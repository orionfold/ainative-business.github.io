# Copyright 2026 Manav Sehgal
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for fieldkit.harness.mcp (the H4 fieldkit-as-MCP surface).

The tool *functions* are plain and testable without the `mcp` SDK; the capability
tools are pure (no GPU/network) and the quantize/publish dry-runs build plans /
stage cards without touching the GPU or HuggingFace. `build_mcp_server` needs the
`fieldkit[harness]` extra, so its tests `importorskip("mcp")`. The live
GPU-measure + RAG tools are exercised by the H4 evidence run, not here.
"""

from __future__ import annotations

import pytest

import fieldkit.harness as h
from fieldkit.harness import mcp as fkmcp


def test_mcp_exports_are_lazy_and_complete():
    # the six MCP names round-trip through the package's PEP 562 __getattr__
    for name in [
        "MCP_SERVER_NAME",
        "MCP_TOOL_SPECS",
        "MCPToolSpec",
        "McpNotAvailable",
        "build_mcp_server",
        "run_mcp_server",
    ]:
        assert name in h.__all__
        assert getattr(h, name) is getattr(fkmcp, name)


def test_unknown_harness_attr_still_raises():
    with pytest.raises(AttributeError):
        h.does_not_exist  # noqa: B018


def test_tool_specs_shape():
    names = [s.name for s in fkmcp.MCP_TOOL_SPECS]
    assert names == [
        "spark_inference_envelope",
        "spark_weight_footprint",
        "measure_gguf_throughput",
        "measure_gguf_perplexity",
        "quantize_gguf",
        "publish_quant_dry_run",
        "ask_second_brain",
        # M8 — Arena dispatcher job-execution tools (added by demand, M8-7)
        "run_vertical_eval",
        "measure_variants",
        # M10 — Arena recall-pipeline job-execution tools (Bet 5)
        "reindex_memory",
        "rag_eval_index",
        "scout_ingest",
    ]
    by_name = {s.name: s for s in fkmcp.MCP_TOOL_SPECS}
    # the two capability tools + the RAG bridge are read-only; the rest write
    assert by_name["spark_inference_envelope"].read_only is True
    assert by_name["spark_weight_footprint"].read_only is True
    assert by_name["ask_second_brain"].read_only is True
    assert by_name["measure_gguf_throughput"].read_only is False
    assert by_name["quantize_gguf"].read_only is False
    assert by_name["publish_quant_dry_run"].read_only is False
    # M8 eval/measure tools both touch the GPU → not read-only
    assert by_name["run_vertical_eval"].read_only is False
    assert by_name["measure_variants"].read_only is False
    # M10 recall-pipeline tools write the index → not read-only
    assert by_name["reindex_memory"].read_only is False
    assert by_name["rag_eval_index"].read_only is False
    assert by_name["scout_ingest"].read_only is False
    assert {s.surface for s in fkmcp.MCP_TOOL_SPECS} == {
        "capabilities",
        "quant",
        "publish",
        "rag",
        "eval",  # M8 — run_vertical_eval is mcp.py's first fieldkit.eval wiring
        "memory",  # M10 — the recall-pipeline tools (Bet 5)
    }


def test_spark_inference_envelope_hit():
    out = fkmcp.spark_inference_envelope("8B params bf16")
    assert out["model_size"] == "8B params bf16"
    assert isinstance(out["envelope"], str) and out["envelope"]


def test_spark_inference_envelope_miss_returns_keys():
    out = fkmcp.spark_inference_envelope("30B")
    assert out["envelope"] is None
    assert "available_keys" in out
    assert any("params" in k for k in out["available_keys"])


def test_spark_weight_footprint():
    out = fkmcp.spark_weight_footprint(8.0, "fp16")
    assert out["weight_bytes"] == 16_000_000_000
    assert out["weight_gb"] == 16.0
    assert out["unified_memory_gb"] == 128


def test_measure_throughput_rejects_missing_and_non_gguf(tmp_path):
    with pytest.raises(FileNotFoundError):
        fkmcp.measure_gguf_throughput(str(tmp_path / "nope.gguf"))
    bad = tmp_path / "weights.bin"
    bad.write_bytes(b"x")
    with pytest.raises(ValueError):
        fkmcp.measure_gguf_throughput(str(bad))


def test_quantize_dry_run_builds_plan_without_gpu(tmp_path, monkeypatch):
    monkeypatch.setenv("LLAMA_CPP_BIN", str(tmp_path))
    # stub the resolved binaries so LlamaCppPaths.resolve() is satisfied
    (tmp_path / "llama-quantize").write_text("#!/bin/sh\n")
    src = tmp_path / "model-F16.gguf"
    src.write_bytes(b"GGUF")
    out = fkmcp.quantize_gguf(
        model_path=str(src),
        outdir=str(tmp_path / "out"),
        variants=["Q4_K_M", "Q5_K_M"],
        dry_run=True,
    )
    assert out["dry_run"] is True
    assert out["variants"] == ["Q4_K_M", "Q5_K_M"]
    assert any("llama-quantize" in n for n in out["notes"])


def test_quantize_rejects_missing_model(tmp_path):
    with pytest.raises(FileNotFoundError):
        fkmcp.quantize_gguf(model_path=str(tmp_path / "nope"), outdir=str(tmp_path))


def test_publish_dry_run_stages_card_and_never_pushes():
    out = fkmcp.publish_quant_dry_run(
        base_model="deepseek-ai/DeepSeek-R1-0528-Qwen3-8B",
        repo_name="patent-strategist-v3-nemo-GGUF",
        variants=["Q4_K_M", "Q5_K_M"],
        recommended_variant="Q5_K_M",
        perplexity={"Q4_K_M": 10.5, "Q5_K_M": 10.04},
        tokens_per_sec={"Q4_K_M": 40.0, "Q5_K_M": 35.0},
        article_slug="hermes-drives-the-spark-via-fieldkit-mcp",
    )
    assert out["dry_run"] is True
    assert "README.md" in out["staged_files"]
    assert out["card_preview"].startswith("---")  # YAML frontmatter


@pytest.mark.parametrize("name", [fkmcp.MCP_SERVER_NAME, "custom-name"])
def test_build_mcp_server_lists_curated_tools(name):
    pytest.importorskip("mcp")
    import asyncio

    server = fkmcp.build_mcp_server(name)
    tools = asyncio.run(server.list_tools())
    got = {t.name for t in tools}
    assert got == {s.name for s in fkmcp.MCP_TOOL_SPECS}
    # annotations carry the read-only hints the harness relies on for trust
    ro = {t.name: (t.annotations.readOnlyHint if t.annotations else None) for t in tools}
    assert ro["spark_weight_footprint"] is True
    assert ro["quantize_gguf"] is False


def test_require_fastmcp_returns_class_when_available():
    pytest.importorskip("mcp")
    cls = fkmcp._require_fastmcp()
    assert cls.__name__ == "FastMCP"
