# Copyright 2026 Manav Sehgal
# SPDX-License-Identifier: Apache-2.0
"""Vertical-domain eval-bench wrapper around `fieldkit.eval.Bench`.

`VerticalBench` is the Spark-overlay scorer for FinanceBench / LegalBench /
SemEval-style JSONL test sets. Per `ideas/mtbm-use-cases.md` §6 Pick #1.b +
§8.5.1 cross-walk, vertical-curator quants ship four measurement axes per
variant: perplexity (from `fieldkit.quant.measure_perplexity_gguf`), tok/s
(`measure_tokens_per_sec_gguf`), sustained-load minutes (`ThermalProbe`), and
**vertical-eval accuracy** — the load-bearing axis this module supplies.

The bench is intentionally callable-shaped: it accepts a `model_fn(prompt) -> str`
and times each call via the existing `Bench` harness, so latency aggregates
alongside accuracy and refusal. Network access lives in the caller (llama-cli,
NIM, vLLM, etc.), keeping the bench offline-only for unit tests.

Supported JSONL shapes (auto-detected by `VerticalBench.from_jsonl`):

- **financebench** — Patronus AI's FinanceBench schema. Maps
  ``question`` → prompt, ``answer`` (or ``gold_standard``) → reference. Pulls
  ``company``, ``doc_period``, ``question_type`` into per-row tags.
- **legalbench** — Stanford CRFM's LegalBench schema. Most tasks use
  ``text`` / ``input`` for prompt and ``answer`` / ``label`` for reference.
- **patent-strategist** — Orionfold patent-strategist-bench schema
  (`specs/patent-strategist-v1.md` §3.3). Rows carry ``family`` (A-E),
  ``use_case``, ``scoring_mode`` (closed/retrieval/oracle), ``gold_label``,
  optional ``options`` (MCQ subset), ``context`` (retrieval), and
  ``oracle_context`` (oracle). The branch handles open-book context
  prepending per ``scoring_mode`` and MCQ option-appending for rows with
  ``options``. Default scorer is ``mcq_letter`` (Family D MCQ subset);
  other families dispatch via ``PATENT_STRATEGIST_SCORERS``.
- **generic** — `{question, answer}` (or `{prompt, expected}`) JSONL. Falls
  back here when no FinanceBench / LegalBench / patent-strategist signature
  matches.

Three scorers ship in v0.4.x; callers pass any `Callable[[str, str], float]`
for custom scoring. ``exact_match`` and ``contains`` are deterministic;
``numeric_match`` extracts the first number from the prediction and compares
to the reference under a relative tolerance — the right default for
FinanceBench's quantitative questions.

**Open-book mode (v0.4.1+).** FinanceBench is an *open-book* benchmark — the
right answer is in the 10-K excerpt cited under ``evidence[*].evidence_text``.
``VerticalBench.from_jsonl(..., open_book=True)`` rewrites the
``VerticalQA.question`` to include the evidence text + a numeric-answer prompt
before the model sees it. Default is auto: ``True`` for `financebench`,
``False`` for everything else (LegalBench/generic). The 2026-05-13 V1 attempt
on AdaptLLM/finance-chat scored 0/50 closed-book and 14–18%/50 open-book on
the same JSONL — open-book is the load-bearing flag for FinanceBench scoring.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Iterable
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from fieldkit.eval import (
    Bench,
    BenchCall,
    irac_structure,
    is_refusal,
    mcq_letter,
    office_action_argument,
    patent_claim_validity,
    prior_art_relevance,
)


__all__ = [
    "PATENT_STRATEGIST_SCORERS",
    "PATENT_STRATEGIST_SCORER_FNS",
    "VerticalBench",
    "VerticalQA",
    "contains",
    "exact_match",
    "numeric_match",
]


# --- Patent-strategist scorer dispatch -----------------------------------

PATENT_STRATEGIST_SCORERS: dict[str, str] = {
    # Per `specs/patent-strategist-v1.md` §3.3. Values are scorer *names*
    # (strings) for callers that want lazy resolution or want to render the
    # dispatch into a config dump. The matching live-callable map below
    # (`PATENT_STRATEGIST_SCORER_FNS`) is the import-it-and-use surface.
    "A": "patent_claim_validity",        # generative / inventive — claim broadening/narrowing
    "B": "prior_art_relevance",          # search / analytical — Spearman ρ on ranked priors
    "C": "judge_rubric",                 # strategic / portfolio — open-ended Judge
    "D-mcq": "mcq_letter",               # procedural prosecution — MCQ subset
    "D-oa": "office_action_argument",    # procedural prosecution — office-action response
    "D-irac": "irac_structure",          # procedural prosecution — IRAC scenarios
    "E": "judge_rubric",                 # communication / education — open-ended Judge (MCQ quiz subset uses mcq_letter)
}
"""Family/use-case → scorer-name map. Callers slice the bench by family and
configure ``VerticalBench(scorer=...)`` per-slice; per-row dispatch isn't
wired into ``VerticalBench.run`` because each scorer has distinct kwargs
(rubric dict, ranking list, judge backend) that don't share a signature."""


PATENT_STRATEGIST_SCORER_FNS: dict[str, Callable[..., float]] = {
    # Live-callable companion to `PATENT_STRATEGIST_SCORERS`. The two
    # ``judge_rubric`` slots ("C", "E") aren't included here because they're
    # open-ended `Judge.grade(...)` calls parameterized by the caller's
    # chosen rubric — there isn't a single scorer fn that fits.
    "A": patent_claim_validity,
    "B": prior_art_relevance,
    "D-mcq": mcq_letter,
    "D-oa": office_action_argument,
    "D-irac": irac_structure,
}
"""Live-callable map for the four T6 scorers + the promoted `mcq_letter`.
Skips the two ``judge_rubric`` slots ("C", "E"): those are open-ended
`Judge.grade(...)` calls where the rubric is caller-chosen, not a single
named scorer fn."""


@dataclass(frozen=True, slots=True)
class VerticalQA:
    """One vertical-eval test case.

    `qid` is the row's stable id (FinanceBench `financebench_id`, etc.) so
    per-row scores can be cross-referenced against the source JSONL. `tags`
    carry per-row metadata (company, doc_period, question_type) that flow
    through to `Bench` for slice-by aggregation downstream.
    """

    qid: str
    question: str
    expected: str
    tags: dict[str, Any] = field(default_factory=dict)


# --- Scorers -------------------------------------------------------------


def exact_match(predicted: str, expected: str) -> float:
    """1.0 if `predicted.strip().lower() == expected.strip().lower()` else 0.0.

    Whitespace-insensitive and case-insensitive. The right default for
    LegalBench-style single-label classification (yes / no / hold / overrule).
    """
    return 1.0 if predicted.strip().lower() == expected.strip().lower() else 0.0


def contains(predicted: str, expected: str) -> float:
    """1.0 if `expected.strip().lower()` appears in `predicted.strip().lower()`.

    The right default when the model is asked to produce a paragraph and the
    reference is a key fact / number / phrase that must appear somewhere in
    the answer.
    """
    e = expected.strip().lower()
    if not e:
        return 0.0
    return 1.0 if e in predicted.strip().lower() else 0.0


_NUM_RE = re.compile(r"-?\d[\d,]*(?:\.\d+)?")


def numeric_match(
    predicted: str,
    expected: str,
    *,
    rel_tolerance: float = 0.01,
) -> float:
    """1.0 if the first number in `predicted` is within `rel_tolerance` of
    the first number in `expected`, else 0.0.

    Commas in numbers (`1,234.56`) are stripped before parsing. Returns 0.0 if
    either side has no parseable number — that includes refusals, so the
    refusal-rate counter elsewhere doesn't need to gate this scorer.
    The default `rel_tolerance=0.01` matches FinanceBench's quantitative-answer
    grading convention (±1%).
    """
    pn = _first_number(predicted)
    en = _first_number(expected)
    if pn is None or en is None:
        return 0.0
    if en == 0.0:
        return 1.0 if abs(pn) <= rel_tolerance else 0.0
    return 1.0 if abs(pn - en) / abs(en) <= rel_tolerance else 0.0


def _first_number(s: str) -> float | None:
    m = _NUM_RE.search(s)
    if not m:
        return None
    try:
        return float(m.group(0).replace(",", ""))
    except ValueError:
        return None


# --- JSONL loaders -------------------------------------------------------


def _detect_format(row: dict[str, Any]) -> str:
    """Auto-detect JSONL schema from the first row's field signature."""
    keys = set(row.keys())
    if "financebench_id" in keys or "gold_standard" in keys:
        return "financebench"
    if {"family", "use_case", "scoring_mode"}.issubset(keys):
        return "patent-strategist"
    if {"text", "answer"}.issubset(keys) or {"input", "label"}.issubset(keys):
        return "legalbench"
    return "generic"


def _row_to_qa(
    row: dict[str, Any],
    fmt: str,
    fallback_idx: int,
    *,
    open_book: bool = False,
) -> VerticalQA | None:
    """Map a JSONL row to `VerticalQA`. Returns None if required fields missing.

    When `open_book=True` and `fmt == "financebench"`, prepends the row's
    ``evidence[*].evidence_text`` to the question so the model sees the
    10-K excerpt the gold answer was derived from. No-op for other formats —
    LegalBench / generic JSONLs don't have a standard evidence field.
    """
    if fmt == "financebench":
        qid = str(row.get("financebench_id") or f"fb-{fallback_idx}")
        question = row.get("question") or ""
        expected = (
            row.get("gold_standard")
            or row.get("metric_eval_text")
            or row.get("answer")
            or ""
        )
        tags = {
            k: row[k]
            for k in ("company", "doc_period", "doc_type", "question_type")
            if k in row
        }
        if open_book and question:
            evidence_text = _extract_evidence_text(row)
            if evidence_text:
                doc_name = row.get("doc_name") or "the filing"
                question = (
                    f"Context from {doc_name}:\n\n"
                    f"{evidence_text}\n\n"
                    f"Question: {question}\n\n"
                    f"Answer with just the numeric value."
                )
    elif fmt == "legalbench":
        qid = str(row.get("id") or row.get("index") or f"lb-{fallback_idx}")
        question = row.get("text") or row.get("input") or row.get("question") or ""
        expected = row.get("answer") or row.get("label") or ""
        tags = {k: row[k] for k in ("task", "subtask") if k in row}
    elif fmt == "patent-strategist":
        qid = str(row.get("qid") or f"ps-{fallback_idx}")
        question = row.get("question") or ""
        expected = row.get("gold_label") or ""
        scoring_mode = row.get("scoring_mode") or "closed"
        # Open-book-style context prepending. `oracle` mode wins over
        # `retrieval` if both fields are populated — oracle is the
        # idealized-retrieval upper-bound by construction.
        ctx: str | None = None
        if scoring_mode == "oracle":
            ctx = row.get("oracle_context") or row.get("context")
        elif scoring_mode == "retrieval":
            ctx = row.get("context")
        if ctx and question:
            question = f"Context:\n\n{ctx}\n\nQuestion: {question}"
        # MCQ option-appending — Family D MCQ + Family E quiz subset.
        options = row.get("options")
        if options and isinstance(options, list) and question:
            opts_block = "\n".join(
                f"{chr(65 + i)}. {opt}" for i, opt in enumerate(options) if isinstance(opt, str)
            )
            if opts_block:
                question = f"{question}\n\nOptions:\n{opts_block}"
        tags = {
            "family": row.get("family"),
            "use_case": row.get("use_case"),
            "scoring_mode": scoring_mode,
            "reviewed": bool(row.get("reviewed", False)),
        }
        # Caller-supplied tags merge in — jurisdiction, art-unit, year-band.
        extra_tags = row.get("tags")
        if isinstance(extra_tags, dict):
            tags.update(extra_tags)
    else:
        qid = str(row.get("id") or row.get("qid") or f"q-{fallback_idx}")
        question = row.get("question") or row.get("prompt") or row.get("input") or ""
        expected = (
            row.get("answer")
            or row.get("expected")
            or row.get("gold")
            or row.get("label")
            or ""
        )
        tags = {}
    if not question or not expected:
        return None
    return VerticalQA(qid=qid, question=str(question), expected=str(expected), tags=tags)


def _extract_evidence_text(row: dict[str, Any]) -> str:
    """Flatten FinanceBench's `evidence: [{evidence_text: ...}, ...]` into a
    blank-line-joined string. Accepts either list-of-dicts (canonical shape)
    or list-of-strings (some pre-flattened dumps). Returns ``""`` when no
    evidence field is present — caller falls back to closed-book.
    """
    chunks: list[str] = []
    for e in row.get("evidence") or []:
        if isinstance(e, dict):
            txt = e.get("evidence_text") or ""
            if txt:
                chunks.append(str(txt))
        elif isinstance(e, str):
            chunks.append(e)
    return "\n\n".join(chunks)


# --- VerticalBench -------------------------------------------------------


@dataclass
class VerticalBench:
    """Wraps `Bench` to score model outputs against a vertical-eval JSONL.

    Usage::

        vb = VerticalBench.from_jsonl("financebench.jsonl", scorer=numeric_match)

        def model_fn(prompt: str) -> str:
            return llama_cli_call(gguf_path, prompt)

        bench = vb.run(model_fn, limit=50)
        print(bench.report())
        # → table with accuracy, refusal_rate, latency_ms aggregated

    The returned `Bench` carries one `BenchCall` per question with metrics
    ``accuracy`` (0.0/1.0 via the scorer) and ``refusal`` (0.0/1.0 via
    `is_refusal`). Per-row tags from the JSONL flow through to `BenchCall.tags`,
    so callers can slice by `company` / `doc_period` / `question_type`
    downstream.
    """

    name: str
    questions: list[VerticalQA]
    scorer: Callable[..., float] = exact_match
    """Pluggable. `exact_match` / `contains` / `numeric_match` ship; pass any
    `Callable[[predicted, expected], float]` for custom scoring (LLM-judge,
    BLEU, etc.). Extra kwargs to the scorer (e.g. `rel_tolerance`) go through
    `scorer_kwargs`."""
    scorer_kwargs: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_jsonl(
        cls,
        path: str | Path,
        *,
        name: str | None = None,
        format: str = "auto",
        limit: int | None = None,
        scorer: Callable[..., float] | None = None,
        scorer_kwargs: dict[str, Any] | None = None,
        open_book: bool | None = None,
        subset: str | None = None,
    ) -> VerticalBench:
        """Load a JSONL test set from disk and return a configured bench.

        `format` is one of ``"auto"`` (sniff the first row), ``"financebench"``,
        ``"legalbench"``, or ``"generic"``. The auto-sniffer reads only the
        first row, so a partially-corrupt JSONL still triggers
        format-specific behavior. Rows missing question or expected are
        silently dropped (they show up as a row-count delta vs the JSONL).

        `open_book` controls whether per-row evidence text is prepended to the
        question. Default ``None`` resolves to ``True`` for `financebench`
        (where the gold answer lives in the cited 10-K excerpt) and ``False``
        for everything else. Pass ``True`` / ``False`` to override. Currently
        only `financebench` rows have a standard evidence field; the flag is
        a no-op for the other formats.

        `subset` is a FinanceBench-only convenience filter that drops rows
        whose ``question_type`` doesn't match. Useful for scoring only the
        ``metrics-generated`` subset (quantitative questions) without
        pre-filtering the JSONL.
        """
        p = Path(path)
        questions: list[VerticalQA] = []
        fmt: str | None = None if format == "auto" else format
        with p.open() as f:
            for i, line in enumerate(f):
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if fmt is None:
                    fmt = _detect_format(row)
                # Resolve open_book on the first row once fmt is known.
                if open_book is None:
                    open_book = fmt == "financebench"
                if subset is not None and row.get("question_type") != subset:
                    continue
                qa = _row_to_qa(row, fmt, fallback_idx=i, open_book=open_book)
                if qa is not None:
                    questions.append(qa)
                if limit is not None and len(questions) >= limit:
                    break
        # If the file was empty, open_book may still be None — collapse to False.
        if open_book is None:
            open_book = False
        # Pick a sensible default scorer per format if caller didn't override.
        # patent-strategist defaults to `mcq_letter` because the Family D MCQ
        # subset is the largest single sub-population (~40 of 200 Qs per spec
        # §5.1) — callers slicing other families pass the right scorer
        # explicitly (see ``PATENT_STRATEGIST_SCORERS``).
        if scorer is None:
            if fmt == "financebench":
                scorer = numeric_match
            elif fmt == "patent-strategist":
                scorer = mcq_letter
            else:
                scorer = exact_match
        return cls(
            name=name or p.stem,
            questions=questions,
            scorer=scorer,
            scorer_kwargs=scorer_kwargs or {},
        )

    def run(
        self,
        model_fn: Callable[[str], str],
        *,
        limit: int | None = None,
        on_error: str = "record",
        extra_tags: dict[str, Any] | None = None,
    ) -> Bench:
        """Run `model_fn(question.question)` per question; score against `expected`.

        Returns the underlying `Bench` so callers can `.summary()` /
        `.report()` / `.dump()` it through the existing reporting pipeline.
        Each call's `BenchCall.metrics` carries ``accuracy`` and ``refusal``;
        per-row metadata (company, doc_period, etc.) lands in `BenchCall.tags`
        alongside any `extra_tags` the caller supplies (e.g. the gguf variant
        being scored — useful when the caller does `for variant in variants:`).
        """
        import time

        if on_error not in ("record", "raise"):
            raise ValueError(f"on_error must be 'record' or 'raise', got {on_error!r}")

        bench = Bench(self.name, metrics=["accuracy", "refusal"])
        items = self.questions if limit is None else self.questions[:limit]
        takes_kwargs = _accepts_kwargs(self.scorer)
        with bench:
            for q in items:
                tags = {"qid": q.qid, **q.tags, **(extra_tags or {})}
                t0 = time.perf_counter()
                try:
                    out = model_fn(q.question)
                except Exception as exc:
                    if on_error == "raise":
                        raise
                    latency_ms = round((time.perf_counter() - t0) * 1000.0, 2)
                    bench.record(
                        input=q.question,
                        output=None,
                        latency_ms=latency_ms,
                        success=False,
                        error=f"{type(exc).__name__}: {exc}",
                        tags=tags,
                    )
                    continue
                latency_ms = round((time.perf_counter() - t0) * 1000.0, 2)
                if takes_kwargs:
                    acc = float(self.scorer(out, q.expected, **self.scorer_kwargs))
                else:
                    acc = float(self.scorer(out, q.expected))
                refusal = 1.0 if is_refusal(out) else 0.0
                bench.record(
                    input=q.question,
                    output=out,
                    latency_ms=latency_ms,
                    success=True,
                    tags=tags,
                    accuracy=acc,
                    refusal=refusal,
                )
        return bench

    def summary(self) -> dict[str, Any]:
        """Lightweight summary without invoking a model — row counts + tags.

        Useful for the lineage entry (V2 in HANDOFF) where we want to record
        what the bench will measure before the model has actually run.
        """
        return {
            "name": self.name,
            "n": len(self.questions),
            "scorer": getattr(self.scorer, "__name__", "custom"),
            "tag_keys": sorted({k for q in self.questions for k in q.tags.keys()}),
        }


def _accepts_kwargs(fn: Callable[..., Any]) -> bool:
    """True iff `fn` declares **kwargs or any default-valued kwarg.

    Lets `VerticalBench.run` pass `scorer_kwargs` through to scorers like
    `numeric_match(..., rel_tolerance=0.01)` without breaking the two-arg
    `exact_match` / `contains` signatures.
    """
    import inspect

    try:
        sig = inspect.signature(fn)
    except (TypeError, ValueError):
        return False
    for p in sig.parameters.values():
        if p.kind == p.VAR_KEYWORD:
            return True
        if p.kind == p.KEYWORD_ONLY:
            return True
    return False
