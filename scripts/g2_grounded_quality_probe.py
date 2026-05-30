#!/usr/bin/env python3
"""G2-extra — Probe whether RAG-grounding recovers teacher quality on patent law.

Tests one A2-family prompt against the served vLLM model, with top-3 MPEP
retrieved chunks as context. R1-distilled models emit `<think>` natively;
Nemotron models need a "detailed thinking on" toggle in the system prompt.

Usage:
    python3 g2_grounded_quality_probe.py --model r1-qwen3-8b
    python3 g2_grounded_quality_probe.py --model nvidia/Llama-3.1-Nemotron-Nano-8B-v1 --nemotron-toggle
"""
import argparse
import json
import os

import faiss
import httpx
import pandas as pd

os.environ.setdefault("HF_HOME", "/home/nvidia/data/.hf-cache")
os.environ.setdefault("HF_HUB_CACHE", "/home/nvidia/data/.hf-cache/hub")

from sentence_transformers import SentenceTransformer


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--model", required=True)
    p.add_argument("--nemotron-toggle", action="store_true",
                   help="Prepend 'detailed thinking on' (Nemotron-style reasoning trigger)")
    p.add_argument("--server", default="http://127.0.0.1:8000/v1")
    p.add_argument("--max-tokens", type=int, default=4000)
    p.add_argument("--temperature", type=float, default=0.6)
    args = p.parse_args()

    idx = faiss.read_index("/home/nvidia/data/aifn-retrieval-index/mpep-bge-base/index.faiss")
    chunks = pd.read_parquet("/home/nvidia/data/aifn-retrieval-index/mpep-bge-base/chunks.parquet")
    embed = SentenceTransformer("BAAI/bge-base-en-v1.5", device="cpu")

    USR = (
        'Identify any 35 USC §112(b) indefiniteness risks in this claim: '
        '"A system for handling user requests, wherein the system is essentially '
        'user-friendly and operates in real-time or near real-time." Flag the '
        "specific phrases and cite the controlling MPEP sections."
    )

    q = embed.encode([USR], normalize_embeddings=True, convert_to_numpy=True)
    _, ids = idx.search(q, 3)
    mpep_ctx = []
    for cid in ids[0].tolist():
        row = chunks.iloc[cid]
        meta = json.loads(row["metadata_json"])
        mpep_ctx.append(f"### MPEP {meta.get('title','?').strip()}\n{row['text'][:1200]}")

    context = "\n\n".join(mpep_ctx)
    print("=== RETRIEVED MPEP TITLES ===")
    for c in mpep_ctx:
        print(c.split("\n")[0])
    print()

    base_sys = (
        "You are a senior US patent practitioner with 15 years of prosecution experience. "
        "Use the MPEP excerpts provided as your sole source of MPEP authority — do not cite "
        "any MPEP section that does not appear in the excerpts. Reason step-by-step inside "
        "<think>…</think> tags, then provide a concise practitioner answer. "
        "Cite MPEP sections by their exact titles as shown in the excerpts. "
        "No producer-meta-commentary, no row-index references."
    )
    sys_prompt = ("detailed thinking on\n\n" + base_sys) if args.nemotron_toggle else base_sys

    user_grounded = f"""## MPEP EXCERPTS (top-3 retrieved)
{context}

## TASK
{USR}
"""

    r = httpx.post(
        f"{args.server}/chat/completions",
        json={
            "model": args.model,
            "messages": [
                {"role": "system", "content": sys_prompt},
                {"role": "user", "content": user_grounded},
            ],
            "max_tokens": args.max_tokens,
            "temperature": args.temperature,
            "top_p": 0.95,
        },
        timeout=900.0,
    ).json()
    content = r["choices"][0]["message"]["content"]
    print("=== GROUNDED RESPONSE (full) ===")
    print(content)
    print(f"\n=== USAGE ===\n{r.get('usage')}")
    print(f"\n=== think-block stats ===")
    has_open = "<think>" in content
    has_close = "</think>" in content
    print(f"opens with <think>: {content.lstrip().startswith('<think>')}")
    print(f"has <think>: {has_open}")
    print(f"has </think>: {has_close}")
    if has_open and has_close:
        think_block = content.split("<think>", 1)[1].split("</think>", 1)[0]
        print(f"think length (chars): {len(think_block.strip())}")


if __name__ == "__main__":
    main()
