<!-- Arena end-to-end operator smoke — Last updated: 2026-06-06 -->

# Arena end-to-end operator smoke (build → serve → review)

> **What this is.** A reusable runbook for walking the **whole** Orionfold Arena pipeline as
> one operator session — *build → serve → review* — with the operator driving every
> GPU/cloud-armed step and Claude guiding, explaining, watching the live cockpit over CDP,
> shooting evidence, and harvesting bugs + v2 features. Every surface has been unit-tested +
> per-feature browser-smoked in isolation; this is the first time the **whole machine** is
> exercised in one flow. It also fires the two long-deferred **operator-armed gates**
> (guardrail AE-R1 + RL-lane AE-R1). Vertical = **Kepler / astrodynamics** (all artifacts on
> disk). Reusable: any future vertical re-runs this with its own slugs.

## Roles

- **Operator** runs every GPU/cloud-armed command and reports what they see. (Give
  copy-pasteable blocks — the `!`-prefix shell does not work here, per
  `feedback_terminal_bang_unavailable`.)
- **Claude**, at each step: (a) gives the exact command, (b) explains *why* + what it teaches,
  (c) states the **success criterion**, (d) watches the live pane over CDP and confirms the
  render, (e) shoots a 2× screenshot, (f) logs anything off into the issue ledger.

## Harness

- Cockpit + visible Chromium: `.claude/skills/arena-lifecycle/scripts/arena_lifecycle.sh
  restart --browser` → sidecar `:7866` + CDP Chromium `:9222`.
- CDP attach (proven 2026-06-06): `playwright-core` `connectOverCDP('http://127.0.0.1:9222')`
  (`/tmp/pw/node_modules/playwright-core`, default-export interop:
  `import pkg from '…/index.js'; const { chromium } = pkg;`), `ctx.newPage()`. Hidden inputs
  (e.g. the Settings toggle) are clicked via their visible label/track, not the `<input>`.
- Screenshots → `/tmp/aifn-smoke/e2e/{build,serve,review}/`, `NN-kebab.png`, 2× scale; `rm -rf`
  the staging dir at session end (`browser_smoke_snapshots_tmp`). Visible Chromium caches hashed
  JS — hard-reload / CDP `Network.clearBrowserCache` if a pane looks stale.
- Rebake (`fieldkit arena build --repo-root arena-app`) only if an `arena-app/` edit is needed
  mid-smoke (it shouldn't be).

## Pre-session arming checklist (operator, before we start)

- [ ] **NeMo container up** (`nvcr.io/nvidia/nemo:26.04.00`) with `mcore-base/` + `dataset/`
  built under `/home/nvidia/data/astro-train-lora/p65-nemo/` — for the SFT smoke (A4).
- [ ] **`fieldkit[rl]` + the pinned aarch64+CUDA-13 vLLM lane** (`vllm-node:latest`) + `FK_RL_*`
  via `scripts/astro_bench/fk-rl-env.sh` — for the RL run (C3). One-lane envelope:
  **tear the Kepler llama.cpp lane down first** (`project_spark_unified_memory_oom`).
- [ ] **OpenRouter key** loaded (`.env.local` → `OPENROUTER_API_KEY`) — cloud evals (C1/C2) + compare (B3).
- [ ] **pgvector up** (`:5432`, usually already up) — Cortex (C5).
- [ ] **`sudo chown`** the root-owned container-written dirs (`merged-hf-bf16`, `init-lora-r16`,
  `evidence/astrodynamics/av10-preflight*.json`) if the smoke must rewrite them.

## Pre-flight (Claude, ~3 min, no GPU)

`arena_lifecycle.sh restart --browser` → confirm `/healthz` + CDP `:9222`; attach playwright;
verify the on-disk inventory:

- bench `evidence/astrodynamics/astro-bench-v0.1.jsonl` (120) + `.heldout.jsonl` (44)
- corpus `astro-sft-corpus.jsonl` (600) + `astro-sft-queue.jsonl` (600)
- reward `av10-preflight.json` (base 12.5%) + `av10-preflight-sft.json` (SFT 86.36%)
- `build-manifest.json` (Kepler 7/8), Kepler GGUFs `/home/nvidia/data/quants/Kepler/`
- bench registry `~/.fieldkit/arena/benches/kepler-astro.jsonl`

`mkdir -p /tmp/aifn-smoke/e2e/{build,serve,review}`.

## Phase A — BUILD (the spine; ~20 min)

| # | Pane / action | Operator runs | Claude watches / success criterion | Shot |
|---|---|---|---|---|
| A0 | `/arena/build/` spine | — | 8 C1..C6 cards render, Kepler **7/8**, lane honestly idle | `build/00-spine.png` |
| A1 | Scout — `/arena/compare/` ScoutPanel | — | `2026-06-04/astrodynamics-7B · top 3 of 6`, Qwen3-8B 95/100 + 6 trap axes + ruled-out table | `build/01-scout.png` |
| A2 | Bench provenance card (build pane) | — | `astro-bench v0.1 · 120 pool + 44 held-out · disjoint ✓ (RV-10) · 164/164 self-verify` | `build/02-bench.png` |
| A3 | Corpus feed (AE-6) | `/tmp/fk/bin/python scripts/astro_bench/verify_sft.py` (~2 s) **or** Claude seeds a `corpus-progress-*.json` heartbeat | corpus strip lights (written/target · verify ✓ · family-mix · ETA) | `build/03-corpus.png` |
| A4 | **SFT smoke (REAL)** | `python scripts/astro_bench/run_sft_nemo.py smoke` (10 iters, ~2 min, NeMo container) | `/arena/sft/` lights from the real driver log — iters climb, loss curve, peak-mem watch | `build/04a-sft-live.png`, `04b-sft-done.png` |
| A5 | Reward gauge — `/arena/reward/` | — | AV-10: base **12.5%** → SFT **86.36%** held-out (on-disk reports) | `build/05-reward.png` |
| A6 | Gate ledger (AE-7, build pane) | — | gate cards with allow/hold + consequence text | `build/06-gates.png` |

**Narration beats:** scout traps (license / chat-format / arch / 128 GB envelope); held-out
disjointness discipline (RV-10); template-synth + the 4 verifier gates; SFT-init warm-start; the
**headroom gate + SFT-vs-RL decision rule** (`feedback_sft_vs_rlvr_decision`,
`feedback_rlvr_headroom_gate`); operator gates as the human checkpoints.

## Phase B — SERVE (lane + inference; ~10 min)

| # | Pane / action | Operator runs | Claude watches / success criterion | Shot |
|---|---|---|---|---|
| B0 | Serve Kepler-Q8 lane | `spark-serve` llama.cpp `model-Q8_0.gguf` on `:8091` (~8 s) | `:8091/health` OK; one-lane 128 GB envelope explained | — |
| B1 | Models + telemetry rail | — | lane registered; rail shows live tok/s + **resident-lane truth** (AE-15) | `serve/01-models.png` |
| B2 | Chat — `/arena/chat/` | ask an orbital-period question | SSE stream + `<think>` chain; **score 1.0** vs bench gold (`astro_numeric_match`) | `serve/02-chat-scored.png` |
| B3 | Compare — `/arena/compare/` | Kepler-local vs an OpenRouter cloud model on an astro prompt (~$0.01) | both stream; rubric winner banner; **`$0·local`** vs cloud-$ chip | `serve/03-compare.png` |
| B4 | Leaderboard — `/arena/leaderboard/` | — | efficiency frontier + real Kepler rows (`kepler-q8` 0.86/44) | `serve/04-leaderboard.png` |

## Phase C — REVIEW (meta + both operator-armed gates; ~35 min)

| # | Pane / action | Operator runs | Claude watches / success criterion | Shot |
|---|---|---|---|---|
| C0 | Jobs — local eval | dispatch `eval_rerun` Kepler-Q8 × astro-bench **held-out subset ~10 rows** | card runs → done with the scorer_path score (~0.8x/10) | `review/00-jobs-local.png` |
| C1 | **Guardrail AE-R1 · G3 cost cap** | `/arena/settings/` → cap **$0.05** (confirm source=`file`, no restart); dispatch a **cloud** eval (~20 rows) | G3 trips → `⚠ aborted · cost cap · partial · N scored · $0.05x · cap $0.05` | `review/01a-settings.png`, `01b-costcap-abort.png` |
| C2 | **Guardrail AE-R1 · G1 teardown** | reset cap $1; dispatch a cloud eval; mid-run `arena_lifecycle.sh down`; then restart | sentinel trips → job lands partial/teardown on restart; then reset cap→default + re-enable on Settings | `review/02-teardown-partial.png` |
| C3 | **RL-lane AE-R1 · 4-step RLVR (REAL)** | **tear Kepler lane down first**; arm the vLLM[rl] lane; `export FK_RL_MAX_STEPS=4`; `python scripts/astro_bench/enqueue_rl.py` → `fieldkit arena drain` (~20 min) | `/arena/reward/` gauge lights end-to-end from the live run; `/arena/jobs/` rl_run card: GRPO row + held-out summary + lineage (AE-9 `↑corpus·sft-init·bench`) + `(rl-<step>)` pointer | `review/03a-reward-live.png`, `03b-rl-card.png` |
| C4 | Standup — `/arena/standup/` | — | overnight digest + promote gate reads the jobs just run | `review/04-standup.png` |
| C5 | Cortex — `/arena/cortex/` | a live query | recall coverage + RAG-eval trend (pgvector) | `review/05-cortex.png` |
| C6 | Lab — `/arena/lab/` | pin a note on a card | operator-private CRUD persists | `review/06-lab.png` |

**C3 caveat:** Kepler's own C5 RLVR was a clean null (`feedback_rlvr_headroom_gate`) — this run
is a **pipeline-mechanism** validation (does the gauge / card / lineage light from a *real*
run), not a lift expectation. Watch liveness via `latest_checkpointed_iteration.txt` + iter
dirs, not a tail-grep of stdout (`feedback_megatron_train_log_buffering`).

## Phase D — CLOSE (Claude, ~10 min, no GPU)

- **Teardown:** EngineCore-aware `pkill -9 -f 'vllm|EngineCore'` for the RL lane; kill any
  llama.cpp lane; verify `free -h` (`feedback_vllm_engine_core_orphan`).
- **Revert smoke state:** delete any seeded synthetic rows + reset the guardrail config to
  default (the GS-3 cleanup discipline — `rm ~/.fieldkit/arena/guardrail-config.json`).
- **Log issues** (Claude's + operator-shared) → `_IDEAS/arena-smoke-v2-features.md` "Bugs found"
  section; quick actionable nits → HANDOFF "Destination & cleanup" `#N`.
- **Capture v2 features** (AF-style blocks + the extractable-features table) → the same ledger.
- **Screenshots:** curate the best 2× shots into `products/arena-control-plane/screenshots/`
  (add build / serve / settings / review panes — the demo is currently jobs-board-only); keep
  the full set staged in `/tmp`; note candidates for an article refresh. Secret-scan + scoped
  captures before any commit (invariant #3).
- **Update HANDOFF + beacon**; if v2 findings mature, draft `_SPECS/arena-enhancements-v2.md`
  (AE-18+).

## Efficiency / dummy-data safeguards (minutes, not hours)

- Eval **subsets** (held-out ~10–20 rows, not the full 44). RL **4 steps** (not 34),
  `FK_RL_MAX_MODEL_LEN=4096`, `FK_RL_GPU_UTIL=0.5`. SFT **10-step** smoke (not 100).
- **Cloud spend ceiling ≈ $1 total** (cost-cap eval + teardown eval + compare).
- **One-lane rule** strictly enforced: Kepler llama.cpp **down** before the vLLM RL lane up.
- Pre-staged / on-disk artifacts for every read-only stage; live runs only where the gate
  *requires* real signal (SFT pane, reward gauge, the two guardrail trips, the RL card).

## Wall-time budget (Full tier)

Pre-flight 3 · BUILD ~20 (SFT 2 + reads) · SERVE ~10 · REVIEW ~35 (jobs 3 · G3 5 · G1 5 · RL 20
· standup/cortex/lab ~5) · CLOSE ~10 ≈ **~80 min** with narration + screenshots.

## Verification (smoke succeeded when)

- Every pane above renders its success criterion live over CDP (Claude confirms each).
- **Both operator-armed gates fire for real:** a cloud eval aborts on the $0.05 cap with the
  partial badge (G3) and on `arena down` mid-run (G1); the reward gauge + rl_run card light from
  a real 4-step run.
- ≥18 curated 2× screenshots across build / serve / review / settings.
- `_IDEAS/arena-smoke-v2-features.md` holds the session's bug + feature harvest; HANDOFF +
  beacon updated; the box is left clean (`free -h`, no orphan EngineCore, config reverted).
