# Fix Taxonomy

The full catalog of SEO checks `audit_site.mjs` performs and the repair recipe for each. The `class` column determines whether `seo-monitor` will apply the fix automatically (after user approval) or surface it for the user to do manually.

**`auto`** — `seo-monitor`'s Execute Phase will edit code on user approval.
**`console`** — surfaced as a manual task. The skill never automates these because (a) they require authored content (meta descriptions), (b) they're better done in Google's UI (request indexing), or (c) the fix is too contextual for safe automation (title rewrites).

## Catalog

| # | Check ID | Detector | File glob | Repair recipe | Class |
|---|----------|----------|-----------|---------------|-------|
| 1 | `missing-meta-description` | `<head>` lacks `<meta name="description">` or content is empty | `dist/**/*.html` → trace back to `src/pages/**/*.{md,mdx,astro}` | Write a 70–160 char description from scratch matching the article's tone. Never auto-derive from page content. | console |
| 2 | `description-length-out-of-range` | `<meta name="description">` content length < 70 or > 160 chars | same | Rewrite description to fit window. Author judgment, not mechanical. | console |
| 3 | `missing-title` | `<title>` element missing or empty | same | Add `title:` to front-matter. The skill can identify the missing slot but won't invent the title — surface. | console |
| 4 | `title-length-out-of-range` | `<title>` text length < 25 or > 65 chars | same | Author judgment. | console |
| 5 | `missing-canonical` | `<link rel="canonical">` absent | same | Astro's Layout.astro emits canonical from `Astro.url.pathname` automatically — if a page lacks it, the page is bypassing Layout. Surface for inspection. | console |
| 6 | `canonical-mismatch` | Canonical href != current page URL or points off-site | same | Likely a hand-coded override in front-matter. Surface for review. | console |
| 7 | `noindex-on-indexable-page` | `<meta name="robots" content="noindex">` on a page listed in the sitemap | same | The page is in the sitemap but says "don't index" — contradictory. Either remove noindex or exclude from sitemap in `astro.config.mjs:55-80`. | auto (sitemap exclusion is mechanical; noindex tag removal requires inspection — surface those) |
| 8 | `missing-og-image` | `<meta property="og:image">` absent | same | Set `ogImage:` in front-matter pointing to an existing image in `public/og/` matching the slug, or a category default. | auto (only if a matching `/og/<slug>.png` exists in `public/og/`; otherwise surface) |
| 9 | `json-ld-parse-error` | `<script type="application/ld+json">` content fails `JSON.parse` | same | A JSON-LD block is malformed. Surface — usually means a templating bug in `JsonLd.astro` or a layout. | console |
| 10 | `article-jsonld-missing` | `/field-notes/<slug>/` page lacks Article or TechArticle JSON-LD | `dist/field-notes/**/*.html` → `src/pages/field-notes/[slug].astro` | The slug-route layout should always emit Article JSON-LD. If missing, the layout's type guard is broken. Patch the type guard. | auto |
| 11 | `redirect-chain-depth-gt-1` | A target of one redirect is itself a redirect source (chain) | `astro.config.mjs:35-44` redirect map | Flatten the chain so every source points directly to the final destination. | auto |
| 12 | `sitemap-priority-drift` | A page's calculated priority disagrees with the rules in `astro.config.mjs:55-80` | `dist/sitemap-0.xml` ∩ `astro.config.mjs` | Reconcile by editing the `serialize()` rule (the audit script knows the rule and the actual emitted value). | auto |
| 13 | `internal-href-missing-trailing-slash` | An `<a href="/foo">` (or in source: `href="/foo"`) without trailing slash | `src/**/*.{astro,tsx,ts,mdx}` | Append `/`. Trailing slashes are mandatory per `trailingSlash: 'always'`. Skip external URLs and anchor-only hrefs. | auto |
| 14 | `person-jsonld-missing-or-stale` | Layout emits Person JSON-LD that doesn't match `src/data/seo.ts:PERSON` | `dist/**/*.html` ∩ `src/data/seo.ts` | The Layout.astro should source from `PERSON`. If a page hardcodes Person fields, refactor to source from `seo.ts`. | auto (if simple inline → import refactor) |

## Join recipes (cross-reference Step 8)

The leverage of `seo-monitor` is joining GSC/GA findings with the local audit. These joins drive ranking:

| Join | Confidence | Resulting fix |
|------|-----------|---------------|
| GSC `crawled_not_indexed` URL ∩ check #1 (`missing-meta-description`) | high | Surface check #1 as `console` (described above), tag it high priority |
| GSC `crawled_not_indexed` URL ∩ check #8 (`missing-og-image`) | high | Apply check #8 `auto` if /og asset exists; surface otherwise |
| GSC `discovered_not_indexed` URL ∩ check #5 (`missing-canonical`) | medium | Surface for review |
| GSC `discovered_not_indexed` URL ∩ check #10 (`article-jsonld-missing`) | high | Apply check #10 `auto` |
| GSC `duplicate_no_canonical` URL ∩ check #6 (`canonical-mismatch`) | high | Surface — the user picked the wrong canonical |
| GA low-engagement landing page ∩ check #4 (`title-length-out-of-range`) | medium | Surface check #4 `console` |
| GA low-engagement landing page ∩ check #2 (`description-length-out-of-range`) | medium | Surface check #2 `console` |
| PSI poor LCP page ∩ check from `pagespeed-playbook.md` audit table (LCP element / image audits) | high | Surface for review — specific to the LCP element identified by Lighthouse |
| GSC `redirect` count growing ∩ check #11 (`redirect-chain-depth-gt-1`) | high | Apply check #11 `auto` — flatten chains |
| Sitemap last-read > 14d ∩ new pages in `dist/` since last read | medium | Surface `console` action: resubmit sitemap |
| Any local-audit issue without GSC/GA signal | low | Surface, but rank below joined fixes |

The "low / medium / high" confidence is informational — all fixes still go through the single approval gate. Confidence shapes the proposed-fixes order so the gate question is easy to scan.

## Stale flag rules

Stale flagging lives in `references/issue-history.md`. The rules:

- **First sight** — issue added to history with status `new`.
- **Second consecutive run** — status `stale`. (Two snapshots, same issue, still unfixed.)
- **Third consecutive run** — status `manual-review-needed`. Surface prominently in the plan output; consider removing the page or rewriting it.
- **Resolved** — issue no longer surfaces in the current run; the most recent history row stays but isn't re-printed.

"Consecutive" means appearing in the immediately prior snapshot. If an issue skips a run (because that run had `Status: partial` on GA), don't reset the count — preserve continuity. (The history script handles this — see `diff_snapshot.mjs`.)

## What this taxonomy intentionally omits

- **Mobile-friendliness rules** — covered by PSI accessibility score.
- **Schema.org type completeness beyond Article/Person/Breadcrumb** — diminishing returns; current Layout.astro coverage is strong.
- **Image alt-text coverage** — `audit_site.mjs` could check this, but Astro markdown alt-text comes from author intent. Better surfaced via PSI accessibility audits.
- **Internal link graph analysis (orphan pages, link depth)** — would be valuable but expensive to compute. Possible v2.
- **Competitor analysis** — explicitly out of scope per the plan.
- **Conversion-funnel from GA4** — landing-page traction is the v1 surface.
