---
project: arena-enhancements
version: v1.0
status: DRAFT (decisions PROPOSED 2026-06-04 — confirm before build)
created: 2026-06-04
authoritative: Spark
---

# Arena Enhancements v1.0 — Project Specification

> The **dogfood payoff** spec. It formalizes the gitignored feature-extraction ledger
> (`_IDEAS/arena-dogfood-feature-extraction.md`, AF-1…AF-11) into a tracked plan, **plus** a
> cockpit **information-architecture refresh** the operator asked for after the first real
> `rl_run`. Sibling to — not an extension of — `spark-arena-v1.md`: that 1650-line spec owns the
> M1→M11 build; this one owns the **next layer of operator visibility + flow legibility** that fell
> out of driving the live cockpit beside the astrodynamics RLVR run (2026-06-04).
>
> Three bodies of work, one spec: **(A–D) observability** — make the whole vertical build visible
> in the cockpit (the build spine, the corpus feed, the live `rl_run` reward, per-step RL internals,
> bench provenance, scout/eval wiring); **(E) information architecture** — regroup the overflowing
> flat nav by the model lifecycle, audit which telemetry lands in which tab, and redefine the role of
> the Standup / Lab / Reward panes now that Phase-3 RLVR actually runs; **(F) cloud-run safety** —
> bounded, configurable, tracked guardrails on metered cloud lanes (teardown / stall / cost), after a
> baseline OpenRouter eval hung ~2.5 h holding the lane and accruing uncapped spend (2026-06-05).
>
> **Placement (user-confirmed 2026-06-04): standalone, full-backlog scope, RL-observability first.**
> A new focused spec (the recent pattern — `rl-lane-autonomy-v1`, `rlvr-loop-v1` — over growing the
> Arena spec), cross-linking `spark-arena-v1.md` at its seams. The *build* is deliberately deferred:
> this spec is **queued in `HANDOFF.md` to execute after the astrodynamics model ships (astro C6)**,
> so the next vertical (#2, or an astro re-run) meets a cockpit that can actually watch a build.

## 1. Context

### Why this project

`spark-arena-v1.md` built the **control plane** (M8 dispatcher → M9 cost → M10 recall → M11 cron) and
`rlvr-loop-v1.md` built the **engine**. The dogfood directive (`dogfood_finds_mock_blind_bugs`,
`feedback_dogfood_pipeline_with_live_arena`, `astrodynamics-vertical-v1.md` §1 goal 2) was to drive
the live cockpit *beside* a real vertical build and let features "fall out of the run, not planned."
Running the whole astro spine — scout → bench → corpus (C1) → SFT-init (C2) → smoke (C3) → the first
real `rl_run` (C5) — produced the ledger this spec formalizes, plus a sharp look at the cockpit's
own information architecture.

**The headline finding (ledger "Baseline finding"):** an operator parked on the cockpit during an
active vertical build watches *"a static board of yesterday's jobs."* The whole pre-RLVR spine is
in-session skill work the control plane never sees; even the dispatchable `rl_run` shows no upstream
provenance. The cockpit surfaces *the engine's jobs*, not *the machine*.

### Body 1 — observability gaps (the dogfood backlog + what the live run exposed)

The first live `rl_run` (2026-06-04) added four engine-level gaps to the ledger's AF backlog,
verified against shipped code:

- **AF-11 — the reward gauge is dark during the run it exists for.** `/arena/reward/` (the
  `<RewardSignalPane>` over `GET /api/reward-signal`) auto-follows `av10-preflight*.json` files by
  mtime (`fieldkit/src/fieldkit/arena/server.py:1962`); an `rl_run` writes its live progress to
  `jobs.result_json` via the LA-8 `rl_progress_writer` (`fieldkit/src/fieldkit/arena/lane.py:347`),
  surfaced on the **`/arena/jobs/`** board — never the file the reward gauge polls. AF-9's claim that
  "C5's per-step reports slot into the same history with no UI change" **did not hold at first
  contact**. (The `/arena/jobs/` `<RlProgress>` island, `arena-app/src/components/arena/JobsBoard.jsx:148`,
  *does* render live step/pool/held-out — so the dedicated **gauge**, not all telemetry, is the gap.)
- **Degenerate steps are invisible.** `group_advantage` / `keep_rate` / `n_used` are computed in the
  loop (`fieldkit/src/fieldkit/rl.py:321`) but never emitted (`_emit`, `rl.py:418`) or persisted. A
  no-op zero-advantage step (correct GRPO behavior with a strong SFT init — uniform-reward groups →
  zero advantage → no update, no adapter, no lane restart) reads **identical to a stall** from the
  cockpit. During the live run this required reading trainer source + counting vLLM completions to
  disambiguate step-1 (degenerate) from a hang.
- **Per-step internals are discarded.** `_persist_rl_run` (`fieldkit/src/fieldkit/arena/jobs.py:516`)
  saves only the aggregate `heldout_scores` / `pool_scores` dicts; no per-step loss / kl / keep_rate /
  duration / `trained` flag — so "which steps moved the policy" is unrecoverable after the run.
- **Lineage doesn't index which step shipped.** The final rl_run card holds the trial list but has no
  pointer from `selected_step` to its `rl-<step>` lineage row, so a regression can't trace to its
  exact checkpoint.

Plus the still-unbuilt ledger items: **AF-1** (Vertical-Build pane), **AF-2** (corpus-synth live
feed), **AF-4** (bench provenance card), **AF-5** (build-gate cards), **AF-6** (lineage threading),
**AF-7** (scout top-3 → Compare, *also* a lock-time behavioral gate), **AF-8** (bench preview).
(AF-3 / AF-9 / AF-10 are **already built** — they supply the reused transport pattern, §3.)

### Body 2 — information architecture & data-flow (the user's added scope)

A fresh look at the cockpit IA surfaced three coupled problems:

- **Nav overflow.** The top nav is a **flat 11-item CSS-flex row** (`arena-app/src/layouts/ArenaAppLayout.astro:226`):
  Cockpit · Models · Leaderboard · Chat · Compare · Jobs · Standup · SFT · Reward · Cortex · Lab —
  with three more deferred (Articles / Evals / Publish, `spark-arena-v1.md` §4.4). No grouping, no
  tiers; it does not fit horizontally and gives no sense of the model lifecycle.
- **Data-flow mis-routing.** Some training-pipeline telemetry doesn't land in the obvious tab. Seven
  flags (audited in §4 AE-13): corpus-synth has no cockpit pane; Reward is isolated from the RL jobs
  it feeds; the SFT → Reward → RL chain has no visible thread; Jobs vs Standup responsibilities
  overlap; Cortex is disconnected from the training flow; cost metrics live only on Leaderboard;
  Leaderboard rows don't link back to the job that produced them.
- **Pane-purpose drift.** Standup / Lab / Reward are **spec-aligned but were built in the M8 era as
  forward-looking placeholders** — they are *not* broken (the IA audit confirms each matches its spec
  intent). The operator's instinct is subtler: now that Phase-3 RLVR *actually runs*, recent
  intuition lets us **leverage them better** (Standup already carries `rl.display` / `oom_deferred`;
  Reward should span SFT-eval + live RL, not just the AV-10 preflight; Lab could thread the live build).

### Body 3 — two correctness defects found during astro C6 (2026-06-05)

Driving the cockpit beside the C6 generalization eval surfaced two more dogfood finds — both
**verified against shipped code + the live `:7866` board**, both within this spec's no-schema-change
envelope:

- **The telemetry "active lane" lies — it echoes the static Hermes config, not what's on the GPU.**
  `_build_payload` sets `resident_lane = self._resident_model()` (`server.py:463`), which reads
  `~/.hermes/config.yaml`'s `default` model (`_read_hermes_lane`, `server.py:108`) — pinned to
  **Qwen3-30B-A3B MoE** (`[[project_hermes_brain_pinned_moe]]`). The telemetry rail labels the lane
  `t.speed_model || t.lane_id || t.resident_lane` (`TelemetryRail.astro:309`), so **at idle, or while
  an astro 8B / vLLM-rl / NeMo container holds the GPU, the rail still says Qwen3-30B** — the config
  value, never reconciled against the actual process. The reader checks the file's mtime but never its
  liveness; and a Phase-3 lane (a `vllm-rl`/`nemo:26.04` container Hermes doesn't manage) is wholly
  invisible to it, even though the **lane arbiter (`fieldkit.arena.lane`) knows it tore the resident
  brain down** to seat that lane. Verified live: board idle, GPU free, rail reads `Qwen3-30B`.
- **Jobs "Done" cards read as repeats — distinct jobs lack any on-card identity.** Not data or DOM
  duplication (verified: `list_jobs` is a plain `SELECT * FROM jobs`, no JOIN fan-out; live DOM = one
  board, 5 distinct cards, no duplicate ids). The card face shows only kind + `laneBench(job)` (=
  `[lane_id, bench_id||manifest_slug]`, `JobsBoard.jsx:28`) + a kind-specific result line — **no
  timestamp, no short id, no run discriminator**. So the C5 4-step **smoke** and the full **34-step**
  run render as two near-identical `RL_RUN · astro-rlvr × astro-bench-v0.1 · held-out step 0 · 0.958`
  cards (differing only by `peak 104 GB` vs `106 GB`), and the two operator `rag_eval` jobs are
  **byte-identical** (`RAG_EVAL · rag_eval`). Distinct work is indistinguishable on the board.

### Body 4 — cloud-run safety: the OpenRouter eval that hung ~2.5 h (2026-06-05)

Driving the cockpit to verify the AF-15 eval dispatch (2026-06-05, after the `fieldkit v0.23.0` cut)
surfaced a **safety / cost** gap orthogonal to observability. A baseline `eval_rerun` on the OpenRouter
`qwen/qwen3-8b` lane ran **~2.5 hours** without completing — holding the single drain lane and accruing
**uncapped** cloud spend — until the operator killed it by hand (bouncing the cockpit + deleting the job
row). Three protections were missing, each verified against shipped code:

- **No teardown shutdown.** The in-flight OpenRouter request only died because the whole cockpit
  *process* was killed. Arena teardown has no clean abort for a running cloud eval: it executes
  synchronously in a FastAPI `BackgroundTask` (`server.py:2422`) with **no abort sentinel** — the
  `MemoryWatchdog` / `abort_poller` cancellation pattern is **RL-only** (`fieldkit/src/fieldkit/arena/lane.py:389`).
- **No stall ceiling.** `OpenAICompatClient` sets a **per-request** 120 s httpx timeout
  (`fieldkit/src/fieldkit/notebook/__init__.py:203`), but the per-row `VerticalBench.run` loop has **no
  per-run wall-clock or no-progress ceiling**, so a chronically-slow provider drags the whole run for hours.
- **No live cost cap.** Eval runs **don't capture per-row token `usage`** from the OpenRouter response,
  so cost is invisible mid-run; the `BudgetGovernor.daily_cap_usd=5.0` (`fieldkit/src/fieldkit/budget.py:333`)
  is a **per-job pre-dispatch** estimate check, not a live accumulator that can abort a run already crossing the cap.

Metered cloud lanes need bounded, configurable, tracked guardrails. → **Cluster F / AE-17.**

### Why now (and why gated after astro C6)

The gaps were found *because* a real run finally exercised the plane; building the fixes before the
next run would be speculative again. Sequencing them **after astro C6** means: (1) the astro run
finishes uninterrupted; (2) the fixes land where the next live `rl_run` (astro re-run or vertical #2)
can validate them — the only honest acceptance test (AE-R1); (3) the IA refresh (S2) lands *before*
the new panes (S3+), so they slot into a reorganized nav rather than worsening the overflow.

## 2. Scope

**In:**
- **A — RL-run observability:** AF-11 reward-gauge wiring + degenerate-step visibility + per-step
  history persistence + lineage step-indexing + **Jobs-card identity** (AE-16, Body 3).
- **B — build-pipeline spine:** AF-1 `/arena/build/` pane, AF-2 corpus feed, AF-5 build-gate cards.
- **C — substrate / provenance:** AF-4 bench provenance card, AF-6 rl_run lineage threading.
- **D — wiring quick-wins:** AF-7 scout-top-3 → Compare (+ lock-time behavioral gate), AF-8 bench
  preview via the existing Eval surface.
- **E — information architecture:** flow-based nav regroup, data-flow routing audit + corrections,
  Standup/Lab/Reward purpose redefinition, **telemetry lane-truth** (AE-15, Body 3).
- **F — cloud-run safety guardrails:** teardown-abort + stall-timeout + per-run cost-cap on metered
  cloud lanes, env-configurable + tracked in `result_json` (AE-17, Body 4).

**Out:**
- **AF-3 / AF-9 / AF-10** — already built (`/arena/reward/`, the live eval-run feed + run-history
  dropdown, `/arena/sft/`); cited here only as the **reused transport pattern** (file-polled report +
  the pane's existing poll).
- **The build itself** — this spec is decisions + breakdown; the build is a post-C6 fast-follow,
  session by session (§6). It ships `status: DRAFT`.
- **Any URL/route change** — the nav regroup (AE-12) changes **grouping + labels only**; route paths
  stay stable so deep links and the public mirror don't break (AE-R5).
- **Any arena.db schema change** — every fix lands in `result_json` / file-polled reports / existing
  panes / nav markup (§3). `user_version` stays **6** (AH-9 / RV-8 discipline).
- **Guardrails on cloud Compare / Chat** — AE-17 scopes the `EvalGuardrail` to **eval runs**; the same
  watchdog + sentinel generalizes to other metered cloud calls, but that wiring is deferred to a second
  reuse (`[[feedback_keep_scorer_local_until_reuse]]` discipline).

## 3. Code reconciliation (2026-06-04 — verified against the shipped `fieldkit/` + `arena-app/`)

The headline: **nothing here needs a new table or a migration.** Every decision extends an existing
write path, report file, pane, or the nav markup.

| Surface | Where it lives today | What this spec does to it |
|---|---|---|
| Reward gauge | `arena-app/src/.../RewardSignalPane.jsx` + `GET /api/reward-signal` (`server.py:1935`); selection precedence `?source=` → `FK_ARENA_REWARD_SIGNAL` → newest-by-mtime (`server.py:1962`) | **AE-1** has the `rl_run` loop *also* write an `av10-preflight`-shaped report under the auto-followed dir → gauge lights up, **zero pane change** |
| Jobs board / live RL strip | `arena-app/.../JobsBoard.jsx:148` (`<RlProgress>` reads `step/pool/held/eta/mem` from live `result_json`; LA-14 inversion/plateau classifier) | **AE-2** adds `keep_rate`/`n_used`/advantage-spread render (one line per metric) |
| Per-step progress writer | `fieldkit/src/fieldkit/arena/lane.py:347` `rl_progress_writer` (phase-change / gate / 30 s) → `store.update_job()` | unchanged transport; **AE-2** carries the new fields through it |
| Loop emit | `fieldkit/src/fieldkit/rl.py:418` `_emit` (step/phase/pool/held/gate/eta); `group_advantage`/`keep_rate` computed at `rl.py:321` but dropped | **AE-2** widens `_emit`; **AE-3** captures the per-step dict |
| Final persist | `fieldkit/src/fieldkit/arena/jobs.py:516` `_persist_rl_run` (aggregate `heldout_scores`/`pool_scores` only) | **AE-3** adds a bounded `step_history[]`; **AE-4** adds the `selected_step → rl-<step>` pointer |
| Lineage | `fieldkit.lineage` (append-only trials: `rl-<step>`, `heldout-<n>`) | **AE-4** / **AE-9** thread pointers (corpus/SFT/bench upstream + selected step) into the rl_run card |
| Compare / Eval surfaces | `/arena/compare/`, `GET /api/eval/benches` (+ `…/prompts`) | **AE-10** routes scout top-3 through Compare; **AE-11** registers `astro-bench v0.1` |
| Standup / Lab | `/arena/standup/` (`build_standup` — Ran/Regressed/Queued/Spend + `rl.display`/`oom_deferred`); `/arena/lab/` (static Now/Next/Exploring + git-log timeline + `lab_notes`) | **AE-14** redefines their role; reuses fields already present |
| Nav | `arena-app/src/layouts/ArenaAppLayout.astro:226` (flat 11-item flex, CSS 483–520) | **AE-12** regroups markup + CSS; routes unchanged |
| Cloud eval lane | `run_vertical_eval` (`mcp.py:455`) → `OpenAICompatClient.chat` (per-request 120 s httpx timeout, **no `usage` capture**, `notebook/__init__.py:203`); runs in a `BackgroundTask` (`server.py:2422`) with **no abort sentinel** | **AE-17** wraps it in an `EvalGuardrail` (stall + cost watchdog) + a shared **eval-abort sentinel** the `vb.run` row-loop polls (mirroring `abort_poller`, `lane.py:389`), tripped by `_lifespan` shutdown; captures response `usage` → `run_cost_usd`; all in `result_json` + env config, **no migration** |
| Cost pricing | `fieldkit.cost.PriceSnapshot.cost_usd(tokens_in,tokens_out)` (`cost.py`) — already the per-run USD math | **AE-17** reuses it to accumulate live per-row cost for the G3 cap (no change to `fieldkit.cost`) |
| Schema | `fieldkit/src/fieldkit/arena/store.py:63` `USER_VERSION = 6` | **unchanged** — no migration (AH-9 / RV-8) |
| Transport precedent | AF-9 (`av10-preflight*.json` + 5 s poll), AF-10 (`/arena/sft/` + 3 s poll over `FK_ARENA_SFT_DIR`) | the proven **file-polled-heartbeat** pattern AE-5/AE-6 reuse |

## 4. Locked decisions (PROPOSED 2026-06-04 — confirm before build)

Decision IDs are spec-local **AE-N**; each notes its **AF-N** ledger provenance where applicable.
Grouped by cluster; cluster ↔ session mapping is in §6 (decision number ≠ session order — Cluster E
executes in S2).

### Cluster A — RL-run observability (the gaps that bit)

| # | Decision | Value | Grounding |
|---|---|---|---|
| **AE-1** | **Wire the reward gauge to the live `rl_run`** *(AF-11)* | The `rl_run` loop **also writes an `av10-preflight`-shaped report** (pool reward · held-out reward · boxed-rate · AV-R1 truncation · step) per held-out gate under the dir `/arena/reward/` auto-follows → the gauge lights up with **zero pane change**. | The report already carries `reward_rate_step0`/per-bucket/per-row; reuses AF-9's auto-newest transport. **Alternative (rejected for v1):** teach `/api/reward-signal` to project a running `result_json` — couples the endpoint to arena.db. The gauge key is `reward_rate_step0`, **not** `reward` (ledger foot-gun). |
| **AE-2** | **Make degenerate / no-op steps visible** *(new)* | Emit `keep_rate` · `n_used` · advantage-spread from `_emit` (`rl.py:418`) and render them in `<RlProgress>` (`JobsBoard.jsx:148`); an `n_used==0` step must read **visibly distinct** from a trained step (e.g. a "no update — zero advantage" badge). | Already computed at `rl.py:321`, just dropped. Tonight a degenerate step looked identical to a stall. |
| **AE-3** | **Persist per-step history** *(new)* | `_persist_rl_run` (`jobs.py:516`) writes a bounded `step_history[]` of `{step, phase, pool_score, last_heldout, keep_rate, loss, kl, n_used, step_duration, trained}`, within the existing `result_json` column. | No migration (AE-R2 caps it). Reconstructs "which steps moved the policy" after the run. |
| **AE-4** | **Lineage step-indexing** *(new)* | The final rl_run card points `selected_step → rl-<step>` (the lineage trial id), so a regression traces to the exact selected checkpoint. | `fieldkit.lineage` already writes `rl-<step>` trials; this adds the back-pointer. |
| **AE-16** | **Jobs-card identity** *(new — Body 3)* | Every Jobs card carries a unique discriminator on its face: **relative enqueue time** (`enqueued_at` → "2 h ago") + a **short id** (`id[:8]`), and for `rl_run` a **run label** (`payload.run_label`/step-count) so the smoke vs the full run are distinguishable. Pure render — `enqueued_at`/`id` are already in the snapshot. | Verified live (Body 3): 5 distinct done jobs read as repeats — 2 `rl_run` differ only by peak-GB, 2 `rag_eval` byte-identical. Card face shows only kind + `laneBench` (`JobsBoard.jsx:28`); no time/id. Complements AE-4 (the `selected_step → rl-<step>` pointer disambiguates rl_run cards by outcome). |

### Cluster B — Build-pipeline spine

| # | Decision | Value | Grounding |
|---|---|---|---|
| **AE-5** | **`/arena/build/` Vertical-Build pane** *(AF-1)* | A new pane of C1…C6 stage cards (scout✓ · bench · corpus · SFT · smoke · lane · RLVR · publish), each with state + headline metric + the operator gate. The spine that frames the rest. | Derive state from existing artifacts + a manifest + file-polled heartbeats (AE-R3) — no heavy schema (ledger note). |
| **AE-6** | **Corpus-synth live feed** *(AF-2)* | An in-session `corpus_runs` heartbeat (polled JSON, the AF-9/AF-10 pattern) → a cockpit strip mirroring the rl_run strip: `written/target` · batch verify ✓/✗ · accumulating tier·topic mix · ETA-in-batches. | Closes the C1 blind spot + the "no corpus pane" data-flow flag (AE-13). #1 immediate win in the ledger. |
| **AE-7** | **Build-gate cards** *(AF-5)* | Extend the budget/autonomy allow-escalate-defer pattern (M9/M11/LA-15) to the pipeline's human gates: AV-10 preflight pass/hold · C1 `/usage` token preflight · SFT held-out>base (C2) · held-out-win publish (C6) — each with consequence + an allow/hold control. | Reuses the Standup autonomy-banner pattern. |

### Cluster C — Substrate / provenance

| # | Decision | Value | Grounding |
|---|---|---|---|
| **AE-8** | **Bench provenance card** *(AF-4)* | Version · pool/held-out counts · **disjointness✓ (RV-10)** · tier/topic mix · "every gold self-verifies✓" · corpus held-out-exclusion proof. | The Cortex-pane card pattern, applied to the bench. Folds into AE-11's preview. |
| **AE-9** | **rl_run lineage threading** *(AF-6)* | The rl_run card links its upstream **corpus (C1) + SFT-init (C2) + bench version**, so a regression traces to its corpus, not just its step. | Builds on the `LineageSnapshot` already on the card + AE-4's step pointer. |

### Cluster D — Wiring quick-wins (existing surfaces)

| # | Decision | Value | Grounding |
|---|---|---|---|
| **AE-10** | **Base-model Compare + lock-time behavioral gate** *(AF-7)* | Route the `hf-model-scout` top-3 (the `/tmp/hf-scout/**/report.md` the cockpit never saw) through the **existing `/arena/compare/`** — A-vs-B on a few held-out bench prompts. **Doubles as the lock-time behavioral smoke gate between scout-lock (A) and bench-build (B)** — 2–3 domain prompts on the top-N, eyeball boxing + verbosity, *then* commit a bench. | The headline flow-gap fix (`feedback_dogfood_pipeline_with_live_arena`): scout is paper-blind to behavior; we found Qwen3-8B's over-think one stage too late. One-lane caveat (`project_spark_unified_memory_oom`) → sequential lane swaps / cached generations (AE-R4). |
| **AE-11** | **Bench preview** *(AF-8)* | Register `astro-bench v0.1` so the **existing `/api/eval/benches` + `…/prompts`** Eval surface previews pool/held-out rows (prompt · gold · tier · subtopic). Mostly registration — the render exists. | Folds in AE-8's provenance card. |

### Cluster E — Information architecture & flow (the user's added scope; executes in S2)

| # | Decision | Value | Grounding |
|---|---|---|---|
| **AE-12** | **Flow-based nav IA** *(new)* | Regroup the flat 11+ tabs by the model lifecycle, with responsive overflow handling (section labels / grouped dropdowns / two-tier), **URLs unchanged**, and reserved slots for the deferred Articles/Evals/Publish. Proposed grouping: **Build/Train** {Models · SFT · Reward · Build · Jobs · Standup} · **Serve/Infer** {Chat · Compare · Leaderboard} · **Review/Meta** {Cockpit · Lab · Cortex}. | Nav is a flat 11-item flex today (`ArenaAppLayout.astro:226`); overflows + reads as a list, not a lifecycle. Cortex is *infrastructure* supporting both flows → Review/Meta or a submenu. |
| **AE-13** | **Data-flow routing audit + corrections** *(new)* | The spec carries the audit table below as the contract, and resolves each flag: Jobs (operator dispatch) vs Standup (overnight-cron staged) boundary made **visually explicit**; a Cockpit **training-flow summary card** (SFT → Reward → RL-job status chain); **Leaderboard row → producing-job link** (the `arq_job_id` socket exists, the UI doesn't surface it); a **cost badge** beyond Leaderboard (Chat/Compare). Corpus pane → AE-6; reward→RL wiring → AE-1 (cross-referenced, not duplicated). | 7 mis-routings flagged in the IA audit; grounded in `leaderboard.astro`, `standup.astro` vs `jobs.astro`, the telemetry rail. |
| **AE-14** | **Pane-purpose redefinition (recent-intuition leverage)** *(new)* | Restate the role of three panes now that Phase-3 RLVR runs: **Standup** = the overnight RL-run digest + promote gate (leverage the existing `rl.display`/`oom_deferred` fields, surface the last drain's `step_history` summary); **Reward** = the cross-stage "is the model producing scorable output" gauge spanning SFT-eval + live RL (folds in AE-1), not just the AV-10 preflight; **Lab** = thread the live vertical-build (link Now/Next cards to the AE-5 `/arena/build/` stages). | The IA audit confirms all three are spec-aligned, not broken — this elevates leverage, it does not rebuild. If the operator wants a genuine rebuild of any, re-scope that row before build. |
| **AE-15** | **Telemetry lane-truth** *(new — Body 3)* | The rail's lane label must reflect **what's actually serving**, not the static Hermes config. Three layers, cheapest first: (1) **liveness-gate** the `resident_lane` fallback — only label it "active" if a probe of the configured `base_url`/port answers; else show "idle / no warm lane". (2) **Surface the lane arbiter's truth** — when `fieldkit.arena.lane` has torn the resident brain down for an `rl_run`/external lane, the rail reads that lane (model + "RL lane / external") instead of the stale config. (3) **Relabel** the idle fallback as "configured lane", reserving "active lane" for a verified-live process. | Body 3 root cause: `resident_lane = _resident_model()` (`server.py:463`) → `~/.hermes/config.yaml` (`server.py:108`, pinned Qwen3-30B `[[project_hermes_brain_pinned_moe]]`); rail fallback `TelemetryRail.astro:309`; no liveness check, GB10 unified `nvidia-smi` shows N/A so per-process attribution is hard (`[[project_spark_unified_memory_oom]]`) → the arbiter state (layer 2) is the reliable signal. Updates the AE-13 audit "Live hardware telemetry" row from OK. |

#### AE-13 data-flow audit — telemetry → correct tab

| Telemetry surface | Lands today | Flow stage | Verdict / correction |
|---|---|---|---|
| Corpus synth | *(no pane — CLI/skill)* | Train (input prep) | **Add** via AE-6 corpus feed (→ Build group) |
| SFT training | `/arena/sft/` (AF-10) | Train (warm-start) | OK; thread into the Cockpit training-flow card (AE-13) |
| Reward signal | `/arena/reward/` | Train (verifier / RL) | **Wire to live rl_run** (AE-1); span SFT-eval + RL (AE-14) |
| RL run progress | `/arena/jobs/` `<RlProgress>` | Train (loop) | OK for live; **add reward gauge** (AE-1) + degenerate visibility (AE-2) |
| Job dispatch/queue | `/arena/jobs/` | Train (control) | OK; clarify vs Standup (AE-13) |
| Overnight digest / regressions | `/arena/standup/` | Train (review gate) | OK; **make Jobs↔Standup boundary explicit** (AE-13); elevate as RL digest (AE-14) |
| Leaderboard rank/frontier | `/arena/leaderboard/` | Eval/Infer | **Add row → producing-job link** (AE-13) |
| Cost / $ per task | Leaderboard only | Eval/Infer | **Surface a cost badge** on Chat/Compare (AE-13) |
| Chat / Compare | `/arena/chat/`, `/arena/compare/` | Infer | OK; Compare also hosts AE-10 scout duel |
| Knowledge / recall | `/arena/cortex/` | Infra (both flows) | OK; place in Review/Meta group (AE-12) |
| Live hardware telemetry | persistent rail | Infer | GPU/mem/temp OK; **lane label is stale** — echoes the Hermes config, not the live process → **fix via AE-15** (Body 3) |

### Cluster F — Cloud-run safety & cost guardrails (the OpenRouter hang fix; executes its own session, may pull forward)

| # | Decision | Value | Grounding |
|---|---|---|---|
| **AE-17** | **Bounded, configurable, tracked guardrails on metered cloud lanes** *(new — Body 4)* | A single **`EvalGuardrail`** wraps any cloud/metered lane run (OpenRouter today — detected by a non-loopback `base_url`) with **three trip conditions**, all writing a shared **eval-abort sentinel** that the `VerticalBench.run` row-loop polls between rows (mirroring the RL `abort_poller` / sentinel, `lane.py:389`): **(G1) teardown** — the cockpit `_lifespan` shutdown (`server.py:750`) **and** an explicit `arena down` hook trip the sentinel, so an in-flight cloud eval aborts cleanly instead of only dying with the process; **(G2) stall** — a **no-progress** watchdog trips when no row has completed within `FK_EVAL_STALL_TIMEOUT_S` (default **600 s / 10 min**), backstopped by the existing 120 s per-request httpx timeout; **(G3) cost** — capture per-row `usage` tokens from each response → accumulate via `fieldkit.cost.PriceSnapshot.cost_usd` → trip when the **per-run** total exceeds `FK_EVAL_RUN_COST_CAP_USD` (default **$5**), the per-run sibling of the governor's per-day cap. **Configure:** env-anchored thresholds (the AF-9/AF-10 convention); G1 is always-on. **Track:** every trip writes `result_json.{aborted_by ∈ teardown\|stall_timeout\|cost_cap, run_cost_usd, partial:true, n_scored}` + a `guardrail_<reason>` audit row, surfaced on the Jobs card (composes with **AE-16** card identity + **AE-2** abort visibility); the captured `run_cost_usd` also feeds the **AE-13** cost badge. | Body 4 root cause: eval runs synchronously in a `BackgroundTask` (`server.py:2422`) with **no abort sentinel** (RL-only today, `lane.py:389`); `OpenAICompatClient` timeout is **per-request** 120 s (`notebook/__init__.py:203`), no per-run ceiling; eval **doesn't capture `usage`** so cost is invisible; `BudgetGovernor.daily_cap_usd` (`budget.py:333`) is a **per-job pre-check**, not a live accumulator. **No schema change** — sentinel file + `result_json` fields + env config. Generalizes to cloud Compare/Chat (deferred, §2 Out). |

## 5. Architecture

**Reused surfaces** (no new route): `/arena/reward/` (AE-1, AE-14), `/arena/jobs/` (AE-2),
`/arena/compare/` (AE-10), `GET /api/eval/benches` (AE-11), `/arena/standup/` + `/arena/lab/`
(AE-14), `/arena/leaderboard/` + Cockpit landing (AE-13).

**New surfaces:** `/arena/build/` (AE-5, in the Build/Train nav group); a `corpus_runs` file-polled
heartbeat (AE-6); per-step `result_json` extensions (AE-2/AE-3) and lineage pointers (AE-4/AE-9).

**Cloud-run guardrails (AE-17):** a new `EvalGuardrail` (a stall + cost watchdog, mirroring
`MemoryWatchdog`) plus a shared **eval-abort sentinel** file the `VerticalBench.run` row-loop polls
(mirroring `abort_poller`, `lane.py:389`), tripped by the `_lifespan`/`arena down` teardown and the
three conditions; per-run cost is captured from each response's `usage` via `fieldkit.cost.PriceSnapshot`.
No new route, no schema — the trip + per-run cost land in `result_json` and the thresholds are env-anchored.

**Transport discipline:** every cross-process feed uses the **proven file-polled-heartbeat** pattern
(AF-9's `av10-preflight*.json` + 5 s poll; AF-10's `FK_ARENA_SFT_DIR` + 3 s poll) — never importing
skill code into the cockpit (AE-R3). In-process RL progress keeps the LA-8 `rl_progress_writer` →
`result_json` → poll-nonce SSE board re-emit path; this spec only widens the payload (AE-2/AE-3).

**Nav (AE-12):** `ArenaAppLayout.astro` nav markup + CSS regrouped into three lifecycle sections with
responsive overflow handling; route `href`s unchanged.

## 6. Session-by-session work breakdown

The deliverable the HANDOFF queues. Gated **after astro C6 publish**. RL-observability first (the
gaps that just bit); the IA refresh second (foundational, before new panes); the spine, feeds,
provenance, and wiring after.

```
S1  RL-run observability        AE-1 reward-gauge → live rl_run  ·  AE-2 degenerate-step visibility
    (the gaps that bit)         AE-3 per-step step_history       ·  AE-4 lineage step-index
                                AE-16 Jobs-card identity (time + short id + run label — pure render)
                                all within result_json / file reports — NO schema change
                                ▶ GATE: validate on the NEXT live rl_run (astro re-run / vertical #2),
                                  not a file test (AE-R1)
                                          │
S2  Information architecture     AE-12 flow-based nav regroup (URLs unchanged)
    & flow (foundational)        AE-13 data-flow routing audit + corrections (Jobs↔Standup, training-flow
                                       card, leaderboard→job link, cost badge)
                                 AE-14 Standup/Lab/Reward purpose redefinition
                                 AE-15 telemetry lane-truth (liveness-gate + arbiter-aware label)
                                 ▶ done before new panes so S3+ land into the reorganized nav
                                          │
S3  Build-spine backbone         AE-5 /arena/build/ pane (into the new Build/Train group)
                                          │
S4  Live feeds + gates           AE-6 corpus-synth live feed  ·  AE-7 build-gate cards
                                          │
S5  Provenance / lineage         AE-8 bench provenance card  ·  AE-9 rl_run lineage threading
                                          │
S6  Wiring quick-wins            AE-10 scout top-3 → Compare (+ lock-time behavioral gate)
                                 AE-11 bench preview (register astro-bench v0.1 in Eval)
                                          │
S7  Cloud-run guardrails         AE-17 EvalGuardrail (G1 teardown · G2 stall · G3 cost) on metered
    (safety; MAY pull forward)         cloud lanes — env-config thresholds + result_json trip-tracking
                                 ▶ NB a safety/cost concern, NOT observability — may execute AHEAD of S1
                                   if cloud eval runs continue before astro C6 (a hung run is a live cost leak)
                                 ▶ GATE: validate by a deliberately-slow / capped cloud eval that trips
                                   each condition + a teardown mid-run (not only a unit test)
```

Each session closes its loop to the AF-3 bar (ledger "operating discipline" §5): tests + `_webui`
rebake + a live side-by-side over CDP. Never block an astro/vertical gate on an Arena build.

## 7. Risk register (this spec's local IDs; the Arena register R13–R26 lives in `spark-arena-v1.md` §10)

| ID | Risk | Likelihood | Impact | Mitigation | Fallback |
|---|---|---|---|---|---|
| **AE-R1** | Repeating AF-9's "reuses the same transport, no UI change" assumption — which **failed at first contact** (the AF-11 root cause) | med | the reward gauge stays dark on the real run again | S1 acceptance is a **live `rl_run` lighting the gauge end-to-end**, not a synthetic file test | if the file path mismatches, fall back to the AE-1 alternative (project `result_json` in `/api/reward-signal`) |
| **AE-R2** | `step_history[]` bloats `result_json` (34 steps × dict) | low | a fat JSON blob in the `jobs` row | cap to the fields in AE-3; bounded by `max_steps` | if it grows, move to a JSONL in `evidence/` or a new table (deferred — no migration now) |
| **AE-R3** | `/arena/build/` couples the cockpit to in-session skill internals | med | brittle pane that breaks when a skill changes | **file-polled heartbeat contracts only** (the AF-9/AF-10 transport); never import skill code | the pane degrades to "stage unknown" rather than erroring |
| **AE-R4** | One-lane envelope blocks AF-7 head-to-head (`project_spark_unified_memory_oom`) | high | can't serve 3 candidate lanes at once | **sequential lane swaps / cached generations** for the Compare duel | run the behavioral gate as N single-lane preflights, compared offline |
| **AE-R5** | Nav reorg churns muscle memory / breaks deep links / the public mirror | med | broken bookmarks, sidecar-less mirror nav breaks | keep route **URLs stable** (grouping + labels only); verify the public-mirror nav renders sidecar-less | revert to the flat nav (markup-only change, trivially reversible) |
| **AE-R6** | An AE-17 guardrail **false-trips** and aborts a legitimately-slow-but-progressing cloud run | med | a valid eval is killed mid-run, the partial spend wasted | **no-progress** semantics for G2 (reset the timer on every completed row, never a wall-clock total) + generous env-tunable defaults (10 min / $5); G3 trips only on *accrued* cost from real `usage` | raise the env thresholds and re-run; the `partial` `result_json` (`n_scored`, `run_cost_usd`) records exactly what was spent so the re-run has context |

## 8. Release gate

Site/cockpit-only sessions (AE-12 nav, AE-5/AE-6/AE-8 panes) rebake the `_webui` bundle
(`fieldkit arena build --repo-root arena-app`, gitignored) — no Python version change required.
Module-touching sessions (AE-1/AE-2/AE-3/AE-4 in `fieldkit.rl` / `fieldkit.arena`, and **AE-17** in
`fieldkit.arena` / `fieldkit.harness` + the `fieldkit.cost` reuse) get a `fieldkit` minor bump with
CHANGELOG `[Unreleased]` entries. The cluster likely lands across **`fieldkit v0.24.0+`** (v0.23.0
already shipped). No arena.db migration in any session (`user_version` stays 6).

## 9. Change log

| Date | Change | Author |
|---|---|---|
| 2026-06-05 | **+1 decision (now 17: AE-1…17) + new Cluster F + §1 Body 4, from the OpenRouter eval that hung ~2.5 h during the AF-15 dispatch verification** (after the `fieldkit v0.23.0` cut). **AE-17** (Cluster F → S7) cloud-run safety & cost guardrails: an `EvalGuardrail` on metered cloud lanes with three trip conditions — **G1 teardown** (cockpit `_lifespan` / `arena down` abort an in-flight cloud eval cleanly), **G2 stall** (`FK_EVAL_STALL_TIMEOUT_S` default 600 s no-progress watchdog), **G3 cost** (capture response `usage` → `PriceSnapshot.cost_usd` → `FK_EVAL_RUN_COST_CAP_USD` default $5 per-run cap) — all env-configurable + tracked in `result_json` (`aborted_by` / `run_cost_usd` / `partial`), mirroring the RL `abort_poller`/sentinel pattern. + risk **AE-R6** (false-trip). Updated §1 intro (three bodies of work), §2 scope (In F / Out generalization), the §3 reconciliation (+2 rows), §5 architecture, §6 (S7, may pull forward), §8 release gate. **Build deferred — spec only (operator-confirmed "don't build yet").** Still **no arena.db schema change** (sentinel file + `result_json` + env config). | Manav (with Claude) |
| 2026-06-05 | **+2 decisions (now 16: AE-1…16), from two correctness defects found driving the cockpit during astro C6** (new §1 Body 3, both verified against shipped code + the live `:7866` board). **AE-16** (Cluster A → S1) Jobs-card identity: distinct done jobs render as repeats (C5 smoke vs full run; two `rag_eval`s byte-identical) — add relative time + short id + rl_run run-label (pure render, no schema). **AE-15** (Cluster E → S2) telemetry lane-truth: the rail's "active lane" echoes the static `~/.hermes/config.yaml` (pinned Qwen3-30B) not the live GPU process — liveness-gate the fallback + read the lane arbiter's actual lane. Updated §2 scope, the AE-13 audit "Live hardware telemetry" row, and §6 (S1/S2). Still **no arena.db schema change**; both land in render + existing payloads. | Manav (with Claude) |
| 2026-06-04 | Spec authored (v1.0 DRAFT, PROPOSED). 14 decisions AE-1…14 across 5 clusters (A RL-observability · B build-spine · C provenance · D wiring · E information-architecture) + 5 risks AE-R1…5 + the §4 data-flow audit table; 6-session breakdown §6. Formalizes the gitignored `_IDEAS/arena-dogfood-feature-extraction.md` (AF-1/2/4/5/6/7/8/11; AF-3/9/10 already built) **plus** the cockpit IA refresh raised after the first live `rl_run`. Decisions confirmed in planning: standalone spec, full backlog, RL-observability first; build queued after astro C6. Plan workspace: `/home/nvidia/.claude/plans/while-we-wait-shall-polished-hummingbird.md`. | Manav (with Claude planning session) |

## 10. References

### Internal
- **The Arena spec this extends:** `spark-arena-v1.md` (§4 route map, §10 risk register, §12–15
  M8–M11; `/arena/standup/` = §15/AH-3, `/arena/lab/` = v0.2, `/arena/reward/` = M8 + Phase-3 seam)
- **The engine whose run exposed the gaps:** `rlvr-loop-v1.md` (RV-4 held-out-only selection; the
  `_emit` / `_persist_rl_run` / lineage surfaces AE-1…4 touch)
- **The autonomy layer that owns the live RL progress transport:** `rl-lane-autonomy-v1.md`
  (LA-8 `rl_progress_writer`, LA-13/14 the RL strip + classifier)
- **The vertical that drove the dogfood:** `astrodynamics-vertical-v1.md` (§1 goal 2; the C1…C6
  spine AE-5 mirrors; AV-10 the behavioral smoke AE-10 promotes to a lock-time gate)
- **The source ledger (gitignored, kept living):** `_IDEAS/arena-dogfood-feature-extraction.md`
  (AF-1…AF-11, the per-stage retrospective, the headline flow gap)
- Cockpit code surfaces: `arena-app/src/layouts/ArenaAppLayout.astro`,
  `arena-app/src/components/arena/{JobsBoard,RewardSignalPane}.jsx`,
  `fieldkit/src/fieldkit/{rl.py, arena/{server,lane,jobs,store}.py, lineage/}`

### Memory cross-references (`[[name]]`)
- `[[dogfood_finds_mock_blind_bugs]]` — why dogfooding the live cockpit beside real work is the source
- `[[feedback_dogfood_pipeline_with_live_arena]]` — observe-always/build-rarely; the scout behavioral-blindness that AE-10 fixes
- `[[project_spark_unified_memory_oom]]` — the one-lane envelope behind AE-R4
- `[[reference_fieldkit_module_enum_three_places]]` — the content.config.ts × audit_docs enum drift any new module/pane must update
