---
name: nvidia-learn-stats
description: Compute and refresh project-level statistics for the nvidia-learn repo — article count, total word count, total lines of code across evidence/ and src/, NVIDIA models and products covered, per-stage distribution, and representative latency/throughput/accuracy metrics mined from article prose. Writes a compact JSON file at src/data/field-notes/project-stats.json that the Astro home page imports to render a visual infographic. Use this skill whenever the user asks for "project stats", "blog stats", "how many articles", "refresh the stats", "update the infographic on the home page", or after publishing a new article (stats should be refreshed so the home page numbers stay current). Prefer this skill over ad-hoc counting because the numbers show up in a user-facing infographic and drift silently otherwise.
---

# nvidia-learn project stats

Produces `src/data/field-notes/project-stats.json` consumed by the home page's "at-a-glance" infographic. The JSON is the single source of truth — the Astro component just renders it.

## What to do

Run the bundled script from the repo root:

```bash
cd /home/nvidia/ainative-business.github.io
python3 ~/.claude/skills/nvidia-learn-stats/scripts/compute_stats.py
```

It walks `articles/*/article.md` for prose stats, counts code under `articles/*/evidence/` (excluding `/repo-snapshot/` vendored upstream snapshots) and `fieldkit/{src,tests,samples,scripts}/` (excluding the gitignored `_webui/` baked Arena bundle — a build artifact, not source), emits `src/data/field-notes/project-stats.json`, and prints a short human-readable summary so you can eyeball the numbers before committing. The Astro site under `src/` is infrastructure, not the deliverable, and is intentionally excluded from `total_loc`.

If the schema or detection lists need to change (new product, new metric pattern), edit `scripts/compute_stats.py` — the script is the schema.

## Output shape (stable contract with the home page)

```json
{
  "generated_at": "2026-04-23T08:00:00Z",
  "articles": { "total": 10, "published": 10, "drafts": 2 },
  "words": { "total": 84000, "mean_per_article": 8400, "longest": { "slug": "...", "words": 12000 } },
  "code": { "evidence_loc": 13839, "fieldkit_loc": 6021, "vendored_loc": 344711, "total_loc": 19860, "by_language": { "python": 19832, "shell": 13, "sql": 15, ... } },
  "stages": { "foundations": 3, "inference": 6, "agentic": 1, "training": 0, "observability": 0, "dev-tools": 0 },
  "models": [ { "id": "llama-3.1-8b-instruct", "label": "Llama 3.1 8B Instruct", "articles": 5 }, ... ],
  "products": [ { "id": "nim", "label": "NVIDIA NIM", "articles": 8 }, ... ],
  "metrics": {
    "latency": [ { "label": "query embed", "value": "40ms", "article_slug": "naive-rag-on-spark" }, ... ],
    "throughput": [ ... ],
    "accuracy": [ ... ]
  }
}
```

The home page component (`src/components/ProjectStats.astro`) is tolerant of missing keys — if a new category appears in the JSON it won't break the render, and empty categories are simply hidden.

## When to invoke

- User says "update the project stats" / "refresh the infographic" / "how many articles / how many words"
- After `tech-writer` publishes a new article — stats drift the moment a new article lands, so run this before committing the new article
- After `fieldkit-curator` cuts a release or `fieldkit/src/` gains modules (LOC shifts)
- After a Frontier-Scout article promotes (vendored snapshot lands; `vendored_loc` grows but `total_loc` should not, which is a useful sanity check)

## Why a pre-computed JSON, not live computation

Astro could compute these at build time, but:
1. The git-derived publish ordinal (see `src/lib/article-order.mjs`) already gave us one precedent where computing at render time led to hidden drift across pages. A single JSON file committed to the repo makes the numbers visible in PR diffs.
2. The detection lists (model IDs, product names, metric regexes) are maintenance code — keeping them in a Python script rather than scattered across Astro components keeps the home page lean.
3. `git log src/data/field-notes/project-stats.json` becomes a low-key timeline of the repo's maturation.

## Detection scope (edit the script to extend)

**Models** — regex against article prose and `product:` frontmatter. The list is maintained in `MODELS` inside `scripts/compute_stats.py`; when an article pulls in a new base, add it there or it will be absent from the home-page infographic despite appearing prominently in prose. Current coverage:
- NVIDIA-served: `llama-3.1-8b-instruct`, `llama-3.3-70b-instruct`, `llama-3.1-nemotron-nano-*`, `nemotron-super-49b`
- Embedding / reranker: `nvidia/nv-embedqa-e5-v5`, `nemotron-embed-1b-v2`, `nemotron-reranker` / `llama-3.2-nv-rerankqa-1b`
- Non-NVIDIA bases (fine-tuning articles): `Qwen2.5-3B-Instruct`, `Qwen2.5-7B-Instruct`

**When to extend `MODELS`:** any time a new article's `product:` frontmatter names a model family (Mistral, DeepSeek, Phi, etc.) that the regex list doesn't already cover, add an entry before committing the article. The script re-runs cheaply and the home-page counter is the visible consequence of a miss.

**Products** — normalized to a canonical `id` + display `label`:
- NIM, NeMo Retriever, NeMo Guardrails, NeMo, NemoClaw, OpenClaw, TensorRT-LLM, Triton, DGX Spark, pgvector (non-NVIDIA but core substrate)

**Metrics** — regex for `\d+\s?ms`, `\d+\s?tok(ens)?/s`, `recall@\d+ = ?\d+%?`, with a ±40-char context window so the label is meaningful. Dedupes by (value, article) to avoid counting the same number three times.

**Stages** — read from frontmatter `stage:` field; schema values are `foundations`, `inference`, `training`, `agentic`, `observability`, `dev-tools`.

## Edge cases

- **Drafts**: `articles/_drafts/` is excluded from the published count but listed as `articles.drafts`. Check `_drafts/` exists before counting.
- **Transcripts**: each article has a `transcript.md` — **not counted** in the word total (session logs, not published prose).
- **Evidence LOC**: counted across common code extensions (`.py`, `.sh`, `.sql`, `.js`, `.ts`, `.json`, `.yaml`, `.toml`). Skip binary files, logs (`.log`), screenshots, and `node_modules/`.
- **`src/` LOC**: skip `src/data/field-notes/project-stats.json` itself (so the stat doesn't count its own weight) and `src/content/articles/` symlinks.

## Post-run

After writing the JSON:
1. Print the summary (top 5 models, top 5 products, articles count, LOC, word count) so the user can sanity-check.
2. Do NOT auto-commit. Let the user review and stage the file themselves — the home-page diff and the JSON diff should land in the same commit.
