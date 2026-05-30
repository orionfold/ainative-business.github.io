#!/usr/bin/env python3
"""Rescore an existing baseline-run predictions.jsonl in place.

Use after a fieldkit scorer bug-fix: replays `score_prediction` against
every row, writes back atomically, and regenerates scores.json. Inference
predictions themselves are untouched.

Usage
-----
    python scripts/rescore_predictions.py /path/to/run-dir
"""
from __future__ import annotations
import json, os, sys
from pathlib import Path

def score_prediction(shape, prediction, gold_label):
    SUPP = {"A", "B", "D-mcq", "D-oa", "D-irac"}
    if shape not in SUPP:
        return None
    from fieldkit.eval.vertical import PATENT_STRATEGIST_SCORER_FNS
    fn = PATENT_STRATEGIST_SCORER_FNS.get(shape)
    if fn is None:
        return None
    try:
        return float(fn(prediction, gold_label))
    except Exception as e:  # noqa: BLE001
        print(f"[scorer] {shape} fail: {type(e).__name__}", flush=True)
        return None

def main():
    run = Path(sys.argv[1])
    pred_path = run / "predictions.jsonl"
    scores_path = run / "scores.json"
    if not pred_path.exists():
        sys.exit(f"no predictions.jsonl at {pred_path}")
    rows = [json.loads(l) for l in pred_path.read_text().splitlines() if l.strip()]
    changed = 0
    for r in rows:
        old = r.get("score")
        new = score_prediction(r["shape"], r.get("prediction") or "", r.get("gold_label", ""))
        if old != new:
            changed += 1
        r["score"] = new
    tmp = pred_path.with_suffix(".jsonl.tmp")
    with tmp.open("w") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    os.replace(tmp, pred_path)
    print(f"[rescore] {changed}/{len(rows)} rows updated")

    # Regenerate scores.json
    from collections import defaultdict
    by_shape = defaultdict(list); by_uc = defaultdict(list); skipped = defaultdict(int)
    for r in rows:
        s = r.get("shape", "?"); sc = r.get("score")
        if sc is None:
            skipped[s] += 1; continue
        by_shape[s].append(float(sc))
        by_uc[f"{s}/{r.get('use_case') or '?'}"].append(float(sc))
    mean = lambda xs: round(sum(xs)/len(xs), 4) if xs else None
    summary = {
        "per_shape": {k: {"mean": mean(v), "n": len(v)} for k, v in by_shape.items()},
        "per_use_case": {k: {"mean": mean(v), "n": len(v)} for k, v in by_uc.items()},
        "skipped_by_shape": dict(skipped),
        "overall_mean": mean([v for xs in by_shape.values() for v in xs]),
        "overall_n": sum(len(xs) for xs in by_shape.values()),
        "rescored": True,
    }
    # Preserve prior wall/inference if present
    if scores_path.exists():
        old = json.loads(scores_path.read_text())
        for k in ("wall_seconds", "inference_calls", "inference_seconds", "error_count", "errors"):
            if k in old:
                summary[k] = old[k]
    scores_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False))
    print(f"[rescore] wrote {scores_path}")
    for s, x in sorted(summary["per_shape"].items()):
        print(f"  {s:8} mean={x['mean']}  n={x['n']}")
    print(f"  overall mean: {summary['overall_mean']}  (n={summary['overall_n']})")

if __name__ == "__main__":
    main()
