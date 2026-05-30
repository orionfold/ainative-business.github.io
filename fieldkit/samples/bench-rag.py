#!/usr/bin/env python3
# Copyright 2026 Manav Sehgal
# SPDX-License-Identifier: Apache-2.0
"""Offline `Bench` + `Judge` walkthrough — runs without NIM or pgvector.

Replaces the question-loop / mean-median-min-max boilerplate from
`articles/naive-rag-on-spark/evidence/benchmark.py` with one `Bench` and
one `Judge.parse()` round-trip. The "callable" is a deterministic stub
that returns a fake RAG response with `timings_ms` so the metric-extraction
path is exercised exactly the way a real `pipe.ask()` callable would
trigger it. The judge response is faked too — `Judge.parse()` is a pure
function, so we don't need a real NIM to demonstrate the parsing path.

Run:
    python samples/bench-rag.py

Wires up against a real NIM / pipeline by swapping `_fake_ask()` for
`pipe.ask` and constructing `Judge.builtin(NIMClient(...), "correctness")`.
"""

from __future__ import annotations

import json
import random

from fieldkit.eval import Bench, Judge, JudgeResult, is_refusal


QUESTIONS = [
    ("in_corpus", "Who won the 2004 US presidential election?"),
    ("in_corpus", "What did Google do in 2004 related to going public?"),
    ("in_corpus", "What happened at the 2004 Athens Olympics in swimming?"),
    ("out_of_corpus", "Who won the 2020 US presidential election?"),
    ("out_of_corpus", "What is NVIDIA DGX Spark?"),
    ("out_of_corpus", "When was Claude 4 Opus released?"),
]


def _fake_ask(item: tuple[str, str]) -> dict:
    """Deterministic stub for `Pipeline.ask` so this sample stays offline."""
    kind, q = item
    rng = random.Random(hash(q) & 0xFFFF)
    embed = round(40 + rng.random() * 10, 2)
    retrieve = round(70 + rng.random() * 20, 2)
    ttft = round(80 + rng.random() * 60, 2)
    gen = round(ttft + 350 + rng.random() * 250, 2)
    answer = (
        "The provided context does not contain the answer."
        if kind == "out_of_corpus"
        else f"(stub answer for: {q})"
    )
    return {
        "answer": answer,
        "timings_ms": {
            "embed": embed,
            "retrieve": retrieve,
            "generate_first_token": ttft,
            "generate_total": gen,
            "end_to_end": embed + retrieve + gen,
        },
    }


def main() -> int:
    bench = Bench(
        name="naive-rag-offline",
        metrics=["embed", "retrieve", "generate_first_token", "generate_total", "end_to_end"],
        metrics_key="timings_ms",
    )

    with bench:
        bench.run(_fake_ask, QUESTIONS, tag_fn=lambda item: {"kind": item[0]})

    print(bench.report())

    refusals = sum(
        1 for c in bench.calls if c.success and is_refusal(c.output["answer"])
    )
    print(f"\nrefusal rate: {refusals}/{len(bench.calls)} "
          f"({round(100 * refusals / len(bench.calls), 1)}%)")

    print("\n--- Judge.parse() examples ---")
    for raw in [
        '{"score": 4, "rationale": "close enough"}',
        '```json\n{"score": 0.5, "rationale": "partial"}\n```',
        "I cannot give a numeric score, sorry.",
    ]:
        result = Judge.parse(raw)
        print(f"  raw: {raw[:60]!r:<70}  → score={result.score}")
        assert isinstance(result, JudgeResult)

    out = bench.dump("/tmp/fieldkit-bench-rag.json")
    print(f"\nwrote {out}")
    print(f"summary keys: {list(json.loads(out.read_text())['summary'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
