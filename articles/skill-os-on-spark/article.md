---
title: 'SkillOS: Learning Skill Curation for Self-Evolving Agents — Spark reproduction notes'
date: 2026-05-08
author: 'Manav Sehgal'
product: 'NemoClaw'
stage: agentic
difficulty: 'intermediate'
time_required: '~30 min read'
hardware: 'NVIDIA DGX Spark'
tags: ['agentic', 'skills', 'reinforcement-learning', 'grpo', 'self-improvement', 'lora', 'bm25']
summary: 'Reproducing the SkillOS curator/executor split on a DGX Spark — both Qwen3-8B (frozen executor + LoRA-trained curator) over a markdown SkillRepo with BM25 retrieval, then extracting the pattern into `fieldkit.skills`.'
status: upcoming
series: 'Machine that Builds Machines'
book_chapters: [10]
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

- arXiv: [2605.06614](https://arxiv.org/abs/2605.06614) — SkillOS: Learning Skill Curation for Self-Evolving Agents
- Repo: (none — see eval Blockers section)
- Popularity: 15 · 6 HF upvotes · not yet indexed

## Frontier Scout verdict

**spark-feasible** — both Qwen3-8B models fit co-resident in unified memory with comfortable headroom for LoRA GRPO; the only real adaptation is wall-clock (single GB10 vs 16×H100), not memory budget.

## Hypothesis (from eval)

LLM agents that handle streaming tasks tend to remain one-off problem solvers because the *skill curator* — the policy that decides what to add, update, or delete in an external SkillRepo — has historically been hand-rolled or heuristic. SkillOS pairs a *frozen executor* (an LLM that retrieves and applies skills) with a *trainable curator* (an LLM whose actions are `insert_skill | update_skill | delete_skill` over a markdown skill library), and trains the curator end-to-end with GRPO under a composite reward (task outcome, function-call validity, content quality, compression). The split lets the executor stay frozen while the agent's *memory* gets better over time. The reusable contribution is the curator/executor decoupling and the markdown-file-based SkillRepo schema — both directly extractable as fieldkit primitives.

## Proposed Spark recipe

No public code release found in the paper or trivial GitHub search — this is the dominant blocker (see below). Plausible Spark reconstruction once code lands (or as a from-scratch build):

1. Pull Qwen3-8B from NGC or HF: `huggingface-cli download Qwen/Qwen3-8B-Instruct`.
2. Stand up the executor as a NIM endpoint — capability map confirms NIM serves Qwen3-class models with paged-attention KV economics (see "NIM First Inference on DGX Spark" in the blog).
3. Build the SkillRepo as a flat directory of markdown files: `skills/<skill_name>.md` with YAML frontmatter (`name`, `usage`) + body (workflow, constraints). Retrieval: BM25 over the YAML+body via `rank_bm25` (no embedding model needed — directly mirrors the paper's choice and aligns with DCI-style "no vector index" thinking).
4. Wire the curator policy as a separate Qwen3-8B with a small action head emitting one of `insert_skill | update_skill | delete_skill` + the target file path; train with `verl` (paper's framework) or NeMo-Aligner GRPO. Capability map says fine-tuning ≤ 70B with LoRA is in-envelope; do LoRA on the curator.
5. Composite reward: task_outcome (judge model = Qwen3-32B served on a second NIM, or use the local NeMo Evaluator pattern from "RAG Eval — Ragas + NeMo Evaluator" in the blog) + λf · validity + λu · content_quality + λc · compression. Weights from the paper: λf=1.0, λu=0.1, λc=0.05.
6. Eval on **ALFWorld** subsets (Pick=35, Look=13, Clean=27, Heat=16, Cool=25, Pick2=24 — small enough to run in a few hours on Spark) before scaling to WebShop or DeepMath-103k.

## Open questions for the experiment

- **No public code as of 2026-05-08** — the dominant blocker. Reproduction is a from-scratch reimplementation of the curator/executor split, which is a multi-week effort, not a weekend.
- BM25 over markdown is fine, but the paper doesn't publicly release initial skill seeds; you'd need to bootstrap the SkillRepo from logged executor traces, which adds a "trajectory→skill" extraction step the paper glosses.
- The 16-GPU verl training schedule is the published path; getting GRPO to converge on a single Spark requires reduced batch size and longer wall-clock — convergence isn't guaranteed to match published deltas, but the *architectural pattern* is what's reproducible.

## Suggested article shape

- **Would write?** yes
- **Suggested slug:** skill-os-on-spark
- **Suggested stage:** agentic
- **Suggested series:** Machine that Builds Machines
- **Suggested book chapters (MTBM only):** [10]
- **Suggested mtbm_station (MTBM only):** forge
- **Suggested tags:** agentic, skills, reinforcement-learning, grpo, self-improvement, lora, bm25
- **Suggested summary:** Reproducing the SkillOS curator/executor split on a DGX Spark — both Qwen3-8B (frozen executor + LoRA-trained curator) over a markdown SkillRepo with BM25 retrieval, then extracting the pattern into `fieldkit.skills`.
- **Suggested `fieldkit_modules`:** [nim, rag, eval]
