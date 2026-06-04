"""Reshape the astrodynamics SFT-init corpus into the {input, output} JSONL
schema NeMo Framework SFT expects — Qwen3 chat format (C2(b), AV-5).

Source:  evidence/astrodynamics/astro-sft-corpus.jsonl
         (keys: task_id, topic, subtopic, tier, prompt, completion,
          answer, gold_value_si, gold_unit)

Writes (90/10 train/val split, deterministic by SEED=42):
  /home/nvidia/data/astro-train-lora/p65-nemo/dataset/training.jsonl
  /home/nvidia/data/astro-train-lora/p65-nemo/dataset/validation.jsonl

Schema per row (matches `_preprocess` in megatron.bridge.data.datasets.utils;
NeMo concatenates input+output as literal text — NO chat template is
re-applied, so the Qwen3 tags + EOS must be baked into the strings here):

  {"input":  "<|im_start|>user\n{prompt}<|im_end|>\n<|im_start|>assistant\n",
   "output": "{completion}<|im_end|>"}

Qwen3 tokenizer specifics (verified against the cached base config, NOT the
R1 patent base this script's sibling p65_v3_to_nemo_jsonl.py was written for):
  - NO BOS  (tokenizer add_bos_token=False, bos_token=None)        [feedback_sft_eos_bos_explicit]
  - EOS = <|im_end|> (id 151645) — explicit, the assistant-turn terminator
  - user/assistant turns wrapped <|im_start|>…<|im_end|>

The corpus completion already carries `<think>…</think>` + a `\boxed{}`
answer; the assistant turn begins right after `<|im_start|>assistant\n`,
matching Qwen3 thinking-mode generation (enable_thinking=True) — so the SFT
format is byte-consistent with RLVR/eval rollouts.

answer_only_loss=False in the recipe → loss on every token (input+output),
matching the patent NeMo lane.

Pure-python, host-runnable (no GPU, no container, no transformers dep).
"""
from __future__ import annotations

import json
import random
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SRC = REPO / "evidence" / "astrodynamics" / "astro-sft-corpus.jsonl"
OUT_DIR = Path("/home/nvidia/data/astro-train-lora/p65-nemo/dataset")
SEED = 42
VAL_FRAC = 0.10

IM_START = "<|im_start|>"
IM_END = "<|im_end|>"


def main() -> int:
    if not SRC.exists():
        print(f"ERROR: {SRC} missing", file=sys.stderr)
        return 2

    rows = [json.loads(line) for line in SRC.open() if line.strip()]
    out_rows: list[dict] = []
    skipped = 0
    for r in rows:
        prompt = r.get("prompt", "")
        completion = r.get("completion", "")
        if not prompt or not completion:
            skipped += 1
            continue
        if "<think>" not in completion or "</think>" not in completion:
            print(
                f"ERROR: {r.get('task_id')} missing <think> markers",
                file=sys.stderr,
            )
            return 3
        if "\\boxed{" not in completion:
            print(
                f"ERROR: {r.get('task_id')} missing \\boxed{{}}",
                file=sys.stderr,
            )
            return 4
        input_str = (
            f"{IM_START}user\n{prompt}{IM_END}\n{IM_START}assistant\n"
        )
        output_str = f"{completion}{IM_END}"
        out_rows.append(
            {
                "input": input_str,
                "output": output_str,
                "task_id": r["task_id"],
                "topic": r["topic"],
                "subtopic": r["subtopic"],
            }
        )

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
    print(
        f"wrote training.jsonl ({len(train_rows)} rows) + "
        f"validation.jsonl ({len(val_rows)} rows) to {OUT_DIR}"
    )
    print(f"   skipped: {skipped}")
    print(
        f"   input  chars  min={min(lens_in)} "
        f"mean={sum(lens_in) // len(lens_in)} max={max(lens_in)}"
    )
    print(
        f"   output chars  min={min(lens_out)} "
        f"mean={sum(lens_out) // len(lens_out)} max={max(lens_out)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
