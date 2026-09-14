"""OpenAI-compatible LLM client that forces strict JSON output.

Pure LLM plumbing: no FastAPI, no DB. Raises typed errors from app.errors so
routers can map them to the standard JSON envelope.
"""
import json
import re
from typing import Any

from openai import (
    APIConnectionError,
    APITimeoutError,
    AsyncOpenAI,
    RateLimitError,
)

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

_JSON_BLOCK_RE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL)


def extract_json_object(text: str) -> dict[str, Any]:
    """Pull the first JSON object out of raw model text (handles ```json fences,
    prose before/after the object, and single quotes / trailing commas)."""
    candidates: list[str] = []

    for match in _JSON_BLOCK_RE.finditer(text):
        candidates.append(match.group(1))
    # First {...} span anywhere in the text, including multi-line.
    brace_start = text.find("{")
    if brace_start != -1:
        candidates.append(text[brace_start: text.rfind("}") + 1])

    for candidate in candidates:
        candidate = candidate.strip()
        if not candidate:
            continue
        try:
            parsed = json.loads(candidate)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            continue

    # Last resort: tolerate single quotes and trailing commas.
    if candidates:
        relaxed = candidates[0].replace("'", '"').rstrip()
        relaxed = re.sub(r",\s*([}\]])", r"\1", relaxed)
        try:
            parsed = json.loads(relaxed)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass

    raise LLMInvalidOutputError("LLM did not return a valid JSON object.")


def validate_structured_answer(data: dict[str, Any]) -> StructuredAnswer:
    """Validate the raw parsed JSON into a StructuredAnswer; raises LLMInvalidOutputError."""
    missing = [field for field in ("answer", "confidence", "confidence_reason") if field not in data]
    if missing:
        raise LLMInvalidOutputError(f"LLM JSON is missing required fields: {', '.join(missing)}")
    if not isinstance(data["answer"], str) or not data["answer"].strip():
        raise LLMInvalidOutputError("'answer' must be a non-empty string.")
    try:
        confidence = float(data["confidence"])
    except (TypeError, ValueError) as exc:
        raise LLMInvalidOutputError("'confidence' must be a number between 0 and 1.") from exc
    if not 0.0 <= confidence <= 1.0:
        raise LLMInvalidOutputError(f"'confidence' out of range: {confidence}")
    reason = data["confidence_reason"]
    if not isinstance(reason, str) or not reason.strip():
        raise LLMInvalidOutputError("'confidence_reason' must be a non-empty string.")

    factors = data.get("uncertainty_factors", [])
    if factors is None:
        factors = []
    if not isinstance(factors, list) or not all(isinstance(f, str) for f in factors):
        raise LLMInvalidOutputError("'uncertainty_factors' must be an array of strings.")

    return StructuredAnswer(
        answer=data["answer"].strip(),
        confidence=round(confidence, 4),
        confidence_reason=reason.strip(),
        uncertainty_factors=[f.strip() for f in factors if f.strip()],
    )


class LLMClient:
    """Thin async wrapper over an OpenAI-compatible chat completion API."""

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()
        self._client: AsyncOpenAI | None = None

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

    async def complete(self, messages: list[dict[str, str]]) -> str:
        """Send chat messages, return raw completion text; raises typed LLMError."""
        client = self._ensure_client()
        kwargs: dict[str, Any] = {
            "model": self._settings.llm_model,
            "messages": messages,
            "temperature": self._settings.llm_temperature,
            "max_tokens": self._settings.llm_max_tokens,
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
        message = response.choices[0].message
        content = (message.content or "").strip()
        if not content:
            logger.error("LLM response contained empty content (finish_reason=%s)",
                         response.choices[0].finish_reason)
            raise LLMBadResponseError("LLM returned empty content.")
        return content

    async def chat_structured(self, messages: list[dict[str, str]]) -> StructuredAnswer:
        """Full pipeline: complete -> extract JSON -> validate -> StructuredAnswer."""
        raw = await self.complete(messages)
        logger.debug("LLM raw response (%d chars): %.200s", len(raw), raw)  # may contain user content
        try:
            data = extract_json_object(raw)
        except LLMInvalidOutputError:
            logger.error("Could not extract JSON from LLM output: %.500s", raw)
            raise
        return validate_structured_answer(data)


# Singleton used by the app (overridable in tests).
llm_client = LLMClient()
