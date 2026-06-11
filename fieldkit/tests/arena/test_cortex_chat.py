# Copyright 2026 Manav Sehgal
# SPDX-License-Identifier: Apache-2.0
"""Tests for :mod:`fieldkit.arena.cortex_chat` — the live-retrieval Advisor
packet builder behind ``POST /api/chat/stream`` ``retrieval: true``."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

from fieldkit.arena.cortex_chat import (
    ADVISOR_TABLE,
    CortexUnavailable,
    build_packet,
    is_advisor_model,
)


# ---------------------------------------------------------------------------
# Fixtures — a tiny corpus pack (manifest + bodies) and an injectable index
# ---------------------------------------------------------------------------


def _manifest_row(source_id: str, relpath: str, title: str) -> dict[str, Any]:
    return {
        "source_id": source_id,
        "citation_label": f"Field Note: {title}",
        "path_or_url": relpath,
        "source_class": "field_note",
        "source_role": "book2_field_note",
        "title": title,
        "trust_tier": "published_orionfold",
        "public_safe": True,
        "status": "published",
    }


@pytest.fixture
def corpus_root(tmp_path: Path) -> Path:
    """Repo-shaped root with a 3-source manifest and two article bodies on
    disk (``src_c`` is deliberately missing — exercises the chunk-text
    fallback)."""
    articles = tmp_path / "articles"
    articles.mkdir()
    (articles / "alpha.md").write_text(
        "The Hermes brain is pinned to Qwen3-30B-A3B. " * 40, encoding="utf-8"
    )
    (articles / "beta.md").write_text(
        "LaneTruth guards every model swap with a two-step confirm.",
        encoding="utf-8",
    )
    manifest_dir = tmp_path / "evidence" / "orionfold-advisor"
    manifest_dir.mkdir(parents=True)
    rows = [
        _manifest_row("src_a", "articles/alpha.md", "Alpha"),
        _manifest_row("src_b", "articles/beta.md", "Beta"),
        _manifest_row("src_c", "articles/missing.md", "Gamma"),
    ]
    (manifest_dir / "public-corpus-manifest.jsonl").write_text(
        "\n".join(json.dumps(r, sort_keys=True) for r in rows) + "\n",
        encoding="utf-8",
    )
    return tmp_path


class _StubIndex:
    """Injectable stand-in for ``MemoryIndex`` — canned chunk hits."""

    def __init__(self, hits: list[dict[str, Any]] | Exception) -> None:
        self._hits = hits
        self.queries: list[tuple[str, int]] = []

    def query(self, text: str, *, top_k: int = 5, sources=None):
        self.queries.append((text, top_k))
        if isinstance(self._hits, Exception):
            raise self._hits
        return self._hits


def _hit(slug: str, idx: int, dist: float, text: str = "meta line\n\nbody text") -> dict[str, Any]:
    return {"slug": slug, "chunk_idx": idx, "dist": dist, "text": text}


# ---------------------------------------------------------------------------
# Packet contract
# ---------------------------------------------------------------------------


def test_build_packet_dedupes_chunks_to_unique_sources(corpus_root: Path) -> None:
    """Multiple chunk hits from one source collapse to one ``Source N:``
    block (preflight ``_top_unique_sources`` rule), capped at ``top_k``."""
    index = _StubIndex(
        [
            _hit("src_a", 0, 0.10),
            _hit("src_a", 3, 0.12),
            _hit("src_b", 1, 0.20),
            _hit("src_a", 7, 0.25),
            _hit("src_c", 0, 0.30),
        ]
    )
    packet = build_packet("hermes brain?", root=corpus_root, index=index, top_k=2)
    ids = [s["source_id"] for s in packet["retrieval"]["sources"]]
    assert ids == ["src_a", "src_b"]
    assert "Source 1: src_a" in packet["user_prompt"]
    assert "Source 2: src_b" in packet["user_prompt"]
    assert "Source 3" not in packet["user_prompt"]
    # The chunk pool is what hits the index, not top_k.
    assert index.queries[0][1] > 2


def test_build_packet_carries_the_serving_contract(corpus_root: Path) -> None:
    """System prompt is the measured reasoning-off contract; user prompt is
    the production shape (no evaluator hint); kwargs carry the AD-AE-17
    rider; the retrieval receipt pins table + manifest sha."""
    index = _StubIndex([_hit("src_a", 0, 0.1)])
    packet = build_packet("hermes brain?", root=corpus_root, index=index)

    assert packet["system"].startswith("/no_think\n")
    assert "Citations: [source_id, ...]" in packet["system"]
    assert packet["user_prompt"].startswith("Question: hermes brain?")
    assert "Retrieved public context:" in packet["user_prompt"]
    assert "Expected behavior family" not in packet["user_prompt"]  # no hint
    assert packet["chat_kwargs"] == {
        "chat_template_kwargs": {"enable_thinking": False}
    }

    receipt = packet["retrieval"]
    assert receipt["table"] == ADVISOR_TABLE
    manifest_bytes = (
        corpus_root / "evidence/orionfold-advisor/public-corpus-manifest.jsonl"
    ).read_bytes()
    assert receipt["manifest_sha256_12"] == hashlib.sha256(manifest_bytes).hexdigest()[:12]
    assert receipt["sources"][0]["dist"] == 0.1


def test_build_packet_skips_slugs_outside_the_manifest(corpus_root: Path) -> None:
    """Provenance-card rows / drifted slugs never reach the packet — only
    manifest sources are citable."""
    index = _StubIndex([_hit("__provenance__", 0, 0.05), _hit("src_b", 0, 0.2)])
    packet = build_packet("lanetruth?", root=corpus_root, index=index)
    ids = [s["source_id"] for s in packet["retrieval"]["sources"]]
    assert ids == ["src_b"]


def test_build_packet_zero_hits_yields_refusal_shaped_context(corpus_root: Path) -> None:
    index = _StubIndex([])
    packet = build_packet("what is in .env.local?", root=corpus_root, index=index)
    assert packet["user_prompt"].endswith("Retrieved public context:\n(none)")
    assert packet["retrieval"]["sources"] == []


def test_build_packet_missing_body_falls_back_to_chunk_text(corpus_root: Path) -> None:
    """``src_c``'s article body is absent on this checkout — the excerpt
    falls back to the retrieved chunk text minus its metadata prefix line."""
    index = _StubIndex(
        [_hit("src_c", 0, 0.1, text="src_c | Field Note: Gamma\n\nGamma chunk prose.")]
    )
    packet = build_packet("gamma?", root=corpus_root, index=index)
    assert "Excerpt: Gamma chunk prose." in packet["user_prompt"]


def test_build_packet_excerpts_are_query_centered_and_bounded(corpus_root: Path) -> None:
    index = _StubIndex([_hit("src_a", 0, 0.1)])
    packet = build_packet(
        "hermes brain?", root=corpus_root, index=index, excerpt_chars=120
    )
    excerpt = packet["user_prompt"].split("Excerpt: ", 1)[1]
    assert len(excerpt) <= 160  # 120-char window + sentence-boundary slack
    assert "Qwen3-30B-A3B" in excerpt


# ---------------------------------------------------------------------------
# Failure modes — never degrade silently
# ---------------------------------------------------------------------------


def test_query_failure_raises_cortex_unavailable(corpus_root: Path) -> None:
    index = _StubIndex(MemoryError("pgvector connect failed"))
    with pytest.raises(CortexUnavailable, match="pgvector"):
        build_packet("q?", root=corpus_root, index=index)


def test_missing_manifest_raises_cortex_unavailable(tmp_path: Path) -> None:
    with pytest.raises(CortexUnavailable, match="manifest missing"):
        build_packet("q?", root=tmp_path, index=_StubIndex([]))


# ---------------------------------------------------------------------------
# Lane affordance
# ---------------------------------------------------------------------------


def test_is_advisor_model_matches_promoted_gguf_and_recipe_ids() -> None:
    assert is_advisor_model("NVIDIA-Nemotron-3-Nano-4B-advisor-sft-v0.2-Q8_0.gguf")
    assert is_advisor_model("nemotron3-nano-4b-advisor-sft-v02-q8::Q8_0")
    assert not is_advisor_model("Qwen3-30B-A3B-Q4_K_M.gguf")
    assert not is_advisor_model(None)


# ---------------------------------------------------------------------------
# Retrieval-source surface (swappable corpus pack label)
# ---------------------------------------------------------------------------


def test_retrieval_source_reports_the_active_pack(corpus_root: Path) -> None:
    from fieldkit.arena.cortex_chat import retrieval_source

    src = retrieval_source(corpus_root)
    assert src["available"] is True
    assert src["table"] == ADVISOR_TABLE
    assert src["sources"] == 3
    manifest_bytes = (
        corpus_root / "evidence/orionfold-advisor/public-corpus-manifest.jsonl"
    ).read_bytes()
    assert src["manifest_sha256_12"] == hashlib.sha256(manifest_bytes).hexdigest()[:12]


def test_retrieval_source_degrades_without_a_manifest(tmp_path: Path) -> None:
    from fieldkit.arena.cortex_chat import retrieval_source

    src = retrieval_source(tmp_path)
    assert src["available"] is False
    assert src["table"] == ADVISOR_TABLE
    assert "manifest missing" in src["detail"]
