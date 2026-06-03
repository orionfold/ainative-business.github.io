# Copyright 2026 Manav Sehgal
# SPDX-License-Identifier: Apache-2.0
"""`fieldkit.reward` — the verifier→reward adapter (RLVR Phase 3, Bet 1).

The **reward** half of the closed-loop RLVR engine
(`_SPECS/rlvr-loop-v1.md` §5). It realizes the disruptive move the whole roadmap
points at: **the eval harness *is* the reward model**. `fieldkit.eval` already
ships seven deterministic verifiers — `patent_claim_validity` (7-dim judge),
`office_action_argument` (4-dim judge), `prior_art_relevance` (Spearman ρ),
`irac_structure` (4-checklist regex), `mcq_letter`, `numeric_match`, `is_refusal`
— plus `exact_match` / `contains`. Those are *exactly* the well-formed verifiers
GRPO/RLVR scores rollouts against, with **no learned reward model**. This module
is a **thin adapter** over them; it adds no scoring logic of its own (RV-2).

Two reconciliation wins shape the design (RV-2/RV-3):

- **The reward is a `(success, failure_class, auxiliary)` tuple, not a scalar.**
  Binary keep/revert mode-collapses (the project saw 5/5 train keeps on one knob
  and 0/8 held-out generalization from a 42-row corpus). The categorical
  `failure_class` densifies the signal — and it is **already modeled** as
  `fieldkit.lineage.FailureLabel` (a 10-class string enum with an
  `is_informational` predicate). The reward **reuses `FailureLabel`**; it does
  not invent an enum. `auxiliary` carries the per-assertion / partial-credit
  float so the gradient sees more than a bit.
- **Group-relative advantage** (`group_advantage`) is the standardize-within-the-
  group step GRPO replaces a value network with: subtract the group mean, divide
  by the group spread. A degenerate group (every rollout scores the same) yields
  a zero advantage vector — no spurious gradient.

Per `feedback_llm_skill_pattern`: deterministic Python only — no ``anthropic``
import, no ``claude_agent_sdk`` import, no LLM call of its own (a judge-backed
verifier brings its own `fieldkit.eval.Judge`; this module just calls it). Pure
stdlib + `fieldkit.eval` / `fieldkit.lineage` — no torch, no numpy.
"""

from __future__ import annotations

import inspect
import math
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping, Sequence

from fieldkit.eval import is_refusal
from fieldkit.lineage import FailureLabel

__all__ = [
    "Reward",
    "RewardAdapter",
    "group_advantage",
    "RewardError",
]


class RewardError(Exception):
    """Raised when a reward cannot be computed for a configuration reason.

    A *verifier* that raises mid-score is **not** an error here — it is caught
    and turned into a ``CRASH``-labelled :class:`Reward` so one bad rollout
    never sinks the whole group. This exception is for caller mistakes: a
    verifier that isn't callable, a rollout missing both prediction and
    expected, a `pass_threshold` outside the verifier's range.
    """


@dataclass(frozen=True, slots=True)
class Rollout:
    """One sampled generation to be scored — the unit the reward grades.

    `prediction` is the model's output text; `expected` is the gold reference
    (or a rank-list / number / letter depending on the verifier). `rubric` is
    the optional per-row hint dict the patent-strategist judge scorers consume
    (claim_type, statutory_focus, …); `task_id` carries the source question id
    so a per-rollout reward can be cross-referenced back to the bench. This is a
    supporting type, deliberately *not* in ``__all__`` — :meth:`RewardAdapter.
    score` duck-types it (any object with ``.prediction``/``.expected``, or a
    mapping with those keys, works), so callers needn't import it.
    """

    prediction: str
    expected: str = ""
    rubric: Mapping[str, Any] | None = None
    task_id: str = ""


def _rollout_field(rollout: Any, name: str, default: Any = None) -> Any:
    """Read `name` off a Rollout-like object OR a mapping. Duck-typed (RV-2)."""
    if isinstance(rollout, Mapping):
        return rollout.get(name, default)
    return getattr(rollout, name, default)


@dataclass(frozen=True, slots=True)
class Reward:
    """The reward tuple — `(success, failure_class, auxiliary)` (RV-3).

    - `success` — did the rollout pass the verifier at the configured threshold?
    - `failure_class` — a :class:`fieldkit.lineage.FailureLabel`. ``KEEP`` on a
      pass; ``CRASH`` when the verifier itself raised; ``DISCARD`` for a scored
      miss (including a coherent refusal). Sharing the lineage vocabulary means
      the loop's per-step :class:`~fieldkit.lineage.Trial` label *is* the reward
      signal — one enum, two consumers (RV-7).
    - `auxiliary` — the densifying signal beyond the bit: the raw verifier
      `score` (partial credit for the 0.25-granularity `irac_structure`, the ρ
      for `prior_art_relevance`, etc.), a `refusal` flag, and the `scorer` name.

    `scalar` is the value `group_advantage` standardizes: the partial-credit
    `auxiliary["score"]` when present, else ``1.0``/``0.0`` from `success`.
    """

    success: bool
    failure_class: FailureLabel
    auxiliary: Mapping[str, Any] = field(default_factory=dict)

    @property
    def scalar(self) -> float:
        """The reward magnitude — partial-credit score if present, else binary.

        Prefers `auxiliary["score"]` (the dense per-assertion / Spearman /
        IRAC-quarter signal) so the gradient sees more than keep/revert; falls
        back to ``1.0``/``0.0`` when a verifier only emits a pass bit.
        """
        score = self.auxiliary.get("score") if self.auxiliary else None
        if isinstance(score, (int, float)) and not isinstance(score, bool):
            return float(score)
        return 1.0 if self.success else 0.0

    @property
    def is_informational(self) -> bool:
        """True if the label carries usable gradient signal (`FailureLabel`)."""
        return self.failure_class.is_informational

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "failure_class": self.failure_class.value,
            "scalar": round(self.scalar, 6),
            "auxiliary": dict(self.auxiliary),
        }


def _accepted_kwargs(fn: Callable[..., Any]) -> set[str] | None:
    """Return the kwarg names `fn` accepts, or ``None`` if it takes ``**kwargs``.

    Lets :meth:`RewardAdapter.score` pass only the keyword arguments a given
    verifier understands — `patent_claim_validity` wants ``judge`` + ``rubric``,
    `numeric_match` wants ``rel_tolerance``, `mcq_letter` wants ``strip_think``,
    `irac_structure` wants neither — without a TypeError per scorer.
    """
    try:
        sig = inspect.signature(fn)
    except (TypeError, ValueError):
        return set()
    names: set[str] = set()
    for p in sig.parameters.values():
        if p.kind is inspect.Parameter.VAR_KEYWORD:
            return None  # accepts anything
        if p.kind in (
            inspect.Parameter.KEYWORD_ONLY,
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
        ):
            names.add(p.name)
    return names


@dataclass
class RewardAdapter:
    """Turn any `fieldkit.eval` verifier into a reward callable (RV-2).

    Wraps one scorer — ``Callable[[predicted, expected, **kw], float]`` — so a
    rollout becomes a :class:`Reward`. The same contract `VerticalBench` uses,
    so every shipped scorer slots in unchanged:

    - **deterministic** — `irac_structure`, `mcq_letter`, `numeric_match`,
      `prior_art_relevance`, `exact_match`, `contains`;
    - **judge-backed** — `patent_claim_validity`, `office_action_argument`
      (construct with ``scorer_kwargs={"judge": Judge(...)}``; the loop reuses
      one warm judge across the group).

    `pass_threshold` is the score at/above which the rollout counts as a pass
    (``1.0`` for the binary scorers; lower it for the graded ones — e.g.
    ``0.75`` to treat a 3-of-4 IRAC answer as a keep). `scorer_kwargs` are
    forwarded to the scorer, filtered to the kwargs it actually accepts.

    Usage::

        adapter = RewardAdapter(irac_structure, pass_threshold=0.75)
        reward = adapter.score(Rollout(prediction=answer, expected=gold))
        reward.success            # True if ≥3 of 4 IRAC components present
        reward.scalar             # 0.0 / 0.25 / 0.5 / 0.75 / 1.0 — dense
        reward.failure_class      # FailureLabel.KEEP or .DISCARD
    """

    verifier: Callable[..., float]
    pass_threshold: float = 1.0
    scorer_kwargs: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not callable(self.verifier):
            raise RewardError(
                f"verifier must be callable, got {type(self.verifier).__name__}"
            )

    @property
    def scorer_name(self) -> str:
        return getattr(self.verifier, "__name__", "custom")

    def _call(self, prediction: str, expected: str, rubric: Mapping[str, Any] | None) -> float:
        accepted = _accepted_kwargs(self.verifier)
        call_kwargs: dict[str, Any] = {}
        # Per-row rubric hint, only if the scorer takes it (judge scorers do).
        if rubric is not None and (accepted is None or "rubric" in accepted):
            call_kwargs["rubric"] = rubric
        for k, v in self.scorer_kwargs.items():
            if accepted is None or k in accepted:
                call_kwargs[k] = v
        return float(self.verifier(prediction, expected, **call_kwargs))

    def score(self, rollout: Any) -> Reward:
        """Score one rollout → a :class:`Reward` tuple.

        `rollout` is a :class:`Rollout`, or any object / mapping carrying
        ``prediction`` (+ optional ``expected`` / ``rubric``). A verifier that
        raises is caught and returns a ``CRASH``-labelled reward (one bad
        rollout never sinks the group); a clean miss is ``DISCARD``; a pass is
        ``KEEP``. The numeric verifier score rides ``auxiliary["score"]`` so
        :attr:`Reward.scalar` is dense.
        """
        prediction = _rollout_field(rollout, "prediction")
        expected = _rollout_field(rollout, "expected", "") or ""
        rubric = _rollout_field(rollout, "rubric", None)
        if prediction is None:
            raise RewardError("rollout has no `prediction` to score")
        prediction = str(prediction)

        try:
            score = self._call(prediction, str(expected), rubric)
        except Exception as exc:  # noqa: BLE001 — one bad rollout, not a crash
            return Reward(
                success=False,
                failure_class=FailureLabel.CRASH,
                auxiliary={
                    "score": 0.0,
                    "scorer": self.scorer_name,
                    "error": f"{type(exc).__name__}: {exc}",
                },
            )

        if math.isnan(score):
            score = 0.0
        success = score >= self.pass_threshold
        refusal = is_refusal(prediction)
        label = FailureLabel.KEEP if success else FailureLabel.DISCARD
        return Reward(
            success=success,
            failure_class=label,
            auxiliary={
                "score": score,
                "scorer": self.scorer_name,
                "refusal": refusal,
            },
        )

    def score_group(self, rollouts: Sequence[Any]) -> list[Reward]:
        """Score a whole rollout group — ``[score(r) for r in rollouts]``."""
        return [self.score(r) for r in rollouts]


def group_advantage(
    rewards: Sequence[Reward],
    *,
    normalize_std: bool = True,
    eps: float = 1e-8,
) -> list[float]:
    """Group-relative advantage — GRPO's value-network-free baseline (RV-2).

    Standardizes the rollout group's scalar rewards: subtract the group mean
    (the baseline a value network would otherwise estimate) and, when
    `normalize_std`, divide by the group standard deviation. This is the exact
    move GRPO makes to drop the learned critic — the group *is* the baseline.

    A **degenerate group** — every rollout scoring the same (all pass, all fail,
    or a one-element group) — has zero spread and yields an **all-zero**
    advantage vector: no spurious gradient from a group that learned nothing.
    With `normalize_std=False` the centered (mean-subtracted) advantages are
    returned without the spread division.

    Operates on :attr:`Reward.scalar`, so partial-credit verifiers
    (`irac_structure`, `prior_art_relevance`) drive a graded advantage, not just
    a keep/revert bit.
    """
    if not rewards:
        return []
    scalars = [r.scalar for r in rewards]
    n = len(scalars)
    mean = sum(scalars) / n
    centered = [s - mean for s in scalars]
    if not normalize_std:
        return centered
    var = sum(c * c for c in centered) / n
    std = math.sqrt(var)
    if std <= eps:
        return [0.0] * n  # degenerate group — no advantage signal
    return [c / (std + eps) for c in centered]
