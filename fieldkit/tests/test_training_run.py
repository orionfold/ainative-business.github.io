# Copyright 2026 Manav Sehgal
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for `fieldkit.training.run`.

Pure-python — no torch, no docker, no megatron-bridge. The
backend-specific shell-outs are exercised via a `runner` injection
that records the command and writes synthetic `iter_NNNNNNN/`
directories to simulate a trainer.

Four surfaces under test:

- `poll_run_progress(run_dir)` — disk-poll liveness helper.
- `standardize_hf_export(hf_dir)` — the BF16-clean transformation.
- `run(recipe, ...)` — recipe → command construction → runner → poll.
- `merge_and_export(recipe, ...)` — merge + export + standardize.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Callable

import pytest

from fieldkit.training import (
    DEEPSEEK_TOKENIZER_CLASS_REMAP,
    MODE_FULL,
    MODE_SMOKE,
    MergeExportError,
    MergeExportResult,
    TrainError,
    TrainRecipe,
    TrainResult,
    merge_and_export,
    poll_run_progress,
    run,
    standardize_hf_export,
)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _write_iter_dir(run_dir: Path, iter_num: int) -> Path:
    d = run_dir / f"iter_{iter_num:07d}"
    d.mkdir(parents=True, exist_ok=True)
    (d / "common.pt").write_bytes(b"")  # presence marker
    return d


def _write_latest_file(run_dir: Path, iter_num: int) -> Path:
    p = run_dir / "latest_checkpointed_iteration.txt"
    p.write_text(f"{iter_num}\n", encoding="utf-8")
    return p


def _make_recipe(tmp_path: Path, *, backend: str = "nemo") -> TrainRecipe:
    base = tmp_path / "base-model"
    base.mkdir()
    (base / "config.json").write_text("{}", encoding="utf-8")
    ds = tmp_path / "corpus.jsonl"
    ds.write_text('{"input":"x","output":"y"}\n', encoding="utf-8")
    out = tmp_path / "runs-root"
    out.mkdir()
    return TrainRecipe(
        base_model=str(base),
        dataset_jsonl=str(ds),
        output_dir=str(out),
        backend=backend,
        max_steps=10,
        save_interval=5,
        smoke_steps=2,
        seq_length=128 if backend == "nemo" else 4,
    )


# ---------------------------------------------------------------------------
# poll_run_progress
# ---------------------------------------------------------------------------


def test_poll_run_progress_on_missing_dir(tmp_path: Path) -> None:
    """Returns (0, []) on a non-existent run dir — safe to call in a
    monitor loop before the trainer has launched."""
    latest, iters = poll_run_progress(tmp_path / "does-not-exist")
    assert latest == 0
    assert iters == []


def test_poll_run_progress_empty_run_dir(tmp_path: Path) -> None:
    """Empty dir → (0, []). Trainer hasn't written its first
    checkpoint yet."""
    run_dir = tmp_path / "runs"
    run_dir.mkdir()
    latest, iters = poll_run_progress(run_dir)
    assert latest == 0
    assert iters == []


def test_poll_run_progress_reads_latest_file(tmp_path: Path) -> None:
    """The latest_checkpointed_iteration.txt value is parsed and
    returned as `latest`."""
    run_dir = tmp_path / "runs"
    run_dir.mkdir()
    _write_latest_file(run_dir, 625)
    latest, iters = poll_run_progress(run_dir)
    assert latest == 625
    assert iters == []  # no iter_NNNNNNN/ dirs on disk yet


def test_poll_run_progress_returns_sorted_iter_dirs(tmp_path: Path) -> None:
    """iter_NNNNNNN dirs are collected, sorted ascending, and parsed
    to ints — agnostic to the order the trainer writes them."""
    run_dir = tmp_path / "runs"
    run_dir.mkdir()
    for it in (50, 200, 100, 25):
        _write_iter_dir(run_dir, it)
    _write_latest_file(run_dir, 200)
    latest, iters = poll_run_progress(run_dir)
    assert latest == 200
    assert iters == [25, 50, 100, 200]


def test_poll_run_progress_skips_non_iter_subdirs(tmp_path: Path) -> None:
    """Random sibling dirs (e.g. `logs/`, `wandb/`) are ignored —
    only iter_NNNNNNN matches."""
    run_dir = tmp_path / "runs"
    run_dir.mkdir()
    _write_iter_dir(run_dir, 50)
    (run_dir / "logs").mkdir()
    (run_dir / "iter_50").mkdir()  # short form, doesn't match 7-digit
    latest, iters = poll_run_progress(run_dir)
    assert latest == 0
    assert iters == [50]


def test_poll_run_progress_handles_unparseable_latest_file(
    tmp_path: Path,
) -> None:
    """A malformed latest file degrades gracefully to 0 — the
    iter_NNNNNNN scan is the authoritative signal anyway."""
    run_dir = tmp_path / "runs"
    run_dir.mkdir()
    (run_dir / "latest_checkpointed_iteration.txt").write_text(
        "not-an-int", encoding="utf-8"
    )
    _write_iter_dir(run_dir, 100)
    latest, iters = poll_run_progress(run_dir)
    assert latest == 0
    assert iters == [100]


# ---------------------------------------------------------------------------
# standardize_hf_export — shard renames
# ---------------------------------------------------------------------------


def _stage_overpadded_export(hf_dir: Path) -> None:
    """Write a tiny synthetic export with the NeMo over-padding quirk."""
    hf_dir.mkdir(parents=True, exist_ok=True)
    (hf_dir / "config.json").write_text("{}", encoding="utf-8")
    (hf_dir / "model-00001-of-000002.safetensors").write_bytes(b"\x00")
    (hf_dir / "model-00002-of-000002.safetensors").write_bytes(b"\x00")
    index = {
        "metadata": {"total_size": 1234},
        "weight_map": {
            "model.embed_tokens.weight": "model-00001-of-000002.safetensors",
            "lm_head.weight": "model-00002-of-000002.safetensors",
        },
    }
    (hf_dir / "model.safetensors.index.json").write_text(
        json.dumps(index, indent=2) + "\n", encoding="utf-8"
    )


def test_standardize_renames_overpadded_shards(tmp_path: Path) -> None:
    """The two shards with `of-000002` get renamed to `of-00002` and
    the index JSON's weight_map is rewritten to match."""
    hf_dir = tmp_path / "export"
    _stage_overpadded_export(hf_dir)
    renames, _ = standardize_hf_export(hf_dir, tokenizer_class_remap={})
    assert sorted(renames) == [
        ("model-00001-of-000002.safetensors", "model-00001-of-00002.safetensors"),
        ("model-00002-of-000002.safetensors", "model-00002-of-00002.safetensors"),
    ]
    assert (hf_dir / "model-00001-of-00002.safetensors").is_file()
    assert (hf_dir / "model-00002-of-00002.safetensors").is_file()
    assert not (hf_dir / "model-00001-of-000002.safetensors").exists()
    idx = json.loads((hf_dir / "model.safetensors.index.json").read_text())
    assert (
        idx["weight_map"]["model.embed_tokens.weight"]
        == "model-00001-of-00002.safetensors"
    )
    assert (
        idx["weight_map"]["lm_head.weight"]
        == "model-00002-of-00002.safetensors"
    )


def test_standardize_is_idempotent(tmp_path: Path) -> None:
    """Re-running the standardize pass on an already-clean dir is a
    no-op."""
    hf_dir = tmp_path / "export"
    _stage_overpadded_export(hf_dir)
    standardize_hf_export(hf_dir, tokenizer_class_remap={})
    renames, remaps = standardize_hf_export(hf_dir, tokenizer_class_remap={})
    assert renames == []
    assert remaps == []


def test_standardize_skips_already_standard_shards(tmp_path: Path) -> None:
    """A 5-digit-padded export (standard Unsloth / HF Transformers
    output) is left untouched — no renames, no warning."""
    hf_dir = tmp_path / "export"
    hf_dir.mkdir()
    (hf_dir / "config.json").write_text("{}", encoding="utf-8")
    (hf_dir / "model-00001-of-00002.safetensors").write_bytes(b"")
    (hf_dir / "model-00002-of-00002.safetensors").write_bytes(b"")
    renames, _ = standardize_hf_export(hf_dir, tokenizer_class_remap={})
    assert renames == []


def test_standardize_keeps_5digit_when_total_needs_5(tmp_path: Path) -> None:
    """A genuinely-large shard count (`of-12345`) is left untouched —
    the standard width is `max(5, len(str(total)))`."""
    hf_dir = tmp_path / "export"
    hf_dir.mkdir()
    (hf_dir / "config.json").write_text("{}", encoding="utf-8")
    (hf_dir / "model-00001-of-12345.safetensors").write_bytes(b"")
    renames, _ = standardize_hf_export(hf_dir, tokenizer_class_remap={})
    assert renames == []


def test_standardize_raises_on_missing_dir(tmp_path: Path) -> None:
    with pytest.raises(MergeExportError, match="does not exist"):
        standardize_hf_export(tmp_path / "nope")


def test_standardize_raises_when_index_not_json(tmp_path: Path) -> None:
    """A non-JSON index file surfaces as MergeExportError, not a silent
    no-op — the caller needs to know the rename happened but the
    weight_map is broken."""
    hf_dir = tmp_path / "export"
    _stage_overpadded_export(hf_dir)
    (hf_dir / "model.safetensors.index.json").write_text(
        "not-json", encoding="utf-8"
    )
    with pytest.raises(MergeExportError, match="not valid JSON"):
        standardize_hf_export(hf_dir, tokenizer_class_remap={})


def test_standardize_tolerates_missing_index(tmp_path: Path) -> None:
    """If the export omits `model.safetensors.index.json` entirely
    (single-shard exports do this), the rename step still runs and the
    function returns cleanly — there's no index to rewrite."""
    hf_dir = tmp_path / "export"
    hf_dir.mkdir()
    (hf_dir / "model-00001-of-000001.safetensors").write_bytes(b"")
    renames, _ = standardize_hf_export(hf_dir, tokenizer_class_remap={})
    assert renames == [
        ("model-00001-of-000001.safetensors", "model-00001-of-00001.safetensors")
    ]


# ---------------------------------------------------------------------------
# standardize_hf_export — tokenizer_class remap
# ---------------------------------------------------------------------------


def test_standardize_remaps_tokenizer_class_default(tmp_path: Path) -> None:
    """Default remap (DEEPSEEK_TOKENIZER_CLASS_REMAP) rewrites
    TokenizersBackend → LlamaTokenizer."""
    hf_dir = tmp_path / "export"
    hf_dir.mkdir()
    cfg = {"tokenizer_class": "TokenizersBackend", "vocab_size": 100}
    (hf_dir / "tokenizer_config.json").write_text(
        json.dumps(cfg), encoding="utf-8"
    )
    _, remaps = standardize_hf_export(hf_dir)
    assert remaps == [("TokenizersBackend", "LlamaTokenizer")]
    reloaded = json.loads(
        (hf_dir / "tokenizer_config.json").read_text(encoding="utf-8")
    )
    assert reloaded["tokenizer_class"] == "LlamaTokenizer"
    assert reloaded["vocab_size"] == 100  # other fields preserved


def test_standardize_skips_unmapped_tokenizer_class(tmp_path: Path) -> None:
    """A tokenizer_class not in the remap (e.g. `LlamaTokenizer`
    already) is left alone."""
    hf_dir = tmp_path / "export"
    hf_dir.mkdir()
    cfg = {"tokenizer_class": "LlamaTokenizer"}
    (hf_dir / "tokenizer_config.json").write_text(
        json.dumps(cfg), encoding="utf-8"
    )
    _, remaps = standardize_hf_export(hf_dir)
    assert remaps == []


def test_standardize_empty_remap_skips_tokenizer_fix(
    tmp_path: Path,
) -> None:
    """An empty `tokenizer_class_remap={}` disables the tokenizer fix
    even when the source has TokenizersBackend."""
    hf_dir = tmp_path / "export"
    hf_dir.mkdir()
    cfg = {"tokenizer_class": "TokenizersBackend"}
    (hf_dir / "tokenizer_config.json").write_text(
        json.dumps(cfg), encoding="utf-8"
    )
    _, remaps = standardize_hf_export(hf_dir, tokenizer_class_remap={})
    assert remaps == []
    reloaded = json.loads(
        (hf_dir / "tokenizer_config.json").read_text(encoding="utf-8")
    )
    assert reloaded["tokenizer_class"] == "TokenizersBackend"


def test_standardize_tolerates_missing_tokenizer_config(
    tmp_path: Path,
) -> None:
    """Some exports omit tokenizer_config.json (model-only checkpoints);
    the standardize pass should not crash."""
    hf_dir = tmp_path / "export"
    hf_dir.mkdir()
    renames, remaps = standardize_hf_export(hf_dir)
    assert renames == []
    assert remaps == []


def test_deepseek_remap_default_value() -> None:
    """The exported constant carries the actual remap that ships with
    the helper — locks the default value into the test suite."""
    assert DEEPSEEK_TOKENIZER_CLASS_REMAP == {
        "TokenizersBackend": "LlamaTokenizer"
    }


# ---------------------------------------------------------------------------
# run() — command construction + happy path
# ---------------------------------------------------------------------------


class _FakeRunner:
    """Records the command, simulates the trainer by writing one
    iter_NNNNNNN dir + the latest file, returns the configured rc."""

    def __init__(
        self,
        *,
        write_iter: int | None = None,
        run_dir_factory: Callable[[], Path] | None = None,
        rc: int = 0,
    ) -> None:
        self.commands: list[list[str]] = []
        self.write_iter = write_iter
        self.run_dir_factory = run_dir_factory
        self.rc = rc

    def __call__(self, cmd: list[str]) -> int:
        self.commands.append(list(cmd))
        if self.write_iter is not None and self.run_dir_factory is not None:
            run_dir = self.run_dir_factory()
            run_dir.mkdir(parents=True, exist_ok=True)
            _write_iter_dir(run_dir, self.write_iter)
            _write_latest_file(run_dir, self.write_iter)
        return self.rc


def test_run_nemo_full_mode(tmp_path: Path) -> None:
    """Happy path: NeMo backend, full mode. The runner gets a
    docker-exec command targeting nemo-train with --train-iters set
    to recipe.max_steps. The TrainResult reflects the simulated
    iter dir."""
    recipe = _make_recipe(tmp_path, backend="nemo")
    runner = _FakeRunner(
        write_iter=10,
        run_dir_factory=lambda: Path(recipe.output_dir) / "runs-full",
    )
    result = run(recipe, mode=MODE_FULL, runner=runner, poll_interval=0)
    assert isinstance(result, TrainResult)
    assert result.backend == "nemo"
    assert result.mode == MODE_FULL
    assert result.final_iter == 10
    assert result.iter_dirs == (10,)
    assert result.container == "nemo-train"
    assert result.run_dir.endswith("runs-full")

    cmd = runner.commands[0]
    assert cmd[:3] == ["docker", "exec", "-w"]
    assert "nemo-train" in cmd
    inner = cmd[-1]
    assert "p65_train_nemo_lora.py" in inner
    assert "--train-iters 10" in inner
    assert "--smoke" not in inner


def test_run_nemo_smoke_mode_uses_smoke_steps(tmp_path: Path) -> None:
    """Smoke mode swaps the --train-iters flag for --smoke N, and
    targets runs-smoke/ instead of runs-full/."""
    recipe = _make_recipe(tmp_path, backend="nemo")
    runner = _FakeRunner(
        write_iter=2,
        run_dir_factory=lambda: Path(recipe.output_dir) / "runs-smoke",
    )
    result = run(recipe, mode=MODE_SMOKE, runner=runner, poll_interval=0)
    assert result.mode == MODE_SMOKE
    assert result.final_iter == 2
    assert result.run_dir.endswith("runs-smoke")
    inner = runner.commands[0][-1]
    assert "--smoke 2" in inner
    assert "--train-iters" not in inner


def test_run_nemo_honors_extra_env_overrides(tmp_path: Path) -> None:
    """Recipe.extra_env can override TRAIN_SCRIPT / MCORE_BASE /
    DATASET_DIR so a single recipe can drive a custom Megatron-Bridge
    fork or a non-default mcore-base path."""
    recipe = _make_recipe(tmp_path, backend="nemo")
    custom = TrainRecipe.from_dict(
        {
            **recipe.to_dict(),
            "extra_env": {
                "TRAIN_SCRIPT": "/opt/custom/trainer.py",
                "MCORE_BASE": "/data/custom-mcore",
                "DATASET_DIR": "/data/custom-dataset",
            },
        }
    )
    runner = _FakeRunner(
        write_iter=10,
        run_dir_factory=lambda: Path(custom.output_dir) / "runs-full",
    )
    run(custom, mode=MODE_FULL, runner=runner, poll_interval=0)
    inner = runner.commands[0][-1]
    assert "/opt/custom/trainer.py" in inner
    assert "/data/custom-mcore" in inner
    assert "/data/custom-dataset" in inner


def test_run_unsloth_requires_train_script(tmp_path: Path) -> None:
    """Unsloth backend without TRAIN_SCRIPT raises TrainError — the
    v0.5 release does not bundle a canonical Unsloth driver."""
    recipe = _make_recipe(tmp_path, backend="unsloth")
    runner = _FakeRunner()
    with pytest.raises(TrainError, match="TRAIN_SCRIPT"):
        run(recipe, mode=MODE_FULL, runner=runner, poll_interval=0)


def test_run_unsloth_with_train_script(tmp_path: Path) -> None:
    """Unsloth backend with TRAIN_SCRIPT set produces a docker-exec
    targeting ps-train + env vars passed to the bash entry point."""
    recipe = _make_recipe(tmp_path, backend="unsloth")
    custom = TrainRecipe.from_dict(
        {**recipe.to_dict(), "extra_env": {"TRAIN_SCRIPT": "/opt/u.sh"}}
    )
    runner = _FakeRunner(
        write_iter=10,
        run_dir_factory=lambda: Path(custom.output_dir) / "runs-full",
    )
    run(custom, mode=MODE_FULL, runner=runner, poll_interval=0)
    cmd = runner.commands[0]
    assert "ps-train" in cmd
    inner = cmd[-1]
    assert "/opt/u.sh" in inner
    assert f"BASE_MODEL={custom.base_model}" in inner
    assert "MODE=full" in inner


def test_run_propagates_nonzero_runner_rc(tmp_path: Path) -> None:
    """A non-zero rc from the runner surfaces as TrainError with the
    code in the message."""
    recipe = _make_recipe(tmp_path, backend="nemo")
    runner = _FakeRunner(rc=137)
    with pytest.raises(TrainError, match="137"):
        run(recipe, mode=MODE_FULL, runner=runner, poll_interval=0)


def test_run_rejects_bad_mode(tmp_path: Path) -> None:
    recipe = _make_recipe(tmp_path, backend="nemo")
    with pytest.raises(TrainError, match="unknown mode"):
        run(recipe, mode="bogus", runner=_FakeRunner(), poll_interval=0)


def test_run_rejects_negative_poll_interval(tmp_path: Path) -> None:
    recipe = _make_recipe(tmp_path, backend="nemo")
    with pytest.raises(TrainError, match="poll_interval"):
        run(recipe, runner=_FakeRunner(), poll_interval=-1.0)


def test_run_emits_on_progress_callback(tmp_path: Path) -> None:
    """The on_progress callback fires once with the final state for a
    synchronous runner."""
    recipe = _make_recipe(tmp_path, backend="nemo")
    runner = _FakeRunner(
        write_iter=10,
        run_dir_factory=lambda: Path(recipe.output_dir) / "runs-full",
    )
    calls: list[tuple[int, list[int]]] = []
    run(
        recipe,
        runner=runner,
        on_progress=lambda latest, iters: calls.append((latest, iters)),
        poll_interval=0,
    )
    assert len(calls) == 1
    assert calls[0] == (10, [10])


# ---------------------------------------------------------------------------
# AE-25 / BUG-1 — the canonical sft-progress heartbeat
# ---------------------------------------------------------------------------


def _progress_files(recipe: TrainRecipe) -> list[Path]:
    return sorted((Path(recipe.output_dir) / "progress").glob("sft-progress-*.json"))


def test_run_writes_canonical_progress_heartbeat(tmp_path: Path) -> None:
    """Every run() stamps the invocation-independent heartbeat the Arena SFT
    pane reads — the fix for a finished real run rendering `0/0 · starting`."""
    recipe = _make_recipe(tmp_path, backend="nemo")
    runner = _FakeRunner(
        write_iter=10,
        run_dir_factory=lambda: Path(recipe.output_dir) / "runs-full",
    )
    run(recipe, mode=MODE_FULL, runner=runner, poll_interval=0)
    files = _progress_files(recipe)
    assert len(files) == 1
    j = json.loads(files[0].read_text())
    assert j["kind"] == "sft-progress"
    assert j["status"] == "done" and j["final"] is True
    assert j["latest_iter"] == 10 and j["max_iters"] == 10
    assert j["checkpoint_iters"] == [10]
    assert j["backend"] == "nemo" and j["mode"] == MODE_FULL
    assert "wall_seconds" in j and "run_label" in j
    assert files[0].name.startswith("sft-progress-full-")


def test_run_heartbeat_failed_on_nonzero_rc(tmp_path: Path) -> None:
    recipe = _make_recipe(tmp_path, backend="nemo")
    runner = _FakeRunner(rc=3)
    with pytest.raises(TrainError):
        run(recipe, mode=MODE_SMOKE, runner=runner, poll_interval=0)
    files = _progress_files(recipe)
    assert len(files) == 1
    j = json.loads(files[0].read_text())
    assert j["status"] == "failed"
    assert "exit code 3" in j["error"]


def test_sft_progress_dir_env_override(tmp_path: Path, monkeypatch) -> None:
    from fieldkit.training import sft_progress_dir

    recipe = _make_recipe(tmp_path, backend="nemo")
    override = tmp_path / "elsewhere"
    monkeypatch.setenv("FK_SFT_PROGRESS_DIR", str(override))
    assert sft_progress_dir(recipe) == override
    runner = _FakeRunner(
        write_iter=2,
        run_dir_factory=lambda: Path(recipe.output_dir) / "runs-smoke",
    )
    run(recipe, mode=MODE_SMOKE, runner=runner, poll_interval=0)
    assert list(override.glob("sft-progress-smoke-*.json"))
    assert not (Path(recipe.output_dir) / "progress").exists()


def test_run_async_runner_polls_until_iter(tmp_path: Path) -> None:
    """An async runner that returns 0 immediately but writes the
    iter dir on the second sleep — the poll loop catches it."""
    recipe = _make_recipe(tmp_path, backend="nemo")
    run_dir = Path(recipe.output_dir) / "runs-full"
    sleep_count = {"n": 0}

    def fake_sleep(_: float) -> None:
        sleep_count["n"] += 1
        if sleep_count["n"] >= 2:
            run_dir.mkdir(parents=True, exist_ok=True)
            _write_iter_dir(run_dir, 10)
            _write_latest_file(run_dir, 10)

    def async_runner(_cmd: list[str]) -> int:
        return 0

    result = run(
        recipe,
        runner=async_runner,
        poll_interval=0.001,
        sleep=fake_sleep,
    )
    assert result.final_iter == 10
    assert sleep_count["n"] >= 2


def test_run_invalid_recipe_raises_clear_error(tmp_path: Path) -> None:
    """Recipe whose preflight fails surfaces as TrainError, not the
    raw RecipeError — keeps callers' catch surface small."""
    recipe = TrainRecipe(
        base_model=str(tmp_path / "missing"),
        dataset_jsonl=str(tmp_path / "also-missing.jsonl"),
        output_dir=str(tmp_path / "out"),
        backend="nemo",
    )
    with pytest.raises(TrainError, match="preflight"):
        run(recipe, runner=_FakeRunner(), poll_interval=0)


# ---------------------------------------------------------------------------
# merge_and_export()
# ---------------------------------------------------------------------------


class _MergeExportRunner:
    """Two-call runner: records merge cmd, records export cmd, writes
    a synthetic merged-hf-bf16/ that the standardize pass can chew on."""

    def __init__(
        self,
        merged_hf_factory: Callable[[], Path],
        *,
        overpadded: bool = True,
        with_tokenizer_quirk: bool = True,
    ) -> None:
        self.commands: list[list[str]] = []
        self.merged_hf_factory = merged_hf_factory
        self.overpadded = overpadded
        self.with_tokenizer_quirk = with_tokenizer_quirk

    def __call__(self, cmd: list[str]) -> int:
        self.commands.append(list(cmd))
        # On the export step (second call for NeMo, first for Unsloth)
        # we write the synthetic merged dir.
        is_export = any("convert_checkpoints.py" in part for part in cmd)
        is_unsloth_merge = any("MERGED_HF=" in part for part in cmd)
        if is_export or is_unsloth_merge:
            merged = self.merged_hf_factory()
            merged.mkdir(parents=True, exist_ok=True)
            (merged / "config.json").write_text("{}", encoding="utf-8")
            if self.overpadded:
                (merged / "model-00001-of-000002.safetensors").write_bytes(b"")
                (merged / "model-00002-of-000002.safetensors").write_bytes(b"")
                idx = {
                    "weight_map": {
                        "model.embed.weight": "model-00001-of-000002.safetensors",
                        "lm_head.weight": "model-00002-of-000002.safetensors",
                    }
                }
                (merged / "model.safetensors.index.json").write_text(
                    json.dumps(idx), encoding="utf-8"
                )
            if self.with_tokenizer_quirk:
                (merged / "tokenizer_config.json").write_text(
                    json.dumps({"tokenizer_class": "TokenizersBackend"}),
                    encoding="utf-8",
                )
        return 0


def test_merge_and_export_nemo_bakes_in_clean_transform(
    tmp_path: Path,
) -> None:
    """End-to-end NeMo merge+export: two docker-exec commands (merge,
    export), then the standardize pass renames shards + remaps
    tokenizer_class. The MergeExportResult reflects all of it."""
    recipe = _make_recipe(tmp_path, backend="nemo")
    run_dir = Path(recipe.output_dir) / "runs-full"
    run_dir.mkdir()
    _write_iter_dir(run_dir, 625)
    _write_latest_file(run_dir, 625)
    merged_factory = lambda: Path(recipe.output_dir) / "merged-hf-bf16"
    runner = _MergeExportRunner(merged_factory)

    result = merge_and_export(recipe, runner=runner)

    assert isinstance(result, MergeExportResult)
    assert result.backend == "nemo"
    assert result.source_iter == 625
    assert result.merged_mcore_dir is not None
    assert result.standardize_applied is True
    assert result.tokenizer_class_remapped == (
        ("TokenizersBackend", "LlamaTokenizer"),
    )
    assert sorted(result.shard_renames) == [
        ("model-00001-of-000002.safetensors", "model-00001-of-00002.safetensors"),
        ("model-00002-of-000002.safetensors", "model-00002-of-00002.safetensors"),
    ]
    # Both stages issued; merge first, then export.
    assert len(runner.commands) == 2
    assert any("merge_lora.py" in c[-1] for c in runner.commands[:1])
    assert any("convert_checkpoints.py" in c[-1] for c in runner.commands[1:])


def test_merge_and_export_respects_explicit_iter(tmp_path: Path) -> None:
    """When `iter=` is explicit, the merge command uses that iter, no
    matter what the latest file says."""
    recipe = _make_recipe(tmp_path, backend="nemo")
    run_dir = Path(recipe.output_dir) / "runs-full"
    run_dir.mkdir()
    _write_latest_file(run_dir, 625)
    _write_iter_dir(run_dir, 500)
    merged_factory = lambda: Path(recipe.output_dir) / "merged-hf-bf16"
    runner = _MergeExportRunner(merged_factory)
    result = merge_and_export(recipe, iter=500, runner=runner)
    assert result.source_iter == 500
    merge_cmd = runner.commands[0][-1]
    assert "iter_0000500" in merge_cmd


def test_merge_and_export_expect_iter_guard(tmp_path: Path) -> None:
    """expect_iter mismatch raises early — caught the early-stopped
    training run case in p65_merge_and_probe.sh."""
    recipe = _make_recipe(tmp_path, backend="nemo")
    run_dir = Path(recipe.output_dir) / "runs-full"
    run_dir.mkdir()
    _write_latest_file(run_dir, 100)
    with pytest.raises(MergeExportError, match="expect_iter"):
        merge_and_export(
            recipe, expect_iter=625, runner=_MergeExportRunner(lambda: tmp_path)
        )


def test_merge_and_export_raises_without_iter(tmp_path: Path) -> None:
    """No latest file, no explicit iter → clear MergeExportError."""
    recipe = _make_recipe(tmp_path, backend="nemo")
    runner = _MergeExportRunner(lambda: tmp_path)
    with pytest.raises(MergeExportError, match="latest_checkpointed"):
        merge_and_export(recipe, runner=runner)


def test_merge_and_export_standardize_false_skips_cleanup(
    tmp_path: Path,
) -> None:
    """standardize=False leaves the over-padded shards in place so the
    caller can inspect the raw export."""
    recipe = _make_recipe(tmp_path, backend="nemo")
    run_dir = Path(recipe.output_dir) / "runs-full"
    run_dir.mkdir()
    _write_iter_dir(run_dir, 625)
    _write_latest_file(run_dir, 625)
    merged_factory = lambda: Path(recipe.output_dir) / "merged-hf-bf16"
    runner = _MergeExportRunner(merged_factory)
    result = merge_and_export(recipe, standardize=False, runner=runner)
    assert result.standardize_applied is False
    assert result.shard_renames == ()
    assert (
        Path(recipe.output_dir) / "merged-hf-bf16"
        / "model-00001-of-000002.safetensors"
    ).is_file()


def test_merge_and_export_unsloth_requires_merge_script(
    tmp_path: Path,
) -> None:
    """Unsloth backend without extra_env['MERGE_SCRIPT'] raises a
    clear MergeExportError."""
    recipe = _make_recipe(tmp_path, backend="unsloth")
    run_dir = Path(recipe.output_dir) / "runs-full"
    run_dir.mkdir()
    _write_latest_file(run_dir, 625)
    _write_iter_dir(run_dir, 625)
    runner = _MergeExportRunner(lambda: tmp_path / "ignored")
    with pytest.raises(MergeExportError, match="MERGE_SCRIPT"):
        merge_and_export(recipe, runner=runner)


def test_merge_and_export_unsloth_with_merge_script(tmp_path: Path) -> None:
    """Unsloth backend with MERGE_SCRIPT set issues exactly one
    docker-exec; standardize is still applied (no-op on clean
    output)."""
    recipe = _make_recipe(tmp_path, backend="unsloth")
    custom = TrainRecipe.from_dict(
        {**recipe.to_dict(), "extra_env": {"MERGE_SCRIPT": "/opt/u-merge.sh"}}
    )
    run_dir = Path(custom.output_dir) / "runs-full"
    run_dir.mkdir()
    _write_latest_file(run_dir, 625)
    _write_iter_dir(run_dir, 625)
    merged_factory = lambda: Path(custom.output_dir) / "merged-hf-bf16"
    runner = _MergeExportRunner(
        merged_factory, overpadded=False, with_tokenizer_quirk=False
    )
    result = merge_and_export(custom, runner=runner)
    assert result.backend == "unsloth"
    assert result.merged_mcore_dir is None
    assert result.shard_renames == ()
    assert result.tokenizer_class_remapped == ()
    assert result.standardize_applied is True
    assert len(runner.commands) == 1
    assert "/opt/u-merge.sh" in runner.commands[0][-1]


def test_merge_export_result_is_frozen(tmp_path: Path) -> None:
    """MergeExportResult mutation rejected — callers can hash/share
    without defensive copies."""
    r = MergeExportResult(
        backend="nemo",
        source_iter=625,
        merged_hf_dir="/tmp/m",
    )
    with pytest.raises((AttributeError, Exception)):
        r.source_iter = 100  # type: ignore[misc]


def test_train_result_is_frozen() -> None:
    r = TrainResult(
        backend="nemo",
        mode=MODE_FULL,
        run_dir="/tmp/r",
        final_iter=10,
        wall_seconds=1.0,
        container="nemo-train",
    )
    with pytest.raises((AttributeError, Exception)):
        r.final_iter = 0  # type: ignore[misc]
