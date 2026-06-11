#!/usr/bin/env python3
# Copyright 2026 Manav Sehgal
# SPDX-License-Identifier: Apache-2.0
"""Score Advisor retrieval recall through the LIVE Cortex retrieval stack.

`score_recall.py` is the deterministic local BM25 baseline. This script is the
§14 "retriever recall remains green on public corpus" gate run through the
production retrieval lane instead: the Advisor public corpus pack is ingested
into pgvector via `fieldkit.memory` (the M10 Cortex ingest path — 900-word
chunks, provenance card, NIM `llama-nemotron-embed-1b-v2` embeddings) and the
frozen bench is scored with `MemoryIndex.query` (cosine dense, the M10-9
production query backend).

The corpus pack lands in its OWN table (`advisor_corpus_v01`) so the operator's
`blog_chunks` Second Brain index is untouched — corpus packs are swappable
units per spec OA-NV-8.

Chunking rule: each 900-word body chunk is prefixed with the same provenance
metadata line the v0.1 BM25 chunks carried (source_id, citation_label, title,
roles) so source-id and citation-label lookups stay measurable like-for-like
with `rag-recall-v0.1.json`.

Prereqs: pgvector container on :5432, `nim-embed-nemotron` on :8001.

Usage:

    /tmp/arena-venv/bin/python3 scripts/orionfold_advisor/score_recall_live.py
    ... --skip-ingest      # rescore against an already-ingested table
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from score_recall import (  # type: ignore
    HELDOUT_PATH,
    MANIFEST_PATH,
    POOL_PATH,
    REPO_ROOT,
    _load_rows,
    _read_jsonl,
    _strip_markup,
    _write_json,
    _write_jsonl,
)

from fieldkit.memory import (
    CHUNK_OVERLAP,
    EMBED_BATCH,
    WORDS_PER_CHUNK,
    MemoryIndex,
    Provenance,
    chunk_words,
)

EVIDENCE_DIR = REPO_ROOT / "evidence" / "orionfold-advisor"
REPORT_PATH = EVIDENCE_DIR / "rag-recall-v0.1-cortex.json"
PREDICTIONS_PATH = EVIDENCE_DIR / "rag-recall-v0.1-cortex.predictions.jsonl"
VERSION = "v0.1"
TABLE = "advisor_corpus_v01"
DEFAULT_TOP_K = (1, 3, 5, 10)
#: chunks fetched per query before source-level dedup (>= 10 unique sources).
CHUNK_POOL = 80


def _metadata_line(source: dict[str, Any]) -> str:
    """The same provenance metadata text the v0.1 BM25 chunks carried."""
    return " ".join(
        str(source.get(key) or "")
        for key in (
            "source_id",
            "path_or_url",
            "source_class",
            "source_role",
            "book_surface",
            "citation_label",
            "title",
            "slug",
            "artifact_slug",
            "product_slug",
            "chapter_id",
        )
    ).strip()


def ingest_corpus(index: MemoryIndex, manifest: list[dict[str, Any]]) -> dict[str, Any]:
    """Chunk + embed + upsert the corpus pack via the production primitives.

    Mirrors `fieldkit.memory.ingest_sources` (same chunker, batch size, upsert,
    indexes) with one corpus-pack rule on top: every chunk is prefixed with the
    source's provenance metadata line.
    """
    index.ensure_schema()
    index.replace_slugs(str(s["source_id"]) for s in manifest)

    rows: list[tuple[str, int, str, Any, Provenance]] = []
    pending_meta: list[tuple[str, int, str, Provenance]] = []
    pending_text: list[str] = []
    chunk_total = 0

    def flush() -> None:
        if not pending_text:
            return
        vecs = index._embed(pending_text, "passage")
        for (slug, idx, text, prov), vec in zip(pending_meta, vecs, strict=True):
            rows.append((slug, idx, text, vec, prov))
        pending_text.clear()
        pending_meta.clear()

    for source in manifest:
        path = REPO_ROOT / source["path_or_url"]
        if not path.exists():
            raise FileNotFoundError(f"manifest path missing: {source['path_or_url']}")
        body = _strip_markup(path.read_text(encoding="utf-8", errors="replace"))
        meta = _metadata_line(source)
        prov = Provenance(
            source="article",  # all 181 sources are published_orionfold tier
            kind=str(source["source_class"]),
            doc_date=str(source.get("date_or_version") or ""),
            link=str(source["path_or_url"]),
        )
        for idx, chunk in enumerate(chunk_words(body)):
            if not chunk.strip():
                continue
            chunk_total += 1
            pending_text.append(f"{meta}\n\n{chunk}")
            pending_meta.append((str(source["source_id"]), idx, f"{meta}\n\n{chunk}", prov))
            if len(pending_text) >= EMBED_BATCH:
                flush()
    flush()
    written = index.write_chunks(rows)
    index.create_indexes()
    return {"chunks_written": written, "chunk_total": chunk_total}


def _top_unique_sources(
    hits: list[dict[str, Any]], by_id: dict[str, dict[str, Any]], top_k: int
) -> list[dict[str, Any]]:
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for hit in hits:
        sid = str(hit["slug"])
        if sid in seen:
            continue
        seen.add(sid)
        src = by_id.get(sid, {})
        out.append(
            {
                "source_id": sid,
                "dist": round(float(hit["dist"]), 6),
                "path_or_url": src.get("path_or_url"),
                "source_class": src.get("source_class"),
                "source_role": src.get("source_role"),
                "book_surface": src.get("book_surface"),
                "title": src.get("title"),
                "citation_label": src.get("citation_label"),
            }
        )
        if len(out) >= top_k:
            break
    return out


def score(
    index: MemoryIndex,
    manifest: list[dict[str, Any]],
    rows: list[dict[str, Any]],
    top_k_values: tuple[int, ...],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    by_id = {str(s["source_id"]): s for s in manifest}
    source_ids = set(by_id)
    max_k = max(top_k_values)

    def new_bucket() -> dict[str, Any]:
        return {
            "answerable_n": 0,
            "refusal_n": 0,
            "source_recall": {f"@{k}": 0 for k in top_k_values},
            "chunk_recall": {f"@{k}": 0 for k in top_k_values},
            "source_misses_at_5": [],
        }

    metrics = new_bucket()
    metrics["missing_expected_sources"] = []
    by_family: dict[str, dict[str, Any]] = defaultdict(new_bucket)
    by_split: dict[str, dict[str, Any]] = defaultdict(new_bucket)
    predictions: list[dict[str, Any]] = []

    for row in rows:
        expected = set(row.get("source_ids") or [])
        missing = sorted(expected - source_ids)
        if missing:
            metrics["missing_expected_sources"].append(
                {"task_id": row["task_id"], "source_ids": missing}
            )
        hits = index.query(str(row["question"]), top_k=CHUNK_POOL)
        top_sources = _top_unique_sources(hits, by_id, max_k)
        top_source_ids = [h["source_id"] for h in top_sources]
        top_chunk_sources = [str(h["slug"]) for h in hits[:max_k]]
        family = str(row["family"])
        split_name = str(row["split"])
        fam = by_family[family]
        split_bucket = by_split[split_name]

        if row.get("expected_behavior") == "refuse":
            metrics["refusal_n"] += 1
            fam["refusal_n"] += 1
            split_bucket["refusal_n"] += 1
        else:
            metrics["answerable_n"] += 1
            fam["answerable_n"] += 1
            split_bucket["answerable_n"] += 1
            for k in top_k_values:
                key = f"@{k}"
                source_hit = bool(expected & set(top_source_ids[:k]))
                chunk_hit = bool(expected & set(top_chunk_sources[:k]))
                for bucket in (metrics, fam, split_bucket):
                    bucket["source_recall"][key] += int(source_hit)
                    bucket["chunk_recall"][key] += int(chunk_hit)
            if not (expected & set(top_source_ids[:5])):
                miss = {
                    "task_id": row["task_id"],
                    "split": split_name,
                    "family": family,
                    "expected_source_ids": sorted(expected),
                    "top5_source_ids": top_source_ids[:5],
                }
                metrics["source_misses_at_5"].append(miss)
                fam["source_misses_at_5"].append(miss)
                split_bucket["source_misses_at_5"].append(miss)

        predictions.append(
            {
                "task_id": row["task_id"],
                "split": row["split"],
                "family": family,
                "expected_behavior": row["expected_behavior"],
                "expected_source_ids": sorted(expected),
                "top_sources": top_sources[:10],
                "top_chunks": [
                    {
                        "source_id": str(h["slug"]),
                        "chunk_idx": h["chunk_idx"],
                        "dist": round(float(h["dist"]), 6),
                    }
                    for h in hits[:10]
                ],
            }
        )

    answerable_n = metrics["answerable_n"]
    for bucket in (metrics, *by_family.values(), *by_split.values()):
        n = bucket["answerable_n"]
        for metric_name in ("source_recall", "chunk_recall"):
            for k in top_k_values:
                key = f"@{k}"
                raw = bucket[metric_name][key]
                bucket[metric_name][key] = None if n == 0 else round(raw / n, 4)

    baseline = json.loads((EVIDENCE_DIR / "rag-recall-v0.1.json").read_text())
    report = {
        "generated": date.today().isoformat(),
        "version": VERSION,
        "split": "all",
        "method": "live-cortex-pgvector-dense",
        "stack": {
            "ingest": "fieldkit.memory chunk_words(900/150) + provenance card; "
            "per-chunk metadata prefix matching rag-recall-v0.1 BM25 chunks",
            "embedder": index.embed_model,
            "embed_url": index.embed_url,
            "table": index.table,
            "query": "MemoryIndex.query cosine dense (M10-9), rerank off",
            "chunk_pool_per_query": CHUNK_POOL,
        },
        "top_k": list(top_k_values),
        "manifest_path": MANIFEST_PATH.relative_to(REPO_ROOT).as_posix(),
        "bench_paths": [
            POOL_PATH.relative_to(REPO_ROOT).as_posix(),
            HELDOUT_PATH.relative_to(REPO_ROOT).as_posix(),
        ],
        "manifest_sha256_12": hashlib.sha256(MANIFEST_PATH.read_bytes()).hexdigest()[:12],
        "bench_sha256_12": hashlib.sha256(
            POOL_PATH.read_bytes() + HELDOUT_PATH.read_bytes()
        ).hexdigest()[:12],
        "source_count": len(manifest),
        "row_count": len(rows),
        "metrics": metrics,
        "by_family": dict(sorted(by_family.items())),
        "by_split": dict(sorted(by_split.items())),
        "baseline_bm25": {
            "report": "evidence/orionfold-advisor/rag-recall-v0.1.json",
            "source_recall": baseline["metrics"]["source_recall"],
            "heldout_source_recall": baseline["by_split"]["heldout"]["source_recall"],
        },
        "gate": {
            "name": "advisor-rag-source-recall-live",
            "threshold": "source_recall@5 >= 0.90 on answerable rows; no missing expected sources",
            "passed": (
                answerable_n > 0
                and not metrics["missing_expected_sources"]
                and (metrics["source_recall"]["@5"] or 0.0) >= 0.90
            ),
        },
        "notes": [
            "Live-lane twin of rag-recall-v0.1.json: same manifest, same frozen bench, "
            "retrieval through the production Cortex stack (pgvector + NIM embedder) "
            "instead of local BM25.",
            "Corpus pack ingested into its own table (advisor_corpus_v01); the operator "
            "blog_chunks Second Brain index is untouched (OA-NV-8 corpus-pack swap).",
            "Refusal rows have no expected public source ids and are excluded from "
            "recall denominators.",
        ],
    }
    return report, predictions


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skip-ingest", action="store_true")
    parser.add_argument("--report", type=Path, default=REPORT_PATH)
    parser.add_argument("--predictions", type=Path, default=PREDICTIONS_PATH)
    args = parser.parse_args()

    manifest = _read_jsonl(MANIFEST_PATH)
    rows = _load_rows("all", POOL_PATH, HELDOUT_PATH)
    index = MemoryIndex(table=TABLE)

    if not args.skip_ingest:
        stats = ingest_corpus(index, manifest)
        print(f"ingested {stats['chunks_written']} chunks into {TABLE}")

    report, predictions = score(index, manifest, rows, DEFAULT_TOP_K)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    _write_json(args.report, report)
    _write_jsonl(args.predictions, predictions)

    metrics = report["metrics"]
    print(f"wrote live Cortex recall report -> {args.report}")
    print(
        "answerable={answerable} refusal={refusal} source_recall@5={recall} gate={gate}".format(
            answerable=metrics["answerable_n"],
            refusal=metrics["refusal_n"],
            recall=metrics["source_recall"]["@5"],
            gate="pass" if report["gate"]["passed"] else "fail",
        )
    )


if __name__ == "__main__":
    main()
