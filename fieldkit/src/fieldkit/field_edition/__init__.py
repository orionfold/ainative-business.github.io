# Copyright 2026 Manav Sehgal
# SPDX-License-Identifier: Apache-2.0
"""Orionfold Arena **Field Edition** — the self-serve DGX Spark distributable.

This package owns the *installer / orchestration* surface for the commercial
Field Edition (Arena + Advisor + Cortex + fieldkit + quants + Hermes) per
``_SPECS/arena-field-edition-v1.md``. It is **separate from the model/eval
work** — the Advisor v0.3 road does not touch this machinery, so it can be
built on its own track.

M1 surface: ``fieldkit field-edition doctor`` (the §7 matrix gate) and
``fieldkit field-edition up`` (the checkpointed Compose bring-up) are
implemented for real. ``up``'s orchestration + the digest-pinned Compose bundle
(:mod:`.compose`, :mod:`.up`) run today; ``--dry-run`` writes the bundle and
prints the plan. The live phases fail honestly until the proven-matrix images
exist (M2). ``verify`` (the §8 eval gate) is the next increment; ``down`` /
``repair`` / ``rollback`` / ``update`` remain milestone-marked stubs so the
surface is discoverable from day one.
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
from fieldkit.field_edition.compose import (
    FieldEditionConfig,
    ImagePin,
    compose_yaml,
    default_config,
    render_compose,
    unpinned_images,
    write_bundle,
)
from fieldkit.field_edition.up import (
    PHASES,
    Executor,
    InstallState,
    LiveExecutor,
    PhaseError,
    UpResult,
    plan_remaining,
    run_up,
)

__all__ = [
    # doctor
    "TESTED_MATRIX",
    "CheckResult",
    "DoctorReport",
    "MatrixCheck",
    "evaluate_matrix",
    "parse_version",
    "probe_environment",
    "run_doctor",
    # compose bundle
    "FieldEditionConfig",
    "ImagePin",
    "compose_yaml",
    "default_config",
    "render_compose",
    "unpinned_images",
    "write_bundle",
    # up (phase machine)
    "PHASES",
    "Executor",
    "InstallState",
    "LiveExecutor",
    "PhaseError",
    "UpResult",
    "plan_remaining",
    "run_up",
]
