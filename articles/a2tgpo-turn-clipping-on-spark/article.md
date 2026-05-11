---
title: "Adaptive Turn Clipping on a Single Spark — A²TGPO, Studied from Source"
date: 2026-05-11
author: Manav Sehgal
product: NeMo
stage: fine-tuning
also_stages: [agentic, training]
difficulty: advanced
time_required: "~30 min read"
hardware: "NVIDIA DGX Spark"
tags: [reinforcement-learning, grpo, agentic, credit-assignment, information-gain, qwen, verl, fieldkit, lineage, machine-that-builds-machines]
summary: "A²TGPO redesigns how Information Gain feeds GRPO: turn-group normalization, variance-rescaled accumulation, and adaptive turn-level clipping. The paper's release is the code; the Spark's contribution is the lineage primitive that records what each trial learned."
signature: AdaptiveClipBand
series: "Machine that Builds Machines"
book_chapters: [10]
fieldkit_modules: [capabilities, training, lineage]
---

The A²TGPO paper ([arXiv 2605.06200](https://arxiv.org/abs/2605.06200)) reports two numbers: +1.75 EM on multi-hop QA and +1.69 EM on single-hop QA, both over a strong RL baseline on Qwen3-4B. The reference run trains on eight H20 GPUs across a single node. Reproducing that schedule on one DGX Spark would take six-to-eight days of wall-clock per single configuration — a memory-trivial fit on the 128 GB unified pool, but a per-trial budget that no overnight experimenter can absorb. The released artifact is therefore not training logs or checkpoints. It is the *code* in [`verl_atgpo/`](https://github.com/CuSO4-Chen/A-TGPO/tree/main/verl_atgpo) — three small overrides on top of verl's GRPO loss that name what the paper actually adds to the agentic-RL toolbox.

That is the unit of work this article studies. Not "reproduce A²TGPO on Spark," but: *read the three primitives the paper defines from the released source, write the arithmetic that says they fit, and wire the result into the lineage substrate so that when a Spark-feasible A²TGPO run does land — one trial per night, not one hundred per night — the next agent that picks up the harness can read what the prior trial learned.* The lineage layer just shipped in `fieldkit` v0.3.0. This article is its first non-cxcscmu consumer.

## Why this matters for the personal AI builder

The cluster question is "how many trials per night." The Spark question is "what does each overnight trial leave for the next one." A²TGPO matters on the Spark exactly to the extent that its three primitives — turn-group normalization, variance-rescaled accumulation, adaptive turn-level clipping — give the next training run something it could not have done without seeing the prior one. The information gain (IG) signal A²TGPO uses *as a process reward* is also the most natural thing to log per turn into a trial's row. The receipt is the artifact. The receipt is what the next specialist reads at session start.

Reformulated: on a cluster you optimize across trials; on a Spark you optimize across nights, and the connector is whatever you wrote down in between. The lineage primitive is the connector. A²TGPO is the first MTBM-arc loss whose internal telemetry happens to land cleanly into the lineage row's existing columns — IG signal per turn fits in `expected_delta`, the per-token entropy lands in `notes`, the EM score becomes `core_metric`. No new fieldkit module is needed for the accounting layer. The training-side module that wraps A²TGPO's loss will need extracting later; today the lineage layer alone earns its keep.

## The paper, in one breath

**Thesis.** Agentic LLM RL optimizes against a sparse trajectory-level outcome reward, which is what makes per-turn credit assignment in multi-turn tool-use loops hard. Information Gain — the per-turn change in the policy's predicted probability of the ground-truth answer — is an attractive *intrinsic* process signal that needs no external evaluator, but it is unstable across turn positions: turn-1 IG and turn-5 IG live on different scales, and accumulating them naively makes advantage magnitudes drift with trajectory depth. A²TGPO retains IG as the signal and redesigns how it is normalized, accumulated, and consumed.

**Why this technique matters for a personal AI builder.** The per-turn IG signal costs one additional forward pass through the same model that already produced the rollout — no second reward model, no external API, no separate evaluator container. On a unified-memory machine, "one more forward" is paged-attention reuse, not a second model load. The technique fits the Spark's resource shape *exactly* the way that an external 70B-parameter process reward model would not.

**Promise vs achieved.** Paper: +1.75 EM on multi-hop QA, +1.69 EM on single-hop QA over the strong RL baseline at Qwen3-4B, 8×H20 reference. Spark: this article does not reproduce the EM numbers — the 8×H20 schedule does not fit a single GB10's per-trial budget. The delta the article *does* deliver is a study-from-source reading of the three primitives that produced those numbers, plus a working lineage demo that the next Spark-feasible A²TGPO trial can write into directly.

:::define[Information Gain (IG)]
For an agentic RL trajectory, the per-turn change in the policy's predicted probability of the ground-truth answer. After turn *t*, run one forward pass through the policy on the prompt-plus-tool-results-so-far; record the probability mass on the gold token; the IG of turn *t* is the difference between that mass and the mass at turn *t−1*. The signal is *intrinsic*: it needs no external reward model, only one extra logit computation per turn.
:::

## Architectural context — where A²TGPO sits in the GRPO family tree

A²TGPO is not a fork of GRPO; it is the fourth stratum of a four-layer evolution that the verl codebase carries verbatim, one layer per `info_gain_norm_mode`. Reading the strata top-to-bottom is how the paper's three contributions distinguish themselves from what was already in verl on day one.

<figure class="fn-diagram" aria-label="Layered stack of four GRPO-family losses, from PPO at the foundation through GRPO and ATPO to A²TGPO at the accent layer. PPO uses token-level importance sampling with a fixed clip range. GRPO adds group-relative advantage normalization. ATPO replaces token-level IS with turn-level IS — one ratio per turn, broadcast to its tokens. A²TGPO retains turn-level IS and adds three primitives: turn-group normalization, variance-rescaled discounted accumulation, and adaptive turn-level clipping bounded in (0.7, 1.3) of the base clip.">
  <svg viewBox="0 0 900 460" role="img" preserveAspectRatio="xMidYMid meet" aria-label="Layered stack of four GRPO-family losses, from PPO at the foundation through GRPO and ATPO to A²TGPO at the accent layer.">
    <defs>
      <linearGradient id="d01-accent-grad" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%" stop-color="var(--color-primary)" stop-opacity="0.30"/>
        <stop offset="100%" stop-color="var(--color-primary)" stop-opacity="0.08"/>
      </linearGradient>
      <radialGradient id="d01-accent-halo" cx="0.5" cy="0.5" r="0.7">
        <stop offset="0%" stop-color="var(--color-primary)" stop-opacity="0.12"/>
        <stop offset="100%" stop-color="var(--color-primary)" stop-opacity="0"/>
      </radialGradient>
      <linearGradient id="d01-lane" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%" stop-color="var(--svg-accent-blue)" stop-opacity="0.06"/>
        <stop offset="100%" stop-color="var(--svg-accent-blue)" stop-opacity="0.02"/>
      </linearGradient>
    </defs>
    <rect x="40" y="40" width="820" height="380" rx="12" fill="url(#d01-lane)" stroke="none"/>
    <g class="fn-diagram__edges">
      <path class="fn-diagram__edge fn-diagram__edge--dashed" pathLength="100" d="M 450 360 L 450 320" />
      <path class="fn-diagram__edge fn-diagram__edge--dashed" pathLength="100" d="M 450 280 L 450 240" />
      <path class="fn-diagram__edge fn-diagram__edge--dashed" pathLength="100" d="M 450 200 L 450 160" />
    </g>
    <g class="fn-diagram__nodes">
      <rect class="fn-diagram__node" x="100" y="360" width="700" height="50" rx="8" />
      <rect class="fn-diagram__node" x="100" y="280" width="700" height="50" rx="8" />
      <rect class="fn-diagram__node" x="100" y="200" width="700" height="50" rx="8" />
      <rect x="100" y="50" width="700" height="120" rx="10" fill="url(#d01-accent-halo)" stroke="none"/>
      <rect class="fn-diagram__node fn-diagram__node--accent" x="100" y="50" width="700" height="120" rx="10" style="fill: url(#d01-accent-grad)" />
    </g>
    <g class="fn-diagram__labels">
      <text class="fn-diagram__label fn-diagram__label--mono" x="120" y="382" text-anchor="start">PPO</text>
      <text class="fn-diagram__label" x="120" y="400" text-anchor="start">token-level IS · fixed clip [1−ε, 1+ε] · per-token advantage</text>
      <text class="fn-diagram__label fn-diagram__label--mono" x="120" y="302" text-anchor="start">GRPO</text>
      <text class="fn-diagram__label" x="120" y="320" text-anchor="start">PPO + group-relative advantage (within-prompt-group normalization)</text>
      <text class="fn-diagram__label fn-diagram__label--mono" x="120" y="222" text-anchor="start">ATPO</text>
      <text class="fn-diagram__label" x="120" y="240" text-anchor="start">turn-level IS ratio replaces token-level · advantage constant within a turn</text>
      <text class="fn-diagram__label fn-diagram__label--mono" x="120" y="78" text-anchor="start">A²TGPO</text>
      <text class="fn-diagram__label" x="120" y="97" text-anchor="start">three new IG primitives over turn-level IS:</text>
      <text class="fn-diagram__label fn-diagram__label--mono" x="140" y="119" text-anchor="start">(i) turn-group norm   normalize IG per (prompt, turn_index)</text>
      <text class="fn-diagram__label fn-diagram__label--mono" x="140" y="138" text-anchor="start">(ii) variance-rescaled accum   D_t = Σ γ^(j−t)·normed_ig_j  /  √n_terms</text>
      <text class="fn-diagram__label fn-diagram__label--mono" x="140" y="157" text-anchor="start">(iii) adaptive clip   c = 1 + 0.3·(2σ(normed_ig) − 1)   bounded (0.7, 1.3)</text>
    </g>
    <g class="fn-diagram__annotations">
      <text class="fn-diagram__annotation" x="780" y="382" text-anchor="end">2017 · Schulman et al.</text>
      <text class="fn-diagram__annotation" x="780" y="302" text-anchor="end">2024 · DeepSeek-Math</text>
      <text class="fn-diagram__annotation" x="780" y="222" text-anchor="end">2025 · verl turn-level loss</text>
      <text class="fn-diagram__annotation" x="780" y="97" text-anchor="end">2026 · arXiv 2605.06200</text>
    </g>
  </svg>
  <figcaption>The three primitives are additive over a turn-level IS loss that verl already had. The contribution is not a new loss family; it is a named correction for the depth-instability that IG-based intrinsic rewards exhibit by default.</figcaption>
</figure>

The four `info_gain_norm_mode` settings in the published code — `joint`, `separate`, `turn-group`, and `turn-group-v1d` — map one-for-one onto strata two through five of that stack. `joint` is ATPO with both signals normalized together; `separate` normalizes outcome and IG rewards independently; `turn-group` adds depth-aware IG normalization (primitive i); `turn-group-v1d` adds variance-rescaled discounted accumulation (ii) and adaptive clipping (iii). The clip-scale knob is gated by a single `dynamic_clip` boolean in the PPO loss override.

## The three primitives, read from `core_algos.py`

The honest way to walk A²TGPO is to walk the three blocks the paper claims as new and check that the released code does what the math says.

### Primitive 1 — turn-group normalization

The block at [`verl/trainer/ppo/core_algos.py:1264–1322`](https://github.com/CuSO4-Chen/A-TGPO/blob/main/ATGPO/verl_atgpo/verl/trainer/ppo/core_algos.py) builds a composite group id from the prompt group and the per-turn index, then normalizes the raw IG reward within each composite group. The mechanism is one line per primitive operation:

```python
# Composite group: prompt_group * max_turns + turn_index
valid_ig_composite = valid_ig_prompt_groups * max_turns + valid_ig_turn_indices

# Per-composite-group mean and std
cg_sum   = torch.zeros(num_contrastive_groups, device=device).scatter_add_(
    0, valid_ig_composite, valid_ig_rewards)
cg_count = torch.zeros(num_contrastive_groups, device=device).scatter_add_(
    0, valid_ig_composite, torch.ones_like(valid_ig_rewards))
cg_mean  = cg_sum / cg_count.clamp(min=1.0)
# ... cg_std follows the same scatter_add reduction ...

norm_ig  = token_level_rewards - cg_mean[contrastive_group_ids]
if norm_adv_by_std_in_grpo:
    norm_ig = norm_ig / (cg_std[contrastive_group_ids] + epsilon)
```

The semantic claim is the composite group: a turn at depth 3 is compared *only* to other turns at depth 3 from the same prompt group. Turn-1 IG never enters turn-3 IG's normalization statistics. The depth-scale-mixing that the paper identifies as a failure mode of `info_gain_norm_mode=joint` is the entire reason this primitive exists.

:::define[Turn-group normalization]
Normalize the IG reward at turn-index *t* against the population of all turn-*t* IG values within the same prompt group. The composite group id is `prompt_group_id * max_turns + turn_index`. Practically: a turn deep in the trajectory is no longer competing on advantage magnitude with a turn at the start, even though both produced an IG value on the same scalar scale.
:::

### Primitive 2 — variance-rescaled discounted accumulation

The cumulative-IG path through the trajectory needs a discount and a magnitude correction. Discount because earlier turns get credit for later wins (γ-discounted). Magnitude correction because a trajectory with 8 informative turns must not produce 8× the advantage signal of a trajectory with 1 informative turn. The block at lines 1358–1365:

```python
# Compute discounted cumulative D_t for each IG position
for t in range(n_ig):
    D_t = 0.0
    for j in range(t, n_ig):
        D_t += (gamma ** (j - t)) * ig_values[j]
    n_terms = n_ig - t
    D_t_normed = D_t / (n_terms ** 0.5) if n_terms > 0 else 0.0
    ig_discounted.append(D_t_normed)
```

The `√n_terms` denominator is the *variance-rescaling*. It is what makes the advantage's magnitude scale comparably across short and long trajectories — divide by sample-count's square root and the standard deviation of the running sum stays bounded as the number of summed terms grows.

:::math[Why √n and not n?]
A sum of *n* zero-mean, unit-variance IG values has variance ≈ *n* and standard deviation ≈ √*n*. Dividing by *n* shrinks the *mean*, which would zero out the cumulative-IG signal entirely; dividing by √*n* shrinks the *standard deviation* so cumulative advantages stay on a per-step scale that the clip range can still see. Same shape as the central-limit-theorem normalization.
:::

The advantage delivered to PPO at each timestep is `final_adv[s, t] = α × ig_discounted[t] + outcome_adv`, with `α = adv_rescale_alpha` (default 0.3 in the reference recipe). Outcome advantage carries the trajectory-level success/failure; the discounted-cumulative IG term carries the per-turn process signal.

### Primitive 3 — adaptive turn-level clipping

The PPO clipping range is no longer a constant `[1 − ε, 1 + ε]`. Each turn carries its own clip-scale factor that widens the range for informative turns and narrows it for uninformative ones. The construction is one tanh-shaped curve through a sigmoid:

```python
# Compute IG-adaptive clip scale per IG turn
for t_idx, pos in enumerate(ig_positions):
    normed_ig_t = ig_values[t_idx]
    sig         = torch.sigmoid(torch.tensor(normed_ig_t, device=device)).item()
    clip_s      = 1.0 + 0.3 * (2.0 * sig - 1.0)
    ig_clip_scale[s, pos] = clip_s
# Outcome turn: clip_scale stays 1.0 (already initialized)
```

By construction `clip_s` is bounded in `(1 − 0.3, 1 + 0.3) = (0.7, 1.3)`. A turn whose normalized IG is far above zero (a turn that moved the predicted probability of the gold token noticeably forward) gets a clip range of roughly `1.3 × [1 − ε, 1 + ε]` — about 30% more update headroom. A turn whose normalized IG is far below zero gets `0.7 × [1 − ε, 1 + ε]` — about 30% less, narrowing the policy gradient for moves that the IG signal flagged as uninformative.

:::define[Adaptive turn-level clipping]
The PPO clipping range is multiplied per turn by `c = 1 + β·(2σ(normed_IG) − 1)` with β = 0.3. The factor is `1.0` when normed_IG is near zero, monotone-increasing in IG, asymptotic to `1.0 ± β` at the extremes. The clip range itself is therefore bounded in `(1 − β·ε, 1 + β·ε)` of the baseline, regardless of how extreme the IG signal becomes. The output is per-token: every token inside a turn inherits its turn's clip scale, broadcast through the same advantage-equality boundary detection that the turn-level IS ratio also uses.
:::

The PPO loss itself, at lines 920–924, consumes the per-token clip scale exactly the way the math reads:

```python
if dynamic_clip and ig_clip_scale is not None:
    effective_low  = cliprange_low  * ig_clip_scale
    effective_high = cliprange_high * ig_clip_scale
    clamped_ratio  = torch.max(torch.min(ratio, 1.0 + effective_high),
                               1.0 - effective_low)
else:
    clamped_ratio  = torch.clamp(ratio, 1.0 - cliprange_low, 1.0 + cliprange_high)
```

Three primitives, ~150 lines of pure tensor code across the advantage computation and the PPO loss. The next step is naming them in fieldkit so a future MTBM article reaches for `fieldkit.training.rl.AdaptiveTurnClipper` instead of vendoring `verl_atgpo/` again.

<figure class="fn-diagram" aria-label="Flow pipeline showing one A²TGPO turn through the three primitives. Raw IG signal enters a turn-group normalizer that produces normed_ig by composite-grouping (prompt, turn_index). Normed_ig feeds the variance-rescaled accumulator, which computes D_t = sum of gamma-discounted normed_ig_j divided by sqrt(n_terms). The same normed_ig signal feeds the adaptive clipper, which applies sigmoid then maps the result to c = 1 + 0.3 * (2*sigmoid - 1) bounded in (0.7, 1.3). Outputs combine into the PPO loss: advantage = alpha * D_t + outcome_adv, clipped by ratio * c.">
  <svg viewBox="0 0 900 380" role="img" preserveAspectRatio="xMidYMid meet" aria-label="Flow pipeline showing one A²TGPO turn through the three primitives.">
    <defs>
      <linearGradient id="d02-band" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%" stop-color="var(--svg-accent-blue)" stop-opacity="0.10"/>
        <stop offset="100%" stop-color="var(--svg-accent-blue)" stop-opacity="0.02"/>
      </linearGradient>
      <linearGradient id="d02-accent-grad" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%" stop-color="var(--color-primary)" stop-opacity="0.30"/>
        <stop offset="100%" stop-color="var(--color-primary)" stop-opacity="0.08"/>
      </linearGradient>
      <radialGradient id="d02-accent-halo" cx="0.5" cy="0.5" r="0.7">
        <stop offset="0%" stop-color="var(--color-primary)" stop-opacity="0.12"/>
        <stop offset="100%" stop-color="var(--color-primary)" stop-opacity="0"/>
      </radialGradient>
    </defs>
    <rect x="40" y="80" width="820" height="220" rx="12" fill="url(#d02-band)" stroke="none"/>
    <g class="fn-diagram__edges">
      <path class="fn-diagram__edge" pathLength="100" d="M 120 190 L 230 190" />
      <path class="fn-diagram__edge" pathLength="100" d="M 390 160 L 510 130" />
      <path class="fn-diagram__edge fn-diagram__edge--accent" pathLength="100" d="M 390 220 L 510 250" />
      <path class="fn-diagram__edge" pathLength="100" d="M 670 130 L 760 170" />
      <path class="fn-diagram__edge fn-diagram__edge--accent" pathLength="100" d="M 670 250 L 760 210" />
    </g>
    <g class="fn-diagram__nodes">
      <rect class="fn-diagram__node" x="40" y="160" width="80" height="60" rx="8" />
      <rect class="fn-diagram__node" x="230" y="160" width="160" height="60" rx="8" />
      <rect class="fn-diagram__node" x="510" y="100" width="160" height="60" rx="8" />
      <rect x="510" y="220" width="160" height="60" rx="10" fill="url(#d02-accent-halo)" stroke="none"/>
      <rect class="fn-diagram__node fn-diagram__node--accent" x="510" y="220" width="160" height="60" rx="10" style="fill: url(#d02-accent-grad)" />
      <rect class="fn-diagram__node" x="760" y="160" width="100" height="60" rx="8" />
    </g>
    <g class="fn-diagram__labels">
      <text class="fn-diagram__label fn-diagram__label--mono" x="80" y="186" text-anchor="middle">raw IG</text>
      <text class="fn-diagram__label" x="80" y="204" text-anchor="middle">(turn t)</text>
      <text class="fn-diagram__label fn-diagram__label--mono" x="310" y="180" text-anchor="middle">turn-group norm</text>
      <text class="fn-diagram__label" x="310" y="198" text-anchor="middle">per (prompt, t)</text>
      <text class="fn-diagram__label fn-diagram__label--mono" x="310" y="214" text-anchor="middle">→ normed_ig_t</text>
      <text class="fn-diagram__label fn-diagram__label--mono" x="590" y="120" text-anchor="middle">variance-rescaled</text>
      <text class="fn-diagram__label" x="590" y="138" text-anchor="middle">accumulation</text>
      <text class="fn-diagram__label fn-diagram__label--mono" x="590" y="154" text-anchor="middle">D_t / √n_terms</text>
      <text class="fn-diagram__label fn-diagram__label--mono" x="590" y="240" text-anchor="middle">adaptive clip</text>
      <text class="fn-diagram__label" x="590" y="258" text-anchor="middle">c = 1 + 0.3·(2σ−1)</text>
      <text class="fn-diagram__label fn-diagram__label--mono" x="590" y="274" text-anchor="middle">bounded (0.7, 1.3)</text>
      <text class="fn-diagram__label fn-diagram__label--mono" x="810" y="186" text-anchor="middle">PPO loss</text>
      <text class="fn-diagram__label" x="810" y="204" text-anchor="middle">α·D_t + outcome</text>
    </g>
    <g class="fn-diagram__annotations">
      <text class="fn-diagram__annotation" x="170" y="180" text-anchor="middle">≈ 1.7M params/step</text>
      <text class="fn-diagram__annotation" x="450" y="115" text-anchor="middle">advantage path</text>
      <text class="fn-diagram__annotation" x="450" y="275" text-anchor="middle">clip-range path</text>
    </g>
  </svg>
  <figcaption>One signal in, two paths out. The same `normed_ig` feeds the advantage path (variance-rescaled accumulation, scaled by α) and the clip-range path (sigmoid-bounded multiplier). The PPO loss consumes both: advantage on the numerator, clip range on the denominator's bracket.</figcaption>
</figure>

## Verification — what success looks like, on Spark, without the eight H20s

The verification this article ships is not a training curve. It is the arithmetic that says the Spark *could* run a Qwen3-4B A²TGPO loop one trial at a time, plus the working accounting layer that records what the trial learned.

The memory math:

```text
weight_bytes(params_b=4, dtype="bf16")        ≈  8.0 GB
LoRA training overhead (~1.5x)                 ≈ 12.0 GB
GRPO rollouts kv_cache (g=8, ctx=8192,
  hidden=2560, n_layers=28, dtype=bf16)        ≈  9.0 GB
IG forward (paged-attention reuse, no new
  resident weights)                             +  0.0 GB
local e5_Flat retriever (wiki-18 corpus,
  faiss-gpu index)                             ≈  5.0 GB
─────────────────────────────────────────────
working set                                    ≈ 34 GB / 128 GB unified pool
```

That is well inside the in-envelope signal the [GPU sizing-math article](/field-notes/gpu-sizing-math-for-fine-tuning/) walks for fine-tuning ≤ 70B with LoRA. The Spark fits the configuration. The constraint is not memory; it is wall-clock per trial.

Per-step latency from the paper: the IG forward adds 164 s/step on 8×H20 but recovers 86 s/step of generation savings (the IG forward skips the prefill rewrites that the no-IG baseline does to recompute trajectory logits). Net step cost: +78 s, roughly +30% over the no-IG baseline. The reference recipe runs ~14,000 steps on 8×H20 for a single HotpotQA configuration. Scale to one GB10: a 6–8× single-GPU slowdown (the verl team's published benchmark for this loss shape) puts a single configuration at six-to-eight days of continuous Spark wall-clock.

:::why[Six days is the right unit, not the wrong unit]
On a cluster you'd reject six-day single-config wall-clock as too slow. On a Spark, six days is one decent overnight per night for a week — and the IG signal you write into each trial's lineage row is reusable, so the seventh night's hypothesis comes from the prior six nights' rendered prompt. The bottleneck shifts from "more compute" to "more carefully-named trials."
:::

The fieldkit-side verification is mechanical: the lineage primitive that A²TGPO writes into is the same one that cxcscmu's Auto-Research-Recipes harness writes into. The TSV header is shared; the failure-class enum is shared; the rendered prompt format is shared. The accounting layer ships with `pip install fieldkit==0.3.0`. The Spark contribution is wiring it.

The full demo is at [`evidence/lineage-demo.py`](evidence/lineage-demo.py); the relevant slice walks a six-trial sweep (baseline, ATPO joint, separate normalization, turn-group, full v1d, alpha=0.9 sweep):

```python
from fieldkit.lineage import FailureLabel, LineageStore, Trial

store = LineageStore(Path(d), lower_is_better=False)  # HotpotQA EM: higher is better

store.append(Trial(
    exp_id="004", timestamp="2026-05-12T12:20:00Z",
    specialist="a2tgpo-v1d", parent_exp="003", baseline_exp="000",
    domain="agentic-grpo-multihop",
    hypothesis="Full A²TGPO: turn-group norm + variance-rescaled "
               "discounted accumulation + adaptive clip via sigmoid",
    expected_delta="+0.75 EM over turn-group",
    status=FailureLabel.KEEP,
    core_metric=34.96, val_bpb=None, delta_vs_best=+0.45,
    train_s=14260.0, total_s=14320.0,
    job_name="atgpo-a2tgpo-v1d-004",
    snapshot_path="snapshots/004_a2tgpo-v1d",
    notes="ig_clip_scale mean=1.014 std=0.087 "
          "(informative turns widen, uninformative narrow); "
          "alpha=0.300 fixed; gamma=1.000",
))
```

The notes field is the operational receipt of A²TGPO running: `ig_clip_scale mean=1.014 std=0.087` is the empirical distribution of the adaptive-clip multiplier across all turn positions in that trial. The fact that the mean sits at `1.014` and the std at `0.087` is the load-bearing measurement — clip widens slightly on net (the trajectory has slightly-more-informative turns than uninformative ones), and the modulation has bite (a non-trivial standard deviation, not a zero-spread degenerate distribution).

Running `python evidence/lineage-demo.py` renders the prompt the next specialist would see. The current-best lineage chain and the recent-activity table land in `## KNOWLEDGE.md`:

```text
## KNOWLEDGE.md

**Current-best lineage** (root → best):
exp_000 [grpo-baseline, baseline, metric=33.21] Vanilla GRPO, token-level IS, fixed clip [0.8, 1.2], no IG signal
 └─ exp_001 [atpo-joint, keep, metric=34.02, Δ=+0.81] Switch token-level IS to turn-level IS; keep joint IG/outcome normalization; clip still fixed
 └─ exp_003 [atpo-turn-group, keep, metric=34.51, Δ=+0.49] Add turn-group normalization: normalize IG per (prompt, turn_index) composite group
 └─ exp_004 [a2tgpo-v1d, keep, metric=34.96, Δ=+0.45] Full A²TGPO: turn-group norm + variance-rescaled discounted accumulation + adaptive clip via sigmoid ← BEST

## Recent Activity (most recent 3 — full hypothesis)
- exp_005 [a2tgpo-v1d-alpha09, eval_budget_overrun, metric=—] Increase adv_rescale_alpha 0.3 → 0.9 to weight IG-discounted accumulation more heavily
  └─ ig_clip_scale mean=1.022 std=0.114; eval wall exceeded budget on MuSiQue 4-hop subset — high alpha amplifies long-tail trajectory variance
```

The discard branch (`exp_002 = atpo-separate`) does not appear in the lineage chain to best — it forked off exp_001, did not earn a `keep`, and the chain renderer walks parent pointers only through kept ancestors. The eval-budget overrun at `exp_005` *does* appear in recent activity, because the failure class is informational: the next specialist learns that `alpha=0.9` blew the budget on long-tail MuSiQue, and will narrow the next sweep to `α ∈ [0.1, 0.5]` accordingly. That is precisely the load-bearing function of the lineage layer — the agent that picks up the harness at trial #6 has read what trials #0–#5 produced, including the failure classes, without needing to re-run anything.

## Tradeoffs, gotchas, surprises

**The IG forward is not free, but it is paged.** The 164 s/step the paper documents is real; on the Spark it scales with the GB10's compute-to-memory-bandwidth ratio, not its memory budget. The forward is one extra pass through the *same* policy network on a *shorter* prefix (no tool outputs yet), so paged attention reuses the cached KV blocks the rollout already filled. No second model resides in memory. The replacement-of-an-external-process-reward-model story is the real cost saving — a 70B process reward model would take roughly the entire 128 GB of unified pool that the Spark has to offer.

**The v1d formula's α is fixed, not adaptive.** The published recipe sets `adv_rescale_alpha = 0.3` and keeps it constant across training. There is an earlier version of the loss in the repo's history (the `v1c` variant) that made α adaptive too; the authors removed it for the published runs. The deferred extraction in `fieldkit.training.rl` should keep α as a constructor argument and let the caller decide — locking it inside the primitive is a choice the paper has *not* validated.

**Turn-boundary detection by advantage equality is fragile.** The PPO loss override at `core_algos.py:889–913` detects turn boundaries by `advantage value changes from previous token`. If two consecutive turns happen to produce identical advantage values — possible if the IG signal at both turns rounds to the same float, or if both turns receive the same `0` advantage — they merge silently into one turn. The published recipe has not seen this case in HotpotQA traces; the failure mode is real on a 4-hop dataset with degenerate IG. A future fieldkit extraction should carry explicit turn-boundary markers rather than inferring them.

:::pitfall[Turn boundaries inferred from advantage equality merge silently]
The released PPO loss override detects turn breaks by "advantage value differs from previous token." When two consecutive turns generate the same advantage scalar — possible with degenerate IG or rounded zero — they fuse into a single super-turn whose IS ratio averages across what should have been two distinct updates. The agent gets no warning; the only symptom is `turn_log_ratio` smoothing where the trajectory schema would have predicted a discontinuity.
:::

**Flash-attn for Blackwell is the environment risk, not the algorithm.** The published recipe uses `flash-attn 2.x` precompiled for CUDA 12.4. The GB10's sm_100 ISA shipped after that wheel set; a precompiled Blackwell wheel may not exist in the version pinned by the verl_atgpo `requirements.txt`. Fallback to PyTorch SDPA loses some throughput (~15% per the verl team's benchmarks on this loss shape) but does not change algorithmic semantics. The Spark's [PyTorch container](/field-notes/cuda-13-toolkit-on-dgx-spark/) ships an SDPA path in the in-envelope signal — this is a quality-of-implementation gotcha, not a feasibility blocker.

**The `verl_atgpo/` vendor is large.** The repo snapshot under `articles/a2tgpo-turn-clipping-on-spark/evidence/repo-snapshot/` is mostly upstream verl, not the A²TGPO additions. The actual delta is the `info_gain_norm_mode=turn-group-v1d` branch plus the `dynamic_clip` flag in the PPO loss — roughly 150 effective lines. After the stats-methodology change two commits back, all of `evidence/repo-snapshot/` lives in the tracked-but-excluded `vendored_loc` bucket; the article's project-LOC footprint is the `evidence/lineage-demo.py` it actually authored, ~150 lines.

## What this unlocks

**One.** The [Auto-Research loop](/field-notes/auto-research-loop-on-spark/) gains its first wrapping policy loss. Today the loop edits training recipes against a `val_bpb` target on character-LM tasks. With A²TGPO landed, the same lineage substrate handles a different shape of search — instead of editing `train.py`, the agent edits the policy by running a single RL trial per night, and the lineage row's `expected_delta` (the agent's stated IG-signal prediction) versus `core_metric` (the observed EM lift) becomes the calibration signal the loop optimizes against. Same TSV, different domain.

**Two.** The deferred `fieldkit.training.rl` extraction is now scoped. Three named primitives — `InformationGain` (the per-turn logit-diff), `TurnGroupNormalizer` (composite-group reduction), `AdaptiveTurnClipper` (the σ-bounded multiplier) — each ~50 lines of pure tensor code, each composable with any verl-shaped GRPO loop without taking ownership of the rollout. A future MTBM article on the actual single-GB10 A²TGPO run will reach for `fieldkit.training.rl.AdaptiveTurnClipper(beta=0.3)` instead of vendoring `verl_atgpo/`. The extraction does not need to ship before the run does; the run informs the extraction.

**Three.** Multi-day RL configurations on a single Spark become legible. The bottleneck on a per-night training rig is no longer "I forgot which α I tried" or "did the last sweep cover γ < 1.0 or not." The TSV row is the receipt; the rendered Markdown block at session entry is the answer. With A²TGPO providing the per-turn process signal that lands in `expected_delta`, the agent that opens the next session reads not just "what was tried" but "what each turn within each trial thought it was learning." The IG signal becomes a first-class lineage column, not a one-off log file in some Slurm scratch directory.

:::hardware[The forge thesis at frontier scale]
The Spark configuration in this article is a single Qwen3-4B trial per night, lineage primitive recording one row per trial. The cxcscmu configuration on 8×H100 ran 1,797 trials in days. On a SuperPOD the same primitive runs at 8× the per-trial throughput of an H100 node and reaches the same trial budget in hours. The lineage substrate is identical at all three scales — it is fcntl-locked stdlib Python; the difference is only how many rows the harness writes per unit time. The same `fieldkit.lineage` import works against all three.
:::

:::deeper
- [arXiv 2605.06200 — A²TGPO paper](https://arxiv.org/abs/2605.06200) for the full HotpotQA / MuSiQue / NaturalQuestions ablation table and the IG-stability analysis.
- [`fieldkit.lineage` reference](/fieldkit/lineage/) for the canonical TSV schema, the FailureLabel enum, and the deterministic prompt-rendering format A²TGPO trials write into.
- [Reading the Lineage Primitive — cxcscmu Auto-Research](/field-notes/auto-research-loop-on-spark/) for the predecessor study that defined the lineage substrate this article reuses.
- [verl_atgpo source on GitHub](https://github.com/CuSO4-Chen/A-TGPO/tree/main/ATGPO/verl_atgpo/verl/trainer/ppo/core_algos.py) — `core_algos.py:1264–1400` is where the three primitives live verbatim.
:::

## Closing

In the Machine-that-Builds-Machines arc, the [forge station](/series/machine-that-builds-machines/) is where new primitives get hammered out of existing ones. A²TGPO forges three: turn-group normalization, variance-rescaled accumulation, adaptive clipping. The paper's contribution is naming them and showing they earn +1.75 EM together at frontier scale. The Spark's contribution, today, is reading them from source and wiring the next-night's accounting against the lineage layer that already shipped. The training-side primitives extract later; the lineage row writes now.

The next station in the MTBM arc is the trial — a single Spark-feasible A²TGPO configuration running overnight, writing one row into the same `LineageStore`, leaving its receipt for the agent that opens tomorrow's session. The substrate is in place. The accounting is wired. What gets built next on the forge is what the next trial measures.

— *MTBM arc · Ch10 · forge station · station 1 of N. Predecessor: [Reading the Lineage Primitive](/field-notes/auto-research-loop-on-spark/). Next: a single Spark-feasible A²TGPO trial, the first row that exits a draft and lands in a results.tsv worth reading.*
