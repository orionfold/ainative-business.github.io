#!/usr/bin/env python3
# Copyright 2026 Manav Sehgal
# SPDX-License-Identifier: Apache-2.0
"""headroom_gate.py — apply the AV-12 / RV-11 RL-headroom decision to a gate run.

Reads the report `preflight_av10.py` wrote when scoring the SFT init on the
transfer candidates, then:

  1. reports aggregate boxed/reward/truncation,
  2. reports the **per-subtopic** SFT pass-rate (the family-level headroom view),
  3. identifies the in-band families (SFT pass-rate in the ``[lo, hi]`` Goldilocks
     band, default 0.30–0.70) — those genuinely have headroom (the init is
     *partially* right, so GRPO has something to climb),
  4. writes the filtered **RL selection held-out** from the candidate rows whose
     subtopic is in-band → ``astro-rl-selection-heldout.jsonl``, and
  5. prints the AV-12 verdict:
       * aggregate ≥ ~0.85  → **SATURATED** → ship SFT (branch 1, AV-11),
       * a real fraction in-band → **HEADROOM** → re-RL on the filtered set (branch 2),
       * aggregate ≤ ~0.15  → **NO SIGNAL** → make the set easier / improve SFT first.

This is inference-only — it consumes the gate's JSON, runs no model.

    python headroom_gate.py                       # default report + candidates
    python headroom_gate.py --report <json> --candidates <jsonl> --lo 0.3 --hi 0.7
"""

from __future__ import annotations

import argparse
import json
import os
from collections import defaultdict

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
_EVID = os.path.join(_REPO, "evidence", "astrodynamics")
_REPORT = os.path.join(_EVID, "av12-headroom-transfer.json")
_CANDS = os.path.join(_EVID, "astro-transfer-candidates.jsonl")
_OUT = os.path.join(_EVID, "astro-rl-selection-heldout.jsonl")


def per_subtopic(rows: list[dict]) -> dict[str, tuple[int, int]]:
    """subtopic -> (n_correct, n_total)."""
    agg: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    for r in rows:
        agg[r["subtopic"]][0] += int(r["score"] >= 1.0)
        agg[r["subtopic"]][1] += 1
    return {k: (v[0], v[1]) for k, v in agg.items()}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--report", default=_REPORT)
    ap.add_argument("--candidates", default=_CANDS)
    ap.add_argument("--out", default=_OUT)
    ap.add_argument("--lo", type=float, default=0.30, help="Goldilocks band lower edge")
    ap.add_argument("--hi", type=float, default=0.70, help="Goldilocks band upper edge")
    ap.add_argument("--ship-floor", type=float, default=0.85,
                    help="aggregate >= this → saturated, ship SFT (AV-11)")
    ap.add_argument("--signal-floor", type=float, default=0.15,
                    help="aggregate <= this → no reward density")
    args = ap.parse_args()

    report = json.load(open(args.report, encoding="utf-8"))
    rows = report["rows"]
    n = len(rows)
    agg_reward = report.get("reward_rate_step0", sum(r["score"] for r in rows) / n)
    boxed = report.get("boxed_rate")
    trunc = report.get("truncation_rate")

    print(f"==== AV-12 RL-headroom gate :: SFT init on {n} transfer candidates ====")
    print(f"model            {report.get('model')}")
    print(f"aggregate reward {agg_reward:.2%}   boxed {boxed:.2%}   trunc {trunc:.2%}")
    print(f"Goldilocks band  [{args.lo:.0%}, {args.hi:.0%}]\n")

    subs = per_subtopic(rows)
    print(f"{'subtopic':<32} {'pass':>7}  {'rate':>6}  band")
    in_band: set[str] = set()
    for st in sorted(subs, key=lambda s: subs[s][0] / subs[s][1]):
        c, t = subs[st]
        rate = c / t
        tag = ""
        if args.lo <= rate <= args.hi:
            tag = "◀ HEADROOM"
            in_band.add(st)
        elif rate < args.lo:
            tag = "(too hard)"
        else:
            tag = "(saturated)"
        print(f"{st:<32} {c:>3}/{t:<3}  {rate:>6.0%}  {tag}")

    # Build the filtered selection held-out from the in-band families.
    cands = [json.loads(line) for line in open(args.candidates, encoding="utf-8")
             if line.strip()]
    selected = [r for r in cands if r["subtopic"] in in_band]
    with open(args.out, "w", encoding="utf-8") as fh:
        for r in selected:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")

    print(f"\nin-band families: {len(in_band)} → {sorted(in_band)}")
    print(f"selection held-out: {len(selected)} rows  →  {args.out}")

    # AV-12 verdict.
    print("\n==== VERDICT ====")
    if agg_reward >= args.ship_floor:
        print(f"SATURATED (agg {agg_reward:.0%} ≥ {args.ship_floor:.0%}) → SHIP SFT (branch 1, AV-11). "
              "Even an error-mined transfer set is aced; the SFT model is the deliverable.")
        verdict = "ship"
    elif agg_reward <= args.signal_floor:
        print(f"NO SIGNAL (agg {agg_reward:.0%} ≤ {args.signal_floor:.0%}) → make easier / improve SFT first. "
              "GRPO would collapse to zero-advantage.")
        verdict = "no_signal"
    elif selected:
        print(f"HEADROOM (agg {agg_reward:.0%} in-band, {len(selected)} in-band rows) → RE-RL viable (branch 2). "
              "The filtered set is the new RL selection held-out.")
        verdict = "headroom"
    else:
        print(f"AGGREGATE in-band ({agg_reward:.0%}) but NO single family landed in [{args.lo:.0%},{args.hi:.0%}] "
              "— families are bimodal (each ~0% or ~100%). Re-mix before re-RL.")
        verdict = "bimodal"
    print(f"verdict={verdict}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
