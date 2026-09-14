"""In-process smoke test: boots the app with TestClient and exercises every endpoint.

Run with: .venv/Scripts/python scripts/smoke_test.py
"""
import os
import sys
import tempfile

# Isolated temp DB so this never touches the dev database.
_TMP = tempfile.mkdtemp(prefix="cf_smoke_")
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{_TMP}/smoke.db"
# Keep the smoke test offline: force the OpenAI provider with no key -> LLM_NOT_CONFIGURED.
os.environ["LLM_PROVIDER"] = "openai"
os.environ["OPENAI_API_KEY"] = ""  # intentionally empty -> LLMNotConfigured path

import json  # noqa: E402
import sys  # noqa: E402
from pathlib import Path  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient  # noqa: E402

import app.main as main_module  # noqa: E402


def show(label: str, resp) -> None:
    print(f"--- {label} -> {resp.status_code}")
    try:
        print(json.dumps(resp.json(), indent=2)[:600])
    except Exception:
        print(resp.text[:300])


def main() -> None:
    with TestClient(main_module.app) as client:
        show("GET /health", client.get("/health"))
        show("GET /stats/summary (empty)", client.get("/stats/summary"))
        show("POST /chat (no API key)", client.post("/chat", json={"message": "hi"}))
        show("POST /chat (empty message)", client.post("/chat", json={"message": "   "}))
        show("GET /conversations/c-nope", client.get("/conversations/c-nope"))
        show("POST /improve (nothing to improve)", client.post("/improve", json={}))

    print("\nSmoke test complete.")


if __name__ == "exit_marker":  # defensive: never auto-run under import
    sys.exit(1)

if __name__ == "__main__":
    main()
