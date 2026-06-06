"""Tests for the vertical-build spine endpoint (AE-5 / AF-1 — ``GET /api/build``).

The spine is a pure projection over signals the cockpit already has (the reward
report, the bench registry, the rl_run rows, the lane arbiter) plus an optional
``build-manifest.json``. These tests pin the assembly contract: eight stages in
pipeline order, the live-feed signals win, the manifest fills the no-feed stages
+ the gate annotations, and a fresh box degrades to ``pending`` rather than a 500
— never reading or writing arena.db schema.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

fastapi = pytest.importorskip("fastapi")

from fastapi.testclient import TestClient  # noqa: E402

from fieldkit.arena.server import create_app  # noqa: E402

_STAGE_KEYS = ["scout", "bench", "corpus", "sft", "smoke", "lane", "rlvr", "publish"]

_REWARD = {
    "model": "Qwen/Qwen3-8B",
    "status": "done",
    "boxed_rate": 1.0,
    "reward_rate_step0": 0.864,
    "gate_pass": True,
}


def _no_hermes(monkeypatch: pytest.MonkeyPatch) -> None:
    """Steer the resident-lane reader at nothing so the lane stage is
    deterministic regardless of the developer's local Spark state."""
    monkeypatch.setattr(
        "fieldkit.arena.server._read_hermes_lane",
        lambda hermes_path=None: None,
    )


def _no_scout(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Point the scout-presence probe at an empty dir (no /tmp/hf-scout leak)."""
    monkeypatch.setenv("FK_ARENA_SCOUT_DIR", str(tmp_path / "no-scout"))


def _no_sft(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Point the SFT-feed reader at an empty dir so the developer's real
    ``/home/nvidia/data`` run-root doesn't leak into a hermetic assertion."""
    monkeypatch.setenv("FK_ARENA_SFT_DIR", str(tmp_path / "no-sft"))


def _app(tmp_path: Path):
    return create_app(
        repo_root=tmp_path,
        db=str(tmp_path / "no-such.db"),
        telemetry_interval=2.0,
    )


def test_build_fresh_box_is_all_pending(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # No manifest, no feeds → 200 with eight stages in pipeline order, not a
    # 404/500. The stages with no signal on a clean box (corpus/smoke/lane/rlvr/
    # publish + the neutralized scout/sft) read pending; bench reflects the
    # machine-global registry, so it isn't asserted here.
    _no_hermes(monkeypatch)
    _no_scout(monkeypatch, tmp_path)
    _no_sft(monkeypatch, tmp_path)
    with TestClient(_app(tmp_path)) as client:
        r = client.get("/api/build")
        assert r.status_code == 200
        body = r.json()
        assert body["available"] is True
        assert body["manifest_present"] is False
        assert body["stages_total"] == 8
        assert [s["key"] for s in body["stages"]] == _STAGE_KEYS
        stages = {s["key"]: s for s in body["stages"]}
        for key in ("scout", "corpus", "smoke", "rlvr", "publish"):
            assert stages[key]["state"] == "pending", key
        # no resident config + no db → lane is pending (not falsely "active")
        assert stages["lane"]["state"] == "pending"


def test_build_live_reward_lights_smoke_stage(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The smoke stage reads the newest reward report live (no manifest needed):
    # a passing av10-preflight → done + the held-out headline + gate pass.
    _no_hermes(monkeypatch)
    _no_scout(monkeypatch, tmp_path)
    p = tmp_path / "evidence" / "astrodynamics" / "av10-preflight.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(_REWARD))
    with TestClient(_app(tmp_path)) as client:
        stages = {s["key"]: s for s in client.get("/api/build").json()["stages"]}
        smoke = stages["smoke"]
        assert smoke["state"] == "done"
        assert smoke["source"] == "reward-signal"
        assert "86%" in smoke["headline"]
        assert smoke["gate_state"] == "pass"
        assert "boxed 100%" in smoke["detail"]


def test_build_running_reward_marks_smoke_active(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _no_hermes(monkeypatch)
    _no_scout(monkeypatch, tmp_path)
    p = tmp_path / "evidence" / "astrodynamics" / "av10-preflight.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(dict(_REWARD, status="running", scored=3, total=8)))
    with TestClient(_app(tmp_path)) as client:
        stages = {s["key"]: s for s in client.get("/api/build").json()["stages"]}
        assert stages["smoke"]["state"] == "active"
        assert "3/8" in stages["smoke"]["headline"]


def test_build_manifest_fills_no_feed_stages_and_label(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The manifest owns the no-live-feed stages (scout/corpus/publish) + the
    # vertical label + the human-gate text; it must NOT clobber a live signal.
    _no_hermes(monkeypatch)
    _no_scout(monkeypatch, tmp_path)
    p = tmp_path / "evidence" / "astrodynamics" / "av10-preflight.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(_REWARD))
    manifest = {
        "vertical": "astrodynamics",
        "label": "Kepler",
        "updated": "2026-06-05",
        "stages": {
            "scout": {"state": "done", "headline": "Qwen3-8B locked", "gate_state": "pass"},
            "publish": {
                "state": "done",
                "headline": "Orionfold/Kepler-GGUF",
                "href": "https://huggingface.co/Orionfold/Kepler-GGUF",
                "gate_state": "pass",
            },
            # smoke is a LIVE stage — the manifest's bogus headline must be ignored
            # in favor of the reward report, but its gate annotation still applies.
            "smoke": {"headline": "SHOULD-NOT-WIN", "gate": "AV-10 preflight"},
        },
    }
    (tmp_path / "evidence" / "astrodynamics" / "build-manifest.json").write_text(
        json.dumps(manifest)
    )
    with TestClient(_app(tmp_path)) as client:
        body = client.get("/api/build").json()
        assert body["label"] == "Kepler"
        assert body["manifest_present"] is True
        stages = {s["key"]: s for s in body["stages"]}
        assert stages["scout"]["state"] == "done"
        assert stages["scout"]["headline"] == "Qwen3-8B locked"
        assert stages["publish"]["href"].endswith("Kepler-GGUF")
        # live smoke headline wins; manifest gate annotation still applied
        assert "86%" in stages["smoke"]["headline"]
        assert stages["smoke"]["headline"] != "SHOULD-NOT-WIN"
        assert stages["smoke"]["gate"] == "AV-10 preflight"


def test_build_manifest_bench_id_unregistered_stays_blank(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # An explicit bench_id that isn't registered (astro-bench, pending AE-11)
    # must NOT fall back to an unrelated vertical's bench — it stays blank so the
    # manifest fills it, rather than mislabeling the card.
    _no_hermes(monkeypatch)
    _no_scout(monkeypatch, tmp_path)
    manifest = {
        "vertical": "astrodynamics",
        "label": "Kepler",
        "bench_id": "astro-bench",
        "stages": {
            "bench": {"state": "done", "headline": "astro-bench v0.1 · 120+44"},
        },
    }
    (tmp_path / "evidence" / "astrodynamics").mkdir(parents=True, exist_ok=True)
    (tmp_path / "evidence" / "astrodynamics" / "build-manifest.json").write_text(
        json.dumps(manifest)
    )
    with TestClient(_app(tmp_path)) as client:
        stages = {s["key"]: s for s in client.get("/api/build").json()["stages"]}
        # the manifest's headline fills the blanked live stage
        assert stages["bench"]["headline"] == "astro-bench v0.1 · 120+44"
        assert "Patent" not in stages["bench"]["headline"]


def test_build_dir_env_override(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # FK_ARENA_BUILD_DIR relocates the manifest away from the evidence default.
    _no_hermes(monkeypatch)
    _no_scout(monkeypatch, tmp_path)
    alt = tmp_path / "alt-build"
    alt.mkdir()
    (alt / "build-manifest.json").write_text(
        json.dumps({"label": "Relocated", "stages": {}})
    )
    monkeypatch.setenv("FK_ARENA_BUILD_DIR", str(alt))
    with TestClient(_app(tmp_path)) as client:
        body = client.get("/api/build").json()
        assert body["label"] == "Relocated"
        assert body["manifest_present"] is True
