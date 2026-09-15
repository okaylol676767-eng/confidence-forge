"""Independent verification of draft answers: skeptic re-check, then arbitrate.

Design (the anti-sycophancy core of the app):

1. DRAFT — the existing pipeline produces an answer (self-consistency vote
   on quantitative questions, single call otherwise).
2. VERIFY — a second model call re-derives the answer SKEPTICALLY. It does
   not see the draft's reasoning chain; it sees the draft's final answer
   labeled as a CLAIM to attack, and every user assertion is treated as a
   claim to check, never as ground truth. Its job: try to find a real error.
3. ARBITRATE — if the verifier CONFIRMS, the draft ships. If it REFUTES, a
   third call sees both competing answers in randomized-feeling order (A/B,
   blind to which came first) and must decide on the merits alone. The draft
   does NOT win just for existing.

Fail-open: any verification failure (LLM error, malformed JSON) keeps the
draft with verification marked unavailable — a broken checker must never
break the chat. Enabled with VERIFICATION_ENABLED=true (off by default);
per-request override via ChatRequest.self_verified=false.
"""
import re
from dataclasses import dataclass
from typing import Any, Literal

from .config import get_logger, get_settings
from .consistency import is_trivial_arithmetic
from .errors import LLMError
from .llm_json import extract_json_object, validate_structured_answer
from .schemas import StructuredAnswer

logger = get_logger("verification")
settings = get_settings()

Verdict = Literal["confirmed", "corrected", "unavailable"]

VERIFIER_PROMPT = """\
You are the VERIFIER in a two-agent correctness check. A draft answer to the \
conversation below was produced by another model instance. Your job is to try \
to FIND A REAL ERROR in it — you are skeptical by design.

Rules of engagement:
1. Do NOT trust the draft. Treat its final answer as a CLAIM to attack, not a fact.
2. Do NOT trust the user either. Any statement of fact, number, or premise the \
user asserted is also a CLAIM to check against your own derivation.
3. Re-derive independently from the original question. Do not assume the \
draft's approach, units, or intermediate steps are right.
4. If the draft is fully correct, verdict = "confirmed". If the draft is \
wrong, partially wrong, or rests on a false user premise, verdict = \
"refuted" and you must supply your own corrected full answer.
5. Judge substance, not phrasing: a different wording of the same correct \
result is still "confirmed".

Reply with ONE strict JSON object and nothing else:
{"verdict": "confirmed" or "refuted",
 "issue": string (empty when confirmed; otherwise the concrete error found),
 "answer": string (your corrected full answer when refuted; repeat the draft's answer when confirmed),
 "confidence": number (your independent confidence in YOUR verdict, 0.0-1.0),
 "confidence_reason": string,
 "uncertainty_factors": array of strings}
"""

ARBITER_PROMPT = """\
Two independent solutions to the same problem below disagree. You are the \
ARBITER. The solutions are labeled A and B; you do not know and must not \
guess which one the main agent produced. Decide ONLY on the mathematics, \
physics, or chemistry and the evidence. Do not rewrite either solution.

Reply with ONE strict JSON object and nothing else:
{"winner": "A" or "B",
 "reason": string (one or two sentences naming the decisive check),
 "confidence": number (0.0-1.0),
 "confidence_reason": string,
 "uncertainty_factors": array of strings}
"""


@dataclass(frozen=True)
class VerificationResult:
    """Outcome of the draft -> verify -> arbitrate pipeline."""

    answer: StructuredAnswer
    verdict: Verdict
    detail: str  # human-readable note for the UI
    # (input, output) tokens across verification + arbitration calls
    # (draft tokens included by the caller when passed in).
    token_usage: tuple[int, int] | None = None


def _verification_applicable(message: str, attachment_count: int) -> bool:
    """Skip trivial arithmetic and attachment turns; require a real question."""
    if attachment_count > 0 or is_trivial_arithmetic(message):
        return False
    return bool((message or "").strip())


def _verifier_message(draft_answer: str) -> dict[str, str]:
    return {
        "role": "user",
        "content": (
            f"DRAFT ANSWER (a claim to attack): {draft_answer}\n\n"
            "Verify it independently per your instructions."
        ),
    }


def _arbiter_message(solution_a: str, solution_b: str) -> dict[str, str]:
    return {
        "role": "user",
        "content": (
            f"SOLUTION A:\n{solution_a}\n\n"
            f"SOLUTION B:\n{solution_b}\n\n"
            "Decide which solution is correct, per your instructions."
        ),
    }


def _validated_verdict(data: dict[str, Any]) -> tuple[str, str, StructuredAnswer]:
    """Validate a verifier payload -> (verdict, issue, answer StructuredAnswer)."""
    verdict = str(data.get("verdict", "")).strip().lower()
    if verdict not in {"confirmed", "refuted"}:
        raise LLMError(f"Verifier returned unknown verdict: {verdict!r}")
    issue = str(data.get("issue", "") or "").strip()
    answer = validate_structured_answer(data)
    return verdict, issue, answer


def _validate_arbitration(data: dict[str, Any]) -> tuple[str, str]:
    """Validate an arbiter payload -> (winner 'A'|'B', reason).

    The arbiter only PICKS the winner; the winning text is selected by the
    caller from the solutions it already holds. Asking the arbiter to echo
    the winning answer verbatim would let paraphrasing or truncation
    corrupt the shipped content.
    """
    winner = str(data.get("winner", "")).strip().upper()
    if winner not in {"A", "B"}:
        raise LLMError(f"Arbiter returned unknown winner: {winner!r}")
    reason = str(data.get("reason", "") or "").strip()
    return winner, reason


def _combine(*batches: tuple[int, int] | None) -> tuple[int, int] | None:
    """Sum token batches, ignoring Nones; None when nothing was reported."""
    total = [0, 0]
    seen = False
    for batch in batches:
        if batch:
            seen = True
            total[0] += int(batch[0])
            total[1] += int(batch[1])
    return (total[0], total[1]) if seen else None


async def verify_and_finalize(
    llm,
    messages: list[dict[str, str]],
    draft: StructuredAnswer,
    attachments: list[Any] | None = None,
    draft_tokens: tuple[int, int] | None = None,
) -> VerificationResult:
    """Skeptic re-check of ``draft``; arbitration on disagreement. Fail-open."""
    if not _verification_applicable(
        str(messages[-1].get("content", "")) if messages else "", len(attachments or [])
    ):
        return VerificationResult(
            answer=draft, verdict="unavailable",
            detail="not applicable for this turn", token_usage=draft_tokens,
        )

    verifier_messages = [
        {"role": "system", "content": VERIFIER_PROMPT},
        *messages,
        _verifier_message(draft.answer),
    ]
    try:
        verifier_raw = await llm.complete(
            verifier_messages, attachments=list(attachments or []), json_mode=True
        )
        verify_tokens = getattr(llm, "last_usage", None)
        verdict, issue, verifier_answer = _validated_verdict(
            extract_json_object(verifier_raw)
        )
    except LLMError as exc:
        logger.warning("verification unavailable (%s); shipping draft", exc)
        return VerificationResult(
            answer=draft, verdict="unavailable",
            detail="verification could not run", token_usage=draft_tokens,
        )

    if verdict == "confirmed":
        logger.info("verification: draft confirmed (%s)", (verifier_answer.confidence_reason or "")[:80])
        return VerificationResult(
            answer=draft, verdict="confirmed",
            detail="independently re-derived and confirmed",
            token_usage=_combine(draft_tokens, verify_tokens),
        )

    # ---- REFUTED: arbitration between the draft and the correction ----
    logger.info("verification: draft refuted (%.120s); arbitrating", issue)
    correction = verifier_answer
    arbiter_messages = [
        {"role": "system", "content": ARBITER_PROMPT},
        *messages,
        _arbiter_message(draft.answer, correction.answer),
    ]
    arb_tokens: tuple[int, int] | None = None
    try:
        arbiter_raw = await llm.complete(arbiter_messages, json_mode=True)
        arb_tokens = getattr(llm, "last_usage", None)
        winner, reason = _validate_arbitration(extract_json_object(arbiter_raw))
    except LLMError as exc:
        # The skeptic found a concrete error; trusting the refutation is safer
        # than trusting an arbitration that could not run.
        logger.warning("arbitration failed (%s); shipping the correction", exc)
        correction.uncertainty_factors = [
            *correction.uncertainty_factors,
            f"Initial draft was refuted during verification: {issue}"[:200],
        ]
        return VerificationResult(
            answer=correction, verdict="corrected",
            detail=f"draft was wrong: {issue}"[:200],
            token_usage=_combine(draft_tokens, verify_tokens),
        )

    if winner == "A":
        final, detail = draft, "draft survived arbitration"
    else:
        final = correction
        final.uncertainty_factors = [
            *correction.uncertainty_factors,
            "An independent verification pass corrected the initial answer",
        ]
        detail = f"verification changed the answer: {reason or issue}"
    return VerificationResult(
        answer=final,
        verdict="corrected",
        detail=(f"{detail}" + (f" ({reason})" if reason and winner == "B" else ""))[:220],
        token_usage=_combine(draft_tokens, verify_tokens, arb_tokens),
    )
