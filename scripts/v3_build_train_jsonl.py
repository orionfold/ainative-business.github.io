"""Convert v3 corpus (DataDesigner-produced) to trainer's {"text": ...} shape.

Same template as scripts/build_train_jsonl.py (patent-prod v2):
  <bos><｜User｜>{prompt}<｜Assistant｜>{response}<eos>

Explicit BOS+EOS per [feedback_sft_eos_bos_explicit]: R1 tokenizer does not
auto-add either at encode-time; without these the probe runs the full
max_new_tokens budget because the model never sees EOS during training.

Reads:  /home/nvidia/data/aifn-corpus-v3/v3_full_5000.jsonl   (root-owned, read-only)
Writes: /home/nvidia/data/aifn-train-lora/v3-corpus/v3_full_5000.train.jsonl
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

SRC = Path("/home/nvidia/data/aifn-corpus-v3/v3_full_5000.jsonl")
DST = Path("/home/nvidia/data/aifn-train-lora/v3-corpus/v3_full_5000.train.jsonl")

BOS = "<｜begin▁of▁sentence｜>"
EOS = "<｜end▁of▁sentence｜>"
USER_TAG = "<｜User｜>"
ASSISTANT_TAG = "<｜Assistant｜>"


def main() -> int:
    if not SRC.exists():
        print(f"ERROR: {SRC} missing", file=sys.stderr)
        return 2

    rows_in = [json.loads(line) for line in SRC.open() if line.strip()]
    fams: Counter[str] = Counter()
    out_rows: list[dict] = []
    skipped = 0
    for r in rows_in:
        prompt = r.get("prompt", "")
        response = r.get("response", "")
        if not prompt or not response:
            skipped += 1
            continue
        if "<think>" not in response or "</think>" not in response:
            print(f"ERROR: row {r.get('row_idx')} missing <think> markers", file=sys.stderr)
            return 3
        text = f"{BOS}{USER_TAG}{prompt}{ASSISTANT_TAG}{response}{EOS}"
        out_rows.append({
            "text": text,
            "row_idx": r["row_idx"],
            "family": r["family"],
        })
        fams[r["family"]] += 1

    DST.parent.mkdir(parents=True, exist_ok=True)
    with DST.open("w") as fh:
        for r in out_rows:
            fh.write(json.dumps(r) + "\n")

    n_with_think = sum(1 for r in out_rows if "<think>" in r["text"] and "</think>" in r["text"])
    lens = [len(r["text"]) for r in out_rows]
    print(f"wrote {len(out_rows)} rows -> {DST}  (skipped {skipped} incomplete)")
    print(f"  <think> markers: {n_with_think}/{len(out_rows)}")
    print(f"  text chars  min={min(lens)} mean={sum(lens)//len(lens)} max={max(lens)}")
    print(f"  family breakdown: {dict(fams)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
