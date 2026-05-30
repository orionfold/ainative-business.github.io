# Copyright 2026 Manav Sehgal
# SPDX-License-Identifier: Apache-2.0
"""Spark-live integration tests for fieldkit.nim.

Skipped unless `pytest --spark` is passed AND a NIM endpoint is reachable.
Default endpoint is the Spark's local 8B NIM at http://localhost:8000/v1;
override with NIM_BASE_URL / NIM_MODEL env vars.
"""

from __future__ import annotations

import os

import pytest

from fieldkit.nim import NIMClient, wait_for_warm

NIM_BASE_URL = os.environ.get("NIM_BASE_URL", "http://localhost:8000/v1")
NIM_MODEL = os.environ.get("NIM_MODEL", "meta/llama-3.1-8b-instruct")


@pytest.mark.spark
def test_nim_8b_round_trip() -> None:
    """Wait for warm, send one short chat, get a non-empty assistant message.

    Cold-start budget is 120 s — generous because NIM pulls weights on first
    boot. Subsequent runs are sub-second.
    """
    if not wait_for_warm(NIM_BASE_URL, timeout=120.0, poll_interval=2.0):
        pytest.skip(f"NIM at {NIM_BASE_URL} did not warm within 120s")

    with NIMClient(base_url=NIM_BASE_URL, model=NIM_MODEL, timeout=30.0) as client:
        assert client.health() is True
        result = client.chat(
            [
                {"role": "system", "content": "Reply with exactly the word READY."},
                {"role": "user", "content": "Acknowledge."},
            ],
            max_tokens=8,
            temperature=0.0,
        )
    content = result["choices"][0]["message"]["content"].strip()
    assert content, "expected a non-empty completion from NIM"
