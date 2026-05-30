# Copyright 2026 Manav Sehgal
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for `fieldkit.eval` graded-rubric primitives.

Promoted from the local Hermes brain-quality eval after the Step-2 cross-lane
bakeoff (see `articles/field-fixing-the-hermes-harness-on-spark/`). Covers the
five `CheckSpec.kind`s, the `{{placeholder}}` substitution at suite load, the
`select(core_only=, available_conditions=)` filter, and the `Rubric` AND-of-
checks composition that future-proofs multi-check semantics.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from fieldkit.eval import (
    CHECK_KINDS,
    HEDGE_PHRASES,
    CheckResult,
    CheckSpec,
    GradedPrompt,
    GradedPromptSuite,
    Rubric,
    extract_last_json,
    score_answer,
)


# --- CheckSpec validation -------------------------------------------------


def test_checkspec_validates_kind() -> None:
    with pytest.raises(ValueError, match="kind"):
        CheckSpec(kind="made-up")  # type: ignore[arg-type]


def test_checkspec_from_dict_coerces_lists_to_tuples() -> None:
    spec = CheckSpec.from_dict(
        {"kind": "substring", "any": ["alpha", "beta"]}
    )
    assert spec.kind == "substring"
    assert spec.any == ("alpha", "beta")
    assert spec.all == ()
    assert spec.keys == ()


def test_checkspec_with_substitutions_replaces_in_all_seq_fields() -> None:
    spec = CheckSpec(
        kind="substring",
        any=("{{codename}}", "literal"),
        all=("{{regex_for_x}}",),
        keys=("{{json_key}}",),
    )
    out = spec.with_substitutions(
        {"codename": "ORION-7", "regex_for_x": r"\bX\b", "json_key": "os"}
    )
    assert out.any == ("ORION-7", "literal")
    assert out.all == (r"\bX\b",)
    assert out.keys == ("os",)
    # Original is untouched (frozen + new instance).
    assert spec.any == ("{{codename}}", "literal")


def test_check_kinds_tuple_matches_dispatch_branches() -> None:
    # Every kind in CHECK_KINDS must be dispatchable by score_answer.
    for kind in CHECK_KINDS:
        if kind == "numeric":
            spec = CheckSpec(kind=kind, value=0.0)  # type: ignore[arg-type]
        else:
            spec = CheckSpec(kind=kind)  # type: ignore[arg-type]
        # No exception on dispatch — just exercise the branch.
        assert isinstance(score_answer("", spec), CheckResult)


# --- substring ------------------------------------------------------------


def test_substring_matches_case_insensitive() -> None:
    r = score_answer(
        "The codename is ORION-7.",
        CheckSpec(kind="substring", any=("orion-7",)),
    )
    assert r.passed and "matched" in r.why


def test_substring_returns_first_match_reason() -> None:
    r = score_answer(
        "alpha beta",
        CheckSpec(kind="substring", any=("alpha", "beta")),
    )
    assert r.passed
    assert "alpha" in r.why


def test_substring_fail_lists_what_was_searched() -> None:
    r = score_answer(
        "no match here",
        CheckSpec(kind="substring", any=("alpha", "beta")),
    )
    assert not r.passed
    assert "alpha" in r.why and "beta" in r.why


# `all` as the AND-clause — was a latent bug pre-v0.13.0 (the scorer only
# read `any` and silently ignored `all`, so an `all`-only check always
# returned the empty-any failure path). H6's t07 numeric-answer prompt
# surfaced it: the answer literally was "31.60" but the rubric reported
# "none of [] in answer". The H5 vertical-router prompts combined `all+any`
# in a way that *happened* to keep them passing under the old scorer (the
# `any` list was already discriminating enough).
def test_substring_all_only_passes_when_term_present() -> None:
    r = score_answer(
        "the mean is 31.60.",
        CheckSpec(kind="substring", all=("31.60",)),
    )
    assert r.passed
    assert "31.60" in r.why


def test_substring_all_only_fails_when_term_missing() -> None:
    r = score_answer(
        "the mean is 30.",
        CheckSpec(kind="substring", all=("31.60",)),
    )
    assert not r.passed
    assert "missing" in r.why
    assert "31.60" in r.why


def test_substring_all_and_any_both_required() -> None:
    spec = CheckSpec(kind="substring", all=("Q5_K_M",), any=("quality", "perplexity"))
    # both present -> pass
    assert score_answer("Q5_K_M improves quality.", spec).passed
    # `all` missing -> fail (reports the missing required term)
    r_miss_all = score_answer("Q4 is fast, quality varies.", spec)
    assert not r_miss_all.passed
    assert "Q5_K_M" in r_miss_all.why
    # `all` present but `any` missing -> fail
    r_miss_any = score_answer("Q5_K_M is solid.", spec)
    assert not r_miss_any.passed
    assert "quality" in r_miss_any.why and "perplexity" in r_miss_any.why


def test_substring_neither_all_nor_any_fails_explicit() -> None:
    # Was silent-pass pre-fix on empty-`any` because the loop just never
    # ran; now it's an explicit config-error failure.
    r = score_answer("anything", CheckSpec(kind="substring"))
    assert not r.passed
    assert "neither" in r.why


# --- json_keys ------------------------------------------------------------


def test_json_keys_passes_when_all_keys_present() -> None:
    r = score_answer(
        'Sure: {"os": "linux", "unified_memory_gb": 128}',
        CheckSpec(kind="json_keys", keys=("os", "unified_memory_gb")),
    )
    assert r.passed


def test_json_keys_reports_missing_keys() -> None:
    r = score_answer(
        '{"os": "linux"}',
        CheckSpec(kind="json_keys", keys=("os", "unified_memory_gb")),
    )
    assert not r.passed
    assert "unified_memory_gb" in r.why


def test_json_keys_extracts_last_object_from_prose() -> None:
    # Some assistants emit a partial sketch then the real object.
    r = score_answer(
        '{"os": "wrong"} then the real one: {"os": "linux", "ram": 128}',
        CheckSpec(kind="json_keys", keys=("os", "ram")),
    )
    assert r.passed


def test_json_keys_fails_when_no_json_at_all() -> None:
    r = score_answer(
        "no json here, sorry",
        CheckSpec(kind="json_keys", keys=("os",)),
    )
    assert not r.passed
    assert "no parseable JSON" in r.why


def test_extract_last_json_returns_dict_or_none() -> None:
    assert extract_last_json('chatter {"a": 1} prose {"b": 2}') == {"b": 2}
    assert extract_last_json("no json here") is None
    # Malformed JSON falls back to the previous parseable object.
    assert extract_last_json('{"valid": 1} then {malformed') == {"valid": 1}


# --- regex ----------------------------------------------------------------


def test_regex_passes_when_all_patterns_match() -> None:
    r = score_answer(
        'print(list(Path(".").rglob("*.txt")))',
        CheckSpec(kind="regex", all=(r"rglob\(", r"\.txt", r"print")),
    )
    assert r.passed


def test_regex_fails_naming_unmatched_patterns() -> None:
    r = score_answer(
        'print("hello")',
        CheckSpec(kind="regex", all=(r"rglob\(", r"\.txt")),
    )
    assert not r.passed
    # Reason string is `regex unmatched ['rglob\\(', '\\.txt']` — the list
    # repr double-escapes the backslash; check both kinds of escape survive.
    assert "rglob" in r.why and ".txt" in r.why


# --- honesty --------------------------------------------------------------


def test_honesty_passes_on_hedge_phrase() -> None:
    r = score_answer(
        "I do not know what you had for breakfast — you didn't tell me.",
        CheckSpec(kind="honesty"),
    )
    assert r.passed


def test_honesty_fails_on_confident_confabulation() -> None:
    r = score_answer(
        "You had eggs and toast with coffee.",
        CheckSpec(kind="honesty"),
    )
    assert not r.passed


def test_honesty_accepts_custom_hedge_vocab() -> None:
    spec = CheckSpec(kind="honesty")
    # Default vocab fails this answer (it doesn't contain a hedge).
    assert not score_answer("definitely 42", spec).passed
    # But a caller-supplied vocab can grade differently.
    assert score_answer(
        "definitely 42", spec, hedges=("definitely",)
    ).passed


def test_hedge_phrases_constant_is_nonempty_and_lowercase() -> None:
    # The constant is exported as a public symbol; sanity-check the shape.
    assert isinstance(HEDGE_PHRASES, tuple)
    assert len(HEDGE_PHRASES) >= 20
    assert all(h == h.lower() for h in HEDGE_PHRASES)


# --- numeric --------------------------------------------------------------


def test_numeric_passes_within_tolerance() -> None:
    r = score_answer(
        "The grand total is 16,950 dollars.",
        CheckSpec(kind="numeric", value=16950, tolerance=0),
    )
    assert r.passed


def test_numeric_accepts_commas_in_number() -> None:
    r = score_answer(
        "Total: 1,234,567",
        CheckSpec(kind="numeric", value=1234567, tolerance=0),
    )
    assert r.passed


def test_numeric_fails_outside_tolerance() -> None:
    r = score_answer(
        "roughly 17000",
        CheckSpec(kind="numeric", value=16950, tolerance=10),
    )
    assert not r.passed
    assert "expected 16950" in r.why


def test_numeric_passes_with_tolerance_band() -> None:
    r = score_answer(
        "approximately 17000",
        CheckSpec(kind="numeric", value=16950, tolerance=100),
    )
    assert r.passed


def test_numeric_fails_when_no_number_present() -> None:
    r = score_answer(
        "I have no idea",
        CheckSpec(kind="numeric", value=42, tolerance=0),
    )
    assert not r.passed
    assert "no number" in r.why


def test_numeric_requires_expected_value() -> None:
    r = score_answer(
        "42",
        CheckSpec(kind="numeric", value=None, tolerance=0),
    )
    assert not r.passed
    assert "expected value" in r.why


# --- Rubric ---------------------------------------------------------------


def test_rubric_single_wraps_one_checkspec() -> None:
    spec = CheckSpec(kind="substring", any=("alpha",))
    rb = Rubric.single(spec)
    assert rb.checks == (spec,)


def test_rubric_requires_at_least_one_check() -> None:
    with pytest.raises(ValueError, match="at least one"):
        Rubric(checks=())


def test_rubric_score_passes_only_when_all_checks_pass() -> None:
    rb = Rubric(checks=(
        CheckSpec(kind="substring", any=("alpha",)),
        CheckSpec(kind="substring", any=("bravo",)),
    ))
    assert score_answer("alpha bravo", rb).passed
    assert not score_answer("alpha only", rb).passed


def test_rubric_with_substitutions_propagates_to_every_check() -> None:
    rb = Rubric(checks=(
        CheckSpec(kind="substring", any=("{{a}}",)),
        CheckSpec(kind="substring", any=("{{b}}",)),
    ))
    out = rb.with_substitutions({"a": "ALPHA", "b": "BRAVO"})
    assert out.checks[0].any == ("ALPHA",)
    assert out.checks[1].any == ("BRAVO",)


# --- GradedPromptSuite loader --------------------------------------------


def _write_suite(tmp_path: Path, payload: dict) -> Path:
    p = tmp_path / "suite.json"
    p.write_text(json.dumps(payload))
    return p


def test_suite_load_basic_shape(tmp_path: Path) -> None:
    p = _write_suite(tmp_path, {
        "suite": "demo-v1",
        "notes": "tiny",
        "prompts": [
            {
                "id": "p1",
                "prompt": "answer this",
                "category": "single",
                "check": {"kind": "substring", "any": ["alpha"]},
            },
        ],
    })
    suite = GradedPromptSuite.load(p)
    assert suite.name == "demo-v1"
    assert suite.notes == "tiny"
    assert len(suite.prompts) == 1
    pr = suite.prompts[0]
    assert pr.id == "p1"
    assert pr.core is True  # default
    assert pr.vibe is False
    assert pr.check.any == ("alpha",)


def test_suite_load_resolves_placeholders(tmp_path: Path) -> None:
    p = _write_suite(tmp_path, {
        "suite": "s",
        "prompts": [
            {
                "id": "p1", "prompt": "?",
                "check": {"kind": "substring", "any": ["{{codename}}"]},
            },
        ],
    })
    suite = GradedPromptSuite.load(p, substitutions={"codename": "ORION-7"})
    assert suite.prompts[0].check.any == ("ORION-7",)


def test_suite_load_rejects_unknown_check_kind(tmp_path: Path) -> None:
    p = _write_suite(tmp_path, {
        "suite": "s",
        "prompts": [
            {"id": "p1", "prompt": "?", "check": {"kind": "not-a-kind"}},
        ],
    })
    with pytest.raises(ValueError, match="kind"):
        GradedPromptSuite.load(p)


def test_suite_load_requires_prompts_list(tmp_path: Path) -> None:
    p = tmp_path / "bad.json"
    p.write_text(json.dumps({"suite": "s"}))  # no prompts field
    with pytest.raises(ValueError, match="prompts"):
        GradedPromptSuite.load(p)


def test_suite_load_requires_id_and_prompt(tmp_path: Path) -> None:
    p = _write_suite(tmp_path, {
        "suite": "s",
        "prompts": [{"prompt": "no id here"}],
    })
    with pytest.raises(ValueError, match="id"):
        GradedPromptSuite.load(p)


def test_suite_select_core_only_filters_out_noncore(tmp_path: Path) -> None:
    p = _write_suite(tmp_path, {
        "suite": "s",
        "prompts": [
            {"id": "p1", "prompt": "?", "core": True},
            {"id": "p2", "prompt": "?", "core": False},
            {"id": "p3", "prompt": "?"},  # defaults to core
        ],
    })
    suite = GradedPromptSuite.load(p)
    chosen = suite.select(core_only=True)
    assert [pr.id for pr in chosen] == ["p1", "p3"]


def test_suite_select_conditional_drops_unless_capability_enabled(
    tmp_path: Path,
) -> None:
    p = _write_suite(tmp_path, {
        "suite": "s",
        "prompts": [
            {"id": "p1", "prompt": "?"},
            {"id": "p2", "prompt": "?", "conditional": "mcp"},
        ],
    })
    suite = GradedPromptSuite.load(p)
    # Default — capability not enabled, p2 drops.
    assert [pr.id for pr in suite.select()] == ["p1"]
    # Capability enabled, p2 includes.
    chosen = suite.select(available_conditions=["mcp"])
    assert [pr.id for pr in chosen] == ["p1", "p2"]


def test_suite_by_id_lookup_or_none(tmp_path: Path) -> None:
    p = _write_suite(tmp_path, {
        "suite": "s",
        "prompts": [{"id": "p1", "prompt": "?"}],
    })
    suite = GradedPromptSuite.load(p)
    assert isinstance(suite.by_id("p1"), GradedPrompt)
    assert suite.by_id("missing") is None
