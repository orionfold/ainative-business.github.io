#!/usr/bin/env python3
# Copyright 2026 Manav Sehgal
# SPDX-License-Identifier: Apache-2.0
"""Emit `exports/index.json` mapping each captured image to its notebook +
label, for downstream reuse (site cards, HF READMEs, social). DETERMINISTIC.

Walks `exports/{builder,user}/*.png` (both the deterministic matplotlib heroes
and the Playwright-captured PNGs the session saved) and writes a stable index
keyed by notebook → label → relative path.

Usage:
    build_index.py --out notebooks/<vertical>/exports
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", required=True, type=Path)
    args = ap.parse_args(argv)

    index: dict[str, dict[str, str]] = {}
    for which in ("builder", "user"):
        d = args.out / which
        if not d.is_dir():
            continue
        for png in sorted(d.glob("*.png")):
            index.setdefault(which, {})[png.stem] = f"{which}/{png.name}"

    total = sum(len(v) for v in index.values())
    index_path = args.out / "index.json"
    index_path.write_text(json.dumps(index, indent=2) + "\n", encoding="utf-8")
    print(f"indexed {total} images → {index_path}")
    for which, items in index.items():
        for label, rel in items.items():
            print(f"  {which}/{label}: {rel}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
