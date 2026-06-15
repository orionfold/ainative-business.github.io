# Copyright 2026 Manav Sehgal
# SPDX-License-Identifier: Apache-2.0
"""`fieldkit field-edition {doctor,up,onboard,verify,down,repair,rollback,update}`.

The installer / orchestration surface for the Arena Field Edition (§7 of
``_SPECS/arena-field-edition-v1.md``). Wired into the top-level CLI so
``fieldkit field-edition <cmd>`` resolves the way operators expect.

**Status:** the full §7 + §9 CLI surface is implemented. ``doctor`` (the §7
support-matrix check), ``up`` (the checkpointed Compose bring-up), and ``verify``
(the §8 first-boot eval gate + receipt) are M1. ``down`` (§7 uninstall / AC-6),
``repair`` (the §8 single-component re-pull + re-gate), ``rollback`` and
``update`` (the §9 eval-gated, rollback-safe proven-matrix channel) are now real
too — each fails *honestly* at the boundaries that still need M2/M3 infra (the
unbuilt GHCR images, the unpublished signed update channel) rather than stubbing.
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
        "the supported DGX OS / driver / CUDA / Container-Toolkit matrix; `up` "
        "brings up the Compose stack; `verify` runs the §8 first-boot eval gate + "
        "receipt; `down` uninstalls (AC-6); `repair` re-pulls + re-gates one "
        "component; `update`/`rollback` are the §9 eval-gated proven-matrix "
        "channel. See _SPECS/arena-field-edition-v1.md."
    ),
    no_args_is_help=True,
    add_completion=False,
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
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Run only the safe local phases (matrix gate + write the bundle) and print the rest of the plan.",
    ),
    force: bool = typer.Option(
        False, "--force", help="Re-run every phase, ignoring the saved checkpoint."
    ),
    open_embedder: bool = typer.Option(
        False,
        "--open-embedder",
        help="Use the open no-NGC embedder (v1.1 path; image not yet published) instead of the v1 NIM default.",
    ),
) -> None:
    """Bring up the Compose stack + load the default resident Advisor (§7 step 2).

    A checkpointed, re-entrant phase machine — a re-run resumes from the last
    good phase. ``--dry-run`` writes the digest-pinned Compose bundle into
    ``~/.orionfold/`` and prints the remaining plan without pulling or launching
    anything.
    """
    from fieldkit.field_edition.compose import default_config
    from fieldkit.field_edition.up import PHASES, run_up

    config = default_config()
    if open_embedder:
        config = config.with_open_embedder()

    detail = {p.key: p.detail for p in PHASES}
    result = run_up(
        config,
        force=force,
        with_verify=verify,
        dry_run=dry_run,
        on_event=lambda msg: typer.echo("  " + msg),
    )

    if result.skipped:
        typer.echo(f"\n  skipped (already done): {', '.join(result.skipped)}")

    if not result.ok:
        typer.echo(f"\nStopped at `{result.failed}` — {detail.get(result.failed, '')}.", err=True)
        if result.fix:
            typer.echo(f"  → fix: {result.fix}", err=True)
        typer.echo("  Re-run `fieldkit field-edition up` to resume from this phase.", err=True)
        raise typer.Exit(code=1)

    if result.dry_run:
        typer.echo(f"\nBundle written to {config.home}/compose.yaml (+ .env).")
        if result.planned:
            typer.echo("Remaining (a real `up` would run):")
            for key in result.planned:
                typer.echo(f"  • {key} — {detail.get(key, '')}")
        typer.echo("\nValidate it: `docker compose -f ~/.orionfold/compose.yaml config`.")
        raise typer.Exit(code=0)

    typer.echo("\nField Edition up — stack live, resident model warm.")
    raise typer.Exit(code=0)


@app.command("verify")
def verify(
    json_out: bool = typer.Option(
        False, "--json", help="Emit the receipt as JSON instead of a table."
    ),
    hermes: bool = typer.Option(
        False, "--hermes", help="Also run the optional Hermes MCP tool round-trip gate."
    ),
) -> None:
    """Run the first-boot eval gate and emit the receipt (§8, AC-3).

    Walks the five component gates (fieldkit · Advisor · Cortex · serving lane ·
    Hermes), applies the published floors, and **always writes the receipt** —
    pass or fail — to ``~/.orionfold/receipts/``. Exit 0 when every gate passes
    (or is skipped); exit 1 when any gate fails or could not run (each names the
    component, the gate, and the fix).
    """
    from fieldkit.field_edition.compose import default_config
    from fieldkit.field_edition.verify import run_verify

    config = default_config()
    report, path = run_verify(
        config,
        with_hermes=hermes,
        on_event=(None if json_out else (lambda msg: typer.echo("  " + msg))),
    )

    if json_out:
        # Echo the receipt exactly as written to disk (carries generated_at).
        typer.echo(path.read_text(encoding="utf-8").rstrip("\n"))
        typer.echo(f"\nReceipt: {path}", err=True)
        raise typer.Exit(code=0 if report.ok else 1)

    typer.echo(f"\nReceipt written to {path}")
    if report.ok:
        typer.echo("Field Edition verify PASSED — every gate green (no vanity passes).")
        raise typer.Exit(code=0)
    typer.echo(
        f"\nVerify FAILED — {len(report.failures)} gate(s) need attention:", err=True
    )
    for r in report.failures:
        typer.echo(f"  [{r.status.upper()}] {r.label}: {r.detail}", err=True)
        if r.fix:
            typer.echo(f"         → fix: {r.fix}", err=True)
    raise typer.Exit(code=1)


@app.command("down")
def down(
    purge: bool = typer.Option(
        False, "--purge", help="Also remove downloaded models + data (explicit opt-in)."
    ),
) -> None:
    """Stop + remove the stack; preserve data/models unless ``--purge`` (§7, AC-6).

    Default ``down`` removes the containers + network but keeps the Cortex
    volume, model store, and ``arena.db`` (a later ``up`` comes back warm).
    ``--purge`` additionally drops those — the explicit "remove my data" path.
    The Arena cockpit is a pipx host process, not a container, so its uninstall
    is printed as the final manual step rather than self-destructing this CLI.
    """
    from fieldkit.field_edition.compose import default_config
    from fieldkit.field_edition.down import run_down

    result = run_down(
        default_config(), purge=purge, on_event=lambda msg: typer.echo("  " + msg)
    )
    if not result.ok:
        typer.echo(f"\nDown FAILED — {result.error}", err=True)
        raise typer.Exit(code=1)

    if result.removed_paths:
        typer.echo("\nRemoved:")
        for p in result.removed_paths:
            typer.echo(f"  • {p}")
    if result.preserved:
        typer.echo("\nPreserved:")
        for p in result.preserved:
            typer.echo(f"  • {p}")
    typer.echo(
        "\nStack down. To remove the Arena cockpit too: `pipx uninstall fieldkit`."
    )
    raise typer.Exit(code=0)


@app.command("onboard")
def onboard(
    no_open: bool = typer.Option(
        False, "--no-open", help="Do not auto-open the cockpit at the end (headless / CI)."
    ),
    verify: bool = typer.Option(
        False, "--verify", help="Also run the first-boot eval gate after bring-up."
    ),
    force: bool = typer.Option(
        False, "--force", help="Re-run every phase, ignoring the saved checkpoint."
    ),
    open_embedder: bool = typer.Option(
        False,
        "--open-embedder",
        help="Use the open no-NGC embedder (v1.1 path) instead of the v1 NIM default.",
    ),
) -> None:
    """Guided onboarding — the customer-shaped front door (wraps doctor + up).

    A Rich-rendered linear flow: greet, run the preflight matrix, capture a free
    NGC key if one is missing, bring the stack up while narrating each phase +
    showing a named download manifest + 'while you wait' orientation cards, then
    open the cockpit warm. The headless ``up``/``doctor`` engines do the work
    underneath; ``onboard`` owns only the experience. Re-entrant — re-run to
    resume from a stopped step. This is what ``curl … | sh`` invokes.
    """
    from fieldkit.field_edition.compose import default_config
    from fieldkit.field_edition.onboard import run_onboard

    config = default_config()
    if open_embedder:
        config = config.with_open_embedder()

    result = run_onboard(
        config,
        auto_open=not no_open,
        with_verify=verify,
        force=force,
    )
    raise typer.Exit(code=0 if result.ok else 1)


@app.command("ingest")
def ingest(
    force: bool = typer.Option(
        False, "--force", help="Re-ingest even if the corpus table already has chunks."
    ),
) -> None:
    """Ingest the vendored Advisor demo corpus into Cortex (AD-FK-β).

    A fresh box boots an empty pgvector, so the §8 Cortex gate can't pass until
    the demo corpus is seeded. ``up`` runs this automatically; this command is
    the manual / re-ingest hatch. Idempotent: a non-empty corpus is left as-is
    unless ``--force`` (so a customer's own ingest is never clobbered).
    """
    from fieldkit.field_edition.compose import default_config
    from fieldkit.field_edition.ingest import run_ingest

    result = run_ingest(
        default_config(), force=force, on_event=lambda msg: typer.echo("  " + msg)
    )
    if not result.ok:
        typer.echo(f"\nIngest FAILED — {result.error}", err=True)
        raise typer.Exit(code=1)
    if result.skipped:
        typer.echo(f"\nCorpus already present — {result.sources} sources (use --force to re-ingest).")
    else:
        typer.echo(
            f"\nIngested {result.chunks_written} chunks from {result.sources} sources "
            "into advisor_corpus_v01."
        )
    raise typer.Exit(code=0)


@app.command("repair")
def repair(
    component: str = typer.Argument(..., help="Component to repair: advisor | cortex | lane."),
) -> None:
    """Re-pull + re-gate a single component named by a failed gate (§8 failure UX).

    Force-recreates the component's container(s) (re-pulling the pinned image),
    re-pulls model weights if it owns any, then re-runs only that component's §8
    gate and prints a fresh honest receipt-line for it.
    """
    from fieldkit.field_edition.compose import default_config
    from fieldkit.field_edition.repair import run_repair

    result = run_repair(
        component, default_config(), on_event=lambda msg: typer.echo("  " + msg)
    )
    if result.error:
        typer.echo(f"\nRepair FAILED — {result.error}", err=True)
        raise typer.Exit(code=1)

    gate = result.gate
    if gate is None:
        typer.echo(f"\nRepair of `{component}` produced no gate result.", err=True)
        raise typer.Exit(code=1)
    typer.echo(f"\n[{gate.status.upper()}] {gate.label}: {gate.detail}")
    if not gate.ok:
        if gate.fix:
            typer.echo(f"  → fix: {gate.fix}", err=True)
        raise typer.Exit(code=1)
    typer.echo(f"Repair of `{component}` PASSED its gate.")
    raise typer.Exit(code=0)


@app.command("rollback")
def rollback() -> None:
    """Restore the prior pinned matrix + re-apply it (manual §9 escape hatch)."""
    from fieldkit.field_edition.compose import default_config
    from fieldkit.field_edition.update import run_rollback

    result = run_rollback(default_config(), on_event=lambda msg: typer.echo("  " + msg))
    if not result.ok:
        typer.echo(f"\nRollback FAILED — {result.error}", err=True)
        if result.fix:
            typer.echo(f"  → fix: {result.fix}", err=True)
        raise typer.Exit(code=1)
    typer.echo(f"\n{result.message}.")
    raise typer.Exit(code=0)


@app.command("update")
def update() -> None:
    """Update to the latest signed, eval-gated proven matrix; auto-rollback on fail (§9).

    Fetches the new pinned matrix, cosign-verifies it, applies it, re-runs the §8
    gate, emits a fresh receipt, and rolls back automatically if the gate fails.
    The signed GHCR channel is published at M3 — until then this aborts honestly
    (no published channel) rather than pretending to update.
    """
    from fieldkit.field_edition.compose import default_config
    from fieldkit.field_edition.update import run_update

    result = run_update(default_config(), on_event=lambda msg: typer.echo("  " + msg))
    if not result.ok:
        typer.echo(f"\nUpdate aborted — {result.error}", err=True)
        if result.rolled_back:
            typer.echo(f"  {result.message}.", err=True)
        if result.fix:
            typer.echo(f"  → fix: {result.fix}", err=True)
        raise typer.Exit(code=1)
    typer.echo(f"\n{result.message}.")
    if result.receipt_path:
        typer.echo(f"Receipt: {result.receipt_path}")
    raise typer.Exit(code=0)
