# Confidence Forge

An AI chatbot that shows its own confidence after every answer — and actually uses those scores to improve itself over time.

Every answer comes back as structured JSON with a self-reported `confidence` score, every interaction is logged, and a `/improve` endpoint analyzes low-confidence answers and writes a new, versioned system prompt. A Next.js frontend ("SPIRAL") lives in `frontend/` and talks to this backend.

## Features

- **Transparent answers** — every response includes `confidence` (0–1), `confidence_reason`, and `uncertainty_factors`.
- **Images & document reading** — attach images, PDFs, or text files in the chat UI (paperclip) or via multipart `POST /chat`; Gemini sees them inline and answers about their content.
- **Two LLM providers** — Google Gemini (default) or any OpenAI-compatible API, selected by one env var.
- **Forced structured LLM output** — the LLM must return strict JSON; markdown fences / prose around the JSON are stripped automatically, and unusable output maps to a clean 502.
- **Full interaction logging** — SQLite (default) or PostgreSQL, with latency, prompt version, and timestamps.
- **Versioned system prompts** — v1 is seeded on startup; `/improve` writes v2, v3, … and can activate them.
- **Self-improvement loop** — `/improve` feeds low-confidence answers back to the LLM to rewrite the active prompt.
- **Consistent error envelope** — every error is `{"error": true, "message": "...", "code": "..."}`; stack traces and secrets never reach the client.
- **Next.js frontend included** — relative `/chat` fetches are proxied to the backend by a rewrite; no CORS setup needed.

## Quick start (backend + frontend together)

```bash
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements-dev.txt   # macOS/Linux: source .venv/bin/activate first

cp .env.example .env                   # then set GEMINI_API_KEY (or OPENAI_API_KEY)
cd frontend && npm install && cd ..

# one command: backend on :8000, frontend on :3000, proxy wired
.venv\Scripts\python scripts/dev.py
```

Then open **http://localhost:3000** → Launch → chat. The frontend posts to relative `/chat`, which Next.js proxies to the FastAPI server, so there is no CORS surface at all.

Run them separately if you prefer:

```bash
.venv\Scripts\python -m uvicorn app.main:app --reload      # API on :8000 (docs at /docs)
cd frontend && npm run dev                                  # UI on :3000
```

## Configuration (env vars / `.env`)

The key is loaded from `.env` via `python-dotenv` — never commit it (`.env` is gitignored).

| Variable | Default | Purpose |
|---|---|---|
| `LLM_PROVIDER` | `gemini` | `gemini` or `openai` |
| `GEMINI_API_KEY` | — | Google AI Studio key (get one at aistudio.google.com) |
| `GEMINI_MODEL` | `gemini-flash-lite-latest` | Model name — see note below |
| `OPENAI_API_KEY` | — | Key for any OpenAI-compatible provider |
| `OPENAI_BASE_URL` | `https://api.openai.com/v1` | Groq, Ollama, vLLM, … |
| `LLM_MODEL` | `gpt-4o-mini` | Model name (OpenAI provider) |
| `LLM_TEMPERATURE` / `LLM_MAX_TOKENS` | `0.2` / `800` | Generation parameters |
| `LLM_TIMEOUT_SECONDS` / `LLM_MAX_RETRIES` | `30` / `2` | Request timeout and retry count |
| `LLM_JSON_MODE` | `true` | Request native JSON mode (disable for picky providers) |
| `ANSWER_CACHE_ENABLED` | `true` | Serve identical repeat questions (no history/files) from an in-process cache — single-digit-ms responses |
| `ANSWER_CACHE_SIZE` | `1024` | Max cached questions (LRU eviction) |
| `ANSWER_CACHE_TTL_SECONDS` | `3600` | Cache entry lifetime |
| `MAX_HISTORY_TURNS` | `10` | Previous exchanges replayed to the model |
| `LOW_CONFIDENCE_THRESHOLD` | `0.7` | What counts as "low confidence" |
| `IMPROVE_SAMPLE_LIMIT` | `200` | Max rows analyzed per `/improve` run |
| `DATABASE_URL` | `sqlite+aiosqlite:///./confidence_forge.db` | Use `postgresql+asyncpg://...` for PostgreSQL |
| `CORS_ORIGINS` | localhost dev ports | Comma-separated allowed origins (only needed for non-proxied cross-origin frontends) |
| `NEXT_PUBLIC_API_ORIGIN` | `http://127.0.0.1:8000` | Backend origin the Next.js proxy targets (rebuild after changing) |

> **Model note:** `gemini-1.5-flash` has been retired by Google (404 on the v1beta endpoint).
> The default is `gemini-flash-lite-latest`, an alias that always tracks the current *lite* flash
> model — fast, cheap, and no "thinking" phase. Avoid `gemini-flash-latest` for this chat
> contract: its thinking mode routinely exceeds 30s on math/reasoning prompts and hits the
> request timeout. Pin any specific version with `GEMINI_MODEL=<name>` if you prefer.

## API

### `POST /chat`

Text-only (JSON):

```json
{ "message": "What is the capital of France?", "conversation_id": "optional" }
```

**With attachments** — send `multipart/form-data` with the same fields plus one or more
`files` parts. Supported: images (png/jpg/webp/heic/heif), PDF, txt, md, csv, json —
max 4 files, 8 MB each, 16 MB total. Attachment-only sends (empty message) are allowed;
a default "analyze this file" prompt is supplied. Files are forwarded to Gemini as
inline parts (vision/document understanding); only their **metadata** is persisted.

```bash
curl -X POST http://localhost:8000/chat \
  -F "message=What do you see?" \
  -F "files=@photo.png;type=image/png"
```

Response (identical shape; `attachments` echoes file metadata):

```json
{
  "conversation_id": "c-1a2b3c4d5e6f",
  "interaction_id": 1,
  "prompt_version": "v1",
  "latency_ms": 812,
  "answer": "Paris is the capital of France.",
  "confidence": 0.98,
  "confidence_reason": "Well-established fact.",
  "uncertainty_factors": [],
  "attachments": [
    { "filename": "photo.png", "mime_type": "image/png", "size_bytes": 1234, "kind": "image" }
  ]
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
| `LLM_UNAVAILABLE` | 503 | Provider unreachable (network/DNS) |
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
.venv\Scripts\python -m pytest -q      # Windows
python -m pytest -q                    # macOS/Linux
```

44 tests cover the chat flow, history, stats, improvement, both LLM providers, and every error path (malformed LLM JSON, timeouts, blocked responses, validation, unknown conversations) using deterministic fakes — no API key needed and no network access.

Offline smoke check (no key required): `python scripts/smoke_test.py`
Live Gemini check (requires a key in `.env`): `python scripts/live_gemini_check.py`

## Project layout

```
app/
  main.py          # app factory: CORS, exception handlers, lifespan
  config.py        # env-driven settings (python-dotenv)
  schemas.py       # Pydantic request/response models
  errors.py        # typed errors + error codes
  database.py      # async engine/session (SQLite or PostgreSQL)
  models.py        # ORM: interactions, prompt_versions
  llm.py           # OpenAI-compatible client
  llm_gemini.py    # Gemini client (google-generativeai)
  llm_factory.py   # provider selection from settings
  llm_json.py      # shared strict-JSON extraction/validation
  prompts.py       # versioned prompt registry (DB-backed)
  services.py      # chat/history/stats business logic
  improve.py       # self-improvement flow
  routers/         # thin HTTP layer
frontend/          # Next.js "SPIRAL" UI (proxies API calls via rewrites)
tests/             # pytest suite (fake LLMs, offline)
scripts/dev.py     # run backend + frontend together
scripts/smoke_test.py
scripts/live_gemini_check.py
```
