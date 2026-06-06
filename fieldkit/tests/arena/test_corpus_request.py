# Copyright 2026 Manav Sehgal
# SPDX-License-Identifier: Apache-2.0
"""AE-27 (arena-enhancements-v2 cut 3) — the corpus-gen request handshake +
producer liveness (AF-22 / OBS-3).

The contract under test: Arena writes an INTENT file (`corpus-request.json`,
atomic, beside the heartbeats) the in-CC-session synth skill polls + fulfils —
Arena never imports skill code (AE-R3). Fulfilment is an OBSERVATION (a
heartbeat stamped after the request), never an assertion; producer liveness is
heartbeat-mtime freshness, so "no synth" and "synth running but not stamping"
(the OBS-3 blind spot) are distinguishable.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

import pytest

fastapi = pytest.importorskip("fastapi")

from fastapi.testclient import TestClient  # noqa: E402

from fieldkit.arena.server import create_app  # noqa: E402


def _app(tmp_path: Path):
    return create_app(
        repo_root=tmp_path,
        db=str(tmp_path / "no-such.db"),
        telemetry_interval=2.0,
    )


def _corpus_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    d = tmp_path / "corpus-feed"
    d.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("FK_ARENA_CORPUS_DIR", str(d))
    return d


def _heartbeat(d: Path, *, status: str = "running", mtime: float | None = None) -> Path:
    p = d / "corpus-progress-test.json"
    p.write_text(json.dumps({
        "kind": "corpus_run", "run_label": "t", "vertical": "astrodynamics",
        "status": status, "written": 100, "target": 600, "batch_size": 50,
    }))
    if mtime is not None:
        os.utime(p, (mtime, mtime))
    return p


def test_post_writes_intent_and_get_roundtrips(tmp_path, monkeypatch):
    d = _corpus_dir(tmp_path, monkeypatch)
    with TestClient(_app(tmp_path)) as client:
        r = client.post("/api/corpus-request", json={"target": 600, "note": "vertical 2"})
        assert r.status_code == 200
        body = r.json()
        assert body["present"] is True
        assert body["fulfilled"] is False
        assert body["request"]["target"] == 600
        assert body["request"]["status"] == "open"
        # The intent file is on disk where the producer skill looks.
        on_disk = json.loads((d / "corpus-request.json").read_text())
        assert on_disk["kind"] == "corpus_request"
        assert on_disk["note"] == "vertical 2"
        # GET returns the same view.
        g = client.get("/api/corpus-request").json()
        assert g["present"] is True and g["request"]["target"] == 600


def test_fulfilment_is_observed_from_a_newer_heartbeat(tmp_path, monkeypatch):
    d = _corpus_dir(tmp_path, monkeypatch)
    with TestClient(_app(tmp_path)) as client:
        client.post("/api/corpus-request", json={"target": 600})
        # No heartbeat yet → open, unfulfilled.
        assert client.get("/api/corpus-request").json()["fulfilled"] is False
        # A heartbeat stamped AFTER the request → fulfilled, by observation.
        req_mtime = (d / "corpus-request.json").stat().st_mtime
        _heartbeat(d, mtime=req_mtime + 5)
        g = client.get("/api/corpus-request").json()
        assert g["fulfilled"] is True
        assert g["fulfilled_by"] == "corpus-progress-test.json"


def test_older_heartbeat_does_not_fulfil(tmp_path, monkeypatch):
    d = _corpus_dir(tmp_path, monkeypatch)
    _heartbeat(d, mtime=time.time() - 3600)  # an hour-old prior run
    with TestClient(_app(tmp_path)) as client:
        client.post("/api/corpus-request", json={})
        g = client.get("/api/corpus-request").json()
        assert g["fulfilled"] is False


def test_delete_withdraws(tmp_path, monkeypatch):
    d = _corpus_dir(tmp_path, monkeypatch)
    with TestClient(_app(tmp_path)) as client:
        client.post("/api/corpus-request", json={})
        assert (d / "corpus-request.json").is_file()
        r = client.delete("/api/corpus-request")
        assert r.status_code == 200
        assert r.json()["present"] is False
        assert not (d / "corpus-request.json").is_file()
        assert client.get("/api/corpus-request").json()["present"] is False


def test_liveness_none_live_stale_done(tmp_path, monkeypatch):
    d = _corpus_dir(tmp_path, monkeypatch)
    with TestClient(_app(tmp_path)) as client:
        # none — no heartbeat at all.
        assert client.get("/api/corpus-request").json()["liveness"]["state"] == "none"
        # live — a running heartbeat inside the window.
        p = _heartbeat(d, status="running")
        assert client.get("/api/corpus-request").json()["liveness"]["state"] == "live"
        # stale — claims running but stopped stamping (the OBS-3 blind spot).
        os.utime(p, (time.time() - 3600, time.time() - 3600))
        lv = client.get("/api/corpus-request").json()["liveness"]
        assert lv["state"] == "stale"
        assert lv["age_s"] > 1800
        # done — the newest run finished; age no longer matters.
        _heartbeat(d, status="done", mtime=time.time() - 3600)
        assert client.get("/api/corpus-request").json()["liveness"]["state"] == "done"


def test_liveness_window_env_override(tmp_path, monkeypatch):
    d = _corpus_dir(tmp_path, monkeypatch)
    p = _heartbeat(d, status="running", mtime=time.time() - 60)
    monkeypatch.setenv("FK_ARENA_CORPUS_LIVE_S", "30")
    with TestClient(_app(tmp_path)) as client:
        assert client.get("/api/corpus-request").json()["liveness"]["state"] == "stale"
    monkeypatch.setenv("FK_ARENA_CORPUS_LIVE_S", "600")
    with TestClient(_app(tmp_path)) as client:
        assert client.get("/api/corpus-request").json()["liveness"]["state"] == "live"


def test_corpus_stage_carries_liveness_and_request(tmp_path, monkeypatch):
    d = _corpus_dir(tmp_path, monkeypatch)
    _heartbeat(d, status="running")
    with TestClient(_app(tmp_path)) as client:
        client.post("/api/corpus-request", json={"note": "next vertical"})
        body = client.get("/api/build").json()
        corpus = {s["key"]: s for s in body["stages"]}["corpus"]
        assert corpus["liveness"]["state"] == "live"
        assert corpus["request"]["present"] is True
        assert corpus["request"]["request"]["note"] == "next vertical"


def test_corpus_progress_response_carries_liveness(tmp_path, monkeypatch):
    _corpus_dir(tmp_path, monkeypatch)
    with TestClient(_app(tmp_path)) as client:
        body = client.get("/api/corpus-progress").json()
        assert body["available"] is False
        assert body["liveness"]["state"] == "none"


def test_request_validation_422(tmp_path, monkeypatch):
    _corpus_dir(tmp_path, monkeypatch)
    with TestClient(_app(tmp_path)) as client:
        assert client.post("/api/corpus-request", json={"target": 0}).status_code == 422
        assert client.post("/api/corpus-request", json={"target": -5}).status_code == 422
        assert client.post(
            "/api/corpus-request", json={"note": "x" * 501}
        ).status_code == 422
