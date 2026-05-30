---
arxiv_id: 2605.02910
title: "CreativityBench: Evaluating Agent Creative Reasoning via Affordance-Based Tool Repurposing"
published: 2026-05-05
hf_upvotes: 18
popularity_score: 23
suggested_stage: observability
suggested_series: "LLM Wiki"
fast_verdict: spark-feasible
relevance_score: 0.65
has_deep_eval: false
hf_paper_url: https://huggingface.co/papers/2605.02910
---

# CreativityBench: Evaluating Agent Creative Reasoning via Affordance-Based Tool Repurposing

**Verdict:** spark-feasible · **Series:** LLM Wiki · **Stage:** observability · **Relevance:** 0.65 · **Popularity:** 23/100

> CreativityBench — affordance-grounded creativity benchmark with 14K tasks evaluating 10 LLMs; eval-pipeline-on-Spark territory.

## Abstract

Recent advances in large language models have led to strong performance on reasoning and environment-interaction tasks, yet their ability for creative problem-solving remains underexplored. We study this capability through the lens of creative tool use, where a model repurposes available objects by reasoning about their affordances and attributes rather than relying on canonical usage. As a first step, we introduce CreativityBench, a benchmark for evaluating affordance-based creativity in LLMs. To this end, we build a large-scale affordance knowledge base (KB) with 4K entities and 150K+ affordance annotations, explicitly linking objects, parts, attributes, and actionable uses. Building on this KB, we generate 14K grounded tasks that require identifying non-obvious yet physically plausible solutions under constraints. Evaluations across 10 state-of-the-art LLMs, including closed and open-source models, show that models can often select a plausible object, but fail to identify the correct parts, their affordances, and the underlying physical mechanism needed to solve the task, leading to a significant drop in performance. Furthermore, improvements from model scaling quickly saturate, strong general reasoning does not reliably translate to creative affordance discovery, and common inference-time strategies such as Chain-of-Thought yield limited gains. These results suggest that creative tool use remains a major challenge for current models, and that CreativityBench provides a useful testbed for studying this missing dimension of intelligence, with potential implications for planning and reasoning modules in future agents.

## Why this matters for ai-field-notes

- **Topic tags:** evals, agentic, reasoning
- **NVIDIA stack:** NIM
- **Fast verdict rationale:** CreativityBench — affordance-grounded creativity benchmark with 14K tasks evaluating 10 LLMs; eval-pipeline-on-Spark territory.

## Repos

_No public repo yet._

## Citations

_not yet indexed_

## Links

- [HuggingFace daily papers](https://huggingface.co/papers/2605.02910)
