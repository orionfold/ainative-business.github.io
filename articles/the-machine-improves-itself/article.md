---
title: "The Machine Improves Itself — Closed-Loop RLVR on a DGX Spark, Where the Eval Harness Is the Reward"
date: 2026-06-03
author: Manav Sehgal
product: Foundation
stage: fine-tuning
difficulty: advanced
time_required: "~16 min read — a synthesis of a proven run plus the engine it became"
hardware: "NVIDIA DGX Spark"
tags: [rlvr, grpo, reinforcement-learning, fine-tuning, machine-that-builds-machines, fieldkit, dgx-spark]
summary: "Closed-loop RLVR on one box: an eval→reward→fine-tune loop where the Spark's own verifiers ARE the reward — no learned reward model. The hero finding is defensive: pick the checkpoint on a frozen held-out split, never the training pool, or the loop reports success while it regresses."
signature: ClosedLoopRlvr
status: published
also_stages: [training, agentic]
series: Machine that Builds Machines
book_chapters: [10, 11, 14]
fieldkit_modules: [rl, reward, eval, lineage]
---

[The meta-program opener](/field-notes/the-meta-program-on-spark/) ended on an admission: of the three beats a self-improving loop needs — engine, hands, pane — the pane was the least built, and the loop wasn't yet closed-loop in the strong sense. *"A fully autonomous eval → reward → fine-tune → re-eval cycle, where a verifier's score directly drives the next training run with no human in the middle, isn't wired. The pieces exist; the wiring is the work ahead."* This article is that wiring. The pane shipped (the [Arena control plane](/products/arena-control-plane/)), the hands shipped (the budget-governed overnight drain), and now the engine — `fieldkit.rl` plus `fieldkit.reward` — closes the loop. The box can improve a model from its own measured signal.

The claim that makes this more than another fine-tuning post is where the reward comes from. Reinforcement learning on language models is usually gated by the most expensive component in the stack: a *reward model* — a separately trained network, fed by a human-annotation pipeline, that scores outputs. The disruptive move in 2026-era post-training is to delete it. If you already have a deterministic verifier that can decide whether an answer is correct — a regex that checks IRAC structure, a judge that scores patent-claim validity against seven dimensions, a Spearman correlation against a prior-art ranking — then *that verifier is the reward function*. You don't learn a reward; you already wrote one. On a DGX Spark, where the [seven `fieldkit.eval` verifiers](/fieldkit/api/eval/) were built across a dozen articles before any of this, the reward model was sitting on disk the whole time.

:::define[RLVR]
Reinforcement Learning from Verifiable Rewards. Instead of a learned reward model scoring outputs (RLHF), a *deterministic verifier* — a checker that returns pass/fail or a graded score — supplies the reward directly. It works when correctness is checkable: math answers, structured-output conformance, code that compiles, a claim that validates. The 2026 reasoning-model wave (R1-class models) is largely RLVR at scale.
:::

## Why this matters for a personal AI builder

On a cloud platform, the reward model is the moat and the meter. You rent it, or you pay an annotation vendor to feed it, and either way the thing that decides "is this output good" lives behind someone else's API. That single dependency is what keeps reinforcement fine-tuning out of reach for an individual — not the GPU, the *judgment*. The Spark inverts it. When the verifier is a function you wrote, audited, and can `cat`, you own the reward function outright. There is no annotation pipeline to fund, no reward-model API to call mid-rollout, no network hop between "the model produced an answer" and "here is its score." The loop closes on one box, under one user, against models you quantized yourself.

That ownership is the edge-builder's version of the whole arc. The corpus is yours, the GPU is yours, the agent loop is yours — and now the part that on every other platform belongs to a vendor, *the signal that drives learning*, is also yours. The independence isn't "no cloud bill." It's that the thing teaching the model has no owner but you, and you can read every line of it before you trust it with a gradient.

:::why[The reward model is the thing you already built]
RLHF's cost center is the learned reward model and its annotation pipeline. RLVR replaces both with a verifier you already have. On the Spark the verifiers predate the loop by a dozen articles — so the most expensive component of a reinforcement-learning stack was already written, tested, and free. The engine just had to treat it as the reward.
:::

## Where this sits in the stack — the loop, and its one load-bearing defense

[GRPO](/fieldkit/api/rl/) is the algorithm under the hood, and its relevance to a single box is specific: it drops the value network. Classic policy-gradient RL needs a learned critic to estimate a baseline; GRPO replaces that critic with a *group* — sample K answers to the same prompt, score them all with the verifier, and let the group's mean be the baseline. No critic to train, no reward model to host. That is what makes reinforcement fine-tuning fit in 128 GB: the only model resident is the one you're training, plus one inference lane to sample from it.

:::define[GRPO]
Group Relative Policy Optimization. For each prompt, sample a *group* of K rollouts, score each with the reward, and compute each rollout's advantage as its score minus the group mean (optionally divided by the group's spread). The group *is* the baseline a value network would otherwise estimate — so GRPO drops the learned critic entirely. Single-GPU-friendly; the algorithm behind most 2026 open reasoning models.
:::

The architecture is a loop of five beats, and the diagram below is the anatomy of one step. But the beat that earns the accent isn't the clever one — it's the defensive one. The whole loop hinges on a single rule that is easy to get wrong and catastrophic when you do: **the checkpoint you ship is selected on a frozen held-out split, never on the training pool.** Skip that, and the loop will reliably tell you it succeeded while the model regressed. I'll spend the journey on why, because it's the most expensive lesson the Spark taught this arc.

<figure class="fn-diagram" aria-label="One step of the closed RLVR loop as five beats: sample a group of rollouts, score them with the verifier-as-reward, take a group-relative REINFORCE step on the LoRA, run the held-out gate every ten steps, and select the published checkpoint on the held-out score only. A dashed return arc carries the lifted checkpoint back to become the next step's policy.">
  <svg viewBox="0 0 900 440" role="img" aria-label="One step of the closed RLVR loop as five beats: sample a group of rollouts, score with the verifier-as-reward, take a group-relative REINFORCE step on the LoRA, run the held-out gate every ten steps, and select the published checkpoint on the held-out score only; a dashed return arc carries the lifted checkpoint back to become the next step's policy." preserveAspectRatio="xMidYMid meet">
    <defs>
      <linearGradient id="rlvr-flow-band" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%"   stop-color="var(--svg-accent-blue)" stop-opacity="0.02"/>
        <stop offset="50%"  stop-color="var(--svg-accent-blue)" stop-opacity="0.12"/>
        <stop offset="100%" stop-color="var(--svg-accent-blue)" stop-opacity="0.02"/>
      </linearGradient>
      <radialGradient id="rlvr-gate-halo" cx="0.5" cy="0.5" r="0.6">
        <stop offset="0%"   stop-color="var(--svg-accent-blue)" stop-opacity="0.12"/>
        <stop offset="100%" stop-color="var(--svg-accent-blue)" stop-opacity="0"/>
      </radialGradient>
      <linearGradient id="rlvr-gate-accent" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%"   stop-color="var(--color-primary)" stop-opacity="0.30"/>
        <stop offset="100%" stop-color="var(--color-primary)" stop-opacity="0.08"/>
      </linearGradient>
    </defs>
    <rect x="20" y="232" width="860" height="56" rx="4" fill="url(#rlvr-flow-band)" stroke="none"/>
    <rect x="560" y="200" width="140" height="120" rx="8" fill="url(#rlvr-gate-halo)" stroke="none"/>
    <g class="fn-diagram__edges">
      <path id="rlvr-flow-path" class="fn-diagram__edge fn-diagram__edge--accent" pathLength="100" d="M 160 260 L 740 260" />
      <path class="fn-diagram__edge" pathLength="100" d="M 160 260 L 200 260" />
      <path class="fn-diagram__edge" pathLength="100" d="M 340 260 L 380 260" />
      <path class="fn-diagram__edge" pathLength="100" d="M 520 260 L 560 260" />
      <path class="fn-diagram__edge" pathLength="100" d="M 700 260 L 740 260" />
      <path class="fn-diagram__edge fn-diagram__edge--dashed" pathLength="100" d="M 810 200 C 810 96 90 96 90 200" />
    </g>
    <circle class="fn-diagram__flow" r="6"><animateMotion dur="4s" repeatCount="indefinite" calcMode="spline" keyTimes="0;1" keySplines="0.4 0 0.2 1" begin="1.6s"><mpath href="#rlvr-flow-path" /></animateMotion></circle>
    <g class="fn-diagram__nodes">
      <rect class="fn-diagram__node" x="20" y="200" width="140" height="120" rx="8" />
      <rect class="fn-diagram__node" x="200" y="200" width="140" height="120" rx="8" />
      <rect class="fn-diagram__node" x="380" y="200" width="140" height="120" rx="8" />
      <rect class="fn-diagram__node fn-diagram__node--accent fn-diagram__pulse" x="560" y="200" width="140" height="120" rx="8" style="fill: url(#rlvr-gate-accent)" />
      <rect class="fn-diagram__node" x="740" y="200" width="140" height="120" rx="8" />
    </g>
    <g class="fn-diagram__labels">
      <text class="fn-diagram__label fn-diagram__label--accent" x="90" y="264" text-anchor="middle">SAMPLE</text>
      <text class="fn-diagram__label fn-diagram__label--display" x="90" y="286" text-anchor="middle">8 tasks × K=4</text>
      <text class="fn-diagram__label fn-diagram__label--mono fn-diagram__label--muted" x="90" y="306" text-anchor="middle">rollouts</text>
      <text class="fn-diagram__label fn-diagram__label--accent" x="270" y="264" text-anchor="middle">SCORE</text>
      <text class="fn-diagram__label fn-diagram__label--display" x="270" y="286" text-anchor="middle">verifier = reward</text>
      <text class="fn-diagram__label fn-diagram__label--mono fn-diagram__label--muted" x="270" y="306" text-anchor="middle">no learned RM</text>
      <text class="fn-diagram__label fn-diagram__label--accent" x="450" y="264" text-anchor="middle">STEP</text>
      <text class="fn-diagram__label fn-diagram__label--display" x="450" y="286" text-anchor="middle">REINFORCE + KL</text>
      <text class="fn-diagram__label fn-diagram__label--mono fn-diagram__label--muted" x="450" y="306" text-anchor="middle">LoRA · ~22 s</text>
      <text class="fn-diagram__label fn-diagram__label--accent" x="630" y="264" text-anchor="middle">HELD-OUT GATE</text>
      <text class="fn-diagram__label fn-diagram__label--display" x="630" y="286" text-anchor="middle">frozen split</text>
      <text class="fn-diagram__label fn-diagram__label--mono fn-diagram__label--muted" x="630" y="306" text-anchor="middle">every ≤10 steps</text>
      <text class="fn-diagram__label fn-diagram__label--accent" x="810" y="264" text-anchor="middle">SELECT</text>
      <text class="fn-diagram__label fn-diagram__label--display" x="810" y="286" text-anchor="middle">argmax held-out</text>
      <text class="fn-diagram__label fn-diagram__label--mono fn-diagram__label--muted" x="810" y="306" text-anchor="middle">never pool</text>
    </g>
    <g class="fn-diagram__symbols">
      <g class="fn-diagram__icon" transform="translate(78 214)"><path d="M2.25 7.125C2.25 6.504 2.754 6 3.375 6h6c.621 0 1.125.504 1.125 1.125v3.75c0 .621-.504 1.125-1.125 1.125h-6a1.125 1.125 0 01-1.125-1.125v-3.75zM14.25 8.625c0-.621.504-1.125 1.125-1.125h5.25c.621 0 1.125.504 1.125 1.125v8.25c0 .621-.504 1.125-1.125 1.125h-5.25a1.125 1.125 0 01-1.125-1.125v-8.25zM3.75 16.125c0-.621.504-1.125 1.125-1.125h5.25c.621 0 1.125.504 1.125 1.125v2.25c0 .621-.504 1.125-1.125 1.125h-5.25a1.125 1.125 0 01-1.125-1.125v-2.25z" /></g>
      <g class="fn-diagram__icon" transform="translate(258 214)"><path d="M9 12.75L11.25 15 15 9.75M21 12a9 9 0 11-18 0 9 9 0 0118 0z" /></g>
      <g class="fn-diagram__icon" transform="translate(438 214)"><path d="M2.25 18L9 11.25l4.306 4.307a11.95 11.95 0 015.814-5.519l2.74-1.22m0 0l-5.94-2.281m5.94 2.28l-2.28 5.941" /></g>
      <g class="fn-diagram__icon fn-diagram__icon--accent" transform="translate(618 214)"><path d="M9 12.75L11.25 15 15 9.75m-3-7.036A11.959 11.959 0 013.598 6 11.99 11.99 0 003 9.749c0 5.592 3.824 10.29 9 11.623 5.176-1.332 9-6.03 9-11.622 0-1.31-.21-2.571-.598-3.751h-.152c-3.196 0-6.1-1.248-8.25-3.285z" /></g>
      <g class="fn-diagram__icon" transform="translate(798 214)"><path d="M3 3v1.5M3 21v-6m0 0l2.77-.693a9 9 0 016.208.682l.108.054a9 9 0 006.086.71l3.114-.732a48.524 48.524 0 01-.005-10.499l-3.11.732a9 9 0 01-6.085-.711l-.108-.054a9 9 0 00-6.208-.682L3 4.5M3 15V4.5" /></g>
    </g>
    <g class="fn-diagram__annotations">
      <text class="fn-diagram__annotation" x="450" y="86" text-anchor="middle">the lifted checkpoint becomes the next step's policy</text>
    </g>
  </svg>
  <figcaption>Four of the five beats are the obvious RL loop. The accent is on the fifth — the held-out gate — because it is the only thing standing between a number that climbs and a model that improves, and those are not the same number.</figcaption>
</figure>

The loop is dispatched, not clicked. An 8.5-hour run can't be a synchronous button — so `rl_run` is an Arena job kind drained overnight by the [budget-governed scheduler](/products/arena-control-plane/), single-lane, after the [recall layer](/field-notes/the-machine-manages-its-own-memory/) is asked "has this been tried?" and the cost ledger prices RL-vs-pay. That is the entire reason the pane and hands were built before the engine: an autonomous training loop on a no-auto-push box needs somewhere to safely land its output. The engine is the payload; the control plane is the truck.

## The journey — a proven run, and the engine it became

This is not a fresh result. The feasibility was proven months ago in [clawgym on Spark with GRPO](/field-notes/clawgym-on-spark-grpo/): a single GB10, a 42-task pool drawn 8-per-step at K=4 (a 32-rollout bundle), 34 GRPO steps in 8.5 hours, with a binary task-grader as the reward and *no learned reward model*. The agent's task-completion went from 0 of 158 to 154 of 158 — a 97.5-point lift — with mean turns down 58% and wall-clock down 62%. The textbook RLVR claim ("under 100 examples, a single GPU, the verifier scores directly") held on a desktop. What `fieldkit.rl` does is productize *that* run — the one that actually ran — with the three corrections the proven version taught, baked in so the next vertical doesn't relearn them.

The first correction is the one the abstract roadmap got wrong. The plan named Unsloth-GRPO and NeMo-RL — the library names you'd reach for. Neither drove the working run. A hand-rolled REINFORCE-with-KL loop of roughly 280 lines did, with a kill-and-restart of vLLM between steps to load the updated adapter. So `fieldkit.rl` wraps *that* loop, and treats the named libraries as a documented fallback lane, not the default. The cautionary precedent is real: a pinned-vLLM RL recipe has [burned this arc before](/field-notes/runtime-frontier-six-patches-on-spark/) on aarch64 + CUDA-13 wheel gaps.

The reward is a thin adapter, exactly as the thesis promises. Any `fieldkit.eval` scorer becomes a reward callable — and crucially, the reward is not a bare bit:

```python
from fieldkit.reward import RewardAdapter, group_advantage
from fieldkit.eval import irac_structure

# the verifier IS the reward — no learned reward model is trained or hosted
reward = RewardAdapter(irac_structure, pass_threshold=0.75)

rewards = reward.score_group(rollouts)   # one Reward(success, failure_class, auxiliary) each
rewards[0].success         # True if ≥3 of 4 IRAC components present
rewards[0].scalar          # 0.0 / 0.25 / 0.5 / 0.75 / 1.0 — dense partial credit
rewards[0].failure_class   # FailureLabel.KEEP, .DISCARD, or .CRASH on a raising verifier

adv = group_advantage(rewards)           # the group is the baseline — GRPO drops the critic
```

That `failure_class` field is the second correction, and it reuses something already built. A binary keep/revert reward *mode-collapses*: in [the trajectory-distillation work](/field-notes/distill-architect-lora-from-trajectories/), a 42-row corpus produced 5-of-5 training keeps on a single knob and 0-of-8 held-out generalization. The fix is a categorical signal — `(success, failure_class, auxiliary)` — and the categories were already shipped as `fieldkit.lineage.FailureLabel`, the same 10-class enum the [autoresearch loop](/field-notes/auto-research-loop-on-spark/) uses to label what a trial was worth. The reward and the loop's lineage record share one vocabulary because they're the same enum; nothing was invented to densify the gradient.

:::pitfall[Binary keep/revert is too sparse a reward — it collapses to one knob]
A scalar pass/fail reward gives the policy one bit per rollout, and a small corpus lets it satisfy that bit by exploiting a single degenerate behavior — 5/5 train keeps, 0/8 held-out. The fix is two-fold: a categorical `failure_class` (reusing the built `FailureLabel`) plus dense partial credit in `auxiliary["score"]` so a 3-of-4 IRAC answer scores 0.75, not 0. The graded scalar is what `group_advantage` actually standardizes.
:::

The loop itself takes the GPU as injected seams — and this is where the article has to be honest about what shipped:

```python
from fieldkit.rl import GRPOConfig, RLLoop, gpu_seams

cfg = GRPOConfig(base="patent-strategist-base", vllm_pin="0.10.2",
                 group_k=4, tasks_per_step=8, heldout_every=10, corpus_min=100)

# the three GPU seams: a vLLM sampler, the REINFORCE+KL trainer, the held-out eval.
# gpu_seams() RAISES until a pinned aarch64+CUDA-13 vLLM is vendored into the
# fieldkit[rl] extra. A test injects fakes; the Arena run_rl_loop tool calls this.
sampler, trainer, heldout_eval = gpu_seams(cfg)

loop = RLLoop(cfg, reward=reward, bench=bench,        # bench = the patent gold JSONL
              sampler=sampler, trainer=trainer, heldout_eval=heldout_eval)
snapshot = loop.run()                    # LineageSnapshot — the rl_run card
snapshot.summary()["selected_on"]        # "heldout" — never the pool
```

The shipped v0.20.0 engine is the *orchestration* — the split, the group math, the gate scheduling, the held-out-only checkpoint pick, the lineage record — with `torch` and vLLM behind seams that never import at module load. The real GPU backend is a documented fast-follow: vendor a pinned vLLM with an aarch64 + CUDA-13 wheel and the proven REINFORCE loop into the `fieldkit[rl]` extra, and `gpu_seams` resolves. Until then, callers inject their own. I'd rather show you the seam than pretend the loop has run end-to-end through this code — it hasn't. The 97.5-point number is the *predecessor* run's; the engine is the predecessor's lessons made reusable.

## Verification — what success looks like, and why the obvious metric lies

Here is the third correction, and the reason the diagram's accent is where it is. On the training pool, the loop converges beautifully. In [the T²PO run](/field-notes/t2po-uncertainty-guided-rl-on-spark/), at step 45 the training-pool task-pass hit 87.5% — 28 of 32. The same checkpoint, scored on the 158-task held-out set, passed 9. That's 5.7%. An 81.8-percentage-point inversion: *the strongest training-side checkpoint was the worst held-out checkpoint.* If you select the model you ship by watching the pool number climb, you will ship the regression, and the loop will report a triumph the whole way down.

:::pitfall[The loop reliably lies if you select the checkpoint on the training pool]
Training-pool score and held-out score don't just diverge — they can *invert*. T²PO measured 87.5% pool vs 5.7% held-out at the same step: an 81.8 pp gap, with the pool-best checkpoint being the held-out-worst. Pool convergence is not evidence of improvement; it's frequently evidence of overfitting the rollout sampler. The only honest stopping signal is a frozen held-out split scored on a fixed cadence.
:::

So the engine encodes the defense structurally, not as advice. `RLLoop` carves a frozen held-out split before step 0, runs the held-out gate every `heldout_every` (≤10) steps, and selects the published checkpoint with `argmax` over **held-out** scores only — `summary()["selected_on"]` is the string `"heldout"`, and a unit test proves the selector picks the held-out-best step *while the pool climbs monotonically past it*. The held-out eval is itself dispatched as an Arena `eval_rerun` job, so the gate is a control-plane artifact you can audit in the leaderboard, not a manual step someone can skip under deadline. Success on this machine isn't "the loss went down." It's "the held-out curve peaked at step N, we shipped step N, and the lineage card shows exactly that."

:::define[Held-out split]
A subset of the corpus carved off *before training starts* and never used to compute a gradient — used only to measure whether the policy is generalizing or memorizing the rollout pool. "Frozen" means the split is fixed before step 0 (here, `heldout_frac=0.2` of a ≥100-row corpus) so it can't drift into the training signal. Checkpoint selection reads this split and nothing else.
:::

The run's record is a `LineageSnapshot` — the same `fieldkit.lineage` card the rest of the arc uses, one `Trial` logged per step with its `FailureLabel`, plus a held-out-gate trial per eval. No new store, no new schema. That snapshot is what a future "living model" product renders as a public delta chart: not a marketing curve, but the actual held-out trajectory with the selected step marked.

## Tradeoffs, gotchas, and the honest gaps

The sharpest gotcha is the one above: the metric you'd naturally trust is the one that lies. Everything else is downstream of taking that seriously.

The second is that RLVR is not a corpus-quality lever, and it's easy to mistake it for one. The same T²PO run plateaued at roughly 47.7% per-assertion accuracy against an estimated synthetic-noise floor near 80% — and spending more wall-clock past the held-out peak bought nothing (the uncertainty-guided variant ran 18.5 hours to GRPO's 8.5 and landed *worse*). When the held-out curve flattens well below the ceiling, that's a signal about your *data*, not your *steps*. The move is to improve the corpus — better synthesis, curation, a cleaner gold set — not to crank the step count.

:::math[A 47.7% ceiling against an ~80% floor is a corpus signal, not an RL target]
If per-assertion accuracy plateaus at ~47.7% while the synthetic-noise floor sits near ~80%, the gap (~32 pp) is headroom the reward *can't* reach by optimizing harder — it's bounded by how noisy the gold labels are. More GRPO steps optimize against noise. The held-out peak is the stop signal; the floor is the to-do list for the corpus, not the loop.
:::

The third is the runtime tax, and it's the one optimization worth naming. Of a ~15-minute step, the rollouts take ~13 minutes, the trainer step takes ~22 seconds, and the vLLM kill-and-restart to load the new adapter takes ~3.5 minutes. That restart is ~25% of wall-clock and the *only* eliminable quarter — the top fast-follow is hot-LoRA-swap in vLLM (`/v1/load_lora_adapter`) so the lane never restarts. Note what this means: the trainer is not the bottleneck. Speeding up the 22-second step is a rounding error; killing the 3.5-minute restart is the win.

:::pitfall[The trainer is not the bottleneck — the vLLM restart is]
Intuition says "RL is slow because the gradient step is heavy." On a single Spark the REINFORCE step is ~22 s; the rollouts are ~13 min and the vLLM restart between steps is ~3.5 min. Optimizing the trainer is optimizing a rounding error. Pin one vLLM version (six API drifts across two minor versions, one of them a silent return-shape change) and target the restart, not the step.
:::

And the fourth is the envelope, which the whole design respects. The Spark holds one serving lane in 128 GB; the training run is ~50 GiB of base weights plus ~28 GiB trainer plus ~20 GiB vLLM — about 98 of 128, a ~30 GiB margin — which means *trainer resident, one vLLM lane, no second model*. You don't stack a critic and a policy and a judge; you take turns. That constraint isn't a limitation to apologize for — it's why GRPO (no critic) and a verifier-reward (no reward model) were the right choices and not just convenient ones. The algorithm and the hardware agree.

## What this unlocks

Three things become possible the week the GPU backend lands, none of which need anything past one Spark and a corpus you trust.

First: take a domain you have a verifier for — structured extraction, a compliance checklist, a graded rubric — and reinforcement-fine-tune a 7–8B LoRA toward it overnight, with your verifier as the reward and zero annotation budget. Wrap the scorer in a `RewardAdapter`, set `corpus_min` honestly (≥100 rows; 42 mode-collapsed), point the gate at a frozen split, and let the budget-governed drain run it while you sleep. The output is a model measurably better on *your* metric, selected on held-out, with a lineage card that proves it.

Second: the **living model**. A model re-RLVR'd on a cadence against a bench that keeps freshening, sold not on a static benchmark but on the public delta chart from its `LineageSnapshot` — a model whose whole pitch is that it keeps getting measurably better, with the receipts. That's the first §5 product launch this arc is staking now and shipping when the loop runs end-to-end.

Third: the recursion the book has been pointing at. When an `rl_run` lifts a bench past a threshold, the same machinery that drafts these articles can auto-scaffold the write-up — the engine's output becoming the next iteration's *input* not just for training, but for publishing. That's the loop the [meta-program opener](/field-notes/the-meta-program-on-spark/) drew with a dashed arc; this engine is what finally makes the arc a wire.

## Closing

The Machine-that-Builds-Machines arc opened by naming three beats and admitting the engine was the one with nowhere to land. It has a home now. The pane watches, the hands dispatch, and the engine improves a model from a reward function you wrote, audited, and own — selected on a held-out split so the improvement is real and not just a number that climbed. The Spark is the first machine where one person holds the entire loop, *including the reward*, and can read every line of the thing that teaches the model before trusting it with a gradient. That's the edge-builder's version of closed-loop RL: not renting the judgment, owning it.

What's left is honest and small: vendor the one pinned-vLLM backend that turns the injected seams into a run, and let the held-out curve speak. The feasibility is proven, the corrections are baked in, the control plane is waiting. The machine that builds machines can finally improve the machine it built — and on a desk, you can watch every loop of it close.

:::deeper
- [The Meta-Program on a DGX Spark](/field-notes/the-meta-program-on-spark/): the arc opener that named engine/hands/pane and left the engine for last.
- [ClawGym on Spark with GRPO](/field-notes/clawgym-on-spark-grpo/): the proven single-GB10 run — 0→154/158, 8.5 hours, no learned reward model.
- [T²PO — uncertainty-guided RL on Spark](/field-notes/t2po-uncertainty-guided-rl-on-spark/): where the 81.8 pp pool-vs-held-out inversion was measured.
- [`fieldkit.rl`](/fieldkit/api/rl/) and [`fieldkit.reward`](/fieldkit/api/reward/): the shipped engine surface — `GRPOConfig`, `RLLoop`, `RewardAdapter`, `group_advantage`.
- [Chapter 11 — The Machine That Builds Machines](/book/ch-11-the-machine-that-builds-machines/) and [Chapter 14 — The Meta-Program](/book/ch-14-the-meta-program/): the recursion this engine wires.
:::

:::hardware[The same loop, frontier coefficients]
The Spark runs LoRA-GRPO on a 7–8B model: one serving lane, ~15 min/step, one held-out gate, ~30 GiB margin. The *identical orchestration* runs full-parameter GRPO on a 30–120B model on a B200 or a SuperPOD — the code is invariant; only the envelope math changes. Prove the loop cheaply on the desk; rent frontier hardware for the one run whose model won't fit. The verifier-as-reward and the held-out gate don't change with scale — the inversion that bites at 8B bites worse at 120B.
:::
