"""Compare two reasoning-preservation probe runs against spec §4 Layer 5 thresholds.

Pass thresholds (relative to baseline):
  think_presence_rate   ≥ 90%
  think_token_length    ≥ 75%
  think_quality_score   ≥ 80%

Usage:
  python scripts/compare_probes.py probes/baseline.json probes/smoke-step200.json
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

THRESHOLDS = {
    "think_presence_rate": 0.90,
    "think_token_length": 0.75,
    "think_quality_score": 0.80,
}


def fmt(v, n=4):
    if v is None:
        return "n/a"
    return f"{v:.{n}f}" if isinstance(v, float) else str(v)


def check(baseline_v, current_v, threshold_ratio):
    """Returns (status, ratio) where status is PASS/FAIL/skip."""
    if baseline_v is None or current_v is None:
        return "skip", None
    if baseline_v == 0:
        return "skip", None
    ratio = current_v / baseline_v
    return ("PASS" if ratio >= threshold_ratio else "FAIL"), ratio


def main() -> int:
    if len(sys.argv) != 3:
        print(__doc__, file=sys.stderr)
        return 2
    baseline = json.loads(Path(sys.argv[1]).read_text())
    current = json.loads(Path(sys.argv[2]).read_text())

    print(f"baseline: {baseline['model']}  ({baseline['n_probe']} rows)")
    print(f"current:  {current['model']}  step={current.get('step', 'n/a')}  lora={current.get('lora_path', 'n/a')}  ({current['n_probe']} rows)")
    print()

    all_pass = True
    print(f"{'metric':<26} {'baseline':>10}  {'current':>10}  {'ratio':>8}  {'thresh':>8}  status")
    print("-" * 80)
    for metric, threshold in THRESHOLDS.items():
        bv = baseline["overall"].get(metric)
        cv = current["overall"].get(metric)
        status, ratio = check(bv, cv, threshold)
        if status == "FAIL":
            all_pass = False
        print(f"{metric:<26} {fmt(bv):>10}  {fmt(cv):>10}  "
              f"{fmt(ratio, 3) if ratio else 'n/a':>8}  ≥{threshold:>6.0%}  {status}")

    print()
    print("Per-category breakdown:")
    cats = sorted(set(baseline["by_category"].keys()) | set(current["by_category"].keys()))
    for cat in cats:
        b = baseline["by_category"].get(cat, {})
        c = current["by_category"].get(cat, {})
        print(f"  {cat:<22} baseline presence={fmt(b.get('think_presence_rate'))}  "
              f"current={fmt(c.get('think_presence_rate'))}")

    print()
    if all_pass:
        print("OVERALL: PASS — spec §4 Layer 5 thresholds met. Safe to proceed.")
        return 0
    else:
        print("OVERALL: FAIL — spec §4 Layer 5 thresholds not met. Revert to last-good checkpoint.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
