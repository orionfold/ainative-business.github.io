# Copyright 2026 Manav Sehgal
# SPDX-License-Identifier: Apache-2.0
"""`fieldkit arena {serve,import,mirror,memcheck,rebuild-leaderboard,promote-run}`.

**M1 stub.** Six Typer subcommands declared; bodies raise `NotImplementedError`
with a milestone marker so the CLI surface is discoverable from day one
(`fieldkit arena --help` lists every command) but no command actually does
anything until its milestone lands. Mirrors the spec §3.4 CLI contract.

Wired into the top-level `fieldkit` CLI via `cli/__init__.py` so the path
`fieldkit arena <cmd>` resolves the way `fieldkit-curator` users expect.
"""

from __future__ import annotations

import json as _json

import typer

from fieldkit.arena import DEFAULT_ARENA_DB, DEFAULT_ARENA_PORT

__all__ = ["app"]

app = typer.Typer(
    name="arena",
    help=(
        "Orionfold Arena — operator cockpit for the DGX Spark. v0.2 surface: "
        "telemetry SSE + lanes + leaderboard + chat + side-by-side compare + "
        "rubric registry + thumbs prefs + Lab notes live on `fieldkit arena "
        "serve`; `fieldkit arena up` serves the baked cockpit + opens a browser "
        "(`pip install fieldkit[arena]` → `fieldkit arena up`); `fieldkit arena "
        "build` bakes the web UI into the wheel; `fieldkit arena import` (M2) "
        "seeds the DB; `fieldkit arena mirror` (M6) exports the leak-proof "
        "publishable slice. See specs/spark-arena-v1.md."
    ),
    no_args_is_help=True,
    add_completion=False,
)


@app.command("serve")
def serve(
    host: str = typer.Option("127.0.0.1", help="Bind host. Loopback only by default."),
    port: int = typer.Option(DEFAULT_ARENA_PORT, help="Bind port (spec §3.4)."),
    db: str = typer.Option(DEFAULT_ARENA_DB, help="Operator-private SQLite path."),
    repo_root: str = typer.Option(
        "",
        "--repo-root",
        help="Repo root for the static mirror JSON (default: cwd).",
    ),
    reload: bool = typer.Option(False, help="Hot-reload for development."),
    log_level: str = typer.Option("info", help="uvicorn log level."),
) -> None:
    """Launch the FastAPI cockpit sidecar at ``127.0.0.1:7866``.

    M5 surface — telemetry SSE + ``/api/lanes`` + ``/api/leaderboard`` +
    ``POST /api/chat/stream`` + ``GET /api/rubrics`` +
    ``POST /api/compare/stream`` + ``POST /api/prefs``. Mirror at M6.
    The cockpit landing at ``/arena/`` consumes ``/api/telemetry/stream``;
    ``/arena/chat/`` consumes ``POST /api/chat/stream``;
    ``/arena/compare/`` consumes ``POST /api/compare/stream``.
    """
    # Local import — keeps `fieldkit arena --help` cheap (FastAPI is heavy).
    from fieldkit.arena.server import serve as _serve

    _serve(
        host=host,
        port=port,
        db=db,
        repo_root=repo_root or None,
        reload=reload,
        log_level=log_level,
    )


@app.command("import")
def import_existing(
    db: str = typer.Option(DEFAULT_ARENA_DB, help="Operator-private SQLite path."),
    repo_root: str = typer.Option(
        "",
        "--repo-root",
        help="Walk this repo root (default: the checkout fieldkit ships in).",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run/--write",
        help="Plan-only: in-memory SQLite, no on-disk writes (default: write).",
    ),
    refresh_hf: bool = typer.Option(
        False,
        "--refresh-hf",
        help="Hit the HuggingFace API for each Orionfold/ repo (default: cache-only).",
    ),
    no_mirror: bool = typer.Option(
        False,
        "--no-mirror",
        help="Skip writing src/data/arena-mirror/leaderboard.json.",
    ),
    json_out: bool = typer.Option(
        False, "--json", help="Emit the row-count report as JSON."
    ),
) -> None:
    """Retroactive load: manifests + articles + bench evidence + HF metadata
    into `~/.fieldkit/arena.db` (spec §7). Idempotent — a second run produces
    identical row counts."""
    # Local import keeps `fieldkit arena --help` cheap (importer pulls pyyaml).
    from fieldkit.arena.importer import import_artifacts

    report = import_artifacts(
        repo_root=repo_root or None,
        db_path=db,
        dry_run=dry_run,
        refresh_hf=refresh_hf,
        write_mirror=not no_mirror,
    )
    if json_out:
        typer.echo(_json.dumps(report.as_dict(), indent=2))
    else:
        mode = "dry-run" if dry_run else "wrote"
        typer.echo(f"[{mode}] arena.db ← {report.summary_line()}")
        if report.warnings:
            typer.echo(f"  ({len(report.warnings)} warning(s); rerun with --json to see)")


@app.command("mirror")
def mirror(
    db: str = typer.Option(DEFAULT_ARENA_DB, help="Operator-private SQLite path."),
    out_dir: str = typer.Option(
        "src/data/arena-mirror",
        help="Target dir for the publishable JSON slice (chat_* never enumerated).",
    ),
    repo_root: str = typer.Option(
        "",
        "--repo-root",
        help="Repo root (resolves a relative --out-dir against this). Default: cwd.",
    ),
    allow_empty: bool = typer.Option(
        False, help="Permit a zero-row leaderboard export (default: refuse)."
    ),
    no_rebuild: bool = typer.Option(
        False,
        "--no-rebuild",
        help=(
            "Skip the implicit `rebuild-leaderboard` pre-step. Use when the "
            "leaderboard_rows table is already up-to-date and you only want "
            "to re-emit the JSON."
        ),
    ),
    json_out: bool = typer.Option(
        False, "--json", help="Emit the export report as JSON."
    ),
) -> None:
    """Export the publishable slice to ``src/data/arena-mirror/*.json``.

    The exporter uses a hardcoded allowlist
    (``fieldkit.arena.mirror.PUBLISHABLE_TABLES``); ``chat_*`` tables are
    **never** enumerated. Writes to ``<out_dir>/_staging/`` first then
    atomic-renames per ``[[reference_sync_workflow_nfs_mount]]``. The
    regression test ``fieldkit/tests/arena/test_mirror_does_not_leak.py``
    pins the leak-proof contract — see ``specs/spark-arena-v1.md`` §4.10.
    """
    # Local import — keeps `fieldkit arena --help` cheap (sqlite + dataclass
    # only by this path, but the convention holds).
    from fieldkit.arena.mirror import export_publishable_slice
    from fieldkit.arena.store import ArenaStore

    store = ArenaStore(db)
    store.initialize()
    with store:
        report = export_publishable_slice(
            store,
            out_dir=out_dir,
            allow_empty=allow_empty,
            rebuild=not no_rebuild,
            repo_root=repo_root or None,
        )
    if json_out:
        typer.echo(_json.dumps(report.as_dict(), indent=2))
    else:
        typer.echo(f"[wrote] {report.files_written[0]} ← {report.summary_line()}")
        if report.warnings:
            typer.echo(f"  ({len(report.warnings)} warning(s); rerun with --json to see)")


@app.command("record")
def record(
    db: str = typer.Option(DEFAULT_ARENA_DB, help="Operator-private SQLite path."),
    out: str = typer.Option(
        "public/arena-demo/fixtures.json",
        help="Target JSON for the demo replay bundle (served as a static asset).",
    ),
    repo_root: str = typer.Option(
        "",
        "--repo-root",
        help="Repo root (resolves a relative --out against this). Default: cwd.",
    ),
    max_chat: int = typer.Option(5, "--max-chat", help="Max curated chat runs."),
    max_compare: int = typer.Option(3, "--max-compare", help="Max curated compares."),
    sidecar: str = typer.Option(
        "http://127.0.0.1:7866",
        "--sidecar",
        help="Running sidecar to capture sanitized read-only stubs from.",
    ),
    json_out: bool = typer.Option(False, "--json", help="Emit the report as JSON."),
) -> None:
    """Record a curated demo-replay bundle so the cockpit is interactive
    WITHOUT a sidecar.

    Selects a small set of *real* runs from ``~/.fieldkit/arena.db`` and writes
    a static JSON the client replays token-by-token (same SSE wire format, real
    answers + measured TTFT/throughput; cadence synthesized from the measured
    tok/s). This is a deliberate, curated export — NOT a bulk dump — so review
    the output before publishing. Built with ``ARENA_DEMO=1`` the cockpit boots
    a fetch/EventSource shim that reads this file instead of the sidecar.
    """
    from fieldkit.arena.fixtures import record_demo_fixtures

    report = record_demo_fixtures(
        db_path=db,
        out_path=out,
        repo_root=repo_root or None,
        max_chat=max_chat,
        max_compare=max_compare,
        sidecar_url=sidecar,
    )
    if json_out:
        typer.echo(_json.dumps(report.as_dict(), indent=2))
    else:
        typer.echo(f"[wrote] {report.out_path} ← {report.summary_line()}")


@app.command("build")
def build_webui_cmd(
    repo_root: str = typer.Option(
        "",
        "--repo-root",
        help="Website checkout root (has astro.config.mjs + node_modules/astro). Default: cwd.",
    ),
    dest: str = typer.Option(
        "",
        "--dest",
        help="Override the bake destination (default: the packaged _webui/).",
    ),
    skip_astro: bool = typer.Option(
        False,
        "--skip-astro",
        help="Re-prune an existing build output without re-running the Astro build.",
    ),
    demo: bool = typer.Option(
        False,
        "--demo",
        help="Build the sidecar-less demo bundle (ARENA_DEMO=1 → dist-arena-demo-pruned/) "
        "for the public GitHub Pages preview, instead of the wheel bundle.",
    ),
) -> None:
    """Build the Orionfold Arena bundle (P7).

    **Builder-side only** — shells out to ``node node_modules/astro/astro.js
    build`` in the website checkout, then prunes the ``/arena`` routes + shared
    assets into a self-contained bundle. Two modes:

    * default (wheel) — ``ARENA_BUILD=1`` → bakes into
      ``fieldkit/src/fieldkit/arena/_webui/`` so the next ``fieldkit-curator``
      release ships it; served by ``fieldkit arena up``.
    * ``--demo`` — ``ARENA_DEMO=1`` → ``dist-arena-demo-pruned/`` (promoted +
      ``arena-demo/`` shim/fixtures + ``.nojekyll``) for the GitHub Pages preview.

    End users never run this — they run ``fieldkit arena up``.
    """
    from fieldkit.arena.webui import build_webui

    report = build_webui(
        repo_root=repo_root or None,
        dest=dest or None,
        skip_astro=skip_astro,
        demo=demo,
    )
    typer.echo(f"[baked] {report.summary_line()}")


@app.command("up")
def up(
    host: str = typer.Option("127.0.0.1", help="Bind host. Loopback only by default."),
    port: int = typer.Option(DEFAULT_ARENA_PORT, help="Bind port (spec §3.4)."),
    db: str = typer.Option(DEFAULT_ARENA_DB, help="Operator-private SQLite path."),
    repo_root: str = typer.Option(
        "", "--repo-root", help="Repo root for the static mirror JSON (default: cwd)."
    ),
    open_browser: bool = typer.Option(
        True, "--open/--no-open", help="Open the cockpit in a browser tab on boot."
    ),
    log_level: str = typer.Option("info", help="uvicorn log level."),
) -> None:
    """Serve the cockpit **and** open it in a browser — the one-command UX.

    ``pip install fieldkit[arena]`` → ``fieldkit arena up`` → the full
    cockpit at ``http://127.0.0.1:7866/arena/``. Requires the baked
    ``_webui/`` bundle (shipped in the wheel; build it with ``fieldkit arena
    build``). Falls back to API-only mode with a warning if the bundle is
    missing.
    """
    from fieldkit.arena.server import serve as _serve
    from fieldkit.arena.webui import bundle_present

    url = f"http://{host}:{port}/arena/"
    if not bundle_present():
        typer.echo(
            "⚠ packaged web UI not found (_webui/ missing) — serving API only. "
            "Run `fieldkit arena build` from the website checkout to bake it.",
            err=True,
        )
    else:
        typer.echo(f"Orionfold Arena → {url}")
        if open_browser:
            # Open after a short beat so uvicorn is listening. webbrowser is
            # non-blocking; uvicorn.run blocks below.
            import threading
            import time
            import webbrowser

            def _open() -> None:
                time.sleep(1.2)
                try:
                    webbrowser.open(url)
                except Exception:  # noqa: BLE001 — headless box, no browser
                    pass

            threading.Thread(target=_open, daemon=True).start()

    _serve(host=host, port=port, db=db, repo_root=repo_root or None, log_level=log_level)


@app.command("memcheck")
def memcheck() -> None:
    """Print the current unified-memory envelope + warm-lane footprint
    (M3 fills the body — reads `~/.hermes/config.yaml` + `Telemetry`)."""
    raise typer.Exit(_milestone_message("memcheck", "M3 — telemetry surface"))


@app.command("rebuild-leaderboard")
def rebuild_leaderboard(
    db: str = typer.Option(DEFAULT_ARENA_DB, help="Operator-private SQLite path."),
    json_out: bool = typer.Option(
        False, "--json", help="Emit the rebuild report as JSON."
    ),
) -> None:
    """Recompute the denormalized ``leaderboard_rows`` from ``bench_results``
    + the live ``compare_runs`` × ``rubric_scores`` × ``human_prefs`` join.

    Idempotent — re-running over an unchanged DB produces identical
    row counts. Implicitly run as a pre-step inside ``fieldkit arena
    mirror`` unless ``--no-rebuild`` is passed there.
    """
    from fieldkit.arena.mirror import rebuild_leaderboard as _rebuild
    from fieldkit.arena.store import ArenaStore

    store = ArenaStore(db)
    store.initialize()
    with store:
        report = _rebuild(store)
    if json_out:
        typer.echo(
            _json.dumps(
                {
                    "bench_rows": report.bench_rows_written,
                    "cockpit_rows": report.cockpit_rows_written,
                    "total_rows": report.total_rows,
                },
                indent=2,
            )
        )
    else:
        typer.echo(
            f"[rebuilt] leaderboard_rows: bench={report.bench_rows_written} "
            f"cockpit={report.cockpit_rows_written} total={report.total_rows}"
        )


@app.command("promote-run")
def promote_run(
    run_id: str = typer.Argument(..., help="`compare_runs.id` to mark publishable."),
    db: str = typer.Option(DEFAULT_ARENA_DB, help="Operator-private SQLite path."),
    redacted_prompt: str = typer.Option(
        "",
        help=(
            "Operator-supplied redacted prompt; only this string leaks to the "
            "public mirror (the raw `prompt` column is never enumerated)."
        ),
    ),
) -> None:
    """Mark a `compare_run` row as publishable and (optionally) supply a
    redacted prompt for the public mirror (M6 fills the body)."""
    raise typer.Exit(_milestone_message("promote-run", "M6 — mirror promotion gate"))


def _milestone_message(cmd: str, milestone: str) -> str:
    return (
        f"`fieldkit arena {cmd}` is an M1 stub — the body lands at "
        f"{milestone}. See specs/spark-arena-v1.md."
    )
