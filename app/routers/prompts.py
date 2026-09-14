"""POST /improve + prompt-version introspection endpoints."""
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import get_logger
from ..database import get_session
from ..errors import DatabaseError
from ..improve import improve_prompt_flow
from ..models import PromptVersion
from ..schemas import ImproveRequest, ImproveResponse, PromptVersionOut

logger = get_logger("routers.prompts")

router = APIRouter(tags=["prompts"])


@router.post("/improve", response_model=ImproveResponse)
async def improve(payload: ImproveRequest, session: AsyncSession = Depends(get_session)) -> ImproveResponse:
    # Typed errors (LLMError, AppError) propagate; main.py renders the envelope.
    return await improve_prompt_flow(session, activate=payload.activate)


@router.get("/prompts/versions", response_model=list[PromptVersionOut])
async def list_prompt_versions(session: AsyncSession = Depends(get_session)) -> list[PromptVersionOut]:
    try:
        result = await session.execute(select(PromptVersion).order_by(PromptVersion.id))
        rows = list(result.scalars().all())
    except SQLAlchemyError:
        logger.exception("DB error while listing prompt versions")
        raise DatabaseError("Failed to list prompt versions.") from None
    return [PromptVersionOut.model_validate(row, from_attributes=True) for row in rows]
