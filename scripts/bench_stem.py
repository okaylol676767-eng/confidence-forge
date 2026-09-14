"""One-off benchmark: accuracy + latency of candidate Gemini models on STEM problems.

Run: .venv/Scripts/python scripts/bench_stem.py
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
    "Solve the problem carefully, step by step, checking your work. "
    "End your reply with a final line of exactly: FINAL: <answer>"
)

# (label, question, accepted answer substrings, is_regex)
PROBLEMS = [
    ("M1 integral", "Compute the exact value of the definite integral of 3x^2 with respect to x from 0 to 2.", ["8"], False),
    ("M2 extrema", "If f(x) = x^3 - 3x, find the x-coordinates of all local extrema of f.", [r"x\s*=\s*[-±]?\s*1.*x\s*=\s*[-±]?\s*1|±\s*1|-1,?\s*(and|,)\s*1|1,?\s*(and|,)\s*-1"], True),
    ("P1 range", "A projectile is launched at 20 m/s at 30 degrees above horizontal. Using g = 10 m/s^2, what is its range in meters? Give the numeric value.", ["34.6", "34.64", "20\\u221a3", "20sqrt(3)", "20 \u221a 3"], False),
    ("P2 speed", "A 2 kg block slides from rest down a frictionless incline of vertical height 5 m. Using g = 10 m/s^2, what is its speed at the bottom in m/s? Give the numeric value.", ["10 m/s", "= 10", "10 m/s^", "v = 10", "speed of 10"], False),
    ("C1 STP volume", "What volume in liters does 0.25 mol of an ideal gas occupy at STP (molar volume 22.4 L/mol)? Give the numeric value.", ["5.6"], False),
    ("C2 pH", "What is the pH of a 0.01 M HCl solution? Assume complete dissociation.", [r"\bpH\s*(of|=|is)?\s*2\b", "= 2\b", "pH 2"], True),
]

MODELS = [
    "gemini-flash-lite-latest",
    "gemini-3.1-flash-lite",
    "gemini-3.5-flash-lite",
    "gemini-3.5-flash",
]


def ask(model: str, question: str) -> tuple[str, float]:
    m = genai.GenerativeModel(model_name=model)
    t0 = time.time()
    try:
        resp = m.generate_content(
            f"{INSTRUCTION}\n\n{question}",
            request_options={"timeout": 120},
        )
        return (resp.text or ""), time.time() - t0
    except Exception as exc:  # noqa: BLE001
        return f"<<ERROR {type(exc).__name__}: {str(exc)[:120]}>>", time.time() - t0


def grade(text: str, accepted: list[str], is_regex: bool) -> bool:
    final = ""
    m = re.search(r"FINAL:\s*(.+)", text)
    if m:
        final = m.group(1).strip().lower()
    hay = (final + "\n" + text.lower())
    for a in accepted:
        if is_regex:
            if re.search(a.lower(), hay):
                return True
        elif a.lower() in hay:
            return True
    return False


def run_model(model: str) -> tuple[str, int, float, list[str]]:
    correct = 0
    total_lat = 0.0
    misses: list[str] = []
    for label, question, accepted, is_regex in PROBLEMS:
        text, lat = ask(model, question)
        total_lat += lat
        ok = not text.startswith("<<ERROR") and grade(text, accepted, is_regex)
        if ok:
            correct += 1
        else:
            misses.append(f"    {label}: {text[:160].replace(chr(10), ' / ')}")
    return model, correct, total_lat / len(PROBLEMS), misses


def main() -> None:
    print(f"{'model':<28}{'score':<9}{'avg lat':<10}")
    print("-" * 47)
    with ThreadPoolExecutor(max_workers=4) as pool:
        for model, correct, avg_lat, misses in pool.map(run_model, MODELS):
            print(f"{model:<28}{correct}/6      {avg_lat:6.1f}s")
            for miss in misses:
                print(miss)
            print(flush=True)


if __name__ == "__main__":
    main()
