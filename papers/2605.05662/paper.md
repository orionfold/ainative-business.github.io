---
arxiv_id: 2605.05662
title: "XL-SafetyBench: A Country-Grounded Cross-Cultural Benchmark for LLM Safety and Cultural Sensitivity"
published: 2026-05-06
hf_upvotes: 3
popularity_score: 11
suggested_stage: observability
suggested_series: "LLM Wiki"
fast_verdict: spark-feasible
relevance_score: 0.55
has_deep_eval: false
hf_paper_url: https://huggingface.co/papers/2605.05662
---

# XL-SafetyBench: A Country-Grounded Cross-Cultural Benchmark for LLM Safety and Cultural Sensitivity

**Verdict:** spark-feasible · **Series:** LLM Wiki · **Stage:** observability · **Relevance:** 0.55 · **Popularity:** 11/100

> XL-SafetyBench — 5,500 country-grounded safety + cultural-sensitivity test cases evaluating LLMs; runs as a judge-pipeline against any Spark-resident model.

## Abstract

Current LLM safety benchmarks are predominantly English-centric and often rely on translation, failing to capture country-specific harms. Moreover, they rarely evaluate a model's ability to detect culturally embedded sensitivities as distinct from universal harms. We introduce XL-SafetyBench. a suite of 5,500 test cases across 10 country-language pairs, comprising a Jailbreak Benchmark of country-grounded adversarial prompts and a Cultural Benchmark where local sensitivities are embedded within innocuous requests. Each item is constructed via a multi-stage pipeline that combines LLM-assisted discovery, automated validation gates, and dual independent native-speaker annotators per country. To distinguish principled refusal from comprehension failure, we evaluate Attack Success Rate (ASR) alongside two complementary metrics we introduce: Neutral-Safe Rate (NSR) and Cultural Sensitivity Rate (CSR). Evaluating 10 frontier and 27 local LLMs reveals two key findings. First, jailbreak robustness and cultural awareness do not show a coupled relationship among frontier models, so a composite safety score obscures per-axis variation. Second, local models exhibit a near-linear ASR-NSR trade-off (r = -0.81), indicating that their apparent safety reflects generation failure rather than genuine alignment. XL-SafetyBench enables more nuanced, cross-cultural safety evaluation in the multilingual era.

## Why this matters for ai-field-notes

- **Topic tags:** evals, safety, guardrails, multilingual
- **NVIDIA stack:** NIM, Guardrails
- **Fast verdict rationale:** XL-SafetyBench — 5,500 country-grounded safety + cultural-sensitivity test cases evaluating LLMs; runs as a judge-pipeline against any Spark-resident model.

## Repos

_No public repo yet._

## Citations

_not yet indexed_

## Links

- [HuggingFace daily papers](https://huggingface.co/papers/2605.05662)
