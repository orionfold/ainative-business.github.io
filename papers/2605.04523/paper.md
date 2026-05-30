---
arxiv_id: 2605.04523
title: "RaguTeam at SemEval-2026 Task 8: Meno and Friends in a Judge-Orchestrated LLM Ensemble for Faithful Multi-Turn Response Generation"
published: 2026-05-05
hf_upvotes: 27
popularity_score: 28
suggested_stage: inference
suggested_series: "LLM Wiki"
fast_verdict: spark-feasible
relevance_score: 0.7
has_deep_eval: true
deep_verdict: spark-feasible
promoted_to: judge-orchestrated-ensemble-on-spark
hf_paper_url: https://huggingface.co/papers/2605.04523
---

# RaguTeam at SemEval-2026 Task 8: Meno and Friends in a Judge-Orchestrated LLM Ensemble for Faithful Multi-Turn Response Generation

**Verdict:** spark-feasible · **Series:** LLM Wiki · **Stage:** inference · **Relevance:** 0.7 · **Popularity:** 28/100

> Judge-orchestrated 7-LLM ensemble for multi-turn RAG (SemEval-2026 T8 winner) — every member except gpt-oss-120b fits a single Spark.

## Abstract

We present our winning system for Task~B (generation with reference passages) in SemEval-2026 Task~8: MTRAGEval. Our method is a heterogeneous ensemble of seven LLMs with two prompting variants, where a GPT-4o-mini judge selects the best candidate per instance. We ranked 1st out of 26 teams, achieving a conditioned harmonic mean of 0.7827 and outperforming the strongest baseline (gpt-oss-120b, 0.6390). Ablations show that diversity in model families, scales, and prompting strategies is essential, with the ensemble consistently beating any single model. We also introduce Meno-Lite-0.1, a 7B domain-adapted model with a strong cost--performance trade-off, and analyse MTRAGEval, highlighting annotation limitations and directions for improvement. Our code is publicly available: https://github.com/RaguTeam/ragu_mtrag_semeval

## Why this matters for ai-field-notes

- **Topic tags:** rag, ensemble, judge, multi-agent
- **NVIDIA stack:** NIM, NeMo
- **Fast verdict rationale:** Judge-orchestrated 7-LLM ensemble for multi-turn RAG (SemEval-2026 T8 winner) — every member except gpt-oss-120b fits a single Spark.

## Repos

| Repo | Stars | Forks | Last commit | Language |
|------|------:|------:|-------------|----------|
| [RaguTeam/ragu_mtrag_semeval](https://github.com/RaguTeam/ragu_mtrag_semeval) | 1 | 1 | 2026-05-04 | Jupyter Notebook |

## Citations

_not yet indexed_

## Links

- [HuggingFace daily papers](https://huggingface.co/papers/2605.04523)

## Deep eval

[Full feasibility eval →](./eval.md) (verdict: **spark-feasible**, evaluated 2026-05-08)

## Promoted

This paper has been promoted to `articles/judge-orchestrated-ensemble-on-spark/` (status: upcoming).
