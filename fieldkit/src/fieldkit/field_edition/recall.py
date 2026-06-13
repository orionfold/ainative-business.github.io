# Copyright 2026 Manav Sehgal
# SPDX-License-Identifier: Apache-2.0
"""The §8 Cortex gate's recall-half — vendored frozen set + a pure scorer.

The §8 Cortex gate (:mod:`fieldkit.field_edition.verify`) floors retrieval
``recall@5 ≥ 0.95`` against the Advisor corpus the customer's box ingested at
``up`` time. For that to run on a fresh install with no repo checkout, the
*queries + gold sources* ride the wheel as a vendored data file
(``data/cortex-recall-mini.json``, built by
``scripts/field_edition/build_cortex_recall_set.py`` — a deterministic
projection of the already-frozen Advisor recall bench).

This module is the **pure** half (the deterministic-scripts invariant, same
split as :mod:`doctor`/`up`/`verify`): :func:`load_recall_set` reads the
packaged data, :func:`score_recall_set` computes recall@k given an injected
``retrieve`` callable — so the scorer unit-tests with a fake retriever, no live
Cortex stack. The live retrieval (``MemoryIndex.query`` against pgvector) lives
in :class:`fieldkit.field_edition.verify.LiveGateRunner.cortex`, which builds the
``retrieve`` closure and calls in here.

``recall@5`` here means **source_recall@5**: the fraction of *answerable* rows
whose gold source id appears in the top-5 unique retrieved sources (refusal rows
carry no gold and are excluded from the denominator — they belong to the
grounded-contract / refusal-hygiene half, which needs the serving lane). This is
exactly the metric ``scripts/orionfold_advisor/score_recall_live.py`` measured at
0.977 on the running embedder image.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Sequence

__all__ = [
    "RECALL_SET_PATH",
    "RECALL_SET_SHA",
    "RecallRow",
    "RecallSet",
    "RecallReport",
    "load_recall_set",
    "recall_set_sha",
    "score_recall_set",
]

#: The vendored frozen recall set (rides the wheel via the ``data/*.json`` glob).
RECALL_SET_PATH = Path(__file__).resolve().parent / "data" / "cortex-recall-mini.json"

#: sha256[:12] of the vendored file — the proof-control pin. Re-pin (and re-run
#: every gate) only after a deliberate rebuild via the builder script. Drift from
#: this value means the shipped recall set was edited out-of-band.
RECALL_SET_SHA = "97ce168b851d"


@dataclass(frozen=True)
class RecallRow:
    """One vendored recall probe: a query + its gold source(s)."""

    task_id: str
    question: str
    source_ids: frozenset[str]
    family: str
    split: str
    expected_behavior: str

    @property
    def is_answerable(self) -> bool:
        return self.expected_behavior != "refuse"


@dataclass(frozen=True)
class RecallSet:
    """The vendored frozen recall set + its provenance pins."""

    name: str
    version: str
    rows: tuple[RecallRow, ...]
    source_bench_sha256_12: str
    corpus_table: str
    recall_floor: float

    @property
    def answerable(self) -> tuple[RecallRow, ...]:
        return tuple(r for r in self.rows if r.is_answerable)


@dataclass(frozen=True)
class RecallReport:
    """The measured recall verdict for the vendored set."""

    answerable_n: int
    hits_at_5: int
    recall_at_5: float
    misses: tuple[str, ...]  # task_ids whose gold missed the top-5

    def as_metrics(self) -> dict[str, float]:
        """The numbers the §8 floor logic (``_assess_cortex``) reads."""
        return {
            "recall_at_5": self.recall_at_5,
            "recall_answerable_n": float(self.answerable_n),
            "recall_misses": float(len(self.misses)),
        }


def recall_set_sha(path: Path = RECALL_SET_PATH) -> str:
    """sha256[:12] of the vendored file as it sits on disk (drift check)."""
    return hashlib.sha256(path.read_bytes()).hexdigest()[:12]


def load_recall_set(
    path: Path = RECALL_SET_PATH, *, verify_sha: bool = True
) -> RecallSet:
    """Read the packaged recall set; optionally assert the proof-control sha.

    ``verify_sha`` defaults on — a mismatch against :data:`RECALL_SET_SHA` means
    the shipped set was edited without a deliberate re-pin and raises, never
    silently scoring a tampered set.
    """
    if verify_sha:
        actual = recall_set_sha(path)
        if actual != RECALL_SET_SHA:
            raise ValueError(
                f"recall-set sha drift: {path.name} is {actual}, "
                f"pinned {RECALL_SET_SHA} — rebuild via the builder script + re-pin"
            )
    doc = json.loads(path.read_text(encoding="utf-8"))
    rows = tuple(
        RecallRow(
            task_id=str(r["task_id"]),
            question=str(r["question"]),
            source_ids=frozenset(str(s) for s in (r.get("source_ids") or [])),
            family=str(r["family"]),
            split=str(r["split"]),
            expected_behavior=str(r["expected_behavior"]),
        )
        for r in doc["rows"]
    )
    return RecallSet(
        name=str(doc["name"]),
        version=str(doc["version"]),
        rows=rows,
        source_bench_sha256_12=str(doc["source_bench_sha256_12"]),
        corpus_table=str(doc.get("corpus_table", "advisor_corpus_v01")),
        recall_floor=float(doc.get("recall_floor", 0.95)),
    )


def score_recall_set(
    rows: Sequence[RecallRow],
    retrieve: Callable[[str], Sequence[str]],
    *,
    k: int = 5,
) -> RecallReport:
    """Pure source_recall@k over the *answerable* rows.

    ``retrieve(question)`` returns the ranked, **source-deduped** source ids the
    live stack produced (the caller does the unique-source dedup, mirroring
    ``score_recall_live._top_unique_sources``). A row hits when its gold source
    appears in the top-``k``. Refusal rows are skipped (no gold). With zero
    answerable rows recall is ``0.0`` (an empty set can never clear the floor).
    """
    answerable = [r for r in rows if r.is_answerable]
    hits = 0
    misses: list[str] = []
    for row in answerable:
        topk = set(list(retrieve(row.question))[:k])
        if row.source_ids & topk:
            hits += 1
        else:
            misses.append(row.task_id)
    n = len(answerable)
    recall = round(hits / n, 4) if n else 0.0
    return RecallReport(
        answerable_n=n,
        hits_at_5=hits,
        recall_at_5=recall,
        misses=tuple(misses),
    )
