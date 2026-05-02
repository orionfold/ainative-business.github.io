---
title: "Continued Pre-training on a DGX Spark — NeMo Framework Without a Cluster"
date: 2026-05-07
author: Manav Sehgal
product: NeMo Framework + Llama 3.1 8B
stage: training
difficulty: advanced
time_required: "planned ~2 days of wall-clock, one long weekend"
hardware: "NVIDIA DGX Spark"
tags: [training, nemo, megatron, continued-pretraining, llama, bf16, activation-checkpoint, autoresearch, dgx-spark]
summary: "When does it make sense to continue pre-training on a single GB10 box, and when is it a category error? A planned run that pushes NeMo Framework, Megatron-LM parallelism, and BF16 mixed precision against the 128 GB unified-memory wall with a small domain corpus."
status: upcoming
series: Autoresearch
---

## What this article will answer

Continued pre-training is usually framed as a cluster sport. This piece tests whether there's a useful envelope for it on a single DGX Spark: a small domain corpus, a modestly-sized base (Llama 3.1 8B or Nemotron Nano 9B), and a week of wall-clock.

## NVIDIA technologies to be covered

- **NeMo Framework 24.09+** — the `.nemo` checkpoint, the Megatron-LM backbone, the YAML-first config surface.
- **Megatron-LM parallelism knobs** — tensor-parallel and pipeline-parallel settings on a single GPU (both forced to 1, which narrows what we can train).
- **BF16 mixed precision + gradient checkpointing** — activation recompute vs. activation offload trade-offs on unified memory.
- **NeMo data prep pipelines** — tokenizing a domain corpus with the base model's tokenizer and streaming it into the training loop.
- **Checkpoint → `.nemo` → NIM** — converting a continued-pre-trained checkpoint back into something a Nemotron NIM can serve.

## What I expect to find

The unified-memory budget is load-bearing. 8B at BF16 with activations checkpointed should fit. 49B won't. Gradient accumulation will substitute for a bigger batch size. The bigger question this article closes is: for an Autoresearch loop that wants overnight training, is continued pre-training ever the right tool, or does LoRA always win on a personal rig?

## Where it sits in the arc

First article of the **Autoresearch** track (A1 in the shared-substrate arc). Presumes the seven foundation articles are already standing.
