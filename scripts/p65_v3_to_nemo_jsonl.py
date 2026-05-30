"""Reshape v3 corpus into the {input, output} JSONL schema NeMo Framework
SFT expects.

Source:  /home/nvidia/data/aifn-corpus-v3/v3_full_5000.jsonl
         (has prompt, chain, answer, response columns; row_idx, family)

Writes (90/10 train/val split, deterministic by row_idx):
  /home/nvidia/data/aifn-train-lora/p65-nemo/dataset/training.jsonl
  /home/nvidia/data/aifn-train-lora/p65-nemo/dataset/validation.jsonl

Schema per row (matches `_preprocess` in megatron.bridge.data.datasets.utils):
  {"input": "<R1 chat-template user turn>",
   "output": "<think>chain</think>answer<eos>"}

Loss computation matches Unsloth's all-token training:
   answer_only_loss=False  set in recipe → loss on every token of input+output.
"""
from __future__ import annotations

import json
import random
import sys
from pathlib import Path

SRC = Path("/home/nvidia/data/aifn-corpus-v3/v3_full_5000.jsonl")
OUT_DIR = Path("/home/nvidia/data/aifn-train-lora/p65-nemo/dataset")
SEED = 42
VAL_FRAC = 0.10

BOS = "<｜begin▁of▁sentence｜>"
EOS = "<｜end▁of▁sentence｜>"
USER_TAG = "<｜User｜>"
ASSISTANT_TAG = "<｜Assistant｜>"


def main() -> int:
    if not SRC.exists():
        print(f"ERROR: {SRC} missing", file=sys.stderr)
        return 2

    rows = [json.loads(line) for line in SRC.open() if line.strip()]
    out_rows: list[dict] = []
    skipped = 0
    for r in rows:
        prompt = r.get("prompt", "")
        response = r.get("response", "")
        if not prompt or not response:
            skipped += 1
            continue
        if "<think>" not in response or "</think>" not in response:
            print(f"ERROR: row {r.get('row_idx')} missing <think> markers", file=sys.stderr)
            return 3
        input_str = f"{BOS}{USER_TAG}{prompt}{ASSISTANT_TAG}"
        output_str = f"{response}{EOS}"
        out_rows.append({
            "input": input_str,
            "output": output_str,
            "row_idx": r["row_idx"],
            "family": r["family"],
        })

    rng = random.Random(SEED)
    rng.shuffle(out_rows)
    n_val = max(1, int(len(out_rows) * VAL_FRAC))
    val_rows = out_rows[:n_val]
    train_rows = out_rows[n_val:]

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    with (OUT_DIR / "training.jsonl").open("w") as fh:
        for r in train_rows:
            fh.write(json.dumps(r) + "\n")
    with (OUT_DIR / "validation.jsonl").open("w") as fh:
        for r in val_rows:
            fh.write(json.dumps(r) + "\n")

    lens_in = [len(r["input"]) for r in out_rows]
    lens_out = [len(r["output"]) for r in out_rows]
    print(f"wrote training.jsonl  ({len(train_rows)} rows) + validation.jsonl ({len(val_rows)} rows)  to {OUT_DIR}")
    print(f"   skipped: {skipped}")
    print(f"   input  chars  min={min(lens_in)} mean={sum(lens_in)//len(lens_in)} max={max(lens_in)}")
    print(f"   output chars  min={min(lens_out)} mean={sum(lens_out)//len(lens_out)} max={max(lens_out)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
