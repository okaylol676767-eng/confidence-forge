"""Selects the LLM client implementation based on configuration."""
from .config import Settings, get_settings
from .llm import LLMClient
from .llm_gemini import GeminiClient


def build_llm_client(settings: Settings | None = None) -> LLMClient | GeminiClient:
    """Return the configured provider client.

    Keys are validated lazily by each client so the app can boot without one
    (chat then answers 503 LLM_NOT_CONFIGURED instead of crashing at startup).
    """
    settings = settings or get_settings()
    if settings.llm_provider == "gemini":
        return GeminiClient(settings)
    return LLMClient(settings)
