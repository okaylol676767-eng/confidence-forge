"""Fully automated self-improvement loop.

Every IMPROVE_INTERVAL_SECONDS the scheduler:

1. COLLECT — gathers what went wrong from two sources:
   - PRISM traces (third-party quality signals: response_quality,
     customer_satisfaction, flag_for_review, guardrail_flags) via the
     PRISM read API; only traces newer than the last harvest are read.
   - the local interactions log (low-confidence answers below the
     threshold, which the explicit-logging contract already stores).
2. SYNTHESIZE — one LLM call turns the failure evidence into concrete,
   general lessons ("When asked X, do Y") — never row-specific text.
3. STORE — lessons are kept in the ``improvement_lessons`` table with a
   source tag and a content hash; identical lessons are never duplicated.
4. INJECT — at chat time the most relevant active lessons are placed in
   the system prompt, and — per the transparency contract — the model is
   told to SAY when a lesson changed how it answered ("I've adjusted my
   approach on this topic after earlier uncertainty").

Failure policy: every stage fails open. A broken PRISM pull, a bad LLM
response, or a DB hiccup logs a warning and waits for the next cycle;
chat never depends on the loop running.
"""
import asyncio
import hashlib
import json
import os
import re

import httpx
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from .config import get_logger, get_settings
from .database import SessionFactory
from .models import ImprovementLesson, Interaction

logger = get_logger("self_improve")
settings = get_settings()

PRISM_HOST = (os.environ.get("PRISMTRACE_HOST", "").strip()
              or "https://prism-api-prod.up.railway.app")
MAX_LESSONS_IN_PROMPT = settings.lessons_in_prompt

# Verbatim user text never enters a lesson; this bounds the quoted fragment.
MAX_EVIDENCE_CHARS = 160


def _evidence(text: str | None, limit: int = MAX_EVIDENCE_CHARS) -> str:
    return (text or "").strip().replace("\n", " ")[:limit]


# --------------------------------------------------------------------------
# 1. COLLECT — PRISM traces + local low-confidence log
# --------------------------------------------------------------------------

class _HarvestedTrace:
    """Normalized quality signal from one PRISM trace."""

    __slots__ = ("trace_id", "quality", "satisfaction", "flagged",
                 "guardrails", "intent")

    def __init__(self, raw: dict) -> None:
        eval_block = raw.get("evaluation") or {}
        self.trace_id = str(raw.get("trace_id") or raw.get("id") or "")
        try:
            self.quality = eval_block.get("response_quality")
        except AttributeError:
            self.quality = None
        self.satisfaction = eval_block.get("customer_satisfaction")
        self.flagged = bool(eval_block.get("flag_for_review"))
        flags = raw.get("guardrail_flags")
        self.guardrails = flags if isinstance(flags, list) else None
        self.intent = eval_block.get("intent_detected")


def _prism_credentials() -> tuple[str, str] | None:
    api_key = os.environ.get("PRISMTRACE_API_KEY", "").strip()
    project_id = os.environ.get("PRISMTRACE_PROJECT_ID", "").strip()
    return (api_key, project_id) if api_key and project_id else None


def _parse_since(created_at: str | None) -> str | None:
    """Keep only the datetime part PRISM's ISO format understands."""
    if not created_at:
        return None
    match = re.match(r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}", created_at)
    return match.group(0) if match else None


async def fetch_prism_signals(since: str | None) -> tuple[list[_HarvestedTrace], str | None]:
    """Pull recent traces from PRISM's read API. Returns (signals, newest_created_at)."""
    creds = _prism_credentials()
    if creds is None:
        return [], None
    api_key, project_id = creds
    params: dict[str, str | int] = {"project_id": project_id, "page_size": 100}
    since_dt = _parse_since(since)
    if since_dt:
        params["created_after"] = since_dt
    headers = {"X-PRISMtrace-Key": api_key}
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(
            f"{PRISM_HOST}/api/traces", params=params, headers=headers
        )
        resp.raise_for_status()
        payload = resp.json()
    traces = payload.get("traces") or []
    signals: list[_HarvestedTrace] = []
    newest: str | None = since
    for raw in traces:
        signal = _HarvestedTrace(raw)
        if signal.quality is not None or signal.flagged or signal.guardrails:
            signals.append(signal)
        created = raw.get("created_at")
        if created and created > (newest or ""):
            newest = created
    return signals, newest


async def fetch_low_confidence(session: AsyncSession) -> list[Interaction]:
    """Recent locally-logged low-confidence answers (the explicit contract)."""
    result = await session.execute(
        select(Interaction)
        .where(Interaction.confidence < settings.low_confidence_threshold)
        .order_by(Interaction.created_at.desc())
        .limit(20)
    )
    return list(result.scalars().all())


# --------------------------------------------------------------------------
# 2. SYNTHESIZE — failure evidence -> general lessons (one LLM call)
# --------------------------------------------------------------------------

def build_synthesis_messages(
    evidence_blocks: list[str],
    existing_lessons: list[str],
) -> list[dict[str, str]]:
    existing = "\n".join(f"- {lesson}" for lesson in existing_lessons) or "(none yet)"
    evidence = "\n\n".join(evidence_blocks) or "(no recent failures)"
    instruction = (
        "You are the self-improvement module of SPIRAL, a STEM tutor AI. "
        "Below is recent evidence of its failures: PRISM quality evaluations "
        "(response_quality / 100 and customer_satisfaction / 100, review flags, "
        "guardrail flags) and locally logged low-confidence answers. Identify "
        "the RECURRING mistakes and distill them into at most 5 concrete, "
        "durable lessons that would prevent those mistakes in future answers.\n\n"
        "Context you must apply: SPIRAL is an EXAM-TUTORING assistant — users "
        "send homework and competition (JEE) problems, so most turns are "
        "problem-solving, not customer service. PRISM's evaluator scores "
        "against a customer-service rubric and sometimes flags turns with "
        "reasons like 'not a customer service conversation' or 'answers "
        "questions the user did not ask' on attachment turns. Do NOT treat "
        "that framing itself as a failure of the answer; learn only from "
        "genuine correctness/completeness failures (wrong result, missed "
        "sub-parts, invented file content, unit errors).\n\n"
        "Rules for each lesson:\n"
        "- One sentence, general and reusable (a rule of method), NOT a summary "
        "of one specific question.\n"
        "- Actionable: 'Verify unit conversions line by line before finalizing' "
        "— not 'unit errors happened'.\n"
        "- Never quote user text verbatim, never mention trace ids.\n\n"
        'Reply with ONE JSON object: {"lessons": ["...", "..."]}. '
        "If the evidence is too thin to justify any lesson, reply {\"lessons\": []}."
    )
    body = (
        f"ALREADY-KNOWN LESSONS (do not repeat these):\n{existing}\n\n"
        f"FAILURE EVIDENCE:\n{evidence}"
    )
    return [
        {"role": "system", "content": "You are a rigorous AI improvement analyst."},
        {"role": "user", "content": f"{instruction}\n\n{body}"},
    ]


def _parse_lessons(raw: str) -> list[str]:
    """Extract the lessons array; anything malformed yields []."""
    try:
        start = raw.index("{")
        end = raw.rindex("}") + 1
        data = json.loads(raw[start:end])
    except (ValueError, json.JSONDecodeError):
        return []
    items = data.get("lessons") if isinstance(data, dict) else None
    if not isinstance(items, list):
        return []
    cleaned: list[str] = []
    for item in items:
        if not isinstance(item, str):
            continue
        lesson = " ".join(item.split()).strip()
        if 15 <= len(lesson) <= 300:
            cleaned.append(lesson)
    return cleaned[:5]


def lesson_hash(text: str) -> str:
    normalized = " ".join(text.lower().split())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:32]


# --------------------------------------------------------------------------
# 3. STORE — deduplicated lesson rows
# --------------------------------------------------------------------------

async def dedupe_against_existing(
    session: AsyncSession, candidates: list[str]
) -> list[str]:
    """Drop candidates whose content hash (or normalized text) already exists."""
    if not candidates:
        return []
    hashes = [lesson_hash(c) for c in candidates]
    rows = (await session.execute(
        select(ImprovementLesson.text_hash).where(
            ImprovementLesson.text_hash.in_(hashes)
        )
    )).scalars().all()
    known_hashes = set(rows)
    normalized = {
        " ".join(r.lower().split()) for r in (await session.execute(
            select(ImprovementLesson.lesson)
        )).scalars().all()
    }
    fresh: list[str] = []
    seen_this_batch: set[str] = set()
    for candidate in candidates:
        h = lesson_hash(candidate)
        norm = " ".join(candidate.lower().split())
        if h in known_hashes or norm in normalized or norm in seen_this_batch:
            continue
        seen_this_batch.add(norm)
        fresh.append(candidate)
    return fresh


async def store_lessons(session: AsyncSession, lessons: list[str], source: str) -> int:
    fresh = await dedupe_against_existing(session, lessons)
    for lesson in fresh:
        session.add(ImprovementLesson(
            lesson=lesson, source=source, text_hash=lesson_hash(lesson),
        ))
    await session.commit()
    return len(fresh)


async def store_lessons_standalone(lessons: list[str], source: str) -> int:
    """Store lessons outside the request cycle (bench scripts, scheduler)."""
    if not lessons:
        return 0
    async with SessionFactory() as session:
        return await store_lessons(session, lessons, source=source)


# --------------------------------------------------------------------------
# 4. INJECT — relevant lessons into the chat system prompt
# --------------------------------------------------------------------------

def _keywords(text: str) -> set[str]:
    stop = {
        "the", "a", "an", "and", "or", "of", "to", "in", "on", "for", "with",
        "is", "are", "was", "were", "be", "been", "when", "if", "that", "this",
        "it", "its", "as", "at", "by", "from", "your", "you", "always", "never",
        "before", "after", "answer", "answers", "question", "questions",
    }
    words = re.findall(r"[a-z]{3,}", text.lower())
    return {w for w in words if w not in stop}


def score_lesson(lesson_text: str, message: str) -> int:
    """Cheap relevance: keyword overlap between lesson and the user message.
    Score 0 lessons are still injected when slots remain (all lessons are
    global behavioural rules), relevance only orders them."""
    lesson_words = _keywords(lesson_text)
    message_words = _keywords(message)
    return len(lesson_words & message_words)


def build_lesson_block(lessons: list[str]) -> str:
    listed = "\n".join(f"- {lesson}" for lesson in lessons)
    return (
        "LEARNED LESSONS (from automated review of past answers):\n"
        f"{listed}\n"
        "Apply the relevant ones to this answer. If a lesson changed how you "
        "handled this question compared with a naive answer, add ONE short "
        'line to the END of "answer" of the exact form: "(I\'ve adjusted my '
        'approach on this after reviewing earlier mistakes.)" — only when a '
        "lesson genuinely applied, never for routine arithmetic or greetings."
    )


def select_lessons(lessons: list[str], message: str) -> list[str]:
    ranked = sorted(
        lessons, key=lambda text: score_lesson(text, message), reverse=True
    )
    return ranked[:MAX_LESSONS_IN_PROMPT]


def fingerprint_lessons(lessons: list[str]) -> str:
    """Stable id of the lesson set — used to version answer-cache keys so a
    new lesson invalidates cached answers produced without it."""
    return "|".join(lesson_hash(lesson) for lesson in lessons) or "none"


def system_prompt_with_lessons(system_prompt: str, lessons: list[str]) -> str:
    if not lessons:
        return system_prompt
    return f"{system_prompt.rstrip()}\n\n{build_lesson_block(lessons)}"


async def get_active_lessons(session: AsyncSession) -> list[str]:
    result = await session.execute(
        select(ImprovementLesson.lesson)
        .where(ImprovementLesson.is_active.is_(True))
        .order_by(ImprovementLesson.created_at.desc())
        .limit(30)
    )
    return list(result.scalars().all())


# --------------------------------------------------------------------------
# The loop: one cycle + the background scheduler
# --------------------------------------------------------------------------

async def collect_and_store_lessons(llm_client, session: AsyncSession) -> int:
    """One full collect -> synthesize -> store pass. Returns lessons stored."""
    prism_signals, newest = await fetch_prism_signals(_load_last_prism_ts())
    low_conf = await fetch_low_confidence(session)

    evidence: list[str] = []
    for signal in prism_signals[:15]:
        parts = [f"trace {signal.trace_id}"]
        if signal.quality is not None:
            parts.append(f"response_quality={signal.quality}/100")
        if signal.satisfaction is not None:
            parts.append(f"satisfaction={signal.satisfaction}/100")
        if signal.flagged:
            parts.append("FLAGGED for review")
        if signal.guardrails:
            parts.append(f"guardrail_flags={signal.guardrails}")
        if signal.intent:
            parts.append(f"intent={signal.intent}")
        evidence.append("; ".join(parts))
    for row in low_conf[:10]:
        factors = row.uncertainty_factors or ""
        evidence.append(
            f"local low-confidence answer (confidence={row.confidence:.2f}, "
            f"prompt {row.prompt_version}): question topic: {_evidence(row.user_message)} | "
            f"uncertainty factors: {_evidence(factors)}"
        )

    if not evidence:
        logger.info("self-improve: no failure evidence this cycle")
        return 0

    existing = await get_active_lessons(session)
    messages = build_synthesis_messages(evidence, existing)
    raw = await llm_client.complete(messages)
    lessons = _parse_lessons(raw)
    if not lessons:
        logger.info("self-improve: synthesis produced no new lessons")
        _save_last_prism_ts(newest)
        return 0

    stored = await store_lessons(session, lessons, source="auto")
    _save_last_prism_ts(newest)
    logger.info(
        "self-improve: evidence=%d prism=%d lowconf=%d synthesized=%d stored=%d",
        len(evidence), len(prism_signals), len(low_conf), len(lessons), stored,
    )
    return stored


def _state_path() -> str:
    return os.environ.get("SELF_IMPROVE_STATE_PATH", ".freebuff/self_improve_state.json")


def _load_last_prism_ts() -> str | None:
    try:
        with open(_state_path(), encoding="utf-8") as fh:
            return json.load(fh).get("last_prism_ts")
    except (OSError, json.JSONDecodeError, AttributeError):
        return None


def _save_last_prism_ts(ts: str | None) -> None:
    if not ts:
        return
    path = _state_path()
    try:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump({"last_prism_ts": ts}, fh)
    except OSError:
        logger.warning("self-improve: could not persist PRISM cursor", exc_info=True)


async def improvement_cycle(llm_client) -> int:
    """One scheduled cycle on its own DB session. Never raises."""
    try:
        async with SessionFactory() as session:
            return await collect_and_store_lessons(llm_client, session)
    except Exception:
        logger.warning("self-improve: cycle failed (will retry next interval)",
                       exc_info=True)
        return 0


async def _scheduler_loop(llm_client, interval: float) -> None:
    while True:
        await asyncio.sleep(interval)
        await improvement_cycle(llm_client)


def start_self_improve(llm_client, interval: float | None = None) -> asyncio.Task | None:
    """Launch the background improvement loop. Returns None when disabled."""
    if not settings.self_improve_enabled:
        logger.info("Self-improvement loop disabled")
        return None
    seconds = float(interval or settings.self_improve_interval_seconds)
    logger.info("Self-improvement loop started (interval=%ss)", seconds)
    return asyncio.get_running_loop().create_task(_scheduler_loop(llm_client, seconds))
