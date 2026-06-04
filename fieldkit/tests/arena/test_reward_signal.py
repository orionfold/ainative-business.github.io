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


def test_reward_signal_absent_is_clean_empty(tmp_path: Path) -> None:
    # No report on a fresh box → available:false, not a 404/500.
    app = create_app(repo_root=tmp_path, telemetry_interval=2.0)
    with TestClient(app) as client:
        r = client.get("/api/reward-signal")
        assert r.status_code == 200
        assert r.json() == {"available": False, "kind": "preflight"}


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
