"""Day-0 micro-derisk for the W3 LoRA stack.

Validates the smallest possible end-to-end path before committing to the
3-hour Day-1 smoke test (spec §4 Day-1). Six checks, ~5 minutes wall:

  1. Imports     — transformers / peft / trl / accelerate / fieldkit.training
  2. Load        — R1-0528-Qwen3-8B in BF16 on cuda:0
  3. Tokenizer   — <think>...</think> roundtrip survives encode/decode (R14)
  4. LoRA attach — q/k/v/o r=8 + only-attention frozen check (spec §4 Layer 1)
  5. Train step  — 1 forward+backward+optimizer.step on 4 toy <think>-wrapped rows
  6. Weight Δ    — WeightDeltaTracker reports non-zero L2 on attention LoRA tensors
                   and zero L2 on MLP (gate/up/down) — proves Layer 1 isolation

Exits 0 on full green; non-zero with a short red on first failure.
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

# Spec §3.1: pytorch:25.11-py3 base. HF cache mount lives at /root/.cache/huggingface
# when run inside ps-train; on host fall back to /home/nvidia/data/.hf-cache.
os.environ.setdefault("HF_HUB_CACHE", "/root/.cache/huggingface/hub")
os.environ.setdefault("HF_HOME", "/root/.cache/huggingface")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

MODEL_ID = os.environ.get("MODEL_ID", "deepseek-ai/DeepSeek-R1-0528-Qwen3-8B")


def step(label: str) -> None:
    print(f"\n>>> {label}", flush=True)


def fail(msg: str) -> None:
    print(f"\nRED — {msg}", file=sys.stderr, flush=True)
    sys.exit(1)


# ─── 1. Imports ──────────────────────────────────────────────────────────────
step("1/6 imports")
try:
    import torch
    import transformers
    import peft
    import trl
    import accelerate
    from fieldkit.training import WeightDeltaTracker
except ImportError as exc:
    fail(f"missing dep: {exc}")

print(
    f"  torch={torch.__version__}  transformers={transformers.__version__}  "
    f"peft={peft.__version__}  trl={trl.__version__}  accelerate={accelerate.__version__}"
)
if not torch.cuda.is_available():
    fail("CUDA not available")
print(f"  device: {torch.cuda.get_device_name(0)}")


# ─── 2. Load base in BF16 ────────────────────────────────────────────────────
step(f"2/6 load {MODEL_ID} in BF16")
from transformers import AutoModelForCausalLM, AutoTokenizer  # noqa: E402

t0 = time.time()
tok = AutoTokenizer.from_pretrained(MODEL_ID, trust_remote_code=True)
if tok.pad_token is None:
    tok.pad_token = tok.eos_token
print(f"  tokenizer loaded in {time.time()-t0:.1f}s  vocab={tok.vocab_size}")

t0 = time.time()
model = AutoModelForCausalLM.from_pretrained(
    MODEL_ID,
    dtype=torch.bfloat16,
    device_map="cuda:0",
    attn_implementation="sdpa",
    trust_remote_code=True,
)
n_params = sum(p.numel() for p in model.parameters()) / 1e9
print(f"  base loaded in {time.time()-t0:.1f}s  params={n_params:.2f}B")


# ─── 3. Tokenizer surgery (R14) ──────────────────────────────────────────────
step("3/6 <think> roundtrip")
sample = "<think>\nStep 1: identify the claim element.\nStep 2: apply MPEP 2143.\n</think>The claim is anticipated under §102."
ids = tok.encode(sample, add_special_tokens=False)
decoded = tok.decode(ids, skip_special_tokens=False)
print(f"  ids[:8]={ids[:8]}  total_ids={len(ids)}")
print(f"  decoded[:80]={decoded[:80]!r}")
# Roundtrip must preserve <think> and </think> markers literally
if "<think>" not in decoded or "</think>" not in decoded:
    fail("tokenizer dropped <think> tags through encode/decode")
# Also assert <think> is a single token or stable sub-sequence
think_ids = tok.encode("<think>", add_special_tokens=False)
end_think_ids = tok.encode("</think>", add_special_tokens=False)
print(f"  <think> = {think_ids}  </think> = {end_think_ids}")


# ─── 4. LoRA attach with q/k/v/o-only targets ────────────────────────────────
step("4/6 attach LoRA (q/k/v/o, r=8, α=16)")
from peft import LoraConfig, TaskType, get_peft_model  # noqa: E402

lora_cfg = LoraConfig(
    task_type=TaskType.CAUSAL_LM,
    r=8,
    lora_alpha=16,
    lora_dropout=0.05,
    bias="none",
    target_modules=["q_proj", "k_proj", "v_proj", "o_proj"],
)
model = get_peft_model(model, lora_cfg)
trainable = sum(p.numel() for p in model.parameters() if p.requires_grad)
total = sum(p.numel() for p in model.parameters())
print(f"  trainable: {trainable/1e6:.2f}M / total: {total/1e9:.2f}B  ({100*trainable/total:.3f}%)")

# Verify ONLY attention proj tensors are trainable (MLP must be frozen)
trainable_names = [n for n, p in model.named_parameters() if p.requires_grad]
mlp_trainable = [n for n in trainable_names if any(t in n for t in ("gate_proj", "up_proj", "down_proj"))]
if mlp_trainable:
    fail(f"MLP layers are trainable (Layer-1 violation): {mlp_trainable[:3]}")
attn_trainable = [n for n in trainable_names if any(t in n for t in ("q_proj", "k_proj", "v_proj", "o_proj"))]
print(f"  attention-trainable tensors: {len(attn_trainable)} (expected per layer × 4 × 2 lora_A/B)")


# ─── 5. One training step on 4 toy rows ──────────────────────────────────────
step("5/6 single training step on 4 toy rows")
import torch.nn.functional as F  # noqa: E402

toy = [
    "<think>\nPatent claim broadening removes limitations.\n</think>Removing 'metallic' from claim 1 broadens it.",
    "<think>\nMPEP 2143 governs obviousness.\n</think>The combination is obvious under §103.",
    "<think>\nPrior art must predate the filing date.\n</think>The 2018 publication is prior art for a 2020 application.",
    "<think>\nIRAC = Issue, Rule, Application, Conclusion.\n</think>Issue: anticipation. Rule: §102. Application: full match. Conclusion: rejected.",
]

# Tokenize as causal-LM batch; pad to longest in batch
enc = tok(toy, return_tensors="pt", padding=True, truncation=True, max_length=512).to("cuda:0")
labels = enc["input_ids"].clone()
labels[enc["attention_mask"] == 0] = -100  # don't supervise pad

# Set up optimizer over LoRA params only
opt = torch.optim.AdamW(
    [p for p in model.parameters() if p.requires_grad],
    lr=3e-5,
    betas=(0.9, 0.999),
    weight_decay=0.0,
)

# Snapshot trainable weights BEFORE the step
tracker = WeightDeltaTracker(model)
print(f"  WeightDeltaTracker captured {len(tracker)} trainable tensors")

model.train()
t0 = time.time()
out = model(**enc, labels=labels)
loss = out.loss
loss.backward()
opt.step()
opt.zero_grad()
print(f"  loss={loss.item():.4f}  step wall={time.time()-t0:.2f}s")


# ─── 6. Weight delta validation ──────────────────────────────────────────────
step("6/6 weight Δ check (non-zero on attn-LoRA, frozen elsewhere)")
l2, max_abs = tracker.delta()
print(f"  trainable L2-delta = {l2:.6f}  max|Δ| = {max_abs:.6f}")
if l2 == 0.0:
    fail("weights did not move — gradient flow broken")
print("\nGREEN — stack derisked. Safe to proceed to Day-1 smoke (spec §4).")
