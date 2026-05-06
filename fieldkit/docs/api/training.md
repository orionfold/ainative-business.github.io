---
module: training
title: fieldkit.training
summary: Fine-tuning primitives for any RL or SFT loop on the Spark — a CPU-resident LoRA reference snapshot that sidesteps peft 0.19's offloader bug, and a pre/post weight-delta tracker for sanity-checking that gradients actually moved.
order: 5
---

## What it is

Two utilities lifted from `articles/clawgym-on-spark` for any PPO / GRPO / DPO / SFT loop on the DGX Spark's unified-memory GB10:

- **`LoraReferenceSnapshot`** — a CPU-resident snapshot of a peft adapter's LoRA tensors plus a context manager that swaps the snapshot into the live model for one no-grad forward pass and restores trainable weights on exit. **Solves a real peft 0.19 bug**: `model.load_adapter(adapter_name="reference", is_trainable=False)` crashes with a `KeyError` under `device_map="auto"` whenever the GPU has anything else resident — peft's offload-detection over-triggers on Spark unified memory. Verified with vLLM co-resident *and* with the trainer alone. The snapshot/swap dance sidesteps the offloader entirely.
- **`WeightDeltaTracker`** — pre/post snapshot of trainable params with L2 + max|Δ| reporting. Sanity-check that any fine-tuning step actually moved weights. The first time someone debugs "why didn't my LoRA update?" they'll wish for this.

Both classes use **lazy `torch` imports** so `import fieldkit.training` costs nothing in environments that don't run training. Construct any class and you'll get a clear `ImportError` if `torch` (or `safetensors`, for `LoraReferenceSnapshot.from_disk`) isn't installed — install them yourself in the training environment. NeMo / Triton / pytorch-base containers ship them; pure inference envs don't.

## Public API

```python
from fieldkit.training import (
    LoraReferenceSnapshot,
    WeightDeltaTracker,
)
```

### `WeightDeltaTracker(model)`

Snapshot every parameter for which `requires_grad` is True at construction time, copy to CPU. `delta()` re-reads the live model and computes aggregate L2 + max-abs-delta against the snapshot.

```python
from fieldkit.training import WeightDeltaTracker

tracker = WeightDeltaTracker(model)
# ... one or more optimizer steps ...
l2, max_abs = tracker.delta()
print(f"weight L2 = {l2:.6f}, max|Δ| = {max_abs:.6f}")
```

`delta()` returns `(0.0, 0.0)` when no trainable params were captured (the model was set to inference mode before construction). Tensors that became trainable *after* construction are ignored — the tracker only re-measures what it captured.

`len(tracker)` returns the number of tensors held in the pre-snapshot. ~15 lines of math, lazy-torch import.

### `LoraReferenceSnapshot(model, *, snapshot=None)`

A context manager that swaps a CPU-resident snapshot's LoRA weights into the live model for one no-grad forward pass, then restores the pre-swap trainable values on exit. Default constructor snapshots the model's *current* trainable params (online-reference flavor); pass `snapshot=` directly to reuse one snapshot dict across many model instances.

```python
from fieldkit.training import LoraReferenceSnapshot

# Online — snapshot current policy at step start
snap = LoraReferenceSnapshot(model)
# ... one or more optimizer steps on the policy ...
with snap:
    ref_logits = model(input_ids).logits   # frozen-policy forward
# trainable weights restored on exit
```

### `LoraReferenceSnapshot.from_disk(model, adapter_dir, *, adapter_name="default", weights_filename="adapter_model.safetensors")`

Load LoRA weights from a peft adapter directory on disk. Performs the **safetensors-key transform** required by peft: keys in the file have shape `base_model.<…>.weight` while live parameters have shape `base_model.<…>.<adapter_name>.weight`. The snapshot indexes live names so swap/restore Just Works.

```python
# Fixed reference — classic GRPO with SFT-init reference policy
snap = LoraReferenceSnapshot.from_disk(
    model,
    adapter_dir="adapters/sft-init",
    adapter_name="default",
)
for step in range(num_steps):
    with snap:
        ref_logits = model(...).logits
    # ... policy update against fixed reference ...
```

Names that don't match the live model's trainable params are silently skipped — the loader is tolerant of LoRA targets that vary between the saved adapter and the live one (a common occurrence when adapters load into a slightly different model build).

`len(snap)` returns the number of LoRA tensors in the snapshot. Nested `with` is rejected with a `RuntimeError` — only one swap can be active at a time.

## Why it's only two classes

The `clawgym-on-spark` GRPO training loop (`articles/clawgym-on-spark/scripts/grpo_train.py`) leaned on these two patterns repeatedly. They're the smallest, most-grounded surface that survived the v0.2 extract review — anything broader (a full trainer wrapper, an `RLConfig`, a peft-side adapter loader) needs a second consuming article before the API locks. Look out for them in subsequent off-policy-training pieces; the v0.3 release is where larger training surfaces will land.

## Samples

- [`articles/clawgym-on-spark/scripts/grpo_train.py`](https://github.com/manavsehgal/ai-field-notes/blob/main/articles/clawgym-on-spark/scripts/grpo_train.py) — the original `--reference-adapter` + snapshot/swap blocks and the `--check-weight-delta` harness this module is lifted from.
