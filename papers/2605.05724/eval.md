# Auto Research with Specialist Agents Develops Effective and Non-Trivial Training Recipes

## Hypothesis

A team of LLM-driven specialist agents can run a *closed empirical loop* over training recipes — each agent proposes a code edit, an external evaluator runs it, the resulting score-or-failure becomes feedback for the next proposal — and the lineage of those measurements (crashes, budget overruns, accuracy-gate misses, score deltas) is what lets later trials produce *program-level* rewrites rather than one-shot suggestions. The paper instantiates this on three reference tasks (Parameter Golf, NanoChat-D12 pretraining, CIFAR-10 Airbench96) and reports SOTA-or-better deltas with no human in the loop after launch — 1,797 trials total. The contribution is the *harness* and the *lineage* artifact, not a model.

## Memory budget

The agents are remote (Claude Opus 4.7 via Claude Agent SDK — no local LLM weights). The on-device cost is whatever each *trial recipe* consumes. The reference tasks are small by design — designed so a single trial fits an 8-GPU node:

| Task | Size | Trial cap | Spark fit |
|---|---|---|---|
| Parameter Golf | LM on FineWeb-derived task, 16 MB artifact cap | 10 min | trivial (sub-100M params) |
| NanoChat-D12 | 12-layer transformer pretrain, vendored nanochat tree | 90 min | comfortable (`weight_bytes(params_b≈0.5, dtype="bf16")` ≈ 1 GB) |
| CIFAR-10 Airbench96 | vision CNN, ≥0.96 accuracy gate | wall-clock minimization | trivial |

The published runs used 4,000 H100-hours (Parameter Golf) + 2,400 H100-hours (NanoChat-D12) — those are *trial budgets*, not single-trial sizes. On a single Spark you reproduce the loop with fewer concurrent trials per supervisor, not a smaller per-trial footprint.

## Proposed Spark recipe

The repo is at `github.com/cxcscmu/Auto-Research-Recipes` and ships a clean adapter contract (`docs/task_adapter.md`). Reproduction path:

1. `git clone --depth 1 https://github.com/cxcscmu/Auto-Research-Recipes && cd Auto-Research-Recipes && pip install -e .`
2. Set `ANTHROPIC_API_KEY` in `.env` — the agent driver is Claude Agent SDK, not a local NIM. Capability map says "Agentic systems: tool use, multi-step planning, sandboxed execution" is in-envelope; the agent is just a remote API consumer.
3. Pick **NanoChat-D12** as the first task — it's the most representative MTBM shape (LLM-on-LLM training) and runs on a single GB10 within the 90-minute trial cap. `python -m multi_agent_nc.supervisor --state-root ./magent_state_nc`
4. Reduce the parallel-trial fanout from the published 8-H100 worker default to a **single GB10 worker** (one trial at a time). The supervisor loop, blackboard, and lineage TSV accept arbitrary worker count — the bottleneck is wall-clock per-trial, not the lineage primitive itself.
5. Tap into NemoClaw (already in the capability map's `stack`) for the sandbox — the harness's "MCP tools" wrapping in `agent_core/` is the same shape NemoClaw provides natively. (See "NemoClaw vs OpenClaw on DGX Spark" in the blog for the substrate.)
6. Inspect with `dashboard.py` while the supervisor runs; `release_artifacts/` shows what a frozen run looks like (results.tsv, tree.tsv, best.json, KNOWLEDGE.md, LEADERBOARD.md, lineage_snapshots/).

Per-trial training itself is plain PyTorch — no special TRT-LLM build flags or NIM endpoint required for the *worker*; the cleverness is on the orchestration side.

## Blockers

- (none for the loop itself — recipe should run as-is at reduced parallelism)
- Trial throughput is the only real constraint: the published 1,500-trial Parameter Golf budget would take ~15× wall-clock on a single Spark vs. an 8-H100 node. Real Spark answer is "reproduce ~50–150 trials of one task to demonstrate the lineage primitive," not "rerun the full headline."

## Verdict

**spark-feasible** — the harness is task-agnostic and trial-size-bounded, and the Spark's 128 GB unified pool comfortably holds the largest reference task (NanoChat-D12 12-layer pretraining) within its 90-minute cap; the only adaptation is running fewer concurrent workers per supervisor.

## Fieldkit fit

- **Would import:** `fieldkit.capabilities` (envelope/feasibility checks per trial), `fieldkit.training` (currently a stub — this paper is the first concrete reason to fill it).
- **Would extend:** `fieldkit.training` — add a `TrialRunner` + `Lineage` data model that mirrors the harness's `agent_core/` blackboard. Fields straight from the paper: proposing_role, edit_domain, hypothesis_text, code_diff_summary, evaluator_status (`keep|discard|crash|budget_overrun|size_blocked`), score_delta, failure_metadata, timing.
- **Would propose for v0.2:** `fieldkit.lineage` (or `fieldkit.experiments`) — a lightweight TSV/JSONL log + `Trial` / `RecipeEdit` / `FailureLabel` / `LineageSnapshot` types adapted from `release_artifacts/`. This is the abstraction the rest of the MTBM arc has been gesturing at without a name. Pairs with `fieldkit.eval` for the judge side.

## Article suggestion

- **Would write?** yes
- **Suggested slug:** auto-research-loop-on-spark
- **Suggested stage:** agentic
- **Suggested series:** Machine that Builds Machines
- **Suggested book chapters (MTBM only):** [10, 11]
- **Suggested mtbm_station (MTBM only):** planner
- **Suggested tags:** agentic, autoresearch, multi-agent, lineage, claude-agent-sdk, nemoclaw
- **Suggested summary:** Reproducing the cxcscmu Auto-Research-Recipes harness on a single DGX Spark — Claude Opus 4.7 specialists driving NanoChat-D12 pretraining trials with full lineage feedback, then extracting the trial/lineage primitive into `fieldkit.lineage`.
- **Suggested `fieldkit_modules`:** [capabilities, training]

## Alignment lens (MTBM only)

- **Ontological** — strong: every trial is a structured TSV row with the same fields, so all agents share a vocabulary for "what a trial is" (proposal, diff, score, failure-class).
- **Teleological** — strong: the external evaluator owns scoring; agents cannot redefine success. Reward is the same column the leaderboard reads.
- **Behavioral** — partial: edge-cases are handled as failure classes (crash, budget-overrun, size-blocked, accuracy-gate miss) with explicit metadata, so the next proposal sees them rather than re-discovering them.
- **Temporal** — strong: lineage_snapshots/ + tree.tsv preserve the full causal chain across runs; alignment doesn't have to be re-bootstrapped because the system's memory of past failure modes persists.
- **Reflexive** — partial: the supervisor audit log catches some failure modes, but the agents do not estimate their own uncertainty per proposal — that's where T²PO-style work (see "T²PO: Uncertainty-Guided Exploration Control on Spark" upcoming) would compose with this loop.
