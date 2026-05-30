#!/usr/bin/env python3
# Copyright 2026 Manav Sehgal
# SPDX-License-Identifier: Apache-2.0
"""``python -m fieldkit.arena.scripts.import_existing`` — M2 retroactive load.

Thin shim around :func:`fieldkit.arena.importer.import_artifacts`. The full
logic lives in the importer module so the CLI (``fieldkit arena import``)
and the script form share one code path. Run this directly when you want
the script-shape exit semantics; use the CLI for tab-completion + the
Typer help-page.

Examples
--------

Plan-only (no writes; in-memory SQLite):

    python -m fieldkit.arena.scripts.import_existing --dry-run

Real run + refresh HF metadata over the wire:

    python -m fieldkit.arena.scripts.import_existing --refresh-hf

Test against a temp tree (used by ``fieldkit/tests/arena/``):

    python -m fieldkit.arena.scripts.import_existing \
        --repo-root /tmp/fixture --db /tmp/arena.db
"""

from __future__ import annotations

import argparse
import json
import logging
import sys

from fieldkit.arena.importer import DEFAULT_REPO_ROOT, import_artifacts
from fieldkit.arena.store import DEFAULT_DB_PATH


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="fieldkit-arena-import-existing",
        description=__doc__.split("\n\n", 1)[0],
    )
    p.add_argument(
        "--repo-root",
        default=str(DEFAULT_REPO_ROOT),
        help="Walk this repo root (default: the checkout this script ships in).",
    )
    p.add_argument(
        "--db",
        default=DEFAULT_DB_PATH,
        help="SQLite path to populate (default: %(default)s).",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Plan-only: in-memory SQLite, no on-disk writes. Prints the row counts.",
    )
    p.add_argument(
        "--refresh-hf",
        action="store_true",
        help="Hit the HuggingFace API for each Orionfold/ repo (default: cache-only).",
    )
    p.add_argument(
        "--no-mirror",
        action="store_true",
        help="Skip writing src/data/arena-mirror/leaderboard.json.",
    )
    p.add_argument(
        "--json",
        action="store_true",
        help="Emit the report as JSON (default: a human one-liner).",
    )
    p.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Log warnings + per-walk info to stderr.",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        stream=sys.stderr,
    )

    report = import_artifacts(
        repo_root=args.repo_root,
        db_path=args.db,
        dry_run=args.dry_run,
        refresh_hf=args.refresh_hf,
        write_mirror=not args.no_mirror,
    )

    if args.json:
        print(json.dumps(report.as_dict(), indent=2))
    else:
        mode = "dry-run" if args.dry_run else "wrote"
        print(f"[{mode}] arena.db ← {report.summary_line()}")
        if report.warnings and args.verbose:
            for w in report.warnings:
                print(f"  warning: {w}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
