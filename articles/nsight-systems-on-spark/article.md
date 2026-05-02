---
title: "Tracing a NIM Request with Nsight Systems — What the 24.8 tok/s Number Hides"
date: 2026-06-04
author: Manav Sehgal
product: NVIDIA Nsight Systems + CUDA Toolkit
stage: dev-tools
difficulty: advanced
time_required: "planned ~4 hours including trace analysis"
hardware: "NVIDIA DGX Spark"
tags: [dev-tools, nsight-systems, cuda, profiling, kernel-tracing, trtllm, optimization, dgx-spark]
summary: "A planned kernel-level trace of a single NIM inference request on GB10. Where does the wall-clock time actually go — tokenization, KV-cache attention, the sampling loop, memcpy? The article turns 24.8 tokens per second into a timeline you can point at and say 'that line is the bottleneck'."
status: upcoming
---

## What this article will answer

Headline throughput numbers are a consequence, not a cause. This piece opens the hood on the 8B NIM at inference time and asks, for a single representative request, which kernels own the latency budget and which are rounding error.

## NVIDIA technologies to be covered

- **Nsight Systems** — launching a trace against a running NIM container; NVTX ranges; filtering the timeline to the request of interest.
- **CUDA Toolkit** — minimum version requirements; `nsys` CLI on the Spark host vs inside a container.
- **Kernel trace interpretation** — attention kernels, GEMM tiles, the sampling loop, memcpy H2D/D2H; what's slow because of the model and what's slow because of the plumbing.
- **Nsight Compute** — when timeline sampling isn't enough and you need per-kernel occupancy and achieved memory throughput.
- **Editor integration** — launching captures from VS Code / Cursor without breaking the container's lifecycle.

## What I expect to find

Paged-KV attention will dominate the decode phase. Prefill will be a GEMM wall. The memcpy between host-side request parsing and GPU-side tokenization will be smaller than feared thanks to unified memory. The piece closes by feeding the trace back into the TRT-LLM article as a prioritization tool: here's what to try to fix first.

## Where it sits in the arc

Cross-cutting. Belongs to `dev-tools` primary, but pairs with the TRT-LLM deployment article — a trace in hand is the right prerequisite for deciding which compile-time knob to turn.
