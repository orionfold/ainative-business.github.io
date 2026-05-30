"""Patent-Strategist W3 LoRA trainer (TRL 1.x SFTTrainer + PEFT 0.19+).

Implements spec §4 reasoning-preservation strategy:
  - Layer 1: q/k/v/o-only LoRA targets (MLP untouched)
  - Layer 2: 100% <think>chain</think>answer training examples
  - Layer 4: lr=1e-4 default, cosine schedule, warmup 5%, max 2 epochs, bf16
  - Layer 5: probe-every-N-steps callback hook (set via PROBE_EVERY env var)
  - Layer 6: checkpoint every CHECKPOINT_EVERY steps; pick earliest viable

Env overrides (all optional; defaults are the spec recipe):

  MODEL_ID            HF id or local path                  (deepseek-ai/DeepSeek-R1-0528-Qwen3-8B)
  DATASET             jsonl with {"text": ...}             (required)
  OUTPUT_DIR          adapter output dir                   (/tmp/aifn-train-lora/<run>/adapter)
  RUNS_DIR            trainer state dir                    (/tmp/aifn-train-lora/<run>/runs)

  LORA_TARGETS        comma-list                           (q_proj,k_proj,v_proj,o_proj)
  LORA_R              int                                  (16)
  LORA_ALPHA          int                                  (32)
  LORA_DROPOUT        float                                (0.05)

  LR                  float                                (1e-4)
  EPOCHS              int (mutually exclusive w/ MAX_STEPS)(2)
  MAX_STEPS           int                                  (0 = disabled, use EPOCHS)
  BATCH_SIZE          int                                  (2)
  GRAD_ACCUM          int                                  (8 -> effective batch 16)
  CHECKPOINT_EVERY    int                                  (200)
  PROBE_EVERY         int (0 disables probe callback)      (0 by default; smoke sets 50)
  WARMUP_RATIO        float                                (0.05)
  LOG_EVERY           int                                  (5)
  SEED                int                                  (42)
  MAX_SEQ_LENGTH      int                                  (2048)

Usage:
  MODEL_ID=deepseek-ai/DeepSeek-R1-0528-Qwen3-8B \
  DATASET=/home/nvidia/data/corpus/patent-smoke-50.jsonl \
  OUTPUT_DIR=/tmp/aifn-train-lora/smoke-2026-05-17/adapter \
  RUNS_DIR=/tmp/aifn-train-lora/smoke-2026-05-17/runs \
  LORA_R=8 LORA_ALPHA=16 LR=3e-5 \
  MAX_STEPS=200 CHECKPOINT_EVERY=50 \
  python scripts/g3_train_first_lora.py
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

os.environ.setdefault("HF_HUB_CACHE", "/root/.cache/huggingface/hub")
os.environ.setdefault("HF_HOME", "/root/.cache/huggingface")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")


def env_str(key: str, default: str) -> str:
    return os.environ.get(key, default)


def env_int(key: str, default: int) -> int:
    return int(os.environ.get(key, default))


def env_float(key: str, default: float) -> float:
    return float(os.environ.get(key, default))


def main() -> int:
    import torch
    from datasets import Dataset
    from peft import LoraConfig, TaskType
    from transformers import AutoModelForCausalLM, AutoTokenizer, TrainerCallback
    from trl import SFTConfig, SFTTrainer

    from fieldkit.training import WeightDeltaTracker

    # ─── Config ──────────────────────────────────────────────────────────────
    MODEL_ID = env_str("MODEL_ID", "deepseek-ai/DeepSeek-R1-0528-Qwen3-8B")
    DATASET = env_str("DATASET", "")
    if not DATASET:
        print("ERROR: DATASET env var required", file=sys.stderr)
        return 2

    OUTPUT_DIR = Path(env_str("OUTPUT_DIR", "/tmp/aifn-train-lora/adapter"))
    RUNS_DIR = Path(env_str("RUNS_DIR", "/tmp/aifn-train-lora/runs"))
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    RUNS_DIR.mkdir(parents=True, exist_ok=True)

    LORA_TARGETS = env_str("LORA_TARGETS", "q_proj,k_proj,v_proj,o_proj").split(",")
    LORA_R = env_int("LORA_R", 16)
    LORA_ALPHA = env_int("LORA_ALPHA", 32)
    LORA_DROPOUT = env_float("LORA_DROPOUT", 0.05)

    LR = env_float("LR", 1e-4)
    EPOCHS = env_int("EPOCHS", 2)
    MAX_STEPS = env_int("MAX_STEPS", 0)
    BATCH_SIZE = env_int("BATCH_SIZE", 2)
    GRAD_ACCUM = env_int("GRAD_ACCUM", 8)
    CHECKPOINT_EVERY = env_int("CHECKPOINT_EVERY", 200)
    PROBE_EVERY = env_int("PROBE_EVERY", 0)
    WARMUP_RATIO = env_float("WARMUP_RATIO", 0.05)
    LOG_EVERY = env_int("LOG_EVERY", 5)
    SEED = env_int("SEED", 42)
    MAX_SEQ_LENGTH = env_int("MAX_SEQ_LENGTH", 2048)

    print(f"MODEL_ID={MODEL_ID}")
    print(f"DATASET={DATASET}")
    print(f"LORA={LORA_TARGETS} r={LORA_R} α={LORA_ALPHA} dropout={LORA_DROPOUT}")
    print(f"LR={LR} EPOCHS={EPOCHS} MAX_STEPS={MAX_STEPS} BATCH={BATCH_SIZE}×{GRAD_ACCUM}")
    print(f"OUTPUT_DIR={OUTPUT_DIR}  RUNS_DIR={RUNS_DIR}")

    # ─── Load tokenizer + model ─────────────────────────────────────────────
    print(f"\n>>> loading tokenizer ({MODEL_ID})")
    tok = AutoTokenizer.from_pretrained(MODEL_ID, trust_remote_code=True)
    if tok.pad_token is None:
        tok.pad_token = tok.eos_token

    print(f">>> loading base model bf16 on cuda:0")
    t0 = time.time()
    model = AutoModelForCausalLM.from_pretrained(
        MODEL_ID,
        dtype=torch.bfloat16,
        device_map="cuda:0",
        attn_implementation="sdpa",
        trust_remote_code=True,
    )
    print(f"   loaded in {time.time()-t0:.1f}s  params={sum(p.numel() for p in model.parameters())/1e9:.2f}B")

    # ─── Dataset ────────────────────────────────────────────────────────────
    print(f"\n>>> loading dataset {DATASET}")
    with open(DATASET) as fh:
        raw_rows = [json.loads(line) for line in fh if line.strip()]
    print(f"   {len(raw_rows)} rows")
    # Sanity-check Layer 2: all rows must have <think>...</think>
    bad = [i for i, r in enumerate(raw_rows) if "<think>" not in r.get("text", "") or "</think>" not in r["text"]]
    if bad:
        print(f"   WARNING: {len(bad)} rows missing <think> structure (spec §4 Layer 2)", file=sys.stderr)
    train_ds = Dataset.from_list([{"text": r["text"]} for r in raw_rows])

    # ─── LoRA config ─────────────────────────────────────────────────────────
    lora_cfg = LoraConfig(
        task_type=TaskType.CAUSAL_LM,
        r=LORA_R,
        lora_alpha=LORA_ALPHA,
        lora_dropout=LORA_DROPOUT,
        bias="none",
        target_modules=LORA_TARGETS,
    )

    # ─── SFTConfig ──────────────────────────────────────────────────────────
    cfg_kwargs = dict(
        output_dir=str(RUNS_DIR),
        per_device_train_batch_size=BATCH_SIZE,
        gradient_accumulation_steps=GRAD_ACCUM,
        learning_rate=LR,
        lr_scheduler_type="cosine",
        warmup_ratio=WARMUP_RATIO,
        weight_decay=0.0,
        logging_steps=LOG_EVERY,
        save_strategy="steps",
        save_steps=CHECKPOINT_EVERY,
        save_total_limit=4,
        bf16=True,
        gradient_checkpointing=True,
        gradient_checkpointing_kwargs={"use_reentrant": False},
        report_to=[],
        seed=SEED,
        max_length=MAX_SEQ_LENGTH,
        dataset_text_field="text",
        packing=False,  # spec §3.1: preserve <think> structure
    )
    if MAX_STEPS > 0:
        cfg_kwargs["max_steps"] = MAX_STEPS
    else:
        cfg_kwargs["num_train_epochs"] = EPOCHS
    sft_cfg = SFTConfig(**cfg_kwargs)

    # ─── Probe callback (spec §4 Layer 5) ───────────────────────────────────
    class ProbeCallback(TrainerCallback):
        def __init__(self, every: int):
            self.every = every

        def on_step_end(self, args, state, control, **kwargs):
            if self.every <= 0:
                return
            if state.global_step > 0 and state.global_step % self.every == 0:
                # Write a marker; the probe is run *out-of-process* via the
                # orchestrator shell script so the trainer doesn't pay the
                # cost of model swap or generation here.
                marker = Path(args.output_dir) / f"PROBE_AT_STEP_{state.global_step:06d}"
                marker.touch()
                print(f"   [probe-callback] marked step {state.global_step}", flush=True)

    callbacks = [ProbeCallback(PROBE_EVERY)] if PROBE_EVERY > 0 else []

    # ─── Train ──────────────────────────────────────────────────────────────
    print(f"\n>>> constructing SFTTrainer")
    trainer = SFTTrainer(
        model=model,
        args=sft_cfg,
        train_dataset=train_ds,
        processing_class=tok,
        peft_config=lora_cfg,
        callbacks=callbacks,
    )

    # WeightDeltaTracker after PEFT attach (model is now PeftModel)
    tracker = WeightDeltaTracker(trainer.model)
    print(f"   WeightDeltaTracker tracking {len(tracker)} trainable tensors")

    trainable = sum(p.numel() for p in trainer.model.parameters() if p.requires_grad)
    total = sum(p.numel() for p in trainer.model.parameters())
    print(f"   trainable: {trainable/1e6:.2f}M / total: {total/1e9:.2f}B  ({100*trainable/total:.3f}%)")

    print(f"\n>>> starting training")
    t0 = time.time()
    trainer.train()
    dt = time.time() - t0
    print(f"   training done in {dt/60:.1f}min")

    # ─── Final adapter + sanity ─────────────────────────────────────────────
    print(f"\n>>> saving final adapter -> {OUTPUT_DIR}")
    trainer.model.save_pretrained(str(OUTPUT_DIR))
    tok.save_pretrained(str(OUTPUT_DIR))

    l2, max_abs = tracker.delta()
    print(f"   weight L2-delta = {l2:.6f}  max|Δ| = {max_abs:.6f}")

    # Verify Layer 1: no MLP weights moved
    trainable_names = [n for n, p in trainer.model.named_parameters() if p.requires_grad]
    mlp_trainable = [n for n in trainable_names if any(t in n for t in ("gate_proj", "up_proj", "down_proj"))]
    if mlp_trainable:
        print(f"   WARNING: {len(mlp_trainable)} MLP tensors trainable — Layer-1 violation!", file=sys.stderr)
    else:
        print(f"   Layer-1 isolation verified: only attention LoRA tensors trained.")

    print(f"\nDONE  adapter={OUTPUT_DIR}  trainer-state={RUNS_DIR}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
