> **FIELDKIT FIT (2026-05-02):** retro-annotation; eval predates the v0.1 template.
> - **Would import:** `fieldkit.nim` (the bench reads `OPENAI_API_BASE` — drop in `NIMClient` + `wait_for_warm` for cold-start polling); `fieldkit.eval` (`Bench` for the 3-model NIM leaderboard; `is_refusal` for the search-tool fallback rate).
> - **Would extend:** `fieldkit.eval` — `Trajectory.from_jsonl` covers the autoresearch-loop schema today; the bench's per-task search-tool trace has a different shape, so this article would either land a small parser variant or a `from_jsonl(schema=...)` parameter.
> - **Would propose for v0.x:** none. The agent shell is the upstream AutoResearchBench repo, not a fieldkit responsibility.

# AutoResearchBench: Benchmarking AI Agents on Complex Scientific Literature Discovery

## Hypothesis

Web-browsing agent benchmarks like BrowseComp test general retrieval; AutoResearchBench tests *literature* retrieval — finding a specific paper through multi-step probing (Deep Research) or comprehensively collecting all papers matching a condition (Wide Research). The headline result is brutal: even frontier LLMs that hit high BrowseComp scores top out at **9.39% accuracy on Deep Research and 9.31% IoU on Wide Research**, with most baselines under 5%. The paper's bet is that *literature* search asks for a different bundle of skills than general browsing — fine-grained scientific concept comprehension, cross-paper reasoning over citations, and open-ended termination judgment about when "enough" papers have been collected.

## Memory budget

This is a pure-inference benchmark — agent under test, no training involved. The Spark cost is whatever model is being evaluated:

- **Llama 3.1 8B bf16 via NIM**: 16 GB weights + ~4 GB KV at 8192 ctx ≈ 20 GB. Trivial.
- **Llama 3.3 70B fp8 via NIM**: 70 GB weights + ~8–12 GB KV (longer ctx for tool traces) ≈ 82 GB. Tight but in-envelope per the capabilities map.
- **Nemotron Super 49B**: ~50 GB bf16. Comfortable.
- **Embedding side** (for any local retrieval the agent does): nemotron-embed-1b-v2 + nemotron-reranker-1b add ~3 GB combined.

Realistic Spark setup: 70B fp8 + retriever stack ≈ 90 GB peak, leaves ~35 GB for OS + Postgres + the agent's Python process pool. Inside envelope but no room for a second concurrent model — kill any Ollama before starting (per `feedback_stop_unneeded_services`).

## Proposed Spark recipe

The repo `github.com/CherYou/AutoResearchBench` (29⭐, Apache-2.0, Python+Shell) is mature and the benchmark dataset is on Hugging Face at `Lk123/AutoResearchBench`. Crucially, the inference entrypoint reads `OPENAI_API_KEY` and `OPENAI_API_BASE` from `.env` — the agent talks to its model via an OpenAI-compatible chat endpoint, which **NIM exposes natively**. Drop-in.

1. **Clone + install**: `git clone --depth 1 https://github.com/CherYou/AutoResearchBench && cd AutoResearchBench && /opt/venv/bin/python3 -m pip install -r requirements.txt`.
2. **Start NIM with Llama 3.3 70B fp8** (or a smaller in-envelope model first for plumbing). Note the OpenAI-compatible base URL, e.g. `http://localhost:8000/v1`.
3. **Configure `.env`**:
   ```
   MODEL=meta/llama-3.3-70b-instruct
   OPENAI_API_KEY=local
   OPENAI_API_BASE=http://localhost:8000/v1
   INPUT_FILE=input_data/academic_deepsearch_example.jsonl
   ```
4. **Download + decrypt the bench bundle** from HF (the README documents `decrypt_benchmark.py` against an `.obf.json` released bundle).
5. **Run inference**: `bash run_inference.sh`. The agent uses two ship-with-the-repo tools — `tool_deepxivsearch.py` (academic search) and `tool_websearch.py` (general web) — both of which need internet egress and likely an API key for the academic backend.
6. **Run evaluation**:
   ```bash
   bash evaluate/run_evaluate.sh deep --input-file output_data/inference_output.jsonl
   bash evaluate/run_evaluate.sh wide --input-file output_data/inference_output.jsonl --gt-file path/to/gt.jsonl
   ```
7. **Comparative table**: run the same bench against `llama-3.1-8b-instruct` (NIM), `nemotron-super-49b` (NIM), and Nemotron via NemoClaw to land a Spark-stack-internal leaderboard. Tie back to the Autoresearch arc — this *is* the eval harness for the autonomous research loop the blog is building.

## Blockers

- **Live search dependency**: DeepXiv + web search tools need internet and likely API keys. Article must call out the keys + cost; "fully offline reproduction" is not the play.
- **Headline accuracy is low for everyone** (~9% Deep, ~9% Wide). Local Spark models will likely be lower still — the article should be framed as "where are we on the absolute scale" not "we beat the state of the art."
- **Bundle decryption** — the released benchmark is obfuscated and gated through `decrypt_benchmark.py`. If the decrypt key flow requires an extra step (license accept, etc.) that's a soft blocker but solvable.
- **Ground-truth file** for Wide eval is required and may need separate fetching.

## Verdict

**spark-feasible** — pure inference, NIM exposes the OpenAI-compatible endpoint the bench expects, the 29⭐ Apache-2.0 repo + HF dataset are real and pushable, and the largest in-envelope NIM model (70B fp8) leaves enough room for the retriever stack; only blocker is internet-egress for the search tools.

## Article suggestion

- **Would write?** yes
- **Suggested slug:** autoresearchbench-on-spark
- **Suggested stage:** observability
- **Suggested series:** Autoresearch
- **Suggested tags:** agentic, benchmark, rag, retrieval, literature-search, nim, evaluation
- **Suggested summary:** Run AutoResearchBench's Deep + Wide literature-discovery tasks against three NIM-hosted Spark models (Llama 8B, Nemotron Super 49B, Llama 70B fp8) and chart where local-first agents land on a benchmark where even frontier LLMs sit under 10%.
