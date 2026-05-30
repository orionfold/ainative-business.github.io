# Copyright 2026 Manav Sehgal
# SPDX-License-Identifier: Apache-2.0
"""Eval-bench surface for the Arena — v0.3.

The Orionfold quant/LoRA models were each *measured* against a vertical eval
bench (prompts + gold answers) that lives on the Spark at
``$ARENA_EVAL_BENCHES_ROOT`` (default ``/home/nvidia/data/eval-benches``). This
module exposes those benches to the cockpit so a user can pick a bench prompt,
see the reference answer beside the live response, and get the response scored
against gold with the *correct* per-prompt scorer.

Design notes
------------
* **Two views of every row.** :func:`fieldkit.eval.VerticalBench.from_jsonl`
  mutates ``question`` (prepends oracle/retrieval/evidence context + MCQ
  options) and keeps only the gold in ``expected``; it drops per-row
  ``family`` / ``scoring_mode`` for the non-patent shapes. So we read the raw
  JSONL rows ourselves and, per row, build **both** the *raw question* (shown
  in the composer, editable) and the *model prompt* (the context-prepended form
  the bench was measured with — what the model actually receives). We reuse
  ``_row_to_qa`` / ``_detect_format`` from :mod:`fieldkit.eval.vertical` so the
  prepend logic stays identical to the offline measurement scripts.
* **Scorer dispatch is data, not branching.** Each bench declares its scorer
  policy in :data:`BENCHES`; patent dispatches per-family via
  :data:`fieldkit.eval.vertical.PATENT_STRATEGIST_SCORERS`. Deterministic
  scorers (``mcq_letter`` / ``numeric_match`` / ``exact_match`` /
  ``irac_structure``) run instantly and never construct a judge. Only the
  judge-backed families (patent ``A`` / ``D-oa`` / open-ended ``C`` / ``E``)
  and free-prompt quality grading call an LLM.
* **Two judge backends, one client class.** :class:`fieldkit.nim.NIMClient`
  already carries an ``api_key`` bearer header, so it doubles as the OpenRouter
  judge client (``base_url="https://openrouter.ai/api/v1"`` + the key) — no
  adapter needed. The *local* judge reuses the already-warm **resident brain**
  (zero extra model load, no eviction of the model under eval, no extra
  unified-memory pressure).
* **The server owns the gold.** The prompts endpoint returns ``reference`` for
  *display*, but the scoring path re-derives gold from the cached raw row keyed
  by ``(bench_id, qid)`` — the client never sends the gold it scores against.

Per ``feedback_llm_skill_pattern`` the deterministic parts are pure Python; the
judge call is the one LLM touch and is gated behind explicit backend selection.
"""

from __future__ import annotations

import os
import re
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from fieldkit.eval.vertical import (
    PATENT_STRATEGIST_SCORERS,
    _detect_format,
    _extract_evidence_text,
    _row_to_qa,
)

__all__ = [
    "ARENA_EVAL_BENCHES_ROOT",
    "BenchSpec",
    "BENCHES",
    "EvalPrompt",
    "build_model_prompt",
    "EvalScoreError",
    "LoadedBench",
    "bench_for_lane",
    "default_openrouter_judge_model",
    "judge_availability",
    "list_benches",
    "list_prompts",
    "load_bench",
    "score_eval_prediction",
    "score_free_prompt",
]


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

#: Root of the on-disk eval benches. Override with ``ARENA_EVAL_BENCHES_ROOT``
#: so a fresh machine (or a test) can point at a different tree.
ARENA_EVAL_BENCHES_ROOT = Path(
    os.environ.get("ARENA_EVAL_BENCHES_ROOT", "/home/nvidia/data/eval-benches")
)

#: Default OpenRouter judge model — a cheap, capable frontier grader. The UI
#: can override per-request via ``judge.model``.
_DEFAULT_OPENROUTER_JUDGE = "anthropic/claude-3.5-haiku"

#: Judge token budget. Generous enough that a reasoning resident brain's
#: ``<think>`` preamble doesn't crowd out the trailing ``{"score": ...}`` JSON
#: that :meth:`fieldkit.eval.Judge.parse` recovers.
_JUDGE_MAX_TOKENS = 512

# Scorer kinds that need no LLM — score instantly, free.
_DETERMINISTIC_KINDS = frozenset(
    {"mcq_letter", "numeric_match", "exact_match", "contains", "irac_structure"}
)
# Scorer kinds that require a judge backend.
_JUDGE_KINDS = frozenset(
    {"patent_claim_validity", "office_action_argument", "judge_rubric"}
)

_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class BenchSpec:
    """One eval bench the cockpit can browse + score against.

    ``files`` are paths relative to :data:`ARENA_EVAL_BENCHES_ROOT`. ``fmt`` is
    the :func:`VerticalBench.from_jsonl` format used to map raw rows to a
    context-prepended model prompt. ``fixed_scorer`` overrides the per-row
    scorer kind for every row (MCQ benches → ``mcq_letter``, LegalBench →
    ``exact_match``); when ``None`` the scorer is derived per row (finance →
    ``numeric_match``; patent → per-family). ``models`` are the artifact slugs
    that map to this bench for the auto-suggested-bench UX.
    """

    bench_id: str
    vertical: str
    label: str
    files: tuple[str, ...]
    fmt: str
    open_book: bool = False
    fixed_scorer: str | None = None
    models: tuple[str, ...] = ()


BENCHES: dict[str, BenchSpec] = {
    "patent-strategist": BenchSpec(
        bench_id="patent-strategist",
        vertical="patent",
        label="Patent Strategist",
        files=(
            "patent-strategist/seed-A.jsonl",
            "patent-strategist/seed-B.jsonl",
            "patent-strategist/seed-C.jsonl",
            "patent-strategist/seed-D-mcq.jsonl",
            "patent-strategist/seed-D-oa.jsonl",
            "patent-strategist/seed-D-irac.jsonl",
            "patent-strategist/seed-E.jsonl",
        ),
        fmt="patent-strategist",
        models=("patent-strategist-v3-nemo-gguf", "patent-strategist-v3-nemo"),
    ),
    "financebench": BenchSpec(
        bench_id="financebench",
        vertical="finance",
        label="FinanceBench",
        files=("financebench/financebench_merged.jsonl",),
        fmt="financebench",
        open_book=True,
        fixed_scorer="numeric_match",
        models=("finance-chat-gguf",),
    ),
    "legalbench": BenchSpec(
        bench_id="legalbench",
        vertical="legal",
        label="LegalBench",
        files=("legalbench/legalbench_merged.jsonl",),
        fmt="legalbench",
        fixed_scorer="exact_match",
        models=("saul-7b-instruct-v1-gguf",),
    ),
    "cybermetric": BenchSpec(
        bench_id="cybermetric",
        vertical="cyber",
        label="CyberMetric",
        # {id, text, answer, task} — same field signature as LegalBench (no
        # separate context), MCQ options already inlined into ``text``.
        files=("cybermetric/cybermetric_merged.jsonl",),
        fmt="legalbench",
        fixed_scorer="mcq_letter",
        models=("securityllm-gguf",),
    ),
    "medmcqa": BenchSpec(
        bench_id="medmcqa",
        vertical="medical",
        label="MedMCQA",
        files=("medmcqa/medmcqa_merged.jsonl",),
        fmt="legalbench",
        fixed_scorer="mcq_letter",
        models=("ii-medical-8b-gguf",),
    ),
}


# ---------------------------------------------------------------------------
# Loaded bench (mtime-cached)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class EvalPrompt:
    """One bench row, resolved into the two views the cockpit needs."""

    qid: str
    question: str  # raw question — shown in the composer, editable
    model_prompt: str  # context+options-prepended — what the model receives
    reference: str  # gold answer (display + scoring)
    family: str | None  # patent family key (A / B / C / D-mcq / D-oa / D-irac / E)
    scorer_kind: str
    scoring_mode: str | None
    options: list[str] | None
    has_context: bool
    context_kind: str | None  # oracle | retrieval | evidence | None
    context_text: str  # the raw context block (for re-wrapping edited prompts)
    context_token_hint: int
    judge_required: bool
    rubric_hints: dict[str, Any] | None  # per-row judge hints (patent A / D-oa)


@dataclass
class LoadedBench:
    """A parsed bench: ordered prompts + a qid index."""

    spec: BenchSpec
    prompts: list[EvalPrompt]
    by_qid: dict[str, EvalPrompt] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.by_qid:
            self.by_qid = {p.qid: p for p in self.prompts}


class EvalScoreError(Exception):
    """Raised when a judge backend is requested but cannot be constructed
    (no resident brain / no OpenRouter key) — caught by the caller and
    surfaced as ``{scored: false, reason: ...}`` rather than a 500."""


# mtime-keyed cache. Maps bench_id -> (mtime_signature, LoadedBench).
_CACHE: dict[str, tuple[tuple[float, ...], LoadedBench]] = {}
_CACHE_LOCK = threading.Lock()


def _bench_paths(spec: BenchSpec) -> list[Path]:
    return [ARENA_EVAL_BENCHES_ROOT / rel for rel in spec.files]


def _mtime_signature(spec: BenchSpec) -> tuple[float, ...] | None:
    """Aggregate mtimes of a bench's files, or ``None`` if none exist."""
    sig: list[float] = []
    any_present = False
    for p in _bench_paths(spec):
        try:
            sig.append(p.stat().st_mtime)
            any_present = True
        except OSError:
            sig.append(-1.0)
    return tuple(sig) if any_present else None


def _patent_family_key(stem: str, row_family: str | None) -> str | None:
    """Map a patent seed file (``seed-A`` / ``seed-D-mcq`` / …) to a
    :data:`PATENT_STRATEGIST_SCORERS` key. The filename is authoritative for
    the D sub-shapes (mcq / oa / irac); A/B/C/E fall back to the row's
    ``family`` field."""
    m = re.match(r"seed-(.+)$", stem)
    if m:
        return m.group(1)
    return row_family


def _raw_question(row: dict[str, Any], fmt: str) -> str:
    """The unprepended prompt to show in the composer."""
    if fmt == "legalbench":
        return str(row.get("text") or row.get("input") or row.get("question") or "")
    return str(row.get("question") or row.get("prompt") or row.get("input") or "")


def _context_for(row: dict[str, Any], fmt: str) -> tuple[str, str | None]:
    """Return ``(context_text, context_kind)`` for a row, or ``("", None)``."""
    if fmt == "financebench":
        return _extract_evidence_text(row), "evidence"
    if fmt == "patent-strategist":
        mode = row.get("scoring_mode") or "closed"
        if mode == "oracle":
            return str(row.get("oracle_context") or row.get("context") or ""), "oracle"
        if mode == "retrieval":
            return str(row.get("context") or ""), "retrieval"
    return "", None


def _resolve_scorer_kind(spec: BenchSpec, family_key: str | None) -> str:
    if spec.fixed_scorer:
        return spec.fixed_scorer
    if spec.fmt == "patent-strategist":
        return PATENT_STRATEGIST_SCORERS.get(family_key or "", "judge_rubric")
    if spec.fmt == "financebench":
        return "numeric_match"
    return "exact_match"


def _parse_jsonl(path: Path) -> list[dict[str, Any]]:
    import json

    rows: list[dict[str, Any]] = []
    try:
        with path.open() as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    except OSError:
        return []
    return rows


def _build_loaded_bench(spec: BenchSpec) -> LoadedBench:
    prompts: list[EvalPrompt] = []
    for rel, path in zip(spec.files, _bench_paths(spec)):
        stem = Path(rel).stem
        rows = _parse_jsonl(path)
        # Resolve format once per file (auto for the bare patent shape).
        fmt = spec.fmt
        for idx, row in enumerate(rows):
            if fmt == "auto":
                fmt = _detect_format(row)
            qa = _row_to_qa(row, fmt, fallback_idx=idx, open_book=spec.open_book)
            if qa is None:
                continue
            family_key = (
                _patent_family_key(stem, row.get("family"))
                if spec.fmt == "patent-strategist"
                else None
            )
            scorer_kind = _resolve_scorer_kind(spec, family_key)
            ctx_text, ctx_kind = _context_for(row, fmt)
            options = row.get("options") if isinstance(row.get("options"), list) else None
            rubric_hints = row.get("rubric") if isinstance(row.get("rubric"), dict) else None
            prompts.append(
                EvalPrompt(
                    qid=qa.qid,
                    question=_raw_question(row, fmt) or qa.question,
                    model_prompt=qa.question,
                    reference=qa.expected,
                    family=family_key,
                    scorer_kind=scorer_kind,
                    scoring_mode=row.get("scoring_mode"),
                    options=options,
                    has_context=bool(ctx_text),
                    context_kind=ctx_kind if ctx_text else None,
                    context_text=ctx_text,
                    context_token_hint=len(ctx_text) // 4,
                    judge_required=scorer_kind in _JUDGE_KINDS,
                    rubric_hints=rubric_hints,
                )
            )
    return LoadedBench(spec=spec, prompts=prompts)


def build_model_prompt(prompt: EvalPrompt, user_text: str) -> str:
    """The prompt actually sent to the model for an eval row.

    When ``user_text`` matches the cached raw question (the common, unedited
    case) we return the canonical ``model_prompt`` verbatim — the exact form
    the bench was measured with. When the user edited the question we re-wrap
    their text with the same context block + MCQ options so the score stays a
    fair, context-matched grade (the gold is unchanged either way).
    """
    if (user_text or "").strip() == (prompt.question or "").strip():
        return prompt.model_prompt
    q = user_text
    if prompt.context_kind in ("oracle", "retrieval") and prompt.context_text:
        q = f"Context:\n\n{prompt.context_text}\n\nQuestion: {q}"
    elif prompt.context_kind == "evidence" and prompt.context_text:
        q = (
            f"Context from the filing:\n\n{prompt.context_text}\n\n"
            f"Question: {q}\n\nAnswer with just the numeric value."
        )
    if prompt.options:
        opts = "\n".join(
            f"{chr(65 + i)}. {o}"
            for i, o in enumerate(prompt.options)
            if isinstance(o, str)
        )
        if opts:
            q = f"{q}\n\nOptions:\n{opts}"
    return q


def load_bench(bench_id: str) -> LoadedBench | None:
    """Return the parsed bench, refreshing the cache on file mtime change.

    Returns ``None`` when the bench is unknown or its files are absent (fresh
    machine) — callers degrade gracefully rather than 500.
    """
    spec = BENCHES.get(bench_id)
    if spec is None:
        return None
    sig = _mtime_signature(spec)
    if sig is None:
        return None
    with _CACHE_LOCK:
        cached = _CACHE.get(bench_id)
        if cached is not None and cached[0] == sig:
            return cached[1]
        loaded = _build_loaded_bench(spec)
        _CACHE[bench_id] = (sig, loaded)
        return loaded


# ---------------------------------------------------------------------------
# Model → bench mapping
# ---------------------------------------------------------------------------


def _norm(s: str) -> str:
    return "".join(ch for ch in (s or "").lower() if ch.isalnum())


def bench_for_lane(lane_id: str | None) -> str | None:
    """Map a compare/options lane id to its own-vertical bench, or ``None``.

    Normalizes ``local:<slug>::<variant>`` (and bare slugs) the same way the
    on-demand GGUF resolver does, then matches against each bench's declared
    ``models`` by normalized-prefix. ``local:resident`` and ``openrouter:*``
    have no canonical bench (cross-vertical runs are still allowed — the UI
    just doesn't pre-suggest a bench)."""
    if not lane_id:
        return None
    lid = lane_id
    if lid.startswith("local:"):
        lid = lid[len("local:") :]
    if lid in ("resident",) or lid.startswith("openrouter"):
        return None
    slug = lid.partition("::")[0]
    nslug = _norm(slug)
    if not nslug:
        return None
    for spec in BENCHES.values():
        for model in spec.models:
            nm = _norm(model)
            if nm and (nslug.startswith(nm) or nm.startswith(nslug)):
                return spec.bench_id
    return None


# ---------------------------------------------------------------------------
# Listing helpers (JSON-safe payloads for the endpoints)
# ---------------------------------------------------------------------------


def _prompt_payload(p: EvalPrompt) -> dict[str, Any]:
    return {
        "qid": p.qid,
        "question": p.question,
        "reference": p.reference,
        "family": p.family,
        "scorer_kind": p.scorer_kind,
        "scoring_mode": p.scoring_mode,
        "options": p.options,
        "has_context": p.has_context,
        "context_kind": p.context_kind,
        "context_token_hint": p.context_token_hint,
        "judge_required": p.judge_required,
    }


def list_benches() -> list[dict[str, Any]]:
    """One row per bench, with availability + the models it maps to.

    Unavailable benches (files absent) are still listed with
    ``available: false`` so the UI can explain what's missing rather than
    silently hide a vertical."""
    out: list[dict[str, Any]] = []
    for spec in BENCHES.values():
        loaded = load_bench(spec.bench_id)
        if loaded is None:
            out.append(
                {
                    "bench_id": spec.bench_id,
                    "vertical": spec.vertical,
                    "label": spec.label,
                    "available": False,
                    "count": 0,
                    "families": [],
                    "scorer_kinds": [],
                    "models": list(spec.models),
                }
            )
            continue
        families = sorted({p.family for p in loaded.prompts if p.family})
        scorer_kinds = sorted({p.scorer_kind for p in loaded.prompts})
        out.append(
            {
                "bench_id": spec.bench_id,
                "vertical": spec.vertical,
                "label": spec.label,
                "available": True,
                "count": len(loaded.prompts),
                "families": families,
                "scorer_kinds": scorer_kinds,
                "models": list(spec.models),
            }
        )
    return out


def list_prompts(
    bench_id: str,
    *,
    q: str | None = None,
    family: str | None = None,
    offset: int = 0,
    limit: int = 50,
) -> dict[str, Any] | None:
    """Paginated, filterable prompt list for one bench, or ``None`` if absent.

    ``q`` is a case-insensitive substring filter over the raw question; the
    pagination ``total`` reflects the *filtered* set so the UI's "Load more"
    converges."""
    loaded = load_bench(bench_id)
    if loaded is None:
        return None
    rows = loaded.prompts
    if family:
        rows = [p for p in rows if p.family == family]
    if q:
        ql = q.lower()
        rows = [p for p in rows if ql in p.question.lower()]
    total = len(rows)
    offset = max(0, offset)
    limit = max(1, min(limit, 200))
    window = rows[offset : offset + limit]
    return {
        "bench_id": bench_id,
        "total": total,
        "offset": offset,
        "limit": limit,
        "prompts": [_prompt_payload(p) for p in window],
    }


# ---------------------------------------------------------------------------
# Judge construction + availability
# ---------------------------------------------------------------------------


def default_openrouter_judge_model() -> str:
    return os.environ.get("ARENA_OPENROUTER_JUDGE_MODEL", _DEFAULT_OPENROUTER_JUDGE)


def judge_availability(resident: dict[str, Any] | None) -> dict[str, Any]:
    """Surface to the UI which judge backends are usable right now."""
    local_ok = bool(resident and resident.get("base_url"))
    or_ok = bool(os.environ.get("OPENROUTER_API_KEY"))
    return {
        "local_available": local_ok,
        "openrouter_available": or_ok,
        "openrouter_default_model": default_openrouter_judge_model(),
        "default_backend": "local" if local_ok else ("openrouter" if or_ok else None),
    }


def _build_judge(
    rubric: str,
    *,
    judge_backend: str | None,
    judge_model: str | None,
    resident: dict[str, Any] | None,
):
    """Construct a :class:`fieldkit.eval.Judge` for the chosen backend.

    Local reuses the warm resident brain (no extra model load); OpenRouter
    points the same :class:`NIMClient` at the OpenRouter ``/v1`` base with the
    API key as the bearer token. Raises :class:`EvalScoreError` when the chosen
    backend is unavailable so the caller can degrade with a clear reason."""
    from fieldkit.eval import Judge
    from fieldkit.nim import NIMClient

    backend = judge_backend or "local"
    if backend == "openrouter":
        key = os.environ.get("OPENROUTER_API_KEY")
        if not key:
            raise EvalScoreError("OpenRouter judge requested but OPENROUTER_API_KEY is unset")
        client = NIMClient(
            base_url="https://openrouter.ai/api/v1",
            model=judge_model or default_openrouter_judge_model(),
            api_key=key,
        )
    else:
        if not resident or not resident.get("base_url"):
            raise EvalScoreError("local judge unavailable (no resident brain configured)")
        client = NIMClient(
            base_url=str(resident["base_url"]),
            model=judge_model or str(resident.get("model") or "resident"),
            api_key="local",
        )
        # Local residents are often reasoning models (Qwen3 / R1-distill family)
        # that burn the whole token budget on a ``<think>`` chain before ever
        # emitting the ``{"score": ...}`` JSON — leaving the grade unparseable.
        # The ``/no_think`` switch turns Qwen3 thinking off so the JSON lands
        # immediately; it's inert text on non-reasoning residents. (The resident
        # must be served with ``--reasoning-format none`` so the answer stays in
        # ``message.content`` rather than a separate reasoning field.)
        rubric = rubric + " /no_think"
    return Judge(client=client, rubric=rubric, max_tokens=_JUDGE_MAX_TOKENS)


def _render_hints(rubric: dict[str, Any] | None) -> str | None:
    """Render a per-row judge-hint dict as a stable ``Hints:`` block."""
    if not rubric:
        return None
    import json

    lines = ["Hints:"]
    for k in sorted(rubric.keys()):
        v = rubric[k]
        if isinstance(v, (list, tuple)):
            lines.append(f"- {k}:")
            lines.extend(f"  - {item}" for item in v)
        elif isinstance(v, dict):
            lines.append(f"- {k}: {json.dumps(v, sort_keys=True)}")
        else:
            lines.append(f"- {k}: {v}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------


def _content_only(predicted: str) -> str:
    """Strip a stray ``<think>…</think>`` block defensively. Callers usually
    pass the already-split answer channel, but free-typed scoring may hand us
    a raw stream."""
    return _THINK_RE.sub("", predicted or "").strip()


def _skip(scorer_kind: str, reason: str, reference: str = "") -> dict[str, Any]:
    return {
        "scored": False,
        "scorer_kind": scorer_kind,
        "reason": reason,
        "reference": reference,
    }


def _det_result(
    *, scorer_kind: str, score: float, max_score: float, why: str, reference: str
) -> dict[str, Any]:
    return {
        "scored": True,
        "scorer_kind": scorer_kind,
        "score": round(float(score), 4),
        "max": float(max_score),
        "normalized": round(float(score) / float(max_score), 4) if max_score else 0.0,
        "why": why,
        "reference": reference,
        "judge_backend": None,
    }


def _judge_result(
    *,
    scorer_kind: str,
    judge_backend: str,
    score: float | None,
    max_score: float,
    rationale: str,
    reference: str,
) -> dict[str, Any]:
    s = 0.0 if score is None else float(score)
    return {
        "scored": True,
        "scorer_kind": scorer_kind,
        "score": round(s, 4),
        "max": float(max_score),
        "normalized": round(s / float(max_score), 4) if max_score else 0.0,
        "why": rationale,
        "reference": reference,
        "judge_backend": judge_backend,
    }


def score_eval_prediction(
    bench_id: str,
    qid: str,
    predicted: str,
    *,
    judge_backend: str | None = None,
    judge_model: str | None = None,
    resident: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Score ``predicted`` against the gold for ``(bench_id, qid)``.

    Deterministic scorers run instantly with no judge. Judge-backed families
    build a :class:`Judge` on the chosen backend. Returns a JSON-safe dict;
    ``scored`` is ``False`` (with a ``reason``) when scoring can't proceed —
    missing row, judge unavailable, context overflow, or an unreconstructable
    structured reference (patent Family B ranked lists).
    """
    from fieldkit.eval import (
        RUBRIC_CORRECTNESS,
        RUBRIC_OFFICE_ACTION_ARGUMENT,
        RUBRIC_PATENT_CLAIM_VALIDITY,
        exact_match,
        irac_structure,
        mcq_letter,
        numeric_match,
    )
    from fieldkit.nim import NIMContextOverflowError

    loaded = load_bench(bench_id)
    if loaded is None:
        return _skip("unknown", f"bench {bench_id!r} unavailable")
    prompt = loaded.by_qid.get(qid)
    if prompt is None:
        return _skip("unknown", f"qid {qid!r} not found in {bench_id!r}")

    kind = prompt.scorer_kind
    pred = _content_only(predicted)
    ref = prompt.reference

    # --- Deterministic scorers (no judge) ---
    if kind == "numeric_match":
        s = numeric_match(pred, ref)
        return _det_result(
            scorer_kind=kind, score=s, max_score=1.0, reference=ref,
            why=f"first number {'matches' if s else 'differs from'} gold within ±1%",
        )
    if kind == "mcq_letter":
        s = mcq_letter(pred, ref)
        return _det_result(
            scorer_kind=kind, score=s, max_score=1.0, reference=ref,
            why=f"picked letter {'matches' if s else 'differs from'} gold {ref!r}",
        )
    if kind == "exact_match":
        s = exact_match(pred, ref)
        return _det_result(
            scorer_kind=kind, score=s, max_score=1.0, reference=ref,
            why=f"answer {'matches' if s else 'differs from'} gold {ref!r}",
        )
    if kind == "irac_structure":
        s = irac_structure(pred)
        return _det_result(
            scorer_kind=kind, score=s, max_score=1.0, reference=ref,
            why=f"{int(round(s * 4))}/4 IRAC components present",
        )

    # --- Family B: ranked-list gold can't be reconstructed from prose ---
    if kind == "prior_art_relevance":
        if judge_backend:
            kind = "judge_fallback"  # fall through to judge-correctness below
        else:
            return _skip(
                "prior_art_relevance",
                "prior-art ranking reference is not reconstructable from the prose "
                "gold_label; pick a judge backend to grade by correctness instead",
                reference=ref,
            )

    # --- Judge-backed families ---
    if kind in _JUDGE_KINDS or kind == "judge_fallback":
        if kind == "patent_claim_validity":
            rubric, max_score = RUBRIC_PATENT_CLAIM_VALIDITY, 5.0
        elif kind == "office_action_argument":
            rubric, max_score = RUBRIC_OFFICE_ACTION_ARGUMENT, 5.0
        else:  # judge_rubric (C / E) or judge_fallback (B)
            rubric, max_score = RUBRIC_CORRECTNESS, 5.0
        try:
            judge = _build_judge(
                rubric,
                judge_backend=judge_backend,
                judge_model=judge_model,
                resident=resident,
            )
            result = judge.grade(
                prediction=pred,
                question=prompt.question,
                reference=ref or None,
                context=_render_hints(prompt.rubric_hints),
            )
        except EvalScoreError as exc:
            return _skip(kind, str(exc), reference=ref)
        except NIMContextOverflowError:
            return _skip(kind, "judge context overflow", reference=ref)
        except Exception as exc:  # noqa: BLE001 — judge transport / parse failures
            return _skip(kind, f"judge call failed: {exc}", reference=ref)
        if result.score is None:
            # Empty / unparseable grade — common when a reasoning-model judge is
            # served without ``--reasoning-format none`` (the answer JSON lands
            # in a separate reasoning field, leaving ``content`` empty). Surface
            # honestly rather than reporting a misleading 0.0.
            return _skip(
                kind,
                "judge returned no parseable score — serve the local judge with "
                "--reasoning-format none, or switch the judge backend to OpenRouter",
                reference=ref,
            )
        return _judge_result(
            scorer_kind=kind,
            judge_backend=judge_backend or "local",
            score=result.score,
            max_score=max_score,
            rationale=result.rationale or "",
            reference=ref,
        )

    return _skip(kind, f"no scorer wired for kind {kind!r}", reference=ref)


def score_free_prompt(
    question: str,
    predicted: str,
    *,
    judge_backend: str | None = None,
    judge_model: str | None = None,
    resident: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Reference-free quality grade for a user's own (non-eval) prompt.

    Uses the relevance rubric (0–1): does the answer address the question?
    Only invoked when the user explicitly opts into judging a free prompt."""
    from fieldkit.eval import RUBRIC_RELEVANCE
    from fieldkit.nim import NIMContextOverflowError

    try:
        judge = _build_judge(
            RUBRIC_RELEVANCE,
            judge_backend=judge_backend,
            judge_model=judge_model,
            resident=resident,
        )
        result = judge.grade(prediction=_content_only(predicted), question=question)
    except EvalScoreError as exc:
        return _skip("judge_quality", str(exc))
    except NIMContextOverflowError:
        return _skip("judge_quality", "judge context overflow")
    except Exception as exc:  # noqa: BLE001
        return _skip("judge_quality", f"judge call failed: {exc}")
    if result.score is None:
        return _skip(
            "judge_quality",
            "judge returned no parseable score — serve the local judge with "
            "--reasoning-format none, or switch the judge backend to OpenRouter",
        )
    return _judge_result(
        scorer_kind="judge_quality",
        judge_backend=judge_backend or "local",
        score=result.score,
        max_score=1.0,
        rationale=result.rationale or "",
        reference="",
    )
