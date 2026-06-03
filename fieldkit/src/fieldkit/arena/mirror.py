# Copyright 2026 Manav Sehgal
# SPDX-License-Identifier: Apache-2.0
"""SQLite → ``src/data/arena-mirror/*.json`` exporter — the **leak-proof
boundary** between the operator-private cockpit DB and the public mirror.

**M6 surface.** Per spec §4.10 + the M6 / M7 sequencing in
`_SPECS/spark-arena-v1.md`: this module owns *what leaves the Spark*. Two
hardcoded surfaces enforce the boundary, both of which the regression test
``fieldkit/tests/arena/test_mirror_does_not_leak.py`` pins as a hard
M7-blocker:

1. **Allowlist** — the only tables and columns this exporter enumerates are
   the ones in :data:`PUBLISHABLE_TABLES`. Anything not listed is invisible
   to the exporter; adding a new column requires editing the allowlist by
   hand, which is the design point.
2. **Forbidden list** — :data:`FORBIDDEN_TABLES` + :data:`FORBIDDEN_COLUMNS`
   exist as a *belt* over the allowlist's *suspenders*. The exporter never
   references these by name; the regression test reads the emitted JSON
   payload as a string and asserts that a sentinel injected into a
   forbidden column does not appear.

The default output file is ``src/data/arena-mirror/leaderboard.json`` so
the Astro build picks it up by the same import the M2 day-one cut wrote.
The legacy ``rows: [...]`` key is preserved (so the existing ``/arena/``
landing reader keeps working) and supplemented with ``bench_rows`` /
``live_rows`` / ``compare_runs`` / ``compare_responses`` /
``rubric_scores`` / ``human_prefs`` / ``lanes`` arrays the new
``/arena/leaderboard/`` page consumes.

**Atomic write contract** — per `[[reference_sync_workflow_nfs_mount]]`,
the Mac SMB sync can pick up a half-written file mid-tear. Every JSON file
is written to ``<out_dir>/_staging/<name>.json`` first, fully ``fsync``'d,
then renamed onto the final path under a lock-free atomic ``os.replace``.

Per `feedback_llm_skill_pattern`: deterministic Python only. No LLM call,
no network I/O, no subprocess.
"""

from __future__ import annotations

import json
import os
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from fieldkit.arena.store import ArenaStore

__all__ = [
    # Public API the CLI + Astro build prehook call
    "export_publishable_slice",
    "rebuild_leaderboard",
    # Result records — exposed for the CLI's --json output and for the
    # arq job stub that calls the exporter in M2 of v0.2
    "ExportReport",
    "RebuildReport",
    # Allowlist + forbidden-list constants — the security surface, surfaced
    # so the regression test asserts against the same constants the
    # exporter uses (no risk of test/implementation drift)
    "PUBLISHABLE_TABLES",
    "FORBIDDEN_TABLES",
    "FORBIDDEN_COLUMNS",
    "MIRROR_SCHEMA_VERSION",
]

#: Bump when the emitted JSON shape changes incompatibly. M2's seed wrote
#: schema_version=1; M6's exporter writes 2 (adds ``bench_rows`` /
#: ``live_rows`` / per-table arrays alongside the legacy ``rows`` alias).
MIRROR_SCHEMA_VERSION = 2


# ---------------------------------------------------------------------------
# Allowlist (publishable) — every column the exporter is permitted to read
# ---------------------------------------------------------------------------

#: ``{table: (column, …)}``. The exporter NEVER reads a column from a table
#: that isn't a key of this mapping. Order is the emit order in the JSON.
#: NOTE: ``compare_runs`` exposes ``redacted_prompt`` (operator opt-in) but
#: NEVER ``prompt`` — that column lives in :data:`FORBIDDEN_COLUMNS`.
PUBLISHABLE_TABLES: dict[str, tuple[str, ...]] = {
    "leaderboard_rows": (
        "bench_id",
        "lane_id",
        "manifest_slug",
        "n_runs",
        "mean_score",
        "median_tok_per_s",
        "mean_ttft_ms",
        "human_pref_winrate",
        "last_run_at",
        # M9 (Bet 6): the aggregate cost axis. Public-safe — derived means, no
        # prompts. Per-run cost stays on the private host tables (M9-2/M9-7).
        "mean_cost_usd",
        "cost_per_quality_point",
    ),
    "compare_runs": (
        "id",
        "rubric_id",
        "lane_a_id",
        "lane_b_id",
        "created_at",
        "publishable",
        "redacted_prompt",
        # NOTE: 'prompt' deliberately omitted — operator-private until
        # promoted via `fieldkit arena promote-run` (M7+ wires the body).
    ),
    "compare_responses": (
        "compare_run_id",
        "side",
        "lane_id",
        "tokens_out",
        "ttft_ms",
        "tok_per_s",
        "unified_peak_gb",
        # NOTE: 'content' + 'reasoning' deliberately omitted — the full
        # text of the model's reply is operator-private until the
        # corresponding compare_runs row carries a redacted_prompt and an
        # explicit publish promote.
    ),
    "rubric_scores": (
        "id",
        "compare_run_id",
        "side",
        "rubric_id",
        "total",
        "checks_json",
        "scored_at",
    ),
    "human_prefs": (
        "id",
        "compare_run_id",
        "winner",
        "note",
        "created_at",
    ),
    "lanes": (
        "id",
        "kind",
        "model",
        "manifest_slug",
        "recommended",
        # NOTE: ``port`` / ``base_url`` / ``start_script`` / ``stop_script``
        # are operator-host-specific and skipped on principle.
    ),
    # M9 (Bet 6): the price snapshot the public $/task is reconstructable from.
    # PUBLIC-SAFE — pinned per-million prices keyed by model id, no prompts
    # (M9-7). Per-run cost columns inherit their host tables' exclusion.
    "openrouter_price_snapshot": (
        "snapshot_id",
        "model_id",
        "price_per_m_input_usd",
        "price_per_m_output_usd",
        "source",
        "captured_at",
    ),
    # M10 (Bet 5 recall layer): the RAG-eval trend. PUBLIC-SAFE — pure
    # aggregate scores (recall@k, faithfulness) per index version, no prompts
    # and no chunk text (M10-10). ``reindex_runs`` (which can name internal
    # slugs) and any chunk-text path stay OFF — in FORBIDDEN_TABLES below.
    "rag_eval_runs": (
        "id",
        "reindex_run_id",
        "qa_set",
        "recall_at_k",
        "slug_recall_at_k",
        "faithfulness",
        "mean_correctness",
        "refusal_rate",
        "rerank",
        "status",
        "created_at",
    ),
}


# ---------------------------------------------------------------------------
# Forbidden list — the belt over the allowlist's suspenders
# ---------------------------------------------------------------------------

#: Tables the exporter must never enumerate, even by accident. The hardcoded
#: ``PUBLISHABLE_TABLES`` already excludes these; this tuple exists so the
#: regression test asserts the exporter doesn't reach them and so future
#: edits to the exporter can grep for ``FORBIDDEN_TABLES`` before touching
#: a new query.
FORBIDDEN_TABLES: tuple[str, ...] = (
    "chat_sessions",
    "chat_turns",
    "lab_notes",  # v0.2 — operator-private Lab annotations; freeform body never mirrored
    "eval_scores",  # v0.3 — interactive eval grades; rationale can quote model output. Served live via /api/eval/leaderboard, never the static mirror.
    "jobs",  # M8 — control-plane queue; payload_json carries operator prompts/lanes/benches. Served live via /api/jobs, never the static mirror (R13).
    "job_triggers",  # M8 — job audit trail (regression deltas, operator notes); operator-private alongside jobs.
    "leaderboard_baseline",  # M8 — regression-detector prev-snapshot; derived from forbidden eval_scores, operator-internal control-plane state.
    "reindex_runs",  # M10 — index-rebuild provenance; source_set can name internal (lineage) slugs. Control-plane state, never mirrored (M10-10).
)

#: Columns inside otherwise-publishable tables that the exporter must never
#: emit. The :data:`PUBLISHABLE_TABLES` allowlist already excludes these;
#: this tuple exists as the audit anchor.
FORBIDDEN_COLUMNS: tuple[tuple[str, str], ...] = (
    ("compare_runs", "prompt"),
    ("compare_responses", "content"),
    ("compare_responses", "reasoning"),
    ("chat_turns", "content"),
    ("chat_turns", "reasoning"),
    ("chat_sessions", "id"),
    ("lab_notes", "body"),
    ("jobs", "payload_json"),  # M8 — job prompts/lanes/benches; never mirrored (R13)
)


# ---------------------------------------------------------------------------
# Reports
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RebuildReport:
    """Outcome of :func:`rebuild_leaderboard`. Read by the CLI and the
    audit-mode of the curator skill."""

    bench_rows_written: int
    cockpit_rows_written: int
    total_rows: int


@dataclass(frozen=True)
class ExportReport:
    """Outcome of :func:`export_publishable_slice`. Carries enough state for
    the CLI to render a one-line confirmation and for the v0.2 arq job
    stub to log a structured "what got mirrored" event."""

    out_dir: str
    files_written: tuple[str, ...]
    bench_row_count: int
    live_row_count: int
    compare_run_count: int
    rubric_score_count: int
    human_pref_count: int
    lane_count: int
    generated_at: str
    rebuild_report: RebuildReport | None = None
    warnings: tuple[str, ...] = field(default_factory=tuple)

    def summary_line(self) -> str:
        return (
            f"bench={self.bench_row_count} live={self.live_row_count} "
            f"compare_runs={self.compare_run_count} "
            f"rubric_scores={self.rubric_score_count} "
            f"human_prefs={self.human_pref_count} "
            f"lanes={self.lane_count}"
        )

    def as_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "out_dir": self.out_dir,
            "files_written": list(self.files_written),
            "counts": {
                "bench_rows": self.bench_row_count,
                "live_rows": self.live_row_count,
                "compare_runs": self.compare_run_count,
                "rubric_scores": self.rubric_score_count,
                "human_prefs": self.human_pref_count,
                "lanes": self.lane_count,
            },
            "generated_at": self.generated_at,
            "warnings": list(self.warnings),
        }
        if self.rebuild_report is not None:
            d["rebuild"] = {
                "bench_rows": self.rebuild_report.bench_rows_written,
                "cockpit_rows": self.rebuild_report.cockpit_rows_written,
                "total_rows": self.rebuild_report.total_rows,
            }
        return d


# ---------------------------------------------------------------------------
# Rebuild
# ---------------------------------------------------------------------------


def rebuild_leaderboard(store: ArenaStore) -> RebuildReport:
    """Recompute ``leaderboard_rows`` from ``bench_results`` + the live
    ``compare_runs`` × ``rubric_scores`` × ``human_prefs`` join.

    **Bench-anchored rows.** One row per ``(bench_slug, variant_label)``
    in :class:`bench_results` whose ``core_pass_rate`` is not NULL. The
    M2 importer already seeded the 3 brain-bakeoff lanes; this rebuild
    extends the set to vertical-router and cost-router benches (plus any
    future bench evidence the importer registers). ``bench_id`` matches
    ``f"{bench_slug}"`` so an Astro filter can group by it cleanly.

    **Live-cockpit rows.** One row per ``(rubric_id, lane_id)`` derived
    from the publishable ``compare_runs`` (``publishable=1``). Aggregates:

    - ``mean_score`` = average ``rubric_scores.total`` across runs/side.
    - ``n_runs`` = distinct ``compare_run_id`` count for the pair.
    - ``median_tok_per_s`` = median ``compare_responses.tok_per_s``.
    - ``mean_ttft_ms`` = mean ``compare_responses.ttft_ms``.
    - ``human_pref_winrate`` = wins (or 0.5·ties) ÷ total prefs for
      this side; ``None`` until ≥5 prefs accumulate per spec §4.4.

    ``bench_id`` for live-cockpit rows = ``f"cockpit:{rubric_id}"`` so
    they sort/group separately from bench-anchored rows.

    Idempotent — re-running over the same DB produces identical rows.
    Returns a :class:`RebuildReport` for the CLI to render.
    """
    conn = store.connect()
    now = _utc_now_iso()
    bench_written = _rebuild_bench_anchored(conn, fetched_at=now)
    cockpit_written = _rebuild_cockpit_runs(conn, fetched_at=now)
    total = int(
        conn.execute("SELECT COUNT(*) FROM leaderboard_rows").fetchone()[0]
    )
    return RebuildReport(
        bench_rows_written=bench_written,
        cockpit_rows_written=cockpit_written,
        total_rows=total,
    )


def _rebuild_bench_anchored(conn: sqlite3.Connection, *, fetched_at: str) -> int:
    """Promote every scored ``bench_results`` row into ``leaderboard_rows``.

    Skips rows where ``core_pass_rate`` is NULL — those are evidence
    placeholders the M2 importer registered for completeness but that
    don't carry a numeric pass-rate (e.g., the serving-lane bakeoff which
    measured warm-time + tok/s but recorded pass-rate qualitatively in
    the prose).
    """
    written = 0
    rows = conn.execute(
        "SELECT bench_slug, variant_label, core_pass_rate, "
        "       tok_per_sec, p50_s, p95_s, wall_mean_s "
        "FROM bench_results "
        "WHERE core_pass_rate IS NOT NULL"
    ).fetchall()
    for r in rows:
        bench_id = r["bench_slug"]
        variant = r["variant_label"]
        # If the M2 importer already registered a leaderboard_row for this
        # (bench_id, variant) under its own suffix convention (e.g.
        # ``::brain-bakeoff`` for the canonical brain-bakeoff seed), reuse
        # that lane_id so the rebuild updates the row in place instead of
        # inserting a duplicate under a different lane_id suffix.
        existing = conn.execute(
            "SELECT lane_id FROM leaderboard_rows "
            "WHERE bench_id=? AND lane_id LIKE ?",
            (bench_id, f"{variant}::%"),
        ).fetchone()
        if existing is not None:
            lane_id = existing["lane_id"]
        else:
            # Fresh derivation: bench-slug suffix gives a stable id without
            # colliding across benches that share variant labels (e.g.
            # both vertical-router and bench-X could have a "v1" variant).
            lane_id = f"{variant}::{bench_id.split(':')[0]}"
            # Upsert a placeholder lanes row so the FK holds. INSERT OR
            # IGNORE preserves a richer lane row written by the importer.
            conn.execute(
                "INSERT OR IGNORE INTO lanes "
                "(id, kind, model, port, base_url, manifest_slug, recommended) "
                "VALUES (?, 'BenchVariant', ?, 0, '', NULL, 0)",
                (lane_id, variant),
            )
        conn.execute(
            "INSERT OR REPLACE INTO leaderboard_rows "
            "(bench_id, lane_id, manifest_slug, n_runs, mean_score, "
            " median_tok_per_s, mean_ttft_ms, human_pref_winrate, last_run_at) "
            "VALUES (?, ?, NULL, 1, ?, ?, NULL, NULL, ?)",
            (
                bench_id,
                lane_id,
                float(r["core_pass_rate"]),
                float(r["tok_per_sec"]) if r["tok_per_sec"] is not None else None,
                fetched_at,
            ),
        )
        written += 1
    conn.commit()
    return written


def _aggregate_cockpit_rows(
    conn: sqlite3.Connection, *, include_chat: bool = False
) -> list[dict[str, Any]]:
    """Per-``(bench_id, lane_id)`` live-cockpit leaderboard aggregates.

    **Pure read** — computes the ``leaderboard_rows`` shape from the live
    ``compare_*`` (and, when ``include_chat``, ``chat_*``) tables WITHOUT
    writing anything. Shared by the CLI rebuild (:func:`_rebuild_cockpit_runs`,
    compare-only so the public mirror snapshot stays byte-stable) and the live
    API query (``store.leaderboard_live``). SELECTs only metric/id/timestamp
    columns — never ``prompt`` / ``content`` / ``reasoning`` / ``note``.

    ``bench_id`` is ``f"cockpit:{rubric_id}"`` for scored compare/chat rows and
    ``"cockpit:chat"`` for unscored chat turns (throughput-only — ``mean_score``
    is ``None``). ``side`` is folded into the lane id so an A-lane that shows up
    on both sides across runs is one row, not two. ``last_run_at`` is the max
    run/score timestamp in each bucket.
    """
    by_pair: dict[tuple[str, str], list[dict[str, Any]]] = {}

    def _push(bench_id, lane_id, *, score, tok, ttft, wins, n_prefs, ts, cost=None):
        by_pair.setdefault((bench_id, lane_id), []).append(
            {
                "score": score,
                "tok_per_s": tok,
                "ttft_ms": ttft,
                "wins": wins,
                "n_prefs": n_prefs,
                "ts": ts,
                "cost": cost,  # M9 (Bet 6): per-run cost_usd, None when unpriced
            }
        )

    # --- compare runs: one entry per publishable run × side that has a score.
    runs = conn.execute(
        "SELECT id, rubric_id, lane_a_id, lane_b_id, created_at "
        "FROM compare_runs WHERE publishable=1"
    ).fetchall()
    for run in runs:
        for side, lane_id in (("A", run["lane_a_id"]), ("B", run["lane_b_id"])):
            score_row = conn.execute(
                "SELECT total, scored_at FROM rubric_scores "
                "WHERE compare_run_id=? AND side=? AND rubric_id=?",
                (run["id"], side, run["rubric_id"]),
            ).fetchone()
            if score_row is None:
                # Mid-flight or canned compare without scored output; skip —
                # the row appears once its score lands.
                continue
            resp_row = conn.execute(
                "SELECT tok_per_s, ttft_ms, cost_usd FROM compare_responses "
                "WHERE compare_run_id=? AND side=?",
                (run["id"], side),
            ).fetchone()
            prefs = conn.execute(
                "SELECT winner FROM human_prefs WHERE compare_run_id=?",
                (run["id"],),
            ).fetchall()
            wins = sum(
                1.0 if p["winner"] == side else (0.5 if p["winner"] == "tie" else 0.0)
                for p in prefs
            )
            _push(
                f"cockpit:{run['rubric_id']}",
                lane_id,
                score=float(score_row["total"]),
                tok=float(resp_row["tok_per_s"]) if resp_row and resp_row["tok_per_s"] is not None else None,
                ttft=float(resp_row["ttft_ms"]) if resp_row and resp_row["ttft_ms"] is not None else None,
                cost=float(resp_row["cost_usd"]) if resp_row and resp_row["cost_usd"] is not None else None,
                wins=wins,
                n_prefs=len(prefs),
                ts=max([t for t in (run["created_at"], score_row["scored_at"]) if t] or [run["created_at"]]),
            )

    # --- chat turns (live-only): every assistant turn is a throughput sample
    #     for its lane; quality folds in when a rubric score is attached.
    if include_chat:
        turns = conn.execute(
            "SELECT t.id AS turn_id, t.tok_per_s AS tok_per_s, "
            "       t.ttft_ms AS ttft_ms, t.created_at AS created_at, "
            "       t.cost_usd AS cost_usd, "
            "       s.lane_id AS lane_id "
            "FROM chat_turns t JOIN chat_sessions s ON s.id = t.session_id "
            "WHERE t.role='assistant'"
        ).fetchall()
        for t in turns:
            score_row = conn.execute(
                "SELECT total, rubric_id, scored_at FROM rubric_scores "
                "WHERE chat_turn_id=? ORDER BY scored_at DESC LIMIT 1",
                (t["turn_id"],),
            ).fetchone()
            if score_row is not None:
                bench_id = f"cockpit:{score_row['rubric_id']}"
                score: float | None = float(score_row["total"])
                ts = max([x for x in (t["created_at"], score_row["scored_at"]) if x] or [t["created_at"]])
            else:
                bench_id = "cockpit:chat"  # throughput-only bucket
                score = None
                ts = t["created_at"]
            _push(
                bench_id,
                t["lane_id"],
                score=score,
                tok=float(t["tok_per_s"]) if t["tok_per_s"] is not None else None,
                ttft=float(t["ttft_ms"]) if t["ttft_ms"] is not None else None,
                cost=float(t["cost_usd"]) if t["cost_usd"] is not None else None,
                wins=0.0,
                n_prefs=0,
                ts=ts,
            )

    rows: list[dict[str, Any]] = []
    for (bench_id, lane_id), entries in by_pair.items():
        scores = [e["score"] for e in entries if e["score"] is not None]
        tokps = [e["tok_per_s"] for e in entries if e["tok_per_s"] is not None]
        ttfts = [e["ttft_ms"] for e in entries if e["ttft_ms"] is not None]
        total_prefs = sum(e["n_prefs"] for e in entries)
        total_wins = sum(e["wins"] for e in entries)
        winrate: float | None = None
        if total_prefs >= 5:  # spec §4.4 — render only after ≥5 prefs
            winrate = total_wins / total_prefs
        ts_vals = [e["ts"] for e in entries if e["ts"]]
        # M9 (Bet 6): aggregate cost + the $/quality-point third axis. Cost
        # rows that are None (local/unpriced runs) drop out of the AVG; a pair
        # with no priced runs gets mean_cost_usd=None. ``cost_per_quality_point``
        # = mean_cost_usd / mean_score, guarded on mean_score>0 (M9-4); a local
        # lane lands 0.0 here and renders "$0 (local)" via fieldkit.cost.
        costs = [e["cost"] for e in entries if e["cost"] is not None]
        mean_score_val = (sum(scores) / len(scores)) if scores else None
        mean_cost_usd = (sum(costs) / len(costs)) if costs else None
        cost_per_quality_point: float | None = None
        if mean_cost_usd is not None and mean_score_val and mean_score_val > 0:
            cost_per_quality_point = mean_cost_usd / mean_score_val
        rows.append(
            {
                "bench_id": bench_id,
                "lane_id": lane_id,
                "manifest_slug": None,
                "n_runs": len(entries),
                "mean_score": mean_score_val,
                "median_tok_per_s": _median(tokps) if tokps else None,
                "mean_ttft_ms": (sum(ttfts) / len(ttfts)) if ttfts else None,
                "human_pref_winrate": winrate,
                "last_run_at": max(ts_vals) if ts_vals else None,
                "mean_cost_usd": mean_cost_usd,
                "cost_per_quality_point": cost_per_quality_point,
            }
        )
    return rows


def _rebuild_cockpit_runs(conn: sqlite3.Connection, *, fetched_at: str) -> int:
    """Promote publishable compare runs into ``leaderboard_rows``.

    Thin wrapper over :func:`_aggregate_cockpit_rows` (compare-only — chat is
    live-API-only and never enters the public mirror snapshot). Writes
    ``fetched_at`` for ``last_run_at`` to preserve the existing byte-stable CLI
    output; the live query keeps the data-derived ``last_run_at`` instead.
    """
    rows = _aggregate_cockpit_rows(conn, include_chat=False)
    for r in rows:
        conn.execute(
            "INSERT OR REPLACE INTO leaderboard_rows "
            "(bench_id, lane_id, manifest_slug, n_runs, mean_score, "
            " median_tok_per_s, mean_ttft_ms, human_pref_winrate, last_run_at, "
            " mean_cost_usd, cost_per_quality_point) "
            "VALUES (?, ?, NULL, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                r["bench_id"],
                r["lane_id"],
                r["n_runs"],
                r["mean_score"],
                r["median_tok_per_s"],
                r["mean_ttft_ms"],
                r["human_pref_winrate"],
                fetched_at,
                r.get("mean_cost_usd"),  # M9 (Bet 6) — aggregate cost
                r.get("cost_per_quality_point"),
            ),
        )
    conn.commit()
    return len(rows)


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------


def export_publishable_slice(
    store: ArenaStore,
    out_dir: str | os.PathLike[str] = "src/data/arena-mirror",
    *,
    allow_empty: bool = False,
    rebuild: bool = True,
    repo_root: str | os.PathLike[str] | None = None,
) -> ExportReport:
    """Write the publishable slice of ``arena.db`` to ``out_dir/*.json``.

    The exporter reads ONLY columns listed in :data:`PUBLISHABLE_TABLES`.
    No code path here references :data:`FORBIDDEN_TABLES` or
    :data:`FORBIDDEN_COLUMNS` (those exist for the regression test to
    audit and for future maintainers to grep before touching the
    exporter).

    Parameters
    ----------
    store
        An open :class:`ArenaStore`. The caller is responsible for
        ``initialize()`` having been run.
    out_dir
        Target directory for the JSON files. If relative, resolved
        against ``repo_root`` (or the current working directory).
        Default: ``src/data/arena-mirror`` (the path the Astro build
        already reads at build time).
    allow_empty
        If False (default), refuse to write a zero-row leaderboard
        export. The guard exists to prevent accidentally blanking the
        public mirror when an upstream query goes wrong; operator opts
        out via ``--allow-empty`` on the CLI.
    rebuild
        If True (default), run :func:`rebuild_leaderboard` first.
        Set False if the caller has already rebuilt and wants the
        exporter to read the cached state.
    repo_root
        Optional repo-root override. Useful in tests to land mirror
        output under a temp tree.

    Returns
    -------
    ExportReport
        Counts + file paths for the CLI to render.

    Raises
    ------
    fieldkit.arena.PublishableSliceEmpty
        If ``allow_empty=False`` and both ``bench_rows`` + ``live_rows``
        would be empty.
    """
    # Local import to avoid an arena import cycle at module load time.
    from fieldkit.arena import PublishableSliceEmpty

    rebuild_report: RebuildReport | None = None
    if rebuild:
        rebuild_report = rebuild_leaderboard(store)

    conn = store.connect()
    warnings: list[str] = []

    # Read each allowlist table.
    table_rows: dict[str, list[dict[str, Any]]] = {}
    for table, cols in PUBLISHABLE_TABLES.items():
        col_list = ", ".join(cols)
        try:
            rs = conn.execute(f"SELECT {col_list} FROM {table}").fetchall()
        except sqlite3.OperationalError as exc:
            # Schema drift — table missing (test fixture, fresh DB).
            warnings.append(f"table {table} missing: {exc}")
            table_rows[table] = []
            continue
        table_rows[table] = [_row_to_dict(r, cols) for r in rs]

    bench_rows, live_rows = _split_leaderboard_rows(table_rows["leaderboard_rows"])

    if not allow_empty and not bench_rows and not live_rows:
        raise PublishableSliceEmpty(
            "Refusing to write empty leaderboard JSON over a possibly-"
            "non-empty prior file. Re-run with allow_empty=True to "
            "override (or --allow-empty on the CLI)."
        )

    generated_at = _utc_now_iso()
    payload: dict[str, Any] = {
        "generated_at": generated_at,
        "source": "fieldkit arena mirror (M6 exporter)",
        "schema_version": MIRROR_SCHEMA_VERSION,
        # Legacy alias: the M2 day-one cut shipped ``rows: [...]`` and the
        # /arena/ landing page reads ``leaderboard.rows``. Keep both pointing
        # at the bench-anchored slice so the existing consumer doesn't break.
        "rows": bench_rows,
        "bench_rows": bench_rows,
        "live_rows": live_rows,
        "compare_runs": table_rows.get("compare_runs", []),
        "compare_responses": table_rows.get("compare_responses", []),
        "rubric_scores": table_rows.get("rubric_scores", []),
        "human_prefs": table_rows.get("human_prefs", []),
        "lanes": table_rows.get("lanes", []),
        # M9 (Bet 6): the price snapshot so the public $/task is reconstructable.
        "openrouter_price_snapshot": table_rows.get(
            "openrouter_price_snapshot", []
        ),
        # M10 (Bet 5): the public RAG-eval trend (aggregate recall@k/faithfulness
        # per index version — no prompts, no chunk text; M10-10).
        "rag_eval_runs": table_rows.get("rag_eval_runs", []),
    }

    # Atomic staged write. _staging/ → final path under os.replace.
    resolved_out = _resolve_out_dir(out_dir, repo_root=repo_root)
    staging_dir = resolved_out / "_staging"
    resolved_out.mkdir(parents=True, exist_ok=True)
    staging_dir.mkdir(parents=True, exist_ok=True)

    final_path = resolved_out / "leaderboard.json"
    staged_path = staging_dir / "leaderboard.json"
    _atomic_write_json(staged_path, final_path, payload)

    return ExportReport(
        out_dir=str(resolved_out),
        files_written=(str(final_path),),
        bench_row_count=len(bench_rows),
        live_row_count=len(live_rows),
        compare_run_count=len(payload["compare_runs"]),
        rubric_score_count=len(payload["rubric_scores"]),
        human_pref_count=len(payload["human_prefs"]),
        lane_count=len(payload["lanes"]),
        generated_at=generated_at,
        rebuild_report=rebuild_report,
        warnings=tuple(warnings),
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _row_to_dict(row: sqlite3.Row, cols: Sequence[str]) -> dict[str, Any]:
    """Convert a sqlite3.Row to a plain dict over the allowlist columns
    (in declaration order). Defensive against schema drift — a missing
    column lands as ``None``.
    """
    out: dict[str, Any] = {}
    for c in cols:
        try:
            out[c] = row[c]
        except (IndexError, KeyError):
            out[c] = None
    return out


def _split_leaderboard_rows(
    rows: Sequence[Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Split a sequence of leaderboard rows into (bench_anchored, live_cockpit).

    Live-cockpit rows have ``bench_id`` starting with ``"cockpit:"``;
    everything else is bench-anchored.
    """
    bench: list[dict[str, Any]] = []
    live: list[dict[str, Any]] = []
    for r in rows:
        target = live if str(r.get("bench_id", "")).startswith("cockpit:") else bench
        target.append(dict(r))
    return bench, live


def _resolve_out_dir(
    out_dir: str | os.PathLike[str], *, repo_root: str | os.PathLike[str] | None
) -> Path:
    p = Path(os.fspath(out_dir))
    if p.is_absolute():
        return p
    base = Path(os.fspath(repo_root)) if repo_root else Path.cwd()
    return (base / p).resolve()


def _atomic_write_json(staging_path: Path, final_path: Path, payload: dict[str, Any]) -> None:
    """Write ``payload`` to ``staging_path`` (fsync), then atomically
    rename onto ``final_path``. Mirrors the Mac sync contract per
    ``[[reference_sync_workflow_nfs_mount]]``.
    """
    staging_path.parent.mkdir(parents=True, exist_ok=True)
    # Use indent=2 so the operator can grep the file straight from disk
    # without piping through jq, AND so the regression test's substring
    # scan finds keys on independent lines.
    data = json.dumps(payload, indent=2, sort_keys=False)
    with open(staging_path, "w", encoding="utf-8") as fh:
        fh.write(data)
        fh.write("\n")
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(staging_path, final_path)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _median(values: Iterable[float]) -> float:
    xs = sorted(values)
    n = len(xs)
    if n == 0:
        raise ValueError("median of empty sequence")
    if n % 2 == 1:
        return xs[n // 2]
    return 0.5 * (xs[n // 2 - 1] + xs[n // 2])
