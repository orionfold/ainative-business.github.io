#!/usr/bin/env python3
"""G2 — NIM Nemotron-Nano-9B-v2 quality (4 prompts × 4 families) + throughput.

Quality probe: one grounded prompt per family A1/A2/A4/E1 + 1 random.
Throughput probe: concurrent=8 over 16 prompts (mix of families).

Notes:
  - NIM endpoint is on the HOST network (port 8000). From inside ps-train,
    reach via host docker-bridge IP `172.17.0.1`.
  - NIM prepends `<think>` to the assistant prompt prefix; response content
    starts with reasoning text and the model later emits `</think>` before the
    final answer. Post-process by prepending `<think>` client-side and treating
    everything before first `</think>` as chain, rest as answer.
"""
import asyncio
import json
import os
import random
import re
import time
from pathlib import Path

import faiss
import httpx
import pandas as pd

os.environ.setdefault("HF_HOME", "/home/nvidia/data/.hf-cache")
os.environ.setdefault("HF_HUB_CACHE", "/home/nvidia/data/.hf-cache/hub")

from sentence_transformers import SentenceTransformer


SERVER = "http://172.17.0.1:8000/v1"
MODEL = "nvidia/nemotron-nano-9b-v2"
QUEUE = Path("/home/nvidia/data/aifn-corpus-v2/queue.jsonl")
INDEX_DIR = Path("/home/nvidia/data/aifn-retrieval-index/mpep-bge-base")

SYS = (
    "You are a senior US patent practitioner with 15 years of prosecution experience. "
    "Use the MPEP excerpts provided as your sole source of MPEP authority — do not cite "
    "any MPEP section that does not appear in the excerpts. Reason step-by-step inside "
    "<think>…</think> tags, then provide a concise practitioner answer. "
    "Cite MPEP sections by their exact titles as shown in the excerpts. "
    "No producer-meta-commentary, no row-index references."
)


def split_think(raw: str) -> tuple[str, str]:
    """Apply the 'NIM prepends <think>' convention. Return (chain, answer)."""
    decorated = "<think>\n" + raw
    if "</think>" in decorated:
        chain, rest = decorated.split("</think>", 1)
        chain = chain.removeprefix("<think>\n")
        # Strip a stray second `<think>` block the model sometimes emits after </think>
        rest = re.sub(r"<think>.*?</think>", "", rest, flags=re.DOTALL).strip()
        return chain.strip(), rest.strip()
    return "", decorated.strip()


def load_retriever():
    idx = faiss.read_index(str(INDEX_DIR / "index.faiss"))
    chunks = pd.read_parquet(INDEX_DIR / "chunks.parquet")
    embed = SentenceTransformer("BAAI/bge-base-en-v1.5", device="cpu")
    return idx, chunks, embed


def retrieve(idx, chunks, embed, query: str, k: int = 3) -> str:
    q = embed.encode([query], normalize_embeddings=True, convert_to_numpy=True)
    _, ids = idx.search(q, k)
    out = []
    for cid in ids[0].tolist():
        row = chunks.iloc[cid]
        meta = json.loads(row["metadata_json"])
        out.append(f"### MPEP {meta.get('title', '?').strip()}\n{row['text'][:1200]}")
    return "\n\n".join(out)


def build_user(prompt: str, context: str) -> str:
    return f"## MPEP EXCERPTS (top-3 retrieved)\n{context}\n\n## TASK\n{prompt}\n"


async def call_one(client, prompt: str, context: str) -> dict:
    t0 = time.time()
    resp = await client.post(
        f"{SERVER}/chat/completions",
        json={
            "model": MODEL,
            "messages": [
                {"role": "system", "content": SYS},
                {"role": "user", "content": build_user(prompt, context)},
            ],
            "max_tokens": 2500,
            "temperature": 0.6,
            "top_p": 0.95,
        },
        timeout=600.0,
    )
    elapsed = time.time() - t0
    data = resp.json()
    msg = data["choices"][0]["message"]["content"]
    chain, answer = split_think(msg)
    return {
        "elapsed_s": elapsed,
        "prompt_tokens": data["usage"]["prompt_tokens"],
        "completion_tokens": data["usage"]["completion_tokens"],
        "chain": chain,
        "answer": answer,
        "raw": msg,
    }


def pick_quality_prompts() -> list[dict]:
    """One per family A1/A2/A4/E1/E2, deterministic via seed."""
    with QUEUE.open() as f:
        rows = [json.loads(line) for line in f]
    by_fam: dict[str, list[dict]] = {}
    for r in rows:
        by_fam.setdefault(r["family"], []).append(r)
    random.seed(11)
    return [random.choice(by_fam[fam]) for fam in ["A1", "A2", "A4", "E1", "E2"]]


def pick_throughput_prompts(n: int = 16) -> list[dict]:
    with QUEUE.open() as f:
        rows = [json.loads(line) for line in f]
    random.seed(17)
    return random.sample(rows, n)


async def quality_pass(rows, idx, chunks, embed) -> list[dict]:
    print("\n=== QUALITY PASS (5 prompts, one per family) ===")
    async with httpx.AsyncClient() as client:
        results = []
        for r in rows:
            ctx = retrieve(idx, chunks, embed, r["prompt"])
            res = await call_one(client, r["prompt"], ctx)
            res.update({"row_idx": r["row_idx"], "family": r["family"], "prompt": r["prompt"]})
            results.append(res)
            print(
                f"\n--- family={r['family']} row_idx={r['row_idx']} "
                f"| gen_tok={res['completion_tokens']} wall={res['elapsed_s']:.1f}s ---"
            )
            print(f"  PROMPT: {r['prompt'][:160]}…")
            print(f"  CHAIN (first 350): {res['chain'][:350].replace(chr(10),' / ')}")
            print(f"  ANSWER (first 350): {res['answer'][:350].replace(chr(10),' / ')}")
        return results


async def throughput_pass(rows, idx, chunks, embed, concurrency: int = 8) -> dict:
    print(f"\n=== THROUGHPUT PASS (n={len(rows)}, concurrent={concurrency}) ===")
    contexts = [retrieve(idx, chunks, embed, r["prompt"]) for r in rows]
    sem = asyncio.Semaphore(concurrency)

    async def _wrapped(client, row, ctx):
        async with sem:
            return await call_one(client, row["prompt"], ctx)

    async with httpx.AsyncClient() as client:
        t0 = time.time()
        results = await asyncio.gather(
            *[_wrapped(client, row, ctx) for row, ctx in zip(rows, contexts)]
        )
        wall = time.time() - t0
    total_tok = sum(r["completion_tokens"] for r in results)
    return {
        "n": len(rows),
        "concurrency": concurrency,
        "wall_s": wall,
        "total_gen_tok": total_tok,
        "aggregate_tok_per_sec": total_tok / wall,
        "tok_per_row_mean": total_tok / len(rows),
        "projected_hr_5000_600": (5000 * 600 / (total_tok / wall)) / 3600,
        "projected_hr_5000_800": (5000 * 800 / (total_tok / wall)) / 3600,
    }


async def main():
    idx, chunks, embed = load_retriever()
    qrows = pick_quality_prompts()
    qresults = await quality_pass(qrows, idx, chunks, embed)

    trows = pick_throughput_prompts()
    tres = await throughput_pass(trows, idx, chunks, embed, concurrency=8)
    print(f"\n=== THROUGHPUT SUMMARY ===\n{json.dumps(tres, indent=2)}")

    out_md = Path("/home/nvidia/ainative-business.github.io/ideas/g2-nim-nano9b-2026-05-19.md")
    lines = [
        "# G2 — NIM Nemotron-Nano-9B-v2 quality + throughput (2026-05-19)",
        "",
        f"**Endpoint:** `{SERVER}` (NIM container `nvcr.io/nim/nvidia/nvidia-nemotron-nano-9b-v2-dgx-spark:latest`)",
        f"**Model:** `{MODEL}` (NVFP4 profile, max_model_len=131072)",
        f"**Backend:** TRT-LLM under NIM (correct tokenizer + chat template, no detok bugs)",
        "",
        "## Quality results (one prompt per family, RAG-grounded)",
        "",
        "| family | row_idx | gen_tok | wall_s | chain_chars | answer_chars |",
        "|---|---|---|---|---|---|",
    ]
    for r in qresults:
        lines.append(
            f"| {r['family']} | {r['row_idx']} | {r['completion_tokens']} | "
            f"{r['elapsed_s']:.1f} | {len(r['chain'])} | {len(r['answer'])} |"
        )
    lines += ["", "## Throughput", "", "```json", json.dumps(tres, indent=2), "```", ""]
    lines += ["## Sample answers (eyeball)", ""]
    for r in qresults:
        lines += [
            f"### {r['family']} — row_idx={r['row_idx']}",
            "",
            f"**Prompt:** {r['prompt']}",
            "",
            "**Chain (truncated):**",
            "",
            "```",
            r["chain"][:1200] + ("…" if len(r["chain"]) > 1200 else ""),
            "```",
            "",
            "**Answer:**",
            "",
            "```",
            r["answer"][:1500] + ("…" if len(r["answer"]) > 1500 else ""),
            "```",
            "",
        ]
    out_md.write_text("\n".join(lines))
    print(f"\nWrote {out_md}")


if __name__ == "__main__":
    asyncio.run(main())
