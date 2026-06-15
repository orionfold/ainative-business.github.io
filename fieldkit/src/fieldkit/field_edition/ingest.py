# Copyright 2026 Manav Sehgal
# SPDX-License-Identifier: Apache-2.0
"""`fieldkit field-edition` corpus ingest — the AD-FK-β fresh-box seed.

A fresh Field Edition box boots an **empty** pgvector, so the §8 Cortex gate
(retrieval recall + grounded contract) cannot pass until the Advisor demo
corpus is ingested. `up` has no repo checkout to read the 182 public sources
from, so the corpus rides the wheel as a **self-contained vendored pack**
(``data/advisor-corpus-pack-v01.jsonl.gz`` — built by
``scripts/field_edition/build_advisor_corpus_pack.py``): each source carries its
already-stripped body + the provenance metadata prefix line, exactly as the
recall-proof's ``ingest_corpus`` computed them. This module chunks→embeds→
upserts that pack **offline** into ``advisor_corpus_v01``, reproducing the chunks
the recall@5 0.977 proof was measured against — no network, no auth (AC-2).

Design (the deterministic-scripts invariant, same split as :mod:`up`):
:func:`plan_chunks` is **pure** — pack in, the ``(slug, chunk_idx, text,
provenance)`` rows out, no embedding and no I/O — so the chunking is
unit-testable against the proof's recipe. The embedding + pgvector upsert is the
only I/O (:func:`ingest_pack`, via :class:`fieldkit.memory.MemoryIndex`), and
:func:`index_for` builds the index pointed at the Field Edition stack.

Packaging decision (operator, 2026-06-15): **wheel-vendored** over HF/GitHub —
the bootstrap already pulls the fieldkit wheel, so the ~1 MB pack rides along
with zero extra fetches, fully offline, matching the existing frozen ``data/``
sets. The 2.6 GB GGUF is pulled from HF precisely because it is too big to
vendor; the corpus is the opposite case.
"""

from __future__ import annotations

import gzip
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Callable

from fieldkit.field_edition.compose import FieldEditionConfig, default_config

if TYPE_CHECKING:  # heavy imports stay out of `import fieldkit.field_edition`
    from fieldkit.memory import MemoryIndex, Provenance

__all__ = [
    "CORPUS_PACK_PATH",
    "CORPUS_PACK_SHA",
    "CorpusSource",
    "CorpusPack",
    "corpus_pack_sha",
    "load_corpus_pack",
    "plan_chunks",
    "index_for",
    "ingest_pack",
    "corpus_chunk_count",
    "run_ingest",
    "IngestResult",
]

#: The vendored frozen corpus pack (rides the wheel via the ``data/*.jsonl.gz``
#: glob). Gzip of the canonical JSON payload :data:`CORPUS_PACK_SHA` pins.
CORPUS_PACK_PATH = Path(__file__).resolve().parent / "data" / "advisor-corpus-pack-v01.jsonl.gz"

#: sha256[:12] of the **decompressed** canonical payload — the proof-control pin
#: (gzip headers vary, so we pin the content, not the compressed bytes). Drift
#: means the shipped pack was edited out-of-band; rebuild via the builder script
#: and re-run every gate before re-pinning.
CORPUS_PACK_SHA = "e2f4a2d64ada"


@dataclass(frozen=True)
class CorpusSource:
    """One vendored source: its stripped body + the provenance prefix line."""

    source_id: str
    meta: str
    body: str
    source_class: str
    date_or_version: str
    path_or_url: str


@dataclass(frozen=True)
class CorpusPack:
    """The vendored demo corpus + its provenance pins."""

    name: str
    version: str
    corpus_table: str
    source_manifest_sha256_12: str
    sources: tuple[CorpusSource, ...]


def corpus_pack_sha(path: Path = CORPUS_PACK_PATH) -> str:
    """sha256[:12] of the decompressed canonical payload (drift check)."""
    return hashlib.sha256(gzip.decompress(path.read_bytes())).hexdigest()[:12]


def load_corpus_pack(path: Path = CORPUS_PACK_PATH, *, verify_sha: bool = True) -> CorpusPack:
    """Read the packaged corpus pack; optionally assert the proof-control sha.

    ``verify_sha`` defaults on — a mismatch against :data:`CORPUS_PACK_SHA` means
    the shipped pack was edited without a deliberate re-pin and raises, never
    silently ingesting a tampered corpus.
    """
    raw = gzip.decompress(path.read_bytes())
    if verify_sha:
        actual = hashlib.sha256(raw).hexdigest()[:12]
        if actual != CORPUS_PACK_SHA:
            raise ValueError(
                f"corpus-pack sha drift: {path.name} content is {actual}, "
                f"pinned {CORPUS_PACK_SHA} — rebuild via the builder script + re-pin"
            )
    doc = json.loads(raw)
    sources = tuple(
        CorpusSource(
            source_id=str(s["source_id"]),
            meta=str(s["meta"]),
            body=str(s["body"]),
            source_class=str(s["source_class"]),
            date_or_version=str(s.get("date_or_version") or ""),
            path_or_url=str(s["path_or_url"]),
        )
        for s in doc["sources"]
    )
    return CorpusPack(
        name=str(doc["name"]),
        version=str(doc["version"]),
        corpus_table=str(doc.get("corpus_table", "advisor_corpus_v01")),
        source_manifest_sha256_12=str(doc.get("source_manifest_sha256_12", "")),
        sources=sources,
    )


def plan_chunks(pack: CorpusPack) -> list[tuple[str, int, str, "Provenance"]]:
    """Pure: the ``(slug, chunk_idx, prefixed_text, provenance)`` rows to write.

    A faithful port of ``score_recall_live.ingest_corpus``: each source's body is
    split by :func:`fieldkit.memory.chunk_words` (900/150) and every chunk is
    prefixed with the source's provenance metadata line, so the vendored chunks
    match the recall proof's chunks. No embedding, no I/O — the chunking is
    testable in isolation.
    """
    from fieldkit.memory import Provenance, chunk_words

    rows: list[tuple[str, int, str, Provenance]] = []
    for src in pack.sources:
        prov = Provenance(
            source="article",  # all sources are published_orionfold tier
            kind=src.source_class,
            doc_date=src.date_or_version,
            link=src.path_or_url,
        )
        for idx, chunk in enumerate(chunk_words(src.body)):
            if not chunk.strip():
                continue
            rows.append((src.source_id, idx, f"{src.meta}\n\n{chunk}", prov))
    return rows


def index_for(config: FieldEditionConfig | None = None) -> "MemoryIndex":
    """A :class:`~fieldkit.memory.MemoryIndex` pointed at the Field Edition stack
    (the ``advisor_corpus_v01`` table, the compose pgvector + embedder ports)."""
    from fieldkit.memory import MemoryIndex

    cfg = config or default_config()
    pg = cfg.postgres
    emb = cfg.embedder
    return MemoryIndex(
        pg_dsn=f"host=127.0.0.1 port={pg.port} dbname={pg.db} user={pg.user} password={pg.password}",
        embed_url=f"http://127.0.0.1:{emb.port}/v1/embeddings",
        embed_model=emb.model,
        embed_dim=emb.dim,
        table="advisor_corpus_v01",
    )


def corpus_chunk_count(index: "MemoryIndex") -> int:
    """Total chunks currently in the corpus table (0 on a fresh box). Ensures the
    schema first so the count works on a never-ingested table."""
    index.ensure_schema()
    return sum(index.chunk_counts().values())


@dataclass
class IngestResult:
    """The outcome of a :func:`run_ingest`."""

    sources: int
    chunks_written: int
    chunk_total: int
    skipped: bool = False
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None


def ingest_pack(index: "MemoryIndex", pack: CorpusPack, *, embed_batch: int | None = None) -> dict:
    """Embed + upsert the pack into the index (the only I/O). Mirrors
    ``fieldkit.memory.ingest_sources`` batching; embeddings are per-text so the
    batch boundaries do not change the vectors (recall reproduced)."""
    from fieldkit.memory import EMBED_BATCH

    batch = embed_batch or EMBED_BATCH
    index.ensure_schema()
    index.replace_slugs(s.source_id for s in pack.sources)
    planned = plan_chunks(pack)
    rows = []
    for start in range(0, len(planned), batch):
        window = planned[start : start + batch]
        vecs = index._embed([t for (_slug, _idx, t, _prov) in window], "passage")
        for (slug, idx, text, prov), vec in zip(window, vecs, strict=True):
            rows.append((slug, idx, text, vec, prov))
    written = index.write_chunks(rows)
    index.create_indexes()
    return {"chunks_written": written, "sources": len(pack.sources), "chunk_total": len(planned)}


def run_ingest(
    config: FieldEditionConfig | None = None,
    *,
    index: "MemoryIndex | None" = None,
    force: bool = False,
    on_event: Callable[[str], None] | None = None,
) -> IngestResult:
    """Load the vendored pack and ingest it into ``advisor_corpus_v01``.

    Idempotent: a non-empty corpus is left as-is (``skipped=True``) unless
    ``force``. Returns an :class:`IngestResult` so the CLI / the ``up`` phase can
    print an honest line; failures surface as ``error`` rather than a traceback.
    """
    cfg = config or default_config()
    emit = on_event or (lambda _msg: None)
    try:
        pack = load_corpus_pack()
    except (OSError, ValueError) as exc:
        return IngestResult(0, 0, 0, error=f"corpus pack unavailable: {exc}")
    idx = index or index_for(cfg)
    try:
        existing = corpus_chunk_count(idx)
        if existing and not force:
            emit(f"corpus already ingested ({existing} chunks) — skipping")
            return IngestResult(len(pack.sources), 0, 0, skipped=True)
        emit(f"ingesting {len(pack.sources)} sources into {pack.corpus_table}")
        stats = ingest_pack(idx, pack)
    except Exception as exc:  # noqa: BLE001 — surface embed/pg failures honestly
        return IngestResult(len(pack.sources), 0, 0, error=str(exc)[:300])
    emit(f"ingested {stats['chunks_written']} chunks")
    return IngestResult(
        sources=stats["sources"],
        chunks_written=stats["chunks_written"],
        chunk_total=stats["chunk_total"],
    )
