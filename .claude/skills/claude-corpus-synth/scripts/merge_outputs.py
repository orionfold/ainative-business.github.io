"""Validate + consolidate claude-corpus-synth outputs into a final corpus JSONL.

Joins the deterministic queue (queue.jsonl from prepare_queue.py) with the
in-CC-session generation log (out.jsonl, written via Edit-append by Claude in
the skill's live loop). Drops rows that failed structural validation, writes a
final corpus file with stats footer.

NO Claude calls — pure validation/I/O.

Input shapes:
  queue.jsonl:  {"row_idx": 0, "family": "A1", "prompt": "Draft a claim …"}
  out.jsonl:    {"row_idx": 0, "response": "<think>…</think>final answer."}
                  (the skill records output tokens via input later if available)

Output shape (one JSONL line per validated row):
  {"row_idx": 0, "family": "A1", "prompt": "…", "response": "<think>…</think>…", "has_think": true}

Usage:
  python merge_outputs.py \\
      --queue /tmp/aifn-corpus-synth/queue.jsonl \\
      --out   /tmp/aifn-corpus-synth/out.jsonl \\
      --final /home/nvidia/data/corpus/patent-prod-2026-05-18.jsonl
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def has_think(text: str) -> bool:
    return "<think>" in text and "</think>" in text


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--queue", required=True, help="queue.jsonl from prepare_queue.py")
    p.add_argument("--out", required=True, help="out.jsonl from in-session generation pass")
    p.add_argument("--final", required=True, help="Final corpus JSONL path")
    p.add_argument("--strict", action="store_true",
                   help="Refuse to write if any queue row is missing from out.jsonl")
    return p.parse_args()


def main() -> int:
    args = parse_args()

    queue_path = Path(args.queue)
    out_path = Path(args.out)
    final_path = Path(args.final)

    if not queue_path.exists():
        print(f"ERROR: queue file not found: {queue_path}", file=sys.stderr)
        return 2
    if not out_path.exists():
        print(f"ERROR: out file not found: {out_path}", file=sys.stderr)
        return 2

    queue_by_idx: dict[int, dict] = {}
    with open(queue_path) as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            queue_by_idx[row["row_idx"]] = row

    out_by_idx: dict[int, dict] = {}
    n_dup = 0
    with open(out_path) as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                print(f"  WARN: skip malformed JSONL line: {exc}", file=sys.stderr)
                continue
            idx = row.get("row_idx")
            if idx is None or "response" not in row:
                print(f"  WARN: skip row missing row_idx or response: {row.keys()}", file=sys.stderr)
                continue
            if idx in out_by_idx:
                n_dup += 1  # last-write-wins semantics (resume safety)
            out_by_idx[idx] = row

    missing = sorted(set(queue_by_idx) - set(out_by_idx))
    extra = sorted(set(out_by_idx) - set(queue_by_idx))

    if missing and args.strict:
        print(f"ERROR: --strict: {len(missing)} queue rows missing from out.jsonl "
              f"(first 5: {missing[:5]})", file=sys.stderr)
        return 3
    if extra:
        print(f"  WARN: {len(extra)} out rows reference row_idx not in queue (first 5: {extra[:5]})",
              file=sys.stderr)

    n_total = len(queue_by_idx)
    n_generated = len(out_by_idx)
    n_valid = 0
    n_no_think = 0
    by_family: dict[str, dict[str, int]] = {}

    final_path.parent.mkdir(parents=True, exist_ok=True)
    with open(final_path, "w") as fh:
        for idx in sorted(queue_by_idx):
            q = queue_by_idx[idx]
            o = out_by_idx.get(idx)
            fam = q["family"]
            by_family.setdefault(fam, {"have": 0, "valid": 0, "no_think": 0, "missing": 0})
            if o is None:
                by_family[fam]["missing"] += 1
                continue
            by_family[fam]["have"] += 1
            response = o.get("response", "")
            has = has_think(response)
            if not has:
                by_family[fam]["no_think"] += 1
                n_no_think += 1
                continue
            merged = {
                "row_idx": idx,
                "family": fam,
                "prompt": q["prompt"],
                "response": response,
                "has_think": True,
            }
            fh.write(json.dumps(merged) + "\n")
            n_valid += 1
            by_family[fam]["valid"] += 1

    print(f"Wrote {final_path}")
    print(f"  queue rows:        {n_total}")
    print(f"  generated rows:    {n_generated} ({n_dup} duplicate lines in out.jsonl, last-wins)")
    print(f"  missing from out:  {len(missing)}")
    print(f"  no <think> block:  {n_no_think}")
    print(f"  valid + written:   {n_valid}")
    print(f"  yield:             {100*n_valid/max(n_total,1):.1f}%")
    print("\n  Per-family breakdown:")
    print(f"    {'family':<6}  {'valid':>6}  {'no_think':>9}  {'missing':>8}  {'have':>6}")
    for fam in sorted(by_family):
        s = by_family[fam]
        print(f"    {fam:<6}  {s['valid']:>6}  {s['no_think']:>9}  {s['missing']:>8}  {s['have']:>6}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
