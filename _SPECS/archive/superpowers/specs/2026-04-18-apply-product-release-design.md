# Apply Product Release — Skill Consolidation Design

**Date:** 2026-04-18
**Status:** Draft — pending user review
**Author:** Brainstormed with Claude (Opus 4.7, 1M context)

## Context

The `apply-product-release/` skill was previously gitignored (see `.gitignore` line 12, added in commit `930b764`) and has been lost — replacing a prior `apply-screengrabs/` entry that was also gitignored. Git history has no copy because it was never tracked. Six commits titled "Apply product release: …" reveal what the workflow used to do (refresh 44–67 screenshots, update docs, landing page, book, API docs), but the orchestrator instructions themselves are gone.

Meanwhile, three tracked, specialized skills exist and are well-designed:

- `apply-api-docs` — product API routes/validators/schema → website `/docs/api/` MDX pages
- `apply-book-update` — product `book/chapters/` + `book/images/` → website book subsystem
- `ainative-stats` — product metrics (LOC, tests, velocity, business primitives) → report + propagate to 10 website locations

These three cover roughly 60% of the "apply a product release to the marketing site" surface. The missing 40% — screengrab sync with rename migration, product feature-doc sync, landing-page/research refresh, end-to-end browser smoke — either isn't covered or is handled ad hoc.

## Goal

Reconstruct and refine `apply-product-release` as a **pure orchestrator**, add **two new atomic skills** (`apply-screengrabs`, `apply-product-docs`), and **refactor the three existing skills** with a lightweight Plan/Execute mode contract so the orchestrator can run them all in planning mode, present one unified plan, and execute on approval. End the pipeline with a browser smoke test so console errors and broken asset references fail loudly before the user commits.

## Non-Goals

- Not replacing the three existing skills. They remain runnable standalone.
- Not auto-committing. Orchestrator proposes a commit message; user stages and commits.
- Not adding a CI job. This is a local, human-initiated workflow.
- Not covering release detection via webhooks or RSS. User triggers the orchestrator manually; sub-skills do their own diffing.

## Decisions

| Decision | Choice | Rationale |
|---|---|---|
| Strategy | Pure orchestrator + 2 new atomic skills | Modular, each runnable standalone; orchestrator just sequences and gates |
| Screengrab naming | Rename & migrate (product names win) | One-time migration pain; product and website stay name-locked forever after |
| Change detection | Always run all, delegate diffing to sub-skills | Simplest model; no state file to keep honest; ~5s cost per clean sub-skill is acceptable |
| Confirmation gate | Single unified plan, then execute | One release = one review; matches mental model from historical commits |
| Terminal step | Browser smoke after build | Failing loudly beats failing silently; catches broken asset refs and console errors before commit |

## Final Skill Map

| # | Skill | Status | Role |
|---|-------|--------|------|
| 1 | `apply-screengrabs` | new, atomic | Product `/screengrabs/` + `manifest.json` → website `/public/screenshots/`; one-time rename migration, diff-copy thereafter |
| 2 | `apply-product-docs` | new, atomic | Product `/docs/features/*.md` → website `/src/pages/docs/*.mdx`; 13 direct 1:1 mappings, 8 product-only docs flagged per run |
| 3 | `apply-api-docs` | existing, + plan-mode | Unchanged behavior standalone; gains `## Plan Phase` / `## Execute Phase` headers; in-skill user gate removed |
| 4 | `apply-book-update` | existing, + plan-mode | Same refactor |
| 5 | `ainative-stats` | existing, + plan-mode | Same refactor |
| — | `apply-product-release` | new, orchestrator | Runs all 5 in plan mode, aggregates, user approves once, executes, builds, browser-smokes, reports |

## Orchestrator Pipeline

Six stages, executed in order.

```
1. Preconditions      — repo cleanliness checks
2. Plan Phase          — invoke every sub-skill in Plan Phase only, aggregate
3. Approval Gate       — one user confirmation; partial-approval supported
4. Execute Phase       — run approved sub-skills in order (see below)
5. Build Verification  — npm run build must exit 0
6. Browser Smoke       — 8-route spot check via claude-in-chrome
7. Report              — unified summary + suggested commit message
```

### Execute order (matters)

1. `apply-screengrabs` — images first, because docs/book/research reference them
2. `apply-product-docs` — docs may reference newly-renamed screenshots
3. `apply-api-docs` — independent
4. `apply-book-update` — independent (book images already synced in step 1? No — book images live under `/book/images/`, separate directory, synced by apply-book-update itself)
5. `ainative-stats` — last, because it propagates counts into files (Proof, timeline, research.mdx, SVGs) that earlier steps may have touched

## Plan-Mode Contract

Sub-skills are invoked via the `Skill` tool, which does not accept parameters. "Plan mode" is therefore a **structural contract** in each sub-skill's `SKILL.md`.

### Required section headers

Every sub-skill's SKILL.md must contain, in order:

```markdown
## Plan Phase
(detection, diffing, no file writes)
…ordered steps…

## Plan Output Format
(canonical markdown block the sub-skill emits to summarize its plan)

## Execute Phase
(file writes, copies, rebuilds, audits)
…ordered steps…
```

### Plan Output Format block

Every sub-skill ends its Plan Phase by emitting exactly this shape, so the orchestrator can concatenate five of them:

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
- **Risks**: (optional) drift warnings, forbidden patterns, new-product-docs-no-target, etc.
```

### In-skill user gates are removed

`apply-api-docs` Step 5 ("User Confirmation Gate") is deleted. The orchestrator owns all gating. When a sub-skill runs standalone, one universal gate fires at the Plan → Execute boundary.

### Orchestrator invocation pattern (pseudocode, lives in `apply-product-release/SKILL.md`)

```
for each sub-skill in [screengrabs, product-docs, api-docs, book-update, stats]:
  invoke Skill(<name>) — run "## Plan Phase" section only
  capture emitted plan block

aggregate 5 blocks → unified plan
present plan to user → wait for approval (full / partial / abort)

for each approved sub-skill (in order):
  invoke Skill(<name>) — run "## Execute Phase" section
  capture result summary

run npm run build
run browser smoke (see below)
emit final report
```

## Stage 6 — Browser Smoke

### Server setup

```bash
cd /Users/manavsehgal/Developer/ainative-business.github.io
npm run build
npm run preview -- --port 4321 &
# wait for "Local: http://localhost:4321/" in the preview log
```

### Tool choice

`claude-in-chrome` MCP tools (lighter than Playwright for spot-check smoke): `navigate`, `read_console_messages`, `read_page`, `take_screenshot`, `wait_for`.

### Route matrix — 8 routes curated to cover every sub-skill's output

| Route | Covers | Assertions |
|---|---|---|
| `/` | stats, screengrabs | Proof section metric count matches `ainative-stats` output; hero screenshot loads |
| `/docs/` | docs landing, nav | All sidebar items resolve (no broken links) |
| `/docs/tasks/` | product-docs | Page contains a `<BrowserFrame>` with tasks screenshot; alt-text matches `manifest.json` description |
| `/docs/api/` | api-docs landing | Domain cards render with current endpoint counts |
| `/docs/api/tasks/` | api-docs deep | Quick Start renders; CodeExample TS/Python tabs present |
| `/book/` | book landing | Chapter count in hero matches `CHAPTERS.length`; no stale "N chapters" prose |
| `/book/ch-1-from-hierarchy-to-intelligence/` | book + attribution | "by Manav Sehgal" byline present; "CC BY-NC 4.0" preface renders |
| `/research/ai-transformation/` | research snapshot | Page loads. Do NOT fail on stat drift — historical snapshot |

### Per-route procedure

1. `navigate` to route
2. `wait_for` DOMContentLoaded
3. `read_console_messages` with pattern to exclude known noise (`/DevTools listening/`, `/vite/`)
4. Fail on any application-code console `error` or `warning`
5. `read_page` to run the route-specific assertions above
6. On `/`, `/docs/tasks/`, `/book/ch-1-*/` — `take_screenshot` to `smoke-screenshots/YYYY-MM-DD/<route-slug>.png`

### Failure policy

- Console error (app code) → stop, report route + error, do not emit commit suggestion
- Assertion fail → stop, report which assertion
- 404 / network failure → hard fail

### Teardown

Always kill the preview server, even on smoke failure.

## New Atomic Skill — `apply-screengrabs`

**Source:** product `/Users/manavsehgal/Developer/ainative/screengrabs/*.png` + `manifest.json` (67 files as of 2026-04-18)
**Target:** website `/Users/manavsehgal/Developer/ainative-business.github.io/public/screenshots/*.png`

### First-run mode detection

- **Migration** — target has pre-rebrand names (`dashboard-list.png`, `dashboard-card-edit.png`, …); product has post-rebrand names (`tasks-list.png`, `tasks-card-edit.png`, …). Skill must propose a rename map and rewrite site-wide references.
- **Incremental** — target and product agree on names; skill just diff-copies content.
- **Fresh** — no target directory; skill copies everything.

### Plan Phase output

- Mode detected
- Files to create / update / delete
- **Rename map** (migration only) — table of `old → new` with per-file count of references to rewrite across `src/pages/**/*.{astro,mdx}`, `src/components/**/*.{astro,tsx}`, `src/data/**/*.ts`

### Execute Phase

1. In migration mode: grep-replace every `old-name.png` → `new-name.png` across listed globs. Show diff count per file before writing.
2. Copy product screengrabs → target; hash-diff to skip unchanged.
3. Delete stale orphans in target that have no product counterpart.
4. Sync alt-text: for each screenshot referenced in the website, pull authoritative `description` from product `manifest.json` and update the `alt` attribute.
5. Refresh cache manifest: `.claude/skills/apply-screengrabs/references/manifest-cache.md` (hash per file, last-sync timestamp).

### Key rule

`manifest.json` is the source of truth for both filenames and alt-text. The skill never invents alt text.

## New Atomic Skill — `apply-product-docs`

**Source:** product `/Users/manavsehgal/Developer/ainative/docs/features/*.md` (21 files) + `/docs/manifest.json`
**Target:** website `/Users/manavsehgal/Developer/ainative-business.github.io/src/pages/docs/*.mdx` (17 pages exist)

### Slug mapping table

Stored in `.claude/skills/apply-product-docs/references/docs-mapping.md`.

- **13 direct 1:1:** chat, costs, documents, home-workspace → index, inbox-notifications → inbox, monitoring, profiles, projects, schedules, settings, tables, tasks, workflows
- **8 product-only (no website page, flagged per run for user decision):** `design-system`, `shared-components`, `keyboard-navigation`, `user-guide`, `agent-intelligence`, `delivery-channels`, `provider-runtimes`, `tool-permissions`

### Plan Phase output

- Per-doc status: `unchanged` / `body-diff` / `new-product-doc-no-target` / `orphan-target-no-product`
- Body diffs summarized as "+N paragraphs, -M paragraphs, X image refs updated"

### Execute Phase

1. For each changed doc:
   - Read product markdown
   - Convert to MDX: preserve frontmatter (rewrite `layout:` → `../layouts/DocsLayout.astro`)
   - Preserve body markdown (mostly compatible with MDX)
   - Rewrite image paths: `/screengrabs/foo.png` → `/screenshots/foo.png` (verify convention against one existing website MDX exemplar first)
   - Wrap top-of-page screenshot in `<BrowserFrame>` component per existing `tasks.mdx` exemplar
2. Preserve website-only additions using sync markers: `{/* SYNC:START */}` … `{/* SYNC:END */}` wraps the auto-generated body. Anything outside those markers is preserved across syncs (CTAs, crosslinks, design-system framing).
3. Refresh cache manifest: `.claude/skills/apply-product-docs/references/docs-mapping.md` (hash per source file).

### Key rule

The sync-marker convention lets the website own its own chrome while the product owns the body content. No blind overwrite.

## Refactor Impact on Existing Skills

Mechanical, minimal-diff. Zero behavior change when run standalone.

### `apply-api-docs/SKILL.md`

- Add `## Plan Phase` header before current Step 1
- Current Steps 1-4 move under Plan Phase
- **Delete** Step 5 (User Confirmation Gate) — orchestrator owns gating; standalone runs fire one universal gate at the Plan → Execute boundary
- Add `## Execute Phase` header before current Step 6
- Current Steps 6-10 move under Execute Phase
- Add `## Plan Output Format` section at end with the canonical block template
- ~25 line diff

### `apply-book-update/SKILL.md`

- `## Plan Phase` wraps Steps 1-2 (Detect Sync Mode, Compare Files)
- `## Execute Phase` wraps Steps 3-7
- Add `## Plan Output Format` section
- ~15 line diff

### `ainative-stats/SKILL.md`

- `## Plan Phase` wraps Steps 1-7 (all metric collection, no writes)
- `## Execute Phase` wraps Steps 8-10 + "Updating the Website" subsection
- Add `## Plan Output Format` section
- ~10 line diff

## Directory Layout

```
.claude/skills/
├── apply-product-release/              # NEW, orchestrator
│   ├── SKILL.md
│   └── references/
│       └── sub-skill-contracts.md      # plan-output-block spec, invocation pattern
├── apply-screengrabs/                  # NEW, atomic
│   ├── SKILL.md
│   └── references/
│       ├── manifest-cache.md           # hash per screenshot (gitignored)
│       └── rename-map.md               # pre-migration pairs (committed once)
├── apply-product-docs/                  # NEW, atomic
│   ├── SKILL.md
│   └── references/
│       ├── docs-mapping.md             # slug + hash cache (gitignored)
│       └── exemplar-doc.md             # reference MDX template (committed)
├── apply-api-docs/                      # EXISTING, refactored
├── apply-book-update/                   # EXISTING, refactored
└── ainative-stats/                      # EXISTING, refactored
```

## `.gitignore` Changes

Remove:
```
.claude/skills/apply-product-release/
```

Add (cache files only — prevent git churn on every sync, fresh clones do a forced full refresh which is acceptable):
```
.claude/skills/*/references/manifest-cache.md
.claude/skills/*/references/docs-mapping.md
```

## Rollout Order

1. **Refactor existing 3 skills** — add Plan Phase / Execute Phase headers, delete in-skill confirmation gate from `apply-api-docs`, add Plan Output Format sections. Test each runs standalone. ~60 min.
2. **Create `apply-screengrabs`** via `skill-creator`. First real run is the one-time rename migration. Run carefully under explicit user supervision. ~90 min.
3. **Create `apply-product-docs`** via `skill-creator`. Needs exemplar MDX reference first (abstract from current `tasks.mdx`). ~60 min.
4. **Create `apply-product-release` orchestrator** via `skill-creator`. Simplest content, most logic per line. ~60 min.
5. **Remove `.gitignore` line** for `apply-product-release/`; add cache exclusions.
6. **End-to-end smoke run** against current product state. Serves as the first real release application (pending screengrab migration + pending stats sync). ~30 min observation + cleanup.

## Suggested Commit Message Template (for orchestrator to emit)

```
Apply product release: <summary phrase>

- Screengrabs: <N changed, M renamed>
- Docs: <N pages updated>
- API: <N endpoints, M domains>
- Book: <N chapters, M images>
- Stats: <LOC delta>, <features shipped delta>

<any risks flagged>
```

## Risks and Open Questions

- **Rename migration blast radius.** First run of `apply-screengrabs` in migration mode may rewrite references in dozens of files. If any reference was hand-customized (e.g., an `alt` attribute with bespoke copy), the grep-replace could clobber it. Mitigation: Plan Phase must show per-file diff counts and let user drop specific file globs from the rename pass.
- **MDX sync-marker convention is new.** Existing website docs don't have `SYNC:START` / `SYNC:END` markers. `apply-product-docs` first run must add them retroactively — that's a one-time migration step, not a drift risk.
- **Browser smoke requires a running chrome session.** If the user hasn't got chrome connected (via the `claude-in-chrome` extension), the smoke step can't run. Orchestrator should detect missing browser tools at the start of Stage 6 and offer to skip smoke with a loud warning — not silently pass.
- **Ordering between `apply-book-update` and `ainative-stats`.** `apply-book-update` touches `src/pages/research/ai-transformation.mdx` as a drift audit flag; `ainative-stats` also writes `research.mdx`. If book-update reports drift and the user accepts a research edit, stats running afterwards could conflict. Mitigation: stats Execute Phase should grep-verify it's not stomping a book-update-era edit; if it detects one, prompt.
- **Partial approval UX.** "Proceed but skip stats" requires the orchestrator to track per-sub-skill approval state. Not complex, but must be explicit in orchestrator SKILL.md to avoid skipping by accident.
