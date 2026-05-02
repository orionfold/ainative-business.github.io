---
title: "Looking Beyond Spark — KV-Cache Arithmetic at Inference"
date: 2026-04-30
author: Manav Sehgal
product: TensorRT-LLM
stage: foundations
also_stages: [inference, deployment]
difficulty: intermediate
time_required: "~22 minute read"
hardware: "NVIDIA DGX Spark"
tags: [inference, kv-cache, paged-attention, fp8, gqa, h100, h200, b200, dgx-spark]
summary: "The serving memory bill is not weights. It's KV cache, and KV scales with concurrent users × context length, not parameters. Same four bills as training; different weights. A 70B at 32 users × 16k context wants 168 GB just for KV — and the Spark teaches you the per-token math."
signature: KvCacheArithmetic
series: Looking Beyond Spark
fieldkit_modules: [capabilities]
---

You cannot serve a 100B-class model to real traffic on a DGX Spark. Even FP8-quantized, the weights alone consume 100 GB of the Spark's 128 GB unified envelope, and that's before a single user has sent a single token through it. *That* part of the arithmetic is identical to the [fine-tuning sizing piece](/articles/gpu-sizing-math-for-fine-tuning/) — and just as much beside the point.

The harder, more useful question is *how the memory bill rearranges itself the moment you stop training and start serving*. Three of the four memory bills you paid during fine-tuning vanish — gradients, optimizer state, half the activation bill all go to zero the second the backward pass goes away. In their place, one new bill grows from negligible to dominant: the **KV cache**, the per-token attention state every concurrent user accumulates as their conversation lengthens. And unlike training memory, which scales with parameter count, the KV bill scales with **concurrent users × context length**. A model that fit comfortably for one user at 4k context can OOM the same hardware four hours later when it has 128 sessions open at 32k context each — without one parameter changing.

This article walks the KV-cache arithmetic end-to-end and pins it to concrete hardware asks for serving 70B and 100B-class models. The Spark appears in this story not as the rig that serves a frontier model — it obviously won't — but as the rig that lets you *measure* per-token KV cost on an 8B serve, then multiply. A TRT-LLM NVFP4 run on this machine pulled [38.8 tokens/second of decode at 2.5 GiB resident](/articles/trtllm-and-triton-on-spark/) — and inside that 2.5 GB lives a paged KV cache whose size is the same equation that decides whether your 70B serves 32 or 256 concurrent users on a rented H200. Same math. Different coefficients.

## Why this matters for a personal AI builder

The Spark's lesson for a personal AI builder is the same on serving as it was on training: *prototype the workload at a scale your desk can afford, then own the math that scales it up*. Get the serving math right and you can answer *"to host my fine-tuned 70B for 32 colleagues at 16k context, what do I rent?"* on a napkin in two minutes. Get it wrong and you book an H100 instance that OOMs at user 18, or — more expensively — overprovision an 8× H200 node when one would have done.

Owning this arithmetic is also what lets you read a serving-stack benchmark with eyes open. A vendor benchmark that shows *"X tok/s aggregate at concurrency 64"* tells you almost nothing about *your* workload until you back out the per-user context length and the KV precision they used. The arithmetic in this article is that decoder ring. The Spark is where you measure the constants; the formula is what travels.

## Where the memory actually goes — at inference

Every LLM inference server pays four memory bills, just like fine-tuning. The line items survived; the relative weights inverted.

1. **Model weights.** Same as training — parameters × bytes-per-parameter. BF16 is 2 bytes; FP8 is 1; NVFP4 is ~0.5. Frozen for the lifetime of the server.
2. **Activations.** Smaller than at training because there's no backward pass to feed; only the prefill activations need to live long enough for the first token to come out, and decode activations are sized by *one* token at a time per request.
3. **KV cache.** **The new dominant bill.** Per-token attention state: every layer caches the K and V projections for every token already seen, for every active request, so subsequent decode steps don't have to recompute attention over the prefix. This is the term that makes serving hard.
4. **Overhead and workspace.** CUDA-graph buffers, NCCL workspace, framework scratch — typically 1–4 GB, model-specific.

The KV equation is short and load-bearing:

```
KV bytes = 2 × n_layers × n_kv_heads × head_dim × seq_len × batch × precision
                                                              ↑           ↑
                                            sum across all      bytes per
                                            active requests     stored value
                                            (their lengths)
```

The factor of 2 is K and V — both stored. The `seq_len × batch` term is doing the work that scares you: every active request contributes its current token count, and every new token added to any request grows the bill. There is no batch-axis trick to amortize this — each user's context is uniquely theirs.

<figure class="fn-diagram" aria-label="KV cache memory for Llama 3.1 70B as a function of concurrent users and average context length, in FP16 and FP8. At one user and 4k context, KV is under 2 GB and trivial. At 32 users and 4k context, FP16 KV reaches 42 GB and fits a single H100. At 32 users and 16k context, FP16 KV is 168 GB and needs an H200 or two H100s. At 128 users and 8k context, FP16 KV is 336 GB and the workload becomes multi-GPU. At 32 users and 128k context, FP16 KV is 1.3 TB and the workload becomes multi-node. FP8 KV halves every number — the same shape, half the slope.">
  <svg viewBox="0 0 900 460" role="img" aria-label="KV cache memory for Llama 3.1 70B across concurrency and context-length tiers, in FP16 and FP8, with hardware tier annotations from one H100 80GB to multi-node." preserveAspectRatio="xMidYMid meet">
    <defs>
      <linearGradient id="d-kv-lane" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%"   stop-color="var(--svg-accent-blue)" stop-opacity="0.03"/>
        <stop offset="50%"  stop-color="var(--svg-accent-blue)" stop-opacity="0.10"/>
        <stop offset="100%" stop-color="var(--svg-accent-blue)" stop-opacity="0.03"/>
      </linearGradient>
      <linearGradient id="d-kv-trivial-grad" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%"   stop-color="var(--svg-accent-green)" stop-opacity="0.30"/>
        <stop offset="100%" stop-color="var(--svg-accent-green)" stop-opacity="0.08"/>
      </linearGradient>
      <linearGradient id="d-kv-h100-grad" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%"   stop-color="var(--svg-accent-cyan)" stop-opacity="0.28"/>
        <stop offset="100%" stop-color="var(--svg-accent-cyan)" stop-opacity="0.08"/>
      </linearGradient>
      <linearGradient id="d-kv-h200-grad" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%"   stop-color="var(--color-primary)" stop-opacity="0.38"/>
        <stop offset="100%" stop-color="var(--color-primary)" stop-opacity="0.10"/>
      </linearGradient>
      <linearGradient id="d-kv-multi-grad" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%"   stop-color="var(--svg-accent-orange)" stop-opacity="0.28"/>
        <stop offset="100%" stop-color="var(--svg-accent-orange)" stop-opacity="0.08"/>
      </linearGradient>
      <linearGradient id="d-kv-node-grad" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%"   stop-color="var(--svg-accent-red)" stop-opacity="0.28"/>
        <stop offset="100%" stop-color="var(--svg-accent-red)" stop-opacity="0.08"/>
      </linearGradient>
    </defs>
    <rect x="30" y="80" width="840" height="320" rx="10" fill="url(#d-kv-lane)" stroke="none"/>
    <g class="fn-diagram__edges">
      <line x1="240" y1="100" x2="240" y2="380" stroke="var(--color-text-dim)" stroke-width="0.5" stroke-dasharray="2 3"/>
      <line x1="320" y1="100" x2="320" y2="380" stroke="var(--color-text-dim)" stroke-width="0.5" stroke-dasharray="2 3"/>
      <line x1="450" y1="100" x2="450" y2="380" stroke="var(--color-text-dim)" stroke-width="0.5" stroke-dasharray="2 3"/>
      <line x1="640" y1="100" x2="640" y2="380" stroke="var(--color-text-dim)" stroke-width="0.5" stroke-dasharray="2 3"/>
      <line x1="780" y1="100" x2="780" y2="380" stroke="var(--color-text-dim)" stroke-width="0.5" stroke-dasharray="2 3"/>
    </g>
    <g class="fn-diagram__nodes">
      <rect class="fn-diagram__node" x="240" y="118" width="6" height="34" rx="3" fill="url(#d-kv-trivial-grad)" stroke="var(--svg-accent-green)" stroke-width="1"/>
      <rect class="fn-diagram__node" x="240" y="168" width="80" height="34" rx="3" fill="url(#d-kv-h100-grad)" stroke="var(--svg-accent-cyan)" stroke-width="1"/>
      <rect class="fn-diagram__node fn-diagram__node--accent" x="240" y="218" width="210" height="34" rx="3" style="fill: url(#d-kv-h200-grad)"/>
      <rect class="fn-diagram__node" x="240" y="268" width="400" height="34" rx="3" fill="url(#d-kv-multi-grad)" stroke="var(--svg-accent-orange)" stroke-width="1"/>
      <rect class="fn-diagram__node" x="240" y="318" width="540" height="34" rx="3" fill="url(#d-kv-node-grad)" stroke="var(--svg-accent-red)" stroke-width="1"/>
    </g>
    <g class="fn-diagram__labels">
      <text class="fn-diagram__label fn-diagram__label--display" x="230" y="139" text-anchor="end">1 × 4k</text>
      <text class="fn-diagram__label fn-diagram__label--mono fn-diagram__label--muted" x="230" y="153" text-anchor="end">interactive single-user</text>
      <text class="fn-diagram__label fn-diagram__label--display" x="230" y="189" text-anchor="end">32 × 4k</text>
      <text class="fn-diagram__label fn-diagram__label--mono fn-diagram__label--muted" x="230" y="203" text-anchor="end">small team chat</text>
      <text class="fn-diagram__label fn-diagram__label--display" x="230" y="239" text-anchor="end">32 × 16k</text>
      <text class="fn-diagram__label fn-diagram__label--mono fn-diagram__label--muted" x="230" y="253" text-anchor="end">RAG / coding agent</text>
      <text class="fn-diagram__label fn-diagram__label--display" x="230" y="289" text-anchor="end">128 × 8k</text>
      <text class="fn-diagram__label fn-diagram__label--mono fn-diagram__label--muted" x="230" y="303" text-anchor="end">small product</text>
      <text class="fn-diagram__label fn-diagram__label--display" x="230" y="339" text-anchor="end">32 × 128k</text>
      <text class="fn-diagram__label fn-diagram__label--mono fn-diagram__label--muted" x="230" y="353" text-anchor="end">long-doc analysis</text>
      <text class="fn-diagram__label fn-diagram__label--display" x="790" y="139" text-anchor="start">~1.3 GB</text>
      <text class="fn-diagram__label fn-diagram__label--mono fn-diagram__label--muted" x="790" y="153" text-anchor="start">trivial · 1× H100</text>
      <text class="fn-diagram__label fn-diagram__label--display" x="790" y="189" text-anchor="start">~42 GB</text>
      <text class="fn-diagram__label fn-diagram__label--mono fn-diagram__label--muted" x="790" y="203" text-anchor="start">1× H100 80 GB</text>
      <text class="fn-diagram__label fn-diagram__label--display" x="790" y="239" text-anchor="start">~168 GB</text>
      <text class="fn-diagram__label fn-diagram__label--mono fn-diagram__label--muted" x="790" y="253" text-anchor="start">1× H200 · 2× H100</text>
      <text class="fn-diagram__label fn-diagram__label--display" x="790" y="289" text-anchor="start">~336 GB</text>
      <text class="fn-diagram__label fn-diagram__label--mono fn-diagram__label--muted" x="790" y="303" text-anchor="start">4× H100 / 2× H200</text>
      <text class="fn-diagram__label fn-diagram__label--display" x="790" y="339" text-anchor="start">~1.3 TB</text>
      <text class="fn-diagram__label fn-diagram__label--mono fn-diagram__label--muted" x="790" y="353" text-anchor="start">multi-node</text>
      <text class="fn-diagram__label fn-diagram__label--mono fn-diagram__label--muted" x="450" y="105" text-anchor="middle">FP16 KV cache for Llama 3.1 70B · 80 layers · 8 KV heads · head_dim 128 · weights ~140 GB BF16 / 70 GB FP8 (separate budget)</text>
      <text class="fn-diagram__label fn-diagram__label--mono fn-diagram__label--muted" x="450" y="395" text-anchor="middle">FP8 KV halves every bar — same shape, half the slope</text>
    </g>
  </svg>
  <figcaption>KV cache, not weights, is the term that decides which hardware tier you need. Concurrent users × context length is the dial; precision is the discount.</figcaption>
</figure>

To make this concrete, walk Llama 3.1 70B end-to-end. The architecture: 80 transformer layers, 64 attention heads but only **8 KV heads** (the GQA reduction), head dimension 128, BF16 by default, FP8 KV cache an option.

Per-token KV at FP16: `2 × 80 × 8 × 128 × 2 = 327,680 bytes`. Round to **320 KB per token, per request**. At FP8 it's 160 KB. That's the constant you multiply.

Now scale it:

| Concurrency | Avg context | KV (FP16) | KV (FP8) | Hardware tier (KV alone) |
|---|---|---|---|---|
| 1 user | 4k tokens | 1.3 GB | 0.65 GB | trivial — fits any single GPU |
| 32 users | 4k tokens | 42 GB | 21 GB | 1× H100 80 GB |
| 32 users | 16k tokens | 168 GB | 84 GB | 1× H200 141 GB or 2× H100 |
| 128 users | 8k tokens | 336 GB | 168 GB | 4× H100 80 GB or 2× H200 |
| 32 users | 128k tokens | 1.3 TB | 656 GB | multi-node, no other path |

Weights add another ~140 GB at BF16 or ~70 GB at FP8 — a *separate*, fixed bill. The cells above are KV alone. For total memory, add the weights row to whichever cell you land in. At "32 users × 16k context, FP16 KV", a node with 168 GB of KV plus 70 GB of FP8 weights wants ~240 GB of GPU memory, which lands cleanly on a 2× H200 setup or an 8× H100 with KV-cache spread across ranks.

The 8B at the top of the same family — 32 layers, 8 KV heads, head_dim 128 — works out to **128 KB/token (FP16)** or 64 KB/token (FP8), four times less per user. The 405B at the other end — 126 layers, still 8 KV heads with GQA-16 — works out to **504 KB/token (FP16)**. Notice what *didn't* scale: the KV-head count is **constant at 8 across the entire Llama 3.1 family**. That's the load-bearing decision Meta made for serving — and the reason a 405B is "only" 4× the KV-per-token of an 8B, not 50×.

## Verification — reading the Spark back into the formula

The Spark's TRT-LLM 8B serve in [`trtllm-and-triton-on-spark`](/articles/trtllm-and-triton-on-spark/) was built with the exact knobs the math above predicts you'd reach for:

```
trtllm-build \
  --max_batch_size 8 --max_input_len 2048 --max_seq_len 4096 \
  --max_num_tokens 4096 \
  --use_paged_context_fmha enable --use_fp8_context_fmha enable
```

Read those flags as the KV-cache budget in disguise. `--max_batch_size 8` × `--max_seq_len 4096` × 64 KB/token (FP8 KV) × `2` (K and V already implicit in the per-token figure) is the engine declaring an 8 × 4096 × 64 KB = **2 GB** ceiling on KV, give or take rounding. That number is small enough that it almost vanishes inside the 2.5 GiB resident measurement — which is why the article didn't break it out, and why a single-user benchmark on the Spark looks deceptively comfortable. Crank `--max_batch_size` to 128 and `--max_seq_len` to 32768 and the engine will refuse the build, because 128 × 32768 × 64 KB = **256 GB** of KV — twice the Spark's entire memory.

The NIM container's behavior in [`nim-first-inference-dgx-spark`](/articles/nim-first-inference-dgx-spark/) tells the same story from a different angle. The `NIM_GPU_MEM_FRACTION=0.5` default felt conservative for a single user, and on single-stream the experiment confirmed it — bumping to 0.8 changed throughput by less than the noise floor. *"Don't tune what isn't the bottleneck"* was the right read for one caller. But that 50% headroom isn't conservative; it's the **KV reservation pool** for the concurrent requests that single-stream benchmarks don't generate. NIM's vLLM uses PagedAttention to allocate KV blocks on demand from that pool — fine when one user is talking, the difference between 4 concurrent users and 40 when many are.

The two articles together gave the Spark its inference voice: **8B at FP8, single-user, ~52 ms TTFT, ~25 tok/s decode, KV is a rounding error.** That whole picture is one corner of the table above. Walk to a different corner and the dominant term changes; the equation stays.

## Tradeoffs and surprises

**GQA is doing more for serving than for training.** Llama 3.1's 8 KV heads (regardless of model size) is a deliberate architectural decision aimed at exactly this serving math. A pre-GQA model with `n_kv_heads = n_attention_heads` would have 8× the KV-cache cost at 70B — making the 32 user × 16k context cell jump from 168 GB to 1.3 TB on the same model. When you read a model card, the KV-head count is the line that decides whether you serve it on one GPU or one node. Mistral 7B, Qwen 2.5 72B, DeepSeek-V3, all the modern serving-friendly models have aggressive GQA for the same reason.

**FP8 KV is a free 2× concurrency budget.** The accuracy trade is small for chat-style workloads — modern serving stacks land within a few tenths of a perplexity point on standard benchmarks — and the budget impact is exactly half of FP16. TRT-LLM's `--use_fp8_context_fmha enable` flag is doing this on the Spark already; vLLM exposes it as `kv_cache_dtype="fp8"`. If your math says you're 30% over the KV budget on the next concurrency tier, FP8 KV moves the line without any other change.

**Prefill and decode are different workloads — the H100/H200 spread is much bigger on decode.** Prefill is compute-bound: dense GEMMs against the full prompt. Decode is memory-bandwidth-bound: every step reads the KV cache plus the model weights to produce one token. The H200's 4.8 TB/s HBM3e bandwidth (vs the H100's 3.35 TB/s) is a ~40% theoretical decode lift on the same model. That translates to ~25–35% real-world tok/s improvement on long-context decode that a serving benchmark on prefill-dominated prompts will quietly hide. If your workload is RAG (long retrieved context, short generation) your prefill arithmetic drives the H100/H200 choice; if your workload is creative generation (short prompt, long completion) decode arithmetic drives it.

**PagedAttention turned the KV cache from a brick into a heap.** The pre-PagedAttention world reserved a fixed contiguous KV buffer per request, sized for the worst case — `max_seq_len` for everyone, even users whose context was 200 tokens. A 32-user serve at `max_seq_len=32k` reserved KV as if every user was at 32k, leaving ~95% of the cache idle. PagedAttention (vLLM's default, TRT-LLM's `--use_paged_context_fmha enable`) allocates KV in 16-token blocks on demand, so the 200-token user uses 200 tokens of KV, full stop. Effective concurrency at the same hardware budget went up roughly 2–4× the day this landed. The arithmetic in this article assumes paged KV; without it, every cell in the table doubles.

**Speculative decoding adds a KV bill you forgot about.** The draft model — typically 1B-class for a 70B target — has its own KV cache. It's small per-token (8 layers × 4 KV heads × 64 head_dim × 2 bytes = ~4 KB/token at FP16), but it's there, and at high concurrency it's not nothing. Worth budgeting if you're considering Llama 3.1 8B as a draft for 70B.

**Continuous batching is the other half of the heap.** PagedAttention manages KV memory; continuous batching (also called in-flight batching) manages compute. A request's prefill step can join a batch that already has decode steps for other requests in flight, so the GPU is never waiting for a batch to "complete" before starting the next one. TRT-LLM and vLLM both implement this; SGLang adds a more aggressive variant with prefix sharing. On a serve with high concurrency variance — chat traffic, agent loops — these features are the difference between 30% utilization and 70%.

## What this unlocks

Three things you can do this week with this math in your head.

**A serving sizing sheet.** Rows = model (8B, 49B, 70B, 100B, 405B); columns = concurrency tier (1, 32, 128, 1024); cells = KV bytes at the tier's typical context (4k for chat, 16k for RAG, 128k for long-doc). Each cell is the equation above. Add the weights row underneath at FP8 and BF16. You now have a one-page artifact that converts a product manager's *"can we host this for 200 users?"* into a specific GPU and instance type, in seconds. The same way [LBS #1's training sizing sheet](/articles/gpu-sizing-math-for-fine-tuning/) did for fine-tuning, but for the *operating* cost rather than the *training* cost.

**An informed serving-stack choice.** vLLM, TRT-LLM, NIM, SGLang, and LMDeploy all serve transformers; the differences live in their KV-cache management. vLLM has the best baseline PagedAttention implementation and the widest model support. TRT-LLM wins on Blackwell (NVFP4 path) and on aggressive prefix sharing for repeated-prompt workloads. NIM is whichever of the two NVIDIA bundled for your model. SGLang's `RadixAttention` shares KV across requests with overlapping prefixes — a 30–40% cache hit rate is typical on RAG workloads, and that drops your effective KV bill by the same factor. *"Which serving stack should I use?"* has no general answer; *"which serving stack matches the KV pattern of my workload?"* has a specific one.

**A better OOM filter at serving time.** When a serving deployment dies in production, the wall-clock location is a fingerprint just like at training. Dies during a long completion → KV cache filled; cap context or precision. Dies under a concurrency spike → request queue overflowed KV pool; size pool larger or shed load. Dies on prefill of a single long prompt → engine's `max_input_len` ceiling; rebuild engine. Dies at startup with weights loaded → workspace + KV-pool reservation exceeded total memory; the math at build time was wrong. *Same kind of fingerprint table as training, different bills.* The hour you save not bisecting config is paid for by knowing which bill overran.

## Closing

The DGX Spark's role at inference is the same as at training — a 128 GB envelope inside which a personal AI builder learns, in a form they can run on their desk, the equations that scale to anything they will ever rent. The 2.5 GB of resident memory for an 8B at FP8 single-user, and the 1.3 TB of KV cache for a 70B serving 32 users at 128k context, are the same equation with different coefficients. One fits in a personal machine and one fits in a multi-node DGX H200 cluster. The math is fixed; the hardware is negotiable. The tax for not owning the math is paid in over-provisioned cloud bills and surprise OOMs.

Next in this *Looking Beyond Spark* series: **disaggregated prefill and decode at frontier scale** — when prefill becomes compute-bound on H100s and decode becomes bandwidth-bound on H200s, the modern serving topology splits the two workloads across different hardware in the same rack. The math we just walked is the input to that decision; the system that consumes it is the next thing the Spark can teach you in miniature, even when the rack itself is not on your desk.
