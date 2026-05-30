# Quant-shape signals — Q8_0 expectation per training shape

`training-signals.md` answers the question **"is this model SFT-tuned or continued-pretrain?"** for the *trap-avoidance* purpose (continued-pretrain bases score ~0 on Q&A benches without further SFT).

This file extends that detection with a **downstream quantization implication** discovered across the four-vertical sprint (2026-05-09 → 2026-05-16): the same training-type signal also predicts whether **Q8_0 will be faster or slower than F16** on GB10 (Spark). The implication is consequential because the `recommended_variant` line on the HF card is built from these numbers — and the scout report should pre-load the expectation so the user picks knowing which side of the split they're sampling.

See `[[project_q8_anomaly_model_specific]]` for the source memory and the n=4 evidence table.

## The four-vertical evidence

Same sweep order on all four (F16 → Q4_K_M → Q5_K_M → Q6_K → Q8_0 last). Same GB10. Result split 2-2 along the **continued-pretrain-vs-not** axis:

| Vertical | Date     | Training shape                                                | F16 tok/s | Q8_0 tok/s | Q8 vs F16        |
|----------|----------|----------------------------------------------------------------|-----------|------------|------------------|
| finance  | 2026-05-09 | continued-pretrain (Llama-2-7B-chat + AdaptLLM CPT)         | 11.5      | 8.9        | **23% slower**   |
| legal    | 2026-05-14 | continued-pretrain (Mistral-7B-Instruct + Saul CPT)         | 10.9      | 7.3        | **33% slower**   |
| cyber    | 2026-05-15 | chat-tune-only (Mistral-7B base + Zephyr DPO)               | 17.5      | 30.3       | **73% faster**   |
| medical  | 2026-05-16 | chat-tune-only (Qwen3-8B base + SFT + DAPO)                 | 15.9      | 28.4       | **78% faster**   |

Architecture doesn't line up (finance=Llama, legal/cyber=Mistral, medical=Qwen3); model size doesn't line up (all 7-8B). **Continued-pretrain-vs-chat-tune-only is the cleanest 2-2 split.**

Early thermal-throttling hypothesis (Q8_0 ran last, warmed die, throttle) would have predicted slowdown on every vertical — cyber + medical break it. Most parsimonious story at n=4: continued-pretrain weights pack differently (denser activation distributions / mid-range outliers / a quantization-grid mismatch the Q8 path hits but Q4–Q6 don't), but at n=4 this is **hypothesis, not conclusion**.

## What to expect on the next vertical

For a scout that has classified the candidate's training-type:

| Training shape (detected via `training-signals.md`)            | Q8_0 expectation vs F16                  | Recommended-variant default          |
|-----------------------------------------------------------------|-------------------------------------------|---------------------------------------|
| **continued-pretrain** (`*-pretrain*`, `*-continued*`, AdaptLLM-CPT, Saul-CPT) | likely ~25–35% **slower**       | **Q5_K_M** (best quality-per-byte at the smaller end) |
| **chat-tune-only** (`*-Chat`, `*-Instruct`, SFT/DPO without an upstream CPT layer) | likely ~70–80% **faster**       | **Q4_K_M** (throughput-led) **or** **Q8_0** (quality-led — newly viable because it's now faster than F16) |
| **base-only** (no chat-tune, no CPT)                            | unmeasured at n=4 — flag as `UNKNOWN_SHAPE` | defer; the bench gate won't pass anyway, see `[[feedback_preflight_bench_before_quant]]` |
| **CPT + later chat-tune** (`*-pretrain-chat`, AdaptLLM-chat)    | unmeasured at n=4 — treat as **continued-pretrain** until n≥1 sample contradicts | Q5_K_M |

These are **pre-measurement expectations** for the report, not facts. The actual sweep still runs F16 → Q4_K_M → Q5_K_M → Q6_K → Q8_0; the HF card always records as-measured numbers (per `[[project_q8_anomaly_model_specific]]` — never pre-correct).

## Vertical N+1 sample-balancing — the discriminating-pick rule

The strategic move on each new vertical is **whichever shape has fewer samples so far**. The current state across the four shipped verticals:

| Shape                 | Count | Verticals                          |
|-----------------------|-------|------------------------------------|
| continued-pretrain    | 2     | finance, legal                     |
| chat-tune-only        | 2     | cyber, medical                     |
| base-only             | 0     | (not a viable production shape)    |
| CPT + later chat-tune | 0     | (unmeasured)                       |

**A third sample on either side promotes that side's pattern from "n=2 observation" to "n=3 weak rule".** Both sides are equally information-bearing at n=4, but the v5 strategy doc has flagged **chat-tune-only as the vertical #5 pick** (per `mtbm-strategy-v5.md §6 Pick #1`) because the corpus landscape there is wider open. The scout should:

1. **Read the current shape distribution** from the latest four Orionfold cards (or this table if it's stale) before recommending.
2. **Flag a "Vertical #N+1 sample-balancing" line** in the report header that names the current counts and which shape the v5 prescription says to pick this cycle.
3. **Cross-tag the recommended candidates** by training shape so the user can override the prescription if a candidate of the prescribed shape doesn't pass the four-axis gate.

### Updating this table

When a 5th (or later) vertical lands on HF, update the count table above and the n-sample row in the evidence table. The doc-update cost is ~3 minutes per vertical and keeps the scout's framing accurate; the alternative is the scout silently sampling the rich side and never closing the rule.

**A `git log articles/becoming-a-*-curator-on-spark/` survey is the authoritative way to read current verticals at scout time** — this file's count is a snapshot, not a live read.

## Why this lives in the scout skill

The HF card consumer sees Q8_0 numbers as a measured fact. The Spark builder sees them as a sweep-order outcome. **The picker** — i.e., this skill's user — is the only actor who can pre-load the expectation and use it to *pick a model that will produce a useful data point*. That's why the sample-balancing logic and the per-shape expectation table live here and not in `hf-publisher` or `tech-writer`.

If the shape-vs-Q8 hypothesis sharpens to a rule (n≥5 each side), this file is the canonical place to retire the hedging language and promote the table into a deterministic recommendation. Until then, every entry is hedged with "likely" / "expected" — the scout reports the expectation; the measurement decides.

## Memory cross-references

- `[[project_q8_anomaly_model_specific]]` — the source memory + the live evidence table
- `[[feedback_preflight_bench_before_quant]]` — the gate that rules out base-only shapes regardless of Q8 expectation
- `[[feedback_chat_vs_continued_pretrain_trap]]` — the upstream detection that feeds the shape classification used here
- `[[feedback_keep_scorer_local_until_reuse]]` — adjacent operational rule for `mcq_letter` promotion on the 3rd reuse (vertical #5 trigger if MCQ-shaped)
