---
name: apply-product-docs
description: Sync product feature documentation from /Users/manavsehgal/Developer/ainative/docs/features/*.md (21 files) to the marketing website at /Users/manavsehgal/Developer/ainative-business.github.io/src/pages/docs/*.mdx (13-17 pages). Uses {/* SYNC:START */} and {/* SYNC:END */} markers to preserve website-only chrome (CTAs, crosslinks, design-system callouts) while replacing auto-generated body content. Rewrites image paths /screengrabs/ → /screenshots/ inside markers. Flags product-only docs (delivery-channels, provider-runtimes, tool-permissions, etc.) for user decision per run. Use whenever the user says "apply product docs", "sync product docs", "update feature docs from product", "refresh docs pages", "apply docs", "sync docs from product", "update website docs from product source", "docs are stale", or any request to update the website's docs subsite from the product's feature reference. Also trigger as part of "apply product release".
---

# Apply Product Docs

Syncs product feature documentation into the website's `/docs/` subsite. The product repo owns the content of each doc (what the feature does, how to use it); the website owns the chrome (CTAs, crosslinks, design-system framing). The boundary between them is marked by `{/* SYNC:START */}` and `{/* SYNC:END */}` comment tags inside each MDX page.

## Why this matters

Product documentation drifts when it's maintained in two places. Historically, website docs were hand-copied from the product, then both evolved independently — the product added features; the website added marketing crosslinks; the markdown diverged. This skill makes the product the source of truth for body content, and makes the website the source of truth for its own chrome.

The sync-marker convention enforces this without requiring either side to compromise:
- Inside markers: auto-generated from product, replaced on every sync
- Outside markers: website-owned, preserved forever

## Source and Target

| | Path |
|---|---|
| Product feature docs | `/Users/manavsehgal/Developer/ainative/docs/features/*.md` (21 files) |
| Product manifest | `/Users/manavsehgal/Developer/ainative/docs/manifest.json` |
| Website docs | `/Users/manavsehgal/Developer/ainative-business.github.io/src/pages/docs/*.mdx` (17 pages) |
| Slug mapping | `references/docs-mapping.md` — read this BEFORE any sync decision |
| Exemplar template | `references/exemplar-doc.md` — canonical MDX shape for new/updated pages |

## Sync Modes

The skill detects one of two modes automatically.

| Mode | Detected when | Behavior |
|---|---|---|
| **first-sync** | No website page has `{/* SYNC:START */}` / `{/* SYNC:END */}` markers yet. | Propose marker placement diff per page, require explicit user confirmation before writing markers or regenerating body. |
| **incremental** | All synced pages have markers. | For each source file, diff against last-synced hash (from cache). Replace content inside markers only if source changed. |

## Workflow

This skill has two phases. When invoked standalone it runs both sequentially with one user gate between them. When invoked by `apply-product-release` the orchestrator runs only Plan Phase, aggregates plans from all sub-skills, fires one unified gate, then invokes each sub-skill's Execute Phase.

## Plan Phase

### Step 1: Load slug mapping and manifest

Read `references/docs-mapping.md` to load the authoritative slug map. Read the product's `/docs/manifest.json` to get the current 21 sections. Cross-check: any new section in manifest not in the mapping table is a **new-product-doc** that wasn't in the last sync — flag for user decision.

### Step 2: Detect mode

```bash
# count pages that have sync markers
grep -l 'SYNC:START' /Users/manavsehgal/Developer/ainative-business.github.io/src/pages/docs/*.mdx | wc -l
```

- If 0 pages have markers → mode is **first-sync**
- If all mapped pages have markers → mode is **incremental**
- If some have markers and some don't → **mixed** — treat unmarked pages as first-sync sub-operations within this run; mark which ones need first-sync treatment in the plan

### Step 3: Compute per-page status

For each slug in `references/docs-mapping.md` "Direct mappings" section, determine:

| Status | Condition |
|---|---|
| `unchanged` | Source hash matches `manifest-cache.md` AND (incremental mode OR markers already exist) |
| `body-diff` | Source hash differs from cache; Execute Phase will replace content inside markers |
| `first-sync-needed` | Target page exists but has no SYNC markers |
| `new-target-needed` | Mapping entry exists but target page doesn't exist yet |
| `missing-source` | Target page exists, mapping exists, but source file missing (unexpected — flag) |

### Step 4: Classify product-only and orphans

From `references/docs-mapping.md`:

- **Product-only docs** (7 slugs): `delivery-channels`, `provider-runtimes`, `tool-permissions`, `design-system`, `shared-components`, `keyboard-navigation`, `playbook`. For each, surface in Plan Output with the suggested action from the mapping file. User decides per-run.
- **Website-only pages** (listed in mapping file, e.g., `dashboard.mdx`, `environment.mdx`, `api/*`): reported for awareness, never modified by this skill.

### Step 5: Scan body for image path rewrites

For each page in `body-diff` or `first-sync-needed` status, scan the source markdown for `/screengrabs/` image references. The sync step will rewrite these to `/screenshots/`. Count rewrites per page for the Plan Output.

### Step 6: Detect first-sync marker placement

For each page in `first-sync-needed` status, propose where `{/* SYNC:START */}` and `{/* SYNC:END */}` should be inserted:

- **SYNC:START** goes after the first `<BrowserFrame>` element (the hero screenshot) and one blank line
- **SYNC:END** goes before any trailing website-only chrome — typically before a `<Callout>`, a crosslink paragraph, a "Related" section, or end-of-file if no chrome exists

Emit the proposed placement in the plan. Rely on the user to override per-page if their chrome boundary is in an unexpected spot.

## Plan Output Format

When running in Plan Phase only (invoked by `apply-product-release` orchestrator), stop after Step 6 and emit a single plan block in this exact shape:

```markdown
### apply-product-docs
- **Status**: changed | no-changes | error
- **Mode**: first-sync | incremental | mixed
- **Summary**: <one-line: e.g., "First-sync: 13 pages need markers, 2 body diffs, 7 product-only flagged">
- **Page status**:
  | Slug | Page | Status | Body diff | Image rewrites |
  |---|---|---|---|---|
  | tasks | tasks.mdx | body-diff | +12 / -3 lines | 4 |
  | chat | chat.mdx | first-sync-needed | — | 6 |
  | inbox-notifications | inbox.mdx | unchanged | — | — |
- **Marker placement (first-sync pages only)**:
  | Page | SYNC:START after | SYNC:END before |
  |---|---|---|
  | tasks.mdx | line 13 (after hero BrowserFrame) | EOF |
  | chat.mdx | line 15 | line 42 (before `<Callout>` at EOF) |
- **Product-only docs (user decision required)**:
  | Slug | Suggested action | User decision |
  |---|---|---|
  | delivery-channels | merge into settings.mdx | TBD |
  | provider-runtimes | create /docs/runtimes/ | TBD |
  | playbook | create /docs/guide/ | TBD |
- **Risks**: (e.g., "5 pages have hand-authored content after the hero image that will fall inside proposed SYNC block — user must confirm boundary placement")
```

Do not write any files during Plan Phase. Do not prompt for confirmation. Return control to the caller.

## Execute Phase

### Step 7: Apply first-sync marker placement (first-sync and mixed modes)

For each approved page with `first-sync-needed` status:

1. Read current page content.
2. Insert `{/* SYNC:START */}` at approved position; `{/* SYNC:END */}` at approved position.
3. Content between markers is the CURRENT body; no replacement yet in this step.
4. Save page. This is a separate edit from the body sync so the diff is auditable.

### Step 8: Sync body content for changed pages

For each page in `body-diff` or `first-sync-needed` (post-marker) status:

1. Read product source markdown: `/Users/manavsehgal/Developer/ainative/docs/features/<source-file>.md`.
2. Strip frontmatter (product markdown may have YAML frontmatter; website gets its own frontmatter).
3. Rewrite image paths: `/screengrabs/foo.png` → `/screenshots/foo.png`. Also handle relative paths like `./screengrabs/foo.png`.
4. Read target website page, extract content between `{/* SYNC:START */}` and `{/* SYNC:END */}`.
5. Replace with converted product body.
6. Save page.

**Important:** do NOT touch the hero `<BrowserFrame>` (above SYNC:START) — it's website-owned and hand-positioned. The product body starts with the first heading after whatever hero context the website already has.

### Step 9: Handle product-only decisions

Based on user decisions from the Plan Phase approval:

- **create new page** — scaffold a new MDX file at `src/pages/docs/<new-slug>.mdx` following the exemplar template. Place the product body inside SYNC markers. Add minimal website chrome (title, intro, optional hero screenshot if manifest provides one).
- **merge into existing page** — append product body content to the existing page under a new H2 inside the target's SYNC block. Preserve target's existing content above the merged section.
- **skip** — do nothing; record the skip in the cache so future runs don't re-ask.

### Step 10: Refresh cache

Write `.claude/skills/apply-product-docs/references/manifest-cache.md`:

```markdown
# apply-product-docs cache

Last sync: <ISO-8601>
Mode on last sync: first-sync | incremental

## Source hashes

| Product file | SHA-256 | Synced to |
|---|---|---|
| features/tasks.md | abc123... | tasks.mdx |
| features/chat.md | def456... | chat.mdx |

## User decisions on product-only docs

| Slug | Decision | When |
|---|---|---|
| provider-runtimes | skip | 2026-04-18 |
| playbook | create /docs/guide/ | 2026-04-18 |
```

The "User decisions" section persists across runs so the skill doesn't re-ask each time.

### Step 11: Build verification

```bash
cd /Users/manavsehgal/Developer/ainative-business.github.io
npm run build 2>&1 | tail -20
```

Must exit 0. Common failure modes:
- Missing component import (e.g., product body uses a component the website hasn't imported)
- Broken image reference (slipped past the `/screengrabs/` → `/screenshots/` rewrite — check for subtle variants like `screengrab` singular or relative paths)
- MDX parser error on product markdown syntax the website's Astro version doesn't accept

### Step 12: Report

Emit a summary:

```markdown
## apply-product-docs complete

- **Mode**: <mode>
- **Pages marked** (first-sync): <N>
- **Pages updated** (body-diff): <N>
- **Pages created** (new targets): <N>
- **Pages skipped** (unchanged or user-declined): <N>
- **Image rewrites**: <N screenshots paths fixed>
- **Product-only decisions recorded**: <N>
- **Build**: ✓ (or ✗ with details)
```

## Key Rules

- **Sync markers are inviolate.** Never edit content outside `{/* SYNC:START */}` / `{/* SYNC:END */}`. Never move the markers without explicit user approval (the only time the skill places or moves markers is Step 7, which gates on per-page user confirmation).
- **Image path rewrite is exactly `/screengrabs/` → `/screenshots/`.** Not case-insensitive; not regex-general. If the product uses a different convention (e.g., `/assets/`), that's out of scope and should be normalized upstream.
- **Frontmatter is website-owned.** Product markdown frontmatter is stripped, not copied. The website's `layout:`, `title:`, and `description:` are authoritative. If the product body needs a new title, fix it upstream; don't try to sync titles.
- **Hero `<BrowserFrame>` is website-owned.** The first image in a page is a marketing/framing choice; the website picks it, with alt-text from product manifest. The skill doesn't touch the hero.
- **Product-only docs default to "user decision required" every run.** Unless the user explicitly said "skip" in a previous run (persisted in cache). This prevents silent drift when the product adds new feature docs.
- **Build must pass.** Don't report success if the build fails. Image reference slips and MDX syntax issues show up here; investigate rather than suppress.
- **Standalone vs orchestrated.** When running standalone, this skill prompts at the Plan → Execute boundary. When invoked by `apply-product-release`, it runs Plan Phase only and returns a plan block; the orchestrator fires the unified gate.
