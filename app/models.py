"""ORM models for logged chat interactions and versioned system prompts."""
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Float, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class Interaction(Base):
    """One user message + structured assistant answer, fully logged."""

    __tablename__ = "interactions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    conversation_id: Mapped[str] = mapped_column(String(64), index=True)
    user_message: Mapped[str] = mapped_column(Text)
    assistant_answer: Mapped[str] = mapped_column(Text)
    confidence: Mapped[float] = mapped_column(Float)
    confidence_reason: Mapped[str] = mapped_column(Text)
    uncertainty_factors: Mapped[str] = mapped_column(Text, default="[]")  # JSON list
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, index=True)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    prompt_version: Mapped[str] = mapped_column(String(32), default="v1", index=True)
    # JSON list of {filename, mime_type, size_bytes, kind}; "[]" when none.
    attachments: Mapped[str] = mapped_column(Text, default="[]")
    # Optional full derivation for problem-solving turns ("See detailed solution").
    detailed_solution: Mapped[str | None] = mapped_column(Text, nullable=True)


class ChatSession(Base):
    """A named conversation. Created lazily on the first message; renamable."""

    __tablename__ = "chat_sessions"

    conversation_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(80), default="New chat")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, index=True
    )


class PromptVersion(Base):
    """Versioned system prompts so different versions can be compared later."""

    __tablename__ = "prompt_versions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    version: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    system_prompt: Mapped[str] = mapped_column(Text)
    parent_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    created_by: Mapped[str] = mapped_column(String(32), default="system")  # "seed" | "improve"
    is_active: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
