# Copyright 2026 Manav Sehgal
# SPDX-License-Identifier: Apache-2.0
"""`fieldkit` command-line entry point.

Wires Typer subcommands to the existing module APIs:

    fieldkit version           — print the installed version
    fieldkit envelope <size>   — practical inference envelope rule for a model size
    fieldkit feasibility <id>  — quick feasibility view from spark-capabilities.json
    fieldkit bench rag         — drive Pipeline.ask through Bench against a tiny
                                 in-memory corpus, print the latency report

The CLI is intentionally thin — every command is a ~20-line wrapper over the
public Python API. For real workloads, import `fieldkit.{capabilities,nim,rag,eval}`
directly instead.
"""

from __future__ import annotations

import json
import os
import sys
from typing import Optional

import typer

from fieldkit import __version__
from fieldkit.capabilities import (
    Capabilities,
    UnknownDtype,
    UnknownEnvelope,
    kv_cache_bytes,
    practical_inference_envelope,
    weight_bytes,
)

app = typer.Typer(
    name="fieldkit",
    help="Verified-on-Spark patterns from the ai-field-notes blog.",
    no_args_is_help=True,
    add_completion=False,
)

bench_app = typer.Typer(
    name="bench",
    help="Run small benchmarks against Spark services.",
    no_args_is_help=True,
)
app.add_typer(bench_app, name="bench")

# Cockpit subcommands (Spark Arena — spark-arena-v1 §3.4). Importing
# `fieldkit.arena.cli` is stdlib+Typer only — heavy deps (FastAPI, aiosqlite,
# sse-starlette) ship via the `arena` extra and stay lazy inside individual
# command bodies (M3 onward). Until M3 lands, every command is a stub that
# raises `typer.Exit` with a milestone marker so the surface is discoverable
# from day one (`fieldkit arena --help` works) without doing anything yet.
from fieldkit.arena.cli import app as arena_app  # noqa: E402

app.add_typer(arena_app, name="arena")


@app.command("version")
def version_cmd() -> None:
    """Print the installed fieldkit version."""
    typer.echo(__version__)


@app.command("envelope")
def envelope_cmd(
    size: str = typer.Argument(
        ...,
        help='Model size key — e.g. "8B params bf16", "70B params fp8", "405B+ params".',
    ),
) -> None:
    """Look up a practical inference envelope rule from spark-capabilities.json."""
    try:
        rule = practical_inference_envelope(size)
    except UnknownEnvelope as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(code=2) from exc
    typer.echo(rule)


@app.command("feasibility")
def feasibility_cmd(
    model_id: str = typer.Argument(
        ...,
        help='Model id — e.g. "llama-3.1-8b", "llama-3.1-70b", "100B-bf16".',
    ),
    ctx: int = typer.Option(4096, "--ctx", help="Context length in tokens."),
    batch: int = typer.Option(1, "--batch", help="Concurrency / batch size."),
    dtype: str = typer.Option(
        "fp16",
        "--dtype",
        help="Weights/KV dtype — fp32, bf16, fp16, fp8, int8, int4, nf4.",
    ),
) -> None:
    """Quick weights + KV-cache feasibility view for a known shape.

    Recognises a small built-in catalog of shapes (Llama 3.1 8B/70B, 100B
    Nemotron-class). Prints weight bytes, KV bytes, and the practical
    inference envelope string.
    """
    shapes: dict[str, dict[str, object]] = {
        "llama-3.1-8b": {
            "params_b": 8.0,
            "kv_hidden": 8 * 128,
            "n_layers": 32,
            "envelope_key": "8B params bf16",
        },
        "llama-3.1-70b": {
            "params_b": 70.0,
            "kv_hidden": 8 * 128,
            "n_layers": 80,
            "envelope_key": "70B params fp8",
        },
        "100b-bf16": {
            "params_b": 100.0,
            "kv_hidden": 8 * 128,
            "n_layers": 96,
            "envelope_key": "70B params bf16",
        },
    }
    key = model_id.strip().lower()
    if key not in shapes:
        typer.echo(
            f"error: unknown model id {model_id!r}; known: {sorted(shapes)}",
            err=True,
        )
        raise typer.Exit(code=2)
    shape = shapes[key]
    try:
        wb = weight_bytes(params_b=float(shape["params_b"]), dtype=dtype)
        kvb = kv_cache_bytes(
            hidden=int(shape["kv_hidden"]),  # type: ignore[arg-type]
            n_layers=int(shape["n_layers"]),  # type: ignore[arg-type]
            ctx=ctx,
            batch=batch,
            dtype=dtype,
        )
    except UnknownDtype as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(code=2) from exc

    caps = Capabilities.load()
    gb = lambda b: b / 10**9  # noqa: E731

    typer.echo(f"model:           {model_id}")
    typer.echo(f"hardware:        {caps.hardware.name} — {caps.hardware.unified_memory_gb} GB unified")
    typer.echo(f"weights ({dtype}):    {gb(wb):>7.1f} GB")
    typer.echo(f"KV cache ({dtype}):   {gb(kvb):>7.1f} GB  (ctx={ctx}, batch={batch})")
    typer.echo(f"weights + KV:    {gb(wb + kvb):>7.1f} GB")
    try:
        rule = practical_inference_envelope(str(shape["envelope_key"]))
        typer.echo(f"envelope rule:   {rule}")
    except UnknownEnvelope:
        pass


@bench_app.command("rag")
def bench_rag_cmd(
    embed_url: str = typer.Option(
        os.environ.get("EMBED_BASE_URL", "http://localhost:8001/v1"),
        "--embed-url",
        envvar="EMBED_BASE_URL",
    ),
    nim_url: str = typer.Option(
        os.environ.get("NIM_BASE_URL", "http://localhost:8000/v1"),
        "--nim-url",
        envvar="NIM_BASE_URL",
    ),
    nim_model: str = typer.Option(
        os.environ.get("NIM_MODEL", "meta/llama-3.1-8b-instruct"),
        "--nim-model",
        envvar="NIM_MODEL",
    ),
    pgvector_dsn: str = typer.Option(
        os.environ.get(
            "PGVECTOR_DSN", "postgresql://spark:spark@localhost:5432/vectors"
        ),
        "--pgvector-dsn",
        envvar="PGVECTOR_DSN",
    ),
    table: str = typer.Option(
        "fieldkit_cli_bench_rag", "--table", help="pgvector table to use."
    ),
    out: Optional[str] = typer.Option(
        None, "--out", help="Optional path to dump the bench JSON."
    ),
) -> None:
    """Smoke-bench Pipeline.ask against a 3-doc in-memory corpus.

    Requires the chat NIM, embed NIM, and pgvector to be reachable. Prints
    a markdown latency report and (optionally) writes the full bench JSON
    to disk.
    """
    # Imports are local so `fieldkit version` / `envelope` / `feasibility`
    # don't pay the httpx / psycopg import cost.
    from fieldkit.eval import Bench
    from fieldkit.nim import NIMClient, wait_for_warm
    from fieldkit.rag import Document, Pipeline

    typer.echo(f"waiting for embed NIM at {embed_url} ...")
    if not wait_for_warm(embed_url):
        typer.echo("error: embed NIM not warm in time", err=True)
        raise typer.Exit(code=1)
    typer.echo(f"waiting for chat NIM at {nim_url} ...")
    if not wait_for_warm(nim_url):
        typer.echo("error: chat NIM not warm in time", err=True)
        raise typer.Exit(code=1)

    docs = [
        Document(id=1, label="spark", text=(
            "The DGX Spark is a personal AI computer with a GB10 Grace-Blackwell "
            "superchip and 128 GB of unified memory shared between CPU and GPU."
        )),
        Document(id=2, label="spark", text=(
            "Spark's unified memory means a single large model competes with the "
            "OS and other processes for the same 128 GB pool."
        )),
        Document(id=3, label="distractor", text=(
            "The 2004 Athens Olympics hosted 11099 athletes across 28 sports."
        )),
    ]
    questions = [
        "How much unified memory does the DGX Spark have?",
        "What superchip powers the DGX Spark?",
        "What does Spark's unified memory mean for large models?",
        "Who won the 2020 US presidential election?",  # out-of-corpus
    ]

    with NIMClient(base_url=nim_url, model=nim_model) as gen, Pipeline(
        embed_url=embed_url,
        pgvector_dsn=pgvector_dsn,
        generator=gen,
        table=table,
        chunk_tokens=400,
    ) as pipe:
        pipe.ensure_schema()
        ingested = pipe.ingest(docs)
        typer.echo(f"ingested {ingested} chunks into {table}")

        bench = Bench(name="fieldkit-cli-bench-rag", metrics=[])
        with bench:
            bench.run(
                lambda q: pipe.ask(q, retrieve_k=3, rerank_k=2, max_tokens=96),
                questions,
            )
        typer.echo("")
        typer.echo(bench.report())

        if out:
            from pathlib import Path

            path = bench.dump(Path(out))
            typer.echo(f"\nwrote {path}")


def main() -> None:
    """Module-level entry point used by `python -m fieldkit`."""
    app()


if __name__ == "__main__":  # pragma: no cover
    sys.exit(app() or 0)
