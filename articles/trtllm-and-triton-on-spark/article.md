---
title: "TensorRT-LLM on the Spark — FP8 Isn't the Reason to Drop NIM. NVFP4 Is."
date: 2026-04-23
author: Manav Sehgal
product: TensorRT-LLM + Triton Inference Server
stage: deployment
difficulty: advanced
time_required: "~4 hours including two container pulls and three engine builds"
hardware: "NVIDIA DGX Spark"
tags: [deployment, tensorrt-llm, triton, trtllm-serve, fp8, nvfp4, blackwell, gb10, second-brain, dgx-spark]
summary: "Dropping below NIM to raw TensorRT-LLM on a GB10 Spark. FP8 beats NIM's vLLM by 10-15% — barely worth the rebuild. NVFP4 beats it by 76% on decode, 43% on TTFT, and ships a 34%-smaller engine. The reason to drop NIM is the Blackwell-native 4-bit kernel, not FP8."
signature: TrtLlmBladeTriple
series: Second Brain
---

NIM 8B is the convenient answer. One `docker run`, an OpenAI-compatible endpoint on port 8000, 22 tokens per second of greedy decode on the DGX Spark, eleven gigabytes resident, and enough concurrency to carry a small team without breaking a sweat. The label on the container says `meta/llama-3.1-8b-instruct`, and the temptation is to treat it as a generic upstream. But the NIM ref hash is `hf-fp8-42d9515+chk1` and the environment declares `BACKEND_TYPE=vllm` — NVIDIA ships an FP8-quantized, Spark-specific build of vLLM 0.10.1 inside. The convenience tax is not buying you laziness; it is buying you a tuned stack.

That reframes the question the Second Brain arc wants answered. The original thesis was *"is the complexity of raw TensorRT-LLM worth the latency win over NIM?"* The answer, once you strip away the marketing framing, is almost no. TRT-LLM FP8 beats the NIM FP8 baseline by **10–15%** on decode and time-to-first-token. That is not nothing, but it is also not worth a container pull, a checkpoint convert, an engine rebuild every time the model moves, and a new serving surface to maintain.

The real answer lives one precision further down. This article spent a session building three parallel 8B servers — NIM vLLM FP8, TRT-LLM FP8, and TRT-LLM **NVFP4** — and measuring them against the same 29-token prompt, 200-token greedy completion, stream-per-client benchmark. The NVFP4 run, the Blackwell-native 4-bit variant that only exists when you drop below NIM, pulled **38.8 tokens/second of decode** (vs 22.1 on NIM), **30.8 ms TTFT** (vs 54 ms), a **5.7 GB engine file** (vs 8.6 GB for TRT-LLM FP8), and **2.5 GiB resident** (vs 11.2 GiB for NIM). The reason to rebuild is not FP8. It is the 4-bit kernel that Blackwell's SM 12.1 executes in hardware and that NIM's vLLM does not expose.

## Why this matters for the power user on one machine

Unified memory is what makes the DGX Spark interesting for a personal AI builder, and it is also what makes memory footprint the first-class currency on this hardware. The GPU and the CPU share one 121.7 GiB pool. Every gigabyte a serving stack holds resident is a gigabyte pgvector cannot use for its index, that a second NIM cannot use for its weights, that Nsight cannot use while it traces a request. Trading NIM's 11.2 GiB for NVFP4's 2.5 GiB is not a benchmark flex — it is room for the next load-bearing piece of the Second Brain, without migrating anything to disk.

The latency math is the second reason, and it lands in the opposite direction from what a cluster engineer would predict. At concurrency 1 — one user, one query, which is exactly what a Second Brain looks like most of the day — TRT-LLM NVFP4 cuts the end-to-end wall clock from 7.3 seconds to 5.1 seconds for a 165-token answer. That is the difference between a query that feels *slow* and one that feels *instant*. And it is specifically a single-user, single-stream win. On a cluster you would solve this with a bigger batch; on a personal rig you solve it by descending one layer of abstraction and picking the kernel the silicon was designed for.

## Architectural context — one checkpoint, three stacks

<figure class="fn-diagram" aria-label="Three serving stacks on the same Llama 3.1 8B base checkpoint, showing decode throughput, TTFT, and resident memory side by side. NIM bundles vLLM FP8 and a Spark-specific quant in one convenient container. TRT-LLM FP8 drops below NIM to run the same precision through a TensorRT-compiled engine. TRT-LLM NVFP4 is the Blackwell-native 4-bit path and the thesis of this article.">
  <svg viewBox="0 0 900 440" role="img" aria-label="One 8B base checkpoint → three serving stacks → three result profiles. NIM vLLM FP8 is the convenience baseline. TRT-LLM FP8 is the comparable-precision descent. TRT-LLM NVFP4 is the Blackwell-native 4-bit win." preserveAspectRatio="xMidYMid meet">
    <defs>
      <linearGradient id="d11-lane-nim" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%"   stop-color="var(--svg-text-muted)" stop-opacity="0.08"/>
        <stop offset="100%" stop-color="var(--svg-text-muted)" stop-opacity="0.02"/>
      </linearGradient>
      <linearGradient id="d11-lane-fp8" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%"   stop-color="var(--svg-accent-blue)" stop-opacity="0.10"/>
        <stop offset="100%" stop-color="var(--svg-accent-blue)" stop-opacity="0.02"/>
      </linearGradient>
      <linearGradient id="d11-lane-nvfp4" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%"   stop-color="var(--svg-accent-green)" stop-opacity="0.14"/>
        <stop offset="100%" stop-color="var(--svg-accent-green)" stop-opacity="0.02"/>
      </linearGradient>
      <linearGradient id="d11-accent-grad" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%"   stop-color="var(--color-primary)" stop-opacity="0.30"/>
        <stop offset="100%" stop-color="var(--color-primary)" stop-opacity="0.08"/>
      </linearGradient>
      <radialGradient id="d11-accent-halo" cx="0.5" cy="0.5" r="0.7">
        <stop offset="0%"   stop-color="var(--color-primary)" stop-opacity="0.12"/>
        <stop offset="100%" stop-color="var(--color-primary)" stop-opacity="0"/>
      </radialGradient>
    </defs>
    <rect x="280" y="40"  width="320" height="120" rx="10" fill="url(#d11-lane-nim)"   stroke="none"/>
    <rect x="280" y="170" width="320" height="120" rx="10" fill="url(#d11-lane-fp8)"   stroke="none"/>
    <rect x="280" y="300" width="320" height="120" rx="10" fill="url(#d11-lane-nvfp4)" stroke="none"/>
    <rect x="620" y="300" width="220" height="120" rx="10" fill="url(#d11-accent-halo)" stroke="none"/>
    <g class="fn-diagram__edges">
      <path class="fn-diagram__edge" pathLength="100" d="M 220 230 L 280 100" />
      <path class="fn-diagram__edge" pathLength="100" d="M 220 230 L 280 230" />
      <path class="fn-diagram__edge fn-diagram__edge--accent" pathLength="100" d="M 220 230 L 280 360" />
      <path class="fn-diagram__edge" pathLength="100" d="M 440 100 L 620 100" />
      <path class="fn-diagram__edge" pathLength="100" d="M 440 230 L 620 230" />
      <path class="fn-diagram__edge fn-diagram__edge--accent" pathLength="100" d="M 440 360 L 620 360" />
    </g>
    <g class="fn-diagram__nodes">
      <rect class="fn-diagram__node" x="60"  y="190" width="160" height="80" rx="10" />
      <rect class="fn-diagram__node" x="280" y="60"  width="160" height="80" rx="10" />
      <rect class="fn-diagram__node" x="280" y="190" width="160" height="80" rx="10" />
      <rect class="fn-diagram__node fn-diagram__node--accent"
            x="280" y="320" width="160" height="80" rx="10"
            style="fill: url(#d11-accent-grad)" />
      <rect class="fn-diagram__node" x="620" y="60"  width="220" height="80" rx="10" />
      <rect class="fn-diagram__node" x="620" y="190" width="220" height="80" rx="10" />
      <rect class="fn-diagram__node fn-diagram__node--accent"
            x="620" y="320" width="220" height="80" rx="10"
            style="fill: url(#d11-accent-grad)" />
    </g>
    <g class="fn-diagram__labels">
      <text class="fn-diagram__label" x="140" y="222" text-anchor="middle">Llama 3.1 8B</text>
      <text class="fn-diagram__label fn-diagram__label--mono" x="140" y="240" text-anchor="middle">FP8 / NVFP4 HF ckpt</text>
      <text class="fn-diagram__label" x="140" y="258" text-anchor="middle">from NVIDIA / ModelOpt</text>
      <text class="fn-diagram__label" x="360" y="92" text-anchor="middle">NIM (vLLM 0.10.1 FP8)</text>
      <text class="fn-diagram__label fn-diagram__label--mono" x="360" y="112" text-anchor="middle">BACKEND_TYPE=vllm</text>
      <text class="fn-diagram__label fn-diagram__label--mono" x="360" y="128" text-anchor="middle">:8000 · nim-llama31-8b</text>
      <text class="fn-diagram__label" x="360" y="222" text-anchor="middle">TRT-LLM FP8 engine</text>
      <text class="fn-diagram__label fn-diagram__label--mono" x="360" y="242" text-anchor="middle">trtllm-build --gemm_plugin fp8</text>
      <text class="fn-diagram__label fn-diagram__label--mono" x="360" y="258" text-anchor="middle">trtllm-serve · :8003</text>
      <text class="fn-diagram__label" x="360" y="352" text-anchor="middle">TRT-LLM NVFP4 engine</text>
      <text class="fn-diagram__label fn-diagram__label--mono" x="360" y="372" text-anchor="middle">trtllm-build --gemm_plugin nvfp4</text>
      <text class="fn-diagram__label fn-diagram__label--mono" x="360" y="388" text-anchor="middle">SM 12.1 hardware FP4</text>
      <text class="fn-diagram__label fn-diagram__label--mono" x="730" y="88"  text-anchor="middle">22.1 tok/s · TTFT 54 ms</text>
      <text class="fn-diagram__label" x="730" y="108" text-anchor="middle">11.2 GiB resident</text>
      <text class="fn-diagram__label fn-diagram__label--mono" x="730" y="126" text-anchor="middle">c=8 agg: 175 tok/s</text>
      <text class="fn-diagram__label fn-diagram__label--mono" x="730" y="218" text-anchor="middle">24.6 tok/s · TTFT 46 ms</text>
      <text class="fn-diagram__label" x="730" y="238" text-anchor="middle">engine: 8.6 GB</text>
      <text class="fn-diagram__label fn-diagram__label--mono" x="730" y="256" text-anchor="middle">c=8 agg: 194 tok/s</text>
      <text class="fn-diagram__label fn-diagram__label--mono" x="730" y="348" text-anchor="middle">38.8 tok/s · TTFT 31 ms</text>
      <text class="fn-diagram__label" x="730" y="368" text-anchor="middle">engine: 5.7 GB · 2.5 GiB RAM</text>
      <text class="fn-diagram__label fn-diagram__label--mono" x="730" y="386" text-anchor="middle">c=8 agg: 265 tok/s</text>
    </g>
    <g class="fn-diagram__annotations">
      <text class="fn-diagram__annotation" x="140" y="175" text-anchor="middle">same base · same prompt</text>
      <text class="fn-diagram__annotation" x="360" y="48"  text-anchor="middle">CONVENIENCE</text>
      <text class="fn-diagram__annotation" x="360" y="178" text-anchor="middle">COMPARABLE PRECISION</text>
      <text class="fn-diagram__annotation" x="360" y="308" text-anchor="middle">BLACKWELL-NATIVE</text>
      <text class="fn-diagram__annotation" x="730" y="288" text-anchor="middle">+10% vs NIM</text>
      <text class="fn-diagram__annotation" x="730" y="418" text-anchor="middle">+76% decode · 4× less RAM</text>
    </g>
  </svg>
  <figcaption>The reason to descend is not the middle lane.</figcaption>
</figure>

NIM is a layered stack hiding under one label: NVIDIA's vLLM fork bundled with a Spark-specific FP8 checkpoint, a KV-cache manager, a tokenizer, an OpenAI-compatible HTTP surface, a health probe, telemetry. TRT-LLM is a single compiled engine behind a thinner server. Triton is the fuller serving plane — model repository, ensemble graphs, dynamic batching — that this article explicitly chose *not* to stand up in its full form. For a single-model OpenAI endpoint, `trtllm-serve serve` gives you the 80% and skips the model-repo scaffolding entirely. That choice is worth naming up front, because every TRT-LLM tutorial on the internet points at the old ensemble pipeline and the newer path is both simpler and faster to run.

## The journey

### The FP8 checkpoint is already quantized — use NVIDIA's, not your own

Both checkpoints came from HuggingFace directly, un-gated, without needing an NGC login. `nvidia/Llama-3.1-8B-Instruct-FP8` is a ModelOpt 0.33 export: `F8_E4M3` weights for the Linear layers, BF16 embeddings and layernorms, FP32 per-tensor scales. `nvidia/Llama-3.1-8B-Instruct-NVFP4` is a ModelOpt 0.37 export with `NVFP4` weights packed as `U8` (two 4-bit values per byte), a `group_size=16` quantization and an FP8 KV cache. Both have a `config.json` that looks like a generic Llama model; the quantization lives in the weights and, for NVFP4, in a separate `hf_quant_config.json`.

```
=== FP8 ===
model-00001-of-00002.safetensors  5.00 GB
model-00002-of-00002.safetensors  4.08 GB   total weights ≈ 9.08 GB

=== NVFP4 ===
model-00001-of-00002.safetensors  4.98 GB
model-00002-of-00002.safetensors  1.05 GB   total weights ≈ 6.03 GB
```

The detail worth noticing is that both downloads are un-gated. For a local-first builder this closes the loop started in the first NIM article — you do not need an NGC key, a Meta access form, or a calibration dataset. NVIDIA has already done the PTQ run, pushed it to HuggingFace, and the 8B base fits in a `curl` loop. The slowest part of the setup is the 9 GB download, and even that runs in parallel with the container pull.

### The assertion that tells you your container is too old

The first FP8 build attempt used `nvcr.io/nvidia/tritonserver:25.01-trtllm-python-py3`, which ships TensorRT-LLM 0.17.0.post1. The container log started with a blunt warning:

```
WARNING: Detected NVIDIA GB10 GPU, which may not yet be supported in this version of the container
```

The checkpoint converted in 16 seconds. The engine build ran through graph construction for a minute, then crashed. The salient line in the log, stripped of its backtrace:

```
[TRT-LLM] [I] Compute capability: (12, 1)
[TRT-LLM] [I] SM count: 48
...
terminate called after throwing an instance of 'tensorrt_llm::common::TllmException'
  what():  [TensorRT-LLM][ERROR] Assertion failed: FP8 FMHA cannot be enabled
    except on Ada or Hopper or Blackwell Arch.
```

The assertion is the giveaway. GB10 *is* Blackwell — the GPU identifies itself as compute capability (12, 1). But TRT-LLM 0.17's enumeration of "Blackwell" was written before SM 12.x existed; the code recognises the datacenter B100/B200 parts at SM 10.0 and nothing past that. The assertion fires on a supported architecture because the enumeration is stale. This is a detail no official release note tells you, and the fix — upgrading to Triton `25.12-trtllm-python-py3`, which bundles TensorRT-LLM 1.1.0 — is not discoverable from the stack trace. The warning at container startup *was* the discoverable sign, and the correct reading of it is *"you will hit a wall."* Trust that warning.

### Two engines in a minute each

With Triton 25.12 in play, the build timings collapse. Both engines — FP8 and NVFP4 — land in under 45 seconds of wall-clock from HF checkpoint to loadable `.engine` file, split roughly 16 seconds for the TRT-LLM checkpoint conversion and 27–33 seconds for the `trtllm-build` engine compile. The build log confirms the SM detection is clean this time:

```
[TRT-LLM] [I] Compute capability: (12, 1)
[TRT-LLM] [I] SM count: 48
[TRT-LLM] [W] Failed to infer cluster info for NVIDIA GB10, treat it
              as a L40 node with 121 GB memory.
...
[TRT-LLM] [I] Total time of building all engines: 00:00:32
```

The warning in the middle is the kind of honest-weirdness note that makes the Spark such a recognisable machine. TRT-LLM's auto-parallel planner does not have a GB10 entry in its cluster-info table; it substitutes the closest datacenter GPU it does know about (an L40) for the purposes of parallelism planning. On a single-GPU workload this has zero effect — but it is a reminder that the Spark is still a novel SKU relative to the datacenter muscle memory baked into the tooling.

```bash
# FP8 engine
trtllm-build \
  --checkpoint_dir /ckpt --output_dir /engine \
  --gemm_plugin fp8 \
  --max_batch_size 8 --max_input_len 2048 --max_seq_len 4096 \
  --max_num_tokens 4096 \
  --use_paged_context_fmha enable --use_fp8_context_fmha enable

# NVFP4 engine — swap one flag
trtllm-build \
  --checkpoint_dir /nvfp4-ckpt --output_dir /nvfp4-engine \
  --gemm_plugin nvfp4 \
  --max_batch_size 8 --max_input_len 2048 --max_seq_len 4096 \
  --max_num_tokens 4096 \
  --use_paged_context_fmha enable
```

The artifacts are a single `rank0.engine` file each: **8.6 GB for FP8, 5.7 GB for NVFP4**. The 34% size drop between the two is what the 4-bit quantization directly buys you on disk; the bigger win comes from what it buys you at runtime.

### `trtllm-serve` skips the full Triton scaffolding

The tutorial path for Triton + TRT-LLM is the model-repository ensemble — four sub-models (preprocessing, `tensorrt_llm`, postprocessing, and an ensemble that wires them), each with its own `config.pbtxt`, chained behind `tritonserver --model-repository=...`. That path exists, and it is what you want if you are planning to serve multiple models from one process with Triton's dynamic batching across them. It is also not what this article needed. For a single-model OpenAI-compatible endpoint, TRT-LLM 1.1 ships a newer `trtllm-serve` CLI that swallows the tokenizer, the engine, and the HTTP surface in one command:

```bash
docker run -d --name trtllm-serve-nvfp4 --gpus all -p 8003:8003 \
  -v /home/nvidia/trtllm-work/nvfp4-engine:/engine:ro \
  -v /home/nvidia/models/llama-3.1-8b-instruct-fp8:/tokenizer:ro \
  nvcr.io/nvidia/tritonserver:25.12-trtllm-python-py3 \
  trtllm-serve serve /engine \
    --tokenizer /tokenizer --backend tensorrt \
    --host 0.0.0.0 --port 8003 \
    --max_batch_size 8 --max_num_tokens 4096 --max_seq_len 4096 \
    --kv_cache_free_gpu_memory_fraction 0.4
```

The first time the NVFP4 server launched, `/v1/chat/completions` returned an HTTP 400 with the message *"No chat template found for the given tokenizer and tools."* The NVFP4 HuggingFace repo ships `tokenizer.json` and `tokenizer_config.json`, but the config is missing a `chat_template` field — the Llama-3.1 template was stripped from the quantized release. The fix is to point `--tokenizer` at the FP8 checkpoint directory instead; the vocabulary, tokenizer, and special tokens are identical to the base model (both are ModelOpt exports of the same `meta-llama/Llama-3.1-8B-Instruct`), and the FP8 tokenizer does carry the chat template. The benchmark loads the engine from `nvfp4-engine/` and the tokenizer from `llama-3.1-8b-instruct-fp8/`. This is the kind of cross-wiring that an enterprise DevOps playbook would linting-fail on; for a personal rig it is a one-line fix that earns an article footnote.

### Three stacks, one benchmark

The benchmark harness is intentionally small — about 100 lines of Python, no dependencies outside the standard library, one fixed prompt (*"In one paragraph: what is retrieval-augmented generation and when is it the wrong tool?"*), greedy decode, 200-token ceiling. Two measurements per stack: a streaming serial bench for TTFT and decode rate, and a multi-threaded concurrent bench for aggregate throughput at c ∈ {1, 2, 4, 8}. The three endpoints are all OpenAI-compatible, so the same harness drives all of them:

```
NIM-vLLM-FP8      http://localhost:8000/v1/chat/completions
TRT-LLM-FP8       http://localhost:8003/v1/chat/completions
TRT-LLM-NVFP4     http://localhost:8003/v1/chat/completions   (after swap)
```

The serial numbers:

| stack | TTFT (ms, p50) | decode (tok/s) | wall (s, p50) | engine size |
|---|---:|---:|---:|---:|
| NIM vLLM FP8 | 54.0 | 22.06 | 7.33 | — (container) |
| TRT-LLM FP8 | 46.1 | 24.57 | 6.00 | 8.6 GB |
| TRT-LLM NVFP4 | **30.8** | **38.82** | **5.11** | **5.7 GB** |

And the concurrent aggregate throughput, in tokens/second:

| stack | c=1 | c=2 | c=4 | c=8 |
|---|---:|---:|---:|---:|
| NIM vLLM FP8 | 21.9 | 45.0 | 89.6 | 175.2 |
| TRT-LLM FP8 | 26.9 | 52.8 | 107.6 | 193.5 |
| TRT-LLM NVFP4 | **36.3** | **69.2** | **135.2** | **264.7** |

Two things worth staring at. First, vLLM's continuous batching is real: the NIM number scales from 22 tok/s at c=1 to 175 tok/s at c=8, near-linear. That is the reputational strength of vLLM earning its line. Second, TRT-LLM NVFP4 also scales near-linearly — from 36 to 265 — and it does so from a *higher starting floor*. The two stacks' batching math is comparable; the kernel math is not. NVFP4 wins at every concurrency column.

The delta vs the NIM baseline:

| stack | TTFT | decode | c=8 aggregate |
|---|---:|---:|---:|
| TRT-LLM FP8 | −14.7% | +11.4% | +10.5% |
| TRT-LLM NVFP4 | **−42.9%** | **+76.0%** | **+51.1%** |

The +10-15% column is the one that motivated this article when we started. The −43% / +76% / +51% column is the one that rewrote the thesis mid-session.

## Verification — what success feels like on the DGX Spark

The easiest-to-feel signal is memory. `docker stats` while the NVFP4 server is running returns `2.535GiB / 121.7GiB` — about 2% of unified memory to serve an 8B model at 38 tokens a second. The NIM 8B at idle sits at 11.2 GiB. The difference is not a rounding error; it is the piece of the memory budget that pgvector, a retriever, or the Nsight agent would otherwise have to fight for. On a cluster this would be a cost-per-GPU question; on the Spark it is a *what else fits on this box* question, and NVFP4's answer is "more."

The second signal lands at the client. A 165-token completion that took 7.3 seconds on NIM takes 5.1 seconds on NVFP4. You feel the difference the moment you type a query — the pause between `send` and the first streamed token drops from *noticeable* (54 ms) to *disappears into the scroll* (31 ms). For a Second Brain hitting the endpoint tens or hundreds of times a day, that is the difference between a tool you reach for and a tool you work around.

The third signal is the engine-build time itself. 32 seconds to recompile an 8B engine is fast enough that iterating on quantization settings is a viable activity, not a scheduled task. You can try FP8, try NVFP4, try different `max_batch_size` and KV-cache budgets in the span of a coffee. That was not the case when this work started — the 25.01 container's broken build wasted more wall-clock than the entire 25.12 build pipeline consumed.

## Gotchas and honest friction

The Blackwell compatibility issue burned a full cycle before we knew to pull a newer image. The startup warning *"may not yet be supported"* is the sort of thing easy to dismiss; in hindsight it was the single most important line in the early logs. A less charitable reading is that TRT-LLM 0.17 should not advertise `--gemm_plugin nvfp4` as an option if it will not build with it, but the reality of deep-learning tooling is that matrix compatibility is a moving target. The practical rule: *when the container warns about your GPU, believe it, and find a newer container.* Triton 25.12 was a clean pull at the time of writing; by the time you read this there will likely be a 26.x that is fresher still.

The chat-template mismatch on NVFP4 was the second gotcha — subtle because it does not fail the server startup, only the first HTTP request. The HF release for the quantized model trimmed the template out of `tokenizer_config.json`. The fix (point `--tokenizer` at the un-quantized or FP8-quantized dir) is benign because the tokenizer is a property of the *base* model, not the quantization. But the lesson is a design one: the benchmark's assumption that tokenizer and engine travel together is wrong in the ModelOpt-export world. Wire the tokenizer from the closest complete repo, not the quantized one.

The "treat it as a L40 node with 121 GB memory" warning is harmless, but it is the kind of detail worth flagging to a reader who may be about to ask *"can I tensor-parallel this across two GB10s?"* The answer for now is that the auto-parallel tooling does not model the Spark's topology — it picks an analogue. For single-GPU work this is noise. For future multi-Spark clusters it will not be.

Lastly: disk and container weight. Pulling `25.12-trtllm-python-py3` is a **34.6 GB** image download. The NVIDIA TRT-LLM source clone is another ~400 MB. Two 8B checkpoints are ~15 GB. Two engine builds are ~14 GB more. A full walk of this article uses roughly 60 GB of disk that was not there before, and most of that stays resident because iterating on engine settings means rebuilding. This is a real cost on a personal rig, but the 3.3 TB of free space the Spark ships with swallows it comfortably. It is worth mentioning only because the convenience of NIM comes with a much smaller footprint: one pull, one container, one cache.

## What this unlocks

The immediate win is a local 8B endpoint that is materially faster than NIM for a single-user workload and takes a quarter of the memory. That is the foundation that the Second Brain arc will now build on — every retrieval-augmented query cuts wall-clock by 30%, every concurrent multi-client workload scales from 175 to 265 tok/s aggregate without more hardware, and the freed memory makes room for a richer retrieval chain.

Three concrete things a reader can pursue this week from here. First, swap in a larger model and measure whether NVFP4's win holds at scale — Nemotron-Super-49B and Llama 3.3 70B both have NVIDIA-FP4 variants on HuggingFace, and the Spark's 121 GiB unified memory says both of those fit. Second, stand up a second `trtllm-serve` on a different port and stack a generator + critic + a small reranker engine on the same GPU; with NVFP4's 2.5 GiB per model, the memory math finally works for a classic critic-driven loop. Third, wire the NVFP4 endpoint behind the existing Second Brain RAG pipeline (the one [built across articles 3-9](/articles/one-substrate-three-apps/)) by changing one `OPENAI_BASE_URL` environment variable and re-running the qrels benchmark — the grounding behavior may shift, and that becomes a measurable next article on its own.

Sibling articles will cover the same `Triton + TensorRT-LLM` product surface with two different optimization profiles: *ingest throughput* for the LLM Wiki arc (batched, large-context, many documents per second) and *agent-loop latency* for the Autoresearch arc (the critic NIM sitting next to the training driver). The three profiles will share this engine-build tooling but diverge on `max_batch_size`, `max_input_len`, and the KV-cache budget — same stack, three specializations.

## Closing — state of the Second Brain

**Second Brain now:** has a faster brain and more free memory. The 8B generator that answers queries dropped from 7.3 seconds end-to-end to 5.1 seconds, resident memory fell from 11.2 GiB to 2.5 GiB, and the Spark's Blackwell-native FP4 kernel is what made both numbers possible. Next up in this track: **LoRA on your own Q&A pairs** — personalizing the generator on whatever corpus the Second Brain is built for, and measuring whether a cheap adapter beats a bigger base.

The meta-lesson is the one worth carrying. NIM is not a lazy abstraction — it is a deliberately chosen tuning layer that ships NVIDIA's best FP8 recipe for the Spark. Dropping below it is only worth it for things NIM does not do. The +10% FP8 win is not that thing. The **76% NVFP4 win** is — and it exists specifically because Blackwell's SM 12.1 executes 4-bit math in hardware, and the layer above NIM has not yet wired it through. On a personal rig, on one machine, that is exactly the kind of capability worth descending one layer to reach. The rest of the Second Brain arc is going to keep reaching.
