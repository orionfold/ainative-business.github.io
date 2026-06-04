# Copyright 2026 Manav Sehgal
# SPDX-License-Identifier: Apache-2.0
"""test_astro_bench.py — real tests for the astrodynamics bench generator + verifier.

Run:  /tmp/fk/bin/python -m pytest scripts/astro_bench/test_astro_bench.py -q
  or:  python scripts/astro_bench/test_astro_bench.py   (standalone runner)

No mocks — the verifier is the reward, so it gets graded against real strings,
and every generated row's gold is round-tripped through it.
"""

from __future__ import annotations

import math
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

import formulas as F  # noqa: E402
import units as U  # noqa: E402
from generate import REL_TOL, curveballs, generate  # noqa: E402
from verifier import astro_numeric_match, extract_boxed  # noqa: E402


# ---- units ----------------------------------------------------------------

def test_parse_basic():
    assert U.parse_quantity("5310 s") == (5310.0, "s")
    assert U.parse_quantity("88.5 min") == (88.5, "min")
    assert U.parse_quantity("7.53 km/s") == (7.53, "km/s")
    assert U.parse_quantity("-28.4 MJ/kg") == (-28.4, "mj/kg")
    assert U.parse_quantity("1,234 km") == (1234.0, "km")


def test_parse_scientific_and_latex():
    assert U.parse_quantity("3.5e3 W")[0] == 3500.0
    v, u = U.parse_quantity("1.2 × 10^3 pc")
    assert abs(v - 1200.0) < 1e-9 and u == "pc"
    v, u = U.parse_quantity(r"4.4 \times 10^{5} W")
    assert abs(v - 4.4e5) < 1 and u == "w"


def test_to_si_dimensions():
    assert U.to_si(1.0, "km")[0] == 1000.0
    assert U.to_si(1.0, "hr")[0] == 3600.0
    assert U.same_dimension("min", "hr")
    assert not U.same_dimension("s", "km")


# ---- verifier -------------------------------------------------------------

def test_unit_conversion_pass():
    # gold seconds, model answered minutes — must convert and pass.
    assert astro_numeric_match("\\boxed{88.5 min}", "5310 s", rel_tolerance=REL_TOL) == 1.0


def test_bare_number_assumes_gold_unit():
    assert astro_numeric_match("\\boxed{7.53}", "7.53 km/s") == 1.0
    assert astro_numeric_match("\\boxed{7.8}", "7.53 km/s") == 0.0  # +3.6%, >2% off


def test_dimension_mismatch_fails():
    # gold is a period (time); model answered a speed — hard miss.
    assert astro_numeric_match("\\boxed{7.5 km/s}", "5310 s") == 0.0


def test_tolerance_edges():
    assert astro_numeric_match("\\boxed{102 m}", "100 m", rel_tolerance=0.02) == 1.0   # +2%
    assert astro_numeric_match("\\boxed{103 m}", "100 m", rel_tolerance=0.02) == 0.0   # +3%


def test_boxed_takes_last():
    txt = "first I guessed \\boxed{1 m} then corrected to \\boxed{500 km}"
    assert astro_numeric_match(txt, "500 km") == 1.0


def test_final_answer_fallback():
    assert astro_numeric_match("Final answer: 1.5 Mpc", "1.5 Mpc") == 1.0


def test_negative_answer():
    assert astro_numeric_match("\\boxed{-28.4 MJ/kg}", "-28.4 MJ/kg") == 1.0
    assert astro_numeric_match("\\boxed{28.4 MJ/kg}", "-28.4 MJ/kg") == 0.0  # sign matters


def test_no_answer_scores_zero():
    assert astro_numeric_match("I cannot solve this.", "5310 s") == 0.0


def test_extract_boxed_brace_matching():
    assert extract_boxed("a \\boxed{x=\\frac{1}{2} m} b") == "x=\\frac{1}{2} m"


# ---- generator ------------------------------------------------------------

def test_generator_determinism():
    a = generate(120, 42)
    b = generate(120, 42)
    assert [p.prompt for p in a] == [p.prompt for p in b]
    assert [p.answer for p in a] == [p.answer for p in b]


def test_every_gold_self_verifies():
    # the load-bearing check: each row's gold scores 1.0 through the verifier.
    for p in generate(120, 7) + curveballs(7):
        assert astro_numeric_match(p.answer, p.answer, rel_tolerance=REL_TOL) == 1.0, p.subtopic
        assert astro_numeric_match(f"\\boxed{{{p.answer}}}", p.answer, rel_tolerance=REL_TOL) == 1.0, p.subtopic


def test_domain_mix_70_30():
    rows = generate(200, 1)
    orb = sum(1 for p in rows if p.topic == "orbital_mechanics")
    frac = orb / len(rows)
    assert 0.62 <= frac <= 0.78, f"orbital fraction {frac:.2f} outside 70/30 band"


def test_floor_enforced():
    # generate() itself doesn't enforce; the CLI does. Sanity: ≥100 yields ≥100.
    assert len(generate(100, 3)) == 100


def test_heldout_disjoint_from_pool():
    # RV-10: no train/held-out prompt leakage — the CLI passes the pool as `exclude`.
    pool = {p.prompt for p in generate(120, 20260604)}
    held = {p.prompt for p in generate(40, 20260604 + 99991, exclude=pool)}
    assert pool.isdisjoint(held), "held-out shares prompts with the pool (leakage!)"


def test_no_dupes_within_pool():
    rows = generate(160, 5)
    prompts = [p.prompt for p in rows]
    assert len(prompts) == len(set(prompts)), "duplicate prompts within the pool"


def test_tier_spread_present():
    tiers = {p.tier for p in generate(150, 9)}
    assert tiers == {1, 2, 3}, f"missing difficulty tiers: {tiers}"


def test_wrong_computation_is_caught():
    # a plausible-but-wrong solver (forgot the 2π in Kepler) should mostly miss.
    rng_problems = [F.kepler3_period(__import__("random").Random(i)) for i in range(10)]
    misses = 0
    for p in rng_problems:
        a = p.params["a_km"] * 1e3
        wrong = math.sqrt(a ** 3 / F.MU_EARTH) / 3600.0   # dropped 2π
        if astro_numeric_match(f"\\boxed{{{wrong:.4g} hr}}", p.answer) == 0.0:
            misses += 1
    assert misses >= 9, f"verifier too loose: only {misses}/10 wrong answers rejected"


# ---- C1 SFT corpus (build + gate) -----------------------------------------

import build_sft_corpus as B  # noqa: E402
from verify_sft import check_row  # noqa: E402


def _queue_rows(n=64, seed=4242):
    """A held-out-disjoint worklist, mirroring sft_queue.py."""
    import json
    heldout = os.path.join(
        os.path.dirname(__file__), "..", "..", "evidence", "astrodynamics",
        "astro-bench-v0.1.heldout.jsonl",
    )
    excl = set()
    if os.path.exists(heldout):
        with open(heldout, encoding="utf-8") as fh:
            excl = {json.loads(line)["prompt"] for line in fh if line.strip()}
    problems = generate(n, seed, exclude=excl)
    rows = []
    for i, p in enumerate(problems):
        rows.append({
            "task_id": f"astro-sft-{i:04d}", "topic": p.topic, "subtopic": p.subtopic,
            "tier": p.tier, "prompt": p.prompt, "answer": p.answer,
            "gold_value_si": p.gold_value_si, "gold_unit": p.gold_unit, "params": p.params,
        })
    return rows, excl


def test_build_every_row_clears_the_gate():
    queue_rows, _ = _queue_rows()
    queue = {q["task_id"]: q for q in queue_rows}
    for i, q in enumerate(queue_rows):
        row = B.build_row(q, i)
        errs = check_row(row, queue)
        assert not errs, f"{q['subtopic']}: {errs}"


def test_build_covers_all_16_subtopics():
    # the dispatch must have a template for every formula family the generator emits.
    queue_rows, _ = _queue_rows(n=200)
    seen = {q["subtopic"] for q in queue_rows}
    missing = seen - set(B._DISPATCH)
    assert not missing, f"no template for: {missing}"


def test_built_completion_is_a_real_chain_with_boxed():
    queue_rows, _ = _queue_rows(n=16)
    q = queue_rows[0]
    row = B.build_row(q, 0)
    c = row["completion"]
    assert "<think>" in c and "</think>" in c
    assert extract_boxed(c) is not None
    chain = c[c.index("<think>") + 7 : c.index("</think>")].strip()
    assert len(chain) >= 40 and not chain.startswith("<think>")


def test_gate_rejects_corrupted_box():
    # the gate must reject a row whose boxed answer is wrong (corpus poison).
    queue_rows, _ = _queue_rows(n=8)
    q = queue_rows[0]
    queue = {q["task_id"]: q}
    row = B.build_row(q, 0)
    row["completion"] = row["completion"].rsplit("\\boxed{", 1)[0] + "\\boxed{999999 km}"
    assert check_row(row, queue), "gate accepted a wrong boxed answer"


def test_gate_rejects_empty_think():
    queue_rows, _ = _queue_rows(n=8)
    q = queue_rows[0]
    queue = {q["task_id"]: q}
    row = B.build_row(q, 0)
    row["completion"] = "<think>\n \n</think>\n\n\\boxed{" + q["answer"] + "}"
    assert any("empty <think>" in e for e in check_row(row, queue))


def test_queue_disjoint_from_heldout():
    queue_rows, excl = _queue_rows(n=128)
    if not excl:
        return  # held-out split absent in this checkout; nothing to assert
    qprompts = {q["prompt"] for q in queue_rows}
    assert qprompts.isdisjoint(excl), "RV-10: worklist overlaps held-out"


def _run_standalone() -> int:
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failed = 0
    for fn in fns:
        try:
            fn()
            print(f"  PASS  {fn.__name__}")
        except Exception as exc:  # noqa: BLE001
            failed += 1
            print(f"  FAIL  {fn.__name__}: {type(exc).__name__}: {exc}")
    print(f"\n{len(fns) - failed}/{len(fns)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(_run_standalone())
