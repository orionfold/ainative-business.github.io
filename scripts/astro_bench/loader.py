# Copyright 2026 Manav Sehgal
# SPDX-License-Identifier: Apache-2.0
"""loader.py — bench JSONL → RLLoop tasks + the verifier-as-reward adapter (C3).

The glue that turns the generated astrodynamics bench (`generate.py`'s
`astro-bench-v0.1.jsonl` / `…heldout.jsonl`) into the inputs `fieldkit.rl.RLLoop`
consumes (`_SPECS/astrodynamics-vertical-v1.md` AV-7/AV-8):

- **`AstroTask`** — one bench row as an RLLoop *question*. It exposes
  ``.question`` (the prompt) and ``.expected`` (the canonical ``"<value> <unit>"``
  gold) so `fieldkit.rl._qa_to_rollout_target` pulls the prompt + gold straight
  off it in the real GPU path, while keeping the rich fields (`task_id`, `tier`,
  `rel_tol`, `gold_value_si`) the loader's own bookkeeping needs.
- **`AstroBench`** — the minimal ``bench`` object `RLLoop` reads: it needs only a
  ``.questions`` list. (`fieldkit.eval.VerticalBench` is the production shape;
  this is the local-until-reuse stand-in, per `feedback_keep_scorer_local_until_reuse`.)
- **`make_rollout`** — ``(task, generation) -> fieldkit.reward.Rollout`` with
  ``prediction = generation`` and ``expected = task.expected`` (← the row's
  ``answer``). This is the RV-2 mapping the spec names: *prediction ← model text,
  expected ← answer*.
- **`astro_reward`** — the one-liner that wraps the local `astro_numeric_match`
  (the verifier IS the reward, RV-2) in a `fieldkit.reward.RewardAdapter` with
  ``scorer_kwargs={"rel_tolerance": 0.02}``. The adapter's kwarg introspection
  forwards only ``rel_tolerance`` (the scorer's sole keyword), so the wrap is
  clean — no `fieldkit.eval` promotion (`feedback_keep_scorer_local_until_reuse`).

No GPU, no torch: ``import fieldkit.reward`` / ``fieldkit.rl`` stay stdlib-cheap
(the torch/vLLM seams live behind `gpu_seams`, never imported here). The
companion `smoke_rl.py` drives a ≤2-step `RLLoop` over this glue with **injected
fake seams** to prove held-out-only checkpoint selection on CPU.
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

sys.path.insert(0, os.path.dirname(__file__))

from verifier import astro_numeric_match  # noqa: E402

from fieldkit.reward import RewardAdapter, Rollout  # noqa: E402

REL_TOL = 0.02

# Default bench locations (repo-relative), so callers can `load_bench()` bare.
_EVIDENCE = Path(__file__).resolve().parents[2] / "evidence" / "astrodynamics"
DEFAULT_POOL = _EVIDENCE / "astro-bench-v0.1.jsonl"
DEFAULT_HELDOUT = _EVIDENCE / "astro-bench-v0.1.heldout.jsonl"


@dataclass(frozen=True, slots=True)
class AstroTask:
    """One bench row as an `RLLoop` question.

    ``question`` / ``expected`` satisfy `fieldkit.rl._qa_to_rollout_target` (the
    real GPU sampler reads them off the object); the remaining fields carry the
    row's provenance + the per-row tolerance the reward uses. Frozen + slotted so
    it is hashable (the loop carves a held-out split by indexing + tuple-ing
    these) and cheap.
    """

    task_id: str
    question: str  # the prompt text
    expected: str  # the canonical "<value> <unit>" gold (the row's `answer`)
    topic: str
    subtopic: str
    tier: int
    rel_tol: float = REL_TOL
    gold_value_si: float | None = None
    gold_unit: str = ""
    hand_curated: bool = False


def _row_to_task(row: dict) -> AstroTask:
    return AstroTask(
        task_id=row["task_id"],
        question=row["prompt"],
        expected=row["answer"],
        topic=row.get("topic", ""),
        subtopic=row.get("subtopic", ""),
        tier=int(row.get("tier", 0)),
        rel_tol=float(row.get("rel_tol", REL_TOL)),
        gold_value_si=row.get("gold_value_si"),
        gold_unit=row.get("gold_unit", ""),
        hand_curated=bool(row.get("hand_curated", False)),
    )


def iter_rows(path: str | os.PathLike) -> Iterator[dict]:
    """Yield each non-blank JSONL object from a bench file."""
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            yield json.loads(line)


def load_tasks(path: str | os.PathLike) -> list[AstroTask]:
    """Load a bench JSONL into a list of :class:`AstroTask`."""
    return [_row_to_task(row) for row in iter_rows(path)]


@dataclass
class AstroBench:
    """The minimal ``bench`` `RLLoop` consumes — just a ``.questions`` list."""

    questions: list[AstroTask]

    @classmethod
    def from_jsonl(cls, path: str | os.PathLike) -> AstroBench:
        return cls(load_tasks(path))

    def __len__(self) -> int:
        return len(self.questions)


def load_bench(path: str | os.PathLike = DEFAULT_POOL) -> AstroBench:
    """Load the train/eval pool bench (defaults to the tracked v0.1 pool)."""
    return AstroBench.from_jsonl(path)


def load_heldout(path: str | os.PathLike = DEFAULT_HELDOUT) -> AstroBench:
    """Load the frozen external held-out bench (the disjoint curveball split)."""
    return AstroBench.from_jsonl(path)


def make_rollout(task: AstroTask, generation: str) -> Rollout:
    """Map a task + a model generation → a scoreable `Rollout` (RV-2).

    ``prediction`` is the raw model text (the reward extracts the ``\\boxed{}``
    answer from it); ``expected`` is the row's gold string; ``task_id`` rides
    along so a per-rollout reward can be traced back to the bench row.
    """
    return Rollout(prediction=generation, expected=task.expected, task_id=task.task_id)


def astro_reward(rel_tolerance: float = REL_TOL) -> RewardAdapter:
    """The verifier-as-reward adapter: `astro_numeric_match` → `RewardAdapter` (RV-2).

    Binary pass at threshold 1.0 (the scorer already emits 1.0/0.0); the sole
    forwarded kwarg is ``rel_tolerance``. Kept local — promotes to
    `fieldkit.eval` only on a second vertical's reuse.
    """
    return RewardAdapter(
        astro_numeric_match,
        pass_threshold=1.0,
        scorer_kwargs={"rel_tolerance": rel_tolerance},
    )
