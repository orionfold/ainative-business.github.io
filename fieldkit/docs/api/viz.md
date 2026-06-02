---
module: viz
title: fieldkit.viz
summary: Branded chart + hero-table builders for Orionfold artifact notebooks. Turns an `ArtifactManifest` (or its bare measurement dicts) into marketing-grade matplotlib `Figure`s styled by the bundled `orionfold.mplstyle`, plus great_tables `GT` hero tables with inline nano-plots. The visual layer behind the notebooks-as-artifacts pilot, article figures, and (eventually) the home-page infographic. Lazy + optional — lives behind the `fieldkit[notebook]` extra.
order: 10
---

## What it is

Five verticals × two notebooks × ~5 figures each is fifty charts that must all read as one brand. `fieldkit.viz` makes the figure the deterministic output of the measured run — the same contract `fieldkit.publish` uses to make the card. Re-style once, re-render everywhere.

Every figure consumes a duck-typed `manifest` (anything with `.perplexity` / `.spark_tokens_per_sec` / `.vertical_eval` / `.variants` / `.recommended_variant` / `.stack_origin` …) **or** the bare measurement dicts as keyword arguments; explicit kwargs win. The module imports nothing from `fieldkit.publish`, so there is no cycle — it duck-types the manifest shape instead.

The accent color is keyed off `stack_origin` (`STACK_COLORS`) so two siblings — the Unsloth lane and the NeMo lane of the same vertical — render visually distinct at a glance. That is _GUIDES/NARRATIVE-CONTRACT.md Rule 7 (data-driven, stack-distinct visuals) expressed in code.

Heavy deps (matplotlib, great_tables, pandas, polars) are lazy and optional. `import fieldkit.viz` stays cheap; the imports happen on first call and raise `VizNotAvailable` with an install hint (`pip install fieldkit[notebook]`) if the extra is missing.

## Public API

```python
from fieldkit.viz import (
    perplexity_sweep, throughput_bars, vertical_eval_bars,
    train_wall_compare, spark_quad,      # matplotlib Figures
    variants_table,                      # great_tables GT
    save_figure, apply_style,
    STYLE_PATH, STACK_COLORS, DEFAULT_ACCENT, VizNotAvailable,
)
```

### Figures (matplotlib)

Each returns a styled `matplotlib.figure.Figure` when called standalone, or draws onto a supplied `ax=` (returning that `Axes`) — which is how `spark_quad` composes its panel from the same primitives.

| Function | Renders |
|---|---|
| `perplexity_sweep` | Line plot of perplexity across canonical-ordered variants. Lower is better; the `recommended_variant` is ringed + bolded. |
| `throughput_bars` | Bar chart of sustained `tok/s` on Spark. Recommended variant at full accent, the rest dimmed. |
| `vertical_eval_bars` | Bar chart of vertical-domain accuracy (fractions in → percent out). |
| `train_wall_compare` | Builder-only. Compares training wall-clock across lanes (`{"unsloth": 128.0, "nemo": 95.0}`); bars colored from `STACK_COLORS`, fastest lane annotated with its delta. |
| `spark_quad` | The four-axis Spark-tested panel — perplexity, throughput, vertical accuracy, thermal envelope in one figure. Mirrors the HF card's measurement quad; the signature visual of a release. |

```python
import fieldkit.viz as viz
fig = viz.spark_quad(manifest)                      # 2×2 panel from the manifest
viz.save_figure(fig, "exports/builder/spark-quad.png", scale=2.0)
```

**Common keyword arguments.** Each figure accepts the manifest dicts as explicit overrides — `perplexity`, `tokens_per_sec`, `vertical_eval`, `vertical_eval_name`, `sustained_load_minutes`, `variants`, `recommended_variant`, `stack_origin` — plus presentation knobs `figsize` and (single-panel) `ax`. `spark_quad` adds `suptitle`; `train_wall_compare` takes `colors` (per-lane overrides) and a `title`; `variants_table` adds `sizes` (per-variant size strings), `title`, `subtitle`, and `article`. Explicit kwargs always win over the manifest.

### `variants_table(manifest=None, *, ...) -> GT`

Publication-grade great_tables hero table of the per-variant measurement matrix (size, perplexity, tok/s, and — when present — vertical accuracy with an inline nano-plot bar). The recommended variant's row is highlighted; a source-note credits the field-notes article from `manifest.article`.

```python
tbl = viz.variants_table(manifest)
tbl.as_raw_html()        # embed in a notebook / HTML page
viz.save_figure(tbl, "exports/variants.png")   # PNG export (needs a browser engine; see below)
```

Nano-plots: great_tables routes its nano-plot NA check through an `Agnostic` dispatcher that imports `polars` even for a pandas frame, so the inline bar is attached only when polars is importable. A pandas-only env renders a clean table without the bar; `fieldkit[notebook]` ships polars so the default install gets it.

### `save_figure(obj, path, *, scale=2.0) -> Path`

Save a matplotlib `Figure` **or** a great_tables `GT` to PNG, creating parent dirs. Matplotlib figures carry the brand `savefig.dpi` from the style (220), scaled by `scale`. great_tables `.save()` shells out to a headless browser engine (selenium / chromium) — in the notebook-snapshot flow, prefer driving Playwright over the table's HTML (`as_raw_html()`) when that engine is not available.

### `apply_style()`

Context manager applying the bundled `orionfold.mplstyle` so ad-hoc matplotlib in a notebook matches the brand:

```python
with viz.apply_style():
    fig, ax = plt.subplots()
    ax.plot(...)
```

### `STYLE_PATH`, `STACK_COLORS`, `DEFAULT_ACCENT`

`STYLE_PATH` is the absolute path to the bundled `assets/orionfold.mplstyle` (ships in the wheel). `STACK_COLORS` maps each `stack_origin` (`unsloth` amber, `nemo` NVIDIA-green, `axolotl`, `verl`, `peft`) to its accent; `DEFAULT_ACCENT` is the brand blue used when `stack_origin` is unset.

## Notes

- **No OKLCH in matplotlib.** The site palette is dark-first OKLCH (`--color-primary` hue 250). `orionfold.mplstyle` translates it to sRGB hex because matplotlib has no OKLCH input; the values are eyeball-matched to the rendered site, not round-tripped.
- **Variant ordering** is canonical GGUF (`Q4_K_M < Q5_K_M < Q6_K < Q8_0 < F16 …`); unknown variant names sort to the end in first-seen order so a chart's x-axis stays sane regardless of dict insertion order.
- **Vibe-tested, not pixel-diffed.** Per the project's testing cadence, the test suite asserts the builders return the right object type and that exports write a non-empty PNG — visual quality is reviewed by eye, not a golden-image diff.
