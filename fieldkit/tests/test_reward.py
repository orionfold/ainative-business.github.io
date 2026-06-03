# Copyright 2026 Manav Sehgal
# SPDX-License-Identifier: Apache-2.0
"""`fieldkit.reward` — the verifier→reward adapter (RLVR Phase 3, §5).

Covers the three locked decisions the module realizes:
- **RV-2** the verifier IS the reward — a thin adapter over each shipped
  `fieldkit.eval` scorer (deterministic + judge-backed), no new scoring logic;
- **RV-3** the `(success, failure_class, auxiliary)` tuple, `failure_class`
  reusing the built `lineage.FailureLabel` (KEEP / DISCARD / CRASH), with the
  dense partial-credit `scalar`;
- group-relative `group_advantage` (the value-network-free GRPO baseline) +
  the degenerate-group zero-advantage guard.
"""

from __future__ import annotations

import pytest

from fieldkit.eval import contains, irac_structure, mcq_letter, numeric_match
from fieldkit.lineage import FailureLabel
from fieldkit.reward import (
    Reward,
    RewardAdapter,
    RewardError,
    Rollout,
    group_advantage,
)


# ---------------------------------------------------------------------------
# RewardAdapter over the shipped scorers (RV-2)
# ---------------------------------------------------------------------------


def test_binary_scorer_pass_is_keep():
    adp = RewardAdapter(mcq_letter)
    r = adp.score(Rollout(prediction="The answer is B", expected="B"))
    assert r.success is True
    assert r.failure_class is FailureLabel.KEEP
    assert r.scalar == 1.0
    assert r.auxiliary["scorer"] == "mcq_letter"


def test_binary_scorer_miss_is_discard():
    adp = RewardAdapter(mcq_letter)
    r = adp.score(Rollout(prediction="A", expected="B"))
    assert r.success is False
    assert r.failure_class is FailureLabel.DISCARD
    assert r.scalar == 0.0


def test_graded_scorer_partial_credit_densifies_scalar():
    # irac_structure returns {0, .25, .5, .75, 1.0}; pass_threshold lets a
    # 3-of-4 answer count as a keep while scalar stays the dense 0.75 (RV-3).
    adp = RewardAdapter(irac_structure, pass_threshold=0.75)
    three_of_four = "Issue: whether. Under 35 USC 103 the rule. Here applied."
    r = adp.score(Rollout(prediction=three_of_four, expected=""))
    assert r.scalar == pytest.approx(0.75)
    assert r.success is True and r.failure_class is FailureLabel.KEEP


def test_scorer_kwargs_filtered_to_accepted_signature():
    # numeric_match takes rel_tolerance; mcq_letter would reject it. The adapter
    # filters kwargs to the scorer's signature, so one config doesn't crash a
    # scorer that doesn't accept it.
    adp = RewardAdapter(numeric_match, scorer_kwargs={"rel_tolerance": 0.5})
    r = adp.score(Rollout(prediction="105", expected="100"))
    assert r.success is True  # within the loosened 50% tolerance
    # The same kwarg passed to a scorer that doesn't take it is dropped, not raised.
    adp2 = RewardAdapter(contains, scorer_kwargs={"rel_tolerance": 0.5})
    assert adp2.score(Rollout(prediction="yes it is", expected="yes")).success is True


def test_refusal_flagged_in_auxiliary():
    adp = RewardAdapter(mcq_letter)
    r = adp.score(Rollout(prediction="I cannot determine the answer", expected="B"))
    assert r.failure_class is FailureLabel.DISCARD
    assert r.auxiliary["refusal"] is True


def test_verifier_crash_is_caught_not_raised():
    # One bad rollout must not sink the group — a raising verifier → CRASH label.
    def boom(pred, exp):
        raise RuntimeError("scorer exploded")

    adp = RewardAdapter(boom)
    r = adp.score(Rollout(prediction="x", expected="y"))
    assert r.success is False
    assert r.failure_class is FailureLabel.CRASH
    assert "scorer exploded" in r.auxiliary["error"]
    assert r.is_informational  # CRASH still carries signal


def test_score_accepts_mapping_rollout():
    # Duck-typed: a plain dict works as a rollout (RV-2 store-agnostic).
    adp = RewardAdapter(mcq_letter)
    r = adp.score({"prediction": "B", "expected": "B"})
    assert r.success is True


def test_missing_prediction_raises_reward_error():
    adp = RewardAdapter(mcq_letter)
    with pytest.raises(RewardError):
        adp.score({"expected": "B"})


def test_non_callable_verifier_rejected():
    with pytest.raises(RewardError):
        RewardAdapter("not-a-function")  # type: ignore[arg-type]


def test_judge_backed_scorer_uses_injected_judge():
    # patent_claim_validity / office_action_argument take a `judge` kwarg; the
    # adapter forwards it from scorer_kwargs. A fake judge keeps this offline.
    from fieldkit.eval import patent_claim_validity

    class FakeJudge:
        def grade(self, *, prediction, reference=None, context=None):
            from fieldkit.eval import JudgeResult

            return JudgeResult(score=1.0, rationale="ok", raw="{}")

    adp = RewardAdapter(patent_claim_validity, scorer_kwargs={"judge": FakeJudge()})
    r = adp.score(Rollout(prediction="A claim", expected="ref"))
    assert r.success is True and r.scalar == 1.0


# ---------------------------------------------------------------------------
# group_advantage (RV-2 — the value-network-free baseline)
# ---------------------------------------------------------------------------


def _rewards(scalars):
    return [
        Reward(success=s >= 1.0, failure_class=FailureLabel.KEEP, auxiliary={"score": s})
        for s in scalars
    ]


def test_group_advantage_standardizes_within_group():
    adv = group_advantage(_rewards([1.0, 0.0, 1.0, 0.0]))
    # Mean .5, symmetric → +/- equal magnitude, mean-zero.
    assert adv[0] == pytest.approx(-adv[1])
    assert sum(adv) == pytest.approx(0.0)


def test_group_advantage_degenerate_group_is_zero():
    # All-equal rewards → no spread → no gradient (anti-mode-collapse guard).
    assert group_advantage(_rewards([0.7, 0.7, 0.7])) == [0.0, 0.0, 0.0]
    assert group_advantage(_rewards([1.0])) == [0.0]
    assert group_advantage([]) == []


def test_group_advantage_centered_without_std():
    adv = group_advantage(_rewards([1.0, 0.0]), normalize_std=False)
    assert adv == pytest.approx([0.5, -0.5])


def test_reward_to_dict_roundtrips_label():
    r = _rewards([0.75])[0]
    d = r.to_dict()
    assert d["failure_class"] == "keep"
    assert d["scalar"] == pytest.approx(0.75)
