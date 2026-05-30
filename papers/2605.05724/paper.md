---
arxiv_id: 2605.05724
title: "Auto Research with Specialist Agents Develops Effective and Non-Trivial Training Recipes"
published: 2026-05-06
hf_upvotes: 9
popularity_score: 18
suggested_stage: agentic
suggested_series: "Machine that Builds Machines"
fast_verdict: spark-feasible
relevance_score: 0.95
has_deep_eval: true
deep_verdict: spark-feasible
promoted_to: auto-research-loop-on-spark
chapter_alignment: [10, 11]
mtbm_station: planner
hf_paper_url: https://huggingface.co/papers/2605.05724
---

# Auto Research with Specialist Agents Develops Effective and Non-Trivial Training Recipes

**Verdict:** spark-feasible · **Series:** Machine that Builds Machines · **Stage:** agentic · **Relevance:** 0.95 · **Popularity:** 18/100

> Closed empirical-loop auto-research with specialist agents and lineage feedback — the literal MTBM picture, fully autonomous over 1,197 trials.

## Abstract

We study auto research as a closed empirical loop driven by external measurement. Each submitted trial carries a hypothesis, an executable code edit, an evaluator-owned outcome, and feedback that shapes the next proposal. The output is not a generated paper or a single model checkpoint, but an auditable trajectory of proposals, code diffs, experiments, scores, and failure labels. We instantiate this loop with specialist agents that partition recipe surfaces and share measured lineage across trials. The central empirical finding is that lineage feedback lets agents turn evaluator outcomes, including crashes, budget overruns, size failures, and accuracy-gate misses, into later program-level recipe edits rather than one-shot suggestions. Across 1,197 headline-run trials plus 600 Parameter Golf control trials after one-time setup and launch, humans did not choose proposals, edit recipes, override scores, or repair failed trials during the search. In the three headline runs, the same submitted-trial loop reduces Parameter Golf validation bpb by 0.81%, raises NanoChat-D12 CORE by 38.7%, and reduces CIFAR-10 Airbench96 wallclock by 4.59%, with each task measured by its own external evaluator and legality checks. The trace includes a strict architecture-domain audit of 157 headline-run submissions and program rewrites such as a NanoChat attention-kernel path change. Within this scope the loop autonomously writes code, submits experiments, absorbs feedback, applies and combines known techniques inside each environment, and improves public starting recipes.

## Why this matters for ai-field-notes

- **Topic tags:** agentic, autoresearch, multi-agent, reinforcement-learning
- **NVIDIA stack:** NemoClaw, NeMo
- **Chapter alignment:** Ch10, Ch11
- **MTBM station:** planner
- **Fast verdict rationale:** Closed empirical-loop auto-research with specialist agents and lineage feedback — the literal MTBM picture, fully autonomous over 1,197 trials.

## Repos

_No public repo yet._

## Citations

_not yet indexed_

## Links

- [HuggingFace daily papers](https://huggingface.co/papers/2605.05724)

## Deep eval

[Full feasibility eval →](./eval.md) (verdict: **spark-feasible**, evaluated 2026-05-08)

## Promoted

This paper has been promoted to `articles/auto-research-loop-on-spark/` (status: upcoming).
