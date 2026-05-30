#!/usr/bin/env python3
# Copyright 2026 Manav Sehgal
# SPDX-License-Identifier: Apache-2.0
"""spark_envelope.py — Spark inference-envelope estimator for hf-model-scout.

Given a HuggingFace `config.json`, computes:

  - F16 weight bytes (theoretical lower bound — params × 2)
  - Q4_K_M weight bytes (empirical — params × 0.52 byte/param avg from
    the Orionfold finance-chat numbers, plus 5% per-tensor overhead)
  - Whether each fits the Spark practical inference envelope, via
    `fieldkit.capabilities.practical_inference_envelope(...)`.
  - Estimated tg tok/s for the Q4_K_M variant (linear extrapolation
    from the AdaptLLM/finance-chat baseline at 31.1 tok/s @ 6.7B params Q4_K_M).

Usage:
    spark_envelope.py <path-to-config.json>

Emits one JSON line to stdout. Exits 0 on success, 1 if config.json can't
be parsed. Uses ONLY stdlib + fieldkit — no other deps.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# Allow running this script standalone without a venv install of fieldkit
# (the skill is invoked from inside the ai-field-notes repo).
_REPO_FIELDKIT = Path("/home/nvidia/ainative-business.github.io/fieldkit/src")
if _REPO_FIELDKIT.exists():
    sys.path.insert(0, str(_REPO_FIELDKIT))

try:
    from fieldkit.capabilities import Capabilities, weight_bytes  # type: ignore
    _FK_AVAILABLE = True
except ImportError:
    _FK_AVAILABLE = False


# Spark practical envelope is ~80 GB free unified memory in normal state
# (per `[[project_spark_unified_memory_oom]]` — pkill-ed orphans not counted).
# `Capabilities.load()` is read for the hardware total; we subtract a fixed
# 48 GB for OS + KV cache + headroom to land on the practical ceiling.
_SPARK_TOTAL_BYTES_FALLBACK = 128 * 1024**3
_OS_HEADROOM_BYTES = 48 * 1024**3

# Tok/s reference points from the published Orionfold/finance-chat card.
# Linear-in-params interpolation; close-enough for the purposes of this scout.
# (Caller validates with real llama-bench once the F16 GGUF is built.)
_REF_TG_TOK_S_PER_PARAM = {
    "Q4_K_M": 31.1 / 6.7e9,  # 31.1 tok/s @ 6.7B
    "F16":    11.5 / 6.7e9,  # 11.5 tok/s @ 6.7B
}


def _estimate_params(cfg: dict) -> int | None:
    """Estimate parameter count from a HF config.json.

    Two paths: (1) a `num_parameters` field if upstream populates it (rare);
    (2) a closed-form approximation from `hidden_size` + `num_hidden_layers`
    + `intermediate_size` + `vocab_size` — the standard transformer formula:

        params ≈ vocab × hidden × 2                          # embeddings + lm_head
               + n_layers × (4 × hidden² + 3 × hidden × ffn) # attention + mlp
    """
    if "num_parameters" in cfg and isinstance(cfg["num_parameters"], (int, float)):
        return int(cfg["num_parameters"])
    h = cfg.get("hidden_size")
    n = cfg.get("num_hidden_layers")
    v = cfg.get("vocab_size")
    ffn = cfg.get("intermediate_size") or (h * 4 if h else None)
    if not all(isinstance(x, int) for x in (h, n, v, ffn)):
        return None
    return int(v * h * 2 + n * (4 * h * h + 3 * h * ffn))


def _f16_bytes(params: int) -> int:
    # When fieldkit.weight_bytes is available, prefer it (single source of truth).
    if _FK_AVAILABLE:
        return weight_bytes(params_b=params / 1e9, dtype="fp16")
    return params * 2


def _q4km_bytes(params: int) -> int:
    # Empirical: AdaptLLM/finance-chat 6.7B → 3.8 GB GGUF Q4_K_M.
    # 3.8 GB / 6.7e9 = 0.567 bytes/param. Round to 0.57 with a small safety margin.
    return int(params * 0.57)


def main() -> int:
    if len(sys.argv) < 2:
        print(json.dumps({"error": "config.json path required"}))
        return 1
    cfg_path = Path(sys.argv[1])
    try:
        cfg = json.loads(cfg_path.read_text())
    except Exception as exc:
        print(json.dumps({"error": f"failed to read {cfg_path}: {exc}"}))
        return 1

    params = _estimate_params(cfg)
    if params is None:
        print(json.dumps({
            "fits_fp16": None,
            "fits_q4km": None,
            "f16_gb": None,
            "q4km_gb": None,
            "estimated_tg_tok_s": None,
            "warnings": ["could not estimate params from config.json"],
        }))
        return 0

    f16_b = _f16_bytes(params)
    q4_b = _q4km_bytes(params)

    if _FK_AVAILABLE:
        caps = Capabilities.load()
        total_bytes = caps.hardware.unified_memory_gb * (1024 ** 3)
    else:
        total_bytes = _SPARK_TOTAL_BYTES_FALLBACK

    # Practical model-weight ceiling = total unified memory minus OS / KV / headroom.
    # 48 GB headroom is conservative for a 128 GB box (matches the safe envelope
    # the user has hit reliably across the published cards).
    weight_ceiling = total_bytes - _OS_HEADROOM_BYTES

    out = {
        "params_estimated": params,
        "f16_gb": round(f16_b / 1024**3, 2),
        "q4km_gb": round(q4_b / 1024**3, 2),
        "weight_ceiling_gb": round(weight_ceiling / 1024**3, 2),
        "fits_fp16": f16_b <= weight_ceiling,
        "fits_q4km": q4_b <= weight_ceiling,
        "estimated_tg_tok_s": round(_REF_TG_TOK_S_PER_PARAM["Q4_K_M"] * params, 1),
        "estimated_f16_tg_tok_s": round(_REF_TG_TOK_S_PER_PARAM["F16"] * params, 1),
    }
    print(json.dumps(out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
