# Copyright 2026 Manav Sehgal
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for `fieldkit.eval.mcq_letter` (promoted in v0.4.3)."""

from __future__ import annotations

import pytest

from fieldkit.eval import mcq_letter


class TestBareLetter:
    def test_single_letter_match(self) -> None:
        assert mcq_letter("B", "B") == 1.0

    def test_single_letter_miss(self) -> None:
        assert mcq_letter("A", "B") == 0.0

    def test_lowercase_match(self) -> None:
        assert mcq_letter("b", "B") == 1.0

    def test_letter_with_punctuation(self) -> None:
        # ".,)!:- " strip-set should normalize trailing punctuation.
        assert mcq_letter("C.", "C") == 1.0
        assert mcq_letter("C)", "C") == 1.0
        assert mcq_letter("- C", "C") == 1.0

    def test_lowercase_expected(self) -> None:
        # Expected is upper-cased internally; lowercase 'b' still matches.
        assert mcq_letter("B", "b") == 1.0


class TestAnswerMarker:
    def test_answer_colon_X(self) -> None:
        assert mcq_letter("Answer: D", "D") == 1.0

    def test_answer_is_X(self) -> None:
        assert mcq_letter("The answer is C.", "C") == 1.0

    def test_option_X(self) -> None:
        assert mcq_letter("I pick option A here.", "A") == 1.0

    def test_choice_X(self) -> None:
        assert mcq_letter("My choice: B", "B") == 1.0

    def test_marker_wins_over_first_letter(self) -> None:
        # 'A' is the first word-bounded letter but "Answer: D" should win.
        assert mcq_letter("A is wrong. Answer: D", "D") == 1.0
        assert mcq_letter("A is wrong. Answer: D", "A") == 0.0

    def test_concluding_answer_wins_over_elimination(self) -> None:
        # Reasoning models often eliminate distractors with "Option A is
        # incorrect" / "Option D is incorrect" before naming the final pick.
        # The scorer must follow the conclusion, not the first trigger.
        pred = "Option A is incorrect. Option D is incorrect. Answer: B"
        assert mcq_letter(pred, "B") == 1.0
        assert mcq_letter(pred, "A") == 0.0
        assert mcq_letter(pred, "D") == 0.0


class TestNoisyProse:
    def test_first_bounded_letter_fallback(self) -> None:
        # No marker → first word-bounded [A-D] wins.
        assert mcq_letter("The correct choice would be B.", "B") == 1.0

    def test_no_letter_at_all(self) -> None:
        assert mcq_letter("I have no idea.", "B") == 0.0

    def test_letter_inside_word_does_not_match(self) -> None:
        # \b boundary should reject letters embedded in words.
        assert mcq_letter("apple banana cantaloupe date", "A") == 0.0


class TestThinkWrapped:
    def test_think_block_stripped_default(self) -> None:
        # `<think>` content must not pollute the letter pick.
        pred = "<think>Maybe A, maybe B. Reasoning...</think>\nAnswer: C"
        assert mcq_letter(pred, "C") == 1.0
        assert mcq_letter(pred, "A") == 0.0

    def test_think_block_multiline(self) -> None:
        pred = "<think>\nStep 1: read carefully.\nStep 2: pick.\n</think>\nD"
        assert mcq_letter(pred, "D") == 1.0

    def test_strip_think_false_keeps_block(self) -> None:
        # With strip_think=False, "A" inside <think> becomes the first match.
        pred = "<think>I think A</think>\nAnswer: B"
        assert mcq_letter(pred, "A", strip_think=False) == 0.0
        # The "Answer: B" marker still wins over the first-bounded match.
        assert mcq_letter(pred, "B", strip_think=False) == 1.0

    def test_strip_think_noop_on_text_without_tags(self) -> None:
        # Default strip_think=True must be byte-compatible on cyber/medical text.
        assert mcq_letter("Answer: A", "A") == 1.0
        assert mcq_letter("B", "B") == 1.0

    def test_only_think_block_returns_zero(self) -> None:
        # If everything is inside <think>, nothing is left to score.
        pred = "<think>The answer is A</think>"
        assert mcq_letter(pred, "A") == 0.0


class TestEmptyAndMalformed:
    def test_empty_predicted(self) -> None:
        assert mcq_letter("", "A") == 0.0

    def test_whitespace_predicted(self) -> None:
        assert mcq_letter("   \n  ", "B") == 0.0

    def test_empty_expected(self) -> None:
        assert mcq_letter("A", "") == 0.0

    def test_invalid_expected(self) -> None:
        # Only A-D are valid gold labels.
        assert mcq_letter("E", "E") == 0.0
        assert mcq_letter("A", "X") == 0.0

    @pytest.mark.parametrize("predicted", [None, ""])
    def test_none_predicted(self, predicted: str | None) -> None:
        assert mcq_letter(predicted, "A") == 0.0  # type: ignore[arg-type]
