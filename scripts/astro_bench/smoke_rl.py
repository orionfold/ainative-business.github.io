# Copyright 2026 Manav Sehgal
# SPDX-License-Identifier: Apache-2.0
"""smoke_rl.py — a ≤2-step `RLLoop` over the astro bench with FAKE seams (C3).

The CPU smoke `_SPECS/astrodynamics-vertical-v1.md` AV-8 asks for: drive the real
`fieldkit.rl.RLLoop` orchestration end-to-end with **injected fake GPU seams**
(no vLLM, no torch) and **prove the loop selects its published checkpoint on the
held-out score only, never the pool** (RV-4 — the t2po 81.8 pp pool↔held-out
inversion defense).

The proof is constructed, not hoped for. The three seams are scripted into a
deliberate **inversion**:

- `_InversionSampler` — pool correctness *rises* every step (step 0 is mostly
  wrong, step 1 is all-correct). So the **pool**-best checkpoint is the *last*
  step — exactly the overfitting trajectory that fooled `t2po`.
- `_scripted_heldout` — the frozen held-out score *peaks early then falls*
  (step 0 high, step 1 low). So the **held-out**-best checkpoint is step 0.

A loop that (wrongly) selected on pool would publish step 1; the RV-4 loop
publishes step 0. `assert loop.selected_step == 0 != pool_argmax` is the smoke.

Everything is pure-Python + deterministic (seeded). Run::

    /tmp/fk/bin/python scripts/astro_bench/smoke_rl.py

Reward correctness rides the real `loader.astro_reward()` (the verifier IS the
reward) — the sampler emits genuine ``\\boxed{}`` strings the adapter grades, so
this also exercises the bench→Rollout→reward path, not just the control flow.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

sys.path.insert(0, os.path.dirname(__file__))

from loader import AstroBench, AstroTask, astro_reward, load_bench, make_rollout  # noqa: E402

from fieldkit.reward import Rollout  # noqa: E402
from fieldkit.rl import GRPOConfig, RLLoop  # noqa: E402

# A universally-wrong answer: bare 0 is assumed to be in gold's unit, and every
# astro gold is non-zero, so |0 - gold| always exceeds the ±2% band → reward 0.
_WRONG = "<think>botched the algebra</think>\\boxed{0}"


def _correct(task: AstroTask) -> str:
    """A correct generation for `task` — the gold string in a ``\\boxed{}``."""
    return f"<think>solved it</think>\\boxed{{{task.expected}}}"


@dataclass
class _InversionSampler:
    """Fake pinned-vLLM rollout whose POOL accuracy rises every call (the trap).

    ``correct_frac_by_step[n]`` is the fraction of each task's K rollouts that
    carry the correct boxed answer on call *n* (clamped to the last entry past
    the end). Rising fractions → a pool score that climbs monotonically, so a
    pool-best selector would always crown the final step.
    """

    correct_frac_by_step: Sequence[float]
    calls: int = field(default=0, init=False)

    def __call__(self, tasks: Sequence[AstroTask], k: int) -> list[list[Rollout]]:
        i = min(self.calls, len(self.correct_frac_by_step) - 1)
        frac = self.correct_frac_by_step[i]
        self.calls += 1
        n_correct = round(frac * k)
        groups: list[list[Rollout]] = []
        for task in tasks:
            group = [
                make_rollout(task, _correct(task) if j < n_correct else _WRONG)
                for j in range(k)
            ]
            groups.append(group)
        return groups


def _fake_trainer(
    rollouts: Sequence[Any], advantages: Sequence[float], step: int
) -> Mapping[str, Any]:
    """No-op LoRA step — records plausible metrics, touches no GPU."""
    return {
        "loss": round(1.0 / (step + 1), 4),
        "kl": 0.01,
        "train_s": 0.0,
        "total_s": 0.0,
        "checkpoint": f"/tmp/astro-fake-ckpt/step-{step}",
    }


def _scripted_heldout(scores_by_step: Mapping[int, float]):
    """Frozen-split held-out gate scripted to PEAK EARLY (the inversion)."""

    def _eval(step: int, tasks: Sequence[AstroTask]) -> float:
        # Default to the last scripted score for any unscripted step.
        if step in scores_by_step:
            return scores_by_step[step]
        return scores_by_step[max(scores_by_step)]

    return _eval


def run_inversion_smoke(
    bench: AstroBench | None = None,
    *,
    max_steps: int = 2,
    pool_fracs: Sequence[float] = (0.25, 1.0),
    heldout_traj: Mapping[int, float] | None = None,
    seed: int = 0,
) -> RLLoop:
    """Run the ≤2-step inversion smoke and return the finished `RLLoop`.

    Pool accuracy climbs (`pool_fracs`); held-out peaks early (`heldout_traj`).
    After ``run()`` the loop's ``selected_step`` is the held-out argmax (RV-4),
    which differs from the pool argmax — the assertion the caller checks.
    """
    if bench is None:
        bench = load_bench()
    if heldout_traj is None:
        heldout_traj = {0: 0.90, 1: 0.20}

    config = GRPOConfig(
        base="Qwen/Qwen3-8B",
        max_steps=max_steps,
        heldout_every=1,  # gate every step so a ≤2-step run yields ≥2 held-out points
        tasks_per_step=8,
        group_k=4,
        seed=seed,
        vllm_pin="0.10.2-aarch64-cu13 (fake-smoke)",
    )
    loop = RLLoop(
        config=config,
        reward=astro_reward(),
        bench=bench,
        sampler=_InversionSampler(pool_fracs),
        trainer=_fake_trainer,
        heldout_eval=_scripted_heldout(heldout_traj),
        domain="astrodynamics",
    )
    loop.run()
    return loop


def _pool_argmax(loop: RLLoop) -> int | None:
    if not loop.pool_scores:
        return None
    return max(loop.pool_scores, key=lambda s: loop.pool_scores[s])


def main() -> int:
    bench = load_bench()
    print(f"loaded pool bench: {len(bench)} questions "
          f"({bench.questions[0].topic} … {bench.questions[-1].topic})")
    loop = run_inversion_smoke(bench)

    pool_best = _pool_argmax(loop)
    summary = loop.summary()
    print("\n--- ≤2-step RLLoop smoke (fake seams, no GPU) ---")
    print(f"  pool_scores      : {summary['pool_scores']}  (pool-best step = {pool_best})")
    print(f"  heldout_scores   : {summary['heldout_scores']}")
    print(f"  selected_step    : {loop.selected_step}   selected_on = {summary['selected_on']}")
    print(f"  selected_heldout : {loop.selected_heldout_score}")

    ok = (
        loop.selected_step == 0
        and pool_best == loop.config.max_steps - 1
        and loop.selected_step != pool_best
    )
    if ok:
        print("\n  PASS — checkpoint selected on HELD-OUT (step 0), not pool "
              f"(step {pool_best}). RV-4 held-out-only selection proven.")
        return 0
    print("\n  FAIL — selection did not honor held-out-only checkpoint pick.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
