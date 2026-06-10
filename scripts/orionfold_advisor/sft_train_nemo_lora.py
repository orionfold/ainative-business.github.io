# Copyright 2026 Manav Sehgal
# SPDX-License-Identifier: Apache-2.0
"""Advisor 4B — NeMo Framework / Megatron-Bridge LoRA SFT trainer.

p65_train_nemo_lora.py adapted for the decided training base
``nvidia/NVIDIA-Nemotron-3-Nano-4B-BF16`` (dense NemotronH hybrid):
starts from ``nemotronh_4b_peft_config`` instead of the Qwen3 recipe.
The YARN patch is carried but expected to be a no-op (NemotronH is not
yarn-rope); harmless either way per the conditional guard.

LoRA targets stay attention-only (``linear_qkv`` + ``linear_proj``) —
on the hybrid stack these exist only in the attention layers; Mamba
blocks stay frozen. Fine for the export-path smoke and a deliberate
first choice for the real run (widen only if held-out residue persists).

Run from inside ``nvcr.io/nvidia/nemo:26.04.00`` (container ``nemo-train``):

  torchrun --nproc_per_node=1 scripts/orionfold_advisor/sft_train_nemo_lora.py \
    --hf-model <snapshot-dir> \
    --pretrained-mcore /home/nvidia/data/aifn-train-lora/advisor-4b-smoke/mcore-base \
    --dataset-root /home/nvidia/data/aifn-train-lora/advisor-4b-smoke/dataset \
    --run-dir /home/nvidia/data/aifn-train-lora/advisor-4b-smoke/runs-smoke \
    --smoke 10
"""
from __future__ import annotations

import argparse
import sys

import torch
from megatron.bridge import AutoBridge
from megatron.bridge.peft.lora import LoRA
from megatron.bridge.recipes.nemotronh import nemotronh_4b_peft_config
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
    p.add_argument("--train-iters", type=int, default=150)
    p.add_argument("--smoke", type=int, default=0, help="If >0, override train-iters to this value for a smoke test")
    p.add_argument("--seq-length", type=int, default=2048)
    p.add_argument("--lora-r", type=int, default=16)
    p.add_argument("--lora-alpha", type=int, default=32)
    p.add_argument("--lora-dropout", type=float, default=0.05)
    p.add_argument("--lr", type=float, default=1e-4)
    p.add_argument("--micro-batch", type=int, default=1)
    p.add_argument("--global-batch", type=int, default=8)
    p.add_argument("--save-interval", type=int, default=10)
    p.add_argument("--most-recent-k", type=int, default=3)
    p.add_argument(
        "--eval-iters",
        type=int,
        default=-1,
        help=(
            "Override eval_iters for non-smoke runs; size so that "
            "eval_iters x global_batch <= validation rows or end-of-train "
            "validation wedges forever. -1 keeps the recipe default."
        ),
    )
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
    print(f"[adv4b] hf_model={args.hf_model}")
    print(f"[adv4b] mcore_base={args.pretrained_mcore}")
    print(f"[adv4b] dataset_root={args.dataset_root}")
    print(f"[adv4b] run_dir={args.run_dir}  train_iters={train_iters}")

    cfg = nemotronh_4b_peft_config(peft_scheme="lora")

    # Nemotron-3-Nano-4B ships custom configuration/modeling code; without
    # trust_remote_code the config loader dies with a bare KeyError ('-').
    bridge = AutoBridge.from_hf_pretrained(
        args.hf_model, torch_dtype=torch.bfloat16, trust_remote_code=True
    )
    provider = bridge.to_megatron_provider(load_weights=True)
    patch_yarn_defaults(provider)
    cfg.model = provider
    cfg.tokenizer.tokenizer_model = args.hf_model
    # nemotronh_4b_peft_config targets the old Nemotron-H-4B-Base-8K tokenizer
    # and injects hf_tokenizer_kwargs={'eos_token': '<SPECIAL_11>'}. That token
    # does not exist in the Nemotron-3-Nano-4B tokenizer, so transformers ADDS
    # it (vocab 131072 -> 131073) and setup dies on the model/tokenizer vocab
    # check. The Nemotron-3 tokenizer already carries the right EOS (<|im_end|>).
    cfg.tokenizer.hf_tokenizer_kwargs = {}

    cfg.model.tensor_model_parallel_size = 1
    cfg.model.pipeline_model_parallel_size = 1
    cfg.model.context_parallel_size = 1
    cfg.model.sequence_parallel = False
    cfg.model.seq_length = args.seq_length

    cfg.peft = LoRA(
        target_modules=["linear_qkv", "linear_proj"],
        dim=args.lora_r,
        alpha=args.lora_alpha,
        dropout=args.lora_dropout,
    )

    cfg.train.micro_batch_size = args.micro_batch
    cfg.train.global_batch_size = args.global_batch
    cfg.train.train_iters = train_iters
    cfg.train.eval_interval = 100
    # The end-of-training validation pass wedges forever (GPU 0%, dataloader
    # alive) when the validation split is smaller than eval_iters ×
    # global_batch — the 10-step smoke hung an hour on its 5-row val set.
    # Size eval to what the split can actually feed.
    if args.smoke > 0:
        cfg.train.eval_iters = 0
    elif args.eval_iters >= 0:
        cfg.train.eval_iters = args.eval_iters

    cfg.optimizer.lr = args.lr
    cfg.optimizer.min_lr = 0.0
    cfg.scheduler.lr_decay_style = "cosine"
    cfg.scheduler.lr_warmup_fraction = 0.05
    cfg.scheduler.lr_decay_iters = train_iters
    cfg.scheduler.lr_warmup_iters = 0
    cfg.scheduler.lr_warmup_samples = 0

    cfg.dataset = FinetuningDatasetConfig(
        dataset_root=args.dataset_root,
        seq_length=args.seq_length,
        seed=42,
        do_validation=True,
        do_test=False,
    )

    cfg.checkpoint.pretrained_checkpoint = args.pretrained_mcore
    cfg.checkpoint.save = args.run_dir
    cfg.checkpoint.save_interval = args.save_interval
    cfg.checkpoint.most_recent_k = args.most_recent_k
    cfg.checkpoint.load = args.run_dir

    print(f"[adv4b] cfg ready | peft target_modules={cfg.peft.target_modules} | r={cfg.peft.dim} α={cfg.peft.alpha}")
    print(f"[adv4b] global_batch={cfg.train.global_batch_size} micro_batch={cfg.train.micro_batch_size} iters={cfg.train.train_iters}")

    finetune(config=cfg, forward_step_func=forward_step)
    return 0


if __name__ == "__main__":
    sys.exit(main())
