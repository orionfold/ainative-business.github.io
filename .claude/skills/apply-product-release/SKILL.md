---
name: apply-product-release
description: Orchestrator skill that chains five sub-skills (apply-screengrabs, apply-product-docs, apply-api-docs, apply-book-update, ainative-stats) to apply a full ainative product release to the marketing website ainative.business. Runs all sub-skills in Plan Phase only, aggregates plans into one report, gets one user approval, then runs each in Execute Phase in the defined order. Verifies the build, runs a browser smoke test across 8 critical routes, and emits a suggested commit message (does NOT auto-commit). Use whenever the user says "apply product release", "sync product to website", "update website from product", "product release", "refresh everything from ainative", "ship product changes", "refresh website from product", "apply release", "release to website", "propagate product changes", or any request to apply a full product release / regenerate the website from the current product state. Also trigger when the user mentions the website being generally out of date with the product, or after a significant product version bump in CHANGELOG.md.
---

# Apply Product Release

Orchestrator skill. Chains five atomic sub-skills to apply a full ainative product release to the marketing website `ainative.business`. Aggregates one unified change plan across all sub-skills, fires one user gate, then runs each in order with build + browser-smoke verification at the end.

This skill does not have its own content logic. Its only job is to sequence, gate, build, and smoke-test the sub-skills. Content semantics live in the sub-skills — read their SKILL.md files if you need to understand what they actually do.

## Source and Target

| | Path |
|---|---|
| Product repo | `/Users/manavsehgal/Developer/ainative/` |
| Website repo | `/Users/manavsehgal/Developer/ainative-business.github.io/` |

## Sub-skills

Read `references/sub-skill-contracts.md` before running. It documents the Plan/Execute contract that every sub-skill below honors.

| # | Sub-skill | Purpose |
|---|---|---|
| 1 | `apply-screengrabs` | Product `/screengrabs/` → website `/public/screenshots/` |
| 2 | `apply-product-docs` | Product `/docs/features/*.md` → website `/src/pages/docs/*.mdx` (SYNC-marker bounded) |
| 3 | `apply-api-docs` | Product API routes/validators → website `/docs/api/*.mdx` |
| 4 | `apply-book-update` | Product `/book/chapters/` + `/book/images/` → website book subsystem |
| 5 | `ainative-stats` | Product metrics → `ainative-stats.md` + 10 website stat locations |

## Pipeline

Seven stages, executed in order. Stage 3 is the one gate; the rest are automatic if preconditions hold.

```
Stage 1: Preconditions       — repo cleanliness + sub-skill availability + browser tooling check
Stage 2: Plan Phase          — invoke every sub-skill in Plan Phase only; aggregate outputs
Stage 3: Approval Gate       — one user confirmation (supports partial approval)
Stage 4: Execute Phase       — run approved sub-skills in order
Stage 5: Build Verification  — npm run build must exit 0
Stage 6: Browser Smoke       — 8-route check via claude-in-chrome; fail-loud on console errors
Stage 7: Report              — unified summary + suggested commit message (no auto-commit)
```

## Stage 1: Preconditions

Before anything, verify the workspace is ready.

### 1a. Check repo cleanliness

```bash
cd /Users/manavsehgal/Developer/ainative && git status --porcelain
cd /Users/manavsehgal/Developer/ainative-business.github.io && git status --porcelain
```

- **Website repo must be clean.** Any uncommitted changes → HARD STOP. User must commit or stash before proceeding. A dirty website repo means changes from this run would mix with in-progress work.
- **Product repo may be dirty.** A product repo with uncommitted work is normal during active development. Warn the user but allow continue — the sub-skills read committed files only (they don't compare against HEAD), so product dirtiness doesn't affect the sync.

### 1b. Check branches

```bash
cd /Users/manavsehgal/Developer/ainative-business.github.io && git rev-parse --abbrev-ref HEAD
```

Should be `main`. If not, warn and ask the user whether they want to continue on a non-default branch.

### 1c. Read product CHANGELOG top entry

```bash
head -30 /Users/manavsehgal/Developer/ainative/CHANGELOG.md
```

Informational only. Surface the top entry in the pre-plan summary so the user sees which release they're applying. This is NOT a gate.

### 1d. Verify sub-skills exist

```bash
ls /Users/manavsehgal/Developer/ainative-business.github.io/.claude/skills/{apply-screengrabs,apply-product-docs,apply-api-docs,apply-book-update,ainative-stats}/SKILL.md
```

All five must exist. Missing sub-skill → HARD STOP with a note on which one, so the user can restore it.

### 1e. Check browser tooling

Browser smoke (Stage 6) requires the `claude-in-chrome` MCP extension to be active. Attempt:

```
mcp__claude-in-chrome__tabs_context_mcp  (this is a deferred MCP tool; fetch via ToolSearch if needed)
```

If the call fails or returns no tabs context:
- Inform the user: "claude-in-chrome is not connected. Stage 6 (browser smoke) can't run. Options: (a) connect chrome + re-run, (b) proceed without smoke but with loud warning, (c) abort."
- Default suggestion: (a). Never silently skip smoke.

## Stage 2: Plan Phase

For each sub-skill in the order `[screengrabs, product-docs, api-docs, book-update, stats]`:

1. Invoke `Skill(<sub-skill-name>)`.
2. Instruct the sub-skill to run **only the content under its `## Plan Phase` header**, emit the block under `## Plan Output Format`, and return control without writing files or prompting.
3. Capture the emitted plan block verbatim.

Concatenate all five blocks into a unified plan report with a preamble:

```markdown
# Product Release Plan

**Product CHANGELOG top entry:** <from Stage 1c>
**Website repo:** clean on main
**Plan generated:** <ISO-8601>

## Aggregate totals

- Creates: <N files>
- Updates: <N files>
- Deletes: <N files>
- Renames: <N files>
- Alt-text syncs: <N>

## Per sub-skill

<concatenated plan blocks from each sub-skill, in order>

## Overall risks

<any `Risks:` bullets from sub-skill outputs, flattened and deduplicated>
```

## Stage 3: Approval Gate

Present the unified plan to the user. Ask:

> "Proceed with all 5 sub-skills, abort, or skip specific ones? (Reply: `proceed` / `abort` / `skip <name> [<name>...]` / `only <name> [<name>...]`)"

Record the decision per sub-skill. If `abort`, stop here (no rollback needed — Plan Phase wrote nothing).

If `skip` or `only`, adjust the approved set but keep the documented execution order for whatever remains.

## Stage 4: Execute Phase

For each approved sub-skill, in the fixed order `[screengrabs, product-docs, api-docs, book-update, stats]`:

1. Invoke `Skill(<sub-skill-name>)`.
2. Instruct: "Run only the content under your `## Execute Phase` header. Treat the user as already having approved the plan."
3. Capture the result summary (per-skill report emitted at the end of Execute Phase).

If any sub-skill reports an error mid-execution, STOP before Stage 5. Report which sub-skill failed and the error. The working tree may be partially modified — the user can `git diff` to see the state and decide whether to commit partial progress, stash, or roll back.

## Stage 5: Build Verification

```bash
cd /Users/manavsehgal/Developer/ainative-business.github.io
npm run build 2>&1 | tail -30
```

Must exit 0. On failure:
- Show the last 30 lines of build output
- Stop. Do NOT proceed to smoke or commit suggestion.
- Most common cause: a missed screenshot reference (rename pass didn't cover all files) or an MDX import that the product body references but the website hasn't imported.

## Stage 6: Browser Smoke

### 6a. Start preview server

```bash
cd /Users/manavsehgal/Developer/ainative-business.github.io
npm run preview -- --port 4321 &
PREVIEW_PID=$!
# wait for "Local: http://localhost:4321/" in preview log, up to 30s
```

If the preview server fails to start, kill any leftover process on 4321 and retry once. If it still fails, report and stop.

### 6b. Get a browser tab

Use `mcp__claude-in-chrome__tabs_context_mcp` to list tabs, then `mcp__claude-in-chrome__tabs_create_mcp` to create a new tab. Capture the tab ID.

(Load the MCP tool schemas via ToolSearch first: `select:mcp__claude-in-chrome__tabs_context_mcp,mcp__claude-in-chrome__tabs_create_mcp,mcp__claude-in-chrome__navigate,mcp__claude-in-chrome__wait_for,mcp__claude-in-chrome__read_console_messages,mcp__claude-in-chrome__read_page,mcp__claude-in-chrome__take_screenshot`.)

### 6c. Smoke each route

| Route | Covers | Assertions |
|---|---|---|
| `http://localhost:4321/` | stats + screengrabs | Proof section metric count matches `ainative-stats` output; hero screenshot loads |
| `http://localhost:4321/docs/` | docs landing + nav | All sidebar items resolve (no broken links visible) |
| `http://localhost:4321/docs/tasks/` | product-docs | Page contains a `<BrowserFrame>` with tasks screenshot; alt-text non-empty |
| `http://localhost:4321/docs/api/` | api-docs landing | Domain cards render with current endpoint counts |
| `http://localhost:4321/docs/api/tasks/` | api-docs deep | Quick Start renders; `CodeExample` TS/Python tabs present |
| `http://localhost:4321/book/` | book landing | Chapter count in hero matches CHAPTERS.length; no stale "N chapters" prose |
| `http://localhost:4321/book/ch-1-from-hierarchy-to-intelligence/` | book + attribution | "by Manav Sehgal" byline present; CC BY-NC 4.0 preface present |
| `http://localhost:4321/research/ai-transformation/` | research snapshot | Page loads. Do NOT fail on stat drift — this is a historical snapshot |

For each route:

1. `navigate(tab_id, route)`
2. `wait_for(tab_id, "domcontentloaded")` — or up to 8 seconds
3. `read_console_messages(tab_id, pattern: "^(?!.*DevTools|vite|HMR).*$")` — filter common noise; keep only application-code messages
4. If any message has `level: error` or `level: warning` and is not in the explicit allowlist below → fail the route
5. `read_page(tab_id)` to run the per-route assertion from the table above
6. On the subset `[/, /docs/tasks/, /book/ch-1-*/]` also `take_screenshot(tab_id, path)` to `smoke-screenshots/YYYY-MM-DD/<route-slug>.png`

**Console noise allowlist** (filter OUT, don't fail on):
- DevTools listening messages
- Vite HMR / reload chatter
- Cross-origin preflight console warnings from third-party CDN resources
- React DevTools "download the React DevTools" info message

**Everything else fails the route.**

### 6d. Teardown

Always kill the preview server, even on failure:

```bash
kill $PREVIEW_PID 2>/dev/null
```

If smoke failed on any route, report which route + which assertion + the console excerpt. STOP. Do not proceed to Stage 7's commit suggestion.

If smoke passed, proceed.

## Stage 7: Report

Emit a unified markdown report:

```markdown
# Apply Product Release — Complete

## Summary

- Mode: <from each sub-skill, noted in line>
- Screengrabs: <N renamed, M updated, K deleted>
- Docs: <N pages marked, M updated, K product-only decisions>
- API: <N domains created/updated>
- Book: <N chapters/images changed>
- Stats: <LOC delta> · <tests delta> · <features delta>

## Build
✓ npm run build succeeded

## Browser Smoke
✓ 8/8 routes passed
Screenshots archived: smoke-screenshots/YYYY-MM-DD/

## Suggested commit message

```
Apply product release: <concise one-line summary>

- Screengrabs: <N changed, M renamed>
- Docs: <N pages updated>
- API: <N endpoints, M domains>
- Book: <N chapters, M images>
- Stats: <LOC delta>, <features delta>

<any risks flagged>
```

**Next step**: review `git status`, stage the relevant files, and commit. The orchestrator does NOT auto-commit.
```

## Key Rules

- **Pure orchestrator.** No content logic. If you find yourself rewriting a sub-skill's behavior in this file, the logic belongs in the sub-skill instead.
- **Always run all 5 in Plan Phase.** Simplicity wins over clever change-detection. Each sub-skill's diffing is fast enough that parallel optimization isn't worth the state-file complexity.
- **Single aggregate gate.** One release = one review. Don't fire gates inside Execute Phase.
- **Partial approval is first-class.** `skip`/`only` work at the approval gate. A skipped sub-skill is noted in the final report; it's not an error state.
- **No auto-commit.** The orchestrator produces a commit message; the user decides when and how to commit.
- **Browser smoke is non-optional when chrome is available.** Skipping smoke on a healthy setup risks shipping a broken site. If chrome isn't connected, STOP and surface the option to user — don't silently proceed.
- **Teardown always.** Preview server must be killed whether smoke passed, failed, or errored mid-route.
- **Fail loud on errors.** Any sub-skill error, build error, or smoke failure stops the pipeline with a clear report. Never report success on a partial run.
- **Working tree is the communication channel.** The orchestrator's output is changes to the working tree + a report. Sub-skills may write intermediate cache files; those are gitignored per `.gitignore` entries and don't need to be cleaned up.

## Cost

A clean full run (no changes in any sub-skill) takes roughly:
- Plan Phase: ~30-60 seconds (5 sub-skills × ~8s each for diff detection)
- Build: ~20-40 seconds
- Smoke: ~60-90 seconds (8 routes × ~10s each including screenshot)
- Total: ~2-3 minutes

A real release (many changes) can take 10+ minutes in Execute Phase depending on sub-skill work.
