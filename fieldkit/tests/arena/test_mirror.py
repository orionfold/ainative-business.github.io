# Copyright 2026 Manav Sehgal
# SPDX-License-Identifier: Apache-2.0
"""Tests for ``fieldkit.arena.mirror`` — exporter + rebuild + atomic write.

The *leak* contract has its own file (``test_mirror_does_not_leak.py``) so
the M7-blocker gate is easy to invoke from CI in isolation.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone

import pytest

from fieldkit.arena import PublishableSliceEmpty
from fieldkit.arena.mirror import (
    MIRROR_SCHEMA_VERSION,
    ExportReport,
    RebuildReport,
    export_publishable_slice,
    rebuild_leaderboard,
)
from fieldkit.arena.store import ArenaStore


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def store(tmp_path):
    db = tmp_path / "arena.db"
    s = ArenaStore(db)
    s.initialize()
    yield s
    s.close()


def _seed_lane(store: ArenaStore, lane_id: str, *, kind: str = "LlamaServerLane") -> None:
    store.upsert_lane(
        {
            "id": lane_id,
            "kind": kind,
            "model": "test-model",
            "port": 0,
            "base_url": "",
            "manifest_slug": None,
            "recommended": 0,
        }
    )


def _seed_bench_results(store: ArenaStore) -> None:
    """Two benches × a few variants — gives rebuild something to promote."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    conn = store.connect()
    rows = [
        ("bench-a", "v1", 0.8, 50.0, None, None, None, "p", now),
        ("bench-a", "v2", 0.9, 60.0, None, None, None, "p", now),
        ("bench-b", "v1", 0.7, None, None, None, None, "p", now),
        # NULL pass-rate row — rebuild must skip it
        ("bench-c", "v1", None, 99.0, None, None, None, "p", now),
    ]
    conn.executemany(
        "INSERT OR REPLACE INTO bench_results "
        "(bench_slug, variant_label, core_pass_rate, tok_per_sec, p50_s, p95_s, "
        " wall_mean_s, source_path, fetched_at) "
        "VALUES (?,?,?,?,?,?,?,?,?)",
        rows,
    )
    conn.commit()


def _seed_compare_run(
    store: ArenaStore,
    *,
    run_id: str,
    rubric_id: str,
    a_lane: str,
    b_lane: str,
    a_score: float,
    b_score: float,
    a_tokps: float = 80.0,
    b_tokps: float = 30.0,
    publishable: int = 1,
    prompt: str = "What is novelty under §102?",
) -> None:
    """One self-consistent compare run with both responses + both scores."""
    _seed_lane(store, a_lane)
    _seed_lane(store, b_lane)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    store.upsert_compare_run(
        {
            "id": run_id,
            "prompt": prompt,
            "rubric_id": rubric_id,
            "lane_a_id": a_lane,
            "lane_b_id": b_lane,
            "created_at": now,
            "publishable": publishable,
            "redacted_prompt": "[redacted §102 novelty question]",
        }
    )
    for side, lane, tokps in (("A", a_lane, a_tokps), ("B", b_lane, b_tokps)):
        store.upsert_compare_response(
            {
                "compare_run_id": run_id,
                "side": side,
                "lane_id": lane,
                "content": f"answer-{side}",
                "reasoning": None,
                "tokens_out": 200,
                "ttft_ms": 100.0,
                "tok_per_s": tokps,
                "unified_peak_gb": 36.0,
            }
        )
    for side, total in (("A", a_score), ("B", b_score)):
        store.append_rubric_score(
            {
                "compare_run_id": run_id,
                "chat_turn_id": None,
                "side": side,
                "rubric_id": rubric_id,
                "total": total,
                "checks_json": json.dumps([{"name": "check_1", "kind": "substring", "ok": bool(total), "why": ""}]),
                "scored_at": now,
            }
        )


# ---------------------------------------------------------------------------
# rebuild_leaderboard
# ---------------------------------------------------------------------------


def test_rebuild_promotes_bench_results_with_scores(store):
    _seed_bench_results(store)
    report = rebuild_leaderboard(store)
    assert isinstance(report, RebuildReport)
    # 3 scored rows from bench_results; the NULL row is skipped.
    assert report.bench_rows_written == 3
    assert report.cockpit_rows_written == 0
    assert report.total_rows == 3


def test_rebuild_promotes_publishable_compare_runs(store):
    _seed_compare_run(
        store,
        run_id="cr-1",
        rubric_id="patent_claim_validity",
        a_lane="resident-brain",
        b_lane="openrouter-frontier",
        a_score=1.0,
        b_score=1.0,
    )
    _seed_compare_run(
        store,
        run_id="cr-2",
        rubric_id="patent_claim_validity",
        a_lane="resident-brain",
        b_lane="openrouter-frontier",
        a_score=0.0,
        b_score=1.0,
    )
    report = rebuild_leaderboard(store)
    # 2 lanes × 1 rubric = 2 cockpit rows (averaged across the 2 runs).
    assert report.bench_rows_written == 0
    assert report.cockpit_rows_written == 2
    conn = store.connect()
    rows = conn.execute(
        "SELECT lane_id, mean_score, n_runs FROM leaderboard_rows "
        "WHERE bench_id='cockpit:patent_claim_validity' ORDER BY lane_id"
    ).fetchall()
    by_lane = {r["lane_id"]: (r["mean_score"], r["n_runs"]) for r in rows}
    assert by_lane["openrouter-frontier"] == (1.0, 2)
    assert by_lane["resident-brain"] == (0.5, 2)  # (1.0 + 0.0)/2


def test_rebuild_skips_non_publishable_runs(store):
    _seed_compare_run(
        store,
        run_id="cr-x",
        rubric_id="generic-correctness",
        a_lane="A",
        b_lane="B",
        a_score=1.0,
        b_score=1.0,
        publishable=0,
    )
    report = rebuild_leaderboard(store)
    assert report.cockpit_rows_written == 0


def test_rebuild_is_idempotent(store):
    _seed_bench_results(store)
    _seed_compare_run(
        store,
        run_id="cr-id",
        rubric_id="generic-correctness",
        a_lane="A",
        b_lane="B",
        a_score=0.5,
        b_score=0.9,
    )
    r1 = rebuild_leaderboard(store)
    r2 = rebuild_leaderboard(store)
    assert (r1.bench_rows_written, r1.cockpit_rows_written) == (
        r2.bench_rows_written,
        r2.cockpit_rows_written,
    )
    assert r1.total_rows == r2.total_rows


def test_rebuild_human_pref_winrate_gated_at_5(store):
    """Per spec §4.4 — winrate is None until ≥5 prefs accumulate."""
    _seed_compare_run(
        store,
        run_id="cr-pref",
        rubric_id="generic-correctness",
        a_lane="A",
        b_lane="B",
        a_score=1.0,
        b_score=1.0,
    )
    # Add 3 prefs — under threshold
    for i in range(3):
        store.append_human_pref(
            {
                "id": f"pref-{i}",
                "compare_run_id": "cr-pref",
                "winner": "A",
                "note": None,
                "created_at": "2026-05-28T00:00:00Z",
            }
        )
    rebuild_leaderboard(store)
    row = store.connect().execute(
        "SELECT human_pref_winrate FROM leaderboard_rows "
        "WHERE bench_id='cockpit:generic-correctness' AND lane_id='A'"
    ).fetchone()
    assert row["human_pref_winrate"] is None
    # Add 2 more — now 5 total
    for i in range(3, 5):
        store.append_human_pref(
            {
                "id": f"pref-{i}",
                "compare_run_id": "cr-pref",
                "winner": "A",
                "note": None,
                "created_at": "2026-05-28T00:00:00Z",
            }
        )
    rebuild_leaderboard(store)
    row = store.connect().execute(
        "SELECT human_pref_winrate FROM leaderboard_rows "
        "WHERE bench_id='cockpit:generic-correctness' AND lane_id='A'"
    ).fetchone()
    assert row["human_pref_winrate"] == 1.0


# ---------------------------------------------------------------------------
# export_publishable_slice — happy path + shape
# ---------------------------------------------------------------------------


def test_export_writes_leaderboard_json_with_schema_v2(store, tmp_path):
    _seed_bench_results(store)
    _seed_compare_run(
        store,
        run_id="cr-1",
        rubric_id="patent_claim_validity",
        a_lane="resident-brain",
        b_lane="openrouter-frontier",
        a_score=1.0,
        b_score=1.0,
    )
    report = export_publishable_slice(store, out_dir=tmp_path / "mirror")
    assert isinstance(report, ExportReport)
    out = tmp_path / "mirror" / "leaderboard.json"
    assert out.exists()
    payload = json.loads(out.read_text())
    assert payload["schema_version"] == MIRROR_SCHEMA_VERSION
    assert payload["source"].startswith("fieldkit arena mirror")
    # Bench-anchored rows from bench_results
    assert len(payload["bench_rows"]) >= 3
    # Live-cockpit rows from compare runs
    assert len(payload["live_rows"]) == 2
    # Backward-compat: `rows` mirrors `bench_rows`
    assert payload["rows"] == payload["bench_rows"]
    # Compare detail arrays present
    assert len(payload["compare_runs"]) == 1
    assert len(payload["compare_responses"]) == 2
    assert len(payload["rubric_scores"]) == 2
    # 2 explicit (resident-brain, openrouter-frontier) +
    # 3 bench-variant stubs that rebuild auto-upserted from bench_results.
    lane_ids = {lane["id"] for lane in payload["lanes"]}
    assert "resident-brain" in lane_ids
    assert "openrouter-frontier" in lane_ids
    assert "v1::bench-a" in lane_ids  # bench-variant stub
    assert len(payload["lanes"]) == 5


def test_export_refuses_empty_by_default(store, tmp_path):
    """The empty-slice guard prevents accidentally blanking the public mirror."""
    with pytest.raises(PublishableSliceEmpty):
        export_publishable_slice(store, out_dir=tmp_path / "mirror")


def test_export_allow_empty_writes_zero_row_file(store, tmp_path):
    report = export_publishable_slice(
        store, out_dir=tmp_path / "mirror", allow_empty=True
    )
    assert report.bench_row_count == 0
    assert report.live_row_count == 0
    out = tmp_path / "mirror" / "leaderboard.json"
    payload = json.loads(out.read_text())
    assert payload["rows"] == []


def test_export_atomic_rename_uses_staging_dir(store, tmp_path):
    _seed_bench_results(store)
    out_dir = tmp_path / "mirror"
    export_publishable_slice(store, out_dir=out_dir)
    # _staging exists but should be empty after a clean export.
    staging = out_dir / "_staging"
    assert staging.exists()
    assert list(staging.iterdir()) == []  # atomic-renamed away
    # The final file landed.
    assert (out_dir / "leaderboard.json").exists()


def test_export_promotes_redacted_prompt_not_raw_prompt(store, tmp_path):
    _seed_compare_run(
        store,
        run_id="cr-redact",
        rubric_id="patent_claim_validity",
        a_lane="A",
        b_lane="B",
        a_score=1.0,
        b_score=1.0,
        prompt="RAW_PROMPT_SENTINEL_DO_NOT_LEAK",
    )
    export_publishable_slice(store, out_dir=tmp_path / "mirror")
    text = (tmp_path / "mirror" / "leaderboard.json").read_text()
    assert "RAW_PROMPT_SENTINEL_DO_NOT_LEAK" not in text
    # JSON encodes § as § (sort_keys=False, indent=2, default ensure_ascii)
    assert "redacted" in text
    assert "novelty question" in text


def test_export_skip_rebuild_preserves_existing_rows(store, tmp_path):
    """``rebuild=False`` honors a caller's pre-rebuilt leaderboard_rows."""
    # Manually seed one leaderboard row without bench_results / compare_runs.
    store.upsert_lane({"id": "manual-lane", "kind": "x", "model": "x", "port": 0, "base_url": ""})
    store.upsert_leaderboard_row(
        {
            "bench_id": "manual-bench",
            "lane_id": "manual-lane",
            "manifest_slug": None,
            "n_runs": 1,
            "mean_score": 0.42,
            "median_tok_per_s": 10.0,
            "mean_ttft_ms": None,
            "human_pref_winrate": None,
            "last_run_at": "2026-05-28T00:00:00Z",
        }
    )
    report = export_publishable_slice(
        store, out_dir=tmp_path / "mirror", rebuild=False
    )
    assert report.bench_row_count == 1
    payload = json.loads((tmp_path / "mirror" / "leaderboard.json").read_text())
    assert payload["bench_rows"][0]["mean_score"] == 0.42


def test_export_report_summary_line(store, tmp_path):
    _seed_bench_results(store)
    report = export_publishable_slice(store, out_dir=tmp_path / "mirror")
    line = report.summary_line()
    assert "bench=3" in line
    assert "live=0" in line


def test_export_report_as_dict_carries_rebuild_subreport(store, tmp_path):
    _seed_bench_results(store)
    report = export_publishable_slice(store, out_dir=tmp_path / "mirror")
    d = report.as_dict()
    assert d["counts"]["bench_rows"] == 3
    assert "rebuild" in d
    assert d["rebuild"]["bench_rows"] == 3
