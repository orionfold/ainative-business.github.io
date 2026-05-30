# Copyright 2026 Manav Sehgal
# SPDX-License-Identifier: Apache-2.0
"""Tests for `fieldkit.arena.store.ArenaStore` — schema + upserts + reads."""

from __future__ import annotations

import json
import sqlite3

import pytest

from fieldkit.arena.schemas import (
    ArticleIndexRow,
    BenchResultRow,
    ChatSessionRecord,
    ChatTurnRecord,
    CompareResponseRecord,
    CompareRunRecord,
    HfMetaRow,
    HumanPrefRecord,
    LaneRecord,
    LeaderboardRow,
    NotebookExportRow,
    RubricScoreRecord,
)
from fieldkit.arena.store import USER_VERSION, ArenaStore


@pytest.fixture
def store(tmp_path):
    db = tmp_path / "arena.db"
    s = ArenaStore(db)
    s.initialize()
    yield s
    s.close()


def test_initialize_is_idempotent(tmp_path):
    db = tmp_path / "arena.db"
    s = ArenaStore(db)
    s.initialize()
    s.initialize()  # second call must not raise
    expected = {
        "lanes",
        "chat_sessions",
        "chat_turns",
        "compare_runs",
        "compare_responses",
        "rubric_scores",
        "leaderboard_rows",
        "human_prefs",
        "eval_runs",
        "bench_results",
        "article_index",
        "hf_meta",
        "notebook_export",
    }
    actual = set(s.table_names())
    assert expected.issubset(actual)
    assert s.user_version == USER_VERSION
    s.close()


def test_pragma_journal_mode_wal(store):
    cur = store.connect().execute("PRAGMA journal_mode")
    assert cur.fetchone()[0].lower() == "wal"


def test_count_unknown_table_is_zero(store):
    assert store.count("does_not_exist") == 0


def test_lane_upsert_then_read(store):
    from dataclasses import asdict

    store.upsert_lane(
        asdict(
            LaneRecord(
                id="moe-q4km",
                kind="LlamaServerLane",
                model="Qwen3-30B-A3B-Q4_K_M",
                port=8080,
                base_url="http://127.0.0.1:8080",
                manifest_slug="patent-strategist-v3-nemo-gguf",
                recommended=1,
            )
        )
    )
    rows = store.lanes()
    assert len(rows) == 1
    assert rows[0]["id"] == "moe-q4km"
    assert rows[0]["kind"] == "LlamaServerLane"


def test_upsert_replaces_on_conflict(store):
    from dataclasses import asdict

    base = LaneRecord(
        id="lane-a", kind="NIMLane", model="m1", port=8000, base_url="http://x"
    )
    store.upsert_lane(asdict(base))
    store.upsert_lane(
        asdict(
            LaneRecord(
                id="lane-a",
                kind="NIMLane",
                model="m2",  # changed
                port=8000,
                base_url="http://x",
                recommended=1,
            )
        )
    )
    rows = store.lanes()
    assert len(rows) == 1  # not duplicated
    assert rows[0]["model"] == "m2"
    assert rows[0]["recommended"] == 1


def test_bench_results_composite_key(store):
    from dataclasses import asdict

    store.upsert_bench_result(
        asdict(
            BenchResultRow(
                bench_slug="brain",
                variant_label="moe",
                core_pass_rate=0.9,
                tok_per_sec=83.5,
                source_path="x",
                fetched_at="now",
            )
        )
    )
    store.upsert_bench_result(
        asdict(
            BenchResultRow(
                bench_slug="brain",
                variant_label="nim",
                core_pass_rate=0.78,
                source_path="x",
                fetched_at="now",
            )
        )
    )
    assert store.count("bench_results") == 2
    assert len(store.bench_results("brain")) == 2
    assert len(store.bench_results("other")) == 0


def test_article_upsert(store):
    from dataclasses import asdict

    store.upsert_article(
        asdict(
            ArticleIndexRow(
                slug="foo",
                title="Foo",
                source_path="articles/foo/article.md",
                fetched_at="now",
                series="Cockpit",
                stage="agentic",
                customer_linked=1,
                fieldkit_modules_json=json.dumps(["arena", "harness"]),
            )
        )
    )
    rows = store.articles()
    assert len(rows) == 1
    assert rows[0]["series"] == "Cockpit"
    assert json.loads(rows[0]["fieldkit_modules_json"]) == ["arena", "harness"]


def test_hf_meta_records_errors_as_data(store):
    from dataclasses import asdict

    store.upsert_hf_meta(
        asdict(
            HfMetaRow(
                repo_id="Orionfold/foo",
                fetched_at="now",
                error="HTTP 401 — unauthorized",
            )
        )
    )
    rows = list(store.connect().execute("SELECT * FROM hf_meta"))
    assert len(rows) == 1
    assert rows[0]["error"].startswith("HTTP")


def test_notebook_export_path_keyed(store):
    from dataclasses import asdict

    store.upsert_notebook_export(
        asdict(
            NotebookExportRow(
                file_path="notebooks/patent-strategist/exports/builder/x.png",
                fetched_at="now",
                artifact_slug="patent-strategist-notebooks",
                role="builder",
                kind="png",
            )
        )
    )
    # Re-upsert same path must not duplicate
    store.upsert_notebook_export(
        asdict(
            NotebookExportRow(
                file_path="notebooks/patent-strategist/exports/builder/x.png",
                fetched_at="newer",
                artifact_slug="patent-strategist-notebooks",
                role="builder",
                kind="png",
            )
        )
    )
    assert store.count("notebook_export") == 1


def test_leaderboard_row_composite_key(store):
    from dataclasses import asdict

    # Need a lane to satisfy FK
    store.upsert_lane(
        asdict(
            LaneRecord(
                id="lane-a", kind="NIMLane", model="m", port=8000, base_url=""
            )
        )
    )
    store.upsert_leaderboard_row(
        asdict(
            LeaderboardRow(
                bench_id="b", lane_id="lane-a", n_runs=5, mean_score=0.9, last_run_at="now"
            )
        )
    )
    rows = store.leaderboard_rows()
    assert len(rows) == 1
    assert rows[0]["mean_score"] == 0.9


def test_transaction_rolls_back_on_exception(store):
    from dataclasses import asdict

    store.upsert_lane(
        asdict(LaneRecord(id="lane-x", kind="NIMLane", model="m", port=0, base_url=""))
    )
    try:
        with store.transaction() as conn:
            conn.execute(
                "INSERT INTO lanes (id, kind, model, port, base_url) "
                "VALUES ('lane-y', 'NIMLane', 'm', 0, '')"
            )
            raise RuntimeError("boom")
    except RuntimeError:
        pass
    ids = {r["id"] for r in store.lanes()}
    assert ids == {"lane-x"}  # 'lane-y' rolled back


def test_count_lanes_after_no_writes_is_zero(tmp_path):
    db = tmp_path / "fresh.db"
    s = ArenaStore(db)
    s.initialize()
    assert s.count("lanes") == 0
    s.close()


# ---------------------------------------------------------------------------
# M4 — chat session + turn persistence
# ---------------------------------------------------------------------------


def _seed_lane(store):
    """The ``chat_sessions.lane_id`` is a FK to ``lanes.id`` — seed a row."""
    store.upsert_lane(
        LaneRecord(
            id="resident-brain",
            kind="LlamaServerLane",
            model="qwen-fixture",
            port=8080,
            base_url="http://127.0.0.1:8080/v1",
        )
    )


def test_chat_session_round_trip(store):
    _seed_lane(store)
    store.upsert_chat_session(
        ChatSessionRecord(
            id="cs-aaa",
            lane_id="resident-brain",
            created_at="2026-05-28T16:00:00Z",
        )
    )
    row = store.chat_session("cs-aaa")
    assert row is not None
    assert row["lane_id"] == "resident-brain"
    assert row["publishable"] == 0  # operator-private default per spec §4.8


def test_chat_session_replaces_on_conflict(store):
    _seed_lane(store)
    store.upsert_chat_session(
        ChatSessionRecord(
            id="cs-aaa",
            lane_id="resident-brain",
            created_at="2026-05-28T16:00:00Z",
        )
    )
    store.upsert_chat_session(
        ChatSessionRecord(
            id="cs-aaa",
            lane_id="resident-brain",
            created_at="2026-05-28T17:00:00Z",
            rubric_id="generic-correctness",
        )
    )
    row = store.chat_session("cs-aaa")
    assert row["created_at"] == "2026-05-28T17:00:00Z"
    assert row["rubric_id"] == "generic-correctness"
    # Idempotent — still one row.
    assert store.count("chat_sessions") == 1


def test_chat_turn_append_and_read(store):
    _seed_lane(store)
    store.upsert_chat_session(
        ChatSessionRecord(
            id="cs-bbb",
            lane_id="resident-brain",
            created_at="2026-05-28T16:00:00Z",
        )
    )
    uid = store.append_chat_turn(
        ChatTurnRecord(
            session_id="cs-bbb",
            ord=0,
            role="user",
            content="hi",
            created_at="2026-05-28T16:00:00Z",
        )
    )
    aid = store.append_chat_turn(
        ChatTurnRecord(
            session_id="cs-bbb",
            ord=1,
            role="assistant",
            content="hello",
            reasoning="thinking …",
            tokens_out=4,
            ttft_ms=420.5,
            tok_per_s=83.4,
            finish_reason="stop",
            created_at="2026-05-28T16:00:01Z",
        )
    )
    assert uid > 0 and aid > uid

    rows = store.chat_turns("cs-bbb")
    assert [r["ord"] for r in rows] == [0, 1]
    assert rows[0]["role"] == "user"
    assert rows[1]["role"] == "assistant"
    assert rows[1]["reasoning"] == "thinking …"
    assert abs(rows[1]["tok_per_s"] - 83.4) < 1e-6


def test_chat_turn_duplicate_ord_raises(store):
    """`chat_turns (session_id, ord)` is UNIQUE — re-using ord is a
    programming error worth surfacing rather than silently overwriting."""
    _seed_lane(store)
    store.upsert_chat_session(
        ChatSessionRecord(
            id="cs-ccc",
            lane_id="resident-brain",
            created_at="2026-05-28T16:00:00Z",
        )
    )
    store.append_chat_turn(
        ChatTurnRecord(
            session_id="cs-ccc",
            ord=0,
            role="user",
            content="hi",
            created_at="2026-05-28T16:00:00Z",
        )
    )
    with pytest.raises(sqlite3.IntegrityError):
        store.append_chat_turn(
            ChatTurnRecord(
                session_id="cs-ccc",
                ord=0,  # same ord — must trip UNIQUE
                role="user",
                content="dup",
                created_at="2026-05-28T16:00:00Z",
            )
        )


# ---------------------------------------------------------------------------
# M5 — compare / rubric_scores / human_prefs round-trips
# ---------------------------------------------------------------------------


def _seed_compare_lanes(store):
    """The compare_runs FKs both A + B lanes — seed two ``lanes`` rows."""
    store.upsert_lane(
        LaneRecord(
            id="resident-brain",
            kind="LlamaServerLane",
            model="qwen-fixture",
            port=8080,
            base_url="http://127.0.0.1:8080/v1",
        )
    )
    store.upsert_lane(
        LaneRecord(
            id="openrouter-frontier",
            kind="RemoteLane",
            model="anthropic/claude-opus-4.1",
            port=443,
            base_url="https://openrouter.ai/api/v1",
        )
    )


def test_compare_run_round_trip(store):
    """A `compare_runs` row + two `compare_responses` rows + one
    `rubric_scores` per side land in three append-only tables that read
    back cleanly via the M5 helpers."""
    _seed_compare_lanes(store)
    store.upsert_compare_run(
        CompareRunRecord(
            id="cr-aaa111",
            prompt="What is the validity standard for §103 obviousness?",
            rubric_id="patent_claim_validity",
            lane_a_id="resident-brain",
            lane_b_id="openrouter-frontier",
            created_at="2026-05-28T18:00:00Z",
        )
    )
    store.upsert_compare_response(
        CompareResponseRecord(
            compare_run_id="cr-aaa111",
            side="A",
            lane_id="resident-brain",
            content="Obviousness under §103 …",
            tokens_out=128,
            ttft_ms=412.0,
            tok_per_s=83.5,
        )
    )
    store.upsert_compare_response(
        CompareResponseRecord(
            compare_run_id="cr-aaa111",
            side="B",
            lane_id="openrouter-frontier",
            content="The obviousness inquiry …",
            tokens_out=204,
            ttft_ms=1180.0,
            tok_per_s=42.1,
        )
    )
    a_row = store.append_rubric_score(
        RubricScoreRecord(
            rubric_id="patent_claim_validity",
            total=1.0,
            checks_json=json.dumps(
                [{"name": "check_1", "kind": "substring", "ok": True, "why": "matched 'obviousness'"}]
            ),
            scored_at="2026-05-28T18:00:30Z",
            compare_run_id="cr-aaa111",
            side="A",
        )
    )
    b_row = store.append_rubric_score(
        RubricScoreRecord(
            rubric_id="patent_claim_validity",
            total=1.0,
            checks_json=json.dumps(
                [{"name": "check_1", "kind": "substring", "ok": True, "why": "matched 'obviousness'"}]
            ),
            scored_at="2026-05-28T18:00:30Z",
            compare_run_id="cr-aaa111",
            side="B",
        )
    )
    assert a_row > 0 and b_row > a_row

    head = store.compare_run("cr-aaa111")
    assert head is not None
    assert head["rubric_id"] == "patent_claim_validity"
    assert head["publishable"] == 1  # spec §4.3 default

    sides = store.compare_responses("cr-aaa111")
    assert [r["side"] for r in sides] == ["A", "B"]
    assert sides[0]["lane_id"] == "resident-brain"
    assert sides[1]["lane_id"] == "openrouter-frontier"

    scores = store.rubric_scores_for_run("cr-aaa111")
    assert len(scores) == 2
    assert {s["side"] for s in scores} == {"A", "B"}
    assert all(s["total"] == 1.0 for s in scores)


def test_compare_response_replaces_on_conflict(store):
    """``(compare_run_id, side)`` is the composite key — re-emitting the
    same side replaces (used by the long-stream-reconnect path)."""
    _seed_compare_lanes(store)
    store.upsert_compare_run(
        CompareRunRecord(
            id="cr-bbb222",
            prompt="ping",
            rubric_id="generic-correctness",
            lane_a_id="resident-brain",
            lane_b_id="openrouter-frontier",
            created_at="2026-05-28T18:01:00Z",
        )
    )
    store.upsert_compare_response(
        CompareResponseRecord(
            compare_run_id="cr-bbb222",
            side="A",
            lane_id="resident-brain",
            content="first attempt",
        )
    )
    store.upsert_compare_response(
        CompareResponseRecord(
            compare_run_id="cr-bbb222",
            side="A",
            lane_id="resident-brain",
            content="second attempt — replaces",
            tokens_out=42,
        )
    )
    sides = store.compare_responses("cr-bbb222")
    assert len(sides) == 1
    assert sides[0]["content"] == "second attempt — replaces"
    assert sides[0]["tokens_out"] == 42


def test_human_pref_append_does_not_mutate_rubric_score(store):
    """Spec §4.3 — human prefs are a **separate signal**. Inserting a row
    must NOT change the corresponding ``rubric_scores.total``. The
    leaderboard surfaces this as a separate column at ≥5 prefs."""
    _seed_compare_lanes(store)
    store.upsert_compare_run(
        CompareRunRecord(
            id="cr-ccc333",
            prompt="claim 1 covers the embodiment",
            rubric_id="patent_claim_validity",
            lane_a_id="resident-brain",
            lane_b_id="openrouter-frontier",
            created_at="2026-05-28T18:02:00Z",
        )
    )
    store.upsert_compare_response(
        CompareResponseRecord(
            compare_run_id="cr-ccc333",
            side="A",
            lane_id="resident-brain",
            content="answer A — discusses obviousness",
        )
    )
    store.upsert_compare_response(
        CompareResponseRecord(
            compare_run_id="cr-ccc333",
            side="B",
            lane_id="openrouter-frontier",
            content="answer B — written description",
        )
    )
    score_row = store.append_rubric_score(
        RubricScoreRecord(
            rubric_id="patent_claim_validity",
            total=0.5,  # pre-pref total
            checks_json=json.dumps([{"name": "check_1", "ok": False, "why": "x"}]),
            scored_at="2026-05-28T18:02:10Z",
            compare_run_id="cr-ccc333",
            side="A",
        )
    )
    assert score_row > 0

    store.append_human_pref(
        HumanPrefRecord(
            id="hp-aaa",
            compare_run_id="cr-ccc333",
            winner="B",
            created_at="2026-05-28T18:02:20Z",
            note="B was clearer",
        )
    )
    # The rubric score's total stays at 0.5 — pref is independent.
    scores = store.rubric_scores_for_run("cr-ccc333")
    assert len(scores) == 1
    assert scores[0]["total"] == 0.5

    prefs = store.human_prefs_for_run("cr-ccc333")
    assert len(prefs) == 1
    assert prefs[0]["winner"] == "B"
    assert prefs[0]["note"] == "B was clearer"


def test_rubric_score_requires_one_of_compare_or_chat(store):
    """The SQL CHECK constraint enforces at-least-one of ``compare_run_id``
    or ``chat_turn_id``. Both NULL must trip."""
    _seed_compare_lanes(store)
    with pytest.raises(sqlite3.IntegrityError):
        store.append_rubric_score(
            RubricScoreRecord(
                rubric_id="generic-correctness",
                total=1.0,
                checks_json="[]",
                scored_at="2026-05-28T18:03:00Z",
            )
        )
