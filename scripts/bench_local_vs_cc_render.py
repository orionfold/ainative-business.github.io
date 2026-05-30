#!/usr/bin/env python3
# Copyright 2026 Manav Sehgal
# SPDX-License-Identifier: Apache-2.0
"""Join out-*.jsonl files into a side-by-side comparison markdown.

Reads the queue + any out-{backend}-{slug}.jsonl files in the same dir,
emits comparison.md with one section per prompt — full <think> + answer
from each generator stacked, plus per-row blank score columns for the
vibe-test eyeball pass. Also writes summary.json with `<think>` presence
rate, mean wall_s, mean output_tok per generator.

CC-in-session output (out-cc.jsonl) is treated identically — Claude in
the current session appends rows there following the same schema as the
HTTP backends.

Usage:
  python bench_local_vs_cc_render.py
  python bench_local_vs_cc_render.py --dir /tmp/aifn-bench-local-vs-cc
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path


def load_outputs(run_dir: Path) -> dict[str, list[dict]]:
    bundles: dict[str, list[dict]] = {}
    for f in sorted(run_dir.glob("out-*.jsonl")):
        rows = [json.loads(line) for line in f.read_text().splitlines() if line.strip()]
        if rows:
            label = f.stem.replace("out-", "")
            bundles[label] = rows
    return bundles


def summarize(rows: list[dict]) -> dict:
    walls = [r["wall_s"] for r in rows if r.get("wall_s") is not None]
    outs = [r["output_tok"] for r in rows if r.get("output_tok") is not None]
    return {
        "n_rows": len(rows),
        "n_with_think": sum(1 for r in rows if r.get("has_think")),
        "mean_wall_s": round(statistics.mean(walls), 2) if walls else None,
        "mean_output_tok": round(statistics.mean(outs), 0) if outs else None,
        "model": rows[0].get("model") if rows else None,
    }


def render_md(queue: list[dict], bundles: dict[str, list[dict]]) -> str:
    lines: list[str] = ["# Local-vs-CC routing bench — comparison\n"]

    lines.append("## Summary\n")
    lines.append("| Generator | Model | n | `<think>` rate | mean wall (s) | mean out tok |")
    lines.append("|---|---|---|---|---|---|")
    for label, rows in bundles.items():
        s = summarize(rows)
        rate = f"{s['n_with_think']}/{s['n_rows']}" if s["n_rows"] else "0/0"
        lines.append(
            f"| {label} | {s['model'] or '?'} | {s['n_rows']} | {rate} "
            f"| {s['mean_wall_s'] or '–'} | {s['mean_output_tok'] or '–'} |"
        )
    lines.append("")

    lines.append("## Per-row eyeball pass\n")
    lines.append("Score each row 1–5 on **legal coherence** (would a patent attorney trust the chain?). Write in the *Your score* column.\n")
    for q in queue:
        idx, fam, prompt = q["row_idx"], q["family"], q["prompt"]
        lines.append(f"### Row {idx} · {fam}\n")
        lines.append(f"**Prompt:** {prompt}\n")
        lines.append("| Generator | Your score |")
        lines.append("|---|---|")
        for label in bundles:
            lines.append(f"| `{label}` | |")
        lines.append("")
        for label, rows in bundles.items():
            match = next((r for r in rows if r["row_idx"] == idx), None)
            lines.append(f"<details><summary><b>{label}</b></summary>\n")
            if match is None:
                lines.append("_(no output)_\n")
            else:
                think = match.get("think", "")
                answer = match.get("answer", "")
                has_think = match.get("has_think", False)
                tag = "" if has_think else " · ⚠️ NO `<think>` BLOCK"
                lines.append(f"_wall={match.get('wall_s')}s · out_tok={match.get('output_tok')}{tag}_\n")
                if think:
                    lines.append("**Think:**\n")
                    lines.append("```\n" + think + "\n```\n")
                lines.append("**Answer:**\n")
                lines.append("```\n" + answer + "\n```\n")
            lines.append("</details>\n")
        lines.append("---\n")
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--dir", default="/tmp/aifn-bench-local-vs-cc")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    run_dir = Path(args.dir)
    queue_path = run_dir / "queue.jsonl"
    if not queue_path.exists():
        print(f"ERROR: queue not found at {queue_path}", file=sys.stderr)
        return 2

    queue = [json.loads(line) for line in queue_path.read_text().splitlines() if line.strip()]
    bundles = load_outputs(run_dir)
    if not bundles:
        print(
            "WARN: no out-*.jsonl files yet — run a generator (ollama / nim / "
            "cc-in-session) before render makes sense.",
            file=sys.stderr,
        )

    summary = {label: summarize(rows) for label, rows in bundles.items()}
    (run_dir / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    (run_dir / "comparison.md").write_text(render_md(queue, bundles))
    print(f"Wrote {run_dir}/comparison.md")
    print(f"Wrote {run_dir}/summary.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
