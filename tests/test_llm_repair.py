"""Repair pass: recover missing/malformed JSON, skip when not repairable."""
import json

import pytest

from app.llm_json import (
    LLMInvalidOutputError,
    chat_structured_repaired,
    extract_json_object,
    validate_structured_answer,
)
from app.schemas import StructuredAnswer


def _ok_json(answer: str = "42") -> str:
    return json.dumps(
        {
            "answer": answer,
            "confidence": 0.9,
            "confidence_reason": "clean computation",
            "uncertainty_factors": [],
            "detailed_solution": None,
        }
    )


class ScriptedCompleter:
    """Returns queued raw payloads; records every prompt it was handed."""

    def __init__(self, payloads: list[str]) -> None:
        self.payloads = list(payloads)
        self.prompts: list[list[dict[str, str]]] = []

    async def __call__(self, messages, **kwargs) -> str:
        self.prompts.append([dict(m) for m in messages])
        return self.payloads.pop(0)


@pytest.mark.asyncio
async def test_missing_metadata_is_repaired_in_one_retry():
    """Math came back right but without confidence fields -> repair asks once, recovers."""
    broken = json.dumps({"answer": "42", "confidence": 0.9})  # missing required fields
    comp = ScriptedCompleter([broken, _ok_json("42")])

    result = await chat_structured_repaired(
        comp, [{"role": "user", "content": "6 x 7"}], validate_structured_answer
    )

    assert result.answer == "42"
    assert len(comp.prompts) == 2  # original + exactly one repair
    # The repair prompt names the actual failure.
    repair_text = comp.prompts[1][-1]["content"]
    assert "confidence_reason" in repair_text  # names the missing field
    assert "Resend the SAME answer" in repair_text


@pytest.mark.asyncio
async def test_second_failure_raises_original_problem():
    comp = ScriptedCompleter(["not json at all", "still not json"])
    with pytest.raises(LLMInvalidOutputError):
        await chat_structured_repaired(
            comp, [{"role": "user", "content": "q"}], validate_structured_answer
        )
    assert len(comp.prompts) == 2  # never retries more than once


@pytest.mark.asyncio
async def test_should_repair_veto_skips_second_call():
    comp = ScriptedCompleter(["truncated junk {"])
    with pytest.raises(LLMInvalidOutputError):
        await chat_structured_repaired(
            comp,
            [{"role": "user", "content": "q"}],
            validate_structured_answer,
            should_repair=lambda exc: False,
        )
    assert len(comp.prompts) == 1  # vetoed: no repair call


@pytest.mark.asyncio
async def test_valid_first_answer_never_triggers_repair():
    comp = ScriptedCompleter([_ok_json("56")])
    result = await chat_structured_repaired(
        comp, [{"role": "user", "content": "7 x 8"}], validate_structured_answer
    )
    assert result.answer == "56"
    assert len(comp.prompts) == 1
