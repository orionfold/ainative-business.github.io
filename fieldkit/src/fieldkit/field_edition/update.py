# Copyright 2026 Manav Sehgal
# SPDX-License-Identifier: Apache-2.0
"""`fieldkit field-edition {update,rollback}` — the §9 eval-gated update channel.

Implements the update-flow half of §9 of ``_SPECS/arena-field-edition-v1.md``::

    fetch the new pinned matrix → cosign-verify → pull → `compose up` the new
    digests → run the §8 gate → emit a fresh receipt.
    On gate failure or health-check failure → automatic rollback to the prior
    pinned matrix (retained on disk). `rollback` is the manual escape hatch.

This is deliberately **not** a Watchtower-style continuous auto-pull — it stages,
gates, and rolls back, which is the "kept proven" value the paid tier funds.

Design (the deterministic-scripts invariant): the orchestration is pure control
flow over injectable seams, so the whole update/rollback decision tree is
unit-testable without a registry, cosign, or the GPU:

- :class:`UpdateChannel` — fetch the latest matrix + verify its signature. The
  **only external boundary**: ``LiveUpdateChannel`` honestly raises
  :class:`UpdateError` because there is no published, signed GHCR channel yet
  (that lands with the proven-matrix images + cosign at M3) — exactly the same
  "fail honestly until the infra exists" stance as ``up``'s live phases.
- ``applier`` — reconcile the running stack to a matrix (Live: re-run ``up``'s
  pull + stack phases against the new pins).
- ``gate`` — run the §8 battery + emit the receipt (Live: :func:`run_verify`).

:func:`run_update` ties them together with the retention helpers in
:mod:`.proven_matrix`; :func:`run_rollback` is the manual restore.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from fieldkit.field_edition import proven_matrix as _pm
from fieldkit.field_edition.compose import FieldEditionConfig, default_config
from fieldkit.field_edition.proven_matrix import ProvenMatrix
from fieldkit.field_edition.verify import VerifyReport

__all__ = [
    "UpdateError",
    "UpdateChannel",
    "LiveUpdateChannel",
    "UpdateResult",
    "run_update",
    "run_rollback",
]


class UpdateError(RuntimeError):
    """A step in the update flow failed. Carries the operator-facing ``fix``."""

    def __init__(self, message: str, *, fix: str = "") -> None:
        super().__init__(message)
        self.fix = fix


# --- The external boundary (fetch + cosign-verify) ---------------------------


class UpdateChannel:
    """Fetches + verifies the latest proven matrix. Subclass / fake for tests."""

    def fetch_latest(self, config: FieldEditionConfig) -> ProvenMatrix:  # pragma: no cover - overridden
        raise NotImplementedError

    def verify_signature(self, matrix: ProvenMatrix) -> None:  # pragma: no cover - overridden
        """Raise :class:`UpdateError` on a tamper / signature mismatch."""
        raise NotImplementedError


class LiveUpdateChannel(UpdateChannel):
    """The real channel — not yet published.

    §9's signed GHCR proven-matrix channel ships at M3 (it needs the built +
    pushed Orionfold images and cosign signatures). Until then this raises an
    honest :class:`UpdateError` naming the missing piece instead of pretending to
    update — the same posture as ``up``'s live phases."""

    def fetch_latest(self, config: FieldEditionConfig) -> ProvenMatrix:
        raise UpdateError(
            "no published proven-matrix channel yet",
            fix=(
                "the signed GHCR update channel lands at M3 (needs the built + "
                "cosign-signed Orionfold images); until then the box runs the "
                "matrix pinned in `fieldkit.field_edition.compose`"
            ),
        )

    def verify_signature(self, matrix: ProvenMatrix) -> None:
        if not matrix.signed:
            raise UpdateError(
                "matrix is unsigned",
                fix="reject — proven-matrix releases must be cosign-signed (§9)",
            )


# --- The orchestrator --------------------------------------------------------


@dataclass
class UpdateResult:
    """The outcome of a :func:`run_update` / :func:`run_rollback`."""

    applied: bool
    rolled_back: bool
    matrix: ProvenMatrix | None
    report: VerifyReport | None
    receipt_path: Path | None
    message: str
    error: str | None = None
    fix: str = ""

    @property
    def ok(self) -> bool:
        return self.error is None


def run_update(
    config: FieldEditionConfig | None = None,
    *,
    channel: UpdateChannel | None = None,
    applier: Callable[[FieldEditionConfig], None] | None = None,
    gate: Callable[[FieldEditionConfig], tuple[VerifyReport, Path]] | None = None,
    on_event: Callable[[str], None] | None = None,
) -> UpdateResult:
    """Fetch → verify → apply → gate → (auto-rollback on failure). §9 update flow.

    Auto-rollback is the load-bearing safety: if applying the new matrix or its
    §8 gate fails, the prior matrix is restored and re-applied so the box is
    never left on a broken release. Returns an :class:`UpdateResult` describing
    exactly what happened (applied / rolled back / already current)."""
    cfg = config or default_config()
    chan = channel or LiveUpdateChannel()
    apply = applier or _live_applier
    run_gate = gate or _live_gate
    emit = on_event or (lambda _msg: None)

    # 1. fetch + 2. cosign-verify (the external boundary).
    emit("▶ fetching the latest proven matrix")
    try:
        latest = chan.fetch_latest(cfg)
        chan.verify_signature(latest)
    except UpdateError as err:
        return UpdateResult(
            applied=False, rolled_back=False, matrix=None, report=None,
            receipt_path=None, message="update aborted", error=str(err), fix=err.fix,
        )
    emit("✓ matrix fetched + signature verified")

    # 3. already current?
    current = _pm.load_current(cfg)
    if current is not None and current.fingerprint() == latest.fingerprint():
        return UpdateResult(
            applied=False, rolled_back=False, matrix=current, report=None,
            receipt_path=None, message="already on the latest proven matrix",
        )

    # 4. stage: rotate current → previous, then apply the new pins.
    _pm.save_current(latest, cfg)
    emit(f"▶ applying matrix {latest.matrix_version}")
    try:
        apply(cfg)
    except Exception as err:  # noqa: BLE001 — any apply failure triggers rollback
        return _auto_rollback(cfg, apply, emit, reason=f"apply failed: {str(err)[:300]}")

    # 5. re-run the §8 gate + emit a fresh receipt.
    emit("▶ re-running the §8 eval gate")
    report, path = run_gate(cfg)
    if not report.ok:
        failed = ", ".join(f"{r.label} ({r.status})" for r in report.failures)
        result = _auto_rollback(cfg, apply, emit, reason=f"gate failed: {failed}")
        result.report = report
        result.receipt_path = path
        return result

    emit("✓ update proven")
    return UpdateResult(
        applied=True, rolled_back=False, matrix=latest, report=report,
        receipt_path=path, message=f"updated to matrix {latest.matrix_version}, gate green",
    )


def _auto_rollback(
    config: FieldEditionConfig,
    apply: Callable[[FieldEditionConfig], None],
    emit: Callable[[str], None],
    *,
    reason: str,
) -> UpdateResult:
    """Restore the prior matrix + re-apply it (the §9 auto-rollback)."""
    emit(f"✗ {reason} — rolling back to the prior matrix")
    prev = _pm.rollback(config)
    if prev is None:
        return UpdateResult(
            applied=False, rolled_back=False, matrix=None, report=None,
            receipt_path=None, message="rollback unavailable",
            error=f"{reason}; no prior matrix to roll back to",
            fix="re-run `fieldkit field-edition up` to rebuild from the pinned config",
        )
    try:
        apply(config)
    except Exception as err:  # noqa: BLE001
        return UpdateResult(
            applied=False, rolled_back=True, matrix=prev, report=None,
            receipt_path=None, message="rolled back (re-apply incomplete)",
            error=f"{reason}; rollback re-apply failed: {str(err)[:200]}",
            fix="inspect `docker compose logs`; the prior matrix is restored on disk",
        )
    emit("✓ rolled back to the prior matrix")
    return UpdateResult(
        applied=False, rolled_back=True, matrix=prev, report=None, receipt_path=None,
        message="rolled back to the prior proven matrix", error=reason,
        fix="the box is back on the prior matrix; report the failing gate",
    )


def run_rollback(
    config: FieldEditionConfig | None = None,
    *,
    applier: Callable[[FieldEditionConfig], None] | None = None,
    on_event: Callable[[str], None] | None = None,
) -> UpdateResult:
    """Manually restore the prior proven matrix + re-apply it (§9 escape hatch)."""
    cfg = config or default_config()
    apply = applier or _live_applier
    emit = on_event or (lambda _msg: None)

    prev = _pm.rollback(cfg)
    if prev is None:
        return UpdateResult(
            applied=False, rolled_back=False, matrix=None, report=None,
            receipt_path=None, message="nothing to roll back to",
            error="no previous proven matrix retained",
            fix="rollback is only available after at least one update",
        )
    emit(f"▶ restoring matrix {prev.matrix_version}")
    try:
        apply(cfg)
    except Exception as err:  # noqa: BLE001
        return UpdateResult(
            applied=False, rolled_back=True, matrix=prev, report=None,
            receipt_path=None, message="rolled back (re-apply incomplete)",
            error=f"re-apply failed: {str(err)[:300]}",
            fix="inspect `docker compose logs`; the prior matrix is restored on disk",
        )
    emit("✓ restored")
    return UpdateResult(
        applied=False, rolled_back=True, matrix=prev, report=None, receipt_path=None,
        message=f"rolled back to matrix {prev.matrix_version}",
    )


# --- Live seams --------------------------------------------------------------


def _live_applier(config: FieldEditionConfig) -> None:
    """Reconcile the running stack to the current matrix — re-run ``up``.

    ``up`` is the re-entrant phase machine; ``force=True`` re-pulls + recreates
    against the (now updated) pins. It raises honestly if the proven-matrix
    images aren't built yet (M2/M3)."""
    from fieldkit.field_edition.up import run_up

    result = run_up(config, force=True)
    if not result.ok:
        raise UpdateError(
            f"stack reconcile stopped at `{result.failed}`", fix=result.fix
        )


def _live_gate(config: FieldEditionConfig) -> tuple[VerifyReport, Path]:
    from fieldkit.field_edition.verify import run_verify

    return run_verify(config)
