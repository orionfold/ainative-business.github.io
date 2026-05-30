#!/usr/bin/env python3
# Copyright 2026 Manav Sehgal
# SPDX-License-Identifier: Apache-2.0
"""Merge a MedMCQA subset into one JSONL for VerticalBench.

MedMCQA (`openlifescienceai/medmcqa`, paper arxiv 2203.14371, Apache-2.0)
is a 4-option MCQ medical-domain benchmark drawn from Indian medical
entrance / AIIMS / NEET-PG exams. Three splits: train (182,822 rows),
validation (4,183 rows with gold labels), test (6,150 rows with `cop=-1`,
labels held for the public leaderboard).

This script samples N rows from the *validation* split (default 50) into
one JSONL the v0.4.1 `VerticalBench.from_jsonl(..., format="legalbench")`
loader consumes. Schema matches `cyber_merge.py` (CyberMetric was the
first MCQ vertical to write this shape; medical is the second reuse —
per `[[feedback_keep_scorer_local_until_reuse]]` the `mcq_letter` scorer
stays in `g3_*` until a third vertical promotes it to `fieldkit.eval`).

    text     formatted MCQ prompt with 4 options + instruction to reply
             with only one letter (A/B/C/D)
    answer   the gold solution letter (mapped from MedMCQA's `cop` int)
    task     "medmcqa-<subject>" (preserves subject_name for per-subject
             slice analysis — Physiology/Pathology/Pharmacology/etc.)
    id       medmcqa-<source_row_index>

Why validation, not test: MedMCQA's `test` split has `cop=-1` for every
row (labels held by leaderboard). Validation has true labels and is the
standard slice for offline eval (per the original MedMCQA paper).

Env knobs:
    MEDMCQA_ROOT       /home/nvidia/data/eval-benches/medmcqa
    MEDMCQA_SRC        <ROOT>/data/validation-00000-of-00001.parquet
    MEDMCQA_OUT        <ROOT>/medmcqa_merged.jsonl
    MEDMCQA_LIMIT      50
    MEDMCQA_SEED       42  (deterministic shuffle)
    MEDMCQA_CHOICE_TYPE  ""   (filter to "single" or "multi"; "" = both)
"""

from __future__ import annotations

import json
import os
import random
import sys
from pathlib import Path

import pyarrow.parquet as pq

ROOT = Path(os.environ.get("MEDMCQA_ROOT", "/home/nvidia/data/eval-benches/medmcqa"))
SRC = Path(os.environ.get("MEDMCQA_SRC", str(ROOT / "data/validation-00000-of-00001.parquet")))
OUT = Path(os.environ.get("MEDMCQA_OUT", str(ROOT / "medmcqa_merged.jsonl")))
LIMIT = int(os.environ.get("MEDMCQA_LIMIT", "50"))
SEED = int(os.environ.get("MEDMCQA_SEED", "42"))
CHOICE_TYPE_FILTER = os.environ.get("MEDMCQA_CHOICE_TYPE", "").strip().lower()

PROMPT_TEMPLATE = (
    "Question: {question}\n\n"
    "A) {a}\n"
    "B) {b}\n"
    "C) {c}\n"
    "D) {d}\n\n"
    "Choose the correct answer. Reply with only the single letter A, B, C, or D."
)

_COP_TO_LETTER = {0: "A", 1: "B", 2: "C", 3: "D"}


def main() -> int:
    if not SRC.exists():
        raise SystemExit(
            f"MedMCQA source not at {SRC} — run "
            f"`hf download openlifescienceai/medmcqa --repo-type dataset "
            f"--local-dir {ROOT}` first"
        )
    tbl = pq.read_table(SRC)
    rows = tbl.num_rows
    if rows == 0:
        raise SystemExit(f"no rows in {SRC}")

    # Build a list of (src_idx, row_dict) for shuffling. Skip rows that
    # would emit a degenerate prompt (missing option text or cop out of range).
    candidates: list[tuple[int, dict]] = []
    for i in range(rows):
        row = {c: tbl.column(c)[i].as_py() for c in tbl.column_names}
        cop = row.get("cop")
        if cop not in _COP_TO_LETTER:
            continue
        if CHOICE_TYPE_FILTER and (row.get("choice_type") or "").lower() != CHOICE_TYPE_FILTER:
            continue
        if not all(row.get(k) for k in ("question", "opa", "opb", "opc", "opd")):
            continue
        candidates.append((i, row))

    rng = random.Random(SEED)
    rng.shuffle(candidates)
    picks = candidates[:LIMIT]

    OUT.parent.mkdir(parents=True, exist_ok=True)
    rows_out = 0
    letter_hist: dict[str, int] = {"A": 0, "B": 0, "C": 0, "D": 0}
    subject_hist: dict[str, int] = {}
    with OUT.open("w") as fout:
        for src_idx, row in picks:
            letter = _COP_TO_LETTER[row["cop"]]
            text = PROMPT_TEMPLATE.format(
                question=row["question"].strip(),
                a=row["opa"].strip(),
                b=row["opb"].strip(),
                c=row["opc"].strip(),
                d=row["opd"].strip(),
            )
            subject = (row.get("subject_name") or "general").strip().lower().replace(" ", "-")
            fout.write(
                json.dumps(
                    {
                        "id": f"medmcqa-{src_idx}",
                        "text": text,
                        "answer": letter,
                        "task": f"medmcqa-{subject}",
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )
            rows_out += 1
            letter_hist[letter] += 1
            subject_hist[subject] = subject_hist.get(subject, 0) + 1
    top_subjects = sorted(subject_hist.items(), key=lambda kv: -kv[1])[:5]
    print(
        f"wrote {OUT} ({rows_out} rows, "
        f"letter distribution {letter_hist}, seed={SEED}, "
        f"top subjects: {top_subjects})"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
