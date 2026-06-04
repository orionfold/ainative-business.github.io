---
project: rl-lane-autonomy
version: v1.0
status: PARTIAL — LA-1..11 (self-driving + safety backend) BUILT 2026-06-03; education layer LA-12..16 = fast-follow
created: 2026-06-03
authoritative: Spark
---

# RL Lane Autonomy v1.0 — Project Specification

> The **self-driving** of `pane → hands → engine`. The four `_FLOWS` §3 builds are shipped and
> on PyPI (`fieldkit v0.21.0`), but the engine's longest job — an ~8.5 h `rl_run` — is still
> **human-armed at two physical chokepoints**: the operator brings up the one vLLM lane the box can
> hold, and the operator arms the overnight cron. This spec closes both, and adds the two things a
> multi-hour unattended GPU job *must* have to be trustworthy: **live step-level reporting** so the
> operator always knows what's happening, and a **telemetry-correlated OOM defense** so the box
> protects itself against the 2026-04-22 unified-memory landmine. It then does the on-brand thing —
> **teaches the operator at every step** from the curriculum already published in the deep-dives.
>
> **Placement (proposed): standalone `_SPECS/rl-lane-autonomy-v1.md`.** It is *not* one of the four
> original `_FLOWS` §3 bets — those are done. It is the **post-roadmap follow-on** the HANDOFF named
> as "the deliberate operator follow-on": operationalize the Phase-3 engine's operator-armed gap (RV-6),
> complete the Phase-2 autonomy the M11 cron left as an opt-in, and consume the Phase-cost-plane
> telemetry. Its one new module, `fieldkit.arena.lane`, is an **Arena submodule** (like
> `arena.scheduler`/`arena.jobs`), so — unlike `fieldkit.rl`/`fieldkit.reward` — it lives *inside*
> `fieldkit.arena`; hence standalone-spec-but-arena-module, the inverse of `rlvr-loop-v1`.
>
> It is grounded against the **shipped** `fieldkit/src/fieldkit/`: the hard primitives it needs —
> the memory envelope, the lane lifecycle, the drain lock, the telemetry sampler, the progress
> column, the curriculum — **all already exist**. v1 is overwhelmingly *connective tissue*, not new
> physics. The single genuinely-external blocker (a pinned aarch64+CUDA-13 vLLM the operator can
> install) is unchanged from `rlvr-loop-v1` and degrades to a clean `defer`, not a crash.

## 1. Context

### Why this project

`rlvr-loop-v1` shipped `rl_run`/`requant` as `DISPATCHABLE` M8 jobs that drain under the M11 cron
behind the M9 governor (RV-6). The loop is real; what is *not* automated is the envelope around it.
Three deliberate gaps keep every run human-armed:

1. **No managed serving lane.** `fieldkit._rl_gpu_serve.VLLMLane` can `start`/`stop`/`restart` a vLLM
   process, but **nothing on the dispatch path drives it** — the operator brings the lane up by hand
   and the loop assumes it is there. vLLM is deliberately not a `fieldkit[rl]` dep (no aarch64+CUDA-13
   wheel — `[[project_verl_atgpo_vllm_gap]]`), so it is served as a separate process; *managing its
   lifecycle* from the control plane is the missing half.
2. **No memory arbiter on the dispatch path.** `fieldkit.budget.MemoryEnvelope` ships `fits()` /
   `headroom_gb()` / `lane_footprint()` — but nothing *enforces* "tear down the resident chat brain
   before spawning a 7B-plus-training lane." Auto-spawning today walks straight into the one-lane
   landmine (`[[project_spark_unified_memory_oom]]`).
3. **No registered cron.** M11's `run_drain_cycle` ships; wiring `/schedule` is an explicit opt-in
   "so the autonomy gate stays human-armed" (AH as-built). Until it is registered, a queued `rl_run`
   sits forever — autonomy is one config step away but no operator-legible action arms it.

And even once those are closed, a multi-hour unattended job that reports only `running → done` is
**operationally blind**: the operator cannot tell a healthy run from a stuck one, cannot watch the
held-out line that decides whether the checkpoint is worth keeping (the t2po inversion, RV-4), and
gets no warning before the box hangs on OOM. This spec makes the run **observable, self-defending,
and self-explaining** — the three things that turn "technically dispatchable" into "safe to leave
running overnight."

### Why now

The GPU backend is no longer the blocker. As of `fieldkit v0.21.0` the real seams are vendored
(`fieldkit.rl.gpu_seams` over `fieldkit._rl_gpu_serve` + `fieldkit._rl_gpu_trainer`, behind the
`fieldkit[rl]` extra — `[[reference_fieldkit_rl_gpu_backend]]`). The *only* remaining prerequisite for
a live run is installing a compatible pinned vLLM. That shifts the critical path squarely onto the
**control-plane machinery this spec defines** — all of which is buildable and GPU-free-testable
**now**, ahead of the vLLM install, and goes live the moment a compatible vLLM is present.

### Code reconciliation (2026-06-03 — verified against the built `fieldkit/src/fieldkit/`)

The headline: **this spec is mostly wiring shipped primitives together.** Verified facts:

1. **The memory-decision primitive already exists.** `fieldkit.budget.MemoryEnvelope` ships
   `headroom_gb()` / `lane_footprint(lane_id)` / `fits(lane_id)`, and `EscalationReason` already
   carries `OOM_ENVELOPE`. The arbiter *consumes* these; it adds one sibling reason
   (`LANE_BIN_ABSENT`), not a new decision engine.
2. **The lane lifecycle already exists.** `fieldkit._rl_gpu_serve` ships `VLLMLane`
   (`ensure_started` / `start` / `stop` / `restart` / `is_running`), `serve_command`, and an
   **EngineCore-aware `stop_command`** (`pkill -9 -f 'vllm|EngineCore'` + resource-tracker reap —
   `[[feedback_vllm_engine_core_orphan]]`). The arbiter drives this; it does not re-implement serving.
3. **The cron home already exists.** `fieldkit.arena.scheduler` ships `DrainLock` (one-drain-at-a-time
   with stale-pid steal) + `run_drain_cycle` + `build_standup`. The arbiter nests *inside* the drain
   lock for GPU kinds; the autonomy CLI registers/removes the routine that calls `run_drain_cycle`.
4. **The telemetry sampler already exists and already samples memory.** `fieldkit.arena.server`'s
   `TelemetryHub` samples `gpu_util` / `gpu_temp_c` / unified-mem (via `nvidia-smi` at the telemetry
   interval) + `/proc/meminfo`, fanned out on `/api/telemetry/stream` (500 ms). The OOM watchdog
   **subscribes to the existing sample** — no new sampler.
5. **The live progress channel already exists.** `jobs.result_json` is a `TEXT` column; `patch_job`
   can write it mid-run; `jobs_event_stream` already re-emits the board on change. Throttled progress
   rides `result_json` while `status='running'` — **no schema change** (continues RV-8 / AH-9; arena.db
   stays at `user_version 6`). The SSE parser gotcha is known (`[[feedback_sse_starlette_crlf]]`:
   `EventSourceResponse` emits CRLF).
6. **The cross-process signal precedent already exists.** The cron drain runs in a **separate process**
   from the serving sidecar (sidecar holds `TelemetryHub`; the cron subprocess holds the loop). So
   watchdog→loop "abort" cannot be in-memory — it rides a **filesystem sentinel** (the `DrainLock`
   pattern), keeping `result_json` single-writer (the loop) and the DB schema untouched.
7. **The curriculum already exists, fully authored.** `articles/the-machine-improves-itself/article.md`
   ships the RLVR explainer set as `:::define[RLVR]`, `:::define[GRPO]`, `:::define[Held-out split]`,
   `:::pitfall[The loop reliably lies if you select the checkpoint on the training pool]`,
   `:::pitfall[The trainer is not the bottleneck — the vLLM restart is]`, `:::math[…]`, `:::deeper`,
   `:::hardware[…]`. The education layer **surfaces these contextually** — it does not write new copy.
8. **The guidance interaction precedent already exists.** The demo `boot.js` ships a Discord-style
   "interact here next" coach (blurple ping-ring, one-target-at-a-time, `prefers-reduced-motion`
   fallback, give-up timeout). The guided decision gates generalize that pattern to the live cockpit.
9. **The async-only dispatch posture is fixed and must be preserved.** `server.py`'s `POST /api/jobs`
   enqueues + optionally drains in a `BackgroundTask`; the allowlist stays narrow (RV-6) — the 8.5 h
   loop is never a synchronous click. v1 adds an *enqueue* affordance, never a synchronous run.

**Net:** of the spec's surface, the arbiter/watchdog/progress/CLI are connective code over (1)–(6),
and the education layer is rendering over (7)–(8). The one new public surface is the
`fieldkit.arena.lane` submodule — documented under `docs/api/arena.md`, **no new top-level module**,
so `audit-landing` stays 4/4 (the `arena.scheduler` precedent). New site content collection
`src/content/explainers/` is the only net-new authored data, and it is mostly *extraction* of (7).

## 2. Scope

**In scope (v1 = the run becomes self-driving, observable, self-defending, and self-explaining).**
- **`fieldkit.arena.lane`** — `LaneArbiter` (envelope-gated single-lane bring-up/teardown around a GPU
  job), `MemoryWatchdog` (telemetry-correlated OOM defense), `mem_trace` (the per-run memory report).
- **Live step reporting** — the loop writes throttled progress into `jobs.result_json`; a
  `/api/jobs/{id}` detail route + an `rl_run` progress pane in the cockpit render it live (step
  counter, pool-vs-held-out spark-line, ETA, phase).
- **Telemetry-correlated OOM defense** — the watchdog enforces a headroom floor during the arbiter
  window: warn → pre-emptive abort-and-teardown *before* the kernel OOM-kills; every run attaches a
  memory trace to its `fieldkit.lineage` snapshot + the standup.
- **One-step autonomy** — `fieldkit arena autonomy on|off|status` registers/removes the
  `run_drain_cycle` routine; a guided cockpit gate arms it with consequence + reversal stated.
- **The education layer** — a shared `explainers` content collection consumed by both the cockpit and
  the deep-dives; "what / why / watch" guide cards per phase; a live interpreter on the held-out plot;
  guided decision gates; a compounding post-run debrief.

**Out of scope (deferred / other specs).**
- **Multi-lane / multi-GPU arbitration** — violates invariant #2 (one serving lane in 128 GB); the
  arbiter is single-slot by design. Frontier multi-node lives in `_FLOWS` §6.
- **Installing / vendoring vLLM** — the wheel gap is external and unchanged (`rlvr-loop-v1` RV-5 /
  `[[project_verl_atgpo_vllm_gap]]`); v1 manages the lane's *lifecycle*, not its *install*. Absent a
  compatible binary the arbiter `defer`s cleanly (LANE_BIN_ABSENT).
- **The GRPO loop itself** — owned by `rlvr-loop-v1` (shipped). This spec only adds the progress
  callback + abort-poll hooks it calls between steps.
- **Publishable `rl_run`/`verifier`/`reward` artifact kinds** — still deferred to second-vertical reuse
  (`rlvr-loop-v1` RV-9); v1 ships no new `ARTIFACT_KINDS`.
- **The editorial→Book auto-seed on a >X% lift** — named in `rlvr-loop-v1` §6; the post-run debrief
  (LA-16) *flags* an editorial-promotable run but does not scaffold the article.

## 3. Locked decisions (PROPOSED 2026-06-03 — confirm before build)

Sixteen decisions across four layers: **arbiter → live progress → telemetry/OOM → education.**

### 3.1 Lane arbiter (LA-1 … LA-7)

| # | Decision | Grounding |
|---|---|---|
| LA-1 | **New `fieldkit.arena.lane` module owns the single serving slot.** A `LaneArbiter` context manager, entered by the GPU-kind runner, (a) reads `MemoryEnvelope.headroom_gb()`, (b) tears down the resident chat brain via the existing serve-lifecycle, (c) `VLLMLane.ensure_started(adapter)`, (d) on exit restores the prior lane. One arbiter, one slot. | Reuses `MemoryEnvelope` + `VLLMLane`; invariant #2. |
| LA-2 | **The arbiter composes with `DrainLock`, it does not replace it.** The cron's `run_drain_cycle` holds `DrainLock`; the arbiter is a strictly-narrower nested resource only GPU kinds enter. CPU kinds (`eval_rerun`/`reindex`/…) never touch it. | `arena.scheduler.DrainLock` shipped; M11 one-drain-at-a-time. |
| LA-3 | **vLLM is an optional out-of-tree *managed process*, not a hard dep.** A thin launcher shells the operator-pre-installed pinned vLLM, discovered by `FK_RL_VLLM_BIN`/`FK_RL_VLLM_URL`; the arbiter manages its **lifecycle**, never its **install**. Absent the binary → clean `defer` (LA-6), never a crash. | `[[project_verl_atgpo_vllm_gap]]`; `_rl_gpu_serve.serve_command`/`stop_command`; the `FK_RL_*` contract. |
| LA-4 | **The cockpit gets an *async-enqueue* affordance, never a synchronous run.** An `rl_run` *enqueue* button over the existing `POST /api/jobs` returns immediately with a job id + a "drains at next cycle / now if idle" note. The 8.5 h loop never blocks a request. | RV-6; `server.py` narrow allowlist + `BackgroundTask` drain. |
| LA-5 | **Cron registration is a first-class, reversible control-plane action.** `fieldkit arena autonomy on\|off\|status` registers/removes the `run_drain_cycle` routine and writes its state into the standup. Default **off**. "Human-armed per run" becomes "human-*policy*-armed, once." | M11 `run_drain_cycle` shipped, unregistered by design (AH as-built). |
| LA-6 | **Three-way pre-flight before any lane spawn: governor `allow` AND envelope `fits` AND lane binary present.** A failed check `defer`s with a distinct `EscalationReason` (`OOM_ENVELOPE` exists; add `LANE_BIN_ABSENT`), releases the claim back to `queued`, and writes a `budget_<reason>` `job_triggers` audit row (the AH-6 pattern). | `budget.BudgetGovernor`/`EscalationReason`; `arena/jobs.py` claim-release. |
| LA-7 | **No new arena.db table, no `user_version` bump.** Lane state is process-runtime (observable via the standup, not persisted); the run rides `fieldkit.lineage`; the abort signal rides a filesystem sentinel (LA-10). Continues RV-8 / AH-9 — schema stays at `user_version 6`. | store `USER_VERSION`; minimize schema churn. |

### 3.2 Live step reporting (LA-8 … LA-9)

| # | Decision | Grounding |
|---|---|---|
| LA-8 | **The loop writes throttled progress into the existing `jobs.result_json` while `status='running'`.** A `{step, max_steps, phase, pool_score, last_heldout, eta_s}` blob, patched every held-out gate (≤10 steps) or ~30 s, whichever first; `_jobs_signature` gains a progress nonce so `jobs_event_stream` re-emits. The loop is the **single writer** (no `result_json` race). Final digest overwrites on `done`. | `jobs.result_json` TEXT + `patch_job` + `jobs_event_stream` shipped; **no schema change** (RV-8). |
| LA-9 | **New `GET /api/jobs/{id}` detail route + an `rl_run` progress pane.** Renders the live `result_json`: step counter, **pool-vs-held-out spark-line** (the inversion made visible *as it happens*), ETA, current phase (lane-bringup / sampling / training / heldout-gate / teardown). The detail route is read-only and mirror-safe (never carries `payload_json`). | `fieldkit.viz` for the spark-line (`[[reference_fieldkit_viz_module]]`); SSE CRLF care (`[[feedback_sse_starlette_crlf]]`). |

### 3.3 Telemetry-correlated OOM defense (LA-10 … LA-11)

| # | Decision | Grounding |
|---|---|---|
| LA-10 | **A `MemoryWatchdog` runs inside the arbiter window, subscribed to the existing TelemetryHub unified-mem sample.** During an `rl_run` it enforces a headroom floor: **warn** below `FK_RL_OOM_WARN_GB` (default 8), **abort-and-teardown** below `FK_RL_OOM_FLOOR_GB` (default 4) — *before* the kernel OOM-kills and hangs the box. The abort crosses the process boundary via a **filesystem sentinel** the loop polls between steps; on trip it calls `VLLMLane.stop()` (EngineCore-aware) + releases the claim with a `budget_defer(oom_envelope)` audit row. A breach must persist N samples (~2 s) to fire (anti-transient). | `TelemetryHub` unified-mem sample shipped; `[[project_spark_unified_memory_oom]]`; `[[feedback_vllm_engine_core_orphan]]`. |
| LA-11 | **Every `rl_run` attaches a memory trace to its lineage snapshot.** Peak unified-mem, headroom-at-lane-spawn, per-phase mem deltas (bringup/sample/train/teardown), and the telemetry sample at abort if it OOM'd. Surfaced in the standup ("RAN 1 · peak 119 GB · 1 OOM-deferred at bringup") and on the run's lineage card — OOMs become **explainable**, not silent hangs. `MemoryWatchdog`/`mem_trace` are exported as **arena-wide** primitives (reusable by any GPU kind, `rl_run` the proving ground). | rides `fieldkit.lineage` (no new store, RV-7); `arena.scheduler.build_standup`. |

### 3.4 The education layer — guide the operator at every step (LA-12 … LA-16)

| # | Decision | Grounding |
|---|---|---|
| LA-12 | **Single curriculum source — a shared `src/content/explainers/` collection consumed by BOTH the cockpit and the articles.** Operational concepts (RLVR, GRPO, held-out split, KL drift, OOM envelope, the vLLM-restart bottleneck) keyed by `term` + `kind` (define/why/pitfall/math/hardware) + a `source_article` backlink. Each cockpit phase/event carries a `teach_key`. **No second copy to drift** — the article `:::pitfall` and the cockpit tooltip are the same bytes. | the curriculum is authored in `articles/the-machine-improves-itself/article.md` (`:::` blocks). |
| LA-13 | **Every phase has a "what / why / watch" guide card** drawn from LA-12 — *lane-bringup* → "freeing ~40 GB by tearing down the chat brain; this is the one-lane envelope; watch unified-mem fall then rise"; *heldout-gate* → the t2po pitfall + "the published checkpoint is chosen on **this** line, never the pool." Plain language first; the `:::math` on expand. | reuses the explainer `kind`s as the rhetorical structure. |
| LA-14 | **Live interpreter on the pool-vs-held-out plot (LA-9).** A one-line read updates as the lines move: both climbing → "genuine generalization"; pool up / held-out flat → "**the inversion the article warns about — the loop will publish the held-out-best step, not the current one.**" The counterintuitive finding made legible in real time. | RV-4 / the t2po `:::pitfall`. |
| LA-15 | **Guided decision gates, not bare buttons** (generalizing the demo coach). The three moments the operator *acts* — arm autonomy (LA-5), confirm resident-brain teardown, acknowledge an OOM-defer (LA-10) — render consequence + recommendation *before* the click ("Arming autonomy registers the overnight cron; up to $X/day under the governor; tears down/restores the chat lane per run; reversible with `autonomy off`"). No silent irreversible action. | demo `boot.js` coach (ping-ring, one-at-a-time, `prefers-reduced-motion`). |
| LA-16 | **A compounding post-run debrief.** Each completed `rl_run` closes with a teaching summary — what it did, which pitfalls it hit ("deferred once at bring-up; headroom was 3 GB; chat brain hadn't fully released"), and a backlink to the relevant explainer + deep-dive section. A notably-good run is **flagged editorial-promotable** (the living-model launch flywheel). | feeds the §5 editorial cadence; `[[feedback_side_by_side_review_after_major_features]]`. |

## 4. Architecture

**One new Arena submodule + three cross-process signals over shipped storage.** No new arena.db table
(LA-7); the run record lives in `fieldkit.lineage` (RV-7); progress rides `result_json`; the abort
signal rides a filesystem sentinel.

```
fieldkit.arena.lane
  LaneArbiter(envelope: MemoryEnvelope, cfg: RLBackendConfig)         # LA-1/2/6
    .__enter__()  -> preflight (governor allow ∧ fits ∧ bin present)  # else raise -> defer (LA-6)
                     stop resident brain; VLLMLane.ensure_started(adapter)
    .__exit__()   -> VLLMLane.stop() (EngineCore-aware); restore prior lane
  MemoryWatchdog(hub_sample, floor_gb, warn_gb)                       # LA-10  (arena-wide)
    .watch(job_id) -> on persistent breach: touch abort-sentinel; record mem at trip
  mem_trace(job_id) -> {peak_gb, headroom_at_spawn, per_phase_delta}  # LA-11  -> lineage + standup
__all__ = ["LaneArbiter", "MemoryWatchdog", "mem_trace", "LaneError"]
```

**The two-process picture (why signals cross via disk, not memory):**

```
  serving sidecar process                       cron drain process (run_drain_cycle, DrainLock held)
  ┌────────────────────────┐                    ┌──────────────────────────────────────────────┐
  │ TelemetryHub            │  nvidia-smi 500ms  │ rl_run claimed → LaneArbiter.enter()           │
  │  gpu_util/temp/mem ─────┼──┐                 │   preflight: allow ∧ fits ∧ bin  → else defer  │
  │ /api/telemetry/stream   │  │                 │   stop chat brain; VLLMLane.ensure_started     │
  │ /api/jobs/stream        │  │  operator        │   RLLoop.run(on_step=cb, abort=poll_sentinel)  │
  │ /api/jobs/{id} (LA-9) ──┼──┼─► dashboard      │     ├ phase events + step → patch_job(         │
  │ MemoryWatchdog (LA-10)◄─┘  │   (progress +     │     │   result_json={step,phase,pool,heldout,eta})│ LA-8
  │   breach → touch sentinel ─┼── filesystem ───►│     └ between steps: if sentinel → stop+defer  │
  └────────────────────────┘  │   sentinel        │   LaneArbiter.exit(): teardown + restore       │
                              └── arena.db ───────►│   mem_trace → lineage snapshot (LA-11)         │
   education layer renders teach_key on every      │ build_standup(+lane state, autonomy on/off,    │
   phase event / telemetry sample / decision gate  │   spend, mem peak)                             │
   (LA-12–16, shared explainers collection)        └──────────────────────────────────────────────┘
```

**One event stream, three renderers.** Phase change, telemetry sample, and decision gate each carry a
`teach_key`, so **progress (LA-8/9), diagnosis (LA-10/11), and education (LA-12–16) are the same event
stream rendered three ways**, not three subsystems.

**Autonomy as one reversible step.** `fieldkit arena autonomy on` registers a routine that calls
`run_drain_cycle`; `off` removes it; `status` reports it (and the standup mirrors it). The guided gate
(LA-15) states the governor cap, the per-run lane churn, and the one-command reversal before arming.

## 5. Sequencing — prerequisites + what this feeds

**Prerequisites (all shipped; one external).**
- **`rlvr-loop-v1` (shipped, `v0.20.0`)** — the loop the arbiter wraps; v1 adds its `on_step`/`abort`
  hooks. Hard dependency, done.
- **M11 cron + governor (shipped, `v0.19.0`)** — the drain home + the `allow/escalate/defer` brake the
  arbiter's pre-flight consults (LA-6). Done.
- **M9 cost plane (shipped, `v0.18.0`)** — the `$/day` cap surfaced in the autonomy gate (LA-15) + the
  standup spend digest. Soft; absent it degrades to the token+envelope guard.
- **The GPU backend (shipped, `v0.21.0`)** — `fieldkit.rl.gpu_seams` + `_rl_gpu_serve.VLLMLane`. Done.
- **External (unchanged):** a pinned aarch64+CUDA-13 vLLM the operator installs. Until present, the
  arbiter `defer`s (LANE_BIN_ABSENT); the machinery ships and is fully testable without it.

**What it feeds.**
- **The first live `rl_run`** — the HANDOFF's ▶ operator-armed run becomes "install vLLM, `autonomy on`,
  watch it drain" instead of a hand-driven overnight session.
- **The §5 living-model launch** — a held-out-winning run draws the real `fieldkit.lineage` delta
  chart, **promoting `products/living-model/` from `status: upcoming` to published** with a live hero.
- **Arena-wide OOM defense** — `MemoryWatchdog`/`mem_trace` (LA-11) protect *every* future GPU kind
  (`reindex`, `measure_variants`, local-serving jobs), not just `rl_run`.
- **The operator's competence** — the education layer (LA-12–16) graduates the operator from
  "armed each run" to "sets policy and understands every deferral," and feeds the editorial flywheel
  (LA-16 → §5 launches → the Ch-11 recursion).

## 6. Risk register (this spec's local IDs — the Arena register R13–R26 lives in `spark-arena-v1.md` §10)

| ID | Risk | Likelihood | Impact | Mitigation | Fallback |
|---|---|---|---|---|---|
| LA-R1 | **Arbiter tears down the chat brain, then the lane fails to start** — box left with no serving lane | med | no resident lane until restart | `LaneArbiter.__exit__` restores the prior lane in `finally`; the standup surfaces "no resident lane" | `arena_lifecycle.sh restart` brings the chat brain back; the failure is bounded to one drain pass |
| LA-R2 | **Auto-spawn races a manual operator lane** → two lanes → OOM | med | box hang (the landmine) | single `LaneArbiter` slot + `VLLMLane.is_running()` check; **refuse if an unmanaged vLLM is detected** | the M11 `DrainLock` bounds blast radius to one pass; the watchdog (LA-10) aborts before the kernel does |
| LA-R3 | **Unattended 8.5 h burn on a regressing run** | med | wasted overnight compute | the held-out gate already early-stops on no-lift (RV-4 `heldout_patience`); add a `max_wall_s` ceiling the arbiter enforces | the M9 governor's `$/day` cap and the standup catch it next morning |
| LA-R4 | **Cron left on silently drains the weekly `/usage` cap** | med | surprise spend | M9 governor `defer` on `OVER_USAGE_CAP`; `autonomy status` in every standup; the guided gate (LA-15) states the cap before arming | `autonomy off` is one command; the governor hard-stops at the cap |
| LA-R5 | **Progress writes amplify DB I/O over 8.5 h** | low | write churn | LA-8 throttle (per-gate or ~30 s); progress is a single-row `patch_job`, not an insert | drop to per-gate-only if churn shows in practice |
| LA-R6 | **Watchdog aborts on a transient sampling-burst mem spike** → wasted hours | med | a healthy run killed | breach must persist N consecutive samples (~2 s) before abort; the warn-tier is non-destructive | raise `FK_RL_OOM_FLOOR_GB`; the trace (LA-11) shows whether it was real |
| LA-R7 | **nvidia-smi sample stalls → watchdog blind** | low | no OOM defense mid-run | stale-sample detection (no sample in 4× interval) → conservatively `defer` *new* spawns; **never** abort a running job on missing data (avoid false-positive kills) | the proven kill-and-restart envelope (~30 GiB margin) is the static safety net |
| LA-R8 | **Education copy drifts from the shipped surface** (tooltip says X, code does Y) | med | misleading guidance | LA-12 single-source the explainers; cockpit + article read the same collection; a build check asserts every `teach_key` resolves | treat a missing/extra `teach_key` as a build warning (the `[[reference_fieldkit_module_enum_three_places]]` discipline) |

## 7. Release gate

**~`fieldkit v0.22.0`** (after the `v0.21.0` GPU-backend cut). Cut via `fieldkit-curator` (separate
action). The wheel ships `fieldkit.arena.lane`; **no new top-level module** (it documents under
`docs/api/arena.md`, so `audit-landing` stays 4/4 — the `arena.scheduler` precedent); `audit-docs
arena` clean for the new `LaneArbiter`/`MemoryWatchdog`/`mem_trace` exports. The website ships the
`src/content/explainers/` collection (both `content.config.ts` copies updated per
`[[reference_fieldkit_module_enum_three_places]]`) + the progress pane / guided gates / debrief.
**Schema unchanged (`user_version 6`, LA-7).** Live autonomy remains an operator opt-in — but **one**
opt-in (`autonomy on`), not per-run.

## 8. Deliverables

| Artifact | Surface | Gate |
|---|---|---|
| **New submodule `fieldkit.arena.lane`** — `LaneArbiter` (envelope-gated single-lane bring-up/teardown), `MemoryWatchdog` (telemetry OOM defense), `mem_trace` | `fieldkit.arena` | `audit-docs arena` clean; fake-lane/fake-envelope tests (spawn-gate, restore-on-failure, refuse-on-unmanaged) |
| **`LANE_BIN_ABSENT` defer reason + 3-way pre-flight** | `fieldkit.budget` (+1 enum) + `arena/jobs.py` | governor defers; claim released; `job_triggers` audit row written |
| **Live progress** — throttled `result_json` write from the loop + `_jobs_signature` nonce + `GET /api/jobs/{id}` detail route | `fieldkit.rl` (on_step) + `arena.server` | fake-event test: progress surfaces on `/api/jobs/stream`; no schema bump (LA-7) |
| **OOM watchdog + abort sentinel** — subscribe TelemetryHub mem; persistent-breach → sentinel → loop stops + defers; mem trace → lineage + standup | `fieldkit.arena.lane` + `arena.scheduler.build_standup` | fake-telemetry test: floor breach trips after N samples; transient spike does not; trace round-trips |
| **`fieldkit arena autonomy on\|off\|status`** | `fieldkit.cli` + `arena.scheduler` | registers/removes the routine; standup reflects state |
| **Async-enqueue `rl_run` affordance** + progress pane + guided gates + post-run debrief | `arena-app/` | E2E (Playwright): enqueue → job id (no hang); progress renders; gates state consequence; debrief links the explainer |
| **Shared `explainers` content collection** + `teach_key` wiring; deep-dive references the same source | `src/content/explainers/` + both `content.config.ts` copies | build green; every `teach_key` resolves (LA-R8 check) |
| Docs — `docs/api/arena.md` (lane exports) + an "Operator: full autonomy" runbook in `docs/api/rl.md` | `fieldkit` docs | `audit-docs` gate |
| Release `~fieldkit v0.22.0` | PyPI + tag | `fieldkit-curator` action (separate) |

**Review discipline (subjective UX).** The progress pane, guided gates, and education cards are
subjective output → per `[[feedback_testing_cadence]]` they close with an **operator + Playwright-MCP
side-by-side vibe pass** (`[[feedback_side_by_side_review_after_major_features]]`), not a formal eval.
The arbiter/watchdog logic is objectively-verifiable → GPU-free unit tests with fakes.

## 8.1 As-built (LA-1..11 — BUILT 2026-06-03)

The self-driving + safety backend landed as specified; the education layer
(LA-12..16) is the tracked fast-follow. Surface as shipped:

| Decision | As-built |
|---|---|
| LA-1/2/6 | **`fieldkit.arena.lane.LaneArbiter`** — the 3-way pre-flight (`preflight()` = governor *allow* ∧ `MemoryEnvelope.fits` ∧ `lane_binary_present`) raises `LaneDeferred` before any teardown; `__enter__` frees the resident brain + starts the watchdog; `__exit__` stops the watchdog, `VLLMLane.stop()`s (EngineCore-aware, global `pkill`), and **always** restores the prior lane. Composes inside `DrainLock` (drain-level brake, never replaces it). |
| LA-3 | **`lane_binary_present(cfg)`** — `FK_RL_VLLM_BIN` / `FK_RL_SERVE_CMD` launcher / `vllm` on PATH; absent → `LANE_BIN_ABSENT` defer (clean, never a crash). vLLM stays an out-of-tree managed process. |
| LA-4 | **`POST /api/jobs` accepts `rl_run`, forces `dispatch=False`** (`async_only: true` + autonomy note); cockpit "Enqueue RLVR run" affordance. The 8.5 h loop never runs in a request. |
| LA-5 | **`fieldkit arena autonomy on\|off\|status`** (reversible policy record via `scheduler.{read,write,clear}_autonomy_state` + crontab line install/print) + **`fieldkit arena drain`** (the cron target = one `run_drain_cycle` tick). Standup surfaces the armed state. |
| LA-7 | **No arena.db schema change** — `user_version` stays `6` (test-pinned). Lane state is process-runtime; the abort signal rides a filesystem sentinel; the run rides `fieldkit.lineage`. |
| LA-8 | **`fieldkit.rl.rl_hooks` / `current_rl_hooks`** (a `contextvars` conduit, arena → rl only — `run_rl_loop` unchanged); `RLLoop` emits throttled `{step, phase, pool_score, last_heldout, eta_s}` + polls an abort between steps. `rl_progress_writer` = the single-writer `result_json` patch (throttle: phase-change/gate, else ≤ `throttle_s`); `server._jobs_signature` gains a progress nonce. |
| LA-9 | The existing `GET /api/jobs/{id}` already surfaces parsed `result`; the **cockpit Jobs board** renders an inline progress strip from the SSE stream — phase · step/max · **pool-vs-held-out** (the t2po inversion flagged live) · ETA · peak mem. |
| LA-10 | **`MemoryWatchdog`** (arena-wide) over `/proc/meminfo` headroom — warn `FK_RL_OOM_WARN_GB` (8), abort below `FK_RL_OOM_FLOOR_GB` (4) after `persist_n` (~2 s) breaches; touches an abort sentinel; never trips on a stale sample (R7). |
| LA-11 | **`mem_trace` / `MemTrace`** (thread-safe) — peak / headroom-at-spawn / per-phase / abort sample → `jobs.result_json` + `_persist_rl_run` + the standup `rl` digest ("RAN 1 · peak 119 GB · 1 OOM-deferred"). |

**Verified (GPU-free):** suite **1253 pass / 5 skip** (+20: `test_lane.py` + the
async-only API test); `audit-docs` 17/18 (`rl` + `arena` PASS, `rl_lane` kwargs
documented, only pre-existing kwarg-drift WARNs remain), `audit-landing` **4/4**;
`astro build` **514 pages**; both render verifiers green; cockpit `_webui`
rebaked; `mypy` + `ruff` clean on the new source. **No schema change**
(`user_version 6`); **no new top-level module**; **no new `ARTIFACT_KINDS`**.
**Deferred (fast-follow):** the education layer LA-12..16 (the shared
`src/content/explainers/` collection + "what/why/watch" guide cards + the live
held-out-plot interpreter + guided decision gates + the post-run debrief).
**Operator action left (unchanged):** install a pinned aarch64+CUDA-13 vLLM; until
then the arbiter `defer`s `LANE_BIN_ABSENT` and the machinery is GPU-free-testable.

## 9. Change log

| Date | Change | Author |
|---|---|---|
| 2026-06-03 | **LA-1..11 BUILT** (self-driving + safety backend) — new submodule `fieldkit.arena.lane` (`LaneArbiter`/`MemoryWatchdog`/`mem_trace`/`RLLaneContext` + helpers), `fieldkit.rl` observability hooks, `EscalationReason.LANE_BIN_ABSENT` + the `rl_lane` dispatch brake, async-only `rl_run` enqueue, the `autonomy`/`drain` CLI, the cockpit progress strip + standup autonomy/RL surfacing. No schema change (`user_version 6`); no new top-level module (documents under `arena`); suite 1253 pass; `audit-landing` 4/4. The education layer (LA-12..16) is the tracked fast-follow. See §8.1 as-built + `fieldkit/CHANGELOG.md` [Unreleased]. | Manav (with Claude) |
| 2026-06-03 | **Initial spec authored — v1.0 DRAFT, decisions PROPOSED, UNBUILT.** The post-roadmap follow-on that makes the shipped Phase-3 engine self-driving: closes the two operator-armed chokepoints (managed vLLM lane + one-step cron arming), adds live step reporting + telemetry-correlated OOM defense for the multi-hour unattended run, and surfaces the published RLVR curriculum contextually so Arena teaches the operator at every step. 16 decisions across four layers (LA-1…7 arbiter / LA-8…9 live progress / LA-10…11 telemetry+OOM / LA-12…16 education). 8 risks (LA-R1…R8). One new Arena submodule `fieldkit.arena.lane` (`LaneArbiter`/`MemoryWatchdog`/`mem_trace`) + one new site content collection `src/content/explainers/`. Code-reconciled against the **shipped** `fieldkit/src/fieldkit/`: the memory envelope (`budget.MemoryEnvelope`), lane lifecycle (`_rl_gpu_serve.VLLMLane`), drain lock + standup (`arena.scheduler`), telemetry sampler (`server.TelemetryHub`), progress column (`jobs.result_json`), and curriculum (`articles/the-machine-improves-itself`) **all already exist** — v1 is overwhelmingly connective tissue. No arena.db schema change (`user_version 6`, LA-7); no new top-level module (documents under `arena.md`, `audit-landing` stays 4/4); no new `ARTIFACT_KINDS`. Release gate ~`fieldkit v0.22.0`. **Status: spec only, awaiting green-light** (the M9/M10/M11/RLVR "locked decisions — confirm before build" discipline). | Manav (with Claude) |

## 10. References

### Internal
- **The engine this makes self-driving:** `_SPECS/rlvr-loop-v1.md` (RV-6 async-only dispatch, RV-4 held-out gate, §10.1 as-built) + its `gpu_seams` GPU backend (vendored `v0.21.0`)
- **The dispatch / cron / governor / cost it builds on:** `_SPECS/spark-arena-v1.md` §12 (M8 dispatcher), §13 (M9 cost plane), §15 (M11 cron drain + `fieldkit.budget` governor + standup)
- **The roadmap framing (this = the named operator follow-on):** `_FLOWS/the-machine-that-builds-machines.md` §3 Phase 2 (the hands — autonomy) + Phase 3 (the engine — the operator-armed gap)
- **The curriculum the education layer surfaces:** `articles/the-machine-improves-itself/article.md` (`:::define`/`:::pitfall`/`:::math`/`:::hardware` blocks)
- Spec-format precedent: `_SPECS/rlvr-loop-v1.md` (the closest sibling — standalone, code-reconciled, layered decisions)
- fieldkit surfaces reused/extended: `fieldkit/src/fieldkit/{budget,arena/scheduler,arena/server,arena/jobs,_rl_gpu_serve,rl,lineage,viz}.py`

### Memory cross-references (`[[name]]`)
- `[[project_spark_unified_memory_oom]]` — the 128 GB one-lane envelope the arbiter enforces (LA-1/6/10)
- `[[feedback_vllm_engine_core_orphan]]` — EngineCore-aware lane teardown (`pkill -9 -f 'vllm|EngineCore'`) the arbiter/watchdog use (LA-1/10)
- `[[project_verl_atgpo_vllm_gap]]` — why vLLM is a managed *process*, not a dep (LA-3); the one external blocker
- `[[reference_fieldkit_rl_gpu_backend]]` — the vendored GPU backend + `FK_RL_*` operator-armed run contract this spec automates
- `[[feedback_sse_starlette_crlf]]` — CRLF parser care for the live progress SSE (LA-8/9)
- `[[reference_fieldkit_viz_module]]` — the pool-vs-held-out spark-line renderer (LA-9/14)
- `[[reference_fieldkit_module_enum_three_places]]` — update both `content.config.ts` copies (+ audit) for the new `explainers` collection (LA-12); the build check for `teach_key` (LA-R8)
- `[[feedback_side_by_side_review_after_major_features]]` + `[[feedback_testing_cadence]]` — the subjective-UX close for the panes/gates/cards (§8)
- `[[reference_marketing_screenshots_live_sse_2x]]` — driving the live SSE cockpit for the review/launch shots (LA-16 → §5)
