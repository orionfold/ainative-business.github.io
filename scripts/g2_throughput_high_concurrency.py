#!/usr/bin/env python3
"""G2.x — Retest throughput at higher concurrencies (8/16/32) on the same teacher.

Concurrent=4 measured at 40 tok/s aggregate, projecting 27 hr for 5000 rows ×
800 tok. vLLM's continuous batching scales sublinearly but should give a much
higher ceiling. Test 8/16/32 with 32-row workloads to find the knee.
"""
from __future__ import annotations

import asyncio
import json
import random
import time
from pathlib import Path

import httpx

QUEUE = Path("/home/nvidia/data/aifn-corpus-v2/queue.jsonl")
SERVER = "http://127.0.0.1:8000/v1"
MODEL = "nvidia/Llama-3.1-Nemotron-Nano-8B-v1"
MAX_TOKENS = 1500

SYSTEM_PROMPT = (
    "You are a senior US patent practitioner with 15 years of prosecution experience. "
    "When given a patent-strategy task, first reason step-by-step inside <think>…</think> tags "
    "(citing specific MPEP sections, 35 USC provisions, and Federal Circuit case law where relevant), "
    "then provide a concise practitioner-grade answer. Keep `<think>` blocks substantive but focused — "
    "no producer-meta-commentary, no row-index references, no diversification reasoning."
)


def pick_n_prompts(n: int = 32, seed: int = 13) -> list[dict]:
    with QUEUE.open() as f:
        rows = [json.loads(line) for line in f]
    random.seed(seed)
    return random.sample(rows, n)


async def one_call(client, prompt):
    t0 = time.time()
    resp = await client.post(
        f"{SERVER}/chat/completions",
        json={
            "model": MODEL,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            "max_tokens": MAX_TOKENS,
            "temperature": 0.7,
        },
        timeout=600.0,
    )
    elapsed = time.time() - t0
    resp.raise_for_status()
    data = resp.json()
    usage = data.get("usage", {})
    return {"elapsed_s": elapsed, "gen_tok": usage.get("completion_tokens", 0)}


async def measure(rows: list[dict], concurrency: int) -> dict:
    sem = asyncio.Semaphore(concurrency)

    async def _wrapped(client, row):
        async with sem:
            return await one_call(client, row["prompt"])

    async with httpx.AsyncClient() as client:
        t0 = time.time()
        results = await asyncio.gather(*[_wrapped(client, row) for row in rows])
        wall = time.time() - t0
    total_tok = sum(r["gen_tok"] for r in results)
    return {
        "concurrency": concurrency,
        "n_rows": len(rows),
        "wall_s": wall,
        "total_gen_tok": total_tok,
        "aggregate_tok_per_sec": total_tok / wall,
        "tok_per_row_mean": total_tok / len(rows),
    }


async def main():
    rows = pick_n_prompts(32)
    print(f"Selected {len(rows)} prompts (seed=13)")
    summaries = []
    for c in [8, 16, 32]:
        print(f"\n=== concurrency={c} ===")
        s = await measure(rows, c)
        print(f"  wall={s['wall_s']:.1f}s · gen_tok={s['total_gen_tok']} "
              f"· {s['aggregate_tok_per_sec']:.1f} tok/s aggregate "
              f"· avg {s['tok_per_row_mean']:.0f} tok/row")
        summaries.append(s)
    out = Path("/home/nvidia/ainative-business.github.io/ideas/g2-throughput-high-concurrency-2026-05-19.md")
    lines = ["# G2.x — High-concurrency throughput retest (2026-05-19)", "",
             f"**Teacher:** `{MODEL}` · BF16 · max_model_len=8192 · prefix-caching ON",
             f"**Workload:** 32 random prompts (seed=13) from queue.jsonl, max_tokens={MAX_TOKENS}",
             "",
             "| concurrency | wall_s | gen_tok | aggregate tok/s | tok/row mean | proj 5000×600 (hr) | proj 5000×800 (hr) |",
             "|---|---|---|---|---|---|---|"]
    for s in summaries:
        rate = s["aggregate_tok_per_sec"]
        proj_600 = (5000 * 600) / rate / 3600
        proj_800 = (5000 * 800) / rate / 3600
        lines.append(
            f"| {s['concurrency']} | {s['wall_s']:.1f} | {s['total_gen_tok']} | "
            f"{rate:.1f} | {s['tok_per_row_mean']:.0f} | {proj_600:.2f} | {proj_800:.2f} |"
        )
    out.write_text("\n".join(lines) + "\n")
    print(f"\nWrote {out}")


if __name__ == "__main__":
    asyncio.run(main())
