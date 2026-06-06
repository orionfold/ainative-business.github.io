# Copyright 2026 Manav Sehgal
# SPDX-License-Identifier: Apache-2.0
"""Tests for AE-10 (S6) — the hf-model-scout → Compare projection.

Covers the report parser (ranked picks + ruled-out table + the ``> Run:`` line),
the ``candidates.json`` join (license / arch / Spark-envelope traps), the
newest-report selection, and the ``GET /api/scout`` endpoint (available + empty).
Pure filesystem reads — no skill import (AE-R3), no GPU, no db.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from fieldkit.arena import server
from fieldkit.arena.server import create_app

_REPORT = """# HF Model Scout — astrodynamics @ ~7-8B

> Run: 2026-06-04 (UTC) · license_tier=permissive (commercial-OK) · eval_bench=astro-bench

## Recommended picks

### 1. Qwen/Qwen3-8B — score 95/100 · the RLVR-native reasoning base
- License: apache-2.0

### 2. Qwen/Qwen2.5-Math-7B-Instruct — score 84/100 · purest math priors, context-capped
- License: apache-2.0

### 3. Qwen/Qwen2.5-7B-Instruct — score 80/100 · the safe generalist workhorse
- License: apache-2.0

## Picks ruled out

| Repo | Reason |
|------|--------|
| `PhysicsWallahAI/Aryabhata-1.0` | cc-by-nc-4.0 — non-commercial |
| `nvidia/Nemotron-H-8B-Reasoning` | Hybrid SSM/Mamba arch — not in llama.cpp |

## Next steps
"""

_CANDIDATES = [
    {
        "repo": "Qwen/Qwen3-8B",
        "license": "apache-2.0",
        "commercial_ok": "true",
        "chat_format": "chatml",
        "training_type": "DPO/RLHF",
        "arch_name": "qwen3",
        "llama_cpp_compat": "true",
        "spark_envelope": {"f16_gb": 16.94, "q4km_gb": 4.83, "estimated_tg_tok_s": 42.2, "fits_q4km": True},
        "warnings": [""],
    },
    {
        "repo": "PhysicsWallahAI/Aryabhata-1.0",
        "license": "cc-by-nc-4.0",
        "commercial_ok": "false",
        "chat_format": "MISSING",
        "training_type": "SFT",
        "arch_name": "qwen2",
        "llama_cpp_compat": "true",
        "spark_envelope": {"f16_gb": 15.33, "q4km_gb": 4.37, "estimated_tg_tok_s": 38.2, "fits_q4km": True},
        "warnings": ["chat_template missing — MANUAL_REVIEW"],
    },
]


def _seed_scout(scout_dir: Path) -> Path:
    run = scout_dir / "2026-06-04" / "astrodynamics-7B"
    run.mkdir(parents=True, exist_ok=True)
    (run / "report.md").write_text(_REPORT)
    (run / "candidates.json").write_text(json.dumps(_CANDIDATES))
    return run


def test_parse_scout_report_picks_and_ruled_out() -> None:
    parsed = server._parse_scout_report(_REPORT)
    assert [p["repo"] for p in parsed["picks"]] == [
        "Qwen/Qwen3-8B", "Qwen/Qwen2.5-Math-7B-Instruct", "Qwen/Qwen2.5-7B-Instruct"
    ]
    assert parsed["picks"][0]["score"] == 95
    assert parsed["picks"][0]["tagline"] == "the RLVR-native reasoning base"
    assert parsed["generated"].startswith("2026-06-04 (UTC)")
    ruled = {r["repo"] for r in parsed["ruled_out"]}
    assert ruled == {"PhysicsWallahAI/Aryabhata-1.0", "nvidia/Nemotron-H-8B-Reasoning"}
    # the markdown header/separator rows must not leak in as a candidate
    assert "Repo" not in ruled


def test_scout_projection_joins_candidates(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("FK_ARENA_SCOUT_DIR", str(tmp_path))
    _seed_scout(tmp_path)
    proj = server._scout_projection()
    assert proj is not None and proj["available"] is True
    assert proj["run"] == "2026-06-04/astrodynamics-7B"
    assert proj["n_candidates"] == 2
    top = proj["picks"][0]
    assert top["repo"] == "Qwen/Qwen3-8B"
    assert top["license"] == "apache-2.0" and top["commercial_ok"] == "true"
    assert top["arch"] == "qwen3" and top["q4km_gb"] == 4.83 and top["fits"] is True
    # a pick with no candidate match still renders (axes just come back None)
    assert proj["picks"][1]["arch"] is None


def test_scout_projection_picks_newest_report(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("FK_ARENA_SCOUT_DIR", str(tmp_path))
    old = tmp_path / "old" / "v1"
    old.mkdir(parents=True)
    (old / "report.md").write_text("### 1. old/model — score 10/100 · stale\n")
    import os
    import time
    os.utime(old / "report.md", (time.time() - 9999, time.time() - 9999))
    _seed_scout(tmp_path)  # newer mtime
    proj = server._scout_projection()
    assert proj["picks"][0]["repo"] == "Qwen/Qwen3-8B"


def test_scout_projection_absent_returns_none(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("FK_ARENA_SCOUT_DIR", str(tmp_path / "empty"))
    assert server._scout_projection() is None


def test_api_scout_endpoint_available(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("FK_ARENA_SCOUT_DIR", str(tmp_path))
    monkeypatch.setattr(
        server, "_read_hermes_lane", lambda *a, **k: None, raising=False
    )
    _seed_scout(tmp_path)
    with TestClient(create_app(repo_root=tmp_path, db=str(tmp_path / "x.db"), telemetry_interval=2.0)) as client:
        r = client.get("/api/scout")
        assert r.status_code == 200
        body = r.json()
        assert body["available"] is True
        assert len(body["picks"]) == 3
        assert body["ruled_out"]


def test_api_scout_endpoint_empty(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("FK_ARENA_SCOUT_DIR", str(tmp_path / "empty"))
    with TestClient(create_app(repo_root=tmp_path, db=str(tmp_path / "x.db"), telemetry_interval=2.0)) as client:
        r = client.get("/api/scout")
        assert r.status_code == 200
        assert r.json()["available"] is False
