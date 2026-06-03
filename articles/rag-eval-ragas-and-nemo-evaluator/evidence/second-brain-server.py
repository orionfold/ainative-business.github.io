"""Second Brain MCP server — the version-controlled M10 build.

The canonical copy of the standalone `second-brain-mcp` server, committed into
the repo as part of Arena M10 (Bet 5, decision M10-12 — close the "external,
manually re-indexed, none version-controlled" drift that let the index rot to
12/63 articles). Retrieval goes through the **single `fieldkit.memory` backend**
(M10-9), so the trust-tier (provenance) filter + the cosine-only / rerank policy
are defined once and shared with the harness `ask_second_brain` tool.

Models run LOCAL on the Spark: NIM Embed (:8001) → pgvector `blog_chunks`
(+ M10 provenance card) → optional reranker → NIM Llama 3.1 8B (:8000).
Reranking is OFF by default (cosine-only is the GB10 measured baseline, M10-7);
set RERANK_URL once a `-dgx-spark` reranker profile exists.

All tools are read-only; the server speaks JSON-RPC over stdio. Deploy the live
copy at /home/nvidia/second-brain-mcp/server.py from this canonical seed.
"""
from __future__ import annotations

import json
import os
import time
import urllib.request
from typing import Any

from fieldkit.memory import SOURCE_CLASSES, MemoryIndex
from mcp.server.fastmcp import FastMCP

LLM_URL = os.environ.get("LLM_URL", "http://127.0.0.1:8000/v1/chat/completions")
LLM_MODEL = os.environ.get("LLM_MODEL", "meta/llama-3.1-8b-instruct")
CHUNK_WORD_BUDGET = 500  # trim per-chunk before generation; matches grade.py

mcp = FastMCP("second-brain")
_index = MemoryIndex()  # reads SECOND_BRAIN_PG_DSN / EMBED_URL from env


def _trim(text: str, words: int) -> str:
    parts = text.split()
    return text if len(parts) <= words else " ".join(parts[:words]) + " …"


SYS_PROMPT = (
    "You are a careful assistant answering questions about the ai-field-notes "
    "project (articles by Manav Sehgal on running AI locally on the NVIDIA "
    "DGX Spark). Answer using ONLY the provided context passages, each "
    "labeled with its source article slug and chunk index like [slug #N]. "
    "Answer concisely and concretely. Cite the passages you used in a "
    "trailing line: 'Sources: [slug #N, slug #N]'. If the context does not "
    "contain the answer, reply with exactly one sentence: 'The provided "
    "context does not contain the answer.'"
)


def _generate(question: str, contexts: list[dict], max_tokens: int) -> dict:
    parts = [
        f"[{h['slug']} #{h['chunk_idx']}]\n{_trim(h['text'], CHUNK_WORD_BUDGET)}"
        for h in contexts
    ]
    user = (
        f"Context passages:\n\n{chr(10).join(parts)}\n\n"
        f"Question: {question}\n\nAnswer:"
    )
    body = json.dumps({
        "model": LLM_MODEL,
        "messages": [
            {"role": "system", "content": SYS_PROMPT},
            {"role": "user", "content": user},
        ],
        "temperature": 0.0,
        "top_p": 1.0,
        "max_tokens": max_tokens,
    }).encode()
    req = urllib.request.Request(
        LLM_URL, data=body, headers={"Content-Type": "application/json"}
    )
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=120) as r:
        resp = json.loads(r.read())
    return {
        "text": resp["choices"][0]["message"]["content"].strip(),
        "wall_s": round(time.time() - t0, 3),
    }


@mcp.tool(
    description=(
        "Semantic search over Manav's ai-field-notes blog corpus (articles on "
        "running AI locally on the NVIDIA DGX Spark), via the shared "
        "fieldkit.memory backend. Returns top-k chunks with slug, chunk index, "
        "prose, and provenance (source class + verdict). Optional `provenance` "
        "filters by trust tier (article|lineage|scout|...). Cosine-only on GB10."
    ),
    annotations={"readOnlyHint": True, "idempotentHint": True, "openWorldHint": False},
)
def search_blog(
    query: str, top_k: int = 5, provenance: list[str] | None = None
) -> dict:
    if top_k < 1 or top_k > 20:
        raise ValueError("top_k must be between 1 and 20")
    t0 = time.time()
    hits = _index.query(query, top_k=top_k, sources=provenance)
    return {
        "query": query,
        "provenance": provenance,
        "wall_s": round(time.time() - t0, 3),
        "hits": [
            {
                "slug": h["slug"],
                "chunk_idx": h["chunk_idx"],
                "dist": round(h["dist"], 4),
                "source": h["source"],
                "verdict": h["verdict"],
                "text": h["text"],
            }
            for h in hits
        ],
    }


@mcp.tool(
    description=(
        "Ask a question of Manav's ai-field-notes blog corpus. Retrieves top-k "
        "chunks via fieldkit.memory (cosine-only) and generates a grounded "
        "answer with NIM Llama 3.1 8B locally. Optional `provenance` trust-tier "
        "filter. Requires the 8B generator NIM up on :8000."
    ),
    annotations={"readOnlyHint": True, "idempotentHint": True, "openWorldHint": False},
)
def ask_blog(
    question: str,
    top_k: int = 3,
    max_tokens: int = 256,
    provenance: list[str] | None = None,
) -> dict:
    if top_k < 1 or top_k > 5:
        raise ValueError("top_k must be between 1 and 5 (NIM 8192-token ceiling)")
    if max_tokens < 16 or max_tokens > 1024:
        raise ValueError("max_tokens must be between 16 and 1024")
    t_total = time.time()
    hits = _index.query(question, top_k=top_k, sources=provenance)
    gen = _generate(question, hits, max_tokens)
    return {
        "question": question,
        "answer": gen["text"],
        "sources": [
            {"slug": h["slug"], "chunk_idx": h["chunk_idx"], "source": h["source"]}
            for h in hits
        ],
        "wall_s": round(time.time() - t_total, 3),
        "generate_wall_s": gen["wall_s"],
    }


@mcp.tool(
    description=(
        "List every article in the Second Brain index with slug and chunk "
        "count. Discovery surface — call first to see what's indexed."
    ),
    annotations={"readOnlyHint": True, "idempotentHint": True, "openWorldHint": False},
)
def list_articles() -> dict:
    counts = _index.chunk_counts()
    return {
        "count": len(counts),
        "articles": [
            {"slug": s, "chunks": n} for s, n in sorted(counts.items())
        ],
    }


@mcp.tool(
    description=(
        "The provenance source classes the index supports for trust-tier "
        "filtering: article (highest trust — published prose), lineage "
        "(internal experiment memory), scout/deep_research (external, lowest)."
    ),
    annotations={"readOnlyHint": True, "idempotentHint": True, "openWorldHint": False},
)
def provenance_classes() -> dict:
    return {"source_classes": list(SOURCE_CLASSES)}


if __name__ == "__main__":
    mcp.run()
