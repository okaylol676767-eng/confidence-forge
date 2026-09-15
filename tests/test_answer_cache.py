"""Answer cache: exact hits, TTL/expiry, safety gating, and service integration."""
import time

from app.answer_cache import AnswerCache, cacheable_turn, normalize_question
from app.schemas import StructuredAnswer


def _answer(text: str = "42", confidence: float = 0.99) -> StructuredAnswer:
    return StructuredAnswer(
        answer=text,
        confidence=confidence,
        confidence_reason="r",
        uncertainty_factors=[],
        detailed_solution=None,
    )


def test_normalize_question_is_case_and_whitespace_insensitive():
    assert normalize_question("What is 7 x 8? ") == normalize_question("  what is 7 x 8?")
    assert normalize_question("a  b") == "a b"


def test_exact_match_hits_and_wrong_question_misses():
    cache = AnswerCache(max_size=8, ttl_seconds=60)
    key = cache.make_key("v2", "What is 7 x 8?")
    cache.put(key, _answer("56"), "v2")

    assert cache.get(key) is not None
    assert cache.get(cache.make_key("v2", "What is 7 x 9?")) is None


def test_ttl_expiry_turns_hit_into_miss():
    cache = AnswerCache(max_size=8, ttl_seconds=0.01)
    key = cache.make_key("v2", "q")
    cache.put(key, _answer(), "v2")
    assert cache.get(key) is not None
    time.sleep(0.02)
    assert cache.get(key) is None


def test_lru_eviction_respects_max_size():
    cache = AnswerCache(max_size=2, ttl_seconds=60)
    k1 = cache.make_key("v2", "one")
    k2 = cache.make_key("v2", "two")
    k3 = cache.make_key("v2", "three")
    cache.put(k1, _answer("1"), "v2")
    cache.put(k2, _answer("2"), "v2")
    cache.get(k1)  # refresh k1; k2 becomes LRU
    cache.put(k3, _answer("3"), "v2")

    assert cache.get(k1) is not None
    assert cache.get(k2) is None
    assert cache.get(k3) is not None


def test_cacheable_turn_gating():
    assert cacheable_turn(message="hi", history_count=0, attachment_count=0) is True
    assert cacheable_turn(message="hi", history_count=1, attachment_count=0) is False
    assert cacheable_turn(message="hi", history_count=0, attachment_count=2) is False
    assert cacheable_turn(message="   ", history_count=0, attachment_count=0) is False


def test_service_repeat_question_served_from_cache(client, fake_llm, monkeypatch):
    """Second identical first-turn question must not call the LLM again."""
    from app import services
    from app.answer_cache import AnswerCache

    # The suite disables the cache globally; enable a fresh one for this test.
    monkeypatch.setattr(services, "answer_cache", AnswerCache(max_size=8, ttl_seconds=60))

    body = {"message": "What is the boiling point of water in Fahrenheit?"}
    r1 = client.post("/chat", json=body)
    r2 = client.post("/chat", json=body)

    assert r1.status_code == r2.status_code == 200
    assert len(fake_llm.calls) == 1          # LLM called only for the first turn
    assert r1.json()["answer"] == r2.json()["answer"]
    assert r2.json()["latency_ms"] <= r1.json()["latency_ms"] + 50
