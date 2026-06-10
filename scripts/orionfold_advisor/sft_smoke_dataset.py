# Copyright 2026 Manav Sehgal
# SPDX-License-Identifier: Apache-2.0
"""Toy 50-row dataset for the Advisor 4B export-path smoke (plan step 2).

This is NOT the SFT corpus (plan step 3). It exists only to prove the
mechanical round trip: NeMo LoRA train -> merge -> HF export -> GGUF ->
lane -> preflight. Rows are deterministic title-lookup QA built from the
public corpus manifest, rendered through the base model's own chat
template so the {input, output} strings carry the real special tokens
(the p65 lesson: megatron.bridge FinetuningDatasetConfig consumes raw
strings; template tokens must be baked in, and they are family-specific).

Run INSIDE the nemo-train container (needs transformers + the downloaded
snapshot):

    python3 scripts/orionfold_advisor/sft_smoke_dataset.py \
        --hf-model /home/nvidia/data/.hf-cache/hub/models--nvidia--NVIDIA-Nemotron-3-Nano-4B-BF16/snapshots/<sha> \
        --out-dir /home/nvidia/data/aifn-train-lora/advisor-4b-smoke/dataset
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

MANIFEST = Path(__file__).resolve().parents[2] / "evidence" / "orionfold-advisor" / "public-corpus-manifest.jsonl"
N_ROWS = 50
VAL_ROWS = 5

SYSTEM = (
    "/no_think\n"
    "You are Orionfold Advisor. Answer only from the retrieved public context. "
    "For a supported answer, finish with exactly one citation line using source ids: "
    "Citations: [source_id, ...]."
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--hf-model", required=True, help="HF snapshot dir (tokenizer + chat template source)")
    parser.add_argument("--out-dir", required=True)
    args = parser.parse_args()

    from transformers import AutoTokenizer

    tok = AutoTokenizer.from_pretrained(args.hf_model, trust_remote_code=True)
    eos = tok.eos_token or ""

    sources = [json.loads(line) for line in MANIFEST.read_text(encoding="utf-8").splitlines() if line.strip()]
    sources = sources[:N_ROWS]
    if len(sources) < N_ROWS:
        print(f"ERROR: manifest has only {len(sources)} sources", file=sys.stderr)
        return 2

    rows = []
    for src in sources:
        sid, title = src["source_id"], src["title"]
        question = f"What is the title of the public source '{sid}'?"
        context = f"Retrieved public context:\nid: {sid}\nTitle: {title}"
        answer = f'The public source {sid} is titled "{title}". Citations: [{sid}]'
        messages = [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": f"Question: {question}\n\n{context}"},
        ]
        prompt = tok.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=True, enable_thinking=False
        )
        rows.append({"input": prompt, "output": answer + eos})

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    train, val = rows[VAL_ROWS:], rows[:VAL_ROWS]
    for name, subset in (("training.jsonl", train), ("validation.jsonl", val)):
        with (out_dir / name).open("w", encoding="utf-8") as fh:
            for row in subset:
                fh.write(json.dumps(row, sort_keys=True) + "\n")
    print(f"wrote {len(train)} train + {len(val)} val rows -> {out_dir}")
    print("--- sample input ---")
    print(rows[0]["input"][:600])
    print("--- sample output ---")
    print(rows[0]["output"][:300])
    return 0


if __name__ == "__main__":
    sys.exit(main())
