# Copyright 2026 Manav Sehgal
# SPDX-License-Identifier: Apache-2.0
"""`fieldkit field-edition up` — bring up the stack + load the resident Advisor.

Implements §7 step 2 of ``_SPECS/arena-field-edition-v1.md``. ``up`` is a
**checkpointed, re-entrant phase machine**: it walks an ordered list of phases,
persists a checkpoint after each, and on a re-run **resumes from the last good
phase** rather than restarting (the spec's idempotency / partial-failure
contract — the box runs ~4.77 MB/s, so a failed pull must not redo the work
already done).

Phases (ordered)::

    matrix    re-run the §7 support-matrix gate (refuse an untested base)
    bundle    render + write the digest-pinned Compose bundle into ~/.orionfold
    pull      pull the default Advisor GGUF + embedder weights (resumable)
    stack     `docker compose up -d`  →  pgvector + embedder + the llama.cpp lane
    sidecar   start the pipx Arena cockpit on :7866 and wait for health
    resident  point Arena at the lane and warm the default model
    verify    (only with --verify) run the §8 first-boot eval gate + emit receipt

Design (the deterministic-scripts invariant): the **planning** is pure —
:func:`plan_remaining` decides which phases run from a state dict, with no I/O —
and the **execution** lives behind an injectable :class:`Executor` so the live
shell-outs (Docker, HF, the cockpit) are isolated and the runner is testable
with a fake. :func:`run_up` is the loop that ties them together and checkpoints.

**M1 status.** The orchestration, the Compose bundle (:mod:`.compose`), and the
``matrix``/``bundle`` phases run for real today; ``--dry-run`` writes the bundle
and prints the remaining plan. The live phases (``pull``/``stack``/``resident``)
fail honestly until the proven-matrix images + the published Q4_K_M GGUF exist
(M2) — :data:`compose.unpinned_images` is checked up front so the failure names
the missing artifact and the fix instead of a cryptic registry error. ``verify``
is the next increment (§8 eval gate); ``--verify`` reports that honestly.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from fieldkit.field_edition import compose as _compose
from fieldkit.field_edition.compose import FieldEditionConfig

__all__ = [
    "PHASES",
    "Phase",
    "PhaseError",
    "InstallState",
    "Executor",
    "LiveExecutor",
    "UpResult",
    "plan_remaining",
    "run_up",
]


class PhaseError(RuntimeError):
    """A phase failed. Carries the operator-facing ``fix`` (the §8 failure-UX
    contract: name the component, the gate, and the fix)."""

    def __init__(self, message: str, *, fix: str = "") -> None:
        super().__init__(message)
        self.fix = fix


@dataclass(frozen=True)
class Phase:
    """One step in the ``up`` sequence."""

    key: str
    label: str
    detail: str
    #: A "safe" phase only touches the local box (matrix gate, file writes) and
    #: runs under ``--dry-run``; non-safe phases pull/launch and are skipped.
    safe: bool = False
    #: Optional phases (``verify``) only run when explicitly requested.
    optional: bool = False


PHASES: tuple[Phase, ...] = (
    Phase("matrix", "Matrix gate", "verify the DGX OS / driver / CUDA / Docker matrix", safe=True),
    Phase("bundle", "Compose bundle", "render + write ~/.orionfold/compose.yaml + .env", safe=True),
    Phase("pull", "Model pull", "pull the default Advisor GGUF + embedder weights (resumable)"),
    Phase("stack", "Container stack", "docker compose up -d (pgvector + embedder + lane)"),
    Phase("sidecar", "Arena cockpit", "start the pipx Arena sidecar on :7866"),
    Phase("resident", "Resident model", "point Arena at the lane and warm the default model"),
    Phase("verify", "First-boot gate", "run the §8 eval gate + emit the receipt", optional=True),
)

_DONE = "done"
_FAILED = "failed"
_PENDING = "pending"


# --- State (the checkpoint) --------------------------------------------------


@dataclass
class InstallState:
    """The on-disk checkpoint at ``~/.orionfold/state.json``.

    Maps each phase key to ``"done"``/``"failed"``/``"pending"``; ``done``
    phases are skipped on a re-run (unless ``--force``)."""

    version: int = 1
    phases: dict[str, str] = field(default_factory=dict)

    @classmethod
    def load(cls, path: Path) -> "InstallState":
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return cls()
        return cls(version=int(data.get("version", 1)), phases=dict(data.get("phases", {})))

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps({"version": self.version, "phases": self.phases}, indent=2) + "\n",
            encoding="utf-8",
        )

    def status(self, key: str) -> str:
        return self.phases.get(key, _PENDING)

    def mark(self, key: str, status: str) -> None:
        self.phases[key] = status


def plan_remaining(
    state: InstallState,
    *,
    phases: tuple[Phase, ...] = PHASES,
    force: bool = False,
    with_verify: bool = False,
    safe_only: bool = False,
) -> list[Phase]:
    """Pure: the phases this run will execute, in order (no I/O).

    Skips ``done`` phases (re-entrancy) unless ``force``; drops optional phases
    unless requested (``with_verify``); under ``safe_only`` (dry-run) keeps only
    the local-touch phases."""
    chosen: list[Phase] = []
    for p in phases:
        if p.optional and not (p.key == "verify" and with_verify):
            continue
        if safe_only and not p.safe:
            continue
        if not force and state.status(p.key) == _DONE:
            continue
        chosen.append(p)
    return chosen


# --- Execution (the only I/O) ------------------------------------------------


def _which(name: str) -> bool:
    return shutil.which(name) is not None


def _run(cmd: list[str], *, timeout: int = 600) -> subprocess.CompletedProcess:
    return subprocess.run(  # noqa: S603 — fixed argv, no shell
        cmd, capture_output=True, text=True, timeout=timeout, check=False
    )


class Executor:
    """The phase actions. Subclass / fake for tests; :meth:`dispatch` maps a
    phase key to its method so the runner stays dispatch-agnostic."""

    def dispatch(self, key: str, config: FieldEditionConfig) -> None:
        getattr(self, key)(config)

    # Each method runs one phase and raises PhaseError on failure.
    def matrix(self, config: FieldEditionConfig) -> None:  # pragma: no cover - overridden
        raise NotImplementedError

    def bundle(self, config: FieldEditionConfig) -> None:  # pragma: no cover
        raise NotImplementedError

    def pull(self, config: FieldEditionConfig) -> None:  # pragma: no cover
        raise NotImplementedError

    def stack(self, config: FieldEditionConfig) -> None:  # pragma: no cover
        raise NotImplementedError

    def sidecar(self, config: FieldEditionConfig) -> None:  # pragma: no cover
        raise NotImplementedError

    def resident(self, config: FieldEditionConfig) -> None:  # pragma: no cover
        raise NotImplementedError

    def verify(self, config: FieldEditionConfig) -> None:  # pragma: no cover
        raise NotImplementedError


class LiveExecutor(Executor):
    """Runs the phases against the real box."""

    def matrix(self, config: FieldEditionConfig) -> None:
        from fieldkit.field_edition.doctor import run_doctor

        report = run_doctor()
        if not report.ok:
            failed = ", ".join(f"{r.label} ({r.status})" for r in report.failures)
            raise PhaseError(
                f"support matrix failed: {failed}",
                fix="run `fieldkit field-edition doctor` to see each reason + fix",
            )

    def bundle(self, config: FieldEditionConfig) -> None:
        _compose.write_bundle(config)

    def pull(self, config: FieldEditionConfig) -> None:
        gguf = config.model_store / config.lane.gguf_name
        if gguf.exists():
            return
        # No published Q4_K_M rev to pull from yet (Advisor-GGUF ships Q8_0
        # only). The resumable HF download wires in here when the rev is pinned.
        raise PhaseError(
            f"default model not present at {gguf}",
            fix=(
                "the resumable GGUF pull lands at M2 once a Q4_K_M rev of "
                "Orionfold/Advisor-GGUF is published + pinned; until then place "
                "the GGUF in the model store manually"
            ),
        )

    def stack(self, config: FieldEditionConfig) -> None:
        unpinned = _compose.unpinned_images(config)
        if unpinned:
            names = ", ".join(p.reference() for p in unpinned)
            raise PhaseError(
                f"{len(unpinned)} image(s) not yet published/pinned: {names}",
                fix=(
                    "build + push + digest-pin the Orionfold proven-matrix images "
                    "(open embedder, CUDA-13 llama.cpp lane) before a live `up` — "
                    "M2; the bundle is rendered and `docker compose config`-valid now"
                ),
            )
        if not _which("docker"):
            raise PhaseError("docker not found", fix="install Docker CE (preinstalled on DGX OS 7.x)")
        compose_path = config.home / "compose.yaml"
        proc = _run(["docker", "compose", "-f", str(compose_path), "up", "-d"])
        if proc.returncode != 0:
            raise PhaseError(
                f"`docker compose up -d` failed (exit {proc.returncode})",
                fix=(proc.stderr or proc.stdout).strip()[:400] or "inspect `docker compose logs`",
            )

    def sidecar(self, config: FieldEditionConfig) -> None:
        # The Arena cockpit is the pipx fieldkit[arena] process (§5), not a
        # compose service. Health-poll if it is already up; otherwise the
        # operator brings it up via `fieldkit arena up` (wired fully at M2 with
        # the bootstrap that owns the pipx install lifecycle).
        import httpx  # core dep

        url = "http://127.0.0.1:7866/healthz"
        try:
            if httpx.get(url, timeout=2.0).status_code == 200:
                return
        except httpx.HTTPError:
            pass
        raise PhaseError(
            "Arena cockpit not reachable on :7866",
            fix="start it with `fieldkit arena up --no-open` (the bootstrap owns this at M2)",
        )

    def resident(self, config: FieldEditionConfig) -> None:
        import httpx  # core dep

        url = f"http://127.0.0.1:{config.lane.port}/v1/models"
        try:
            ok = httpx.get(url, timeout=2.0).status_code == 200
        except httpx.HTTPError:
            ok = False
        if not ok:
            raise PhaseError(
                f"serving lane not answering on :{config.lane.port}",
                fix="the lane container comes up in the `stack` phase; re-run `up` after it is healthy",
            )

    def verify(self, config: FieldEditionConfig) -> None:
        # The §8 first-boot eval gate. `up --verify` collapses steps 2-3 into
        # one command (§7): bring the stack up, then run the gate + emit the
        # receipt. The receipt is always written (pass or fail); a failing gate
        # raises so the phase is marked `failed` and `up` resumes here.
        from fieldkit.field_edition.verify import run_verify

        report, path = run_verify(config)
        if not report.ok:
            failed = ", ".join(f"{r.label} ({r.status})" for r in report.failures)
            raise PhaseError(
                f"first-boot eval gate failed: {failed}",
                fix=f"see the receipt at {path}; run `fieldkit field-edition verify` for per-gate fixes",
            )


@dataclass
class UpResult:
    """The outcome of a :func:`run_up`."""

    ran: list[str]
    skipped: list[str]
    planned: list[str]  # safe-only / dry-run: phases not executed, just reported
    failed: str | None
    fix: str
    dry_run: bool

    @property
    def ok(self) -> bool:
        return self.failed is None


def run_up(
    config: FieldEditionConfig | None = None,
    *,
    executor: Executor | None = None,
    force: bool = False,
    with_verify: bool = False,
    dry_run: bool = False,
    on_event: Callable[[str], None] | None = None,
) -> UpResult:
    """Run the phase machine; checkpoint after each phase; resume on re-run.

    Stops at the first phase that raises :class:`PhaseError`, leaving it marked
    ``failed`` so a later ``up`` resumes there. ``dry_run`` runs only the safe
    (local) phases and reports the rest as planned."""
    cfg = config or _compose.default_config()
    exe = executor or LiveExecutor()
    emit = on_event or (lambda _msg: None)
    state_path = cfg.home / "state.json"
    state = InstallState.load(state_path)

    def _eligible(p: Phase) -> bool:
        """A phase that this invocation considers at all (optional/verify gate)."""
        return not p.optional or (p.key == "verify" and with_verify)

    chosen = plan_remaining(
        state, force=force, with_verify=with_verify, safe_only=dry_run
    )
    chosen_keys = {p.key for p in chosen}
    # "skipped" = eligible phases not run this invocation because they are
    # already `done` (re-entrancy) — excludes the live phases a dry-run defers.
    skipped = [
        p.key
        for p in PHASES
        if _eligible(p)
        and p.key not in chosen_keys
        and not (dry_run and not p.safe)
        and state.status(p.key) == _DONE
    ]

    ran: list[str] = []
    for phase in chosen:
        emit(f"▶ {phase.label}: {phase.detail}")
        try:
            exe.dispatch(phase.key, cfg)
        except PhaseError as err:
            state.mark(phase.key, _FAILED)
            state.save(state_path)
            emit(f"✗ {phase.label}: {err}")
            return UpResult(
                ran=ran, skipped=skipped, planned=[], failed=phase.key, fix=err.fix, dry_run=dry_run
            )
        state.mark(phase.key, _DONE)
        state.save(state_path)
        ran.append(phase.key)
        emit(f"✓ {phase.label}")

    planned: list[str] = []
    if dry_run:
        # Report (don't run) the live phases that a real `up` would do next.
        planned = [p.key for p in PHASES if not p.safe and _eligible(p)]

    return UpResult(ran=ran, skipped=skipped, planned=planned, failed=None, fix="", dry_run=dry_run)
