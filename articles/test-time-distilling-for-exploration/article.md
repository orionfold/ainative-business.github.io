---
title: 'ESamp Test-Time Distilling — Spark reproduction notes'
date: 2026-05-02
author: 'Manav Sehgal'
product: 'TRT-LLM'
stage: inference
difficulty: 'intermediate'
time_required: '~30 min read'
hardware: 'NVIDIA DGX Spark'
tags: [decoding, sampling, test-time-scaling, reasoning, distillation, pass-at-k, vllm]
summary: 'Reproduce ESamp test-time Distiller on Qwen 2.5 7B with the public tLLM (vLLM-extension) repo on Spark, measure Pass@k lift on AIME and HumanEval, and quantify the 1.2 to 5 percent throughput overhead under unified-memory pressure.'
status: upcoming
series: 'LLM Wiki'
---

## Source paper

- arXiv: [2604.24927](https://arxiv.org/abs/2604.24927) — Large Language Models Explore by Latent Distilling
- Repo: [LinesHogan/tLLM](https://github.com/LinesHogan/tLLM) (33⭐, last push 2026-04-26) — _"tLLM is a test-time training extension of vLLM"_
- Popularity: **31/100** · 59 HF upvotes · 0 citations

## Frontier Scout verdict

**spark-feasible** — Qwen/Llama 7–8B + a ~1 GB Distiller fit inside 20 GB of the 128 GB pool, the public tLLM repo gives a working vLLM-based starting point, and the article's natural framing extends the existing *KV-Cache Arithmetic at Inference* deep-dive into test-time exploration.

## Proposed Spark recipe

1. **Clone the repo**: `git clone --depth 1 https://github.com/LinesHogan/tLLM`. Already snapshotted at `evidence/repo-snapshot/`. Top-level layout is `tllm/` (the package), `starter.py`, `doc/`, `doc_zh/`, `test/`.
2. **Install in a fresh container** — vLLM on Blackwell needs CUDA 12.x kernels; use NeMo / PyTorch container as base and remember the `/opt/venv` pip-trap (always `/opt/venv/bin/python3 -m pip install`).
3. **Pick the base model**: Qwen 2.5 7B Instruct (already in NIM-supported list — same weights, just served via vLLM here). Reasoning option: DeepSeek-R1-Distill-Qwen-7B for Pass@k benchmarks.
4. **Run the baseline**: vanilla vLLM stochastic sampling, n=8 samples, on AIME / MATH / HumanEval / a creative-writing prompt set. Measure Pass@k and tok/s.
5. **Run ESamp**: enable the Distiller via tLLM's starter.py; same n=8 samples; same benchmarks. Measure Pass@k lift, tok/s degradation (paper claims ≤5% worst-case), and semantic diversity.
6. **Cross-link**: ties directly to *KV-Cache Arithmetic at Inference* — both are about extracting more from a fixed compute budget. The article frames ESamp as the *exploration* counterpart to KV's *capacity* analysis.

Full recipe with stack-map references in [`evidence/spark-recipe.md`](./evidence/spark-recipe.md).

## Open questions for the experiment

- vLLM is not the project's verified inference path — capability map verifies NIM (TRT-LLM) and Triton, not vLLM. Article runs vLLM standalone (works, just not the production path).
- Asynchronous training-during-inference is a non-trivial concurrency story — the 1.2% overhead claim depends on overlapping the Distiller backward pass with the LLM's next forward pass. Verify on single GB10.
- Reasoning-benchmark Pass@k requires a verifier loop (math correctness, code exec). Reuse the existing eval-runner pattern from previous articles.

## Suggested article shape

- **Stage:** inference
- **Series:** LLM Wiki
- **Tags:** decoding, sampling, test-time-scaling, reasoning, distillation, pass-at-k, vllm
- **Voice:** essay on *the difference between lexical variation and semantic exploration* — and what a tiny online-trained probe network can buy you when the same compute budget needs to land somewhere new.
