# Copyright 2026 Manav Sehgal
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for `fieldkit.training.decide`.

Pure-python — every test scopes the search path via ``dirs=tmp_path``
so the bundled seed dir + user dir are never read. The
`USER_ENTRIES_DIR` resolution is asserted by constant (no actual
filesystem touch).

Surfaces under test:

- `DecideEntry.from_dict` / `from_yaml` — required keys, optional
  defaults, ISO-date parsing, malformed shape error paths.
- `DecideEntry.matches_context` / `find` / `age_days` — pure-math
  helpers.
- `DecideFinding` — extra-keys preservation.
- `load_entries` — directory scan, lifecycle filter, question filter,
  sorting, multi-dir resolution, file-suffix filter.
- `train_backend` — happy path, no-match error messages, freshness
  ordering (newer entry wins on equal context), context filter.
- `refresh` — staleness math, `today=` override, default vs explicit
  ``include_lifecycle``, bad ``freshness_days`` rejection.
- Module constants — `SEED_ENTRIES_DIR` / `USER_ENTRIES_DIR` /
  `VALID_LIFECYCLES` / `DEFAULT_FRESHNESS_DAYS`.
"""
from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

import pytest

from fieldkit.training import (
    DEFAULT_FRESHNESS_DAYS,
    DecideEntry,
    DecideError,
    DecideFinding,
    DecidePick,
    SEED_ENTRIES_DIR,
    StalenessReport,
    USER_ENTRIES_DIR,
    VALID_LIFECYCLES,
    load_entries,
    refresh,
    train_backend,
)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _entry_dict(
    *,
    slug: str = "test-entry",
    lifecycle: str = "active",
    created: str = "2026-05-22",
    question: str = "train_backend",
    context: dict | None = None,
    findings: list[dict] | None = None,
    sources: list[str] | None = None,
    supersedes: list[str] | None = None,
    notes: str = "",
) -> dict:
    return {
        "slug": slug,
        "lifecycle": lifecycle,
        "created": created,
        "question": question,
        "context": context if context is not None else {"base_model_family": "qwen3-r1-distill"},
        "findings": findings if findings is not None else [
            {"optimize_for": "patent_chain_length", "pick": "nemo", "evidence": "+44%"},
        ],
        "sources": sources if sources is not None else [],
        "supersedes": supersedes if supersedes is not None else [],
        "notes": notes,
    }


def _write_entry(tmp_dir: Path, data: dict, *, ext: str = ".json") -> Path:
    """Write a fixture entry to ``tmp_dir/<slug>.<ext>``. JSON by default
    so the tests pass even when pyyaml isn't installed."""
    tmp_dir.mkdir(parents=True, exist_ok=True)
    p = tmp_dir / f"{data['slug']}{ext}"
    p.write_text(json.dumps(data), encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# module constants
# ---------------------------------------------------------------------------


def test_default_freshness_days_is_180() -> None:
    """Spec §4 default — six months matches typical hardware /
    framework / base-model drift cadence."""
    assert DEFAULT_FRESHNESS_DAYS == 180


def test_valid_lifecycles_locked() -> None:
    assert VALID_LIFECYCLES == frozenset({"active", "superseded", "deprecated"})


def test_seed_entries_dir_inside_package() -> None:
    """SEED_ENTRIES_DIR lives under the installed package tree so it
    rides the wheel via hatch's package-data include."""
    assert "training" in SEED_ENTRIES_DIR.parts
    assert SEED_ENTRIES_DIR.name == "decide-entries"


def test_user_entries_dir_under_home() -> None:
    """USER_ENTRIES_DIR resolves under ``~/.fieldkit/``."""
    assert ".fieldkit" in USER_ENTRIES_DIR.parts
    assert USER_ENTRIES_DIR.name == "decide-entries"


# ---------------------------------------------------------------------------
# DecideFinding
# ---------------------------------------------------------------------------


def test_decide_finding_frozen() -> None:
    f = DecideFinding(optimize_for="wall_clock", pick="nemo", evidence="-26%")
    with pytest.raises(Exception):
        f.pick = "unsloth"  # type: ignore[misc]


def test_decide_finding_preserves_extra_keys() -> None:
    entry = DecideEntry.from_dict(
        _entry_dict(
            findings=[
                {
                    "optimize_for": "wall_clock",
                    "pick": "nemo",
                    "evidence": "-26%",
                    "deltas": {"wall_seconds": -1996, "tokens_per_step": +12},
                }
            ]
        )
    )
    fd = entry.findings[0]
    assert fd.evidence == "-26%"
    assert fd.extra["deltas"]["wall_seconds"] == -1996


# ---------------------------------------------------------------------------
# DecideEntry.from_dict — happy paths
# ---------------------------------------------------------------------------


def test_from_dict_minimal_shape() -> None:
    entry = DecideEntry.from_dict(_entry_dict())
    assert entry.slug == "test-entry"
    assert entry.lifecycle == "active"
    assert entry.created == date(2026, 5, 22)
    assert entry.question == "train_backend"
    assert entry.context == {"base_model_family": "qwen3-r1-distill"}
    assert len(entry.findings) == 1
    assert entry.findings[0].pick == "nemo"
    assert entry.sources == ()
    assert entry.supersedes == ()
    assert entry.notes == ""
    assert entry.path is None


def test_from_dict_records_path_when_supplied(tmp_path: Path) -> None:
    p = tmp_path / "foo.yaml"
    entry = DecideEntry.from_dict(_entry_dict(), path=p)
    assert entry.path == p


def test_from_dict_optional_fields_carried() -> None:
    entry = DecideEntry.from_dict(
        _entry_dict(
            sources=["article-slug-x", "probes/foo.json"],
            supersedes=["older-slug"],
            notes="manually edited",
        )
    )
    assert entry.sources == ("article-slug-x", "probes/foo.json")
    assert entry.supersedes == ("older-slug",)
    assert entry.notes == "manually edited"


def test_from_dict_accepts_native_date_object() -> None:
    """When pyyaml parses an ISO date it returns a real ``date`` —
    we must accept it without re-parsing."""
    d = _entry_dict()
    d["created"] = date(2026, 1, 5)
    entry = DecideEntry.from_dict(d)
    assert entry.created == date(2026, 1, 5)


# ---------------------------------------------------------------------------
# DecideEntry.from_dict — error paths
# ---------------------------------------------------------------------------


def test_from_dict_missing_required_key_raises() -> None:
    d = _entry_dict()
    del d["question"]
    with pytest.raises(DecideError) as exc_info:
        DecideEntry.from_dict(d)
    assert "question" in str(exc_info.value)


def test_from_dict_rejects_bad_lifecycle() -> None:
    with pytest.raises(DecideError) as exc_info:
        DecideEntry.from_dict(_entry_dict(lifecycle="wip"))
    assert "lifecycle" in str(exc_info.value)


def test_from_dict_rejects_empty_findings() -> None:
    with pytest.raises(DecideError) as exc_info:
        DecideEntry.from_dict(_entry_dict(findings=[]))
    assert "findings" in str(exc_info.value)


def test_from_dict_rejects_non_mapping_context() -> None:
    d = _entry_dict()
    d["context"] = ["not", "a", "mapping"]
    with pytest.raises(DecideError):
        DecideEntry.from_dict(d)


def test_from_dict_rejects_finding_missing_pick() -> None:
    with pytest.raises(DecideError) as exc_info:
        DecideEntry.from_dict(
            _entry_dict(findings=[{"optimize_for": "x"}])
        )
    assert "pick" in str(exc_info.value)


def test_from_dict_rejects_bad_iso_date_format() -> None:
    with pytest.raises(DecideError):
        DecideEntry.from_dict(_entry_dict(created="not-a-date"))


def test_from_dict_rejects_findings_string() -> None:
    """A string accidentally passed as findings would otherwise iterate
    char-by-char; fail closed."""
    d = _entry_dict()
    d["findings"] = "not-a-list"
    with pytest.raises(DecideError):
        DecideEntry.from_dict(d)


# ---------------------------------------------------------------------------
# DecideEntry methods
# ---------------------------------------------------------------------------


def test_find_returns_matching_finding() -> None:
    entry = DecideEntry.from_dict(
        _entry_dict(
            findings=[
                {"optimize_for": "wall_clock", "pick": "nemo", "evidence": "-26%"},
                {"optimize_for": "dev_velocity", "pick": "unsloth", "evidence": "4x faster"},
            ]
        )
    )
    fd = entry.find(optimize_for="dev_velocity")
    assert fd is not None and fd.pick == "unsloth"


def test_find_returns_none_when_no_match() -> None:
    entry = DecideEntry.from_dict(_entry_dict())
    assert entry.find(optimize_for="nonexistent") is None


def test_matches_context_all_constraints_match() -> None:
    entry = DecideEntry.from_dict(
        _entry_dict(context={"base_model_family": "qwen3", "size": "8b"})
    )
    assert entry.matches_context(base_model_family="qwen3", size="8b") is True


def test_matches_context_partial_match_false() -> None:
    entry = DecideEntry.from_dict(
        _entry_dict(context={"base_model_family": "qwen3"})
    )
    # 'size' isn't in entry context → fail closed
    assert entry.matches_context(base_model_family="qwen3", size="8b") is False


def test_matches_context_no_constraints_returns_true() -> None:
    entry = DecideEntry.from_dict(_entry_dict())
    assert entry.matches_context() is True


def test_age_days_with_today_override() -> None:
    entry = DecideEntry.from_dict(_entry_dict(created="2026-01-01"))
    assert entry.age_days(today=date(2026, 5, 22)) == 141


def test_age_days_clamps_negative_to_zero() -> None:
    """Future-dated entries (e.g. drafts committed ahead of publish) get 0,
    not a negative."""
    entry = DecideEntry.from_dict(_entry_dict(created="2027-01-01"))
    assert entry.age_days(today=date(2026, 5, 22)) == 0


# ---------------------------------------------------------------------------
# DecideEntry.from_yaml (using JSON form for portability)
# ---------------------------------------------------------------------------


def test_from_yaml_loads_json_form(tmp_path: Path) -> None:
    """from_yaml accepts JSON syntax — exercised by the test suite so
    the suite passes without pyyaml installed."""
    p = _write_entry(tmp_path, _entry_dict(), ext=".json")
    entry = DecideEntry.from_yaml(p)
    assert entry.slug == "test-entry"
    assert entry.path == p.resolve()


def test_from_yaml_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(DecideError):
        DecideEntry.from_yaml(tmp_path / "nope.yaml")


def test_from_yaml_non_mapping_raises(tmp_path: Path) -> None:
    p = tmp_path / "bad.json"
    p.write_text("[1, 2, 3]", encoding="utf-8")
    with pytest.raises(DecideError):
        DecideEntry.from_yaml(p)


# ---------------------------------------------------------------------------
# load_entries
# ---------------------------------------------------------------------------


def test_load_entries_from_explicit_dir(tmp_path: Path) -> None:
    _write_entry(tmp_path, _entry_dict(slug="a", created="2026-05-01"))
    _write_entry(tmp_path, _entry_dict(slug="b", created="2026-05-10"))
    entries = load_entries(dirs=[tmp_path])
    assert {e.slug for e in entries} == {"a", "b"}


def test_load_entries_sorts_by_created_descending(tmp_path: Path) -> None:
    _write_entry(tmp_path, _entry_dict(slug="oldest", created="2026-01-01"))
    _write_entry(tmp_path, _entry_dict(slug="middle", created="2026-03-01"))
    _write_entry(tmp_path, _entry_dict(slug="newest", created="2026-05-01"))
    entries = load_entries(dirs=[tmp_path])
    assert [e.slug for e in entries] == ["newest", "middle", "oldest"]


def test_load_entries_lifecycle_filter_default_active(tmp_path: Path) -> None:
    _write_entry(tmp_path, _entry_dict(slug="a", lifecycle="active"))
    _write_entry(tmp_path, _entry_dict(slug="b", lifecycle="superseded"))
    _write_entry(tmp_path, _entry_dict(slug="c", lifecycle="deprecated"))
    entries = load_entries(dirs=[tmp_path])  # default = "active"
    assert [e.slug for e in entries] == ["a"]


def test_load_entries_lifecycle_filter_none_returns_all(tmp_path: Path) -> None:
    _write_entry(tmp_path, _entry_dict(slug="a", lifecycle="active"))
    _write_entry(tmp_path, _entry_dict(slug="b", lifecycle="superseded"))
    entries = load_entries(dirs=[tmp_path], lifecycle=None)
    assert {e.slug for e in entries} == {"a", "b"}


def test_load_entries_lifecycle_filter_sequence(tmp_path: Path) -> None:
    _write_entry(tmp_path, _entry_dict(slug="a", lifecycle="active"))
    _write_entry(tmp_path, _entry_dict(slug="b", lifecycle="superseded"))
    _write_entry(tmp_path, _entry_dict(slug="c", lifecycle="deprecated"))
    entries = load_entries(dirs=[tmp_path], lifecycle=["active", "superseded"])
    assert {e.slug for e in entries} == {"a", "b"}


def test_load_entries_rejects_bad_lifecycle_string(tmp_path: Path) -> None:
    with pytest.raises(DecideError):
        load_entries(dirs=[tmp_path], lifecycle="wip")


def test_load_entries_rejects_bad_lifecycle_in_sequence(tmp_path: Path) -> None:
    with pytest.raises(DecideError):
        load_entries(dirs=[tmp_path], lifecycle=["active", "wip"])


def test_load_entries_question_filter(tmp_path: Path) -> None:
    _write_entry(tmp_path, _entry_dict(slug="a", question="train_backend"))
    _write_entry(tmp_path, _entry_dict(slug="b", question="seq_length"))
    entries = load_entries(dirs=[tmp_path], question="train_backend")
    assert [e.slug for e in entries] == ["a"]


def test_load_entries_skips_non_entry_suffixes(tmp_path: Path) -> None:
    """README, .txt etc. in the entries dir must be skipped, not parsed."""
    _write_entry(tmp_path, _entry_dict(slug="a"))
    (tmp_path / "README.md").write_text("docs\n", encoding="utf-8")
    (tmp_path / "notes.txt").write_text("scratch\n", encoding="utf-8")
    entries = load_entries(dirs=[tmp_path])
    assert {e.slug for e in entries} == {"a"}


def test_load_entries_multi_dir_merges(tmp_path: Path) -> None:
    a_dir = tmp_path / "a"
    b_dir = tmp_path / "b"
    _write_entry(a_dir, _entry_dict(slug="from-a", created="2026-05-01"))
    _write_entry(b_dir, _entry_dict(slug="from-b", created="2026-05-10"))
    entries = load_entries(dirs=[a_dir, b_dir])
    assert [e.slug for e in entries] == ["from-b", "from-a"]


def test_load_entries_tolerates_missing_dir(tmp_path: Path) -> None:
    """A configured dir that doesn't exist is silently skipped."""
    entries = load_entries(dirs=[tmp_path / "does-not-exist"])
    assert entries == []


# ---------------------------------------------------------------------------
# train_backend
# ---------------------------------------------------------------------------


def test_train_backend_happy_path(tmp_path: Path) -> None:
    _write_entry(
        tmp_path,
        _entry_dict(
            findings=[
                {"optimize_for": "patent_chain_length", "pick": "nemo", "evidence": "+44%"},
                {"optimize_for": "dev_velocity", "pick": "unsloth", "evidence": "4x faster"},
            ]
        ),
    )
    result = train_backend(
        base_model_family="qwen3-r1-distill",
        optimize_for="patent_chain_length",
        dirs=[tmp_path],
    )
    assert isinstance(result, DecidePick)
    assert result.pick == "nemo"
    assert result.backend == "nemo"  # alias
    assert result.evidence == "+44%"
    assert result.optimize_for == "patent_chain_length"
    assert result.entry.slug == "test-entry"
    assert result.entry_path is not None


def test_train_backend_returns_evidence_for_other_optimize_for(tmp_path: Path) -> None:
    _write_entry(
        tmp_path,
        _entry_dict(
            findings=[
                {"optimize_for": "wall_clock", "pick": "nemo", "evidence": "-26%"},
                {"optimize_for": "dev_velocity", "pick": "unsloth", "evidence": "4x"},
            ]
        ),
    )
    result = train_backend(
        base_model_family="qwen3-r1-distill",
        optimize_for="dev_velocity",
        dirs=[tmp_path],
    )
    assert result.pick == "unsloth"
    assert result.evidence == "4x"


def test_train_backend_picks_newer_entry_on_equal_context(tmp_path: Path) -> None:
    _write_entry(
        tmp_path,
        _entry_dict(
            slug="older",
            created="2025-12-01",
            findings=[{"optimize_for": "x", "pick": "old-pick", "evidence": "stale"}],
        ),
    )
    _write_entry(
        tmp_path,
        _entry_dict(
            slug="newer",
            created="2026-05-22",
            findings=[{"optimize_for": "x", "pick": "new-pick", "evidence": "fresh"}],
        ),
    )
    result = train_backend(
        base_model_family="qwen3-r1-distill",
        optimize_for="x",
        dirs=[tmp_path],
    )
    assert result.pick == "new-pick"
    assert result.entry.slug == "newer"


def test_train_backend_skips_non_active(tmp_path: Path) -> None:
    """Superseded / deprecated entries must never satisfy a lookup,
    even if they're the only match."""
    _write_entry(
        tmp_path,
        _entry_dict(
            lifecycle="superseded",
            findings=[{"optimize_for": "x", "pick": "y", "evidence": "z"}],
        ),
    )
    with pytest.raises(DecideError):
        train_backend(
            base_model_family="qwen3-r1-distill",
            optimize_for="x",
            dirs=[tmp_path],
        )


def test_train_backend_no_match_on_context_raises(tmp_path: Path) -> None:
    _write_entry(tmp_path, _entry_dict(context={"base_model_family": "other"}))
    with pytest.raises(DecideError) as exc_info:
        train_backend(
            base_model_family="qwen3-r1-distill",
            optimize_for="x",
            dirs=[tmp_path],
        )
    # Error message should list what was seen — helps the caller debug
    assert "qwen3-r1-distill" in str(exc_info.value)


def test_train_backend_no_match_on_optimize_for_raises(tmp_path: Path) -> None:
    _write_entry(
        tmp_path,
        _entry_dict(
            findings=[{"optimize_for": "wall_clock", "pick": "nemo", "evidence": "x"}]
        ),
    )
    with pytest.raises(DecideError) as exc_info:
        train_backend(
            base_model_family="qwen3-r1-distill",
            optimize_for="completely-different-knob",
            dirs=[tmp_path],
        )
    # Error message should hint available optimize_for keys
    assert "wall_clock" in str(exc_info.value)


def test_train_backend_only_considers_train_backend_question(tmp_path: Path) -> None:
    _write_entry(
        tmp_path,
        _entry_dict(question="seq_length"),
    )
    with pytest.raises(DecideError):
        train_backend(
            base_model_family="qwen3-r1-distill",
            optimize_for="patent_chain_length",
            dirs=[tmp_path],
        )


def test_train_backend_pick_carries_entry_context_copy(tmp_path: Path) -> None:
    _write_entry(
        tmp_path,
        _entry_dict(context={"base_model_family": "qwen3-r1-distill", "size": "8b"}),
    )
    result = train_backend(
        base_model_family="qwen3-r1-distill",
        optimize_for="patent_chain_length",
        dirs=[tmp_path],
    )
    assert result.context["size"] == "8b"


# ---------------------------------------------------------------------------
# refresh
# ---------------------------------------------------------------------------


def test_refresh_flags_stale_entries(tmp_path: Path) -> None:
    today = date(2026, 5, 22)
    fresh = today - timedelta(days=30)
    stale = today - timedelta(days=200)
    _write_entry(tmp_path, _entry_dict(slug="fresh", created=fresh.isoformat()))
    _write_entry(tmp_path, _entry_dict(slug="stale", created=stale.isoformat()))
    reports = refresh(dirs=[tmp_path], freshness_days=180, today=today)
    by_slug = {r.entry.slug: r for r in reports}
    assert by_slug["fresh"].stale is False
    assert by_slug["stale"].stale is True


def test_refresh_sorts_oldest_first(tmp_path: Path) -> None:
    today = date(2026, 5, 22)
    _write_entry(
        tmp_path, _entry_dict(slug="oldest", created="2025-01-01")
    )
    _write_entry(
        tmp_path, _entry_dict(slug="newer", created="2026-04-01")
    )
    reports = refresh(dirs=[tmp_path], today=today)
    assert [r.entry.slug for r in reports] == ["oldest", "newer"]
    assert reports[0].age_days > reports[1].age_days


def test_refresh_includes_all_lifecycles_by_default(tmp_path: Path) -> None:
    """Refresh cares about the full corpus, not just active entries —
    a stale superseded entry is still useful audit signal."""
    _write_entry(tmp_path, _entry_dict(slug="a", lifecycle="active"))
    _write_entry(tmp_path, _entry_dict(slug="b", lifecycle="superseded"))
    _write_entry(tmp_path, _entry_dict(slug="c", lifecycle="deprecated"))
    reports = refresh(dirs=[tmp_path], today=date(2026, 5, 22))
    assert {r.entry.slug for r in reports} == {"a", "b", "c"}


def test_refresh_include_lifecycle_filter(tmp_path: Path) -> None:
    _write_entry(tmp_path, _entry_dict(slug="a", lifecycle="active"))
    _write_entry(tmp_path, _entry_dict(slug="b", lifecycle="superseded"))
    reports = refresh(
        dirs=[tmp_path], include_lifecycle="active", today=date(2026, 5, 22)
    )
    assert {r.entry.slug for r in reports} == {"a"}


def test_refresh_rejects_negative_freshness_days(tmp_path: Path) -> None:
    with pytest.raises(DecideError):
        refresh(dirs=[tmp_path], freshness_days=-1)


def test_refresh_empty_corpus_returns_empty_list(tmp_path: Path) -> None:
    assert refresh(dirs=[tmp_path]) == []


def test_staleness_report_carries_age_days(tmp_path: Path) -> None:
    _write_entry(tmp_path, _entry_dict(created="2026-01-01"))
    reports = refresh(dirs=[tmp_path], today=date(2026, 5, 22))
    assert len(reports) == 1
    assert reports[0].age_days == 141
    assert isinstance(reports[0], StalenessReport)
