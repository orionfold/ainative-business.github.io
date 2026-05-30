# Copyright 2026 Manav Sehgal
# SPDX-License-Identifier: Apache-2.0
"""End-to-end RAG primitive: ingest → retrieve → rerank → fuse.

Lifted from `naive-rag-on-spark`, `pgvector-on-spark`,
`nemo-retriever-embeddings-local`, `rerank-fusion-retrieval-on-spark`,
`bigger-generator-grounding-on-spark`, and `guardrails-on-the-retrieval-path`.
Each article shows one stage; this module wraps all four behind one
composable `Pipeline` and a one-line `.ask()` convenience.

Defaults match the project's verified-on-Spark stack:

- Embed NIM at `http://localhost:8001/v1` serving
  `nvidia/llama-nemotron-embed-1b-v2` at 1024-d (Matryoshka-truncated).
- pgvector container reachable via the configured DSN.
- Generator: any `fieldkit.nim.NIMClient`.
- Rerank is **opt-in**: pass `rerank_url=DEFAULT_RERANK_URL` (NGC's hosted
  endpoint, `rerank_api_key=os.environ["NGC_API_KEY"]`) because the local
  reranker NIM doesn't yet run on GB10 (see article
  `rerank-fusion-retrieval-on-spark`).

The strict-context system prompt is the same one used across the project's
RAG articles. Override via `Pipeline(system_prompt=...)` when you need a
different policy.

`.ingest()` chunks by token budget (default 900 tokens, ~3600 chars under
the 4-chars-per-token estimate), embeds in batches of 32, and upserts to
pgvector. Each chunk gets `id = doc.id * CHUNKS_PER_DOC_MAX + idx`, so a
single doc may produce up to `CHUNKS_PER_DOC_MAX = 10000` chunks before
the encoding overflows. Documents that fit in one chunk keep their
original `id` (idx 0).

For schema setup see `Pipeline.ensure_schema()`. The default table is
named `chunks` and its column types match the project's article series.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from typing import Any

import httpx
import psycopg
from tenacity import (
    Retrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from fieldkit.nim import DEFAULT_CHUNK_TOKENS as _NIM_DEFAULT_CHUNK_TOKENS
from fieldkit.nim import NIMClient, chunk_text

__all__ = [
    "Pipeline",
    "Chunk",
    "Document",
    "RAGError",
    "DEFAULT_EMBED_MODEL",
    "DEFAULT_EMBED_DIM",
    "DEFAULT_EMBED_BATCH",
    "DEFAULT_CHUNK_TOKENS",
    "CHUNKS_PER_DOC_MAX",
    "DEFAULT_RERANK_URL",
    "DEFAULT_RERANK_MODEL",
    "DEFAULT_SYSTEM_PROMPT",
]


DEFAULT_EMBED_MODEL: str = "nvidia/llama-nemotron-embed-1b-v2"
"""The 1024-d Matryoshka embedder used across the project's RAG articles."""

DEFAULT_EMBED_DIM: int = 1024
"""1024-d gives a ~50% storage cut vs native 2048-d at ~4 recall points;
the quality/storage sweet spot per `nemo-retriever-embeddings-local`."""

DEFAULT_EMBED_BATCH: int = 32
"""Per-call passage batch size; matches the article #4 sweet spot of ~28 docs/s."""

DEFAULT_CHUNK_TOKENS: int = 900
"""Per-chunk token budget for `.ingest()`. Five chunks at this budget still
fit comfortably under `fieldkit.nim.NIM_CONTEXT_WINDOW = 8192` with room
for the system + query + answer envelope.

Always smaller than `fieldkit.nim.DEFAULT_CHUNK_TOKENS` (=1024) so a top-3
retrieval with this chunk size ≈ 2700 prompt tokens — well below the
ceiling. See `project_spark_nim_context_window` memory for the rationale."""

CHUNKS_PER_DOC_MAX: int = 10000
"""Max chunks per document. The chunk id encoding is
`doc.id * CHUNKS_PER_DOC_MAX + chunk_idx` so doc-level grouping survives
without an extra column."""

DEFAULT_RERANK_URL: str = (
    "https://ai.api.nvidia.com/v1/retrieval/nvidia/llama-3_2-nv-rerankqa-1b-v2/reranking"
)
"""NGC's hosted reranker. Local Spark TRT plans not yet available on GB10
(per `rerank-fusion-retrieval-on-spark`); when they are, point at
`http://localhost:8002/v1/...` instead and the API stays the same."""

DEFAULT_RERANK_MODEL: str = "nvidia/llama-3.2-nv-rerankqa-1b-v2"

DEFAULT_SYSTEM_PROMPT: str = (
    "You are a careful assistant. Answer the user's question using ONLY the "
    "provided context passages. Each passage is prefixed with its row id in "
    "square brackets like [123]. If the answer is present, state it plainly "
    "and cite the ids you used in a trailing 'Sources: [id, id]' line. If "
    "the context does not contain the answer, reply with exactly one "
    "sentence: 'The provided context does not contain the answer.' Do not "
    "fall back to general knowledge."
)
"""Strict-context prompt used across the project's RAG articles. Reused
verbatim by `naive-rag-on-spark`, `bigger-generator-grounding-on-spark`,
and `guardrails-on-the-retrieval-path`."""


# Sanity invariant: keep the rag default tighter than the nim default.
assert DEFAULT_CHUNK_TOKENS <= _NIM_DEFAULT_CHUNK_TOKENS


# --- Errors --------------------------------------------------------------


class RAGError(Exception):
    """Base class for `fieldkit.rag` errors."""


class _RetryableRAGError(RAGError):
    """Internal sentinel for tenacity. Callers should catch `RAGError` instead."""


# --- Public types --------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Document:
    """One document handed to `Pipeline.ingest()`.

    `id` is the user-owned stable identifier. If a document is split into
    multiple chunks the chunks get ids `id * CHUNKS_PER_DOC_MAX + idx`;
    a doc that fits in one chunk keeps its original `id`.
    """

    id: int
    text: str
    label: str = ""


@dataclass(frozen=True, slots=True)
class Chunk:
    """One retrieved chunk with retrieval / rerank scores attached."""

    id: int
    text: str
    label: str = ""
    distance: float | None = None
    """pgvector cosine distance; lower = closer."""

    rerank_score: float | None = None
    """Reranker logit; higher = more relevant."""

    @property
    def score(self) -> float:
        """Single 'higher is better' score: rerank logit if available, else
        `1 - distance`. Fallback `0.0` if neither is set."""
        if self.rerank_score is not None:
            return self.rerank_score
        if self.distance is not None:
            return 1.0 - self.distance
        return 0.0


# --- Pipeline ------------------------------------------------------------


@dataclass
class Pipeline:
    """Composable ingest → retrieve → rerank → fuse RAG pipeline.

    Construction is cheap: opens long-lived HTTP clients for embed and
    (optionally) rerank. pgvector connections are short-lived per
    `.ingest()` / `.retrieve()` call so callers don't have to manage them.

    The pipeline is a context manager — use `with Pipeline(...) as p:` to
    release the embed/rerank `httpx.Client`s deterministically.
    """

    embed_url: str
    pgvector_dsn: str
    generator: NIMClient
    rerank_url: str | None = None
    rerank_api_key: str | None = None
    rerank_model: str = DEFAULT_RERANK_MODEL
    embed_model: str = DEFAULT_EMBED_MODEL
    embed_dim: int = DEFAULT_EMBED_DIM
    embed_api_key: str = "local"
    embed_batch: int = DEFAULT_EMBED_BATCH
    table: str = "chunks"
    chunk_tokens: int = DEFAULT_CHUNK_TOKENS
    system_prompt: str = DEFAULT_SYSTEM_PROMPT
    timeout: float = 60.0
    max_retries: int = 4
    """Retry budget for transient embed / rerank failures (429, 503, connect
    errors, timeouts). Mirrors `NIMClient.max_retries` so co-resident NIM
    memory pressure on the Spark's unified pool doesn't fail the pipeline."""

    _embed_client: httpx.Client | None = field(default=None, init=False, repr=False)
    _rerank_client: httpx.Client | None = field(default=None, init=False, repr=False)

    def __post_init__(self) -> None:
        if self.embed_batch <= 0:
            raise ValueError("embed_batch must be positive")
        if self.embed_dim <= 0:
            raise ValueError("embed_dim must be positive")
        if self.chunk_tokens <= 0:
            raise ValueError("chunk_tokens must be positive")
        self.embed_url = self.embed_url.rstrip("/")
        self._embed_client = httpx.Client(
            base_url=self.embed_url,
            headers={"Authorization": f"Bearer {self.embed_api_key}"},
            timeout=self.timeout,
        )
        if self.rerank_url:
            key = self.rerank_api_key or self.embed_api_key
            self._rerank_client = httpx.Client(
                headers={
                    "Authorization": f"Bearer {key}",
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                },
                timeout=self.timeout,
            )

    def close(self) -> None:
        if self._embed_client is not None:
            self._embed_client.close()
            self._embed_client = None
        if self._rerank_client is not None:
            self._rerank_client.close()
            self._rerank_client = None

    def __enter__(self) -> Pipeline:
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    # -- Schema helper -----------------------------------------------------

    def ensure_schema(self) -> None:
        """`CREATE EXTENSION IF NOT EXISTS vector` + `CREATE TABLE IF NOT EXISTS`
        for the configured table at the configured embedding dim. Idempotent;
        safe to call from sample scripts and tests.

        Existing tables are *not* altered — if `embed_dim` changes between
        runs, drop the table manually first.
        """
        sql = (
            "CREATE EXTENSION IF NOT EXISTS vector; "
            f"CREATE TABLE IF NOT EXISTS {self.table} ("
            "  id BIGINT PRIMARY KEY,"
            "  label TEXT,"
            "  text TEXT NOT NULL,"
            f"  embedding vector({self.embed_dim}) NOT NULL"
            ");"
        )
        with psycopg.connect(self.pgvector_dsn) as conn, conn.cursor() as cur:
            cur.execute(sql)
            conn.commit()

    # -- Ingest ------------------------------------------------------------

    def ingest(
        self,
        documents: Iterable[Document | dict[str, Any]],
        *,
        chunk_tokens: int | None = None,
    ) -> int:
        """Chunk + embed + upsert. Returns the number of chunks written.

        `documents` may yield `Document` instances or dicts with `id`, `text`,
        and optional `label` keys. Each doc is split into ≤ `chunk_tokens`-token
        chunks; embeddings are produced in batches of `embed_batch`, and the
        whole batch is upserted to pgvector inside one transaction.
        """
        budget = chunk_tokens or self.chunk_tokens
        rows: list[tuple[int, str, str, list[float]]] = []
        pending_texts: list[str] = []
        pending_meta: list[tuple[int, str]] = []  # (chunk_id, label)

        def flush() -> None:
            if not pending_texts:
                return
            vectors = self._embed(pending_texts, input_type="passage")
            for (cid, label), text, vec in zip(
                pending_meta, pending_texts, vectors, strict=True
            ):
                rows.append((cid, label, text, vec))
            pending_texts.clear()
            pending_meta.clear()

        for doc in documents:
            d = _coerce_doc(doc)
            chunks = chunk_text(d.text, max_tokens=budget)
            non_empty = [c for c in chunks if c.strip()]
            if not non_empty:
                continue
            single = len(non_empty) == 1
            for i, chunk in enumerate(non_empty):
                if i >= CHUNKS_PER_DOC_MAX:
                    raise RAGError(
                        f"document {d.id} produced more than "
                        f"{CHUNKS_PER_DOC_MAX} chunks; raise CHUNKS_PER_DOC_MAX "
                        "or pre-split the document into smaller documents"
                    )
                cid = d.id if single else d.id * CHUNKS_PER_DOC_MAX + i
                pending_texts.append(chunk)
                pending_meta.append((cid, d.label))
                if len(pending_texts) >= self.embed_batch:
                    flush()
        flush()

        self._upsert(rows)
        return len(rows)

    # -- Retrieve ----------------------------------------------------------

    def retrieve(self, query: str, *, top_k: int = 5) -> list[Chunk]:
        """Dense top-K via pgvector cosine distance (`<=>` operator).

        Empty corpus returns `[]`. Distance is the raw `<=>` value: lower
        is closer.
        """
        if top_k <= 0:
            return []
        qvec = self._embed([query], input_type="query")[0]
        vec_literal = _vec_literal(qvec)
        sql = (
            f"SELECT id, label, text, (embedding <=> %s::vector) AS dist "
            f"FROM {self.table} "
            f"ORDER BY embedding <=> %s::vector "
            f"LIMIT %s"
        )
        with psycopg.connect(self.pgvector_dsn) as conn, conn.cursor() as cur:
            cur.execute(sql, (vec_literal, vec_literal, int(top_k)))
            rows = cur.fetchall()
        return [
            Chunk(id=int(rid), label=label or "", text=text, distance=float(dist))
            for rid, label, text, dist in rows
        ]

    # -- Rerank ------------------------------------------------------------

    def rerank(
        self, query: str, chunks: Sequence[Chunk], *, top_k: int = 3
    ) -> list[Chunk]:
        """Reorder via the configured reranker and slice to `top_k`.

        Pass-through when `rerank_url` is None or the input is empty: the
        first `top_k` chunks are returned unchanged. This is intentional —
        the local reranker NIM doesn't yet run on GB10, so callers without
        NGC creds still get a usable pipeline (just no rerank stage).
        """
        if not chunks:
            return []
        if self.rerank_url is None or self._rerank_client is None:
            return list(chunks[: int(top_k)])
        body = {
            "model": self.rerank_model,
            "query": {"text": query},
            "passages": [{"text": c.text} for c in chunks],
        }
        try:
            r = self._post_with_retry(
                self._rerank_client, self.rerank_url, body, label="rerank"
            )
        except httpx.HTTPError as exc:
            raise RAGError(f"rerank request failed: {exc}") from exc
        rankings = r.json().get("rankings", [])
        out: list[Chunk] = []
        for entry in rankings[: int(top_k)]:
            idx = int(entry["index"])
            base = chunks[idx]
            out.append(
                Chunk(
                    id=base.id,
                    label=base.label,
                    text=base.text,
                    distance=base.distance,
                    rerank_score=float(entry["logit"]),
                )
            )
        return out

    # -- Fuse / Ask --------------------------------------------------------

    def fuse(
        self,
        query: str,
        chunks: Sequence[Chunk],
        *,
        max_tokens: int = 256,
        temperature: float = 0.0,
        **gen_kwargs: Any,
    ) -> dict[str, Any]:
        """Build the grounded prompt and call the generator.

        Returns the raw chat-completions response. The prompt overflow check
        from `fieldkit.nim` runs as a pre-flight inside `generator.chat()`,
        so over-long retrievals raise `NIMContextOverflowError` *before* any
        network call.
        """
        messages = self.build_messages(query, chunks)
        return self.generator.chat(
            messages, max_tokens=max_tokens, temperature=temperature, **gen_kwargs
        )

    def ask(
        self,
        query: str,
        *,
        retrieve_k: int = 5,
        rerank_k: int = 3,
        max_tokens: int = 256,
        temperature: float = 0.0,
    ) -> dict[str, Any]:
        """retrieve → rerank → fuse, in one call.

        Returns ``{"answer": str, "chunks": list[Chunk], "raw": dict}`` where
        `chunks` is the list actually fed to the generator (post-rerank if
        rerank is configured, else the first `rerank_k` of retrieved).
        """
        retrieved = self.retrieve(query, top_k=retrieve_k)
        ranked = self.rerank(query, retrieved, top_k=rerank_k) if retrieved else []
        if not ranked and retrieved:
            ranked = retrieved[:rerank_k]
        raw = self.fuse(query, ranked, max_tokens=max_tokens, temperature=temperature)
        choices = raw.get("choices") or []
        answer = ""
        if choices:
            content = choices[0].get("message", {}).get("content")
            if isinstance(content, str):
                answer = content.strip()
        return {"answer": answer, "chunks": list(ranked), "raw": raw}

    def build_messages(
        self, query: str, chunks: Sequence[Chunk]
    ) -> list[dict[str, Any]]:
        """Strict-context message list lifted verbatim from the project's
        RAG articles. Override `system_prompt` to swap the policy."""
        context_block = "\n".join(
            f"[{c.id}] ({c.label}) {c.text}" if c.label else f"[{c.id}] {c.text}"
            for c in chunks
        )
        user = f"Context passages:\n{context_block}\n\nQuestion: {query}"
        return [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": user},
        ]

    # -- Internals ---------------------------------------------------------

    def _embed(
        self, texts: Sequence[str], *, input_type: str
    ) -> list[list[float]]:
        if self._embed_client is None:
            raise RAGError("pipeline closed")
        body = {
            "model": self.embed_model,
            "input": list(texts),
            "input_type": input_type,
            "encoding_format": "float",
            "truncate": "END",
            "dimensions": self.embed_dim,
        }
        try:
            r = self._post_with_retry(self._embed_client, "/embeddings", body, label="embed")
        except httpx.HTTPError as exc:
            raise RAGError(f"embed request failed: {exc}") from exc
        data = sorted(r.json()["data"], key=lambda d: int(d["index"]))
        return [list(d["embedding"]) for d in data]

    def _post_with_retry(
        self,
        client: httpx.Client,
        url: str,
        body: dict[str, Any],
        *,
        label: str,
    ) -> httpx.Response:
        """POST with the same retry policy as `NIMClient.chat`.

        Retries on 429 / 503 and `httpx.ConnectError` / `TimeoutException`.
        Non-retryable errors (4xx other than 429) re-raise immediately as
        `httpx.HTTPStatusError`. Retry exhaustion lets the last underlying
        exception propagate; callers wrap it in `RAGError`.
        """
        retrying = Retrying(
            reraise=True,
            stop=stop_after_attempt(self.max_retries + 1),
            wait=wait_exponential(multiplier=0.5, min=0.5, max=8.0),
            retry=retry_if_exception_type(_RetryableRAGError),
        )
        for attempt in retrying:
            with attempt:
                try:
                    r = client.post(url, json=body)
                except httpx.TimeoutException as exc:
                    raise _RetryableRAGError(f"{label} timeout: {exc}") from exc
                except httpx.ConnectError as exc:
                    raise _RetryableRAGError(f"{label} connect error: {exc}") from exc
                if r.status_code in (429, 503):
                    raise _RetryableRAGError(f"{label} {r.status_code}: {r.text[:200]}")
                r.raise_for_status()
                return r
        raise RAGError("unreachable")  # pragma: no cover

    def _upsert(
        self, rows: Sequence[tuple[int, str, str, list[float]]]
    ) -> None:
        if not rows:
            return
        sql = (
            f"INSERT INTO {self.table} (id, label, text, embedding) "
            f"VALUES (%s, %s, %s, %s::vector) "
            "ON CONFLICT (id) DO UPDATE SET "
            "label = EXCLUDED.label, "
            "text = EXCLUDED.text, "
            "embedding = EXCLUDED.embedding"
        )
        with psycopg.connect(self.pgvector_dsn) as conn, conn.cursor() as cur:
            for cid, label, text, vec in rows:
                cur.execute(sql, (cid, label, text, _vec_literal(vec)))
            conn.commit()


# --- Helpers -------------------------------------------------------------


def _coerce_doc(d: Document | dict[str, Any]) -> Document:
    if isinstance(d, Document):
        return d
    return Document(
        id=int(d["id"]), text=str(d["text"]), label=str(d.get("label", ""))
    )


def _vec_literal(v: Sequence[float]) -> str:
    return "[" + ",".join(f"{x:.6f}" for x in v) + "]"
