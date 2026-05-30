#!/usr/bin/env python3
"""G2 — Measure vLLM teacher throughput on Spark for the patent corpus.

Sends 10 prompts (one per family A1/A2/A4/E1/E2 + 5 random) to the local
vLLM OpenAI-API server and reports:

  - single-stream tok/sec (sequential calls)
  - concurrent_requests=4 aggregate tok/sec (parallel calls)
  - per-row wall + tokens generated

Output written to `ideas/g2-teacher-throughput-2026-05-19.md` so it survives
the session.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import random
import time
from pathlib import Path

import httpx

QUEUE = Path("/home/nvidia/data/aifn-corpus-v2/queue.jsonl")
SERVER = "http://127.0.0.1:8000/v1"
MODEL = "nvidia/Llama-3.1-Nemotron-Nano-8B-v1"
MAX_TOKENS = 1500  # reasoning models need ≥1024 per memory; corpus rows ~600-1200 tokens

SYSTEM_PROMPT = (
    "You are a senior US patent practitioner with 15 years of prosecution experience. "
    "When given a patent-strategy task, first reason step-by-step inside <think>…</think> tags "
    "(citing specific MPEP sections, 35 USC provisions, and Federal Circuit case law where relevant), "
    "then provide a concise practitioner-grade answer. Keep `<think>` blocks substantive but focused — "
    "no producer-meta-commentary, no row-index references, no diversification reasoning."
)


def pick_10_prompts(seed: int = 7) -> list[dict]:
    """One per family + 5 random; 10 total."""
    with QUEUE.open() as f:
        rows = [json.loads(line) for line in f]
    by_family: dict[str, list[dict]] = {}
    for r in rows:
        by_family.setdefault(r["family"], []).append(r)

    random.seed(seed)
    selected: list[dict] = []
    for fam in ["A1", "A2", "A4", "E1", "E2"]:
        if fam in by_family:
            selected.append(random.choice(by_family[fam]))
    pool = [r for r in rows if r not in selected]
    selected.extend(random.sample(pool, 5))
    return selected


def render_messages(prompt: str) -> list[dict]:
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": prompt},
    ]


async def one_call(client: httpx.AsyncClient, prompt: str) -> dict:
    t0 = time.time()
    resp = await client.post(
        f"{SERVER}/chat/completions",
        json={
            "model": MODEL,
            "messages": render_messages(prompt),
            "max_tokens": MAX_TOKENS,
            "temperature": 0.7,
        },
        timeout=600.0,
    )
    elapsed = time.time() - t0
    resp.raise_for_status()
    data = resp.json()
    usage = data.get("usage", {})
    content = data["choices"][0]["message"]["content"]
    return {
        "elapsed_s": elapsed,
        "prompt_tokens": usage.get("prompt_tokens", 0),
        "completion_tokens": usage.get("completion_tokens", 0),
        "tok_per_sec": usage.get("completion_tokens", 0) / max(elapsed, 1e-6),
        "first_200_chars": content[:200],
    }


async def run_serial(rows: list[dict]) -> list[dict]:
    out = []
    async with httpx.AsyncClient() as client:
        for i, row in enumerate(rows):
            r = await one_call(client, row["prompt"])
            r.update({"row_idx": row["row_idx"], "family": row["family"]})
            print(
                f"  [serial {i+1}/{len(rows)}] fam={row['family']} "
                f"row={row['row_idx']:>4} → {r['completion_tokens']} tok "
                f"in {r['elapsed_s']:.1f}s = {r['tok_per_sec']:.1f} tok/s"
            )
            out.append(r)
    return out


async def run_concurrent(rows: list[dict], concurrency: int = 4) -> list[dict]:
    sem = asyncio.Semaphore(concurrency)
    results: list[dict] = []

    async def _wrapped(row, client):
        async with sem:
            r = await one_call(client, row["prompt"])
            r.update({"row_idx": row["row_idx"], "family": row["family"]})
            return r

    async with httpx.AsyncClient() as client:
        tasks = [_wrapped(row, client) for row in rows]
        t0 = time.time()
        results = await asyncio.gather(*tasks)
        wall = time.time() - t0
    print(
        f"  [concurrent={concurrency}] {len(rows)} prompts in {wall:.1f}s wall · "
        f"total {sum(r['completion_tokens'] for r in results)} tok = "
        f"{sum(r['completion_tokens'] for r in results)/wall:.1f} aggregate tok/s"
    )
    for r in results:
        r["_aggregate_wall_s"] = wall
    return results


def summarize(serial: list[dict], parallel: list[dict], parallel_wall: float) -> dict:
    total_tok_serial = sum(r["completion_tokens"] for r in serial)
    total_s_serial = sum(r["elapsed_s"] for r in serial)
    total_tok_parallel = sum(r["completion_tokens"] for r in parallel)
    return {
        "serial": {
            "n": len(serial),
            "total_completion_tokens": total_tok_serial,
            "total_wall_s": total_s_serial,
            "avg_tok_per_sec": total_tok_serial / max(total_s_serial, 1e-6),
            "median_tok_per_sec": sorted(r["tok_per_sec"] for r in serial)[len(serial) // 2],
        },
        "concurrent_4": {
            "n": len(parallel),
            "wall_s": parallel_wall,
            "total_completion_tokens": total_tok_parallel,
            "aggregate_tok_per_sec": total_tok_parallel / max(parallel_wall, 1e-6),
        },
    }


def project_5000(summary: dict) -> dict:
    """Project full-corpus wall-time at both regimes assuming ~800 completion tokens/row."""
    serial_rate = summary["serial"]["avg_tok_per_sec"]
    parallel_rate = summary["concurrent_4"]["aggregate_tok_per_sec"]
    target_tok = 5000 * 800
    return {
        "assumed_completion_tokens_per_row": 800,
        "target_total_tokens": target_tok,
        "serial_hr": (target_tok / serial_rate) / 3600 if serial_rate else None,
        "concurrent_4_hr": (target_tok / parallel_rate) / 3600 if parallel_rate else None,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--out",
        default="/home/nvidia/ainative-business.github.io/ideas/g2-teacher-throughput-2026-05-19.md",
    )
    args = parser.parse_args()

    rows = pick_10_prompts()
    print(f"Selected {len(rows)} prompts:")
    for r in rows:
        print(f"  row_idx={r['row_idx']:>4} family={r['family']}")

    print("\n=== SERIAL (single-stream) ===")
    serial = asyncio.run(run_serial(rows))

    print("\n=== CONCURRENT (4 in flight) ===")
    parallel = asyncio.run(run_concurrent(rows, concurrency=4))

    parallel_wall = parallel[0]["_aggregate_wall_s"] if parallel else 0.0
    summary = summarize(serial, parallel, parallel_wall)
    projection = project_5000(summary)

    lines = [
        "# G2 — vLLM teacher throughput on Spark (2026-05-19)",
        "",
        f"**Teacher:** `{MODEL}`",
        f"**Server:** `{SERVER}` (vLLM 0.21.0, BF16, max_model_len=8192, prefix-caching=ON)",
        f"**Prompts:** 10 (one per family A1/A2/A4/E1/E2 + 5 random from queue.jsonl, seed=7)",
        f"**System prompt:** patent-practitioner persona, `<think>…</think>` reasoning shape",
        f"**Sampling:** temp=0.7, max_tokens={MAX_TOKENS}",
        "",
        "## Per-row results (serial)",
        "",
        "| # | family | row_idx | prompt_tok | gen_tok | wall_s | tok/s |",
        "|---|---|---|---|---|---|---|",
    ]
    for i, r in enumerate(serial, 1):
        lines.append(
            f"| {i} | {r['family']} | {r['row_idx']} | {r['prompt_tokens']} | "
            f"{r['completion_tokens']} | {r['elapsed_s']:.1f} | {r['tok_per_sec']:.1f} |"
        )

    lines += [
        "",
        "## Summary",
        "",
        "```json",
        json.dumps(summary, indent=2),
        "```",
        "",
        "## Projection to 5000-row corpus",
        "",
        "```json",
        json.dumps(projection, indent=2),
        "```",
        "",
        "## Gate decision",
        "",
    ]
    gate_threshold_hr = 2.0
    gate_escalation_hr = 6.0
    serial_hr = projection["serial_hr"]
    concurrent_hr = projection["concurrent_4_hr"]
    decision = ""
    if concurrent_hr is not None and concurrent_hr < gate_threshold_hr:
        decision = (
            f"**PROCEED with Nano-8B as teacher** — concurrent-4 projects to "
            f"{concurrent_hr:.2f} hr for 5000 rows × 800 tok, well under the 2-hr gate."
        )
    elif concurrent_hr is not None and concurrent_hr < gate_escalation_hr:
        decision = (
            f"**PROCEED with Nano-8B (slower run)** — concurrent-4 projects to "
            f"{concurrent_hr:.2f} hr; between 2-hr fast-gate and 6-hr escalation gate. "
            f"Accept the longer wall-time."
        )
    elif concurrent_hr is not None:
        decision = (
            f"**ESCALATE to Super-49B-FP8** — concurrent-4 projects to "
            f"{concurrent_hr:.2f} hr, over the 6-hr escalation gate."
        )
    else:
        decision = "**INDETERMINATE** — throughput numbers missing."
    lines.append(decision)
    lines.append("")

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines))
    print(f"\nWrote {out}")
    print(f"\nGate decision: {decision}")


if __name__ == "__main__":
    main()
