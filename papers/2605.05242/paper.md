---
arxiv_id: 2605.05242
title: "Beyond Semantic Similarity: Rethinking Retrieval for Agentic Search via Direct Corpus Interaction"
published: 2026-05-02
hf_upvotes: 6
popularity_score: 15
suggested_stage: agentic
suggested_series: "Second Brain"
fast_verdict: spark-feasible
relevance_score: 0.8
has_deep_eval: true
deep_verdict: spark-feasible
promoted_to: dci-corpus-operators-on-spark
hf_paper_url: https://huggingface.co/papers/2605.05242
---

# Beyond Semantic Similarity: Rethinking Retrieval for Agentic Search via Direct Corpus Interaction

**Verdict:** spark-feasible · **Series:** Second Brain · **Stage:** agentic · **Relevance:** 0.8 · **Popularity:** 15/100

> Agents searching the raw corpus directly via general operators (lexical, conjunctive, multi-step) instead of fixed top-k retrieval — Second Brain extension.

## Abstract

Modern retrieval systems, whether lexical or semantic, expose a corpus through a fixed similarity interface that compresses access into a single top-k retrieval step before reasoning. This abstraction is efficient, but for agentic search, it becomes a bottleneck: exact lexical constraints, sparse clue conjunctions, local context checks, and multi-step hypothesis refinement are difficult to implement by calling a conventional off-the-shelf retriever, and evidence filtered out early cannot be recovered by stronger downstream reasoning. Agentic tasks further exacerbate this limitation because they require agents to orchestrate multiple steps, including discovering intermediate entities, combining weak clues, and revising the plan after observing partial evidence. To tackle the limitation, we study direct corpus interaction (DCI), where an agent searches the raw corpus directly with general-purpose terminal tools (e.g., grep, file reads, shell commands, lightweight scripts), without any embedding model, vector index, or retrieval API. This approach requires no offline indexing and adapts naturally to evolving local corpora. Across IR benchmarks and end-to-end agentic search tasks, this simple setup substantially outperforms strong sparse, dense, and reranking baselines on several BRIGHT and BEIR datasets, and attains strong accuracy on BrowseComp-Plus and multi-hop QA without relying on any conventional semantic retriever. Our results indicate that as language agents become stronger, retrieval quality depends not only on reasoning ability but also on the resolution of the interface through which the model interacts with the corpus, with which DCI opens a broader interface-design space for agentic search.

## Why this matters for ai-field-notes

- **Topic tags:** rag, retrieval, agentic, search
- **NVIDIA stack:** NIM, NeMo
- **Fast verdict rationale:** Agents searching the raw corpus directly via general operators (lexical, conjunctive, multi-step) instead of fixed top-k retrieval — Second Brain extension.

## Repos

_No public repo yet._

## Citations

`citations: 0`

## Links

- [HuggingFace daily papers](https://huggingface.co/papers/2605.05242)

## Deep eval

[Full feasibility eval →](./eval.md) (verdict: **spark-feasible**, evaluated 2026-05-08)

## Promoted

This paper has been promoted to `articles/dci-corpus-operators-on-spark/` (status: upcoming).
