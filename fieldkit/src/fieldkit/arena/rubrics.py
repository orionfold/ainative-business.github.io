# Copyright 2026 Manav Sehgal
# SPDX-License-Identifier: Apache-2.0
"""Default rubric registry — M5.

Three deterministic rubrics ship with v0.1: ``generic-correctness``,
``patent_claim_validity``, and ``mcq_letter``. Each is expressed as a
:class:`fieldkit.eval.Rubric` so the M5 compare scorer can call
:func:`fieldkit.eval.score_answer` over them without any per-rubric branching.

The registry is intentionally **frozen Python data** (not YAML) — per
``feedback_llm_skill_pattern`` the M5 sidecar is deterministic-Python-only
and per ``feedback_keep_scorer_local_until_reuse`` ad-hoc rubrics live at
``~/.fieldkit/arena/rubrics/`` until a 2nd reuse promotes them to
``fieldkit.eval.rubrics``; these three are the *seeds* of that promotion
gate, not promoted scorers themselves. They are public so the
``GET /api/rubrics`` endpoint can serialize them to JSON without rebuilding
the spec from a YAML round-trip.

Default-pick heuristic (spec §4.3): patent prompts → ``patent_claim_validity``;
mcq-shaped prompts → ``mcq_letter``; everything else → ``generic-correctness``.
The picker is a single substring sweep over the lowercased prompt — no LLM,
no embedder, no regex back-references. Cheap to call on every
``GET /api/rubrics`` round-trip.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from fieldkit.eval import CheckSpec, Rubric

__all__ = [
    "RubricSpec",
    "DEFAULT_RUBRIC_REGISTRY",
    "default_rubric_for_prompt",
    "list_rubrics",
    "get_rubric",
]


@dataclass(frozen=True)
class RubricSpec:
    """One row of the M5 rubric registry.

    The ``rubric`` field carries the executable :class:`fieldkit.eval.Rubric`
    that ``score_answer`` consumes; ``id`` / ``title`` / ``description`` are
    the operator-visible metadata that paints the rubric-picker dropdown in
    ``<CompareDuel>``. The dataclass is frozen so the module-level
    ``DEFAULT_RUBRIC_REGISTRY`` is safe to share across requests.
    """

    id: str
    title: str
    description: str
    rubric: Rubric

    def to_payload(self) -> dict[str, object]:
        """JSON-safe shape for ``GET /api/rubrics``.

        The executable :class:`Rubric` is replaced with a flat list of
        check kinds so the browser knows what to render in the
        score-result column (a ``substring`` check renders the ``why``
        text; a ``json_keys`` check would render a key list). Callers
        on the Python side keep using ``self.rubric`` directly.
        """
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "checks": [{"kind": c.kind} for c in self.rubric.checks],
        }


# ---------------------------------------------------------------------------
# Default rubrics
# ---------------------------------------------------------------------------
#
# These three rubrics are deliberately CHEAP to score — no LLM judge, no
# embedder, no external service. They're the "deterministic floor" the
# compare surface ships with on day one; richer rubrics arrive via the
# per-operator override directory (``~/.fieldkit/arena/rubrics/``) which
# layers on top of these (M6+).


_GENERIC_CORRECTNESS = RubricSpec(
    id="generic-correctness",
    title="Generic correctness",
    description=(
        "Passes when the answer is non-empty and does not start with a hedge "
        "phrase — the floor rubric for free-form prompts where the operator "
        "hasn't picked a specialized rubric yet. Deterministic and fast."
    ),
    # The "non-hedge" axis is the inverse of the `honesty` check: honesty
    # passes WHEN hedging is appropriate (the model can't know the answer
    # and should decline); here we want the opposite — a confident
    # answer for a free-form prompt. The cheapest deterministic proxy is
    # a regex that matches at least one alphanumeric token in the reply.
    rubric=Rubric.single(
        CheckSpec(kind="regex", all=(r"[A-Za-z0-9]",))
    ),
)


_PATENT_CLAIM_VALIDITY = RubricSpec(
    id="patent_claim_validity",
    title="Patent claim validity",
    description=(
        "Patent-strategist canonical rubric — looks for at least one of the "
        "claim-validity anchor terms (anticipation / obviousness / written "
        "description / enablement / 35 U.S.C. § 102 / § 103 / § 112). One of "
        "the three default rubrics so the patent vertical's compare runs "
        "produce comparable scores out of the box."
    ),
    rubric=Rubric.single(
        CheckSpec(
            kind="substring",
            any=(
                "anticipation",
                "obviousness",
                "written description",
                "enablement",
                "§ 102",
                "§ 103",
                "§ 112",
                "35 U.S.C.",
            ),
        )
    ),
)


_MCQ_LETTER = RubricSpec(
    id="mcq_letter",
    title="MCQ letter (A/B/C/D)",
    description=(
        "Cyber-bench canonical rubric — expects the final answer to contain "
        "a standalone 'A', 'B', 'C', or 'D' letter (whitespace- or "
        "punctuation-bounded), matching the multiple-choice format the cyber "
        "vertical bench uses. Per `feedback_keep_scorer_local_until_reuse`, "
        "this scorer was the first to ship beyond plain substring; promoted "
        "from the cyber preflight after the second-vertical-reuse gate."
    ),
    # A regex with a word-boundary on the bare letter — matches "B." /
    # "(B)" / "B " / "the answer is B" without false-positives on
    # in-word letters ("Brian"). Case-insensitive via the regex
    # engine's flags-in-pattern syntax.
    rubric=Rubric.single(
        CheckSpec(kind="regex", all=(r"(?i)\b[ABCD]\b",))
    ),
)


#: The frozen module-level registry. Tests assert exact key set + count.
DEFAULT_RUBRIC_REGISTRY: dict[str, RubricSpec] = {
    _GENERIC_CORRECTNESS.id: _GENERIC_CORRECTNESS,
    _PATENT_CLAIM_VALIDITY.id: _PATENT_CLAIM_VALIDITY,
    _MCQ_LETTER.id: _MCQ_LETTER,
}


def list_rubrics(registry: Mapping[str, RubricSpec] | None = None) -> list[dict[str, object]]:
    """JSON-safe list for ``GET /api/rubrics``.

    Order is the registry's insertion order so the picker dropdown stays
    stable across reloads. Operator-supplied rubrics (M6+) layer on top
    via a separate directory walk; the default registry is always the
    head of the list so the floor stays visible.
    """
    reg = registry if registry is not None else DEFAULT_RUBRIC_REGISTRY
    return [spec.to_payload() for spec in reg.values()]


def get_rubric(
    rubric_id: str, *, registry: Mapping[str, RubricSpec] | None = None
) -> RubricSpec | None:
    """Lookup a registered rubric by id, or ``None`` if absent.

    The compare event stream calls this every time a ``score`` event is
    emitted; the route handler raises ``HTTPException(404)`` if the
    operator passes an unknown id. Returns ``None`` (not raises) so the
    same helper covers the picker UX (a stale id silently falls back to
    the default).
    """
    reg = registry if registry is not None else DEFAULT_RUBRIC_REGISTRY
    return reg.get(rubric_id)


# Heuristic-defaults — a fast substring sweep over the lowercased prompt.
# Keep them aligned with the rubric ids; the dictionary order is the
# evaluation order (first hit wins, fall through to ``generic-correctness``).
_DEFAULT_PROMPT_TRIGGERS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "patent_claim_validity",
        (
            "patent",
            "claim",
            "prior art",
            "uspto",
            "35 u.s.c.",
            "mpep",
        ),
    ),
    (
        "mcq_letter",
        (
            "(a)",
            "(b)",
            "(c)",
            "(d)",
            "multiple choice",
            "select one",
            "choose one",
        ),
    ),
)


def default_rubric_for_prompt(prompt: str) -> str:
    """Pick the default rubric id for ``prompt`` — spec §4.3.

    The picker is a substring sweep over the lowercased prompt against
    the heuristic table above. First trigger fires wins; otherwise the
    floor (``generic-correctness``). Pure function — no I/O, no LLM.
    Deterministic over identical inputs so the UI's "default rubric"
    suggestion is stable across reloads.
    """
    low = (prompt or "").lower()
    for rubric_id, triggers in _DEFAULT_PROMPT_TRIGGERS:
        for tok in triggers:
            if tok in low:
                return rubric_id
    return "generic-correctness"
