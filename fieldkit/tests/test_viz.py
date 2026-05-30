# Copyright 2026 Manav Sehgal
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for `fieldkit.viz`.

Two tiers:
- Dep-free: import is cheap, palette + variant ordering + manifest
  normalization are pure-Python and always run.
- Dep-gated: the matplotlib / great_tables / pandas figure builders run only
  when `fieldkit[notebook]` is installed (importorskip). They assert the
  builders return the right object type and that `save_figure` writes a PNG —
  a vibe-level smoke, not a pixel diff (per `feedback_testing_cadence`).
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

import fieldkit.viz as viz
from fieldkit.viz import (
    DEFAULT_ACCENT,
    STACK_COLORS,
    STYLE_PATH,
    VizNotAvailable,
)
from fieldkit.viz import _resolve


# ---------------- dep-free -------------------------------------------------


def test_style_asset_ships_and_is_readable() -> None:
    assert STYLE_PATH.exists(), f"bundled mplstyle missing at {STYLE_PATH}"
    text = STYLE_PATH.read_text()
    assert "axes.prop_cycle" in text
    assert "figure.facecolor" in text


def test_stack_colors_cover_the_schema_enum() -> None:
    # Mirrors content.config.ts stack_origin enum.
    for stack in ("unsloth", "nemo", "axolotl", "verl", "peft"):
        assert stack in STACK_COLORS
        assert STACK_COLORS[stack].startswith("#")


def test_accent_falls_back_to_brand_blue_for_unknown_stack() -> None:
    d = _resolve(None, stack_origin="nonesuch")
    assert d.accent == DEFAULT_ACCENT
    d2 = _resolve(None, stack_origin="nemo")
    assert d2.accent == STACK_COLORS["nemo"]


def test_resolve_reads_spark_tokens_per_sec_from_manifest() -> None:
    m = SimpleNamespace(
        perplexity={"Q4_K_M": 11.3, "Q8_0": 10.8},
        spark_tokens_per_sec={"Q4_K_M": 41.0, "Q8_0": 26.5},
        vertical_eval={},
        variants=["Q4_K_M", "Q8_0"],
        recommended_variant="Q4_K_M",
        stack_origin="unsloth",
    )
    d = _resolve(m)
    assert d.tokens_per_sec == {"Q4_K_M": 41.0, "Q8_0": 26.5}
    assert d.accent == STACK_COLORS["unsloth"]


def test_resolve_reads_tokens_per_sec_when_no_spark_key() -> None:
    # ModelCard / QuantReport carry `.tokens_per_sec`, not `.spark_*`.
    m = SimpleNamespace(tokens_per_sec={"Q5_K_M": 32.0})
    d = _resolve(m)
    assert d.tokens_per_sec == {"Q5_K_M": 32.0}


def test_resolve_orders_variants_canonically() -> None:
    d = _resolve(None, perplexity={"Q8_0": 1, "Q4_K_M": 2, "Q6_K": 3, "Q5_K_M": 4})
    assert d.variants == ["Q4_K_M", "Q5_K_M", "Q6_K", "Q8_0"]


def test_resolve_unknown_variants_sort_to_end_in_seen_order() -> None:
    d = _resolve(None, perplexity={"weird-b": 1, "Q4_K_M": 2, "weird-a": 3})
    assert d.variants[0] == "Q4_K_M"
    assert set(d.variants[1:]) == {"weird-a", "weird-b"}


def test_resolve_explicit_kwargs_win_over_manifest() -> None:
    m = SimpleNamespace(perplexity={"Q4_K_M": 99.0}, variants=["Q4_K_M"])
    d = _resolve(m, perplexity={"Q4_K_M": 11.3})
    assert d.perplexity == {"Q4_K_M": 11.3}


# ---------------- dep-gated (matplotlib) -----------------------------------


@pytest.fixture()
def real_manifest() -> SimpleNamespace:
    """The shape of the live patent-strategist-v3-unsloth-gguf manifest."""
    return SimpleNamespace(
        slug="patent-strategist-v3-unsloth-gguf",
        base_model="deepseek-ai/DeepSeek-R1-0528-Qwen3-8B",
        variants=["Q4_K_M", "Q5_K_M", "Q6_K", "Q8_0"],
        perplexity={"Q4_K_M": 11.2987, "Q5_K_M": 10.9716, "Q6_K": 10.8737, "Q8_0": 10.8446},
        spark_tokens_per_sec={"Q4_K_M": 41.04, "Q5_K_M": 32.47, "Q6_K": 30.79, "Q8_0": 26.56},
        vertical_eval={"Q4_K_M": 0.82, "Q5_K_M": 0.86, "Q6_K": 0.86, "Q8_0": 0.88},
        vertical_eval_name="PatentBench (n=50)",
        sustained_load_minutes=42.0,
        recommended_variant="Q5_K_M",
        stack_origin="unsloth",
        article="articles/patent-strategist-bakeoff-unsloth-vs-nemo-framework/",
    )


def test_perplexity_sweep_returns_figure(real_manifest: SimpleNamespace) -> None:
    pytest.importorskip("matplotlib")
    from matplotlib.figure import Figure
    fig = viz.perplexity_sweep(real_manifest)
    assert isinstance(fig, Figure)


def test_throughput_bars_returns_figure(real_manifest: SimpleNamespace) -> None:
    pytest.importorskip("matplotlib")
    from matplotlib.figure import Figure
    assert isinstance(viz.throughput_bars(real_manifest), Figure)


def test_vertical_eval_bars_returns_figure(real_manifest: SimpleNamespace) -> None:
    pytest.importorskip("matplotlib")
    from matplotlib.figure import Figure
    assert isinstance(viz.vertical_eval_bars(real_manifest), Figure)


def test_train_wall_compare_returns_figure() -> None:
    pytest.importorskip("matplotlib")
    from matplotlib.figure import Figure
    fig = viz.train_wall_compare({"unsloth": 128.0, "nemo": 95.0})
    assert isinstance(fig, Figure)


def test_spark_quad_returns_single_figure(real_manifest: SimpleNamespace) -> None:
    pytest.importorskip("matplotlib")
    from matplotlib.figure import Figure
    fig = viz.spark_quad(real_manifest)
    assert isinstance(fig, Figure)
    assert len(fig.axes) == 4


def test_spark_quad_handles_missing_thermal_and_vertical() -> None:
    pytest.importorskip("matplotlib")
    from matplotlib.figure import Figure
    m = SimpleNamespace(
        perplexity={"Q4_K_M": 11.3, "Q8_0": 10.8},
        spark_tokens_per_sec={"Q4_K_M": 41.0, "Q8_0": 26.5},
    )
    fig = viz.spark_quad(m)
    assert isinstance(fig, Figure)


def test_save_figure_writes_png_for_matplotlib(tmp_path: Path, real_manifest: SimpleNamespace) -> None:
    pytest.importorskip("matplotlib")
    fig = viz.throughput_bars(real_manifest)
    out = viz.save_figure(fig, tmp_path / "sub" / "tput.png")
    assert out.exists() and out.stat().st_size > 0


def test_save_figure_rejects_wrong_type() -> None:
    with pytest.raises(TypeError):
        viz.save_figure(object(), "/tmp/nope.png")


def test_apply_style_context_runs(tmp_path: Path) -> None:
    pytest.importorskip("matplotlib")
    import matplotlib.pyplot as plt
    with viz.apply_style():
        fig, ax = plt.subplots()
        ax.plot([1, 2, 3], [1, 4, 9])
    assert fig is not None


# ---------------- dep-gated (great_tables) ---------------------------------


def test_variants_table_returns_gt(real_manifest: SimpleNamespace) -> None:
    pytest.importorskip("great_tables")
    pytest.importorskip("pandas")
    from great_tables import GT
    tbl = viz.variants_table(real_manifest)
    assert isinstance(tbl, GT)


def test_variants_table_renders_html(real_manifest: SimpleNamespace) -> None:
    pytest.importorskip("great_tables")
    pytest.importorskip("pandas")
    tbl = viz.variants_table(real_manifest)
    html = tbl.as_raw_html()
    assert "patent-strategist" in html
    assert "PatentBench" in html
