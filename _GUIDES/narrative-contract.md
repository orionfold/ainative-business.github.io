<!-- Narrative contract (Orionfold artifact READMEs + detail pages) — Last updated: 2026-05-23 -->

# Narrative contract — Orionfold artifact READMEs and detail pages

The canonical, surface-agnostic content rubric for every artifact published
under the Orionfold name. Both the HuggingFace model card and the
ainative.business detail page surface the same artifact; this file is the
single source of truth for what good looks like at both surfaces.

## Where this contract applies

- **HuggingFace model card** — enforced by `.claude/skills/hf-publisher/`
  (see `references/card-polish.md` for HF-surface specifics like
  frontmatter, llms.txt, Spark-tested table format)
- **ainative.business detail page** — enforced by the destination Astro
  templates (see destination repo's
  `.claude/skills/sync-field-notes/references/site-rendering-rubric.md` for
  Astro-component slot mapping)
- Future surfaces (PDF datasheet, deck slide, embedded share card) should
  reference this file as the rubric — never duplicate the rules elsewhere.

If the rules in this file conflict with anything in either per-surface
companion, this file wins.

## Section order (canonical)

Both surfaces present sections in this order. The order itself is part of
the contract — readers form their first impression from whichever H2 leads.

1. **Identifier strip** — kind + class + stack badge + publish date
2. **Title + elevator** — slug as title; `positioning.headline` as the one-line elevator
3. **What this model does** — `positioning.problem` → `use_cases` → `audience`
4. **Runnable on-ramp** (optional) — a `## Notebooks` section from
   `notebooks[]`: a short intro + a table (Notebook | What it does | Open) with
   Open-in-Colab / Open-in-Kaggle badges per row. Sits *after* positioning,
   before Spark-tested (see Rule 8). Only when the vertical ships notebooks.
5. **Spark-tested measurements** — the Orionfold moat; for quants this is
   the four-axis (perplexity / throughput / vertical eval / thermal envelope);
   for LoRA this is `vertical_eval` deltas vs baseline; for datasets this is
   shape composition + baseline numbers
6. **Variants / Choosing this lane** — within-repo variant picker (Quant);
   cross-sibling lane differentiation (LoRA/Adapter when `stack_origin` set
   and siblings share `base_model`)
7. **How to use** — HF link + minimal code snippet (PEFT for LoRA,
   `load_dataset` for Dataset, llama.cpp/ollama for Quant)
8. **Lineage** (optional) — `lineage_run_id`, trial log
9. **Methods** — wire-back to the field-notes article at
   `https://ainative.business/field-notes/<slug>/` (required)
10. **Known drift** — bounded limitations (every entry MUST carry a `bound`)
11. **Other Orionfold variants** — sibling cross-link table
12. **Footer** — Orionfold attribution + launch-list CTA (HF only); site
    footer chrome (site only)

## Content rules

### Rule 1 — Positioning leads, drift never above-the-fold

The first H2 after the elevator MUST be "What this model does" (positioning),
NEVER "Known drift" or "Known issues." Drift sits below Methods.

**Why:** A reader scrolls top-to-bottom. The first H2 sets the model's
first impression. The 2026-05-22 patent-strategist publish landed cards
with `## Known issues` as the first H2 — two MPEP fabrication bullets
above any positioning — which read as "this model hallucinates." After
repolish, positioning leads.

### Rule 2 — Every drift entry must carry a `bound`

Each entry in `known_drift` MUST include a `bound` field that quantifies
scope: a count ("2 of 200 bench questions"), a fraction ("<1% of probe
answers"), a comparison ("balance of bench cites real MPEP sections"), or
an inherited reference ("same scope as above"). Unbounded narrative drift
— "the model sometimes hallucinates legal citations" — is NOT card-ready.

**Why:** Unbounded drift sounds worse than it is. Bounding the scope
preserves honesty without overstating the problem.

### Rule 3 — No forward-looking roadmap language

Forbidden phrases anywhere in detail body / card body:

- "coming soon"
- "will fix" / "will address" / "will support" / "will ship"
- "on the roadmap" / "in the roadmap"
- "fix ETA" (no `fix_eta` field in any manifest schema)
- "v4 will" / "next version will" / "planned for v3.5"

Promises rot, over-promise, and shift the reader from what works today to
what might exist someday. Ship current truth only.

**Exception:** The catalog hub at `/artifacts/` (destination only) shows
"Coming soon" pills on inactive kinds. That's index chrome, not detail
narrative. The site verifier exempts hub tiles.

### Rule 4 — Sibling cross-links amplify reach

From card #2 onward, every artifact MUST list its siblings in a
cross-link section. Each entry: `{ slug, hook, hf_repo? }`. Hooks should
be one-liners that name the sibling's differentiator, not boilerplate.

**Why:** Cross-link amplification is the single largest engagement lever
the publish pipeline has. A reader on one card discovers the family in
one scroll instead of one search.

### Rule 5 — Lane differentiation required for multi-stack releases

When two or more artifacts share a `base_model` but differ in
`stack_origin` (e.g., patent-strategist Unsloth vs NeMo, finance-chat
GGUF vs BF16), each card MUST carry a "Choosing this lane" block naming
who picks this lane vs others. Either via explicit `lane_summary` field
or via an automatic "you're in the X lane, compare to N sibling lanes"
copy generated from the manifest.

**Why:** Without it, two siblings look like noise. With it, a reader
self-selects based on their constraints.

### Rule 6 — Wire-back to Methods

Every artifact MUST link to its field-notes article in the Methods section.
The site templates auto-generate this from the `article:` manifest field;
HF cards include a direct link to `https://ainative.business/field-notes/<slug>/`.

**Why:** The artifact is the deliverable. The article is the receipt.
Readers who want to verify the work, replicate the result, or understand
the trade-offs follow the wire-back. Without it, the artifact becomes
unverifiable.

### Rule 7 — Visuals are data-driven, not editorial

Every card thumbnail and detail page MUST carry a programmatic signature
SVG (or equivalent data visualization) generated from manifest fields.
No stock imagery, no AI-generated illustrations, no decorative graphics.
Color identity derives from `stack_origin` (so two siblings render
visually distinct at a glance).

**Why:** A data-driven visual reflects the artifact's actual shape — a
LoRA card colored by training stack and showing eval deltas tells the
reader more than a generic robot illustration. It also preserves the
moat: anyone can clone the README; only Orionfold has the per-artifact
Spark-measured data the signature is built from.

### Rule 8 — Runnable notebooks are their own section, after positioning

When a vertical ships notebooks (`notebooks[]` populated), the card carries a
`## Notebooks` section placed **after** the "What this model does" positioning
lead and **before** Spark-tested. It is a short intro line plus a table — one
row per notebook: **Notebook** name, a one-sentence "what it does," and an
"Open" cell with the standard Open-in-Colab / Open-in-Kaggle badges. Positioning
still leads (Rule 1); the on-ramp follows it.

Constraints: the table is the on-ramp and nothing more — names + one-sentence
blurbs + badges, no marketing copy and no measurement teasers. Default names /
blurbs come from the entry's `label` ("Build it" → **Builder**: reproduce the
build + Spark benchmarks; "Use it" → **User**: load the published model from
your app), overridable per entry via `name` / `blurb`. A vertical with no
notebooks omits the section. Source-of-truth is `ModelCard.notebooks` /
`ArtifactManifest.notebooks` (`{label, colab, kaggle}` per entry, plus optional
`name` / `blurb`); both surfaces render from the same field.

**Why:** HF renders every markdown image as `display: block` — even inside
table cells — so a bare inline badge row stacks one-badge-per-line with heavy
whitespace and reads as broken (the 2026-05-23 single-line attempt). A table
gives the horizontal Notebook/description/open structure and lets the two
badges stack *intentionally* within the Open cell. Making it a titled section
*after* positioning (not a pre-positioning badge strip) also keeps Rule 1
intact — positioning is the first thing the reader meets — while still selling
the one-click on-ramp and explaining what each notebook is for.

## Schema field requirements

For an artifact to satisfy this contract, the manifest MUST populate:

- `slug`, `kind`, `class`, `base_model`, `hf_repo` (existing required)
- `positioning.{headline, problem, use_cases[], audience}` (added v0.5.x)
- `stack_origin` (added v0.5.x; required when ≥2 siblings share base_model)
- `known_drift[]` with `{item, bound}` for every entry (added v0.5.x)
- `siblings[]` with `{slug, hook}` from card #2 onward (added v0.5.x)
- `article:` pointing to the field-notes wire-back (existing optional, now required)

Optional but recommended: `lane_summary`, `lineage_run_id`,
`vertical_eval`, `vertical_eval_name`, `notebooks[]` (Rule 8 badge row,
added in the notebooks-as-artifacts v1 work).

## Enforcement

- **HF surface:** `.claude/skills/hf-publisher/scripts/verify_stage.sh`
  (existing — checks section order, frontmatter completeness, etc.)
- **Site surface:** destination's `scripts/verify_artifact_rendering.mjs`
  (post-build check, blocks build on contract violation)
- **Schema:** `fieldkit/tests/test_publish_positioning.py` and
  destination's Zod schema in `src/content.config.ts`

A new surface (PDF, deck, etc.) joining the contract should add its own
verifier referencing this file — never duplicate the rules.

## Revision

This contract is amended only when a deliberate publishing-quality
decision is made (e.g., adding a new required section, changing the
canonical section order). Each amendment should leave a note in the
relevant session's HANDOFF.md and bump the date below.

Last amended: 2026-05-23 (PM) — reworks Rule 8 + the section order: the
runnable on-ramp is now a `## Notebooks` table section placed *after*
positioning, not a pre-positioning badge row. HF renders markdown images as
`display: block` (even in table cells), so an inline badge row stacks
one-per-line; a table fixes the layout and lets the on-ramp explain each
notebook. All 8 Orionfold cards re-pushed.

Prior: 2026-05-23 (AM) — added Rule 8 + section-order slot 3 for the runnable
Open-in-Colab / Open-in-Kaggle badge row, per
`_SPECS/notebooks-as-artifacts-v1.md` §8.3 (superseded same day).

Prior: 2026-05-22 (initial extraction from card-polish.md; adds Rule 7
visual contract; codifies section order across both surfaces).
