---
title: "Gates Before the Advisor — Recall Floors, Raw-Base Preflights, and the Bench That Ate Its Own Spec"
date: 2026-06-14
author: Manav Sehgal
product: NIM
stage: inference
difficulty: advanced
time_required: "planned ~14 min read"
hardware: "NVIDIA DGX Spark"
tags: [rag, recall, retrieval-eval, preflight, corpus, pgvector, embedding, advisor, dgx-spark]
summary: "Before the Advisor trained: a 182-source corpus pack with recall gates on two retrieval lanes (BM25 and live pgvector + NIM embedder), raw-base preflights that failed two NVIDIA bases honestly, and the rebuild that caught the bench's own spec contaminating its retrieval context."
status: upcoming
series: Machine that Builds Machines
---

The companion piece to [The Refusal Floor Is Trainable](/articles/the-refusal-floor-is-trainable/), covering everything that gated the Orionfold Advisor *before* a single training minute was spent.

Planned coverage: how a public corpus becomes a governed **corpus pack** (manifest with roles and trust tiers, a frozen bench seed, refusal and private-state cases); scoring source-recall@k on a cheap BM25 proxy *and* the production lane (pgvector `advisor_corpus_v01` + the `llama-nemotron-embed-1b-v2` NIM, 0.977@5, 1.0 on held-out answerable); and the raw-floor preflight that disqualified two candidate bases through the visible Arena cockpit — including a reasoning-mode leak on 7 of 8 packets that no amount of prompt politeness fixed.

The centerpiece incident: a deliberate corpus-freshness rebuild pulled the Advisor's *own proof spec* — the document defining the bench and its erratum — into the retrieval index, and the erratum text started surfacing inside eval packets. The full gate re-run caught it before anything shipped; proof-control documents are now excluded at manifest-generation time. The lesson generalizes to any self-documenting system that retrieves over its own repository.
