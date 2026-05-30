#!/usr/bin/env python3
# Copyright 2026 Manav Sehgal
# SPDX-License-Identifier: Apache-2.0
"""Merge a CyberMetric subset into one JSONL for VerticalBench.

CyberMetric (`tihanyin/CyberMetric`, arxiv 2402.07688, Apache-2.0) is a
4-option MCQ cybersecurity benchmark with balanced answer distribution
(20/20/20/20 across A/B/C/D in the 80-row release). The 80-question
release is the right scale for a per-quant-variant Spark sweep — same
order of magnitude as the 50-row FinanceBench / LegalBench mini-evals
used for `Orionfold/finance-chat-GGUF` and `Orionfold/Saul-7B-Instruct-v1-GGUF`.

This script samples N rows from CyberMetric-80 (default 50) into one
JSONL the v0.4.1 `VerticalBench.from_jsonl(..., format="legalbench")`
loader consumes. Schema matches `legalbench_merge.py`:

    text     formatted MCQ prompt with the 4 options laid out + instruction
             to reply with only one letter (A/B/C/D)
    answer   the gold solution letter
    task     "cybermetric" (single-task — CyberMetric is a unified bench,
             unlike LegalBench's 162 task folders)
    id       cybermetric-<source_index>

Scoring runs at `g3_measure_variants.py` time via the local `mcq_letter`
scorer (regex-extract `[A-D]` from response, case-insensitive). Letter
gold + an mcq_letter scorer is more robust than full-text gold + `contains`
because CyberMetric answers are long technical sentences models tend to
paraphrase — letter matching survives paraphrasing.

Env knobs:
    CYBERBENCH_ROOT       /home/nvidia/data/eval-benches/cybermetric
    CYBERBENCH_SRC        CyberMetric-80-v1.json (sibling of ROOT)
    CYBERBENCH_OUT        <ROOT>/cybermetric_merged.jsonl
    CYBERBENCH_LIMIT      50
    CYBERBENCH_SEED       42  (deterministic shuffle for reproducibility)
"""

from __future__ import annotations

import json
import os
import random
import sys
from pathlib import Path

ROOT = Path(os.environ.get("CYBERBENCH_ROOT", "/home/nvidia/data/eval-benches/cybermetric"))
SRC = Path(os.environ.get("CYBERBENCH_SRC", str(ROOT / "CyberMetric-80-v1.json")))
OUT = Path(os.environ.get("CYBERBENCH_OUT", str(ROOT / "cybermetric_merged.jsonl")))
LIMIT = int(os.environ.get("CYBERBENCH_LIMIT", "50"))
SEED = int(os.environ.get("CYBERBENCH_SEED", "42"))

PROMPT_TEMPLATE = (
    "Question: {question}\n\n"
    "A) {a}\n"
    "B) {b}\n"
    "C) {c}\n"
    "D) {d}\n\n"
    "Choose the correct answer. Reply with only the single letter A, B, C, or D."
)


def main() -> int:
    if not SRC.exists():
        raise SystemExit(
            f"CyberMetric source not at {SRC} — run "
            f"`curl -sLo {SRC} https://huggingface.co/datasets/tihanyin/CyberMetric/"
            f"resolve/main/CyberMetric-80-v1.json` first"
        )
    payload = json.loads(SRC.read_text())
    questions = payload.get("questions") or []
    if not questions:
        raise SystemExit(f"no questions[] array in {SRC}")

    # Deterministic shuffle so reruns produce the same eval set.
    rng = random.Random(SEED)
    indexed = list(enumerate(questions))
    rng.shuffle(indexed)
    picks = indexed[:LIMIT]

    OUT.parent.mkdir(parents=True, exist_ok=True)
    rows_out = 0
    letter_hist: dict[str, int] = {"A": 0, "B": 0, "C": 0, "D": 0}
    with OUT.open("w") as fout:
        for src_idx, q in picks:
            ans = q.get("answers") or {}
            sol = (q.get("solution") or "").strip().upper()
            if sol not in ("A", "B", "C", "D"):
                continue
            if not all(k in ans for k in ("A", "B", "C", "D")):
                continue
            text = PROMPT_TEMPLATE.format(
                question=q.get("question", "").strip(),
                a=ans["A"].strip(),
                b=ans["B"].strip(),
                c=ans["C"].strip(),
                d=ans["D"].strip(),
            )
            fout.write(
                json.dumps(
                    {
                        "id": f"cybermetric-{src_idx}",
                        "text": text,
                        "answer": sol,
                        "task": "cybermetric",
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )
            rows_out += 1
            letter_hist[sol] += 1
    print(
        f"wrote {OUT} ({rows_out} rows, "
        f"letter distribution {letter_hist}, seed={SEED})"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
