"""POST /chat — the main chat endpoint."""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_session
from ..schemas import ChatRequest, ChatResponse
from ..services import handle_chat

router = APIRouter(tags=["chat"])


@router.post("/chat", response_model=ChatResponse)
async def chat(payload: ChatRequest, session: AsyncSession = Depends(get_session)) -> ChatResponse:
    return await handle_chat(session, payload)
