#!/usr/bin/env python3
"""
Scaffold a populated bench-manifest YAML for a new `kind: bench` artifact.

Bench manifests follow the schema documented at
`src/content/artifacts/README.md`. This script generates a populated skeleton
from an HuggingFace dataset slug + paired-article path, leaving editorial
fields (shape labels, results numbers, source blurbs) as `# TODO`
placeholders for the author to fill in.

Read-only — never writes to source or destination. Output goes to stdout.

Usage:
    python3 scaffold_bench_manifest.py \\
        --hf-repo Orionfold/foo-bench \\
        --article articles/foo-bench-on-spark/ \\
        --slug foo-bench-v0.1 \\
        --class foo-domain-reasoning \\
        [--source-cards-path /Volumes/home/ai-field-notes/dataset-cards/]

Pipe to a new file in the destination repo:
    python3 scaffold_bench_manifest.py ... \\
        > src/content/artifacts/foo-bench-v0.1.yaml

Then fill in the `# TODO` placeholders (shape labels, results numbers,
source blurbs) before opening a source-side PR.

The script tries to fetch the HF dataset metadata for license + lastModified.
If the API is unreachable, a partial scaffold still emits to stdout (with
`# TODO: confirm` markers on the affected fields).

If --source-cards-path is provided AND points at a directory containing
`<slug>/data/train.jsonl`, the script picks one random row per detected
`shape` column value and embeds it in `samples`. Otherwise `samples` is left
as a TODO array.
"""

import argparse
import json
import random
import sys
import textwrap
import urllib.error
import urllib.request
from pathlib import Path

HF_API_BASE = "https://huggingface.co/api/datasets"
HTTP_TIMEOUT = 10  # seconds


def fetch_hf_metadata(hf_repo: str) -> dict | None:
    """GET /api/datasets/<repo> from HuggingFace. Returns parsed JSON or None
    on any network / parse failure (caller falls back to TODO placeholders)."""
    url = f"{HF_API_BASE}/{hf_repo}"
    try:
        with urllib.request.urlopen(url, timeout=HTTP_TIMEOUT) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, urllib.error.HTTPError, json.JSONDecodeError, TimeoutError) as e:
        print(f"# WARN: HF metadata fetch failed: {e}", file=sys.stderr)
        return None


def extract_license(meta: dict | None) -> tuple[str, str]:
    """Returns (tier, model). tier defaults to 'free'; model from HF card
    if present, else 'TODO: confirm license model'."""
    tier = "free"
    if meta is None:
        return tier, "# TODO: confirm license model"
    card = meta.get("cardData") or {}
    lic = card.get("license") or meta.get("license")
    if isinstance(lic, list) and lic:
        lic = lic[0]
    return tier, str(lic) if lic else "# TODO: confirm license model"


def extract_published_at(meta: dict | None) -> str:
    """ISO datetime string. From HF's lastModified field if available."""
    if meta is None:
        return "# TODO: confirm published_at"
    last = meta.get("lastModified") or meta.get("createdAt")
    return last or "# TODO: confirm published_at"


def pick_samples_from_jsonl(jsonl_path: Path, seed: int = 42) -> list[dict] | None:
    """Read JSONL; for each distinct `shape` value, pick one row. Returns a
    list of {shape, question, oracle_context, gold_label} dicts, or None if
    the file doesn't exist or has no recognizable rows."""
    if not jsonl_path.is_file():
        return None
    rows_by_shape: dict[str, list[dict]] = {}
    try:
        with jsonl_path.open() as f:
            for line in f:
                r = json.loads(line)
                shape = r.get("shape")
                if not shape:
                    continue
                rows_by_shape.setdefault(shape, []).append(r)
    except (json.JSONDecodeError, OSError) as e:
        print(f"# WARN: failed to read {jsonl_path}: {e}", file=sys.stderr)
        return None
    if not rows_by_shape:
        return None

    random.seed(seed)
    picked = []
    for shape, rows in sorted(rows_by_shape.items()):
        chosen = random.choice(rows)
        picked.append(
            {
                "shape": shape,
                "question": _truncate(chosen.get("question", ""), 400),
                "oracle_context": _truncate(chosen.get("oracle_context", ""), 250),
                "gold_label": _truncate(chosen.get("gold_label", ""), 400),
            }
        )
    return picked


def _truncate(s: str, max_len: int) -> str:
    """Truncate to max_len chars, appending an ellipsis if cut. Strips internal
    newlines so values render cleanly in YAML."""
    s = s.replace("\n", " ").strip()
    if len(s) > max_len:
        return s[: max_len - 1].rstrip() + "…"
    return s


def yaml_quote(s: str) -> str:
    """Quote a string for safe YAML emission. Uses double quotes; escapes
    embedded double quotes. Multi-line strings get block-literal `|` style."""
    if "\n" in s:
        indented = textwrap.indent(s.strip("\n"), "  ")
        return "|\n" + indented
    escaped = s.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def emit_yaml(
    *,
    slug: str,
    klass: str,
    hf_repo: str,
    article: str,
    license_tier: str,
    license_model: str,
    published_at: str,
    samples: list[dict] | None,
) -> str:
    """Build the populated bench manifest YAML."""
    out: list[str] = []

    out.append(f"slug: {slug}")
    out.append("kind: bench")
    out.append(f"class: {klass}")
    out.append("base_model: n/a")
    out.append(f"hf_repo: {hf_repo}")
    out.append("variants: []")
    out.append("license:")
    out.append(f"  tier: {license_tier}")
    if license_model.startswith("# TODO"):
        out.append(f"  model: # {license_model[2:]}")
    else:
        out.append(f"  model: {license_model}")
    out.append(f"article: {article}")
    if published_at.startswith("# TODO"):
        out.append(f"published_at: # {published_at[2:]}")
    else:
        out.append(f'published_at: "{published_at}"')

    out.append("")
    out.append("# Bench-specific fields — schema-driven, all optional.")
    out.append("# See src/content/artifacts/README.md for the contract.")
    out.append("")

    out.append("shapes:")
    out.append("  # TODO: populate with one entry per question shape.")
    out.append("  # Each: { code, label, count, scorer, source }")
    out.append("  # scorer ∈ { deterministic, structural, judge }")
    out.append("  #")
    out.append("  # Example:")
    out.append("  # - code: A")
    out.append("  #   label: 'Claim drafting + validity'")
    out.append("  #   count: 50")
    out.append("  #   scorer: judge")
    out.append("  #   source: bigpatent")
    out.append("")

    out.append("modes:")
    out.append("  - closed")
    out.append("  - retrieval")
    out.append("  - oracle")
    out.append("")

    out.append("results:")
    out.append("  # TODO: populate from the paired methodology article.")
    out.append("  # Per-shape rows + an 'overall' row. Mode keys must match modes[] above.")
    out.append("  #")
    out.append("  # Example:")
    out.append("  # D-mcq:")
    out.append("  #   closed: 0.625")
    out.append("  #   retrieval: 0.850")
    out.append("  #   oracle: 0.950")
    out.append("  # overall:")
    out.append("  #   closed: 0.397")
    out.append("  #   retrieval: 0.489")
    out.append("  #   oracle: 0.541")
    out.append("")

    out.append("results_provenance:")
    out.append("  model: '# TODO: model name + quant (e.g., DeepSeek-R1-...Q5_K_M)'")
    out.append("  article_anchor: '# TODO: optional in-article anchor (#what-the-numbers-say)'")
    out.append("")

    out.append("sources:")
    out.append("  # TODO: one entry per public source corpus")
    out.append("  # Each: { key, name, url, blurb }")
    out.append("  # key must match shapes[].source")
    out.append("")

    out.append("samples:")
    if samples:
        out.append(f"  # Auto-populated from --source-cards-path; one row per detected shape ({len(samples)} samples).")
        for s in samples:
            out.append(f"  - shape: {s['shape']}")
            out.append(f"    question: {yaml_quote(s['question'])}")
            if s.get("oracle_context"):
                out.append(f"    oracle_context: {yaml_quote(s['oracle_context'])}")
            out.append(f"    gold_label: {yaml_quote(s['gold_label'])}")
    else:
        out.append("  # TODO: one representative row per shape")
        out.append("  # Each: { shape, question, oracle_context?, gold_label }")
        out.append("  # Truncate long oracle_context / gold_label values to ~250-400 chars.")
    out.append("")

    out.append("how_to_load: |")
    out.append("  from datasets import load_dataset")
    out.append(f'  ds = load_dataset("{hf_repo}", split="train")')
    out.append("  print(ds)")
    out.append("")

    out.append("citation: |")
    out.append("  # TODO: paste BibTeX block from the dataset card.")

    return "\n".join(out) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Scaffold a populated bench-manifest YAML for a new kind: bench artifact.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--hf-repo", required=True, help="HuggingFace repo, e.g., Orionfold/foo-bench")
    parser.add_argument("--article", required=True, help="Paired field-note path, e.g., articles/foo-bench-on-spark/")
    parser.add_argument("--slug", required=True, help="Artifact slug; also the output filename stem")
    parser.add_argument("--class", dest="klass", required=True, help="Editorial class, e.g., patent-prosecution-reasoning")
    parser.add_argument(
        "--source-cards-path",
        default=None,
        help="Optional: path to dataset-cards/ directory in source repo. If <slug>/data/train.jsonl exists there, samples are auto-picked.",
    )
    args = parser.parse_args()

    meta = fetch_hf_metadata(args.hf_repo)
    tier, model = extract_license(meta)
    pub = extract_published_at(meta)

    samples = None
    if args.source_cards_path:
        jsonl = Path(args.source_cards_path) / args.slug / "data" / "train.jsonl"
        samples = pick_samples_from_jsonl(jsonl)
        if samples:
            print(f"# INFO: picked {len(samples)} samples from {jsonl}", file=sys.stderr)
        else:
            print(f"# WARN: no samples picked (looked for {jsonl})", file=sys.stderr)

    yaml = emit_yaml(
        slug=args.slug,
        klass=args.klass,
        hf_repo=args.hf_repo,
        article=args.article,
        license_tier=tier,
        license_model=model,
        published_at=pub,
        samples=samples,
    )
    print(yaml, end="")
    return 0


if __name__ == "__main__":
    sys.exit(main())
