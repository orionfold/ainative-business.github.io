# Copyright 2026 Manav Sehgal
# SPDX-License-Identifier: Apache-2.0
"""Quantization dispatcher — llama.cpp GGUF path first, multi-format dispatcher next.

The forge-side companion to `fieldkit.publish`. Produces a `QuantReport` from a
model directory: GGUF variants written to disk, per-variant perplexity on a
calibration corpus, sustained `tok/s` on Spark, optional thermal envelope. The
report shape is the contract `fieldkit.publish.publish_quant(...)` consumes —
no intermediate hand-editing required.

**Implemented in v0.4 (this cut):**

- `quantize_gguf(...)` — wraps `llama-quantize` (the llama.cpp binary). Emits
  one file per requested variant. Auto-derives the F16 GGUF from a HuggingFace
  Transformers checkpoint via `llama.cpp/convert_hf_to_gguf.py` when needed.
- `measure_perplexity_gguf(...)` — wraps `llama-perplexity`. Parses the output
  for the final perplexity number. Default corpus = wikitext-2 (canonical for
  GGUF cross-comparison vs Bartowski / Unsloth tables).
- `measure_tokens_per_sec_gguf(...)` — wraps `llama-bench`. Returns prompt-eval
  and text-gen `tok/s` measured on the local box (Spark in our case).
- `ThermalProbe` — pure-stdlib loop wrapping `nvidia-smi` queries; reports
  sustained-load minutes before throttle, per the duty-cycle disclosure
  standard (HANDOFF Q9 decision 2026-05-12).
- `QuantReport` — the canonical output shape; consumed by `publish_quant`.

**Stubs (named here for the v0.4 surface, NotImplementedError until v0.5+):**

`quantize_awq`, `quantize_gptq`, `quantize_exl3`, `quantize_mlx`,
`quantize_nvfp4`. Each raises with a one-liner pointing at the roadmap (see
`ideas/mtbm-use-cases.md` §7) so callers don't trip on a missing import; the
G3 v0 critical path is GGUF only.

The module subprocess-shells to llama.cpp; no Python-side quant math runs
here. That keeps the dependency surface zero at import time. Locate the
binaries via `LlamaCppPaths` — env defaults `LLAMA_CPP_BIN`, `LLAMA_CPP_CONVERT`.
"""

from __future__ import annotations

import math
import os
import sys
import re
import shutil
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional, Sequence, Union

__all__ = [
    "GGUFVariant",
    "GGUF_VARIANTS",
    "QuantFormat",
    "QuantReport",
    "QuantError",
    "LlamaCppNotFound",
    "LlamaCppPaths",
    "ThermalProbe",
    "ThermalReading",
    "quantize_gguf",
    "quantize_awq",
    "quantize_gptq",
    "quantize_exl3",
    "quantize_mlx",
    "quantize_nvfp4",
    "measure_perplexity_gguf",
    "measure_tokens_per_sec_gguf",
    "parse_perplexity_output",
    "parse_llama_bench_output",
]


GGUFVariant = str
"""One of the entries in `GGUF_VARIANTS`. Aliased as `str` so the public surface
doesn't over-constrain experimental variant additions (e.g. IQ4_XS)."""

GGUF_VARIANTS: tuple[str, ...] = ("Q4_K_M", "Q5_K_M", "Q6_K", "Q8_0", "F16")
"""Canonical Orionfold GGUF variant set per HANDOFF §2. Bartowski-comparable.

Order matters — perplexity tables in model cards walk this list left to right.
"""

QuantFormat = str
"""Top-level format: `gguf` | `awq` | `gptq` | `exl3` | `mlx` | `nvfp4`."""


# --- Errors --------------------------------------------------------------


class QuantError(Exception):
    """Base class for fieldkit.quant errors."""


class LlamaCppNotFound(QuantError):
    """The llama.cpp `llama-quantize` / `llama-perplexity` / `llama-bench` binary
    couldn't be located. Set `LLAMA_CPP_BIN` env or pass `paths=` explicitly."""


# --- Paths --------------------------------------------------------------


@dataclass
class LlamaCppPaths:
    """Locator for llama.cpp binaries + conversion script.

    Env defaults:

    - `LLAMA_CPP_BIN` — directory containing `llama-quantize`, `llama-perplexity`,
      `llama-bench` (compiled-from-source layout). Defaults to `which llama-quantize`'s
      parent.
    - `LLAMA_CPP_CONVERT` — path to `convert_hf_to_gguf.py` from a llama.cpp checkout.

    Override any field directly when constructing.
    """

    quantize: Optional[Path] = None
    perplexity: Optional[Path] = None
    bench: Optional[Path] = None
    convert: Optional[Path] = None

    def resolve(self) -> "LlamaCppPaths":
        """Fill in any unset paths from env + `which` lookups. Returns self."""
        bin_dir_env = os.environ.get("LLAMA_CPP_BIN")
        bin_dir = Path(bin_dir_env) if bin_dir_env else None

        def _find(name: str) -> Optional[Path]:
            if bin_dir is not None:
                candidate = bin_dir / name
                if candidate.exists():
                    return candidate
            located = shutil.which(name)
            return Path(located) if located else None

        if self.quantize is None:
            self.quantize = _find("llama-quantize")
        if self.perplexity is None:
            self.perplexity = _find("llama-perplexity")
        if self.bench is None:
            self.bench = _find("llama-bench")
        if self.convert is None:
            convert_env = os.environ.get("LLAMA_CPP_CONVERT")
            if convert_env:
                self.convert = Path(convert_env)
            else:
                located = shutil.which("convert_hf_to_gguf.py")
                self.convert = Path(located) if located else None
        return self

    def require(self, attr: str) -> Path:
        """Return the path for `attr` or raise `LlamaCppNotFound`."""
        value: Optional[Path] = getattr(self, attr)
        if value is None or not value.exists():
            raise LlamaCppNotFound(
                f"llama.cpp `{attr}` not found. Set LLAMA_CPP_BIN to the directory"
                f" containing the binaries, set LLAMA_CPP_CONVERT for the convert"
                f" script, or pass paths=LlamaCppPaths(...) explicitly."
            )
        return value


# --- Reports --------------------------------------------------------------


@dataclass
class QuantReport:
    """Canonical quant-run output. Consumed by `fieldkit.publish.publish_quant`.

    Fields are intentionally generic across formats — `format` discriminates;
    GGUF callers populate `variant_files` paths, AWQ/GPTQ callers populate a
    single-file shape, etc.
    """

    format: QuantFormat
    base_model: str
    variants: tuple[str, ...]
    variant_files: dict[str, dict[str, Any]] = field(default_factory=dict)
    perplexity: dict[str, float] = field(default_factory=dict)
    tokens_per_sec: dict[str, float] = field(default_factory=dict)
    sustained_load_minutes: Optional[float] = None
    notes: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ThermalReading:
    """One nvidia-smi sample. Probe loop emits these; sustained-load minutes
    are derived from the first sample that crosses the throttle threshold."""

    t_seconds: float
    temperature_c: float
    sm_clock_mhz: float
    is_throttled: bool


# --- GGUF path --------------------------------------------------------------


def quantize_gguf(
    *,
    model: Union[str, Path],
    outdir: Union[str, Path],
    variants: Sequence[str] = GGUF_VARIANTS,
    paths: Optional[LlamaCppPaths] = None,
    base_model_id: Optional[str] = None,
    dry_run: bool = False,
    f16_path: Optional[Union[str, Path]] = None,
    extra_quantize_args: Sequence[str] = (),
) -> QuantReport:
    """Run llama.cpp GGUF quantization across `variants`.

    Two construction modes:

    - `model` points at a HuggingFace Transformers directory (the common case):
      this function first runs `convert_hf_to_gguf.py` to produce an F16 GGUF,
      then runs `llama-quantize` once per requested variant. F16 is always
      written too (it's the reference for perplexity-delta tables).
    - `model` points at an existing F16 GGUF file: skip the convert step,
      `llama-quantize` directly. Pass `f16_path=` to disambiguate when both
      a HF directory and an F16 file coexist.

    `dry_run=True` enumerates the would-be subprocess calls into `report.notes`
    without invoking them — used by tests and CI.
    """
    paths = paths or LlamaCppPaths().resolve()
    out_dir = Path(outdir)
    out_dir.mkdir(parents=True, exist_ok=True)
    model_path = Path(model)
    report = QuantReport(
        format="gguf",
        base_model=base_model_id or str(model),
        variants=tuple(variants),
    )

    f16: Optional[Path] = Path(f16_path) if f16_path else None
    if f16 is None:
        if model_path.is_file() and model_path.suffix == ".gguf":
            f16 = model_path
        else:
            f16 = out_dir / "model-f16.gguf"
            convert_cmd = [
                os.environ.get("LLAMA_CPP_PYTHON") or sys.executable,
                str(paths.require("convert")),
                str(model_path),
                "--outfile",
                str(f16),
                "--outtype",
                "f16",
            ]
            if dry_run:
                report.notes.append("convert: " + " ".join(convert_cmd))
            else:
                _run(convert_cmd, label="convert_hf_to_gguf")

    for variant in variants:
        variant_path = out_dir / f"model-{variant}.gguf"
        if variant == "F16":
            if dry_run and not f16.exists():
                report.notes.append(f"f16-copy: {f16} → {variant_path}")
            elif f16.resolve() != variant_path.resolve():
                if not dry_run:
                    shutil.copy2(f16, variant_path)
            quantize_cmd: list[str] = []
        else:
            quantize_cmd = [
                str(paths.require("quantize")),
                str(f16),
                str(variant_path),
                variant,
                *extra_quantize_args,
            ]
            if dry_run:
                report.notes.append("quantize: " + " ".join(quantize_cmd))
            else:
                _run(quantize_cmd, label=f"llama-quantize {variant}")

        size_bytes: Optional[int] = None
        if not dry_run and variant_path.exists():
            size_bytes = variant_path.stat().st_size
        report.variant_files[variant] = {
            "path": str(variant_path),
            "rel": variant_path.name,
            "size": _human_bytes(size_bytes) if size_bytes else "",
            "size_bytes": size_bytes,
        }

    return report


def measure_perplexity_gguf(
    *,
    gguf_path: Union[str, Path],
    corpus_path: Union[str, Path],
    paths: Optional[LlamaCppPaths] = None,
    extra_args: Sequence[str] = (),
    dry_run: bool = False,
) -> Optional[float]:
    """Run `llama-perplexity` against `corpus_path` and parse the final number.

    Returns `None` on dry-run or parse failure (callers should treat None as
    "skip the perplexity column" rather than failing the whole run — model
    cards still ship without a perplexity number; we just want to know about it).
    """
    paths = paths or LlamaCppPaths().resolve()
    cmd = [
        str(paths.require("perplexity")),
        "-m",
        str(gguf_path),
        "-f",
        str(corpus_path),
        *extra_args,
    ]
    if dry_run:
        return None
    result = _run(cmd, label=f"llama-perplexity {Path(gguf_path).name}", capture=True)
    return parse_perplexity_output(result.stdout + "\n" + result.stderr)


def measure_tokens_per_sec_gguf(
    *,
    gguf_path: Union[str, Path],
    paths: Optional[LlamaCppPaths] = None,
    n_gen: int = 128,
    n_prompt: int = 512,
    extra_args: Sequence[str] = (),
    dry_run: bool = False,
) -> Optional[dict[str, Optional[float]]]:
    """Run `llama-bench` and return `{"tg": tok/s, "pp": tok/s}`.

    Both axes matter for a real Spark card: `tg` (text-generation) dominates
    interactive decode latency, `pp` (prompt-process) dominates long-context
    ingestion. Returns `None` on `dry_run`. The returned dict's values may
    individually be `None` if the corresponding row isn't in `llama-bench`'s
    output for that build.
    """
    paths = paths or LlamaCppPaths().resolve()
    cmd = [
        str(paths.require("bench")),
        "-m",
        str(gguf_path),
        "-n",
        str(n_gen),
        "-p",
        str(n_prompt),
        *extra_args,
    ]
    if dry_run:
        return None
    result = _run(cmd, label=f"llama-bench {Path(gguf_path).name}", capture=True)
    return {
        "tg": parse_llama_bench_output(result.stdout, metric="tg"),
        "pp": parse_llama_bench_output(result.stdout, metric="pp"),
    }


# --- Output parsers (pure, testable) -------------------------------------


_PERPLEXITY_FINAL_RE = re.compile(
    r"(?:Final estimate:\s*PPL\s*=\s*|perplexity\s*=\s*|PPL\s*=\s*)"
    r"([0-9]+\.[0-9]+)",
    re.IGNORECASE,
)


def parse_perplexity_output(text: str) -> Optional[float]:
    """Extract the final perplexity float from `llama-perplexity` stdout/stderr.

    Returns `None` when no recognizable perplexity line is present.

    The matcher is conservative: it accepts `Final estimate: PPL = N.NNN` (the
    primary llama.cpp output format) plus a `perplexity = N.NNN` fallback
    seen in some llama.cpp release lines.
    """
    matches = _PERPLEXITY_FINAL_RE.findall(text or "")
    if not matches:
        return None
    try:
        value = float(matches[-1])
    except ValueError:
        return None
    if math.isnan(value) or math.isinf(value):
        return None
    return value


_BENCH_TG_RE = re.compile(
    r"\|\s*(?P<metric>tg|pp)\s*(?P<n>\d+)\s*\|\s*(?P<tps>[0-9.]+)\s*±",
    re.IGNORECASE,
)


def parse_llama_bench_output(text: str, *, metric: str = "tg") -> Optional[float]:
    """Parse `llama-bench`'s markdown-table output for tok/s on `metric`.

    `llama-bench` emits a table where each row looks like

        | tg 128 | 23.45 ± 0.12 |
        | pp 512 | 145.67 ± 0.87 |

    This returns the first matching `metric` (`tg` or `pp`) tok/s number, or
    `None` if no row matches.
    """
    metric_lower = metric.lower()
    for match in _BENCH_TG_RE.finditer(text or ""):
        if match.group("metric").lower() == metric_lower:
            try:
                return float(match.group("tps"))
            except ValueError:
                continue
    return None


# --- Thermal probe --------------------------------------------------------


class ThermalProbe:
    """Polls `nvidia-smi` over a sustained workload to detect throttle onset.

    Usage::

        probe = ThermalProbe(interval_s=10, throttle_temp_c=87)
        with probe.run_in_background():
            run_my_workload()
        sustained_minutes = probe.sustained_load_minutes()

    The probe is intentionally minimal — no nvml binding required (we shell to
    `nvidia-smi --query-gpu=...,--format=csv,noheader,nounits`). Two probe
    modes: foreground `sample()` for one-off queries, and `samples()` iterator
    for a streaming poll. Background-thread orchestration is left to callers
    because `fieldkit.training` already pulls `threading` lazily and we don't
    want this module to.

    Readings beyond `throttle_temp_c` count as throttled; sustained minutes is
    the wall-clock time elapsed between probe start and the first throttled
    sample (or total wall if no throttle was observed).
    """

    def __init__(
        self,
        *,
        interval_s: float = 10.0,
        throttle_temp_c: float = 87.0,
        nvidia_smi: Optional[Union[str, Path]] = None,
    ) -> None:
        self.interval_s = interval_s
        self.throttle_temp_c = throttle_temp_c
        self._nvidia_smi = str(nvidia_smi) if nvidia_smi else shutil.which("nvidia-smi") or "nvidia-smi"
        self._readings: list[ThermalReading] = []
        self._start_time: Optional[float] = None

    @property
    def readings(self) -> tuple[ThermalReading, ...]:
        return tuple(self._readings)

    def sample(self) -> ThermalReading:
        """Take one `nvidia-smi` sample and record it. Returns the reading."""
        if self._start_time is None:
            self._start_time = time.monotonic()
        cmd = [
            self._nvidia_smi,
            "--query-gpu=temperature.gpu,clocks.current.sm",
            "--format=csv,noheader,nounits",
        ]
        result = _run(cmd, label="nvidia-smi", capture=True, check=False)
        temp, sm_clock = _parse_nvidia_smi_csv(result.stdout)
        reading = ThermalReading(
            t_seconds=time.monotonic() - self._start_time,
            temperature_c=temp,
            sm_clock_mhz=sm_clock,
            is_throttled=temp >= self.throttle_temp_c,
        )
        self._readings.append(reading)
        return reading

    def sustained_load_minutes(self) -> Optional[float]:
        """Wall-clock minutes until first throttled sample (or total wall if none).

        Returns `None` if no samples were taken yet.
        """
        if not self._readings:
            return None
        for reading in self._readings:
            if reading.is_throttled:
                return reading.t_seconds / 60.0
        return self._readings[-1].t_seconds / 60.0


def _parse_nvidia_smi_csv(text: str) -> tuple[float, float]:
    """Parse `nvidia-smi --query-gpu=temperature.gpu,clocks.current.sm,...,csv,noheader,nounits`."""
    line = (text or "").strip().splitlines()[0] if (text or "").strip() else ""
    parts = [p.strip() for p in line.split(",")] if line else []
    try:
        temp = float(parts[0]) if len(parts) > 0 else 0.0
    except ValueError:
        temp = 0.0
    try:
        sm = float(parts[1]) if len(parts) > 1 else 0.0
    except ValueError:
        sm = 0.0
    return temp, sm


# --- Stubs for non-GGUF formats -------------------------------------------


_STUB_HINT = (
    "Not yet implemented in fieldkit v0.4. Roadmap: see"
    " `ideas/mtbm-use-cases.md` §7 — `fieldkit.quant` extends to AWQ / GPTQ /"
    " EXL3 / MLX / NVFP4 in v0.4+; the GGUF path is the v0.4 critical path"
    " for the G3 publisher pick."
)


def quantize_awq(**kwargs: Any) -> QuantReport:
    """AutoAWQ dispatcher — stub, v0.5+."""
    raise NotImplementedError("quantize_awq: " + _STUB_HINT)


def quantize_gptq(**kwargs: Any) -> QuantReport:
    """AutoGPTQ dispatcher — stub, v0.5+. Targets the orphaned qwopqwop200 audience."""
    raise NotImplementedError("quantize_gptq: " + _STUB_HINT)


def quantize_exl3(**kwargs: Any) -> QuantReport:
    """exllamav3 variable-bpw dispatcher — stub, v0.5+."""
    raise NotImplementedError("quantize_exl3: " + _STUB_HINT)


def quantize_mlx(**kwargs: Any) -> QuantReport:
    """mlx-lm 4-bit / 8-bit dispatcher (Apple Silicon) — stub, v0.5+."""
    raise NotImplementedError("quantize_mlx: " + _STUB_HINT)


def quantize_nvfp4(**kwargs: Any) -> QuantReport:
    """NVIDIA TensorRT-LLM FP4 dispatcher — stub, v0.5+."""
    raise NotImplementedError("quantize_nvfp4: " + _STUB_HINT)


# --- Internals --------------------------------------------------------------


def _run(
    cmd: Sequence[str],
    *,
    label: str,
    capture: bool = False,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    """Subprocess helper. Single-spot for the all the llama.cpp invocations
    so a future replacement (e.g. a Python-side binding) drops in cleanly."""
    return subprocess.run(
        list(cmd),
        check=check,
        capture_output=capture,
        text=True,
    )


def _human_bytes(n: Optional[int]) -> str:
    if n is None:
        return ""
    units = ["B", "KB", "MB", "GB", "TB"]
    size = float(n)
    for unit in units:
        if size < 1024.0 or unit == units[-1]:
            return f"{size:.1f} {unit}" if unit != "B" else f"{int(size)} {unit}"
        size /= 1024.0
    return f"{size:.1f} TB"
