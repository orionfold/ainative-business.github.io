# Copyright 2026 Manav Sehgal
# SPDX-License-Identifier: Apache-2.0
"""Reasoning-preservation probe — lifted from `scripts/probe_reasoning.py`.

Phase D of the v0.5 `fieldkit.training` build-out. Pure-python by default;
`ReasoningProbe.run()` lazy-imports torch + transformers (+ optional peft)
only when called without a `generator` injection. Three primary classes
plus two helpers and a default-thresholds constant:

- `ProbeQuestion` — input record (qid, category, question + optional
  source/license/metadata). Built by `ReasoningProbe.from_jsonl`.
- `ProbeRow` — single response result with parsed think block.
- `ProbeReport` — bag of `ProbeRow` with `model`, `max_new_tokens`,
  `lora_path`, `step`, plus `overall` / `by_category` / `with_budget(cap)`
  / `compare(other, normalize_budget=True)` / `to_json` / `from_json`.
- `ReasoningProbe` — orchestrator. `from_jsonl(path)` loads a probe set;
  `run(model_id, *, lora_path=None, generator=None, ...)` returns a
  `ProbeReport`. The `generator` injection is the test seam (and a
  legitimate prod knob for callers that already have a model loaded).
- `parse_think(response)` — picks the longest `<think>...</think>` pair
  in a response. R1-distill models occasionally false-start with an
  empty `<think></think>` block before the real one — non-greedy regex
  alone would undercount. (Caught on smoke-step-200 row 14 in the
  patent-strategist v1 lineage.)
- `summarize_rows(rows)` — pure-python aggregator. Re-runnable after
  any filter so callers can build their own subset summaries.

The JSON shape on disk matches what `scripts/probe_reasoning.py`
already emits (probes/baseline.json, probes/patent-strategist-v3-*.json):

  {
    "model": ..., "lora_path": ..., "step": ..., "n_probe": N,
    "max_new_tokens": ..., "temperature": ...,
    "overall": {...}, "by_category": {...},
    "raw_responses": [...], "wall_seconds": ...,
  }

`ProbeReport.from_json` reads that shape directly; `to_json` writes it.
The legacy `think_quality_score` key (LLM-judge coherence 0-5) is
silently ignored on load and never written — quality scoring is owned
by an in-CC-session orchestrator skill per
`[[feedback_llm_skill_pattern]]`, not by this module.

The `compare(other, normalize_budget=True)` knob handles the case the
NeMo-vs-Unsloth bakeoff hit on 2026-05-21: lanes ran at different
`max_new_tokens` (NeMo 2048, Unsloth 1536). With normalization on, any
qid whose think_n_tok exceeds the smaller cap in either report is
excluded from BOTH before the per-metric ratios are recomputed —
apples-to-apples, with the excluded qids surfaced on the result so the
caller can footnote them.
"""
from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Optional, Sequence


__all__ = [
    "CompareResult",
    "CompareRow",
    "CompareThresholds",
    "DEFAULT_COMPARE_THRESHOLDS",
    "ProbeError",
    "ProbeQuestion",
    "ProbeReport",
    "ProbeRow",
    "ProbeSummary",
    "ReasoningProbe",
    "THINK_REGEX",
    "parse_think",
    "summarize_rows",
]


THINK_REGEX: re.Pattern[str] = re.compile(r"<think>(.*?)</think>", re.DOTALL)
"""Compiled regex for picking out `<think>...</think>` blocks. Non-greedy
so multiple blocks are returned as separate matches; the longest is
chosen by `parse_think`. Exposed because some callers re-parse cached
responses without going through `parse_think` (e.g. for the LLM-judge
sidecar described in `[[feedback_llm_skill_pattern]]`)."""


class ProbeError(RuntimeError):
    """Raised by `ReasoningProbe.run()` / `ProbeReport.from_json` on
    malformed input (bad probe-set JSONL, missing fields in a saved
    report, etc). Distinct from `ValueError` so callers can selectively
    catch probe-layer failures."""


# ---------------------------------------------------------------------------
# Data classes — frozen, pure-python, JSON-friendly.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ProbeQuestion:
    """One row of a reasoning probe set.

    `source`, `license`, and `metadata` are optional pass-throughs lifted
    from the probe-set JSONL — kept on the dataclass so a probe artifact
    written by this module is round-trippable through provenance audits.
    """

    qid: str
    category: str
    question: str
    source: Optional[str] = None
    license: Optional[str] = None
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ProbeRow:
    """One per-question result. `think_n_tok` is None when has_think is
    False (no block to count); ~`len(think_text) // 4` otherwise per the
    same fast-and-rough char-quarter heuristic the standalone runner
    uses."""

    qid: str
    category: str
    response: str
    has_think: bool
    think_n_tok: Optional[int]
    think_text: str
    wall_seconds: float = 0.0


@dataclass(frozen=True)
class ProbeSummary:
    """Aggregate over a (sub)set of `ProbeRow`. `think_presence_rate` is
    computed over the full input; `think_token_length` averages
    only over rows with `has_think=True` (matches the standalone runner's
    `summarize()`)."""

    think_presence_rate: float
    think_token_length: float
    n: int


@dataclass(frozen=True)
class CompareThresholds:
    """Per-metric pass-ratio thresholds — current/baseline must be >=
    the value to PASS. Defaults match spec §4 Layer 5 of the
    patent-strategist v1 fine-tune plan (0.90 presence, 0.75 chain
    length); third metric (`think_quality_score` ≥ 0.80) is intentionally
    not surfaced here — see module docstring."""

    think_presence_rate: float = 0.90
    think_token_length: float = 0.75


DEFAULT_COMPARE_THRESHOLDS: CompareThresholds = CompareThresholds()
"""Spec §4 Layer 5 defaults — see `CompareThresholds`."""


@dataclass(frozen=True)
class CompareRow:
    """Per-metric compare detail. `status` is one of `"PASS"`, `"FAIL"`,
    or `"skip"`; the last is emitted when baseline is None or 0 (ratio
    undefined)."""

    metric: str
    baseline: Optional[float]
    current: Optional[float]
    ratio: Optional[float]
    threshold: float
    status: str


@dataclass(frozen=True)
class CompareResult:
    """Output of `ProbeReport.compare()`.

    `budget_normalized=True` means the comparator clamped both inputs
    via `with_budget(min(self.max_new_tokens, other.max_new_tokens))`
    before computing per-metric ratios; `budget_cap` is the cap used
    and `excluded_qids` is the union of qids dropped from both reports.
    `per_category` is a category → {baseline_presence, current_presence}
    breakdown for an at-a-glance read.
    """

    rows: tuple[CompareRow, ...]
    all_pass: bool
    baseline_label: str
    current_label: str
    budget_normalized: bool
    budget_cap: Optional[int]
    excluded_qids: tuple[str, ...]
    per_category: Mapping[str, Mapping[str, Optional[float]]]


# ---------------------------------------------------------------------------
# Pure helpers.
# ---------------------------------------------------------------------------


def parse_think(response: str) -> tuple[bool, Optional[int], str]:
    """Return ``(has_think_block, n_tokens_in_block_approx, think_text)``.

    Picks the longest pair when multiple ``<think>...</think>`` blocks
    are present — R1-distill models occasionally false-start with an
    empty ``<think></think>`` before opening a real one. The non-greedy
    regex would match the empty pair first and undercount the real
    chain (caught on smoke-step-200 row 14 of the patent-strategist v1
    lineage). Length heuristic is char-quarter approximation; close
    enough for the presence/length-ratio thresholds the spec checks
    against, and zero per-question detokenizer cost.
    """
    matches = THINK_REGEX.findall(response)
    if not matches:
        return False, None, ""
    think_text = max(matches, key=len).strip()
    if not think_text:
        return True, 0, ""
    return True, max(1, len(think_text) // 4), think_text


def summarize_rows(rows: Sequence[ProbeRow]) -> ProbeSummary:
    """Aggregate a sequence of rows into a `ProbeSummary`.

    Empty input → zeros (n=0). `think_token_length` divides by the
    number of has_think=True rows (not the full row count) — matches the
    standalone runner's semantics so direct JSON round-trips with
    existing artifacts produce identical numbers.
    """
    if not rows:
        return ProbeSummary(0.0, 0.0, 0)
    has = [r for r in rows if r.has_think]
    presence = len(has) / len(rows)
    if has:
        mean_len = sum((r.think_n_tok or 0) for r in has) / len(has)
    else:
        mean_len = 0.0
    return ProbeSummary(
        think_presence_rate=round(presence, 4),
        think_token_length=round(mean_len, 1),
        n=len(rows),
    )


# ---------------------------------------------------------------------------
# ProbeReport — main container.
# ---------------------------------------------------------------------------


class ProbeReport:
    """A reasoning-preservation probe run, hydrated from rows + run-metadata.

    Construct directly with the canonical keyword args, or load via
    `ProbeReport.from_json(path)` against any artifact written by
    `ReasoningProbe.run()` or the standalone `scripts/probe_reasoning.py`.

    Properties:

    - `overall` — `ProbeSummary` over all rows.
    - `by_category` — dict of category → `ProbeSummary`.

    Methods:

    - `with_budget(cap)` — return a new report excluding rows whose
      `think_n_tok` exceeds `cap`. The new `max_new_tokens` is set to
      `min(self.max_new_tokens, cap)`. Rows with `has_think=False` are
      preserved (the cap doesn't change their state).
    - `compare(other, *, normalize_budget=True, thresholds=None,
      baseline_label=None, current_label=None)` — compute per-metric
      pass/fail ratios against another report.
    - `to_json(path)` — serialize to disk in the canonical JSON shape.
    """

    __slots__ = (
        "_model",
        "_lora_path",
        "_step",
        "_max_new_tokens",
        "_temperature",
        "_rows",
        "_wall_seconds",
        "_excluded_qids",
    )

    def __init__(
        self,
        *,
        model: str,
        rows: Sequence[ProbeRow],
        max_new_tokens: int,
        temperature: float = 0.6,
        lora_path: Optional[str] = None,
        step: Optional[int] = None,
        wall_seconds: float = 0.0,
        excluded_qids: Sequence[str] = (),
    ) -> None:
        if max_new_tokens <= 0:
            raise ProbeError(
                f"max_new_tokens must be > 0 (got {max_new_tokens})"
            )
        self._model = str(model)
        self._lora_path = lora_path
        self._step = step
        self._max_new_tokens = int(max_new_tokens)
        self._temperature = float(temperature)
        self._rows = tuple(rows)
        self._wall_seconds = float(wall_seconds)
        self._excluded_qids = tuple(excluded_qids)

    # --- read-only attributes -------------------------------------------------

    @property
    def model(self) -> str:
        return self._model

    @property
    def lora_path(self) -> Optional[str]:
        return self._lora_path

    @property
    def step(self) -> Optional[int]:
        return self._step

    @property
    def max_new_tokens(self) -> int:
        return self._max_new_tokens

    @property
    def temperature(self) -> float:
        return self._temperature

    @property
    def rows(self) -> tuple[ProbeRow, ...]:
        return self._rows

    @property
    def wall_seconds(self) -> float:
        return self._wall_seconds

    @property
    def excluded_qids(self) -> tuple[str, ...]:
        """qids dropped by a prior `with_budget(cap)` call. Empty for
        a freshly-run report."""
        return self._excluded_qids

    @property
    def n(self) -> int:
        return len(self._rows)

    # --- aggregates -----------------------------------------------------------

    @property
    def overall(self) -> ProbeSummary:
        return summarize_rows(self._rows)

    @property
    def by_category(self) -> dict[str, ProbeSummary]:
        """Category → `ProbeSummary`. Categories are returned in the
        order they first appear in `rows` for deterministic output;
        callers that want alphabetical can sort the dict themselves."""
        out: dict[str, list[ProbeRow]] = {}
        for r in self._rows:
            out.setdefault(r.category, []).append(r)
        return {cat: summarize_rows(rs) for cat, rs in out.items()}

    # --- transformations ------------------------------------------------------

    def with_budget(self, cap: int) -> ProbeReport:
        """Return a new report excluding rows where ``has_think and
        think_n_tok > cap``. Rows with ``has_think=False`` are
        preserved unchanged — the cap doesn't change whether a
        truncated response had a chain to begin with.

        ``max_new_tokens`` of the new report is set to ``min(self.max_new_tokens,
        cap)``. The dropped qids are appended to ``excluded_qids`` so
        successive ``with_budget`` calls compose without losing history.
        """
        if cap <= 0:
            raise ProbeError(f"cap must be > 0 (got {cap})")
        kept: list[ProbeRow] = []
        dropped: list[str] = list(self._excluded_qids)
        for r in self._rows:
            if r.has_think and (r.think_n_tok or 0) > cap:
                dropped.append(r.qid)
                continue
            kept.append(r)
        return ProbeReport(
            model=self._model,
            rows=kept,
            max_new_tokens=min(self._max_new_tokens, cap),
            temperature=self._temperature,
            lora_path=self._lora_path,
            step=self._step,
            wall_seconds=self._wall_seconds,
            excluded_qids=dropped,
        )

    # --- compare --------------------------------------------------------------

    def compare(
        self,
        other: ProbeReport,
        *,
        normalize_budget: bool = True,
        thresholds: Optional[CompareThresholds] = None,
        baseline_label: Optional[str] = None,
        current_label: Optional[str] = None,
    ) -> CompareResult:
        """Compare this report (treated as **current**) against ``other``
        (treated as **baseline**).

        With ``normalize_budget=True`` (the default), if the two reports
        ran at different ``max_new_tokens`` the comparator first calls
        ``with_budget(min(self.max_new_tokens, other.max_new_tokens))``
        on both. Any qid whose ``think_n_tok`` exceeds the cap in
        EITHER report drives exclusion from BOTH; the excluded qids are
        returned on `CompareResult.excluded_qids` so the caller can
        footnote them. With ``normalize_budget=False``, the raw
        aggregates are compared regardless of budget difference.

        Thresholds default to `DEFAULT_COMPARE_THRESHOLDS`. Pass a
        custom `CompareThresholds` for stricter or looser per-metric
        bars. The result's ``all_pass`` is True iff every PASS-eligible
        metric (i.e. not 'skip') is PASS.

        ``baseline_label`` / ``current_label`` default to the model
        ids; pass overrides for prettier compare output (e.g. lane
        names: ``"unsloth"`` vs ``"nemo"``).
        """
        if thresholds is None:
            thresholds = DEFAULT_COMPARE_THRESHOLDS

        baseline = other
        current = self
        budget_cap: Optional[int] = None
        excluded: tuple[str, ...] = ()

        if normalize_budget and baseline.max_new_tokens != current.max_new_tokens:
            cap = min(baseline.max_new_tokens, current.max_new_tokens)
            # Union of qids that would be dropped from either side.
            drop_qids = set()
            for r in baseline._rows:
                if r.has_think and (r.think_n_tok or 0) > cap:
                    drop_qids.add(r.qid)
            for r in current._rows:
                if r.has_think and (r.think_n_tok or 0) > cap:
                    drop_qids.add(r.qid)

            def _filter(rep: ProbeReport) -> ProbeReport:
                kept = [r for r in rep._rows if r.qid not in drop_qids]
                return ProbeReport(
                    model=rep._model,
                    rows=kept,
                    max_new_tokens=cap,
                    temperature=rep._temperature,
                    lora_path=rep._lora_path,
                    step=rep._step,
                    wall_seconds=rep._wall_seconds,
                    excluded_qids=tuple(rep._excluded_qids) + tuple(sorted(drop_qids)),
                )

            baseline = _filter(baseline)
            current = _filter(current)
            budget_cap = cap
            excluded = tuple(sorted(drop_qids))
            budget_normalized = True
        else:
            budget_normalized = False

        b_overall = baseline.overall
        c_overall = current.overall

        rows: list[CompareRow] = []
        all_pass = True
        for metric, threshold in (
            ("think_presence_rate", thresholds.think_presence_rate),
            ("think_token_length", thresholds.think_token_length),
        ):
            b_val = getattr(b_overall, metric)
            c_val = getattr(c_overall, metric)
            status, ratio = _check_ratio(b_val, c_val, threshold)
            if status == "FAIL":
                all_pass = False
            rows.append(
                CompareRow(
                    metric=metric,
                    baseline=b_val,
                    current=c_val,
                    ratio=ratio,
                    threshold=threshold,
                    status=status,
                )
            )

        b_by_cat = baseline.by_category
        c_by_cat = current.by_category
        per_cat: dict[str, dict[str, Optional[float]]] = {}
        for cat in sorted(set(b_by_cat) | set(c_by_cat)):
            per_cat[cat] = {
                "baseline_presence": b_by_cat.get(cat, ProbeSummary(0.0, 0.0, 0)).think_presence_rate
                if cat in b_by_cat
                else None,
                "current_presence": c_by_cat.get(cat, ProbeSummary(0.0, 0.0, 0)).think_presence_rate
                if cat in c_by_cat
                else None,
            }

        return CompareResult(
            rows=tuple(rows),
            all_pass=all_pass,
            baseline_label=baseline_label or baseline._model,
            current_label=current_label or current._model,
            budget_normalized=budget_normalized,
            budget_cap=budget_cap,
            excluded_qids=excluded,
            per_category=per_cat,
        )

    # --- serialization --------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-shaped dict matching what `scripts/probe_reasoning.py`
        emits. Useful for tests + callers that want to inspect the shape
        without round-tripping through disk."""
        overall = self.overall
        by_cat = {
            cat: {
                "think_presence_rate": s.think_presence_rate,
                "think_token_length": s.think_token_length,
                "n": s.n,
            }
            for cat, s in self.by_category.items()
        }
        return {
            "model": self._model,
            "lora_path": self._lora_path,
            "step": self._step,
            "n_probe": len(self._rows),
            "max_new_tokens": self._max_new_tokens,
            "temperature": self._temperature,
            "overall": {
                "think_presence_rate": overall.think_presence_rate,
                "think_token_length": overall.think_token_length,
                "n": overall.n,
            },
            "by_category": by_cat,
            "raw_responses": [
                {
                    "qid": r.qid,
                    "category": r.category,
                    "response": r.response,
                    "has_think": r.has_think,
                    "think_n_tok": r.think_n_tok,
                    "think_text": r.think_text,
                    "wall_seconds": r.wall_seconds,
                }
                for r in self._rows
            ],
            "excluded_qids": list(self._excluded_qids),
            "wall_seconds": self._wall_seconds,
        }

    def to_json(self, path: str | Path, *, indent: int = 2) -> Path:
        """Write the canonical JSON shape to disk and return the Path."""
        out = Path(path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(self.to_dict(), indent=indent), encoding="utf-8")
        return out

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> ProbeReport:
        """Hydrate from a dict matching the canonical JSON shape.

        `raw_responses` is the source of truth — `overall` / `by_category`
        in the input are silently ignored on load (they'd be recomputed
        from rows). Tolerant of the legacy `think_quality_score` key
        being present and set to None; just ignores it.
        """
        try:
            raw = data["raw_responses"]
        except KeyError as exc:
            raise ProbeError(
                "ProbeReport JSON missing required key 'raw_responses'"
            ) from exc
        rows = []
        for i, r in enumerate(raw):
            try:
                rows.append(
                    ProbeRow(
                        qid=r["qid"],
                        category=r["category"],
                        response=r["response"],
                        has_think=bool(r["has_think"]),
                        think_n_tok=r.get("think_n_tok"),
                        think_text=r.get("think_text", ""),
                        wall_seconds=float(r.get("wall_seconds", 0.0)),
                    )
                )
            except KeyError as exc:
                raise ProbeError(
                    f"ProbeReport row {i} missing required key {exc!s}"
                ) from exc
        return cls(
            model=data.get("model", "unknown"),
            rows=rows,
            max_new_tokens=int(data.get("max_new_tokens", 1024)),
            temperature=float(data.get("temperature", 0.6)),
            lora_path=data.get("lora_path"),
            step=data.get("step"),
            wall_seconds=float(data.get("wall_seconds", 0.0)),
            excluded_qids=tuple(data.get("excluded_qids") or ()),
        )

    @classmethod
    def from_json(cls, path: str | Path) -> ProbeReport:
        """Load a report JSON from disk."""
        p = Path(path)
        if not p.is_file():
            raise ProbeError(f"ProbeReport JSON not found at {p}")
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ProbeError(f"ProbeReport JSON at {p} is not valid JSON: {exc}") from exc
        return cls.from_dict(data)

    # --- repr -----------------------------------------------------------------

    def __repr__(self) -> str:
        lora = f", lora={self._lora_path!r}" if self._lora_path else ""
        step = f", step={self._step}" if self._step is not None else ""
        return (
            f"ProbeReport(model={self._model!r}{lora}{step}, "
            f"n={len(self._rows)}, max_new_tokens={self._max_new_tokens})"
        )


def _check_ratio(
    baseline: Optional[float],
    current: Optional[float],
    threshold: float,
) -> tuple[str, Optional[float]]:
    """Compute pass/fail for ``current / baseline`` against ``threshold``.

    Returns ``("PASS"|"FAIL"|"skip", ratio_or_None)``. Skip when baseline
    is None or 0 (ratio undefined); the metric is then excluded from
    the all_pass tally."""
    if baseline is None or current is None:
        return "skip", None
    if baseline == 0:
        return "skip", None
    ratio = current / baseline
    return ("PASS" if ratio >= threshold else "FAIL"), ratio


# ---------------------------------------------------------------------------
# ReasoningProbe — orchestrator.
# ---------------------------------------------------------------------------


def _default_generator(
    model_id: str,
    lora_path: Optional[str],
    max_new_tokens: int,
    temperature: float,
) -> Callable[[ProbeQuestion], str]:
    """Build a real torch + transformers generate() callable.

    Lazy-imports torch, transformers, and (when ``lora_path`` is set)
    peft. Raises ImportError with a clear pointer if any aren't
    installed in the current environment. Mirrors the script-side
    behavior in `scripts/probe_reasoning.py` — bf16 on cuda:0,
    `attn_implementation="sdpa"`, R1-recommended `temperature=0.6` /
    `top_p=0.95`.
    """
    try:
        import torch
    except ImportError as exc:
        raise ImportError(
            "fieldkit.training.probe.ReasoningProbe.run() requires torch. "
            "Install it in your probe environment, or pass a `generator` "
            "callable (test seam) to skip the real model load."
        ) from exc
    try:
        from transformers import AutoModelForCausalLM, AutoTokenizer
    except ImportError as exc:
        raise ImportError(
            "fieldkit.training.probe.ReasoningProbe.run() requires "
            "`transformers`. Install it in your probe environment, or "
            "pass a `generator` callable."
        ) from exc

    tok = AutoTokenizer.from_pretrained(model_id, trust_remote_code=True)
    if tok.pad_token is None:
        tok.pad_token = tok.eos_token

    model = AutoModelForCausalLM.from_pretrained(
        model_id,
        dtype=torch.bfloat16,
        device_map="cuda:0",
        attn_implementation="sdpa",
        trust_remote_code=True,
    )

    if lora_path:
        try:
            from peft import PeftModel
        except ImportError as exc:
            raise ImportError(
                "fieldkit.training.probe.ReasoningProbe.run(lora_path=...) "
                "requires `peft`. Install it or omit `lora_path`."
            ) from exc
        model = PeftModel.from_pretrained(model, lora_path)

    model.eval()

    def _generate(q: ProbeQuestion) -> str:
        messages = [{"role": "user", "content": q.question}]
        prompt = tok.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=True
        )
        enc = tok(prompt, return_tensors="pt").to(model.device)
        with torch.no_grad():
            out = model.generate(
                **enc,
                max_new_tokens=max_new_tokens,
                temperature=temperature,
                do_sample=True,
                top_p=0.95,
                pad_token_id=tok.pad_token_id,
            )
        gen_ids = out[0, enc["input_ids"].shape[1]:]
        return tok.decode(gen_ids, skip_special_tokens=False)

    return _generate


class ReasoningProbe:
    """Reasoning-preservation probe orchestrator.

    Construct from a sequence of `ProbeQuestion`, then call
    `run(model_id, ...)` to generate a `ProbeReport`. For tests +
    callers with an already-loaded model, pass a ``generator`` callable
    of signature ``fn(question: ProbeQuestion) -> str`` to bypass the
    default torch + transformers load entirely.

    Usage::

        from fieldkit.training import ReasoningProbe

        probe = ReasoningProbe.from_jsonl("probes/reasoning-preservation-20q.jsonl")
        report = probe.run(
            model_id="deepseek-ai/DeepSeek-R1-0528-Qwen3-8B",
            lora_path="/work/runs/checkpoint-200",
            step=200,
            max_new_tokens=1024,
        )
        report.to_json("probes/smoke-step200.json")

        baseline = ProbeReport.from_json("probes/baseline.json")
        result = report.compare(baseline)
        if not result.all_pass:
            print("revert to last-good checkpoint")
    """

    __slots__ = ("_questions",)

    def __init__(self, questions: Sequence[ProbeQuestion]) -> None:
        if not questions:
            raise ProbeError("ReasoningProbe requires at least one question")
        self._questions = tuple(questions)

    @property
    def questions(self) -> tuple[ProbeQuestion, ...]:
        return self._questions

    def __len__(self) -> int:
        return len(self._questions)

    @classmethod
    def from_jsonl(cls, path: str | Path) -> ReasoningProbe:
        """Load a probe set from JSONL — one ``ProbeQuestion`` per line.

        Required per-line keys: ``qid``, ``category``, ``question``.
        Optional pass-throughs: ``source``, ``license``, plus any extra
        keys gathered under ``metadata``. Raises ``ProbeError`` on
        malformed input or missing required keys.
        """
        p = Path(path)
        if not p.is_file():
            raise ProbeError(f"probe-set JSONL not found at {p}")
        questions: list[ProbeQuestion] = []
        for ln, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ProbeError(
                    f"probe-set JSONL {p} line {ln} not valid JSON: {exc}"
                ) from exc
            try:
                qid = row.pop("qid")
                category = row.pop("category")
                question = row.pop("question")
            except KeyError as exc:
                raise ProbeError(
                    f"probe-set JSONL {p} line {ln} missing required key {exc!s}"
                ) from exc
            source = row.pop("source", None)
            license_ = row.pop("license", None)
            questions.append(
                ProbeQuestion(
                    qid=qid,
                    category=category,
                    question=question,
                    source=source,
                    license=license_,
                    metadata=row,
                )
            )
        if not questions:
            raise ProbeError(f"probe-set JSONL {p} contained no rows")
        return cls(questions)

    def run(
        self,
        model_id: str,
        *,
        lora_path: Optional[str | Path] = None,
        step: Optional[int] = None,
        max_new_tokens: int = 1024,
        temperature: float = 0.6,
        generator: Optional[Callable[[ProbeQuestion], str]] = None,
        on_progress: Optional[Callable[[int, int, "ProbeRow"], None]] = None,
    ) -> ProbeReport:
        """Run the probe set and return a `ProbeReport`.

        Parameters:
            model_id: HF id or local path of the base model. Passed
                through to the default generator; ignored if a
                ``generator`` is supplied.
            lora_path: Optional peft adapter directory. When set, the
                default generator stacks a peft `PeftModel` on top of
                the base.
            step: Training-step number to record on the report (for
                checkpoint probes). Pure metadata; nothing computes
                with it.
            max_new_tokens: Generation cap. Per
                `[[feedback_reasoning_model_npredict]]`, values below
                1024 truncate `<think>` blocks before the answer
                token lands. Default 1024; bump to 1536/2048 for
                long-chain probe sets.
            temperature: Sampling temperature. Default 0.6 — the
                R1-distill family's recommended value.
            generator: Optional pre-built ``fn(ProbeQuestion) -> str``.
                When provided, skips the default torch + transformers
                load entirely. Used by tests + by callers driving the
                probe from a pre-loaded model.
            on_progress: Optional ``fn(i, total, row)`` invoked after
                each question. ``i`` is 1-based.
        """
        if max_new_tokens <= 0:
            raise ProbeError(
                f"max_new_tokens must be > 0 (got {max_new_tokens})"
            )

        gen = generator
        if gen is None:
            gen = _default_generator(
                model_id=model_id,
                lora_path=str(lora_path) if lora_path is not None else None,
                max_new_tokens=max_new_tokens,
                temperature=temperature,
            )

        rows: list[ProbeRow] = []
        t_start = time.monotonic()
        total = len(self._questions)
        for i, q in enumerate(self._questions, 1):
            t0 = time.monotonic()
            response = gen(q)
            has_think, n_tok, think_text = parse_think(response)
            row = ProbeRow(
                qid=q.qid,
                category=q.category,
                response=response,
                has_think=has_think,
                think_n_tok=n_tok,
                think_text=think_text,
                wall_seconds=round(time.monotonic() - t0, 2),
            )
            rows.append(row)
            if on_progress is not None:
                on_progress(i, total, row)

        return ProbeReport(
            model=model_id,
            rows=rows,
            max_new_tokens=max_new_tokens,
            temperature=temperature,
            lora_path=str(lora_path) if lora_path is not None else None,
            step=step,
            wall_seconds=round(time.monotonic() - t_start, 1),
        )
