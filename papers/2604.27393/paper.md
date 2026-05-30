---
arxiv_id: 2604.27393
title: "MiniCPM-o 4.5: Towards Real-Time Full-Duplex Omni-Modal Interaction"
published: 2026-04-29
hf_upvotes: 42
popularity_score: 27
suggested_stage: inference
suggested_series: "LLM Wiki"
fast_verdict: spark-feasible
relevance_score: 0.6
has_deep_eval: false
hf_paper_url: https://huggingface.co/papers/2604.27393
---

# MiniCPM-o 4.5: Towards Real-Time Full-Duplex Omni-Modal Interaction

**Verdict:** spark-feasible · **Series:** LLM Wiki · **Stage:** inference · **Relevance:** 0.6 · **Popularity:** 27/100

> Open small omni-modal model with full-duplex streaming inference — sub-10B, fits 128 GB envelope and surfaces real-time inference techniques.

## Abstract

Recent progress in multimodal large language models (MLLMs) has brought AI capabilities from static offline data processing to real-time streaming interaction, yet they still remain far from human-level multimodal interaction. The key bottlenecks are no longer modality coverage or latency alone, but the interaction paradigm itself. First, perception and response are still separated into alternating phases, preventing models from incorporating new inputs for timely adjustment during generation. Second, most current models remain reactive, responding only to explicit user requests instead of acting proactively in the evolving multimodal environment. We present MiniCPM-o 4.5, our latest effort towards human-like multimodal interaction, which mitigates these gaps by real-time full-duplex omni-modal interaction. It can see, listen, and speak simultaneously in real-time, while also exhibiting proactive behaviors such as issuing reminders or comments based on its continuous understanding of the live scene. The key technique behind MiniCPM-o 4.5 is Omni-Flow, a unified streaming framework that aligns omni-modal inputs and outputs along a shared temporal axis. This formulation converts conventional turn-based interaction into a full-duplex, time-aligned process, enabling simultaneous perception and response and allowing proactive behavior to arise within the same framework. With a total of 9B parameters, MiniCPM-o 4.5 approaches Gemini 2.5 Flash in vision-language capabilities, delivering state-of-the-art open-source performance at its scale. It also surpasses Qwen3-Omni-30B-A3B in omni-modal understanding and delivers better speech generation, with significantly higher computation efficiency. Driven by its efficient architecture design and inference optimization, the model can perform real-time full-duplex omni-modal interaction on edge devices with less than 12GB RAM cost.

## Why this matters for ai-field-notes

- **Topic tags:** multimodal, inference, streaming, kv-cache
- **NVIDIA stack:** NIM, TensorRT-LLM, Triton
- **Fast verdict rationale:** Open small omni-modal model with full-duplex streaming inference — sub-10B, fits 128 GB envelope and surfaces real-time inference techniques.

## Repos

_No public repo yet._

## Citations

`citations: 0`

## Links

- [HuggingFace daily papers](https://huggingface.co/papers/2604.27393)
