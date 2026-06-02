# Copyright 2026 Manav Sehgal
# SPDX-License-Identifier: Apache-2.0
"""**The M7-blocker leak gate** — assert no operator-private chat content
appears in any mirror JSON output.

This is the hard regression test the M6 release gates against, called out
in HANDOFF (QUEUED NEXT #1) and `_SPECS/spark-arena-v1.md` §4.10 + risk R1.
The test seeds *unique sentinel strings* into every forbidden column the
exporter must never touch (``chat_turns.content``, ``chat_turns.reasoning``,
``compare_runs.prompt``, ``compare_responses.content``,
``compare_responses.reasoning``) AND runs the exporter against the seeded
DB. After the export it reads the emitted JSON as a single string and
asserts none of the sentinels appear.

Sentinels are random-uuid-prefixed so a substring match is a true leak,
not a false positive on a natural-language coincidence with the
leaderboard payload. Test refuses to run if it can't prove the sentinels
are unique within the seeded text.

If this test fails, the public mirror is broken and the M7 launch article
**must not ship** — see HANDOFF's "leak gate is the M7 blocker" line.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pytest

from fieldkit.arena.mirror import (
    FORBIDDEN_COLUMNS,
    FORBIDDEN_TABLES,
    PUBLISHABLE_TABLES,
    export_publishable_slice,
)
from fieldkit.arena.store import ArenaStore


# ---------------------------------------------------------------------------
# Sentinel injection
# ---------------------------------------------------------------------------


def _new_sentinel(label: str) -> str:
    """A sentinel guaranteed to be unique within the seeded DB."""
    return f"LEAK_SENTINEL_{label}_{uuid.uuid4().hex}"


@pytest.fixture
def store(tmp_path):
    db = tmp_path / "arena.db"
    s = ArenaStore(db)
    s.initialize()
    yield s
    s.close()


@pytest.fixture
def seeded_store_with_sentinels(store):
    """Seed the DB with one of every shape, planting a unique sentinel in
    each forbidden column. Returns (store, sentinels-dict)."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    sentinels = {
        "chat_turns_content": _new_sentinel("CHAT_CONTENT"),
        "chat_turns_reasoning": _new_sentinel("CHAT_REASONING"),
        "compare_runs_prompt": _new_sentinel("COMPARE_PROMPT"),
        "compare_responses_content_A": _new_sentinel("RESPONSE_A_CONTENT"),
        "compare_responses_content_B": _new_sentinel("RESPONSE_B_CONTENT"),
        "compare_responses_reasoning_A": _new_sentinel("RESPONSE_A_REASONING"),
        "compare_responses_reasoning_B": _new_sentinel("RESPONSE_B_REASONING"),
        "lab_notes_body": _new_sentinel("LAB_NOTE_BODY"),
        "jobs_payload_json": _new_sentinel("JOBS_PAYLOAD"),
        "job_triggers_detail": _new_sentinel("JOB_TRIGGER_DETAIL"),
    }

    # Resident-brain + frontier lanes
    for lane_id in ("resident-brain", "openrouter-frontier"):
        store.upsert_lane(
            {
                "id": lane_id,
                "kind": "LlamaServerLane",
                "model": "test-model",
                "port": 0,
                "base_url": "",
                "manifest_slug": None,
                "recommended": 0,
            }
        )

    # --- chat (operator-private; the exporter must never touch this) ---
    store.upsert_chat_session(
        {
            "id": "chat-1",
            "lane_id": "resident-brain",
            "created_at": now,
            "rubric_id": None,
            "publishable": 0,
        }
    )
    store.append_chat_turn(
        {
            "session_id": "chat-1",
            "ord": 0,
            "role": "user",
            "content": sentinels["chat_turns_content"],
            "reasoning": sentinels["chat_turns_reasoning"],
            "tokens_in": 10,
            "tokens_out": None,
            "ttft_ms": None,
            "tok_per_s": None,
            "finish_reason": None,
            "created_at": now,
        }
    )

    # --- compare (publishable shape — exporter reads the publishable
    # columns but NOT prompt/content/reasoning) ---
    store.upsert_compare_run(
        {
            "id": "cr-leak",
            "prompt": sentinels["compare_runs_prompt"],
            "rubric_id": "generic-correctness",
            "lane_a_id": "resident-brain",
            "lane_b_id": "openrouter-frontier",
            "created_at": now,
            "publishable": 1,
            "redacted_prompt": "[redacted public-safe prompt]",
        }
    )
    for side, lane, content, reasoning in (
        (
            "A",
            "resident-brain",
            sentinels["compare_responses_content_A"],
            sentinels["compare_responses_reasoning_A"],
        ),
        (
            "B",
            "openrouter-frontier",
            sentinels["compare_responses_content_B"],
            sentinels["compare_responses_reasoning_B"],
        ),
    ):
        store.upsert_compare_response(
            {
                "compare_run_id": "cr-leak",
                "side": side,
                "lane_id": lane,
                "content": content,
                "reasoning": reasoning,
                "tokens_out": 100,
                "ttft_ms": 100.0,
                "tok_per_s": 50.0,
                "unified_peak_gb": 35.0,
            }
        )
    for side in ("A", "B"):
        store.append_rubric_score(
            {
                "compare_run_id": "cr-leak",
                "chat_turn_id": None,
                "side": side,
                "rubric_id": "generic-correctness",
                "total": 1.0,
                "checks_json": json.dumps([]),
                "scored_at": now,
            }
        )

    # --- Lab notes (v0.2; operator-private — the exporter must never touch) ---
    store.append_lab_note(
        {
            "card_id": "frontier-scatter",
            "lane": "now",
            "body": sentinels["lab_notes_body"],
            "created_at": now,
            "updated_at": None,
        }
    )

    # --- M8 jobs + job_triggers (control-plane queue; operator-private —
    # the exporter must never touch these; R13) ---
    store.enqueue_job(
        {
            "id": "job-leak",
            "kind": "eval_rerun",
            "status": "queued",
            "trigger": "manual",
            "priority": 0,
            "payload_json": json.dumps(
                {"secret_prompt": sentinels["jobs_payload_json"]}
            ),
            "dedup_key": None,
            "result_json": None,
            "error": None,
            "attempt": 0,
            "enqueued_at": now,
            "dispatched_at": None,
            "finished_at": None,
            "arq_job_id": None,
        }
    )
    store.record_job_trigger(
        {
            "job_id": "job-leak",
            "source": "operator",
            "detail_json": json.dumps(
                {"operator_note": sentinels["job_triggers_detail"]}
            ),
            "created_at": now,
        }
    )

    # Add some bench rows so the export doesn't trip PublishableSliceEmpty.
    conn = store.connect()
    conn.execute(
        "INSERT INTO bench_results "
        "(bench_slug, variant_label, core_pass_rate, tok_per_sec, source_path, fetched_at) "
        "VALUES (?,?,?,?,?,?)",
        ("test-bench", "v1", 0.8, 50.0, "p", now),
    )
    conn.commit()

    return store, sentinels


# ---------------------------------------------------------------------------
# The leak gate
# ---------------------------------------------------------------------------


def test_mirror_json_does_not_leak_chat_content(
    seeded_store_with_sentinels, tmp_path
):
    """**Hard M7 blocker.** No `chat_turns.content` string appears in mirror JSON."""
    store, sentinels = seeded_store_with_sentinels
    out_dir = tmp_path / "mirror"
    export_publishable_slice(store, out_dir=out_dir)

    # Scan every emitted JSON file as raw text.
    emitted_text = ""
    for path in sorted(Path(out_dir).rglob("*.json")):
        if "_staging" in path.parts:
            continue  # staging dir is empty after atomic rename anyway
        emitted_text += path.read_text(encoding="utf-8")

    # Every sentinel from every forbidden column must be absent.
    leaks: list[str] = []
    for name, sentinel in sentinels.items():
        if sentinel in emitted_text:
            leaks.append(f"{name}={sentinel!r}")
    assert not leaks, (
        f"LEAK GATE FAILED — operator-private content found in mirror JSON: "
        f"{leaks}. This is the M7-blocker per spec §4.10 risk R1. "
        f"The exporter's allowlist (fieldkit.arena.mirror.PUBLISHABLE_TABLES) "
        f"must be tightened before any public mirror push."
    )


def test_mirror_json_does_not_mention_chat_table_names(
    seeded_store_with_sentinels, tmp_path
):
    """Defense in depth: even the table NAMES of forbidden tables shouldn't
    appear in the emitted JSON. (Catches a stray ``"chat_sessions": [...]``
    array being added without removing it from FORBIDDEN_TABLES.)"""
    store, _ = seeded_store_with_sentinels
    out_dir = tmp_path / "mirror"
    export_publishable_slice(store, out_dir=out_dir)
    text = (out_dir / "leaderboard.json").read_text(encoding="utf-8")
    for table in FORBIDDEN_TABLES:
        assert table not in text, (
            f"FORBIDDEN_TABLES leak: '{table}' name appeared in mirror JSON. "
            f"Did someone add a sibling array to the exporter without "
            f"removing the table from FORBIDDEN_TABLES?"
        )


def test_publishable_tables_does_not_overlap_forbidden(seeded_store_with_sentinels):
    """The allowlist must not name any forbidden (table, column) pair."""
    overlaps = []
    for table, cols in PUBLISHABLE_TABLES.items():
        for col in cols:
            if (table, col) in FORBIDDEN_COLUMNS:
                overlaps.append(f"{table}.{col}")
        if table in FORBIDDEN_TABLES:
            overlaps.append(f"{table} (whole table)")
    assert not overlaps, (
        f"PUBLISHABLE_TABLES leaked into FORBIDDEN_COLUMNS/TABLES: {overlaps}"
    )


def test_publishable_compare_runs_does_not_include_prompt():
    """Anchor test — explicit per spec §4.10."""
    cols = PUBLISHABLE_TABLES["compare_runs"]
    assert "prompt" not in cols
    assert "redacted_prompt" in cols  # opt-in promote target lives here


def test_publishable_compare_responses_does_not_include_content_or_reasoning():
    """Anchor test — explicit per spec §4.10."""
    cols = PUBLISHABLE_TABLES["compare_responses"]
    assert "content" not in cols
    assert "reasoning" not in cols


def test_publishable_tables_does_not_list_any_chat_table():
    """Anchor test — explicit per spec §4.10."""
    for table in FORBIDDEN_TABLES:
        assert table not in PUBLISHABLE_TABLES


def test_lab_notes_is_forbidden():
    """v0.2 anchor — the Lab annotation table is operator-private and must be
    on the FORBIDDEN allowlist + out of PUBLISHABLE_TABLES."""
    assert "lab_notes" in FORBIDDEN_TABLES
    assert "lab_notes" not in PUBLISHABLE_TABLES
    assert ("lab_notes", "body") in FORBIDDEN_COLUMNS


def test_jobs_tables_are_forbidden():
    """M8 anchor (R13) — the control-plane queue is operator-private: ``jobs``
    payloads carry prompts/lanes/benches, ``job_triggers`` carries operator
    notes. Both must be on FORBIDDEN_TABLES + out of PUBLISHABLE_TABLES, and
    the payload column must be on FORBIDDEN_COLUMNS."""
    assert "jobs" in FORBIDDEN_TABLES
    assert "job_triggers" in FORBIDDEN_TABLES
    assert "jobs" not in PUBLISHABLE_TABLES
    assert "job_triggers" not in PUBLISHABLE_TABLES
    assert ("jobs", "payload_json") in FORBIDDEN_COLUMNS


def test_leaderboard_baseline_is_forbidden():
    """M8 anchor — the regression-detector baseline is control-plane-internal
    (derived from forbidden ``eval_scores``); off the mirror alongside ``jobs``."""
    assert "leaderboard_baseline" in FORBIDDEN_TABLES
    assert "leaderboard_baseline" not in PUBLISHABLE_TABLES
