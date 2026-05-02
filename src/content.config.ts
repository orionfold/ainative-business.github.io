import { defineCollection, z } from 'astro:content';
import { glob } from 'astro/loaders';

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
  'Autoresearch',
  'Looking Beyond Spark',
  'Frontier Scout',
] as const;

export const SERIES_SLUGS: Record<(typeof SERIES)[number], string> = {
  'AI Native Platform': 'ai-native-platform',
  'Foundations': 'foundations',
  'Second Brain': 'second-brain',
  'LLM Wiki': 'llm-wiki',
  'Autoresearch': 'autoresearch',
  'Looking Beyond Spark': 'looking-beyond-spark',
  'Frontier Scout': 'frontier-scout',
};

export const SERIES_BY_SLUG: Record<string, (typeof SERIES)[number]> =
  Object.fromEntries(
    Object.entries(SERIES_SLUGS).map(([name, slug]) => [slug, name as (typeof SERIES)[number]]),
  );

const fieldkitModules = ['capabilities', 'nim', 'rag', 'eval', 'cli'] as const;
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

export const collections = { 'field-notes': fieldNotes, fieldkit_docs: fieldkitDocs };
