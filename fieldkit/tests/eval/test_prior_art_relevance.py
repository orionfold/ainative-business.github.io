# Copyright 2026 Manav Sehgal
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for `fieldkit.eval.prior_art_relevance` /
`prior_art_relevance_full` — the Spearman-ρ scorer over ranked prior-art
lists added in v0.4.3 for the patent-strategist Family B bench cells.
"""

from __future__ import annotations

import math

import pytest

from fieldkit.eval import (
    PriorArtRelevanceResult,
    prior_art_relevance,
    prior_art_relevance_full,
)


class TestPerfectAndReverse:
    def test_identical_ranking_scores_1(self) -> None:
        assert prior_art_relevance(["a", "b", "c"], ["a", "b", "c"]) == 1.0

    def test_reversed_ranking_scores_minus_1(self) -> None:
        assert prior_art_relevance(["c", "b", "a"], ["a", "b", "c"]) == -1.0

    def test_single_element_returns_0(self) -> None:
        # n<2: insufficient signal to correlate, by convention 0.0.
        assert prior_art_relevance(["a"], ["a"]) == 0.0


class TestPartialOverlap:
    def test_one_item_swapped(self) -> None:
        # ["a","x","c"] vs gold ["a","b","c"]: "x" is unrecognized, gets
        # worst rank (n_gold+1=4); "b" missing from pred also gets 4.
        # gold ranks: a=1, b=2, c=3 → [1, 2, 3]
        # pred ranks: a=1, b=4 (missing), c=3 → [1, 4, 3]
        # Spearman on [1,4,3] vs [1,2,3]: positive but not 1.0.
        rho = prior_art_relevance(["a", "x", "c"], ["a", "b", "c"])
        assert 0.0 < rho < 1.0

    def test_completely_disjoint(self) -> None:
        # No overlap: all gold items get worst-plus-one rank from pred.
        # Pred ranks vector: [4,4,4]; var=0 → ρ=0 by zero-denom rule.
        assert prior_art_relevance(["x", "y", "z"], ["a", "b", "c"]) == 0.0

    def test_pred_subset_of_gold(self) -> None:
        # pred has only first 2 of gold's 3 items, in correct order.
        rho = prior_art_relevance(["a", "b"], ["a", "b", "c"])
        assert 0.0 < rho <= 1.0


class TestStringParsing:
    def test_newline_separated_with_numbering(self) -> None:
        s = "1. doc-a\n2. doc-b\n3. doc-c"
        assert prior_art_relevance(s, "doc-a, doc-b, doc-c") == 1.0

    def test_json_array(self) -> None:
        s = '["a","b","c"]'
        assert prior_art_relevance(s, "a, b, c") == 1.0

    def test_comma_separated_with_spaces(self) -> None:
        assert prior_art_relevance("a , b , c", "a, b, c") == 1.0

    def test_bullet_prefix_stripped(self) -> None:
        s = "- doc-a\n- doc-b\n- doc-c"
        assert prior_art_relevance(s, "doc-a, doc-b, doc-c") == 1.0

    def test_paren_numbered_prefix_stripped(self) -> None:
        s = "1) alpha\n2) beta\n3) gamma"
        assert prior_art_relevance(s, "alpha, beta, gamma") == 1.0

    def test_empty_string_inputs_safe(self) -> None:
        # Empty gold → no signal → rho=0.
        assert prior_art_relevance("", "") == 0.0
        assert prior_art_relevance("a, b", "") == 0.0
        assert prior_art_relevance("", "a, b") == 0.0


class TestLikertBranch:
    def test_likert_perfect_match_zero_mse(self) -> None:
        res = prior_art_relevance_full("5, 4, 3, 2, 1", "5, 4, 3, 2, 1")
        assert res.spearman_rho == 1.0
        assert res.mse_likert == 0.0
        assert res.n == 5

    def test_likert_off_by_one_uniform(self) -> None:
        # Each rating off by 1: MSE = 1.0; ranks still match → ρ=1.0.
        res = prior_art_relevance_full([4, 3, 2, 1], [5, 4, 3, 2])
        assert res.mse_likert == 1.0
        assert res.spearman_rho == 1.0

    def test_likert_uneven_lengths_falls_to_id_branch(self) -> None:
        # Length mismatch knocks off the Likert branch; numeric IDs treated as
        # string identifiers — overlap analysis fires.
        res = prior_art_relevance_full([5, 4, 3], [5, 4, 3, 2])
        assert res.mse_likert is None

    def test_non_numeric_no_likert(self) -> None:
        res = prior_art_relevance_full(["a", "b"], ["a", "b"])
        assert res.mse_likert is None

    def test_id_branch_has_none_mse(self) -> None:
        # The single-value scorer must still return a float for ID-style input.
        rho = prior_art_relevance(["doc-a", "doc-b"], ["doc-a", "doc-b"])
        assert isinstance(rho, float)


class TestDataclassShape:
    def test_returns_dataclass_with_three_fields(self) -> None:
        res = prior_art_relevance_full(["a", "b", "c"], ["a", "b", "c"])
        assert isinstance(res, PriorArtRelevanceResult)
        assert res.spearman_rho == 1.0
        assert res.mse_likert is None
        assert res.n == 3

    def test_dataclass_is_frozen(self) -> None:
        res = prior_art_relevance_full(["a"], ["a"])
        with pytest.raises((AttributeError, Exception)):
            res.spearman_rho = 0.5  # type: ignore[misc]


class TestSpearmanCorrectness:
    def test_known_value_three_swaps(self) -> None:
        # gold:  a(1) b(2) c(3) d(4)
        # pred:  b(1) a(2) c(3) d(4)  — first two swapped
        # ranks-paired (gold-order): pred=[2,1,3,4], gold=[1,2,3,4]
        # ρ = 1 - 6*Σdi^2 / (n*(n^2-1)) = 1 - 6*(1+1+0+0)/(4*15) = 1 - 12/60 = 0.8
        rho = prior_art_relevance(["b", "a", "c", "d"], ["a", "b", "c", "d"])
        assert math.isclose(rho, 0.8, rel_tol=1e-9)

    def test_duplicates_in_pred_ignored_after_first(self) -> None:
        # Pred lists "a" twice — second occurrence is ignored, ranks come
        # from first appearance only.
        rho = prior_art_relevance(["a", "a", "b", "c"], ["a", "b", "c"])
        assert rho == 1.0
