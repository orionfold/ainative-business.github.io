---
name: deck
description: >-
  Update the ainative prospect sales deck with fresh data from the product codebase,
  website sources, and stats. Use this skill whenever the user mentions "update the deck",
  "refresh the deck", "update prospect deck", "sync deck", "regenerate deck", "update slides",
  "refresh slides", "deck update", "update sales deck", "update pitch deck", "rebuild deck",
  "deck is stale", "update deck stats", "update deck screenshots", "update traction slide",
  "update portfolio slide", or any request to update, refresh, regenerate, or sync the ainative
  PPTX prospect deck with current data. Also trigger when the user says "apply product release"
  and then mentions the deck, or after running ainative-stats and wanting to push new numbers
  into the presentation. If the user mentions deck content being outdated or stale, use this skill.
---

# Deck Update Skill

This skill automates updating `deck/generate-deck.mjs` with fresh data from the ainative product and website, then regenerating the 27-slide PPTX prospect deck.

**What it does:** Updates data values (stats, metrics, project cards, market data, roadmap horizons) inside existing slide code.

**What it does NOT do:** Restructure slides, change layouts, add/remove slides, or modify the brand palette — only data values inside existing slide code.

---

## Phase 1: Collect Fresh Data

### Step 1 — Collect ainative Stats

Check if `ainative-stats.md` exists and has a recent entry (same day). If stale or missing, invoke the `ainative-stats` skill first.

Extract from the stats report:
- TypeScript production LOC (for traction slide)
- Test count (for traction slide)
- Feature completion ratio (for traction slide)
- API route count, UI component count, page count (for traction slide)

### Step 2 — Read Website Data Sources

Read these files from the website repo:

| File | What to extract |
|------|-----------------|
| `src/data/timeline.ts` lines 23-29 | `metrics` array: aggregate LOC, AI agents, production systems, projects, blog articles |
| `src/data/timeline.ts` lines 31+ | `timeline` array: per-project `stats`, `techWave`, `techCategories`, `status` |
| `src/components/sections/Progress.astro` lines 4-25 | `stats` array: surface count, workflow pattern count |
| `src/pages/research.mdx` Section 2 | Market stats: market size, CAGR, enterprise adoption, cancellation rate |

### Step 3 — Read Product Sources

Read these files from the ainative product:

| File | What to extract |
|------|-----------------|
| `/Users/manavsehgal/Developer/ainative/features/roadmap.md` | Feature counts, horizon timelines (H1/H2/H3 focus areas) |
| `/Users/manavsehgal/Developer/ainative/features/changelog.md` | Recent completions for roadmap context |
| `/Users/manavsehgal/Developer/ainative/README.md` | Framework versions, architecture details, service module list |

### Data Collection Checkpoint

Present a **Data Collection Summary** table showing all values collected and their sources.

**STOP: Wait for user confirmation before proceeding to Phase 2.**

---

## Phase 2: Compare and Plan

### Step 4 — Extract Current Deck Values

Read `deck/generate-deck.mjs` and extract values from these locations:

| Deck Section | Slide(s) | What to find in code |
|---|---|---|
| Traction stats | 26 | `traction` array — 6 objects: `{ value, label }` for LOC, tests, features, components, routes, pages |
| Portfolio metrics | 19 | `portMetrics` array — 5 objects: `{ value, label }` for aggregate LOC, agents, systems, projects, articles |
| Project cards | 20 | `projects` array — 9 objects: `{ name, stats, tech, wave, color }` |
| Tech waves timeline | 19 | `waves` array — 5 objects: `{ year, wave, projects }` |
| Market research | 21 | `mktStats` array — 7 objects: `{ metric, value, src }` |
| Competitive table | 22 | `capabilities` array — 8 row objects |
| Roadmap horizons | 24 | `horizons` array — 3 objects: `{ h, timeline, focus, details[] }` |
| Architecture swimlane | 18 | `routes` array (10 pills), `svcRow1`/`svcRow2` (8 service cards), `externals` (3 cards) |
| Tech stack | 17 | `techStack` array — 5 objects: `{ label, value }` |
| Layer descriptions | 3 | `layers` array — 4 objects: `{ name, desc }` |
| Screenshot files | 5-8, 10-15 | `productFiles` array — 10 filenames |
| Product slide copy | 5-8, 10-15 | `addProductSlide` calls — `title` and `subtitle` strings |
| CTA links | 27 | `ctas` array — 3 objects with `desc` URLs; footer URL string |

### Step 5 — Build the Change Plan

Compare fresh data vs. current values. Present a diff table:

```
| Slide | Field | Current | New | Source |
|-------|-------|---------|-----|--------|
| 26    | LOC   | 42,673  | 55,210 | ainative-stats |
| 26    | Tests | 312     | 348    | ainative-stats |
| ...   | ...   | ...     | ...    | ...    |
```

Also list sections with **no changes detected**.

**STOP: Wait for user confirmation. User may reject individual changes.**

---

## Phase 3: Apply Changes

### Step 6 — Update generate-deck.mjs

For each approved change, use the Edit tool to update the specific array/value in `deck/generate-deck.mjs`.

**Formatting rules:**
- Traction numbers: comma-separated (`42,673` not `42673`)
- Portfolio metrics: use suffix pattern from `timeline.ts` (e.g., `300K+`, `30+`, `8`)
- Feature ratios: format as `"51/53"`
- Screenshot filenames: verify each file exists in `public/screenshots/` before accepting

### Step 7 — Review the Diff

Run `git diff deck/generate-deck.mjs` and present the full diff to the user.

**STOP: Wait for user confirmation before regeneration.**

---

## Phase 4: Regenerate and QA

### Step 8 — Regenerate the Deck

```bash
cd /Users/manavsehgal/Developer/ainative.business/deck && node generate-deck.mjs
```

Verify output says `(27 slides)` — slide count must not change.

### Step 9 — Convert to Images for QA

```bash
cd /Users/manavsehgal/Developer/ainative.business/deck
python ../.claude/skills/pptx/scripts/office/soffice.py --headless --convert-to pdf ainative-Prospect-Deck.pptx
pdftoppm -jpeg -r 150 ainative-Prospect-Deck.pdf slide
```

### Step 10 — Visual QA

Only inspect slides that were changed. For each changed slide, read the `slide-NN.jpg` image and verify:
- Updated values render correctly (no truncation/overflow)
- Numbers formatted correctly
- No layout breakage from longer/shorter strings
- Text fits within card boundaries

If issues found: fix in `generate-deck.mjs` → re-run `node generate-deck.mjs` → re-render affected slides → re-inspect. Repeat until clean.

---

## Phase 5: Summary

### Step 11 — Present Summary

```
## Deck Update Summary

| Slide | Section | Changes |
|-------|---------|---------|
| 26    | Traction | LOC: 42,673→55,210, Tests: 312→348 |
| ...   | ...      | ...                                  |

### Slides Not Modified
- Slide 1 (Title) — no updatable data
- ...

### Output
- deck/ainative-Prospect-Deck.pptx (27 slides, regenerated)

### QA
- Visual inspection: N slides verified, N issues fixed
```

---

## Key Rules

- **Idempotent**: Safe to run multiple times. Each run reads fresh data and overwrites stale values.
- **Non-destructive**: Never removes slides, changes layouts, or modifies the brand palette (`C` object).
- **User confirmation required**: At data collection, change plan, code changes, and QA stages.
- **Preserve slide count**: Must remain exactly 27 slides.
- **Format consistency**: Commas for thousands, suffix patterns from sources.
- **Screenshot safety**: Never swap screenshot files without explicit user confirmation. Verify filenames exist before regeneration.
- **Scope boundary**: This skill only updates data values. Layout, design, and structural changes are manual work outside this skill.
