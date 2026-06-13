# Copyright 2026 Manav Sehgal
# SPDX-License-Identifier: Apache-2.0
"""Orionfold Arena **Field Edition** — the self-serve DGX Spark distributable.

This package owns the *installer / orchestration* surface for the commercial
Field Edition (Arena + Advisor + Cortex + fieldkit + quants + Hermes) per
``_SPECS/arena-field-edition-v1.md``. It is **separate from the model/eval
work** — the Advisor v0.3 road does not touch this machinery, so it can be
built on its own track.

M1 surface: ``fieldkit field-edition doctor`` (the §7 matrix gate),
``fieldkit field-edition up`` (the checkpointed Compose bring-up), and
``fieldkit field-edition verify`` (the §8 first-boot eval gate + receipt) are
implemented for real. ``up``'s orchestration + the digest-pinned Compose bundle
(:mod:`.compose`, :mod:`.up`) run today; ``--dry-run`` writes the bundle and
prints the plan. ``verify`` (:mod:`.verify`) runs the five-gate battery, applies
the published floors, and always emits the receipt — the ``fieldkit`` gate is
measured live now, the bench gates report an honest ``error`` until the live
stack lands (M2). The live ``up`` phases fail honestly until the proven-matrix
images exist (M2).

The rest of the §7 + §9 surface is now implemented too: ``down`` (:mod:`.down`,
the AC-6 uninstall — preserves data unless ``--purge``), ``repair``
(:mod:`.repair`, the §8 single-component re-pull + re-gate), and ``update`` /
``rollback`` (:mod:`.update` over the :mod:`.proven_matrix` retained manifest —
the §9 eval-gated, rollback-safe channel). Each fails honestly at the boundaries
that still need M2/M3 infra (the unbuilt GHCR images, the unpublished signed
channel) rather than stubbing the whole command.
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
from fieldkit.field_edition.verify import (
    ADVISOR_CURVEBALL_FLOOR,
    ADVISOR_REFUSALS_TOTAL,
    CORTEX_RECALL_FLOOR,
    GATES,
    GateOutcome,
    GateResult,
    GateRunner,
    GateSpec,
    LiveGateRunner,
    VerifyReport,
    assess_gate,
    evaluate_gates,
    run_verify,
    write_receipt,
)
from fieldkit.field_edition.down import (
    DownExecutor,
    DownPlan,
    DownResult,
    LiveDownExecutor,
    plan_down,
    run_down,
)
from fieldkit.field_edition.repair import (
    COMPONENTS,
    LiveRepairExecutor,
    RepairExecutor,
    RepairPlan,
    RepairResult,
    plan_repair,
    run_repair,
)
from fieldkit.field_edition.proven_matrix import (
    ProvenMatrix,
    rollback as rollback_matrix,
    save_current,
)
from fieldkit.field_edition.update import (
    LiveUpdateChannel,
    UpdateChannel,
    UpdateError,
    UpdateResult,
    run_rollback,
    run_update,
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
    # verify (§8 first-boot eval gate)
    "ADVISOR_CURVEBALL_FLOOR",
    "ADVISOR_REFUSALS_TOTAL",
    "CORTEX_RECALL_FLOOR",
    "GATES",
    "GateOutcome",
    "GateResult",
    "GateRunner",
    "GateSpec",
    "LiveGateRunner",
    "VerifyReport",
    "assess_gate",
    "evaluate_gates",
    "run_verify",
    "write_receipt",
    # down (§7 uninstall, AC-6)
    "DownExecutor",
    "DownPlan",
    "DownResult",
    "LiveDownExecutor",
    "plan_down",
    "run_down",
    # repair (§8 single-component re-pull + re-gate)
    "COMPONENTS",
    "LiveRepairExecutor",
    "RepairExecutor",
    "RepairPlan",
    "RepairResult",
    "plan_repair",
    "run_repair",
    # proven matrix + update channel (§9)
    "ProvenMatrix",
    "rollback_matrix",
    "save_current",
    "LiveUpdateChannel",
    "UpdateChannel",
    "UpdateError",
    "UpdateResult",
    "run_rollback",
    "run_update",
]
