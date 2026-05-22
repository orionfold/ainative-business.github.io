---
name: sync-field-notes
description: Sync field-notes articles AND apply UX feature changes from the directly-mounted ai-field-notes source at /Volumes/home/ai-field-notes into this website. Uses source's git log as the change narrative; runs the diff scripts to copy article markdown, screenshots, evidence images, signature SVGs, fieldkit landing sections, and project-stats; verifies the build. Supports bidirectional writes — when source-side nits are spotted during review (missing footer, frontmatter typo, broken link), the skill edits the source file, commits on source's main, and pushes to origin. Use when the user says "sync field notes", "update field notes", "check what's new from spark", "spark commit", "new article in ai-field-notes", "ai-field-notes has new content", "ship reader UX from ai-field-notes", "fix the source-side <issue>", "refresh field notes from source", or any request to surface changes from the mounted source repo into the website. Also trigger when the user mentions a specific article slug they just published on spark (e.g., "I just shipped the kv-cache piece — sync it over") or a feature shipped in source (e.g., "ship the explainers feature over").
---

# Sync Field Notes Skill

Mirrors field-notes content (articles + supporting surfaces) from the directly-mounted source repo at `/Volumes/home/ai-field-notes/` (Spark over NFS) into this website at `/Users/manavsehgal/Developer/ainative-business.github.io/`. The website's `/field-notes/` section is an Astro content collection that loads from `articles/<slug>/article.{md,mdx}` at the project root, mirroring the layout in the source repo so a copy is the entire integration.

**Source is live, not a clone.** No `git pull` needed — the mount IS the source. **Git is the change narrative.** `git -C /Volumes/home/ai-field-notes log` answers "what changed on source since last destination sync?" deterministically; this replaces the old SYNC-HANDOFF.md narrative document. **Writes flow both ways.** When Claude spots a source-side issue during review (missing catalog footer, frontmatter typo, etc.), it edits the file at `/Volumes/home/ai-field-notes/<path>`, commits on source's `main`, and pushes to origin — all without leaving this skill.

## Source and target paths

| Content | Source (read+write, NFS mount) | Target |
|---|---|---|
| Article markdown | `/Volumes/home/ai-field-notes/articles/<slug>/article.md` | `articles/<slug>/article.md` |
| Article MDX (research papers) | `/Volumes/home/ai-field-notes/articles/<slug>/article.mdx` | `articles/<slug>/article.mdx` |
| Upcoming-only seed (no article.md yet) | `/Volumes/home/ai-field-notes/articles/<slug>/seed.md` | `articles/<slug>/article.md` (renamed) |
| Screenshots | `/Volumes/home/ai-field-notes/articles/<slug>/screenshots/` | `articles/<slug>/screenshots/` |
| Evidence images | `/Volumes/home/ai-field-notes/articles/<slug>/evidence/*.{png,jpg,jpeg,svg,gif,webp}` | `articles/<slug>/evidence/` |
| Fieldkit module reference | `/Volumes/home/ai-field-notes/fieldkit/docs/api/*.md` | `fieldkit/docs/api/*.md` |
| Fieldkit version pin | `/Volumes/home/ai-field-notes/fieldkit/src/fieldkit/_version.py` | `fieldkit/_version.py` |
| Fieldkit landing page sections (Install / Quickstart / CLI) | `/Volumes/home/ai-field-notes/src/pages/fieldkit/index.astro` | `src/pages/fieldkit/index.astro` (only the named `<section>` bodies are replaced) |
| Signature SVG components | `/Volumes/home/ai-field-notes/src/components/svg/*.astro` | `src/components/field-notes/svg/*.astro` |
| Article-sequence manifest | (derived from source's `git log`, no on-disk source) | `src/data/field-notes/sequence.json` |
| Project-stats JSON ("At a glance" KPIs) | `/Volumes/home/ai-field-notes/src/data/project-stats.json` | `src/data/field-notes/project-stats.json` (with one hand-curated override re-applied) |

## What to copy and what to skip

**Copy:**
- `article.md` and `article.mdx` (the article body)
- `screenshots/` directories (entire folder, all files)
- Image files inside `evidence/` directories (`*.png`, `*.jpg`, `*.jpeg`, `*.svg`, `*.gif`, `*.webp`)
- New article folders that don't yet exist in the target
- Signature SVG components (`*.astro` from source's `src/components/svg/` → target's `src/components/field-notes/svg/`). One-way flow only — the website may have signatures the source doesn't (e.g., for the two reframed papers), and those are never deleted.

**Generate (not a file copy):**
- `src/data/field-notes/sequence.json` — derived from the source repo's `git log` output for `articles/*/article.md`, captures the canonical authoring order so the website's №01..№N ordinals track source order across syncs.

**Skip:**
- `transcript.md` (authoring-time artifact, never published)
- `seed.md` IF a real `article.md` already exists alongside it
- All non-image files inside `evidence/` directories (Python source code, ~30k lines — link out to GitHub if articles need to reference raw evidence)
- The `_drafts/` folder at the root of the source `articles/` directory
- Landing page sections **other than** Install / Quickstart / CLI (rest is site-specific brand framing)

## Workflow

Follow these steps in order. Steps 3 and 5 are the load-bearing ones; the rest are guardrails and narrative.

### Step 1: Verify the mount is healthy

Run two quick checks:

```bash
ls /Volumes/home/ai-field-notes/.git >/dev/null && echo "mount OK"
git -C /Volumes/home/ai-field-notes status --short
git -C /Volumes/home/ai-field-notes log --oneline -1
```

If the mount is unavailable (`ls` fails), stop and surface to the user — NFS may be down, or Spark may be off. If `git status` reports uncommitted changes, warn but don't block (Spark may be mid-edit; the user can decide whether to proceed). Print source's HEAD commit for context.

### Step 2: Show what's new since last destination sync (narrative)

Find the destination's most recent commit touching synced paths:

```bash
git log --oneline -1 -- articles/ src/components/field-notes/svg/ src/data/field-notes/ src/pages/fieldkit/index.astro fieldkit/
```

Take that commit's committer date (`git log -1 --format=%cI <sha>`), then enumerate source commits since:

```bash
git -C /Volumes/home/ai-field-notes log --since=<date> --oneline
```

Print the list with one line of context per commit (subject + a hint at files touched via `--stat=80,40` if you want detail). This is decoration — it tells the user *why* the upcoming diff exists. If destination has no prior sync commit, fall back to `--oneline -20` on source.

### Step 3: Compute the content diff

```bash
python3 .claude/skills/sync-field-notes/scripts/diff_articles.py
```

The script prints structured findings:
- **New articles** (folders present in source but not target)
- **Updated articles** (article.md / article.mdx hash differs, with link-rewrite + gated-footer-strip applied before comparing)
- **New or changed images** (screenshots and evidence images)
- **Signature SVG drift** (new or changed `*.astro` files under source's `src/components/svg/`)
- **Fieldkit landing drift** (Install/Quickstart/CLI section bodies differ)
- **Project-stats drift** (KPI deltas after recall@5 override re-applied)
- **Articles only in target** (orphans — usually a renamed slug; flag for human review, do not auto-delete)

Show the diff to the user before copying anything. If the diff is empty AND Step 4 finds nothing, stop and report "no changes to sync."

### Step 4: Surface non-tracked source-side changes (judgement loop)

From the commits-since-last-sync window in Step 2, find files modified that are OUTSIDE the auto-flow surfaces (which Step 3 already covers):

```bash
git -C /Volumes/home/ai-field-notes log --since=<date> --name-only --pretty=format: \
  | sort -u \
  | grep -vE '^(articles/|src/components/svg/|src/data/project-stats\.json|src/pages/fieldkit/index\.astro|fieldkit/(docs/api/|src/fieldkit/_version\.py)|SYNC-|mirrors/|ideas/|papers/|specs/|scripts/|probes/|dataset-cards/|share/|evidence/|README\.md|HANDOFF\.md|COMMANDS\.md|package-lock\.json|node_modules/|unsloth_compiled_cache/|dist/)'
```

Anything left is a candidate UX/config change: new file under `src/components/` (excluding `svg/`), edited `src/styles/global.css`, edited `astro.config.mjs`, modified `package.json`, etc. Present the list and, for each, ask the user one of: **inspect** (Read source + brainstorm an edit on destination), **skip** (not porting in this sync), **defer** (re-surface on next sync). Empty list → skip this step silently.

If a candidate file is `package.json`, run `diff` between source and destination to see the actual dependency delta before proposing `npm install <pkg>@<range>`. If it's `astro.config.mjs`, Read both files before proposing an Edit — plugin-chain insertion order matters (e.g. `remark-directive` *before* `remark-explainers`).

**Before any UX edit, Read the destination target.** If the proposed change already exists verbatim, mark the item "verify only" and don't re-apply. Destructive changes (file deletion, route removal) ALWAYS prompt explicitly per item.

### Step 5: Apply the diff

If the user approves Step 3's content diff:

```bash
python3 .claude/skills/sync-field-notes/scripts/sync_articles.py
```

The script applies the same rules as Step 3 in copy mode — articles, screenshots, evidence images, signature SVGs, fieldkit landing sections (only Install/Quickstart/CLI bodies), project-stats (with recall@5 override re-applied), and the sequence manifest. It also handles the seed-only edge case: when a folder has only `seed.md`, the seed is copied as `article.md` so the content collection picks it up as upcoming. Idempotent — running it twice is the same as running it once.

**Article-sequence manifest.** Derived from source's `git log --diff-filter=A` for `articles/*/article.md` — captures the canonical authoring order. Rewritten only when slug ordering actually changes.

**Landing-page section sync.** Replaces only the inner bodies of three named `<section class="fk-section">` blocks (Install / Quickstart / CLI). The wrapping layout, Modules section, and Verified-in section stay untouched.

**Gated catalog-footer preservation.** Articles with a matching catalog manifest at `src/content/artifacts/<slug>.yaml` carry a Mac-owned trailing chrome block:

> `**Catalog page:** [/artifacts/<kind>/<artifact-slug>/](...) — the same four-axis card rendered on this site, with the sweet-spot variant highlighted on a heatmap row.`

The source repo deliberately doesn't carry this block. Both diff and sync scripts strip the footer from target before comparing, then `restore_gated_footers()` re-appends the canonical footer after sync. The binding is data-driven — drop a new `src/content/artifacts/<slug>.yaml` with `article: articles/<slug>/` and the matching article picks up its footer on the next sync.

After `sync_articles.py` runs, separately walk any per-file Step 4 items the user approved: Read source file → Edit/Write target.

### Step 6: Source-side nit fixes (optional, user-driven)

When the user spots a source-side issue during Step 3/4 review (e.g. "article X is missing its catalog footer", "frontmatter typo in Y", "image filename is wrong", "footer in Z links to the wrong artifact"), Claude can fix it directly on source. For each fix:

1. **Read** the source file at `/Volumes/home/ai-field-notes/<path>`.
2. **Edit** the fix in place.
3. Confirm with the user before committing.
4. After the user approves the batch:
   - `git -C /Volumes/home/ai-field-notes pull --rebase --autostash origin main` — fast-forward to catch concurrent Spark commits. If the rebase reports conflicts, abort, surface to the user, and don't push.
   - `git -C /Volumes/home/ai-field-notes add -- <paths>` — stage only the files Claude edited (never `add -A`).
   - `git -C /Volumes/home/ai-field-notes commit -m "<conventional message>"` — generated subject like `chore(field-notes): restore catalog footer on <slug>` or `fix(field-notes): correct frontmatter typo in <slug>`. Include `Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>`.
   - `git -C /Volumes/home/ai-field-notes push origin main`.
5. After the source-side commit lands, re-run Step 3 + Step 5 to pull the fix through to destination (some fixes — like footer restoration — will only show as a destination diff once the source is fixed).

The push step is gated by user approval. Never auto-push without confirmation. If the source repo has unrelated uncommitted changes (Spark mid-edit), abort and surface — don't try to stash someone else's work.

### Step 7: Build verification

```bash
npm run build
```

**Astro 5 cache caveat.** If Step 4 touched the content config, a remark plugin, or `astro.config.mjs`, run `rm -rf .astro node_modules/.astro` before the first build.

Common failures:

- **`ImageNotFound: <path>`** — an article references an image that wasn't copied. Check whether it's a missed screenshot (re-run sync), an evidence file with a non-image extension (article body needs to point elsewhere or use a GitHub link), or a typo.
- **Schema validation error on a frontmatter field** — source article uses a field this site's schema doesn't accept, or an enum value not in `STAGES`/`SERIES`. Check `src/content.config.ts`. Usually it's a new tag or stage that should be allowed — extend the schema (and the matching copy in `src/pages/field-notes/stages/[stage].astro` `STAGE_COPY` for stages).
- **Series enum mismatch** — "AI Native Platform" is exclusive to the website (used by the two reframed papers). If source ever uses it, accept it.

### Step 8: Run the dev server briefly

Start `npm run dev`, visit `/field-notes/` to confirm new articles appear in the index, then click into 2–3 to verify their bodies render. Confirm signatures and gated catalog footers are present where expected.

### Step 9: Commit on destination (only when explicitly requested)

Don't commit automatically. Show the user a `git status` summary and ask whether they want a commit. Propose a one-line conventional message:

- New article(s) — `feat(field-notes): add <slug-1>, <slug-2>`
- Updated article — `chore(field-notes): refresh <slug>`
- Mixed — `chore(field-notes): sync <N> articles from ai-field-notes`
- UX feature release — `feat(field-notes): add <feature-name> + sync <N> articles`
- UX-only release (no article diff) — `feat(field-notes): apply <feature-name> from ai-field-notes`

## Preserve the reframed research papers

Two articles in the website's `articles/` tree are NOT mirrors of the source — they were reframed from the old `/research/` MDX papers and live only on the website:

- `articles/ai-transformation/article.mdx` (ordinal 1, AI Native Platform series)
- `articles/solo-builder-case-study/article.mdx` (ordinal 2, AI Native Platform series)

The sync script knows about these (`TARGET_ONLY_SLUGS`) and never touches them. To update their bodies, edit them manually in the website repo — source does not host them.

## Hand-curated overrides re-applied during sync

`src/data/field-notes/project-stats.json` is sourced from source's `src/data/project-stats.json` (auto-regenerated on every source release by text-mining the article corpus), but the website needs one deterministic override so the homepage and `/field-notes/` index read well.

| File | Override re-applied by `sync_articles.py` | Why |
|---|---|---|
| `src/data/field-notes/project-stats.json` | The entry in `metrics.accuracy[]` matched by `(article_slug == "bigger-generator-grounding-on-spark", value == "recall@5 = 1.0")` is moved to index 0, with its `label` rewritten to `"perfect retrieval on the eval set"`. | Both the homepage `FieldNotesSummary` KPI and the `/field-notes/` "At a glance" tile read `metrics.accuracy[0]`. The auto-generator orders by article-recency, which once put `9% accuracy` (out of context, unflattering) ahead of a real, equally-citable recall@5 result. The override pins the citable headline. |

The override is matched by `(article_slug, value)` rather than by index so it survives source-side reordering. If the recall@5 entry ever stops being auto-generated, the override silently no-ops. Diff and sync scripts both apply it before comparing, so they agree.

## Edge cases

**NFS mount unavailable.** `ls /Volumes/home/ai-field-notes/.git` fails. Stop immediately and surface — the user needs to bring Spark up or remount before any sync can proceed. Don't proceed with partial data.

**NFS read stall (process state `U`).** The diff and sync scripts hash every article and evidence image. On a flaky or warming NFS connection, individual hash reads can stall in uninterruptible I/O wait (process state `U`), making the script appear hung. If `diff_articles.py` hasn't produced any output for several minutes and `ps -p <pid> -o state` shows `U`, the script is waiting on a stuck NFS read. Recovery: `kill -9 <pid>`, then re-run. A second run usually completes normally because the kernel re-resolves the NFS handles. If it stalls repeatedly on the same file, that file's directory may have a stale handle on Spark — check the path manually and consider remounting.

**Source has uncommitted changes.** `git status --short` is non-empty. Warn but don't block content sync (Spark may be mid-edit and the on-disk state is what the user wants synced). DO block Step 6 source-side writes — never commit on top of someone else's uncommitted work.

**Source push rejected (non-fast-forward).** Step 6's `pull --rebase --autostash` should fast-forward, but if the rebase reports conflicts, abort the push, leave the local commit in place, and surface to the user. They'll resolve from Spark.

**A new stage value or tag.** The schema in `src/content.config.ts` enumerates stages and series; new tags are free-form (`z.array(z.string())`). New stages require updating the enum + `STAGE_COPY` map in `src/pages/field-notes/stages/[stage].astro` + (optionally) `STAGE_LABELS` order in `src/components/field-notes/StageFilter.astro`. Series are similarly closed.

**A new signature SVG component referenced by `signature: <Name>` in frontmatter.** Handled automatically by the sync script. ArticleCard's signature lookup uses `import.meta.glob`, so the new file is picked up at next build with no registration. If the article ships before the SVG exists in source, it renders without the graphic (schema marks `signature` optional) until the next sync that includes the SVG. **One-way flow only:** target-only signatures (reframed papers) are never deleted.

**An article is renamed in the source repo (slug change).** The old folder appears as an "orphan in target" in Step 3's diff. Flag it to the user — the safe move is to delete the orphan by hand (preserving any redirect they may need to add). Do not auto-delete.

**Uncommitted local changes in the website's `articles/` directory.** Ask before overwriting. Show which files are dirty. The sync script does not stash — that's git's job.

**Source repo's `git log` is unavailable** (e.g., a shallow clone with truncated history). `_compute_source_sequence()` returns `None` and the sync script silently skips the manifest write. The website's `publishOrdinals()` falls back to deriving order from this repo's own git log. Order may not perfectly mirror source but the build succeeds.

**An article moves from `status: upcoming` to published in source.** The manifest already lists the slug (it has had an `article.md` from the moment source committed the upcoming placeholder), so no manifest rewrite. The website's ordinal walk now slots it into its reserved position.

**A new artifact manifest lands but the matching article has no catalog footer.** Run `sync_articles.py` — `restore_gated_footers()` appends the footer automatically once the manifest exists at `src/content/artifacts/<slug>.yaml` with a valid `article: articles/<slug>/` field.

**Stale catalog footer on an article whose manifest moved or was deleted.** The restore step strips any trailing catalog footer before re-appending. If a manifest is removed, the footer is also removed on next sync. If a manifest's `slug:` changes, the footer is rewritten to point at the new URL.

**Artifact `kind:` is unmapped in `chrome_footers._KIND_TO_URL_FAMILY`.** The footer is silently skipped (defensive — better to skip than emit a broken URL). Add the new kind to the map when fieldkit ships a new publisher module.

**Build warns "X published article(s) not in sequence manifest — appended alphabetically."** A new article exists in the website's `articles/` tree but isn't in `src/data/field-notes/sequence.json`. Most common cause: the user added an article folder by hand, or pulled the source mount but ran `npm run build` without first running `sync_articles.py`. Re-run sync to regenerate the manifest. Non-fatal.

## Why this design

- **Git is the narrative.** With a live mount, `git -C /Volumes/home/ai-field-notes log` answers "what changed on source since last sync?" deterministically. The old SYNC-HANDOFF.md document was a workaround for the airlock between machines; the airlock is gone, so the workaround can go. The diff script remains the authoritative "what to copy" — git is just the human-readable receipt.
- **Bidirectional writes close a loop that used to span machines.** Spotting "this article is missing its footer" used to require a destination-side observation, a Spark-side fix, a push, a Mac pull, and a re-sync. Now it's one skill invocation: observe, edit, commit, push, re-sync.
- **Scripts do mechanical, Claude does judgement.** The Python scripts auto-flow the well-known surfaces (articles, screenshots, evidence images, signature SVGs, fieldkit landing sections, project-stats, gated footers). Anything outside those surfaces is surfaced as a per-file judgement loop in Step 4 — Claude reads, brainstorms, and Edit/Writes. This split keeps each layer simple.
- **No git operations on source other than Step 6.** The mount is the user's authoring environment; the skill doesn't pull, doesn't fetch, doesn't stash. Step 6's commit + push is the one exception, and it's user-gated per batch.
- **Gated chrome blocks are data-driven, not allowlisted.** The trailing catalog footer is owned by Mac. The script discovers which articles get the footer by reading `src/content/artifacts/*.yaml` for `article: articles/<slug>/` bindings — no skill-side allowlist to maintain. Drop a new manifest, the matching article picks up its footer on next sync.
- **Sequence manifest, not per-article frontmatter.** The website needs source's authoring order to render matching №01..№N labels, but encoding that into each article's frontmatter would smear ordering metadata across 30+ files. A single manifest file is the cheaper representation: one diff, one place to look, one git audit trail.
