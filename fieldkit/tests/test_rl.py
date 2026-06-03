# Copyright 2026 Manav Sehgal
# SPDX-License-Identifier: Apache-2.0
"""`fieldkit.rl` — the closed-loop RLVR driver (Phase 3, the engine).

Covers the orchestration with **injected GPU seams** (no torch / no vLLM), the
way the production loop will run with real ones:
- **RV-10** the ≥100-row corpus floor + the frozen held-out split before step 0;
- **RV-4** the held-out gate + **held-out-ONLY checkpoint selection** — the test
  makes the pool rise monotonically while held-out peaks early, and asserts the
  loop selects the held-out-best step, *not* the pool-best/last (the 81.8 pp
  `t2po` inversion defense);
- the `RLLoop` writes a `Trial` per step into `fieldkit.lineage` and returns the
  `rl_run` `LineageSnapshot` (RV-7);
- `GRPOConfig` validation + the `gpu_seams` not-yet-vendored guard (RV-1/RV-5).
"""

from __future__ import annotations

import pytest

from fieldkit.eval import VerticalQA, mcq_letter
from fieldkit.lineage import FailureLabel, LineageSnapshot, LineageStore
from fieldkit.reward import RewardAdapter, Rollout
from fieldkit.rl import GRPOConfig, RLLoop, RLLoopError, gpu_seams


class _Bench:
    """A bench-shaped stub — `RLLoop` only reads `.questions`."""

    def __init__(self, n=120):
        self.questions = [
            VerticalQA(qid=f"q{i}", question=f"Q{i}?", expected="B") for i in range(n)
        ]


def _seams(heldout_curve, pool_climbs=True):
    """Build (sampler, trainer, heldout_eval) fakes.

    `heldout_curve` maps step → held-out score. `sampler` emits more correct
    rollouts as steps progress (pool reward rises), so the test can prove
    selection ignores the pool.
    """
    state = {"step": 0}

    def sampler(tasks, k):
        s = state["step"]
        state["step"] += 1
        n_correct = min(k, s + 1) if pool_climbs else 1
        out = []
        for t in tasks:
            preds = ["B"] * n_correct + ["A"] * (k - n_correct)
            out.append([Rollout(prediction=p, expected="B", task_id=t.qid) for p in preds])
        return out

    def trainer(rollouts, advantages, step):
        assert len(rollouts) == len(advantages)
        return {"loss": 0.5 / (step + 1), "kl": 0.01, "train_s": 22.0, "checkpoint": f"/ckpt/{step}"}

    def heldout_eval(step, tasks):
        return heldout_curve[step]

    return sampler, trainer, heldout_eval


# ---------------------------------------------------------------------------
# RV-4 — held-out-only checkpoint selection
# ---------------------------------------------------------------------------


def test_selects_heldout_best_not_pool_best():
    cfg = GRPOConfig(
        base="patent-Q4", max_steps=4, heldout_every=1, corpus_min=100,
        group_k=4, tasks_per_step=8, vllm_pin="vllm==0.10.2", seed=7,
    )
    # Pool climbs 0.25→1.0; held-out PEAKS at step 1 then collapses (inversion).
    sampler, trainer, heldout_eval = _seams({0: 0.30, 1: 0.90, 2: 0.50, 3: 0.40})
    loop = RLLoop(
        cfg, RewardAdapter(mcq_letter), _Bench(),
        sampler=sampler, trainer=trainer, heldout_eval=heldout_eval,
    )
    snap = loop.run()

    assert isinstance(snap, LineageSnapshot)
    # Pool is monotincreasing; held-out peaks at 1. Selection MUST pick 1.
    assert loop.pool_scores[3] > loop.pool_scores[0]
    assert loop.selected_step == 1
    assert loop.selected_heldout_score == pytest.approx(0.90)
    assert loop.summary()["selected_on"] == "heldout"


def test_lineage_trials_written_with_explicit_store(tmp_path):
    store = LineageStore(tmp_path / "lin", lower_is_better=False)
    cfg = GRPOConfig(base="x", max_steps=3, heldout_every=1, corpus_min=100)
    sampler, trainer, heldout_eval = _seams({0: 0.5, 1: 0.6, 2: 0.55})
    loop = RLLoop(
        cfg, RewardAdapter(mcq_letter), _Bench(),
        sampler=sampler, trainer=trainer, heldout_eval=heldout_eval,
        lineage_store=store,
    )
    loop.run()
    trials = store.all_trials()
    statuses = [t.status for t in trials]
    assert FailureLabel.BASELINE in statuses  # the seed row (RV-7)
    # one heldout-gate trial per held-out eval (every step here)
    assert sum(1 for t in trials if t.specialist == "heldout-gate") == 3
    assert any(t.specialist == "baseline" for t in trials)


# ---------------------------------------------------------------------------
# RV-10 — corpus floor + frozen split
# ---------------------------------------------------------------------------


def test_corpus_below_floor_refused():
    cfg = GRPOConfig(base="x", corpus_min=100)
    sampler, trainer, heldout_eval = _seams({0: 0.5})
    with pytest.raises(RLLoopError, match="corpus_min"):
        RLLoop(
            cfg, RewardAdapter(mcq_letter), _Bench(n=42),
            sampler=sampler, trainer=trainer, heldout_eval=heldout_eval,
        ).run()


def test_heldout_patience_stops_early():
    cfg = GRPOConfig(
        base="x", max_steps=10, heldout_every=1, corpus_min=100, heldout_patience=2,
    )
    # held-out improves once then plateaus → patience trips, run stops early.
    curve = {0: 0.5, 1: 0.5, 2: 0.5, 3: 0.5, 4: 0.5}
    sampler, trainer, heldout_eval = _seams(curve)
    loop = RLLoop(
        cfg, RewardAdapter(mcq_letter), _Bench(),
        sampler=sampler, trainer=trainer, heldout_eval=heldout_eval,
    )
    loop.run()
    assert len(loop.pool_scores) < 10  # stopped before max_steps


# ---------------------------------------------------------------------------
# GRPOConfig validation + gpu_seams guard
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "kw",
    [
        {"heldout_every": 0},
        {"group_k": 0},
        {"tasks_per_step": 0},
        {"max_steps": 0},
        {"heldout_frac": 1.5},
        {"heldout_patience": 0},
    ],
)
def test_invalid_config_rejected(kw):
    with pytest.raises(RLLoopError):
        GRPOConfig(base="x", **kw)


def test_missing_seam_raises():
    cfg = GRPOConfig(base="x", corpus_min=100)
    loop = RLLoop(cfg, RewardAdapter(mcq_letter), _Bench())  # no seams injected
    with pytest.raises(RLLoopError, match="sampler"):
        loop.run()


def test_gpu_seams_not_yet_vendored():
    # v1 ships the orchestration; the real GPU backend is a documented fast-follow.
    with pytest.raises(RLLoopError, match="vLLM|fieldkit\\[rl\\]"):
        gpu_seams(GRPOConfig(base="x"))
