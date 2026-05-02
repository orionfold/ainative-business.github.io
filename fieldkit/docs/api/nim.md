---
module: nim
title: fieldkit.nim
summary: OpenAI-compatible NIM client with retries, context-overflow preflight, and a chunker that respects the 8192-token ceiling.
order: 2
---

## What it is

A thin, sync, OpenAI-compatible client for any locally-served NIM. Hardens the project's RAG pipelines against three landmines:

1. The opaque HTTP 400 NIM returns when a request would exceed its 8192-token context — caught **before any network call** by a token-estimate preflight.
2. Co-resident memory pressure on the Spark's unified pool — handled by tenacity-driven retries on 429 / 503 / connect / timeout.
3. NIM cold start (~96 s for Llama 3.1 8B) — `wait_for_warm` polls `/models` so callers don't race the warmup.

## Public API

```python
from fieldkit.nim import (
    NIMClient,
    NIM_CONTEXT_WINDOW,            # 8192
    DEFAULT_CHUNK_TOKENS,          # 1024
    chunk_text,
    estimate_tokens,
    wait_for_warm,
    NIMError,
    NIMHTTPError,
    NIMTimeoutError,
    NIMContextOverflowError,
)
```

### `NIMClient(base_url, model, api_key="local", timeout=60.0, max_retries=4)`

Sync, OpenAI-compatible. Context-manager friendly so the underlying `httpx.Client` closes deterministically.

```python
from fieldkit.nim import NIMClient

with NIMClient(base_url="http://localhost:8000/v1",
               model="meta/llama-3.1-8b-instruct") as c:
    raw = c.chat(
        messages=[{"role": "user", "content": "Summarise the DGX Spark."}],
        max_tokens=120,
        temperature=0.0,
    )
    print(raw["choices"][0]["message"]["content"])
```

`.chat()` retries 429 / 503 / `httpx.ConnectError` / `httpx.TimeoutException` via exponential backoff (0.5s → 8s, configurable via `max_retries`); explicitly does **not** retry 400. Retry exhaustion surfaces as `NIMTimeoutError`; 400 surfaces as `NIMHTTPError(status_code=400, body=...)`.

### `chunk_text(text, *, max_tokens=1024) -> list[str]`

Paragraph → sentence → word splitter under a char-based token budget (1 token ≈ 4 chars).

```python
from fieldkit.nim import chunk_text
chunks = chunk_text(long_doc, max_tokens=900)
```

### `wait_for_warm(base_url, timeout=120, poll_interval=2, api_key="local") -> bool`

Polls `/models` until 200 or timeout. Returns `True` on success, `False` on timeout. Use it as the first call in any sample script that talks to a cold NIM.

### Context-overflow preflight

`NIMClient.chat()` runs a token-estimate check on its message list and raises `NIMContextOverflowError(estimated_tokens, ceiling)` **before any network call** when the request would exceed `NIM_CONTEXT_WINDOW = 8192`. The opaque NIM 400 from `project_spark_nim_context_window` never surfaces.

## Errors

| Class | When |
|---|---|
| `NIMHTTPError` | Server returned 4xx (non-retryable) |
| `NIMTimeoutError` | Retry budget exhausted (429/503/connect/timeout) |
| `NIMContextOverflowError` | Preflight token-estimate exceeded `NIM_CONTEXT_WINDOW` |
| `NIMError` | Base class — catch this if you don't care which |

## Sample

[`samples/hello-nim.py`](https://github.com/manavsehgal/ai-field-notes/blob/main/fieldkit/samples/hello-nim.py) is the Python equivalent of the `nim-first-inference-dgx-spark` curl one-liner. Honors `NIM_BASE_URL` / `NIM_MODEL` / `NIM_PROMPT` env vars.
