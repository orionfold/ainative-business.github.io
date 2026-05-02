---
title: "Looking Beyond Spark — Fine-Tuning a 100B Nemotron"
date: 2026-04-23
author: Manav Sehgal
product: Foundation
stage: foundations
also_stages: [fine-tuning]
difficulty: intermediate
time_required: "~25 minute read"
hardware: "NVIDIA DGX Spark"
tags: [fine-tuning, memory, sizing, lora, qlora, fsdp, nemotron, h100, h200, dgx-spark]
summary: "A working answer to: how many GPUs to fine-tune a 100B Nemotron? Three methods, three memory footprints — full FT ≈ 1.6 TB needs 24× H100; LoRA ≈ 250 GB fits 8× H100; QLoRA ≈ 65 GB fits 1× H200. The Spark's 3B LoRA teaches the math."
signature: FineTuneMemoryMath
series: Looking Beyond Spark
fieldkit_modules: [capabilities]
---

You cannot fine-tune a 100B-parameter Nemotron on a DGX Spark. The Spark's 128 GB of unified memory runs out twenty times over before the optimizer has even allocated its state buffers. That is the first sentence of this article, and I am going to spend the rest of it *not* making it the point.

The harder question — the one you should actually care about — is *how many GPUs, of what type, would you actually need?* That one has a specific, boring, defensible answer, and it is the difference between a $500 weekend on a rented H100 node and a $20,000 monthly bill you spend the rest of the quarter defending. Owning the math is cheaper than owning the hardware.

This article works the arithmetic end-to-end for a hypothetical 100B Nemotron fine-tune across three methods — full BF16 fine-tune, LoRA, and QLoRA — and pins each to a concrete GPU count. The Spark appears in this story not as the rig that runs the training, but as the rig that lets you *see* the memory equation at a scale your desk can actually afford. A 3B LoRA peaked at ~20 GB of GPU memory on the Spark, measured in [`lora-on-your-own-qa-pairs`](/articles/lora-on-your-own-qa-pairs/). A 100B full fine-tune peaks at ~1.6 TB, arithmetically inevitable. Those are the same equation. You cannot learn the shape of the cost space by reading model cards on HuggingFace. You learn it by running a small fine-tune on your desk and asking where the extra zeros come from.

## Why this matters for a personal AI builder

The Spark's uber move for a personal AI builder is not that it will train a frontier model — it obviously won't — but that it lets you *prototype the same workloads a frontier-scale run would use, at a scale your desk can afford*. You write the same `trl` / `peft` code you'd write for an 8× H100 node. You import the same `transformers`. You hit the same memory-shape surprises. Then you multiply.

Sizing math is the bridge between "what I can do on my machine" and "what it would cost to do it at the scale I actually need." Get it wrong and you either rent a cluster you don't need, or — worse — book one that OOMs on the first epoch and hands back a bill for a run that never finished. A power user who owns this math can look at *"fine-tune 100B Nemotron"* and sketch a credible hardware ask on a napkin in ninety seconds. That's the piece of independence this article is trying to buy.

## Where the memory actually goes

Every LLM fine-tune, whatever the method, pays four memory bills simultaneously. They scale differently with model size and with which parameters are trainable, which is the only reason the three methods produce such wildly different footprints at 100B.

1. **Model weights.** Parameters × bytes-per-parameter. BF16 is 2 bytes; INT8 is 1; NF4 (QLoRA's 4-bit format) is ~0.5.
2. **Gradients.** Same size as trainable weights, same precision. Frozen weights contribute zero — this is the whole point of LoRA.
3. **Optimizer state.** Adam / AdamW keeps two fp32 moments (momentum + variance) per trainable parameter, plus a fp32 master-weight copy when using mixed precision. That's ~12 bytes per *trainable* parameter, independent of the weight precision. This is the single biggest line in a full fine-tune, and the reason LoRA moves the needle.
4. **Activations.** What the forward pass computes for the backward pass to consume. Scales with batch × sequence × hidden × layers — not parameter count, despite how often people approximate it that way. Activation checkpointing halves this bill at a ~30% compute tax.

The canonical figure for a full BF16 fine-tune with Adam and mixed precision is **~16 bytes per parameter for state** (2 weights + 2 gradients + 12 optimizer) plus a variable activation budget on top. At 100B that is 1.6 TB before a single token of activation lands.

<figure class="fn-diagram" aria-label="Three methods for fine-tuning a 100B Nemotron model, drawn to scale by peak GPU memory. Full BF16 fine-tune with Adam: approximately 1,600 gigabytes, needs 24 H100 80GB GPUs with FSDP sharding. LoRA rank 16 across all linear layers: approximately 250 gigabytes, fits on 8 H100 80GB GPUs with ZeRO-3. QLoRA with NF4 4-bit quantized base: approximately 65 gigabytes, fits on a single H200 141GB GPU. A Spark anchor line at the bottom records the 3 billion parameter LoRA on 128GB unified memory peaking at about 20GB — same four memory bills, 1 over 250 times the scale.">
  <svg viewBox="0 0 900 460" role="img" aria-label="Three fine-tuning methods for a 100B Nemotron compared by peak GPU memory: Full FT 1,600GB on 24×H100, LoRA 250GB on 8×H100, QLoRA 65GB on one H200. Spark 3B LoRA anchor at 20GB." preserveAspectRatio="xMidYMid meet">
    <defs>
      <linearGradient id="d100-lane" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%"   stop-color="var(--svg-accent-blue)" stop-opacity="0.03"/>
        <stop offset="50%"  stop-color="var(--svg-accent-blue)" stop-opacity="0.10"/>
        <stop offset="100%" stop-color="var(--svg-accent-blue)" stop-opacity="0.03"/>
      </linearGradient>
      <linearGradient id="d100-full-grad" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%"   stop-color="var(--svg-accent-red)" stop-opacity="0.28"/>
        <stop offset="100%" stop-color="var(--svg-accent-red)" stop-opacity="0.08"/>
      </linearGradient>
      <linearGradient id="d100-lora-grad" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%"   stop-color="var(--svg-accent-orange)" stop-opacity="0.28"/>
        <stop offset="100%" stop-color="var(--svg-accent-orange)" stop-opacity="0.08"/>
      </linearGradient>
      <linearGradient id="d100-qlora-grad" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%"   stop-color="var(--color-primary)" stop-opacity="0.38"/>
        <stop offset="100%" stop-color="var(--color-primary)" stop-opacity="0.10"/>
      </linearGradient>
    </defs>
    <rect x="30" y="90" width="840" height="260" rx="10" fill="url(#d100-lane)" stroke="none"/>
    <g class="fn-diagram__edges">
      <line x1="223" y1="110" x2="223" y2="330" stroke="var(--color-text-dim)" stroke-width="0.5" stroke-dasharray="2 3"/>
      <line x1="289" y1="110" x2="289" y2="330" stroke="var(--color-text-dim)" stroke-width="0.5" stroke-dasharray="2 3"/>
      <line x1="440" y1="110" x2="440" y2="330" stroke="var(--color-text-dim)" stroke-width="0.5" stroke-dasharray="2 3"/>
      <line x1="770" y1="110" x2="770" y2="330" stroke="var(--color-text-dim)" stroke-width="0.5" stroke-dasharray="2 3"/>
    </g>
    <g class="fn-diagram__nodes">
      <rect class="fn-diagram__node" x="200" y="128" width="570" height="40" rx="5" fill="url(#d100-full-grad)" stroke="var(--color-text-muted)" stroke-width="1"/>
      <rect class="fn-diagram__node" x="200" y="208" width="89" height="40" rx="5" fill="url(#d100-lora-grad)" stroke="var(--color-text-muted)" stroke-width="1"/>
      <rect class="fn-diagram__node fn-diagram__node--accent" x="200" y="288" width="23" height="40" rx="5" style="fill: url(#d100-qlora-grad)"/>
    </g>
    <g class="fn-diagram__labels">
      <text class="fn-diagram__label fn-diagram__label--display" x="190" y="153" text-anchor="end">Full FT</text>
      <text class="fn-diagram__label fn-diagram__label--mono fn-diagram__label--muted" x="190" y="170" text-anchor="end">bf16 + Adam</text>
      <text class="fn-diagram__label fn-diagram__label--display" x="190" y="233" text-anchor="end">LoRA</text>
      <text class="fn-diagram__label fn-diagram__label--mono fn-diagram__label--muted" x="190" y="250" text-anchor="end">rank 16 · all linears</text>
      <text class="fn-diagram__label fn-diagram__label--display" x="190" y="313" text-anchor="end">QLoRA</text>
      <text class="fn-diagram__label fn-diagram__label--mono fn-diagram__label--muted" x="190" y="330" text-anchor="end">NF4 base · rank 16</text>
      <text class="fn-diagram__label fn-diagram__label--display" x="780" y="153" text-anchor="start">~1,600 GB</text>
      <text class="fn-diagram__label fn-diagram__label--mono fn-diagram__label--muted" x="780" y="170" text-anchor="start">→ 24× H100 80GB · FSDP</text>
      <text class="fn-diagram__label fn-diagram__label--display" x="299" y="233" text-anchor="start">~250 GB</text>
      <text class="fn-diagram__label fn-diagram__label--mono fn-diagram__label--muted" x="299" y="250" text-anchor="start">→ 8× H100 80GB · ZeRO-3</text>
      <text class="fn-diagram__label fn-diagram__label--display" x="233" y="313" text-anchor="start">~65 GB</text>
      <text class="fn-diagram__label fn-diagram__label--mono fn-diagram__label--muted" x="233" y="330" text-anchor="start">→ 1× H200 141GB · no shard</text>
      <text class="fn-diagram__label fn-diagram__label--mono" x="210" y="152" text-anchor="start" fill="var(--color-text-muted)">weights · grads · optimizer · activations</text>
    </g>
    <g class="fn-diagram__annotations">
      <text class="fn-diagram__label fn-diagram__label--accent" x="30" y="60" text-anchor="start">THE 100B NEMOTRON FINE-TUNE, THREE WAYS</text>
      <text class="fn-diagram__label fn-diagram__label--mono fn-diagram__label--muted" x="30" y="80" text-anchor="start">peak GPU memory by method · all at 100B params · bf16 + activation checkpointing</text>
      <text class="fn-diagram__annotation" x="223" y="105" text-anchor="middle">1× 80GB</text>
      <text class="fn-diagram__annotation" x="440" y="105" text-anchor="middle">8× 80GB = 640</text>
      <text class="fn-diagram__annotation" x="770" y="105" text-anchor="middle">16× 80GB = 1280</text>
      <line x1="30" y1="365" x2="870" y2="365" stroke="var(--color-text-dim)" stroke-width="0.5" stroke-dasharray="2 3"/>
      <text class="fn-diagram__label fn-diagram__label--accent" x="30" y="395" text-anchor="start">SPARK ANCHOR — WHERE THE MATH IS MEASURABLE</text>
      <text class="fn-diagram__label" x="30" y="418" text-anchor="start">3B rank-16 LoRA · 128 GB unified · measured peak ≈ 20 GB</text>
      <text class="fn-diagram__label fn-diagram__label--mono fn-diagram__label--muted" x="30" y="438" text-anchor="start">Same four bills — weights, gradients, optimizer, activations — at 1/250× the scale. Extrapolate term by term.</text>
    </g>
  </svg>
  <figcaption>Three methods, three hardware asks, one model size. The 25× gap between full FT and QLoRA is almost entirely the optimizer-state bill — the one line that collapses when you freeze the base weights and quantize them.</figcaption>
</figure>

LoRA changes the arithmetic at lines 2 and 3. You freeze the base weights, so the gradient bill and optimizer bill apply only to the LoRA adapter — which on a rank-16 all-linears target is ~1% of the model. You still pay the full weights bill (the base has to be in memory to forward and backward through) and the full activation bill (you still backprop through every layer). Adapter-state collapse is what makes the method work: at 100B, the optimizer's 12 bytes/param × 1% trainable = 12 GB instead of 1.2 TB.

QLoRA goes further. Quantize the frozen base to 4-bit NF4, dequantizing blockwise on the fly during the forward pass. Weights drop from 2 bytes/param to ~0.5. The adapter arithmetic is unchanged. Activations are unchanged. The weights bill at 100B drops from 200 GB to ~50 GB, and suddenly the whole run fits on a single 141 GB H200.

## Working 100B three ways

### Full BF16 fine-tune

| Bill | Bytes/param | 100B total |
|---|---:|---:|
| Weights (bf16) | 2 | 200 GB |
| Gradients (bf16) | 2 | 200 GB |
| Adam state (fp32 momentum + variance + master) | 12 | 1,200 GB |
| Activations (checkpointed, realistic) | ~2 | ~200 GB |
| **Subtotal** | | **~1,800 GB** |

The activation term is the squishy one. It's a function of micro-batch × sequence × layer count × hidden size, not parameter count. Activation checkpointing gets you to ~2 bytes/param-per-microbatch. Without it you can hit 5–10× that, which is why nobody runs unchecked activations at frontier scale.

On an H100 80 GB fleet with FSDP full shard (ZeRO-3 semantics — weights, gradients, and optimizer state all sharded across ranks), you need **1,800 GB / 80 GB per GPU ≈ 23 GPUs minimum**, and you want ~30% headroom for transient allocations during the backward pass. The practical number is **24–32× H100 80 GB** — one or two DGX H100 nodes. On H200 141 GB the same run fits in **14–16×**. On B200 192 GB, **10–12×**. The total-memory budget dominates; which frontier accelerator you pick matters less than you'd think.

A production 100B full-FT is not sitting on one node. You are picking InfiniBand-connected multi-node topology because the weights alone cross the NVLink bandwidth threshold of a single DGX. That opens a second line item — interconnect — which this article's math doesn't price but your procurement conversation will.

### LoRA on a 100B base

Rank-16 LoRA across every linear projection in attention and MLP blocks touches ~0.5–1% of parameters depending on the architecture. Take 1% as a clean ceiling.

| Bill | 100B total |
|---|---:|
| Frozen base weights (bf16) | 200 GB |
| Adapter weights (1% × bf16) | 2 GB |
| Adapter gradients | 2 GB |
| Adapter Adam state (12 B × 1%) | 12 GB |
| Activations (checkpointed) | ~30–60 GB |
| **Subtotal** | **~250 GB** |

The optimizer line is the one that collapses — 1.2 TB → 12 GB. That is what LoRA is *for*, and at 100B it is the difference between "unthinkable" and "a long weekend on someone else's rig."

On 80 GB H100 with FSDP sharding the frozen base across ranks, **4–8× H100 80 GB** is the target — the frozen 200 GB splits into 25–50 GB slices, activations fit in the per-GPU budget with checkpointing, the tiny optimizer state lives wherever. A single **8× H100 80 GB node** (one DGX H100) is the natural unit, with room for sequence 4k–8k and a reasonable micro-batch.

### QLoRA on a 100B base

| Bill | 100B total |
|---|---:|
| Frozen base weights (NF4 4-bit) | 50 GB |
| Dequantization scratch + constants | ~5 GB |
| Adapter weights (1% × bf16) | 2 GB |
| Adapter gradients | 2 GB |
| Adapter Adam state (paged, 8-bit) | ~4 GB |
| Activations (checkpointed) | ~30–60 GB |
| **Subtotal** | **~65 GB tight · ~100 GB with headroom** |

QLoRA's trick is NF4 quantization of the frozen base plus paged 8-bit optimizers and bitsandbytes-style dequant-on-the-fly. The trainable adapter stays in bf16 — quantization touches only the frozen part. Activations are unchanged, because forward/backward still run in bf16 after dequant.

On current hardware, the single-GPU target is an **H200 141 GB** or a **B200 192 GB**. Either fits 100B QLoRA with room for decent sequence length. On 80 GB H100s you need **2× minimum, 4× for comfort**. At this scale the run stops being a cluster conversation and starts being a one-GPU-in-the-closet conversation.

The punchline: the ratio between 24 GPUs, 8 GPUs, and 1 GPU is almost entirely driven by *which of the four memory bills you opted out of paying*. Nothing else about the model changed.

## Verification — reading the Spark back into the formula

On the Spark, a rank-16 LoRA on a 3B Qwen2.5 base — 30M trainable parameters, ~1% of the model — hit **~20 GB peak GPU memory** on batch 4, sequence 2048, bf16 with gradient checkpointing, 8B NIM stopped to free ~10 GB of co-resident headroom (see [`lora-on-your-own-qa-pairs`](/articles/lora-on-your-own-qa-pairs/)). That 20 GB number is the sanity check for the math.

3B × 2 bytes (frozen base bf16) = 6 GB. Adapter + gradients + Adam at 1% ≈ <1 GB. Activations at batch 4, seq 2048, 32 layers, 2560 hidden, 2 bytes ≈ 8–10 GB with checkpointing. Total: ~15 GB, peak ~20 GB once you account for transient bf16/fp32 casts during the optimizer step. The Spark run lives inside the arithmetic.

Now scale the formula. 100B / 3B = ~33× — but you don't just multiply the 20 GB by 33, because activations don't scale linearly with total parameter count. They scale with hidden dimension and layer count, both sub-linear in params once you're past the 10B regime. Use the term-by-term math from the previous section and you land at 250 GB for LoRA at 100B. The Spark teaches you *which terms to extrapolate differently* — and that lesson is what transfers.

The related landmark from [`nemo-framework-continued-pretraining-on-spark`](/articles/nemo-framework-continued-pretraining-on-spark/): *"8B at BF16 with activations checkpointed should fit. 49B won't."* That is the full-fine-tune ceiling on 128 GB. 8B × 16 bytes/param = 128 GB — exactly the Spark's budget. 49B × 16 = 784 GB — won't fit and can't be made to fit without dropping to LoRA or QLoRA. That sentence is the Spark's tells-you-what-fits oracle, and it is dimensionally identical to the 100B reasoning above.

## Tradeoffs and surprises

**Context length is the silent killer.** The four bills above treat activations as ~2 bytes per parameter, a single-number approximation of a quantity that is actually proportional to batch × sequence × hidden × layers. Doubling sequence from 4k to 8k roughly doubles the activation bill. For un-flash-attended attention, the quadratic term can eat the entire GPU by itself at 32k context. If your fine-tuning data has long documents, price the context in *first* — it can flip a 1-GPU QLoRA into a 2-GPU QLoRA without the parameter count changing by one.

**Batch size compounds with context the same way.** Activation budgets scale linearly with both. Gradient accumulation is the canonical workaround: micro-batch 1 × accumulate 32 = effective batch 32, with activation memory set by micro-batch alone. On a single H200, this is how QLoRA of a 100B at 8k context produces credible loss curves — activations sized for micro-batch 1, gradient direction sized for 32.

**Parallelism choice is a sidebar, not the main act.** Three strategies to know:
- **FSDP / ZeRO-3** — shard weights, gradients, and optimizer state across data-parallel ranks. All-gather on forward, reduce-scatter on backward. The right default for full FT when per-rank shards fit on each GPU. Needed for anything over half a node's aggregate VRAM.
- **Tensor parallelism (TP)** — shard individual weight matrices across GPUs within a node; collective comms every matmul. Needs NVLink bandwidth or it dies. Use when a single layer's activations don't fit on one GPU — 70B+ at long context.
- **Pipeline parallelism (PP)** — split layers across GPUs, pass activations forward. Pipeline bubbles eat efficiency; you recover with micro-batching. Use when crossing node boundaries — cheaper inter-node comms than TP.

A 100B full-FT on 24× H100 80 GB almost certainly wants FSDP across all 24 (simple) or TP-8 within each DGX H100 node × PP-3 across 3 nodes (faster but fiddly). QLoRA on 1–2 GPUs wants FSDP-lite (ZeRO-1) or no parallelism.

**Flash-attention changes the slope.** FA2 / FA3 takes attention activations from O(seq²) to O(seq). That's the difference between a workable 32k-context QLoRA and an OOM. NeMo enables it by default on recent versions; `trl` / `peft` standalone scripts sometimes don't — worth grepping for in your config.

**Silent failure modes.** Two that don't look like OOMs — (a) the optimizer state silently offloads to CPU and step time jumps from 300 ms to 3 s; (b) activation checkpointing is configured but never reruns because something in the model graph breaks the recompute boundary. Both show up as "training is suspiciously slow" rather than "training crashed." Watch for them in `nvidia-smi dmon -s u` and profiler traces.

## What this unlocks

Three things you can do this week with this math in your head.

**A one-page sizing sheet.** Rows = model size (7B, 13B, 70B, 100B, 400B); columns = method (full FT, LoRA, QLoRA); cells = GPU count × type. Each cell is the term-by-term calculation above, scaled to the row. Tedious to build once, free to update thereafter. It replaces ninety minutes of Twitter threads with a single piece of paper you can hand to a procurement meeting.

**An informed rent-vs-buy conversation.** 100B QLoRA on 1× H200 141 GB is roughly $3/hour on today's spot market; 100B full-FT on 24× H100 80 GB is $80–$100/hour. Over a three-day run that is a $200 tab versus a $7,000 tab. Same model, same data — different bill because one of you priced the optimizer state and the other didn't.

**A better OOM filter.** When a run dies on epoch 2, the wall-clock location is a fingerprint. Dies during the optimizer step → gradient + state accounting is wrong (you probably under-counted trainable parameters — your LoRA target modules are wider than you thought). Dies during the backward pass → activations overran; cut sequence or micro-batch. Dies during the forward at a specific layer → tensor-parallelism boundary issue. The failure's location tells you which bill overran, which saves the hour you'd otherwise spend bisecting config.

## Closing

The DGX Spark is a 128 GB memory budget. Every article in this series eventually walks back to that number, because it's the envelope within which a personal AI power user makes decisions. The Spark will not fine-tune a 100B Nemotron — but it teaches you the arithmetic in a form small enough to run on your desk, measure in `nvidia-smi`, and extrapolate to any scale you will ever need to rent. The 20 GB from the 3B LoRA and the 1.6 TB from the 100B full-FT are the same four terms with different coefficients. One fits in a personal machine and one fits in a DGX H100 SuperPOD. The math is fixed; the hardware is negotiable.

Next in this *Looking Beyond Spark* series: **KV-cache arithmetic at inference time** — the memory story flips again when you leave the training loop and start serving a 100B model to real traffic. Same four bills; different weights. Different hardware ask. Same Spark, teaching a different lesson on a different day.
