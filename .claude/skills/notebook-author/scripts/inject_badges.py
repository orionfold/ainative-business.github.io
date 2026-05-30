#!/usr/bin/env python3
# Copyright 2026 Manav Sehgal
# SPDX-License-Identifier: Apache-2.0
"""Inject / refresh the Open-in-Colab / Open-in-Kaggle badge row in a vertical's
notebooks. DETERMINISTIC — no LLM.

Each notebook gets a badge cell (tagged `badges`) directly after the
`parameters` cell, with a labelled row per notebook so a reader on either can
jump to the other: **Build it:** → builder.ipynb, **Use it:** → user.ipynb,
plus the HF model repo. Idempotent — re-running replaces the existing badge cell
rather than stacking a new one.

Usage:
    inject_badges.py --vertical patent-strategist --out notebooks/patent-strategist \
        [--hf-repo Orionfold/...] [--branch main]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import jupytext

sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "fieldkit" / "src"))
from fieldkit.notebook import badge_markdown, colab_url, kaggle_url, notebook_path  # noqa: E402


def _badge_block(vertical: str, branch: str, hf_repo: str | None) -> str:
    bp = notebook_path(vertical, "builder")
    up = notebook_path(vertical, "user")
    rows = [
        badge_markdown(colab=colab_url(bp, branch=branch), kaggle=kaggle_url(bp, branch=branch),
                       label="Build it"),
        badge_markdown(colab=colab_url(up, branch=branch), kaggle=kaggle_url(up, branch=branch),
                       label="Use it"),
    ]
    if hf_repo:
        rows.append(badge_markdown(hf=f"https://huggingface.co/{hf_repo}", label="Model"))
    return "\n\n".join(r for r in rows if r)


def _inject(path: Path, badge_md: str) -> bool:
    if not path.exists():
        return False
    nb = jupytext.read(str(path))
    # Drop any existing badges cell.
    nb.cells = [c for c in nb.cells if "badges" not in (c.get("metadata", {}).get("tags") or [])]
    # Find the parameters cell index; insert right after it (else at top).
    insert_at = 0
    for i, c in enumerate(nb.cells):
        if "parameters" in (c.get("metadata", {}).get("tags") or []):
            insert_at = i + 1
            break
    from nbformat.v4 import new_markdown_cell
    cell = new_markdown_cell(badge_md)
    cell.metadata["tags"] = ["badges"]
    nb.cells.insert(insert_at, cell)
    jupytext.write(nb, str(path), fmt="py:percent")
    return True


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--vertical", required=True)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--hf-repo", default=None)
    ap.add_argument("--branch", default="main")
    args = ap.parse_args(argv)

    badge_md = _badge_block(args.vertical, args.branch, args.hf_repo)
    touched = []
    for which in ("builder", "user"):
        p = args.out / f"{which}.py"
        if _inject(p, badge_md):
            touched.append(str(p))
    if not touched:
        print("no .py notebooks found to inject into", file=sys.stderr)
        return 1
    print("injected badge row into:")
    for t in touched:
        print("  -", t)
    print("\nRe-run sync_notebook.py to regenerate the .ipynb files.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
