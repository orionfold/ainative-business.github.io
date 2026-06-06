# Copyright 2026 Manav Sehgal
# SPDX-License-Identifier: Apache-2.0
"""BUG-2 — the real-process SIGTERM test (the mock-blind gap, closed).

The offline G1 tests called ``_trip_running_eval_sentinels()`` directly and
never exercised the signal→drain→lifespan ordering, so the **circular wait**
shipped: uvicorn's graceful shutdown waits for the in-flight eval
BackgroundTask *before* running lifespan shutdown, but the eval only aborts
once the sentinel — written by lifespan shutdown — exists. Found live in the
e2e operator-smoke (2026-06-06, a real metered R1 eval).

This test reproduces the exact topology in a real subprocess: a sidecar with a
``running`` eval row + a BackgroundTask that (like a guarded eval's row-loop)
only finishes when the abort sentinel appears. SIGTERM must (a) land the
sentinel promptly — the signal-handler trip, NOT the lifespan one — and (b) let
the process drain and exit cleanly. Without the fix, (a) never happens and the
process hangs in graceful-drain until killed.
"""

from __future__ import annotations

import os
import signal
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(os.name != "posix", reason="POSIX signals required")


_RUNNER = '''
import json, sys, time
from pathlib import Path

port, db, owner_pid, jobfile = int(sys.argv[1]), sys.argv[2], int(sys.argv[3]), sys.argv[4]

from fieldkit.arena import jobs as jobs_mod
from fieldkit.arena.jobs import JobKind, JobStatus
from fieldkit.arena.store import ArenaStore

store = ArenaStore(db)
store.initialize()
store.upsert_lane({"id": "cloud", "kind": "OpenRouterLane", "model": "m", "port": 0,
                   "base_url": "", "recommended": 0})
job_id = jobs_mod.enqueue_job(store, JobKind.EVAL_RERUN, {"lane_id": "cloud", "bench_id": "b1"})
store.update_job(job_id, status=JobStatus.RUNNING)
# Owner-stamp with the parent's (live) pid so the startup reconciler leaves the
# row alone — we need it still `running` when the signal lands.
stamp = jobs_mod.job_owner_path(job_id)
stamp.parent.mkdir(parents=True, exist_ok=True)
stamp.write_text(json.dumps({"pid": owner_pid, "kind": "eval_rerun"}))
store.close()
Path(jobfile).write_text(job_id)

from fastapi import BackgroundTasks

from fieldkit.arena.guardrail import eval_sentinel_for
from fieldkit.arena.server import create_app

app = create_app(db=db, repo_root=str(Path(db).parent), telemetry_interval=2.0)


def _emulated_guarded_eval():
    # The guarded eval row-loop: only stops once the abort sentinel exists.
    # This is what holds uvicorn's graceful drain open.
    s = eval_sentinel_for(job_id)
    deadline = time.time() + 30.0
    while not s.exists() and time.time() < deadline:
        time.sleep(0.05)


@app.post("/test/hold-drain")
async def hold_drain(background_tasks: BackgroundTasks):
    background_tasks.add_task(_emulated_guarded_eval)
    return {"ok": True}


import uvicorn

uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")
'''


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _wait_http(url: str, timeout_s: float) -> None:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2):
                return
        except (urllib.error.URLError, ConnectionError, OSError):
            time.sleep(0.1)
    raise TimeoutError(f"server never answered at {url}")


def test_real_sigterm_trips_g1_while_drain_held(tmp_path: Path) -> None:
    port = _free_port()
    db = tmp_path / "arena.db"
    jobfile = tmp_path / "job_id.txt"
    sentinel_dir = tmp_path / "sentinels"
    script = tmp_path / "runner.py"
    script.write_text(_RUNNER)
    env = {
        **os.environ,
        "FK_EVAL_SENTINEL_DIR": str(sentinel_dir),
        "FK_ARENA_OWNER_DIR": str(tmp_path / "owners"),
    }
    proc = subprocess.Popen(
        [sys.executable, str(script), str(port), str(db), str(os.getpid()), str(jobfile)],
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )
    try:
        _wait_http(f"http://127.0.0.1:{port}/healthz", 30)
        job_id = jobfile.read_text().strip()
        assert job_id, "runner never seeded the job"
        # Start the drain-holding BackgroundTask (the emulated guarded eval).
        req = urllib.request.Request(f"http://127.0.0.1:{port}/test/hold-drain", method="POST")
        with urllib.request.urlopen(req, timeout=5) as r:
            assert r.status == 200
        time.sleep(0.4)  # let the background task begin polling

        proc.send_signal(signal.SIGTERM)

        # (a) The sentinel must land at SIGNAL time — were it only written by
        # lifespan shutdown, the drain (held by the task above) would never end.
        sentinel = sentinel_dir / f"abort-{job_id}.json"
        deadline = time.time() + 8.0
        while not sentinel.exists() and time.time() < deadline:
            time.sleep(0.05)
        assert sentinel.exists(), "G1 sentinel not tripped at signal time (BUG-2 regression)"

        # (b) With the sentinel down, the emulated eval finishes, the drain
        # completes, and the process exits on its own. uvicorn ≥0.29 restores
        # the original disposition and re-raises the captured SIGTERM after a
        # *graceful* shutdown (correct Unix signal-death reporting), so
        # ``-SIGTERM`` is the clean-exit code; 0 covers older uvicorns.
        proc.wait(timeout=15)
        assert proc.returncode in (0, -signal.SIGTERM), (
            proc.returncode,
            proc.stderr.read().decode()[-2000:],
        )
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait(timeout=10)
