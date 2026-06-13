# Copyright 2026 Manav Sehgal
# SPDX-License-Identifier: Apache-2.0
"""`fieldkit field-edition {doctor,up,verify,down,repair,rollback,update}`.

The installer / orchestration surface for the Arena Field Edition (§7 of
``_SPECS/arena-field-edition-v1.md``). Wired into the top-level CLI so
``fieldkit field-edition <cmd>`` resolves the way operators expect.

**M1 status:** ``doctor`` is implemented for real (the §7 support-matrix
check — the gate the bootstrap runs before touching the box). The remaining
commands are milestone-marked stubs so ``fieldkit field-edition --help`` lists
the full surface from day one; each body lands at its milestone (Compose
bring-up + eval gate at M1→M2, signed update channel at M3).
"""

from __future__ import annotations

import json as _json

import typer

__all__ = ["app"]

app = typer.Typer(
    name="field-edition",
    help=(
        "Orionfold Arena Field Edition — the self-serve DGX Spark distributable "
        "(Arena + Advisor + Cortex + fieldkit + quants + Hermes). `doctor` checks "
        "the supported DGX OS / driver / CUDA / Container-Toolkit matrix; "
        "`up`/`verify`/`down`/`repair`/`rollback`/`update` orchestrate the "
        "Docker Compose stack (milestone stubs). See "
        "_SPECS/arena-field-edition-v1.md."
    ),
    no_args_is_help=True,
    add_completion=False,
)


def _milestone_message(cmd: str, milestone: str) -> str:
    return (
        f"`fieldkit field-edition {cmd}` is a stub — the body lands at "
        f"{milestone}. See _SPECS/arena-field-edition-v1.md §7."
    )


@app.command("doctor")
def doctor(
    json_out: bool = typer.Option(
        False, "--json", help="Emit the matrix verdict as JSON instead of a table."
    ),
) -> None:
    """Check the supported DGX OS / driver / CUDA / Container-Toolkit matrix.

    The §7 gate the bootstrap runs *before* installing — it refuses an
    untested base rather than installing onto it. Exit 0 when the matrix is
    satisfied, exit 1 when any check is too-old or missing (each failure names
    the reason and the fix).
    """
    from fieldkit.field_edition.doctor import run_doctor

    report = run_doctor()

    if json_out:
        payload = {
            "ok": report.ok,
            "checks": [
                {
                    "key": r.key,
                    "label": r.label,
                    "found": r.found,
                    "tested": r.tested,
                    "status": r.status,
                    "reason": r.reason,
                    "fix": r.fix,
                }
                for r in report.results
            ],
        }
        typer.echo(_json.dumps(payload, indent=2))
        raise typer.Exit(code=0 if report.ok else 1)

    for r in report.results:
        mark = "OK  " if r.ok else "FAIL"
        found = r.found or "(not detected)"
        line = f"  [{mark}] {r.label}: {found}"
        if r.status == "ok":
            line += f"  (tested ≥ {r.tested})" if r.tested[0:1].isdigit() else ""
        typer.echo(line)
        if not r.ok:
            typer.echo(f"         → {r.reason}")
            typer.echo(f"         → fix: {r.fix}")

    if report.ok:
        typer.echo("\nMatrix OK — this box matches the Field Edition support matrix.")
        raise typer.Exit(code=0)
    typer.echo(
        f"\nMatrix FAILED — {len(report.failures)} check(s) need attention before install.",
        err=True,
    )
    raise typer.Exit(code=1)


@app.command("up")
def up(
    verify: bool = typer.Option(
        False, "--verify", help="Run the first-boot eval gate after bring-up (collapses steps 2–3)."
    ),
) -> None:
    """Bring up the Compose stack + load the default resident Advisor (§7 step 2)."""
    raise typer.Exit(_milestone_message("up", "M1 — Docker Compose bring-up"))


@app.command("verify")
def verify() -> None:
    """Run the first-boot eval gate and emit the receipt (§8, AC-3)."""
    raise typer.Exit(_milestone_message("verify", "M1 — first-boot eval gate"))


@app.command("down")
def down(
    purge: bool = typer.Option(
        False, "--purge", help="Also remove downloaded models + data (explicit opt-in)."
    ),
) -> None:
    """Stop + remove the stack; preserve data/models unless ``--purge`` (§7, AC-6)."""
    raise typer.Exit(_milestone_message("down", "M2 — uninstall path"))


@app.command("repair")
def repair(
    component: str = typer.Argument(..., help="Component to repair, e.g. 'cortex'."),
) -> None:
    """Re-pull + re-gate a single component named by a failed gate (§8 failure UX)."""
    raise typer.Exit(_milestone_message("repair", "M2 — component repair"))


@app.command("rollback")
def rollback() -> None:
    """Restore the prior pinned matrix (manual escape hatch for §9 updates)."""
    raise typer.Exit(_milestone_message("rollback", "M3 — update channel"))


@app.command("update")
def update() -> None:
    """Update to the latest signed, eval-gated proven matrix; auto-rollback on fail (§9)."""
    raise typer.Exit(_milestone_message("update", "M3 — signed update channel"))
