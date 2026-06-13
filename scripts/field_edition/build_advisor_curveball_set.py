#!/usr/bin/env python3
# Copyright 2026 Manav Sehgal
# SPDX-License-Identifier: Apache-2.0
"""Vendor the frozen Advisor curveball-v0.2 gate into the shipped Field Edition package.

The §8 Advisor gate (`fieldkit field-edition verify`) scores the resident
Advisor lane against the frozen **curveball-v0.2** out-of-distribution bench
(floor: curveball ≥80%, refusals 9/9). For that gate to run on a fresh install
with no repo checkout, the *scored prompt packets* must ride the wheel — that is
what this script produces:

    fieldkit/src/fieldkit/field_edition/data/advisor-curveball-mini.json

**Why freeze the packets, not regenerate them?** Unlike the recall set (a
deterministic projection of gold source ids), each curveball packet carries the
**retrieved context baked into its `user` message**. That context comes from a
BM25 pass over the public corpus manifest — which *grows every time an article
ships*, so `preflight.build_packets` is NOT reproducible run-to-run. To stay
honest, the gate must ship the **exact packets that produced the published
85.7%** (curveball-v0.2, Q4_K_M, reasoning off, no evaluator hint — the
production-shaped run preserved at
``evidence/orionfold-advisor/advisor-curveball-v0.2-q4km.prompts.jsonl``). This
script projects that frozen prompts file down to the fields the gate's scorer
needs; the input prompts' sha is recorded for provenance, and the output file's
own sha is what `fieldkit.field_edition.advisor.CURVEBALL_SET_SHA` pins. Drift
from that sha means the shipped gate was edited out-of-band.

Re-pin only after a deliberate re-score: serve the new Advisor revision, re-run
``scripts/orionfold_advisor/preflight.py --bench
evidence/orionfold-advisor/advisor-curveball-v0.2.jsonl --all-rows
--no-evaluator-hint --reasoning-mode off --endpoint http://127.0.0.1:8091``,
commit the fresh ``*-q4km.prompts.jsonl``, then re-run this builder and update
``CURVEBALL_SET_SHA``.

Usage:

    python3 scripts/field_edition/build_advisor_curveball_set.py          # write + print sha
    python3 scripts/field_edition/build_advisor_curveball_set.py --check   # verify, no write
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
EVIDENCE_DIR = REPO_ROOT / "evidence" / "orionfold-advisor"
#: The frozen, scored prompt packets behind the published 85.7% (Q4_K_M) run.
PROMPTS_PATH = EVIDENCE_DIR / "advisor-curveball-v0.2-q4km.prompts.jsonl"
OUT_PATH = (
    REPO_ROOT
    / "fieldkit"
    / "src"
    / "fieldkit"
    / "field_edition"
    / "data"
    / "advisor-curveball-mini.json"
)

NAME = "advisor-curveball-mini"
VERSION = "v0.2"
#: The §8 published Advisor floors (kept in lockstep with verify.ADVISOR_*).
CURVEBALL_FLOOR = 0.80
#: Generation controls the gate replays so the served lane matches the frozen run.
REASONING_MODE = "off"  # /no_think baked into the system message + enable_thinking=False
MAX_TOKENS = 700
TEMPERATURE = 0.0


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _project(row: dict[str, Any]) -> dict[str, Any]:
    """Down to exactly what the §8 Advisor scorer needs.

    Keeps the baked ``messages`` (the request the lane replays), the behavioral
    expectations, and the citation targets. Drops ``expected_answer`` /
    ``answer_terms`` / ``retrieved_sources`` (the structured form is redundant
    with the context already baked into the user message) and ``question`` (it
    lives inside ``messages``)."""
    return {
        "task_id": str(row["task_id"]),
        "family": str(row["family"]),
        "split": str(row["split"]),
        "expected_behavior": str(row["expected_behavior"]),
        "expected_source_ids": [str(s) for s in (row.get("expected_source_ids") or [])],
        "accepted_source_ids": [str(s) for s in (row.get("accepted_source_ids") or [])],
        "messages": [
            {"role": str(m["role"]), "content": str(m["content"])}
            for m in row["messages"]
        ],
    }


def build() -> dict[str, Any]:
    rows = _read_jsonl(PROMPTS_PATH)
    projected = sorted((_project(r) for r in rows), key=lambda r: r["task_id"])
    by_behavior: dict[str, int] = {}
    for r in projected:
        by_behavior[r["expected_behavior"]] = by_behavior.get(r["expected_behavior"], 0) + 1
    prompts_sha = hashlib.sha256(PROMPTS_PATH.read_bytes()).hexdigest()[:12]
    return {
        "name": NAME,
        "version": VERSION,
        "source_prompts": PROMPTS_PATH.relative_to(REPO_ROOT).as_posix(),
        "source_prompts_sha256_12": prompts_sha,
        "curveball_floor": CURVEBALL_FLOOR,
        "refusals_total": by_behavior.get("refuse", 0),
        "reasoning_mode": REASONING_MODE,
        "max_tokens": MAX_TOKENS,
        "temperature": TEMPERATURE,
        "row_count": len(projected),
        "behavior_counts": dict(sorted(by_behavior.items())),
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
            raise SystemExit(f"missing vendored curveball set: {args.out}")
        current = args.out.read_bytes()
        cur_sha = hashlib.sha256(current).hexdigest()[:12]
        if current != payload:
            raise SystemExit(
                f"DRIFT: {args.out} sha {cur_sha} != rebuilt {sha} "
                f"(frozen prompts changed? re-run without --check, then re-pin CURVEBALL_SET_SHA)"
            )
        print(f"ok: {args.out.name} matches the frozen prompts (sha {sha})")
        return

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_bytes(payload)
    print(
        f"wrote {args.out} ({doc['row_count']} rows: {doc['behavior_counts']}, "
        f"refusals_total={doc['refusals_total']})"
    )
    print(f"source prompts sha12: {doc['source_prompts_sha256_12']}")
    print(f"curveball-set sha12 (pin this as CURVEBALL_SET_SHA): {sha}")


if __name__ == "__main__":
    main()
