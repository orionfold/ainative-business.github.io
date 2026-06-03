# Copyright 2026 Manav Sehgal
# SPDX-License-Identifier: Apache-2.0
"""`fieldkit.memory` — the Arena **M10 recall layer**: a managed, multi-source,
provenance-aware knowledge index over the Second Brain.

Bet 5 of the MTBM roadmap (`_FLOWS/the-machine-that-builds-machines.md` §3) —
"the Second Brain as a control-plane-managed knowledge pipeline". M10 is
**connective tissue**, not greenfield: the retrieval stack
(`fieldkit.rag.Pipeline`, pgvector `blog_chunks`), the eval harness
(`rag-eval-work/`), and the query surface (`second-brain-mcp`, the harness
`ask_second_brain` tool) all already exist. What was missing — and why the
index silently rotted to 12/63 articles — is a *managed, version-controlled,
multi-source* ingest with **provenance** so retrieval can filter by trust tier.
This module is that layer.

It owns the canonical `blog_chunks` shape (slug · chunk_idx · text · embedding +
the M10-4 provenance card) so the eval gold set (keyed on `(slug, chunk_idx)`)
and the standalone `second-brain-mcp` server keep working unchanged. The
word-based 900w/150-overlap chunker is ported verbatim from the external
`rag-eval-work/ingest_blog.py` (decision M10-2 — that script is retired, its
logic adopted here as the one version-controlled ingest path).

Three surfaces:

- :class:`Provenance` + :class:`KnowledgeCard` — the M10-3/4 multi-source card.
  Every chunk carries ``source · kind · doc_date · verdict · link`` so a
  Spark-*measured* number and an external-*claimed* one are not interchangeable.
- :class:`MemoryIndex` — the managed pgvector handle: ``ensure_schema()`` (the
  M10-4 provenance ALTER, idempotent + backfill-safe per R21), ``indexed_slugs``
  / ``chunk_counts`` (the coverage join inputs), and a provenance-filtered
  ``query()`` (the single backend, M10-9). Network + db touchpoints are
  injectable so the module unit-tests without a live pgvector/embedder.
- :func:`ingest_sources` + :func:`coverage_report` + the ``collect_*`` source
  readers — the multi-source ingest (M10-3) and the ``article_index`` ⋈ index
  freshness number (M10-8) that makes the 12/63 staleness a standing metric.

Per `feedback_llm_skill_pattern`: deterministic Python only. No ``anthropic``
import, no ``claude_agent_sdk`` import, no LLM call. Embeddings go to the local
NIM endpoint via stdlib ``urllib`` (matching the ported script); pgvector via
``psycopg`` (already a `fieldkit` dep). The arena-store dependency is duck-typed
(anything with ``.connect()`` → a ``sqlite3.Connection``) so this module never
imports ``fieldkit.arena`` — the dispatcher seeds *this* module, not the reverse.
"""

from __future__ import annotations

import json
import os
import re
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence

__all__ = [
    "MemoryIndex",
    "KnowledgeCard",
    "Provenance",
    "ingest_sources",
    "coverage_report",
    "resolve_qa_set",
    "MemoryError",
]

#: Default pgvector DSN — the live Second Brain ``vectors`` db on the Spark.
#: Matches ``second-brain-mcp/server.py`` so the two share one backend (M10-9).
DEFAULT_PG_DSN = (
    "host=127.0.0.1 port=5432 dbname=vectors user=spark password=spark"
)

#: Default embedding endpoint — the local ``llama-nemotron-embed-1b-v2`` NIM on
#: ``:8001`` (bridge port-map, NOT host-net — collides with Triton gRPC 8001;
#: see ``[[reference_second_brain_reindex]]``).
DEFAULT_EMBED_URL = "http://127.0.0.1:8001/v1/embeddings"
DEFAULT_EMBED_MODEL = "nvidia/llama-nemotron-embed-1b-v2"
DEFAULT_EMBED_DIM = 1024

#: The canonical index table. The provenance columns (M10-4) extend it; the
#: ``(slug, chunk_idx)`` key is preserved so the qa-eval gold set still lines up.
DEFAULT_TABLE = "blog_chunks"

#: The word-based chunker constants, ported verbatim from the retired
#: ``rag-eval-work/ingest_blog.py`` so re-ingest keeps ``chunk_idx`` aligned
#: with the eval gold set (decision M10-2).
WORDS_PER_CHUNK = 900
CHUNK_OVERLAP = 150

#: Batch size for embedding passages — matches the ported script's NIM batch.
EMBED_BATCH = 16

#: The trust tiers (M10-4). A source class maps to a tier; the query filter
#: takes a set of source classes. ``article`` (published, reviewed) is the
#: highest; an external ``scout`` verdict the lowest.
SOURCE_CLASSES: tuple[str, ...] = (
    "article",
    "lineage",
    "eval",
    "scout",
    "deep_research",
)

#: The provenance columns added to ``blog_chunks`` (M10-4). Name → SQL type.
PROVENANCE_COLUMNS: tuple[tuple[str, str], ...] = (
    ("source", "text"),
    ("kind", "text"),
    ("doc_date", "text"),
    ("verdict", "text"),
    ("link", "text"),
)


#: The version-controlled qa-eval gold set (M10-12) — committed under the eval
#: article's ``evidence/``. The retired ``rag-eval-work/retrieve.py`` read it
#: from the now-gone ``nvidia-learn`` path; this is its in-repo canonical home.
QA_SET_EVIDENCE = (
    "articles/rag-eval-ragas-and-nemo-evaluator/evidence/qa-eval.jsonl"
)


class MemoryError(Exception):
    """Raised when an ingest / query / coverage operation cannot complete."""


def resolve_qa_set(qa_set: str | None = None) -> str:
    """Resolve the qa-eval gold set path (M10-6 / M10-12).

    Resolution order: an explicit ``qa_set`` path → ``$ARENA_QA_SET`` →
    the in-repo :data:`QA_SET_EVIDENCE` searched up from a few roots (the
    ``$ARENA_REPO_ROOT`` env, this package's repo, the cwd). Raises
    :class:`MemoryError` with the paths it tried when none exist — so a
    ``rag_eval`` job can't silently grade against nothing.
    """
    if qa_set:
        p = Path(os.path.expanduser(qa_set))
        if p.is_file():
            return str(p)
        raise MemoryError(f"qa-eval gold set not found at {p}")
    env = os.environ.get("ARENA_QA_SET")
    if env and Path(os.path.expanduser(env)).is_file():
        return str(Path(os.path.expanduser(env)))
    tried: list[str] = []
    roots = [
        os.environ.get("ARENA_REPO_ROOT"),
        # fieldkit/src/fieldkit/memory.py → repo root is parents[3]
        str(Path(__file__).resolve().parents[3]),
        os.getcwd(),
    ]
    for root in roots:
        if not root:
            continue
        cand = Path(root) / QA_SET_EVIDENCE
        tried.append(str(cand))
        if cand.is_file():
            return str(cand)
    raise MemoryError(
        "qa-eval gold set not found; set $ARENA_QA_SET or commit it at "
        f"{QA_SET_EVIDENCE}. Tried: {tried}"
    )


# ---------------------------------------------------------------------------
# Provenance card (M10-3 / M10-4)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Provenance:
    """The trust card stamped on every chunk (M10-4).

    ``source`` is a :data:`SOURCE_CLASSES` member (the trust tier the query
    filter keys on); ``kind`` is the doc kind within that class
    (``'article'`` → ``'deep-dive'`` / ``'product'``; ``'scout'`` →
    ``'paper'``); ``doc_date`` the publish/measure date; ``verdict`` an
    optional judgement (a scout feasibility ``'feasible'`` / ``'infeasible:X'``,
    or a lineage ``keep`` / ``discard``); ``link`` the canonical URL/path.
    """

    source: str
    kind: str = ""
    doc_date: str = ""
    verdict: str = ""
    link: str = ""

    def __post_init__(self) -> None:
        if self.source not in SOURCE_CLASSES:
            raise MemoryError(
                f"unknown provenance source {self.source!r}; "
                f"known: {SOURCE_CLASSES}"
            )

    def as_row(self) -> tuple[str, str, str, str, str]:
        """The five provenance values in :data:`PROVENANCE_COLUMNS` order."""
        return (self.source, self.kind, self.doc_date, self.verdict, self.link)


@dataclass(frozen=True)
class KnowledgeCard:
    """One source document plus its provenance, handed to :func:`ingest_sources`.

    ``slug`` is the index key (the ``blog_chunks.slug``); ``text`` the full
    body the chunker splits. A card maps 1→N chunks, each inheriting the same
    ``provenance``.
    """

    slug: str
    text: str
    provenance: Provenance


# ---------------------------------------------------------------------------
# Chunking + embedding (ported from ingest_blog.py — M10-2)
# ---------------------------------------------------------------------------


def chunk_words(
    text: str,
    *,
    words_per_chunk: int = WORDS_PER_CHUNK,
    overlap: int = CHUNK_OVERLAP,
) -> list[str]:
    """Word-based overlapping chunker — verbatim from the retired ingest script.

    Kept identical so a re-index converges ``chunk_idx`` with the qa-eval gold
    set (M10-2 / the promotion gate's like-for-like comparison).
    """
    words = text.split()
    out: list[str] = []
    step = words_per_chunk - overlap
    if step <= 0:
        raise MemoryError("overlap must be smaller than words_per_chunk")
    i = 0
    while i < len(words):
        out.append(" ".join(words[i : i + words_per_chunk]))
        i += step
    return out


def _embed_passages(
    texts: Sequence[str],
    *,
    embed_url: str,
    embed_model: str,
    embed_dim: int,
    input_type: str = "passage",
    timeout: float = 120.0,
) -> list[list[float]]:
    """Embed ``texts`` via the local NIM ``/v1/embeddings`` endpoint (stdlib)."""
    body = json.dumps(
        {
            "model": embed_model,
            "input": list(texts),
            "input_type": input_type,
            "encoding_format": "float",
            "truncate": "END",
            "dimensions": embed_dim,
        }
    ).encode()
    req = urllib.request.Request(
        embed_url, data=body, headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = json.loads(r.read())["data"]
    except Exception as exc:  # noqa: BLE001 — wrap network/parse errors uniformly
        raise MemoryError(f"embedding request to {embed_url} failed: {exc}") from exc
    return [d["embedding"] for d in data]


def _vec_literal(v: Sequence[float]) -> str:
    """pgvector text literal: ``[0.1,0.2,…]``."""
    return "[" + ",".join(f"{x:.7f}" for x in v) + "]"


# ---------------------------------------------------------------------------
# The managed index handle (M10-4 / M10-9)
# ---------------------------------------------------------------------------


@dataclass
class MemoryIndex:
    """Managed pgvector handle for the canonical ``blog_chunks`` index.

    Construction is cheap (no connection opened). ``pg_dsn`` / ``embed_url``
    default to the live Spark Second Brain but are env-overridable
    (``SECOND_BRAIN_PG_DSN`` / ``EMBED_URL``) so one backend serves the
    standalone server *and* the harness tool (M10-9). The ``embed_fn`` hook
    (``texts, input_type → vectors``) is injectable so the module unit-tests
    without a live embedder; left ``None`` it calls the NIM endpoint.
    """

    pg_dsn: str = field(default_factory=lambda: os.environ.get(
        "SECOND_BRAIN_PG_DSN", DEFAULT_PG_DSN
    ))
    embed_url: str = field(default_factory=lambda: os.environ.get(
        "EMBED_URL", DEFAULT_EMBED_URL
    ))
    embed_model: str = DEFAULT_EMBED_MODEL
    embed_dim: int = DEFAULT_EMBED_DIM
    table: str = DEFAULT_TABLE
    embed_fn: Callable[[Sequence[str], str], list[list[float]]] | None = None

    # -- pgvector plumbing (lazy psycopg import → import stays light) --------

    def _connect(self):  # type: ignore[no-untyped-def]
        try:
            import psycopg
        except ImportError as exc:  # pragma: no cover - psycopg is a hard dep
            raise MemoryError("psycopg is required for MemoryIndex") from exc
        try:
            return psycopg.connect(self.pg_dsn)
        except Exception as exc:  # noqa: BLE001
            raise MemoryError(f"pgvector connect failed ({self.pg_dsn}): {exc}") from exc

    def _embed(self, texts: Sequence[str], input_type: str) -> list[list[float]]:
        if self.embed_fn is not None:
            return self.embed_fn(texts, input_type)
        return _embed_passages(
            texts,
            embed_url=self.embed_url,
            embed_model=self.embed_model,
            embed_dim=self.embed_dim,
            input_type=input_type,
        )

    # -- Schema (M10-4: provenance card, idempotent + backfill-safe, R21) ---

    def ensure_schema(self) -> None:
        """Create ``blog_chunks`` (with provenance) if absent, else ALTER-add
        the provenance columns guarded against re-runs.

        A fresh db gets the full provenance-carrying CREATE; a live populated
        ``blog_chunks`` (pre-M10) gets each provenance column added via guarded
        ``ALTER TABLE ADD COLUMN`` — additive, non-destructive (R21). Existing
        rows keep NULL provenance until the next re-ingest backfills them; the
        coverage report exposes that fraction so the trust filter can gate on it.
        """
        cols = ",\n          ".join(f"{n} {t}" for n, t in PROVENANCE_COLUMNS)
        create = (
            "CREATE EXTENSION IF NOT EXISTS vector; "
            f"CREATE TABLE IF NOT EXISTS {self.table} ("
            "  id        bigserial PRIMARY KEY,"
            "  slug      text NOT NULL,"
            "  chunk_idx int  NOT NULL,"
            "  text      text NOT NULL,"
            f"  embedding vector({self.embed_dim}) NOT NULL,"
            f"  {cols},"
            "  UNIQUE (slug, chunk_idx)"
            ");"
        )
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(create)
            for name, sqltype in PROVENANCE_COLUMNS:
                cur.execute(
                    f"ALTER TABLE {self.table} "
                    f"ADD COLUMN IF NOT EXISTS {name} {sqltype}"
                )
            conn.commit()

    def create_indexes(self) -> None:
        """The HNSW + FTS + slug indexes (ported from ingest_blog.py).
        Idempotent (``IF NOT EXISTS``); cheap to call after a rebuild."""
        ddl = (
            f"CREATE INDEX IF NOT EXISTS {self.table}_hnsw "
            f"  ON {self.table} USING hnsw (embedding vector_cosine_ops) "
            f"  WITH (m=16, ef_construction=64); "
            f"CREATE INDEX IF NOT EXISTS {self.table}_fts "
            f"  ON {self.table} USING gin (to_tsvector('english', text)); "
            f"CREATE INDEX IF NOT EXISTS {self.table}_slug_idx "
            f"  ON {self.table} (slug); "
            f"CREATE INDEX IF NOT EXISTS {self.table}_source_idx "
            f"  ON {self.table} (source);"
        )
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(ddl)
            conn.commit()

    # -- Coverage inputs (M10-8) -------------------------------------------

    def indexed_slugs(self) -> set[str]:
        """The distinct ``slug`` set currently in the index (what *is* indexed)."""
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(f"SELECT DISTINCT slug FROM {self.table}")
            return {r[0] for r in cur.fetchall()}

    def chunk_counts(self) -> dict[str, int]:
        """``slug → chunk count`` for every indexed doc."""
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(f"SELECT slug, COUNT(*) FROM {self.table} GROUP BY slug")
            return {r[0]: int(r[1]) for r in cur.fetchall()}

    def provenance_backfilled(self) -> tuple[int, int]:
        """``(rows_with_source, total_rows)`` — the R21 backfill fraction.

        The pane gates the trust filter on this reaching 100% (a populated
        pre-M10 row has NULL ``source`` until re-ingest stamps it)."""
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                f"SELECT COUNT(source), COUNT(*) FROM {self.table}"
            )
            row = cur.fetchone()
        return (int(row[0] or 0), int(row[1] or 0))

    # -- Write (the rebuild body) ------------------------------------------

    def write_chunks(
        self, rows: Sequence[tuple[str, int, str, Sequence[float], Provenance]]
    ) -> int:
        """Upsert ``(slug, chunk_idx, text, embedding, provenance)`` rows.

        ``INSERT … ON CONFLICT (slug, chunk_idx) DO UPDATE`` so a re-ingest of
        the same slug overwrites in place (and backfills provenance on legacy
        rows, R21). Returns the row count written.
        """
        if not rows:
            return 0
        sql = (
            f"INSERT INTO {self.table} "
            "(slug, chunk_idx, text, embedding, source, kind, doc_date, verdict, link) "
            "VALUES (%s, %s, %s, %s::vector, %s, %s, %s, %s, %s) "
            "ON CONFLICT (slug, chunk_idx) DO UPDATE SET "
            "  text=EXCLUDED.text, embedding=EXCLUDED.embedding, "
            "  source=EXCLUDED.source, kind=EXCLUDED.kind, "
            "  doc_date=EXCLUDED.doc_date, verdict=EXCLUDED.verdict, "
            "  link=EXCLUDED.link"
        )
        with self._connect() as conn, conn.cursor() as cur:
            for slug, idx, text, vec, prov in rows:
                cur.execute(
                    sql,
                    (slug, idx, text, _vec_literal(vec), *prov.as_row()),
                )
            conn.commit()
        return len(rows)

    def replace_slugs(self, slugs: Iterable[str]) -> int:
        """Delete every chunk for ``slugs`` (so a re-ingest is a clean replace).
        Returns rows deleted. Used by per-source-class re-index."""
        slug_list = list(slugs)
        if not slug_list:
            return 0
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                f"DELETE FROM {self.table} WHERE slug = ANY(%s)", (slug_list,)
            )
            n = cur.rowcount
            conn.commit()
        return int(n or 0)

    # -- Query (the single provenance-aware backend, M10-9) ----------------

    def query(
        self,
        text: str,
        *,
        top_k: int = 5,
        sources: Sequence[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Provenance-filtered dense top-K (cosine ``<=>``).

        ``sources`` (a subset of :data:`SOURCE_CLASSES`) restricts the trust
        tier in the vector SQL itself (M10-4) — a measured number and a claimed
        one are not interchangeable. ``None`` searches every tier. Returns hits
        with ``slug · chunk_idx · dist · text`` and the full provenance card.
        Rerank is intentionally OFF (cosine-only is the GB10 measured baseline,
        M10-7); ``RERANK_URL`` self-enables one when a ``-dgx-spark`` reranker
        lands (the standalone server owns that path).
        """
        if top_k <= 0:
            return []
        qvec = self._embed([text], "query")[0]
        lit = _vec_literal(qvec)
        where = ""
        params: list[Any] = [lit, lit]
        if sources is not None:
            bad = [s for s in sources if s not in SOURCE_CLASSES]
            if bad:
                raise MemoryError(f"unknown source filter {bad}; known {SOURCE_CLASSES}")
            where = "WHERE source = ANY(%s) "
            params = [lit, list(sources), lit]
        sql = (
            "SELECT slug, chunk_idx, (embedding <=> %s::vector) AS dist, text, "
            "       source, kind, doc_date, verdict, link "
            f"FROM {self.table} {where}"
            "ORDER BY embedding <=> %s::vector LIMIT %s"
        )
        params.append(int(top_k))
        try:
            with self._connect() as conn, conn.cursor() as cur:
                cur.execute(sql, tuple(params))
                rows = cur.fetchall()
        except MemoryError:
            raise
        except Exception as exc:  # noqa: BLE001 — psycopg/UndefinedColumn etc.
            raise MemoryError(
                f"query failed (is the index provenance-migrated? "
                f"run ensure_schema): {exc}"
            ) from exc
        return [
            {
                "slug": r[0],
                "chunk_idx": r[1],
                "dist": float(r[2]),
                "text": r[3],
                "source": r[4],
                "kind": r[5],
                "doc_date": r[6],
                "verdict": r[7],
                "link": r[8],
            }
            for r in rows
        ]


# ---------------------------------------------------------------------------
# Multi-source ingest (M10-3)
# ---------------------------------------------------------------------------


def _strip_frontmatter(md: str) -> tuple[dict[str, str], str]:
    """Split YAML-ish frontmatter from a markdown body (ported from the script)."""
    if md.startswith("---"):
        end = md.find("\n---", 3)
        if end != -1:
            fm_block = md[3:end]
            body = md[end + 4 :]
            fm: dict[str, str] = {}
            for line in fm_block.strip().split("\n"):
                m = re.match(r"^(\w+):\s*(.*)$", line)
                if m:
                    fm[m.group(1)] = m.group(2).strip().strip("'\"")
            return fm, body
    return {}, md


def collect_article_sources(
    articles_dir: str | Path,
) -> list[KnowledgeCard]:
    """Read published ``articles/*/article.md`` into article :class:`KnowledgeCard`s.

    Skips ``_drafts`` and ``status: upcoming`` (matching the retired script's
    publish gate). Each card is tier ``article`` — the highest trust (published,
    reviewed prose). ``link`` points at the live ``/articles/<slug>/`` route.
    """
    base = Path(os.path.expanduser(str(articles_dir)))
    cards: list[KnowledgeCard] = []
    if not base.is_dir():
        return cards
    for d in sorted(p for p in base.iterdir() if p.is_dir()):
        if d.name == "_drafts":
            continue
        md_path = d / "article.md"
        if not md_path.is_file():
            continue
        fm, body = _strip_frontmatter(md_path.read_text())
        if fm.get("status") == "upcoming":
            continue
        cards.append(
            KnowledgeCard(
                slug=d.name,
                text=body,
                provenance=Provenance(
                    source="article",
                    kind=fm.get("series", "deep-dive") or "deep-dive",
                    doc_date=fm.get("date", ""),
                    link=f"/articles/{d.name}/",
                ),
            )
        )
    return cards


def collect_scout_sources(
    papers_json: str | Path,
) -> list[KnowledgeCard]:
    """Read a ``frontier-scout`` ``papers.json`` sidecar into scout cards (M10-3).

    Each scouted paper persists as ``"evaluated, <verdict>"`` so the system
    stops re-scouting what it already judged (the external twin of M8-4's
    re-scouting-amnesia cure). Tier ``scout`` — lowest trust (external claim,
    not Spark-measured). Tolerant of a missing/!shaped file (returns ``[]``).
    """
    path = Path(os.path.expanduser(str(papers_json)))
    cards: list[KnowledgeCard] = []
    if not path.is_file():
        return cards
    try:
        data = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return cards
    papers = data.get("papers", data) if isinstance(data, dict) else data
    if not isinstance(papers, list):
        return cards
    for p in papers:
        if not isinstance(p, Mapping):
            continue
        pid = str(p.get("id") or p.get("arxiv_id") or p.get("slug") or "").strip()
        if not pid:
            continue
        title = str(p.get("title", ""))
        summary = str(p.get("summary") or p.get("abstract") or "")
        verdict = str(p.get("feasibility") or p.get("verdict") or "")
        text = f"{title}\n\n{summary}\n\nFeasibility verdict: {verdict}".strip()
        cards.append(
            KnowledgeCard(
                slug=f"scout-{pid}",
                text=text,
                provenance=Provenance(
                    source="scout",
                    kind="paper",
                    doc_date=str(p.get("date", "")),
                    verdict=verdict,
                    link=str(p.get("url") or p.get("link") or ""),
                ),
            )
        )
    return cards


def collect_lineage_sources(
    cards_in: Sequence[Mapping[str, Any]],
) -> list[KnowledgeCard]:
    """Turn internal experiment-memory rows (lineage trials / eval summaries)
    into ``lineage`` cards (M10-3, the internal source class).

    Each input mapping carries ``slug``, ``text``, and optionally ``verdict``
    (a ``fieldkit.lineage.FailureLabel`` value — ``keep`` / ``discard`` / …)
    and ``date``. Tier ``lineage`` — internal, Spark-measured. Pure transform
    (no IO) so the dispatcher can feed it from any in-repo experiment record.
    """
    out: list[KnowledgeCard] = []
    for c in cards_in:
        slug = str(c.get("slug", "")).strip()
        text = str(c.get("text", "")).strip()
        if not slug or not text:
            continue
        out.append(
            KnowledgeCard(
                slug=slug if slug.startswith("lineage-") else f"lineage-{slug}",
                text=text,
                provenance=Provenance(
                    source="lineage",
                    kind=str(c.get("kind", "trial")),
                    doc_date=str(c.get("date", "")),
                    verdict=str(c.get("verdict", "")),
                    link=str(c.get("link", "")),
                ),
            )
        )
    return out


def ingest_sources(
    index: MemoryIndex,
    cards: Sequence[KnowledgeCard],
    *,
    words_per_chunk: int = WORDS_PER_CHUNK,
    overlap: int = CHUNK_OVERLAP,
    embed_batch: int = EMBED_BATCH,
) -> dict[str, Any]:
    """Chunk + embed + upsert ``cards`` into ``index`` with provenance (M10-3).

    The one version-controlled ingest path (M10-2 — replaces the external
    ``ingest_blog.py``). Each card is replaced cleanly (its old chunks deleted
    first) so re-ingest is idempotent and backfills provenance (R21). Returns
    ``{chunks_written, slugs, by_source}`` for the ``reindex_runs`` row.
    """
    if not cards:
        return {"chunks_written": 0, "slugs": [], "by_source": {}}
    index.ensure_schema()
    index.replace_slugs(c.slug for c in cards)

    rows: list[tuple[str, int, str, Sequence[float], Provenance]] = []
    by_source: dict[str, int] = {}
    # Embed in batches across all cards' chunks, preserving (slug, idx).
    pending_meta: list[tuple[str, int, str, Provenance]] = []
    pending_text: list[str] = []

    def flush() -> None:
        if not pending_text:
            return
        vecs = index._embed(pending_text, "passage")
        for (slug, idx, text, prov), vec in zip(pending_meta, vecs, strict=True):
            rows.append((slug, idx, text, vec, prov))
        pending_text.clear()
        pending_meta.clear()

    for card in cards:
        chunks = [c for c in chunk_words(
            card.text, words_per_chunk=words_per_chunk, overlap=overlap
        ) if c.strip()]
        by_source[card.provenance.source] = by_source.get(
            card.provenance.source, 0
        ) + len(chunks)
        for idx, passage in enumerate(chunks):
            pending_text.append(passage)
            pending_meta.append((card.slug, idx, passage, card.provenance))
            if len(pending_text) >= embed_batch:
                flush()
    flush()

    written = index.write_chunks(rows)
    index.create_indexes()
    return {
        "chunks_written": written,
        "slugs": sorted({c.slug for c in cards}),
        "by_source": by_source,
    }


# ---------------------------------------------------------------------------
# Coverage report (M10-8) — article_index ⋈ index
# ---------------------------------------------------------------------------


def coverage_report(
    store: Any,
    index: MemoryIndex | None = None,
    *,
    indexed_slugs: Sequence[str] | None = None,
    chunk_counts: Mapping[str, int] | None = None,
) -> dict[str, Any]:
    """The ``article_index`` ⋈ index freshness number (M10-8).

    Joins what *should* be indexed (arena.db ``article_index``, minus
    ``upcoming``) against what *is* (the index's distinct slug set). Returns
    counts + the indexed / stale-missing / orphan slug lists + per-slug chunk
    counts. The silent 12/63 staleness that bit the roadmap harvest becomes a
    visible, actionable number.

    ``index`` queries pgvector for the live slug set; pass ``indexed_slugs`` /
    ``chunk_counts`` directly to unit-test without a live db. ``store`` is an
    ``ArenaStore`` (its ``.articles()`` reader) or anything exposing one.
    """
    if indexed_slugs is None:
        if index is None:
            raise MemoryError("coverage_report needs an index or indexed_slugs")
        indexed = index.indexed_slugs()
        counts = index.chunk_counts()
    else:
        indexed = set(indexed_slugs)
        counts = dict(chunk_counts or {})

    should: dict[str, dict[str, Any]] = {}
    for art in store.articles():
        row = {k: art[k] for k in art.keys()} if hasattr(art, "keys") else dict(art)
        if str(row.get("status", "")).lower() == "upcoming":
            continue
        should[row["slug"]] = row

    should_slugs = set(should)
    # An indexed article-class slug not in article_index is an "orphan"
    # (e.g. a scout/lineage card — expected; surfaced, not flagged stale).
    missing = sorted(should_slugs - indexed)  # should be indexed, isn't (stale)
    present = sorted(should_slugs & indexed)
    orphan = sorted(indexed - should_slugs)  # in index, not an article (non-prose)

    return {
        "should_index": len(should_slugs),
        "indexed": len(present),
        "missing": missing,
        "missing_n": len(missing),
        "orphan": orphan,
        "orphan_n": len(orphan),
        "total_indexed_slugs": len(indexed),
        "chunk_counts": {s: counts.get(s, 0) for s in present},
        "coverage_pct": (
            round(100.0 * len(present) / len(should_slugs), 1)
            if should_slugs
            else 0.0
        ),
    }
