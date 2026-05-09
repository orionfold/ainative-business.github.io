---
title: "Was the Agent Researching, or Flailing? An Observability Pass on the Trajectory"
date: 2026-05-01
author: Manav Sehgal
product: NIM Llama 3.1 8B
stage: observability
also_stages: [agentic]
difficulty: intermediate
time_required: "~2 hours wall — analysis runs in seconds, the rest is reading + writing"
hardware: "NVIDIA DGX Spark"
tags: [observability, agentic, autoresearch, evaluation, llm-agents, prompt-engineering]
summary: "A8 said the LoRA mode-collapsed because the trajectory was thin. This puts numbers on it: 6 of 13 knobs ever touched, 72% of proposals repeated a prior pair, and the proposer's k=5 history window is the structural cause."
signature: TrajectoryFlailing
series: Machine that Builds Machines
book_chapters: [10]
---

[A8 shipped an honest negative result](/field-notes/distill-architect-lora-from-trajectories/): a Qwen2.5-3B LoRA trained on the [A4 trajectory](/field-notes/autoresearch-agent-loop/) mode-collapsed onto the trajectory's most-frequent winning move — `d_model=768`, suggested verbatim five out of five training-set keeps — and matched 0 of 8 held-out picks. The article's own diagnosis was: *the corpus was thin*. This is the follow-up that puts numbers on what "thin" means and points at the line of code that caused it.

:::define[Trajectory]
The full sequence of an agent's actions and observations across one task — every prompt the LLM saw, every command it proposed, every keep/revert decision the loop made, in order. In autoresearch, one trajectory = 50 iterations × (proposal, evaluation, decision) tuples. The trajectory is what you train *from* (a corpus for distillation) and what you measure *on* (an observability target). This article is about that second use.
:::

:::define[Mode collapse]
A fine-tuned model's tendency to over-concentrate probability mass on the most-frequent label in the training set, ignoring the diversity that was actually present. With LoRA on a five-of-five-identical training split, the student's softmax peaks so sharply on the one label that even mildly out-of-distribution prompts cannot pull it elsewhere. The 0-of-8 held-out match here is mode collapse in its purest form: not "the model is bad", but "the model is too good at the one wrong thing".
:::

The A4 loop ran for 73 minutes overnight, evaluated 50 perturbations, accepted 8 of them, and lowered val_bpb from 10.9554 to 10.8534 — a real 0.93% improvement that would have made the article shippable on its own. So at the surface, the trajectory looked like a researcher: it explored, it accepted, it improved. The trouble is that a corpus designed for distillation has to be *informative*, not just successful. And by every observability metric, this trajectory was the opposite.

The numbers below come from one Python script — `analyze_trajectory.py` reads the 50-row JSONL and the 13-knob perturbation menu — and produce three figures plus an `analysis.json`. Total wall: ~2 seconds.

| measurement | value |
|---|---:|
| trajectory iterations | 50 (8 keeps, 42 reverts) |
| **knob coverage** | **6 of 13** ever touched · **46.2%** of search space |
| knobs the agent never proposed | n_layer · lr_warmup · grad_clip · weight_decay · batch_size · seq_len · precision |
| **(knob, value) repeat rate** | **36 / 50 = 72%** were proposals already seen |
| unique (knob, value) pairs explored | 14 (out of ≥40 menu-allowed) |
| most-proposed pair | `d_model=1536` (**10×**, all reverted) |
| most-kept pair | `d_model=768` (**6 of 8 keeps** = 75%) |
| repeat rate, iters 1-10 → iters 41-50 | **50% → 90%** (climbs as the proposer forgets) |
| time to first keep | iter 4 (`d_model=768`, `+0.76%`) |
| time to best keep | iter 45 (`d_model=768`, `+0.93%`) — 41 iters of plateau |
| **train split keeps that were `d_model=768`** | **5 of 5** = 100% (the LoRA had only one mode to learn) |
| test split keeps that were `d_model=768` | 1 of 3 (held-out diversity is fine — train split's isn't) |
| script wall to compute all of the above | ~2 s |

The honest one-line summary: *the trajectory wasn't a corpus — it was the same successful proposal copy-pasted six times with 42 misses around it*. A8's distilled student didn't fail because LoRA can't capture the 8B's behaviour; it failed because the only behaviour the training data reinforced was "always say `d_model=768`".

## What flailing looks like in numbers

The 13-knob perturbation menu (defined in [A5's guardrails](/field-notes/guardrails-for-code-generation/)) gave the agent a wide search space: `n_layer`, `n_head`, `d_model`, `d_ff`, `lr`, `lr_warmup`, `grad_clip`, `weight_decay`, `beta1`, `beta2`, `batch_size`, `seq_len`, `precision`. Some are categorical (`precision: bf16/fp8`), some range-bounded (`lr: 1e-5..1e-2`). All thirteen are first-class citizens of the menu — the rails treat them identically.

Across 50 proposals, the agent touched six.

<figure class="fn-diagram" aria-label="Knob coverage waterfall. A stacked horizontal bar of 50 proposals decomposes into six knob segments — d_model 24, n_head 15, d_ff 5, lr 3, beta2 2, beta1 1. The d_model segment is the accent and dominates at nearly half the bar. Below the bar, seven outlined ghost cells label the untouched knobs (n_layer, lr_warmup, grad_clip, weight_decay, batch_size, seq_len, precision). Right margin annotates 6 of 13 knobs touched and 14 unique pairs across 50 iterations.">
  <svg viewBox="0 0 900 340" role="img" aria-label="Knob coverage waterfall. A stacked horizontal bar of 50 proposals decomposes into six knob segments — d_model 24, n_head 15, d_ff 5, lr 3, beta2 2, beta1 1. The d_model segment is the accent and dominates at nearly half the bar. Below the bar, seven outlined ghost cells label the untouched knobs (n_layer, lr_warmup, grad_clip, weight_decay, batch_size, seq_len, precision). Right margin annotates 6 of 13 knobs touched and 14 unique pairs across 50 iterations." preserveAspectRatio="xMidYMid meet">
    <defs>
      <linearGradient id="d-tev1-bar-grad" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%"   stop-color="var(--svg-accent-blue)" stop-opacity="0.10"/>
        <stop offset="100%" stop-color="var(--svg-accent-blue)" stop-opacity="0.02"/>
      </linearGradient>
      <linearGradient id="d-tev1-accent-grad" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%"   stop-color="var(--color-primary)" stop-opacity="0.30"/>
        <stop offset="100%" stop-color="var(--color-primary)" stop-opacity="0.08"/>
      </linearGradient>
      <radialGradient id="d-tev1-accent-halo" cx="0.5" cy="0.5" r="0.6">
        <stop offset="0%"   stop-color="var(--color-primary)" stop-opacity="0.18"/>
        <stop offset="100%" stop-color="var(--color-primary)" stop-opacity="0"/>
      </radialGradient>
    </defs>
    <rect x="60" y="80" width="780" height="80" rx="8" fill="url(#d-tev1-bar-grad)" stroke="none"/>
    <rect x="60" y="80" width="374.4" height="80" fill="url(#d-tev1-accent-halo)" stroke="none"/>
    <g class="fn-diagram__edges">
      <path class="fn-diagram__edge" pathLength="100" d="M 60 80 L 60 160" />
      <path class="fn-diagram__edge" pathLength="100" d="M 60 160 L 840 160" />
    </g>
    <g class="fn-diagram__nodes">
      <rect class="fn-diagram__node fn-diagram__node--accent" x="60"    y="90" width="374.4" height="60" rx="4" style="fill: url(#d-tev1-accent-grad)"/>
      <rect class="fn-diagram__node" x="438.4" y="90" width="234"   height="60" rx="4"/>
      <rect class="fn-diagram__node" x="676.4" y="90" width="78"    height="60" rx="4"/>
      <rect class="fn-diagram__node" x="758.4" y="90" width="46.8"  height="60" rx="4"/>
      <rect class="fn-diagram__node" x="809.2" y="90" width="31.2"  height="60" rx="4"/>
      <rect class="fn-diagram__node" x="844.4" y="90" width="15.6"  height="60" rx="4"/>
      <rect class="fn-diagram__node fn-diagram__node--ghost" x="60"  y="220" width="105" height="46" rx="4"/>
      <rect class="fn-diagram__node fn-diagram__node--ghost" x="171" y="220" width="105" height="46" rx="4"/>
      <rect class="fn-diagram__node fn-diagram__node--ghost" x="282" y="220" width="105" height="46" rx="4"/>
      <rect class="fn-diagram__node fn-diagram__node--ghost" x="393" y="220" width="105" height="46" rx="4"/>
      <rect class="fn-diagram__node fn-diagram__node--ghost" x="504" y="220" width="105" height="46" rx="4"/>
      <rect class="fn-diagram__node fn-diagram__node--ghost" x="615" y="220" width="105" height="46" rx="4"/>
      <rect class="fn-diagram__node fn-diagram__node--ghost" x="726" y="220" width="105" height="46" rx="4"/>
    </g>
    <g class="fn-diagram__labels">
      <text class="fn-diagram__label fn-diagram__label--accent" x="60"  y="64" text-anchor="start">KNOB COVERAGE · 50 PROPOSALS</text>
      <text class="fn-diagram__label fn-diagram__label--display" x="247" y="124" text-anchor="middle">d_model</text>
      <text class="fn-diagram__label fn-diagram__label--mono"   x="247" y="142" text-anchor="middle">24 · 48%</text>
      <text class="fn-diagram__label fn-diagram__label--display" x="555" y="124" text-anchor="middle">n_head</text>
      <text class="fn-diagram__label fn-diagram__label--mono"   x="555" y="142" text-anchor="middle">15 · 30%</text>
      <text class="fn-diagram__label fn-diagram__label--mono" x="715" y="124" text-anchor="middle">d_ff</text>
      <text class="fn-diagram__label fn-diagram__label--mono" x="715" y="140" text-anchor="middle">5</text>
      <text class="fn-diagram__label fn-diagram__label--mono fn-diagram__label--muted" x="781" y="178" text-anchor="middle">lr · 3</text>
      <text class="fn-diagram__label fn-diagram__label--mono fn-diagram__label--muted" x="824" y="178" text-anchor="middle">β₂ · 2</text>
      <text class="fn-diagram__label fn-diagram__label--mono fn-diagram__label--muted" x="852" y="178" text-anchor="middle">β₁</text>
      <text class="fn-diagram__label fn-diagram__label--accent" x="60"  y="208" text-anchor="start">NEVER PROPOSED · 7 KNOBS</text>
      <text class="fn-diagram__label fn-diagram__label--mono fn-diagram__label--muted" x="112" y="248" text-anchor="middle">n_layer</text>
      <text class="fn-diagram__label fn-diagram__label--mono fn-diagram__label--muted" x="223" y="248" text-anchor="middle">lr_warmup</text>
      <text class="fn-diagram__label fn-diagram__label--mono fn-diagram__label--muted" x="334" y="248" text-anchor="middle">grad_clip</text>
      <text class="fn-diagram__label fn-diagram__label--mono fn-diagram__label--muted" x="445" y="248" text-anchor="middle">weight_decay</text>
      <text class="fn-diagram__label fn-diagram__label--mono fn-diagram__label--muted" x="556" y="248" text-anchor="middle">batch_size</text>
      <text class="fn-diagram__label fn-diagram__label--mono fn-diagram__label--muted" x="667" y="248" text-anchor="middle">seq_len</text>
      <text class="fn-diagram__label fn-diagram__label--mono fn-diagram__label--muted" x="778" y="248" text-anchor="middle">precision</text>
    </g>
    <g class="fn-diagram__annotations">
      <text class="fn-diagram__annotation" x="840" y="64"  text-anchor="end">6 / 13 touched · 14 unique pairs</text>
      <text class="fn-diagram__annotation" x="60"  y="296" text-anchor="start">six capacity-dim knobs absorb every proposal</text>
      <text class="fn-diagram__annotation" x="840" y="296" text-anchor="end">seven optimization-dim knobs untouched across 50 chances</text>
    </g>
  </svg>
  <figcaption>Six knobs absorb every proposal — <code>d_model</code> alone takes 24 of 50, and seven optimization-dim knobs never appeared.</figcaption>
</figure>

`d_model` alone took 24 of the 50 proposals — nearly half. Combined with `n_head` it took 39 of 50 = 78%. Seven knobs never appeared: not even once across 50 chances. That's not a sampling fluke; even uniform random over 13 knobs would have hit every knob by iter 50 with overwhelming probability. The proposer is biased toward *capacity-dimension* knobs (`d_model`, `n_head`, `d_ff`) and ignores *optimization-dimension* knobs (`lr_warmup`, `grad_clip`, `weight_decay`, `batch_size`, `seq_len`, `precision`).

:::math[Why "uniform random over 13 knobs" should hit all 13]
Probability that a specific knob is *never* picked across 50 uniform draws from 13: `(12/13)^50 ≈ 0.019`. Probability that *any* of the 13 is missed (union bound): `13 × 0.019 ≈ 0.25`. So even uniform random would skip ~3 knobs on average across many runs of 50. That the agent skipped *7* knobs — and specifically the optimization-dim ones — is a 4× excess over null and a clear directional bias, not noise.
:::

:::define[Knob coverage]
The number of distinct knobs (or `(knob, value)` pairs) the agent has *ever* proposed across the trajectory, divided by the menu size. A 50-iteration trajectory covering 6 of 13 knobs has 46.2 % knob coverage and 14 unique pairs. Coverage is the cheap, observability-first proxy for "how much of the search space did this loop actually explore?" — a number the loop counter alone cannot tell you.
:::

Why does this matter for distillation? The corpus the LoRA learned from has zero examples of "what to do when the optimizer is too aggressive" or "what to do when sequence length is wrong." Whatever the agent learned about the optimization-dim subspace is unrepresented. The student couldn't have learned it even if the teacher had been consistent.

## The repeat rate climbs because the proposer forgets

A worse problem hides inside the 50 proposals: 36 of them were *literal repeats* of a (knob, value) pair the agent had already proposed. The unique-pair count across the run is 14. So the agent proposed `d_model=1536` ten times across the run, `n_head=32` six times, `d_model=768` seven times — most of those after the first instance had already been evaluated and the result logged.

Why? `articles/autoresearch-agent-loop/evidence/proposer.py` builds the prompt with this line:

```python
def _history_lines(history: list[dict], k: int = 5) -> str:
    if not history:
        return "(no prior iterations yet)"
    recent = history[-k:]
    ...
```

The agent's prompt only shows the **last 5 iterations**. The system prompt warns "DO NOT propose the same knob and value as the last accepted state" — and the agent obeys *that* literally: the most recent acceptance is rarely re-proposed. But the prompt has no view of iterations 1 through 25 by the time iter 30 fires. Whatever the loop learned then is gone.

The repeat rate makes the cost of this design choice visible:

<figure class="fn-diagram" aria-label="Repeat rate timeline. Five vertical bars across the 50-iteration trajectory, one per ten-iteration window. Window 1 (iters 1-10) and window 2 (iters 11-20) sit at 50%. Window 3 (iters 21-30) climbs to 80%. Windows 4 and 5 (iters 31-40 and 41-50) reach 90%, the accent bars. A horizontal annotation marks the k=5 history window — by iter 30 the proposer cannot see iters 1-25, so it re-proposes ground it already covered. Overall repeat rate of 72 percent labelled at the top right.">
  <svg viewBox="0 0 900 360" role="img" aria-label="Repeat rate timeline. Five vertical bars across the 50-iteration trajectory, one per ten-iteration window. Window 1 (iters 1-10) and window 2 (iters 11-20) sit at 50%. Window 3 (iters 21-30) climbs to 80%. Windows 4 and 5 (iters 31-40 and 41-50) reach 90%, the accent bars. A horizontal annotation marks the k=5 history window — by iter 30 the proposer cannot see iters 1-25, so it re-proposes ground it already covered. Overall repeat rate of 72 percent labelled at the top right." preserveAspectRatio="xMidYMid meet">
    <defs>
      <linearGradient id="d-tev2-plot-grad" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%"   stop-color="var(--svg-accent-blue)" stop-opacity="0.10"/>
        <stop offset="100%" stop-color="var(--svg-accent-blue)" stop-opacity="0.02"/>
      </linearGradient>
      <linearGradient id="d-tev2-accent-grad" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%"   stop-color="var(--color-primary)" stop-opacity="0.34"/>
        <stop offset="100%" stop-color="var(--color-primary)" stop-opacity="0.08"/>
      </linearGradient>
      <radialGradient id="d-tev2-accent-halo" cx="0.5" cy="0.5" r="0.6">
        <stop offset="0%"   stop-color="var(--color-primary)" stop-opacity="0.15"/>
        <stop offset="100%" stop-color="var(--color-primary)" stop-opacity="0"/>
      </radialGradient>
    </defs>
    <rect x="100" y="40" width="740" height="240" fill="url(#d-tev2-plot-grad)" stroke="none"/>
    <rect x="556" y="40" width="284" height="240" fill="url(#d-tev2-accent-halo)" stroke="none"/>
    <g class="fn-diagram__edges">
      <path class="fn-diagram__edge fn-diagram__edge--ghost" d="M 100 280 L 840 280" />
      <path class="fn-diagram__edge fn-diagram__edge--ghost" d="M 100 220 L 840 220" />
      <path class="fn-diagram__edge fn-diagram__edge--ghost" d="M 100 160 L 840 160" />
      <path class="fn-diagram__edge fn-diagram__edge--ghost" d="M 100 100 L 840 100" />
      <path class="fn-diagram__edge fn-diagram__edge--ghost" d="M 100 40  L 840 40"  />
      <path class="fn-diagram__edge" pathLength="100" d="M 100 40 L 100 280" />
      <path class="fn-diagram__edge" pathLength="100" d="M 100 280 L 840 280" />
    </g>
    <g class="fn-diagram__nodes">
      <rect class="fn-diagram__node" x="146" y="160" width="100" height="120" rx="4"/>
      <rect class="fn-diagram__node" x="282" y="160" width="100" height="120" rx="4"/>
      <rect class="fn-diagram__node" x="418" y="100" width="100" height="180" rx="4"/>
      <rect class="fn-diagram__node fn-diagram__node--accent" x="554" y="76"  width="100" height="204" rx="4" style="fill: url(#d-tev2-accent-grad)"/>
      <rect class="fn-diagram__node fn-diagram__node--accent" x="690" y="76"  width="100" height="204" rx="4" style="fill: url(#d-tev2-accent-grad)"/>
      <rect class="fn-diagram__node fn-diagram__node--ghost" x="554" y="76" width="236" height="204" rx="4"/>
    </g>
    <g class="fn-diagram__labels">
      <text class="fn-diagram__label fn-diagram__label--mono fn-diagram__label--muted" x="92" y="284" text-anchor="end">0%</text>
      <text class="fn-diagram__label fn-diagram__label--mono fn-diagram__label--muted" x="92" y="224" text-anchor="end">25</text>
      <text class="fn-diagram__label fn-diagram__label--mono fn-diagram__label--muted" x="92" y="164" text-anchor="end">50</text>
      <text class="fn-diagram__label fn-diagram__label--mono fn-diagram__label--muted" x="92" y="104" text-anchor="end">75</text>
      <text class="fn-diagram__label fn-diagram__label--mono fn-diagram__label--muted" x="92" y="44"  text-anchor="end">100</text>
      <text class="fn-diagram__label fn-diagram__label--mono fn-diagram__label--muted" x="100" y="22" text-anchor="start">repeat rate %</text>
      <text class="fn-diagram__label fn-diagram__label--accent" x="100" y="332" text-anchor="start">REPEAT RATE BY 10-ITER WINDOW</text>
      <text class="fn-diagram__label fn-diagram__label--mono fn-diagram__label--muted" x="196" y="304" text-anchor="middle">1 – 10</text>
      <text class="fn-diagram__label fn-diagram__label--mono fn-diagram__label--muted" x="332" y="304" text-anchor="middle">11 – 20</text>
      <text class="fn-diagram__label fn-diagram__label--mono fn-diagram__label--muted" x="468" y="304" text-anchor="middle">21 – 30</text>
      <text class="fn-diagram__label fn-diagram__label--mono fn-diagram__label--muted" x="604" y="304" text-anchor="middle">31 – 40</text>
      <text class="fn-diagram__label fn-diagram__label--mono fn-diagram__label--muted" x="740" y="304" text-anchor="middle">41 – 50</text>
      <text class="fn-diagram__label fn-diagram__label--mono" x="196" y="152" text-anchor="middle">50%</text>
      <text class="fn-diagram__label fn-diagram__label--mono" x="332" y="152" text-anchor="middle">50%</text>
      <text class="fn-diagram__label fn-diagram__label--mono" x="468" y="92"  text-anchor="middle">80%</text>
      <text class="fn-diagram__label fn-diagram__label--display" x="604" y="68"  text-anchor="middle">90%</text>
      <text class="fn-diagram__label fn-diagram__label--display" x="740" y="68"  text-anchor="middle">90%</text>
    </g>
    <g class="fn-diagram__annotations">
      <text class="fn-diagram__annotation" x="840" y="332" text-anchor="end">72% overall · k=5 window forgets iters past N-5</text>
      <text class="fn-diagram__annotation" x="668" y="40"  text-anchor="middle">9 of 10 proposals are ground already covered</text>
    </g>
  </svg>
  <figcaption>Repeat rate climbs from 50% to 90% as the <code>k=5</code> history window slides past prior decisions; second-half iters re-litigate ground already evaluated.</figcaption>
</figure>

In the first 10 iterations, half of the proposals were already-seen pairs — already a sign the proposer was leaning on a few favorites. By iter 21-30, that's 80%. By iter 31-50, it's 90%. *Nine out of ten proposals in the second half of the run were ground the agent had already covered.* The 73-minute wall did not get the loop nine-tenths of a richer corpus; it got it the same ~14 ideas re-litigated with diminishing utility.

This is a **prompt design bug, not a model bug**. The 8B is a competent proposer when it can see what it has tried — the first 10 iterations are evidence of that. After the rolling window slides past iter 5, it's proposing into an amnesiac context.

:::pitfall[`k=5` history window silently caps exploration]
The k=5 default looks innocuous — five recent iterations is "what changed lately," which is what most agent loops want for *response* generation. But for *exploration* generation, k=5 means iter 30 cannot see iters 1–25. The agent obediently re-proposes ground it had already evaluated, the loop counter increments, and the dashboard reads "the agent is exploring." It isn't. The `k` constant is one of those numbers that costs nothing to set, and silently bounds what the loop can ever discover.
:::

:::why[Loop counter ≠ search-space coverage]
A status-line "iteration 47/50" is a measure of *how long the loop has been running*, not *how much of the search space it has explored*. A loop that runs 50 iterations covering 6 of 13 knobs and producing 14 unique (knob, value) pairs is 47 % through its budget but ~10–15 % through its search space. Treating the iteration count as a progress bar is what made the original A4 article describe a healthy run; it took an analysis pass on the trajectory to surface the gap. Always log coverage, always log repeat-rate, never trust the counter alone.
:::

## The plateau — first keep and best keep are the same idea

The cumulative best curve over 50 iters tells the same story from a different angle.

<figure class="fn-diagram" aria-label="Cumulative best validation bpb over the 50-iteration trajectory. A stepped curve drops from baseline at iter 4 (first keep, +0.76%), confirms at iter 6 (+0.77%), and then plateaus for 17 iterations. At iter 23 the curve drops again to +0.89%, then holds nearly flat through small keeps at iters 31 and 33, and finally drops to the best value of +0.93% at iter 45. Eight keep iterations are marked as dots along the curve. The accent dots are the first keep at iter 4 and the best at iter 45, with a shaded band over the 17-iteration plateau between iters 6 and 23.">
  <svg viewBox="0 0 900 360" role="img" aria-label="Cumulative best validation bpb over the 50-iteration trajectory. A stepped curve drops from baseline at iter 4 (first keep, +0.76%), confirms at iter 6 (+0.77%), and then plateaus for 17 iterations. At iter 23 the curve drops again to +0.89%, then holds nearly flat through small keeps at iters 31 and 33, and finally drops to the best value of +0.93% at iter 45. Eight keep iterations are marked as dots along the curve. The accent dots are the first keep at iter 4 and the best at iter 45, with a shaded band over the 17-iteration plateau between iters 6 and 23." preserveAspectRatio="xMidYMid meet">
    <defs>
      <linearGradient id="d-tev3-plot-grad" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%"   stop-color="var(--svg-accent-blue)" stop-opacity="0.10"/>
        <stop offset="100%" stop-color="var(--svg-accent-blue)" stop-opacity="0.02"/>
      </linearGradient>
      <linearGradient id="d-tev3-plateau-grad" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%"   stop-color="var(--color-primary)" stop-opacity="0.14"/>
        <stop offset="100%" stop-color="var(--color-primary)" stop-opacity="0.02"/>
      </linearGradient>
    </defs>
    <rect x="100" y="40" width="740" height="240" fill="url(#d-tev3-plot-grad)" stroke="none"/>
    <rect x="189" y="40" width="251" height="240" fill="url(#d-tev3-plateau-grad)" stroke="none"/>
    <rect class="fn-diagram__node fn-diagram__node--ghost" x="189" y="40" width="251" height="240" rx="0"/>
    <g class="fn-diagram__edges">
      <path class="fn-diagram__edge fn-diagram__edge--ghost" d="M 100 280 L 840 280" />
      <path class="fn-diagram__edge fn-diagram__edge--ghost" d="M 100 215 L 840 215" />
      <path class="fn-diagram__edge fn-diagram__edge--ghost" d="M 100 150 L 840 150" />
      <path class="fn-diagram__edge fn-diagram__edge--ghost" d="M 100 85  L 840 85"  />
      <path class="fn-diagram__edge fn-diagram__edge--ghost" d="M 100 40  L 840 40"  />
      <path class="fn-diagram__edge" pathLength="100" d="M 100 40 L 100 280" />
      <path class="fn-diagram__edge" pathLength="100" d="M 100 280 L 840 280" />
      <path class="fn-diagram__edge fn-diagram__edge--accent" pathLength="100" d="M 100 40 L 159 40 L 159 207 L 189 207 L 189 211 L 440 211 L 440 244 L 559 244 L 559 246 L 588 246 L 588 248 L 736 248 L 736 252 L 766 252 L 766 257 L 840 257" />
    </g>
    <g class="fn-diagram__nodes">
      <circle class="fn-diagram__dot fn-diagram__dot--accent" cx="159" cy="207" r="7"/>
      <circle class="fn-diagram__dot" cx="189" cy="211" r="5"/>
      <circle class="fn-diagram__dot" cx="440" cy="244" r="5"/>
      <circle class="fn-diagram__dot" cx="559" cy="246" r="5"/>
      <circle class="fn-diagram__dot" cx="588" cy="248" r="5"/>
      <circle class="fn-diagram__dot" cx="736" cy="252" r="5"/>
      <circle class="fn-diagram__dot fn-diagram__dot--accent" cx="766" cy="257" r="7"/>
      <circle class="fn-diagram__dot" cx="781" cy="257" r="5"/>
    </g>
    <g class="fn-diagram__labels">
      <text class="fn-diagram__label fn-diagram__label--mono fn-diagram__label--muted" x="92" y="44"  text-anchor="end">10.96</text>
      <text class="fn-diagram__label fn-diagram__label--mono fn-diagram__label--muted" x="92" y="89"  text-anchor="end">10.93</text>
      <text class="fn-diagram__label fn-diagram__label--mono fn-diagram__label--muted" x="92" y="154" text-anchor="end">10.90</text>
      <text class="fn-diagram__label fn-diagram__label--mono fn-diagram__label--muted" x="92" y="219" text-anchor="end">10.87</text>
      <text class="fn-diagram__label fn-diagram__label--mono fn-diagram__label--muted" x="92" y="284" text-anchor="end">10.85</text>
      <text class="fn-diagram__label fn-diagram__label--mono fn-diagram__label--muted" x="100" y="22" text-anchor="start">val_bpb · cumulative best</text>
      <text class="fn-diagram__label fn-diagram__label--accent" x="100" y="332" text-anchor="start">50-ITER TRAJECTORY · 8 KEEPS</text>
      <text class="fn-diagram__label fn-diagram__label--mono fn-diagram__label--muted" x="100" y="304" text-anchor="middle">1</text>
      <text class="fn-diagram__label fn-diagram__label--mono fn-diagram__label--muted" x="248" y="304" text-anchor="middle">10</text>
      <text class="fn-diagram__label fn-diagram__label--mono fn-diagram__label--muted" x="396" y="304" text-anchor="middle">20</text>
      <text class="fn-diagram__label fn-diagram__label--mono fn-diagram__label--muted" x="544" y="304" text-anchor="middle">30</text>
      <text class="fn-diagram__label fn-diagram__label--mono fn-diagram__label--muted" x="692" y="304" text-anchor="middle">40</text>
      <text class="fn-diagram__label fn-diagram__label--mono fn-diagram__label--muted" x="840" y="304" text-anchor="middle">50</text>
      <text class="fn-diagram__label fn-diagram__label--mono" x="159" y="196" text-anchor="middle">iter 4 · +0.76%</text>
      <text class="fn-diagram__label fn-diagram__label--mono" x="766" y="278" text-anchor="middle">iter 45 · +0.93%</text>
    </g>
    <g class="fn-diagram__annotations">
      <text class="fn-diagram__annotation" x="315" y="62"  text-anchor="middle">17-iter plateau · same idea, smaller adjustments</text>
      <text class="fn-diagram__annotation" x="840" y="332" text-anchor="end">six of eight keeps land on d_model=768</text>
    </g>
  </svg>
  <figcaption>First keep at iter 4 (<code>d_model=768</code>), best at iter 45 — and a 17-iter plateau between, where the loop kept relitigating the same idea.</figcaption>
</figure>

The agent finds `d_model=768` at iter 4 (`+0.76%`) and confirms it at iter 6 (`+0.77%`). Then nothing happens for **17 iterations**. Iter 23 is another `d_model=768` keep with marginally better val_bpb (`+0.89%`). More small `d_model=768` keeps at iters 31, 33, 43, 45, 46. The "best" iter 45 is `+0.93%` — a 0.04 percentage-point improvement over what the agent already knew at iter 6.

Eight keeps is genuinely a respectable yield for a free overnight loop. But six of those eight keeps proposed *the same single change*. From an exploration perspective, this loop did its useful work in the first ~6 iterations and the next ~44 were variations on the theme. From a distillation-corpus perspective, this is much worse than it looks: the keep-side mode dominance is even higher than the proposal-side mode dominance.

## Why this killed the LoRA

A8's `prepare_corpus.py` used a **time-tail split**: iters 1–42 became train, iters 43–50 became held-out test. Both decisions (keep + revert) are training rows, but the keeps are what the LoRA has the strongest signal to imitate — they're the proposals that worked.

Across the 8 keeps in the trajectory:

| split | keep iters | mode breakdown |
|---|---|---|
| train (iters 1–42) | 5 keeps: 4, 6, 23, 31, 33 | **5 of 5 = `d_model=768`** |
| test (iters 43–50) | 3 keeps: 43, 45, 46 | 1× `d_model=768` · 1× `d_ff=6144` · 1× `d_ff=8192` |

The train split is *literally a single-mode distribution*. Every successful example the LoRA was supervised on said the same thing. Cross-entropy loss on five copies of `{"knob": "d_model", "new_value": 768, "reason": "..."}` reinforces exactly one output sequence. With `r=16` LoRA adapters and 30 optimizer steps, that signal isn't competing with much else.

The held-out 3 keeps are diverse — they touch a *different* knob (`d_ff`) the model barely saw in training. So at race time, the 3B distilled student saw 8 prompts that, on average, asked for a knob it had no positive examples of, and answered with the only thing it had been trained to be confident about. 0 of 8 exact match was the predictable outcome.

The 8B teacher fared better on the same 8 prompts (4 of 8 exact, 0.5 mean reciprocal-rank in spirit if not in name) for an obvious reason: the 8B's distribution wasn't filtered through 5-of-5 mode collapse. It still has the broad world knowledge that says "if `d_model=768` keeps winning, maybe try `d_ff` next." The LoRA stripped that prior out.

## Three cheap fixes for A4.2

The 200-iter overnight rerun queued in the next session has to land *one* of these to be worth the wall time.

**1. Rail-side anti-repeat (cleanest).** [A5's guardrails](/field-notes/guardrails-for-code-generation/) already maintain `seen_pairs` semantics conceptually. Adding a `block_repeat` rail that rejects any (knob, value) seen in the last 50 iterations forces the agent to propose elsewhere on retry. The proposer doesn't change — the rails just refuse to evaluate ground already covered. Cost: a one-line check in `gate()`.

**2. Prompt-side widening (most informative for distillation).** Bump `k` from 5 to 30 (or all-history). The proposer's prompt grows from ~6 lines of recent history to ~30+. The 8B sees what it tried, what worked, what failed; it can reason "I already tried `d_model=1536` six times and reverted every time, let me try `lr_warmup` for a change." Cost: longer prompt (~10× tokens for the history block), proportionally slower per-iter NIM call (was 1.23 s mean — would become maybe 2-3 s), but the corpus quality goes up dramatically.

**3. Reason-temperature bump.** A lazier fix: serve the 8B with `temperature=0.8` instead of whatever default the NIM uses. The agent will be less prone to falling into the local mode. Cheapest to implement, but doesn't fix the structural problem; just papers over it.

The honest recommendation is **(1) plus (2)**: rails reject duplicates, prompt shows the full history. Then 200 iters produces 200 unique evaluated configs, and the corpus distillation can learn from is roughly 14× richer than what A4 produced. With 200 train rows of diverse keeps and reverts, A8's rematch becomes a real test of whether a 3B can imitate an 8B at this task — instead of a test of whether 3B can mode-collapse onto a single training example, which we already know it can.

:::deeper
- [A4 — autoresearch-agent-loop](/field-notes/autoresearch-agent-loop/) — the trajectory this analysis pass dissects.
- [A5 — guardrails-for-code-generation](/field-notes/guardrails-for-code-generation/) — the rails layer where `block_repeat` belongs.
- [A8 — distill-architect-lora-from-trajectories](/field-notes/distill-architect-lora-from-trajectories/) — the LoRA distillation that mode-collapsed; this article diagnoses *why*.
- [Chinchilla scaling (Hoffmann et al., 2022)](https://arxiv.org/abs/2203.15556) — the compute-optimal recipe the agent's `d_model=768` keeps were drifting toward.
:::

## What this means for the agent loop

The A4 article's headline was *"the agent ran 50 experiments overnight on a Spark and the box stayed up."* Both are still true. What this observability pass adds is the qualifier: the agent ran 50 experiments, but only ~14 of them were genuinely new experiments — the rest were the agent's k=5 rolling window failing to teach it that it had already covered the same ground.

That's a useful thing to know about LLM-driven loops in general. Agents with bounded prompt history are biased toward whatever mode the rolling window happens to anchor on. They look like they're exploring because the loop counter increments. They're not. The loop counter and the search-space coverage are two different things, and only one of them shows up in a status dashboard.

The fix is observability that runs continuously, not retrospectively. A4.2 should land **`agent_loop.py` writing per-iter knob-coverage and pair-repeat numbers to a sidecar JSON** so the next time someone watches the overnight run progress, they're watching exploration, not iteration count. The Spark substrate was free; the corpus quality is what determined whether downstream work could use it. Measuring corpus quality cheaply, while the loop is still running, makes the next overnight worth running.

## State of the apps

The Autoresearch arc now has nine pieces: A4 (the loop), A5 (the rails), A6 (the rerank we never finished), A7 (the curator pre-prep), A8 (the LoRA distillation), A8.2 implied (the rematch, blocked on more corpus), and now A9 (this observability pass). The remaining open work is A4.2 — the 200-iter rerun with anti-repeat and (ideally) widened prompt history. After that runs, the A8 rematch becomes the next natural article: same recipe, the corpus distillation actually had a chance to learn from.

Other arcs unchanged. Second Brain is at four articles, LLM Wiki opener still queued, Looking Beyond Spark at three.

:::hardware[Same trajectory shape, frontier iteration rate]
The 73-minute Spark wall produced 50 iterations × ~88 s/iter (1.23 s NIM proposer + ~85 s for the 60-step taste-test training). Move proposer + trainer to an H100 80 GB and the per-iter wall drops toward ~25 s (proposer ~0.3 s, trainer ~25 s, bandwidth-bound) — a 50-iter run becomes 21 minutes. An H200's HBM3e or a B200's 8 TB/s collapses it further toward 10 min for 50 iters, or 200 iters in the same overnight wall. The interesting coefficient *isn't* iter rate, though; it's that **wider search-space coverage** is what the corpus distillation actually needs. Faster hardware buys more iterations; a `block_repeat` rail and a longer history window buy more *unique* iterations. The corpus quality is the lever, not the wall.
:::
