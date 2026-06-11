---
name: sync-field-notes
description: Sync field-notes articles AND apply UX feature changes from the ai-field-notes source repo (github.com/manavsehgal/ai-field-notes, cache-cloned locally) into this website. Uses the source's git log as the change narrative; runs the diff scripts to copy article markdown, screenshots, evidence images, signature SVGs, fieldkit landing sections, and project-stats; verifies the build. Supports bidirectional writes — when source-side nits are spotted during review (missing footer, frontmatter typo, broken link), the skill edits the file in the cache clone, commits on main, and pushes to origin. Use when the user says "sync field notes", "update field notes", "check what's new from spark", "spark commit", "new article in ai-field-notes", "ai-field-notes has new content", "ship reader UX from ai-field-notes", "fix the source-side <issue>", "refresh field notes from source", or any request to surface changes from the source repo into the website. Also trigger when the user mentions a specific article slug they just published on spark (e.g., "I just shipped the kv-cache piece — sync it over") or a feature shipped in source (e.g., "ship the explainers feature over").
---

# Sync Field Notes Skill

Mirrors field-notes content (articles + supporting surfaces) from the **ai-field-notes source repo** at `https://github.com/manavsehgal/ai-field-notes` into this website at `/Users/manavsehgal/Developer/ainative-business.github.io/`. The website's `/field-notes/` section is an Astro content collection that loads from `articles/<slug>/article.{md,mdx}` at the project root, mirroring the layout in the source repo so a copy is the entire integration.

**Source is the GitHub remote, read via a local cache clone.** The skill keeps a disposable clone at `~/.cache/ai-field-notes-src` (override with `AI_FIELD_NOTES_SRC`) and refreshes it to `origin/main` at the start of every run — `git fetch && git reset --hard origin/main`. This replaced the old SMB mount at `/Volumes/home/ai-field-notes`: pulling over `https` instead of reading Spark's working tree over `smbfs` removes every stale-handle / torn-write / peer-lock failure mode the mount had. Spark keeps the remote current by pushing to `origin/main`. **The skill syncs committed + pushed state, never a live working tree** — only intentional, pushed work flows.

**Git is the change narrative.** `git -C ~/.cache/ai-field-notes-src log` (after the Step 1 refresh) answers "what changed on source since last destination sync?" deterministically. **Writes flow both ways.** When Claude spots a source-side issue during review (missing catalog footer, frontmatter typo, etc.), it edits the file in the cache clone, commits on `main`, and pushes to `origin` — git is the transport, so there is no torn-write window.

The source-path resolution (cache location, remote URL, branch, and every mirrored sub-path) lives in one module: `.claude/skills/sync-field-notes/scripts/source_repo.py`. Both diff and sync scripts import their source paths from it.

## Source and target paths

The "Source" column is relative to the cache clone root `~/.cache/ai-field-notes-src/` (= `$AI_FIELD_NOTES_SRC`), which mirrors `origin/main`.

| Content | Source (cache clone of origin/main) | Target |
|---|---|---|
| Article markdown | `articles/<slug>/article.md` | `articles/<slug>/article.md` |
| Article MDX (research papers) | `articles/<slug>/article.mdx` | `articles/<slug>/article.mdx` |
| Upcoming-only seed (no article.md yet) | `articles/<slug>/seed.md` | `articles/<slug>/article.md` (renamed) |
| Screenshots | `articles/<slug>/screenshots/` | `articles/<slug>/screenshots/` |
| Evidence images | `articles/<slug>/evidence/*.{png,jpg,jpeg,svg,gif,webp}` | `articles/<slug>/evidence/` |
| Fieldkit module reference | `fieldkit/docs/api/*.md` | `fieldkit/docs/api/*.md` |
| Fieldkit version pin | ~~`fieldkit/src/fieldkit/_version.py` → `fieldkit/_version.py`~~ | RETIRED 2026-06-10 — the landing page reads the canonical `fieldkit/src/fieldkit/_version.py` directly; never recreate the mirror (it froze the live page at v0.13.0 for 18 releases) |
| Fieldkit landing page sections (Install / Quickstart / CLI) | `src/pages/fieldkit/index.astro` | `src/pages/fieldkit/index.astro` (only the named `<section>` bodies are replaced) |
| Signature SVG components | `src/components/svg/*.astro` | `src/components/field-notes/svg/*.astro` |
| Article-sequence manifest | (derived from the cache clone's `git log`, no on-disk source) | `src/data/field-notes/sequence.json` |
| Project-stats JSON ("At a glance" KPIs) | `src/data/project-stats.json` | `src/data/field-notes/project-stats.json` (with one hand-curated override re-applied) |

## What to copy and what to skip

**Copy:**
- `article.md` and `article.mdx` (the article body)
- `screenshots/` directories (entire folder, all files)
- Image files inside `evidence/` directories (`*.png`, `*.jpg`, `*.jpeg`, `*.svg`, `*.gif`, `*.webp`)
- New article folders that don't yet exist in the target
- Signature SVG components (`*.astro` from source's `src/components/svg/` → target's `src/components/field-notes/svg/`). One-way flow only — the website may have signatures the source doesn't (e.g., for the two reframed papers), and those are never deleted.

**Generate (not a file copy):**
- `src/data/field-notes/sequence.json` — derived from the cache clone's `git log` output for `articles/*/article.md`, captures the canonical authoring order so the website's №01..№N ordinals track source order across syncs.

**Skip:**
- `transcript.md` (authoring-time artifact, never published)
- `seed.md` IF a real `article.md` already exists alongside it
- All non-image files inside `evidence/` directories (Python source code, ~30k lines — link out to GitHub if articles need to reference raw evidence)
- The `_drafts/` folder at the root of the source `articles/` directory
- `notebooks/` (notebook `.ipynb`/`.py` + their rendered `exports/*.png` live on GitHub and render in Colab/Kaggle — the website references them via `kind: notebook` manifest links, it doesn't host them)
- Landing page sections **other than** Install / Quickstart / CLI (rest is site-specific brand framing)

## Workflow

Follow these steps in order. Steps 3 and 5 are the load-bearing ones; the rest are guardrails and narrative.

### Step 1: Refresh the source cache clone

```bash
python3 .claude/skills/sync-field-notes/scripts/source_repo.py
```

This clones `github.com/manavsehgal/ai-field-notes` into `~/.cache/ai-field-notes-src` on first run, and on every subsequent run does `git fetch --prune origin main && git reset --hard origin/main`. It prints the resulting `HEAD <sha> <subject>` for context.

If it exits non-zero, the remote is unreachable (no network, GitHub down, or auth failure on a private fork) or the cache path is occupied by a non-git directory. Surface the error to the user and stop — don't proceed against a stale or partial cache.

There is **no mount health check and no peer-writer lock** anymore. The cache clone is per-machine and private to this skill, so there is no shared tree to coordinate; the old `peer_lock.py` heartbeat was retired with the mount.

### Step 2: Show what's new since last destination sync (narrative)

Find the destination's most recent commit touching synced paths:

```bash
git log --oneline -1 -- articles/ src/components/field-notes/svg/ src/data/field-notes/ src/pages/fieldkit/index.astro fieldkit/
```

Take that commit's committer date (`git log -1 --format=%cI <sha>`), then enumerate source commits since (against the freshly-refreshed cache clone):

```bash
git -C ~/.cache/ai-field-notes-src log --since=<date> --oneline
```

Print the list with one line of context per commit (subject + a hint at files touched via `--stat=80,40` if you want detail). This is decoration — it tells the user *why* the upcoming diff exists. If destination has no prior sync commit, fall back to `--oneline -20` on the cache clone.

### Step 3: Compute the content diff

```bash
python3 .claude/skills/sync-field-notes/scripts/diff_articles.py
```

The script reads the cache clone (via `source_repo.py`) and prints structured findings:
- **New articles** (folders present in source but not target)
- **Updated articles** (article.md / article.mdx hash differs, with link-rewrite + gated-footer-strip applied before comparing)
- **New or changed images** (screenshots and evidence images)
- **Signature SVG drift** (new or changed `*.astro` files under source's `src/components/svg/`)
- **Fieldkit landing drift** (Install/Quickstart/CLI section bodies differ)
- **Fieldkit version + module-reference doc drift**
- **Project-stats drift** (KPI deltas after recall@5 override re-applied)
- **Articles only in target** (orphans — usually a renamed slug; flag for human review, do not auto-delete)

Show the diff to the user before copying anything. If the diff is empty AND Step 4 finds nothing, stop and report "no changes to sync."

### Step 4: Surface non-tracked source-side changes (judgement loop)

From the commits-since-last-sync window in Step 2, find files modified that are OUTSIDE the auto-flow surfaces (which Step 3 already covers):

```bash
git -C ~/.cache/ai-field-notes-src log --since=<date> --name-only --pretty=format: \
  | sort -u \
  | grep -vE '^(articles/|notebooks/|src/components/svg/|src/data/project-stats\.json|src/pages/fieldkit/index\.astro|fieldkit/(docs/api/|src/fieldkit/_version\.py)|SYNC-|mirrors/|ideas/|papers/|specs/|plans/|scripts/|probes/|dataset-cards/|share/|evidence/|README\.md|HANDOFF\.md|COMMANDS\.md|CHANGELOG\.md|package-lock\.json|node_modules/|unsloth_compiled_cache/|dist/)'
```

Anything left is a candidate UX/config change: new file under `src/components/` (excluding `svg/`), edited `src/styles/global.css`, edited `astro.config.mjs`, modified `package.json`, etc. Present the list and, for each, ask the user one of: **inspect** (Read source + brainstorm an edit on destination), **skip** (not porting in this sync), **defer** (re-surface on next sync). Empty list → skip this step silently.

If a candidate file is `package.json`, run `diff` between source and destination to see the actual dependency delta before proposing `npm install <pkg>@<range>`. If it's `astro.config.mjs`, Read both files before proposing an Edit — plugin-chain insertion order matters (e.g. `remark-directive` *before* `remark-explainers`).

**Before any UX edit, Read the destination target.** If the proposed change already exists verbatim, mark the item "verify only" and don't re-apply. Destructive changes (file deletion, route removal) ALWAYS prompt explicitly per item.

**Existing artifact-manifest "drift" is usually a false positive — do NOT propose a re-copy by default.** When a candidate file is an existing `src/content/artifacts/<slug>.yaml`, source's manifest carries only the bare frontmatter that `fieldkit.publish` writes (slug/kind/class/base_model/hf_repo/license/article/published_at), while destination's version is destination-extended with the measurement data that drives rendering (bench `shapes`/`modes`/`results`, quant `perplexity`/`spark_tokens_per_sec`/`vertical_eval`, lora deltas, etc.). Re-copying clobbers the rendering data and breaks `visual-required` in the post-build verifier. The cheap pre-flight check is line count: `wc -l <source> <destination>` — if source is dramatically smaller, treat the drift as destination-authoritative and skip. Only propose the copy when the user explicitly asks to absorb a source-side editorial change (new `positioning`, expanded `known_drift`, new `notebooks` block) AND a line-count diff confirms source isn't truncated relative to destination. **New** `*-notebooks.yaml` manifests (or any new artifact-kind manifest) ARE editorial-only on source, so those flow normally — this rule applies only to existing manifests with destination measurement data.

Note: `src/content/artifacts/*.yaml` is not in the auto-flow surfaces, so manifests appear here as Step 4 judgement items. When source **deletes** a manifest (e.g. an unpublished model lane), the corresponding destination `.yaml` becomes an orphan whose catalog footer may 404 — surface the deletion and repoint/remove on the destination by hand (see the gated-footer + render-path notes in Step 5).

### Step 5: Apply the diff

If the user approves Step 3's content diff:

```bash
python3 .claude/skills/sync-field-notes/scripts/sync_articles.py
```

The script applies the same rules as Step 3 in copy mode — articles, screenshots, evidence images, signature SVGs, fieldkit landing sections (only Install/Quickstart/CLI bodies), fieldkit docs + version pin, project-stats (with recall@5 override re-applied), and the sequence manifest. It also handles the seed-only edge case: when a folder has only `seed.md`, the seed is copied as `article.md` so the content collection picks it up as upcoming. Idempotent — running it twice is the same as running it once.

**Article-sequence manifest.** Derived from the cache clone's `git log --diff-filter=A` for `articles/*/article.md` — captures the canonical authoring order. Rewritten only when slug ordering actually changes.

**Landing-page section sync.** Replaces only the inner bodies of three named `<section class="fk-section">` blocks (Install / Quickstart / CLI). The wrapping layout, Modules section, and Verified-in section stay untouched.

**Gated catalog-footer preservation.** Articles with a matching catalog manifest at `src/content/artifacts/<slug>.yaml` carry a Mac-owned trailing chrome block:

> `**Catalog page:** [/artifacts/<kind>/<artifact-slug>/](...) — the same four-axis card rendered on this site, with the sweet-spot variant highlighted on a heatmap row.`

The source repo deliberately doesn't carry this block. Both diff and sync scripts strip the footer from target before comparing, then `restore_gated_footers()` re-appends the canonical footer after sync. The binding is data-driven — drop a new `src/content/artifacts/<slug>.yaml` with `article: articles/<slug>/` and the matching article picks up its footer on the next sync. When an article binds to **multiple** manifests, deleting one manifest causes the next sync's footer restore to repoint at a surviving manifest — verify the resulting footer URL after a manifest deletion.

After `sync_articles.py` runs, separately walk any per-file Step 4 items the user approved: Read source file → Edit/Write target.

**Render-path sanity check (artifact manifests).** When `src/content/artifacts/*.yaml` files were copied or removed in this sync, confirm each live manifest's `kind:` has a corresponding render path under `src/pages/artifacts/<segment>/[slug]/index.astro`. The current valid kinds are: `quant` → `/quants/`, `lora` → `/loras/`, `adapter` → `/adapters/`, `dataset` → `/datasets/`, `bench` → `/benches/`, `notebook` → (rendered via the bound model manifest, no standalone route). Mismatches (e.g. a `kind: lora` manifest before the `/loras/` route exists, or a footer pointing at a just-deleted manifest) will silently produce 404s on the catalog footer's link — surface to the user, never auto-fix. The narrative/visual contract a synced manifest must satisfy is documented at `.claude/skills/sync-field-notes/references/site-rendering-rubric.md`. After sync, run `npm run build` — the post-build verifier at `scripts/verify_artifact_rendering.mjs` enforces the contract and fails the build on violation.

### Step 6: Source-side nit fixes (optional, user-driven)

When the user spots a source-side issue during Step 3/4 review (e.g. "article X is missing its catalog footer", "frontmatter typo in Y", "image filename is wrong", "footer in Z links to the wrong artifact"), Claude can fix it directly in the cache clone and push to `origin`. Because git is the transport, there is no torn-write risk — just normal `Edit`/`Write` on local files, then commit + push.

For each fix:

1. **Read + Edit the file in the cache clone** at `~/.cache/ai-field-notes-src/<path>` using the normal `Read` and `Edit`/`Write` tools. (These are ordinary local-disk files — none of the old `smbfs` atomic-write dance applies.)
2. Confirm with the user before committing.
3. After the user approves the batch:
   - `git -C ~/.cache/ai-field-notes-src pull --rebase origin main` — catch any Spark push that landed since Step 1. If the rebase reports conflicts, abort (`git -C ~/.cache/ai-field-notes-src rebase --abort`), surface to the user, and don't push.
   - `git -C ~/.cache/ai-field-notes-src add -- <paths>` — stage only the files Claude edited (never `add -A`).
   - `git -C ~/.cache/ai-field-notes-src commit -m "<conventional message>"` — generated subject like `chore(field-notes): restore catalog footer on <slug>` or `fix(field-notes): correct frontmatter typo in <slug>`. Include `Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>`.
   - `git -C ~/.cache/ai-field-notes-src push origin main`.
4. After the source-side commit lands on `origin`, re-run Step 3 + Step 5 to pull the fix through to destination (some fixes — like footer restoration — only show as a destination diff once the source is fixed).

**Push before the next Step 1.** The cache clone is `reset --hard origin/main` at the start of every run, so an *unpushed* local commit would be silently discarded on the next refresh. Always push Step 6 commits in the same session; never leave a local-only commit in the cache clone. The push step is gated by user approval — never auto-push without confirmation.

Spark picks the fix up on its next `git pull`. There is no longer any need to write to Spark's disk directly (no `ssh spark`, no SMB) — origin/main is the rendezvous.

### Step 7: Build verification

```bash
npm run build
```

**Astro 5 cache caveat.** If Step 4 touched the content config, a remark plugin, or `astro.config.mjs`, run `rm -rf .astro node_modules/.astro` before the first build.

`npm run build` runs two build-blocking post-build verifiers (non-zero exit fails the build):
- `scripts/verify_artifact_rendering.mjs` — artifact card/detail narrative + visual contract.
- `scripts/verify_field_notes_rendering.mjs` — article-body **explainer float contract**: every explainer aside whose next significant sibling is another explainer (or a `<figure>`) must carry the `explain--before-explainer` (or `explain--before-figure`) un-float class. This catches orphaned gutter floats from clustered explainers on any synced article. The contract + pipeline (`remark-explainers.mjs` → `rehype-explainer-figure.mjs` → `src/styles/explainers.css`, all destination-owned) is documented in `references/site-rendering-rubric.md` → "Article-body explainer rendering". A failure here is a plugin/CSS regression in this repo, never an article-authoring problem — do not edit the synced `article.md` to work around it.

Common failures:

- **`ImageNotFound: <path>`** — an article references an image that wasn't copied. Check whether it's a missed screenshot (re-run sync), an evidence file with a non-image extension (article body needs to point elsewhere or use a GitHub link), or a typo.
- **Schema validation error on a frontmatter field** — source article uses a field this site's schema doesn't accept, or an enum value not in `STAGES`/`SERIES`. Check `src/content.config.ts`. Usually it's a new tag or stage that should be allowed — extend the schema (and the matching copy in `src/pages/field-notes/stages/[stage].astro` `STAGE_COPY` for stages).
- **Series enum mismatch** — "AI Native Platform" is exclusive to the website (used by the two reframed papers). If source ever uses it, accept it.
- **`verify_field_notes_rendering` violation** — an explainer is missing its un-float class. The fix is in `rehype-explainer-figure.mjs` (tagging) / `explainers.css` (un-float rule), not the article. See the rubric section above.

### Step 8: Run the dev server briefly

Start `npm run dev`, visit `/field-notes/` to confirm new articles appear in the index, then click into 2–3 to verify their bodies render. Confirm signatures and gated catalog footers are present where expected. At a wide window (≥64rem), spot-check any article with clustered or trailing explainers (`:::why`/`:::deeper`/`:::hardware` back-to-back): they should stack as full-width inline callouts, not float orphaned in the right gutter with whitespace beside them. (The Step 7 verifier already enforces this structurally; this is the visual confirmation.)

### Step 9: Commit on destination (only when explicitly requested)

Don't commit automatically. Show the user a `git status` summary and ask whether they want a commit. Propose a one-line conventional message:

- New article(s) — `feat(field-notes): add <slug-1>, <slug-2>`
- Updated article — `chore(field-notes): refresh <slug>`
- Mixed — `chore(field-notes): sync <N> articles from ai-field-notes`
- UX feature release — `feat(field-notes): add <feature-name> + sync <N> articles`
- UX-only release (no article diff) — `feat(field-notes): apply <feature-name> from ai-field-notes`

(No peer-writer heartbeat to release — that machinery was retired with the mount.)

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

**Remote unreachable.** `source_repo.py` exits non-zero on `git clone`/`git fetch` failure (no network, GitHub down, auth failure on a private fork). Stop and surface — don't proceed against a stale cache. If the user knows the network is fine and just wants to re-use the existing cache, they can re-run later; the cache is not deleted on a failed fetch.

**Cache path occupied by a non-git directory.** `ensure_fresh()` raises if `~/.cache/ai-field-notes-src` exists but has no `.git`. Remove the directory (or point `AI_FIELD_NOTES_SRC` at a clean path) and re-run Step 1.

**Spark committed but hasn't pushed.** The remote model only sees `origin/main`. If the user says "I just changed X on Spark" but the diff doesn't show it, the commit hasn't reached `origin` — ask them to `git push` from Spark (or `ssh spark 'cd ~/ai-field-notes && git push'`), then re-run Step 1. This is the deliberate trade-off of syncing pushed state rather than a live working tree.

**Unpushed Step 6 commit in the cache clone.** The next Step 1 `reset --hard origin/main` discards it. Always push Step 6 commits in the same session (see Step 6). If a commit was lost this way, it can be recovered from the clone's reflog (`git -C ~/.cache/ai-field-notes-src reflog`) until gc runs.

**Source push rejected (non-fast-forward) in Step 6.** A Spark push landed between your Step 1 refresh and your Step 6 push. `pull --rebase origin main` should fast-forward; if the rebase conflicts, abort it, surface to the user, and don't push.

**A new stage value or tag.** The schema in `src/content.config.ts` enumerates stages and series; new tags are free-form (`z.array(z.string())`). New stages require updating the enum + `STAGE_COPY` map in `src/pages/field-notes/stages/[stage].astro` + (optionally) `STAGE_LABELS` order in `src/components/field-notes/StageFilter.astro`. Series are similarly closed.

**A new signature SVG component referenced by `signature: <Name>` in frontmatter.** Handled automatically by the sync script. ArticleCard's signature lookup uses `import.meta.glob`, so the new file is picked up at next build with no registration. If the article ships before the SVG exists in source, it renders without the graphic (schema marks `signature` optional) until the next sync that includes the SVG. **One-way flow only:** target-only signatures (reframed papers) are never deleted.

**An article is renamed in the source repo (slug change).** The old folder appears as an "orphan in target" in Step 3's diff. Flag it to the user — the safe move is to delete the orphan by hand (preserving any redirect they may need to add). Do not auto-delete.

**Uncommitted local changes in the website's `articles/` directory.** Ask before overwriting. Show which files are dirty. The sync script does not stash — that's git's job.

**Source repo's `git log` is unavailable** (e.g., a shallow clone with truncated history — `git clone` here is a full clone, so this is unlikely). `_compute_source_sequence()` returns `None` and the sync script silently skips the manifest write. The website's `publishOrdinals()` falls back to deriving order from this repo's own git log. Order may not perfectly mirror source but the build succeeds.

**An article moves from `status: upcoming` to published in source.** The manifest already lists the slug (it has had an `article.md` from the moment source committed the upcoming placeholder), so no manifest rewrite. The website's ordinal walk now slots it into its reserved position.

**A new artifact manifest lands but the matching article has no catalog footer.** Run `sync_articles.py` — `restore_gated_footers()` appends the footer automatically once the manifest exists at `src/content/artifacts/<slug>.yaml` with a valid `article: articles/<slug>/` field.

**Stale catalog footer on an article whose manifest moved or was deleted.** The restore step strips any trailing catalog footer before re-appending. If a manifest is removed, the footer is also removed on next sync. If a manifest's `slug:` changes, the footer is rewritten to point at the new URL. When an article binds to several manifests and one is deleted, the footer repoints to a surviving manifest — verify the new URL resolves.

**Artifact `kind:` is unmapped in `chrome_footers._KIND_TO_URL_FAMILY`.** The footer is silently skipped (defensive — better to skip than emit a broken URL). Add the new kind to the map when fieldkit ships a new publisher module.

**Existing artifact manifest at `src/content/artifacts/<slug>.yaml` is bigger on destination than source.** This is the common case for any manifest with rendering data (bench `shapes`/`results`, quant `perplexity` tables, etc.) — source's `fieldkit.publish` only writes the bare publisher-frontmatter fields, while destination extends them. A naïve `diff -q` flags the file as drifted; copying would clobber destination chrome and break the page's signature SVG (`visual-required` violation in `verify_artifact_rendering.mjs`). Default is "destination authoritative, do not copy." If a sync run did clobber by mistake, restore via `git checkout HEAD -- src/content/artifacts/<slug>.yaml`. Adding a new field source-side that destination should pick up (e.g., a new `positioning` block) requires a manual merge — `git show HEAD:<path> | diff - <source-path>` first, then a targeted `Edit` to add only the new field.

**Manifest with `kind:` whose render path under `src/pages/artifacts/<segment>/[slug]/index.astro` is missing.** Build will succeed but the catalog-footer URL is a 404. Pre-flight check: the destination's `src/lib/artifacts.ts` (`SEGMENT_BY_KIND`) and the file system (`ls src/pages/artifacts/`) must both have the segment before a new-kind manifest goes live. If the render path file exists but the kind isn't in `chrome_footers._KIND_TO_URL_FAMILY`, the footer is silently skipped — see the entry above.

**Build warns "X published article(s) not in sequence manifest — appended alphabetically."** A new article exists in the website's `articles/` tree but isn't in `src/data/field-notes/sequence.json`. Most common cause: the user added an article folder by hand, or ran `npm run build` without first running `sync_articles.py`. Re-run sync to regenerate the manifest. Non-fatal.

## Why this design

- **Remote, not mount.** Reading `origin/main` over `https` via a disposable cache clone is immune to the failure modes the `smbfs` mount had — stale handles when Spark slept, torn writes on WiFi blips, and the peer-writer contention that the heartbeat lock existed to mitigate. The trade-off is that only committed + pushed work syncs; that is a feature, not a limitation (no half-edited working tree ever leaks to the website).
- **One module owns source paths.** `source_repo.py` is the single definition of where the cache lives and every sub-path the skill mirrors. Both diff and sync scripts import from it, so re-homing the source again is a one-file change. Cache location, remote, and branch are all env-overridable.
- **Git is the narrative.** `git -C ~/.cache/ai-field-notes-src log` (after Step 1's refresh) answers "what changed on source since last sync?" deterministically. The diff script remains the authoritative "what to copy" — git is just the human-readable receipt.
- **Bidirectional writes ride git.** Source-side fixes are edited in the cache clone, committed, and pushed to `origin/main` — Spark pulls them on its next sync. No SMB, no torn-write window, no machine-spanning airlock.
- **Scripts do mechanical, Claude does judgement.** The Python scripts auto-flow the well-known surfaces (articles, screenshots, evidence images, signature SVGs, fieldkit landing sections + docs + version, project-stats, gated footers). Anything outside those surfaces is surfaced as a per-file judgement loop in Step 4 — Claude reads, brainstorms, and Edit/Writes. This split keeps each layer simple.
- **Gated chrome blocks are data-driven, not allowlisted.** The trailing catalog footer is owned by Mac. The script discovers which articles get the footer by reading `src/content/artifacts/*.yaml` for `article: articles/<slug>/` bindings — no skill-side allowlist to maintain. Drop a new manifest, the matching article picks up its footer on next sync.
- **Sequence manifest, not per-article frontmatter.** The website needs source's authoring order to render matching №01..№N labels, but encoding that into each article's frontmatter would smear ordering metadata across 30+ files. A single manifest file is the cheaper representation: one diff, one place to look, one git audit trail.
