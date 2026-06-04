#!/usr/bin/env python3
# Copyright 2026 Manav Sehgal
# SPDX-License-Identifier: Apache-2.0
"""generate.py — deterministic astrodynamics bench generator.

Emits the RLVR train/eval pool + a *frozen* held-out split. Every row's gold is
computed at full precision and self-checked through the verifier before write
(a row whose own gold doesn't score 1.0 is a generator bug — we fail loudly).

    python generate.py                       # defaults: 120 pool + 40 held-out
    python generate.py --n 160 --heldout 50 --seed 7 --out-dir /tmp/astro

Held-out gets a DIFFERENT seed (RV-10: no train/held-out leakage) plus a handful
of computed "curveball" variants the templates don't emit — answers requested in
an off-template unit (forces the verifier's unit conversion), and a non-Earth
body. Output: ``astro-bench-v0.1.jsonl`` + ``astro-bench-v0.1.heldout.jsonl``.
"""

from __future__ import annotations

import argparse
import json
import math
import os
from random import Random

import formulas as F
from formulas import Problem
from verifier import astro_numeric_match

VERSION = "v0.1"
REL_TOL = 0.02
_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
_DEFAULT_OUT = os.path.join(_REPO_ROOT, "evidence", "astrodynamics")

_TOPIC_SHORT = {"orbital_mechanics": "orb", "astrophysics": "ap"}


def _row(p: Problem, idx: int, *, hand: bool = False) -> dict:
    tid = f"astro-{_TOPIC_SHORT[p.topic]}-{p.subtopic}-{idx:04d}"
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
        "hand_curated": hand,
        "params": p.params,
    }


def _self_check(p: Problem) -> None:
    """Gold must score 1.0 against itself AND against a \\boxed{gold} prediction."""
    if astro_numeric_match(p.answer, p.answer, rel_tolerance=REL_TOL) != 1.0:
        raise AssertionError(f"gold-vs-gold self-check failed: {p.subtopic} :: {p.answer!r}")
    boxed = f"...working...\\boxed{{{p.answer}}}"
    if astro_numeric_match(boxed, p.answer, rel_tolerance=REL_TOL) != 1.0:
        raise AssertionError(f"boxed self-check failed: {p.subtopic} :: {p.answer!r}")


def generate(n: int, seed: int, exclude: set[str] | None = None) -> list[Problem]:
    """`n` unique problems. `exclude` prompts are treated as already-seen, so the
    result is disjoint from them (RV-10: no train/held-out leakage)."""
    rng = Random(seed)
    plan = F.weighted_plan(n)
    rng.shuffle(plan)
    out: list[Problem] = []
    seen: set[str] = set(exclude or ())
    for fn in plan:
        p = None
        for _ in range(200):                # retry until a fresh prompt
            cand = fn(rng)
            if cand.prompt not in seen:
                p = cand
                break
        if p is None:
            raise RuntimeError(
                f"template {fn.__name__} exhausted its cardinality before {n} unique rows"
            )
        seen.add(p.prompt)
        _self_check(p)
        out.append(p)
    return out


def curveballs(seed: int) -> list[Problem]:
    """A few computed off-template held-out items (unit conversion + non-Earth body)."""
    rng = Random(seed)
    items: list[Problem] = []

    # 1. LEO period asked in HOURS (templates ask minutes) — forces unit conversion.
    h = rng.randrange(400, 1500, 10)
    r = (F.R_EARTH / 1e3 + h) * 1e3
    T = 2 * math.pi * math.sqrt(r ** 3 / F.MU_EARTH)
    items.append(Problem(
        "leo_period_hours", "orbital_mechanics", 2,
        f"A satellite orbits at altitude h = {h:,} km (R = {F._sci(F.R_EARTH)} m, "
        f"μ = {F._sci(F.MU_EARTH)} m³/s²). Report the orbital period in HOURS. {F.PROMPT_TAIL}",
        F._g(T / 3600.0, "hr"), T, "s", {"h_km": h}))

    # 2. Mars circular orbit — non-Earth μ supplied in-prompt.
    mu_mars = 4.283e13
    r_km = rng.randrange(4000, 12000, 100)
    v = math.sqrt(mu_mars / (r_km * 1e3))
    items.append(Problem(
        "mars_circular_velocity", "orbital_mechanics", 1,
        f"A probe is in a circular orbit of radius r = {r_km:,} km about Mars "
        f"(μ_Mars = {F._sci(mu_mars)} m³/s²). Compute the circular speed in km/s. {F.PROMPT_TAIL}",
        F._g(v / 1e3, "km/s"), v, "m/s", {"r_km": r_km}))

    # 3. Schwarzschild radius asked in METERS for a stellar-mass BH.
    m_solar = rng.choice([3, 7, 15])
    M = m_solar * F.M_SUN
    rs = 2 * F.G * M / F.C ** 2
    items.append(Problem(
        "schwarzschild_meters", "astrophysics", 2,
        f"A black hole of mass M = {m_solar} M_⊙ (M_⊙ = {F._sci(F.M_SUN)} kg, "
        f"G = {F._sci(F.G)} m³ kg⁻¹ s⁻², c = {F._sci(F.C)} m/s). Compute the "
        f"Schwarzschild radius r_s = 2GM/c² in METERS. {F.PROMPT_TAIL}",
        F._g(rs, "m"), rs, "m", {"m_solar": m_solar}))

    # 4. Hubble distance asked in km/s/Mpc inverse but answered in pc (cross-scale).
    v_rec = rng.randrange(500, 5000, 50)
    d_mpc = v_rec / F.H0
    d_pc = d_mpc * 1e6
    items.append(Problem(
        "hubble_in_pc", "astrophysics", 2,
        f"A nearby galaxy recedes at v = {v_rec:,} km/s (H₀ = {F.H0:g} km/s/Mpc). "
        f"Give its distance in PARSECS (not Mpc). {F.PROMPT_TAIL}",
        F._g(d_pc, "pc"), d_pc * 3.0856775815e16, "m", {"v_kms": v_rec}))

    for p in items:
        _self_check(p)
    return items


def write_jsonl(path: str, problems: list[Problem], *, start: int = 0, hand: bool = False) -> int:
    with open(path, "w", encoding="utf-8") as fh:
        for i, p in enumerate(problems):
            fh.write(json.dumps(_row(p, start + i, hand=hand), ensure_ascii=False) + "\n")
    return len(problems)


def _summarize(problems: list[Problem]) -> str:
    topics: dict[str, int] = {}
    tiers: dict[int, int] = {}
    subs: dict[str, int] = {}
    for p in problems:
        topics[p.topic] = topics.get(p.topic, 0) + 1
        tiers[p.tier] = tiers.get(p.tier, 0) + 1
        subs[p.subtopic] = subs.get(p.subtopic, 0) + 1
    n = len(problems)
    orb = topics.get("orbital_mechanics", 0)
    ap = topics.get("astrophysics", 0)
    lines = [
        f"  rows={n}  orbital={orb} ({100*orb//max(n,1)}%)  astrophysics={ap} ({100*ap//max(n,1)}%)",
        "  tiers: " + "  ".join(f"T{t}={tiers.get(t,0)}" for t in sorted(tiers)),
        f"  subtopics: {len(subs)}",
    ]
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--n", type=int, default=120, help="train/eval pool size (floor 100)")
    ap.add_argument("--heldout", type=int, default=40, help="held-out size (before curveballs)")
    ap.add_argument("--seed", type=int, default=20260604, help="pool seed")
    ap.add_argument("--out-dir", default=_DEFAULT_OUT)
    args = ap.parse_args()

    if args.n < 100:
        raise SystemExit("RV-10: bench floor is 100 rows; pass --n >= 100")

    os.makedirs(args.out_dir, exist_ok=True)
    pool = generate(args.n, args.seed)
    pool_prompts = {p.prompt for p in pool}
    held_gen = generate(args.heldout, args.seed + 99991, exclude=pool_prompts)
    held_hand = curveballs(args.seed + 7)
    held = held_gen + held_hand

    pool_path = os.path.join(args.out_dir, f"astro-bench-{VERSION}.jsonl")
    held_path = os.path.join(args.out_dir, f"astro-bench-{VERSION}.heldout.jsonl")
    np = write_jsonl(pool_path, pool)
    with open(held_path, "w", encoding="utf-8") as fh:
        for i, p in enumerate(held_gen):
            fh.write(json.dumps(_row(p, 10000 + i, hand=False), ensure_ascii=False) + "\n")
        for i, p in enumerate(held_hand):
            fh.write(json.dumps(_row(p, 20000 + i, hand=True), ensure_ascii=False) + "\n")
    nh = len(held)

    print(f"[astro-bench {VERSION}] wrote {np} pool rows  →  {pool_path}")
    print(_summarize(pool))
    print(f"[astro-bench {VERSION}] wrote {nh} held-out rows ({len(held_hand)} hand-curated curveballs)  →  {held_path}")
    print(_summarize(held))
    print(f"  self-check: every gold scored 1.0 through the verifier (rel_tol={REL_TOL})")


if __name__ == "__main__":
    main()
