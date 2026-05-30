# Beyond Semantic Similarity: Rethinking Retrieval for Agentic Search via Direct Corpus Interaction

## Hypothesis

Modern retrieval — lexical or semantic — exposes a corpus through a fixed top-k similarity interface that compresses access into a single retrieval step before reasoning. For agentic tasks (multi-hop QA, deep research, evidence chasing) this is a bottleneck: exact lexical constraints, sparse-clue conjunctions, local-context checks, and plan revision after partial evidence are all hard to express through `retrieve(query, k=10)`. **Direct Corpus Interaction (DCI)** removes the retriever entirely — the agent searches the raw corpus with general-purpose terminal tools (`rg`, `find`, `sed`, file reads, lightweight scripts), composes its own search primitives, and revises plans mid-search. **No embedding model, no vector index, no retrieval API.** With GPT-5.4-nano as the agent, DCI-Agent-Lite hits **62.9 % on BrowseComp-Plus**, beating top baselines powered by GPT-5.2, Claude-Sonnet-4.6, Qwen3.5-122B, and GLM-4.7.

## Memory budget

DCI's headline finding is that the corpus side has *zero* model footprint — no embedder, no vector DB, no reranker. Memory is dominated entirely by the agent LLM:

- Published config uses GPT-5.4-nano (remote API) — zero local weight.
- Spark-local config: any NIM-served model ≤ 70B works. `weight_bytes(params_b=8, dtype="bf16")` ≈ 16 GB for Llama-3.1-8B; `weight_bytes(params_b=70, dtype="fp8")` ≈ 70 GB for the upper-bound. KV at long context (deep-research workflows hit 64–128 K tokens often): `kv_cache_bytes(hidden=8192, n_layers=80, ctx=65536, batch=1, dtype="fp8")` ≈ 40 GB at 70B fp8 + 65K ctx.
- Corpus storage: filesystem only. The DCI-Agent corpus on HF (`DCI-Agent/corpus`) is sized for ripgrep, not vector search — Spark NVMe handles this trivially.

**Total Spark working set:** 16–110 GB depending on chosen agent model, all in-envelope. The radical move is what's *not* there: no faiss-gpu allocation, no embedding-model load, no reranker. Compared to the existing Spark RAG stack (`pgvector-on-spark`, `rerank-fusion-retrieval-on-spark`), DCI deletes ~20–40 GB of retrieval infrastructure.

## Proposed Spark recipe

The repo is at `github.com/DCI-Agent/DCI-Agent-Lite` and is uv-managed with a one-click `bash setup.sh`. It builds on **Pi** (`badlogic/pi-mono` coding-agent) with bash tools.

1. `git clone --depth 1 https://github.com/DCI-Agent/DCI-Agent-Lite && cd DCI-Agent-Lite && bash setup.sh`
2. Configure `.env` with at least one of `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` for the published path. **Spark-local path:** point the harness at a NIM endpoint via the OpenAI-compatible API the NIM container exposes — Pi already speaks OpenAI-format, so this is a base-URL swap, no code change.
3. Download the corpus + bench: `uv run python scripts/download_corpus.py` and `uv run python scripts/download_dci_bench.py`. Both come from HF: `DCI-Agent/corpus` and `DCI-Agent/dci-bench`.
4. Install ripgrep (`apt install ripgrep`) — capability map's `stack` block already presumes a Linux userspace; this is a one-line dependency.
5. Run a benchmark: the repo ships scripts for BRIGHT, BEIR, BrowseComp-Plus, and multi-hop QA — total 13 benchmarks. The full suite is hours, not days, on a single Spark with a local NIM.
6. **The extractable abstraction is the operator vocabulary** — `rg` (regex with `-A`/`-B` context), `find` (filename / mtime predicates), `sed` (slice ranges), `cat` (whole-file read), shell pipes for composition. The agent learns to compose these instead of calling `retriever.search(q)`. This is what becomes `fieldkit.rag.operators`.

## Blockers

- (none — recipe should run as-is)
- Long-horizon agentic loops accumulate context, but Pi ships explicit context-management for this; the README mentions the `codex/context-management-ablation` branch is the supported path.
- The published headline uses GPT-5.4-nano which is a remote API — quoting Spark-local numbers with a 8B-class NIM is a follow-up study, not a blocker.

## Verdict

**spark-feasible** — the published config trivially runs against a remote API and the Spark-local config (NIM-served 8B–70B agent + ripgrep + filesystem corpus) is *strictly cheaper* in resident memory than the existing pgvector + reranker RAG stack already documented in the blog; the only adaptation is swapping the agent's LLM endpoint.

## Fieldkit fit

- **Would import:** `fieldkit.nim` (the agent LLM is a NIMClient), `fieldkit.rag` (existing `Pipeline` provides the document/chunk types DCI sidesteps but still needs for the *eval-set* corpus shape).
- **Would extend:** `fieldkit.rag` — add a `fieldkit.rag.operators` submodule with typed wrappers around terminal primitives: `Grep(pattern, context_before, context_after, paths)`, `Find(name_glob, mtime_range, paths)`, `FileRead(path, byte_range | line_range)`, `Sed(slice_expr, path)`, `Compose(*ops)`. Each is a pure function returning `list[Match]` — composable, deterministic, no hidden state. This drops cleanly next to the existing `Pipeline` without modifying it; you'd swap a `Pipeline.search()` call for an `OperatorSet.search()` chain when the corpus is filesystem-resident.
- **Would propose for v0.x:** none — `fieldkit.rag.operators` is the right home; no new top-level module needed. (DCI is the rare paper whose contribution is *deleting* infrastructure, so its abstraction is small.)

## Article suggestion

- **Would write?** yes
- **Suggested slug:** dci-corpus-operators-on-spark
- **Suggested stage:** agentic
- **Suggested series:** Second Brain
- **Suggested tags:** rag, retrieval, agentic, search, ripgrep, terminal-tools, no-vector
- **Suggested summary:** Reproducing DCI-Agent-Lite on a DGX Spark — NIM-served 8B agent + ripgrep + filesystem corpus, no embedder or vector DB; extracts the operator vocabulary as `fieldkit.rag.operators` and quantifies how much of the existing pgvector + reranker stack DCI lets you delete.
- **Suggested `fieldkit_modules`:** [nim, rag]

(No alignment lens — series is Second Brain, not MTBM.)
