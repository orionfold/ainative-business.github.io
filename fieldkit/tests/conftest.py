# Copyright 2026 Manav Sehgal
# SPDX-License-Identifier: Apache-2.0
"""pytest fixtures + the `--spark` integration-test gate.

`--spark` enables the marker `pytest.mark.spark`, which guards tests that
need a live NIM / pgvector on the DGX Spark. Without the flag those tests
are skipped, so `pytest tests/` stays green on any laptop.
"""

from __future__ import annotations

import pytest


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--spark",
        action="store_true",
        default=False,
        help="Run integration tests that require live Spark services (NIM, pgvector, etc.).",
    )


def pytest_collection_modifyitems(
    config: pytest.Config, items: list[pytest.Item]
) -> None:
    if config.getoption("--spark"):
        return
    skip_spark = pytest.mark.skip(reason="needs --spark (live NIM / pgvector required)")
    for item in items:
        if "spark" in item.keywords:
            item.add_marker(skip_spark)


@pytest.fixture(autouse=True)
def _isolate_reward_signal_dir(tmp_path, monkeypatch):
    """Keep the AE-1 ``rl_run`` reward-signal writer out of the repo (test hygiene).

    ``fieldkit.arena.lane.reward_signal_writer`` defaults its output dir to
    ``ARENA_REPO_ROOT``/``cwd`` + ``evidence/astrodynamics`` (the dir the cockpit
    reward gauge auto-follows). Under pytest that resolves into the checkout, so
    an arbitered ``rl_run`` drain test would drop ``av10-preflight-rl-*.json``
    files into ``fieldkit/evidence/``. Pin it to a per-test tmp dir; a test that
    needs a specific location still overrides this env or passes ``reward_dir=``.
    """
    monkeypatch.setenv("FK_ARENA_REWARD_DIR", str(tmp_path / "reward-signal"))


@pytest.fixture(autouse=True)
def _no_live_price_fetch(monkeypatch):
    """The offline suite never reads the live OpenRouter catalog (BUG-3 path).

    ``_run_eval_guarded`` does a best-effort price-at-dispatch capture when a
    cloud model is unpriced — a real HTTP GET in production. Gate it off here
    (the honest offline behavior: still-unpriced ⇒ tokens-only); a test
    exercising the capture path re-enables the env and injects a fake fetcher.
    """
    monkeypatch.setenv("FK_EVAL_PRICE_AT_DISPATCH", "0")


@pytest.fixture(autouse=True)
def _isolate_arena_db_and_sentinels(tmp_path, monkeypatch):
    """Never let a test touch the operator's real arena db or eval sentinels.

    ``create_app(db=None)`` resolves ``ARENA_DB`` (env) before the packaged
    default ``~/.fieldkit/arena.db`` — without this pin, every TestClient
    lifespan (BUG-2 orphan reconcile at startup, G1 sentinel trip at shutdown)
    would run against the operator's **live** store, e.g. failing a genuinely
    running overnight ``rl_run`` or aborting a real cloud eval mid-suite.
    """
    monkeypatch.setenv("ARENA_DB", str(tmp_path / "arena-isolated.db"))
    monkeypatch.setenv("FK_EVAL_SENTINEL_DIR", str(tmp_path / "eval-sentinels"))
    # The eval-bench registry (`resolve_bench` + the AF-27 verifier lookup)
    # defaults to the operator's real ~/.fieldkit/arena/benches — pin it too,
    # so e.g. the astro honest-skip test can't find the box's real verifier.
    monkeypatch.setenv("ARENA_BENCH_DIR", str(tmp_path / "bench-registry"))


@pytest.fixture(autouse=True)
def _isolate_job_owner_dir(tmp_path, monkeypatch):
    """Keep the BUG-2 job owner stamps out of the real ``~/.fieldkit`` (test hygiene).

    ``fieldkit.arena.jobs.dispatch_job`` stamps ``owner-<job_id>.json`` at the
    ``running`` flip and the sidecar's startup reconciler reads/unlinks it; both
    default to ``~/.fieldkit/arena/owners``. Pin to a per-test tmp dir so the
    suite never touches (or is confused by) the operator's live stamps.
    """
    monkeypatch.setenv("FK_ARENA_OWNER_DIR", str(tmp_path / "job-owners"))


@pytest.fixture(autouse=True)
def _isolate_lane_truth(tmp_path, monkeypatch):
    """Keep lane discovery hermetic + the active-lane registry out of the real home.

    ``server._resolve_active_lane`` calls ``fieldkit.arena.lanes.discover_cached``,
    which probes real serving ports (e.g. a live llama.cpp lane on :8091 during an
    operator smoke). Under pytest that makes lane-dependent tests flaky against
    whatever happens to be serving on the box. Neutralize discovery to ``[]`` by
    default — tests that exercise discovery call ``lanes.discover``/``probe_port``
    with the HTTP layer mocked, or pass ``discovered=`` to ``resolve_active_lane``
    — and pin the Arena-owned registry to a per-test tmp dir.
    """
    from fieldkit.arena import lanes

    monkeypatch.setattr(lanes, "discover_cached", lambda *a, **k: [])
    lanes._discover_cache.update(t=0.0, key=None, v=None)
    monkeypatch.setenv("FK_ARENA_LANE_DIR", str(tmp_path / "lane-registry"))
    monkeypatch.delenv("FK_ARENA_LANE_PATH", raising=False)
    monkeypatch.delenv("FK_ARENA_LANE_PORTS", raising=False)
