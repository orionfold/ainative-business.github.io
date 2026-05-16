# SEO Progress

Append-only journal of SEO snapshots for ainative.business. Latest snapshot at top.

Maintained by `.claude/skills/seo-monitor/`. Run via `/seo-monitor` (on-demand only).

Each snapshot summarises:
- **KPI deltas** vs the prior run, with arrows reflecting "good direction" (LCP ↓ better, clicks ↑ better)
- **Top movers** — queries/pages that swung the most
- **Applied auto fixes** — code edits this skill made on approval
- **Console actions** — manual tasks for the user to perform in Google's UI
- **Archive path** to the full per-snapshot file under `./seo/`
- **Build result**

---

## SEO Action Tracker

Persistent done/pending log for the HIGH/MED/LOW console actions surfaced by `/seo-monitor`. Updated as work is completed. The snapshot journal below is append-only; this tracker is mutable. Pending items here become the source for next session's HANDOFF.

### Strategy

The 12-indexed-of-305-submitted gap is mostly **queue lag** (Google's crawl budget on a low-authority property), but the 3 `crawled-not-indexed` URLs (`/book/ch-4-the-forge/`, `/book/ch-6-the-arena/`, `/docs/api/settings/`) are Google saying *"I looked, it wasn't worth keeping"* — driven by thin titles + descriptions. Fixing the metadata cluster is the only lever that moves both buckets: (a) demoted pages may get re-promoted on next crawl, (b) queued pages have stronger signals when crawled.

### Architectural rule (anti-skill-conflict)

Where possible, fix at the **template/layout** level rather than at the synced content level. Synced content (book chapter markdown, docs/api MDX bodies, field-notes articles) gets overwritten by `apply-book-update`, `apply-api-docs`, `apply-product-docs`, `sync-field-notes`. Layouts and dynamic-route files in `src/layouts/` and `src/pages/[...slug].astro` are NOT in any sync skill's manifest — safe to edit.

### Done — 2026-05-16 (this session)

**Audit delta: 333 → 303 issues (-30 resolved, 0 regressions).** Verified via `node .claude/skills/seo-monitor/scripts/audit_site.mjs`. Detail: title-issues 67→49 (-18), description-issues 262→250 (-12), trailing-slash hits unchanged at 4 (known false positives).

| ✓ | Fix | File | Replaces |
|---|-----|------|----------|
| ✓ | ApiDocsLayout suffix → `— ainative API Reference` | `src/layouts/ApiDocsLayout.astro:21` | Fixes 6 short titles across `/docs/api/{apps,chat,data,logs,tasks,views}/` (23–24 → 33–34 chars) |
| ✓ | BookLayout chapter pageTitle → `${title} — AI Native Business · Ch ${number}` | `src/layouts/BookLayout.astro:29-31` | Fixes 6 short titles across `/book/ch-3..ch-9/` (all 14 chapters re-verified within 25–65, longest is Ch 11 at 64) |
| ✓ | Book chapter description — programmatic 70–160 char builder with subtitle truncation | `src/pages/book/[...slug].astro:79-87` | Fixes 10 short descriptions on `/book/ch-3..ch-12/`. Ch 13 (very long subtitle) auto-truncates at 160 with `…` |
| ✓ | `SITE.description` trim 173 → 144 chars | `src/data/seo.ts:5` | Source of truth — propagates to homepage, ORGANIZATION JSON-LD, `/llms.txt`, `/llms-full.txt` |
| ✓ | `Layout.astro` `description` default now sources `SITE.description` | `src/layouts/Layout.astro:24` | Fixes homepage `/` (was using a stale 173-char fallback hardcoded in the layout default). Also any other page that doesn't pass its own description |
| ✓ | `/book/` page descriptions trimmed 162 / 164 → 140 / 148 | `src/pages/book/index.astro:24, 37` | Fixes `/book/` description-length warning |
| ✓ | `/docs/api/instance/` description trimmed 167 → 156 | `src/pages/docs/api/instance.mdx:4` | Single 7-char trim |
| ✓ | DocsLayout suffix → `— ainative Documentation` | `src/layouts/DocsLayout.astro:21` | Fixes 7 short titles across `/docs/`, `/docs/{apps,chat,profiles,projects,settings,tables}/` (20–24 → 29–33 chars) |
| ✓ | `apply-api-docs` skill — added SEO contract rule | `.claude/skills/apply-api-docs/SKILL.md:232-233` | Prevents `description:` regrowth >160 on next regen; documents that titles stay short (layout adds suffix) |
| ✓ | `apply-product-docs` skill — added SEO contract rule | `.claude/skills/apply-product-docs/SKILL.md:213-214` | Same rule for `/docs/*` non-api MDX scaffolding |
| ✓ | `apply-book-update` skill — added 160-char description guard | `.claude/skills/apply-book-update/SKILL.md:338` | Guards `/book/` site-chrome description from regrowing during count-driven updates |
| ✓ | GSC URL Inspection > Request Indexing — 3 crawled-not-indexed URLs | GSC console (`/book/ch-4-the-forge/`, `/book/ch-6-the-arena/`, `/docs/api/settings/`) | Manual user action after the layout/template fixes shipped. Reindex queued; awaiting next Google crawl to see promotion |

**Architectural rationale (preserved for next session):** Every fix lives in a **layout/template** (`*Layout.astro` or a dynamic `[...slug].astro`), not in synced content (chapter markdown, api MDX bodies). The sync skills (`apply-book-update`, `apply-api-docs`, `apply-product-docs`) regenerate content files; they don't touch layouts. The three skill updates above add explicit guards so that if a future maintainer (or me) regenerates content, the SEO contract is part of the regen contract.

### Pending

| Priority | Item | File / where | Owner | Why deferred |
|---------:|------|---------------|-------|--------------|
| HIGH | Rewrite KV-cache article title (95→≤65) + description (228→70–160) | `src/pages/field-notes/lora-fine-tune-nemotron-on-spark.mdx` | user (authored content) | Article body is source-of-record in `ai-field-notes/` source repo; needs source-side rewrite + sync, not destination edit |
| HIGH | Lengthen book chapter `description:` and `subtitle:` front-matter | `src/data/book/chapters/*.md` (synced from product) | user (authored content) | These come from the product source. Edit there, then `apply-book-update` syncs in. If we add a destination-only override layer, document in apply-book-update skill |
| MED | Trim 48 field-notes article titles >65ch — likely the `— AI Native Field Notes` layout suffix | TBD — likely `src/layouts/FieldNotesArticleLayout.astro` or similar | this skill (later session) | Need to inspect layout vs per-article frontmatter to decide template fix vs systemic content edit |
| MED | Trim 50 field-notes article descriptions >200ch | per-article frontmatter (synced) | user (authored content) | Source repo `ai-field-notes/` is authoritative; edit there per the SYNC contract |
| MED | Fix field-notes tag-page description template — 187 pages share too-short pattern | TBD — likely `src/pages/field-notes/tags/[tag].astro` | this skill (later session) | Single template fix; deferred to focus this session on HIGH cluster |
| LOW | Verify intentional noindex on `/field-notes/series/autoresearch/` | `src/pages/field-notes/series/autoresearch.astro` or related | user (decision) | Only excluded-by-noindex URL on the property — confirm intent |
| INFO | PSI quota — wire up personal Google Cloud API key OR wait for daily reset | `.claude/skills/seo-monitor/scripts/` or `.env` | user | Daily quota tied to shared no-API-key project; user owns auth strategy |
| USER | Resubmit sitemap in GSC | https://search.google.com/search-console/sitemaps?resource_id=sc-domain%3Aainative.business | user | Console-only action; click "Submit" again |

### Stale-flag rule reminder

After 3 consecutive runs with the same `<file>:<issue-id>` unfixed, `issue-history.md` flags it `manual-review-needed`. The audit fixes in "Done" below will resolve their keys in the next snapshot, so they age out naturally.

---

<!-- snapshots appended below this line; newest first -->

## [2026-05-16 09:37] Snapshot

**Window:** 2026-04-18 → 2026-05-16 (28 days)
**Status:** no-changes · 0 auto fixes applied · 4 skipped · 11 console actions surfaced
**Summary:** Clicks 1 (→ no change) · Impressions 42 (→ no change) · Indexed 12 (→ no change)

| KPI | Value | Δ vs prior |
|-----|-------|------------------|
| GSC Total clicks (28d) | 1 | → no change |
| GSC Total impressions (28d) | 42 | → no change |
| GSC Avg CTR (28d) | 2.4% | → no change |
| GSC Avg position | 8.10 | → no change |
| GSC Indexed pages | 12 | → no change |
| GSC Crawled Not Indexed | 3 | → no change |
| GSC Discovered Not Indexed | 0 | → no change |
| GSC Redirect | 3 | → no change |
| AUDIT Local audit issues | 333 | → no change |

**Applied auto fixes:** none.
**Skipped (4):** internal-href-missing-trailing-slash on src/layouts/Layout.astro:151 — False positive (stale — 2nd consecutive run): .woff2 font preload; trailing slash would 404; internal-href-missing-trailing-slash on src/layouts/Layout.astro:152 — False positive (stale — 2nd consecutive run): .woff2 font preload; trailing slash would 404; internal-href-missing-trailing-slash on src/pages/docs/api/documents.mdx:418 — False positive (stale — 2nd consecutive run): example API URL inside js code block; internal-href-missing-trailing-slash on src/pages/docs/api/uploads.mdx:161 — False positive (stale — 2nd consecutive run): example API URL inside js code block.
**Console actions surfaced (11):** [HIGH][STALE] Lengthen 6 book-chapter titles (`The Refinery`, `The Forge`, `Blueprints`, `The Arena`, `The Swarm`, 1 more) — GSC crawled-not-indexed lists /book/ch-4-the-forge/ and /book/ch-6-the-arena/; cross-references local audit's book_chapter_title_short cluster. 2nd consecutive run.; [HIGH][STALE] Lengthen 10 book-chapter descriptions (all currently 34–67 chars, target 70–160). Systemic — per-chapter front-matter or shared template. 2nd consecutive run.; [HIGH][STALE] Lengthen 6 /docs/api/* titles (e.g., `Apps API — ainative API` at 23 chars) — GSC crawled-not-indexed lists /docs/api/settings/. 2nd consecutive run.; [MED][STALE] Rewrite KV-cache article title (95→≤65) and description (228→70–160) at src/pages/field-notes/lora-fine-tune-nemotron-on-spark.mdx — top non-home GSC traffic (6 impressions, position 4.0). 2nd consecutive run.; [MED][STALE] Trim 48 field-notes article titles >65 chars — likely the `— AI Native Field Notes` suffix in the layout title template. 2nd consecutive run.; [MED][STALE] Trim 50 field-notes article descriptions >200 chars. Per-article front-matter or shared template. 2nd consecutive run.; [MED][STALE] Fix field-notes tag-page description template (187 pages share too-short pattern). Systemic layout fix. 2nd consecutive run.; [LOW][STALE] Trim homepage description 173→≤160 at src/pages/index.astro. 2nd consecutive run.; [LOW][STALE] Trim /book/ description 162→≤160 at src/pages/book/index.astro. 2nd consecutive run.; [LOW][STALE] Verify the noindex on /field-notes/series/autoresearch/ is intentional — only excluded-by-noindex URL on the property. 2nd consecutive run.; [INFO][STALE] Re-run PSI after quota reset OR obtain authenticated Google Cloud PSI API key — unauth project 583797351490 quota exhausted again this run. 2nd consecutive run..

**Archive:** seo/2026-05-16-0937.md · **Build:** ✓ —

---

## [2026-05-15 17:00] Snapshot

**Window:** 2026-04-17 → 2026-05-15 (28 days)
**Status:** first-run · 0 auto fixes applied · 4 skipped · 11 console actions surfaced
**Summary:** Clicks 1 (↓ —) · Impressions 42 (↓ —) · Indexed 12 (↓ —)

| KPI | Value | Δ vs prior |
|-----|-------|------------------|
| GSC Total clicks (28d) | 1 | ↓ — |
| GSC Total impressions (28d) | 42 | ↓ — |
| GSC Avg CTR (28d) | 2.4% | ↓ — |
| GSC Avg position | 8.10 | ↓ — |
| GSC Indexed pages | 12 | ↓ — |
| GSC Crawled Not Indexed | 3 | ↓ — |
| GSC Discovered Not Indexed | 0 | ↓ — |
| GSC Redirect | 3 | ↓ — |
| AUDIT Local audit issues | 333 | ↓ — |

**Top movers:**
- Page "https://ainative.business/" — clicks 0→1 (↑ +1)

**Applied auto fixes:** none.
**Skipped (4):** internal-href-missing-trailing-slash on src/layouts/Layout.astro:151 — False positive — font .woff2 asset, trailing slash would 404; internal-href-missing-trailing-slash on src/layouts/Layout.astro:152 — False positive — font .woff2 asset, trailing slash would 404; internal-href-missing-trailing-slash on src/pages/docs/api/documents.mdx:418 — False positive — example API URL inside JS code block; internal-href-missing-trailing-slash on src/pages/docs/api/uploads.mdx:161 — False positive — example API URL inside JS code block.
**Console actions surfaced (11):** [HIGH] Lengthen book chapter title + desc template — GSC 'Crawled-not-indexed' drilldown found /book/ch-4-the-forge/ and /book/ch-6-the-arena/ exactly match local-audit's too-short cluster (10 chapters with desc <70, 6 with title <25). HIGH-CONFIDENCE JOIN; [HIGH] Extend /docs/api/settings/ title (and the 6 docs/api cluster) — GSC drilldown lists settings as crawled-not-indexed; matches docs/api too-short-title local-audit cluster. HIGH-CONFIDENCE JOIN; Rewrite KV-cache article title (95→≤65) and description (228→70-160) at src/pages/field-notes/lora-fine-tune-nemotron-on-spark.mdx — top non-home GSC traffic (6 impressions); Patch audit_site.mjs trailing-slash detector — exclude file-extension URLs (.woff2/.png/.jpg/.css/.js) and content inside <pre>/<code> blocks (eliminates 4 false positives); Fix field-notes tag-page description template — 187 pages share too-short pattern (systemic); Trim field-notes article-description template (50 articles >200ch); Trim field-notes article-title template suffix (48 articles >65ch — likely the '— AI Native Field Notes' suffix); Trim homepage description (173→≤160) at src/pages/index.astro; Trim /book/ description (162→≤160) at src/pages/book/index.astro; Verify the noindex on /field-notes/series/autoresearch/ is intentional (only excluded-by-noindex URL on the property); Re-run PSI after midnight UTC OR obtain authenticated Google Cloud PSI API key — unauth quota exhausted this run.

**Archive:** seo/2026-05-16-1240.md · **Build:** ✓ — (no auto fixes applied)

---
