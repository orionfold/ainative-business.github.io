---
title: "AutoResearchBench on Spark — Two NIMs, One Bench, Two Failure Modes"
date: 2026-05-02
author: Manav Sehgal
product: NIM
stage: observability
also_stages: [agentic, inference]
difficulty: intermediate
time_required: "~3 hours — 30 min plumbing, ~20 min for the runs themselves, the rest is reading what they show"
hardware: "NVIDIA DGX Spark"
tags: [agentic, benchmark, retrieval, literature-search, nim, evaluation, autoresearch]
summary: "Two Spark-tuned NIMs run AutoResearchBench's three Deep-Research example questions. Llama-3.1-8B crashes by turn 5-6 on its 8K context; Nemotron-Nano-9B-v2 finishes cleanly at 128K. Both score 0% Accuracy@1 — for completely different reasons."
signature: AutoresearchbenchCeiling
series: Frontier Scout
fieldkit_modules: [nim, eval, capabilities]
---

The headline number on this bench is harsh by design. [AutoResearchBench's paper](https://arxiv.org/abs/2604.25256) reports **9.39% Accuracy@1** on Deep Research and 9.31% IoU on Wide Research for the strongest frontier-LLM agents in the field. Most baselines sit under 5%. The dataset is a set of obfuscated probing questions whose ground-truth answers are specific arxiv papers; the agent gets a tool that searches the web (or, in the paper's strongest configuration, an academic-paper-specialized retrieval API called **DeepXiv**), reads back the top-k results, and either cites the right paper or concedes. Even with frontier models, the floor is brutal.

## The paper, in one breath

**Thesis.** AutoResearchBench's bet is that *literature retrieval is not general browsing*. Web-browsing benchmarks like BrowseComp test whether an agent can navigate the open web; AutoResearchBench tests whether an agent can find a specific scientific paper through multi-step probing (Deep Research) or comprehensively collect all papers matching a condition (Wide Research). That asks for a different bundle of skills — fine-grained scientific concept comprehension, cross-paper reasoning over citations, and open-ended judgment about when "enough" papers have been collected. The brutal headline (9.39% Acc@1, 9.31% IoU even for frontier LLMs that ace BrowseComp) is the paper's evidence that the bundle is genuinely missing today.

**Why this benchmark matters for a personal AI builder.** AutoResearchBench *is* the eval harness for any local autonomous-research loop a Spark builder is building — second-brain Q&A, daily literature digests, citation walks. The bench's design pattern — obfuscated probes whose ground truth is a specific paper — is itself transferable to any retrieval-bound agent, not just a number to chase. A loop that scores 0% here is a loop that will not reliably find the paper you actually want.

**Promise vs achieved.** Paper: **9.39% Acc@1** on Deep Research, **9.31% IoU** on Wide Research — both with the DeepXiv academic retriever, with most baselines under 5%. Spark, this article: **0/3** on the Deep-Research example set across two Spark-tuned NIMs (Llama-3.1-8B and Nemotron-Nano-9B-v2), using generic Serper + Jina web search instead of DeepXiv. The two zeros are not the same zero — one is a model–bench fit bug (8K context wall, crashed mid-loop), the other is the *correct* read of a thin retrieval signal at 128K context. The model upgrade removes the model-side bottleneck cleanly; retrieval is the next bottleneck, exactly where the paper's DeepXiv design predicts it would be.

That's the bench. Run it on a DGX Spark with two NIMs that ship with native GB10 engine profiles — one with 8K context, one with 128K — and the same three example Deep-Research questions hand back **0/3** in both cases. Same destination on the scoreboard, two completely different journeys to get there.

| measurement | Llama 3.1 8B (Spark NIM) | Nemotron-Nano-9B-v2 (Spark NIM) |
|---|---:|---:|
| `max_model_len` | **8,192** | **131,072** |
| inference engine | vLLM bf16 | vLLM nvfp4 (modelopt FP4) |
| status_counts | 2× context-overflow, 1× finished | 3× finished |
| wall_seconds (mean / range) | 253s / [115, 386] | 363s / [328, 433] |
| turns (mean / range) | 4.0 / [1, 6] | 2.3 / [2, 3] |
| **`final_candidates`** mean | **0** | **0** |
| Accuracy@1 (upstream `evaluate_deep_search.py`) | **0.00%** | **0.00%** |
| failure mode | crashed mid-loop on 8K ctx wall | judged "no candidate matches" |

The interesting line is the last one. A casual read of the table sees two zeros and shrugs; the work is in unpacking why one zero is a bug in the model–bench fit and the other is a correct read of a thin retrieval signal.

## Why this matters for a personal AI builder

Three reasons this run, on this box, on these two NIMs, beats the abstract version.

**Locality.** The paper's published numbers run against frontier-tier models behind cloud APIs and against a paid academic-search backend. Replicating *any* of it locally is the kind of thing the DGX Spark exists to make affordable — both NIMs in this article install with `docker run`, expose an OpenAI-compatible endpoint at `localhost:8000/v1`, and cost zero per token, zero per question, zero in egress. The whole bench run plus its LLM-as-judge evaluator passes nothing over the LAN beyond what the agent's *web tool* needs.

**The honest read.** The frontier ~9% headline is a *retrieval-assisted* number — DeepXiv routes the agent at academic papers, not at arbitrary web pages. Substituting generic Serper + Jina web search (which is what we have without DeepXiv API access) **lowers the ceiling for everyone**, frontier or local. So the question this article actually answers is not *"can a 9B Spark NIM beat 70B in the cloud on this bench?"* — it's *"on the substrate I can actually run on my desk, does the model upgrade help, and how do I read the result?"* The answer turns out to be: yes, it removes the model-side bottleneck cleanly, but a different bottleneck — retrieval — takes over.

**The catalog gap.** The original plan was to run NIM Llama-3.1-8B against **NIM Nemotron-Super-49B** (the big reasoning-tier Llama-3.3 derivative) for a stronger comparison. The 49B's image is in the catalog and pulled to the box (`nvcr.io/nim/nvidia/llama-3.3-nemotron-super-49b-v1:latest`, 23.4 GB on disk), but its `list-model-profiles` output ships TensorRT-LLM engines for L40s, H100, H200, B200, A100, A100-SXM4 — and **nothing for GB10**. A NIM with no compatible profile errors out at startup with `Detected 0 compatible profile(s)`. NVIDIA distributes Spark-tuned NIMs as a curated set; not every published NIM is a member. That curation is itself worth knowing about — and it's the half-step that pushed this article from a 49B comparison to the 9B-v2 comparison it actually is.

## Where this sits in the stack

AutoResearchBench is an *agent* benchmark — the model under test isn't asked a question and graded on its answer. It's asked to *plan, call tools, read results, judge candidates, and decide*. That makes the inference loop look very different from a single-shot Q&A: each turn appends a few thousand tokens of search results to the conversation, and the agent's reasoning chain grows with each pass.

<figure class="fn-diagram" aria-label="The AutoResearchBench loop has three components and one ceiling. The agent planner (a NIM Llama-3.1-8B or Nemotron-Nano-9B-v2 endpoint at localhost:8000/v1) emits a search query, the tool layer (Qwen-Agent's WebSearchTool wrapping Serper plus Jina) returns the top-10 web results plus a per-result summary, and the candidate evaluator picks at most one final candidate per pass. The retrieval ceiling is the structural limit: if the truth paper is not among the top-10 web results, no model — frontier or local — can name it. The two failure modes overlay this same pipeline. The 8K-context Llama-8B path crashes inside the agent planner box once accumulated tool responses pass 8K tokens, typically by turn 5 to 6. The 128K-context Nemotron-Nano-9B-v2 path completes the loop, reaches the candidate evaluator with the full top-10 in scope, and correctly judges no candidate matches — the failure has moved one box to the left.">
  <svg viewBox="0 0 900 440" role="img" aria-label="AutoResearchBench loop diagram. Three boxes left-to-right: agent planner, tool layer (Serper + Jina + summarizer), candidate evaluator. The retrieval ceiling box brackets the tool layer as the structural bound. The 8B path crashes inside the agent planner; the 9B-v2 path completes through to the evaluator and judges no match." preserveAspectRatio="xMidYMid meet">
    <defs>
      <linearGradient id="arb-accent-grad" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%"   stop-color="var(--color-primary)" stop-opacity="0.30"/>
        <stop offset="100%" stop-color="var(--color-primary)" stop-opacity="0.08"/>
      </linearGradient>
      <radialGradient id="arb-tool-halo" cx="0.5" cy="0.5" r="0.65">
        <stop offset="0%"   stop-color="var(--color-primary)" stop-opacity="0.12"/>
        <stop offset="100%" stop-color="var(--color-primary)" stop-opacity="0"/>
      </radialGradient>
      <linearGradient id="arb-8b-band" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%"   stop-color="var(--svg-accent-red)" stop-opacity="0.10"/>
        <stop offset="100%" stop-color="var(--svg-accent-red)" stop-opacity="0.02"/>
      </linearGradient>
      <linearGradient id="arb-9b-band" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%"   stop-color="var(--svg-accent-green)" stop-opacity="0.10"/>
        <stop offset="100%" stop-color="var(--svg-accent-green)" stop-opacity="0.02"/>
      </linearGradient>
    </defs>
    <rect x="20" y="40" width="860" height="160" rx="10" fill="url(#arb-8b-band)" stroke="none"/>
    <rect x="20" y="240" width="860" height="160" rx="10" fill="url(#arb-9b-band)" stroke="none"/>
    <rect x="320" y="20" width="280" height="400" rx="8" fill="url(#arb-tool-halo)" stroke="none"/>
    <rect x="320" y="20" width="280" height="400" rx="8" fill="none"
          stroke="var(--color-text-muted)" stroke-width="0.5" stroke-dasharray="3 3"/>
    <g class="fn-diagram__edges">
      <path class="fn-diagram__edge" pathLength="100" d="M 220 120 L 320 120" />
      <path class="fn-diagram__edge fn-diagram__edge--accent" pathLength="100" d="M 600 120 L 700 120" />
      <path class="fn-diagram__edge" pathLength="100" d="M 220 320 L 320 320" />
      <path class="fn-diagram__edge fn-diagram__edge--accent" pathLength="100" d="M 600 320 L 700 320" />
    </g>
    <g class="fn-diagram__nodes">
      <rect class="fn-diagram__node" x="60" y="80" width="160" height="80" rx="8" />
      <rect class="fn-diagram__node fn-diagram__node--accent" x="320" y="80" width="280" height="80" rx="10" style="fill: url(#arb-accent-grad)" />
      <rect class="fn-diagram__node" x="700" y="80" width="160" height="80" rx="8" />
      <rect class="fn-diagram__node" x="60" y="280" width="160" height="80" rx="8" />
      <rect class="fn-diagram__node fn-diagram__node--accent" x="320" y="280" width="280" height="80" rx="10" style="fill: url(#arb-accent-grad)" />
      <rect class="fn-diagram__node" x="700" y="280" width="160" height="80" rx="8" />
    </g>
    <g class="fn-diagram__labels">
      <text class="fn-diagram__label fn-diagram__label--muted" x="75" y="104" text-anchor="start">AGENT PLANNER (8B)</text>
      <text class="fn-diagram__label fn-diagram__label--display" x="75" y="126" text-anchor="start">localhost:8000/v1</text>
      <text class="fn-diagram__label fn-diagram__label--mono fn-diagram__label--muted" x="75" y="144" text-anchor="start">max_model_len=8192</text>
      <text class="fn-diagram__label fn-diagram__label--accent" x="335" y="104" text-anchor="start">TOOL LAYER · RETRIEVAL CEILING</text>
      <text class="fn-diagram__label fn-diagram__label--display" x="335" y="126" text-anchor="start">Serper + Jina · top-10 + summary</text>
      <text class="fn-diagram__label fn-diagram__label--mono fn-diagram__label--muted" x="335" y="144" text-anchor="start">truth not in top-10 → ceiling = 0</text>
      <text class="fn-diagram__label fn-diagram__label--muted" x="715" y="104" text-anchor="start">EVALUATOR</text>
      <text class="fn-diagram__label fn-diagram__label--display" x="715" y="126" text-anchor="start">candidates: 0</text>
      <text class="fn-diagram__label fn-diagram__label--mono fn-diagram__label--muted" x="715" y="144" text-anchor="start">crashed before reaching</text>
      <text class="fn-diagram__label fn-diagram__label--muted" x="75" y="304" text-anchor="start">AGENT PLANNER (9B-v2)</text>
      <text class="fn-diagram__label fn-diagram__label--display" x="75" y="326" text-anchor="start">localhost:8000/v1</text>
      <text class="fn-diagram__label fn-diagram__label--mono fn-diagram__label--muted" x="75" y="344" text-anchor="start">max_model_len=131072</text>
      <text class="fn-diagram__label fn-diagram__label--accent" x="335" y="304" text-anchor="start">TOOL LAYER · SAME RETRIEVAL</text>
      <text class="fn-diagram__label fn-diagram__label--display" x="335" y="326" text-anchor="start">Serper + Jina · top-10 + summary</text>
      <text class="fn-diagram__label fn-diagram__label--mono fn-diagram__label--muted" x="335" y="344" text-anchor="start">retrieval not improved by 9B</text>
      <text class="fn-diagram__label fn-diagram__label--muted" x="715" y="304" text-anchor="start">EVALUATOR</text>
      <text class="fn-diagram__label fn-diagram__label--display" x="715" y="326" text-anchor="start">candidates: None</text>
      <text class="fn-diagram__label fn-diagram__label--mono fn-diagram__label--muted" x="715" y="344" text-anchor="start">correctly judged: no match</text>
    </g>
    <g class="fn-diagram__annotations">
      <text class="fn-diagram__annotation" x="140" y="200" text-anchor="middle">crash · turn 5–6 · ctx&gt;8K</text>
      <text class="fn-diagram__annotation" x="780" y="400" text-anchor="middle">retrieval ceiling, not model ceiling</text>
    </g>
  </svg>
  <figcaption>Both NIMs share the tool layer; the difference is whether the agent planner survives long enough to reach the evaluator. The 8B's failure is in the planner; the 9B-v2's failure is in the retrieval that bounds every model's ceiling on this bench.</figcaption>
</figure>

The bench's `inference.py` reads a single `OPENAI_API_BASE` from `.env` — that's the only line that needs to change between the two runs. The summarizer that re-reads each web result also points at the same Spark NIM (the bench's `WEB_SEARCH_OPENAI_API_BASE` slot accepts any OpenAI-compatible endpoint). So the agent, its tool's summarizer, and the LLM-as-judge that scores the final candidates all run on the same `localhost:8000/v1` — three slots in the .env, one Spark NIM behind all of them.

## The journey — two NIMs, two runs, three questions each

The published Spark NIM for the comparison is `nvcr.io/nim/nvidia/nvidia-nemotron-nano-9b-v2-dgx-spark` — found by searching NVIDIA's catalog after the 49B image refused to start. It's a hybrid Mamba/Transformer architecture (`NemotronHForCausalLM`) at 9B parameters, served via NVIDIA's vLLM fork with an NVFP4 quantization profile (`vllm-nvfp4-tp1-pp1`). The Spark profile is the one with `nim_workspace_hash_v1` for GB10; the same model's other profiles in the same image cover B200/H200/H100/etc. as you'd expect.

```
docker run -d --name nim-nemotron-nano-9b-v2 --gpus all --shm-size=16g \
    -p 8000:8000 \
    -e NGC_API_KEY=nvapi-<redacted> \
    -v /home/nvidia/.nim/cache/nvidia-nemotron-nano-9b-v2-dgx-spark:/opt/nim/.cache \
    nvcr.io/nim/nvidia/nvidia-nemotron-nano-9b-v2-dgx-spark:latest
```

The same `-v` mount that the existing Llama-3.1-8B Spark NIM uses (only the directory name changes), the same shm-size, the same port. The image was a 33 GB pull on Wi-Fi at ~9 MB/s sustained, then NIM downloaded another 8 GB of model weights (10 safetensors shards) into the cache mount over another ~15 minutes. After that, the engine took about a minute to load weights into GPU memory, the V1 LLM engine warmed (Flash Attention backend, `cudagraph_mode=FULL_AND_PIECEWISE` because hybrid-mamba models disable prefix caching), and `/v1/models` returned `id: nvidia/nemotron-nano-9b-v2 | max_model_len: 131072`.

That `max_model_len: 131072` is the line that changes the article. The Llama-8B Spark NIM caps `max_model_len` at 8192 — even though Llama-3.1 natively supports 128K context, NVIDIA's Spark build of the 8B image is a smaller-context profile to keep the working set lean. AutoResearchBench's agent loop accumulates context turn-by-turn — the planner sees the system prompt, the original question, every prior turn's tool call, and every prior turn's tool response. At turn 5 with top-10 web results and per-result summaries, the input is comfortably past 11–12K tokens. NIM 8B returns an HTTP 400 with `This model's maximum context length is 8192 tokens. However, your request has 12,925 input tokens.` and the bench logs `status: context_length_exceeded`.

```
$ AUTORESEARCHBENCH_ENV_FILE=~/.config/autoresearchbench/.env \
    bash run_inference.sh
...
Running Inference: 100%|██████████| 3/3 [08:22<00:00, 167.64s/it]
```

Eight minutes wall for three questions on the 8B NIM, with two of the three hitting context-length errors before reaching a final candidate. The same `run_inference.sh` against the 9B-v2 NIM completes all three cleanly in ~11 minutes (each question runs longer because the model is reasoning-tuned and outputs more chain-of-thought tokens per turn — typically 1000+ tokens of `<think>…</think>` deliberation before each tool call).

The outputs land as JSONL with one row per question. The bench's own per-question schema includes a `status` field (one of `finished`, `context_length_exceeded`, plus a few others) and a `turn_details` array with per-turn `action`, `duration`, `input_tokens`, `output_tokens`, and `papers_retrieved_this_turn`. That's the data `analyze_run.py` aggregates into the summary table at the top of this article. Two scripts ship in `articles/autoresearchbench-on-spark/scripts/`:

```python
# scripts/analyze_run.py — wraps fieldkit.eval.Bench around the per-question
# summary so the same code lifts into other agent benches in the future.
from fieldkit.eval import Bench, summarize_metric

bench = Bench(name=f"autoresearchbench/{args.label}",
              metrics=["turns", "candidates"])
for i, r in enumerate(rows):
    ir = r["inference_results"][0]
    bench.record(
        input=r["input_data"]["arxiv_id"],
        output={"status": ir["status"], "candidates": len(ir.get("final_candidates") or [])},
        latency_ms=float(ir["total_time"]) * 1000.0,
        success=(ir["status"] == "finished" and len(ir.get("final_candidates") or []) > 0),
        error=None if ir["status"] == "finished" else ir["status"],
        tags={"q_index": i, "model": args.label},
        turns=float(len(ir.get("turn_details") or [])),
    )
```

The use of [`fieldkit.eval`](/fieldkit/api/eval/) is a small win on its own — the same `Bench` object that the [bench-rag sample](/fieldkit/api/eval/) used to aggregate naive-RAG latencies absorbs the AutoResearchBench per-question record without modification. `summarize_metric` rolls the per-question wall_seconds, turns, and candidates into the headline stats. The full per-turn detail (action, duration, papers retrieved, tool-format errors) gets captured alongside in the same JSON, ready for a future `fieldkit.eval.AgentRun` abstraction that the existing [`Trajectory`](/fieldkit/api/eval/) — shaped for the autoresearch arc's scalar-score iterations — doesn't quite fit.

The 9B-v2's per-question turn detail is where the article's thesis hardens:

| q | arxiv | turns | first-turn outcome | input_tokens (max) | wall |
|---|---|---:|---|---:|---:|
| 1 | 2204.05525 (TopFormer) | 3 | tool-format parse error → retry → finish | 4,617 | 327.7s |
| 2 | 2011.04709 (f-IRL) | 2 | retrieved 10 papers → judged "None" | 12,589 | 432.8s |
| 3 | 2011.03802 (Symmetric Parallax) | 2 | retrieved 10 papers → judged "None" | 11,740 | 330.0s |

Q1 hit a real wrinkle worth naming: **the Nemotron-Hybrid model wraps tool calls in a `<tool_call>` block whose internal serialization diverges slightly from what the Qwen-Agent-flavored bench parser expects**. The first turn returned `action: error`, `papers_retrieved: 0`, with an action_content of `Failed to parse tool format error: <tool_call>…`. The model self-corrected on turn 2 by emitting a parser-friendly version. This is a model–harness compatibility detail, not a defect of either side — it's the kind of thing a power user setting up a third-party agent bench against a curated NIM expects to spend an afternoon ironing out before they trust the numbers.

Q2 and Q3 ran cleanly in two turns each. Both questions blew past 11K input tokens (the Llama-8B's hard wall), reasoned over the full top-10 web result list, and produced explicit `<candidates>None</candidates>` outputs after evaluating every paper against the query criteria. The reasoning is articulate: paper 6 partially matches the vehicular scenario but lacks the divergence-objective constraint; paper 3 mentions frame selection but uses NIQE/BRISQUE and not the information-theoretic statistic the question specifies; therefore, no match. That's not a model failure — that's the model correctly observing that **the truth paper is not among the ten papers a generic web search returned for the query**. The bench's headline ~9% accuracy uses a paper-specialized retrieval API (DeepXiv) precisely because *generic web search caps every model at near-zero accuracy* on this dataset.

## Verification — what success feels like on Spark for an agent bench

Three concrete things to look at, on this hardware, that you couldn't see without running the bench yourself.

**Memory under load.** With the 9B-v2 NIM warm and the bench's three concurrent agent worker processes running their tool calls and reasoning chains, peak resident memory measured at about 22 GiB (NIM's vLLM workspace plus the model's NVFP4 weights), with another ~3 GiB for the Python agent processes and their summarizer-call buffers. The Spark's 121 GiB unified pool sat at 60 GiB free for the duration. Quantization at NVFP4 puts the 9B's weights at ~5 GB on disk plus the KV cache for whatever effective context the agent uses (the bench held average ~10K input tokens in flight, so KV stayed small). 128K-context inference at 9B on Spark is comfortable, not tight.

**Per-turn latency.** The 9B-v2 took an average of 110-180 seconds per turn — substantially longer than the 8B's 25-40 seconds — but that's the cost of the reasoning-tuned model emitting several hundred to a thousand tokens of explicit deliberation before each action. For an agent bench whose outputs you're going to read and grade, that's a feature, not a defect: the trace is auditable, the per-candidate reasoning is explicit, and the wall-time is still well under what cloud-API rate limits would impose if you were running this against a frontier API.

**The upstream evaluator runs in milliseconds.** The bench ships an `evaluate_deep_search.py` that's an LLM-as-judge — it sends each predicted candidate plus the truth title to a judge model, asks for a 0/1 match, and computes Accuracy@1. With 0 candidates produced across all 3 questions for both models, the judge had nothing to grade — the script returns `Accuracy@1: 0.00%, pass@1: 0.00%, mean@1: 0.0000` in 0.05 seconds without making a single judge call. That's the *correct* zero, formally, but it gives back almost no information about whether the model-side or retrieval-side is the bound.

## Tradeoffs and surprises

**The catalog gap is real.** The original plan was to hold the 8B comparison against `nvcr.io/nim/nvidia/llama-3.3-nemotron-super-49b-v1` — NVIDIA's reasoning-tier 49B Llama-3.3 derivative. The image is in NGC, pulled to disk, and weighs 23.4 GB. On Spark it refuses to start: `Detected 0 compatible profile(s)`. `list-model-profiles` against the image prints engines for L40s (`tensorrt_llm-l40s-fp8-tp4-pp1-latency-26b9:10de-4`), B200, H100, H200, H100-NVL, A100, A100-SXM4 — and nothing for GB10. The Spark-curated NIMs are a strict subset of the published catalog, distinguished by an `-dgx-spark` suffix on the image name (`llama-3.1-8b-instruct-dgx-spark`, `nvidia-nemotron-nano-9b-v2-dgx-spark`). When NIM startup logs `0 compatible profile(s)`, the model exists in the catalog but not for your hardware — look for the `-dgx-spark` variant of the same family before reaching for Ollama or another runtime.

**The Wi-Fi flap was annoying.** The Nemotron-Nano image pulled at ~9 MB/s sustained over 16 minutes (33 GB image + 8 GB of model weights downloaded into the cache mount). Mid-session, Wi-Fi link rate dropped from 216 Mbit/s to 135 Mbit/s and went from 2-stream to 1-stream MIMO — interference or AP load on 2.4 GHz, not a Spark issue but worth diagnosing before pulling another 30+ GB image. The wired interface (`enP7s7`) is available; an Ethernet pull would probably double or triple this throughput. The NGC CDN itself sat at ~10–15 MB/s in bursts, so the upstream isn't the constraint either — 5/6 GHz Wi-Fi or wired would help future pulls.

**The Llama-8B context wall is a Spark-NIM build choice, not a Llama-3.1 limit.** The Llama-3.1-8B-Instruct *model* supports 128K natively. The Spark NIM image ships with `max_model_len: 8192` to keep the working set lean for the smaller end of the GB10 envelope. On a single-shot Q&A workload that's fine; on an accumulating-context agent loop it's a hard cliff. If you're spinning up a Spark NIM for an agent that grows context turn-by-turn, *check `/v1/models` first* — the `max_model_len` field is in the response and tells you whether your bench will reach turn 6.

**The reasoning-tuned model talks more.** Nemotron-Nano-9B-v2 is reasoning-tuned. Even when the bench's system prompt asks for terse structured output, the model emits 800–1,200 tokens of `<think>…</think>` deliberation per turn before producing the `<tool_call>` or `<candidates>` block. That's why per-question wall time is ~3.6 minutes vs the 8B's ~2.5 minutes when the 8B doesn't crash. It also means *every* trace is explicitly auditable — for an observability-stage article in the Frontier Scout series, the per-turn reasoning is half the value, not overhead.

**Tool-format compatibility is a thing.** The bench is built on Qwen-Agent (`qwen-agent==0.0.34` per its `requirements.txt`). The Nemotron-Hybrid family wraps tool calls in a `<tool_call>` block whose internal format diverges slightly from what Qwen-Agent's parser expects. Q1's first turn errored on parse with `Failed to parse tool format error: <tool_call>…`; the model recovered on turn 2. Three things you might want to do downstream: (a) catch the tool-format error specifically and retry with a clarifying system message, (b) lift the prompt to explicitly call out the JSON tool-call schema, or (c) write a thin adapter inside the bench's tool layer that normalizes Nemotron-style tool-calls before handing them to Qwen-Agent. None of that is necessary for the article's thesis, but it's the kind of frictional surface a real production deployment of this stack would have to file.

## What this unlocks

**A Spark-local Frontier Scout bench loop.** The Frontier Scout series scouts arxiv papers and decides which ones are worth a deep-dive on Spark. AutoResearchBench is a *meta* bench for that workflow — it asks the agent to find specific papers given probing questions about them. Wired up the way this article wires it (NIM on `localhost:8000/v1`, OpenAI-compat slots all pointing at the same NIM, web search via Serper+Jina), the bench becomes a reusable substrate for measuring *which model + retrieval combination* makes the autonomous-research-loop work. The next obvious experiment is upgrading retrieval (adding the DeepXiv API once it's available, or substituting an arxiv-aware retriever the user runs on their own corpus) and re-measuring — same scripts, same `analyze_run.py` summary, drop-in.

**A canonical "compare two NIMs" scaffold.** The `analyze_run.py` + `compare_runs.py` pair in `articles/autoresearchbench-on-spark/scripts/` is general — it consumes any inference output JSONL with the bench's per-question schema and produces a `Bench`-style summary plus a side-by-side comparison JSON. Future articles in the Frontier Scout series will reuse it. When the next NIM with extended context lands in the Spark catalog (Nemotron-Nano-Omni 30B is announced, Nemotron-Super 120B/12B-active is announced), the third row of the comparison drops in by changing one `--label` argument.

**A repeatable read of "is the bottleneck the model or the retrieval?"** The two-zero result here makes the diagnostic pattern obvious. When two models with very different capabilities both score zero on the same agent bench, the bottleneck is upstream of the model — almost always retrieval, sometimes the tool-call format, sometimes the truncation policy. Future agent-bench articles can lift the same diagnostic: vary the model first, vary the retrieval second, and the location of the change in the score is the location of the bottleneck.

## Closing — same destination, two journeys

Two Spark-tuned NIMs, the same three Deep-Research questions, the same 0% Accuracy@1, two completely different reasons. The 8B's zero is a model–bench mismatch — its 8K context wall is a build choice that's invisible until an accumulating-context agent loop hits it, and at that point the `context_length_exceeded` is a hard signal to either swap models or reshape the bench. The 9B-v2's zero is the *correct* read of a thin retrieval signal — the model completes the loop, evaluates ten web results per question, and concludes that none match the ground truth. To move that needle you don't reach for a bigger model; you reach for a better retriever.

Next in the Frontier Scout series: take this same bench substrate and aim it at the four other in-flight evaluations the scout has scaffolded — `clawgym`, `claw-eval-live`, `test-time-distilling`, `scientific-foundation-models-as-tools` — each of which exercises a different combination of `fieldkit` modules. The 9B-v2 NIM that this article warmed up is the agent driver for the next three articles in the series. The Spark stays at 60 GiB free; the loop stays on the desk.
