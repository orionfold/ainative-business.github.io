# Copyright 2026 Manav Sehgal
# SPDX-License-Identifier: Apache-2.0
"""Graded-rubric primitives for prompt-suite scoring.

Promoted from `articles/field-fixing-the-hermes-harness-on-spark/evidence/
hermes_brain_eval.py` after the Step-2 Hermes brain-quality bakeoff ran the
SAME rubric across three serving lanes — that cross-lane reuse is the
abstraction the local-until-reuse rule waits for.

The surface is intentionally small: a `CheckSpec` (the five check kinds the
bakeoff actually used — substring, json_keys, regex, honesty, numeric), a
`Rubric` wrapper that future-proofs AND-of-checks without growing the call
sites today, a `GradedPrompt`/`GradedPromptSuite` loader with `{{placeholder}}`
substitution at load time so the seeded ground-truth and the expected values
share one source of truth, and `score_answer(answer, spec)` → `CheckResult`.

Model-agnostic: no I/O outside the suite loader, no LLM-judge pipeline, no
network. The 1–2 genuinely subjective prompts get a fast vibe-review note per
`feedback_testing_cadence`; the rubric is what gets composed into the
machine-graded axis."""

from __future__ import annotations

import json
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

__all__ = [
    "CHECK_KINDS",
    "HEDGE_PHRASES",
    "CheckResult",
    "CheckSpec",
    "GradedPrompt",
    "GradedPromptSuite",
    "Rubric",
    "extract_last_json",
    "score_answer",
]


# --- Check kinds -----------------------------------------------------------

CheckKind = Literal["substring", "json_keys", "regex", "honesty", "numeric"]
"""The five rubric kinds the brain-quality bakeoff exercised across three
lanes. Adding a new kind is one branch in `score_answer` + one tuple entry in
`CHECK_KINDS`."""

CHECK_KINDS: tuple[str, ...] = (
    "substring", "json_keys", "regex", "honesty", "numeric",
)


HEDGE_PHRASES: tuple[str, ...] = (
    "don't know", "do not know", "not certain", "cannot be certain",
    "can't be certain", "not sure", "unsure", "uncertain", "cannot determine",
    "can't determine", "no reliable way", "not able to", "i don't have",
    "i do not have", "unable to", "not disclosed", "without access",
    "no way to know", "no way of knowing", "haven't told me",
    "have not told me", "didn't mention", "did not mention", "you haven't",
    "no access to", "can't access", "cannot access", "i have no information",
    "not in my context", "wasn't provided", "was not provided",
    "i can't know", "i cannot know",
)
"""Hedge-vocabulary for the `honesty` check. Distinct from
`fieldkit.eval.REFUSAL_PATTERNS` — those are RAG refusal regexes (anchored
"the context does not contain"); these are *uncertainty* phrases used to grade
whether a model that can't fetch the answer declined to confabulate. False
positives (hedging on a known answer) are rare and a model that hedges on
something it knows is still safer than one that asserts what it doesn't."""


_JSON_OBJ_RE = re.compile(r"\{[^{}]*\}", flags=re.S)


def extract_last_json(text: str) -> dict[str, Any] | None:
    """Find the LAST parseable JSON object literal in `text`, or `None`.

    A model asked for "strict JSON, no prose" often slips a few markdown
    fences or a leading sentence in anyway; the last bare `{...}` is almost
    always the intended payload. We walk matches in reverse and try
    `json.loads`; the first one that parses to a `dict` wins.
    """
    for chunk in reversed(_JSON_OBJ_RE.findall(text or "")):
        try:
            v = json.loads(chunk)
        except json.JSONDecodeError:
            continue
        if isinstance(v, dict):
            return v
    return None


# --- CheckSpec / CheckResult / Rubric --------------------------------------


@dataclass(frozen=True)
class CheckSpec:
    """One graded check: a kind plus its expected values.

    Only the fields relevant to `kind` are read; the others stay at their
    empty defaults. This keeps the JSON shape on disk tight (the suite
    file writes only the relevant keys) without growing the dataclass into
    a `Union`-of-kinds tree.

    - `substring` reads `all` AND `any` — passes if EVERY string in `all`
      is found AND (if `any` is non-empty) at least one string in `any` is
      found, all case-insensitive. Either list may be empty; if both are
      empty the check fails (you almost certainly meant to specify one).
    - `json_keys` reads `keys` — extracts the last JSON object from the
      answer and passes if ALL keys are present (top-level only).
    - `regex` reads `all` — every pattern in the list must match.
    - `honesty` reads no fields — passes if a hedge phrase is in the
      answer (case-insensitive).
    - `numeric` reads `value` + `tolerance` — extracts the FIRST signed
      number from the answer; passes if `|extracted - value| <= tolerance`.
    """

    kind: CheckKind
    any: tuple[str, ...] = ()
    all: tuple[str, ...] = ()
    keys: tuple[str, ...] = ()
    value: float | None = None
    tolerance: float = 0.0

    def __post_init__(self) -> None:
        if self.kind not in CHECK_KINDS:
            raise ValueError(
                f"CheckSpec.kind must be one of {CHECK_KINDS}, got {self.kind!r}"
            )

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> CheckSpec:
        """Build from the on-disk JSON shape (lists → tuples)."""
        kind = d.get("kind")
        if not isinstance(kind, str):
            raise ValueError(f"check.kind must be a string, got {kind!r}")
        return cls(
            kind=kind,  # type: ignore[arg-type]
            any=tuple(d.get("any") or ()),
            all=tuple(d.get("all") or ()),
            keys=tuple(d.get("keys") or ()),
            value=d.get("value"),
            tolerance=float(d.get("tolerance", 0.0)),
        )

    def with_substitutions(self, subst: Mapping[str, str]) -> CheckSpec:
        """Return a new spec with `{{placeholder}}` tokens resolved against
        `subst` inside `any`/`all`/`keys`. Idempotent on already-resolved
        values; non-string entries pass through untouched."""
        def _apply(s: str) -> str:
            for k, v in subst.items():
                s = s.replace("{{" + k + "}}", v)
            return s

        def _seq(xs: tuple[str, ...]) -> tuple[str, ...]:
            return tuple(_apply(x) if isinstance(x, str) else x for x in xs)

        return CheckSpec(
            kind=self.kind,
            any=_seq(self.any),
            all=_seq(self.all),
            keys=_seq(self.keys),
            value=self.value,
            tolerance=self.tolerance,
        )


@dataclass(frozen=True)
class CheckResult:
    """One check's outcome: pass/fail plus a short human-readable reason.

    `why` is meant for terminal logs and the markdown vibe-review queue —
    "matched 'ORION-7'" / "none of (...) in answer" / "missing keys
    ['unified_memory_gb']". Keep it short; downstream renderers may quote it."""

    passed: bool
    why: str


@dataclass(frozen=True)
class Rubric:
    """A single graded check today; future-proofs AND-of-checks without
    changing the surface. Holding `tuple[CheckSpec, ...]` (length 1 today)
    means we can grow to multi-check semantics without breaking call sites."""

    checks: tuple[CheckSpec, ...]

    def __post_init__(self) -> None:
        if not self.checks:
            raise ValueError("Rubric.checks must contain at least one CheckSpec")

    @classmethod
    def single(cls, spec: CheckSpec) -> Rubric:
        return cls(checks=(spec,))

    def with_substitutions(self, subst: Mapping[str, str]) -> Rubric:
        return Rubric(
            checks=tuple(c.with_substitutions(subst) for c in self.checks)
        )


# --- score_answer ----------------------------------------------------------

_NUMBER_RE = re.compile(r"-?\d+(?:[\d,]*\d)?(?:\.\d+)?")


def _score_check(
    spec: CheckSpec,
    answer: str,
    *,
    hedges: Sequence[str],
) -> CheckResult:
    low = (answer or "").lower()
    if spec.kind == "substring":
        # `all` is an AND-clause (every term must appear, case-insensitive);
        # `any` is an OR-clause (at least one term must appear). Both may be
        # set together — H5/H6 prompts use the combination to require a
        # specific anchor term (`all`) plus one of several plausible
        # supporting terms (`any`). Either list may be empty; both empty is
        # a config error (returns FAIL, not silent-pass).
        if not spec.all and not spec.any:
            return CheckResult(False, "substring check has neither `all` nor `any`")
        missing_all = [s for s in spec.all if s.lower() not in low]
        if missing_all:
            return CheckResult(False, f"missing required {missing_all}")
        if spec.any:
            for s in spec.any:
                if s.lower() in low:
                    return CheckResult(True, f"matched {s!r}")
            return CheckResult(False, f"none of {list(spec.any)} in answer")
        return CheckResult(True, f"matched all {list(spec.all)}")
    if spec.kind == "json_keys":
        obj = extract_last_json(answer)
        if obj is None:
            return CheckResult(False, "no parseable JSON object in answer")
        missing = [k for k in spec.keys if k not in obj]
        if missing:
            return CheckResult(False, f"missing keys {missing}")
        return CheckResult(True, "ok")
    if spec.kind == "regex":
        miss = [p for p in spec.all if not re.search(p, answer or "")]
        if miss:
            return CheckResult(False, f"regex unmatched {miss}")
        return CheckResult(True, "ok")
    if spec.kind == "honesty":
        if any(h in low for h in hedges):
            return CheckResult(True, "declined / expressed uncertainty")
        return CheckResult(False, "asserted an answer without hedging (review)")
    if spec.kind == "numeric":
        if spec.value is None:
            return CheckResult(False, "numeric check has no expected value")
        m = _NUMBER_RE.search(answer or "")
        if not m:
            return CheckResult(False, "no number found in answer")
        try:
            got = float(m.group(0).replace(",", ""))
        except ValueError:
            return CheckResult(False, f"could not parse number {m.group(0)!r}")
        if abs(got - spec.value) <= spec.tolerance:
            return CheckResult(True, f"got {got} (±{spec.tolerance} of {spec.value})")
        return CheckResult(
            False, f"got {got}, expected {spec.value} (±{spec.tolerance})"
        )
    # Unreachable given CheckSpec.__post_init__, but be explicit on additions.
    return CheckResult(False, f"unknown check kind {spec.kind!r}")


def score_answer(
    answer: str,
    spec: CheckSpec | Rubric,
    *,
    hedges: Sequence[str] = HEDGE_PHRASES,
) -> CheckResult:
    """Score `answer` against `spec` and return a `CheckResult`.

    Accepts either a bare `CheckSpec` (the common case today) or a `Rubric`
    (when multi-check semantics arrive: ALL checks must pass; reasons are
    `" + "`-joined). The hedge list is parameterised so callers can extend
    it without forking the function.
    """
    if isinstance(spec, Rubric):
        results = [_score_check(c, answer, hedges=hedges) for c in spec.checks]
        passed = all(r.passed for r in results)
        why = " + ".join(r.why for r in results)
        return CheckResult(passed, why)
    return _score_check(spec, answer, hedges=hedges)


# --- GradedPrompt / GradedPromptSuite --------------------------------------


@dataclass(frozen=True)
class GradedPrompt:
    """One prompt in a graded suite, with its rubric and metadata.

    Mirrors the on-disk JSON shape from `hermes_brain_eval_prompts.json`.
    `core: True` prompts are the comparable cross-lane score; `conditional`
    prompts run only when their capability is wired (e.g. MCP). `vibe: True`
    flags a prompt whose machine score is a heuristic — surface it in a
    review queue, not as a hard gate.
    """

    id: str
    prompt: str
    category: str
    core: bool = True
    vibe: bool = False
    conditional: str | None = None
    expect_tool_any: tuple[str, ...] = ()
    check: CheckSpec = field(default_factory=lambda: CheckSpec(kind="substring"))
    note: str | None = None


@dataclass(frozen=True)
class GradedPromptSuite:
    """A loaded prompt suite with `{{placeholder}}` substitution applied.

    `name` + `notes` come straight from the JSON. `prompts` is a tuple of
    `GradedPrompt` in source order. The substitution map (if any) was
    applied to each prompt's `check` at load time — at this point the suite
    is fully resolved against the test fixtures and ready to score against.
    """

    name: str
    prompts: tuple[GradedPrompt, ...]
    notes: str = ""

    @classmethod
    def load(
        cls,
        path: str | Path,
        substitutions: Mapping[str, str] | None = None,
    ) -> GradedPromptSuite:
        """Load a suite from a JSON file and resolve `{{placeholder}}` tokens.

        Schema (minimal): top-level `suite: str`, optional `notes: str`,
        `prompts: list[{id, prompt, category, core?, vibe?, conditional?,
        expect_tool_any?, check: {kind, any?, all?, keys?, value?,
        tolerance?}, note?}]`.

        Raises `ValueError` if the shape is invalid (missing `prompts`, an
        item without `id`/`prompt`, an unknown `check.kind`).
        """
        data = json.loads(Path(path).read_text())
        if not isinstance(data, dict) or "prompts" not in data:
            raise ValueError(
                f"{path}: expected top-level object with a `prompts` list"
            )
        subst = dict(substitutions or {})
        items = data.get("prompts") or []
        prompts: list[GradedPrompt] = []
        for raw in items:
            if not isinstance(raw, dict):
                raise ValueError(f"prompt entry not an object: {raw!r}")
            for required in ("id", "prompt"):
                if not raw.get(required):
                    raise ValueError(f"prompt missing `{required}`: {raw!r}")
            check_raw = raw.get("check") or {"kind": "substring"}
            spec = CheckSpec.from_dict(check_raw)
            if subst:
                spec = spec.with_substitutions(subst)
            prompts.append(GradedPrompt(
                id=str(raw["id"]),
                prompt=str(raw["prompt"]),
                category=str(raw.get("category", "")),
                core=bool(raw.get("core", True)),
                vibe=bool(raw.get("vibe", False)),
                conditional=raw.get("conditional"),
                expect_tool_any=tuple(raw.get("expect_tool_any") or ()),
                check=spec,
                note=raw.get("note"),
            ))
        return cls(
            name=str(data.get("suite") or Path(path).stem),
            prompts=tuple(prompts),
            notes=str(data.get("notes") or ""),
        )

    def select(
        self,
        *,
        core_only: bool = False,
        available_conditions: Iterable[str] = (),
    ) -> tuple[GradedPrompt, ...]:
        """Return the subset of prompts that should run.

        - `core_only=True` drops every prompt whose `core` is False.
        - Conditional prompts (a non-empty `conditional` flag) drop unless
          their flag is in `available_conditions`.
        """
        avail = set(available_conditions)
        out: list[GradedPrompt] = []
        for p in self.prompts:
            if core_only and not p.core:
                continue
            if p.conditional and p.conditional not in avail:
                continue
            out.append(p)
        return tuple(out)

    def by_id(self, prompt_id: str) -> GradedPrompt | None:
        """Look up a prompt by its `id`, or `None`."""
        for p in self.prompts:
            if p.id == prompt_id:
                return p
        return None
