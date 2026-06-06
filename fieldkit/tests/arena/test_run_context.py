# Copyright 2026 Manav Sehgal
# SPDX-License-Identifier: Apache-2.0
"""Tests for run-context (AE-23) + the AE-22 select run-anchor (arena-enhancements-v2 cut 2).

``GET /api/run-context`` derives the current run from the build-manifest vertical
+ the reconciled active lane; ``POST /api/active-lane`` now stamps ``set_at`` —
the run anchor the AE-24 provenance chips compare data ages against. Honest when
unanchored: no operator selection ⇒ ``anchored`` false, no run boundary claimed.

Hermetic notes: conftest neutralizes ``discover_cached`` to ``[]`` and pins the
lane registry per-test; tests that need a discovered lane re-patch it. The real
``~/.hermes/config.yaml`` (present on the operator box, absent elsewhere) only
affects the demoted hint, so assertions avoid the hint-dependent ``source``
value in the unanchored cases.
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from fieldkit.arena import lanes
from fieldkit.arena.server import create_app

_KEPLER_LANE = {
    "id": "discovered:8091",
    "kind": "LlamaServerLane",
    "model": "model-Q8_0.gguf",
    "base_url": "http://127.0.0.1:8091/v1",
    "port": 8091,
    "provider": "custom",
    "context_length": 8192,
    "max_tokens": None,
    "model_path": "/data/quants/Kepler/model-Q8_0.gguf",
    "source": "discovered",
}


def _mk_app(tmp_path, monkeypatch, manifest=None):
    build_dir = tmp_path / "evidence"
    build_dir.mkdir(exist_ok=True)
    if manifest is not None:
        (build_dir / "build-manifest.json").write_text(json.dumps(manifest))
    monkeypatch.setenv("FK_ARENA_BUILD_DIR", str(build_dir))
    return create_app(
        repo_root=tmp_path, db=str(tmp_path / "arena.db"), telemetry_interval=2.0
    )


def test_run_context_unanchored(tmp_path, monkeypatch):
    """No operator selection ⇒ anchored:false, no run_started, lane not live."""
    app = _mk_app(
        tmp_path,
        monkeypatch,
        manifest={
            "vertical": "astrodynamics",
            "label": "Kepler",
            "bench_id": "astro-bench",
        },
    )
    with TestClient(app) as client:
        body = client.get("/api/run-context").json()
    assert body["vertical"] == "astrodynamics"
    assert body["label"] == "Kepler"
    assert body["bench_id"] == "astro-bench"
    assert body["anchored"] is False
    assert body["run_started"] is None
    # Discovery is neutralized; a hermes hint (if present on the box) is an
    # assertion, never "live" — lane_live stays honestly false.
    assert body["lane_live"] is False


def test_run_context_label_falls_back_to_vertical(tmp_path, monkeypatch):
    app = _mk_app(tmp_path, monkeypatch, manifest={"vertical": "astrodynamics"})
    with TestClient(app) as client:
        body = client.get("/api/run-context").json()
    assert body["label"] == "astrodynamics"


def test_run_context_no_manifest(tmp_path, monkeypatch):
    """No build-manifest ⇒ no vertical claimed (still a clean 200, never an error)."""
    app = _mk_app(tmp_path, monkeypatch, manifest=None)
    with TestClient(app) as client:
        body = client.get("/api/run-context").json()
    assert body["vertical"] is None
    assert body["label"] is None
    assert body["anchored"] is False


def test_select_lane_stamps_run_anchor(tmp_path, monkeypatch):
    """AE-22 select arms the run: registry gains set_at; run-context anchors on it."""
    monkeypatch.setattr(lanes, "discover_cached", lambda *a, **k: [dict(_KEPLER_LANE)])
    app = _mk_app(
        tmp_path, monkeypatch, manifest={"vertical": "astrodynamics", "label": "Kepler"}
    )
    with TestClient(app) as client:
        r = client.post("/api/active-lane", json={"port": 8091})
        assert r.status_code == 200
        reg = lanes.load_active_lane()
        assert reg["port"] == 8091
        assert reg["source"] == "operator-selected"
        assert reg["set_at"] and reg["set_at"].endswith("Z")  # the AE-23 anchor

        body = client.get("/api/run-context").json()
        assert body["anchored"] is True
        assert body["run_started"] == reg["set_at"]
        assert body["lane"]["port"] == 8091
        assert body["lane"]["model"] == "model-Q8_0.gguf"
        assert body["lane_live"] is True
        assert body["source"] == "registry"
        assert body["drift"] is None
        assert body["discovered_n"] == 1

        # Clear → run-context reverts honestly to unanchored.
        assert client.post("/api/active-lane", json={"clear": True}).status_code == 200
        body = client.get("/api/run-context").json()
        assert body["anchored"] is False
        assert body["run_started"] is None


def test_run_context_surfaces_registry_drift(tmp_path, monkeypatch):
    """A selected lane that died ⇒ drift is explicit on run-context (AE-R9)."""
    monkeypatch.setattr(lanes, "discover_cached", lambda *a, **k: [dict(_KEPLER_LANE)])
    lanes.save_active_lane(
        {"model": "ghost", "port": 9999, "source": "operator-selected", "set_at": "2026-06-06T00:00:00Z"}
    )
    app = _mk_app(tmp_path, monkeypatch, manifest={"vertical": "astrodynamics"})
    with TestClient(app) as client:
        body = client.get("/api/run-context").json()
    assert body["anchored"] is True  # the selection exists…
    assert "not live" in (body["drift"] or "")  # …but reality disagrees, loudly


def test_select_dead_port_404(tmp_path, monkeypatch):
    app = _mk_app(tmp_path, monkeypatch)
    with TestClient(app) as client:
        assert client.post("/api/active-lane", json={"port": 9999}).status_code == 404
