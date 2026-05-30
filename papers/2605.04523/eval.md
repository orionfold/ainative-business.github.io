# RaguTeam at SemEval-2026 Task 8: Meno and Friends in a Judge-Orchestrated LLM Ensemble

## Hypothesis

Multi-turn RAG generation has enough heterogeneity in failure mode that *no single model wins consistently*. RaguTeam's claim is operational: a heterogeneous ensemble of seven LLMs with two prompting variants per model (so up to 14 candidate generations per instance) plus a single GPT-4o-mini judge that picks the best candidate beats every member individually — including the strongest open baseline (gpt-oss-120b at 0.6390) by 14+ points conditioned harmonic mean (0.7827, 1st of 26 teams). The reusable contribution is the *judge-orchestrated ensemble* pattern itself, plus **Meno-Lite-0.1** — a 7B domain-adapted model that delivers the strongest cost-performance trade-off in the team. The pattern is directly extractable as a fieldkit primitive: `fieldkit.ensemble` + `fieldkit.judge`.

## Memory budget

The seven members are heterogeneous (Llama, Qwen, GLM-4.5, Gemini variants, Meno-Lite-0.1) — most served via OpenAI-compatible API endpoints (the README hardcodes `OPENAI_URL=https://api.vsegpt.ru/v1`), with **Qwen3-4B-FP8 served locally** via vLLM as the only must-be-resident model.

- Local member: `weight_bytes(params_b=4, dtype="fp8")` ≈ 4 GB. README config: `vllm serve Qwen/Qwen3-4B-FP8 --max_model_len 6000 --gpu_memory_utilization 0.85`.
- KV at ctx=6000, batch=8: `kv_cache_bytes(hidden=2560, n_layers=28, ctx=6000, batch=8, dtype="fp8")` ≈ 3.4 GB.
- Judge (GPT-4o-mini): remote API, no local memory.
- Meno-Lite-0.1 (7B): `weight_bytes(params_b=7, dtype="bf16")` ≈ 14 GB if served locally — comfortably co-resident with the Qwen3-4B endpoint.
- Hosting *all seven* members locally as alternative to API: 7 × ~10 GB avg ≈ 70 GB total weights — still in the 128 GB envelope, but you'd serialize requests via a single vLLM with model swap, not run all seven concurrently.

**Verdict on memory:** trivial in the published config (one local model + API judges); achievable in a fully-local config (≤ 70 GB resident) with model-swap serving.

## Proposed Spark recipe

The repo is at `github.com/RaguTeam/ragu_mtrag_semeval` and is uv-managed. Reproduction path:

1. `git clone --depth 1 https://github.com/RaguTeam/ragu_mtrag_semeval && cd ragu_mtrag_semeval && uv sync --extra eval`
2. Clone the IBM MTRAG benchmark: `git clone https://github.com/IBM/mt-rag-benchmark` and set `MTRAG_DATA` accordingly.
3. **Local member** — replace the README's bare-vLLM call with a NIM-served Qwen3-4B endpoint per "NIM First Inference on DGX Spark" (capability map confirms NIM serves Qwen3 with paged-attention KV economics). NIM provides the OpenAI-compatible API the harness already speaks.
4. **Other six members** — keep the OpenAI-compatible endpoint indirection. Spark-local alternative: stand up a second NIM with Meno-Lite-0.1 (7B); for the rest, you can either hit a hosted API (paper's choice) or model-swap inside vLLM. Capability map's "Long-context inference economics (KV cache, paged attention)" is in-envelope for ≤ 14B models.
5. **Judge** — Replace GPT-4o-mini with a local NIM-served Qwen3-32B (or NeMo Evaluator's judge harness from "RAG Eval — Ragas + NeMo Evaluator" in the blog). Capability map: ≤ 70B inference is in-envelope; 32B fits with margin.
6. Run `python src/generation/main.py` then `scripts/generation/run_generation_task_b.py`. Aggregate metrics: `python scripts/evaluation/metrics_aggregation.py`.
7. Adapt the routing logic in `src/generation/main.py` — that's where the per-instance "two prompting variants × seven models" candidate fan-out happens, and where the judge-selection call is wired.

## Blockers

- (none for memory)
- The seven-model-name list isn't fully enumerated in the abstract or the README excerpt — need to read `src/generation/main.py` to confirm names, but at least three are local-friendly: Qwen3-4B-FP8 (explicit), Meno-Lite-0.1 (HF: `bond005/meno-lite-0.1`), and per the abstract there are GLM-4.5 and Gemini-class members which are API-only.
- The MTRAG benchmark itself is sizable (~few GB) but well within Spark's NVMe budget.

## Verdict

**spark-feasible** — the published config fits trivially (one local 4B model + remote judges), and a fully-local variant (Meno-Lite-0.1 7B + Qwen3-class members + Qwen3-32B judge) keeps the resident set ≤ 70 GB inside the 128 GB envelope; this is the cleanest "judge-orchestrated ensemble at production quality" pattern publicly available.

## Fieldkit fit

- **Would import:** `fieldkit.nim` (each ensemble member becomes a NIMClient with a different model id), `fieldkit.eval` (the MTRAGEval scoring harness becomes a `Bench` subclass).
- **Would extend:** `fieldkit.nim` — add a multi-endpoint client wrapper that fans a single prompt across N NIMClient instances and returns the candidate set with metadata (latency, token count, source model). Trivial generalization of the existing single-client API.
- **Would propose for v0.2:** `fieldkit.ensemble` — first-class types `EnsembleMember` (NIMClient + prompt_variant), `EnsembleClient` (parallel fanout + candidate aggregation), `JudgeOrchestrator` (judge model + selection policy with `argmax | weighted | majority` strategies). Pairs with `fieldkit.eval` — the judge IS an eval pipeline, just one whose output drives selection rather than scoring. This is the single highest-leverage fieldkit abstraction in this batch: the multi-LLM-with-judge pattern shows up in MoA, RaguTeam, ARIS (covered in the prior 2026-05-06 refresh), and almost every multi-agent paper.

## Article suggestion

- **Would write?** yes
- **Suggested slug:** judge-orchestrated-ensemble-on-spark
- **Suggested stage:** inference
- **Suggested series:** LLM Wiki
- **Suggested tags:** rag, ensemble, judge, multi-agent, nim, vllm, qwen, meno-lite
- **Suggested summary:** Reproducing the RaguTeam SemEval-2026 T8 winning system on a DGX Spark — judge-orchestrated 7-LLM ensemble (Qwen3-4B-FP8 + Meno-Lite-0.1 7B local + remote members) with Qwen3-32B judge, then extracting the pattern into `fieldkit.ensemble` + `fieldkit.judge`.
- **Suggested `fieldkit_modules`:** [nim, rag, eval]

(No alignment lens — series is LLM Wiki, not MTBM.)
