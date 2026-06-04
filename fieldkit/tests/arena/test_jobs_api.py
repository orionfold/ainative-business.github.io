# Copyright 2026 Manav Sehgal
# SPDX-License-Identifier: Apache-2.0
"""Tests for the M8 ``/api/jobs`` control-plane endpoints + SSE feed.

Covers the cockpit's only window onto the queue: list / create (with the R15
dedup coalesce) / get-one (+ trigger trail) / cancel / the SSE board snapshot,
and the R14 graceful-degradation contract — a ``dispatch=True`` enqueue on a
box with no served lane lands the job ``failed`` (visible card) rather than
500-ing the request. No GPU: the background drain hits the missing lane and
records the failure.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

fastapi = pytest.importorskip("fastapi")
httpx = pytest.importorskip("httpx")

from fastapi.testclient import TestClient  # noqa: E402

from fieldkit.arena.server import create_app, jobs_event_stream  # noqa: E402


@pytest.fixture
def client(tmp_path):
    db = tmp_path / "arena.db"
    app = create_app(db=db)
    return TestClient(app), str(db)


def test_list_empty_on_fresh_box(client):
    c, _ = client
    r = c.get("/api/jobs")
    assert r.status_code == 200 and r.json() == {"jobs": []}


def test_create_and_get(client):
    c, _ = client
    r = c.post(
        "/api/jobs",
        json={"kind": "eval_rerun", "payload": {"lane_id": "L", "bench_id": "B"}, "dispatch": False},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] and body["coalesced"] is False
    jid = body["job_id"]

    one = c.get(f"/api/jobs/{jid}").json()
    assert one["status"] == "queued"
    assert one["payload"] == {"lane_id": "L", "bench_id": "B"}
    assert one["triggers"] == []


def test_create_coalesces_inflight_duplicate(client):
    c, _ = client
    payload = {"kind": "eval_rerun", "payload": {"lane_id": "L", "bench_id": "B"}, "dispatch": False}
    first = c.post("/api/jobs", json=payload).json()
    dup = c.post("/api/jobs", json=payload).json()
    assert first["coalesced"] is False and first["job_id"]
    assert dup["coalesced"] is True and dup["job_id"] is None
    assert len(c.get("/api/jobs").json()["jobs"]) == 1


def test_create_rejects_non_allowlisted_kind(client):
    c, _ = client
    # The enqueue allowlist is pattern-validated; `requant` stays out of it
    # (still a non-enqueueable kind) → a 422.
    r = c.post("/api/jobs", json={"kind": "requant", "payload": {}, "dispatch": False})
    assert r.status_code == 422


def test_create_rl_run_is_async_only(client):
    c, _ = client
    # rl-lane-autonomy LA-4 / RV-6: rl_run IS enqueue-allowed, but the route
    # forces async-only — it never drains the 8.5 h loop in a request, even with
    # dispatch=True. The response advertises async_only + the autonomy note.
    r = c.post(
        "/api/jobs",
        json={"kind": "rl_run", "payload": {"base": "Q", "bench_path": "/x"}, "dispatch": True},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["coalesced"] is False and body["job_id"]
    assert body["async_only"] is True
    assert "autonomy" in (body["note"] or "")
    # It is queued, not dispatched — the cron + arbiter own it.
    jobs = c.get("/api/jobs").json()["jobs"]
    assert any(j["id"] == body["job_id"] and j["status"] == "queued" for j in jobs)


def test_status_filter(client):
    c, _ = client
    jid = c.post(
        "/api/jobs",
        json={"kind": "measure_variants", "payload": {"manifest_slug": "x"}, "dispatch": False},
    ).json()["job_id"]
    c.delete(f"/api/jobs/{jid}")  # → skipped
    assert len(c.get("/api/jobs", params={"status": "queued"}).json()["jobs"]) == 0
    assert len(c.get("/api/jobs", params={"status": "skipped"}).json()["jobs"]) == 1


def test_cancel_then_404_and_409_paths(client):
    c, _ = client
    jid = c.post(
        "/api/jobs",
        json={"kind": "eval_rerun", "payload": {"lane_id": "L", "bench_id": "B"}, "dispatch": False},
    ).json()["job_id"]
    assert c.delete(f"/api/jobs/{jid}").status_code == 200
    # already skipped → 409 (past cancellation)
    assert c.delete(f"/api/jobs/{jid}").status_code == 409
    # never existed → 404
    assert c.delete("/api/jobs/nope").status_code == 404
    assert c.get("/api/jobs/nope").status_code == 404


def test_dispatch_true_degrades_to_failed_without_a_lane(client):
    """R14 — no served lane on this box: the background drain stamps the job
    ``failed`` (the run_vertical_eval tool rejects the missing bench), and the
    POST itself still returns 200. A misconfigured box shows a failed card,
    never a 500."""
    c, _ = client
    jid = c.post(
        "/api/jobs",
        json={"kind": "eval_rerun", "payload": {"lane_id": "L", "bench_id": "B"}, "dispatch": True},
    ).json()["job_id"]
    # TestClient runs BackgroundTasks synchronously after the response.
    assert c.get(f"/api/jobs/{jid}").json()["status"] == "failed"


def test_sse_emits_board_snapshot(client):
    c, db = client
    c.post(
        "/api/jobs",
        json={"kind": "eval_rerun", "payload": {"lane_id": "L", "bench_id": "B"}, "dispatch": False},
    )

    class _Req:
        def __init__(self, ticks):
            self.ticks = ticks
            self.i = 0

        async def is_disconnected(self):
            self.i += 1
            return self.i > self.ticks

    async def _drive():
        gen = jobs_event_stream(db, _Req(1))
        ev = await gen.__anext__()
        await gen.aclose()
        return ev

    ev = asyncio.run(_drive())
    assert ev["event"] == "jobs"
    assert len(json.loads(ev["data"])["jobs"]) == 1


def _seed_score(db, normalized, *, qid, scored_at):
    from fieldkit.arena.store import ArenaStore

    s = ArenaStore(db)
    s.initialize()
    s.append_eval_score(
        {
            "bench_id": "patent-bench",
            "qid": qid,
            "lane_id": "patent-q4km",
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
    s.close()


def test_check_regressions_first_scan_sets_baseline(client):
    c, db = client
    _seed_score(db, 0.9, qid="q1", scored_at="2026-06-01T00:00:00Z")
    r = c.post("/api/jobs/check-regressions")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] and body["had_baseline"] is False
    assert body["enqueued"] == [] and body["checked"] == 1


def test_check_regressions_enqueues_on_drop(client):
    c, db = client
    _seed_score(db, 0.9, qid="q1", scored_at="2026-06-01T00:00:00Z")
    c.post("/api/jobs/check-regressions")  # sets baseline @0.9
    for i in range(9):
        _seed_score(db, 0.0, qid=f"d{i}", scored_at="2026-06-02T00:00:00Z")
    body = c.post("/api/jobs/check-regressions", params={"dispatch": False}).json()
    assert body["had_baseline"] is True
    assert len(body["enqueued"]) == 1
    # the confirming re-eval is on the board, trigger-tagged for the UI banner
    jobs = c.get("/api/jobs").json()["jobs"]
    reg = [j for j in jobs if j["trigger"] == "leaderboard_regression"]
    assert len(reg) == 1 and reg[0]["kind"] == "eval_rerun"
