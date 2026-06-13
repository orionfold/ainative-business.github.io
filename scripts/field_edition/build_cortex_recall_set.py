#!/usr/bin/env python3
# Copyright 2026 Manav Sehgal
# SPDX-License-Identifier: Apache-2.0
"""Vendor the frozen Advisor recall bench into the shipped Field Edition package.

The §8 Cortex gate (`fieldkit field-edition verify`) measures retrieval recall@5
against a corpus the customer's box ingested at `up` time. For that gate to run
on a fresh install with no repo checkout, the *queries + gold sources* must ride
the wheel — that is what this script produces:

    fieldkit/src/fieldkit/field_edition/data/cortex-recall-mini.json

It is a **deterministic projection** of the already-frozen Advisor recall bench
(`evidence/orionfold-advisor/advisor-bench-v0.1{,.heldout}.jsonl`) down to the
fields recall needs (task_id, question, gold source_ids, family, split,
behavior), sorted by task_id. The source bench sha is recorded so drift between
the vendored set and its parent bench is detectable; the output file's own sha
is what `fieldkit.field_edition.recall.RECALL_SET_SHA` pins.

**Why the full bench, not a sub-sample?** The live recall floor (0.95) sits only
~0.027 above the measured 0.977 — a ~2.3% natural miss rate against a 5% floor
tolerance. Sub-sampling to a few dozen rows makes the floor *fragile*: small-N
quantization means one or two misses swing recall past 0.95. Shipping the whole
frozen slice preserves the proven margin; "mini" here means *small vs a real
customer corpus*, not a sub-sample of the bench. A future `--per-family N` knob
can sub-sample if a faster gate is wanted, accepting that fragility.

Usage:

    python3 scripts/field_edition/build_cortex_recall_set.py          # write + print sha
    python3 scripts/field_edition/build_cortex_recall_set.py --check   # verify, no write
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
EVIDENCE_DIR = REPO_ROOT / "evidence" / "orionfold-advisor"
POOL_PATH = EVIDENCE_DIR / "advisor-bench-v0.1.jsonl"
HELDOUT_PATH = EVIDENCE_DIR / "advisor-bench-v0.1.heldout.jsonl"
OUT_PATH = (
    REPO_ROOT
    / "fieldkit"
    / "src"
    / "fieldkit"
    / "field_edition"
    / "data"
    / "cortex-recall-mini.json"
)

NAME = "cortex-recall-mini"
VERSION = "v0.1"
#: The corpus pack table the gate retrieves against (ingested by `up`).
CORPUS_TABLE = "advisor_corpus_v01"
#: The §8 published Cortex recall floor (kept in lockstep with verify.CORTEX_RECALL_FLOOR).
RECALL_FLOOR = 0.95


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _project(row: dict[str, Any]) -> dict[str, Any]:
    """Down to exactly what recall scoring needs — nothing model/answer-bearing."""
    return {
        "task_id": str(row["task_id"]),
        "question": str(row["question"]),
        "source_ids": sorted(str(s) for s in (row.get("source_ids") or [])),
        "family": str(row["family"]),
        "split": str(row["split"]),
        "expected_behavior": str(row["expected_behavior"]),
    }


def build() -> dict[str, Any]:
    rows = _read_jsonl(POOL_PATH) + _read_jsonl(HELDOUT_PATH)
    projected = sorted((_project(r) for r in rows), key=lambda r: r["task_id"])
    answerable = [r for r in projected if r["expected_behavior"] != "refuse"]
    bench_sha = hashlib.sha256(
        POOL_PATH.read_bytes() + HELDOUT_PATH.read_bytes()
    ).hexdigest()[:12]
    return {
        "name": NAME,
        "version": VERSION,
        "source_bench": [
            POOL_PATH.relative_to(REPO_ROOT).as_posix(),
            HELDOUT_PATH.relative_to(REPO_ROOT).as_posix(),
        ],
        "source_bench_sha256_12": bench_sha,
        "corpus_table": CORPUS_TABLE,
        "recall_floor": RECALL_FLOOR,
        "row_count": len(projected),
        "answerable_count": len(answerable),
        "rows": projected,
    }


def _canonical_bytes(doc: dict[str, Any]) -> bytes:
    return (json.dumps(doc, indent=2, sort_keys=True) + "\n").encode("utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="verify the vendored file matches; no write")
    parser.add_argument("--out", type=Path, default=OUT_PATH)
    args = parser.parse_args()

    doc = build()
    payload = _canonical_bytes(doc)
    sha = hashlib.sha256(payload).hexdigest()[:12]

    if args.check:
        if not args.out.exists():
            raise SystemExit(f"missing vendored recall set: {args.out}")
        current = args.out.read_bytes()
        cur_sha = hashlib.sha256(current).hexdigest()[:12]
        if current != payload:
            raise SystemExit(
                f"DRIFT: {args.out} sha {cur_sha} != rebuilt {sha} "
                f"(source bench changed? re-run without --check, then re-pin RECALL_SET_SHA)"
            )
        print(f"ok: {args.out.name} matches the frozen bench (sha {sha})")
        return

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_bytes(payload)
    print(f"wrote {args.out} ({doc['row_count']} rows, {doc['answerable_count']} answerable)")
    print(f"source bench sha12: {doc['source_bench_sha256_12']}")
    print(f"recall-set sha12 (pin this as RECALL_SET_SHA): {sha}")


if __name__ == "__main__":
    main()
