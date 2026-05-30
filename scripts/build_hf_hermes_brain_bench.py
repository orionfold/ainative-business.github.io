"""Build the HF-uploadable staging dir for Orionfold/hermes-brain-bench-v0.1.

Consolidates the live bench artifacts under
`articles/field-fixing-the-hermes-harness-on-spark/evidence/` into a single
HF-shaped directory:

  /tmp/hf-stage/hermes-brain-bench-v0.1/
    README.md                  (copied from dataset-cards/hermes-brain-bench-v0.1/)
    data/train.jsonl           (10 prompts, one per line; HF datasets-loadable)
    ground_truth.json          ({{placeholder}} substitution map; from hermes_brain_eval._subst_map)
    scratch/                   (bytes-deterministic seed fixtures, regenerated via seed_scratch())
      facts.txt
      notes/budget-q3.txt
      notes/roadmap.txt
      notes/standup-2026-05-20.txt
      numbers.csv
      inventory.csv
      prices.csv
      service.conf
    results/
      nim-incumbent.json
      qwen3-30b-moe-llamacpp-q4km.json
      qwen3-30b-moe-vllm-fp8.json
      summary.md               (human-readable cross-lane rank — same shape as hermes_brain_report.md)

Modeled on `scripts/build_hf_dataset_bench.py`. Re-run any time the source
prompt suite, scratch fixtures, results JSON, or dataset card change.

Usage:
  python scripts/build_hf_hermes_brain_bench.py
"""
from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
EVIDENCE_DIR = REPO_ROOT / "articles" / "picking-the-hermes-brain-on-spark" / "evidence"
PROMPTS_FILE = EVIDENCE_DIR / "hermes_brain_eval_prompts.json"
RESULTS_FILE = EVIDENCE_DIR / "hermes_brain_results.json"
RUNNER_FILE = EVIDENCE_DIR / "hermes_brain_eval.py"
CARD_PATH = REPO_ROOT / "dataset-cards" / "hermes-brain-bench-v0.1" / "README.md"
STAGE_DIR = Path("/tmp/hf-stage/hermes-brain-bench-v0.1")

LANES = (
    "nim-incumbent",
    "qwen3-30b-moe-llamacpp-q4km",
    "qwen3-30b-moe-vllm-fp8",
)


def load_ground_truth_from_runner() -> dict[str, str]:
    """Single source of truth: import the runner's `_subst_map` directly so the
    staged ground_truth.json can never drift from the runner that scored the
    reference lanes. Cheaper than parsing the runner's literals."""
    sys.path.insert(0, str(EVIDENCE_DIR))
    try:
        import hermes_brain_eval  # type: ignore[import-not-found]
        return hermes_brain_eval._subst_map()
    finally:
        sys.path.pop(0)


def seed_scratch_into(target: Path) -> None:
    """Re-run the runner's `seed_scratch()` against a target dir. The runner
    writes to its own SCRATCH constant, so we monkey-patch it for this build.
    This guarantees the staged scratch is byte-identical to the scored scratch."""
    sys.path.insert(0, str(EVIDENCE_DIR))
    try:
        import hermes_brain_eval  # type: ignore[import-not-found]
        original = hermes_brain_eval.SCRATCH
        hermes_brain_eval.SCRATCH = target
        try:
            hermes_brain_eval.seed_scratch()
        finally:
            hermes_brain_eval.SCRATCH = original
    finally:
        sys.path.pop(0)


def flatten_prompt(p: dict) -> dict:
    """Pass-through with stable column order — every prompt has the same keys."""
    return {
        "id": p["id"],
        "category": p.get("category", ""),
        "core": bool(p.get("core", False)),
        "conditional": p.get("conditional"),
        "prompt": p["prompt"],
        "expect_tool_any": list(p.get("expect_tool_any", [])),
        "check": p.get("check", {}),
        "vibe": bool(p.get("vibe", False)),
        "note": p.get("note", ""),
    }


def write_prompts(stage: Path) -> int:
    (stage / "data").mkdir(parents=True, exist_ok=True)
    suite = json.loads(PROMPTS_FILE.read_text())
    out_path = stage / "data" / "train.jsonl"
    n = 0
    with out_path.open("w") as out:
        for p in suite["prompts"]:
            out.write(json.dumps(flatten_prompt(p), ensure_ascii=False) + "\n")
            n += 1
    return n


def write_ground_truth(stage: Path) -> dict[str, str]:
    gt = load_ground_truth_from_runner()
    (stage / "ground_truth.json").write_text(
        json.dumps(gt, indent=2, sort_keys=True) + "\n"
    )
    return gt


def write_results(stage: Path) -> dict:
    """Split the on-disk results JSON into per-lane files + render summary.md.
    Preserves the full `BrainScorecard` shape (per-prompt attempts, telemetry).
    """
    (stage / "results").mkdir(parents=True, exist_ok=True)
    results = json.loads(RESULTS_FILE.read_text())
    models = results.get("models", {})
    missing = [lane for lane in LANES if lane not in models]
    if missing:
        raise SystemExit(f"ERROR: results JSON missing lanes: {missing}")
    for lane in LANES:
        (stage / "results" / f"{lane}.json").write_text(
            json.dumps(models[lane], indent=2, ensure_ascii=False) + "\n"
        )
    (stage / "results" / "summary.md").write_text(render_summary(results))
    return results


def render_summary(results: dict) -> str:
    """Human-readable cross-lane rank table. Same shape as the article's
    `hermes_brain_report.md` but trimmed to the columns useful when picking a
    lane (no per-prompt detail — that's in the per-lane JSON)."""
    models = results.get("models", {})

    def _hon(m):
        h = m.get("honesty_pass_rate")
        return 1.0 if h is None else h

    ranked = sorted(
        models.values(),
        key=lambda m: (
            _hon(m) >= 0.5,
            m.get("core_pass_rate", 0.0),
            m.get("consistency", 0.0),
            -m.get("runaway_rate", 0.0),
        ),
        reverse=True,
    )
    out: list[str] = [
        "# Hermes Brain Bench v0.1 — reference lane scores",
        "",
        "Three local serving lanes scored on the v0.1 suite under N=5 attempts",
        "per prompt, on a DGX Spark GB10 (128 GB unified memory).",
        "",
        "Rank key: honesty-as-a-gate → mean core pass_rate → consistency → fewer",
        "runaways → tokens-per-second tiebreaker.",
        "",
        "| Rank | Lane | core_pass | pass_rate | consistency | runaway | tok/s | peak unified |",
        "|---:|---|:---:|---:|---:|---:|---:|---:|",
    ]
    for i, m in enumerate(ranked, 1):
        unified_peak = (m.get("telemetry") or {}).get("unified_used_gb_max")
        unified_str = f"{unified_peak:.1f} GB" if unified_peak else "—"
        out.append(
            f"| {i} | `{m['label']}` "
            f"| {m['core_pass']}/{m['core_n']} "
            f"| {m['core_pass_rate']:.0%} "
            f"| {m['consistency']:.0%} "
            f"| {m['runaway_rate']:.0%} "
            f"| {m['tokens_per_sec']:.1f} "
            f"| {unified_str} |"
        )

    out += [
        "",
        "## Per-prompt pass rates",
        "",
        "Pass rate = fraction of N attempts whose deterministic check passed.",
        "",
    ]
    prompt_ids: list[str] = []
    for m in models.values():
        for ps in m.get("per_prompt", []):
            if "skipped" in ps:
                continue
            if ps["id"] not in prompt_ids:
                prompt_ids.append(ps["id"])
    header = "| Prompt | " + " | ".join(f"`{m['label']}`" for m in ranked) + " |"
    out.append(header)
    out.append("|---|" + "|".join([":---:" for _ in ranked]) + "|")
    for pid in prompt_ids:
        row_cells = [f"`{pid}`"]
        for m in ranked:
            ps = next(
                (p for p in m.get("per_prompt", []) if p.get("id") == pid), None
            )
            if not ps or "skipped" in ps:
                row_cells.append("—")
            else:
                row_cells.append(f"{ps['pass_rate']:.0%}")
        out.append("| " + " | ".join(row_cells) + " |")

    out += [
        "",
        "## Telemetry",
        "",
        "| Lane | GPU% mean | GPU% max | peak unified | peak temp |",
        "|---|---:|---:|---:|---:|",
    ]
    for m in ranked:
        t = m.get("telemetry") or {}
        out.append(
            f"| `{m['label']}` "
            f"| {t.get('gpu_util_mean', '—'):.0f}% "
            f"| {t.get('gpu_util_max', '—'):.0f}% "
            f"| {t.get('unified_used_gb_max', 0):.1f} GB "
            f"| {t.get('gpu_temp_c_max', 0):.0f} °C |"
        )

    out += [
        "",
        "## Latency",
        "",
        "| Lane | wall mean | p50 | p95 | max |",
        "|---|---:|---:|---:|---:|",
    ]
    for m in ranked:
        lat = m.get("latency") or {}
        out.append(
            f"| `{m['label']}` "
            f"| {lat.get('mean_s', 0):.1f} s "
            f"| {lat.get('p50_s', 0):.1f} s "
            f"| {lat.get('p95_s', 0):.1f} s "
            f"| {lat.get('max_s', 0):.1f} s |"
        )

    out.append("")
    return "\n".join(out) + "\n"


def main() -> int:
    if not PROMPTS_FILE.exists():
        print(f"ERROR: prompts file missing at {PROMPTS_FILE}", file=sys.stderr)
        return 2
    if not RESULTS_FILE.exists():
        print(f"ERROR: results file missing at {RESULTS_FILE}", file=sys.stderr)
        return 2
    if not RUNNER_FILE.exists():
        print(f"ERROR: runner file missing at {RUNNER_FILE}", file=sys.stderr)
        return 2
    if not CARD_PATH.exists():
        print(f"ERROR: dataset card missing at {CARD_PATH}", file=sys.stderr)
        return 2

    if STAGE_DIR.exists():
        shutil.rmtree(STAGE_DIR)
    STAGE_DIR.mkdir(parents=True)

    # 1. README (dataset card)
    shutil.copy2(CARD_PATH, STAGE_DIR / "README.md")

    # 2. data/train.jsonl
    n_prompts = write_prompts(STAGE_DIR)

    # 3. ground_truth.json — pulled from the runner's _subst_map
    gt = write_ground_truth(STAGE_DIR)

    # 4. scratch/ — bytes-identical to what the lanes saw
    scratch_dir = STAGE_DIR / "scratch"
    scratch_dir.mkdir()
    seed_scratch_into(scratch_dir)

    # 5. results/ — per-lane scorecards + cross-lane summary
    results = write_results(STAGE_DIR)

    # Validation summary
    print(f"\nStaged: {STAGE_DIR}")
    print(f"  README.md ({CARD_PATH.stat().st_size:,} bytes)")
    print(f"  data/train.jsonl  ({n_prompts} prompts)")
    print(f"  ground_truth.json  ({len(gt)} substitutions)")
    print("  scratch/:")
    for p in sorted((STAGE_DIR / "scratch").rglob("*")):
        if p.is_file():
            print(f"    {p.relative_to(scratch_dir)}  ({p.stat().st_size:,} bytes)")
    print("  results/:")
    for p in sorted((STAGE_DIR / "results").rglob("*")):
        if p.is_file():
            print(f"    {p.relative_to(STAGE_DIR / 'results')}  ({p.stat().st_size:,} bytes)")

    # Try datasets.load_dataset to confirm the staged tree parses
    print("\nValidation: datasets.load_dataset on the staged dir...")
    try:
        from datasets import load_dataset
    except ImportError:
        print("  (skipped — `pip install datasets` to run validation)", file=sys.stderr)
        return 0
    ds = load_dataset(str(STAGE_DIR), split="train")
    print(f"  loaded {len(ds)} rows; columns: {ds.column_names}")
    print(f"  first row: id={ds[0]['id']}  core={ds[0]['core']}")
    print(f"  core-only: {len(ds.filter(lambda r: r['core']))} rows")
    print(f"  with conditional: "
          f"{len(ds.filter(lambda r: r['conditional'] is not None))} rows")
    return 0


if __name__ == "__main__":
    sys.exit(main())
