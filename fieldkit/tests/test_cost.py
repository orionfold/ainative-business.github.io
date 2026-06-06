# Copyright 2026 Manav Sehgal
# SPDX-License-Identifier: Apache-2.0
"""`fieldkit.cost` — the Arena M9 cost plane (Bet 6).

Covers the four cost surfaces: the **4→5 ALTER migration** round-trip on a
seeded ``user_version=4`` db (R18), the **price-snapshot seed** (M9-5), the
**per-run ledger** + session-spend rehydration (M9-8), the public
**$/quality-point** read with the local-lane render (M9-4), and the
**leaderboard aggregate** computed by ``rebuild_leaderboard`` (M9-3).
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

import pytest

from fieldkit.arena.mirror import rebuild_leaderboard
from fieldkit.arena.store import USER_VERSION, ArenaStore
from fieldkit.cost import (
    H6_SNAPSHOT_ID,
    CostError,
    CostLedger,
    PriceSnapshot,
    cost_per_quality,
    seed_price_snapshot,
)


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@pytest.fixture
def store(tmp_path):
    s = ArenaStore(tmp_path / "arena.db")
    s.initialize()
    yield s
    s.close()


# ---------------------------------------------------------------------------
# Schema 4→5 migration (R18)
# ---------------------------------------------------------------------------


def _build_v4_db(path) -> None:
    """A minimal pre-M9 (``user_version=4``) db: old table shapes, real rows."""
    c = sqlite3.connect(str(path))
    c.executescript(
        """
        CREATE TABLE lanes (id TEXT PRIMARY KEY, kind TEXT NOT NULL,
            model TEXT NOT NULL, port INTEGER NOT NULL, base_url TEXT NOT NULL,
            manifest_slug TEXT, recommended INTEGER NOT NULL DEFAULT 0);
        CREATE TABLE chat_sessions (id TEXT PRIMARY KEY, lane_id TEXT NOT NULL,
            created_at TEXT NOT NULL, rubric_id TEXT,
            publishable INTEGER NOT NULL DEFAULT 0);
        CREATE TABLE chat_turns (id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL, ord INTEGER NOT NULL, role TEXT NOT NULL,
            content TEXT NOT NULL, reasoning TEXT, tokens_in INTEGER,
            tokens_out INTEGER, ttft_ms REAL, tok_per_s REAL,
            finish_reason TEXT, created_at TEXT NOT NULL, UNIQUE(session_id, ord));
        CREATE TABLE compare_runs (id TEXT PRIMARY KEY, prompt TEXT NOT NULL,
            rubric_id TEXT NOT NULL, lane_a_id TEXT NOT NULL,
            lane_b_id TEXT NOT NULL, created_at TEXT NOT NULL,
            publishable INTEGER NOT NULL DEFAULT 1, redacted_prompt TEXT);
        CREATE TABLE compare_responses (compare_run_id TEXT NOT NULL,
            side TEXT NOT NULL, lane_id TEXT NOT NULL, content TEXT NOT NULL,
            reasoning TEXT, tokens_out INTEGER, ttft_ms REAL, tok_per_s REAL,
            unified_peak_gb REAL, PRIMARY KEY (compare_run_id, side));
        CREATE TABLE leaderboard_rows (bench_id TEXT NOT NULL,
            lane_id TEXT NOT NULL, manifest_slug TEXT, n_runs INTEGER NOT NULL,
            mean_score REAL NOT NULL, median_tok_per_s REAL, mean_ttft_ms REAL,
            human_pref_winrate REAL, last_run_at TEXT NOT NULL,
            PRIMARY KEY (bench_id, lane_id));
        """
    )
    c.execute("INSERT INTO lanes VALUES ('L1','k','m',8080,'http://x',NULL,0)")
    c.execute(
        "INSERT INTO compare_runs VALUES "
        "('R1','secret prompt','rub','L1','L1','t',1,NULL)"
    )
    c.execute(
        "INSERT INTO compare_responses "
        "(compare_run_id,side,lane_id,content,tokens_out) "
        "VALUES ('R1','A','L1','ans',42)"
    )
    c.execute(
        "INSERT INTO leaderboard_rows VALUES ('b','L1',NULL,1,0.8,10,5,NULL,'t')"
    )
    c.execute("PRAGMA user_version=4")
    c.commit()
    c.close()


def test_migration_v4_to_v5_round_trip(tmp_path):
    """R18 — a seeded ``user_version=4`` db migrates additively to 5: existing
    rows are preserved, the cost columns appear (defaulted), and the price
    snapshot is seeded."""
    db = tmp_path / "v4.db"
    _build_v4_db(db)

    store = ArenaStore(db)
    store.initialize()
    conn = store.connect()

    # Migrates to the current pin (M9's 4→5 cost ALTER + M10's 5→6 new tables).
    assert store.user_version == USER_VERSION

    # New columns exist on every altered table.
    cr_cols = {r[1] for r in conn.execute("PRAGMA table_info(compare_responses)")}
    assert {"tokens_in", "cost_usd", "tokens_estimated", "price_snapshot_id"} <= cr_cols
    ct_cols = {r[1] for r in conn.execute("PRAGMA table_info(chat_turns)")}
    assert {"cost_usd", "tokens_estimated"} <= ct_cols
    lb_cols = {r[1] for r in conn.execute("PRAGMA table_info(leaderboard_rows)")}
    assert {"mean_cost_usd", "cost_per_quality_point"} <= lb_cols

    # Existing data survived the ALTER (non-destructive).
    assert conn.execute("SELECT prompt FROM compare_runs").fetchone()[0] == "secret prompt"
    row = conn.execute(
        "SELECT content, tokens_out, cost_usd, tokens_estimated "
        "FROM compare_responses WHERE compare_run_id='R1'"
    ).fetchone()
    assert row[0] == "ans" and row[1] == 42
    assert row[2] is None  # cost defaults NULL on the back-filled row
    assert row[3] == 1  # tokens_estimated NOT NULL DEFAULT 1

    # Snapshot seeded.
    assert store.count("openrouter_price_snapshot") == 2
    store.close()


def test_initialize_is_idempotent(store):
    """Re-running initialize() over a v5 db is a no-op (no dup columns / rows)."""
    before = store.count("openrouter_price_snapshot")
    store.initialize()
    assert store.user_version == USER_VERSION
    assert store.count("openrouter_price_snapshot") == before == 2


# ---------------------------------------------------------------------------
# Price snapshot (M9-5)
# ---------------------------------------------------------------------------


def test_seed_price_snapshot_default_h6(store):
    n = seed_price_snapshot(store)  # idempotent re-seed
    assert n == 2
    led = CostLedger(store)
    opus = led.price_for("anthropic/claude-opus-4.1")
    assert isinstance(opus, PriceSnapshot)
    assert opus.snapshot_id == H6_SNAPSHOT_ID
    assert opus.price_per_m_input_usd == 15.0
    assert opus.price_per_m_output_usd == 75.0
    assert opus.source == "h6_evidence"
    # Cost math.
    assert opus.cost_usd(tokens_in=1_000_000, tokens_out=0) == pytest.approx(15.0)
    assert opus.cost_usd(tokens_in=0, tokens_out=2_000_000) == pytest.approx(150.0)


def test_price_for_unknown_model_is_none(store):
    assert CostLedger(store).price_for("does/not-exist") is None


def test_reseed_under_new_snapshot_id_preserves_old(store):
    """R19 fallback + the BUG-3 default flip — a re-seed lands under a fresh id;
    the **freshest** row wins the default read (so a refresh actually arms G3),
    while a pinned read keeps the baseline reproducible."""
    seed_price_snapshot(
        store,
        prices=[
            {
                "model_id": "anthropic/claude-opus-4.1",
                "price_per_m_input_usd": 99.0,
                "price_per_m_output_usd": 199.0,
            }
        ],
        snapshot_id="reseed-2026-06",
        source="fallback",
        captured_at="2026-06-06T00:00:00Z",  # newer than the H6 baseline
    )
    led = CostLedger(store)
    # Default read = the freshest capture (the pre-BUG-3 default pinned this to
    # the stale H6 baseline — exactly how the cost cap ran silently inert).
    assert led.price_for("anthropic/claude-opus-4.1").price_per_m_input_usd == 99.0
    # Pinned reads stay reproducible — the baseline row is intact.
    base = led.price_for("anthropic/claude-opus-4.1", snapshot_id=H6_SNAPSHOT_ID)
    assert base.price_per_m_input_usd == 15.0
    fresh = led.price_for("anthropic/claude-opus-4.1", snapshot_id="reseed-2026-06")
    assert fresh.price_per_m_input_usd == 99.0


# ---------------------------------------------------------------------------
# BUG-3 / AF-29 — the live price-refresh path
# ---------------------------------------------------------------------------


def test_refresh_prices_seeds_dated_snapshot_and_wins_default_read(store):
    from fieldkit.cost import refresh_prices

    def _fake_fetch(model_ids):
        assert list(model_ids) == ["deepseek/deepseek-r1"]
        return [
            {
                "model_id": "deepseek/deepseek-r1",
                "price_per_m_input_usd": 0.4,
                "price_per_m_output_usd": 2.0,
            }
        ]

    rows = refresh_prices(
        store, ["deepseek/deepseek-r1"], fetcher=_fake_fetch, now_iso="2026-06-06T12:00:00Z"
    )
    assert len(rows) == 1
    assert rows[0]["snapshot_id"] == "or-refresh-2026-06-06"
    led = CostLedger(store)
    p = led.price_for("deepseek/deepseek-r1")
    assert p is not None and p.price_per_m_output_usd == 2.0
    assert p.source == "openrouter-api"
    assert p.captured_at == "2026-06-06T12:00:00Z"


def test_refresh_prices_empty_fetch_is_noop(store):
    from fieldkit.cost import refresh_prices

    assert refresh_prices(store, ["nope/none"], fetcher=lambda m: []) == []
    assert CostLedger(store).price_for("nope/none") is None


def test_fetch_openrouter_prices_parses_catalog(monkeypatch):
    """The catalog read converts per-token strings → per-M floats, filters to
    the requested ids, and omits un-priceable entries."""
    import httpx

    from fieldkit import cost as cost_mod

    payload = {
        "data": [
            {"id": "deepseek/deepseek-r1", "pricing": {"prompt": "0.0000004", "completion": "0.000002"}},
            {"id": "anthropic/claude-haiku-4.5", "pricing": {"prompt": "0.000001", "completion": "0.000005"}},
            {"id": "other/model", "pricing": {"prompt": "0.000001", "completion": "0.000001"}},
            {"id": "broken/no-pricing", "pricing": {}},
        ]
    }

    def _fake_get(url, headers=None, timeout=None):
        assert "openrouter.ai" in url
        return httpx.Response(200, json=payload, request=httpx.Request("GET", url))

    monkeypatch.setattr(httpx, "get", _fake_get)
    rows = cost_mod.fetch_openrouter_prices(["deepseek/deepseek-r1", "broken/no-pricing"])
    assert rows == [
        {
            "model_id": "deepseek/deepseek-r1",
            "price_per_m_input_usd": 0.4,
            "price_per_m_output_usd": 2.0,
        }
    ]


def test_fetch_openrouter_prices_failure_raises_cost_error(monkeypatch):
    import httpx

    from fieldkit import cost as cost_mod

    def _boom(url, headers=None, timeout=None):
        raise httpx.ConnectError("offline")

    monkeypatch.setattr(httpx, "get", _boom)
    with pytest.raises(CostError, match="price fetch failed"):
        cost_mod.fetch_openrouter_prices(["x/y"])


def test_seed_bad_row_raises(store):
    with pytest.raises(CostError):
        seed_price_snapshot(store, prices=[{"model_id": "x"}])  # missing prices


# ---------------------------------------------------------------------------
# Per-run ledger + session spend (M9-8)
# ---------------------------------------------------------------------------


def _seed_one_compare(store, *, cost_a, cost_b, score=1.0):
    now = _now()
    for lane in ("local", "frontier"):
        store.upsert_lane(
            {
                "id": lane,
                "kind": "k",
                "model": "m",
                "port": 0,
                "base_url": "",
                "manifest_slug": None,
                "recommended": 0,
            }
        )
    store.upsert_compare_run(
        {
            "id": "c1",
            "prompt": "p",
            "rubric_id": "rub",
            "lane_a_id": "local",
            "lane_b_id": "frontier",
            "created_at": now,
            "publishable": 1,
            "redacted_prompt": None,
        }
    )
    for side, lane, cost in (("A", "local", cost_a), ("B", "frontier", cost_b)):
        store.upsert_compare_response(
            {
                "compare_run_id": "c1",
                "side": side,
                "lane_id": lane,
                "content": "ans",
                "tokens_out": 100,
                "tok_per_s": 50.0,
                "ttft_ms": 100.0,
                "cost_usd": cost,
                "tokens_in": 20,
                "tokens_estimated": 1,
                "price_snapshot_id": H6_SNAPSHOT_ID if cost else None,
            }
        )
        store.append_rubric_score(
            {
                "compare_run_id": "c1",
                "chat_turn_id": None,
                "side": side,
                "rubric_id": "rub",
                "total": score,
                "checks_json": "[]",
                "scored_at": now,
            }
        )


def test_session_spend_sums_persisted_rows(store):
    _seed_one_compare(store, cost_a=0.0, cost_b=0.0123)
    total, calls = CostLedger(store).session_spend()
    assert total == pytest.approx(0.0123)
    assert calls == 1  # only the priced (frontier) side counts as a paid run


def test_session_spend_empty_is_zero(store):
    assert CostLedger(store).session_spend() == (0.0, 0)


def test_session_spend_folds_eval_job_guardrail_cost(store):
    """AF-30 — metered eval spend (jobs.result_json.guardrail.run_cost_usd)
    counts toward session spend; the governor/standup were blind to it (the
    smoke showed $0.0023 while ~$0.18 of real eval spend sat invisible)."""
    import json as _json

    from fieldkit.arena import jobs as jobs_mod
    from fieldkit.arena.jobs import JobKind, JobStatus

    _seed_one_compare(store, cost_a=0.0, cost_b=0.0123)
    jid = jobs_mod.enqueue_job(
        store,
        JobKind.EVAL_RERUN,
        {"lane_id": "openrouter::claude-haiku-4.5", "bench_id": "b",
         "base_url": "https://openrouter.ai/api/v1", "model": "anthropic/claude-haiku-4.5"},
    )
    store.update_job(
        jid,
        status=JobStatus.DONE,
        result_json=_json.dumps({"guardrail": {"run_cost_usd": 0.0515, "priced": True}}),
    )
    # An unpriced/zero-cost eval contributes nothing.
    jid2 = jobs_mod.enqueue_job(
        store,
        JobKind.EVAL_RERUN,
        {"lane_id": "openrouter::x", "bench_id": "b2",
         "base_url": "https://openrouter.ai/api/v1", "model": "x/y"},
    )
    store.update_job(
        jid2,
        status=JobStatus.DONE,
        result_json=_json.dumps({"guardrail": {"run_cost_usd": 0.0, "priced": False}}),
    )
    total, calls = CostLedger(store).session_spend()
    assert total == pytest.approx(0.0123 + 0.0515)
    assert calls == 2  # the paid compare side + the paid eval run


# ---------------------------------------------------------------------------
# Leaderboard aggregate + $/quality-point (M9-3 / M9-4)
# ---------------------------------------------------------------------------


def test_rebuild_leaderboard_computes_cost_aggregates(store):
    _seed_one_compare(store, cost_a=0.0, cost_b=0.02, score=0.5)
    rebuild_leaderboard(store)

    # Local lane → mean_cost 0, cost_per_quality 0 → renders "$0 (local)".
    local = cost_per_quality(store, "cockpit:rub", "local")
    assert local is not None
    assert local["mean_cost_usd"] == pytest.approx(0.0)
    assert local["is_local"] is True
    assert local["display"] == "$0 (local)"

    # Frontier lane → mean_cost 0.02, score 0.5 → $0.04/pt.
    frontier = cost_per_quality(store, "cockpit:rub", "frontier")
    assert frontier["mean_cost_usd"] == pytest.approx(0.02)
    assert frontier["cost_per_quality_point"] == pytest.approx(0.04)
    assert frontier["is_local"] is False
    assert frontier["display"] == "$0.0400/pt"


def test_cost_per_quality_missing_pair_is_none(store):
    assert cost_per_quality(store, "nope", "nope") is None
