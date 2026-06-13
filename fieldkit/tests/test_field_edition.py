# Copyright 2026 Manav Sehgal
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for fieldkit.field_edition (Arena Field Edition installer surface).

The matrix verdict (:func:`evaluate_matrix`) is a pure function over probed
strings, so these tests are box-independent — no DGX hardware required. The
live probe layer is exercised only for "does not raise / returns the right
keys"; its values depend on the host.
"""

from __future__ import annotations

import fieldkit.field_edition.doctor as doctor_mod
from fieldkit.cli import app
from fieldkit.field_edition import (
    TESTED_MATRIX,
    DoctorReport,
    evaluate_matrix,
    parse_version,
    probe_environment,
)
from typer.testing import CliRunner

runner = CliRunner()


# --- parse_version -----------------------------------------------------------


def test_parse_version_dotted() -> None:
    assert parse_version("580.159.03") == (580, 159, 3)


def test_parse_version_embedded() -> None:
    assert parse_version("CUDA Version: 13.0") == (13, 0)


def test_parse_version_none_and_garbage() -> None:
    assert parse_version(None) is None
    assert parse_version("no version here") is None


# --- evaluate_matrix ---------------------------------------------------------


def _all_green_probes() -> dict[str, str | None]:
    return {
        "dgx_os": "7.2.3",
        "driver": "580.95.05",
        "cuda": "13.0",
        "docker": "Docker version 29.2.1, build a5c7197",
        "container_toolkit": "NVIDIA Container Toolkit CLI version 1.19.1",
    }


def test_exact_baseline_passes() -> None:
    report = evaluate_matrix(_all_green_probes())
    assert isinstance(report, DoctorReport)
    assert report.ok
    assert report.failures == ()


def test_newer_than_tested_still_passes() -> None:
    """A box ahead of the tested baseline (DGX OS churn) must NOT be refused."""
    probes = _all_green_probes()
    probes["dgx_os"] = "7.5.0"
    probes["driver"] = "580.159.03"
    report = evaluate_matrix(probes)
    assert report.ok, [f.reason for f in report.failures]


def test_too_old_driver_fails_with_fix() -> None:
    probes = _all_green_probes()
    probes["driver"] = "535.10.01"
    report = evaluate_matrix(probes)
    assert not report.ok
    driver = next(r for r in report.results if r.key == "driver")
    assert driver.status == "too_old"
    assert "older than the tested minimum" in driver.reason
    assert driver.fix  # a fix is always offered


def test_missing_docker_fails() -> None:
    probes = _all_green_probes()
    probes["docker"] = None
    report = evaluate_matrix(probes)
    assert not report.ok
    docker = next(r for r in report.results if r.key == "docker")
    assert docker.status == "missing"


def test_missing_version_probe_is_missing_not_crash() -> None:
    probes = _all_green_probes()
    probes["cuda"] = None
    report = evaluate_matrix(probes)
    cuda = next(r for r in report.results if r.key == "cuda")
    assert cuda.status == "missing"


def test_matrix_covers_the_seven_spec_axes() -> None:
    keys = {c.key for c in TESTED_MATRIX}
    assert keys == {"dgx_os", "driver", "cuda", "docker", "container_toolkit"}


# --- probe layer (host-dependent, just smoke it) -----------------------------


def test_probe_environment_returns_all_keys() -> None:
    probes = probe_environment()
    assert set(probes) == {c.key for c in TESTED_MATRIX}


# --- CLI surface -------------------------------------------------------------


def test_field_edition_help_lists_full_surface() -> None:
    result = runner.invoke(app, ["field-edition", "--help"])
    assert result.exit_code == 0
    for cmd in ("doctor", "up", "verify", "down", "repair", "rollback", "update"):
        assert cmd in result.stdout


def test_doctor_table_ok(monkeypatch) -> None:
    monkeypatch.setattr(doctor_mod, "run_doctor", lambda *a, **k: evaluate_matrix(_all_green_probes()))
    result = runner.invoke(app, ["field-edition", "doctor"])
    assert result.exit_code == 0
    assert "Matrix OK" in result.stdout


def test_doctor_json_failure_exit_1(monkeypatch) -> None:
    probes = _all_green_probes()
    probes["driver"] = "535.10.01"
    monkeypatch.setattr(doctor_mod, "run_doctor", lambda *a, **k: evaluate_matrix(probes))
    result = runner.invoke(app, ["field-edition", "doctor", "--json"])
    assert result.exit_code == 1
    assert '"ok": false' in result.stdout
    assert '"status": "too_old"' in result.stdout


def test_stub_commands_exit_with_milestone_marker() -> None:
    for cmd in ("up", "verify", "down", "rollback", "update"):
        result = runner.invoke(app, ["field-edition", cmd])
        assert result.exit_code != 0
        assert "stub" in result.stdout or "stub" in str(result.exception)
