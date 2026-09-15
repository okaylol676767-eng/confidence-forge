"""Self-improvement: hashing, dedupe, selection, injection, fingerprinting."""
import pytest

from app.self_improve import (
    _parse_lessons,
    build_lesson_block,
    fingerprint_lessons,
    lesson_hash,
    score_lesson,
    select_lessons,
    system_prompt_with_lessons,
)


def test_lesson_hash_normalizes_case_and_whitespace():
    assert lesson_hash("Check Units  Carefully") == lesson_hash("check units carefully")


def test_parse_lessons_valid_and_malformed():
    good = '{"lessons": ["Always check units", "Re-derive before finalizing"]}'
    assert len(_parse_lessons(good)) == 2
    assert _parse_lessons("not json at all") == []
    assert _parse_lessons('{"lessons": [1, 2]}') == []
    assert _parse_lessons('{"lessons": ["short"]}') == []  # below min length


def test_parse_lessons_caps_at_five():
    raw = '{"lessons": [' + ",".join(f'"lesson number {i} is quite long"' for i in range(8)) + "]}"
    assert len(_parse_lessons(raw)) == 5


def test_score_lesson_prefers_relevant():
    lesson_units = "Convert all units to SI before substituting into equations"
    lesson_organic = "For iodoform tests check for the methyl ketone group"
    message = "find the iodoform test result for the methyl ketone compound"
    assert score_lesson(lesson_organic, message) > score_lesson(lesson_units, message)


def test_select_lessons_caps_at_limit():
    lessons = [f"Lesson about topic {i} with plenty of words" for i in range(10)]
    assert len(select_lessons(lessons, "a physics question about motion")) <= 6


def test_system_prompt_with_lessons_appends_block():
    prompt = system_prompt_with_lessons("BASE", ["Always check units"])
    assert prompt.startswith("BASE")
    assert "Always check units" in prompt
    assert "adjusted my approach" in prompt
    assert system_prompt_with_lessons("BASE", []) == "BASE"


def test_fingerprint_changes_with_lessons_and_stable_order():
    a = fingerprint_lessons(["Always check units", "Re-derive results"])
    b = fingerprint_lessons(["Always check units"])
    assert a != b
    assert a == fingerprint_lessons(["Always check units", "Re-derive results"])
    assert fingerprint_lessons([]) == "none"


@pytest.mark.asyncio
async def test_store_lessons_dedupes():
    from app.database import SessionFactory, init_db
    from app.self_improve import store_lessons

    await init_db()  # create improvement_lessons in this test's temp DB
    lessons = ["Always verify unit conversions line by line before substituting",
               "Check limiting cases before finalizing any physics result"]
    first = await store_lessons(SessionFactory(), lessons, source="test")
    second = await store_lessons(SessionFactory(), lessons, source="test")
    variant = await store_lessons(
        SessionFactory(),
        ["always verify unit conversions  line by LINE before substituting"],
        source="test",
    )
    assert first == 2
    assert second == 0
    assert variant == 0
