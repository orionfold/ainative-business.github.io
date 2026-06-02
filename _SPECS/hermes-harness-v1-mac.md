---
project: hermes-harness
version: v1.0-mac
status: locked
created: 2026-05-28
authoritative: Spark (this file mirrors)
source-spec: ~/.cache/ai-field-notes-src/specs/hermes-harness-v1.md
mirror-discipline: |
  This file mirrors the Spark spec section-for-section, restating Mac
  (ainative.business) scope per section. When the Spark spec gains, loses, or
  amends a section, this file is updated symmetrically in the same session —
  Spark stays authoritative; Mac never invents net-new sections without
  pushing them upstream first.
---

# Hermes Harness v1.0 — Mac (destination) integration mirror

> **How to read this file.** Every section header mirrors a section in the Spark
> spec. Each body opens with **"Mac scope:"** stating what destination work the
> Spark decision implies; sections where Mac has no work say so explicitly so the
> mirror stays section-complete and the diff against future Spark versions stays
> mechanical.

---

## 1. Context

**Mac scope:** consume. The site already renders 6 artifact kinds (quant, lora,
adapter, dataset, bench, notebook). This spec adds 2 more (`harness`, `skill`) +
1 new SERIES (`Harnesses`). Mac becomes the canonical place where a visitor
*reads* the cockpit narrative and *catalogues* the Spark-Hermes profile bundle
and the agentskills.io-compatible skill bundle.

The Harnesses series was added to `SRC/content.config.ts` `SERIES` enum + the
`'Harnesses': 'harnesses'` slug map in the prior sync (commit `02c3663`,
2026-05-26). The two new artifact kinds land in this sync.

## 2. Use-case taxonomy — the three pillars

**Mac scope:** consume only. The pillar metrics (time-to-first-turn,
tool-call reliability, sustained-load, dollar-curve) live on the article body
and the `harness` artifact manifest's fields (`spark_tokens_per_sec`,
`sustained_load_minutes`, `known_drift`). The destination renders these as-is;
no Mac-side measurement work.

## 3. Decisions

**Mac scope:** consume. Decision #2 (new artifact kinds `harness` + `skill`) is
the load-bearing one for this sync — implemented in §4.9 below.

§3.4 naming. The destination URL family is `kindToSegment("harness") = "harnesses"`
and `kindToSegment("skill") = "skills"`. Both render at `/artifacts/<family>/<slug>/`.
Mirrored in `chrome_footers._KIND_TO_URL_FAMILY` so the gated catalog footer on
bound articles emits the correct URL.

## 4. Architecture

### 4.0 Article sequence — Mac scope: zero

The article order is driven from source's `git log` via the sync's
`_compute_source_sequence()`. Mac doesn't reorder.

### 4.1–4.6 H1–H6

**Mac scope:** consume. Each Hx article lands as a normal field-notes entry
under `articles/<slug>/article.md`. Frontmatter pre-validated: `series: Harnesses`
is accepted by the destination schema (added in the prior sync); the
`fieldkit_modules: [harness]` enum value is accepted (added in the prior sync
to `fieldkitModules` in `src/content.config.ts`).

### 4.7 `fieldkit.harness` module — Mac scope: docs only

The destination mirrors the source's `fieldkit/docs/api/harness.md` into
`fieldkit/docs/api/harness.md` via the sync's auto-flow. The page is rendered
through the `fieldkit_docs` content collection and surfaced on the fieldkit
landing page (the `FieldkitModules.astro` section already carries a `harness:`
tagline — destination-authored, kept as destination-authoritative per the
"verify-only, skip" rule when source's wording drifts).

### 4.8 New artifact kinds — Mac scope: scaffold (this sync)

| Source contract | Destination scaffolding (this sync) |
|---|---|
| Append `'harness'` and `'skill'` to `fieldkit.publish.ARTIFACT_KINDS` | `src/lib/artifacts.ts` → `ARTIFACT_KINDS`, `SEGMENT_BY_KIND`, `DISPLAY_NAME_BY_KIND`, `PLURAL_DISPLAY_NAME_BY_KIND` |
| `HarnessProfile.to_manifest()` → `ArtifactManifest(kind="harness")` | Render path `src/pages/artifacts/harnesses/[slug]/index.astro` + list page `src/pages/artifacts/harnesses/index.astro` + signature `src/components/artifacts/HarnessSignature.astro` |
| `publish_skill()` → `ArtifactManifest(kind="skill")` | Render path `src/pages/artifacts/skills/[slug]/index.astro` + list page `src/pages/artifacts/skills/index.astro` + signature `src/components/artifacts/SkillSignature.astro` |
| `chrome_footers._KIND_TO_URL_FAMILY` | Extended with `harness → "harnesses"`, `skill → "skills"` + per-kind catalog-footer blurbs in `_BLURB_BY_KIND` |
| `scripts/verify_artifact_rendering.mjs` | Extended to walk `harnesses/` and `skills/` segments; signature-class regex extended with `harness-sig|skill-sig` |

The destination's catalog hub (`src/pages/artifacts/index.astro`) iterates
`ARTIFACT_KINDS` directly, so adding entries to the enum auto-grows the hub;
the new tiles render their compact signature components when a featured
artifact is available, no monogram fallback needed.

### 4.9 Schema edits (Session 1) — the two-site trap

**Mac scope:** done. Source spec calls out two sites that must land together:
- `src/content.config.ts` SERIES + ARTIFACT_KINDS + FIELDKIT_MODULES
- `src/pages/series/[series].astro` SERIES_COPY map

The destination's series rendering lives at `src/pages/field-notes/series/[series].astro`
(slightly different path than the source spec assumes). The Harnesses entry
landed in the prior sync; this sync confirms the route still resolves after the
new kinds are added.

## 5. Pillar-realization strategy

**Mac scope:** consume only. The metrics ship on each `harness` manifest's
`spark_tokens_per_sec`, `sustained_load_minutes`, and `known_drift` fields and
in the bound article body. Verifier rule 2 (`drift-bounded`) ensures every
drift entry on the destination renders with a numeric bound.

## 6. Harness artifact + bench design

**Mac scope:** render only. The harness detail page (`/artifacts/harnesses/<slug>/`)
opens with positioning (verifier rule 1), shows the lane variants with measured
throughput via `HarnessSignature` (verifier rule 4), then known drift (with
bounds, verifier rule 2). No forward-looking language anywhere in the page body
(verifier rule 3).

## 7. Reuse inventory

**Mac scope:** consume only.

## 8. Risks and contingencies

**Mac scope:** R12 ("two-site `[series].astro` edit gets missed → series page
500s") — Mac counterpart: missing render path for a new artifact kind. Mitigated
this sync by landing `src/pages/artifacts/{harnesses,skills}/[slug]/index.astro`
in the same commit as the manifests. Build will fail loudly via
`verify_artifact_rendering.mjs` if a kind ships without a render path.

## 9. Article-by-article task plan

**Mac scope:** consume. Articles ship via the normal sync flow. Catalog
footers auto-append for any article bound to a manifest at
`src/content/artifacts/<slug>.yaml` whose `kind:` is mapped in
`chrome_footers._KIND_TO_URL_FAMILY`.

## 10. Publish checklist

**Mac scope (destination chrome only):**
- The two new render paths (`/artifacts/harnesses/`, `/artifacts/skills/`) +
  the two new signature components.
- `chrome_footers._KIND_TO_URL_FAMILY` mapping for the new kinds.
- `scripts/verify_artifact_rendering.mjs` covers the new segments.
- Catalog hub tiles render compact signatures for the new kinds (no monogram
  fallback once a featured artifact exists per kind).

## 11. Change log

| Date | Change | Author |
|---|---|---|
| 2026-05-28 | Mirror landed. New kinds `harness`/`skill` scaffolded on destination — render paths, signatures, hub tiles, footer mapping, verifier coverage. Three new manifests copied from source: `hermes-brain-bench-v0.1` (kind: bench), `spark-hermes-profile` (kind: harness), `spark-hermes-skills` (kind: skill). | Manav (via Claude sync session) |

## 12. References

### Source spec
- `~/.cache/ai-field-notes-src/specs/hermes-harness-v1.md` (Spark, authoritative)

### Mac files touched in this sync
- `src/lib/artifacts.ts` — `ARTIFACT_KINDS` + segment/display maps
- `src/components/artifacts/HarnessSignature.astro` — new
- `src/components/artifacts/SkillSignature.astro` — new
- `src/pages/artifacts/harnesses/[slug]/index.astro` — new
- `src/pages/artifacts/harnesses/index.astro` — new
- `src/pages/artifacts/skills/[slug]/index.astro` — new
- `src/pages/artifacts/skills/index.astro` — new
- `src/pages/artifacts/index.astro` — KIND_BLURBS + tile-visual extended
- `scripts/verify_artifact_rendering.mjs` — segments + signature regex extended
- `.claude/skills/sync-field-notes/scripts/chrome_footers.py` — kind → URL family + per-kind blurbs
- `src/content/artifacts/hermes-brain-bench-v0.1.yaml` — new (copied from source)
- `src/content/artifacts/spark-hermes-profile.yaml` — new (copied from source)
- `src/content/artifacts/spark-hermes-skills.yaml` — new (copied from source)

### Memory cross-references
- `[[feedback_spec_mirror_discipline]]` — section-for-section mirror discipline
- `[[feedback_spec_location]]` — specs live in repo `spec/`, not `~/.claude/plans/`
- `[[project_artifact_manifests_phase2]]` — running ledger of artifact-kind expansion
