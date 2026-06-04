#!/usr/bin/env python3
"""Path-A C4 fix: emit a zero-init rank-16 LoRA adapter on top of the merged SFT
Qwen3-8B, so FK_RL_ADAPTER_INIT is a real --lora-modules target.

The B matrices are zero-initialized by PEFT, so at step 0 the served policy ==
the merged SFT model (delta is a no-op) — the held-out gate should reproduce the
C2(b) 86% before RL moves a single weight. CPU-only; no GPU needed.

Run inside a torch+peft env, e.g. the vllm-node image:
  docker run --rm --gpus all --network host \
    -v /home/nvidia/data/astro-train-lora/p65-nemo/merged-hf-bf16:/model:ro \
    -v /home/nvidia/data/astro-train-lora/p65-nemo:/out \
    -v /tmp/make_init_lora.py:/make_init_lora.py:ro \
    --entrypoint python3 vllm-node:latest /make_init_lora.py
"""
import torch
from transformers import AutoModelForCausalLM
from peft import LoraConfig, get_peft_model

SRC = "/model"
DST = "/out/init-lora-r16"

# Qwen3 attention + MLP projections — the standard GRPO LoRA target set.
TARGETS = ["q_proj", "k_proj", "v_proj", "o_proj",
           "gate_proj", "up_proj", "down_proj"]

print(f"loading {SRC} (bf16, CPU)…", flush=True)
model = AutoModelForCausalLM.from_pretrained(
    SRC, torch_dtype=torch.bfloat16, device_map="cpu"
)
cfg = LoraConfig(r=16, lora_alpha=32, lora_dropout=0.0,
                 target_modules=TARGETS, task_type="CAUSAL_LM", bias="none")
peft_model = get_peft_model(model, cfg)
peft_model.print_trainable_parameters()
peft_model.save_pretrained(DST)  # writes adapter_config.json + adapter_model.safetensors only
print(f"wrote zero-init LoRA → {DST}", flush=True)
