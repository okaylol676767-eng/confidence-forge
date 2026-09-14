"""GET /stats/summary — aggregate quality metrics across all interactions."""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_session
from ..schemas import StatsSummaryResponse
from ..services import get_stats_summary

router = APIRouter(prefix="/stats", tags=["stats"])


@router.get("/summary", response_model=StatsSummaryResponse)
async def stats_summary(session: AsyncSession = Depends(get_session)) -> StatsSummaryResponse:
    return await get_stats_summary(session)
