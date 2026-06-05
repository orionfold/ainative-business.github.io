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
from loader import (  # noqa: E402
    DEFAULT_HELDOUT,
    DEFAULT_POOL,
    AstroBench,
    astro_reward,
    load_bench,
    load_heldout,
    load_tasks,
    make_rollout,
)
from smoke_rl import _InversionSampler, run_inversion_smoke  # noqa: E402
from verifier import astro_numeric_match, extract_boxed  # noqa: E402

from fieldkit.reward import RewardAdapter  # noqa: E402
from fieldkit.rl import GRPOConfig, RLLoop, RLLoopError  # noqa: E402


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


# ---- AF-9 live preflight summary -----------------------------------------

def _row(bucket, score, boxed):
    return {"task_id": "t", "subtopic": "x", "tier": 1, "answer": "1",
            "score": score, "bucket": bucket, "boxed": boxed,
            "n_chars": 10, "wall_s": 1.0}


def test_preflight_summarize_running_shell():
    # AF-9: an empty results list paints a clean 0/total running shell.
    from preflight_av10 import summarize
    s = summarize([], model="Qwen/Qwen3-8B", n_target=8,
                  max_new_tokens=8192, rel_tol=0.02, status="running")
    assert s["status"] == "running"
    assert s["scored"] == 0 and s["total"] == 8
    assert s["rows"] == []
    assert s["boxed_rate"] == 0.0 and s["truncation_rate"] == 0.0


def test_preflight_summarize_partial_rates():
    # AF-9: running rates are computed over the rows scored so far.
    from preflight_av10 import summarize
    rows = [_row("correct", 1.0, "4.35"), _row("truncated_think", 0.0, "")]
    s = summarize(rows, model="m", n_target=8, max_new_tokens=8192,
                  rel_tol=0.02, status="running")
    assert s["scored"] == 2 and s["total"] == 8
    assert s["boxed_rate"] == 0.5 and s["truncation_rate"] == 0.5
    assert s["buckets"]["correct"] == 1 and s["buckets"]["truncated_think"] == 1


def test_preflight_summarize_done_gate():
    # AF-9: the final write is status:"done"; the gate is boxed>0 ∧ trunc<50%.
    from preflight_av10 import summarize
    clean = summarize([_row("correct", 1.0, "4.35"), _row("boxed_wrong", 0.0, "x")],
                      model="m", n_target=2, max_new_tokens=8192, rel_tol=0.02,
                      status="done")
    assert clean["status"] == "done"
    assert clean["gate_pass"] is True  # boxed_rate 1.0 > 0, truncation 0 < 0.5
    held = summarize([_row("truncated_think", 0.0, "")] * 2, model="m", n_target=2,
                     max_new_tokens=4096, rel_tol=0.02, status="done")
    assert held["gate_pass"] is False  # truncation 1.0 → av_r1 not clear


def test_fewshot_exemplars_terse_distinct_deterministic():
    # AV-10 conditioning probe: exemplars are terse, distinct-subtopic, ordered
    # shortest-first, and deterministic (no RNG) — held-out-disjoint by RV-10.
    from preflight_av10 import _CORPUS, build_fewshot_content, load_fewshot, summarize
    ex = load_fewshot(_CORPUS, 3)
    assert len(ex) == 3
    assert len({e["subtopic"] for e in ex}) == 3
    lens = [len(e["completion"]) for e in ex]
    assert lens == sorted(lens)  # shortest-first
    assert [e["task_id"] for e in load_fewshot(_CORPUS, 3)] == [e["task_id"] for e in ex]
    content = build_fewshot_content(ex, "SOLVE THIS Q")
    assert content.rstrip().endswith("SOLVE THIS Q")
    assert content.count("### Example") == 3
    assert r"\boxed{value unit}" in content
    # the fewshot count rides the report for provenance + dropdown disambiguation
    assert summarize([], model="m", n_target=8, max_new_tokens=8192,
                     rel_tol=0.02, status="running", fewshot=3)["fewshot"] == 3


# ---- C3: loader glue + RewardAdapter wrap --------------------------------

def test_loader_parses_pool_rows():
    tasks = load_tasks(DEFAULT_POOL)
    assert len(tasks) == 120
    t = tasks[0]
    # question ← prompt, expected ← answer (the RV-2 field mapping)
    assert t.question and "\\boxed" in t.question
    assert t.expected and t.expected == tasks[0].expected
    assert t.rel_tol == 0.02
    # every task exposes the (.question/.expected) contract the GPU sampler reads
    assert all(q.question and q.expected for q in tasks)


def test_astro_bench_from_jsonl_exposes_questions():
    bench = load_bench(DEFAULT_POOL)
    assert isinstance(bench, AstroBench)
    assert len(bench) == 120
    assert hasattr(bench, "questions") and len(bench.questions) == 120


def test_loader_heldout_disjoint_from_pool():
    pool_ids = {t.task_id for t in load_bench(DEFAULT_POOL).questions}
    heldout_ids = {t.task_id for t in load_heldout(DEFAULT_HELDOUT).questions}
    assert len(heldout_ids) == 44
    assert pool_ids.isdisjoint(heldout_ids)  # RV-10 frozen-split disjointness


def test_make_rollout_maps_prediction_and_expected():
    task = load_bench(DEFAULT_POOL).questions[0]
    roll = make_rollout(task, "some model text")
    assert roll.prediction == "some model text"
    assert roll.expected == task.expected
    assert roll.task_id == task.task_id


def test_astro_reward_grades_correct_and_wrong():
    reward = astro_reward()
    assert isinstance(reward, RewardAdapter)
    task = load_bench(DEFAULT_POOL).questions[0]
    correct = make_rollout(task, f"<think>x</think>\\boxed{{{task.expected}}}")
    wrong = make_rollout(task, "<think>x</think>\\boxed{0}")
    assert reward.score(correct).success is True
    assert reward.score(correct).scalar == 1.0
    assert reward.score(wrong).success is False
    assert reward.score(wrong).scalar == 0.0


def test_astro_reward_forwards_rel_tolerance():
    # gold "7.53 km/s": +0.9% passes the default 2% band, +3.6% fails.
    from loader import AstroTask

    t = AstroTask(task_id="x", question="q", expected="7.53 km/s", topic="", subtopic="", tier=1)
    assert astro_reward().score(make_rollout(t, "\\boxed{7.6 km/s}")).success is True  # +0.9%
    assert astro_reward().score(make_rollout(t, "\\boxed{7.8 km/s}")).success is False  # +3.6%
    # a tighter adapter (forwarding rel_tolerance=0.005) rejects the +0.9% miss
    assert astro_reward(rel_tolerance=0.005).score(make_rollout(t, "\\boxed{7.6 km/s}")).success is False


# ---- C3: ≤2-step RLLoop with fake seams — held-out-only selection (RV-4) ---

def test_smoke_selects_on_heldout_not_pool():
    loop = run_inversion_smoke()
    # pool climbs (best = last step); held-out peaks early (best = step 0).
    pool_best = max(loop.pool_scores, key=lambda s: loop.pool_scores[s])
    assert loop.pool_scores[0] < loop.pool_scores[1]  # the overfitting trajectory
    assert loop.heldout_scores[0] > loop.heldout_scores[1]  # the inversion
    assert pool_best == 1
    assert loop.selected_step == 0  # RV-4: selection ignores the pool-best step
    assert loop.selected_step != pool_best
    assert loop.summary()["selected_on"] == "heldout"
    assert loop.selected_heldout_score == 0.90


def test_smoke_reward_path_is_real():
    # The fake sampler emits genuine \boxed{} strings the real reward grades:
    # at frac=1.0 every rollout is correct → pool score 1.0 (not a stubbed number).
    loop = run_inversion_smoke(pool_fracs=(1.0, 1.0), heldout_traj={0: 0.5, 1: 0.5})
    assert loop.pool_scores[0] == 1.0
    # a degenerate all-correct group yields zero advantage — no spurious gradient.
    sampler = _InversionSampler([0.0])
    groups = sampler(load_bench(DEFAULT_POOL).questions[:2], 4)
    rewards = astro_reward().score_group(groups[0])
    assert all(r.scalar == 0.0 for r in rewards)  # frac 0.0 → all wrong


def test_loop_refuses_subfloor_corpus():
    # RV-10: the ≥100-row floor. A 42-row bench is rejected before step 0.
    tiny = AstroBench(load_bench(DEFAULT_POOL).questions[:42])
    loop = RLLoop(
        config=GRPOConfig(base="Qwen/Qwen3-8B", max_steps=1, heldout_every=1),
        reward=astro_reward(),
        bench=tiny,
        sampler=_InversionSampler([1.0]),
        trainer=lambda r, a, s: {},
        heldout_eval=lambda s, t: 1.0,
    )
    try:
        loop.run()
    except RLLoopError as exc:
        assert "corpus_min" in str(exc)
    else:
        raise AssertionError("RLLoop accepted a 42-row corpus below the RV-10 floor")


# ---- transfer set (AV-12 / RV-11 RL-headroom gate) ------------------------

def test_transfer_gold_self_verifies():
    import transfer as TX
    rng = __import__("random").Random(3)
    for fn, _ in TX.TRANSFER_TEMPLATES:
        for _ in range(5):
            p = fn(rng)
            assert astro_numeric_match(p.answer, p.answer, rel_tolerance=REL_TOL) == 1.0, p.subtopic
            assert astro_numeric_match(
                f"\\boxed{{{p.answer}}}", p.answer, rel_tolerance=REL_TOL
            ) == 1.0, p.subtopic


def test_transfer_generator_deterministic():
    from gen_transfer import generate as gtx
    a = gtx(48, 20260605, set())
    b = gtx(48, 20260605, set())
    assert [p.prompt for p in a] == [p.prompt for p in b]


def test_transfer_disjoint_from_existing():
    # AV-R6: the selection set must be separate from pool + generalization
    # held-out + SFT corpus (no leakage either direction).
    from gen_transfer import _existing_prompts
    from gen_transfer import generate as gtx
    existing = _existing_prompts()
    cands = {p.prompt for p in gtx(48, 20260605, existing)}
    assert cands.isdisjoint(existing), "transfer candidates overlap pool/heldout/SFT"


def test_transfer_subtopics_are_namespaced():
    # xfer_* names can never collide with the original bench/corpus subtopics.
    import transfer as TX
    rng = __import__("random").Random(1)
    for fn, _ in TX.TRANSFER_TEMPLATES:
        assert fn(rng).subtopic.startswith("xfer_")


def test_transfer_error_mines_weak_spots():
    # AV-R6: weighted HEAVY toward the C6 measured weak spots.
    from gen_transfer import generate as gtx
    cands = gtx(48, 20260605, set())
    subs = [p.subtopic for p in cands]
    hohmann = sum(1 for s in subs if "hohmann" in s)
    altitude = sum(1 for s in subs if "altitude_from_period" in s)
    assert hohmann >= 8, f"too few hohmann error-mine rows: {hohmann}"
    assert altitude >= 5, f"too few altitude_from_period error-mine rows: {altitude}"


def test_transfer_hyperbolic_is_unbound():
    # mild extrapolation e>1: v_inf must be real and positive (v > escape speed).
    import transfer as TX
    rng = __import__("random").Random(7)
    for _ in range(20):
        p = TX.xfer_hyperbolic_excess(rng)
        assert p.gold_value_si > 0.0, "hyperbolic excess speed must be positive (e>1)"


def test_transfer_new_bodies_present():
    # transfer shift: non-Earth central bodies appear in the prompts.
    from gen_transfer import generate as gtx
    cands = gtx(48, 20260605, set())
    bodies = sum(1 for p in cands if any(b in p.prompt for b in ("Mars", "Moon", "Jupiter")))
    assert bodies >= 10, f"too few new-body transfer rows: {bodies}"


def test_headroom_per_subtopic_and_band():
    from headroom_gate import per_subtopic
    rows = (
        [{"subtopic": "a", "score": 1.0}] * 5          # saturated 100%
        + [{"subtopic": "b", "score": 0.0}] * 5        # too hard 0%
        + [{"subtopic": "c", "score": 1.0}] * 2 + [{"subtopic": "c", "score": 0.0}] * 2  # 50% in-band
    )
    subs = per_subtopic(rows)
    assert subs["a"] == (5, 5)
    assert subs["b"] == (0, 5)
    assert subs["c"] == (2, 4)
    # the anti-degenerate-advantage criterion: keep families strictly in (0,1).
    partial = {k for k, (c, t) in subs.items() if 0 < c < t}
    assert partial == {"c"}, "only partial-competence families have RL headroom"


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
