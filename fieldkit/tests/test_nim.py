# Copyright 2026 Manav Sehgal
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for fieldkit.nim — respx-backed, no real network.

Spark-live integration test lives in test_nim_spark.py and is gated by
`pytest --spark`.
"""

from __future__ import annotations

import httpx
import pytest
import respx

from fieldkit.nim import (
    DEFAULT_CHUNK_TOKENS,
    NIM_CONTEXT_WINDOW,
    NIMClient,
    NIMContextOverflowError,
    NIMHTTPError,
    NIMTimeoutError,
    chunk_text,
    estimate_tokens,
    wait_for_warm,
)


BASE_URL = "http://nim.test/v1"
MODEL = "meta/llama-3.1-8b-instruct"


def _ok_response(content: str = "ok") -> dict:
    return {
        "id": "chatcmpl-test",
        "object": "chat.completion",
        "model": MODEL,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 5, "completion_tokens": 1, "total_tokens": 6},
    }


@pytest.fixture
def client() -> NIMClient:
    c = NIMClient(base_url=BASE_URL, model=MODEL, max_retries=2, timeout=2.0)
    yield c
    c.close()


# --- estimate_tokens / chunk_text ----------------------------------------


class TestEstimateTokens:
    def test_empty(self) -> None:
        assert estimate_tokens("") == 0

    def test_rough_4_chars_per_token(self) -> None:
        assert estimate_tokens("x" * 4) == 1
        assert estimate_tokens("x" * 4096) == 1024

    def test_rounds_up(self) -> None:
        # 5 chars → ceil(5/4) = 2 tokens, not 1.
        assert estimate_tokens("hello") == 2


class TestChunkText:
    def test_empty_returns_one_empty_chunk(self) -> None:
        assert chunk_text("") == [""]

    def test_short_stays_single_chunk(self) -> None:
        chunks = chunk_text("hello world", max_tokens=DEFAULT_CHUNK_TOKENS)
        assert chunks == ["hello world"]

    def test_long_paragraphs_split_at_blank_lines(self) -> None:
        para = "x" * 200
        text = "\n\n".join([para] * 5)
        # max_tokens=60 → ~240 chars per chunk; each para ≤ that, so each para
        # gets its own chunk (joining two would exceed the budget).
        chunks = chunk_text(text, max_tokens=60)
        assert len(chunks) == 5
        for c in chunks:
            assert c == para

    def test_oversized_paragraph_splits_at_word_boundary(self) -> None:
        # One paragraph, 100 words, ≈ 6 chars each = 600 chars total.
        words = ["word"] * 100
        text = " ".join(words)
        chunks = chunk_text(text, max_tokens=20)  # ~80 chars per chunk
        assert len(chunks) > 1
        for c in chunks:
            # Each chunk must be ≤ 20 tokens worth (~80 chars).
            assert len(c) <= 80
        # Reassembling chunks should match the source word-for-word.
        assert " ".join(chunks).split() == words

    def test_rejects_non_positive_max_tokens(self) -> None:
        with pytest.raises(ValueError):
            chunk_text("anything", max_tokens=0)


# --- Context-overflow preflight ------------------------------------------


class TestContextOverflow:
    def test_blocks_oversized_request_before_call(self, client: NIMClient) -> None:
        oversized = [{"role": "user", "content": "x" * (NIM_CONTEXT_WINDOW * 5)}]
        with pytest.raises(NIMContextOverflowError) as exc:
            client.chat(oversized, max_tokens=512)
        assert exc.value.estimated_tokens > NIM_CONTEXT_WINDOW
        assert exc.value.ceiling == NIM_CONTEXT_WINDOW

    def test_overflow_skips_network(self, client: NIMClient) -> None:
        # If the preflight didn't fire, respx with no routes would raise.
        with respx.mock(base_url=BASE_URL, assert_all_called=True):
            oversized = [{"role": "user", "content": "x" * (NIM_CONTEXT_WINDOW * 5)}]
            with pytest.raises(NIMContextOverflowError):
                client.chat(oversized, max_tokens=512)
            # respx exits cleanly because no routes had to be called.


# --- chat() success + retry policy ---------------------------------------


class TestChatSuccess:
    @respx.mock
    def test_success_returns_parsed_body(self, client: NIMClient) -> None:
        respx.post(f"{BASE_URL}/chat/completions").mock(
            return_value=httpx.Response(200, json=_ok_response("hi"))
        )
        result = client.chat(
            [{"role": "user", "content": "hi"}], max_tokens=32, temperature=0.5
        )
        assert result["choices"][0]["message"]["content"] == "hi"
        # Confirm we sent the model + temperature through.
        sent = respx.routes[0].calls.last.request
        assert b'"temperature":0.5' in sent.content.replace(b" ", b"")
        assert b'"model":"meta/llama-3.1-8b-instruct"' in sent.content.replace(b" ", b"")


class TestChatRetry:
    @respx.mock
    def test_retries_429_then_succeeds(self, client: NIMClient) -> None:
        route = respx.post(f"{BASE_URL}/chat/completions").mock(
            side_effect=[
                httpx.Response(429, text="rate limited"),
                httpx.Response(200, json=_ok_response("recovered")),
            ]
        )
        result = client.chat([{"role": "user", "content": "hi"}], max_tokens=8)
        assert result["choices"][0]["message"]["content"] == "recovered"
        assert route.call_count == 2

    @respx.mock
    def test_retries_503_then_succeeds(self, client: NIMClient) -> None:
        route = respx.post(f"{BASE_URL}/chat/completions").mock(
            side_effect=[
                httpx.Response(503, text="warming"),
                httpx.Response(200, json=_ok_response("warmed")),
            ]
        )
        result = client.chat([{"role": "user", "content": "hi"}], max_tokens=8)
        assert result["choices"][0]["message"]["content"] == "warmed"
        assert route.call_count == 2

    @respx.mock
    def test_retries_connect_error_then_succeeds(self, client: NIMClient) -> None:
        route = respx.post(f"{BASE_URL}/chat/completions").mock(
            side_effect=[
                httpx.ConnectError("conn refused"),
                httpx.Response(200, json=_ok_response("recovered")),
            ]
        )
        result = client.chat([{"role": "user", "content": "hi"}], max_tokens=8)
        assert result["choices"][0]["message"]["content"] == "recovered"
        assert route.call_count == 2

    @respx.mock
    def test_does_not_retry_400(self, client: NIMClient) -> None:
        route = respx.post(f"{BASE_URL}/chat/completions").mock(
            return_value=httpx.Response(400, text="bad request")
        )
        with pytest.raises(NIMHTTPError) as exc:
            client.chat([{"role": "user", "content": "hi"}], max_tokens=8)
        assert exc.value.status_code == 400
        assert route.call_count == 1  # exactly one — no retry on 400

    @respx.mock
    def test_exhausts_retries_then_raises_timeout(self, client: NIMClient) -> None:
        route = respx.post(f"{BASE_URL}/chat/completions").mock(
            return_value=httpx.Response(503, text="still warming")
        )
        with pytest.raises(NIMTimeoutError):
            client.chat([{"role": "user", "content": "hi"}], max_tokens=8)
        # max_retries=2 means 3 attempts total (initial + 2 retries).
        assert route.call_count == 3


# --- health() + wait_for_warm() ------------------------------------------


class TestHealth:
    @respx.mock
    def test_health_returns_true_on_200(self, client: NIMClient) -> None:
        respx.get(f"{BASE_URL}/models").mock(return_value=httpx.Response(200, json={}))
        assert client.health() is True

    @respx.mock
    def test_health_returns_false_on_503(self, client: NIMClient) -> None:
        respx.get(f"{BASE_URL}/models").mock(return_value=httpx.Response(503))
        assert client.health() is False

    @respx.mock
    def test_health_returns_false_on_connect_error(self, client: NIMClient) -> None:
        respx.get(f"{BASE_URL}/models").mock(side_effect=httpx.ConnectError("nope"))
        assert client.health() is False


class TestWaitForWarm:
    @respx.mock
    def test_returns_true_when_ready_immediately(self) -> None:
        respx.get(f"{BASE_URL}/models").mock(return_value=httpx.Response(200, json={}))
        assert wait_for_warm(BASE_URL, timeout=1.0, poll_interval=0.05) is True

    @respx.mock
    def test_returns_false_on_timeout(self) -> None:
        respx.get(f"{BASE_URL}/models").mock(return_value=httpx.Response(503))
        assert wait_for_warm(BASE_URL, timeout=0.2, poll_interval=0.05) is False

    @respx.mock
    def test_returns_true_after_initial_503(self) -> None:
        respx.get(f"{BASE_URL}/models").mock(
            side_effect=[
                httpx.Response(503),
                httpx.Response(503),
                httpx.Response(200, json={}),
            ]
        )
        assert wait_for_warm(BASE_URL, timeout=2.0, poll_interval=0.05) is True
