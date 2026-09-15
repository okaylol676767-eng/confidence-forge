# STEM Response Quality Baseline

Established from the local interaction log (as of 2026-09-15, prompt **v2** active).
This is the benchmark future physics/technical-education changes are measured against —
after any prompt, model, or pipeline change, re-run `GET /stats/summary` and compare
against the numbers below.

## Headline numbers (all interactions)

| Metric | Value |
|---|---|
| Total logged interactions | 132 |
| Conversations | 72 |
| Average confidence | 0.866 |
| Low-confidence answers (< 0.7) | 21 (15.9%) |
| Average latency | ~2.4s (v1-era, includes the 3-sample vote) |

## Per-prompt-version comparison (the A/B signal)

| Version | Interactions | Avg confidence |
|---|---|---|
| v1 (generic confidence prompt) | 109 | 0.845 |
| v2 (STEM tutor, calibrated scale, self-consistency) | 23 | **0.964** |

v2's +0.12 confidence uplift reflects both genuinely better answers and the
recalibrated, evidence-anchored scoring (v1's scale was inflated-but-shallow;
v2 anchors scores to derivation quality and passes/vetoes them with sample
agreement). Judge quality by the low-confidence rate and user-visible
correctness, not the raw average alone.

## Reference cases

### Positive reference — general-inquiry intent resolution

Interaction **#126**: *"Different question entirely: who wrote Hamlet?"* →
confident, correct general-knowledge answer (**William Shakespeare**),
confidence 1.0, 1100ms. Retained as the canonical example that the STEM-heavy
prompt does not degrade general inquiries: intent was recognized, no spurious
derivation was forced, and confidence reporting stayed honest.

Other strong exemplars (v2 era): "State Ohm's law" (conf 0.98), quadratic
formula (1.0), photosynthesis definition (0.99).

### Known-failure archive — superseded

Eight interactions with confidence 0.0 are all one root cause, **already
fixed**: the pre-`pypdf` pipeline asked the model to read raw PDF bytes, and
it answered "unable to decode the compressed stream content". Since the
server-side PDF text-extraction fix, PDFs answer from their real text layer
(verified end-to-end with compressed 2-page documents). These rows are kept
as regression markers: if confidence-0.0 "cannot read document" answers ever
reappear, the extraction path regressed.

## Change-management rules

1. Any change to `PROMPT_V2`, the model, or the solving pipeline must be
   compared against this file's numbers via `/stats/summary` (per-version
   breakdown) before being declared an improvement.
2. `/improve`-generated prompt versions (v3+) are the intended vehicle for
   further tuning; baselines are refreshed from code at startup and never
   hand-edited in the DB.
3. The self-consistency vote (3 samples) applies to non-trivial quantitative
   questions only; trivial arithmetic skips it by design (see
   `app/consistency.py`), so latency comparisons must respect that split.

## Regulated-domain guardrail

Prompt v2 (and v1) now instruct the model to append a one-line disclaimer
whenever an answer could feed equipment design, safety compliance, medical
dosing, structural or aerospace work — e.g. *"For equipment design/compliance,
consult domain-specific standards and a qualified professional."* — while
explicitly NOT disclaiming routine homework or study help. This is prompt
guidance, not a hard guardrail; if regulated-domain traffic ever becomes
significant, add a classifier-based check in `services.py` rather than
relying on the model's judgment alone.
