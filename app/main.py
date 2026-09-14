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
from .prompts import BASELINE_VERSIONS, DEFAULT_PROMPT_VERSION, prompt_manager

logger = get_logger("main")
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()
    try:
        await init_db()
        await seed_prompts()
    except Exception:
        logger.exception("Startup failed")
        raise
    yield
    await engine.dispose()


async def seed_prompts() -> None:
    """Ensure baseline prompt versions exist, v_default is active, text current.

    Fresh DB: seed all baselines, activate the default. Existing DB: refresh
    each baseline's text in place (so prompt improvements ship without manual
    migration) and activate the default if nothing is active. /improve-derived
    versions (created_by='improve') are never touched.
    """
    existing = {row.version for row in await prompt_manager.list_versions()}
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
        for version, text in BASELINE_VERSIONS.items():
            await prompt_manager.update_text(version, text)
        active_version = await prompt_manager.get_active_version()
        if active_version is None:
            await prompt_manager.activate(DEFAULT_PROMPT_VERSION)
        logger.info("Baseline prompt versions refreshed: %s", sorted(existing | set(BASELINE_VERSIONS)))


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
    from .routers.stats import router as stats_router
    from .routers.prompts import router as prompts_router

    app.include_router(chat_router)
    app.include_router(conversations_router)
    app.include_router(stats_router)
    app.include_router(prompts_router)

    @app.get("/health", tags=["meta"])
    async def health() -> dict:
        return {"status": "ok", "app": "confidence-forge", "version": "1.0.0"}

    return app


app = create_app()
