# Copyright 2026 Manav Sehgal
# SPDX-License-Identifier: Apache-2.0
"""Tests for `fieldkit.arena.server` — M3 surface.

Covers the FastAPI app factory, the three M3 GET endpoints, and the
`TelemetryHub` reference-counter contract (sampler starts on first
subscriber, stops on last). The SSE endpoint is exercised via
`httpx.AsyncClient` + a short-window `stream` cycle; we never sit on
the live stream for more than a fraction of a second.
"""

from __future__ import annotations

import asyncio
import json
import os
import textwrap
import threading
import time
from pathlib import Path

import pytest

# Skip the whole module cleanly if the `arena` extra isn't installed —
# matches how `test_store.py` already guards on `aiosqlite` availability
# patterns. The dev venv always has them; CI installs the extra.
fastapi = pytest.importorskip("fastapi")
httpx = pytest.importorskip("httpx")

from fastapi.testclient import TestClient  # noqa: E402

from fieldkit.arena import (  # noqa: E402
    ARENA_SURFACE_VERSION,
    DEFAULT_ARENA_PORT,
)
from fieldkit.arena.server import (  # noqa: E402
    TelemetryHub,
    _read_active_gpu_lane,
    _read_hermes_lane,
    create_app,
)


@pytest.fixture
def repo_root(tmp_path: Path) -> Path:
    """A fixture repo with the mirror JSON wired up the way M2 writes it."""
    mirror_dir = tmp_path / "src" / "data" / "arena-mirror"
    mirror_dir.mkdir(parents=True)
    (mirror_dir / "leaderboard.json").write_text(
        json.dumps(
            {
                "version": 1,
                "rows": [
                    {
                        "bench_id": "fixture-bench",
                        "lane_id": "fixture-lane-a",
                        "manifest_slug": None,
                        "n_runs": 5,
                        "mean_score": 0.9,
                        "median_tok_per_s": 83.5,
                        "mean_ttft_ms": 460,
                        "human_pref_winrate": None,
                        "last_run_at": "2026-05-28T15:00:00Z",
                    },
                    {
                        "bench_id": "fixture-bench",
                        "lane_id": "fixture-lane-b",
                        "manifest_slug": None,
                        "n_runs": 5,
                        "mean_score": 0.8,
                        "median_tok_per_s": 55.0,
                        "mean_ttft_ms": 700,
                        "human_pref_winrate": None,
                        "last_run_at": "2026-05-28T15:00:00Z",
                    },
                ],
            }
        )
    )
    return tmp_path


# ---------------------------------------------------------------------------
# Hermes config reader
# ---------------------------------------------------------------------------


def test_read_hermes_lane_with_missing_file(tmp_path: Path) -> None:
    missing = tmp_path / "config.yaml"
    assert _read_hermes_lane(hermes_path=missing) is None


def test_read_hermes_lane_with_live_shape(tmp_path: Path) -> None:
    cfg = tmp_path / "hermes-config.yaml"
    cfg.write_text(
        textwrap.dedent(
            """\
            model:
              default: Qwen3-30B-A3B-Q4_K_M
              provider: custom
              base_url: http://127.0.0.1:8080/v1
              context_length: 64000
              max_tokens: 8192
            """
        )
    )
    lane = _read_hermes_lane(hermes_path=cfg)
    assert lane is not None
    assert lane["id"] == "resident-brain"
    assert lane["model"] == "Qwen3-30B-A3B-Q4_K_M"
    assert lane["base_url"] == "http://127.0.0.1:8080/v1"
    assert lane["port"] == 8080
    # provider==custom + 127.0.0.1 → LlamaServerLane.
    assert lane["kind"] == "LlamaServerLane"
    assert lane["context_length"] == 64000
    assert lane["max_tokens"] == 8192
    assert lane["config_path"] == str(cfg)


def test_read_hermes_lane_with_nim_shape(tmp_path: Path) -> None:
    cfg = tmp_path / "hermes-nim.yaml"
    cfg.write_text(
        textwrap.dedent(
            """\
            model:
              default: nemotron-9b-v2
              provider: nim
              base_url: http://127.0.0.1:8000/v1
            """
        )
    )
    lane = _read_hermes_lane(hermes_path=cfg)
    assert lane is not None
    # 127.0.0.1 wins over the provider hint (it's our local NIM container).
    assert lane["kind"] == "LlamaServerLane"
    # Either way the port + base_url surface for the chip.
    assert lane["port"] == 8000


def test_read_hermes_lane_empty_model_block(tmp_path: Path) -> None:
    cfg = tmp_path / "hermes-empty.yaml"
    cfg.write_text("model: {}\nproviders: {}\n")
    assert _read_hermes_lane(hermes_path=cfg) is None


# ---------------------------------------------------------------------------
# TelemetryHub — subscriber bookkeeping
# ---------------------------------------------------------------------------


def test_telemetry_hub_starts_and_stops_with_subscribers() -> None:
    """First subscribe starts the underlying Telemetry; last unsubscribe
    stops it. The spec §4.6 zero-emit-when-idle commitment depends on this."""
    hub = TelemetryHub(interval=2.0)  # slow tick — we just check the counter
    assert hub.subscriber_count == 0
    assert not hub.is_running

    loop = asyncio.new_event_loop()
    try:
        q1, unsub1 = hub.subscribe(loop)
        assert hub.subscriber_count == 1
        assert hub.is_running

        q2, unsub2 = hub.subscribe(loop)
        assert hub.subscriber_count == 2
        assert hub.is_running  # still up

        unsub1()
        assert hub.subscriber_count == 1
        assert hub.is_running  # second subscriber keeps it up

        unsub2()
        assert hub.subscriber_count == 0
        # The pump thread joins on stop; give it a beat.
        time.sleep(0.05)
        assert not hub.is_running

        # Idempotent.
        unsub2()
        assert hub.subscriber_count == 0
        assert not hub.is_running
    finally:
        loop.close()


def test_telemetry_hub_unsubscribe_is_idempotent() -> None:
    hub = TelemetryHub(interval=2.0)
    loop = asyncio.new_event_loop()
    try:
        _q, unsub = hub.subscribe(loop)
        assert hub.is_running
        unsub()
        unsub()  # no-op the second time
        assert hub.subscriber_count == 0
        assert not hub.is_running
    finally:
        loop.close()


def test_telemetry_hub_report_inflight_threads_through_payload() -> None:
    hub = TelemetryHub(interval=2.0)
    hub.report_inflight(
        inflight=True, tok_per_s=83.5, ttft_ms=462.0, lane_id="llama-qwen3-30b"
    )
    payload = hub._build_payload()  # noqa: SLF001
    assert payload["inflight"] is True
    assert payload["tok_per_s"] == 83.5
    assert payload["ttft_ms"] == 462.0
    assert payload["lane_id"] == "llama-qwen3-30b"

    # The idle/disconnect guard flips inflight off but omits the speeds — they
    # must stay *sticky* so the rail keeps showing the last generation's tok/s
    # + TTFT (dimmed) instead of blanking the instant a stream ends.
    hub.report_inflight(inflight=False, lane_id=None)
    payload = hub._build_payload()  # noqa: SLF001
    assert payload["inflight"] is False
    assert payload["tok_per_s"] == 83.5
    assert payload["ttft_ms"] == 462.0
    assert payload["lane_id"] is None

    # A new stream start explicitly clears the speeds (passing None) so the
    # prefill window shows a clean dash, not the prior run's rate as if live.
    hub.report_inflight(inflight=True, tok_per_s=None, ttft_ms=None, lane_id="lane-b")
    payload = hub._build_payload()  # noqa: SLF001
    assert payload["tok_per_s"] is None
    assert payload["ttft_ms"] is None
    assert payload["lane_id"] == "lane-b"


# ---------------------------------------------------------------------------
# AE-15 — telemetry lane-truth (the rail must reflect a LIVE process, not the
# static Hermes config that persists at idle / during an rl_run teardown).
# ---------------------------------------------------------------------------


def test_build_payload_resident_live_false_when_nothing_listening() -> None:
    """A configured resident whose port has no listener → resident_live False
    (so the rail relabels it "Configured Lane · idle", not "Active")."""
    hub = TelemetryHub(interval=2.0)
    # Port 9 (discard) is virtually never bound on a dev box; the TCP connect
    # fails fast → not live. The model name still flows for the label.
    hub._resident_reader = lambda: {  # noqa: SLF001
        "model": "Qwen3-30B-A3B-Q4_K_M",
        "base_url": "http://127.0.0.1:9",
        "port": 9,
    }
    payload = hub._build_payload()  # noqa: SLF001
    assert payload["resident_lane"] == "Qwen3-30B-A3B-Q4_K_M"
    assert payload["resident_live"] is False


def test_build_payload_resident_live_true_when_socket_listening() -> None:
    """A real listening socket at the configured host:port → resident_live True."""
    import socket

    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.bind(("127.0.0.1", 0))
    srv.listen(1)
    port = srv.getsockname()[1]
    try:
        hub = TelemetryHub(interval=2.0)
        hub._resident_reader = lambda: {  # noqa: SLF001
            "model": "resident-brain",
            "base_url": f"http://127.0.0.1:{port}",
            "port": port,
        }
        payload = hub._build_payload()  # noqa: SLF001
        assert payload["resident_live"] is True
    finally:
        srv.close()


def test_build_payload_surfaces_active_rl_lane() -> None:
    """When the arbiter has an rl_run holding the GPU, the active lane (not the
    stale resident config) is what the rail names (AE-15 layer 2)."""
    hub = TelemetryHub(interval=2.0)
    hub._resident_reader = lambda: {"model": "Qwen3-30B-A3B-Q4_K_M", "port": 0}  # noqa: SLF001
    hub._active_lane_reader = lambda: {"model": "Qwen/Qwen3-8B", "where": "rl"}  # noqa: SLF001
    payload = hub._build_payload()  # noqa: SLF001
    assert payload["active_lane_model"] == "Qwen/Qwen3-8B"
    assert payload["active_lane_where"] == "rl"


def test_build_payload_active_lane_none_without_reader() -> None:
    """No injected reader (the M8 default) → no active-lane fields claimed."""
    hub = TelemetryHub(interval=2.0)
    payload = hub._build_payload()  # noqa: SLF001
    assert payload["active_lane_model"] is None
    assert payload["active_lane_where"] is None


def test_read_active_gpu_lane_missing_db_is_none(tmp_path: Path) -> None:
    """Best-effort: a cold/missing db just yields None, never raises."""
    assert _read_active_gpu_lane(str(tmp_path / "nope.db")) is None


# ---------------------------------------------------------------------------
# AE-17 (S7) / G1 — _lifespan trips the eval-abort sentinel on shutdown
# ---------------------------------------------------------------------------


def test_trip_running_eval_sentinels_missing_db_is_zero(tmp_path: Path) -> None:
    from fieldkit.arena.server import _trip_running_eval_sentinels

    assert _trip_running_eval_sentinels(str(tmp_path / "nope.db")) == 0


def test_trip_running_eval_sentinels_touches_running_eval(tmp_path: Path, monkeypatch) -> None:
    """A shutdown trips the sentinel only for *running* eval jobs — the G1 hook
    an in-flight cloud eval's row-loop polls so it aborts cleanly."""
    from fieldkit.arena import jobs
    from fieldkit.arena.guardrail import eval_sentinel_for
    from fieldkit.arena.jobs import JobKind, JobStatus
    from fieldkit.arena.server import _trip_running_eval_sentinels
    from fieldkit.arena.store import ArenaStore

    monkeypatch.setenv("FK_EVAL_SENTINEL_DIR", str(tmp_path / "sentinels"))
    db = tmp_path / "arena.db"
    store = ArenaStore(db)
    store.initialize()
    store.upsert_lane(
        {"id": "cloud", "kind": "OpenRouterLane", "model": "m", "port": 0, "base_url": "", "recommended": 0}
    )
    running_id = jobs.enqueue_job(store, JobKind.EVAL_RERUN, {"lane_id": "cloud", "bench_id": "b1"})
    queued_id = jobs.enqueue_job(store, JobKind.EVAL_RERUN, {"lane_id": "cloud", "bench_id": "b2"})
    rl_id = jobs.enqueue_job(store, JobKind.RL_RUN, {"base": "x", "lane_id": "cloud", "bench_path": "p"})
    store.update_job(running_id, status=JobStatus.RUNNING)
    store.update_job(rl_id, status=JobStatus.RUNNING)  # a running RL job — NOT an eval, must be left alone
    store.close()

    n = _trip_running_eval_sentinels(str(db))
    assert n == 1
    assert eval_sentinel_for(running_id).exists()
    assert not eval_sentinel_for(queued_id).exists()  # queued, not running
    assert not eval_sentinel_for(rl_id).exists()  # rl_run, not eval
    body = json.loads(eval_sentinel_for(running_id).read_text())
    assert body["aborted_by"] == "teardown"


# ---------------------------------------------------------------------------
# BUG-2 — startup reconciler: orphaned in-flight rows land, live-owned rows don't
# ---------------------------------------------------------------------------


def test_reconcile_orphaned_jobs_missing_db_is_zero(tmp_path: Path) -> None:
    from fieldkit.arena.server import _reconcile_orphaned_jobs

    assert _reconcile_orphaned_jobs(str(tmp_path / "nope.db")) == 0


def _seed_inflight_db(tmp_path: Path):
    """A db with: an orphaned running eval, an orphaned running rl_run, a
    running eval owned by a live sibling pid, and an untouched queued eval."""
    import os

    from fieldkit.arena import jobs as jobs_mod
    from fieldkit.arena.jobs import JobKind, JobStatus
    from fieldkit.arena.store import ArenaStore

    db = tmp_path / "arena.db"
    store = ArenaStore(db)
    store.initialize()
    store.upsert_lane(
        {"id": "cloud", "kind": "OpenRouterLane", "model": "m", "port": 0, "base_url": "", "recommended": 0}
    )
    orphan_eval = jobs_mod.enqueue_job(store, JobKind.EVAL_RERUN, {"lane_id": "cloud", "bench_id": "b1"})
    orphan_rl = jobs_mod.enqueue_job(store, JobKind.RL_RUN, {"base": "x", "lane_id": "cloud", "bench_path": "p"})
    owned = jobs_mod.enqueue_job(store, JobKind.EVAL_RERUN, {"lane_id": "cloud", "bench_id": "b2"})
    queued = jobs_mod.enqueue_job(store, JobKind.EVAL_RERUN, {"lane_id": "cloud", "bench_id": "b3"})
    store.update_job(orphan_eval, status=JobStatus.RUNNING)
    store.update_job(orphan_rl, status=JobStatus.RUNNING)
    store.update_job(owned, status=JobStatus.RUNNING)
    # Stamp `owned` with a pid that is alive and not ours: pytest's parent.
    stamp = jobs_mod.job_owner_path(owned)
    stamp.parent.mkdir(parents=True, exist_ok=True)
    stamp.write_text(json.dumps({"pid": os.getppid(), "kind": "eval_rerun"}))
    store.close()
    return db, {"orphan_eval": orphan_eval, "orphan_rl": orphan_rl, "owned": owned, "queued": queued}


def test_reconcile_orphans_land_failed_with_honest_trail(tmp_path: Path) -> None:
    from fieldkit.arena.jobs import JobStatus, job_owner_path
    from fieldkit.arena.server import _reconcile_orphaned_jobs
    from fieldkit.arena.store import ArenaStore

    db, ids = _seed_inflight_db(tmp_path)
    n = _reconcile_orphaned_jobs(str(db))
    assert n == 2  # the two orphans; the live-owned + queued rows untouched

    store = ArenaStore(db)
    rows = {str(r["id"]): r for r in store.list_jobs(limit=50)}
    # Orphaned eval → failed, error names the reconcile, guardrail trail honest
    # (teardown-shaped, 0 scored, reconciled flag for forensics).
    ev = rows[ids["orphan_eval"]]
    assert ev["status"] == JobStatus.FAILED
    assert "orphaned" in ev["error"]
    g = json.loads(ev["result_json"])["guardrail"]
    assert g["aborted_by"] == "teardown"
    assert g["partial"] is True and g["n_scored"] == 0 and g["reconciled"] is True
    # Orphaned rl_run → failed too (a reboot mid-run), no guardrail block.
    rl = rows[ids["orphan_rl"]]
    assert rl["status"] == JobStatus.FAILED and "orphaned" in rl["error"]
    assert rl["result_json"] is None
    # Owned by a live sibling (the cron drain case) — left alone, stamp kept.
    assert rows[ids["owned"]]["status"] == JobStatus.RUNNING
    assert job_owner_path(ids["owned"]).exists()
    # Queued rows are never reconciled.
    assert rows[ids["queued"]]["status"] == JobStatus.QUEUED
    store.close()


def test_reconcile_runs_on_lifespan_startup(tmp_path: Path, repo_root: Path) -> None:
    """The reconciler is wired into app startup — booting the sidecar lands
    orphans without any operator action (the full down+up cycle in the smoke
    left a dead eval `running` forever)."""
    from fieldkit.arena.jobs import JobStatus
    from fieldkit.arena.store import ArenaStore

    db, ids = _seed_inflight_db(tmp_path)
    app = create_app(repo_root=repo_root, db=str(db), telemetry_interval=2.0)
    with TestClient(app) as client:
        assert client.get("/healthz").status_code == 200
    store = ArenaStore(db)
    rows = {str(r["id"]): r for r in store.list_jobs(limit=50)}
    assert rows[ids["orphan_eval"]]["status"] == JobStatus.FAILED
    assert rows[ids["owned"]]["status"] == JobStatus.RUNNING
    store.close()


# ---------------------------------------------------------------------------
# BUG-2 — signal-time sentinel trip (the G1 circular-wait fix)
# ---------------------------------------------------------------------------


def test_signal_teardown_trips_sentinel_and_chains(tmp_path: Path, monkeypatch) -> None:
    """SIGTERM trips the eval-abort sentinels *in the handler* (not lifespan
    shutdown) and still delegates to the previously-installed handler."""
    import signal as _signal

    from fieldkit.arena import jobs as jobs_mod
    from fieldkit.arena.guardrail import eval_sentinel_for
    from fieldkit.arena.jobs import JobKind, JobStatus
    from fieldkit.arena.server import _install_signal_teardown
    from fieldkit.arena.store import ArenaStore

    monkeypatch.setenv("FK_EVAL_SENTINEL_DIR", str(tmp_path / "sentinels"))
    db = tmp_path / "arena.db"
    store = ArenaStore(db)
    store.initialize()
    store.upsert_lane(
        {"id": "cloud", "kind": "OpenRouterLane", "model": "m", "port": 0, "base_url": "", "recommended": 0}
    )
    running_id = jobs_mod.enqueue_job(store, JobKind.EVAL_RERUN, {"lane_id": "cloud", "bench_id": "b1"})
    store.update_job(running_id, status=JobStatus.RUNNING)
    store.close()

    seen: list[int] = []
    prev_term = _signal.getsignal(_signal.SIGTERM)
    prev_int = _signal.getsignal(_signal.SIGINT)
    try:
        # A stand-in for uvicorn's handler — must still be called (chained).
        _signal.signal(_signal.SIGTERM, lambda s, f: seen.append(s))
        assert _install_signal_teardown(str(db)) is True
        _signal.raise_signal(_signal.SIGTERM)
        assert eval_sentinel_for(running_id).exists()
        body = json.loads(eval_sentinel_for(running_id).read_text())
        assert body["aborted_by"] == "teardown"
        assert seen == [_signal.SIGTERM]  # the prior handler still ran
    finally:
        _signal.signal(_signal.SIGTERM, prev_term)
        _signal.signal(_signal.SIGINT, prev_int)


def test_signal_teardown_skipped_off_main_thread(tmp_path: Path) -> None:
    """`signal.signal` is main-thread-only; the installer must no-op (not
    raise) when called from a worker thread — the TestClient portal case."""
    import threading

    from fieldkit.arena.server import _install_signal_teardown

    out: list[bool] = []
    t = threading.Thread(target=lambda: out.append(_install_signal_teardown(str(tmp_path / "x.db"))))
    t.start()
    t.join()
    assert out == [False]


# ---------------------------------------------------------------------------
# create_app — endpoints
# ---------------------------------------------------------------------------


def test_create_app_healthz_reports_surface_version(repo_root: Path) -> None:
    app = create_app(repo_root=repo_root, telemetry_interval=2.0)
    with TestClient(app) as client:
        r = client.get("/healthz")
        assert r.status_code == 200
        body = r.json()
        assert body["ok"] is True
        assert body["arena_surface_version"] == ARENA_SURFACE_VERSION
        assert body["telemetry_running"] is False
        assert body["subscribers"] == 0


def test_guardrail_config_get_defaults(
    repo_root: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # GS-2 — GET reflects defaults when no file/env, with per-field provenance
    # + the canonical defaults & bounds for the Settings pane.
    monkeypatch.setenv("FK_EVAL_CONFIG_DIR", str(tmp_path / "gcfg"))
    monkeypatch.delenv("FK_EVAL_CONFIG_PATH", raising=False)
    monkeypatch.delenv("FK_EVAL_STALL_TIMEOUT_S", raising=False)
    monkeypatch.delenv("FK_EVAL_RUN_COST_CAP_USD", raising=False)
    monkeypatch.delenv("FK_EVAL_GUARDRAIL_ENABLED", raising=False)
    app = create_app(repo_root=repo_root, telemetry_interval=2.0)
    with TestClient(app) as client:
        r = client.get("/api/guardrail-config")
        assert r.status_code == 200
        body = r.json()
        assert body["effective"] == {
            "stall_timeout_s": 600.0,
            "cost_cap_usd": 5.0,
            "enabled": True,
        }
        assert set(body["sources"].values()) == {"default"}
        assert body["defaults"]["enabled"] is True
        assert body["bounds"]["cost_cap_usd"] == [0.0, 1000.0]


def test_guardrail_config_post_persists_and_takes_effect(
    repo_root: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # GS-2 — POST writes the file; a subsequent GET reads it back with source=file.
    monkeypatch.setenv("FK_EVAL_CONFIG_DIR", str(tmp_path / "gcfg"))
    monkeypatch.delenv("FK_EVAL_CONFIG_PATH", raising=False)
    app = create_app(repo_root=repo_root, telemetry_interval=2.0)
    with TestClient(app) as client:
        r = client.post(
            "/api/guardrail-config",
            json={"stall_timeout_s": 300.0, "cost_cap_usd": 2.5, "enabled": False},
        )
        assert r.status_code == 200
        assert r.json()["effective"]["cost_cap_usd"] == 2.5
        assert r.json()["sources"]["cost_cap_usd"] == "file"
        # And the live resolver reflects it (the arm path reads the same file).
        from fieldkit.arena.guardrail import load_config

        cfg, sources = load_config()
        assert (cfg.cost_cap_usd, cfg.enabled) == (2.5, False)
        assert sources["enabled"] == "file"
        # GET now shows file provenance too.
        g = client.get("/api/guardrail-config").json()
        assert g["effective"]["stall_timeout_s"] == 300.0
        assert g["sources"]["stall_timeout_s"] == "file"


def test_guardrail_config_post_out_of_bounds_422(
    repo_root: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # GS-5 — an out-of-range value is rejected. Negative is caught by Pydantic
    # (422); an over-cap or below-floor value is caught by save_config (422).
    monkeypatch.setenv("FK_EVAL_CONFIG_DIR", str(tmp_path / "gcfg"))
    monkeypatch.delenv("FK_EVAL_CONFIG_PATH", raising=False)
    app = create_app(repo_root=repo_root, telemetry_interval=2.0)
    with TestClient(app) as client:
        neg = client.post(
            "/api/guardrail-config",
            json={"stall_timeout_s": 600.0, "cost_cap_usd": -1.0, "enabled": True},
        )
        assert neg.status_code == 422
        over = client.post(
            "/api/guardrail-config",
            json={"stall_timeout_s": 600.0, "cost_cap_usd": 5000.0, "enabled": True},
        )
        assert over.status_code == 422
        floor = client.post(
            "/api/guardrail-config",
            json={"stall_timeout_s": 5.0, "cost_cap_usd": 5.0, "enabled": True},
        )
        assert floor.status_code == 422
        # The file was never written (no GET shows a file source).
        g = client.get("/api/guardrail-config").json()
        assert set(g["sources"].values()) == {"default"}


def test_guardrail_config_file_wins_over_env(
    repo_root: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # GS-R2 — file source is authoritative over env for a written field.
    monkeypatch.setenv("FK_EVAL_CONFIG_DIR", str(tmp_path / "gcfg"))
    monkeypatch.delenv("FK_EVAL_CONFIG_PATH", raising=False)
    monkeypatch.setenv("FK_EVAL_RUN_COST_CAP_USD", "9.0")  # env base
    app = create_app(repo_root=repo_root, telemetry_interval=2.0)
    with TestClient(app) as client:
        client.post(
            "/api/guardrail-config",
            json={"stall_timeout_s": 600.0, "cost_cap_usd": 1.0, "enabled": True},
        )
        g = client.get("/api/guardrail-config").json()
        assert g["effective"]["cost_cap_usd"] == 1.0  # file beats env
        assert g["sources"]["cost_cap_usd"] == "file"


# ---------------------------------------------------------------------------
# BUG-3 / AF-29 — /api/prices (G3-arming disclosure) + /api/prices/refresh
# ---------------------------------------------------------------------------


def _seed_eval_roster_db(tmp_path: Path) -> Path:
    """A db with two cloud eval jobs (one H6-priced model, one unpriced) and a
    local-lane eval that must stay off the roster."""
    from fieldkit.arena import jobs as jobs_mod
    from fieldkit.arena.jobs import JobKind
    from fieldkit.arena.store import ArenaStore

    db = tmp_path / "arena.db"
    store = ArenaStore(db)
    store.initialize()
    store.upsert_lane(
        {"id": "cloud", "kind": "OpenRouterLane", "model": "m", "port": 0, "base_url": "", "recommended": 0}
    )
    jobs_mod.enqueue_job(
        store,
        JobKind.EVAL_RERUN,
        {"lane_id": "cloud", "bench_id": "b1", "base_url": "https://openrouter.ai/api/v1",
         "model": "openai/gpt-4o-mini"},
    )
    jobs_mod.enqueue_job(
        store,
        JobKind.EVAL_RERUN,
        {"lane_id": "cloud", "bench_id": "b2", "base_url": "https://openrouter.ai/api/v1",
         "model": "fresh/unpriced"},
    )
    jobs_mod.enqueue_job(
        store,
        JobKind.EVAL_RERUN,
        {"lane_id": "cloud", "bench_id": "b3", "base_url": "http://127.0.0.1:8091/v1",
         "model": "kepler-q8"},
    )
    store.close()
    return db


def test_api_prices_reports_g3_arming_per_model(repo_root: Path, tmp_path: Path) -> None:
    db = _seed_eval_roster_db(tmp_path)
    app = create_app(repo_root=repo_root, db=str(db), telemetry_interval=2.0)
    with TestClient(app) as client:
        body = client.get("/api/prices").json()
        by_id = {m["model_id"]: m for m in body["models"]}
        # The local-lane eval never needs a price — off the roster.
        assert "kepler-q8" not in by_id
        # H6-seeded model: armed, provenance visible.
        priced = by_id["openai/gpt-4o-mini"]
        assert priced["priced"] is True
        assert priced["source"] == "h6_evidence"
        assert priced["price_per_m_output_usd"] == 0.6
        # Unpriced model: the loud bit — the next eval of it is tokens-only.
        assert by_id["fresh/unpriced"]["priced"] is False
        assert body["unpriced"] == 1
        assert body["enabled"] is True and body["cost_cap_usd"] == 5.0


def test_api_prices_refresh_captures_roster(repo_root: Path, tmp_path: Path, monkeypatch) -> None:
    from fieldkit import cost as cost_mod

    db = _seed_eval_roster_db(tmp_path)

    def _fake_fetch(model_ids, **kwargs):
        # The roster (cloud models only); we price just one of the two.
        assert set(model_ids) == {"openai/gpt-4o-mini", "fresh/unpriced"}
        return [
            {"model_id": "fresh/unpriced", "price_per_m_input_usd": 0.2,
             "price_per_m_output_usd": 0.8}
        ]

    monkeypatch.setattr(cost_mod, "fetch_openrouter_prices", _fake_fetch)
    app = create_app(repo_root=repo_root, db=str(db), telemetry_interval=2.0)
    with TestClient(app) as client:
        body = client.post("/api/prices/refresh", json={}).json()
        assert body["ok"] is True
        assert [r["model_id"] for r in body["refreshed"]] == ["fresh/unpriced"]
        assert body["still_unpriced"] == ["openai/gpt-4o-mini"]  # absent from the fake catalog
        # The disclosure now shows the captured model armed, fresh provenance.
        by_id = {m["model_id"]: m for m in client.get("/api/prices").json()["models"]}
        assert by_id["fresh/unpriced"]["priced"] is True
        assert by_id["fresh/unpriced"]["source"] == "openrouter-api"


def test_api_prices_refresh_fetch_failure_is_502(repo_root: Path, tmp_path: Path, monkeypatch) -> None:
    from fieldkit import cost as cost_mod
    from fieldkit.cost import CostError

    db = _seed_eval_roster_db(tmp_path)

    def _boom(model_ids, **kwargs):
        raise CostError("OpenRouter price fetch failed: offline")

    monkeypatch.setattr(cost_mod, "fetch_openrouter_prices", _boom)
    app = create_app(repo_root=repo_root, db=str(db), telemetry_interval=2.0)
    with TestClient(app) as client:
        r = client.post("/api/prices/refresh", json={})
        assert r.status_code == 502  # loud, not a silent no-op (BUG-3's silence)
        assert "fetch failed" in r.json()["detail"]


def test_create_app_leaderboard_reads_mirror_json(repo_root: Path) -> None:
    app = create_app(repo_root=repo_root, telemetry_interval=2.0)
    with TestClient(app) as client:
        r = client.get("/api/leaderboard?limit=5")
        assert r.status_code == 200
        body = r.json()
        assert body["found"] is True
        assert len(body["rows"]) == 2
        assert body["rows"][0]["lane_id"] == "fixture-lane-a"
        assert body["rows"][0]["median_tok_per_s"] == 83.5
        # source path is relative to the repo root.
        assert body["source"].endswith("arena-mirror/leaderboard.json")


def test_create_app_leaderboard_limit_truncates(repo_root: Path) -> None:
    app = create_app(repo_root=repo_root, telemetry_interval=2.0)
    with TestClient(app) as client:
        r = client.get("/api/leaderboard?limit=1")
        assert r.status_code == 200
        assert len(r.json()["rows"]) == 1


def test_create_app_leaderboard_missing_mirror_yields_empty(
    tmp_path: Path,
) -> None:
    # Empty repo with no mirror file — should not 500, just return empty.
    app = create_app(repo_root=tmp_path, telemetry_interval=2.0)
    with TestClient(app) as client:
        r = client.get("/api/leaderboard?limit=5")
        assert r.status_code == 200
        body = r.json()
        assert body["found"] is False
        assert body["rows"] == []


def test_create_app_lanes_with_no_hermes_config(
    repo_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Steer the hermes-config reader at a non-existent path so tests don't
    # depend on the developer's local Spark state.
    monkeypatch.setattr(
        "fieldkit.arena.server._read_hermes_lane",
        lambda hermes_path=None: None,
    )
    app = create_app(
        repo_root=repo_root,
        db=str(repo_root / "no-such.db"),
        telemetry_interval=2.0,
    )
    with TestClient(app) as client:
        r = client.get("/api/lanes")
        assert r.status_code == 200
        body = r.json()
        assert body["resident"] is None
        assert body["roster"] == []


def test_create_app_lanes_surfaces_resident_when_present(
    repo_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "fieldkit.arena.server._read_hermes_lane",
        lambda hermes_path=None: {
            "id": "resident-brain",
            "kind": "LlamaServerLane",
            "model": "Qwen3-30B-A3B-Q4_K_M",
            "base_url": "http://127.0.0.1:8080/v1",
            "port": 8080,
            "provider": "custom",
            "context_length": 64000,
            "max_tokens": 8192,
            "config_path": "/tmp/hermes.yaml",
            "config_mtime": 1.0,
        },
    )
    app = create_app(
        repo_root=repo_root,
        db=str(repo_root / "no-such.db"),
        telemetry_interval=2.0,
    )
    with TestClient(app) as client:
        r = client.get("/api/lanes")
        body = r.json()
        assert body["resident"]["model"] == "Qwen3-30B-A3B-Q4_K_M"
        assert body["resident"]["port"] == 8080


# ---------------------------------------------------------------------------
# SSE endpoint — exercised via httpx stream against a live uvicorn loop.
# ---------------------------------------------------------------------------


class _FakeRequest:
    """Minimal stand-in for ``starlette.Request.is_disconnected()``.

    The generator polls it on each loop iteration. Tests flip
    ``_disconnected`` to terminate the stream and exercise the
    ``finally`` cleanup branch.
    """

    def __init__(self) -> None:
        self._disconnected = False

    async def is_disconnected(self) -> bool:
        return self._disconnected

    def disconnect(self) -> None:
        self._disconnected = True


def test_telemetry_event_stream_emits_hello_payload() -> None:
    """Direct unit test of the generator: subscribes on entry, yields the
    "hello" payload immediately, then waits on the queue. We disconnect
    after the first event so the generator's ``finally`` unsubscribes.

    Bypassing the HTTP layer keeps the test deterministic across the
    sse-starlette / httpx-ASGITransport / TestClient triad — the wire
    behaviour is covered by the live curl + Playwright smoke at M3
    side-by-side review time.
    """
    from fieldkit.arena.server import telemetry_event_stream

    hub = TelemetryHub(interval=0.1)
    request = _FakeRequest()

    async def _drive() -> dict[str, object]:
        gen = telemetry_event_stream(hub, request)
        event = await gen.__anext__()
        # Tell the generator to terminate on its next loop iteration,
        # then drive one more step so the `finally` runs.
        request.disconnect()
        try:
            await gen.__anext__()
        except StopAsyncIteration:
            pass
        await gen.aclose()
        return event

    event = asyncio.run(_drive())
    assert event["event"] == "telemetry"
    payload = json.loads(event["data"])
    # Required keys on every M3 tick (values may be None on a host without
    # nvidia-smi or /proc/meminfo, e.g. a CI runner).
    for key in (
        "ts",
        "gpu_util",
        "gpu_temp_c",
        "unified_used_gb",
        "unified_total_gb",
        "inflight",
        "tok_per_s",
        "ttft_ms",
        "lane_id",
    ):
        assert key in payload, f"missing key: {key}"

    # Cleanup: the generator's `finally` should have torn down the hub.
    for _ in range(80):
        if hub.subscriber_count == 0 and not hub.is_running:
            break
        time.sleep(0.05)
    assert hub.subscriber_count == 0
    assert not hub.is_running


def test_telemetry_event_stream_unsubscribes_on_disconnect() -> None:
    """Spec §4.6 zero-idle commitment — disconnect must stop the sampler."""
    from fieldkit.arena.server import telemetry_event_stream

    hub = TelemetryHub(interval=0.1)
    request = _FakeRequest()

    async def _drive() -> None:
        gen = telemetry_event_stream(hub, request)
        await gen.__anext__()  # hello payload
        assert hub.subscriber_count == 1
        assert hub.is_running
        request.disconnect()
        # Drain until StopAsyncIteration — the next yield path checks
        # is_disconnected before pulling from the queue.
        try:
            for _ in range(8):
                await gen.__anext__()
        except StopAsyncIteration:
            pass
        await gen.aclose()

    asyncio.run(_drive())
    for _ in range(80):
        if hub.subscriber_count == 0 and not hub.is_running:
            break
        time.sleep(0.05)
    assert hub.subscriber_count == 0
    assert not hub.is_running


def test_telemetry_event_stream_route_is_registered(repo_root: Path) -> None:
    """The HTTP surface stays minimal: a route at the spec'd path that
    returns an EventSourceResponse. The wire-level behaviour is exercised
    via the live curl smoke at M3 review time; here we just gate that
    the route exists and is shaped right."""
    app = create_app(repo_root=repo_root, telemetry_interval=2.0)
    paths = {r.path for r in app.routes if hasattr(r, "path")}
    assert "/api/telemetry/stream" in paths
    assert "/api/lanes" in paths
    assert "/api/leaderboard" in paths
    assert "/healthz" in paths


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------


def test_default_arena_port_locked_at_7866() -> None:
    """Spec §3.4 — DEFAULT_ARENA_PORT is operator-visible and must stay 7866."""
    assert DEFAULT_ARENA_PORT == 7866


# ---------------------------------------------------------------------------
# M4 — chat SSE proxy
# ---------------------------------------------------------------------------


class _StubChatClient:
    """Stub of `fieldkit.notebook.OpenAICompatClient` for the chat-stream
    unit tests. Yields a canned `<think>…</think>answer` shape so the
    `split_think` / channel-classification path exercises end-to-end.
    Captures the `messages` it was called with so the test can assert
    the prompt threading.
    """

    def __init__(self, chunks: list[str]) -> None:
        self._chunks = list(chunks)
        self.calls: list[list[dict[str, str]]] = []

    def chat_stream(self, messages, **_kwargs):
        self.calls.append(list(messages))
        for piece in self._chunks:
            yield piece


_CANNED_CHAT_CHUNKS = [
    "<think>",
    "Routing to the answer.",
    "</think>",
    "Hello, ",
    "world.",
]


def test_chat_event_stream_emits_start_token_done(
    repo_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Drive `chat_event_stream` directly: it should emit `start` first,
    then one `token` event per chunk (with `channel` set per the
    `<think>` boundary), then `done` with a `session_id` + `turn_id`."""
    from types import SimpleNamespace

    from fieldkit.arena.server import chat_event_stream

    stub = _StubChatClient(_CANNED_CHAT_CHUNKS)
    monkeypatch.setattr(
        "fieldkit.arena.server._chat_client_factory",
        lambda resident: stub,
    )

    hub = TelemetryHub(interval=0.1)
    request = _FakeRequest()
    body = SimpleNamespace(
        prompt="ping",
        session_id=None,
        rubric_id=None,
        max_tokens=128,
        temperature=0.0,
    )
    resident = {
        "id": "test-lane",
        "model": "qwen-fixture",
        "base_url": "http://127.0.0.1:8080/v1",
    }
    db_path = str(repo_root / "arena.db")

    async def _drive():
        events: list[dict[str, str]] = []
        gen = chat_event_stream(
            hub=hub,
            request=request,
            body=body,
            resident=resident,
            db_path=db_path,
        )
        async for ev in gen:
            events.append(ev)
            if ev["event"] == "done":
                break
        await gen.aclose()
        return events

    events = asyncio.run(_drive())
    kinds = [ev["event"] for ev in events]
    assert kinds[0] == "start"
    assert kinds[-1] == "done"
    # Every middle event is a token (or heartbeat); we expect at least
    # one of each channel — reasoning ("Routing…") + content ("Hello…").
    token_events = [ev for ev in events if ev["event"] == "token"]
    channels = {json.loads(ev["data"])["channel"] for ev in token_events}
    assert "reasoning" in channels
    assert "content" in channels

    start_payload = json.loads(events[0]["data"])
    assert start_payload["lane_id"] == "test-lane"
    assert start_payload["model"] == "qwen-fixture"
    assert start_payload["session_id"].startswith("cs-")

    done_payload = json.loads(events[-1]["data"])
    assert done_payload["session_id"] == start_payload["session_id"]
    assert done_payload["turn_id"] > 0
    assert done_payload["finish_reason"] == "stop"
    # Stub used a single round; the messages passed to chat_stream were a
    # single-user-turn shape (the M4 surface doesn't carry history yet —
    # M5 wires that).
    assert len(stub.calls) == 1
    assert stub.calls[0] == [{"role": "user", "content": "ping"}]


def test_chat_event_stream_persists_user_and_assistant_turns(
    repo_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Each chat turn lands as two `chat_turns` rows: user + assistant.
    Re-running the generator under the same session_id appends + bumps
    ord monotonically."""
    from types import SimpleNamespace

    from fieldkit.arena.server import chat_event_stream
    from fieldkit.arena.store import ArenaStore

    stub = _StubChatClient(_CANNED_CHAT_CHUNKS)
    monkeypatch.setattr(
        "fieldkit.arena.server._chat_client_factory",
        lambda resident: stub,
    )

    hub = TelemetryHub(interval=0.1)
    db_path = str(repo_root / "arena.db")
    resident = {
        "id": "test-lane",
        "model": "qwen-fixture",
        "base_url": "http://127.0.0.1:8080/v1",
    }

    async def _drive(session_id):
        request = _FakeRequest()
        body = SimpleNamespace(
            prompt="ping",
            session_id=session_id,
            rubric_id=None,
            max_tokens=128,
            temperature=0.0,
        )
        events: list[dict[str, str]] = []
        gen = chat_event_stream(
            hub=hub,
            request=request,
            body=body,
            resident=resident,
            db_path=db_path,
        )
        async for ev in gen:
            events.append(ev)
            if ev["event"] == "done":
                break
        await gen.aclose()
        return events

    events1 = asyncio.run(_drive(None))
    sid = json.loads(events1[0]["data"])["session_id"]
    # Second turn under the same session.
    events2 = asyncio.run(_drive(sid))
    sid2 = json.loads(events2[0]["data"])["session_id"]
    assert sid2 == sid

    with ArenaStore(repo_root / "arena.db") as store:
        rows = store.chat_turns(sid)
        # 2 turns × (user + assistant) = 4 rows; ord = 0,1,2,3.
        assert [r["ord"] for r in rows] == [0, 1, 2, 3]
        roles = [r["role"] for r in rows]
        assert roles == ["user", "assistant", "user", "assistant"]
        # Assistant rows carry the split reasoning + content.
        asst = [r for r in rows if r["role"] == "assistant"]
        for a in asst:
            assert "Hello," in a["content"]
            assert a["reasoning"] and "Routing" in a["reasoning"]
            assert a["finish_reason"] == "stop"


def test_chat_event_stream_pings_report_inflight(
    repo_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The M4 telemetry round-trip: `report_inflight(inflight=True, lane_id=…)`
    fires at stream start, and `inflight=False` fires on done. Idle ticks
    after the stream should therefore read inflight=False."""
    from types import SimpleNamespace

    from fieldkit.arena.server import chat_event_stream

    stub = _StubChatClient(_CANNED_CHAT_CHUNKS)
    monkeypatch.setattr(
        "fieldkit.arena.server._chat_client_factory",
        lambda resident: stub,
    )

    hub = TelemetryHub(interval=0.1)
    request = _FakeRequest()
    body = SimpleNamespace(
        prompt="ping",
        session_id=None,
        rubric_id=None,
        max_tokens=128,
        temperature=0.0,
    )
    resident = {
        "id": "test-lane",
        "model": "qwen-fixture",
        "base_url": "http://127.0.0.1:8080/v1",
    }
    db_path = str(repo_root / "arena.db")

    seen: list[dict[str, object]] = []
    real_report = hub.report_inflight

    def _spy(**kwargs):
        seen.append(dict(kwargs))
        return real_report(**kwargs)

    monkeypatch.setattr(hub, "report_inflight", _spy)

    async def _drive():
        gen = chat_event_stream(
            hub=hub,
            request=request,
            body=body,
            resident=resident,
            db_path=db_path,
        )
        async for ev in gen:
            if ev["event"] == "done":
                break
        await gen.aclose()

    asyncio.run(_drive())
    # First call: inflight=True with the resident lane id.
    assert seen[0]["inflight"] is True
    assert seen[0]["lane_id"] == "test-lane"
    # Final call: inflight=False, with lane_id OMITTED — the finally guard keeps
    # the lane label + final speeds sticky so the rail keeps labelling the model
    # you just ran (with its completion-final tok/s) at idle.
    assert seen[-1]["inflight"] is False
    assert "lane_id" not in seen[-1]


def test_chat_stream_route_is_registered_with_pydantic_body(
    repo_root: Path,
) -> None:
    """Route surface gate: POST /api/chat/stream is mounted; the empty body
    case returns 422 from the Pydantic validator (proves the request model
    is wired)."""
    app = create_app(
        repo_root=repo_root,
        db=str(repo_root / "arena.db"),
        telemetry_interval=2.0,
    )
    routes = {
        (r.path, tuple(sorted(r.methods))) for r in app.routes if hasattr(r, "methods")
    }
    assert ("/api/chat/stream", ("POST",)) in routes
    with TestClient(app) as client:
        r = client.post("/api/chat/stream", json={})
        # Empty body — Pydantic rejects with 422 (prompt missing).
        assert r.status_code == 422


def test_chat_stream_returns_503_when_no_resident_lane(
    repo_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """If `~/.hermes/config.yaml` is unreadable / empty, the chat endpoint
    surfaces an explicit 503 rather than crashing on a missing base_url."""
    monkeypatch.setattr(
        "fieldkit.arena.server._read_hermes_lane",
        lambda hermes_path=None: None,
    )
    app = create_app(
        repo_root=repo_root,
        db=str(repo_root / "arena.db"),
        telemetry_interval=2.0,
    )
    with TestClient(app) as client:
        r = client.post(
            "/api/chat/stream", json={"prompt": "ping"}
        )
        assert r.status_code == 503
        assert "resident brain" in r.json()["detail"].lower()


# ---------------------------------------------------------------------------
# M5 — rubric registry + compare SSE + prefs
# ---------------------------------------------------------------------------


def test_default_rubric_registry_has_three_entries() -> None:
    from fieldkit.arena.rubrics import DEFAULT_RUBRIC_REGISTRY

    assert set(DEFAULT_RUBRIC_REGISTRY.keys()) == {
        "generic-correctness",
        "patent_claim_validity",
        "mcq_letter",
    }
    # Each spec carries an executable Rubric.
    for spec in DEFAULT_RUBRIC_REGISTRY.values():
        assert len(spec.rubric.checks) >= 1


def test_default_rubric_for_prompt_picks_patent_when_claim_word_present() -> None:
    from fieldkit.arena.rubrics import default_rubric_for_prompt

    assert (
        default_rubric_for_prompt("Is claim 1 anticipated by prior art under §102?")
        == "patent_claim_validity"
    )
    # MCQ — answer letter (A) on Q5
    assert (
        default_rubric_for_prompt("Which of (a), (b), (c), (d) is the floor?")
        == "mcq_letter"
    )
    # Free-form falls through to the floor
    assert default_rubric_for_prompt("Write a haiku about Spark.") == (
        "generic-correctness"
    )


def test_api_rubrics_returns_default_registry(repo_root: Path) -> None:
    app = create_app(
        repo_root=repo_root,
        db=str(repo_root / "arena.db"),
        telemetry_interval=2.0,
    )
    with TestClient(app) as client:
        r = client.get("/api/rubrics")
        assert r.status_code == 200
        data = r.json()
        ids = [row["id"] for row in data["rubrics"]]
        assert ids[0] == "generic-correctness"
        assert "patent_claim_validity" in ids
        assert "mcq_letter" in ids
        # Each entry surfaces the check kinds.
        kinds = {row["id"]: [c["kind"] for c in row["checks"]] for row in data["rubrics"]}
        assert kinds["patent_claim_validity"] == ["substring"]


class _StubBlankAClient:
    """Stub for lane A — yields a fixture <think>… chain plus an answer
    that does NOT match the patent rubric (so the rubric score is 0)."""

    def chat_stream(self, messages, **_kwargs):
        for piece in [
            "<think>",
            "Routing for A.",
            "</think>",
            "Hello from lane A.",
        ]:
            yield piece


class _StubPatentBClient:
    """Stub for lane B — answer contains 'obviousness' (matches the
    patent_claim_validity substring rubric)."""

    def __init__(self) -> None:
        self.api_key = "fake-key-so-no-stub"

    def chat_stream(self, messages, **_kwargs):
        for piece in [
            "Under §103, obviousness is the controlling standard. ",
            "The claim is invalid.",
        ]:
            yield piece


def test_compare_event_stream_emits_full_sse_sequence(
    repo_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The compare generator emits exactly the spec §4.3 SSE event
    sequence: ``start_a → token_a* → done_a → start_b → token_b* →
    done_b → score`` with the score event carrying the per-check
    ``ok`` + ``why`` strings for both sides."""
    from types import SimpleNamespace

    from fieldkit.arena.server import compare_event_stream

    monkeypatch.setattr(
        "fieldkit.arena.server._chat_client_factory",
        lambda resident: _StubBlankAClient(),
    )
    stub_b = _StubPatentBClient()
    monkeypatch.setattr(
        "fieldkit.arena.server._compare_b_factory",
        lambda: (stub_b, None),
    )
    # Make sure the "no-key" fallback doesn't fire.
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-fake")

    hub = TelemetryHub(interval=0.1)
    request = _FakeRequest()
    body = SimpleNamespace(
        prompt="Is the claim anticipated under §102?",
        lane_b="openrouter",
        rubric_id="patent_claim_validity",
        max_tokens=128,
        temperature=0.0,
    )
    resident = {
        "id": "resident-brain",
        "model": "qwen-fixture",
        "base_url": "http://127.0.0.1:8080/v1",
    }
    db_path = str(repo_root / "arena.db")

    async def _drive():
        events: list[dict[str, str]] = []
        gen = compare_event_stream(
            hub=hub,
            request=request,
            body=body,
            resident=resident,
            db_path=db_path,
        )
        async for ev in gen:
            events.append(ev)
            if ev["event"] == "score":
                break
        await gen.aclose()
        return events

    events = asyncio.run(_drive())
    kinds = [ev["event"] for ev in events]
    # Floor ordering: start_a comes before done_a, done_a before start_b,
    # start_b before done_b, done_b before score.
    assert kinds[0] == "start_a"
    assert "done_a" in kinds
    assert kinds.index("done_a") < kinds.index("start_b")
    assert "done_b" in kinds
    assert kinds.index("done_b") < kinds.index("score")
    assert kinds[-1] == "score"

    # Token events carry the channel.
    token_a = [ev for ev in events if ev["event"] == "token_a"]
    channels_a = {json.loads(ev["data"])["channel"] for ev in token_a}
    assert "reasoning" in channels_a
    assert "content" in channels_a

    # Score payload: A fails patent rubric (no anchor term), B passes.
    score = json.loads(events[-1]["data"])
    assert score["rubric_id"] == "patent_claim_validity"
    assert score["a"]["total"] == 0.0  # "Hello from lane A." — no §103 / obviousness
    assert score["b"]["total"] == 1.0  # carries 'obviousness'
    assert score["deltas"]["score"] == -1.0  # B beats A on the rubric
    # Per-check why strings are visible.
    assert all("why" in c for c in score["a"]["checks"])
    assert all("why" in c for c in score["b"]["checks"])


class _StubAstroWrongAClient:
    """Lane A — boxed value wrong ~2× (the smoke's B3 lane-A failure shape)."""

    def chat_stream(self, messages, **_kwargs):
        yield "The orbital period is \\boxed{210.0 min}."


class _StubAstroRightBClient:
    def __init__(self) -> None:
        self.api_key = "fake-key-so-no-stub"

    def chat_stream(self, messages, **_kwargs):
        yield "The orbital period is \\boxed{105.6 min}."


def test_compare_free_prompt_auto_matches_bench_row(
    repo_root: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AF-27(b) — a free-typed prompt that IS a registered bench row gets the
    bench's own reference verdict (via its scorer_path verifier), not just the
    format rubric. The exact smoke-B3 topology: both sides pass the format
    regex ("Dead heat — both 100%") while lane A's VALUE is wrong ~2×."""
    import asyncio
    from types import SimpleNamespace

    from fieldkit.arena import benches
    from fieldkit.arena.server import compare_event_stream
    from fieldkit.arena.store import ArenaStore

    # The astro bench splits (FK_ARENA_BENCH_DIR root override, AE-11 shape).
    astro = tmp_path / "astro-evidence"
    astro.mkdir()
    (astro / "astro-bench-v0.1.jsonl").write_text(
        json.dumps(
            {"task_id": "astro-orb-leo_period-0000", "topic": "orbital_mechanics",
             "subtopic": "leo_period", "tier": 2,
             "prompt": "Compute the orbital period. Give \\boxed{value unit}.",
             "answer": "105.6 min", "gold_value_si": 6336.4, "gold_unit": "s",
             "rel_tol": 0.02}
        )
        + "\n"
    )
    (astro / "astro-bench-v0.1.heldout.jsonl").write_text("")
    monkeypatch.setenv("FK_ARENA_BENCH_DIR", str(astro))
    benches._CACHE.clear()
    # A registered verifier the AF-15 loader can resolve (the kepler-astro
    # registry shape from the live box).
    reg = tmp_path / "bench-registry"
    reg.mkdir()
    verifier = tmp_path / "verifier.py"
    verifier.write_text(
        "def astro_numeric_match(predicted, expected, **kw):\n"
        "    return 1.0 if expected.split()[0] in predicted else 0.0\n"
    )
    (reg / "kepler-astro.meta.json").write_text(
        json.dumps({"scorer_path": f"{verifier}:astro_numeric_match"})
    )
    monkeypatch.setenv("ARENA_BENCH_DIR", str(reg))
    benches._SCORER_FN_CACHE.clear()

    monkeypatch.setattr(
        "fieldkit.arena.server._chat_client_factory",
        lambda resident: _StubAstroWrongAClient(),
    )
    monkeypatch.setattr(
        "fieldkit.arena.server._compare_b_factory",
        lambda: (_StubAstroRightBClient(), None),
    )
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-fake")

    hub = TelemetryHub(interval=0.1)
    body = SimpleNamespace(
        prompt="Compute the orbital period. Give \\boxed{value unit}.",
        lane_b="openrouter",
        rubric_id=None,
        max_tokens=128,
        temperature=0.0,
    )
    resident = {"id": "resident-brain", "model": "qwen-fixture",
                "base_url": "http://127.0.0.1:8080/v1"}
    db_path = str(repo_root / "arena.db")

    async def _drive():
        events = []
        gen = compare_event_stream(
            hub=hub, request=_FakeRequest(), body=body, resident=resident, db_path=db_path
        )
        async for ev in gen:
            events.append(ev)
            if ev["event"] == "score":
                break
        await gen.aclose()
        return events

    events = asyncio.run(_drive())
    score = json.loads(events[-1]["data"])
    # The format rubric is labelled as such — and both sides pass it (the
    # misleading "dead heat") …
    assert score["rubric_scope"] == "format"
    assert score["a"]["total"] == 1.0 and score["b"]["total"] == 1.0
    # … but the auto-matched bench verdict tells the truth: A's value is wrong.
    ev = score["eval"]
    assert ev["auto_matched"] is True
    assert ev["bench_id"] == "astro-bench"
    assert ev["a"]["normalized"] == 0.0
    assert ev["b"]["normalized"] == 1.0
    # The real verdict persisted into eval_scores (feeds the AF-28 live group).
    store = ArenaStore(db_path)
    n = store.connect().execute(
        "SELECT COUNT(*) FROM eval_scores WHERE source='compare'"
    ).fetchone()[0]
    store.close()
    assert n == 2


def test_compare_free_prompt_no_match_keeps_rubric_path(
    repo_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A plain free prompt (no bench row) carries no eval block — the rubric
    verdict (scope-labelled) stands."""
    import asyncio
    from types import SimpleNamespace

    from fieldkit.arena.server import compare_event_stream

    monkeypatch.setattr(
        "fieldkit.arena.server._chat_client_factory",
        lambda resident: _StubBlankAClient(),
    )
    monkeypatch.setattr(
        "fieldkit.arena.server._compare_b_factory",
        lambda: (_StubPatentBClient(), None),
    )
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-fake")
    hub = TelemetryHub(interval=0.1)
    body = SimpleNamespace(
        prompt="Tell me something nice.", lane_b="openrouter",
        rubric_id=None, max_tokens=128, temperature=0.0,
    )
    resident = {"id": "resident-brain", "model": "qwen-fixture",
                "base_url": "http://127.0.0.1:8080/v1"}

    async def _drive():
        gen = compare_event_stream(
            hub=hub, request=_FakeRequest(), body=body, resident=resident,
            db_path=str(repo_root / "arena.db"),
        )
        events = []
        async for ev in gen:
            events.append(ev)
            if ev["event"] == "score":
                break
        await gen.aclose()
        return events

    score = json.loads(asyncio.run(_drive())[-1]["data"])
    assert score["rubric_scope"] == "format"
    assert "eval" not in score


def test_compare_event_stream_persists_rows_and_no_pref_mutation(
    repo_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Drive one compare end-to-end + verify the on-disk artifacts:
    one ``compare_runs`` row, two ``compare_responses``, two
    ``rubric_scores``. Then insert a human pref and assert the
    rubric_scores totals do NOT move — spec §4.3 separate-signal
    contract."""
    from types import SimpleNamespace

    from fieldkit.arena.schemas import HumanPrefRecord
    from fieldkit.arena.server import compare_event_stream
    from fieldkit.arena.store import ArenaStore

    monkeypatch.setattr(
        "fieldkit.arena.server._chat_client_factory",
        lambda resident: _StubBlankAClient(),
    )
    monkeypatch.setattr(
        "fieldkit.arena.server._compare_b_factory",
        lambda: (_StubPatentBClient(), None),
    )
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-fake")

    hub = TelemetryHub(interval=0.1)
    db_path = str(repo_root / "arena.db")
    resident = {
        "id": "resident-brain",
        "model": "qwen-fixture",
        "base_url": "http://127.0.0.1:8080/v1",
    }

    async def _drive():
        body = SimpleNamespace(
            prompt="Is the claim anticipated under §102?",
            lane_b="openrouter",
            rubric_id="patent_claim_validity",
            max_tokens=128,
            temperature=0.0,
        )
        events: list[dict[str, str]] = []
        gen = compare_event_stream(
            hub=hub,
            request=_FakeRequest(),
            body=body,
            resident=resident,
            db_path=db_path,
        )
        async for ev in gen:
            events.append(ev)
            if ev["event"] == "score":
                break
        await gen.aclose()
        return events

    events = asyncio.run(_drive())
    run_id = json.loads(events[0]["data"])["run_id"]

    with ArenaStore(repo_root / "arena.db") as store:
        head = store.compare_run(run_id)
        assert head is not None
        assert head["rubric_id"] == "patent_claim_validity"
        sides = store.compare_responses(run_id)
        assert [r["side"] for r in sides] == ["A", "B"]
        scores = store.rubric_scores_for_run(run_id)
        assert len(scores) == 2
        totals_before = {s["side"]: s["total"] for s in scores}
        assert totals_before["A"] == 0.0
        assert totals_before["B"] == 1.0

        # Operator thumbs B — spec §4.3 separate-signal: rubric_scores.total stays put.
        store.append_human_pref(
            HumanPrefRecord(
                id="hp-test",
                compare_run_id=run_id,
                winner="B",
                created_at="2026-05-28T19:00:00Z",
                note="B clearer",
            )
        )
        scores_after = store.rubric_scores_for_run(run_id)
        totals_after = {s["side"]: s["total"] for s in scores_after}
        assert totals_after == totals_before


def test_compare_stub_no_key_path_emits_clean_termination(
    repo_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When the env var is missing AND the stub client carries no api_key,
    the B-lane falls through to a canned reply. The stream still terminates
    cleanly with a ``score`` event (A wins by default — the stub reply has
    no patent anchor)."""
    from types import SimpleNamespace

    from fieldkit.arena.server import compare_event_stream

    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)

    class _NoKeyB:
        api_key = None  # triggers the stub path

        def chat_stream(self, messages, **kwargs):  # pragma: no cover — never called
            raise AssertionError("stub no-key path should NOT call chat_stream")

    monkeypatch.setattr(
        "fieldkit.arena.server._chat_client_factory",
        lambda resident: _StubBlankAClient(),
    )
    monkeypatch.setattr(
        "fieldkit.arena.server._compare_b_factory",
        lambda: (_NoKeyB(), None),
    )

    hub = TelemetryHub(interval=0.1)
    body = SimpleNamespace(
        prompt="hello",
        lane_b="openrouter",
        rubric_id=None,
        max_tokens=128,
        temperature=0.0,
    )
    resident = {
        "id": "resident-brain",
        "model": "qwen-fixture",
        "base_url": "http://127.0.0.1:8080/v1",
    }

    async def _drive():
        events: list[dict[str, str]] = []
        gen = compare_event_stream(
            hub=hub,
            request=_FakeRequest(),
            body=body,
            resident=resident,
            db_path=str(repo_root / "arena.db"),
        )
        async for ev in gen:
            events.append(ev)
            if ev["event"] == "score":
                break
        await gen.aclose()
        return events

    events = asyncio.run(_drive())
    kinds = [ev["event"] for ev in events]
    assert kinds[-1] == "score"
    start_b = next(ev for ev in events if ev["event"] == "start_b")
    assert json.loads(start_b["data"]).get("no_key") is True


def test_compare_stream_two_local_lanes_runs_full_duel(
    repo_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """v0.2 any-vs-any — two local lanes are now allowed (no v0.2-only error).

    The only warm Spark lane is the resident, so a ``local:*`` B-side resolves
    to it: the duel streams both sides off the resident client and scores
    normally. (The pre-v0.2 ``two_local_lanes_v0_2_only`` guard is gone.)"""
    from types import SimpleNamespace

    from fieldkit.arena.server import compare_event_stream

    monkeypatch.setattr(
        "fieldkit.arena.server._chat_client_factory",
        lambda resident: _StubBlankAClient(),
    )

    hub = TelemetryHub(interval=0.1)
    # Both sides = the resident (the only warm local lane); a full duel runs.
    body = SimpleNamespace(
        prompt="hello",
        lane_a="local:resident",
        lane_b="local:resident",
        rubric_id=None,
        max_tokens=128,
        temperature=0.0,
    )
    resident = {
        "id": "resident-brain",
        "model": "qwen-fixture",
        "base_url": "http://127.0.0.1:8080/v1",
    }

    async def _drive():
        events: list[dict[str, str]] = []
        gen = compare_event_stream(
            hub=hub,
            request=_FakeRequest(),
            body=body,
            resident=resident,
            db_path=str(repo_root / "arena.db"),
        )
        async for ev in gen:
            events.append(ev)
        await gen.aclose()
        return events

    events = asyncio.run(_drive())
    kinds = [ev["event"] for ev in events]
    # No v0.2-only error, and a full A→B→score sequence ran.
    assert not any(ev["event"] == "error" for ev in events)
    assert "start_a" in kinds and "done_a" in kinds
    assert "start_b" in kinds and "done_b" in kinds
    assert kinds[-1] == "score"
    # Both local sides cost nothing.
    done_b = json.loads(next(ev for ev in events if ev["event"] == "done_b")["data"])
    assert done_b.get("cost_usd") == 0.0


def test_api_prefs_inserts_row_and_returns_count(
    repo_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """POST /api/prefs writes one human_prefs row and returns the new
    pref id + the per-run pref count. 404 on unknown compare_run_id."""
    from types import SimpleNamespace

    from fieldkit.arena.server import compare_event_stream
    from fieldkit.arena.store import ArenaStore

    monkeypatch.setattr(
        "fieldkit.arena.server._chat_client_factory",
        lambda resident: _StubBlankAClient(),
    )
    monkeypatch.setattr(
        "fieldkit.arena.server._compare_b_factory",
        lambda: (_StubPatentBClient(), None),
    )
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-fake")

    # First, drive one compare so we have a real run_id.
    hub = TelemetryHub(interval=0.1)
    db_path = str(repo_root / "arena.db")

    async def _drive():
        body = SimpleNamespace(
            prompt="ping",
            lane_b="openrouter",
            rubric_id="generic-correctness",
            max_tokens=128,
            temperature=0.0,
        )
        gen = compare_event_stream(
            hub=hub,
            request=_FakeRequest(),
            body=body,
            resident={
                "id": "resident-brain",
                "model": "qwen-fixture",
                "base_url": "http://127.0.0.1:8080/v1",
            },
            db_path=db_path,
        )
        events = []
        async for ev in gen:
            events.append(ev)
            if ev["event"] == "score":
                break
        await gen.aclose()
        return events

    events = asyncio.run(_drive())
    run_id = json.loads(events[0]["data"])["run_id"]

    # Stub _read_hermes_lane so the app builds without needing live config.
    monkeypatch.setattr(
        "fieldkit.arena.server._read_hermes_lane",
        lambda hermes_path=None: {
            "id": "resident-brain",
            "model": "qwen-fixture",
            "base_url": "http://127.0.0.1:8080/v1",
        },
    )
    app = create_app(
        repo_root=repo_root,
        db=db_path,
        telemetry_interval=2.0,
    )
    with TestClient(app) as client:
        r = client.post(
            "/api/prefs",
            json={"compare_run_id": run_id, "winner": "B"},
        )
        assert r.status_code == 200
        payload = r.json()
        assert payload["ok"] is True
        assert payload["n_prefs"] == 1
        assert payload["pref_id"].startswith("hp-")

        # Second pref bumps the count.
        r2 = client.post(
            "/api/prefs",
            json={"compare_run_id": run_id, "winner": "tie", "note": "wash"},
        )
        assert r2.json()["n_prefs"] == 2

        # 404 on unknown.
        r3 = client.post(
            "/api/prefs",
            json={"compare_run_id": "cr-does-not-exist", "winner": "A"},
        )
        assert r3.status_code == 404

        # Pydantic gate: bad winner shape.
        r4 = client.post(
            "/api/prefs",
            json={"compare_run_id": run_id, "winner": "X"},
        )
        assert r4.status_code == 422

    # Persistence sanity: pref count on disk matches.
    with ArenaStore(repo_root / "arena.db") as store:
        prefs = store.human_prefs_for_run(run_id)
        assert len(prefs) == 2


def test_compare_stream_route_is_registered_with_pydantic_body(
    repo_root: Path,
) -> None:
    """Route surface gate — POST /api/compare/stream is mounted; empty
    body returns 422 (Pydantic prompt-missing)."""
    app = create_app(
        repo_root=repo_root,
        db=str(repo_root / "arena.db"),
        telemetry_interval=2.0,
    )
    routes = {
        (r.path, tuple(sorted(r.methods))) for r in app.routes if hasattr(r, "methods")
    }
    assert ("/api/compare/stream", ("POST",)) in routes
    assert ("/api/rubrics", ("GET",)) in routes
    assert ("/api/prefs", ("POST",)) in routes
    with TestClient(app) as client:
        r = client.post("/api/compare/stream", json={})
        assert r.status_code == 422


# ---------------------------------------------------------------------------
# Lab notes (v0.2; operator-private CRUD)
# ---------------------------------------------------------------------------


def test_api_lab_notes_crud_round_trip(repo_root: Path) -> None:
    """POST → GET → DELETE the operator-private Lab annotations. Notes are
    scoped per card and carry the freeform body on read (loopback-only;
    never mirrored — see test_mirror_does_not_leak)."""
    from fieldkit.arena.store import ArenaStore

    db_path = str(repo_root / "arena.db")
    app = create_app(repo_root=repo_root, db=db_path, telemetry_interval=2.0)
    with TestClient(app) as client:
        # Empty to start.
        assert client.get("/api/lab/notes").json()["notes"] == []

        # Pin two notes to one card + one to another.
        r = client.post(
            "/api/lab/notes",
            json={"card_id": "frontier", "body": "tighten the gold skyline", "lane": "now"},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["ok"] is True and body["n_notes"] == 1
        note_id = body["note_id"]

        client.post("/api/lab/notes", json={"card_id": "frontier", "body": "add hover labels"})
        client.post("/api/lab/notes", json={"card_id": "compare", "body": "two-local-lanes"})

        # Scoped read returns only this card's notes, newest first, with body.
        scoped = client.get("/api/lab/notes", params={"card_id": "frontier"}).json()["notes"]
        assert len(scoped) == 2
        assert scoped[0]["body"] == "add hover labels"
        assert all(n["card_id"] == "frontier" for n in scoped)

        # Unscoped read sees all three.
        assert len(client.get("/api/lab/notes").json()["notes"]) == 3

        # Delete one; 404 on a second delete of the same id.
        assert client.delete(f"/api/lab/notes/{note_id}").status_code == 200
        assert client.delete(f"/api/lab/notes/{note_id}").status_code == 404
        assert len(client.get("/api/lab/notes", params={"card_id": "frontier"}).json()["notes"]) == 1

        # Pydantic gate: empty body rejected.
        assert client.post("/api/lab/notes", json={"card_id": "x", "body": ""}).status_code == 422

    # Persistence sanity on disk.
    with ArenaStore(repo_root / "arena.db") as store:
        assert len(store.lab_notes()) == 2


def test_api_lab_notes_missing_db_returns_empty(tmp_path: Path) -> None:
    """GET on a cold DB returns an empty list, not a 500."""
    app = create_app(repo_root=tmp_path, db=str(tmp_path / "no-such.db"), telemetry_interval=2.0)
    with TestClient(app) as client:
        assert client.get("/api/lab/notes").json() == {"notes": []}


# ---------------------------------------------------------------------------
# v0.2 — OpenRouter curation + on-demand local lane resolution
# ---------------------------------------------------------------------------


def test_curate_openrouter_models_picks_newest_per_family() -> None:
    """Each family matcher keeps the single newest (by `created`) chat model;
    non-chat modalities are skipped."""
    from fieldkit.arena.server import _curate_openrouter_models

    catalog = [
        {"id": "openai/gpt-5.5", "name": "GPT-5.5", "created": 200},
        {"id": "openai/gpt-5.1", "name": "GPT-5.1", "created": 100},
        {"id": "openai/gpt-5-image", "name": "GPT-5 Image", "created": 999},
        {"id": "anthropic/claude-opus-4.8", "name": "Opus 4.8", "created": 300},
        {"id": "qwen/qwen3-8b", "name": "Qwen3 8B", "created": 50},
        {"id": "qwen/qwen3.6-max", "name": "Qwen3.6 Max", "created": 400},
        {"id": "mistralai/mistral-7b-instruct", "name": "Mistral 7B", "created": 10},
    ]
    out = _curate_openrouter_models(catalog)
    front_ids = {m["id"] for m in out["frontier"]}
    # Newest GPT (non-image) + the Opus; the image model is excluded.
    assert "openai/gpt-5.5" in front_ids
    assert "openai/gpt-5-image" not in front_ids
    assert "anthropic/claude-opus-4.8" in front_ids
    open_ids = {m["id"] for m in out["open"]}
    assert "qwen/qwen3.6-max" in open_ids  # newest Qwen3 wins
    assert "qwen/qwen3-8b" not in open_ids
    base_ids = {m["id"] for m in out["project_base"]}
    assert "qwen/qwen3-8b" in base_ids  # project-base family matches the 8B
    assert "mistralai/mistral-7b-instruct" in base_ids


def test_resolve_local_gguf_missing_returns_none(monkeypatch: pytest.MonkeyPatch) -> None:
    """A slug with no on-disk quants dir resolves to None (not a crash)."""
    from pathlib import Path as _P

    import fieldkit.arena.server as srv

    monkeypatch.setattr(srv, "_QUANTS_ROOT", _P("/nonexistent/quants/root"))
    assert srv._resolve_local_gguf("no-such-model-gguf", "Q4_K_M") is None


def test_resolve_local_gguf_prefix_match(tmp_path: Path) -> None:
    """Normalized dir-name prefix match + model-<variant>.gguf resolution."""
    import fieldkit.arena.server as srv

    d = tmp_path / "II-Medical-8B"
    d.mkdir()
    (d / "model-Q4_K_M.gguf").write_bytes(b"gguf")
    orig = srv._QUANTS_ROOT
    srv._QUANTS_ROOT = tmp_path
    try:
        hit = srv._resolve_local_gguf("ii-medical-8b-gguf", "Q4_K_M")
        assert hit is not None and hit.name == "model-Q4_K_M.gguf"
    finally:
        srv._QUANTS_ROOT = orig


def test_compare_options_endpoint_shape(
    repo_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """/api/compare/options returns local + curated openrouter groups + full list."""
    import fieldkit.arena.server as srv

    monkeypatch.setattr(srv, "_read_hermes_lane", lambda *a, **k: None)
    monkeypatch.setattr(
        srv,
        "_openrouter_catalog",
        lambda *a, **k: [
            {"id": "openai/gpt-5.5", "name": "GPT-5.5", "created": 200,
             "price_per_m_input_usd": 5.0, "price_per_m_output_usd": 25.0},
            {"id": "qwen/qwen3.6-max", "name": "Qwen3.6 Max", "created": 100,
             "price_per_m_input_usd": 1.0, "price_per_m_output_usd": 3.0},
        ],
    )
    app = create_app(repo_root=repo_root, telemetry_interval=2.0)
    with TestClient(app) as client:
        r = client.get("/api/compare/options")
        assert r.status_code == 200
        data = r.json()
        assert "local" in data
        assert set(data["openrouter_groups"]) == {"frontier", "open", "project_base"}
        assert data["catalog_size"] == 2
        assert any(o["id"] == "openrouter:openai/gpt-5.5" for o in data["openrouter"])


def test_telemetry_payload_carries_resident_lane() -> None:
    """Idle ticks surface the warm resident so the rail shows it (not 'no warm
    brain'). The hub reads it via the injected resident reader."""
    hub = TelemetryHub(interval=2.0)
    hub._resident_reader = lambda: {"model": "Qwen3-30B-A3B-Q4_K_M"}  # noqa: SLF001
    payload = hub._build_payload()  # noqa: SLF001
    assert payload["resident_lane"] == "Qwen3-30B-A3B-Q4_K_M"
    # No reader → None (e.g. tests that don't inject one).
    assert TelemetryHub(interval=2.0)._build_payload()["resident_lane"] is None  # noqa: SLF001


def test_local_load_stream_missing_gguf_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    """Loading an unknown on-demand lane yields a clean error event (no spawn)."""
    import fieldkit.arena.server as srv

    monkeypatch.setattr(srv, "_resolve_local_gguf", lambda *a, **k: None)

    async def _drive():
        evs = []
        async for ev in srv._local_load_stream("local:no-such-model::Q4_K_M"):
            evs.append(ev)
        return evs

    events = asyncio.run(_drive())
    assert any(e["event"] == "error" for e in events)
    assert not any(e["event"] == "done" for e in events)


def test_local_load_stream_resident_is_noop() -> None:
    """Loading the resident is a no-op done (it's always warm; no spawn)."""
    import fieldkit.arena.server as srv

    async def _drive():
        return [ev async for ev in srv._local_load_stream("local:resident")]

    events = asyncio.run(_drive())
    assert events and events[-1]["event"] == "done"
    assert json.loads(events[-1]["data"])["lane_id"] == "local:resident"


# ---------------------------------------------------------------------------
# v0.3 — eval-prompt benches, scoring, leaderboard
# ---------------------------------------------------------------------------


def _write_eval_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n")


@pytest.fixture
def eval_tree(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Minimal eval-benches tree wired into ``fieldkit.arena.benches``."""
    from fieldkit.arena import benches

    root = tmp_path / "eval-benches"
    _write_eval_jsonl(
        root / "medmcqa" / "medmcqa_merged.jsonl",
        [
            {"id": "mm-1", "text": "Q1?\nA) a\nB) b\nC) c\nD) d", "answer": "B", "task": "medmcqa"},
            {"id": "mm-2", "text": "Q2?\nA) a\nB) b\nC) c\nD) d", "answer": "C", "task": "medmcqa"},
        ],
    )
    _write_eval_jsonl(
        root / "patent-strategist" / "seed-A.jsonl",
        [{
            "qid": "ps-A-1", "question": "Draft a claim.", "family": "A",
            "use_case": "A1", "scoring_mode": "oracle", "gold_label": "A claim.",
            "options": [], "oracle_context": "ctx", "rubric": {"claim_type": "independent"},
        }],
    )
    monkeypatch.setattr(benches, "ARENA_EVAL_BENCHES_ROOT", root)
    benches._CACHE.clear()
    yield root
    benches._CACHE.clear()


def test_api_eval_benches_lists_and_reports_judge(
    repo_root: Path, eval_tree: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("fieldkit.arena.server._read_hermes_lane", lambda hermes_path=None: None)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    app = create_app(repo_root=repo_root, telemetry_interval=2.0)
    with TestClient(app) as client:
        r = client.get("/api/eval/benches")
        assert r.status_code == 200
        body = r.json()
        ids = {b["bench_id"]: b for b in body["benches"]}
        assert ids["medmcqa"]["available"] and ids["medmcqa"]["count"] == 2
        assert ids["patent-strategist"]["available"]
        # No resident + no key → both judge backends unavailable.
        assert body["judge"]["local_available"] is False
        assert body["judge"]["openrouter_available"] is False


def test_api_eval_prompts_pagination_and_404(repo_root: Path, eval_tree: Path) -> None:
    app = create_app(repo_root=repo_root, telemetry_interval=2.0)
    with TestClient(app) as client:
        r = client.get("/api/eval/benches/medmcqa/prompts", params={"limit": 1})
        body = r.json()
        assert body["total"] == 2 and len(body["prompts"]) == 1
        assert body["prompts"][0]["scorer_kind"] == "mcq_letter"
        assert body["prompts"][0]["reference"] in ("B", "C")
        # Unknown bench → 404 with a path hint.
        miss = client.get("/api/eval/benches/nope/prompts")
        assert miss.status_code == 404
        assert "ARENA_EVAL_BENCHES_ROOT" in miss.json()["detail"]


def test_api_chat_score_deterministic_persists_and_leaderboards(
    repo_root: Path, eval_tree: Path, tmp_path: Path
) -> None:
    """A persisted chat turn scored against an MCQ bench lands an eval_scores
    row and shows in the accuracy leaderboard."""
    from fieldkit.arena.schemas import ChatSessionRecord, ChatTurnRecord, LaneRecord
    from fieldkit.arena.store import ArenaStore

    db_path = str(tmp_path / "arena.db")
    store = ArenaStore(db_path)
    store.initialize()
    store.upsert_lane(
        LaneRecord(id="local:ii-medical-8b-gguf::Q8_0", kind="LlamaServerLane",
                   model="ii-medical-8b-gguf::Q8_0", port=8091, base_url="")
    )
    store.upsert_chat_session(
        ChatSessionRecord(id="cs-x", lane_id="local:ii-medical-8b-gguf::Q8_0",
                          created_at="2026-05-28T00:00:00Z", publishable=0)
    )
    turn_id = store.append_chat_turn(
        ChatTurnRecord(session_id="cs-x", ord=1, role="assistant",
                       content="The answer is B.", created_at="2026-05-28T00:00:01Z")
    )
    store.close()

    app = create_app(repo_root=repo_root, db=db_path, telemetry_interval=2.0)
    with TestClient(app) as client:
        r = client.post("/api/chat/score", json={
            "turn_id": turn_id, "bench_id": "medmcqa", "eval_qid": "mm-1",
            "lane_id": "local:ii-medical-8b-gguf::Q8_0",
        })
        body = r.json()
        assert body["scored"] is True and body["score"] == 1.0
        assert body["scorer_kind"] == "mcq_letter" and body["turn_id"] == turn_id
        # Leaderboard rollup picks it up (own-bench, not cross-vertical).
        lb = client.get("/api/eval/leaderboard").json()
        rows = {(r["bench_id"], r["lane_id"]): r for r in lb["rows"]}
        key = ("medmcqa", "local:ii-medical-8b-gguf::Q8_0")
        assert key in rows and rows[key]["mean_normalized"] == 1.0


def test_resident_lane_sid_resolution(monkeypatch: pytest.MonkeyPatch) -> None:
    """AD-FK-2 — resident→recipe resolution is unambiguous-only."""
    import fieldkit.arena.launcher as launcher
    from fieldkit.arena.server import _resident_lane_sid

    recipes = {
        "ii-medical-8b-gguf": {"gguf_path": "/q/II-Medical-8B-Q8_0.gguf"},
        "kepler-q8": {"gguf_path": "/q/Kepler/model-Q8_0.gguf"},
        "qwen3-8b-q8": {"gguf_path": "/q/Qwen3-8B/model-Q8_0.gguf"},
    }
    monkeypatch.setattr(launcher, "load_lane_recipes", lambda: recipes)
    # Unique basename → resolves (case-insensitive, path or bare filename).
    assert _resident_lane_sid({"model": "II-Medical-8B-Q8_0.gguf"}) == "local:ii-medical-8b-gguf"
    assert _resident_lane_sid({"model": "/q/II-Medical-8B-Q8_0.gguf"}) == "local:ii-medical-8b-gguf"
    # Two recipes share model-Q8_0.gguf → a guess would mislabel; refuse.
    assert _resident_lane_sid({"model": "model-Q8_0.gguf"}) is None
    # Full-path match disambiguates a shared basename.
    assert _resident_lane_sid({"model": "/q/Kepler/model-Q8_0.gguf"}) == "local:kepler-q8"
    assert _resident_lane_sid({"model": ""}) is None
    assert _resident_lane_sid(None) is None


def test_api_chat_score_resident_lane_resolves_for_live_island(
    repo_root: Path, eval_tree: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AD-FK-2 — a bench grade on lane_id='local:resident' persists under the
    resolved recipe lane with server-computed cross_vertical=0, so the live
    accuracy island (default excludes cross-vertical) surfaces it even though
    the client sent cross_vertical=true (it can't see what's resident)."""
    import fieldkit.arena.launcher as launcher
    from fieldkit.arena.schemas import ChatSessionRecord, ChatTurnRecord, LaneRecord
    from fieldkit.arena.store import ArenaStore

    monkeypatch.setattr(
        "fieldkit.arena.server._resolve_active_lane",
        lambda hermes_path=None: {
            "model": "II-Medical-8B-Q8_0.gguf",
            "base_url": "http://127.0.0.1:8091/v1",
            "source": "registry", "drift": None, "discovered": [], "hermes_hint": None,
        },
    )
    monkeypatch.setattr(
        launcher, "load_lane_recipes",
        lambda: {"ii-medical-8b-gguf": {"gguf_path": "/q/II-Medical-8B-Q8_0.gguf"}},
    )
    db_path = str(tmp_path / "arena.db")
    store = ArenaStore(db_path)
    store.initialize()
    store.upsert_lane(
        LaneRecord(id="local:resident", kind="LlamaServerLane",
                   model="II-Medical-8B-Q8_0.gguf", port=8091, base_url="")
    )
    store.upsert_chat_session(
        ChatSessionRecord(id="cs-r", lane_id="local:resident",
                          created_at="2026-06-12T00:00:00Z", publishable=0)
    )
    turn_id = store.append_chat_turn(
        ChatTurnRecord(session_id="cs-r", ord=1, role="assistant",
                       content="The answer is B.", created_at="2026-06-12T00:00:01Z")
    )
    store.close()

    app = create_app(repo_root=repo_root, db=db_path, telemetry_interval=2.0)
    with TestClient(app) as client:
        r = client.post("/api/chat/score", json={
            "turn_id": turn_id, "bench_id": "medmcqa", "eval_qid": "mm-1",
            "lane_id": "local:resident", "cross_vertical": True,
        })
        assert r.json()["scored"] is True
        lb = client.get("/api/eval/leaderboard").json()
        rows = {(row["bench_id"], row["lane_id"]): row for row in lb["rows"]}
        key = ("medmcqa", "local:ii-medical-8b-gguf")
        assert key in rows and rows[key]["mean_normalized"] == 1.0
        assert ("medmcqa", "local:resident") not in rows


def test_api_chat_score_missing_turn_404(repo_root: Path, eval_tree: Path, tmp_path: Path) -> None:
    db_path = str(tmp_path / "arena.db")
    ArenaStore_init(db_path)
    app = create_app(repo_root=repo_root, db=db_path, telemetry_interval=2.0)
    with TestClient(app) as client:
        r = client.post("/api/chat/score", json={"turn_id": 999, "bench_id": "medmcqa", "eval_qid": "mm-1"})
        assert r.status_code == 404


def ArenaStore_init(db_path: str) -> None:
    from fieldkit.arena.store import ArenaStore

    s = ArenaStore(db_path)
    s.initialize()
    s.close()


class _StubAnswerClient:
    """Compare-side stub that yields a fixed answer (no <think>)."""

    def __init__(self, answer: str) -> None:
        self._answer = answer

    def chat_stream(self, messages, **_kwargs):
        yield self._answer


def test_compare_eval_block_scores_both_sides(
    repo_root: Path, eval_tree: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A compare run with an eval prompt augments the score event with an
    ``eval`` block grading both sides against the bench gold."""
    from types import SimpleNamespace

    from fieldkit.arena.server import compare_event_stream

    monkeypatch.setattr(
        "fieldkit.arena.server._chat_client_factory",
        lambda resident: _StubAnswerClient("Answer: B"),  # correct vs gold "B"
    )
    monkeypatch.setattr(
        "fieldkit.arena.server._compare_b_factory",
        lambda: (_StubAnswerClient("Answer: D"), None),  # wrong
    )
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-fake")

    hub = TelemetryHub(interval=0.1)
    body = SimpleNamespace(
        prompt="Q1?", lane_a="local:resident", lane_b="openrouter",
        rubric_id=None, max_tokens=64, temperature=0.0,
        bench_id="medmcqa", eval_qid="mm-1", judge=None,
    )
    resident = {"id": "resident", "model": "qwen", "base_url": "http://127.0.0.1:8080/v1"}
    db_path = str(tmp_path / "arena.db")

    async def _drive():
        events = []
        gen = compare_event_stream(hub=hub, request=_FakeRequest(), body=body,
                                   resident=resident, db_path=db_path)
        async for ev in gen:
            events.append(ev)
            if ev["event"] == "score":
                break
        await gen.aclose()
        return events

    events = asyncio.run(_drive())
    # start events carry the eval_context transparency block.
    start_a = json.loads(next(e["data"] for e in events if e["event"] == "start_a"))
    assert start_a["eval_context"]["bench_id"] == "medmcqa"
    score = json.loads(events[-1]["data"])
    assert "eval" in score
    assert score["eval"]["scorer_kind"] == "mcq_letter"
    assert score["eval"]["reference"] == "B"
    assert score["eval"]["a"]["score"] == 1.0
    assert score["eval"]["b"]["score"] == 0.0


# --- AD-AE-17 — eval mode replays the bench's measured reasoning control ---


@pytest.fixture
def advisor_tree(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Minimal Advisor evidence dir (one held-out row + its measured packet)
    wired through the FK_ARENA_ADVISOR_DIR root override."""
    from fieldkit.arena import benches

    root = tmp_path / "advisor-evidence"
    _write_eval_jsonl(
        root / "advisor-bench-v0.1.heldout.jsonl",
        [{
            "task_id": "advisor-qa-0001", "split": "heldout",
            "family": "cited_factual_qa", "expected_behavior": "answer",
            "question": "What does artifact_x ship?",
            "expected_answer": "It ships Y. Citations: [artifact_x]",
            "expected_citations": ["artifact_x"], "source_ids": ["artifact_x"],
        }],
    )
    _write_eval_jsonl(
        root / "advisor-preflight-4b-wide-nohint-v0.1.prompts.jsonl",
        [{
            "task_id": "advisor-qa-0001",
            "messages": [
                {"role": "system", "content": "/no_think\nYou are Orionfold Advisor."},
                {"role": "user", "content": (
                    "Question: What does artifact_x ship?\n\n"
                    "Retrieved public context:\nSource 1: artifact_x\nExcerpt: ships Y."
                )},
            ],
        }],
    )
    monkeypatch.setenv("FK_ARENA_ADVISOR_DIR", str(root))
    benches._CACHE.clear()
    yield root
    benches._CACHE.clear()


class _KwargRecordingClient:
    """Stub that records the (messages, kwargs) of every chat_stream call."""

    def __init__(self, answer: str) -> None:
        self._answer = answer
        self.calls: list[tuple[list[dict[str, str]], dict]] = []

    def chat_stream(self, messages, **kwargs):
        self.calls.append((list(messages), dict(kwargs)))
        yield self._answer


def _drive_chat(body, monkeypatch, stub, db_path: str) -> list[dict[str, str]]:
    from fieldkit.arena.server import chat_event_stream

    monkeypatch.setattr(
        "fieldkit.arena.server._chat_client_factory", lambda resident: stub
    )
    hub = TelemetryHub(interval=0.1)
    resident = {"id": "resident", "model": "qwen", "base_url": "http://127.0.0.1:8080/v1"}

    async def _run():
        events = []
        gen = chat_event_stream(hub=hub, request=_FakeRequest(), body=body,
                                resident=resident, db_path=db_path)
        async for ev in gen:
            events.append(ev)
            if ev["event"] == "done":
                break
        await gen.aclose()
        return events

    return asyncio.run(_run())


def test_chat_eval_mode_replays_reasoning_kwargs_on_local_lane(
    repo_root: Path, advisor_tree: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An Advisor eval row through chat sends BOTH measured reasoning controls
    to the local lane — the /no_think system contract AND
    ``chat_template_kwargs={"enable_thinking": False}`` — and surfaces
    ``reasoning_mode`` in the start event's eval_context (AD-AE-17: without
    the kwarg, Nemotron-3 templates think anyway and the row can fabricate)."""
    from types import SimpleNamespace

    stub = _KwargRecordingClient("It ships Y. Citations: [artifact_x]")
    body = SimpleNamespace(
        prompt="What does artifact_x ship?", session_id=None, rubric_id=None,
        max_tokens=64, temperature=0.0, lane="local:resident",
        bench_id="advisor-bench", eval_qid="advisor-qa-0001",
    )
    events = _drive_chat(body, monkeypatch, stub, str(tmp_path / "arena.db"))
    start = json.loads(events[0]["data"])
    assert start["eval_context"]["system_attached"] is True
    assert start["eval_context"]["reasoning_mode"] == "off"
    messages, kwargs = stub.calls[0]
    assert messages[0]["role"] == "system"
    assert messages[0]["content"].startswith("/no_think")
    assert kwargs["chat_template_kwargs"] == {"enable_thinking": False}


def test_chat_eval_mode_no_rider_for_unridden_bench(
    repo_root: Path, eval_tree: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Benches without a reasoning rider keep the exact pre-AD-AE-17 payload —
    no ``chat_template_kwargs``, no ``reasoning_mode`` in eval_context."""
    from types import SimpleNamespace

    stub = _KwargRecordingClient("Answer: B")
    body = SimpleNamespace(
        prompt="Q1?", session_id=None, rubric_id=None,
        max_tokens=64, temperature=0.0, lane="local:resident",
        bench_id="medmcqa", eval_qid="mm-1",
    )
    events = _drive_chat(body, monkeypatch, stub, str(tmp_path / "arena.db"))
    start = json.loads(events[0]["data"])
    assert "reasoning_mode" not in start["eval_context"]
    messages, kwargs = stub.calls[0]
    assert [m["role"] for m in messages] == ["user"]
    assert "chat_template_kwargs" not in kwargs


def test_compare_eval_mode_reasoning_kwargs_local_side_only(
    repo_root: Path, advisor_tree: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Compare forwards the rider to the LOCAL side only; the hosted side keeps
    the measured no-kwarg shape (§13.F bakeoff tiers ran without it)."""
    from types import SimpleNamespace

    from fieldkit.arena.server import compare_event_stream

    a = _KwargRecordingClient("It ships Y. Citations: [artifact_x]")
    b = _KwargRecordingClient("Hosted: ships Y. Citations: [artifact_x]")
    monkeypatch.setattr(
        "fieldkit.arena.server._chat_client_factory", lambda resident: a
    )
    monkeypatch.setattr(
        "fieldkit.arena.server._compare_b_factory", lambda: (b, None)
    )
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-fake")

    hub = TelemetryHub(interval=0.1)
    body = SimpleNamespace(
        prompt="What does artifact_x ship?", lane_a="local:resident",
        lane_b="openrouter", rubric_id=None, max_tokens=64, temperature=0.0,
        bench_id="advisor-bench", eval_qid="advisor-qa-0001", judge=None,
    )
    resident = {"id": "resident", "model": "qwen", "base_url": "http://127.0.0.1:8080/v1"}

    async def _drive():
        events = []
        gen = compare_event_stream(hub=hub, request=_FakeRequest(), body=body,
                                   resident=resident,
                                   db_path=str(tmp_path / "arena.db"))
        async for ev in gen:
            events.append(ev)
            if ev["event"] == "score":
                break
        await gen.aclose()
        return events

    asyncio.run(_drive())
    _, kwargs_a = a.calls[0]
    _, kwargs_b = b.calls[0]
    assert kwargs_a["chat_template_kwargs"] == {"enable_thinking": False}
    assert "chat_template_kwargs" not in kwargs_b


def test_trip_sentinels_includes_running_lane_launch(tmp_path: Path, monkeypatch) -> None:
    """AE-31 — a running lane_launch polls the same per-job sentinel during its
    warm-poll: a sidecar SIGTERM must abort the poll (the job), never hang the
    drain (BUG-2 shape). The detached lane itself is not the sidecar's child."""
    from fieldkit.arena import jobs
    from fieldkit.arena.guardrail import eval_sentinel_for
    from fieldkit.arena.jobs import JobKind, JobStatus
    from fieldkit.arena.server import _trip_running_eval_sentinels
    from fieldkit.arena.store import ArenaStore

    monkeypatch.setenv("FK_EVAL_SENTINEL_DIR", str(tmp_path / "sentinels"))
    db = tmp_path / "arena.db"
    store = ArenaStore(db)
    store.initialize()
    launch_id = jobs.enqueue_job(store, JobKind.LANE_LAUNCH, {"recipe": "kepler-q8"})
    store.update_job(launch_id, status=JobStatus.RUNNING)
    store.close()

    assert _trip_running_eval_sentinels(str(db)) == 1
    assert eval_sentinel_for(launch_id).exists()


# ---------------------------------------------------------------------------
# v0.4 — Cortex-grounded chat (live retrieval over the Advisor corpus pack)
# ---------------------------------------------------------------------------


_CANNED_PACKET = {
    "system": "/no_think\nYou are Orionfold Advisor. …",
    "user_prompt": (
        "Question: hermes brain?\n\n"
        "Retrieved public context:\nSource 1: src_a\nLabel: Field Note: Alpha\n"
        "Class: field_note / book2_field_note\nTitle: Alpha\nExcerpt: pinned."
    ),
    "chat_kwargs": {"chat_template_kwargs": {"enable_thinking": False}},
    "retrieval": {
        "table": "advisor_corpus_v01",
        "manifest_sha256_12": "6b1e832d099c",
        "top_k": 3,
        "chunk_pool": 80,
        "sources": [
            {"source_id": "src_a", "title": "Alpha",
             "citation_label": "Field Note: Alpha", "dist": 0.1}
        ],
    },
}


def test_chat_retrieval_grounds_free_prompt(
    repo_root: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``retrieval: true`` on a free prompt sends the packet system contract +
    the retrieved-context user prompt + the reasoning-off rider to the local
    lane, and pins the retrieval receipt on the ``start`` event."""
    from types import SimpleNamespace

    import copy

    captured: list[str] = []

    def _fake_build_packet(question, *, root, **_kw):
        captured.append(question)
        return copy.deepcopy(_CANNED_PACKET)

    monkeypatch.setattr("fieldkit.arena.cortex_chat.build_packet", _fake_build_packet)

    stub = _KwargRecordingClient("Pinned to Qwen3-30B-A3B. Citations: [src_a]")
    body = SimpleNamespace(
        prompt="hermes brain?", session_id=None, rubric_id=None,
        max_tokens=64, temperature=0.0, lane="local:resident",
        retrieval=True,
    )
    events = _drive_chat(body, monkeypatch, stub, str(tmp_path / "arena.db"))

    assert captured == ["hermes brain?"]
    start = json.loads(events[0]["data"])
    assert start["retrieval"]["table"] == "advisor_corpus_v01"
    assert start["retrieval"]["sources"][0]["source_id"] == "src_a"
    assert start["retrieval"]["truncated"] is False

    messages, kwargs = stub.calls[0]
    assert messages[0]["role"] == "system"
    assert messages[0]["content"].startswith("/no_think")
    assert messages[1]["content"].startswith("Question: hermes brain?")
    assert "Retrieved public context" in messages[1]["content"]
    assert kwargs["chat_template_kwargs"] == {"enable_thinking": False}


def test_chat_retrieval_failure_is_a_hard_error(
    repo_root: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A dead Cortex stack yields an ``error`` event and NO generation — an
    ungrounded turn must never masquerade as a grounded one."""
    from types import SimpleNamespace

    from fieldkit.arena.cortex_chat import CortexUnavailable

    def _down(question, *, root, **_kw):
        raise CortexUnavailable("pgvector connect failed (…)")

    monkeypatch.setattr("fieldkit.arena.cortex_chat.build_packet", _down)

    stub = _KwargRecordingClient("should never stream")
    body = SimpleNamespace(
        prompt="hermes brain?", session_id=None, rubric_id=None,
        max_tokens=64, temperature=0.0, lane="local:resident",
        retrieval=True,
    )
    events = _drive_chat(body, monkeypatch, stub, str(tmp_path / "arena.db"))

    kinds = [ev["event"] for ev in events]
    assert "error" in kinds and "token" not in kinds
    err = json.loads([ev for ev in events if ev["event"] == "error"][0]["data"])
    assert "Cortex retrieval unavailable" in err["detail"]
    assert stub.calls == []


def test_chat_eval_mode_wins_over_retrieval(
    repo_root: Path, advisor_tree: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``bench_id``+``eval_qid`` replay the measured frozen packet even when
    ``retrieval`` is also set — live retrieval never contaminates an eval."""
    from types import SimpleNamespace

    def _never(question, *, root, **_kw):  # pragma: no cover - must not run
        raise AssertionError("live retrieval ran inside eval mode")

    monkeypatch.setattr("fieldkit.arena.cortex_chat.build_packet", _never)

    stub = _KwargRecordingClient("It ships Y. Citations: [artifact_x]")
    body = SimpleNamespace(
        prompt="What does artifact_x ship?", session_id=None, rubric_id=None,
        max_tokens=64, temperature=0.0, lane="local:resident",
        bench_id="advisor-bench", eval_qid="advisor-qa-0001",
        retrieval=True,
    )
    events = _drive_chat(body, monkeypatch, stub, str(tmp_path / "arena.db"))
    start = json.loads(events[0]["data"])
    assert "eval_context" in start
    assert "retrieval" not in start


def test_compare_options_carries_retrieval_source(
    repo_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The options payload labels the corpus pack ``retrieval: true`` chat
    grounds in — degrading to ``available: False`` on a manifest-less box so
    the UI can warn instead of implying a grounded lane exists."""
    import fieldkit.arena.server as srv

    monkeypatch.setattr(srv, "_read_hermes_lane", lambda *a, **k: None)
    monkeypatch.setattr(srv, "_openrouter_catalog", lambda *a, **k: [])
    app = create_app(repo_root=repo_root, telemetry_interval=2.0)
    with TestClient(app) as client:
        data = client.get("/api/compare/options").json()
        src = data["retrieval_source"]
        assert src["available"] is False  # fixture repo has no manifest
        assert src["table"]  # table name still surfaced for the warn label


# ---------------------------------------------------------------------------
# grounded-eval-v1 §8 — free-prompt ±Cortex ablation duel (per-side retrieval)
# ---------------------------------------------------------------------------


def _drive_compare(body, monkeypatch, stub_a, stub_b, db_path: str) -> list[dict[str, str]]:
    from fieldkit.arena.server import compare_event_stream

    monkeypatch.setattr(
        "fieldkit.arena.server._chat_client_factory", lambda resident: stub_a
    )
    monkeypatch.setattr(
        "fieldkit.arena.server._compare_b_factory", lambda: (stub_b, None)
    )
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-fake")
    hub = TelemetryHub(interval=0.1)
    resident = {
        "id": "resident-brain",
        "model": "qwen-fixture",
        "base_url": "http://127.0.0.1:8080/v1",
    }

    async def _run():
        events = []
        gen = compare_event_stream(
            hub=hub, request=_FakeRequest(), body=body,
            resident=resident, db_path=db_path,
        )
        async for ev in gen:
            events.append(ev)
            if ev["event"] in ("score", "error"):
                break
        await gen.aclose()
        return events

    return asyncio.run(_run())


def test_compare_ablation_grounds_only_flagged_side(
    repo_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``retrieval_a: true`` on a free prompt grounds ONLY side A: A streams
    the packet (system contract + retrieved context + reasoning-off rider) and
    its start event carries the receipt; B streams the bare prompt with no
    receipt. The score event labels the ablation so the verdict is honest."""
    import copy
    from types import SimpleNamespace

    calls: list[str] = []

    def _fake_build_packet(question, *, root, **_kw):
        calls.append(question)
        return copy.deepcopy(_CANNED_PACKET)

    monkeypatch.setattr("fieldkit.arena.cortex_chat.build_packet", _fake_build_packet)

    stub_a = _KwargRecordingClient("Pinned to Qwen3-30B-A3B. Citations: [src_a]")
    stub_b = _KwargRecordingClient("Ungrounded guess.")
    stub_b.api_key = "fake-key-so-no-stub"
    body = SimpleNamespace(
        prompt="hermes brain?", lane_b="openrouter", rubric_id="generic-correctness",
        max_tokens=64, temperature=0.0, retrieval_a=True, retrieval_b=False,
    )
    events = _drive_compare(body, monkeypatch, stub_a, stub_b, str(repo_root / "arena.db"))

    # Packet built exactly ONCE (shared across flagged sides by construction).
    assert calls == ["hermes brain?"]

    start_a = json.loads([e for e in events if e["event"] == "start_a"][0]["data"])
    start_b = json.loads([e for e in events if e["event"] == "start_b"][0]["data"])
    assert start_a["retrieval"]["table"] == "advisor_corpus_v01"
    assert start_a["retrieval"]["sources"][0]["source_id"] == "src_a"
    assert start_a["retrieval"]["truncated"] is False
    assert "retrieval" not in start_b

    # A got the packet contract; B got the bare prompt, no system, no rider.
    msgs_a, kwargs_a = stub_a.calls[0]
    assert msgs_a[0]["role"] == "system"
    assert msgs_a[0]["content"].startswith("/no_think")
    assert "Retrieved public context" in msgs_a[1]["content"]
    assert kwargs_a["chat_template_kwargs"] == {"enable_thinking": False}
    msgs_b, _kwargs_b = stub_b.calls[0]
    assert msgs_b[0]["role"] == "user"
    assert msgs_b[0]["content"] == "hermes brain?"

    score = json.loads(events[-1]["data"])
    assert score["retrieval_ablation"] == {"a": True, "b": False}


def test_compare_ablation_cortex_down_is_a_hard_error(
    repo_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Cortex down on an ablation duel errors BEFORE any side streams — an
    ungrounded side must never be presented as the grounded arm."""
    from types import SimpleNamespace

    from fieldkit.arena.cortex_chat import CortexUnavailable

    def _down(question, *, root, **_kw):
        raise CortexUnavailable("pgvector connect failed (…)")

    monkeypatch.setattr("fieldkit.arena.cortex_chat.build_packet", _down)

    stub_a = _KwargRecordingClient("never")
    stub_b = _KwargRecordingClient("never")
    stub_b.api_key = "fake-key-so-no-stub"
    body = SimpleNamespace(
        prompt="hermes brain?", lane_b="openrouter", rubric_id=None,
        max_tokens=64, temperature=0.0, retrieval_a=False, retrieval_b=True,
    )
    events = _drive_compare(body, monkeypatch, stub_a, stub_b, str(repo_root / "arena.db"))
    kinds = [ev["event"] for ev in events]
    assert "error" in kinds and "start_a" not in kinds
    err = json.loads([ev for ev in events if ev["event"] == "error"][0]["data"])
    assert "Cortex retrieval unavailable" in err["detail"]
    assert stub_a.calls == [] and stub_b.calls == []


def test_compare_eval_mode_ignores_per_side_flags(
    repo_root: Path, advisor_tree: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Eval mode wins: a frozen-packet bench row replays its measured packet
    even when an ablation flag is set — per-side live retrieval never
    contaminates an eval, and the score event carries no ablation label."""
    from types import SimpleNamespace

    def _never(question, *, root, **_kw):  # pragma: no cover - must not run
        raise AssertionError("live retrieval ran inside eval mode")

    monkeypatch.setattr("fieldkit.arena.cortex_chat.build_packet", _never)

    stub_a = _KwargRecordingClient("It ships Y. Citations: [artifact_x]")
    stub_b = _KwargRecordingClient("It ships Y. Citations: [artifact_x]")
    stub_b.api_key = "fake-key-so-no-stub"
    body = SimpleNamespace(
        prompt="What does artifact_x ship?", lane_b="openrouter", rubric_id=None,
        max_tokens=64, temperature=0.0,
        bench_id="advisor-bench", eval_qid="advisor-qa-0001",
        retrieval_a=True, retrieval_b=True,
    )
    events = _drive_compare(body, monkeypatch, stub_a, stub_b, str(repo_root / "arena.db"))
    start_a = json.loads([e for e in events if e["event"] == "start_a"][0]["data"])
    assert "eval_context" in start_a
    assert "retrieval" not in start_a
    score = json.loads(events[-1]["data"])
    assert "retrieval_ablation" not in score
