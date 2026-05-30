# Copyright 2026 Manav Sehgal
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for `fieldkit.eval.irac_structure` — the deterministic
4-checklist IRAC (Issue/Rule/Application/Conclusion) detector added in
v0.4.3 alongside the patent-strategist bench format.
"""

from __future__ import annotations

import pytest

from fieldkit.eval import irac_structure


class TestPerfectIRAC:
    def test_canonical_form_scores_1(self) -> None:
        txt = (
            "Issue: whether the claims are obvious over the cited art. "
            "Under 35 USC 103 the rule provides that obviousness is "
            "determined under the Graham factors. "
            "Here, the cited references do not teach element X. "
            "Therefore the rejection should be withdrawn."
        )
        assert irac_structure(txt, "") == 1.0

    def test_all_caps_headings_score_1(self) -> None:
        txt = (
            "ISSUE\nwhether the claims are obvious.\n"
            "RULE\n35 USC 103 governs obviousness.\n"
            "APPLICATION\nHere, the references fail to teach X.\n"
            "CONCLUSION\nTherefore the rejection should be withdrawn."
        )
        assert irac_structure(txt, "") == 1.0

    def test_lowercase_inline_prose(self) -> None:
        # Single-paragraph IRAC with no headings; transition words alone.
        txt = (
            "the issue is whether the claim is enabled. the rule under "
            "35 USC 112 requires undue experimentation analysis. here, "
            "the specification teaches the full scope. therefore "
            "enablement is satisfied."
        )
        assert irac_structure(txt, "") == 1.0


class TestPartialIRAC:
    def test_issue_only(self) -> None:
        # Just the issue heading; no R/A/C transitions present.
        assert irac_structure("Issue: whether the claim is enabled.", "") == 0.25

    def test_issue_and_conclusion(self) -> None:
        assert irac_structure("Issue: whether X. Therefore Y.", "") == 0.5

    def test_three_out_of_four(self) -> None:
        # Drop the Application component.
        txt = "Issue: whether X. Under 35 USC 103 obviousness applies. Therefore Y."
        assert irac_structure(txt, "") == 0.75

    def test_no_irac_signals_returns_0(self) -> None:
        # Bare assertion with no structural cues.
        assert irac_structure("The applicant disagrees with the examiner.", "") == 0.0

    def test_empty_predicted(self) -> None:
        assert irac_structure("", "") == 0.0

    def test_whitespace_only_predicted(self) -> None:
        # Treated as empty after `if not predicted` guard.
        assert irac_structure("   \n   ", "") == 0.0


class TestIssueDetector:
    def test_issue_colon(self) -> None:
        assert irac_structure("Issue: whether X.", "") >= 0.25

    def test_the_issue_phrase(self) -> None:
        assert irac_structure("The issue is whether X.", "") >= 0.25

    def test_question_presented(self) -> None:
        assert irac_structure("Question presented: whether X.", "") >= 0.25

    def test_whether_alone(self) -> None:
        # "Whether" as a paragraph-leading cue is enough for the issue dim.
        assert irac_structure("Whether the claim is patentable.", "") >= 0.25


class TestRuleDetector:
    def test_under_35_usc(self) -> None:
        assert irac_structure("Under 35 USC 103 obviousness applies.", "") >= 0.25

    def test_under_35_usc_dotted(self) -> None:
        # Citation form with dots: 35 U.S.C. 102.
        assert irac_structure("Under 35 U.S.C. 102 anticipation applies.", "") >= 0.25

    def test_mpep_citation(self) -> None:
        assert irac_structure("MPEP 2143 sets forth the rationales.", "") >= 0.25

    def test_mpep_section_symbol(self) -> None:
        assert irac_structure("MPEP § 2143 sets forth the rationales.", "") >= 0.25

    def test_holding_alone(self) -> None:
        assert irac_structure("The holding in KSR controls.", "") >= 0.25

    def test_law_provides(self) -> None:
        assert irac_structure("The law provides that obviousness is a question of law.", "") >= 0.25


class TestApplicationDetector:
    def test_here_comma(self) -> None:
        assert irac_structure("Here, the references fail to teach X.", "") >= 0.25

    def test_here_space(self) -> None:
        assert irac_structure("Here the references fail to teach X.", "") >= 0.25

    def test_in_this_case(self) -> None:
        assert irac_structure("In this case the references do not teach X.", "") >= 0.25

    def test_in_the_present(self) -> None:
        assert irac_structure("In the present application the claims recite X.", "") >= 0.25

    def test_applying_phrase(self) -> None:
        assert irac_structure("Applying the Graham factors, the claims are non-obvious.", "") >= 0.25

    def test_applied_to(self) -> None:
        assert irac_structure("As applied to claim 1, the rejection fails.", "") >= 0.25


class TestConclusionDetector:
    def test_therefore(self) -> None:
        assert irac_structure("Therefore the rejection should be withdrawn.", "") >= 0.25

    def test_accordingly(self) -> None:
        assert irac_structure("Accordingly the claims are allowable.", "") >= 0.25

    def test_in_conclusion(self) -> None:
        assert irac_structure("In conclusion the claim is non-obvious.", "") >= 0.25

    def test_for_the_above_reasons(self) -> None:
        assert irac_structure("For the above reasons the claims are patentable.", "") >= 0.25

    def test_for_foregoing_reasons(self) -> None:
        assert irac_structure("For the foregoing reasons reconsideration is requested.", "") >= 0.25

    def test_examiner_should_phrase(self) -> None:
        assert irac_structure("The examiner should withdraw the rejection.", "") >= 0.25


class TestExpectedIgnored:
    def test_expected_arg_does_not_affect_score(self) -> None:
        # `expected` is a structural-form scorer signature stub; value is unused.
        txt = "Issue: whether X. Therefore Y."
        assert irac_structure(txt, "anything") == irac_structure(txt, "") == 0.5

    def test_default_expected_omitted(self) -> None:
        # Signature has expected="" default so callers can drop the arg.
        assert irac_structure("Therefore Y.") == 0.25  # type: ignore[call-arg]


class TestQuarterGranularity:
    @pytest.mark.parametrize(
        "txt,expected_score",
        [
            ("Issue: X", 0.25),
            ("Issue: X. Under 35 USC 103", 0.5),
            ("Issue: X. Under 35 USC 103. Here, the claims", 0.75),
            ("Issue: X. Under 35 USC 103. Here, the claims. Therefore Y.", 1.0),
        ],
    )
    def test_one_quarter_per_component(self, txt: str, expected_score: float) -> None:
        assert irac_structure(txt, "") == expected_score
