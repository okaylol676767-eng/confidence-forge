"""GET /stats/summary — aggregate quality metrics across all interactions.
GET /stats/lessons — lessons learned by the automated self-improvement loop."""
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import get_logger
from ..database import get_session
from ..errors import DatabaseError
from ..models import ImprovementLesson
from ..schemas import LessonOut, LessonsOut, StatsSummaryResponse
from ..services import get_stats_summary

logger = get_logger("routers.stats")

router = APIRouter(prefix="/stats", tags=["stats"])


@router.get("/summary", response_model=StatsSummaryResponse)
async def stats_summary(session: AsyncSession = Depends(get_session)) -> StatsSummaryResponse:
    return await get_stats_summary(session)


@router.get("/lessons", response_model=LessonsOut)
async def lessons(session: AsyncSession = Depends(get_session)) -> LessonsOut:
    """What the self-improvement loop has learned so far (newest first)."""
    try:
        result = await session.execute(
            select(ImprovementLesson)
            .where(ImprovementLesson.is_active.is_(True))
            .order_by(ImprovementLesson.created_at.desc())
            .limit(100)
        )
        rows = list(result.scalars().all())
    except SQLAlchemyError:
        logger.exception("DB error while listing improvement lessons")
        raise DatabaseError("Failed to list improvement lessons.") from None
    return LessonsOut(count=len(rows), lessons=[
        LessonOut.model_validate(row, from_attributes=True) for row in rows
    ])
