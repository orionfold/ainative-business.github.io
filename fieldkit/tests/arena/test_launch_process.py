# Copyright 2026 Manav Sehgal
# SPDX-License-Identifier: Apache-2.0
"""AE-31 — REAL-process launch/teardown tests (the mock-blind antidote).

Precedent: ``test_signal_teardown_process.py`` (BUG-2). A python stub named
``llama-server`` really gets ``Popen``-spawned detached by the launcher, really
serves ``/health`` + ``/v1/models`` + ``/props``, really gets discovered by
``lanes.probe_port``, and really dies under the teardown kill chain — proving
the detach (``start_new_session``), the owner-file lifecycle, the warm-poll
fast-fail on a crashed binary, and the observed released gate, none of which a
monkeypatched Popen can exercise (``dogfood_finds_mock_blind_bugs``).
"""

from __future__ import annotations

import json
import os
import socket
import time
from pathlib import Path

import pytest

from fieldkit.arena import lanes, launcher
from fieldkit.arena.launcher import LaunchRefused

# A real llama-server-shaped stub: parses --port/-m from argv, answers the
# three endpoints discovery reads. STUB_MODE=crash exits 3 at once;
# STUB_MODE=never_warm listens on nothing and sleeps.
_STUB = """#!/usr/bin/env python3
import json, os, sys, time
from http.server import BaseHTTPRequestHandler, HTTPServer

mode = os.environ.get("STUB_MODE", "serve")
if mode == "crash":
    sys.stderr.write("stub: simulated load failure\\n")
    sys.exit(3)

argv = sys.argv[1:]
port = int(argv[argv.index("--port") + 1])
gguf = argv[argv.index("-m") + 1]

if mode == "never_warm":
    time.sleep(600)
    sys.exit(0)

class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass
    def do_GET(self):
        if self.path == "/health":
            body = b"{}"
        elif self.path == "/v1/models":
            body = json.dumps({"data": [{"id": "stub-model"}]}).encode()
        elif self.path == "/props":
            body = json.dumps({"model_path": gguf, "n_ctx": 512}).encode()
        else:
            self.send_response(404); self.end_headers(); return
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

HTTPServer(("127.0.0.1", port), H).serve_forever()
"""


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


@pytest.fixture()
def rig(tmp_path, monkeypatch):
    """A launchable rig: stub binary on FIELDKIT_LLAMA_SERVER + a recipe whose
    port rides FK_ARENA_LANE_PORTS so real discovery sweeps exactly it."""
    stub = tmp_path / "bin" / "llama-server"
    stub.parent.mkdir(parents=True, exist_ok=True)
    stub.write_text(_STUB)
    stub.chmod(0o755)
    monkeypatch.setenv("FIELDKIT_LLAMA_SERVER", str(stub))

    gguf = tmp_path / "model-Q8_0.gguf"
    gguf.write_bytes(b"\0" * (1024 * 1024))

    port = _free_port()
    monkeypatch.setenv("FK_ARENA_LANE_PORTS", str(port))
    recipes = tmp_path / "lane-registry" / "lane-recipes.json"
    recipes.parent.mkdir(parents=True, exist_ok=True)
    recipes.write_text(
        json.dumps(
            [{"name": "stub", "gguf_path": str(gguf), "port": port, "warm_timeout": 20}]
        )
    )
    yield {"port": port, "gguf": str(gguf)}
    # belt-and-braces: never leak a stub past the test
    try:
        launcher.teardown_lane(port)
    except LaunchRefused:
        pass


def test_launch_discover_teardown_end_to_end(rig):
    port = rig["port"]
    out = launcher.launch_lane("stub")
    try:
        assert out["model"] == "stub-model"
        assert out["port"] == port
        assert out["warm_seconds"] is not None

        # detached + owned: the owner file records the live pid/pgid
        owner = launcher.read_lane_owner(port)
        assert owner and owner["pid"] == out["pid"]
        assert owner["pgid"] == owner["pid"]  # start_new_session ⇒ group leader
        assert owner.get("warm_at")

        # REAL discovery sees it (the same probe the rail reads)
        seen = lanes.probe_port(port)
        assert seen and seen["model"] == "stub-model"

        # select_on_warm (default) anchored the run — the AE-19 shape
        reg = lanes.load_active_lane()
        assert reg and reg["port"] == port and reg.get("set_at")
    finally:
        down = launcher.teardown_lane(port)

    # the released gate, observed: port refused + group empty + honest revert
    assert down["port_dead"] is True
    assert down["pgid_empty"] is True
    assert down["registry_cleared"] is True
    assert launcher.read_lane_owner(port) is None
    assert lanes.probe_port(port) is None


def test_second_launch_refused_lane_resident(rig, tmp_path):
    port = rig["port"]
    launcher.launch_lane("stub")
    try:
        # a second recipe targeting another port still trips ONE-LANE
        port2 = _free_port()
        recipes = tmp_path / "lane-registry" / "lane-recipes.json"
        recipes.write_text(
            json.dumps(
                [
                    {"name": "stub", "gguf_path": rig["gguf"], "port": port, "warm_timeout": 20},
                    {"name": "two", "gguf_path": rig["gguf"], "port": port2, "warm_timeout": 20},
                ]
            )
        )
        with pytest.raises(LaunchRefused) as e:
            launcher.launch_lane("two")
        assert e.value.reason == "lane_resident"
        assert "stub-model" in str(e.value)
    finally:
        launcher.teardown_lane(port)


def test_teardown_first_replaces_resident_lane(rig, tmp_path):
    port = rig["port"]
    launcher.launch_lane("stub")
    port2 = _free_port()
    os.environ["FK_ARENA_LANE_PORTS"] = f"{port},{port2}"
    recipes = tmp_path / "lane-registry" / "lane-recipes.json"
    recipes.write_text(
        json.dumps(
            [
                {"name": "stub", "gguf_path": rig["gguf"], "port": port, "warm_timeout": 20},
                {"name": "two", "gguf_path": rig["gguf"], "port": port2, "warm_timeout": 20},
            ]
        )
    )
    out = launcher.launch_lane("two", teardown_first=True)
    try:
        assert out["port"] == port2
        assert out["teardown_first"] and out["teardown_first"][0]["port"] == port
        # the old lane is genuinely gone; the new one genuinely serves
        assert lanes.probe_port(port) is None
        assert lanes.probe_port(port2)["model"] == "stub-model"
        # the anchor moved with the replacement
        assert lanes.load_active_lane()["port"] == port2
    finally:
        launcher.teardown_lane(port2)


def test_crashed_binary_fast_fails_with_log_tail(rig, monkeypatch):
    monkeypatch.setenv("STUB_MODE", "crash")
    t0 = time.monotonic()
    with pytest.raises(LaunchRefused) as e:
        launcher.launch_lane("stub")
    assert e.value.reason == "launch_crashed"
    assert "exited 3" in str(e.value)
    assert "simulated load failure" in str(e.value)  # the log tail rides the error
    assert time.monotonic() - t0 < 10  # fast-fail, not the full warm_timeout
    assert launcher.read_lane_owner(rig["port"]) is None  # no orphan owner file


def test_warm_timeout_is_non_destructive(rig, tmp_path, monkeypatch):
    """A timeout leaves the (maybe-still-loading) process + owner file in place
    — honest 'left loading', the ONE-LANE guard holds until a teardown."""
    monkeypatch.setenv("STUB_MODE", "never_warm")
    recipes = tmp_path / "lane-registry" / "lane-recipes.json"
    recipes.write_text(
        json.dumps(
            [{"name": "stub", "gguf_path": rig["gguf"], "port": rig["port"], "warm_timeout": 2}]
        )
    )
    with pytest.raises(LaunchRefused) as e:
        launcher.launch_lane("stub")
    assert e.value.reason == "warm_timeout"
    owner = launcher.read_lane_owner(rig["port"])
    assert owner is not None  # kept
    # the process is still alive (left loading) — and teardown reaps it
    st = launcher._proc_stat(owner["pid"])
    assert st and st[0] != "Z"
    down = launcher.teardown_lane(rig["port"])
    assert down["port_dead"] is True
    # dead or zombie (we are the parent and never wait() the detached child)
    st = launcher._proc_stat(owner["pid"])
    assert st is None or st[0] == "Z"


def test_abort_sentinel_stops_warm_poll_only(rig, tmp_path, monkeypatch):
    """The BUG-2 wiring: aborting the warm-poll fails the JOB but never kills
    the detached lane — discovery/teardown still own it after."""
    monkeypatch.setenv("STUB_MODE", "never_warm")
    polls = {"n": 0}

    def should_abort():
        polls["n"] += 1
        return polls["n"] >= 2

    with pytest.raises(LaunchRefused) as e:
        launcher.launch_lane("stub", should_abort=should_abort)
    assert e.value.reason == "aborted"
    owner = launcher.read_lane_owner(rig["port"])
    assert owner is not None
    os.kill(owner["pid"], 0)  # the detached process survived the abort
    launcher.teardown_lane(rig["port"])
