# Apply Product Release — Skill Consolidation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebuild the lost `apply-product-release` skill as a pure orchestrator, add two new atomic skills (`apply-screengrabs`, `apply-product-docs`), and add a structural Plan/Execute contract to the three existing skills so a single "apply product release" invocation aggregates one unified plan, gets one approval, then executes end-to-end through a browser smoke test.

**Architecture:** Six skills in `.claude/skills/` — three existing (refactored to add `## Plan Phase` / `## Execute Phase` section headers plus a canonical Plan Output Format block), two new atomic skills, one new orchestrator that invokes the other five via the `Skill` tool. Each sub-skill remains runnable standalone. The orchestrator adds a browser-smoke step via `claude-in-chrome` MCP tools after `npm run build` succeeds.

**Tech Stack:** SKILL.md markdown files (YAML frontmatter + prose instructions) in `.claude/skills/`; Bash / Grep for sub-skill detection logic; Astro for website build (`npm run build`, `npm run preview`); `claude-in-chrome` MCP tools for browser smoke; `skill-creator` skill for scaffolding new skills and iterating on descriptions.

**Reference spec:** `docs/superpowers/specs/2026-04-18-apply-product-release-design.md`

---

## Phase A — Refactor existing skills (add Plan/Execute headers)

The three existing skills each get a minimal structural refactor so the orchestrator can invoke them in plan mode. Zero behavior change when run standalone.

### Task 1: Refactor `apply-api-docs` with Plan/Execute structure

**Files:**
- Modify: `.claude/skills/apply-api-docs/SKILL.md`

**Refactor spec:**
- Add `## Plan Phase` header before current "### Step 1: Inventory API Routes"
- **Delete** "### Step 5: User Confirmation Gate" entirely (lines starting at Step 5 through end of that step's block) — orchestrator owns gating; standalone runs fire one gate at the Plan→Execute boundary
- Add `## Plan Output Format` section immediately after the deleted Step 5 and before `## Execute Phase`
- Add `## Execute Phase` header before renumbered Step 5 (was Step 6: Generate/Update Domain Pages)
- Renumber Steps 6-10 to 5-9 within Execute Phase (since old Step 5 was deleted)
- Update any cross-references inside the SKILL.md that cite "Step N" numbers

- [ ] **Step 1: Read the current skill to anchor line numbers**

Run: `wc -l .claude/skills/apply-api-docs/SKILL.md`
Expected: ~338 lines

Open the file and locate these anchor blocks:
- Line with `### Step 1: Inventory API Routes` — insertion point for `## Plan Phase` (just before)
- Line with `### Step 5: User Confirmation Gate` — start of block to DELETE
- Line with `### Step 6: Generate/Update Domain Pages` — renamed to `### Step 5: …` and preceded by `## Execute Phase`

- [ ] **Step 2: Insert `## Plan Phase` header**

Edit the file. Find:
```
## 10-Step Workflow

### Step 1: Inventory API Routes
```
Replace with:
```
## 10-Step Workflow

This skill has two phases. When invoked standalone it runs both sequentially with one user gate between them. When invoked by `apply-product-release` the orchestrator runs only Plan Phase, aggregates plans from all sub-skills, fires one unified gate, then invokes each sub-skill's Execute Phase.

## Plan Phase

### Step 1: Inventory API Routes
```

- [ ] **Step 3: Delete `### Step 5: User Confirmation Gate` block**

Remove the entire Step 5 block from the line starting `### Step 5: User Confirmation Gate` through the last line of that step (includes the "Proceed? [Wait for user confirmation]" line). Also remove the `Present a change summary and **wait for user approval**:` prose.

Leave no trailing blank-line cruft.

- [ ] **Step 4: Insert `## Plan Output Format` section**

Right after the deleted Step 5, before the next step (which will become Execute Phase Step 5), add:

````markdown
## Plan Output Format

When running in Plan Phase only (invoked by `apply-product-release` orchestrator), stop after Step 4 and emit a single plan block in this exact shape:

```markdown
### apply-api-docs
- **Status**: changed | no-changes | error
- **Summary**: <one-line: e.g., "3 new domains, 2 updated, 21 unchanged">
- **Changes**:
  | Type | Item | Reason |
  |------|------|--------|
  | create | chat.mdx | new domain, 9 endpoints |
  | update | tasks.mdx | endpoint count changed 10 → 13 |
  | skip   | projects.mdx | unchanged since last run |
- **Risks**: (optional — e.g., "2 domains with no Zod validator — request shapes inferred from handler code")
```

Do not write any files during Plan Phase. Do not prompt for confirmation. Return control to the caller.
````

- [ ] **Step 5: Add `## Execute Phase` header and renumber old steps 6-10 → 5-9**

Find:
```
### Step 6: Generate/Update Domain Pages
```
Replace with:
```
## Execute Phase

### Step 5: Generate/Update Domain Pages
```

Find each subsequent step header and decrement by one:
- `### Step 7: Generate/Update Index Page` → `### Step 6: Generate/Update Index Page`
- `### Step 8: Update Navigation` → `### Step 7: Update Navigation`
- `### Step 9: Update Reference Manifest` → `### Step 8: Update Reference Manifest`
- `### Step 10: Verify and Summarize` → `### Step 9: Verify and Summarize`

- [ ] **Step 6: Grep for stale step references**

Run: `grep -n 'Step [0-9]' .claude/skills/apply-api-docs/SKILL.md`

Expected: all matches either reference the new (5-9) Execute Phase step numbers, or reference "Step 1-4" for the Plan Phase. No bare references to "Step 5" as "User Confirmation Gate" and no references to "Step 10" should remain.

If any stale reference found, fix in place.

- [ ] **Step 7: Verify structure is coherent**

Run: `grep -n '^## \|^### Step' .claude/skills/apply-api-docs/SKILL.md`

Expected output pattern:
```
## 10-Step Workflow
## Plan Phase
### Step 1: Inventory API Routes
### Step 2: Extract Validators and Schemas
### Step 3: Extract Type Definitions
### Step 4: Read Existing API Docs (Incremental Check)
## Plan Output Format
## Execute Phase
### Step 5: Generate/Update Domain Pages
### Step 6: Generate/Update Index Page
### Step 7: Update Navigation
### Step 8: Update Reference Manifest
### Step 9: Verify and Summarize
```

Also update the `## 10-Step Workflow` heading to `## Workflow` (since it's no longer exactly 10 steps; it's now 4 planning + 5 executing).

- [ ] **Step 8: Commit**

```bash
git add .claude/skills/apply-api-docs/SKILL.md
git commit -m "refactor(apply-api-docs): split into Plan Phase and Execute Phase

Adds '## Plan Phase' (steps 1-4, detection) and '## Execute Phase'
(steps 5-9, writes + verify) section headers. Deletes in-skill
confirmation gate (old Step 5) — orchestrator now owns gating.
Adds '## Plan Output Format' section so apply-product-release
orchestrator can aggregate plans from all sub-skills.

Zero behavior change when run standalone.
"
```

---

### Task 2: Refactor `apply-book-update` with Plan/Execute structure

**Files:**
- Modify: `.claude/skills/apply-book-update/SKILL.md`

**Refactor spec:**
- Add `## Plan Phase` before current Step 1 (Detect Sync Mode)
- Plan Phase contains Steps 1-2 (Detect Sync Mode, Compare Files) only
- Add `## Plan Output Format` block
- Add `## Execute Phase` before Step 3 (Copy Chapters)
- Execute Phase contains Steps 3-7 (+ Step 3 Lint, 6b/6c/6d sub-steps stay where they are)

- [ ] **Step 1: Read current skill structure**

Run: `grep -n '^## \|^### Step' .claude/skills/apply-book-update/SKILL.md`

Expected: see the current `## 7-Step Workflow` heading and `### Step 1` through `### Step 7`.

- [ ] **Step 2: Rename workflow heading and insert Plan Phase header**

Find:
```
## 7-Step Workflow

### Step 1: Detect Sync Mode
```
Replace with:
```
## Workflow

This skill has two phases. When invoked standalone it runs both sequentially. When invoked by `apply-product-release` the orchestrator runs only Plan Phase, aggregates plans from all sub-skills, fires one unified gate, then invokes each sub-skill's Execute Phase.

## Plan Phase

### Step 1: Detect Sync Mode
```

- [ ] **Step 3: Insert `## Plan Output Format` section between Step 2 and Step 3**

After the Step 2 block ends (ends with the "If nothing changed and mode is incremental, report 'Book content is up to date' and stop." prose), but BEFORE `### Step 3: Copy Chapters`, add:

````markdown
## Plan Output Format

When running in Plan Phase only (invoked by `apply-product-release` orchestrator), stop after Step 2 and emit a single plan block in this exact shape:

```markdown
### apply-book-update
- **Status**: changed | no-changes | error
- **Summary**: <e.g., "Incremental sync: 2 chapters changed, 1 image changed">
- **Mode**: migration | incremental | fresh
- **Changes**:
  | Type | Item | Reason |
  |------|------|--------|
  | update | ch-5-blueprints.md | diff detected vs source |
  | create | ch-14-the-meta-program.md | new chapter |
  | image  | workflow-progress.png | new image in source |
- **Risks**: (optional — e.g., "reader chrome leaked into ch-14 body; upstream fix recommended")
```

Do not write any files during Plan Phase. Do not prompt for confirmation. Return control to the caller.

## Execute Phase
````

- [ ] **Step 4: Verify the Step 3 header immediately follows the new Execute Phase header**

Run: `grep -n '^## \|^### Step' .claude/skills/apply-book-update/SKILL.md`

Expected output pattern:
```
## Workflow
## Plan Phase
### Step 1: Detect Sync Mode
### Step 2: Compare Files
## Plan Output Format
## Execute Phase
### Step 3: Copy Chapters
### Step 4: Copy Changed Images
### Step 5: Update Code Files (Structural Changes)
### Step 6: Verify Build
### Step 7: Report Changes
```

(Step numbers are unchanged in apply-book-update since we're not deleting any steps — only adding section dividers.)

- [ ] **Step 5: Commit**

```bash
git add .claude/skills/apply-book-update/SKILL.md
git commit -m "refactor(apply-book-update): split into Plan Phase and Execute Phase

Adds '## Plan Phase' (steps 1-2, detection + diff) and '## Execute Phase'
(steps 3-7, writes + audits) section headers. Adds '## Plan Output
Format' block so apply-product-release orchestrator can aggregate plans.

Zero behavior change when run standalone.
"
```

---

### Task 3: Refactor `ainative-stats` with Plan/Execute structure

**Files:**
- Modify: `.claude/skills/ainative-stats/SKILL.md`

**Refactor spec:**
- Add `## Plan Phase` before current "### 1. Verify Tools"
- Plan Phase contains Steps 1-7b (tool verification + all metric collection is read-only, no writes)
- Add `## Plan Output Format` block
- Add `## Execute Phase` before Step 8 (Write Report)
- Execute Phase contains Steps 8-10 plus the existing "## Updating the Website" section and "## Post-Update Verification" section

- [ ] **Step 1: Read current skill structure**

Run: `grep -nE '^## |^### [0-9]' .claude/skills/ainative-stats/SKILL.md`

Expected: `## Collection Steps`, `### 1. Verify Tools` through `### 10. Save Snapshot to`, `## Updating the Website`, `## Post-Update Verification`, `## Output`.

- [ ] **Step 2: Rename Collection Steps heading and insert Plan Phase header**

Find:
```
## Collection Steps

### 1. Verify Tools
```
Replace with:
```
## Workflow

This skill has two phases. When invoked standalone it runs both sequentially (collect metrics, then write report + propagate to website). When invoked by `apply-product-release` the orchestrator runs only Plan Phase, aggregates plans from all sub-skills, fires one unified gate, then invokes each sub-skill's Execute Phase.

## Plan Phase

### 1. Verify Tools
```

- [ ] **Step 3: Insert `## Plan Output Format` between Step 7b and Step 8**

After the "### 7b. Business Functionality" block ends (ends with the markdown table of primitives and their descriptions), but BEFORE `### 8. Write Report`, add:

````markdown
## Plan Output Format

When running in Plan Phase only (invoked by `apply-product-release` orchestrator), stop after Step 7b and emit a single plan block in this exact shape. Include computed deltas vs previous snapshot if `ainative-stats.md` exists.

```markdown
### ainative-stats
- **Status**: changed | no-changes | error
- **Summary**: <e.g., "LOC +2,400 · Tests +18 · Features 32/48 → 34/48">
- **Deltas**:
  | Metric | Previous | Current | Change |
  |--------|----------|---------|--------|
  | TypeScript LOC | 58,200 | 60,600 | +2,400 |
  | Tests | 812 | 830 | +18 |
  | Features shipped | 32/48 | 34/48 | +2 |
- **Website targets affected**: <list of files that will be updated in Execute Phase>
- **Risks**: (optional — e.g., "research.mdx has hand-edited historical snapshots; stat updates may conflict")
```

Do not write any files during Plan Phase. Do not prompt for confirmation. Return control to the caller.

## Execute Phase
````

- [ ] **Step 4: Verify structure**

Run: `grep -nE '^## |^### [0-9]' .claude/skills/ainative-stats/SKILL.md`

Expected output pattern:
```
## Target Project
## Architecture
## Workflow
## Plan Phase
### 1. Verify Tools
### 2. Collect LOC
### 3. Count Tests
### 4. Git Velocity
### 5. Feature Status
### 6. Infrastructure Counts
### 7. Quality Indicators
### 7b. Business Functionality
## Plan Output Format
## Execute Phase
### 8. Write Report
### 9. Trend Comparison
### 10. Save Snapshot to `stats/`
## Updating the Website
## Post-Update Verification
## Output
```

The existing `## Updating the Website` and `## Post-Update Verification` sections remain unchanged — they are conceptually part of Execute Phase (reached after Step 10).

- [ ] **Step 5: Commit**

```bash
git add .claude/skills/ainative-stats/SKILL.md
git commit -m "refactor(ainative-stats): split into Plan Phase and Execute Phase

Adds '## Plan Phase' (steps 1-7b, pure read-only metric collection) and
'## Execute Phase' (steps 8-10 + website propagation + verification)
section headers. Adds '## Plan Output Format' block with delta table so
apply-product-release orchestrator can show stats change before write.

Zero behavior change when run standalone.
"
```

---

## Phase B — Create new atomic skills via `skill-creator`

### Task 4: Create `apply-screengrabs` skill

**Files:**
- Create: `.claude/skills/apply-screengrabs/SKILL.md`
- Create: `.claude/skills/apply-screengrabs/references/rename-map.md`

**Source of truth:** The design spec, section "New Atomic Skill — `apply-screengrabs`".

- [ ] **Step 1: Invoke skill-creator**

Use the `Skill` tool with `skill-creator:skill-creator`.

Provide skill-creator with the following requirements (paste into the session):

```
I want to create a new skill called "apply-screengrabs".

Location: .claude/skills/apply-screengrabs/SKILL.md (project-level, committed to git)

Purpose: Sync product screenshots from /Users/manavsehgal/Developer/ainative/screengrabs/ to the marketing website at /Users/manavsehgal/Developer/ainative-business.github.io/public/screenshots/. On first run it performs a one-time migration to rename pre-rebrand filenames (dashboard-*.png etc.) to post-rebrand filenames (tasks-*.png etc.) AND update every site reference. On subsequent runs it diff-copies changed files and syncs alt-text from the product's manifest.json.

Trigger phrases: "apply screengrabs", "sync screenshots from product", "refresh screenshots", "update product screenshots", "migrate screenshot names", "sync screengrabs".

Structure the SKILL.md with:
  ## Source and Target (paths)
  ## Mode Detection (migration | incremental | fresh)
  ## Workflow
    ## Plan Phase
      ### Step 1: Detect mode
      ### Step 2: Compare files (hash-diff source vs target)
      ### Step 3: Build rename map (migration mode only)
      ### Step 4: Scan site for references to renames
    ## Plan Output Format (canonical block)
    ## Execute Phase
      ### Step 5: Execute rename pass (migration only) — grep-replace across src/pages/**/*.{astro,mdx}, src/components/**/*.{astro,tsx}, src/data/**/*.ts
      ### Step 6: Copy changed/new files to target
      ### Step 7: Delete stale orphans in target
      ### Step 8: Sync alt-text from manifest.json descriptions
      ### Step 9: Refresh references/manifest-cache.md
      ### Step 10: Build verification (npm run build)
  ## Key Rules (manifest.json is source of truth, never invent alt text, trailing-slash convention for docs-links-to-screenshots only, etc.)

Canonical Plan Output Format block:
  ### apply-screengrabs
  - **Status**: changed | no-changes | error
  - **Mode**: migration | incremental | fresh
  - **Summary**: one-line
  - **Changes**: table of (create | update | delete | rename) × file × reason
  - **Rename map** (migration only): table of old → new with per-file reference-count
  - **Risks**: e.g., "alt-text for 3 screenshots has been hand-customized; rename pass will overwrite"

Reference files under .claude/skills/apply-screengrabs/references/:
  - rename-map.md — stores the pre-migration old→new pairs (committed once)
  - manifest-cache.md — stores hash-per-file + last-sync timestamp (gitignored)

Evaluation criteria: given the current product state (67 screengrabs, post-rebrand names in manifest.json) and website state (pre-rebrand filenames in public/screenshots/), Plan Phase must emit a plan block in "migration" mode with the correct rename map and correct reference-count per file.
```

Work with skill-creator interactively until the SKILL.md is generated and the skill's description/frontmatter is tuned for reliable triggering.

- [ ] **Step 2: Create the initial rename-map reference file**

Based on the actual file delta between product and website, populate `.claude/skills/apply-screengrabs/references/rename-map.md` with the known pre-migration pairs.

First, compute the actual delta:

```bash
diff <(ls /Users/manavsehgal/Developer/ainative/screengrabs/*.png | xargs -n1 basename | sort) \
     <(ls /Users/manavsehgal/Developer/ainative-business.github.io/public/screenshots/*.png | xargs -n1 basename | sort) \
  | head -100
```

Then write `.claude/skills/apply-screengrabs/references/rename-map.md`:

```markdown
# Screenshot Rename Map (Pre-Migration)

Pairs of pre-rebrand (website, current) → post-rebrand (product, canonical) filenames.

This file is consumed by `apply-screengrabs` in migration mode. After the first successful run the skill will mark migration complete by setting the "mode" sentinel in `manifest-cache.md` to `incremental`. On subsequent runs this file is informational only.

## Rename Pairs

| Old (website) | New (product) | Notes |
|---|---|---|
| dashboard-list.png | tasks-list.png | /dashboard route renamed to /tasks |
| dashboard-below-fold.png | tasks-below-fold.png | same |
| dashboard-bulk-select.png | tasks-bulk-select.png | same |
| dashboard-card-edit.png | tasks-card-edit.png | same |
| dashboard-create-form-ai-applied.png | tasks-create-form-ai-applied.png | same |
| dashboard-create-form-ai-assist.png | tasks-create-form-ai-assist.png | same |
| dashboard-create-form-ai-breakdown.png | tasks-create-form-ai-breakdown.png | same |
| dashboard-create-form-empty.png | tasks-create-form-empty.png | same |
| dashboard-create-form-filled.png | tasks-create-form-filled.png | same |
| dashboard-detail.png | — | removed (detail view merged into card-edit) |
| dashboard-filtered.png | — | removed |
| dashboard-new-entity.png | — | removed |
| dashboard-sorted.png | — | removed |
| dashboard-card-detail.png | — | removed |
| cost-usage-list.png | costs-list.png | /cost-usage renamed to /costs |
| chat-model-selector.png | chat-model-picker.png | component renamed |
| chat-create-tab.png | — | removed (merged into chat-list) |
| chat-quick-access.png | — | removed |

(Add all remaining deltas from the diff command above.)

## Removed-from-Product Files

These files exist only in the website's current public/screenshots/ and have no product counterpart. They should be deleted in migration mode unless still referenced by the site (in which case the reference itself is stale and needs cleanup).

(List from diff command above.)
```

Complete the table with the real diff output. Any ambiguous pairs (where product renamed _and_ refactored the screenshot) should be marked and surfaced to the user for confirmation during the migration Plan Phase.

- [ ] **Step 3: Dry-run the skill in Plan Phase against current state**

Invoke the new skill: `/apply-screengrabs` (or via Skill tool).

Since this is the first run, it should detect **migration mode** and output a plan block showing:
- ~40-50 rename operations
- ~10 delete operations (orphans)
- Per-file reference counts (e.g., `dashboard-list.png → tasks-list.png: 3 references in src/pages/docs/tasks.mdx, 1 in src/components/sections/HeroScreenshot.astro, …`)

Do NOT approve the execute phase yet. Review the plan output, confirm it matches expectations.

- [ ] **Step 4: Adjust skill if plan output is wrong**

If the plan block is missing fields, has wrong table columns, or produces surprising rename pairs, re-invoke skill-creator with feedback:

```
The apply-screengrabs skill's Plan Phase output [describe issue]. Revise SKILL.md so [fix].
```

Iterate until the plan output is accurate.

- [ ] **Step 5: Commit the skill (WITHOUT running Execute Phase yet)**

```bash
git add .claude/skills/apply-screengrabs/
git commit -m "feat(skills): add apply-screengrabs atomic skill

Syncs product /screengrabs/ to website /public/screenshots/. First run
detects pre-rebrand names in the website (dashboard-*.png) vs
post-rebrand names in product (tasks-*.png) and plans a migration:
rename map + site-wide reference rewrite.

Plan Phase dry-run verified against current state (migration mode
detected, ~50 rename operations planned). Execute Phase not yet run
— will be triggered by the first apply-product-release invocation.
"
```

---

### Task 5: Create `apply-product-docs` skill

**Files:**
- Create: `.claude/skills/apply-product-docs/SKILL.md`
- Create: `.claude/skills/apply-product-docs/references/docs-mapping.md`
- Create: `.claude/skills/apply-product-docs/references/exemplar-doc.md`

- [ ] **Step 1: Create exemplar-doc reference from existing `tasks.mdx`**

Read the richest existing website docs page to extract the template shape:

```bash
cat /Users/manavsehgal/Developer/ainative-business.github.io/src/pages/docs/tasks.mdx
```

Abstract the shape into `.claude/skills/apply-product-docs/references/exemplar-doc.md`:

```markdown
# Exemplar MDX Doc Template

This is the canonical shape for website docs pages under `src/pages/docs/`. New pages created by `apply-product-docs` must follow this structure.

## Frontmatter

\`\`\`yaml
---
layout: ../../layouts/DocsLayout.astro
title: "<Feature Name> — Docs"
description: "<One-line SEO description>"
---
\`\`\`

## Imports

\`\`\`mdx
import BrowserFrame from '../../components/BrowserFrame.astro'
\`\`\`

(Add other component imports as required by the body.)

## Body structure

1. **H1 + intro paragraph** — 1-3 sentences framing the feature.
2. **Top-of-page screenshot** — wrapped in `<BrowserFrame>` with src from /screenshots/, alt from manifest.json description, caption optional.
3. **Sync-marker boundary**:
   \`\`\`mdx
   {/* SYNC:START */}

   ... body content imported from product /docs/features/<slug>.md ...

   {/* SYNC:END */}
   \`\`\`
4. **Website-only chrome below SYNC:END** — CTAs, crosslinks to /research/, footer hints. Never overwritten by sync.

## Rules enforced by apply-product-docs

- Content between SYNC:START and SYNC:END is auto-generated from product; edits here will be overwritten on next sync.
- Content outside SYNC markers is preserved across syncs.
- Image paths inside SYNC block are rewritten: /screengrabs/foo.png → /screenshots/foo.png.
- BrowserFrame usage: only the top-of-page screenshot; subsequent images are plain `![alt](/screenshots/foo.png)`.
- Frontmatter `layout` always points to DocsLayout.astro.
```

Verify this matches actual page structure — if `tasks.mdx` doesn't use `<BrowserFrame>` exactly this way, adjust the exemplar to match reality.

- [ ] **Step 2: Create docs-mapping reference**

Write `.claude/skills/apply-product-docs/references/docs-mapping.md`:

```markdown
# Docs Slug Mapping

Maps product doc slugs (from `/Users/manavsehgal/Developer/ainative/docs/manifest.json`) to website MDX pages.

## Direct 1:1 mappings

| Product slug | Product file | Website page | Status |
|---|---|---|---|
| chat | docs/features/chat.md | src/pages/docs/chat.mdx | tracked |
| costs | docs/features/cost-usage.md | src/pages/docs/costs.mdx | tracked |
| documents | docs/features/documents.md | src/pages/docs/documents.mdx | tracked |
| home-workspace | docs/features/home-workspace.md | src/pages/docs/index.astro | special — index page, not a standard mdx |
| inbox-notifications | docs/features/inbox-notifications.md | src/pages/docs/inbox.mdx | tracked |
| monitoring | docs/features/monitoring.md | src/pages/docs/monitoring.mdx | tracked |
| profiles | docs/features/profiles.md | src/pages/docs/profiles.mdx | tracked |
| projects | docs/features/projects.md | src/pages/docs/projects.mdx | tracked |
| schedules | docs/features/schedules.md | src/pages/docs/schedules.mdx | tracked |
| settings | docs/features/settings.md | src/pages/docs/settings.mdx | tracked |
| tables | docs/features/tables.md | src/pages/docs/tables.mdx | tracked |
| tasks | docs/features/tasks.md | src/pages/docs/tasks.mdx | tracked |
| workflows | docs/features/workflows.md | src/pages/docs/workflows.mdx | tracked |
| environment | docs/features/environment.md (if exists) | src/pages/docs/environment.mdx | tracked |
| agents | (derived from profiles + agent-intelligence) | src/pages/docs/agents.mdx | composite |

## Product-only (no website page)

These 8 product docs have no target on the website. `apply-product-docs` flags each as `new-product-doc-no-target` in Plan Phase and asks the user whether to create a new page, skip, or update the mapping.

| Product slug | Reason to flag |
|---|---|
| design-system | Internal design guide; probably skip |
| shared-components | Component library; probably skip |
| keyboard-navigation | Power-user reference; consider adding to website |
| user-guide | Tutorial content; consider adding as /docs/guide/ |
| agent-intelligence | May belong merged into agents.mdx |
| delivery-channels | New product surface; probably worth a page |
| provider-runtimes | Deep config reference; consider /docs/runtimes/ |
| tool-permissions | Security reference; consider /docs/permissions/ |

## Orphan targets (website-only)

Website pages that have no product slug. `apply-product-docs` reports these but does NOT delete them.

(None known as of 2026-04-18; refresh this list after each sync.)

## Content hash cache

(Generated by skill. Format: `product-slug: sha256-of-body-text`. Gitignored.)
```

- [ ] **Step 3: Invoke skill-creator for apply-product-docs**

Use the `Skill` tool with `skill-creator:skill-creator`.

Paste these requirements:

```
I want to create a new skill called "apply-product-docs".

Location: .claude/skills/apply-product-docs/SKILL.md (project-level, committed to git)

Purpose: Sync product feature docs from /Users/manavsehgal/Developer/ainative/docs/features/*.md (21 files) to website /Users/manavsehgal/Developer/ainative-business.github.io/src/pages/docs/*.mdx (17 pages). Preserves website-only chrome (CTAs, crosslinks) using {/* SYNC:START */} / {/* SYNC:END */} markers — only content inside markers is replaced. Rewrites image paths inside markers: /screengrabs/foo.png → /screenshots/foo.png. Flags product-only docs for user decision per run.

Reference files (already created):
  - references/docs-mapping.md — slug mapping table
  - references/exemplar-doc.md — target MDX template shape

Trigger phrases: "apply product docs", "sync product docs", "update feature docs from product", "refresh docs pages", "apply docs", "sync docs from product", "update website docs from product source".

Structure the SKILL.md with:
  ## Source and Target (paths)
  ## Slug Mapping (reference references/docs-mapping.md)
  ## Sync Marker Convention
    - {/* SYNC:START */} and {/* SYNC:END */} bound the auto-generated body
    - First-time pages are created with the marker pair wrapping the converted body
    - Existing pages: content between markers is replaced; content outside markers is preserved
    - Pages with no markers yet: first sync treats entire body as auto-generated and adds markers; show diff before write so user can confirm chrome isn't clobbered
  ## Workflow
    ## Plan Phase
      ### Step 1: Read product docs/manifest.json and enumerate slugs
      ### Step 2: For each slug, locate target (website page)
      ### Step 3: Compute content diff (body-only, markers-aware)
      ### Step 4: Flag product-only docs and orphan targets
    ## Plan Output Format (canonical block)
    ## Execute Phase
      ### Step 5: For each changed doc, read product markdown
      ### Step 6: Convert to MDX (rewrite frontmatter layout:, rewrite image paths, wrap in sync markers)
      ### Step 7: Merge into target preserving non-marker content
      ### Step 8: For first-time pages (no markers), add markers and commit separately with diff shown to user
      ### Step 9: Refresh references/docs-mapping.md hash cache
      ### Step 10: Build verification (npm run build)
  ## Key Rules (sync markers are inviolate, image path rewrite is /screengrabs/ → /screenshots/, layout: rewrite, no blind overwrite of chrome)

Canonical Plan Output Format block:
  ### apply-product-docs
  - **Status**: changed | no-changes | error
  - **Summary**: one-line
  - **Changes**: table of (create | update | orphan-no-source | new-product-doc-no-target) × page × reason
  - **First-time marker addition**: list of pages that will gain SYNC markers on this run (user should review first)
  - **Risks**: e.g., "3 pages have hand-edited content inside what will become SYNC block; first-sync will reset them"

Evaluation criteria: given current product state (21 feature docs) and website state (17 docs pages, none with SYNC markers yet), Plan Phase output in "first-sync" sub-mode must correctly identify all pages that need markers added, flag 8 product-only slugs, and list 0 orphan targets.
```

Iterate with skill-creator until SKILL.md is generated and triggering is tuned.

- [ ] **Step 4: Dry-run in Plan Phase**

Invoke the new skill. Expected: plan shows first-sync mode (since no pages have SYNC markers yet), lists all ~17 pages that need marker addition, and surfaces the 8 product-only slugs for user decision.

Review output, adjust if incorrect.

- [ ] **Step 5: Commit**

```bash
git add .claude/skills/apply-product-docs/
git commit -m "feat(skills): add apply-product-docs atomic skill

Syncs product /docs/features/*.md to website /src/pages/docs/*.mdx.
Uses {/* SYNC:START */} / {/* SYNC:END */} markers to preserve
website-only chrome across syncs. Rewrites image paths inside
markers (/screengrabs/ → /screenshots/).

Plan Phase dry-run verified against current state — first-sync
mode detected, ~17 pages flagged for marker addition, 8
product-only slugs surfaced for user decision.
"
```

---

## Phase C — Create the orchestrator

### Task 6: Create `apply-product-release` orchestrator skill

**Files:**
- Create: `.claude/skills/apply-product-release/SKILL.md`
- Create: `.claude/skills/apply-product-release/references/sub-skill-contracts.md`
- Modify: `.gitignore`

- [ ] **Step 1: Create the sub-skill contracts reference**

Write `.claude/skills/apply-product-release/references/sub-skill-contracts.md`:

````markdown
# Sub-Skill Contracts

This file documents the Plan/Execute contract every sub-skill must honor so the orchestrator can chain them.

## Required SKILL.md structure

Every sub-skill SKILL.md must contain these section headers in order:

```
## Plan Phase
(detection, diffing, no file writes)

## Plan Output Format
(canonical markdown block the sub-skill emits)

## Execute Phase
(file writes, copies, rebuilds, audits)
```

## Plan Output Format — canonical block

Every sub-skill's Plan Phase ends by emitting exactly this shape:

```markdown
### <skill-name>
- **Status**: changed | no-changes | error
- **Summary**: one-line description
- **Changes**:
  | Type | Item | Reason |
  |------|------|--------|
  | create | foo.mdx | new domain |
  | update | bar.md | content diff |
  | delete | baz.png | stale |
- **Risks**: (optional) drift warnings, forbidden patterns, etc.
```

Additional fields are permitted per-skill (e.g., `apply-screengrabs` adds `- **Mode**` and `- **Rename map**`; `ainative-stats` adds `- **Deltas**`). The orchestrator concatenates whatever each sub-skill emits and presents the full aggregate.

## Invocation pattern

The orchestrator invokes each sub-skill via the `Skill` tool, instructing the skill to run Plan Phase only. Since skills don't accept parameters, this instruction is part of the orchestrator's prose: "When you invoke Skill(apply-book-update), tell it to run only the Plan Phase section and return control."

Each sub-skill's SKILL.md explicitly states this behavior in its `## Plan Phase` intro.

## Sub-skill order (for Execute Phase)

1. `apply-screengrabs` — images first, because docs/book/research reference them
2. `apply-product-docs` — docs may reference newly-renamed screenshots
3. `apply-api-docs` — independent
4. `apply-book-update` — independent
5. `ainative-stats` — last; propagates counts into files that earlier steps may have touched

## In-skill confirmation gates are removed

`apply-api-docs` previously had Step 5 (User Confirmation Gate) — deleted during Phase A refactor. Orchestrator owns all gating. Standalone invocations of any sub-skill prompt at the Plan→Execute boundary with a single gate.

## Partial approval

User can reject specific sub-skills during the aggregate gate ("proceed but skip stats"). Orchestrator drops that sub-skill from Execute Phase and reports the skip in the final summary.
````

- [ ] **Step 2: Invoke skill-creator for the orchestrator**

Use the `Skill` tool with `skill-creator:skill-creator`.

Paste these requirements:

```
I want to create a new skill called "apply-product-release".

Location: .claude/skills/apply-product-release/SKILL.md (project-level, committed to git)

Purpose: Orchestrator skill that chains 5 sub-skills (apply-screengrabs, apply-product-docs, apply-api-docs, apply-book-update, ainative-stats) to apply a full product release to the marketing website. Runs all 5 in Plan Phase only, aggregates plans into one report, gets one user approval, then runs each in Execute Phase in order. Ends with npm run build + browser smoke test on 8 critical routes.

Trigger phrases: "apply product release", "sync product to website", "update website from product", "product release", "refresh everything from ainative", "ship product changes", "refresh website from product", "apply release".

Reference file (already created): references/sub-skill-contracts.md

Structure the SKILL.md with:

  ## Source and Target Repos
    - Product: /Users/manavsehgal/Developer/ainative/
    - Website: /Users/manavsehgal/Developer/ainative-business.github.io/

  ## Pipeline Overview (7 stages diagram)

  ## Stage 1: Preconditions
    - Product repo: on main, warn if dirty but allow continue
    - Website repo: on main, HARD STOP if dirty
    - Read product CHANGELOG.md top entry (informational, not gating)
    - Verify all 5 sub-skills exist at .claude/skills/{apply-screengrabs,apply-product-docs,apply-api-docs,apply-book-update,ainative-stats}/SKILL.md
    - Verify claude-in-chrome MCP tool is available (for Stage 6) — if not, prompt user whether to skip smoke or abort

  ## Stage 2: Plan Phase
    - For each sub-skill in [screengrabs, product-docs, api-docs, book-update, stats]:
      - Invoke Skill(<name>) and instruct it to run only its ## Plan Phase section
      - Capture the emitted plan block verbatim
    - Aggregate all 5 blocks into unified plan

  ## Stage 3: Approval Gate
    - Present unified plan with totals (creates/updates/deletes/renames across all skills)
    - List any risks flagged by sub-skills
    - Ask: "Proceed? / Abort / Skip [skill-name]"
    - Support partial approval — record which sub-skills were approved

  ## Stage 4: Execute Phase
    - For each approved sub-skill, in order [screengrabs, product-docs, api-docs, book-update, stats]:
      - Invoke Skill(<name>) and instruct it to run only its ## Execute Phase section
      - Capture result summary
    - If any sub-skill reports error, STOP — do not proceed to build

  ## Stage 5: Build Verification
    - cd /Users/manavsehgal/Developer/ainative-business.github.io && npm run build
    - Must exit 0; show last 20 lines on failure

  ## Stage 6: Browser Smoke
    - Start preview server: npm run preview -- --port 4321 (background, capture PID)
    - Wait for "Local: http://localhost:4321/" in log
    - Use claude-in-chrome tabs_context_mcp → tabs_create_mcp to open a fresh tab
    - For each of 8 routes:
        /, /docs/, /docs/tasks/, /docs/api/, /docs/api/tasks/, /book/, /book/ch-1-from-hierarchy-to-intelligence/, /research/ai-transformation/
      - navigate
      - wait_for DOMContentLoaded
      - read_console_messages (filter out known-noise patterns)
      - Route-specific assertions via read_page (see design spec for per-route check list)
      - take_screenshot for /, /docs/tasks/, /book/ch-1-*/ to smoke-screenshots/YYYY-MM-DD/<route-slug>.png
    - Teardown: kill preview server PID regardless of pass/fail
    - Smoke failure stops before commit-suggestion emission

  ## Stage 7: Report
    - Unified markdown report:
      - Per-skill changes
      - Build result
      - Smoke result (pass/fail per route + any warnings)
      - Suggested commit message (see template below)
    - Do NOT auto-commit

  ## Suggested Commit Message Template
  ```
  Apply product release: <concise summary>

  - Screengrabs: <N changed, M renamed>
  - Docs: <N pages updated>
  - API: <N endpoints, M domains>
  - Book: <N chapters, M images>
  - Stats: <LOC delta>, <features delta>

  <any risks flagged>
  ```

  ## Key Rules
    - Pure orchestrator — no content logic of its own
    - Always run all 5 sub-skills in Plan Phase (simplicity > premature optimization)
    - Single aggregate gate (not per-sub-skill)
    - Partial approval supported
    - No auto-commit
    - Browser smoke is non-optional on a healthy setup; skippable only with loud warning if chrome tools unavailable

Evaluation criteria: invoking "apply product release" against current state produces a single aggregate plan containing contributions from all 5 sub-skills. The plan shows total creates/updates/deletes. User gate fires exactly once.
```

Iterate with skill-creator until the skill is generated and triggering is tuned.

- [ ] **Step 3: Remove `.gitignore` line for `apply-product-release/` and add cache exclusions**

Open `.gitignore`. Find and remove the line:
```
.claude/skills/apply-product-release/
```

In the same section (around line 12-13), add:
```
.claude/skills/*/references/manifest-cache.md
.claude/skills/*/references/docs-mapping.md
```

Verify with:
```bash
grep -n 'apply-product-release\|manifest-cache\|docs-mapping' /Users/manavsehgal/Developer/ainative-business.github.io/.gitignore
```

Expected: only the two new cache-exclusion lines appear; no `apply-product-release/` line.

- [ ] **Step 4: Commit orchestrator skill + .gitignore change**

```bash
git add .claude/skills/apply-product-release/ .gitignore
git commit -m "feat(skills): add apply-product-release orchestrator + untrack caches

Adds the reconstructed apply-product-release orchestrator that chains
5 sub-skills (screengrabs, product-docs, api-docs, book-update, stats)
through a plan → approve → execute → build → smoke → report pipeline.

.gitignore: removes the orphan .claude/skills/apply-product-release/
entry (orchestrator is now tracked) and adds per-skill cache-file
exclusions so sync state doesn't churn git on every run.
"
```

---

## Phase D — End-to-end integration

### Task 7: First end-to-end orchestrator run

This is the payoff task. Invoking `/apply-product-release` should cover the pending screengrab rename migration, product docs first-sync (marker addition), any api/book diffs, and a stats refresh — all under one aggregate plan.

**Files (no skill changes here — this is an invocation):**
- Many website files will be touched by sub-skills. Do not edit by hand; let the orchestrator run.

- [ ] **Step 1: Verify preconditions manually before invocation**

Run:
```bash
cd /Users/manavsehgal/Developer/ainative && git status && git rev-parse --abbrev-ref HEAD
cd /Users/manavsehgal/Developer/ainative-business.github.io && git status && git rev-parse --abbrev-ref HEAD
```

Both repos must be on `main`. Website repo must be clean (no uncommitted changes). Product repo may have uncommitted work; orchestrator will warn but proceed.

- [ ] **Step 2: Verify claude-in-chrome is connected**

Ask user to confirm claude-in-chrome extension is active in a chrome tab. If not, user must start chrome and authorize the extension before Stage 6 can run. Orchestrator will detect and prompt.

- [ ] **Step 3: Invoke the orchestrator**

Use the `Skill` tool: `apply-product-release`. Or say "apply product release" as the user.

Expected: orchestrator runs Preconditions (stage 1), then invokes each sub-skill in Plan Phase (stage 2), then presents one aggregate plan with:

- `apply-screengrabs`: migration mode, ~50 renames, alt-text refresh for 67 files
- `apply-product-docs`: first-sync mode, ~17 pages get SYNC markers, 8 product-only slugs flagged
- `apply-api-docs`: whatever the current drift is (read manifest, diff)
- `apply-book-update`: whatever the current drift is (Chapter Manifest vs source)
- `ainative-stats`: LOC/tests/features deltas vs last snapshot

- [ ] **Step 4: Review aggregate plan carefully**

Before approving Execute:
- Check rename map for any clobbers of hand-customized alt text
- Check 8 product-only docs — decide per-slug: skip / create new page / update mapping
- Check stats deltas make sense (not hugely negative, no impossible numbers)
- Check book-update drift audit for any "forbidden pattern" hits (e.g., `maven.com`, `founding member`)

If any risk is unacceptable, abort or skip that sub-skill.

- [ ] **Step 5: Approve and let execute phase run**

Orchestrator runs all 5 (or approved subset) sequentially, reports per-skill completion.

- [ ] **Step 6: Build verification runs automatically (Stage 5)**

Orchestrator runs `npm run build` in the website repo. Must exit 0. If it fails, stop and investigate — likely cause is a missed image reference in the rename pass (Task 4), or a broken MDX import in the product-docs first-sync (Task 5).

- [ ] **Step 7: Browser smoke runs automatically (Stage 6)**

Orchestrator starts preview server, runs the 8-route smoke. Review output:
- Any console errors or warnings from app code = fail
- Screenshots saved to `smoke-screenshots/YYYY-MM-DD/` for visual archive

If smoke fails, orchestrator stops. Fix the underlying issue and re-invoke (sub-skills are idempotent).

- [ ] **Step 8: Review suggested commit message**

Orchestrator emits a commit message per the template. User reviews and adjusts.

- [ ] **Step 9: Stage and commit the changes manually**

```bash
cd /Users/manavsehgal/Developer/ainative-business.github.io
git status
git add <files orchestrator report mentioned>
git commit -m "<use orchestrator's suggested message, edited as needed>"
```

Do NOT blindly `git add -A` — the report tells you exactly what changed per sub-skill.

- [ ] **Step 10: Push when ready (user's call)**

```bash
git push origin main
```

This is a regular user action, not an orchestrator action.

---

## Phase E — Post-run cleanup

### Task 8: Verify gitignored caches aren't tracked, post-run audit

- [ ] **Step 1: Confirm manifest-cache files are gitignored**

```bash
cd /Users/manavsehgal/Developer/ainative-business.github.io
git check-ignore .claude/skills/apply-screengrabs/references/manifest-cache.md
git check-ignore .claude/skills/apply-product-docs/references/docs-mapping.md
```

Expected: both commands output the paths (indicating they ARE ignored). Exit status 0.

If any returns non-ignored, fix `.gitignore` and commit.

- [ ] **Step 2: Confirm orchestrator skill IS tracked**

```bash
git ls-files .claude/skills/apply-product-release/SKILL.md
```

Expected: path is printed (file is tracked). If empty, run `git add` and commit.

- [ ] **Step 3: Run standalone sub-skill sanity check**

Invoke each sub-skill standalone to confirm it still works outside the orchestrator:

- `/apply-api-docs` — should detect no-changes (since orchestrator just ran it), emit plan, offer confirmation gate at Plan→Execute boundary, user declines
- `/apply-book-update` — same
- `/ainative-stats` — may show small deltas (time passed), emit plan, user declines

If any sub-skill fails to produce a plan block or prompts mid-plan, the refactor in Phase A has a bug — fix the affected SKILL.md and commit.

- [ ] **Step 4: Archive the first-run report**

Save the full orchestrator output (plan + execute + smoke summary) to `docs/superpowers/reports/2026-04-18-first-apply-product-release.md` for future reference.

```bash
mkdir -p docs/superpowers/reports
# Paste orchestrator output into the file
```

- [ ] **Step 5: Commit the report and any cleanup**

```bash
git add docs/superpowers/reports/
git commit -m "docs(reports): archive first apply-product-release run output

Full orchestrator output from the inaugural end-to-end run: plan
aggregation across 5 sub-skills, migration-mode screengrab rename,
first-sync product-docs marker addition, stats refresh, build + smoke
pass. Reference for tuning future runs.
"
```

---

## Appendix — Rollback strategy

If Phase A refactors break sub-skills standalone, revert individually:

```bash
git log --oneline .claude/skills/apply-api-docs/SKILL.md | head -3
# find the last pre-refactor commit hash for that skill
git checkout <hash> -- .claude/skills/apply-api-docs/SKILL.md
git commit -m "revert: apply-api-docs refactor (rolled back pending fix)"
```

If Phase C orchestrator has a structural bug, disable it by restoring the `.gitignore` line:

```bash
# In .gitignore:
# re-add .claude/skills/apply-product-release/
# rm -rf .claude/skills/apply-product-release/
git commit -am "temp: disable apply-product-release pending fix"
```

Sub-skills remain usable during rollback — each is independent.

---

## Self-Review Notes

- **Spec coverage:** all 5 decisions from the spec are implemented as tasks. Every design section in the spec (skill map, pipeline, plan-mode contract, stage 6 smoke, new skills, refactors, directory layout, .gitignore, rollout) has a corresponding task.
- **Placeholders scanned:** no TBD / TODO / "add error handling" / "similar to Task N" patterns. Each refactor step shows exact find/replace text. Each skill-creator invocation includes complete requirements prompt.
- **Type consistency:** the `### <skill-name>` Plan Output Format header shape is identical across Task 1, Task 2, Task 3 (refactors) and Tasks 4, 5, 6 (new skills). Stage numbers in Task 6 match the pipeline definition in Task 6 Step 2 and in the design spec. Sub-skill execute order ([screengrabs, product-docs, api-docs, book-update, stats]) is identical in Task 6, Task 7 Step 3, and the contracts reference file.
- **TDD adaptation:** since this plan produces markdown SKILL.md files rather than executable code, "test" steps are grep-based structural verification (grep for section headers), and Plan Phase dry-runs against real state. The "fails then passes" cadence is preserved: Step 1 typically confirms a structural expectation; Step 2 modifies; later steps verify the modification.
