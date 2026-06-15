# Copyright 2026 Manav Sehgal
# SPDX-License-Identifier: Apache-2.0
"""`fieldkit field-edition repair <component>` — re-pull + re-gate one component.

Implements the §8 failure-UX escape hatch of ``_SPECS/arena-field-edition-v1.md``:
a failed first-boot/post-update gate names a component + the fix, and the fix is
``fieldkit field-edition repair <component>`` (e.g. "Cortex recall 0.91 < 0.95 —
embedder image digest mismatch; run `fieldkit field-edition repair cortex`").

Repair is scoped to **one component** so a single mis-pulled image / corrupt GGUF
doesn't force a whole-stack ``up``: it force-recreates that component's
container(s) (re-pulling the pinned image), re-pulls the model weights if the
component owns any, and then re-runs **only that component's §8 gate** — so the
operator gets a fresh honest receipt-line for the thing they repaired.

Components:

    advisor   the resident model lane — re-pull the GGUF + recreate the lane,
              then the `advisor` gate (curveball-v0.2 + refusal floor)
    cortex    the memory layer — recreate pgvector + the embedder, then the
              `cortex` gate (frozen recall + grounded contract)
    lane      the serving lane container only — recreate, then the `lane` gate
              (launch → 1 generation → clean teardown)

Design (the deterministic-scripts invariant, same split as :mod:`up`/:mod:`down`):
:func:`plan_repair` is **pure** — it validates the component name and returns the
:class:`RepairPlan` (which services to recreate, whether to re-pull, which gate to
re-run), no I/O — so the dispatch is unit-testable. The I/O lives behind an
injectable :class:`RepairExecutor` (recreate / pull) and the existing
:class:`~fieldkit.field_edition.verify.GateRunner` (measure the one gate).
"""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from typing import Callable

from fieldkit.field_edition import compose as _compose
from fieldkit.field_edition.compose import FieldEditionConfig, default_config
from fieldkit.field_edition.verify import (
    GATES,
    GateResult,
    GateRunner,
    LiveGateRunner,
    evaluate_gates,
)

__all__ = [
    "COMPONENTS",
    "RepairExecutor",
    "LiveRepairExecutor",
    "RepairPlan",
    "RepairResult",
    "plan_repair",
    "run_repair",
]


@dataclass(frozen=True)
class _Component:
    """The repair recipe for one component."""

    key: str
    services: tuple[str, ...]  # compose service container_names to force-recreate
    repulls_model: bool  # whether the component owns model weights to re-pull
    gate: str  # the §8 gate key to re-run after recreating


def _components(cfg: FieldEditionConfig) -> dict[str, _Component]:
    return {
        "advisor": _Component(
            "advisor", (cfg.lane.container_name,), repulls_model=True, gate="advisor"
        ),
        "cortex": _Component(
            "cortex",
            (cfg.postgres.container_name, cfg.embedder.container_name),
            repulls_model=False,
            gate="cortex",
        ),
        "lane": _Component(
            "lane", (cfg.lane.container_name,), repulls_model=False, gate="lane"
        ),
    }


#: The components a customer can repair (the names that appear in §8 fixes).
COMPONENTS: tuple[str, ...] = ("advisor", "cortex", "lane")


@dataclass(frozen=True)
class RepairPlan:
    """Pure description of a repair (no I/O)."""

    component: str
    services: tuple[str, ...]
    repull_model: bool
    gate: str


def plan_repair(component: str, config: FieldEditionConfig | None = None) -> RepairPlan:
    """Pure: validate the component name and return its repair recipe.

    Raises :class:`ValueError` (with the valid set) on an unknown component — the
    CLI turns that into a clean error rather than a traceback."""
    cfg = config or default_config()
    comps = _components(cfg)
    try:
        comp = comps[component]
    except KeyError:
        raise ValueError(
            f"unknown component {component!r} — repairable: {', '.join(COMPONENTS)}"
        ) from None
    return RepairPlan(comp.key, comp.services, comp.repulls_model, comp.gate)


# --- Execution (the only I/O) ------------------------------------------------


def _which(name: str) -> bool:
    return shutil.which(name) is not None


def _run(
    cmd: list[str], *, timeout: int = 1800, env: dict[str, str] | None = None
) -> subprocess.CompletedProcess:
    return subprocess.run(  # noqa: S603 — fixed argv, no shell
        cmd, capture_output=True, text=True, timeout=timeout, check=False, env=env
    )


class RepairExecutor:
    """The repair actions. Subclass / fake for tests."""

    def repull_model(self, config: FieldEditionConfig) -> None:  # pragma: no cover - overridden
        raise NotImplementedError

    def recreate(self, config: FieldEditionConfig, services: tuple[str, ...]) -> None:  # pragma: no cover
        raise NotImplementedError


class LiveRepairExecutor(RepairExecutor):
    """Runs repair against the real box."""

    def repull_model(self, config: FieldEditionConfig) -> None:
        # Re-pull is the same resumable-HF path `up` uses; until a Q4_K_M rev is
        # published + pinned (M2) this fails honestly with the same fix as `up`.
        from fieldkit.field_edition.up import LiveExecutor, PhaseError

        try:
            LiveExecutor().pull(config)
        except PhaseError as err:
            raise RuntimeError(f"{err} (fix: {err.fix})") from None

    def recreate(self, config: FieldEditionConfig, services: tuple[str, ...]) -> None:
        unpinned = _compose.unpinned_images(config)
        if unpinned:
            names = ", ".join(p.reference() for p in unpinned)
            raise RuntimeError(
                f"{len(unpinned)} image(s) not yet published/pinned: {names} — "
                "build + push + digest-pin the Orionfold proven-matrix images (M2)"
            )
        if not _which("docker"):
            raise RuntimeError("docker not found (preinstalled on DGX OS 7.x)")
        compose_path = config.home / "compose.yaml"
        # AD-FK-α: inject NGC_API_KEY (env → ~/.nim/secrets.env) so the bundle's
        # ${NGC_API_KEY:?…} interpolation resolves. A placeholder is acceptable
        # for non-embedder repairs; a cortex repair that starts with a bad key
        # fails its own gate honestly.
        env = _compose.compose_env(config, placeholder_if_missing=True)
        proc = _run(
            ["docker", "compose", "-f", str(compose_path), "up", "-d", "--force-recreate", *services],
            env=env,
        )
        if proc.returncode != 0:
            raise RuntimeError(
                f"force-recreate of {', '.join(services)} failed (exit {proc.returncode}): "
                + ((proc.stderr or proc.stdout).strip()[:300] or "inspect `docker compose logs`")
            )


@dataclass
class RepairResult:
    """The outcome of a :func:`run_repair`."""

    component: str
    gate: GateResult | None
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None and self.gate is not None and self.gate.ok


def run_repair(
    component: str,
    config: FieldEditionConfig | None = None,
    *,
    executor: RepairExecutor | None = None,
    runner: GateRunner | None = None,
    on_event: Callable[[str], None] | None = None,
) -> RepairResult:
    """Recreate one component, optionally re-pull its model, then re-run its gate.

    Returns the single :class:`GateResult` for the repaired component so the CLI
    prints a fresh honest receipt-line (pass/fail/error) for exactly the thing
    repaired (§8 failure UX)."""
    cfg = config or default_config()
    exe = executor or LiveRepairExecutor()
    run = runner or LiveGateRunner()
    emit = on_event or (lambda _msg: None)

    try:
        plan = plan_repair(component, cfg)
    except ValueError as err:
        return RepairResult(component=component, gate=None, error=str(err))

    if plan.repull_model:
        emit(f"▶ re-pulling {component} model weights")
        try:
            exe.repull_model(cfg)
        except Exception as err:  # noqa: BLE001
            return RepairResult(component, gate=None, error=f"re-pull failed: {str(err)[:300]}")
        emit("✓ model re-pulled")

    emit(f"▶ recreating {', '.join(plan.services)}")
    try:
        exe.recreate(cfg, plan.services)
    except Exception as err:  # noqa: BLE001
        return RepairResult(component, gate=None, error=f"recreate failed: {str(err)[:300]}")
    emit("✓ recreated")

    emit(f"▶ re-running the {plan.gate} gate")
    outcome = run.measure(plan.gate, cfg)
    report = evaluate_gates({plan.gate: outcome}, gates=tuple(g for g in GATES if g.key == plan.gate))
    result = report.results[0] if report.results else None
    if result is not None:
        emit(f"{'✓' if result.ok else '✗'} {result.label}: {result.detail}")
    return RepairResult(component, gate=result)
