#!/usr/bin/env python3
# Copyright 2026 Manav Sehgal
# SPDX-License-Identifier: Apache-2.0
"""sft_queue.py — deterministic worklist for the C1 SFT-init corpus synth.

Emits N unique problems (prompt + gold) the session model then writes worked
`<think>…</think>\\boxed{}` solutions for. The queue is DISJOINT from the frozen
held-out split (RV-10 / AV-4: held-out prompts MUST be excluded so the SFT-init
never memorizes an eval prompt). Pool-bench overlap is allowed — SFT and RLVR
train on the same problem distribution; only the held-out eval is protected.

Deterministic transform only (`feedback_llm_skill_pattern`): no model calls, no
`anthropic`/SDK. The session model does the writing; this script only plans.

    python sft_queue.py --n 600                  # full live worklist
    python sft_queue.py --n 5 --seed 1 \\
        --out evidence/astrodynamics/astro-sft-queue.dry.jsonl   # dry run
"""

from __future__ import annotations

import argparse
import json
import os

import generate as G
from formulas import Problem

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
_DEFAULT_DIR = os.path.join(_REPO_ROOT, "evidence", "astrodynamics")
_HELDOUT = os.path.join(_DEFAULT_DIR, "astro-bench-v0.1.heldout.jsonl")


def _heldout_prompts(path: str) -> set[str]:
    if not os.path.exists(path):
        raise SystemExit(f"held-out split not found: {path} (run generate.py first)")
    prompts: set[str] = set()
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                prompts.add(json.loads(line)["prompt"])
    return prompts


def _queue_row(p: Problem, idx: int) -> dict:
    """The worklist row — gold travels with it so the verifier needs no recompute."""
    return {
        "task_id": f"astro-sft-{idx:04d}",
        "topic": p.topic,
        "subtopic": p.subtopic,
        "tier": p.tier,
        "prompt": p.prompt,
        "answer": p.answer,          # the gold the written \boxed{} must match (±2%)
        "gold_value_si": p.gold_value_si,
        "gold_unit": p.gold_unit,
        "params": p.params,
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--n", type=int, default=600, help="worklist size (full live run ≈600)")
    ap.add_argument("--seed", type=int, default=20260605, help="queue seed (≠ pool/held-out seeds)")
    ap.add_argument("--heldout", default=_HELDOUT)
    ap.add_argument("--out", default=os.path.join(_DEFAULT_DIR, "astro-sft-queue.jsonl"))
    args = ap.parse_args()

    excl = _heldout_prompts(args.heldout)
    problems = G.generate(args.n, args.seed, exclude=excl)   # self-checks every gold
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as fh:
        for i, p in enumerate(problems):
            fh.write(json.dumps(_queue_row(p, i), ensure_ascii=False) + "\n")

    # provenance: confirm disjointness from held-out (RV-10)
    qprompts = {p.prompt for p in problems}
    assert qprompts.isdisjoint(excl), "RV-10 VIOLATION: queue overlaps held-out"
    print(f"[sft-queue] wrote {len(problems)} rows → {args.out}")
    print(f"[sft-queue] disjoint from {len(excl)} held-out prompts ✓")
    print(G._summarize(problems))


if __name__ == "__main__":
    main()
