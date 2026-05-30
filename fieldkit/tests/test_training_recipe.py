# Copyright 2026 Manav Sehgal
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for `fieldkit.training.recipe` — the declarative
``TrainRecipe`` dataclass.

Pure-python tests; no torch import. Covers validation rules, YAML
round-trip, and backend-target-module mapping.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from fieldkit.training import MODE_FULL, MODE_SMOKE, RecipeError, TrainRecipe


# --- Fixtures ----------------------------------------------------------------


@pytest.fixture
def good_recipe(tmp_path: Path) -> TrainRecipe:
    """A minimal, valid recipe whose paths exist on disk."""
    bm = tmp_path / "base_model"
    bm.mkdir()
    ds = tmp_path / "corpus.jsonl"
    ds.write_text('{"input":"x","output":"y"}\n', encoding="utf-8")
    out = tmp_path / "runs"
    out.parent.mkdir(parents=True, exist_ok=True)  # parent exists; out itself does not (OK)
    return TrainRecipe(
        base_model=str(bm),
        dataset_jsonl=str(ds),
        output_dir=str(out),
    )


# --- Construction + defaults --------------------------------------------------


def test_minimal_recipe_validates() -> None:
    r = TrainRecipe(
        base_model="/no/such/path",
        dataset_jsonl="/no/such/file",
        output_dir="/tmp/out",
    )
    # validate() is offline — should pass even with bogus paths.
    r.validate()


def test_defaults_match_phase65_setup() -> None:
    """Defaults track the Phase 6.5 patent-strategist v3 setup so a
    fresh recipe is a drop-in for that lane."""
    r = TrainRecipe(
        base_model="/x", dataset_jsonl="/x", output_dir="/x"
    )
    assert r.backend == "nemo"
    assert r.lora_rank == 16
    assert r.lora_alpha == 32
    assert r.lora_dropout == 0.05
    assert r.lora_target_modules == ("q_proj", "k_proj", "v_proj", "o_proj")
    assert r.seq_length == 4096
    assert r.micro_batch_size == 2
    assert r.global_batch_size == 16
    assert r.learning_rate == 1e-4
    assert r.lr_schedule == "cosine"
    assert r.lr_warmup_fraction == 0.05
    assert r.max_steps == 625
    assert r.save_interval == 50
    assert r.smoke_steps == 10
    assert r.torch_dtype == "bfloat16"
    assert r.seed == 42


def test_mode_constants() -> None:
    assert MODE_FULL == "full"
    assert MODE_SMOKE == "smoke"


def test_recipe_is_frozen() -> None:
    r = TrainRecipe(base_model="/x", dataset_jsonl="/x", output_dir="/x")
    with pytest.raises((AttributeError, Exception)):
        r.lora_rank = 32  # type: ignore[misc]


# --- validate() rules --------------------------------------------------------


def test_validate_rejects_unknown_backend() -> None:
    r = TrainRecipe(
        base_model="/x", dataset_jsonl="/x", output_dir="/x", backend="megatron"
    )  # type: ignore[arg-type]
    with pytest.raises(RecipeError, match="backend"):
        r.validate()


@pytest.mark.parametrize("rank", [0, -1])
def test_validate_rejects_bad_lora_rank(rank: int) -> None:
    r = TrainRecipe(
        base_model="/x", dataset_jsonl="/x", output_dir="/x", lora_rank=rank
    )
    with pytest.raises(RecipeError, match="lora_rank"):
        r.validate()


@pytest.mark.parametrize("dropout", [-0.01, 1.0, 1.5])
def test_validate_rejects_bad_lora_dropout(dropout: float) -> None:
    r = TrainRecipe(
        base_model="/x", dataset_jsonl="/x", output_dir="/x", lora_dropout=dropout
    )
    with pytest.raises(RecipeError, match="lora_dropout"):
        r.validate()


def test_validate_rejects_empty_lora_targets() -> None:
    r = TrainRecipe(
        base_model="/x",
        dataset_jsonl="/x",
        output_dir="/x",
        lora_target_modules=(),
    )
    with pytest.raises(RecipeError, match="lora_target_modules"):
        r.validate()


def test_validate_rejects_nemo_seq_length_not_multiple_of_64() -> None:
    r = TrainRecipe(
        base_model="/x",
        dataset_jsonl="/x",
        output_dir="/x",
        backend="nemo",
        seq_length=4100,
    )
    with pytest.raises(RecipeError, match="seq_length"):
        r.validate()


def test_validate_accepts_unsloth_non_64_seq_length() -> None:
    """Unsloth doesn't carry the Megatron tensor-layout constraint."""
    r = TrainRecipe(
        base_model="/x",
        dataset_jsonl="/x",
        output_dir="/x",
        backend="unsloth",
        seq_length=4100,
    )
    r.validate()


def test_validate_rejects_global_not_multiple_of_micro() -> None:
    r = TrainRecipe(
        base_model="/x",
        dataset_jsonl="/x",
        output_dir="/x",
        micro_batch_size=3,
        global_batch_size=16,
    )
    with pytest.raises(RecipeError, match="multiple"):
        r.validate()


def test_validate_rejects_global_less_than_micro() -> None:
    r = TrainRecipe(
        base_model="/x",
        dataset_jsonl="/x",
        output_dir="/x",
        micro_batch_size=8,
        global_batch_size=4,
    )
    with pytest.raises(RecipeError, match=">=.*micro_batch"):
        r.validate()


def test_validate_rejects_min_lr_above_lr() -> None:
    r = TrainRecipe(
        base_model="/x",
        dataset_jsonl="/x",
        output_dir="/x",
        learning_rate=1e-4,
        min_learning_rate=1e-3,
    )
    with pytest.raises(RecipeError, match="min_learning_rate"):
        r.validate()


def test_validate_rejects_smoke_above_max() -> None:
    r = TrainRecipe(
        base_model="/x",
        dataset_jsonl="/x",
        output_dir="/x",
        max_steps=10,
        smoke_steps=20,
    )
    with pytest.raises(RecipeError, match="smoke_steps"):
        r.validate()


@pytest.mark.parametrize("k", [0, -2, -5])
def test_validate_rejects_bad_most_recent_k(k: int) -> None:
    r = TrainRecipe(
        base_model="/x",
        dataset_jsonl="/x",
        output_dir="/x",
        most_recent_k=k,
    )
    with pytest.raises(RecipeError, match="most_recent_k"):
        r.validate()


def test_validate_accepts_most_recent_k_keep_all() -> None:
    r = TrainRecipe(
        base_model="/x",
        dataset_jsonl="/x",
        output_dir="/x",
        most_recent_k=-1,
    )
    r.validate()


@pytest.mark.parametrize("warmup", [-0.01, 1.01, 2.0])
def test_validate_rejects_bad_warmup_fraction(warmup: float) -> None:
    r = TrainRecipe(
        base_model="/x",
        dataset_jsonl="/x",
        output_dir="/x",
        lr_warmup_fraction=warmup,
    )
    with pytest.raises(RecipeError, match="lr_warmup_fraction"):
        r.validate()


# --- preflight() rules --------------------------------------------------------


def test_preflight_happy_path(good_recipe: TrainRecipe) -> None:
    good_recipe.preflight()


def test_preflight_rejects_missing_base_model(tmp_path: Path) -> None:
    ds = tmp_path / "corpus.jsonl"
    ds.write_text("{}\n", encoding="utf-8")
    r = TrainRecipe(
        base_model=str(tmp_path / "missing"),
        dataset_jsonl=str(ds),
        output_dir=str(tmp_path / "runs"),
    )
    with pytest.raises(RecipeError, match="base_model"):
        r.preflight()


def test_preflight_rejects_missing_dataset(tmp_path: Path) -> None:
    bm = tmp_path / "base_model"
    bm.mkdir()
    r = TrainRecipe(
        base_model=str(bm),
        dataset_jsonl=str(tmp_path / "missing.jsonl"),
        output_dir=str(tmp_path / "runs"),
    )
    with pytest.raises(RecipeError, match="dataset_jsonl"):
        r.preflight()


def test_preflight_rejects_missing_output_parent(tmp_path: Path) -> None:
    bm = tmp_path / "base_model"
    bm.mkdir()
    ds = tmp_path / "corpus.jsonl"
    ds.write_text("{}\n", encoding="utf-8")
    r = TrainRecipe(
        base_model=str(bm),
        dataset_jsonl=str(ds),
        output_dir=str(tmp_path / "missing" / "more-missing" / "runs"),
    )
    with pytest.raises(RecipeError, match="output_dir parent"):
        r.preflight()


# --- YAML round-trip ---------------------------------------------------------


def test_to_dict_round_trip() -> None:
    r = TrainRecipe(
        base_model="/x",
        dataset_jsonl="/x",
        output_dir="/x",
        extra_env={"NCCL_DEBUG": "WARN"},
        notes="phase 6.5 patent-strategist v3",
    )
    d = r.to_dict()
    assert isinstance(d["lora_target_modules"], list)
    assert isinstance(d["extra_env"], dict)
    r2 = TrainRecipe.from_dict(d)
    assert r == r2


def test_from_dict_rejects_unknown_field() -> None:
    with pytest.raises(RecipeError, match="unknown recipe field"):
        TrainRecipe.from_dict(
            {
                "base_model": "/x",
                "dataset_jsonl": "/x",
                "output_dir": "/x",
                "lora_rnak": 16,  # typo
            }
        )


def test_yaml_round_trip_via_file(tmp_path: Path) -> None:
    r = TrainRecipe(
        base_model="/data/base",
        dataset_jsonl="/data/corpus.jsonl",
        output_dir="/data/runs",
        notes="session 41 patent-strategist v3 nemo lane",
    )
    p = r.to_yaml(tmp_path / "recipe.yaml")
    assert p.is_file()
    r2 = TrainRecipe.from_yaml(p)
    assert r == r2


def test_from_yaml_accepts_plain_json(tmp_path: Path) -> None:
    """JSON is a valid subset of YAML; the loader must accept it."""
    p = tmp_path / "recipe.json"
    payload = {
        "base_model": "/x",
        "dataset_jsonl": "/x",
        "output_dir": "/x",
        "backend": "unsloth",
        "lora_rank": 8,
    }
    p.write_text(json.dumps(payload), encoding="utf-8")
    r = TrainRecipe.from_yaml(p)
    assert r.backend == "unsloth"
    assert r.lora_rank == 8


def test_from_yaml_rejects_non_mapping(tmp_path: Path) -> None:
    p = tmp_path / "bad.yaml"
    p.write_text("- just\n- a\n- list\n", encoding="utf-8")
    with pytest.raises(RecipeError, match="did not parse to a mapping"):
        TrainRecipe.from_yaml(p)


# --- Backend-specific helpers ------------------------------------------------


def test_resolved_container_defaults_by_backend() -> None:
    nemo = TrainRecipe(base_model="/x", dataset_jsonl="/x", output_dir="/x")
    assert nemo.resolved_container() == "nemo-train"
    unsloth = TrainRecipe(
        base_model="/x", dataset_jsonl="/x", output_dir="/x", backend="unsloth"
    )
    assert unsloth.resolved_container() == "ps-train"


def test_resolved_container_explicit_override() -> None:
    r = TrainRecipe(
        base_model="/x",
        dataset_jsonl="/x",
        output_dir="/x",
        container="custom-trainer",
    )
    assert r.resolved_container() == "custom-trainer"


def test_lora_target_modules_unsloth_keeps_hf_names() -> None:
    r = TrainRecipe(
        base_model="/x", dataset_jsonl="/x", output_dir="/x", backend="unsloth"
    )
    assert r.lora_target_modules_for_backend() == (
        "q_proj",
        "k_proj",
        "v_proj",
        "o_proj",
    )


def test_lora_target_modules_nemo_maps_to_fused() -> None:
    """q/k/v/o → linear_qkv + linear_proj (Megatron-Bridge fused names)."""
    r = TrainRecipe(base_model="/x", dataset_jsonl="/x", output_dir="/x")
    mapped = r.lora_target_modules_for_backend()
    assert mapped == ("linear_qkv", "linear_proj")


def test_lora_target_modules_nemo_full_mlp_mapping() -> None:
    """q/k/v/o + gate/up/down → linear_qkv + linear_proj + linear_fc1 + linear_fc2."""
    r = TrainRecipe(
        base_model="/x",
        dataset_jsonl="/x",
        output_dir="/x",
        lora_target_modules=(
            "q_proj",
            "k_proj",
            "v_proj",
            "o_proj",
            "gate_proj",
            "up_proj",
            "down_proj",
        ),
    )
    assert r.lora_target_modules_for_backend() == (
        "linear_qkv",
        "linear_proj",
        "linear_fc1",
        "linear_fc2",
    )


def test_lora_target_modules_nemo_rejects_unmappable() -> None:
    r = TrainRecipe(
        base_model="/x",
        dataset_jsonl="/x",
        output_dir="/x",
        lora_target_modules=("some_unknown_module",),
    )
    with pytest.raises(RecipeError, match="did not map"):
        r.lora_target_modules_for_backend()
