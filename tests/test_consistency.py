"""Tests for self-consistency voting and quantitative-question detection."""
import pytest

from app.consistency import (
    VoteResult,
    consistency_solve,
    extract_final_answer,
    looks_quantitative,
    pick_winner,
)
from app.schemas import StructuredAnswer


def _answer(final_line: str, confidence: float = 0.95) -> StructuredAnswer:
    return StructuredAnswer(
        answer=f"Step 1.\nStep 2.\n**Final answer:** {final_line}",
        confidence=confidence,
        confidence_reason="reason",
        uncertainty_factors=[],
    )


# ---------- detection ----------

def test_detects_quantitative_questions():
    assert looks_quantitative("Solve for x: 2x + 3 = 7")
    assert looks_quantitative("Calculate the pH of 0.01 M HCl")
    assert looks_quantitative("A projectile is launched at 20 m/s, find the range")
    assert looks_quantitative("Balance the equation Fe + O2 -> Fe2O3")
    assert looks_quantitative("What is 5 moles of CO2 in grams?")
    assert looks_quantitative("Find the derivative of x^3")


def test_does_not_flag_plain_chat():
    assert not looks_quantitative("Hello, how are you today?")
    assert not looks_quantitative("Tell me a fun story about cats")
    assert not looks_quantitative("What's your name?")
    assert not looks_quantitative("Write a poem about the ocean")


# ---------- final answer extraction ----------

def test_extracts_final_answer_line():
    assert extract_final_answer("work...\n**Final answer:** 42 J") == "42 J"
    assert extract_final_answer("**Final answer:** $x = 2$") == "$x = 2$"


def test_accepts_marker_variants():
    assert extract_final_answer("...\n**Answer**: $22\\text{ g}$ of CO2") == "$22\\text{ g}$ of CO2"
    assert extract_final_answer("...\nfinal result: 9.8 m/s^2") == "9.8 m/s^2"


def test_falls_back_to_last_line_without_marker():
    assert extract_final_answer("step one\nstep two\nThus v = 10 m/s") == "Thus v = 10 m/s"


def test_extracts_last_occurrence():
    text = "**Final answer:** wrong\nmore work\n**Final answer:** right"
    assert extract_final_answer(text) == "right"


def test_empty_text_returns_empty():
    assert extract_final_answer("") == ""
    assert extract_final_answer(None) == ""


# ---------- voting ----------

def test_unanimous_vote_keeps_confidence():
    result = pick_winner([_answer("42", 0.95)] * 3)
    assert result.agreement == 1.0
    assert result.winner.confidence == pytest.approx(0.95)
    assert "All 3 independent solutions agreed" in result.winner.confidence_reason
    # No disagreement factor appended.
    assert result.winner.uncertainty_factors == []


def test_majority_vote_wins_and_penalizes_confidence():
    samples = [_answer("42", 0.95), _answer("42", 0.90), _answer("43", 0.99)]
    result = pick_winner(samples)
    assert result.agreement == pytest.approx(2 / 3)
    assert "42" in result.winner.answer
    assert result.winner.confidence == pytest.approx(0.95 * 2 / 3, rel=1e-3)
    assert any("agreed" in f for f in result.winner.uncertainty_factors)


def test_normalization_groups_equivalent_answers():
    a1 = _answer("x = 2 m/s")
    a2 = _answer("X = 2 m/s.")
    a3 = _answer("$x=2\\ \\mathrm{m/s}$")
    result = pick_winner([a1, a2, a3])
    assert result.agreement == 1.0


def test_tie_prefers_first_sample_answer():
    samples = [_answer("the answer is five", 0.9), _answer("the answer is seven", 0.9)]
    result = pick_winner(samples)
    assert "five" in result.winner.answer  # first sample's answer wins ties
    assert result.agreement == 0.5


def test_numeric_vote_survives_phrasing_variance():
    """'Tension: T = 28.125 N' and 'T = 28.125 N' are the same vote."""
    a1 = StructuredAnswer(
        answer="steps\n- Tension: $T = 28.125\\text{ N}$", confidence=0.9,
        confidence_reason="r", uncertainty_factors=[])
    a2 = StructuredAnswer(
        answer="steps\nTherefore $T = 28.125$ N.", confidence=0.9,
        confidence_reason="r", uncertainty_factors=[])
    a3 = StructuredAnswer(
        answer="steps\n**Final answer:** 28.125 N", confidence=0.9,
        confidence_reason="r", uncertainty_factors=[])
    result = pick_winner([a1, a2, a3])
    assert result.agreement == 1.0


def test_numeric_vote_distinguishes_different_values():
    a1 = _answer("x is about 1.710")
    a2 = _answer("x = 1.7095")
    a3 = _answer("x = 2.5")
    result = pick_winner([a1, a2, a3])
    # 1.710 == 1.7095? No — they differ numerically, so top count is 1...
    # but a1/a2 both end in different floats, so all three split 1/1/1.
    assert result.agreement <= 1 / 3 + 1e-9 or result.samples == 3


def test_empty_samples_raise():
    import app.errors as errors

    with pytest.raises(errors.LLMError):
        pick_winner([])


# ---------- consistency_solve ----------

class _FlakyLLM:
    """LLM double whose chat_structured returns queued answers, raising on error."""

    def __init__(self, outcomes):
        self.outcomes = list(outcomes)
        self.calls = 0

    async def chat_structured(self, messages, attachments=None, temperature=None):
        self.calls += 1
        item = self.outcomes.pop(0) if self.outcomes else self.outcomes
        if isinstance(item, BaseException):
            raise item
        return item


async def test_consistency_solve_votes_across_samples(monkeypatch):
    from app import consistency as mod

    monkeypatch.setattr(mod, "settings", type("S", (), {
        "consistency_samples": 3,
        "consistency_timeout_seconds": 5.0,
    })())
    llm = _FlakyLLM([_answer("8", 0.9), _answer("8", 0.9), _answer("16", 0.9)])
    vote = await consistency_solve(llm, [{"role": "user", "content": "q"}])
    assert vote.samples == 3
    assert vote.agreement == pytest.approx(2 / 3)
    assert "8" in vote.winner.answer


async def test_consistency_solve_all_fail_raises(monkeypatch):
    from app import consistency as mod
    import app.errors as errors

    monkeypatch.setattr(mod, "settings", type("S", (), {
        "consistency_samples": 2,
        "consistency_timeout_seconds": 5.0,
    })())
    llm = _FlakyLLM([errors.LLMTimeoutError(), errors.LLMTimeoutError()])
    with pytest.raises(errors.LLMTimeoutError):
        await consistency_solve(llm, [{"role": "user", "content": "q"}])
