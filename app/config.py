"""Application configuration loaded from environment variables / .env file."""
import logging
from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """All runtime knobs. Everything is overridable via env vars."""

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # --- LLM ---
    openai_api_key: str = ""
    openai_base_url: str = "https://api.openai.com/v1"
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
