"""Session endpoints — named conversations (\"New chat\" or whatever the user names it)."""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_session
from ..schemas import SessionOut, SessionRenameRequest
from ..services import list_sessions, rename_session

router = APIRouter(tags=["sessions"])


@router.get("/sessions", response_model=list[SessionOut])
async def get_sessions(
    limit: int = Query(default=100, ge=1, le=500),
    session: AsyncSession = Depends(get_session),
) -> list[SessionOut]:
    """Most-recently-active sessions first."""
    return await list_sessions(session, limit=limit)


@router.patch("/sessions/{conversation_id}", response_model=SessionOut)
async def rename_conversation(
    conversation_id: str,
    payload: SessionRenameRequest,
    session: AsyncSession = Depends(get_session),
) -> SessionOut:
    """Rename a chat session (\"New chat\" -> anything, 1-80 chars)."""
    return await rename_session(session, conversation_id, payload.name)
