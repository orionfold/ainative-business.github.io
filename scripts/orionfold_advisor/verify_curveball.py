#!/usr/bin/env python3
# Copyright 2026 Manav Sehgal
# SPDX-License-Identifier: Apache-2.0
"""Deterministic verification gate for the Advisor external-curveball bench.

The curveball bench (`advisor-curveball-v0.1.jsonl`) is session-authored OOD
eval data — no template machinery, no teacher model. Before any lane is scored
on it, this gate proves each row is honestly scoreable (the 0082 lesson:
verify groundability deterministically before freezing a bench):

1. schema + unique task ids + behavior/scoring-flag consistency
2. answer/route rows: every gold source_id exists in the corpus manifest
3. retrieval: gold is inside the packet actually shown to the model
   (BM25 top-5, 900-char excerpts — the serving preflight configuration)
4. groundability: each row's `answer_terms` appear in the gold block's
   title+label+excerpt as the model sees it
5. ambiguity probe: warn when a non-gold retrieved block also carries all
   answer_terms (citation credit could defensibly go elsewhere)
6. dedup: question text never collides with the frozen bench (103 rows) or
   the SFT training corpus (777 rows)

Exit code is non-zero on any hard failure (checks 1-4, 6); ambiguity is a
reported warning for bench-author review.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

from preflight import build_packets  # type: ignore
from score_recall import EVIDENCE_DIR, MANIFEST_PATH, _read_jsonl  # type: ignore

CURVEBALL_PATH = EVIDENCE_DIR / "advisor-curveball-v0.1.jsonl"
BENCH_PATHS = (
    EVIDENCE_DIR / "advisor-bench-v0.1.jsonl",
    EVIDENCE_DIR / "advisor-bench-v0.1.heldout.jsonl",
)
SFT_CORPUS_PATH = Path(
    "/home/nvidia/data/aifn-train-lora/advisor-4b-sft/corpus/advisor-sft-corpus-v0.1.jsonl"
)
REQUIRED_FIELDS = (
    "task_id",
    "version",
    "split",
    "family",
    "expected_behavior",
    "question",
    "expected_answer",
    "source_ids",
    "scoring",
)


def _norm_question(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().lower())


def main() -> int:
    rows = _read_jsonl(CURVEBALL_PATH)
    manifest_ids = {row["source_id"] for row in _read_jsonl(MANIFEST_PATH)}
    errors: list[str] = []
    warnings: list[str] = []

    # 1. schema
    seen_ids: set[str] = set()
    for row in rows:
        task_id = row.get("task_id", "<missing>")
        for field in REQUIRED_FIELDS:
            if field not in row:
                errors.append(f"{task_id}: missing field {field}")
        if task_id in seen_ids:
            errors.append(f"{task_id}: duplicate task id")
        seen_ids.add(task_id)
        behavior = row.get("expected_behavior")
        if behavior not in ("answer", "route", "refuse"):
            errors.append(f"{task_id}: bad expected_behavior {behavior!r}")
        scoring = row.get("scoring") or {}
        if behavior == "refuse":
            if row.get("source_ids") or not scoring.get("refusal_required"):
                errors.append(f"{task_id}: refuse row must have empty source_ids + refusal_required")
        else:
            if not row.get("source_ids") or not scoring.get("citation_required"):
                errors.append(f"{task_id}: {behavior} row needs source_ids + citation_required")
        if behavior == "route" and not scoring.get("route_required"):
            errors.append(f"{task_id}: route row missing route_required")
        if behavior != "refuse" and not row.get("answer_terms") and behavior == "answer":
            errors.append(f"{task_id}: answer row missing answer_terms")

    # 2. gold ids exist
    for row in rows:
        for source_id in row.get("source_ids") or []:
            if source_id not in manifest_ids:
                errors.append(f"{row['task_id']}: gold {source_id} not in manifest")

    # 3-5. retrieval, groundability, ambiguity — on the packets the model will see
    packets = build_packets(
        task_ids=[],
        top_k=5,
        max_sources=5,
        excerpt_chars=900,
        reasoning_mode="off",
        bench_path=CURVEBALL_PATH,
        select_all=True,
        evaluator_hint=False,
    )
    by_task = {row["task_id"]: row for row in rows}
    retrieval_hits = 0
    answerable = 0
    for packet in packets:
        row = by_task[packet["task_id"]]
        if row["expected_behavior"] == "refuse":
            continue
        answerable += 1
        retrieved = {block["source_id"]: block for block in packet["retrieved_sources"]}
        missing = [sid for sid in row["source_ids"] if sid not in retrieved]
        if missing:
            ranks = list(retrieved)
            errors.append(
                f"{row['task_id']}: gold {missing} not retrieved@5; got {ranks}"
            )
            continue
        retrieval_hits += 1
        terms = [t.lower() for t in row.get("answer_terms") or []]
        for sid in row["source_ids"]:
            block = retrieved[sid]
            visible = " ".join(
                str(block.get(k) or "") for k in ("title", "citation_label", "excerpt")
            ).lower()
            for term in terms:
                if term not in visible:
                    errors.append(
                        f"{row['task_id']}: answer term {term!r} not visible in gold "
                        f"block {sid} (title+label+excerpt)"
                    )
        if terms:
            for sid, block in retrieved.items():
                if sid in row["source_ids"]:
                    continue
                visible = " ".join(
                    str(block.get(k) or "") for k in ("title", "citation_label", "excerpt")
                ).lower()
                if all(term in visible for term in terms):
                    warnings.append(
                        f"{row['task_id']}: non-gold retrieved block {sid} also carries "
                        f"all answer terms (ambiguity risk)"
                    )

    # 6. dedup
    other_questions: set[str] = set()
    for path in BENCH_PATHS:
        for row in _read_jsonl(path):
            other_questions.add(_norm_question(row["question"]))
    corpus_note = "checked"
    if SFT_CORPUS_PATH.exists():
        with SFT_CORPUS_PATH.open(encoding="utf-8") as fh:
            for line in fh:
                if line.strip():
                    corpus_row = json.loads(line)
                    question = corpus_row.get("question")
                    if question:
                        other_questions.add(_norm_question(str(question)))
    else:
        corpus_note = f"SKIPPED (missing {SFT_CORPUS_PATH})"
        warnings.append(f"sft corpus dedup skipped: {SFT_CORPUS_PATH} not found")
    for row in rows:
        if _norm_question(row["question"]) in other_questions:
            errors.append(f"{row['task_id']}: question collides with bench/SFT corpus")

    behaviors = {b: sum(1 for r in rows if r["expected_behavior"] == b) for b in ("answer", "route", "refuse")}
    print(f"rows={len(rows)} behaviors={behaviors} refusal_share={behaviors['refuse']/len(rows):.3f}")
    print(f"retrieval: gold@5 {retrieval_hits}/{answerable} answerable rows; sft-corpus dedup {corpus_note}")
    for warning in warnings:
        print(f"WARN {warning}")
    for error in errors:
        print(f"FAIL {error}")
    print("VERDICT:", "PASS" if not errors else f"FAIL ({len(errors)} errors)")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
