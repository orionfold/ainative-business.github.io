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
    benches._CACHE.clear()
    yield root
    benches._CACHE.clear()


# --- registry + loader ---------------------------------------------------


def test_list_benches_reports_all_available(eval_root: Path) -> None:
    rows = {b["bench_id"]: b for b in benches.list_benches()}
    assert set(rows) == {
        "patent-strategist", "financebench", "legalbench", "cybermetric", "medmcqa"
    }
    assert all(b["available"] for b in rows.values())
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
