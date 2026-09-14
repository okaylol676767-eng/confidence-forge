"""Provider-agnostic strict JSON extraction + validation for structured LLM answers.

Shared by the OpenAI-compatible and Gemini clients so both enforce the exact
same output contract (answer, confidence, confidence_reason, uncertainty_factors).
"""
import json
import re
from typing import Any

from .errors import LLMInvalidOutputError
from .schemas import StructuredAnswer

_JSON_BLOCK_RE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL)


def extract_json_object(text: str) -> dict[str, Any]:
    """Pull the first JSON object out of raw model text (handles ```json fences,
    prose before/after the object, and single quotes / trailing commas)."""
    candidates: list[str] = []
    for match in _JSON_BLOCK_RE.finditer(text):
        candidates.append(match.group(1))
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
    missing = [f for f in ("answer", "confidence", "confidence_reason") if f not in data]
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
