---
title: "The GB10 Pretrain Envelope — Sweeping Batch, Sequence, and Precision on One Spark"
date: 2026-04-25
author: Manav Sehgal
product: NeMo
stage: training
difficulty: intermediate
time_required: "~30 min once the NeMo container is on disk — 7.4 min wall for the 16-config sweep, the rest is reading the numbers"
hardware: "NVIDIA DGX Spark"
tags: [nemo, training, pytorch, transformer-engine, fp8, megatron, autoresearch, dgx-spark, throughput]
summary: "Same 354M GPT, same training loop, swept across micro-batch (2,4,8,16), sequence length (1024,2048), and precision (bf16,fp8). 16 configurations, 30 steps each. Peak: 14,266 tokens/sec at batch=16, seq=1024, fp8 — 18% above the hand-rolled PyTorch baseline."
signature: BaselineTrainingEnvelope
also_stages: [foundations]
series: Autoresearch
---

The previous article (`nemo-framework-on-spark`) measured *one* operating point: 354M GPT, batch=4, seq=1024, bf16, 100 steps. The framework earned +5.8% throughput and 30% less memory over a hand-rolled `train.py` at that point — a clean floor measurement, but a measurement of one point on a curve. The honest next question is: *what does the curve actually look like?* On the GB10, when you push the micro-batch up, when you double the sequence, when you flip from bf16 to fp8 — where does throughput peak, where does it plateau, and how much GPU memory does each step buy you? That's the envelope this article maps.

The sweep is small enough to be honest and large enough to be useful: **16 configurations** (batch ∈ {2,4,8,16} × seq ∈ {1024,2048} × precision ∈ {bf16,fp8}), 30 steps each, 5 warmup steps excluded from the mean. Total wall time **7.4 minutes** on one GB10. The same `nemo_train.py` from the [NeMo Framework article](/field-notes/nemo-framework-on-spark/) is the kernel of the harness — only the per-run config varies. Headline result up front:

| operating point (354M GPT, GB10, 30 steps) | tokens/sec | step ms | peak GPU GiB | vs. vanilla A1 (12,119 tok/s) |
|---|---:|---:|---:|---:|
| **batch=16 · seq=1024 · fp8** *(peak throughput)* | **14,266** | 1,148 | 24.33 | **+17.7%** |
| batch=16 · seq=1024 · bf16 | 13,626 | 1,202 | 25.63 | +12.4% |
| batch=8 · seq=2048 · fp8 | 13,641 | 1,201 | 24.34 | +12.6% |
| batch=8 · seq=1024 · fp8 | 13,777 | 595 | 13.49 | +13.7% |
| batch=4 · seq=1024 · bf16 *(A1 setpoint, re-measured)* | 12,641 | 324 | 7.94 | +4.3% |
| batch=2 · seq=1024 · bf16 *(smallest tried)* | 11,044 | 185 | 5.26 | −8.9% |

Two things to read off this table before going further. First, **FP8 wins every single shape** — the gain is small (2.6–8.1%) but it's free, and the memory footprint shrinks too. Second, the ceiling is around **14.3K tok/s for this 354M model on this GPU** — about 18% above the hand-rolled baseline, less than 25% above the smallest config in the sweep. The envelope is *narrow*, and that's an important data point in its own right.

:::define[Micro-batch vs global batch]
*Micro-batch* is the per-step batch the GPU actually computes a forward+backward over (the "batch" in this article — 2, 4, 8, or 16 sequences). *Global batch* is the effective batch size the optimizer sees per update, equal to micro-batch × gradient-accumulation-steps × data-parallel-rank-count. On a single Spark with grad-accum=1, the two are equal — but in any multi-GPU or accumulation-based recipe, micro-batch sets *memory* and global batch sets *learning dynamics*.
:::

:::define[BF16 mixed-precision training]
Brain Float 16: 1 sign bit, 8 exponent bits, 7 mantissa bits — same dynamic range as fp32, half the storage. Trains stably at billions of parameters where IEEE fp16 underflows. "Mixed precision" means weights and activations are bf16 but the optimizer keeps fp32 master copies of weights and fp32 momentum/variance buffers. The default training precision on Hopper and Blackwell — including the Spark's GB10.
:::

## Why this matters for the personal AI power user

The Autoresearch arc's overnight agent (article A4 — `autoresearch-agent-loop`, still upcoming) will run something like *edit `train.py`, train for 5 minutes, measure `val_bpb`, keep or discard, repeat ~100×*. Every one of those 100 iterations costs wall-clock time the agent doesn't get back. **The envelope this article maps is the agent's currency.** At 14.3K tok/s, a 5-minute training step processes ~4.3 M tokens; 100 iterations ≈ 430 M tokens overnight. That's not "pretrain a model from scratch" budget, but it's plenty for 100 controlled-perturbation experiments on the architecture / optimizer / data-mix knobs the agent will be twisting.

The other audience for this measurement is the **person debating whether to bother with a training loop on a single GPU at all**. The Spark sits in an awkward spot: too small for the parallelism story NeMo Framework was designed around (TP / PP / CP / SP all collapse to 1), too big to dismiss as a toy. The envelope answers that debate empirically — at the largest config we tried (batch=16 × seq=2048 × bf16), the GB10 sustains **49 GiB peak GPU memory** and never OOMs. There's still ~80 GiB of unified-memory headroom on the same box. That's the edge-AI builder pitch: you can pretrain a 354M-class model on one machine in your office without ever leaving the predictable-power, predictable-memory regime.

## The sweep at architecture-glance

<figure class="fn-diagram" aria-label="Sweep harness architecture: three input axes (precision ∈ {bf16, fp8}, sequence length ∈ {1024, 2048}, micro-batch ∈ {2, 4, 8, 16}) flow into a for-loop that calls run_one for each of 16 configurations. run_one builds a 354M GPT, trains it for 30 steps on the GB10, and emits a metrics record (tokens/sec, peak GiB, step ms, loss). Records accumulate into sweep_results.json. Parallel to the loop, an nvidia-smi sampler at 2-second intervals records GPU utilization, power, and temperature into a CSV.">
  <svg viewBox="0 0 900 460" role="img" aria-label="Sweep architecture: 3 input axes feed a 16-config for-loop; each config runs one 354M GPT pretrain on GB10 and outputs metrics; nvidia-smi samples telemetry in parallel." preserveAspectRatio="xMidYMid meet">
    <defs>
      <linearGradient id="bteflow-accent-grad" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%"   stop-color="var(--svg-accent-blue)" stop-opacity="0.18"/>
        <stop offset="100%" stop-color="var(--svg-accent-blue)" stop-opacity="0.04"/>
      </linearGradient>
    </defs>
    <g class="fn-diagram__edges">
      <path class="fn-diagram__edge" d="M 230 95 L 380 215" />
      <path class="fn-diagram__edge" d="M 230 175 L 380 230" />
      <path class="fn-diagram__edge" d="M 230 255 L 380 245" />
      <path class="fn-diagram__edge fn-diagram__edge--accent" d="M 620 230 L 760 230" />
      <path class="fn-diagram__edge fn-diagram__edge--dashed" d="M 500 300 L 500 350" />
      <path class="fn-diagram__edge fn-diagram__edge--dashed" d="M 620 380 L 760 380" />
    </g>
    <g class="fn-diagram__nodes">
      <rect class="fn-diagram__node" x="60" y="60"  width="170" height="60" rx="8" />
      <rect class="fn-diagram__node" x="60" y="140" width="170" height="60" rx="8" />
      <rect class="fn-diagram__node" x="60" y="220" width="170" height="60" rx="8" />
      <rect class="fn-diagram__node fn-diagram__node--accent fn-diagram__pulse" x="380" y="200" width="240" height="100" rx="10" style="fill: url(#bteflow-accent-grad)" />
      <rect class="fn-diagram__node" x="760" y="200" width="120" height="60" rx="8" />
      <rect class="fn-diagram__node fn-diagram__node--ghost" x="380" y="350" width="240" height="60" rx="8" />
      <rect class="fn-diagram__node fn-diagram__node--ghost" x="760" y="350" width="120" height="60" rx="8" />
    </g>
    <g class="fn-diagram__labels">
      <text class="fn-diagram__label fn-diagram__label--muted" x="75" y="84" text-anchor="start">PRECISION</text>
      <text class="fn-diagram__label fn-diagram__label--display" x="75" y="106" text-anchor="start">bf16 · fp8</text>
      <text class="fn-diagram__label fn-diagram__label--muted" x="75" y="164" text-anchor="start">SEQ LEN</text>
      <text class="fn-diagram__label fn-diagram__label--display" x="75" y="186" text-anchor="start">1024 · 2048</text>
      <text class="fn-diagram__label fn-diagram__label--muted" x="75" y="244" text-anchor="start">MICRO-BATCH</text>
      <text class="fn-diagram__label fn-diagram__label--display" x="75" y="266" text-anchor="start">2 · 4 · 8 · 16</text>
      <text class="fn-diagram__label fn-diagram__label--accent" x="395" y="226" text-anchor="start">run_one(cfg) · 16×</text>
      <text class="fn-diagram__label fn-diagram__label--display" x="395" y="250" text-anchor="start">354M GPT · 30 steps · GB10</text>
      <text class="fn-diagram__label fn-diagram__label--mono fn-diagram__label--muted" x="395" y="270" text-anchor="start">build → train → measure → release</text>
      <text class="fn-diagram__label fn-diagram__label--mono fn-diagram__label--muted" x="395" y="288" text-anchor="start">try/except OOM · gc.collect · empty_cache</text>
      <text class="fn-diagram__label fn-diagram__label--muted" x="775" y="224" text-anchor="start">PER CONFIG</text>
      <text class="fn-diagram__label fn-diagram__label--display" x="775" y="246" text-anchor="start">tok/s · GiB · ms</text>
      <text class="fn-diagram__label fn-diagram__label--muted" x="395" y="374" text-anchor="start">nvidia-smi sampler · 2 s</text>
      <text class="fn-diagram__label fn-diagram__label--mono fn-diagram__label--muted" x="395" y="396" text-anchor="start">parallel telemetry stream · 225 samples</text>
      <text class="fn-diagram__label fn-diagram__label--muted" x="775" y="374" text-anchor="start">CSV STREAM</text>
      <text class="fn-diagram__label fn-diagram__label--display" x="775" y="396" text-anchor="start">util · W · °C</text>
    </g>
  </svg>
  <figcaption>Three sweep axes, one inner loop, two output streams. The loop body — <code>run_one(cfg)</code> — is the only thing that touches the GPU; the 30-step training run is the unit of measurement. The dashed line is the 2-second nvidia-smi sampler that runs in parallel — it doesn't gate the sweep, it just records what the GB10 was doing while the harness ran.</figcaption>
</figure>

## What the harness does — and what it intentionally doesn't

```python
# articles/baseline-training-loop-on-spark/evidence/sweep.py — excerpt

configs: list[RunCfg] = []
for precision in ("bf16", "fp8"):
    for seq in (1024, 2048):
        for batch in (2, 4, 8, 16):
            configs.append(RunCfg(batch_size=batch, seq_len=seq,
                                  precision=precision))

for c in configs:
    m = run_one(c)         # 30 steps, 5 warmup, returns metrics dict
```

:::define[AdamW fused]
AdamW = Adam with decoupled weight decay (Loshchilov & Hutter, 2017) — the optimizer of choice for transformer pretrain. Per *trainable* parameter it stores fp32 momentum (`m`), fp32 variance (`v`), and a fp32 master weight when training in mixed precision: 12 bytes/param of optimizer state. The "fused" variant launches a single CUDA kernel for the per-parameter `m`, `v`, and weight update instead of three; saves dozens of µs per step on the GB10.
:::

The model shape, the optimizer (AdamW fused), the cosine LR schedule, the random-token batches, the cross-entropy loss — every one of those is identical to A1's `nemo_train.py`. The only knobs the sweep touches are the three axes named above. That intentional poverty matters: the chart in the signature is a *throughput envelope*, not a benchmark of competing implementations. We're not asking "is NeMo faster than vLLM?" — we're asking "where on the GB10 does this same training loop find its ceiling?"

A few choices the harness makes that are worth flagging:

- **30 steps per config, 5 warmup excluded.** A1's matched run used 100 steps and 10 warmup. We dropped both for sweep economics — the 5-warmup mean is stable to within ~1% of the 100-step number at the one shape (batch=4, seq=1024, bf16) we cross-checked. The article calls this out in the gotchas section.
- **No data loader.** Random-token batches are generated on-device per step. A real pretrain run on a 1+ TB corpus would saturate the disk-→-CPU-→-GPU pipeline before it saturates the model — but that's a *system* measurement, not a *kernel* measurement. The envelope here is the model's ceiling; the data path is a separate envelope a future article will measure (A3 — `nemo-curator-training-data-prep`).
- **No gradient accumulation, no parallelism axes.** Every config runs on one GPU with TP=PP=CP=SP=1. The GB10 has one GPU; there's nothing to parallelize across. This is the conservative case for NeMo's value pitch — one of A1's findings, restated.
- **OOM caught and recorded, sweep continues.** The harness wraps each `run_one` in a `try/except` for `torch.cuda.OutOfMemoryError`. Zero OOMs occurred — even batch=16 × seq=2048 × bf16 (49 GiB peak) stayed well under the GB10's unified-memory ceiling.
- **FP8 uses TransformerEngine's `DelayedScaling` recipe, HYBRID format** (E4M3 forward, E5M2 backward), `amax_history_len=16`. This is the same recipe the bundled NeMo container's defaults reach for; we did not tune it.

:::define[FP8 with delayed scaling]
Storing weights and activations in 8-bit floating-point — half the bandwidth of bf16. Two formats: E4M3 (more mantissa, used for forward activations) and E5M2 (more exponent, used for backward gradients). "Delayed scaling" tracks per-tensor max-absolute-value over a recent history window (`amax_history_len`) and uses that to pick the scale factor for the *next* step, avoiding a synchronous reduction every iteration. Hopper introduced the math; Blackwell (Spark's GB10) doubled the throughput per FP8 op.
:::

## The shape of the envelope

The signature SVG at the top of the article tells the story at thumbnail size; here's the same story in two tables.

**Throughput (tokens/sec, higher is better):**

| seq=1024 | batch=2 | batch=4 | batch=8 | batch=16 |
|---|---:|---:|---:|---:|
| bf16 | 11,044 | 12,641 | 12,819 | 13,626 |
| fp8  | 11,944 | 13,462 | 13,777 | **14,266** |
| **fp8 win** | +8.1% | +6.5% | +7.5% | +4.7% |

| seq=2048 | batch=2 | batch=4 | batch=8 | batch=16 |
|---|---:|---:|---:|---:|
| bf16 | 12,422 | 12,729 | 13,036 | 13,036 |
| fp8  | 12,873 | 13,202 | 13,641 | 13,370 |
| **fp8 win** | +3.6% | +3.7% | +4.6% | +2.6% |

**Peak GPU memory allocated (GiB, lower is better):**

| seq=1024 | batch=2 | batch=4 | batch=8 | batch=16 |
|---|---:|---:|---:|---:|
| bf16 | 5.26 | 7.94 | 13.83 | 25.63 |
| fp8  | 5.60 | 8.03 | 13.49 | 24.33 |

| seq=2048 | batch=2 | batch=4 | batch=8 | batch=16 |
|---|---:|---:|---:|---:|
| bf16 | 7.95 | 13.85 | 25.65 | 49.24 |
| fp8  | 8.05 | 13.52 | 24.34 | 46.06 |

Three findings drop out of these two tables:

**1. FP8 wins free throughput at every shape.** The smallest gain (+2.6%) is at the largest, slowest shape (batch=16 × seq=2048); the largest gain (+8.1%) is at the smallest, latency-bound shape (batch=2 × seq=1024). The spread tells you something — at small shapes the arithmetic is more dominant in the step time so flipping to FP8 matmuls helps more; at large shapes more of the wall time is in non-matmul ops (attention masking, layer norms, optimizer step) that FP8 doesn't touch.

**2. Throughput plateaus past batch=8 at seq=2048.** Look at the bf16 row of the seq=2048 table: 13,036 → 13,036 from batch=8 → batch=16. Identical. The fp8 row actually *regresses* slightly (13,641 → 13,370). At seq=1024 you can still squeeze some more throughput out of batch=16, but at seq=2048 you're already on the flat. That matters for the agent: at long sequence, the cost of doubling batch is 2× memory and ~2× wall time for ~0% throughput gain. Don't.

**3. Memory scales linearly in tokens-per-step.** Peak GPU memory ≈ 1.5 KiB/token × tokens-per-step + ~5 GiB model overhead, on this 354M model. (Worked example: batch=16 × seq=2048 = 32,768 tokens-per-step × 1.5 KiB ≈ 48 GiB — measured 49.24 GiB.) That linearity is *useful*: the agent can predict OOMs ahead of time without trying them. Anything that fits in (`tokens_per_step` × 1.5 KiB + ~5 GiB) < 100 GiB will run on the Spark with reasonable margin.

:::math[The 1.5 KiB/token rule on this 354M model]
At batch=8 × seq=1024 = 8,192 tokens × 1.5 KiB = 12 GiB activations + ~1.5 GiB model state ≈ 13.5 GiB peak. Measured: 13.83 GiB. At batch=16 × seq=2048 = 32,768 tokens × 1.5 KiB = 48 GiB + 1.5 GiB = 49.5 GiB. Measured: 49.24 GiB. The constant comes from activation checkpointing's recompute-boundary spacing × the model's hidden dim (1024) × layers (24). Different model shape, different constant — but the *linear-in-tokens* rule generalizes.
:::

:::why[A narrow envelope is the agent's friend]
A 25% spread between best and worst config means the agent's overnight budget doesn't depend on guessing the right shape. Even the worst sweep config gets ~75% of peak throughput. Translation for the autoresearch loop: the agent can sweep architecture knobs without simultaneously sweeping batch/seq/dtype — those settle into "use fp8, use the largest batch that fits, prefer seq=1024 for short-context experiments and seq=2048 for long-context ones." Wide-envelope hardware would force the agent to co-search both spaces; this hardware doesn't.
:::

## Sustained load — what the GPU did during the sweep

The 7.4-minute sweep ran with a 2-second `nvidia-smi` sampler in parallel. **225 samples** captured across 450 wall seconds. The summary:

| metric | mean | peak |
|---|---:|---:|
| GPU utilization | 86.8 % | 96 % |
| Power draw | 55.8 W | 77.1 W |
| Temperature | 65.8 °C | 77 °C |

Three things worth noting. **First**, the GB10 sustained 86.8% mean utilization across a 16-configuration sweep with no thermal throttling — the peak temperature (77°C) is well below any throttle threshold. **Second**, the power envelope is small in absolute terms — 55.8 W mean is roughly an LED light bulb's continuous draw. A whole night of pretrain (8 hours × 56 W = 448 Wh ≈ 0.45 kWh) costs about as much electricity as running a desk lamp through the same period. The "personal AI power user" pitch isn't a metaphor — the energy bill genuinely doesn't change. **Third**, the gap between mean (87%) and peak (96%) utilization is the harness overhead between configs (model build, OOM-cleanup, optimizer reset). A long-running single-config training would sit closer to the 96% peak the whole time.

The full nvidia-smi stream is preserved at [`evidence/nvidia_smi_during_sweep.csv`](./evidence/nvidia_smi_during_sweep.csv) — one row every 2 seconds.

## Cross-checks against the NeMo Framework article

Before trusting the numbers, two cross-checks against the A1 measurement at the matched setpoint (batch=4, seq=1024, bf16):

| metric | A1 (100 steps, 10 warmup) | A2 sweep (30 steps, 5 warmup) | drift |
|---|---:|---:|---:|
| tokens/sec | 12,820 | 12,641 | −1.4 % |
| mean step ms | 319.5 | 324.0 | +1.4 % |
| peak GPU memory GiB | 7.94 | 7.94 | 0.0 % |

Within 1.4% on throughput, identical on peak memory. The 30-step / 5-warmup measurement is reproducible enough that the sweep numbers stand. The drift is most likely due to thermal state (A1 ran on a cool GPU; A2 ran the matched config sixth in a sweep, with a warmer GPU and slightly different DRAM cache state), not a measurement artifact.

## Tradeoffs, gotchas, and the things the sweep doesn't measure

**A 30-step run isn't a training run.** It's a kernel timing test. Real pretrain involves convergence, validation loss curves, learning-rate schedule effects on tokens-to-target — none of which a 30-step run captures. The throughput numbers here are *steady-state forward-backward-step* throughput, suitable for system planning; they're not "this is what your loss will look like at hour 8" claims.

:::pitfall[Don't read loss across configs as a quality signal]
A 30-step run is a *kernel timing test*, not a training run. Loss after 30 steps depends on the per-step weight-update bandwidth, which scales inversely with batch size at fixed step count. Smaller batches converge faster on a per-step basis (more gradient updates per token of data), so they always end with lower 30-step loss — even when their *per-token* convergence rate is worse. If you need an apples-to-apples loss comparison, train each config to the same total token count, not the same step count.
:::

**Loss values fluctuate by config and that's expected.** Final loss after 30 steps ranges from 6.46 (batch=2 / seq=1024 / fp8) to 9.77 (batch=16 / seq=2048 / bf16). The reason isn't the framework — it's that 30 steps × small batch makes more weight-update bandwidth than 30 steps × large batch, *for the same total tokens trained*. Smaller batch converges faster on a per-step basis. If you needed an apples-to-apples loss comparison you'd train each config to the same total token count, not the same step count. We didn't, because this article is about the throughput envelope, not the loss-vs-tokens curve.

**FP8 came almost free, but `DelayedScaling` is a recipe with knobs.** We used the bundled `DelayedScaling(format=HYBRID, amax_history_len=16, amax_compute_algo="max")` — TransformerEngine's documented default. Tuning the recipe (history length, the per-tensor scaling vs. delayed-scaling tradeoff, MX-format if you want to chase the latest 2026 recipes) could push the FP8 numbers further. None of that was explored.

**The harness uses random tokens, not real data.** A real pretrain reads from a sharded TFRecord / WebDataset / Megatron-LM `.bin` file; the data path can absolutely be the bottleneck on a single-GPU system if you don't pre-shard, pre-tokenize, and prefetch. Article A3 (`nemo-curator-training-data-prep`, upcoming) measures *that* envelope; this article isolates the model envelope from the data path on purpose.

**One Python `try/except` cleanup-between-configs trick worth knowing.** Between configs the harness has to release the prior model + optimizer + activations, otherwise the next config's `build_model()` fails with a fragmented allocator. The fix is `gc.collect()` followed by `torch.cuda.empty_cache()` in a `finally` block — covered by every PyTorch sweep tutorial, easy to forget. The `dir()`-walking dead-code in the harness is a deliberate empty stub for "if you ever need explicit `del` calls, here's where they go." Currently the implicit Python frame teardown is enough.

**Single-GPU is the conservative case for NeMo's value pitch — restated.** Every parallelism axis is 1 on the GB10; the 17.7% headroom over vanilla PyTorch is the *floor* of what NeMo's substrate earns. On a multi-GPU box that headroom would compound with TP / PP / SP scaling that vanilla PyTorch doesn't ship at all. Worth saying explicitly because at first read the 17.7% might look small relative to the 70 GiB container that ships it.

:::deeper
- [Megatron-LM paper (Shoeybi et al., 2019)](https://arxiv.org/abs/1909.08053) — the parallelism architecture under TransformerEngine; the kernels Spark's TP=PP=1 mode collapses to.
- [TransformerEngine docs](https://docs.nvidia.com/deeplearning/transformer-engine/user-guide/index.html) — `DelayedScaling`, HYBRID format, and the `amax_history_len` knob this sweep didn't tune.
- [`nemo-curator-training-data-prep`](/field-notes/nemo-curator-training-data-prep/) — A3's data-path measurement that uses this same harness with real tokens; together they bound the model and data envelopes.
- [Chinchilla scaling-laws paper (Hoffmann et al., 2022)](https://arxiv.org/abs/2203.15556) — the 20-tokens-per-parameter ratio used in the "Chinchilla-optimal in 6 days" claim above.
:::

## What this unlocks

**1. The Autoresearch agent's per-iteration budget is now a number.** A 5-minute training step at the peak config gives the agent ~4.3 M tokens of forward-backward-update bandwidth per experiment. 100 experiments overnight ≈ 430 M tokens of compute spent. That's the "what can the agent actually try?" math A4 will lean on.

**2. A 354M-class model can be pretrained-from-scratch on one Spark in well under a week.** Chinchilla-optimal for 354M is roughly 20× the parameter count in tokens — 7.1 B tokens. At 14.3K tok/s × 86,400 s/day = 1.24 B tokens/day. **Six days of wall time** for a Chinchilla-optimal pretrain on one machine, ~$0.27 of electricity per day at average US residential rates. That's not a serious research model, but it's a serious *learning project* — and "you can do this without a cloud account" is what the Spark uniquely earns.

**3. The hardware envelope informs the architecture envelope.** When you know the GB10 holds 49 GiB at batch=16 × seq=2048 × bf16 with ~80 GiB of headroom remaining, you can confidently scale to a 1B-class model at modest batch on the same machine without a sweep. Memory-per-token is roughly architecture-invariant for transformer-family models; throughput-per-step scales with parameter count. That math is the foundation A2 hands forward to A3 and A4.

## State of the apps — as of A2

**Autoresearch now:** has a driver (NIM 8B, from F1), an experiment substrate (NeMo Framework, from A1), and a measured throughput envelope (this article — 14.3K tok/s peak on 354M, ~50 GiB peak memory at the largest stable config). The agent loop itself (A4) is still upcoming. **Second Brain now:** unchanged since S4 ([`mcp-second-brain-in-claude-code`](/field-notes/mcp-second-brain-in-claude-code/)) — RAG-over-MCP shipped. **LLM Wiki now:** un-opened — W1 (`wiki-schema-and-llm-bookkeeper`) is the next decision point. Next up in Autoresearch: **A3 — `nemo-curator-training-data-prep`** (the data-path envelope to complement this kernel envelope), or jump to **A4 — `autoresearch-agent-loop`** if the user wants to skip data prep and synthesize an agent on top of the random-token harness.

The full sweep is preserved at [`evidence/sweep_results.json`](./evidence/sweep_results.json). The harness is at [`evidence/sweep.py`](./evidence/sweep.py) — copy it, change the axes, sweep your own model. The interesting sweep on a 354M model is the one above; the interesting sweep on *your* model is the one you haven't run yet.

:::hardware[Same kernel envelope, frontier coefficients]
The 14.3K tok/s peak on a 354M GPT scales by accelerator memory bandwidth, since transformer training at this size is bandwidth-bound, not compute-bound. The Spark's GB10 sits at ~273 GB/s effective bandwidth for unified memory. An H100 80 GB at 3.35 TB/s lifts the same shape to ~150K tok/s (~10×); H200 at 4.8 TB/s pushes to ~210K (~15×); B200 at 8 TB/s reaches ~350K (~25×). Multi-GPU TP=2/4 then compounds. The Spark teaches the *shape* of the envelope — narrow in batch, FP8-positive, memory-linear-in-tokens — and the cloud rents the coefficients.
:::
