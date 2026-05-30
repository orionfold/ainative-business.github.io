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
