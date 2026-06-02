#!/usr/bin/env python3
# Copyright 2026 Manav Sehgal
# SPDX-License-Identifier: Apache-2.0
"""T10 — RAG-only baseline driver for patent-strategist-v0.1 bench.

Per `_SPECS/patent-strategist-v1.md` §3.4 and the W2 HANDOFF: drives the
patent-strategist eval bench against either retrieved context (BGE-small +
FAISS flat-IP at top-k=8), the seeded oracle context, or no context at all,
then optionally calls a llama-server / OpenAI-compatible chat endpoint for
the actual generation step.

Three modes (mutually exclusive):

    --mode closed       no context; pure parametric knowledge
    --mode retrieval    top-k BGE retrieval, joined into context (default 8)
    --mode oracle       prepend the row's seeded oracle_context as-is

One side-mode that skips inference entirely:

    --retrieval-only    dump retrieved chunks + exit. Useful for validating the
                        retrieval layer offline without burning model time.

Inference backend (OpenAI-compatible chat completions):

    --llama-server-url   default http://localhost:8080/v1/chat/completions
    --model              default deepseek-r1-0528-qwen3-8b
    --temperature        default 0.6  (R1-Distill recommended)
    --max-tokens         default 4096
    --timeout-s          default 600  (reasoning models emit long traces)

Output layout (one per run):

    evidence/patent-strategist/baseline-runs/<run-id>/
        config.json         mode, model, top-k, temperature, max_tokens, bench-hash
        predictions.jsonl   one row per question (qid, prompt, prediction, score,
                            retrieved_chunk_ids, retrieval_scores, latency_s)
        scores.json         per-shape mean score + per-use-case slice + N

Scoring: family A / B / D-mcq / D-oa / D-irac → `PATENT_STRATEGIST_SCORER_FNS`.
Family C / E (open-ended judge_rubric) are skipped in v1 — predictions are
emitted but scored as None. The W4 full eval matrix (spec §3.5) wires those
two slots through a Judge backend.

Examples
--------

    # Smoke retrieval layer on 5 D-mcq rows; no llama-server needed:
    python scripts/run_rag_baseline.py --shape D-mcq --limit 5 --retrieval-only

    # Full baseline, retrieval mode, all scorer-supported shapes:
    python scripts/run_rag_baseline.py --all --mode retrieval

    # Oracle upper-bound on D-mcq only:
    python scripts/run_rag_baseline.py --shape D-mcq --mode oracle

    # Closed-book sweep (parametric-only baseline):
    python scripts/run_rag_baseline.py --all --mode closed
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import sys
import time
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

DEFAULT_BENCH_DIR = Path("/home/nvidia/data/eval-benches/patent-strategist")
DEFAULT_INDEX_DIR = Path("/home/nvidia/data/rag/patent-bge-small")
DEFAULT_EVIDENCE_DIR = Path("/home/nvidia/ainative-business.github.io/evidence/patent-strategist/baseline-runs")
DEFAULT_EMBED_MODEL = "BAAI/bge-small-en-v1.5"
DEFAULT_LLAMA_URL = "http://localhost:8080/v1/chat/completions"
DEFAULT_GEN_MODEL = "deepseek-r1-0528-qwen3-8b"
SHAPE_FILES = ["A", "B", "C", "D-mcq", "D-oa", "D-irac", "E"]
SCORER_SUPPORTED_SHAPES = {"A", "B", "D-mcq", "D-oa", "D-irac"}  # C/E are judge_rubric


SYSTEM_PROMPT = (
    "You are a U.S. patent attorney and patent strategist. Answer the question "
    "precisely and concisely. If a context section is provided, ground your "
    "answer in it. For multiple-choice questions, end your answer with "
    "'Answer: <letter>'."
)


# --- retrieval layer ----------------------------------------------------


@dataclass
class RetrievalIndex:
    """Lazily-loaded FAISS index + chunk sidecar + embedding model."""

    index_dir: Path
    embed_model_name: str = DEFAULT_EMBED_MODEL
    device: str = "cuda"

    _index: Any = None  # faiss.Index
    _chunks: Any = None  # pyarrow Table → pandas DataFrame
    _model: Any = None   # SentenceTransformer
    _meta: dict[str, Any] = field(default_factory=dict)

    def load(self) -> None:
        if self._index is not None:
            return
        import faiss  # type: ignore[import-not-found]
        import pandas as pd  # type: ignore[import-not-found]
        from sentence_transformers import SentenceTransformer  # type: ignore[import-not-found]

        meta_path = self.index_dir / "meta.json"
        index_path = self.index_dir / "index.faiss"
        chunks_path = self.index_dir / "chunks.parquet"
        for p in (meta_path, index_path, chunks_path):
            if not p.exists():
                raise FileNotFoundError(f"missing {p.name} in {self.index_dir}")
        self._meta = json.loads(meta_path.read_text())
        print(f"[retrieval] loading index ({self._meta.get('total_vectors')} vectors, "
              f"{self._meta.get('dim')}-dim, {self._meta.get('index_type')})", flush=True)
        self._index = faiss.read_index(str(index_path))
        self._chunks = pd.read_parquet(chunks_path)
        print(f"[retrieval] loading embedder {self.embed_model_name} on {self.device}", flush=True)
        self._model = SentenceTransformer(self.embed_model_name, device=self.device)

    def search(self, query: str, top_k: int) -> list[dict[str, Any]]:
        self.load()
        vec = self._model.encode(
            [query],
            normalize_embeddings=True,
            convert_to_numpy=True,
            show_progress_bar=False,
        )
        # faiss returns (scores, indices) — both shape [1, k]
        scores, indices = self._index.search(vec, top_k)
        out: list[dict[str, Any]] = []
        for i, idx in enumerate(indices[0]):
            if idx < 0:
                continue
            row = self._chunks.iloc[int(idx)]
            out.append({
                "chunk_id": str(row["chunk_id"]),
                "source": str(row["source"]),
                "doc_id": str(row["doc_id"]),
                "text": str(row["text"]),
                "score": float(scores[0][i]),
                "rank": i,
            })
        return out


def format_context(chunks: list[dict[str, Any]], max_chars: int | None = None) -> str:
    """Render retrieved chunks as a numbered context block.

    `max_chars` caps the total context (None = uncapped). Per-chunk source +
    doc_id are included so the model can cite. Truncation is from the tail.
    """
    parts: list[str] = []
    for c in chunks:
        header = f"[{c['rank'] + 1}] source={c['source']}  doc_id={c['doc_id']}"
        parts.append(f"{header}\n{c['text']}")
    block = "\n\n---\n\n".join(parts)
    if max_chars and len(block) > max_chars:
        block = block[:max_chars].rstrip() + "\n…[truncated]"
    return block


# --- inference layer ----------------------------------------------------


@dataclass
class LlamaClient:
    """OpenAI-compatible chat completion via urllib (no httpx dep)."""

    url: str = DEFAULT_LLAMA_URL
    model: str = DEFAULT_GEN_MODEL
    temperature: float = 0.6
    max_tokens: int = 4096
    timeout_s: float = 600.0

    def chat(self, system: str, user: str) -> tuple[str, dict[str, Any]]:
        """Returns (assistant_text, raw_response_envelope)."""
        body = json.dumps({
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
        }).encode()
        req = urllib.request.Request(
            self.url,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=self.timeout_s) as r:
            envelope = json.loads(r.read().decode())
        choices = envelope.get("choices") or []
        text = ""
        if choices and isinstance(choices[0], dict):
            msg = choices[0].get("message") or {}
            text = msg.get("content") or ""
        return text, envelope

    def ping(self) -> bool:
        """Cheap reachability probe — does the chat endpoint accept a 1-token request?"""
        try:
            self.chat(system="", user="hi")
            return True
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError):
            return False


# --- prompt assembly ----------------------------------------------------


def build_user_prompt(question: str, context: str | None, options: list[str] | None = None) -> str:
    parts: list[str] = []
    if context:
        parts.append(f"Context:\n\n{context}\n")
    parts.append(f"Question: {question}")
    if options:
        # D-mcq style — render as labeled choices so the model can answer with a letter.
        labels = "ABCDEFGH"
        choices = "\n".join(f"{labels[i]}. {opt}" for i, opt in enumerate(options))
        parts.append(f"\nOptions:\n{choices}")
    return "\n".join(parts)


# --- scoring ------------------------------------------------------------


def score_prediction(shape: str, prediction: str, gold_label: str) -> float | None:
    """Dispatch to PATENT_STRATEGIST_SCORER_FNS. Returns None for unsupported shapes."""
    if shape not in SCORER_SUPPORTED_SHAPES:
        return None
    from fieldkit.eval.vertical import PATENT_STRATEGIST_SCORER_FNS
    fn = PATENT_STRATEGIST_SCORER_FNS.get(shape)
    if fn is None:
        return None
    try:
        return float(fn(prediction, gold_label))
    except Exception as e:  # noqa: BLE001
        # Don't poison the whole run on a scorer assertion. Log and continue.
        print(f"[scorer] {shape} failed on this row: {e}", flush=True)
        return None


# --- bench loading ------------------------------------------------------


def iter_bench_rows(
    bench_dir: Path,
    shapes: list[str],
    limit: int | None,
    reviewed_only: bool,
) -> list[tuple[str, dict[str, Any]]]:
    """Returns a flat list of (shape, row) tuples, capped at `limit` total rows."""
    out: list[tuple[str, dict[str, Any]]] = []
    for shape in shapes:
        path = bench_dir / f"seed-{shape}.jsonl"
        if not path.exists():
            print(f"[bench] no file at {path}; skipping {shape}", flush=True)
            continue
        with path.open() as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                row = json.loads(line)
                if reviewed_only and not row.get("reviewed"):
                    continue
                if (row.get("tags") or {}).get("rejected"):
                    continue
                out.append((shape, row))
                if limit is not None and len(out) >= limit:
                    return out
    return out


def bench_hash(bench_dir: Path, shapes: list[str]) -> str:
    """SHA256 of the qid set across selected shapes — for reproducibility."""
    h = hashlib.sha256()
    qids: list[str] = []
    for shape in sorted(shapes):
        path = bench_dir / f"seed-{shape}.jsonl"
        if not path.exists():
            continue
        for line in path.read_text().splitlines():
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            qids.append(str(row.get("qid", "")))
    for q in sorted(qids):
        h.update(q.encode())
    return h.hexdigest()[:16]


# --- main loop ----------------------------------------------------------


@dataclass
class RunStats:
    questions: int = 0
    inference_calls: int = 0
    inference_seconds: float = 0.0
    scored: int = 0
    score_sum: float = 0.0
    errors: list[str] = field(default_factory=list)


def run_one_question(
    shape: str,
    row: dict[str, Any],
    *,
    mode: str,
    retrieval_only: bool,
    top_k: int,
    max_context_chars: int | None,
    retriever: RetrievalIndex | None,
    client: LlamaClient | None,
    out_f,
    stats: RunStats,
) -> None:
    question = row.get("question", "")
    gold = row.get("gold_label", "")
    qid = row.get("qid", "?")

    context: str | None = None
    retrieved_chunks: list[dict[str, Any]] = []
    if mode == "oracle":
        context = row.get("oracle_context")
    elif mode == "retrieval":
        assert retriever is not None
        retrieved_chunks = retriever.search(question, top_k=top_k)
        context = format_context(retrieved_chunks, max_chars=max_context_chars)
    # mode == "closed" → no context

    options = row.get("options") or None
    prompt = build_user_prompt(question, context, options)

    prediction = ""
    latency_s = 0.0
    if not retrieval_only:
        assert client is not None
        t0 = time.perf_counter()
        try:
            prediction, _envelope = client.chat(SYSTEM_PROMPT, prompt)
            stats.inference_calls += 1
        except Exception as e:  # noqa: BLE001
            err = f"{qid}: inference failed → {type(e).__name__}: {e}"
            stats.errors.append(err)
            print(f"[infer] {err}", flush=True)
        latency_s = time.perf_counter() - t0
        stats.inference_seconds += latency_s

    score: float | None = None
    if prediction and not retrieval_only:
        score = score_prediction(shape, prediction, gold)
        if score is not None:
            stats.scored += 1
            stats.score_sum += score

    out_row = {
        "qid": qid,
        "shape": shape,
        "family": row.get("family"),
        "use_case": row.get("use_case"),
        "mode": mode,
        "prompt": prompt if retrieval_only else None,  # save prompt only when no prediction recorded
        "prediction": prediction or None,
        "score": score,
        "gold_label": gold,
        "retrieved_chunks": [
            {k: c[k] for k in ("chunk_id", "source", "doc_id", "score", "rank")}
            for c in retrieved_chunks
        ],
        "latency_s": round(latency_s, 3) if latency_s else None,
    }
    out_f.write(json.dumps(out_row, ensure_ascii=False) + "\n")
    out_f.flush()
    stats.questions += 1


def aggregate_scores(predictions_path: Path) -> dict[str, Any]:
    """Per-shape + per-use-case mean score from predictions.jsonl."""
    from collections import defaultdict

    by_shape: dict[str, list[float]] = defaultdict(list)
    by_use_case: dict[str, list[float]] = defaultdict(list)
    skipped_by_shape: dict[str, int] = defaultdict(int)

    with predictions_path.open() as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            shape = row.get("shape", "?")
            score = row.get("score")
            if score is None:
                skipped_by_shape[shape] += 1
                continue
            by_shape[shape].append(float(score))
            uc = row.get("use_case") or "?"
            by_use_case[f"{shape}/{uc}"].append(float(score))

    def mean(xs: list[float]) -> float | None:
        return round(sum(xs) / len(xs), 4) if xs else None

    return {
        "per_shape": {s: {"mean": mean(xs), "n": len(xs)} for s, xs in by_shape.items()},
        "per_use_case": {k: {"mean": mean(xs), "n": len(xs)} for k, xs in by_use_case.items()},
        "skipped_by_shape": dict(skipped_by_shape),
        "overall_mean": mean([v for xs in by_shape.values() for v in xs]),
        "overall_n": sum(len(xs) for xs in by_shape.values()),
    }


# --- CLI ----------------------------------------------------------------


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--bench-dir", default=str(DEFAULT_BENCH_DIR), type=Path)
    ap.add_argument("--index-dir", default=str(DEFAULT_INDEX_DIR), type=Path)
    ap.add_argument("--evidence-dir", default=str(DEFAULT_EVIDENCE_DIR), type=Path)
    ap.add_argument("--shape", action="append", choices=SHAPE_FILES,
                    help="Repeatable; default --all if not passed.")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--mode", choices=["closed", "retrieval", "oracle"], default="retrieval")
    ap.add_argument("--retrieval-only", action="store_true",
                    help="Skip llama-server inference; dump retrieved chunks + exit.")
    ap.add_argument("--limit", type=int, default=None,
                    help="Cap total rows (across shapes) for a thin-slice run.")
    ap.add_argument("--reviewed-only", action="store_true",
                    help="Filter to rows where reviewed=true (T9-blessed subset).")
    ap.add_argument("--top-k", type=int, default=8, help="FAISS retrieval depth (spec §3.4).")
    ap.add_argument("--max-context-chars", type=int, default=None,
                    help="Cap formatted-context length. Default: uncapped.")
    ap.add_argument("--embed-model", default=DEFAULT_EMBED_MODEL)
    ap.add_argument("--embed-device", default="cuda")
    ap.add_argument("--llama-server-url", default=DEFAULT_LLAMA_URL)
    ap.add_argument("--model", default=DEFAULT_GEN_MODEL)
    ap.add_argument("--temperature", type=float, default=0.6)
    ap.add_argument("--max-tokens", type=int, default=4096)
    ap.add_argument("--timeout-s", type=float, default=600.0)
    ap.add_argument("--run-id", default=None, help="Auto-generated if unset.")
    args = ap.parse_args()

    shapes = SHAPE_FILES if args.all or not args.shape else args.shape
    rows = iter_bench_rows(args.bench_dir, shapes, args.limit, args.reviewed_only)
    if not rows:
        print("no bench rows match the filter", file=sys.stderr)
        return 1

    # Inference reachability check (skip if retrieval-only)
    client: LlamaClient | None = None
    if not args.retrieval_only:
        client = LlamaClient(
            url=args.llama_server_url,
            model=args.model,
            temperature=args.temperature,
            max_tokens=args.max_tokens,
            timeout_s=args.timeout_s,
        )
        print(f"[infer] pinging {client.url}...", flush=True)
        if not client.ping():
            print(
                f"[infer] FAIL — could not reach {client.url}. "
                f"Start llama-server first, or pass --retrieval-only.",
                file=sys.stderr,
            )
            return 1
        print("[infer] reachable.", flush=True)

    retriever: RetrievalIndex | None = None
    if args.mode == "retrieval":
        retriever = RetrievalIndex(
            index_dir=args.index_dir,
            embed_model_name=args.embed_model,
            device=args.embed_device,
        )
        retriever.load()  # eager-load so we surface missing-files errors before we start.

    # Run id + output paths
    run_id = args.run_id or (
        dt.datetime.now().strftime("%Y%m%d-%H%M%S")
        + f"-{args.mode}"
        + ("-retonly" if args.retrieval_only else "")
        + "-" + uuid.uuid4().hex[:6]
    )
    run_dir = args.evidence_dir / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    config_path = run_dir / "config.json"
    predictions_path = run_dir / "predictions.jsonl"
    scores_path = run_dir / "scores.json"

    config = {
        "run_id": run_id,
        "started_at": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "mode": args.mode,
        "retrieval_only": args.retrieval_only,
        "shapes": shapes,
        "reviewed_only": args.reviewed_only,
        "limit": args.limit,
        "top_k": args.top_k,
        "max_context_chars": args.max_context_chars,
        "embed_model": args.embed_model,
        "embed_device": args.embed_device,
        "generator": {
            "url": args.llama_server_url,
            "model": args.model,
            "temperature": args.temperature,
            "max_tokens": args.max_tokens,
            "timeout_s": args.timeout_s,
        } if not args.retrieval_only else None,
        "bench_hash": bench_hash(args.bench_dir, shapes),
        "questions_planned": len(rows),
    }
    config_path.write_text(json.dumps(config, indent=2, ensure_ascii=False))
    print(f"[run] {run_id}", flush=True)
    print(f"[run] writing to {run_dir}", flush=True)
    print(f"[run] {len(rows)} questions across {shapes}", flush=True)

    stats = RunStats()
    t0 = time.perf_counter()
    with predictions_path.open("w") as out_f:
        for shape, row in rows:
            print(
                f"[q {stats.questions + 1}/{len(rows)}] {shape}  qid={row.get('qid')}",
                flush=True,
            )
            run_one_question(
                shape, row,
                mode=args.mode,
                retrieval_only=args.retrieval_only,
                top_k=args.top_k,
                max_context_chars=args.max_context_chars,
                retriever=retriever,
                client=client,
                out_f=out_f,
                stats=stats,
            )
    wall = time.perf_counter() - t0

    summary = aggregate_scores(predictions_path)
    summary["wall_seconds"] = round(wall, 1)
    summary["inference_calls"] = stats.inference_calls
    summary["inference_seconds"] = round(stats.inference_seconds, 1)
    summary["error_count"] = len(stats.errors)
    summary["errors"] = stats.errors[:20]
    scores_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False))

    print()
    print("=== run_rag_baseline summary ===")
    print(f"  run_id:           {run_id}")
    print(f"  wall:             {wall:.1f}s")
    print(f"  questions:        {stats.questions}")
    print(f"  inference calls:  {stats.inference_calls}  ({stats.inference_seconds:.1f}s)")
    if summary["overall_n"]:
        print(f"  overall mean:     {summary['overall_mean']}  (n={summary['overall_n']})")
        for shape, s in sorted(summary["per_shape"].items()):
            print(f"    {shape:8}        mean={s['mean']}  n={s['n']}")
    if summary["skipped_by_shape"]:
        label = (
            "unscored (retrieval-only — no prediction)"
            if args.retrieval_only
            else "unscored (judge_rubric or scorer-failed)"
        )
        print(f"  {label}: {summary['skipped_by_shape']}")
    if stats.errors:
        print(f"  errors:           {len(stats.errors)} (see scores.json)")

    return 0 if not stats.errors or stats.questions > 0 else 1


if __name__ == "__main__":
    sys.exit(main())
