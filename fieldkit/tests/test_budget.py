# Copyright 2026 Manav Sehgal
# SPDX-License-Identifier: Apache-2.0
"""`fieldkit.budget` — the Arena M11 budget governor (Phase 2, §15).

Covers the governor's three verdicts on both prerequisite branches:
- **M9 present** (a wired `CostLedger`): over-daily-cap → defer; the
  `LOCAL_CEILING` failure class → escalate (AH-4); within cap + lane fits → allow.
- **M9 absent** (`ledger=None`): over-weekly-`/usage` → defer; else the
  token + OOM-envelope guard (AH-5).
- **`MemoryEnvelope.fits`** — the OOM guard defers an oversized lane (R24).
- **`SpendDigest`** — the standup Spend row, "—" on a pre-M9 db.
"""

from __future__ import annotations

import sqlite3

import pytest

from fieldkit.budget import (
    ALLOW,
    DEFER,
    ESCALATE,
    BudgetDecision,
    BudgetError,
    BudgetGovernor,
    EscalationReason,
    MemoryEnvelope,
    SpendDigest,
    check_budget,
)


# ---------------------------------------------------------------------------
# Fixtures — a db with the M9 cost plane, and one without
# ---------------------------------------------------------------------------


@pytest.fixture
def m9_conn():
    """An in-memory db carrying M9's `cost_usd` columns + a paid run."""
    c = sqlite3.connect(":memory:")
    c.execute("CREATE TABLE compare_responses (lane_id TEXT, cost_usd REAL)")
    c.execute("CREATE TABLE chat_turns (cost_usd REAL)")
    c.execute("INSERT INTO compare_responses VALUES ('claude-opus', 4.50)")
    c.execute("INSERT INTO compare_responses VALUES ('gpt-4o-mini', 0.25)")
    c.commit()
    return c


@pytest.fixture
def pre_m9_conn():
    """A pre-M9 db: compare_responses WITHOUT the cost_usd column."""
    c = sqlite3.connect(":memory:")
    c.execute("CREATE TABLE compare_responses (lane_id TEXT)")
    c.commit()
    return c


# ---------------------------------------------------------------------------
# MemoryEnvelope — the OOM guard
# ---------------------------------------------------------------------------


def test_envelope_fits_default_lane():
    env = MemoryEnvelope()  # 128 total, 31.8 brain, 5.5 default cold lane
    assert env.fits("patent") is True
    assert env.headroom_gb() == pytest.approx(96.2)


def test_envelope_rejects_oversized_lane():
    env = MemoryEnvelope(lane_gb={"giant": 200.0})
    assert env.fits("giant") is False


def test_envelope_none_lane_always_fits():
    assert MemoryEnvelope().fits(None) is True


# ---------------------------------------------------------------------------
# Governor — M9 absent branch (AH-5 degradation)
# ---------------------------------------------------------------------------


def test_m9_absent_allow_within_usage():
    g = BudgetGovernor(ledger=None)
    d = g.check_budget({"payload": {"lane_id": "patent"}}, weekly_usage_pct=10.0)
    assert d.action == ALLOW and d.reason == EscalationReason.WITHIN_BUDGET
    assert d.allowed is True


def test_m9_absent_defer_over_usage_cap():
    g = BudgetGovernor(ledger=None, weekly_usage_cap_pct=80.0)
    d = g.check_budget({"payload": {"lane_id": "patent"}}, weekly_usage_pct=95.0)
    assert d.action == DEFER and d.reason == EscalationReason.OVER_USAGE_CAP
    assert d.allowed is False


def test_m9_absent_defer_on_envelope_even_within_usage():
    g = BudgetGovernor(ledger=None, envelope=MemoryEnvelope(lane_gb={"big": 300.0}))
    d = g.check_budget({"payload": {"lane_id": "big"}}, weekly_usage_pct=0.0)
    assert d.action == DEFER and d.reason == EscalationReason.OOM_ENVELOPE


# ---------------------------------------------------------------------------
# Governor — M9 present branch (AH-4)
# ---------------------------------------------------------------------------


def test_m9_present_defer_over_daily_cap(m9_conn):
    # session spend = 4.75; a 1.0 job projects 5.75 > 5.0 cap.
    g = BudgetGovernor(ledger=m9_conn, daily_cap_usd=5.0)
    d = g.check_budget({"payload": {"lane_id": "patent", "est_cost_usd": 1.0}})
    assert d.action == DEFER and d.reason == EscalationReason.OVER_DAILY_CAP
    assert d.detail["projected_usd"] == pytest.approx(5.75)


def test_m9_present_allow_within_cap(m9_conn):
    g = BudgetGovernor(ledger=m9_conn, daily_cap_usd=100.0)
    d = g.check_budget({"payload": {"lane_id": "patent", "est_cost_usd": 1.0}})
    assert d.action == ALLOW


def test_m9_present_escalate_on_local_ceiling(m9_conn):
    g = BudgetGovernor(ledger=m9_conn, daily_cap_usd=100.0)
    d = g.check_budget(
        {"payload": {"lane_id": "patent"}, "failure_class": "multi_step_planning"}
    )
    assert d.action == ESCALATE and d.reason == EscalationReason.LOCAL_CEILING
    assert d.detail["ceiling"] == pytest.approx(0.33)


def test_m9_present_non_ceiling_failure_does_not_escalate(m9_conn):
    # A transient crash is a local problem to fix, not a frontier spend.
    g = BudgetGovernor(ledger=m9_conn, daily_cap_usd=100.0)
    d = g.check_budget(
        {"payload": {"lane_id": "patent"}, "failure_class": "crash"}
    )
    assert d.action == ALLOW


def test_spend_today_override_is_deterministic(m9_conn):
    g = BudgetGovernor(ledger=m9_conn, daily_cap_usd=5.0)
    # ignore the db's 4.75; inject 4.9 → a 0.2 job projects 5.1 > 5.0.
    d = g.check_budget(
        {"payload": {"lane_id": "x", "est_cost_usd": 0.2}}, spend_today=4.9
    )
    assert d.action == DEFER and d.reason == EscalationReason.OVER_DAILY_CAP


def test_daily_cap_precedes_escalation(m9_conn):
    # When BOTH over-cap and a ceiling failure apply, defer wins (spec order).
    g = BudgetGovernor(ledger=m9_conn, daily_cap_usd=5.0)
    d = g.check_budget(
        {
            "payload": {"lane_id": "patent", "est_cost_usd": 1.0},
            "failure_class": "kv_cache_derivation",
        }
    )
    assert d.action == DEFER and d.reason == EscalationReason.OVER_DAILY_CAP


# ---------------------------------------------------------------------------
# Payload extraction — jobs-row (payload_json) vs synthetic mapping
# ---------------------------------------------------------------------------


def test_governor_reads_payload_json_string():
    import json

    g = BudgetGovernor(ledger=None, envelope=MemoryEnvelope(lane_gb={"big": 300.0}))
    job = {"payload_json": json.dumps({"lane_id": "big"})}
    d = g.check_budget(job, weekly_usage_pct=0.0)
    assert d.action == DEFER and d.reason == EscalationReason.OOM_ENVELOPE


# ---------------------------------------------------------------------------
# SpendDigest — the standup Spend row
# ---------------------------------------------------------------------------


def test_spend_digest_m9_present(m9_conn):
    dig = SpendDigest.from_store(m9_conn, cap_usd=5.0)
    assert dig.has_cost_plane is True
    assert dig.total_usd == pytest.approx(4.75)
    assert dig.over_cap is False
    assert dig.display == "$4.7500 / $5.00"
    lanes = dict(dig.by_lane)
    assert lanes["claude-opus"] == pytest.approx(4.5)


def test_spend_digest_over_cap(m9_conn):
    dig = SpendDigest.from_store(m9_conn, cap_usd=1.0)
    assert dig.over_cap is True


def test_spend_digest_includes_eval_job_spend(m9_conn):
    """AF-30 — the Standup SPEND row counts metered eval-job spend, per-lane."""
    m9_conn.execute(
        "CREATE TABLE jobs (id TEXT, kind TEXT, payload_json TEXT, result_json TEXT)"
    )
    m9_conn.execute(
        "INSERT INTO jobs VALUES ('j1', 'eval_rerun', "
        "'{\"lane_id\": \"openrouter::claude-haiku-4.5\"}', "
        "'{\"guardrail\": {\"run_cost_usd\": 0.0515, \"priced\": true}}')"
    )
    m9_conn.commit()
    dig = SpendDigest.from_store(m9_conn, cap_usd=5.0)
    assert dig.total_usd == pytest.approx(4.75 + 0.0515)
    lanes = dict(dig.by_lane)
    assert lanes["openrouter::claude-haiku-4.5"] == pytest.approx(0.0515)


def test_spend_digest_pre_m9_is_dash(pre_m9_conn):
    dig = SpendDigest.from_store(pre_m9_conn, cap_usd=5.0)
    assert dig.has_cost_plane is False
    assert dig.total_usd is None
    assert dig.display == "—"
    assert dig.as_dict()["by_lane"] == []


# ---------------------------------------------------------------------------
# check_budget convenience + error surface
# ---------------------------------------------------------------------------


def test_check_budget_convenience_allows():
    d = check_budget({"payload": {"lane_id": "patent"}}, weekly_usage_pct=0.0)
    assert isinstance(d, BudgetDecision) and d.action == ALLOW


def test_governor_spend_digest_no_ledger_is_dash():
    g = BudgetGovernor(ledger=None, daily_cap_usd=7.0)
    dig = g.spend_digest()
    assert dig.has_cost_plane is False and dig.cap_usd == 7.0


def test_bad_store_raises_budget_error():
    with pytest.raises(BudgetError):
        SpendDigest.from_store(object())
