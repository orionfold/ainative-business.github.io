---
arxiv_id: 2604.25256
title: "AutoResearchBench: Benchmarking AI Agents on Complex Scientific Literature Discovery"
published: 2026-04-27
hf_upvotes: 27
popularity_score: 24
suggested_stage: agentic
suggested_series: "Machine that Builds Machines"
fast_verdict: spark-feasible
relevance_score: 0.78
has_deep_eval: true
deep_verdict: spark-feasible
promoted_to: autoresearchbench-on-spark
abs_url: https://arxiv.org/abs/2604.25256
pdf_url: https://arxiv.org/pdf/2604.25256
hf_paper_url: https://huggingface.co/papers/2604.25256
---

# AutoResearchBench: Benchmarking AI Agents on Complex Scientific Literature Discovery

**Verdict:** spark-feasible · **Series:** Machine that Builds Machines · **Stage:** agentic · **Relevance:** 0.78 · **Popularity:** 24/100

> Agent-driven literature discovery benchmark fits Machine that Builds Machines arc; runnable on Spark via NemoClaw + NIM + NeMo Retriever with pgvector, no training needed.

## Abstract

Autonomous scientific research is significantly advanced thanks to the development of AI agents. One key step in this process is finding the right scientific literature, whether to explore existing knowledge for a research problem, or to acquire evidence for verifying assumptions and supporting claims. To assess AI agents' capability in driving this process, we present AutoResearchBench, a dedicated benchmark for autonomous scientific literature discovery. AutoResearchBench consists of two complementary task types: (1) Deep Research, which requires tracking down a specific target paper through a progressive, multi-step probing process, and (2) Wide Research, which requires comprehensively collecting a set of papers satisfying given conditions. Compared to previous benchmarks on agentic web browsing, AutoResearchBench is distinguished along three dimensions: it is research-oriented, calling for in-depth comprehension of scientific concepts; literature-focused, demanding fine-grained utilization of detailed information; and open-ended, involving an unknown number of qualified papers and thus requiring deliberate reasoning and search throughout. These properties make AutoResearchBench uniquely suited for evaluating autonomous research capabilities, and extraordinarily challenging. Even the most powerful LLMs, despite having largely conquered general agentic web-browsing benchmarks such as BrowseComp, achieve only 9.39% accuracy on Deep Research and 9.31% IoU on Wide Research, while many other strong baselines fall below 5%. We publicly release the dataset and evaluation pipeline to facilitate future research in this direction. We publicly release the dataset, evaluation pipeline, and code at https://github.com/CherYou/AutoResearchBench.

## Why this matters for ai-field-notes

- **Topic tags:** agentic, rag, retrieval, reranker, observability, benchmark
- **NVIDIA stack:** NemoClaw, NIM, NeMo Retriever, pgvector, Guardrails
- **Fast verdict rationale:** Agent-driven literature discovery benchmark fits Machine that Builds Machines arc; runnable on Spark via NemoClaw + NIM + NeMo Retriever with pgvector, no training needed.

## Repos

_No public repo yet._

## Citations

_not yet indexed_

## Links

- [arXiv abstract](https://arxiv.org/abs/2604.25256)
- [PDF](https://arxiv.org/pdf/2604.25256)
- [HuggingFace daily papers](https://huggingface.co/papers/2604.25256)

## Deep eval

[Full feasibility eval →](./eval.md) (verdict: **spark-feasible**, evaluated 2026-05-02)

## Promoted

This paper has been promoted to `articles/autoresearchbench-on-spark/` (status: upcoming).
