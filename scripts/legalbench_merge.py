#!/usr/bin/env python3
# Copyright 2026 Manav Sehgal
# SPDX-License-Identifier: Apache-2.0
"""Merge a curated subset of nguha/legalbench into one JSONL for VerticalBench.

LegalBench ships 162 task folders under `data/<task>/test.tsv`. The full corpus
is too large for a per-quant-variant Spark sweep; this script samples 10 rows
from each of 5 representative tasks (50 rows total — same scale as the
FinanceBench mini-eval used for `Orionfold/finance-chat-GGUF`) and emits one
JSONL the v0.4.1 `VerticalBench.from_jsonl(..., format="legalbench")` loader
consumes directly. Each row carries:

    text     formatted prompt = task-instruction with `{{text}}` substituted
    answer   the gold label from the task's `answer_space`
    task     the LegalBench task name (for tag-aware reporting)
    id       <task>-<index>

Tasks were picked for breadth across legal domains (case law, statutory, NDA,
trademark, federal jurisdiction). All five use `contained_in_output` as the
eval_method, so a single `fieldkit.eval.contains` scorer covers the set.

Env knobs:
    LEGALBENCH_ROOT       /home/nvidia/data/eval-benches/legalbench
    LEGALBENCH_OUT        /home/nvidia/data/eval-benches/legalbench/legalbench_merged.jsonl
    LEGALBENCH_TASKS      comma-separated task names (default: 5 picks below)
    LEGALBENCH_N_PER_TASK 10
"""

from __future__ import annotations

import csv
import json
import os
import sys
from pathlib import Path

DEFAULT_TASKS = (
    "overruling",
    "abercrombie",
    "proa",
    "contract_nli_confidentiality_of_agreement",
    "diversity_1",
)

ROOT = Path(os.environ.get("LEGALBENCH_ROOT", "/home/nvidia/data/eval-benches/legalbench"))
OUT = Path(os.environ.get("LEGALBENCH_OUT", str(ROOT / "legalbench_merged.jsonl")))
TASKS = tuple(s.strip() for s in os.environ.get("LEGALBENCH_TASKS", ",".join(DEFAULT_TASKS)).split(",") if s.strip())
N_PER_TASK = int(os.environ.get("LEGALBENCH_N_PER_TASK", "10"))


def _load_instruction(task: str, meta: dict) -> str:
    entry = meta.get(task)
    if not entry or "instruction" not in entry:
        raise SystemExit(f"task_metadata.json has no instruction for task {task!r}")
    return entry["instruction"]


def _row_text_field(task: str, instruction: str, row: dict) -> str:
    text = row.get("text") or ""
    return instruction.replace("{{text}}", text)


def main() -> int:
    if not ROOT.exists():
        raise SystemExit(f"LegalBench not at {ROOT} — run `hf download nguha/legalbench --repo-type=dataset` first")
    meta_path = ROOT / "task_metadata.json"
    meta = json.loads(meta_path.read_text())

    OUT.parent.mkdir(parents=True, exist_ok=True)
    rows_out = 0
    with OUT.open("w") as fout:
        for task in TASKS:
            tsv_path = ROOT / "data" / task / "test.tsv"
            if not tsv_path.exists():
                print(f"  [warn] {task}: {tsv_path} not present — skipping", flush=True)
                continue
            instruction = _load_instruction(task, meta)
            with tsv_path.open() as fin:
                reader = csv.DictReader(fin, delimiter="\t")
                kept = 0
                for i, row in enumerate(reader):
                    if kept >= N_PER_TASK:
                        break
                    text_field = _row_text_field(task, instruction, row)
                    answer = (row.get("answer") or "").strip()
                    if not text_field.strip() or not answer:
                        continue
                    fout.write(json.dumps({
                        "id": f"{task}-{row.get('index', i)}",
                        "text": text_field,
                        "answer": answer,
                        "task": task,
                    }, ensure_ascii=False) + "\n")
                    kept += 1
                    rows_out += 1
                print(f"  [{task}] kept {kept}/{N_PER_TASK}", flush=True)
    print(f"wrote {OUT} ({rows_out} rows from {len(TASKS)} tasks)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
