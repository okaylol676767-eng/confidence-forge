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

    async def generate_content_async(self, prompt, generation_config=None, request_options=None):
        self.calls.append((prompt, generation_config or {}))
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
