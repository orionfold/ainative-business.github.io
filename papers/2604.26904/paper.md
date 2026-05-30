---
arxiv_id: 2604.26904
title: "ClawGym: A Scalable Framework for Building Effective Claw Agents"
published: 2026-04-28
hf_upvotes: 44
popularity_score: 27
suggested_stage: agentic
suggested_series: "Machine that Builds Machines"
fast_verdict: spark-feasible
relevance_score: 0.82
has_deep_eval: true
deep_verdict: spark-feasible
promoted_to: clawgym-on-spark
abs_url: https://arxiv.org/abs/2604.26904
pdf_url: https://arxiv.org/pdf/2604.26904
hf_paper_url: https://huggingface.co/papers/2604.26904
---

# ClawGym: A Scalable Framework for Building Effective Claw Agents

**Verdict:** spark-feasible · **Series:** Machine that Builds Machines · **Stage:** agentic · **Relevance:** 0.82 · **Popularity:** 27/100

> Claw-style sandboxed agent SFT + lightweight RL on per-task sandboxes maps directly onto NemoClaw + NeMo fine-tuning within the 128 GB envelope.

## Abstract

Claw-style environments support multi-step workflows over local files, tools, and persistent workspace states. However, scalable development around these environments remains constrained by the absence of a systematic framework, especially one for synthesizing verifiable training data and integrating it with agent training and diagnostic evaluation. To address this challenge, we present ClawGym, a scalable framework that supports the full lifecycle of Claw-style personal agent development. Concretely, we construct ClawGym-SynData, a diverse dataset of 13.5K filtered tasks synthesized from persona-driven intents and skill-grounded operations, paired with realistic mock workspaces and hybrid verification mechanisms. We then train a family of capable Claw-style models, termed ClawGym-Agents, through supervised fine-tuning on black-box rollout trajectories, and further explore reinforcement learning via a lightweight pipeline that parallelizes rollouts across per-task sandboxes.To support reliable evaluation, we further construct ClawGym-Bench, a benchmark of 200 instances calibrated through automated filtering and human-LLM review. Relevant resources will be soon released at https://github.com/ClawGym.

## Why this matters for ai-field-notes

- **Topic tags:** agentic, sandboxing, fine-tuning, lora, peft, rag, observability
- **NVIDIA stack:** NemoClaw, NeMo, NIM, Guardrails
- **Fast verdict rationale:** Claw-style sandboxed agent SFT + lightweight RL on per-task sandboxes maps directly onto NemoClaw + NeMo fine-tuning within the 128 GB envelope.

## Repos

_No public repo yet._

## Citations

_not yet indexed_

## Links

- [arXiv abstract](https://arxiv.org/abs/2604.26904)
- [PDF](https://arxiv.org/pdf/2604.26904)
- [HuggingFace daily papers](https://huggingface.co/papers/2604.26904)

## Deep eval

[Full feasibility eval →](./eval.md) (verdict: **spark-feasible**, evaluated 2026-05-02)

## Promoted

This paper has been promoted to `articles/clawgym-on-spark/` (status: upcoming).
