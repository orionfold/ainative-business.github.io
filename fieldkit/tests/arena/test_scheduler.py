# Copyright 2026 Manav Sehgal
# SPDX-License-Identifier: Apache-2.0
"""`fieldkit.arena.scheduler` — the M11 cron glue (§15).

Covers the autonomy layer over the built drain:
- `DrainLock` — acquire / stale-pid steal / live-holder contention (R24).
- `run_drain_cycle` — drains a seeded queue, runs the freshness sweep, stages
  the standup; skips cleanly when the lock is held.
- the budget governor in the drain loop — a *defer* leaves the job `queued`,
  records a `budget_defer` audit row, and stops the pass (AH-4).
- `build_standup` — the Ran / Regressed / Queued / Spend buckets (AH-3),
  aggregate-only (no `payload_json`).
"""

from __future__ import annotations

import json
import os

import pytest

from fieldkit.arena import jobs
from fieldkit.arena.jobs import JobKind, JobStatus
from fieldkit.arena.scheduler import (
    DrainLock,
    build_standup,
    run_drain_cycle,
)
from fieldkit.arena.store import ArenaStore
from fieldkit.budget import BudgetGovernor, MemoryEnvelope


@pytest.fixture
def store(tmp_path):
    s = ArenaStore(tmp_path / "arena.db")
    s.initialize()
    # eval_runs / eval_scores FK lanes(id); register the lanes a job targets.
    for lane in ("patent-q4km", "legal-q4km"):
        s.upsert_lane(
            {
                "id": lane,
                "kind": "LlamaServerLane",
                "model": lane,
                "port": 0,
                "base_url": "",
                "recommended": 0,
            }
        )
    yield s
    s.close()


def _fake_eval_runner(kind, payload):
    return {
        "scorer_kind": "exact_match",
        "mean_normalized": 0.8,
        "calls": [{"qid": "q1", "score": 1.0, "normalized": 1.0, "max_score": 1.0}],
    }


_NOW = lambda: "2026-06-02T00:00:00Z"  # noqa: E731 — deterministic stamp


# ---------------------------------------------------------------------------
# DrainLock
# ---------------------------------------------------------------------------


def test_lock_acquire_and_release(tmp_path):
    lk = DrainLock(str(tmp_path / "drain.lock"))
    assert lk.acquire() is True
    assert lk.acquired is True
    lk.release()
    assert lk.acquired is False
    assert not (tmp_path / "drain.lock").exists()


def test_lock_steals_stale_pid(tmp_path):
    path = tmp_path / "drain.lock"
    # A lock owned by a dead pid (PID 2**31-1 is never alive).
    path.write_text(json.dumps({"pid": 2147483646, "acquired_at": "x"}))
    lk = DrainLock(str(path))
    assert lk.acquire() is True  # stale → stolen


def test_lock_blocks_on_live_holder(tmp_path):
    path = tmp_path / "drain.lock"
    path.write_text(json.dumps({"pid": os.getpid(), "acquired_at": "x"}))
    lk = DrainLock(str(path))
    assert lk.acquire() is False  # this process IS alive → held
    assert lk.acquired is False


def test_lock_context_manager(tmp_path):
    path = str(tmp_path / "drain.lock")
    with DrainLock(path) as lk:
        assert lk.acquired is True
    assert not os.path.exists(path)


# ---------------------------------------------------------------------------
# run_drain_cycle
# ---------------------------------------------------------------------------


def _enqueue_eval(store, lane, bench):
    return jobs.enqueue_job(
        store, JobKind.EVAL_RERUN, {"lane_id": lane, "bench_id": bench}, now_fn=_NOW
    )


def test_cycle_drains_and_stages_standup(store, tmp_path):
    _enqueue_eval(store, "patent-q4km", "b1")
    _enqueue_eval(store, "legal-q4km", "b2")
    res = run_drain_cycle(
        store,
        runner=_fake_eval_runner,
        lock=DrainLock(str(tmp_path / "d.lock")),
        now_fn=_NOW,
    )
    assert res["skipped"] is False
    assert res["n_drained"] == 2
    assert res["sweep"] is not None  # freshness sweep ran (AH-6)
    standup = res["standup"]
    assert standup["counts"]["ran"] == 2
    assert standup["counts"]["queued"] == 0
    assert standup["staged_only"] is True


def test_cycle_skips_when_lock_held(store, tmp_path):
    lk_path = str(tmp_path / "d.lock")
    held = DrainLock(lk_path)
    held.acquire()
    try:
        res = run_drain_cycle(
            store, runner=_fake_eval_runner, lock=DrainLock(lk_path), now_fn=_NOW
        )
        assert res["skipped"] is True
        assert res["standup"] is None
    finally:
        held.release()


def test_cycle_freshness_can_be_disabled(store, tmp_path):
    res = run_drain_cycle(
        store,
        runner=_fake_eval_runner,
        freshness=False,
        lock=DrainLock(str(tmp_path / "d.lock")),
        now_fn=_NOW,
    )
    assert res["sweep"] is None


# ---------------------------------------------------------------------------
# Budget governor in the drain loop (AH-4)
# ---------------------------------------------------------------------------


def test_governor_defer_leaves_job_queued_and_audits(store, tmp_path):
    _enqueue_eval(store, "patent-q4km", "b1")
    # An envelope that rejects the lane → the governor defers it.
    gov = BudgetGovernor(
        ledger=None, envelope=MemoryEnvelope(lane_gb={"patent-q4km": 300.0})
    )
    res = run_drain_cycle(
        store,
        runner=_fake_eval_runner,
        governor=gov,
        freshness=False,
        lock=DrainLock(str(tmp_path / "d.lock")),
        now_fn=_NOW,
    )
    assert res["n_drained"] == 0
    # The job is back on the queue (not skipped/failed) for the next tick.
    queued = store.list_jobs(status=JobStatus.QUEUED)
    assert len(queued) == 1
    # A budget_defer audit row was recorded.
    rows = list(
        store.connect().execute(
            "SELECT source, detail_json FROM job_triggers WHERE source LIKE 'budget_%'"
        )
    )
    assert len(rows) == 1
    assert rows[0]["source"] == "budget_defer"
    assert "oom_envelope" in rows[0]["detail_json"]


def test_governor_allow_drains_normally(store, tmp_path):
    _enqueue_eval(store, "patent-q4km", "b1")
    gov = BudgetGovernor(ledger=None)  # default envelope fits, no usage cap hit
    res = run_drain_cycle(
        store,
        runner=_fake_eval_runner,
        governor=gov,
        freshness=False,
        lock=DrainLock(str(tmp_path / "d.lock")),
        now_fn=_NOW,
    )
    assert res["n_drained"] == 1
    assert store.list_jobs(status=JobStatus.QUEUED) == []


# ---------------------------------------------------------------------------
# build_standup — aggregate-only (no payload leak)
# ---------------------------------------------------------------------------


def test_standup_omits_payload_json(store):
    # A queued job whose payload carries an operator "secret" must not surface.
    jobs.enqueue_job(
        store,
        JobKind.EVAL_RERUN,
        {"lane_id": "patent-q4km", "bench_id": "b1", "note": "operator-secret"},
        now_fn=_NOW,
    )
    standup = build_standup(store, now_fn=_NOW)
    blob = json.dumps(standup)
    assert "operator-secret" not in blob
    assert "payload_json" not in blob
    assert standup["counts"]["queued"] == 1


def test_standup_spend_dash_without_governor(store):
    # No governor → SpendDigest.from_store; a fresh store HAS the M9 columns,
    # so the cost plane is present but spend is 0.
    standup = build_standup(store, now_fn=_NOW)
    assert standup["spend"]["has_cost_plane"] is True
    assert standup["spend"]["total_usd"] == pytest.approx(0.0)
