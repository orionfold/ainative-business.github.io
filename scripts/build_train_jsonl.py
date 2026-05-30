"""Convert patent-prod corpus {row_idx, family, prompt, response, has_think}
to the trainer's expected {"text": ...} shape.

Format: <bos><｜User｜>{prompt}<｜Assistant｜>{response}<eos>

The first cut omitted BOS+EOS — the tokenizer didn't auto-add either at
encode-time for this model. Symptom: probe rows ran the full
max_new_tokens=4096 budget because the model never saw EOS during
training. Explicit BOS also aligns the training prefix with what
`apply_chat_template` emits at inference (bos + User/Assistant tags).
The response already contains <think>...</think>answer.

Reads:  /home/nvidia/data/corpus/patent-prod-2026-05-19.jsonl
Writes: /home/nvidia/data/corpus/patent-prod-2026-05-19.train.jsonl
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

SRC = Path("/home/nvidia/data/corpus/patent-prod-2026-05-19.jsonl")
DST = Path("/home/nvidia/data/corpus/patent-prod-2026-05-19.train.jsonl")

BOS = "<｜begin▁of▁sentence｜>"
EOS = "<｜end▁of▁sentence｜>"
USER_TAG = "<｜User｜>"
ASSISTANT_TAG = "<｜Assistant｜>"


def main() -> int:
    if not SRC.exists():
        print(f"ERROR: {SRC} missing", file=sys.stderr)
        return 2

    rows_in = [json.loads(line) for line in SRC.open() if line.strip()]
    fams = Counter()
    out_rows: list[dict] = []
    for r in rows_in:
        prompt = r["prompt"]
        response = r["response"]
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
    print(f"wrote {len(out_rows)} rows -> {DST}")
    print(f"  <think> markers: {n_with_think}/{len(out_rows)}")
    print(f"  text chars  min={min(lens)} mean={sum(lens)//len(lens)} max={max(lens)}")
    print(f"  family breakdown: {dict(fams)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
