# Copyright 2026 Manav Sehgal
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for `fieldkit.eval` — Bench (offline), Judge (respx-mocked
NIM), Trajectory (fixture JSONL). No live services required.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx

from fieldkit.eval import (
    ASSERTION_KINDS,
    BUILTIN_RUBRICS,
    REFUSAL_PATTERNS,
    RUBRIC_CORRECTNESS,
    RUBRIC_FAITHFULNESS,
    RUBRIC_RELEVANCE,
    AgentRun,
    AssertionGrader,
    AssertionResult,
    Bench,
    BenchCall,
    GradeResult,
    GroupStats,
    Judge,
    JudgeError,
    JudgeResult,
    MatchedBaseComparison,
    MatchedBaseComparisonResult,
    PassAtK,
    PassAtKResult,
    Trajectory,
    TrajectoryIter,
    TurnDetail,
    is_refusal,
    pass_at_k_estimator,
    summarize_agent_runs,
    summarize_metric,
)
from fieldkit.nim import NIMClient


NIM_BASE_URL = "http://nim.test/v1"
NIM_MODEL = "meta/llama-3.1-8b-instruct"


# --- summarize_metric ----------------------------------------------------


class TestSummarizeMetric:
    def test_empty_returns_n_zero(self) -> None:
        assert summarize_metric([]) == {"n": 0}

    def test_all_none_returns_n_zero(self) -> None:
        assert summarize_metric([None, None]) == {"n": 0}

    def test_basic_stats(self) -> None:
        s = summarize_metric([1.0, 2.0, 3.0, 4.0, 5.0])
        assert s["n"] == 5
        assert s["mean"] == 3.0
        assert s["median"] == 3.0
        assert s["min"] == 1.0
        assert s["max"] == 5.0

    def test_drops_none_entries(self) -> None:
        s = summarize_metric([10.0, None, 20.0, None])
        assert s["n"] == 2
        assert s["min"] == 10.0
        assert s["max"] == 20.0


# --- Bench ---------------------------------------------------------------


def _identity_with_metrics(x: int) -> dict[str, Any]:
    return {"value": x, "tokens": x * 10}


def _nested_metrics(x: int) -> dict[str, Any]:
    return {
        "answer": f"answer-{x}",
        "timings_ms": {"embed": x * 1.0, "retrieve": x * 2.0, "generate": x * 3.0},
    }


class TestBenchRun:
    def test_collects_calls(self) -> None:
        b = Bench("identity")
        b.run(_identity_with_metrics, [1, 2, 3])
        assert len(b.calls) == 3
        assert all(c.success for c in b.calls)
        assert [c.input for c in b.calls] == [1, 2, 3]
        assert b.calls[0].output == {"value": 1, "tokens": 10}

    def test_extracts_top_level_metrics(self) -> None:
        b = Bench("identity", metrics=["tokens"])
        b.run(_identity_with_metrics, [1, 2, 3])
        assert [c.metrics["tokens"] for c in b.calls] == [10.0, 20.0, 30.0]

    def test_extracts_nested_metrics_via_metrics_key(self) -> None:
        b = Bench("rag", metrics=["embed", "retrieve"], metrics_key="timings_ms")
        b.run(_nested_metrics, [1, 2, 3])
        assert b.calls[0].metrics == {"embed": 1.0, "retrieve": 2.0}
        assert b.calls[2].metrics == {"embed": 3.0, "retrieve": 6.0}

    def test_records_latency_ms(self) -> None:
        def slow(x: int) -> int:
            time.sleep(0.01)
            return x

        b = Bench("slow")
        b.run(slow, [1])
        assert b.calls[0].latency_ms >= 9.0  # 10ms sleep, allow noise

    def test_run_returns_self(self) -> None:
        b = Bench("chain")
        result = b.run(_identity_with_metrics, [1])
        assert result is b

    def test_tag_fn_attaches_metadata(self) -> None:
        b = Bench("tagged")
        b.run(_identity_with_metrics, [1, 2], tag_fn=lambda x: {"kind": "even" if x % 2 == 0 else "odd"})
        assert b.calls[0].tags == {"kind": "odd"}
        assert b.calls[1].tags == {"kind": "even"}


class TestBenchOnError:
    def test_default_records_failure(self) -> None:
        def boom(x: int) -> int:
            if x == 2:
                raise ValueError("nope")
            return x

        b = Bench("boom")
        b.run(boom, [1, 2, 3])
        assert [c.success for c in b.calls] == [True, False, True]
        assert b.calls[1].error is not None
        assert "ValueError" in b.calls[1].error
        assert "nope" in b.calls[1].error

    def test_raise_aborts_sweep(self) -> None:
        def boom(x: int) -> int:
            if x == 2:
                raise ValueError("nope")
            return x

        b = Bench("boom")
        with pytest.raises(ValueError, match="nope"):
            b.run(boom, [1, 2, 3], on_error="raise")
        # Got call 1 in before raising.
        assert len(b.calls) == 1
        assert b.calls[0].success

    def test_invalid_on_error_value(self) -> None:
        b = Bench("x")
        with pytest.raises(ValueError, match="on_error"):
            b.run(lambda x: x, [1], on_error="huh")


class TestBenchRecord:
    def test_imperative_record(self) -> None:
        b = Bench("manual", metrics=["embed", "retrieve"])
        b.record(input="q1", latency_ms=42.0, embed=10.0, retrieve=32.0)
        assert b.calls[0].latency_ms == 42.0
        assert b.calls[0].metrics == {"embed": 10.0, "retrieve": 32.0}


class TestBenchSummary:
    def test_empty_summary(self) -> None:
        b = Bench("empty")
        assert b.summary() == {"name": "empty", "n": 0}

    def test_aggregates_latency_and_metrics(self) -> None:
        b = Bench("agg", metrics=["tokens"])
        for i in [1, 2, 3]:
            b.record(latency_ms=float(i * 100), tokens=float(i * 10))
        s = b.summary()
        assert s["n"] == 3
        assert s["n_success"] == 3
        assert s["n_failure"] == 0
        assert s["latency_ms"]["mean"] == 200.0
        assert s["latency_ms"]["min"] == 100.0
        assert s["latency_ms"]["max"] == 300.0
        assert s["tokens"]["mean"] == 20.0
        assert s["tokens"]["median"] == 20.0

    def test_failures_counted(self) -> None:
        b = Bench("agg")
        b.record(latency_ms=10.0)
        b.record(latency_ms=20.0, success=False, error="boom")
        s = b.summary()
        assert s["n"] == 2
        assert s["n_success"] == 1
        assert s["n_failure"] == 1
        # Failure latency is excluded from successful aggregate.
        assert s["latency_ms"]["n"] == 1
        assert s["latency_ms"]["mean"] == 10.0


class TestBenchReport:
    def test_renders_markdown_table(self) -> None:
        b = Bench("doc", metrics=["tokens"])
        b.record(latency_ms=10.0, tokens=5.0)
        b.record(latency_ms=20.0, tokens=15.0)
        text = b.report()
        assert "### Bench: doc (n=2)" in text
        assert "| metric | mean | median | min | max |" in text
        assert "| latency_ms |" in text
        assert "| tokens |" in text

    def test_dashes_when_metric_missing(self) -> None:
        b = Bench("doc", metrics=["tokens"])
        b.record(latency_ms=10.0)  # no tokens metric provided
        text = b.report()
        assert "| tokens | — | — | — | — |" in text


class TestBenchDump:
    def test_dump_round_trip(self, tmp_path: Path) -> None:
        b = Bench("dumper", metrics=["tokens"])
        b.record(input="q", output={"answer": "a"}, latency_ms=12.0, tokens=7.0)
        path = b.dump(tmp_path / "bench.json")
        loaded = json.loads(path.read_text())
        assert loaded["summary"]["name"] == "dumper"
        assert loaded["summary"]["n"] == 1
        assert "calls" in loaded
        assert len(loaded["calls"]) == 1
        # Output dropped by default.
        assert "output" not in loaded["calls"][0]
        assert loaded["calls"][0]["latency_ms"] == 12.0
        assert loaded["calls"][0]["metrics"] == {"tokens": 7.0}

    def test_dump_can_include_outputs(self, tmp_path: Path) -> None:
        b = Bench("dumper")
        b.record(input="q", output={"answer": "long-answer"}, latency_ms=1.0)
        path = b.dump(tmp_path / "bench.json", include_outputs=True)
        loaded = json.loads(path.read_text())
        assert loaded["calls"][0]["output"] == {"answer": "long-answer"}


class TestBenchContextManager:
    def test_wall_seconds_recorded(self) -> None:
        with Bench("walled") as b:
            time.sleep(0.005)
        assert b.wall_seconds >= 0.004
        assert "wall_seconds" not in b.summary()  # n==0 short-circuits
        b.record(latency_ms=1.0)
        s = b.summary()
        assert s["wall_seconds"] >= 0.004


# --- is_refusal ----------------------------------------------------------


class TestIsRefusal:
    def test_empty_is_refusal(self) -> None:
        assert is_refusal("")
        assert is_refusal(None)

    @pytest.mark.parametrize(
        "text",
        [
            "I do not know the answer.",
            "I don't have enough information.",
            "I cannot answer that.",
            "I am not able to provide that.",
            "The provided context does not contain the answer.",
            "Not specified in the context.",
            "No information available.",
            "Unclear from the passages.",
            "Insufficient context for that question.",
            "Cannot be determined from the source.",
        ],
    )
    def test_known_refusal_patterns(self, text: str) -> None:
        assert is_refusal(text), f"should be refusal: {text!r}"

    @pytest.mark.parametrize(
        "text",
        [
            "George W. Bush won the 2004 election.",
            "The Spark has 128 GB of unified memory.",
            "Phelps won 8 medals at the 2008 Olympics.",
        ],
    )
    def test_real_answers_not_flagged(self, text: str) -> None:
        assert not is_refusal(text), f"should NOT be refusal: {text!r}"


# --- Judge ---------------------------------------------------------------


def _judge_response(content: str) -> dict[str, Any]:
    return {
        "id": "chatcmpl-judge",
        "object": "chat.completion",
        "model": NIM_MODEL,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 100, "completion_tokens": 30, "total_tokens": 130},
    }


@pytest.fixture
def judge_client() -> NIMClient:
    c = NIMClient(base_url=NIM_BASE_URL, model=NIM_MODEL, max_retries=0, timeout=2.0)
    yield c
    c.close()


class TestJudgeBuiltins:
    def test_builtin_rubrics_present(self) -> None:
        assert set(BUILTIN_RUBRICS) == {"correctness", "faithfulness", "relevance"}
        assert BUILTIN_RUBRICS["correctness"] is RUBRIC_CORRECTNESS
        assert BUILTIN_RUBRICS["faithfulness"] is RUBRIC_FAITHFULNESS
        assert BUILTIN_RUBRICS["relevance"] is RUBRIC_RELEVANCE

    def test_builtin_factory(self, judge_client: NIMClient) -> None:
        j = Judge.builtin(judge_client, "correctness")
        assert j.rubric == RUBRIC_CORRECTNESS

    def test_builtin_factory_unknown_kind(self, judge_client: NIMClient) -> None:
        with pytest.raises(ValueError, match="unknown rubric"):
            Judge.builtin(judge_client, "made-up")


class TestJudgeParse:
    def test_strict_json_with_int_score(self) -> None:
        r = Judge.parse('{"score": 4, "rationale": "almost right"}')
        assert r.score == 4.0
        assert r.rationale == "almost right"

    def test_strict_json_with_float_score(self) -> None:
        r = Judge.parse('{"score": 0.5, "rationale": "partial"}')
        assert r.score == 0.5
        assert r.rationale == "partial"

    def test_strips_json_fences(self) -> None:
        text = '```json\n{"score": 5, "rationale": "exact"}\n```'
        r = Judge.parse(text)
        assert r.score == 5.0
        assert r.rationale == "exact"

    def test_strips_bare_fences(self) -> None:
        text = '```\n{"score": 3, "rationale": "ok"}\n```'
        r = Judge.parse(text)
        assert r.score == 3.0

    def test_regex_fallback_when_json_invalid(self) -> None:
        # Trailing prose, no closing brace handling — regex finds the score.
        r = Judge.parse('here you go: "score": 2, then more text')
        assert r.score == 2.0

    def test_returns_none_when_unparseable(self) -> None:
        r = Judge.parse("I cannot give a score, sorry.")
        assert r.score is None
        assert "cannot give" in r.rationale

    def test_largest_brace_substring_wins(self) -> None:
        # Two JSON-ish braces; largest substring carries the actual score.
        r = Judge.parse('preface {garbage} ... {"score": 4, "rationale": "fine"}')
        assert r.score == 4.0


class TestJudgeGrade:
    def test_grade_correctness_round_trip(
        self, judge_client: NIMClient, respx_mock: respx.MockRouter
    ) -> None:
        route = respx_mock.post(f"{NIM_BASE_URL}/chat/completions").mock(
            return_value=httpx.Response(
                200, json=_judge_response('{"score": 4, "rationale": "close enough"}')
            )
        )
        j = Judge.builtin(judge_client, "correctness")
        result = j.grade(
            question="Q?", reference="R", prediction="P"
        )
        assert isinstance(result, JudgeResult)
        assert result.score == 4.0
        assert result.rationale == "close enough"
        # Verify the rubric arrived as the system message.
        body = json.loads(route.calls[0].request.content)
        assert body["messages"][0]["role"] == "system"
        assert "0-5 scale" in body["messages"][0]["content"]
        # User message includes question + reference + prediction.
        user = body["messages"][1]["content"]
        assert "Question: Q?" in user
        assert "Reference answer: R" in user
        assert "Predicted answer: P" in user

    def test_grade_faithfulness_uses_context(
        self, judge_client: NIMClient, respx_mock: respx.MockRouter
    ) -> None:
        route = respx_mock.post(f"{NIM_BASE_URL}/chat/completions").mock(
            return_value=httpx.Response(
                200, json=_judge_response('{"score": 1.0, "rationale": "all supported"}')
            )
        )
        j = Judge.builtin(judge_client, "faithfulness")
        r = j.grade(prediction="A", context="passage about A")
        assert r.score == 1.0
        body = json.loads(route.calls[0].request.content)
        assert "Context passages" in body["messages"][1]["content"]
        assert "passage about A" in body["messages"][1]["content"]

    def test_grade_handles_unparseable_judge_output(
        self, judge_client: NIMClient, respx_mock: respx.MockRouter
    ) -> None:
        respx_mock.post(f"{NIM_BASE_URL}/chat/completions").mock(
            return_value=httpx.Response(
                200, json=_judge_response("this judge forgot the JSON envelope")
            )
        )
        j = Judge.builtin(judge_client, "correctness")
        r = j.grade(prediction="x", reference="y", question="z")
        assert r.score is None

    def test_grade_wraps_nim_errors(
        self, judge_client: NIMClient, respx_mock: respx.MockRouter
    ) -> None:
        respx_mock.post(f"{NIM_BASE_URL}/chat/completions").mock(
            return_value=httpx.Response(400, text="bad request")
        )
        j = Judge.builtin(judge_client, "correctness")
        with pytest.raises(JudgeError, match="judge call failed"):
            j.grade(prediction="x", reference="y", question="z")


class TestJudgeRefusalPatternsExposed:
    def test_refusal_patterns_compiled(self) -> None:
        # Sanity: tuple of compiled regexes, all case-insensitive.
        assert len(REFUSAL_PATTERNS) > 0
        for p in REFUSAL_PATTERNS:
            assert p.flags & 2  # re.IGNORECASE


# --- Trajectory ----------------------------------------------------------


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> Path:
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    return path


def _baseline_header() -> dict[str, Any]:
    return {
        "_meta": "trajectory log",
        "baseline_val_bpb": 10.95,
        "baseline_cfg": {"n_layer": 24},
    }


def _iter_record(
    iter: int, knob: str, value: Any, decision: str, val_bpb: float, **extra: Any
) -> dict[str, Any]:
    rec = {
        "iter": iter,
        "stage": "evaluated",
        "proposal": {"knob": knob, "new_value": value, "reason": "test"},
        "decision": decision,
        "val_bpb": val_bpb,
    }
    rec.update(extra)
    return rec


@pytest.fixture
def trajectory_path(tmp_path: Path) -> Path:
    rows = [
        _baseline_header(),
        _iter_record(1, "lr", 1e-3, "keep", 10.90),
        _iter_record(2, "lr", 1e-3, "revert", 10.92),  # repeat
        _iter_record(3, "n_head", 8, "keep", 10.85),
        _iter_record(4, "n_head", 8, "revert", 10.88),  # repeat
        _iter_record(5, "d_model", 512, "keep", 10.80),
    ]
    return _write_jsonl(tmp_path / "traj.jsonl", rows)


class TestTrajectoryParse:
    def test_basic_parse(self, trajectory_path: Path) -> None:
        t = Trajectory.from_jsonl(trajectory_path)
        assert len(t.iters) == 5
        assert t.baseline == 10.95
        assert t.header["_meta"] == "trajectory log"
        assert t.iters[0].knob == "lr"
        assert t.iters[0].decision == "keep"

    def test_no_header_still_parses(self, tmp_path: Path) -> None:
        rows = [
            _iter_record(1, "lr", 1e-3, "keep", 10.90),
            _iter_record(2, "n_head", 8, "revert", 10.92),
        ]
        p = _write_jsonl(tmp_path / "traj.jsonl", rows)
        t = Trajectory.from_jsonl(p)
        assert t.baseline is None
        assert len(t.iters) == 2

    def test_skips_non_evaluated_stages(self, tmp_path: Path) -> None:
        rows = [
            _baseline_header(),
            _iter_record(1, "lr", 1e-3, "keep", 10.90),
            {"iter": 2, "stage": "proposed", "proposal": {"knob": "lr", "new_value": 2e-3}},
            {"iter": 3, "stage": "failed", "proposal": {"knob": "lr", "new_value": 3e-3}},
            _iter_record(4, "n_head", 8, "keep", 10.85),
        ]
        p = _write_jsonl(tmp_path / "traj.jsonl", rows)
        t = Trajectory.from_jsonl(p)
        assert [it.iter for it in t.iters] == [1, 4]

    def test_skips_malformed_lines(self, tmp_path: Path) -> None:
        path = tmp_path / "traj.jsonl"
        path.write_text(
            json.dumps(_baseline_header()) + "\n"
            "this is not json\n"
            + json.dumps(_iter_record(1, "lr", 1e-3, "keep", 10.90)) + "\n"
            "\n"  # blank
            + json.dumps({"iter": 2, "stage": "evaluated", "proposal": {"knob": "x"}, "decision": "k"}) + "\n"  # missing val_bpb
            + json.dumps(_iter_record(3, "n_head", 8, "keep", 10.85)) + "\n"
        )
        t = Trajectory.from_jsonl(path)
        assert [it.iter for it in t.iters] == [1, 3]

    def test_empty_file(self, tmp_path: Path) -> None:
        p = tmp_path / "empty.jsonl"
        p.write_text("")
        t = Trajectory.from_jsonl(p)
        assert t.iters == []
        assert t.baseline is None

    def test_alternate_score_field(self, tmp_path: Path) -> None:
        rows = [
            {"baseline_loss": 5.0},
            {"iter": 1, "stage": "evaluated", "proposal": {"knob": "x", "new_value": 1}, "decision": "keep", "loss": 4.5},
            {"iter": 2, "stage": "evaluated", "proposal": {"knob": "y", "new_value": 2}, "decision": "revert", "loss": 4.8},
        ]
        p = _write_jsonl(tmp_path / "traj.jsonl", rows)
        t = Trajectory.from_jsonl(p, score_field="loss")
        assert t.baseline == 5.0
        assert t.iters[0].score == 4.5
        assert t.iters[1].score == 4.8


class TestTrajectoryAnalysis:
    def test_knob_coverage_basic(self, trajectory_path: Path) -> None:
        t = Trajectory.from_jsonl(trajectory_path)
        cov = t.knob_coverage()
        assert cov["knobs_touched"] == 3
        assert cov["knob_count"] == {"lr": 2, "n_head": 2, "d_model": 1}
        # No `all_knobs` → no untouched / pct.
        assert "knobs_untouched" not in cov

    def test_knob_coverage_with_universe(self, trajectory_path: Path) -> None:
        t = Trajectory.from_jsonl(trajectory_path)
        cov = t.knob_coverage(["lr", "n_head", "d_model", "weight_decay", "beta1"])
        assert cov["knobs_total"] == 5
        assert cov["knobs_untouched"] == ["weight_decay", "beta1"]
        assert cov["knobs_touched_pct"] == 60.0

    def test_repeat_rate_total(self, trajectory_path: Path) -> None:
        t = Trajectory.from_jsonl(trajectory_path)
        # Iter 2 (lr=1e-3) and iter 4 (n_head=8) repeat → 2/5 = 0.4
        assert t.repeat_rate() == 0.4

    def test_repeat_rate_windowed(self, trajectory_path: Path) -> None:
        t = Trajectory.from_jsonl(trajectory_path)
        windows = t.repeat_rate(window=2)
        assert isinstance(windows, list)
        assert windows[0] == {"first": 1, "last": 2, "n": 2, "repeats": 1, "rate": 0.5}
        assert windows[1] == {"first": 3, "last": 4, "n": 2, "repeats": 1, "rate": 0.5}
        assert windows[2] == {"first": 5, "last": 5, "n": 1, "repeats": 0, "rate": 0.0}

    def test_repeat_rate_rejects_non_positive_window(
        self, trajectory_path: Path
    ) -> None:
        t = Trajectory.from_jsonl(trajectory_path)
        with pytest.raises(ValueError, match="window"):
            t.repeat_rate(window=0)

    def test_mode_dominance(self, trajectory_path: Path) -> None:
        t = Trajectory.from_jsonl(trajectory_path)
        modes = t.mode_dominance(top_n=2)
        assert len(modes) == 2
        # lr=1e-3 and n_head=8 each have count 2
        assert {(m["knob"], m["n"]) for m in modes} == {("lr", 2), ("n_head", 2)}

    def test_mode_dominance_full(self, trajectory_path: Path) -> None:
        t = Trajectory.from_jsonl(trajectory_path)
        modes = t.mode_dominance()
        assert len(modes) == 3  # 3 distinct (knob, value) pairs

    def test_cumulative_best(self, trajectory_path: Path) -> None:
        t = Trajectory.from_jsonl(trajectory_path)
        # baseline 10.95 → 10.90, 10.90, 10.85, 10.85, 10.80
        assert t.cumulative_best() == [10.90, 10.90, 10.85, 10.85, 10.80]

    def test_cumulative_best_with_explicit_baseline(
        self, trajectory_path: Path
    ) -> None:
        t = Trajectory.from_jsonl(trajectory_path)
        out = t.cumulative_best(baseline=10.84)
        # Iter 1 doesn't beat 10.84 (10.90 > 10.84), iter 3 doesn't (10.85 > 10.84),
        # but iter 5 (10.80) does.
        assert out[0] == 10.84
        assert out[2] == 10.84
        assert out[4] == 10.80

    def test_higher_is_better(self, tmp_path: Path) -> None:
        rows = [
            {"baseline_score": 0.5},
            {"iter": 1, "stage": "evaluated", "proposal": {"knob": "x", "new_value": 1}, "decision": "keep", "score": 0.6},
            {"iter": 2, "stage": "evaluated", "proposal": {"knob": "y", "new_value": 2}, "decision": "revert", "score": 0.55},
            {"iter": 3, "stage": "evaluated", "proposal": {"knob": "z", "new_value": 3}, "decision": "keep", "score": 0.7},
        ]
        p = _write_jsonl(tmp_path / "traj.jsonl", rows)
        t = Trajectory.from_jsonl(p, score_field="score", lower_is_better=False)
        assert t.cumulative_best() == [0.6, 0.6, 0.7]
        assert t.best().score == 0.7

    def test_keeps_filter(self, trajectory_path: Path) -> None:
        t = Trajectory.from_jsonl(trajectory_path)
        keeps = t.keeps()
        assert [it.iter for it in keeps] == [1, 3, 5]

    def test_best_iteration(self, trajectory_path: Path) -> None:
        t = Trajectory.from_jsonl(trajectory_path)
        b = t.best()
        assert b is not None
        assert b.iter == 5
        assert b.score == 10.80

    def test_best_empty(self, tmp_path: Path) -> None:
        p = tmp_path / "empty.jsonl"
        p.write_text("")
        t = Trajectory.from_jsonl(p)
        assert t.best() is None

    def test_unhashable_value_does_not_crash(self, tmp_path: Path) -> None:
        # Some knobs might propose dict / list values.
        rows = [
            _baseline_header(),
            _iter_record(1, "shape", [1, 2, 3], "keep", 10.90),
            _iter_record(2, "shape", [1, 2, 3], "revert", 10.92),  # same list → repeat
            _iter_record(3, "shape", [1, 2, 4], "keep", 10.88),
        ]
        p = _write_jsonl(tmp_path / "traj.jsonl", rows)
        t = Trajectory.from_jsonl(p)
        assert t.repeat_rate() == round(1 / 3, 3)
        modes = t.mode_dominance()
        # Two distinct (knob, value) tuples after hashing
        assert len(modes) == 2


# --- AssertionGrader -----------------------------------------------------


def _make_task(
    *,
    task_id: str = "synth-test-00",
    assertions: list[dict[str, Any]] | None = None,
    seed_files: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "task_id": task_id,
        "verifiable_assertions": assertions or [],
        "workspace_seed": {"files": seed_files or []},
    }


class TestAssertionGraderKinds:
    def test_supported_kinds_match_constant(self) -> None:
        assert AssertionGrader.supported_kinds() == ASSERTION_KINDS
        assert "file_exists" in ASSERTION_KINDS
        assert "file_unchanged" in ASSERTION_KINDS

    def test_file_exists_pass_and_fail(self, tmp_path: Path) -> None:
        (tmp_path / "present.txt").write_text("hi")
        task = _make_task(
            assertions=[
                {"kind": "file_exists", "path": "present.txt"},
                {"kind": "file_exists", "path": "missing.txt"},
            ]
        )
        result = AssertionGrader().grade(task, tmp_path)
        assert result.task_id == "synth-test-00"
        assert result.n_total == 2
        assert result.n_passed == 1
        assert not result.passed
        assert result.assertions[0].passed
        assert "missing" in result.assertions[1].detail

    def test_file_exists_matches_directory(self, tmp_path: Path) -> None:
        (tmp_path / "subdir").mkdir()
        task = _make_task(
            assertions=[{"kind": "file_exists", "path": "subdir"}]
        )
        result = AssertionGrader().grade(task, tmp_path)
        assert result.passed

    def test_file_not_exists(self, tmp_path: Path) -> None:
        (tmp_path / "stale.txt").write_text("old")
        task = _make_task(
            assertions=[
                {"kind": "file_not_exists", "path": "stale.txt"},
                {"kind": "file_not_exists", "path": "absent.txt"},
            ]
        )
        result = AssertionGrader().grade(task, tmp_path)
        assert not result.assertions[0].passed
        assert result.assertions[1].passed

    def test_file_contents_contain(self, tmp_path: Path) -> None:
        (tmp_path / "log.txt").write_text("hello world\nfoo bar\n")
        task = _make_task(
            assertions=[
                {
                    "kind": "file_contents_contain",
                    "path": "log.txt",
                    "must_contain": ["hello", "bar"],
                },
                {
                    "kind": "file_contents_contain",
                    "path": "log.txt",
                    "must_contain": ["nope"],
                },
                {
                    "kind": "file_contents_contain",
                    "path": "nofile.txt",
                    "must_contain": ["x"],
                },
            ]
        )
        result = AssertionGrader().grade(task, tmp_path)
        assert result.assertions[0].passed
        assert not result.assertions[1].passed
        assert "missing substrings" in result.assertions[1].detail
        assert not result.assertions[2].passed
        assert "file missing" in result.assertions[2].detail

    def test_file_contents_match_regex(self, tmp_path: Path) -> None:
        (tmp_path / "code.py").write_text("def foo():\n    return 42\n")
        task = _make_task(
            assertions=[
                {
                    "kind": "file_contents_match_regex",
                    "path": "code.py",
                    "regex": r"def\s+foo\(\):",
                },
                {
                    "kind": "file_contents_match_regex",
                    "path": "code.py",
                    "regex": r"class\s+",
                },
            ]
        )
        result = AssertionGrader().grade(task, tmp_path)
        assert result.assertions[0].passed
        assert not result.assertions[1].passed
        assert "regex not matched" in result.assertions[1].detail

    def test_file_unchanged_with_seeds_pass_and_fail(self, tmp_path: Path) -> None:
        (tmp_path / "config.yml").write_text("a: 1\n")
        (tmp_path / "drifted.yml").write_text("a: 1\nb: 2\n")
        task = _make_task(
            seed_files=[
                {"kind": "text", "path": "config.yml", "content": "a: 1\n"},
                {"kind": "text", "path": "drifted.yml", "content": "a: 1\n"},
            ],
            assertions=[
                {"kind": "file_unchanged", "path": "config.yml"},
                {"kind": "file_unchanged", "path": "drifted.yml"},
            ],
        )
        result = AssertionGrader().grade(task, tmp_path)
        assert result.assertions[0].passed
        assert not result.assertions[1].passed
        assert "diverged" in result.assertions[1].detail

    def test_file_unchanged_without_seed_skipped(self, tmp_path: Path) -> None:
        (tmp_path / "untouched.txt").write_text("content")
        task = _make_task(
            assertions=[{"kind": "file_unchanged", "path": "untouched.txt"}]
        )
        # No seed_files given, no workspace_seed entry — assertion is skipped (passes).
        result = AssertionGrader().grade(task, tmp_path)
        assert result.assertions[0].passed
        assert "skipped" in result.assertions[0].detail

    def test_file_unchanged_missing_post_rollout_fails(self, tmp_path: Path) -> None:
        task = _make_task(
            seed_files=[{"kind": "text", "path": "x.txt", "content": "v"}],
            assertions=[{"kind": "file_unchanged", "path": "x.txt"}],
        )
        result = AssertionGrader().grade(task, tmp_path)
        assert not result.assertions[0].passed
        assert "missing post-rollout" in result.assertions[0].detail


class TestAssertionGraderInputShapes:
    def test_bare_assertions_list(self, tmp_path: Path) -> None:
        (tmp_path / "a.txt").write_text("hi")
        result = AssertionGrader().grade(
            [{"kind": "file_exists", "path": "a.txt"}],
            tmp_path,
            task_id="bare-input",
        )
        assert result.task_id == "bare-input"
        assert result.passed

    def test_explicit_seed_overrides_workspace(self, tmp_path: Path) -> None:
        (tmp_path / "x.txt").write_text("the real contents")
        task = _make_task(
            seed_files=[{"kind": "text", "path": "x.txt", "content": "WRONG"}],
            assertions=[{"kind": "file_unchanged", "path": "x.txt"}],
        )
        # workspace_seed says "WRONG" (would fail), explicit seed says "the real contents"
        result = AssertionGrader().grade(
            task, tmp_path, seed_files={"x.txt": "the real contents"}
        )
        assert result.assertions[0].passed

    def test_unknown_kind_fails_with_detail_not_crashes(
        self, tmp_path: Path
    ) -> None:
        task = _make_task(
            assertions=[{"kind": "file_is_chmod_777", "path": "anywhere"}]
        )
        result = AssertionGrader().grade(task, tmp_path)
        assert not result.assertions[0].passed
        assert "unknown kind" in result.assertions[0].detail

    def test_empty_task_grades_as_pass(self, tmp_path: Path) -> None:
        # Vacuous truth: no assertions = passed (binary AND over empty set).
        result = AssertionGrader().grade([], tmp_path)
        assert result.passed
        assert result.n_total == 0


class TestGradeResultSerialization:
    def test_to_dict_round_trip_shape(self, tmp_path: Path) -> None:
        (tmp_path / "f.txt").write_text("ok")
        result = AssertionGrader().grade(
            _make_task(
                task_id="t1",
                assertions=[
                    {"kind": "file_exists", "path": "f.txt"},
                    {"kind": "file_not_exists", "path": "f.txt"},  # fail
                ],
            ),
            tmp_path,
        )
        d = result.to_dict()
        assert d["task_id"] == "t1"
        assert d["passed"] is False
        assert d["n_passed"] == 1
        assert d["n_total"] == 2
        assert isinstance(d["assertions"], list)
        assert all("kind" in a and "passed" in a for a in d["assertions"])

    def test_assertion_result_to_dict(self) -> None:
        a = AssertionResult("file_exists", "x.txt", True, "")
        assert a.to_dict() == {
            "kind": "file_exists",
            "path": "x.txt",
            "passed": True,
            "detail": "",
        }

    def test_grade_result_is_immutable(self) -> None:
        result = GradeResult(
            task_id="x",
            passed=True,
            n_passed=0,
            n_total=0,
            assertions=[],
        )
        with pytest.raises(AttributeError):
            result.task_id = "y"  # type: ignore[misc]


# --- pass_at_k_estimator + PassAtK --------------------------------------


class TestPassAtKEstimator:
    def test_all_pass_returns_one(self) -> None:
        assert pass_at_k_estimator(n=8, c=8, k=1) == 1.0
        assert pass_at_k_estimator(n=8, c=8, k=8) == 1.0

    def test_no_pass_returns_zero(self) -> None:
        assert pass_at_k_estimator(n=8, c=0, k=1) == 0.0
        assert pass_at_k_estimator(n=8, c=0, k=8) == 0.0

    def test_pass_at_1_equals_c_over_n(self) -> None:
        # pass@1 unbiased estimator collapses to c/n
        assert pass_at_k_estimator(n=10, c=3, k=1) == pytest.approx(0.3)
        assert pass_at_k_estimator(n=8, c=5, k=1) == pytest.approx(5 / 8)

    def test_pass_at_k_when_k_equals_n(self) -> None:
        # k == n: probability that any of the n samples pass = 1 if c >= 1
        assert pass_at_k_estimator(n=8, c=1, k=8) == 1.0
        assert pass_at_k_estimator(n=8, c=4, k=8) == 1.0

    def test_canonical_value(self) -> None:
        # n=10, c=2, k=4: 1 - C(8,4)/C(10,4) = 1 - 70/210 = 2/3.
        # Unbiased estimator math byte-identical to Chen et al. 2021.
        assert pass_at_k_estimator(n=10, c=2, k=4) == pytest.approx(2 / 3)

    def test_validates_inputs(self) -> None:
        with pytest.raises(ValueError, match="k and n must be"):
            pass_at_k_estimator(n=0, c=0, k=1)
        with pytest.raises(ValueError, match="k and n must be"):
            pass_at_k_estimator(n=8, c=0, k=0)
        with pytest.raises(ValueError, match="0 <= c <= n"):
            pass_at_k_estimator(n=8, c=-1, k=1)
        with pytest.raises(ValueError, match="0 <= c <= n"):
            pass_at_k_estimator(n=8, c=9, k=1)


def _trivial_grader(text: str, problem: dict[str, Any]) -> bool:
    """Grader returns True iff sample contains the problem's expected token."""
    return problem["expect"] in text


class TestPassAtKScore:
    def test_basic_two_problems_two_samples(self) -> None:
        problems = [
            {"task_id": "T0", "expect": "yes"},
            {"task_id": "T1", "expect": "ok"},
        ]
        # T0: 1/2 pass, T1: 2/2 pass
        samples = [
            ["yes I think so", "no I disagree"],
            ["ok", "ok again"],
        ]
        result = PassAtK(ks=(1, 2)).score(problems, samples, _trivial_grader)
        assert result.n_problems == 2
        assert result.samples_per_problem == 2
        # pass@1: T0 = 1/2, T1 = 2/2 → mean = 0.75
        assert result.pass_at[1] == pytest.approx(0.75)
        # pass@2: T0 = 1.0 (one of two passed at k=2), T1 = 1.0 → mean = 1.0
        assert result.pass_at[2] == pytest.approx(1.0)

    def test_per_task_rows_carry_task_id_and_passed(self) -> None:
        problems = [{"task_id": "T0", "expect": "yes"}]
        samples = [["yes", "no", "yes"]]
        result = PassAtK(ks=(1,)).score(problems, samples, _trivial_grader)
        assert len(result.per_task) == 1
        assert result.per_task[0]["task_id"] == "T0"
        assert result.per_task[0]["n"] == 3
        assert result.per_task[0]["passed"] == 2

    def test_extras_fn_attaches_metadata(self) -> None:
        problems = [{"task_id": "T0", "expect": "yes"}]
        samples = [["yes longish prediction"]]

        def extras(problem: dict[str, Any], samples: Sequence[str]) -> dict[str, Any]:
            return {"first_pred_tail": samples[0][-10:]}

        result = PassAtK(ks=(1,)).score(
            problems, samples, _trivial_grader, extras_fn=extras
        )
        assert result.per_task[0]["first_pred_tail"] == "prediction"

    def test_empty_problems_returns_zero(self) -> None:
        result = PassAtK(ks=(1, 8)).score([], [], _trivial_grader)
        assert result.n_problems == 0
        assert result.pass_at[1] == 0.0
        assert result.pass_at[8] == 0.0

    def test_validates_length_mismatch(self) -> None:
        with pytest.raises(ValueError, match="length mismatch"):
            PassAtK(ks=(1,)).score(
                [{"task_id": "T0", "expect": "x"}],
                [["x"], ["y"]],  # 2 rows, 1 problem
                _trivial_grader,
            )

    def test_validates_uneven_sample_counts(self) -> None:
        with pytest.raises(ValueError, match="same number of samples"):
            PassAtK(ks=(1,)).score(
                [
                    {"task_id": "T0", "expect": "x"},
                    {"task_id": "T1", "expect": "x"},
                ],
                [["x", "x"], ["x"]],
                _trivial_grader,
            )

    def test_validates_k_exceeds_samples(self) -> None:
        with pytest.raises(ValueError, match="exceeds samples"):
            PassAtK(ks=(8,)).score(
                [{"task_id": "T0", "expect": "x"}],
                [["x", "x"]],
                _trivial_grader,
            )

    def test_validates_empty_ks(self) -> None:
        with pytest.raises(ValueError, match="ks cannot be empty"):
            PassAtK(ks=()).score(
                [{"task_id": "T0", "expect": "x"}],
                [["x"]],
                _trivial_grader,
            )


class TestPassAtKFromRows:
    def test_basic(self) -> None:
        rows = [
            {"task_id": "T0", "n": 8, "passed": 5},
            {"task_id": "T1", "n": 8, "passed": 0},
            {"task_id": "T2", "n": 8, "passed": 8},
        ]
        result = PassAtK(ks=(1, 8)).from_rows(rows)
        assert result.n_problems == 3
        assert result.samples_per_problem == 8
        # pass@1: 5/8 + 0/8 + 8/8 = 1.625 → mean = 0.5417
        assert result.pass_at[1] == pytest.approx((5 / 8 + 0 + 1.0) / 3, abs=1e-3)
        # pass@8: 1 + 0 + 1 = 2 → mean = 2/3
        assert result.pass_at[8] == pytest.approx(2 / 3)

    def test_validates_inconsistent_n(self) -> None:
        with pytest.raises(ValueError, match="inconsistent sample counts"):
            PassAtK(ks=(1,)).from_rows(
                [
                    {"task_id": "T0", "n": 8, "passed": 1},
                    {"task_id": "T1", "n": 4, "passed": 1},
                ]
            )

    def test_empty_rows(self) -> None:
        result = PassAtK(ks=(1,)).from_rows([])
        assert result.n_problems == 0
        assert result.pass_at[1] == 0.0


class TestPassAtKResult:
    def test_to_dict_round_trip(self) -> None:
        result = PassAtKResult(
            n_problems=2,
            samples_per_problem=8,
            per_task=[{"task_id": "T0", "n": 8, "passed": 4}],
            pass_at={1: 0.5, 8: 0.84156789},
        )
        d = result.to_dict()
        assert d["n_problems"] == 2
        assert d["samples_per_problem"] == 8
        assert d["pass_at"] == {"pass@1": 0.5, "pass@8": 0.8416}
        assert d["per_task"][0]["task_id"] == "T0"

    def test_immutable(self) -> None:
        result = PassAtKResult(
            n_problems=0,
            samples_per_problem=0,
            per_task=[],
            pass_at={1: 0.0},
        )
        with pytest.raises(AttributeError):
            result.n_problems = 99  # type: ignore[misc]


# --- AgentRun + TurnDetail + summarize_agent_runs ------------------------


_DEFAULT_TURNS: list[dict[str, Any]] = [
    {
        "turn": 1,
        "action": "tool",
        "duration": 4.21,
        "input_tokens": 1024,
        "output_tokens": 256,
        "papers_retrieved_this_turn": 5,
    },
    {
        "turn": 2,
        "action": "synthesis",
        "duration": 3.10,
        "input_tokens": 2048,
        "output_tokens": 512,
    },
]
_DEFAULT_CANDIDATES: list[dict[str, Any]] = [{"title": "Cand1"}, {"title": "Cand2"}]


def _autoresearch_record(
    *,
    arxiv_id: str = "2602.01234",
    status: str = "finished",
    total_time: float = 12.5,
    turn_details: list[dict[str, Any]] | None = None,
    final_candidates: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build an AutoResearchBench-shaped JSON record for tests.

    Use ``turn_details=[]`` / ``final_candidates=[]`` to override with empty
    lists; pass ``None`` (the default) to get the canonical fixture.
    """
    return {
        "input_data": {
            "arxiv_id": arxiv_id,
            "answer": ["Some Reference Title"],
        },
        "inference_results": [
            {
                "status": status,
                "total_time": total_time,
                "turn_details": _DEFAULT_TURNS if turn_details is None else turn_details,
                "final_candidates": (
                    _DEFAULT_CANDIDATES if final_candidates is None else final_candidates
                ),
            }
        ],
    }


class TestTurnDetail:
    def test_basic_dict(self) -> None:
        t = TurnDetail(
            turn=1,
            action="tool",
            duration_s=4.21,
            input_tokens=1024,
            output_tokens=256,
            extras={"papers": 5},
        )
        d = t.to_dict()
        assert d["turn"] == 1
        assert d["action"] == "tool"
        assert d["duration_s"] == 4.21
        assert d["input_tokens"] == 1024
        assert d["output_tokens"] == 256
        assert d["extras"] == {"papers": 5}

    def test_empty_extras_omitted(self) -> None:
        t = TurnDetail(turn=1, action="x", duration_s=0.5)
        assert "extras" not in t.to_dict()


class TestAgentRunFromRecord:
    def test_autoresearch_default_shape(self) -> None:
        raw = _autoresearch_record()
        run = AgentRun.from_record(raw)
        assert run.question_id == "2602.01234"
        assert run.status == "finished"
        assert run.wall_seconds == 12.5
        assert run.n_turns == 2
        assert run.n_candidates == 2
        assert run.turns[0].action == "tool"
        assert run.turns[0].duration_s == 4.21
        assert run.turns[0].extras == {"papers_retrieved_this_turn": 5}
        assert run.turns[1].action == "synthesis"

    def test_missing_inference_results_recovers(self) -> None:
        # Some pre-run / failed records have no inference_results at all.
        raw = {"input_data": {"arxiv_id": "2602.99999"}}
        run = AgentRun.from_record(raw)
        assert run.question_id == "2602.99999"
        assert run.status == ""
        assert run.wall_seconds == 0.0
        assert run.n_turns == 0
        assert run.n_candidates == 0

    def test_custom_field_overrides(self) -> None:
        # Synthetic shape: top-level question_id, no inference_results wrapper.
        raw = {
            "task_id": "TASK-007",
            "result_status": "ok",
            "elapsed": 9.0,
            "steps": [
                {"turn": 1, "action": "search", "duration": 1.0, "output_tokens": 50},
            ],
            "outputs": [{"x": 1}],
        }
        run = AgentRun.from_record(
            raw,
            question_id_field="task_id",
            question_id_path=(),
            inference_path=(),
            status_field="result_status",
            wall_field="elapsed",
            turns_field="steps",
            candidates_field="outputs",
        )
        assert run.question_id == "TASK-007"
        assert run.status == "ok"
        assert run.n_turns == 1
        assert run.n_candidates == 1
        assert run.turns[0].action == "search"
        assert run.turns[0].output_tokens == 50

    def test_supports_duration_s_alias(self) -> None:
        # Some agent loops emit duration_s instead of duration.
        raw = _autoresearch_record(
            turn_details=[
                {"turn": 1, "action": "tool", "duration_s": 0.75, "input_tokens": 100}
            ]
        )
        run = AgentRun.from_record(raw)
        assert run.turns[0].duration_s == 0.75


class TestAgentRunDerivations:
    def test_tool_calls_and_errors(self) -> None:
        raw = _autoresearch_record(
            turn_details=[
                {"turn": 1, "action": "tool", "duration": 1.0},
                {"turn": 2, "action": "error", "duration": 0.5},
                {"turn": 3, "action": "tool", "duration": 1.5},
                {"turn": 4, "action": "synthesis", "duration": 2.0},
            ]
        )
        run = AgentRun.from_record(raw)
        assert run.tool_calls() == 2
        assert run.tool_format_errors() == 1

    def test_total_tokens(self) -> None:
        raw = _autoresearch_record(
            turn_details=[
                {"turn": 1, "action": "tool", "duration": 0.1, "input_tokens": 1000, "output_tokens": 100},
                {"turn": 2, "action": "tool", "duration": 0.1, "input_tokens": 2000, "output_tokens": 200},
                {"turn": 3, "action": "tool", "duration": 0.1, "input_tokens": None, "output_tokens": None},
            ]
        )
        run = AgentRun.from_record(raw)
        assert run.total_input_tokens() == 3000
        assert run.total_output_tokens() == 300

    def test_succeeded(self) -> None:
        ok = AgentRun.from_record(_autoresearch_record(status="finished"))
        assert ok.succeeded()
        no_cands = AgentRun.from_record(
            _autoresearch_record(status="finished", final_candidates=[])
        )
        assert not no_cands.succeeded()
        not_finished = AgentRun.from_record(
            _autoresearch_record(status="context_overflow")
        )
        assert not not_finished.succeeded()


class TestAgentRunFromJsonl:
    def test_basic_jsonl_parse(self, tmp_path: Path) -> None:
        path = tmp_path / "runs.jsonl"
        path.write_text(
            "\n".join(
                json.dumps(_autoresearch_record(arxiv_id=f"2602.{i:05d}"))
                for i in range(3)
            )
            + "\n"
        )
        runs = AgentRun.from_jsonl(path)
        assert len(runs) == 3
        assert runs[0].question_id == "2602.00000"
        assert runs[2].question_id == "2602.00002"

    def test_skips_blank_and_malformed_lines(self, tmp_path: Path) -> None:
        path = tmp_path / "messy.jsonl"
        path.write_text(
            json.dumps(_autoresearch_record(arxiv_id="2602.A"))
            + "\n\n"
            + "{not valid json\n"
            + json.dumps(_autoresearch_record(arxiv_id="2602.B"))
            + "\n"
        )
        runs = AgentRun.from_jsonl(path)
        assert len(runs) == 2
        assert {r.question_id for r in runs} == {"2602.A", "2602.B"}

    def test_custom_parser(self, tmp_path: Path) -> None:
        from functools import partial
        path = tmp_path / "alt.jsonl"
        path.write_text(
            json.dumps(
                {
                    "task_id": "T1",
                    "result_status": "ok",
                    "elapsed": 3.0,
                    "steps": [],
                    "outputs": [{}],
                }
            )
            + "\n"
        )
        parser = partial(
            AgentRun.from_record,
            question_id_field="task_id",
            question_id_path=(),
            inference_path=(),
            status_field="result_status",
            wall_field="elapsed",
            turns_field="steps",
            candidates_field="outputs",
        )
        runs = AgentRun.from_jsonl(path, parser=parser)
        assert runs[0].question_id == "T1"


class TestAgentRunSerialization:
    def test_to_dict_compact(self) -> None:
        raw = _autoresearch_record()
        run = AgentRun.from_record(raw)
        d = run.to_dict()
        assert d["question_id"] == "2602.01234"
        assert d["n_turns"] == 2
        assert d["tool_calls"] == 1
        assert d["input_tokens"] == 1024 + 2048
        assert "raw" not in d

    def test_to_dict_with_raw(self) -> None:
        raw = _autoresearch_record()
        run = AgentRun.from_record(raw)
        d = run.to_dict(include_raw=True)
        assert d["raw"] == raw


class TestSummarizeAgentRuns:
    def test_empty_runs(self) -> None:
        s = summarize_agent_runs([])
        assert s["n_questions"] == 0
        assert s["status_counts"] == {}

    def test_basic_aggregate(self) -> None:
        runs = [
            AgentRun.from_record(_autoresearch_record(status="finished", total_time=10.0)),
            AgentRun.from_record(
                _autoresearch_record(status="finished", total_time=20.0, final_candidates=[])
            ),
            AgentRun.from_record(_autoresearch_record(status="context_overflow", total_time=5.0)),
        ]
        s = summarize_agent_runs(runs, label="llama-3.1-8b")
        assert s["label"] == "llama-3.1-8b"
        assert s["n_questions"] == 3
        assert s["n_succeeded"] == 1  # status=finished AND candidates>0
        assert s["status_counts"] == {"context_overflow": 1, "finished": 2}
        assert s["wall_seconds"]["mean"] == pytest.approx(11.67, abs=0.01)
        assert s["wall_seconds"]["min"] == 5.0
        assert s["wall_seconds"]["max"] == 20.0


# --- MatchedBaseComparison ----------------------------------------------


def _trajectory_record(
    *,
    task_id: str,
    passed: bool,
    n_passed: int,
    n_total: int,
    assertions: list[dict[str, Any]] | None = None,
    stopped: str = "task_complete",
    n_turns: int = 5,
    wall_seconds: float = 8.0,
) -> dict[str, Any]:
    """Build one rollout trajectory record matching clawgym-on-spark's shape."""
    if assertions is None:
        # Default: synthesize n_total assertions of which n_passed pass, kind=file_exists.
        assertions = [
            {"kind": "file_exists", "passed": True} for _ in range(n_passed)
        ] + [
            {"kind": "file_exists", "passed": False}
            for _ in range(n_total - n_passed)
        ]
    return {
        "task_id": task_id,
        "final_grade": {
            "passed": passed,
            "n_passed": n_passed,
            "n_total": n_total,
            "assertions": assertions,
        },
        "stopped": stopped,
        "n_turns": n_turns,
        "wall_seconds": wall_seconds,
    }


class TestMatchedBaseComparisonStats:
    def test_basic_aggregation(self) -> None:
        rows = [
            _trajectory_record(
                task_id="synth-ml-engineer-00",
                passed=True,
                n_passed=5,
                n_total=5,
                n_turns=4,
                wall_seconds=10.0,
            ),
            _trajectory_record(
                task_id="synth-ml-engineer-01",
                passed=False,
                n_passed=2,
                n_total=4,
                n_turns=12,
                wall_seconds=30.0,
            ),
            _trajectory_record(
                task_id="synth-academic-author-00",
                passed=True,
                n_passed=3,
                n_total=3,
                n_turns=3,
                wall_seconds=8.0,
            ),
        ]
        s = MatchedBaseComparison().stats(rows)
        assert s.n == 3
        assert s.n_passed == 2
        assert s.n_assertions_passed == 10
        assert s.n_assertions_total == 12
        assert s.task_pass_pct() == pytest.approx(2 / 3 * 100)
        assert s.assertion_pass_pct() == pytest.approx(10 / 12 * 100)
        assert s.mean_turns == pytest.approx((4 + 12 + 3) / 3)
        assert s.mean_wall == pytest.approx((10 + 30 + 8) / 3)
        assert "ml-engineer" in s.by_group
        assert "academic-author" in s.by_group
        assert s.by_group["ml-engineer"]["n"] == 2
        assert s.by_group["ml-engineer"]["passed"] == 1
        assert s.by_kind["file_exists"]["n"] == 12
        assert s.by_kind["file_exists"]["passed"] == 10
        assert s.stops == {"task_complete": 3}

    def test_empty_rows(self) -> None:
        s = MatchedBaseComparison().stats([])
        assert s.n == 0
        assert s.task_pass_pct() == 0.0
        assert s.assertion_pass_pct() == 0.0

    def test_no_group_extractor(self) -> None:
        rows = [
            _trajectory_record(
                task_id="anything", passed=True, n_passed=1, n_total=1
            )
        ]
        cmp = MatchedBaseComparison(group_extractor=None)
        s = cmp.stats(rows)
        assert s.by_group == {}

    def test_jsonl_path_input(self, tmp_path: Path) -> None:
        path = tmp_path / "traj.jsonl"
        rows = [
            _trajectory_record(
                task_id="synth-ml-engineer-00", passed=True, n_passed=2, n_total=2
            ),
            _trajectory_record(
                task_id="synth-ml-engineer-01", passed=False, n_passed=0, n_total=3
            ),
        ]
        path.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
        s = MatchedBaseComparison().stats(path)
        assert s.n == 2
        assert s.n_passed == 1

    def test_jsonl_skips_blank_and_malformed(self, tmp_path: Path) -> None:
        path = tmp_path / "messy.jsonl"
        good = _trajectory_record(
            task_id="synth-ml-engineer-00", passed=True, n_passed=1, n_total=1
        )
        path.write_text(
            json.dumps(good) + "\n\n{not valid\n" + json.dumps(good) + "\n"
        )
        s = MatchedBaseComparison().stats(path)
        assert s.n == 2

    def test_short_task_id_falls_back_to_full(self) -> None:
        rows = [
            _trajectory_record(task_id="x", passed=True, n_passed=1, n_total=1)
        ]
        s = MatchedBaseComparison().stats(rows)
        assert "x" in s.by_group


class TestMatchedBaseComparisonCompare:
    def test_phase5_shape_overall_deltas(self) -> None:
        # Mirror the article's headline: SFT has more assertions passed
        # but takes more turns + more wall.
        baseline = [
            _trajectory_record(
                task_id="synth-ml-engineer-00",
                passed=False,
                n_passed=1,
                n_total=5,
                n_turns=4,
                wall_seconds=12.0,
                stopped="task_complete",
            ),
            _trajectory_record(
                task_id="synth-ml-engineer-01",
                passed=True,
                n_passed=4,
                n_total=4,
                n_turns=3,
                wall_seconds=8.0,
                stopped="task_complete",
            ),
        ]
        sft = [
            _trajectory_record(
                task_id="synth-ml-engineer-00",
                passed=True,
                n_passed=5,
                n_total=5,
                n_turns=12,
                wall_seconds=28.0,
                stopped="max_turns",
            ),
            _trajectory_record(
                task_id="synth-ml-engineer-01",
                passed=True,
                n_passed=4,
                n_total=4,
                n_turns=12,
                wall_seconds=29.0,
                stopped="max_turns",
            ),
        ]
        result = MatchedBaseComparison().compare(baseline, sft)
        # Task pass: base 1/2 (50%) → sft 2/2 (100%) → +50pp
        assert result.overall_delta["delta_task_pp"] == pytest.approx(50.0)
        # Per-assertion: base 5/9 (55.6%) → sft 9/9 (100%) → +44.4pp
        assert result.overall_delta["delta_assertion_pp"] == pytest.approx(
            44.44, abs=0.01
        )
        # Mean turns: 3.5 → 12 = +8.5
        assert result.overall_delta["delta_mean_turns"] == pytest.approx(8.5)
        # Per-group has one entry (ml-engineer)
        assert len(result.per_group) == 1
        assert result.per_group[0]["group"] == "ml-engineer"
        assert result.per_group[0]["delta_task_pp"] == pytest.approx(50.0)
        # Per-kind has one entry (file_exists default)
        assert len(result.per_kind) == 1
        assert result.per_kind[0]["delta_pp"] == pytest.approx(44.44, abs=0.01)

    def test_per_group_handles_disjoint_groups(self) -> None:
        # baseline-only persona + candidate-only persona — both should appear.
        baseline = [
            _trajectory_record(
                task_id="synth-only-base-00", passed=True, n_passed=1, n_total=1
            )
        ]
        candidate = [
            _trajectory_record(
                task_id="synth-only-cand-00", passed=False, n_passed=0, n_total=1
            )
        ]
        result = MatchedBaseComparison().compare(baseline, candidate)
        groups = {r["group"] for r in result.per_group}
        assert groups == {"only-base", "only-cand"}

    def test_per_kind_groups_assertions_correctly(self) -> None:
        baseline = [
            _trajectory_record(
                task_id="synth-x-00",
                passed=False,
                n_passed=1,
                n_total=2,
                assertions=[
                    {"kind": "file_exists", "passed": True},
                    {"kind": "file_not_exists", "passed": False},
                ],
            )
        ]
        candidate = [
            _trajectory_record(
                task_id="synth-x-00",
                passed=True,
                n_passed=2,
                n_total=2,
                assertions=[
                    {"kind": "file_exists", "passed": True},
                    {"kind": "file_not_exists", "passed": True},
                ],
            )
        ]
        result = MatchedBaseComparison().compare(baseline, candidate)
        per_kind = {r["kind"]: r for r in result.per_kind}
        assert per_kind["file_exists"]["delta_pp"] == 0.0
        assert per_kind["file_not_exists"]["delta_pp"] == pytest.approx(100.0)

    def test_report_renders_markdown(self) -> None:
        baseline = [
            _trajectory_record(
                task_id="synth-x-00", passed=False, n_passed=0, n_total=1
            )
        ]
        candidate = [
            _trajectory_record(
                task_id="synth-x-00", passed=True, n_passed=1, n_total=1
            )
        ]
        result = MatchedBaseComparison().compare(baseline, candidate)
        rep = result.report()
        assert "Matched-base comparison" in rep
        assert "task pass" in rep
        assert "+100.0 pp" in rep

    def test_to_dict_round_trip(self) -> None:
        baseline = [
            _trajectory_record(
                task_id="synth-x-00", passed=True, n_passed=1, n_total=1
            )
        ]
        candidate = baseline
        result = MatchedBaseComparison().compare(baseline, candidate)
        d = result.to_dict()
        assert "baseline" in d
        assert "candidate" in d
        assert d["overall_delta"]["delta_task_pp"] == 0.0
        # Round-trip must be JSON-serializable
        json.dumps(d)


class TestGroupStatsImmutable:
    def test_immutable(self) -> None:
        s = GroupStats(
            n=0,
            n_passed=0,
            n_assertions_passed=0,
            n_assertions_total=0,
            by_group={},
            by_kind={},
            stops={},
            mean_turns=0.0,
            mean_wall=0.0,
        )
        with pytest.raises(AttributeError):
            s.n = 1  # type: ignore[misc]
