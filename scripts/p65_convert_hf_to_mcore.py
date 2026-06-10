"""HF → Megatron-Core checkpoint converter for DeepSeek-R1-0528-Qwen3-8B.

Mirrors `AutoBridge.import_ckpt(...)` but patches the YARN-default
propagation bug observed in Megatron-Bridge 0.4.0rc0: when the HF config
carries `rope_type=yarn`, the bridge sets `yarn_rotary_scaling_factor` +
`yarn_original_max_position_embeddings` correctly but leaves
`yarn_beta_fast`, `yarn_beta_slow`, `yarn_mscale`, `yarn_mscale_all_dim`
as None. The downstream YarnRotaryEmbedding then crashes in
`_yarn_find_correction_dim` because `None * math.pi` is invalid.

Defaults come from megatron.core.models.common.embeddings.yarn_rotary_pos_embedding:
  beta_fast=32.0, beta_slow=1.0, mscale=1.0, mscale_all_dim=0.0

Run from inside `nvcr.io/nvidia/nemo:26.04.00` (container `nemo-train`):

    torchrun --nproc_per_node=1 scripts/p65_convert_hf_to_mcore.py \
      --hf-model /home/nvidia/data/.hf-cache/hub/models--deepseek-ai--DeepSeek-R1-0528-Qwen3-8B/snapshots/<sha>/ \
      --megatron-path /home/nvidia/data/aifn-train-lora/p65-nemo/mcore-base \
      --torch-dtype bfloat16
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import torch
from megatron.bridge import AutoBridge


YARN_DEFAULTS = {
    "yarn_beta_fast": 32.0,
    "yarn_beta_slow": 1.0,
    "yarn_mscale": 1.0,
    "yarn_mscale_all_dim": 0.0,
    "yarn_correction_range_round_to_int": True,
}


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--hf-model", required=True)
    p.add_argument("--megatron-path", required=True)
    p.add_argument("--torch-dtype", default="bfloat16", choices=["float32", "float16", "bfloat16"])
    p.add_argument("--trust-remote-code", action="store_true",
                   help="Models shipping custom config/modeling code (e.g. Nemotron-3-Nano-4B) need this")
    return p.parse_args()


def patch_yarn_defaults(provider) -> None:
    if getattr(provider, "position_embedding_type", None) != "yarn":
        return
    for field, value in YARN_DEFAULTS.items():
        if getattr(provider, field, None) is None:
            setattr(provider, field, value)
            print(f"   patched {field}={value}")


def main() -> int:
    args = parse_args()
    dtype_map = {"float32": torch.float32, "float16": torch.float16, "bfloat16": torch.bfloat16}
    torch_dtype = dtype_map[args.torch_dtype]

    print(f"Loading HF model bridge: {args.hf_model}")
    bridge = AutoBridge.from_hf_pretrained(
        args.hf_model, torch_dtype=torch_dtype, trust_remote_code=args.trust_remote_code
    )

    print("Building Megatron provider (with weight-load plumbing)...")
    provider = bridge.to_megatron_provider(load_weights=True)
    print(f"   position_embedding_type: {provider.position_embedding_type}")
    print(f"   num_layers: {provider.num_layers}  hidden: {provider.hidden_size}  heads: {provider.num_attention_heads}")
    print(f"   seq_length: {provider.seq_length}")

    print("Patching YARN defaults (if needed)...")
    patch_yarn_defaults(provider)

    if hasattr(provider, "finalize"):
        provider.finalize()

    print("Instantiating Megatron model (CPU init, no DDP)...")
    megatron_model = provider.provide_distributed_model(
        wrap_with_ddp=False,
        use_cpu_initialization=True,
    )

    print(f"Saving Megatron checkpoint to: {args.megatron_path}")
    Path(args.megatron_path).mkdir(parents=True, exist_ok=True)
    hf_tokenizer_kwargs = {}
    if hasattr(bridge._model_bridge, "get_hf_tokenizer_kwargs"):
        hf_tokenizer_kwargs = bridge._model_bridge.get_hf_tokenizer_kwargs()
    bridge.save_megatron_model(
        megatron_model,
        args.megatron_path,
        hf_tokenizer_path=args.hf_model,
        hf_tokenizer_kwargs=hf_tokenizer_kwargs,
        low_memory_save=True,
    )
    print("Done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
