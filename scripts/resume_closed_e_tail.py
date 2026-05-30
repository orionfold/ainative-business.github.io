#!/usr/bin/env python3
"""Resume the 25 missing E-shape rows in the session-27 closed-book run.

The power-outage at ~19:53 truncated `predictions.jsonl` mid-write while the
closed-book sweep was processing the last 25 rows of seed-E.jsonl. The
corrupted line was stripped (175 good rows remain). This helper re-runs the
exact missing qids against the same llama-server endpoint and appends them
back to the same `predictions.jsonl`, then triggers a rescore.

E rows have no scorer in v1 (judge_rubric deferred to W4), so this only
exists to keep the closed-book run-dir at 200-row parity with the retrieval
and oracle runs. Article numbers do not depend on it.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

# Import the driver's primitives so the prompt + chat path matches exactly.
sys.path.insert(0, str(Path(__file__).parent))
from run_rag_baseline import (  # type: ignore[import-not-found]
    LlamaClient,
    SYSTEM_PROMPT,
    build_user_prompt,
    score_prediction,
)

RUN_DIR = Path("/home/nvidia/ainative-business.github.io/evidence/patent-strategist/baseline-runs/20260517-170410-closed-b8cfe9")
BENCH_DIR = Path("/home/nvidia/data/eval-benches/patent-strategist")


def main() -> int:
    pred_path = RUN_DIR / "predictions.jsonl"
    config = json.loads((RUN_DIR / "config.json").read_text())

    # Discover done qids
    done_qids: set[str] = set()
    with pred_path.open() as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            done_qids.add(json.loads(line)["qid"])
    print(f"[resume] {len(done_qids)} qids already in predictions.jsonl")

    # Find missing rows by walking all bench files in original order
    missing: list[dict] = []
    for shape in ("A", "B", "C", "D-mcq", "D-oa", "D-irac", "E"):
        path = BENCH_DIR / f"seed-{shape}.jsonl"
        if not path.exists():
            continue
        with path.open() as f:
            for line in f:
                row = json.loads(line)
                if row["qid"] not in done_qids:
                    row["_shape"] = shape  # carry shape into runner
                    missing.append(row)
    print(f"[resume] {len(missing)} rows to run")
    if not missing:
        print("[resume] nothing to do")
        return 0

    gen = config["generator"]
    client = LlamaClient(
        url=gen["url"],
        model=gen["model"],
        temperature=float(gen["temperature"]),
        max_tokens=int(gen["max_tokens"]),
        timeout_s=float(gen["timeout_s"]),
    )
    if not client.ping():
        sys.exit(f"[resume] llama-server unreachable at {gen['url']}")

    appended = 0
    started = time.perf_counter()
    with pred_path.open("a") as out_f:
        for i, row in enumerate(missing, 1):
            shape = row["_shape"]
            question = row.get("question", "")
            gold = row.get("gold_label", "")
            qid = row.get("qid", "?")
            options = row.get("options") or None
            prompt = build_user_prompt(question, context=None, options=options)  # closed mode

            t0 = time.perf_counter()
            prediction = ""
            try:
                prediction, _ = client.chat(SYSTEM_PROMPT, prompt)
            except Exception as e:  # noqa: BLE001
                print(f"[resume] {qid} inference fail: {type(e).__name__}: {e}", flush=True)
            latency_s = time.perf_counter() - t0

            score = score_prediction(shape, prediction, gold) if prediction else None
            out_row = {
                "qid": qid,
                "shape": shape,
                "family": row.get("family"),
                "use_case": row.get("use_case"),
                "mode": "closed",
                "prompt": None,
                "prediction": prediction or None,
                "score": score,
                "gold_label": gold,
                "retrieved_chunks": [],
                "latency_s": round(latency_s, 3),
            }
            out_f.write(json.dumps(out_row, ensure_ascii=False) + "\n")
            out_f.flush()
            appended += 1
            print(f"[resume] {i:>3}/{len(missing)}  {qid}  {latency_s:.1f}s  pred_len={len(prediction)}", flush=True)

    wall = time.perf_counter() - started
    print(f"[resume] appended {appended} rows in {wall:.1f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
