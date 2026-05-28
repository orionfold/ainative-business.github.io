---
title: "The Hermes Serving Lane on a DGX Spark — MoE vs Dense, and the Number That Actually Picks the Lane"
date: 2026-05-26
author: Manav Sehgal
product: NIM
stage: deployment
difficulty: intermediate
time_required: "~3 hours, most of it model pulls and four cold-starts"
hardware: "NVIDIA DGX Spark"
tags: [hermes, vllm, llama-cpp, nim, qwen3, moe, tool-calling, dgx-spark]
summary: "Five Hermes serving lanes on one DGX Spark: Qwen3-30B-A3B MoE vs Qwen3-32B dense across vLLM, llama.cpp, and NIM. The MoE runs ~8.5× faster for the same memory — but the lane is picked by tool-call reliability, which took two config fights to get to 0% everywhere."
signature: HermesLaneBakeoff
series: Harnesses
also_stages: [inference]
fieldkit_modules: [capabilities, harness, nim]
---

The first article in this series installed the cockpit: Hermes Agent driving the cached Nemotron-Nano-9B-v2 NIM, a closed tool-call loop, no API key. It closed on a question it deliberately left open — *which* model should sit behind the harness once you care about speed? A 9B answers a file-read in a few seconds, but it also occasionally misreads what it just read. The obvious move is a bigger model. The non-obvious part is that on a 128 GB DGX Spark, "bigger" splits into two very different shapes — a **mixture-of-experts** model that's 30B on disk but only activates 3B per token, and a **dense** model that activates all 32B — and they behave nothing alike under an agent loop.

So this piece is a bakeoff. Five lanes on one machine: Qwen3-30B-A3B (MoE) and Qwen3-32B (dense), each served two ways — through **vLLM** at FP8 and through **llama.cpp** at Q4 — plus the NIM Nemotron lane from article #1 as the incumbent. Three numbers per lane: throughput, sustained-load behavior, and the one that decides whether a lane is usable at all by an agent — **tool-call reliability**. The headline result is a clean 8.5× speed gap between MoE and dense; the result I didn't expect is that *every* lane can be made perfectly reliable, and the real work was two configuration fights that have nothing to do with the model.

:::define[Mixture-of-experts (MoE)]
A transformer whose feed-forward layers are split into many "expert" sub-networks, with a router that sends each token to only a few of them. Qwen3-30B-A3B has **30B total parameters but activates ~3B per token** (`A3B` = "active 3B"). All 30B must be *resident* in memory, but only 3B do arithmetic on each token — so it costs like a 3B model to run and like a 30B model to store. A dense model activates every parameter on every token.
:::

## Why the lane is the whole question on this machine

On a cluster you pick the model that fits your GPUs and move on. On a DGX Spark the 128 GB of unified memory inverts that: almost any model you'd actually want for a local agent *fits*, so the binding constraint stops being "does it load" and becomes "how fast does it turn a tool-call loop, and does it turn it correctly every time." For an always-on agent you text from your phone — the destination this series is walking toward — those two numbers are the entire user experience. A lane that answers in three seconds but mangles one tool call in ten is worse than useless; it's actively dangerous, because the harness *acts* on the call it can't parse.

That reframes "deployment" for a personal box. There's no autoscaler, no fleet, no A/B traffic split. There's one machine, one model resident at a time, and a choice about which serving stack drives it. The cloud hides this decision behind an endpoint URL; the Spark makes you make it, and the cost of making it wrong is a slow or unreliable agent sitting on your desk. The good news is that the decision is *measurable* in an afternoon, which is exactly what the rest of this article does.

:::why[Tool-call reliability is the metric, not tok/s]
Throughput is the number everyone benchmarks because it's easy. But a harness doesn't consume tokens — it consumes *tool calls*. If the model emits a malformed `tool_calls` block, the loop stalls or, worse, the harness acts on garbage. So the gating metric is the **format-error rate**: of every tool call the agent attempted, how many came back as well-formed structured calls the harness could execute. A lane that fails here is disqualified regardless of how fast it is. tok/s only breaks ties among lanes that already pass.
:::

## The two shapes, and where they sit

Hermes speaks plain OpenAI `/v1/chat/completions`, so any of these lanes is just a `base_url` swap as far as the harness is concerned. What changes behind that URL is the serving stack and the model's *shape*. The bakeoff holds the model family constant (all Qwen3, same tokenizer and chat template) and varies two axes: MoE vs dense, and vLLM vs llama.cpp. The NIM Nemotron lane is the incumbent from article #1 — a different model, kept as a reliability and speed reference point.

<figure class="fn-diagram" aria-label="Two model shapes converging on one verdict. The top lane is Qwen3-30B-A3B, a mixture-of-experts model activating 3B of 30B parameters, measured around 88 and 56 tokens per second on llama.cpp and vLLM. The bottom lane is Qwen3-32B, a dense model activating all 32B, measured around 10 and 7 tokens per second. Both lanes converge on a shared accent node reading 0% tool-call format error, 100% clean — agent-grade. An annotation marks the roughly 8.5x speed gap between the lanes.">
  <svg viewBox="0 0 900 440" role="img" aria-label="Two model shapes converging on one verdict. The top lane is Qwen3-30B-A3B, a mixture-of-experts model activating 3B of 30B parameters, measured around 88 and 56 tokens per second on llama.cpp and vLLM. The bottom lane is Qwen3-32B, a dense model activating all 32B, measured around 10 and 7 tokens per second. Both lanes converge on a shared accent node reading 0% tool-call format error, 100% clean — agent-grade. An annotation marks the roughly 8.5x speed gap between the lanes." preserveAspectRatio="xMidYMid meet">
    <defs>
      <linearGradient id="d02-moe-lane-grad" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%"   stop-color="var(--svg-accent-blue)" stop-opacity="0.10"/>
        <stop offset="100%" stop-color="var(--svg-accent-blue)" stop-opacity="0.02"/>
      </linearGradient>
      <linearGradient id="d02-dense-lane-grad" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%"   stop-color="var(--svg-accent-orange)" stop-opacity="0.10"/>
        <stop offset="100%" stop-color="var(--svg-accent-orange)" stop-opacity="0.02"/>
      </linearGradient>
      <radialGradient id="d02-verdict-halo-grad" cx="0.5" cy="0.5" r="0.6">
        <stop offset="0%"   stop-color="var(--svg-accent-blue)" stop-opacity="0.16"/>
        <stop offset="100%" stop-color="var(--svg-accent-blue)" stop-opacity="0"/>
      </radialGradient>
      <linearGradient id="d02-verdict-accent-grad" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%"   stop-color="var(--color-primary)" stop-opacity="0.30"/>
        <stop offset="100%" stop-color="var(--color-primary)" stop-opacity="0.08"/>
      </linearGradient>
    </defs>
    <rect x="50" y="60" width="300" height="140" rx="10" fill="url(#d02-moe-lane-grad)" stroke="none"/>
    <rect x="50" y="240" width="300" height="140" rx="10" fill="url(#d02-dense-lane-grad)" stroke="none"/>
    <rect x="570" y="160" width="270" height="120" rx="8" fill="url(#d02-verdict-halo-grad)" stroke="none"/>
    <g class="fn-diagram__edges">
      <path class="fn-diagram__edge fn-diagram__edge--accent" pathLength="100" d="M 320 130 L 570 205" />
      <path class="fn-diagram__edge" pathLength="100" d="M 320 310 L 570 245" />
    </g>
    <g class="fn-diagram__nodes">
      <rect class="fn-diagram__node" x="70" y="70" width="250" height="120" rx="8" />
      <rect class="fn-diagram__node" x="70" y="250" width="250" height="120" rx="8" />
      <rect class="fn-diagram__node fn-diagram__node--accent fn-diagram__pulse" x="570" y="160" width="270" height="120" rx="8" style="fill: url(#d02-verdict-accent-grad)" />
    </g>
    <g class="fn-diagram__labels">
      <text class="fn-diagram__label fn-diagram__label--accent" x="195" y="128" text-anchor="middle">MOE LANE</text>
      <text class="fn-diagram__label fn-diagram__label--display" x="195" y="148" text-anchor="middle">Qwen3-30B-A3B</text>
      <text class="fn-diagram__label fn-diagram__label--mono fn-diagram__label--muted" x="195" y="166" text-anchor="middle">3B active of 30B</text>
      <text class="fn-diagram__label fn-diagram__label--muted" x="195" y="308" text-anchor="middle">DENSE LANE</text>
      <text class="fn-diagram__label fn-diagram__label--display" x="195" y="328" text-anchor="middle">Qwen3-32B</text>
      <text class="fn-diagram__label fn-diagram__label--mono fn-diagram__label--muted" x="195" y="346" text-anchor="middle">32B active of 32B</text>
      <text class="fn-diagram__label fn-diagram__label--accent" x="705" y="218" text-anchor="middle">SHARED VERDICT</text>
      <text class="fn-diagram__label fn-diagram__label--display" x="705" y="240" text-anchor="middle">0% format error</text>
      <text class="fn-diagram__label fn-diagram__label--mono fn-diagram__label--muted" x="705" y="260" text-anchor="middle">100% clean · agent-grade</text>
    </g>
    <g class="fn-diagram__annotations">
      <text class="fn-diagram__annotation" x="445" y="150" text-anchor="middle">~88 · 56 tok/s</text>
      <text class="fn-diagram__annotation" x="445" y="300" text-anchor="middle">~10 · 7 tok/s</text>
      <text class="fn-diagram__annotation" x="445" y="225" text-anchor="middle">~8.5× gap</text>
    </g>
    <g class="fn-diagram__symbols">
      <g class="fn-diagram__icon fn-diagram__icon--accent" transform="translate(183 78)"><path d="M8.25 3v1.5M4.5 8.25H3m18 0h-1.5M4.5 12H3m18 0h-1.5m-15 3.75H3m18 0h-1.5M8.25 19.5V21M12 3v1.5m0 15V21m3.75-18v1.5m0 15V21m-9-1.5h10.5a2.25 2.25 0 002.25-2.25V6.75a2.25 2.25 0 00-2.25-2.25H6.75A2.25 2.25 0 004.5 6.75v10.5a2.25 2.25 0 002.25 2.25zm.75-12h9v9h-9v-9z"/></g>
      <g class="fn-diagram__icon" transform="translate(183 258)"><path d="M8.25 3v1.5M4.5 8.25H3m18 0h-1.5M4.5 12H3m18 0h-1.5m-15 3.75H3m18 0h-1.5M8.25 19.5V21M12 3v1.5m0 15V21m3.75-18v1.5m0 15V21m-9-1.5h10.5a2.25 2.25 0 002.25-2.25V6.75a2.25 2.25 0 00-2.25-2.25H6.75A2.25 2.25 0 004.5 6.75v10.5a2.25 2.25 0 002.25 2.25zm.75-12h9v9h-9v-9z"/></g>
      <g class="fn-diagram__icon fn-diagram__icon--accent" transform="translate(693 168)"><path d="M9 12.75L11.25 15 15 9.75M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/></g>
    </g>
  </svg>
  <figcaption>Two shapes, same family, same memory class — and the same verdict on the only metric that disqualifies a lane. What separates them is an 8.5× speed gap the router buys for free.</figcaption>
</figure>

:::define[The unified-memory envelope]
The GB10 shares one 128 GB pool between CPU and GPU. A serving lane's resident cost is roughly model weights + KV cache + runtime overhead, and all of it draws from that single pool. Qwen3-30B-A3B is ~32 GB at FP8 and ~19 GB at Q4 GGUF; the dense 32B is about the same. Either fits with room to spare — but only **one at a time**, which is why the bakeoff serves lanes sequentially and `fieldkit`'s `serve_lane` guard refuses to start a lane that would tip the pool.
:::

## Right-sizing before launching

Before serving anything I let `fieldkit.capabilities` do the envelope arithmetic, because the cheapest bug to catch is the one you catch before a 30 GB model loads. Each lane is a `fieldkit.harness` `serve_lane` context — it sizes the lane's footprint against currently-available unified memory, refuses if it wouldn't fit with headroom, brings the lane up, waits for it to warm, and tears it down on exit so the next lane starts from a clean pool:

```python
from fieldkit.harness import LaneSpec, VLLMLane, serve_lane

# One model at a time. The guard reuses fieldkit.capabilities' memory math and
# raises UnifiedMemoryExceeded *before* launch if the lane wouldn't fit.
spec = LaneSpec("vllm", "Qwen/Qwen3-30B-A3B-FP8", port=8000,
                extra={"gpu_memory_utilization": 0.75, "max_model_len": 40960})
with serve_lane(VLLMLane(spec, footprint_gb=98.0), warm_timeout=900) as lane:
    ...  # benchmark against lane.base_url; torn down (+ EngineCore sweep) on exit
```

The teardown is the load-bearing part. vLLM has a well-documented failure mode on this box where a stopped server leaves an orphaned `EngineCore` worker holding ~100 GB of unified memory — and on a single-pool machine that one orphan hangs everything. `VLLMLane.teardown` stops the container and then sweeps for the orphan, so each lane in the bakeoff starts from a verified-clean pool. Across all five lanes, memory returned to ~116 GB free after every teardown; no orphan ever survived.

:::why[One model at a time is a feature, not a limitation]
On a fleet you'd run these lanes side by side and compare live. On the Spark the 128 GB pool forbids it — and that turns out to clarify the benchmark rather than constrain it. Each lane gets the whole machine, so the tok/s number is the lane's *best* case, not a number contended down by a neighbor. The sequential `serve_lane` pattern isn't a workaround for small memory; it's the honest way to measure a personal box you'll only ever run one model on anyway.
:::

## Throughput: the 8.5× the router buys you

The throughput method is deliberately boring — a fixed prompt, a 256-token completion, measured straight against each lane's OpenAI endpoint with no agent loop in the way, after a warm-up pass. Single-stream, because a personal agent is a single user. Here's the full board, fastest first:

| Lane | Serving stack | Quant | tok/s | Sustained (3 min) | Peak temp |
|---|---|---|---:|:---:|:---:|
| Qwen3-30B-A3B **MoE** | llama.cpp | Q4_K_M | **88.0** | 87.3 (−0.5%) | 65 °C |
| Qwen3-30B-A3B **MoE** | vLLM | FP8 | 55.9 | 55.5 (−0.0%) | 56 °C |
| Nemotron-9B (incumbent) | NIM | — | 27.7 | — | — |
| Qwen3-32B **dense** | llama.cpp | Q4_K_M | 10.2 | 10.2 (−0.2%) | 64 °C |
| Qwen3-32B **dense** | vLLM | FP8 | 6.6 | 6.6 (−0.2%) | 60 °C |

The MoE-vs-dense gap is the headline: **88 vs 10 on llama.cpp, 56 vs 7 on vLLM** — about 8.5× either way, for models that cost essentially the same to store. That's the 3B-active router doing exactly what it promises. On a memory-bound box like the Spark, where decode speed tracks how many parameter bytes you stream per token, activating 3B instead of 32B is close to a 10× discount, and you pay it in storage you have to spare. For a local agent that turns many short tool-call loops, this is the single biggest lever on the desk.

:::define[Single-stream vs batched throughput]
A serving stack can be fast in two different ways: low latency for *one* request (single-stream) or high aggregate tokens across *many concurrent* requests (batched). llama.cpp is tuned for the former, vLLM for the latter — its continuous batching and paged KV cache shine when dozens of requests share the GPU. This bakeoff measures single-stream because a personal agent is one user, which is exactly the regime where llama.cpp's 88 beats vLLM's 56. Put fifty users on the box and the ranking would flip; on your desk, it won't.
:::

The second surprise is in that sustained column. I ran each lane flat-out for three continuous minutes expecting to watch the GB10 thermally throttle — and it essentially didn't. Throughput drift stayed inside ±0.5% across every lane, with peak temperatures of 56–65 °C. Three minutes isn't an overnight soak, but it's long enough to say the Spark holds its single-stream rate under a sustained agent burst rather than sagging after the first few seconds. The incumbent NIM lane's 27.7 tok/s, measured single-stream, sits where you'd expect a batch-tuned 9B to land when only one request is in flight — fast enough, and the lane I still trust most, for reasons the next section earns.

## The number that actually picks the lane

Throughput orders the lanes; tool-call reliability decides whether each one is allowed on the list at all. The method borrows the harness's own memory: Hermes persists every agent run in a SQLite session store, and `hermes sessions export` dumps it to JSONL — one record per run, each carrying the full message trace with per-turn `finish_reason` and `tool_calls`. `fieldkit.harness` parses that trace into the same `eval.AgentRun` shape the rest of this blog uses for agent benchmarks, then reduces it:

```python
from fieldkit.harness import agent_runs_from_hermes_sessions, tool_call_reliability

runs = agent_runs_from_hermes_sessions("hermes_sessions.jsonl")
print(tool_call_reliability(runs))
# {'n_runs': 8, 'tool_calls': 8, 'tool_format_errors': 0,
#  'format_error_rate': 0.0, 'clean_run_rate': 1.0, 'finished_rate': 1.0, ...}
```

I drove each lane through the same eight-task battery — read a planted phrase, count lines, create-then-read, a shell date, a search, a sum — byte-identical prompts across every lane, each task a real `hermes -z` agent turn. The result is almost anticlimactic, and that's the point: **every lane scored a 0% format-error rate and a 100% clean-run rate.** Once a lane was configured correctly, all five — MoE and dense, vLLM and llama.cpp and NIM — emitted well-formed tool calls on every task. The dense models even tended to make *more* tool calls per task (1.4–1.9 vs the MoE's 1.0), spending their extra deliberation on the loop rather than fumbling it.

:::define[Format-error rate]
Of every tool call the agent *attempted*, the fraction that came back malformed — a `tool_calls` block the harness couldn't parse into a function name plus valid JSON arguments. It's the agent-critical number because the harness acts on tool calls: a clean answer that arrives via a broken call is still a broken loop. `clean_run_rate` is its per-task companion — the fraction of whole tasks that completed with zero format errors. Both at their ceiling (0% error, 100% clean) is the bar a lane has to clear to be agent-grade.
:::

"Once configured correctly" is carrying real weight in that paragraph. The first time I ran the GGUF lanes and the vLLM lanes, both scored *zero tool calls* — the agent did nothing — and the honest version of this article is mostly about the two fights that took.

## The two configuration fights

Neither fight was about the model. Both were about a default in the stack between Hermes and the model, and both produced the same misleading symptom — an agent that exits cleanly having done nothing — which is exactly the kind of silent failure that makes "0% reliability" look like a model problem when it's a config problem.

The first was Hermes refusing the model outright. Hermes enforces a **64K-token minimum context window** for "reliable tool-calling workflows," and Qwen3's native context is 40,960 — below the floor. Hermes aborts before the first call with a `ValueError`, the `hermes -z` turn exits, and no session is ever written. The fix is the override Hermes documents, but with a catch: you have to set it in *two* places, because Hermes also runs the served model as its own context-compression model and checks that separately.

:::pitfall[Hermes rejects any model under 64K context — in two places]
Qwen3 serves at native 40,960 tokens; Hermes's minimum is 64,000. Setting `model.context_length: 64000` clears the *main* model check but not the *auxiliary compression* check, which fails with a near-identical error naming the same model. You need both `model.context_length` and `auxiliary.compression.context_length`. Declaring 64K while serving 40K is safe here because the agentic tasks never use more than ~30K — the override tells Hermes the budget, it doesn't change what the lane serves.
:::

The second fight was subtler because vLLM *looked* like it was working — it warmed, it answered raw completions at 56 tok/s, its `/v1/models` returned 200 — but every agent turn produced a session with only the user's message and no assistant reply. vLLM does not emit structured `tool_calls` unless you serve it with `--enable-auto-tool-choice` and a model-matched `--tool-call-parser`; without them, a request carrying a `tools` array is rejected and the turn dies before the model ever reasons. The parser for Qwen3 is `hermes` (the format Qwen models use). The moment I added the flags, the vLLM MoE lane went from 0 tool calls to a perfect 8-for-8.

:::pitfall[vLLM serves tool calls only with the parser flags]
A bare `vllm serve` answers chat completions fine but silently can't do tool calls — it needs `--enable-auto-tool-choice --tool-call-parser <parser>` (`hermes` for Qwen3). The failure is invisible from a throughput test and only shows up under an agent loop, as an empty assistant turn. `fieldkit`'s `VLLMLane` now sets these by default, on the principle that a serving lane built for an agent harness that can't tool-call isn't a lane worth shipping.
:::

That's why article #1 insisted on measuring this rather than asserting it, and why NIM remains the lane I reach for first even though llama.cpp is faster: the NIM container ships the correct tokenizer, chat template, *and* tool-call config in the box, so it had none of these fights. The other lanes match its reliability — but only after you win the two configuration battles the NIM lane already won for you.

## Packaging the result as an artifact

A bakeoff that lives in a notebook is a one-off; a bakeoff that ships as a reusable profile is infrastructure. So the measured board above renders to a `harness` artifact — a new `fieldkit` artifact kind — via `HarnessProfile`, the harness analog of the model cards this project publishes:

```python
from fieldkit.harness import HarnessProfile, publish_harness

profile = HarnessProfile(title="Spark Hermes Profile — serving-lane bakeoff",
                         lanes=measured_lanes, hermes_config=cfg, env_example=env, ...)
publish_harness(profile=profile, repo_name="spark-hermes-profile",
                staging_dir=..., artifacts_dir=..., dry_run=True)
```

The profile bundles the lane table, the embedded `hermes.yaml` + `.env` that reproduce the recommended lane, a doctor checklist, and the bounded caveats (the reliability sample is eight tasks per lane, not a large-N guarantee) into a README plus a manifest the site catalog renders. The recommended lane it pins is the llama.cpp MoE — fastest single-stream and agent-grade — with NIM a hop behind on speed and ahead on trust. Staged dry-run first, because publishing a profile that recommends a lane is a claim, and the claim should be reproducible from the same `fieldkit` surface that measured it.

## What this unlocks

With the lane decided, three things are newly concrete this week. **A snappy local agent**: swapping the article-#1 9B for the Qwen3-30B-A3B MoE roughly triples the tok/s while keeping tool calls perfect, so the file-triage and scripting agents from last time stop feeling like they're thinking out loud. **A reproducible serving recipe**: the `spark-hermes-profile` artifact is a copy-pasteable `hermes.yaml` + `.env` + the two override lines that took an afternoon to find, so the next person's lane works on the first `hermes -z`. And **a sizing rule of thumb** you can carry to any model: on this box, prefer the MoE shape — it buys ~8.5× decode speed for memory you have to spare, and the dense model's only edge (slightly more deliberate multi-tool runs) rarely pays for a 9× slowdown.

The honest caveat is the one the method draws a box around: every reliability number here is eight tasks per lane on file-and-shell tools. It says the lanes *can* be made agent-grade and that the two config fights are the real work — it does not say a lane will never fumble a gnarlier tool schema. That's the next layer of rigor, and it's exactly what hardening is for.

## Closing

The DGX Spark's 128 GB turns a fleet question — which model fits which GPUs — into a personal one: which *shape* of model, on which serving stack, drives your agent fastest without ever fumbling a tool call. The answer this time is the MoE, by 8.5×, on a lane you can fit five different ways and only run one at a time. But the durable lesson isn't the winner; it's that throughput sorts the lanes and reliability disqualifies them, and that getting a lane to agent-grade is two config fights the marketing copy never mentions. The cockpit is installed and it's fast. Next it needs to be safe — because the same agent that reliably reads the file you asked for will just as reliably read the one you didn't.

:::deeper
- [The Hermes Harness on a DGX Spark](/field-notes/the-hermes-harness-on-spark/) — article #1: installing the cockpit and the first local tool-call loop against NIM.
- [Qwen3-30B-A3B (Qwen)](https://huggingface.co/Qwen/Qwen3-30B-A3B) — the MoE; `A3B` = 3B active of 30B total.
- [vLLM tool calling](https://docs.vllm.ai/en/latest/features/tool_calling.html) — the `--enable-auto-tool-choice` + `--tool-call-parser` flags this article fought.
- [vLLM on DGX Spark (eugr/spark-vllm-docker)](https://github.com/eugr/spark-vllm-docker) — the community image, with prebuilt Spark wheels, that the vLLM lanes ran on.
:::

:::hardware[Same gap, more headroom]
The MoE-vs-dense ratio is an arithmetic property of activation, not of the Spark — it holds on any memory-bound accelerator. What a frontier box changes is the floor: the dense 32B that crawls at ~10 tok/s on GB10's unified memory would clear 5–6× that on an H100's HBM3 and more on an H200 or B200, enough that the dense penalty stops mattering for a single user. The Spark's contribution is making the *choice* legible — when every lane fits and only one runs at a time, you measure the trade-off directly instead of inheriting it from whatever the cluster scheduler happened to place.
:::

---

**Catalog page:** [`/artifacts/harnesses/spark-hermes-profile/`](/artifacts/harnesses/spark-hermes-profile/) — positioning, lane variants with measured throughput, the recommended lane, and bounded drift — the full Spark-agent harness profile.
