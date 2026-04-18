# Handoff: Rename local dev folder `stagent.github.io` → `ainative-business.github.io`

**Date:** 2026-04-18
**Context:** The GitHub remote has already been migrated to `manavsehgal/ainative-business.github.io`. The local working directory is still named `stagent.github.io` — this handoff documents the steps to finish the local rename cleanly.

---

## Pre-flight: what I verified before writing this handoff

Ran from inside `/Users/manavsehgal/Developer/stagent.github.io` on 2026-04-18:

- `git remote -v` → already `https://github.com/manavsehgal/ainative-business.github.io.git`
- `package.json` → `"name": "ainative-business-website"` (already renamed in a prior commit)
- `grep -r "stagent.github.io" .` → only `handoff/*.md` and `docs/superpowers/**/*.md` match (archival refs, correct to keep)
- `grep -r "/Developer/stagent"` inside the repo (code + `.claude/` + skills) → **zero hits**. No hardcoded absolute paths.
- `.claude/settings.json` hook → `gh run list ...` does not hardcode any path. Safe.
- `.claude/launch.json` → no path hardcoding.
- `~/.claude/projects/-Users-manavsehgal-Developer-stagent-github-io/memory/` contains 6 memory files + `MEMORY.md`. **This is what must be migrated manually.**

So: the only things that actually need intervention are (1) the folder itself, (2) the Claude auto-memory directory under `~/.claude/projects/`, and (3) regenerable caches that have absolute paths baked in.

---

## Part A — Steps **YOU** take before restarting Claude Code

Run these in Terminal. Order matters.

### 1. Quit Claude Code completely

Close the Claude Code window/process attached to the old folder. If anything is still holding the dir open (a running `astro dev`, a background task), kill it first.

```bash
pkill -f "astro dev" 2>/dev/null || true
```

### 2. Verify git is clean (or intentionally dirty)

```bash
cd /Users/manavsehgal/Developer/stagent.github.io
git status
```

There's one untracked file right now: `.claude/settings.json`. That's fine — it will move with the folder. Commit it first if you want it tracked, or leave it.

### 3. Rename the working directory

```bash
mv /Users/manavsehgal/Developer/stagent.github.io \
   /Users/manavsehgal/Developer/ainative-business.github.io
```

Everything inside — `.git/`, `.claude/`, `src/`, `handoff/`, `node_modules/`, `dist/`, `.astro/` — moves intact. `git` itself doesn't care about the parent folder name.

### 4. Migrate Claude Code's auto-memory directory

Claude Code stores per-project memory at `~/.claude/projects/<cwd-with-slashes-as-dashes>/`. The new cwd maps to a new dashed name, so we need to copy the `memory/` subdir across.

```bash
# Create the new project folder (Claude Code will also create it on first launch,
# but we want memory in place before that happens).
mkdir -p ~/.claude/projects/-Users-manavsehgal-Developer-ainative-business-github-io

# Copy the persistent memory (MEMORY.md + feedback_*.md + project_*.md).
cp -r ~/.claude/projects/-Users-manavsehgal-Developer-stagent-github-io/memory \
      ~/.claude/projects/-Users-manavsehgal-Developer-ainative-business-github-io/
```

**Optional — migrate prior conversation history** (the `*.jsonl` session files so `/resume` still sees old sessions):

```bash
# Copy (don't move) so you keep a rollback option.
rsync -a \
  ~/.claude/projects/-Users-manavsehgal-Developer-stagent-github-io/ \
  ~/.claude/projects/-Users-manavsehgal-Developer-ainative-business-github-io/
```

If you skip this step, old sessions won't be resumable from the new folder (but memory will still work because step above already placed `memory/`).

**Do NOT delete the old `-Users-manavsehgal-Developer-stagent-github-io/` folder yet.** Keep it as a rollback until you've confirmed the new setup works. Delete it a few days later with:

```bash
# Only after verifying everything works in the new folder.
rm -rf ~/.claude/projects/-Users-manavsehgal-Developer-stagent-github-io
```

### 5. Purge regenerable caches that have the old absolute path baked in

These will rebuild on first run. Doing this now avoids subtle "why does this fail" moments later.

```bash
cd /Users/manavsehgal/Developer/ainative-business.github.io
rm -rf node_modules .astro dist .superpowers/brainstorm
```

`node_modules/.bin/*` shebangs and many tooling caches bake in the absolute install path. Rebuilding guarantees no stale references.

### 6. Reinstall and verify the build works on the new path

```bash
npm install
npm run build
```

If `npm run build` succeeds, the rename is structurally sound.

### 7. Start Claude Code from the new folder

```bash
cd /Users/manavsehgal/Developer/ainative-business.github.io
claude
```

Then tell me:

> Read `handoff/2026-04-18-folder-rename-to-ainative-business.md` and run the "Part B" steps.

---

## Part B — Steps **I (Claude Code)** take on first session in the new folder

When you point me at this file, I will:

### 1. Confirm environment

- Verify `pwd` is `/Users/manavsehgal/Developer/ainative-business.github.io`.
- Verify `git remote -v` points to `ainative-business.github.io.git`.
- Verify `git status` looks sane (no mysterious deletions from the rename).

### 2. Confirm auto-memory survived

- Check that the auto-memory system-reminder at session start references the **new** path (`/Users/manavsehgal/.claude/projects/-Users-manavsehgal-Developer-ainative-business-github-io/memory/`).
- Confirm `MEMORY.md` loaded (I should see the 4 feedback entries + 2 project entries from the old location).
- If memory did NOT carry over, I will fall back to manually reading the old location and re-copy.

### 3. Sanity-check that nothing references the old path inside the repo

Run a final grep for safety:

```bash
grep -r "Developer/stagent" --include="*.{ts,tsx,astro,mjs,js,json,md,mdx}" .
```

Expected result: matches only in `handoff/` and `docs/superpowers/` (archival). Anything else is a bug I need to fix.

### 4. Rebuild verification

- Run `npm run build` and confirm it completes.
- Run `npm run dev` briefly and confirm the dev server starts cleanly. Then kill it.

### 5. Commit the handoff file (if you want)

Ask you first — but the handoff belongs in git alongside the prior `2026-04-17-*` and `2026-04-18-ainative-business-naming-and-rendering.md` handoffs.

### 6. Update memory if anything changed

- If any memory entry referenced the old folder name in its body (none currently do, based on the titles: `feedback_light_theme`, `feedback_trailing_slashes`, `feedback_pagespeed_techniques`, `feedback_work_on_main`, `project_stagent_maven_relationship`, `project_newsletter_rename`), leave them alone.
- Note: `project_stagent_maven_relationship.md` is named after **Stagent.io the brand**, not the folder — keep the filename. The brand is still Stagent; only the repo/domain moved to AI Native Business.

---

## What is NOT affected by the rename (and why)

| Thing | Why it's safe |
|---|---|
| Git history, branches, remotes | Git tracks `.git/` contents, not the parent folder name. Remote already updated separately. |
| GitHub Pages deploy | Driven by `.github/workflows/` + repo name on GitHub, not local folder name. |
| Astro build output (`dist/`) | Regenerated from source on every build. |
| Published site URL | Set by CNAME / GitHub Pages settings, not local path. |
| `src/`, `public/`, `astro.config.mjs` | Use relative paths throughout — verified via grep. |
| Installed skills (`.claude/skills/*`, `.superpowers/*`) | Skills use relative paths inside the repo. No hardcoded absolute cwd. |
| User-level settings (`~/.claude/settings.json`, installed plugins) | Live outside the project folder, unaffected. |

## What IS affected (and what we do about it)

| Thing | Fix |
|---|---|
| `~/.claude/projects/<old-dashed-path>/memory/` | Copy to new dashed-path location (Part A, step 4). |
| `~/.claude/projects/<old-dashed-path>/*.jsonl` session history | Optional copy (Part A, step 4). |
| `node_modules/` shebangs with old abs paths | `rm -rf node_modules && npm install` (Part A, steps 5–6). |
| `.astro/` build cache | `rm -rf .astro` — rebuilds on next `astro build`. |
| `.superpowers/brainstorm/*/.server-info` | Ephemeral per-session file with hardcoded abs path. Purge — regenerated next brainstorm. |
| Worktrees under `-Users-manavsehgal-Developer-stagent-github-io--claude-worktrees-*` | None currently mounted. Old worktree memory dirs can stay — you'll never open those paths again. Clean up later if desired. |

---

## Rollback plan

If anything goes wrong mid-migration:

```bash
# Restore folder name.
mv /Users/manavsehgal/Developer/ainative-business.github.io \
   /Users/manavsehgal/Developer/stagent.github.io

# The old auto-memory dir was never deleted (per step 4 warning), so it's still there.
# Just re-open Claude Code from the original path.
```

No data loss as long as Part A step 4's "don't delete old" guidance is followed until verification is complete.
