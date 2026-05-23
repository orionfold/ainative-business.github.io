---
project: notebooks-as-artifacts
version: v1.0-mac
status: locked
created: 2026-05-23
authoritative: Spark (this file mirrors)
source-spec: /Volumes/home/ai-field-notes/specs/notebooks-as-artifacts-v1.md
mirror-discipline: |
  This file mirrors the Spark spec section-for-section, restating Mac
  (ainative.business) scope per section. When the Spark spec gains, loses, or
  amends a section, this file is updated symmetrically in the same session —
  Spark stays authoritative; Mac never invents net-new sections without
  pushing them upstream first.
supersedes: spec/2026-05-22-model-playground-and-eval-surface-design.md (v1 — playground/leaderboard approach, dropped)
---

# Notebooks as a first-class artifact — Mac (destination) integration mirror

> **How to read this file.** Every section header mirrors a section in the Spark
> spec. Each body opens with **"Mac scope:"** stating what destination work the
> Spark decision implies; sections where Mac has no work say so explicitly so the
> mirror stays section-complete and the diff against future Spark versions stays
> mechanical.

---

## 1. Context

**Mac scope:** consume. The site already renders 5 artifact kinds (quant, lora,
adapter, dataset, bench) per the May 22 `be7c219` render-path work. The pivot
adds a 6th kind (`notebook`) and a new `notebooks: {colab, kaggle}` field that
appears on **every** artifact kind's manifest, not just `kind: notebook`. Mac
becomes the canonical place where a visitor *sees* the badge row that turns a
Spark-published notebook into a one-click runnable artifact. The site doesn't
*execute* anything; it surfaces what Spark publishes.

Replaces the v1 playground spec entirely (`spec/2026-05-22-model-playground-…`)
— that approach (HF Space CPU + `/playground/` page + `/evals/` leaderboard)
is dropped. Kept as historical reference per user instruction; do not
implement.

---

## 2. Decisions locked

**Mac scope:** adopt Spark's four locked decisions; add three Mac-only:

| # | Decision | Choice |
|---|----------|--------|
| M-1 | Naming-pluralization | `kind: notebook` → URL segment `/artifacts/notebooks/` (matches established plural-by-kind convention at `src/lib/artifacts.ts`). |
| M-2 | Badge row scope | The `NotebookBadges` component renders above-the-fold on **every** artifact detail template that exists today (Quant, LoRA, Adapter, Dataset, Bench, Notebook) when the manifest carries the `notebooks` field; graceful no-op when absent. |
| M-3 | Schema mirror order | Land the kind addition + the `notebooks` zod field as a **scaffold PR before** the first pilot manifest syncs over, so the patent-strategist notebook manifest doesn't break the build on arrival. |

---

## 3. Artifact-kind change — add `"notebook"` (the 6th kind)

**Mac scope:** mirror two of the three Spark files (the third is fieldkit-internal):

- `src/lib/artifacts.ts` — extend `ARTIFACT_KINDS` from `['quant','lora','adapter','dataset','bench']` to add `'notebook'`. All three name maps in that file (display name, plural segment, blurb) get a `notebook` entry. The TS compiler will catch any stale references on the next `npm run build`.
- `src/content.config.ts` — the zod enum already reads from `ARTIFACT_KINDS`, so the kind addition lands automatically via the import. **Add** the new optional field below to the artifact schema:

  ```ts
  notebooks: z
    .object({
      colab: z.string().url().optional(),
      kaggle: z.string().url().optional(),
    })
    .optional(),
  ```

  Optional + nested-optional so a manifest can carry just `colab` (Kaggle deferred per Spark §14), and so older manifests without the field still validate.

**Manifest granularity** (informational for Mac): Spark publishes **one notebook manifest per vertical** with `variants: [builder, user]` and `class: ipynb`. No new perplexity/spark_tokens_per_sec/vertical_eval fields — those are sourced from the sibling **model** manifest by slug at render time (see §10).

---

## 4. Notebook anatomy

**Mac scope:** none — informational. The builder/user split is rendered *inside*
the .ipynb, not on the Astro page. The detail page surfaces *that two notebooks
exist* (via the variants chip + the badge row pointing at each), not their
internal narrative.

---

## 5. Repo layout

**Mac scope:** none — the notebook source-of-truth (`notebooks/<vertical>/*.{py,ipynb}`) lives in `ai-field-notes` (Spark-side). Mac never owns notebook files; if a `notebooks/` directory exists in this repo, it is wrong and should be removed. Confirm none currently exists before scaffolding.

---

## 6. Dual-path runtime contract

**Mac scope:** none — Mac doesn't execute notebooks. The destination page may
*mention* that the notebook is dual-path (Spark + Colab/Kaggle) in the
`positioning.problem` or `positioning.use_cases` strings Spark populates, but
Mac doesn't enforce or detect runtime.

---

## 7. Visual system + tooling

**Mac scope:** none for chart/table rendering (that happens inside the
notebook). Two indirect dependencies:

- `NotebookSignature.astro` (Mac) must visually harmonize with the same OKLCH
  brand palette `fieldkit.viz` ships in `orionfold.mplstyle` — so the signature
  on the card and the chart inside the linked notebook feel like one product.
  Reuse the existing `--color-primary`/`--color-accent` CSS custom properties
  established by the May 22 LoRA/Adapter/Dataset signatures.
- Notebook snapshot PNGs Spark exports to `notebooks/<vertical>/exports/`
  (tracked) may eventually be **embedded** in the Mac notebook detail page as a
  "preview" — defer to a v1.1 mirror update; do not build for v1.

---

## 8. New fieldkit surface (extractions)

**Mac scope:** §8.1, §8.2, §8.4, §8.5 are fieldkit-internal (Spark). Only §8.3
has a Mac side.

### 8.3 `ArtifactManifest.notebooks` field — Mac render

Add **`NotebookBadges.astro`** at `src/components/artifacts/`:

- Renders an inline horizontal badge row with the standard Colab + Kaggle SVGs (Colab `colab-badge.svg`, Kaggle `open-in-kaggle.svg` — assets shipped in `public/badges/`).
- Each badge is an anchor to the URL from `data.notebooks.{colab,kaggle}`.
- WCAG AA contrast checked on light theme (primary) and dark theme (secondary) per `feedback_pagespeed_techniques.md` and `feedback_light_theme.md`.
- Trailing slashes preserved if the manifest URL is on our domain; pass through untouched if external (Colab/Kaggle/GitHub URLs are external and don't take our slash convention).

**Slot mapping** — inject the component above-the-fold on every kind's detail template, **after** the `positioning` block (kicker → title → elevator → hero signature → meta strip → **NotebookBadges** → "What this model does"):

- `src/pages/artifacts/quants/[slug]/index.astro` — already extended in `be7c219`; add a `<NotebookBadges />` slot conditional on `notebooks` present.
- `src/pages/artifacts/loras/[slug]/index.astro` — same.
- `src/pages/artifacts/adapters/[slug]/index.astro` — same.
- `src/pages/artifacts/datasets/[slug]/index.astro` — same.
- `src/pages/artifacts/benches/[slug]/index.astro` — same.
- `src/pages/artifacts/notebooks/[slug]/index.astro` — **new** (§9 below); badges point at *its own* Colab/Kaggle URLs (a notebook artifact's badges are how you open the notebook itself).

**Catalog tile** — when a manifest carries `notebooks`, the corresponding `*Card.astro` (e.g. `QuantCard.astro`) shows a tiny inline "▶ Colab" affordance under the headline so visitors notice the runnable on-ramp at the listing level too. Same conditional render.

---

## 9. Two skills (built via `skill-creator`)

**Mac scope:** none — both skills are Spark-side. Mac consumes their outputs:
the notebook manifests they emit (`notebook-author`) and the snapshot PNGs they
produce (`notebook-snapshot`, deferred to v1.1 for Mac embedding per §7).

The render path Mac builds in §3 + §8.3 + §10 must work *without* the skills
existing on Mac.

---

## 10. Pilot — patent-strategist (Mac integration)

**Mac scope:** verify the destination renders the patent-strategist notebook
manifest end-to-end after Spark publishes it.

**New render path for `kind: notebook`** (mirrors the LoRA/Adapter/Dataset path
landed in `be7c219`):

- `src/components/artifacts/NotebookSignature.astro` — **new**; programmatic
  data-driven SVG (compact + hero variants). Use the same seeded-glyph pattern
  as `LoRASignature.astro` but with a distinctive shape (suggestion: a
  document-with-cursor glyph or a stacked-cells motif so it reads as
  "notebook" at a glance, not another lora variant).
- `src/components/artifacts/NotebookCard.astro` — **new**; renders
  `positioning.headline` prominently, variants chip showing `builder` /
  `user`, plus the inline ▶ Colab affordance from §8.3.
- `src/pages/artifacts/notebooks/index.astro` — **new** listing page.
- `src/pages/artifacts/notebooks/[slug]/index.astro` — **new** detail page.
  Section order per NARRATIVE-CONTRACT: kicker → title → elevator → hero
  `NotebookSignature` + meta strip → **NotebookBadges** (above-the-fold) →
  "What this notebook does" (positioning.problem / use_cases) → "Choosing the
  variant" (builder vs user, per Spark §4.1/§4.2) → "Methods" (article
  wire-back) → "Known drift" (Colab-Q4 vs Spark-BF16 bound) → "Sibling
  artifacts" (the model manifests this notebook targets, resolved by `hf_repo`).

**Sibling-data sourcing** (Spark §3 contract): on the notebook detail page,
locate the sibling model manifest by walking the `siblings[]` array (when
populated) or by `hf_repo` match against other artifacts. Reuse the existing
`resolvedSiblings` pattern from `src/pages/artifacts/quants/[slug]/index.astro:53-65`.
Surface the sibling model's `vertical_eval` / `perplexity` numbers in the
"Sibling artifacts" section as a courtesy cross-link, not as the notebook's
own data.

**Catalog hub** — `src/pages/artifacts/index.astro` adds the 6th tile
("Notebooks", count = N from `getCollection('artifacts', d => d.kind === 'notebook')`).

---

## 11. Templatization rule

**Mac scope:** none for v1. The vertical template is Spark-side. Mac's render
path is already kind-generic (one template per kind, manifest-driven content);
adding finance / legal / cyber / medical notebook manifests post-pilot
requires zero Mac code change beyond a `npm run build`.

---

## 12. Distribution — Mac primary owner

**Mac scope:** primary. Two surfaces (HF README, Civitai card) are Spark's;
the ainative artifact card is Mac's.

Already covered above:
- Detail-page badge row (§8.3 NotebookBadges slot mapping)
- Catalog-tile inline ▶ affordance (§8.3 tail)
- New `/artifacts/notebooks/` listing + detail (§10)

**Cross-link audit** — the new `notebooks` field on (say) a `kind: quant`
manifest points to notebooks that target *that* quant. When the user clicks
through to the notebook detail page, the "Sibling artifacts" section should
show the originating quant card. This is bidirectional sibling resolution;
verify both directions render before declaring done (Spark may not populate
`siblings[]` symmetrically — Mac should still resolve via `hf_repo` match).

---

## 13. Verification

**Mac scope:** extend `scripts/verify_artifact_rendering.mjs` post-build checks:

- When a parsed `<artifact>.yaml` manifest carries `notebooks: { colab }` (or `kaggle`), the rendered HTML must contain a recognizable badge-row element (regex against `class="*notebook-badges"`) and that element must appear **before** the first `<h2>` in the article body (above-the-fold per Spark §8.3 + NARRATIVE-CONTRACT).
- Notebook detail pages must pass all existing contract checks (first H2 is positioning-shaped, drift entries carry `bound`, no forward-looking phrases, signature SVG present).
- The catalog hub at `/artifacts/` renders 6 tiles (was 5 after the May 22 work).

**Browser smoke** (via `claude-in-chrome` MCP per `feedback_pagespeed_techniques.md`):
- `npm run dev` → load `/artifacts/`, confirm 6 tiles.
- Load `/artifacts/notebooks/` (empty state pre-pilot, 1+ entry post-pilot).
- Load `/artifacts/notebooks/<patent-strategist-slug>/` after pilot sync — confirm signature, badges, variants chip, sibling cross-links resolve.
- Load `/artifacts/loras/patent-strategist-v3-nemo/` — confirm new badge row injects above-the-fold without disturbing the existing layout.
- Lighthouse + WCAG AA contrast on the new pages; light theme primary.

**Trailing-slashes audit** (per `feedback_trailing_slashes.md`): every internal
link the new components emit (`/artifacts/notebooks/<slug>/`, listing page,
catalog tile) ends in `/`. External Colab/Kaggle URLs are passed through
verbatim.

---

## 14. Deferred / open (Mac side)

- **v1.1 — Snapshot PNG embedding.** When Spark's `notebook-snapshot` skill is
  shipping `exports/*.png` reliably, embed the hero PNG (e.g. `spark_quad.png`)
  inline on the notebook detail page as a "preview" between the elevator and
  the badge row. Requires a new manifest field
  `notebook_previews: { hero: <path>, ... }` — defer until Spark side proposes
  the field shape.
- **v1.1 — Nav entry.** Should `/artifacts/notebooks/` get its own top-nav
  link, or stay nested under the catalog hub at `/artifacts/`? Defer to after
  the pilot ships and we can see the traffic pattern.
- **Sibling backfill on existing quant manifests.** Once Spark publishes the
  patent-strategist notebook manifest, the 4 patent-strategist sibling
  manifests (lora-nemo, lora-unsloth, gguf-nemo, gguf-unsloth) should add the
  notebook to their `siblings[]` list — destination already renders the
  sibling block when populated; no Mac code change. Source-side authoring.

---

## 15. Research sources

**Mac scope:** none Mac-specific. The Spark spec §15 covers the visual /
authoring / snapshot stack. Mac's render path follows existing patterns from
the May 22 work (`be7c219`); no new research dependencies.

---

## Sync-discipline checklist (run when Spark spec changes)

When `/Volumes/home/ai-field-notes/specs/notebooks-as-artifacts-v*.md` updates:

1. Diff old vs new Spark spec section-by-section.
2. For each changed section, update the **same-numbered** section in this file with the new Mac scope, even if "Mac scope: none — informational" remains true.
3. If a section is added/removed on Spark side, add/remove the mirror section here.
4. Bump this file's `version:` to track Spark's (`v1.0-mac` → `v1.1-mac` etc.).
5. If a code change is implied (new field, new kind, changed slot), update the relevant Mac scope detail and **flag the implementation delta as the first item in HANDOFF.md Open items**.

The Spark spec is authoritative; this file is the destination *translation*.
