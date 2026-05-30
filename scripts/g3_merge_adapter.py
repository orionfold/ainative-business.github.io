"""peft merge_and_unload → BF16 safetensors handoff for g3_build_first_quant.sh.

Reads MODEL_ID (base) + ADAPTER_DIR (LoRA), produces a BF16 merged model at
MERGED_DIR in the same on-disk shape as a base HF checkpoint, so the existing
g3_build_first_quant.sh pipeline can pick it up as MODEL_DIR.

Env vars:
  MODEL_ID       HF id or local path of base model    (required)
  ADAPTER_DIR    peft adapter dir                     (required)
  MERGED_DIR     output dir for merged BF16 weights   (required)
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

os.environ.setdefault("HF_HUB_CACHE", "/root/.cache/huggingface/hub")
os.environ.setdefault("HF_HOME", "/root/.cache/huggingface")


def main() -> int:
    MODEL_ID = os.environ.get("MODEL_ID")
    ADAPTER_DIR = os.environ.get("ADAPTER_DIR")
    MERGED_DIR = os.environ.get("MERGED_DIR")
    for name, val in [("MODEL_ID", MODEL_ID), ("ADAPTER_DIR", ADAPTER_DIR), ("MERGED_DIR", MERGED_DIR)]:
        if not val:
            print(f"ERROR: {name} env var required", file=sys.stderr)
            return 2

    out = Path(MERGED_DIR)
    out.mkdir(parents=True, exist_ok=True)

    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer
    from peft import PeftModel

    print(f"loading base {MODEL_ID} (bf16)...", flush=True)
    t0 = time.time()
    base = AutoModelForCausalLM.from_pretrained(
        MODEL_ID,
        dtype=torch.bfloat16,
        device_map="cuda:0",
        attn_implementation="sdpa",
        trust_remote_code=True,
    )
    print(f"  base loaded in {time.time()-t0:.1f}s")

    print(f"attaching adapter {ADAPTER_DIR}...", flush=True)
    t0 = time.time()
    model = PeftModel.from_pretrained(base, ADAPTER_DIR)
    print(f"  adapter attached in {time.time()-t0:.1f}s")

    print("merging adapter into base weights...", flush=True)
    t0 = time.time()
    merged = model.merge_and_unload()
    print(f"  merge done in {time.time()-t0:.1f}s")

    print(f"saving merged BF16 → {out}", flush=True)
    t0 = time.time()
    merged.save_pretrained(str(out), safe_serialization=True)
    tok = AutoTokenizer.from_pretrained(MODEL_ID, trust_remote_code=True)
    tok.save_pretrained(str(out))
    print(f"  saved in {time.time()-t0:.1f}s")

    # Quick sanity: list output and confirm safetensors are present
    safetensors = sorted(out.glob("*.safetensors"))
    print(f"  output safetensors: {len(safetensors)} files, "
          f"{sum(p.stat().st_size for p in safetensors)/1e9:.2f} GB total")

    print(f"\nDONE. Handoff path for g3_build_first_quant.sh:")
    print(f"  MODEL_DIR={out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
