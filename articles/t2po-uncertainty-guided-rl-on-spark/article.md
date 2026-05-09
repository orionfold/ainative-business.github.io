---
title: "T²PO on Spark — When the Training Pool Says 28/32 and Held-out Says 9/158"
date: 2026-05-09
author: Manav Sehgal
product: NeMo
stage: fine-tuning
also_stages: [agentic, training]
difficulty: advanced
time_required: "~18.5 hours wall (50 T²PO steps + three evals)"
hardware: "NVIDIA DGX Spark"
tags: [agentic, fine-tuning, lora, peft, rl, grpo, gigpo, t2po, exploration]
summary: "T²PO's two deltas on the Phase 6 ClawGym harness: mean turns 5.00 → 4.61, task_complete 154/158, but the per-assertion ceiling stays flat at 47.7%. The strongest training-side step (45) is the worst held-out checkpoint — pool saturation lies on a single Spark."
signature: T2poPoolVsHeldout
series: Frontier Scout
fieldkit_modules: [capabilities, eval, training]
---

The [Phase 6 GRPO article](/field-notes/clawgym-on-spark-grpo/) ended with a clean number — 34 steps, +97.5 pp on `task_complete`, mean turns collapsed 12 → 5. The pool converged at step 35 because every K=4 group on the 8-task batch saturated at SUCCESS, the gradient went to zero, and the loop exited the way it was supposed to. The next question was whether two algorithmic additions on top of GRPO — a token-level chain-of-thought cap and a turn-level uncertainty-resample — could push the per-step rollout count down further by *not generating turns the policy had nothing left to learn from*. The [T²PO paper](https://arxiv.org/abs/2605.02178) (ICML 2026) names the additions and reports the gains on cluster-scale runs.

This piece reproduces those two deltas on the same Phase 6 ClawGym harness — same model (Qwen 2.5 7B + LoRA), same SFT init, same 158-task held-out eval — and the headline does not read the way I expected. **Mean turns drops 5.00 → 4.61. `task_complete` ticks up 154 → 154 (parity). Per-assertion stays put at 47.7%, identical to where it sat at step 25 of training, identical to where Phase 6 GRPO landed at step 34.** The lift T²PO is reported to deliver did not materialize on a single Spark; what showed up instead is a set of findings about Spark-scale RL itself.

The most useful one — and the load-bearing claim of this article — is that **the training-side pool-pass metric does not predict held-out generalization** at this scale. Step 45 had the run's strongest training-side pool task_pass (28 of 32, 87.5%) and the run's *weakest* held-out task_pass (9 of 158, 5.7%). The strongest step on the training pool was the worst step on held-out. Held-out generalization at K=4 with 8 tasks per step samples a distribution different enough from the held-out 158 that pool saturation tells you almost nothing about the adapter you'd ship. That's a Spark-scale RL finding, not a T²PO finding, and it's the part of this run worth a deep-dive.

## Why this matters for a personal AI builder

There's a version of "RL on a personal box" where the training-side metric and the held-out metric move together, the loop terminates when the training metric saturates, and you ship the last adapter the loop saved. That version is what a cluster does: hundreds of parallel rollout workers, thousands of tasks per gradient step, training-side variance close enough to the eval distribution that the loss curve and the eval curve look like the same shape on different axes. On that machine, the loop's natural endpoint is the right adapter to keep.

On a Spark, with 8 tasks per step and K=4 rollouts each, the training pool is a 32-rollout sample of the policy's *current* on-distribution behavior — and that behavior is shaped by the same gradient updates the metric is supposed to be measuring. Pool saturation can mean "the policy solves this task family"; it can also mean "the policy has memorized the 8 tasks this step happened to sample." When the pool is small relative to the held-out set the article actually scores against, the second story dominates. **The right adapter to ship is the one that wins on held-out, not the one the loop's pool-converge terminator stops on.** This article is what it costs to learn that with one machine, a five-day-old paper, and a willingness to let the box run overnight.

## Architectural context — what T²PO adds to GRPO, in one turn

The Phase 6 GRPO loop is a kill-and-restart cycle: sample 8 tasks, run K=4 rollouts each at temperature 0.8, compute group-relative advantages, REINFORCE-with-KL on the bundle, restart vLLM with the new adapter. T²PO leaves that outer loop intact and changes what happens *inside* a rollout's individual turn. Two pieces, both running between when vLLM emits a candidate assistant turn and when the rollout commits it.

:::define[T²PO]
The Token-and-Turn Policy Optimization paper (arXiv 2605.02178, ICML 2026 spotlight) layers two uncertainty-guided controls on top of GRPO. **Token-level:** cap each assistant turn at `num_think_tokens` to bound the chain-of-thought budget. **Turn-level:** Test-time Distillation Sampling (TDS) — measure per-token entropy of the candidate turn, resample if entropy disagrees with the prior turn by an `eta_threshold` margin, up to `max_try` retries. The thesis is that uncertainty-aware exploration finds a better policy per gradient step than vanilla GRPO does at the same wall budget.
:::

<figure class="fn-diagram" aria-label="Inside one T²PO rollout turn: vLLM generates an assistant turn capped at 450 think tokens, top-20 token logprobs feed an entropy estimate, TDS compares it to the prior turn's entropy and either accepts the turn or regenerates up to two times; only after acceptance does the turn execute against the sandbox.">
  <svg viewBox="0 0 900 440" role="img" preserveAspectRatio="xMidYMid meet" aria-label="Inside one T²PO rollout turn: vLLM generates an assistant turn capped at 450 think tokens, top-20 token logprobs feed an entropy estimate, TDS compares it to the prior turn's entropy and either accepts the turn or regenerates up to two times; only after acceptance does the turn execute against the sandbox.">
    <defs>
      <linearGradient id="t2po-flow-grad" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%" stop-color="var(--color-primary)" stop-opacity="0.30"/>
        <stop offset="100%" stop-color="var(--color-primary)" stop-opacity="0.08"/>
      </linearGradient>
      <radialGradient id="t2po-tds-halo" cx="0.5" cy="0.5" r="0.7">
        <stop offset="0%" stop-color="var(--color-primary)" stop-opacity="0.12"/>
        <stop offset="100%" stop-color="var(--color-primary)" stop-opacity="0"/>
      </radialGradient>
      <linearGradient id="t2po-lane-grad" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%" stop-color="var(--svg-accent-blue)" stop-opacity="0.10"/>
        <stop offset="100%" stop-color="var(--svg-accent-blue)" stop-opacity="0.02"/>
      </linearGradient>
    </defs>
    <rect x="40" y="80" width="820" height="180" rx="10" fill="url(#t2po-lane-grad)" stroke="none"/>
    <g class="fn-diagram__edges">
      <path class="fn-diagram__edge" pathLength="100" d="M 200 170 L 320 170"/>
      <path class="fn-diagram__edge" pathLength="100" d="M 460 170 L 560 170"/>
      <path class="fn-diagram__edge fn-diagram__edge--accent" pathLength="100" d="M 700 170 L 820 170"/>
      <path class="fn-diagram__edge fn-diagram__edge--dashed" pathLength="100" d="M 630 220 C 630 290, 380 290, 380 220"/>
    </g>
    <g class="fn-diagram__nodes">
      <rect class="fn-diagram__node" x="60" y="130" width="140" height="80" rx="8"/>
      <rect class="fn-diagram__node" x="320" y="130" width="140" height="80" rx="8"/>
      <rect class="fn-diagram__node fn-diagram__node--accent" x="560" y="130" width="140" height="80" rx="8" style="fill: url(#t2po-flow-grad)"/>
      <rect x="560" y="130" width="140" height="80" rx="8" fill="url(#t2po-tds-halo)" stroke="none"/>
      <rect class="fn-diagram__node" x="820" y="130" width="40" height="80" rx="8"/>
      <rect class="fn-diagram__node fn-diagram__node--ghost" x="320" y="280" width="320" height="80" rx="8"/>
    </g>
    <g class="fn-diagram__labels">
      <text class="fn-diagram__label" x="130" y="158" text-anchor="middle">prompt + history</text>
      <text class="fn-diagram__label fn-diagram__label--mono" x="130" y="180" text-anchor="middle">turn N input</text>
      <text class="fn-diagram__label" x="390" y="158" text-anchor="middle">vLLM generate</text>
      <text class="fn-diagram__label fn-diagram__label--mono" x="390" y="180" text-anchor="middle">max_tokens=450</text>
      <text class="fn-diagram__label fn-diagram__label--mono" x="390" y="195" text-anchor="middle">logprobs, top_logprobs=20</text>
      <text class="fn-diagram__label" x="630" y="158" text-anchor="middle">TDS check</text>
      <text class="fn-diagram__label fn-diagram__label--mono" x="630" y="180" text-anchor="middle">|H_t − H_t-1| ∈ (0, 0.3)</text>
      <text class="fn-diagram__label fn-diagram__label--mono" x="630" y="195" text-anchor="middle">accept or regen</text>
      <text class="fn-diagram__label fn-diagram__label--mono" x="840" y="175" text-anchor="middle">exec</text>
      <text class="fn-diagram__label" x="480" y="308" text-anchor="middle">resample, max_try=2</text>
      <text class="fn-diagram__label fn-diagram__label--mono" x="480" y="330" text-anchor="middle">~6.4 regens / rollout (mean)</text>
    </g>
    <g class="fn-diagram__annotations">
      <text class="fn-diagram__annotation" x="260" y="160" text-anchor="middle">~33 s/turn</text>
      <text class="fn-diagram__annotation" x="510" y="160" text-anchor="middle">+33% wall</text>
      <text class="fn-diagram__annotation" x="760" y="160" text-anchor="middle">accepted turn</text>
    </g>
  </svg>
  <figcaption>The two T²PO additions sit between vLLM emitting a candidate turn and the rollout committing it. Token-level: cap the candidate at 450 think tokens. Turn-level: if entropy disagrees with the prior turn by under 0.3, regenerate — up to twice. The +33% wall per rollout is the cost; the question is whether the policy reaches a better minimum because of it.</figcaption>
</figure>

The token-level cap is one config knob. `num_think_tokens=450` flows through to vLLM as the `max_tokens` on every generate call, and that's it — the cap fires whether or not the turn would have been longer. The turn-level addition is more interesting. Each generated turn carries token-by-token logprobs back from vLLM (`logprobs=True, top_logprobs=20`), the rollout driver computes mean per-token entropy from the top-20 distribution, and TDS compares it to the prior turn's entropy. If `|H_t − H_{t-1}|` lands in `(0, 0.3)` — small but non-zero, the regime where the policy is "between" two strategies — the turn is regenerated, up to `max_try=2` times. The implementation is roughly 120 LOC of glue around vLLM's existing OpenAI-shaped completions endpoint.

:::define[Test-time Distillation Sampling]
TDS is T²PO's turn-level mechanism for resampling under controlled uncertainty. After vLLM generates a candidate turn, the driver computes mean per-token entropy from the top-20 logprobs and compares it to the prior turn's entropy. Turns where the entropy delta is *small but non-zero* — `|ΔH| ∈ (0, eta_threshold)` — are regenerated, on the theory that those are the turns where the policy is least sure between two strategies and resampling produces useful exploration. Turns with zero or large entropy deltas are accepted as-is.
:::

The third piece — and the one that requires the trainer to know about T²PO — is GiGPO step-level credit assignment. GRPO computes one advantage per rollout from the trajectory's terminal reward; GiGPO additionally assigns a per-turn advantage based on whether each turn's bash command succeeded (`exit_code=0` ∧ ¬`parse_error`). The per-token policy loss weights each assistant token by `α·A_traj + β·A_step[turn_id]`, where the trainer flag `--gigpo-step-w 1.0` enables β = 1.0 (β = 0 reverts to vanilla GRPO).

:::define[GiGPO step advantages]
Group-in-Group Policy Optimization extends GRPO's single trajectory-level advantage with a second per-turn advantage. For K rollouts of the same task, GiGPO groups *at the same turn-index* across the K and computes a turn-N advantage from per-turn signals (here: did the bash command succeed). Each assistant token's gradient weight becomes `α·A_traj + β·A_step[turn_id]`. ClawGym's continuous shell observations don't admit upstream's anchor-state matching, so this run uses the simpler same-turn-index grouping.
:::

## The journey — 50 steps, three evals, and a flat ceiling

The kickoff was a 9-second-per-rollout faster start than Phase 6 (smoke validated end-to-end on 2 tasks × K=4 in 266 s wall). The full run took 18.5 hours over 50 gradient steps with two evals at step 25 and step 50, plus a third post-hoc eval against step 45's adapter when the per-step CSV showed step 45 had the run's strongest training-side metrics. Mean TDS regenerations per rollout: **6.39** — TDS fired aggressively, as the smoke had warned. Total trainer wall: 51.2 minutes; the rest of the 18.5 hours was rollouts (50 × ~17 minutes) plus three evals (~36 minutes each). KL stayed small the whole run (max 0.0034) and the weight-delta L2 held remarkably constant at ~0.0625, which says the loop was making consistent-magnitude updates without cumulative drift.

The training-side trajectory is the one I want to show first because it's the part that *did* improve cleanly:

| step | groups used | task_pass on pool | TC on pool | mean turns |
|---:|---:|---:|---:|---:|
| 1 | 7/8 | 20/32 | 23/32 | 7.31 |
| 11 | 7/8 | 8/32 | **30/32** | 5.03 |
| 25 | 4/8 | 12/32 | **32/32** | 3.78 |
| 45 | 1/8 | **28/32** | 32/32 | 3.66 |
| 50 | 3/8 | 4/32 | 29/32 | 4.53 |

Mean turns dropped from 7.3 to under 4 by step 23 and stayed there. `task_complete` first hit 100% at step 25 and held 32/32 thirteen times across the next 24 steps. By step 28, only one of eight sampled groups was producing usable advantage variance — the rest had K=4 rollouts all returning identical rewards, GRPO's natural mute condition. Step 45 was the run's standout step on every metric: 28 of 32 rollouts passed their tasks, every rollout stopped via `task_complete`, and mean turns sat at 3.66. The pool-converge terminator didn't fire because the loop's threshold is *all* groups producing zero advantage — usually one stayed productive, and the loop ran the full 50.

Then I ran the held-out eval at step 25 and step 50, plus the post-hoc step 45:

| step | task_pass | per-asrt | mean turns | TC | Δ vs P6 GRPO@34 |
|---:|---:|---:|---:|---:|---:|
| @25 | **12/158** | 47.6% (371/780) | 5.37 | 148/158 | −0.6 pp |
| @45 | **9/158** | 47.8% (373/780) | 4.87 | 150/158 | **−2.5 pp** |
| @50 | **11/158** | 47.7% (372/780) | **4.61** | **154/158** | −1.3 pp |

<figure class="fn-diagram" aria-label="Training-step timeline of pool task_pass versus held-out task_pass. X-axis spans 50 training steps. Y-axis shows task_pass as a percentage from 0 to 100. The pool task_pass trace (32-rollout sample, accent) zigzags wildly: 62.5 percent at step 1, 25 at step 11, 37.5 at step 25, peaks at 87.5 percent at step 45 (the highest point of the run), then collapses to 12.5 percent at step 50. The held-out task_pass trace (158-task population, ghost) sits in a narrow band near 7 percent across the only three measured points: 7.6 percent at step 25, 5.7 at step 45, 7.0 at step 50. A vertical highlight at step 45 marks the divergence — pool peak coincides with held-out trough; the 80-percentage-point gap is the article's load-bearing finding.">
  <svg viewBox="0 0 900 380" role="img" aria-label="Training-step timeline of pool task_pass versus held-out task_pass. X-axis spans 50 training steps. Y-axis shows task_pass as a percentage from 0 to 100. The pool task_pass trace (32-rollout sample, accent) zigzags wildly: 62.5 percent at step 1, 25 at step 11, 37.5 at step 25, peaks at 87.5 percent at step 45 (the highest point of the run), then collapses to 12.5 percent at step 50. The held-out task_pass trace (158-task population, ghost) sits in a narrow band near 7 percent across the only three measured points: 7.6 percent at step 25, 5.7 at step 45, 7.0 at step 50. A vertical highlight at step 45 marks the divergence — pool peak coincides with held-out trough; the 80-percentage-point gap is the article's load-bearing finding." preserveAspectRatio="xMidYMid meet">
    <defs>
      <linearGradient id="d-t2po1-plot-grad" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%"   stop-color="var(--svg-accent-blue)" stop-opacity="0.10"/>
        <stop offset="100%" stop-color="var(--svg-accent-blue)" stop-opacity="0.02"/>
      </linearGradient>
      <linearGradient id="d-t2po1-divergence-grad" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%"   stop-color="var(--color-primary)" stop-opacity="0.20"/>
        <stop offset="100%" stop-color="var(--color-primary)" stop-opacity="0.04"/>
      </linearGradient>
      <radialGradient id="d-t2po1-peak-halo" cx="0.5" cy="0.5" r="0.6">
        <stop offset="0%"   stop-color="var(--color-primary)" stop-opacity="0.30"/>
        <stop offset="100%" stop-color="var(--color-primary)" stop-opacity="0"/>
      </radialGradient>
    </defs>
    <rect x="100" y="40" width="740" height="240" fill="url(#d-t2po1-plot-grad)" stroke="none"/>
    <rect x="694" y="40" width="44"  height="240" fill="url(#d-t2po1-divergence-grad)" stroke="none"/>
    <rect class="fn-diagram__node fn-diagram__node--ghost" x="694" y="40" width="44" height="240" rx="0"/>
    <rect x="690" y="50" width="50" height="40" fill="url(#d-t2po1-peak-halo)" stroke="none"/>
    <g class="fn-diagram__edges">
      <path class="fn-diagram__edge fn-diagram__edge--ghost" d="M 100 280 L 840 280" />
      <path class="fn-diagram__edge fn-diagram__edge--ghost" d="M 100 220 L 840 220" />
      <path class="fn-diagram__edge fn-diagram__edge--ghost" d="M 100 160 L 840 160" />
      <path class="fn-diagram__edge fn-diagram__edge--ghost" d="M 100 100 L 840 100" />
      <path class="fn-diagram__edge fn-diagram__edge--ghost" d="M 100 40  L 840 40"  />
      <path class="fn-diagram__edge" pathLength="100" d="M 100 40 L 100 280" />
      <path class="fn-diagram__edge" pathLength="100" d="M 100 280 L 840 280" />
      <path class="fn-diagram__edge fn-diagram__edge--accent" pathLength="100" d="M 115 130 L 263 220 L 471 190 L 716 70 L 790 250" />
      <path class="fn-diagram__edge fn-diagram__edge--ghost" d="M 471 261.8 L 716 266.3 L 790 263.2" />
    </g>
    <g class="fn-diagram__nodes">
      <circle class="fn-diagram__dot fn-diagram__dot--accent" cx="115" cy="130" r="5"/>
      <circle class="fn-diagram__dot fn-diagram__dot--accent" cx="263" cy="220" r="5"/>
      <circle class="fn-diagram__dot fn-diagram__dot--accent" cx="471" cy="190" r="5"/>
      <circle class="fn-diagram__dot fn-diagram__dot--accent" cx="716" cy="70"  r="7"/>
      <circle class="fn-diagram__dot fn-diagram__dot--accent" cx="790" cy="250" r="5"/>
      <circle class="fn-diagram__dot" cx="471" cy="261.8" r="4"/>
      <circle class="fn-diagram__dot" cx="716" cy="266.3" r="4"/>
      <circle class="fn-diagram__dot" cx="790" cy="263.2" r="4"/>
    </g>
    <g class="fn-diagram__labels">
      <text class="fn-diagram__label fn-diagram__label--mono fn-diagram__label--muted" x="92" y="44"  text-anchor="end">100%</text>
      <text class="fn-diagram__label fn-diagram__label--mono fn-diagram__label--muted" x="92" y="104" text-anchor="end">75</text>
      <text class="fn-diagram__label fn-diagram__label--mono fn-diagram__label--muted" x="92" y="164" text-anchor="end">50</text>
      <text class="fn-diagram__label fn-diagram__label--mono fn-diagram__label--muted" x="92" y="224" text-anchor="end">25</text>
      <text class="fn-diagram__label fn-diagram__label--mono fn-diagram__label--muted" x="92" y="284" text-anchor="end">0</text>
      <text class="fn-diagram__label fn-diagram__label--mono fn-diagram__label--muted" x="100" y="22" text-anchor="start">task_pass · % of sampled tasks</text>
      <text class="fn-diagram__label fn-diagram__label--accent" x="100" y="332" text-anchor="start">50-STEP T²PO RUN · 18.5 H WALL</text>
      <text class="fn-diagram__label fn-diagram__label--mono fn-diagram__label--muted" x="115" y="304" text-anchor="middle">step 1</text>
      <text class="fn-diagram__label fn-diagram__label--mono fn-diagram__label--muted" x="263" y="304" text-anchor="middle">11</text>
      <text class="fn-diagram__label fn-diagram__label--mono fn-diagram__label--muted" x="471" y="304" text-anchor="middle">25</text>
      <text class="fn-diagram__label fn-diagram__label--mono fn-diagram__label--muted" x="716" y="304" text-anchor="middle">45</text>
      <text class="fn-diagram__label fn-diagram__label--mono fn-diagram__label--muted" x="790" y="304" text-anchor="middle">50</text>
      <text class="fn-diagram__label fn-diagram__label--display" x="716" y="56"  text-anchor="middle">87.5%</text>
      <text class="fn-diagram__label fn-diagram__label--mono"   x="678" y="80" text-anchor="end">pool · n=32</text>
      <text class="fn-diagram__label fn-diagram__label--mono fn-diagram__label--muted" x="450" y="248" text-anchor="middle">held-out · n=158 · ~5–8% across all three checkpoints</text>
    </g>
    <g class="fn-diagram__annotations">
      <text class="fn-diagram__annotation" x="450" y="356" text-anchor="middle">step 45 · pool peak (87.5%) coincides with held-out trough (5.7%) — 81.8pp gap</text>
    </g>
  </svg>
  <figcaption>Pool peak (87.5% at step 45) coincides with held-out trough (5.7% at step 45) — the same adapter looks like the run's best on a 32-rollout pool and its worst on the 158-task held-out set.</figcaption>
</figure>

The right column is the one to pay attention to: T²PO trails Phase 6 GRPO@34 on task pass at every checkpoint — by 0.6, 2.5, and 1.3 percentage points. The middle column is the load-bearing one for the negative result: **per-assertion sits at 47.6 / 47.8 / 47.7%, three flat numbers spanning 25 gradient steps**. Whatever T²PO is buying at the per-token weight or the entropy resample, it is not lifting the per-assertion ceiling. Mean turns is the only metric that improves monotonically across the three evals (5.37 → 4.87 → 4.61), and the gap to Phase 6 GRPO closes from +0.37 turns at eval-1 to −0.39 turns at eval-2. The model is getting genuinely faster as training progresses; it is not getting more correct.

:::math[The per-assertion ceiling, in three numbers]
Per-assertion is the fraction of synth-task assertions that pass on held-out: `passed / total = 371 / 780 = 47.56%` at step 25, `373 / 780 = 47.82%` at step 45, `372 / 780 = 47.69%` at step 50. The window across 25 gradient steps and a difference in adapter weights of 0.063 L2 is **0.26 percentage points**. The 47–48% number is what Phase 6 GRPO landed at too (49.9% at step 34). Whatever's gating the next 5pp on this benchmark, RL gradient steps with this reward shape on this pool aren't reaching it.
:::

## Verification — what success looks like on a Spark RL run

The thing the loop was supposed to accomplish, it accomplished. Compared to Phase 5 SFT — the article's actual baseline, since it's what the SFT-init adapter started from — the held-out 158 numbers move the way RL on top of SFT should make them move: task pass 10 → 11 (+0.6 pp), per-assertion 46.8 → 47.7% (+0.9 pp), mean turns 12.0 → 4.61 (−61%), `task_complete` 0/158 → 154/158 (+97.5 pp). Every metric is in the right direction. The shape of "RL unlearned the never-stop failure mode SFT taught" reproduces exactly. The Phase 6 number is the ceiling, not the floor.

The loop's mechanical success looks like a clean exit log (`=== loop complete in 66692s ===`), a per-step CSV that fills out monotonically, a weight-delta L2 that holds steady step over step, and three eval-step directories whose `comparison.json` files share the same shape and units. It looks like vLLM coming back up in 190–220 seconds at every step boundary and never failing the 360-second cold-start timeout. It looks like memory falling to 116 GiB free between trainer and rollout phases, climbing to ~28 GiB used during trainer steps with vLLM down, and never tripping the OOM landmine the Spark's unified memory has caught me on before. None of those numbers move the held-out per-assertion percentage, but they're what makes the experiment a real measurement instead of a crash.

:::why[Held-out numbers are the only ones that ship]
The training pool is 8 tasks per step × K=4 rollouts = 32 trajectories that the same gradient updates are shaping. A pool task_pass of 28/32 is the policy's on-distribution score against the policy's most recent updates. The 158-task held-out is the only sample that's policy-independent. When you ship an adapter, you ship it because of held-out; when you stop the loop, you should stop it because of held-out. On Spark, the gap between those two numbers can be 80 percentage points (step 45: 87.5% pool, 5.7% held-out). That gap is not noise. It's the wrong metric being used for the right decision.
:::

## Tradeoffs, gotchas, surprises

The biggest surprise is the one named already: pool task_pass and held-out task_pass disagreed by 81.8 percentage points at step 45. I went into the run thinking the natural endpoint was wherever the loop's pool-converge terminator decided; I came out thinking the loop should periodically eval against held-out and *that* trajectory is what you steer on. The cost of running an eval against held-out is real (~36 minutes per eval, three evals burn ~1.8 hours) but trivial against the run's 18.5 total. Phase 7 of this arc would set `--eval-every 10` instead of 25 and treat the held-out eval curve as the schedule's ground truth.

:::pitfall[Training-side metrics overfit the pool you're sampling from]
Step 45 had pool task_pass 28/32 (87.5%) and held-out task_pass 9/158 (5.7%). Same adapter, same prompts, same temperature, two eval populations. The 32-rollout pool is not a held-out sample of the policy's behavior; it's a reflection of the most recent gradient updates against the 8 tasks this step happened to draw. On a single Spark with K=4 and small pool sizes, the training-side curve overstates generalization by a factor that's specific to the run, not a constant you can correct for. Eval against held-out periodically; don't trust the loop's converge terminator alone.
:::

The second surprise is the per-assertion ceiling. I expected T²PO's entropy-aware resample to find higher-quality candidate turns at marginal-uncertainty boundaries — turns that the model would have committed to with vanilla GRPO but where a regenerate-and-recheck would land on a more-correct command. The mean TDS regen rate of 6.39/rollout says it *did* fire aggressively. The flat per-assertion numbers say the regenerated turns are not, in aggregate, more correct than the original ones — they're roughly the same quality, just averaged over more samples. That can mean the eta_threshold of 0.3 is too generous (most turns fall in `(0, 0.3)`, so most turns are getting resampled and the resample is closer to a temperature-perturbation than a directed retry), or it can mean the underlying policy's per-turn entropy is not actually correlated with per-turn correctness on this benchmark. Both are testable in a Phase 8.

The third surprise is on wall-time accounting. Phase 6 GRPO ran 34 steps in 8.5 hours; T²PO ran 50 steps in 18.5 hours. Per-step wall went from 15 minutes to 22 minutes — a +47% step cost. The arithmetic line is +33% per rollout from TDS regen overhead × 1.5× more steps = ~2× total wall, which matches. What surprised me is that the held-out per-assertion numbers don't cash that wall in for accuracy. I paid 10 hours for trajectories that don't move the metric I care about.

## What this unlocks

The negative result is itself a thing you can build on. **First**: a held-out-driven schedule for any RL-on-Spark loop. Replace the loop's pool-converge terminator with a held-out eval every 10 steps and a "best held-out so far" adapter pointer. The third eval (step 45) cost 36 minutes and would have changed which adapter I shipped if it had run inside the loop instead of after it. Two new lines in `t2po_loop.sh`'s eval cadence buy a different stopping rule.

**Second**: an extracted post-hoc-eval driver. The `eval_step.sh` script that ran the step-45 eval is now in the repo at `articles/t2po-uncertainty-guided-rl-on-spark/scripts/`, parametric over step number and pool path, reusable for any T²PO or GRPO run. If a future loop does converge on the held-out trajectory, the same script confirms the choice. If it doesn't, the same script finds the actual peak.

**Third**: a fieldkit primitive that's now ready to graduate. T²PO's TDS regenerate path needed exactly the per-turn message reconstruction that Phase 6 GRPO does inline at `grpo_train.py:reconstruct_messages()`. Two consuming use cases is what `fieldkit.agents.replay_messages_from_trajectory` was waiting on; the next fieldkit cut promotes it from `[Unreleased]` to v0.3.

:::deeper
- [T²PO paper (arXiv 2605.02178)](https://arxiv.org/abs/2605.02178) — the algorithmic source; per-token CoT cap + per-turn TDS, originally evaluated on ALFWorld and WebShop.
- [GiGPO paper (verl/trainer/ppo/core_algos.py)](https://github.com/volcengine/verl) — the upstream step-advantage implementation; T²PO's `compute_step_advantages_within_group` is a ClawGym-adapted port.
- [Phase 6 GRPO article](/field-notes/clawgym-on-spark-grpo/) — direct predecessor; same harness, same eval, no T²PO additions.
- [Phase 5 SFT article](/field-notes/clawgym-on-spark/) — the SFT init both this and Phase 6 build on.
- Phase 7 candidate (not yet written): held-out-driven schedule + smaller eta_threshold sweep.
:::

:::hardware[10 hours per RL run, days on a single H100]
T²PO on a Spark: 50 steps × 22 min/step + 3 × 36 min eval = 18.5 hr wall. The same 7B Qwen + LoRA fits on one H100 with vLLM at 4× the rollout throughput; 50 steps would take ~5 hours plus evals — call it 7 hours wall. A SuperPOD with 8 H100s and properly-distributed rollouts hits the same step count in under 2 hours but at $40-80/hr fully-loaded vs the Spark's $0/hr after acquisition. The Spark reading lets one person try three of these runs a week without a budget conversation. The frontier reading lets a team try thirty a day with one. Both are useful; only one of them is *yours*.
:::

## Closing

The Phase 6 GRPO article ended on a clean +97.5 pp claim. This one ends on a flat 47.7%. That's not a worse result; it's a different finding. **Phase 6 was about the algorithm doing what the algorithm promises.** This piece is about the loop's metric not being the metric you should be optimizing on a single-Spark RL run. The held-out eval is what generalizes; the pool task_pass is what's most recently been trained on. The 32-rollout sample at K=4 with 8 tasks per step is too small a window into the held-out 158 to trust as a stopping rule, and the gap is large enough — 81.8 percentage points at the run's peak — to flip which adapter you ship.

What this one machine lets one person do is run three of these experiments a week and learn what to measure. Not what's the best algorithm — that's what cluster runs are for. What's the right metric to *terminate the loop on*, what's the right eval cadence, what's the right pool size to make pool saturation actually mean something. Those questions don't have published answers because cluster-scale runs don't have to ask them. The Spark does. Next up: the held-out-driven schedule, with `--eval-every 10` and a "best so far" adapter pointer, and the question of whether a smaller `eta_threshold` (say, 0.1) would convert the TDS regen overhead into actual per-assertion lift.
