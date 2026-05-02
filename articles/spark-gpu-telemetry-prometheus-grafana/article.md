---
title: "Watching the GPU — DCGM, Prometheus, and a Local Grafana for the Spark"
date: 2026-05-28
author: Manav Sehgal
product: NVIDIA DCGM + Prometheus + Grafana
stage: observability
difficulty: intermediate
time_required: "planned ~3 hours, mostly dashboard tuning"
hardware: "NVIDIA DGX Spark"
tags: [observability, dcgm, prometheus, grafana, gpu-telemetry, nvidia-smi, unified-memory, dgx-spark]
summary: "A planned setup of DCGM Exporter → Prometheus → Grafana entirely on the Spark itself. The goal is a single dashboard that tells the truth about GPU memory, SM occupancy, and per-container utilization for a rig that's running NIMs, pgvector, and an occasional training job at the same time."
status: upcoming
---

## What this article will answer

The Spark's unified memory is shared CPU+GPU, which means `nvidia-smi` alone doesn't tell the whole story. This piece wires up a proper telemetry stack so the next OOM landmine gets caught by a dashboard, not a hard-hung box.

## NVIDIA technologies to be covered

- **DCGM Exporter** — the NVIDIA-maintained Prometheus exporter; which metrics are worth scraping on GB10, which are noise.
- **nvidia-smi dmon** — fast sanity-check loop when Grafana is down.
- **Prometheus** — local scrape config, retention sized for a personal rig.
- **Grafana dashboards** — one pane for memory (unified budget + per-container attribution), one for SM occupancy, one for power and thermals.
- **Kernel-level hooks** — where `nvidia-smi` stops being enough and Nsight Systems takes over (forward reference to the Nsight article).

## What I expect to find

The interesting metric is not peak GPU utilization — it's the shape of memory over time as NIMs warm up and pgvector indexes churn. The article closes with a screenshot of the dashboard the day the Spark hung on 2026-04-22, so the visual becomes a diagnostic template for next time.

## Where it sits in the arc

Cross-cutting. Useful for all three application tracks (Second Brain, LLM Wiki, Autoresearch) — whichever is running at the moment, the dashboard is the same.
