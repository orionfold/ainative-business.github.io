# Copyright 2026 Manav Sehgal
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for `fieldkit.quant`.

Covers:
- GGUF_VARIANTS canonical tuple lock.
- parse_perplexity_output across the llama.cpp output shapes seen in the wild.
- parse_llama_bench_output for tg + pp metric rows.
- LlamaCppPaths resolve + require semantics.
- ThermalProbe sustained_load_minutes derivation.
- quantize_gguf dry-run command enumeration.
- Format stubs raise NotImplementedError with the roadmap hint.

Pure-stdlib module — runs offline. No llama.cpp binary required because the
`dry_run=True` path emits commands into `report.notes` instead of running them.
The live-quantize path is exercised only as an offline-skipped marker if
binaries are present (left out of v0.4; integration tests can opt in later).
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from fieldkit.quant import (
    GGUF_VARIANTS,
    LlamaCppNotFound,
    LlamaCppPaths,
    QuantError,
    QuantReport,
    ThermalProbe,
    ThermalReading,
    measure_perplexity_gguf,
    measure_tokens_per_sec_gguf,
    parse_llama_bench_output,
    parse_perplexity_output,
    quantize_awq,
    quantize_exl3,
    quantize_gguf,
    quantize_gptq,
    quantize_mlx,
    quantize_nvfp4,
)
from fieldkit.quant import _human_bytes, _parse_nvidia_smi_csv


# ---------------- canonical variants --------------------------------------


def test_gguf_variants_locked_in() -> None:
    # HANDOFF §2 specifies this exact set + order for Orionfold quants.
    assert GGUF_VARIANTS == ("Q4_K_M", "Q5_K_M", "Q6_K", "Q8_0", "F16")


# ---------------- parse_perplexity_output ---------------------------------


def test_parse_perplexity_final_estimate_line() -> None:
    text = "[1]4.5,[2]5.0,[3]7.1\nFinal estimate: PPL = 7.123 +/- 0.045\n"
    assert parse_perplexity_output(text) == pytest.approx(7.123)


def test_parse_perplexity_lowercase_perplexity_line() -> None:
    text = "Computing ...\nperplexity = 8.501\n"
    assert parse_perplexity_output(text) == pytest.approx(8.501)


def test_parse_perplexity_returns_last_match_when_multiple() -> None:
    text = "Final estimate: PPL = 9.000\nFinal estimate: PPL = 7.500"
    assert parse_perplexity_output(text) == pytest.approx(7.500)


def test_parse_perplexity_empty_or_unrelated_returns_none() -> None:
    assert parse_perplexity_output("") is None
    assert parse_perplexity_output("nothing about ppl here") is None


def test_parse_perplexity_rejects_nan_inf_strings() -> None:
    assert parse_perplexity_output("Final estimate: PPL = nan") is None
    assert parse_perplexity_output("Final estimate: PPL = inf") is None


# ---------------- parse_llama_bench_output --------------------------------


_BENCH_OUTPUT = """\
| model       | size  | params  | backend    | ngl | test  |              t/s |
| ----------- | ----- | ------- | ---------- | --- | ----- | ---------------- |
| llama 8B    | 5GiB  | 8.03 B  | CUDA       | 99  | pp 512 | 145.67 ± 0.87  |
| llama 8B    | 5GiB  | 8.03 B  | CUDA       | 99  | tg 128 |  23.45 ± 0.12  |
"""


def test_parse_llama_bench_tg_metric() -> None:
    assert parse_llama_bench_output(_BENCH_OUTPUT, metric="tg") == pytest.approx(23.45)


def test_parse_llama_bench_pp_metric() -> None:
    assert parse_llama_bench_output(_BENCH_OUTPUT, metric="pp") == pytest.approx(145.67)


def test_parse_llama_bench_no_match_returns_none() -> None:
    assert parse_llama_bench_output("nothing", metric="tg") is None


# ---------------- _parse_nvidia_smi_csv -----------------------------------


def test_parse_nvidia_smi_csv_well_formed() -> None:
    temp, sm = _parse_nvidia_smi_csv("85, 1980")
    assert temp == 85.0
    assert sm == 1980.0


def test_parse_nvidia_smi_csv_handles_blank() -> None:
    temp, sm = _parse_nvidia_smi_csv("")
    assert temp == 0.0
    assert sm == 0.0


def test_parse_nvidia_smi_csv_handles_garbage() -> None:
    temp, sm = _parse_nvidia_smi_csv("not-a-number, another")
    assert temp == 0.0
    assert sm == 0.0


# ---------------- _human_bytes -------------------------------------------


def test_human_bytes_table() -> None:
    assert _human_bytes(None) == ""
    assert _human_bytes(0) == "0 B"
    assert _human_bytes(100) == "100 B"
    assert _human_bytes(1024) == "1.0 KB"
    assert _human_bytes(1024 * 1024) == "1.0 MB"
    assert _human_bytes(1024 * 1024 * 1024) == "1.0 GB"


# ---------------- LlamaCppPaths ------------------------------------------


def test_llama_cpp_paths_resolve_returns_self() -> None:
    paths = LlamaCppPaths().resolve()
    assert isinstance(paths, LlamaCppPaths)


def test_llama_cpp_paths_require_raises_when_missing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Force LLAMA_CPP_BIN to point at an empty dir + clear PATH lookups
    empty = tmp_path / "empty"
    empty.mkdir()
    monkeypatch.setenv("LLAMA_CPP_BIN", str(empty))
    # Override PATH to a dir that definitely doesn't have llama tools
    monkeypatch.setenv("PATH", str(empty))
    paths = LlamaCppPaths().resolve()
    with pytest.raises(LlamaCppNotFound):
        paths.require("quantize")


def test_llama_cpp_paths_require_returns_path_when_present(tmp_path: Path) -> None:
    stub = tmp_path / "llama-quantize"
    stub.write_text("#!/bin/sh\nexit 0\n")
    stub.chmod(0o755)
    paths = LlamaCppPaths(quantize=stub)
    assert paths.require("quantize") == stub


# ---------------- ThermalProbe -------------------------------------------


def test_thermal_reading_is_frozen() -> None:
    r = ThermalReading(t_seconds=1.0, temperature_c=80.0, sm_clock_mhz=1980.0, is_throttled=False)
    with pytest.raises(Exception):  # dataclasses.FrozenInstanceError
        r.temperature_c = 90.0  # type: ignore[misc]


def test_thermal_probe_sustained_minutes_returns_none_without_readings() -> None:
    probe = ThermalProbe()
    assert probe.sustained_load_minutes() is None


def test_thermal_probe_sustained_minutes_picks_first_throttled() -> None:
    probe = ThermalProbe(throttle_temp_c=87.0)
    # Inject readings directly (bypass nvidia-smi).
    probe._readings.extend(
        [
            ThermalReading(t_seconds=60.0, temperature_c=80.0, sm_clock_mhz=1980.0, is_throttled=False),
            ThermalReading(t_seconds=120.0, temperature_c=85.0, sm_clock_mhz=1980.0, is_throttled=False),
            ThermalReading(t_seconds=300.0, temperature_c=88.0, sm_clock_mhz=1700.0, is_throttled=True),
        ]
    )
    assert probe.sustained_load_minutes() == pytest.approx(5.0)


def test_thermal_probe_sustained_minutes_returns_last_when_never_throttled() -> None:
    probe = ThermalProbe()
    probe._readings.extend(
        [
            ThermalReading(t_seconds=60.0, temperature_c=80.0, sm_clock_mhz=1980.0, is_throttled=False),
            ThermalReading(t_seconds=600.0, temperature_c=82.0, sm_clock_mhz=1980.0, is_throttled=False),
        ]
    )
    assert probe.sustained_load_minutes() == pytest.approx(10.0)


# ---------------- quantize_gguf (dry-run) --------------------------------


def test_quantize_gguf_dry_run_enumerates_convert_and_quantize(tmp_path: Path) -> None:
    # Stub binaries so resolve() finds them
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for name in ("llama-quantize",):
        f = bin_dir / name
        f.write_text("#!/bin/sh\n")
        f.chmod(0o755)
    convert = bin_dir / "convert_hf_to_gguf.py"
    convert.write_text("#!/usr/bin/env python3\n")
    convert.chmod(0o755)
    paths = LlamaCppPaths(
        quantize=bin_dir / "llama-quantize",
        convert=convert,
    )

    model_dir = tmp_path / "model"
    model_dir.mkdir()
    out_dir = tmp_path / "out"

    report = quantize_gguf(
        model=model_dir,
        outdir=out_dir,
        variants=("Q4_K_M", "Q8_0", "F16"),
        paths=paths,
        dry_run=True,
    )
    assert report.format == "gguf"
    assert report.variants == ("Q4_K_M", "Q8_0", "F16")
    convert_notes = [n for n in report.notes if n.startswith("convert:")]
    assert len(convert_notes) == 1  # one convert call before quants
    quant_notes = [n for n in report.notes if n.startswith("quantize:")]
    assert len(quant_notes) == 2  # one per non-F16 variant
    # variant_files populated for every variant (sizes empty in dry-run)
    assert set(report.variant_files.keys()) == {"Q4_K_M", "Q8_0", "F16"}


def test_quantize_gguf_dry_run_skips_convert_when_f16_supplied(tmp_path: Path) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    quantize = bin_dir / "llama-quantize"
    quantize.write_text("#!/bin/sh\n")
    quantize.chmod(0o755)
    paths = LlamaCppPaths(quantize=quantize)

    f16 = tmp_path / "model-f16.gguf"
    f16.write_bytes(b"GGUF")
    out_dir = tmp_path / "out"

    report = quantize_gguf(
        model=f16,
        outdir=out_dir,
        variants=("Q4_K_M",),
        paths=paths,
        f16_path=f16,
        dry_run=True,
    )
    assert all(not n.startswith("convert:") for n in report.notes)
    assert any(n.startswith("quantize:") for n in report.notes)


def test_measure_perplexity_dry_run_returns_none() -> None:
    assert measure_perplexity_gguf(
        gguf_path="/no/such.gguf",
        corpus_path="/no/such.txt",
        paths=LlamaCppPaths(perplexity=Path("/bin/sh")),
        dry_run=True,
    ) is None


def test_measure_tokens_per_sec_dry_run_returns_none() -> None:
    assert measure_tokens_per_sec_gguf(
        gguf_path="/no/such.gguf",
        paths=LlamaCppPaths(bench=Path("/bin/sh")),
        dry_run=True,
    ) is None


# ---------------- format stubs --------------------------------------------


@pytest.mark.parametrize(
    "func",
    [quantize_awq, quantize_gptq, quantize_exl3, quantize_mlx, quantize_nvfp4],
)
def test_format_stubs_raise_with_roadmap_hint(func: Any) -> None:  # type: ignore[name-defined]
    with pytest.raises(NotImplementedError) as exc:
        func()
    assert "v0.4" in str(exc.value) or "v0.5" in str(exc.value) or "roadmap" in str(exc.value).lower()


# ---------------- error hierarchy + report shape --------------------------


def test_error_hierarchy() -> None:
    assert issubclass(LlamaCppNotFound, QuantError)


def test_quant_report_defaults_are_empty() -> None:
    r = QuantReport(format="gguf", base_model="x", variants=("Q4_K_M",))
    assert r.variant_files == {}
    assert r.perplexity == {}
    assert r.tokens_per_sec == {}
    assert r.sustained_load_minutes is None
    assert r.notes == []
