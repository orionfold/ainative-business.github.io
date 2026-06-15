"""Tests for the lane-truth system of record (AE-18/19/20, arena-enhancements-v2 Cluster G).

Covers discovery (mocked HTTP), the Arena-owned registry file roundtrip, and the
reconciliation rules (registry∩discovery, single-discovered auto, Hermes-hint
demotion, drift, ambiguous, none).
"""

from __future__ import annotations

import json

import pytest

from fieldkit.arena import lanes


# --------------------------------------------------------------------------- #
# discovery (AE-18)
# --------------------------------------------------------------------------- #
def _fake_http(mapping):
    """Build a fake ``_http_json`` from a ``{url-substr: payload}`` map."""

    def _inner(url, timeout):
        for key, payload in mapping.items():
            if key in url:
                return payload
        return None

    return _inner


def test_probe_port_llama_server(monkeypatch):
    monkeypatch.setattr(
        lanes,
        "_http_json",
        _fake_http(
            {
                ":8091/v1/models": {"data": [{"id": "model-Q8_0.gguf"}]},
                ":8091/props": {
                    "model_path": "/data/quants/Kepler/model-Q8_0.gguf",
                    "default_generation_settings": {"n_ctx": 8192},
                },
            }
        ),
    )
    lane = lanes.probe_port(8091)
    assert lane is not None
    assert lane["model"] == "model-Q8_0.gguf"
    assert lane["base_url"] == "http://127.0.0.1:8091/v1"
    assert lane["context_length"] == 8192
    assert lane["kind"] == "LlamaServerLane"
    assert lane["source"] == "discovered"


def test_probe_port_dead_returns_none(monkeypatch):
    monkeypatch.setattr(lanes, "_http_json", _fake_http({}))
    assert lanes.probe_port(8080) is None


def test_discover_collects_live_ports(monkeypatch):
    monkeypatch.setattr(
        lanes,
        "_http_json",
        _fake_http({":8091/v1/models": {"data": [{"id": "kepler"}]}}),
    )
    found = lanes.discover(ports=[8080, 8091, 8000])
    assert [l["port"] for l in found] == [8091]


def test_lane_ports_env_override(monkeypatch):
    monkeypatch.setenv("FK_ARENA_LANE_PORTS", "9001, 9002 ,bad,9003")
    assert lanes.lane_ports() == [9001, 9002, 9003]


def test_lane_ports_excludes_embedder_infra_port(monkeypatch):
    # AD-AE: the Cortex embedder (:8001) answers /v1/models but is NOT a chat
    # lane. Discovery must exclude the infra ports so the cockpit doesn't see a
    # phantom 2nd lane and land "ambiguous"/idle.
    monkeypatch.delenv("FK_ARENA_LANE_PORTS", raising=False)
    monkeypatch.delenv("FK_ARENA_INFRA_PORTS", raising=False)
    ports = lanes.lane_ports()
    assert 8001 not in ports  # embedder filtered out
    assert 8091 in ports and 8000 in ports  # chat lanes kept


def test_lane_ports_infra_exemption_can_be_turned_off(monkeypatch):
    # FK_ARENA_INFRA_PORTS set-but-empty = "exempt nothing" → 8001 swept again.
    monkeypatch.delenv("FK_ARENA_LANE_PORTS", raising=False)
    monkeypatch.setenv("FK_ARENA_INFRA_PORTS", "")
    assert 8001 in lanes.lane_ports()


# --------------------------------------------------------------------------- #
# registry (AE-19) — Arena owns the selection, in a JSON file (no db schema)
# --------------------------------------------------------------------------- #
def test_registry_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setenv("FK_ARENA_LANE_DIR", str(tmp_path))
    assert lanes.load_active_lane() is None
    lanes.save_active_lane({"model": "kepler", "port": 8091})
    assert lanes.lane_registry_path().is_file()
    assert lanes.load_active_lane()["port"] == 8091
    lanes.clear_active_lane()
    assert lanes.load_active_lane() is None


def test_registry_corrupt_file_is_none(tmp_path, monkeypatch):
    monkeypatch.setenv("FK_ARENA_LANE_DIR", str(tmp_path))
    lanes.lane_registry_path().write_text("{not json")
    assert lanes.load_active_lane() is None  # never raises


# --------------------------------------------------------------------------- #
# reconciliation (AE-19/20, AE-R9/R11)
# --------------------------------------------------------------------------- #
_KEPLER = {"model": "model-Q8_0.gguf", "base_url": "http://127.0.0.1:8091/v1", "port": 8091}
_HERMES = {"model": "Qwen3-30B", "base_url": "http://127.0.0.1:8080/v1", "port": 8080}


def test_resolve_single_discovered_auto():
    r = lanes.resolve_active_lane(discovered=[_KEPLER], registry=None, hermes_hint=_HERMES)
    assert r["source"] == "discovered"
    assert r["base_url"] == _KEPLER["base_url"]
    assert r["drift"] is None


def test_resolve_registry_confirmed_live():
    reg = {"model": "model-Q8_0.gguf", "port": 8091}
    r = lanes.resolve_active_lane(discovered=[_KEPLER], registry=reg, hermes_hint=_HERMES)
    assert r["source"] == "registry"
    assert r["port"] == 8091
    assert r["drift"] is None


def test_resolve_registry_dead_falls_through_with_drift():
    reg = {"model": "ghost", "port": 9999}
    r = lanes.resolve_active_lane(discovered=[_KEPLER], registry=reg, hermes_hint=_HERMES)
    assert r["source"] == "discovered"  # falls through to the one live lane
    assert "not live" in (r["drift"] or "")


def test_resolve_registry_model_mismatch_flags_drift():
    reg = {"model": "totally-different", "port": 8091}
    r = lanes.resolve_active_lane(discovered=[_KEPLER], registry=reg, hermes_hint=_HERMES)
    assert r["source"] == "registry"
    assert r["drift"] and "but it serves" in r["drift"]


def test_resolve_hermes_hint_fallback_when_none_discovered():
    # Discovery found nothing → the demoted Hermes hint is surfaced (configured ·
    # idle), never blank — but labelled hermes-hint, not a claim it's serving.
    r = lanes.resolve_active_lane(discovered=[], registry=None, hermes_hint=_HERMES)
    assert r["source"] == "hermes-hint"
    assert r["port"] == 8080
    assert r["base_url"] == _HERMES["base_url"]


def test_resolve_ambiguous_blocks_hint_fallback():
    # >1 discovered, no registry pick → ambiguous; the hint does NOT override it.
    two = [_KEPLER, {**_HERMES}]
    r = lanes.resolve_active_lane(discovered=two, registry=None, hermes_hint=_HERMES)
    assert r["source"] == "ambiguous"
    assert r["base_url"] == ""


def test_resolve_none_when_nothing_live_and_no_hint():
    r = lanes.resolve_active_lane(discovered=[], registry=None, hermes_hint=None)
    assert r["source"] == "none"
    assert r["base_url"] == ""
    assert r["discovered"] == []
