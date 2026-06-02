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


def ask_second_brain(
    query: str, retrieve_k: int = 5, rerank_k: int = 3, max_tokens: int = 256
) -> dict[str, Any]:
    """Ask the ai-field-notes Second-Brain RAG corpus (read-only).

    Builds a `rag.Pipeline` from env — `SECOND_BRAIN_PG_DSN`, `EMBED_URL`,
    `LLM_URL`, `LLM_MODEL` — so the same MCP tool serves both the Hermes harness
    and a Claude Code session (the `mcp-second-brain-in-claude-code` bridge).
    Requires the embedder + generator NIMs and pgvector to be up.
    """
    from fieldkit.nim import NIMClient
    from fieldkit.rag import Pipeline

    pg_dsn = os.environ.get(
        "SECOND_BRAIN_PG_DSN",
        "host=127.0.0.1 port=5432 dbname=vectors user=spark password=spark",
    )
    embed_url = os.environ.get("EMBED_URL", "http://127.0.0.1:8001/v1/embeddings")
    llm_url = os.environ.get("LLM_URL", "http://127.0.0.1:8000/v1")
    llm_model = os.environ.get("LLM_MODEL", "meta/llama-3.1-8b-instruct")
    rerank_url = os.environ.get("RERANK_URL") or None
    rerank_key = os.environ.get("NGC_API_KEY") or None

    generator = NIMClient(base_url=llm_url, model=llm_model)
    pipeline = Pipeline(
        embed_url=embed_url,
        pgvector_dsn=pg_dsn,
        generator=generator,
        rerank_url=rerank_url,
        rerank_api_key=rerank_key,
        table=os.environ.get("SECOND_BRAIN_TABLE", "blog_chunks"),
    )
    out = pipeline.ask(
        query, retrieve_k=retrieve_k, rerank_k=rerank_k, max_tokens=max_tokens
    )
    return {
        "query": query,
        "answer": out["answer"],
        "sources": [
            {"slug": getattr(c, "slug", None), "chunk_idx": getattr(c, "chunk_idx", None)}
            for c in out.get("chunks", [])
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
            "dispatcher fills this from the bench registry."
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

    return server


def run_mcp_server(name: str = MCP_SERVER_NAME) -> None:
    """Build the server and serve it over stdio (the `python -m` entrypoint)."""
    build_mcp_server(name).run()


if __name__ == "__main__":
    run_mcp_server()
