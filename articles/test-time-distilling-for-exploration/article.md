---
title: "Test-Time Distilling on Spark — Same Compute Envelope, Wider Semantic Reach"
date: 2026-05-02
author: Manav Sehgal
product: Foundation
stage: inference
also_stages: [observability]
difficulty: advanced
time_required: "~2 hours — most of it watching vLLM 0.20 build inside an NGC PyTorch container; the runtime+drift diagnosis that follows is the short, sharp half"
hardware: "NVIDIA DGX Spark"
tags: [decoding, sampling, test-time-scaling, reasoning, distillation, vllm, runtime]
summary: "ESamp adds a tiny test-time-trained probe to vLLM that converts decoding from lexical resampling into semantic exploration. The runtime is vLLM-native — and that is a Spark catalog-gap story before it is a benchmark."
signature: EsampExploration
series: Frontier Scout
fieldkit_modules: [eval, capabilities]
---

[KV-cache arithmetic at inference](/articles/kv-cache-arithmetic-at-inference/) asked one question of a fixed compute budget: *how much fits?* Weights × dtype, KV cache × context × batch, all the way down to the last GiB. The answer determined what could run on the Spark at all.

[ESamp](https://arxiv.org/abs/2604.24927) — *Large Language Models Explore by Latent Distilling* — asks a different question of the same envelope: *how widely can the model search inside it?* When you sample n=8 candidates from the same prompt, do you get eight lexically different rephrasings of one bad attempt, or eight semantically distinct paths through the answer space? At fixed compute, the second is worth more. Pass@k benchmarks on AIME, MATH, and HumanEval reward whichever dimension the samples actually spread along; the paper reports that a ~1 GB online-trained probe pushes that spread without measurably moving the wall clock — the optimized 7B `min_p` path lands at **0.9878×** the baseline tokens-per-second on a reference RTX 4090 run, with a Pass@k lift on the reasoning benchmarks the paper highlights.

The plot twist for a Spark power-user is upstream of the numbers. ESamp ships as a runtime extension to **vLLM v1**, packaged as the [tLLM](https://github.com/LinesHogan/tLLM) repository — a Producer/Consumer hook layer over vLLM. The Spark's blessed inference path is **NIM (TensorRT-LLM) and Triton**, not vLLM. So the article's first half is about a stack mismatch, not a benchmark: when a paper's runtime is in a different lane than the box's verified runtime, what does it actually take to make the experiment runnable here?

## The paper, in one breath

**Thesis.** Standard stochastic decoding produces *lexical* variation but rarely *semantic* exploration — temperature and top-p resample near-duplicate ideas. ESamp adds a lightweight Distiller trained online at test time to predict the LLM's *deep*-layer hidden state from its *shallow*-layer hidden state. When the Distiller's prediction error spikes on a candidate continuation, that's a novelty signal — the prefix is moving into territory the LLM hasn't been recently calibrated on — and ESamp reweights token candidates toward those less-explored semantic patterns.

**Why this technique matters for a personal AI builder.** Reasoning workloads spend their compute budget on `n` parallel samples; if all `n` collapse onto rephrasings of one bad attempt, the budget is wasted. ESamp converts the same `n` into `n` *semantically distinct* paths through the answer space — which is the dimension Pass@k on AIME, MATH, and HumanEval actually rewards. At a fixed compute envelope, that is the difference between a brittle reasoner and one that explores.

**Promise vs achieved.** Paper claims **0.9878×** baseline tokens-per-second on a reference RTX 4090 with CUDA graphs (vLLM 0.10.x), with a Pass@k lift on the reasoning benchmarks above. *This* article does not measure the ratio — it lands the runtime substrate and surfaces the first two upstream API drifts that block tLLM's hooks on vLLM 0.20.0. The ratio measurement on Spark lands in the [follow-up](/articles/runtime-frontier-six-patches-on-spark/), which closes at **0.974×** on patched Qwen 2.5 7B — within **1.4 percentage points** of the paper, with CUDA graphs deliberately disabled and six (not two) patches in place.

## Why this matters for a personal AI builder

Reasoning models are the workload class where the Spark's 128 GiB unified pool earns its line on the spec sheet — n=16 parallel completions of a 7B reasoning model with a few thousand tokens each is comfortable, not tight. A frontier-API equivalent would burn through credits and rate limits long before you finished iterating on the *sampler*. The Spark makes test-time-scaling techniques — Pass@k sweeps, beam-search ablations, sampler-guidance tuning — *iterable*. ESamp is one such technique that needs the iteration: the Distiller is online-trained, its hyperparameters interact with the model and the prompt distribution, and getting the `--distiller-beta` knob right takes a sweep.

But none of that is reachable until vLLM runs on the box. The Spark catalog ships eight-or-so curated `-dgx-spark` NIM images and zero vLLM containers. vLLM-on-Blackwell exists in the broader ecosystem but the wheels and CUDA-13 ABI matrix is its own afternoon. This article documents that afternoon as a first-class part of the work — the catalog gap is the experiment.

## Where this sits in the stack

The paper's algorithm and the runtime that hosts it are deliberately decoupled. ESamp's idea — predict the model's deep-layer hidden state from its shallow-layer hidden state with a lightweight probe, treat prediction error as a novelty signal, reweight token candidates in proportion — could in principle live in any inference engine. In practice it lives in vLLM v1 because that is where the published reference implementation runs, and re-porting it to TensorRT-LLM is a separate research-engineering project the paper does not attempt.

<figure class="fn-diagram" aria-label="The tLLM runtime sits as a thin layer between vLLM v1's hot path and a consumer such as the ESampConsumer. The left lane shows the vLLM v1 verified path on the Spark — installable but not the curated NIM/TRT-LLM lane that ships with the box. tLLM's runtime hooks bind around three vLLM lifecycle points (load_model, _prepare_inputs, execute_model) plus the sampler bridge. ESamp's consumer reads the residual_stream port at a shallow and deep layer, runs an asynchronous distiller train step on the captured hidden rows, and writes back into the sampler as a post_filter_exact intervention with a beta knob. The right side surfaces the same n=16 sample slot whether or not the consumer is registered — the visible difference is in how those samples spread through the answer space, not in their wall-clock cost.">
  <svg viewBox="0 0 900 440" role="img" aria-label="Layered diagram showing the tLLM runtime mediating between the vLLM v1 hot path and the ESamp consumer. Three lifecycle hooks (load_model, prepare_inputs, execute_model) plus a sampler bridge feed a consumer flow that reads residual_stream rows at a shallow and deep layer, runs an asynchronous distiller training step, and writes a post-filter sampler intervention back into vLLM. Same compute envelope, different reach across the answer space." preserveAspectRatio="xMidYMid meet">
    <defs>
      <linearGradient id="ttd-accent-grad" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%"   stop-color="var(--color-primary)" stop-opacity="0.30"/>
        <stop offset="100%" stop-color="var(--color-primary)" stop-opacity="0.08"/>
      </linearGradient>
      <linearGradient id="ttd-vllm-band" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%"   stop-color="var(--svg-accent-blue)" stop-opacity="0.10"/>
        <stop offset="100%" stop-color="var(--svg-accent-blue)" stop-opacity="0.02"/>
      </linearGradient>
      <linearGradient id="ttd-consumer-band" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%"   stop-color="var(--svg-accent-teal)" stop-opacity="0.10"/>
        <stop offset="100%" stop-color="var(--svg-accent-teal)" stop-opacity="0.02"/>
      </linearGradient>
      <radialGradient id="ttd-tllm-halo" cx="0.5" cy="0.5" r="0.65">
        <stop offset="0%"   stop-color="var(--color-primary)" stop-opacity="0.12"/>
        <stop offset="100%" stop-color="var(--color-primary)" stop-opacity="0"/>
      </radialGradient>
    </defs>
    <rect x="20" y="40" width="860" height="160" rx="10" fill="url(#ttd-vllm-band)" stroke="none"/>
    <rect x="20" y="240" width="860" height="160" rx="10" fill="url(#ttd-consumer-band)" stroke="none"/>
    <rect x="320" y="180" width="260" height="120" rx="10" fill="url(#ttd-tllm-halo)" stroke="none"/>
    <rect x="320" y="180" width="260" height="120" rx="10" fill="none"
          stroke="var(--color-text-muted)" stroke-width="0.5" stroke-dasharray="3 3"/>
    <g class="fn-diagram__edges">
      <path class="fn-diagram__edge" pathLength="100" d="M 220 120 L 320 220" />
      <path class="fn-diagram__edge" pathLength="100" d="M 580 220 L 700 120" />
      <path class="fn-diagram__edge" pathLength="100" d="M 220 320 L 320 260" />
      <path class="fn-diagram__edge fn-diagram__edge--accent" pathLength="100" d="M 580 260 L 700 320" />
    </g>
    <g class="fn-diagram__nodes">
      <rect class="fn-diagram__node" x="60" y="80" width="160" height="80" rx="8" />
      <rect class="fn-diagram__node fn-diagram__node--accent" x="320" y="180" width="260" height="120" rx="10"
            style="fill: url(#ttd-accent-grad)" />
      <rect class="fn-diagram__node" x="700" y="80" width="160" height="80" rx="8" />
      <rect class="fn-diagram__node" x="60" y="280" width="160" height="80" rx="8" />
      <rect class="fn-diagram__node" x="700" y="280" width="160" height="80" rx="8" />
    </g>
    <g class="fn-diagram__labels">
      <text class="fn-diagram__label fn-diagram__label--muted" x="75" y="104" text-anchor="start">VLLM V1 ENGINE</text>
      <text class="fn-diagram__label fn-diagram__label--display" x="75" y="126" text-anchor="start">load_model · prepare_inputs</text>
      <text class="fn-diagram__label fn-diagram__label--mono fn-diagram__label--muted" x="75" y="144" text-anchor="start">execute_model · sampler</text>
      <text class="fn-diagram__label fn-diagram__label--accent" x="335" y="208" text-anchor="start">tLLM RUNTIME</text>
      <text class="fn-diagram__label fn-diagram__label--display" x="335" y="230" text-anchor="start">producer · localization · bundles</text>
      <text class="fn-diagram__label fn-diagram__label--mono fn-diagram__label--muted" x="335" y="248" text-anchor="start">ports: residual_stream, logits</text>
      <text class="fn-diagram__label fn-diagram__label--mono fn-diagram__label--muted" x="335" y="266" text-anchor="start">sampler-bridge: post_filter_exact</text>
      <text class="fn-diagram__label fn-diagram__label--mono fn-diagram__label--muted" x="335" y="284" text-anchor="start">async-train window: background</text>
      <text class="fn-diagram__label fn-diagram__label--muted" x="715" y="104" text-anchor="start">SamplingParams</text>
      <text class="fn-diagram__label fn-diagram__label--display" x="715" y="126" text-anchor="start">n=16 · temp 0.8 · top_p 0.95</text>
      <text class="fn-diagram__label fn-diagram__label--mono fn-diagram__label--muted" x="715" y="144" text-anchor="start">same envelope either way</text>
      <text class="fn-diagram__label fn-diagram__label--muted" x="75" y="304" text-anchor="start">ESampConsumer</text>
      <text class="fn-diagram__label fn-diagram__label--display" x="75" y="326" text-anchor="start">distiller(shallow → deep)</text>
      <text class="fn-diagram__label fn-diagram__label--mono fn-diagram__label--muted" x="75" y="344" text-anchor="start">~1 GB online-trained probe</text>
      <text class="fn-diagram__label fn-diagram__label--muted" x="715" y="304" text-anchor="start">SAMPLER INTERVENTION</text>
      <text class="fn-diagram__label fn-diagram__label--display" x="715" y="326" text-anchor="start">(1+β)·llm − β·distiller</text>
      <text class="fn-diagram__label fn-diagram__label--mono fn-diagram__label--muted" x="715" y="344" text-anchor="start">novelty signal → wider reach</text>
    </g>
    <g class="fn-diagram__annotations">
      <text class="fn-diagram__annotation" x="270" y="200" text-anchor="middle">capture hidden rows</text>
      <text class="fn-diagram__annotation" x="640" y="200" text-anchor="middle">return n samples</text>
      <text class="fn-diagram__annotation" x="640" y="340" text-anchor="middle">reweight last; keep top-k/top-p/min-p first</text>
    </g>
  </svg>
  <figcaption>The intervention is gated through the same SamplingParams either way — the difference is in how the n samples spread through the answer space, not in their wall-clock cost.</figcaption>
</figure>

The runtime split is what makes the paper's overhead claim tractable: the consumer's training pipeline runs in a `background` window — its backward pass overlaps the next vLLM forward. On the validated 7B `min_p` path, the optimized intervention sits at **98.78% of baseline tok/s** (5,304.855 vs 5,370.616 on the reference 4090). On Spark, that overhead figure is the second number we want to read. The first one is whether the runtime starts at all.

## The journey — landing a vLLM-native paper on a NIM-curated box

The repo's install instructions are honest and short. From `tLLM/doc/getting-started/installation.md`:

```bash
python -m venv .venv && source .venv/bin/activate
pip install vllm
pip install -e .
python starter.py --max-new-tokens 32
```

Three lines, one validated environment (`vllm==0.10.x`, the doc says), and a healthy run prints `loss_count > 0` and a list of generations. On a normal x86 + CUDA 12 host with pre-built wheels, this works in minutes. On a Spark — aarch64 GB10 (SM 12.1), `nvcr.io/nvidia/pytorch:25.11-py3` shipping `torch 2.10.0a0+nv25.11` against CUDA 13.0 — the `pip install vllm` line is the work. There is no published wheel that matches *all of*: aarch64, SM 12.1, CUDA 13, vLLM ≥ 0.10. The install resolves, then starts compiling source dependencies (`fastsafetensors` is the first to appear in `/tmp/pip-build-env-*/`), and the wall clock starts ticking.

```bash
docker run -d --name tllm-build --gpus all --ipc=host \
  --ulimit memlock=-1 --ulimit stack=67108864 \
  -v /tmp/tllm-spark:/work \
  -v /home/nvidia/.../evidence/repo-snapshot:/tllm:ro \
  nvcr.io/nvidia/pytorch:25.11-py3 sleep infinity

docker exec tllm-build sh -c '
  python3 -c "import torch; print(torch.__version__, torch.version.cuda,
                                   torch.cuda.get_device_capability(0))"
'
# 2.10.0a0+b558c986e8.nv25.11  13.0  (12, 1)
```

The four numbers in the second command's output are the entire integration story compressed: torch is the container's nightly, CUDA is the new major (13.0, not 12.x), and the device reports SM 12.1 — the Blackwell B100/GB10 compute capability. vLLM 0.10.x wheels were built for CUDA 12, so the matrix forces a build. The build is the article's first measurable: a sustained `pip install vllm` that holds the box at ~3 GB of resident pip-build-env, walking through every source dep that doesn't have a matching pre-built wheel for this triple.

While that runs, the rest of the experimental shape is fixed enough to write the harness around it. ESamp's published functional check is a `repro_esamp_loss` runner that takes the model name, a list of debug prompts, and the two layer paths the Distiller bridges. Its published throughput benchmark is `per_request_esamp_benchmark`, comparing `single_off` (plain vLLM) against `model_bank_on` (ESamp registered as a consumer) on identical SamplingParams. The ratio is the headline. From `doc/reference/esamp-usage.md`:

```text
ratio = model_bank_on / single_off   # baseline=1.0; paper's optimized 7B = 0.9878
```

The `Bench` shape that absorbed [AutoResearchBench's per-question schema in article #1](/articles/autoresearchbench-on-spark/) generalizes to ESamp's per-prompt-batch schema cleanly:

```python
# scripts/run_esamp_bench.py — registers fieldkit.eval.Bench around the
# tLLM throughput-benchmark workflow, so the same harness rolls up Pass@k
# tasks once the verifier loops are added in the next article.
from fieldkit.eval import Bench, summarize_metric
from fieldkit.capabilities import Capabilities, practical_inference_envelope

caps = Capabilities.load()
print(practical_inference_envelope("7B params bf16"))   # sanity: Qwen-7B fits
# ~14 GB weights; leaves >100 GB of unified pool for KV / activations / Distiller

for label, args in [("baseline", BASELINE_ARGS), ("esamp", ESAMP_ARGS)]:
    with Bench(name=f"esamp/{label}",
               metrics=["tokens_per_s", "loss_avg", "answers"]) as bench:
        for prompt in PROMPTS:
            bench.record(callable=lambda: tllm_run(prompt, args))
    bench.report()
```

The install resolves cleanly — `pip install vllm` lands `vllm-0.20.0` after a ~14-minute build that walks `fastsafetensors` and a long tail of CUDA-13 user-space packages. Post-install: `torch 2.11.0+cu130`, CUDA available, GB10 reported as SM (12, 1), `vllm 0.20.0`, `from vllm import LLM, SamplingParams` round-trips. So far so good.

The validated tLLM environment was `vllm==0.10.x`. The starter, run on the smallest model the doc suggests as the OOM-safe default, gets through model load and into vLLM v1 engine init — and dies inside a tLLM patch:

```text
File "/tmp/tllm-rw/tllm/runtime/vllm_patch/sampler_patch.py", line 181,
    in wrapped_sampler_sample
  logits_for_sampling = sampler.apply_temperature(
      logits, sampling_metadata.temperature
  )
TypeError: Sampler.apply_temperature() missing 1 required positional argument: 'all_random'
```

That's the article's catalog gap reduced to a single signature change. tLLM's runtime patches a v1-engine sampler whose entry point gained a third required argument across the 0.10 → 0.20 churn. The fix is local — `all_random` is already computed three lines above the failing call, in the same function — and the patched call goes through:

```diff
- logits_for_sampling = sampler.apply_temperature(logits, sampling_metadata.temperature)
+ logits_for_sampling = sampler.apply_temperature(logits, sampling_metadata.temperature,
+                                                 sampling_metadata.all_random)
```

The patch goes through. The starter — patched, otherwise unmodified — gets the rest of the way through engine init: vLLM v1 allocates a KV cache of 3,894,336 tokens (max-concurrency 15,212× at 256 tokens per request — Qwen 2.5 0.5B is tiny next to the 128 GiB pool), the FlashInfer autotuner runs in 60 ms, and CUDA-graph capture finishes in 3 seconds across 51 piecewise-prefill-decode shapes and 35 decode-full shapes. Engine init reports `init engine (profile, create kv cache, warmup model) took 82.18 s (compilation: 5.15 s)`. Four prompts render. The first execute_model hits a *second* drift:

```text
File "/tmp/tllm-rw/tllm/runtime/vllm_patch/port_runtime_hooks.py", line 511,
    in wrapped_prepare_inputs
TypeError: _wrapped_prepare_inputs() takes 2 positional arguments but 3 were given
```

vLLM 0.20.0's `GPUModelRunner._prepare_inputs(self, scheduler_output, num_scheduled_tokens)` added a required second positional argument; tLLM's `wrapped_prepare_inputs(*, core, runner, scheduler_output)` was written to keyword-route a single `scheduler_output`. That is a deeper change than the sampler one — the wrapper's keyword-only signature, the adapter that downstream consumers call to unpack `prepare_inputs` output, and the consumer's bundle-assembly path all need to thread the new `num_scheduled_tokens` argument. It's still tractable — five-to-ten lines and a careful re-read of the runtime — but it's the second uncaptured drift in the same file in two patches, and that is itself the article's central evidence: **the runtime is the frontier**. The test-time-distilling literature is moving fast enough that the production-grade inference engine it targets is itself moving fast enough that one-line drifts compound into deeper ones. The catalog gap on the Spark side meets the version drift on the upstream side; both are tractable, neither is documented in the paper, and a power user landing this stack here ends a session with two upstream patches in their notes and a Pass@k matrix queued for the next session.

## Verification — what success looks like on Spark

The "did the integration work" question splits cleanly into three layers, and we got two and a half of them by running the patched starter against `Qwen/Qwen2.5-0.5B-Instruct` (the doc's OOM-safe default) inside the PyTorch container:

| Layer | What it asks | This session |
|---|---|---|
| **Install** | Does `pip install vllm` resolve and import on the Spark's torch + CUDA + SM triple? | ✅ vllm 0.20.0 in ~14 min; `torch 2.11.0+cu130`; `import vllm` round-trips |
| **Engine** | Does vLLM v1 init, allocate KV, capture CUDA graphs on GB10? | ✅ KV cache 3.8M tokens; 86 CUDA graphs captured; `init engine took 82.18 s` |
| **tLLM hooks** | Do tLLM's runtime patches bind into the vLLM v1 hot-path on this version? | ⚠ two API drifts: `apply_temperature` (one-line fix), `_prepare_inputs` (multi-line fix) |
| **ESamp loss** | Does the consumer fire and `loss_count > 0` after a real prompt? | deferred — gated on the second patch landing |
| **Throughput ratio** | Is `model_bank_on / single_off` in the same neighborhood as the paper's 0.9878? | deferred — gated on the consumer firing |

The interesting line is the Engine row. vLLM 0.20.0 — torch-2.11.0+cu130, no Spark-specific tuning, default `--gpu-memory-utilization=0.4` — initialized cleanly on GB10 (SM 12.1) inside an `nvcr.io/nvidia/pytorch:25.11-py3` container with nothing more exotic than `pip install vllm`. CUDA-graph capture, FlashInfer autotuning, and KV-cache profiling all worked. That is the *positive* result of the session and it is worth naming: vLLM-on-Blackwell is no longer the multi-day port it was at the start of the GB10 cycle. The fact that it "just works" with one pip install is the substrate the next experiment lives on top of.

The unified-memory check the Spark uniquely cares about is the easy one to read off this run. KV cache reserved 3.89 M token slots inside the 0.4 × 121 GiB envelope — meaning a 0.5B model's KV is a rounding error against the unified pool. Scaling to Qwen-7B at bf16 (~14 GB weights), n=16 decode at `max_tokens=512` (a few GB of KV in the same arithmetic), plus the ESamp Distiller (~1 GB) lands the whole loadout under 25 GB on a 121 GiB envelope. That is the inversion of the [KV-cache arithmetic](/articles/kv-cache-arithmetic-at-inference/) story: where the foundation article asked *what fits*, the test-time-distilling article asks *what does fitting waste*. The Spark is comfortable; the bottleneck — once the runtime patches land — will be throughput overhead and consumer-side GPU contention, not capacity.

## Tradeoffs and surprises

**vLLM-on-Blackwell is solved; vLLM-on-Blackwell-with-tLLM is the open afternoon.** The two halves of that sentence point in opposite directions. The base install — `pip install vllm` inside `nvcr.io/nvidia/pytorch:25.11-py3` against torch 2.11.0+cu130 and SM 12.1 — resolved cleanly to vllm 0.20.0 in ~14 minutes, walked through one source build (`fastsafetensors`), and produced an engine that allocated KV cache, captured CUDA graphs, and warmed up in 82 seconds. None of that needed a Spark-specific patch. The runtime extension — tLLM, validated against `vllm==0.10.x` — needed two patches in two different files in the same session to clear two different signature drifts on the v1-engine API surface. Pinning to `vllm==0.10.2` would close those drifts but open a different set: torch 2.11.0+cu130 is what the container's stack converges on, and rolling torch back to whatever 0.10.x was built against re-opens the build matrix. The right answer depends on whether the tLLM authors land 0.20.x support upstream first or whether the user files patches and runs from a fork; this article is the data point that prompts that decision.

**The runtime/algorithm split is the paper's gift.** ESamp the algorithm — predict deep hidden state from shallow, treat error as novelty, reweight tokens by `(1+β)·llm − β·distiller` — is reasonably small and well-isolated in the consumer. It is the *runtime* — the Producer/Consumer/Port/ConsumerFlow plumbing that lets a consumer read packed-tensor row-localized hidden states and write back through the sampler bridge without forking vLLM — that is the engineering load. The split means the algorithm is portable in principle: a TRT-LLM consumer with the same intervention math could in theory live on the verified Spark inference path. Nobody has written that consumer; the gap is engineering, not research.

**Pass@k verifier loops are deferred, intentionally.** AIME and HumanEval Pass@k requires per-task verifier loops (math correctness, sandbox code execution). Those are well-trodden ground in the eval ecosystem and not novel to this article — but they are non-trivial to wire up correctly, and the article's claim is sharper if the *runtime* number is honest before the *task* number is asserted. The follow-up article in this series will land Pass@k on AIME and HumanEval against a Spark-side ESamp run; today's article lands the runtime and characterizes its overhead.

**`fieldkit.eval` already absorbs the harness; `fieldkit.inference` is the next surface to lift.** The throughput-comparison loop, the per-prompt-batch metrics dict, the `model_bank_on / single_off` ratio computation — all of that fits inside the existing `fieldkit.eval.Bench` shape. What does not fit is a vLLM-flavored client wrapper analogous to the existing `fieldkit.nim.NIMClient`. A `fieldkit.inference.VLLMClient` would absorb the SamplingParams construction, the `make_llm` call, and the throughput-measurement boilerplate that every vLLM-side experiment in the series will otherwise repeat. This is the one new module the test-time-distilling work motivates; tracked for `fieldkit v0.2`. A second candidate worth filing now is `fieldkit.eval.PassAtK` — a verifier-loop primitive that takes a per-task grader and an `n`-sample iterator and returns `pass@1, pass@k`. That candidate also lands in v0.2, alongside the AIME/HumanEval follow-up article.

## What this unlocks

**A repeatable shape for "the paper's runtime is in a different lane than my box's runtime."** This article is not the first time the Spark has met a paper whose reference implementation runs on a stack the box does not curate; it will not be the last. The shape — pull a PyTorch container, install the third-party runtime from source, document the version-pin choices, then write the harness around it — is reusable. The next paper in the Frontier Scout queue (`scientific-foundation-models-as-tools`) will need a similar move for a different runtime. Documenting the surface area of the move now means the next one is shorter.

**A test-time-scaling experimental substrate on the desk.** vLLM-on-Blackwell now installs in one pip line and 14 minutes inside the standard NGC PyTorch container. That is the substrate every test-time-scaling technique lives on — speculative decoding, classifier-free guidance, contrastive decoding, beam-search ablations, the rest of the literature. All of them are sampler interventions; all of them are tunable on a workload the user owns; all of them benefit from the Spark's ability to run n=16 (or n=64) parallel completions of a 7B reasoning model without rate limits or per-token billing. ESamp is the first-class citizen; the runtime install path is what makes the rest reachable.

**A clean motivating case for `fieldkit.inference`.** The same week's [AutoResearchBench article](/articles/autoresearchbench-on-spark/) closed by surfacing a candidate `fieldkit.eval.AgentRun` for the per-question, per-turn agent schema. This week's article surfaces two new candidates — `fieldkit.inference.VLLMClient` and `fieldkit.eval.PassAtK` — that the package's v0.2 release will likely absorb. The pattern is healthy: each Frontier Scout article validates one or two existing modules and proposes one or two new ones, with the package's CHANGELOG growing from real authoring rather than speculative scope.

## Closing — exploration as the dual of capacity

The Spark's distinguishing feature is not that it runs models you couldn't run elsewhere; it is that it lets one person own the entire test-time-scaling loop end-to-end — including the part where the loop is two upstream patches away from completing. KV-cache arithmetic answered *what fits*; ESamp asks *what does fitting waste*. Same compute envelope, different question. The paper's claim — that an online-trained ~1 GB probe converts decoding from lexical resampling into semantic exploration at ≤1.2% overhead — is exactly the kind of claim that wants a second machine to verify it, and a Spark is the second machine that does not need a second wallet. The verification is queued, not finished; the runtime substrate is now in place to finish it.

Next in the Frontier Scout series: the AIME and HumanEval Pass@k follow-up that this article scaffolds the harness for, with the two `vllm_patch` drifts either landed upstream or filed locally. After that, the same `fieldkit.eval.Bench` shape rolls into `clawgym`, `claw-eval-live`, and `scientific-foundation-models-as-tools` — three more papers, three more catalog-gap shapes, all of them landing on the desk and not the cloud.
