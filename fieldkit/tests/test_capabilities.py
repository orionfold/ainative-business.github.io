# Copyright 2026 Manav Sehgal
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for fieldkit.capabilities.

Numbers are pinned to the canonical examples in:
- articles/kv-cache-arithmetic-at-inference (Llama 3.1 70B serving math)
- articles/gpu-sizing-math-for-fine-tuning (100B Nemotron weight math)

Both articles are rounding to GB-decimal (10^9 bytes); the API returns
exact bytes. We allow ±2% tolerance on cross-checks against the article
prose to absorb rounding, but exact-byte arithmetic is also exercised.
"""

from __future__ import annotations

import pytest

from fieldkit.capabilities import (
    Capabilities,
    UnknownDtype,
    UnknownEnvelope,
    kv_cache_bytes,
    practical_inference_envelope,
    weight_bytes,
)


GB = 10**9


# Llama 3.1 70B architecture constants used in the article walkthrough.
LLAMA_70B_KV_HIDDEN = 8 * 128  # 8 KV heads × 128 head_dim (GQA)
LLAMA_70B_N_LAYERS = 80


class TestCapabilitiesLoad:
    def test_load_returns_singleton(self) -> None:
        a = Capabilities.load()
        b = Capabilities.load()
        assert a is b

    def test_refresh_rebuilds(self) -> None:
        a = Capabilities.load()
        b = Capabilities.load(refresh=True)
        assert a is not b
        assert a.version == b.version

    def test_hardware_shape(self) -> None:
        caps = Capabilities.load()
        assert caps.hardware.unified_memory_gb == 128
        assert "GB10" in caps.hardware.name
        assert "bf16" in caps.hardware.supported_dtypes

    def test_stack_includes_core_services(self) -> None:
        caps = Capabilities.load()
        for key in ("nim", "nemo", "tensorrt_llm", "triton", "pgvector"):
            assert key in caps.stack, f"missing stack entry: {key}"

    def test_envelope_signals_non_empty(self) -> None:
        caps = Capabilities.load()
        assert len(caps.in_envelope_signals) >= 5
        assert len(caps.out_of_envelope_signals) >= 3


class TestKVCacheBytes:
    """Pin to article numbers: KV bytes = 2 × n_layers × kv_hidden × ctx × batch × bpd."""

    def test_70b_32users_16k_fp16(self) -> None:
        # Article cites ~168 GB for this cell; exact arithmetic gives 171.8 GB.
        b = kv_cache_bytes(
            hidden=LLAMA_70B_KV_HIDDEN,
            n_layers=LLAMA_70B_N_LAYERS,
            ctx=16384,
            batch=32,
            dtype="fp16",
        )
        # 2 × 80 × 1024 × 16384 × 32 × 2 = 171,798,691,840
        assert b == 171_798_691_840
        assert 168 * GB <= b <= 175 * GB  # within rounding of article cell

    def test_fp8_halves_fp16(self) -> None:
        fp16 = kv_cache_bytes(
            hidden=LLAMA_70B_KV_HIDDEN,
            n_layers=LLAMA_70B_N_LAYERS,
            ctx=16384,
            batch=32,
            dtype="fp16",
        )
        fp8 = kv_cache_bytes(
            hidden=LLAMA_70B_KV_HIDDEN,
            n_layers=LLAMA_70B_N_LAYERS,
            ctx=16384,
            batch=32,
            dtype="fp8",
        )
        assert fp8 * 2 == fp16

    def test_70b_1user_4k_fp16(self) -> None:
        # Article cites ~1.3 GB for the trivial cell.
        b = kv_cache_bytes(
            hidden=LLAMA_70B_KV_HIDDEN,
            n_layers=LLAMA_70B_N_LAYERS,
            ctx=4096,
            batch=1,
            dtype="fp16",
        )
        assert 1.2 * GB <= b <= 1.5 * GB

    def test_70b_128users_8k_fp16(self) -> None:
        # Article cites ~336 GB.
        b = kv_cache_bytes(
            hidden=LLAMA_70B_KV_HIDDEN,
            n_layers=LLAMA_70B_N_LAYERS,
            ctx=8192,
            batch=128,
            dtype="fp16",
        )
        assert 330 * GB <= b <= 350 * GB

    def test_70b_32users_128k_fp16_long_context(self) -> None:
        # Article cites ~1.3 TB.
        b = kv_cache_bytes(
            hidden=LLAMA_70B_KV_HIDDEN,
            n_layers=LLAMA_70B_N_LAYERS,
            ctx=131072,
            batch=32,
            dtype="fp16",
        )
        assert 1300 * GB <= b <= 1400 * GB

    @pytest.mark.parametrize(
        "kw",
        [
            {"hidden": 0, "n_layers": 80, "ctx": 4096, "batch": 1, "dtype": "fp16"},
            {"hidden": 1024, "n_layers": -1, "ctx": 4096, "batch": 1, "dtype": "fp16"},
            {"hidden": 1024, "n_layers": 80, "ctx": 0, "batch": 1, "dtype": "fp16"},
            {"hidden": 1024, "n_layers": 80, "ctx": 4096, "batch": 0, "dtype": "fp16"},
        ],
    )
    def test_rejects_non_positive_dims(self, kw: dict) -> None:
        with pytest.raises(ValueError):
            kv_cache_bytes(**kw)

    def test_rejects_unknown_dtype(self) -> None:
        with pytest.raises(UnknownDtype):
            kv_cache_bytes(hidden=1024, n_layers=80, ctx=4096, batch=1, dtype="fp7")


class TestWeightBytes:
    """Pin to article numbers from gpu-sizing-math-for-fine-tuning."""

    def test_100b_bf16_is_200gb(self) -> None:
        assert weight_bytes(params_b=100, dtype="bf16") == 200 * GB

    def test_100b_fp8_is_100gb(self) -> None:
        assert weight_bytes(params_b=100, dtype="fp8") == 100 * GB

    def test_100b_nf4_is_50gb(self) -> None:
        # Article: "Weights drop from 2 bytes/param to ~0.5 ... 200 GB to ~50 GB"
        assert weight_bytes(params_b=100, dtype="nf4") == 50 * GB

    def test_8b_bf16_is_16gb(self) -> None:
        # JSON envelope says "8B params bf16 ... ~16 GB weights".
        assert weight_bytes(params_b=8, dtype="bf16") == 16 * GB

    def test_70b_bf16_is_140gb(self) -> None:
        # Article: "Weights add another ~140 GB at BF16".
        assert weight_bytes(params_b=70, dtype="bf16") == 140 * GB

    def test_70b_fp8_is_70gb(self) -> None:
        # Article: "or ~70 GB at FP8".
        assert weight_bytes(params_b=70, dtype="fp8") == 70 * GB

    def test_rejects_non_positive_params(self) -> None:
        with pytest.raises(ValueError):
            weight_bytes(params_b=0, dtype="bf16")

    def test_rejects_unknown_dtype(self) -> None:
        with pytest.raises(UnknownDtype):
            weight_bytes(params_b=8, dtype="banana")


class TestPracticalInferenceEnvelope:
    def test_lookup_70b_fp8(self) -> None:
        s = practical_inference_envelope("70B params fp8")
        assert "70 GB weights" in s

    def test_case_insensitive(self) -> None:
        s = practical_inference_envelope("  70B PARAMS FP8  ")
        assert "70 GB weights" in s

    def test_lookup_405b(self) -> None:
        s = practical_inference_envelope("405B+ params")
        assert "out of envelope" in s.lower()

    def test_unknown_raises(self) -> None:
        with pytest.raises(UnknownEnvelope):
            practical_inference_envelope("17B params bf16")
