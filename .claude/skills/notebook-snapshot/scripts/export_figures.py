#!/usr/bin/env python3
# Copyright 2026 Manav Sehgal
# SPDX-License-Identifier: Apache-2.0
"""Export the branded matplotlib hero figures for a vertical, straight from the
artifact manifest. DETERMINISTIC — no LLM, no browser (Agg backend).

These are the money shots — `spark_quad` plus the single-axis charts —
reproducible from the manifest alone, so they render even when a hardware-only
builder step was recorded rather than run live. The great_tables hero table is
NOT exported here (its `.save()` needs selenium); capture it via Playwright over
the nbconvert HTML.

Usage:
    export_figures.py --manifest src/content/artifacts/<slug>.yaml \
        --which builder --out notebooks/<vertical>/exports/builder \
        [--wall unsloth=128,nemo=95]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from types import SimpleNamespace

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "fieldkit" / "src"))
import fieldkit.viz as viz  # noqa: E402


def _manifest_ns(path: Path) -> SimpleNamespace:
    d = yaml.safe_load(path.read_text(encoding="utf-8"))
    # ArtifactManifest emits tok/s under `spark_tokens_per_sec`; viz reads it.
    return SimpleNamespace(**d)


def _parse_wall(spec: str | None) -> dict[str, float]:
    if not spec:
        return {}
    out: dict[str, float] = {}
    for pair in spec.split(","):
        if "=" in pair:
            k, v = pair.split("=", 1)
            out[k.strip()] = float(v)
    return out


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--manifest", required=True, type=Path)
    ap.add_argument("--which", choices=["builder", "user"], default="builder")
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--wall", default=None, help="builder-only, e.g. unsloth=128,nemo=95")
    ap.add_argument("--scale", type=float, default=2.0)
    args = ap.parse_args(argv)

    m = _manifest_ns(args.manifest)
    args.out.mkdir(parents=True, exist_ok=True)
    written: list[str] = []

    def save(fig: object, name: str) -> None:
        p = viz.save_figure(fig, args.out / name, scale=args.scale)
        written.append(str(p))

    # spark_quad — always (the signature hero).
    save(viz.spark_quad(m), "spark-quad.png")

    # Single-axis charts only when the manifest carries that data.
    if getattr(m, "perplexity", None):
        save(viz.perplexity_sweep(m), "perplexity-sweep.png")
    tps = getattr(m, "spark_tokens_per_sec", None) or getattr(m, "tokens_per_sec", None)
    if tps:
        save(viz.throughput_bars(m), "throughput-bars.png")
    if getattr(m, "vertical_eval", None):
        save(viz.vertical_eval_bars(m), "vertical-eval-bars.png")

    # train-wall: builder-only, needs measured per-lane minutes.
    wall = _parse_wall(args.wall)
    if args.which == "builder" and wall:
        save(viz.train_wall_compare(wall, title="Training wall — by lane"), "train-wall.png")

    print(f"exported {len(written)} figures to {args.out}:")
    for w in written:
        print("  -", Path(w).name)
    if args.which == "builder" and not wall:
        print("note: pass --wall unsloth=NN,nemo=NN to also export train-wall.png")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
