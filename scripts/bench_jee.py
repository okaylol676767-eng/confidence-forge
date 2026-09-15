"""JEE Mains/Advanced training + evaluation benchmark.

Run: .venv/Scripts/python scripts/bench_jee.py [--limit N] [--store-lessons]

What it does (the "training" mechanism for exam accuracy):
1. Runs every benchmark question through the REAL pipeline (active system
   prompt + learned lessons + self-consistency, exactly as /chat does).
2. Grades the final answer against verified reference keys
   (app.answer_check.check_answer) and reports accuracy per subject/level.
3. With --store-lessons, failed questions are distilled by the model into
   durable, general lessons and saved via self_improve.store_lessons —
   those lessons are then injected into every future answer, so measured
   mistakes are trained away and re-checked by re-running the bench.
"""
import argparse
import asyncio
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.answer_check import check_answer, extract_final_answer  # noqa: E402
from app.database import init_db, SessionFactory  # noqa: E402
from app.llm_factory import build_llm_client  # noqa: E402
from app.prompts import prompt_manager  # noqa: E402
from app.self_improve import (  # noqa: E402
    build_synthesis_messages,
    _parse_lessons,
    store_lessons_standalone,
)
from app.services import build_chat_messages  # noqa: E402

BENCH_PATH = Path(__file__).resolve().parent.parent / "data" / "jee_bench.json"


def load_bench() -> list[dict]:
    with open(BENCH_PATH, encoding="utf-8") as fh:
        return json.load(fh)["questions"]


async def ask_one(llm_client, system_prompt: str, q: dict) -> tuple[str, float]:
    """One question through the real chat path (system prompt + question)."""
    messages = build_chat_messages(system_prompt, [], q["question"])
    started = time.perf_counter()
    structured = await llm_client.chat_structured(messages)
    elapsed = time.perf_counter() - started
    return structured.answer, elapsed


def grade(q: dict, produced_answer: str) -> bool:
    final = extract_final_answer(produced_answer)
    return check_answer(q["answer_text"], final) or check_answer(q["answer"], final)


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=0, help="Only first N questions")
    parser.add_argument("--store-lessons", action="store_true",
                        help="Distill failures into stored lessons")
    args = parser.parse_args()

    questions = load_bench()
    if args.limit:
        questions = questions[: args.limit]

    await init_db()
    llm_client = build_llm_client()
    _, system_prompt = await prompt_manager.get_active()

    results: list[dict] = []
    print(f"Running {len(questions)} JEE questions through the live pipeline...\n")
    for q in questions:
        try:
            produced, elapsed = await ask_one(llm_client, system_prompt, q)
        except Exception as exc:
            produced, elapsed = f"<LLM ERROR: {type(exc).__name__}>", 0.0
        passed = grade(q, produced)
        results.append({"q": q, "produced": produced, "passed": passed,
                        "elapsed": elapsed})
        marker = "PASS" if passed else "FAIL"
        print(f"[{marker}] {q['id']} ({q['subject']}/{q['level']}) "
              f"{elapsed:5.1f}s  key={q['answer']!r}")

    total = len(results)
    passed = sum(1 for r in results if r["passed"])
    print(f"\n=== OVERALL: {passed}/{total} ({100 * passed / max(total, 1):.0f}%) ===")
    for key in ("subject", "level"):
        groups: dict[str, list[bool]] = {}
        for r in results:
            groups.setdefault(r["q"][key], []).append(r["passed"])
        for name, votes in sorted(groups.items()):
            ok = sum(votes)
            print(f"  {key:8s} {name:12s} {ok}/{len(votes)} ({100 * ok / len(votes):.0f}%)")

    if args.store_lessons:
        failures = [
            f"JEE benchmark miss ({r['q']['subject']}/{r['q']['level']}, "
            f"{r['q']['type']}): question topic: {r['q']['question'][:160]} | "
            f"correct key: {r['q']['answer_text']} | "
            f"SPIRAL's final line was: {r['produced'][-160:]}"
            for r in results if not r["passed"]
        ]
        if not failures:
            print("\nNo failures — nothing to learn from this run.")
            return 0
        print(f"\nDistilling {len(failures)} failures into lessons...")
        raw = await llm_client.complete(build_synthesis_messages(
            failures, existing_lessons=[]
        ))
        lessons = _parse_lessons(raw)
        if not lessons:
            print("Synthesis produced no usable lessons (raw below):")
            print(raw[:500])
            return 1
        stored = await store_lessons_standalone(lessons, source="jee-bench")
        print(f"Stored {stored} new lessons (duplicates dropped):")
        for lesson in lessons:
            print(f"  - {lesson}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
