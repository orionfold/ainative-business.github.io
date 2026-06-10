#!/usr/bin/env python3
# Copyright 2026 Manav Sehgal
# SPDX-License-Identifier: Apache-2.0
"""Score deterministic Advisor retrieval recall over the public corpus manifest.

This is the first RAG gate for `_SPECS/orionfold-advisor-unsloth-arena-v1.md`:
it measures whether the frozen Advisor bench can retrieve its expected public
sources from the corrected manifest before any generator, embedding service, or
training lane is armed.

The scorer is intentionally local and deterministic. It builds provenance-rich
lexical chunks from `public-corpus-manifest.jsonl`, scores queries with a small
BM25 implementation, and writes:

    evidence/orionfold-advisor/rag-recall-v0.1.json
    evidence/orionfold-advisor/rag-recall-v0.1.predictions.jsonl

Usage:

    python3 scripts/orionfold_advisor/score_recall.py
    python3 scripts/orionfold_advisor/score_recall.py --split heldout
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
EVIDENCE_DIR = REPO_ROOT / "evidence" / "orionfold-advisor"
MANIFEST_PATH = EVIDENCE_DIR / "public-corpus-manifest.jsonl"
POOL_PATH = EVIDENCE_DIR / "advisor-bench-v0.1.jsonl"
HELDOUT_PATH = EVIDENCE_DIR / "advisor-bench-v0.1.heldout.jsonl"
REPORT_PATH = EVIDENCE_DIR / "rag-recall-v0.1.json"
PREDICTIONS_PATH = EVIDENCE_DIR / "rag-recall-v0.1.predictions.jsonl"
VERSION = "v0.1"
DEFAULT_TOP_K = (1, 3, 5, 10)
DEFAULT_CHUNK_TOKENS = 220
DEFAULT_CHUNK_OVERLAP = 40

TOKEN_RE = re.compile(r"[a-z0-9]+")
STOPWORDS = {
    "a",
    "about",
    "after",
    "and",
    "are",
    "as",
    "at",
    "be",
    "before",
    "by",
    "can",
    "cite",
    "citing",
    "does",
    "for",
    "from",
    "how",
    "in",
    "is",
    "it",
    "of",
    "on",
    "or",
    "public",
    "should",
    "source",
    "the",
    "them",
    "to",
    "what",
    "when",
    "which",
    "with",
}


@dataclass(frozen=True)
class Chunk:
    chunk_id: str
    source_id: str
    path_or_url: str
    source_class: str
    source_role: str
    book_surface: str | None
    title: str
    citation_label: str
    text: str
    token_counts: Counter[str]
    length: int


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, sort_keys=True) + "\n")


def _tokenize(text: str) -> list[str]:
    return [tok for tok in TOKEN_RE.findall(text.lower()) if tok not in STOPWORDS and len(tok) > 1]


def _strip_markup(text: str) -> str:
    text = re.sub(r"^---\n.*?\n---\n", " ", text, flags=re.DOTALL)
    text = re.sub(r"```.*?```", " ", text, flags=re.DOTALL)
    text = re.sub(r"`([^`]+)`", r"\1", text)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\{[^{}]*\}", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _stable_chunk_id(source_id: str, ordinal: int) -> str:
    digest = hashlib.sha1(f"{source_id}:{ordinal}".encode()).hexdigest()[:12]
    return f"{source_id}#{ordinal:04d}-{digest}"


def _chunk_tokens(tokens: list[str], size: int, overlap: int) -> list[list[str]]:
    if len(tokens) <= size:
        return [tokens]
    step = max(1, size - overlap)
    chunks: list[list[str]] = []
    for start in range(0, len(tokens), step):
        chunk = tokens[start : start + size]
        if chunk:
            chunks.append(chunk)
        if start + size >= len(tokens):
            break
    return chunks


def build_chunks(manifest: list[dict[str, Any]], chunk_tokens: int, chunk_overlap: int) -> list[Chunk]:
    chunks: list[Chunk] = []
    for source in manifest:
        path = REPO_ROOT / source["path_or_url"]
        if not path.exists():
            raise FileNotFoundError(f"manifest path missing: {source['path_or_url']}")
        raw_text = _strip_markup(path.read_text(encoding="utf-8", errors="replace"))
        metadata_text = " ".join(
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
        )
        body_tokens = _tokenize(raw_text)
        metadata_tokens = _tokenize(metadata_text)
        for idx, window in enumerate(_chunk_tokens(body_tokens, chunk_tokens, chunk_overlap)):
            tokens = metadata_tokens + window
            text = f"{metadata_text}\n\n{' '.join(window[:120])}"
            chunks.append(
                Chunk(
                    chunk_id=_stable_chunk_id(str(source["source_id"]), idx),
                    source_id=str(source["source_id"]),
                    path_or_url=str(source["path_or_url"]),
                    source_class=str(source["source_class"]),
                    source_role=str(source["source_role"]),
                    book_surface=source.get("book_surface"),
                    title=str(source["title"]),
                    citation_label=str(source["citation_label"]),
                    text=text,
                    token_counts=Counter(tokens),
                    length=len(tokens),
                )
            )
    return chunks


def bm25_scores(query: str, chunks: list[Chunk], *, k1: float = 1.5, b: float = 0.75) -> list[tuple[float, Chunk]]:
    query_terms = _tokenize(query)
    if not query_terms:
        return []
    doc_freq: Counter[str] = Counter()
    for chunk in chunks:
        for term in set(chunk.token_counts):
            doc_freq[term] += 1
    avgdl = sum(chunk.length for chunk in chunks) / max(1, len(chunks))
    n_docs = len(chunks)
    query_counts = Counter(query_terms)

    scored: list[tuple[float, Chunk]] = []
    for chunk in chunks:
        score = 0.0
        for term, qf in query_counts.items():
            tf = chunk.token_counts.get(term, 0)
            if tf == 0:
                continue
            idf = math.log(1 + (n_docs - doc_freq[term] + 0.5) / (doc_freq[term] + 0.5))
            denom = tf + k1 * (1 - b + b * chunk.length / avgdl)
            score += idf * ((tf * (k1 + 1)) / denom) * (1 + math.log(qf))
        if score > 0:
            scored.append((score, chunk))
    scored.sort(key=lambda item: (-item[0], item[1].source_id, item[1].chunk_id))
    return scored


def _top_unique_sources(scored: list[tuple[float, Chunk]], top_k: int) -> list[dict[str, Any]]:
    seen: set[str] = set()
    rows: list[dict[str, Any]] = []
    for score, chunk in scored:
        if chunk.source_id in seen:
            continue
        seen.add(chunk.source_id)
        rows.append(
            {
                "source_id": chunk.source_id,
                "score": round(score, 6),
                "path_or_url": chunk.path_or_url,
                "source_class": chunk.source_class,
                "source_role": chunk.source_role,
                "book_surface": chunk.book_surface,
                "title": chunk.title,
                "citation_label": chunk.citation_label,
            }
        )
        if len(rows) >= top_k:
            break
    return rows


def _top_chunks(scored: list[tuple[float, Chunk]], top_k: int) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for score, chunk in scored[:top_k]:
        rows.append(
            {
                "chunk_id": chunk.chunk_id,
                "source_id": chunk.source_id,
                "score": round(score, 6),
                "path_or_url": chunk.path_or_url,
                "source_class": chunk.source_class,
                "source_role": chunk.source_role,
                "book_surface": chunk.book_surface,
                "title": chunk.title,
            }
        )
    return rows


def _load_rows(split: str, pool_path: Path, heldout_path: Path) -> list[dict[str, Any]]:
    pool = _read_jsonl(pool_path)
    heldout = _read_jsonl(heldout_path)
    if split == "pool":
        return pool
    if split == "heldout":
        return heldout
    return pool + heldout


def score_recall(
    *,
    split: str,
    top_k_values: tuple[int, ...],
    chunk_tokens: int,
    chunk_overlap: int,
    # OA-NV-8 corpus-pack swap: the pack (manifest + gold bench) is data, the
    # scorer is harness. Defaults are the Orionfold public pack; a customer /
    # synthetic fixture pack swaps in by path with zero code change.
    manifest_path: Path = MANIFEST_PATH,
    pool_path: Path = POOL_PATH,
    heldout_path: Path = HELDOUT_PATH,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    manifest = _read_jsonl(manifest_path)
    source_ids = {row["source_id"] for row in manifest}
    rows = _load_rows(split, pool_path, heldout_path)
    chunks = build_chunks(manifest, chunk_tokens, chunk_overlap)
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
            metrics["missing_expected_sources"].append({"task_id": row["task_id"], "source_ids": missing})
        scored = bm25_scores(str(row["question"]), chunks)
        top_chunks = _top_chunks(scored, max_k)
        top_sources = _top_unique_sources(scored, max_k)
        top_chunk_sources = [hit["source_id"] for hit in top_chunks]
        top_source_ids = [hit["source_id"] for hit in top_sources]
        family = str(row["family"])
        split_name = str(row["split"])
        fam = by_family[family]
        split_bucket = by_split[split_name]

        is_refusal = row.get("expected_behavior") == "refuse"
        if is_refusal:
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
                metrics["source_recall"][key] += int(source_hit)
                metrics["chunk_recall"][key] += int(chunk_hit)
                fam["source_recall"][key] += int(source_hit)
                fam["chunk_recall"][key] += int(chunk_hit)
                split_bucket["source_recall"][key] += int(source_hit)
                split_bucket["chunk_recall"][key] += int(chunk_hit)
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
                "top_sources": top_sources,
                "top_chunks": top_chunks,
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

    manifest_hash = hashlib.sha256(manifest_path.read_bytes()).hexdigest()[:12]
    bench_hash = hashlib.sha256(pool_path.read_bytes() + heldout_path.read_bytes()).hexdigest()[:12]
    report = {
        "generated": date.today().isoformat(),
        "version": VERSION,
        "split": split,
        "method": "local-bm25-provenance-chunks",
        "top_k": list(top_k_values),
        "chunk_tokens": chunk_tokens,
        "chunk_overlap": chunk_overlap,
        "manifest_path": manifest_path.relative_to(REPO_ROOT).as_posix(),
        "bench_paths": [
            pool_path.relative_to(REPO_ROOT).as_posix(),
            heldout_path.relative_to(REPO_ROOT).as_posix(),
        ],
        "manifest_sha256_12": manifest_hash,
        "bench_sha256_12": bench_hash,
        "source_count": len(manifest),
        "chunk_count": len(chunks),
        "row_count": len(rows),
        "metrics": metrics,
        "by_family": dict(sorted(by_family.items())),
        "by_split": dict(sorted(by_split.items())),
        "gate": {
            "name": "advisor-rag-source-recall",
            "threshold": "source_recall@5 >= 0.90 on answerable rows; no missing expected sources",
            "passed": (
                answerable_n > 0
                and not metrics["missing_expected_sources"]
                and (metrics["source_recall"]["@5"] or 0.0) >= 0.90
            ),
        },
        "notes": [
            "Retrieval-only gate; generator faithfulness, answer quality, and refusal wording are intentionally unscored here.",
            "Refusal rows have no expected public source ids and are counted separately from recall denominators.",
            "BM25 chunks include citation/provenance metadata so source-id and citation-label lookups are measurable before embedding.",
        ],
    }
    return report, predictions


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--split", choices=("all", "pool", "heldout"), default="all")
    parser.add_argument("--chunk-tokens", type=int, default=DEFAULT_CHUNK_TOKENS)
    parser.add_argument("--chunk-overlap", type=int, default=DEFAULT_CHUNK_OVERLAP)
    parser.add_argument("--report", type=Path, default=REPORT_PATH)
    parser.add_argument("--predictions", type=Path, default=PREDICTIONS_PATH)
    # OA-NV-8 corpus-pack swap (spec §14): point the same scorer at a different
    # pack — customer/synthetic manifest + gold bench — with no code change.
    parser.add_argument("--manifest", type=Path, default=MANIFEST_PATH)
    parser.add_argument("--pool", type=Path, default=POOL_PATH)
    parser.add_argument("--heldout", type=Path, default=HELDOUT_PATH)
    args = parser.parse_args()

    if args.chunk_tokens <= 0:
        raise ValueError("--chunk-tokens must be positive")
    if args.chunk_overlap < 0 or args.chunk_overlap >= args.chunk_tokens:
        raise ValueError("--chunk-overlap must be >= 0 and smaller than --chunk-tokens")

    report, predictions = score_recall(
        split=args.split,
        top_k_values=DEFAULT_TOP_K,
        chunk_tokens=args.chunk_tokens,
        chunk_overlap=args.chunk_overlap,
        manifest_path=args.manifest.resolve(),
        pool_path=args.pool.resolve(),
        heldout_path=args.heldout.resolve(),
    )
    args.report.parent.mkdir(parents=True, exist_ok=True)
    _write_json(args.report, report)
    _write_jsonl(args.predictions, predictions)

    metrics = report["metrics"]
    print(f"wrote Advisor RAG recall report -> {args.report}")
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
