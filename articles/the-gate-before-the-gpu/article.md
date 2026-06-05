---
title: "The Gate Before the GPU — Deciding SFT vs RL vs RLVR Before You Spend the Run"
date: 2026-06-05
author: Manav Sehgal
product: NeMo
stage: fine-tuning
difficulty: advanced
time_required: "~18 min read — synthesis of a multi-day greenfield-vertical build on one Spark"
hardware: "NVIDIA DGX Spark"
tags: [rlvr, sft, grpo, method-selection, reinforcement-learning, fine-tuning, machine-that-builds-machines, dgx-spark]
summary: "Building Kepler — a numeric astrodynamics reasoner — from scratch on one Spark. The method choice (SFT vs RL vs RLVR) is decided by cheap gates before any GPU run: a base preflight, an SFT gate, and a Goldilocks headroom gate. A flawless RLVR run that changed nothing is the proof."
signature: GateReadings
status: published
customer_linked: true
series: Machine that Builds Machines
book_chapters: [10, 11, 14]
fieldkit_modules: [rl, reward, eval]
---

The most expensive line of code in a reinforcement-learning project is the one that starts the run. Six hours of GPU time, a pinned vLLM lane, a checkpoint cadence, a held-out gate firing every ten steps — and at the end, a number. The trap is that you can do all of it correctly, watch a textbook-clean loop converge, and discover the number was knowable before you spent a watt. This is the story of building a model that way on purpose, to learn exactly where the decision should have been made: at a gate, well upstream of the GPU.

The model is **Kepler** — a numeric astrodynamics and quantitative-astrophysics reasoner. Text in ("a satellite orbits at 7,000 km altitude; what's its orbital period?"), one verifiable number out. There was no existing base model for this domain, so it's a genuine greenfield vertical: scout a base, build a benchmark, generate a corpus, train, and decide *how* to train. That last decision — supervised fine-tuning, reinforcement learning, or RL with a verifier as the reward — is the one that actually separates a cheap, stable result from a slow, fragile one. And it turns out to be decidable cheaply, if you build the right gates.

:::define[RLVR]
Reinforcement Learning from Verifiable Rewards. A reinforcement-learning loop where the reward signal is a *programmatic checker* — not a learned reward model and not a human — that scores the model's final answer as right or wrong. For a numeric domain, the verifier is a function: extract the boxed answer, normalize units, compare to the gold value within a tolerance. The verifier *is* the reward.
:::

## Why this matters for a personal AI builder

On a cluster, a wasted RL run is a line item someone else approves. On one DGX Spark, it's *your* box, hung for six hours on a single lane, with the rest of your week's experiments queued behind it. The 128 GB unified-memory envelope is generous enough to fine-tune and serve an 8B model, but it serves exactly one heavy thing at a time — so the cost of a run isn't just the GPU-hours, it's the opportunity cost of everything you didn't run instead. That constraint is a gift in disguise: it forces you to get good at *deciding before spending*, which is a skill the cloud lets you skip by throwing parallelism at the question.

The discipline below is what the Spark taught me. It's three cheap measurements that each fork the method decision, run in minutes-to-inference-only cost, and would have correctly predicted the outcome of a six-hour RL run before I started it. The point isn't that RL is bad. The point is that *method selection is a measurement problem*, and on one machine you can't afford to answer it with the run itself.

## Where this sits in the stack: the gate cascade

The conventional pipeline is linear — scout, corpus, train, evaluate — and the train step is a fork you resolve by intuition ("this feels like an RL problem"). The discipline replaces that intuition with a cascade of gates. Each gate is an inference-only measurement on a held-out set; each one forks the path; and the expensive RL run sits behind the *last* gate, not the first.

<figure class="fn-diagram" aria-label="The method-selection gate cascade: a base preflight gate forks to reconsider-base; if it passes, an SFT gate forks to re-corpus; if that passes, an RL-headroom gate forks to go-RL; and only if headroom is absent does the path terminate at ship-SFT. The horizontal spine is the path the Kepler model actually took — every gate passed forward to shipping SFT — while the downward dashed forks are the roads not taken.">
  <svg viewBox="0 0 900 440" role="img" aria-label="A cascade of three gates — base preflight, SFT gate, RL-headroom gate — each forking downward to an alternate method path, with the main spine terminating at ship SFT." preserveAspectRatio="xMidYMid meet">
    <defs>
      <linearGradient id="gc-band" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%" stop-color="var(--svg-accent-blue)" stop-opacity="0.02"/>
        <stop offset="50%" stop-color="var(--svg-accent-blue)" stop-opacity="0.12"/>
        <stop offset="100%" stop-color="var(--svg-accent-blue)" stop-opacity="0.02"/>
      </linearGradient>
      <radialGradient id="gc-halo" cx="0.5" cy="0.5" r="0.6">
        <stop offset="0%" stop-color="var(--svg-accent-blue)" stop-opacity="0.12"/>
        <stop offset="100%" stop-color="var(--svg-accent-blue)" stop-opacity="0"/>
      </radialGradient>
      <linearGradient id="gc-accent" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%" stop-color="var(--color-primary)" stop-opacity="0.30"/>
        <stop offset="100%" stop-color="var(--color-primary)" stop-opacity="0.08"/>
      </linearGradient>
    </defs>
    <rect x="20" y="172" width="860" height="56" rx="4" fill="url(#gc-band)" stroke="none"/>
    <rect x="700" y="150" width="160" height="100" rx="8" fill="url(#gc-halo)" stroke="none"/>
    <g class="fn-diagram__edges">
      <path id="gc-flow" class="fn-diagram__edge fn-diagram__edge--accent" pathLength="100" d="M 200 200 L 700 200" />
      <path class="fn-diagram__edge" pathLength="100" d="M 200 200 L 250 200" />
      <path class="fn-diagram__edge" pathLength="100" d="M 410 200 L 470 200" />
      <path class="fn-diagram__edge" pathLength="100" d="M 630 200 L 700 200" />
      <path class="fn-diagram__edge fn-diagram__edge--dashed" pathLength="100" d="M 120 250 L 120 330" />
      <path class="fn-diagram__edge fn-diagram__edge--dashed" pathLength="100" d="M 340 250 L 340 330" />
      <path class="fn-diagram__edge fn-diagram__edge--dashed" pathLength="100" d="M 560 250 L 560 330" />
    </g>
    <circle class="fn-diagram__flow" r="6"><animateMotion dur="4s" repeatCount="indefinite" calcMode="spline" keyTimes="0;1" keySplines="0.4 0 0.2 1" begin="1.6s"><mpath href="#gc-flow" /></animateMotion></circle>
    <g class="fn-diagram__nodes">
      <rect class="fn-diagram__node" x="40" y="150" width="160" height="100" rx="8" />
      <rect class="fn-diagram__node" x="260" y="150" width="160" height="100" rx="8" />
      <rect class="fn-diagram__node fn-diagram__node--accent fn-diagram__pulse" x="700" y="150" width="160" height="100" rx="8" style="fill: url(#gc-accent)" />
      <rect class="fn-diagram__node" x="480" y="150" width="160" height="100" rx="8" />
      <rect class="fn-diagram__node fn-diagram__node--ghost" x="55" y="330" width="130" height="56" rx="6" />
      <rect class="fn-diagram__node fn-diagram__node--ghost" x="275" y="330" width="130" height="56" rx="6" />
      <rect class="fn-diagram__node fn-diagram__node--ghost" x="495" y="330" width="130" height="56" rx="6" />
    </g>
    <g class="fn-diagram__labels">
      <text class="fn-diagram__label" x="120" y="190" text-anchor="middle">BASE PREFLIGHT</text>
      <text class="fn-diagram__label fn-diagram__label--mono fn-diagram__label--muted" x="120" y="212" text-anchor="middle">boxed · trunc</text>
      <text class="fn-diagram__label" x="340" y="190" text-anchor="middle">SFT GATE</text>
      <text class="fn-diagram__label fn-diagram__label--mono fn-diagram__label--muted" x="340" y="212" text-anchor="middle">held-out vs base</text>
      <text class="fn-diagram__label" x="560" y="190" text-anchor="middle">HEADROOM GATE</text>
      <text class="fn-diagram__label fn-diagram__label--mono fn-diagram__label--muted" x="560" y="212" text-anchor="middle">Goldilocks band</text>
      <text class="fn-diagram__label fn-diagram__label--accent" x="780" y="190" text-anchor="middle">SHIP SFT</text>
      <text class="fn-diagram__label fn-diagram__label--mono fn-diagram__label--muted" x="780" y="212" text-anchor="middle">Kepler</text>
      <text class="fn-diagram__label fn-diagram__label--mono fn-diagram__label--muted" x="120" y="363" text-anchor="middle">reconsider base</text>
      <text class="fn-diagram__label fn-diagram__label--mono fn-diagram__label--muted" x="340" y="363" text-anchor="middle">re-corpus</text>
      <text class="fn-diagram__label fn-diagram__label--mono fn-diagram__label--muted" x="560" y="363" text-anchor="middle">GO RL</text>
    </g>
    <g class="fn-diagram__annotations">
      <text class="fn-diagram__annotation" x="450" y="84" text-anchor="middle">the expensive RL run sits behind the LAST gate, not the first</text>
    </g>
  </svg>
  <figcaption>Three inference-only gates, each forking the method. The horizontal spine is the path Kepler took — every gate passed forward until the last one said "ship SFT." The GPU run lives behind the rightmost fork, where it's cheapest to skip.</figcaption>
</figure>

The rest of this piece walks the cascade as three nested questions: should I reach for RL at all, what does each gate measure, and how do I keep the runs that *do* fire as cheap as possible until the moment they have to be expensive.

## Question 1: SFT, RL, or RLVR — and the rule that decides

Before tuning any hyperparameter, answer the prior question: should this be reinforcement learning at all, or just supervised fine-tuning of the whole domain? The two paradigms need fundamentally different things from you.

:::define[SFT vs RLVR, in one line]
**SFT** (supervised fine-tuning) imitates *full correct trajectories* — reasoning chain and answer — that you provide. **RLVR** needs only a *verifier* that scores the final answer; the model explores its own reasoning paths to maximize that score.
:::

The decision rule is about **demonstration versus verification**. If you can *cheaply generate the correct demonstration* — the whole worked chain, not just the answer — **and** the output is *enumerable* (a single verifiable number from a closed-form generator), then SFT is the efficient frontier and RL is redundant. Kepler is exactly that case: every problem comes from a formula, so the gold answer is a function call, and a competent worked solution is a templated substitution. There is nothing for RL to *discover* that I can't already *write down*.

:::why[RL earns its keep only when verifying is easier than demonstrating]
RL's whole advantage is that it optimizes an *outcome* you can score without being able to *author* the ideal path to it. If you can author the path cheaply, you've already given SFT everything it needs — and SFT is cheaper, more stable, and has a clearer failure lever (more data) than a GPU-bound exploration loop.
:::

Concretely, RLVR buys you four things SFT cannot, and the decision turns on whether *any* apply:

1. **Verification ≫ demonstration** — you can score answers but can't author ideal reasoning at scale (theorem proving, search-heavy reasoning).
2. **Surpassing a noisy teacher** — SFT is capped by the quality of its demonstrations; RL optimizes against clean ground truth and can climb past noisy training data.
3. **Compositional / out-of-distribution generalization** — RL rewards outcome, not form, so it can compose known skills on novel inputs — *but only if the model already has nonzero competence there*, which is what the third gate checks.
4. **Non-enumerable output** — proofs, code-versus-tests, agentic trajectories you can't list — where SFT data is fundamentally incomplete.

For Kepler, all four were no. Closed-form generator, every row self-verifies, output is one number, and the demonstrations are template-perfect. The decision rule said *SFT-only*, unambiguously — before I touched the benchmark.

So why did I run RLVR anyway? Because validating the end-to-end control plane — the dispatcher, the budget governor, the memory watchdog, the vLLM lane, the checkpoint selector — was itself a goal. Running RL on a domain where I *knew* it shouldn't help is the cleanest possible stress test: any lift would be suspicious, and a null would prove the loop's machinery worked without confounding it with a real learning signal. That's the only honest reason to run RL on a fully-SFT-able domain, and it's worth being explicit that it's a deliberate exception, not the rule.

## Question 2: how each gate forks the path

The decision rule tells you the *default*. The gates tell you when the default is wrong — and each one measures a different thing.

### Gate 1 — the base preflight: verbosity, or non-convergence?

Before SFT, score the raw base model on the held-out set. For Kepler, the base was Qwen3-8B (a native thinking-mode reasoner — the scout confirmed no astrodynamics-specific base existed). The first reading was brutal: **reward 12.5%, and a 87.5% truncation rate**. Seven of eight problems ran the full 4,096-token budget without ever closing their `<think>` block. The one correct answer — a parallax-distance problem — got there, but only after **8,954 characters and 295 seconds** of reasoning.

:::pitfall[A thinking model that never stops thinking scores zero, regardless of competence]
If the model doesn't emit a closeable answer inside the token budget, the verifier sees nothing to score — reward is zero everywhere, and an RL loop "learns" from a flat signal. This failure mode looks identical to incompetence from the outside, but the fix is the opposite: it's conditioning, not capability.
:::

That truncation reading forks the path into a real question: is this **verbosity** (the model knows the physics but rambles, which SFT on terse demonstrations will fix) or **non-convergence** (the model is structurally lost and a different base is warranted)? Doubling the budget to 8,192 tokens barely moved it — boxed rate crept to 25%, reward stayed at 12.5%, with 16,000-character `<think>` blocks that *still* didn't terminate. That looked like non-convergence, and the expensive response would be to scout a new base.

Instead I ran the cheapest possible disambiguator: a **few-shot conditioning probe**. Same problems, same budget, but with three terse worked examples from the SFT corpus prepended to the prompt. If three examples could fix it, real SFT on 600 of them certainly would. The result was decisive — **boxed 75%, reward 75%, truncation 12.5%**, a six-fold lift, and the completions got *concise where they boxed*. The over-thinking was conditioning, not incompetence. The fork resolved to "stick with this base," and it cost one inference pass to learn.

### Gate 2 — the SFT gate: did the corpus take?

The SFT itself was almost anticlimactic. Six hundred authored rows — formula, substitution, intermediate steps, boxed gold, all deterministically generated and every one self-verifying through the same checker that serves as the RL reward — trained in about **eleven minutes**, loss falling 1.57 to 0.067. The gate is simple: score the merged model on a held-out set and compare to the base.

:::math[The SFT gate, in one comparison]
Base: 12.5% reward, 87.5% truncated. SFT: 86.4% reward (38/44), 0% truncated, 100% boxed. The same parallax problem that took the base 8,954 characters took the SFT model **185 characters and 9.8 seconds** — a clean chain straight to the boxed answer.
:::

That's a 6.9× lift and the complete elimination of the truncation failure mode. The gate passes decisively: the corpus took, the model is shippable as-is. This is the point where the decision rule from Question 1 gets its empirical confirmation — SFT alone reached 86% on a closed-form domain, which is exactly what the rule predicted. The fork here is "re-corpus if the gate fails"; it didn't, so we move to the last gate.

### Gate 3 — the headroom gate: the Goldilocks band

This is the gate that should sit *immediately* before any RL run, and it's the one I under-weighted. **Score the SFT init on the exact held-out set the RL loop will use to select checkpoints**, and only run RL if that score sits in a Goldilocks band — roughly **30–70%**.

:::why[RLVR amplifies existing competence; it cannot teach a skill from zero]
Above ~85%, most reinforcement-learning groups are uniformly correct, so there's no group-relative advantage, no gradient, no update. Below ~15%, no rollout ever succeeds, so there's no positive signal to amplify. RL only moves a model that already gets the answer *sometimes*. The band is where "sometimes" lives.
:::

Here's where it got interesting, and where the simple band rule needed a refinement. I built an *error-mined* transfer set — un-named formulas, new central bodies (Mars, the Moon, Jupiter, with their constants given in-prompt), two-hop chains, mild extrapolation into hyperbolic regimes — deliberately concentrated on the SFT model's measured weak spots. The aggregate reward dropped to **20.83%**. By the band rule alone, that's almost in range — tantalizingly close to "there's headroom here, go run RL."

But the aggregate lied. The per-family breakdown was **bimodal**, not uniformly mediocre:

| Transfer family | Reward |
|---|---|
| Altitude → speed | 100% (5/5) |
| Escape speed | 50% (1/2) |
| Hyperbolic excess | 40% (2/5) |
| Altitude → period | 25% (1/4) |
| Hubble cross-scale | 25% (1/4) |
| Un-named Hohmann transfer | **0% (0/7)** |
| New-body Hohmann | **0% (0/5)** |
| New-body circular speed | **0% (0/4)** |
| Period → speed | **0% (0/5)** |
| New-body altitude → period | **0% (0/7)** |

:::pitfall[A family at 0% is the mirror of saturation, not RL headroom]
Uniformly-wrong groups have zero group-relative advantage for exactly the same reason uniformly-correct ones do — every rollout scores the same, so there's no gradient. A 0% family isn't a learning opportunity; it's a coverage gap. The fix is more SFT templates for that family, not reinforcement learning.
:::

So the model *fully generalized* some shifts (altitude→speed transferred at 100% with zero extra training) and *completely failed* others (anything with a new central body, or an un-named composition). Only four families — about fifteen rows — actually sat in the productive middle band where RL could grip. The headroom existed, but it was thin and concentrated in lower-stakes families, while the high-value targets were a supervised-coverage problem masquerading as an RL opportunity. The gate's verdict: don't run RL to chase this; either expand the SFT corpus or ship what you have.

:::deeper
- ["Large Language Models Hack Rewards, and Society"](https://arxiv.org/abs/2606.04075) — why a surface verifier like ±2% boxed-match deserves adversarial stress before you trust it as a reward.
- ["The Shadow Price of Reasoning"](https://arxiv.org/abs/2606.03092) — per-query thinking-budget allocation, the principled answer to the flat token cap that triggered Gate 1's truncation reading.
- [Reinforcement Learning Elicits Contextual Learning](https://arxiv.org/abs/2606.06428) — the clean counter-case: a domain where RL *does* beat SFT because it teaches a meta-skill demonstrations can't.
:::

## Question 3: the iterative spiral — small probes before large runs

Notice the shape of every gate above: a cheap measurement that *forks* an expensive decision. That's not three isolated tricks — it's one discipline applied at every scale. Before committing to a large run, you spiral out a small one that's a decisive proxy for it.

The ladder, in order of ascending cost:

- A **5-row corpus dry-run** validated the generation template before producing 600.
- A **3-shot conditioning probe** (one inference pass) forked the base stick-vs-flip decision before any SFT.
- A **10-iteration loss smoke** confirmed the training loop converged before the full 100-iteration run.
- A **single-sample preflight** read the headroom before the group-sampled RL loop.
- A **4-step real-GPU smoke** — serve, sample, reward, train, restart, gate, checkpoint, teardown — proved the whole RL machinery end-to-end before the 34-step overnight drain.
- A **fake-seam CPU loop** with scripted rewards proved the orchestration logic before any GPU was involved at all.

:::why[On one machine, the proxy is the only affordable way to be sure]
A cluster lets you answer "will this work?" by running it twenty times in parallel. One Spark forces the cheaper question: "what's the smallest thing I can run that would tell me the answer?" That constraint produces better engineering, because the proxy forces you to articulate what success even looks like before you spend the time.
:::

There's a calibration caveat worth keeping: the single-sample preflight *under*-estimates headroom, because RL samples a whole group per problem — a single-sample 0% can hide a true 10–20% pass probability that a group would surface. So the spiral isn't infallible; it's directionally decisive and cheap, which is the right trade when the alternative is a six-hour commit.

## The honest null: what the run that changed nothing proved

I ran the full RLVR loop anyway — 34 steps, a held-out gate every 10, checkpoint selection on the held-out best. It was, mechanically, flawless. The in-loop held-out scored **0.9583 at step 0 and stayed exactly there** across all four gates. Five steps were degenerate zero-advantage steps — groups of uniformly-correct rollouts that produced no gradient — which is precisely what the headroom gate predicts when you start from a saturated init. The checkpoint selector, correctly, chose **step 0**: the SFT model itself. Memory peaked at 104 GB against the 128 GB envelope, the watchdog never had to defer a step, and the lane tore down clean.

:::define[Degenerate (zero-advantage) step]
A GRPO step where every sampled rollout for a problem gets the same reward. The group-relative advantage is then zero for all of them, so no policy gradient flows and the model doesn't update. Sparse degenerate steps from a strong init are correct behavior, not a bug — but from the outside they look identical to a stalled loop.
:::

Zero lift. A clean null. And it was the most valuable run of the project, for two reasons. First, it confirmed the gate cascade's prediction empirically — the headroom gate said "saturated init, no productive headroom," and the loop delivered exactly the no-op the gate forecast, which is the strongest possible validation that the gate measures what it claims. Second — and this was the actual goal — it stress-tested the entire control plane under a real GPU workload and shook out a stack of observability bugs that mock tests had slept through: the reward gauge was blind to a live run, degenerate steps were invisible from the cockpit, per-step history wasn't persisted. A foreseeable null is not a wasted run when validating the pipeline is a stated objective.

The deliverable, then, is the SFT model — Kepler, 86% on both the in-distribution and the off-template generalization held-out, with the truncation failure mode fully eliminated. The decision rule was right at the top of the funnel; the gates confirmed it at each step; and the GPU run was the receipt, not the discovery.

## What this unlocks

If you're building a domain reasoner on your own hardware, three concrete things change on Monday. **First**, you can decide your training method in an afternoon of inference passes instead of a week of runs: score the base, ask whether you can author the demonstrations, and if you can and the output is enumerable, SFT and stop. **Second**, you can build the headroom gate into your pipeline as a hard prerequisite — score the SFT init on an error-mined, *per-family* held-out, and refuse to launch RL unless families sit strictly inside the (0,1) band — which turns "should we RL this?" from a gut call into a table you read. **Third**, you can adopt the spiral as a habit: for every expensive run, write down the cheapest proxy that would predict its outcome, and run that first.

The broader lesson is that method selection is a measurement problem wearing the costume of an architecture decision. The instinct to reach for reinforcement learning because a problem "feels like RL" is exactly the instinct the gates are built to interrupt — with a number, before the GPU.

:::hardware[The gate gets cheaper as the model gets bigger]
On a Spark, the headroom preflight is one inference pass over ~50 held-out rows on an 8B model — minutes. Scale the same discipline to a 70B model on an H100 node and the gate's *relative* value grows: the RL run you might skip now costs hundreds of GPU-hours instead of six, while the preflight that decides it still costs one pass. The decision discipline is hardware-agnostic; the savings it protects scale with the iron. The Spark is where you learn it cheaply enough to make the habit stick before the runs get expensive.
:::

The next machine in this arc is the one that decides its *own* method — a pipeline that reads the gate table and picks SFT-or-RL without a human in the fork. That's a harder loop to close honestly, and it starts exactly here: with gates cheap and trustworthy enough that a machine could read them. For now, the human reads them, and the discipline holds: measure at the gate, spend at the GPU, and never the other way around.
