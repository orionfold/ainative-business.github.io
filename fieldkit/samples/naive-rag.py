#!/usr/bin/env python3
# Copyright 2026 Manav Sehgal
# SPDX-License-Identifier: Apache-2.0
"""End-to-end naive RAG in <30 lines via fieldkit.rag.Pipeline.

Reproduces the `naive-rag-on-spark` flow: ensure schema → ingest a few
documents → ask one question against them. Replaces ~250 lines of
hand-rolled embed / pgvector / chat-completions glue across articles
#4-7 with a single `Pipeline(...)` import.

Prerequisites (Spark):
    docker start nim-embed-nemotron     # :8001 — embedder
    docker start pgvector               # :5432 — vector store
    docker start nim-llama31-8b         # :8000 — generator (~90s cold start)

Run:
    python samples/naive-rag.py

Env overrides:
    EMBED_BASE_URL, NIM_BASE_URL, NIM_MODEL, PGVECTOR_DSN
"""

from __future__ import annotations

import os

from fieldkit.nim import NIMClient, wait_for_warm
from fieldkit.rag import Document, Pipeline

EMBED_BASE_URL = os.environ.get("EMBED_BASE_URL", "http://localhost:8001/v1")
NIM_BASE_URL = os.environ.get("NIM_BASE_URL", "http://localhost:8000/v1")
NIM_MODEL = os.environ.get("NIM_MODEL", "meta/llama-3.1-8b-instruct")
PGVECTOR_DSN = os.environ.get(
    "PGVECTOR_DSN", "postgresql://spark:spark@localhost:5432/vectors"
)

DOCS = [
    Document(id=1, label="spark", text=(
        "The DGX Spark is a personal AI computer with a GB10 Grace-Blackwell "
        "superchip and 128 GB of unified memory shared between CPU and GPU."
    )),
    Document(id=2, label="spark", text=(
        "Spark's unified memory means a single large model competes with the "
        "OS and other processes for the same 128 GB pool."
    )),
    Document(id=3, label="distractor", text=(
        "The 2004 Athens Olympics hosted 11099 athletes across 28 sports."
    )),
]


def main() -> int:
    wait_for_warm(EMBED_BASE_URL)
    wait_for_warm(NIM_BASE_URL)
    with NIMClient(base_url=NIM_BASE_URL, model=NIM_MODEL) as gen, Pipeline(
        embed_url=EMBED_BASE_URL, pgvector_dsn=PGVECTOR_DSN, generator=gen,
        table="fieldkit_naive_rag_sample", chunk_tokens=400,
    ) as pipe:
        pipe.ensure_schema()
        n = pipe.ingest(DOCS)
        print(f"Ingested {n} chunks.")
        result = pipe.ask(
            "How much unified memory does the DGX Spark have?",
            retrieve_k=3, rerank_k=2, max_tokens=64,
        )
        print(f"\nA: {result['answer']}")
        print(f"   chunks: {[c.id for c in result['chunks']]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
