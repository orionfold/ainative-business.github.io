# ainative.business pivot — implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Atomically rename the website from "Stagent / stagent.io" to "ainative / ainative.business", reframe the homepage as book-first with the companion software second, rewrite all in-narrative book and research prose, rename skills, delete dead code, and prepare the deploy + redirect plan.

**Architecture:** This is a *narrative* pivot, not a *product* pivot. The runtime/install/CLI behavior of the companion software is unchanged. Work is concentrated in: SEO/metadata, brand surfaces in components/pages, in-narrative book + research prose, skills, and a small set of cleanup deletions. All changes land in close-spaced commits on the current worktree branch and are pushed/merged as one PR.

**Tech Stack:** Astro 5, React 19, Tailwind v4, MDX, TypeScript. Static site → GitHub Pages. Supabase Edge Functions for waitlist email. The Claude Preview MCP for verification.

**Companion docs:**
- Spec: [`docs/superpowers/specs/2026-04-17-ainative-pivot-design.md`](../specs/2026-04-17-ainative-pivot-design.md)
- Cross-repo handoff: [`handoff/2026-04-17-ainative-pivot-stagent-repo.md`](../../../handoff/2026-04-17-ainative-pivot-stagent-repo.md)

**Convention used throughout this plan:**
- The new product name is `ainative` — always lowercase, even at sentence start unless grammar absolutely demands `Ainative`. Same convention as `bun`, `npm`, `pnpm`.
- The new domain is `ainative.business`.
- The new GitHub product code repo URL is `https://github.com/manavsehgal/ainative` (renamed in a parallel session — see handoff doc).
- The replacement social handle is `https://x.com/manavsehgal`.

---

### Task 1: Establish baseline and capture pre-pivot screenshots

**Files:** none modified.

- [ ] **Step 1: Confirm git status is clean**

Run:
```bash
git status
```
Expected: `nothing to commit, working tree clean` on branch `claude/bold-bassi-5278f5`. The two earlier commits (`fe5fffb` spec, `8dde750` handoff) should be visible in `git log --oneline -5`.

- [ ] **Step 2: Run baseline grep to confirm starting count of Stagent references**

Run:
```bash
grep -ric "stagent" --exclude-dir=node_modules --exclude-dir=.git --exclude-dir=dist --exclude-dir=.astro . 2>/dev/null | awk -F: '{s+=$2} END {print s}'
```
Expected: a number around 600 (baseline was 633 across 105 files at brainstorm time; the spec + handoff added some legitimate references).

- [ ] **Step 3: Start dev server**

Use the `mcp__Claude_Preview__preview_start` tool with `command: "npm run dev"` and `cwd: "/Users/manavsehgal/Developer/stagent.github.io/.claude/worktrees/bold-bassi-5278f5"`.

Wait until the preview reports a usable URL (Astro dev server ready).

- [ ] **Step 4: Capture pre-pivot screenshots for visual diff comparison**

Use `mcp__Claude_Preview__preview_screenshot` for these routes (one screenshot per route):
- `/` (homepage)
- `/about/`
- `/book/`

These are the proof-of-state-before for the eventual commit message. They are not committed; they are kept in conversation only.

- [ ] **Step 5: Stop the dev server before mutations**

Use `mcp__Claude_Preview__preview_stop`. (We restart fresh after the rewrites so HMR doesn't get confused by mass file changes.)

---

### Task 2: Rewrite SEO core (`src/data/seo.ts`)

**Files:** Modify `src/data/seo.ts`.

This file is the single source of truth for site name, URL, OG image, organization JSON-LD, and publisher JSON-LD. Most other SEO surfaces import from it.

- [ ] **Step 1: Rewrite the file completely**

Replace the entire contents of `src/data/seo.ts` with:

```typescript
export const SITE = {
  name: 'ainative',
  url: 'https://ainative.business',
  description:
    'AI Native Business — the book and the companion software. A personal research project by Manav Sehgal into building AI-native businesses. Open source, local-first, and free.',
  logo: 'https://ainative.business/ainative-s-128.png',
  ogImage: 'https://ainative.business/og-image.png',
  themeColor: '#0f172a',
  license: 'Apache-2.0',
};

export const ORGANIZATION = {
  '@type': 'Organization',
  name: 'ainative',
  url: SITE.url,
  logo: SITE.logo,
  description: SITE.description,
  founder: {
    '@type': 'Person',
    name: 'Manav Sehgal',
  },
  foundingDate: '2026',
  sameAs: [
    'https://github.com/manavsehgal/ainative',
    'https://x.com/manavsehgal',
  ],
};

export const PUBLISHER = {
  '@type': 'Organization',
  name: SITE.name,
  url: SITE.url,
  logo: {
    '@type': 'ImageObject',
    url: SITE.logo,
  },
};
```

- [ ] **Step 2: Verify no Stagent references remain in the file**

Run:
```bash
grep -i "stagent" src/data/seo.ts
```
Expected: no output (zero matches).

---

### Task 3: Update domain artifacts (`public/CNAME`, `astro.config.mjs`)

**Files:**
- Modify `public/CNAME`
- Modify `astro.config.mjs:9`

- [ ] **Step 1: Update CNAME**

Replace the contents of `public/CNAME` with:
```
ainative.business
```
(Single line, trailing newline.)

- [ ] **Step 2: Update Astro `site:` URL**

In `astro.config.mjs`, change line 9 from:
```javascript
  site: 'https://stagent.io',
```
to:
```javascript
  site: 'https://ainative.business',
```

- [ ] **Step 3: Verify both files**

Run:
```bash
grep -i "stagent" public/CNAME astro.config.mjs
```
Expected: no output.

---

### Task 4: Update `package.json` and lockfile

**Files:**
- Modify `package.json:2`
- Regenerate `package-lock.json`

- [ ] **Step 1: Rename the package**

In `package.json`, change line 2 from:
```json
  "name": "stagent-website",
```
to:
```json
  "name": "ainative-business-website",
```

- [ ] **Step 2: Regenerate the lockfile**

Run:
```bash
npm install --package-lock-only
```
Expected: completes silently or with no warnings; `package-lock.json` shows the new name as the root package.

- [ ] **Step 3: Verify**

Run:
```bash
grep -c '"stagent-website"' package.json package-lock.json
```
Expected: zero matches in both files.

---

### Task 5: Rename logo assets and update icon source for the renamer

**Files:**
- Rename `public/stagent-s-64.png` → `public/ainative-s-64.png`
- Rename `public/stagent-s-128.png` → `public/ainative-s-128.png`
- Rename `public/stagent-s-512.png` → `public/ainative-s-512.png`

- [ ] **Step 1: Rename the three logo files using `git mv` to preserve history**

Run:
```bash
git mv public/stagent-s-64.png public/ainative-s-64.png && \
git mv public/stagent-s-128.png public/ainative-s-128.png && \
git mv public/stagent-s-512.png public/ainative-s-512.png
```
Expected: three rename operations, no errors.

- [ ] **Step 2: Verify the renamed files exist and the originals do not**

Run:
```bash
ls public/ainative-s-*.png 2>&1; ls public/stagent-s-*.png 2>&1
```
Expected: three `ainative-s-*.png` files listed; "No such file or directory" for `stagent-s-*.png`.

> Note: image *content* still shows the old "S" mark. That's fine for this commit — visual logo replacement is a separate design task. The filenames carry the new brand; the image bytes can be re-rendered later.

---

### Task 6: Update public manifest, llms, robots, humans

**Files:**
- Modify `public/manifest.json`
- Rewrite `public/llms.txt` (and `public/llms-full.txt` similarly — see step 4)
- Modify `public/robots.txt`
- Modify `public/humans.txt`

- [ ] **Step 1: Rewrite `public/manifest.json`**

Replace the entire contents with:

```json
{
  "name": "ainative",
  "short_name": "ainative",
  "description": "Companion software for the AI Native Business book. Local-first builder scaffold for AI-native businesses.",
  "start_url": "/",
  "display": "browser",
  "background_color": "#0f172a",
  "theme_color": "#0f172a",
  "icons": [
    {
      "src": "/ainative-s-64.png",
      "type": "image/png",
      "sizes": "64x64"
    },
    {
      "src": "/ainative-s-128.png",
      "type": "image/png",
      "sizes": "128x128"
    },
    {
      "src": "/ainative-s-512.png",
      "type": "image/png",
      "sizes": "512x512"
    }
  ]
}
```

- [ ] **Step 2: Rewrite `public/llms.txt`**

Replace the entire contents with:

```
# ainative

> Companion software for the AI Native Business book by Manav Sehgal. A personal research project exploring what it takes to build AI-native businesses on a shoestring. Local-first, open source, free.

## About

ainative is a builder scaffold for AI-native businesses. It pairs with the AI Native Business book — a 14-chapter playbook for autonomous business systems — and gives readers a working factory to study and extend. Same runtime, same governance, same local-first architecture as before.

### Five Differentiation Pillars

1. **Long-Horizon Task Persistence** — Tasks that survive beyond sessions with checkpoint/resume, progress tracking, failure recovery, and per-task resource budgets.
2. **Multi-Model Orchestration** — Routes subtasks to the best available model (Claude, GPT, Gemini, Grok, Ollama) based on measured performance.
3. **Memory-Native Architecture** — Four-tier hierarchical memory (working, episodic, semantic, procedural) with hybrid retrieval (BM25 + vector + MMR).
4. **Graduated Autonomy** — Trust earned through demonstrated competence. Supervised → semi-autonomous → autonomous, scoped per-agent-type, per-task-type, per-risk-level.
5. **Hybrid Execution** — Desktop-native with cloud reach. Same task graph runs locally or in the cloud with state portability.

### Technology Stack

- **Backend**: Rust (Tauri), WASM sandboxing (Wasmtime), SQLite (rusqlite)
- **Frontend**: TypeScript, React, React Flow (task DAG canvas)
- **Protocols**: MCP, A2A, CDP, WebMCP, Tauri IPC, WebSocket
- **AI Providers**: Anthropic Claude, OpenAI, Google Gemini, Ollama

### Status

- License: Apache 2.0
- Stage: Pre-alpha (active development)
- Author: Manav Sehgal

## Documentation

- [Homepage](https://ainative.business): Book + companion software overview, architecture, research
- [The Book](https://ainative.business/book/): AI Native Business — the 14-chapter playbook
- [Research](https://ainative.business/research/): Solo-builder case study and supporting research papers

## Source Code

- [GitHub Repository](https://github.com/manavsehgal/ainative)

## Optional

- [Sitemap](https://ainative.business/sitemap-index.xml)
```

- [ ] **Step 3: Rewrite `public/llms-full.txt`**

Read the current contents:
```bash
wc -l public/llms-full.txt
```

Open it with the Read tool. It is the same shape as `llms.txt` but expanded with chapter summaries. Apply the same substitutions:
- Replace every `Stagent` and `stagent` with `ainative` (lowercase, never sentence-initial without a leading "The ").
- Replace every `https://stagent.io` with `https://ainative.business`.
- Replace `https://github.com/manavsehgal/stagent` with `https://github.com/manavsehgal/ainative`.
- Reframe any product-positioning copy to book-companion language consistent with `llms.txt` above.

Use the Edit tool with `replace_all: true` for each of the three string substitutions, then a manual read pass for any positioning copy that needs reframing.

- [ ] **Step 4: Update `public/robots.txt`**

Open the file. Find the `Sitemap:` line referencing `https://stagent.io/...` and replace `stagent.io` with `ainative.business`. There is exactly 1 stagent reference in this file per baseline grep.

- [ ] **Step 5: Update `public/humans.txt`**

Open the file. Replace the 3 stagent references using Edit with `replace_all: true` for `stagent.io` → `ainative.business` and `Stagent` → `ainative` as appropriate.

- [ ] **Step 6: Verify all `public/` files**

Run:
```bash
grep -ri "stagent" public/
```
Expected: no output.

---

### Task 7: Rewrite `src/components/Nav.astro`

**Files:** Modify `src/components/Nav.astro`.

Five surfaces in this file: aria-label, logo image src, logo text span, GitHub link, mobile-menu GitHub link.

- [ ] **Step 1: Update the desktop logo block**

In the `<a href="/" ...>` block at lines 7-22:
- Change `aria-label="Stagent home"` to `aria-label="ainative home"`.
- Change `src="/stagent-s-64.png"` to `src="/ainative-s-64.png"`.
- Change the span text `Stagent` to `ainative`.

- [ ] **Step 2: Update the desktop GitHub link**

In the `<a href="https://github.com/manavsehgal/stagent" ...>` block around lines 65-75, change the URL to `https://github.com/manavsehgal/ainative`.

- [ ] **Step 3: Update the mobile-menu GitHub link**

In the `<a href="https://github.com/manavsehgal/stagent" ...>` block around line 114, change the URL to `https://github.com/manavsehgal/ainative`.

- [ ] **Step 4: Verify**

Run:
```bash
grep -i "stagent" src/components/Nav.astro
```
Expected: no output.

---

### Task 8: Rewrite `src/components/Footer.astro`

**Files:** Modify `src/components/Footer.astro`.

- [ ] **Step 1: Read the file and identify the Stagent reference**

Use the Read tool on `src/components/Footer.astro`. Baseline grep showed 1 reference. Identify whether it is the brand name in copyright text, a logo, or another surface.

- [ ] **Step 2: Apply substitution preserving voice**

Use Edit:
- If brand text: replace `Stagent` with `ainative`.
- If a URL: replace `stagent.io` with `ainative.business`.
- If a copyright line, ensure the year and "Manav Sehgal" attribution are intact.

- [ ] **Step 3: Verify**

Run:
```bash
grep -i "stagent" src/components/Footer.astro
```
Expected: no output.

---

### Task 9: Rewrite the Hero — book-first IA + new copy

**Files:** Modify `src/components/sections/Hero.astro`.

Per the spec (Section "Site & information architecture"), the Hero shifts from product-first to book-first. Two stagent references to remove plus the H1, subtitle, and CTA copy changes.

- [ ] **Step 1: Update the H1**

Find at line 22-26:
```html
<h1
  class="hero-gradient-text font-display text-[clamp(1.6rem,3vw,2.3rem)] font-bold leading-[1.15] mb-3"
>
  AI Native for everyone.
</h1>
```
Replace the inner text `AI Native for everyone.` with `AI Native Business`.

- [ ] **Step 2: Update the subtitle**

Find at line 28-32:
```html
<p
  class="text-[clamp(0.85rem,1.8vw,1.05rem)] text-text-muted leading-relaxed mb-5 mx-auto lg:mx-0 max-w-xl"
>
  A personal research into building and working with AI agents. Free and open source.
</p>
```
Replace the inner text with:
`The book and the companion software. A personal research project by Manav Sehgal. Free and open source.`

- [ ] **Step 3: Update the terminal CTA label**

Find at line 65-67:
```html
<p data-animate class="font-mono text-[10px] tracking-[0.2em] uppercase text-text-muted mt-10 mb-2 max-w-sm mx-auto lg:mx-0">
  Try Stagent community edition now
</p>
```
Replace the inner text with: `Try the companion software`.

- [ ] **Step 4: Update the terminal command**

Find at line 87:
```html
<pre class="font-mono text-lg sm:text-xl leading-relaxed text-text-muted"><span class="text-primary">$</span> <code id="hero-code">npx stagent</code><span class="hero-cursor">▌</span></pre>
```
Replace `npx stagent` with `npx ainative`.

- [ ] **Step 5: Update the architecture diagram link target**

Find at line 95:
```html
<a href="/research/" data-animate class="hero-arch-wrapper block hover:opacity-90 transition-opacity cursor-pointer" style="transition-delay: 200ms" aria-label="View research">
```
Change `href="/research/"` to `href="/book/"` and `aria-label="View research"` to `aria-label="Read the book"`.

- [ ] **Step 6: Verify**

Run:
```bash
grep -i "stagent" src/components/sections/Hero.astro
```
Expected: no output.

---

### Task 10: Rewrite remaining section components

**Files:** Modify these files (1-9 stagent references each per baseline grep):
- `src/components/sections/Problem.astro` (1)
- `src/components/sections/PersonaLanes.astro` (2)
- `src/components/sections/Proof.astro` (1)
- `src/components/sections/Features.astro` (1)
- `src/components/sections/RuntimeBridge.astro` (9)
- `src/components/sections/CTAFooter.astro` (3)
- `src/components/sections/TechTicker.astro` (1)

Note: `src/components/sections/Pricing.astro` is **deleted** in Task 23 — do not edit it here.

- [ ] **Step 1: For each file in the list, perform the same substitution sequence**

For each file, in order:
1. Read the file.
2. Apply Edit with `replace_all: true`:
   - `Stagent` → `ainative`
   - `stagent.io` → `ainative.business` (if any URLs)
   - `https://github.com/manavsehgal/stagent` → `https://github.com/manavsehgal/ainative` (if any)
3. Re-read for context-sensitive copy that needs reframing (e.g., "Stagent helps you..." may need to become "ainative is the companion software that helps you..." rather than just "ainative helps you...").
4. Verify with `grep -i "stagent" <filepath>` → expect zero matches.

- [ ] **Step 2: Final verification across all section files**

Run:
```bash
grep -ri "stagent" src/components/sections/ --exclude="Pricing.astro"
```
Expected: no output.

---

### Task 11: Rewrite layouts

**Files:** Modify (1-6 stagent references each):
- `src/layouts/Layout.astro` (6)
- `src/layouts/BookLayout.astro` (1)
- `src/layouts/DocsLayout.astro` (1)
- `src/layouts/ApiDocsLayout.astro` (1)
- `src/layouts/ResearchLayout.astro` (2)

- [ ] **Step 1: For each file, apply substitutions**

Same procedure as Task 10:
1. Read the file.
2. Edit with `replace_all: true` for the standard substitutions.
3. For `Layout.astro` (6 references — likely `<title>` defaults, OG meta defaults, Twitter card defaults), pay extra attention to title-tag patterns. Where you see ` — Stagent`, replace with ` — ainative`. Where you see `Stagent —`, replace with `ainative —`.

- [ ] **Step 2: Verify**

Run:
```bash
grep -ri "stagent" src/layouts/
```
Expected: no output.

---

### Task 12: Rewrite top-level pages

**Files:** Modify:
- `src/pages/about.astro` (8)
- `src/pages/projects.astro` (1)
- `src/pages/terms.astro` (26)
- `src/pages/privacy.astro` (13)
- `src/pages/confirmed.astro` (2)
- `src/pages/og.astro` (4)
- `src/pages/book/og.astro` (1)
- `src/pages/book/index.astro` (2)

- [ ] **Step 1: Special handling for `src/pages/about.astro`**

This page has prose that already aligns with the book-companion framing. Apply substitutions but keep the exact factual content (credentials, bio, attribution paragraph). Specifically:
- Title tag: `"About — Stagent"` → `"About — ainative"`.
- Description: rewrite to: `"ainative is a personal research project by Manav Sehgal — the companion software for the AI Native Business book."`.
- The right-side card text `Stagent &amp; AI Native Business` → `ainative &amp; AI Native Business`.
- The "Short version" aside: `Stagent is a personal research project exploring what it takes to build AI-native on a shoestring budget over weekends.` → `ainative is a personal research project exploring what it takes to build AI-native on a shoestring budget over weekends.`
- The "Why Stagent" h2: `Why Stagent` → `Why ainative`.
- Inside that section: `Stagent is a personal research project exploring what an AI-native operating system looks like.` → `ainative is a personal research project exploring what an AI-native operating system looks like.`
- The "Attribution" section: `Stagent and AI Native Business are personal works of Manav Sehgal...` → `ainative and AI Native Business are personal works of Manav Sehgal...`
- The GitHub link `https://github.com/manavsehgal/stagent` → `https://github.com/manavsehgal/ainative`.
- The waitlist source string `source="research-newsletter"` is unchanged (it's an internal identifier).

- [ ] **Step 2: For the other 7 pages, mechanical substitution**

For each remaining page in the file list:
1. Read the file.
2. Edit with `replace_all: true` for `Stagent` → `ainative`, `stagent.io` → `ainative.business`, and `https://github.com/manavsehgal/stagent` → `https://github.com/manavsehgal/ainative`.
3. For `terms.astro` and `privacy.astro` (high reference counts), do a final read-pass to catch any awkward sentence-start capitalizations that need rephrasing.

- [ ] **Step 3: Verify**

Run:
```bash
grep -ri "stagent" src/pages/about.astro src/pages/projects.astro src/pages/terms.astro src/pages/privacy.astro src/pages/confirmed.astro src/pages/og.astro src/pages/book/og.astro src/pages/book/index.astro
```
Expected: no output.

---

### Task 13: Rewrite `src/pages/index.astro` (homepage JSON-LD + FAQs)

**Files:** Modify `src/pages/index.astro`.

This file has 9 stagent references and a critical JSON-LD block including a FAQPage with brand-specific Q&A.

- [ ] **Step 1: Rewrite the SoftwareApplication name**

Find at line 29:
```javascript
    name: 'Stagent',
```
Replace with:
```javascript
    name: 'ainative',
```

- [ ] **Step 2: Rewrite the FAQ entries**

In the FAQPage block (lines 53-90 area), rewrite each Q&A:

- Q1 (`name: 'What is Stagent?'`) →
  - name: `'What is ainative?'`
  - text: `'ainative is the companion software for the AI Native Business book by Manav Sehgal. It is a local-first builder scaffold that lets you run AI agents across marketing, sales, and operations with governed execution, reusable profiles, workflow blueprints, and human-in-the-loop oversight.'`

- Q2 (`name: 'What makes Stagent different from other AI agent tools?'`) →
  - name: `'What makes ainative different from other AI agent tools?'`
  - text: `'ainative is the only book-companion platform combining full-stack agent orchestration with enterprise-grade governance. It supports 6 AI runtimes, 56+ specialist agent profiles, 37 workflow patterns, multi-channel delivery, chat system, heartbeat scheduling, and a local-first architecture that keeps your data on your machine. Every feature is free and unlimited — no tiers, no paywalls.'`

- Q3 (`name: 'What technology stack does Stagent use?'`) →
  - name: `'What technology stack does ainative use?'`
  - text: `'ainative is built with Next.js 16, React 19, TypeScript, Tailwind CSS v4, shadcn/ui, SQLite via Drizzle ORM, and governed runtime integrations for both the Claude Agent SDK and OpenAI Codex App Server.'`

- Q4 (`name: 'Is Stagent open source?'`) →
  - name: `'Is ainative open source?'`
  - text: `'Yes, ainative is fully open source under the Apache 2.0 license.'`

- [ ] **Step 3: Verify**

Run:
```bash
grep -i "stagent" src/pages/index.astro
```
Expected: no output.

---

### Task 14: Rewrite the docs subsite (`src/pages/docs/`)

**Files:** Modify all docs pages with stagent references:
- `src/pages/docs/documents.mdx` (3)
- `src/pages/docs/index.astro` (3)
- `src/pages/docs/schedules.mdx` (1)
- `src/pages/docs/tables.mdx` (2)
- `src/pages/docs/projects.mdx` (2)
- `src/pages/docs/agents.mdx` (5)
- `src/pages/docs/monitoring.mdx` (2)
- `src/pages/docs/inbox.mdx` (4)
- `src/pages/docs/costs.mdx` (2)
- `src/pages/docs/profiles.mdx` (3)
- `src/pages/docs/chat.mdx` (2)
- `src/pages/docs/environment.mdx` (1)
- `src/pages/docs/dashboard.mdx` (3)
- `src/pages/docs/workflows.mdx` (3)
- `src/pages/docs/tasks.mdx` (3)
- `src/pages/docs/settings.mdx` (4)

- [ ] **Step 1: Mechanical substitution per file**

For each file in the list:
1. Read the file.
2. Edit with `replace_all: true`:
   - `Stagent` → `ainative`
   - `stagent.io` → `ainative.business`
   - `https://github.com/manavsehgal/stagent` → `https://github.com/manavsehgal/ainative`

- [ ] **Step 2: Bulk verification**

Run:
```bash
grep -ri "stagent" src/pages/docs/ --exclude-dir=api
```
Expected: no output.

---

### Task 15: Rewrite the API docs subsite (`src/pages/docs/api/`)

**Files:** Modify all API docs pages with stagent references:
- `src/pages/docs/api/index.astro` (3)
- `src/pages/docs/api/workspace.mdx` (10)
- `src/pages/docs/api/profiles.mdx` (14)
- `src/pages/docs/api/channels.mdx` (4)
- `src/pages/docs/api/blueprints.mdx` (4)
- `src/pages/docs/api/instance.mdx` (5)
- `src/pages/docs/api/uploads.mdx` (1)
- `src/pages/docs/api/settings.mdx` (2)
- `src/pages/docs/api/tasks.mdx` (2)
- `src/pages/docs/api/runtimes.mdx` (2)
- `src/pages/docs/api/environment.mdx` (2)
- `src/pages/docs/api/projects.mdx` (1)
- `src/pages/docs/api/schedules.mdx` (1)
- `src/pages/docs/api/chat.mdx` (1)
- `src/pages/docs/api/documents.mdx` (2)

- [ ] **Step 1: Mechanical substitution per file**

For each file in the list, perform the same Edit-with-`replace_all` procedure as Task 14.

- [ ] **Step 2: Bulk verification**

Run:
```bash
grep -ri "stagent" src/pages/docs/api/
```
Expected: no output.

---

### Task 16: Rewrite research pages and source

**Files:**
- Modify `src/pages/research/index.astro` (6)
- Modify `src/pages/research/ai-transformation.mdx` (9)
- Modify `src/pages/research/solo-builder-case-study.mdx` (39)
- Modify `research/solo-builder-case-study.md` (30)

- [ ] **Step 1: Mechanical substitution per file**

For each of the four files:
1. Read.
2. Edit with `replace_all: true`:
   - `Stagent` → `ainative`
   - `stagent.io` → `ainative.business`
   - `https://github.com/manavsehgal/stagent` → `https://github.com/manavsehgal/ainative`

- [ ] **Step 2: Manual prose review for the two long files**

For `solo-builder-case-study.mdx` (39 references) and `solo-builder-case-study.md` (30 references), do a Read pass after the substitutions. Look for:
- Sentences that begin with `ainative` (lowercase) where capitalization or rephrasing reads more naturally.
- Phrases like "the Stagent runtime" → now reading as "the ainative runtime" — confirm grammatical correctness.
- Any links/URLs that escaped the replace_all due to formatting peculiarities (markdown link syntax, etc.).

- [ ] **Step 3: Verify**

Run:
```bash
grep -ri "stagent" src/pages/research/ research/
```
Expected: no output.

---

### Task 17: Rewrite book chapters (in-narrative prose)

**Files:** Modify all 14 book chapter markdown files in `src/data/book/chapters/`:
- `ch-1-from-hierarchy-to-intelligence.md` (1)
- `ch-2-the-ai-native-blueprint.md` (9)
- `ch-3-the-refinery.md` (10)
- `ch-4-the-forge.md` (8)
- `ch-5-blueprints.md` (9)
- `ch-6-the-arena.md` (6)
- `ch-7-institutional-memory.md` (5)
- `ch-8-the-swarm.md` (7)
- `ch-9-the-governance-layer.md` (9)
- `ch-10-the-world-model.md` (18)
- `ch-11-the-machine-that-builds-machines.md` (21)
- `ch-12-the-road-ahead.md` (8)
- `ch-13-the-wealth-manager.md` (27)
- `ch-14-the-meta-program.md` (43)

- [ ] **Step 1: For each chapter, perform substitution + prose review**

For each chapter file:
1. Read the file.
2. Edit with `replace_all: true` for `Stagent` → `ainative`.
3. Read the file again for prose review. Pay particular attention to:
   - Sentences that begin with the brand name (e.g., "Stagent's runtime..." now reads "ainative's runtime..." — that's fine; the apostrophe-s clarifies). If a sentence now reads as `Ainative does X...` after capitalization, prefer rewording to `The ainative runtime does X...` or similar to keep the lowercase convention.
   - The factory-as-character literary device. Example chapter 1 line 167: `"we'll build a working factory — Stagent — that demonstrates the patterns"` becomes `"we'll build a working factory — ainative — that demonstrates the patterns"`. This reads cleanly with em-dashes; verify after each chapter.
   - Code blocks or fenced blocks where `stagent` appears as a literal command (`npx stagent`, `stagent init`, etc.) — these become `npx ainative`, `ainative init`, etc.

- [ ] **Step 2: Verify each chapter**

After each chapter, run:
```bash
grep -i "stagent" src/data/book/chapters/<filename>
```
Expected: no output for that file.

- [ ] **Step 3: Bulk verification across all chapters**

Run:
```bash
grep -ri "stagent" src/data/book/chapters/
```
Expected: no output.

---

### Task 18: Rewrite SVG components, lib, supabase, book-reader

**Files:**
- `src/components/svg/DetailedArchitecture.astro` (2)
- `src/components/svg/GovernanceMatrix.astro` (3)
- `src/components/svg/SystemArchitecture.astro` (1)
- `src/components/svg/BusinessConstellation.astro` (3)
- `src/components/ui/WaitlistForm.astro` (1)
- `src/components/book/book-reader.tsx` (10)
- `src/lib/book/content.ts` (1)
- `src/data/timeline.ts` (1)
- `supabase/functions/confirm-email/index.ts` (1)
- `supabase/functions/waitlist-signup/index.ts` (5)

- [ ] **Step 1: Per-file substitution**

For each file:
1. Read.
2. Edit with `replace_all: true` for `Stagent` → `ainative` and `stagent.io` → `ainative.business`.

- [ ] **Step 2: Special attention for SVG files**

SVGs may have `<text>` elements with embedded labels like `Stagent Runtime` or `Stagent Architecture`. After the substitution, view the rendered SVG in the browser preview (covered in Task 26) to ensure the text fits within the original layout space. If a label overflows, adjust the SVG `<text>` x/y or font-size attributes.

- [ ] **Step 3: Special attention for `supabase/functions/waitlist-signup/index.ts`**

This file (5 references) is the email-sending edge function. Watch for:
- Email `From:` header / sender name (e.g., `Stagent <noreply@stagent.io>` → `ainative <noreply@ainative.business>`).
- Email subject and body templates referencing the brand.
- Any URL constants for confirmation links.

For the email From-address: the actual SMTP/SES configuration may live in Supabase environment variables, not in code. The code change here updates the *display name* and any URL templates; the underlying SMTP `From:` address change is a deploy-time secret change (out of scope for this plan, but flag it for the deploy step).

- [ ] **Step 4: Verify**

Run:
```bash
grep -ri "stagent" src/components/svg/ src/components/ui/WaitlistForm.astro src/components/book/ src/lib/ src/data/timeline.ts supabase/
```
Expected: no output.

---

### Task 19: Rename and rewrite skills

**Files:**
- Rename directory `.claude/skills/stagent-stats/` → `.claude/skills/ainative-stats/`
- Modify `.claude/skills/ainative-stats/SKILL.md` (29 references after rename)
- Modify `.claude/skills/apply-book-update/SKILL.md` (14)
- Modify `.claude/skills/deck/SKILL.md` (17)
- Modify `.claude/skills/apply-api-docs/SKILL.md` (12)
- Rename file `stagent-stats.md` → `ainative-stats.md` and update its 1 internal reference.

- [ ] **Step 1: Rename the skill directory**

Run:
```bash
git mv .claude/skills/stagent-stats .claude/skills/ainative-stats
```
Expected: rename completes.

- [ ] **Step 2: Update the SKILL.md frontmatter for the renamed skill**

Open `.claude/skills/ainative-stats/SKILL.md`. The frontmatter `name:` field must match the new directory name. Edit:
- `name: stagent-stats` → `name: ainative-stats`
- Update the description if it references "Stagent" by name.

Then apply Edit with `replace_all: true` for `Stagent` → `ainative` in the body.

- [ ] **Step 3: Update the other three SKILL.md files**

For each of `apply-book-update/SKILL.md`, `deck/SKILL.md`, `apply-api-docs/SKILL.md`:
1. Read.
2. Edit with `replace_all: true` for `Stagent` → `ainative`, `stagent.io` → `ainative.business`, `stagent-stats` → `ainative-stats` (catches any references to the renamed skill).

- [ ] **Step 4: Rename the root stats file**

Run:
```bash
git mv stagent-stats.md ainative-stats.md
```
Then read the file and apply substitutions as needed (1 reference).

- [ ] **Step 5: Verify**

Run:
```bash
grep -ri "stagent" .claude/skills/ ainative-stats.md
```
Expected: no output.

- [ ] **Step 6: Confirm the old skill directory is gone**

Run:
```bash
ls .claude/skills/ | grep -i stagent
```
Expected: no output.

---

### Task 20: Rewrite historical internal design docs

**Files:**
- `docs/superpowers/specs/2026-03-31-landing-page-revolution-design.md` (8)
- `docs/superpowers/specs/2026-04-01-hero-constellation-design.md` (6)
- `docs/superpowers/specs/2026-04-01-tech-ticker-design.md` (1)
- `docs/superpowers/specs/2026-04-02-hero-title-revision-design.md` (3)
- `docs/superpowers/plans/2026-04-01-hero-constellation.md` (8)

These are the prior internal design docs that retain "Stagent" references. Per the spec's "Historical internal docs" section, they get rewritten in-place using the same 1:1 substitution rule. The current pivot spec (`docs/superpowers/specs/2026-04-17-ainative-pivot-design.md`) is *intentionally excluded* — it documents the rename and must mention both names. Same for this plan file and the handoff file.

- [ ] **Step 1: Per-file substitution**

For each of the five files in the list:
1. Read.
2. Edit with `replace_all: true` for `Stagent` → `ainative` and `stagent.io` → `ainative.business`.

- [ ] **Step 2: Verify, excluding the rename-bridge files**

Run:
```bash
grep -ril "stagent" docs/superpowers/ | grep -v "2026-04-17-ainative-pivot"
```
Expected: no output. (Two files retain stagent references intentionally: the spec and the plan from 2026-04-17.)

---

### Task 21: Cleanup — delete orphaned pricing files

**Files:**
- Delete `src/pages/pricing.astro`
- Delete `src/components/sections/Pricing.astro`

- [ ] **Step 1: Confirm no inbound references before deletion**

Run:
```bash
grep -r "Pricing" src/ --include="*.astro" --include="*.ts" --include="*.tsx" --include="*.mdx" -l | grep -v "Pricing.astro" | grep -v "pricing.astro"
```
Expected: no output (no other file imports or links to Pricing).

If any references appear: stop and update the plan to handle them before deletion. Most likely false positive is the unrelated word "pricing" in copy or comments.

- [ ] **Step 2: Delete the files**

Run:
```bash
git rm src/pages/pricing.astro src/components/sections/Pricing.astro
```
Expected: two file deletions staged.

- [ ] **Step 3: Verify**

Run:
```bash
ls src/pages/pricing.astro src/components/sections/Pricing.astro 2>&1
```
Expected: "No such file or directory" for both.

---

### Task 22: Cleanup — delete unused root-dir dev screenshots

**Files:** Delete (after verifying each is unreferenced):
- `stagent-hero.png`
- `stagent-layers.png`
- `stagent-orbit.png`
- `fynt-bottom.png`
- `fynt-features-section.png`
- `fynt-features.png`
- `fynt-hero-iso-detail.png`
- `fynt-hero-iso-zoom.png`
- `fynt-hero-top.png`
- `fynt-hero.png`
- `fynt-templates.png`
- `homepage-top.png`
- `progress-section.png`
- `progress-updated.png`
- `velocity-chart-updated.png`

- [ ] **Step 1: Verify none are referenced in source**

Run:
```bash
for f in stagent-hero.png stagent-layers.png stagent-orbit.png fynt-bottom.png fynt-features-section.png fynt-features.png fynt-hero-iso-detail.png fynt-hero-iso-zoom.png fynt-hero-top.png fynt-hero.png fynt-templates.png homepage-top.png progress-section.png progress-updated.png velocity-chart-updated.png; do
  count=$(grep -r "$f" src/ public/ docs/ 2>/dev/null | wc -l | tr -d ' ')
  echo "$f: $count references"
done
```
Expected: all show `0 references`. If any show >0, stop and inspect — that file may need to be retained.

- [ ] **Step 2: Delete the unreferenced screenshots**

Run:
```bash
git rm stagent-hero.png stagent-layers.png stagent-orbit.png fynt-bottom.png fynt-features-section.png fynt-features.png fynt-hero-iso-detail.png fynt-hero-iso-zoom.png fynt-hero-top.png fynt-hero.png fynt-templates.png homepage-top.png progress-section.png progress-updated.png velocity-chart-updated.png
```
Expected: 15 file deletions staged.

- [ ] **Step 3: Verify**

Run:
```bash
ls *.png 2>&1 | head
```
Expected: no `stagent-*.png`, `fynt-*.png`, `homepage-top.png`, `progress-*.png`, or `velocity-*.png` listed at root.

---

### Task 23: Final verification — grep across the whole tree

**Files:** none modified (verification only).

- [ ] **Step 1: Full-tree grep for any remaining Stagent reference**

Run:
```bash
grep -ril "stagent" --exclude-dir=node_modules --exclude-dir=.git --exclude-dir=dist --exclude-dir=.astro . 2>/dev/null
```
Expected output (the only allowed files):
- `docs/superpowers/specs/2026-04-17-ainative-pivot-design.md` (rename spec — must mention both names)
- `docs/superpowers/plans/2026-04-17-ainative-pivot.md` (this plan — must mention both names)
- `handoff/2026-04-17-ainative-pivot-stagent-repo.md` (handoff — must mention both names)

Any other file in the output is a missed substitution. Open it, fix it, re-run this step.

- [ ] **Step 2: Same for capital-S Stagent**

Run:
```bash
grep -rl "Stagent" --exclude-dir=node_modules --exclude-dir=.git --exclude-dir=dist --exclude-dir=.astro . 2>/dev/null
```
Expected: same three allowed files only.

- [ ] **Step 3: Same for the old domain**

Run:
```bash
grep -rl "stagent\.io" --exclude-dir=node_modules --exclude-dir=.git --exclude-dir=dist --exclude-dir=.astro . 2>/dev/null
```
Expected: same three allowed files only.

- [ ] **Step 4: Same for the old GitHub URL**

Run:
```bash
grep -rl "github\.com/manavsehgal/stagent" --exclude-dir=node_modules --exclude-dir=.git --exclude-dir=dist --exclude-dir=.astro . 2>/dev/null
```
Expected: same three allowed files only.

If any of these four greps surface unexpected files, return to the relevant earlier task and fix.

---

### Task 24: Build verification

**Files:** none modified (verification only).

- [ ] **Step 1: Clean previous build artifacts**

Run:
```bash
rm -rf dist/ .astro/
```

- [ ] **Step 2: Run the production build**

Run:
```bash
npm run build
```
Expected: completes without error. The build script is `astro build && node scripts/generate-slashless-duplicates.mjs && npm run build:og`. Watch for:
- Astro build completes; sitemap generates referencing `https://ainative.business`.
- Slashless duplicate generation completes.
- OG image generation (`tsx scripts/generate-og-images.ts`) completes; check that any embedded brand text in OG images shows "ainative" not "Stagent".

- [ ] **Step 3: Inspect the built sitemap**

Run:
```bash
grep -c "ainative.business" dist/sitemap-0.xml; grep -c "stagent.io" dist/sitemap-0.xml
```
Expected: many ainative.business URLs; zero stagent.io URLs.

- [ ] **Step 4: Inspect the built CNAME**

Run:
```bash
cat dist/CNAME
```
Expected: `ainative.business`.

- [ ] **Step 5: Inspect a generated OG image (visual)**

Use the Read tool on one of the OG images in `dist/`, e.g., `dist/og-image.png`. Confirm the embedded text shows the new brand.

---

### Task 25: Preview verification — visual proof

**Files:** none modified (verification only).

- [ ] **Step 1: Start the dev server**

Use `mcp__Claude_Preview__preview_start` with `command: "npm run dev"` and the worktree path as `cwd`.

- [ ] **Step 2: Capture screenshots of the critical routes**

Use `mcp__Claude_Preview__preview_screenshot` for:
- `/` (homepage hero shows "AI Native Business" H1, `npx ainative` in terminal)
- `/about/` (Manav's bio + ainative attribution)
- `/book/` (book reader, no Stagent in chapter titles or prose)
- `/research/` (research index)
- `/docs/` (docs index)
- `/projects/`
- `/terms/`

- [ ] **Step 3: Confirm the deleted pricing route is gone**

Use `mcp__Claude_Preview__preview_snapshot` on path `/pricing/`.
Expected: 404 page (Astro's default not-found, not the old pricing page).

- [ ] **Step 4: Check the console for errors on the homepage**

Use `mcp__Claude_Preview__preview_console_logs` after navigating to `/`. Expected: no JavaScript errors. Warnings about external resources are acceptable.

- [ ] **Step 5: Check network tab for broken images**

Use `mcp__Claude_Preview__preview_network` after the homepage load. Expected: no 404s for any image path. Specifically verify `/ainative-s-64.png` and `/ainative-s-128.png` resolve.

- [ ] **Step 6: Stop the dev server**

Use `mcp__Claude_Preview__preview_stop`.

---

### Task 26: Commit the pivot

**Files:** all changes from Tasks 2-22.

- [ ] **Step 1: Review the staged changes**

Run:
```bash
git status
git diff --stat HEAD
```

Expected: many modifications across `src/`, `public/`, `astro.config.mjs`, `package.json`, `package-lock.json`, `.claude/skills/`, `docs/superpowers/`. Several deletions (pricing files, dev screenshots). Several renames (logo files, skill directory, stats file).

- [ ] **Step 2: Stage everything**

Run:
```bash
git add -A
```

- [ ] **Step 3: Commit with a comprehensive message**

Run:
```bash
git commit -m "$(cat <<'EOF'
feat: pivot to ainative.business — domain, brand, IA, content

Atomic narrative pivot. Renames Stagent → ainative across the
website, book chapters, research, docs, skills, and historical
design docs. Switches the homepage to a book-first IA with the
companion software as second-act. Domain changes from stagent.io
to ainative.business; CNAME and astro config updated. Old domain
will be served by a separate stagent-io-redirect repo (not in
this commit).

Runtime behavior of the companion software is unchanged. Cleanup:
deletes orphaned pricing route + 15 unused dev screenshots.

Spec: docs/superpowers/specs/2026-04-17-ainative-pivot-design.md
Plan: docs/superpowers/plans/2026-04-17-ainative-pivot.md
Handoff for product code repo: handoff/2026-04-17-ainative-pivot-stagent-repo.md

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

Expected: commit succeeds. If a pre-commit hook fails, fix the underlying issue and re-stage; do NOT use `--no-verify`.

- [ ] **Step 4: Verify the commit**

Run:
```bash
git log --oneline -5
git show --stat HEAD | head -40
```
Expected: the new commit at HEAD with the expected file count and rename markers.

---

### Task 27: Coordinate the deploy with the parallel session

**Files:** none modified (operational coordination only).

This task is the contract with the parallel-session work in the `manavsehgal/stagent` (product code) repo described in the handoff doc. Both repos must be ready before the GitHub repo renames + DNS swap happen.

- [ ] **Step 1: Confirm the parallel session has landed its changes**

Verify with the user that the parallel session against `manavsehgal/stagent` has:
- Completed all changes per [`handoff/2026-04-17-ainative-pivot-stagent-repo.md`](../../../handoff/2026-04-17-ainative-pivot-stagent-repo.md).
- Committed and pushed to that repo's `main`.
- Is ready to publish `ainative` to npm and rename the repo.

If the user has not yet completed the parallel work, stop here. The website pivot can be merged to `main` of this repo without breaking anything (the GitHub link in the new Nav points to `https://github.com/manavsehgal/ainative`, which currently 404s but starts working the moment the parallel rename lands). However, the DNS swap and the redirect repo creation should wait until the product code is also ready, so visitors don't follow links that 404.

- [ ] **Step 2: Push the website branch and open a PR**

Run:
```bash
git push -u origin claude/bold-bassi-5278f5
```
Then open a PR against `main`:
```bash
gh pr create --title "Pivot to ainative.business" --body "$(cat <<'EOF'
## Summary
Atomic narrative pivot from Stagent / stagent.io to ainative / ainative.business. Book-first homepage IA, runtime unchanged, cleanup of orphaned routes.

Spec: `docs/superpowers/specs/2026-04-17-ainative-pivot-design.md`
Plan: `docs/superpowers/plans/2026-04-17-ainative-pivot.md`
Cross-repo handoff: `handoff/2026-04-17-ainative-pivot-stagent-repo.md`

## Test plan
- [x] All grep checks (Task 23) return only the three rename-bridge docs as exceptions
- [x] `npm run build` succeeds; sitemap and OG images regenerated
- [x] Preview screenshots captured for `/`, `/about/`, `/book/`, `/research/`, `/docs/`, `/projects/`, `/terms/`
- [x] `/pricing` returns 404 (orphaned route deleted)
- [x] No broken image network requests; no console errors

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

- [ ] **Step 3: Document the post-merge sequence for the user**

Print the following sequence to the user (do not execute these — they require external accounts and DNS changes the user controls):

```
Post-merge deploy sequence (perform in this order, within an hour):

1. Merge the PR to main. GitHub Pages will rebuild but still serve at stagent.io for now.
2. Rename the GitHub Pages repo:
   manavsehgal/stagent.github.io → manavsehgal/ainative-business.github.io
3. Confirm the parallel session has renamed the product code repo:
   manavsehgal/stagent → manavsehgal/ainative
4. Update DNS for ainative.business (apex + www) to point at GitHub Pages:
   A records → 185.199.108.153 / .109.153 / .110.153 / .111.153
   www CNAME → manavsehgal.github.io
5. In the renamed website repo's Pages settings, set the custom domain
   to ainative.business and wait for TLS to provision (Let's Encrypt).
6. Create a new repo manavsehgal/stagent-io-redirect with:
   - CNAME file containing: stagent.io
   - index.html with the meta-refresh + canonical link + JS path-preserving redirect
     (template in the spec under "Domain & redirect").
7. In the redirect repo's Pages settings, set custom domain to stagent.io.
   GitHub will associate stagent.io with this repo via its CNAME file.
8. Verify:
   - https://ainative.business/ loads with valid TLS, shows new branding
   - https://stagent.io/book/some-chapter redirects to https://ainative.business/book/some-chapter (path preserved)
   - GitHub link in nav resolves to a live repo
9. The Supabase email From-address may still say Stagent — update the SUPABASE
   environment variables (sender name and reply-to) for the waitlist function.
10. Maintain stagent.io domain registration for at least 12 months. Re-evaluate at month 11.
```

---

## Self-review

After completing all tasks, the engineer running this plan should re-read:
- The verification checklist in Task 23 (grep cleanliness).
- The build verification in Task 24 (build succeeds, sitemap correct, OG image correct).
- The preview verification in Task 25 (visual proof).

Any discrepancy is a failure of the rewrite — return to the relevant earlier task and resolve before commit.
