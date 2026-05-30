# Copyright 2026 Manav Sehgal
# SPDX-License-Identifier: Apache-2.0
"""Tests for the live cockpit leaderboard.

Covers the shared aggregation core (`_aggregate_cockpit_rows` — compare parity
with the CLI rebuild + the chat throughput-only fold), `store.leaderboard_live`
(sort + column allowlist / no-leak), the importer's shape-3/4 ``tok_per_sec``
extraction, and the `TelemetryHub.leaderboard_rev` push signal.
"""

from __future__ import annotations

import json

import pytest

from fieldkit.arena.importer import _extract_bench_rows
from fieldkit.arena.mirror import _aggregate_cockpit_rows, _rebuild_cockpit_runs
from fieldkit.arena.server import TelemetryHub
from fieldkit.arena.store import ArenaStore

NOW = "2026-05-30T00:00:00Z"

# The only keys the live endpoint / store method may emit — numeric metrics,
# ids, timestamps. No prompt / content / reasoning / note ever.
ALLOWLIST = {
    "bench_id",
    "lane_id",
    "manifest_slug",
    "n_runs",
    "mean_score",
    "median_tok_per_s",
    "mean_ttft_ms",
    "human_pref_winrate",
    "last_run_at",
}


@pytest.fixture
def store(tmp_path):
    s = ArenaStore(tmp_path / "arena.db")
    s.initialize()
    yield s
    s.close()


def _lane(store: ArenaStore, lane_id: str) -> None:
    store.upsert_lane(
        {
            "id": lane_id,
            "kind": "x",
            "model": "m",
            "port": 0,
            "base_url": "",
            "manifest_slug": None,
            "recommended": 0,
        }
    )


def _compare(store, run_id, rubric_id, a, b, a_tok=80.0, b_tok=30.0):
    _lane(store, a)
    _lane(store, b)
    store.upsert_compare_run(
        {
            "id": run_id,
            "prompt": "secret prompt",
            "rubric_id": rubric_id,
            "lane_a_id": a,
            "lane_b_id": b,
            "created_at": NOW,
            "publishable": 1,
            "redacted_prompt": "[r]",
        }
    )
    for side, lane, tok in (("A", a, a_tok), ("B", b, b_tok)):
        store.upsert_compare_response(
            {
                "compare_run_id": run_id,
                "side": side,
                "lane_id": lane,
                "content": "secret answer",
                "reasoning": "secret reasoning",
                "tokens_out": 200,
                "ttft_ms": 100.0,
                "tok_per_s": tok,
                "unified_peak_gb": 36.0,
            }
        )
    for side, total in (("A", 1.0), ("B", 0.5)):
        store.append_rubric_score(
            {
                "compare_run_id": run_id,
                "chat_turn_id": None,
                "side": side,
                "rubric_id": rubric_id,
                "total": total,
                "checks_json": "[]",
                "scored_at": NOW,
            }
        )


def _chat(store, session_id, lane_id, tok=50.0, ttft=120.0) -> int:
    _lane(store, lane_id)
    store.upsert_chat_session(
        {
            "id": session_id,
            "lane_id": lane_id,
            "created_at": NOW,
            "rubric_id": None,
            "publishable": 0,
        }
    )
    return store.append_chat_turn(
        {
            "session_id": session_id,
            "ord": 1,
            "role": "assistant",
            "content": "secret answer",
            "reasoning": None,
            "tokens_in": None,
            "tokens_out": 100,
            "ttft_ms": ttft,
            "tok_per_s": tok,
            "finish_reason": "stop",
            "created_at": NOW,
        }
    )


def test_compare_only_parity_with_rebuild(store):
    _compare(store, "cr-1", "rub", "lane-a", "lane-b")
    agg = {
        (r["bench_id"], r["lane_id"]): r
        for r in _aggregate_cockpit_rows(store.connect(), include_chat=False)
    }
    a = agg[("cockpit:rub", "lane-a")]
    assert a["mean_score"] == 1.0
    assert a["median_tok_per_s"] == 80.0
    assert a["n_runs"] == 1
    # The CLI wrapper persists the identical aggregate.
    n = _rebuild_cockpit_runs(store.connect(), fetched_at=NOW)
    assert n == 2  # A + B sides
    rows = {
        (r["bench_id"], r["lane_id"]): r
        for r in store.connect().execute("SELECT * FROM leaderboard_rows")
    }
    assert rows[("cockpit:rub", "lane-a")]["mean_score"] == 1.0
    assert rows[("cockpit:rub", "lane-a")]["median_tok_per_s"] == 80.0
    assert rows[("cockpit:rub", "lane-a")]["last_run_at"] == NOW


def test_chat_fold_is_live_only(store):
    _chat(store, "s1", "chat-lane", tok=44.0)
    # Compare-only (CLI / public mirror): no chat rows.
    bench = {r["bench_id"] for r in _aggregate_cockpit_rows(store.connect(), include_chat=False)}
    assert "cockpit:chat" not in bench


def test_chat_fold_throughput_only_row(store):
    _chat(store, "s1", "chat-lane", tok=44.0)
    rows = {
        (r["bench_id"], r["lane_id"]): r
        for r in _aggregate_cockpit_rows(store.connect(), include_chat=True)
    }
    r = rows[("cockpit:chat", "chat-lane")]
    assert r["mean_score"] is None  # throughput-only — no quality
    assert r["median_tok_per_s"] == 44.0
    assert r["n_runs"] == 1


def test_leaderboard_live_sorts_and_is_allowlisted(store):
    _compare(store, "cr-1", "rub", "lane-a", "lane-b")
    _chat(store, "s1", "chat-lane", tok=44.0)
    rows = store.leaderboard_live(include_chat=True)
    # Scored rows rank above throughput-only (null-score) chat rows.
    assert rows[0]["mean_score"] is not None
    assert rows[-1]["mean_score"] is None
    # Column allowlist — no leaked prompt/content/reasoning text.
    for r in rows:
        assert set(r.keys()) == ALLOWLIST
        assert "secret" not in json.dumps(r)


def test_importer_extracts_tok_per_sec_vertical_router():
    data = {
        "per_vertical_quality": {"patent": {"pass_rate": 0.8, "tok_per_sec": 42.0}},
        "summary": {"vertical_pass_rates": {"patent": 0.8}},
    }
    rows = {r["variant_label"]: r for r in _extract_bench_rows(data)}
    assert rows["patent"]["tok_per_sec"] == 42.0


def test_importer_extracts_tok_per_sec_legacy_verticals():
    data = {"verticals": {"cyber": {"pass_rate": 0.7, "warm_time_s": 5.0, "tokens_per_sec": 31.0}}}
    rows = {r["variant_label"]: r for r in _extract_bench_rows(data)}
    assert rows["cyber"]["tok_per_sec"] == 31.0


def test_telemetry_hub_leaderboard_rev_push():
    hub = TelemetryHub()
    assert hub._build_payload()["leaderboard_rev"] == 0
    hub.bump_leaderboard()
    hub.bump_leaderboard()
    assert hub.leaderboard_rev == 2
    assert hub._build_payload()["leaderboard_rev"] == 2
