"""Final-answer extraction and grading for exam-style questions.

Given SPIRAL's markdown answer (which ends with a **Final answer:** line by
prompt contract) and a benchmark's reference key, decide pass/fail. Checking
is tolerant of formatting but strict about the value:

- numbers: parsed after stripping LaTeX, commas, units, and wrappers like
  "(A)" or "Option 2"; compared with a relative tolerance (or exact for
  integers);
- MCQ: single or multi-select letter sets, order-insensitive;
- text: normalized word overlap (contains-style match).
"""
import math
import re

_FINAL_PATTERNS = [
    r"\*\*Final answer:?\*\*\s*(.+)",
    r"\*\*Answer:?\*\*\s*(.+)",
    r"Final answer:?\s*(.+)",
]


def extract_final_answer(text: str) -> str:
    """The text after the final-answer marker, else the last non-empty line."""
    for pattern in _FINAL_PATTERNS:
        match = re.search(pattern, text or "", flags=re.IGNORECASE)
        if match:
            return match.group(1).strip().strip("*`_ ").strip()
    lines = [line.strip() for line in (text or "").strip().splitlines() if line.strip()]
    return lines[-1] if lines else ""


_LATEX_WRAPPERS = [
    (r"\\boxed\{([^{}]*)\}", 1),
    (r"\\text\{([^{}]*)\}", 1),
    (r"\\mathrm\{([^{}]*)\}", 1),
    (r"\$([^$]*)\$", 1),
]


def _strip_latex(fragment: str) -> str:
    out = fragment
    # \frac{a}{b} -> a/b so the fraction parser can see it.
    out = re.sub(r"\\\\frac\{([^{}]*)\}\{([^{}]*)\}", r"\1/\2", out)
    for _ in range(3):  # nested wrappers, e.g. $\boxed{42}$
        changed = False
        for pattern, group in _LATEX_WRAPPERS:
            new = re.sub(pattern, lambda m: m.group(group), out)
            if new != out:
                out, changed = new, True
        if not changed:
            break
    return out


_MCQ_SET_RE = re.compile(r"[A-D]")


def _parse_mcq_set(fragment: str) -> frozenset[str] | None:
    """{A} / (B) / A and C / A, C / option A, C -> letter set; None if not MCQ."""
    compact = re.sub(r"^option[s]?\s*", "", fragment.strip(), flags=re.IGNORECASE)
    compact = re.sub(r"[()\[\]{}]", " ", compact)
    # Remove connector words BEFORE letter extraction — the "d" in "and"
    # would otherwise be read as option D.
    compact = re.sub(r"\b(and|&)\b", " ", compact, flags=re.IGNORECASE)
    compact = re.sub(r"\s+", " ", compact).strip()
    if re.fullmatch(r"[A-D](\s*(,|and|&)?\s*[A-D]){0,3}", compact, flags=re.IGNORECASE):
        return frozenset(m for m in _MCQ_SET_RE.findall(compact.upper()))
    return None


_FRACTION_RE = re.compile(r"(-?\d+(?:\.\d+)?)\s*/\s*(\d+(?:\.\d+)?)")
_NUM_RE = re.compile(r"-?\d+(?:\.\d+)?(?:\s*[eE][+-]?\d+)?")


def _parse_number(fragment: str) -> float | None:
    """First number (or fraction) after stripping latex/commas/units/labels."""
    cleaned = _strip_latex(fragment)
    cleaned = cleaned.replace(",", "").replace("°", "")
    # Drop a leading option label like "(B) 4 m/s^2"
    cleaned = re.sub(r"^\(?[A-Da-d]\)?\s*", "", cleaned).strip()
    fraction = _FRACTION_RE.search(cleaned)
    if fraction:
        try:
            return float(fraction.group(1)) / float(fraction.group(2))
        except (ValueError, ZeroDivisionError):
            return None
    match = _NUM_RE.search(cleaned)
    if not match:
        return None
    try:
        return float(match.group(0).replace(" ", ""))
    except ValueError:
        return None


def _numbers_match(expected: str, actual: str) -> bool | None:
    exp_num = _parse_number(expected)
    act_num = _parse_number(actual)
    if exp_num is None or act_num is None:
        return None
    if exp_num == 0 or float(exp_num).is_integer() and float(act_num).is_integer():
        return math.isclose(exp_num, act_num, rel_tol=0, abs_tol=1e-9)
    return math.isclose(exp_num, act_num, rel_tol=0.02, abs_tol=1e-9)


_WORD_RE = re.compile(r"[a-z]{2,}")


def _text_match(expected: str, actual: str) -> bool:
    exp_words = set(_WORD_RE.findall(expected.lower()))
    act_words = set(_WORD_RE.findall(actual.lower()))
    if not exp_words:
        return expected.strip().lower() == actual.strip().lower()
    return len(exp_words & act_words) / len(exp_words) >= 0.75


def check_answer(reference: str, produced: str) -> bool:
    """Tolerant-in-format, strict-in-value comparison against the key."""
    reference = (reference or "").strip()
    produced = (produced or "").strip()
    if not reference or not produced:
        return False

    exp_mcq = _parse_mcq_set(reference)
    if exp_mcq is not None:
        act_mcq = _parse_mcq_set(produced) or frozenset(
            m.upper() for m in _MCQ_SET_RE.findall(produced.strip().strip("() "))
        ) if _MCQ_SET_RE.search(produced) else None
        return act_mcq == exp_mcq

    numbers = _numbers_match(reference, produced)
    if numbers is not None:
        return numbers
    return _text_match(reference, produced)
