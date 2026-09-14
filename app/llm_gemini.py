"""Google Gemini client producing the same structured JSON contract as the OpenAI client.

Isolates all Gemini specifics (SDK quirks, error mapping, JSON-mode retry) so the
rest of the app only ever sees StructuredAnswer or typed AppErrors.
"""
from typing import Any

import google.generativeai as genai

from .config import Settings, get_logger, get_settings
from .errors import (
    LLMBadResponseError,
    LLMError,
    LLMNotConfiguredError,
    LLMRateLimitError,
    LLMTimeoutError,
    LLMUnavailableError,
)
from .llm_json import extract_json_object, validate_structured_answer
from .schemas import StructuredAnswer

logger = get_logger("llm_gemini")


def _gexc():
    """Lazy import of google.api_core.exceptions (dep of google-generativeai)."""
    from google.api_core import exceptions as gexc

    return gexc


def _map_gemini_error(exc: Exception) -> LLMError:
    """Map google-api-core exceptions to typed errors; messages stay generic."""
    gexc = _gexc()
    text = str(exc)

    if isinstance(exc, gexc.DeadlineExceeded):
        return LLMTimeoutError()
    if isinstance(exc, gexc.TooManyRequests) or "429" in text:
        return LLMRateLimitError()
    if isinstance(exc, gexc.RetryError):
        cause = getattr(exc, "cause", None) or exc.__cause__
        if isinstance(cause, gexc.TooManyRequests):
            return LLMRateLimitError()
        if isinstance(cause, gexc.DeadlineExceeded):
            return LLMTimeoutError()
        return LLMUnavailableError()
    if isinstance(exc, (gexc.ServiceUnavailable, gexc.InternalServerError)):
        return LLMUnavailableError()
    if isinstance(exc, gexc.GoogleAPIError):
        return LLMBadResponseError()
    return LLMBadResponseError()


class GeminiClient:
    """Thin async wrapper over the Gemini API with the shared JSON contract."""

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()
        self._model: Any = None

    # ---- public API (mirrors LLMClient) ----

    async def complete(self, messages: list[dict[str, str]], json_mode: bool = False) -> str:
        """Send a flattened conversation, return raw model text; typed errors on failure."""
        model = self._ensure_model()
        prompt = self._flatten(messages)

        def generation_config(use_json_mode: bool) -> dict[str, Any]:
            config: dict[str, Any] = {
                "temperature": self._settings.llm_temperature,
                "max_output_tokens": self._settings.llm_max_tokens,
            }
            if use_json_mode:
                config["response_mime_type"] = "application/json"
            return config

        async def generate(use_json_mode: bool) -> Any:
            return await model.generate_content_async(
                prompt,
                generation_config=generation_config(use_json_mode),
                request_options={"timeout": self._settings.llm_timeout_seconds},
            )

        try:
            response = await generate(json_mode)
        except Exception as exc:
            gexc = _gexc()
            # Some Gemini models/endpoints reject response_mime_type; fall back gracefully.
            if isinstance(exc, gexc.InvalidArgument) and "response_mime_type" in str(exc):
                logger.warning("Gemini rejected JSON mode; retrying without response_mime_type")
                try:
                    response = await generate(False)
                except Exception as retry_exc:
                    raise _map_gemini_error(retry_exc) from retry_exc
            else:
                raise _map_gemini_error(exc) from exc

        return self._extract_text(response)

    async def chat_structured(self, messages: list[dict[str, str]]) -> StructuredAnswer:
        """Full pipeline: complete -> extract JSON -> validate -> StructuredAnswer."""
        raw = await self.complete(messages, json_mode=self._settings.llm_json_mode)
        logger.debug("Gemini raw response (%d chars)", len(raw))
        try:
            data = extract_json_object(raw)
        except LLMError:
            logger.error("Could not extract JSON from Gemini output: %.500s", raw)
            raise
        return validate_structured_answer(data)

    # ---- internals ----

    def _ensure_model(self):
        if not self._settings.gemini_api_key:
            raise LLMNotConfiguredError()
        if self._model is None:
            genai.configure(api_key=self._settings.gemini_api_key)
            self._model = genai.GenerativeModel(model_name=self._settings.gemini_model)
        return self._model

    @staticmethod
    def _flatten(messages: list[dict[str, str]]) -> str:
        """Gemini has no chat message list on generate_content: flatten to one prompt."""
        parts: list[str] = []
        for message in messages:
            role = message.get("role", "user")
            content = message.get("content", "")
            if role == "system":
                parts.append(f"[System instructions]\n{content}")
            elif role == "assistant":
                parts.append(f"[Previous assistant message]\n{content}")
            else:
                parts.append(f"[User message]\n{content}")
        return "\n\n".join(parts)

    @staticmethod
    def _extract_text(response: Any) -> str:
        """Pull text out of a GenerateContentResponse; map blocked/empty to typed errors."""
        text = ""
        try:
            text = (response.text or "").strip()
        except (ValueError, AttributeError):
            text = ""

        if not text:
            block_reason = getattr(getattr(response, "prompt_feedback", None), "block_reason", None)
            if block_reason:
                logger.error("Gemini blocked the request (block_reason=%s)", block_reason)
                raise LLMBadResponseError("The model refused this request (safety filter).")
            candidates = getattr(response, "candidates", None) or []
            finish_reason = getattr(candidates[0], "finish_reason", None) if candidates else None
            logger.error("Gemini returned empty text (finish_reason=%s)", finish_reason)
            raise LLMBadResponseError("The model returned an empty response. Please retry.")
        return text
