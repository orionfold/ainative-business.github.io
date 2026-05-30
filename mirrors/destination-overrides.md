# Destination-owned paths (Mac-authoritative — do not clobber from Spark)

> **This file is mirrored from the Mac destination repo.** Spark CC reads it before touching
> root-level paths or introducing new top-level Astro pages, to avoid stomping on
> destination-owned IA.
>
> Mac CC's `sync-field-notes` skill is responsible for keeping this file accurate. When Mac
> adds a new top-level page or override, Mac CC opens a PR back to source updating only this
> file (PR title prefix: `mirror: destination-overrides update — <date> — <summary>`).
>
> **Last reverse-sync: 2026-05-16.**

## Top-level pages (Mac-authoritative)

These pages live in the Mac destination repo only. Spark CC never adds files under these globs.

- `/book/**` — Ch10–11 MTBM thesis + all book chapters. Mac CC owns end-to-end.
- `/pricing/**` — commercial license tiers for G-cluster artifacts (G1 embedder licenses, G3/G4 paid-tier quants, G6 dataset commercial tier, G8 adapter licenses, G9 LoRA commissions). Mac CC owns.
- `/about/**` — marketing about page; biographical chrome only (articles themselves live on Spark).
- `/` (root landing — `src/pages/index.astro`) — marketing hero. Spark's homepage at `:4321/` is a dev preview; production landing on `ainative.business` is Mac-rendered.
- `/projects/**` — marketing projects page (`src/pages/projects.astro`).
- `/privacy/**`, `/terms/**` — legal pages.
- `/bookmarks/**` — reader bookmarks surface (paired with the explainers feature).
- `/glossary/**` — glossary surface (consumes `src/lib/field-notes/article-glossary.mjs`).
- `/docs/**` — product documentation subsite (synced separately from `ainative` product via `apply-product-docs` skill, not from `ai-field-notes`).
- `/confirmed` (`src/pages/confirmed.astro`) — newsletter double-opt-in landing.
- `/feed.xml`, `/feed.json`, `/llms.txt`, `/llms-full.txt` — Mac-managed feeds/discovery endpoints.

## Forthcoming top-level pages (Phase 2; chrome owned by Mac, data from Spark manifests)

These will appear as `fieldkit v0.4` ships artifact-publishing modules. Mac owns page chrome; data comes from `src/content/artifacts/` on Spark.

- `/artifacts/quants/` — GGUF / AWQ / EXL3 / MLX / NVFP4 quant catalog (G3 + G4).
- `/artifacts/loras/` — Civitai-shape image/video LoRAs (G9).
- `/artifacts/adapters/` — LoRA/DoRA/IA3 adapter publisher catalog (G8).
- `/artifacts/embeds/` — niche embedding model catalog (G1) + reranker (G2).
- `/artifacts/datasets/` — synthetic dataset foundry catalog (G6).
- `/artifacts/spaces/` — HF Space app catalog (G10).
- `/artifacts/benches/` — eval benchmark publisher catalog (G11).
- `/skills/**` — cross-vendor SKILL.md catalog (D7 + side-effect distribution), if/when it ships.

## Article-body overrides (narrow, gated)

Articles live under `articles/**` and are Spark-authoritative for editorial content. Mac CC owns the
following narrow append-only chrome blocks; Spark CC never writes these blocks and never overwrites
them on republish. The blocks are gated on destination-side conditions Spark cannot observe (e.g.
existence of a matching artifact manifest), so the safe rule is "if you see one of these blocks at
the tail of an article, leave it alone."

- **Trailing catalog footer** — When an article has a matching artifact manifest at
  `src/content/artifacts/<slug>.yaml` (destination-side), Mac CC appends a single trailing block of
  the shape:

  ```markdown
  ---

  **Catalog page:** [`/artifacts/quants/<slug>/`](/artifacts/quants/<slug>/) — the same four-axis card rendered on this site, with the sweet-spot variant highlighted on a heatmap row.
  ```

  The block sits after the article's final editorial paragraph (or after the last `:::` if the
  article closes inside a directive). It points at destination-side catalog URLs (`/artifacts/<kind>/<slug>/`)
  that Mac owns per the chrome boundary table. Spark CC never emits this block; if `tech-writer`
  ever needs a similar pointer at source, surface it as a separate handoff item rather than writing
  into this gated region.

  Currently in use on (auto-grown as new artifact manifests land):
  - `articles/becoming-a-cyber-curator-on-spark/article.md` → `/artifacts/quants/securityllm-gguf/`
  - `articles/becoming-a-legal-curator-on-spark/article.md` → `/artifacts/quants/saul-7b-instruct-v1-gguf/`
  - `articles/becoming-a-gguf-publisher-on-spark/article.md` → `/artifacts/quants/finance-chat-gguf/`
  - `articles/becoming-a-medical-curator-on-spark/article.md` → `/artifacts/quants/ii-medical-8b-gguf/` (added 2026-05-16)

## Style overrides

The destination ships its own design system. Spark CC never edits `src/styles/**` on the Mac side.

- **Design tokens** — OKLCH palette in `src/styles/global.css` (surface / text / primary / success / border / SVG tokens), driven by CSS custom properties. Stagent → ainative.business is **light-first**; dark surfaces are token-defaulted but the production site renders light.
- **Font stack** — self-hosted Geist Sans (400 / 500 / 700) and Geist Mono via `public/fonts/*.woff2`, declared with `@font-face` and `<link rel="preload">` in `src/layouts/Layout.astro`. No CDN fonts.
- **Stylesheet layers** — `src/styles/{global,prose,api-prose,book,explainers,field-notes}.css`. Each layer scopes a surface; Mac CC owns all six.
- **Layouts** — `src/layouts/{Layout,FieldNotesLayout,BookLayout,DocsLayout,ApiDocsLayout}.astro`. Mac-owned; Spark articles render inside `FieldNotesLayout` but never read from these files.
- **Mac-only field-notes components** — `src/components/field-notes/{ArticleArcNav,BookmarkStar,ProjectStats,ReaderSettings,SeriesFilter,StageFilter,TermsInThisPiece,TocDrawer}.astro`. `ArticleCard.astro` mirrors source but Mac may extend it for marketing chrome.
- **Mac-extended signature components** — `src/components/field-notes/svg/*.astro` mirrors source's `src/components/svg/` (one-way Spark → Mac). Mac may have signatures source doesn't (e.g., signatures for the two reframed research papers `ai-transformation` and `solo-builder-case-study`); Spark never deletes destination-only signatures.
- **Mac-only utility libraries** — `src/lib/field-notes/{article-glossary,article-order,remark-explainers,rehype-explainer-figure}.mjs`. The two remark/rehype plugins are wired into `astro.config.mjs` markdown pipeline; source's markdown pipeline configures itself independently.

## Build / deploy config (Mac-authoritative)

- **Hosting** — GitHub Pages from `manavsehgal/ainative-business.github.io` with a CNAME at `public/CNAME = ainative.business`. Production base URL is **`/`**, not `/field-notes/` (corrected from earlier TBD note — `/field-notes/` is a route family inside a root-served site, not the Astro `base`).
- **Astro config** — `astro.config.mjs` sets `site: 'https://ainative.business'`, `trailingSlash: 'always'`. No `base`. Sitemap priority/changefreq is route-family-aware (root + field-notes weekly, docs weekly, about/projects/fieldkit monthly, privacy/terms yearly).
- **Redirects** — destination-owned `redirects:` map in `astro.config.mjs`:
  - `/research/` → `/field-notes/series/ai-native-platform/`
  - `/research/ai-transformation/` → `/field-notes/ai-transformation/`
  - `/research/solo-builder-case-study/` → `/field-notes/solo-builder-case-study/`
  - `/rss.xml/` → `/feed.xml/`
  - `/field-notes/series/autoresearch/` → `/field-notes/series/machine-that-builds-machines/` (the receipt of the 2026-05-08 series rename)
  - Auto-generated `/articles/<slug>/` → `/field-notes/<slug>/` for every article folder so Spark's intra-article cross-links resolve on the destination.
- **Custom 404** — none authored; Astro auto-generates from the layout. If/when a custom 404 ships at `src/pages/404.astro`, it's Mac-owned.
- **Deploy workflow** — `.github/workflows/deploy.yml`. Triggers on push to `main` and `workflow_dispatch`. Two jobs: build (Node 20, npm ci, install Chrome via `browser-actions/setup-chrome@v1` for OG image generation, `npm run build`, upload `dist/`) → deploy (`actions/deploy-pages@v4`). `concurrency: pages, cancel-in-progress: true`.
- **OG image pipeline** — Mac-owned `scripts/generate-slashless-duplicates.mjs` + `npm run build:og`; outputs to `public/og/field-notes/<slug>.png` for every article. Spark never touches `public/og/**`.
- **Discovery endpoints** — `src/pages/{feed.xml,feed.json,llms.txt,llms-full.txt}.ts`. Mac-owned.
- **Mac-side `sync-field-notes` skill** — lives at `.claude/skills/sync-field-notes/` in the destination repo only. Version-pinned via git commits on the destination side; no source-side version file. Source-skill script changes (handoff §B work) ship as PRs to destination.
- **Mac-side companion skills** — `.claude/skills/{ainative-stats,apply-api-docs,apply-book-update,apply-product-docs,apply-product-release,apply-screengrabs,deck,frontend-design,pptx}/`. None interact with Spark; listed for inventory completeness.

## Reverse-sync contract

Mac CC opens a PR to source (`manavsehgal/ai-field-notes`) updating only this file when:

1. A new top-level page or page family appears on the Mac side.
2. An existing design override changes in a way that would affect Spark's understanding of "do not touch."
3. The reverse-sync date is updated regardless (heartbeat — at most once per consumption cycle).

PR title prefix: `mirror: destination-overrides update — <date> — <one-line summary>`.
