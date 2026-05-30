---
arxiv_id: 2605.02178
title: "T^2PO: Uncertainty-Guided Exploration Control for Stable Multi-Turn Agentic Reinforcement Learning"
published: 2026-05-03
hf_upvotes: 5
popularity_score: 21
suggested_stage: training
suggested_series: "Machine that Builds Machines"
fast_verdict: spark-feasible
relevance_score: 0.8
has_deep_eval: true
deep_verdict: spark-feasible
promoted_to: t2po-uncertainty-guided-rl-on-spark
abs_url: https://arxiv.org/abs/2605.02178
pdf_url: https://arxiv.org/pdf/2605.02178
hf_paper_url: https://huggingface.co/papers/2605.02178
---

# T^2PO: Uncertainty-Guided Exploration Control for Stable Multi-Turn Agentic Reinforcement Learning

**Verdict:** spark-feasible · **Series:** Machine that Builds Machines · **Stage:** training · **Relevance:** 0.8 · **Popularity:** 21/100

> Uncertainty-guided exploration for multi-turn agentic RL — direct sequel to the GRPO-on-ClawGym arc.

## Abstract

Recent progress in multi-turn reinforcement learning (RL) has significantly improved reasoning LLMs' performances on complex interactive tasks. Despite advances in stabilization techniques such as fine-grained credit assignment and trajectory filtering, instability remains pervasive and often leads to training collapse. We argue that this instability stems from inefficient exploration in multi-turn settings, where policies continue to generate low-information actions that neither reduce uncertainty nor advance task progress. To address this issue, we propose Token- and Turn-level Policy Optimization (T^2PO), an uncertainty-aware framework that explicitly controls exploration at fine-grained levels. At the token level, T^2PO monitors uncertainty dynamics and triggers a thinking intervention once the marginal uncertainty change falls below a threshold. At the turn level, T^2PO identifies interactions with negligible exploration progress and dynamically resamples such turns to avoid wasted rollouts. We evaluate T^2PO in diverse environments, including WebShop, ALFWorld, and Search QA, demonstrating substantial gains in training stability and performance improvements with better exploration efficiency. Code is available at: https://github.com/WillDreamer/T2PO.

## Why this matters for ai-field-notes

- **Topic tags:** rl, grpo, ppo, agentic, exploration, stability
- **NVIDIA stack:** NeMo, NemoClaw
- **Fast verdict rationale:** Uncertainty-guided exploration for multi-turn agentic RL — direct sequel to the GRPO-on-ClawGym arc.

## Repos

| Repo | Stars | Forks | Last commit | Language |
|------|------:|------:|-------------|----------|
| [WillDreamer/T2PO](https://github.com/WillDreamer/T2PO) | 12 | 0 | 2026-05-05 | Python |

## Citations

_not yet indexed_

## Links

- [arXiv abstract](https://arxiv.org/abs/2605.02178)
- [PDF](https://arxiv.org/pdf/2605.02178)
- [HuggingFace daily papers](https://huggingface.co/papers/2605.02178)

## Deep eval

[Full feasibility eval →](./eval.md) (verdict: **spark-feasible**, evaluated 2026-05-07)

## Promoted

This paper has been promoted to `articles/t2po-uncertainty-guided-rl-on-spark/` (status: upcoming).
