# Copyright 2026 Manav Sehgal
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for `fieldkit.eval.VerticalBench` — the Spark-overlay vertical
scorer added in v0.4.x for Orionfold vertical-curator quants. Offline only.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from fieldkit.eval import (
    Bench,
    VerticalBench,
    VerticalQA,
    contains,
    exact_match,
    irac_structure,
    mcq_letter,
    numeric_match,
    office_action_argument,
    patent_claim_validity,
    prior_art_relevance,
)
from fieldkit.eval.vertical import (
    PATENT_STRATEGIST_SCORER_FNS,
    PATENT_STRATEGIST_SCORERS,
)


# --- Scorers -----------------------------------------------------------------


class TestExactMatch:
    def test_identical_returns_1(self) -> None:
        assert exact_match("yes", "yes") == 1.0

    def test_case_insensitive(self) -> None:
        assert exact_match("YES", "yes") == 1.0

    def test_whitespace_insensitive(self) -> None:
        assert exact_match("  yes\n", "yes") == 1.0

    def test_mismatch_returns_0(self) -> None:
        assert exact_match("no", "yes") == 0.0

    def test_substring_does_not_match(self) -> None:
        assert exact_match("yes it does", "yes") == 0.0


class TestContains:
    def test_substring_returns_1(self) -> None:
        assert contains("the answer is yes", "yes") == 1.0

    def test_case_insensitive(self) -> None:
        assert contains("THE ANSWER IS YES", "yes") == 1.0

    def test_missing_returns_0(self) -> None:
        assert contains("the answer is no", "yes") == 0.0

    def test_empty_expected_returns_0(self) -> None:
        assert contains("anything", "") == 0.0


class TestNumericMatch:
    def test_exact_number(self) -> None:
        assert numeric_match("the answer is 1234.5", "1234.5") == 1.0

    def test_within_default_tolerance(self) -> None:
        # 1% tolerance — 1234.5 ± 12.345
        assert numeric_match("1240", "1234.5") == 1.0

    def test_outside_default_tolerance(self) -> None:
        assert numeric_match("1300", "1234.5") == 0.0

    def test_comma_stripping(self) -> None:
        assert numeric_match("Revenue was $1,234,567", "1234567") == 1.0

    def test_first_number_wins(self) -> None:
        # First number in the predicted string wins — here "100", not "200".
        assert numeric_match("Revenue was 100, costs were 200", "100") == 1.0

    def test_no_number_in_predicted_returns_0(self) -> None:
        assert numeric_match("the data does not specify", "42") == 0.0

    def test_no_number_in_expected_returns_0(self) -> None:
        assert numeric_match("42", "no answer") == 0.0

    def test_custom_tolerance(self) -> None:
        # 10% tolerance — 100 ± 10
        assert numeric_match("109", "100", rel_tolerance=0.1) == 1.0
        assert numeric_match("111", "100", rel_tolerance=0.1) == 0.0

    def test_negative_numbers(self) -> None:
        assert numeric_match("the loss was -50.0M", "-50") == 1.0

    def test_zero_reference_uses_absolute_tolerance(self) -> None:
        # When expected is exactly 0, we treat tolerance as absolute (|pn| <= rel_tol).
        assert numeric_match("0.005", "0", rel_tolerance=0.01) == 1.0
        assert numeric_match("0.5", "0", rel_tolerance=0.01) == 0.0


# --- JSONL loader ------------------------------------------------------------


def _write_jsonl(tmp: Path, name: str, rows: list[dict]) -> Path:
    p = tmp / name
    p.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    return p


class TestFromJsonl:
    def test_financebench_autodetect(self, tmp_path: Path) -> None:
        rows = [
            {
                "financebench_id": "fb-001",
                "question": "What was Pepsi's revenue in FY2022?",
                "gold_standard": "79.47 billion",
                "answer": "Per the 10-K, revenue was approximately $79.47 billion.",
                "company": "Pepsi",
                "doc_period": "FY2022",
                "doc_type": "10-K",
                "question_type": "numerical",
            }
        ]
        p = _write_jsonl(tmp_path, "fb.jsonl", rows)
        vb = VerticalBench.from_jsonl(p)
        assert len(vb.questions) == 1
        q = vb.questions[0]
        assert q.qid == "fb-001"
        assert q.expected == "79.47 billion"
        assert q.tags["company"] == "Pepsi"
        assert q.tags["doc_period"] == "FY2022"
        # numeric_match is the default for financebench
        assert vb.scorer.__name__ == "numeric_match"

    def test_legalbench_autodetect(self, tmp_path: Path) -> None:
        rows = [
            {
                "id": "lb-001",
                "text": "Is this clause a non-compete?",
                "answer": "yes",
                "task": "contract_nli",
            }
        ]
        p = _write_jsonl(tmp_path, "lb.jsonl", rows)
        vb = VerticalBench.from_jsonl(p)
        assert len(vb.questions) == 1
        q = vb.questions[0]
        assert q.qid == "lb-001"
        assert q.question == "Is this clause a non-compete?"
        assert q.expected == "yes"
        assert q.tags["task"] == "contract_nli"
        # exact_match is the default for legalbench
        assert vb.scorer.__name__ == "exact_match"

    def test_generic_fallback(self, tmp_path: Path) -> None:
        rows = [
            {"question": "2+2?", "answer": "4"},
            {"prompt": "3+3?", "expected": "6"},
        ]
        p = _write_jsonl(tmp_path, "generic.jsonl", rows)
        vb = VerticalBench.from_jsonl(p)
        assert len(vb.questions) == 2
        assert vb.questions[0].question == "2+2?"
        assert vb.questions[0].expected == "4"
        assert vb.questions[1].question == "3+3?"
        assert vb.questions[1].expected == "6"

    def test_limit_caps_rows(self, tmp_path: Path) -> None:
        rows = [{"question": f"q{i}", "answer": str(i)} for i in range(10)]
        p = _write_jsonl(tmp_path, "many.jsonl", rows)
        vb = VerticalBench.from_jsonl(p, limit=3)
        assert len(vb.questions) == 3

    def test_missing_required_fields_dropped(self, tmp_path: Path) -> None:
        rows = [
            {"question": "q1", "answer": "a1"},
            {"question": "q2"},  # missing answer
            {"answer": "a3"},  # missing question
            {"question": "q4", "answer": "a4"},
        ]
        p = _write_jsonl(tmp_path, "partial.jsonl", rows)
        vb = VerticalBench.from_jsonl(p)
        assert len(vb.questions) == 2
        assert {q.expected for q in vb.questions} == {"a1", "a4"}

    def test_corrupt_lines_skipped(self, tmp_path: Path) -> None:
        p = tmp_path / "corrupt.jsonl"
        p.write_text(
            '{"question": "good", "answer": "yes"}\n'
            "not json at all\n"
            '{"question": "also good", "answer": "no"}\n'
        )
        vb = VerticalBench.from_jsonl(p)
        assert len(vb.questions) == 2

    def test_blank_lines_skipped(self, tmp_path: Path) -> None:
        p = tmp_path / "blanks.jsonl"
        p.write_text(
            '\n\n{"question": "q", "answer": "a"}\n\n'
        )
        vb = VerticalBench.from_jsonl(p)
        assert len(vb.questions) == 1

    def test_format_override(self, tmp_path: Path) -> None:
        # A row that looks like generic (no financebench_id) but caller forces financebench.
        rows = [{"question": "q", "gold_standard": "g"}]
        p = _write_jsonl(tmp_path, "force.jsonl", rows)
        vb = VerticalBench.from_jsonl(p, format="financebench")
        assert len(vb.questions) == 1
        assert vb.questions[0].expected == "g"

    def test_custom_scorer_override(self, tmp_path: Path) -> None:
        rows = [{"question": "q", "answer": "a"}]
        p = _write_jsonl(tmp_path, "custom.jsonl", rows)
        vb = VerticalBench.from_jsonl(p, scorer=contains)
        assert vb.scorer is contains

    def test_name_defaults_to_stem(self, tmp_path: Path) -> None:
        rows = [{"question": "q", "answer": "a"}]
        p = _write_jsonl(tmp_path, "financebench-mini.jsonl", rows)
        vb = VerticalBench.from_jsonl(p)
        assert vb.name == "financebench-mini"


# --- Open-book mode (v0.4.1+) -----------------------------------------------


def _fb_row(qid: str, question: str, gold: str, evidence_text: str, **extra) -> dict:
    return {
        "financebench_id": qid,
        "question": question,
        "gold_standard": gold,
        "doc_name": extra.get("doc_name", "ACME_2024_10-K"),
        "company": extra.get("company", "ACME"),
        "doc_period": extra.get("doc_period", "FY2024"),
        "question_type": extra.get("question_type", "metrics-generated"),
        "evidence": [{"evidence_text": evidence_text}] if evidence_text else [],
    }


class TestOpenBook:
    def test_financebench_auto_open_book(self, tmp_path: Path) -> None:
        # No explicit open_book — default for financebench is True.
        rows = [_fb_row("fb-1", "What was revenue?", "1234", "Revenue: $1,234M")]
        p = _write_jsonl(tmp_path, "fb.jsonl", rows)
        vb = VerticalBench.from_jsonl(p)
        assert len(vb.questions) == 1
        q = vb.questions[0]
        # Evidence is now in the question prompt.
        assert "Revenue: $1,234M" in q.question
        assert "Question: What was revenue?" in q.question
        assert "ACME_2024_10-K" in q.question
        # Expected is unchanged.
        assert q.expected == "1234"

    def test_explicit_open_book_false_keeps_closed(self, tmp_path: Path) -> None:
        rows = [_fb_row("fb-1", "What was revenue?", "1234", "Revenue: $1,234M")]
        p = _write_jsonl(tmp_path, "fb.jsonl", rows)
        vb = VerticalBench.from_jsonl(p, open_book=False)
        assert vb.questions[0].question == "What was revenue?"

    def test_open_book_no_evidence_falls_back(self, tmp_path: Path) -> None:
        # A financebench row missing evidence — open_book=True is a no-op.
        rows = [_fb_row("fb-1", "What was revenue?", "1234", "")]
        p = _write_jsonl(tmp_path, "fb.jsonl", rows)
        vb = VerticalBench.from_jsonl(p)
        assert vb.questions[0].question == "What was revenue?"

    def test_legalbench_open_book_is_noop(self, tmp_path: Path) -> None:
        # No standard evidence field — open_book=True doesn't change the question.
        rows = [{"id": "lb-1", "text": "Is X enforceable?", "answer": "yes"}]
        p = _write_jsonl(tmp_path, "lb.jsonl", rows)
        vb = VerticalBench.from_jsonl(p, open_book=True)
        assert vb.questions[0].question == "Is X enforceable?"

    def test_open_book_default_off_for_legalbench(self, tmp_path: Path) -> None:
        # Auto-default for non-financebench is False, even if a stray evidence
        # field is present.
        rows = [
            {
                "id": "lb-1",
                "text": "Is X enforceable?",
                "answer": "yes",
                "evidence": [{"evidence_text": "Section 3.1 prohibits X."}],
            }
        ]
        p = _write_jsonl(tmp_path, "lb.jsonl", rows)
        vb = VerticalBench.from_jsonl(p)
        # No prepending — only financebench triggers open-book by default.
        assert vb.questions[0].question == "Is X enforceable?"

    def test_evidence_text_as_strings(self, tmp_path: Path) -> None:
        # Some pre-flattened dumps put evidence as list-of-strings.
        rows = [
            {
                "financebench_id": "fb-1",
                "question": "q",
                "gold_standard": "g",
                "evidence": ["chunk-1", "chunk-2"],
            }
        ]
        p = _write_jsonl(tmp_path, "fb.jsonl", rows)
        vb = VerticalBench.from_jsonl(p)
        assert "chunk-1" in vb.questions[0].question
        assert "chunk-2" in vb.questions[0].question

    def test_subset_filter_financebench(self, tmp_path: Path) -> None:
        rows = [
            _fb_row("fb-1", "q1", "1", "ev-1", question_type="metrics-generated"),
            _fb_row("fb-2", "q2", "2", "ev-2", question_type="domain-relevant"),
            _fb_row("fb-3", "q3", "3", "ev-3", question_type="metrics-generated"),
        ]
        p = _write_jsonl(tmp_path, "fb.jsonl", rows)
        vb = VerticalBench.from_jsonl(p, subset="metrics-generated")
        assert len(vb.questions) == 2
        assert {q.qid for q in vb.questions} == {"fb-1", "fb-3"}

    def test_subset_limit_compose(self, tmp_path: Path) -> None:
        # subset filters before limit applies.
        rows = [
            _fb_row(f"fb-{i}", f"q{i}", str(i), f"ev-{i}", question_type="metrics-generated")
            for i in range(5)
        ] + [
            _fb_row(f"fbx-{i}", f"qx{i}", str(i), f"ev-{i}", question_type="other")
            for i in range(5)
        ]
        p = _write_jsonl(tmp_path, "fb.jsonl", rows)
        vb = VerticalBench.from_jsonl(p, subset="metrics-generated", limit=3)
        assert len(vb.questions) == 3
        assert all(q.qid.startswith("fb-") for q in vb.questions)


# --- VerticalBench.run -------------------------------------------------------


class TestVerticalBenchRun:
    def _make(self, scorer=exact_match) -> VerticalBench:
        return VerticalBench(
            name="toy",
            questions=[
                VerticalQA(qid="q1", question="say yes", expected="yes", tags={"section": "a"}),
                VerticalQA(qid="q2", question="say no", expected="no", tags={"section": "b"}),
            ],
            scorer=scorer,
        )

    def test_perfect_model_scores_1(self) -> None:
        vb = self._make()
        # model_fn echoes the literal expected — should score 1.0 each.
        bench = vb.run(lambda q: "yes" if "yes" in q else "no")
        s = bench.summary()
        assert s["n"] == 2
        assert s["n_success"] == 2
        assert s["accuracy"]["mean"] == 1.0

    def test_wrong_model_scores_0(self) -> None:
        vb = self._make()
        bench = vb.run(lambda q: "wrong")
        s = bench.summary()
        assert s["accuracy"]["mean"] == 0.0

    def test_refusal_tracked(self) -> None:
        vb = self._make()
        # is_refusal hits on "I don't know"
        bench = vb.run(lambda q: "I don't know")
        s = bench.summary()
        assert s["refusal"]["mean"] == 1.0
        # And refusals don't count as correct.
        assert s["accuracy"]["mean"] == 0.0

    def test_tags_propagate(self) -> None:
        vb = self._make()
        bench = vb.run(lambda q: "yes", extra_tags={"variant": "Q4_K_M"})
        # Each BenchCall.tags carries qid + question tags + extra_tags
        for call in bench.calls:
            assert "qid" in call.tags
            assert "variant" in call.tags
            assert call.tags["variant"] == "Q4_K_M"
        sections = [c.tags.get("section") for c in bench.calls]
        assert sorted(sections) == ["a", "b"]

    def test_limit_caps_runs(self) -> None:
        vb = self._make()
        bench = vb.run(lambda q: "yes", limit=1)
        assert bench.summary()["n"] == 1

    def test_returns_bench_instance(self) -> None:
        vb = self._make()
        bench = vb.run(lambda q: "yes")
        assert isinstance(bench, Bench)

    def test_scorer_with_kwargs(self) -> None:
        # numeric_match accepts rel_tolerance — scorer_kwargs should flow through.
        vb = VerticalBench(
            name="num",
            questions=[VerticalQA(qid="q1", question="?", expected="100")],
            scorer=numeric_match,
            scorer_kwargs={"rel_tolerance": 0.5},
        )
        # 140 is within ±50 of 100
        bench = vb.run(lambda q: "140")
        assert bench.summary()["accuracy"]["mean"] == 1.0


# --- VerticalBench.summary (pre-run, lineage-friendly) -----------------------


class TestVerticalBenchSummary:
    def test_summary_shape(self) -> None:
        vb = VerticalBench(
            name="toy",
            questions=[
                VerticalQA(qid="q1", question="q", expected="a", tags={"company": "X", "year": 2024}),
                VerticalQA(qid="q2", question="q", expected="a", tags={"company": "Y"}),
            ],
            scorer=numeric_match,
        )
        s = vb.summary()
        assert s["name"] == "toy"
        assert s["n"] == 2
        assert s["scorer"] == "numeric_match"
        assert s["tag_keys"] == ["company", "year"]


# --- End-to-end --------------------------------------------------------------


class TestEndToEnd:
    def test_financebench_jsonl_to_bench_summary(self, tmp_path: Path) -> None:
        # Two FinanceBench-shaped rows, model gets one right and one wrong.
        rows = [
            {
                "financebench_id": "fb-correct",
                "question": "What was revenue?",
                "gold_standard": "100",
                "company": "ACME",
                "question_type": "numerical",
            },
            {
                "financebench_id": "fb-wrong",
                "question": "What was profit?",
                "gold_standard": "50",
                "company": "ACME",
                "question_type": "numerical",
            },
        ]
        p = _write_jsonl(tmp_path, "fb.jsonl", rows)
        vb = VerticalBench.from_jsonl(p)

        def model_fn(q: str) -> str:
            # Right for the revenue question (100), wrong for the profit question (says 999).
            if "revenue" in q.lower():
                return "It was 100 million."
            return "Profit was 999 million."

        bench = vb.run(model_fn)
        s = bench.summary()
        assert s["n"] == 2
        # Exactly 1 of 2 correct → mean = 0.5
        assert s["accuracy"]["mean"] == 0.5
        # No refusals
        assert s["refusal"]["mean"] == 0.0

    def test_per_row_metric_capture(self, tmp_path: Path) -> None:
        # Confirm BenchCall.metrics carries accuracy + refusal per-row,
        # not just the aggregate.
        rows = [{"question": "say yes", "answer": "yes"}]
        p = _write_jsonl(tmp_path, "single.jsonl", rows)
        vb = VerticalBench.from_jsonl(p)
        bench = vb.run(lambda q: "yes")
        assert len(bench.calls) == 1
        assert bench.calls[0].metrics["accuracy"] == 1.0
        assert bench.calls[0].metrics["refusal"] == 0.0
        assert bench.calls[0].success is True


# --- Patent-strategist format (T4 / specs/patent-strategist-v1.md §3.3) -----


def _ps_row(
    qid: str,
    question: str,
    gold_label: str,
    *,
    family: str = "D",
    use_case: str = "D1",
    scoring_mode: str = "closed",
    options: list[str] | None = None,
    context: str | None = None,
    oracle_context: str | None = None,
    reviewed: bool = True,
    tags: dict | None = None,
) -> dict:
    row: dict = {
        "qid": qid,
        "question": question,
        "family": family,
        "use_case": use_case,
        "scoring_mode": scoring_mode,
        "gold_label": gold_label,
        "reviewed": reviewed,
    }
    if options is not None:
        row["options"] = options
    if context is not None:
        row["context"] = context
    if oracle_context is not None:
        row["oracle_context"] = oracle_context
    if tags is not None:
        row["tags"] = tags
    return row


class TestPatentStrategistFormat:
    def test_autodetect_via_family_use_case_scoring_mode(self, tmp_path: Path) -> None:
        rows = [_ps_row("ps-001", "Which 35 USC section?", "B")]
        p = _write_jsonl(tmp_path, "ps.jsonl", rows)
        vb = VerticalBench.from_jsonl(p)
        assert len(vb.questions) == 1
        # mcq_letter is the default for patent-strategist.
        assert vb.scorer.__name__ == "mcq_letter"

    def test_mcq_options_appended_to_question(self, tmp_path: Path) -> None:
        rows = [
            _ps_row(
                "ps-002",
                "Which 35 USC section governs novelty?",
                "B",
                family="D",
                use_case="D1",
                scoring_mode="closed",
                options=["35 USC 101", "35 USC 102", "35 USC 103", "35 USC 112"],
            )
        ]
        p = _write_jsonl(tmp_path, "ps.jsonl", rows)
        vb = VerticalBench.from_jsonl(p)
        q = vb.questions[0]
        assert "Options:" in q.question
        assert "A. 35 USC 101" in q.question
        assert "B. 35 USC 102" in q.question
        assert "C. 35 USC 103" in q.question
        assert "D. 35 USC 112" in q.question
        assert q.expected == "B"

    def test_retrieval_mode_prepends_context(self, tmp_path: Path) -> None:
        rows = [
            _ps_row(
                "ps-003",
                "Does the cited reference anticipate?",
                "yes",
                family="B",
                use_case="B2",
                scoring_mode="retrieval",
                context="The cited reference discloses all elements...",
            )
        ]
        p = _write_jsonl(tmp_path, "ps.jsonl", rows)
        vb = VerticalBench.from_jsonl(p)
        q = vb.questions[0]
        assert "Context:" in q.question
        assert "The cited reference discloses all elements" in q.question
        assert "Question: Does the cited reference anticipate?" in q.question

    def test_oracle_mode_uses_oracle_context_over_retrieval(self, tmp_path: Path) -> None:
        rows = [
            _ps_row(
                "ps-004",
                "Apply MPEP 2143.",
                "obvious",
                family="D",
                use_case="D2",
                scoring_mode="oracle",
                context="retrieved chunk (wrong)",
                oracle_context="MPEP 2143: ideal text",
            )
        ]
        p = _write_jsonl(tmp_path, "ps.jsonl", rows)
        vb = VerticalBench.from_jsonl(p)
        q = vb.questions[0]
        assert "MPEP 2143: ideal text" in q.question
        assert "retrieved chunk (wrong)" not in q.question

    def test_oracle_falls_back_to_context_when_oracle_missing(self, tmp_path: Path) -> None:
        rows = [
            _ps_row(
                "ps-005",
                "Q?",
                "yes",
                family="D",
                scoring_mode="oracle",
                context="fallback retrieval text",
            )
        ]
        p = _write_jsonl(tmp_path, "ps.jsonl", rows)
        vb = VerticalBench.from_jsonl(p)
        assert "fallback retrieval text" in vb.questions[0].question

    def test_closed_mode_no_context_prepend(self, tmp_path: Path) -> None:
        rows = [
            _ps_row(
                "ps-006",
                "Closed-book question.",
                "A",
                scoring_mode="closed",
                context="should not appear",
                oracle_context="also should not appear",
            )
        ]
        p = _write_jsonl(tmp_path, "ps.jsonl", rows)
        q = VerticalBench.from_jsonl(p).questions[0]
        assert "Context:" not in q.question
        assert "should not appear" not in q.question

    def test_tags_carry_family_use_case_scoring_mode_reviewed(self, tmp_path: Path) -> None:
        rows = [
            _ps_row(
                "ps-007",
                "Q?",
                "A",
                family="A",
                use_case="A3",
                scoring_mode="retrieval",
                reviewed=True,
                tags={"jurisdiction": "US", "art_unit": "2143"},
            )
        ]
        p = _write_jsonl(tmp_path, "ps.jsonl", rows)
        q = VerticalBench.from_jsonl(p).questions[0]
        assert q.tags["family"] == "A"
        assert q.tags["use_case"] == "A3"
        assert q.tags["scoring_mode"] == "retrieval"
        assert q.tags["reviewed"] is True
        assert q.tags["jurisdiction"] == "US"
        assert q.tags["art_unit"] == "2143"

    def test_missing_qid_synthesized(self, tmp_path: Path) -> None:
        rows = [
            {
                "question": "Q?",
                "family": "C",
                "use_case": "C1",
                "scoring_mode": "closed",
                "gold_label": "answer",
            }
        ]
        p = _write_jsonl(tmp_path, "ps.jsonl", rows)
        vb = VerticalBench.from_jsonl(p)
        assert vb.questions[0].qid.startswith("ps-")

    def test_missing_gold_label_drops_row(self, tmp_path: Path) -> None:
        rows = [
            _ps_row("ps-008", "Q?", "A"),
            {  # missing gold_label
                "qid": "ps-009",
                "question": "Q?",
                "family": "D",
                "use_case": "D1",
                "scoring_mode": "closed",
            },
        ]
        p = _write_jsonl(tmp_path, "ps.jsonl", rows)
        vb = VerticalBench.from_jsonl(p)
        assert len(vb.questions) == 1
        assert vb.questions[0].qid == "ps-008"

    def test_explicit_format_override(self, tmp_path: Path) -> None:
        # Even if signature is ambiguous, explicit format pins the branch.
        rows = [
            {
                "qid": "ps-010",
                "question": "Q?",
                "family": "D",
                "use_case": "D1",
                "scoring_mode": "closed",
                "gold_label": "A",
            }
        ]
        p = _write_jsonl(tmp_path, "ps.jsonl", rows)
        vb = VerticalBench.from_jsonl(p, format="patent-strategist")
        assert len(vb.questions) == 1

    def test_default_scorer_is_mcq_letter(self) -> None:
        # Sanity-check the dispatch table covers all five families.
        for family_key in ("A", "B", "C", "D-mcq", "D-oa", "D-irac", "E"):
            assert family_key in PATENT_STRATEGIST_SCORERS
        assert PATENT_STRATEGIST_SCORERS["D-mcq"] == "mcq_letter"

    def test_end_to_end_scoring(self, tmp_path: Path) -> None:
        rows = [
            _ps_row(
                "ps-011",
                "Which 35 USC section governs novelty?",
                "B",
                family="D",
                use_case="D1",
                scoring_mode="closed",
                options=["101", "102", "103", "112"],
            ),
            _ps_row(
                "ps-012",
                "Which section governs obviousness?",
                "C",
                family="D",
                use_case="D1",
                scoring_mode="closed",
                options=["101", "102", "103", "112"],
            ),
        ]
        p = _write_jsonl(tmp_path, "ps.jsonl", rows)
        vb = VerticalBench.from_jsonl(p)

        def model_fn(prompt: str) -> str:
            return "<think>thinking hard</think>\nAnswer: B" if "novelty" in prompt else "C"

        bench = vb.run(model_fn)
        s = bench.summary()
        assert s["n"] == 2
        assert s["accuracy"]["mean"] == 1.0  # both correct via mcq_letter

    def test_scorer_fns_dispatch_resolves_to_callables(self) -> None:
        # The live-callable companion must cover all non-judge_rubric slots
        # and each value must be importable from fieldkit.eval verbatim.
        assert PATENT_STRATEGIST_SCORER_FNS["A"] is patent_claim_validity
        assert PATENT_STRATEGIST_SCORER_FNS["B"] is prior_art_relevance
        assert PATENT_STRATEGIST_SCORER_FNS["D-mcq"] is mcq_letter
        assert PATENT_STRATEGIST_SCORER_FNS["D-oa"] is office_action_argument
        assert PATENT_STRATEGIST_SCORER_FNS["D-irac"] is irac_structure
        # The two judge_rubric slots ("C", "E") aren't in the fn map by design.
        assert "C" not in PATENT_STRATEGIST_SCORER_FNS
        assert "E" not in PATENT_STRATEGIST_SCORER_FNS

    def test_scorer_name_map_matches_fn_map(self) -> None:
        # Every keyed scorer fn should have a matching name entry with the
        # function's actual __name__ so config dumps + live dispatch stay in
        # sync (no drift between the two surfaces).
        for key, fn in PATENT_STRATEGIST_SCORER_FNS.items():
            assert PATENT_STRATEGIST_SCORERS[key] == fn.__name__

    def test_irac_end_to_end_via_vertical_bench(self, tmp_path: Path) -> None:
        # Wire `irac_structure` as a vertical-bench scorer — it's the only
        # T6 scorer that's bench-shaped (predicted, expected) → float and
        # doesn't need a network. Validates the dispatch end-to-end without
        # a live NIM.
        rows = [
            _ps_row(
                "ps-irac-1",
                "Write an IRAC response to this 103 rejection.",
                "any-reference",
                family="D",
                use_case="D2",
                scoring_mode="closed",
            ),
            _ps_row(
                "ps-irac-2",
                "Write an IRAC response.",
                "any",
                family="D",
                use_case="D2",
                scoring_mode="closed",
            ),
        ]
        p = _write_jsonl(tmp_path, "ps.jsonl", rows)
        vb = VerticalBench.from_jsonl(
            p,
            scorer=PATENT_STRATEGIST_SCORER_FNS["D-irac"],
        )

        def model_fn(prompt: str) -> str:
            # First call: full IRAC; second: only I + R.
            if "103 rejection" in prompt:
                return (
                    "Issue: whether the claim is obvious. "
                    "Under 35 USC 103 the rule provides Graham factors apply. "
                    "Here, the references fail to teach element X. "
                    "Therefore the rejection should be withdrawn."
                )
            return "Issue: whether X. Under 35 USC 103 the rule applies."

        bench = vb.run(model_fn)
        s = bench.summary()
        assert s["n"] == 2
        # mean of 1.0 + 0.5 = 0.75
        assert s["accuracy"]["mean"] == pytest.approx(0.75)
