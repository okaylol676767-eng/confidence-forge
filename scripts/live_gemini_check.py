"""Live one-shot verification of the Gemini integration (uses .env, never prints the key)."""
import os
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# Isolated temp DB so the live check never touches dev data.
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{tempfile.mkdtemp(prefix='cf_live_')}/live.db"

from dotenv import load_dotenv  # noqa: E402

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

provider = os.environ.get("LLM_PROVIDER", "")
model = os.environ.get("GEMINI_MODEL", "")
key_present = "yes" if os.environ.get("GEMINI_API_KEY") else "no"
print(f"provider={provider} model={model} key_present={key_present}")

from fastapi.testclient import TestClient  # noqa: E402

import app.main as main_module  # noqa: E402


def main() -> int:
    with TestClient(main_module.app) as client:
        started = time.perf_counter()
        resp = client.post(
            "/chat",
            json={"message": "What is the capital of France? Answer in one sentence.", "conversation_id": "c-live-check"},
        )
        wall = time.perf_counter() - started

        print(f"\nPOST /chat -> {resp.status_code} (wall {wall:.2f}s)")
        body = resp.json()
        print(repr(body)[:900])

        if resp.status_code != 200:
            return 1

        assert body["answer"], "answer must be non-empty"
        assert 0.0 <= body["confidence"] <= 1.0, "confidence must be in [0,1]"
        assert body["confidence_reason"], "confidence_reason must be non-empty"
        assert isinstance(body["uncertainty_factors"], list), "uncertainty_factors must be a list"
        assert body["latency_ms"] > 0
        assert body["conversation_id"] == "c-live-check"

        hist = client.get("/conversations/c-live-check")
        print(f"\nGET /conversations/c-live-check -> {hist.status_code}, messages={hist.json()['message_count']}")
        stats = client.get("/stats/summary")
        print(f"GET /stats/summary -> {stats.status_code}: {stats.json()['total_interactions']} interaction(s), "
              f"avg_confidence={stats.json()['average_confidence']}")
        print("\nLIVE CHECK PASSED: Gemini returned valid structured confidence data.")
        return 0


if __name__ == "__main__":
    sys.exit(main())
