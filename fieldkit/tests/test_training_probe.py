# Copyright 2026 Manav Sehgal
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for `fieldkit.training.probe`.

Pure-python — no torch, no transformers, no peft. The default
`ReasoningProbe.run()` generator is bypassed via a ``generator=`` test
seam that records the questions and returns scripted responses, so the
real model load path is only exercised by the runtime ImportError
fallback path (which we *don't* hit on a working install — the run()
test always passes a generator).

Surfaces under test:

- `parse_think` — empty / single / multi block / longest-pair behavior.
- `summarize_rows` — presence rate over all rows, length over has_think
  rows, empty input zeros.
- `ProbeQuestion` / `ProbeRow` — frozen dataclass construction.
- `ProbeReport` — overall / by_category aggregation, with_budget
  exclusion, to_json / from_json round-trip.
- `ProbeReport.compare` — same-budget direct, diff-budget normalize-
  exclude semantics, custom thresholds, label overrides, skip on zero
  baseline.
- `ReasoningProbe.from_jsonl` — well-formed + malformed inputs.
- `ReasoningProbe.run` — fake generator path, on_progress callback,
  metadata round-trip.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from fieldkit.training import (
    DEFAULT_COMPARE_THRESHOLDS,
    CompareResult,
    CompareRow,
    CompareThresholds,
    ProbeError,
    ProbeQuestion,
    ProbeReport,
    ProbeRow,
    ProbeSummary,
    ReasoningProbe,
    THINK_REGEX,
    parse_think,
    summarize_rows,
)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _row(
    qid: str = "q1",
    category: str = "general-reasoning",
    *,
    has_think: bool = True,
    think_n_tok: int | None = 100,
    think_text: str = "thinking...",
    response: str = "<think>thinking...</think>answer",
    wall_seconds: float = 0.0,
) -> ProbeRow:
    return ProbeRow(
        qid=qid,
        category=category,
        response=response,
        has_think=has_think,
        think_n_tok=think_n_tok,
        think_text=think_text,
        wall_seconds=wall_seconds,
    )


def _report(rows: list[ProbeRow], *, max_new_tokens: int = 1024, model: str = "m") -> ProbeReport:
    return ProbeReport(model=model, rows=rows, max_new_tokens=max_new_tokens)


# ---------------------------------------------------------------------------
# parse_think
# ---------------------------------------------------------------------------


def test_parse_think_no_block() -> None:
    has, n, text = parse_think("just a flat answer with no think tags")
    assert has is False
    assert n is None
    assert text == ""


def test_parse_think_single_block() -> None:
    has, n, text = parse_think("<think>aaaa bbbb cccc dddd</think>final")
    assert has is True
    assert n is not None and n >= 1
    assert "aaaa" in text


def test_parse_think_empty_block_is_marked_present_but_zero() -> None:
    """R1 false-start: empty `<think></think>` is a present-but-empty block."""
    has, n, text = parse_think("<think></think>direct answer")
    assert has is True
    assert n == 0
    assert text == ""


def test_parse_think_picks_longest_of_multiple() -> None:
    """Empty `<think></think>` followed by a real `<think>...</think>` —
    the regex finds both and `parse_think` must pick the longer one."""
    resp = "<think></think>first<think>this is the real chain</think>answer"
    has, n, text = parse_think(resp)
    assert has is True
    assert n is not None and n >= 1
    assert "real chain" in text


def test_parse_think_multiline_block() -> None:
    """DOTALL — `\\n` inside the block must not terminate the match."""
    resp = "<think>line1\nline2\nline3</think>"
    has, _n, text = parse_think(resp)
    assert has is True
    assert "line1" in text and "line3" in text


def test_think_regex_exported() -> None:
    """THINK_REGEX is exposed for callers that re-parse cached responses."""
    assert THINK_REGEX.search("<think>x</think>") is not None
    assert THINK_REGEX.search("no block here") is None


# ---------------------------------------------------------------------------
# summarize_rows
# ---------------------------------------------------------------------------


def test_summarize_rows_empty() -> None:
    s = summarize_rows([])
    assert s.n == 0
    assert s.think_presence_rate == 0.0
    assert s.think_token_length == 0.0


def test_summarize_rows_all_think() -> None:
    rows = [_row(qid=f"q{i}", think_n_tok=100 * i) for i in range(1, 5)]
    s = summarize_rows(rows)
    assert s.n == 4
    assert s.think_presence_rate == 1.0
    # mean of 100, 200, 300, 400 = 250
    assert s.think_token_length == 250.0


def test_summarize_rows_mixed_presence() -> None:
    rows = [
        _row(qid="q1", has_think=True, think_n_tok=200),
        _row(qid="q2", has_think=False, think_n_tok=None, think_text=""),
        _row(qid="q3", has_think=True, think_n_tok=400),
        _row(qid="q4", has_think=False, think_n_tok=None, think_text=""),
    ]
    s = summarize_rows(rows)
    assert s.n == 4
    assert s.think_presence_rate == 0.5
    # mean of present-rows: (200+400)/2 = 300
    assert s.think_token_length == 300.0


def test_summarize_rows_no_present_means_zero_length() -> None:
    rows = [_row(qid="q1", has_think=False, think_n_tok=None, think_text="")]
    s = summarize_rows(rows)
    assert s.n == 1
    assert s.think_presence_rate == 0.0
    assert s.think_token_length == 0.0


# ---------------------------------------------------------------------------
# ProbeQuestion / ProbeRow construction (frozen)
# ---------------------------------------------------------------------------


def test_probe_question_frozen() -> None:
    q = ProbeQuestion(qid="a", category="b", question="c")
    assert q.qid == "a"
    with pytest.raises(Exception):
        q.qid = "z"  # type: ignore[misc]


def test_probe_question_metadata_default_is_empty() -> None:
    q = ProbeQuestion(qid="a", category="b", question="c")
    assert dict(q.metadata) == {}


def test_probe_row_frozen() -> None:
    r = _row()
    with pytest.raises(Exception):
        r.has_think = False  # type: ignore[misc]


# ---------------------------------------------------------------------------
# ProbeReport — construction / properties
# ---------------------------------------------------------------------------


def test_probe_report_rejects_zero_budget() -> None:
    with pytest.raises(ProbeError):
        ProbeReport(model="m", rows=[_row()], max_new_tokens=0)


def test_probe_report_rejects_negative_budget() -> None:
    with pytest.raises(ProbeError):
        ProbeReport(model="m", rows=[_row()], max_new_tokens=-1)


def test_probe_report_overall_and_by_category() -> None:
    rows = [
        _row(qid="q1", category="general-reasoning", has_think=True, think_n_tok=100),
        _row(qid="q2", category="general-reasoning", has_think=False, think_n_tok=None, think_text=""),
        _row(qid="q3", category="patent-irac", has_think=True, think_n_tok=300),
    ]
    rep = _report(rows)
    assert rep.n == 3
    overall = rep.overall
    assert overall.n == 3
    assert overall.think_presence_rate == round(2 / 3, 4)  # 0.6667
    # length-mean is over has_think rows: (100+300)/2 = 200
    assert overall.think_token_length == 200.0

    by_cat = rep.by_category
    assert set(by_cat) == {"general-reasoning", "patent-irac"}
    assert by_cat["general-reasoning"].n == 2
    assert by_cat["general-reasoning"].think_presence_rate == 0.5
    assert by_cat["patent-irac"].n == 1
    assert by_cat["patent-irac"].think_presence_rate == 1.0


def test_probe_report_repr_includes_key_fields() -> None:
    rep = ProbeReport(
        model="deepseek/x",
        rows=[_row()],
        max_new_tokens=1024,
        lora_path="/runs/ckpt-200",
        step=200,
    )
    s = repr(rep)
    assert "deepseek/x" in s
    assert "/runs/ckpt-200" in s
    assert "step=200" in s
    assert "n=1" in s


# ---------------------------------------------------------------------------
# ProbeReport.with_budget
# ---------------------------------------------------------------------------


def test_with_budget_drops_rows_above_cap() -> None:
    rows = [
        _row(qid="q1", think_n_tok=100),
        _row(qid="q2", think_n_tok=2000),  # exceeds cap
        _row(qid="q3", think_n_tok=300),
    ]
    rep = _report(rows, max_new_tokens=2048)
    capped = rep.with_budget(1500)
    assert {r.qid for r in capped.rows} == {"q1", "q3"}
    assert capped.excluded_qids == ("q2",)
    assert capped.max_new_tokens == 1500


def test_with_budget_keeps_no_think_rows() -> None:
    """A row with has_think=False is not bounded by the cap — keep it."""
    rows = [
        _row(qid="q1", has_think=False, think_n_tok=None, think_text=""),
        _row(qid="q2", has_think=True, think_n_tok=2000),
    ]
    capped = _report(rows, max_new_tokens=2048).with_budget(1500)
    assert {r.qid for r in capped.rows} == {"q1"}
    assert capped.excluded_qids == ("q2",)


def test_with_budget_no_exclusion_when_under_cap() -> None:
    rows = [_row(qid="q1", think_n_tok=100), _row(qid="q2", think_n_tok=200)]
    rep = _report(rows, max_new_tokens=2048)
    capped = rep.with_budget(1500)
    assert len(capped.rows) == 2
    assert capped.excluded_qids == ()
    assert capped.max_new_tokens == 1500


def test_with_budget_preserves_lower_budget_on_cap_higher_than_current() -> None:
    """If cap > self.max_new_tokens, the new budget keeps the smaller value."""
    capped = _report([_row(think_n_tok=100)], max_new_tokens=512).with_budget(1024)
    assert capped.max_new_tokens == 512


def test_with_budget_rejects_zero() -> None:
    with pytest.raises(ProbeError):
        _report([_row()]).with_budget(0)


def test_with_budget_composes_excluded_history() -> None:
    """Successive `with_budget()` calls accumulate excluded qids."""
    rows = [
        _row(qid="q1", think_n_tok=100),
        _row(qid="q2", think_n_tok=600),
        _row(qid="q3", think_n_tok=1500),
    ]
    rep = _report(rows, max_new_tokens=2048)
    step1 = rep.with_budget(1000)  # drops q3
    assert step1.excluded_qids == ("q3",)
    step2 = step1.with_budget(500)  # drops q2
    assert set(step2.excluded_qids) == {"q2", "q3"}


# ---------------------------------------------------------------------------
# ProbeReport.compare
# ---------------------------------------------------------------------------


def test_compare_same_budget_direct_pass() -> None:
    baseline = _report(
        [_row(qid="q1", think_n_tok=200), _row(qid="q2", think_n_tok=300)],
        max_new_tokens=1024,
        model="baseline",
    )
    current = _report(
        [_row(qid="q1", think_n_tok=200), _row(qid="q2", think_n_tok=300)],
        max_new_tokens=1024,
        model="current",
    )
    result = current.compare(baseline)
    assert isinstance(result, CompareResult)
    assert result.all_pass is True
    assert result.budget_normalized is False
    assert result.budget_cap is None
    assert result.excluded_qids == ()
    metrics = {r.metric: r for r in result.rows}
    assert metrics["think_presence_rate"].status == "PASS"
    assert metrics["think_token_length"].status == "PASS"


def test_compare_records_labels() -> None:
    baseline = _report([_row(think_n_tok=200)], max_new_tokens=1024, model="base-m")
    current = _report([_row(think_n_tok=200)], max_new_tokens=1024, model="curr-m")
    result = current.compare(baseline)
    assert result.baseline_label == "base-m"
    assert result.current_label == "curr-m"


def test_compare_explicit_label_overrides_model_name() -> None:
    baseline = _report([_row(think_n_tok=200)], max_new_tokens=1024, model="base-m")
    current = _report([_row(think_n_tok=200)], max_new_tokens=1024, model="curr-m")
    result = current.compare(
        baseline, baseline_label="unsloth", current_label="nemo"
    )
    assert result.baseline_label == "unsloth"
    assert result.current_label == "nemo"


def test_compare_fails_when_presence_drops_below_threshold() -> None:
    baseline = _report(
        [_row(qid="q1"), _row(qid="q2"), _row(qid="q3"), _row(qid="q4")],
        max_new_tokens=1024,
        model="base",
    )
    # current has 2/4 with-think → presence 0.5; baseline 1.0; ratio 0.5
    # default threshold is 0.90 — must FAIL.
    current = _report(
        [
            _row(qid="q1"),
            _row(qid="q2"),
            _row(qid="q3", has_think=False, think_n_tok=None, think_text=""),
            _row(qid="q4", has_think=False, think_n_tok=None, think_text=""),
        ],
        max_new_tokens=1024,
        model="current",
    )
    result = current.compare(baseline)
    assert result.all_pass is False
    metrics = {r.metric: r for r in result.rows}
    assert metrics["think_presence_rate"].status == "FAIL"


def test_compare_custom_thresholds_can_pass_what_default_fails() -> None:
    """Loose thresholds = 0.40 → the 0.5-ratio presence drop is now PASS."""
    baseline = _report(
        [_row(qid=f"q{i}") for i in range(4)], max_new_tokens=1024, model="b"
    )
    current = _report(
        [
            _row(qid="q0"),
            _row(qid="q1"),
            _row(qid="q2", has_think=False, think_n_tok=None, think_text=""),
            _row(qid="q3", has_think=False, think_n_tok=None, think_text=""),
        ],
        max_new_tokens=1024,
        model="c",
    )
    result = current.compare(
        baseline,
        thresholds=CompareThresholds(think_presence_rate=0.4, think_token_length=0.4),
    )
    assert result.all_pass is True


def test_compare_normalize_budget_excludes_overlong_qid() -> None:
    """Bakeoff case: Unsloth ran at 1536, NeMo at 2048. A NeMo qid with
    1895 tok would have been truncated at 1536 — exclude from both."""
    unsloth = ProbeReport(
        model="unsloth",
        rows=[
            _row(qid="p-strat-01", think_n_tok=1400),
            _row(qid="p-strat-02", think_n_tok=800),
        ],
        max_new_tokens=1536,
    )
    nemo = ProbeReport(
        model="nemo",
        rows=[
            _row(qid="p-strat-01", think_n_tok=1895),  # over the 1536 cap
            _row(qid="p-strat-02", think_n_tok=800),
        ],
        max_new_tokens=2048,
    )
    result = nemo.compare(unsloth, normalize_budget=True)
    assert result.budget_normalized is True
    assert result.budget_cap == 1536
    assert result.excluded_qids == ("p-strat-01",)


def test_compare_normalize_budget_is_a_noop_when_budgets_match() -> None:
    a = _report([_row(think_n_tok=400)], max_new_tokens=1024, model="a")
    b = _report([_row(think_n_tok=400)], max_new_tokens=1024, model="b")
    result = a.compare(b, normalize_budget=True)
    assert result.budget_normalized is False
    assert result.budget_cap is None


def test_compare_disables_normalize_runs_direct_even_on_diff_budgets() -> None:
    """With normalize_budget=False, the raw aggregates are compared."""
    unsloth = ProbeReport(
        model="unsloth",
        rows=[_row(think_n_tok=1400)],
        max_new_tokens=1536,
    )
    nemo = ProbeReport(
        model="nemo",
        rows=[_row(think_n_tok=1895)],
        max_new_tokens=2048,
    )
    result = nemo.compare(unsloth, normalize_budget=False)
    assert result.budget_normalized is False
    assert result.excluded_qids == ()
    # both reports have 1.0 presence — should pass
    assert result.all_pass is True


def test_compare_skip_on_zero_baseline() -> None:
    """If baseline overall is zeros, ratio is undefined → skip status."""
    baseline_no_think = ProbeReport(
        model="b",
        rows=[_row(has_think=False, think_n_tok=None, think_text="")],
        max_new_tokens=1024,
    )
    current = ProbeReport(
        model="c", rows=[_row(think_n_tok=200)], max_new_tokens=1024
    )
    result = current.compare(baseline_no_think)
    # presence ratio: current 1.0 / baseline 0.0 → skip
    metrics = {r.metric: r for r in result.rows}
    assert metrics["think_presence_rate"].status == "skip"
    # all_pass should still be True (skip excludes from tally)
    assert result.all_pass is True


def test_compare_records_per_category_breakdown() -> None:
    baseline = _report(
        [
            _row(qid="q1", category="general-reasoning", think_n_tok=200),
            _row(qid="q2", category="patent-irac", think_n_tok=300),
        ],
        max_new_tokens=1024,
    )
    current = _report(
        [
            _row(qid="q1", category="general-reasoning", think_n_tok=200),
            _row(qid="q2", category="patent-irac", think_n_tok=300),
        ],
        max_new_tokens=1024,
    )
    result = current.compare(baseline)
    assert "general-reasoning" in result.per_category
    assert "patent-irac" in result.per_category
    assert result.per_category["general-reasoning"]["baseline_presence"] == 1.0
    assert result.per_category["general-reasoning"]["current_presence"] == 1.0


def test_compare_uses_default_thresholds() -> None:
    """DEFAULT_COMPARE_THRESHOLDS is the spec §4 Layer 5 values."""
    assert DEFAULT_COMPARE_THRESHOLDS.think_presence_rate == 0.90
    assert DEFAULT_COMPARE_THRESHOLDS.think_token_length == 0.75


# ---------------------------------------------------------------------------
# ProbeReport — to/from json
# ---------------------------------------------------------------------------


def test_to_dict_matches_canonical_shape() -> None:
    rep = ProbeReport(
        model="m",
        rows=[_row(qid="q1", think_n_tok=300)],
        max_new_tokens=1024,
        temperature=0.6,
        lora_path="/x",
        step=42,
        wall_seconds=12.3,
    )
    d = rep.to_dict()
    assert d["model"] == "m"
    assert d["lora_path"] == "/x"
    assert d["step"] == 42
    assert d["n_probe"] == 1
    assert d["max_new_tokens"] == 1024
    assert d["temperature"] == 0.6
    assert "overall" in d and "by_category" in d
    assert "raw_responses" in d and len(d["raw_responses"]) == 1
    assert d["raw_responses"][0]["qid"] == "q1"
    assert d["raw_responses"][0]["think_n_tok"] == 300
    assert d["wall_seconds"] == 12.3


def test_to_json_then_from_json_round_trip(tmp_path: Path) -> None:
    rep = ProbeReport(
        model="m",
        rows=[
            _row(qid="q1", category="cat-a", think_n_tok=200),
            _row(qid="q2", category="cat-b", has_think=False, think_n_tok=None, think_text=""),
        ],
        max_new_tokens=1024,
        lora_path="/lora",
        step=100,
    )
    p = tmp_path / "rep.json"
    rep.to_json(p)
    loaded = ProbeReport.from_json(p)
    assert loaded.model == "m"
    assert loaded.lora_path == "/lora"
    assert loaded.step == 100
    assert loaded.n == 2
    assert loaded.overall.think_presence_rate == 0.5
    assert {r.qid for r in loaded.rows} == {"q1", "q2"}


def test_from_json_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(ProbeError):
        ProbeReport.from_json(tmp_path / "nope.json")


def test_from_json_invalid_json_raises(tmp_path: Path) -> None:
    p = tmp_path / "bad.json"
    p.write_text("{not-json", encoding="utf-8")
    with pytest.raises(ProbeError):
        ProbeReport.from_json(p)


def test_from_dict_missing_raw_responses_raises() -> None:
    with pytest.raises(ProbeError):
        ProbeReport.from_dict({"model": "m", "max_new_tokens": 1024})


def test_from_dict_row_missing_required_key_raises() -> None:
    with pytest.raises(ProbeError):
        ProbeReport.from_dict(
            {
                "model": "m",
                "max_new_tokens": 1024,
                "raw_responses": [{"qid": "q1"}],  # missing category, response, has_think
            }
        )


def test_from_dict_ignores_legacy_think_quality_score_key() -> None:
    """The legacy spec-§4 LLM-judge score in `overall` must be tolerated
    on load — old probe artifacts have ``"think_quality_score": null``."""
    data = {
        "model": "m",
        "max_new_tokens": 1024,
        "temperature": 0.6,
        "overall": {
            "think_presence_rate": 0.5,
            "think_token_length": 100.0,
            "think_quality_score": None,
            "n": 1,
            "n_judged": 0,
        },
        "raw_responses": [
            {
                "qid": "q1",
                "category": "c",
                "response": "r",
                "has_think": True,
                "think_n_tok": 100,
                "think_text": "x",
                "wall_seconds": 0.0,
            }
        ],
    }
    rep = ProbeReport.from_dict(data)
    assert rep.overall.think_presence_rate == 1.0  # recomputed from rows, not loaded


# ---------------------------------------------------------------------------
# ReasoningProbe.from_jsonl
# ---------------------------------------------------------------------------


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")


def test_from_jsonl_loads_required_keys(tmp_path: Path) -> None:
    p = tmp_path / "probe.jsonl"
    _write_jsonl(
        p,
        [
            {"qid": "q1", "category": "general-reasoning", "question": "what is 2+2?"},
            {"qid": "q2", "category": "patent-irac", "question": "claim construction?"},
        ],
    )
    probe = ReasoningProbe.from_jsonl(p)
    assert len(probe) == 2
    assert probe.questions[0].qid == "q1"
    assert probe.questions[1].category == "patent-irac"


def test_from_jsonl_collects_optional_pass_throughs(tmp_path: Path) -> None:
    p = tmp_path / "probe.jsonl"
    _write_jsonl(
        p,
        [
            {
                "qid": "q1",
                "category": "c",
                "question": "?",
                "source": "AIME-2024",
                "license": "MIT",
                "extra": "metadata-pass-through",
            }
        ],
    )
    probe = ReasoningProbe.from_jsonl(p)
    q = probe.questions[0]
    assert q.source == "AIME-2024"
    assert q.license == "MIT"
    assert q.metadata.get("extra") == "metadata-pass-through"


def test_from_jsonl_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(ProbeError):
        ReasoningProbe.from_jsonl(tmp_path / "nope.jsonl")


def test_from_jsonl_malformed_line_raises(tmp_path: Path) -> None:
    p = tmp_path / "bad.jsonl"
    p.write_text('{"qid":"q1","category":"c","question":"q"}\n{not-json\n', encoding="utf-8")
    with pytest.raises(ProbeError):
        ReasoningProbe.from_jsonl(p)


def test_from_jsonl_missing_required_key_raises(tmp_path: Path) -> None:
    p = tmp_path / "missing-key.jsonl"
    _write_jsonl(p, [{"qid": "q1", "category": "c"}])  # no question
    with pytest.raises(ProbeError):
        ReasoningProbe.from_jsonl(p)


def test_from_jsonl_empty_file_raises(tmp_path: Path) -> None:
    p = tmp_path / "empty.jsonl"
    p.write_text("\n\n", encoding="utf-8")
    with pytest.raises(ProbeError):
        ReasoningProbe.from_jsonl(p)


def test_from_jsonl_skips_blank_lines(tmp_path: Path) -> None:
    p = tmp_path / "with-blanks.jsonl"
    p.write_text(
        '\n\n{"qid":"q1","category":"c","question":"?"}\n\n', encoding="utf-8"
    )
    probe = ReasoningProbe.from_jsonl(p)
    assert len(probe) == 1


# ---------------------------------------------------------------------------
# ReasoningProbe.run with fake generator
# ---------------------------------------------------------------------------


def test_run_with_fake_generator_returns_probereport() -> None:
    questions = [
        ProbeQuestion(qid="q1", category="general-reasoning", question="?"),
        ProbeQuestion(qid="q2", category="patent-irac", question="?"),
    ]

    def fake_gen(q: ProbeQuestion) -> str:
        return f"<think>thinking about {q.qid}</think>answer-{q.qid}"

    probe = ReasoningProbe(questions)
    rep = probe.run(
        model_id="fake-model",
        step=42,
        max_new_tokens=1024,
        generator=fake_gen,
    )
    assert isinstance(rep, ProbeReport)
    assert rep.model == "fake-model"
    assert rep.step == 42
    assert rep.n == 2
    assert rep.overall.think_presence_rate == 1.0
    assert {r.qid for r in rep.rows} == {"q1", "q2"}


def test_run_records_lora_path_and_metadata() -> None:
    def gen(_q: ProbeQuestion) -> str:
        return "<think>x</think>y"

    rep = ReasoningProbe(
        [ProbeQuestion(qid="q1", category="c", question="?")]
    ).run(
        model_id="m",
        lora_path="/runs/ckpt-200",
        step=200,
        max_new_tokens=2048,
        temperature=0.7,
        generator=gen,
    )
    assert rep.lora_path == "/runs/ckpt-200"
    assert rep.step == 200
    assert rep.max_new_tokens == 2048
    assert rep.temperature == 0.7


def test_run_on_progress_callback_fires_per_question() -> None:
    questions = [ProbeQuestion(qid=f"q{i}", category="c", question="?") for i in range(3)]
    seen: list[tuple[int, int, str]] = []

    def gen(q: ProbeQuestion) -> str:
        return f"<think>{q.qid}</think>"

    def on_progress(i: int, total: int, row: ProbeRow) -> None:
        seen.append((i, total, row.qid))

    ReasoningProbe(questions).run(
        model_id="m", generator=gen, on_progress=on_progress
    )
    assert seen == [(1, 3, "q0"), (2, 3, "q1"), (3, 3, "q2")]


def test_run_rejects_zero_max_new_tokens() -> None:
    def gen(_q: ProbeQuestion) -> str:
        return ""

    probe = ReasoningProbe([ProbeQuestion(qid="q1", category="c", question="?")])
    with pytest.raises(ProbeError):
        probe.run(model_id="m", max_new_tokens=0, generator=gen)


def test_run_records_wall_seconds() -> None:
    def gen(_q: ProbeQuestion) -> str:
        return "<think>x</think>"

    rep = ReasoningProbe(
        [ProbeQuestion(qid="q1", category="c", question="?")]
    ).run(model_id="m", generator=gen)
    assert rep.wall_seconds >= 0.0
    assert rep.rows[0].wall_seconds >= 0.0


def test_run_no_think_response_recorded_correctly() -> None:
    def gen(_q: ProbeQuestion) -> str:
        return "answer without any think block"

    rep = ReasoningProbe(
        [ProbeQuestion(qid="q1", category="c", question="?")]
    ).run(model_id="m", generator=gen)
    assert rep.rows[0].has_think is False
    assert rep.rows[0].think_n_tok is None


def test_reasoning_probe_rejects_empty_question_list() -> None:
    with pytest.raises(ProbeError):
        ReasoningProbe([])


def test_reasoning_probe_len() -> None:
    probe = ReasoningProbe(
        [ProbeQuestion(qid="q1", category="c", question="?")]
    )
    assert len(probe) == 1
