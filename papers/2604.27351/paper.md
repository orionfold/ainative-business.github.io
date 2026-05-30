---
arxiv_id: 2604.27351
title: "Heterogeneous Scientific Foundation Model Collaboration"
published: 2026-04-29
hf_upvotes: 181
popularity_score: 38
suggested_stage: agentic
suggested_series: "Machine that Builds Machines"
fast_verdict: spark-feasible
relevance_score: 0.65
has_deep_eval: true
deep_verdict: spark-feasible
promoted_to: scientific-foundation-models-as-tools
abs_url: https://arxiv.org/abs/2604.27351
pdf_url: https://arxiv.org/pdf/2604.27351
hf_paper_url: https://huggingface.co/papers/2604.27351
---

# Heterogeneous Scientific Foundation Model Collaboration

**Verdict:** spark-feasible · **Series:** Machine that Builds Machines · **Stage:** agentic · **Relevance:** 0.65 · **Popularity:** 38/100

> Lightweight LLM-orchestrator over domain foundation models is software glue that fits NemoClaw/NIM; underlying scientific FMs would be hosted as endpoints.

## Abstract

Agentic large language model systems have demonstrated strong capabilities. However, their reliance on language as the universal interface fundamentally limits their applicability to many real-world problems, especially in scientific domains where domain-specific foundation models have been developed to address specialized tasks beyond natural language. In this work, we introduce Eywa, a heterogeneous agentic framework designed to extend language-centric systems to a broader class of scientific foundation models. The key idea of Eywa is to augment domain-specific foundation models with a language-model-based reasoning interface, enabling language models to guide inference over non-linguistic data modalities. This design allows predictive foundation models, which are typically optimized for specialized data and tasks, to participate in higher-level reasoning and decision-making processes within agentic systems. Eywa can serve as a drop-in replacement for a single-agent pipeline (EywaAgent) or be integrated into existing multi-agent systems by replacing traditional agents with specialized agents (EywaMAS). We further investigate a planning-based orchestration framework in which a planner dynamically coordinates traditional agents and Eywa agents to solve complex tasks across heterogeneous data modalities (EywaOrchestra). We evaluate Eywa across a diverse set of scientific domains spanning physical, life, and social sciences. Experimental results demonstrate that Eywa improves performance on tasks involving structured and domain-specific data, while reducing reliance on language-based reasoning through effective collaboration with specialized foundation models.

## Why this matters for ai-field-notes

- **Topic tags:** agentic, tool-use, multimodal, foundation-models
- **NVIDIA stack:** NemoClaw, NIM, Guardrails
- **Fast verdict rationale:** Lightweight LLM-orchestrator over domain foundation models is software glue that fits NemoClaw/NIM; underlying scientific FMs would be hosted as endpoints.

## Repos

_No public repo yet._

## Citations

_not yet indexed_

## Links

- [arXiv abstract](https://arxiv.org/abs/2604.27351)
- [PDF](https://arxiv.org/pdf/2604.27351)
- [HuggingFace daily papers](https://huggingface.co/papers/2604.27351)

## Deep eval

[Full feasibility eval →](./eval.md) (verdict: **spark-feasible**, evaluated 2026-05-02)

## Promoted

This paper has been promoted to `articles/scientific-foundation-models-as-tools/` (status: upcoming).
