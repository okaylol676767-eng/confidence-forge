"""JEE grader: extraction + tolerant checking, deterministic."""
from app.answer_check import check_answer, extract_final_answer


def test_extract_from_final_answer_marker():
    text = "Some steps...\n**Final answer:** 42 J"
    assert extract_final_answer(text) == "42 J"


def test_extract_falls_back_to_last_line():
    text = "step one\nstep two\n40 m"
    assert extract_final_answer(text) == "40 m"


def test_numeric_match_ignores_units_and_latex():
    assert check_answer("20 m", "**Final answer:** $20\\ m$ upward")
    assert check_answer("0.6", "Final answer: 0.60 m")
    assert check_answer("150", "**Final answer:** 150 m")


def test_fraction_keys():
    assert check_answer("1/2", "Final answer: $\\\\frac{1}{2}$")
    assert check_answer("5/36", "Final answer: 0.1389")
    assert check_answer("1/6", "Final answer: 1/6")


def test_numeric_mismatch_fails():
    assert not check_answer("40", "Final answer: 20 m")
    assert not check_answer("0.6", "Final answer: 6 m")


def test_mcq_single():
    assert check_answer("B", "**Final answer:** (B) 20 m")
    assert check_answer("B", "Final answer: B")
    assert not check_answer("A", "Final answer: (B) 20 m")


def test_mcq_multi_order_insensitive():
    assert check_answer("A and C", "Final answer: (C) and (A)")
    assert check_answer("AC", "Final answer: A, C")


def test_text_match():
    assert check_answer("Si", "Final answer: Si (silicon)")
    assert check_answer("Ethanol", "Final answer: **Ethanol** — it has the CH3CH2OH group")


def test_partial_text_requires_mostly_match():
    # 1 of 3 words matches -> below 0.75 -> fail
    assert not check_answer("completely different words", "Final answer: silicon")


def test_empty_inputs_fail_closed():
    assert not check_answer("", "something")
    assert not check_answer("42", "")
    assert not check_answer("", "")
