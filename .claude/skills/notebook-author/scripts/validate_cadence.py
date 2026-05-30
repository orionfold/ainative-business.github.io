#!/usr/bin/env python3
# Copyright 2026 Manav Sehgal
# SPDX-License-Identifier: Apache-2.0
"""Validate the explainer→code→interpretation cadence (spec §4.3) + check no
prose TODO markers survive. DETERMINISTIC — no LLM. Exit non-zero on violation
so it gates the handoff.

The contract: a notebook is a marketing landing page. Every code cell must be
*preceded* by a markdown cell that explains why and *followed* by one that
interprets the result — no naked code, no uninterpreted output. The branded
banner (markdown, first cell) and the parameters/badges cells satisfy this
naturally, so no exemptions are needed.

Usage:
    validate_cadence.py --out notebooks/patent-strategist --which both
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import jupytext

TODO = "TODO(notebook-author):"


def _check(py_path: Path) -> list[str]:
    nb = jupytext.read(str(py_path))
    cells = nb.cells
    problems: list[str] = []
    for i, c in enumerate(cells):
        src = (c.get("source") or "").strip()
        if TODO in src:
            problems.append(f"cell {i}: unfilled '{TODO}' marker survives")
        if c.get("cell_type") != "code":
            continue
        if not src:
            continue  # empty code cell — ignore
        prev_md = i > 0 and cells[i - 1].get("cell_type") == "markdown"
        next_md = i + 1 < len(cells) and cells[i + 1].get("cell_type") == "markdown"
        if not prev_md:
            problems.append(f"cell {i}: code cell not preceded by an explainer markdown")
        if not next_md:
            problems.append(f"cell {i}: code cell not followed by an interpretation markdown")
    return problems


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--which", choices=["builder", "user", "both"], default="both")
    args = ap.parse_args(argv)

    which = ["builder", "user"] if args.which == "both" else [args.which]
    failed = False
    for w in which:
        py = args.out / f"{w}.py"
        if not py.exists():
            print(f"skip: {py} not found")
            continue
        problems = _check(py)
        if problems:
            failed = True
            print(f"FAIL {py}:")
            for p in problems:
                print("   -", p)
        else:
            print(f"PASS {py}: cadence clean, no TODO markers")
    if failed:
        print("\ncadence validation failed — fix the .py, re-sync, re-validate.")
        return 1
    print("\nall notebooks pass the explainer→code→interpretation cadence.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
