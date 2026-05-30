#!/usr/bin/env python3
# Copyright 2026 Manav Sehgal
# SPDX-License-Identifier: Apache-2.0
"""Convert an executed notebook to a single self-contained HTML file for
Playwright-MCP screenshotting. DETERMINISTIC — no LLM.

`--embed-images` inlines outputs so the file:// page renders with no missing
assets. Output goes to /tmp scratch.

Usage:
    notebook_to_html.py --executed /tmp/aifn-nb-snapshot/<v>/user.executed.ipynb \
        [--out /tmp/aifn-nb-snapshot/<v>/user.html]
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--executed", required=True, type=Path)
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args(argv)

    if not args.executed.exists():
        print(f"executed notebook not found: {args.executed}", file=sys.stderr)
        return 2
    out = args.out or args.executed.with_suffix(".html")
    out.parent.mkdir(parents=True, exist_ok=True)

    cmd = [
        sys.executable, "-m", "jupyter", "nbconvert", "--to", "html",
        "--embed-images", "--output", out.name, "--output-dir", str(out.parent),
        str(args.executed),
    ]
    rc = subprocess.run(cmd).returncode
    if out.exists():
        print(f"html → {out}")
        print(f"open it in Playwright: file://{out}")
    else:
        print("nbconvert produced no HTML", file=sys.stderr)
        return rc or 1
    return rc


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
