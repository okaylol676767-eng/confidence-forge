"""Self-improvement flow: analyze low-confidence answers, generate + store a new prompt version."""
import json
import re

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from .config import get_logger, get_settings
from .errors import DatabaseError, InvalidRequestError, LLMBadResponseError
from .llm_factory import build_llm_client
from .models import Interaction, PromptVersion
from .prompts import prompt_manager, validate_version_tag  # noqa: F401
from .services import parse_factors
from .schemas import ImproveResponse, PromptVersionOut

logger = get_logger("improve")
settings = get_settings()

llm_client = build_llm_client()

MAX_EXAMPLES_IN_PROMPT = 15


def _truncate(text: str | None, limit: int = 300) -> str:
    return (text or "")[:limit]


def build_examples(sample: list[Interaction]) -> list[dict]:
    return [
        {
            "user": _truncate(row.user_message),
            "answer": _truncate(row.assistant_answer),
            "confidence": row.confidence,
            "reason": _truncate(row.confidence_reason, 200),
            "factors": parse_factors(row.uncertainty_factors)[:3],
        }
        for row in sample
    ]


def build_improve_messages(current_prompt: str, sample: list[Interaction]) -> list[dict[str, str]]:
    """Prompt for the LLM that rewrites the system prompt."""
    examples = build_examples(sample)[:MAX_EXAMPLES_IN_PROMPT]
    instruction = (
        "You are an expert prompt engineer. Below is the current system prompt and a sample "
        "of low-confidence answers (confidence < threshold) it produced. Identify the recurring "
        "failure patterns (e.g. missing info requested, vague answers, wrong assumptions) and "
        "rewrite the system prompt to fix them. Keep the exact same JSON output contract "
        "(answer, confidence, confidence_reason, uncertainty_factors). "
        "Output ONLY the new system prompt as plain text, no commentary, no code fences."
    )
    body = (
        f"CURRENT PROMPT:\n{current_prompt}\n\n"
        f"LOW-CONFIDENCE SAMPLE ({len(examples)} of {len(sample)} items):\n"
        f"{json.dumps(examples, indent=2)}"
    )
    return [
        {"role": "system", "content": "You are an expert prompt engineer."},
        {"role": "user", "content": f"{instruction}\n\n{body}"},
    ]


async def next_version_number(session: AsyncSession) -> str:
    """v1 -> v2 -> v3 ... based on the highest existing numeric version."""
    rows = (await session.execute(select(PromptVersion.version))).scalars().all()
    numbers = []
    for version in rows:
        match = re.fullmatch(r"v(\d+)", version)
        if match:
            numbers.append(int(match.group(1)))
    return f"v{max(numbers) + 1}" if numbers else "v1"


async def analyze_low_confidence(session: AsyncSession) -> list[Interaction]:
    try:
        result = await session.execute(
            select(Interaction)
            .where(Interaction.confidence < settings.low_confidence_threshold)
            .order_by(Interaction.created_at.desc())
            .limit(settings.improve_sample_limit)
        )
        return list(result.scalars().all())
    except SQLAlchemyError:
        logger.exception("DB error while fetching low-confidence interactions")
        raise DatabaseError("Failed to fetch low-confidence interactions.") from None


async def improve_prompt_flow(session: AsyncSession, activate: bool = True) -> ImproveResponse:
    """The /improve endpoint logic: sample -> LLM rewrite -> save new version."""
    sample = await analyze_low_confidence(session)
    if not sample:
        raise InvalidRequestError(
            "No low-confidence interactions found below threshold "
            f"{settings.low_confidence_threshold}; nothing to improve yet."
        )

    current_version, current_prompt = await prompt_manager.get_active()
    new_prompt_text = await llm_client.complete(build_improve_messages(current_prompt, sample))

    cleaned = new_prompt_text.strip()
    if len(cleaned) < 50:
        logger.error("Improved prompt too short (%d chars); refusing to save", len(cleaned))
        raise LLMBadResponseError("The LLM returned an implausibly short prompt.")

    next_version = await next_version_number(session)
    try:
        saved = await prompt_manager.save(
            version=next_version,
            system_prompt=cleaned,
            created_by="improve",
            parent_version=current_version,
            activate=activate,
        )
    except ValueError as exc:
        raise InvalidRequestError(str(exc)) from None
    except SQLAlchemyError:
        logger.exception("DB error while saving improved prompt version %s", next_version)
        raise DatabaseError("Failed to save the improved prompt.") from None

    avg_conf = sum(row.confidence for row in sample) / len(sample)
    logger.info(
        "improve: analyzed=%d avg_conf=%.3f new_version=%s active=%s",
        len(sample), avg_conf, next_version, activate,
    )
    return ImproveResponse(
        new_version=PromptVersionOut.model_validate(saved, from_attributes=True),
        analyzed_interactions=len(sample),
        average_confidence_of_sample=round(avg_conf, 4),
        rationale=(
            f"Rewrote {current_version} using {len(sample)} low-confidence "
            "interactions; new version fixes recurring failure patterns while keeping the JSON contract."
        ),
    )
