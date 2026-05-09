---
title: 'A^2TGPO: Agentic Turn-Group Policy Optimization with Adaptive Turn-level Clipping — Spark reproduction notes'
date: 2026-05-08
author: 'Manav Sehgal'
product: 'NeMo'
stage: fine-tuning
difficulty: 'intermediate'
time_required: '~30 min read'
hardware: 'NVIDIA DGX Spark'
tags: ['reinforcement-learning', 'grpo', 'agentic', 'credit-assignment', 'information-gain', 'qwen', 'verl']
summary: 'Reproducing A²TGPO turn-level clipping on Qwen3-4B on a single DGX Spark — local faiss retriever + verl + the three IG primitives, then promoting fieldkit.training.rl to a first-class submodule.'
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

- arXiv: [2605.06200](undefined) — A^2TGPO: Agentic Turn-Group Policy Optimization with Adaptive Turn-level Clipping
- Repo: (none — see eval Blockers section)
- Popularity: 16 · 7 HF upvotes · 0 citations

## Frontier Scout verdict

**spark-feasible** — Qwen3-4B at bf16 with GRPO rollouts + local faiss retriever totals ~30 GB on the 128 GB unified pool, well inside the in-envelope signal "fine-tuning ≤ 70B with LoRA / QLoRA"; the IG forward adds ~30% per-step latency but no additional resident memory.

## Hypothesis (from eval)

Agentic LLM RL typically optimizes against a sparse trajectory-level outcome reward, which makes per-turn credit assignment in multi-turn tool-use loops hard. Information Gain (IG) — the per-turn change in the policy's predicted probability of the ground-truth answer — is an attractive intrinsic process signal but is unstable across turn positions. A²TGPO redesigns how IG is normalized, accumulated, and consumed: (i) **turn-group normalization** compares each turn against peers at the same depth, (ii) **variance-rescaled discounted accumulation** (cumulative IG / √n) keeps advantage magnitudes comparable across turn positions, and (iii) **adaptive turn-level clipping** widens the PPO clipping range for informative turns and narrows it for uninformative ones via `c_{i,t} = 1 + β(2σ(IG_{i,t}) − 1)`. Result: +1.75 on multi-hop QA and +1.69 on single-hop QA over RL baselines. The IG signal forward-pass adds 164 s/step but is largely offset by 86 s of saved generation time.

## Proposed Spark recipe

The repo is at `github.com/CuSO4-Chen/A-TGPO` and uses **verl** for RL. Reproduction path:

1. `git clone --depth 1 https://github.com/CuSO4-Chen/A-TGPO && cd A-TGPO`
2. Two conda envs as the README prescribes — one for the retriever (`pyserini` + `faiss-gpu=1.8.0`), one for training (`torch==2.6.0` + `flash-attn`). The `flash-attn` build needs CUDA 12.4; capability map confirms Spark ships CUDA 12.x in the NeMo / PyTorch containers, so this works inside `nvcr.io/nvidia/pytorch:25.x` (avoid the venv-trap from memory note `feedback_nvidia_container_uv_venv_trap`).
3. Stand up the local retriever: `python rag_server/download.py` then `bash rag_server/launch.sh`. Wiki-18 + e5_Flat fits the Spark NVMe budget (~50 GB).
4. Process datasets: `python data_process/hotpotqa_multihop_train.py` + `python data_process/multihop_test_merge.py` for multi-hop, plus the single-hop pair.
5. Run `bash ATGPO/scripts/ATGPO_multihop_qwen3_4B.sh`. The script's batch sizes will need a halve-or-quarter pass for single-GPU verl (the published 8×H20 schedule won't map 1:1), but the algorithm is the same.
6. Eval on the seven QA datasets the paper uses: HotpotQA, 2WikiMultihopQA, MuSiQue, Bamboogle (multi-hop) + NaturalQuestions, TriviaQA, PopQA (single-hop).

The IG forward + adaptive-clipping logic lives in `verl_atgpo/` and is the actual extractable abstraction — three small overrides on top of verl's GRPO loss.

## Open questions for the experiment

- (none for the algorithm itself — recipe should run as-is at reduced batch)
- `flash-attn` precompiled wheel availability for Blackwell (sm_100) is the only environment-side risk. Falls back to PyTorch SDPA at modest throughput cost if unavailable; capability map's PyTorch container ships an SDPA path that's "in-envelope."
- verl on a single GB10 vs the published 8×H20 means longer wall-clock per epoch (estimated ~6–8× slowdown), not a memory blocker.

## Suggested article shape

- **Would write?** yes
- **Suggested slug:** a2tgpo-turn-clipping-on-spark
- **Suggested stage:** fine-tuning
- **Suggested series:** Machine that Builds Machines
- **Suggested book chapters (MTBM only):** [10]
- **Suggested mtbm_station (MTBM only):** forge
- **Suggested tags:** reinforcement-learning, grpo, agentic, credit-assignment, information-gain, qwen, verl
- **Suggested summary:** Reproducing A²TGPO turn-level clipping on Qwen3-4B on a single DGX Spark — local faiss retriever + verl + the three IG primitives, then promoting fieldkit.training.rl to a first-class submodule.
- **Suggested `fieldkit_modules`:** [capabilities, nim]
