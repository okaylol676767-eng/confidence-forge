"""Async SQLAlchemy engine + session factory + schema creation."""
import logging
from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from .config import get_settings

logger = logging.getLogger("confidence_forge.db")

_settings = get_settings()

def _build_engine(url: str) -> AsyncEngine:
    kwargs: dict = {"echo": False, "pool_pre_ping": True}
    if url.startswith("sqlite"):
        # NullPool: avoids cross-event-loop connection reuse and file-lock issues.
        kwargs["poolclass"] = NullPool
    return create_async_engine(url, **kwargs)


engine: AsyncEngine = _build_engine(_settings.database_url)

SessionFactory = async_sessionmaker(
    bind=engine,
    expire_on_commit=False,
    autoflush=False,
)


async def get_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency: one session per request, always closed."""
    async with SessionFactory() as session:
        yield session


async def init_db() -> None:
    """Create tables if they don't exist yet (no-op when they do)."""
    from . import models  # noqa: F401  (ensures models are registered)

    async with engine.begin() as conn:
        await conn.run_sync(models.Base.metadata.create_all)
    logger.info("Database initialised (%s)", _settings.database_url.split("://")[0])
