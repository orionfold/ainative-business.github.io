---
module: cli
title: fieldkit (CLI)
summary: A thin Typer wrapper over the modules. Quick checks and smoke benchmarks without writing Python.
order: 6
---

## What it is

A thin command-line entry point exposed at `fieldkit` after `pip install`. Every subcommand is a ~20-line wrapper over the existing module APIs — for real workloads, import `fieldkit.{capabilities,nim,rag,eval,training}` directly instead.

## Commands

### `fieldkit version`

Print the installed package version.

```bash
$ fieldkit version
0.2.0
```

### `fieldkit envelope <size>`

Look up the practical inference envelope rule for a model size from `spark-capabilities.json`.

```bash
$ fieldkit envelope "70B params fp8"
~70 GB weights; leaves ~50 GB for KV + activations + system; tight but possible

$ fieldkit envelope "8B params bf16"
fits with room — ~16 GB weights + KV; 24.8 tok/s measured on NIM
```

Unknown size → exit code 2 with the list of known keys.

### `fieldkit feasibility <model_id>`

Quick weights + KV-cache feasibility view for a known shape. Built-in catalog: `llama-3.1-8b`, `llama-3.1-70b`, `100b-bf16`.

```bash
$ fieldkit feasibility llama-3.1-70b --ctx 4096 --batch 32 --dtype fp8
model:           llama-3.1-70b
hardware:        NVIDIA DGX Spark (GB10 Grace Blackwell) — 128 GB unified
weights (fp8):       70.0 GB
KV cache (fp8):      21.5 GB  (ctx=4096, batch=32)
weights + KV:       91.5 GB
envelope rule:   ~70 GB weights; leaves ~50 GB for KV + activations + system; tight but possible
```

Flags:

| Flag | Default | Notes |
|---|---|---|
| `--ctx` | 4096 | Context length in tokens |
| `--batch` | 1 | Concurrency / batch size |
| `--dtype` | fp16 | `fp32`, `bf16`, `fp16`, `fp8`, `int8`, `int4`, `nf4` |

### `fieldkit bench rag`

Smoke-bench `Pipeline.ask` against a 3-doc in-memory corpus. Requires the chat NIM, embed NIM, and pgvector to be reachable.

```bash
$ fieldkit bench rag --table fieldkit_cli_bench_rag --out /tmp/bench.json
waiting for embed NIM at http://localhost:8001/v1 ...
waiting for chat NIM at http://localhost:8000/v1 ...
ingested 3 chunks into fieldkit_cli_bench_rag

| call | latency_ms | success |
|---|---|---|
| ... |
```

Env vars: `EMBED_BASE_URL`, `NIM_BASE_URL`, `NIM_MODEL`, `PGVECTOR_DSN`. Each has a matching `--flag` form.
