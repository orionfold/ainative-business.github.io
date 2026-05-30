# Copyright 2026 Manav Sehgal
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for `fieldkit.training.convert`.

Pure-python — no torch import. Three surfaces under test:

- `patch_yarn_defaults(provider)` — duck-typed fake provider via
  `types.SimpleNamespace`; no megatron-bridge dependency.
- `register_llama_cpp_pretokenizer_hash(...)` — synthetic minimal
  `convert_hf_to_gguf.py` fixture; no llama.cpp checkout needed.
- `HFToMegatron.run()` — the "no torch / no megatron-bridge" failure
  path raises a clear `ConvertError`. The happy path is tested in
  `--spark`-gated integration paths (out of scope here).
"""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from fieldkit.training import (
    DEEPSEEK_R1_0528_QWEN3_TOKENIZER_HASH,
    ConvertError,
    HFToMegatron,
    YARN_DEFAULTS,
    patch_yarn_defaults,
    register_llama_cpp_pretokenizer_hash,
)


# --- patch_yarn_defaults ----------------------------------------------------


def test_yarn_defaults_constant_shape() -> None:
    """The defaults dict carries exactly the five fields that
    Megatron-Bridge 0.4.0rc0 leaves None on YARN models."""
    assert set(YARN_DEFAULTS) == {
        "yarn_beta_fast",
        "yarn_beta_slow",
        "yarn_mscale",
        "yarn_mscale_all_dim",
        "yarn_correction_range_round_to_int",
    }


def test_patch_yarn_defaults_skips_non_yarn_provider() -> None:
    """Non-YARN providers return an empty patch list AND no fields are
    written (the function exits before reaching the YARN field loop)."""
    provider = SimpleNamespace(position_embedding_type="rope")
    patched = patch_yarn_defaults(provider)
    assert patched == []
    # Verify no YARN field was set as a side effect.
    for field_name in YARN_DEFAULTS:
        assert not hasattr(provider, field_name)


def test_patch_yarn_defaults_patches_when_all_none() -> None:
    """A YARN provider with all five fields == None gets all five patched."""
    provider = SimpleNamespace(
        position_embedding_type="yarn",
        yarn_beta_fast=None,
        yarn_beta_slow=None,
        yarn_mscale=None,
        yarn_mscale_all_dim=None,
        yarn_correction_range_round_to_int=None,
    )
    patched = patch_yarn_defaults(provider)
    assert set(patched) == set(YARN_DEFAULTS)
    assert provider.yarn_beta_fast == 32.0
    assert provider.yarn_beta_slow == 1.0
    assert provider.yarn_mscale == 1.0
    assert provider.yarn_mscale_all_dim == 0.0
    assert provider.yarn_correction_range_round_to_int is True


def test_patch_yarn_defaults_preserves_already_set_fields() -> None:
    """User-set YARN values aren't clobbered."""
    provider = SimpleNamespace(
        position_embedding_type="yarn",
        yarn_beta_fast=64.0,
        yarn_beta_slow=None,
        yarn_mscale=None,
        yarn_mscale_all_dim=None,
        yarn_correction_range_round_to_int=None,
    )
    patched = patch_yarn_defaults(provider)
    assert "yarn_beta_fast" not in patched
    assert provider.yarn_beta_fast == 64.0  # preserved


def test_patch_yarn_defaults_is_idempotent() -> None:
    """Calling twice on the same YARN provider is a no-op the second time."""
    provider = SimpleNamespace(
        position_embedding_type="yarn",
        yarn_beta_fast=None,
        yarn_beta_slow=None,
        yarn_mscale=None,
        yarn_mscale_all_dim=None,
        yarn_correction_range_round_to_int=None,
    )
    patch_yarn_defaults(provider)
    second = patch_yarn_defaults(provider)
    assert second == []


def test_patch_yarn_defaults_handles_missing_attrs() -> None:
    """A YARN provider missing some attrs entirely still gets them set
    via setattr — the bug's surface is exactly None vs not-present, and
    we treat both equivalently."""
    provider = SimpleNamespace(position_embedding_type="yarn")
    patched = patch_yarn_defaults(provider)
    assert set(patched) == set(YARN_DEFAULTS)
    assert provider.yarn_beta_fast == 32.0


# --- register_llama_cpp_pretokenizer_hash -----------------------------------


_FAKE_CONVERT_SCRIPT = '''\
"""minimal convert_hf_to_gguf.py fixture."""

class Foo:
    def get_vocab_base_pre(self, tokenizer):
        chkhsh = "abc"
        if chkhsh == "0000000000000000000000000000000000000000000000000000000000000000":
            res = "llama-bpe"
        if chkhsh == "1111111111111111111111111111111111111111111111111111111111111111":
            # ref: https://huggingface.co/example/model
            res = "qwen2"
        return res
'''


@pytest.fixture
def fake_convert_script(tmp_path: Path) -> Path:
    p = tmp_path / "convert_hf_to_gguf.py"
    p.write_text(_FAKE_CONVERT_SCRIPT, encoding="utf-8")
    return p


def test_register_inserts_new_block(fake_convert_script: Path) -> None:
    new_hash = "0d75215efe33c49084836cb245f2fa78de4b3858f5a3e54d5e1fd27f4ce33b05"
    inserted = register_llama_cpp_pretokenizer_hash(
        fake_convert_script,
        chkhsh=new_hash,
        pre_tokenizer="qwen35",
        model_ref="https://huggingface.co/deepseek-ai/DeepSeek-R1-0528-Qwen3-8B",
        note="Qwen3 BPE + Metaspace + DeepSeek special tokens",
    )
    assert inserted is True
    text = fake_convert_script.read_text(encoding="utf-8")
    assert new_hash in text
    assert 'res = "qwen35"' in text
    assert "# ref: https://huggingface.co/deepseek-ai/DeepSeek-R1-0528-Qwen3-8B" in text
    assert "# Qwen3 BPE + Metaspace + DeepSeek special tokens" in text


def test_register_is_idempotent(fake_convert_script: Path) -> None:
    new_hash = "0d75215efe33c49084836cb245f2fa78de4b3858f5a3e54d5e1fd27f4ce33b05"
    first = register_llama_cpp_pretokenizer_hash(
        fake_convert_script, chkhsh=new_hash, pre_tokenizer="qwen35"
    )
    second = register_llama_cpp_pretokenizer_hash(
        fake_convert_script, chkhsh=new_hash, pre_tokenizer="qwen35"
    )
    assert first is True
    assert second is False
    # And the file should only contain one occurrence of the hash.
    text = fake_convert_script.read_text(encoding="utf-8")
    assert text.count(new_hash) == 1


def test_register_preserves_existing_chain(fake_convert_script: Path) -> None:
    """Existing blocks in the chain stay byte-identical after insertion."""
    original = fake_convert_script.read_text(encoding="utf-8")
    new_hash = "0d75215efe33c49084836cb245f2fa78de4b3858f5a3e54d5e1fd27f4ce33b05"
    register_llama_cpp_pretokenizer_hash(
        fake_convert_script, chkhsh=new_hash, pre_tokenizer="qwen35"
    )
    after = fake_convert_script.read_text(encoding="utf-8")
    # The original chain blocks must still be present verbatim.
    assert (
        'if chkhsh == "0000000000000000000000000000000000000000000000000000000000000000":'
        in after
    )
    assert (
        'if chkhsh == "1111111111111111111111111111111111111111111111111111111111111111":'
        in after
    )
    # And the new block must come AFTER the prior last block.
    last_existing = after.index(
        '1111111111111111111111111111111111111111111111111111111111111111'
    )
    new_pos = after.index(new_hash)
    assert new_pos > last_existing
    # Header docstring must survive.
    assert after.startswith(original.split("\n")[0])


def test_register_rejects_non_hex_hash(fake_convert_script: Path) -> None:
    with pytest.raises(ConvertError, match="64-char hex digest"):
        register_llama_cpp_pretokenizer_hash(
            fake_convert_script,
            chkhsh="nothex" * 11,  # 66 chars, not hex
            pre_tokenizer="qwen35",
        )


def test_register_rejects_short_hash(fake_convert_script: Path) -> None:
    with pytest.raises(ConvertError, match="64-char hex digest"):
        register_llama_cpp_pretokenizer_hash(
            fake_convert_script,
            chkhsh="abcdef",
            pre_tokenizer="qwen35",
        )


def test_register_raises_on_missing_file(tmp_path: Path) -> None:
    with pytest.raises(ConvertError, match="not found"):
        register_llama_cpp_pretokenizer_hash(
            tmp_path / "does-not-exist.py",
            chkhsh="0" * 64,
            pre_tokenizer="qwen35",
        )


def test_register_raises_when_chain_pattern_missing(tmp_path: Path) -> None:
    """A file with no `if chkhsh == "...":` chain raises a clear error."""
    p = tmp_path / "convert_hf_to_gguf.py"
    p.write_text("# wrong file, no chain here\nprint('hello')\n", encoding="utf-8")
    with pytest.raises(ConvertError, match="could not locate"):
        register_llama_cpp_pretokenizer_hash(
            p, chkhsh="0" * 64, pre_tokenizer="qwen35"
        )


# --- HFToMegatron -----------------------------------------------------------


def test_hf_to_megatron_dataclass_fields() -> None:
    """The dataclass carries the expected (hf_model, megatron_path, dtype)
    surface and is frozen."""
    job = HFToMegatron(
        hf_model="/tmp/source-model",
        megatron_path="/tmp/dest-mcore",
    )
    assert str(job.hf_model) == "/tmp/source-model"
    assert str(job.megatron_path) == "/tmp/dest-mcore"
    assert job.torch_dtype == "bfloat16"  # default
    with pytest.raises((AttributeError, Exception)):
        # frozen dataclass — assignment must fail
        job.torch_dtype = "float16"  # type: ignore[misc]


def test_hf_to_megatron_run_raises_clear_error_without_torch() -> None:
    """In a venv without torch+megatron-bridge, .run() must raise
    ConvertError with a clear pointer to the nemo-train container.
    `/tmp/fk` venv lacks megatron-bridge so this is the path we exercise."""
    job = HFToMegatron(hf_model="/no/such/path", megatron_path="/tmp/never")
    try:
        import megatron.bridge  # noqa: F401
    except ImportError:
        with pytest.raises(ConvertError, match="megatron-bridge"):
            job.run()
    else:
        pytest.skip("megatron-bridge is installed; ImportError path not exercised")


# --- The exported DeepSeek-R1 constant --------------------------------------


def test_deepseek_r1_qwen3_hash_constant_format() -> None:
    """64-char lowercase hex digest, matches the value from
    `[[reference_deepseek_r1_0528_qwen3_tokenizer_hash]]`."""
    h = DEEPSEEK_R1_0528_QWEN3_TOKENIZER_HASH
    assert len(h) == 64
    assert all(c in "0123456789abcdef" for c in h)
    assert h == "0d75215efe33c49084836cb245f2fa78de4b3858f5a3e54d5e1fd27f4ce33b05"
