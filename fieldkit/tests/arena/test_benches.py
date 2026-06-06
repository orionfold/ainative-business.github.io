# Copyright 2026 Manav Sehgal
# SPDX-License-Identifier: Apache-2.0
"""Tests for ``fieldkit.arena.benches`` — the v0.3 eval-prompt surface.

Covers the registry/loader (mtime cache, availability, raw-vs-model prompt),
``bench_for_lane`` slug mapping, the deterministic scorer dispatch (which must
build NO judge), the patent Family-B graceful skip, the judge-backend
selection + degradation, and ``build_model_prompt`` context re-wrapping.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from fieldkit.arena import benches


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n")


@pytest.fixture
def eval_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A minimal eval-benches tree at the canonical relative paths, wired so
    ``benches`` reads it (root override + cache clear)."""
    root = tmp_path / "eval-benches"
    # patent — one row per scorer shape we care about.
    _write_jsonl(
        root / "patent-strategist" / "seed-A.jsonl",
        [{
            "qid": "ps-A-1", "question": "Draft a broadened claim.",
            "family": "A", "use_case": "A1", "scoring_mode": "oracle",
            "gold_label": "A claim reciting X.", "options": [],
            "oracle_context": "Prior art blob.", "rubric": {"claim_type": "independent"},
        }],
    )
    _write_jsonl(
        root / "patent-strategist" / "seed-B.jsonl",
        [{
            "qid": "ps-B-1", "question": "Rank the prior art.",
            "family": "B", "use_case": "B1", "scoring_mode": "closed",
            "gold_label": '["doc-a", "doc-b", "doc-c"]', "options": [],
        }],
    )
    _write_jsonl(
        root / "patent-strategist" / "seed-D-mcq.jsonl",
        [{
            "qid": "ps-D-1", "question": "Which statute governs obviousness?",
            "family": "D", "use_case": "D1", "scoring_mode": "closed",
            "gold_label": "B", "options": ["§101", "§103", "§112", "§102"],
        }],
    )
    _write_jsonl(
        root / "financebench" / "financebench_merged.jsonl",
        [{
            "financebench_id": "fb-1", "question": "What was FY18 capex?",
            "answer": "$1577.00", "question_type": "metrics-generated",
            "evidence": [{"evidence_text": "Capex was 1577."}],
            "company": "ACME", "doc_period": "2018",
        }],
    )
    _write_jsonl(
        root / "legalbench" / "legalbench_merged.jsonl",
        [{"id": "lb-1", "text": "Overruling? ...", "answer": "Yes", "task": "overruling"}],
    )
    _write_jsonl(
        root / "cybermetric" / "cybermetric_merged.jsonl",
        [{"id": "cm-1", "text": "Q ...\nA) a\nB) b\nC) c\nD) d", "answer": "C", "task": "cybermetric"}],
    )
    _write_jsonl(
        root / "medmcqa" / "medmcqa_merged.jsonl",
        [{"id": "mm-1", "text": "Q ...\nA) a\nB) b\nC) c\nD) d", "answer": "B", "task": "medmcqa"}],
    )
    monkeypatch.setattr(benches, "ARENA_EVAL_BENCHES_ROOT", root)
    # AE-11 — astro resolves via its own root override; keep it out of this tree
    # so the published-bench assertions stay deterministic.
    monkeypatch.delenv("FK_ARENA_BENCH_DIR", raising=False)
    monkeypatch.delenv("ARENA_REPO_ROOT", raising=False)
    benches._CACHE.clear()
    yield root
    benches._CACHE.clear()


# --- registry + loader ---------------------------------------------------


def test_list_benches_reports_all_available(eval_root: Path) -> None:
    rows = {b["bench_id"]: b for b in benches.list_benches()}
    published = {
        "patent-strategist", "financebench", "legalbench", "cybermetric", "medmcqa"
    }
    # astro-bench (AE-11) is always registry-listed but resolves via its own root
    # override — absent from this eval-benches tree, so it lists as unavailable.
    assert set(rows) == published | {"astro-bench"}
    assert all(rows[b]["available"] for b in published)
    assert rows["astro-bench"]["available"] is False
    assert rows["patent-strategist"]["count"] == 3
    assert set(rows["medmcqa"]["scorer_kinds"]) == {"mcq_letter"}
    assert "A" in rows["patent-strategist"]["families"]


def test_missing_bench_files_mark_unavailable(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(benches, "ARENA_EVAL_BENCHES_ROOT", tmp_path / "nope")
    benches._CACHE.clear()
    rows = {b["bench_id"]: b for b in benches.list_benches()}
    assert all(not b["available"] for b in rows.values())
    assert benches.load_bench("medmcqa") is None
    assert benches.list_prompts("medmcqa") is None


def test_list_prompts_pagination_and_filters(eval_root: Path) -> None:
    res = benches.list_prompts("patent-strategist", limit=2)
    assert res["total"] == 3 and len(res["prompts"]) == 2
    page2 = benches.list_prompts("patent-strategist", offset=2, limit=2)
    assert len(page2["prompts"]) == 1
    fam = benches.list_prompts("patent-strategist", family="A")
    assert fam["total"] == 1 and fam["prompts"][0]["family"] == "A"
    srch = benches.list_prompts("patent-strategist", q="obviousness")
    assert srch["total"] == 1 and srch["prompts"][0]["qid"] == "ps-D-1"


def test_prompt_payload_marks_context_and_judge(eval_root: Path) -> None:
    a = benches.list_prompts("patent-strategist", family="A")["prompts"][0]
    assert a["scorer_kind"] == "patent_claim_validity"
    assert a["judge_required"] is True
    assert a["has_context"] is True and a["context_kind"] == "oracle"
    d = benches.list_prompts("patent-strategist", family="D-mcq")["prompts"][0]
    assert d["scorer_kind"] == "mcq_letter" and d["judge_required"] is False


def test_mtime_cache_refreshes_on_file_change(eval_root: Path) -> None:
    first = benches.load_bench("legalbench")
    assert len(first.prompts) == 1
    # Append a row + bump mtime → cache should rebuild.
    p = eval_root / "legalbench" / "legalbench_merged.jsonl"
    rows = [json.loads(line) for line in p.read_text().splitlines() if line.strip()]
    rows.append({"id": "lb-2", "text": "Another?", "answer": "No", "task": "overruling"})
    _write_jsonl(p, rows)
    import os as _os
    st = p.stat()
    _os.utime(p, (st.st_atime, st.st_mtime + 5))
    assert len(benches.load_bench("legalbench").prompts) == 2


# --- bench_for_lane ------------------------------------------------------


@pytest.mark.parametrize(
    "lane_id,expected",
    [
        ("local:patent-strategist-v3-nemo-gguf::Q5_K_M", "patent-strategist"),
        ("local:finance-chat-gguf::Q4_K_M", "financebench"),
        ("local:saul-7b-instruct-v1-gguf::Q5_K_M", "legalbench"),
        ("local:securityllm-gguf::Q4_K_M", "cybermetric"),
        ("local:ii-medical-8b-gguf::Q8_0", "medmcqa"),
        ("local:resident", None),
        ("openrouter:anthropic/claude-opus-4.1", None),
        (None, None),
    ],
)
def test_bench_for_lane(lane_id, expected) -> None:
    assert benches.bench_for_lane(lane_id) == expected


# --- deterministic scoring (NO judge) ------------------------------------


def test_deterministic_scorers_build_no_judge(eval_root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def _boom(*a, **k):  # pragma: no cover — must never be called
        raise AssertionError("deterministic scoring must not construct a judge")

    monkeypatch.setattr(benches, "_build_judge", _boom)

    # MCQ correct / wrong.
    ok = benches.score_eval_prediction("medmcqa", "mm-1", "Answer: B")
    assert ok["scored"] and ok["score"] == 1.0 and ok["normalized"] == 1.0
    assert ok["judge_backend"] is None
    bad = benches.score_eval_prediction("medmcqa", "mm-1", "Answer: Z")
    assert bad["scored"] and bad["score"] == 0.0
    # numeric within ±1%.
    fin = benches.score_eval_prediction("financebench", "fb-1", "It was 1577 dollars.")
    assert fin["scored"] and fin["score"] == 1.0 and fin["scorer_kind"] == "numeric_match"
    # exact-match legal.
    leg = benches.score_eval_prediction("legalbench", "lb-1", "yes")
    assert leg["scored"] and leg["score"] == 1.0
    # patent D-mcq deterministic.
    pat = benches.score_eval_prediction("patent-strategist", "ps-D-1", "The answer is B")
    assert pat["scored"] and pat["score"] == 1.0


def test_mcq_strips_think_block(eval_root: Path) -> None:
    res = benches.score_eval_prediction(
        "cybermetric", "cm-1", "<think>maybe A or C, let me reason</think> Answer: C"
    )
    assert res["scored"] and res["score"] == 1.0


def test_patent_family_b_skips_without_judge(eval_root: Path) -> None:
    res = benches.score_eval_prediction("patent-strategist", "ps-B-1", "doc-a, doc-b, doc-c")
    assert res["scored"] is False
    assert res["scorer_kind"] == "prior_art_relevance"
    assert "reconstructable" in res["reason"]


def test_unknown_qid_skips(eval_root: Path) -> None:
    res = benches.score_eval_prediction("medmcqa", "nope", "B")
    assert res["scored"] is False


# --- judge backends ------------------------------------------------------


class _FakeJudge:
    def __init__(self, score: float, rationale: str = "ok") -> None:
        self._score = score
        self._rationale = rationale
        self.calls: list[dict] = []

    def grade(self, **kwargs):
        self.calls.append(kwargs)
        from fieldkit.eval import JudgeResult

        return JudgeResult(score=self._score, rationale=self._rationale, raw="{}")


def test_judge_backed_scoring_uses_built_judge(eval_root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakeJudge(4.0, "well-formed claim")
    captured: dict = {}

    def _fake_build(rubric, *, judge_backend, judge_model, resident):
        captured["backend"] = judge_backend
        captured["resident"] = resident
        return fake

    monkeypatch.setattr(benches, "_build_judge", _fake_build)
    res = benches.score_eval_prediction(
        "patent-strategist", "ps-A-1", "A claim reciting X with tunable Y.",
        judge_backend="local", resident={"base_url": "http://x/v1", "model": "m"},
    )
    assert res["scored"] and res["score"] == 4.0
    assert res["max"] == 5.0 and res["normalized"] == 0.8
    assert res["judge_backend"] == "local"
    assert captured["backend"] == "local"
    # The judge saw the reference + the per-row hints as context.
    assert fake.calls and "Hints:" in (fake.calls[0]["context"] or "")


def test_local_judge_unavailable_skips(eval_root: Path) -> None:
    res = benches.score_eval_prediction(
        "patent-strategist", "ps-A-1", "claim", judge_backend="local", resident=None
    )
    assert res["scored"] is False and "local judge unavailable" in res["reason"]


def test_openrouter_judge_without_key_skips(eval_root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    res = benches.score_eval_prediction(
        "patent-strategist", "ps-A-1", "claim", judge_backend="openrouter", resident=None
    )
    assert res["scored"] is False and "OPENROUTER_API_KEY" in res["reason"]


def test_family_b_falls_back_to_judge_when_backend_given(eval_root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(benches, "_build_judge", lambda *a, **k: _FakeJudge(3.0))
    res = benches.score_eval_prediction(
        "patent-strategist", "ps-B-1", "doc-a, doc-b",
        judge_backend="local", resident={"base_url": "http://x/v1"},
    )
    assert res["scored"] and res["scorer_kind"] == "judge_fallback"


def test_free_prompt_quality_grade(eval_root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(benches, "_build_judge", lambda *a, **k: _FakeJudge(1.0))
    res = benches.score_free_prompt(
        "What is 2+2?", "It is 4.", judge_backend="local", resident={"base_url": "http://x/v1"}
    )
    assert res["scored"] and res["scorer_kind"] == "judge_quality" and res["max"] == 1.0


def test_judge_availability_flags(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    a = benches.judge_availability({"base_url": "http://x/v1", "model": "m"})
    assert a["local_available"] is True and a["openrouter_available"] is False
    assert a["default_backend"] == "local"
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-test")
    b = benches.judge_availability(None)
    assert b["local_available"] is False and b["openrouter_available"] is True
    assert b["default_backend"] == "openrouter"


# --- build_model_prompt --------------------------------------------------


def test_build_model_prompt_unedited_returns_canonical(eval_root: Path) -> None:
    p = benches.load_bench("patent-strategist").by_qid["ps-A-1"]
    assert benches.build_model_prompt(p, p.question) == p.model_prompt
    # canonical patent oracle prompt prepends the context.
    assert "Context:" in p.model_prompt and "Prior art blob." in p.model_prompt


def test_build_model_prompt_edited_rewraps_context(eval_root: Path) -> None:
    p = benches.load_bench("patent-strategist").by_qid["ps-A-1"]
    out = benches.build_model_prompt(p, "My reworded question?")
    assert "Prior art blob." in out and "My reworded question?" in out


def test_build_model_prompt_mcq_appends_options(eval_root: Path) -> None:
    p = benches.load_bench("patent-strategist").by_qid["ps-D-1"]
    out = benches.build_model_prompt(p, "Edited stem?")
    assert "Options:" in out and "B. §103" in out


# --- AE-11 (S6) astro-bench preview ---------------------------------------


@pytest.fixture
def astro_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """An astro-bench split pair under the FK_ARENA_BENCH_DIR override, wired so
    ``benches`` resolves the astro spec there (its root_env)."""
    root = tmp_path / "astro-evidence"
    root.mkdir(parents=True, exist_ok=True)
    _write_jsonl(
        root / "astro-bench-v0.1.jsonl",
        [
            {"task_id": "astro-orb-leo_period-0000", "topic": "orbital_mechanics",
             "subtopic": "leo_period", "tier": 2,
             "prompt": "Compute the orbital period. Give \\boxed{value unit}.",
             "answer": "105.6 min", "gold_value_si": 6336.4, "gold_unit": "s", "rel_tol": 0.02},
            {"task_id": "astro-astro-flux-0001", "topic": "astrophysics",
             "subtopic": "flux", "tier": 1,
             "prompt": "Compute the flux. \\boxed{value unit}.",
             "answer": "3.8e-9 W/m^2", "gold_value_si": 3.8e-9, "gold_unit": "W/m^2", "rel_tol": 0.02},
        ],
    )
    _write_jsonl(
        root / "astro-bench-v0.1.heldout.jsonl",
        [{"task_id": "astro-orb-hohmann-0000", "topic": "orbital_mechanics",
          "subtopic": "hohmann_transfer", "tier": 3,
          "prompt": "Compute the Hohmann delta-v. \\boxed{value unit}.",
          "answer": "3.94 km/s", "gold_value_si": 3940.0, "gold_unit": "m/s", "rel_tol": 0.02}],
    )
    monkeypatch.setenv("FK_ARENA_BENCH_DIR", str(root))
    benches._CACHE.clear()
    yield root
    benches._CACHE.clear()


def test_astro_bench_registered_and_available(astro_root: Path) -> None:
    rows = {b["bench_id"]: b for b in benches.list_benches()}
    a = rows["astro-bench"]
    assert a["available"] is True
    assert a["vertical"] == "astrodynamics"
    assert a["count"] == 3  # 2 pool + 1 held-out
    # the split rides ``family`` so the drawer can filter pool vs held-out
    assert set(a["families"]) == {"pool", "heldout"}
    assert a["scorer_kinds"] == ["astro_numeric_match"]


def test_astro_bench_root_env_override_isolates_from_eval_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # With no FK_ARENA_BENCH_DIR + no ARENA_REPO_ROOT, astro falls back to the
    # eval-benches tree (where its files are absent) → unavailable, not a crash.
    monkeypatch.delenv("FK_ARENA_BENCH_DIR", raising=False)
    monkeypatch.delenv("ARENA_REPO_ROOT", raising=False)
    monkeypatch.setattr(benches, "ARENA_EVAL_BENCHES_ROOT", tmp_path / "nope")
    benches._CACHE.clear()
    rows = {b["bench_id"]: b for b in benches.list_benches()}
    assert rows["astro-bench"]["available"] is False


def test_astro_prompts_carry_tier_subtopic_split(astro_root: Path) -> None:
    res = benches.list_prompts("astro-bench", limit=50)
    assert res["total"] == 3
    by_qid = {p["qid"]: p for p in res["prompts"]}
    p = by_qid["astro-orb-leo_period-0000"]
    assert p["tier"] == 2 and p["subtopic"] == "leo_period" and p["split"] == "pool"
    assert p["scorer_kind"] == "astro_numeric_match" and p["judge_required"] is False
    assert p["reference"] == "105.6 min"  # gold previewed for the numeric bench


def test_astro_split_filter_via_family(astro_root: Path) -> None:
    pool = benches.list_prompts("astro-bench", family="pool")
    held = benches.list_prompts("astro-bench", family="heldout")
    assert pool["total"] == 2 and held["total"] == 1
    assert all(p["split"] == "heldout" for p in held["prompts"])


# --- AF-27(b) — free-prompt → bench-row auto-match -------------------------


def test_find_prompt_by_text_matches_registered_row(astro_root: Path) -> None:
    hit = benches.find_prompt_by_text(
        "Compute the orbital period. Give \\boxed{value unit}."
    )
    assert hit is not None
    bench_id, prompt = hit
    assert bench_id == "astro-bench"
    assert prompt.qid == "astro-orb-leo_period-0000"


def test_find_prompt_by_text_normalizes_whitespace(astro_root: Path) -> None:
    hit = benches.find_prompt_by_text(
        "  Compute the orbital period.   Give \\boxed{value unit}.\n"
    )
    assert hit is not None and hit[1].qid == "astro-orb-leo_period-0000"


def test_find_prompt_by_text_misses_free_text(astro_root: Path) -> None:
    assert benches.find_prompt_by_text("What's the capital of France?") is None
    assert benches.find_prompt_by_text("") is None


def _register_astro_verifier(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A registered eval bench whose meta carries an astro scorer_path verifier
    (the kepler-astro registry shape from the live box)."""
    reg = tmp_path / "bench-registry"
    reg.mkdir(parents=True, exist_ok=True)
    verifier = tmp_path / "verifier.py"
    verifier.write_text(
        "def astro_numeric_match(predicted, expected, **kw):\n"
        "    # toy unit-aware match: pass iff the gold string appears verbatim\n"
        "    return 1.0 if expected.split()[0] in predicted else 0.0\n"
    )
    (reg / "kepler-astro.jsonl").write_text("")
    (reg / "kepler-astro.meta.json").write_text(
        f'{{"scorer_path": "{verifier}:astro_numeric_match"}}'
    )
    monkeypatch.setenv("ARENA_BENCH_DIR", str(reg))
    benches._SCORER_FN_CACHE.clear()
    return reg


def test_astro_scores_via_registered_scorer_path(
    astro_root: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AF-27(b) — with a registered verifier on the box, an astro row scores
    for REAL through the scorer_path loader (the smoke's Compare/chat gold
    verdict), instead of honest-skipping."""
    _register_astro_verifier(tmp_path, monkeypatch)
    good = benches.score_eval_prediction(
        "astro-bench", "astro-orb-leo_period-0000", "The period is \\boxed{105.6 min}."
    )
    assert good["scored"] is True and good["normalized"] == 1.0
    assert good["scorer_kind"] == "astro_numeric_match"
    bad = benches.score_eval_prediction(
        "astro-bench", "astro-orb-leo_period-0000", "The period is \\boxed{210.0 min}."
    )
    assert bad["scored"] is True and bad["normalized"] == 0.0


def test_astro_skips_when_no_verifier_registered(astro_root: Path) -> None:
    # The conftest pins ARENA_BENCH_DIR to an empty tmp registry — no verifier
    # found ⇒ the honest-skip path is unchanged.
    benches._SCORER_FN_CACHE.clear()
    res = benches.score_eval_prediction(
        "astro-bench", "astro-orb-leo_period-0000", "\\boxed{105.6 min}"
    )
    assert res["scored"] is False
    assert "scorer_path verifier" in res["reason"]


def test_rubric_specs_carry_format_scope() -> None:
    # AF-27(a) — every default rubric is a FORMAT check and must say so; the
    # compare banner labels itself from this scope.
    from fieldkit.arena.rubrics import DEFAULT_RUBRIC_REGISTRY, list_rubrics

    assert all(s.scope == "format" for s in DEFAULT_RUBRIC_REGISTRY.values())
    assert all(p["scope"] == "format" for p in list_rubrics())


def test_astro_interactive_score_is_honest_skip(astro_root: Path) -> None:
    # The astro bench is scored by its scorer_path verifier via the eval-job
    # dispatch, not interactive grading — so the interactive path skips with a
    # clear reason (never mis-scores with the unit-blind built-in numeric_match).
    res = benches.score_eval_prediction(
        "astro-bench", "astro-orb-leo_period-0000",
        "The period is \\boxed{105.6 min}",
    )
    assert res["scored"] is False
    assert res["scorer_kind"] == "astro_numeric_match"
    assert "scorer_path" in res["reason"]
    assert res["reference"] == "105.6 min"


def test_astro_bench_for_lane_maps_kepler() -> None:
    assert benches.bench_for_lane("local:kepler-q8-gguf") == "astro-bench"
    assert benches.bench_for_lane("kepler-q8-gguf::Q8_0") == "astro-bench"
