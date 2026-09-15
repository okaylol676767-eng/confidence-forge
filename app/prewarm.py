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
)


async def prewarm_cache(llm, prompt_version: str, system_prompt: str) -> int:
    """Answer the warm list once each and cache the results. Returns count."""
    if answer_cache is None:
        return 0
    from .services import build_chat_messages

    warmed = 0
    for question in DEFAULT_WARM_QUESTIONS:
        if not cacheable_turn(message=question, history_count=0, attachment_count=0):
            continue
        key = answer_cache.make_key(prompt_version, question)
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
