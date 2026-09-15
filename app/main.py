"""FastAPI application factory: middleware, exception handlers, routers, lifespan."""
import logging
import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError

from .config import get_logger, get_settings
from .database import engine, init_db
from .errors import AppError, DatabaseError, ErrorCode
from .logging_config import configure_logging
from .prewarm import start_prewarm
from .prompts import BASELINE_VERSIONS, DEFAULT_PROMPT_VERSION, prompt_manager
from .tracing import close_tracing

logger = get_logger("main")
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()
    try:
        await init_db()
        await seed_prompts()
        # Pre-warm the answer cache with common questions (background task;
        # answers come from the real model, first user ask is cache-fast).
        try:
            from . import services

            prompt_version, system_prompt = await prompt_manager.get_active()
            app.state.prewarm_task = start_prewarm(
                services.llm, prompt_version, system_prompt
            )
        except Exception:
            logger.exception("Answer-cache prewarm failed to start (non-fatal)")
        # Automated self-improvement loop: periodically harvest failure
        # signals (PRISM evaluations + low-confidence answers) into lessons.
        try:
            from .self_improve import start_self_improve

            app.state.self_improve_task = start_self_improve(services.llm)
        except Exception:
            logger.exception("Self-improvement loop failed to start (non-fatal)")
    except Exception:
        logger.exception("Startup failed")
        raise
    yield
    prewarm_task = getattr(app.state, "prewarm_task", None)
    if prewarm_task is not None and not prewarm_task.done():
        prewarm_task.cancel()
    improve_task = getattr(app.state, "self_improve_task", None)
    if improve_task is not None and not improve_task.done():
        improve_task.cancel()
    close_tracing()  # flush pending PRISM traces before the process exits
    await engine.dispose()


async def seed_prompts() -> None:
    """Ensure baseline prompt versions exist, v_default is active, text current.

    Fresh DB: seed all baselines, activate the default. Existing DB: refresh
    each baseline's text in place (so prompt improvements ship without manual
    migration) and activate the default if nothing is active. /improve-derived
    versions (created_by='improve') are never touched.
    """
    existing = {row.version for row in await prompt_manager.list_versions()}
    # Fresh DB: seed all baselines, activate the default. Existing DB: refresh
    # each baseline's text in place AND insert any baseline that is missing
    # (e.g. v2 added after the DB was created) so prompt upgrades ship without
    # manual migration. /improve-derived versions are never touched.
    if not existing:
        for index, (version, text) in enumerate(BASELINE_VERSIONS.items()):
            await prompt_manager.save(
                version=version,
                system_prompt=text,
                created_by="seed",
                parent_version=None,
                activate=(version == DEFAULT_PROMPT_VERSION),
            )
        logger.info("Seeded baseline prompt versions %s", list(BASELINE_VERSIONS))
    else:
        missing = [v for v in BASELINE_VERSIONS if v not in existing]
        active_version = await prompt_manager.get_active_version()
        for version in missing:
            # Upgrade rule: a missing DEFAULT baseline replaces an older
            # BASELINE as active (that is the prompt upgrade shipping). An
            # /improve-derived active version stays untouched.
            should_activate = (
                version == DEFAULT_PROMPT_VERSION
                and (active_version is None or active_version in BASELINE_VERSIONS)
            )
            await prompt_manager.save(
                version=version,
                system_prompt=BASELINE_VERSIONS[version],
                created_by="seed",
                parent_version=None,
                activate=should_activate,
            )
        for version, text in BASELINE_VERSIONS.items():
            if version in existing:
                await prompt_manager.update_text(version, text)
        active_version = await prompt_manager.get_active_version()
        if active_version is None:
            await prompt_manager.activate(DEFAULT_PROMPT_VERSION)
        elif active_version in BASELINE_VERSIONS and active_version != DEFAULT_PROMPT_VERSION:
            # The default baseline is newer than the active one (e.g. DB
            # created before v2 existed): upgrade the activation so prompt
            # improvements actually ship. /improve-derived versions win and
            # are never switched away from.
            await prompt_manager.activate(DEFAULT_PROMPT_VERSION)
            logger.info(
                "Active baseline upgraded %s -> %s",
                active_version, DEFAULT_PROMPT_VERSION,
            )
        logger.info(
            "Baseline prompt versions refreshed: %s%s",
            sorted(existing | set(BASELINE_VERSIONS)),
            f" (inserted missing: {missing})" if missing else "",
        )


def error_response(status_code: int, message: str, code: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"error": True, "message": message, "code": code},
    )


async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    """Our typed errors -> standard envelope; details logged server-side only."""
    log = logger.error if exc.status_code >= 500 else logger.warning
    log(
        "%s %s -> %s [%s]: %s",
        request.method, request.url.path, exc.status_code, exc.code, exc.message,
    )
    return error_response(exc.status_code, exc.message, str(exc.code))


async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """Pydantic/FastAPI validation errors -> 422 with the standard envelope."""
    summary = "; ".join(
        f"{'.'.join(str(loc) for loc in err.get('loc', []))}: {err.get('msg', 'invalid')}"
        for err in exc.errors()
    )
    logger.warning("%s %s -> 422 [VALIDATION_ERROR]: %s", request.method, request.url.path, summary)
    return error_response(422, f"Invalid request: {summary}", ErrorCode.VALIDATION_ERROR)


async def unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
    """Never leak stack traces or internals to the client."""
    logger.exception("Unhandled error on %s %s", request.method, request.url.path)
    return error_response(
        500,
        "An unexpected server error occurred. Please try again later.",
        ErrorCode.INTERNAL_ERROR,
    )


async def db_error_handler(request: Request, exc: SQLAlchemyError) -> JSONResponse:
    logger.exception("Database error on %s %s", request.method, request.url.path)
    return error_response(500, "A database error occurred.", ErrorCode.DATABASE_ERROR)


def create_app() -> FastAPI:
    app = FastAPI(
        title="Confidence Forge",
        description="A transparent, self-improving AI chatbot backend.",
        version="1.0.0",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Order matters: most specific first.
    app.add_exception_handler(AppError, app_error_handler)
    app.add_exception_handler(RequestValidationError, validation_error_handler)
    app.add_exception_handler(SQLAlchemyError, db_error_handler)

    @app.middleware("http")
    async def catch_all_errors(request: Request, call_next):
        """Last-resort net: any unhandled exception becomes the standard envelope."""
        try:
            return await call_next(request)
        except Exception:
            return await unhandled_error_handler(request, sys.exc_info()[1])

    # Routers
    from .routers.chat import router as chat_router
    from .routers.conversations import router as conversations_router
    from .routers.sessions import router as sessions_router
    from .routers.stats import router as stats_router
    from .routers.prompts import router as prompts_router

    app.include_router(chat_router)
    app.include_router(conversations_router)
    app.include_router(sessions_router)
    app.include_router(stats_router)
    app.include_router(prompts_router)

    @app.get("/health", tags=["meta"])
    async def health() -> dict:
        return {"status": "ok", "app": "confidence-forge", "version": "1.0.0"}

    return app


app = create_app()
