# Copyright 2026 Manav Sehgal
# SPDX-License-Identifier: Apache-2.0
"""Tests for `fieldkit.arena.lane` — the RL-lane autonomy arbiter (LA-1..11).

GPU-free by construction: every lane is a fake (its ``stop`` records a call), the
envelope/governor are the real deterministic ones, and the loop runs with fake
seams. These pin the spec §8 deliverables — spawn-gate, restore-on-failure,
refuse-on-unmanaged, watchdog floor-breach-after-N + transient-no-fire, mem-trace
round-trip, live-progress surfaces, the defer brake, and the autonomy policy.
"""

from __future__ import annotations

import json

import pytest

from fieldkit.arena import jobs as J
from fieldkit.arena import lane as L
from fieldkit.arena.scheduler import (
    build_standup,
    clear_autonomy_state,
    read_autonomy_state,
    write_autonomy_state,
)
from fieldkit.arena.store import ArenaStore
from fieldkit.budget import EscalationReason, MemoryEnvelope
from fieldkit.reward import RewardAdapter, Rollout
from fieldkit.rl import GRPOConfig, RLLoop, rl_hooks


# --------------------------------------------------------------------------- #
# Fakes                                                                        #
# --------------------------------------------------------------------------- #


class FakeLane:
    def __init__(self) -> None:
        self.stopped = 0

    def stop(self) -> None:
        self.stopped += 1


def _cfg():
    class Cfg:
        serve_cmd_override = ""
        stop_cmd = "true"

    return Cfg()


def _job(lane_id="rl-lane"):
    return {"payload_json": json.dumps({"lane_id": lane_id, "base": "Q"})}


def _rl_runner(payload):
    """A runner that runs a real RLLoop with fake seams (ambient hooks drive it)."""

    def scorer(pred, expected, **k):
        return 1.0 if pred == expected else 0.0

    reward = RewardAdapter(scorer, pass_threshold=1.0)
    qs = [{"question": f"q{i}", "expected": "A", "rubric": None} for i in range(110)]

    class Bench:
        questions = qs

    def sampler(tasks, k):
        return [
            [Rollout(prediction="A", expected="A", rubric=None, task_id=str(i)) for _ in range(k)]
            for i, _ in enumerate(tasks)
        ]

    def trainer(rolls, adv, step):
        return {"loss": 0.1, "kl": 0.0, "train_s": 0.0, "total_s": 0.0, "checkpoint": "/tmp/c"}

    def heldout(step, tasks):
        return 0.5 + 0.01 * step

    cfg = GRPOConfig(base=payload["base"], max_steps=4, heldout_every=2, corpus_min=100)
    loop = RLLoop(
        cfg, reward, Bench(),
        sampler=sampler, trainer=trainer, heldout_eval=heldout,
        domain=payload.get("vertical", "test"),
    )
    snap = loop.run()
    out = loop.summary()
    out["lineage_card"] = snap.rendered_prompt
    out["base"] = payload["base"]
    return out


# --------------------------------------------------------------------------- #
# LaneArbiter — the 3-way pre-flight + spawn/teardown/restore (LA-1/2/6)        #
# --------------------------------------------------------------------------- #


def test_arbiter_spawns_tears_down_and_restores_in_order():
    events: list[str] = []
    fake = FakeLane()
    arb = L.LaneArbiter(
        envelope=MemoryEnvelope(),
        cfg=_cfg(),
        job=_job(),
        bin_check=lambda c: True,
        lane_factory=lambda c: fake,
        stop_resident=lambda: events.append("brain.stop"),
        restore_resident=lambda: events.append("brain.restore"),
    )
    with arb:
        events.append("inside")
    assert events == ["brain.stop", "inside", "brain.restore"]
    assert fake.stopped == 1  # the lane is always torn down on exit (LA-1)


def test_arbiter_refuses_when_lane_binary_absent():
    arb = L.LaneArbiter(
        envelope=MemoryEnvelope(), cfg=_cfg(), job=_job(), bin_check=lambda c: False
    )
    with pytest.raises(L.LaneDeferred) as exc, arb:
        pass
    assert exc.value.decision.reason == EscalationReason.LANE_BIN_ABSENT


def test_arbiter_defers_when_lane_does_not_fit_envelope():
    tight = MemoryEnvelope(total_gb=32.0, reserved_gb=31.8, default_lane_gb=5.5)
    arb = L.LaneArbiter(
        envelope=tight, cfg=_cfg(), job=_job("big"), bin_check=lambda c: True
    )
    with pytest.raises(L.LaneDeferred) as exc, arb:
        pass
    assert exc.value.decision.reason == EscalationReason.OOM_ENVELOPE


def test_arbiter_restores_resident_even_if_body_raises():
    """restore-on-failure (R1): the box never ends with no serving lane."""
    events: list[str] = []
    arb = L.LaneArbiter(
        envelope=MemoryEnvelope(), cfg=_cfg(), job=_job(),
        bin_check=lambda c: True, lane_factory=lambda c: FakeLane(),
        stop_resident=lambda: events.append("stop"),
        restore_resident=lambda: events.append("restore"),
    )
    with pytest.raises(RuntimeError), arb:
        raise RuntimeError("loop blew up")
    assert events == ["stop", "restore"]


def test_governor_veto_is_the_first_preflight_gate():
    class Veto:
        def check_budget(self, job):
            from fieldkit.budget import DEFER, BudgetDecision

            return BudgetDecision(DEFER, EscalationReason.OVER_DAILY_CAP, {})

    arb = L.LaneArbiter(
        envelope=MemoryEnvelope(), cfg=_cfg(), job=_job(),
        governor=Veto(), bin_check=lambda c: True,
    )
    with pytest.raises(L.LaneDeferred) as exc, arb:
        pass
    assert exc.value.decision.reason == EscalationReason.OVER_DAILY_CAP


# --------------------------------------------------------------------------- #
# MemoryWatchdog — telemetry-correlated OOM defense (LA-10)                     #
# --------------------------------------------------------------------------- #


def test_watchdog_trips_after_persistent_floor_breach(tmp_path):
    sentinel = tmp_path / "abort.json"
    trace = L.MemTrace(total_gb=128.0)
    seq = iter([80, 80, 3, 3, 3, 3, 80])
    wd = L.MemoryWatchdog(
        sentinel=sentinel, floor_gb=4, warn_gb=8, persist_n=4, trace=trace,
        mem_sampler=lambda: next(seq, 80),
    )
    states = [wd.poll() for _ in range(7)]
    assert "tripped" in states
    assert sentinel.exists()
    assert trace.oom_deferred is True
    assert trace.abort_headroom_gb == 3


def test_watchdog_ignores_a_transient_spike(tmp_path):
    sentinel = tmp_path / "abort.json"
    seq = iter([80, 3, 80, 80])  # one low sample, then recovery
    wd = L.MemoryWatchdog(sentinel=sentinel, floor_gb=4, persist_n=4, mem_sampler=lambda: next(seq, 80))
    [wd.poll() for _ in range(4)]
    assert wd.tripped is False
    assert not sentinel.exists()


def test_watchdog_never_trips_on_a_stale_sample(tmp_path):
    """R7 — a missing /proc/meminfo read never aborts a running job."""
    wd = L.MemoryWatchdog(
        sentinel=tmp_path / "abort.json", floor_gb=4, persist_n=2, mem_sampler=lambda: None
    )
    assert [wd.poll() for _ in range(3)] == ["stale", "stale", "stale"]
    assert wd.tripped is False


def test_warn_tier_is_non_destructive(tmp_path):
    warned: list[float] = []
    seq = iter([6, 6, 6])  # below warn(8), above floor(4)
    wd = L.MemoryWatchdog(
        sentinel=tmp_path / "abort.json", floor_gb=4, warn_gb=8,
        mem_sampler=lambda: next(seq, 80), on_warn=warned.append,
    )
    assert [wd.poll() for _ in range(3)] == ["warn", "warn", "warn"]
    assert wd.tripped is False and warned == [6, 6, 6]


# --------------------------------------------------------------------------- #
# mem_trace — the per-run memory report (LA-11)                                 #
# --------------------------------------------------------------------------- #


def test_mem_trace_records_peak_and_per_phase_and_round_trips():
    mt = L.mem_trace(total_gb=128.0)
    mt.observe(used_gb=50.0, phase="sampling")
    mt.observe(used_gb=119.0, phase="training")
    mt.observe(used_gb=40.0, phase="teardown")
    d = mt.as_dict()
    assert d["peak_used_gb"] == 119.0
    assert d["phase_used_gb"]["training"] == 119.0
    assert "peak 119 GB" in d["display"]


# --------------------------------------------------------------------------- #
# Live progress (LA-8) — throttle + single-writer into result_json             #
# --------------------------------------------------------------------------- #


def test_progress_writer_throttles_then_writes_on_phase_change():
    writes: list[dict] = []

    class Store:
        def update_job(self, job_id, **fields):
            writes.append(json.loads(fields["result_json"]))

    clk = iter([0.0, 1.0, 2.0, 100.0])
    write = L.rl_progress_writer(
        Store(), "j1", min_interval=30.0,
        used_sampler=lambda: 50.0, clock=lambda: next(clk),
    )
    write({"phase": "sampling", "step": 0})  # first → writes
    write({"phase": "sampling", "step": 0})  # same phase, <30s → throttled
    write({"phase": "training", "step": 0})  # phase change → writes
    write({"phase": "training", "step": 1})  # same phase, >30s elapsed → writes
    phases = [w["phase"] for w in writes]
    assert phases == ["sampling", "training", "training"]
    assert all(w["status"] == "running" for w in writes)


def test_progress_gate_always_writes_through_throttle():
    writes: list[dict] = []

    class Store:
        def update_job(self, job_id, **fields):
            writes.append(json.loads(fields["result_json"]))

    write = L.rl_progress_writer(Store(), "j", min_interval=1e9, used_sampler=lambda: 1.0, clock=lambda: 0.0)
    write({"phase": "heldout-gate", "step": 2, "gate": False})  # phase change → write
    write({"phase": "heldout-gate", "step": 2, "gate": True})  # gate → write despite throttle
    assert len(writes) == 2


# --------------------------------------------------------------------------- #
# lane_binary_present (LA-3)                                                    #
# --------------------------------------------------------------------------- #


def test_lane_binary_present_reads_env(monkeypatch, tmp_path):
    monkeypatch.delenv("FK_RL_VLLM_BIN", raising=False)

    class Cfg:
        serve_cmd_override = ""

    # Nothing set + no `vllm` on PATH (CI) → absent.
    monkeypatch.setattr(L.shutil, "which", lambda name: None)
    assert L.lane_binary_present(Cfg()) is False
    # A real FK_RL_VLLM_BIN path → present.
    binp = tmp_path / "vllm"
    binp.write_text("#!/bin/sh\n")
    monkeypatch.setenv("FK_RL_VLLM_BIN", str(binp))
    assert L.lane_binary_present(Cfg()) is True


# --------------------------------------------------------------------------- #
# RLLoop abort hook (LA-10) + ambient rl_hooks                                  #
# --------------------------------------------------------------------------- #


def test_loop_aborts_when_sentinel_present_between_steps(tmp_path):
    sentinel = tmp_path / "abort.json"
    sentinel.write_text("{}")
    out = _rl_runner_with_hooks({"base": "Q"}, should_abort=L.abort_poller(sentinel))
    assert out["aborted"] is True
    assert out["n_steps"] == 0  # aborted before the first step


def _rl_runner_with_hooks(payload, *, should_abort=None, progress_cb=None):
    with rl_hooks(progress_cb, should_abort):
        return _rl_runner(payload)


# --------------------------------------------------------------------------- #
# Full dispatch integration — arbiter + progress + mem-trace + defer brake      #
# --------------------------------------------------------------------------- #


def test_drain_arbiters_rl_run_with_progress_and_mem_trace(monkeypatch, tmp_path):
    # Isolate the autonomy state file — build_standup reads it, and the box's
    # real ~/.fieldkit/arena/autonomy.json may be armed (enabled), which would
    # otherwise fail the unarmed-policy assertion below (LA-5/11).
    monkeypatch.setenv("ARENA_AUTONOMY_STATE", str(tmp_path / "autonomy.json"))
    store = ArenaStore(tmp_path / "arena.db")
    store.initialize()
    fake = FakeLane()
    rl_lane = L.RLLaneContext(
        bin_check=lambda c: True,
        lane_factory=lambda c: fake,
        throttle_s=0.0,
        sentinel_dir=str(tmp_path / "rl"),
    )
    jid = J.enqueue_job(
        store, "rl_run", {"base": "Qwen/X", "vertical": "patent", "bench_path": "/x", "lane_id": "rl-lane"}
    )
    J.drain_jobs(store, runner=lambda kind, p: _rl_runner(p), rl_lane=rl_lane)
    row = store.get_job(jid)
    assert row["status"] == "done"
    res = json.loads(row["result_json"])
    assert res["kind"] == "rl_run" and res["selected_on"] == "heldout"
    assert res["mem_trace"] is not None
    assert fake.stopped == 1  # the lane was torn down (LA-1)
    # The standup surfaces the run + an unarmed autonomy policy (LA-5/11).
    su = build_standup(store)
    assert su["rl"]["n_rl_run"] == 1
    assert su["autonomy"]["enabled"] is False


def test_drain_defers_rl_run_when_binary_absent_without_looping(tmp_path):
    """The defer brake (LA-6): release + audit + stop the pass, never spin."""
    store = ArenaStore(tmp_path / "arena.db")
    store.initialize()
    rl_lane = L.RLLaneContext(bin_check=lambda c: False, sentinel_dir=str(tmp_path / "rl"))
    jid = J.enqueue_job(store, "rl_run", {"base": "Q", "bench_path": "/x", "lane_id": "rl"})
    done = J.drain_jobs(store, runner=lambda kind, p: _rl_runner(p), rl_lane=rl_lane)
    assert done == []  # nothing dispatched
    row = store.get_job(jid)
    assert row["status"] == "queued"  # released, not failed
    triggers = list(
        store.connect().execute(
            "SELECT source, detail_json FROM job_triggers WHERE job_id=?", [jid]
        )
    )
    assert triggers and triggers[0][0] == "budget_defer"
    assert json.loads(triggers[0][1])["reason"] == EscalationReason.LANE_BIN_ABSENT


def test_rl_run_without_rl_lane_runs_bare(tmp_path):
    """No RLLaneContext = byte-for-byte M8/RV-6 behavior (no arbiter, no mem_trace key set)."""
    store = ArenaStore(tmp_path / "arena.db")
    store.initialize()
    jid = J.enqueue_job(store, "rl_run", {"base": "Q", "bench_path": "/x"})
    J.drain_jobs(store, runner=lambda kind, p: _rl_runner(p))  # rl_lane=None
    row = store.get_job(jid)
    assert row["status"] == "done"
    res = json.loads(row["result_json"])
    assert res["mem_trace"] is None and res["aborted"] is False


# --------------------------------------------------------------------------- #
# No schema change (LA-7)                                                       #
# --------------------------------------------------------------------------- #


def test_no_schema_change_user_version_stays_6(tmp_path):
    store = ArenaStore(tmp_path / "arena.db")
    store.initialize()
    assert store.connect().execute("PRAGMA user_version").fetchone()[0] == 6


# --------------------------------------------------------------------------- #
# Autonomy policy (LA-5)                                                        #
# --------------------------------------------------------------------------- #


def test_autonomy_state_round_trip(tmp_path):
    p = str(tmp_path / "autonomy.json")
    assert read_autonomy_state(p) == {"enabled": False}
    write_autonomy_state({"enabled": True, "interval_min": 20, "cap_usd": 4.0}, p)
    st = read_autonomy_state(p)
    assert st["enabled"] is True and st["interval_min"] == 20
    assert clear_autonomy_state(p) is True
    assert read_autonomy_state(p) == {"enabled": False}
