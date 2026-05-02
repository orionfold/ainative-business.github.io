---
module: capabilities
title: fieldkit.capabilities
summary: Typed Python facade over the project's Spark capabilities map. Canonical KV-cache and weight arithmetic.
order: 1
---

## What it is

A read-only typed view of `spark-capabilities.json` — the project's grounding floor for hardware envelope claims (KV-cache math, weight memory, in/out-envelope signals, NIM/NeMo/TRT-LLM stack notes). The same JSON the `frontier-scout` skill uses to decide whether a paper fits on the Spark.

The package keeps its own copy of the JSON in sync with the source-of-truth at `scripts/lib/spark-capabilities.json` via a pre-commit drift check.

## Public API

```python
from fieldkit.capabilities import (
    Capabilities,
    kv_cache_bytes,
    weight_bytes,
    practical_inference_envelope,
    DTYPE_BYTES,
    UnknownDtype,
    UnknownEnvelope,
)
```

### `Capabilities.load(refresh=False) -> Capabilities`

Cached singleton typed view. Pass `refresh=True` to force a re-read from disk.

```python
caps = Capabilities.load()
caps.hardware.unified_memory_gb        # 128
caps.hardware.compute_arch             # "GB10 Grace Blackwell"
caps.memory_budget_rules_of_thumb.practical_inference_envelope
caps.stack["nim"].verified_in_articles
caps.in_envelope_signals               # tuple[str, ...]
caps.out_of_envelope_signals
caps.stage_routing_hints               # {"inference": "...", ...}
caps.raw                               # full JSON dict for ad-hoc inspection
```

### `kv_cache_bytes(*, hidden, n_layers, ctx, batch, dtype) -> int`

Canonical KV-cache equation from `kv-cache-arithmetic-at-inference`:

```
KV bytes = 2 × n_layers × kv_hidden × ctx × batch × bytes_per_dtype
```

`hidden` here is the **KV hidden size** (`n_kv_heads × head_dim`), not the model's full hidden dim — important for GQA models like Llama 3.1 70B (8 KV heads × 128 head_dim = 1024).

```python
kv_cache_bytes(hidden=1024, n_layers=80, ctx=16384, batch=32, dtype="fp16")
# 171_798_691_840  (≈ 171.8 GB)
```

### `weight_bytes(*, params_b, dtype) -> int`

Weight memory in bytes for `params_b` billion parameters at `dtype`.

```python
weight_bytes(params_b=70, dtype="bf16")   # 140_000_000_000  (140 GB)
weight_bytes(params_b=100, dtype="fp8")   # 100_000_000_000  (100 GB)
weight_bytes(params_b=100, dtype="nf4")   #  50_000_000_000  ( 50 GB)
```

### `practical_inference_envelope(model_size: str) -> str`

Look up the rule-of-thumb envelope string for a model size.

```python
practical_inference_envelope("8B params bf16")
# "fits with room — ~16 GB weights + KV; 24.8 tok/s measured on NIM"

practical_inference_envelope("70B params fp8")
# "~70 GB weights; leaves ~50 GB for KV + activations + system; tight but possible"
```

Raises `UnknownEnvelope` if no rule matches.

### `DTYPE_BYTES`

Bytes-per-parameter table:

| dtype | bytes |
|---|---|
| `fp32` | 4 |
| `bf16` / `fp16` | 2 |
| `fp8` / `int8` | 1 |
| `int4` / `nf4` | 0.5 |

Unknown dtype → `UnknownDtype`.

## Sample

[`samples/feasibility-math.py`](https://github.com/manavsehgal/ai-field-notes/blob/main/fieldkit/samples/feasibility-math.py) reproduces the kv-cache article's serving table, the 100B Nemotron weight table, and the envelope lookup, all via the public API.
