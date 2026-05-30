# fieldkit

> Verified-on-Spark patterns lifted from the [ai-field-notes](https://ainative.business/field-notes/) blog into one importable Python package.

Every essay in `ai-field-notes` ends with `evidence/` — a folder of working code that produced the article's numbers. After 30+ articles the same patterns kept reappearing: the same NIM client wrapper, the same chunk-embed-store dance, the same bench harness, the same verifier-loop math. `fieldkit` is what those `evidence/` folders look like once the boilerplate is lifted into a real package.

The blog stays the long-form rationale. `fieldkit` is the `pip install`-able surface so you can reproduce — and extend — the work without re-pasting 80 lines of NIM-client setup per article.

## Install

```bash
pip install fieldkit
```

For the bleeding edge between releases, install from the git tag instead:

```bash
pip install "git+https://github.com/manavsehgal/ai-field-notes.git@fieldkit/v0.2.0#subdirectory=fieldkit"
```

## Quickstart

```python
from fieldkit.nim import NIMClient

client = NIMClient(base_url="http://localhost:8000/v1", model="meta/llama-3.1-8b-instruct")
print(client.chat([{"role": "user", "content": "Hello, Spark."}]))
```

## What's in v0.2.0

| Module | Purpose | Source articles |
|---|---|---|
| `fieldkit.capabilities` | Typed Python facade over `spark-capabilities.json` — KV cache math, weight bytes, inference envelope. | `kv-cache-arithmetic-at-inference`, `gpu-sizing-math-for-fine-tuning` |
| `fieldkit.nim` | OpenAI-compatible NIM client wrapper with retry, chunking, and the 8192-token context guard. | `nim-first-inference-dgx-spark` and friends |
| `fieldkit.rag` | `Pipeline(embed_url, rerank_url, pgvector_dsn, generator)` — ingest → retrieve → rerank → fuse. | `naive-rag-on-spark` and friends |
| `fieldkit.eval` | `Bench`, `Judge`, `Trajectory` — plus v0.2's `AssertionGrader`, `PassAtK`, `AgentRun`, `MatchedBaseComparison`. | every article with a `bench.py` or `benchmark.py`, plus `clawgym-on-spark`, `autoresearchbench-on-spark`, `pass-at-k-after-the-seventh-patch` |
| `fieldkit.training` *(new in v0.2)* | `LoraReferenceSnapshot` (sidesteps peft 0.19's offloader bug), `WeightDeltaTracker` — for any RL or SFT loop. Lazy `torch` import; pure-inference envs don't pay. | `clawgym-on-spark-grpo` |
| `fieldkit.cli` | `fieldkit bench rag`, `fieldkit feasibility <id>`, `fieldkit envelope <size>`. | discoverability |

### What v0.2 adds

- **`fieldkit.training`** — new module. `LoraReferenceSnapshot` is a CPU-resident snapshot of a peft adapter's LoRA tensors plus a context manager that swaps the snapshot in for one no-grad forward pass and restores trainable weights on exit. Solves a real peft 0.19 bug: `model.load_adapter(adapter_name="reference", is_trainable=False)` crashes with `KeyError` under `device_map="auto"` whenever the GPU has anything else resident — peft's offload-detection over-triggers on Spark unified memory. `WeightDeltaTracker` is a pre/post snapshot of trainable params with L2 + max|Δ| reporting — sanity-check that any fine-tuning step actually moved weights.
- **`fieldkit.eval.AssertionGrader`** — pure-function grader over five file-system assertion primitives (`file_exists`, `file_not_exists`, `file_contents_contain`, `file_contents_match_regex`, `file_unchanged`). Lifted from `clawgym-on-spark`'s deterministic grader; no LLM, no fuzzy matching.
- **`fieldkit.eval.PassAtK` + `pass_at_k_estimator`** — verifier-loop with the Chen 2021 unbiased pass@k estimator (lower variance than the naive `1 - (1-p)^k` for finite n).
- **`fieldkit.eval.AgentRun` + `TurnDetail` + `summarize_agent_runs`** — per-question agent-bench schema with overrideable field-name path tuples for non-AutoResearchBench layouts.
- **`fieldkit.eval.MatchedBaseComparison` + `GroupStats`** — two-rollout B−A driver with per-group and per-assertion-kind delta and a markdown `.report()`. Reusable for any LoRA / adapter ablation, fine-tuned-vs-base, or system-prompt-A-vs-B comparison.

**Deferred to v0.3+:** `fieldkit.agents` (Persona / WorkspaceSeed / SynthTask / TaskAuthor / Sandbox / RolloutDriver / Trajectory + TurnRecord — 7 symbols), `fieldkit.inference.VLLMClient`, and `replay_messages_from_trajectory`. Each needs a second consuming article before its public API locks.

## Hardware

Every code path is verified on a DGX Spark (GB10, 128 GB unified memory, NIM 8B + embed NIM + pgvector co-resident). `fieldkit.training`'s torch + safetensors imports are lazy, so the package costs nothing on inference-only boxes — install `torch` and `safetensors` yourself in the training environment when you need the training primitives. NeMo / Triton / pytorch-base containers ship them; pure-inference envs don't.

Portability to non-Spark CUDA 12.x boxes lands when there's demand.

## License

Apache-2.0. See [`LICENSE`](https://github.com/manavsehgal/ai-field-notes/blob/main/fieldkit/LICENSE).

## Links

- **Blog:** https://ainative.business/field-notes/
- **Docs:** https://ainative.business/fieldkit/
- **Source:** https://github.com/manavsehgal/ai-field-notes/tree/main/fieldkit
- **Changelog:** [`CHANGELOG.md`](https://github.com/manavsehgal/ai-field-notes/blob/main/fieldkit/CHANGELOG.md)
