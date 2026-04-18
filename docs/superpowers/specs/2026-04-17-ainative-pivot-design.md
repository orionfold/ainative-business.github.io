# ainative.business pivot — design

**Date:** 2026-04-17
**Author:** Manav Sehgal (with Claude Code)
**Status:** Approved, ready for implementation plan

## Why

Reposition the project to strengthen two things at once:

1. **Trademark defensibility.** "AI Native" is descriptive enough that nobody can strongly own it — including challengers. "Stagent" was distinctive and therefore both ownable and challengeable.
2. **The "personal research project" thesis.** Anchoring the public identity to the book (*AI Native Business*) and framing the software as the book's companion artifact makes it legibly a research project, not a product.

The project is 30 days old with effectively zero inbound link graph, so the rename has near-zero historical cost. A short transitional 301 from stagent.io covers the few places the old domain has been shared.

## What changes vs. what does not

**Changes:** domain, brand surface (product name, package names, hero copy, SEO metadata, social links), in-narrative book/research prose, repo names.

**Does not change:** runtime behavior of the companion software; install flow; docs subsite structure; book chapter structure or content beyond name substitution; newsletter ("AI Native research"); Maven cohort relationship (one-way); pricing model (still free, Apache 2.0).

This is a **narrative pivot, not a product pivot.**

## Naming & identity

| Surface | Before | After |
|---|---|---|
| Domain | `stagent.io` | `ainative.business` |
| Product / CLI | `Stagent` / `stagent` | `ainative` (always lowercase, even at sentence start unless grammar requires capitalization, in which case "Ainative") |
| npm package — CLI | `stagent` | `ainative` (verified available on registry) |
| npm package — website | `stagent-website` | `ainative-business-website` |
| GitHub Pages (website) repo | `manavsehgal/stagent.github.io` | `manavsehgal/ainative-business.github.io` |
| GitHub product (code) repo | `manavsehgal/stagent` | `manavsehgal/ainative` (renamed in a parallel session — see Out of scope) |
| Hero H1 | "AI Native for everyone." | **"AI Native Business"** (book title) |
| Hero subtitle | "A personal research into building and working with AI agents. Free and open source." | **"The book and the companion software. A personal research project by Manav Sehgal. Free and open source."** |
| Terminal CTA label | "Try Stagent community edition now" | "Try the companion software" |
| Terminal command | `npx stagent` | `npx ainative` |
| Nav logo text | "Stagent" | **"ainative"** (lowercase; reinforces CLI identity, keeps nav compact) |
| Social link in JSON-LD `sameAs` | `https://x.com/stagent` | `https://x.com/manavsehgal` |

## Domain & redirect

**`ainative.business` setup:**
- `public/CNAME` becomes `ainative.business`.
- DNS: apex + `www` to GitHub Pages IPs (185.199.108.153 / .109.153 / .110.153 / .111.153) and `www` CNAME to `manavsehgal.github.io`.
- TLS: GitHub Pages auto-provisions via Let's Encrypt.

**`stagent.io` redirect (path-preserving):**
- Create a new minimal repo `manavsehgal/stagent-io-redirect` to host the redirect shell. (The old `stagent.github.io` repo gets renamed to `ainative-business.github.io` and serves the new site, so it can no longer also serve the old domain.)
- Redirect repo contents:
  - `CNAME` file containing `stagent.io`.
  - A single `index.html` that:
    - Sets `<meta http-equiv="refresh" content="0; url=https://ainative.business/">` for non-JS clients.
    - Sets `<link rel="canonical" href="https://ainative.business/">`.
    - Runs `<script>location.replace('https://ainative.business' + location.pathname + location.search + location.hash)</script>` so any deep link is preserved.
- DNS for `stagent.io` continues to point to GitHub Pages IPs; GitHub associates the domain with the redirect repo via its CNAME file.
- HTTP 301 semantics are emulated via meta-refresh + canonical (GitHub Pages cannot emit a true 3xx). For SEO purposes this is treated as a permanent move because of the canonical link.
- Maintain stagent.io domain registration for at least 12 months. Re-evaluate at month 11.

## GitHub repository moves

**In scope for this spec:**
1. Rename `manavsehgal/stagent.github.io` → `manavsehgal/ainative-business.github.io`. GitHub auto-redirects all old repo URLs and clones permanently. After rename, update the repo's `CNAME` file from `stagent.io` to `ainative.business`.
2. Create `manavsehgal/stagent-io-redirect` as the new redirect shell repo (CNAME = `stagent.io`, single meta-refresh `index.html`). See Domain & redirect.
3. Update all `https://github.com/manavsehgal/stagent` URLs in the website source (Nav, Footer, About, JSON-LD `sameAs`) to `https://github.com/manavsehgal/ainative`. These references will resolve correctly once the parallel-session rename of the product code repo lands.

**Out of scope (handled separately):**
- Renaming `manavsehgal/stagent` → `manavsehgal/ainative` is performed in a parallel session against the product code repo. This spec only updates the website's *references* to that URL. The two renames must both land before deploy so that visitors clicking "GitHub" on the new site reach a live repo.

## Site & information architecture

**Approach: book-first homepage, companion-software second-act below** (Approach A from brainstorming).

**Homepage hero:**
- H1 becomes the book title "AI Native Business".
- Subtitle reframed (see naming table above).
- Primary CTA: **"Read the book"** linking to `/book/`.
- Secondary CTA: newsletter signup ("AI Native research").
- Tertiary CTA: `npx ainative` terminal block.
- `BusinessConstellation.astro` diagram retained; its link target shifts from `/research/` to `/book/`.

**Section order (unchanged):** Hero → Problem → PersonaLanes → Proof → ResearchTeaser → CTAFooter. All sections survive; surrounding copy is reframed so each Stagent-as-product reference becomes ainative-as-companion-to-book.

**Nav:** unchanged structure (Book / Research / Projects / Docs / API / About + GitHub). Logo text changes from "Stagent" to "ainative". Logo image (`/stagent-s-64.png`) renamed to `/ainative-s-64.png`.

## Files touched (mechanical brand renames)

Brand surface (find-replace `Stagent` → `ainative` with manual review for capitalization and grammar):

- `src/data/seo.ts` — SITE, ORGANIZATION, PUBLISHER constants. URL → `https://ainative.business`. Logo paths → `/ainative-s-128.png`. `sameAs` array updated (GitHub URL + replace `x.com/stagent` with `x.com/manavsehgal`).
- `src/pages/index.astro` — JSON-LD `SoftwareApplication.name` → `ainative`. FAQPage entries (4 questions) reworded.
- `src/pages/about.astro` — 8 instances; preserve existing factual content (credentials, bio, attribution); update brand references only.
- `src/components/Nav.astro` — logo text, logo image src, GitHub URL, `aria-label` ("Stagent home" → "ainative home").
- `src/components/Footer.astro`.
- `src/components/sections/{Hero,Problem,Features,Proof,RuntimeBridge,PersonaLanes,CTAFooter,TechTicker}.astro` — copy and any embedded brand strings.
- `src/components/sections/Pricing.astro` — **deleted** (see Cleanup below).
- `src/layouts/{Layout,BookLayout,DocsLayout,ApiDocsLayout,ResearchLayout}.astro` — title fragments and OG metadata.
- `src/pages/{terms,privacy,projects,confirmed,book/index,book/og,og}.astro`.
- `src/pages/docs/**/*.{astro,mdx}` and `src/pages/docs/api/**/*.{astro,mdx}` — every docs page that references the brand.
- `src/pages/research/{ai-transformation,solo-builder-case-study}.mdx`.
- `src/pages/research/index.astro`.
- `src/data/timeline.ts`.
- `src/lib/book/content.ts`.
- `src/components/book/book-reader.tsx`.
- `src/components/svg/{DetailedArchitecture,GovernanceMatrix,SystemArchitecture,BusinessConstellation}.astro` — embedded labels/text inside SVGs.
- `src/components/ui/WaitlistForm.astro`.
- `public/{CNAME,llms.txt,llms-full.txt,robots.txt,humans.txt,manifest.json}` — manifest `name`/`short_name`, robots `Sitemap:` URL, llms.txt content.
- `astro.config.mjs` — `site:` URL and any base config.
- `package.json` — `name` field → `ainative-business-website`.
- `package-lock.json` — regenerate after `package.json` change.
- `supabase/functions/{confirm-email,waitlist-signup}/index.ts` — email From-name, copy text, any branded URLs.

**Image / asset renames in `public/`:**
- `stagent-s-64.png` → `ainative-s-64.png`
- `stagent-s-128.png` → `ainative-s-128.png`
- Any other `stagent-*.png` in `public/` (favicon variants, OG images): renamed to `ainative-*`.
- Update all `<img src>`, `<link rel="icon">`, `og:image`, and manifest `icons[]` references.

## Book + research content rewrite

**Strategy:** 1:1 substitution of `Stagent` → `ainative` (lowercase always), with manual prose review to preserve voice.

**Conventions:**
- Lowercase `ainative` everywhere mid-sentence, including after periods if sentence starts. (Style note: same convention as `bun`, `npm`, `pnpm`. Acceptable to capitalize as `Ainative` only when grammatical correctness demands it; prefer rephrasing to avoid sentence-initial position.)
- Preserve the factory-as-character literary device. Example: chapter 1 line 167 *"we'll build a working factory — Stagent — that demonstrates the patterns"* becomes *"we'll build a working factory — ainative — that demonstrates the patterns"*.

**Files:**
- `src/data/book/chapters/ch-1-from-hierarchy-to-intelligence.md` (1)
- `src/data/book/chapters/ch-2-the-ai-native-blueprint.md` (9)
- `src/data/book/chapters/ch-3-the-refinery.md` (10)
- `src/data/book/chapters/ch-4-the-forge.md` (8)
- `src/data/book/chapters/ch-5-blueprints.md` (9)
- `src/data/book/chapters/ch-6-the-arena.md` (6)
- `src/data/book/chapters/ch-7-institutional-memory.md` (5)
- `src/data/book/chapters/ch-8-the-swarm.md` (7)
- `src/data/book/chapters/ch-9-the-governance-layer.md` (9)
- `src/data/book/chapters/ch-10-the-world-model.md` (18)
- `src/data/book/chapters/ch-11-the-machine-that-builds-machines.md` (21)
- `src/data/book/chapters/ch-12-the-road-ahead.md` (8)
- `src/data/book/chapters/ch-13-the-wealth-manager.md` (27)
- `src/data/book/chapters/ch-14-the-meta-program.md` (43)
- `research/solo-builder-case-study.md` (30)

After rewrite: per-chapter visual diff review to catch capitalization mistakes, broken sentence flow, and any spots where "the Stagent runtime" reads worse than "the ainative runtime" and benefits from rephrasing.

## Skills rename

- Rename directory `.claude/skills/stagent-stats/` → `.claude/skills/ainative-stats/`. Update `SKILL.md` frontmatter `name:` field and all body references (29 instances).
- Update body text in `.claude/skills/apply-book-update/SKILL.md` (14 references).
- Update body text in `.claude/skills/deck/SKILL.md` (17 references).
- Update body text in `.claude/skills/apply-api-docs/SKILL.md` (12 references).
- Rename root file `stagent-stats.md` → `ainative-stats.md`. Update internal references (1).

## Historical internal docs

The repo contains prior design docs and plans under `docs/superpowers/specs/` and `docs/superpowers/plans/` that reference Stagent (5 files, ~26 references). These are internal artifacts documenting past design decisions, not user-facing content.

**Decision:** rewrite them in-place using the same 1:1 substitution rule as book chapters. Rationale: (1) keeps verification grep clean and unambiguous; (2) these docs aren't a "publication record" — they're working notes; (3) the *current* spec file (this one) intentionally retains "Stagent" references because it documents the rename, and that's the only doc explicitly excluded from the grep verification.

Files:
- `docs/superpowers/specs/2026-03-31-landing-page-revolution-design.md` (8)
- `docs/superpowers/specs/2026-04-01-hero-constellation-design.md` (6)
- `docs/superpowers/specs/2026-04-01-tech-ticker-design.md` (1)
- `docs/superpowers/specs/2026-04-02-hero-title-revision-design.md` (3)
- `docs/superpowers/plans/2026-04-01-hero-constellation.md` (8)

Excluded from rewrite (intentional Stagent references):
- `docs/superpowers/specs/2026-04-17-ainative-pivot-design.md` (this spec) — describes the rename, must mention both names.

## Cleanup (free wins under the new framing)

**Delete (orphaned / dead weight):**
- `src/pages/pricing.astro` — orphaned route (nothing in Nav or homepage links to it).
- `src/components/sections/Pricing.astro` — only consumed by the deleted page.
- Root-dir dev screenshots (verify each is unreferenced before deleting): `stagent-hero.png`, `stagent-layers.png`, `stagent-orbit.png`, `fynt-bottom.png`, `fynt-features-section.png`, `fynt-features.png`, `fynt-hero-iso-detail.png`, `fynt-hero-iso-zoom.png`, `fynt-hero-top.png`, `fynt-hero.png`, `fynt-templates.png`, `homepage-top.png`, `progress-section.png`, `progress-updated.png`, `velocity-chart-updated.png`.

## Execution approach

**Approach 1: Atomic.** Single PR/commit batch on `main`, executed locally with verification, then deploy + DNS swap + npm publish + GitHub repo rename in close sequence (within an hour).

Rationale: 30-day-old project with near-zero inbound link graph, solo author working on `main` per memory, small total surface (633 references / 105 files / one repo). Phased rollout would visibly leave the site mid-pivot for users; atomic minimizes that exposure window. Any missed reference after deploy is a 5-minute hot-fix on `main`.

## Verification checklist (run before any deploy)

1. `grep -ri "stagent" .` → expect zero matches outside the legitimate exceptions: `.git/`, `node_modules/`, lockfile residue, this spec file (`docs/superpowers/specs/2026-04-17-ainative-pivot-design.md`), and any preserved historical mentions covered by the Historical docs decision below.
2. `grep -ri "stagent\.io" .` → zero matches outside the same exception set.
3. `grep -ri "Stagent" .` → zero matches outside exceptions (catches preserved capitalization).
4. `npm run build` → succeeds; sitemap, OG image generation, slashless duplicate generation all complete without error.
5. Local preview via `preview_start`:
   - Homepage hero shows "AI Native Business" H1; `npx ainative` in terminal block.
   - `/book/` route renders book reader with no Stagent text in chapter prose.
   - `/research/` and `/docs/` render cleanly.
   - `/about/` renders Manav's bio; "ainative & AI Native Business" couplet in card; attribution preserved.
   - `/pricing` returns 404 (route deleted).
   - No broken images (favicon, logo, OG).
6. `preview_screenshot` of homepage hero + book index + about page → visual proof of new branding for the commit.
7. After deploy:
   - `https://ainative.business/` resolves with valid TLS.
   - `https://stagent.io/book/some-chapter` redirects to `https://ainative.business/book/some-chapter` (path preserved).
   - GitHub Pages serves the renamed `ainative-business.github.io` repo at the new domain; the old `stagent.github.io` repo URLs auto-redirect to the new repo URL.
   - The `stagent-io-redirect` repo serves the redirect shell at the old domain.
   - GitHub `https://github.com/manavsehgal/ainative` link in Nav resolves to a live repo (depends on the parallel-session rename landing).

## Out of scope

- Renaming `manavsehgal/stagent` → `manavsehgal/ainative` (product code repo) — performed in a parallel session against the product code repo. This spec only updates the website's *references* to that URL.
- Runtime / install / CLI behavior of `npx ainative` itself — lives in the separate `manavsehgal/ainative` repo, handled in a separate PR there.
- Newsletter list rename or migration in the email backend — already named "AI Native research" per memory.
- Maven cohort messaging — one-way relationship; cohort copy lives outside this repo.
- Trademark filings or legal entity changes — research-project framing is the defensive posture; no legal action proposed.
- Social handle creation or rename (`x.com/ainative`, etc.) — operational task; the website only references `x.com/manavsehgal` going forward.
- README at repo root — none currently exists; not creating one as part of this pivot.
