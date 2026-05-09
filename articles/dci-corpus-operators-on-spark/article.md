---
title: 'Beyond Semantic Similarity: Rethinking Retrieval for Agentic Search via Direct Corpus Interaction — Spark reproduction notes'
date: 2026-05-08
author: 'Manav Sehgal'
product: 'NIM'
stage: agentic
difficulty: 'intermediate'
time_required: '~30 min read'
hardware: 'NVIDIA DGX Spark'
tags: ['rag', 'retrieval', 'agentic', 'search', 'ripgrep', 'terminal-tools', 'no-vector']
summary: 'Reproducing DCI-Agent-Lite on a DGX Spark — NIM-served 8B agent + ripgrep + filesystem corpus, no embedder or vector DB; extracts the operator vocabulary as `fieldkit.rag.operators` and quantifies how much of the existing pgvector + reranker stack DCI lets you delete.'
status: upcoming
series: 'Second Brain'
---

## The paper, in one breath (ARTICLE OPENING — required at publish)

> tech-writer: this becomes a `## The paper, in one breath` section in
> the published article, placed immediately after the lede and before
> any "Why this matters for a personal AI builder" substrate framing.
> Pull thesis material from the eval's `## Hypothesis`; fill in the
> achieved beat after the experiment runs.

**Thesis.** _<paraphrase the eval's Hypothesis section in 2–3 sentences, plain language, one concrete mechanism — distinguish from the obvious baseline the technique replaces>_

**Why this technique matters for a personal AI builder.** _<2 sentences on what this unlocks for the reader on a single Spark — distinct from the substrate framing in the next section>_

**Promise vs achieved.** Paper: _<headline number on reference hardware>_. Spark: _<measured number once the experiment runs>_. Delta: _<one sentence on why the gap is what it is>_.

## Source paper

- arXiv: [2605.05242](undefined) — Beyond Semantic Similarity: Rethinking Retrieval for Agentic Search via Direct Corpus Interaction
- Repo: (none — see eval Blockers section)
- Popularity: 15 · 6 HF upvotes · 0 citations

## Frontier Scout verdict

**spark-feasible** — the published config trivially runs against a remote API and the Spark-local config (NIM-served 8B–70B agent + ripgrep + filesystem corpus) is *strictly cheaper* in resident memory than the existing pgvector + reranker RAG stack already documented in the blog; the only adaptation is swapping the agent's LLM endpoint.

## Hypothesis (from eval)

Modern retrieval — lexical or semantic — exposes a corpus through a fixed top-k similarity interface that compresses access into a single retrieval step before reasoning. For agentic tasks (multi-hop QA, deep research, evidence chasing) this is a bottleneck: exact lexical constraints, sparse-clue conjunctions, local-context checks, and plan revision after partial evidence are all hard to express through `retrieve(query, k=10)`. **Direct Corpus Interaction (DCI)** removes the retriever entirely — the agent searches the raw corpus with general-purpose terminal tools (`rg`, `find`, `sed`, file reads, lightweight scripts), composes its own search primitives, and revises plans mid-search. **No embedding model, no vector index, no retrieval API.** With GPT-5.4-nano as the agent, DCI-Agent-Lite hits **62.9 % on BrowseComp-Plus**, beating top baselines powered by GPT-5.2, Claude-Sonnet-4.6, Qwen3.5-122B, and GLM-4.7.

## Proposed Spark recipe

The repo is at `github.com/DCI-Agent/DCI-Agent-Lite` and is uv-managed with a one-click `bash setup.sh`. It builds on **Pi** (`badlogic/pi-mono` coding-agent) with bash tools.

1. `git clone --depth 1 https://github.com/DCI-Agent/DCI-Agent-Lite && cd DCI-Agent-Lite && bash setup.sh`
2. Configure `.env` with at least one of `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` for the published path. **Spark-local path:** point the harness at a NIM endpoint via the OpenAI-compatible API the NIM container exposes — Pi already speaks OpenAI-format, so this is a base-URL swap, no code change.
3. Download the corpus + bench: `uv run python scripts/download_corpus.py` and `uv run python scripts/download_dci_bench.py`. Both come from HF: `DCI-Agent/corpus` and `DCI-Agent/dci-bench`.
4. Install ripgrep (`apt install ripgrep`) — capability map's `stack` block already presumes a Linux userspace; this is a one-line dependency.
5. Run a benchmark: the repo ships scripts for BRIGHT, BEIR, BrowseComp-Plus, and multi-hop QA — total 13 benchmarks. The full suite is hours, not days, on a single Spark with a local NIM.
6. **The extractable abstraction is the operator vocabulary** — `rg` (regex with `-A`/`-B` context), `find` (filename / mtime predicates), `sed` (slice ranges), `cat` (whole-file read), shell pipes for composition. The agent learns to compose these instead of calling `retriever.search(q)`. This is what becomes `fieldkit.rag.operators`.

## Open questions for the experiment

- (none — recipe should run as-is)
- Long-horizon agentic loops accumulate context, but Pi ships explicit context-management for this; the README mentions the `codex/context-management-ablation` branch is the supported path.
- The published headline uses GPT-5.4-nano which is a remote API — quoting Spark-local numbers with a 8B-class NIM is a follow-up study, not a blocker.

## Suggested article shape

- **Would write?** yes
- **Suggested slug:** dci-corpus-operators-on-spark
- **Suggested stage:** agentic
- **Suggested series:** Second Brain
- **Suggested tags:** rag, retrieval, agentic, search, ripgrep, terminal-tools, no-vector
- **Suggested summary:** Reproducing DCI-Agent-Lite on a DGX Spark — NIM-served 8B agent + ripgrep + filesystem corpus, no embedder or vector DB; extracts the operator vocabulary as `fieldkit.rag.operators` and quantifies how much of the existing pgvector + reranker stack DCI lets you delete.
- **Suggested `fieldkit_modules`:** [nim, rag]

(No alignment lens — series is Second Brain, not MTBM.)
