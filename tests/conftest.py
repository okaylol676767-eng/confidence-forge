"""Shared test fixtures: env before app import, temp SQLite DB, TestClient, fake LLM."""
import json
import os
import tempfile
from pathlib import Path

import pytest

# --- Configure env BEFORE any app import (settings are read at import time). ---
_TMP_DIR = tempfile.mkdtemp(prefix="confidence_forge_test_")
DB_PATH = str(Path(_TMP_DIR) / "test.db")
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{DB_PATH}"
os.environ.setdefault("OPENAI_API_KEY", "test-key")
os.environ.setdefault("LLM_JSON_MODE", "false")
os.environ.setdefault("LLM_MAX_RETRIES", "0")

import app.improve as improve_module  # noqa: E402
import app.main as main_module  # noqa: E402
import app.services as services_module  # noqa: E402
from app.llm import LLMClient  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402


class FakeLLM(LLMClient):
    """Deterministic LLM double; default output is a valid structured answer."""

    def __init__(self, answer: str = "Paris is the capital of France.",
                 confidence: float = 0.95, response: str | None = None) -> None:
        super().__init__()
        self.answer = answer
        self.confidence = confidence
        self.response = response
        self.calls: list[list[dict]] = []

    def _raw(self) -> str:
        if self.response is not None:
            return self.response
        return json.dumps({
            "answer": self.answer,
            "confidence": self.confidence,
            "confidence_reason": "Well-known fact.",
            "uncertainty_factors": [],
        })

    async def complete(self, messages):
        self.calls.append(messages)
        return self._raw()

    async def chat_structured(self, messages):
        from app.llm import extract_json_object, validate_structured_answer
        self.calls.append(messages)
        data = extract_json_object(self._raw())
        return validate_structured_answer(data)


@pytest.fixture()
def fake_llm(monkeypatch):
    llm = FakeLLM()
    monkeypatch.setattr(services_module, "llm", llm)
    monkeypatch.setattr(improve_module, "llm_client", llm)
    return llm


@pytest.fixture()
def client(fake_llm):
    # Fresh DB file per test; lifespan startup runs init_db + seeds prompt v1.
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
    with TestClient(main_module.app) as test_client:
        yield test_client
