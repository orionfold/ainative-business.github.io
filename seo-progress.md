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

### Done — 2026-05-16 (final session — template-level truncate clears 92 → 0)

**Audit delta: 92 → 0 issues (-92 resolved, 0 regressions).** Both remaining clusters (39 over-long article titles, 53 over-long article descriptions, 4 over-long series-page blurbs after the article fixes surfaced them) cleared via template-level truncation. Build clean at 391 pages.

| ✓ | Fix | File | Replaces |
|---|-----|------|----------|
| ✓ | Article `<title>` smart-truncate at em-dash / colon / `?!` separator (pick longest head that fits +SUFFIX in 65) | `src/pages/field-notes/[slug]/index.astro:38-65` | All 39 title-length issues. On-page `<h1>` still renders full `title` |
| ✓ | Article `<meta description>` via `truncateForMeta` (word-boundary cut to ≤160 + `…`) | `src/pages/field-notes/[slug]/index.astro:67-75,86` | All 53 article description-length issues. JSON-LD `description: summary` and the on-page `<p class="article__summary">` stay full |
| ✓ | Series-page `<meta description>` via same `truncateForMeta` | `src/pages/field-notes/series/[series].astro:62-71` | 4 over-long blurbs in `SERIES_COPY` (ai-native-platform, frontier-scout, looking-beyond-spark, machine-that-builds-machines @ 333ch). On-page `<p class="stage-header__blurb">` still renders full prose |

**Architectural rationale (continued).** The article fixes mirror the fieldkit/api pattern from the prior session: synced source-of-record stays in source (`summary` and `title` come from `ai-field-notes/articles/*/article.{md,mdx}` frontmatter); only the meta tags are truncated/condensed via template logic. Visible page content (`<h1>`, `<p class="article__summary">`, ArticleCard listings) keeps the author's full prose. The series-page fix is destination-only content (`SERIES_COPY` constant); the truncate runs locally rather than editing the prose because the on-page blurb is pedagogically dense — the 333ch `machine-that-builds-machines` text is the right length for a reader landing on the index, just too long for Google's snippet window.

### Done — 2026-05-16 (earlier session — destination-fixable description cluster)

**Audit delta: 104 → 92 issues (-12 resolved, 0 regressions).** All 12 destination-fixable description-length issues cleared: /about/ (181→155), /field-notes/ (195→152), /fieldkit/ (284→158), /artifacts/quants/* × 4 (173–183→134–144), /fieldkit/api/* × 5 (183–401→153–157 via in-template truncation). Build clean at 391 pages.

| ✓ | Fix | File | Replaces |
|---|-----|------|----------|
| ✓ | /about/ description trim — drop redundant "a … for AI-native operators" suffix | `src/pages/about.astro:60` | 181 → 155ch |
| ✓ | /field-notes/ index description — strip "published" + "spanning … series of research papers. By Manav Sehgal." | `src/pages/field-notes/index.astro:24` | 195 → 152ch (stays ≤160 up to N=999 articles) |
| ✓ | /fieldkit/ index description — condense to module list | `src/pages/fieldkit/index.astro:44-45` | 284 → 158ch |
| ✓ | /artifacts/quants/[slug]/ description template — compress to four-axis card line | `src/pages/artifacts/quants/[slug]/index.astro:76` | 173–183 → 134–144ch across the four cards |
| ✓ | /fieldkit/api/[module]/ — meta-only truncator | `src/pages/fieldkit/api/[module].astro:42-49` | 183–401 → ≤157ch via word-boundary truncate; on-page blurb still shows full `summary` |

**Architectural note (continued).** The fieldkit/api fix is the first time this session needed to diverge meta description from on-page text. The `truncateForMeta` helper is local to the template; rationale: `summary` is synced source-of-record from `ai-field-notes`, so editing the field directly would (a) get clobbered on next sync or (b) require an upstream PR for prose that reads fine at full length for human visitors. Truncating only the meta tag preserves both contracts.

### Done — 2026-05-16 (earlier session — MED cluster + audit-detector patch)

**Audit delta: 303 → 104 issues (-199 resolved, 0 regressions).** Verified via `node .claude/skills/seo-monitor/scripts/audit_site.mjs`. Detail: title-issues 49→39 (-10), description-issues 250→65 (-185), trailing-slash 4→0 (false-positive detector patched). Build clean at 391 pages.

| ✓ | Fix | File | Replaces |
|---|-----|------|----------|
| ✓ | Field-notes article `<title>` — conditional suffix (drop when `title + " — AI Native Field Notes"` >65ch) | `src/pages/field-notes/[slug]/index.astro:33-45,80` | Resolves 10 title-length issues. Remaining 39 are source-authored raw titles >65ch — inherent to author style, not destination-fixable |
| ✓ | Field-notes tag-page `<meta description>` — new template at 100–140 chars | `src/pages/field-notes/tags/[tag].astro:39-44` | Resolves ~185 description-length issues across all tag pages. Visible-page blurb (`Articles tagged "${tag}" — N entries.`) preserved on-page; SEO `description` diverges to satisfy 70–160 contract |
| ✓ | `/field-notes/` index title `Field Notes — ainative` (22ch) → `AI Native Field Notes — research on building AI-native business` (63ch) | `src/pages/field-notes/index.astro:23` | Resolves the 1 too-short title flagged at `/field-notes/` |
| ✓ | Audit trailing-slash detector — exclude JS property assignments (`link.href = '/api/...'`) via negative-lookbehind, and add `woff2/woff/ttf/otf/eot` to asset-extension blacklist | `.claude/skills/seo-monitor/scripts/audit_site.mjs:167,172` | Eliminates 4 known false positives (2 font preloads + 2 MDX code-block examples). Future runs will report these as fixed rather than skipped |

**Architectural rationale (continued from earlier session):** All four fixes again live in **layouts / dynamic-route templates / audit tooling** — none in synced content. The article-title and tag-page-description fixes are systemic (one template, hundreds of pages). The remaining ~104 audit hits are all source-authored content (article raw titles too long, article `summary` frontmatter too long, fieldkit/artifact descriptions too long, one /about description) and require either: (a) source-side rewrites + sync, or (b) a destination-only override layer.

### Done — 2026-05-16 (earlier session — HIGH cluster fix)

**Audit delta: 333 → 303 issues (-30 resolved, 0 regressions).** Verified via `node .claude/skills/seo-monitor/scripts/audit_site.mjs`. Detail: title-issues 67→49 (-18), description-issues 262→250 (-12), trailing-slash hits unchanged at 4 (known false positives — now patched in later session).

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
| ~~HIGH~~ | ~~Rewrite KV-cache article title (95→≤65) + description (228→70–160)~~ | resolved 2026-05-16 final session — template-level smart-truncate + `truncateForMeta` | — | Meta `<title>` and `<meta description>` now condensed at the template layer; visible `<h1>` and on-page `<p class="article__summary">` still show the synced author prose |
| HIGH | Lengthen book chapter `description:` and `subtitle:` front-matter | `src/data/book/chapters/*.md` (synced from product) | user (authored content) | These come from the product source. Edit there, then `apply-book-update` syncs in. The programmatic builder at `src/pages/book/[...slug].astro:79-87` already produces 70–160 char descriptions from `title + subtitle + chapter number + author` — only matters if audit window/rules tighten |
| ~~MED~~ | ~~Rewrite ~37 field-notes article titles >65ch~~ | resolved 2026-05-16 final session | — | `shortenTitle()` in article template splits on em-dash / colon / `?!` and picks the longest head that fits +SUFFIX in 65. 39 of 39 cleared |
| ~~MED~~ | ~~Trim ~54 field-notes article descriptions >200ch~~ | resolved 2026-05-16 final session | — | `truncateForMeta()` in article template word-boundary-cuts to ≤160 with `…` ellipsis. 53 of 53 cleared. JSON-LD `description: summary` and ArticleCard listings still show full synced text |
| ~~MED~~ | ~~Trim 6 fieldkit landing/API descriptions + 4 artifacts descriptions + 1 /about description~~ | resolved 2026-05-16 latest session — see Done block above | — | All 12 dest-fixable items shipped via layout/template edits + meta-only truncator on fieldkit/api/[module]/ |
| ~~LOW~~ | ~~Verify intentional noindex on `/field-notes/series/autoresearch/`~~ | resolved 2026-05-16 latest session | — | Astro redirect (slug rename to `machine-that-builds-machines`) — meta-refresh + noindex is the correct GitHub-Pages pattern; declared in `astro.config.*` `redirects:` block |
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
