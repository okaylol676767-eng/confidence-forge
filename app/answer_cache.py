"""In-process exact-match answer cache for repeat questions.

A live LLM call physically cannot answer in single-digit milliseconds —
network + inference is seconds. What CAN is a cached answer to a question
the model has already answered identically. This cache makes repeat
questions instant (honest ~1-10ms traces, lower spend) without ever
risking a wrong answer:

- Only EXACT matches (casefold + whitespace-collapsed) hit. No fuzzy
  matching: "What is 7 x 8?" and "what is 7x8?" hit, "7 x 9" never does.
- Only cacheable turns participate: no attachments, and no conversation
  history (a follow-up like "and why?" must reach the model with context).
- Entries expire (TTL) and the cache is size-bounded (LRU).
- Fully optional: disable with ANSWER_CACHE_ENABLED=false.
"""
import re
import time
from collections import OrderedDict
from dataclasses import dataclass

from .config import get_logger, get_settings
from .schemas import StructuredAnswer

logger = get_logger("answer_cache")
settings = get_settings()

_WHITESPACE_RE = re.compile(r"\s+")


def normalize_question(message: str) -> str:
    """Canonical text form for exact matching (case/spacing-insensitive)."""
    return _WHITESPACE_RE.sub(" ", (message or "").strip().casefold())


@dataclass(frozen=True)
class _Entry:
    answer: StructuredAnswer
    prompt_version: str
    # Provider-reported (input, output) tokens of the call that produced this
    # answer. Replayed on hits so observability dashboards see the true cost
    # of the turn even when it was served from cache.
    token_usage: tuple[int, int] | None
    expires_at: float


class AnswerCache:
    """Tiny TTL + LRU cache: question (+ prompt version) -> StructuredAnswer."""

    def __init__(self, max_size: int, ttl_seconds: float) -> None:
        self._max_size = max(1, int(max_size))
        self._ttl = float(ttl_seconds)
        self._entries: OrderedDict[str, _Entry] = OrderedDict()
        self.hits = 0
        self.misses = 0

    @staticmethod
    def make_key(prompt_version: str, message: str) -> str:
        return f"{prompt_version}::{normalize_question(message)}"

    def get(self, key: str) -> tuple[StructuredAnswer, tuple[int, int] | None] | None:
        entry = self._entries.get(key)
        if entry is None:
            self.misses += 1
            return None
        if entry.expires_at < time.monotonic():
            # Expired: drop it and count a miss.
            self._entries.pop(key, None)
            self.misses += 1
            return None
        self._entries.move_to_end(key)  # LRU refresh
        self.hits += 1
        return entry.answer, entry.token_usage

    def put(
        self,
        key: str,
        answer: StructuredAnswer,
        prompt_version: str,
        token_usage: tuple[int, int] | None = None,
    ) -> None:
        self._entries[key] = _Entry(
            answer=answer,
            prompt_version=prompt_version,
            token_usage=token_usage,
            expires_at=time.monotonic() + self._ttl,
        )
        self._entries.move_to_end(key)
        while len(self._entries) > self._max_size:
            self._entries.popitem(last=False)  # evict least-recently-used

    def clear(self) -> None:
        self._entries.clear()

    def __len__(self) -> int:
        return len(self._entries)


def cacheable_turn(*, message: str, history_count: int, attachment_count: int) -> bool:
    """A turn may be served/stored only when context cannot change the answer."""
    return bool((message or "").strip()) and history_count == 0 and attachment_count == 0


# Module-level singleton used by services.
answer_cache = AnswerCache(
    max_size=settings.answer_cache_size,
    ttl_seconds=settings.answer_cache_ttl_seconds,
) if settings.answer_cache_enabled else None
