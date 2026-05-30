# Copyright 2026 Manav Sehgal
# SPDX-License-Identifier: Apache-2.0
"""Typed Python facade over the project's Spark capabilities map.

The JSON at `data/spark-capabilities.json` is the project's grounding floor for
hardware envelope claims (KV-cache math, weight memory, in/out-envelope
signals, NIM/NeMo/TRT-LLM stack notes). This module exposes it as:

- `Capabilities.load()` — singleton typed view of the JSON
- `kv_cache_bytes(...)` — canonical KV cache equation from
  `kv-cache-arithmetic-at-inference`
- `weight_bytes(...)` — parameter-bytes lookup from the rules-of-thumb table
- `practical_inference_envelope(...)` — string lookup over the envelope table

Read-only by design. The source-of-truth JSON lives at
`scripts/lib/spark-capabilities.json` in the parent repo; the package's copy
is kept in sync by `fieldkit/scripts/sync_capabilities.py`.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from importlib.resources import files
from typing import Any, ClassVar

__all__ = [
    "Capabilities",
    "Hardware",
    "MemoryBudgetRulesOfThumb",
    "StackEntry",
    "kv_cache_bytes",
    "weight_bytes",
    "practical_inference_envelope",
    "DTYPE_BYTES",
    "UnknownDtype",
    "UnknownEnvelope",
]


DTYPE_BYTES: dict[str, float] = {
    "fp32": 4.0,
    "bf16": 2.0,
    "fp16": 2.0,
    "fp8": 1.0,
    "int8": 1.0,
    "int4": 0.5,
    "nf4": 0.5,
}


class UnknownDtype(KeyError):
    """Raised when a dtype string isn't in `DTYPE_BYTES`."""


class UnknownEnvelope(KeyError):
    """Raised when `practical_inference_envelope` can't find the requested model size."""


@dataclass(frozen=True, slots=True)
class Hardware:
    name: str
    unified_memory_gb: int
    memory_topology: str
    compute_arch: str
    supported_dtypes: tuple[str, ...]
    interconnect_to_other_gpus: str


@dataclass(frozen=True, slots=True)
class MemoryBudgetRulesOfThumb:
    param_bytes: dict[str, float]
    training_overhead_multiplier: str
    kv_cache_per_token_per_layer: str
    practical_inference_envelope: dict[str, str]
    practical_finetune_envelope: dict[str, str]


@dataclass(frozen=True, slots=True)
class StackEntry:
    id: str
    label: str
    purpose: str
    verified_in_articles: tuple[str, ...] = ()
    known_limits: tuple[str, ...] = ()
    fits_paper_shapes: tuple[str, ...] = ()
    supported_models_at_spark_scale: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class Capabilities:
    """Typed singleton view of `spark-capabilities.json`."""

    schema: str
    version: str
    hardware: Hardware
    memory_budget_rules_of_thumb: MemoryBudgetRulesOfThumb
    stack: dict[str, StackEntry]
    out_of_envelope_signals: tuple[str, ...]
    in_envelope_signals: tuple[str, ...]
    stage_routing_hints: dict[str, str]
    series_routing_hints: dict[str, str]
    raw: dict[str, Any] = field(repr=False)

    _instance: ClassVar["Capabilities | None"] = None

    @classmethod
    def load(cls, *, refresh: bool = False) -> "Capabilities":
        """Return the cached singleton; pass `refresh=True` to force a re-read."""
        if cls._instance is None or refresh:
            data = json.loads(_data_path().read_text(encoding="utf-8"))
            cls._instance = cls._from_raw(data)
        return cls._instance

    @classmethod
    def _from_raw(cls, raw: dict[str, Any]) -> "Capabilities":
        hw = raw["hardware"]
        rt = raw["memory_budget_rules_of_thumb"]
        stack = {
            key: StackEntry(
                id=entry.get("id", key),
                label=entry["label"],
                purpose=entry["purpose"],
                verified_in_articles=tuple(entry.get("verified_in_articles", [])),
                known_limits=tuple(entry.get("known_limits", [])),
                fits_paper_shapes=tuple(entry.get("fits_paper_shapes", [])),
                supported_models_at_spark_scale=tuple(
                    entry.get("supported_models_at_spark_scale", [])
                ),
            )
            for key, entry in raw["stack"].items()
        }
        return cls(
            schema=raw["$schema"],
            version=raw["version"],
            hardware=Hardware(
                name=hw["name"],
                unified_memory_gb=int(hw["unified_memory_gb"]),
                memory_topology=hw["memory_topology"],
                compute_arch=hw["compute_arch"],
                supported_dtypes=tuple(hw["supported_dtypes"]),
                interconnect_to_other_gpus=hw["interconnect_to_other_gpus"],
            ),
            memory_budget_rules_of_thumb=MemoryBudgetRulesOfThumb(
                param_bytes={k: float(v) for k, v in rt["param_bytes"].items()},
                training_overhead_multiplier=rt["training_overhead_multiplier"],
                kv_cache_per_token_per_layer=rt["kv_cache_per_token_per_layer"],
                practical_inference_envelope=dict(rt["practical_inference_envelope"]),
                practical_finetune_envelope=dict(rt["practical_finetune_envelope"]),
            ),
            stack=stack,
            out_of_envelope_signals=tuple(raw["out_of_envelope_signals"]),
            in_envelope_signals=tuple(raw["in_envelope_signals"]),
            stage_routing_hints=dict(raw["stage_routing_hints"]),
            series_routing_hints=dict(raw["series_routing_hints"]),
            raw=raw,
        )


def _data_path() -> Any:
    return files("fieldkit.capabilities.data").joinpath("spark-capabilities.json")


def _dtype_bytes(dtype: str) -> float:
    try:
        return DTYPE_BYTES[dtype.lower()]
    except KeyError as exc:
        raise UnknownDtype(
            f"unknown dtype {dtype!r}; known: {sorted(DTYPE_BYTES)}"
        ) from exc


def kv_cache_bytes(
    *,
    hidden: int,
    n_layers: int,
    ctx: int,
    batch: int,
    dtype: str,
) -> int:
    """KV cache memory in bytes for one decoder, given KV-hidden size and shape.

    Formula (from `kv-cache-arithmetic-at-inference`):

        KV bytes = 2 × n_layers × kv_hidden × ctx × batch × bytes_per_dtype

    The factor of 2 covers K and V (both stored). `hidden` here means the
    *KV hidden size* — `n_kv_heads × head_dim`. For a non-GQA model that
    equals the model's hidden size; for Llama 3.1 70B (8 KV heads × 128
    head_dim) it's 1024, regardless of the 8192-dim model hidden size.

    Returns bytes as an int (rounded down).
    """
    if min(hidden, n_layers, ctx, batch) <= 0:
        raise ValueError("hidden, n_layers, ctx, batch must all be positive")
    bpd = _dtype_bytes(dtype)
    return int(2 * n_layers * hidden * ctx * batch * bpd)


def weight_bytes(*, params_b: float, dtype: str) -> int:
    """Weight memory in bytes for `params_b` billion parameters at `dtype`.

    `params_b` is in billions; `weight_bytes(params_b=70, dtype="bf16")` is
    70e9 × 2 = 140 GB. Quantization dtypes (fp8, int8, nf4, int4) follow the
    rules-of-thumb table in `spark-capabilities.json`.
    """
    if params_b <= 0:
        raise ValueError("params_b must be positive (in billions)")
    bpp = _dtype_bytes(dtype)
    return int(params_b * 1e9 * bpp)


def practical_inference_envelope(model_size: str) -> str:
    """Look up the rule-of-thumb envelope string for `model_size`.

    Keys mirror the JSON's `practical_inference_envelope` dict — e.g.
    `"8B params bf16"`, `"70B params fp8"`, `"405B+ params"`. Lookup is
    case-insensitive and tolerates surrounding whitespace.

    Raises `UnknownEnvelope` if no rule matches.
    """
    table = Capabilities.load().memory_budget_rules_of_thumb.practical_inference_envelope
    needle = model_size.strip().lower()
    for key, val in table.items():
        if key.lower() == needle:
            return val
    raise UnknownEnvelope(
        f"no envelope rule for {model_size!r}; known keys: {list(table)}"
    )
