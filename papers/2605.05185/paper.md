---
arxiv_id: 2605.05185
title: "OpenSearch-VL: An Open Recipe for Frontier Multimodal Search Agents"
published: 2026-05-05
hf_upvotes: 87
popularity_score: 49
suggested_stage: agentic
suggested_series: "Machine that Builds Machines"
fast_verdict: spark-feasible
relevance_score: 0.85
has_deep_eval: false
chapter_alignment: [10]
mtbm_station: forge
hf_paper_url: https://huggingface.co/papers/2605.05185
---

# OpenSearch-VL: An Open Recipe for Frontier Multimodal Search Agents

**Verdict:** spark-feasible · **Series:** Machine that Builds Machines · **Stage:** agentic · **Relevance:** 0.85 · **Popularity:** 49/100

> Open recipe for multimodal deep-search agents trained with agentic RL — SFT + RL on a single-Spark-sized policy fits the MTBM forge.

## Abstract

Deep search has become a crucial capability for frontier multimodal agents, enabling models to solve complex questions through active search, evidence verification, and multi-step reasoning. Despite rapid progress, top-tier multimodal search agents remain difficult to reproduce, largely due to the absence of open high-quality training data, transparent trajectory synthesis pipelines, or detailed training recipes. To this end, we introduce OpenSearch-VL, a fully open-source recipe for training frontier multimodal deep search agents with agentic reinforcement learning. First, we curated a dedicated pipeline to construct high-quality training data through Wikipedia path sampling, fuzzy entity rewriting, and source-anchor visual grounding, which jointly reduce shortcuts and one-step retrieval collapse. Based on this pipeline, we curate two training datasets, SearchVL-SFT-36k for SFT and SearchVL-RL-8k for RL. Besides, we design a diverse tool environment that unifies text search, image search, OCR, cropping, sharpening, super-resolution, and perspective correction, enabling agents to combine active perception with external knowledge acquisition. Finally, we propose a multi-turn fatal-aware GRPO training algorithm that handles cascading tool failures by masking post-failure tokens while preserving useful pre-failure reasoning through one-sided advantage clamping. Built on this recipe, OpenSearch-VL delivers substantial performance gains, with over 10-point average improvements across seven benchmarks, and achieves results comparable to proprietary commercial models on several tasks. We will release all data, code, and models to support open research on multimodal deep search agents.

## Why this matters for ai-field-notes

- **Topic tags:** agentic, rag, multimodal, reinforcement-learning, sft
- **NVIDIA stack:** NeMo, NIM, TensorRT-LLM
- **Chapter alignment:** Ch10
- **MTBM station:** forge
- **Fast verdict rationale:** Open recipe for multimodal deep-search agents trained with agentic RL — SFT + RL on a single-Spark-sized policy fits the MTBM forge.

## Repos

| Repo | Stars | Forks | Last commit | Language |
|------|------:|------:|-------------|----------|
| [shawn0728/OpenSearch-VL](https://github.com/shawn0728/OpenSearch-VL) | 104 | 7 | 2026-05-07 | Python |

## Citations

_not yet indexed_

## Links

- [HuggingFace daily papers](https://huggingface.co/papers/2605.05185)
