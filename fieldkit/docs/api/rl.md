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
orchestration tests run with no GPU. The real backend is now **vendored** (the
ported `clawgym-on-spark-grpo` loop): `gpu_seams` returns the three real seams
when the `fieldkit[rl]` extra is installed, and raises a friendly `RLLoopError`
pointing at the extra when it isn't. It splits torch-free / torch-bound so the
GPU stack is touched only on a live call:

- `fieldkit._rl_gpu_serve` (**torch-free**) — the HTTP rollout sampler over the
  local pinned-vLLM OpenAI endpoint (via `fieldkit.nim.NIMClient`; the GPU lives
  in a *separate* vLLM server process), the held-out gate, and the `VLLMLane`
  kill-and-restart serve lifecycle;
- `fieldkit._rl_gpu_trainer` — the torch/peft REINFORCE-with-KL step (the K3 KL
  estimator against a frozen CPU-resident reference snapshot, advantage-weighted
  loss, AdamW, adapter save). Importing it **is** the `fieldkit[rl]` gate.

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
- **`rl_hooks(progress_cb=None, should_abort=None)`** — a context manager that
  binds **live-progress** + **OOM-abort** hooks for any `RLLoop` run in its scope
  (rl-lane-autonomy LA-8/10). The Arena `rl_run` dispatch enters it around the
  loop so an unmodified `run_rl_loop` still reports live step state (into
  `jobs.result_json`) and respects a watchdog abort — the hooks ride a
  `contextvars.ContextVar`, so they are thread-/task-local and flow **arena → rl**
  only (`fieldkit.rl` never imports `fieldkit.arena`). Explicit `RLLoop(progress_cb=…,
  should_abort=…)` injection wins; otherwise the loop falls back to the ambient
  hooks. A bare `import fieldkit.rl` leaves them unset → zero overhead.
- **`current_rl_hooks()`** — the ambient `(progress_cb, should_abort)` for the
  current scope (`(None, None)` when no `rl_hooks` is active). `RLLoop.run` reads
  this when its own hook fields are unset.

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

## Operator run (the GPU path is armed, not automatic)

A live run is a deliberate operator action — the orchestration is GPU-free, but
the rollout/train loop needs the GPU stack on the box:

1. **Install the extra** — `pip install "fieldkit[rl]"` (torch + peft +
   transformers + protobuf + sentencepiece + safetensors + accelerate). These
   are pip-installable on the GB10.

   **The proven GB10 stack (BUG-4, e2e smoke 2026-06-06).** The extra is
   ceiling-pinned to the combo a real 4-step GRPO `rl_run` validated:
   `transformers==4.51.3` + `protobuf` + `sentencepiece` + `torch 2.12.0+cu130`
   + `peft 0.19.1`. Do not "upgrade past" it casually — the drift chain it
   pins out: transformers **5.x** crashes `device_map="auto"` on GB10 (`Cannot
   copy out of meta tensor`); 4.5x without protobuf/sentencepiece fails the
   qwen3 tokenizer load; and **no 4.x** accepts a NeMo-exported
   `tokenizer_config.json` carrying *list-form* `extra_special_tokens`.

   **The shadow model dir (the NeMo-export fix).** A NeMo-merged HF export may
   write `extra_special_tokens` as a list (and may be root-owned, so unfixable
   in place). Build a shadow dir: symlink every file from the export, replace
   only `tokenizer_config.json` with a copy whose `extra_special_tokens` key is
   dropped, then point `FK_RL_BASE_MODEL` at the shadow. vLLM keeps serving the
   original (identical weights); only the trainer-side tokenizer load needs the
   fixed config. On the Spark: `merged-hf-bf16-fixed/` shadows
   `merged-hf-bf16/`.

   **Venue:** keep the RL venv OFF `/tmp` (reboot-ephemeral — every reboot
   silently re-resolves the stack; that is exactly how BUG-4 shipped).
2. **Serve a pinned vLLM separately.** vLLM is *not* a dependency of the extra:
   there is no aarch64+CUDA-13 wheel for the pinned version yet
   (`[[project_verl_atgpo_vllm_gap]]`), so it is brought up as its own process
   (or container) serving the base model with `--enable-lora`. `VLLMLane` then
   kill-and-restarts it between steps to load each lifted adapter.
3. **Point the seams at the box** via environment (the seam signature
   `gpu_seams(config)` stays stable — the operator tunes the box, not the API):

   | Var | Meaning | Default |
   |---|---|---|
   | `FK_RL_VLLM_URL` | local vLLM OpenAI base | `http://localhost:8000/v1` |
   | `FK_RL_BASE_MODEL` | HF base id to serve + train | `Qwen/Qwen2.5-7B-Instruct` |
   | `FK_RL_ADAPTER_INIT` | SFT-init LoRA the run starts from | *(required)* |
   | `FK_RL_WORK_DIR` | where per-step adapters are written | `~/.fieldkit/rl` |
   | `FK_RL_LORA_NAME` | served LoRA module == chat `model` | `policy` |
   | `FK_RL_GPU_UTIL` | vLLM `--gpu-memory-utilization` (one-lane, RV-10) | `0.55` |
   | `FK_RL_HELDOUT_TEMP` | held-out-eval temperature (< train temp) | `0.2` |
   | `FK_RL_SERVE_CMD` / `FK_RL_STOP_CMD` | full serve/stop overrides (e.g. `docker exec`) | host `vllm` / EngineCore-aware `pkill` |

4. **Dispatch overnight, never synchronously** (RV-6) — `rl_run` enqueues into
   the M8 dispatcher and drains under the M11 single-lane cron behind the budget
   governor. The ~8.5 h loop is not a cockpit click.

Until those are in place, inject your own `sampler` / `trainer` / `heldout_eval`
into `RLLoop` directly — the orchestration is fully functional and tested with
fakes.

## Operator: full autonomy (rl-lane-autonomy v1)

Once a pinned vLLM is installed, the hand-driven overnight session becomes one
armed policy. `fieldkit.arena.lane` (LA-1..11) wraps the dispatchable `rl_run`
so it is **self-driving, observable, and self-defending**:

1. **Arm the cron once** — `fieldkit arena autonomy on --interval-min 30
   --cap-usd 5` records the policy + prints the crontab line that runs
   `fieldkit arena drain` on a cadence (`--install-cron` writes it for you).
   `fieldkit arena autonomy status` reports it; `fieldkit arena autonomy off`
   is the one-command reversal.
2. **Each drain tick** acquires the single-drain lock and, for an `rl_run`,
   enters the `LaneArbiter`: a **3-way pre-flight** (governor *allow* ∧ envelope
   *fits* ∧ a vLLM binary present — else a clean `defer` with `LANE_BIN_ABSENT`,
   never a crash), then it frees the resident chat brain (`FK_RL_RESIDENT_STOP_CMD`
   / `FK_RL_RESIDENT_START_CMD`), runs under a `MemoryWatchdog`, and **always**
   restores the prior lane on exit.
3. **It reports live** — the loop writes throttled `{step, phase, pool_score,
   last_heldout, eta_s, mem}` into `jobs.result_json` (LA-8); the cockpit Jobs
   board renders an inline progress strip with the **pool-vs-held-out** read, so
   the t2po inversion (RV-4) is visible *as it happens*.
4. **It defends the box** — the `MemoryWatchdog` enforces a unified-memory
   headroom floor (`FK_RL_OOM_FLOOR_GB`, default 4; warn at `FK_RL_OOM_WARN_GB`,
   default 8). A breach that persists ~2 s touches an abort sentinel the loop
   polls between steps → the run tears down *before* the kernel OOM-kills
   (`[[project_spark_unified_memory_oom]]`). Every run attaches a `mem_trace`
   (peak / headroom / per-phase) to its lineage + the morning standup ("RAN 1 ·
   peak 119 GB · 1 OOM-deferred").

The autonomy gate stays **operator-armed** — one `autonomy on`, not per run —
and the `$/day` governor cap + the single-lane lock still bound every tick.

## What it is not

It does **not** re-implement a GPU trainer (the proven loop is injected via the
seams / vendored later), publish a `kind: rl_run` artifact (RV-9 defers
publishable kinds to second-vertical reuse), or churn the schema. v1 ships **the
loop**, not the storefront.
