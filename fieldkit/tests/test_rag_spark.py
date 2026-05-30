# Copyright 2026 Manav Sehgal
# SPDX-License-Identifier: Apache-2.0
"""Spark-live integration test for fieldkit.rag.

Skipped unless `pytest --spark` is passed AND all three services are
reachable: pgvector at the configured DSN, the embed NIM, and the 8B
chat NIM. Defaults match the project's verified-on-Spark setup; override
via env vars.

The test ingests two tiny documents into a temporary pgvector table
(`fieldkit_rag_smoke`), retrieves+asks one question, and asserts the
answer references the seeded chunk's id. Cleans up the table at the end.
"""

from __future__ import annotations

import os

import pytest

from fieldkit.nim import NIMClient, wait_for_warm
from fieldkit.rag import Document, Pipeline


PGV_DSN = os.environ.get(
    "PGVECTOR_DSN", "postgresql://spark:spark@localhost:5432/vectors"
)
EMBED_BASE_URL = os.environ.get("EMBED_BASE_URL", "http://localhost:8001/v1")
NIM_BASE_URL = os.environ.get("NIM_BASE_URL", "http://localhost:8000/v1")
NIM_MODEL = os.environ.get("NIM_MODEL", "meta/llama-3.1-8b-instruct")

SMOKE_TABLE = "fieldkit_rag_smoke"


@pytest.mark.spark
def test_rag_round_trip() -> None:
    """Ensure → ingest → ask round trip against live Spark services.

    Uses a dedicated `fieldkit_rag_smoke` table so it doesn't tread on
    the corpus that the article evidence uses.
    """
    if not wait_for_warm(EMBED_BASE_URL, timeout=120.0, poll_interval=2.0):
        pytest.skip(f"embed NIM at {EMBED_BASE_URL} did not warm within 120s")
    if not wait_for_warm(NIM_BASE_URL, timeout=120.0, poll_interval=2.0):
        pytest.skip(f"chat NIM at {NIM_BASE_URL} did not warm within 120s")

    try:
        import psycopg

        with psycopg.connect(PGV_DSN, connect_timeout=5) as conn, conn.cursor() as cur:
            cur.execute("SELECT 1")
    except Exception as exc:  # pragma: no cover - skip path
        pytest.skip(f"pgvector unreachable at {PGV_DSN}: {exc}")

    with NIMClient(base_url=NIM_BASE_URL, model=NIM_MODEL, timeout=30.0) as gen:
        with Pipeline(
            embed_url=EMBED_BASE_URL,
            pgvector_dsn=PGV_DSN,
            generator=gen,
            embed_dim=1024,
            embed_batch=8,
            chunk_tokens=200,
            table=SMOKE_TABLE,
            timeout=30.0,
        ) as pipe:
            # Fresh table every run keeps assertions deterministic.
            with psycopg.connect(PGV_DSN) as conn, conn.cursor() as cur:
                cur.execute(f"DROP TABLE IF EXISTS {SMOKE_TABLE}")
                conn.commit()
            pipe.ensure_schema()

            try:
                ingested = pipe.ingest(
                    [
                        Document(
                            id=1001,
                            label="seed",
                            text=(
                                "The DGX Spark is a personal AI computer with a GB10 "
                                "Grace-Blackwell superchip and 128 GB of unified memory."
                            ),
                        ),
                        Document(
                            id=1002,
                            label="distractor",
                            text=(
                                "The Olympic Games of 2004 took place in Athens, "
                                "Greece, with 11099 athletes competing across 28 sports."
                            ),
                        ),
                    ]
                )
                assert ingested >= 2

                result = pipe.ask(
                    "How much unified memory does the DGX Spark have?",
                    retrieve_k=2,
                    rerank_k=1,
                    max_tokens=64,
                )
                answer = result["answer"]
                assert isinstance(answer, str) and answer
                assert "128" in answer  # the canonical unified-memory number
                ids = [c.id for c in result["chunks"]]
                assert 1001 in ids
            finally:
                with psycopg.connect(PGV_DSN) as conn, conn.cursor() as cur:
                    cur.execute(f"DROP TABLE IF EXISTS {SMOKE_TABLE}")
                    conn.commit()
