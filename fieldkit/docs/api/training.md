---
module: training
title: fieldkit.training
summary: Fine-tuning primitives for any RL or SFT loop on the Spark — a declarative TrainRecipe, an HF→Megatron-Core converter with the Megatron-Bridge YARN-rope-defaults fix baked in, an idempotent llama.cpp pre-tokenizer registrar, a symmetric `run()`/`merge_and_export()` driver across NeMo and Unsloth backends with poll-disk liveness and the BF16-clean export transformation baked in, a budget-normalizing `ReasoningProbe` + `ProbeReport.compare` for chain-of-thought preservation checks, a YAML-lookup `train_backend()` decision API with a `refresh()` flywheel for keeping the decision corpus current, a CPU-resident LoRA reference snapshot that sidesteps peft 0.19's offloader bug, and a pre/post weight-delta tracker for sanity-checking that gradients actually moved.
order: 5
---

## What it is

Ten primitives for any LoRA SFT or RL loop on the DGX Spark's unified-memory GB10:

- **`TrainRecipe`** — a frozen dataclass that captures the surface area `scripts/p65_train_nemo_lora.{py,sh}` spreads across argparse flags + bash env vars in a single record. Round-trips through YAML so a recipe can sit alongside its article (`articles/<slug>/recipe.yaml`) and drive either the NeMo or Unsloth lane from the same file. Pure-python; `validate()` is offline-preflight only.
- **`HFToMegatron`** — frozen dataclass wrapping `megatron.bridge.AutoBridge` with the YARN-rope-defaults fix baked in. Solves a real Megatron-Bridge 0.4.0rc0 bug: `to_megatron_provider(load_weights=True)` leaves `yarn_beta_fast` / `yarn_beta_slow` / `yarn_mscale` / `yarn_mscale_all_dim` as `None`, so the downstream `YarnRotaryEmbedding` crashes in `_yarn_find_correction_dim` (`None * math.pi`). Lazy-imports torch + megatron-bridge.
- **`register_llama_cpp_pretokenizer_hash`** — idempotent string-patcher for llama.cpp's `convert_hf_to_gguf.py`. Inserts a tokenizer-hash → pre-tokenizer mapping into the `get_vocab_base_pre` chain so new tokenizers (e.g. DeepSeek-R1-0528-Qwen3-8B) work without waiting for upstream merges. Re-apply after a fresh `git pull` on the llama.cpp checkout.
- **`run(recipe, ...)`** — symmetric LoRA SFT driver across NeMo and Unsloth backends. Builds the backend-specific `docker exec` command from a `TrainRecipe`, invokes it via an injectable `runner`, then polls `<run_dir>/latest_checkpointed_iteration.txt` + the on-disk `iter_NNNNNNN/` dirs for liveness (the *only* reliable progress signal — `train.log` can lag the process by 4+ hours under docker-exec + shell-redirect). Returns a `TrainResult` with `final_iter` / `wall_seconds` / `iter_dirs`.
- **`merge_and_export(recipe, ...)`** — merge a LoRA adapter into base + export to HF BF16, with the **BF16-clean transformation baked in**. For NeMo, invokes Megatron-Bridge's `merge_lora.py` + `convert_checkpoints.py export` and then runs `standardize_hf_export` so the resulting HF directory is consumer-ready for `huggingface_hub.upload_large_folder`, `convert_hf_to_gguf.py`, and `fieldkit.publish.publish_quant`. For Unsloth, invokes the caller-supplied `MERGE_SCRIPT` and standardizes the same way (no-op on already-clean output).
- **`standardize_hf_export(hf_dir, *, tokenizer_class_remap=...)`** — the pure-python BF16-clean helper. Two surgical fixes the patent-strategist v3 NeMo lane discovered the hard way: (1) `model-NNNNN-of-000002.safetensors` → `model-NNNNN-of-00002.safetensors` (Megatron-Bridge over-pads small shard counts; HF + llama.cpp expect the standard 5-digit width) with matching `model.safetensors.index.json` rewrite, and (2) `tokenizer_config.json`'s `tokenizer_class` field remapped via lookup table (default `DEEPSEEK_TOKENIZER_CLASS_REMAP`: `TokenizersBackend` → `LlamaTokenizer`). Idempotent.
- **`poll_run_progress(run_dir)`** — pure-python helper that reads `latest_checkpointed_iteration.txt` and scans for `iter_NNNNNNN/` directories. Safe to call from a notebook or a `Monitor` loop; returns `(0, [])` before the trainer has saved its first checkpoint. The driver loop uses this internally; surfaced as a public function so callers can build their own progress monitors.
- **`train_backend(*, base_model_family, optimize_for) -> DecidePick`** — YAML-lookup decision API. Walks the bundled `SEED_ENTRIES_DIR` + the user's `~/.fieldkit/decide-entries/` looking for an `active` `train_backend` entry whose `context.base_model_family` matches; the first finding with the matching `optimize_for` wins (entries sorted newest-first by `created`). Returns a `DecidePick` with `pick` / `backend` (alias) / `evidence` / `entry` (the matched `DecideEntry`) / `optimize_for` / `context`. Companion primitives: `load_entries` (lifecycle + question filtering), `refresh` (flags entries older than `freshness_days`; default 180 — the refresh flywheel that keeps the decision corpus from going stale silently), `DecideEntry` / `DecideFinding` for the YAML schema. The `[[project_nemo_pilot_verdict]]` "carry both Unsloth & NeMo" finding lands as the first seed entry, written alongside the bakeoff article so the next-session's `decide(...)` returns the article's findings programmatically.
- **`ReasoningProbe` + `ProbeReport`** — reasoning-preservation probe lifted from `scripts/probe_reasoning.py`. Loads a JSONL probe set with `qid`/`category`/`question` rows, runs them through a model (real torch + transformers + optional peft, or any injected `generator` callable for tests / pre-loaded models), and returns a `ProbeReport` with `overall` / `by_category` aggregates. `ProbeReport.compare(other, *, normalize_budget=True, thresholds=...)` runs the spec §4 Layer 5 pass/fail check (presence rate ≥ 90%, chain length ≥ 75%); with `normalize_budget=True`, qids whose `<think>` chain exceeds the smaller of the two `max_new_tokens` are excluded from BOTH reports so different-budget runs (e.g. the patent-strategist v3 NeMo-2048 vs Unsloth-1536 bakeoff) compare apples-to-apples. JSON shape on disk matches the standalone script's emit format; `ProbeReport.from_json` reads existing artifacts directly.
- **`LoraReferenceSnapshot`** — a CPU-resident snapshot of a peft adapter's LoRA tensors plus a context manager that swaps the snapshot into the live model for one no-grad forward pass and restores trainable weights on exit. **Solves a real peft 0.19 bug**: `model.load_adapter(adapter_name="reference", is_trainable=False)` crashes with a `KeyError` under `device_map="auto"` whenever the GPU has anything else resident — peft's offload-detection over-triggers on Spark unified memory. Verified with vLLM co-resident *and* with the trainer alone. The snapshot/swap dance sidesteps the offloader entirely.
- **`WeightDeltaTracker`** — pre/post snapshot of trainable params with L2 + max|Δ| reporting. Sanity-check that any fine-tuning step actually moved weights. The first time someone debugs "why didn't my LoRA update?" they'll wish for this.

All ten use **lazy `torch` imports** so `import fieldkit.training` costs nothing in environments that don't run training. Construct any class and you'll get a clear `ImportError` if `torch` (or `safetensors`, for `LoraReferenceSnapshot.from_disk`, or `megatron-bridge` for `HFToMegatron`) isn't installed — install them yourself in the training environment. NeMo / Triton / pytorch-base containers ship them; pure inference envs don't. `run` / `merge_and_export` / `standardize_hf_export` / `poll_run_progress` are pure-python and have no heavy dependencies; they shell out to docker only when invoked through the default runner.

## Public API

```python
from fieldkit.training import (
    CompareResult,
    CompareRow,
    CompareThresholds,
    DEEPSEEK_R1_0528_QWEN3_TOKENIZER_HASH,
    DEEPSEEK_TOKENIZER_CLASS_REMAP,
    DEFAULT_COMPARE_THRESHOLDS,
    DEFAULT_FRESHNESS_DAYS,
    ConvertError,
    DecideEntry,
    DecideError,
    DecideFinding,
    DecidePick,
    HFToMegatron,
    LoraReferenceSnapshot,
    MODE_FULL,
    MODE_SMOKE,
    MergeExportError,
    MergeExportResult,
    ProbeError,
    ProbeQuestion,
    ProbeReport,
    ProbeRow,
    ProbeSummary,
    ReasoningProbe,
    RecipeError,
    SEED_ENTRIES_DIR,
    StalenessReport,
    THINK_REGEX,
    TrainError,
    TrainRecipe,
    TrainResult,
    USER_ENTRIES_DIR,
    VALID_LIFECYCLES,
    WeightDeltaTracker,
    YARN_DEFAULTS,
    load_entries,
    merge_and_export,
    parse_think,
    patch_yarn_defaults,
    poll_run_progress,
    refresh,
    register_llama_cpp_pretokenizer_hash,
    run,
    standardize_hf_export,
    summarize_rows,
    train_backend,
)
```

### `HFToMegatron(hf_model, megatron_path, torch_dtype="bfloat16")`

Frozen dataclass; construct + call `.run()`. Runs inside `nvcr.io/nvidia/nemo:26.04.00` (container `nemo-train`).

```python
from fieldkit.training import HFToMegatron

job = HFToMegatron(
    hf_model="/home/nvidia/data/.hf-cache/hub/models--deepseek-ai--DeepSeek-R1-0528-Qwen3-8B/snapshots/<sha>/",
    megatron_path="/home/nvidia/data/aifn-train-lora/p65-nemo/mcore-base",
    torch_dtype="bfloat16",
)
summary = job.run()
# {'hf_model': ..., 'megatron_path': ..., 'torch_dtype': 'bfloat16',
#  'yarn_patched_fields': ['yarn_beta_fast', 'yarn_beta_slow', ...],
#  'position_embedding_type': 'yarn'}
```

The `yarn_patched_fields` entry in the summary is the empty list for non-YARN models (no patch needed) and the list of fields written for YARN models (most often the full set on first call). Outside the `nemo-train` envelope `.run()` raises `ConvertError` with a clear pointer.

### `patch_yarn_defaults(provider) -> list[str]`

The load-bearing helper, also exported so callers driving Megatron-Bridge directly can apply just the patch without going through `HFToMegatron`. Sets `yarn_beta_fast=32.0` / `yarn_beta_slow=1.0` / `yarn_mscale=1.0` / `yarn_mscale_all_dim=0.0` / `yarn_correction_range_round_to_int=True` (defaults lifted from `megatron.core.models.common.embeddings.yarn_rotary_pos_embedding`) on a provider whose YARN fields the bridge left as `None`. Idempotent — re-running after a successful patch is a no-op (returns `[]`). Non-YARN providers are skipped (also returns `[]`).

The `YARN_DEFAULTS` constant is exposed too, for inspection or custom-patch callers.

### `register_llama_cpp_pretokenizer_hash(convert_script, *, chkhsh, pre_tokenizer, model_ref=None, note=None)`

Idempotent string-patcher. Inserts a 3-4 line block into llama.cpp `convert_hf_to_gguf.py`'s `get_vocab_base_pre` `if chkhsh == "...":` chain. Returns `True` if a new block was inserted, `False` if the hash was already present.

```python
from fieldkit.training import (
    DEEPSEEK_R1_0528_QWEN3_TOKENIZER_HASH,
    register_llama_cpp_pretokenizer_hash,
)

inserted = register_llama_cpp_pretokenizer_hash(
    "/home/nvidia/llama.cpp/convert_hf_to_gguf.py",
    chkhsh=DEEPSEEK_R1_0528_QWEN3_TOKENIZER_HASH,
    pre_tokenizer="qwen35",
    model_ref="https://huggingface.co/deepseek-ai/DeepSeek-R1-0528-Qwen3-8B",
    note="Qwen3 BPE + Metaspace pre-tokenizer + DeepSeek special tokens",
)
# inserted=True on a fresh `git pull`; False on a re-run.
```

Raises `ConvertError` if the script is missing, the hash isn't a valid 64-char hex digest, or the chain pattern can't be located.

### `TrainRecipe(base_model, dataset_jsonl, output_dir, ...)`

Frozen dataclass that captures the surface area `scripts/p65_train_nemo_lora.{py,sh}` spreads across argparse flags + bash env vars in a single record. See `tests/test_training_recipe.py` for the full surface; key fields:

```python
from fieldkit.training import TrainRecipe

recipe = TrainRecipe(
    base_model="/home/nvidia/data/aifn-train-lora/p65-nemo/mcore-base",
    dataset_jsonl="/home/nvidia/data/aifn-train-lora/p65-nemo/corpus-v3.jsonl",
    output_dir="/home/nvidia/data/aifn-train-lora/p65-nemo/runs-full",
    backend="nemo",        # or "unsloth"
    seq_length=4096,
    micro_batch_size=2,
    global_batch_size=16,
    learning_rate=1e-4,
    max_steps=625,
    save_interval=50,
    most_recent_k=3,
    smoke_steps=10,
    torch_dtype="bfloat16",
)
recipe.validate()                  # pure-python preflight (no FS reads)
recipe.preflight()                 # adds filesystem checks
recipe.to_yaml("recipe.yaml")      # persist for re-runs
TrainRecipe.from_yaml("recipe.yaml")  # round-trip
recipe.lora_target_modules_for_backend()
# → ("linear_qkv", "linear_proj") on backend="nemo"
# → ("q_proj", "k_proj", "v_proj", "o_proj") on backend="unsloth"
```

The backend-target-modules mapping makes a single recipe portable across NeMo (Megatron-Bridge's fused `linear_qkv` / `linear_proj`) and Unsloth (HF names verbatim) without duplicating the LoRA target list per backend.

### `run(recipe, *, mode="full", poll_interval=30.0, on_progress=None, runner=None, sleep=None) -> TrainResult`

Launch a LoRA SFT run for the given recipe and poll disk for liveness. Symmetric across `recipe.backend == "nemo"` and `"unsloth"`.

```python
from fieldkit.training import TrainRecipe, run, MODE_FULL

recipe = TrainRecipe.from_yaml("articles/<slug>/recipe.yaml")
result = run(recipe, mode=MODE_FULL)
# result.final_iter, result.iter_dirs, result.wall_seconds
```

The function:

1. Calls `recipe.preflight()` to fail fast on bad inputs.
2. Builds the backend-specific `docker exec` command. **NeMo:** `scripts/p65_train_nemo_lora.py` with `--hf-model / --pretrained-mcore / --dataset-root / --run-dir / (--train-iters | --smoke)` — overridable via `recipe.extra_env['TRAIN_SCRIPT' | 'MCORE_BASE' | 'DATASET_DIR']`. **Unsloth:** invokes the caller-supplied `recipe.extra_env['TRAIN_SCRIPT']` with recipe fields passed as env vars (`BASE_MODEL` / `DATASET_JSONL` / `RUN_DIR` / `MODE` / `MAX_STEPS` / `SMOKE_STEPS` / `SEQ_LENGTH` / `MICRO_BATCH_SIZE` / `GLOBAL_BATCH_SIZE` / `LEARNING_RATE` / `LORA_RANK` / `LORA_ALPHA`).
3. Invokes the command via the `runner` callable (defaults to `subprocess.run`).
4. Polls `<run_dir>/latest_checkpointed_iteration.txt` and the `iter_NNNNNNN/` directories on disk — the *only* reliable progress signal. `train.log` can lag the process by 4+ hours under docker-exec + shell-redirect, so tail-grep of stdout is not a substitute.

Run-dir layout under `recipe.output_dir`:

- `runs-smoke/` — when `mode="smoke"` (clamped to `recipe.smoke_steps` iterations).
- `runs-full/` — when `mode="full"` (`recipe.max_steps` iterations).

Parameters:

- `mode`: `"full"` (default) or `"smoke"`.
- `poll_interval`: seconds between disk polls (default 30.0). Set to `0` to disable polling entirely; useful for synchronous runners that block until the trainer exits.
- `on_progress`: optional callback `fn(latest_iter, iter_dirs)` invoked after each poll cycle. Pipe into a `Monitor` / logger / lineage row.
- `runner`: optional `fn(cmd: list[str]) -> int` command runner; defaults to a synchronous `subprocess.run` wrapper. Tests inject a fake that records the command and writes synthetic `iter_NNNNNNN/`.
- `sleep`: optional `time.sleep` replacement; tests inject `lambda _s: None`.

Raises `TrainError` on recipe-preflight failure, bad `mode` / `poll_interval`, missing Unsloth `TRAIN_SCRIPT`, or non-zero exit code from the runner.

### `merge_and_export(recipe, *, iter=None, expect_iter=None, standardize=True, tokenizer_class_remap=None, runner=None) -> MergeExportResult`

Merge a LoRA adapter into base weights and export to HF BF16, with the **BF16-clean transformation baked in**.

```python
from fieldkit.training import merge_and_export, MergeExportResult

result = merge_and_export(recipe, expect_iter=625)
# result.merged_hf_dir       — path the exporter wrote
# result.shard_renames       — [(old, new), …] applied by standardize
# result.tokenizer_class_remapped  — [(old_class, new_class), …]
```

- **NeMo** — invokes Megatron-Bridge's `examples/peft/merge_lora.py` (LoRA + base → dense Megatron) then `examples/conversion/convert_checkpoints.py export` (Megatron → HF BF16). Mirrors `scripts/p65_merge_and_probe.sh` stages 1/2. The merged Megatron checkpoint lands at `<output_dir>/merged-mcore/`, the HF export at `<output_dir>/merged-hf-bf16/`.
- **Unsloth** — invokes `recipe.extra_env['MERGE_SCRIPT']` with `BASE_MODEL` / `LORA_CKPT` / `MERGED_HF` env vars; the script is expected to run `model.merge_and_unload()` + `tokenizer.save_pretrained()` + `model.save_pretrained()`. The HF export lands at `<output_dir>/merged-hf-bf16/`.

After the export, runs `standardize_hf_export` on the resulting HF directory (unless `standardize=False`). This bakes in the two known NeMo-export quirks (shard padding + tokenizer_class remap) so the output is consumer-ready.

Parameters:

- `iter`: explicit LoRA iteration to merge. `None` resolves to the value in `runs-full/latest_checkpointed_iteration.txt`.
- `expect_iter`: optional sanity-check value — raises if the resolved iter doesn't match. Catches early-stopped training runs.
- `standardize`: when `True` (default) runs `standardize_hf_export`. Disable for callers that already write HF-canonical output or want to inspect the raw export first.
- `tokenizer_class_remap`: forwarded to `standardize_hf_export`. Defaults to `DEEPSEEK_TOKENIZER_CLASS_REMAP`.
- `runner`: same shape as `run()`'s `runner`. Defaults to `subprocess.run`.

Raises `MergeExportError` on recipe-preflight failure, missing iter / expect-iter mismatch, missing Unsloth `MERGE_SCRIPT`, or non-zero exit from any stage (merge / export / standardize).

### `standardize_hf_export(hf_dir, *, tokenizer_class_remap=None)`

Bake in the two NeMo-export quirks on any HF model directory. Returns `(shard_renames, tokenizer_remaps)` — each a list of `(old, new)` tuples. Empty lists signal "already standard".

```python
from fieldkit.training import standardize_hf_export

shard_renames, tokenizer_remaps = standardize_hf_export(
    "/home/nvidia/data/aifn-train-lora/p65-nemo/merged-hf-bf16",
)
# shard_renames = [
#   ('model-00001-of-000002.safetensors', 'model-00001-of-00002.safetensors'),
#   ('model-00002-of-000002.safetensors', 'model-00002-of-00002.safetensors'),
# ]
# tokenizer_remaps = [('TokenizersBackend', 'LlamaTokenizer')]
```

Idempotent: re-running on an already-standardized dir yields `([], [])` and writes nothing. Tolerant of missing `model.safetensors.index.json` (single-shard exports) and missing `tokenizer_config.json` (model-only checkpoints). Raises `MergeExportError` only on malformed inputs (rename collision, non-JSON index, etc.).

The `tokenizer_class_remap` parameter is an explicit lookup table — pass `{}` to disable the tokenizer fix while keeping the shard rename, or pass a custom table to handle other model families (e.g. `{"CustomBackend": "MistralTokenizer"}`). The default `DEEPSEEK_TOKENIZER_CLASS_REMAP` is also exported as a module-level constant so callers can inspect or extend it.

### `poll_run_progress(run_dir)`

Pure-python disk-poll helper used internally by `run()`. Returns `(latest_iter_from_file, sorted_iter_dirs_on_disk)`:

```python
from fieldkit.training import poll_run_progress

latest, iters = poll_run_progress("/home/nvidia/data/.../runs-full")
# latest = 625  (from latest_checkpointed_iteration.txt)
# iters  = [550, 600, 625]  (iter_NNNNNNN/ on disk, sorted)
```

`latest` defaults to `0` if the file is missing or unparseable; `iters` is empty if no `iter_NNNNNNN/` directory exists. Safe to call from a notebook or a `Monitor` loop — `(0, [])` on a non-existent run dir is the documented quiescent state, not an error.

### `ReasoningProbe(questions)`

Reasoning-preservation probe orchestrator. Construct from a sequence of `ProbeQuestion`, or load a JSONL probe set via `ReasoningProbe.from_jsonl(path)`. Then call `run(model_id, ...)` to generate a `ProbeReport`. `len(probe)` returns the question count.

```python
from fieldkit.training import ReasoningProbe

probe = ReasoningProbe.from_jsonl("probes/reasoning-preservation-20q.jsonl")
report = probe.run(
    model_id="deepseek-ai/DeepSeek-R1-0528-Qwen3-8B",
    lora_path="/work/runs/checkpoint-200",
    step=200,
    max_new_tokens=1024,
)
report.to_json("probes/smoke-step200.json")
```

Raises `ProbeError` on an empty question list at construction time.

### `ReasoningProbe.from_jsonl(path)`

Load a probe set from JSONL — one `ProbeQuestion` per line. Required per-line keys: `qid`, `category`, `question`. Optional pass-throughs: `source`, `license`; any other keys are gathered into the question's `metadata` dict. Raises `ProbeError` on missing required keys, malformed JSON, missing files, or empty input.

```python
probe = ReasoningProbe.from_jsonl("probes/reasoning-preservation-20q.jsonl")
# 20 questions across general-reasoning / patent-irac / patent-strategic
```

### `ReasoningProbe.run(model_id, *, lora_path=None, step=None, max_new_tokens=1024, temperature=0.6, generator=None, on_progress=None) -> ProbeReport`

Iterates the probe set, generates a response per question, parses the `<think>` block, and returns a `ProbeReport`.

Without a `generator`, the default path lazy-imports `torch` + `transformers` (and `peft` if `lora_path` is set) and loads the base model in bf16 on `cuda:0` with `attn_implementation="sdpa"`. With `generator=fn` (signature `fn(ProbeQuestion) -> str`), the load is skipped entirely — used by tests and by callers driving the probe from a pre-loaded model.

```python
report = probe.run(
    model_id="deepseek-ai/DeepSeek-R1-0528-Qwen3-8B",
    lora_path="/work/runs/checkpoint-200",
    step=200,
    max_new_tokens=1024,          # ≥1024 to avoid <think>-block truncation
    temperature=0.6,              # R1-distill recommended
    on_progress=lambda i, n, row: print(f"[{i}/{n}] qid={row.qid} has_think={row.has_think}"),
)
```

Per `[[feedback_reasoning_model_npredict]]`, `max_new_tokens<1024` truncates `<think>` blocks before the answer token lands on R1-distill / DAPO / GRPO models — bump to 1536 / 2048 for long-chain probe sets. Raises `ProbeError` if `max_new_tokens <= 0`; raises `ImportError` (with a clear pointer) if the default generator can't find `torch` / `transformers` / `peft`.

### `ProbeReport(*, model, rows, max_new_tokens, temperature=0.6, lora_path=None, step=None, wall_seconds=0.0, excluded_qids=())`

Bag of `ProbeRow` plus run-metadata. Read-only properties for every constructor arg, plus `n`, `overall`, and `by_category`. Construct directly (in tests + callers that already have rows) or via `ProbeReport.from_json(path)`.

```python
report = ProbeReport(
    model="m",
    rows=[ProbeRow(qid="q1", category="c", response="<think>x</think>y",
                   has_think=True, think_n_tok=200, think_text="x")],
    max_new_tokens=1024,
)
report.overall      # ProbeSummary(think_presence_rate=1.0, think_token_length=200.0, n=1)
report.by_category  # {"c": ProbeSummary(...)}
```

Raises `ProbeError` on `max_new_tokens <= 0`.

### `ProbeReport.from_json(path)` / `ProbeReport.to_json(path, *, indent=2)`

Round-trip a report through disk. The on-disk JSON shape matches what `scripts/probe_reasoning.py` emits and what existing artifacts in `probes/baseline.json` / `probes/patent-strategist-v3-*.json` use:

```python
report = ProbeReport.from_json("probes/patent-strategist-v3-nemo-2026-05-21.json")
report.to_json("probes/normalized.json")
```

`raw_responses` is the source of truth on load — the JSON's `overall` / `by_category` blocks (and the legacy `think_quality_score` key) are recomputed from rows, not loaded. Raises `ProbeError` on missing files, invalid JSON, or missing required row keys.

### `ProbeReport.with_budget(cap)`

Returns a new `ProbeReport` excluding any row whose `<think>` chain exceeds `cap` tokens. Rows with `has_think=False` are preserved unchanged — the cap doesn't change whether a truncated response had a chain to begin with. The new report's `max_new_tokens` is set to `min(self.max_new_tokens, cap)`, and the dropped qids are appended to `excluded_qids` (composes across multiple `with_budget` calls).

```python
nemo_at_2048 = ProbeReport.from_json("probes/patent-strategist-v3-nemo-2026-05-21.json")
nemo_normalized = nemo_at_2048.with_budget(1536)
nemo_normalized.excluded_qids  # qids with think_n_tok > 1536 — p-p-strat-01 etc.
```

Raises `ProbeError` on `cap <= 0`.

### `ProbeReport.compare(other, *, normalize_budget=True, thresholds=None, baseline_label=None, current_label=None) -> CompareResult`

Compare this report (treated as **current**) against `other` (treated as **baseline**). Two metrics: `think_presence_rate` and `think_token_length`. Returns a `CompareResult` with per-metric pass/fail + `all_pass` aggregate.

`normalize_budget=True` (the default) handles different-budget runs — if `self.max_new_tokens != other.max_new_tokens`, both reports are first `with_budget(min(...))`-filtered and any qid whose `think_n_tok` exceeds the cap in EITHER report is excluded from BOTH. Apples-to-apples comparison; the excluded qids land on `CompareResult.excluded_qids` for footnoting. `normalize_budget=False` compares raw aggregates regardless of budget skew.

```python
unsloth = ProbeReport.from_json("probes/patent-strategist-v3-2026-05-21.json")        # 1536
nemo    = ProbeReport.from_json("probes/patent-strategist-v3-nemo-2026-05-21.json")   # 2048

result = nemo.compare(
    unsloth,
    normalize_budget=True,
    baseline_label="unsloth",
    current_label="nemo",
)
result.all_pass        # True / False on spec §4 Layer 5 thresholds
result.budget_cap      # 1536
result.excluded_qids   # ("p-p-strat-01",) — qid that exceeded the smaller budget
result.per_category    # {"general-reasoning": {"baseline_presence": ..., "current_presence": ...}, ...}
for row in result.rows:
    print(row.metric, row.status, row.ratio, row.threshold)
```

Custom thresholds via `thresholds=CompareThresholds(think_presence_rate=0.95, think_token_length=0.80)`. Skip status fires when baseline is None or 0 (ratio undefined); skipped metrics are excluded from the `all_pass` tally.

### `parse_think(response) -> (has_think, think_n_tok, think_text)`

Picks the longest `<think>...</think>` pair from a response. R1-distill models occasionally false-start with an empty `<think></think>` before the real chain — the non-greedy regex alone would match the empty pair first and undercount. `think_n_tok` is `None` when no block is present, `0` for an empty block, and `len(text) // 4` (char-quarter approximation) otherwise.

```python
from fieldkit.training import parse_think

has, n_tok, text = parse_think("<think></think>first<think>real chain</think>answer")
# has=True, n_tok≈2, text="real chain"
```

### `summarize_rows(rows) -> ProbeSummary`

Pure-python aggregator. `think_presence_rate` is computed over all rows; `think_token_length` is the mean over `has_think=True` rows only (zero on empty input). Re-runnable after any filter so callers can build subset summaries without going through `ProbeReport`.

```python
from fieldkit.training import summarize_rows

patent_only = [r for r in report.rows if r.category.startswith("patent-")]
summary = summarize_rows(patent_only)
```

### `ProbeQuestion(qid, category, question, *, source=None, license=None, metadata=...)`

Frozen dataclass — one row of a probe set. `source` / `license` are optional pass-throughs lifted from the probe-set JSONL; any extra keys land in `metadata`. Round-trippable through provenance audits.

### `ProbeRow(qid, category, response, has_think, think_n_tok, think_text, wall_seconds=0.0)`

Frozen dataclass — one per-question result. `think_n_tok` is `None` when `has_think=False`, `0` for an empty block, char-quarter approx otherwise.

### `ProbeSummary(think_presence_rate, think_token_length, n)`

Frozen dataclass returned by `summarize_rows`, `ProbeReport.overall`, and the values of `ProbeReport.by_category`.

### `CompareThresholds(think_presence_rate=0.90, think_token_length=0.75)`

Frozen dataclass holding the per-metric pass ratios. `DEFAULT_COMPARE_THRESHOLDS` is the module-level singleton with the spec §4 Layer 5 defaults; pass a custom instance to `ProbeReport.compare(thresholds=...)` for stricter / looser bars. The third spec metric (`think_quality_score` ≥ 0.80, LLM-judge coherence) is intentionally not surfaced here — that scoring is owned by an in-CC-session orchestrator skill per `[[feedback_llm_skill_pattern]]`.

### `CompareRow` / `CompareResult`

Frozen dataclasses returned by `ProbeReport.compare`. `CompareRow` is per-metric (`metric` / `baseline` / `current` / `ratio` / `threshold` / `status`); `CompareResult` wraps the per-metric rows plus `all_pass`, `baseline_label`, `current_label`, `budget_normalized`, `budget_cap`, `excluded_qids`, and `per_category`.

### `ProbeError`

Raised by `ReasoningProbe.run()` / `ReasoningProbe.from_jsonl` / `ProbeReport.from_json` / `ProbeReport.with_budget` on malformed input or bad arguments. Distinct from `ValueError` so callers can selectively catch probe-layer failures.

### `THINK_REGEX`

Compiled `re.Pattern` for `<think>(.*?)</think>` with `re.DOTALL`. Exposed for callers that re-parse cached responses without going through `parse_think` (e.g. the LLM-judge sidecar described in `[[feedback_llm_skill_pattern]]`).

### `train_backend(*, base_model_family, optimize_for, dirs=None) -> DecidePick`

YAML-lookup decision API. Walks the configured entry directories (default = bundled `SEED_ENTRIES_DIR` + `USER_ENTRIES_DIR`), filters to `lifecycle="active"` entries with `question="train_backend"`, sorts by `created` descending, and returns the first finding whose `optimize_for` matches the argument from an entry whose `context.base_model_family` matches.

```python
from fieldkit.training import train_backend

pick = train_backend(
    base_model_family="qwen3-r1-distill",
    optimize_for="patent_chain_length",
)
pick.backend        # "nemo" — alias for pick.pick
pick.evidence       # "+44% mean chain, -26% wall vs unsloth on R1-Qwen3-8B"
pick.entry.slug     # "2026-05-22-paired-bakeoff"
pick.entry_path     # Path to the entry YAML
```

Raises `DecideError` (with a message that lists every active entry's slug + `created` date for the no-context-match case, or the available `optimize_for` keys for the partial-match case) if no entry covers the cell. Pass `dirs=[path1, path2, ...]` to scope the lookup (tests do this; production callers usually want the default search path).

### `load_entries(*, dirs=None, lifecycle="active", question=None) -> list[DecideEntry]`

Read every YAML / JSON entry under each directory. `lifecycle` accepts a single value, a sequence of values, or `None` (return entries of any lifecycle). `question` filters on `entry.question` when set. Returns entries sorted by `created` descending so callers iterating linearly hit the freshest finding first.

```python
from fieldkit.training import load_entries

active = load_entries()                                  # default = active only
all_entries = load_entries(lifecycle=None)               # full corpus including superseded
backend_picks = load_entries(question="train_backend")   # one question only
audit = load_entries(lifecycle=["active", "superseded"], question="train_backend")
```

Missing directories are silently skipped (no error). Files with unsupported suffixes (`.md`, `.txt`, etc.) are ignored — only `.yaml` / `.yml` / `.json` files are parsed. Raises `DecideError` on bad lifecycle values.

### `refresh(*, dirs=None, freshness_days=180, today=None, include_lifecycle=None) -> list[StalenessReport]`

Walk every entry and flag any older than `freshness_days`. Returns a list of `StalenessReport` (one per entry) sorted by `age_days` descending — oldest first so callers act on the stalest entries first. By default scans entries of every lifecycle (`include_lifecycle=None`) — the refresh flywheel cares about the full corpus, not just active entries. Pass `include_lifecycle="active"` to scope.

```python
from fieldkit.training import refresh

reports = refresh()  # freshness_days = DEFAULT_FRESHNESS_DAYS = 180
stale = [r.entry for r in reports if r.stale]
for entry in stale:
    print(f"{entry.slug}: created {entry.created} — re-verify or supersede")
```

Raises `DecideError` if `freshness_days` is negative. `today` defaults to `date.today()`; tests override.

### `DecideEntry(slug, lifecycle, created, question, context, findings, *, sources=(), supersedes=(), notes="", path=None)`

Frozen dataclass for a parsed YAML entry. Load via `DecideEntry.from_yaml(path)` or `DecideEntry.from_dict(data)`. Constructor enforces `lifecycle in VALID_LIFECYCLES` and `len(findings) >= 1`.

```python
from fieldkit.training import DecideEntry

entry = DecideEntry.from_yaml("data/decide-entries/2026-05-22-paired-bakeoff.yaml")
entry.matches_context(base_model_family="qwen3-r1-distill")   # bool
entry.find(optimize_for="patent_chain_length")                 # DecideFinding | None
entry.age_days(today=date(2026, 5, 22))                        # int — clamps negative to 0
```

The YAML schema:

```yaml
slug: 2026-05-22-paired-bakeoff       # required, unique within dir
lifecycle: active                     # active | superseded | deprecated
created: 2026-05-22                   # ISO date (YYYY-MM-DD)
question: train_backend               # the decide.<name>() entry point
context:                              # required mapping
  base_model_family: qwen3-r1-distill
findings:                             # required, non-empty
  - optimize_for: patent_chain_length
    pick: nemo
    evidence: "+44% mean chain ..."
sources: []                           # optional, default []
supersedes: []                        # optional, default []
notes: "free-form annotation"         # optional
```

`from_yaml` uses optional `pyyaml` if available; falls back to `json.loads` so JSON-shaped entries work even in pyyaml-less environments. Unknown top-level keys are tolerated for forward compatibility; unknown keys inside a finding survive under `finding.extra`. Raises `DecideError` on missing required keys, bad shapes, invalid lifecycle values, or unparseable dates.

### `DecideFinding` / `DecidePick` / `StalenessReport`

Frozen dataclasses. `DecideFinding(optimize_for, pick, evidence="", extra={})` is one row of an entry's `findings` list. `DecidePick(pick, evidence, entry, optimize_for, context)` is the return value of `train_backend` (with `.backend` and `.entry_path` convenience accessors). `StalenessReport(entry, age_days, stale)` is one row of `refresh()` output.

### `SEED_ENTRIES_DIR` / `USER_ENTRIES_DIR` / `VALID_LIFECYCLES` / `DEFAULT_FRESHNESS_DAYS`

Module constants. `SEED_ENTRIES_DIR` is the bundled-in-wheel entry dir (under `fieldkit.training.data/decide-entries/`); `USER_ENTRIES_DIR` is `~/.fieldkit/decide-entries/` (read-after-write, gitignored, created by the caller on first write). `VALID_LIFECYCLES = {"active", "superseded", "deprecated"}` is the locked set of lifecycle values. `DEFAULT_FRESHNESS_DAYS = 180` is the default `refresh()` cutoff (six months — matches typical hardware / framework / base-model drift cadence).

### `DecideError`

Raised by `load_entries` / `train_backend` / `refresh` / `DecideEntry.from_dict` / `DecideEntry.from_yaml` on bad inputs or unresolved lookups. Distinct from `ValueError` so callers can selectively catch decide-layer failures.

### `TrainResult` / `MergeExportResult`

Frozen dataclasses returned from `run()` and `merge_and_export()` respectively.

```python
TrainResult(
    backend="nemo",
    mode="full",
    run_dir="/home/nvidia/data/.../runs-full",
    final_iter=625,
    wall_seconds=11340.5,
    container="nemo-train",
    log_path=None,
    iter_dirs=(550, 600, 625),
)

MergeExportResult(
    backend="nemo",
    source_iter=625,
    merged_hf_dir="/home/nvidia/data/.../merged-hf-bf16",
    merged_mcore_dir="/home/nvidia/data/.../merged-mcore",
    tokenizer_class_remapped=(("TokenizersBackend", "LlamaTokenizer"),),
    shard_renames=(
        ("model-00001-of-000002.safetensors", "model-00001-of-00002.safetensors"),
        ("model-00002-of-000002.safetensors", "model-00002-of-00002.safetensors"),
    ),
    standardize_applied=True,
)
```

Both are hashable; safe to drop into a lineage row.

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
