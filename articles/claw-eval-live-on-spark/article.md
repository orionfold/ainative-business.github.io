---
title: 'Claw-Eval-Live on Spark — Spark reproduction notes'
date: 2026-05-02
author: 'Manav Sehgal'
product: 'NemoClaw'
stage: observability
difficulty: 'intermediate'
time_required: '~30 min read'
hardware: 'NVIDIA DGX Spark'
tags: [agentic, benchmark, sandboxing, evals, llm-as-judge, audit-log, nemoclaw, openclaw]
summary: 'Stand up Claw-Eval-Live sandboxed-workflow protocol on Spark via NemoClaw + OpenShell, mock the business-service backends, run Llama 8B vs Nemotron 49B with deterministic-trace + LLM-judge grading, and chart where local agents land vs the paper 66.7 percent ceiling.'
status: upcoming
series: 'Autoresearch'
---

## Source paper

- arXiv: [2604.28139](https://arxiv.org/abs/2604.28139) — Claw-Eval-Live: A Live Agent Benchmark for Evolving Real-World Workflows
- Project page: [claw-eval-live.github.io](https://claw-eval-live.github.io) _(no GitHub repo discoverable at promotion time)_
- Popularity: **25/100** · 22 HF upvotes · 0 citations

## Frontier Scout verdict

**spark-feasible** — 8B agent + lightweight service mocks + sequential sandbox runs sit comfortably below 50 GB, and NemoClaw + OpenShell are exactly the verified primitives this benchmark needs (`nemoclaw-vs-openclaw-dgx-spark`, `autoresearch-agent-loop`); the active blocker is the unreleased dataset, not the hardware envelope.

## Proposed Spark recipe

1. **Wait or proxy** — if the 105-task release isn't out, hand-author 5 representative tasks per family (HR, multi-system business, local workspace repair) using the paper's task structure as a template.
2. **Stand up the sandbox via NemoClaw** — each task gets a fresh OpenShell container with the workspace pre-populated from a fixture tarball. Use the `cat | openshell sandbox exec` workaround (since `openshell sandbox upload` is broken on v0.0.26).
3. **Mock the business services** as Flask/FastAPI processes inside the same network namespace — HR API, ticketing API, file-workspace state. Audit-log every request to a JSONL.
4. **Serve the agent under test via NIM**. Run two side-by-side: `llama-3.1-8b-instruct` and `nemotron-super-49b` (or 70B fp8 if the box has been freshly booted). Tool-call against mocked services + sandbox shell.
5. **Build the grader**: deterministic checks come from audit log + workspace diff (file-state checksums, service-state asserts). Semantic checks via Llama 8B as judge.
6. **Score and compare**: per-task-family pass rates, mirror the paper's "leaderboard rank vs overall completion" finding on the smaller scale, and call out whether local-first models exhibit the same HR / multi-system bottleneck pattern.

Full recipe with stack-map references in [`evidence/spark-recipe.md`](./evidence/spark-recipe.md).

## Open questions for the experiment

- No repo, no dataset URL as of eval time. Article either holds for the release or proxies a hand-authored subset (honest if framed as protocol replication, not benchmark reproduction).
- Service mocking is real engineering — risk of becoming "how I built mocks" rather than "what the agent did." Use the simplest possible mocks (3 endpoints each, single-table SQLite state).
- The 13 models the paper evaluates aren't named in the abstract; local leaderboard will be Spark-stack subset rather than directly comparable.
- Judge contamination risk: agent + judge from same family biases the score. Use different families (Llama agent / Nemotron judge) or rely on deterministic-only checks for the headline number.

## Suggested article shape

- **Stage:** observability
- **Series:** Autoresearch
- **Tags:** agentic, benchmark, sandboxing, evals, llm-as-judge, audit-log, nemoclaw, openclaw
- **Voice:** essay on *why "did the agent do the thing" is harder to grade than "did the agent say the right thing"* — and what verifiable execution traces buy you when the leaderboard model still tops out at 66.7%.
