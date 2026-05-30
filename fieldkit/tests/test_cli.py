# Copyright 2026 Manav Sehgal
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for fieldkit.cli.

The CLI is a thin Typer wrapper over the existing module APIs. We assert
on its output formatting and exit codes rather than reproducing the
underlying numeric tests already covered in test_capabilities.py.

The `bench rag` subcommand is exercised under the `--spark` integration
gate (see tests/test_rag_spark.py for analogous live tests); offline we
just confirm `bench rag --help` parses.
"""

from __future__ import annotations

from typer.testing import CliRunner

from fieldkit import __version__
from fieldkit.cli import app


runner = CliRunner()


def test_version_prints_package_version() -> None:
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert __version__ in result.stdout


def test_envelope_known_key() -> None:
    result = runner.invoke(app, ["envelope", "70B params fp8"])
    assert result.exit_code == 0
    # The rule string from spark-capabilities.json mentions "70 GB weights".
    assert "70" in result.stdout


def test_envelope_unknown_key_exits_2() -> None:
    result = runner.invoke(app, ["envelope", "garbage-size"])
    assert result.exit_code == 2
    assert "no envelope rule" in result.stderr or "no envelope rule" in result.output


def test_feasibility_llama70b_fp8() -> None:
    result = runner.invoke(
        app, ["feasibility", "llama-3.1-70b", "--ctx", "4096", "--batch", "32", "--dtype", "fp8"]
    )
    assert result.exit_code == 0
    out = result.stdout
    assert "llama-3.1-70b" in out
    assert "DGX Spark" in out
    assert "weights (fp8)" in out
    assert "KV cache (fp8)" in out
    # 70B params @ fp8 = 70 GB; the row shows "70.0 GB".
    assert "70.0 GB" in out


def test_feasibility_unknown_model_exits_2() -> None:
    result = runner.invoke(app, ["feasibility", "nope-9000"])
    assert result.exit_code == 2
    assert "unknown model id" in result.stderr or "unknown model id" in result.output


def test_feasibility_bad_dtype_exits_2() -> None:
    result = runner.invoke(
        app, ["feasibility", "llama-3.1-8b", "--dtype", "fp17"]
    )
    assert result.exit_code == 2


def test_bench_rag_help_lists_options() -> None:
    result = runner.invoke(app, ["bench", "rag", "--help"])
    assert result.exit_code == 0
    assert "--embed-url" in result.stdout
    assert "--nim-url" in result.stdout
    assert "--pgvector-dsn" in result.stdout


def test_top_level_help_lists_commands() -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "version" in result.stdout
    assert "envelope" in result.stdout
    assert "feasibility" in result.stdout
    assert "bench" in result.stdout
