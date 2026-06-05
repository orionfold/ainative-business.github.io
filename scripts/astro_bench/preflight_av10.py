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
_CORPUS = _REPO / "evidence" / "astrodynamics" / "astro-sft-corpus.jsonl"


def load_heldout(path: Path, n: int | None) -> list[dict]:
    rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    return rows if n is None else rows[:n]


def load_fewshot(corpus_path: Path, k: int) -> list[dict]:
    """Pick ``k`` terse worked-solution exemplars from the SFT corpus.

    The conditioning probe (AV-10 follow-on): the AV-10 zero-shot read showed
    Qwen3-8B over-thinks past the budget without boxing. SFT-init conditions it to
    the terse ``<think>…</think>\\boxed{}`` format (corpus mean ~282 chars) — this
    prepends a few of those exemplars in-context as a cheap proxy for *will SFT
    fix it?* Picks the shortest completion per distinct subtopic (so the model
    sees brevity), then the ``k`` shortest overall — deterministic, no RNG. The
    corpus is held-out-disjoint by construction (RV-10), so no leakage."""
    rows = [json.loads(line) for line in corpus_path.read_text().splitlines() if line.strip()]
    by_sub: dict[str, dict] = {}
    for r in rows:
        st = r["subtopic"]
        if st not in by_sub or len(r["completion"]) < len(by_sub[st]["completion"]):
            by_sub[st] = r
    return sorted(by_sub.values(), key=lambda r: len(r["completion"]))[:k]


def build_fewshot_content(exemplars: list[dict], question_prompt: str) -> str:
    """Wrap the held-out question with terse in-context exemplars.

    Embedded as text in the user turn (not prior chat turns) so the Qwen3 chat
    template can't strip the ``<think>`` history — the whole point is to show the
    model the *brief reasoning → boxed answer* shape it should imitate."""
    parts = [
        "Here are worked examples in the required format. Reason concisely, then "
        "end with the final answer as \\boxed{value unit}.\n",
    ]
    for i, ex in enumerate(exemplars, 1):
        parts.append(f"### Example {i}\n{ex['prompt']}\n{ex['completion']}\n")
    parts.append(f"### Now solve\n{question_prompt}")
    return "\n".join(parts)


def summarize(
    results: list[dict],
    *,
    model: str,
    n_target: int,
    max_new_tokens: int,
    rel_tol: float,
    status: str,
    fewshot: int = 0,
) -> dict:
    """Build the reward-signal report over the rows scored *so far*.

    Called after every row so the cockpit reward gauge can stream live (dogfood
    AF-9 — the eval-time twin of the shipped rl_run progress strip). ``status``
    is ``"running"`` mid-run and ``"done"`` on the final write; ``scored``/
    ``total`` drive the pane's progress bar. The rates are computed over the
    rows present, so an empty ``results`` paints a clean ``0/total`` shell before
    the first (slow) generation lands. torch-free — unit-testable without a GPU.
    """
    n = len(results)
    extract_rate = sum(1 for r in results if r["bucket"] not in
                       ("no_answer", "truncated_think")) / n if n else 0.0
    boxed_rate = sum(1 for r in results if r["boxed"]) / n if n else 0.0
    reward_rate = sum(r["score"] for r in results) / n if n else 0.0
    trunc_rate = sum(1 for r in results if r["bucket"] == "truncated_think") / n if n else 0.0
    # AV-10 gate: the base CAN box (so SFT can format-condition it) AND AV-R1 is
    # not dominating at this token budget. Step-0 reward is allowed to be low.
    av_r1_clear = trunc_rate < 0.5
    gate_pass = boxed_rate > 0.0 and av_r1_clear
    return {
        "model": model, "n": n_target, "max_new_tokens": max_new_tokens,
        "rel_tol": rel_tol,
        "status": status,   # AF-9: "running" | "done"
        "scored": n,        # AF-9: rows scored so far
        "total": n_target,  # AF-9: rows in the held-out slice
        "fewshot": fewshot,  # 0 = zero-shot base read; >0 = SFT-format conditioning probe
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
    ap.add_argument("--heldout", default=str(_HELDOUT),
                    help="JSONL slice to score (default: the generalization held-out; "
                         "the AV-12 headroom gate points this at the transfer candidates)")
    ap.add_argument("--report", default=str(_REPORT))
    ap.add_argument("--fewshot", type=int, default=0,
                    help="prepend K terse SFT-corpus exemplars (conditioning probe; "
                         "0 = zero-shot base read)")
    ap.add_argument("--corpus", default=str(_CORPUS),
                    help="SFT corpus to draw --fewshot exemplars from")
    args = ap.parse_args()

    rows = load_heldout(Path(args.heldout), args.n)
    exemplars = load_fewshot(Path(args.corpus), args.fewshot) if args.fewshot > 0 else []
    mode = (f"fewshot={args.fewshot} ({','.join(e['subtopic'] for e in exemplars)})"
            if exemplars else "zero-shot")
    print(f"[av10] {len(rows)} held-out rows · model={args.model} "
          f"· max_new_tokens={args.max_new_tokens} · {mode}", flush=True)

    report_path = Path(args.report)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    # AF-9: paint a running 0/total shell before the (slow) model load + first
    # generation, so the cockpit reward gauge shows the run is live immediately.
    report_path.write_text(json.dumps(summarize(
        [], model=args.model, n_target=len(rows), max_new_tokens=args.max_new_tokens,
        rel_tol=args.rel_tol, status="running", fewshot=args.fewshot,
    ), indent=2))

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
        content = (build_fewshot_content(exemplars, row["prompt"])
                   if exemplars else row["prompt"])
        messages = [{"role": "user", "content": content}]
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
        # AF-9: heartbeat after each row → the cockpit reward gauge streams the
        # run live (scored/total bar + running rates) instead of waiting for exit.
        report_path.write_text(json.dumps(summarize(
            results, model=args.model, n_target=len(rows),
            max_new_tokens=args.max_new_tokens, rel_tol=args.rel_tol,
            status="running", fewshot=args.fewshot,
        ), indent=2))

    summary = summarize(
        results, model=args.model, n_target=len(rows),
        max_new_tokens=args.max_new_tokens, rel_tol=args.rel_tol,
        status="done", fewshot=args.fewshot,
    )
    boxed_rate = summary["boxed_rate"]
    reward_rate = summary["reward_rate_step0"]
    trunc_rate = summary["truncation_rate"]
    gate_pass = summary["gate_pass"]
    report_path.write_text(json.dumps(summary, indent=2))

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
