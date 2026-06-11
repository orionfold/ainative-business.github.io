# Copyright 2026 Manav Sehgal
# SPDX-License-Identifier: Apache-2.0
"""Live Cortex retrieval for Arena chat — the Advisor packet builder.

Free-prompt chat with ``retrieval: true`` grounds the turn in the Advisor's
*frozen corpus pack*: dense top-K over the ``advisor_corpus_v01`` pgvector
table (the OA-NV-8 swap table the live recall gate measured — NOT the
operator's ``blog_chunks`` Second Brain), deduped to the top unique manifest
sources, then formatted into the exact production packet the 4B-SFT lane was
trained and gated on.

The packet contract here must stay byte-compatible with
``scripts/orionfold_advisor/preflight.py`` (the canonical scorer):

* system prompt — ``_system_prompt("off")`` verbatim (``/no_think`` prefix);
* user prompt — the *production-shaped* form (no evaluator hint):
  ``Question: …\\n\\nRetrieved public context:\\nSource N: …`` blocks;
* k=3 unique sources, 900-char query-centered excerpts from the manifest
  article bodies, ``Source N:`` positional labels with exact ``source_id``s.

Retrieval differs from preflight by design: preflight ranks with local BM25;
chat ranks through the production Cortex stack (pgvector + NIM embedder),
mirroring ``scripts/orionfold_advisor/score_recall_live.py`` — the lane the
``advisor-rag-source-recall-live`` gate passed at 0.977@5.

Per ``feedback_llm_skill_pattern`` everything here is deterministic transform:
no LLM calls — the caller streams the packet to whatever lane is selected.
"""

from __future__ import annotations

import json
import os
import re
from collections import Counter
from pathlib import Path
from typing import Any

__all__ = [
    "ADVISOR_TABLE",
    "CHUNK_POOL",
    "EXCERPT_CHARS",
    "TOP_K",
    "CortexUnavailable",
    "build_packet",
    "is_advisor_model",
]

#: Corpus-pack table the live recall gate measured (OA-NV-8 swap unit).
ADVISOR_TABLE = os.environ.get("ARENA_ADVISOR_TABLE", "advisor_corpus_v01")
#: Packet contract knobs — keep in sync with preflight.py defaults / HF card.
TOP_K = 3
EXCERPT_CHARS = 900
#: Chunks fetched per query before source-level dedup (score_recall_live.py).
CHUNK_POOL = 80

MANIFEST_RELPATH = Path("evidence/orionfold-advisor/public-corpus-manifest.jsonl")

_TOKEN_RE = re.compile(r"[a-z0-9]+")
# Verbatim from scripts/orionfold_advisor/score_recall.py — the excerpt
# builder's term weighting must match the one the packets were gated with.
_STOPWORDS = {
    "a", "about", "after", "and", "are", "as", "at", "be", "before", "by",
    "can", "cite", "citing", "does", "for", "from", "how", "in", "is", "it",
    "of", "on", "or", "public", "should", "source", "the", "them", "to",
    "what", "when", "which", "with",
}


class CortexUnavailable(RuntimeError):
    """Raised when the retrieval stack (pgvector / embedder NIM / manifest)
    can't serve a packet — callers surface this verbatim instead of letting
    an ungrounded turn masquerade as a grounded one."""


def is_advisor_model(model: str | None) -> bool:
    """Heuristic advisor-lane detector for UI affordances (the promoted GGUF
    is named ``…-advisor-sft-…``; lane ids carry the recipe slug)."""
    return "advisor" in (model or "").lower()


def _tokenize(text: str) -> list[str]:
    return [
        tok
        for tok in _TOKEN_RE.findall(text.lower())
        if tok not in _STOPWORDS and len(tok) > 1
    ]


def _strip_markup(text: str) -> str:
    text = re.sub(r"^---\n.*?\n---\n", " ", text, flags=re.DOTALL)
    text = re.sub(r"```.*?```", " ", text, flags=re.DOTALL)
    text = re.sub(r"`([^`]+)`", r"\1", text)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\{[^{}]*\}", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _query_centered_excerpt(text: str, query: str, max_chars: int) -> str:
    """Pick the ``max_chars`` window around the sentence that best matches
    ``query`` (same selection preflight.py used to build training/serving
    packets)."""
    text = re.sub(r"\s+", " ", _strip_markup(text)).strip()
    if len(text) <= max_chars:
        return text

    query_terms = Counter(_tokenize(query))
    sentences = re.split(r"(?<=[.!?])\s+", text)
    if not sentences:
        return text[:max_chars].rstrip()

    best_idx = 0
    best_score = -1
    for idx, sentence in enumerate(sentences):
        score = sum(query_terms.get(term, 0) for term in _tokenize(sentence))
        if score > best_score:
            best_idx = idx
            best_score = score

    start = max(0, best_idx - 1)
    excerpt = ""
    for sentence in sentences[start:]:
        if excerpt and len(excerpt) + len(sentence) + 1 > max_chars:
            break
        excerpt = f"{excerpt} {sentence}".strip()
    if not excerpt:
        excerpt = text[:max_chars].rstrip()
    return excerpt


def _system_prompt() -> str:
    # Verbatim preflight.py ``_system_prompt("off")`` — the measured serving
    # contract (reasoning off; Nemotron-3 also gets the enable_thinking kwarg
    # via ``chat_kwargs`` below).
    return "/no_think\n" + (
        "You are Orionfold Advisor. Answer only from the retrieved public context. "
        "Do not use private handoff state, live runtime state, local filesystem "
        "state, credentials, or unpublished operator notes. If the retrieved "
        "public context does not support the answer, say that directly. For a "
        "supported answer, finish with exactly one citation line using source ids: "
        "Citations: [source_id, ...]. For an unsupported answer, finish with "
        "Citations: []. If the task is workflow routing, start with 'Route:'. "
        "Questions asking what is stored in .env.local, credential files, live "
        "runtime state, or private operator state are unsupported even if public "
        "docs mention environment variable names such as *_TOKEN or *_API_KEY. "
        "Do not emit hidden reasoning or <think> tags. "
        "Format examples — supported answer ends: "
        "'Citations: [product_orionfold_cortex]' (copy the exact source_id "
        "strings from the retrieved context; never positional aliases like "
        "'Citations: [Source 2]' or 'Citations: [2]'). Unsupported answer ends: "
        "'The retrieved public context does not support this question. "
        "Citations: []' (always state that the context does not support the "
        "answer before the empty citation line)."
    )


def _user_prompt(question: str, blocks: list[dict[str, Any]]) -> str:
    # Production-shaped packet (preflight.py ``evaluator_hint=False``): the
    # system prompt alone carries the contract, as for a real user question.
    context = "\n\n".join(
        (
            f"Source {idx}: {block['source_id']}\n"
            f"Label: {block['citation_label']}\n"
            f"Class: {block['source_class']} / {block['source_role']}\n"
            f"Title: {block['title']}\n"
            f"Excerpt: {block['excerpt']}"
        )
        for idx, block in enumerate(blocks, start=1)
    )
    return (
        f"Question: {question}\n\n"
        f"Retrieved public context:\n{context or '(none)'}"
    )


# (manifest rows, sha256_12) keyed by resolved path, invalidated on mtime.
_MANIFEST_CACHE: dict[str, tuple[float, list[dict[str, Any]], str]] = {}


def _load_manifest(root: Path) -> tuple[list[dict[str, Any]], str]:
    path = (root / MANIFEST_RELPATH).resolve()
    if not path.is_file():
        raise CortexUnavailable(f"corpus manifest missing: {path}")
    mtime = path.stat().st_mtime
    cached = _MANIFEST_CACHE.get(str(path))
    if cached and cached[0] == mtime:
        return cached[1], cached[2]
    import hashlib

    raw = path.read_bytes()
    sha12 = hashlib.sha256(raw).hexdigest()[:12]
    rows = [
        json.loads(line)
        for line in raw.decode("utf-8").splitlines()
        if line.strip()
    ]
    _MANIFEST_CACHE[str(path)] = (mtime, rows, sha12)
    return rows, sha12


def build_packet(
    question: str,
    *,
    root: Path,
    index: Any | None = None,
    top_k: int = TOP_K,
    excerpt_chars: int = EXCERPT_CHARS,
    chunk_pool: int = CHUNK_POOL,
) -> dict[str, Any]:
    """Retrieve from the corpus pack and build the production Advisor packet.

    Returns ``{system, user_prompt, chat_kwargs, retrieval}`` where
    ``retrieval`` is the start-event surface (table, manifest sha, deduped
    source cards with cosine distance). ``index`` is injectable for tests;
    left ``None`` it opens :class:`fieldkit.memory.MemoryIndex` on
    :data:`ADVISOR_TABLE`. Raises :class:`CortexUnavailable` when pgvector,
    the embedder, or the manifest can't be reached — never degrades silently.
    """
    manifest, manifest_sha = _load_manifest(root)
    by_id = {str(row["source_id"]): row for row in manifest}

    if index is None:
        from fieldkit.memory import MemoryIndex

        index = MemoryIndex(table=ADVISOR_TABLE)
    try:
        hits = index.query(question, top_k=chunk_pool)
    except Exception as exc:  # noqa: BLE001 — MemoryError, connect, embed…
        raise CortexUnavailable(str(exc)) from exc

    # Source-level dedup over chunk hits (slug == source_id in the corpus-pack
    # table) — same rule as score_recall_live.py / preflight _top_unique_sources.
    blocks: list[dict[str, Any]] = []
    seen: set[str] = set()
    for hit in hits:
        source_id = str(hit["slug"])
        source = by_id.get(source_id)
        if source is None or source_id in seen:
            continue  # provenance-card rows / drifted slugs never reach the packet
        seen.add(source_id)
        path = root / str(source["path_or_url"])
        try:
            body = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            # Manifest body missing on this checkout — fall back to the
            # retrieved chunk text (already provenance-prefixed at ingest;
            # drop that metadata line so the excerpt is prose).
            body = str(hit.get("text") or "")
            body = body.split("\n\n", 1)[1] if "\n\n" in body else body
        blocks.append(
            {
                "source_id": source_id,
                "citation_label": source["citation_label"],
                "path_or_url": source["path_or_url"],
                "source_class": source["source_class"],
                "source_role": source["source_role"],
                "title": source["title"],
                "dist": round(float(hit["dist"]), 6),
                "excerpt": _query_centered_excerpt(body, question, excerpt_chars),
            }
        )
        if len(blocks) >= top_k:
            break

    return {
        "system": _system_prompt(),
        "user_prompt": _user_prompt(question, blocks),
        # AD-AE-17 sibling: replicate the measured reasoning-off control on
        # local lanes (hosted lanes ignore it upstream, as in eval mode).
        "chat_kwargs": {"chat_template_kwargs": {"enable_thinking": False}},
        "retrieval": {
            "table": ADVISOR_TABLE,
            "manifest_sha256_12": manifest_sha,
            "top_k": top_k,
            "chunk_pool": chunk_pool,
            "sources": [
                {
                    "source_id": b["source_id"],
                    "title": b["title"],
                    "citation_label": b["citation_label"],
                    "dist": b["dist"],
                }
                for b in blocks
            ],
        },
    }
