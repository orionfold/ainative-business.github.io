# Artifact manifests — per-kind schema contract

This directory holds the structured catalog manifests for everything that
publishes alongside a field note. Files are loaded by Astro as a content
collection via the `artifacts` collection in `src/content.config.ts`. Each
manifest is a single YAML file at `<slug>.yaml` (no subdirectories).

**URL convention:** plural-by-kind. A manifest with `kind: quant` and
`slug: finance-chat-gguf` is rendered at `/artifacts/quants/finance-chat-gguf/`.
The plural segments are: `quants`, `loras`, `adapters`, `datasets`, `benches`.
Driven by `kindToSegment()` in `src/lib/artifacts.ts`. (The 2026-05-22
reduction dropped `embed`/`reranker`/`space` from `ARTIFACT_KINDS` — those
kinds are not pursued.)

**Schema source of truth:** `src/content.config.ts`. The list below is a
human-readable summary; if the two ever drift, the Zod schema wins.

---

## Common fields (every kind)

| Field | Required | Type | Notes |
|---|---|---|---|
| `slug` | ✓ | string | URL slug; should match the filename without `.yaml` |
| `kind` | ✓ | enum | One of `quant`, `lora`, `adapter`, `dataset`, `bench` |
| `positioning.headline` |  | string | One-line elevator (added v0.5.x; required by [NARRATIVE-CONTRACT.md](/Volumes/home/ai-field-notes/NARRATIVE-CONTRACT.md)) |
| `positioning.problem` |  | string | Customer-problem framing — sets "What this model does" body |
| `positioning.use_cases` |  | string[] | Use-case bullets |
| `positioning.audience` |  | string | Who picks this artifact |
| `stack_origin` |  | enum | `unsloth` \| `nemo` \| `axolotl` \| `verl` \| `peft` — drives lane badge color |
| `lane_summary` |  | string | "Choosing this lane" block copy (when multi-stack siblings exist) |
| `known_drift[]` |  | array of `{ item, bound }` | Bounded limitations — every entry must include a `bound` |
| `siblings[]` |  | array of `{ slug, hook, hf_repo? }` | Cross-link family — required from card #2 onward |
| `class` | ✓ | string | Editorial subdomain — surfaced in card meta strip and `<h1>` chip |
| `base_model` | ✓ | string | The model the artifact derives from; `"n/a"` for benches and datasets |
| `hf_repo` | ✓ | string | `org/repo` — drives HF link CTA and `/datasets/` URL prefix for benches/datasets |
| `variants` |  | string[] | Quant variant ladder (`Q2_K`, `Q4_K_M`, etc.). Empty for non-quants |
| `license.tier` | ✓ | string | `free` \| commercial tier label |
| `license.model` |  | string | The actual license name (e.g., `cc-by-4.0`) |
| `article` |  | string | Path to the paired field-note: `articles/<slug>/` |
| `published_at` |  | ISO datetime | Drives card date label |

---

## `kind: quant`

GGUF / AWQ / EXL3 / MLX / NVFP4 quantizations. Rendered by `QuantCard.astro`
(catalog) and `src/pages/artifacts/quants/[slug]/index.astro` (detail).

| Field | Required | Type | Surfaced by |
|---|---|---|---|
| `variants` | ✓ | string[] | The full variant ladder including the unquantized reference (e.g., `F16`) |
| `recommended_variant` |  | string | Manifest-level override for the sweet-spot picker; otherwise computed by rank-avg |
| `perplexity` |  | record(variant → number) | Quality axis — lower is better; drives heatmap column on detail |
| `spark_tokens_per_sec` |  | record(variant → number) | Throughput axis — higher is better |
| `vertical_eval` |  | record(variant → number) | Domain-fitness axis — higher is better |
| `vertical_eval_name` |  | string | Bench name for the table caption |
| `sustained_load_minutes` |  | number | Thermal envelope; rendered as a single big number on detail |
| `lineage_run_id` |  | string | Optional `fieldkit.lineage` run id |

Worked example: `finance-chat-gguf.yaml`, `ii-medical-8b-gguf.yaml`,
`saul-7b-instruct-v1-gguf.yaml`, `securityllm-gguf.yaml`.

---

## `kind: bench`

Open benchmarks for vertical-finetune evaluation. Rendered by
`BenchCard.astro` (catalog) and `src/pages/artifacts/benches/[slug]/index.astro`
(detail). All bench-specific fields are **optional** — a manifest with none
of them renders a text-only detail page with just masthead + load + citation.

| Field | Required | Type | Surfaced by |
|---|---|---|---|
| `shapes` |  | array of `{ code, label, count, scorer, source }` | Drives `BenchSignature` viz (catalog compact + detail hero) and `BenchBracketTable` row ordering |
| `shapes[].scorer` | (with `shapes`) | enum | One of `deterministic`, `structural`, `judge` — color-codes the signature segment |
| `shapes[].source` | (with `shapes`) | string | Source key used for `BenchSources` aggregation; should match a `sources[].key` |
| `modes` |  | string[] | Evaluation modes: `closed`, `retrieval`, `oracle`, `judge`. Drives column order in the bracket table |
| `results` |  | record(shape-or-overall → record(mode → number)) | Per-shape × per-mode scores. Drives `BenchBracketTable` and `BenchBracketHeadline` |
| `results_provenance` |  | `{ model, article_anchor? }` | Bracket-table caption: "Measured on …" |
| `samples` |  | array of `{ shape, question, oracle_context?, gold_label }` | One row per shape; drives `BenchSampleRow` gallery |
| `sources` |  | array of `{ key, name, url, blurb }` | Drives `BenchSources` provenance breakdown |
| `how_to_load` |  | string | Multi-line code snippet; defaults to `from datasets import load_dataset; …` if omitted |
| `citation` |  | string | BibTeX block; rendered as a `<pre>` on the detail page |

Worked example: `patent-strategist-bench-v0.1.yaml`.

### Authoring tips for benches

- **Picking sample rows.** One representative row per shape is the right
  trade-off between credibility and YAML size. Truncate `oracle_context` and
  long free-text `gold_label` values to ~250–400 chars (the `<details>`
  collapse handles overflow on the detail page).
- **Picking the headline shape.** `BenchBracketHeadline` and the
  `BenchBracketTable` highlight the deterministic shape with the largest
  closed→oracle span. If that's not the editorial headline you want,
  reorder `shapes` or refine `scorer` tiers.
- **Sources order matters.** Sources in `sources[]` render in declaration
  order on the detail page; the source-provenance stacked bar respects this
  order too. List the largest-contribution source first for a cleaner visual.
- **Scaffolding a new manifest.** Use
  `.claude/skills/sync-field-notes/scripts/scaffold_bench_manifest.py` to
  generate a populated skeleton from an HF dataset slug. Editorial fields
  (shape labels, results, blurbs) are left as `# TODO` placeholders.

---

## `kind: lora`

LoRA fine-tunes — the trained adapter weights (typically BF16/FP16) that
sit above a base model. Rendered by `LoRACard.astro` (catalog) and
`src/pages/artifacts/loras/[slug]/index.astro` (detail). Shipped 2026-05-22
with the patent-strategist v3 bakeoff (`patent-strategist-v3-nemo`,
`patent-strategist-v3-unsloth`).

Required fields beyond the common set: `positioning.{headline,problem}`,
`stack_origin`, `known_drift[]`. The corresponding GGUF re-pack (when one
exists) lives as a separate `kind: quant` manifest with `-gguf` suffix.

The detail page renders the full narrative arc: hero LoRA signature SVG →
"What this model does" → "Evaluated on Spark" (vertical_eval heatmap) →
"Choosing this lane" (when stack_origin + sibling lanes share base_model)
→ "How to use" (PEFT snippet) → "Methods" (article wire-back) → "Known
drift" (bounded entries) → "Other Orionfold variants" (siblings).

Worked example: `patent-strategist-v3-nemo.yaml`, `patent-strategist-v3-unsloth.yaml`.

## `kind: adapter`

Prefix, prompt, and IA³ adapters for specialized inference. Render path
exists at `src/pages/artifacts/adapters/[slug]/index.astro` but no
manifests have shipped yet. Schema mirrors `kind: lora` — use the same
positioning / stack_origin / known_drift fields.

## `kind: dataset`

Curated and synthesized training/eval datasets. Render path exists at
`src/pages/artifacts/datasets/[slug]/index.astro` but no manifests have
shipped yet. Reuses the `shapes`, `samples`, `sources`, `how_to_load`,
`citation` fields from the bench schema for shape composition and load
snippets. `kind: bench` and `kind: dataset` differ in intent: a bench has
scored results; a dataset is data without scores.

---

## Source-side authoring

Manifests are authored in the sibling `ai-field-notes` source repo (under
its own `src/content/artifacts/`) and copied here by the
`sync-field-notes` skill on Mac. **Don't author manifests directly in this
repo** — the next sync will overwrite them. The source repo's
`mirrors/destination-overrides.md` points back to this README so source-side
authors know what fields to populate.

The catalog footer (`**Catalog page:** …`) that appears at the tail of
articles with a paired quant manifest is a destination-side override per
`mirrors/destination-overrides.md` — Mac CC appends it on every sync; Spark
CC never writes it. See `chrome_footers.py` in the sync skill for the
boundary-owning code.
