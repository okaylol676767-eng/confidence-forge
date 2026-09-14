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
        await _add_missing_columns(conn)
    logger.info("Database initialised (%s)", _settings.database_url.split("://")[0])


async def _add_missing_columns(conn) -> None:
    """Tiny idempotent migration for columns added after first release.

    create_all only creates missing *tables*, not missing columns on existing
    tables. SQLite supports ADD COLUMN; PostgreSQL too (non-unique columns).
    """
    from sqlalchemy import text

    try:
        await conn.execute(text(
            "ALTER TABLE interactions ADD COLUMN attachments TEXT DEFAULT '[]'"
        ))
    except Exception:
        pass  # Column already exists — the normal case after the first run.
    try:
        await conn.execute(text(
            "ALTER TABLE interactions ADD COLUMN detailed_solution TEXT"
        ))
    except Exception:
        pass  # Column already exists — the normal case after the first run.
