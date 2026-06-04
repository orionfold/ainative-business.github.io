# Copyright 2026 Manav Sehgal
# SPDX-License-Identifier: Apache-2.0
"""Tests for the `GET /api/reward-signal` endpoint (dogfood AF-3).

The eval-is-reward gauge — a read-only render of a reward-signal report JSON
(today the AV-10 preflight baseline). No arena.db read, no schema bump
(AH-9/RV-8): the endpoint reads a file under ``repo_root`` (or the
``FK_ARENA_REWARD_SIGNAL`` override) and degrades to ``{available: false}``
when no report exists, so the cockpit pane paints a clean empty state.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

fastapi = pytest.importorskip("fastapi")

from fastapi.testclient import TestClient  # noqa: E402

from fieldkit.arena.server import create_app  # noqa: E402

_FIXTURE = {
    "model": "Qwen/Qwen3-8B",
    "n": 2,
    "max_new_tokens": 2560,
    "rel_tol": 0.02,
    "boxed_rate": 0.5,
    "extract_rate": 0.5,
    "reward_rate_step0": 0.5,
    "truncation_rate": 0.0,
    "av_r1_clear": True,
    "gate_pass": True,
    "buckets": {"correct": 1, "boxed_wrong": 0, "no_answer": 1, "truncated_think": 0},
    "rows": [
        {"task_id": "astro-x", "subtopic": "parallax_distance", "tier": 1,
         "answer": "4.348 pc", "score": 1.0, "bucket": "correct",
         "boxed": "4.35 pc", "n_chars": 900, "wall_s": 30.0},
    ],
}


def _write_report(repo_root: Path) -> Path:
    p = repo_root / "evidence" / "astrodynamics" / "av10-preflight.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(_FIXTURE))
    return p


def test_reward_signal_present(tmp_path: Path) -> None:
    _write_report(tmp_path)
    app = create_app(repo_root=tmp_path, telemetry_interval=2.0)
    with TestClient(app) as client:
        r = client.get("/api/reward-signal")
        assert r.status_code == 200
        body = r.json()
        assert body["available"] is True
        assert body["kind"] == "preflight"
        assert body["report"]["gate_pass"] is True
        assert body["report"]["model"] == "Qwen/Qwen3-8B"
        assert body["report"]["buckets"]["correct"] == 1


def test_reward_signal_passes_through_running_status(tmp_path: Path) -> None:
    # AF-9 live mode: a mid-flight report carries status/scored/total — the
    # endpoint returns the report verbatim, so the pane can stream the run.
    running = dict(_FIXTURE, status="running", scored=1, total=8)
    p = tmp_path / "evidence" / "astrodynamics" / "av10-preflight.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(running))
    app = create_app(repo_root=tmp_path, telemetry_interval=2.0)
    with TestClient(app) as client:
        body = client.get("/api/reward-signal").json()
        assert body["available"] is True
        assert body["report"]["status"] == "running"
        assert body["report"]["scored"] == 1
        assert body["report"]["total"] == 8


def test_reward_signal_absent_is_clean_empty(tmp_path: Path) -> None:
    # No report on a fresh box → available:false, not a 404/500. The history
    # list (AF-9) is present but empty.
    app = create_app(repo_root=tmp_path, telemetry_interval=2.0)
    with TestClient(app) as client:
        r = client.get("/api/reward-signal")
        assert r.status_code == 200
        assert r.json() == {"available": False, "kind": "preflight", "runs": []}


def _write_named(repo_root: Path, name: str, mtime: float, **over: object) -> Path:
    p = repo_root / "evidence" / "astrodynamics" / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({**_FIXTURE, **over}))
    import os
    os.utime(p, (mtime, mtime))
    return p


def test_reward_signal_prefers_newest_run(tmp_path: Path) -> None:
    # AF-9 auto-follow: with no selection, the newest report by mtime wins.
    _write_named(tmp_path, "av10-preflight.json", 1000.0, max_new_tokens=4096)
    _write_named(tmp_path, "av10-preflight-8192.json", 2000.0, max_new_tokens=8192)
    app = create_app(repo_root=tmp_path, telemetry_interval=2.0)
    with TestClient(app) as client:
        body = client.get("/api/reward-signal").json()
        assert body["available"] is True
        assert body["source"] == "av10-preflight-8192.json"
        assert body["report"]["max_new_tokens"] == 8192


def test_reward_signal_history_and_source_select(tmp_path: Path) -> None:
    # AF-9 history dropdown: runs is newest-first with summaries, and ?source=
    # serves a specific prior run.
    _write_named(tmp_path, "av10-preflight.json", 1000.0, max_new_tokens=4096,
                 gate_pass=False)
    _write_named(tmp_path, "av10-preflight-8192.json", 2000.0, max_new_tokens=8192,
                 status="running", scored=3, total=8)
    app = create_app(repo_root=tmp_path, telemetry_interval=2.0)
    with TestClient(app) as client:
        body = client.get("/api/reward-signal").json()
        runs = body["runs"]
        assert [r["source"] for r in runs] == [
            "av10-preflight-8192.json", "av10-preflight.json"]  # newest first
        assert runs[0]["status"] == "running" and runs[0]["scored"] == 3
        assert runs[1]["max_new_tokens"] == 4096
        # pick the older run explicitly
        picked = client.get("/api/reward-signal",
                            params={"source": "av10-preflight.json"}).json()
        assert picked["source"] == "av10-preflight.json"
        assert picked["report"]["max_new_tokens"] == 4096


def test_reward_signal_source_traversal_rejected(tmp_path: Path) -> None:
    # A crafted ../ source can't escape the evidence dir → available:false.
    _write_named(tmp_path, "av10-preflight.json", 1000.0)
    (tmp_path / "secret.json").write_text(json.dumps({"leak": True}))
    app = create_app(repo_root=tmp_path, telemetry_interval=2.0)
    with TestClient(app) as client:
        body = client.get("/api/reward-signal",
                          params={"source": "../../secret.json"}).json()
        assert body["available"] is False  # name doesn't match av10-preflight*
        # an unknown but well-formed name is also rejected (file absent)
        body2 = client.get("/api/reward-signal",
                           params={"source": "av10-preflight-nope.json"}).json()
        assert body2["available"] is False


def test_reward_signal_malformed_degrades(tmp_path: Path) -> None:
    p = tmp_path / "evidence" / "astrodynamics" / "av10-preflight.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("{not valid json")
    app = create_app(repo_root=tmp_path, telemetry_interval=2.0)
    with TestClient(app) as client:
        r = client.get("/api/reward-signal")
        assert r.status_code == 200
        assert r.json()["available"] is False


def test_reward_signal_env_override(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    custom = tmp_path / "custom-report.json"
    custom.write_text(json.dumps(_FIXTURE))
    monkeypatch.setenv("FK_ARENA_REWARD_SIGNAL", str(custom))
    # repo_root has NO report — the override must win.
    app = create_app(repo_root=tmp_path, telemetry_interval=2.0)
    with TestClient(app) as client:
        r = client.get("/api/reward-signal")
        assert r.status_code == 200
        assert r.json()["available"] is True
        assert r.json()["report"]["n"] == 2
