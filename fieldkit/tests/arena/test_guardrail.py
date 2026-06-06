# Copyright 2026 Manav Sehgal
# SPDX-License-Identifier: Apache-2.0
"""Tests for AE-17 (S7) — cloud-run eval guardrails.

Covers the three trip conditions of :class:`fieldkit.arena.guardrail.EvalGuardrail`
(G1 teardown · G2 stall · G3 cost), the cloud-lane detector, the env-config
defaults, the ``VerticalBench.run`` abort/progress hooks, and the
``run_vertical_eval`` end-to-end wiring (a fake OpenAI-compat client feeding
``usage`` → cost + an abort that yields a partial run). Pure unit work — no GPU,
no live lane, no db.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from fieldkit.arena.guardrail import (
    BOUNDS,
    DEFAULT_RUN_COST_CAP_USD,
    DEFAULT_STALL_TIMEOUT_S,
    DEFAULTS,
    EvalGuardrail,
    GuardrailConfig,
    GuardrailConfigError,
    eval_sentinel_dir,
    eval_sentinel_for,
    guardrail_config_path,
    is_cloud_endpoint,
    load_config,
    save_config,
)
from fieldkit.cost import PriceSnapshot


@pytest.fixture(autouse=True)
def _isolate_guardrail_config(monkeypatch, tmp_path):
    """Point the config resolver at an empty tmp dir (GS-1).

    Keeps every test isolated from any real ``~/.fieldkit/arena/guardrail-config.json``
    on the box — the file is absent by default (falls through to env/default), and a
    test that wants a file just calls :func:`save_config` (it lands here).
    """
    monkeypatch.setenv("FK_EVAL_CONFIG_DIR", str(tmp_path / "gcfg"))
    monkeypatch.delenv("FK_EVAL_CONFIG_PATH", raising=False)
    monkeypatch.delenv("FK_EVAL_GUARDRAIL_ENABLED", raising=False)

_PRICE = PriceSnapshot(
    snapshot_id="t",
    model_id="m",
    price_per_m_input_usd=15.0,
    price_per_m_output_usd=75.0,
    source="test",
    captured_at="2026-06-06",
)


# ---------------------------------------------------------------------------
# Cloud-lane detection (scopes the whole guardrail)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "url,cloud",
    [
        ("https://openrouter.ai/api/v1", True),
        ("https://api.anthropic.com", True),
        ("http://8.8.8.8:8080", True),  # public IP
        ("http://127.0.0.1:8080", False),
        ("http://localhost:8080", False),
        ("http://172.17.0.1:8000", False),  # docker bridge
        ("http://10.0.0.209:4321", False),  # RFC-1918 LAN
        ("http://192.168.1.5:8080", False),
        ("http://[::1]:8080", False),  # ipv6 loopback
        ("box.local", False),
        ("", False),
        (None, False),
    ],
)
def test_is_cloud_endpoint(url, cloud):
    assert is_cloud_endpoint(url) is cloud


def test_eval_sentinel_for_is_deterministic_and_under_dir():
    a = eval_sentinel_for("abc123")
    b = eval_sentinel_for("abc123")
    assert a == b
    assert a.name == "abort-abc123.json"
    assert a.parent == eval_sentinel_dir()


def test_eval_sentinel_dir_env_override(monkeypatch, tmp_path):
    monkeypatch.setenv("FK_EVAL_SENTINEL_DIR", str(tmp_path / "sx"))
    assert eval_sentinel_dir() == tmp_path / "sx"


# ---------------------------------------------------------------------------
# from_env — thresholds + bad-value fallback
# ---------------------------------------------------------------------------


def test_from_env_defaults(monkeypatch, tmp_path):
    monkeypatch.delenv("FK_EVAL_STALL_TIMEOUT_S", raising=False)
    monkeypatch.delenv("FK_EVAL_RUN_COST_CAP_USD", raising=False)
    g = EvalGuardrail.from_env(tmp_path / "s.json")
    assert g.stall_timeout_s == DEFAULT_STALL_TIMEOUT_S
    assert g.cost_cap_usd == DEFAULT_RUN_COST_CAP_USD


def test_from_env_reads_overrides(monkeypatch, tmp_path):
    monkeypatch.setenv("FK_EVAL_STALL_TIMEOUT_S", "30")
    monkeypatch.setenv("FK_EVAL_RUN_COST_CAP_USD", "1.5")
    g = EvalGuardrail.from_env(tmp_path / "s.json")
    assert g.stall_timeout_s == 30.0
    assert g.cost_cap_usd == 1.5


def test_from_env_bad_value_falls_back(monkeypatch, tmp_path):
    monkeypatch.setenv("FK_EVAL_STALL_TIMEOUT_S", "not-a-number")
    g = EvalGuardrail.from_env(tmp_path / "s.json")
    assert g.stall_timeout_s == DEFAULT_STALL_TIMEOUT_S


# ---------------------------------------------------------------------------
# GS-1 — config resolver (file > env > default + provenance) + save_config
# ---------------------------------------------------------------------------


def test_config_path_env_overrides(monkeypatch, tmp_path):
    # FK_EVAL_CONFIG_PATH (exact) wins over FK_EVAL_CONFIG_DIR.
    monkeypatch.setenv("FK_EVAL_CONFIG_PATH", str(tmp_path / "exact.json"))
    assert guardrail_config_path() == tmp_path / "exact.json"
    monkeypatch.delenv("FK_EVAL_CONFIG_PATH", raising=False)
    monkeypatch.setenv("FK_EVAL_CONFIG_DIR", str(tmp_path / "d"))
    assert guardrail_config_path() == tmp_path / "d" / "guardrail-config.json"


def test_load_config_all_defaults(monkeypatch):
    # Isolated tmp dir (autouse), no env, no file → every field is a default.
    monkeypatch.delenv("FK_EVAL_STALL_TIMEOUT_S", raising=False)
    monkeypatch.delenv("FK_EVAL_RUN_COST_CAP_USD", raising=False)
    cfg, sources = load_config()
    assert cfg.stall_timeout_s == DEFAULT_STALL_TIMEOUT_S
    assert cfg.cost_cap_usd == DEFAULT_RUN_COST_CAP_USD
    assert cfg.enabled is True
    assert sources == {
        "stall_timeout_s": "default",
        "cost_cap_usd": "default",
        "enabled": "default",
    }


def test_load_config_env_layer(monkeypatch):
    monkeypatch.setenv("FK_EVAL_STALL_TIMEOUT_S", "120")
    monkeypatch.setenv("FK_EVAL_RUN_COST_CAP_USD", "2.5")
    monkeypatch.setenv("FK_EVAL_GUARDRAIL_ENABLED", "0")
    cfg, sources = load_config()
    assert (cfg.stall_timeout_s, cfg.cost_cap_usd, cfg.enabled) == (120.0, 2.5, False)
    assert sources == {
        "stall_timeout_s": "env",
        "cost_cap_usd": "env",
        "enabled": "env",
    }


def test_load_config_file_wins_per_field(monkeypatch):
    # File sets only cost_cap; env sets stall. Each field resolves independently.
    monkeypatch.setenv("FK_EVAL_STALL_TIMEOUT_S", "45")
    save_config(GuardrailConfig(stall_timeout_s=300.0, cost_cap_usd=9.0, enabled=True))
    # Re-write the file with a partial dict so stall_timeout_s is absent.
    guardrail_config_path().write_text(json.dumps({"cost_cap_usd": 9.0}))
    cfg, sources = load_config()
    assert cfg.cost_cap_usd == 9.0 and sources["cost_cap_usd"] == "file"
    assert cfg.stall_timeout_s == 45.0 and sources["stall_timeout_s"] == "env"
    assert sources["enabled"] == "default"


def test_save_config_round_trips(monkeypatch):
    monkeypatch.delenv("FK_EVAL_STALL_TIMEOUT_S", raising=False)
    monkeypatch.delenv("FK_EVAL_RUN_COST_CAP_USD", raising=False)
    save_config(GuardrailConfig(stall_timeout_s=900.0, cost_cap_usd=12.0, enabled=False))
    cfg, sources = load_config()
    assert (cfg.stall_timeout_s, cfg.cost_cap_usd, cfg.enabled) == (900.0, 12.0, False)
    assert set(sources.values()) == {"file"}


def test_save_config_rejects_out_of_bounds():
    with pytest.raises(GuardrailConfigError):
        save_config(GuardrailConfig(cost_cap_usd=-1.0))
    with pytest.raises(GuardrailConfigError):
        save_config(GuardrailConfig(cost_cap_usd=2000.0))
    with pytest.raises(GuardrailConfigError):
        save_config(GuardrailConfig(stall_timeout_s=5.0))  # below 30, not 0


def test_save_config_allows_off_sentinels_and_tiny_cap():
    # 0 disables a guard; a tiny-but-positive cap is allowed-but-loud (GS-R1).
    save_config(GuardrailConfig(stall_timeout_s=0.0, cost_cap_usd=0.0, enabled=True))
    save_config(GuardrailConfig(stall_timeout_s=60.0, cost_cap_usd=0.001, enabled=True))
    cfg, _ = load_config()
    assert cfg.cost_cap_usd == 0.001


def test_load_config_corrupt_file_falls_back(monkeypatch):
    monkeypatch.setenv("FK_EVAL_RUN_COST_CAP_USD", "7.0")
    path = guardrail_config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{ this is not json")
    cfg, sources = load_config()  # must not raise
    assert cfg.cost_cap_usd == 7.0 and sources["cost_cap_usd"] == "env"
    assert cfg.enabled is True


def test_load_config_ignores_nonnumeric_file_value(monkeypatch):
    monkeypatch.setenv("FK_EVAL_RUN_COST_CAP_USD", "3.0")
    guardrail_config_path().parent.mkdir(parents=True, exist_ok=True)
    guardrail_config_path().write_text(json.dumps({"cost_cap_usd": "lots"}))
    cfg, sources = load_config()
    assert cfg.cost_cap_usd == 3.0 and sources["cost_cap_usd"] == "env"


def test_from_env_reads_config_file(monkeypatch, tmp_path):
    # from_env is now a thin wrapper over load_config → a file edit is picked up.
    save_config(GuardrailConfig(stall_timeout_s=42.0, cost_cap_usd=3.5, enabled=False))
    g = EvalGuardrail.from_env(tmp_path / "s.json")
    assert g.stall_timeout_s == 42.0 and g.cost_cap_usd == 3.5


def test_defaults_and_bounds_shape():
    assert DEFAULTS["enabled"] is True
    assert BOUNDS["stall_timeout_s"][0] == 30.0
    assert BOUNDS["cost_cap_usd"] == (0.0, 1000.0)


# ---------------------------------------------------------------------------
# G3 cost cap
# ---------------------------------------------------------------------------


def test_g3_cost_cap_trips_and_writes_sentinel(tmp_path):
    s = tmp_path / "s.json"
    g = EvalGuardrail(sentinel=s, stall_timeout_s=600, cost_cap_usd=0.01, price=_PRICE, clock=lambda: 0.0)
    # 1000 in × $15/M + 1000 out × $75/M = 0.015 + 0.075 = 0.09 > 0.01
    g.record_usage({"prompt_tokens": 1000, "completion_tokens": 1000})
    assert g.aborted_by == "cost_cap"
    assert g.run_cost_usd == pytest.approx(0.09)
    assert s.exists()
    body = json.loads(s.read_text())
    assert body["aborted_by"] == "cost_cap"
    assert g.should_abort() is True


def test_g3_accumulates_across_rows(tmp_path):
    g = EvalGuardrail(sentinel=tmp_path / "s.json", cost_cap_usd=5.0, price=_PRICE, clock=lambda: 0.0)
    g.record_usage({"prompt_tokens": 100, "completion_tokens": 100})
    first = g.run_cost_usd
    g.record_usage({"prompt_tokens": 100, "completion_tokens": 100})
    assert g.run_cost_usd == pytest.approx(2 * first)
    assert g.aborted_by is None
    assert g.tokens_in == 200 and g.tokens_out == 200


def test_g3_inert_without_price(tmp_path):
    # No price snapshot ⇒ tokens still tracked, but no $ cap can trip (G1/G2 live).
    g = EvalGuardrail(sentinel=tmp_path / "s.json", cost_cap_usd=0.0001, price=None, clock=lambda: 0.0)
    g.record_usage({"prompt_tokens": 10_000, "completion_tokens": 10_000})
    assert g.aborted_by is None
    assert g.run_cost_usd == 0.0
    assert g.tokens_in == 10_000
    assert g.result_fields()["priced"] is False


def test_g3_ignores_empty_usage(tmp_path):
    g = EvalGuardrail(sentinel=tmp_path / "s.json", price=_PRICE, clock=lambda: 0.0)
    g.record_usage(None)
    g.record_usage({})
    assert g.tokens_in == 0 and g.run_cost_usd == 0.0


# ---------------------------------------------------------------------------
# G2 stall — no-progress window, reset on each row (AE-R6)
# ---------------------------------------------------------------------------


def test_g2_stall_trips_after_window(tmp_path):
    now = [0.0]
    g = EvalGuardrail(sentinel=tmp_path / "s.json", stall_timeout_s=10, clock=lambda: now[0])
    assert g.should_abort() is False
    now[0] = 11.0
    assert g.should_abort() is True
    assert g.aborted_by == "stall_timeout"


def test_g2_progress_resets_window(tmp_path):
    now = [0.0]
    g = EvalGuardrail(sentinel=tmp_path / "s.json", stall_timeout_s=10, clock=lambda: now[0])
    now[0] = 8.0
    g.record_progress()  # reset at t=8
    now[0] = 17.0  # 17-8 = 9 < 10 → still alive
    assert g.should_abort() is False
    assert g.n_scored == 1
    now[0] = 19.0  # 19-8 = 11 > 10 → trips
    assert g.should_abort() is True
    assert g.aborted_by == "stall_timeout"


def test_g2_disabled_when_timeout_zero(tmp_path):
    now = [0.0]
    g = EvalGuardrail(sentinel=tmp_path / "s.json", stall_timeout_s=0, clock=lambda: now[0])
    now[0] = 10_000.0
    assert g.should_abort() is False


# ---------------------------------------------------------------------------
# G1 teardown — external sentinel
# ---------------------------------------------------------------------------


def test_g1_teardown_external_sentinel(tmp_path):
    s = tmp_path / "s.json"
    g = EvalGuardrail(sentinel=s, stall_timeout_s=600, clock=lambda: 0.0)
    assert g.should_abort() is False
    s.write_text("{}")  # an external trip (the _lifespan shutdown)
    assert g.should_abort() is True
    assert g.aborted_by == "teardown"


def test_in_process_trip_wins_attribution_over_sentinel(tmp_path):
    # A cost trip writes the sentinel; a later poll must still read "cost_cap",
    # never re-attribute to "teardown" because the file now exists.
    g = EvalGuardrail(sentinel=tmp_path / "s.json", cost_cap_usd=0.01, price=_PRICE, clock=lambda: 0.0)
    g.record_usage({"prompt_tokens": 1000, "completion_tokens": 1000})
    assert g.should_abort() is True
    assert g.aborted_by == "cost_cap"


def test_result_fields_shape(tmp_path):
    g = EvalGuardrail(sentinel=tmp_path / "s.json", stall_timeout_s=30, cost_cap_usd=2.0, price=_PRICE, clock=lambda: 0.0)
    g.record_usage({"prompt_tokens": 10, "completion_tokens": 20})
    g.record_progress()
    f = g.result_fields()
    assert f == {
        "aborted_by": None,
        "partial": False,
        "run_cost_usd": g.run_cost_usd,
        "tokens_in": 10,
        "tokens_out": 20,
        "n_scored": 1,
        "stall_timeout_s": 30,
        "cost_cap_usd": 2.0,
        "priced": True,
    }


# ---------------------------------------------------------------------------
# VerticalBench.run — the abort/progress hooks (eval-side abort_poller)
# ---------------------------------------------------------------------------


def _bench(tmp_path, n=4):
    from fieldkit.eval import VerticalBench, exact_match

    p = tmp_path / "b.jsonl"
    p.write_text("\n".join(json.dumps({"qid": f"q{i}", "question": f"q{i}?", "answer": "ok"}) for i in range(n)))
    return VerticalBench.from_jsonl(p, name="b", scorer=exact_match)


def test_run_should_abort_stops_early_partial(tmp_path):
    vb = _bench(tmp_path, n=6)
    seen = {"n": 0}

    def model_fn(_):
        seen["n"] += 1
        return "ok"

    # Abort once two rows have been processed.
    bench = vb.run(model_fn, should_abort=lambda: seen["n"] >= 2)
    # The loop polls BEFORE each row: rows 0,1 run, then poll sees n>=2 → break.
    assert seen["n"] == 2
    assert len(bench.calls) == 2


def test_run_on_row_fires_per_row_including_errors(tmp_path):
    vb = _bench(tmp_path, n=3)
    rows = {"n": 0}

    def model_fn(q):
        if q == "q1?":
            raise RuntimeError("boom")
        return "ok"

    vb.run(model_fn, on_row=lambda: rows.__setitem__("n", rows["n"] + 1))
    assert rows["n"] == 3  # 2 success + 1 recorded error all count as progress


def test_run_no_hooks_unchanged(tmp_path):
    vb = _bench(tmp_path, n=3)
    bench = vb.run(lambda _: "ok")
    assert len(bench.calls) == 3


# ---------------------------------------------------------------------------
# run_vertical_eval — end-to-end wiring with a fake OpenAI-compat client
# ---------------------------------------------------------------------------


class _FakeClient:
    """Stand-in for OpenAICompatClient: echoes the gold + feeds usage to on_usage."""

    def __init__(self, *a, usage_per_call=None, **k):
        self.usage = usage_per_call or {"prompt_tokens": 100, "completion_tokens": 100}
        self.calls = 0

    def chat(self, messages, *, max_tokens=512, on_usage=None, **kw):
        self.calls += 1
        if on_usage is not None:
            on_usage(dict(self.usage))
        return "ok"


def _patch_client(monkeypatch, usage=None):
    import fieldkit.notebook as nb

    def _factory(*a, **k):
        return _FakeClient(*a, usage_per_call=usage, **k)

    monkeypatch.setattr(nb, "OpenAICompatClient", _factory)


def test_run_vertical_eval_accrues_cost_through_guardrail(tmp_path, monkeypatch):
    from fieldkit.harness import mcp

    _patch_client(monkeypatch, usage={"prompt_tokens": 100, "completion_tokens": 100})
    p = tmp_path / "b.jsonl"
    p.write_text("\n".join(json.dumps({"qid": f"q{i}", "question": f"q{i}?", "answer": "ok"}) for i in range(3)))
    g = EvalGuardrail(sentinel=tmp_path / "s.json", cost_cap_usd=5.0, price=_PRICE, clock=lambda: 0.0)
    out = mcp.run_vertical_eval(
        lane="cloud", bench="b", bench_path=str(p),
        base_url="https://openrouter.ai/api/v1", model="m", scorer="exact_match",
        guardrail=g,
    )
    assert out["n"] == 3
    assert "guardrail" in out
    # 3 rows × (100 in × $15/M + 100 out × $75/M = 0.009) = 0.027
    assert out["guardrail"]["run_cost_usd"] == pytest.approx(0.027)
    assert out["guardrail"]["aborted_by"] is None
    assert out["guardrail"]["n_scored"] == 3


def test_run_vertical_eval_cost_cap_yields_partial(tmp_path, monkeypatch):
    from fieldkit.harness import mcp

    _patch_client(monkeypatch, usage={"prompt_tokens": 10_000, "completion_tokens": 10_000})
    p = tmp_path / "b.jsonl"
    p.write_text("\n".join(json.dumps({"qid": f"q{i}", "question": f"q{i}?", "answer": "ok"}) for i in range(10)))
    # cap $0.10; one row = 10k in ×$15/M + 10k out ×$75/M = 0.15 + 0.75 = 0.90 → first row trips it.
    g = EvalGuardrail(sentinel=tmp_path / "s.json", cost_cap_usd=0.10, price=_PRICE, clock=lambda: 0.0)
    out = mcp.run_vertical_eval(
        lane="cloud", bench="b", bench_path=str(p),
        base_url="https://openrouter.ai/api/v1", model="m", scorer="exact_match",
        guardrail=g,
    )
    assert out["guardrail"]["aborted_by"] == "cost_cap"
    assert out["guardrail"]["partial"] is True
    # The first row scored before the cap-cross; the loop then breaks before row 2.
    assert out["n"] == 1
    assert out["guardrail"]["n_scored"] == 1


def test_run_vertical_eval_no_guardrail_unchanged(tmp_path, monkeypatch):
    from fieldkit.harness import mcp

    _patch_client(monkeypatch)
    p = tmp_path / "b.jsonl"
    p.write_text(json.dumps({"qid": "q0", "question": "q?", "answer": "ok"}) + "\n")
    out = mcp.run_vertical_eval(
        lane="local", bench="b", bench_path=str(p),
        base_url="http://127.0.0.1:8080", model="resident", scorer="exact_match",
    )
    assert "guardrail" not in out
    assert out["n"] == 1
