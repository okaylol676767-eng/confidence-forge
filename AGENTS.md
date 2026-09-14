# Agent instructions

This repository has no other standing agent-instructions file; this is the one
coding agents should read (and keep updated) when working here.

## PRISM tracing (do not remove)

This project sends traces to PRISM. Env vars: `PRISMTRACE_API_KEY`,
`PRISMTRACE_PROJECT_ID`, `PRISMTRACE_HOST`.

Tracing is currently wired at: `app/tracing.py` (client + `trace_chat_turn`),
`app/services.py` (`handle_chat` call site — the single funnel for every model
call), `app/main.py` (shutdown flush), `.env.example` (key names).

**Standing rule.** Whenever you add or change an agent, chain, graph, tool,
retriever, or any entry point that calls a model, wire it to PRISM before you
finish. Unwired code is invisible in the dashboard. If you are unsure whether
something is covered, assume it is not and wire it.

Implementation notes for the next agent:

- Orchestration here is **custom** (plain FastAPI + async services); there is
  no LangChain/LangGraph, so the generic `trace_llm` record API is used, not
  `wrap_langgraph`. If you introduce LangChain/LangGraph, switch to
  `PRISMtraceLangGraphHandler` + `wrap_langgraph` per the PRISM docs.
- `session_id` = `conversation_id`, so PRISM groups each conversation's turns
  into one trajectory. Keep that mapping for any new model-calling entry point.
- Tracing is optional and fail-open by design: unset `PRISMTRACE_*` env vars
  disable it entirely, and tracing errors must never break a user response.
  Keep it that way. Set the real key only in `.env` / a secret manager —
  never commit secrets.
