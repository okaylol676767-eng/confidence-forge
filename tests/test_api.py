"""Integration tests: chat flow, history, stats, improve, and error handling."""
import json

import pytest

from tests.conftest import FakeLLM


def test_chat_returns_structured_response(client, fake_llm):
    resp = client.post("/chat", json={"message": "What is the capital of France?"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["answer"] == "Paris is the capital of France."
    assert body["confidence"] == pytest.approx(0.95)
    assert body["confidence_reason"] == "Well-known fact."
    assert body["uncertainty_factors"] == []
    assert body["conversation_id"].startswith("c-")
    assert body["prompt_version"] == "v1"
    assert body["latency_ms"] >= 0
    assert isinstance(body["interaction_id"], int)


def test_chat_with_existing_conversation_id(client):
    resp = client.post("/chat", json={"message": "hi", "conversation_id": "c-custom123"})
    assert resp.status_code == 200
    assert resp.json()["conversation_id"] == "c-custom123"


def test_chat_validates_empty_message(client):
    resp = client.post("/chat", json={"message": "   "})
    assert resp.status_code == 422
    body = resp.json()
    assert body["error"] is True
    assert body["code"] == "VALIDATION_ERROR"
    assert "message" in body["message"].lower()


def test_chat_validates_missing_message(client):
    resp = client.post("/chat", json={"conversation_id": "c-x"})
    assert resp.status_code == 422
    assert resp.json()["code"] == "VALIDATION_ERROR"


def test_chat_validates_long_message(client):
    resp = client.post("/chat", json={"message": "x" * 9000})
    assert resp.status_code == 422


def test_chat_history_is_included_in_llm_messages(client, fake_llm):
    client.post("/chat", json={"message": "First question", "conversation_id": "c-hist"})
    client.post("/chat", json={"message": "Second question", "conversation_id": "c-hist"})
    second_call_messages = fake_llm.calls[-1]
    # system + [user, assistant] x 1 + new user message
    assert len(second_call_messages) == 4
    assert second_call_messages[0]["role"] == "system"
    assert second_call_messages[-1]["content"] == "Second question"
    assert "First question" in second_call_messages[1]["content"]


def test_llm_malformed_json_returns_fallback_error(client, fake_llm):
    fake_llm.response = "This is not JSON at all."
    resp = client.post("/chat", json={"message": "hello"})
    assert resp.status_code == 502
    body = resp.json()
    assert body["error"] is True
    assert body["code"] == "LLM_INVALID_OUTPUT"
    assert "malformed" in body["message"].lower() or "json" in body["message"].lower()
    # No stack traces or internals in the response.
    assert "Traceback" not in resp.text


def test_llm_missing_fields_returns_error(client, fake_llm):
    fake_llm.response = json.dumps({"answer": "x"})
    resp = client.post("/chat", json={"message": "hello"})
    assert resp.status_code == 502
    assert resp.json()["code"] == "LLM_INVALID_OUTPUT"


def test_conversation_history_returns_messages(client):
    client.post("/chat", json={"message": "Q1", "conversation_id": "c-demo"})
    client.post("/chat", json={"message": "Q2", "conversation_id": "c-demo"})

    resp = client.get("/conversations/c-demo")
    assert resp.status_code == 200
    body = resp.json()
    assert body["conversation_id"] == "c-demo"
    assert body["message_count"] == 4  # 2 user + 2 assistant
    roles = [m["role"] for m in body["messages"]]
    assert roles == ["user", "assistant", "user", "assistant"]
    first = body["messages"][0]
    assert first["content"] == "Q1"
    second = body["messages"][1]
    assert second["confidence"] == pytest.approx(0.95)
    assert second["confidence_reason"] == "Well-known fact."
    assert second["prompt_version"] == "v1"
    assert second["latency_ms"] >= 0


def test_conversation_history_404_for_unknown(client):
    resp = client.get("/conversations/c-doesnotexist")
    assert resp.status_code == 404
    body = resp.json()
    assert body["error"] is True
    assert body["code"] == "NOT_FOUND"


def test_stats_summary_empty(client):
    resp = client.get("/stats/summary")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total_interactions"] == 0
    assert body["average_confidence"] is None
    assert body["low_confidence_count"] == 0
    assert body["low_confidence_threshold"] == pytest.approx(0.7)
    assert body["by_prompt_version"] == {}


def test_stats_summary_counts_low_confidence(client, fake_llm):
    fake_llm.confidence = 0.42
    client.post("/chat", json={"message": "hard question", "conversation_id": "c-low"})
    fake_llm.confidence = 0.9
    client.post("/chat", json={"message": "easy question", "conversation_id": "c-high"})

    resp = client.get("/stats/summary")
    body = resp.json()
    assert body["total_interactions"] == 2
    assert body["low_confidence_count"] == 1
    assert body["average_confidence"] == pytest.approx((0.42 + 0.9) / 2, abs=1e-3)
    v1 = body["by_prompt_version"]["v1"]
    assert v1["count"] == 2
    assert v1["low_confidence_count"] == 1


def test_improve_requires_low_confidence_data(client):
    resp = client.post("/improve", json={})
    assert resp.status_code == 400
    body = resp.json()
    assert body["code"] == "INVALID_REQUEST"


def test_improve_creates_and_activates_new_version(client, fake_llm):
    fake_llm.confidence = 0.3
    client.post("/chat", json={"message": "Hard question", "conversation_id": "c-imp"})

    fake_llm.response = "v2 system prompt with clearer instructions and explicit uncertainty reporting rules."
    resp = client.post("/improve", json={"activate": True})
    assert resp.status_code == 200
    body = resp.json()
    assert body["new_version"]["version"] == "v2"
    assert body["new_version"]["is_active"] is True
    assert body["new_version"]["parent_version"] == "v1"
    assert body["analyzed_interactions"] == 1
    assert body["average_confidence_of_sample"] == pytest.approx(0.3)

    # The new version is now active: next chat uses it.
    fake_llm.response = None
    resp2 = client.post("/chat", json={"message": "Another question"})
    assert resp2.json()["prompt_version"] == "v2"


def test_improve_with_activate_false_does_not_switch(client, fake_llm):
    fake_llm.confidence = 0.3
    client.post("/chat", json={"message": "Hard", "conversation_id": "c-imp2"})

    fake_llm.response = "A brand new improved prompt with much more explicit instructions for answers."
    resp = client.post("/improve", json={"activate": False})
    assert resp.status_code == 200
    assert resp.json()["new_version"]["is_active"] is False

    fake_llm.response = None
    resp2 = client.post("/chat", json={"message": "Next"})
    assert resp2.json()["prompt_version"] == "v1"


def test_prompt_versions_listing(client, fake_llm):
    fake_llm.confidence = 0.3
    client.post("/chat", json={"message": "Hard", "conversation_id": "c-v"})
    fake_llm.response = "Improved prompt text with explicit rules about asking clarifying questions when unsure."
    client.post("/improve", json={"activate": True})

    resp = client.get("/prompts/versions")
    assert resp.status_code == 200
    versions = [v["version"] for v in resp.json()]
    assert versions == ["v1", "v2"]


def test_llm_timeout_maps_to_504(client, fake_llm, monkeypatch):
    async def raise_timeout(messages, attachments=None):
        from app.errors import LLMTimeoutError
        raise LLMTimeoutError()

    monkeypatch.setattr(fake_llm, "chat_structured", raise_timeout)
    resp = client.post("/chat", json={"message": "hello"})
    assert resp.status_code == 504
    body = resp.json()
    assert body["error"] is True
    assert body["code"] == "LLM_TIMEOUT"


def test_unhandled_error_returns_500_envelope(client, monkeypatch):
    async def boom(session):
        raise RuntimeError("boom")

    monkeypatch.setattr("app.routers.stats.get_stats_summary", boom)
    resp = client.get("/stats/summary")
    assert resp.status_code == 500
    body = resp.json()
    assert body["error"] is True
    assert body["code"] == "INTERNAL_ERROR"
    assert "boom" not in resp.text
