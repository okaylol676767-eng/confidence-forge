"""Discrimination test: competition-level STEM, lite vs thinking flash.

Run: .venv/Scripts/python scripts/bench_stem_competition.py
"""
import os
import re
import time
import warnings
from concurrent.futures import ThreadPoolExecutor

warnings.filterwarnings("ignore")
from dotenv import load_dotenv

load_dotenv(".env")
import google.generativeai as genai

genai.configure(api_key=os.environ["GEMINI_API_KEY"])

INSTRUCTION = (
    "Solve the problem carefully, step by step, verifying each step. "
    "End your reply with a final line of exactly: FINAL: <answer>"
)

PROBLEMS = [
    (
        "N1 last-two-digits",
        "Find the last two digits of 7^2025 (in decimal).",
        [r"\b07\b", r"\b7\b"],
    ),
    (
        "N2 rolling sphere",
        "A solid sphere rolls without slipping down an incline. What fraction of its total kinetic energy is rotational? Give the exact fraction.",
        [r"2/7", r"0\.28[56]"],
    ),
    (
        "N3 adiabatic expansion",
        "One mole of a monatomic ideal gas at 300 K expands adiabatically and reversibly to 8 times its initial volume. Find the final temperature in kelvin (gamma = 5/3).",
        [r"\b75\b"],
    ),
]

MODELS = ["gemini-flash-lite-latest", "gemini-3.5-flash"]


def ask(model: str, question: str) -> tuple[str, float]:
    t0 = time.time()
    try:
        resp = genai.GenerativeModel(model_name=model).generate_content(
            f"{INSTRUCTION}\n\n{question}", request_options={"timeout": 150}
        )
        return (resp.text or ""), time.time() - t0
    except Exception as exc:  # noqa: BLE001
        return f"<<ERROR {type(exc).__name__}: {str(exc)[:90]}>>", time.time() - t0


def grade(text: str, patterns: list[str]) -> bool:
    if text.startswith("<<ERROR"):
        return False
    m = re.search(r"FINAL:\s*(.+)", text)
    final = m.group(1).strip().lower() if m else ""
    return any(re.search(p, final) or re.search(p, text.lower()) for p in patterns)


def run_model(model: str) -> None:
    correct = 0
    total = 0.0
    for label, q, patterns in PROBLEMS:
        text, lat = ask(model, q)
        total += lat
        ok = grade(text, patterns)
        correct += ok
        if not ok:
            print(f"    [{model}] {label} MISSED ({lat:.0f}s): {text[:130]!r}", flush=True)
    print(f"{model:<26}{correct}/3      {total/len(PROBLEMS):6.1f}s", flush=True)


if __name__ == "__main__":
    print(f"{'model':<26}{'score':<8}{'avg lat':<9}")
    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(run_model, MODELS))
