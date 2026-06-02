# Copyright 2026 Manav Sehgal
# SPDX-License-Identifier: Apache-2.0
"""Record dataclasses + (M3+) pydantic request/response schemas.

**M2 fills the dataclass half.** The stdlib :mod:`dataclasses` records
(``LaneRecord``, ``BenchResultRow``, ``ArticleIndexRow``, ``HfMetaRow``,
``NotebookExportRow``, ``LeaderboardRow``) are the typed rows the importer
constructs and the store persists. They double as the on-disk row shape and
the M3+ ``schemas`` re-exports (FastAPI request/response models layer on
top of these).

Pydantic still lands at M3 (FastAPI uses pydantic v2 internally) and is
imported lazily then. M2 stays stdlib-only so the import path is cheap and
``pytest fieldkit/tests/arena/`` runs without the ``arena`` extra installed.

Per `feedback_llm_skill_pattern`: deterministic Python only — no LLM here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

__all__ = [
    # M2 — row records the importer + store traffic in
    "LaneRecord",
    "BenchResultRow",
    "ArticleIndexRow",
    "HfMetaRow",
    "NotebookExportRow",
    "LeaderboardRow",
    # M4 — chat surface (operator-private; never mirrored)
    "ChatSessionRecord",
    "ChatTurnRecord",
    # M5 — compare / rubric-score / human-pref records (publishable by default
    # for compare_*, never via the mirror's hardcoded allowlist for human_prefs).
    "CompareRunRecord",
    "CompareResponseRecord",
    "RubricScoreRecord",
    "HumanPrefRecord",
    # M8 — control-plane queue records (operator-private; NEVER mirrored).
    "JobRecord",
    "JobTriggerRecord",
]


# ---------------------------------------------------------------------------
# M2 records (filled in this milestone)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class LaneRecord:
    """One row of the ``lanes`` table — spec §4.8.

    A "lane" is a *servable configuration* the cockpit can warm + swap.
    For a quant manifest that ships N variants, the importer creates N
    lanes (one per ``(slug, variant)``). For a LoRA the importer creates
    one lane keyed off the slug. For a harness/skill manifest the importer
    creates a navigational row (``port=0``, ``base_url=""``) so the
    artifact browser can join through ``manifest_slug`` even though the
    artifact isn't directly servable.
    """

    id: str
    kind: str  # 'LlamaServerLane'|'NIMLane'|'VLLMLane'|'OllamaLane'|'HarnessConfig'|'LoRAMerged'|...
    model: str
    port: int
    base_url: str
    start_script: Optional[str] = None
    stop_script: Optional[str] = None
    manifest_slug: Optional[str] = None
    recommended: int = 0
    last_warm_at: Optional[str] = None
    last_swap_at: Optional[str] = None
    notes: Optional[str] = None


@dataclass(frozen=True)
class BenchResultRow:
    """One row of the ``bench_results`` table — spec §7.

    The per-variant rollup the M2 importer pulls out of an article's
    ``evidence/*_results.json``. ``source_path`` records the JSON the row
    was derived from so the audit-mode in the curator can drift-detect.
    """

    bench_slug: str
    variant_label: str
    core_pass_rate: Optional[float] = None
    consistency: Optional[float] = None
    runaway_rate: Optional[float] = None
    wall_mean_s: Optional[float] = None
    tok_per_sec: Optional[float] = None
    p50_s: Optional[float] = None
    p95_s: Optional[float] = None
    gpu_util_mean: Optional[float] = None
    unified_used_gb_max: Optional[float] = None
    source_path: str = ""
    fetched_at: str = ""


@dataclass(frozen=True)
class ArticleIndexRow:
    """One row of the ``article_index`` table — spec §7.

    The article's frontmatter, denormalized to columns the cockpit
    actually filters/sorts/joins on. ``fieldkit_modules_json`` and
    ``referenced_artifact_slugs_json`` are JSON-encoded list columns
    (SQLite has no native ARRAY).
    """

    slug: str
    title: str
    source_path: str
    fetched_at: str
    series: Optional[str] = None
    stage: Optional[str] = None
    status: Optional[str] = None  # 'published' (default if absent) | 'upcoming'
    customer_linked: int = 0
    published_at: Optional[str] = None
    signature: Optional[str] = None
    summary: Optional[str] = None
    fieldkit_modules_json: Optional[str] = None
    referenced_artifact_slugs_json: Optional[str] = None


@dataclass(frozen=True)
class HfMetaRow:
    """One row of the ``hf_meta`` table — spec §7.

    Cached HF repo metadata (`huggingface_hub.HfApi.repo_info` shape). M2
    populates this opportunistically: when ``huggingface_hub`` is
    importable AND the operator has run ``huggingface-cli login`` OR the
    repo is public; otherwise an ``error`` string lands and the row still
    counts as "we tried." The cockpit treats absent metadata as the
    default-empty state, not an error.
    """

    repo_id: str
    fetched_at: str
    downloads: Optional[int] = None
    likes: Optional[int] = None
    last_modified: Optional[str] = None
    has_card: int = 0
    error: Optional[str] = None


@dataclass(frozen=True)
class NotebookExportRow:
    """One row of the ``notebook_export`` table — spec §7.

    Glob output of ``notebooks/<vertical>/exports/{builder,user}/*.png``.
    ``artifact_slug`` joins back to the notebook manifest (the
    ``<vertical>-notebooks`` slug).
    """

    file_path: str
    fetched_at: str
    artifact_slug: Optional[str] = None
    role: Optional[str] = None  # 'builder' | 'user'
    kind: Optional[str] = None  # 'png' | 'html' | …
    bytes: Optional[int] = None
    mtime: Optional[str] = None


@dataclass(frozen=True)
class LeaderboardRow:
    """One row of the ``leaderboard_rows`` table — spec §4.8.

    Denormalized cross-bench rollup. M2 seeds this from the brain-bakeoff
    evidence JSON so the cockpit ships a non-empty leaderboard on day one.
    M5 keeps it fresh: every compare run touches the corresponding row.
    """

    bench_id: str
    lane_id: str
    n_runs: int
    mean_score: float
    last_run_at: str
    manifest_slug: Optional[str] = None
    median_tok_per_s: Optional[float] = None
    mean_ttft_ms: Optional[float] = None
    human_pref_winrate: Optional[float] = None


# ---------------------------------------------------------------------------
# M3+ stubs (declared so the import path is reserved; bodies land at their
# milestone). Each is a placeholder dataclass — sufficient to round-trip
# through `dataclasses.asdict` and store via ``ArenaStore._upsert`` once
# the table receives writes.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ChatSessionRecord:  # M4
    """One row of the ``chat_sessions`` table — operator-private, never mirrored.

    A chat session groups N ordered ``ChatTurnRecord`` rows under one
    ``lane_id`` (the resident brain the cockpit is talking to). The
    ``publishable`` flag defaults to 0 per spec §4.8 — the mirror
    exporter's allowlist (M6) hardcodes ``chat_*`` tables OUT of the
    enumeration, so even ``publishable=1`` rows never leak. The flag is
    reserved for a future "promote this conversation to a public artifact"
    workflow that doesn't exist in v0.1.
    """

    id: str
    lane_id: str
    created_at: str
    rubric_id: Optional[str] = None
    publishable: int = 0


@dataclass(frozen=True)
class ChatTurnRecord:  # M4
    """One row of the ``chat_turns`` table — operator-private, never mirrored.

    ``reasoning`` carries the ``<think>`` prefix split out via
    ``fieldkit.notebook.split_think`` so the UI can collapse it. ``ttft_ms``
    and ``tok_per_s`` are populated by the M4 chat stream's ``done`` event;
    they're nullable on user-role turns. ``finish_reason`` mirrors the
    OpenAI-compat shape (``"stop"`` / ``"length"`` / ``"error"``).
    """

    session_id: str
    ord: int
    role: str
    content: str
    created_at: str
    reasoning: Optional[str] = None
    tokens_in: Optional[int] = None
    tokens_out: Optional[int] = None
    ttft_ms: Optional[float] = None
    tok_per_s: Optional[float] = None
    finish_reason: Optional[str] = None


@dataclass(frozen=True)
class CompareRunRecord:  # M5
    """One row of the ``compare_runs`` table — spec §4.8.

    The header row for a side-by-side compare. The two ``compare_responses``
    rows (one per side) and the two ``rubric_scores`` rows FK back to ``id``.
    ``publishable`` defaults to 1 — compare runs are the public-facing slice
    of the cockpit (the leaderboard read-model derives from them). ``prompt``
    is operator-only; only ``redacted_prompt`` (operator opt-in via a future
    "promote" workflow) lands in the M6 mirror.
    """

    id: str
    prompt: str
    rubric_id: str
    lane_a_id: str
    lane_b_id: str
    created_at: str
    publishable: int = 1
    redacted_prompt: Optional[str] = None


@dataclass(frozen=True)
class CompareResponseRecord:  # M5
    """One row of the ``compare_responses`` table — one per side per run.

    ``side`` is ``'A'`` or ``'B'``; the ``(compare_run_id, side)`` composite
    is the primary key. ``reasoning`` carries the ``<think>`` prefix split
    out via ``fieldkit.notebook.split_think`` so the mirror's redacted
    rendering can drop the chain without losing the answer. ``unified_peak_gb``
    captures the in-stream envelope ceiling per spec §4.3 (used by the M6
    leaderboard JSON's footprint column).
    """

    compare_run_id: str
    side: str  # 'A' | 'B'
    lane_id: str
    content: str
    reasoning: Optional[str] = None
    tokens_out: Optional[int] = None
    ttft_ms: Optional[float] = None
    tok_per_s: Optional[float] = None
    unified_peak_gb: Optional[float] = None


@dataclass(frozen=True)
class RubricScoreRecord:  # M5
    """One row of the ``rubric_scores`` table — spec §4.8.

    Either ``compare_run_id`` + ``side`` is set (compare scoring) OR
    ``chat_turn_id`` is set (M6 score-a-chat-turn), never both. The SQL
    CHECK constraint enforces at-least-one. ``checks_json`` mirrors the
    :class:`fieldkit.eval.CheckResult` shape — a list of ``{name, kind,
    ok, why}`` — so the M5 compare UI can render the per-check ``why``
    string under each side without a second round-trip.
    """

    rubric_id: str
    total: float
    checks_json: str
    scored_at: str
    compare_run_id: Optional[str] = None
    chat_turn_id: Optional[int] = None
    side: Optional[str] = None


@dataclass(frozen=True)
class HumanPrefRecord:  # M5
    """One row of the ``human_prefs`` table — spec §4.3.

    The operator's thumbs-up / thumbs-down / tie verdict on a compare run.
    Spec §4.3 calls this a **separate signal** from ``rubric_scores.total``:
    the M5 sidecar inserts the row but NEVER mutates the corresponding
    rubric score. Surfaces in the leaderboard as ``human_pref_winrate``
    only at ≥5 prefs per lane (statistical floor).
    """

    id: str
    compare_run_id: str
    winner: str  # 'A'|'B'|'tie'
    created_at: str
    note: Optional[str] = None


# ---------------------------------------------------------------------------
# M8 records — the control-plane queue (operator-private; never mirrored)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class JobRecord:  # M8
    """One row of the ``jobs`` table — spec §12.3. The queue spine.

    A queued job is drained one-at-a-time (single lane, 128 GB envelope)
    through the ``fieldkit.harness`` MCP surface. ``payload_json`` is
    OPERATOR-ONLY (it carries the lane/bench/prompt of the work) — ``jobs``
    is on ``mirror.FORBIDDEN_TABLES`` and ``("jobs","payload_json")`` is on
    ``FORBIDDEN_COLUMNS`` (R13). ``dedup_key`` = ``(kind, lane_id, bench_id)``
    coalesces duplicate triggers while a job is still in flight; leave it
    ``None`` for a manual one-off that should always run. ``arq_job_id`` is the
    existing ``eval_runs`` socket — ``None`` while draining via the M8 primary
    ``BackgroundTasks`` path (R14), populated only under the opt-in arq backend.
    """

    id: str
    kind: str  # 'eval_rerun' | 'measure_variants' (M8); later-phase stubs beyond
    status: str  # 'queued'|'dispatched'|'running'|'done'|'failed'|'skipped'
    trigger: str  # 'manual'|'leaderboard_regression'|'stale_bench'|…
    payload_json: str
    enqueued_at: str
    priority: int = 0
    dedup_key: Optional[str] = None
    result_json: Optional[str] = None
    error: Optional[str] = None
    attempt: int = 0
    dispatched_at: Optional[str] = None
    finished_at: Optional[str] = None
    arq_job_id: Optional[str] = None


@dataclass(frozen=True)
class JobTriggerRecord:  # M8
    """One row of the ``job_triggers`` table — spec §12.3.

    The audit trail of *what* fired each job: a regression delta
    (``{bench_id, prev_score, new_score, delta}``), a staleness age
    (``{age_days}``), or an operator note (``{operator_note}``). Never
    mirrored (the table is on ``FORBIDDEN_TABLES``). ``id`` is AUTOINCREMENT,
    so the importer/dispatcher omits it on insert.
    """

    job_id: str
    source: str  # 'leaderboard_regression'|'stale_bench'|'operator'
    detail_json: str
    created_at: str
