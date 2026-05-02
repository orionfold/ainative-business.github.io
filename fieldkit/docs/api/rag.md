---
module: rag
title: fieldkit.rag
summary: Composable ingest → retrieve → rerank → fuse RAG pipeline backed by pgvector + a NIM embedder + the strict-context grounded prompt from `naive-rag-on-spark`.
order: 3
---

## What it is

The query-time RAG path the project's six retrieval articles converged on, lifted into one importable `Pipeline` class. Replaces ~250 lines of hand-rolled embed + pgvector + chat-completions glue per article.

The strict-context grounded prompt is reproduced verbatim from the article. Embed and rerank inherit `NIMClient.chat`'s retry policy, so co-resident memory pressure on the Spark's unified pool doesn't fail the pipeline.

## Public API

```python
from fieldkit.rag import (
    Pipeline,
    Document,
    Chunk,
    DEFAULT_EMBED_MODEL,           # "nvidia/llama-nemotron-embed-1b-v2"
    DEFAULT_EMBED_DIM,             # 1024
    DEFAULT_CHUNK_TOKENS,          # 900
    DEFAULT_RERANK_URL,
    DEFAULT_SYSTEM_PROMPT,
    RAGError,
)
```

### `Pipeline(embed_url, pgvector_dsn, generator: NIMClient, rerank_url=None, ...)`

Composable, context-manager friendly. One persistent `httpx.Client` for embed and (optionally) one for rerank. pgvector connections are short-lived per call so callers don't have to manage them.

```python
from fieldkit.nim import NIMClient
from fieldkit.rag import Document, Pipeline

with NIMClient(base_url="http://localhost:8000/v1",
               model="meta/llama-3.1-8b-instruct") as gen, \
     Pipeline(
         embed_url="http://localhost:8001/v1",
         pgvector_dsn="postgresql://spark:spark@localhost:5432/vectors",
         generator=gen,
     ) as pipe:
    pipe.ensure_schema()
    pipe.ingest([Document(id=1, text="...", label="spark")])
    result = pipe.ask("How much memory does the Spark have?",
                      retrieve_k=5, rerank_k=3, max_tokens=120)
    print(result["answer"])
```

### Pipeline methods

| Method | Returns | Notes |
|---|---|---|
| `ensure_schema()` | None | `CREATE EXTENSION IF NOT EXISTS vector` + `CREATE TABLE IF NOT EXISTS` at configured embed dim. Idempotent. |
| `ingest(docs, chunk_tokens=900)` | int | Chunks via `fieldkit.nim.chunk_text`, embeds in batches of 32, upserts in one transaction. Returns chunk count. |
| `retrieve(query, top_k=5)` | `list[Chunk]` | pgvector cosine `<=>`. Each chunk carries `distance`. |
| `rerank(query, chunks, top_k=3)` | `list[Chunk]` | Pass-through when `rerank_url=None` so the simplest pipeline works without NGC creds. |
| `fuse(query, chunks, **gen_kwargs)` | dict | Builds the strict-context prompt and calls the generator. |
| `ask(query, retrieve_k=5, rerank_k=3, ...)` | dict | Full chain. Returns `{"answer", "chunks", "raw"}`. |

### Chunk id encoding

Single-chunk docs keep their original id. Multi-chunk docs get `id = doc.id * 10000 + idx` so the doc → chunk relationship survives without an extra column.

### `Chunk.score`

Single "higher is better" score: rerank logit if available, else `1 - distance`. Fallback `0.0` if neither is set.

## Sample

[`samples/naive-rag.py`](https://github.com/manavsehgal/ai-field-notes/blob/main/fieldkit/samples/naive-rag.py) reproduces the `naive-rag-on-spark` flow end-to-end in ~30 lines: ensure schema → ingest 3 docs → ask one question.

## CLI

```bash
fieldkit bench rag --table fieldkit_cli_bench_rag --out /tmp/bench.json
```

Drives `Pipeline.ask` through `fieldkit.eval.Bench` against a 3-doc in-memory corpus and prints a markdown latency report. Requires the chat NIM, embed NIM, and pgvector to be reachable.
