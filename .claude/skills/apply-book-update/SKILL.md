---
name: apply-book-update
description: Sync book content from the Stagent product to the stagent.io website. Compares chapter markdown files and images, copies changed content, updates code files if structure changed, and verifies the build. Use when the user says "update book", "sync book", "refresh book content", "apply book update", "sync book chapters", "update book content", "book content is stale", "new book chapters", "refresh book from product", "copy book chapters", "update book images", or any request to update, sync, or refresh the AI Native Business book content on the website from the source product repository. Also trigger after "apply product release" if the user mentions book content.
---

# Apply Book Update Skill

Syncs the "AI Native Business" book content (chapter markdown files + images) from the Stagent product repository to the stagent.io marketing website. The book lives as a React island reader at `/book/[chapter-slug]` and content is parsed at Astro build time. The current chapter count is whatever is in the Chapter Manifest below — most counts elsewhere in the codebase are derived dynamically from `CHAPTERS.length`.

## Attribution & License Architecture

**The book is a personal research project by Manav Sehgal, licensed CC BY-NC 4.0.** Several attribution artifacts live in the website codebase — not in the source chapter markdown — so they must survive every sync.

| Artifact | Lives in | Rebuilt how |
|----------|----------|-------------|
| Per-chapter "by Manav Sehgal" byline | `src/components/book/book-reader.tsx` (chapter header) | Hardcoded, not from frontmatter |
| Chapter 1 CC BY-NC 4.0 preface | Conditional render in `book-reader.tsx` when `chapter.number === 1` | Hardcoded, not from frontmatter |
| CC BY-NC 4.0 in Book JSON-LD | `src/layouts/BookLayout.astro` + `src/pages/book/index.astro` (`license` field) | Static |

**Do not add an `author` frontmatter field to chapter markdown** — attribution is intentionally centralized in the reader template so the product repo can stay author-agnostic and we don't have to replicate the byline 14× in markdown.

## Source and Target Paths

| Content | Source | Target |
|---------|--------|--------|
| Chapters | `/Users/manavsehgal/Developer/stagent/book/chapters/*.md` | `src/data/book/chapters/` |
| Images | `/Users/manavsehgal/Developer/stagent/book/images/*` | `public/book/images/` |

The website project root is `/Users/manavsehgal/Developer/stagent.github.io/`.

## Chapter Manifest

| ID | Filename | Part |
|----|----------|------|
| ch-1 | `ch-1-from-hierarchy-to-intelligence.md` | 1 |
| ch-2 | `ch-2-the-ai-native-blueprint.md` | 1 |
| ch-3 | `ch-3-the-refinery.md` | 2 |
| ch-4 | `ch-4-the-forge.md` | 2 |
| ch-5 | `ch-5-blueprints.md` | 2 |
| ch-6 | `ch-6-the-arena.md` | 2 |
| ch-7 | `ch-7-institutional-memory.md` | 3 |
| ch-8 | `ch-8-the-swarm.md` | 3 |
| ch-9 | `ch-9-the-governance-layer.md` | 3 |
| ch-10 | `ch-10-the-world-model.md` | 4 |
| ch-11 | `ch-11-the-machine-that-builds-machines.md` | 4 |
| ch-12 | `ch-12-the-road-ahead.md` | 4 |
| ch-13 | `ch-13-the-wealth-manager.md` | 4 |
| ch-14 | `ch-14-the-meta-program.md` | 4 |

## Complete File Manifest

All files that may need updating during a book sync:

| # | File | When to Update |
|---|------|---------------|
| 1 | `src/data/book/chapters/*.md` | Every sync |
| 2 | `public/book/images/*` | Every sync |
| 3 | `src/lib/book/content.ts` | When chapters added/removed/reordered |
| 4 | `src/lib/book/types.ts` | When new callout variants added |
| 5 | `src/lib/book/markdown-parser.ts` | When new callout variants added |
| 6 | `src/components/book/content-blocks.tsx` | When new callout variants added |
| 7 | `src/styles/book.css` | When new callout variants added |
| 8 | `src/lib/book/reading-paths.ts` | When chapters added/removed |
| 9 | `src/pages/book/index.astro` | When parts count or description changes |
| 10 | `src/components/book/book-reader.tsx` | When chapter URL pattern changes |
| 11 | `src/layouts/BookLayout.astro` | Never — imports `CHAPTERS`/`PARTS`, auto-updates |
| 12 | `src/components/sections/RuntimeBridge.astro` | Never — imports `CHAPTERS`/`PARTS`, auto-updates |
| 13 | `src/pages/research/ai-transformation.mdx` | Flag via drift audit only — historical snapshot, update only with user confirmation |

## 7-Step Workflow

### Step 1: Detect Sync Mode

Determine whether this is a **migration** (old chapter filenames still in target) or an **incremental sync** (new filenames already present):

```bash
cd /Users/manavsehgal/Developer/stagent.github.io
if [ -f "src/data/book/chapters/ch-1-project-management.md" ]; then
  echo "MODE: MIGRATION — old chapter files detected, full structural update needed"
elif [ -f "src/data/book/chapters/ch-1-from-hierarchy-to-intelligence.md" ]; then
  echo "MODE: INCREMENTAL — new chapter files already in place, checking for content changes"
else
  echo "MODE: FRESH — no chapter files found, full copy needed"
fi
```

- **Migration mode**: Delete old files, copy all new ones, update all code files in the manifest
- **Incremental mode**: Diff-based copy of changed chapters/images only
- **Fresh mode**: Same as migration but no old files to delete

### Step 2: Compare Files

Check which files have changed between source and target:

```bash
cd /Users/manavsehgal/Developer/stagent.github.io
echo "=== Chapters ==="
for src in /Users/manavsehgal/Developer/stagent/book/chapters/*.md; do
  name=$(basename "$src")
  tgt="src/data/book/chapters/$name"
  if [ ! -f "$tgt" ]; then
    echo "NEW: $name"
  elif ! diff -q "$src" "$tgt" > /dev/null 2>&1; then
    echo "CHANGED: $name"
  fi
done
echo "--- Stale target files ---"
for tgt in src/data/book/chapters/ch-*.md; do
  name=$(basename "$tgt")
  src="/Users/manavsehgal/Developer/stagent/book/chapters/$name"
  if [ ! -f "$src" ]; then
    echo "STALE (delete): $name"
  fi
done
echo "=== Images ==="
for src in /Users/manavsehgal/Developer/stagent/book/images/*; do
  name=$(basename "$src")
  tgt="public/book/images/$name"
  if [ ! -f "$tgt" ]; then
    echo "NEW IMAGE: $name"
  elif ! diff -q "$src" "$tgt" > /dev/null 2>&1; then
    echo "CHANGED IMAGE: $name"
  fi
done
```

If nothing changed and mode is incremental, report "Book content is up to date" and stop.

### Step 3: Copy Chapters

**Migration/Fresh mode**: Delete all old chapter files, then copy all new ones:

```bash
rm -f src/data/book/chapters/ch-*.md
cp /Users/manavsehgal/Developer/stagent/book/chapters/*.md src/data/book/chapters/
```

**Incremental mode**: Copy only changed or new files:

```bash
cp /path/to/changed/files src/data/book/chapters/
```

Delete any stale target files that no longer exist in source.

For each changed chapter, briefly read the diff to understand what changed (new sections, updated content, fixes). This context is useful for the change report.

#### Step 3 Lint: Reader Chrome Leakage Check

After copying, scan the target chapter files for reader chrome that should NOT appear in the markdown body. The `BookReader` component renders its own chapter counter, horizontal rule, and "Explore Related Features" card from frontmatter — any of those in the body will duplicate on screen.

```bash
for f in src/data/book/chapters/ch-*.md; do
  if grep -qE '^Chapter [0-9]+ of [0-9]+$|^### Explore Related Features$' "$f"; then
    echo "⚠️ READER CHROME LEAKED INTO BODY: $(basename "$f")"
  fi
done
```

If any warnings fire, **stop and flag to the user**. Do NOT silently strip the chrome — this is an upstream generator bug that should be fixed in `/Users/manavsehgal/Developer/stagent/book/chapters/` so it doesn't recur on the next sync. Acceptable action: ask the user whether to (a) fix upstream first and re-sync, or (b) strip locally as a one-time hotfix knowing the next sync will re-introduce it.

Historical context: ch-14 shipped with a trailing `---` rule, a "Chapter 14 of 14" line, and a static "### Explore Related Features" block that the reader then rendered a second time. This lint exists to catch that class of drift.

### Step 4: Copy Changed Images

Copy only changed or new image files:

```bash
cp /path/to/changed/images public/book/images/
```

Remove any stale image files that no longer exist in source.

### Step 5: Update Code Files (Structural Changes)

**This step runs in migration/fresh mode, or when source adds/removes chapters or introduces new callout types.** In incremental mode with no structural changes, skip this step.

Update each file as needed:

#### 5a. `src/lib/book/content.ts`

Update `CHAPTER_SLUG_MAP` to map every chapter ID in the Chapter Manifest to its filename. Update `PARTS` array to 4 parts. Update `CHAPTERS` array with one entry per chapter — read frontmatter from each source chapter file to populate `title`, `subtitle`, `readingTime`, `wordCount`, `relatedDocs`, and `relatedJourney`.

For `wordCount`, run `wc -w` on each source chapter file and use the result. This field drives the "X words" and "~Y pages" stats on the landing page. **Run `wc -w` on the target file after any in-repo edits** (e.g., Step 3 chrome-leak hotfixes) so the count reflects what ships, not what was copied.

Part assignments (current — update this list when adding/removing chapters):
- Part 1: ch-1, ch-2
- Part 2: ch-3, ch-4, ch-5, ch-6
- Part 3: ch-7, ch-8, ch-9
- Part 4: ch-10, ch-11, ch-12, ch-13, ch-14

Read the source chapter frontmatter for part titles/descriptions if available, otherwise derive from chapter themes.

#### 5b. `src/lib/book/types.ts`

Add `"case-study"` to the `CalloutBlock` variant union type. Keep existing variants for backward compatibility:

```typescript
variant: "tip" | "warning" | "info" | "lesson" | "authors-note" | "case-study";
```

#### 5c. `src/lib/book/markdown-parser.ts`

Add `case-study` to the callout regex pattern on the line matching `calloutMatch`:

```typescript
const calloutMatch = line.match(/^>\s*\[!(tip|warning|info|lesson|authors-note|case-study)\]\s*$/);
```

#### 5d. `src/components/book/content-blocks.tsx`

Add `case-study` entry to the `calloutConfig` object. Import an appropriate icon (e.g., `FileText` from lucide-react):

```typescript
"case-study": { icon: FileText, className: "book-callout-case-study" },
```

Update the `CalloutBlockView` variant type prop to include `"case-study"`.

#### 5e. `src/styles/book.css`

Add CSS rules for the new callout variant after the existing callout styles:

```css
.book-callout-case-study {
  border-color: oklch(0.55 0.12 230);
}
.book-callout-case-study .book-callout-icon {
  color: oklch(0.55 0.12 230);
}
```

#### 5f. `src/lib/book/reading-paths.ts`

Update reading path `chapterIds` arrays to reference every current chapter ID. Redesign paths to match the chapter themes:

- **Getting Started**: ch-1, ch-2 (foundation/blueprint chapters)
- **Personal Use**: ch-3, ch-5, ch-6 (chapters with `relatedJourney: "personal-use"` or `"power-user"`)
- **Work Use**: ch-4, ch-7, ch-8, ch-9 (chapters with `relatedJourney: "work-use"` or `developer`)
- **Complete**: every chapter in order (append any new chapter to this array)

Adjust based on the `relatedJourney` values in chapter frontmatter.

#### 5g. `src/pages/book/index.astro`

The landing page hero stats are **dynamic** — computed from the CHAPTERS array at build time:
- `{CHAPTERS.length} chapters` — auto-updates
- `~{totalReadingTime} min read` — sum of all readingTime values
- `{PARTS.length} parts` — auto-updates
- `{totalWords.toLocaleString()} words` — sum of all wordCount values
- `~{totalPages} pages` — totalWords / 250, rounded up

The JSON-LD schema uses `numberOfPages: totalPages` for the computed page count.

**No hardcoded stats to update in the hero** — just ensure `wordCount` values in content.ts are current (run `wc -w` on each chapter). If chapters are added/removed, update the meta description text and the screenshot alt text that mentions chapter count.

**Other files that used to drift are now dynamic:**
- `src/layouts/BookLayout.astro` imports `CHAPTERS`/`PARTS` and templates the count into its JSON-LD Book description — auto-updates on every sync, no edits needed.
- `src/components/sections/RuntimeBridge.astro` imports `CHAPTERS`/`PARTS` and templates the count into its feature callout — auto-updates, no edits needed. (This section is currently dormant in the homepage but kept in sync for when it re-activates.)

Only the meta description text and alt text in `index.astro` remain as manual edits. See the drift audit in Step 6b for how to find any new static references that should be refactored or flagged.

**CRITICAL — Trailing slashes on all hrefs:** Every `href` that interpolates `CHAPTER_SLUG_MAP` must append a trailing slash. The map values are bare slugs (no slash), so callers must add it:

- Correct: `` href={`/book/${CHAPTER_SLUG_MAP['ch-1']}/`} ``
- Wrong: `` href={`/book/${CHAPTER_SLUG_MAP['ch-1']}`} ``

There are 4 such links in this file: the hero CTA, the chapter grid links, the reading paths links, and the bottom CTA. Verify all have trailing slashes after any edit.

#### 5h. `src/components/book/book-reader.tsx`

The book reader uses `window.history.replaceState` to update the URL when navigating between chapters client-side. This URL must also include a trailing slash:

- Correct: `` window.history.replaceState({}, "", `/book/${slug}/`) ``
- Wrong: `` window.history.replaceState({}, "", `/book/${slug}`) ``

Without this, the browser URL bar shows a path that would 301 redirect on GitHub Pages, and bookmarking or sharing the URL would fail.

### Step 6: Verify Build

Run the Astro build to confirm all chapter pages generate correctly:

```bash
npm run build 2>&1 | tail -20
```

The build should produce pages under `/book/` for each chapter. Check for:
- Every chapter in the Chapter Manifest has a route generated
- No build errors
- Book index page generated at `/book/index.html`

If the build fails, investigate the error. Common issues:
- Frontmatter format changes in chapter markdown (the parser expects YAML frontmatter with `title`, `subtitle`, `chapter`, `part`, `readingTime` fields)
- New callout type not added to the parser regex, types, or component
- Missing icon import in `content-blocks.tsx`
- CSS class not defined for a new callout variant

### Step 6b: Drift Audit — Find Stale "N chapters" Prose

After the build verifies, grep the codebase for any prose that hardcodes a chapter count and doesn't match `CHAPTERS.length`. This catches references that weren't refactored to use dynamic imports.

```bash
NEW_COUNT=$(grep -c '^  {' src/lib/book/content.ts)  # rough count of CHAPTERS entries
# Or read more precisely from the CHAPTER_SLUG_MAP length
grep -rn -E '\b[0-9]+ chapters\b' src/ \
  --include='*.astro' --include='*.tsx' --include='*.mdx' --include='*.md' \
  | grep -v -E "\b${NEW_COUNT} chapters\b" \
  | grep -v '/book/chapters/'   # exclude sourced book body text (fix upstream)
```

**Triage each hit:**
- **Site chrome / marketing copy** (e.g., `src/pages/book/index.astro` meta description, alt text, BrowserFrame alts): **update in place** to the new count.
- **Research papers / dated snapshots** (e.g., `src/pages/research/*.mdx`): **flag for user confirmation** — these may be historical snapshots. Do not auto-update.
- **Files that could use a dynamic import** (e.g., a new Astro component added since last sync): **suggest refactoring** to `import { CHAPTERS } from '../lib/book/content'` instead of patching the literal. Drift-prone prose should become data-driven at the first opportunity.
- **Book body prose in `src/data/book/chapters/*.md`**: **do not edit in this repo** — it's sourced from the product repo. Flag to the user with the file path so they can fix upstream.

Report any unresolved hits in the Step 7 change report under a "⚠️ Drift audit" heading.

### Step 6c: Commercial Framing Drift Audit

Stagent.io is positioned as a personal research project, not a commercial funnel. Any re-introduction of "founding member" language, Maven/LinkedIn links, or Stage 2 "Orionfold LLC" references must fail the sync. Run this audit after every chapter sync — even if the product repo changed only markdown, a copy-paste could leak commercial framing back in.

```bash
cd /Users/manavsehgal/Developer/stagent.github.io
FORBIDDEN=(
  'founding member'
  'founding-hero'
  'founding-footer'
  'Become a Member'
  'Join as a founding'
  'shape the roadmap'
  'direct access to the team'
  "be first for what's next"
  'maven\.com'
  'linkedin\.com/in/manavsehgal'
  'Orionfold'
  '\bLLC\b'
)
for pattern in "${FORBIDDEN[@]}"; do
  hits=$(grep -rEin "$pattern" src/ public/ supabase/ .github/ 2>/dev/null \
    | grep -v 'node_modules' \
    | grep -v '\.git/' \
    || true)
  if [ -n "$hits" ]; then
    echo "❌ FORBIDDEN PATTERN '$pattern':"
    echo "$hits"
  fi
done
```

False-positive allowlist:
- `src/data/seo.ts` has `foundingDate: '2026'` — this is the schema.org `Organization.foundingDate` property, unrelated to "founding member" framing. Do not flag.

If any pattern hits (outside the allowlist), **stop and flag to the user** — do not silently auto-remove, because the re-introduction is a signal that the upstream product or a copy-paste action reopened commercial framing that should be dealt with at the source.

### Step 6d: Attribution Render Check

Confirm the chapter byline and Chapter 1 copyright preface still render. Because these live in React components rendered client-side, the static HTML grep only catches the JSON-LD license — not the UI attribution. After the build, open a chapter page in the browser (or use a headless check) and verify:

- Chapter title header shows "by Manav Sehgal" in small muted type beneath the subtitle.
- Chapter 1 body starts with a "© 2026 Manav Sehgal. Licensed under Creative Commons Attribution-NonCommercial 4.0 (CC BY-NC 4.0)." preface.
- `dist/book/<chapter>/index.html` contains `"license":"https://creativecommons.org/licenses/by-nc/4.0/"` in the JSON-LD block.

Quick grep check:
```bash
grep -c '"license":"https://creativecommons.org/licenses/by-nc/4.0/"' dist/book/index.html
```

If the count is 0 or the UI doesn't render the attribution, the reader template was inadvertently reverted — restore from git.

### Step 7: Report Changes

Summarize what was updated in a clear report:

```
## Book Content Updated

### Sync Mode
Migration / Incremental

### Chapters Changed
- ch-1-from-hierarchy-to-intelligence.md — [brief description]
- ch-5-blueprints.md — [brief description]

### Images Changed
- workflow-progress.png — [new/updated]

### Code Files Updated
- content.ts — updated CHAPTERS, PARTS, CHAPTER_SLUG_MAP
- types.ts — added case-study variant
- [etc.]

### Build Status
✓ All chapter pages generated successfully

### ⚠️ Drift Audit
(Include any unresolved "N chapters" hits from Step 6b, or "none" if clean.)

### ⚠️ Commercial Framing Drift
(Include any forbidden-pattern hits from Step 6c, or "none" if clean.)

### ⚠️ Attribution Render
(Per Step 6d — confirm "by Manav Sehgal" byline and CC BY-NC 4.0 preface render on a chapter page. Flag if either is missing.)

### ⚠️ Reader Chrome Lint
(Include any chrome-leak warnings from Step 3 lint, or "none" if clean.)
```

## Content Architecture Notes

Understanding how the book content flows through the system helps diagnose issues:

1. **Markdown files** in `src/data/book/chapters/` contain YAML frontmatter + markdown body
2. **At build time**, `src/pages/book/[...slug].astro` reads each file via `fs.readFileSync`
3. **Frontmatter is parsed** to extract metadata (title, subtitle, chapter number, part, reading time, lastGeneratedBy)
4. **Body is parsed** by `src/lib/book/markdown-parser.ts` into structured `ContentBlock[]` (text, code, callout blocks)
5. **All chapters** in the Chapter Manifest (currently across **4 parts**) are serialized as JSON props to the React `BookReader` component
6. **Images** are referenced as `/book/images/filename.png` in the markdown and served from `public/book/images/`

## Chapter File Format

Each chapter markdown file uses this frontmatter format:

```yaml
---
title: "Chapter Title"
subtitle: "Chapter Subtitle"
chapter: 1
part: 1
readingTime: 14
lastGeneratedBy: "2026-04-05T00:00:00.000Z"
relatedDocs: ["docs-slug-1", "docs-slug-2"]
relatedJourney: "personal-use"
---
```

Required fields: `title`, `subtitle`, `chapter`, `part`, `readingTime`, `lastGeneratedBy`
Optional fields: `relatedDocs` (array of doc page slugs), `relatedJourney` (one of: `"personal-use"`, `"work-use"`, `"power-user"`, `"developer"`)

Note: `wordCount` is NOT in the markdown frontmatter — it is computed from `wc -w` and stored only in `src/lib/book/content.ts`. When syncing chapters, always recompute word counts and update the CHAPTERS array.

The body uses standard markdown with these patterns:
- `## Section Title` for major sections (no deeper nesting)
- `> [!case-study]` for case study callout blocks (the only callout type used)
- ` ```typescript ` for code blocks (TypeScript only)
- Standard bold, italic, inline code, and blockquote formatting

## Important: Trailing Slash Configuration

The site has `trailingSlash: 'always'` in `astro.config.mjs`. All book URLs **must** end with a trailing slash:

- Correct: `/book/ch-1-from-hierarchy-to-intelligence/`
- Wrong: `/book/ch-1-from-hierarchy-to-intelligence` (causes 301 redirect on GitHub Pages, 404 on dev server)

**Why this matters:** GitHub Pages serves directory-based routes at `/book/slug/` and 301-redirects `/book/slug` → `/book/slug/`. Missing trailing slashes cause slower page loads, Google Search Console "Page with redirect" warnings, and broken client-side navigation.

**`CHAPTER_SLUG_MAP` values are bare slugs** (e.g., `"ch-1-from-hierarchy-to-intelligence"` — no trailing slash). Every caller must append `/` when constructing hrefs or URLs. Files that generate book chapter URLs:

| File | Pattern | Correct |
|------|---------|---------|
| `src/pages/book/index.astro` | `href={/book/${CHAPTER_SLUG_MAP[id]}/}` | 4 occurrences |
| `src/components/book/book-reader.tsx` | `replaceState({}, "", /book/${slug}/)` | 1 occurrence |

**After every sync**, grep for bare `CHAPTER_SLUG_MAP` usage without trailing slashes:

```bash
grep -n 'CHAPTER_SLUG_MAP\[' src/pages/book/index.astro | grep -v "/'}"
```

Any matches indicate missing trailing slashes that must be fixed.
