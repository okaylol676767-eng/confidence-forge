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

from .attachments import Attachment
from .config import get_logger, get_settings
from .consistency import consistency_solve, looks_quantitative
from .database import get_session  # noqa: F401  (re-exported for routers)
from .errors import DatabaseError, NotFoundError
from .llm_factory import build_llm_client
from .models import ChatSession, Interaction
from .prompts import PromptManager, prompt_manager
from .schemas import (
    AttachmentMeta,
    ChatRequest,
    ChatResponse,
    ConversationHistoryResponse,
    ConversationMessage,
    SessionOut,
    StatsSummaryResponse,
    StructuredAnswer,
)
from .tracing import trace_chat_turn
from .answer_cache import answer_cache, cacheable_turn
from .consistency import is_trivial_arithmetic

logger = get_logger("service")
settings = get_settings()

llm = build_llm_client()  # OpenAI-compatible or Gemini, per LLM_PROVIDER
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


async def handle_chat(
    session: AsyncSession,
    request: ChatRequest,
    attachments: list[Attachment] | None = None,
) -> ChatResponse:
    """Full chat flow: history -> LLM (forced JSON) -> validate -> log -> respond."""
    started = time.perf_counter()
    attachments = attachments or []
    conversation_id = request.conversation_id or new_conversation_id()

    try:
        history = await fetch_recent_history(session, conversation_id)
    except DatabaseError:
        raise
    prompt_version, system_prompt = await prompts.get_active()

    # Exact-match answer cache: only context-free turns (no history, no files)
    # may be served or stored, so a hit can never produce a wrong answer.
    cache_key = None
    if (
        answer_cache is not None
        and cacheable_turn(
            message=request.message,
            history_count=len(history),
            attachment_count=len(attachments),
        )
    ):
        cache_key = answer_cache.make_key(prompt_version, request.message)
        cached = answer_cache.get(cache_key)
        if cached is not None:
            cached_answer, cached_tokens = cached
            latency_ms = int((time.perf_counter() - started) * 1000)
            row = await save_interaction(
                session, conversation_id, request, cached_answer, latency_ms, prompt_version, attachments,
            )
            trace_chat_turn(
                model=settings.llm_model_for_provider,
                input_messages=[m for m in ([{"role": "user", "content": request.message}])],
                answer=cached_answer.answer,
                latency_ms=latency_ms,
                token_usage=cached_tokens,
                conversation_id=conversation_id,
                interaction_id=str(row.id),
                confidence=cached_answer.confidence,
                prompt_version=prompt_version,
                uncertainty_factors=cached_answer.uncertainty_factors,
                attachment_count=0,
            )
            logger.info(
                "chat conversation=%s latency_ms=%d confidence=%.2f version=%s CACHED",
                conversation_id, latency_ms, cached_answer.confidence, prompt_version,
            )
            return ChatResponse(
                conversation_id=conversation_id,
                interaction_id=row.id,
                prompt_version=prompt_version,
                latency_ms=latency_ms,
                attachments=attachment_meta(attachments),
                **cached_answer.model_dump(),
            )

    messages = build_chat_messages(system_prompt, history, request.message)

    # Quantitative questions get self-consistency: N independent solutions +
    # majority vote, with agreement folded into the reported confidence.
    # Trivial one-shot arithmetic skips the vote: a single computation the
    # model cannot meaningfully disagree with itself on (3x latency for 0 info).
    if (
        settings.consistency_samples > 1
        and looks_quantitative(request.message)
        and not is_trivial_arithmetic(request.message)
    ):
        vote = await consistency_solve(llm, messages, attachments=attachments)
        structured = vote.winner
        token_usage: tuple[int, int] | None = vote.token_usage
    else:
        structured = await llm.chat_structured(messages, attachments=attachments)  # typed LLMError
        token_usage = getattr(llm, "last_usage", None)

    latency_ms = int((time.perf_counter() - started) * 1000)

    row = await save_interaction(
        session, conversation_id, request, structured, latency_ms, prompt_version, attachments
    )

    # PRISM live tracing: one record per chat turn (fire-and-forget, fail-open).
    # The system prompt is deliberately NOT included: it is proprietary, and
    # PRISM's content scanner was flagging every trace that carried it as
    # "Blocked" (instruction-like text trips injection/DLP rules). Prompt
    # identity still reaches PRISM via the prompt_version metadata field.
    trace_chat_turn(
        model=settings.llm_model_for_provider,
        input_messages=[m for m in messages if m["role"] != "system"],
        answer=structured.answer,
        latency_ms=latency_ms,
        token_usage=token_usage,
        conversation_id=conversation_id,
        interaction_id=str(row.id),
        confidence=structured.confidence,
        prompt_version=prompt_version,
        uncertainty_factors=structured.uncertainty_factors,
        attachment_count=len(attachments),
    )

    logger.info(
        "chat conversation=%s latency_ms=%d confidence=%.2f version=%s factors=%d",
        conversation_id, latency_ms, structured.confidence, prompt_version,
        len(structured.uncertainty_factors),
    )
    if cache_key is not None and answer_cache is not None:
        answer_cache.put(cache_key, structured, prompt_version, token_usage)
    return ChatResponse(
        conversation_id=conversation_id,
        interaction_id=row.id,
        prompt_version=prompt_version,
        latency_ms=latency_ms,
        attachments=attachment_meta(attachments),
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


def attachment_meta(attachments: list[Attachment]) -> list[AttachmentMeta]:
    """Public metadata for a validated attachment batch."""
    return [
        AttachmentMeta(
            filename=a.filename,
            mime_type=a.mime_type,
            size_bytes=len(a.data),
            kind="image" if a.is_image else "document",
        )
        for a in attachments
    ]


async def save_interaction(
    session: AsyncSession,
    conversation_id: str,
    request: ChatRequest,
    structured: StructuredAnswer,
    latency_ms: int,
    prompt_version: str,
    attachments: list[Attachment] | None = None,
) -> Interaction:
    attachments = attachments or []
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
            attachments=json.dumps([m.model_dump() for m in attachment_meta(attachments)]),
            detailed_solution=structured.detailed_solution,
        )
        session.add(row)
        await session.commit()
        await session.refresh(row)
        await ensure_session_row(session, conversation_id)
        return row
    except SQLAlchemyError:
        await session.rollback()
        logger.exception("DB error while logging interaction (conversation=%s)", conversation_id)
        raise DatabaseError("Failed to save the chat interaction.") from None


def _attachments_from(row: Interaction) -> list[AttachmentMeta] | None:
    try:
        items = json.loads(row.attachments or "[]")
    except (json.JSONDecodeError, TypeError):
        return None
    if not isinstance(items, list) or not items:
        return None
    try:
        return [AttachmentMeta(**item) for item in items]
    except Exception:
        return None


def _user_message_from(row: Interaction) -> ConversationMessage:
    return ConversationMessage(
        id=row.id,
        role="user",
        content=row.user_message,
        created_at=row.created_at,
        prompt_version=row.prompt_version,
        latency_ms=row.latency_ms,
        attachments=_attachments_from(row),
    )


def _assistant_message_from(row: Interaction) -> ConversationMessage:
    return ConversationMessage(
        id=row.id,
        role="assistant",
        content=row.assistant_answer,
        confidence=row.confidence,
        confidence_reason=row.confidence_reason,
        uncertainty_factors=parse_factors(row.uncertainty_factors),
        detailed_solution=row.detailed_solution,
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


# ---------- Sessions (named conversations) ----------

DEFAULT_SESSION_NAME = "New chat"
# Derive a readable default name from the first question (UI can rename later).
_FIRST_QUESTION_MAX = 60


async def ensure_session_row(session: AsyncSession, conversation_id: str) -> None:
    """Create the session row lazily on a conversation's first message.

    Default name comes from the conversation's first user question, trimmed to
    a readable length — better than "New chat" for the sidebar, and the user
    can always rename via PATCH /sessions/{id}.
    """
    try:
        existing = await session.get(ChatSession, conversation_id)
        if existing is not None:
            return
        first = await session.scalar(
            select(Interaction.user_message)
            .where(Interaction.conversation_id == conversation_id)
            .order_by(Interaction.id.asc())
            .limit(1)
        )
        name = DEFAULT_SESSION_NAME
        if first:
            cleaned = " ".join(first.split())
            name = (
                cleaned[:_FIRST_QUESTION_MAX] + "…"
                if len(cleaned) > _FIRST_QUESTION_MAX
                else cleaned
            )
        session.add(ChatSession(conversation_id=conversation_id, name=name))
        await session.commit()
        logger.info("session created conversation=%s name=%.60s", conversation_id, name)
    except SQLAlchemyError:
        await session.rollback()
        # Session bookkeeping must never break a chat response.
        logger.exception("Failed to ensure session row (conversation=%s)", conversation_id)


async def list_sessions(session: AsyncSession, limit: int = 100) -> list[SessionOut]:
    """Most-recently-active sessions first, with per-session message counts."""
    try:
        rows = (await session.execute(
            select(ChatSession)
            .order_by(ChatSession.updated_at.desc())
            .limit(limit)
        )).scalars().all()
        counts = dict((await session.execute(
            select(
                Interaction.conversation_id,
                func.count().label("n"),
            ).group_by(Interaction.conversation_id)
        )).all())
        return [
            SessionOut(
                conversation_id=row.conversation_id,
                name=row.name,
                message_count=int(counts.get(row.conversation_id, 0)),
                created_at=row.created_at,
                updated_at=row.updated_at,
            )
            for row in rows
        ]
    except SQLAlchemyError:
        logger.exception("DB error while listing sessions")
        raise DatabaseError("Failed to list sessions.") from None


async def rename_session(
    session: AsyncSession, conversation_id: str, name: str
) -> SessionOut:
    """Rename a session; 404 when the conversation doesn't exist."""
    try:
        row = await session.get(ChatSession, conversation_id)
        if row is None:
            raise NotFoundError(f"No session found with id '{conversation_id}'.")
        row.name = name
        await session.commit()
        await session.refresh(row)
        count = await session.scalar(
            select(func.count()).select_from(Interaction)
            .where(Interaction.conversation_id == conversation_id)
        ) or 0
        return SessionOut(
            conversation_id=row.conversation_id,
            name=row.name,
            message_count=int(count),
            created_at=row.created_at,
            updated_at=row.updated_at,
        )
    except SQLAlchemyError:
        await session.rollback()
        logger.exception("DB error while renaming session (conversation=%s)", conversation_id)
        raise DatabaseError("Failed to rename the session.") from None
