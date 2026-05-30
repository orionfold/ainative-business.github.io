#!/usr/bin/env python3
"""G1.5 — Smoke-test retrieval against MPEP + PatentMatch indices.

Pulls 5 hand-crafted queries (one per A1/A2/A4/E1/E2 family) + 5 random rows
from `/tmp/aifn-corpus-synth/queue.jsonl` and prints top-3 hits from each
index to confirm topical relevance before sinking time into the dry-run.
"""
from __future__ import annotations

import json
import os
import random
from pathlib import Path

import faiss
import pandas as pd
from sentence_transformers import SentenceTransformer

os.environ.setdefault("HF_HOME", "/home/nvidia/data/.hf-cache")
os.environ.setdefault("HF_HUB_CACHE", "/home/nvidia/data/.hf-cache/hub")

INDEX_ROOT = Path("/home/nvidia/data/aifn-retrieval-index")
QUEUE = Path("/home/nvidia/data/aifn-corpus-v2/queue.jsonl")
MODEL_NAME = "BAAI/bge-base-en-v1.5"
TOP_K = 3

# Hand-crafted queries — one per family, written to surface MPEP rules / prior-art
# pairs we'd expect a competent practitioner to reach for first.
HAND = [
    ("A1", "What does MPEP say about drafting independent claims with the transition word 'comprising' and avoiding means-plus-function interpretation under 35 USC 112(f)?"),
    ("A2", "MPEP guidance on definiteness rejection under 35 USC 112(b) and how to amend claims with relative terms like 'substantially' or 'about'."),
    ("A4", "How does the MPEP instruct an applicant to respond to an obviousness rejection under 35 USC 103, particularly Graham factors and secondary considerations?"),
    ("E1", "Explain the difference between novelty under 35 USC 102 and non-obviousness under 35 USC 103 in plain language for a non-attorney inventor."),
    ("E2", "What is the inherency doctrine under 35 USC 102 and when does an unstated property of a prior-art reference count as anticipating a claim?"),
]


def load_index(name: str):
    d = INDEX_ROOT / name
    idx = faiss.read_index(str(d / "index.faiss"))
    chunks = pd.read_parquet(d / "chunks.parquet")
    print(f"[load] {name}: {idx.ntotal:,} vectors, dim={idx.d}")
    return idx, chunks


def show_hits(label: str, hits, chunks: pd.DataFrame):
    print(f"\n--- {label} ---")
    for rank, (score, cid) in enumerate(hits, 1):
        row = chunks.iloc[cid]
        meta = json.loads(row["metadata_json"]) if row["metadata_json"] else {}
        title = meta.get("title") or meta.get("claim_id") or row.get("doc_id", "?")
        snippet = (row["text"] or "")[:220].replace("\n", " ")
        print(f"  {rank}. [{score:.3f}] {title}")
        print(f"     {snippet}…")


def retrieve(model, idx, chunks: pd.DataFrame, query: str, k: int = TOP_K):
    q = model.encode([query], normalize_embeddings=True, convert_to_numpy=True)
    scores, ids = idx.search(q, k)
    return list(zip(scores[0].tolist(), ids[0].tolist()))


def main():
    print(f"Loading {MODEL_NAME} on cuda …")
    model = SentenceTransformer(MODEL_NAME, device="cuda")

    mpep_idx, mpep_chunks = load_index("mpep-bge-base")
    pm_idx, pm_chunks = load_index("patentmatch-bge-base")

    random.seed(42)
    with QUEUE.open() as f:
        all_rows = [json.loads(line) for line in f]
    random_rows = random.sample(all_rows, 5)

    print("\n" + "=" * 70)
    print("HAND-CRAFTED QUERIES (one per family)")
    print("=" * 70)
    for fam, query in HAND:
        print(f"\n### {fam}: {query}")
        show_hits(f"MPEP top-{TOP_K}", retrieve(model, mpep_idx, mpep_chunks, query), mpep_chunks)
        show_hits(f"PatentMatch top-{TOP_K}", retrieve(model, pm_idx, pm_chunks, query), pm_chunks)

    print("\n" + "=" * 70)
    print(f"5 RANDOM QUEUE ROWS (seed=42)")
    print("=" * 70)
    for r in random_rows:
        q = r["prompt"]
        print(f"\n### row_idx={r['row_idx']} family={r['family']}")
        print(f"    PROMPT: {q[:240]}{'…' if len(q) > 240 else ''}")
        show_hits(f"MPEP top-{TOP_K}", retrieve(model, mpep_idx, mpep_chunks, q), mpep_chunks)
        show_hits(f"PatentMatch top-{TOP_K}", retrieve(model, pm_idx, pm_chunks, q), pm_chunks)


if __name__ == "__main__":
    main()
