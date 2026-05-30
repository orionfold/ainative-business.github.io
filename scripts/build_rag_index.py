#!/usr/bin/env python3
# Copyright 2026 Manav Sehgal
# SPDX-License-Identifier: Apache-2.0
"""Build the patent-strategist RAG index on disk.

Per `specs/patent-strategist-v1.md` §3.4: embeds the pulled patent corpus at
`/home/nvidia/data/corpus/patent/<source>/*.jsonl` with `BAAI/bge-small-en-v1.5`
and persists a FAISS index + Parquet sidecar at
`/home/nvidia/data/rag/patent-bge-small/`.

Chunking rules (spec §3.4):

    | source       | rule                                            |
    | ------------ | ----------------------------------------------- |
    | bigpatent    | abstract atomic — one chunk per patent          |
    | patentmatch  | atomic — one chunk per instruction row          |
    | mpep         | semantic-section (~800 tokens, overlap 100)     |
    | gpat         | abstract + claim 1 atomic                       |

`mpep` and `gpat` are wired but skipped when their source dirs are empty,
matching the W1-partial corpus state per session 19's HANDOFF.

Index choice — `IndexFlatIP` is used at the v1.0 corpus scale (~10.5k
vectors). Spec §3.4 mentions "flat IVF" which crosses over to true
`IndexIVFFlat` only when the corpus passes ~100k vectors (BigQuery
Google Patents + USPTO OARD). The `--index-type` flag is in place so the
W2 follow-up can flip without script surgery.

Embeddings are L2-normalized (BGE convention) so inner-product on a flat
index equals cosine similarity. The Parquet sidecar carries the chunk
text + metadata so retrieval-time hydration is one join (chunk_id → row).

Outputs:

    /home/nvidia/data/rag/patent-bge-small/
        index.faiss
        chunks.parquet
        meta.json           # model + corpus + index provenance

And an evidence snapshot at:

    evidence/patent-strategist/rag-index-snapshot.json

Usage::

    python scripts/build_rag_index.py                    # build everything found on disk
    python scripts/build_rag_index.py --sources bigpatent
    python scripts/build_rag_index.py --max-rows 1000    # cap per source
    python scripts/build_rag_index.py --batch-size 128 --device cuda
    python scripts/build_rag_index.py --force            # overwrite existing index
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CORPUS = Path("/home/nvidia/data/corpus/patent")
DEFAULT_OUT = Path("/home/nvidia/data/rag/patent-bge-small")
DEFAULT_MODEL = "BAAI/bge-small-en-v1.5"
SNAPSHOT_PATH = REPO_ROOT / "evidence" / "patent-strategist" / "rag-index-snapshot.json"

# Reuse the corpus puller's HF cache redirect — `~/.cache/huggingface/hub/`
# is root-owned on this Spark from an earlier container-pull.
os.environ.setdefault("HF_HOME", "/home/nvidia/data/.hf-cache")
os.environ.setdefault("HF_HUB_CACHE", "/home/nvidia/data/.hf-cache/hub")

ALL_SOURCES = ("bigpatent", "patentmatch", "mpep", "gpat")


@dataclass
class Chunk:
    chunk_id: str
    source: str
    doc_id: str
    text: str
    metadata: dict[str, Any] = field(default_factory=dict)


def _stable_id(source: str, doc_id: str, ordinal: int) -> str:
    raw = f"{source}::{doc_id}::{ordinal}".encode()
    return hashlib.sha1(raw).hexdigest()[:16]


# --- BIGPATENT --------------------------------------------------------------


def chunk_bigpatent(src_dir: Path, max_rows: int | None) -> Iterator[Chunk]:
    """One atomic chunk per patent — abstract only.

    Spec §3.4: "BIGPATENT abstracts as atomic (single chunk per patent)".
    Description is intentionally omitted from the chunk text — RAG hits
    over 8k-char descriptions blow the bge-small 512-token window and
    dilute retrieval signal. The patent_number stays as `doc_id` so the
    description is recoverable from the corpus JSONL at hydration time.
    """
    files = sorted(src_dir.glob("bigpatent-*-train.jsonl"))
    seen = 0
    for path in files:
        with path.open() as f:
            for line in f:
                row = json.loads(line)
                abstract = (row.get("abstract") or "").strip()
                if not abstract:
                    continue
                doc_id = str(row.get("patent_number") or f"{path.stem}#{seen}")
                yield Chunk(
                    chunk_id=_stable_id("bigpatent", doc_id, 0),
                    source="bigpatent",
                    doc_id=doc_id,
                    text=abstract,
                    metadata={"ipc_class": row.get("ipc_class"), "config_file": path.name},
                )
                seen += 1
                if max_rows is not None and seen >= max_rows:
                    return


# --- PatentMatch (canonical HPI-Naumann ultra-balanced) --------------------


def chunk_patentmatch(src_dir: Path, max_rows: int | None) -> Iterator[Chunk]:
    """One atomic chunk per claim↔prior-art pair.

    Spec §3.4: "PatentMatch claim ↔ prior-art pairs as atomic chunks (no
    chunking)". The canonical HPI-Naumann schema (claim_text + cited_text
    + label) lets us index both halves of each pair as one searchable
    chunk, with the X/A label riding in metadata so a Family B
    retrieval-cell evaluator can score positives vs negatives later.

    Chunk text format: `<claim_text> [PRIOR ART <X|A>]: <cited_text>`.
    The bracketed label keeps the BGE embedding sensitive to whether
    the pair is novelty-prejudicial (X) or background (A); at retrieval
    time queries that look like claims will preferentially surface X
    pairs whose claim halves are semantically close.
    """
    seen = 0
    for path in sorted(src_dir.glob("*.jsonl")):
        with path.open() as f:
            for line in f:
                row = json.loads(line)
                claim_text = (row.get("claim_text") or "").strip()
                cited_text = (row.get("cited_text") or "").strip()
                if not claim_text or not cited_text:
                    continue
                label_letter = row.get("label_letter", "?")
                combined = f"{claim_text} [PRIOR ART {label_letter}]: {cited_text}"
                doc_id = f"{row.get('claim_id')}::{row.get('cited_document_id')}"
                yield Chunk(
                    chunk_id=_stable_id("patentmatch", doc_id, 0),
                    source="patentmatch",
                    doc_id=doc_id,
                    text=combined,
                    metadata={
                        "claim_id": row.get("claim_id"),
                        "patent_application_id": row.get("patent_application_id"),
                        "cited_document_id": row.get("cited_document_id"),
                        "label": row.get("label"),
                        "label_letter": label_letter,
                        "date": row.get("date"),
                        "split": row.get("split"),
                    },
                )
                seen += 1
                if max_rows is not None and seen >= max_rows:
                    return


# --- MPEP -------------------------------------------------------------------


_MPEP_TARGET_TOKENS = 800
_MPEP_OVERLAP_TOKENS = 100
_MPEP_TOKENIZER: Any | None = None


def _mpep_tokenizer(model_name: str) -> Any:
    """Lazy-load the BGE tokenizer used for accurate chunk-size accounting.

    BGE-small-en-v1.5 is BERT-style WordPiece, so the same tokenizer
    drives both the chunker (size accounting) and the embedder (downstream
    encode). One tokenizer load per process, cached at module level.
    """
    global _MPEP_TOKENIZER
    if _MPEP_TOKENIZER is None:
        from transformers import AutoTokenizer  # type: ignore[import-not-found]

        _MPEP_TOKENIZER = AutoTokenizer.from_pretrained(model_name)
    return _MPEP_TOKENIZER


def _slide_token_windows(
    tokenizer: Any,
    text: str,
    target: int,
    overlap: int,
) -> Iterator[tuple[int, str]]:
    """Yield `(window_idx, text)` chunks via token-aware sliding window.

    For subsections under `target` tokens, yields one untouched chunk.
    For longer subsections, walks a sliding window with `overlap` tokens
    of carryover so retrieval hits aren't sliced through mid-sentence.
    Decodes back to text via the tokenizer to keep chunks
    self-contained (no detached subword fragments).
    """
    ids = tokenizer.encode(text, add_special_tokens=False)
    if len(ids) <= target:
        yield 0, text
        return
    step = max(1, target - overlap)
    window_idx = 0
    for start in range(0, len(ids), step):
        chunk_ids = ids[start : start + target]
        if not chunk_ids:
            break
        yield window_idx, tokenizer.decode(chunk_ids, skip_special_tokens=True)
        window_idx += 1
        if start + target >= len(ids):
            break


def chunk_mpep(src_dir: Path, max_rows: int | None) -> Iterator[Chunk]:
    """Semantic-section chunking (~800 tokens, overlap 100) per spec §3.4.

    Reads per-chapter JSONLs produced by `scripts/build_patent_corpus.py`'s
    `pull_mpep`, each row already at h1.page-title (subsection) granularity.
    Subsections under 800 tokens emit one chunk; longer subsections get
    a token-aware sliding window with 100-token overlap.

    Empty-text rows (section banners like "704 Search and Requirements
    for Information" — content lives in 704.01, 704.10, ... subsections)
    are skipped here; their metadata is preserved upstream in the JSONL.

    The tokenizer is the BGE-small tokenizer so window sizes are accurate
    against the embedder's actual token budget (512-token model max).
    """
    # Use the default embedder so chunk sizes are tokenizer-correct.
    tokenizer = _mpep_tokenizer(DEFAULT_MODEL)
    files = sorted(src_dir.glob("mpep-*.jsonl"))
    emitted = 0
    for path in files:
        with path.open() as f:
            for line in f:
                row = json.loads(line)
                text = (row.get("text") or "").strip()
                if not text:
                    continue
                base_doc = f"{row.get('chapter')}/{row.get('section_id')}#{row.get('anchor') or 'top'}"
                for w_idx, w_text in _slide_token_windows(
                    tokenizer,
                    text,
                    _MPEP_TARGET_TOKENS,
                    _MPEP_OVERLAP_TOKENS,
                ):
                    yield Chunk(
                        chunk_id=_stable_id("mpep", base_doc, w_idx),
                        source="mpep",
                        doc_id=base_doc,
                        text=w_text,
                        metadata={
                            "chapter": row.get("chapter"),
                            "section_id": row.get("section_id"),
                            "anchor": row.get("anchor"),
                            "title": row.get("title"),
                            "url": row.get("url"),
                            "window_idx": w_idx,
                        },
                    )
                    emitted += 1
                    if max_rows is not None and emitted >= max_rows:
                        return


# --- Google Patents (T2-followup placeholder) ------------------------------


def chunk_gpat(src_dir: Path, max_rows: int | None) -> Iterator[Chunk]:
    """One chunk per patent: `abstract + first claim`.

    Stub: gpat is `status: blocked` (needs gcloud auth + BigQuery).
    """
    return iter(())


CHUNKERS = {
    "bigpatent": chunk_bigpatent,
    "patentmatch": chunk_patentmatch,
    "mpep": chunk_mpep,
    "gpat": chunk_gpat,
}


# --- Embedding + index ------------------------------------------------------


def _pick_device(requested: str) -> str:
    if requested != "auto":
        return requested
    import torch  # type: ignore[import-not-found]

    return "cuda" if torch.cuda.is_available() else "cpu"


def embed_chunks(
    chunks: list[Chunk],
    model_name: str,
    batch_size: int,
    device: str,
) -> tuple[Any, str | None]:
    """Run BGE-small encoder; returns (np.ndarray[N, D], model_revision)."""
    from sentence_transformers import SentenceTransformer  # type: ignore[import-not-found]

    print(f"[embed] loading {model_name} on device={device}", flush=True)
    model = SentenceTransformer(model_name, device=device)
    revision: str | None = None
    try:
        from huggingface_hub import HfApi  # type: ignore[import-not-found]

        revision = HfApi().model_info(model_name).sha
    except Exception:  # noqa: BLE001
        revision = None

    texts = [c.text for c in chunks]
    t0 = time.time()
    vectors = model.encode(
        texts,
        batch_size=batch_size,
        show_progress_bar=True,
        normalize_embeddings=True,  # BGE convention — inner-product == cosine
        convert_to_numpy=True,
    )
    print(
        f"[embed] {len(texts):,} chunks → {vectors.shape} in {time.time() - t0:.1f}s",
        flush=True,
    )
    return vectors, revision


def build_index(vectors: Any, index_type: str) -> Any:
    """Build FAISS index. Flat-IP for v1.0 (corpus < 100k vectors).

    Flat-IP on normalized BGE vectors = cosine similarity. IVFFlat is
    wired but needs training data — scale-flip lives in W2.
    """
    import faiss  # type: ignore[import-not-found]

    dim = vectors.shape[1]
    if index_type == "flat":
        index = faiss.IndexFlatIP(dim)
    elif index_type == "ivf":
        nlist = max(8, int(vectors.shape[0] ** 0.5))
        quantizer = faiss.IndexFlatIP(dim)
        index = faiss.IndexIVFFlat(quantizer, dim, nlist, faiss.METRIC_INNER_PRODUCT)
        index.train(vectors)
        index.nprobe = min(16, nlist)
    else:
        raise ValueError(f"unknown index_type: {index_type}")
    index.add(vectors)
    print(f"[index] {index_type} dim={dim} ntotal={index.ntotal}", flush=True)
    return index


# --- Persistence ------------------------------------------------------------


def write_parquet(chunks: list[Chunk], path: Path) -> None:
    import pandas as pd  # type: ignore[import-not-found]

    df = pd.DataFrame(
        [
            {
                "chunk_id": c.chunk_id,
                "source": c.source,
                "doc_id": c.doc_id,
                "text": c.text,
                "metadata_json": json.dumps(c.metadata),
            }
            for c in chunks
        ]
    )
    df.to_parquet(path, index=False)
    print(f"[parquet] {len(df):,} rows → {path} ({path.stat().st_size / 1e6:.1f} MB)")


def write_meta(meta: dict[str, Any], path: Path) -> None:
    path.write_text(json.dumps(meta, indent=2) + "\n")


def write_snapshot(meta: dict[str, Any]) -> None:
    SNAPSHOT_PATH.parent.mkdir(parents=True, exist_ok=True)
    SNAPSHOT_PATH.write_text(json.dumps(meta, indent=2) + "\n")
    print(f"[snapshot] → {SNAPSHOT_PATH}")


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument(
        "--corpus-dir", type=Path, default=DEFAULT_CORPUS, help=f"Default: {DEFAULT_CORPUS}"
    )
    p.add_argument("--out-dir", type=Path, default=DEFAULT_OUT, help=f"Default: {DEFAULT_OUT}")
    p.add_argument("--model", default=DEFAULT_MODEL, help=f"Default: {DEFAULT_MODEL}")
    p.add_argument(
        "--sources",
        default=",".join(ALL_SOURCES),
        help=f"Comma-separated source names. Default: {','.join(ALL_SOURCES)}",
    )
    p.add_argument("--max-rows", type=int, default=None, help="Row cap per source")
    p.add_argument("--batch-size", type=int, default=64)
    p.add_argument("--device", default="auto", choices=("auto", "cpu", "cuda"))
    p.add_argument(
        "--index-type",
        default="flat",
        choices=("flat", "ivf"),
        help="Default 'flat' — switch to 'ivf' when corpus > ~100k vectors.",
    )
    p.add_argument("--force", action="store_true", help="Overwrite existing index files.")
    args = p.parse_args()

    requested = [s.strip() for s in args.sources.split(",") if s.strip()]
    unknown = [s for s in requested if s not in CHUNKERS]
    if unknown:
        print(f"FATAL: unknown sources: {unknown}", file=sys.stderr)
        return 2

    args.out_dir.mkdir(parents=True, exist_ok=True)
    index_path = args.out_dir / "index.faiss"
    parquet_path = args.out_dir / "chunks.parquet"
    meta_path = args.out_dir / "meta.json"

    if index_path.exists() and not args.force:
        print(
            f"SKIP — {index_path} exists. Use --force to rebuild.",
            file=sys.stderr,
        )
        return 0

    chunks: list[Chunk] = []
    per_source: dict[str, int] = {}
    for src in requested:
        src_dir = args.corpus_dir / src
        if not src_dir.exists():
            print(f"[{src}] SKIP — {src_dir} missing")
            per_source[src] = 0
            continue
        before = len(chunks)
        for c in CHUNKERS[src](src_dir, args.max_rows):
            chunks.append(c)
        added = len(chunks) - before
        per_source[src] = added
        print(f"[{src}] +{added:,} chunks (total {len(chunks):,})")

    if not chunks:
        print("FATAL: no chunks materialized — corpus dirs empty?", file=sys.stderr)
        return 3

    device = _pick_device(args.device)
    vectors, model_revision = embed_chunks(chunks, args.model, args.batch_size, device)
    index = build_index(vectors, args.index_type)

    import faiss  # type: ignore[import-not-found]

    faiss.write_index(index, str(index_path))
    print(f"[index] → {index_path} ({index_path.stat().st_size / 1e6:.1f} MB)")
    write_parquet(chunks, parquet_path)

    meta = {
        "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "spec_ref": "specs/patent-strategist-v1.md §3.4",
        "model": args.model,
        "model_revision": model_revision,
        "device": device,
        "batch_size": args.batch_size,
        "dim": int(vectors.shape[1]),
        "total_vectors": int(vectors.shape[0]),
        "index_type": args.index_type,
        "index_metric": "inner_product (cosine on L2-normalized vectors)",
        "chunks_per_source": per_source,
        "files": {
            "index": str(index_path),
            "chunks": str(parquet_path),
            "meta": str(meta_path),
        },
    }
    write_meta(meta, meta_path)
    write_snapshot(meta)

    print("\nDONE")
    for k, v in per_source.items():
        print(f"  {k:12s} {v:>7,} chunks")
    print(f"  TOTAL        {len(chunks):>7,} vectors @ dim={vectors.shape[1]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
