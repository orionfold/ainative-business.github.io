# Copyright 2026 Manav Sehgal
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for `fieldkit.eval.patent_claim_validity` and
`fieldkit.eval.office_action_argument` — the two LLM-judge-backed scorers
added in v0.4.3.

These are wrappers around `Judge.grade(...)` that thread an optional per-row
`rubric` dict through as a structured `Hints:` block. Tests stub the Judge
with a fake that records the last call args so we can assert plumbing
without hitting a NIM endpoint.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pytest

from fieldkit.eval import (
    JudgeResult,
    RUBRIC_OFFICE_ACTION_ARGUMENT,
    RUBRIC_PATENT_CLAIM_VALIDITY,
    _format_rubric_hints,
    load_rubric,
    office_action_argument,
    patent_claim_validity,
)


# --- Fakes --------------------------------------------------------------


@dataclass
class _FakeJudge:
    """Stand-in for `fieldkit.eval.Judge` that captures the last call args.

    `score` and `rationale` come back from `grade()` verbatim. If `score` is
    None we return a JudgeResult with score=None to exercise the
    "missing-parse-falls-to-0.0" branch.
    """

    score: float | None = 1.0
    rationale: str = "ok"
    calls: list[dict[str, Any]] = field(default_factory=list)

    def grade(
        self,
        *,
        prediction: str,
        question: str | None = None,
        reference: str | None = None,
        context: str | None = None,
    ) -> JudgeResult:
        self.calls.append(
            {
                "prediction": prediction,
                "question": question,
                "reference": reference,
                "context": context,
            }
        )
        return JudgeResult(score=self.score, rationale=self.rationale, raw="")


# --- Rubric loader ------------------------------------------------------


class TestLoadRubric:
    def test_loads_patent_claim_validity(self) -> None:
        s = load_rubric("patent_claim_validity")
        assert "PatentScore" in s
        assert "novelty" in s.lower()
        assert "non-obviousness" in s.lower()
        assert "indefiniteness" in s.lower()
        # Must spec the JSON output contract.
        assert '"score"' in s
        assert '"rationale"' in s

    def test_loads_office_action_argument(self) -> None:
        s = load_rubric("office_action_argument")
        assert "rejection" in s.lower()
        assert "statutory" in s.lower()
        assert "persuasiveness" in s.lower()
        assert '"score"' in s

    def test_module_constants_match_files(self) -> None:
        assert RUBRIC_PATENT_CLAIM_VALIDITY == load_rubric("patent_claim_validity")
        assert RUBRIC_OFFICE_ACTION_ARGUMENT == load_rubric("office_action_argument")

    def test_missing_rubric_raises(self) -> None:
        with pytest.raises(FileNotFoundError):
            load_rubric("does_not_exist")


# --- Hints renderer -----------------------------------------------------


class TestFormatRubricHints:
    def test_empty_returns_empty(self) -> None:
        assert _format_rubric_hints(None) == ""
        assert _format_rubric_hints({}) == ""

    def test_scalar_values(self) -> None:
        s = _format_rubric_hints({"claim_type": "independent", "claim_count": 3})
        assert s.startswith("Hints:")
        assert "claim_count: 3" in s
        assert "claim_type: independent" in s

    def test_list_values_bullet_rendered(self) -> None:
        s = _format_rubric_hints({"required_citations": ["MPEP 2143", "KSR v. Teleflex"]})
        assert "- required_citations:" in s
        assert "  - MPEP 2143" in s
        assert "  - KSR v. Teleflex" in s

    def test_keys_sorted_for_determinism(self) -> None:
        # Two calls with same dict but different insertion order → same output.
        a = _format_rubric_hints({"z": 1, "a": 2})
        b = _format_rubric_hints({"a": 2, "z": 1})
        assert a == b
        assert a.find("a: 2") < a.find("z: 1")

    def test_nested_dict_json_dumped(self) -> None:
        s = _format_rubric_hints({"tags": {"jurisdiction": "US", "art_unit": "2143"}})
        # Nested dicts are sorted by json.dumps with sort_keys=True.
        assert '{"art_unit": "2143", "jurisdiction": "US"}' in s


# --- patent_claim_validity ----------------------------------------------


class TestPatentClaimValidity:
    def test_perfect_score_passes_through(self) -> None:
        j = _FakeJudge(score=1.0)
        out = patent_claim_validity("pred claim", "ref claim", judge=j)
        assert out == 1.0
        assert j.calls[0]["prediction"] == "pred claim"
        assert j.calls[0]["reference"] == "ref claim"
        # No rubric dict → no Hints block.
        assert j.calls[0]["context"] is None

    def test_partial_score(self) -> None:
        j = _FakeJudge(score=0.42)
        assert patent_claim_validity("p", "r", judge=j) == 0.42

    def test_none_score_maps_to_zero(self) -> None:
        # When the judge can't parse a score (returns None), bench-friendly
        # default is 0.0 so accuracy averaging stays well-defined.
        j = _FakeJudge(score=None)
        assert patent_claim_validity("p", "r", judge=j) == 0.0

    def test_rubric_dict_threaded_as_hints(self) -> None:
        j = _FakeJudge(score=0.5)
        patent_claim_validity(
            "predicted claim text",
            "reference claim text",
            judge=j,
            rubric={"cited_prior_art": ["US123", "US456"], "claim_type": "independent"},
        )
        ctx = j.calls[0]["context"]
        assert ctx is not None
        assert ctx.startswith("Hints:")
        assert "cited_prior_art" in ctx
        assert "US123" in ctx
        assert "claim_type: independent" in ctx

    def test_empty_reference_becomes_none(self) -> None:
        # `reference or None` collapses empty strings so the Judge doesn't see
        # "Reference answer: \n" — keeps the prompt clean.
        j = _FakeJudge(score=1.0)
        patent_claim_validity("p", "", judge=j)
        assert j.calls[0]["reference"] is None


# --- office_action_argument ---------------------------------------------


class TestOfficeActionArgument:
    def test_perfect_score_passes_through(self) -> None:
        j = _FakeJudge(score=1.0)
        out = office_action_argument("predicted response", "reference response", judge=j)
        assert out == 1.0
        assert j.calls[0]["prediction"] == "predicted response"

    def test_none_score_maps_to_zero(self) -> None:
        j = _FakeJudge(score=None)
        assert office_action_argument("p", "r", judge=j) == 0.0

    def test_rubric_hints_with_rejection_type(self) -> None:
        j = _FakeJudge(score=0.7)
        office_action_argument(
            "pred",
            "ref",
            judge=j,
            rubric={
                "rejection_type": "103",
                "required_citations": ["MPEP 2143", "KSR"],
                "claim_count": 4,
                "relies_on_official_notice": True,
            },
        )
        ctx = j.calls[0]["context"]
        assert ctx is not None
        assert "rejection_type: 103" in ctx
        assert "MPEP 2143" in ctx
        assert "claim_count: 4" in ctx
        assert "relies_on_official_notice: True" in ctx

    def test_no_rubric_no_context(self) -> None:
        j = _FakeJudge(score=0.5)
        office_action_argument("p", "r", judge=j)
        assert j.calls[0]["context"] is None


class TestSignaturesAcceptKwargs:
    """Both scorers must accept rubric and judge as kwargs — required by
    `VerticalBench._accepts_kwargs` so `scorer_kwargs` flows through."""

    def test_patent_claim_validity_takes_kwargs(self) -> None:
        import inspect

        sig = inspect.signature(patent_claim_validity)
        params = sig.parameters
        assert params["judge"].kind == params["judge"].KEYWORD_ONLY
        assert params["rubric"].kind == params["rubric"].KEYWORD_ONLY

    def test_office_action_argument_takes_kwargs(self) -> None:
        import inspect

        sig = inspect.signature(office_action_argument)
        params = sig.parameters
        assert params["judge"].kind == params["judge"].KEYWORD_ONLY
        assert params["rubric"].kind == params["rubric"].KEYWORD_ONLY
