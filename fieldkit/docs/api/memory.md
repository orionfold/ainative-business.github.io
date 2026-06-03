---
module: memory
title: fieldkit.memory
summary: The Arena M10 recall layer (Bet 5) — MemoryIndex, KnowledgeCard, Provenance, ingest_sources, coverage_report, resolve_qa_set. A managed, multi-source, provenance-aware index over the Second Brain, with an article_index ⋈ index coverage report and an eval-gated re-index.
order: 15
---

## What it is

The **recall layer** — Bet 5 of the "machine that builds machines" roadmap
(`_FLOWS/the-machine-that-builds-machines.md` §3), shipped as **Arena M10**
(`_SPECS/spark-arena-v1.md` §14). The Second Brain promoted from a manual,
prose-only, externally-scripted index into a **managed, multi-source,
evaluated, provenance-tagged** one the operator drives from the cockpit.

M10 is **connective tissue, not greenfield.** The retrieval stack
(`fieldkit.rag.Pipeline`, pgvector `blog_chunks`), the eval harness
(`rag-eval-work/`), and the query surface (`second-brain-mcp`, the harness
`ask_second_brain` tool) all already exist. What was missing — and why the
index silently rotted to **12/63 articles** at the 2026-06-02 roadmap harvest —
is a managed, version-controlled, *multi-source* ingest with **provenance** so
retrieval can filter by trust tier. `fieldkit.memory` is that layer.

It owns the canonical `blog_chunks` shape (`slug · chunk_idx · text ·
embedding` + the provenance card) so the qa-eval gold set (keyed on
`(slug, chunk_idx)`) and the standalone `second-brain-mcp` server keep working
unchanged. The word-based 900w/150-overlap chunker is ported verbatim from the
retired `rag-eval-work/ingest_blog.py` (decision M10-2 — that script is retired,
its logic adopted here as the **one version-controlled ingest path**).

The module is **store-agnostic + injectable**: `coverage_report` accepts an
`ArenaStore` (anything with `.articles()`) and the `MemoryIndex` embed/db
touchpoints take injectable hooks, so the deterministic logic unit-tests
without a live pgvector / embedder. Per `feedback_llm_skill_pattern` it is
deterministic Python only — no `anthropic`, no `claude_agent_sdk`, no LLM call;
embeddings hit the local NIM endpoint via stdlib `urllib`.

## The four surfaces

1. **Provenance card** — `Provenance` + `KnowledgeCard`: every chunk carries
   `source · kind · doc_date · verdict · link`, so a Spark-*measured* number and
   an external-*claimed* one are not interchangeable (M10-3/4).
2. **The managed index** — `MemoryIndex`: the pgvector handle. `ensure_schema()`
   runs the idempotent provenance ALTER (backfill-safe, R21); `query()` is the
   single provenance-filtered backend (M10-9); `indexed_slugs()` /
   `chunk_counts()` / `provenance_backfilled()` feed the coverage join.
3. **Multi-source ingest** — `ingest_sources` + the `collect_article_sources` /
   `collect_scout_sources` / `collect_lineage_sources` readers (M10-3): prose +
   internal experiment memory + external research, one provenance card each.
4. **Coverage + eval** — `coverage_report` (the `article_index` ⋈ index diff,
   M10-8) and `resolve_qa_set` (the version-controlled gold set the `rag_eval`
   job + its promotion gate score against, M10-6/12).

## Public API

```python
from fieldkit.memory import (
    MemoryIndex,
    KnowledgeCard,
    Provenance,
    ingest_sources,
    coverage_report,
    resolve_qa_set,
    MemoryError,
)
```

### `Provenance`

The trust card stamped on every chunk (M10-4). `source` is a `SOURCE_CLASSES`
member (`article` highest trust → `scout` / `deep_research` lowest); `kind` the
doc kind within that class; `doc_date`, `verdict` (a scout feasibility or a
lineage `keep`/`discard`), and `link`. The constructor guards `source` against
the known set; `as_row()` returns the five values in column order.

### `KnowledgeCard`

One source document (`slug`, `text`) plus its `Provenance`, handed to
`ingest_sources`. A card maps 1→N chunks, each inheriting the card's provenance.

### `MemoryIndex`

The managed pgvector handle for the canonical `blog_chunks` index. `pg_dsn` /
`embed_url` default to the live Spark Second Brain but are env-overridable
(`SECOND_BRAIN_PG_DSN` / `EMBED_URL`). Key methods: `ensure_schema()` (CREATE +
the idempotent provenance ALTER, R21), `create_indexes()`, `write_chunks()` /
`replace_slugs()` (the rebuild body), `indexed_slugs()` / `chunk_counts()` /
`provenance_backfilled()` (coverage inputs), and `query(text, *, top_k,
sources)` — the single provenance-filtered backend (cosine-only on GB10, M10-7;
`RERANK_URL` self-enables a `-dgx-spark` reranker when one lands). DB/embed
errors are wrapped in `MemoryError` so callers degrade cleanly.

### `ingest_sources(index, cards, *, words_per_chunk=900, overlap=150, embed_batch=16)`

The one version-controlled ingest path (M10-2, replaces `ingest_blog.py`).
Chunks + embeds + upserts `cards` into `index` with provenance; each card is
replaced cleanly (its old chunks deleted first) so a re-ingest is idempotent and
backfills provenance on legacy rows (R21). Returns
`{chunks_written, slugs, by_source}` for the `reindex_runs` row.

### `coverage_report(store, index=None, *, indexed_slugs=None, chunk_counts=None)`

The `article_index` ⋈ index freshness number (M10-8). Joins what *should* be
indexed (arena.db `article_index`, minus `upcoming`) against what *is* (the
index's distinct slug set) → `coverage_pct`, the `missing` (stale) /
`orphan` (non-prose) slug lists, and per-slug chunk counts. The silent 12/63
staleness becomes a standing, actionable number. Pass `indexed_slugs` /
`chunk_counts` directly to unit-test without a live db.

### `resolve_qa_set(qa_set=None)`

Resolves the version-controlled qa-eval gold set (M10-6/12): an explicit path →
`$ARENA_QA_SET` → the in-repo
`articles/rag-eval-ragas-and-nemo-evaluator/evidence/qa-eval.jsonl`. Raises
`MemoryError` with the paths it tried when none exist, so a `rag_eval` job can
never silently grade against nothing.

### `MemoryError`

Raised when an ingest / query / coverage / resolve operation cannot complete
(bad provenance source, unreachable index, missing gold set, …).

## Schema (pgvector `blog_chunks` + arena.db `user_version` 5 → 6)

The vector index stays in **pgvector** `blog_chunks`, extended with the
provenance columns (`source` / `kind` / `doc_date` / `verdict` / `link`) via
`MemoryIndex.ensure_schema()` — additive, non-destructive, backfilled by the
next re-ingest (R21). The **run bookkeeping** lands in **arena.db**
(`user_version 5→6`): `reindex_runs` (per-rebuild provenance — operator-private)
and `rag_eval_runs` (eval scores per index version — public-safe aggregates).

## The dispatcher jobs (M10-1)

`reindex` / `rag_eval` / `scout_ingest` are promoted from `JobKind` named stubs
into `JobKind.DISPATCHABLE`. The dispatcher runs them through the same
`fieldkit.harness` MCP surface M8 established (`reindex_memory` /
`rag_eval_index` / `scout_ingest` tools), inheriting the containment posture. A
`rag_eval` rebuild that drops `recall@k` below the prior cosine-only score is
flagged `promote=False` (the M10-6 promotion gate, like-for-like per R22).

## Mirror safety

`rag_eval_runs` *aggregate scores* (recall@k, faithfulness — no prompts, no
chunk text) are on `mirror.PUBLISHABLE_TABLES` for the public RAG-eval trend.
`reindex_runs` (its `source_set` can name internal slugs) and any chunk-text
path stay on `mirror.FORBIDDEN_TABLES`; a sentinel in
`tests/arena/test_mirror_does_not_leak.py` guards the knowledge path (M10-10,
the R13-family hard gate).

## See also

- `fieldkit.rag` — the underlying embed → pgvector → rerank pipeline.
- `fieldkit.arena` — the store (schema), jobs (dispatcher), and mirror (export).
- `_SPECS/spark-arena-v1.md` §14 — the M10 locked decisions + as-built map.
