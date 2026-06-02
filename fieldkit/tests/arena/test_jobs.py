# Copyright 2026 Manav Sehgal
# SPDX-License-Identifier: Apache-2.0
"""M8 control-plane tests — the dispatcher, the dedup gate, and the
leaderboard-regression trigger producer (`_SPECS/spark-arena-v1.md` §12).

Release-gate coverage (§11, ``fieldkit v0.16.0`` row):
- ``detect_leaderboard_regression`` fires on a seeded regression;
- an ``eval_rerun`` dispatches end-to-end through an injected runner (the
  harness surface in production) and writes back an ``eval_runs`` row +
  ``eval_scores`` rows the accuracy leaderboard picks up;
- the dedup unique-index coalesces duplicate in-flight triggers (R15);
- a named-but-not-built stub kind is rejected, not silently run.

No GPU / no `mcp` SDK needed — the runner is injected.
"""

from __future__ import annotations

import pytest

from fieldkit.arena import jobs
from fieldkit.arena.jobs import (
    JobDispatchError,
    JobKind,
    JobStatus,
    UnknownJobKind,
    detect_leaderboard_regression,
)
from fieldkit.arena.store import ArenaStore


@pytest.fixture
def store(tmp_path):
    s = ArenaStore(tmp_path / "arena.db")
    s.initialize()
    # eval_runs FKs lanes(id); register the lane an eval_rerun targets.
    s.upsert_lane(
        {
            "id": "patent-q4km",
            "kind": "LlamaServerLane",
            "model": "patent-strategist-Q4_K_M",
            "port": 0,
            "base_url": "",
            "recommended": 0,
        }
    )
    yield s
    s.close()


_NOW = "2026-06-02T00:00:00Z"


def _fake_eval_runner(mean=0.7):
    def _run(kind, payload):
        return {
            "scorer_kind": "exact_match",
            "mean_normalized": mean,
            "calls": [
                {"qid": "q1", "score": 1.0, "normalized": 1.0, "max_score": 1.0},
                {"qid": "q2", "score": 0.0, "normalized": 0.0, "max_score": 1.0},
            ],
        }

    return _run


# ---------------------------------------------------------------------------
# Regression detector — the release-gate core
# ---------------------------------------------------------------------------


def test_regression_fires_over_tau():
    prev = [{"bench_id": "patent-bench", "lane_id": "patent-q4km", "mean_normalized": 0.81}]
    curr = [{"bench_id": "patent-bench", "lane_id": "patent-q4km", "mean_normalized": 0.74}]
    regs = detect_leaderboard_regression(prev, curr, tau=0.05)
    assert len(regs) == 1
    r = regs[0]
    assert r["bench_id"] == "patent-bench" and r["lane_id"] == "patent-q4km"
    assert r["prev_score"] == 0.81 and r["new_score"] == 0.74
    assert r["delta"] == pytest.approx(-0.07)


def test_small_drop_under_tau_is_noise():
    prev = [{"bench_id": "b", "lane_id": "l", "mean_normalized": 0.81}]
    curr = [{"bench_id": "b", "lane_id": "l", "mean_normalized": 0.79}]  # -0.02
    assert detect_leaderboard_regression(prev, curr, tau=0.05) == []


def test_improvement_is_not_a_regression():
    prev = [{"bench_id": "b", "lane_id": "l", "mean_normalized": 0.70}]
    curr = [{"bench_id": "b", "lane_id": "l", "mean_normalized": 0.90}]
    assert detect_leaderboard_regression(prev, curr) == []


def test_newly_seen_lane_cannot_regress():
    prev: list = []
    curr = [{"bench_id": "b", "lane_id": "l", "mean_normalized": 0.10}]
    assert detect_leaderboard_regression(prev, curr) == []


def test_regressions_sorted_worst_first():
    prev = [
        {"bench_id": "b1", "lane_id": "l", "mean_normalized": 0.9},
        {"bench_id": "b2", "lane_id": "l", "mean_normalized": 0.9},
    ]
    curr = [
        {"bench_id": "b1", "lane_id": "l", "mean_normalized": 0.7},  # -0.2
        {"bench_id": "b2", "lane_id": "l", "mean_normalized": 0.5},  # -0.4
    ]
    regs = detect_leaderboard_regression(prev, curr)
    assert [r["bench_id"] for r in regs] == ["b2", "b1"]


# ---------------------------------------------------------------------------
# Enqueue + dedup gate (R15)
# ---------------------------------------------------------------------------


def test_enqueue_coalesces_duplicate_in_flight(store):
    first = jobs.enqueue_job(store, JobKind.EVAL_RERUN, {"lane_id": "patent-q4km", "bench_id": "b"})
    dup = jobs.enqueue_job(store, JobKind.EVAL_RERUN, {"lane_id": "patent-q4km", "bench_id": "b"})
    assert first is not None
    assert dup is None  # coalesced — one in-flight job already owns the key
    assert len(store.list_jobs()) == 1


def test_enqueue_manual_oneoff_never_coalesces(store):
    # No lane/bench → dedup_key None → always distinct.
    a = jobs.enqueue_job(store, JobKind.MEASURE_VARIANTS, {"manifest_slug": "x"})
    b = jobs.enqueue_job(store, JobKind.MEASURE_VARIANTS, {"manifest_slug": "x"})
    assert a and b and a != b


def test_unknown_kind_rejected_on_enqueue(store):
    with pytest.raises(UnknownJobKind):
        jobs.enqueue_job(store, "teleport", {"lane_id": "l"})


def test_records_trigger_audit_row(store):
    jid = jobs.enqueue_job(
        store,
        JobKind.EVAL_RERUN,
        {"lane_id": "patent-q4km", "bench_id": "b"},
        trigger="leaderboard_regression",
        trigger_detail={"bench_id": "b", "delta": -0.2},
    )
    rows = list(store.connect().execute("SELECT * FROM job_triggers WHERE job_id=?", [jid]))
    assert len(rows) == 1 and rows[0]["source"] == "leaderboard_regression"


# ---------------------------------------------------------------------------
# Dispatch — through the (injected) harness surface
# ---------------------------------------------------------------------------


def test_eval_rerun_dispatch_end_to_end(store):
    jobs.enqueue_job(store, JobKind.EVAL_RERUN, {"lane_id": "patent-q4km", "bench_id": "patent-bench"})
    claimed = store.claim_next_job(dispatched_at=_NOW)
    assert claimed["status"] == JobStatus.DISPATCHED
    row = jobs.dispatch_job(
        store,
        {k: claimed[k] for k in claimed.keys()},
        runner=_fake_eval_runner(mean=0.7),
        now_fn=lambda: _NOW,
    )
    assert row["status"] == JobStatus.DONE
    # eval_runs activated (status row) + eval_scores written (results path).
    assert store.count("eval_runs") == 1
    assert store.count("eval_scores") == 2
    # The accuracy leaderboard picks the re-eval up: (1.0 + 0.0)/2 = 0.5.
    lb = store.eval_leaderboard()
    assert lb and lb[0]["lane_id"] == "patent-q4km"
    assert lb[0]["mean_normalized"] == pytest.approx(0.5)


def test_non_dispatchable_stub_fails_loudly(store):
    # A named stub can be enqueued (forward marker) but never dispatched in M8.
    jid = jobs.enqueue_job(store, JobKind.RL_RUN, {"lane_id": "patent-q4km", "bench_id": "b"})
    claimed = store.claim_next_job(dispatched_at=_NOW)
    with pytest.raises(UnknownJobKind):
        jobs.dispatch_job(store, {k: claimed[k] for k in claimed.keys()}, now_fn=lambda: _NOW)
    assert store.get_job(jid)["status"] == JobStatus.FAILED


def test_runner_failure_marks_job_failed(store):
    jobs.enqueue_job(store, JobKind.EVAL_RERUN, {"lane_id": "patent-q4km", "bench_id": "b"})
    claimed = store.claim_next_job(dispatched_at=_NOW)

    def boom(kind, payload):
        raise RuntimeError("llama-server unreachable")

    with pytest.raises(JobDispatchError):
        jobs.dispatch_job(store, {k: claimed[k] for k in claimed.keys()}, runner=boom, now_fn=lambda: _NOW)
    failed = store.list_jobs(status=JobStatus.FAILED)
    assert len(failed) == 1 and "unreachable" in failed[0]["error"]


def test_drain_processes_queue_sequentially(store):
    jobs.enqueue_job(store, JobKind.EVAL_RERUN, {"lane_id": "patent-q4km", "bench_id": "b1"})
    jobs.enqueue_job(store, JobKind.EVAL_RERUN, {"lane_id": "patent-q4km", "bench_id": "b2"})
    done = jobs.drain_jobs(store, runner=_fake_eval_runner(), now_fn=lambda: _NOW)
    assert len(done) == 2
    assert all(d["status"] == JobStatus.DONE for d in done)
    assert store.claim_next_job(dispatched_at=_NOW) is None  # queue drained


def test_priority_orders_drain(store):
    jobs.enqueue_job(store, JobKind.EVAL_RERUN, {"lane_id": "patent-q4km", "bench_id": "low"}, priority=0)
    jobs.enqueue_job(store, JobKind.EVAL_RERUN, {"lane_id": "patent-q4km", "bench_id": "high"}, priority=5)
    first = store.claim_next_job(dispatched_at=_NOW)
    import json as _json

    assert _json.loads(first["payload_json"])["bench_id"] == "high"


def test_cancel_only_before_running(store):
    jid = jobs.enqueue_job(store, JobKind.EVAL_RERUN, {"lane_id": "patent-q4km", "bench_id": "b"})
    assert store.cancel_job(jid) is True
    assert store.get_job(jid)["status"] == JobStatus.SKIPPED
    # already-skipped won't flip again
    assert store.cancel_job(jid) is False


# ---------------------------------------------------------------------------
# enqueue_regressions — the wired producer
# ---------------------------------------------------------------------------


def test_enqueue_regressions_fires_eval_rerun(store):
    prev = [{"bench_id": "patent-bench", "lane_id": "patent-q4km", "mean_normalized": 0.85}]
    curr = [{"bench_id": "patent-bench", "lane_id": "patent-q4km", "mean_normalized": 0.70}]
    enq = jobs.enqueue_regressions(store, prev, curr, now_fn=lambda: _NOW)
    assert len(enq) == 1
    job = store.get_job(enq[0])
    assert job["kind"] == JobKind.EVAL_RERUN
    assert job["trigger"] == "leaderboard_regression"
    assert job["priority"] == 1  # ahead of manual re-evals


def test_enqueue_regressions_dedups_storm(store):
    prev = [{"bench_id": "b", "lane_id": "patent-q4km", "mean_normalized": 0.85}]
    curr = [{"bench_id": "b", "lane_id": "patent-q4km", "mean_normalized": 0.70}]
    enq1 = jobs.enqueue_regressions(store, prev, curr, now_fn=lambda: _NOW)
    enq2 = jobs.enqueue_regressions(store, prev, curr, now_fn=lambda: _NOW)  # same in-flight
    assert len(enq1) == 1 and len(enq2) == 0  # second is coalesced (R15)
