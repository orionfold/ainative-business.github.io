# Copyright 2026 Manav Sehgal
# SPDX-License-Identifier: Apache-2.0
"""HF → Megatron-Core checkpoint conversion + llama.cpp pretokenizer registration.

Absorbs two patches that the patent-strategist v3 NeMo lane discovered
the hard way (session 2026-05-21):

1. ``patch_yarn_defaults`` — Megatron-Bridge 0.4.0rc0 leaves the YARN-rope
   hyperparameters (``yarn_beta_fast`` / ``yarn_beta_slow`` / ``yarn_mscale``
   / ``yarn_mscale_all_dim``) as ``None`` after ``to_megatron_provider``.
   The downstream ``YarnRotaryEmbedding`` then crashes in
   ``_yarn_find_correction_dim`` because ``None * math.pi`` is invalid.
   See ``[[feedback_megatron_bridge_yarn_defaults]]``.

2. ``register_llama_cpp_pretokenizer_hash`` — llama.cpp's
   ``convert_hf_to_gguf.py`` reads the source tokenizer's BPE merge-hash
   and maps it to a named pre-tokenizer (``qwen35``, ``llama-bpe``, ...)
   via a long chain of literal-hash ``if``-checks. New hashes
   (e.g. DeepSeek-R1-0528-Qwen3-8B's ``0d75215...``) aren't yet upstream;
   this helper idempotently appends the mapping so a fresh ``git pull``
   on the llama.cpp checkout can be re-patched in one call.
   See ``[[reference_deepseek_r1_0528_qwen3_tokenizer_hash]]``.

The ``HFToMegatron`` dataclass wraps ``megatron.bridge.AutoBridge`` with
the YARN patch baked in, mirroring ``scripts/p65_convert_hf_to_mcore.py``.
Lazy-imports torch + bridge so module import has no GPU cost.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, Optional


__all__ = [
    "ConvertError",
    "DEEPSEEK_R1_0528_QWEN3_TOKENIZER_HASH",
    "HFToMegatron",
    "YARN_DEFAULTS",
    "patch_yarn_defaults",
    "register_llama_cpp_pretokenizer_hash",
]


YARN_DEFAULTS: dict[str, float | bool] = {
    "yarn_beta_fast": 32.0,
    "yarn_beta_slow": 1.0,
    "yarn_mscale": 1.0,
    "yarn_mscale_all_dim": 0.0,
    "yarn_correction_range_round_to_int": True,
}
"""Defaults from ``megatron.core.models.common.embeddings.yarn_rotary_pos_embedding``.

The bridge step sets ``yarn_rotary_scaling_factor`` +
``yarn_original_max_position_embeddings`` but leaves these as ``None``;
``YarnRotaryEmbedding`` then dies on ``None * math.pi``. Used by
``patch_yarn_defaults`` as the patch-source dictionary."""


DEEPSEEK_R1_0528_QWEN3_TOKENIZER_HASH = (
    "0d75215efe33c49084836cb245f2fa78de4b3858f5a3e54d5e1fd27f4ce33b05"
)
"""BPE merge-hash for ``deepseek-ai/DeepSeek-R1-0528-Qwen3-8B``.

Qwen3 BPE + Metaspace pre-tokenizer + DeepSeek special tokens. Not yet
upstream in llama.cpp as of b9276 (2026-05-21). Register with the
``qwen35`` pre-tokenizer via ``register_llama_cpp_pretokenizer_hash(...,
pre_tokenizer='qwen35')``."""


class ConvertError(RuntimeError):
    """Raised when a conversion step fails or its inputs are malformed.

    Distinct from generic ``RuntimeError`` so callers can selectively
    catch convert-stage failures vs other exceptions.
    """


def patch_yarn_defaults(provider: Any) -> list[str]:
    """Set YARN-rope defaults on a provider that left them ``None``.

    Idempotent: only patches fields where ``getattr(provider, field, None)``
    is ``None``. Returns the list of field names that were actually
    patched. Empty list signals either "non-YARN model" (skipped) or
    "all already set" (no-op).

    Callers should run this between ``bridge.to_megatron_provider(...)``
    and ``provider.provide_distributed_model(...)``. ``HFToMegatron.run()``
    does this automatically.
    """
    if getattr(provider, "position_embedding_type", None) != "yarn":
        return []
    patched: list[str] = []
    for field_name, value in YARN_DEFAULTS.items():
        if getattr(provider, field_name, None) is None:
            setattr(provider, field_name, value)
            patched.append(field_name)
    return patched


@dataclass(frozen=True)
class HFToMegatron:
    """HF → Megatron-Core checkpoint conversion with the YARN-rope fix baked in.

    Wraps ``megatron.bridge.AutoBridge`` with the YARN patch from
    ``scripts/p65_convert_hf_to_mcore.py``. Construct + call ``run()``.

    Run inside ``nvcr.io/nvidia/nemo:26.04.00`` (container ``nemo-train``).
    Outside that envelope ``run()`` raises ``ConvertError`` with a clear
    pointer; module-level imports stay cheap.
    """

    hf_model: str | Path
    """HF model path (snapshot dir) or repo id. The source for both
    weights and the tokenizer carried into the Megatron checkpoint."""

    megatron_path: str | Path
    """Target Megatron-Core checkpoint directory. Created if absent."""

    torch_dtype: Literal["bfloat16", "float16", "float32"] = "bfloat16"

    def run(self) -> dict[str, Any]:
        """Execute the conversion. Returns a summary dict.

        Raises ``ConvertError`` on missing dependencies. Re-raises any
        unexpected exceptions from the bridge with traceback intact.

        The summary includes the list of YARN fields actually patched
        — empty for non-YARN models, useful for sanity-checking the
        patch is doing what you expect.
        """
        try:
            import torch
            from megatron.bridge import AutoBridge
        except ImportError as exc:
            raise ConvertError(
                "fieldkit.training.convert.HFToMegatron requires torch + "
                "megatron-bridge. Run inside `nvcr.io/nvidia/nemo:26.04.00` "
                "(container `nemo-train`)."
            ) from exc

        dtype_map = {
            "bfloat16": torch.bfloat16,
            "float16": torch.float16,
            "float32": torch.float32,
        }
        torch_dtype = dtype_map[self.torch_dtype]

        bridge = AutoBridge.from_hf_pretrained(
            str(self.hf_model), torch_dtype=torch_dtype
        )
        provider = bridge.to_megatron_provider(load_weights=True)
        patched = patch_yarn_defaults(provider)
        if hasattr(provider, "finalize"):
            provider.finalize()
        megatron_model = provider.provide_distributed_model(
            wrap_with_ddp=False,
            use_cpu_initialization=True,
        )

        out = Path(self.megatron_path)
        out.mkdir(parents=True, exist_ok=True)
        hf_tokenizer_kwargs: dict[str, Any] = {}
        if hasattr(bridge._model_bridge, "get_hf_tokenizer_kwargs"):
            hf_tokenizer_kwargs = bridge._model_bridge.get_hf_tokenizer_kwargs()
        bridge.save_megatron_model(
            megatron_model,
            str(out),
            hf_tokenizer_path=str(self.hf_model),
            hf_tokenizer_kwargs=hf_tokenizer_kwargs,
            low_memory_save=True,
        )

        return {
            "hf_model": str(self.hf_model),
            "megatron_path": str(out),
            "torch_dtype": self.torch_dtype,
            "yarn_patched_fields": list(patched),
            "position_embedding_type": getattr(
                provider, "position_embedding_type", None
            ),
        }


# ---------------------------------------------------------------------------
# llama.cpp convert_hf_to_gguf pre-tokenizer registration
# ---------------------------------------------------------------------------

_CHKHSH_BLOCK_RE = re.compile(
    r'^(?P<indent>[ \t]+)if chkhsh == "[0-9a-f]{64}":\s*\n'
    r'(?:(?P=indent)[ \t]+#[^\n]*\n)*'
    r'(?P=indent)[ \t]+res = "[^"]+"\s*\n',
    re.MULTILINE,
)


def register_llama_cpp_pretokenizer_hash(
    convert_script: str | Path,
    *,
    chkhsh: str,
    pre_tokenizer: str,
    model_ref: Optional[str] = None,
    note: Optional[str] = None,
) -> bool:
    """Idempotently register a tokenizer-hash → pre-tokenizer mapping.

    Inserts a small block into the chain of ``if chkhsh == "...":``
    statements in llama.cpp's ``convert_hf_to_gguf.py``
    ``get_vocab_base_pre`` method. Re-applies after a fresh ``git pull``
    on the llama.cpp checkout.

    Returns ``True`` if a new block was inserted, ``False`` if the hash
    was already present (no-op). The script is rewritten in place.

    Args:
        convert_script: Path to ``convert_hf_to_gguf.py``.
        chkhsh: 64-char hex BPE merge-hash to register.
        pre_tokenizer: Pre-tokenizer name (e.g. ``"qwen35"``, ``"llama-bpe"``).
        model_ref: Optional HF repo URL emitted as a ``# ref:`` comment.
        note: Optional second-line comment explaining the entry.

    Raises:
        ConvertError: If the script is missing, the hash isn't a valid
            64-char hex digest, or the chain pattern can't be located.
    """
    p = Path(convert_script)
    if not p.is_file():
        raise ConvertError(f"convert_hf_to_gguf.py not found at {p}")
    if len(chkhsh) != 64 or any(c not in "0123456789abcdef" for c in chkhsh.lower()):
        raise ConvertError(
            f"chkhsh must be a 64-char hex digest (got {len(chkhsh)} chars)"
        )

    text = p.read_text(encoding="utf-8")
    if chkhsh in text:
        return False

    matches = list(_CHKHSH_BLOCK_RE.finditer(text))
    if not matches:
        raise ConvertError(
            f"could not locate `if chkhsh == \"...\":` chain in {p} — "
            f"is this really convert_hf_to_gguf.py?"
        )
    last = matches[-1]
    indent = last.group("indent")
    block_lines = [f'{indent}if chkhsh == "{chkhsh}":']
    if model_ref:
        block_lines.append(f"{indent}    # ref: {model_ref}")
    if note:
        block_lines.append(f"{indent}    # {note}")
    block_lines.append(f'{indent}    res = "{pre_tokenizer}"')
    insertion = "\n".join(block_lines) + "\n"
    new_text = text[: last.end()] + insertion + text[last.end():]
    p.write_text(new_text, encoding="utf-8")
    return True
