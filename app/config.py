"""Application configuration loaded from environment variables / .env file."""
import logging
from functools import lru_cache

from dotenv import load_dotenv
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Load .env (if present) BEFORE settings are read; real env vars still win.
load_dotenv()


class Settings(BaseSettings):
    """All runtime knobs. Everything is overridable via env vars."""

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # --- LLM ---
    # "openai" (any OpenAI-compatible API) or "gemini" (Google AI Studio).
    llm_provider: str = "openai"
    openai_api_key: str = ""
    openai_base_url: str = "https://api.openai.com/v1"
    gemini_api_key: str = ""
    # NOTE: gemini-1.5-flash was retired by Google; 'gemini-flash-latest' always
    # tracks the current flash model. Override GEMINI_MODEL to pin a version.
    gemini_model: str = "gemini-flash-latest"
    llm_model: str = "gpt-4o-mini"
    llm_temperature: float = 0.2
    llm_max_tokens: int = 800
    llm_timeout_seconds: float = 30.0
    llm_max_retries: int = 2
    # Ask the API for native JSON mode; disable for providers that reject response_format.
    llm_json_mode: bool = True

    # --- Chat behaviour ---
    max_history_turns: int = 10
    low_confidence_threshold: float = Field(default=0.7, ge=0.0, le=1.0)
    improve_sample_limit: int = Field(default=200, ge=1, le=10_000)

    # --- Storage ---
    # SQLite by default; switch to postgresql+asyncpg://... for PostgreSQL.
    database_url: str = "sqlite+aiosqlite:///./confidence_forge.db"

    # --- HTTP ---
    cors_origins: str = "http://localhost:3000,http://localhost:5173"

    @field_validator("llm_provider")
    @classmethod
    def _validate_provider(cls, value: str) -> str:
        value = (value or "openai").strip().lower()
        if value not in {"openai", "gemini"}:
            raise ValueError(f"llm_provider must be 'openai' or 'gemini', got: {value!r}")
        return value

    @property
    def llm_api_key(self) -> str:
        return self.gemini_api_key if self.llm_provider == "gemini" else self.openai_api_key

    @property
    def llm_model_for_provider(self) -> str:
        return self.gemini_model if self.llm_provider == "gemini" else self.llm_model

    @property
    def cors_origin_list(self) -> list[str]:
        if isinstance(self.cors_origins, str):
            return [o.strip() for o in self.cors_origins.split(",") if o.strip()]
        return self.cors_origins


@lru_cache
def get_settings() -> Settings:
    return Settings()


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(f"confidence_forge.{name}")
