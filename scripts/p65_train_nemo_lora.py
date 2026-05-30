"""Phase 6.5 — NeMo Framework / Megatron-Bridge LoRA SFT recipe.

Mirror of Unsloth v3 hyperparameters (scripts/g3_train_first_lora.py)
on the Megatron-Bridge stack inside `nvcr.io/nvidia/nemo:26.04.00`. Goal
is apples-to-apples comparison: same base model, same v3 corpus, same
LoRA rank/alpha/targets, same LR schedule, same effective batch.

Parity table (Unsloth ↔ NeMo Framework):
  Base model         deepseek-ai/DeepSeek-R1-0528-Qwen3-8B  (same)
  Corpus             v3_full_5000  (5000 rows, reshape via p65_v3_to_nemo_jsonl.py)
  LoRA rank          16
  LoRA alpha         32
  LoRA dropout       0.05
  LoRA targets       q/k/v/o-only (Layer-1 isolation per spec §4)
                     ↔ Megatron-Bridge fused: ["linear_qkv", "linear_proj"]
                       (linear_qkv = q+k+v fused; linear_proj = o)
  LR                 1e-4, cosine, warmup_fraction=0.05
  Epochs             2
  Micro batch        2
  Global batch       16  (= grad_accum 8 effective on single GPU)
  Max seq len        4096
  dtype              bfloat16

YARN-patch (Megatron-Bridge 0.4.0rc0 bug): the AutoBridge fills
yarn_rotary_scaling_factor + yarn_original_max_position_embeddings from
the HF config but leaves beta_fast/beta_slow/mscale as None — downstream
YarnRotaryEmbedding then crashes. Same patch as p65_convert_hf_to_mcore.py.

Run from inside `nvcr.io/nvidia/nemo:26.04.00` (container `nemo-train`):

  torchrun --nproc_per_node=1 scripts/p65_train_nemo_lora.py \
    --hf-model /home/nvidia/data/.hf-cache/.../snapshots/<sha>/ \
    --pretrained-mcore /home/nvidia/data/aifn-train-lora/p65-nemo/mcore-base \
    --dataset-root /home/nvidia/data/aifn-train-lora/p65-nemo/dataset \
    --run-dir /home/nvidia/data/aifn-train-lora/p65-nemo/runs \
    --train-iters 625 \
    --smoke 0
"""
from __future__ import annotations

import argparse
import sys

import torch
from megatron.bridge import AutoBridge
from megatron.bridge.peft.lora import LoRA
from megatron.bridge.recipes.qwen.qwen3 import qwen3_8b_peft_config
from megatron.bridge.training.config import FinetuningDatasetConfig
from megatron.bridge.training.finetune import finetune
from megatron.bridge.training.gpt_step import forward_step


YARN_DEFAULTS = {
    "yarn_beta_fast": 32.0,
    "yarn_beta_slow": 1.0,
    "yarn_mscale": 1.0,
    "yarn_mscale_all_dim": 0.0,
    "yarn_correction_range_round_to_int": True,
}


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--hf-model", required=True, help="HF base model path (for arch + tokenizer)")
    p.add_argument("--pretrained-mcore", required=True, help="Megatron-Core checkpoint dir (from p65_convert_hf_to_mcore.py)")
    p.add_argument("--dataset-root", required=True, help="Dir holding training.jsonl + validation.jsonl")
    p.add_argument("--run-dir", required=True, help="Trainer state + checkpoint save dir")
    p.add_argument("--train-iters", type=int, default=625, help="Total train iters (5000 rows × 2 epochs / global_batch=16 = 625)")
    p.add_argument("--smoke", type=int, default=0, help="If >0, override train-iters to this value for a smoke test")
    p.add_argument("--seq-length", type=int, default=4096)
    p.add_argument("--lora-r", type=int, default=16)
    p.add_argument("--lora-alpha", type=int, default=32)
    p.add_argument("--lora-dropout", type=float, default=0.05)
    p.add_argument("--lr", type=float, default=1e-4)
    p.add_argument("--micro-batch", type=int, default=2)
    p.add_argument("--global-batch", type=int, default=16)
    p.add_argument("--save-interval", type=int, default=50)
    p.add_argument("--most-recent-k", type=int, default=3,
                   help="Rotate checkpoints: keep N most-recent (default 3, set -1 to keep all)")
    return p.parse_args()


def patch_yarn_defaults(provider) -> None:
    if getattr(provider, "position_embedding_type", None) != "yarn":
        return
    for field, value in YARN_DEFAULTS.items():
        if getattr(provider, field, None) is None:
            setattr(provider, field, value)


def main() -> int:
    args = parse_args()
    train_iters = args.smoke if args.smoke > 0 else args.train_iters
    print(f"[p65] hf_model={args.hf_model}")
    print(f"[p65] mcore_base={args.pretrained_mcore}")
    print(f"[p65] dataset_root={args.dataset_root}")
    print(f"[p65] run_dir={args.run_dir}  train_iters={train_iters}")

    # Start from qwen3_8b_peft_config (TP=1/PP=1, LoRA defaults), then override.
    cfg = qwen3_8b_peft_config(peft_scheme="lora")

    # Base model — replace Qwen3-8B with DeepSeek-R1-0528-Qwen3-8B.
    bridge = AutoBridge.from_hf_pretrained(args.hf_model, torch_dtype=torch.bfloat16)
    provider = bridge.to_megatron_provider(load_weights=True)
    patch_yarn_defaults(provider)
    cfg.model = provider
    cfg.tokenizer.tokenizer_model = args.hf_model

    # Single-GPU Spark layout.
    cfg.model.tensor_model_parallel_size = 1
    cfg.model.pipeline_model_parallel_size = 1
    cfg.model.context_parallel_size = 1
    cfg.model.sequence_parallel = False
    cfg.model.seq_length = args.seq_length

    # LoRA: q/k/v/o-only attention adapters (Layer-1 isolation).
    #   linear_qkv = fused q+k+v projection  (Unsloth: q_proj, k_proj, v_proj)
    #   linear_proj = attention output proj  (Unsloth: o_proj)
    # Excluding linear_fc1/linear_fc2 keeps the MLP frozen.
    cfg.peft = LoRA(
        target_modules=["linear_qkv", "linear_proj"],
        dim=args.lora_r,
        alpha=args.lora_alpha,
        dropout=args.lora_dropout,
    )

    # Training schedule — match Unsloth's effective-batch + cosine LR.
    cfg.train.micro_batch_size = args.micro_batch
    cfg.train.global_batch_size = args.global_batch
    cfg.train.train_iters = train_iters
    cfg.train.eval_interval = 100

    # Cosine LR with 5% warmup.
    cfg.optimizer.lr = args.lr
    cfg.optimizer.min_lr = 0.0
    cfg.scheduler.lr_decay_style = "cosine"
    cfg.scheduler.lr_warmup_fraction = 0.05
    cfg.scheduler.lr_decay_iters = train_iters
    # If qwen3_8b_peft_config left warmup iters at a non-zero default, clear them so warmup_fraction wins.
    cfg.scheduler.lr_warmup_iters = 0
    cfg.scheduler.lr_warmup_samples = 0

    # Dataset — our reshaped v3 corpus in {input, output} schema.
    cfg.dataset = FinetuningDatasetConfig(
        dataset_root=args.dataset_root,
        seq_length=args.seq_length,
        seed=42,
        do_validation=True,
        do_test=False,
    )

    # Checkpoints.
    cfg.checkpoint.pretrained_checkpoint = args.pretrained_mcore
    cfg.checkpoint.save = args.run_dir
    cfg.checkpoint.save_interval = args.save_interval
    cfg.checkpoint.most_recent_k = args.most_recent_k
    # Resume from latest checkpoint in run-dir if present (crash recovery);
    # otherwise start fresh from pretrained_checkpoint.
    cfg.checkpoint.load = args.run_dir

    print(f"[p65] cfg ready  | peft target_modules={cfg.peft.target_modules}  | r={cfg.peft.dim} α={cfg.peft.alpha} dropout={cfg.peft.dropout}")
    print(f"[p65] global_batch={cfg.train.global_batch_size}  micro_batch={cfg.train.micro_batch_size}  iters={cfg.train.train_iters}")

    finetune(config=cfg, forward_step_func=forward_step)
    return 0


if __name__ == "__main__":
    sys.exit(main())
