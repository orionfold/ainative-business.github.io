---
name: apply-screengrabs
description: Sync UI screenshots from the ainative product at /Users/manavsehgal/Developer/ainative/screengrabs/ to the marketing website at /Users/manavsehgal/Developer/ainative-business.github.io/public/screenshots/. On first run performs a one-time rename migration (pre-rebrand names like dashboard-*.png → post-rebrand tasks-*.png) and rewrites every site reference. On subsequent runs diff-copies changed files and syncs alt-text from the product's manifest.json. Use whenever the user says "apply screengrabs", "sync screenshots from product", "refresh screenshots", "update product screenshots", "migrate screenshot names", "sync screengrabs", "screenshots are stale", or any request to update the website's marketing/docs screenshots from the product source. Also trigger when the user mentions drift between product UI and website screenshots, or as the first phase of an "apply product release".
---

# Apply Screengrabs

Syncs product UI screenshots into the marketing website. Product is the source of truth — including canonical filenames and alt-text descriptions in its `manifest.json`. The website's screenshots and every page that references them must track product naming exactly.

## Why this matters

The website's `public/screenshots/` has historically drifted from the product — old route names (`/dashboard`), removed surfaces (`playbook-list.png`), pre-rebrand terminology — stay frozen while the product evolves. That drift causes three problems:

1. **Stale UI in docs** — docs pages show 2024-era screenshots of features that look different today
2. **Broken references** — a rename that happens only on the website side means docs reference names that don't exist in the product
3. **Alt-text rot** — hand-authored alt-text diverges from what the screenshot actually shows

The product's `manifest.json` fixes all three: it's the contract for filenames, for the UI they capture, and for descriptive alt-text. This skill enforces that contract.

## Source and Target

| | Path |
|---|---|
| Product screenshots | `/Users/manavsehgal/Developer/ainative/screengrabs/*.png` |
| Product manifest | `/Users/manavsehgal/Developer/ainative/screengrabs/manifest.json` |
| Website target | `/Users/manavsehgal/Developer/ainative-business.github.io/public/screenshots/*.png` |
| Reference globs (where screenshots are used in the website) | `src/pages/**/*.{astro,mdx}`, `src/components/**/*.{astro,tsx}`, `src/data/**/*.ts` |

## Sync Modes

The skill detects one of three modes automatically in Plan Phase.

| Mode | Detected when | Behavior |
|---|---|---|
| **migration** | Target contains pre-rebrand filenames (e.g., `dashboard-*.png`, `cost-usage-list.png`) that have a known rename in product. Also when orphan count > 10. | Compute full rename map, surface orphans for user decision, rewrite site-wide references. |
| **incremental** | All target filenames exist in product and orphan count ≤ 10. | Hash-diff each file, copy changed, refresh alt-text from manifest. |
| **fresh** | No target directory. | Copy everything, generate references/manifest-cache.md from scratch. |

## Workflow

This skill has two phases. When invoked standalone it runs both sequentially with one user gate between them. When invoked by `apply-product-release` the orchestrator runs only Plan Phase, aggregates plans from all sub-skills, fires one unified gate, then invokes each sub-skill's Execute Phase.

## Plan Phase

### Step 1: Detect mode

Check if target directory exists. If empty, mode is `fresh`.

Otherwise, compute the three sets:
- `PRODUCT` — filenames in `/Users/manavsehgal/Developer/ainative/screengrabs/*.png`
- `WEBSITE` — filenames in `/Users/manavsehgal/Developer/ainative-business.github.io/public/screenshots/*.png`
- `ORPHANS = WEBSITE - PRODUCT` — website files with no product counterpart

If `ORPHANS` contains any known pre-rebrand prefix (`dashboard-`, `cost-usage-`, `chat-model-selector`, `chat-create-tab`, `chat-quick-access`, `task-*` without the `s`) **or** `|ORPHANS| > 10`, mode is `migration`. Otherwise `incremental`.

Report detected mode.

### Step 2: Hash-diff files present in both

For each filename in `PRODUCT ∩ WEBSITE`, compare source/target file hashes. Record each as `unchanged` or `update`.

```bash
for src in /Users/manavsehgal/Developer/ainative/screengrabs/*.png; do
  name=$(basename "$src")
  tgt="/Users/manavsehgal/Developer/ainative-business.github.io/public/screenshots/$name"
  if [ -f "$tgt" ] && ! cmp -s "$src" "$tgt"; then
    echo "UPDATE: $name"
  fi
done
```

### Step 3: Build rename map (migration mode only)

Read `references/rename-map.md`. For each known rename pair `old → new`:

- If `old` exists in `WEBSITE` and `new` exists in `PRODUCT` → propose rename
- If `old` exists in `WEBSITE` but `new` does not exist in `PRODUCT` → flag as ambiguous (maybe the feature was removed, maybe renamed differently)

For `ORPHANS` not covered by the rename map, classify each:

- **pre-rebrand-orphan**: matches `dashboard-*`, `cost-usage-*`, etc., but the product has no direct replacement (e.g., `dashboard-detail.png` with no `tasks-detail.png`). Surface for user decision: delete, keep, or map manually.
- **content-orphan**: completely different name pattern (e.g., `kanban-board.png`, `trust-tier-popover.png`). Probably unused or deeply stale. Surface for user decision.
- **book-orphan**: `book-*.png` — these are book-related but live in `public/screenshots/` rather than the canonical `public/book/images/`. Flag as "moved to book directory" and surface for manual migration.

### Step 4: Scan site for references to each affected file

For every file that will be renamed, deleted, or updated, count references across the website globs:

```bash
grep -rl "dashboard-list.png" /Users/manavsehgal/Developer/ainative-business.github.io/src/ 2>/dev/null | wc -l
```

Record per-file reference counts in the Plan Output. This surfaces the blast radius — a rename from `dashboard-list.png` to `tasks-list.png` that hits 5 files is a safe mechanical rewrite; one that hits 47 files warrants careful review.

### Step 5: Compare alt-text in references vs product manifest

For each referenced screenshot, compare the `alt="..."` attribute in the website against the `description` field from the product's `manifest.json`. Flag divergences — these may indicate either hand-customization (preserve) or stale copy (update). List them in Plan Output so the user can decide.

## Plan Output Format

When running in Plan Phase only (invoked by `apply-product-release` orchestrator), stop after Step 5 and emit a single plan block in this exact shape:

```markdown
### apply-screengrabs
- **Status**: changed | no-changes | error
- **Mode**: migration | incremental | fresh
- **Summary**: <one-line: e.g., "Migration mode: 42 renames, 18 orphans (user decision), 3 updates, 67 alt-text syncs">
- **Renames** (migration only):
  | Old → New | References to rewrite | Reason |
  |---|---|---|
  | dashboard-list.png → tasks-list.png | 7 | /dashboard route renamed to /tasks |
  | cost-usage-list.png → costs-list.png | 3 | /cost-usage renamed to /costs |
- **Orphans for user decision** (migration only):
  | Filename | References | Category | Suggested action |
  |---|---|---|---|
  | kanban-board.png | 0 | content-orphan | delete |
  | trust-tier-popover.png | 1 in docs/settings.mdx | content-orphan | replace reference + delete |
  | book-reader.png | 2 | book-orphan | move to public/book/images/ |
- **Updates**:
  | Filename | Reason |
  |---|---|
  | tasks-list.png | hash differs from product |
- **Alt-text drift**:
  | Filename | Website alt (current) | Product description (canonical) |
  |---|---|---|
  | chat-conversation.png | "AI chat interface" | "Active chat conversation with agent" |
- **Risks**: (e.g., "Rename for dashboard-card-detail.png has no product counterpart — feature likely removed; flagging for delete")
```

Do not write any files during Plan Phase. Do not prompt for confirmation. Return control to the caller.

## Execute Phase

### Step 6: Execute rename pass (migration mode only)

For each approved rename `old → new`:

1. Copy source file: `cp /Users/manavsehgal/Developer/ainative/screengrabs/new /Users/manavsehgal/Developer/ainative-business.github.io/public/screenshots/new`
2. Grep-replace `old` → `new` across the reference globs:

```bash
grep -rl "old-name.png" src/ | while read f; do
  sed -i '' "s|old-name\.png|new-name.png|g" "$f"
done
```

3. Delete the old target file: `rm public/screenshots/old-name.png`

Record each rename in a per-run log for rollback.

### Step 7: Resolve orphans per user decision

Apply the Plan-Phase user decisions:
- `delete` → remove from target directory
- `keep` → leave alone, note in report
- `replace reference + delete` → grep-replace with a specified replacement, then delete
- `move to public/book/images/` → copy to book images dir (do NOT delete from source — `apply-book-update` owns that directory)

### Step 8: Copy changed + new files

For each file in `PRODUCT ∩ WEBSITE` marked `update` in Step 2, copy source over target.

For each file in `PRODUCT - WEBSITE` (new in product), copy source to target. These are additive — no existing reference to update.

### Step 9: Sync alt-text from manifest

Read `manifest.json`. For each screenshot reference in the website that has an `alt` attribute, compare against the manifest `description`. Apply updates only where the Plan Output marked the user as accepting the sync (hand-customized alt-text stays unless user opted into overwrite).

Target the `<img src="/screenshots/..." alt="...">` pattern in `.astro` files and the `![alt](/screenshots/...)` pattern in `.md`/`.mdx`. Also the `alt={...}` / `src={...}` props in `<BrowserFrame>` and similar components.

### Step 10: Refresh manifest cache

Write `.claude/skills/apply-screengrabs/references/manifest-cache.md` with:

```markdown
# Screengrab Sync Cache

Last sync: <ISO-8601 timestamp>
Mode on last sync: migration | incremental | fresh

## File hashes

| File | SHA-256 |
|---|---|
| home-list.png | abc123... |
| tasks-list.png | def456... |
```

Include every file currently in the target directory. This enables future `incremental` mode to skip unchanged files.

### Step 11: Build verification

```bash
cd /Users/manavsehgal/Developer/ainative-business.github.io
npm run build 2>&1 | tail -20
```

Must exit 0. A missing image reference from an incomplete rename pass shows up here as a build error — investigate and fix rather than suppressing.

### Step 12: Report

Emit a summary:

```markdown
## apply-screengrabs complete

- **Mode**: <mode>
- **Renamed**: <N files> (<M total reference rewrites)
- **Deleted**: <N orphans>
- **Updated**: <N files> (content changed in product)
- **Added**: <N files> (new in product)
- **Alt-text synced**: <N attributes>
- **Build**: ✓ (or ✗ with details)
```

## Key Rules

- **`manifest.json` is the source of truth.** Never invent alt-text. If the website has hand-customized alt-text, the Plan Phase surfaces the divergence for user decision before Execute Phase touches it.
- **Non-destructive by default.** Orphan deletion requires user decision in Plan Phase. The default suggestion for an unreferenced orphan is delete; for a referenced orphan, replace-reference-then-delete; user can always override.
- **Reference globs are fixed.** Only `src/pages/**/*.{astro,mdx}`, `src/components/**/*.{astro,tsx}`, `src/data/**/*.ts`. Do not grep-replace across `public/`, `node_modules/`, or `.claude/`.
- **One-way rename.** A rename rewrites the website to match the product. The reverse (product adopts a website name) is out of scope for this skill.
- **Book images are separate.** `public/book/images/*.png` is owned by `apply-book-update`. If a file in `public/screenshots/` starts with `book-`, flag it as book-orphan — don't sync it into the book images dir from this skill.
- **Build must pass.** The build is the backstop for missed rename references. If the build fails after Execute Phase, do not report success — surface the error.
- **`references/rename-map.md` is informational after first migration.** Once the site and product are name-locked, this file records the historical migration; it's not re-applied on subsequent incremental runs.
