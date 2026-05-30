"""Build the HF-uploadable staging dir for Orionfold/patent-strategist-bench-v0.1.

Consolidates the 7 in-repo `seed-*.jsonl` files at
`/home/nvidia/data/eval-benches/patent-strategist/` into a single `train.jsonl`
with a flattened, HF-friendly schema, copies the dataset card from
`dataset-cards/patent-strategist-bench-v0.1/README.md`, and runs a basic load
test through `datasets.load_dataset` to confirm the staged tree parses.

Output staging dir:
  /tmp/hf-stage/patent-strategist-bench-v0.1/
    README.md
    data/train.jsonl

The staging dir is what gets uploaded by `scripts/publish_patent_bench.py`.
Re-run this script any time the source seeds or the card change.

Usage:
  python scripts/build_hf_dataset_bench.py
"""
from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

BENCH_DIR = Path("/home/nvidia/data/eval-benches/patent-strategist")
CARD_PATH = Path("/home/nvidia/ainative-business.github.io/dataset-cards/patent-strategist-bench-v0.1/README.md")
STAGE_DIR = Path("/tmp/hf-stage/patent-strategist-bench-v0.1")

SHAPES = ["A", "B", "C", "D-irac", "D-mcq", "D-oa", "E"]

# Tag subkeys that ARE flattened to top-level columns (because they're either
# universal or near-universal across shapes):
COMMON_TAG_KEYS = {"shape", "source", "source_status", "rubric_notes"}


def flatten(row: dict) -> dict:
    tags = row.get("tags") or {}
    common = {k: tags.get(k, "") for k in COMMON_TAG_KEYS}
    source_specific = {k: v for k, v in tags.items() if k not in COMMON_TAG_KEYS}
    return {
        "qid": row["qid"],
        "question": row["question"],
        "family": row["family"],
        "shape": common["shape"] or row.get("family", ""),
        "use_case": row["use_case"],
        "scoring_mode": row["scoring_mode"],
        "gold_label": row["gold_label"],
        "options": row.get("options") or [],
        "oracle_context": row.get("oracle_context") or "",
        "source": common["source"] or "",
        "source_status": common["source_status"] or "",
        "rubric_notes": common["rubric_notes"] or "",
        "source_metadata": json.dumps(source_specific, sort_keys=True) if source_specific else "{}",
    }


def main() -> int:
    if not CARD_PATH.exists():
        print(f"ERROR: dataset card missing at {CARD_PATH}", file=sys.stderr)
        return 2

    if STAGE_DIR.exists():
        shutil.rmtree(STAGE_DIR)
    (STAGE_DIR / "data").mkdir(parents=True)

    out_path = STAGE_DIR / "data" / "train.jsonl"
    total = 0
    per_shape: dict[str, int] = {}
    with out_path.open("w") as out:
        for shape in SHAPES:
            seed = BENCH_DIR / f"seed-{shape}.jsonl"
            if not seed.exists():
                print(f"WARNING: {seed} missing, skipping", file=sys.stderr)
                continue
            n = 0
            with seed.open() as fh:
                for line in fh:
                    if not line.strip():
                        continue
                    row = json.loads(line)
                    out.write(json.dumps(flatten(row), ensure_ascii=False) + "\n")
                    n += 1
            per_shape[shape] = n
            total += n

    shutil.copy2(CARD_PATH, STAGE_DIR / "README.md")

    print(f"\nStaged: {STAGE_DIR}")
    print(f"  README.md ({CARD_PATH.stat().st_size} bytes)")
    print(f"  data/train.jsonl  ({total} rows)")
    for shape, n in per_shape.items():
        print(f"     shape={shape:<7} {n} rows")
    print()

    # Try loading via datasets.load_dataset to validate the staged tree
    print("Validation: datasets.load_dataset on the staged dir...")
    try:
        from datasets import load_dataset
    except ImportError:
        print("  (skipped — `pip install datasets` to run validation)", file=sys.stderr)
        return 0
    ds = load_dataset(str(STAGE_DIR), split="train")
    print(f"  loaded {len(ds)} rows; columns: {ds.column_names}")
    print(f"  first row qid: {ds[0]['qid']}  shape: {ds[0]['shape']}  family: {ds[0]['family']}")
    print(f"  filter D-mcq: {len(ds.filter(lambda r: r['shape'] == 'D-mcq'))} rows")
    return 0


if __name__ == "__main__":
    sys.exit(main())
