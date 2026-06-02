---
name: product-writer
description: Turn the building of a product (an app, tool, or cockpit shipped on the DGX Spark — e.g. Orionfold Arena) into a published product-launch article at /home/nvidia/ainative-business.github.io/products/<slug>/product.md. Use this skill whenever the user wants to write up, announce, launch, or market a product or tool they built — phrases like "write up the launch", "announce the Arena", "do a launch article for X", "market the product", "write the product story", "show what it took to build X", or invokes /product-writer. This is the sibling to tech-writer: tech-writer writes concept-teaching deep-dive essays; product-writer writes product launches with a mined build-metrics infographic (tokens, hours, lines of code, tests, features) and a screenshot-per-feature tour, reading for BOTH an AI-research audience (what it unlocks) and a Spark power-user/operator (what each feature does). Prefer this skill over tech-writer or freehand markdown when the subject is a shippable product and the goal is to launch/market it and sell the agentic-coding workflow that produced it. Targets a separate `products` content collection — see _GUIDES/product-articles.md.
---

# product-writer

Turn the building of a product on the DGX Spark into a published **launch
article** at `/home/nvidia/ainative-business.github.io/products/<slug>/product.md`.

This is the sibling to the `tech-writer` skill, and the distinction matters:

- **tech-writer** writes a *deep-dive essay* — it teaches a concept and uses the
  work as evidence. Concept first, steps as proof.
- **product-writer** writes a *product launch* — it introduces a thing the
  reader can have, shows what it took to build (a mined metrics infographic),
  tours its features (a screenshot + benefit per surface), and sells the
  agentic-coding workflow that produced it. Product first, build story as proof.

A product article serves two readers at once: the **AI researcher** (what does
this unlock — live experimentation, faster decisions, tighter prototyping on
one Spark?) and the **Spark operator** (what does each feature do for me, and
what does it look like?). Both are first-class. See
`references/voice-and-positioning.md`.

## A different content type — the products collection

Product articles are **not** deep-dives and do not live in `articles/`. They
live in their own collection at `products/<slug>/product.md` so the destination
site can render them with a launch layout (hero, build-metrics infographic,
feature-tour gallery) instead of the article reading layout.

`_GUIDES/product-articles.md` is the **contract to the destination
(Mac) repo**: it declares the new type, proposes the `products` Zod collection
for `src/content.config.ts`, and specifies the rendering the destination owns
(the `/products/` URL family, the launch layout, the infographic component).
Read it before authoring — the frontmatter you emit must match it. The
source/destination split is the same as everywhere in this repo: Spark authors
content + schema + spec; the Mac repo owns the rendering chrome.

## Mode router

Detect the mode from the user's phrasing, then follow the matching playbook.

| User intent | Mode |
|---|---|
| "write the launch", "announce X", "do a product article for X", "market the product", "/product-writer" | **draft** |
| "(re)mine the build metrics", "get the real numbers for X", "refresh the infographic data" | **metrics** |
| "capture the feature shots", "screenshot the tour", "refresh the screenshots for X" | **tour** |
| "polish the X launch", "tighten the product piece", "improve the launch article" | **polish** |
| "publish the X launch", "commit the product article" | **publish** |

If ambiguous, ask one sharp question rather than guessing.

## Every invocation — read these first

1. **Editorial source of truth:** `/home/nvidia/.claude/projects/-home-nvidia-ai-field-notes/memory/project_nvidia_learn_editorial.md` — the uber theme threads product articles too (everything ties back to maximizing one Spark for one builder).
2. **Voice + positioning:** `references/voice-and-positioning.md` before writing any prose. The two hard lines: positioning first, and **never name or imply a competitor** (no clone/copy/alternative-to framing — this has bitten before).
3. **Privacy + security:** the blog is public and permanent. The scrub rules are identical to tech-writer's — read `../tech-writer/references/privacy-and-security.md` and apply it to `product.md`, screenshots, and `assets/`. `scripts/verify_product_article.sh` re-runs the secret scan as a hard gate.
4. **Destination contract:** `_GUIDES/product-articles.md` (schema + rendering ownership).

## Mode playbooks

### draft

The full launch article. This is the most common invocation.

1. **Get the positioning.** Before anything, pin down the one-sentence "what is
   this and who is it for." If the user hasn't given it, ask — it's the lead and
   it's theirs, not yours. (This is the product-article analogue of the
   tech-writer editorial overlay.)
2. **Propose a slug** (kebab-case, the product's short name — e.g.
   `orionfold-arena`). Confirm, then run
   `scripts/new_product_article.sh <slug>` to scaffold
   `products/<slug>/` from the template.
3. **Mine the build metrics** (the `metrics` step below) into
   `products/<slug>/assets/build-metrics.json`, and copy the figures into the
   frontmatter `build:` block. Do this before writing the build-story section
   so the numbers are real, not placeholders. See
   `references/metrics-infographic.md`.
4. **Capture the feature tour** (the `tour` step below) into
   `products/<slug>/screenshots/`. The product must be running. See
   `references/feature-tour.md`.
5. **Write `product.md`** following the seven-beat blueprint in
   `references/product-narrative-structure.md`: positioning → what it unlocks →
   build story (+ infographic) → feature tour → built on the substrate → the
   workflow generalized → get it. Lead with the product, not the build story.
6. **Credit the substrate honestly.** A Spark product is buildable in a day
   *because* of what already existed — name the `fieldkit` modules the product
   surfaces (it is often largely a thin surface over them) and the AI Field
   Notes articles/artifacts that gave it real data. Set `fieldkit_modules` in
   frontmatter for the modules it actually uses.
7. **Optional architecture diagram** (section 3 or 5) if it reinforces the
   leverage story — reuse the tech-writer `fn-diagram` archetypes/invariants
   (`../tech-writer/references/visualizations.md`). Unlike a deep-dive, a
   diagram is optional here; the infographic + tour already carry the visuals.
8. **Scrub** per the privacy reference. Tell the user at a category level what,
   if anything, was redacted.
9. **Report:** what was written, the mined numbers (and any honesty caveats —
   e.g. cache-read ratio, single-model build), which features were toured, and
   which sections need the user's input (usually the positioning lead and the
   "what's next" close).

### metrics

(Re)mine the build numbers. Standalone, or step 3 of `draft`.

1. Establish the **build window** (first real commit → ship commit) and the
   source paths, test globs, and commit pattern for the product.
2. Run `scripts/mine_build_metrics.py` (see `references/metrics-infographic.md`
   for the full invocation and how to choose the window honestly). Exclude
   built bundles with `--loc-exclude` so "lines of code" means *authored*
   source.
3. Write the JSON to `products/<slug>/assets/build-metrics.json` and sync the
   `build:` frontmatter block to match.
4. Eyeball the by-model split and the cache ratio — these drive the honest
   framing in the prose. Never quote a prose number that isn't in the JSON.

### tour

Capture (or refresh) the feature screenshots.

1. **Start the product** so captures show real, populated data (e.g.
   `fieldkit arena up`; let telemetry/model output warm up). Empty states don't
   sell.
2. Capture one scoped Playwright-MCP shot per surface to
   `products/<slug>/screenshots/NN-feature.png`, in tour order. Mechanics and
   the aarch64 fix: `../tech-writer/references/screenshot-workflows.md`. Privacy
   discipline: scoped shots, fresh profile, visual scan before embedding.
3. Update the frontmatter `features:` list (name + benefit + screenshot path)
   and the tour section of `product.md`. Write benefit-led captions, not labels
   — see `references/feature-tour.md`.

### polish

1. Read the existing `products/<slug>/product.md`.
2. Ask what specifically to improve — polish scope varies (sharper positioning?
   a re-mine of the metrics? a new feature shot? tighter workflow section?).
   Don't guess.
3. Edit in place, preserving frontmatter and section order unless asked
   otherwise. If you touched the build window or source, re-run `metrics`.
4. Re-scan for voice drift (`references/voice-and-positioning.md`) — the usual
   drifts are hype creep and a competitor punch sneaking back in.

### publish

1. Run `scripts/verify_product_article.sh <slug>` — frontmatter, filled metrics
   block, screenshots resolve, no leftover placeholders, secret scan. Fix any
   `FAIL` before proceeding.
2. Refresh project stats if the repo's stats pipeline counts products
   (check whether `src/data/field-notes/project-stats.json` has a products bucket; if so run
   the stats refresh — coordinate via `_GUIDES/product-articles.md`, since the
   destination owns the home infographic).
3. Stage `products/<slug>/` (and any refreshed stats) and commit with a
   descriptive message: `Add product launch: <Product Name>`.
4. **Do not push.** Report the commit hash; the user pushes when ready. The
   destination repo picks up the new `products/<slug>/` via the normal sync.

## Relationship to the other skills

- **tech-writer** — concept deep-dives in `articles/`. If the user wants to
  *teach how something works* rather than *launch a product*, that's tech-writer.
  A product can have both: a launch article here and a deep-dive there that
  cross-link.
- **frontend-design** — if the user wants to change the product's UI or the
  site's design, that's frontend-design, not this skill.
- **fieldkit-curator / hf-publisher / notebook-author** — release and artifact
  surfaces. This skill writes *about* shipped products; it doesn't cut releases.

## Non-negotiables

- **Lead with the product, positioning first.** Not the build story, not the
  metrics. The reader knows what it is and who it's for within two paragraphs.
- **Never name or imply a competitor.** No clone/copy/alternative-to/"what X
  can't do" framing, even obliquely. State strengths on their own terms.
- **Every metric is mined, never estimated.** If a number is in the prose it is
  in `build-metrics.json`. Quote the cache ratio and the real model mix
  honestly — the truth is more impressive than a rounded boast.
- **Serve both readers.** The argument stands without screenshots; the tour
  stands on its captions alone.
- **Never publish secrets, PII, or system fingerprinting**, and **never
  auto-push.** Same discipline as tech-writer.

## When things go sideways

- **No `products/` tree yet?** `new_product_article.sh` creates the folder; the
  destination renders it once `_GUIDES/product-articles.md`'s schema is wired on the Mac
  side. If the local Astro dev doesn't yet have the `products` collection, that
  is expected — it's a destination-owned rendering step, not a Spark blocker.
- **Token mine returns 0 / wrong totals?** Check the `--log-dir` points at the
  right project transcript dir and the `--since/--until` window is correct;
  resumed sessions are deduped by message id so re-runs are stable.
- **Product won't start for screenshots?** Capture what you can, mark the
  missing surfaces, and tell the user which features still need a shot rather
  than shipping empty-state captures.
- **Playwright-MCP missing on aarch64?** Same bundled-chromium fix as
  tech-writer — see `../tech-writer/references/screenshot-workflows.md`.
