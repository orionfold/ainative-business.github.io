---
project: rlvr-loop
version: v1.0
status: BUILT 2026-06-03 (decisions signed off 2026-06-02) — staged for fieldkit v0.20.0
created: 2026-06-02
authoritative: Spark
---

# RLVR Loop v1.0 — Project Specification

> The **engine** in `pane → hands → engine`. This spec realizes
> `_FLOWS/the-machine-that-builds-machines.md` §3 **Phase 3 / Bet 1 — Closed-loop RLVR
> ("the eval harness *is* the reward model")** as the **last** of the four roadmap stubs.
> It closes the loop the first three milestones were built to land: **eval → reward →
> fine-tune → re-eval**, with the Spark's own `fieldkit.eval` verifiers as the reward
> function. It is the *payload*, not the delivery system — Arena M8 (shipped) **dispatches**
> it, Arena M11 (`spark-arena-v1.md` §15) **schedules + budget-brakes** it overnight,
> Arena M9 (§13) prices its **RL-vs-pay** ROI, Arena M10 (§14) answers **"has this been
> tried"** before it runs, and Phase-0 fan-out parallelizes its eval side.
>
> **Placement (user-confirmed 2026-06-02): standalone `_SPECS/rlvr-loop-v1.md`,** not an
> Arena `spark-arena-v1.md` section. M9/M10/M11 became Arena sections because their build is
> *connective tissue on the Arena data plane* (cost columns, a knowledge pane, a cron over the
> built drain). The RLVR engine is different: its two new modules — `fieldkit.rl` (the trainer)
> and `fieldkit.reward` (the scorer→reward adapter) — live **mostly outside `fieldkit.arena`**,
> and the loop is a self-contained training system that Arena merely *triggers and watches*. So
> the spec is standalone, with a **tight, explicit Arena seam** (it promotes the pre-drilled
> `rl_run`/`requant` job kinds and runs under the M11 drain — §6).
>
> It is grounded against Spark-measured evidence in
> [`roadmap-reconciliation.md`](roadmap-reconciliation.md) §"Phase 3" (*viable, but two
> abstractions are wrong and one risk is missing*) — the **richest correction set** in the whole
> harvest. **The named libraries §3 reached for (Unsloth-GRPO / NeMo-RL) were not what ran**; a
> hand-rolled REINFORCE-with-KL loop drove the only working single-GB10 GRPO run, the **bottleneck
> is the vLLM restart, not the trainer**, and a **training-pool↔held-out inversion** (81.8 pp) is
> the single most likely way the loop "succeeds" while regressing. This spec encodes all three.

## 1. Context

### Why this project

Through the Orionfold arc the project mastered the **artifact** surface (quantize → measure →
publish) and, in the four prior roadmap milestones, the **control** surface: a dispatcher that
runs work through the MCP harness (M8), a cost ledger (M9), a recall index (M10), and an overnight
cron that drains and governs it all (M11). Every one of those is a **delivery system**. What's
still missing is a *new kind of work to deliver* — a way for the system to **improve a model from
its own measured signal**, not just publish a static quant.

Today the only model-improvement lane is **SFT corpus-synth** (`claude-corpus-synth`): expensive,
in-session, capped by template combinatorics (`feedback_corpus_spice_pigeon_hole` — A2 saturated at
250× the template space). It produces a corpus once; it does not *close the loop*. The disruptive
move is to make the **eval harness the reward model**: `fieldkit.eval` already ships seven
deterministic verifiers — `patent_claim_validity` (7-dim), `office_action_argument` (4-dim),
`prior_art_relevance` (Spearman ρ), `irac_structure` (4-checklist regex), `mcq_letter`,
`numeric_match`, `is_refusal` — all confirmed present + exported. Those are *exactly* the
well-formed verifiers GRPO/RLVR needs to score rollouts directly, with **no learned reward model**.

### Why last (and why now)

**Why last.** It is the deepest, most compute-hungry, most uncertain bet — and it is the payload,
not the pane. Built last, it lands into a system that already **dispatches** it (M8), **schedules +
budget-brakes** it (M11), **watches** it (the M11 standup over the leaderboard), **prices** it (M9),
and **parallelizes its eval side** (Phase-0 fan-out). Build the engine before the pane and you have a
powerful loop with nowhere to land its output — the explicit `pane → hands → engine` rationale.

**Why now (SOTA).** GRPO is the 2026 post-training default behind R1-class reasoning models. It drops
the learned reward model (the verifier scores directly), works on a **single GPU with <100 examples**,
and lifts small (1–10B) models to competitive reasoning — precisely the Spark's weight class. And the
core feasibility is **already proven on this box**: `clawgym-on-spark-grpo` ran a real single-GB10 GRPO
run end-to-end (§4 grounding). The bet is **productizing that proven run into a reusable loop**, with
the three corrections the abstract roadmap claim missed baked in.

### Code reconciliation (2026-06-02 — verified against the built `fieldkit/src/fieldkit/`)

Six facts shape the decisions — and the headline is that **the engine is the deepest greenfield in the
roadmap, yet two of its three hard pieces are already modeled in shipped code**:

1. **`fieldkit.rl` and `fieldkit.reward` both do NOT exist** (`ls fieldkit/src/fieldkit/` — neither is
   present; the module list is `arena, assets, capabilities, cli, eval, harness, lineage, nim, notebook,
   publish, quant, rag, training, viz`). These are the two **new top-level modules** this spec
   introduces — the genuinely greenfield core, where M9's `fieldkit.cost` and M11's `fieldkit.budget`
   were the prior new modules.
2. **The verifiers the reward wraps are all built and exported** — `fieldkit.eval.__all__` ships the
   seven scorers above plus `VerticalBench` / `VerticalQA`, and the agent-trajectory primitives
   `Trajectory` / `TrajectoryIter` / `AgentRun` / `TurnDetail`, plus `PassAtK` / `GroupStats` for the
   group-relative math GRPO needs. `fieldkit.reward` is a **thin adapter over these**, not new scoring.
3. **The reward's `failure_class` is ALREADY MODELED.** The reconciliation note said the reward must
   emit a `(success, failure_class, auxiliary)` tuple "cf. the 9-class status enum in
   `auto-research-loop`" — and that enum is **already shipped** as `fieldkit.lineage.FailureLabel`: a
   string-valued enum (`keep`, `discard`, `crash`, `eval_budget_overrun`, `train_budget_overrun`,
   `size_blocked`, `preflight_crash`, `harness_abort`, `disqualified`, + the `baseline` seed) with an
   `is_informational` property that already encodes which classes carry usable gradient signal. So
   `fieldkit.reward` **reuses `FailureLabel`** — it does not invent an enum (RV-3).
4. **The `rl_run` lineage card is ALREADY MODELED.** `fieldkit.lineage.__all__` ships
   `Trial` / `LineageStore` / `LineageSnapshot` / `RecipeEdit`. The loop writes one `Trial` (labelled with
   a `FailureLabel`) per step into a `LineageStore`; the run's `LineageSnapshot` **is** the `rl_run`
   card and the source of the §5 "living-model" public delta chart. No new store (RV-7).
5. **The `rl_run` and `requant` job kinds are pre-drilled, tagged for this spec.** `arena/jobs.py`
   `JobKind` defines `RL_RUN = "rl_run"` and `REQUANT = "requant"` in `ALL` but **not** in
   `DISPATCHABLE`, with the in-code comment *"`rl_run`/`requant` → Phase 3 `rlvr-loop-v1`"*. The store
   schema comment (`store.py`) reads `'eval_rerun'|'measure_variants' (M8); requant/rl_run/... (later
   stubs)`. This spec **promotes `rl_run` (and `requant`) to `DISPATCHABLE`** — the exact M8-`eval_rerun`
   / M10-`reindex` pattern (RV-6).
6. **arena.db is at `USER_VERSION = 4`** (M9 → 5, M10 → 6); `jobs` carries an `arq_job_id` socket. This
   spec adds **no new arena.db table and no `user_version` bump** (RV-8) — rl_run config rides the `jobs`
   payload, the per-step trajectory rides `fieldkit.lineage`, held-out checkpoint scores ride `eval_runs`
   / the leaderboard. And **`ARTIFACT_KINDS` is still the 8 kinds** (`quant, lora, adapter, dataset,
   bench, notebook, harness, skill`) — the roadmap's named `verifier`/`reward`/`rl_run` publish kinds are
   **deferred to second reuse** (RV-9), keeping v1 scoped to the loop, not the storefront.

## 2. Scope

**In scope (v1 = the closed loop, one vertical).** The end-to-end loop on a single GB10 for **one**
vertical (patent-strategist, the existing `VerticalBench`): `sample group → score with verifier-reward
→ GRPO/REINFORCE step (LoRA) → held-out eval every ≤10 steps → select checkpoint on held-out → write
the `rl_run` lineage card`. The two new modules (`fieldkit.rl`, `fieldkit.reward`), the `rl_run`/`requant`
job-kind promotion, and the held-out-gate scheduling seam into M8/M11.

**Out of scope (deferred / other specs).**
- **Full-parameter GRPO on 30–120B** — frontier-HW territory; lives in `_FLOWS` §6 "Looking Beyond
  Spark" (Spark does LoRA-GRPO on 7–8B; a B200/SuperPOD does full-parameter — same code, bigger envelope).
- **Publishable `verifier`/`reward`/`rl_run` artifact kinds** — the §5 "verifier/reward packs" + "living
  model" products; gated to second-vertical reuse per `feedback_keep_scorer_local_until_reuse` (RV-9).
- **Multi-vertical reward packs / a reward DSL** — v1 wraps existing scorers as-is; generalization waits
  for a second consumer.
- **The auto-`tech-writer`-seed on a >X% lift** (the Ch-11 recursion wiring that feeds editorial→Book) —
  named as the §6 follow-on, not built in v1.
- **Hot-LoRA-swap in vLLM** — the *eliminable* wall-clock win (RV-5) is tracked as the top optimization
  but v1 ships on the proven kill-and-restart; closing it is a fast-follow, not a v1 gate.

## 3. Locked decisions (signed off 2026-06-02 — confirm before build)

| # | Decision | Value | Grounding |
|---|---|---|---|
| RV-1 | **Wrap the hand-rolled REINFORCE-with-KL loop, NOT a named library** | `fieldkit.rl` wraps the proven **~280-LOC REINFORCE-with-KL + kill-and-restart-vLLM** pattern from `clawgym-on-spark-grpo` (single GB10, 8 tasks/step × K=4 = 32-rollout bundle, rank-16 LoRA, temp 0.8) — the only loop that actually ran on the Spark. **Unsloth-GRPO / NeMo-RL are a documented *fallback lane*, not the default** (neither verified on the Spark; `[[project_verl_atgpo_vllm_gap]]` is the cautionary precedent). | recon §"Phase 3" #1 — the named abstractions were not used. |
| RV-2 | **The verifier IS the reward — a thin adapter over the shipped `fieldkit.eval` scorers** | `fieldkit.reward` turns any `fieldkit.eval` verifier (the 7 built ones + `VerticalBench`/`VerticalQA`) into a reward callable. **No learned reward model, no new scoring logic.** Group-relative advantage uses the built `PassAtK`/`GroupStats`. | recon "the eval harness *is* the reward model"; eval `__all__` all present. |
| RV-3 | **Reward is a `(success, failure_class, auxiliary)` tuple — reusing `fieldkit.lineage.FailureLabel`** | Binary keep/revert reward **mode-collapses** (5/5 train keeps on one knob; 0/8 held-out from a 42-row corpus). The categorical `failure_class` is **already built** as `FailureLabel` (9-class + `is_informational`) — the reward **reuses it**, not a new enum. `success` ∈ verifier pass; `auxiliary` carries per-assertion / partial-credit signal to densify the gradient beyond a scalar. | recon mode-collapse + 9-class enum; built `FailureLabel`. |
| RV-4 | **Held-out eval every ≤10 steps is a HARD gate; checkpoint selection is held-out-ONLY** | Pool-convergence is a trap: `t2po` hit **pool 87.5% vs held-out 5.7% at step 45 — an 81.8 pp inversion**. The loop evaluates a **frozen held-out split** every ≤10 steps and **selects the published checkpoint on held-out score, never pool**. The held-out eval is dispatched as an **M8 `eval_rerun` job** (M11 schedules it — RV-6), so the gate is a control-plane artifact, not a manual step. | recon §"Phase 3" risk — the missing inversion risk. |
| RV-5 | **Pin vLLM; the top wall-clock target is restart-elimination, NOT the trainer** | Pin **one** vLLM version (6 API drifts across 2 minor versions, one silent return-shape change). Of the ~15-min step, **rollout ≈13 min + vLLM restart ≈3.5 min + trainer ≈22 s** — the restart is ~25% of wall and the *only* eliminable quarter. The optimization target is closing the **hot-LoRA-swap gap** (vLLM `/v1/load_lora_adapter`), not speeding the ≈22 s trainer. v1 ships on kill-and-restart; the swap is a fast-follow. | recon runtime-drift tax + step breakdown; `[[reference_r1_qwen3_gguf_detok_spaces]]` vLLM-lane care. |
| RV-6 | **Promote `rl_run` (and `requant`) to `DISPATCHABLE`; dispatch is async/overnight ONLY** | Flip the pre-drilled `JobKind.RL_RUN`/`REQUANT` from named-stub to `DISPATCHABLE` (the M8-`eval_rerun` / M10-`reindex` pattern). The 8.5 h run **cannot be a synchronous click** — its execution home is the **M11 cron drain, single-lane** (`spark-arena-v1.md` §15.6). A manual `fieldkit rl run` works without M11; *autonomous* runs require it (soft prerequisite). `requant` re-quantizes the lifted checkpoint after a held-out win. | recon envelope; jobs.py socket; M11 §15.6. |
| RV-7 | **The loop's lineage rides `fieldkit.lineage` — no new store** | Each step writes one `Trial` (labelled with a `FailureLabel`) into a `LineageStore`; the run's `LineageSnapshot` **is** the `rl_run` card and the source of the §5 living-model delta chart. The reward tuple's `failure_class` is exactly a `FailureLabel`, so the loop record and the reward signal share one vocabulary. | built `fieldkit.lineage.__all__`. |
| RV-8 | **No new arena.db table, no `user_version` bump** | rl_run **config** rides the `jobs` row payload (+ the `arq_job_id` socket); per-step **trajectory** rides `fieldkit.lineage`; **held-out checkpoint scores** ride `eval_runs` / the leaderboard. arena.db stays at whatever M9/M10 left it (≤6). Connective on storage, like M11 (AH-9). | store `USER_VERSION`; recon — minimize schema churn. |
| RV-9 | **v1 ships the LOOP, not the storefront — publishable kinds deferred to second reuse** | `ARTIFACT_KINDS` stays at **8**. Per `feedback_keep_scorer_local_until_reuse`, the reward adapter + the `rl_run` lineage card stay local until a **second vertical** reuses them; only then promote to `kind: verifier`/`reward`/`rl_run` (the §5 productization, a follow-on spec). Keeps v1 scoped to the engine. | built `ARTIFACT_KINDS` (8); the scorer-local memory. |
| RV-10 | **≥100-row corpus floor + a frozen held-out split; trainer-resident, one lane** | 42 rows mode-collapsed (0/8 held-out). The corpus floor is **≥100 examples** with a **frozen held-out split carved before step 0** (feeds RV-4). The envelope holds at **~30 GiB margin** (50 pretrain + 28 trainer + 20 vLLM = 98/128) — **trainer resident, one vLLM lane, no second model** (the 2026-04-22 OOM landmine). | recon ≥100-row floor; `baseline-training-loop-on-spark` envelope; `[[project_spark_unified_memory_oom]]`. |
| RV-11 | **RL-headroom gate — assert the init scores in the ~30–70% band on the selection held-out BEFORE the run** *(added 2026-06-05, generalized from the astrodynamics C5 null)* | RLVR **amplifies existing competence — it cannot teach from zero, and has nothing to optimize at ceiling.** Before a run, score the init policy on the **exact frozen held-out RV-4 selects on**: **≥~85% → no headroom** (most GRPO groups are uniformly-correct → zero group-relative advantage `group_advantage`→0 → no update; ship the init instead); **≤~15% → no reward density** (no positive rollouts → no signal). GO only in the **Goldilocks band (~30–70%)**. Caller-run for v1 (`RLLoop` already returns step-0 held-out in `summary()` — log it as the gate value); design the selection held-out **error-mined** on the init's measured weak spots, kept **separate** from the publish/generalization held-out. | Astro C5: a perfect end-to-end run with **zero lift** — the held-out was 0.958@step-0 (saturated) → `selected_step=0`, 5 degenerate steps. Distinct from RV-R5 (that's a *mid-run* plateau at a corpus-quality ceiling; this is a *pre-run* go/no-go). `[[feedback_rlvr_headroom_gate]]`; astro `AV-12`/`AV-R6`. |

## 4. Grounding (from `roadmap-reconciliation.md` §"Phase 3")

- **Core feasibility CONFIRMED with a real run.** `clawgym-on-spark-grpo`: **single GB10, 42-task pool
  (8 drawn/step × K=4 = 32-rollout bundle), 34 GRPO steps in 8.5 h**, binary task-grader as reward, **no
  learned reward model** — `task_complete 0/158 → 154/158 (+97.5 pp)`, mean turns −58%, wall −62%.
  "<100 examples + single GPU + verifier-scores-directly" **holds**. Envelope holds
  (`baseline-training-loop-on-spark`: 50 GiB pretrain + ~28 GiB trainer + ~20 GiB vLLM ≈ 98/128,
  **~30 GiB margin**) ⇒ RV-10.
- **COMPLICATES — the named abstractions were not used (RV-1).** Neither Unsloth-GRPO nor NeMo-RL drove
  the working run: a **hand-rolled ~280-LOC REINFORCE-with-KL + kill-and-restart vLLM** (no hot LoRA
  swap in vLLM 0.20) did. **The bottleneck is the rollout/restart, not the trainer:** rollout ≈13 min,
  **vLLM restart ≈3.5 min**, trainer ≈22 s ⇒ RV-5.
- **COMPLICATES — the missing risk: training-pool↔held-out inversion (RV-4).** `t2po`: at step 45
  **pool 87.5% vs held-out 5.7% — 81.8 pp inversion**; per-assertion plateaued at **~47.7%** (synth-noise
  floor ~80%); T²PO trailed plain GRPO at *more* wall (18.5 h vs 8.5 h). **Pool-convergence is a trap;
  held-out-every-10-steps is mandatory.**
- **SHARPENS the reward (RV-3).** Binary keep/revert is too sparse: `trajectory-eval` /
  `distill-architect-lora-from-trajectories` saw **mode-collapse (5/5 train keeps on one knob) and 0/8
  held-out generalization** from a 42-row corpus. The fix is a **categorical-failure-class tuple** —
  realized by the built `FailureLabel` 9-class enum — over a **≥100-row corpus** (RV-10).
- **Runtime drift tax (RV-5).** `runtime-frontier-six-patches-on-spark`: **2 vLLM minor versions = 6 API
  drifts (one silent return-shape change)**; ESamp-style interventions cost ~0.97–1.12× tok/s but only
  pay off on *unsaturated* tasks (`pass-at-k`: +6.67 pp pass@8 on DS-R1×AIME, −0.61 pp noise on saturated
  Qwen×HumanEval). **Pin the version; budget patch-the-runtime time.**

**Spec-feedable constants (head-start, from `roadmap-reconciliation.md` §"Spec-feedable facts"):**
`GRPO_WALL_SPARK_GB10 ≈ 15 min/step` · step = rollout ≈13 min / **restart ≈3.5 min** / trainer ≈22 s ·
`ENVELOPE_MARGIN ≈ 30 GiB` · `POOL_HELDOUT_INVERSION = 81.8 pp @ step 45` · `PER_ASSERTION_CEILING_V1 ≈
47.7%` (synth floor ~80%) · reward `(success, failure_class, auxiliary)`, **≥100-row corpus** ·
`VLLM_API_DRIFT = 6 / 2 minor` (1 silent).

## 5. Architecture

**Two new modules + a reused store + an Arena seam.** No new arena.db table (RV-8); the loop's record
lives in `fieldkit.lineage` (RV-7).

**`fieldkit.reward` — the scorer→reward adapter (RV-2/RV-3).** Thin layer over `fieldkit.eval`:

```
fieldkit.reward
  Reward(success: bool, failure_class: FailureLabel, auxiliary: dict)   # the tuple — failure_class is a lineage.FailureLabel
  RewardAdapter(verifier: <fieldkit.eval scorer>)                       # wraps patent_claim_validity / irac_structure / ...
    .score(rollout) -> Reward                                           # success ← verifier pass; auxiliary ← per-assertion / partial credit
  group_advantage(rewards: list[Reward]) -> list[float]                 # group-relative (uses eval.GroupStats / PassAtK)
  RewardError
__all__ = ["Reward", "RewardAdapter", "group_advantage", "RewardError"]
```

**`fieldkit.rl` — the GRPO/REINFORCE driver (RV-1/RV-5).** Wraps the proven loop; one lane, trainer
resident; pins vLLM:

```
fieldkit.rl
  GRPOConfig(base, lora_rank=16, group_k=4, tasks_per_step=8, temp=0.8,
             heldout_every=10, vllm_pin="<version>", max_steps, corpus_min=100)   # RV-1/4/5/10
  RLLoop(config, reward: RewardAdapter, bench: VerticalBench)
    .run() -> LineageSnapshot      # sample group → reward → REINFORCE+KL step (LoRA) → [every ≤10] held-out gate → Trial
  RLLoopError
__all__ = ["GRPOConfig", "RLLoop", "RLLoopError"]
```

**The loop (one step), envelope-respecting:**

```
RLLoop.run()  (single-lane, trainer resident — RV-10):
  carve frozen held-out split (≥100-row corpus, split before step 0)              [RV-10]
  for step in range(max_steps):
    sample 8 tasks × K=4 rollouts   via the pinned vLLM lane                       [RV-1]   (~13 min)
    rewards ← [RewardAdapter.score(r) for r in rollouts]   # (success, FailureLabel, aux)  [RV-2/3]
    adv ← group_advantage(rewards)
    REINFORCE-with-KL step on the LoRA                                             [RV-1]   (~22 s)
    kill + restart vLLM to load the updated LoRA                                   [RV-5]   (~3.5 min — the eliminable quarter)
    write Trial(failure_class=…, metrics=…) -> LineageStore                        [RV-7]
    if step % heldout_every == 0:                                                  [RV-4]
        enqueue eval_rerun(heldout_split)  ->  M8 dispatcher                       [RV-6]   # held-out gate, NOT pool
        record held-out score on eval_runs / leaderboard
  select published checkpoint = argmax(held-out score)   # NEVER pool             [RV-4]
  return LineageSnapshot   # the rl_run card (RV-7) → §5 living-model delta chart
```

**Arena seam (RV-6).** `JobKind.RL_RUN` and `REQUANT` move into `DISPATCHABLE`. A `compare`-loss in
Arena (or a manual trigger) `enqueue_job(rl_run, payload={base, vertical, corpus, config})`; the M11
cron drains it overnight, single-lane, behind the budget governor; on a held-out win, an optional
`requant` re-quantizes the lifted checkpoint; the leaderboard updates and **the loop closes visibly** —
the entire reason the pane was built first. The held-out gate (RV-4) reuses the *already-dispatchable*
M8 `eval_rerun` path, so no new dispatch logic — only the two kind-promotions.

## 6. Sequencing — prerequisites + what RLVR feeds

**Prerequisites (one built, three soft).**
- **M8 (shipped)** — the `rl_run` dispatch socket + the `eval_rerun` path the held-out gate reuses. The
  one *hard* dependency, and it's done.
- **M11 (`§15`, soft)** — the overnight drain + budget brake. RL without M11 is a loop with no overnight
  home; a manual `fieldkit rl run` works, but *autonomous* `rl_run` needs M11's single-lane cron + the
  governor's RL-vs-frontier decision (RV-6).
- **M9 (`§13`, soft)** — the cost ledger that prices **RL-vs-pay** ("cheaper to RLVR a local model to
  threshold, or pay frontier per call?"); the governor consults it *before* approving an `rl_run`. Absent
  M9, the decision degrades to a token+envelope guard (the M11 AH-5 fallback).
- **M10 (`§14`, soft)** — the pre-flight recall query: "has this been tried?" returns the internal `t2po`
  finding (47.7% ceiling, +33% wall for nothing) *before* the governor approves, so a known-dead run is
  declined or redirected.

**What RLVR feeds.**
- **Closes the visible loop** — `compare`-loss → `rl_run` → held-out lift → leaderboard. The posture
  shift the whole roadmap is about: the operator *dispatches and watches*, the box *improves itself*.
- **The §5 "living-model" product (Phase-3 launch)** — a model re-RLVR'd against a freshening bench, sold
  on a **public delta chart from `fieldkit.lineage`** (the `LineageSnapshot` of RV-7). The first §5
  per-phase `product-writer` launch with a *living* hero, per the HANDOFF editorial overlay.
- **The editorial→Book recursion (follow-on, §2 out-of-scope)** — when an `rl_run` lifts a bench >X%,
  auto-scaffold a `tech-writer` seed (mirrors `frontier-scout`→`tech-writer`), wiring Ch-11's recursion
  so the autonomous loop *feeds* the publishing pipeline. Named here, built after v1.
- **Frontier extrapolation (`_FLOWS` §6)** — Spark LoRA-GRPO on 7–8B is the cheap proof; the identical
  code does full-parameter GRPO on 30–120B on a B200/SuperPOD. Prove the loop cheaply here; rent frontier
  HW only for the one run that needs it.

## 7. Risk register (this spec's local IDs — the Arena register R13–R26 lives in `spark-arena-v1.md` §10)

| ID | Risk | Likelihood | Impact | Mitigation | Fallback |
|---|---|---|---|---|---|
| RV-R1 | **Pool↔held-out inversion masks a regression** — the loop "succeeds" on the training pool while held-out collapses (the 81.8 pp `t2po` finding) | **high** (it already happened) | a shipped checkpoint that *regressed* | held-out eval ≤ every 10 steps as a **hard gate**; checkpoint selection is **held-out-only**, never pool (RV-4); the gate runs as a dispatched M8 `eval_rerun`, not a skippable manual step | abort the run if held-out doesn't track pool within N steps; the leaderboard-regression producer (M8 `check_and_enqueue_regressions`) catches a bad publish downstream |
| RV-R2 | **vLLM restart dominates wall / an API drift breaks the loop mid-run** — 6 drifts / 2 minor versions, one silent | med | ~25% wasted wall; a silent return-shape change corrupts rollouts | **pin the version** (RV-5); restart-elimination (hot-LoRA-swap) is the tracked top optimization; the proven kill-and-restart is the v1 baseline | the kill-and-restart loop already works at 8.5 h/run; degrade to it if the swap path regresses; budget explicit "patch-the-runtime" time |
| RV-R3 | **Reward mode-collapse / sparse signal** — binary keep/revert collapses to one knob (0/8 held-out from 42 rows) | med | the loop optimizes a degenerate policy | the `(success, failure_class, auxiliary)` tuple over the built `FailureLabel` (RV-3) + the ≥100-row corpus floor (RV-10) densify the gradient | widen the auxiliary signal (per-assertion partial credit); add a diversity/anti-collapse term; fall back to a larger corpus before more steps |
| RV-R4 | **Overnight OOM** — a second lane loads while the trainer is resident, or vLLM restart orphans `EngineCore` (~108 GB) | med | box hang (the 2026-04-22 landmine) | trainer-resident **one-lane** envelope with ~30 GiB margin (RV-10); the M11 governor's envelope guard + one-drain-at-a-time lock (R24); lane teardown does `pkill -f 'vllm\|EngineCore'` | the M11 drain lock bounds blast radius to one pass; OOM kills the pass, not the box (`[[feedback_vllm_engine_core_orphan]]`) |
| RV-R5 | **Synth-noise ceiling — RL alone plateaus** — per-assertion stalls ~47.7% against a ~80% synth-noise floor; more steps buy nothing (T²PO: +10 h wall for a *worse* result) | med | wasted compute past the held-out peak | stop at the held-out peak (RV-4), not the pool peak; treat ~47.7% as a **corpus-quality** signal, not an RL target — improve the corpus (SFT/curation) before more RL | M10 pre-flight returns the known ceiling so the governor declines a re-run; redirect budget to corpus work or frontier escalation (M9 ROI) |

## 8. Release gate

**~`fieldkit v0.20.0`** (after M9 `~0.17.0` / M10 `~0.18.0` / M11 `~0.19.0`). Cut via `fieldkit-curator`
(separate action). The wheel ships `fieldkit.rl` + `fieldkit.reward`; `audit-docs rl` + `audit-docs
reward` clean; `docs/api/rl.md` + `docs/api/reward.md` authored; the `rl_run`/`requant` `DISPATCHABLE`
promotion lands with its `arena/jobs.py` tests. **v1 ships the loop; the publishable
`verifier`/`reward`/`rl_run` artifact kinds (RV-9) are a later release.**

## 9. Deliverables

| Artifact | Surface | Gate |
|---|---|---|
| **New module `fieldkit.reward`** — `Reward` tuple (reusing `lineage.FailureLabel`) + `RewardAdapter` over the 7 `fieldkit.eval` scorers + `group_advantage` | `fieldkit` PyPI | `audit-docs reward` clean; adapter unit tests over each verifier |
| **New module `fieldkit.rl`** — `GRPOConfig` + `RLLoop` (REINFORCE-with-KL, pinned vLLM, kill-and-restart) → `LineageSnapshot` | `fieldkit` PyPI | `audit-docs rl` clean; a short smoke run (≤2 steps) on the patent corpus completes + writes Trials |
| **`rl_run`/`requant` → `DISPATCHABLE`** + the held-out-gate `eval_rerun` enqueue path | `fieldkit.arena.jobs` | `test_jobs.py` extension (rl_run dispatch + held-out enqueue); no `user_version` bump (RV-8) |
| **Held-out gate wiring** — eval ≤ every 10 steps as a dispatched `eval_rerun`; checkpoint selection on held-out score | `fieldkit.rl` + `arena/jobs.py` | a seeded loop selects the held-out-best checkpoint, not the pool-best |
| **`rl_run` lineage card** — the `LineageSnapshot` rendered as the run record (source of the §5 delta chart) | `fieldkit.lineage` (reused) | snapshot round-trips; FailureLabel distribution present |
| Docs `docs/api/rl.md` + `docs/api/reward.md` | `fieldkit` docs | `audit-docs` gate |
| Release `~fieldkit v0.20.0` | PyPI + tag | `fieldkit-curator` action (separate) |

## 10. Change log

| Date | Change | Author |
|---|---|---|
| 2026-06-05 | **RV-11 refined — read the gate PER-FAMILY, not just aggregate (astro C6 STEP-1.5).** First proper application of RV-11: an error-mined transfer set scored the SFT init at **20.83% aggregate** but **bimodally** — some families fully generalized (100%), the target weak spots at **0%**, only ~4 families in the productive (0,1) band. Lesson: a **0% family is the mirror of a 100% family** — both are zero group-advantage; 0% is an SFT-coverage gap, not RL headroom. Build the selection held-out from families with pass-rate strictly in (0,1). Caveat: a single-sample preflight under-estimates GRPO headroom (the loop samples a group). `[[feedback_rlvr_headroom_gate]]`; astro `AV-12`. | Manav (with Claude) |
| 2026-06-05 | **+RV-11 (RL-headroom gate)**, generalized from the first real-GPU run of this engine — the astrodynamics C5 RLVR run (`astrodynamics-vertical-v1.md` AV-12/AV-R6). The loop ran flawlessly end-to-end but produced **zero lift**: the selection held-out was already saturated by the strong 86% SFT init (0.958@step-0), so GRPO had no headroom (`selected_step=0`, 5 degenerate zero-advantage steps). RV-11 makes the predictor a **pre-run go/no-go**: score the init on the exact RV-4 selection set, proceed only in the ~30–70% Goldilocks band (RLVR amplifies existing competence — useless at ceiling, signal-starved at floor). Distinct from RV-R5 (mid-run plateau). Validates RV-3/RV-4/`group_advantage` worked exactly as designed — the gap was held-out *design*, not the loop. Memory `[[feedback_rlvr_headroom_gate]]`. Docs only. | Manav (with Claude) |
| 2026-06-03 | **BUILT** — all 10 decisions landed (§10.1 as-built map). New modules `fieldkit.reward` (RewardAdapter over the 7 eval scorers + `group_advantage`, reward tuple reusing `lineage.FailureLabel`) + `fieldkit.rl` (`GRPOConfig`/`RLLoop`, injected GPU seams, held-out-only checkpoint selection, ≥100-row floor); `rl_run`/`requant` promoted to `DISPATCHABLE` (overnight-only, `server.py` POST allowlist stays narrow) + `run_rl_loop`/`requant_checkpoint` harness tools; no arena.db schema change (RV-8). Suite 1211 pass, audit-docs reward 4/4 + rl 3/3 clean, build 497 pages, audit-landing 4/4, cockpit rebaked. Staged in `[Unreleased]` for `fieldkit v0.20.0`. | Manav (with Claude) |
| 2026-06-02 | **Initial spec authored — v1.0 locked, UNBUILT.** Realizes `_FLOWS` §3 **Phase 3 / Bet 1** (closed-loop RLVR) as the **last** of the four roadmap stubs; **standalone** placement user-confirmed (the engine spans the new `fieldkit.rl`/`fieldkit.reward`, mostly outside `fieldkit.arena`). 10 locked decisions (RV-1…10, signed off — wrap the hand-rolled REINFORCE-with-KL loop not a library; verifier-is-the-reward thin adapter; `(success, failure_class, auxiliary)` tuple **reusing the built `lineage.FailureLabel`**; held-out-every-≤10-steps **hard gate** w/ held-out-only checkpoint selection; pin vLLM + restart-elimination as the top win; promote `rl_run`/`requant` to `DISPATCHABLE`, async/overnight only; lineage rides `fieldkit.lineage` — no new store; **no arena.db table / no `user_version` bump**; publishable kinds deferred to second reuse; ≥100-row corpus + one-lane envelope). 5 risks (RV-R1…R5: pool↔held-out inversion · vLLM restart/drift · reward mode-collapse · overnight OOM · synth-noise ceiling). New abstractions `fieldkit.rl` + `fieldkit.reward`. Code-reconciled against the built `fieldkit/src/fieldkit/`: **`fieldkit.rl`/`fieldkit.reward` absent** (the two new modules); the reward's `failure_class` + the `rl_run` card **already modeled** in `fieldkit.lineage` (`FailureLabel` 9-class enum + `Trial`/`LineageStore`); the `rl_run`/`requant` job kinds **pre-drilled** in `arena/jobs.py` (tagged "→ Phase 3 `rlvr-loop-v1`"); the 7 verifiers + agent-trajectory primitives present in `fieldkit.eval`; `ARTIFACT_KINDS` still 8. Grounded against `roadmap-reconciliation.md` §"Phase 3" (the richest correction set). **Spec only — unbuilt;** release gate ~`fieldkit v0.20.0`. **This is the fourth and final `_FLOWS` §3 spec stub — all four are now written.** | Manav (with Claude) |

## 10.1 As-built (BUILT 2026-06-03)

All 10 decisions landed as written; the build is staged in `[Unreleased]` for the
`fieldkit v0.20.0` cut.

| Decision | As-built |
|---|---|
| RV-1 | **`fieldkit.rl`** (new module) wraps the proven loop as **orchestration with injected GPU seams** — `GRPOConfig` + `RLLoop` drive split→sample→reward→group-relative step→held-out gate→checkpoint-select→lineage; `sampler` / `trainer` / `heldout_eval` inject (the `dispatch_job(runner=…)` pattern), so torch/vLLM never import at module load. `gpu_seams` raises until the pinned-vLLM backend is vendored into `fieldkit[rl]` (`project_verl_atgpo_vllm_gap`) — v1 ships the loop, not a re-implemented GPU trainer. |
| RV-2 | **`fieldkit.reward`** (new module) — `RewardAdapter` is a thin layer over any `fieldkit.eval` scorer (7 shipped + `exact_match`/`contains`), kwargs filtered to each scorer's signature (judge / `rel_tolerance` / `strip_think`). `group_advantage` = the value-network-free GRPO baseline; degenerate group → zero vector. |
| RV-3 | `Reward(success, failure_class, auxiliary)` — `failure_class` **reuses `fieldkit.lineage.FailureLabel`** (`KEEP`/`DISCARD`/`CRASH`, no new enum); `auxiliary["score"]` is the dense partial-credit `.scalar`. A raising verifier → caught `CRASH` reward (one bad rollout never sinks the group). |
| RV-4 | **Held-out gate + held-out-ONLY checkpoint selection** — `RLLoop` evaluates the frozen split every `heldout_every` steps; `_select_checkpoint` is `argmax` over **held-out** scores; `summary()["selected_on"] == "heldout"`. Test proves it picks the held-out-best step while the pool climbs monotonically past it. `heldout_patience` is the RV-R1 early-stop. |
| RV-5 | `GRPOConfig.vllm_pin` records the pinned version; the trainer seam owns the kill-and-restart (the eliminable quarter); hot-LoRA-swap noted as the fast-follow. |
| RV-6 | `JobKind.RL_RUN` + `REQUANT` promoted into `DISPATCHABLE` (now `== ALL`); `default_runner` branches call the new `run_rl_loop` / `requant_checkpoint` harness MCP tools; `_persist_rl_run` writes the aggregate digest. **Async/overnight only** — the `server.py` `POST /api/jobs` allowlist stays narrow (no synchronous 8.5 h click); `rl_run` enqueues programmatically + drains under the M11 cron. |
| RV-7 | The loop writes one `Trial` (`FailureLabel`-labelled) per step + a `heldout-gate` Trial per eval into a `LineageStore`; `RLLoop.run` returns the `rl_run` `LineageSnapshot`. **No new store.** |
| RV-8 | **No new arena.db table, no `user_version` bump** — verified by a test (`user_version` unchanged across an `rl_run` dispatch). |
| RV-9 | `ARTIFACT_KINDS` stays at 8; publishable `verifier`/`reward`/`rl_run` kinds deferred to second-vertical reuse. |
| RV-10 | `RLLoop.run` refuses a corpus below `corpus_min` (`RLLoopError`); `_split_corpus` carves the frozen held-out split before step 0 from a seeded shuffle. |

**Verified:** suite **1211 pass / 16 skip** (+28: `test_reward.py` + `test_rl.py` +
the `test_jobs.py` extension); `audit-docs reward 4/4 + rl 3/3 + arena` clean;
`astro build` **497 pages** (new `/fieldkit/api/rl/` + `/fieldkit/api/reward/`);
both rendering verifiers green; `audit-landing` 4/4; cockpit `_webui` **rebaked**.
**Operator action left** (deliberate non-default): the real GPU backend
(`gpu_seams`) is a documented fast-follow — vendor a pinned vLLM with an
aarch64+CUDA-13 wheel + the `clawgym` REINFORCE loop into `fieldkit[rl]`; until
then callers inject their own seams (the orchestration is fully functional).
**Release:** staged in `[Unreleased]`; the `fieldkit v0.20.0` cut is a separate
`fieldkit-curator` action.

## 11. References

### Internal
- **MTBM roadmap (this = Phase 3 / Bet 1):** `_FLOWS/the-machine-that-builds-machines.md` §3 "Phase 3 — Closed-loop RLVR"
- **Grounding (viable, two abstractions wrong, one risk missing):** `_SPECS/roadmap-reconciliation.md` §"Phase 3" + the `rlvr-loop-v1.md` spec-feedable facts
- **The Arena seam (dispatch + overnight home + budget brake):** `_SPECS/spark-arena-v1.md` §12 (M8 dispatcher, shipped), §13 (M9 cost/ROI), §14 (M10 recall pre-flight), §15 (M11 cron drain + governor)
- Spec format precedents: `_SPECS/hermes-harness-v1.md` (standalone sibling), `_SPECS/spark-arena-v1.md` §15 (the M11 locked-decisions template)
- The proven loop: `articles/clawgym-on-spark-grpo/` (the ~280-LOC REINFORCE run + step breakdown)
- The inversion risk: `articles/t2po-uncertainty-guided-rl-on-spark/` (81.8 pp pool↔held-out; ~47.7% per-assertion ceiling)
- The mode-collapse evidence: `articles/trajectory-eval-is-the-agent-flailing/`, `articles/distill-architect-lora-from-trajectories/`
- The 9-class enum precedent (now built as `FailureLabel`): `articles/auto-research-loop-on-spark/`
- The runtime-drift tax: `articles/runtime-frontier-six-patches-on-spark/`, `articles/test-time-distilling-for-exploration/`
- The envelope: `articles/baseline-training-loop-on-spark/`
- fieldkit modules reused/extended: `fieldkit/src/fieldkit/{eval,lineage,arena,training}/`

### Memory cross-references (`[[name]]`)
- `[[project_verl_atgpo_vllm_gap]]` — why a named RL library is a fallback, not the default (vllm-pin pain on aarch64+CUDA-13)
- `[[project_spark_unified_memory_oom]]` — the 128 GB one-lane envelope the loop respects (RV-10)
- `[[feedback_vllm_engine_core_orphan]]` — `pkill -f 'vllm\|EngineCore'` in lane teardown (RV-R4)
- `[[feedback_keep_scorer_local_until_reuse]]` — why the publishable kinds defer to second reuse (RV-9)
- `[[feedback_reasoning_model_npredict]]` — reasoning-model gen-length care during rollouts
- `[[reference_r1_qwen3_gguf_detok_spaces]]` — vLLM-lane reasoning-format care (RV-5)
