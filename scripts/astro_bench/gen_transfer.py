#!/usr/bin/env python3
# Copyright 2026 Manav Sehgal
# SPDX-License-Identifier: Apache-2.0
"""gen_transfer.py — emit the Tier-1 transfer CANDIDATE set for the RL-headroom gate.

This set is scored once on the SFT init (`preflight_av10.py --model <merged-hf>`)
to settle the C6 ship-vs-redesign fork (AV-12 / RV-11). Rows that the SFT scores
in the ~30–70% Goldilocks band become the RL **selection held-out**; if the init
still saturates ≥85%, the SFT model is the deliverable (ship it, AV-11).

Disjointness (AV-R6 — the selection set must be separate from everything else):
the candidate prompts are excluded against the **pool**, the **generalization
held-out**, AND the **SFT corpus** prompts, so there is zero leakage in either
direction. Every gold self-verifies through the verifier before write.

    python gen_transfer.py                       # default: 48 candidates, seed below
    python gen_transfer.py --n 60 --seed 11

Output: evidence/astrodynamics/astro-transfer-candidates.jsonl
"""

from __future__ import annotations

import argparse
import json
import os
from random import Random

import transfer as T
from formulas import Problem
from verifier import astro_numeric_match

VERSION = "v0.1"
REL_TOL = 0.02
_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
_EVID = os.path.join(_REPO_ROOT, "evidence", "astrodynamics")
_POOL = os.path.join(_EVID, "astro-bench-v0.1.jsonl")
_HELDOUT = os.path.join(_EVID, "astro-bench-v0.1.heldout.jsonl")
_SFT = os.path.join(_EVID, "astro-sft-corpus.jsonl")
_OUT = os.path.join(_EVID, "astro-transfer-candidates.jsonl")

_TOPIC_SHORT = {"orbital_mechanics": "orb", "astrophysics": "ap"}


def _existing_prompts() -> set[str]:
    seen: set[str] = set()
    for path in (_POOL, _HELDOUT, _SFT):
        if not os.path.exists(path):
            continue
        for line in open(path, encoding="utf-8"):
            line = line.strip()
            if line:
                seen.add(json.loads(line)["prompt"])
    return seen


def _self_check(p: Problem) -> None:
    if astro_numeric_match(p.answer, p.answer, rel_tolerance=REL_TOL) != 1.0:
        raise AssertionError(f"gold-vs-gold self-check failed: {p.subtopic} :: {p.answer!r}")
    boxed = f"...working...\\boxed{{{p.answer}}}"
    if astro_numeric_match(boxed, p.answer, rel_tolerance=REL_TOL) != 1.0:
        raise AssertionError(f"boxed self-check failed: {p.subtopic} :: {p.answer!r}")


def _row(p: Problem, idx: int) -> dict:
    tid = f"astro-xfer-{_TOPIC_SHORT[p.topic]}-{p.subtopic}-{idx:04d}"
    return {
        "task_id": tid,
        "topic": p.topic,
        "subtopic": p.subtopic,
        "tier": p.tier,
        "prompt": p.prompt,
        "answer": p.answer,
        "gold_value_si": p.gold_value_si,
        "gold_unit": p.gold_unit,
        "rel_tol": REL_TOL,
        "transfer": True,
        "params": p.params,
    }


def generate(n: int, seed: int, exclude: set[str]) -> list[Problem]:
    rng = Random(seed)
    plan = T.weighted_plan(n)
    rng.shuffle(plan)
    out: list[Problem] = []
    seen: set[str] = set(exclude)
    for fn in plan:
        p = None
        for _ in range(300):
            cand = fn(rng)
            if cand.prompt not in seen:
                p = cand
                break
        if p is None:
            raise RuntimeError(f"template {fn.__name__} exhausted cardinality before {n} rows")
        seen.add(p.prompt)
        _self_check(p)
        out.append(p)
    return out


def _summarize(problems: list[Problem]) -> str:
    subs: dict[str, int] = {}
    topics: dict[str, int] = {}
    for p in problems:
        subs[p.subtopic] = subs.get(p.subtopic, 0) + 1
        topics[p.topic] = topics.get(p.topic, 0) + 1
    n = len(problems)
    orb = topics.get("orbital_mechanics", 0)
    ap = topics.get("astrophysics", 0)
    lines = [f"  rows={n}  orbital={orb} ({100*orb//max(n,1)}%)  astrophysics={ap} ({100*ap//max(n,1)}%)"]
    for st in sorted(subs):
        lines.append(f"    {st:<32} {subs[st]}")
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--n", type=int, default=48, help="candidate count")
    ap.add_argument("--seed", type=int, default=20260605)
    ap.add_argument("--out", default=_OUT)
    args = ap.parse_args()

    exclude = _existing_prompts()
    print(f"[transfer] excluding {len(exclude)} existing prompts (pool+heldout+SFT)")
    cands = generate(args.n, args.seed, exclude)

    with open(args.out, "w", encoding="utf-8") as fh:
        for i, p in enumerate(cands):
            fh.write(json.dumps(_row(p, i), ensure_ascii=False) + "\n")

    print(f"[transfer {VERSION}] wrote {len(cands)} candidate rows  →  {args.out}")
    print(_summarize(cands))
    print(f"  self-check: every gold scored 1.0 through the verifier (rel_tol={REL_TOL})")


if __name__ == "__main__":
    main()
