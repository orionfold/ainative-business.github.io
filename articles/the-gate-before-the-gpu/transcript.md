# Provenance — The Gate Before the GPU

Synthesis article (no new setup session). Sources are the astrodynamics greenfield-vertical
build (Phase-C C1…C6, 2026-06-04/05) and the reusable-lesson memories. Drafted via `tech-writer`
on 2026-06-05.

## Editorial overlay
Methodology / decision-discipline piece (NOT a project log): SFT vs RL vs RLVR method selection
decided by cheap gates before the GPU run. Three nested questions — (1) the demonstration-vs-
verification decision rule, (2) how each gate forks a method path, (3) the iterative spiral.
Honest-null centerpiece. Operator-chosen title "The Gate Before the GPU"; model named **Kepler**
(no Orion prefix → `Orionfold/Kepler-GGUF`, `Orionfold/Kepler-bench` in the later ship-tasks).

## Evidence (numbers verified against on-disk JSON)
- `evidence/astrodynamics/av10-preflight.json` — base Qwen3-8B FP @ 4096: reward 12.5%, boxed 12.5%,
  truncation 87.5% (7/8 ran full budget). Parallax row: correct, 8954 chars / 295.1 s.
- `evidence/astrodynamics/av10-preflight-8192.json` — base @ 8192: boxed 25%, reward 12.5%, trunc 75%
  (doubling the budget barely helped → non-termination, not verbosity).
- `evidence/astrodynamics/av10-preflight-8192-fewshot.json` — 3-shot conditioning probe @ 8192:
  boxed 75%, reward 75%, trunc 12.5% → 6× lift → conditioning-fixable → STICK with base.
- `evidence/astrodynamics/av10-preflight-sft.json` — SFT gate, held-out n=44: boxed 100%,
  reward 86.36% (38/44), trunc 0%. Parallax row: 185 chars / 9.8 s. 6.9× over base.
- SFT run: 600 authored rows, ~11 min, loss 1.5688 → 0.0668 (NeMo p65 lane, merged-hf-bf16).
- `evidence/astrodynamics/c6-sft-heldout.json` — external 44-row curveball generalization:
  reward 86.36% (identical to in-distribution), boxed 100%, trunc 0%. Misses: 3× hohmann,
  2× altitude_from_period, 1× hubble.
- `evidence/astrodynamics/av12-headroom-transfer.json` — error-mined Tier-1 transfer, n=48:
  aggregate reward 20.83% (10/48), boxed 100%, trunc 0%. BIMODAL per-family (table in article):
  altitude→speed 100%; un-named/new-body hohmann, circular-speed, period→speed, new-body
  altitude→period all 0%; only ~4 families / 15 rows in the productive (0,1) band.
- C5 RLVR: 34 steps, in-loop held-out 0.9583 flat across gates 0/10/20/30, selected_step=0,
  5 degenerate zero-advantage steps (1,2,9,14,21), mem peak 104 GB, watchdog never deferred,
  lane torn down clean. Clean null.

## Reusable lessons (memories)
- `feedback_sft_vs_rlvr_decision` — the demonstration-vs-verification rule + the 4 things RLVR buys.
- `feedback_rlvr_headroom_gate` — the Goldilocks band + the bimodal "0% = SFT-coverage-gap" refinement.

## Forward-roadmap research seed
`_IDEAS/methodology-improvement-frontiers.md` (frontier-scout run 2026-06-05, HF-only) — the
"where this discipline goes next" frontiers folded into the :::deeper block and the closing.

## Artifacts created
- `articles/the-gate-before-the-gpu/article.md` — the essay (8 sections, 1 inline fn-diagram, 9 explainers).
- `src/components/svg/GateReadings.astro` — signature: 4-bar reading of the gate measurements.
