"""Self-consistency voting for quantitative questions.

For STEM-style questions the model is sampled N times in parallel; the
majority-voted answer wins, and the vote agreement becomes the reported
confidence — so the transparency contract stays honest (low agreement ->
low confidence, exactly what the UI promises).
"""
import asyncio
import re
from collections import Counter
from dataclasses import dataclass, field

from .config import get_logger, get_settings
from .errors import LLMError
from .schemas import StructuredAnswer

logger = get_logger("consistency")
settings = get_settings()

# QUESTION_SIGNALS: heuristics that mark a message as quantitative/STEM.
QUESTION_SIGNALS = re.compile(
    r"(?is)\b("
    r"solve|calculate|compute|evaluate|derive|prove|show\s+that|"
    r"find\s+\S+|how\s+(fast|much|many|long|far|deep|high)|"
    r"integral|integrat|derivative|differentiate|equation|matrix|vector|probability|limit|sum\b|"
    r"velocity|accelerat|force|energy|momentum|moment|tension|friction|projectile|"
    r"wave|frequency|wavelength|current|voltage|resistance|circuit|charge|magnetic|"
    r"mol(?:e|ar|arity)?\b|concentration|pH\b|stoichi|reaction|titration|enthalpy|entropy|"
    r"oxidation|reduction|mole\b|grams?\b|litres?|liters?|pressure|volume|temperature|"
    r"balance.{0,20}(equation)|half[- ]life|kinetics|equilibrium|"
    r"area|perimeter|circumference|radius|diameter|hypotenuse|angle|slope|"
    r"distance|speed|mass|weight|density|percent(?:age)?|ratio|average|mean\b|median"
    r")"
)

_FINAL_RE = re.compile(
    r"^(?:final answer|final result|answer|result)\s*[:\-]\s*(.+?)$", re.IGNORECASE
)
_NUM_TOKEN_RE = re.compile(r"-?\d[\d,]*(?:\.\d+)?")


def looks_quantitative(message: str) -> bool:
    """Heuristic: should this question get the multi-sample consistency treatment?"""
    return bool(QUESTION_SIGNALS.search(message or ""))


def extract_final_answer(text: str) -> str:
    """Pull the final-result line the v2 prompt demands.

    Accepts marker variants (**Final answer:**, **Answer**: , 'result: ...')
    in the last few lines; falls back to the last non-empty line, since models
    in practice end with the conclusion.
    """
    lines = [line.strip() for line in (text or "").splitlines() if line.strip()]
    for line in reversed(lines[-3:]):
        # Bold markers sit inconsistently ('**Final answer:**' vs '**Answer**:')
        # so strip them, then match one anchored label pattern.
        cleaned = line.replace("*", "").strip()
        match = _FINAL_RE.search(cleaned)
        if match:
            return match.group(1).strip().rstrip(".").strip()
    return lines[-1] if lines else ""


def _normalize(answer: str) -> str:
    """Canonical form for vote comparison: lowercase, minimal punctuation/spacing."""
    value = answer.lower().strip()
    value = re.sub(r"[\s]+", " ", value)
    value = value.replace("\\left", "").replace("\\right", "")
    value = re.sub(r"\\(mathrm|text)\{([^}]*)\}", r"\2", value)
    value = value.replace("\\ ", " ")  # LaTeX explicit space
    value = value.replace("$", "")
    value = value.replace("*", "")  # bold markers
    value = value.replace("\\approx", "=").replace("≈", "=")
    value = re.sub(r"[\s]*([=+\-*/^<>])[\s]*", r"\1", value)
    value = re.sub(r"[.,;:!]+$", "", value)
    value = re.sub(r"^[-•·]\s*", "", value)  # bullet prefix
    value = re.sub(r"^(?:final answer|final result|answer|result|thus|therefore|so|hence)[:\-]?\s*", "", value)
    return re.sub(r"\s+", "", value)  # '22 g' and '22g' are the same vote


def _last_number(text: str) -> float | None:
    """The last numeric token in the FINAL line of an answer, float-normalized.

    '1.710', '1.71', and '$x \\approx 1.710$' all become the same vote key.
    Returns None for non-numeric answers. Must be fed the extracted final
    line only — scanning whole answers picks up boilerplate numbers.
    """
    matches = _NUM_TOKEN_RE.findall((text or "").replace(",", ""))
    if not matches:
        return None
    try:
        return float(matches[-1])
    except ValueError:
        return None


@dataclass
class VoteResult:
    """Outcome of one consistency vote."""

    winner: StructuredAnswer
    samples: int
    agreement: float  # 0..1, fraction of successful samples backing the winner
    top_answers: list[tuple[str, int]] = field(default_factory=list)
    # (input_tokens, output_tokens) summed across the successful samples,
    # for observability. None when the client does not report usage.
    token_usage: tuple[int, int] | None = None


def pick_winner(samples: list[StructuredAnswer]) -> VoteResult:
    """Majority-vote over normalized final answers; ties -> first sample.

    Samples without a parseable final line vote for their raw answer tail.
    """
    valid = [s for s in samples if s.answer.strip()]
    if not valid:
        raise LLMError("All consistency samples were empty.")

    votes: list[str] = []
    by_norm: dict[str, StructuredAnswer] = {}
    for sample in valid:
        # Quantitative answers vote on the result NUMBER (float-normalized),
        # which survives phrasing/formatting variance between samples. The
        # number comes from the extracted final line, never the whole body.
        final = extract_final_answer(sample.answer) or sample.answer.strip()
        number = _last_number(final)
        if number is not None:
            norm = f"#{number:.6g}"
        else:
            norm = _normalize(final)
        votes.append(norm)
        by_norm.setdefault(norm, sample)

    counts = Counter(votes)
    top_norm, _ = counts.most_common(1)[0]
    winner_sample = by_norm[top_norm]
    agreement = counts[top_norm] / len(valid)

    confidence = round(winner_sample.confidence * agreement, 4)
    # Surface disagreement explicitly instead of hiding it.
    factors = list(winner_sample.uncertainty_factors)
    if agreement < 1.0:
        factors.append(
            f"Independent samples agreed on this answer in only {counts[top_norm]} of {len(valid)} attempts"
        )
    runner_up = [
        (norm, n) for norm, n in counts.most_common(3) if norm != top_norm
    ]

    return VoteResult(
        winner=StructuredAnswer(
            answer=winner_sample.answer,
            confidence=confidence,
            confidence_reason=(
                f"Majority vote: {counts[top_norm]}/{len(valid)} independent solutions agreed."
                if agreement < 1.0
                else f"All {len(valid)} independent solutions agreed."
            ),
            uncertainty_factors=factors,
            detailed_solution=winner_sample.detailed_solution,
        ),
        samples=len(valid),
        agreement=agreement,
        top_answers=runner_up,
    )


async def consistency_solve(
    llm,
    messages: list[dict[str, str]],
    attachments=None,
) -> VoteResult:
    """Sample the model N times concurrently and vote. Falls back to fewer
    samples on individual sample failure; raises only if all samples fail."""
    sample_count = max(1, settings.consistency_samples)
    budget = settings.consistency_timeout_seconds

    # Deterministic temp-0 calls answer near-identically every time, which
    # would make voting meaningless — samples run warmer instead. JSON mode
    # stays as configured (Gemini allows temperature with response_mime_type).
    sample_temperature = 0.7

    usage_total = [0, 0]

    async def one() -> StructuredAnswer:
        try:
            result = await llm.chat_structured(
                messages, attachments=attachments, temperature=sample_temperature
            )
        except TypeError:
            # Client without temperature support (test doubles).
            result = await llm.chat_structured(messages, attachments=attachments)
        usage = getattr(llm, "last_usage", None)
        if usage:
            usage_total[0] += int(usage[0])
            usage_total[1] += int(usage[1])
        return result

    tasks = [asyncio.create_task(one()) for _ in range(sample_count)]
    done, pending = await asyncio.wait(tasks, timeout=budget)

    for task in pending:
        task.cancel()

    samples: list[StructuredAnswer] = []
    errors: list[BaseException] = []
    for task in done:
        exc = task.exception() if not task.cancelled() else None
        if exc is not None:
            errors.append(exc)
        else:
            samples.append(task.result())

    if not samples:
        if errors:
            raise errors[0]
        raise LLMError(
            "The model did not answer in time. Please retry.",
        )

    logger.info(
        "consistency samples=%d ok=%d failed=%d", sample_count, len(samples), len(errors)
    )
    result = pick_winner(samples)
    if usage_total[0] or usage_total[1]:
        result.token_usage = (usage_total[0], usage_total[1])
    return result
