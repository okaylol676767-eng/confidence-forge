# Confidence Forge

An AI chatbot that shows its own confidence after every answer — and actually uses those scores to improve itself over time.

This repository contains the FastAPI backend: every answer comes back as structured JSON with a self-reported `confidence` score, every interaction is logged, and a `/improve` endpoint analyzes low-confidence answers and writes a new, versioned system prompt.

## Features

- **Transparent answers** — every response includes `confidence` (0–1), `confidence_reason`, and `uncertainty_factors`.
- **Forced structured LLM output** — the LLM must return strict JSON; malformed output is caught and mapped to a clean 502 error.
- **Full interaction logging** — SQLite (default) or PostgreSQL, with latency, prompt version, and timestamps.
- **Versioned system prompts** — v1 is seeded on startup; `/improve` writes v2, v3, … and can activate them.
- **Self-improvement loop** — `/improve` feeds low-confidence answers back to the LLM to rewrite the active prompt.
- **Consistent error envelope** — every error is `{"error": true, "message": "...", "code": "..."}`; stack traces and secrets never reach the client.

## Quick start

```bash
python -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt

cp .env.example .env                 # then set OPENAI_API_KEY (any OpenAI-compatible provider)
uvicorn app.main:app --reload
```

- Interactive docs: http://127.0.0.1:8000/docs
- Health check: http://127.0.0.1:8000/health

## Configuration (env vars / `.env`)

| Variable | Default | Purpose |
|---|---|---|
| `OPENAI_API_KEY` | — | API key for the LLM provider (required for chat) |
| `OPENAI_BASE_URL` | `https://api.openai.com/v1` | Any OpenAI-compatible endpoint (Groq, Ollama, vLLM, …) |
| `LLM_MODEL` | `gpt-4o-mini` | Model name |
| `LLM_TEMPERATURE` / `LLM_MAX_TOKENS` | `0.2` / `800` | Generation parameters |
| `LLM_TIMEOUT_SECONDS` / `LLM_MAX_RETRIES` | `30` / `2` | Request timeout and retry count |
| `LLM_JSON_MODE` | `true` | Request native JSON mode (disable for picky providers) |
| `MAX_HISTORY_TURNS` | `10` | Previous exchanges replayed to the model |
| `LOW_CONFIDENCE_THRESHOLD` | `0.7` | What counts as "low confidence" |
| `IMPROVE_SAMPLE_LIMIT` | `200` | Max rows analyzed per `/improve` run |
| `DATABASE_URL` | `sqlite+aiosqlite:///./confidence_forge.db` | Use `postgresql+asyncpg://...` for PostgreSQL |
| `CORS_ORIGINS` | localhost dev ports | Comma-separated allowed origins |

## API

### `POST /chat`

```json
{ "message": "What is the capital of France?", "conversation_id": "optional" }
```

Response:

```json
{
  "conversation_id": "c-1a2b3c4d5e6f",
  "interaction_id": 1,
  "prompt_version": "v1",
  "latency_ms": 812,
  "answer": "Paris is the capital of France.",
  "confidence": 0.98,
  "confidence_reason": "Well-established fact.",
  "uncertainty_factors": []
}
```

### `GET /conversations/{conversation_id}`

Full history as alternating user/assistant messages (assistant messages carry confidence metadata). 404 if unknown.

### `GET /stats/summary`

`total_interactions`, `average_confidence`, `low_confidence_count` (below threshold), `average_latency_ms`, `conversations`, and a per-prompt-version breakdown for A/B comparison.

### `POST /improve`

Analyzes low-confidence interactions, asks the LLM to rewrite the active system prompt, stores it as the next version. Body: `{"activate": true}` (default) to switch immediately, or `false` to store for later comparison.

Also: `GET /prompts/versions` lists all stored prompt versions; `GET /health` for liveness.

### Error format

All errors use one envelope with correct status codes:

```json
{ "error": true, "message": "The LLM did not respond in time. Please retry.", "code": "LLM_TIMEOUT" }
```

| Code | Status | Meaning |
|---|---|---|
| `VALIDATION_ERROR` | 422 | Invalid request body (Pydantic) |
| `INVALID_REQUEST` | 400 | Semantically invalid (e.g. nothing to improve yet) |
| `NOT_FOUND` | 404 | Unknown conversation |
| `LLM_NOT_CONFIGURED` | 503 | Missing API key |
| `LLM_TIMEOUT` | 504 | Provider too slow |
| `LLM_RATE_LIMIT` | 429 | Provider rate limit |
| `LLM_UNAVAILABLE` | 503 | Provider unreachable |
| `LLM_BAD_RESPONSE` / `LLM_INVALID_OUTPUT` | 502 | Unusable/malformed LLM output |
| `DATABASE_ERROR` | 500 | Persistence failure |
| `INTERNAL_ERROR` | 500 | Unexpected server error |

## Self-improvement loop

1. Users chat; every interaction is logged with its confidence score.
2. `POST /improve` samples the lowest-confidence answers (most recent first).
3. The LLM critiques the active prompt against those failures and returns a new prompt.
4. The new prompt is stored as `vN` (with `parent_version`) and optionally activated.
5. `GET /stats/summary` compares average confidence per version to see what actually improved.

## Tests

```bash
.venv/Scripts/python -m pytest -q      # Windows
python -m pytest -q                    # macOS/Linux
```

28 tests cover the chat flow, history, stats, improvement, and every error path (malformed LLM JSON, timeouts, validation, unknown conversations) using a deterministic fake LLM — no API key needed.

Smoke check without a key: `python scripts/smoke_test.py`

## Project layout

```
app/
  main.py          # app factory: CORS, exception handlers, lifespan
  config.py        # env-driven settings
  schemas.py       # Pydantic request/response models
  errors.py        # typed errors + error codes
  database.py      # async engine/session (SQLite or PostgreSQL)
  models.py        # ORM: interactions, prompt_versions
  llm.py           # OpenAI-compatible client, strict JSON extraction/validation
  prompts.py       # versioned prompt registry (DB-backed)
  services.py      # chat/history/stats business logic
  improve.py       # self-improvement flow
  routers/         # thin HTTP layer
tests/             # pytest suite (fake LLM)
scripts/smoke_test.py
```
