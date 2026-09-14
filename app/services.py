"""Business logic for chat, history, and stats.

All DB work happens here with try/except around DB operations, translating
failures into the standard error envelope (AppError subclasses).
"""
import json
import time
import uuid

from sqlalchemy import case, func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from .config import get_logger, get_settings
from .database import get_session  # noqa: F401  (re-exported for routers)
from .errors import DatabaseError
from .llm import LLMClient, llm_client
from .models import Interaction
from .prompts import PromptManager, prompt_manager
from .schemas import (
    ChatRequest,
    ChatResponse,
    ConversationHistoryResponse,
    ConversationMessage,
    StatsSummaryResponse,
    StructuredAnswer,
)

logger = get_logger("service")
settings = get_settings()

llm: LLMClient = llm_client
prompts: PromptManager = prompt_manager

LOW_CONFIDENCE_THRESHOLD = settings.low_confidence_threshold
MAX_HISTORY_TURNS = settings.max_history_turns


def new_conversation_id() -> str:
    """Short, URL-safe conversation id."""
    return f"c-{uuid.uuid4().hex[:12]}"


def parse_factors(raw: str | None) -> list[str]:
    try:
        value = json.loads(raw or "[]")
        return [str(x) for x in value] if isinstance(value, list) else []
    except (json.JSONDecodeError, TypeError):
        return []


def build_chat_messages(
    system_prompt: str,
    history: list[Interaction],
    user_message: str,
) -> list[dict[str, str]]:
    """System prompt + last N exchanges + the new user message."""
    messages: list[dict[str, str]] = [{"role": "system", "content": system_prompt}]
    for row in history[-MAX_HISTORY_TURNS:]:
        messages.append({"role": "user", "content": row.user_message})
        messages.append({"role": "assistant", "content": row.assistant_answer})
    messages.append({"role": "user", "content": user_message})
    return messages


async def handle_chat(session: AsyncSession, request: ChatRequest) -> ChatResponse:
    """Full chat flow: history -> LLM (forced JSON) -> validate -> log -> respond."""
    started = time.perf_counter()
    conversation_id = request.conversation_id or new_conversation_id()

    try:
        history = await fetch_recent_history(session, conversation_id)
    except DatabaseError:
        raise
    prompt_version, system_prompt = await prompts.get_active()

    messages = build_chat_messages(system_prompt, history, request.message)
    structured = await llm.chat_structured(messages)  # typed LLMError on failure

    latency_ms = int((time.perf_counter() - started) * 1000)

    row = await save_interaction(session, conversation_id, request, structured, latency_ms, prompt_version)

    logger.info(
        "chat conversation=%s latency_ms=%d confidence=%.2f version=%s factors=%d",
        conversation_id, latency_ms, structured.confidence, prompt_version,
        len(structured.uncertainty_factors),
    )
    return ChatResponse(
        conversation_id=conversation_id,
        interaction_id=row.id,
        prompt_version=prompt_version,
        latency_ms=latency_ms,
        **structured.model_dump(),
    )


async def fetch_recent_history(session: AsyncSession, conversation_id: str) -> list[Interaction]:
    try:
        result = await session.execute(
            select(Interaction)
            .where(Interaction.conversation_id == conversation_id)
            .order_by(Interaction.id.desc())
            .limit(MAX_HISTORY_TURNS)
        )
        return list(reversed(result.scalars().all()))
    except SQLAlchemyError:
        logger.exception("DB error while fetching recent history (conversation=%s)", conversation_id)
        raise DatabaseError("Failed to load the conversation history.") from None


async def save_interaction(
    session: AsyncSession,
    conversation_id: str,
    request: ChatRequest,
    structured: StructuredAnswer,
    latency_ms: int,
    prompt_version: str,
) -> Interaction:
    try:
        row = Interaction(
            conversation_id=conversation_id,
            user_message=request.message,
            assistant_answer=structured.answer,
            confidence=structured.confidence,
            confidence_reason=structured.confidence_reason,
            uncertainty_factors=json.dumps(structured.uncertainty_factors),
            latency_ms=latency_ms,
            prompt_version=prompt_version,
        )
        session.add(row)
        await session.commit()
        await session.refresh(row)
        return row
    except SQLAlchemyError:
        await session.rollback()
        logger.exception("DB error while logging interaction (conversation=%s)", conversation_id)
        raise DatabaseError("Failed to save the chat interaction.") from None


def _user_message_from(row: Interaction) -> ConversationMessage:
    return ConversationMessage(
        id=row.id,
        role="user",
        content=row.user_message,
        created_at=row.created_at,
        prompt_version=row.prompt_version,
        latency_ms=row.latency_ms,
    )


def _assistant_message_from(row: Interaction) -> ConversationMessage:
    return ConversationMessage(
        id=row.id,
        role="assistant",
        content=row.assistant_answer,
        confidence=row.confidence,
        confidence_reason=row.confidence_reason,
        uncertainty_factors=parse_factors(row.uncertainty_factors),
        created_at=row.created_at,
        prompt_version=row.prompt_version,
        latency_ms=row.latency_ms,
    )


async def get_conversation_history(
    session: AsyncSession, conversation_id: str, limit: int = 200
) -> ConversationHistoryResponse:
    try:
        result = await session.execute(
            select(Interaction)
            .where(Interaction.conversation_id == conversation_id)
            .order_by(Interaction.id.asc())
            .limit(limit)
        )
        rows = list(result.scalars().all())
    except SQLAlchemyError:
        logger.exception("DB error while fetching history (conversation=%s)", conversation_id)
        raise DatabaseError("Failed to load the conversation history.") from None

    messages: list[ConversationMessage] = []
    for row in rows:
        messages.append(_user_message_from(row))
        messages.append(_assistant_message_from(row))
    return ConversationHistoryResponse(
        conversation_id=conversation_id,
        message_count=len(messages),
        messages=messages,
    )


async def get_stats_summary(session: AsyncSession) -> StatsSummaryResponse:
    try:
        total = await session.scalar(select(func.count()).select_from(Interaction)) or 0
        avg_conf = await session.scalar(select(func.avg(Interaction.confidence)))
        avg_latency = await session.scalar(select(func.avg(Interaction.latency_ms)))
        low_count = await session.scalar(
            select(func.count()).select_from(Interaction)
            .where(Interaction.confidence < LOW_CONFIDENCE_THRESHOLD)
        ) or 0
        conversations = await session.scalar(
            select(func.count(func.distinct(Interaction.conversation_id)))
        ) or 0

        version_rows = await session.execute(
            select(
                Interaction.prompt_version,
                func.count().label("n"),
                func.avg(Interaction.confidence).label("avg_conf"),
                func.avg(Interaction.latency_ms).label("avg_latency"),
                func.sum(case((Interaction.confidence < LOW_CONFIDENCE_THRESHOLD, 1), else_=0)).label("low"),
            ).group_by(Interaction.prompt_version)
        )
        by_version = {
            row.prompt_version: {
                "count": int(row.n or 0),
                "average_confidence": round(float(row.avg_conf), 4) if row.avg_conf is not None else None,
                "low_confidence_count": int(row.low or 0),
                "average_latency_ms": round(float(row.avg_latency), 1) if row.avg_latency is not None else None,
            }
            for row in version_rows
        }
        return StatsSummaryResponse(
            total_interactions=int(total),
            average_confidence=round(float(avg_conf), 4) if avg_conf is not None else None,
            low_confidence_count=int(low_count),
            low_confidence_threshold=LOW_CONFIDENCE_THRESHOLD,
            average_latency_ms=round(float(avg_latency), 1) if avg_latency is not None else None,
            conversations=int(conversations),
            by_prompt_version=by_version,
        )
    except SQLAlchemyError:
        logger.exception("DB error while computing stats summary")
        raise DatabaseError("Failed to compute stats.") from None
