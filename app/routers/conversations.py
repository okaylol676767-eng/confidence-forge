"""GET /conversations/{conversation_id} — chat history for one conversation."""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_session
from ..errors import NotFoundError
from ..schemas import ConversationHistoryResponse
from ..services import get_conversation_history

router = APIRouter(tags=["conversations"])


@router.get("/conversations/{conversation_id}", response_model=ConversationHistoryResponse)
async def conversation_history(
    conversation_id: str, session: AsyncSession = Depends(get_session)
) -> ConversationHistoryResponse:
    history = await get_conversation_history(session, conversation_id)
    if history.message_count == 0:
        raise NotFoundError(f"No conversation found with id '{conversation_id}'.")
    return history
