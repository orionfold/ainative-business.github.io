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

import json

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


# ---------------------------------------------------------------------------
# resolve_bench — the bench registry (Fix #1: eval_rerun's bench_path)
# ---------------------------------------------------------------------------


def _write_bench(bench_dir, bench_id, *, meta=None, n=2):
    bench_dir.mkdir(parents=True, exist_ok=True)
    rows = [
        {"prompt": f"q{i}", "answer": str(i), "qid": f"q{i}"} for i in range(n)
    ]
    (bench_dir / f"{bench_id}.jsonl").write_text(
        "\n".join(json.dumps(r) for r in rows) + "\n"
    )
    if meta is not None:
        (bench_dir / f"{bench_id}.meta.json").write_text(json.dumps(meta))


def test_resolve_bench_finds_registered_jsonl(tmp_path, monkeypatch):
    bench_dir = tmp_path / "benches"
    _write_bench(bench_dir, "patent-strategist")
    monkeypatch.setenv("ARENA_BENCH_DIR", str(bench_dir))
    reg = jobs.resolve_bench("patent-strategist")
    assert reg is not None
    assert reg["bench_path"].endswith("patent-strategist.jsonl")
    assert reg["scorer"] == "exact_match"  # default when no meta sidecar
    assert reg["max_tokens"] == 512


def test_resolve_bench_meta_sidecar_overrides(tmp_path, monkeypatch):
    bench_dir = tmp_path / "benches"
    _write_bench(
        bench_dir, "finance", meta={"scorer": "numeric_match", "max_tokens": 256, "limit": 10}
    )
    monkeypatch.setenv("ARENA_BENCH_DIR", str(bench_dir))
    reg = jobs.resolve_bench("finance")
    assert reg["scorer"] == "numeric_match"
    assert reg["max_tokens"] == 256
    assert reg["limit"] == 10


def test_resolve_bench_unregistered_returns_none(tmp_path, monkeypatch):
    monkeypatch.setenv("ARENA_BENCH_DIR", str(tmp_path / "benches"))
    assert jobs.resolve_bench("nope") is None


def test_default_runner_raises_bench_not_registered(tmp_path, monkeypatch):
    # The exact gap the side-by-side walkthrough hit: eval_rerun with only a
    # bench_id and no registered gold set now fails LOUD + actionable, naming
    # the path it searched — not the opaque "needs bench_path" deep in the tool.
    monkeypatch.setenv("ARENA_BENCH_DIR", str(tmp_path / "benches"))
    with pytest.raises(jobs.BenchNotRegistered) as exc:
        jobs.default_runner(
            JobKind.EVAL_RERUN, {"lane_id": "patent-q4km", "bench_id": "patent-strategist"}
        )
    assert "patent-strategist.jsonl" in str(exc.value)


def test_default_runner_resolves_bench_path(tmp_path, monkeypatch):
    # With a registered bench, default_runner reaches run_vertical_eval with a
    # populated bench_path — it runs to completion (the closed-port lane just
    # yields zero successful calls), echoing back the resolved path. The point:
    # no BenchNotRegistered, the gap the walkthrough hit is closed.
    bench_dir = tmp_path / "benches"
    _write_bench(bench_dir, "patent-strategist")
    monkeypatch.setenv("ARENA_BENCH_DIR", str(bench_dir))
    monkeypatch.setenv("ARENA_EVAL_BASE_URL", "http://127.0.0.1:9")  # closed port
    result = jobs.default_runner(
        JobKind.EVAL_RERUN, {"lane_id": "patent-q4km", "bench_id": "patent-strategist"}
    )
    assert result["bench"] == "patent-strategist"
    assert result["bench_path"].endswith("patent-strategist.jsonl")


# ---------------------------------------------------------------------------
# check_and_enqueue_regressions — the wired producer (Fix #2)
# ---------------------------------------------------------------------------


def _seed_score(store, bench_id, lane_id, normalized, *, qid, scored_at):
    store.append_eval_score(
        {
            "bench_id": bench_id,
            "qid": qid,
            "lane_id": lane_id,
            "scorer_kind": "exact_match",
            "score": normalized,
            "max_score": 1.0,
            "normalized": normalized,
            "reference": None,
            "rationale": None,
            "judge_backend": None,
            "cross_vertical": 0,
            "source": "test",
            "source_id": qid,
            "scored_at": scored_at,
        }
    )


def test_first_scan_only_sets_baseline(store):
    _seed_score(store, "patent-bench", "patent-q4km", 0.9, qid="q1", scored_at="2026-06-01T00:00:00Z")
    out = jobs.check_and_enqueue_regressions(store, now_fn=lambda: _NOW)
    assert out["had_baseline"] is False
    assert out["enqueued"] == []  # nothing to diff against yet
    assert out["baselined"] == 1
    assert len(store.leaderboard_baseline()) == 1


def test_scan_enqueues_on_real_drop(store):
    # baseline at 0.9, then a flood of 0.0 scores drags the mean below tau.
    _seed_score(store, "patent-bench", "patent-q4km", 0.9, qid="q1", scored_at="2026-06-01T00:00:00Z")
    jobs.check_and_enqueue_regressions(store, now_fn=lambda: _NOW)  # sets baseline @0.9
    for i in range(9):
        _seed_score(store, "patent-bench", "patent-q4km", 0.0, qid=f"d{i}", scored_at="2026-06-02T00:00:00Z")
    out = jobs.check_and_enqueue_regressions(store, now_fn=lambda: _NOW)
    assert out["had_baseline"] is True
    assert len(out["enqueued"]) == 1  # the over-tau drop fired one confirming re-eval
    job = store.get_job(out["enqueued"][0])
    assert job["kind"] == JobKind.EVAL_RERUN
    assert job["trigger"] == "leaderboard_regression"
    # baseline was re-set to the new (lower) snapshot
    base = store.leaderboard_baseline()
    assert base and base[0]["mean_normalized"] < 0.5


def test_scan_no_regression_when_stable(store):
    _seed_score(store, "b", "patent-q4km", 0.8, qid="q1", scored_at="2026-06-01T00:00:00Z")
    jobs.check_and_enqueue_regressions(store, now_fn=lambda: _NOW)
    _seed_score(store, "b", "patent-q4km", 0.82, qid="q2", scored_at="2026-06-02T00:00:00Z")
    out = jobs.check_and_enqueue_regressions(store, now_fn=lambda: _NOW)
    assert out["enqueued"] == []
