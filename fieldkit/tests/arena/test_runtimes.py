# Copyright 2026 Manav Sehgal
# SPDX-License-Identifier: Apache-2.0
"""AE-30 (arena-enhancements-v2 cut 3) — runtime readiness, the READ-ONLY half
of AF-20.

The roster OBSERVES the runtimes the build/serve stages depend on: serve lanes
via the AE-18 discovery sweep, training containers via one `docker inspect`,
pgvector/embedder via TCP. These tests fake every probe (no docker, no sockets)
and pin the projection contract: every expected runtime appears with an honest
state; a box without docker degrades to `unknown`, never a 500; the endpoint is
cached (AE-R7) and read-only (no POST routes exist).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

fastapi = pytest.importorskip("fastapi")

from fastapi.testclient import TestClient  # noqa: E402

from fieldkit.arena import server as srv  # noqa: E402
from fieldkit.arena.server import create_app  # noqa: E402


def _app(tmp_path: Path):
    return create_app(
        repo_root=tmp_path,
        db=str(tmp_path / "no-such.db"),
        telemetry_interval=2.0,
    )


@pytest.fixture(autouse=True)
def _fresh_cache(monkeypatch):
    """Each test sees a cold runtimes cache (module-level, 8 s TTL)."""
    monkeypatch.setattr(srv, "_runtimes_cache", {"t": 0.0, "v": None})


def _fake_probes(
    monkeypatch,
    *,
    lanes=(),
    containers=None,
    tcp_up=(),
):
    monkeypatch.setattr(
        "fieldkit.arena.lanes.discover_cached", lambda *a, **k: list(lanes)
    )
    monkeypatch.setattr(
        srv, "_docker_container_states",
        lambda names, timeout=1.5: {
            n: (containers or {}).get(n, "absent") for n in names
        },
    )
    monkeypatch.setattr(
        srv, "_tcp_up", lambda port, host="127.0.0.1", timeout=0.3: port in tcp_up
    )


def test_runtimes_idle_box(tmp_path, monkeypatch):
    _fake_probes(monkeypatch, containers={"nemo-train": "absent", "ps-train": "stopped"})
    with TestClient(_app(tmp_path)) as client:
        body = client.get("/api/runtimes").json()
        assert body["available"] is True
        by_key = {r["key"]: r for r in body["runtimes"]}
        # No lane resident → the honest empty row, not an omission.
        assert by_key["lane"]["state"] == "down"
        assert "GPU lane free" in by_key["lane"]["detail"]
        assert by_key["container:nemo-train"]["state"] == "absent"
        assert by_key["container:ps-train"]["state"] == "stopped"
        assert by_key["tcp:5432"]["state"] == "down"
        assert by_key["tcp:8001"]["state"] == "down"
        assert body["up"] == 0


def test_runtimes_serving_box(tmp_path, monkeypatch):
    _fake_probes(
        monkeypatch,
        lanes=[{"port": 8091, "model": "model-Q8_0.gguf", "kind": "LlamaServerLane"}],
        containers={"nemo-train": "up", "ps-train": "stopped"},
        tcp_up={5432},
    )
    with TestClient(_app(tmp_path)) as client:
        body = client.get("/api/runtimes").json()
        by_key = {r["key"]: r for r in body["runtimes"]}
        assert by_key["lane:8091"]["state"] == "up"
        assert by_key["lane:8091"]["label"] == "model-Q8_0.gguf"
        assert "lane" not in by_key  # a resident lane replaces the empty row
        assert by_key["container:nemo-train"]["state"] == "up"
        assert by_key["tcp:5432"]["state"] == "up"
        assert body["up"] == 3


def test_runtimes_discovered_8001_suppresses_tcp_row(tmp_path, monkeypatch):
    """An embedder answering the lane sweep on :8001 is a lane entry — the
    fixed TCP expectation row must not duplicate it."""
    _fake_probes(
        monkeypatch,
        lanes=[{"port": 8001, "model": "nv-embedqa", "kind": "OpenAICompatLane"}],
    )
    with TestClient(_app(tmp_path)) as client:
        keys = [r["key"] for r in client.get("/api/runtimes").json()["runtimes"]]
        assert "lane:8001" in keys
        assert "tcp:8001" not in keys


def test_runtimes_docker_unavailable_degrades_to_unknown(tmp_path, monkeypatch):
    _fake_probes(monkeypatch)
    monkeypatch.setattr(
        srv, "_docker_container_states",
        lambda names, timeout=1.5: {n: "unknown" for n in names},
    )
    with TestClient(_app(tmp_path)) as client:
        r = client.get("/api/runtimes")
        assert r.status_code == 200
        by_key = {x["key"]: x for x in r.json()["runtimes"]}
        assert by_key["container:nemo-train"]["state"] == "unknown"


def test_runtimes_container_roster_env_override(tmp_path, monkeypatch):
    _fake_probes(monkeypatch, containers={"my-train": "up"})
    monkeypatch.setenv("FK_ARENA_RUNTIME_CONTAINERS", "my-train")
    with TestClient(_app(tmp_path)) as client:
        keys = [r["key"] for r in client.get("/api/runtimes").json()["runtimes"]]
        assert "container:my-train" in keys
        assert "container:nemo-train" not in keys


def test_runtimes_cached_between_calls(tmp_path, monkeypatch):
    calls = {"n": 0}

    def _counting(names, timeout=1.5):
        calls["n"] += 1
        return {n: "absent" for n in names}

    _fake_probes(monkeypatch)
    monkeypatch.setattr(srv, "_docker_container_states", _counting)
    with TestClient(_app(tmp_path)) as client:
        client.get("/api/runtimes")
        client.get("/api/runtimes")
        assert calls["n"] == 1  # AE-R7 — second hit served from the 8 s cache


def test_docker_inspect_parser_contract():
    """The stdout parser: found containers print `/name true|false`; missing
    names print nothing (exit code never trusted)."""
    import subprocess

    class _P:
        stdout = "/nemo-train true\n/ps-train false\n"

    def _fake_run(*a, **k):
        return _P()

    real = subprocess.run
    subprocess.run = _fake_run
    try:
        states = srv._docker_container_states(["nemo-train", "ps-train", "ghost"])
    finally:
        subprocess.run = real
    assert states == {"nemo-train": "up", "ps-train": "stopped", "ghost": "absent"}


# ---------------------------------------------------------------------------
# AE-32 (v2 cut 4) — guarded container arm/teardown (the AF-20 act half)
# ---------------------------------------------------------------------------
#
# The endpoint acts only on roster containers, validates the transition against
# the OBSERVED state, builds `docker run` argv from the operator-authored
# recipe file (never shell-interpolated), and returns the RE-OBSERVED state.


def _fake_action_box(monkeypatch, states, recipes=None, tmp_path=None):
    """States is a mutable {name: state}; the fake docker mutates it so the
    post-action re-inspect observes the transition."""
    calls = []

    def _inspect(names, timeout=1.5):
        return {n: states.get(n, "absent") for n in names}

    def _run(argv, capture_output=True, text=True, timeout=None):
        calls.append(argv)
        name = argv[argv.index("--name") + 1] if "--name" in argv else argv[-1]
        if argv[1] == "start":
            states[argv[2]] = "up"
        elif argv[1] == "stop":
            states[argv[2]] = "stopped"
        elif argv[1] == "run":
            states[name] = "up"

        class P:
            stdout = "ok"
            stderr = ""

        return P()

    monkeypatch.setattr(srv, "_docker_container_states", _inspect)
    monkeypatch.setattr(srv, "_tcp_up", lambda *a, **k: False)  # hermetic roster reads
    import subprocess

    monkeypatch.setattr(subprocess, "run", _run)
    if recipes is not None and tmp_path is not None:
        p = tmp_path / "runtime-recipes.json"
        p.write_text(json.dumps(recipes))
        monkeypatch.setenv("FK_ARENA_RUNTIME_RECIPES", str(p))
    return calls


def test_container_action_requires_confirm(tmp_path, monkeypatch):
    with TestClient(_app(tmp_path)) as client:
        r = client.post(
            "/api/runtimes/container", json={"name": "ps-train", "action": "start"}
        )
        assert r.status_code == 422
        assert "confirm" in r.json()["detail"]


def test_container_action_rejects_off_roster(tmp_path, monkeypatch):
    _fake_action_box(monkeypatch, {"ps-train": "stopped"})
    with TestClient(_app(tmp_path)) as client:
        r = client.post(
            "/api/runtimes/container",
            json={"name": "evil-box", "action": "start", "confirm": True},
        )
        assert r.status_code == 409
        assert "roster" in r.json()["detail"]


def test_container_start_observes_transition(tmp_path, monkeypatch):
    states = {"ps-train": "stopped", "nemo-train": "absent"}
    calls = _fake_action_box(monkeypatch, states)
    with TestClient(_app(tmp_path)) as client:
        r = client.post(
            "/api/runtimes/container",
            json={"name": "ps-train", "action": "start", "confirm": True},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["before"] == "stopped" and body["after"] == "up" and body["ok"]
        assert calls == [["docker", "start", "ps-train"]]
        # the roster cache was invalidated — the next read re-observes
        roster = client.get("/api/runtimes").json()
        by_key = {x["key"]: x for x in roster["runtimes"]}
        assert by_key["container:ps-train"]["state"] == "up"


def test_container_start_on_absent_points_at_run(tmp_path, monkeypatch):
    _fake_action_box(monkeypatch, {"nemo-train": "absent"})
    with TestClient(_app(tmp_path)) as client:
        r = client.post(
            "/api/runtimes/container",
            json={"name": "nemo-train", "action": "start", "confirm": True},
        )
        assert r.status_code == 409
        assert "run" in r.json()["detail"]


def test_container_run_needs_recipe(tmp_path, monkeypatch):
    _fake_action_box(monkeypatch, {"nemo-train": "absent"})
    with TestClient(_app(tmp_path)) as client:
        r = client.post(
            "/api/runtimes/container",
            json={"name": "nemo-train", "action": "run", "confirm": True},
        )
        assert r.status_code == 409
        assert "recipe" in r.json()["detail"]


def test_container_run_builds_argv_from_recipe(tmp_path, monkeypatch):
    states = {"nemo-train": "absent", "ps-train": "stopped"}
    calls = _fake_action_box(
        monkeypatch,
        states,
        recipes={
            "nemo-train": {
                "image": "nvcr.io/nvidia/nemo:26.04.00",
                "gpus": "all",
                "ipc": "host",
                "binds": ["/home/nvidia:/home/nvidia"],
                "cmd": ["sleep", "infinity"],
            }
        },
        tmp_path=tmp_path,
    )
    with TestClient(_app(tmp_path)) as client:
        r = client.post(
            "/api/runtimes/container",
            json={"name": "nemo-train", "action": "run", "confirm": True},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["before"] == "absent" and body["after"] == "up" and body["ok"]
    assert calls == [
        [
            "docker", "run", "-d", "--name", "nemo-train",
            "--gpus", "all", "--ipc", "host",
            "-v", "/home/nvidia:/home/nvidia",
            "nvcr.io/nvidia/nemo:26.04.00", "sleep", "infinity",
        ]
    ]


def test_container_stop_needs_running(tmp_path, monkeypatch):
    _fake_action_box(monkeypatch, {"ps-train": "stopped"})
    with TestClient(_app(tmp_path)) as client:
        r = client.post(
            "/api/runtimes/container",
            json={"name": "ps-train", "action": "stop", "confirm": True},
        )
        assert r.status_code == 409
