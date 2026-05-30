# Copyright 2026 Manav Sehgal
# SPDX-License-Identifier: Apache-2.0
"""Declarative training recipe.

Captures the surface area that `scripts/p65_train_nemo_lora.{py,sh}`
spreads across argparse flags + bash env vars in one frozen Python
dataclass. Round-trips via YAML so recipes can be shared between
sessions as `articles/<slug>/recipe.yaml` companion files.

Pure-python, no torch import — `validate()` is offline preflight only.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict, fields
from pathlib import Path
from typing import Any, Literal, Mapping, Optional

__all__ = [
    "RecipeError",
    "TrainRecipe",
    "MODE_SMOKE",
    "MODE_FULL",
]

MODE_SMOKE: Literal["smoke"] = "smoke"
MODE_FULL: Literal["full"] = "full"

_BACKENDS = ("nemo", "unsloth")
_DEFAULT_LORA_TARGETS_HF = ("q_proj", "k_proj", "v_proj", "o_proj")


class RecipeError(ValueError):
    """Raised when a TrainRecipe fails validation.

    Distinct from generic ValueError so callers can selectively catch
    misconfig vs runtime training failures.
    """


@dataclass(frozen=True)
class TrainRecipe:
    """Declarative training recipe for a single LoRA SFT run.

    Field semantics chosen so the same recipe drives either backend with
    one record. Backend-specific quirks (NeMo's fused ``linear_qkv`` /
    ``linear_proj`` target names vs Unsloth's ``q_proj``/``k_proj`` etc.)
    are resolved at run-time in ``fieldkit.training.run``; the recipe
    carries the HF-flavoured target list and a backend tag.

    Constructed once, immutable thereafter. Round-trips through YAML via
    ``to_yaml(path)`` / ``TrainRecipe.from_yaml(path)``.

    The contract: ``validate()`` is pure-python and runs offline (no
    filesystem reads); ``preflight()`` does the disk-level checks the
    bash orchestrator currently does inline. Splitting lets unit tests
    cover ``validate()`` without fixturing every file path.
    """

    base_model: str
    """HF model path or repo id. The base for both LoRA targeting and
    tokenizer/chat-template resolution."""

    dataset_jsonl: str
    """Source corpus path. The actual on-disk layout fed to the trainer
    (e.g. NeMo's ``{dataset_root}/training.jsonl`` + ``validation.jsonl``
    split) is owned by ``fieldkit.training.convert.dataset_to_nemo`` —
    this field is the *source*, not the staged split."""

    output_dir: str
    """Trainer state + checkpoint root. The run-dir layout
    (``runs-smoke/``, ``runs-full/``, ``merged-mcore/``, etc.) is owned
    by the backend module."""

    backend: Literal["nemo", "unsloth"] = "nemo"
    """Training backend. Drives both the docker container target and the
    LoRA target-module name mapping at runtime."""

    # --- LoRA shape -----------------------------------------------------

    lora_rank: int = 16
    lora_alpha: int = 32
    lora_dropout: float = 0.05
    lora_target_modules: tuple[str, ...] = _DEFAULT_LORA_TARGETS_HF
    """HF-flavoured target-module names. NeMo backend maps q/k/v → fused
    ``linear_qkv`` and o → ``linear_proj`` at runtime — the recipe
    stays portable across backends."""

    # --- Sequence + batching -------------------------------------------

    seq_length: int = 4096
    micro_batch_size: int = 2
    global_batch_size: int = 16
    """Effective batch size across grad-accumulation. NeMo backend
    derives ``grad_accum = global / micro / world_size``."""

    # --- Optimizer / schedule ------------------------------------------

    learning_rate: float = 1e-4
    min_learning_rate: float = 0.0
    lr_schedule: Literal["cosine", "linear", "constant"] = "cosine"
    lr_warmup_fraction: float = 0.05

    # --- Step counts ----------------------------------------------------

    max_steps: int = 625
    """Total iterations for the full train run. Default 625 = 5000 rows
    × 2 epochs / global_batch=16 (Phase 6.5 patent-strategist v3 setup)."""

    save_interval: int = 50
    """Checkpoint save cadence in iterations."""

    most_recent_k: int = 3
    """Checkpoint rotation — keep N most-recent. ``-1`` = keep all.
    Default 3 matches the Phase 6.5 run-dir layout."""

    smoke_steps: int = 10
    """``mode='smoke'`` cap. Must be ≤ ``max_steps``."""

    # --- Backend wiring -------------------------------------------------

    container: Optional[str] = None
    """Docker container name for backend dispatch. Default resolves at
    runtime: ``nemo-train`` for ``backend='nemo'``, ``ps-train`` for
    ``backend='unsloth'``. Set explicitly to override."""

    torch_dtype: Literal["bfloat16", "float16", "float32"] = "bfloat16"
    seed: int = 42

    # --- Extensibility --------------------------------------------------

    extra_env: Mapping[str, str] = field(default_factory=dict)
    """Extra env vars forwarded to the trainer process (e.g.
    ``{"NCCL_DEBUG": "WARN"}``). Recipe-level escape hatch — prefer
    adding a typed field if a knob is reused across recipes."""

    notes: Optional[str] = None
    """Free-text annotation that survives YAML round-trip. Useful for
    correlating a recipe with an article slug or a decide-entry."""

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def validate(self) -> None:
        """Pure-python preflight. No filesystem reads.

        Raises ``RecipeError`` on the first failure; callers can wrap
        and surface a single user-facing line.
        """
        if self.backend not in _BACKENDS:
            raise RecipeError(
                f"backend={self.backend!r} not in {_BACKENDS}"
            )

        if self.lora_rank < 1:
            raise RecipeError(f"lora_rank must be >= 1 (got {self.lora_rank})")
        if self.lora_alpha < 1:
            raise RecipeError(f"lora_alpha must be >= 1 (got {self.lora_alpha})")
        if not 0.0 <= self.lora_dropout < 1.0:
            raise RecipeError(
                f"lora_dropout must be in [0, 1) (got {self.lora_dropout})"
            )
        if not self.lora_target_modules:
            raise RecipeError("lora_target_modules must be non-empty")

        if self.seq_length < 1:
            raise RecipeError(f"seq_length must be >= 1 (got {self.seq_length})")
        if self.backend == "nemo" and self.seq_length % 64 != 0:
            raise RecipeError(
                f"backend=nemo requires seq_length % 64 == 0 "
                f"(got {self.seq_length}) — Megatron tensor layout constraint"
            )

        if self.micro_batch_size < 1:
            raise RecipeError(
                f"micro_batch_size must be >= 1 (got {self.micro_batch_size})"
            )
        if self.global_batch_size < self.micro_batch_size:
            raise RecipeError(
                f"global_batch_size ({self.global_batch_size}) must be >= "
                f"micro_batch_size ({self.micro_batch_size})"
            )
        if self.global_batch_size % self.micro_batch_size != 0:
            raise RecipeError(
                f"global_batch_size ({self.global_batch_size}) must be a "
                f"multiple of micro_batch_size ({self.micro_batch_size})"
            )

        if self.learning_rate <= 0.0:
            raise RecipeError(
                f"learning_rate must be > 0 (got {self.learning_rate})"
            )
        if self.min_learning_rate < 0.0:
            raise RecipeError(
                f"min_learning_rate must be >= 0 (got {self.min_learning_rate})"
            )
        if self.min_learning_rate > self.learning_rate:
            raise RecipeError(
                f"min_learning_rate ({self.min_learning_rate}) must be <= "
                f"learning_rate ({self.learning_rate})"
            )
        if not 0.0 <= self.lr_warmup_fraction <= 1.0:
            raise RecipeError(
                f"lr_warmup_fraction must be in [0, 1] "
                f"(got {self.lr_warmup_fraction})"
            )

        if self.max_steps < 1:
            raise RecipeError(f"max_steps must be >= 1 (got {self.max_steps})")
        if self.save_interval < 1:
            raise RecipeError(
                f"save_interval must be >= 1 (got {self.save_interval})"
            )
        if self.most_recent_k == 0 or self.most_recent_k < -1:
            raise RecipeError(
                f"most_recent_k must be -1 (keep-all) or >= 1 "
                f"(got {self.most_recent_k})"
            )
        if self.smoke_steps < 1:
            raise RecipeError(
                f"smoke_steps must be >= 1 (got {self.smoke_steps})"
            )
        if self.smoke_steps > self.max_steps:
            raise RecipeError(
                f"smoke_steps ({self.smoke_steps}) must be <= "
                f"max_steps ({self.max_steps}) — smoke is a strict subset"
            )

    def preflight(self) -> None:
        """Filesystem-level checks. Raises ``RecipeError`` on miss.

        Separate from ``validate()`` so unit tests cover the pure-python
        rules without fixturing every path. Callers (CLI, ``run()``)
        invoke both in order.
        """
        self.validate()
        bm = Path(self.base_model)
        if not bm.exists():
            raise RecipeError(
                f"base_model path does not exist: {self.base_model!r}"
            )
        ds = Path(self.dataset_jsonl)
        if not ds.exists():
            raise RecipeError(
                f"dataset_jsonl path does not exist: {self.dataset_jsonl!r}"
            )
        out = Path(self.output_dir).resolve()
        parent = out.parent
        if not parent.exists():
            raise RecipeError(
                f"output_dir parent does not exist: {parent} — "
                f"create it before calling run()"
            )

    # ------------------------------------------------------------------
    # YAML round-trip (no pyyaml dep — fieldkit base deps are minimal,
    # so we hand-roll the trivial subset we need)
    # ------------------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        """Plain-dict representation suitable for ``yaml.safe_dump`` /
        ``json.dump`` / hashing.

        Tuples flatten to lists so the round-trip is YAML-clean; the
        ``from_dict`` constructor re-tuples ``lora_target_modules``.
        """
        d: dict[str, Any] = asdict(self)
        d["lora_target_modules"] = list(self.lora_target_modules)
        d["extra_env"] = dict(self.extra_env)
        return d

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "TrainRecipe":
        """Construct from a plain dict (e.g. the ``yaml.safe_load`` of
        a recipe file).

        Unknown keys raise ``RecipeError`` so a typo in the YAML
        surfaces immediately instead of silently dropping the field.
        """
        known = {f.name for f in fields(cls)}
        unknown = set(data) - known
        if unknown:
            raise RecipeError(
                f"unknown recipe field(s): {sorted(unknown)} — "
                f"valid fields: {sorted(known)}"
            )
        kwargs: dict[str, Any] = dict(data)
        if "lora_target_modules" in kwargs:
            kwargs["lora_target_modules"] = tuple(kwargs["lora_target_modules"])
        if "extra_env" in kwargs:
            kwargs["extra_env"] = dict(kwargs["extra_env"])
        return cls(**kwargs)

    def to_yaml(self, path: str | Path) -> Path:
        """Write the recipe to ``path`` as YAML.

        Uses the optional ``yaml`` dep if available; otherwise falls
        back to a hand-rolled minimal renderer good enough for the flat
        schema this dataclass produces. Returns the resolved path.
        """
        p = Path(path).resolve()
        p.parent.mkdir(parents=True, exist_ok=True)
        try:
            import yaml  # type: ignore[import-untyped]

            text = yaml.safe_dump(
                self.to_dict(), sort_keys=False, default_flow_style=False
            )
        except ImportError:
            text = _hand_yaml(self.to_dict())
        p.write_text(text, encoding="utf-8")
        return p

    @classmethod
    def from_yaml(cls, path: str | Path) -> "TrainRecipe":
        """Load a recipe from ``path``. JSON is accepted transparently
        — pyyaml's loader handles flat-JSON shape too, but we also fall
        back to ``json.loads`` if pyyaml is unavailable."""
        p = Path(path)
        text = p.read_text(encoding="utf-8")
        try:
            import yaml  # type: ignore[import-untyped]

            data = yaml.safe_load(text)
        except ImportError:
            data = json.loads(text)
        if not isinstance(data, dict):
            raise RecipeError(
                f"recipe file {p} did not parse to a mapping (got {type(data).__name__})"
            )
        return cls.from_dict(data)

    # ------------------------------------------------------------------
    # Backend-specific helpers (no side effects)
    # ------------------------------------------------------------------

    def resolved_container(self) -> str:
        """Resolve the docker container name for this recipe's backend.

        Returns the explicit ``container`` field when set; otherwise the
        backend default. Callers use this for ``docker exec`` plumbing
        in ``fieldkit.training.run``.
        """
        if self.container:
            return self.container
        if self.backend == "nemo":
            return "nemo-train"
        return "ps-train"

    def lora_target_modules_for_backend(self) -> tuple[str, ...]:
        """Map the HF-flavoured ``lora_target_modules`` to the backend's
        actual module-name vocabulary.

        NeMo's Megatron-Bridge LoRA fuses q/k/v into ``linear_qkv`` and
        names the output projection ``linear_proj``. Unsloth keeps the
        HF names verbatim. The recipe stays portable; the mapping
        happens at runtime so a single recipe file drives either lane.
        """
        if self.backend != "nemo":
            return self.lora_target_modules
        hf = {m.lower() for m in self.lora_target_modules}
        mapped: list[str] = []
        if hf & {"q_proj", "k_proj", "v_proj"}:
            mapped.append("linear_qkv")
        if "o_proj" in hf:
            mapped.append("linear_proj")
        if {"gate_proj", "up_proj"} & hf:
            mapped.append("linear_fc1")
        if "down_proj" in hf:
            mapped.append("linear_fc2")
        if not mapped:
            raise RecipeError(
                f"lora_target_modules {self.lora_target_modules!r} did not "
                f"map to any known NeMo target (expected subset of "
                f"q_proj/k_proj/v_proj/o_proj/gate_proj/up_proj/down_proj)"
            )
        return tuple(mapped)


def _hand_yaml(data: Mapping[str, Any]) -> str:
    """Minimal YAML renderer for the flat shapes ``TrainRecipe`` produces.

    Used only when ``pyyaml`` is not installed in the env; covers
    scalars + flat lists + the single ``extra_env`` dict-of-strings
    field. Anything richer should pull in ``pyyaml`` via the optional
    ``[recipe]`` extra.
    """
    lines: list[str] = []
    for k, v in data.items():
        if isinstance(v, bool):
            lines.append(f"{k}: {'true' if v else 'false'}")
        elif v is None:
            lines.append(f"{k}: null")
        elif isinstance(v, (int, float)):
            lines.append(f"{k}: {v}")
        elif isinstance(v, str):
            lines.append(f"{k}: {_scalar_str(v)}")
        elif isinstance(v, list):
            if not v:
                lines.append(f"{k}: []")
            else:
                lines.append(f"{k}:")
                for item in v:
                    lines.append(f"  - {_scalar_str(str(item))}")
        elif isinstance(v, dict):
            if not v:
                lines.append(f"{k}: {{}}")
            else:
                lines.append(f"{k}:")
                for kk, vv in v.items():
                    lines.append(f"  {kk}: {_scalar_str(str(vv))}")
        else:
            lines.append(f"{k}: {_scalar_str(str(v))}")
    return "\n".join(lines) + "\n"


def _scalar_str(s: str) -> str:
    """Quote strings that need YAML quoting; bare-emit the rest.

    Bare-safe: alphanumerics, ``_``, ``-``, ``.``, ``/`` (paths). Anything
    else gets JSON-quoted, which YAML accepts as a quoted scalar.
    """
    if s == "":
        return '""'
    safe = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-./")
    if all(c in safe for c in s) and not s[0].isdigit():
        return s
    return json.dumps(s)
