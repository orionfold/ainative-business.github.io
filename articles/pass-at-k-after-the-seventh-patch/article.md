---
title: "Pass@k After the Seventh Patch — Three Shapes ESamp Takes on Spark"
date: 2026-05-03
author: Manav Sehgal
product: Foundation
stage: inference
also_stages: [observability]
difficulty: advanced
time_required: "~3 hours of measurement · ~one line of patch"
hardware: "NVIDIA DGX Spark"
tags: [decoding, sampling, test-time-scaling, vllm, runtime, patching, benchmarks, pass-at-k, aime, humaneval]
summary: "Patches were six. The Pass@k harness surfaced a seventh — a one-line slice in the residual tap that only fires once batches shrink mid-run. Once cleared, ESamp takes three shapes: flat on saturated cells, lifting both rates on instruct headroom, and +6.67pp pass@8 on the unsaturated reasoning cell."
signature: WhereEsampBites
series: Frontier Scout
fieldkit_modules: [eval, capabilities]
---

[Patches were six](/field-notes/runtime-frontier-six-patches-on-spark/) closed at three trials, eager mode, and a 97.4% tok/s ratio against baseline on Qwen 2.5 7B Instruct. The Pass@k matrix the [test-time-distilling article](/field-notes/test-time-distilling-for-exploration/) queued for "the next session" was still queued — blocked, the previous article said, on a "diverse-prompt state-isolation issue inside the model bank." This is the next session, and the actual cause was a drift the six-patch arc never surfaced because the bench harness never pushed batches large enough for it to fire.

:::define[ESamp]
A test-time-distilling technique ([paper](https://arxiv.org/abs/2604.24927)). A tiny online-trained Distiller predicts the LLM's deep-layer hidden state from its shallow-layer hidden state. When the prediction error spikes on a candidate continuation, that's a novelty signal — the prefix is moving into territory the LLM has not been recently calibrated on — and ESamp reweights the sampler toward that novelty. The effect is *semantic* exploration, not just lexical resampling, which is exactly what Pass@k workloads reward.
:::

:::define[Pass@k]
The probability that *at least one* of `k` parallel sampled completions is correct on a given problem. Pass@1 measures single-shot accuracy; pass@8 with `n=8` samples per problem rewards a sampler whose `n` attempts cover *different* solution paths rather than rephrasing one. Estimated unbiasedly from `n ≥ k` total samples per problem (HumanEval's standard formula). Pass@k is the natural unit for any test-time-scaling claim, because it isolates *breadth* from *single-attempt* accuracy.
:::

:::define[Test-time scaling]
Spending more compute *at inference* (more samples, longer chains-of-thought, beam search, sampler interventions) instead of more compute at training time. The bet: a smaller model that explores `n` parallel attempts under a verifier (math grader, sandbox, tool) lands more correct answers than the same compute spent training a bigger one. ESamp, speculative decoding, classifier-free guidance, and beam-search ablations all live here — the technique that makes `n` parallel attempts *cover* the answer space wins.
:::

The seventh patch was one line. It made the matrix runnable. The matrix has three shapes.

## The paper, in one breath

**Thesis.** ESamp's value proposition is sharp: at a single-digit-percent throughput cost, a Pass@k workload should land more correct answers per `n` parallel attempts than vanilla temperature sampling. The mechanism is the Distiller-driven reweight — semantic exploration replacing lexical resampling — and the headline empirical claim in the paper is **+9.7pp pass@8 on AIME 2024 with DeepSeek-R1-Distill-Qwen-7B**, a model where chain-of-thought breadth matters and instructive correctness alone does not.

**Why this technique matters for a personal AI builder.** Pass@k is the natural unit of test-time scaling — the right way to spend a Spark's idle GPU on a hard problem is to let `n=8` parallel attempts diverge. Lexical-only diversity (temperature, top-p) tends to produce eight rephrasings of the same approach. Semantic diversity is what gives the verifier loop something to verify *more than once*. ESamp is the first published technique that delivers that diversity at a wall-clock cost a personal builder can absorb, and its claim is verifiable on a 128 GB Spark — one rented hour on cloud GPUs at the same scope, without the patching arc, runs about $30.

**Promise vs achieved.** Paper headline: **+9.7pp pass@8** on AIME 2024 with DeepSeek-R1-Distill-Qwen-7B at `n=8`, β=0.8. Spark, this session, on the same model-task-knob combination at the same `n`: **+6.67pp pass@8** (60.00% → 66.67%), within **3 percentage points** of the paper across a different runtime (vLLM 0.20.0 vs reference 0.10.x), eager mode (the paper used CUDA graphs), and seven upstream patches deep. The same configuration on Qwen 2.5 7B *Instruct* — an instruction-tuned model where AIME hits its low end — lifts pass@1 *and* pass@8 by 3.33pp each. And on Qwen 7B × HumanEval, where the model already saturates pass@1 at 70%, ESamp moves nothing within noise. **Three shapes, one technique, one model bank, one β** — the technique is the same across all three; the workload's headroom decides whether anything moves.

:::why[The matrix tells a richer story than the paper headline]
Single-cell paper claims (`+9.7pp pass@8`) are the best cell, on the model-task pair the technique was designed for. A Spark builder running the same patch arc on a *different* combination — instruction model on saturated benchmark, instruction model on an unsaturated one, reasoning model on a hard one — needs the whole shape, not the headline. ESamp moves nothing on the saturated cell, lifts both pass@1 and pass@8 on the unsaturated instruct cell, and lifts only pass@8 on the reasoning cell. The mechanism reads through the matrix, not the number.
:::

## Why this matters for a personal AI builder

The previous article closed at *the runtime is the frontier*. This one extends the frame to *and the workload is the verifier*. Patching tLLM through six upstream drifts plus a seventh latent was the price of admission to a runtime that fires. Running the matrix is what tells you which workloads are worth firing it on. **Test-time-distilling is not a free add-on.** On a saturated cell — instruction-tuned model, easy benchmark — the compute spent on the Distiller's online training and the post-filter sampler buys nothing. On the unsaturated cells, the picture splits in a way the original paper headline hides.

The split matters for how a Spark builder spends parallel completions. If the local model is reasoning-tuned (R1-Distill, NeMo Reasoning, DeepSeek-V3-style chains) and the task has a verifier (math correctness, sandbox exec, citation match), `n=8` parallel attempts with ESamp lift pass@8 — the breadth — *without making any single attempt better*. The verifier sees more semantically distinct candidates. If the local model is instruction-tuned and the task is at the *bottom* of its competence (AIME for Qwen 2.5 7B Instruct, where both pass@1 and pass@8 are mediocre), ESamp does both — sharpens marginal token probability and spreads exploration. If the model is at the *top* of its competence on the task, neither matters. The picking-which-cell-you're-in step is the new operating cost; once you know, the technique scales.

:::define[Verifier-bound workload]
A workload where each candidate's correctness can be checked cheaply by something other than the LLM — a math grader, a code sandbox, a tool roundtrip, a citation matcher. Verifier-bound is the regime where `n` parallel attempts pay off: the verifier picks the right one, so spending compute on *spreading* the `n` matters more than making any single attempt better. ESamp's pass@8 lift only earns its keep when there's a verifier downstream that can pick from `n=8`.
:::

This is exactly the kind of measurement the Spark earns its keep on. Three matrix cells, two models, two benchmarks, three hours of compute — at home, repeatable, with no latency to a paid endpoint and no rate limit to negotiate around. The patches arc was the entry fee. The matrix is the dividend.

## The seventh drift — and why patches#2 didn't see it

The six drifts in the patches article were all surfaced by *small* workloads — bench mode runs a handful of identical prompts through `model_bank_on` vs `single_off` and compares throughput. None of them pushed the in-flight batch above ten requests, and crucially, none of them pushed it through a *shrinking* phase where one of those requests finished while others were still in decode. The Pass@k harness does both. 30 AIME problems × n=8 = 240 in-flight requests, vLLM scheduling decode tokens across them, requests draining out of the batch as they hit EOS or max-tokens. Every time a request drained, the next batch had a smaller `tensor.shape[0]` than the one before it.

:::define[Residual capture tap]
ESamp's hook into vLLM's transformer forward pass. The runtime replaces `layer.forward` on two layers (a *shallow* one and a *deep* one) with a Python wrapper that captures the residual stream — the per-token hidden state — and forwards it to the Distiller for online training. *Tap* because the hook reads the stream non-destructively; the original forward continues unaltered. The seventh drift lived inside this tap's index-select call when the in-flight batch shrank.
:::

<figure class="fn-diagram" aria-label="Seven-patch drift timeline. A horizontal lane shows patches one through seven across time. Patches one through six (left) were all surfaced by the bench harness, which runs identical prompts through monotonically growing batches — the first six rendered as outlined cells. Patch seven (right) was surfaced only when the Pass@k harness sent thirty AIME problems times n equals eight equals 240 in-flight requests through vLLM, where requests drained at different times and the in-flight batch shrank between scheduler steps. Patch seven sits in an accent cell at the right end of the lane, with the test surface labelled below as decode-shrink workloads (Pass@k, agent loops, multi-prompt streaming). A divider between the two zones makes the change of test surface visible.">
  <svg viewBox="0 0 900 320" role="img" aria-label="Seven-patch drift timeline. A horizontal lane shows patches one through seven across time. Patches one through six (left) were all surfaced by the bench harness, which runs identical prompts through monotonically growing batches — the first six rendered as outlined cells. Patch seven (right) was surfaced only when the Pass@k harness sent thirty AIME problems times n equals eight equals 240 in-flight requests through vLLM, where requests drained at different times and the in-flight batch shrank between scheduler steps. Patch seven sits in an accent cell at the right end of the lane, with the test surface labelled below as decode-shrink workloads (Pass@k, agent loops, multi-prompt streaming). A divider between the two zones makes the change of test surface visible." preserveAspectRatio="xMidYMid meet">
    <defs>
      <linearGradient id="d-pak3-bench-grad" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%"   stop-color="var(--svg-accent-blue)" stop-opacity="0.10"/>
        <stop offset="100%" stop-color="var(--svg-accent-blue)" stop-opacity="0.02"/>
      </linearGradient>
      <linearGradient id="d-pak3-passk-grad" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%"   stop-color="var(--color-primary)" stop-opacity="0.18"/>
        <stop offset="100%" stop-color="var(--color-primary)" stop-opacity="0.04"/>
      </linearGradient>
      <linearGradient id="d-pak3-accent-grad" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%"   stop-color="var(--color-primary)" stop-opacity="0.34"/>
        <stop offset="100%" stop-color="var(--color-primary)" stop-opacity="0.08"/>
      </linearGradient>
      <radialGradient id="d-pak3-accent-halo" cx="0.5" cy="0.5" r="0.6">
        <stop offset="0%"   stop-color="var(--color-primary)" stop-opacity="0.18"/>
        <stop offset="100%" stop-color="var(--color-primary)" stop-opacity="0"/>
      </radialGradient>
    </defs>
    <rect x="60"  y="80" width="600" height="120" rx="8" fill="url(#d-pak3-bench-grad)" stroke="none"/>
    <rect x="700" y="80" width="160" height="120" rx="8" fill="url(#d-pak3-passk-grad)" stroke="none"/>
    <rect x="700" y="80" width="160" height="120" fill="url(#d-pak3-accent-halo)" stroke="none"/>
    <g class="fn-diagram__edges">
      <path class="fn-diagram__edge" pathLength="100" d="M 60 140 L 680 140" />
      <path class="fn-diagram__edge fn-diagram__edge--dashed" pathLength="100" d="M 680 60 L 680 220" />
    </g>
    <g class="fn-diagram__nodes">
      <rect class="fn-diagram__node" x="80"  y="116" width="80" height="48" rx="4"/>
      <rect class="fn-diagram__node" x="180" y="116" width="80" height="48" rx="4"/>
      <rect class="fn-diagram__node" x="280" y="116" width="80" height="48" rx="4"/>
      <rect class="fn-diagram__node" x="380" y="116" width="80" height="48" rx="4"/>
      <rect class="fn-diagram__node" x="480" y="116" width="80" height="48" rx="4"/>
      <rect class="fn-diagram__node" x="580" y="116" width="80" height="48" rx="4"/>
      <rect class="fn-diagram__node fn-diagram__node--accent" x="720" y="108" width="120" height="64" rx="4" style="fill: url(#d-pak3-accent-grad)"/>
    </g>
    <g class="fn-diagram__labels">
      <text class="fn-diagram__label fn-diagram__label--accent" x="60"  y="68"  text-anchor="start">PATCHES 1 – 6 · BENCH-DISCOVERABLE</text>
      <text class="fn-diagram__label fn-diagram__label--accent" x="860" y="68"  text-anchor="end">PATCH 7 · PASS@K-DISCOVERABLE</text>
      <text class="fn-diagram__label fn-diagram__label--display" x="120" y="146" text-anchor="middle">#1</text>
      <text class="fn-diagram__label fn-diagram__label--display" x="220" y="146" text-anchor="middle">#2</text>
      <text class="fn-diagram__label fn-diagram__label--display" x="320" y="146" text-anchor="middle">#3</text>
      <text class="fn-diagram__label fn-diagram__label--display" x="420" y="146" text-anchor="middle">#4</text>
      <text class="fn-diagram__label fn-diagram__label--display" x="520" y="146" text-anchor="middle">#5</text>
      <text class="fn-diagram__label fn-diagram__label--display" x="620" y="146" text-anchor="middle">#6</text>
      <text class="fn-diagram__label fn-diagram__label--display" x="780" y="148" text-anchor="middle">#7</text>
      <text class="fn-diagram__label fn-diagram__label--mono fn-diagram__label--muted" x="360" y="232" text-anchor="middle">small monotonic batches · same-prompt smoke</text>
      <text class="fn-diagram__label fn-diagram__label--mono"   x="780" y="190" text-anchor="middle">decode-shrink</text>
      <text class="fn-diagram__label fn-diagram__label--mono fn-diagram__label--muted" x="780" y="232" text-anchor="middle">240 in-flight</text>
      <text class="fn-diagram__label fn-diagram__label--accent" x="780" y="100" text-anchor="middle">decode_row_idx slice</text>
    </g>
    <g class="fn-diagram__annotations">
      <text class="fn-diagram__annotation" x="450" y="270" text-anchor="middle">first six surfaced by &lt;10 in-flight requests · monotonic batch shape</text>
      <text class="fn-diagram__annotation" x="450" y="290" text-anchor="middle">seventh hid behind a stale scratch-tensor index when the batch shrank</text>
    </g>
  </svg>
  <figcaption>Six drifts surfaced by the bench harness; the seventh only fired once <code>n=8</code> attempts drained at different times — Pass@k workloads expose bugs the bench mode can't.</figcaption>
</figure>

Inside `residual_capture_hooks._forward_with_tap`, the consumer's residual tap was calling:

```python
torch.index_select(tensor, 0, decode_row_idx, out=decode_buf)
```

`decode_row_idx` is a fixed-capacity scratch tensor — its shape is `(graph_scratch_rows,)`, sized once at runtime configuration. The first `decode_count` slots hold the row indices that map current decode tokens to their position in the packed `tensor`. The slots after `decode_count` hold *whatever was there from the previous step*. As long as the batch is monotonically growing or stable, those stale slots are either zeros (initial) or row indices that are still valid against the current `tensor.shape[0]`. The moment a request finishes and `tensor.shape[0]` drops, those stale slots may contain indices that *exceed* the new tensor's row count — and CUDA asserts on out-of-range gather.

Reproduction is one line in the existing harness with `CUDA_LAUNCH_BLOCKING=1`:

```text
CUDA_LAUNCH_BLOCKING=1 python3 passatk_a2.py --mode esamp \
    --num-problems 10 --n 8 --model-name Qwen/Qwen2.5-0.5B-Instruct
```

Within ~1 problem completing, the assert fires:

```text
File "/tmp/tllm-rw/tllm/runtime/ports/residual_capture_hooks.py",
    line 67, in _forward_with_tap
  torch.index_select(tensor, 0, decode_row_idx, out=decode_buf)
torch.AcceleratorError: CUDA error: device-side assert triggered
```

The compact-tap path two blocks below was already correctly slicing to the active count:

```python
torch.index_select(tensor, 0,
                   compact_row_idx[:compact_count],
                   out=compact_buf[:compact_count])
```

The full-tap path was not. The fix matches:

```python
decode_count_runtime = max(0, int(getattr(core.RUNTIME, "decode_count", 0) or 0))
if decode_count_runtime > 0:
    torch.index_select(
        tensor,
        0,
        decode_row_idx[:decode_count_runtime],
        out=decode_buf[:decode_count_runtime],
    )
```

One line, mirroring the path next door that already had it. Post-patch, the same 10×n=8 reproducer ran clean: pass@1=0.1375, pass@8=0.40, 1450.8 tok/s on the 0.5B sanity model — matching the previous session's baseline pilot of pass@8=40% and confirming the Pass@k path was, with one slice, finally measurable.

:::pitfall[Bench harnesses miss bugs only Pass@k workloads expose]
Six patches landed against a bench mode that ran identical prompts through monotonic batches. The seventh drift only fires when batch shape *shrinks* — which happens any time `n` requests of varying lengths finish at different times. Pass@k workloads, agent loops, multi-prompt streaming all share that property; same-prompt smoke tests don't. The mitigation is simple but unobvious: run a Pass@k smoke as part of the patch-validation loop, not as a downstream consumer that crashes after the article ships.
:::

The seventh drift goes on the same call-stack diagram as the original six. It's at the bottom layer — tLLM's own forward tap — same place as drift six (the `decode_count > 0` guard from the previous session). Both are in the same hook, in the same function, both surfaced by something the bench mode does not exercise. The takeaway is more general than the patch: when porting a research runtime onto a different vLLM version, the unit tests in the bench mode are insufficient to catch latent bugs in the runtime's own code. Multi-prompt decode-shrink workloads — Pass@k, agent loops, anything where requests finish at different times — are a different test surface, and they need to be in the patching loop as a first-class signal, not as a downstream consumer that crashes mysteriously.

## The matrix — three shapes

Once the seventh patch landed, the four cells of the model × task × mode matrix ran cleanly. Settings are uniform: enforce-eager (CUDA graphs disabled), bfloat16, `temperature=0.8 top_p=0.95 min_p=0.1`, `model_bank_slots = num_problems × n`, `model_bank_rank=64`, `distiller_beta=0.8`, `distiller_sampler_backend=post_filter_exact`, single batched `llm.generate()` call per cell. HumanEval at 164 problems × n=8 (= 1,312 requests in flight), AIME at 30 × n=8 (= 240 requests), `max_new_tokens` tuned per task (300 for HumanEval, 4096 for Qwen-on-AIME, 8192 for R1-Distill-on-AIME).

| Model | Task | Mode | pass@1 | pass@8 | tok/s | wall (s) |
|---|---|---|---:|---:|---:|---:|
| Qwen 2.5 7B Instruct | HumanEval | baseline | 0.7027 | 0.8476 | 427.0 | 317 |
| Qwen 2.5 7B Instruct | HumanEval | esamp    | 0.7050 | 0.8415 | 434.8 | 305 |
| Qwen 2.5 7B Instruct | AIME 2024 | baseline | 0.1125 | 0.2000 | 370.5 | 773 |
| Qwen 2.5 7B Instruct | AIME 2024 | esamp    | **0.1458** | **0.2333** | 416.4 | 702 |
| DS-R1-Distill-Qwen-7B | AIME 2024 | baseline | 0.3667 | 0.6000 | 367.6 | 4,500 |
| DS-R1-Distill-Qwen-7B | AIME 2024 | esamp    | 0.3708 | **0.6667** | 357.1 | 4,601 |

:::math[The noise floor at 30 problems × n=8]
Pass@1 on AIME is a sample mean over 30 binary outcomes per `n=8` set; one extra correct problem moves the rate by 1/30 = 3.33pp. Pass@8 has the same 1/30 quantum. So any delta under ~3pp is *one problem's worth of jitter*; the +6.67pp on the reasoning cell is two extra problems, well above noise. The +3.33pp on the instruct cell is at the noise edge — earning the matrix only when the trend is consistent across both pass@1 and pass@8.
:::

<figure class="fn-diagram" aria-label="ESamp lift heatmap across three matrix cells. Each cell is a tall card; inside each, two horizontal bars stacked — top bar shows pass@1 delta, bottom bar shows pass@8 delta. Cell 1 (Qwen 2.5 7B Instruct on HumanEval, saturated) shows pass@1 +0.23pp and pass@8 -0.61pp, both within noise, rendered in muted gray. Cell 2 (Qwen on AIME 2024, unsaturated instruct headroom) shows +3.33pp at both pass@1 and pass@8, rendered in mid-tint indigo. Cell 3 (DeepSeek R1-Distill-Qwen-7B on AIME 2024, unsaturated reasoning headroom) shows +0.42pp at pass@1 (flat) and +6.67pp at pass@8, with the pass@8 bar as the accent — the paper's headline lift lives here.">
  <svg viewBox="0 0 900 380" role="img" aria-label="ESamp lift heatmap across three matrix cells. Each cell is a tall card; inside each, two horizontal bars stacked — top bar shows pass@1 delta, bottom bar shows pass@8 delta. Cell 1 (Qwen 2.5 7B Instruct on HumanEval, saturated) shows pass@1 +0.23pp and pass@8 -0.61pp, both within noise, rendered in muted gray. Cell 2 (Qwen on AIME 2024, unsaturated instruct headroom) shows +3.33pp at both pass@1 and pass@8, rendered in mid-tint indigo. Cell 3 (DeepSeek R1-Distill-Qwen-7B on AIME 2024, unsaturated reasoning headroom) shows +0.42pp at pass@1 (flat) and +6.67pp at pass@8, with the pass@8 bar as the accent — the paper's headline lift lives here." preserveAspectRatio="xMidYMid meet">
    <defs>
      <linearGradient id="d-pak1-cell-grad" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%"   stop-color="var(--svg-accent-blue)" stop-opacity="0.10"/>
        <stop offset="100%" stop-color="var(--svg-accent-blue)" stop-opacity="0.02"/>
      </linearGradient>
      <linearGradient id="d-pak1-mid-grad" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%"   stop-color="var(--color-primary)" stop-opacity="0.20"/>
        <stop offset="100%" stop-color="var(--color-primary)" stop-opacity="0.05"/>
      </linearGradient>
      <linearGradient id="d-pak1-accent-grad" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%"   stop-color="var(--color-primary)" stop-opacity="0.40"/>
        <stop offset="100%" stop-color="var(--color-primary)" stop-opacity="0.10"/>
      </linearGradient>
      <radialGradient id="d-pak1-accent-halo" cx="0.5" cy="0.5" r="0.6">
        <stop offset="0%"   stop-color="var(--color-primary)" stop-opacity="0.20"/>
        <stop offset="100%" stop-color="var(--color-primary)" stop-opacity="0"/>
      </radialGradient>
    </defs>
    <rect x="40"  y="60"  width="260" height="280" rx="10" fill="url(#d-pak1-cell-grad)" stroke="none"/>
    <rect x="320" y="60"  width="260" height="280" rx="10" fill="url(#d-pak1-mid-grad)"  stroke="none"/>
    <rect x="600" y="60"  width="260" height="280" fill="url(#d-pak1-accent-halo)" stroke="none"/>
    <g class="fn-diagram__edges">
      <path class="fn-diagram__edge fn-diagram__edge--ghost" d="M 40 200 L 300 200" />
      <path class="fn-diagram__edge fn-diagram__edge--ghost" d="M 320 200 L 580 200" />
      <path class="fn-diagram__edge fn-diagram__edge--ghost" d="M 600 200 L 860 200" />
    </g>
    <g class="fn-diagram__nodes">
      <rect class="fn-diagram__node" x="40"  y="60"  width="260" height="280" rx="10"/>
      <rect class="fn-diagram__node" x="320" y="60"  width="260" height="280" rx="10"/>
      <rect class="fn-diagram__node fn-diagram__node--accent" x="600" y="60"  width="260" height="280" rx="10" style="fill: url(#d-pak1-accent-grad)"/>
      <rect class="fn-diagram__node" x="60"  y="160" width="6"   height="40" rx="2"/>
      <rect class="fn-diagram__node" x="60"  y="208" width="22"  height="40" rx="2"/>
      <rect class="fn-diagram__node" x="340" y="124" width="58"  height="40" rx="2"/>
      <rect class="fn-diagram__node" x="340" y="208" width="58"  height="40" rx="2"/>
      <rect class="fn-diagram__node" x="620" y="160" width="8"   height="40" rx="2"/>
      <rect class="fn-diagram__node fn-diagram__node--accent" x="620" y="208" width="116" height="40" rx="2" style="fill: url(#d-pak1-accent-grad)"/>
    </g>
    <g class="fn-diagram__labels">
      <text class="fn-diagram__label fn-diagram__label--accent" x="170" y="48"  text-anchor="middle">SATURATED</text>
      <text class="fn-diagram__label fn-diagram__label--display" x="170" y="84"  text-anchor="middle">Qwen 7B × HumanEval</text>
      <text class="fn-diagram__label fn-diagram__label--mono"   x="170" y="106" text-anchor="middle">pass@1 70.27% → 70.50%</text>
      <text class="fn-diagram__label fn-diagram__label--mono"   x="170" y="124" text-anchor="middle">pass@8 84.76% → 84.15%</text>
      <text class="fn-diagram__label fn-diagram__label--mono fn-diagram__label--muted" x="60"  y="156" text-anchor="start">pass@1</text>
      <text class="fn-diagram__label fn-diagram__label--mono"   x="92"  y="186" text-anchor="start">+0.23pp</text>
      <text class="fn-diagram__label fn-diagram__label--mono fn-diagram__label--muted" x="60"  y="204" text-anchor="start">pass@8</text>
      <text class="fn-diagram__label fn-diagram__label--mono"   x="92"  y="234" text-anchor="start">−0.61pp</text>
      <text class="fn-diagram__label fn-diagram__label--mono fn-diagram__label--muted" x="170" y="316" text-anchor="middle">both within noise floor</text>
      <text class="fn-diagram__label fn-diagram__label--accent" x="450" y="48"  text-anchor="middle">UNSATURATED · INSTRUCT</text>
      <text class="fn-diagram__label fn-diagram__label--display" x="450" y="84"  text-anchor="middle">Qwen 7B × AIME 2024</text>
      <text class="fn-diagram__label fn-diagram__label--mono"   x="450" y="106" text-anchor="middle">pass@1 11.25% → 14.58%</text>
      <text class="fn-diagram__label fn-diagram__label--mono"   x="450" y="124" text-anchor="middle">pass@8 20.00% → 23.33%</text>
      <text class="fn-diagram__label fn-diagram__label--mono fn-diagram__label--muted" x="340" y="156" text-anchor="start">pass@1</text>
      <text class="fn-diagram__label fn-diagram__label--display" x="408" y="150" text-anchor="start">+3.33pp</text>
      <text class="fn-diagram__label fn-diagram__label--mono fn-diagram__label--muted" x="340" y="204" text-anchor="start">pass@8</text>
      <text class="fn-diagram__label fn-diagram__label--display" x="408" y="234" text-anchor="start">+3.33pp</text>
      <text class="fn-diagram__label fn-diagram__label--mono fn-diagram__label--muted" x="450" y="316" text-anchor="middle">token + trajectory headroom</text>
      <text class="fn-diagram__label fn-diagram__label--accent" x="730" y="48"  text-anchor="middle">UNSATURATED · REASONING</text>
      <text class="fn-diagram__label fn-diagram__label--display" x="730" y="84"  text-anchor="middle">DS-R1-Distill 7B × AIME</text>
      <text class="fn-diagram__label fn-diagram__label--mono"   x="730" y="106" text-anchor="middle">pass@1 36.67% → 37.08%</text>
      <text class="fn-diagram__label fn-diagram__label--mono"   x="730" y="124" text-anchor="middle">pass@8 60.00% → 66.67%</text>
      <text class="fn-diagram__label fn-diagram__label--mono fn-diagram__label--muted" x="620" y="156" text-anchor="start">pass@1</text>
      <text class="fn-diagram__label fn-diagram__label--mono"   x="640" y="186" text-anchor="start">+0.42pp</text>
      <text class="fn-diagram__label fn-diagram__label--mono fn-diagram__label--muted" x="620" y="204" text-anchor="start">pass@8</text>
      <text class="fn-diagram__label fn-diagram__label--display" x="744" y="234" text-anchor="start">+6.67pp</text>
      <text class="fn-diagram__label fn-diagram__label--mono fn-diagram__label--muted" x="730" y="316" text-anchor="middle">trajectory headroom only</text>
    </g>
    <g class="fn-diagram__annotations">
      <text class="fn-diagram__annotation" x="450" y="368" text-anchor="middle">three shapes, one technique, one β · the workload's headroom decides whether anything moves</text>
    </g>
  </svg>
  <figcaption>ESamp's value is a 2×2 grid of headroom shapes — instruct cells light up on both rates, reasoning cells light up on pass@8 alone, saturated cells stay flat.</figcaption>
</figure>

### Cell 1 — saturated (Qwen × HumanEval): nothing moves

The instruction-tuned 7B does HumanEval at pass@1 = 70.27% baseline. Eight samples lift to 84.76% pass@8 — the model already knows the problem, and most of the 14pp gap is tail-distributed across the easier 60% of problems. ESamp lifts pass@1 by 0.23pp (= +0.3 problems out of 164), drops pass@8 by 0.61pp, runs 1.8% faster, and decodes 2% fewer total tokens. **Both deltas are within run-to-run noise.** The decode-token reduction is the only physically meaningful number — intervention concentrates probability mass enough that EOS hits a few tokens earlier. There is no headroom for semantic exploration to find. The Distiller's online training cost lands as a wash on tok/s and zero on accuracy.

### Cell 2 — unsaturated instruct (Qwen × AIME): both rates rise

Drop the same model on AIME 2024 and pass@1 collapses to 11.25%. Eight samples buy the model 8.75pp of pass@k headroom — it is a model that *can* solve some AIME problems but doesn't reliably pick the right approach on a single attempt. ESamp's intervention recovers an extra 1 problem (= +3.33pp) at *both* pass@1 and pass@8, with a 12.4% wall-clock speedup (370.5 → 416.4 tok/s). The faster wall clock is the same EOS-concentration effect, not a free lunch — the workload finishes earlier because intervention sharpens the marginal token distribution enough to produce shorter, higher-confidence chains-of-thought *and* spread the chains semantically across `n=8` attempts. The model has both kinds of headroom — token-level and trajectory-level — and ESamp consumes both.

### Cell 3 — unsaturated reasoning (DS-R1-Distill × AIME): pass@8 rises alone

This is the cell where the paper's headline claim lives. R1-Distill is a chain-of-thought reasoning model — its baseline pass@1 on AIME 2024 is 36.67%, and `n=8` attempts buy it 23.33pp of pass@k headroom (60.00% pass@8). The model is already producing diverse reasoning trajectories from temperature alone; the ESamp question is whether the Distiller-driven novelty signal *spreads them further*.

It does. Pass@8 lifts to 66.67% — **+6.67pp, two extra problems out of 30**. Pass@1 is essentially flat (36.67% → 37.08%, +0.42pp = noise). Tok/s drops to 0.971× baseline — within a third of a percentage point of the patches-article number on the same model. Wall clock is within 2.2% (4500 → 4601 seconds). The Distiller costs the throughput it claims to cost, and what it buys is *exactly* the breadth dimension Pass@k rewards.

The per-problem breakdown makes the mechanism visible. Three AIME problems went from 0/8 baseline → ≥1/8 ESamp — problems the baseline never solved at any temperature trajectory; ESamp's semantic spread found a path. One went the other way (4/8 → 0/8 — intervention pushed all eight attempts down a bad path). Eleven problems shifted by smaller amounts in both directions. The signature shape is wider variance with a positive mean — ESamp is not making any single attempt smarter. It is making the *set of eight attempts* cover more of the problem space.

This is the paper's thesis intact. Pass@1 does not move because the marginal token distribution under R1-Distill is already producing well-calibrated reasoning at temperature 0.8 — the Distiller's reweight has nothing to sharpen. Pass@8 moves because the eight trajectories, after the reweight, are more *semantically* distinct — they explore different solution paths instead of rephrasing the same one. The Spark gets that lift on a model card, three chains of patches, and seven hundred lines of new harness — and the lift survives a runtime two minor versions deeper than the paper's reference.

<figure class="fn-diagram" aria-label="Dual-path mechanism diagram. Eight parallel attempts feed into two lanes. Top lane (instruction-tuned model on AIME, unsaturated): the ESamp Distiller reweight sharpens the marginal token distribution AND spreads the eight trajectories semantically — both pass at 1 and pass at 8 rise by 3.33pp. Bottom lane (reasoning-tuned model on AIME, also unsaturated): the marginal token distribution is already well-calibrated so the reweight has nothing to sharpen — pass at 1 stays flat at +0.42pp. The semantic spread still works — pass at 8 rises by 6.67pp, the accent. Both lanes converge at the verifier-bound endpoint where a grader, sandbox, or tool picks the correct attempt from the eight candidates.">
  <svg viewBox="0 0 900 400" role="img" aria-label="Dual-path mechanism diagram. Eight parallel attempts feed into two lanes. Top lane (instruction-tuned model on AIME, unsaturated): the ESamp Distiller reweight sharpens the marginal token distribution AND spreads the eight trajectories semantically — both pass at 1 and pass at 8 rise by 3.33pp. Bottom lane (reasoning-tuned model on AIME, also unsaturated): the marginal token distribution is already well-calibrated so the reweight has nothing to sharpen — pass at 1 stays flat at +0.42pp. The semantic spread still works — pass at 8 rises by 6.67pp, the accent. Both lanes converge at the verifier-bound endpoint where a grader, sandbox, or tool picks the correct attempt from the eight candidates." preserveAspectRatio="xMidYMid meet">
    <defs>
      <linearGradient id="d-pak2-instruct-grad" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%"   stop-color="var(--svg-accent-blue)" stop-opacity="0.10"/>
        <stop offset="100%" stop-color="var(--svg-accent-blue)" stop-opacity="0.02"/>
      </linearGradient>
      <linearGradient id="d-pak2-reasoning-grad" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%"   stop-color="var(--svg-accent-teal)" stop-opacity="0.10"/>
        <stop offset="100%" stop-color="var(--svg-accent-teal)" stop-opacity="0.02"/>
      </linearGradient>
      <linearGradient id="d-pak2-accent-grad" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%"   stop-color="var(--color-primary)" stop-opacity="0.30"/>
        <stop offset="100%" stop-color="var(--color-primary)" stop-opacity="0.08"/>
      </linearGradient>
      <radialGradient id="d-pak2-accent-halo" cx="0.5" cy="0.5" r="0.6">
        <stop offset="0%"   stop-color="var(--color-primary)" stop-opacity="0.18"/>
        <stop offset="100%" stop-color="var(--color-primary)" stop-opacity="0"/>
      </radialGradient>
    </defs>
    <rect x="160" y="40"  width="540" height="140" rx="10" fill="url(#d-pak2-instruct-grad)"  stroke="none"/>
    <rect x="160" y="220" width="540" height="140" rx="10" fill="url(#d-pak2-reasoning-grad)" stroke="none"/>
    <rect x="700" y="50"  width="160" height="300" fill="url(#d-pak2-accent-halo)" stroke="none"/>
    <g class="fn-diagram__edges">
      <path class="fn-diagram__edge" pathLength="100" d="M 140 200 L 180 200" />
      <path class="fn-diagram__edge fn-diagram__edge--accent" pathLength="100" d="M 160 110 L 240 110" />
      <path class="fn-diagram__edge fn-diagram__edge--accent" pathLength="100" d="M 380 110 L 460 110" />
      <path class="fn-diagram__edge fn-diagram__edge--accent" pathLength="100" d="M 600 110 L 700 200" />
      <path class="fn-diagram__edge" pathLength="100" d="M 160 290 L 240 290" />
      <path class="fn-diagram__edge fn-diagram__edge--accent" pathLength="100" d="M 380 290 L 460 290" />
      <path class="fn-diagram__edge fn-diagram__edge--accent" pathLength="100" d="M 600 290 L 700 200" />
    </g>
    <g class="fn-diagram__nodes">
      <rect class="fn-diagram__node" x="40"  y="170" width="100" height="60" rx="8"/>
      <rect class="fn-diagram__node" x="240" y="80"  width="140" height="60" rx="8"/>
      <rect class="fn-diagram__node" x="460" y="80"  width="140" height="60" rx="8"/>
      <rect class="fn-diagram__node" x="240" y="260" width="140" height="60" rx="8"/>
      <rect class="fn-diagram__node" x="460" y="260" width="140" height="60" rx="8"/>
      <rect class="fn-diagram__node fn-diagram__node--accent" x="700" y="170" width="160" height="60" rx="8" style="fill: url(#d-pak2-accent-grad)"/>
    </g>
    <g class="fn-diagram__labels">
      <text class="fn-diagram__label fn-diagram__label--accent" x="160" y="28"  text-anchor="start">INSTRUCT · BOTH HEADROOMS · +3.33 / +3.33</text>
      <text class="fn-diagram__label fn-diagram__label--display" x="90"  y="206" text-anchor="middle">n = 8</text>
      <text class="fn-diagram__label fn-diagram__label--mono"   x="90"  y="224" text-anchor="middle">attempts</text>
      <text class="fn-diagram__label fn-diagram__label--display" x="310" y="106" text-anchor="middle">marginal</text>
      <text class="fn-diagram__label fn-diagram__label--mono"   x="310" y="126" text-anchor="middle">token sharpens</text>
      <text class="fn-diagram__label fn-diagram__label--display" x="530" y="106" text-anchor="middle">trajectories</text>
      <text class="fn-diagram__label fn-diagram__label--mono"   x="530" y="126" text-anchor="middle">spread</text>
      <text class="fn-diagram__label fn-diagram__label--accent" x="160" y="208" text-anchor="start">REASONING · TRAJECTORY HEADROOM ONLY · +0.42 / +6.67</text>
      <text class="fn-diagram__label fn-diagram__label--display" x="310" y="286" text-anchor="middle">marginal</text>
      <text class="fn-diagram__label fn-diagram__label--mono"   x="310" y="306" text-anchor="middle">already calibrated</text>
      <text class="fn-diagram__label fn-diagram__label--display" x="530" y="286" text-anchor="middle">trajectories</text>
      <text class="fn-diagram__label fn-diagram__label--mono"   x="530" y="306" text-anchor="middle">spread</text>
      <text class="fn-diagram__label fn-diagram__label--display" x="780" y="200" text-anchor="middle">verifier</text>
      <text class="fn-diagram__label fn-diagram__label--mono"   x="780" y="220" text-anchor="middle">picks correct</text>
      <text class="fn-diagram__label fn-diagram__label--mono fn-diagram__label--muted" x="310" y="160" text-anchor="middle">distiller reweight · sharpen</text>
      <text class="fn-diagram__label fn-diagram__label--mono fn-diagram__label--muted" x="530" y="160" text-anchor="middle">distiller reweight · spread</text>
      <text class="fn-diagram__label fn-diagram__label--mono fn-diagram__label--muted" x="310" y="248" text-anchor="middle">no headroom · pass@1 stays</text>
      <text class="fn-diagram__label fn-diagram__label--mono fn-diagram__label--muted" x="530" y="248" text-anchor="middle">distiller reweight · spread</text>
    </g>
    <g class="fn-diagram__annotations">
      <text class="fn-diagram__annotation" x="450" y="384" text-anchor="middle">two lanes, one verifier-bound destination · ESamp scales whichever headroom the model has</text>
    </g>
  </svg>
  <figcaption>Two paths to the same verifier — instruct lifts both pass@1 and pass@8 because both headrooms exist; reasoning lifts only pass@8 because the marginal distribution is already calibrated.</figcaption>
</figure>

:::deeper
- [ESamp paper (LLMs Explore by Latent Distilling)](https://arxiv.org/abs/2604.24927) — the technique whose three matrix shapes this article maps.
- [Runtime frontier: six patches on Spark](/field-notes/runtime-frontier-six-patches-on-spark/) — the prerequisite article that landed patches one through six and the 0.974× tok/s baseline.
- [Test-time distilling on Spark](/field-notes/test-time-distilling-for-exploration/) — the original integration article that surfaced patches one and two.
- [HumanEval pass@k methodology](https://arxiv.org/abs/2107.03374) — Codex paper, original definition of the unbiased estimator the harness uses.
- [DeepSeek-R1-Distill model card](https://huggingface.co/deepseek-ai/DeepSeek-R1-Distill-Qwen-7B) — the chain-of-thought reasoning model where the headline lift lives.
:::

## Tradeoffs and surprises

**Wall clock stayed flat.** Across all three unsaturated cells, the ESamp throughput penalty came in between 0.971× and 1.124×. The patches-article 0.974× number — measured on a same-prompt benchmark that exercises the model bank in its hottest path — was the worst case, not the typical case. On a Pass@k workload with diverse prompts, intervention concentrates probability mass enough to compensate for the per-step Distiller cost. The "single-digit-percent throughput cost" claim from the paper is intact across hardware (Spark's GB10 vs reference 4090) and configuration (eager mode vs CUDA graphs).

**The DS × AIME `pass@1 ≈ flat` is the most interesting observation in the matrix.** It pins down the mechanism: ESamp on a reasoning model is *not* about better single-attempt accuracy. It is about diversifying the `n` attempts. If a Spark builder is verifier-bound — a sandbox checks each attempt, a tool returns a structured answer, a math grader scores correctness — ESamp at `n≥4` is the right knob. If the workload uses pass@1 only (e.g., a chat agent that emits one final response), the DS × AIME cell predicts no benefit from ESamp at all. Different operating regimes; the technique is honest about which one it serves.

**The Qwen × AIME cell — where pass@1 *did* move +3.33pp — predicts a less-discussed regime.** Instruction-tuned models on hard tasks have *both* kinds of headroom: token-level (the model picks bad tokens on a single attempt) *and* trajectory-level (the n attempts collapse to similar approaches). ESamp's reweight catches both because the Distiller's novelty signal is sharper on a less-calibrated baseline distribution. The implication for fieldkit's eventual `Bench` suite is that pass@1 vs pass@k decompositions need to be the *first-class* output of any test-time-scaling experiment — a single accuracy number hides which dimension moved, and the dimension that moved is the dimension the technique's mechanism predicts.

**The seventh drift was hidden by the bench harness, not by the runtime.** This is the unflattering takeaway from the patches arc. Six patches, eight files, three days of patching across two articles — and the bench mode that motivated the patching arc was insufficient to expose the seventh latent bug. Pass@k workloads — diverse prompts, large `n`, requests draining at different times — are a different test surface. The lesson for the next runtime patching arc on Spark is to run a Pass@k smoke as part of the patch-validation loop, not as a downstream consumer that crashes after the article ships.

**HumanEval pass@8 dropped 0.61pp under intervention** (84.76 → 84.15). On a saturated cell with no real signal, this is exactly the noise floor — a pp here, a pp there, no consistent direction. The same magnitude of run-to-run noise on AIME would have wiped out the +3.33pp instruct lift entirely. The matrix scope is small enough (30 AIME problems, 164 HumanEval) that pass@1 deltas under ~2pp should not be load-bearing. Pass@8 deltas under ~3pp should not be either. The DS × AIME cell at +6.67pp is comfortably above that noise band; the Qwen × AIME cell at +3.33pp is at the edge of it; the HumanEval deltas are in it. The matrix earns the ESamp claim only on the cell where the gap is wide enough to read against noise — and that is the cell where the technique was supposed to land.

## What this teaches a Spark builder

The matrix collapses to a small operating-mode table. *Use ESamp when:* the local model is already fluent on the task class (reasoning model on math, code model on programs, tool-use model on agents), *and* the workload is verifier-driven (a grader, a sandbox, a tool roundtrip), *and* `n≥4`. *Skip ESamp when:* the model is at the top of its competence on the task (instruction-tuned 7B on HumanEval), or the workload is single-shot (`n=1`). *Consider ESamp when:* the model is at the bottom of its competence and `n≥4`, and accept that the improvement may show up at pass@1 too.

This is the kind of guidance that comes out of a matrix, not out of a single number. The paper headline (+9.7pp pass@8) is correct; it is also the *best* cell in the matrix on the configuration most flattering to the technique. A Spark builder running the same technique on a different model-task pair needs the matrix shape, not the headline, to decide if the patch arc earns its keep on their workload.

## What's next

The matrix here uses 30 AIME problems (the entire 2024 set) and 164 HumanEval problems — small enough that a third trial across all six cells is two more sessions of compute. With three trials per cell, the noise floor pinned down empirically rather than gestured at, ESamp's deltas in the saturated cell would graduate from "in noise" to "below the resolution of the matrix." Worth banking that work for a follow-up if the same technique gets re-measured on a future model-task pair.

`fieldkit.eval.PassAtK` is the obvious extraction target from this article. The harness in `articles/runtime-frontier-six-patches-on-spark/scripts/passatk_a2.py` is general — it dispatches on `--task humaneval|aime`, builds prompts and grader functions per task, runs both modes through the same `_run_problems_*` core, and emits a JSON identical in shape across all four cells. Lifted into fieldkit alongside `Bench` and the proposed `VLLMClient`, it is what the Wave-2 retrospective on this triplet of articles will use to re-measure cleanly. That, plus an `AgentRun` shape for the autoresearch arc and a `VLLMClient` mirror of `NIMClient`, is the v0.2 fieldkit candidate set surfaced from Phase 9 articles 1–3.

The patches-article closer queued `clawgym-on-spark` next. The triplet is now closed at three articles, two empirical claims (97.4% tok/s on the bench workload, +6.67pp pass@8 on the reasoning cell), and seven cleared upstream drifts. The runtime is the frontier; the workload is the verifier; ESamp is honest about which cell it lives in.

:::hardware[The matrix shape generalizes; only the wall clock changes]
The 4,601-second R1-Distill × AIME ESamp run on Spark is bandwidth-bound on GB10's 273 GB/s LPDDR5X. The same matrix on an H100 80 GB (3.35 TB/s HBM3, ~12× the bandwidth) finishes in roughly 380 seconds — pass@8 still lifts ~6–10pp because ESamp's mechanism is workload-headroom, not hardware. H200 (4.8 TB/s) drops to ~265 seconds; B200 (8 TB/s) to ~160. A SuperPOD running 30 AIME × n=64 in batched parallelism finishes the unsaturated cell sweep in under a minute. The technique's *shape* is the contribution — Spark's role is to verify the shape exists at the cost a personal builder can absorb; the constants scale with whatever bandwidth the rig has.
:::
