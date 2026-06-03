---
title: "The Living Model: a local model that keeps measurably improving — sold on its own delta chart"
date: 2026-06-03
author: Manav Sehgal
product_name: "The Living Model"
tagline: "A local domain model re-trained on a cadence against a freshening bench — sold on its own lineage delta chart."
summary: "An upcoming Orionfold product: a domain model the Spark re-RLVRs on a cadence against a freshening bench, sold on a public delta chart drawn from its own training lineage. The pitch isn't a score — it's the trend. Ships when the GPU backend lands and a real run draws the chart."
hardware: NVIDIA DGX Spark
status: upcoming
series: Cockpit
tags: [living-model, rlvr, self-improving, lineage, delta-chart, local-llm, dgx-spark, fieldkit, orionfold, upcoming]
repo_url: "https://pypi.org/project/fieldkit/"
fieldkit_modules: [rl, reward, lineage]
# build: real mined footprint of the RLVR engine this product is a thin surface over
# (fieldkit.rl + fieldkit.reward, shipped in fieldkit v0.20.0). The infographic is
# hidden for status: upcoming — the product itself has no build session yet; these
# numbers describe the engine it will surface, kept for provenance (assets/build-metrics.json).
build:
  window: "the RLVR engine it surfaces — fieldkit.rl + fieldkit.reward, shipped in fieldkit v0.20.0"
  wall_clock_hours: 0.0
  sessions: 3
  assistant_turns: 111
  tokens_processed: 13527759
  tokens_generated: 101391
  cache_read_tokens: 13025393
  lines_of_code: 624
  test_cases: 21
  feature_count: 0
  models: ["Claude Opus 4.8"]
  daily_driver: "Claude Opus 4.8"
  harness: "Claude Code"
features: []
---

<!-- Upcoming placeholder — a public commitment, not a launch. Promote to status: published
     when fieldkit.rl gpu_seams is vendored and the first real rl_run produces lineage delta
     data to draw the hero chart from. The infographic + feature tour are hidden until then. -->

## The lead — what it is

**The Living Model** is an Orionfold product that doesn't ship as a frozen artifact. It ships as a domain model the DGX Spark re-trains on a cadence — every week, say — against a benchmark that keeps freshening, and it sells on a single thing a static download can't honestly show: a **public delta chart** of how much better it got, drawn straight from its own training lineage. You don't buy a number on a card that was true the day it was uploaded. You buy a trend you can watch, with receipts.

This is the first product in the [Cockpit](/field-notes/series/cockpit/) series to lead with a *living* hero instead of a build-metrics infographic. It is an **upcoming** commitment, not a shipped launch — the engine underneath is built and on PyPI, but the product flips to published when the loop runs end-to-end on real weights (the honest gap is named below). The slug is staked here so the trend has somewhere to land.

## What it unlocks

For the reader, the pitch is durability. A static fine-tune is a snapshot — the moment a domain shifts, a regulation changes, or the bench it was scored against goes stale, the number on its card quietly stops meaning what it meant. A living model answers the only question that actually matters for a model you'll *keep* using: is it still getting better, and can I see it? The product surfaces a chart that says yes — each re-training cycle plotted against a held-out split, with the selected checkpoint marked, so the improvement is the one you can trust rather than the one that merely climbed.

That's a claim a hosted RAG or a frozen GGUF can't make on its own terms, and it's one a single operator can now make honestly — because the whole loop, including the reward function and the lineage record, runs on one box you own. The differentiator isn't "it's good." It's "it's measurably *getting* good, on a cadence, and here is the trajectory."

## How it works — a thin surface over a built engine

The Living Model is largely a presentation layer over machinery that already shipped. The re-training is the [closed-loop RLVR engine](/field-notes/the-machine-improves-itself/) — [`fieldkit.rl`](/fieldkit/api/rl/) plus [`fieldkit.reward`](/fieldkit/api/reward/) — where the Spark's own deterministic verifiers are the reward function (no learned reward model), and the published checkpoint is selected on a frozen held-out split so the chart shows real improvement, not pool overfitting. Each cadence run is dispatched and watched through the [Arena control plane](/products/arena-control-plane/): the budget-governed scheduler drains the `rl_run` overnight, single-lane, after the recall layer checks whether the run has been tried and the cost ledger prices it.

The hero chart is not a marketing curve. It is the run's `LineageSnapshot` — the same [`fieldkit.lineage`](/fieldkit/api/lineage/) record the rest of the system writes — rendered as a delta over cycles, one `Trial` per step, the held-out trajectory with the selected checkpoint pinned. The product's honesty is structural: the chart can only show what the lineage store actually recorded.

## What's gated — and what's next

The honest gap is one piece, and it's a deliberate fast-follow. The engine ships as orchestration with injected GPU seams: `fieldkit.rl.gpu_seams` raises until a pinned aarch64 + CUDA-13 vLLM and the proven REINFORCE loop are vendored into the `fieldkit[rl]` extra. Until that lands and a first real `rl_run` produces a lineage delta, there is no genuine trajectory to chart — so this product is staged, not shipped. Manufacturing a delta from anything but a real run would defeat the entire point of selling the trend.

When the backend lands and the first cadence run completes, this page promotes to a published launch: the hero delta chart, a feature tour of the cockpit's living-model surface, and the real mined build story. Until then it's a commitment — the slug claimed, the shape drawn, the receipts pending. Watch the [`fieldkit`](https://pypi.org/project/fieldkit/) releases for the `fieldkit[rl]` extra; that's the signal the loop has started turning on real weights.
