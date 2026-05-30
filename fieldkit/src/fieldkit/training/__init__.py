# Copyright 2026 Manav Sehgal
# SPDX-License-Identifier: Apache-2.0
"""Fine-tuning primitives lifted from the project's training-shaped articles.

Two utilities for any RL or SFT loop on the DGX Spark's unified-memory
GB10:

- `WeightDeltaTracker` — pre/post snapshot of trainable parameters with
  L2 + max-absolute-delta reporting. Sanity-check that any fine-tuning
  step actually moved weights. ~15 lines of math, but the first time
  someone debugs "why didn't my LoRA update?" they'll wish for this.
- `LoraReferenceSnapshot` — CPU-resident snapshot of a peft adapter's
  LoRA tensors, with a context manager that swaps the snapshot into
  the live model for one no-grad forward pass and restores trainable
  weights on exit. Solves a real peft 0.19 bug: `load_adapter(...,
  is_trainable=False)` crashes with a `KeyError` under
  `device_map="auto"` whenever the GPU has anything else resident
  (verified with vLLM co-resident *and* with the trainer alone — peft's
  offload-detection over-triggers on Spark unified memory). Anyone
  doing PPO / GRPO / DPO with a frozen reference policy on Spark
  hits this wall.

Both classes use lazy `torch` imports so `import fieldkit.training`
costs nothing in environments that don't run training. Construct any
class and you'll get a clear `ImportError` if `torch` (or `safetensors`,
for `LoraReferenceSnapshot.from_disk`) isn't installed — install them
yourself in the training environment (NeMo / Triton / pytorch-base
containers ship them; pure inference envs don't).

Tested in `articles/clawgym-on-spark/scripts/grpo_train.py` against
Qwen 2.5 7B + a rank-16 LoRA adapter; the swap/restore math is
byte-identical to that script's `--reference-adapter` and
`--check-weight-delta` blocks.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fieldkit.training.convert import (
    DEEPSEEK_R1_0528_QWEN3_TOKENIZER_HASH,
    YARN_DEFAULTS,
    ConvertError,
    HFToMegatron,
    patch_yarn_defaults,
    register_llama_cpp_pretokenizer_hash,
)
from fieldkit.training.decide import (
    DEFAULT_FRESHNESS_DAYS,
    DecideEntry,
    DecideError,
    DecideFinding,
    DecidePick,
    SEED_ENTRIES_DIR,
    StalenessReport,
    USER_ENTRIES_DIR,
    VALID_LIFECYCLES,
    load_entries,
    refresh,
    train_backend,
)
from fieldkit.training.probe import (
    DEFAULT_COMPARE_THRESHOLDS,
    CompareResult,
    CompareRow,
    CompareThresholds,
    ProbeError,
    ProbeQuestion,
    ProbeReport,
    ProbeRow,
    ProbeSummary,
    ReasoningProbe,
    THINK_REGEX,
    parse_think,
    summarize_rows,
)
from fieldkit.training.recipe import (
    MODE_FULL,
    MODE_SMOKE,
    RecipeError,
    TrainRecipe,
)
from fieldkit.training.run import (
    DEEPSEEK_TOKENIZER_CLASS_REMAP,
    MergeExportError,
    MergeExportResult,
    TrainError,
    TrainResult,
    merge_and_export,
    poll_run_progress,
    run,
    standardize_hf_export,
)

__all__ = [
    "CompareResult",
    "CompareRow",
    "CompareThresholds",
    "ConvertError",
    "DEEPSEEK_R1_0528_QWEN3_TOKENIZER_HASH",
    "DEEPSEEK_TOKENIZER_CLASS_REMAP",
    "DEFAULT_COMPARE_THRESHOLDS",
    "DEFAULT_FRESHNESS_DAYS",
    "DecideEntry",
    "DecideError",
    "DecideFinding",
    "DecidePick",
    "HFToMegatron",
    "LoraReferenceSnapshot",
    "MODE_FULL",
    "MODE_SMOKE",
    "MergeExportError",
    "MergeExportResult",
    "ProbeError",
    "ProbeQuestion",
    "ProbeReport",
    "ProbeRow",
    "ProbeSummary",
    "ReasoningProbe",
    "RecipeError",
    "SEED_ENTRIES_DIR",
    "StalenessReport",
    "THINK_REGEX",
    "TrainError",
    "TrainRecipe",
    "TrainResult",
    "USER_ENTRIES_DIR",
    "VALID_LIFECYCLES",
    "WeightDeltaTracker",
    "YARN_DEFAULTS",
    "load_entries",
    "merge_and_export",
    "parse_think",
    "patch_yarn_defaults",
    "poll_run_progress",
    "refresh",
    "register_llama_cpp_pretokenizer_hash",
    "run",
    "standardize_hf_export",
    "summarize_rows",
    "train_backend",
]


def _require_torch() -> Any:
    """Lazy `torch` import with a clear error if unavailable."""
    try:
        import torch
    except ImportError as exc:
        raise ImportError(
            "fieldkit.training requires torch. Install it in your "
            "training environment: `pip install torch` (typically already "
            "present in NeMo / Triton / pytorch-base containers)."
        ) from exc
    return torch


def _require_safetensors() -> Any:
    """Lazy `safetensors.torch` import with a clear error if unavailable."""
    try:
        from safetensors.torch import load_file
    except ImportError as exc:
        raise ImportError(
            "fieldkit.training.LoraReferenceSnapshot.from_disk requires "
            "safetensors. Install it: `pip install safetensors`."
        ) from exc
    return load_file


class WeightDeltaTracker:
    """Pre/post snapshot of trainable params with L2 and max|Δ| reporting.

    Sanity-check that a fine-tuning step actually moved weights. Snapshots
    every parameter for which ``requires_grad`` is True at construction
    time, copies to CPU; `delta()` re-reads the live model and computes
    aggregate L2 + max-abs-delta against the snapshot.

    Usage::

        from fieldkit.training import WeightDeltaTracker

        tracker = WeightDeltaTracker(model)
        # ... one or more optimizer steps ...
        l2, max_abs = tracker.delta()
        print(f"weight L2 = {l2:.6f}, max|Δ| = {max_abs:.6f}")

    `delta()` returns ``(0.0, 0.0)`` if no trainable params were captured
    (e.g., the model was set to inference mode before construction).

    Lifted from `articles/clawgym-on-spark/scripts/grpo_train.py` —
    the `--check-weight-delta` block.
    """

    def __init__(self, model: Any) -> None:
        _require_torch()
        self._snapshot: dict[str, Any] = {}
        for name, param in model.named_parameters():
            if param.requires_grad:
                self._snapshot[name] = param.detach().clone().cpu()
        self._model = model

    def __len__(self) -> int:
        """Number of trainable tensors held in the pre-snapshot."""
        return len(self._snapshot)

    def delta(self) -> tuple[float, float]:
        """Re-read live params and compute ``(L2_norm_total, max_abs_delta)``.

        Iterates the model's named_parameters again — only tensors that
        still require_grad AND were captured at construction time
        contribute. New trainable params added after construction are
        ignored (would otherwise blow up with KeyError).
        """
        if not self._snapshot:
            return 0.0, 0.0
        sq_sum = 0.0
        max_abs = 0.0
        for name, param in self._model.named_parameters():
            if not param.requires_grad or name not in self._snapshot:
                continue
            d = (param.detach().cpu() - self._snapshot[name]).float()
            sq_sum += float((d * d).sum())
            tensor_max = float(d.abs().max())
            if tensor_max > max_abs:
                max_abs = tensor_max
        return sq_sum**0.5, max_abs


class LoraReferenceSnapshot:
    """CPU-resident snapshot of a peft adapter's LoRA tensors.

    A context manager that swaps the snapshot's LoRA weights into the
    live model for one no-grad forward pass, then restores the
    pre-swap (trainable) values on exit. Designed for any RL training
    loop that needs a frozen reference policy alongside the
    actively-updating policy adapter.

    Usage — online (snapshot from current policy at step start)::

        from fieldkit.training import LoraReferenceSnapshot

        snap = LoraReferenceSnapshot(model)
        # ... one or more optimizer steps on the policy ...
        with snap:
            ref_logits = model(input_ids).logits     # frozen-policy forward

    Usage — fixed reference loaded from disk (classic GRPO fixed-SFT-init
    reference)::

        snap = LoraReferenceSnapshot.from_disk(
            model,
            adapter_dir="adapters/sft-init",
            adapter_name="default",
        )
        for step in range(num_steps):
            with snap:
                ref_logits = model(...).logits
            # ... policy update against fixed reference ...

    `from_disk` performs the safetensors-key transform required by peft:
    keys in the file have shape ``base_model.<...>.weight`` while live
    parameters have shape ``base_model.<...>.<adapter_name>.weight``. The
    snapshot indexes the live names so swap/restore Just Works.

    Why this exists: peft 0.19's
    ``model.load_adapter(adapter_name="reference", is_trainable=False)``
    crashes with a ``KeyError`` under ``device_map="auto"`` whenever the
    GPU has anything else resident — peft's offload-detection
    over-triggers on Spark unified memory. The CPU-snapshot/swap dance
    sidesteps the offloader entirely. ~30 lines, no peft import; just
    requires that the model's trainable LoRA params live alongside the
    base weights in the same module tree.

    Lifted from `articles/clawgym-on-spark/scripts/grpo_train.py` —
    the `--reference-adapter` + snapshot/swap blocks.
    """

    def __init__(
        self,
        model: Any,
        *,
        snapshot: dict[str, Any] | None = None,
    ) -> None:
        _require_torch()
        self._model = model
        self._snapshot: dict[str, Any] = {}
        if snapshot is not None:
            self._snapshot = dict(snapshot)
        else:
            for name, param in model.named_parameters():
                if param.requires_grad:
                    self._snapshot[name] = param.detach().clone().cpu()
        self._restore: dict[str, Any] = {}
        self._active = False

    @classmethod
    def from_disk(
        cls,
        model: Any,
        adapter_dir: str | Path,
        *,
        adapter_name: str = "default",
        weights_filename: str = "adapter_model.safetensors",
    ) -> LoraReferenceSnapshot:
        """Load LoRA weights from a peft adapter directory on disk.

        Performs the peft key transform — file keys
        ``base_model.<...>.weight`` become live-param keys
        ``base_model.<...>.<adapter_name>.weight``. Names that don't
        match the live model's trainable params are silently skipped
        so the loader is tolerant of LoRA targets that vary between
        the saved adapter and the live one (a common occurrence when
        adapters are loaded into a slightly different model build).
        """
        _require_torch()
        load_file = _require_safetensors()
        adapter_path = Path(adapter_dir) / weights_filename
        if not adapter_path.is_file():
            raise FileNotFoundError(
                f"adapter weights not found at {adapter_path}"
            )
        raw = load_file(str(adapter_path))
        snapshot: dict[str, Any] = {}
        # Index live trainable param names so we know what to look up.
        live_names: dict[str, Any] = {
            n: p for n, p in model.named_parameters() if p.requires_grad
        }
        suffix = f".{adapter_name}.weight"
        for name in live_names:
            if name.endswith(suffix):
                # base_model.X.<adapter_name>.weight → base_model.X.weight
                file_key = name[: -len(suffix)] + ".weight"
                if file_key in raw:
                    snapshot[name] = raw[file_key].clone()
                    continue
            if name in raw:
                snapshot[name] = raw[name].clone()
        return cls(model, snapshot=snapshot)

    def __len__(self) -> int:
        """Number of LoRA tensors in the snapshot."""
        return len(self._snapshot)

    def __enter__(self) -> LoraReferenceSnapshot:
        """Swap snapshot weights into live params; cache live for restore."""
        if self._active:
            raise RuntimeError(
                "LoraReferenceSnapshot is already active — nested swaps "
                "are not supported."
            )
        torch = _require_torch()
        with torch.no_grad():
            for name, param in self._model.named_parameters():
                if name not in self._snapshot:
                    continue
                self._restore[name] = param.detach().clone()
                param.data.copy_(
                    self._snapshot[name].to(param.device, dtype=param.dtype)
                )
        self._active = True
        return self

    def __exit__(self, *_exc: object) -> None:
        """Restore the cached live weights into the model."""
        if not self._active:
            return
        torch = _require_torch()
        with torch.no_grad():
            for name, param in self._model.named_parameters():
                if name not in self._restore:
                    continue
                param.data.copy_(self._restore[name])
        self._restore.clear()
        self._active = False
