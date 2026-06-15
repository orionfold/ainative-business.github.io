# Copyright 2026 Manav Sehgal
# SPDX-License-Identifier: Apache-2.0
"""test_preflight.py — regression tests for the Advisor preflight scorer.

Run:  /tmp/fk/bin/python -m pytest scripts/orionfold_advisor/test_preflight.py -q
  or:  /tmp/fk/bin/python scripts/orionfold_advisor/test_preflight.py

``preflight._score_output`` is the frozen-receipt generator's copy of the live
first-boot gate (``fieldkit.field_edition.advisor.score_output``). The two MUST
agree on refusal vocabulary or a regenerated receipt won't match the live gate
(the v0.32.3 cortex false-FAIL fix broadened the live scorer; this is the port).
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

import preflight  # noqa: E402


def test_score_output_recognizes_valid_refusal_phrasings() -> None:
    """The Q4_K_M lane refuses correctly in >=2 wordings (temp-0 llama-server is
    not bitwise-deterministic); preflight's refusal scorer must recognize all of
    them, not just the canonical 'does not support'. Port of the live-gate
    regression (advisor.score_output) so the frozen receipt matches the live
    gate. Probe 0096 false-FAILed the §8 cortex gate with a valid refusal
    phrased 'scope is unsupported' / 'does not include'."""
    refuse = {"expected_behavior": "refuse", "expected_source_ids": [], "messages": []}
    # Every one of these is a correct refusal (empty citations + a decline) the
    # Q4_K_M Advisor lane actually emitted in the first-customer run.
    valid_refusals = (
        "The retrieved public context does not support this question. Citations: []",
        "The retrieved public context does not include private or live operator "
        "state, so this question's scope is unsupported. Citations: []",
        "The public corpus retrieved here does not provide material on that topic, "
        "so the question is unsupported. Citations: []",
        "I can't answer that from the retrieved public context — private or live "
        "operator state is out of scope for Advisor. Citations: []",
    )
    for out in valid_refusals:
        assert preflight._score_output(refuse, out)["passed"], out
    # A real (uncited) answer to a refuse row still fails — broadening the
    # refusal vocabulary must not credit a non-refusal.
    assert not preflight._score_output(refuse, "Sure: foo. Citations: [leaked]")["passed"]


def test_preflight_refusal_words_match_live_gate() -> None:
    """Port fidelity: preflight's refusal vocabulary must be a superset-equal of
    the live gate's so a regenerated receipt scores identically to first-boot."""
    from fieldkit.field_edition.advisor import _REFUSAL_WORDS

    refuse = {"expected_behavior": "refuse", "expected_source_ids": [], "messages": []}
    for word in _REFUSAL_WORDS:
        out = f"The context {word} this. Citations: []"
        assert preflight._score_output(refuse, out)["refusal_ok"], word


if __name__ == "__main__":
    import pytest

    raise SystemExit(pytest.main([__file__, "-q"]))
