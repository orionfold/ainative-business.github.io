---
title: 'Auto Research with Specialist Agents Develops Effective and Non-Trivial Training Recipes — Spark reproduction notes'
date: 2026-05-08
author: 'Manav Sehgal'
product: 'NemoClaw'
stage: agentic
difficulty: 'intermediate'
time_required: '~30 min read'
hardware: 'NVIDIA DGX Spark'
tags: ['agentic', 'autoresearch', 'multi-agent', 'lineage', 'claude-agent-sdk', 'nemoclaw']
summary: 'Reproducing the cxcscmu Auto-Research-Recipes harness on a single DGX Spark — Claude Opus 4.7 specialists driving NanoChat-D12 pretraining trials with full lineage feedback, then extracting the trial/lineage primitive into `fieldkit.lineage`.'
status: upcoming
series: 'Machine that Builds Machines'
book_chapters: [10, 11]
---

## The paper, in one breath (ARTICLE OPENING — required at publish)

> tech-writer: this becomes a `## The paper, in one breath` section in
> the published article, placed immediately after the lede and before
> any "Why this matters for a personal AI builder" substrate framing.
> Pull thesis material from the eval's `## Hypothesis`; fill in the
> achieved beat after the experiment runs.

**Thesis.** _<paraphrase the eval's Hypothesis section in 2–3 sentences, plain language, one concrete mechanism — distinguish from the obvious baseline the technique replaces>_

**Why this technique matters for a personal AI builder.** _<2 sentences on what this unlocks for the reader on a single Spark — distinct from the substrate framing in the next section>_

**Promise vs achieved.** Paper: _<headline number on reference hardware>_. Spark: _<measured number once the experiment runs>_. Delta: _<one sentence on why the gap is what it is>_.

## Source paper

- arXiv: [2605.05724](undefined) — Auto Research with Specialist Agents Develops Effective and Non-Trivial Training Recipes
- Repo: (none — see eval Blockers section)
- Popularity: 18 · 9 HF upvotes · not yet indexed

## Frontier Scout verdict

**spark-feasible** — the harness is task-agnostic and trial-size-bounded, and the Spark's 128 GB unified pool comfortably holds the largest reference task (NanoChat-D12 12-layer pretraining) within its 90-minute cap; the only adaptation is running fewer concurrent workers per supervisor.

## Hypothesis (from eval)

A team of LLM-driven specialist agents can run a *closed empirical loop* over training recipes — each agent proposes a code edit, an external evaluator runs it, the resulting score-or-failure becomes feedback for the next proposal — and the lineage of those measurements (crashes, budget overruns, accuracy-gate misses, score deltas) is what lets later trials produce *program-level* rewrites rather than one-shot suggestions. The paper instantiates this on three reference tasks (Parameter Golf, NanoChat-D12 pretraining, CIFAR-10 Airbench96) and reports SOTA-or-better deltas with no human in the loop after launch — 1,797 trials total. The contribution is the *harness* and the *lineage* artifact, not a model.

## Proposed Spark recipe

The repo is at `github.com/cxcscmu/Auto-Research-Recipes` and ships a clean adapter contract (`docs/task_adapter.md`). Reproduction path:

1. `git clone --depth 1 https://github.com/cxcscmu/Auto-Research-Recipes && cd Auto-Research-Recipes && pip install -e .`
2. Set `ANTHROPIC_API_KEY` in `.env` — the agent driver is Claude Agent SDK, not a local NIM. Capability map says "Agentic systems: tool use, multi-step planning, sandboxed execution" is in-envelope; the agent is just a remote API consumer.
3. Pick **NanoChat-D12** as the first task — it's the most representative MTBM shape (LLM-on-LLM training) and runs on a single GB10 within the 90-minute trial cap. `python -m multi_agent_nc.supervisor --state-root ./magent_state_nc`
4. Reduce the parallel-trial fanout from the published 8-H100 worker default to a **single GB10 worker** (one trial at a time). The supervisor loop, blackboard, and lineage TSV accept arbitrary worker count — the bottleneck is wall-clock per-trial, not the lineage primitive itself.
5. Tap into NemoClaw (already in the capability map's `stack`) for the sandbox — the harness's "MCP tools" wrapping in `agent_core/` is the same shape NemoClaw provides natively. (See "NemoClaw vs OpenClaw on DGX Spark" in the blog for the substrate.)
6. Inspect with `dashboard.py` while the supervisor runs; `release_artifacts/` shows what a frozen run looks like (results.tsv, tree.tsv, best.json, KNOWLEDGE.md, LEADERBOARD.md, lineage_snapshots/).

Per-trial training itself is plain PyTorch — no special TRT-LLM build flags or NIM endpoint required for the *worker*; the cleverness is on the orchestration side.

## Open questions for the experiment

- (none for the loop itself — recipe should run as-is at reduced parallelism)
- Trial throughput is the only real constraint: the published 1,500-trial Parameter Golf budget would take ~15× wall-clock on a single Spark vs. an 8-H100 node. Real Spark answer is "reproduce ~50–150 trials of one task to demonstrate the lineage primitive," not "rerun the full headline."

## Suggested article shape

- **Would write?** yes
- **Suggested slug:** auto-research-loop-on-spark
- **Suggested stage:** agentic
- **Suggested series:** Machine that Builds Machines
- **Suggested book chapters (MTBM only):** [10, 11]
- **Suggested mtbm_station (MTBM only):** planner
- **Suggested tags:** agentic, autoresearch, multi-agent, lineage, claude-agent-sdk, nemoclaw
- **Suggested summary:** Reproducing the cxcscmu Auto-Research-Recipes harness on a single DGX Spark — Claude Opus 4.7 specialists driving NanoChat-D12 pretraining trials with full lineage feedback, then extracting the trial/lineage primitive into `fieldkit.lineage`.
- **Suggested `fieldkit_modules`:** [capabilities, training]
