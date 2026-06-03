# Copyright 2026 Manav Sehgal
# SPDX-License-Identifier: Apache-2.0
"""Tests for `fieldkit.memory` — the Arena M10 recall layer.

Unit-level (no live pgvector / embedder): the chunker, provenance card, the
``collect_*`` source readers, the multi-source ingest (with an injected embed
fn + a fake index), and the coverage join. The live-stack path is covered by
the ``--spark`` smokes elsewhere.
"""
from __future__ import annotations

import json

import pytest

from fieldkit import memory as m


def test_chunk_words_overlap_parity():
    """The 900w/150-overlap chunker matches the retired ingest_blog.py: a fresh
    chunk every 750 words, so chunk_idx stays aligned with the qa-eval gold set."""
    words = " ".join(str(i) for i in range(2000))
    chunks = m.chunk_words(words)
    assert len(chunks) == 3
    assert chunks[0].split()[0] == "0"
    assert chunks[1].split()[0] == "750"  # 900 - 150 overlap
    with pytest.raises(m.MemoryError):
        m.chunk_words("a b c", words_per_chunk=10, overlap=20)


def test_provenance_guard_and_row():
    with pytest.raises(m.MemoryError):
        m.Provenance(source="not-a-class")
    p = m.Provenance(source="scout", kind="paper", verdict="infeasible:vram", link="u")
    assert p.as_row() == ("scout", "paper", "", "infeasible:vram", "u")
    assert set(("article", "lineage", "eval", "scout", "deep_research")) == set(
        m.SOURCE_CLASSES
    )


def test_collect_article_sources(tmp_path):
    a = tmp_path / "good-article"
    a.mkdir()
    (a / "article.md").write_text(
        "---\ntitle: X\nseries: Harnesses\nstatus: published\n---\nbody words here"
    )
    up = tmp_path / "upcoming-one"
    up.mkdir()
    (up / "article.md").write_text("---\nstatus: upcoming\n---\nnope")
    draft = tmp_path / "_drafts"
    draft.mkdir()
    (draft / "article.md").write_text("---\n---\nskip")

    cards = m.collect_article_sources(tmp_path)
    assert [c.slug for c in cards] == ["good-article"]
    assert cards[0].provenance.source == "article"
    assert cards[0].provenance.kind == "Harnesses"
    assert cards[0].provenance.link == "/articles/good-article/"


def test_collect_scout_sources(tmp_path):
    pj = tmp_path / "papers.json"
    pj.write_text(json.dumps({"papers": [
        {"id": "2401.1", "title": "T", "abstract": "abs", "feasibility": "feasible", "url": "u"},
        {"title": "no-id"},  # skipped — no id
    ]}))
    cards = m.collect_scout_sources(pj)
    assert len(cards) == 1
    assert cards[0].slug == "scout-2401.1"
    assert cards[0].provenance.source == "scout"
    assert cards[0].provenance.verdict == "feasible"
    # tolerant of missing file
    assert m.collect_scout_sources(tmp_path / "nope.json") == []


def test_collect_lineage_sources():
    cards = m.collect_lineage_sources([
        {"slug": "t2po-run", "text": "held-out inversion", "verdict": "discard"},
        {"slug": "", "text": "skip"},  # no slug → skipped
    ])
    assert len(cards) == 1
    assert cards[0].slug == "lineage-t2po-run"
    assert cards[0].provenance.source == "lineage"
    assert cards[0].provenance.verdict == "discard"


class _FakeIndex:
    """A MemoryIndex stand-in: records writes, fakes embeds, no pgvector."""

    def __init__(self):
        self.rows = []
        self.deleted = []
        self.schema_ensured = False
        self.indexes_built = False

    def ensure_schema(self):
        self.schema_ensured = True

    def create_indexes(self):
        self.indexes_built = True

    def replace_slugs(self, slugs):
        self.deleted = list(slugs)
        return len(self.deleted)

    def _embed(self, texts, input_type):
        return [[0.1, 0.2, 0.3] for _ in texts]

    def write_chunks(self, rows):
        self.rows = list(rows)
        return len(self.rows)


def test_ingest_sources_multi_source():
    idx = _FakeIndex()
    cards = [
        m.KnowledgeCard("a", "word " * 1000, m.Provenance(source="article")),
        m.KnowledgeCard("scout-x", "paper text", m.Provenance(source="scout", verdict="feasible")),
    ]
    res = m.ingest_sources(idx, cards)
    assert idx.schema_ensured and idx.indexes_built
    assert res["chunks_written"] == len(idx.rows)
    assert res["slugs"] == ["a", "scout-x"]
    # article ("word "*1000 = 1000 words) → 2 chunks; scout → 1
    assert res["by_source"] == {"article": 2, "scout": 1}
    # every written row carries a provenance object in the source class
    assert {r[4].source for r in idx.rows} == {"article", "scout"}
    assert m.ingest_sources(idx, []) == {"chunks_written": 0, "slugs": [], "by_source": {}}


def test_coverage_report_join():
    class FakeStore:
        def articles(self):
            return [
                {"slug": "indexed-a", "status": "published"},
                {"slug": "stale-b", "status": "published"},
                {"slug": "upcoming-c", "status": "upcoming"},  # excluded
            ]

    rep = m.coverage_report(
        FakeStore(),
        indexed_slugs=["indexed-a", "scout-orphan"],
        chunk_counts={"indexed-a": 4},
    )
    assert rep["should_index"] == 2
    assert rep["indexed"] == 1
    assert rep["missing"] == ["stale-b"]
    assert rep["orphan"] == ["scout-orphan"]
    assert rep["coverage_pct"] == 50.0
    assert rep["chunk_counts"] == {"indexed-a": 4}
    with pytest.raises(m.MemoryError):
        m.coverage_report(FakeStore())  # neither index nor indexed_slugs


def test_resolve_qa_set_in_repo():
    """The committed gold set resolves from the repo without an env override."""
    path = m.resolve_qa_set()
    assert path.endswith("qa-eval.jsonl")
    rows = [json.loads(l) for l in open(path) if l.strip()]
    assert len(rows) == 44
    assert {"question", "answer", "source", "chunk"} <= set(rows[0])
    with pytest.raises(m.MemoryError):
        m.resolve_qa_set("/no/such/path.jsonl")
