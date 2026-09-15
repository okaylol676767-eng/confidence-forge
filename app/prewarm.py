"""Startup pre-warm: fill the answer cache with common questions.

After the app boots, a background task answers a short list of frequently
asked questions once through the real model and stores the results in the
answer cache. The first real user asking one of them then gets the
single-digit-millisecond cached answer instead of a cold multi-second
model call. This is honest speed: the answer was genuinely produced by
the model, and its token usage is replayed on every cache hit.

Fully optional: disable with PREWARM_ENABLED=false. Failures are logged
and swallowed — a failed warmup must never block startup.
"""
import asyncio

from .answer_cache import answer_cache, cacheable_turn
from .config import get_logger, get_settings

logger = get_logger("prewarm")
settings = get_settings()

# Frequently asked starter questions. Keep in sync with the UI's
# suggestion chips where possible. Order = priority (bounded runtime).
DEFAULT_WARM_QUESTIONS: tuple[str, ...] = (
    "What is 7 x 8?",
    "What is 12 x 11?",
    "What is 15% of 240?",
    "State Newton's second law of motion",
    "State Newton's three laws of motion",
    "State Ohm's law",
    "What is the boiling point of water in Fahrenheit?",
    "State the law of conservation of energy",
    "What is Avogadro's number?",
    "Define photosynthesis in one sentence",
    "What is the derivative of x squared?",
    "Solve for x: 2x + 6 = 14",
    "What is the speed of light?",
    "What is the molecular formula of water?",
    "What is the quadratic formula?",
    "Convert 100 degrees Celsius to Fahrenheit",
    "What is the value of pi?",
    "State the first law of thermodynamics",
    "What is Hooke's law?",
    "What is the power law of exponents?",
    # JEE Mains/Advanced starters — high-frequency exam asks, so the first
    # real ask of each is cache-fast.
    "State Newton's first law of motion",
    "State Coulomb's law",
    "State Faraday's law of electromagnetic induction",
    "State Lenz's law",
    "State Kirchhoff's laws",
    "What is dimensional formula of Planck's constant?",
    "State the second law of thermodynamics",
    "State Hess's law of constant heat summation",
    "State Le Chatelier's principle",
    "What is Markovnikov's rule?",
    "State Raoult's law",
    "What is the ideal gas equation?",
    "State Bohr's postulates for the hydrogen atom",
    "What is the de Broglie wavelength formula?",
    "State the mirror formula",
    "What is the lens maker's formula?",
    "State Ampere's circuital law",
    "State the work-energy theorem",
    "State Bernoulli's theorem",
    "What is the formula for time period of a simple pendulum?",
    "What is the derivative of sin x?",
    "What is the integral of 1/x?",
    "What is the formula for the sum of an infinite geometric series?",
    "State the binomial theorem",
    "What is the distance formula between two points?",
    "State De Morgan's laws",
    "What is the standard deviation formula?",
    "State the fundamental theorem of calculus",
    "What is the cross product of two parallel vectors?",
    "What is the value of sin 30 degrees?",
)


async def prewarm_cache(llm, prompt_version: str, system_prompt: str) -> int:
    """Answer the warm list once each and cache the results. Returns count."""
    if answer_cache is None:
        return 0
    from .services import build_chat_messages
    from .self_improve import (
        fingerprint_lessons,
        get_active_lessons,
        select_lessons,
    )
    from .database import SessionFactory

    # Chat keys include the fingerprint of the lessons selected for the
    # question; prewarm must build the IDENTICAL key or its entries are
    # never hit. Same lesson set + same question => same selection.
    try:
        async with SessionFactory() as session:
            active_lessons = await get_active_lessons(session)
    except Exception:
        active_lessons = []

    warmed = 0
    for question in DEFAULT_WARM_QUESTIONS:
        if not cacheable_turn(message=question, history_count=0, attachment_count=0):
            continue
        key = answer_cache.make_key(
            prompt_version + "::" + fingerprint_lessons(select_lessons(active_lessons, question)),
            question,
        )
        if answer_cache.get(key) is not None:
            continue  # already warm (e.g. restart within TTL)
        try:
            messages = build_chat_messages(system_prompt, [], question)
            structured = await llm.chat_structured(messages)
            answer_cache.put(
                key, structured, prompt_version, getattr(llm, "last_usage", None)
            )
            warmed += 1
        except Exception as exc:
            # One bad question must not abort the rest of the warmup.
            logger.warning("prewarm failed for %r: %s", question, exc)
    logger.info("prewarm completed: %d/%d questions cached", warmed, len(DEFAULT_WARM_QUESTIONS))
    return warmed


def start_prewarm(llm, prompt_version: str, system_prompt: str) -> asyncio.Task | None:
    """Fire-and-forget background warmup; returns the Task (or None if disabled)."""
    if not settings.prewarm_enabled or answer_cache is None:
        logger.info("prewarm disabled")
        return None
    task = asyncio.create_task(
        prewarm_cache(llm, prompt_version, system_prompt),
        name="answer-cache-prewarm",
    )
    return task
