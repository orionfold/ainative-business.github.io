---
name: sync-field-notes
description: Sync field-notes articles AND apply UX feature changes from the local ai-field-notes drafting repo into this website. Reads the source's SYNC-HANDOFF.md release narrative to surface content, dependency, config, and UX-contract changes; brainstorms with the user on conflicts and high-judgement items; copies article markdown / screenshots / evidence images; verifies the build. Use when the user says "sync field notes", "update field notes", "refresh field notes from local", "new article in ai-field-notes", "ai-field-notes has new content", "apply UX feature changes from a release", "sync handoff", "follow SYNC-HANDOFF instructions", "ship reader UX from ai-field-notes", or any request to refresh the /field-notes/ section or apply a release from the source ai-field-notes repository. Also trigger when the user mentions a specific article slug they just published (e.g., "I just shipped the kv-cache piece — sync it over") or a feature shipped in source (e.g., "ship the explainers feature over").
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
| Article-sequence manifest | (derived from source's `git log`, no on-disk source) | `src/data/field-notes/sequence.json` |
| Project-stats JSON ("At a glance" KPIs) | `/Users/manavsehgal/Developer/ai-field-notes/src/data/project-stats.json` | `src/data/field-notes/project-stats.json` (with one hand-curated override re-applied) |

Website project root: `/Users/manavsehgal/Developer/ainative-business.github.io/`.

## What to copy and what to skip

**Copy:**
- `article.md` and `article.mdx` (the article body)
- `screenshots/` directories (entire folder, all files)
- Image files inside `evidence/` directories (`*.png`, `*.jpg`, `*.jpeg`, `*.svg`, `*.gif`, `*.webp`)
- New article folders that don't yet exist in the target
- Signature SVG components (`*.astro` from source's `src/components/svg/` → target's `src/components/field-notes/svg/`). One-way flow only — the website may have signatures the source doesn't (e.g., for the two reframed papers), and those are never deleted.

**Generate (not a file copy):**
- `src/data/field-notes/sequence.json` — derived from the source repo's `git log` output for `articles/*/article.md`, captures the canonical authoring order so the website's №01..№N ordinals track source order across syncs. See "Article-sequence manifest" in Step 4 for the full rationale.

**Skip:**
- `transcript.md` (authoring-time artifact, never published)
- `seed.md` IF a real `article.md` already exists alongside it (seed becomes obsolete once article ships)
- All non-image files inside `evidence/` directories — the bulk is Python source code (~30k lines) that should not ship with the website. Link out to GitHub if articles need to reference raw evidence.
- The `_drafts/` folder at the root of the source `articles/` directory (in-progress work)
- Landing page sections **other than** Install / Quickstart / CLI. The header/blurb has site-specific brand framing, the Modules section reads from a content collection, and the "Verified in" section uses `articleHref()` which differs by site. Auto-replacing those would break the build or the page's tone.

The reason for the evidence filter is simple: the plan deliberately defers raw-evidence migration to per-article calls. Bringing the Python in by default would inflate the repo by ~30 MB without giving the reader anything they can run. Linking out preserves provenance without the bulk.

## SYNC-HANDOFF.md — release-aware sync

The source repo writes a release narrative at `/Users/manavsehgal/Developer/ai-field-notes/SYNC-HANDOFF.md` describing both content and UX feature changes shipped in a release (e.g. new components, plugin wiring, `localStorage` contracts, route additions, CSS architecture changes). Mechanical content still flows through the existing Python scripts; UX changes are surfaced for user-driven brainstorm and applied by Claude via Edit/Write/Bash tools, with per-item user approval. The handoff is parsed **semantically** — read it end-to-end and look for these section headings, but degrade gracefully when any are missing: `File inventory`, `Dependency change(s)`, `Plugin chain`/`wiring`, `localStorage contract`, `CSS architecture`, `Reader UX`/`UX features`, `Verification`, `Conflict-avoidance notes`.

**Non-goal.** The Python scripts (`scripts/diff_articles.py`, `scripts/sync_articles.py`) are NOT extended for UX changes. Mechanical content sync stays in scripts; UX changes are applied by Claude via Edit/Write/Bash tools, with per-item user approval. Don't try to script the UX layer — Claude's tools already provide the engine.

### Seven buckets — how to route handoff items

| Bucket | Examples | Routing |
|---|---|---|
| `content` | article.md, screenshots, evidence images | Auto-flows into existing scripts (Step 3 diff, Step 4 copy). |
| `mechanical-new-files` | Net-new files in `src/lib/`, `src/components/`, `src/styles/`, `src/pages/` source ships and website lacks | Claude byte-copies after **per-file** approval. |
| `dependencies` | `package.json` additions | Claude proposes `npm install <pkg>@<range>`. **Always brainstorm** (version conflicts). |
| `config-wiring` | `astro.config.mjs` plugin-chain edits, integrations | Claude proposes diff (correct insertion ordinal — e.g. `remark-directive` *before* `remark-explainers`). **Always brainstorm.** |
| `modified-shared-files` | `src/styles/global.css`, layouts, existing components touched by handoff | Claude proposes diff. **Always brainstorm** — these carry website-specific code. |
| `UX-contract` | `localStorage` keys, FOUC scripts, route surfaces (`/glossary/`, `/bookmarks/`) | Claude greps website for namespace/route collisions. **Always brainstorm.** |
| `verification-checks` | "59 pages", "108 glossary entries", "+2 routes" | Run as cross-check after Step 7 build. |

Only `content` auto-flows. `mechanical-new-files` is per-file approval (low judgement). The four UX-leaning buckets always brainstorm. `verification-checks` runs in Step 7.

### Brainstorm trigger criteria

A handoff item triggers brainstorm mode (cannot auto-apply) if **any** of:

- Touches a file in the existing skill's "DO NOT touch" list (`src/components/` outside `field-notes/svg/`, `src/lib/`, `src/styles/`, `src/pages/` outside `fieldkit/index.astro` named sections, `src/layouts/`, `astro.config.mjs`, `package.json`).
- Modifies a file with known site-specific overrides (`src/data/field-notes/project-stats.json` recall@5 override; `src/pages/fieldkit/index.astro` non-Install/Quickstart/CLI sections).
- Adds a new top-level `localStorage` namespace.
- Adds a new global CSS rule targeting a high-blast-radius selector (`.article`, `.prose`, `figure`, `img`).
- Renames or relocates a file the website already has at a different path.
- Introduces a new top-level route.
- Modifies the article template (`src/pages/field-notes/[slug]/index.astro`).
- Modifies a layout (`src/layouts/*`).
- Modifies the frontmatter schema (`src/content.config.ts`).
- Adds a dependency.
- Is destructive (file deletion, route removal) — **never auto-apply**, even with bucket-level "all default" approval.

### Decision verbs (Step 5 brainstorm)

For each handoff item presented, the user picks one of:

- **`apply`** — Claude executes (Edit / Write / Bash for `npm install`).
- **`skip`** — Item not ported in this sync; Claude logs it in the end-of-step summary.
- **`defer`** — Same as `skip` but flagged for re-surfacing on the next handoff sync.
- **`customize`** — User describes a variation; Claude proposes a modified diff and re-asks.

The user can also say **"all default"** at the top of a bucket to accept Claude's recommendation for every item in that bucket. Cross-bucket dependencies are flagged inline; if a prerequisite is skipped, dependents auto-skip.

## Workflow

Follow these steps in order. Do not skip the diff step — it's how you tell the user precisely what changed without inspecting every file by hand.

### Step 1: Confirm the local clone is up to date

Ask the user (briefly) if they've already pulled the latest from the `ai-field-notes` GitHub repo into the local clone. If they haven't, recommend they do so first via `cd /Users/manavsehgal/Developer/ai-field-notes && git pull`. Don't run `git pull` yourself — the user controls when their local repo updates.

### Step 2: Read SYNC-HANDOFF.md

Check whether `/Users/manavsehgal/Developer/ai-field-notes/SYNC-HANDOFF.md` exists.

**If absent:** Print one line — `"No SYNC-HANDOFF.md at source root — proceeding with content-only sync."` — and skip ahead to Step 3. Don't block content sync on a missing handoff (older releases, draft repos, and content-only refreshes will have none).

**If present:** Read it end-to-end with the Read tool. Extract a structured summary by walking the eight expected section headings (`File inventory`, `Dependency change(s)`, `Plugin chain`/`wiring`, `localStorage contract`, `CSS architecture`, `Reader UX`/`UX features`, `Verification`, `Conflict-avoidance notes`). Skip any section heading that's missing — the handoff format is allowed to evolve. Then classify every change item described in the handoff into one of the seven buckets (`content`, `mechanical-new-files`, `dependencies`, `config-wiring`, `modified-shared-files`, `UX-contract`, `verification-checks`).

Present a short report to the user:

- **Release headline** — pull from the handoff's `# H1` or first paragraph (e.g. "Explainers feature (Phases 1–3 + layout fix)").
- **TL;DR** — one or two sentences from the handoff's TL;DR section.
- **Bucket counts** — seven-row table of bucket name × item count × auto-flow vs brainstorm.
- **Heads-up items** — any handoff item that hits a brainstorm-trigger criterion (see "Brainstorm trigger criteria" above), surfaced with one-line context per item.

Ask the user to confirm: "Proceed with content sync (Steps 3–4) and then walk the UX brainstorm in Step 5?" Wait for explicit approval before continuing. If the user declines the UX half, run only Steps 3–4, 6, 7, 8 (and 9 if requested) — the content-only path.

### Step 3: Compute the diff

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

### Step 4: Copy the changes

If the user approves, copy the diff using:

```bash
python3 .claude/skills/sync-field-notes/scripts/sync_articles.py
```

The script applies the same rules as Step 3 in copy mode — it copies article markdown, screenshot folders, and evidence images, and skips transcript files, Python evidence, and the `_drafts/` folder. It also handles the seed-only edge case: when a folder has only `seed.md` (an upcoming placeholder with `status: upcoming` frontmatter), the seed is copied as `article.md` so the content collection picks it up as an upcoming entry.

The script is idempotent — running it twice is the same as running it once. Files are overwritten only when their content has actually changed.

**Article-sequence manifest.** The script writes `src/data/field-notes/sequence.json` from the source repo's `git log --diff-filter=A` output for `articles/*/article.md`. This captures the canonical authoring order — oldest first — and is read at build time by `src/lib/field-notes/article-order.mjs` to assign the №01..№N ordinals on article cards. Without it, the website would derive ordinals from its own git history, which collapses bulk syncs into a single commit window and reorders by alphabetical tiebreak. The manifest is rewritten only when the slug ordering actually changes, so a no-op sync produces no diff on this file. Articles whose frontmatter carries `status: upcoming` are still listed in the manifest (source committed an `article.md` for them as a placeholder) but the website's ordinal walk skips them so the published sequence has no gaps.

**Landing-page section sync.** The script also keeps the `/fieldkit/` landing page in step with the source by replacing only the inner bodies of three named `<section class="fk-section">` blocks — those whose `<h2>` text is **Install**, **Quickstart**, or **CLI**. These three are pure copy/code; they don't reference site-local URL helpers, so they transplant cleanly. The script detects target's section indentation, dedents source's body to col 0, and re-indents at target's level + 2 spaces, so the wrapping layout (`FieldNotesLayout`, `Nav`, `Footer`, `<main>`) and the Modules / Verified-in / header sections stay untouched. This is what lets a copy change like `pip install fieldkit` propagate to the site without breaking the build.

### Step 5: UX brainstorm and apply

Skip this step entirely if Step 2 found no handoff, or the user declined the UX half. Otherwise walk the buckets from Step 2 in this fixed order:

1. `dependencies`
2. `config-wiring`
3. `mechanical-new-files`
4. `modified-shared-files`
5. `UX-contract`

For each bucket, list every item with a fixed-shape block:

```
[Bucket: <name>] Item N of M
  source: <source path> (<delta from handoff, e.g. +30 -4>)
  target: <target path> (exists | does not exist | exists with overrides)
  proposed change:
    - <one or more bullets describing what the edit does>
    - <call out cross-bucket dependencies, e.g. "depends on Bucket 3 / Item 7">
  conflict signal: <none | TOUCHES "DO NOT touch" file | namespace collision | ...>
  recommendation: <apply | customize — reason | skip — reason>
  decision: [apply / skip / defer / customize] ?
```

Collect the user's per-item decision before moving to the next item. If the user says **"all default"** at the top of a bucket, accept the recommendation for every item in that bucket without further prompting.

**Before any edit, Read the target.** If the proposed insertion already exists verbatim (the user applied it manually before invoking), downgrade the item to `verify only` and don't re-apply. This prevents double-inserts when a release is partly hand-applied.

**Apply approved edits using the right tool:**

- `apply` for `dependencies` → run `npm install <pkg>@<range>` (or instruct the user to, depending on permission mode). Update `package.json` only if the user wants a manual edit instead.
- `apply` for `config-wiring` → use Edit on `astro.config.mjs` with the exact insertion ordinal from the handoff (e.g. `remark-directive` *before* `remark-explainers`).
- `apply` for `mechanical-new-files` → Read source, Write target, byte-for-byte. If the website has a like-named file already at a different path, downgrade to `customize` and surface to user.
- `apply` for `modified-shared-files` → use Edit with the exact diff. If the surrounding context has drifted between source and target, propose the closest match and ask the user to approve.
- `apply` for `UX-contract` → grep the website for the proposed namespace / route first; if a collision is detected, downgrade to `customize` automatically.

**Cross-bucket dependencies:** if a prerequisite item was skipped, automatically skip its dependents and note the cascade in the end-of-step summary.

**Destructive items** (file deletion, route removal) ALWAYS prompt explicitly, even when the user said "all default" — never auto-apply destructive operations.

**End-of-step summary table:**

```
Bucket                    apply  skip  defer  customize  total
─────────────────────────  ─────  ────  ─────  ─────────  ─────
dependencies                  1     0      0          0     1
config-wiring                 1     0      0          0     1
mechanical-new-files          7     0      0          0     7
modified-shared-files         3     0      0          1     4
UX-contract                   2     0      0          0     2
                             ──    ──     ──         ──    ──
total                        14     0      0          1    15
```

Deferred items (`skip` or `defer`) are listed by name underneath the table so the user has them in the next session's context.

### Step 6: Preserve the reframed research papers

Two articles in the website's `articles/` tree are NOT mirrors of the source — they were reframed from the old `/research/` MDX papers and live only on the website:

- `articles/ai-transformation/article.mdx` (ordinal 1, AI Native Platform series)
- `articles/solo-builder-case-study/article.mdx` (ordinal 2, AI Native Platform series)

The sync script knows about these and never touches them. If the user ever wants to update the body of these papers, do it manually in the website repo — the source `ai-field-notes` repo does not host them.

### Step 7: Build verification

After copying, build to make sure nothing broke:

```bash
npm run build
```

**Astro 5 cache caveat.** If the handoff calls for clearing caches (it usually does after a remark-plugin or content-config change), run `rm -rf .astro node_modules/.astro` before `npm run build` for the first build of this sync. Stale content-collection cache will otherwise serve pre-edit rendered articles.

Common failures and how to handle them:

- **`ImageNotFound: <path>`** — an article references an image that wasn't copied. Check whether it's a screenshot (re-run sync), an evidence image with a non-image extension (the article body needs adjustment to point elsewhere or use a GitHub link), or a typo in the article markdown.
- **Schema validation error on a frontmatter field** — the source article uses a field this site's content schema doesn't accept, OR uses an enum value not in the schema. Look at `src/content.config.ts` for the field list and decide whether to extend the schema (add the new value to STAGES/SERIES) or fix the article frontmatter. Usually it's a new tag or stage that should be allowed.
- **Series enum mismatch** — the source repo only has six series; "AI Native Platform" is exclusive to the website. If a source article uses "AI Native Platform" as its series, that's the user authoring on the website's combined taxonomy — accept it.

**Handoff verification cross-check.** If Step 2 captured a `Verification` section in the handoff, run the mechanizable checks now (after the build succeeds):

- **Page count assertion.** Parse `npm run build`'s "X page(s) built" line and compare to the handoff's stated count. The website almost certainly has more pages than source (extra `/book/`, `/docs/`, `/about/` routes), so a mismatch is expected — print the delta as a **warning**, never as an error. The check is useful only for catching big surprises (e.g. handoff says "+2 routes" but build added 0).
- **Route presence.** For each new route the handoff promises (`/glossary/`, `/bookmarks/`, etc.), confirm `dist/<route>/index.html` exists.
- **Content assertion.** For "108 entries from 31 articles"-style claims, grep the rendered HTML at the relevant route. Mismatches are warnings, not errors — destination may have a smaller article corpus than source.
- **Visual / interaction checks.** Anything that needs eyeballs (e.g. "REINFORCE explainer renders inline above the GRPO diagram at viewport ≥1472px") gets handed to Step 8 as a manual spot-check URL with the exact viewport noted.

### Step 8: Run the dev server briefly

Start the dev server and spot-check the new/updated articles render. Use the `preview_start` tool with the `astro` configuration. Visit `/field-notes/` to confirm the new articles appear in the index, then click into 2–3 of them to verify their bodies render.

**Handoff spot-check URLs.** If Step 7 deferred any visual checks from the handoff's `Verification` section, surface them here as a checklist:

```
Manual spot-checks from SYNC-HANDOFF.md:
  [ ] /articles/<slug>/ at viewport ≥1472px — confirm <feature> renders <as described>
  [ ] /glossary/ — masthead reads "<N> entries from <M> articles"
  [ ] /bookmarks/ — empty-state visible when no bookmarks set
```

The user runs these in their browser; the skill doesn't try to mechanize them. Don't block on these — they're optional polish checks.

### Step 9: Commit (only when explicitly requested)

Do not commit automatically. Show the user a `git status` summary and ask whether they want a commit. If yes, propose a one-line conventional commit message based on what changed:

- Content-only — new article(s): `feat(field-notes): add <slug-1>, <slug-2>`
- Content-only — updated article: `chore(field-notes): refresh <slug>`
- Content-only — mixed: `chore(field-notes): sync <N> articles from ai-field-notes`
- UX feature release: `feat(field-notes): add <feature-name> + sync <N> articles`
  - Pull `<feature-name>` from the handoff's H1 (e.g. "explainers feature", "reader settings + bookmarks").
- UX-only release (no article diff): `feat(field-notes): apply <feature-name> from ai-field-notes`

## Hand-curated overrides re-applied during sync

`src/data/field-notes/project-stats.json` is sourced from
`ai-field-notes/src/data/project-stats.json` (auto-regenerated on every
release of the source repo by text-mining the article corpus), but the
website needs one deterministic override to read well on the homepage and
the `/field-notes/` index. The sync script re-applies the override on every
run, so the override survives source regenerations.

| File | Override re-applied by `sync_articles.py` | Why |
|---|---|---|
| `src/data/field-notes/project-stats.json` | The entry in `metrics.accuracy[]` matched by `(article_slug == "bigger-generator-grounding-on-spark", value == "recall@5 = 1.0")` is moved to index 0, with its `label` rewritten to `"perfect retrieval on the eval set"`. | Both the homepage `FieldNotesSummary` KPI and the `/field-notes/` "At a glance" tile read `metrics.accuracy[0]`. The auto-generator orders by article-recency, which once put `9% accuracy` (out of context, unflattering) ahead of a real, equally-citable recall@5 result. The override pins the citable headline. |

The override is matched by `(article_slug, value)` rather than by index so it
survives source-side reordering. If the recall@5 entry ever stops being
auto-generated (e.g., the source pipeline changes), the override silently
no-ops — no error, no clobber of the source's first entry. To extend the
override approach to additional metrics, edit `_apply_recall_at_5_override`
in both `scripts/sync_articles.py` and `scripts/diff_articles.py`. The
diff script must mirror the override so it compares apples to apples; if
they drift, the diff reports phantom changes on every sync.

## Edge cases

**A new stage value or tag.** The schema in `src/content.config.ts` enumerates stages and series. New tags are free-form (the schema is `z.array(z.string())`). New stages are not — adding one requires adding the enum value, copy in `src/pages/field-notes/stages/[stage].astro` `STAGE_COPY` map, and (optionally) the order in `STAGE_LABELS` inside `src/components/field-notes/StageFilter.astro`. Series are similarly closed; same three-file update pattern.

**A new signature SVG component referenced by `signature: <Name>` in frontmatter.** Handled automatically by the sync script — when the source repo adds a new `*.astro` file under `src/components/svg/`, it gets copied to `src/components/field-notes/svg/` on the next sync. The ArticleCard's signature lookup is via `import.meta.glob`, so the new file is picked up by the next build with no registration. If the article ships before the signature SVG exists in source, the article still renders (the schema makes `signature` optional) — just without the signature graphic, until the next sync that includes the SVG. **One-way flow only:** the website may have signatures the source doesn't (e.g., for the two reframed papers), so target-only signatures are never deleted or reported as orphans.

**An article moves between series in the source repo.** Just copy the new `article.md`. The change in `series:` frontmatter is enough — the article will start showing up in the new series page automatically.

**An article is renamed in the source repo (slug change).** The old folder will appear as an "orphan in target" in Step 3's diff. Flag it to the user — the safe thing is to delete the orphan folder by hand (preserving any redirect they may need to add manually). Do not auto-delete; the user owns that call.

**The user has uncommitted local changes in the website's `articles/` directory.** Ask before overwriting. Show them which files are dirty. The sync script does not stash or back up — that's git's job.

**Build warns "X published article(s) not in sequence manifest — appended alphabetically."** A new article exists in the website's `articles/` tree but isn't in `src/data/field-notes/sequence.json`. Most common cause: the user added an article folder by hand, or pulled the source repo but ran `npm run build` without first running `sync_articles.py`. Re-run the sync script to regenerate the manifest. The warning is non-fatal — the website appends orphan articles alphabetically at the end of the published sequence, so the build still succeeds.

**Source repo's `git log` is unavailable (e.g., a tarball, a shallow clone with truncated history).** `_compute_source_sequence()` returns `None` and the sync script silently skips the manifest write. The website's `publishOrdinals()` then falls back to deriving order from this repo's own `git log`, the same behavior it had before the manifest existed. Order won't perfectly mirror source in this state, but the build still succeeds.

**An article moves from `status: upcoming` to published in source.** The manifest already lists the slug (it has had an `article.md` from the moment source committed the upcoming placeholder), so no manifest rewrite is needed. The website's ordinal walk previously skipped it; now it slots into its reserved position in the sequence on the next build.

**SYNC-HANDOFF.md is missing.** Older releases or content-only refreshes have none. Print one line and proceed with the original 7-step content-only flow (skip Step 5 entirely). Never block content sync on a missing handoff.

**The handoff is empty or has zero recognizable section headings.** Treat it as content-only — same fallback as missing.

**Partial application — the user already applied some UX changes manually before invoking the skill.** Step 5 must Read each target before proposing edits; if the proposed insertion already exists verbatim, downgrade that item to `verify only` and don't re-apply. This prevents double-inserts. The end-of-step summary lists the verify-only items so the user knows what was already done.

**Dependency conflict — the website's `package.json` already has the dependency at a different version.** Surface the existing version and source's requested version, then downgrade the item to `customize`. The user picks: keep website version, bump to source version, or pin to a third value.

**localStorage namespace collision.** Before approving the `UX-contract` bucket, grep `src/` for the proposed namespace (e.g. `afn:`). Today the website's `/book/` reader uses unprefixed keys (`theme`, `book-prefs`, `book-progress`, `book-bookmarks`, `ainative-book-path`), so `afn:*` is safe — but the check should still run, because future handoffs may pick a less-careful prefix.

**Handoff article count > diff article count.** If the handoff promises "31 articles touched" but Step 3's diff finds fewer, warn — most likely cause is partial prior sync. Not an error; the diff is authoritative for what to copy.

**Handoff verification cross-check mismatch.** Page count off, glossary entry count off, route presence missing. Print a warning with the delta; don't block. The website's surface area legitimately differs from source.

**Handoff describes a destructive change.** File deletion, route removal, dependency removal. Always prompt explicitly per item — never auto-apply, even when the user said "all default" for the bucket.

**Two handoff items contradict each other.** E.g. one section says "modify global.css line 47" and another says "delete global.css line 47". Flag the inconsistency, present both, ask the user to choose. Don't try to reconcile algorithmically.

**Build fails after UX apply.** Walk the user through `git diff` to see what was changed, then through manual revert (`git checkout -- <file>`) for the offending edit. Don't auto-rollback — the user owns that call, and the just-applied edits may be salvageable with a small fix.

## Why this design

- **Same `articles/<slug>/article.md` layout in both repos.** The only reason this skill exists at all is to keep that mirror in sync. If the layouts diverged, the integration would need a transform step. They don't, so the integration is `cp`.
- **Diff before copy, not blind copy.** A blind copy works but doesn't tell the user what changed, which makes it easy to miss when something is moving that shouldn't be (a renamed slug, an accidentally-published seed). The diff is the receipt.
- **Evidence-folder filter at the boundary.** The plan defers per-article evidence migration; the default is "images yes, source code no." The user can hand-port a Python file or a .ipynb if they want to publish it for a specific article — but the default sync never carries source code along.
- **No git operations.** The drafting repo is the user's authoring environment; this skill stays a one-way mirror. The user pulls when they want to pull, commits when they want to commit, and runs this skill when they want to surface changes on the public site.
- **Sequence manifest, not per-article frontmatter.** The website needs to know source's authoring order to render matching №01..№N labels, but encoding that into each article's frontmatter would smear ordering metadata across 30+ files and require re-stamping every article on every sync. A single manifest file is the cheaper representation: one diff, one place to look, and the file's own `git log` becomes the audit trail for "when did the sequence last change?". The manifest also keeps the build hermetic — `publishOrdinals()` reads a checked-in JSON, not a sibling repo at build time, so CI on GitHub Pages still works.

### Why this design (handoff-aware)

- **Scripts stayed unchanged.** UX changes touch files the scripts intentionally avoid (`src/components/` outside `field-notes/svg/`, `src/lib/`, `src/styles/`, `src/layouts/`, `astro.config.mjs`, `package.json`). Extending the scripts would force a parallel "judgement engine" inside Python that Claude's Edit/Write/Bash tools already provide. Mechanical/judgement split keeps each layer simple — scripts stay small and well-tested; Claude handles the varied stuff.
- **Parsing is semantic, not schema'd.** The handoff format is allowed to evolve. The skill names eight expected section headings to look for, but degrades gracefully when any are missing. A schema would make source-side authoring fragile and destination-side parsing brittle.
- **Brainstorm is per-bucket batched, not per-item-from-zero.** A single dump of 23 items overwhelms the user; per-item from item 1 burns context. Per-bucket batched review with "all default" escape lets the user move quickly through low-risk buckets and slow down where judgement is needed.
- **Verification is cross-check, not hard gate.** The handoff's "59 pages" and "108 glossary entries" assertions are written for the source's surface area. The website has additional routes (`/book/`, `/docs/`, `/about/`) and may have a smaller article corpus, so an exact match is the wrong success criterion. Warn-not-error preserves the signal without manufacturing false failures.
- **No script extension.** Claude's Edit/Write/Bash tools already provide the engine for ad-hoc UX edits. Duplicating that engine in Python adds complexity for negative value — and the handoff is varied enough that any scripted UX engine would lag the format anyway.
