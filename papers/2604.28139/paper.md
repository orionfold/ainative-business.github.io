---
arxiv_id: 2604.28139
title: "Claw-Eval-Live: A Live Agent Benchmark for Evolving Real-World Workflows"
published: 2026-04-29
primary_category: cs.SE
hf_upvotes: 22
popularity_score: 23
suggested_stage: agentic
suggested_series: "Machine that Builds Machines"
fast_verdict: spark-feasible
relevance_score: 0.78
has_deep_eval: true
deep_verdict: spark-feasible
promoted_to: claw-eval-live-on-spark
abs_url: https://arxiv.org/abs/2604.28139
pdf_url: https://arxiv.org/pdf/2604.28139
hf_paper_url: https://huggingface.co/papers/2604.28139
---

# Claw-Eval-Live: A Live Agent Benchmark for Evolving Real-World Workflows

**Verdict:** spark-feasible · **Series:** Machine that Builds Machines · **Stage:** agentic · **Relevance:** 0.78 · **Popularity:** 23/100

> Live agent benchmark with execution traces and graders maps cleanly onto NemoClaw/OpenClaw sandboxed agents on Spark for local workflow eval.

## Abstract

LLM agents are expected to complete end-to-end units of work across software tools, business services, and local workspaces. Yet many agent benchmarks freeze a curated task set at release time and grade mainly the final response, making it difficult to evaluate agents against evolving workflow demand or verify whether a task was executed. We introduce Claw-Eval-Live, a live benchmark for workflow agents that separates a refreshable signal layer, updated across releases from public workflow-demand signals, from a reproducible, time-stamped release snapshot. Each release is constructed from public workflow-demand signals, with ClawHub Top-500 skills used in the current release, and materialized as controlled tasks with fixed fixtures, services, workspaces, and graders. For grading, Claw-Eval-Live records execution traces, audit logs, service state, and post-run workspace artifacts, using deterministic checks when evidence is sufficient and structured LLM judging only for semantic dimensions. The release contains 105 tasks spanning controlled business services and local workspace repair, and evaluates 13 frontier models under a shared public pass rule. Experiments reveal that reliable workflow automation remains far from solved: the leading model passes only 66.7% of tasks and no model reaches 70%. Failures are structured by task family and execution surface, with HR, management, and multi-system business workflows as persistent bottlenecks and local workspace repair comparatively easier but unsaturated. Leaderboard rank alone is insufficient because models with similar pass rates can diverge in overall completion, and task-level discrimination concentrates in a middle band of tasks. Claw-Eval-Live suggests that workflow-agent evaluation should be grounded twice, in fresh external demand and in verifiable agent action.

## Why this matters for ai-field-notes

- **Topic tags:** agentic, observability, sandboxing, evals, benchmarks, tool-use
- **NVIDIA stack:** NemoClaw, OpenClaw, Guardrails
- **Fast verdict rationale:** Live agent benchmark with execution traces and graders maps cleanly onto NemoClaw/OpenClaw sandboxed agents on Spark for local workflow eval.

## Repos

_No public repo yet._

## Citations

_not yet indexed_

## Links

- [arXiv abstract](https://arxiv.org/abs/2604.28139)
- [PDF](https://arxiv.org/pdf/2604.28139)
- [HuggingFace daily papers](https://huggingface.co/papers/2604.28139)

## Deep eval

[Full feasibility eval →](./eval.md) (verdict: **spark-feasible**, evaluated 2026-05-02)

## Promoted

This paper has been promoted to `articles/claw-eval-live-on-spark/` (status: upcoming).
