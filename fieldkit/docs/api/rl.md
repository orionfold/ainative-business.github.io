---
module: rl
title: fieldkit.rl
summary: The closed-loop RLVR driver (Phase 3, the engine) — GRPOConfig, RLLoop, RLLoopError. Wraps the proven hand-rolled REINFORCE-with-KL loop (not Unsloth/NeMo-RL); held-out-every-≤10-steps hard gate with held-out-only checkpoint selection; ≥100-row corpus floor; pinned vLLM. Orchestration ships; GPU seams inject.
order: 18
---

## What it is

The **engine** in `pane → hands → engine` — the trainer half of
`_SPECS/rlvr-loop-v1.md` (`fieldkit.reward` is the scorer half). It closes the
loop the first four roadmap milestones were built to land: **eval → reward →
fine-tune → re-eval**, with the Spark's own `fieldkit.eval` verifiers as the
reward function. Arena M8 *dispatches* it, M11 *schedules + budget-brakes* it
overnight, M9 *prices* its RL-vs-pay ROI, M10 answers *"has this been tried"*
before it runs.

`fieldkit.rl` wraps the loop that actually *ran* on a single GB10 —
`clawgym-on-spark-grpo`'s **hand-rolled ~280-LOC REINFORCE-with-KL +
kill-and-restart-vLLM**, **not** Unsloth-GRPO or NeMo-RL (neither drove the
working run; `[[project_verl_atgpo_vllm_gap]]` is the cautionary precedent). The
named abstractions are a documented *fallback lane*, not the default (RV-1).

## Orchestration ships; GPU math injects

This module owns the **control flow**, not the GPU kernels: split → sample a
group → reward → group-relative step → held-out gate → held-out-only checkpoint
selection → lineage card is pure, deterministic, and unit-testable. The three
GPU-touching seams are **injected** — the same `dispatch_job(runner=…)` pattern:

- a **sampler** (`tasks, k → list[list[Rollout]]`) — the pinned-vLLM rollout
  (~13 min/step, the dominant cost);
- a **trainer** (`rollouts, advantages, step → metrics`) — the REINFORCE-with-KL
  LoRA step (~22 s) plus the **kill-and-restart vLLM** to reload the adapter
  (~3.5 min — *the* eliminable quarter, RV-5; hot-LoRA-swap is the tracked
  fast-follow, not a v1 gate);
- a **heldout_eval** (`step, tasks → float`) — the held-out gate (RV-4), in the
  Arena path a dispatched M8 `eval_rerun` over the frozen split.

torch / vLLM are **never imported at module load** — only inside the GPU-seam
factory `gpu_seams`, so `import fieldkit.rl` stays stdlib-cheap and the
orchestration tests run with no GPU. `gpu_seams` raises until the pinned-vLLM
backend is vendored into the `fieldkit[rl]` extra; callers driving the loop today
inject their own seams.

## Three corrections, encoded structurally

1. **Pool-convergence is a trap (RV-4).** `t2po` hit pool 87.5% vs held-out 5.7%
   at step 45 — an **81.8 pp inversion**. The loop evaluates a *frozen* held-out
   split every ≤`heldout_every` steps and **selects the published checkpoint on
   held-out score, never pool**.
2. **Pin vLLM (RV-5).** Six API drifts across two minor versions (one silent
   return-shape change). `GRPOConfig.vllm_pin` records the pinned version.
3. **≥100-row corpus floor (RV-10).** 42 rows mode-collapsed. `RLLoop.run`
   refuses a corpus below `corpus_min` and carves the held-out split *before*
   step 0, trainer-resident, one vLLM lane (the 2026-04-22 OOM landmine).

## The surfaces

- **`GRPOConfig`** — the hyperparameters, defaulting to the proven `clawgym`
  knobs: `base`, `lora_rank=16`, `group_k=4`, `tasks_per_step=8`, `temp=0.8`,
  `heldout_every=10` (the hard gate), `vllm_pin`, `max_steps=34`,
  `corpus_min=100` (the floor), `heldout_frac=0.2`, `kl_coef`, `lr`, `seed`
  (makes the split + per-step draw deterministic), and `heldout_patience`
  (default off — the RV-R1 inversion guard that stops the run when held-out stops
  improving). Validates on construction.
- **`RLLoop`** — the driver. Construct with a `GRPOConfig`, a
  `fieldkit.reward.RewardAdapter`, and a bench (any object with a `questions`
  list — `fieldkit.eval.VerticalBench`); inject `sampler` / `trainer` /
  `heldout_eval`. `.run()` runs to `max_steps` and returns the run's
  `fieldkit.lineage.LineageSnapshot` — the **`rl_run` card** and the source of
  the §5 "living-model" delta chart (RV-7). After `.run()`, `.heldout_scores`,
  `.pool_scores`, `.selected_step`, and `.selected_heldout_score` expose the
  held-out-only checkpoint pick; `.summary()` is the aggregate digest the Arena
  dispatcher persists to `jobs.result_json`.
- **`RLLoopError`** — raised on a corpus below `corpus_min`, an invalid
  `GRPOConfig`, or a `.run()` with a missing GPU seam.

## How Arena dispatches it

`fieldkit.arena.jobs` promotes the pre-drilled `rl_run` / `requant` job kinds
into `DISPATCHABLE` (RV-6); the M11 cron drains them single-lane overnight behind
the budget governor. The run is **async/overnight only** — the 8.5 h GRPO loop
can't be a synchronous cockpit click, so the `server.py` `POST /api/jobs`
allowlist stays narrow and `rl_run` reaches the dispatcher via `enqueue_job`. On
a held-out win, an optional `requant` re-quantizes the lifted checkpoint and the
loop closes visibly on the leaderboard. **No new arena.db table, no
`user_version` bump** (RV-8): the trajectory rides `fieldkit.lineage`, the
held-out scores ride `eval_runs`.

## What it is not

It does **not** re-implement a GPU trainer (the proven loop is injected via the
seams / vendored later), publish a `kind: rl_run` artifact (RV-9 defers
publishable kinds to second-vertical reuse), or churn the schema. v1 ships **the
loop**, not the storefront.
