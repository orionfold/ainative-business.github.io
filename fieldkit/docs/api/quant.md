---
module: quant
title: fieldkit.quant
summary: GGUF quantize + measure pipeline — wraps llama.cpp's `convert_hf_to_gguf.py` + `llama-quantize` + `llama-perplexity` + `llama-bench`, plus a pure-stdlib `nvidia-smi` thermal probe. Emits the `QuantReport` shape `fieldkit.publish.publish_quant` consumes. Non-GGUF formats (AWQ / GPTQ / EXL3 / MLX / NVFP4) are named stubs reserving the v0.5 API surface.
order: 7
---

## What it is

The Spark-side production line for Orionfold GGUF cards. One module-level call (`quantize_gguf`) produces every variant — `Q4_K_M`, `Q5_K_M`, `Q6_K`, `Q8_0`, `F16` — from a HuggingFace Transformers checkpoint, using the locally-built llama.cpp binaries. Two measurement helpers (`measure_perplexity_gguf`, `measure_tokens_per_sec_gguf`) and a `ThermalProbe` collect the three numbers every Orionfold quant card carries: perplexity (vs wikitext-2), sustained `tok/s` (via `llama-bench`), and minutes-before-thermal-throttle on the GB10's GPU.

The shape exists because the v0.4 quant pipeline used to be three shell scripts that disagreed about argument names and wrote three different report formats. `fieldkit.quant` collapses them behind one `QuantReport` dataclass — the contract `fieldkit.publish.publish_quant` reads. Quantize once, measure four axes, hand the report to publish, get a model card.

Non-GGUF formats are reserved as named stubs. `quantize_awq()`, `quantize_gptq()`, `quantize_exl3()`, `quantize_mlx()`, `quantize_nvfp4()` each raise `NotImplementedError` with a one-line pointer at `ideas/mtbm-use-cases.md` §7. The stubs lock the v0.4 public surface so v0.5+ implementations slot in without an API break — callers can write code against `quantize_<format>(...)` today and pick which formats actually run later.

## Public API

```python
from fieldkit.quant import (
    GGUFVariant, GGUF_VARIANTS, QuantFormat,
    QuantReport, QuantError, LlamaCppNotFound,
    LlamaCppPaths, ThermalProbe, ThermalReading,
    quantize_gguf,
    quantize_awq, quantize_gptq, quantize_exl3, quantize_mlx, quantize_nvfp4,
    measure_perplexity_gguf,
    measure_tokens_per_sec_gguf,
    parse_perplexity_output,
    parse_llama_bench_output,
)
```

### `GGUF_VARIANTS`

```python
GGUF_VARIANTS = ("Q4_K_M", "Q5_K_M", "Q6_K", "Q8_0", "F16")
```

The canonical Orionfold variant set (Bartowski-comparable). Order matters — perplexity tables in model cards walk this list left to right. `GGUFVariant` is type-aliased to `str` so experimental additions (`IQ4_XS`, etc.) don't require an enum bump.

### `LlamaCppPaths`

Locator dataclass for the four llama.cpp executables: `llama-quantize`, `llama-perplexity`, `llama-bench`, and `convert_hf_to_gguf.py`. `resolve()` fills any unset field from env (`LLAMA_CPP_BIN`, `LLAMA_CPP_CONVERT`) and `which` lookups; `require(attr)` returns the path or raises `LlamaCppNotFound` with a clear remediation message.

```python
paths = LlamaCppPaths().resolve()    # populate from env + PATH
paths.require("quantize")            # → Path('/home/nvidia/llama.cpp/build/bin/llama-quantize')
```

### `quantize_gguf(...)`

```python
report = quantize_gguf(
    model="AdaptLLM/finance-chat",          # HF repo id OR local Transformers checkpoint dir
    outdir="/home/nvidia/data/quants/finance-chat",
    variants=("Q4_K_M", "Q5_K_M", "Q6_K", "Q8_0", "F16"),
    paths=LlamaCppPaths().resolve(),
    base_model_id="AdaptLLM/finance-chat",   # threaded into the QuantReport
    dry_run=False,                            # True enumerates the would-be subprocess commands
)
print(report.variant_files["Q4_K_M"])
# {'path': '/home/nvidia/data/quants/finance-chat/model-Q4_K_M.gguf', 'rel': 'model-Q4_K_M.gguf', 'size': '3.8 GB'}
```

If the source isn't already a GGUF, `quantize_gguf` first invokes `convert_hf_to_gguf.py --outtype f16` to produce a base F16 file, then runs `llama-quantize` per variant against that intermediate. The intermediate is reused as the F16 variant of the final report — no double-conversion. `dry_run=True` enumerates the subprocess commands into `report.notes` without running them; this is the path tests + CI use to verify the orchestration without needing an 8 GB checkpoint on hand.

### `measure_perplexity_gguf(gguf, *, corpus, paths, n_ctx=512)`

Wraps `llama-perplexity`. Returns a `float` parsed from the canonical `Final estimate: PPL = N.NNN` line, or `None` on parse failure. Cards that ship without a perplexity column use the `None` path — the rendering is forgiving (the column shows `—`).

```python
ppl = measure_perplexity_gguf(
    "/home/nvidia/data/quants/finance-chat/model-Q4_K_M.gguf",
    corpus="/home/nvidia/data/calibration/wikitext-2-raw-v1/wiki.test.raw",
    paths=paths,
)  # → 6.2215
```

### `measure_tokens_per_sec_gguf(gguf, *, paths, metric='tg', n_gpu_layers=99)`

Wraps `llama-bench`. `metric='tg'` returns text-generation `tok/s`; `metric='pp'` returns prompt-processing `tok/s`. Returns `None` on parse failure.

```python
tg = measure_tokens_per_sec_gguf(gguf, paths=paths, metric='tg')   # → 31.1
pp = measure_tokens_per_sec_gguf(gguf, paths=paths, metric='pp')   # → 1111.1
```

### `ThermalProbe(interval_s=2.0, throttle_temp_c=83.0)`

Pure-stdlib `nvidia-smi` poll loop. Spin one in a background thread for the duration of a measurement run; on `stop()` it returns sustained-load minutes (the wall-clock time before the first sample crossed `throttle_temp_c` or hit a `clocks_throttle_reasons.hw_thermal_slowdown` flag). Per the 2026-05-12 HANDOFF Q9 decision, every Orionfold card publishes this number.

```python
probe = ThermalProbe()
probe.start()
# ... run a long bench / inference burst
probe.stop()
print(probe.sustained_load_minutes)  # → 2.18
```

`ThermalReading` is the per-sample frozen dataclass — useful when you want the full timeseries for a per-variant chart instead of just the sustained-load floor.

### `QuantReport`

The canonical output. `format` discriminates across formats; GGUF callers populate `variant_files` (path + rel + human-size per variant), `perplexity`, and `tokens_per_sec` dicts keyed by variant name; AWQ / GPTQ callers will populate a single-file shape when those backends land. `notes` is a free-text scratchpad — `dry_run` paths use it for the would-be commands; production runs use it for one-off observations the article will quote.

```python
report.format                  # 'gguf'
report.variants                # ('Q4_K_M', 'Q5_K_M', 'Q6_K', 'Q8_0', 'F16')
report.perplexity['Q8_0']      # 6.137
report.tokens_per_sec['Q4_K_M']  # 31.1
report.sustained_load_minutes  # 2.18
```

### `parse_perplexity_output(text)` + `parse_llama_bench_output(text, metric='tg')`

The two parsing primitives, exposed in case you have llama.cpp output already in hand (e.g., from a logged run). Both return `Optional[float]`.

### Non-GGUF stubs

```python
quantize_awq(...)    # NotImplementedError — see ideas/mtbm-use-cases.md §7 (v0.5 cut)
quantize_gptq(...)
quantize_exl3(...)
quantize_mlx(...)
quantize_nvfp4(...)
```

Five named entry points reserving the v0.5 surface. Each raises `NotImplementedError` with a one-liner roadmap pointer. Callers writing forward-looking pipelines can shape their code today against `quantize_<format>(...)` and pick the format at runtime — the v0.5 cut wires the implementations behind the same signatures.

## Why this surface

Three things to notice. First, every public function takes `paths=LlamaCppPaths()` as an explicit kwarg rather than reading env vars internally; this makes test runs (which pass mock paths) and production runs (which pass `LlamaCppPaths().resolve()`) the same code path. Second, the four measurement axes (perplexity, tg tok/s, pp tok/s, thermal) are *separate* helpers rather than a monolithic `measure_all`. Run only the ones you care about, in any order, with whatever subset of variants makes sense — and let the orchestration script (`scripts/g3_build_first_quant.sh measure` is the canonical one) decide the wall-time budget. Third, the non-GGUF stubs aren't error-stubs in disguise — they're a public API contract. v0.5 will fill them in; today's callers can already write `quantize_dispatch(format, ...)` against the full set.

The module sits next to `fieldkit.publish` because the two are tightly coupled: `publish_quant` reads `QuantReport` directly, and the variant-file paths it reads come straight from `report.variant_files[v]['path']`. Splitting them across modules avoids a circular import (publish doesn't import quant; it duck-types the report) while keeping the production line one `from fieldkit.quant import ...` plus one `from fieldkit.publish import ...` away.

## Samples

- [`scripts/g3_build_first_quant.sh`](https://github.com/manavsehgal/ai-field-notes/blob/main/scripts/g3_build_first_quant.sh) — the canonical end-to-end runner. `quantize` step calls `quantize_gguf`; `measure` step calls all three measurement helpers per variant + a `ThermalProbe`; `publish-dryrun` step assembles the `QuantReport` shape and hands it to `fieldkit.publish.publish_quant(..., dry_run=True)`.
- [`articles/becoming-a-gguf-publisher-on-spark/`](https://ainative.business/field-notes/becoming-a-gguf-publisher-on-spark/) — anchor article. Walks the five-variant production line for `Orionfold/finance-chat-GGUF`, the four measurement axes, the open-book FinanceBench overlay, and the chat-vs-base-model trap that gates V1 picks.
