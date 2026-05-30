#!/usr/bin/env python3
# Copyright 2026 Manav Sehgal
# SPDX-License-Identifier: Apache-2.0
"""Regenerate the committed `.ipynb` from the `.py` percent source of truth.

DETERMINISTIC — no LLM. The `.py` percent is the reviewable source of truth;
the `.ipynb` is generated and committed because Colab opens it from GitHub. This
is a one-way generate (`.py` → `.ipynb`) so a hand-edit to the `.ipynb` never
silently wins over the `.py`.

Usage:
    sync_notebook.py --out notebooks/patent-strategist --which both
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import jupytext


def _sync(py_path: Path) -> Path:
    nb = jupytext.read(str(py_path))
    ipynb = py_path.with_suffix(".ipynb")
    jupytext.write(nb, str(ipynb), fmt="ipynb")
    return ipynb


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--which", choices=["builder", "user", "both"], default="both")
    args = ap.parse_args(argv)

    which = ["builder", "user"] if args.which == "both" else [args.which]
    written = []
    for w in which:
        py = args.out / f"{w}.py"
        if not py.exists():
            print(f"skip: {py} not found", file=sys.stderr)
            continue
        written.append(str(_sync(py)))
    if not written:
        print("nothing synced", file=sys.stderr)
        return 1
    print("synced .ipynb:")
    for w in written:
        print("  -", w)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
