"""Skeptic verification: confirm, refute+arbitrate, fail-open, gating."""
import json

import pytest

from app.schemas import StructuredAnswer
from app.verification import (
    VerificationResult,
    _verification_applicable,
    verify_and_finalize,
)


def _answer(text: str, confidence: float = 0.9) -> StructuredAnswer:
    return StructuredAnswer(
        answer=text,
        confidence=confidence,
        confidence_reason="r",
        uncertainty_factors=[],
        detailed_solution=None,
    )


def _payload(**overrides) -> str:
    base = {
        "answer": "The acceleration is 9.8 m/s^2 downward.",
        "confidence": 0.93,
        "confidence_reason": "independent derivation",
        "uncertainty_factors": [],
        "detailed_solution": None,
    }
    base.update(overrides)
    return json.dumps(base)


class StubLLM:
    """Queued raw completions; records (messages, kwargs) per call."""

    def __init__(self, raws: list[str]) -> None:
        self.raws = list(raws)
        self.calls: list[tuple[list[dict], dict]] = []
        self.last_usage = (111, 222)

    async def complete(self, messages, attachments=None, **kwargs):
        self.calls.append((messages, kwargs))
        return self.raws.pop(0)


MESSAGES = [{"role": "user", "content": "A ball falls for 2s. What is its acceleration?"}]


@pytest.mark.asyncio
async def test_confirmed_keeps_draft_and_reports():
    llm = StubLLM([_payload(verdict="confirmed", issue="")])
    draft = _answer("9.8 m/s^2 downward", 0.85)

    result = await verify_and_finalize(llm, MESSAGES, draft, draft_tokens=(50, 60))

    assert result.verdict == "confirmed"
    assert result.answer is draft  # draft ships unchanged
    assert result.token_usage == (161, 282)  # draft + verify tokens combined
    # The verifier saw the draft labeled as a CLAIM to attack.
    verifier_prompt = llm.calls[0][0][0]["content"]
    assert "CLAIM to attack" in verifier_prompt
    assert "Do NOT trust the user" in verifier_prompt


@pytest.mark.asyncio
async def test_refuted_then_arbiter_picks_correction():
    llm = StubLLM(
        [
            _payload(
                verdict="refuted",
                issue="draft used 9.8 for a 2s free-fall on the Moon (1.62 m/s^2)",
                answer="The acceleration is 1.62 m/s^2 (Moon).",
                confidence=0.97,
            ),
            _payload(winner="B", reason="Moon premise checks out; A used Earth g"),
        ]
    )
    draft = _answer("9.8 m/s^2 downward", 0.85)

    result = await verify_and_finalize(llm, MESSAGES, draft)

    assert result.verdict == "corrected"
    assert "1.62" in result.answer.answer  # correction shipped
    assert any("corrected the initial answer" in f for f in result.answer.uncertainty_factors)
    # Arbitration was blind: both solutions presented as A/B, no origin hints.
    arbiter_user = llm.calls[1][0][-1]["content"]
    assert "SOLUTION A:" in arbiter_user and "SOLUTION B:" in arbiter_user


@pytest.mark.asyncio
async def test_refuted_then_arbiter_keeps_draft_when_a_wins():
    llm = StubLLM(
        [
            _payload(verdict="refuted", issue="units look off", answer="alternative 42"),
            _payload(winner="A", reason="A is dimensionally consistent"),
        ]
    )
    draft = _answer("42 m")

    result = await verify_and_finalize(llm, MESSAGES, draft)

    assert result.verdict == "corrected"
    assert result.answer.answer == "42 m"  # draft survived on the merits


@pytest.mark.asyncio
async def test_fail_open_on_verifier_error():
    llm = StubLLM(["this is not json"])
    draft = _answer("draft stands")

    result = await verify_and_finalize(llm, MESSAGES, draft)

    assert result.verdict == "unavailable"
    assert result.answer is draft


@pytest.mark.asyncio
async def test_fail_open_on_arbiter_error_ships_correction():
    llm = StubLLM(
        [
            _payload(verdict="refuted", issue="wrong constant", answer="3.0e8 m/s", confidence=0.99),
            "arbitration garbage",
        ]
    )
    draft = _answer("300,000 km/s")

    result = await verify_and_finalize(llm, MESSAGES, draft)

    assert result.verdict == "corrected"
    assert "3.0e8" in result.answer.answer
    assert any("refuted during verification" in f for f in result.answer.uncertainty_factors)


def test_gating_skips_trivial_arithmetic_and_attachments():
    assert _verification_applicable("What is 7 x 8?", 0) is False
    assert _verification_applicable("Explain orbits", 2) is False
    assert _verification_applicable("Explain orbits", 0) is True
