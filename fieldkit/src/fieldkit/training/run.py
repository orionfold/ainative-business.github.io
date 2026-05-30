# Copyright 2026 Manav Sehgal
# SPDX-License-Identifier: Apache-2.0
"""LoRA SFT runner + merge/export driver — symmetric NeMo and Unsloth backends.

Phase C of the v0.5 `fieldkit.training` build-out (after Phase A's
`recipe.TrainRecipe` and Phase B's `convert`). Three pure-python
primitives plus two thin orchestration entry points:

- `poll_run_progress(run_dir)` — the *only* reliable progress signal for
  a running Megatron or Unsloth checkpoint job. `train.log` can lag the
  process by 4+ hours under docker-exec + shell-redirect (see
  `[[feedback_megatron_train_log_buffering]]`); the canonical signal is
  the `latest_checkpointed_iteration.txt` file + the on-disk
  `iter_NNNNNNN/` directories that the trainer writes atomically.
- `standardize_hf_export(hf_dir)` — bakes in the two known NeMo-export
  quirks the patent-strategist v3 NeMo lane discovered the hard way:
  shard-name padding (`of-000002` → `of-00002`) and
  `tokenizer_class: TokenizersBackend` → `LlamaTokenizer`. Idempotent;
  safe to call on already-standard exports (Unsloth, vanilla HF
  Transformers).
- `run(recipe, ...)` — recipe → backend command → subprocess →
  poll-disk liveness → `TrainResult`. The actual trainer entry point
  stays in `scripts/p65_train_nemo_lora.py` (NeMo) or the article-side
  Unsloth driver; this function owns the docker-exec shape + the
  liveness loop.
- `merge_and_export(recipe, ...)` — for the NeMo backend, invokes the
  Megatron-Bridge `merge_lora.py` + `convert_checkpoints.py export`
  pair and then runs `standardize_hf_export` so the resulting HF
  directory is consumer-ready (`huggingface_hub.upload_large_folder`,
  `convert_hf_to_gguf.py`, `AutoTokenizer.from_pretrained`). For
  Unsloth, runs the standard `merge_and_unload` + `save_pretrained`
  dance and still calls `standardize_hf_export` (no-op on a clean
  export, cheap insurance against silent regressions).

All five primitives are pure-python by default. `run()` and
`merge_and_export()` accept a `runner` injection so the subprocess
shell-out is testable without docker or torch. Lazy `subprocess`
import keeps `import fieldkit.training.run` cheap.
"""
from __future__ import annotations

import json
import re
import shlex
import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Mapping, Optional

from fieldkit.training.recipe import (
    MODE_FULL,
    MODE_SMOKE,
    RecipeError,
    TrainRecipe,
)


__all__ = [
    "DEEPSEEK_TOKENIZER_CLASS_REMAP",
    "MergeExportError",
    "MergeExportResult",
    "TrainError",
    "TrainResult",
    "merge_and_export",
    "poll_run_progress",
    "run",
    "standardize_hf_export",
]


DEEPSEEK_TOKENIZER_CLASS_REMAP: dict[str, str] = {
    "TokenizersBackend": "LlamaTokenizer",
}
"""Default `tokenizer_class` remap applied by `standardize_hf_export`.

Megatron-Bridge's HF exporter writes `"TokenizersBackend"` for
DeepSeek-R1-Qwen3 descendants; HF Transformers' `AutoTokenizer` doesn't
know that class and falls back through `tokenizer.json` (which mostly
works), but every external consumer that introspects `tokenizer_class`
(some quantizers, some `tokenizers`-vs-`transformers` smoke tests)
either errors or warns. Patching to `"LlamaTokenizer"` is the
Qwen-architecture-correct value and avoids the surprise. See
`[[feedback_nemo_export_tokenizer_class_quirk]]`."""


class TrainError(RuntimeError):
    """Raised when `run()` fails to launch or its trainer exits non-zero.

    Distinct from `ValueError` / `RecipeError` so callers can selectively
    catch *launch-time* failures (bad command spec, container missing)
    vs *runtime* failures (trainer crashed mid-run). The exception's
    `args[0]` always includes the subprocess return code when the
    trainer exited; the caller can grep its log for the underlying
    cause.
    """


class MergeExportError(RuntimeError):
    """Raised when `merge_and_export()` fails at any of merge / export /
    standardize stages. Carries the failed stage name in `args[0]`."""


@dataclass(frozen=True)
class TrainResult:
    """Outcome of a `run()` invocation. Frozen so callers can hash it
    into a lineage row without defensive copies."""

    backend: str
    mode: str
    run_dir: str
    final_iter: int
    """Last iteration that landed an `iter_NNNNNNN/` directory on disk.
    `0` if the trainer never reached a save-interval boundary."""
    wall_seconds: float
    container: str
    log_path: Optional[str] = None
    iter_dirs: tuple[int, ...] = field(default_factory=tuple)
    """Sorted list of every iteration directory the run produced.
    Useful for the `most_recent_k` rotation policy and for sanity-checks
    that the trainer hit the expected cadence."""


@dataclass(frozen=True)
class MergeExportResult:
    """Outcome of a `merge_and_export()` invocation. Records every
    file-level change the standardize pass made so the caller can
    surface them in an article / HANDOFF without re-discovering."""

    backend: str
    source_iter: int
    merged_hf_dir: str
    merged_mcore_dir: Optional[str] = None
    """Only set for the NeMo backend; Unsloth merges to HF directly."""
    tokenizer_class_remapped: tuple[tuple[str, str], ...] = field(default_factory=tuple)
    """List of `(old_class, new_class)` pairs the standardize pass
    rewrote in `tokenizer_config.json`. Empty if no remap fired."""
    shard_renames: tuple[tuple[str, str], ...] = field(default_factory=tuple)
    """List of `(old_filename, new_filename)` pairs the standardize
    pass applied to safetensors shards. Empty on already-standard
    exports."""
    standardize_applied: bool = False
    """True iff `standardize_hf_export` was invoked (the caller can
    disable it with `standardize=False`)."""


# ---------------------------------------------------------------------------
# Disk-poll liveness
# ---------------------------------------------------------------------------


_ITER_DIR_RE = re.compile(r"^iter_(\d{7})$")
"""Megatron's checkpoint directory naming convention: `iter_NNNNNNN`
(7-digit zero-padded iteration count). The trainer renames a temp
directory in atomically once the checkpoint write completes."""


def poll_run_progress(run_dir: str | Path) -> tuple[int, list[int]]:
    """Read the canonical liveness signals for a Megatron or Unsloth run.

    Returns ``(latest_iter_from_file, sorted_iter_dirs_on_disk)``:

    - ``latest_iter_from_file`` — contents of
      ``<run_dir>/latest_checkpointed_iteration.txt`` parsed as `int`.
      Set to ``0`` if the file is missing (trainer hasn't saved its
      first checkpoint yet) or unparseable.
    - ``sorted_iter_dirs_on_disk`` — every directory matching
      ``iter_NNNNNNN`` under ``run_dir``, sorted ascending by
      iteration number.

    The two signals usually agree; a disagreement means the trainer is
    mid-write (file updated last, atomic-rename of the new
    iter directory pending) or has rotated stale checkpoints out of
    the run dir. Tail-grep of ``train.log`` is **not** a reliable
    progress signal — log buffering can lag the running process by 4+
    hours under docker-exec + shell-redirect. See
    `[[feedback_megatron_train_log_buffering]]`.

    Pure-python, no torch dep, safe to call from a notebook or a
    monitor loop. Returns ``(0, [])`` on a non-existent run dir.
    """
    p = Path(run_dir)
    if not p.is_dir():
        return 0, []
    latest_path = p / "latest_checkpointed_iteration.txt"
    latest_iter = 0
    if latest_path.is_file():
        try:
            text = latest_path.read_text(encoding="utf-8").strip()
            latest_iter = int(text)
        except (OSError, ValueError):
            latest_iter = 0
    iters: list[int] = []
    for child in p.iterdir():
        if not child.is_dir():
            continue
        m = _ITER_DIR_RE.match(child.name)
        if m is None:
            continue
        iters.append(int(m.group(1)))
    iters.sort()
    return latest_iter, iters


# ---------------------------------------------------------------------------
# HF export standardization (the BF16-clean transformation, baked in)
# ---------------------------------------------------------------------------


_SHARD_OVERPAD_RE = re.compile(
    r"^(?P<prefix>.+)-(?P<idx>\d+)-of-(?P<total>\d+)(?P<ext>\.safetensors)$"
)
"""Generic match for any `<prefix>-NNNNN-of-MMMMM.safetensors` shard
name. The standardize pass renames any shard whose `of-` field has
*more* zero-padding than HF-standard (max of 5 digits or len(str(N))).
Megatron-Bridge writes 6-digit totals on small shard counts
(`of-000002`); HF + llama.cpp expect 5-digit (`of-00002`)."""


def _hf_standard_shard_pad(total: int) -> int:
    """HF Transformers' shard naming uses 5-digit padding by default
    (`model-00001-of-00002.safetensors`); shards beyond 99999 widen
    naturally. See `transformers.utils.hub.SHARDED_FILE_PATTERN`."""
    return max(5, len(str(total)))


def standardize_hf_export(
    hf_dir: str | Path,
    *,
    tokenizer_class_remap: Optional[Mapping[str, str]] = None,
) -> tuple[list[tuple[str, str]], list[tuple[str, str]]]:
    """Bake the two known NeMo-export quirks into an HF model directory.

    Returns ``(shard_renames, tokenizer_remaps)`` for logging — each is
    a list of ``(old, new)`` tuples representing exactly what was
    written. Empty lists signal "already standard".

    **Quirk 1: shard-name padding.** Megatron-Bridge's HF exporter
    writes ``model-NNNNN-of-000002.safetensors`` (6-digit total padding)
    on small shard counts. HF Transformers loads them fine but
    ``huggingface_hub`` validators, ``safetensors`` CLI, and llama.cpp's
    ``convert_hf_to_gguf.py`` all expect the 5-digit standard. This
    function renames every safetensors shard to the standard width
    (``max(5, len(str(total)))`` digits) and rewrites the matching
    entries in ``model.safetensors.index.json``. See
    `[[feedback_nemo_export_shard_numbering]]`.

    **Quirk 2: tokenizer_class remap.** ``tokenizer_config.json``'s
    ``tokenizer_class`` field is patched via the ``tokenizer_class_remap``
    lookup table. Defaults to ``DEEPSEEK_TOKENIZER_CLASS_REMAP``
    (``TokenizersBackend`` → ``LlamaTokenizer``). Pass ``{}`` to skip the
    tokenizer-class fix entirely (e.g. for exports you know are
    already canonical). See
    `[[feedback_nemo_export_tokenizer_class_quirk]]`.

    Idempotent: re-running on an already-standardized directory yields
    ``([], [])`` and writes nothing. Tolerant of missing index files
    and missing tokenizer config (each fix is independent).

    Raises ``MergeExportError`` only on malformed inputs (a safetensors
    rename collides with an existing file, the index JSON exists but
    isn't parseable as a dict, etc.) — the common-case "nothing to do"
    is a quiet two-empty-lists return.
    """
    p = Path(hf_dir)
    if not p.is_dir():
        raise MergeExportError(
            f"standardize: hf_dir does not exist or is not a directory: {p}"
        )
    remap = (
        dict(tokenizer_class_remap)
        if tokenizer_class_remap is not None
        else dict(DEEPSEEK_TOKENIZER_CLASS_REMAP)
    )

    shard_renames = _standardize_safetensors_shards(p)
    tokenizer_remaps = _patch_tokenizer_class(p, remap)
    return shard_renames, tokenizer_remaps


def _standardize_safetensors_shards(p: Path) -> list[tuple[str, str]]:
    """Rename `<prefix>-NNNNN-of-MMMMM.safetensors` shards whose `of-`
    field is over-padded relative to the HF-standard width.

    Returns the list of ``(old_basename, new_basename)`` tuples. Empty
    on no-op. Also rewrites ``model.safetensors.index.json`` if present
    so the ``weight_map`` values track the renames.
    """
    renames: list[tuple[str, str]] = []
    plan: list[tuple[Path, Path, str, str]] = []
    for child in sorted(p.iterdir()):
        if not child.is_file():
            continue
        m = _SHARD_OVERPAD_RE.match(child.name)
        if m is None:
            continue
        total_raw = m.group("total")
        total = int(total_raw)
        # Drop accidental over-padding on the index too — HF uses the
        # same width on both sides of `-of-`.
        std_pad = _hf_standard_shard_pad(total)
        if len(total_raw) <= std_pad and len(m.group("idx")) <= std_pad:
            continue
        new_idx = str(int(m.group("idx"))).zfill(std_pad)
        new_total = str(total).zfill(std_pad)
        new_name = (
            f"{m.group('prefix')}-{new_idx}-of-{new_total}{m.group('ext')}"
        )
        if new_name == child.name:
            continue
        target = p / new_name
        if target.exists() and target != child:
            raise MergeExportError(
                f"standardize: rename target already exists: {target}"
            )
        plan.append((child, target, child.name, new_name))

    if not plan:
        return renames

    for src, dst, _, _ in plan:
        src.rename(dst)
    renames = [(old, new) for _, _, old, new in plan]

    # Patch the index JSON if it carries any of the old filenames.
    index_path = p / "model.safetensors.index.json"
    if index_path.is_file():
        try:
            doc = json.loads(index_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise MergeExportError(
                f"standardize: {index_path} is not valid JSON: {exc}"
            ) from exc
        if not isinstance(doc, dict):
            raise MergeExportError(
                f"standardize: {index_path} did not parse to a JSON object"
            )
        wmap = doc.get("weight_map")
        if isinstance(wmap, dict):
            old_to_new = {old: new for old, new in renames}
            changed = False
            for key, fname in list(wmap.items()):
                if isinstance(fname, str) and fname in old_to_new:
                    wmap[key] = old_to_new[fname]
                    changed = True
            if changed:
                index_path.write_text(
                    json.dumps(doc, indent=2, sort_keys=True) + "\n",
                    encoding="utf-8",
                )

    return renames


def _patch_tokenizer_class(
    p: Path, remap: Mapping[str, str]
) -> list[tuple[str, str]]:
    """Rewrite ``tokenizer_config.json``'s ``tokenizer_class`` field per
    the remap table. Returns the list of ``(old_class, new_class)``
    pairs actually applied (length 0 or 1 in practice)."""
    if not remap:
        return []
    cfg_path = p / "tokenizer_config.json"
    if not cfg_path.is_file():
        return []
    try:
        cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise MergeExportError(
            f"standardize: {cfg_path} is not valid JSON: {exc}"
        ) from exc
    if not isinstance(cfg, dict):
        raise MergeExportError(
            f"standardize: {cfg_path} did not parse to a JSON object"
        )
    current = cfg.get("tokenizer_class")
    if not isinstance(current, str) or current not in remap:
        return []
    new_class = remap[current]
    if new_class == current:
        return []
    cfg["tokenizer_class"] = new_class
    cfg_path.write_text(
        json.dumps(cfg, indent=2) + "\n", encoding="utf-8"
    )
    return [(current, new_class)]


# ---------------------------------------------------------------------------
# Backend command construction
# ---------------------------------------------------------------------------


_NEMO_TRAIN_SCRIPT = (
    "/home/nvidia/ainative-business.github.io/scripts/p65_train_nemo_lora.py"
)
"""Default in-repo entry point for the NeMo training stage. Overridable
via `recipe.extra_env['TRAIN_SCRIPT']`. The script's CLI is
``--hf-model / --pretrained-mcore / --dataset-root / --run-dir /
(--train-iters | --smoke)`` per `scripts/p65_train_nemo_lora.sh`."""


def _smoke_run_dir(recipe: TrainRecipe) -> Path:
    return Path(recipe.output_dir).resolve() / "runs-smoke"


def _full_run_dir(recipe: TrainRecipe) -> Path:
    return Path(recipe.output_dir).resolve() / "runs-full"


def _resolve_run_dir(recipe: TrainRecipe, mode: str) -> Path:
    if mode == MODE_SMOKE:
        return _smoke_run_dir(recipe)
    if mode == MODE_FULL:
        return _full_run_dir(recipe)
    raise TrainError(f"unknown mode={mode!r} (expected 'smoke' or 'full')")


def _nemo_train_command(
    recipe: TrainRecipe,
    *,
    mode: str,
) -> list[str]:
    """Build the docker-exec argv that runs the NeMo trainer for one
    recipe + mode. Mirrors `scripts/p65_train_nemo_lora.sh` stages
    3/4 with `--smoke N` for smoke mode and `--train-iters N` for full
    mode. Defaults can be overridden via `recipe.extra_env`:

    - `TRAIN_SCRIPT` — path to the trainer entry-point inside the
      container (default `_NEMO_TRAIN_SCRIPT`).
    - `MCORE_BASE` — the pre-converted Megatron-Core base dir
      (default `<output_dir>/mcore-base`).
    - `DATASET_DIR` — the NeMo-format dataset root with
      `training.jsonl` + `validation.jsonl` (default
      `<output_dir>/dataset`).
    """
    container = recipe.resolved_container()
    output_root = Path(recipe.output_dir).resolve()
    mcore_base = recipe.extra_env.get("MCORE_BASE") or str(
        output_root / "mcore-base"
    )
    dataset_dir = recipe.extra_env.get("DATASET_DIR") or str(
        output_root / "dataset"
    )
    train_script = recipe.extra_env.get("TRAIN_SCRIPT") or _NEMO_TRAIN_SCRIPT
    run_dir = _resolve_run_dir(recipe, mode)

    inner_args = [
        "torchrun",
        "--nproc_per_node=1",
        train_script,
        "--hf-model",
        str(recipe.base_model),
        "--pretrained-mcore",
        mcore_base,
        "--dataset-root",
        dataset_dir,
        "--run-dir",
        str(run_dir),
    ]
    if mode == MODE_SMOKE:
        inner_args += ["--smoke", str(recipe.smoke_steps)]
    else:
        inner_args += ["--train-iters", str(recipe.max_steps)]

    inner = " ".join(shlex.quote(a) for a in inner_args)
    return ["docker", "exec", "-w", "/tmp", container, "bash", "-lc", inner]


def _unsloth_train_command(
    recipe: TrainRecipe,
    *,
    mode: str,
) -> list[str]:
    """Build the docker-exec argv for the Unsloth backend.

    Symmetric to `_nemo_train_command` but invokes whatever
    article-side Unsloth driver the caller has staged at
    `recipe.extra_env['TRAIN_SCRIPT']`. Raises `TrainError` if no
    `TRAIN_SCRIPT` is set — there is no in-repo canonical Unsloth
    trainer for the v0.5 release; the article-companion driver stays
    the source of truth until the second Unsloth-lane article confirms
    a stable shape.
    """
    train_script = recipe.extra_env.get("TRAIN_SCRIPT")
    if not train_script:
        raise TrainError(
            "Unsloth backend requires recipe.extra_env['TRAIN_SCRIPT'] "
            "to point to your article-side trainer entry point — the "
            "v0.5 release does not bundle a canonical Unsloth driver. "
            "See fieldkit/docs/api/training.md for the contract a "
            "TRAIN_SCRIPT must implement."
        )
    container = recipe.resolved_container()
    run_dir = _resolve_run_dir(recipe, mode)
    inner_args = [
        "bash",
        "-lc",
        # We pass recipe fields through env so a single bash script can
        # consume them without re-encoding the YAML. Symmetric with the
        # NeMo path's argparse flags.
        " ".join(
            shlex.quote(a)
            for a in [
                "env",
                f"BASE_MODEL={recipe.base_model}",
                f"DATASET_JSONL={recipe.dataset_jsonl}",
                f"RUN_DIR={run_dir}",
                f"MODE={mode}",
                f"MAX_STEPS={recipe.max_steps}",
                f"SMOKE_STEPS={recipe.smoke_steps}",
                f"SEQ_LENGTH={recipe.seq_length}",
                f"MICRO_BATCH_SIZE={recipe.micro_batch_size}",
                f"GLOBAL_BATCH_SIZE={recipe.global_batch_size}",
                f"LEARNING_RATE={recipe.learning_rate}",
                f"LORA_RANK={recipe.lora_rank}",
                f"LORA_ALPHA={recipe.lora_alpha}",
                "bash",
                train_script,
            ]
        ),
    ]
    return ["docker", "exec", "-w", "/tmp", container] + inner_args


def _build_train_command(recipe: TrainRecipe, *, mode: str) -> list[str]:
    if recipe.backend == "nemo":
        return _nemo_train_command(recipe, mode=mode)
    return _unsloth_train_command(recipe, mode=mode)


# ---------------------------------------------------------------------------
# run()
# ---------------------------------------------------------------------------


def _default_runner(cmd: list[str]) -> int:
    """The default subprocess runner used by `run()` /
    `merge_and_export()`. Imports `subprocess` lazily so module import
    stays cheap.
    """
    import subprocess

    proc = subprocess.run(cmd, check=False)
    return proc.returncode


def run(
    recipe: TrainRecipe,
    *,
    mode: str = MODE_FULL,
    poll_interval: float = 30.0,
    on_progress: Optional[Callable[[int, list[int]], None]] = None,
    runner: Optional[Callable[[list[str]], int]] = None,
    sleep: Optional[Callable[[float], None]] = None,
) -> TrainResult:
    """Launch a LoRA SFT run for the given recipe; poll disk for liveness.

    Symmetric across `recipe.backend == "nemo"` and `"unsloth"`. The
    function:

    1. Calls `recipe.preflight()` to fail fast on bad inputs / missing
       paths.
    2. Builds the backend-specific docker-exec command via
       `_build_train_command` (NeMo: `scripts/p65_train_nemo_lora.py`;
       Unsloth: the caller's `recipe.extra_env['TRAIN_SCRIPT']`).
    3. Invokes the command via the `runner` callable (defaults to
       `subprocess.run`).
    4. Polls `<run_dir>/latest_checkpointed_iteration.txt` and the
       `iter_NNNNNNN/` directories on disk (the *only* reliable
       liveness signal — see `[[feedback_megatron_train_log_buffering]]`).
       Emits each new `(latest_iter, iter_dirs)` to `on_progress` if
       provided.

    The poll loop runs *after* the runner returns (the default
    `subprocess.run` blocks until the trainer exits, so the poll loop
    has nothing to do for synchronous runners). For asynchronous
    runners that return immediately (e.g. a `nohup` launcher), the
    caller can supply a custom `runner` that returns 0 immediately and
    let `run()` poll until the trainer writes a final iter; pass
    `poll_interval=0` to disable polling entirely.

    Returns a `TrainResult` with `final_iter` set to the last on-disk
    `iter_NNNNNNN/` (or the file value, whichever is larger). Raises
    `TrainError` if the runner returns non-zero or if the recipe is
    invalid.

    Parameters:
        recipe: The frozen `TrainRecipe` to run.
        mode: ``"full"`` (default) or ``"smoke"``. Selects
            ``runs-full/`` vs ``runs-smoke/`` under
            ``recipe.output_dir`` and clamps iterations accordingly.
        poll_interval: Seconds between disk polls. Default 30.0 —
            checkpoint saves are seconds-to-minutes apart at
            production scale, so 30s gives sub-percent overhead while
            keeping `on_progress` responsive. Set to ``0`` to disable
            polling.
        on_progress: Optional callback ``fn(latest_iter, iter_dirs)``
            invoked after each poll cycle. Useful for piping
            progress into a `Monitor` / logger / lineage row.
        runner: Optional command runner — ``fn(cmd: list[str]) -> int``.
            Defaults to a synchronous `subprocess.run` wrapper. For
            tests, pass a fake that records the command + writes a
            synthetic ``iter_NNNNNNN/`` to the run dir.
        sleep: Optional `time.sleep` replacement. Defaults to the real
            sleep; tests inject `lambda _s: None`.
    """
    try:
        recipe.preflight()
    except RecipeError as exc:
        raise TrainError(f"recipe failed preflight: {exc}") from exc
    if mode not in (MODE_SMOKE, MODE_FULL):
        raise TrainError(f"unknown mode={mode!r} (expected 'smoke' or 'full')")
    if poll_interval < 0:
        raise TrainError(
            f"poll_interval must be >= 0 (got {poll_interval})"
        )

    cmd = _build_train_command(recipe, mode=mode)
    run_dir = _resolve_run_dir(recipe, mode)
    run_dir.mkdir(parents=True, exist_ok=True)

    real_runner = runner if runner is not None else _default_runner
    real_sleep = sleep if sleep is not None else time.sleep

    started = time.monotonic()
    rc = real_runner(cmd)
    if rc != 0:
        raise TrainError(
            f"trainer returned non-zero exit code {rc} — inspect the "
            f"container's stdout for the underlying cause."
        )

    # Post-run poll loop. With the default synchronous runner this is
    # a one-shot read. With an async runner that returns 0 immediately,
    # this loop is the place the caller actually waits for completion.
    latest, iters = poll_run_progress(run_dir)
    if on_progress is not None:
        on_progress(latest, iters)

    if poll_interval > 0 and not iters:
        # Async runner with no iters yet — poll until first checkpoint.
        # Cap implicit. Caller wraps in their own timeout for runaway
        # protection.
        while not iters:
            real_sleep(poll_interval)
            latest, iters = poll_run_progress(run_dir)
            if on_progress is not None:
                on_progress(latest, iters)

    final_iter = max(latest, iters[-1] if iters else 0)
    wall = time.monotonic() - started
    return TrainResult(
        backend=recipe.backend,
        mode=mode,
        run_dir=str(run_dir),
        final_iter=final_iter,
        wall_seconds=wall,
        container=recipe.resolved_container(),
        log_path=None,
        iter_dirs=tuple(iters),
    )


# ---------------------------------------------------------------------------
# merge_and_export()
# ---------------------------------------------------------------------------


_NEMO_MERGE_SCRIPT = "/opt/Megatron-Bridge/examples/peft/merge_lora.py"
_NEMO_EXPORT_SCRIPT = (
    "/opt/Megatron-Bridge/examples/conversion/convert_checkpoints.py"
)


def _nemo_merge_command(
    recipe: TrainRecipe,
    *,
    lora_ckpt: Path,
    merged_mcore: Path,
) -> list[str]:
    container = recipe.resolved_container()
    inner_args = [
        "torchrun",
        "--nproc_per_node=1",
        _NEMO_MERGE_SCRIPT,
        "--lora-checkpoint",
        str(lora_ckpt),
        "--hf-model-path",
        str(recipe.base_model),
        "--output",
        str(merged_mcore),
    ]
    inner = " ".join(shlex.quote(a) for a in inner_args)
    return ["docker", "exec", "-w", "/tmp", container, "bash", "-lc", inner]


def _nemo_export_command(
    recipe: TrainRecipe,
    *,
    merged_mcore: Path,
    merged_hf: Path,
) -> list[str]:
    container = recipe.resolved_container()
    inner_args = [
        "python3",
        _NEMO_EXPORT_SCRIPT,
        "export",
        "--hf-model",
        str(recipe.base_model),
        "--megatron-path",
        str(merged_mcore),
        "--hf-path",
        str(merged_hf),
    ]
    inner = " ".join(shlex.quote(a) for a in inner_args)
    return ["docker", "exec", "-w", "/tmp", container, "bash", "-lc", inner]


def _unsloth_merge_command(
    recipe: TrainRecipe,
    *,
    lora_ckpt: Path,
    merged_hf: Path,
) -> list[str]:
    train_script = recipe.extra_env.get("MERGE_SCRIPT")
    if not train_script:
        raise MergeExportError(
            "Unsloth backend requires recipe.extra_env['MERGE_SCRIPT'] "
            "to point to your article-side merge entry point — the "
            "v0.5 release does not bundle a canonical Unsloth merge "
            "driver."
        )
    container = recipe.resolved_container()
    inner = " ".join(
        shlex.quote(a)
        for a in [
            "env",
            f"BASE_MODEL={recipe.base_model}",
            f"LORA_CKPT={lora_ckpt}",
            f"MERGED_HF={merged_hf}",
            "bash",
            train_script,
        ]
    )
    return ["docker", "exec", "-w", "/tmp", container, "bash", "-lc", inner]


def _resolve_lora_iter(
    recipe: TrainRecipe,
    *,
    iter: Optional[int],
    expect_iter: Optional[int],
) -> tuple[int, Path]:
    run_dir = _full_run_dir(recipe)
    if iter is None:
        latest, _ = poll_run_progress(run_dir)
        if latest <= 0:
            raise MergeExportError(
                f"merge: could not resolve LoRA iter — "
                f"{run_dir}/latest_checkpointed_iteration.txt is missing "
                f"or zero. Pass `iter=<n>` explicitly."
            )
        iter = latest
    if expect_iter is not None and iter != expect_iter:
        raise MergeExportError(
            f"merge: resolved iter={iter} ≠ expect_iter={expect_iter}. "
            f"Pass `expect_iter=None` to override, or `iter=<n>` to "
            f"merge a specific checkpoint."
        )
    lora_ckpt = run_dir / f"iter_{iter:07d}"
    return iter, lora_ckpt


def merge_and_export(
    recipe: TrainRecipe,
    *,
    iter: Optional[int] = None,
    expect_iter: Optional[int] = None,
    standardize: bool = True,
    tokenizer_class_remap: Optional[Mapping[str, str]] = None,
    runner: Optional[Callable[[list[str]], int]] = None,
) -> MergeExportResult:
    """Merge a LoRA adapter into base weights and export to HF BF16.

    Symmetric across backends:

    - **NeMo** — invokes Megatron-Bridge's
      `examples/peft/merge_lora.py` (LoRA + base → dense Megatron) then
      `examples/conversion/convert_checkpoints.py export` (Megatron →
      HF BF16). Mirrors `scripts/p65_merge_and_probe.sh` stages 1/2.
    - **Unsloth** — invokes the caller-supplied
      `recipe.extra_env['MERGE_SCRIPT']` which is expected to run
      `model.merge_and_unload()` + `tokenizer.save_pretrained()` +
      `model.save_pretrained()` in the article's `ps-train` envelope.

    After the export, runs `standardize_hf_export` on the resulting HF
    directory (unless `standardize=False`). This bakes in the two
    NeMo-export quirks (shard padding + tokenizer_class remap) so the
    output is consumer-ready for `huggingface_hub.upload_large_folder`,
    `convert_hf_to_gguf.py`, and the project's
    `fieldkit.publish.publish_quant` pipeline.

    Returns a `MergeExportResult` recording every file-level change.
    Raises `MergeExportError` on any stage failure (the failed stage
    name is the first arg of the exception).

    Parameters:
        recipe: The frozen `TrainRecipe` whose
            ``output_dir/runs-full/`` holds the LoRA checkpoints.
        iter: Explicit LoRA iteration to merge. ``None`` (default)
            resolves to the value in
            ``runs-full/latest_checkpointed_iteration.txt``.
        expect_iter: Optional sanity-check value — raises
            `MergeExportError` if the resolved iter doesn't match.
            Useful for catching early-stopped training runs.
        standardize: When True (default) runs `standardize_hf_export`
            on the exported HF directory. Disable for callers that
            already write HF-canonical output or want to inspect the
            raw export first.
        tokenizer_class_remap: Forwarded to `standardize_hf_export`.
            Defaults to `DEEPSEEK_TOKENIZER_CLASS_REMAP` when
            `standardize=True`.
        runner: Same shape as `run()`'s `runner`. Defaults to
            `subprocess.run`.
    """
    try:
        recipe.preflight()
    except RecipeError as exc:
        raise MergeExportError(f"recipe failed preflight: {exc}") from exc

    real_runner = runner if runner is not None else _default_runner
    output_root = Path(recipe.output_dir).resolve()
    merged_hf = output_root / "merged-hf-bf16"

    source_iter, lora_ckpt = _resolve_lora_iter(
        recipe, iter=iter, expect_iter=expect_iter
    )

    if recipe.backend == "nemo":
        merged_mcore = output_root / "merged-mcore"
        if merged_mcore.exists():
            shutil.rmtree(merged_mcore)
        merged_mcore.parent.mkdir(parents=True, exist_ok=True)
        merge_cmd = _nemo_merge_command(
            recipe, lora_ckpt=lora_ckpt, merged_mcore=merged_mcore
        )
        rc = real_runner(merge_cmd)
        if rc != 0:
            raise MergeExportError(
                f"merge: nemo merge_lora.py exited with {rc}"
            )
        if merged_hf.exists():
            shutil.rmtree(merged_hf)
        merged_hf.parent.mkdir(parents=True, exist_ok=True)
        export_cmd = _nemo_export_command(
            recipe, merged_mcore=merged_mcore, merged_hf=merged_hf
        )
        rc = real_runner(export_cmd)
        if rc != 0:
            raise MergeExportError(
                f"export: nemo convert_checkpoints.py exited with {rc}"
            )
        merged_mcore_str: Optional[str] = str(merged_mcore)
    else:
        if merged_hf.exists():
            shutil.rmtree(merged_hf)
        merged_hf.parent.mkdir(parents=True, exist_ok=True)
        merge_cmd = _unsloth_merge_command(
            recipe, lora_ckpt=lora_ckpt, merged_hf=merged_hf
        )
        rc = real_runner(merge_cmd)
        if rc != 0:
            raise MergeExportError(
                f"merge: unsloth driver exited with {rc}"
            )
        merged_mcore_str = None

    shard_renames: list[tuple[str, str]] = []
    tokenizer_remaps: list[tuple[str, str]] = []
    if standardize and merged_hf.is_dir():
        shard_renames, tokenizer_remaps = standardize_hf_export(
            merged_hf, tokenizer_class_remap=tokenizer_class_remap
        )

    return MergeExportResult(
        backend=recipe.backend,
        source_iter=source_iter,
        merged_hf_dir=str(merged_hf),
        merged_mcore_dir=merged_mcore_str,
        tokenizer_class_remapped=tuple(tokenizer_remaps),
        shard_renames=tuple(shard_renames),
        standardize_applied=standardize and merged_hf.is_dir(),
    )
