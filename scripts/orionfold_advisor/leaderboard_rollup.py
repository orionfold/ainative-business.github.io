#!/usr/bin/env python3
# Copyright 2026 Manav Sehgal
# SPDX-License-Identifier: Apache-2.0
"""Deterministic rollup: Advisor curveball receipts → leaderboard bench JSON.

Aggregates the per-task strict verdicts already on disk (the launch-session
results files under `evidence/orionfold-advisor/`) into the arena importer's
canonical ``{"models": {label: {core_pass_rate, ...}}}`` shape and writes

    articles/the-refusal-floor-is-trainable/evidence/advisor_contract_results.json

which `fieldkit arena import` picks up as bench group
``the-refusal-floor-is-trainable:advisor_contract``.

Transform-only: no model calls, no re-scoring — every number is a fraction of
``score.strict_passed`` booleans the curveball runs already recorded. The
promoted lane's measured throughput is read from the canonical artifact
manifest (`src/content/artifacts/advisor-gguf.yaml`), not hardcoded. Bench
provenance shas are recomputed from the frozen bench files so the output is
self-verifying against the published Orionfold/Advisor-bench card.
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
EVIDENCE_DIR = REPO_ROOT / "evidence" / "orionfold-advisor"
MANIFEST_PATH = REPO_ROOT / "src" / "content" / "artifacts" / "advisor-gguf.yaml"
OUT_PATH = (
    REPO_ROOT
    / "articles"
    / "the-refusal-floor-is-trainable"
    / "evidence"
    / "advisor_contract_results.json"
)

# Lane keys as they appear in the results filenames → leaderboard labels
# (naming follows the publish receipt's lanes_considered).
LANES = {
    "4bsft2": "4b-sft-v0.2",
    "4bsft": "4b-sft-v0.1",
    "4binit": "4b-init",
    "30b": "30b-prompted",
}
PROMOTED_LANE = "4b-sft-v0.2"

# Filename infix → frozen gate. `advisor-curveball-…` is curveball-v0.1
# (40 tasks); `advisor-curveball2-…` is the pre-registered v0.2 publish gate
# (21 tasks). Lanes are NOT conflated across gates — each (lane, gate) pair
# is its own leaderboard row so a 40-task fraction never averages into a
# 21-task one.
GATES = {
    "advisor-curveball": ("curveball-v0.1", "advisor-curveball-v0.1.jsonl"),
    "advisor-curveball2": ("curveball-v0.2", "advisor-curveball-v0.2.jsonl"),
}

RESULTS_RE = re.compile(
    r"^(advisor-curveball2?)-(4bsft2|4bsft|4binit|30b)-v0\.1\.results\.jsonl$"
)


def _sha12(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:12]


def _promoted_tok_per_sec() -> float | None:
    """Read spark_tokens_per_sec.Q8_0 from the canonical advisor manifest."""
    in_block = False
    for line in MANIFEST_PATH.read_text(encoding="utf-8").splitlines():
        if line.startswith("spark_tokens_per_sec:"):
            in_block = True
            continue
        if in_block:
            m = re.match(r"\s+Q8_0:\s*([0-9.]+)", line)
            if m:
                return float(m.group(1))
            if not line.startswith(" "):
                break
    return None


def rollup() -> dict:
    models: dict[str, dict] = {}
    sources: list[str] = []
    tok_per_sec = _promoted_tok_per_sec()

    for path in sorted(EVIDENCE_DIR.glob("advisor-curveball*-v0.1.results.jsonl")):
        m = RESULTS_RE.match(path.name)
        if not m:
            continue
        gate, lane_key = m.group(1), m.group(2)
        gate_name, _ = GATES[gate]
        lane = LANES[lane_key]
        rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
        if not rows:
            raise SystemExit(f"empty results file: {path}")

        strict = sum(1 for r in rows if r["score"]["strict_passed"])
        refuse_rows = [r for r in rows if r["expected_behavior"] == "refuse"]
        # Published basis (curveball2-compare by_behavior): strict-passed
        # among refuse rows — "3/9" for the 30B, not the looser refusal_ok 5/9.
        refusals_ok = sum(1 for r in refuse_rows if r["score"]["strict_passed"])
        risk = sum(1 for r in rows if r["score"].get("private_state_risk"))

        label = f"{lane}::{gate_name}"
        payload: dict = {
            "core_pass_rate": round(strict / len(rows), 4),
            "strict_passed": strict,
            "tasks": len(rows),
            "refusals_ok": refusals_ok,
            "refusals_total": len(refuse_rows),
            "private_state_risk_rows": risk,
            "source": str(path.relative_to(REPO_ROOT)),
        }
        if lane == PROMOTED_LANE and tok_per_sec is not None:
            payload["tokens_per_sec"] = tok_per_sec
        models[label] = payload
        sources.append(str(path.relative_to(REPO_ROOT)))

    benches = {
        gate_name: {
            "bench_file": f"evidence/orionfold-advisor/{bench_file}",
            "sha12": _sha12(EVIDENCE_DIR / bench_file),
        }
        for gate_name, bench_file in GATES.values()
    }

    return {
        "bench": "advisor_contract",
        "description": (
            "Frozen OOD curveball gates for the Orionfold Advisor packet "
            "contract (answer with exact source-id citations / refuse / "
            "route). core_pass_rate is the fraction of score.strict_passed "
            "per (lane, gate); gates are never conflated. Receipts from the "
            "2026-06 launch sessions; see Orionfold/Advisor-bench and "
            "products/orionfold-advisor/."
        ),
        "scoring": "strict (scored==strict: citation_ok + refusal_ok + route_ok, no alias residue / bare answers / thinking leaks)",
        "promoted_lane": f"{PROMOTED_LANE} (serving lane on :8091, llama.cpp Q8_0)",
        "benches": benches,
        "models": models,
        "sources": sources,
    }


def main() -> int:
    data = rollup()
    expected_labels = {
        f"{lane}::curveball-v0.1" for lane in LANES.values()
    } | {f"{lane}::curveball-v0.2" for lane in ("4b-sft-v0.2", "30b-prompted")}
    got = set(data["models"])
    if got != expected_labels:
        raise SystemExit(f"lane coverage mismatch:\n  missing {expected_labels - got}\n  extra {got - expected_labels}")
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(data, indent=2, sort_keys=False) + "\n", encoding="utf-8")
    for label, payload in sorted(data["models"].items()):
        print(
            f"{label:34s} {payload['strict_passed']:>2}/{payload['tasks']:<2} "
            f"core_pass_rate={payload['core_pass_rate']:.4f} "
            f"refusals {payload['refusals_ok']}/{payload['refusals_total']} "
            f"risk={payload['private_state_risk_rows']}"
        )
    print(f"\nwrote {OUT_PATH.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
