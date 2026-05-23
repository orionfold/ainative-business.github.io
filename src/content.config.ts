import { defineCollection, z } from 'astro:content';
import { glob } from 'astro/loaders';
import { ARTIFACT_KINDS } from './lib/artifacts';

// Editorial taxonomy — ported up from ai-field-notes during the May 2026
// consolidation. Stage names map to /field-notes/stages/<stage>/ pages and
// drive the colored badge dot on every card. Order matters for nav rendering.
export const STAGES = [
  'foundations',
  'training',
  'fine-tuning',
  'inference',
  'deployment',
  'agentic',
  'observability',
  'dev-tools',
] as const;

// Editorial series — running narrative threads. An article belongs to at
// most one series. "AI Native Platform" is the new series introduced by
// the consolidation; it absorbs the two reframed research papers (ordinals
// 1 and 2) and threads across stages.
export const SERIES = [
  'AI Native Platform',
  'Foundations',
  'Second Brain',
  'LLM Wiki',
  'Machine that Builds Machines',
  'Looking Beyond Spark',
  'Frontier Scout',
] as const;

export const SERIES_SLUGS: Record<(typeof SERIES)[number], string> = {
  'AI Native Platform': 'ai-native-platform',
  'Foundations': 'foundations',
  'Second Brain': 'second-brain',
  'LLM Wiki': 'llm-wiki',
  'Machine that Builds Machines': 'machine-that-builds-machines',
  'Looking Beyond Spark': 'looking-beyond-spark',
  'Frontier Scout': 'frontier-scout',
};

export const SERIES_BY_SLUG: Record<string, (typeof SERIES)[number]> =
  Object.fromEntries(
    Object.entries(SERIES_SLUGS).map(([name, slug]) => [slug, name as (typeof SERIES)[number]]),
  );

const fieldkitModules = ['capabilities', 'nim', 'rag', 'eval', 'training', 'lineage', 'quant', 'publish', 'cli'] as const;
export const FIELDKIT_MODULES = fieldkitModules;

// Articles live at ./articles/<slug>/article.{md,mdx} so the local clone
// of ai-field-notes can be mirrored here without crossing into src/. The
// glob loader collapses the id to the folder slug — URLs become
// /field-notes/<slug>/ rather than /field-notes/<slug>/article/.
const fieldNotes = defineCollection({
  loader: glob({
    pattern: '*/article.{md,mdx}',
    base: './articles',
    generateId: ({ entry }) => entry.split('/')[0],
  }),
  schema: z.object({
    title: z.string(),
    date: z.coerce.date(),
    author: z.string().default('Manav Sehgal'),
    product: z.string().optional(),
    stage: z.enum(STAGES),
    difficulty: z.enum(['beginner', 'intermediate', 'advanced']).optional(),
    time_required: z.string().optional(),
    hardware: z.string().optional(),
    tags: z.array(z.string()).default([]),
    summary: z.string().max(400),
    signature: z.string().optional(),
    status: z.enum(['published', 'upcoming']).default('published'),
    also_stages: z.array(z.enum(STAGES)).default([]),
    series: z.enum(SERIES).optional(),
    fieldkit_modules: z.array(z.enum(fieldkitModules)).optional(),
    // Explicit ordinal override. The two reframed research papers use this
    // to claim №01 and №02 in the AI Native Platform series; everyone else
    // gets a derived ordinal from git first-add timestamps.
    ordinal: z.number().int().optional(),
    // Which /book/ chapter(s) this article grounds with field evidence.
    // Mostly used by "Machine that Builds Machines" articles (default [10]).
    book_chapters: z.array(z.number().int().min(1).max(14)).optional(),
    hf_url: z.string().url().optional(),
  }),
});

// Fieldkit module reference docs at fieldkit/docs/api/<module>.md. Mirrors
// the layout in the source ai-field-notes repo so the sync skill can copy
// without transformation.
const fieldkitDocs = defineCollection({
  loader: glob({
    pattern: '*.md',
    base: './fieldkit/docs/api',
    generateId: ({ entry }) => entry.replace(/\.md$/, ''),
  }),
  schema: z.object({
    module: z.enum(fieldkitModules),
    title: z.string(),
    summary: z.string(),
    order: z.number().int(),
  }),
});

// Structured catalog entries (GGUF quants, LoRA adapters, datasets, etc.).
// Mirrors source ai-field-notes/src/content.config.ts artifacts collection
// byte-faithfully so the sync skill can copy YAML without transformation.
// URL convention is plural-by-kind: /artifacts/quants/, /artifacts/loras/, …
const artifacts = defineCollection({
  loader: glob({ pattern: '**/*.yaml', base: './src/content/artifacts' }),
  schema: z.object({
    slug: z.string(),
    kind: z.enum(ARTIFACT_KINDS),
    class: z.string(),
    base_model: z.string(),
    hf_repo: z.string(),
    variants: z.array(z.string()).default([]),
    recommended_variant: z.string().optional(),
    perplexity: z.record(z.string(), z.number()).optional(),
    spark_tokens_per_sec: z.record(z.string(), z.number()).optional(),
    sustained_load_minutes: z.number().optional(),
    vertical_eval: z.record(z.string(), z.number()).optional(),
    vertical_eval_name: z.string().optional(),
    lineage_run_id: z.string().optional(),
    license: z.object({
      tier: z.string().default('free'),
      commercial_tier: z.string().optional(),
      model: z.string().optional(),
    }),
    article: z.string().optional(),
    civitai_id: z.number().int().optional(),
    download_count: z.number().int().optional(),
    published_at: z.string().optional(),
    // Bench-specific optional fields. Quant manifests leave them undefined;
    // bench manifests with all fields populated fill the detail page; bench
    // manifests with none degrade to a text-only detail page.
    shapes: z
      .array(
        z.object({
          code: z.string(),
          label: z.string(),
          count: z.number().int().positive(),
          scorer: z.enum(['deterministic', 'structural', 'judge']),
          source: z.string(),
        }),
      )
      .optional(),
    modes: z.array(z.enum(['closed', 'retrieval', 'oracle', 'judge'])).optional(),
    results: z.record(z.string(), z.record(z.string(), z.number())).optional(),
    results_provenance: z
      .object({
        model: z.string(),
        article_anchor: z.string().optional(),
      })
      .optional(),
    samples: z
      .array(
        z.object({
          shape: z.string(),
          question: z.string(),
          oracle_context: z.string().optional(),
          gold_label: z.string(),
        }),
      )
      .optional(),
    sources: z
      .array(
        z.object({
          key: z.string(),
          name: z.string(),
          url: z.string().url(),
          blurb: z.string(),
        }),
      )
      .optional(),
    how_to_load: z.string().optional(),
    citation: z.string().optional(),
    // Engagement-pull narrative fields (fieldkit v0.5.x, May 2026). All optional
    // so older manifests still validate. Render templates degrade gracefully
    // when absent. See /NARRATIVE-CONTRACT.md in the source repo.
    positioning: z
      .object({
        headline: z.string(),
        problem: z.string(),
        use_cases: z.array(z.string()).default([]),
        audience: z.string().optional(),
      })
      .optional(),
    stack_origin: z.enum(['unsloth', 'nemo', 'axolotl', 'verl', 'peft']).optional(),
    lane_summary: z.string().optional(),
    known_drift: z
      .array(
        z.object({
          item: z.string(),
          bound: z.string(),
        }),
      )
      .optional(),
    siblings: z
      .array(
        z.object({
          slug: z.string(),
          hf_repo: z.string().optional(),
          hook: z.string(),
        }),
      )
      .optional(),
    // Runnable on-ramp links surfaced as a badge row above-the-fold on every
    // artifact detail page (and as a small inline ▶ Colab affordance on catalog
    // tiles). Spark publishes the notebooks; Mac renders the badges. Both keys
    // optional so a manifest can carry just Colab (Kaggle deferred per source
    // spec §14). Field absent → badge row gracefully no-ops.
    notebooks: z
      .object({
        colab: z.string().url().optional(),
        kaggle: z.string().url().optional(),
      })
      .optional(),
  }),
});

export const collections = { 'field-notes': fieldNotes, fieldkit_docs: fieldkitDocs, artifacts };
