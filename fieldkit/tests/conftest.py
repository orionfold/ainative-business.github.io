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
