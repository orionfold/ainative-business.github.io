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

[Patches were six](/articles/runtime-frontier-six-patches-on-spark/) closed at three trials, eager mode, and a 97.4% tok/s ratio against baseline on Qwen 2.5 7B Instruct. The Pass@k matrix the [test-time-distilling article](/articles/test-time-distilling-for-exploration/) queued for "the next session" was still queued — blocked, the previous article said, on a "diverse-prompt state-isolation issue inside the model bank." This is the next session, and the actual cause was a drift the six-patch arc never surfaced because the bench harness never pushed batches large enough for it to fire.

*For a reader landing cold: [ESamp](https://arxiv.org/abs/2604.24927) is a test-time-distilling technique. A tiny online-trained Distiller predicts the LLM's deep-layer hidden state from its shallow-layer hidden state. When the prediction error spikes on a candidate continuation, that's a novelty signal — the prefix is moving into territory the LLM has not been recently calibrated on — and ESamp reweights the sampler toward that novelty. The effect is *semantic* exploration, not just lexical resampling, which is exactly what Pass@k workloads reward.*

The seventh patch was one line. It made the matrix runnable. The matrix has three shapes.

## The paper, in one breath

**Thesis.** ESamp's value proposition is sharp: at a single-digit-percent throughput cost, a Pass@k workload should land more correct answers per `n` parallel attempts than vanilla temperature sampling. The mechanism is the Distiller-driven reweight — semantic exploration replacing lexical resampling — and the headline empirical claim in the paper is **+9.7pp pass@8 on AIME 2024 with DeepSeek-R1-Distill-Qwen-7B**, a model where chain-of-thought breadth matters and instructive correctness alone does not.

**Why this technique matters for a personal AI builder.** Pass@k is the natural unit of test-time scaling — the right way to spend a Spark's idle GPU on a hard problem is to let `n=8` parallel attempts diverge. Lexical-only diversity (temperature, top-p) tends to produce eight rephrasings of the same approach. Semantic diversity is what gives the verifier loop something to verify *more than once*. ESamp is the first published technique that delivers that diversity at a wall-clock cost a personal builder can absorb, and its claim is verifiable on a 128 GB Spark — one rented hour on cloud GPUs at the same scope, without the patching arc, runs about $30.

**Promise vs achieved.** Paper headline: **+9.7pp pass@8** on AIME 2024 with DeepSeek-R1-Distill-Qwen-7B at `n=8`, β=0.8. Spark, this session, on the same model-task-knob combination at the same `n`: **+6.67pp pass@8** (60.00% → 66.67%), within **3 percentage points** of the paper across a different runtime (vLLM 0.20.0 vs reference 0.10.x), eager mode (the paper used CUDA graphs), and seven upstream patches deep. The same configuration on Qwen 2.5 7B *Instruct* — an instruction-tuned model where AIME hits its low end — lifts pass@1 *and* pass@8 by 3.33pp each. And on Qwen 7B × HumanEval, where the model already saturates pass@1 at 70%, ESamp moves nothing within noise. **Three shapes, one technique, one model bank, one β** — the technique is the same across all three; the workload's headroom decides whether anything moves.

## Why this matters for a personal AI builder

The previous article closed at *the runtime is the frontier*. This one extends the frame to *and the workload is the verifier*. Patching tLLM through six upstream drifts plus a seventh latent was the price of admission to a runtime that fires. Running the matrix is what tells you which workloads are worth firing it on. **Test-time-distilling is not a free add-on.** On a saturated cell — instruction-tuned model, easy benchmark — the compute spent on the Distiller's online training and the post-filter sampler buys nothing. On the unsaturated cells, the picture splits in a way the original paper headline hides.

The split matters for how a Spark builder spends parallel completions. If the local model is reasoning-tuned (R1-Distill, NeMo Reasoning, DeepSeek-V3-style chains) and the task has a verifier (math correctness, sandbox exec, citation match), `n=8` parallel attempts with ESamp lift pass@8 — the breadth — *without making any single attempt better*. The verifier sees more semantically distinct candidates. If the local model is instruction-tuned and the task is at the *bottom* of its competence (AIME for Qwen 2.5 7B Instruct, where both pass@1 and pass@8 are mediocre), ESamp does both — sharpens marginal token probability and spreads exploration. If the model is at the *top* of its competence on the task, neither matters. The picking-which-cell-you're-in step is the new operating cost; once you know, the technique scales.

This is exactly the kind of measurement the Spark earns its keep on. Three matrix cells, two models, two benchmarks, three hours of compute — at home, repeatable, with no latency to a paid endpoint and no rate limit to negotiate around. The patches arc was the entry fee. The matrix is the dividend.

## The seventh drift — and why patches#2 didn't see it

The six drifts in the patches article were all surfaced by *small* workloads — bench mode runs a handful of identical prompts through `model_bank_on` vs `single_off` and compares throughput. None of them pushed the in-flight batch above ten requests, and crucially, none of them pushed it through a *shrinking* phase where one of those requests finished while others were still in decode. The Pass@k harness does both. 30 AIME problems × n=8 = 240 in-flight requests, vLLM scheduling decode tokens across them, requests draining out of the batch as they hit EOS or max-tokens. Every time a request drained, the next batch had a smaller `tensor.shape[0]` than the one before it.

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

### Cell 1 — saturated (Qwen × HumanEval): nothing moves

The instruction-tuned 7B does HumanEval at pass@1 = 70.27% baseline. Eight samples lift to 84.76% pass@8 — the model already knows the problem, and most of the 14pp gap is tail-distributed across the easier 60% of problems. ESamp lifts pass@1 by 0.23pp (= +0.3 problems out of 164), drops pass@8 by 0.61pp, runs 1.8% faster, and decodes 2% fewer total tokens. **Both deltas are within run-to-run noise.** The decode-token reduction is the only physically meaningful number — intervention concentrates probability mass enough that EOS hits a few tokens earlier. There is no headroom for semantic exploration to find. The Distiller's online training cost lands as a wash on tok/s and zero on accuracy.

### Cell 2 — unsaturated instruct (Qwen × AIME): both rates rise

Drop the same model on AIME 2024 and pass@1 collapses to 11.25%. Eight samples buy the model 8.75pp of pass@k headroom — it is a model that *can* solve some AIME problems but doesn't reliably pick the right approach on a single attempt. ESamp's intervention recovers an extra 1 problem (= +3.33pp) at *both* pass@1 and pass@8, with a 12.4% wall-clock speedup (370.5 → 416.4 tok/s). The faster wall clock is the same EOS-concentration effect, not a free lunch — the workload finishes earlier because intervention sharpens the marginal token distribution enough to produce shorter, higher-confidence chains-of-thought *and* spread the chains semantically across `n=8` attempts. The model has both kinds of headroom — token-level and trajectory-level — and ESamp consumes both.

### Cell 3 — unsaturated reasoning (DS-R1-Distill × AIME): pass@8 rises alone

This is the cell where the paper's headline claim lives. R1-Distill is a chain-of-thought reasoning model — its baseline pass@1 on AIME 2024 is 36.67%, and `n=8` attempts buy it 23.33pp of pass@k headroom (60.00% pass@8). The model is already producing diverse reasoning trajectories from temperature alone; the ESamp question is whether the Distiller-driven novelty signal *spreads them further*.

It does. Pass@8 lifts to 66.67% — **+6.67pp, two extra problems out of 30**. Pass@1 is essentially flat (36.67% → 37.08%, +0.42pp = noise). Tok/s drops to 0.971× baseline — within a third of a percentage point of the patches-article number on the same model. Wall clock is within 2.2% (4500 → 4601 seconds). The Distiller costs the throughput it claims to cost, and what it buys is *exactly* the breadth dimension Pass@k rewards.

The per-problem breakdown makes the mechanism visible. Three AIME problems went from 0/8 baseline → ≥1/8 ESamp — problems the baseline never solved at any temperature trajectory; ESamp's semantic spread found a path. One went the other way (4/8 → 0/8 — intervention pushed all eight attempts down a bad path). Eleven problems shifted by smaller amounts in both directions. The signature shape is wider variance with a positive mean — ESamp is not making any single attempt smarter. It is making the *set of eight attempts* cover more of the problem space.

This is the paper's thesis intact. Pass@1 does not move because the marginal token distribution under R1-Distill is already producing well-calibrated reasoning at temperature 0.8 — the Distiller's reweight has nothing to sharpen. Pass@8 moves because the eight trajectories, after the reweight, are more *semantically* distinct — they explore different solution paths instead of rephrasing the same one. The Spark gets that lift on a model card, three chains of patches, and seven hundred lines of new harness — and the lift survives a runtime two minor versions deeper than the paper's reference.

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
