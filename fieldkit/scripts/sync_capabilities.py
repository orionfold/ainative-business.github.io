#!/usr/bin/env python3
# Copyright 2026 Manav Sehgal
# SPDX-License-Identifier: Apache-2.0
"""Sync the canonical Spark capabilities JSON into the fieldkit package.

Source of truth lives at `scripts/lib/spark-capabilities.json` (authored
alongside the blog). The package ships its own copy at
`fieldkit/src/fieldkit/capabilities/data/spark-capabilities.json` so wheels
are self-contained and editable installs don't need the parent repo on disk.

This script keeps the two in sync and refuses to overwrite if the package
copy has been hand-edited (i.e. drifted from the source). It runs as both a
manual command and a pre-commit hook (see fieldkit/.pre-commit-config.yaml).

Usage:
    fieldkit/scripts/sync_capabilities.py            # check; non-zero on drift
    fieldkit/scripts/sync_capabilities.py --apply    # copy source → package
"""

from __future__ import annotations

import argparse
import filecmp
import shutil
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SOURCE = REPO_ROOT / "scripts" / "lib" / "spark-capabilities.json"
TARGET = (
    REPO_ROOT / "fieldkit" / "src" / "fieldkit" / "capabilities" / "data" / "spark-capabilities.json"
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Copy SOURCE → TARGET. Without this flag the script only checks for drift.",
    )
    args = parser.parse_args(argv)

    if not SOURCE.exists():
        sys.stderr.write(f"source not found: {SOURCE}\n")
        return 2
    if not TARGET.parent.exists():
        TARGET.parent.mkdir(parents=True, exist_ok=True)

    if TARGET.exists() and filecmp.cmp(SOURCE, TARGET, shallow=False):
        return 0

    if not args.apply:
        sys.stderr.write(
            "spark-capabilities.json drift detected:\n"
            f"  source: {SOURCE}\n"
            f"  target: {TARGET}\n"
            "Run `fieldkit/scripts/sync_capabilities.py --apply` to refresh the package copy.\n"
        )
        return 1

    shutil.copy2(SOURCE, TARGET)
    print(f"synced {SOURCE.relative_to(REPO_ROOT)} → {TARGET.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
