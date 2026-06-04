# Copyright 2026 Manav Sehgal
# SPDX-License-Identifier: Apache-2.0
"""preflight_av10.py — the AV-10 cheap baseline gate for the astrodynamics vertical.

Scores a held-out slice on the **FP base model** (`Qwen/Qwen3-8B`) *before* the
multi-hour NeMo SFT-init + RLVR run, per `feedback_preflight_bench_before_quant`.
The spec (`_SPECS/astrodynamics-vertical-v1.md` AV-10) sanctions either
`fieldkit.training.ReasoningProbe` *or* transformers — `ReasoningProbe` grades
think-*presence*, not numeric correctness, so this uses transformers directly and
reuses the local `astro_numeric_match` reward.

What it answers (and why each matters):
  * **extract-rate** — fraction of completions that emit a parseable ``\\boxed{}``.
    This is the AV-R1 tripwire: if it's ~0 with a generous ``max_new_tokens`` the
    base can't be format-conditioned and the whole RLVR run would score 0 silently.
  * **reward-rate** — fraction scoring 1.0 via `astro_numeric_match` (±2%). This is
    the **step-0 held-out baseline** — the zero of the `fieldkit.lineage` delta chart.
  * **truncation-rate** — completions where ``<think>`` opened, hit the token cap, and
    never closed/boxed. A high value here means *raise* ``max_new_tokens`` (AV-6), not
    that the base is hopeless. The whole point of AV-10 is to catch this in minutes.

Run inside the NeMo container (`/opt/venv` has torch+transformers, GB10-correct);
the astro_bench dir is stdlib-only so `verifier`/`units` import directly.

    python scripts/astro_bench/preflight_av10.py --n 8 --max-new-tokens 2560

Writes a JSON report to evidence/astrodynamics/av10-preflight.json.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

# astro_bench dir on path so the stdlib verifier/units import cleanly.
_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from verifier import astro_numeric_match, extract_boxed  # noqa: E402

_REPO = _HERE.parent.parent
_HELDOUT = _REPO / "evidence" / "astrodynamics" / "astro-bench-v0.1.heldout.jsonl"
_REPORT = _REPO / "evidence" / "astrodynamics" / "av10-preflight.json"


def load_heldout(path: Path, n: int | None) -> list[dict]:
    rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    return rows if n is None else rows[:n]


def classify(completion: str, score: float) -> str:
    """Bucket a completion for the AV-R1 readout."""
    boxed = extract_boxed(completion)
    has_box = boxed is not None and boxed.strip() != ""
    if has_box:
        return "correct" if score >= 1.0 else "boxed_wrong"
    opened = "<think>" in completion
    closed = "</think>" in completion
    if opened and not closed:
        return "truncated_think"  # AV-R1 firing — raise max_new_tokens
    return "no_answer"  # closed (or no think) but never boxed — format gap, SFT fixes


def main() -> int:
    ap = argparse.ArgumentParser(description="AV-10 preflight baseline on Qwen3-8B FP.")
    ap.add_argument("--model", default="Qwen/Qwen3-8B")
    ap.add_argument("--n", type=int, default=8, help="held-out rows to score (spec: ~5)")
    ap.add_argument("--max-new-tokens", type=int, default=4096, help="AV-6: >=2048")
    ap.add_argument("--rel-tol", type=float, default=0.02)
    ap.add_argument("--seed", type=int, default=0, help="reproducible sampling")
    ap.add_argument("--report", default=str(_REPORT))
    args = ap.parse_args()

    rows = load_heldout(_HELDOUT, args.n)
    print(f"[av10] {len(rows)} held-out rows · model={args.model} "
          f"· max_new_tokens={args.max_new_tokens}", flush=True)

    import torch  # lazy — only needed for the live run
    from transformers import AutoModelForCausalLM, AutoTokenizer

    t0 = time.time()
    tok = AutoTokenizer.from_pretrained(args.model)
    try:  # transformers >=5 renamed torch_dtype -> dtype
        model = AutoModelForCausalLM.from_pretrained(
            args.model, dtype=torch.bfloat16, device_map="cuda"
        )
    except TypeError:
        model = AutoModelForCausalLM.from_pretrained(
            args.model, torch_dtype=torch.bfloat16, device_map="cuda"
        )
    model.eval()
    print(f"[av10] model loaded in {time.time() - t0:.0f}s", flush=True)

    results = []
    for i, row in enumerate(rows):
        messages = [{"role": "user", "content": row["prompt"]}]
        text = tok.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=True,
            enable_thinking=True,  # Qwen3 native thinking mode (AV-6 — keep it on)
        )
        inputs = tok(text, return_tensors="pt").to(model.device)
        g0 = time.time()
        # Qwen3 thinking-mode sampling (model card): temp 0.6 / top_p 0.95 /
        # top_k 20. Greedy (do_sample=False) is explicitly warned against — it
        # loops endlessly inside <think> and never closes, faking AV-R1 truncation.
        torch.manual_seed(args.seed)
        with torch.no_grad():
            out = model.generate(
                **inputs, max_new_tokens=args.max_new_tokens,
                do_sample=True, temperature=0.6, top_p=0.95, top_k=20,
                pad_token_id=tok.eos_token_id,
            )
        completion = tok.decode(out[0][inputs["input_ids"].shape[1]:],
                                skip_special_tokens=True)
        score = astro_numeric_match(completion, row["answer"], rel_tolerance=args.rel_tol)
        bucket = classify(completion, score)
        boxed = extract_boxed(completion)
        results.append({
            "task_id": row["task_id"], "subtopic": row["subtopic"], "tier": row["tier"],
            "answer": row["answer"], "score": score, "bucket": bucket,
            "boxed": (boxed or "").strip()[:80],
            "n_chars": len(completion), "wall_s": round(time.time() - g0, 1),
        })
        print(f"[av10] {i+1}/{len(rows)} {row['subtopic']:<28} "
              f"{bucket:<16} score={score:.0f} boxed={results[-1]['boxed'][:32]!r}",
              flush=True)

    n = len(results)
    extract_rate = sum(1 for r in results if r["bucket"] != "no_answer"
                       and r["bucket"] != "truncated_think") / n if n else 0.0
    boxed_rate = sum(1 for r in results if r["boxed"]) / n if n else 0.0
    reward_rate = sum(r["score"] for r in results) / n if n else 0.0
    trunc_rate = sum(1 for r in results if r["bucket"] == "truncated_think") / n if n else 0.0

    # AV-10 gate: the base CAN box (so SFT can format-condition it) AND AV-R1 is
    # not dominating at this token budget. Step-0 reward is allowed to be low.
    av_r1_clear = trunc_rate < 0.5
    gate_pass = boxed_rate > 0.0 and av_r1_clear

    summary = {
        "model": args.model, "n": n, "max_new_tokens": args.max_new_tokens,
        "rel_tol": args.rel_tol,
        "boxed_rate": round(boxed_rate, 4),
        "extract_rate": round(extract_rate, 4),
        "reward_rate_step0": round(reward_rate, 4),
        "truncation_rate": round(trunc_rate, 4),
        "av_r1_clear": av_r1_clear,
        "gate_pass": gate_pass,
        "buckets": {b: sum(1 for r in results if r["bucket"] == b)
                    for b in ("correct", "boxed_wrong", "no_answer", "truncated_think")},
        "rows": results,
    }
    Path(args.report).write_text(json.dumps(summary, indent=2))

    print("\n===== AV-10 PREFLIGHT =====", flush=True)
    print(f"boxed_rate       {boxed_rate:.2%}  (does the base emit \\boxed{{}} at all?)")
    print(f"reward_rate@step0 {reward_rate:.2%}  (zero-shot held-out baseline)")
    print(f"truncation_rate  {trunc_rate:.2%}  (AV-R1 — raise max_new_tokens if high)")
    print(f"buckets          {summary['buckets']}")
    print(f"GATE             {'PASS' if gate_pass else 'HOLD'} "
          f"(boxed>0 ∧ trunc<50%) → report: {args.report}", flush=True)
    return 0 if gate_pass else 2


if __name__ == "__main__":
    raise SystemExit(main())
