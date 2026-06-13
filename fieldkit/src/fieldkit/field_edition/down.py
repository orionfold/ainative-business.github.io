# Copyright 2026 Manav Sehgal
# SPDX-License-Identifier: Apache-2.0
"""`fieldkit field-edition down` — stop + remove the stack (§7 uninstall, AC-6).

Implements the §7 uninstall / AC-6 "clean exit" contract of
``_SPECS/arena-field-edition-v1.md``: one command stops + removes the Compose
stack and leaves the box in its pre-install state, **without** destroying the
customer's data:

- ``down`` (default) — ``docker compose down`` removes the containers + the
  user-defined network but **preserves** the named Cortex volume (pgdata), the
  model store, and ``arena.db``. The downloaded models and ingested corpus
  survive, so a later ``up`` brings the same box back warm.
- ``down --purge`` — additionally drops the pgdata volume (``compose down -v``),
  the model store, ``arena.db``, and the rendered ``~/.orionfold`` bundle. This
  is the explicit opt-in "remove my data too" path; nothing is purged without it.

The Arena cockpit is the pipx ``fieldkit[arena]`` host process (§5), not a
container — ``down`` cannot (and must not) ``pipx uninstall`` the package whose
own process is running, so it stops the *stack* and prints the one-line pipx
uninstall as the final manual step.

Design (the deterministic-scripts invariant, same split as :mod:`up`):
:func:`plan_down` is **pure** — it returns the :class:`DownPlan` of exactly what
will be removed vs. preserved, with no I/O — so the honest "here's what --purge
would delete" report is unit-testable. The only I/O lives behind an injectable
:class:`DownExecutor` (``LiveDownExecutor`` shells to Docker + ``rmtree``; tests
use a fake).
"""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from fieldkit.field_edition.compose import FieldEditionConfig, default_config

__all__ = [
    "DownExecutor",
    "LiveDownExecutor",
    "DownPlan",
    "DownResult",
    "plan_down",
    "run_down",
]


@dataclass(frozen=True)
class DownPlan:
    """Pure description of what a ``down`` will do (no I/O).

    ``removes_volumes`` is the ``-v`` flag to ``compose down``; ``purge_paths``
    are the host paths deleted only under ``--purge``; ``preserved`` is the
    honest list of what survives so the operator can see the data is kept."""

    remove_volumes: bool
    purge_paths: tuple[Path, ...]
    preserved: tuple[str, ...]

    @property
    def purge(self) -> bool:
        return self.remove_volumes


def plan_down(config: FieldEditionConfig | None = None, *, purge: bool = False) -> DownPlan:
    """Pure: the set of removals/preservations for this ``down`` (no I/O).

    Default ``down`` preserves all data; ``purge`` adds the model store,
    ``arena.db``, and the rendered bundle to the delete list and flips the
    ``compose down -v`` flag so the named pgdata volume is dropped too."""
    cfg = config or default_config()
    arena_db = Path.home() / ".fieldkit" / "arena.db"
    if purge:
        purge_paths = (
            cfg.model_store,
            arena_db,
            cfg.home / "compose.yaml",
            cfg.home / ".env",
            cfg.home / "state.json",
        )
        preserved = ("the box's pre-install state (nothing kept)",)
    else:
        purge_paths = ()
        preserved = (
            f"Cortex pgdata volume ({cfg.postgres.volume})",
            f"model store ({cfg.model_store})",
            f"arena.db ({arena_db})",
        )
    return DownPlan(remove_volumes=purge, purge_paths=purge_paths, preserved=preserved)


# --- Execution (the only I/O) ------------------------------------------------


def _which(name: str) -> bool:
    return shutil.which(name) is not None


def _run(cmd: list[str], *, timeout: int = 300) -> subprocess.CompletedProcess:
    return subprocess.run(  # noqa: S603 — fixed argv, no shell
        cmd, capture_output=True, text=True, timeout=timeout, check=False
    )


class DownExecutor:
    """The ``down`` actions. Subclass / fake for tests."""

    def compose_down(self, config: FieldEditionConfig, *, remove_volumes: bool) -> None:  # pragma: no cover - overridden
        raise NotImplementedError

    def remove_path(self, path: Path) -> None:  # pragma: no cover - overridden
        raise NotImplementedError


class LiveDownExecutor(DownExecutor):
    """Runs ``down`` against the real box."""

    def compose_down(self, config: FieldEditionConfig, *, remove_volumes: bool) -> None:
        compose_path = config.home / "compose.yaml"
        if not compose_path.exists():
            # Nothing was ever rendered — treat as already down (idempotent).
            return
        if not _which("docker"):
            # The box has no docker to talk to; the stack can't be up. Honest
            # no-op rather than a hard failure on an already-clean box.
            return
        cmd = ["docker", "compose", "-f", str(compose_path), "down"]
        if remove_volumes:
            cmd.append("-v")
        proc = _run(cmd)
        if proc.returncode != 0:
            raise RuntimeError(
                f"`docker compose down` failed (exit {proc.returncode}): "
                + ((proc.stderr or proc.stdout).strip()[:300] or "inspect `docker compose ls`")
            )

    def remove_path(self, path: Path) -> None:
        if not path.exists():
            return
        if path.is_dir():
            shutil.rmtree(path)
        else:
            path.unlink()


@dataclass
class DownResult:
    """The outcome of a :func:`run_down`."""

    purged: bool
    removed_paths: list[str] = field(default_factory=list)
    preserved: list[str] = field(default_factory=list)
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None


def run_down(
    config: FieldEditionConfig | None = None,
    *,
    purge: bool = False,
    executor: DownExecutor | None = None,
    on_event: Callable[[str], None] | None = None,
) -> DownResult:
    """Stop + remove the stack; preserve data unless ``purge``. Idempotent.

    Returns a :class:`DownResult` listing what was removed vs. preserved so the
    CLI can print the honest exit summary (AC-6)."""
    cfg = config or default_config()
    exe = executor or LiveDownExecutor()
    emit = on_event or (lambda _msg: None)
    plan = plan_down(cfg, purge=purge)

    emit("▶ stopping the container stack" + (" + dropping volumes" if plan.remove_volumes else ""))
    try:
        exe.compose_down(cfg, remove_volumes=plan.remove_volumes)
    except Exception as err:  # noqa: BLE001 — surface any teardown failure honestly
        return DownResult(purged=purge, error=f"stack teardown failed: {str(err)[:300]}")
    emit("✓ stack down")

    removed: list[str] = []
    for path in plan.purge_paths:
        emit(f"▶ purging {path}")
        try:
            exe.remove_path(path)
        except Exception as err:  # noqa: BLE001
            return DownResult(
                purged=purge, removed_paths=removed,
                error=f"purge of {path} failed: {str(err)[:200]}",
            )
        removed.append(str(path))
        emit(f"✓ removed {path}")

    return DownResult(purged=purge, removed_paths=removed, preserved=list(plan.preserved))
