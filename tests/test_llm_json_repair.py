"""Tests for near-JSON repair: invalid LaTeX escapes and raw control characters."""
from app.llm import extract_json_object  # re-exported from app.llm_json
from app.llm_json import _repair_json
from app.errors import LLMInvalidOutputError


def _payload(answer: str) -> str:
    import json

    return json.dumps({
        "answer": answer,
        "confidence": 0.9,
        "confidence_reason": "math",
        "uncertainty_factors": [],
    })


def test_probe_frac_repair():
    """Diagnostic: show exactly what the repairer does with \frac."""
    raw = '{"answer": "$\\frac{a}{b}$", "confidence": 0.9, "confidence_reason": "r"}'
    rep = _repair_json(raw)
    print("\nRAW     :", raw)
    print("REPAIRED:", rep)
    data = extract_json_object(raw)
    print("PARSED  :", repr(data["answer"]))
    assert "\\frac" in data["answer"], f"repair failed, got: {data['answer']!r}"


def test_single_escaped_latex_backslash_is_repaired():
    """\\alpha (invalid JSON escape) must survive as literal \\alpha text."""
    raw = '{"answer": "value of \\alpha here", "confidence": 0.9, "confidence_reason": "r"}'
    data = extract_json_object(raw)
    assert data["answer"] == "value of \\alpha here"


def test_display_math_with_literal_newlines_is_repaired():
    """A raw newline inside a JSON string (display math on its own line) is repaired."""
    raw = (
        '{\n  "answer": "Solve:\n$$x = 2$$\nDone.",\n'
        '  "confidence": 0.88, "confidence_reason": "clear"\n}'
    )
    data = extract_json_object(raw)
    assert "$$x = 2$$" in data["answer"]
    assert "\n" in data["answer"]


def test_latex_with_tabs_repaired():
    raw = '{"answer": "a\tb", "confidence": 0.5, "confidence_reason": "r"}'
    data = extract_json_object(raw)
    assert data["answer"] == "a\tb"


def test_valid_json_still_parses_untouched():
    data = extract_json_object(_payload("plain answer"))
    assert data["answer"] == "plain answer"


def test_properly_escaped_backslash_n_round_trips():
    # json.dumps of a literal backslash+n -> \\n in JSON -> parses back to backslash+n.
    data = extract_json_object(_payload("line1\\nline2"))
    assert data["answer"] == "line1\\nline2"


def test_properly_escaped_real_newline_round_trips():
    # A well-behaved model escaping a real newline as \n still parses to a newline.
    data = extract_json_object(_payload("line1\nline2"))
    assert data["answer"] == "line1\nline2"


def test_valid_unicode_escape_survives():
    raw = '{"answer": "caf\\u00e9", "confidence": 0.9, "confidence_reason": "r"}'
    data = extract_json_object(raw)
    assert data["answer"] == "café"


def test_truncated_unicode_escape_repaired():
    raw = '{"answer": "caf\\u00", "confidence": 0.9, "confidence_reason": "r"}'
    data = extract_json_object(raw)
    assert data["answer"] == "caf\\u00"


def test_hopeless_garbage_still_raises():
    import pytest

    with pytest.raises(LLMInvalidOutputError):
        extract_json_object("no json at all")


def test_full_math_answer_round_trips():
    """The exact class of payload that 502'd: LaTeX + display math + newlines."""
    answer = (
        "Substitute $3$ for \\alpha:\n\n"
        "$$5 - 3^2 = 5 - 9 = -4$$\n\n"
        "So $5 - \\alpha^2 = -4$."
    )
    raw = '{"answer": "Substitute $3$ for \\alpha:\n\n$$5 - 3^2 = 5 - 9 = -4$$\n\nSo $5 - \\alpha^2 = -4$.", "confidence": 0.95, "confidence_reason": "straightforward arithmetic"}'
    data = extract_json_object(raw)
    assert data["answer"] == answer
