# Copyright 2026 Manav Sehgal
# SPDX-License-Identifier: Apache-2.0
"""Orionfold Arena **Field Edition** — the self-serve DGX Spark distributable.

This package owns the *installer / orchestration* surface for the commercial
Field Edition (Arena + Advisor + Cortex + fieldkit + quants + Hermes) per
``_SPECS/arena-field-edition-v1.md``. It is **separate from the model/eval
work** — the Advisor v0.3 road does not touch this machinery, so it can be
built on its own track.

M1 surface (this commit): the ``fieldkit field-edition doctor`` matrix check
is implemented for real (deterministic environment probing — §7's
"refuse on an unmatched matrix rather than installing onto an untested base").
The rest of the §7 command surface (``up`` / ``verify`` / ``down`` /
``repair`` / ``rollback`` and the top-level ``update``) is declared as
milestone-marked stubs so the surface is discoverable from day one.

Only ``doctor`` is wired to real logic here; everything else lands at its
milestone. The heavy lifting (Docker Compose bring-up, eval gates, signed
update channel) arrives at M1→M3.
"""

from __future__ import annotations

from fieldkit.field_edition.doctor import (
    TESTED_MATRIX,
    CheckResult,
    DoctorReport,
    MatrixCheck,
    evaluate_matrix,
    parse_version,
    probe_environment,
    run_doctor,
)

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
