# Kepler T2 head-to-head — astrodynamics numeric reasoning

**Benchmark:** 44-row external curveball held-out (`astro-bench-v0.1.heldout.jsonl`) — off-template
orbital + astrophysics problems, constants given in-prompt, `\boxed{}` answer scored within ±2%
relative tolerance by the same verifier Kepler was trained against (`astro_numeric_match`).
**Budget:** matched 4096-token completion budget across all lanes. **Sampling:** temp 0.6 / top_p 0.95.

| Model | Lane | Reward (±2%) | Boxed | Trunc | Mean tokens | Misses |
|---|---|---:|---:|---:|---:|---|
| **Kepler-Q8_0** (8B, **local, $0**) | llama.cpp GGUF | **84.1%** (37/44) | 100% | 0% | **166** | altitude_from_period, hohmann_transfer, hubble_in_pc |
| Claude Haiku 4.5 | OpenRouter | 97.7% (43/44) | 100% | 0% | 488 | kepler_third_law |
| Gemini 3.1 Flash-Lite | OpenRouter | 95.5% (42/44) | 100% | 0% | 464 | hohmann_transfer |

**Dropped:** stock `qwen/qwen3-8b` (apples-to-apples base) and `deepseek/deepseek-r1` — both stalled
on slow/unstable OpenRouter providers under the 4096-token thinking budget; not re-run (operator call).

## Honest read

- A **local 8B specialist** lands **~11–14 pp below** frontier cloud *small* models on this off-template
  set — at **$0/query, fully private, no network**, where the cloud lanes incur per-token spend.
- **Kepler is ~3× more concise**: 166 mean tokens vs ~464–488 for the cloud models. The boxed-discipline
  SFT taught it to answer, not ruminate — the same trait that eliminated the base's AV-R1 over-thinking.
- **Every lane boxed 100% with 0% truncation** — Kepler's format reliability matches frontier models;
  the gap is purely reasoning accuracy on a handful of compositional rows.
- **Known weak spots** (the honest `known_drift` for the card): `hohmann_transfer` (multi-step transfer)
  and `altitude_from_period` (inverse Kepler) — the same families that fail across all Kepler quants and
  that the STEP-1.5 headroom gate flagged as an SFT-coverage gap, not an RL-headroom opportunity.

_Source: `evidence/astrodynamics/t2/{kepler-q8,claude-haiku-4.5,gemini-3.1-flash-lite}.json`._
