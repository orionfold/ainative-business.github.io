#!/usr/bin/env python3
# Copyright 2026 Manav Sehgal
# SPDX-License-Identifier: Apache-2.0
"""Reproduce the kv-cache-arithmetic-at-inference table via fieldkit.capabilities.

Walks the same KV-cache and weight equations the article walks, but using the
package's typed API instead of paste-and-edit math. Output should match the
article's table at https://ainative.business/field-notes/articles/kv-cache-arithmetic-at-inference/.

Run:
    python samples/feasibility-math.py
"""

from __future__ import annotations

from fieldkit.capabilities import (
    Capabilities,
    kv_cache_bytes,
    practical_inference_envelope,
    weight_bytes,
)

GB = 10**9

# Llama 3.1 70B architecture (GQA): 8 KV heads × 128 head_dim, 80 layers.
LLAMA_70B = {"hidden": 8 * 128, "n_layers": 80}


def gb(b: int) -> str:
    return f"{b / GB:>7.1f} GB" if b < 1_000 * GB else f"{b / (1000 * GB):>5.2f} TB"


def main() -> None:
    caps = Capabilities.load()
    print(f"Capabilities map: {caps.schema} v{caps.version}")
    print(f"Hardware:         {caps.hardware.name} — {caps.hardware.unified_memory_gb} GB unified")
    print()

    print("Llama 3.1 70B serving — KV cache by concurrency × context × precision")
    print(
        f"  {'concurrency':>11}  {'avg ctx':>8}  {'KV (FP16)':>11}  {'KV (FP8)':>10}"
    )
    cells = [
        (1, 4096),
        (32, 4096),
        (32, 16384),
        (128, 8192),
        (32, 131072),
    ]
    for batch, ctx in cells:
        fp16 = kv_cache_bytes(**LLAMA_70B, ctx=ctx, batch=batch, dtype="fp16")
        fp8 = kv_cache_bytes(**LLAMA_70B, ctx=ctx, batch=batch, dtype="fp8")
        print(
            f"  {batch:>9} u  {ctx:>5}t  {gb(fp16):>11}  {gb(fp8):>10}"
        )

    print()
    print("Weight memory for the 100B Nemotron from gpu-sizing-math-for-fine-tuning")
    for dtype in ("bf16", "fp8", "nf4"):
        b = weight_bytes(params_b=100, dtype=dtype)
        print(f"  100B params @ {dtype:>4}: {gb(b)}")

    print()
    print("Practical inference envelope (rules-of-thumb table)")
    table = caps.memory_budget_rules_of_thumb.practical_inference_envelope
    for key in table:
        print(f"  {key:<22} → {practical_inference_envelope(key)}")


if __name__ == "__main__":
    main()
