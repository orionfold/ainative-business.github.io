# Copyright 2026 Manav Sehgal
# SPDX-License-Identifier: Apache-2.0
"""`ArenaStore` — synchronous SQLite store for the cockpit.

**M2 surface.** Per spec §4.8 + the M2 retroactive-load inventory (§7), this
module owns the on-disk shape of `~/.fieldkit/arena.db` — schema creation,
upserts, and the small handful of read queries the M2 importer + M6 mirror
exporter need. M3+ adds the async `aiosqlite` adapter inside the FastAPI
sidecar; this module stays sync-stdlib-only because the M2 importer is a
one-shot batch and tests should not require async fixtures.

**Why two SQLite paths.** Sync via `sqlite3` here for the importer, future
mirror exporter, and CLI smoke; async via `aiosqlite` in `server.py` for the
SSE handlers (avoids blocking the event loop on the operator's chat
stream). Same database file; SQLite handles the concurrency via WAL.

Schema lives in `_SCHEMA_SQL` as one DDL string so a future migration can
`PRAGMA user_version` against it. The schema is **additive vs spec §4.8** —
the published v0.1 schema (lanes, chat_*, compare_*, rubric_scores,
leaderboard_rows, human_prefs, eval_runs) is mirrored verbatim; the M2 import
adds four data-only tables (`bench_results`, `article_index`, `hf_meta`,
`notebook_export`) called out in §7 but not given explicit `CREATE TABLE`
syntax in the spec. None of the additive tables carry chat content; M6's
mirror allowlist remains the leak-proof guarantor.

Per `feedback_llm_skill_pattern`: deterministic Python only. No `anthropic`
import, no `claude_agent_sdk` import, no LLM call.
"""

from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any, Iterable, Iterator, Mapping, Sequence

from fieldkit.arena import DEFAULT_ARENA_DB

__all__ = [
    "ArenaStore",
    "DEFAULT_DB_PATH",
    "USER_VERSION",
]

#: Schema version pin. Bump when a CREATE TABLE shape changes incompatibly;
#: until then additive tables can land without a bump (the importer uses
#: ``CREATE TABLE IF NOT EXISTS`` + ``INSERT OR REPLACE``).
USER_VERSION = 2

#: Expanded ``~/.fieldkit/arena.db``. Importable so tests can override the
#: env var without forcing a CLI roundtrip.
DEFAULT_DB_PATH = os.path.expanduser(DEFAULT_ARENA_DB)


# ---------------------------------------------------------------------------
# Schema DDL
# ---------------------------------------------------------------------------

# Spec §4.8 — verbatim where possible. Comments call out the M2 additions.
_SCHEMA_SQL = """
-- spec §4.8 — lanes / chat / compare / rubric / leaderboard / prefs / eval
CREATE TABLE IF NOT EXISTS lanes (
    id              TEXT PRIMARY KEY,
    kind            TEXT NOT NULL,
    model           TEXT NOT NULL,
    port            INTEGER NOT NULL,
    base_url        TEXT NOT NULL,
    start_script    TEXT,
    stop_script     TEXT,
    manifest_slug   TEXT,
    recommended     INTEGER NOT NULL DEFAULT 0,
    last_warm_at    TEXT,
    last_swap_at    TEXT,
    notes           TEXT
);

CREATE TABLE IF NOT EXISTS chat_sessions (
    id              TEXT PRIMARY KEY,
    lane_id         TEXT NOT NULL REFERENCES lanes(id),
    created_at      TEXT NOT NULL,
    rubric_id       TEXT,
    publishable     INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS chat_turns (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id      TEXT NOT NULL REFERENCES chat_sessions(id) ON DELETE CASCADE,
    ord             INTEGER NOT NULL,
    role            TEXT NOT NULL,
    content         TEXT NOT NULL,
    reasoning       TEXT,
    tokens_in       INTEGER,
    tokens_out      INTEGER,
    ttft_ms         REAL,
    tok_per_s       REAL,
    finish_reason   TEXT,
    created_at      TEXT NOT NULL,
    UNIQUE (session_id, ord)
);

CREATE TABLE IF NOT EXISTS compare_runs (
    id              TEXT PRIMARY KEY,
    prompt          TEXT NOT NULL,
    rubric_id       TEXT NOT NULL,
    lane_a_id       TEXT NOT NULL REFERENCES lanes(id),
    lane_b_id       TEXT NOT NULL REFERENCES lanes(id),
    created_at      TEXT NOT NULL,
    publishable     INTEGER NOT NULL DEFAULT 1,
    redacted_prompt TEXT
);

CREATE TABLE IF NOT EXISTS compare_responses (
    compare_run_id  TEXT NOT NULL REFERENCES compare_runs(id) ON DELETE CASCADE,
    side            TEXT NOT NULL CHECK (side IN ('A','B')),
    lane_id         TEXT NOT NULL REFERENCES lanes(id),
    content         TEXT NOT NULL,
    reasoning       TEXT,
    tokens_out      INTEGER,
    ttft_ms         REAL,
    tok_per_s       REAL,
    unified_peak_gb REAL,
    PRIMARY KEY (compare_run_id, side)
);

CREATE TABLE IF NOT EXISTS rubric_scores (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    compare_run_id  TEXT REFERENCES compare_runs(id) ON DELETE CASCADE,
    chat_turn_id    INTEGER REFERENCES chat_turns(id) ON DELETE CASCADE,
    side            TEXT,
    rubric_id       TEXT NOT NULL,
    total           REAL NOT NULL,
    checks_json     TEXT NOT NULL,
    scored_at       TEXT NOT NULL,
    CHECK ((compare_run_id IS NOT NULL) OR (chat_turn_id IS NOT NULL))
);

CREATE TABLE IF NOT EXISTS leaderboard_rows (
    bench_id           TEXT NOT NULL,
    lane_id            TEXT NOT NULL REFERENCES lanes(id),
    manifest_slug      TEXT,
    n_runs             INTEGER NOT NULL,
    mean_score         REAL NOT NULL,
    median_tok_per_s   REAL,
    mean_ttft_ms       REAL,
    human_pref_winrate REAL,
    last_run_at        TEXT NOT NULL,
    PRIMARY KEY (bench_id, lane_id)
);

CREATE TABLE IF NOT EXISTS human_prefs (
    id              TEXT PRIMARY KEY,
    compare_run_id  TEXT NOT NULL REFERENCES compare_runs(id) ON DELETE CASCADE,
    winner          TEXT NOT NULL CHECK (winner IN ('A','B','tie')),
    note            TEXT,
    created_at      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS eval_runs (
    id              TEXT PRIMARY KEY,
    bench_id        TEXT NOT NULL,
    lane_id         TEXT NOT NULL REFERENCES lanes(id),
    status          TEXT NOT NULL,
    enqueued_at     TEXT NOT NULL,
    started_at      TEXT,
    finished_at     TEXT,
    result_json     TEXT,
    arq_job_id      TEXT
);

-- M2 retroactive-load tables (spec §7). Data-only, no chat content; safe
-- to mirror under M6's allowlist (M6 enumerates a different subset).

CREATE TABLE IF NOT EXISTS bench_results (
    bench_slug          TEXT NOT NULL,
    variant_label       TEXT NOT NULL,
    core_pass_rate      REAL,
    consistency         REAL,
    runaway_rate        REAL,
    wall_mean_s         REAL,
    tok_per_sec         REAL,
    p50_s               REAL,
    p95_s               REAL,
    gpu_util_mean       REAL,
    unified_used_gb_max REAL,
    source_path         TEXT NOT NULL,
    fetched_at          TEXT NOT NULL,
    PRIMARY KEY (bench_slug, variant_label)
);

CREATE TABLE IF NOT EXISTS article_index (
    slug                        TEXT PRIMARY KEY,
    title                       TEXT NOT NULL,
    series                      TEXT,
    stage                       TEXT,
    status                      TEXT,
    customer_linked             INTEGER NOT NULL DEFAULT 0,
    published_at                TEXT,
    signature                   TEXT,
    summary                     TEXT,
    fieldkit_modules_json       TEXT,
    referenced_artifact_slugs_json TEXT,
    source_path                 TEXT NOT NULL,
    fetched_at                  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS hf_meta (
    repo_id         TEXT PRIMARY KEY,
    downloads       INTEGER,
    likes           INTEGER,
    last_modified   TEXT,
    has_card        INTEGER NOT NULL DEFAULT 0,
    fetched_at      TEXT NOT NULL,
    error           TEXT
);

CREATE TABLE IF NOT EXISTS notebook_export (
    file_path       TEXT PRIMARY KEY,
    artifact_slug   TEXT,
    role            TEXT,            -- 'builder' | 'user' | other
    kind            TEXT,            -- 'png' | 'html' | ...
    bytes           INTEGER,
    mtime           TEXT,
    fetched_at      TEXT NOT NULL
);

-- v0.2 (Lab) — operator-private annotations pinned to a Lab board card.
-- NEVER mirrored: `body` is freeform operator text. Added to the mirror
-- FORBIDDEN_TABLES allowlist + the test_mirror_does_not_leak.py regression.
CREATE TABLE IF NOT EXISTS lab_notes (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    card_id         TEXT NOT NULL,       -- board card this note is pinned to (slug or backlog id)
    lane            TEXT,                -- 'now' | 'next' | 'exploring' | other
    body            TEXT NOT NULL,       -- operator-private note text
    created_at      TEXT NOT NULL,
    updated_at      TEXT
);

-- v0.3 (Eval) — interactive eval-prompt scores. Reference-based grades of a
-- chat turn / compare side against a bench gold answer, with the scorer kind
-- and (for judge-backed kinds) the backend used. Deliberately NO ``lanes(id)``
-- FK: a scored lane may be the resident brain or an OpenRouter model that
-- isn't in the ``lanes`` registry. ``normalized`` is score/max in [0,1] so the
-- accuracy leaderboard can average across deterministic (0/1) and judge (0-5)
-- scorers; ``cross_vertical`` rows (a model run against a bench that isn't its
-- own) are excluded from own-bench rollups.
CREATE TABLE IF NOT EXISTS eval_scores (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    bench_id        TEXT NOT NULL,
    qid             TEXT NOT NULL,
    lane_id         TEXT NOT NULL,
    scorer_kind     TEXT NOT NULL,
    score           REAL,
    max_score       REAL NOT NULL DEFAULT 1.0,
    normalized      REAL,
    reference       TEXT,
    rationale       TEXT,
    judge_backend   TEXT,
    cross_vertical  INTEGER NOT NULL DEFAULT 0,
    source          TEXT NOT NULL,       -- 'chat' | 'compare'
    source_id       TEXT,                -- chat turn id, or compare run id (+ side)
    scored_at       TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_eval_scores_bench_lane ON eval_scores(bench_id, lane_id);
CREATE INDEX IF NOT EXISTS idx_lanes_manifest_slug ON lanes(manifest_slug);
CREATE INDEX IF NOT EXISTS idx_bench_results_slug ON bench_results(bench_slug);
CREATE INDEX IF NOT EXISTS idx_article_index_series ON article_index(series);
CREATE INDEX IF NOT EXISTS idx_notebook_export_slug ON notebook_export(artifact_slug);
CREATE INDEX IF NOT EXISTS idx_lab_notes_card ON lab_notes(card_id);
"""


# ---------------------------------------------------------------------------
# Store
# ---------------------------------------------------------------------------


class ArenaStore:
    """Synchronous SQLite access to ``~/.fieldkit/arena.db``.

    Construct once per CLI run; the connection is opened lazily on the
    first call to :meth:`initialize` / :meth:`connect` and closed by
    :meth:`close` (or by the ``with`` block).

    Schema creation is idempotent (every DDL is ``IF NOT EXISTS``) so
    re-running the M2 importer over an existing database is safe — that
    is the spec's idempotency gate.

    >>> store = ArenaStore("/tmp/arena.db")
    >>> store.initialize()
    >>> with store:
    ...     store.upsert_lane({"id": "moe-q4km", "kind": "LlamaServerLane",
    ...                        "model": "Qwen3-30B-A3B-Q4_K_M", "port": 8080,
    ...                        "base_url": "http://127.0.0.1:8080"})
    """

    def __init__(self, db_path: str | os.PathLike[str] | None = None) -> None:
        path = Path(os.path.expanduser(str(db_path or DEFAULT_DB_PATH)))
        self.db_path: Path = path
        self._conn: sqlite3.Connection | None = None

    # ---- lifecycle ----

    def connect(self) -> sqlite3.Connection:
        """Open the connection if needed, enable WAL + FKs, and return it."""
        if self._conn is not None:
            return self._conn
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        self._conn = conn
        return conn

    def close(self) -> None:
        if self._conn is not None:
            self._conn.commit()
            self._conn.close()
            self._conn = None

    def __enter__(self) -> "ArenaStore":
        self.connect()
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        """Convenience context: yields the conn, commits on success."""
        conn = self.connect()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise

    # ---- schema ----

    def initialize(self) -> None:
        """Create tables + indexes (idempotent) and pin ``PRAGMA user_version``."""
        conn = self.connect()
        with conn:
            conn.executescript(_SCHEMA_SQL)
            conn.execute(f"PRAGMA user_version={USER_VERSION}")

    @property
    def user_version(self) -> int:
        cur = self.connect().execute("PRAGMA user_version")
        row = cur.fetchone()
        return int(row[0]) if row else 0

    def table_names(self) -> list[str]:
        cur = self.connect().execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
        return [r[0] for r in cur.fetchall()]

    def count(self, table: str) -> int:
        """Row count for ``table``. Validates the table name against
        ``sqlite_master`` first to keep the f-string interpolation safe."""
        if table not in self.table_names():
            return 0
        cur = self.connect().execute(f"SELECT COUNT(*) FROM {table}")
        return int(cur.fetchone()[0])

    # ---- upserts (one per M2 table) ----

    def upsert_lane(self, row: Mapping[str, Any]) -> None:
        self._upsert("lanes", row, key=("id",))

    def upsert_bench_result(self, row: Mapping[str, Any]) -> None:
        self._upsert("bench_results", row, key=("bench_slug", "variant_label"))

    def upsert_article(self, row: Mapping[str, Any]) -> None:
        self._upsert("article_index", row, key=("slug",))

    def upsert_hf_meta(self, row: Mapping[str, Any]) -> None:
        self._upsert("hf_meta", row, key=("repo_id",))

    def upsert_notebook_export(self, row: Mapping[str, Any]) -> None:
        self._upsert("notebook_export", row, key=("file_path",))

    def upsert_leaderboard_row(self, row: Mapping[str, Any]) -> None:
        self._upsert("leaderboard_rows", row, key=("bench_id", "lane_id"))

    # ---- M4 chat helpers (operator-private, never mirrored) ----

    def upsert_chat_session(self, row: Mapping[str, Any]) -> None:
        """Insert or replace one ``chat_sessions`` row.

        Accepts a mapping or a :class:`ChatSessionRecord`. Idempotent on
        ``id``: re-running with the same id refreshes ``created_at`` /
        ``rubric_id`` / ``publishable`` without disturbing the FK from
        ``chat_turns`` (the rows hang off ``id`` not a surrogate).
        """
        self._upsert("chat_sessions", row, key=("id",))

    def append_chat_turn(self, row: Mapping[str, Any]) -> int:
        """Append one ``chat_turns`` row and return the rowid.

        Unlike the M2 upserts this is a strict INSERT — ``chat_turns`` is
        append-only and the ``(session_id, ord)`` UNIQUE constraint trips
        on duplicate writes (a programming error worth surfacing rather
        than silently masking with INSERT OR REPLACE).
        """
        if is_dataclass(row) and not isinstance(row, type):
            row = asdict(row)
        cols = list(row.keys())
        placeholders = ",".join("?" for _ in cols)
        col_list = ",".join(cols)
        sql = (
            f"INSERT INTO chat_turns ({col_list}) VALUES ({placeholders})"
        )
        conn = self.connect()
        cur = conn.execute(sql, [row[c] for c in cols])
        conn.commit()
        return int(cur.lastrowid or 0)

    def chat_turns(self, session_id: str) -> list[sqlite3.Row]:
        """All turns for a session, ordered by ``ord``. M4 read helper."""
        return list(
            self.connect().execute(
                "SELECT * FROM chat_turns WHERE session_id=? ORDER BY ord",
                [session_id],
            )
        )

    def chat_turn(self, turn_id: int) -> sqlite3.Row | None:
        """Fetch one ``chat_turns`` row by its rowid, or ``None``.

        Powers ``POST /api/chat/score`` — the eval scorer loads the persisted
        assistant turn's ``content`` (the answer channel, reasoning already
        split off) and grades it against the bench gold."""
        cur = self.connect().execute(
            "SELECT * FROM chat_turns WHERE id=?", [turn_id]
        )
        return cur.fetchone()

    def chat_session(self, session_id: str) -> sqlite3.Row | None:
        """Fetch one ``chat_sessions`` row by id, or ``None`` if missing."""
        cur = self.connect().execute(
            "SELECT * FROM chat_sessions WHERE id=?", [session_id]
        )
        return cur.fetchone()

    def recent_chat_sessions(self, limit: int = 8) -> list[sqlite3.Row]:
        """Most-recent N ``chat_sessions`` rows + their turn counts.

        Returns redacted metadata only — **never** reads
        ``chat_turns.content`` or ``chat_turns.reasoning``. Powers the
        v0.1.1 session switcher pill in ``ChatLane.jsx`` and the activity
        feed on the cockpit landing. Per spec §4.2 + §4.8 the redaction
        contract is about *mirror export*, not about local reads — but
        the listing endpoint deliberately keeps content out of the JSON
        so a sniffed loopback request can't leak prompts either.

        Each row carries: ``id``, ``lane_id``, ``created_at``,
        ``rubric_id``, ``publishable``, ``turn_count``.
        """
        return list(
            self.connect().execute(
                "SELECT cs.id AS id, "
                "       cs.lane_id AS lane_id, "
                "       cs.created_at AS created_at, "
                "       cs.rubric_id AS rubric_id, "
                "       cs.publishable AS publishable, "
                "       (SELECT COUNT(*) FROM chat_turns ct "
                "          WHERE ct.session_id = cs.id) AS turn_count "
                "  FROM chat_sessions cs "
                " ORDER BY cs.created_at DESC "
                " LIMIT ?",
                [int(limit)],
            )
        )

    def recent_compare_runs(self, limit: int = 8) -> list[sqlite3.Row]:
        """Most-recent N ``compare_runs`` rows + their A/B totals.

        Redacted: **never** reads ``compare_runs.prompt`` or
        ``compare_runs.redacted_prompt`` or ``compare_responses.content``
        / ``.reasoning``. Powers the v0.1.1 activity feed only. Each row
        carries: ``id``, ``lane_a_id``, ``lane_b_id``, ``rubric_id``,
        ``created_at``, ``a_score`` (nullable), ``b_score`` (nullable).
        """
        return list(
            self.connect().execute(
                "SELECT cr.id AS id, "
                "       cr.lane_a_id AS lane_a_id, "
                "       cr.lane_b_id AS lane_b_id, "
                "       cr.rubric_id AS rubric_id, "
                "       cr.created_at AS created_at, "
                "       (SELECT total FROM rubric_scores rs "
                "          WHERE rs.compare_run_id = cr.id AND rs.side='A' "
                "          ORDER BY rs.id DESC LIMIT 1) AS a_score, "
                "       (SELECT total FROM rubric_scores rs "
                "          WHERE rs.compare_run_id = cr.id AND rs.side='B' "
                "          ORDER BY rs.id DESC LIMIT 1) AS b_score "
                "  FROM compare_runs cr "
                " ORDER BY cr.created_at DESC "
                " LIMIT ?",
                [int(limit)],
            )
        )

    def recent_human_prefs(self, limit: int = 8) -> list[sqlite3.Row]:
        """Most-recent N ``human_prefs`` rows.

        Redacted: **never** reads ``human_prefs.note``. Powers the
        v0.1.1 activity feed only. Each row carries: ``id``,
        ``compare_run_id``, ``winner``, ``created_at``.
        """
        return list(
            self.connect().execute(
                "SELECT id, compare_run_id, winner, created_at "
                "  FROM human_prefs "
                " ORDER BY created_at DESC "
                " LIMIT ?",
                [int(limit)],
            )
        )

    # ---- M5 compare helpers (publishable by default — spec §4.3) ----

    def upsert_compare_run(self, row: Mapping[str, Any]) -> None:
        """Insert or replace one ``compare_runs`` header row.

        Idempotent on ``id``; the M5 sidecar generates a fresh id per
        compare so this is effectively an INSERT in practice. ``REPLACE``
        cascades through ``compare_responses`` / ``rubric_scores`` /
        ``human_prefs`` via their ON DELETE CASCADE constraints, so a
        replace is functionally a "redo this run" — useful in tests but
        not surfaced as a user-facing knob.
        """
        self._upsert("compare_runs", row, key=("id",))

    def upsert_compare_response(self, row: Mapping[str, Any]) -> None:
        """Insert or replace one ``compare_responses`` row.

        Composite key is ``(compare_run_id, side)``; INSERT OR REPLACE so
        a long-stream reconnect can re-emit the side without leaving a
        stale row behind. Side must be ``'A'`` or ``'B'`` (the SQL CHECK
        constraint enforces).
        """
        self._upsert(
            "compare_responses", row, key=("compare_run_id", "side")
        )

    def append_rubric_score(self, row: Mapping[str, Any]) -> int:
        """Append one ``rubric_scores`` row and return its rowid.

        Unlike the M2 upserts this is a strict INSERT — every scoring
        event is append-only so a multi-rubric workflow (M6+) can store
        independent scores under the same compare_run without clobbering
        the prior. The CHECK constraint guarantees one of
        ``compare_run_id`` / ``chat_turn_id`` is set.
        """
        if is_dataclass(row) and not isinstance(row, type):
            row = asdict(row)
        cols = list(row.keys())
        placeholders = ",".join("?" for _ in cols)
        col_list = ",".join(cols)
        sql = (
            f"INSERT INTO rubric_scores ({col_list}) VALUES ({placeholders})"
        )
        conn = self.connect()
        cur = conn.execute(sql, [row[c] for c in cols])
        conn.commit()
        return int(cur.lastrowid or 0)

    def append_eval_score(self, row: Mapping[str, Any]) -> int:
        """Append one ``eval_scores`` row and return its rowid.

        Append-only like ``append_rubric_score`` — re-scoring the same turn
        with a different judge backend keeps both rows for the forensic trail.
        """
        if is_dataclass(row) and not isinstance(row, type):
            row = asdict(row)
        cols = list(row.keys())
        placeholders = ",".join("?" for _ in cols)
        col_list = ",".join(cols)
        sql = f"INSERT INTO eval_scores ({col_list}) VALUES ({placeholders})"
        conn = self.connect()
        cur = conn.execute(sql, [row[c] for c in cols])
        conn.commit()
        return int(cur.lastrowid or 0)

    def eval_leaderboard(self, *, include_cross_vertical: bool = False) -> list[sqlite3.Row]:
        """Accuracy-per-(bench, lane) rollup over persisted eval scores.

        ``mean_normalized`` averages the ``[0,1]``-normalized scores so
        deterministic (0/1) and judge (0-5) grades land on one scale.
        Own-bench rollups exclude ``cross_vertical`` rows by default (a model
        run against a bench that isn't its own shouldn't pollute its accuracy
        number); pass ``include_cross_vertical=True`` to see everything."""
        where = "WHERE normalized IS NOT NULL"
        if not include_cross_vertical:
            where += " AND cross_vertical=0"
        return list(
            self.connect().execute(
                "SELECT bench_id, lane_id, "
                "       COUNT(*) AS n_runs, "
                "       AVG(normalized) AS mean_normalized, "
                "       MAX(scored_at) AS last_run_at "
                f"FROM eval_scores {where} "
                "GROUP BY bench_id, lane_id "
                "ORDER BY mean_normalized DESC, n_runs DESC"
            )
        )

    def leaderboard_live(self, *, include_chat: bool = True) -> list[dict[str, Any]]:
        """Live cockpit leaderboard rows, computed on-the-fly (no rebuild).

        Mirrors :meth:`eval_leaderboard`'s "read the live tables directly"
        contract, but for the cockpit family: aggregates publishable compare
        runs (and, by default, chat turns) into the ``leaderboard_rows`` shape
        via the same core the CLI rebuild uses, so the two never diverge. Rows
        sort by ``mean_score`` desc (``None`` — throughput-only chat — last),
        then ``median_tok_per_s`` desc. Column-allowlisted by construction —
        the aggregation SELECTs only metric/id/timestamp columns."""
        from fieldkit.arena.mirror import _aggregate_cockpit_rows

        rows = _aggregate_cockpit_rows(self.connect(), include_chat=include_chat)
        rows.sort(
            key=lambda r: (
                r["mean_score"] if r["mean_score"] is not None else -1.0,
                r["median_tok_per_s"] or 0.0,
            ),
            reverse=True,
        )
        return rows

    def eval_scores_for_source(self, source: str, source_id: str) -> list[sqlite3.Row]:
        """All eval-score rows for a chat turn / compare run, oldest first."""
        return list(
            self.connect().execute(
                "SELECT * FROM eval_scores WHERE source=? AND source_id=? "
                "ORDER BY id",
                [source, source_id],
            )
        )

    def append_human_pref(self, row: Mapping[str, Any]) -> None:
        """Insert one ``human_prefs`` row.

        Idempotent on ``id`` (the thumbs-up handler should generate a
        fresh uuid per click; replacing on collision is the safe
        default). Per spec §4.3 the M5 sidecar inserts the row but does
        **not** mutate the corresponding ``rubric_scores.total`` — human
        prefs are a separate signal that surfaces in the leaderboard as
        ``human_pref_winrate`` only at ≥5 prefs.
        """
        self._upsert("human_prefs", row, key=("id",))

    def compare_run(self, run_id: str) -> sqlite3.Row | None:
        """Fetch one ``compare_runs`` header row by id, or ``None``."""
        cur = self.connect().execute(
            "SELECT * FROM compare_runs WHERE id=?", [run_id]
        )
        return cur.fetchone()

    def compare_responses(self, run_id: str) -> list[sqlite3.Row]:
        """Both sides for a compare run, ordered ``A`` then ``B``."""
        return list(
            self.connect().execute(
                "SELECT * FROM compare_responses WHERE compare_run_id=? "
                "ORDER BY side",
                [run_id],
            )
        )

    def rubric_scores_for_run(self, run_id: str) -> list[sqlite3.Row]:
        """All rubric scores for a compare run, oldest first."""
        return list(
            self.connect().execute(
                "SELECT * FROM rubric_scores WHERE compare_run_id=? "
                "ORDER BY id",
                [run_id],
            )
        )

    def human_prefs_for_run(self, run_id: str) -> list[sqlite3.Row]:
        """All thumbs-up / thumbs-down rows for a compare run."""
        return list(
            self.connect().execute(
                "SELECT * FROM human_prefs WHERE compare_run_id=? "
                "ORDER BY created_at",
                [run_id],
            )
        )

    # ---- Lab notes (operator-private; v0.2) ----

    def append_lab_note(self, row: Mapping[str, Any]) -> int:
        """Insert one ``lab_notes`` row and return its rowid.

        Append-only operator annotation pinned to a Lab board card. The
        ``body`` is freeform operator text and is **never** mirrored — the
        table is on the M6 ``FORBIDDEN_TABLES`` allowlist and pinned by the
        ``test_mirror_does_not_leak.py`` regression. ``row`` carries
        ``card_id`` + ``body`` (required), optional ``lane`` + ``created_at``
        (caller stamps the time deterministically; we don't call ``now()``).
        """
        if is_dataclass(row) and not isinstance(row, type):
            row = asdict(row)
        cols = list(row.keys())
        placeholders = ",".join("?" for _ in cols)
        col_list = ",".join(cols)
        sql = f"INSERT INTO lab_notes ({col_list}) VALUES ({placeholders})"
        conn = self.connect()
        cur = conn.execute(sql, [row[c] for c in cols])
        conn.commit()
        return int(cur.lastrowid or 0)

    def lab_notes(self, card_id: str | None = None, limit: int = 200) -> list[sqlite3.Row]:
        """Operator's Lab notes, newest first. Optionally scoped to one card.

        Loopback-only read (the listing endpoint short-circuits on a public
        mirror host); the rows DO carry ``body`` because the redaction
        contract is about *mirror export*, not hiding the operator's own
        notes from themselves — same stance as the chat replay endpoint.
        """
        conn = self.connect()
        if card_id is None:
            return list(
                conn.execute(
                    "SELECT id, card_id, lane, body, created_at, updated_at "
                    "  FROM lab_notes ORDER BY id DESC LIMIT ?",
                    [int(limit)],
                )
            )
        return list(
            conn.execute(
                "SELECT id, card_id, lane, body, created_at, updated_at "
                "  FROM lab_notes WHERE card_id=? ORDER BY id DESC LIMIT ?",
                [card_id, int(limit)],
            )
        )

    def delete_lab_note(self, note_id: int) -> bool:
        """Delete one Lab note by id. Returns True if a row was removed."""
        conn = self.connect()
        cur = conn.execute("DELETE FROM lab_notes WHERE id=?", [int(note_id)])
        conn.commit()
        return cur.rowcount > 0

    # ---- internals ----

    def _upsert(
        self, table: str, row: Mapping[str, Any], *, key: Sequence[str]
    ) -> None:
        """One-shot autocommitting upsert. INSERT OR REPLACE keeps the
        idempotency math simple — re-running the importer over an existing
        DB produces identical row counts (M2 gate).

        Each `_upsert` call commits before returning so that a later
        :meth:`transaction` block can rollback its own DML cleanly without
        also unwinding rows the caller meant to keep. Callers that want to
        batch many upserts atomically should wrap them in a single
        :meth:`transaction` block + use raw SQL (not these helpers).
        """
        if is_dataclass(row) and not isinstance(row, type):
            row = asdict(row)
        cols = list(row.keys())
        placeholders = ",".join("?" for _ in cols)
        col_list = ",".join(cols)
        sql = f"INSERT OR REPLACE INTO {table} ({col_list}) VALUES ({placeholders})"
        conn = self.connect()
        conn.execute(sql, [row[c] for c in cols])
        conn.commit()

    # ---- reads (importer needs these for leaderboard derivation) ----

    def lanes(self) -> list[sqlite3.Row]:
        return list(self.connect().execute("SELECT * FROM lanes ORDER BY id"))

    def articles(self) -> list[sqlite3.Row]:
        return list(
            self.connect().execute(
                "SELECT * FROM article_index ORDER BY published_at DESC"
            )
        )

    def bench_results(self, bench_slug: str | None = None) -> list[sqlite3.Row]:
        conn = self.connect()
        if bench_slug:
            return list(
                conn.execute(
                    "SELECT * FROM bench_results WHERE bench_slug=? "
                    "ORDER BY variant_label",
                    [bench_slug],
                )
            )
        return list(
            conn.execute(
                "SELECT * FROM bench_results ORDER BY bench_slug, variant_label"
            )
        )

    def leaderboard_rows(self) -> list[sqlite3.Row]:
        return list(
            self.connect().execute(
                "SELECT * FROM leaderboard_rows "
                "ORDER BY bench_id, mean_score DESC, lane_id"
            )
        )

    # ---- bulk helpers ----

    def executemany(self, sql: str, params: Iterable[Sequence[Any]]) -> None:
        self.connect().executemany(sql, list(params))
