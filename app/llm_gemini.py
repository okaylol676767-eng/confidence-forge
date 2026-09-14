"""Google Gemini client producing the same structured JSON contract as the OpenAI client.

Isolates all Gemini specifics (SDK quirks, error mapping, JSON-mode retry) so the
rest of the app only ever sees StructuredAnswer or typed AppErrors.
"""
from asyncio import sleep as _sleep
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


def _is_transient(exc: Exception) -> bool:
    """True for failures worth retrying (rate limits, 5xx, deadline)."""
    gexc = _gexc()
    if isinstance(exc, (gexc.DeadlineExceeded, gexc.TooManyRequests,
                        gexc.ServiceUnavailable, gexc.InternalServerError)):
        return True
    # The SDK gave up on its own internal retries; one client-level retry is
    # still worth trying (its cause was usually a transient status).
    return isinstance(exc, gexc.RetryError)


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
            response = await self._generate_with_retries(
                model, prompt, json_mode, generation_config, generate,
            )
        except Exception as exc:
            raise _map_gemini_error(exc) from exc

        return self._extract_text(response)

    async def _generate_with_retries(
        self, model, prompt, json_mode, generation_config, generate,
    ):
        """Call Gemini with client-level retries on transient failures.

        Mirrors the OpenAI client (max_retries setting). The JSON-mode
        response_mime_type fallback switches modes without consuming a retry.
        Retries raise the last raw exception; the caller maps it once.
        """
        use_json_mode = json_mode
        max_attempts = self._settings.llm_max_retries + 1
        attempt = 0
        while True:
            try:
                return await generate(use_json_mode)
            except Exception as exc:
                gexc = _gexc()
                if isinstance(exc, gexc.InvalidArgument) and "response_mime_type" in str(exc):
                    if use_json_mode:
                        logger.warning("Gemini rejected JSON mode; retrying without response_mime_type")
                        use_json_mode = False
                        continue
                if attempt >= max_attempts - 1 or not _is_transient(exc):
                    raise
                attempt += 1
                delay = min(1.5 * (2 ** (attempt - 1)), 6.0)
                logger.warning(
                    "Gemini transient error (%s), retry %d/%d in %.1fs",
                    type(exc).__name__, attempt, self._settings.llm_max_retries, delay,
                )
                await _sleep(delay)

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
