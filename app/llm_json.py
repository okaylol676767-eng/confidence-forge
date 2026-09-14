"""Provider-agnostic strict JSON extraction + validation for structured LLM answers.

Shared by the OpenAI-compatible and Gemini clients so both enforce the exact
same output contract (answer, confidence, confidence_reason, uncertainty_factors).

Extraction is deliberately forgiving: models wrapping JSON in fences/prose and
emitting near-JSON (invalid escapes like \\alpha, raw newlines inside strings)
are repaired before we give up — the output contract matters more than purity.
"""
import json
import re
from typing import Any

from .errors import LLMInvalidOutputError
from .schemas import StructuredAnswer

_JSON_BLOCK_RE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL)

# Characters that are legal after a backslash in a JSON string.
_VALID_ESCAPES = set('"\\/bfnrtu')
_HEX_DIGITS = set("0123456789abcdefABCDEF")

_CONTROL_REPLACEMENTS = {"\n": "\\n", "\r": "\\r", "\t": "\\t", "\b": "\\b", "\f": "\\f"}

# LaTeX commands that start with a letter that is ALSO a valid JSON escape
# (b, f, n, t). "\frac" parses as formfeed+"rac", "\theta" as tab+"heta" —
# legal JSON but never what the model meant. When a b/f/n/t escape is
# immediately followed by a lowercase letter run spelling one of these
# commands, treat it as LaTeX and double the backslash.
_LATEX_COMMANDS = {
    # b
    "beta", "bar", "binom", "bigcup", "bigcap", "bigoplus", "bigotimes",
    "bigvee", "bigwedge", "bigodot", "bmod",
    # f
    "frac", "tfrac", "dfrac", "forall",
    # n
    "neq", "nabla", "nu", "notin", "nsubseteq", "nsupseteq", "nmid",
    "nexists", "nleq", "ngeq", "napprox", "nearrow", "nwarrows", "nwarrowsl",
    # t
    "theta", "tan", "tanh", "times", "tau", "text", "textbf", "textit",
    "textrm", "textsf", "therefore", "thereexists", "to", "top",
    "triangle", "triangleq", "triangledown", "triangleleft", "triangleright",
}


def _repair_json(candidate: str) -> str:
    """Repair the two common near-JSON failure modes while preserving content.

    1. Invalid escape sequences: LaTeX is full of backslashes (\\alpha, \\theta)
       and models sometimes emit them single-escaped, which is not valid JSON
       (\\a is not an escape). Doubling the backslash keeps the literal text
       the model meant: "\\alpha" -> parses back to \\alpha.
    2. Raw control characters inside strings: real newlines/tabs (e.g. display
       math on its own lines) are illegal inside JSON strings; they become \\n
       and friends.
    """
    out: list[str] = []
    i = 0
    n = len(candidate)
    in_string = False
    while i < n:
        ch = candidate[i]
        if not in_string:
            if ch == '"':
                in_string = True
            out.append(ch)
            i += 1
            continue
        # ---- inside a JSON string ----
        if ch == "\\":
            nxt = candidate[i + 1] if i + 1 < n else ""
            valid = nxt in _VALID_ESCAPES
            if nxt == "u":
                # \\uXXXX must be followed by exactly 4 hex digits.
                digits = candidate[i + 2 : i + 6]
                valid = len(digits) == 4 and all(d in _HEX_DIGITS for d in digits)
            if valid and nxt in "bfnrt":
                # Ambiguous: legal JSON escape, but likely LaTeX (\frac would
                # parse as formfeed + "rac"). Double the backslash when the
                # letter run starting at the escape spells a known command
                # (run.group(0) includes nxt itself: "frac", "theta", ...).
                run = re.match(r"[a-z]+", candidate[i + 1 :])
                if run and run.group(0) in _LATEX_COMMANDS:
                    valid = False
            if valid:
                out.append(ch)
                out.append(nxt)
                i += 2
            elif nxt == "":
                out.append("\\\\")  # dangling backslash at end of input
                i += 1
            else:
                # Invalid escape: emit a literal backslash + the character.
                out.append("\\\\")
                out.append(nxt)
                i += 2
        elif ch == '"':
            in_string = False
            out.append(ch)
            i += 1
        elif ord(ch) < 0x20:
            out.append(_CONTROL_REPLACEMENTS.get(ch, f"\\u{ord(ch):04x}"))
            i += 1
        else:
            out.append(ch)
            i += 1
    return "".join(out)


def _loads_dict(candidate: str) -> dict[str, Any] | None:
    try:
        parsed = json.loads(candidate)
        return parsed if isinstance(parsed, dict) else None
    except json.JSONDecodeError:
        return None


def extract_json_object(text: str) -> dict[str, Any]:
    """Pull the first JSON object out of raw model text.

    Handles ```json fences, prose before/after the object, invalid escape
    sequences (LaTeX), raw newlines/tabs inside strings, single quotes, and
    trailing commas. Raises LLMInvalidOutputError when nothing parseable is found.
    """
    candidates: list[str] = []
    for match in _JSON_BLOCK_RE.finditer(text):
        candidates.append(match.group(1))
    brace_start = text.find("{")
    if brace_start != -1:
        candidates.append(text[brace_start : text.rfind("}") + 1])

    for candidate in candidates:
        stripped = candidate.strip()
        if not stripped:
            continue
        # Repair FIRST: payloads like "\frac" are *valid* JSON (formfeed +
        # "rac") and would otherwise parse successfully into corrupted text —
        # the repairer must see them before strict parsing does. Properly
        # escaped content (\\frac, \n) passes through the repairer unchanged.
        parsed = _loads_dict(_repair_json(stripped)) or _loads_dict(stripped)
        if parsed is not None:
            return parsed

    # Last resort for the first candidate: quote-style and comma tolerance
    # (applied on top of the repaired text).
    if candidates:
        stripped = candidates[0].strip()
        if stripped:
            repaired = _repair_json(stripped)
            relaxed = repaired.replace("'", '"').rstrip()
            relaxed = re.sub(r",\s*([}\]])", r"\1", relaxed)
            parsed = _loads_dict(relaxed)
            if parsed is not None:
                return parsed

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
    # Optional full derivation. Models omit it, send null, or occasionally
    # send an empty string — all normalize to None so the UI hides the expander.
    detailed = data.get("detailed_solution")
    if not isinstance(detailed, str) or not detailed.strip():
        detailed = None
    return StructuredAnswer(
        answer=data["answer"].strip(),
        confidence=round(confidence, 4),
        confidence_reason=reason.strip(),
        uncertainty_factors=[f.strip() for f in factors if f.strip()],
        detailed_solution=detailed,
    )
