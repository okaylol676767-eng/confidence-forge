"""Unit tests for the Gemini client (fake model object; no network, no real key)."""
from types import SimpleNamespace

import pytest

from app.config import Settings
from app.errors import (
    LLMBadResponseError,
    LLMInvalidOutputError,
    LLMNotConfiguredError,
    LLMRateLimitError,
    LLMTimeoutError,
    LLMUnavailableError,
)
from app.llm_gemini import GeminiClient, _map_gemini_error

GOOD_JSON = '{"answer": "Paris", "confidence": 0.97, "confidence_reason": "Fact.", "uncertainty_factors": []}'


def make_settings(**overrides) -> Settings:
    values = dict(
        openai_api_key="",
        gemini_api_key="test-gemini-key",
        gemini_model="gemini-1.5-flash",
        llm_json_mode=False,
        llm_max_retries=0,
    )
    values.update(overrides)
    return Settings(**values)


class FakeResponse:
    def __init__(self, text=None, block_reason=None, finish_reason=None):
        self._text = text
        self.prompt_feedback = SimpleNamespace(block_reason=block_reason) if block_reason else None
        self.candidates = [SimpleNamespace(finish_reason=finish_reason)] if finish_reason else []

    @property
    def text(self):
        if self._text == "RAISE":
            raise ValueError("No text extraction for blocked response")
        return self._text


class FakeModel:
    def __init__(self, response=None, exc=None):
        self.response = response
        self.exc = exc
        self.calls = []
        # Optional list of exceptions to raise in order; last entry repeats.
        # A None entry means "succeed and return self.response".
        self.exc_sequence: list | None = None

    async def generate_content_async(self, prompt, generation_config=None, request_options=None):
        self.calls.append((prompt, generation_config or {}))
        if self.exc_sequence:
            item = self.exc_sequence.pop(0) if len(self.exc_sequence) > 1 else self.exc_sequence[0]
            if item is not None:
                raise item
            return self.response
        if self.exc:
            raise self.exc
        return self.response


def client_with(fake_model, **overrides) -> GeminiClient:
    client = GeminiClient(make_settings(**overrides))
    client._model = fake_model
    return client


def gexc():
    from google.api_core import exceptions as module
    return module


async def _noop_sleep(_seconds: float) -> None:
    return None


# ---------- prompt flattening ----------

def test_flatten_preserves_roles_and_order():
    prompt = GeminiClient._flatten([
        {"role": "system", "content": "Be honest."},
        {"role": "user", "content": "Q1"},
        {"role": "assistant", "content": "A1"},
        {"role": "user", "content": "Q2"},
    ])
    order = [
        prompt.index("[System instructions]"),
        prompt.index("[User message]\nQ1"),
        prompt.index("[Previous assistant message]"),
        prompt.index("[User message]\nQ2"),
    ]
    assert order == sorted(order)


def test_flatten_single_user_message():
    assert GeminiClient._flatten([{"role": "user", "content": "only"}]) == "[User message]\nonly"


# ---------- structured parsing ----------

async def test_chat_structured_happy_path():
    model = FakeModel(response=FakeResponse(text=GOOD_JSON))
    structured = await client_with(model).chat_structured([{"role": "user", "content": "capital of France?"}])
    assert structured.answer == "Paris"
    assert structured.confidence == pytest.approx(0.97)


async def test_chat_structured_tolerates_markdown_wrapped_json():
    raw = "Here is the JSON:\n```json\n" + GOOD_JSON + "\n```"
    model = FakeModel(response=FakeResponse(text=raw))
    structured = await client_with(model).chat_structured([{"role": "user", "content": "hi"}])
    assert structured.answer == "Paris"


async def test_json_mode_sets_response_mime_type():
    model = FakeModel(response=FakeResponse(text=GOOD_JSON))
    await client_with(model, llm_json_mode=True).chat_structured([{"role": "user", "content": "hi"}])
    assert model.calls[0][1].get("response_mime_type") == "application/json"


async def test_malformed_json_raises_invalid_output():
    model = FakeModel(response=FakeResponse(text="I cannot do that in JSON."))
    with pytest.raises(LLMInvalidOutputError):
        await client_with(model).chat_structured([{"role": "user", "content": "hi"}])


async def test_missing_fields_raise_invalid_output():
    model = FakeModel(response=FakeResponse(text='{"answer": "x"}'))
    with pytest.raises(LLMInvalidOutputError):
        await client_with(model).chat_structured([{"role": "user", "content": "hi"}])


# ---------- blocked / empty responses ----------

async def test_blocked_prompt_maps_to_bad_response():
    model = FakeModel(response=FakeResponse(text=None, block_reason="SAFETY"))
    with pytest.raises(LLMBadResponseError):
        await client_with(model).complete([{"role": "user", "content": "hi"}])


async def test_empty_text_maps_to_bad_response():
    model = FakeModel(response=FakeResponse(text=None, finish_reason="STOP"))
    with pytest.raises(LLMBadResponseError):
        await client_with(model).complete([{"role": "user", "content": "hi"}])


# ---------- error mapping ----------

def test_timeout_maps_to_504():
    assert isinstance(_map_gemini_error(gexc().DeadlineExceeded("slow")), LLMTimeoutError)


def test_rate_limit_maps_to_429():
    assert isinstance(_map_gemini_error(gexc().TooManyRequests("429")), LLMRateLimitError)


def test_retry_error_with_rate_limit_cause_maps_to_429():
    err = gexc().RetryError("gave up", gexc().TooManyRequests("429"))
    assert isinstance(_map_gemini_error(err), LLMRateLimitError)


def test_service_unavailable_maps_to_503():
    assert isinstance(_map_gemini_error(gexc().ServiceUnavailable("down")), LLMUnavailableError)


def test_unknown_error_maps_to_bad_response():
    assert isinstance(_map_gemini_error(RuntimeError("weird")), LLMBadResponseError)


# ---------- key validation ----------

async def test_missing_key_raises_not_configured():
    client = GeminiClient(make_settings(gemini_api_key=""))
    with pytest.raises(LLMNotConfiguredError):
        await client.complete([{"role": "user", "content": "hi"}])


# ---------- JSON-mode fallback ----------

async def test_invalid_argument_json_mode_falls_back():
    model = FakeModel(response=FakeResponse(text=GOOD_JSON))

    async def generate(prompt, generation_config=None, request_options=None):
        model.calls.append((prompt, generation_config or {}))
        if generation_config and generation_config.get("response_mime_type"):
            raise gexc().InvalidArgument("response_mime_type not supported")
        return model.response

    model.generate_content_async = generate
    structured = await client_with(model, llm_json_mode=True).chat_structured([{"role": "user", "content": "hi"}])
    assert structured.answer == "Paris"
    assert model.calls[0][1].get("response_mime_type") == "application/json"
    assert "response_mime_type" not in model.calls[1][1]


# ---------- transient-failure retries ----------

async def test_transient_timeout_is_retried_and_succeeds(monkeypatch):
    monkeypatch.setattr("app.llm_gemini._sleep", _noop_sleep)
    model = FakeModel(response=FakeResponse(text=GOOD_JSON))
    model.exc_sequence = [gexc().DeadlineExceeded("slow"), None]  # fail once, then succeed
    structured = await client_with(model, llm_max_retries=2).chat_structured(
        [{"role": "user", "content": "hi"}]
    )
    assert structured.answer == "Paris"
    assert len(model.calls) == 2  # 1 failure, then a successful retry


async def test_retries_exhausted_maps_to_timeout(monkeypatch):
    monkeypatch.setattr("app.llm_gemini._sleep", _noop_sleep)
    model = FakeModel(response=FakeResponse(text=GOOD_JSON))
    model.exc_sequence = [gexc().DeadlineExceeded("slow")]
    with pytest.raises(LLMTimeoutError):
        await client_with(model, llm_max_retries=1).complete([{"role": "user", "content": "hi"}])
    assert len(model.calls) == 2  # initial + 1 retry


async def test_retry_budget_never_exceeds_caller_wall_time(monkeypatch):
    """The frontend aborts at 45s; retries must not outlive a 3x budget."""
    monkeypatch.setattr("app.llm_gemini._sleep", _noop_sleep)
    model = FakeModel(response=FakeResponse(text=GOOD_JSON))
    model.exc_sequence = [gexc().DeadlineExceeded("slow")]
    # llm_timeout_seconds=45 -> budget = 90//45 = 2 attempts, so llm_max_retries=5 is capped.
    with pytest.raises(LLMTimeoutError):
        await client_with(model, llm_max_retries=5, llm_timeout_seconds=45).complete(
            [{"role": "user", "content": "hi"}]
        )
    assert len(model.calls) == 2  # capped by wall-time budget, not by max_retries


async def test_truncated_output_retries_with_doubled_cap(monkeypatch):
    """finish_reason=MAX_TOKENS -> one automatic retry with a doubled budget."""
    truncated = FakeResponse(text='{"answer": "partial')
    truncated.candidates = [SimpleNamespace(finish_reason="MAX_TOKENS")]
    complete = FakeResponse(text=GOOD_JSON)
    complete.candidates = [SimpleNamespace(finish_reason="STOP")]

    class TruncatingModel:
        def __init__(self):
            self.calls = []
            self.caps = []

        async def generate_content_async(self, prompt, generation_config=None, request_options=None):
            self.calls.append(prompt)
            self.caps.append((generation_config or {}).get("max_output_tokens"))
            return truncated if len(self.calls) == 1 else complete

    model = TruncatingModel()
    structured = await client_with(model, llm_max_retries=0).chat_structured(
        [{"role": "user", "content": "hi"}]
    )
    assert structured.answer == "Paris"
    assert len(model.caps) == 2
    assert model.caps[1] == model.caps[0] * 2  # doubled once


async def test_truncation_detected_from_raw_int_finish_reason():
    """Regression: some SDK versions str() the finish_reason protobuf to '2'.

    Production saw exactly this — MAX_TOKENS arrived as the raw int, the old
    string check ('MAX_TOKENS' in '2') never fired, and long derivations
    502'd. The int form must trigger the same doubling retry.
    """
    truncated = FakeResponse(text='{"answer": "partial')
    truncated.candidates = [SimpleNamespace(finish_reason=2)]  # MAX_TOKENS as int
    complete = FakeResponse(text=GOOD_JSON)
    complete.candidates = [SimpleNamespace(finish_reason=1)]  # STOP as int

    class IntTruncatingModel:
        def __init__(self):
            self.caps = []

        async def generate_content_async(self, prompt, generation_config=None, request_options=None):
            self.caps.append((generation_config or {}).get("max_output_tokens"))
            return truncated if len(self.caps) == 1 else complete

    model = IntTruncatingModel()
    structured = await client_with(model, llm_max_retries=0).chat_structured(
        [{"role": "user", "content": "hi"}]
    )
    assert structured.answer == "Paris"
    assert model.caps[1] == model.caps[0] * 2


async def test_finish_reason_name_mapping():
    from app.llm_gemini import _finish_reason_name

    assert _finish_reason_name(2) == "MAX_TOKENS"
    assert _finish_reason_name("2") == "MAX_TOKENS"
    assert _finish_reason_name("MAX_TOKENS") == "MAX_TOKENS"
    assert _finish_reason_name(1) == "STOP"
    assert _finish_reason_name(None) == "none"


async def test_truncation_retry_only_happens_once(monkeypatch):
    truncated = FakeResponse(text='{"answer": "partial')
    truncated.candidates = [SimpleNamespace(finish_reason="MAX_TOKENS")]

    class AlwaysTruncating:
        def __init__(self):
            self.caps = []

        async def generate_content_async(self, prompt, generation_config=None, request_options=None):
            self.caps.append((generation_config or {}).get("max_output_tokens"))
            return truncated

    model = AlwaysTruncating()
    with pytest.raises(LLMInvalidOutputError):
        await client_with(model, llm_max_retries=0).chat_structured(
            [{"role": "user", "content": "hi"}]
        )
    assert len(model.caps) == 2  # initial + exactly one doubling, no loop
    assert model.caps[1] == model.caps[0] * 2


async def test_non_transient_errors_are_not_retried(monkeypatch):
    monkeypatch.setattr("app.llm_gemini._sleep", _noop_sleep)
    model = FakeModel(response=FakeResponse(text=GOOD_JSON))
    model.exc_sequence = [gexc().InvalidArgument("bad field")]
    with pytest.raises(LLMBadResponseError):
        await client_with(model, llm_max_retries=2).complete([{"role": "user", "content": "hi"}])
    assert len(model.calls) == 1  # no retry for 4xx-style errors
