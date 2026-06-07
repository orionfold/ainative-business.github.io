# Copyright 2026 Manav Sehgal
# SPDX-License-Identifier: Apache-2.0
"""AE-31 (arena-enhancements-v2 cut 4) — the guarded lane launch/teardown runner.

Unit half (no real Popen — that's ``test_launch_process.py``): the recipe
contract, every typed pre-flight refusal in its locked order, the envelope
math, the teardown honest-revert rules, and the PID-reuse no-kill guard.
``FK_ARENA_LANE_DIR`` is conftest-pinned per test, so recipes/owners/locks
never touch the operator's real ``~/.fieldkit/arena``.
"""

from __future__ import annotations

import fcntl
import json
import os
import socket
import sys
from pathlib import Path

import pytest

from fieldkit.arena import lanes, launcher
from fieldkit.arena.launcher import LaunchRefused


def _write_recipes(tmp_path: Path, recipes: list[dict]) -> Path:
    p = tmp_path / "lane-registry" / "lane-recipes.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(recipes))
    return p


def _fake_binary(tmp_path: Path) -> str:
    b = tmp_path / "bin" / "llama-server"
    b.parent.mkdir(parents=True, exist_ok=True)
    b.write_text("#!/bin/sh\nexit 0\n")
    b.chmod(0o755)
    return str(b)


def _gguf(tmp_path: Path, mb: int = 1) -> str:
    g = tmp_path / "model-Q8_0.gguf"
    g.write_bytes(b"\0" * (mb * 1024 * 1024))
    return str(g)


@pytest.fixture(autouse=True)
def _no_known_binary(monkeypatch, tmp_path):
    """The Spark's real llama-server must never resolve in unit tests."""
    monkeypatch.setattr(launcher, "_KNOWN_LLAMA_SERVER", str(tmp_path / "nope"))
    monkeypatch.delenv("FIELDKIT_LLAMA_SERVER", raising=False)
    monkeypatch.setattr("shutil.which", lambda *_a, **_k: None)


@pytest.fixture(autouse=True)
def _no_real_discovery(monkeypatch):
    """Unit tests never probe real ports; discovery is injected per test."""
    monkeypatch.setattr(lanes, "discover", lambda *a, **k: [])


# --------------------------------------------------------------------------- #
# recipes
# --------------------------------------------------------------------------- #
def test_load_recipes_missing_file_is_empty():
    assert launcher.load_lane_recipes() == {}


def test_load_recipes_bad_json_is_typed(tmp_path):
    p = tmp_path / "lane-registry" / "lane-recipes.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("{nope")
    with pytest.raises(LaunchRefused) as e:
        launcher.load_lane_recipes()
    assert e.value.reason == "recipe_malformed"


def test_validate_recipe_rejects_relative_gguf(tmp_path):
    _write_recipes(tmp_path, [{"name": "x", "gguf_path": "rel/model.gguf", "port": 8091}])
    with pytest.raises(LaunchRefused) as e:
        launcher.launch_lane("x")
    assert e.value.reason == "recipe_malformed"
    assert "absolute" in str(e.value)


def test_validate_recipe_warm_timeout_ceiling(tmp_path):
    rec = launcher._validate_recipe(
        {"name": "x", "gguf_path": "/abs/m.gguf", "port": 8091, "warm_timeout": 900}
    )
    assert rec["warm_timeout"] == launcher.WARM_TIMEOUT_CEILING_S


def test_recipe_summaries_card_safe(tmp_path):
    gguf = _gguf(tmp_path)
    _write_recipes(
        tmp_path,
        [
            {"name": "good", "gguf_path": gguf, "port": 8091},
            {"name": "gone", "gguf_path": "/no/such.gguf", "port": 8092},
            {"name": "bad", "gguf_path": "rel.gguf", "port": 8093},
        ],
    )
    by_name = {s["name"]: s for s in launcher.recipe_summaries()}
    assert by_name["good"]["valid"] and by_name["good"]["gguf_present"]
    # the card digest carries the FILENAME, never the absolute path
    assert by_name["good"]["model_file"] == "model-Q8_0.gguf"
    assert gguf not in json.dumps(by_name["good"])
    assert by_name["gone"]["valid"] and not by_name["gone"]["gguf_present"]
    assert by_name["bad"]["valid"] is False


# --------------------------------------------------------------------------- #
# pre-flight refusals, in the locked order
# --------------------------------------------------------------------------- #
def test_refuses_unknown_recipe(tmp_path):
    _write_recipes(tmp_path, [])
    with pytest.raises(LaunchRefused) as e:
        launcher.launch_lane("kepler")
    assert e.value.reason == "recipe_not_found"


def test_refuses_binary_absent_before_gguf_check(tmp_path):
    # gguf also absent — but the binary gate comes FIRST (cheapest hard gate;
    # a doomed launch must fail before any destructive teardown_first).
    _write_recipes(tmp_path, [{"name": "x", "gguf_path": "/no/m.gguf", "port": 8091}])
    with pytest.raises(LaunchRefused) as e:
        launcher.launch_lane("x")
    assert e.value.reason == "binary_absent"
    assert "exit-127" in str(e.value)


def test_refuses_gguf_absent(tmp_path, monkeypatch):
    monkeypatch.setenv("FIELDKIT_LLAMA_SERVER", _fake_binary(tmp_path))
    _write_recipes(tmp_path, [{"name": "x", "gguf_path": "/no/m.gguf", "port": 8091}])
    with pytest.raises(LaunchRefused) as e:
        launcher.launch_lane("x")
    assert e.value.reason == "gguf_absent"


def test_refuses_oom_envelope(tmp_path, monkeypatch):
    monkeypatch.setenv("FIELDKIT_LLAMA_SERVER", _fake_binary(tmp_path))
    _write_recipes(
        tmp_path, [{"name": "x", "gguf_path": _gguf(tmp_path), "port": 8091}]
    )
    monkeypatch.setattr(launcher, "_meminfo_gb", lambda: (128.0, 2.0))
    with pytest.raises(LaunchRefused) as e:
        launcher.launch_lane("x")
    assert e.value.reason == "oom_envelope"
    assert "MemAvailable" in str(e.value)


def test_envelope_estimate_is_ctx_sensitive():
    small = launcher.estimate_lane_gb(8_700_000_000, 2048)
    big = launcher.estimate_lane_gb(8_700_000_000, 32768)
    assert big > small
    # Kepler-Q8-shaped: ~8.7 GB weights @ 8k ctx lands well under a free box
    assert launcher.estimate_lane_gb(8_700_000_000, 8192) < 20


def test_refuses_lane_resident_without_teardown_first(tmp_path, monkeypatch):
    monkeypatch.setenv("FIELDKIT_LLAMA_SERVER", _fake_binary(tmp_path))
    _write_recipes(
        tmp_path, [{"name": "x", "gguf_path": _gguf(tmp_path), "port": 8091}]
    )
    monkeypatch.setattr(launcher, "_meminfo_gb", lambda: (128.0, 100.0))
    monkeypatch.setattr(
        lanes,
        "discover",
        lambda *a, **k: [{"model": "other.gguf", "port": 8080, "base_url": "http://127.0.0.1:8080/v1"}],
    )
    with pytest.raises(LaunchRefused) as e:
        launcher.launch_lane("x")
    assert e.value.reason == "lane_resident"
    assert "other.gguf:8080" in str(e.value)


def test_discovery_sweep_includes_recipe_port(tmp_path, monkeypatch):
    """A lane on a port OUTSIDE the default sweep must still trip ONE-LANE
    when it is the launch target (P0-3 — the off-sweep blind spot)."""
    monkeypatch.setenv("FIELDKIT_LLAMA_SERVER", _fake_binary(tmp_path))
    _write_recipes(
        tmp_path, [{"name": "x", "gguf_path": _gguf(tmp_path), "port": 9377}]
    )
    monkeypatch.setattr(launcher, "_meminfo_gb", lambda: (128.0, 100.0))
    seen_ports: list[list[int]] = []

    def _discover(ports=None, **_k):
        seen_ports.append(list(ports or []))
        return []

    monkeypatch.setattr(lanes, "discover", _discover)
    # port 9377 free? bind-check runs after discovery; let it refuse there.
    with pytest.raises(LaunchRefused) as e:
        # spawn would need a real binary exec — make the port look busy instead
        monkeypatch.setattr(launcher, "_tcp_connectable", lambda *a, **k: True)
        launcher.launch_lane("x")
    assert e.value.reason == "port_busy"
    assert 9377 in seen_ports[0]


def test_refuses_when_lock_held(tmp_path, monkeypatch):
    monkeypatch.setenv("FIELDKIT_LLAMA_SERVER", _fake_binary(tmp_path))
    _write_recipes(
        tmp_path, [{"name": "x", "gguf_path": _gguf(tmp_path), "port": 8091}]
    )
    lock = tmp_path / "lane-registry" / launcher.LAUNCH_LOCK_NAME
    lock.parent.mkdir(parents=True, exist_ok=True)
    holder = open(lock, "a+")
    try:
        fcntl.flock(holder.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        with pytest.raises(LaunchRefused) as e:
            launcher.launch_lane("x")
        assert e.value.reason == "launch_in_progress"
    finally:
        holder.close()


# --------------------------------------------------------------------------- #
# teardown — honest revert + the no-kill guards
# --------------------------------------------------------------------------- #
def test_teardown_already_dead_reverts_state(tmp_path):
    lanes.save_active_lane({"model": "m", "port": 9533, "base_url": "x"})
    launcher._write_owner(9533, {"pid": 999_999_999, "port": 9533})
    out = launcher.teardown_lane(9533)
    assert out["already_dead"] is True
    assert out["registry_cleared"] is True
    assert lanes.load_active_lane() is None
    assert launcher.read_lane_owner(9533) is None


def test_teardown_leaves_unrelated_registry(tmp_path):
    lanes.save_active_lane({"model": "m", "port": 8080, "base_url": "x"})
    out = launcher.teardown_lane(9533)
    assert out["registry_cleared"] is False
    assert lanes.load_active_lane()["port"] == 8080


def test_teardown_pid_reuse_never_kills(tmp_path):
    """An owner file whose pid now belongs to ANOTHER process (this very test
    process — alive, python argv, no gguf) must not be killed (P1-2)."""
    me = os.getpid()
    launcher._write_owner(
        9533, {"pid": me, "pgid": os.getpgid(me), "gguf_path": "/x/m.gguf", "port": 9533}
    )
    out = launcher.teardown_lane(9533)
    assert any("reused" in n for n in out["notes"] or [])
    # we are alive to assert it
    assert out["already_dead"] is True


def test_owner_cmdline_match_contract():
    owner = {"kind": "llama-server", "gguf_path": "/m/k.gguf"}
    good = ["/opt/llama.cpp/bin/llama-server", "-m", "/m/k.gguf", "--port", "8091"]
    assert launcher._owner_cmdline_matches(owner, good)
    assert not launcher._owner_cmdline_matches(owner, [sys.executable, "-m", "pytest"])
    # NUL-split argv entries — the gguf must match as a whole entry
    assert not launcher._owner_cmdline_matches(owner, ["/bin/llama-server", "-m", "/m/other.gguf"])


def test_teardown_failed_when_port_survives(tmp_path, monkeypatch):
    """A port that still answers after the kill chain must raise, never report
    a false 'freed' (the released gate is observed, not asserted)."""
    srv_sock = socket.socket()
    srv_sock.bind(("127.0.0.1", 0))
    # generous backlog — every unaccepted probe connect must still SYN-ACK,
    # or the port would dishonestly look dead to the released gate
    srv_sock.listen(32)
    port = srv_sock.getsockname()[1]
    monkeypatch.setattr(launcher, "_PORT_DEAD_GRACE_S", 1.0)
    try:
        with pytest.raises(LaunchRefused) as e:
            launcher.teardown_lane(port)
        assert e.value.reason == "teardown_failed"
    finally:
        srv_sock.close()
