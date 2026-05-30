#!/usr/bin/env python3
# Copyright 2026 Manav Sehgal
# SPDX-License-Identifier: Apache-2.0
"""Balanced 20-row queue for the local-vs-CC patent <think> routing bench.

Forces 5 rows per family across A1/A2/A4/E1 (E2 dropped — MCQ generation is
the least patent-prose-shaped family and doesn't discriminate generators on
the legal-coherence bar). Reuses FAMILY_TEMPLATES + SPICE from the
claude-corpus-synth skill so the bench tests the same prompts the production
corpus would receive.

Output schema (one JSONL line per row):
  {"row_idx": 0, "family": "A1", "prompt": "Draft a single independent claim …"}

Usage:
  python bench_local_vs_cc_prepare.py
  python bench_local_vs_cc_prepare.py --seed 7 --rows-per-family 5 \\
      --output /tmp/aifn-bench-local-vs-cc/queue.jsonl
"""
from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path

SKILL_SCRIPTS = (
    Path(__file__).resolve().parent.parent
    / ".claude/skills/claude-corpus-synth/scripts"
)
sys.path.insert(0, str(SKILL_SCRIPTS))
from prepare_queue import FAMILY_TEMPLATES, SPICE, build_prompt  # noqa: E402

BENCH_FAMILIES = ("A1", "A2", "A4", "E1")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--rows-per-family", type=int, default=5)
    p.add_argument(
        "--output",
        default="/tmp/aifn-bench-local-vs-cc/queue.jsonl",
    )
    return p.parse_args()


def main() -> int:
    args = parse_args()
    rng = random.Random(args.seed)

    plan: list[str] = []
    for fam in BENCH_FAMILIES:
        plan.extend([fam] * args.rows_per_family)
    rng.shuffle(plan)

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w") as fh:
        for idx, family in enumerate(plan):
            row = {
                "row_idx": idx,
                "family": family,
                "prompt": build_prompt(family, rng),
            }
            fh.write(json.dumps(row) + "\n")

    counts: dict[str, int] = {}
    for fam in plan:
        counts[fam] = counts.get(fam, 0) + 1
    print(f"Wrote {out_path} ({len(plan)} rows, seed={args.seed})")
    for fam in sorted(counts):
        print(f"  {fam}: {counts[fam]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
