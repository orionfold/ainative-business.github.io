# Copyright 2026 Manav Sehgal
# SPDX-License-Identifier: Apache-2.0
"""Branded chart + hero-table builders for Orionfold artifact notebooks.

`fieldkit.viz` turns an `ArtifactManifest` (or its bare measurement dicts) into
marketing-grade visuals: matplotlib `Figure`s styled by the bundled
`orionfold.mplstyle`, and great_tables `GT` hero tables. It is the visual layer
the notebooks-as-artifacts pilot (`specs/notebooks-as-artifacts-v1.md`) leans on
so every vertical's builder/user notebook, the field-notes article figures, and
(eventually) the home-page infographic all draw from one branded surface.

Why a module and not ad-hoc plotting per notebook. Five verticals × two
notebooks × ~5 figures each is 50 charts that must all read as one brand. A
charting function that consumes the manifest directly means the figure is the
deterministic output of the measured run — same contract as `fieldkit.publish`
makes the card. Re-style once, re-render everywhere.

Design:

- **Lazy, optional deps.** matplotlib + great_tables + pandas live behind the
  `fieldkit[notebook]` extra. `import fieldkit.viz` is cheap; the heavy imports
  happen on first call and raise `VizNotAvailable` with an install hint if the
  extra is missing.
- **Manifest-or-dicts.** Every figure accepts a duck-typed `manifest` (anything
  with `.perplexity` / `.spark_tokens_per_sec` / `.vertical_eval` / `.variants`
  / `.recommended_variant` / `.stack_origin` …) *or* the bare dicts as kwargs;
  explicit kwargs win. No import of `fieldkit.publish` — duck-typed to avoid a
  cycle.
- **Stack-distinct color.** The accent is keyed off `stack_origin` via
  `STACK_COLORS` so two siblings (Unsloth vs NeMo) render visually distinct at a
  glance — NARRATIVE-CONTRACT.md Rule 7.
- **`ax=`-aware.** Single-panel figures accept an `ax` to draw onto, which is
  how `spark_quad` composes the four-axis panel out of the same primitives.

Public surface: `perplexity_sweep`, `throughput_bars`, `vertical_eval_bars`,
`train_wall_compare`, `spark_quad`, `variants_table`, `save_figure`,
`apply_style`, plus `STYLE_PATH`, `STACK_COLORS`, `VizNotAvailable`.
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Iterator, Optional, Sequence, Union

if TYPE_CHECKING:  # import only for type checkers; never at runtime
    from matplotlib.axes import Axes
    from matplotlib.figure import Figure
    from great_tables import GT

__all__ = [
    "VizNotAvailable",
    "STYLE_PATH",
    "STACK_COLORS",
    "DEFAULT_ACCENT",
    "apply_style",
    "perplexity_sweep",
    "throughput_bars",
    "vertical_eval_bars",
    "train_wall_compare",
    "spark_quad",
    "variants_table",
    "save_figure",
]


# --- assets / palette ------------------------------------------------------

STYLE_PATH: Path = Path(__file__).resolve().parent.parent / "assets" / "orionfold.mplstyle"
"""Absolute path to the bundled brand mplstyle. Stable across installs because
it ships in the wheel (`[tool.hatch.build.targets.wheel].include`)."""

DEFAULT_ACCENT: str = "#5B9CFF"
"""Brand blue — `--color-primary` (oklch 0.70/0.18/250) in sRGB. The accent
when `stack_origin` is unset."""

STACK_COLORS: dict[str, str] = {
    "unsloth": "#F2A93B",  # amber — the Unsloth lane
    "nemo": "#76B900",     # NVIDIA green — the NeMo Framework lane
    "axolotl": "#E255A1",  # magenta
    "verl": "#2DD4BF",     # teal
    "peft": "#A78BFA",     # violet
}
"""Per-training-stack accent so siblings render visually distinct (Rule 7).
Falls back to `DEFAULT_ACCENT` for unknown / unset `stack_origin`."""

# Canonical GGUF variant ordering (low quality/size → high). Anything not
# listed sorts to the end in first-seen order — keeps a chart's x-axis sane
# regardless of the dict insertion order in the manifest.
_VARIANT_ORDER: tuple[str, ...] = (
    "Q2_K", "Q3_K_S", "Q3_K_M", "Q3_K_L",
    "Q4_0", "Q4_K_S", "Q4_K_M",
    "Q5_K_S", "Q5_K_M", "Q6_K", "Q8_0",
    "F16", "BF16", "F32",
)

_MUTED = "#9AA3AF"
_TEXT = "#E6E9EE"


class VizNotAvailable(ImportError):
    """The `fieldkit[notebook]` viz deps are not installed in this env.

    `fieldkit.viz` lazy-imports matplotlib / great_tables / pandas so plain
    `import fieldkit` stays cheap. Install with `pip install fieldkit[notebook]`.
    """


def _require_matplotlib() -> Any:
    try:
        import matplotlib  # type: ignore[import-not-found]
        import matplotlib.pyplot as plt  # noqa: F401
    except ImportError as exc:
        raise VizNotAvailable(
            "fieldkit.viz charts require matplotlib. Install the extra:"
            " `pip install fieldkit[notebook]`."
        ) from exc
    return matplotlib


def _require_great_tables() -> Any:
    try:
        import great_tables  # type: ignore[import-not-found]
    except ImportError as exc:
        raise VizNotAvailable(
            "fieldkit.viz.variants_table requires great_tables. Install the"
            " extra: `pip install fieldkit[notebook]`."
        ) from exc
    return great_tables


def _polars_available() -> bool:
    """great_tables nanoplot rendering currently needs polars even with a
    pandas frame (its Agnostic NA-dispatcher). Gate the nanoplot on it."""
    try:
        import polars  # type: ignore[import-not-found]  # noqa: F401
        return True
    except ImportError:
        return False


def _require_pandas() -> Any:
    try:
        import pandas  # type: ignore[import-not-found]
    except ImportError as exc:
        raise VizNotAvailable(
            "fieldkit.viz.variants_table requires pandas as the great_tables"
            " frame backend. Install the extra: `pip install fieldkit[notebook]`."
        ) from exc
    return pandas


# --- data normalization ----------------------------------------------------


@dataclass
class _VizData:
    """Normalized view over a manifest-or-dicts call. Internal."""

    variants: list[str] = field(default_factory=list)
    perplexity: dict[str, float] = field(default_factory=dict)
    tokens_per_sec: dict[str, float] = field(default_factory=dict)
    vertical_eval: dict[str, float] = field(default_factory=dict)
    vertical_eval_name: Optional[str] = None
    sustained_load_minutes: Optional[float] = None
    recommended_variant: Optional[str] = None
    stack_origin: Optional[str] = None
    sizes: dict[str, str] = field(default_factory=dict)
    slug: Optional[str] = None
    article: Optional[str] = None
    base_model: Optional[str] = None

    @property
    def accent(self) -> str:
        return STACK_COLORS.get(self.stack_origin or "", DEFAULT_ACCENT)

    def ordered(self, keys: Sequence[str]) -> list[str]:
        """Sort the given variant names into canonical GGUF order."""
        def rank(name: str) -> tuple[int, int]:
            try:
                return (0, _VARIANT_ORDER.index(name))
            except ValueError:
                return (1, list(keys).index(name))
        return sorted(keys, key=rank)


def _resolve(manifest: Any, **overrides: Any) -> _VizData:
    """Build a `_VizData` from an optional duck-typed manifest + kwarg overrides.

    Reads `spark_tokens_per_sec` (ArtifactManifest) and `tokens_per_sec`
    (ModelCard / QuantReport) both — whichever the object carries. Explicit
    kwargs always win over the manifest.
    """
    data = _VizData()
    if manifest is not None:
        data.perplexity = dict(getattr(manifest, "perplexity", {}) or {})
        tps = getattr(manifest, "spark_tokens_per_sec", None)
        if tps is None:
            tps = getattr(manifest, "tokens_per_sec", None)
        data.tokens_per_sec = dict(tps or {})
        data.vertical_eval = dict(getattr(manifest, "vertical_eval", {}) or {})
        data.vertical_eval_name = getattr(manifest, "vertical_eval_name", None)
        data.sustained_load_minutes = getattr(manifest, "sustained_load_minutes", None)
        data.recommended_variant = getattr(manifest, "recommended_variant", None)
        data.stack_origin = getattr(manifest, "stack_origin", None)
        data.slug = getattr(manifest, "slug", None)
        data.article = getattr(manifest, "article", None)
        data.base_model = getattr(manifest, "base_model", None)
        mv = getattr(manifest, "variants", None)
        if mv:
            data.variants = list(mv)

    # Apply explicit overrides.
    for key in (
        "perplexity", "tokens_per_sec", "vertical_eval", "vertical_eval_name",
        "sustained_load_minutes", "recommended_variant", "stack_origin",
        "sizes", "slug", "article", "base_model",
    ):
        if overrides.get(key) is not None:
            setattr(data, key, overrides[key])
    if overrides.get("variants") is not None:
        data.variants = list(overrides["variants"])

    # If no explicit variant list, derive + canonical-order from whichever
    # measurement dicts are populated.
    if not data.variants:
        seen: list[str] = []
        for d in (data.perplexity, data.tokens_per_sec, data.vertical_eval):
            for k in d:
                if k not in seen:
                    seen.append(k)
        data.variants = data.ordered(seen)
    else:
        data.variants = data.ordered(data.variants)
    return data


# --- style -----------------------------------------------------------------


@contextmanager
def apply_style() -> Iterator[None]:
    """Context manager applying the bundled `orionfold.mplstyle`.

    Use to wrap raw matplotlib in a notebook so ad-hoc plots match the brand::

        with fieldkit.viz.apply_style():
            fig, ax = plt.subplots()
            ax.plot(...)
    """
    mpl = _require_matplotlib()
    with mpl.style.context(str(STYLE_PATH)):
        yield


def _bar_value_labels(ax: "Axes", bars: Any, fmt: str, color: str) -> None:
    """Annotate each bar with its value above the bar."""
    for rect in bars:
        h = rect.get_height()
        ax.annotate(
            fmt.format(h),
            xy=(rect.get_x() + rect.get_width() / 2, h),
            xytext=(0, 4),
            textcoords="offset points",
            ha="center", va="bottom", fontsize=9, color=color,
        )


# --- single-panel drawers (style-agnostic; called under a style context) ---


def _draw_perplexity_sweep(ax: "Axes", data: _VizData) -> None:
    variants = [v for v in data.variants if v in data.perplexity]
    ys = [data.perplexity[v] for v in variants]
    ax.plot(variants, ys, marker="o", color=data.accent, zorder=3)
    for v, y in zip(variants, ys):
        weight = "bold" if v == data.recommended_variant else "normal"
        ax.annotate(
            f"{y:.3f}", xy=(v, y), xytext=(0, 8), textcoords="offset points",
            ha="center", fontsize=9, color=_TEXT, fontweight=weight,
        )
    if data.recommended_variant in variants:
        ridx = variants.index(data.recommended_variant)
        ax.scatter([variants[ridx]], [ys[ridx]], s=150, facecolors="none",
                   edgecolors=data.accent, linewidths=2.0, zorder=4)
    ax.set_ylabel("Perplexity (wikitext-2)")
    ax.set_title("Perplexity — lower is better")
    if ys:
        pad = (max(ys) - min(ys)) * 0.25 or 0.1
        ax.set_ylim(min(ys) - pad, max(ys) + pad * 1.5)


def _draw_throughput_bars(ax: "Axes", data: _VizData) -> None:
    variants = [v for v in data.variants if v in data.tokens_per_sec]
    ys = [data.tokens_per_sec[v] for v in variants]
    colors = [
        data.accent if v == data.recommended_variant else _dim(data.accent)
        for v in variants
    ]
    bars = ax.bar(variants, ys, color=colors, zorder=3)
    _bar_value_labels(ax, bars, "{:.1f}", _TEXT)
    ax.set_ylabel("tok/s on Spark (GB10)")
    ax.set_title("Throughput — higher is better")


def _draw_vertical_eval_bars(ax: "Axes", data: _VizData) -> None:
    variants = [v for v in data.variants if v in data.vertical_eval]
    ys = [data.vertical_eval[v] * 100 for v in variants]
    colors = [
        data.accent if v == data.recommended_variant else _dim(data.accent)
        for v in variants
    ]
    bars = ax.bar(variants, ys, color=colors, zorder=3)
    _bar_value_labels(ax, bars, "{:.0f}%", _TEXT)
    name = data.vertical_eval_name or "Vertical eval"
    ax.set_ylabel(f"{name} accuracy (%)")
    ax.set_title("Vertical accuracy — higher is better")
    ax.set_ylim(0, max(ys + [100]) * 1.1 if ys else 100)


def _draw_thermal(ax: "Axes", data: _VizData) -> None:
    minutes = data.sustained_load_minutes
    ax.set_title("Thermal envelope")
    if minutes is None:
        ax.text(0.5, 0.5, "no thermal probe\nrecorded", ha="center", va="center",
                color=_MUTED, transform=ax.transAxes, fontsize=11)
        ax.set_axis_off()
        return
    ax.barh(["sustained load"], [minutes], color=data.accent, zorder=3, height=0.4)
    ax.annotate(
        f"{minutes:.0f} min", xy=(minutes, 0), xytext=(6, 0),
        textcoords="offset points", va="center", ha="left",
        fontsize=12, fontweight="bold", color=_TEXT,
    )
    ax.set_xlabel("minutes before thermal throttle (single GB10)")
    ax.set_xlim(0, minutes * 1.35)
    ax.grid(axis="x")


def _dim(hex_color: str) -> str:
    """Return a muted variant of an accent for non-recommended bars."""
    h = hex_color.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    # Blend 55% toward the dark canvas.
    bg = (0x0E, 0x11, 0x16)
    mix = tuple(int(c * 0.45 + b2 * 0.55) for c, b2 in zip((r, g, b), bg))
    return "#{:02x}{:02x}{:02x}".format(*mix)


# --- public single-panel figures -------------------------------------------


def _single(draw: Any, data: _VizData, ax: Optional["Axes"],
            figsize: tuple[float, float]) -> Union["Figure", "Axes"]:
    """Shared wrapper — draw onto `ax` if given (returns the Axes), else create
    a styled figure (returns the Figure)."""
    if ax is not None:
        draw(ax, data)
        return ax
    mpl = _require_matplotlib()
    import matplotlib.pyplot as plt
    with mpl.style.context(str(STYLE_PATH)):
        fig, new_ax = plt.subplots(figsize=figsize)
        draw(new_ax, data)
        fig.tight_layout()
    return fig


def perplexity_sweep(
    manifest: Any = None, *, perplexity: Optional[dict[str, float]] = None,
    variants: Optional[Sequence[str]] = None, recommended_variant: Optional[str] = None,
    stack_origin: Optional[str] = None, ax: Optional["Axes"] = None,
    figsize: tuple[float, float] = (6.4, 4.0),
) -> Union["Figure", "Axes"]:
    """Line plot of perplexity across variants (canonical-ordered). Lower is
    better; the recommended variant is ringed + bolded."""
    data = _resolve(manifest, perplexity=perplexity, variants=variants,
                    recommended_variant=recommended_variant, stack_origin=stack_origin)
    return _single(_draw_perplexity_sweep, data, ax, figsize)


def throughput_bars(
    manifest: Any = None, *, tokens_per_sec: Optional[dict[str, float]] = None,
    variants: Optional[Sequence[str]] = None, recommended_variant: Optional[str] = None,
    stack_origin: Optional[str] = None, ax: Optional["Axes"] = None,
    figsize: tuple[float, float] = (6.4, 4.0),
) -> Union["Figure", "Axes"]:
    """Bar chart of sustained `tok/s` on Spark per variant. Recommended variant
    rendered at full accent; the rest dimmed."""
    data = _resolve(manifest, tokens_per_sec=tokens_per_sec, variants=variants,
                    recommended_variant=recommended_variant, stack_origin=stack_origin)
    return _single(_draw_throughput_bars, data, ax, figsize)


def vertical_eval_bars(
    manifest: Any = None, *, vertical_eval: Optional[dict[str, float]] = None,
    vertical_eval_name: Optional[str] = None, variants: Optional[Sequence[str]] = None,
    recommended_variant: Optional[str] = None, stack_origin: Optional[str] = None,
    ax: Optional["Axes"] = None, figsize: tuple[float, float] = (6.4, 4.0),
) -> Union["Figure", "Axes"]:
    """Bar chart of vertical-domain eval accuracy per variant (fractions in →
    percent out)."""
    data = _resolve(manifest, vertical_eval=vertical_eval,
                    vertical_eval_name=vertical_eval_name, variants=variants,
                    recommended_variant=recommended_variant, stack_origin=stack_origin)
    return _single(_draw_vertical_eval_bars, data, ax, figsize)


def train_wall_compare(
    wall_minutes: dict[str, float], *, title: str = "Training wall-clock",
    colors: Optional[dict[str, str]] = None, ax: Optional["Axes"] = None,
    figsize: tuple[float, float] = (6.4, 4.0),
) -> Union["Figure", "Axes"]:
    """Builder-only: compare training wall-clock across backends/lanes.

    `wall_minutes` maps a lane name (e.g. ``"unsloth"`` / ``"nemo"``) to its
    measured wall-clock in minutes. Bars are colored from `STACK_COLORS` when a
    lane name matches a known stack, else cycle the brand palette. The fastest
    lane is annotated with its delta vs the slowest.
    """
    lanes = list(wall_minutes.keys())
    vals = [wall_minutes[k] for k in lanes]
    bar_colors = [
        (colors or {}).get(k) or STACK_COLORS.get(k, DEFAULT_ACCENT) for k in lanes
    ]

    def draw(a: "Axes", _d: Any) -> None:
        bars = a.bar(lanes, vals, color=bar_colors, zorder=3)
        _bar_value_labels(a, bars, "{:.0f} min", _TEXT)
        a.set_ylabel("wall-clock (minutes)")
        a.set_title(title)
        if len(vals) >= 2:
            fastest = min(range(len(vals)), key=lambda i: vals[i])
            slowest = max(vals)
            saved = (slowest - vals[fastest]) / slowest * 100 if slowest else 0
            a.annotate(
                f"{lanes[fastest]} −{saved:.0f}%",
                xy=(fastest, vals[fastest]), xytext=(0, 18),
                textcoords="offset points", ha="center", fontsize=10,
                fontweight="bold", color=STACK_COLORS.get(lanes[fastest], DEFAULT_ACCENT),
            )

    return _single(draw, _VizData(), ax, figsize)


def spark_quad(
    manifest: Any = None, *, perplexity: Optional[dict[str, float]] = None,
    tokens_per_sec: Optional[dict[str, float]] = None,
    vertical_eval: Optional[dict[str, float]] = None,
    vertical_eval_name: Optional[str] = None,
    sustained_load_minutes: Optional[float] = None,
    variants: Optional[Sequence[str]] = None, recommended_variant: Optional[str] = None,
    stack_origin: Optional[str] = None, suptitle: Optional[str] = None,
    figsize: tuple[float, float] = (12.0, 8.5),
) -> "Figure":
    """The four-axis Spark-tested panel — mirrors the HF card's measurement
    quad in one figure: perplexity, throughput, vertical accuracy, thermal
    envelope. The signature visual of an Orionfold release."""
    data = _resolve(
        manifest, perplexity=perplexity, tokens_per_sec=tokens_per_sec,
        vertical_eval=vertical_eval, vertical_eval_name=vertical_eval_name,
        sustained_load_minutes=sustained_load_minutes, variants=variants,
        recommended_variant=recommended_variant, stack_origin=stack_origin,
    )
    mpl = _require_matplotlib()
    import matplotlib.pyplot as plt
    with mpl.style.context(str(STYLE_PATH)):
        fig, axes = plt.subplots(2, 2, figsize=figsize)
        _draw_perplexity_sweep(axes[0][0], data)
        _draw_throughput_bars(axes[0][1], data)
        _draw_vertical_eval_bars(axes[1][0], data)
        _draw_thermal(axes[1][1], data)
        title = suptitle or (
            f"Spark-tested: {data.slug}" if data.slug else "Spark-tested measurement quad"
        )
        fig.suptitle(title, fontsize=16, fontweight="bold", color=_TEXT)
        fig.tight_layout(rect=(0, 0, 1, 0.97))
    return fig


# --- hero table -------------------------------------------------------------


def variants_table(
    manifest: Any = None, *, perplexity: Optional[dict[str, float]] = None,
    tokens_per_sec: Optional[dict[str, float]] = None,
    vertical_eval: Optional[dict[str, float]] = None,
    vertical_eval_name: Optional[str] = None, sizes: Optional[dict[str, str]] = None,
    variants: Optional[Sequence[str]] = None, recommended_variant: Optional[str] = None,
    stack_origin: Optional[str] = None, title: Optional[str] = None,
    subtitle: Optional[str] = None, article: Optional[str] = None,
) -> "GT":
    """Publication-grade great_tables hero table of the per-variant measurement
    matrix: size, perplexity, tok/s, and (when present) vertical accuracy with
    an inline nano-plot bar. The recommended variant's row is highlighted; a
    source-note credits the field-notes article.

    Returns a `great_tables.GT` — call `.save(path)` (or `fieldkit.viz.save_figure`)
    to export a PNG, or display it directly in a notebook cell.
    """
    gt_mod = _require_great_tables()
    pd = _require_pandas()
    GT = gt_mod.GT

    data = _resolve(
        manifest, perplexity=perplexity, tokens_per_sec=tokens_per_sec,
        vertical_eval=vertical_eval, vertical_eval_name=vertical_eval_name,
        sizes=sizes, variants=variants, recommended_variant=recommended_variant,
        stack_origin=stack_origin, article=article,
    )
    has_vertical = bool(data.vertical_eval)
    rows: list[dict[str, Any]] = []
    for v in data.variants:
        row: dict[str, Any] = {
            "Variant": v,
            "Size": data.sizes.get(v, "—"),
            "Perplexity": data.perplexity.get(v),
            "tok/s": data.tokens_per_sec.get(v),
        }
        if has_vertical:
            ve = data.vertical_eval.get(v)
            row["Accuracy"] = ve * 100 if isinstance(ve, (int, float)) else None
        rows.append(row)
    df = pd.DataFrame(rows)

    name = data.vertical_eval_name or "Vertical eval"
    tbl = GT(df, rowname_col="Variant")
    tbl = tbl.tab_header(
        title=title or (f"{data.slug}" if data.slug else "Spark-tested variants"),
        subtitle=subtitle or "Measured end-to-end on the NVIDIA DGX Spark (GB10, 128 GB unified memory)",
    )
    tbl = tbl.fmt_number(columns="Perplexity", decimals=3)
    tbl = tbl.fmt_number(columns="tok/s", decimals=1)
    if has_vertical:
        tbl = tbl.fmt_number(columns="Accuracy", decimals=0, pattern="{x}%")
        tbl = tbl.cols_label(Accuracy=name)
        # Inline nano-plot bar for accuracy. great_tables' nanoplot renderer
        # routes its NA check through an Agnostic dispatcher that imports
        # `polars` even for a pandas frame, so we only attach the nanoplot when
        # polars is importable — a pandas-only env still renders a clean table,
        # just without the inline bar. `fieldkit[notebook]` ships polars so the
        # default install gets the nanoplot.
        if _polars_available():
            try:
                tbl = tbl.fmt_nanoplot(columns="Accuracy", plot_type="bar")
            except Exception:  # noqa: BLE001 - nanoplot signature drift across versions
                pass
    tbl = tbl.tab_source_note(
        source_note=_source_note(data) if data.article else
        "Source: Orionfold Spark-side measurement."
    )
    # Highlight the recommended row.
    if data.recommended_variant and data.recommended_variant in set(data.variants):
        try:
            from great_tables import loc, style
            tbl = tbl.tab_style(
                style=[style.fill(color="#13202E"), style.text(weight="bold")],
                locations=loc.body(rows=[data.recommended_variant]),
            )
            tbl = tbl.tab_style(
                style=style.text(weight="bold"),
                locations=loc.stub(rows=[data.recommended_variant]),
            )
        except Exception:  # noqa: BLE001 - loc/style API drift tolerance
            pass
    return tbl


def _source_note(data: _VizData) -> str:
    art = (data.article or "").strip().strip("/")
    slug = art.split("/")[-1] if art else ""
    if slug:
        return f"Methods: ainative.business/field-notes/{slug}/"
    return "Source: Orionfold Spark-side measurement."


# --- export -----------------------------------------------------------------


def save_figure(obj: Any, path: Union[str, Path], *, scale: float = 2.0) -> Path:
    """Save a matplotlib `Figure` **or** a great_tables `GT` to PNG.

    `scale` is the great_tables `.save(scale=)` (resolution multiplier);
    matplotlib figures already carry `savefig.dpi=220` from the brand style, so
    `scale` is applied as a dpi multiplier there too. Creates parent dirs.
    Returns the written path.
    """
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    # great_tables GT?
    if hasattr(obj, "save") and obj.__class__.__name__ == "GT":
        obj.save(str(out), scale=scale)
        return out
    # matplotlib Figure?
    if hasattr(obj, "savefig"):
        obj.savefig(str(out), dpi=int(110 * scale))
        return out
    raise TypeError(
        f"save_figure expects a matplotlib Figure or great_tables GT, got"
        f" {type(obj)!r}."
    )
