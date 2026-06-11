---
module: budget
title: fieldkit.budget
summary: The spend governor the autonomous job drain consults before each dispatch — allow, escalate, or defer against an explicit budget envelope. Governor, not meter.
order: 16
---

## What it is

The **budget governor** — Phase 2 of the "machine that builds machines" roadmap
(`_FLOWS/the-machine-that-builds-machines.md` §3, Bet 2), shipped as **Arena
M11** (`_SPECS/spark-arena-v1.md` §15). Where M9's `fieldkit.cost` is the
**meter** (the per-run ledger + the public `$/quality-point`), `fieldkit.budget`
is the **brake**: the one pre-launch check the autonomous overnight drain
consults *before* it launches each job.

It is the enforcement arm M9 deferred (decision M9-9): M9 ships the ledger,
M11's governor *consumes* it. The governor generalizes the two guards that
already existed informally — the corpus-synth weekly-`/usage` ceiling and the
OOM-envelope check — into a single `BudgetGovernor.check_budget(job)` call that
returns one of three verdicts:

- **allow** — within budget and the lane fits the resident memory envelope.
- **escalate** — the **`LOCAL_CEILING = 33%`** *failure-mode-driven* contract:
  escalate to a frontier lane when the local model *gives up* (a multi-step
  planning / KV-cache-derivation failure class that hits the 30B-A3B-class
  boundary), **not** on a token ceiling alone. Grounded in H6
  (`hermes-cost-routing-local-and-openrouter`: a third of the workload genuinely
  needs frontier).
- **defer** — over the daily `$` cap (M9 present), over the weekly `/usage` cap
  (M9 absent), or no memory envelope for the lane (the 2026-04-22 OOM landmine).

## M9 is a soft prerequisite (AH-5)

When a `fieldkit.cost.CostLedger` is wired the governor reads the persisted
ledger for `$/task` + the 33% ceiling; when absent it **degrades to a token +
OOM-envelope guard** (the two checks that already exist). M11 ships independent
of M9's build slot; M9 *upgrades* the governor when it lands. The module is
store-agnostic by duck-typing (a `CostLedger`, an `ArenaStore`, or a raw
`sqlite3.Connection`), so `fieldkit.budget` never imports `fieldkit.arena` — the
scheduler injects the governor *into* the drain loop, never the reverse.

## The surfaces

- **`BudgetGovernor`** — the stateless pre-launch check. Construct with a ledger
  (enables the M9 `$/task` branch), a `MemoryEnvelope`, a `daily_cap_usd`, and a
  `weekly_usage_cap_pct`. `check_budget(job, *, spend_today=None,
  weekly_usage_pct=None)` returns a `BudgetDecision`; the keyword overrides make
  a decision deterministic for a test. `spend_digest(cap_usd=None)` returns the
  standup's Spend row.
- **`BudgetDecision`** — the verdict: `action` (`allow` / `escalate` / `defer`),
  `reason` (an `EscalationReason`), and a `detail` dict the standup renders
  (projected spend, cap, ceiling, lane footprint). `.allowed` is True only for
  an outright allow — the scheduler gates dispatch on it.
- **`EscalationReason`** — the reason vocabulary: `WITHIN_BUDGET`,
  `LOCAL_CEILING` (the only escalate reason), `OVER_DAILY_CAP`, `OVER_USAGE_CAP`,
  `OOM_ENVELOPE`.
- **`SpendDigest`** — today's spend rolled up for the morning standup (AH-3):
  `total_usd`, `by_lane`, `cap_usd`, `n_paid_runs`, `has_cost_plane`. `.over_cap`
  flags a crossed cap; `.display` renders the Spend-row string ("—" pre-M9,
  "$X.XXXX / $cap" otherwise); `.as_dict()` is the `/api/standup` payload.
  `SpendDigest.from_store(store, cap_usd=…)` assembles it from the private
  `compare_responses` / `chat_turns` cost rows — operator-private, never mirrored.
- **`MemoryEnvelope`** — the GB10 unified-memory envelope the single-lane drain
  runs inside. Defaults to the Spark-measured numbers (128 GB total, a resident
  brain holding ~31.8 GB, one cold vertical ~5.5 GB). `fits(lane_id)` is the OOM
  guard (the 2026-04-22 box-hang landmine): a lane that would push past the total
  is deferred, never stacked on the resident brain.
- **`check_budget(job, *, ledger=None, envelope=None, …)`** — the one-shot
  convenience read: build a `BudgetGovernor` and decide, for a cron tick or a CLI
  check that doesn't hold a long-lived governor.
- **`BudgetError`** — raised when a governor configuration or spend read cannot
  complete.

## How the drain uses it

`fieldkit.arena.scheduler.run_drain_cycle` passes the governor to
`fieldkit.arena.jobs.drain_jobs(..., governor=…)`. Each claimed job is checked
*before* dispatch: an *allow* dispatches as usual; an *escalate* / *defer*
releases the claim back to `queued`, records a `budget_<action>` audit row in
`job_triggers`, and **stops the pass** (the budget brake — a daily-cap defer
holds all remaining work; an escalate leaves the job for the operator to promote
to a frontier lane from the standup). The drain never escalates or pushes itself
(invariants #1/#3, AH-3/AH-8): it *stages* the decision for the human-review
gate. No schema, no `user_version` bump (AH-9) — the budget policy lives in
version-controlled config, and the still-queued job plus its audit row *are* the
state.

## What it is not

It does **not** dispatch a frontier escalation itself, run the cron loop (that's
`fieldkit.arena.scheduler`), or persist a schedule (AH-9). And it never calls an
LLM — deterministic Python only (invariant #4): the governor is arithmetic over
the ledger, the envelope, and the job's declared failure class.
