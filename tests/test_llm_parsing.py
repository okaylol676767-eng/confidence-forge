"""Unit tests for the strict JSON extraction/validation pipeline."""
import pytest

from app.errors import LLMInvalidOutputError
from app.llm import extract_json_object, validate_structured_answer


def test_extracts_plain_json():
    data = extract_json_object('{"answer": "hi", "confidence": 0.9}')
    assert data["answer"] == "hi"


def test_extracts_json_from_code_fence():
    text = 'Sure! Here you go:\n```json\n{"answer": "hi", "confidence": 0.9}\n```'
    assert extract_json_object(text)["answer"] == "hi"


def test_extracts_json_with_surrounding_prose():
    text = 'The answer is {"answer": "hi", "confidence": 0.9} as requested.'
    assert extract_json_object(text)["confidence"] == 0.9


def test_raises_on_non_json():
    with pytest.raises(LLMInvalidOutputError):
        extract_json_object("I cannot answer that in JSON.")


def test_validates_full_answer():
    structured = validate_structured_answer({
        "answer": "Paris",
        "confidence": 0.93,
        "confidence_reason": "Common knowledge",
        "uncertainty_factors": [],
    })
    assert structured.answer == "Paris"
    assert structured.confidence == pytest.approx(0.93)
    assert structured.uncertainty_factors == []


def test_missing_required_field_raises():
    with pytest.raises(LLMInvalidOutputError) as excinfo:
        validate_structured_answer({"answer": "x", "confidence": 0.5})
    assert "confidence_reason" in str(excinfo.value)


def test_confidence_out_of_range_raises():
    with pytest.raises(LLMInvalidOutputError):
        validate_structured_answer({
            "answer": "x", "confidence": 1.5, "confidence_reason": "r",
        })


def test_confidence_non_numeric_raises():
    with pytest.raises(LLMInvalidOutputError):
        validate_structured_answer({
            "answer": "x", "confidence": "high", "confidence_reason": "r",
        })


def test_uncertainty_factors_wrong_type_raises():
    with pytest.raises(LLMInvalidOutputError):
        validate_structured_answer({
            "answer": "x", "confidence": 0.5, "confidence_reason": "r",
            "uncertainty_factors": "not a list",
        })


def test_missing_uncertainty_factors_defaults_to_empty():
    structured = validate_structured_answer({
        "answer": "x", "confidence": 0.5, "confidence_reason": "r",
    })
    assert structured.uncertainty_factors == []
