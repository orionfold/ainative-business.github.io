# Copyright 2026 Manav Sehgal
# SPDX-License-Identifier: Apache-2.0
"""`fieldkit.rl` — the closed-loop RLVR driver (Phase 3, the engine).

Covers the orchestration with **injected GPU seams** (no torch / no vLLM), the
way the production loop will run with real ones:
- **RV-10** the ≥100-row corpus floor + the frozen held-out split before step 0;
- **RV-4** the held-out gate + **held-out-ONLY checkpoint selection** — the test
  makes the pool rise monotonically while held-out peaks early, and asserts the
  loop selects the held-out-best step, *not* the pool-best/last (the 81.8 pp
  `t2po` inversion defense);
- the `RLLoop` writes a `Trial` per step into `fieldkit.lineage` and returns the
  `rl_run` `LineageSnapshot` (RV-7);
- `GRPOConfig` validation + the `gpu_seams` not-yet-vendored guard (RV-1/RV-5).
"""

from __future__ import annotations

import pytest

from fieldkit.eval import VerticalQA, mcq_letter
from fieldkit.lineage import FailureLabel, LineageSnapshot, LineageStore
from fieldkit.reward import RewardAdapter, Rollout
from fieldkit.rl import GRPOConfig, RLLoop, RLLoopError, gpu_seams


class _Bench:
    """A bench-shaped stub — `RLLoop` only reads `.questions`."""

    def __init__(self, n=120):
        self.questions = [
            VerticalQA(qid=f"q{i}", question=f"Q{i}?", expected="B") for i in range(n)
        ]


def _seams(heldout_curve, pool_climbs=True):
    """Build (sampler, trainer, heldout_eval) fakes.

    `heldout_curve` maps step → held-out score. `sampler` emits more correct
    rollouts as steps progress (pool reward rises), so the test can prove
    selection ignores the pool.
    """
    state = {"step": 0}

    def sampler(tasks, k):
        s = state["step"]
        state["step"] += 1
        n_correct = min(k, s + 1) if pool_climbs else 1
        out = []
        for t in tasks:
            preds = ["B"] * n_correct + ["A"] * (k - n_correct)
            out.append([Rollout(prediction=p, expected="B", task_id=t.qid) for p in preds])
        return out

    def trainer(rollouts, advantages, step):
        assert len(rollouts) == len(advantages)
        return {"loss": 0.5 / (step + 1), "kl": 0.01, "train_s": 22.0, "checkpoint": f"/ckpt/{step}"}

    def heldout_eval(step, tasks):
        return heldout_curve[step]

    return sampler, trainer, heldout_eval


# ---------------------------------------------------------------------------
# RV-4 — held-out-only checkpoint selection
# ---------------------------------------------------------------------------


def test_selects_heldout_best_not_pool_best():
    cfg = GRPOConfig(
        base="patent-Q4", max_steps=4, heldout_every=1, corpus_min=100,
        group_k=4, tasks_per_step=8, vllm_pin="vllm==0.10.2", seed=7,
    )
    # Pool climbs 0.25→1.0; held-out PEAKS at step 1 then collapses (inversion).
    sampler, trainer, heldout_eval = _seams({0: 0.30, 1: 0.90, 2: 0.50, 3: 0.40})
    loop = RLLoop(
        cfg, RewardAdapter(mcq_letter), _Bench(),
        sampler=sampler, trainer=trainer, heldout_eval=heldout_eval,
    )
    snap = loop.run()

    assert isinstance(snap, LineageSnapshot)
    # Pool is monotincreasing; held-out peaks at 1. Selection MUST pick 1.
    assert loop.pool_scores[3] > loop.pool_scores[0]
    assert loop.selected_step == 1
    assert loop.selected_heldout_score == pytest.approx(0.90)
    assert loop.summary()["selected_on"] == "heldout"


# ---------------------------------------------------------------------------
# arena-enhancements S1 — AE-2/AE-3/AE-4 RL-run observability
# ---------------------------------------------------------------------------


def _obs_loop():
    """A 4-step loop whose step 3 is all-correct (uniform reward → degenerate)."""
    cfg = GRPOConfig(
        base="patent-Q4", max_steps=4, heldout_every=1, corpus_min=100,
        group_k=4, tasks_per_step=8, vllm_pin="vllm==0.10.2", seed=7,
    )
    sampler, trainer, heldout_eval = _seams({0: 0.30, 1: 0.90, 2: 0.50, 3: 0.40})
    return RLLoop(
        cfg, RewardAdapter(mcq_letter), _Bench(),
        sampler=sampler, trainer=trainer, heldout_eval=heldout_eval,
    )


def test_step_history_captures_per_step_and_degenerate_no_op():
    """AE-2/AE-3 — summary().step_history records the per-step trajectory, and a
    uniform-reward step reads as a no-op (n_used==0, trained False, spread 0)."""
    loop = _obs_loop()
    loop.run()
    hist = loop.summary()["step_history"]

    assert len(hist) == 4
    assert set(hist[0]) >= {
        "step", "phase", "pool_score", "last_heldout", "keep_rate",
        "loss", "kl", "n_used", "adv_spread", "step_duration", "trained",
    }
    # heldout_every=1 → every step ran a gate, so each record carries a held-out.
    assert all(h["last_heldout"] is not None for h in hist)
    assert all(h["phase"] == "heldout-gate" for h in hist)
    # Step 0 is mixed (1/4 correct) → it moved the policy; step 3 is all-correct
    # (uniform reward → zero advantage) → a no-op the board must read as distinct.
    assert hist[0]["trained"] is True and hist[0]["n_used"] > 0
    assert hist[3]["trained"] is False and hist[3]["n_used"] == 0
    assert hist[3]["adv_spread"] == 0.0


def test_summary_threads_selected_step_to_lineage_trial():
    """AE-4 — the held-out-selected step back-points to its `rl-<step>` trial."""
    loop = _obs_loop()
    loop.run()
    summary = loop.summary()
    assert loop.selected_step == 1
    assert summary["selected_exp_id"] == "rl-001"


def test_lineage_trials_written_with_explicit_store(tmp_path):
    store = LineageStore(tmp_path / "lin", lower_is_better=False)
    cfg = GRPOConfig(base="x", max_steps=3, heldout_every=1, corpus_min=100)
    sampler, trainer, heldout_eval = _seams({0: 0.5, 1: 0.6, 2: 0.55})
    loop = RLLoop(
        cfg, RewardAdapter(mcq_letter), _Bench(),
        sampler=sampler, trainer=trainer, heldout_eval=heldout_eval,
        lineage_store=store,
    )
    loop.run()
    trials = store.all_trials()
    statuses = [t.status for t in trials]
    assert FailureLabel.BASELINE in statuses  # the seed row (RV-7)
    # one heldout-gate trial per held-out eval (every step here)
    assert sum(1 for t in trials if t.specialist == "heldout-gate") == 3
    assert any(t.specialist == "baseline" for t in trials)


# ---------------------------------------------------------------------------
# RV-10 — corpus floor + frozen split
# ---------------------------------------------------------------------------


def test_corpus_below_floor_refused():
    cfg = GRPOConfig(base="x", corpus_min=100)
    sampler, trainer, heldout_eval = _seams({0: 0.5})
    with pytest.raises(RLLoopError, match="corpus_min"):
        RLLoop(
            cfg, RewardAdapter(mcq_letter), _Bench(n=42),
            sampler=sampler, trainer=trainer, heldout_eval=heldout_eval,
        ).run()


def test_heldout_patience_stops_early():
    cfg = GRPOConfig(
        base="x", max_steps=10, heldout_every=1, corpus_min=100, heldout_patience=2,
    )
    # held-out improves once then plateaus → patience trips, run stops early.
    curve = {0: 0.5, 1: 0.5, 2: 0.5, 3: 0.5, 4: 0.5}
    sampler, trainer, heldout_eval = _seams(curve)
    loop = RLLoop(
        cfg, RewardAdapter(mcq_letter), _Bench(),
        sampler=sampler, trainer=trainer, heldout_eval=heldout_eval,
    )
    loop.run()
    assert len(loop.pool_scores) < 10  # stopped before max_steps


# ---------------------------------------------------------------------------
# GRPOConfig validation + gpu_seams guard
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "kw",
    [
        {"heldout_every": 0},
        {"group_k": 0},
        {"tasks_per_step": 0},
        {"max_steps": 0},
        {"heldout_frac": 1.5},
        {"heldout_patience": 0},
    ],
)
def test_invalid_config_rejected(kw):
    with pytest.raises(RLLoopError):
        GRPOConfig(base="x", **kw)


def test_missing_seam_raises():
    cfg = GRPOConfig(base="x", corpus_min=100)
    loop = RLLoop(cfg, RewardAdapter(mcq_letter), _Bench())  # no seams injected
    with pytest.raises(RLLoopError, match="sampler"):
        loop.run()


def test_gpu_seams_requires_rl_extra():
    # The backend is vendored, but a live run needs the fieldkit[rl] extra
    # (torch+peft+transformers) installed. Absent it, gpu_seams raises a
    # friendly RLLoopError pointing at the extra — never a bare ImportError.
    with pytest.raises(RLLoopError, match="fieldkit\\[rl\\]"):
        gpu_seams(GRPOConfig(base="x"))


def test_import_fieldkit_rl_stays_torch_free():
    # The load-bearing invariant: `import fieldkit.rl` (and the torch-free serve
    # half) must NOT drag in torch — only a live gpu_seams() trainer call does.
    import sys

    import fieldkit._rl_gpu_serve as _serve  # torch-free half
    import fieldkit.rl as _rl

    assert _serve and _rl  # touch the names — the point is the import side-effect
    assert "torch" not in sys.modules


# ---------------------------------------------------------------------------
# Vendored GPU backend — the torch-FREE serve/sampler half (fieldkit[rl])
# ---------------------------------------------------------------------------


class _FakeClient:
    """A NIMClient-shaped fake: records calls, returns a fixed completion."""

    def __init__(self, answer="B"):
        self.answer = answer
        self.calls = []

    def chat(self, messages, *, max_tokens, temperature):
        self.calls.append((messages, max_tokens, temperature))
        return {"choices": [{"message": {"content": self.answer}}]}

    def close(self):
        pass


def test_gpu_sampler_builds_rollouts_and_single_turn_messages():
    from fieldkit._rl_gpu_serve import RLBackendConfig, _GpuRollout, _make_sampler

    cfg = RLBackendConfig(system_prompt="SYS")
    client = _FakeClient("B")
    sampler = _make_sampler(cfg, 0.8, lambda: client)
    tasks = [VerticalQA(qid="q1", question="Q1?", expected="B")]

    groups = sampler(tasks, 3)
    assert len(groups) == 1 and len(groups[0]) == 3
    r = groups[0][0]
    assert isinstance(r, _GpuRollout)
    assert (r.prediction, r.expected, r.task_id, r.prompt) == ("B", "B", "q1", "Q1?")

    msgs, _max_tokens, temp = client.calls[0]
    assert msgs[0] == {"role": "system", "content": "SYS"}
    assert msgs[1] == {"role": "user", "content": "Q1?"}
    assert temp == 0.8

    # _GpuRollout duck-types straight into the reward adapter (RV-2/RV-3).
    assert RewardAdapter(mcq_letter).score(r).success is True


def test_gpu_heldout_eval_scores_via_reward_and_requires_it():
    from fieldkit._rl_gpu_serve import RLBackendConfig, _make_heldout_eval, _make_sampler

    sampler = _make_sampler(RLBackendConfig(), 0.2, lambda: _FakeClient("B"))
    tasks = [VerticalQA(qid=f"q{i}", question=f"Q{i}?", expected="B") for i in range(4)]

    he = _make_heldout_eval(sampler, RewardAdapter(mcq_letter))
    assert he(0, tasks) == pytest.approx(1.0)  # all "B" → all pass

    # The gate is the verifier's score on the frozen split — it needs the reward.
    he_noreward = _make_heldout_eval(sampler, None)
    with pytest.raises(RuntimeError, match="reward"):
        he_noreward(0, tasks)


def test_serve_command_is_a_pure_lora_enabled_argv():
    from fieldkit._rl_gpu_serve import RLBackendConfig, serve_command

    cfg = RLBackendConfig(
        vllm_url="http://localhost:8000/v1",
        base_model="Qwen/Qwen2.5-7B-Instruct",
        lora_name="policy",
        max_lora_rank=16,
    )
    argv = serve_command(cfg, "/work/step-001/adapter")
    assert "vllm.entrypoints.openai.api_server" in argv
    assert "--enable-lora" in argv
    assert "policy=/work/step-001/adapter" in argv  # served LoRA == chat model
    assert "16" in argv  # --max-lora-rank
    assert "8000" in argv  # port parsed from the url


def test_serve_command_override_substitutes_placeholders():
    from fieldkit._rl_gpu_serve import RLBackendConfig, serve_command

    cfg = RLBackendConfig(
        vllm_url="http://h:8000/v1",
        serve_cmd_override="docker exec C bash -c 'serve {name} {adapter} {port}'",
    )
    joined = " ".join(serve_command(cfg, "/a/b"))
    assert "policy" in joined and "/a/b" in joined and "8000" in joined


def test_stop_command_is_engine_core_aware():
    # RV-R4 / feedback_vllm_engine_core_orphan: the bare vllm.entrypoints pattern
    # orphans the ~108 GB EngineCore worker — the teardown must catch it.
    from fieldkit._rl_gpu_serve import RLBackendConfig, stop_command

    assert "EngineCore" in stop_command(RLBackendConfig())


def test_backend_config_from_env(monkeypatch):
    monkeypatch.setenv("FK_RL_VLLM_URL", "http://h:9000/v1")
    monkeypatch.setenv("FK_RL_MAX_TOKENS", "256")
    monkeypatch.setenv("FK_RL_LORA_NAME", "pol2")
    from fieldkit._rl_gpu_serve import RLBackendConfig

    cfg = RLBackendConfig.from_env(GRPOConfig(base="x", lora_rank=32))
    assert cfg.vllm_url == "http://h:9000/v1"
    assert cfg.max_tokens == 256
    assert cfg.lora_name == "pol2"
    assert cfg.max_lora_rank == 32  # falls back to GRPOConfig.lora_rank when unset


def test_lane_ensure_started_needs_an_initial_adapter():
    from fieldkit._rl_gpu_serve import RLBackendConfig, VLLMLane

    lane = VLLMLane(RLBackendConfig(adapter_init=""))
    assert lane.is_running is False
    with pytest.raises(RuntimeError, match=r"FK_RL_ADAPTER_INIT|initial LoRA"):
        lane.ensure_started("")


def test_build_serve_seams_wires_three_callables_torch_free():
    # The torch trainer is injected, so the wiring is exercisable without torch.
    from fieldkit._rl_gpu_serve import build_serve_seams

    sentinel = object()

    def fake_make_trainer(cfg, lane, gcfg):
        return sentinel

    sampler, trainer, heldout = build_serve_seams(
        GRPOConfig(base="x"),
        fake_make_trainer,
        reward=RewardAdapter(mcq_letter),
        client_factory=lambda cfg: _FakeClient(),
    )
    assert trainer is sentinel
    assert callable(sampler) and callable(heldout)
