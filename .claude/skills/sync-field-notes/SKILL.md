---
name: sync-field-notes
description: Sync new and updated field-notes articles from the local ai-field-notes drafting repo into this website. Compares each article folder, copies changed article.md/article.mdx, screenshots, and evidence images, then verifies the build. Use when the user says "sync field notes", "pull field notes", "update field notes", "I just pulled new articles", "ai-field-notes has new content", "refresh field notes from local", "copy new field notes", "new article in ai-field-notes", "check for new field notes", "import latest field notes", or any request to refresh the /field-notes/ section from the source ai-field-notes repository on this MacBook. Also trigger when the user mentions a specific article slug they just published in ai-field-notes (e.g., "I just shipped the kv-cache piece — sync it over").
---

# Sync Field Notes Skill

Syncs field-notes articles (markdown + images) from the local clone of the `ai-field-notes` drafting repo into this website. The website's `/field-notes/` section is an Astro content collection that loads from `articles/<slug>/article.{md,mdx}` at the project root, mirroring the layout in the source repo so a copy is the entire integration.

The drafting environment lives on the user's NVIDIA DGX Spark; the user pulls changes to a local clone on this MacBook before invoking this skill. This skill **does not run `git pull`** — it assumes the user has already pulled the latest into the local clone and explicitly wants those changes reflected on the website.

## Source and Target Paths

| Content | Source (read-only) | Target |
|---|---|---|
| Article markdown | `/Users/manavsehgal/Developer/ai-field-notes/articles/<slug>/article.md` | `articles/<slug>/article.md` |
| Article MDX (research papers) | `/Users/manavsehgal/Developer/ai-field-notes/articles/<slug>/article.mdx` | `articles/<slug>/article.mdx` |
| Upcoming-only seed (no article.md yet) | `/Users/manavsehgal/Developer/ai-field-notes/articles/<slug>/seed.md` | `articles/<slug>/article.md` (renamed) |
| Screenshots | `/Users/manavsehgal/Developer/ai-field-notes/articles/<slug>/screenshots/` | `articles/<slug>/screenshots/` |
| Evidence images | `/Users/manavsehgal/Developer/ai-field-notes/articles/<slug>/evidence/*.{png,jpg,jpeg,svg,gif,webp}` | `articles/<slug>/evidence/` |
| Fieldkit module reference | `/Users/manavsehgal/Developer/ai-field-notes/fieldkit/docs/api/*.md` | `fieldkit/docs/api/*.md` |
| Fieldkit version pin | `/Users/manavsehgal/Developer/ai-field-notes/fieldkit/src/fieldkit/_version.py` | `fieldkit/_version.py` |
| Fieldkit landing page sections (Install / Quickstart / CLI) | `/Users/manavsehgal/Developer/ai-field-notes/src/pages/fieldkit/index.astro` | `src/pages/fieldkit/index.astro` (only the named `<section>` bodies are replaced) |
| Signature SVG components | `/Users/manavsehgal/Developer/ai-field-notes/src/components/svg/*.astro` | `src/components/field-notes/svg/*.astro` |

Website project root: `/Users/manavsehgal/Developer/ainative-business.github.io/`.

## What to copy and what to skip

**Copy:**
- `article.md` and `article.mdx` (the article body)
- `screenshots/` directories (entire folder, all files)
- Image files inside `evidence/` directories (`*.png`, `*.jpg`, `*.jpeg`, `*.svg`, `*.gif`, `*.webp`)
- New article folders that don't yet exist in the target
- Signature SVG components (`*.astro` from source's `src/components/svg/` → target's `src/components/field-notes/svg/`). One-way flow only — the website may have signatures the source doesn't (e.g., for the two reframed papers), and those are never deleted.

**Skip:**
- `transcript.md` (authoring-time artifact, never published)
- `seed.md` IF a real `article.md` already exists alongside it (seed becomes obsolete once article ships)
- All non-image files inside `evidence/` directories — the bulk is Python source code (~30k lines) that should not ship with the website. Link out to GitHub if articles need to reference raw evidence.
- The `_drafts/` folder at the root of the source `articles/` directory (in-progress work)
- Landing page sections **other than** Install / Quickstart / CLI. The header/blurb has site-specific brand framing, the Modules section reads from a content collection, and the "Verified in" section uses `articleHref()` which differs by site. Auto-replacing those would break the build or the page's tone.

The reason for the evidence filter is simple: the plan deliberately defers raw-evidence migration to per-article calls. Bringing the Python in by default would inflate the repo by ~30 MB without giving the reader anything they can run. Linking out preserves provenance without the bulk.

## Workflow

Follow these steps in order. Do not skip the diff step — it's how you tell the user precisely what changed without inspecting every file by hand.

### Step 1: Confirm the local clone is up to date

Ask the user (briefly) if they've already pulled the latest from the `ai-field-notes` GitHub repo into the local clone. If they haven't, recommend they do so first via `cd /Users/manavsehgal/Developer/ai-field-notes && git pull`. Don't run `git pull` yourself — the user controls when their local repo updates.

### Step 2: Compute the diff

Run a comparison between the two `articles/` trees and produce a structured report. Use the bundled script:

```bash
python3 .claude/skills/sync-field-notes/scripts/diff_articles.py
```

The script prints:
- **New articles** (folders present in source but not target)
- **Updated articles** (article.md / article.mdx hash differs)
- **New or changed images** (screenshots and evidence images)
- **Articles only in target** (orphans — usually means a slug was renamed in the source; flag for human review)

Show the diff to the user before copying anything. If the diff is empty, stop and report "no changes to sync."

### Step 3: Copy the changes

If the user approves, copy the diff using:

```bash
python3 .claude/skills/sync-field-notes/scripts/sync_articles.py
```

The script applies the same rules as Step 2 in copy mode — it copies article markdown, screenshot folders, and evidence images, and skips transcript files, Python evidence, and the `_drafts/` folder. It also handles the seed-only edge case: when a folder has only `seed.md` (an upcoming placeholder with `status: upcoming` frontmatter), the seed is copied as `article.md` so the content collection picks it up as an upcoming entry.

The script is idempotent — running it twice is the same as running it once. Files are overwritten only when their content has actually changed.

**Landing-page section sync.** The script also keeps the `/fieldkit/` landing page in step with the source by replacing only the inner bodies of three named `<section class="fk-section">` blocks — those whose `<h2>` text is **Install**, **Quickstart**, or **CLI**. These three are pure copy/code; they don't reference site-local URL helpers, so they transplant cleanly. The script detects target's section indentation, dedents source's body to col 0, and re-indents at target's level + 2 spaces, so the wrapping layout (`FieldNotesLayout`, `Nav`, `Footer`, `<main>`) and the Modules / Verified-in / header sections stay untouched. This is what lets a copy change like `pip install fieldkit` propagate to the site without breaking the build.

### Step 4: Preserve the reframed research papers

Two articles in the website's `articles/` tree are NOT mirrors of the source — they were reframed from the old `/research/` MDX papers and live only on the website:

- `articles/ai-transformation/article.mdx` (ordinal 1, AI Native Platform series)
- `articles/solo-builder-case-study/article.mdx` (ordinal 2, AI Native Platform series)

The sync script knows about these and never touches them. If the user ever wants to update the body of these papers, do it manually in the website repo — the source `ai-field-notes` repo does not host them.

### Step 5: Build verification

After copying, build to make sure nothing broke:

```bash
npm run build
```

Common failures and how to handle them:

- **`ImageNotFound: <path>`** — an article references an image that wasn't copied. Check whether it's a screenshot (re-run sync), an evidence image with a non-image extension (the article body needs adjustment to point elsewhere or use a GitHub link), or a typo in the article markdown.
- **Schema validation error on a frontmatter field** — the source article uses a field this site's content schema doesn't accept, OR uses an enum value not in the schema. Look at `src/content.config.ts` for the field list and decide whether to extend the schema (add the new value to STAGES/SERIES) or fix the article frontmatter. Usually it's a new tag or stage that should be allowed.
- **Series enum mismatch** — the source repo only has six series; "AI Native Platform" is exclusive to the website. If a source article uses "AI Native Platform" as its series, that's the user authoring on the website's combined taxonomy — accept it.

### Step 6: Run the dev server briefly

Start the dev server and spot-check the new/updated articles render. Use the `preview_start` tool with the `astro` configuration. Visit `/field-notes/` to confirm the new articles appear in the index, then click into 2–3 of them to verify their bodies render.

### Step 7: Commit (only when explicitly requested)

Do not commit automatically. Show the user a `git status` summary and ask whether they want a commit. If yes, propose a one-line conventional commit message based on what changed:

- New article(s): `feat(field-notes): add <slug-1>, <slug-2>`
- Updated article: `chore(field-notes): refresh <slug>`
- Mixed: `chore(field-notes): sync <N> articles from ai-field-notes`

## Hand-curated files — do not blindly overwrite

A small number of files in the website's tree are derived from sources in the
ai-field-notes repo but have **deliberate hand edits** that the website needs
to keep. The current sync scripts do **not** sync any of these — but if a
future change to `sync_articles.py` or `diff_articles.py` extends the source
list to cover them, preserve these edits or stop and ask the user.

| File | Hand edit | Why |
|---|---|---|
| `src/data/field-notes/project-stats.json` | The first entry in `metrics.accuracy[]` is reordered to put **`recall@5 = 1.0`** ahead of `9% accuracy`. Label hand-cleaned to `"perfect retrieval on the eval set"`. | The headline metric tile on the homepage and field-notes index reads the first item; `9% accuracy` was unflattering and out of context for a marketing surface. The recall metric is a real, equally-citable result from `bigger-generator-grounding-on-spark`. |

If you sync this JSON in the future, the safe move is **don't** — the source
file regenerates from text-mining the article corpus and orderings change
every release. If you do extend the sync, re-apply the override after copy:
move the `recall@5 = 1.0` entry to position 0 of `metrics.accuracy[]` and
restore the cleaned label. Better still: add a `homepage_picks` block at the
top of the JSON that the components prefer over the auto-generated arrays.

## Edge cases

**A new stage value or tag.** The schema in `src/content.config.ts` enumerates stages and series. New tags are free-form (the schema is `z.array(z.string())`). New stages are not — adding one requires adding the enum value, copy in `src/pages/field-notes/stages/[stage].astro` `STAGE_COPY` map, and (optionally) the order in `STAGE_LABELS` inside `src/components/field-notes/StageFilter.astro`. Series are similarly closed; same three-file update pattern.

**A new signature SVG component referenced by `signature: <Name>` in frontmatter.** Handled automatically by the sync script — when the source repo adds a new `*.astro` file under `src/components/svg/`, it gets copied to `src/components/field-notes/svg/` on the next sync. The ArticleCard's signature lookup is via `import.meta.glob`, so the new file is picked up by the next build with no registration. If the article ships before the signature SVG exists in source, the article still renders (the schema makes `signature` optional) — just without the signature graphic, until the next sync that includes the SVG. **One-way flow only:** the website may have signatures the source doesn't (e.g., for the two reframed papers), so target-only signatures are never deleted or reported as orphans.

**An article moves between series in the source repo.** Just copy the new `article.md`. The change in `series:` frontmatter is enough — the article will start showing up in the new series page automatically.

**An article is renamed in the source repo (slug change).** The old folder will appear as an "orphan in target" in Step 2's diff. Flag it to the user — the safe thing is to delete the orphan folder by hand (preserving any redirect they may need to add manually). Do not auto-delete; the user owns that call.

**The user has uncommitted local changes in the website's `articles/` directory.** Ask before overwriting. Show them which files are dirty. The sync script does not stash or back up — that's git's job.

## Why this design

- **Same `articles/<slug>/article.md` layout in both repos.** The only reason this skill exists at all is to keep that mirror in sync. If the layouts diverged, the integration would need a transform step. They don't, so the integration is `cp`.
- **Diff before copy, not blind copy.** A blind copy works but doesn't tell the user what changed, which makes it easy to miss when something is moving that shouldn't be (a renamed slug, an accidentally-published seed). The diff is the receipt.
- **Evidence-folder filter at the boundary.** The plan defers per-article evidence migration; the default is "images yes, source code no." The user can hand-port a Python file or a .ipynb if they want to publish it for a specific article — but the default sync never carries source code along.
- **No git operations.** The drafting repo is the user's authoring environment; this skill stays a one-way mirror. The user pulls when they want to pull, commits when they want to commit, and runs this skill when they want to surface changes on the public site.
