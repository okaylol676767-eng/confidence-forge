"""OpenAI-compatible LLM client that forces strict JSON output.

Pure LLM plumbing: no FastAPI, no DB. Raises typed errors from app.errors so
routers can map them to the standard JSON envelope.
"""
import base64
from typing import Any

from openai import (
    APIConnectionError,
    APITimeoutError,
    AsyncOpenAI,
    RateLimitError,
)

from .attachments import Attachment
from .llm_json import (  # re-exported for tests/tools
    chat_structured_repaired,
    extract_json_object,
    validate_structured_answer,
)  # noqa: F401 (re-exported)
from .schemas import StructuredAnswer
from .config import Settings, get_settings, get_logger
from .errors import (
    LLMBadResponseError,
    LLMInvalidOutputError,
    LLMNotConfiguredError,
    LLMRateLimitError,
    LLMTimeoutError,
    LLMUnavailableError,
)

logger = get_logger("llm")

# Single source of truth for JSON validation lives in llm_json; re-exported
# here because services and tests have always imported it from this module.
from .llm_json import validate_structured_answer  # noqa: E402,F401


class LLMClient:
    """Thin async wrapper over an OpenAI-compatible chat completion API."""

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()
        self._client: AsyncOpenAI | None = None
        # (input_tokens, output_tokens) of the most recent completion, from the
        # API's usage block. None until a call succeeds; consumed for observability.
        self.last_usage: tuple[int, int] | None = None

    def _ensure_client(self) -> AsyncOpenAI:
        if not self._settings.openai_api_key:
            raise LLMNotConfiguredError()
        if self._client is None:
            self._client = AsyncOpenAI(
                api_key=self._settings.openai_api_key,
                base_url=self._settings.openai_base_url,
                timeout=self._settings.llm_timeout_seconds,
                max_retries=self._settings.llm_max_retries,
            )
        return self._client

    async def complete(
        self,
        messages: list[dict[str, str]],
        attachments: list[Attachment] | None = None,
        temperature: float | None = None,
        max_tokens_override: int | None = None,
    ) -> str:
        """Send chat messages (+ optional file attachments), return raw completion text.

        max_tokens_override exists for the internal MAX_TOKENS retry (doubles
        the output budget once); callers should not pass it.
        """
        client = self._ensure_client()
        outbound_messages: list[dict[str, Any]] = [
            dict(message) for message in messages
        ]
        if attachments:
            # Only the final user turn carries the files.
            last_user = next(
                (m for m in reversed(outbound_messages) if m.get("role") == "user"), None
            )
            if last_user is not None:
                last_user["content"] = self._build_multimodal_content(
                    str(last_user.get("content", "")), attachments
                )
        kwargs: dict[str, Any] = {
            "model": self._settings.llm_model,
            "messages": outbound_messages,
            "temperature": self._settings.llm_temperature if temperature is None else temperature,
            "max_tokens": (
                self._settings.llm_max_tokens if max_tokens_override is None else max_tokens_override
            ),
        }
        if self._settings.llm_json_mode:
            kwargs["response_format"] = {"type": "json_object"}
        try:
            response = await client.chat.completions.create(**kwargs)
        except APITimeoutError as exc:
            logger.error("LLM timeout after %ss: %s", self._settings.llm_timeout_seconds, exc)
            raise LLMTimeoutError() from exc
        except RateLimitError as exc:
            logger.error("LLM rate limited: %s", exc)
            raise LLMRateLimitError() from exc
        except APIConnectionError as exc:
            logger.error("LLM connection error: %s", exc)
            raise LLMUnavailableError() from exc
        except APIError as exc:
            logger.error("LLM API error (status=%s): %s", getattr(exc, "status_code", "?"), exc)
            raise LLMBadResponseError() from exc
        except Exception as exc:
            logger.exception("Unexpected LLM client error")
            raise LLMBadResponseError() from exc

        if not response.choices:
            logger.error("LLM response contained no choices")
            raise LLMBadResponseError("LLM returned no choices.")
        usage = getattr(response, "usage", None)
        self.last_usage = (
            int(getattr(usage, "prompt_tokens", 0) or 0),
            int(getattr(usage, "completion_tokens", 0) or 0),
        ) if usage is not None else None
        message = response.choices[0].message
        content = (message.content or "").strip()
        finish_reason = str(response.choices[0].finish_reason or "")
        self._last_finish_reason = finish_reason

        # Truncated mid-generation (finish_reason="length"): retry once with a
        # doubled budget. A cut-off JSON document is unparseable, so a bigger
        # cap is the only fix; parity with the Gemini client's behavior.
        if finish_reason == "length" and max_tokens_override is None:
            doubled = self._settings.llm_max_tokens * 2
            logger.warning(
                "LLM output truncated (finish_reason=length at %d tokens); retrying once with %d",
                self._settings.llm_max_tokens, doubled,
            )
            return await self.complete(
                messages,
                attachments=attachments,
                temperature=temperature,
                max_tokens_override=doubled,
            )
        if not content:
            logger.error("LLM response contained empty content (finish_reason=%s)", finish_reason)
            raise LLMBadResponseError("LLM returned empty content.")
        return content

    @staticmethod
    def _build_multimodal_content(
        text: str, attachments: list[Attachment]
    ) -> list[dict[str, Any]]:
        """OpenAI vision format: text parts + image_url parts (+ doc text inline)."""
        parts: list[dict[str, Any]] = []
        for attachment in attachments:
            if attachment.is_image:
                encoded = base64.b64encode(attachment.data).decode("ascii")
                parts.append({
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:{attachment.mime_type};base64,{encoded}",
                    },
                })
            else:
                if (
                    attachment.mime_type == "application/pdf"
                    and attachment.extracted_text
                ):
                    doc_text = attachment.extracted_text
                else:
                    try:
                        doc_text = attachment.data.decode("utf-8")
                    except UnicodeDecodeError:
                        doc_text = "(binary or non-UTF-8 document; content omitted)"
                parts.append({
                    "type": "text",
                    "text": (
                        f"[Attached document: {attachment.filename} ({attachment.mime_type})]\n"
                        f"File name: {attachment.filename}. Answer ONLY from this document's "
                        f"actual content below; if the content does not contain what was asked, "
                        f"say so explicitly instead of inventing it.\n{doc_text}"
                    ),
                })
        parts.append({"type": "text", "text": text})
        return parts

    async def chat_structured(
        self,
        messages: list[dict[str, str]],
        attachments: list[Attachment] | None = None,
        temperature: float | None = None,
    ) -> StructuredAnswer:
        """Full pipeline: complete -> extract JSON -> validate -> repair retry."""

        async def once(msgs: list[dict[str, str]], **kwargs: Any) -> str:
            return await self.complete(msgs, attachments=attachments, temperature=temperature)

        def check(data: dict[str, Any]) -> StructuredAnswer:
            return validate_structured_answer(data)

        def repairable(exc: LLMInvalidOutputError) -> bool:
            # finish_reason="length" already consumed its doubled-cap retry.
            return getattr(self, "_last_finish_reason", "") != "length"

        return await chat_structured_repaired(once, messages, check, should_repair=repairable)


# Singleton used by the app (overridable in tests).
llm_client = LLMClient()
