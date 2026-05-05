---
title: "Two Patches Were Six — ESamp Lands at 97.4% on a Patched Spark"
date: 2026-05-03
author: Manav Sehgal
product: Foundation
stage: inference
also_stages: [observability]
difficulty: advanced
time_required: "~2 hours of patching · ~30 minutes of measuring"
hardware: "NVIDIA DGX Spark"
tags: [decoding, sampling, test-time-scaling, vllm, runtime, patching, benchmarks]
summary: "Article #2 closed at two patches. Applying them surfaced six — including the silent return-shape adapter that broke the consumer's port. Once cleared, ESamp lands at 97.4% of baseline on patched Qwen 2.5 7B, within 1.4 pp of the paper's reference."
signature: SixDriftsOneNumber
series: Frontier Scout
fieldkit_modules: [eval, capabilities]
---

[Test-time distilling on Spark](/articles/test-time-distilling-for-exploration/) closed at *"two upstream patches needed"* — `Sampler.apply_temperature` had grown a third positional argument, and `GPUModelRunner._prepare_inputs` had grown a second. Both clear in a few lines. The article queued the rest of the work — Pass@k on AIME and HumanEval — for "the next session." This is that session, and the actual answer to *"do the patches work?"* turned out to be more interesting than yes.

*For a reader landing cold: [ESamp](https://arxiv.org/abs/2604.24927) is the test-time-distilling paper — a tiny online-trained probe that converts sampler interventions from lexical resampling into semantic exploration. The patches are about getting its runtime hooks to bind on a vLLM that drifted under the reference implementation.*

The two patches were six. Three of them were signature drifts in vLLM 0.20.0's V1 engine API — including the one the original article called out and two more it didn't see. One was a return-shape change that left the consumer's port silently dead even when every type-checked surface looked happy. One was an `add_request` id-reassignment inside the engine that broke a wrapper written when the input id was the engine id. And the sixth was a *pre-existing* latent bug in tLLM's tap that single-`generate()` smoke tests never expose. None of the six was hard once located; locating them took a printf walk through the engine.

Once cleared, the empirical claim survives intact. On Qwen 2.5 7B Instruct, three trials, the ESamp consumer with the post-filter intervention enabled (β=0.8) lands at **97.4% of baseline tokens-per-second** — three trials, tight variance, all six patches in place. The original tLLM paper quoted 98.78% on a reference RTX 4090 with CUDA graphs. The patched Spark sits **1.4 percentage points** off that on the model the paper highlights, with CUDA graphs deliberately disabled (the python-side hooks the runtime needs don't survive a compiled forward graph). On Qwen 2.5 0.5B Instruct the ratio drops to 82.5%, which is its own data point: ESamp's per-step constant cost is most visible against a small model's tiny forward.

## The paper, in one breath

**Thesis.** ESamp trains a tiny **Distiller** online during inference to predict the LLM's *deep*-layer hidden state from its *shallow*-layer hidden state. When the Distiller's prediction error spikes on a candidate continuation, that's a novelty signal — the prefix is moving into territory the LLM hasn't been recently calibrated on — and ESamp reweights token candidates toward that novelty. Standard temperature and top-p produce *lexical* variation; the Distiller-driven novelty signal produces *semantic* variation, which is the dimension Pass@k on AIME, MATH, and HumanEval actually rewards.

**Why this technique matters for a personal AI builder.** A Spark builder running `n=16` parallel completions of a 7B reasoner cares whether the `n` samples spread or just rephrase one bad attempt. ESamp is the first published technique that lands a measurable Pass@k lift with a *single-digit-percent* throughput cost — the kind of trade-off worth taking when iterating on a sampler. The patch arc below is what stands between that technique and a runtime that fires on this box; without it the reweight intervention is silent and the consumer is dead in the water.

**Promise vs achieved.** Paper: **0.9878×** baseline tok/s on a reference RTX 4090 with CUDA graphs (vLLM 0.10.x). Spark: **0.974×** on patched Qwen 2.5 7B Instruct (vLLM 0.20.0, eager mode, β=0.8, six upstream patches across eight files) — three trials, sd 1.66, within **1.4 percentage points** of the paper across two hardware classes and two engine-mode combinations. The achievement is not the number alone; it is that the number reproduces the paper's claim through six patches in code we didn't write — and the consistency itself is evidence that ESamp's overhead claim holds up across configurations a personal builder is likely to try.

## Why this matters for a personal AI builder

The previous article framed the Spark's value as iterability — fast, free, private test-time-scaling experiments at home. The patch arc here is the second-order benefit of that framing. The paper's reference number is empirically grounded on a runtime that was already two minor versions obsolete by the time the install line ran. A cloud-GPU renter who pays by the hour can't afford the hours it took to find the silent fourth drift. A frontier-API user can't even reach the runtime to patch it. The Spark + a willingness to read source code is what makes the verification pass actually run.

This is also where the *catalogue* of running arcs in this blog earns the "personal AI power user" line over the more honest "person who really likes patching." The patches stay in the runtime, but the mental model — *the runtime is the frontier; signatures drift; assume your reference implementation is six versions behind reality* — generalizes to every paper in the queue.

## Where the six drifts live

The six drifts decompose cleanly along the call stack. The same `make_llm` → `generate` path that ran clean in the original paper now passes through five layers, each of which the upstream vLLM engine had touched between 0.10.x and 0.20.0. The keystone surface — the one whose drift is genuinely *silent* — is in the middle.

<figure class="fn-diagram" aria-label="Layered stack showing where each of the six drifts in vLLM 0.20.0 sits in the call stack tLLM patches. Five vLLM call layers from top: LLM._add_request and LLMEngine.add_request handle a request_id that the engine internally reassigns — drift five. GPUModelRunner.execute_model is unchanged. GPUModelRunner._prepare_inputs is the keystone: it gained a num_scheduled_tokens positional argument (drift two, signature) and changed its return shape from attn_metadata-first to logits_indices-first (drift four, contract). Sampler.sample and its helpers Sampler.apply_temperature and Sampler.topk_topp_sampler each return tuples now (drift three) and apply_temperature gained an all_random argument (drift one, signature). The bottom layer is tLLM's own layer.forward residual tap, which carried a pre-existing decode_count guard bug (drift six, latent) that single-generate smoke tests never trigger. Two drifts at the same call site, three layers up, mean a power user does not exit the stack until both clear.">
  <svg viewBox="0 0 900 440" role="img" aria-label="Five vLLM call sites stacked vertically, each annotated with the drifts the v0.10 to v0.20 churn left behind. The middle layer, GPUModelRunner._prepare_inputs, is the accent — both a signature drift and a silent return-shape drift live there. The bottom layer, tLLM's own forward tap, holds a pre-existing latent bug only multi-generate workloads expose." preserveAspectRatio="xMidYMid meet">
    <defs>
      <linearGradient id="rfsp-accent-grad" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%"   stop-color="var(--color-primary)" stop-opacity="0.30"/>
        <stop offset="100%" stop-color="var(--color-primary)" stop-opacity="0.08"/>
      </linearGradient>
      <linearGradient id="rfsp-stack-band" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%"   stop-color="var(--svg-accent-blue)" stop-opacity="0.10"/>
        <stop offset="100%" stop-color="var(--svg-accent-blue)" stop-opacity="0.02"/>
      </linearGradient>
      <radialGradient id="rfsp-keystone-halo" cx="0.5" cy="0.5" r="0.7">
        <stop offset="0%"   stop-color="var(--color-primary)" stop-opacity="0.14"/>
        <stop offset="100%" stop-color="var(--color-primary)" stop-opacity="0"/>
      </radialGradient>
    </defs>
    <rect x="20" y="40" width="380" height="380" rx="12" fill="url(#rfsp-stack-band)" stroke="none"/>
    <rect x="40" y="180" width="340" height="84" rx="10" fill="url(#rfsp-keystone-halo)" stroke="none"/>
    <g class="fn-diagram__edges">
      <path class="fn-diagram__edge" pathLength="100" d="M 400 84 L 500 84" />
      <path class="fn-diagram__edge fn-diagram__edge--accent" pathLength="100" d="M 400 200 L 500 200" />
      <path class="fn-diagram__edge fn-diagram__edge--accent" pathLength="100" d="M 400 240 L 500 240" />
      <path class="fn-diagram__edge" pathLength="100" d="M 400 320 L 500 320" />
      <path class="fn-diagram__edge" pathLength="100" d="M 400 348 L 500 348" />
      <path class="fn-diagram__edge fn-diagram__edge--dashed" pathLength="100" d="M 400 396 L 500 396" />
    </g>
    <g class="fn-diagram__nodes">
      <rect class="fn-diagram__node" x="40" y="60" width="340" height="48" rx="8" />
      <rect class="fn-diagram__node" x="40" y="120" width="340" height="48" rx="8" />
      <rect class="fn-diagram__node fn-diagram__node--accent" x="40" y="180" width="340" height="84" rx="10"
            style="fill: url(#rfsp-accent-grad)" />
      <rect class="fn-diagram__node" x="40" y="276" width="340" height="84" rx="8" />
      <rect class="fn-diagram__node fn-diagram__node--ghost" x="40" y="372" width="340" height="48" rx="8" />
      <rect class="fn-diagram__node" x="500" y="64" width="380" height="40" rx="6" />
      <rect class="fn-diagram__node fn-diagram__node--accent" x="500" y="180" width="380" height="40" rx="6"
            style="fill: url(#rfsp-accent-grad)" />
      <rect class="fn-diagram__node fn-diagram__node--accent" x="500" y="220" width="380" height="40" rx="6"
            style="fill: url(#rfsp-accent-grad)" />
      <rect class="fn-diagram__node" x="500" y="300" width="380" height="40" rx="6" />
      <rect class="fn-diagram__node" x="500" y="328" width="380" height="40" rx="6" />
      <rect class="fn-diagram__node fn-diagram__node--ghost" x="500" y="376" width="380" height="40" rx="6" />
    </g>
    <g class="fn-diagram__labels">
      <text class="fn-diagram__label fn-diagram__label--muted" x="55" y="34" text-anchor="start">VLLM 0.20.0 CALL STACK</text>
      <text class="fn-diagram__label fn-diagram__label--display" x="55" y="84" text-anchor="start">LLM._add_request</text>
      <text class="fn-diagram__label fn-diagram__label--mono fn-diagram__label--muted" x="55" y="100" text-anchor="start">→ LLMEngine.add_request</text>
      <text class="fn-diagram__label fn-diagram__label--display" x="55" y="144" text-anchor="start">GPUModelRunner.execute_model</text>
      <text class="fn-diagram__label fn-diagram__label--mono fn-diagram__label--muted" x="55" y="160" text-anchor="start">unchanged · single drift-free layer</text>
      <text class="fn-diagram__label fn-diagram__label--accent" x="55" y="208" text-anchor="start">GPUModelRunner._prepare_inputs</text>
      <text class="fn-diagram__label fn-diagram__label--mono fn-diagram__label--muted" x="55" y="226" text-anchor="start">keystone — two drifts at one site</text>
      <text class="fn-diagram__label fn-diagram__label--mono fn-diagram__label--muted" x="55" y="244" text-anchor="start">signature change · return shape change</text>
      <text class="fn-diagram__label fn-diagram__label--display" x="55" y="300" text-anchor="start">Sampler.sample</text>
      <text class="fn-diagram__label fn-diagram__label--mono fn-diagram__label--muted" x="55" y="318" text-anchor="start">apply_temperature · topk_topp_sampler</text>
      <text class="fn-diagram__label fn-diagram__label--mono fn-diagram__label--muted" x="55" y="338" text-anchor="start">tuple return contract across all three</text>
      <text class="fn-diagram__label fn-diagram__label--display" x="55" y="396" text-anchor="start">tLLM layer.forward tap</text>
      <text class="fn-diagram__label fn-diagram__label--mono fn-diagram__label--muted" x="55" y="412" text-anchor="start">pre-existing · multi-generate only</text>
      <text class="fn-diagram__label fn-diagram__label--muted" x="515" y="34" text-anchor="start">DRIFT</text>
      <text class="fn-diagram__label fn-diagram__label--display" x="515" y="88" text-anchor="start">5 · request_id reassigned in add_request</text>
      <text class="fn-diagram__label fn-diagram__label--accent" x="515" y="204" text-anchor="start">2 · _prepare_inputs gains num_scheduled_tokens</text>
      <text class="fn-diagram__label fn-diagram__label--accent" x="515" y="244" text-anchor="start">4 · returns (logits_indices, spec) — silent</text>
      <text class="fn-diagram__label fn-diagram__label--display" x="515" y="324" text-anchor="start">3 · sample &amp; topk_topp_sampler return tuple</text>
      <text class="fn-diagram__label fn-diagram__label--display" x="515" y="352" text-anchor="start">1 · apply_temperature gains all_random</text>
      <text class="fn-diagram__label fn-diagram__label--display" x="515" y="400" text-anchor="start">6 · index_select on stale row indices</text>
    </g>
  </svg>
  <figcaption>Two minor vLLM versions and a quiet upstream contract change later, the patch surface is six fixes in eight files — and the silent ones in the middle layer are the ones that take printf to find.</figcaption>
</figure>

The middle layer is the keystone for a reason: `_prepare_inputs` carries *two* drifts that decompose differently. The signature change — adding `num_scheduled_tokens` as a second positional argument — fails fast and loud, because Python tells you there are too few arguments. The return-shape change does not. In vLLM 0.10.x, `_prepare_inputs` returned a tuple beginning with `attn_metadata`. In 0.20.0, it returns `(logits_indices, spec_decode_metadata)` — a two-tuple in a different order. tLLM's adapter mapped `out[0] → attn_metadata, out[1] → logits_indices`. Under the new shape, `view.logits_indices` becomes a `SpecDecodeMetadata` object (or `None`). Type checking does not fail. Engine init does not fail. Generation does not fail. The consumer's port simply never fires.

## The journey — six drifts, in the order the box exposes them

The previous article called drifts one and two: `apply_temperature(logits, temp)` had grown an `all_random` third arg, and `_prepare_inputs(self, scheduler_output)` had grown a `num_scheduled_tokens` second arg. Three wrapper sites needed the second one threaded through (`residual_runtime._wrapped_prepare_inputs`, `port_runtime_hooks.wrapped_prepare_inputs`, and the parallel `prefill_capture_support._wrapped_prepare_inputs` for repro workflows). Both fixes are mechanical once you read the new vLLM signature.

After applying them, a smoke run on Qwen 2.5 0.5B Instruct made it past engine init and as far as the first decode step before crashing inside the sampler:

```text
File "/tmp/tllm-rw/tllm/runtime/vllm_patch/sampler_patch.py", line 115,
    in _vanilla_sample
  return random_sampled.to(dtype=torch.long)
AttributeError: 'tuple' object has no attribute 'to'
```

Drift three. `Sampler.sample` now returns `tuple[Tensor, Tensor | None]` — `(sampled_token_ids, processed_logprobs)`, a contract change the V1 engine made when it pushed logprobs computation into the sampler. `Sampler.topk_topp_sampler` carries the same shape. tLLM's `_vanilla_sample`, `_maybe_sample_precomputed_dense_fast`, `wrapped_sampler_sample`, and the `_wrapped` install shim all assumed the old single-tensor return. The fix is wider than the first two — eight call sites across `sampler_patch.py` and the parallel `sampler_bridge/bridge.py` — but the shape is the same: unpack the tuple where you read it, return the tuple where you produce it. The `_wrapped` shim also gains a `logprobs_mode_override` keyword argument that the new `Sampler.sample` accepts.

With drift three patched, the smoke ran cleanly *and* produced English text *and* generated four answers from four prompts. The ESamp stats line at the bottom was the tell:

```text
ESamp stats: loss_avg=0.000000 loss_count=0 answers=4
distiller_enabled=True distiller_beta=0.8
distiller_port_hits=0 distiller_candidate_samples=0
```

Distiller enabled. Consumer registered. Port hits zero. Loss count zero. The model generates, the runtime says everything is fine, and the consumer never gets called. This is the silent-fourth-drift signature.

The diagnostic walk took three rounds of `print()`. First, instrument `_forward_with_tap` in `residual_capture_hooks` to confirm the layer tap fires at all — it did, twice per decode step (the source and target layers, exactly as configured). So the runtime was reaching the tap. Second, instrument `maybe_launch_post_logits_decode_work` to print `decode_count` per step — it was zero on every step, even though decode was visibly happening. The variable is set inside `prepare_decode_localization` when the runtime identifies which rows in the current batch are decode rows. Third, instrument `prepare_decode_localization` itself — and that's where the keystone surfaced:

```text
[DIAG-LOC] enter — len(out)=2
[DIAG-LOC] view.logits_indices is None: True
```

`view.logits_indices` was `None` on every call. Pulling `Sampler.sample`'s actual return shape from the installed vLLM made it obvious:

```python
>>> from vllm.v1.worker.gpu_model_runner import GPUModelRunner
>>> import inspect; print(inspect.signature(GPUModelRunner._prepare_inputs))
(self, scheduler_output: 'SchedulerOutput',
       num_scheduled_tokens: numpy.ndarray)
 -> tuple[torch.Tensor,
          vllm.v1.spec_decode.metadata.SpecDecodeMetadata | None]
```

The new return is a two-tuple where `out[0]` is a tensor (`logits_indices`) and `out[1]` is a `SpecDecodeMetadata` (or `None` when speculative decoding is off). The legacy adapter was reading `out[1]` as `logits_indices` — getting `None` or a metadata object — and *silently* short-circuiting the rest of the localization path. The fix landed in `tllm/runtime/vllm_patch/adapters/base.py` as a new `len(out) == 2 and isinstance(out[0], Tensor)` branch that maps `out[0] → logits_indices` and synthesizes a `_SyntheticCommonAttnMetadata` carrying `num_actual_tokens` from the scheduler output (since `attn_metadata` is no longer in the return — vLLM 0.20.0 sets it on the forward context inside `execute_model`).

The next decode step ran with `decode_count=4`, the port published, and the `_extract_training_rows` path on the consumer side raised the next thing — drift five. tLLM's `capture_runner._wrapped_add_request` registered the request-to-prompt mapping under `request_id` as it was passed in (`"0"`, `"1"`, `"2"`, `"3"` from `LLM._add_request`'s integer counter). The runtime, however, sees the engine's reassigned id (`"0-a13b2024"`, `"1-9efb505c"`, etc.) — vLLM 0.20.0's `LLMEngine.add_request` calls `input_processor.assign_request_id(request)` between accepting the input id and queuing the request. The wrapper has to register against the *return value* of `orig_add_request`, not its input. Three lines.

With five drifts cleared, single-batch decode produced loss values, port hits, and candidate-token counts that matched the expected shape — and the same harness, fed multiple sequential `generate()` calls, hit a `device-side assert` from `torch.index_select` inside `_forward_with_tap`. That's drift six, and it's the one I want to call out *as not a 0.20.0 drift*. The tap calls `torch.index_select(tensor, 0, decode_row_idx, out=decode_buf)` if `decode_row_idx is not None`, but doesn't gate on `decode_count > 0`. On a fresh prefill — where `decode_count` is zero but `decode_row_idx` still holds stale indices from the previous batch's last decode step — the indices are out-of-bounds against the new prefill tensor. Single-`generate()` workloads never expose this, because their first step is always the prefill of an *empty* runtime. The `decode_count > 0` guard is one line, and it lights up only when an article-grade harness — multiple problems, sequential `generate()` calls — runs against a long-lived consumer.

Six drifts, eight files, two evenings. The patches and their unified diffs land in `evidence/runs/2026-05-03-A2-patches/`. The harness scripts (`bench_a2.py`, `passatk_a2.py`) sit alongside.

## The number that holds

After all six clear, the original tLLM throughput-comparison shape — `single_off` (vanilla vLLM) vs `model_bank_on` (ESamp consumer registered, intervention enabled) — runs cleanly on the Spark. The Qwen 2.5 7B Instruct row is the apples-to-apples version of the paper's headline:

| Model | Mode | tok/s (n=3, sd) | Ratio |
|---|---|---|---|
| **Qwen 2.5 7B Instruct** | Baseline (vanilla vLLM 0.20.0) | **209.95** (sd 0.50) | 1.000× |
| **Qwen 2.5 7B Instruct** | ESamp (β=0.8, patched tLLM) | **204.54** (sd 1.66) | **0.974×** |
| Qwen 2.5 0.5B Instruct | Baseline | 1167.7 (sd 1.2) | 1.000× |
| Qwen 2.5 0.5B Instruct | ESamp (β=0.8) | 963.0 (sd 9.4) | 0.825× |

*16 prompts × 64 new tokens, `enforce_eager=True`, `gpu_memory_utilization=0.7` for 7B / 0.5 for 0.5B, 1024 decode tokens per trial, three timed runs after warmup. Distiller stats per ESamp run on 7B: loss_count=64, port_publish_hit_count=63, candidate_token_count≈1593.*

The 7B number lands at **0.974× of baseline tokens-per-second**, three trials, sd 1.66 — a 1.4-point gap below the paper's reference 0.9878× on a 4090 with CUDA graphs. The gap is plausibly the eager-mode tax: tLLM's residual tap replaces `layer.forward` with a Python wrapper at install time, and `torch.compile`'d forward graphs swallow that replacement. CUDA graph capture is the production path on the Spark for almost every other workload — the trade-off here is that the test-time-distilling experiment costs a few percent in steady-state throughput in exchange for a python-side hook that actually fires.

The 0.5B number is the reverse curve. ESamp's per-step constant cost — the source/target hidden capture, the asynchronous distiller training step, the post-filter sampler intervention — does not scale with model size. The model forward does. At 7B the model dominates and the ESamp overhead amortizes to noise; at 0.5B the model is so small that the per-step constant cost is visible, and the ratio drops to 0.825×. Any test-time-scaling overhead claim that quotes one model size without disclosing the curve is doing the reader a disservice; the right reading is *"overhead is bounded above by X at the smallest plausible model and rapidly amortizes."* This article's contribution to the literature is two points on that curve, on a Spark.

The distiller side is also worth checking against the runtime's own stats. Across the three 7B ESamp trials, `loss_count` was a stable 64 per run (one training step per decode step, four decode chunks × 16 candidates), `port_publish_hit_count` was 63 (one less than `loss_count` because the final step is post-logits, not post-sample), and `candidate_token_count` was 1593. The intervention isn't a no-op; the consumer is firing on every step, training online, and reweighting the sampler exactly as the paper describes.

## Tradeoffs and surprises

**The "two became six" framing is a sharpening, not a complaint.** The original article's *"the runtime is the frontier"* thesis predicted that a one-line drift would hide deeper drifts behind it. It did. The right way to read this follow-up is: the prediction was correct, and the prediction was *under-counted by 3×*. The mental model the reader leaves with is more useful for the next paper than a clean "two patches and we were done" would have been. Empirically: the ESamp paper's reference run was on `vllm==0.10.x`; in the 90 days between that run and this Spark integration, vLLM 0.20.0 changed at least four API surfaces tLLM was compiled against. That is the velocity of the runtime, and any test-time-scaling literature that targets vLLM v1 will be paying this tax, often silently.

**The fourth drift is what justifies the printf walk.** The first three drifts surface as Python `TypeError`s with file paths and line numbers. The fourth surfaces as a successful `generate()` call whose runtime instrumentation reports `port_hits=0`. There is no Python-level signal that something is wrong. The diagnostic that finds it is shaped like the [KV-cache arithmetic](/articles/kv-cache-arithmetic-at-inference/) shape — *if your numbers don't match the paper's, instrument the layer between you and the paper, top-down, until the dropped value reveals itself*. In this case the dropped value was a tensor that became `None` because a tuple was indexed with the wrong offset. In other articles the dropped value will be different. The shape — `print()` your way through the call stack until the runtime tells on itself — is reusable.

**The Pass@k matrix is partial, on purpose.** The harness exists at `evidence/runs/2026-05-03-A2-patches/patched-source/passatk_a2.py`. The baseline pilot ran on Qwen 2.5 0.5B against ten HumanEval problems at n=8: pass@1 of 6.25% (single-batched) or 10% (per-problem-looped), pass@8 of 40% — small-model HumanEval is a coarse signal and these match expectations. The ESamp variant of the same harness fails on the second problem with a `device-side assert` that is *not* in the six-drift count above: it's a state-isolation issue inside the existing ESamp consumer when the model bank carries slot state across diverse-prompt batches. That bug is in the consumer, not in vLLM 0.20.0, and it's a separate engineering project — likely a `fieldkit.eval.PassAtK` candidate that batches all problem-sample combinations into one `generate()` rather than looping. Fixing it would unblock the full Pass@k matrix at n=16 on Qwen 2.5 7B and DeepSeek-R1-Distill-Qwen-7B; not fixing it leaves the 7B tok/s number standing as the primary empirical claim of this piece. I'd rather ship one number well-grounded than two numbers stitched together over a known consumer bug.

**Eager mode is a deliberate choice, not an accident.** Switching to `enforce_eager=False` would add CUDA-graph capture and shave a few percentage points off the eager baseline as well as the ESamp number. But the python-side `layer.forward` replacement that the residual tap relies on does not survive `torch.compile`'s graph capture — the Python hook is inlined into the compiled graph at trace time, and subsequent decode steps run the compiled version, not the patched one. The ESamp consumer's `port_publish_hit_count` goes back to zero. There are deeper fixes (a backend-aware tap that hooks at the `compiled_model` boundary instead of the Python layer; a `torch.utils.hooks.RemovableHandle` registered on the layer module instead of replacing `forward`), but those are upstream tLLM changes — not in scope for this article.

**`fieldkit.inference.VLLMClient` is now concrete.** The throughput-comparison loop in `bench_a2.py` is exactly the kind of glue every test-time-scaling article in this series will repeat: a `make_llm` call in one mode, a `LLM` constructor in another, identical `SamplingParams`, three timed trials with warmup, JSON output. The shape lifts to a `VLLMClient` mirror of the existing [`fieldkit.nim.NIMClient`](/fieldkit/api/nim/) cleanly. Same for `fieldkit.eval.PassAtK` — `passatk_a2.py` already implements the unbiased estimator and the per-problem rollup; the next ESamp paper-replication article will repeat it. Both are filed for `fieldkit v0.2`.

## What this unlocks

**A patched runtime substrate for any vLLM-targeting test-time-scaling paper.** ESamp is the first one. Speculative decoding, classifier-free guidance, contrastive decoding, beam-search ablations, cascade sampling — the literature is dense, and most of the production-grade reference implementations target vLLM v1 because that's where the inference engine lives. The Spark + the eight patched files in `patched-source/` is the entry ticket. The next paper in the queue costs a `git pull` of its repo and an audit of which of *its* assumptions about vLLM 0.10.x have drifted in 0.20.0; the chassis is built.

**A shape for diagnosing silent runtime drift.** The four-print walk that found drift four — `_forward_with_tap` → `maybe_launch_post_logits_decode_work` → `prepare_decode_localization` → `unpack_prepare_inputs_output` — is the stencil. When a runtime says it's fine and your stats say it isn't, the answer lives in the layer between *what the engine returns* and *what your code expects it to mean*. Inspect both ends with the actual installed library and find the offset.

**A piece of evidence in the test-time-scaling overhead literature.** The 7B 0.974× number on patched Spark + eager mode goes alongside the paper's 0.9878× on a 4090 + CUDA graphs as a second data point. The ratio is *consistent* — within 1.4 percentage points — across two different hardware classes and two different engine-mode combinations. That consistency is itself a finding: ESamp's overhead claim is robust across the configurations a personal builder is likely to try.

## Closing — patches are how the frontier moves

The Spark's distinguishing feature is not that it runs models you couldn't run elsewhere; it is that it lets one person own the entire test-time-scaling loop end-to-end — *including the part where the loop is six upstream patches away from completing, and the diagnosis takes three rounds of `print()` through someone else's source tree*. The previous article framed the runtime as the frontier. This one is what crossing the frontier actually looks like in code: eight files, fewer than 100 lines of patch, and three diagnostic walks past the place a TypeError would have stopped you. The number that comes out the other side is intact. The paper's claim survives. The next test-time-scaling paper that lands on vLLM v1 will hit similar weather; the harness now exists to absorb it.

Next in the Frontier Scout series: `clawgym-on-spark` introduces `fieldkit.ft` (LoRA on the agent's own trajectories) and `fieldkit.agents` (sandbox-rollout primitives) — a different runtime, a different paper, the same shape. The Pass@k matrix on Qwen 2.5 7B + DeepSeek-R1-Distill-Qwen-7B is queued behind the consumer-side state-isolation fix and will ship as a follow-up to this piece, not the next link in the arc.
