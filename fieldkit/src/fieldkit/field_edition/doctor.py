# Copyright 2026 Manav Sehgal
# SPDX-License-Identifier: Apache-2.0
"""Field Edition matrix check — ``fieldkit field-edition doctor``.

Implements §7 of ``_SPECS/arena-field-edition-v1.md``: the bootstrap
**refuses on an unmatched DGX OS / driver / CUDA / Container-Toolkit matrix
rather than installing onto an untested base**, naming the failure and the
fix. ``doctor`` is the standalone form of that gate (also the ``fieldkit``
row of the §8 first-boot eval gate).

Design (per the deterministic-scripts invariant): the version comparison is a
**pure function** — :func:`evaluate_matrix` takes a mapping of already-probed
raw strings and returns a :class:`DoctorReport`. The shelling-out lives in a
thin separate layer (:func:`probe_environment`) so the verdict logic is fully
unit-testable without a DGX box.

Version semantics are **minimum-version gates**, not exact matches: a box on a
*newer* DGX OS / driver than the tested baseline passes (refusing a customer
for being too new is the wrong failure), while a too-old base hard-fails with
the fix. The tested baseline is carried on each :class:`MatrixCheck` so the
report can show "found X, tested against Y" — making matrix drift visible
without making it an error. (Keeping the baseline current against DGX OS churn
is the §9 update channel's job.)
"""

from __future__ import annotations

import re
import shutil
import subprocess
from dataclasses import dataclass
from typing import Mapping, Sequence

__all__ = [
    "TESTED_MATRIX",
    "CheckResult",
    "DoctorReport",
    "MatrixCheck",
    "evaluate_matrix",
    "parse_version",
    "probe_environment",
    "run_doctor",
]


@dataclass(frozen=True)
class MatrixCheck:
    """One requirement in the tested support matrix (§7)."""

    key: str
    label: str
    kind: str  # "version_min" | "present"
    tested: str  # human-readable tested baseline ("7.2.3", "preinstalled")
    fix: str


# The §7 tested matrix. ``tested`` values are the spec baseline (DGX OS 7.2.3
# era). NOTE: the dogfood box has since moved to DGX OS 7.4.0/7.5.0 — the
# minimum-version semantics mean it still passes, and the report surfaces the
# drift. Re-pin these baselines to the clean-wipe target before M2.
TESTED_MATRIX: tuple[MatrixCheck, ...] = (
    MatrixCheck(
        key="dgx_os",
        label="DGX OS",
        kind="version_min",
        tested="7.2.3",
        fix="Update DGX OS to 7.2.3 or newer before installing the Field Edition.",
    ),
    MatrixCheck(
        key="driver",
        label="NVIDIA driver",
        kind="version_min",
        tested="580.95.05",
        fix="Upgrade the NVIDIA driver to >= 580.95.05 (ships with the matched DGX OS).",
    ),
    MatrixCheck(
        key="cuda",
        label="CUDA runtime",
        kind="version_min",
        tested="13.0",
        fix="Install CUDA 13.0+ (matched DGX OS / driver provides it).",
    ),
    MatrixCheck(
        key="docker",
        label="Docker CE",
        kind="present",
        tested="preinstalled",
        fix="Install Docker CE (preinstalled on DGX OS 7.x; `sudo apt-get install docker-ce`).",
    ),
    MatrixCheck(
        key="container_toolkit",
        label="NVIDIA Container Toolkit",
        kind="present",
        tested="preinstalled",
        fix="Install the NVIDIA Container Toolkit (`nvidia-ctk`); preinstalled on DGX OS 7.x.",
    ),
)


def parse_version(value: str | None) -> tuple[int, ...] | None:
    """Extract the first dotted-numeric run from ``value`` as an int tuple.

    ``"580.159.03"`` → ``(580, 159, 3)``; ``"CUDA Version: 13.0"`` →
    ``(13, 0)``. Returns ``None`` when no version is present, so callers can
    treat an unparseable probe as "not detected".
    """
    if not value:
        return None
    match = re.search(r"(\d+(?:\.\d+)+)", value)
    if not match:
        return None
    return tuple(int(part) for part in match.group(1).split("."))


@dataclass(frozen=True)
class CheckResult:
    """The verdict for one :class:`MatrixCheck`."""

    key: str
    label: str
    found: str | None
    status: str  # "ok" | "too_old" | "missing"
    tested: str
    reason: str
    fix: str

    @property
    def ok(self) -> bool:
        return self.status == "ok"


@dataclass(frozen=True)
class DoctorReport:
    """Aggregate verdict over the whole matrix."""

    results: tuple[CheckResult, ...]

    @property
    def ok(self) -> bool:
        """True only when every check passes (no too-old, no missing)."""
        return all(result.ok for result in self.results)

    @property
    def failures(self) -> tuple[CheckResult, ...]:
        return tuple(result for result in self.results if not result.ok)


def evaluate_matrix(
    probes: Mapping[str, str | None],
    matrix: Sequence[MatrixCheck] = TESTED_MATRIX,
) -> DoctorReport:
    """Pure verdict: compare probed values against the tested matrix.

    ``probes`` maps each :class:`MatrixCheck` key to a raw probed string (or
    ``None`` when the probe found nothing). No I/O — fully unit-testable.
    """
    results: list[CheckResult] = []
    for check in matrix:
        found = probes.get(check.key)
        if check.kind == "present":
            if found:
                results.append(
                    CheckResult(check.key, check.label, found, "ok", check.tested, "", "")
                )
            else:
                results.append(
                    CheckResult(
                        check.key,
                        check.label,
                        None,
                        "missing",
                        check.tested,
                        f"{check.label} not detected",
                        check.fix,
                    )
                )
            continue

        if check.kind == "version_min":
            found_version = parse_version(found)
            tested_version = parse_version(check.tested)
            if found_version is None:
                results.append(
                    CheckResult(
                        check.key,
                        check.label,
                        found,
                        "missing",
                        check.tested,
                        f"{check.label} version not detected",
                        check.fix,
                    )
                )
            elif tested_version is not None and found_version < tested_version:
                results.append(
                    CheckResult(
                        check.key,
                        check.label,
                        found,
                        "too_old",
                        check.tested,
                        f"{check.label} {found} is older than the tested minimum {check.tested}",
                        check.fix,
                    )
                )
            else:
                results.append(
                    CheckResult(check.key, check.label, found, "ok", check.tested, "", "")
                )
            continue

        raise ValueError(f"unknown matrix check kind: {check.kind!r}")

    return DoctorReport(tuple(results))


# --- Probe layer (the only I/O; kept thin so evaluate_matrix stays pure) -----


def _run(cmd: list[str]) -> str | None:
    """Run ``cmd`` and return stripped stdout, or ``None`` on any failure."""
    if shutil.which(cmd[0]) is None:
        return None
    try:
        out = subprocess.run(  # noqa: S603 — fixed argv, no shell
            cmd,
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if out.returncode != 0:
        return None
    return out.stdout.strip() or None


def _probe_dgx_os(release_path: str = "/etc/dgx-release") -> str | None:
    """Read the installed DGX OS version from ``/etc/dgx-release``.

    Prefers ``DGX_SWBUILD_VERSION`` (the version actually running) over the
    pending ``DGX_OTA_VERSION``.
    """
    try:
        with open(release_path, "r", encoding="utf-8") as handle:
            text = handle.read()
    except OSError:
        return None
    match = re.search(r'DGX_SWBUILD_VERSION="([^"]+)"', text)
    if match:
        return match.group(1)
    match = re.search(r'DGX_OTA_VERSION="([^"]+)"', text)
    return match.group(1) if match else None


def _probe_driver() -> str | None:
    out = _run(["nvidia-smi", "--query-gpu=driver_version", "--format=csv,noheader"])
    if out:
        return out.splitlines()[0].strip()
    # Fallback to the kernel module banner.
    try:
        with open("/proc/driver/nvidia/version", "r", encoding="utf-8") as handle:
            banner = handle.readline()
    except OSError:
        return None
    match = re.search(r"\b(\d+\.\d+\.\d+)\b", banner)
    return match.group(1) if match else None


def _probe_cuda() -> str | None:
    out = _run(["nvidia-smi"])
    if not out:
        return None
    match = re.search(r"CUDA Version:\s*([\d.]+)", out)
    return match.group(1) if match else None


def probe_environment() -> dict[str, str | None]:
    """Probe the live box for every matrix key (best-effort; never raises)."""
    return {
        "dgx_os": _probe_dgx_os(),
        "driver": _probe_driver(),
        "cuda": _probe_cuda(),
        "docker": _first_line(_run(["docker", "--version"])),
        "container_toolkit": _first_line(_run(["nvidia-ctk", "--version"])),
    }


def _first_line(value: str | None) -> str | None:
    """Keep only the first line of a probe — version banners are often multi-line."""
    return value.splitlines()[0].strip() if value else None


def run_doctor(matrix: Sequence[MatrixCheck] = TESTED_MATRIX) -> DoctorReport:
    """Probe the live environment and return the verdict (probe + evaluate)."""
    return evaluate_matrix(probe_environment(), matrix)
