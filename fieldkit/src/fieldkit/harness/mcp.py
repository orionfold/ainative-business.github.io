# Copyright 2026 Manav Sehgal
# SPDX-License-Identifier: Apache-2.0
"""fieldkit-as-MCP — let an agent harness drive the Spark's Orionfold pipeline.

The H4 keystone of the **Harnesses** line (`_SPECS/hermes-harness-v1.md` §4.4).
Exposes a *curated* subset of `fieldkit` surfaces as Model-Context-Protocol
tools so a harness — Hermes (Nous Research, MIT) first, but any MCP client —
can operate the box itself: read the inference envelope, measure a GGUF, run a
guarded quantize, dry-run a publish, and ask the Second-Brain RAG corpus.

The curation **is** the containment posture (the H3 hardening philosophy applied
at the tool layer rather than the sandbox layer):

- read-only tools carry `readOnlyHint` and never touch disk or GPU;
- the one expensive write — `quantize_gguf` — **defaults to `dry_run=True`** and
  is envelope-guarded against the source weight footprint;
- `publish_quant_dry_run` is **dry-run-forced**: the MCP surface can stage a
  HuggingFace push and preview the card, but the code path that executes a real
  push is simply not reachable through this server.

Unlike the H3 sandbox, this server runs *on the host* — it is the box-driver, so
its safety comes from the shape of the tool list, not from `--network=none`.
Pair it with a hardened Hermes (`harden_config`) so the harness wrapping the
server is itself contained.

**Transport.** Stdio JSON-RPC — launch with `python -m fieldkit.harness.mcp` and
wire into Hermes with::

    hermes mcp add fieldkit \\
      --command /path/to/python --args -m fieldkit.harness.mcp \\
      --env LLAMA_CPP_BIN=/home/nvidia/llama.cpp/build/bin

**Optional dep.** The `mcp` SDK lives behind the `fieldkit[harness]` extra.
`import fieldkit.harness.mcp` stays cheap and every tool *function* is plain and
unit-testable without the SDK — only `build_mcp_server` needs `mcp` (it lazy-
imports `FastMCP` and raises `McpNotAvailable` with an install hint otherwise).
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

__all__ = [
    "MCP_SERVER_NAME",
    "McpNotAvailable",
    "MCPToolSpec",
    "MCP_TOOL_SPECS",
    "build_mcp_server",
    "run_mcp_server",
    # M8 — Arena dispatcher job-execution tools (also callable plainly).
    "run_vertical_eval",
    "measure_variants",
    # M10 — Arena recall-pipeline job-execution tools.
    "reindex_memory",
    "rag_eval_index",
    "scout_ingest",
    # Phase 3 (rlvr-loop-v1) — closed-loop RLVR job-execution tools.
    "run_rl_loop",
    "requant_checkpoint",
]

MCP_SERVER_NAME = "fieldkit"

# Default quantize ladder — mirrors `quant.quantize_gguf`'s own default. Kept as
# a module constant so the MCP tool can expose it without a mutable default arg.
_DEFAULT_VARIANTS = ("Q4_K_M", "Q5_K_M", "Q6_K", "Q8_0", "F16")


class McpNotAvailable(ImportError):
    """The `mcp` SDK (the `fieldkit[harness]` extra) is not installed in this env.

    `fieldkit.harness.mcp` lazy-imports `mcp.server.fastmcp.FastMCP` so plain
    `import fieldkit` — and even importing this module to call the tool
    functions directly — stays cheap. Install with `pip install
    fieldkit[harness]`.
    """


def _require_fastmcp() -> Any:
    try:
        from mcp.server.fastmcp import FastMCP  # type: ignore[import-not-found]
    except ImportError as exc:  # pragma: no cover - exercised in env without mcp
        raise McpNotAvailable(
            "fieldkit-as-MCP requires the `mcp` SDK. Install the extra: "
            "`pip install fieldkit[harness]`."
        ) from exc
    return FastMCP


@dataclass(frozen=True)
class MCPToolSpec:
    """Static description of one curated MCP tool — the documentation surface.

    Pure data, importable without the `mcp` SDK, so the catalog (and the article
    table) can enumerate the curated surface without booting a server.
    """

    name: str
    surface: str  # the fieldkit module the tool delegates to
    summary: str
    read_only: bool


MCP_TOOL_SPECS: tuple[MCPToolSpec, ...] = (
    MCPToolSpec(
        "spark_inference_envelope",
        "capabilities",
        "Practical inference envelope for a model size on the 128 GB Spark.",
        True,
    ),
    MCPToolSpec(
        "spark_weight_footprint",
        "capabilities",
        "Weight memory footprint (bytes/GB) for a param count + dtype.",
        True,
    ),
    MCPToolSpec(
        "measure_gguf_throughput",
        "quant",
        "Single-stream tok/s of a local GGUF via llama-bench.",
        False,
    ),
    MCPToolSpec(
        "measure_gguf_perplexity",
        "quant",
        "Perplexity of a local GGUF over a corpus via llama-perplexity.",
        False,
    ),
    MCPToolSpec(
        "quantize_gguf",
        "quant",
        "Quantize HF/F16 weights to GGUF variants (dry_run-default, guarded).",
        False,
    ),
    MCPToolSpec(
        "publish_quant_dry_run",
        "publish",
        "Stage + preview an Orionfold quant card without pushing (dry-run-forced).",
        False,
    ),
    MCPToolSpec(
        "ask_second_brain",
        "rag",
        "Ask the ai-field-notes RAG corpus (NIM embed → pgvector → NIM LLM).",
        True,
    ),
    # M8 (Arena control plane) — the dispatcher's job-execution tools. Added
    # by demand (M8-7), not speculatively: `run_vertical_eval` is mcp.py's
    # first `fieldkit.eval` wiring; `measure_variants` reuses `fieldkit.quant`.
    MCPToolSpec(
        "run_vertical_eval",
        "eval",
        "Re-run a vertical bench against a served lane → per-question accuracy.",
        False,
    ),
    MCPToolSpec(
        "measure_variants",
        "quant",
        "Single-stream tok/s across a manifest's GGUF variants via llama-bench.",
        False,
    ),
    # M10 (Bet 5 recall layer) — the recall-pipeline job-execution tools.
    # Promoted from named stubs (M10-1): the dispatcher runs them through this
    # same MCP surface, inheriting the M8 containment posture.
    MCPToolSpec(
        "reindex_memory",
        "memory",
        "Rebuild the Second-Brain index multi-source (articles/lineage/scout) with provenance.",
        False,
    ),
    MCPToolSpec(
        "rag_eval_index",
        "memory",
        "Score the live index against the in-repo qa-eval gold set (cosine-only recall@k).",
        False,
    ),
    MCPToolSpec(
        "scout_ingest",
        "memory",
        "Fold a frontier-scout papers.json (feasibility verdicts) into the index as scout-class memory.",
        False,
    ),
    MCPToolSpec(
        "run_rl_loop",
        "rl",
        "Run one closed-loop RLVR run — verifier-as-reward GRPO with a held-out-only checkpoint gate.",
        False,
    ),
    MCPToolSpec(
        "requant_checkpoint",
        "rl",
        "Re-quantize a held-out-winning RLVR checkpoint to the GGUF variant ladder (dry-run by default).",
        False,
    ),
)


# --- llama.cpp path resolution --------------------------------------------


def _llama_paths() -> Any:
    """Resolve llama.cpp binaries from `LLAMA_CPP_BIN` / PATH (shared helper)."""
    from fieldkit.quant import LlamaCppPaths

    return LlamaCppPaths().resolve()


def _validate_gguf(gguf_path: str) -> Path:
    path = Path(gguf_path).expanduser()
    if not path.exists():
        raise FileNotFoundError(
            f"GGUF not found: {gguf_path}. Pass an absolute path to a .gguf on "
            "the Spark (e.g. /home/nvidia/data/quants/<model>/model-Q4_K_M.gguf)."
        )
    if path.suffix.lower() != ".gguf":
        raise ValueError(f"Not a .gguf file: {gguf_path}")
    return path


# --- Tool functions (plain, testable without the mcp SDK) ------------------


def spark_inference_envelope(model_size: str) -> dict[str, Any]:
    """Practical inference envelope for a model-size key.

    Keys are exact (e.g. "8B params bf16", "70B params fp8", "405B+ params").
    On a miss, returns the available keys so the caller can pick one rather than
    erroring.
    """
    from fieldkit.capabilities import (
        Capabilities,
        UnknownEnvelope,
        practical_inference_envelope,
    )

    try:
        return {
            "model_size": model_size,
            "envelope": practical_inference_envelope(model_size),
        }
    except UnknownEnvelope:
        table = Capabilities.load().memory_budget_rules_of_thumb.practical_inference_envelope
        return {"model_size": model_size, "envelope": None, "available_keys": list(table)}


def spark_weight_footprint(params_b: float, dtype: str = "fp16") -> dict[str, Any]:
    """Weight-only memory footprint for `params_b` billion params at `dtype`."""
    from fieldkit.capabilities import weight_bytes

    nbytes = weight_bytes(params_b=params_b, dtype=dtype)
    return {
        "params_b": params_b,
        "dtype": dtype,
        "weight_bytes": nbytes,
        "weight_gb": round(nbytes / 1e9, 2),
        "unified_memory_gb": 128,
    }


def measure_gguf_throughput(
    gguf_path: str, n_gen: int = 128, n_prompt: int = 512
) -> dict[str, Any]:
    """Single-stream throughput of a local GGUF via llama-bench (real GPU work)."""
    from fieldkit.quant import measure_tokens_per_sec_gguf

    path = _validate_gguf(gguf_path)
    result = measure_tokens_per_sec_gguf(
        gguf_path=path, paths=_llama_paths(), n_gen=n_gen, n_prompt=n_prompt
    )
    return {"gguf_path": str(path), "n_gen": n_gen, "n_prompt": n_prompt, **(result or {})}


def measure_gguf_perplexity(gguf_path: str, corpus_path: str) -> dict[str, Any]:
    """Perplexity of a local GGUF over a text corpus via llama-perplexity."""
    from fieldkit.quant import measure_perplexity_gguf

    path = _validate_gguf(gguf_path)
    corpus = Path(corpus_path).expanduser()
    if not corpus.exists():
        raise FileNotFoundError(f"Corpus not found: {corpus_path}")
    ppl = measure_perplexity_gguf(gguf_path=path, corpus_path=corpus, paths=_llama_paths())
    return {"gguf_path": str(path), "corpus_path": str(corpus), "perplexity": ppl}


def quantize_gguf(
    model_path: str,
    outdir: str,
    variants: Optional[list[str]] = None,
    dry_run: bool = True,
) -> dict[str, Any]:
    """Quantize F16/HF weights to GGUF variants.

    `dry_run=True` by default — returns the plan (commands + target files)
    without running llama-quantize. Set `dry_run=False` to execute. Guarded:
    refuses a source whose F16 footprint alone would exceed the Spark's
    unified-memory envelope.
    """
    from fieldkit.quant import quantize_gguf as _quantize_gguf

    src = Path(model_path).expanduser()
    if not src.exists():
        raise FileNotFoundError(f"Model not found: {model_path}")
    vlist = tuple(variants) if variants else _DEFAULT_VARIANTS

    # Envelope guard: a single F16 GGUF must fit with headroom. We size from the
    # file when it's already an F16 GGUF, else trust the caller's variant list.
    if not dry_run and src.is_file() and src.stat().st_size > 120 * 1024**3:
        raise ValueError(
            f"Source weight is {src.stat().st_size / 1e9:.0f} GB — too large to "
            "quantize safely inside the 128 GB unified-memory envelope."
        )

    report = _quantize_gguf(
        model=src, outdir=Path(outdir).expanduser(), variants=vlist,
        paths=_llama_paths(), dry_run=dry_run,
    )
    return {
        "model": str(src),
        "outdir": str(Path(outdir).expanduser()),
        "variants": list(report.variants),
        "dry_run": dry_run,
        "variant_files": report.variant_files,
        "notes": report.notes,
    }


def publish_quant_dry_run(
    base_model: str,
    repo_name: str,
    variants: list[str],
    recommended_variant: Optional[str] = None,
    perplexity: Optional[dict[str, float]] = None,
    tokens_per_sec: Optional[dict[str, float]] = None,
    article_slug: Optional[str] = None,
) -> dict[str, Any]:
    """Stage + preview an Orionfold quant card. Dry-run-forced — never pushes.

    Builds a minimal `QuantReport` from the passed measurements, renders the
    model card, and stages the would-push file set under a temp dir. Returns the
    repo id, the staged file list, and a card preview. The real-push code path is
    deliberately unreachable through this tool.
    """
    import tempfile

    from fieldkit.publish import publish_quant
    from fieldkit.quant import QuantReport

    report = QuantReport(
        format="gguf",
        base_model=base_model,
        variants=tuple(variants),
        perplexity=dict(perplexity or {}),
        tokens_per_sec=dict(tokens_per_sec or {}),
    )
    with tempfile.TemporaryDirectory(prefix="fk-mcp-stage-") as staging:
        result = publish_quant(
            quant_report=report,
            base_model=base_model,
            repo_name=repo_name,
            staging_dir=staging,
            article_slug=article_slug,
            recommended_variant=recommended_variant,
            dry_run=True,  # forced — this surface never executes a real push
        )
        staged = sorted(p.name for p in Path(staging).rglob("*") if p.is_file())
        card = Path(staging) / "README.md"
        preview = card.read_text()[:1200] if card.exists() else ""
    return {
        "repo": getattr(result, "repo_id", repo_name),
        "dry_run": True,
        "staged_files": staged,
        "card_preview": preview,
    }


#: The grounded-answer system prompt (shared with the standalone SB server, so
#: the one backend gives one answer contract, M10-9).
_SB_SYS_PROMPT = (
    "You are a careful assistant answering questions about the ai-field-notes "
    "project (articles by Manav Sehgal on running AI locally on the NVIDIA DGX "
    "Spark). Answer using ONLY the provided context passages, each labeled with "
    "its source article slug and chunk index like [slug #N]. Answer concisely "
    "and concretely. Cite the passages you used in a trailing line: 'Sources: "
    "[slug #N, slug #N]'. If the context does not contain the answer, reply with "
    "exactly one sentence: 'The provided context does not contain the answer.'"
)


def ask_second_brain(
    query: str,
    retrieve_k: int = 5,
    rerank_k: int = 3,
    max_tokens: int = 256,
    provenance: Optional[list[str]] = None,
) -> dict[str, Any]:
    """Ask the ai-field-notes Second-Brain RAG corpus (read-only).

    **M10-9: retrieval goes through the single ``fieldkit.memory`` backend** —
    the same provenance-aware index the standalone ``second-brain-mcp`` server
    uses, so the trust filter + rerank policy are defined once. ``provenance``
    (a subset of ``fieldkit.memory.SOURCE_CLASSES`` — ``article`` / ``lineage`` /
    ``scout`` / …) restricts the trust tier in the vector SQL itself (M10-4); a
    Spark-measured number and an external claim are not interchangeable.
    Generation uses the local Llama NIM. Requires the embedder NIM + pgvector
    (and, for the answer, the generator NIM) up. Cosine-only on GB10 (M10-7);
    ``rerank_k`` is retained for API stability but rerank is off until a
    ``-dgx-spark`` reranker lands.
    """
    from fieldkit.memory import MemoryIndex
    from fieldkit.nim import NIMClient

    llm_url = os.environ.get("LLM_URL", "http://127.0.0.1:8000/v1")
    llm_model = os.environ.get("LLM_MODEL", "meta/llama-3.1-8b-instruct")

    index = MemoryIndex()  # reads SECOND_BRAIN_PG_DSN / EMBED_URL from env
    hits = index.query(query, top_k=retrieve_k, sources=provenance)

    context = "\n\n".join(
        f"[{h['slug']} #{h['chunk_idx']}]\n{h['text']}" for h in hits
    )
    user = (
        f"Context passages:\n\n{context}\n\nQuestion: {query}\n\nAnswer:"
    )
    generator = NIMClient(base_url=llm_url, model=llm_model)
    resp = generator.chat(
        [
            {"role": "system", "content": _SB_SYS_PROMPT},
            {"role": "user", "content": user},
        ],
        max_tokens=max_tokens,
    )
    answer = resp["choices"][0]["message"]["content"].strip()
    return {
        "query": query,
        "answer": answer,
        "sources": [
            {
                "slug": h["slug"],
                "chunk_idx": h["chunk_idx"],
                "source": h["source"],
                "verdict": h["verdict"],
            }
            for h in hits
        ],
    }


_VERTICAL_SCORERS = ("exact_match", "contains", "numeric_match")


def run_vertical_eval(
    lane: str,
    bench: str,
    *,
    bench_path: Optional[str] = None,
    base_url: Optional[str] = None,
    model: Optional[str] = None,
    scorer: str = "exact_match",
    limit: Optional[int] = None,
    max_tokens: int = 512,
) -> dict[str, Any]:
    """Re-run a vertical bench against a served lane (M8 ``eval_rerun`` body).

    Builds a `model_fn` that talks to the lane's OpenAI-compatible endpoint,
    loads the bench JSONL via `fieldkit.eval.VerticalBench`, runs it, and
    returns per-question grades the Arena dispatcher persists through the
    existing `eval_scores` scorer path. `lane` / `bench` are identifiers
    (echoed back for the store write); `base_url` + `model` locate the served
    lane (default the resident llama-server via env `ARENA_EVAL_BASE_URL` /
    `ARENA_EVAL_MODEL`); `bench_path` is the JSONL gold set.

    Returns ``{lane, bench, scorer_kind, n, mean_normalized, calls: [...]}``
    where each call is ``{qid, score, max_score, normalized}``.
    """
    from fieldkit.eval import VerticalBench, contains, exact_match, numeric_match
    from fieldkit.notebook import OpenAICompatClient

    if scorer not in _VERTICAL_SCORERS:
        raise ValueError(
            f"unknown scorer {scorer!r}; choose one of {_VERTICAL_SCORERS}"
        )
    if not bench_path:
        raise ValueError(
            "run_vertical_eval needs `bench_path` — the bench gold JSONL "
            "(e.g. ~/.fieldkit/arena/benches/<bench>.jsonl). The Arena "
            "dispatcher resolves this from the bench registry "
            "(`fieldkit.arena.jobs.resolve_bench`); pass it explicitly when "
            "calling this tool directly."
        )
    path = Path(bench_path).expanduser()
    if not path.exists():
        raise FileNotFoundError(f"Bench JSONL not found: {bench_path}")

    scorer_fn = {
        "exact_match": exact_match,
        "contains": contains,
        "numeric_match": numeric_match,
    }[scorer]

    endpoint = base_url or os.environ.get(
        "ARENA_EVAL_BASE_URL", "http://127.0.0.1:8080"
    )
    model_name = model or os.environ.get("ARENA_EVAL_MODEL", "resident")
    client = OpenAICompatClient(endpoint=endpoint, model=model_name)

    def model_fn(prompt: str) -> str:
        return client.chat(
            [{"role": "user", "content": prompt}], max_tokens=max_tokens
        )

    vb = VerticalBench.from_jsonl(
        path, name=bench, scorer=scorer_fn, limit=limit
    )
    result = vb.run(model_fn, limit=limit)

    calls: list[dict[str, Any]] = []
    accs: list[float] = []
    for call in result.calls:
        if not call.success:
            continue
        acc = call.metrics.get("accuracy")
        qid = (call.tags or {}).get("qid")
        calls.append(
            {
                "qid": qid,
                "score": acc,
                "max_score": 1.0,
                "normalized": acc,
            }
        )
        if acc is not None:
            accs.append(float(acc))
    mean_normalized = sum(accs) / len(accs) if accs else None
    return {
        "lane": lane,
        "bench": bench,
        "bench_path": str(path),
        "scorer_kind": scorer,
        "n": len(calls),
        "mean_normalized": mean_normalized,
        "calls": calls,
    }


def measure_variants(
    manifest_slug: str,
    gguf_paths: Optional[dict[str, str]] = None,
    n_gen: int = 128,
    n_prompt: int = 512,
) -> dict[str, Any]:
    """Single-stream tok/s across a manifest's GGUF variants (M8 stub job).

    `gguf_paths` maps variant label (e.g. ``"Q4_K_M"``) → absolute .gguf path;
    each is measured via llama-bench (real GPU work, one at a time inside the
    envelope). Returns per-variant throughput keyed by label. Same measure core
    as `measure_gguf_throughput`, batched over a manifest's variants so the
    leaderboard can carry a tok/s column per variant.
    """
    from fieldkit.quant import measure_tokens_per_sec_gguf

    if not gguf_paths:
        raise ValueError(
            "measure_variants needs `gguf_paths` — {variant: /abs/path.gguf}. "
            "The Arena dispatcher fills this from the manifest's variant set."
        )
    paths = _llama_paths()
    variants: dict[str, Any] = {}
    for label, raw in gguf_paths.items():
        path = _validate_gguf(raw)
        result = measure_tokens_per_sec_gguf(
            gguf_path=path, paths=paths, n_gen=n_gen, n_prompt=n_prompt
        )
        variants[label] = {"gguf_path": str(path), **(result or {})}
    return {
        "manifest_slug": manifest_slug,
        "n_variants": len(variants),
        "variants": variants,
    }


# --- M10 (Bet 5 recall layer) — recall-pipeline tools ----------------------

#: Default articles tree for `reindex_memory` — env-overridable so a non-Spark
#: checkout (or a test) can point elsewhere.
_DEFAULT_ARTICLES_DIR = os.environ.get(
    "ARENA_ARTICLES_DIR", "/home/nvidia/ainative-business.github.io/articles"
)


def _index_version(chunk_counts: dict[str, int]) -> str:
    """A short content tag for an index state — stable for a given (slug→count)
    map, so two identical rebuilds carry the same ``index_version`` and the
    promotion gate compares like-for-like. Deterministic (no clock)."""
    import hashlib

    payload = ";".join(f"{s}:{n}" for s, n in sorted(chunk_counts.items()))
    digest = hashlib.sha1(payload.encode()).hexdigest()[:12]
    total = sum(chunk_counts.values())
    return f"idx-{len(chunk_counts)}d-{total}c-{digest}"


def reindex_memory(
    source_set: str = "articles",
    articles_dir: Optional[str] = None,
    papers_json: Optional[str] = None,
    lineage_cards: Optional[list[dict[str, Any]]] = None,
) -> dict[str, Any]:
    """Rebuild the Second-Brain index multi-source with provenance (M10 ``reindex``).

    ``source_set`` ∈ ``{articles, scout, lineage, all}`` selects which source
    classes to (re)ingest. Collects :class:`KnowledgeCard`s, runs the one
    version-controlled ingest (``fieldkit.memory.ingest_sources`` — the retired
    ``ingest_blog.py``'s replacement, M10-2), and returns the chunk delta +
    ``index_version`` for the ``reindex_runs`` row. Requires pgvector + the
    embedder NIM up.
    """
    from fieldkit.memory import (
        MemoryIndex,
        collect_article_sources,
        collect_lineage_sources,
        collect_scout_sources,
        ingest_sources,
    )

    valid = {"articles", "scout", "lineage", "all"}
    if source_set not in valid:
        raise ValueError(f"source_set must be one of {sorted(valid)}; got {source_set!r}")

    index = MemoryIndex()
    index.ensure_schema()
    before = sum(index.chunk_counts().values())

    cards: list[Any] = []
    if source_set in ("articles", "all"):
        cards += collect_article_sources(articles_dir or _DEFAULT_ARTICLES_DIR)
    if source_set in ("scout", "all") and papers_json:
        cards += collect_scout_sources(papers_json)
    if source_set in ("lineage", "all") and lineage_cards:
        cards += collect_lineage_sources(lineage_cards)

    res = ingest_sources(index, cards)
    counts = index.chunk_counts()
    after = sum(counts.values())
    return {
        "source_set": source_set,
        "chunks_before": before,
        "chunks_after": after,
        "articles_n": len(res["slugs"]),
        "by_source": res["by_source"],
        "index_version": _index_version(counts),
    }


def rag_eval_index(
    qa_set: Optional[str] = None,
    top_k: int = 5,
    rerank: bool = False,
) -> dict[str, Any]:
    """Score the live index against the in-repo qa-eval gold set (M10 ``rag_eval``).

    Computes **chunk-recall@k** (``p_chunk_at_k``) and **slug-recall@k**
    (``p_slug_at_k``) — the fraction of gold questions whose ``(source, chunk)``
    / ``source`` appears in the cosine top-k. This is the GB10 **cosine-only
    measured baseline** (M10-7): faithfulness/correctness need the generator NIM
    and are left ``None`` here (the rerank lane is bounded drift). ``rerank`` is
    accepted but unsupported on GB10 (no ``-dgx-spark`` profile) — passing
    ``True`` raises so a score is never silently mislabelled (R22). Requires
    pgvector + the embedder.
    """
    from fieldkit.memory import MemoryIndex, resolve_qa_set

    if rerank:
        raise ValueError(
            "rerank=True is unsupported on GB10 (no -dgx-spark reranker profile); "
            "the cosine-only score is the measured baseline (M10-7). Re-enable via "
            "RERANK_URL when a compatible reranker lands."
        )
    gold_path = resolve_qa_set(qa_set)
    gold = [json.loads(line) for line in Path(gold_path).read_text().splitlines() if line.strip()]
    if not gold:
        raise ValueError(f"qa-eval gold set at {gold_path} is empty")

    index = MemoryIndex()
    n = len(gold)
    chunk_hits = 0
    slug_hits = 0
    for q in gold:
        hits = index.query(q["question"], top_k=top_k)
        gold_slug = q["source"]
        gold_chunk = q.get("chunk")
        retrieved = {(h["slug"], h["chunk_idx"]) for h in hits}
        retrieved_slugs = {h["slug"] for h in hits}
        if gold_slug in retrieved_slugs:
            slug_hits += 1
        if (gold_slug, gold_chunk) in retrieved:
            chunk_hits += 1
    return {
        "qa_set": Path(gold_path).name,
        "n": n,
        "top_k": top_k,
        "rerank": 0,
        "recall_at_k": round(chunk_hits / n, 4),
        "slug_recall_at_k": round(slug_hits / n, 4),
        "faithfulness": None,
        "mean_correctness": None,
        "refusal_rate": None,
    }


def scout_ingest(
    papers_json: str,
    articles_dir: Optional[str] = None,
) -> dict[str, Any]:
    """Fold a ``frontier-scout`` papers.json into the index as scout memory (M10
    ``scout_ingest``).

    Each scouted paper persists as ``"evaluated, <feasibility verdict>"`` (the
    lowest trust tier, M10-3) so the system stops re-scouting what it already
    judged — the external twin of M8-4's re-scouting-amnesia cure. Thin wrapper
    over :func:`reindex_memory` with ``source_set='scout'`` so it shares the one
    ingest path + writes a ``reindex_runs`` row.
    """
    return reindex_memory(
        source_set="scout", papers_json=papers_json, articles_dir=articles_dir
    )


# --- Phase 3 (rlvr-loop-v1) — the closed-loop RLVR engine ------------------

#: The vertical-bench scorers `run_rl_loop` can use as its verifier-reward.
#: Mirrors the deterministic `fieldkit.eval` scorers + the patent-strategist set
#: (`RewardAdapter` wraps any of them); judge-backed scorers need a warm NIM and
#: are passed by the caller via the run config, not this string map.
_RL_SCORERS = (
    "mcq_letter", "numeric_match", "irac_structure",
    "prior_art_relevance", "exact_match", "contains",
)


def run_rl_loop(
    base: str,
    vertical: str = "patent-strategist",
    *,
    bench_path: Optional[str] = None,
    scorer: str = "mcq_letter",
    lane: Optional[str] = None,
    bench_id: Optional[str] = None,
    config: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Run one closed-loop RLVR run (Phase 3 ``rl_run`` body — RV-1/2/4).

    Assembles the `fieldkit.rl.RLLoop` over a vertical bench: the verifier
    (`fieldkit.eval` scorer) becomes the reward via `fieldkit.reward.
    RewardAdapter`, and the GPU seams (pinned-vLLM rollout, REINFORCE-with-KL
    LoRA step + kill-and-restart, the held-out gate) come from `fieldkit.rl.
    gpu_seams`. Returns the run's aggregate digest (`RLLoop.summary` — the
    held-out-selected checkpoint, the held-out vs pool trajectories) plus the
    rendered ``rl_run`` lineage card; the Arena dispatcher persists the digest
    to ``jobs.result_json``.

    **Real GPU work, overnight-only** — the 8.5 h GRPO loop runs under the M11
    single-lane cron, never a synchronous click (RV-6). `gpu_seams` raises until
    the pinned-vLLM backend is vendored into `fieldkit[rl]`
    (`[[project_verl_atgpo_vllm_gap]]`); callers driving the loop today inject
    their own seams into `RLLoop` directly. The orchestration — split, reward,
    group-relative advantage, held-out-only checkpoint selection, lineage card —
    is the part this build ships and tests.
    """
    from fieldkit.eval import (
        VerticalBench, contains, exact_match, irac_structure,
        mcq_letter, numeric_match, prior_art_relevance,
    )
    from fieldkit.reward import RewardAdapter
    from fieldkit.rl import GRPOConfig, RLLoop, gpu_seams

    if scorer not in _RL_SCORERS:
        raise ValueError(f"unknown scorer {scorer!r}; choose one of {_RL_SCORERS}")
    if not bench_path:
        raise ValueError(
            "run_rl_loop needs `bench_path` — the bench gold JSONL the corpus "
            "and the held-out split are carved from (≥100 rows, RV-10). The "
            "Arena dispatcher resolves it from the bench registry."
        )
    path = Path(bench_path).expanduser()
    if not path.exists():
        raise FileNotFoundError(f"Bench JSONL not found: {bench_path}")

    scorer_fn = {
        "mcq_letter": mcq_letter, "numeric_match": numeric_match,
        "irac_structure": irac_structure, "prior_art_relevance": prior_art_relevance,
        "exact_match": exact_match, "contains": contains,
    }[scorer]

    cfg_kwargs = dict(config or {})
    pass_threshold = cfg_kwargs.pop("pass_threshold", 1.0)
    cfg_kwargs.setdefault("vllm_pin", os.environ.get("ARENA_RL_VLLM_PIN", ""))
    cfg = GRPOConfig(base=base, **cfg_kwargs)
    reward = RewardAdapter(scorer_fn, pass_threshold=pass_threshold)
    bench = VerticalBench.from_jsonl(path, name=vertical, scorer=scorer_fn)

    sampler, trainer, heldout_eval = gpu_seams(cfg, reward=reward)
    loop = RLLoop(
        cfg, reward, bench,
        sampler=sampler, trainer=trainer, heldout_eval=heldout_eval, domain=vertical,
    )
    snap = loop.run()
    summary = loop.summary()
    summary["lineage_card"] = snap.rendered_prompt
    summary["lane"] = lane
    summary["bench_id"] = bench_id
    return summary


def requant_checkpoint(
    manifest_slug: str,
    checkpoint: str,
    variants: Optional[list[str]] = None,
    dry_run: bool = True,
) -> dict[str, Any]:
    """Re-quantize a held-out-winning RLVR checkpoint to GGUF (``requant`` body).

    The fast-follow after an `rl_run` lifts the held-out bench: re-quantize the
    merged LoRA checkpoint so the lifted model ships as the same GGUF variant
    ladder the original quant did. Thin wrapper over :func:`quantize_gguf`
    (dry-run by default, same envelope guard), keyed by the manifest it
    republishes. RV-9 keeps the *publish* deferred — this produces the variants;
    promotion to a `kind: quant` manifest is a separate, human-gated step.
    """
    report = quantize_gguf(
        model_path=checkpoint,
        outdir=os.path.expanduser(f"~/.fieldkit/arena/requant/{manifest_slug}"),
        variants=variants,
        dry_run=dry_run,
    )
    return {"manifest_slug": manifest_slug, "checkpoint": checkpoint, **report}


# --- Server assembly -------------------------------------------------------

_READ_ONLY = {"readOnlyHint": True, "idempotentHint": True, "openWorldHint": False}
_WRITES = {"readOnlyHint": False, "openWorldHint": False}


def build_mcp_server(name: str = MCP_SERVER_NAME) -> Any:
    """Build the `fieldkit` MCP server (a `FastMCP`) with the curated tool set.

    Lazy-imports the `mcp` SDK; raises `McpNotAvailable` if the
    `fieldkit[harness]` extra is missing. The returned server is not run — the
    caller does `.run()` (stdio) or hands it to a transport.
    """
    FastMCP = _require_fastmcp()
    server = FastMCP(name)

    server.tool(
        description=(
            "Practical inference envelope for a model-size key (exact keys like "
            "'8B params bf16', '70B params fp8', '70B params int4', '405B+ "
            "params') on the DGX Spark's 128 GB unified memory. Returns a "
            "plain-language verdict on what fits and how; on an unknown key, "
            "returns the list of available keys. Call before suggesting a model "
            "to run locally."
        ),
        annotations=_READ_ONLY,
    )(spark_inference_envelope)

    server.tool(
        description=(
            "Weight-only memory footprint (bytes + GB) for a parameter count "
            "(billions) at a dtype (fp16/bf16/fp8/int4/...). Use to reason about "
            "whether weights fit before loading; compare against the 128 GB "
            "unified-memory total."
        ),
        annotations=_READ_ONLY,
    )(spark_weight_footprint)

    server.tool(
        description=(
            "Measure single-stream throughput (tokens/sec) of a local GGUF on "
            "the Spark via llama-bench. Real GPU work — loads the model and runs "
            "a prompt+generation sweep. Pass an absolute .gguf path. Returns "
            "tok/s for prompt and generation."
        ),
        annotations=_WRITES,
    )(measure_gguf_throughput)

    server.tool(
        description=(
            "Measure perplexity of a local GGUF over a text corpus via "
            "llama-perplexity (lower is better). Real GPU work. Pass an absolute "
            ".gguf path and a corpus text file."
        ),
        annotations=_WRITES,
    )(measure_gguf_perplexity)

    server.tool(
        description=(
            "Quantize F16/HF weights to GGUF variants on the Spark. dry_run=True "
            "(default) returns the plan without running llama-quantize; set "
            "dry_run=false to execute (guarded against oversized sources). "
            "Expensive — confirm intent before a non-dry run."
        ),
        annotations=_WRITES,
    )(quantize_gguf)

    server.tool(
        description=(
            "Stage and preview an Orionfold GGUF model card from measurements "
            "(perplexity + tok/s per variant). DRY-RUN ONLY — this tool can "
            "never execute a real HuggingFace push; it returns the repo id, the "
            "staged file list, and a card preview for review."
        ),
        annotations=_WRITES,
    )(publish_quant_dry_run)

    server.tool(
        description=(
            "Ask the ai-field-notes Second-Brain: a RAG query over Manav's blog "
            "corpus (NIM embed → pgvector → NIM Llama). Returns a grounded answer "
            "with cited source slugs. Read-only. Requires the RAG stack up."
        ),
        annotations=_READ_ONLY,
    )(ask_second_brain)

    server.tool(
        description=(
            "Re-run a vertical bench (patent/legal/finance/…) against a served "
            "lane and return per-question accuracy. Real GPU work — talks to the "
            "lane's OpenAI-compatible endpoint over a bench gold JSONL. Backs the "
            "Arena `eval_rerun` job (leaderboard-regression → confirm)."
        ),
        annotations=_WRITES,
    )(run_vertical_eval)

    server.tool(
        description=(
            "Measure single-stream throughput (tok/s) across a manifest's GGUF "
            "variants via llama-bench. Real GPU work, one variant at a time "
            "inside the 128 GB envelope. Pass {variant: absolute .gguf path}."
        ),
        annotations=_WRITES,
    )(measure_variants)

    server.tool(
        description=(
            "Rebuild the Second-Brain index multi-source (articles/lineage/scout) "
            "with a provenance card on every chunk. Talks to pgvector + the "
            "embedder NIM. Backs the Arena `reindex` job (M10). source_set ∈ "
            "{articles, scout, lineage, all}."
        ),
        annotations=_WRITES,
    )(reindex_memory)

    server.tool(
        description=(
            "Score the live Second-Brain index against the in-repo qa-eval gold "
            "set: chunk-recall@k + slug-recall@k (cosine-only, the GB10 measured "
            "baseline). Backs the Arena `rag_eval` job + its promotion gate (M10)."
        ),
        annotations=_WRITES,
    )(rag_eval_index)

    server.tool(
        description=(
            "Fold a frontier-scout papers.json (feasibility verdicts) into the "
            "index as scout-class memory, so the system stops re-scouting what it "
            "already judged. Backs the Arena `scout_ingest` job (M10)."
        ),
        annotations=_WRITES,
    )(scout_ingest)

    server.tool(
        description=(
            "Run one closed-loop RLVR run (Phase 3): a vertical-bench verifier is "
            "the reward, GRPO/REINFORCE-with-KL takes LoRA steps over a pinned "
            "vLLM, and a frozen held-out split gates checkpoint selection (never "
            "the training pool). Real GPU work, overnight-only — backs the Arena "
            "`rl_run` job. Returns the held-out-selected checkpoint + lineage card."
        ),
        annotations=_WRITES,
    )(run_rl_loop)

    server.tool(
        description=(
            "Re-quantize a held-out-winning RLVR checkpoint to the GGUF variant "
            "ladder (dry-run by default, same envelope guard as quantize_gguf). "
            "The fast-follow after an `rl_run` lift. Backs the Arena `requant` "
            "job; publishing the lifted model stays a separate human-gated step."
        ),
        annotations=_WRITES,
    )(requant_checkpoint)

    return server


def run_mcp_server(name: str = MCP_SERVER_NAME) -> None:
    """Build the server and serve it over stdio (the `python -m` entrypoint)."""
    build_mcp_server(name).run()


if __name__ == "__main__":
    run_mcp_server()
