"""Build a 50-row <think>-structured smoke training set from existing bench seeds.

For the Day-1 smoke test (spec §4): the point is to validate training mechanics
(R3 stack + R14 tokenizer + Layer-1 LoRA targeting), NOT reasoning quality.
Templated <think>...</think> chains are sufficient.

The W3 full-run training corpus (~25k rows) needs real Claude-synthesized chains
per spec §4 Layer 2 — that's a separate, later job.

Output schema (one row per line):
  {"text": "<full input including <think>...</think>answer>"}

Reads from: /home/nvidia/data/eval-benches/patent-strategist/seed-*.jsonl
Writes to:  /home/nvidia/data/corpus/patent-smoke-50.jsonl
"""
from __future__ import annotations

import json
import random
from pathlib import Path
from typing import Iterable

BENCH_DIR = Path("/home/nvidia/data/eval-benches/patent-strategist")
OUT_PATH = Path("/home/nvidia/data/corpus/patent-smoke-50.jsonl")


def fmt_mcq_chain(question: str, options: list[str], gold_letter: str) -> str:
    """Build a templated <think> chain for an MCQ row.

    Walks through the options, identifies the gold, justifies it. Templated
    but well-structured — sufficient to validate training mechanics.
    """
    letters = ["A", "B", "C", "D"]
    opts = "\n".join(f"({letters[i]}) {o}" for i, o in enumerate(options))
    chain_lines = [
        "Let me analyze each option against the question.",
        "",
        f"The question asks about a specific MPEP provision or patent-law doctrine.",
    ]
    for letter, opt in zip(letters, options):
        if letter == gold_letter:
            chain_lines.append(f"Option {letter}: {opt[:120]} — this matches the rule stated in the controlling MPEP provision.")
        else:
            chain_lines.append(f"Option {letter}: {opt[:120]} — does not align with the controlling MPEP provision.")
    chain_lines.append("")
    chain_lines.append(f"Therefore the correct answer is {gold_letter}.")
    chain = "\n".join(chain_lines)
    return (
        f"{question}\n\n{opts}\n\n"
        f"<think>\n{chain}\n</think>\n"
        f"Answer: {gold_letter}"
    )


def fmt_irac_chain(question: str, gold_label: str) -> str:
    """Templated IRAC <think> chain — Issue, Rule, Application, Conclusion structure."""
    # Try to detect existing IRAC structure in gold_label; otherwise wrap minimally
    chain = (
        "Step 1: identify the legal issue raised by the fact pattern.\n"
        "Step 2: state the controlling rule from the MPEP / case law.\n"
        "Step 3: apply the rule to the facts.\n"
        "Step 4: state the conclusion."
    )
    return (
        f"{question}\n\n"
        f"<think>\n{chain}\n</think>\n"
        f"{gold_label}"
    )


def fmt_generic_chain(question: str, gold_label: str) -> str:
    """Templated generic <think> chain for free-text rows (A, B, C, E)."""
    chain = (
        "Step 1: read the question carefully and identify the patent-law concept involved.\n"
        "Step 2: recall the controlling MPEP provisions or claim-construction doctrine.\n"
        "Step 3: apply the doctrine to draft the answer."
    )
    return (
        f"{question}\n\n"
        f"<think>\n{chain}\n</think>\n"
        f"{gold_label}"
    )


def build_smoke_set() -> list[dict]:
    """Sample 50 rows across the bench's seven shape files, with <think>-wrapping."""
    rng = random.Random(20260517)
    rows: list[dict] = []

    # Take 20 D-mcq (heaviest formal structure) + 30 from other shapes
    plan = {
        "seed-D-mcq.jsonl": 20,
        "seed-D-irac.jsonl": 10,
        "seed-D-oa.jsonl": 5,
        "seed-A.jsonl": 8,
        "seed-B.jsonl": 4,
        "seed-C.jsonl": 2,
        "seed-E.jsonl": 1,
    }

    for fname, n in plan.items():
        path = BENCH_DIR / fname
        if not path.exists():
            print(f"  WARNING: {path} not found, skipping {n} rows")
            continue
        with open(path) as fh:
            raw = [json.loads(line) for line in fh if line.strip()]
        rng.shuffle(raw)
        for r in raw[:n]:
            if fname == "seed-D-mcq.jsonl":
                if not r.get("options") or len(r.get("options", [])) < 4:
                    continue  # skip malformed MCQ rows
                text = fmt_mcq_chain(r["question"], r["options"], r["gold_label"])
            elif fname == "seed-D-irac.jsonl":
                text = fmt_irac_chain(r["question"], r["gold_label"])
            else:
                text = fmt_generic_chain(r["question"], r["gold_label"])
            rows.append({
                "text": text,
                "source_qid": r["qid"],
                "family": r.get("family"),
                "use_case": r.get("use_case"),
            })

    # Pad to exactly 50 if any shape file was short
    while len(rows) < 50:
        # repeat the first D-mcq row (smoke set; over-counting is fine)
        rows.append(rows[0])
    rows = rows[:50]
    return rows


def main() -> int:
    rows = build_smoke_set()
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_PATH, "w") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")
    print(f"wrote {len(rows)} rows -> {OUT_PATH}")

    # Quick QA: count <think> presence
    n_with_think = sum(1 for r in rows if "<think>" in r["text"] and "</think>" in r["text"])
    print(f"  <think>...</think>: {n_with_think}/{len(rows)} rows")

    # Quick QA: family breakdown
    from collections import Counter
    fams = Counter(r.get("family") for r in rows)
    print(f"  family breakdown: {dict(fams)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
