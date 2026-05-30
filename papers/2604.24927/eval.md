> **FIELDKIT FIT (2026-05-02):** retro-annotation; eval predates the v0.1 template.
> - **Would import:** `fieldkit.capabilities` (envelope math for the ~20 GB working point — Qwen 7B + 1 GB Distiller + KV); `fieldkit.eval` (`Bench` for tok/s deltas; `Judge.parse` for the Pass@k correctness extractor).
> - **Would extend:** `fieldkit.eval` — add a `PassAtKBench` (n-sample-per-prompt loop with verifier callback). Trivially generalizes today's single-shot `Bench`.
> - **Would propose for v0.x:** `fieldkit.inference` — vLLM-flavored OpenAI-compat client + cold-start polling, since `fieldkit.nim` codifies NIM-specific behavior (8192 ctx ceiling, container `wait_for_warm`) that doesn't apply to a vLLM fork. Candidate for v0.2 alongside `fieldkit.retriever`. Stretch: `fieldkit.distill` (test-time-training distiller wrapping a shallow→deep MLP probe) for v0.3 — outside the current deferred-modules list.

# Large Language Models Explore by Latent Distilling

## Hypothesis

Standard stochastic decoding produces lexical variation but rarely semantic exploration — the model keeps re-sampling near-duplicate ideas. ESamp adds a **lightweight Distiller** trained at test time to predict the LLM's deep-layer hidden state from its shallow-layer hidden state. When the Distiller's prediction error spikes on a candidate continuation, that's a *novelty signal* — the prefix is moving into territory the LLM hasn't been recently calibrated on — and ESamp uses it to reweight token candidates toward less-explored semantic patterns. The Distiller updates online during decoding via an asynchronous training pipeline, so the runtime overhead is reported as 1.2% optimized / <5% worst case. The headline win is Pass@k efficiency on reasoning benchmarks: the same compute budget reaches a correct answer in fewer samples because the samples are semantically diverse rather than rephrasings of the same wrong attempt.

## Memory budget

The Distiller is the only addition over a standard inference stack. Working from the abstract's "lightweight" framing and standard depth-wise probe sizes:

- **Base reasoning model** (canonical Spark target: Qwen 2.5 7B Instruct or Llama 3.1 8B): 14–16 GB bf16 weights.
- **Distiller (estimated)**: a 2–3 layer MLP mapping shallow hidden → deep hidden, ~4096 → 4096 with one or two intermediate layers. Roughly `2 × 4096 × 4096 × 2 bytes ≈ 67 MB`. Plus an Adam-state copy for online updates: ~200 MB. Round to ≤ 1 GB total including activations.
- **KV cache** at 8192 ctx, bf16, Llama-class: ~4 GB at batch=1.
- **vLLM scheduler + paged attention**: leaves flexible headroom.

Total: ~20 GB. The 128 GB envelope is barely scratched — the bottleneck on Spark for this paper is throughput overhead, not memory.

## Proposed Spark recipe

The repo is `github.com/LinesHogan/tLLM` (33⭐, Python, last push 2026-04-26). Description: *"tLLM is a test-time training extension of vLLM."* That is load-bearing for the recipe — ESamp ships as a vLLM fork, **not** TRT-LLM/NIM. So the canonical NIM serving path doesn't apply directly; we run vLLM standalone.

1. **Clone the repo**: `git clone --depth 1 https://github.com/LinesHogan/tLLM`. Top-level layout is `tllm/` (the package), `starter.py`, `doc/`, `doc_zh/`, `test/`. No requirements.txt in the public listing — read `pyproject.toml` from the package or follow `doc/`.
2. **Install in a fresh container** — vLLM on Blackwell needs CUDA 12.x kernels; use the NeMo / PyTorch container as the base and remember the `/opt/venv` pip-trap from `feedback_nvidia_container_uv_venv_trap` (always `/opt/venv/bin/python3 -m pip install`).
3. **Pick the base model**: Qwen 2.5 7B Instruct (already in the capability map's NIM-supported list — same weights, just served via vLLM here). Reasoning model option: DeepSeek-R1-Distill-Qwen-7B for the Pass@k benchmarks the paper highlights.
4. **Run the baseline**: vanilla vLLM stochastic sampling, n=8 samples, on AIME / MATH / HumanEval / a creative-writing prompt set. Measure Pass@k and tok/s.
5. **Run ESamp**: enable the Distiller via tLLM's starter.py; same n=8 samples; same benchmarks. Measure Pass@k lift, tok/s degradation (paper claims ≤5% worst-case), and semantic diversity (e.g., embed each sample with `nemotron-embed-1b-v2` and measure mean pairwise cosine).
6. **Cross-link**: ties directly to *KV-Cache Arithmetic at Inference* — both are about extracting more from a fixed compute budget. The article frames ESamp as the *exploration* counterpart to KV's *capacity* analysis.

## Blockers

- vLLM is not the project's verified inference path — capability map verifies NIM (TRT-LLM) and Triton, not vLLM. The article either runs vLLM standalone on Spark (works, just not the production path) or ports the Distiller idea to TRT-LLM (a much larger project, out of scope for one article).
- Asynchronous training-during-inference is a non-trivial concurrency story — the 1.2% overhead claim depends on overlapping the Distiller backward pass with the LLM's next forward pass. Need to verify this actually overlaps on a single GB10 (vs. a multi-GPU host where it's easier).
- Reasoning-benchmark Pass@k requires a verifier loop (math correctness, code exec). Doable but adds plumbing — use the existing eval-runner pattern from previous articles.

## Verdict

**spark-feasible** — Qwen/Llama 7–8B + a ~1 GB Distiller fit inside 20 GB of the 128 GB pool, the public tLLM repo gives a working vLLM-based starting point, and the article's natural framing extends the existing *KV-Cache Arithmetic at Inference* deep-dive into test-time exploration.

## Article suggestion

- **Would write?** yes
- **Suggested slug:** test-time-distilling-for-exploration
- **Suggested stage:** inference
- **Suggested series:** LLM Wiki
- **Suggested tags:** decoding, sampling, test-time-scaling, reasoning, distillation, pass-at-k, vllm
- **Suggested summary:** Reproduce ESamp's test-time Distiller on Qwen 2.5 7B with the public tLLM (vLLM-extension) repo on Spark, measure Pass@k lift on AIME and HumanEval, and quantify the 1.2–5% throughput overhead under unified-memory pressure.
