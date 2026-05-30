# Copyright 2026 Manav Sehgal
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for `fieldkit.rag` — respx-backed embed/rerank/generator + a
tiny fake `psycopg` connect target. No live services required.

The fake captures every SQL `execute(...)` call so we can assert ingest /
retrieve hit pgvector with the right shape, and we hand back canned rows
when `retrieve()` runs its `SELECT`.

Spark-live integration test lives in `test_rag_spark.py` (gated by
`pytest --spark`).
"""

from __future__ import annotations

from typing import Any

import httpx
import pytest
import respx

import fieldkit.rag as rag_module
from fieldkit.nim import NIMClient
from fieldkit.rag import (
    CHUNKS_PER_DOC_MAX,
    Chunk,
    Document,
    Pipeline,
    RAGError,
)


EMBED_URL = "http://embed.test/v1"
RERANK_URL = "http://rerank.test/reranking"
GEN_URL = "http://nim.test/v1"
GEN_MODEL = "meta/llama-3.1-8b-instruct"
EMBED_DIM = 4  # tiny vectors keep the test fixtures readable
PGV_DSN = "postgresql://test/test"


# --- Fake psycopg -------------------------------------------------------


class _FakeCursor:
    def __init__(self, store: "FakePgvector") -> None:
        self._store = store
        self._rows: list[tuple[Any, ...]] = []

    def execute(self, sql: str, params: tuple[Any, ...] | None = None) -> None:
        self._store.calls.append((sql, params))
        # Cheap routing: anything starting with SELECT serves canned rows;
        # everything else is treated as a write.
        normalized = sql.lstrip().upper()
        if normalized.startswith("SELECT"):
            self._rows = list(self._store.canned_rows)
        else:
            self._store.writes.append((sql, params))

    def fetchall(self) -> list[tuple[Any, ...]]:
        return self._rows

    def __enter__(self) -> "_FakeCursor":
        return self

    def __exit__(self, *_exc: object) -> None:
        return None


class _FakeConn:
    def __init__(self, store: "FakePgvector") -> None:
        self._store = store
        self.committed = 0

    def cursor(self) -> _FakeCursor:
        return _FakeCursor(self._store)

    def commit(self) -> None:
        self.committed += 1
        self._store.commits += 1

    def __enter__(self) -> "_FakeConn":
        return self

    def __exit__(self, *_exc: object) -> None:
        return None


class FakePgvector:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[Any, ...] | None]] = []
        self.writes: list[tuple[str, tuple[Any, ...] | None]] = []
        self.canned_rows: list[tuple[int, str, str, float]] = []
        self.commits: int = 0
        self.connect_calls: int = 0

    def connect(self, dsn: str) -> _FakeConn:
        self.connect_calls += 1
        assert dsn == PGV_DSN, f"unexpected dsn {dsn!r}"
        return _FakeConn(self)


@pytest.fixture
def fake_pg(monkeypatch: pytest.MonkeyPatch) -> FakePgvector:
    fake = FakePgvector()
    monkeypatch.setattr(rag_module.psycopg, "connect", fake.connect)
    return fake


# --- Helpers ------------------------------------------------------------


def _embed_payload(n: int) -> dict[str, Any]:
    """NIM-shaped embed response: a vector per input, with `index` order."""
    return {
        "data": [
            {
                "index": i,
                # Embeddings just need to be deterministic + EMBED_DIM-long.
                "embedding": [float(i) + 0.1 * j for j in range(EMBED_DIM)],
            }
            for i in range(n)
        ]
    }


def _gen_response(content: str) -> dict[str, Any]:
    return {
        "id": "chatcmpl-rag-test",
        "object": "chat.completion",
        "model": GEN_MODEL,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
    }


@pytest.fixture
def generator() -> NIMClient:
    c = NIMClient(base_url=GEN_URL, model=GEN_MODEL, max_retries=0, timeout=2.0)
    yield c
    c.close()


@pytest.fixture
def pipeline(generator: NIMClient) -> Pipeline:
    p = Pipeline(
        embed_url=EMBED_URL,
        pgvector_dsn=PGV_DSN,
        generator=generator,
        embed_dim=EMBED_DIM,
        embed_batch=2,
        chunk_tokens=20,
        timeout=2.0,
    )
    yield p
    p.close()


# --- Construction -------------------------------------------------------


class TestConstruction:
    def test_normalises_embed_url_trailing_slash(self, generator: NIMClient) -> None:
        p = Pipeline(
            embed_url=EMBED_URL + "/",
            pgvector_dsn=PGV_DSN,
            generator=generator,
            embed_dim=EMBED_DIM,
        )
        assert p.embed_url == EMBED_URL
        p.close()

    def test_no_rerank_client_by_default(self, pipeline: Pipeline) -> None:
        assert pipeline._rerank_client is None

    def test_rerank_client_when_url_provided(self, generator: NIMClient) -> None:
        p = Pipeline(
            embed_url=EMBED_URL,
            pgvector_dsn=PGV_DSN,
            generator=generator,
            embed_dim=EMBED_DIM,
            rerank_url=RERANK_URL,
            rerank_api_key="ngc-key",
        )
        assert p._rerank_client is not None
        p.close()

    def test_rejects_zero_embed_batch(self, generator: NIMClient) -> None:
        with pytest.raises(ValueError):
            Pipeline(
                embed_url=EMBED_URL,
                pgvector_dsn=PGV_DSN,
                generator=generator,
                embed_dim=EMBED_DIM,
                embed_batch=0,
            )

    def test_close_is_idempotent(self, pipeline: Pipeline) -> None:
        pipeline.close()
        pipeline.close()  # second close must not raise
        assert pipeline._embed_client is None


# --- Schema helper ------------------------------------------------------


class TestEnsureSchema:
    def test_runs_create_extension_and_create_table(
        self, pipeline: Pipeline, fake_pg: FakePgvector
    ) -> None:
        pipeline.ensure_schema()
        assert fake_pg.connect_calls == 1
        assert fake_pg.commits == 1
        assert len(fake_pg.calls) == 1
        sql, _ = fake_pg.calls[0]
        assert "CREATE EXTENSION IF NOT EXISTS vector" in sql
        assert "CREATE TABLE IF NOT EXISTS chunks" in sql
        assert f"vector({EMBED_DIM})" in sql

    def test_honors_custom_table_name(
        self, generator: NIMClient, fake_pg: FakePgvector
    ) -> None:
        with Pipeline(
            embed_url=EMBED_URL,
            pgvector_dsn=PGV_DSN,
            generator=generator,
            embed_dim=EMBED_DIM,
            table="my_chunks",
        ) as p:
            p.ensure_schema()
        assert "my_chunks" in fake_pg.calls[0][0]


# --- Chunk dataclass ----------------------------------------------------


class TestChunkScore:
    def test_score_prefers_rerank_logit(self) -> None:
        c = Chunk(id=1, text="x", distance=0.2, rerank_score=0.9)
        assert c.score == 0.9

    def test_score_falls_back_to_inverted_distance(self) -> None:
        c = Chunk(id=1, text="x", distance=0.25)
        assert c.score == pytest.approx(0.75)

    def test_score_zero_when_no_signal(self) -> None:
        c = Chunk(id=1, text="x")
        assert c.score == 0.0


# --- Ingest -------------------------------------------------------------


class TestIngest:
    @respx.mock
    def test_single_doc_single_chunk_keeps_id(
        self, pipeline: Pipeline, fake_pg: FakePgvector
    ) -> None:
        respx.post(f"{EMBED_URL}/embeddings").mock(
            return_value=httpx.Response(200, json=_embed_payload(1))
        )
        n = pipeline.ingest([Document(id=42, text="short doc", label="L")])
        assert n == 1
        # exactly one INSERT issued, with id=42 (unchanged)
        write_sql, write_params = fake_pg.writes[-1]
        assert "INSERT INTO chunks" in write_sql
        assert write_params is not None
        assert write_params[0] == 42  # id
        assert write_params[1] == "L"  # label
        assert write_params[2] == "short doc"  # text
        assert write_params[3].startswith("[") and "," in write_params[3]  # vec literal

    @respx.mock
    def test_multi_chunk_uses_offset_ids(
        self, pipeline: Pipeline, fake_pg: FakePgvector
    ) -> None:
        # chunk_tokens=20 → ~80-char chunks; 4 long paragraphs → 4 chunks.
        para = "x" * 70
        text = "\n\n".join([para] * 4)
        respx.post(f"{EMBED_URL}/embeddings").mock(
            return_value=httpx.Response(200, json=_embed_payload(2))
        )
        n = pipeline.ingest([Document(id=7, text=text, label="L")])
        assert n == 4
        # First chunk id is 7 * CHUNKS_PER_DOC_MAX + 0 (because >1 chunk)
        ids = [w[1][0] for w in fake_pg.writes]
        assert ids == [
            7 * CHUNKS_PER_DOC_MAX + i for i in range(4)
        ]

    @respx.mock
    def test_dict_documents_accepted(
        self, pipeline: Pipeline, fake_pg: FakePgvector
    ) -> None:
        respx.post(f"{EMBED_URL}/embeddings").mock(
            return_value=httpx.Response(200, json=_embed_payload(1))
        )
        n = pipeline.ingest([{"id": 1, "text": "hello", "label": "x"}])
        assert n == 1
        assert fake_pg.writes[-1][1][2] == "hello"

    @respx.mock
    def test_empty_text_skipped(
        self, pipeline: Pipeline, fake_pg: FakePgvector
    ) -> None:
        # Empty doc and whitespace-only doc both produce no chunks.
        n = pipeline.ingest([Document(id=1, text=""), Document(id=2, text="   \n\n  ")])
        assert n == 0
        assert fake_pg.writes == []

    @respx.mock
    def test_batch_flushes_at_embed_batch(
        self, pipeline: Pipeline, fake_pg: FakePgvector
    ) -> None:
        # embed_batch=2; 5 docs → 3 embed calls (2 + 2 + 1).
        route = respx.post(f"{EMBED_URL}/embeddings")

        def _responder(request: httpx.Request) -> httpx.Response:
            n = len(httpx.Request.read(request))  # touch to keep mypy happy
            del n
            import json
            payload = json.loads(request.content)
            return httpx.Response(200, json=_embed_payload(len(payload["input"])))

        route.mock(side_effect=_responder)
        docs = [Document(id=i, text=f"doc {i}") for i in range(1, 6)]
        n = pipeline.ingest(docs)
        assert n == 5
        assert route.call_count == 3

    @respx.mock
    def test_embed_4xx_raises_RAGError(self, pipeline: Pipeline) -> None:
        respx.post(f"{EMBED_URL}/embeddings").mock(
            return_value=httpx.Response(400, text="bad input")
        )
        with pytest.raises(RAGError):
            pipeline.ingest([Document(id=1, text="hi")])

    @respx.mock
    def test_embed_503_then_recovers_via_retry(
        self, generator: NIMClient, fake_pg: FakePgvector
    ) -> None:
        # Co-resident NIM memory pressure on the Spark unified pool can spike a
        # 503 from the embed NIM during chat NIM warm-up. The pipeline must
        # retry rather than fail the ingest.
        route = respx.post(f"{EMBED_URL}/embeddings").mock(
            side_effect=[
                httpx.Response(503, text="warming"),
                httpx.Response(200, json=_embed_payload(1)),
            ]
        )
        with Pipeline(
            embed_url=EMBED_URL,
            pgvector_dsn=PGV_DSN,
            generator=generator,
            embed_dim=EMBED_DIM,
            embed_batch=2,
            chunk_tokens=20,
            max_retries=2,
            timeout=2.0,
        ) as p:
            n = p.ingest([Document(id=99, text="hi")])
        assert n == 1
        assert route.call_count == 2


# --- Retrieve -----------------------------------------------------------


class TestRetrieve:
    @respx.mock
    def test_top_k_returns_chunks_with_distance(
        self, pipeline: Pipeline, fake_pg: FakePgvector
    ) -> None:
        respx.post(f"{EMBED_URL}/embeddings").mock(
            return_value=httpx.Response(200, json=_embed_payload(1))
        )
        fake_pg.canned_rows = [
            (101, "wiki", "first chunk text", 0.10),
            (202, "blog", "second chunk text", 0.25),
            (303, "docs", "third chunk text", 0.40),
        ]
        chunks = pipeline.retrieve("what is X?", top_k=3)
        assert [c.id for c in chunks] == [101, 202, 303]
        assert chunks[0].label == "wiki"
        assert chunks[0].distance == pytest.approx(0.10)
        assert chunks[0].rerank_score is None
        # SELECT must use the cosine operator + LIMIT 3
        sel_sql, sel_params = fake_pg.calls[-1]
        assert "<=>" in sel_sql
        assert sel_params[-1] == 3

    @respx.mock
    def test_top_k_zero_returns_empty_no_calls(
        self, pipeline: Pipeline, fake_pg: FakePgvector
    ) -> None:
        # No HTTP route registered — if retrieve embedded, respx would fail.
        chunks = pipeline.retrieve("x", top_k=0)
        assert chunks == []
        assert fake_pg.calls == []  # no SQL either

    @respx.mock
    def test_passes_query_input_type(self, pipeline: Pipeline, fake_pg: FakePgvector) -> None:
        route = respx.post(f"{EMBED_URL}/embeddings").mock(
            return_value=httpx.Response(200, json=_embed_payload(1))
        )
        fake_pg.canned_rows = []
        pipeline.retrieve("hi", top_k=5)
        sent = route.calls.last.request.content
        assert b'"input_type":"query"' in sent.replace(b" ", b"")


# --- Rerank -------------------------------------------------------------


class TestRerank:
    def test_no_op_without_rerank_url(self, pipeline: Pipeline) -> None:
        chunks = [
            Chunk(id=1, text="a", distance=0.1),
            Chunk(id=2, text="b", distance=0.2),
            Chunk(id=3, text="c", distance=0.3),
        ]
        out = pipeline.rerank("q", chunks, top_k=2)
        # Pass-through: same order, top_k slice, no rerank_score added.
        assert [c.id for c in out] == [1, 2]
        assert all(c.rerank_score is None for c in out)

    def test_empty_input_short_circuit(self, pipeline: Pipeline) -> None:
        assert pipeline.rerank("q", [], top_k=3) == []

    @respx.mock
    def test_reranker_reorders_by_logit(self, generator: NIMClient) -> None:
        chunks = [
            Chunk(id=11, text="alpha", distance=0.5),
            Chunk(id=22, text="bravo", distance=0.4),
            Chunk(id=33, text="charlie", distance=0.6),
        ]
        respx.post(RERANK_URL).mock(
            return_value=httpx.Response(
                200,
                json={
                    "rankings": [
                        {"index": 2, "logit": 5.0},
                        {"index": 0, "logit": 1.5},
                        {"index": 1, "logit": -2.0},
                    ]
                },
            )
        )
        with Pipeline(
            embed_url=EMBED_URL,
            pgvector_dsn=PGV_DSN,
            generator=generator,
            embed_dim=EMBED_DIM,
            rerank_url=RERANK_URL,
            rerank_api_key="ngc-key",
            timeout=2.0,
        ) as p:
            out = p.rerank("q", chunks, top_k=2)
        # Reordered by logit desc, sliced to 2.
        assert [c.id for c in out] == [33, 11]
        assert out[0].rerank_score == 5.0
        assert out[0].distance == 0.6  # carried through

    @respx.mock
    def test_rerank_4xx_raises_RAGError(self, generator: NIMClient) -> None:
        respx.post(RERANK_URL).mock(return_value=httpx.Response(500, text="oops"))
        with Pipeline(
            embed_url=EMBED_URL,
            pgvector_dsn=PGV_DSN,
            generator=generator,
            embed_dim=EMBED_DIM,
            rerank_url=RERANK_URL,
            rerank_api_key="ngc-key",
            timeout=2.0,
        ) as p:
            with pytest.raises(RAGError):
                p.rerank("q", [Chunk(id=1, text="a")], top_k=1)


# --- build_messages / fuse / ask ----------------------------------------


class TestBuildMessages:
    def test_strict_system_present(self, pipeline: Pipeline) -> None:
        msgs = pipeline.build_messages("q?", [Chunk(id=1, text="alpha", label="L")])
        assert msgs[0]["role"] == "system"
        assert "ONLY the provided context" in msgs[0]["content"]

    def test_user_block_includes_id_and_label(self, pipeline: Pipeline) -> None:
        msgs = pipeline.build_messages(
            "q?",
            [Chunk(id=42, text="alpha", label="wiki"), Chunk(id=7, text="beta")],
        )
        body = msgs[1]["content"]
        assert "[42] (wiki) alpha" in body
        assert "[7] beta" in body
        assert "Question: q?" in body


class TestFuse:
    @respx.mock
    def test_calls_generator_with_grounded_messages(self, pipeline: Pipeline) -> None:
        respx.post(f"{GEN_URL}/chat/completions").mock(
            return_value=httpx.Response(200, json=_gen_response("an answer"))
        )
        out = pipeline.fuse("q?", [Chunk(id=1, text="hello")], max_tokens=16)
        assert out["choices"][0]["message"]["content"] == "an answer"
        sent = respx.routes[0].calls.last.request.content
        assert b'"role":"system"' in sent.replace(b" ", b"")
        assert b'"role":"user"' in sent.replace(b" ", b"")


class TestAsk:
    @respx.mock
    def test_end_to_end_dense_path(
        self, pipeline: Pipeline, fake_pg: FakePgvector
    ) -> None:
        respx.post(f"{EMBED_URL}/embeddings").mock(
            return_value=httpx.Response(200, json=_embed_payload(1))
        )
        respx.post(f"{GEN_URL}/chat/completions").mock(
            return_value=httpx.Response(200, json=_gen_response("the answer is 42. Sources: [101]"))
        )
        fake_pg.canned_rows = [
            (101, "wiki", "answer is 42", 0.05),
            (202, "blog", "tangentially related", 0.50),
        ]
        result = pipeline.ask("q?", retrieve_k=2, rerank_k=1, max_tokens=32)
        assert result["answer"].startswith("the answer is 42")
        # No rerank configured → first rerank_k chunks of retrieval are fed in.
        assert [c.id for c in result["chunks"]] == [101]
        assert result["raw"]["choices"][0]["message"]["content"].startswith("the answer is 42")

    @respx.mock
    def test_empty_retrieval_still_returns(
        self, pipeline: Pipeline, fake_pg: FakePgvector
    ) -> None:
        respx.post(f"{EMBED_URL}/embeddings").mock(
            return_value=httpx.Response(200, json=_embed_payload(1))
        )
        respx.post(f"{GEN_URL}/chat/completions").mock(
            return_value=httpx.Response(
                200, json=_gen_response("The provided context does not contain the answer.")
            )
        )
        fake_pg.canned_rows = []  # nothing to retrieve
        result = pipeline.ask("q?", retrieve_k=3, rerank_k=2)
        assert result["chunks"] == []
        assert "does not contain" in result["answer"]
