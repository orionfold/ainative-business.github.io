---
module: reward
title: fieldkit.reward
summary: The verifier→reward adapter (RLVR Phase 3) — Reward, RewardAdapter, group_advantage, RewardError. The eval harness IS the reward model — a thin adapter that turns any fieldkit.eval scorer into a (success, failure_class, auxiliary) reward, reusing lineage.FailureLabel. No learned reward model.
order: 17
---

## What it is

The **reward** half of the closed-loop RLVR engine
(`_SPECS/rlvr-loop-v1.md` §5, Phase 3 / Bet 1 of the "machine that builds
machines" roadmap). It realizes the disruptive move the whole roadmap points at:
**the eval harness *is* the reward model**. `fieldkit.eval` already ships seven
deterministic verifiers — `patent_claim_validity` (7-dim judge),
`office_action_argument` (4-dim judge), `prior_art_relevance` (Spearman ρ),
`irac_structure` (4-checklist regex), `mcq_letter`, `numeric_match`,
`is_refusal` — plus `exact_match` / `contains`. Those are *exactly* the
well-formed verifiers GRPO/RLVR scores rollouts against, with **no learned
reward model**. `fieldkit.reward` is a **thin adapter** over them; it adds no
scoring logic of its own (RV-2).

It is the scorer that `fieldkit.rl.RLLoop` consumes step by step. Where
`fieldkit.eval` *measures* and `fieldkit.lineage` *records*, this module
*rewards* — the one new translation layer between an offline verifier and an
online RL gradient.

## The reward is a tuple, not a scalar (RV-3)

Binary keep/revert **mode-collapses**: the project saw 5/5 train keeps on one
knob and 0/8 held-out generalization from a 42-row corpus. So the reward is a
`(success, failure_class, auxiliary)` tuple. The categorical `failure_class`
densifies the signal — and it is **already modeled** as
`fieldkit.lineage.FailureLabel` (a 10-class string enum with an
`is_informational` predicate). The reward **reuses `FailureLabel`**; it does not
invent an enum. That means the loop's per-step `Trial` label *is* the reward
signal — one vocabulary, two consumers (RV-7).

## The surfaces

- **`Reward`** — the `(success, failure_class, auxiliary)` tuple. `success` is
  the pass bit; `failure_class` is a `FailureLabel` (`KEEP` on a pass, `CRASH`
  when the verifier raised, `DISCARD` for a scored miss); `auxiliary` carries the
  densifying signal — the raw verifier `score` (partial credit for the
  0.25-granularity `irac_structure`, the ρ for `prior_art_relevance`), a
  `refusal` flag, the `scorer` name. `.scalar` is the value `group_advantage`
  standardizes (the partial-credit score when present, else `1.0`/`0.0`);
  `.is_informational` mirrors the label; `.to_dict()` is the serializable view.
- **`RewardAdapter`** — wraps one `fieldkit.eval` scorer
  (`Callable[[predicted, expected, **kw], float]`) so a rollout becomes a
  `Reward`. Construct with the `verifier`, a `pass_threshold` (the score at/above
  which the rollout is a keep — `1.0` for binary scorers, lower for graded ones),
  and `scorer_kwargs` (forwarded to the scorer, filtered to the kwargs it
  accepts — a judge for `patent_claim_validity`, `rel_tolerance` for
  `numeric_match`). `.score(rollout)` returns the reward; `.score_group(rollouts)`
  scores a whole rollout bundle. A verifier that raises is caught and returns a
  `CRASH`-labelled reward, so one bad rollout never sinks the group.
- **`group_advantage(rewards, *, normalize_std=True, eps=1e-8)`** — GRPO's
  value-network-free baseline: standardize the group's scalar rewards by
  subtracting the group mean (the baseline a critic would estimate) and, when
  `normalize_std`, dividing by the group spread (guarded by `eps`). A degenerate
  group (every rollout scoring the same) yields an **all-zero** advantage vector
  — no spurious gradient. With `normalize_std=False` the centered advantages are
  returned without the spread division.
- **`RewardError`** — raised on a caller mistake (a non-callable verifier, a
  rollout with no `prediction`). A verifier that raises *mid-score* is **not**
  this error — it becomes a `CRASH`-labelled `Reward`.

## What it is not

It does **not** ship a new scorer (it wraps the built `fieldkit.eval` ones, RV-2),
train anything (that's `fieldkit.rl`), or call an LLM of its own — a judge-backed
verifier brings its own `fieldkit.eval.Judge`; this module just calls it.
Deterministic Python, pure stdlib + `fieldkit.eval` / `fieldkit.lineage` — no
torch, no numpy (invariant #4).
