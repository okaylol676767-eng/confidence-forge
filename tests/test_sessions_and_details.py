"""Sessions (named conversations) + detailed_solution end-to-end tests."""
import json

import pytest


def _payload(**overrides) -> str:
    base = {
        "answer": "The radius is $\\sqrt{10}$.",
        "confidence": 0.88,
        "confidence_reason": "Clean derivation, passed dimensional check.",
        "uncertainty_factors": [],
        "detailed_solution": None,
    }
    base.update(overrides)
    return json.dumps(base)


# ---------- detailed_solution ----------

def test_chat_returns_detailed_solution_when_present(client, fake_llm):
    fake_llm.response = _payload(
        detailed_solution="### Step 1\nGivens: $P=(2,1)$...\n### Step 2\n$d=\\sqrt{10}$",
    )
    resp = client.post("/chat", json={"message": "Solve for the radius."})
    assert resp.status_code == 200
    body = resp.json()
    assert body["detailed_solution"] is not None
    assert "Step 1" in body["detailed_solution"]
    # The concise answer stays separate.
    assert "Step 1" not in body["answer"]


def test_chat_detailed_solution_absent_is_null(client, fake_llm):
    fake_llm.response = _payload()
    resp = client.post("/chat", json={"message": "What is the capital of France?"})
    assert resp.status_code == 200
    assert resp.json()["detailed_solution"] is None


def test_detailed_solution_empty_string_normalizes_to_null(client, fake_llm):
    fake_llm.response = _payload(detailed_solution="   ")
    resp = client.post("/chat", json={"message": "hello"})
    assert resp.status_code == 200
    assert resp.json()["detailed_solution"] is None


def test_detailed_solution_persists_in_history(client, fake_llm):
    fake_llm.response = _payload(
        detailed_solution="Full derivation with every algebra step: $d^2 = 1 + 9 = 10$.",
    )
    client.post("/chat", json={"message": "Circumcenter?", "conversation_id": "c-det"})
    resp = client.get("/conversations/c-det")
    assert resp.status_code == 200
    assistant = [m for m in resp.json()["messages"] if m["role"] == "assistant"][0]
    assert assistant["detailed_solution"] is not None
    assert "algebra step" in assistant["detailed_solution"]


def test_history_without_detailed_solution_is_null_not_missing(client):
    client.post("/chat", json={"message": "Q1", "conversation_id": "c-plain"})
    resp = client.get("/conversations/c-plain")
    assistant = [m for m in resp.json()["messages"] if m["role"] == "assistant"][0]
    assert assistant["detailed_solution"] is None


# ---------- sessions ----------

def test_session_auto_created_with_question_as_name(client):
    resp = client.post(
        "/chat",
        json={"message": "How do I compute the area of a circle?", "conversation_id": "c-name1"},
    )
    assert resp.status_code == 200
    sessions = client.get("/sessions").json()
    match = [s for s in sessions if s["conversation_id"] == "c-name1"]
    assert len(match) == 1
    assert match[0]["name"] == "How do I compute the area of a circle?"
    assert match[0]["message_count"] == 1


def test_session_name_defaults_when_first_message_blankish(client, fake_llm):
    fake_llm.response = _payload(answer="ok", confidence=0.9,
                                 confidence_reason="r", detailed_solution=None)
    client.post("/chat", json={"message": "hi", "conversation_id": "c-name2"})
    sessions = client.get("/sessions").json()
    match = [s for s in sessions if s["conversation_id"] == "c-name2"]
    assert match[0]["name"] == "hi"


def test_long_first_message_is_trimmed_for_name(client):
    long_q = "x" * 120
    client.post("/chat", json={"message": long_q, "conversation_id": "c-long"})
    sessions = client.get("/sessions").json()
    match = [s for s in sessions if s["conversation_id"] == "c-long"][0]
    assert len(match["name"]) <= 61  # 60 chars + ellipsis
    assert match["name"].endswith("…")


def test_rename_session(client):
    client.post("/chat", json={"message": "Q", "conversation_id": "c-ren"})
    resp = client.patch("/sessions/c-ren", json={"name": "Physics homework"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["name"] == "Physics homework"
    # Persists.
    sessions = client.get("/sessions").json()
    match = [s for s in sessions if s["conversation_id"] == "c-ren"][0]
    assert match["name"] == "Physics homework"


def test_rename_requires_non_empty_name(client):
    client.post("/chat", json={"message": "Q", "conversation_id": "c-empty"})
    resp = client.patch("/sessions/c-empty", json={"name": "   "})
    assert resp.status_code == 422


def test_rename_unknown_session_404(client):
    resp = client.patch("/sessions/c-ghost", json={"name": "nope"})
    assert resp.status_code == 404
    assert resp.json()["code"] == "NOT_FOUND"


def test_sessions_order_most_recent_first(client):
    client.post("/chat", json={"message": "older q", "conversation_id": "c-old"})
    client.post("/chat", json={"message": "newer q", "conversation_id": "c-new"})
    sessions = client.get("/sessions").json()
    ids = [s["conversation_id"] for s in sessions]
    assert ids.index("c-new") < ids.index("c-old")


def test_second_message_does_not_rename_session(client):
    client.post("/chat", json={"message": "first topic", "conversation_id": "c-keep"})
    client.patch("/sessions/c-keep", json={"name": "My thread"})
    client.post("/chat", json={"message": "second topic", "conversation_id": "c-keep"})
    sessions = client.get("/sessions").json()
    match = [s for s in sessions if s["conversation_id"] == "c-keep"][0]
    assert match["name"] == "My thread"
    assert match["message_count"] == 2
