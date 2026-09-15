"""PRISM live tracing — every chat turn lands in the PRISM dashboard.

Design rules:
- Fully optional: without PRISMTRACE_API_KEY / PRISMTRACE_PROJECT_ID this
  module is a no-op, so local dev and tests stay hermetic.
- Fail-open: a tracing problem must NEVER break a chat response. Every
  failure path is swallowed and logged server-side.
- Non-blocking: the SDK posts from background threads, so request latency
  is unaffected; pending traces are flushed at app shutdown.

The app's orchestration is custom (no LangChain/LangGraph), so the generic
``trace_llm`` record API is used at the one place every model call funnels
through: ``services.handle_chat``.
"""
import os
from typing import Any

from .config import get_logger

logger = get_logger("tracing")

# Stable agent identity for PRISM guardrails/alerts (mint once, never change).
AGENT_ID = "spiral-chat"
AGENT_NAME = "SPIRAL"

_DEFAULT_HOST = "https://prism-api-prod.up.railway.app"

# Cached client + init guard. ``None`` with _init_attempted=True means
# "tracing disabled" — probed once per process, never re-attempted.
_client_instance: Any = None
_init_attempted: bool = False


def _get_client() -> Any:
    """Lazily build the PRISMtrace client; None when unconfigured or broken."""
    global _client_instance, _init_attempted
    if _init_attempted:
        return _client_instance
    _init_attempted = True

    api_key = os.environ.get("PRISMTRACE_API_KEY", "").strip()
    project_id = os.environ.get("PRISMTRACE_PROJECT_ID", "").strip()
    if not api_key or not project_id:
        logger.info("PRISM tracing disabled (PRISMTRACE_* env vars not set)")
        return None
    try:
        from prismtrace import PRISMtrace

        host = os.environ.get("PRISMTRACE_HOST", "").strip() or _DEFAULT_HOST
        _client_instance = PRISMtrace(
            api_key=api_key, host=host, project_id=project_id
        )
        logger.info("PRISM tracing enabled (project %.8s…)", project_id)
    except Exception as exc:  # import error, bad init, anything
        logger.warning("PRISM tracing disabled (client init failed: %s)", exc)
        _client_instance = None
    return _client_instance


def close_tracing() -> None:
    """Flush pending traces and release the client. Never raises; safe twice."""
    global _client_instance
    if _client_instance is None:
        return
    try:
        _client_instance.flush()
        _client_instance.close()
        logger.info("PRISM tracing shut down cleanly")
    except Exception:
        logger.debug("PRISM client shutdown failed (ignored)", exc_info=True)
    _client_instance = None


def trace_chat_turn(
    *,
    model: str,
    input_messages: list[dict[str, str]],
    answer: str,
    latency_ms: int,
    token_usage: tuple[int, int] | None = None,
    conversation_id: str,
    interaction_id: str | None = None,
    confidence: float | None = None,
    prompt_version: str | None = None,
    uncertainty_factors: list[str] | None = None,
    attachment_count: int = 0,
) -> None:
    """Record one full chat turn in PRISM. Fire-and-forget; never raises.

    ``conversation_id`` is passed as ``session_id`` so PRISM groups a
    conversation's turns into one trajectory.
    """
    client = _get_client()
    if client is None:
        return
    metadata: dict[str, Any] = {
        "prompt_version": prompt_version,
        "confidence": confidence,
        "uncertainty_factors": uncertainty_factors or [],
        "attachment_count": attachment_count,
        "surface": "chat-api",
    }
    try:
        client.trace_llm(
            model=model,
            input_messages=input_messages,
            output=answer,
            latency_ms=latency_ms,
            # Real counts from the provider's usage block (summed across
            # samples on the self-consistency path); 0s only when unknown.
            token_count_input=(token_usage or (0, 0))[0],
            token_count_output=(token_usage or (0, 0))[1],
            trace_id=interaction_id,
            agent_id=AGENT_ID,
            agent_name=AGENT_NAME,
            session_id=conversation_id,
            metadata=metadata,
        )
        logger.debug(
            "PRISM trace queued conversation=%s latency_ms=%d", conversation_id, latency_ms
        )
    except Exception:
        logger.warning("PRISM trace_llm failed (ignored)", exc_info=True)
