---
module: publish
title: fieldkit.publish
summary: HuggingFace push surface — `ModelCard` (frontmatter + body renderer), `ArtifactManifest` (Phase-2 sync record), `HFHubAdapter` (lazy huggingface_hub wrapper, dry-run by default), `publish_quant` orchestrator. Every Orionfold artifact card carries the same Spark-tested measurement quad (perplexity, tok/s, thermal envelope, optional vertical-eval) — this module is what makes that shape deterministic.
order: 8
---

## What it is

The publishing side of the Orionfold production line. `fieldkit.quant` produces a `QuantReport`; `fieldkit.publish` turns it into a HuggingFace repo with a deterministic model card and a per-artifact YAML manifest the source repo and destination site both read.

Three surfaces. `ModelCard` renders the canonical card shape — frontmatter (license, library_name, base_model, tags, model_creator), a `## Spark-tested` block (perplexity + tok/s + thermal envelope + optional vertical-eval table), a `## Variants` table, an auto-generated `## How to run` body (`huggingface-cli download` + `llama-server` + `llama-cpp-python` snippets templated from the HF repo path), an optional `## Lineage` block (rendered from a `fieldkit.lineage.LineageStore` if provided), a `## Methods` backlink to the anchor article, and an Orionfold LLC footer. `ArtifactManifest` is the frozen dataclass for `src/content/artifacts/<slug>.yaml` — the Phase-2 sync record per `project_artifact_manifests_phase2`; the destination renders catalog pages from `getCollection('artifacts')`. `HFHubAdapter` is a lazy wrapper around `huggingface_hub` — defaults to `dry_run=True` (stages files + logs the would-be calls; no network, no token); flip `dry_run=False` to push via `HfApi().upload_folder(...)`.

The module exists because manual card authoring at MTBM's 3–5-day cadence is the bottleneck. Every quant needs a tags list, a perplexity table, a tok/s number, a thermal envelope note, a lineage backlink — and getting any of those wrong on the customer-facing HF page is a trust hit. `fieldkit.publish` makes the card the deterministic output of the quant+lineage run, not a hand-edit, so the only knobs the operator sets are the ones that genuinely require human judgement (the upstream license, the chat format, the featured variant).

## Public API

```python
from fieldkit.publish import (
    ARTIFACT_KINDS, ArtifactKind, ArtifactManifest,
    HFHubAdapter, HFHubNotAvailable, HFAuthError,
    ModelCard, PublishError, PublishResult,
    publish_quant, write_artifact_manifest,
    ORIONFOLD_BRAND, ORIONFOLD_HF_HANDLE, ORIONFOLD_HF_ORG,
)
```

### `ORIONFOLD_BRAND` + `ORIONFOLD_HF_HANDLE`

```python
ORIONFOLD_BRAND = "Orionfold LLC"
ORIONFOLD_HF_HANDLE = "Orionfold"
```

The brand stamped on every card footer, and the HuggingFace user handle every repo lands under (`Orionfold/<model>-GGUF`, Bartowski-shape). `ORIONFOLD_HF_ORG` is a back-compat alias for `ORIONFOLD_HF_HANDLE` — kept callable for out-of-tree imports, slated for removal in a future cut.

### `ARTIFACT_KINDS`

```python
ARTIFACT_KINDS = (
    "quant", "lora", "adapter", "embed",
    "reranker", "dataset", "space", "bench",
)
```

The manifest `kind` enum. Mirrored by `src/content.config.ts`'s `ARTIFACT_KINDS` so Astro Zod validation and the Python writer stay in lockstep.

### `ModelCard(...)`

Frozen dataclass + `render() → str`. Constructed by `publish_quant` from a `QuantReport`-shaped object plus the resolved license / chat_format / recommended_variant triple. Renders to a single `README.md`-style string.

Key fields:

```python
ModelCard(
    title="finance chat GGUF",
    one_liner="...",
    base_model="AdaptLLM/finance-chat",
    license="llama2",                  # ← HF frontmatter scalar; reflects upstream model's license
    library_name="gguf",
    pipeline_tag="text-generation",
    tags=("gguf", "spark-tested", "orionfold", "base_model:AdaptLLM/finance-chat"),
    quant_format="gguf",
    variants=({"name": "Q4_K_M", "size": "3.8 GB", "recommended": "..."}, ...),
    perplexity={"Q4_K_M": 6.221, "Q8_0": 6.137, ...},
    tokens_per_sec={"Q4_K_M": 31.1, "Q8_0": 8.9, ...},
    sustained_load_minutes=2.18,
    vertical_eval={"Q4_K_M": 0.14, ...},                       # optional 5th column
    vertical_eval_name="FinanceBench (n=50, numeric_match)",
    hf_repo="Orionfold/finance-chat-GGUF",                    # drives default `## How to run` body
    chat_format="llama-2",                                     # → llama_cpp.Llama(chat_format=...)
    recommended_variant="Q5_K_M",                              # featured in default snippets
    llama_cpp_example_prompt="Explain working capital.",       # user-message in the default `llama-cpp-python` snippet; falls back to a neutral placeholder when omitted
    ollama_pull_handle=None,                                   # opt-in override; default body wins otherwise
    transformers_snippet=None,
    lineage_prompt=None,                                       # injected by publish_quant if a LineageStore is supplied
    article_slug="becoming-a-gguf-publisher-on-spark",
    article_title="...",
    model_creator=ORIONFOLD_BRAND,
)
```

`render()` emits sections in canonical order: YAML frontmatter → title + elevator → `## Spark-tested` (omitted if no measurements) → `## Variants` → `## How to run` (auto-rendered defaults when no explicit handle/snippet given; entirely omitted if no defaults templatable) → `## Lineage` (if `lineage_prompt` supplied) → `## Methods` link → footer.

### `ArtifactManifest(...)`

Frozen dataclass for `src/content/artifacts/<slug>.yaml`. Flat-by-design (primitive types + dicts of primitives) so the YAML emitter is hand-rolled stdlib.

```python
m = ArtifactManifest(
    slug="finance-chat-gguf",
    kind="quant",
    artifact_class="gguf",                  # serialized as `class:` in YAML
    base_model="AdaptLLM/finance-chat",
    hf_repo="Orionfold/finance-chat-GGUF",
    variants=("Q4_K_M", "Q5_K_M", "Q6_K", "Q8_0", "F16"),
    perplexity={"Q4_K_M": 6.221, ...},
    spark_tokens_per_sec={"Q4_K_M": 31.09, ...},
    sustained_load_minutes=2.18,
    vertical_eval={"Q4_K_M": 0.14, ...},
    vertical_eval_name="FinanceBench (n=50, numeric_match)",
    recommended_variant="Q5_K_M",           # article-narrative pick; destination pins the "Sweet spot" badge to this variant
    lineage_run_id=None,
    license_tier="free",                    # Orionfold commercial tier (free / pro)
    license_commercial_tier=None,
    model_license="llama2",                 # upstream model license (HF frontmatter shape)
    article="articles/becoming-a-gguf-publisher-on-spark/",
    civitai_id=None,
    download_count=None,
    published_at="2026-05-14T04:46:11Z",
)
print(m.to_yaml())
```

The `license_tier` / `license_commercial_tier` fields live alongside `model_license` under a nested `license:` block in YAML output. Mac destination's Zod schema mirrors this shape.

`recommended_variant` (v0.4.2+) lets the article's narrative pick — the variant the writeup recommends — override the destination's rank-avg picker. Cyber's `Q4_K_M` topped CyberMetric but its worst-in-class perplexity dragged its rank-avg down, so without this field the catalog page would pin `Q5_K_M` as the "Sweet spot" instead. Same value flows into both `ModelCard` (HF README's How-to-run snippets) and `ArtifactManifest` (destination catalog) so the badge and the snippet stay in sync.

### `write_artifact_manifest(manifest, *, artifacts_dir)`

Writes the manifest to `<artifacts_dir>/<slug>.yaml`. Creates the directory if missing. Returns the absolute path of the written file — callers can stage it alongside the article for the next git commit.

### `HFHubAdapter(staging_dir, *, dry_run=True, token=None, org=ORIONFOLD_HF_HANDLE)`

Thin wrapper around `huggingface_hub`. Dry-run by default: lays out the upload set on disk under `staging_dir`, logs the would-be calls. No HF imports required, no token required. Flip `dry_run=False` to push; the lazy import of `huggingface_hub` fires only then.

```python
adapter = HFHubAdapter(staging_dir="/tmp/orionfold-stage/finance-chat", dry_run=True)
adapter.stage_text(card.render(), "README.md")          # stages from a string
adapter.stage_file(gguf_path, "model-Q4_K_M.gguf")      # stages by copying a file
result = adapter.push_folder(repo_name="finance-chat-GGUF")
result.dry_run        # True
result.files_uploaded  # ('README.md', 'model-Q4_K_M.gguf', ...)
result.logged_calls   # the upload_folder kwargs that would have fired
```

Token resolution order: explicit `token=` arg → `HF_TOKEN` env → `HUGGING_FACE_HUB_TOKEN` env → `huggingface_hub`'s cached login. If all four are absent and `dry_run=False`, `HFAuthError` raises before the network call.

`HFHubAdapter.push_folder(*, repo_name, commit_message="Initial Orionfold upload", private=False, repo_type="model")` exposes the three llama-hub kwargs the orchestrator passes through. `commit_message` defaults to the bootstrap value used by every first-push card — override on subsequent updates (`"Polish llama_cpp_example_prompt"`, `"Add Q4_0 variant"`). `private=True` creates a private repo first (or no-ops if the repo already exists at any visibility — `exist_ok=True` is baked in). `repo_type="model"` covers every Orionfold card; flip to `"dataset"` or `"space"` for the rare cases (lineage-store snapshots have shipped as datasets in past sessions).

### `publish_quant(*, quant_report, base_model, repo_name, staging_dir, ...) → PublishResult`

The one-line orchestrator. Reads the duck-typed `quant_report` fields (`.format`, `.variants`, `.perplexity`, `.tokens_per_sec`, `.sustained_load_minutes`, `.variant_files`, `.vertical_eval`, `.vertical_eval_name`, `.model_license`, `.chat_format`, `.recommended_variant`, `.llama_cpp_example_prompt`), builds a `ModelCard`, stages the README + variant files, writes the `ArtifactManifest` (if `artifacts_dir` supplied), and invokes `HFHubAdapter.push_folder()`. Explicit kwargs override duck-typed report attrs.

```python
result = publish_quant(
    quant_report=report,
    base_model="AdaptLLM/finance-chat",
    repo_name="finance-chat-GGUF",
    staging_dir="/tmp/orionfold-stage/finance-chat",
    artifacts_dir="/home/nvidia/ai-field-notes/src/content/artifacts",
    article_slug="becoming-a-gguf-publisher-on-spark",
    article_title="...",
    vertical_eval={"Q4_K_M": 0.14, "Q5_K_M": 0.16, ...},
    vertical_eval_name="FinanceBench (n=50, numeric_match)",
    model_license="llama2",            # critical — never default silently to apache-2.0
    chat_format="llama-2",
    recommended_variant="Q5_K_M",
    llama_cpp_example_prompt="Explain working capital.",  # mirror the article's example user-message
    lineage_store=store,                # optional; injects ## Lineage block
    dry_run=True,                       # flip to False for the actual push
)
result.hf_repo         # 'Orionfold/finance-chat-GGUF'
result.card_path       # Path('/tmp/orionfold-stage/.../README.md')
result.manifest_path   # Path('.../src/content/artifacts/finance-chat-gguf.yaml')
result.hf_url          # None in dry-run; set after live push
```

The `model_license` / `chat_format` / `recommended_variant` kwargs landed in v0.4.x after the `Orionfold/finance-chat-GGUF` dry-run surfaced two card-rendering bugs: a hardcoded `license: apache-2.0` (wrong for the Llama-2 lineage AdaptLLM base) and an empty `## How to run` section (when no ollama handle or transformers snippet was supplied, the section header rendered with no body). Both are now caller-controlled with sane defaults.

`extra_tags=("finance", "evidence-based")` threads additional HF tags into the rendered card's frontmatter `tags:` array (deduplicated against the auto-generated tags like `gguf`, `quantized`, `orionfold`). Use for vertical-specific discoverability — the four shipped Orionfold cards each add their vertical name (`finance`, `legal`, `cyber`, `medical`) plus secondary tags driven by the base model's lineage.

## Why this surface

Three things to notice. First, `HFHubAdapter` defaults to dry-run because the right workflow is dry-run → human review → live push. Library users who want a one-shot live push pass `dry_run=False` explicitly; library users who want the staging artifact for review (the common case during development) get it for free. The `hf-publisher` skill (`/home/nvidia/.claude/skills/hf-publisher/`) wraps this workflow as a triggered Claude Code surface.

Second, `publish_quant` duck-types its report rather than importing `fieldkit.quant.QuantReport` directly. This avoids a circular import (quant doesn't depend on publish; publish doesn't depend on quant) and lets non-quant callers — a LoRA pipeline, an embedding pipeline — supply their own report-shaped objects without subclassing.

Third, `ArtifactManifest` is structurally distinct from `ModelCard` even though they overlap. The card is for HuggingFace; the manifest is for the destination Astro catalog. Both encode the same artifact, but the *consumers* are different and have different schemas. Keeping them separate dataclasses lets each evolve independently — and lets `write_artifact_manifest` write the manifest even when the HF push is dry-run, which is what the source repo commits look like during article-only iterations.

## Samples

- [`scripts/g3_build_first_quant.sh`](https://github.com/manavsehgal/ai-field-notes/blob/main/scripts/g3_build_first_quant.sh) — `publish-dryrun` step assembles a `QuantReport`-shaped `SimpleNamespace` from the measurement JSON and calls `publish_quant(..., dry_run=True)`.
- [`scripts/g3_push_first_quant.py`](https://github.com/manavsehgal/ai-field-notes/blob/main/scripts/g3_push_first_quant.py) — the live-push one-shot. Reuses the existing dry-run stage; calls `HFHubAdapter(staging_dir=..., dry_run=False).push_folder()` directly so the 32 GB of GGUF bytes don't get re-staged.
- [`articles/becoming-a-gguf-publisher-on-spark/`](https://ainative.business/field-notes/becoming-a-gguf-publisher-on-spark/) — anchor article. Walks the v0.4.x publish surface end-to-end against `Orionfold/finance-chat-GGUF` and narrates the two bugs that v0.4.0 fixed before tagging.
