---
title: "LoRA on Nemotron Nano — Fine-tuning a 9B Without Blowing Unified Memory"
date: 2026-05-14
author: Manav Sehgal
product: NeMo Customizer + Nemotron Nano 9B v2
stage: fine-tuning
difficulty: intermediate
time_required: "planned ~4 hours per sweep"
hardware: "NVIDIA DGX Spark"
tags: [fine-tuning, lora, peft, nemotron, nemo-customizer, adapters, llm-wiki, dgx-spark]
summary: "A planned walk through LoRA fine-tuning on Nemotron Nano 9B with NeMo Customizer: rank and alpha sweeps, a tiny domain corpus, and the memory accounting that keeps a PEFT run from tripping the Spark's 128 GB unified-memory wall."
status: upcoming
series: LLM Wiki
---

## What this article will answer

When is LoRA the right tool on a personal rig, and what settings keep it clean? This piece will run a small fine-tune of Nemotron Nano 9B v2 on a domain corpus, sweeping rank ∈ {8, 16, 32} and alpha across a couple of values to see what actually moves the needle.

## NVIDIA technologies to be covered

- **NeMo Customizer** — the `.yaml`-driven workflow for LoRA/QLoRA on NeMo checkpoints.
- **Nemotron Nano 9B v2** — the base model; its FP8 quantization story; how PEFT plays with quantized bases.
- **PEFT adapters** — saving, merging, and serving adapters without baking them into the base.
- **NIM-compatible deploy path** — loading the fine-tuned model behind a NIM microservice so the rest of the RAG stack keeps working.

## What I expect to find

LoRA at rank 16 on 9B should fit comfortably in unified memory with batch size 4 and sequence length 2048. The real question is not "can it fit" but "does a few hours of LoRA on a hundred-document corpus produce a model that's materially better for LLM-Wiki's compile-time summarization loop than the base + good prompting". The article closes on that comparison.

## Where it sits in the arc

Part of the **LLM Wiki** track (W-series). Builds on the seven foundation articles and complements the bigger-generator article's result that strict-context prompting has a ceiling.
