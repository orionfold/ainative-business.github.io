<!-- Product-launch article contract — Last updated: 2026-05-29 -->

> **Monorepo note (2026-06-02):** this contract was authored under the old
> two-repo Spark→Mac model; "destination / Mac repo" now just means the
> rendering side of *this* monorepo (Spark owns both authoring and rendering
> since the 2026-05-29 cutover). The schema + rendering-ownership contract below
> still applies verbatim — only the "sync / reverse-sync" ceremony is moot.

# Product articles — a new content type

> This document is the contract introducing a new content type — the
> **product-launch article** — and specifying the rendering it requires.
> Authoring (content, schema, this spec) and rendering (layouts, components, URL
> family) now live in one repo.
>
> Authored 2026-05-29. First product article: **Orionfold Arena**
> (`products/orionfold-arena/`).

## Why a separate type

The blog has, until now, had one editorial form: the **deep-dive essay**
(`articles/<slug>/article.md`, authored by the `tech-writer` skill). A deep-dive
*teaches a concept* and uses the work as evidence.

A **product-launch article** is a different genre with a different job: it
*introduces a shippable product* the reader can run, shows what it took to build
(a build-metrics infographic mined from primary sources), tours its features
(one screenshot + one benefit per surface), and makes the case for the
agentic-coding workflow that produced it. It reads for two audiences at once —
an AI-research reader (what the product unlocks) and a Spark operator (what each
feature does).

Because the form, the layout, and the reader intent differ, product articles
get their **own content collection** rather than overloading `articles/` with a
`kind` flag. Keeping them separate means the destination can give them a launch
layout (hero + infographic + feature gallery) without conditionals smeared
through the article reading layout, and they get their own `/products/` URL
family and index.

These are authored by the **`product-writer`** skill (sibling to `tech-writer`),
which lives in `.claude/skills/product-writer/` on the Spark source side.

## Content location (Spark-authoritative)

```
products/
└── <slug>/
    ├── product.md        # frontmatter + launch body (the essay)
    ├── screenshots/      # NN-feature.png — the feature tour, numbered in tour order (AUTHOR copy)
    └── assets/           # build-metrics.json (mined), diagrams, snippets

public/
└── products/
    └── <slug>/
        └── screenshots/  # SERVED copy — `cp` of the author screenshots above; the page
                          # renders from here. Both copies are git-tracked (dual-located).
```

Slugs are kebab-case, the product's short name (e.g. `orionfold-arena`). Spark
owns everything under `products/**` as editorial content, exactly as it owns
`articles/**`. **Screenshots are dual-located:** the page is served from
`public/products/<slug>/`, so the FeatureGallery (`/products/<slug>/<path>`) and
the inline `![](screenshots/…)` images both resolve to the *public* copy. After
every `tour` capture, `cp products/<slug>/screenshots/*.png
public/products/<slug>/screenshots/` and commit both — a shot that lives only in
the author dir is a broken image at runtime. `verify_product_article.sh` hard-
FAILs on a referenced shot missing from public/.

## Proposed `products` collection (for `src/content.config.ts`)

The destination should add a second collection alongside `articles`. Suggested
definition (mirrors the `articles` glob-loader pattern so URLs collapse to
`/products/<slug>/`):

```ts
const products = defineCollection({
  loader: glob({
    pattern: '*/product.md',
    base: './products',
    generateId: ({ entry }) => entry.split('/')[0],
  }),
  schema: z.object({
    title: z.string(),
    date: z.coerce.date(),
    author: z.string().default('Manav Sehgal'),
    product_name: z.string(),
    tagline: z.string().max(120),
    summary: z.string().max(300),
    hardware: z.string().default('NVIDIA DGX Spark'),
    status: z.enum(['published', 'upcoming']).default('published'),
    series: z.enum(SERIES).optional(),          // reuse the existing SERIES enum (e.g. 'Cockpit')
    tags: z.array(z.string()),
    signature: z.string().optional(),           // card-thumbnail SVG under src/components/svg/
    // Hero CTAs — rendered by ProductLayout in this order. Set only the ones
    // that point at something real; a CTA that 404s or misleads is worse than
    // its absence.
    product_url: z.string().optional(),   // → "Try the live preview →" — a HOSTED/SIMULATED demo
                                          //   (e.g. Arena's /arena/demo/ record→replay). Do NOT
                                          //   set it to an artifact card or docs page — that
                                          //   renders a "live preview" button that shows no demo.
    download_url: z.string().optional(),  // → "Download ↓" — a package/registry (e.g. PyPI). Primary
                                          //   button when there's no product_url; ghost beside one.
                                          //   Use for pip-distributed products (no hosted demo).
    repo_url: z.string().optional(),      // → "View source" — a code host. Omit when leading with
                                          //   Download instead of source.
    fieldkit_modules: z.array(z.enum(FIELDKIT_MODULES)).default([]),

    // The build-metrics block — the infographic's data source. Every figure
    // here is mined by scripts/mine_build_metrics.py from primary sources
    // (session transcripts, git, source tree), never estimated.
    build: z.object({
      window: z.string(),                       // human phrasing, e.g. "one day (~15 hours)"
      wall_clock_hours: z.number(),
      sessions: z.number().int(),
      assistant_turns: z.number().int(),
      tokens_processed: z.number().int(),       // all API-processed tokens (incl. cache reads)
      tokens_generated: z.number().int(),       // output tokens
      cache_read_tokens: z.number().int(),
      lines_of_code: z.number().int(),          // authored source only (bundles excluded)
      test_cases: z.number().int(),
      feature_count: z.number().int(),
      models: z.array(z.string()),              // build models, honest mix
      daily_driver: z.string().optional(),      // current model, if newer than the build model
      harness: z.string().default('Claude Code'),
    }),

    // The feature tour — one entry per surface, drives the operator gallery.
    features: z.array(z.object({
      name: z.string(),
      benefit: z.string(),
      screenshot: z.string(),                   // path relative to the product folder
    })).default([]),
  }),
});
```

`build` and `features` are what make this a product article rather than a
deep-dive. For a `status: published` product article both should be populated;
`upcoming` placeholders may leave `features` empty and the `build` numbers at
zero.

## Rendering the destination owns

Layouts, components, styles, and top-level URL families are owned by the site's
rendering side. It owns the following for this type:

1. **`/products/` URL family** — an index page at `/products/` and detail pages
   at `/products/<slug>/`. Same precedent as the forthcoming `/artifacts/**`
   catalog family: Spark provides the data, Mac owns the page chrome.

2. **A launch layout** (e.g. `ProductLayout.astro`) distinct from
   `FieldNotesLayout`. The reading-layout chrome (TOC, arc nav, reader settings)
   is wrong for a launch piece; a product page wants a hero (product_name +
   tagline), the infographic, the feature gallery, then the body prose.

3. **The build-metrics infographic component** — renders the `build:` block.
   This is the analogue of the home-page "At a glance" infographic and should
   live in the same component family. At a glance it should surface:
   - the headline trio **time · lines of code · tests** (the "production tool,
     one day" proof);
   - the agentic-effort row **sessions · turns · tokens generated · cache
     ratio** (cache_read_tokens / tokens_processed — for Arena, 98%);
   - the credits row **built-with models + harness**, and `daily_driver` if set.
   Every number traces to the frontmatter; the component should not compute or
   invent figures, only present them.

4. **The feature-tour gallery** — renders the `features:` array as a
   screenshot-with-benefit-caption sequence. The same array is also walked in
   prose in the body; the gallery is the scannable operator view.

5. **A product card** for the `/products/` index (and any cross-surface
   placement), using `product_name` + `tagline` + `signature` thumbnail. May
   reuse/extend `ArticleCard` or be its own component — Mac's call.

6. **Series cross-linking.** Product articles may set `series` (e.g. `Cockpit`).
   If a product belongs to a series that also has deep-dive articles, the series
   page should be able to list both forms. How that's surfaced is the
   destination's design decision; the data supports it via the shared `SERIES`
   enum.

## Relationship to existing surfaces

- **`articles/` deep-dives** stay exactly as they are. A product may have *both*
  a launch article here and a deep-dive in `articles/` (e.g. a "how the cockpit
  works under the hood" piece); they cross-link, they don't merge.
- **The Cockpit series** already exists in the `SERIES` enum (added 2026-05-28
  for `spark-arena-v1`). Orionfold Arena's launch article is the natural first
  `products/` entry and would carry `series: Cockpit`.
- **Artifacts** (`src/content/artifacts/<slug>.yaml`) are model/dataset
  manifests — a different thing again. A product article describes an
  *application*; an artifact manifest describes a *published model*. No overlap.

## Stats and indices

If the home "At a glance" infographic should also count product articles, that's
a decision to make here — the `nvidia-learn-stats` pipeline currently scans
`articles/**` only. The `product-writer` skill's `publish` mode checks whether
`src/data/field-notes/project-stats.json` has a products bucket and defers to this
document rather than assuming one. If we want products folded into the totals,
extend `compute_stats.py` and note it here.

## Rendering wiring

Product articles use the same content pipeline as `articles/**`. No special
handling is needed beyond wiring the `products` collection + layout once. The
`/products/**` URL family is rendered by the site build; record any rendering
change here so the schema and the local-Astro-dev expectations stay in sync.
