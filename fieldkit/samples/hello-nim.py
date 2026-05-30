#!/usr/bin/env python3
# Copyright 2026 Manav Sehgal
# SPDX-License-Identifier: Apache-2.0
"""Minimal NIM call — the Python equivalent of the curl one-liner from
`nim-first-inference-dgx-spark`.

Walks through:
  1. wait_for_warm — block until /v1/models responds (NIM cold start ≈ 90s)
  2. NIMClient(...) — open a session
  3. client.health() — sanity check
  4. client.chat([...]) — one short generation, retry-aware

Run on the Spark with NIM 8B at localhost:8000:
    docker start nim-llama31-8b
    python samples/hello-nim.py

Override host / model / prompt via env vars:
    NIM_BASE_URL=http://10.0.0.209:8000/v1 NIM_MODEL=meta/llama-3.1-8b-instruct \\
    NIM_PROMPT="What is 2+2?" python samples/hello-nim.py
"""

from __future__ import annotations

import os
import sys
import time

from fieldkit.nim import NIMClient, wait_for_warm

NIM_BASE_URL = os.environ.get("NIM_BASE_URL", "http://localhost:8000/v1")
NIM_MODEL = os.environ.get("NIM_MODEL", "meta/llama-3.1-8b-instruct")
NIM_PROMPT = os.environ.get("NIM_PROMPT", "Say hi from the DGX Spark in one short sentence.")


def main() -> int:
    print(f"Waiting for NIM at {NIM_BASE_URL} (timeout 120s)…")
    if not wait_for_warm(NIM_BASE_URL, timeout=120.0, poll_interval=2.0):
        print(f"  NIM did not become ready within 120s. Is the container running?", file=sys.stderr)
        print(f"  Try:  docker start nim-llama31-8b", file=sys.stderr)
        return 1
    print("  ready.")

    with NIMClient(base_url=NIM_BASE_URL, model=NIM_MODEL, timeout=30.0) as client:
        if not client.health():
            print("  health check failed", file=sys.stderr)
            return 1
        print(f"\nPrompt: {NIM_PROMPT}\n")
        t0 = time.perf_counter()
        result = client.chat(
            [
                {"role": "system", "content": "You are a concise NVIDIA DGX Spark assistant."},
                {"role": "user", "content": NIM_PROMPT},
            ],
            max_tokens=128,
            temperature=0.0,
        )
        elapsed_ms = (time.perf_counter() - t0) * 1000

    msg = result["choices"][0]["message"]["content"].strip()
    usage = result.get("usage", {})
    print(f"Response ({elapsed_ms:.0f} ms, {usage.get('completion_tokens', '?')} tokens):")
    print(msg)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
