"""Harder multi-step STEM benchmark: lite models vs thinking-capable flash.

Run: .venv/Scripts/python scripts/bench_stem_hard.py
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

PROBLEMS = [
    (
        "H1 exponential eq",
        "Solve for x: 2^(x+1) = 3^x. Give x rounded to 3 decimal places.",
        [r"1\.7(09|10|11)"],
        True,
    ),
    (
        "H2 pulley accel",
        "A 5 kg block on a frictionless 30-degree incline is connected by a light string over an ideal pulley to a hanging 3 kg mass. Using g = 10 m/s^2, find the magnitude of the acceleration of the system in m/s^2.",
        [r"0\.6(25)?", r"5/8"],
        True,
    ),
    (
        "H3 combustion mass",
        "How many grams of CO2 are produced by the complete combustion of 8 grams of methane (CH4)? Molar masses: C = 12, H = 1, O = 16 g/mol.",
        [r"22\b"],
        True,
    ),
    (
        "H4 balancing sum",
        "Balance the equation: Fe + O2 -> Fe2O3 using the smallest whole-number coefficients. What is the sum of all coefficients?",
        [r"\b9\b"],
        True,
    ),
    (
        "H5 related rates",
        "A spherical balloon's radius grows at 2 cm/s. At the instant the radius is 3 cm, what is the rate of increase of its volume in cm^3/s? (V = 4/3 pi r^3)",
        [r"72\\?pi", r"72\s*π", r"226(\.0*|\.19)?\s*(cm)?\^?3"],
        True,
    ),
]

MODELS = ["gemini-flash-lite-latest", "gemini-3.1-flash-lite", "gemini-3.5-flash"]


def ask(model: str, question: str) -> tuple[str, float]:
    m = genai.GenerativeModel(model_name=model)
    t0 = time.time()
    try:
        resp = m.generate_content(f"{INSTRUCTION}\n\n{question}", request_options={"timeout": 150})
        return (resp.text or ""), time.time() - t0
    except Exception as exc:  # noqa: BLE001
        return f"<<ERROR {type(exc).__name__}: {str(exc)[:100]}>>", time.time() - t0


def grade(text: str, pattern) -> bool:
    m = re.search(r"FINAL:\s*(.+)", text)
    final = m.group(1).strip().lower() if m else ""
    patterns = pattern if isinstance(pattern, (list, tuple)) else [pattern]
    return any(
        re.search(p, final) or re.search(p, text.lower()) for p in patterns
    )


def run_model(model: str) -> None:
    correct = 0
    total_lat = 0.0
    misses = []
    for label, question, pattern, _ in PROBLEMS:
        text, lat = ask(model, question)
        total_lat += lat
        ok = not text.startswith("<<ERROR") and grade(text, pattern)
        if ok:
            correct += 1
        else:
            misses.append(f"    {label} ({lat:.0f}s): {text[:140].replace(chr(10), ' / ')}")
    print(f"{model:<26}{correct}/5      {total_lat/len(PROBLEMS):6.1f}s", flush=True)
    for miss in misses:
        print(miss, flush=True)


if __name__ == "__main__":
    print(f"{'model':<26}{'score':<8}{'avg lat':<9}")
    print("-" * 43)
    with ThreadPoolExecutor(max_workers=3) as pool:
        list(pool.map(run_model, MODELS))
