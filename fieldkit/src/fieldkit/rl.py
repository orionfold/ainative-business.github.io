# Copyright 2026 Manav Sehgal
# SPDX-License-Identifier: Apache-2.0
"""`fieldkit.rl` — the closed-loop RLVR driver (Phase 3, Bet 1 — the *engine*).

The **trainer** half of `_SPECS/rlvr-loop-v1.md` (`fieldkit.reward` is the
scorer half). It wraps the loop that actually *ran* on a single GB10 —
`clawgym-on-spark-grpo`'s **hand-rolled ~280-LOC REINFORCE-with-KL +
kill-and-restart-vLLM**, **not** Unsloth-GRPO or NeMo-RL (neither drove the
working run; `[[project_verl_atgpo_vllm_gap]]` is the cautionary precedent). The
named abstractions are a documented *fallback lane*, not the default (RV-1).

This module owns the **orchestration**, not the GPU math: the control flow
(carve a frozen held-out split → sample a group → reward → group-relative step →
held-out gate → held-out-only checkpoint selection → lineage card) is pure,
deterministic, and unit-testable with injected seams — exactly the
`dispatch_job(runner=…)` pattern. The three GPU-touching seams are **injected**:

- ``sampler(tasks, k) -> list[list[Rollout]]`` — the pinned-vLLM rollout
  (~13 min/step; the dominant cost). The real one lazy-imports vLLM; a test
  passes a fake that returns canned generations.
- ``trainer(rollouts, advantages, step) -> dict`` — the REINFORCE-with-KL LoRA
  step (~22 s) + the **kill-and-restart vLLM** to reload the updated adapter
  (~3.5 min — *the* eliminable quarter, RV-5; hot-LoRA-swap is the tracked
  fast-follow, not a v1 gate).
- ``heldout_eval(step, tasks) -> float`` — the **held-out gate** (RV-4). In the
  Arena-dispatched path this enqueues an M8 ``eval_rerun`` over the frozen split
  (`enqueue_heldout_eval`); standalone it scores directly.

Three corrections from the grounding harvest are encoded structurally
(`roadmap-reconciliation.md` §"Phase 3"):

1. **Pool-convergence is a trap (RV-4).** `t2po` hit pool 87.5% vs held-out 5.7%
   at step 45 — an **81.8 pp inversion**. So the loop evaluates a *frozen*
   held-out split every ≤``heldout_every`` steps and **selects the published
   checkpoint on held-out score, never pool** (:attr:`RLLoop.selected_step`).
2. **Pin vLLM (RV-5).** Six API drifts across two minor versions (one silent
   return-shape change). `GRPOConfig.vllm_pin` records the pinned version.
3. **≥100-row corpus floor (RV-10).** 42 rows mode-collapsed (0/8 held-out).
   :meth:`RLLoop.run` refuses a corpus below `corpus_min` and carves the
   held-out split *before step 0*, trainer-resident, one vLLM lane (the
   2026-04-22 OOM landmine, `[[project_spark_unified_memory_oom]]`).

Per `feedback_llm_skill_pattern`: deterministic Python only. torch / vLLM are
**never imported at module load** — only inside the GPU seam factory
(:func:`gpu_seams`), so ``import fieldkit.rl`` stays stdlib-cheap and the
orchestration tests run with no GPU.
"""

from __future__ import annotations

import contextlib
import contextvars
import random
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterator, Mapping, Optional, Sequence

from fieldkit.lineage import FailureLabel, LineageSnapshot, LineageStore, Trial
from fieldkit.reward import RewardAdapter, Rollout

__all__ = [
    "GRPOConfig",
    "RLLoop",
    "RLLoopError",
    "rl_hooks",
    "current_rl_hooks",
]


# Observability seams (rl-lane-autonomy-v1 LA-8/10). The arena dispatcher pushes
# a (progress_cb, should_abort) pair down here via :func:`rl_hooks` so the loop
# can report live step state + poll an abort sentinel **without** fieldkit.rl
# importing anything from fieldkit.arena (the conduit flows arena → rl, never
# back). A bare ``import fieldkit.rl`` leaves the hooks unset → zero overhead.
ProgressCb = Callable[[Mapping[str, Any]], None]
ShouldAbort = Callable[[], bool]
_RL_HOOKS: contextvars.ContextVar[Optional[tuple[Optional[ProgressCb], Optional[ShouldAbort]]]] = (
    contextvars.ContextVar("fk_rl_hooks", default=None)
)


@contextlib.contextmanager
def rl_hooks(
    progress_cb: Optional[ProgressCb] = None,
    should_abort: Optional[ShouldAbort] = None,
) -> Iterator[None]:
    """Bind live-progress + abort hooks for any :class:`RLLoop` run in this scope.

    The Arena `rl_run` dispatch enters this around the loop so an unmodified
    :func:`fieldkit.harness.mcp.run_rl_loop` — which builds the loop without
    knowing about progress — still reports live and respects an OOM abort. The
    hooks ride a :class:`contextvars.ContextVar`, so they are thread- and
    task-local and auto-reset on exit.
    """
    token = _RL_HOOKS.set((progress_cb, should_abort))
    try:
        yield
    finally:
        _RL_HOOKS.reset(token)


def current_rl_hooks() -> tuple[Optional[ProgressCb], Optional[ShouldAbort]]:
    """The ambient ``(progress_cb, should_abort)`` for this scope (``(None, None)``
    when no :func:`rl_hooks` is active)."""
    hooks = _RL_HOOKS.get()
    return hooks if hooks is not None else (None, None)


class RLLoopError(Exception):
    """Raised on a loop-configuration or envelope-violation fault.

    The two load-bearing cases: a corpus below :attr:`GRPOConfig.corpus_min`
    (the ≥100-row floor that 42 rows violated, RV-10), and a missing GPU seam
    (a `.run()` with no `sampler` / `trainer` / `heldout_eval` injected and no
    `gpu_seams` available — the real loop needs the `fieldkit[rl]` extra + a
    pinned vLLM).
    """


# Injected GPU-seam signatures (documented, not enforced — duck-typed at call).
Sampler = Callable[[Sequence[Any], int], "list[list[Rollout]]"]
Trainer = Callable[["list[Rollout]", "list[float]", int], Mapping[str, Any]]
HeldoutEval = Callable[[int, Sequence[Any]], float]


@dataclass(frozen=True, slots=True)
class GRPOConfig:
    """Hyperparameters for one RLVR run — the proven `clawgym` knobs (RV-1).

    Defaults mirror the only loop that ran end-to-end on a single GB10: rank-16
    LoRA, 8 tasks/step × K=4 = a 32-rollout bundle, temperature 0.8, ~34 steps.
    `heldout_every` (≤10) drives the hard gate (RV-4); `corpus_min` (≥100) is
    the floor (RV-10); `vllm_pin` records the pinned vLLM version (RV-5).
    `heldout_frac` is the fraction carved into the frozen held-out split before
    step 0; `seed` makes the split + the per-step task draw deterministic.
    `heldout_patience` (default off) optionally stops the run early when the
    held-out score stops improving — the RV-R1 inversion guard.
    """

    base: str
    lora_rank: int = 16
    group_k: int = 4
    tasks_per_step: int = 8
    temp: float = 0.8
    heldout_every: int = 10
    vllm_pin: str = ""
    max_steps: int = 34
    corpus_min: int = 100
    heldout_frac: float = 0.2
    kl_coef: float = 0.1
    lr: float = 1e-6
    seed: int = 0
    heldout_patience: Optional[int] = None

    def __post_init__(self) -> None:
        problems: list[str] = []
        if self.group_k < 1:
            problems.append("group_k must be ≥ 1")
        if self.tasks_per_step < 1:
            problems.append("tasks_per_step must be ≥ 1")
        if self.heldout_every < 1:
            problems.append("heldout_every must be ≥ 1 (RV-4 hard gate)")
        if self.max_steps < 1:
            problems.append("max_steps must be ≥ 1")
        if self.corpus_min < 1:
            problems.append("corpus_min must be ≥ 1")
        if not (0.0 < self.heldout_frac < 1.0):
            problems.append("heldout_frac must be in (0, 1)")
        if self.heldout_patience is not None and self.heldout_patience < 1:
            problems.append("heldout_patience must be None or ≥ 1")
        if problems:
            raise RLLoopError("invalid GRPOConfig: " + "; ".join(problems))


def _split_corpus(
    questions: Sequence[Any], frac: float, seed: int
) -> tuple[tuple[Any, ...], tuple[Any, ...]]:
    """Deterministically carve a frozen held-out split (RV-4/RV-10).

    Returns ``(train_pool, heldout)`` as immutable tuples. The split is computed
    once, *before step 0*, from a seeded shuffle — so the held-out gate scores
    questions the policy never trains on, and the same seed reproduces the same
    split. At least one question lands in each side.
    """
    idx = list(range(len(questions)))
    random.Random(seed).shuffle(idx)
    n_heldout = max(1, round(len(questions) * frac))
    n_heldout = min(n_heldout, len(questions) - 1)  # keep ≥1 in train
    heldout_idx = set(idx[:n_heldout])
    heldout = tuple(questions[i] for i in sorted(heldout_idx))
    train = tuple(questions[i] for i in range(len(questions)) if i not in heldout_idx)
    return train, heldout


def _qa_to_rollout_target(q: Any) -> tuple[str, str, Any]:
    """Pull ``(question, expected, rubric)`` off a VerticalQA / mapping."""
    if isinstance(q, Mapping):
        return q.get("question", ""), q.get("expected", ""), q.get("rubric")
    return (
        getattr(q, "question", ""),
        getattr(q, "expected", ""),
        getattr(q, "tags", None),
    )


@dataclass
class RLLoop:
    """The closed-loop RLVR driver: sample → reward → step → gate → select.

    Construct with a :class:`GRPOConfig`, a :class:`~fieldkit.reward.
    RewardAdapter` (the verifier-as-reward), and a bench (any object with a
    ``questions`` list — `fieldkit.eval.VerticalBench`). Inject the three GPU
    seams (`sampler`, `trainer`, `heldout_eval`); a test passes fakes, the Arena
    `run_rl_loop` tool passes :func:`gpu_seams`. :meth:`run` returns the run's
    :class:`~fieldkit.lineage.LineageSnapshot` — the **`rl_run` card** and the
    source of the §5 "living-model" delta chart (RV-7).

    After :meth:`run`, :attr:`heldout_scores`, :attr:`selected_step`, and
    :attr:`selected_heldout_score` expose the **held-out-only** checkpoint pick
    (RV-4) — never the pool-best.
    """

    config: GRPOConfig
    reward: RewardAdapter
    bench: Any
    sampler: Optional[Sampler] = None
    trainer: Optional[Trainer] = None
    heldout_eval: Optional[HeldoutEval] = None
    lineage_store: Optional[LineageStore] = None
    domain: str = "patent-strategist"
    # Observability seams (LA-8/10) — explicit injection wins; when left None the
    # loop falls back to the ambient :func:`rl_hooks` so run_rl_loop needs no edit.
    progress_cb: Optional[ProgressCb] = None
    should_abort: Optional[ShouldAbort] = None

    # Populated by run().
    heldout_scores: dict[int, float] = field(default_factory=dict, init=False)
    pool_scores: dict[int, float] = field(default_factory=dict, init=False)
    selected_step: Optional[int] = field(default=None, init=False)
    selected_heldout_score: Optional[float] = field(default=None, init=False)
    aborted: bool = field(default=False, init=False)
    # AE-3 — bounded per-step trajectory (one dict/step): which steps moved the
    # policy, captured live in run() and surfaced through summary() → result_json.
    step_history: list[dict[str, Any]] = field(default_factory=list, init=False)

    def _store(self) -> LineageStore:
        if self.lineage_store is not None:
            return self.lineage_store
        # Higher-reward-is-better, so the rendered card's "best" tracks the
        # pool metric sensibly; checkpoint *selection* ignores this and uses
        # the held-out dict directly (RV-4).
        root = Path(tempfile.mkdtemp(prefix="fk-rl-"))
        return LineageStore(root, lower_is_better=False)

    def run(self) -> LineageSnapshot:
        """Run the loop to `max_steps` and return the `rl_run` lineage card.

        Refuses a corpus below `corpus_min` (RV-10). Carves the frozen held-out
        split before step 0. Each step: draw `tasks_per_step` from the train
        pool → `sampler` rolls out K each → `reward.score` + `group_advantage`
        per group → `trainer` takes one REINFORCE-with-KL LoRA step (and
        restarts vLLM) → a :class:`Trial` is logged. Every ≤`heldout_every`
        steps the **held-out gate** runs and its score is recorded. The
        published checkpoint is ``argmax`` over **held-out** scores only.
        """
        if self.sampler is None or self.trainer is None or self.heldout_eval is None:
            raise RLLoopError(
                "RLLoop.run needs sampler + trainer + heldout_eval injected. "
                "The real GPU loop is fieldkit.rl.gpu_seams (needs the "
                "fieldkit[rl] extra + a pinned vLLM); a test injects fakes."
            )
        from fieldkit.reward import group_advantage  # local — keep load cheap

        questions = list(getattr(self.bench, "questions", []) or [])
        if len(questions) < self.config.corpus_min:
            raise RLLoopError(
                f"corpus has {len(questions)} rows < corpus_min="
                f"{self.config.corpus_min} (RV-10: 42 rows mode-collapsed, "
                "0/8 held-out). Grow the corpus before training."
            )

        train_pool, heldout = _split_corpus(
            questions, self.config.heldout_frac, self.config.seed
        )
        store = self._store()
        store.append(_baseline_trial(self.config, self.domain, len(train_pool), len(heldout)))

        # Resolve the observability seams (LA-8/10): explicit injection wins,
        # else the ambient rl_hooks bound by the Arena dispatcher.
        progress_cb = self.progress_cb
        should_abort = self.should_abort
        if progress_cb is None or should_abort is None:
            amb_progress, amb_abort = current_rl_hooks()
            progress_cb = progress_cb or amb_progress
            should_abort = should_abort or amb_abort

        draw_rng = random.Random(self.config.seed + 1)
        prev_exp = "baseline"
        best_heldout = float("-inf")
        stale = 0
        step_durations: list[float] = []
        self._emit(progress_cb, phase="lane-bringup", step=0, durations=step_durations)

        for step in range(self.config.max_steps):
            # Abort check BETWEEN steps (LA-10): the watchdog has touched the
            # sentinel → tear down cleanly rather than walk into the OOM kill.
            if should_abort is not None and should_abort():
                self.aborted = True
                store.append(_aborted_trial(self.config, self.domain, prev_exp, step))
                break
            t_step = time.monotonic()
            self._emit(progress_cb, phase="sampling", step=step, durations=step_durations)
            k_tasks = min(self.config.tasks_per_step, len(train_pool))
            tasks = draw_rng.sample(list(train_pool), k_tasks)
            groups = self.sampler(tasks, self.config.group_k)

            flat_rollouts: list[Any] = []
            flat_adv: list[float] = []
            rewards_all: list[Any] = []
            for group in groups:
                rewards = self.reward.score_group(group)
                adv = group_advantage(rewards)
                flat_rollouts.extend(group)
                flat_adv.extend(adv)
                rewards_all.extend(rewards)

            # AE-2 — degenerate-step telemetry. A GRPO step whose every group has
            # uniform reward yields all-zero advantage → no gradient, no adapter,
            # no lane restart (correct behavior with a strong SFT init, but it
            # reads IDENTICAL to a stall on the board until surfaced). `n_used` =
            # rollouts carrying a non-zero advantage (the ones that move the
            # policy); `adv_spread` = the advantage range; `trained` flips False
            # on a no-op step.
            n_used = sum(1 for a in flat_adv if abs(a) > 1e-12)
            adv_spread = (max(flat_adv) - min(flat_adv)) if flat_adv else 0.0
            trained = n_used > 0

            metrics = dict(self.trainer(flat_rollouts, flat_adv, step) or {})
            pool_mean = (
                sum(r.scalar for r in rewards_all) / len(rewards_all)
                if rewards_all
                else 0.0
            )
            keep_rate = (
                sum(1 for r in rewards_all if r.success) / len(rewards_all)
                if rewards_all
                else 0.0
            )
            self.pool_scores[step] = pool_mean
            step_durations.append(time.monotonic() - t_step)
            self._emit(
                progress_cb, phase="training", step=step, pool=pool_mean,
                keep_rate=keep_rate, n_used=n_used, adv_spread=adv_spread,
                trained=trained, durations=step_durations,
            )
            exp_id = f"rl-{step:03d}"
            store.append(
                Trial(
                    exp_id=exp_id,
                    timestamp="",
                    specialist=self.domain,
                    parent_exp=prev_exp,
                    baseline_exp="baseline",
                    domain=self.domain,
                    hypothesis=f"GRPO step {step} (k={self.config.group_k}, "
                    f"{k_tasks} tasks, pool keep-rate {keep_rate:.2f})",
                    expected_delta="",
                    status=FailureLabel.KEEP if keep_rate > 0 else FailureLabel.DISCARD,
                    core_metric=round(pool_mean, 6),
                    val_bpb=None,
                    delta_vs_best=None,
                    train_s=_as_float(metrics.get("train_s")),
                    total_s=_as_float(metrics.get("total_s")),
                    job_name=f"rl_run:{self.config.base}",
                    snapshot_path=str(metrics.get("checkpoint", "")),
                    notes=f"loss={metrics.get('loss')} kl={metrics.get('kl')} "
                    f"vllm_pin={self.config.vllm_pin}",
                )
            )
            prev_exp = exp_id

            # AE-3 — capture the step record now (before the inversion-guard can
            # break the loop in the gate below), patched with the held-out score
            # if this step runs a gate.
            self.step_history.append(
                {
                    "step": step,
                    "phase": "training",
                    "pool_score": round(pool_mean, 6),
                    "last_heldout": None,
                    "keep_rate": round(keep_rate, 6),
                    "loss": _as_float(metrics.get("loss")),
                    "kl": _as_float(metrics.get("kl")),
                    "n_used": n_used,
                    "adv_spread": round(adv_spread, 6),
                    "step_duration": round(step_durations[-1], 3),
                    "trained": trained,
                }
            )

            if step % self.config.heldout_every == 0:
                self._emit(
                    progress_cb, phase="heldout-gate", step=step,
                    pool=pool_mean, durations=step_durations,
                )
                ho = float(self.heldout_eval(step, heldout))
                self.heldout_scores[step] = ho
                if self.step_history:  # AE-3 — patch this step's gate score
                    self.step_history[-1]["last_heldout"] = round(ho, 6)
                    self.step_history[-1]["phase"] = "heldout-gate"
                self._emit(
                    progress_cb, phase="heldout-gate", step=step, pool=pool_mean,
                    heldout=ho, gate=True, durations=step_durations,
                )
                store.append(
                    Trial(
                        exp_id=f"heldout-{step:03d}",
                        timestamp="",
                        specialist="heldout-gate",
                        parent_exp=exp_id,
                        baseline_exp="baseline",
                        domain=self.domain,
                        hypothesis=f"held-out gate @ step {step} (frozen split, "
                        f"n={len(heldout)}) — selection metric, NOT pool",
                        expected_delta="",
                        status=FailureLabel.KEEP,
                        core_metric=round(ho, 6),
                        val_bpb=None,
                        delta_vs_best=None,
                        train_s=None,
                        total_s=None,
                        job_name=f"rl_run:{self.config.base}",
                        snapshot_path=str(metrics.get("checkpoint", "")),
                        notes="held-out checkpoint-selection metric (RV-4)",
                    )
                )
                # RV-R1 inversion guard — stop if held-out stops improving.
                if ho > best_heldout:
                    best_heldout = ho
                    stale = 0
                else:
                    stale += 1
                    if (
                        self.config.heldout_patience is not None
                        and stale >= self.config.heldout_patience
                    ):
                        break

        self._emit(progress_cb, phase="teardown", step=len(self.pool_scores), durations=step_durations)
        self._select_checkpoint()
        return store.render_prompt("rl_run", session_timestamp="")

    def _emit(
        self,
        progress_cb: Optional[ProgressCb],
        *,
        phase: str,
        step: int,
        pool: Optional[float] = None,
        heldout: Optional[float] = None,
        gate: bool = False,
        keep_rate: Optional[float] = None,
        n_used: Optional[int] = None,
        adv_spread: Optional[float] = None,
        trained: Optional[bool] = None,
        durations: Optional[list[float]] = None,
    ) -> None:
        """Push one live-progress blob (LA-8) — best-effort, never fails the run.

        Carries the step counter, the phase, the latest pool + held-out scalars,
        a steps-remaining ETA from the running mean step duration, and (AE-2) the
        degenerate-step signal — `keep_rate` / `n_used` / `adv_spread` / `trained`
        — so the board can read a no-op zero-advantage step as distinct from a
        stall. The writer downstream throttles + folds in a memory sample; here we
        only describe *where the loop is*.
        """
        if progress_cb is None:
            return
        eta_s: Optional[float] = None
        if durations:
            avg = sum(durations) / len(durations)
            eta_s = round(avg * max(0, self.config.max_steps - step - 1), 1)
        try:
            progress_cb(
                {
                    "step": step,
                    "max_steps": self.config.max_steps,
                    "phase": phase,
                    "pool_score": (round(pool, 6) if pool is not None else None),
                    "last_heldout": (round(heldout, 6) if heldout is not None else None),
                    "gate": gate,
                    "eta_s": eta_s,
                    "base": self.config.base,
                    "domain": self.domain,
                    # AE-2 — degenerate-step visibility (None on non-training phases)
                    "keep_rate": (round(keep_rate, 6) if keep_rate is not None else None),
                    "n_used": n_used,
                    "adv_spread": (round(adv_spread, 6) if adv_spread is not None else None),
                    "trained": trained,
                }
            )
        except Exception:  # noqa: BLE001 — progress is observational, not load-bearing
            pass

    def _select_checkpoint(self) -> None:
        """Pick the published checkpoint on **held-out** score only (RV-4)."""
        if not self.heldout_scores:
            self.selected_step = None
            self.selected_heldout_score = None
            return
        self.selected_step = max(self.heldout_scores, key=lambda s: self.heldout_scores[s])
        self.selected_heldout_score = self.heldout_scores[self.selected_step]

    def summary(self) -> dict[str, Any]:
        """Compact run record for the Arena ``jobs.result_json`` (RV-6/RV-8).

        Aggregate-only (no rollout text) — the held-out checkpoint pick, the
        held-out vs pool trajectories, and the run config. The full per-step
        trajectory rides `fieldkit.lineage` (RV-7); this is the dispatcher's
        digest.
        """
        return {
            "base": self.config.base,
            "domain": self.domain,
            "vllm_pin": self.config.vllm_pin,
            "n_steps": len(self.pool_scores),
            "selected_step": self.selected_step,
            "selected_heldout_score": (
                round(self.selected_heldout_score, 6)
                if self.selected_heldout_score is not None
                else None
            ),
            "heldout_scores": {s: round(v, 6) for s, v in sorted(self.heldout_scores.items())},
            "pool_scores": {s: round(v, 6) for s, v in sorted(self.pool_scores.items())},
            "selected_on": "heldout",  # RV-4 — never pool
            "aborted": self.aborted,  # LA-10 — watchdog tore the run down early
            # AE-3 — the bounded per-step trajectory (reconstructs which steps
            # moved the policy after the run); AE-R2 caps it at max_steps rows.
            "step_history": list(self.step_history),
            # AE-4 — back-pointer from the held-out-selected step to its lineage
            # trial id (`rl-<step>`), so a regression traces to the exact ckpt.
            "selected_exp_id": (
                f"rl-{self.selected_step:03d}" if self.selected_step is not None else None
            ),
        }


def _baseline_trial(cfg: GRPOConfig, domain: str, n_train: int, n_heldout: int) -> Trial:
    return Trial(
        exp_id="baseline",
        timestamp="",
        specialist="baseline",
        parent_exp="",
        baseline_exp="baseline",
        domain=domain,
        hypothesis=f"RLVR seed — base={cfg.base}, rank-{cfg.lora_rank} LoRA, "
        f"K={cfg.group_k}, {n_train} train / {n_heldout} held-out (frozen)",
        expected_delta="",
        status=FailureLabel.BASELINE,
        core_metric=None,
        val_bpb=None,
        delta_vs_best=None,
        train_s=None,
        total_s=None,
        job_name=f"rl_run:{cfg.base}",
        snapshot_path="",
        notes=f"corpus_min={cfg.corpus_min} heldout_every={cfg.heldout_every} "
        f"vllm_pin={cfg.vllm_pin}",
    )


def _aborted_trial(cfg: GRPOConfig, domain: str, parent_exp: str, step: int) -> Trial:
    """A lineage row recording an OOM-watchdog abort (LA-10) before ``step``."""
    return Trial(
        exp_id=f"aborted-{step:03d}",
        timestamp="",
        specialist="oom-watchdog",
        parent_exp=parent_exp,
        baseline_exp="baseline",
        domain=domain,
        hypothesis=f"run aborted before step {step} — memory watchdog tripped the "
        "headroom floor (LA-10), torn down before the kernel OOM-kill",
        expected_delta="",
        status=FailureLabel.DISCARD,
        core_metric=None,
        val_bpb=None,
        delta_vs_best=None,
        train_s=None,
        total_s=None,
        job_name=f"rl_run:{cfg.base}",
        snapshot_path="",
        notes="oom_envelope abort (rl-lane-autonomy LA-10)",
    )


def _as_float(v: Any) -> Optional[float]:
    try:
        return float(v) if v is not None else None
    except (TypeError, ValueError):
        return None


def gpu_seams(
    config: GRPOConfig, *, reward: Optional["RewardAdapter"] = None
) -> tuple[Sampler, Trainer, HeldoutEval]:
    """Build the real GPU-backed `(sampler, trainer, heldout_eval)` seams.

    This is the production path the Arena ``run_rl_loop`` tool wires (the
    vendored `clawgym-on-spark-grpo` loop): a pinned-vLLM rollout over the local
    OpenAI endpoint, the hand-rolled REINFORCE-with-KL LoRA step +
    kill-and-restart (RV-1/RV-5), and a held-out bench score through the reward
    adapter. The backend splits in two so plain ``import fieldkit.rl`` stays
    stdlib-cheap and only this call touches the GPU stack:

    - :mod:`fieldkit._rl_gpu_serve` — **torch-free** (the HTTP sampler via
      `fieldkit.nim.NIMClient` + the vLLM serve lane); always importable.
    - :mod:`fieldkit._rl_gpu_trainer` — the torch/peft REINFORCE step. Importing
      it **is** the `fieldkit[rl]` gate: a missing-dependency ``ImportError``
      becomes a friendly :class:`RLLoopError` pointing at the extra.

    `reward` is the :class:`~fieldkit.reward.RewardAdapter` the **held-out gate**
    scores the frozen split with (the verifier's score, never the pool — RV-4);
    ``run_rl_loop`` passes it. Omit it only when you intend to inject your own
    `heldout_eval` into `RLLoop` instead.

    **The run is operator-armed, not synchronous.** The seams are real, but a
    live run needs the `fieldkit[rl]` extra installed *and* a pinned vLLM with an
    aarch64+CUDA-13 wheel served on the box (`[[project_verl_atgpo_vllm_gap]]`),
    plus ``FK_RL_ADAPTER_INIT`` and friends (see :mod:`fieldkit._rl_gpu_serve`).
    Without the GPU stack this raises :class:`RLLoopError` — callers can still
    inject fakes into `RLLoop` to exercise the orchestration. The hot-LoRA-swap
    optimization (RV-5) lands in the trainer as the tracked fast-follow.
    """
    from fieldkit import _rl_gpu_serve  # torch-free — always importable

    try:
        from fieldkit import _rl_gpu_trainer  # the fieldkit[rl] / torch gate
    except ImportError as exc:
        raise RLLoopError(
            "the GPU GRPO backend needs the fieldkit[rl] extra "
            "(torch + peft + transformers + safetensors) — `pip install "
            "'fieldkit[rl]'` — plus a pinned vLLM with an aarch64+CUDA-13 wheel "
            "served locally (project_verl_atgpo_vllm_gap). Until then inject "
            f"sampler/trainer/heldout_eval into RLLoop directly. ({exc})"
        ) from exc

    return _rl_gpu_serve.build_serve_seams(
        config, _rl_gpu_trainer.make_trainer, reward=reward
    )
