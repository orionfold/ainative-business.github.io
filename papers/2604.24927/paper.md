---
arxiv_id: 2604.24927
title: "Large Language Models Explore by Latent Distilling"
published: 2026-04-26
hf_upvotes: 59
popularity_score: 29
suggested_stage: inference
suggested_series: "LLM Wiki"
fast_verdict: spark-feasible
relevance_score: 0.72
has_deep_eval: true
deep_verdict: spark-feasible
promoted_to: test-time-distilling-for-exploration
abs_url: https://arxiv.org/abs/2604.24927
pdf_url: https://arxiv.org/pdf/2604.24927
hf_paper_url: https://huggingface.co/papers/2604.24927
---

# Large Language Models Explore by Latent Distilling

**Verdict:** spark-feasible · **Series:** LLM Wiki · **Stage:** inference · **Relevance:** 0.72 · **Popularity:** 29/100

> Lightweight test-time distiller plus reweighted sampling on existing open-weight reasoning models fits comfortably within Spark's 128 GB inference envelope.

## Abstract

Generating diverse responses is crucial for test-time scaling of large language models (LLMs), yet standard stochastic sampling mostly yields surface-level lexical variation, limiting semantic exploration. In this paper, we propose Exploratory Sampling (ESamp), a decoding approach that explicitly encourages semantic diversity during generation. ESamp is motivated by the well-known observation that neural networks tend to make lower-error predictions on inputs similar to those encountered before, and incur higher prediction error on novel ones. Building on this property, we train a lightweight Distiller at test time to predict deep-layer hidden representations of the LLM from its shallow-layer representations to model the LLM's depth-wise representation transitions. During decoding, the Distiller continuously adapts to the mappings induced by the current generation context. ESamp uses the prediction error as a novelty signal to reweight candidate token extensions conditioned on the current prefix, thereby biasing decoding toward less-explored semantic patterns. ESamp is implemented with an asynchronous training--inference pipeline, with less than 5% worst case overhead (1.2% in the optimized release). Empirical results show that ESamp significantly boosts the Pass@k efficiency of reasoning models, showing superior or comparable performance to strong stochastic and heuristic baselines. Notably, ESamp achieves robust generalization across mathematics, science, and code generation benchmarks and breaks the trade-off between diversity and coherence in creative writing. Our code has released at: https://github.com/LinesHogan/tLLM.

## Why this matters for ai-field-notes

- **Topic tags:** decoding, sampling, test-time-scaling, reasoning, distillation, kv-cache
- **NVIDIA stack:** TRT-LLM, Triton, NIM
- **Fast verdict rationale:** Lightweight test-time distiller plus reweighted sampling on existing open-weight reasoning models fits comfortably within Spark's 128 GB inference envelope.

## Repos

_No public repo yet._

## Citations

_not yet indexed_

## Links

- [arXiv abstract](https://arxiv.org/abs/2604.24927)
- [PDF](https://arxiv.org/pdf/2604.24927)
- [HuggingFace daily papers](https://huggingface.co/papers/2604.24927)

## Deep eval

[Full feasibility eval →](./eval.md) (verdict: **spark-feasible**, evaluated 2026-05-02)

## Promoted

This paper has been promoted to `articles/test-time-distilling-for-exploration/` (status: upcoming).
