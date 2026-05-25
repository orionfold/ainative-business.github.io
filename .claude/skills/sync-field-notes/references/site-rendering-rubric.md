# Site rendering rubric — artifact cards & detail pages

This file is the Astro-side companion to the source repo's `NARRATIVE-CONTRACT.md`
(canonical content rubric for both HuggingFace and the marketing site; read it at
`~/.cache/ai-field-notes-src/NARRATIVE-CONTRACT.md` after a Step 1 refresh, or on GitHub).

**The content rules live in `NARRATIVE-CONTRACT.md`.** This file covers
site-surface specifics only: which manifest field maps to which Astro
component slot, plus light-theme / mobile / a11y guidance the source-side
contract doesn't address because it's not relevant on HF.

## Section order on detail pages

Mirrors the canonical order in `NARRATIVE-CONTRACT.md`:

1. **Header** — kicker (kind + class + stack_origin badge), title, elevator (`positioning.headline`), hero signature SVG + meta strip
2. **What this model does** — `positioning.problem` → `positioning.use_cases` → `positioning.audience`
3. **Evaluated on Spark** — `vertical_eval` heatmap (LoRA), spec matrix (Quant), shape composition (Dataset/Bench)
4. **Choosing this lane** — only when `stack_origin` set AND (`lane_summary` present OR sibling lanes exist sharing `base_model`)
5. **How to use** — HF link + code snippet (PEFT load for LoRA, `load_dataset` for Dataset)
6. **Methods** — wire-back card linking to `/field-notes/<slug>/` (required by contract)
7. **Known drift** — `<dt>`/`<dd>` table from `known_drift`; each `<dd>` must contain a bound
8. **Other Orionfold variants** — sibling cross-link cards from `siblings`
9. **Lineage** — small badge with `lineage_run_id` (optional)

## Manifest → Astro slot mapping

| Manifest field | Astro component slot |
|---|---|
| `positioning.headline` | `.lora-detail__elevator` / `.qa-card__headline` / hub tile blurb |
| `positioning.problem` | `.lora-detail__problem` / `.qa-detail__problem` |
| `positioning.use_cases[]` | `.lora-detail__uses` (`<ul>`) |
| `positioning.audience` | `.lora-detail__audience` (callout) |
| `stack_origin` | `.lora-detail__kicker-stack` badge + drives signature color in `LoRASignature` |
| `lane_summary` | `.lora-detail__lane` paragraph (when set) |
| `vertical_eval` | `.lora-detail__eval-grid` (LoRA) / spec table heatmap (Quant) |
| `known_drift[]` | `.lora-detail__drift` (`<dl>` with `<dt>` items + `<dd>` bounds) |
| `siblings[]` | `.lora-detail__siblings` list of cross-link cards |
| `article` | `.lora-detail__followup-card` (Methods section) |
| `lineage_run_id` | `.lora-detail__lineage` badge |

## Visual contract (data-driven SVGs only)

Every card and detail page MUST carry a programmatic signature SVG that
derives its visual identity from manifest fields. **No editorial stock
imagery or AI-generated illustrations.** Per-kind signatures:

- `<QuantSignature />` — perplexity-vs-throughput tradeoff curve + sweet-spot halo
- `<BenchSignature />` — shape composition bar colored by scorer tier
- `<LoRASignature />` — seeded radial glyph, color-coded by `stack_origin`
  (Unsloth = accent, NeMo = primary), with optional vertical-eval overlay
- `<AdapterSignature />` — concentric arcs seeded by slug
- `<DatasetSignature />` — stacked bar (if shapes) or seeded data grid (fallback)

Each has both `variant="compact"` (card thumbnails, hub tile previews) and
`variant="hero"` (detail page top-of-page hero). The site verifier at
`scripts/verify_artifact_rendering.mjs` enforces signature presence on every
detail page.

## Light-theme + a11y requirements

- Light theme is primary (per `feedback_light_theme.md`). Every SVG must
  render legibly on `--color-surface` AND `--color-surface-raised`. Use only
  CSS custom properties (`--color-primary`, `--color-accent`,
  `--color-text-muted`, `--color-border`); never hardcode hex.
- WCAG AA contrast on all foreground text (per `feedback_pagespeed_techniques.md`)
- Every SVG carries `role="img"` and an `aria-label` summarizing the data
- Every signature SVG includes a `<title>` element with the accessible name
- `prefers-reduced-motion: reduce` disables stroke-draw and pulse animations

## Mobile layout

- Hero blocks reflow from 2-column (visual + meta) to 1-column at <840px
- Sibling cross-link cards stack vertically; no horizontal scroll
- Drift `<dl>` rows reflow from 2-column to single-column at <700px
- Tile previews on `/artifacts/` index keep their signature visible at all viewports

## Trailing slashes

Every internal link to an artifact detail page MUST use trailing slashes
(per `feedback_trailing_slashes.md`). The slashless duplicate generator
(`scripts/generate-slashless-duplicates.mjs`) handles GitHub Pages 301
avoidance for crawler discovery.

## Backfill TODO (quant manifests without positioning)

These older quants currently render via graceful-fallback ("At a glance"
section instead of "What this model does"). Source-side hf-publisher
should add `positioning`, `stack_origin`, and `known_drift` to:

- `finance-chat-gguf`
- `ii-medical-8b-gguf`
- `saul-7b-instruct-v1-gguf`
- `securityllm-gguf`

Once those flips happen at source, sync them via the normal `/sync-field-notes`
flow — no Mac-side changes needed beyond running the verifier.
