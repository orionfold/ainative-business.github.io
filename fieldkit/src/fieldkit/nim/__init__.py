# Copyright 2026 Manav Sehgal
# SPDX-License-Identifier: Apache-2.0
"""OpenAI-compatible client wrapper for NVIDIA NIM endpoints.

Captures the project's verified-on-Spark patterns:

- Retry on 429 / 503 / network errors via `tenacity`. No retry on 400 — bad
  requests stay bad. The 8192-token context-overflow case in the project
  (`project_spark_nim_context_window` memory) is detected *before* the call
  and raised as `NIMContextOverflowError` so the underlying opaque 400 from
  NIM never surfaces.
- `chunk_text(...)` (also exposed as `NIMClient.chunk(...)`) breaks long
  text at paragraph → sentence → word boundaries with a token-budget guard.
  Default `max_tokens=1024` keeps a top-3 generation prompt comfortably
  inside 8192.
- `wait_for_warm(...)` polls `/v1/models` for the ~90s NIM cold-start
  window so callers can launch a container then call into it.

The token estimate is a 1-token ≈ 4-character heuristic — robust enough for
budget guards, never used for billing. Swap in a real BPE tokenizer when
one is needed; the API is `estimate_tokens(text) -> int`.
"""

from __future__ import annotations

import re
import time
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Any

import httpx
from tenacity import (
    Retrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

__all__ = [
    "NIM_CONTEXT_WINDOW",
    "DEFAULT_CHUNK_TOKENS",
    "NIMClient",
    "NIMError",
    "NIMHTTPError",
    "NIMTimeoutError",
    "NIMContextOverflowError",
    "ChatMessage",
    "chunk_text",
    "estimate_tokens",
    "wait_for_warm",
]


NIM_CONTEXT_WINDOW: int = 8192
"""NIM's default context ceiling. Chunking math must respect this.

Source: `project_spark_nim_context_window` memory and the JSON capability
map's `nim.known_limits` entry.
"""

DEFAULT_CHUNK_TOKENS: int = 1024
"""Default per-chunk token budget. Five of these still fit in NIM_CONTEXT_WINDOW
with room for system + query + answer; production RAG paths typically use
top-3 of these (see `bigger-generator-grounding-on-spark`)."""

CHARS_PER_TOKEN_ESTIMATE: float = 4.0
"""Rough upper bound for English / code text under Llama-class BPE tokenizers.
Used only for budget guards — never for billing or exact accounting."""


ChatMessage = dict[str, Any]
"""OpenAI-style chat message: `{"role": "system" | "user" | "assistant", "content": ...}`."""


# --- Errors --------------------------------------------------------------


class NIMError(Exception):
    """Base class for fieldkit.nim errors."""


class NIMHTTPError(NIMError):
    """A non-retryable HTTP error from NIM (4xx other than 429, or 5xx after retries)."""

    def __init__(self, message: str, *, status_code: int, body: str | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.body = body


class NIMTimeoutError(NIMError):
    """A network or request timeout that didn't resolve within retry budget."""


class NIMContextOverflowError(NIMError):
    """Request would exceed `NIM_CONTEXT_WINDOW`; raised *before* the call.

    Carries the estimated token count so callers can decide whether to chunk
    further, drop top-K, or trim the system prompt.
    """

    def __init__(self, *, estimated_tokens: int, ceiling: int) -> None:
        super().__init__(
            f"request estimated at {estimated_tokens} tokens; NIM ceiling is {ceiling}. "
            "Chunk inputs further (chunk_text(..., max_tokens=...)) or lower top-K."
        )
        self.estimated_tokens = estimated_tokens
        self.ceiling = ceiling


# --- Token + chunking utilities -----------------------------------------


def estimate_tokens(text: str) -> int:
    """Cheap upper-bound token estimate (1 token ≈ 4 chars).

    Robust enough to drive budget guards; do not use for billing. Returns
    `ceil(len(text) / CHARS_PER_TOKEN_ESTIMATE)`.
    """
    if not text:
        return 0
    return -(-len(text) // int(CHARS_PER_TOKEN_ESTIMATE))


_PARAGRAPH_SPLIT_RE = re.compile(r"\n\s*\n")
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+(?=[A-Z\"'(\[])")
_WHITESPACE_RE = re.compile(r"\s+")


def chunk_text(text: str, *, max_tokens: int = DEFAULT_CHUNK_TOKENS) -> list[str]:
    """Break `text` into chunks of approximately `max_tokens` tokens each.

    Boundary preference: blank-line paragraph → sentence → word. Preserves
    the original whitespace inside chunks. Returns at minimum one chunk
    (possibly empty if `text` is empty).
    """
    if max_tokens <= 0:
        raise ValueError("max_tokens must be positive")
    if not text:
        return [""]
    max_chars = int(max_tokens * CHARS_PER_TOKEN_ESTIMATE)

    chunks: list[str] = []
    buf = ""

    def flush() -> None:
        nonlocal buf
        if buf:
            chunks.append(buf)
            buf = ""

    paragraphs = _PARAGRAPH_SPLIT_RE.split(text)
    for paragraph in paragraphs:
        candidate = (buf + "\n\n" + paragraph) if buf else paragraph
        if len(candidate) <= max_chars:
            buf = candidate
            continue

        if buf:
            flush()

        if len(paragraph) <= max_chars:
            buf = paragraph
            continue

        for sentence_chunk in _split_long_block(paragraph, max_chars):
            if buf and len(buf) + 1 + len(sentence_chunk) <= max_chars:
                buf = buf + " " + sentence_chunk
            else:
                flush()
                buf = sentence_chunk

    flush()
    return chunks if chunks else [""]


def _split_long_block(block: str, max_chars: int) -> Iterable[str]:
    """Split one long paragraph into ≤ max_chars pieces, sentence-first then word."""
    sentences = _SENTENCE_SPLIT_RE.split(block) if len(block) > max_chars else [block]
    for sentence in sentences:
        if len(sentence) <= max_chars:
            yield sentence
            continue
        words = _WHITESPACE_RE.split(sentence)
        buf = ""
        for word in words:
            candidate = (buf + " " + word) if buf else word
            if len(candidate) <= max_chars:
                buf = candidate
            else:
                if buf:
                    yield buf
                buf = word
        if buf:
            yield buf


def _messages_token_estimate(messages: Sequence[ChatMessage]) -> int:
    total = 0
    for msg in messages:
        content = msg.get("content", "")
        if isinstance(content, str):
            total += estimate_tokens(content)
        elif isinstance(content, list):
            for part in content:
                if isinstance(part, dict):
                    total += estimate_tokens(str(part.get("text", "")))
        total += 4  # rough per-message envelope tax
    return total


# --- Health + warm-up ----------------------------------------------------


def wait_for_warm(
    base_url: str,
    *,
    timeout: float = 120.0,
    poll_interval: float = 2.0,
    api_key: str = "local",
) -> bool:
    """Block until `base_url`/v1/models returns 200 or `timeout` seconds elapse.

    Returns True if the endpoint warmed in time, False otherwise. Designed for
    NIM's ~90-second cold-start window after `docker run`.
    """
    deadline = time.monotonic() + timeout
    headers = {"Authorization": f"Bearer {api_key}"}
    url = base_url.rstrip("/") + "/models"
    with httpx.Client(timeout=poll_interval) as client:
        while time.monotonic() < deadline:
            try:
                r = client.get(url, headers=headers)
                if r.status_code == 200:
                    return True
            except httpx.HTTPError:
                pass
            time.sleep(poll_interval)
    return False


# --- Client --------------------------------------------------------------


@dataclass
class NIMClient:
    """OpenAI-compatible client for NVIDIA NIM endpoints.

    Defaults match the project's verified-on-Spark setup:
    - `base_url` like `"http://localhost:8000/v1"` for the local 8B NIM
    - `api_key="local"` (NIM accepts any non-empty bearer token by default)
    - `timeout=60` covers the longest realistic NIM completion at this scale

    `max_retries` shapes the tenacity policy used by `.chat()`. Set to 0 to
    disable retries (useful for tests that want to assert the raw error).
    """

    base_url: str
    model: str
    api_key: str = "local"
    timeout: float = 60.0
    max_retries: int = 4
    _client: httpx.Client | None = None

    def __post_init__(self) -> None:
        self.base_url = self.base_url.rstrip("/")
        self._client = httpx.Client(
            base_url=self.base_url,
            headers={"Authorization": f"Bearer {self.api_key}"},
            timeout=self.timeout,
        )

    def close(self) -> None:
        if self._client is not None:
            self._client.close()
            self._client = None

    def __enter__(self) -> "NIMClient":
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    @staticmethod
    def chunk(text: str, *, max_tokens: int = DEFAULT_CHUNK_TOKENS) -> list[str]:
        """Static alias for `chunk_text` so `client.chunk(...)` works."""
        return chunk_text(text, max_tokens=max_tokens)

    def health(self) -> bool:
        """Ping `/models` and return True iff it responds 200."""
        if self._client is None:
            raise NIMError("client closed")
        try:
            r = self._client.get("/models")
        except httpx.HTTPError:
            return False
        return r.status_code == 200

    def chat(
        self,
        messages: Sequence[ChatMessage],
        *,
        max_tokens: int = 512,
        temperature: float = 0.0,
        **extra: Any,
    ) -> dict[str, Any]:
        """Call `/chat/completions` with retry on 429/503/network errors.

        Pre-flight: refuses to send if the request would exceed
        `NIM_CONTEXT_WINDOW`; raises `NIMContextOverflowError` instead of
        getting an opaque 400 back.

        Returns the parsed JSON body (`{"choices": [...], ...}`).
        """
        if self._client is None:
            raise NIMError("client closed")

        prompt_tokens = _messages_token_estimate(messages)
        if prompt_tokens + max_tokens > NIM_CONTEXT_WINDOW:
            raise NIMContextOverflowError(
                estimated_tokens=prompt_tokens + max_tokens,
                ceiling=NIM_CONTEXT_WINDOW,
            )

        payload: dict[str, Any] = {
            "model": self.model,
            "messages": list(messages),
            "max_tokens": max_tokens,
            "temperature": temperature,
            **extra,
        }

        retrying = Retrying(
            reraise=True,
            stop=stop_after_attempt(self.max_retries + 1),
            wait=wait_exponential(multiplier=0.5, min=0.5, max=8.0),
            retry=retry_if_exception_type(_RetryableNIMError),
        )
        try:
            for attempt in retrying:
                with attempt:
                    return self._chat_once(payload)
        except _RetryableNIMError as exc:
            raise NIMTimeoutError(
                f"NIM request failed after {self.max_retries + 1} attempts: {exc}"
            ) from exc
        raise NIMError("unreachable")  # pragma: no cover

    def _chat_once(self, payload: dict[str, Any]) -> dict[str, Any]:
        if self._client is None:
            raise NIMError("client closed")
        try:
            r = self._client.post("/chat/completions", json=payload)
        except httpx.TimeoutException as exc:
            raise _RetryableNIMError(f"timeout: {exc}") from exc
        except httpx.ConnectError as exc:
            raise _RetryableNIMError(f"connect error: {exc}") from exc
        except httpx.HTTPError as exc:
            raise NIMError(f"transport error: {exc}") from exc

        if r.status_code in (429, 503):
            raise _RetryableNIMError(f"NIM {r.status_code}: {r.text[:200]}")
        if r.status_code >= 400:
            raise NIMHTTPError(
                f"NIM {r.status_code}: {r.text[:200]}",
                status_code=r.status_code,
                body=r.text,
            )
        return r.json()


class _RetryableNIMError(NIMError):
    """Internal sentinel for tenacity. Callers should catch `NIMError` instead."""
