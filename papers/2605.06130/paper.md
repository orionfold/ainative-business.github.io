---
arxiv_id: 2605.06130
title: "Skill1: Unified Evolution of Skill-Augmented Agents via Reinforcement Learning"
published: 2026-05-06
hf_upvotes: 45
popularity_score: 30
suggested_stage: agentic
suggested_series: "Machine that Builds Machines"
fast_verdict: spark-feasible
relevance_score: 0.85
has_deep_eval: false
chapter_alignment: [10]
mtbm_station: forge
hf_paper_url: https://huggingface.co/papers/2605.06130
---

# Skill1: Unified Evolution of Skill-Augmented Agents via Reinforcement Learning

**Verdict:** spark-feasible · **Series:** Machine that Builds Machines · **Stage:** agentic · **Relevance:** 0.85 · **Popularity:** 30/100

> Single policy co-evolving skill selection + utilization + distillation from one task-outcome reward — clean MTBM forge case at sub-70B.

## Abstract

A persistent skill library allows language model agents to reuse successful strategies across tasks. Maintaining such a library requires three coupled capabilities. The agent selects a relevant skill, utilizes it during execution, and distills new skills from experience. Existing methods optimize these capabilities in isolation or with separate reward sources, resulting in partial and conflicting evolution. We propose Skill1, a framework that trains a single policy to co-evolve skill selection, utilization, and distillation toward a shared task-outcome objective. The policy generates a query to search the skill library, re-ranks candidates to select one, solves the task conditioned on it, and distills a new skill from the trajectory. All learning derives from a single task-outcome signal. Its low-frequency trend credits selection and its high-frequency variation credits distillation. Experiments on ALFWorld and WebShop show that Skill1 outperforms prior skill-based and reinforcement learning baselines. Training dynamics confirm the co-evolution of the three capabilities, and ablations show that removing any credit signal degrades the evolution.

## Why this matters for ai-field-notes

- **Topic tags:** agentic, reinforcement-learning, self-improvement
- **NVIDIA stack:** NeMo, NemoClaw
- **Chapter alignment:** Ch10
- **MTBM station:** forge
- **Fast verdict rationale:** Single policy co-evolving skill selection + utilization + distillation from one task-outcome reward — clean MTBM forge case at sub-70B.

## Repos

_No public repo yet._

## Citations

_not yet indexed_

## Links

- [HuggingFace daily papers](https://huggingface.co/papers/2605.06130)
