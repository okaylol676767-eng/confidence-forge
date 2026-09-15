"""Pydantic schemas: request validation + consistent response/error shapes."""
from datetime import datetime

from pydantic import BaseModel, Field, field_validator


# ---------- Errors (the one true error envelope) ----------

class ErrorEnvelope(BaseModel):
    error: bool = True
    message: str
    code: str


# ---------- Chat ----------

class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=8_000, examples=["What is the capital of France?"])
    conversation_id: str | None = Field(
        default=None, max_length=64,
        examples=["c-7f3a2b"],
        description="Optional; a new one is generated when omitted.",
    )
    self_verified: bool = Field(
        default=True,
        description="Run the independent verification pass on the answer (when enabled server-side).",
    )

    @field_validator("message")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("message must not be empty or whitespace-only")
        return value.strip()

    @field_validator("conversation_id")
    @classmethod
    def _clean_conversation_id(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            return None
        if len(value) > 64 or any(ch in value for ch in " \t\r\n"):
            raise ValueError("conversation_id must be <= 64 chars without whitespace")
        return value


class StructuredAnswer(BaseModel):
    """The strict JSON contract we force the LLM into."""

    answer: str
    confidence: float = Field(..., ge=0.0, le=1.0)
    confidence_reason: str
    uncertainty_factors: list[str] = Field(default_factory=list)
    # Optional full derivation. The model supplies it for problem-solving
    # turns; the short ``answer`` stays what the bubble shows first.
    detailed_solution: str | None = None


class AttachmentMeta(BaseModel):
    """Metadata about one file attached to a chat turn (content never stored)."""

    filename: str
    mime_type: str
    size_bytes: int
    kind: str  # "image" | "document"


class VerificationInfo(BaseModel):
    """Transparent record of the independent verification pass."""

    verdict: str  # "confirmed" | "corrected" | "unavailable"
    detail: str


class ChatResponse(BaseModel):
    conversation_id: str
    interaction_id: int
    prompt_version: str
    latency_ms: int
    answer: str
    confidence: float
    confidence_reason: str
    uncertainty_factors: list[str]
    detailed_solution: str | None = None
    verification: VerificationInfo | None = None
    attachments: list[AttachmentMeta] = Field(default_factory=list)


# ---------- Conversation history ----------

class ConversationMessage(BaseModel):
    id: int
    role: str  # "user" | "assistant"
    content: str
    confidence: float | None = None
    confidence_reason: str | None = None
    uncertainty_factors: list[str] | None = None
    detailed_solution: str | None = None
    created_at: datetime
    prompt_version: str
    latency_ms: int
    attachments: list[AttachmentMeta] | None = None


class ConversationHistoryResponse(BaseModel):
    conversation_id: str
    message_count: int
    messages: list[ConversationMessage]


# ---------- Sessions (named conversations) ----------

class SessionOut(BaseModel):
    conversation_id: str
    name: str
    message_count: int
    created_at: datetime
    updated_at: datetime


class SessionRenameRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=80)

    @field_validator("name")
    @classmethod
    def _clean_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("name must not be empty or whitespace-only")
        return value


# ---------- Stats ----------

class StatsSummaryResponse(BaseModel):
    total_interactions: int
    average_confidence: float | None = None
    low_confidence_count: int = Field(..., description="Answers with confidence below the threshold")
    low_confidence_threshold: float
    average_latency_ms: float | None = None
    conversations: int
    by_prompt_version: dict[str, dict[str, float | int | None]]


# ---------- Prompt improvement ----------

class ImproveRequest(BaseModel):
    activate: bool = Field(
        default=True,
        description="Make the newly generated version the active prompt.",
    )


class PromptVersionOut(BaseModel):
    id: int
    version: str
    parent_version: str | None
    created_by: str
    is_active: bool
    created_at: datetime
    system_prompt: str


class ImproveResponse(BaseModel):
    new_version: PromptVersionOut
    analyzed_interactions: int
    average_confidence_of_sample: float | None
    rationale: str
