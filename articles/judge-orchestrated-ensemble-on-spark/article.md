---
title: 'RaguTeam at SemEval-2026 Task 8: Meno and Friends in a Judge-Orchestrated LLM Ensemble for Faithful Multi-Turn Response Generation — Spark reproduction notes'
date: 2026-05-08
author: 'Manav Sehgal'
product: 'NIM'
stage: inference
difficulty: 'intermediate'
time_required: '~30 min read'
hardware: 'NVIDIA DGX Spark'
tags: ['rag', 'ensemble', 'judge', 'multi-agent', 'nim', 'vllm', 'qwen', 'meno-lite']
summary: 'Reproducing the RaguTeam SemEval-2026 T8 winning system on a DGX Spark — judge-orchestrated 7-LLM ensemble (Qwen3-4B-FP8 + Meno-Lite-0.1 7B local + remote members) with Qwen3-32B judge, then extracting the pattern into `fieldkit.ensemble` + `fieldkit.judge`.'
status: upcoming
series: 'LLM Wiki'
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

- arXiv: [2605.04523](undefined) — RaguTeam at SemEval-2026 Task 8: Meno and Friends in a Judge-Orchestrated LLM Ensemble for Faithful Multi-Turn Response Generation
- Repo: [https://github.com/RaguTeam/ragu_mtrag_semeval](https://github.com/RaguTeam/ragu_mtrag_semeval) (1★, last commit 2026-05-04)
- Popularity: 28 · 27 HF upvotes · not yet indexed

## Frontier Scout verdict

**spark-feasible** — the published config fits trivially (one local 4B model + remote judges), and a fully-local variant (Meno-Lite-0.1 7B + Qwen3-class members + Qwen3-32B judge) keeps the resident set ≤ 70 GB inside the 128 GB envelope; this is the cleanest "judge-orchestrated ensemble at production quality" pattern publicly available.

## Hypothesis (from eval)

Multi-turn RAG generation has enough heterogeneity in failure mode that *no single model wins consistently*. RaguTeam's claim is operational: a heterogeneous ensemble of seven LLMs with two prompting variants per model (so up to 14 candidate generations per instance) plus a single GPT-4o-mini judge that picks the best candidate beats every member individually — including the strongest open baseline (gpt-oss-120b at 0.6390) by 14+ points conditioned harmonic mean (0.7827, 1st of 26 teams). The reusable contribution is the *judge-orchestrated ensemble* pattern itself, plus **Meno-Lite-0.1** — a 7B domain-adapted model that delivers the strongest cost-performance trade-off in the team. The pattern is directly extractable as a fieldkit primitive: `fieldkit.ensemble` + `fieldkit.judge`.

## Proposed Spark recipe

The repo is at `github.com/RaguTeam/ragu_mtrag_semeval` and is uv-managed. Reproduction path:

1. `git clone --depth 1 https://github.com/RaguTeam/ragu_mtrag_semeval && cd ragu_mtrag_semeval && uv sync --extra eval`
2. Clone the IBM MTRAG benchmark: `git clone https://github.com/IBM/mt-rag-benchmark` and set `MTRAG_DATA` accordingly.
3. **Local member** — replace the README's bare-vLLM call with a NIM-served Qwen3-4B endpoint per "NIM First Inference on DGX Spark" (capability map confirms NIM serves Qwen3 with paged-attention KV economics). NIM provides the OpenAI-compatible API the harness already speaks.
4. **Other six members** — keep the OpenAI-compatible endpoint indirection. Spark-local alternative: stand up a second NIM with Meno-Lite-0.1 (7B); for the rest, you can either hit a hosted API (paper's choice) or model-swap inside vLLM. Capability map's "Long-context inference economics (KV cache, paged attention)" is in-envelope for ≤ 14B models.
5. **Judge** — Replace GPT-4o-mini with a local NIM-served Qwen3-32B (or NeMo Evaluator's judge harness from "RAG Eval — Ragas + NeMo Evaluator" in the blog). Capability map: ≤ 70B inference is in-envelope; 32B fits with margin.
6. Run `python src/generation/main.py` then `scripts/generation/run_generation_task_b.py`. Aggregate metrics: `python scripts/evaluation/metrics_aggregation.py`.
7. Adapt the routing logic in `src/generation/main.py` — that's where the per-instance "two prompting variants × seven models" candidate fan-out happens, and where the judge-selection call is wired.

## Open questions for the experiment

- (none for memory)
- The seven-model-name list isn't fully enumerated in the abstract or the README excerpt — need to read `src/generation/main.py` to confirm names, but at least three are local-friendly: Qwen3-4B-FP8 (explicit), Meno-Lite-0.1 (HF: `bond005/meno-lite-0.1`), and per the abstract there are GLM-4.5 and Gemini-class members which are API-only.
- The MTRAG benchmark itself is sizable (~few GB) but well within Spark's NVMe budget.

## Suggested article shape

- **Would write?** yes
- **Suggested slug:** judge-orchestrated-ensemble-on-spark
- **Suggested stage:** inference
- **Suggested series:** LLM Wiki
- **Suggested tags:** rag, ensemble, judge, multi-agent, nim, vllm, qwen, meno-lite
- **Suggested summary:** Reproducing the RaguTeam SemEval-2026 T8 winning system on a DGX Spark — judge-orchestrated 7-LLM ensemble (Qwen3-4B-FP8 + Meno-Lite-0.1 7B local + remote members) with Qwen3-32B judge, then extracting the pattern into `fieldkit.ensemble` + `fieldkit.judge`.
- **Suggested `fieldkit_modules`:** [nim, rag, eval]

(No alignment lens — series is LLM Wiki, not MTBM.)
