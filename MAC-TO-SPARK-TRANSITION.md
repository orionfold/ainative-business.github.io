<!--
  MAC-TO-SPARK-TRANSITION.md
  Written on the Mac (ainative-business.github.io) on 2026-05-29 as the operating
  handoff for consolidating website production onto Spark. Read this first when
  Spark takes over the repo. Once the cutover in §6 is complete and stable, this
  Mac folder can be archived.
-->

# Mac → Spark transition — operating handoff

## 1. Why this exists & the new model

Until now `ainative.business` was produced in **two steps**:

- **Spark** (the DGX Spark) authored field-notes content in `ai-field-notes` and pushed to `github.com/manavsehgal/ai-field-notes`.
- **This Mac project** (`ainative-business.github.io`) published the website: it synced that content in, ran the build, and deployed to GitHub Pages.

We are **consolidating website production onto Spark**. After cutover, Spark stops being only the content author and instead **clones this repo's remote and operates it directly** — running the sync, build, deploy, and the destination-side editorial work itself. This Mac folder then gets archived.

**Key principle:** git already carries everything Spark needs. All 11 custom skills, `scripts/`, the verifiers, and `.claude/settings.json` are tracked. A plain `git clone` reproduces the working environment. This document transfers the *operating knowledge* and the *ownership boundary* — not files.

- **Remote:** `git@github.com-manavsehgal:manavsehgal/ainative-business.github.io.git`
- **Live site:** `ainative.business` (CNAME), Astro 5 → GitHub Pages.
- **No `CLAUDE.md`/`README.md` at root** — operating knowledge lives in `HANDOFF.md` + the per-skill `SKILL.md` files + this doc (see §7).

---

## 2. What Spark owns immediately (fully portable — no Mac dependency)

### Field-notes content sync — `sync-field-notes` skill
The skill mirrors committed+pushed state from the `ai-field-notes` source into the website (articles, screenshots, evidence images, signature SVGs, fieldkit docs/version, project-stats, sequence manifest, and Mac-owned gated catalog footers).

On Spark, **point the sync at Spark's own `ai-field-notes`** via env vars (resolved in `.claude/skills/sync-field-notes/scripts/source_repo.py`):

| Env var | Default | Set on Spark to |
|---|---|---|
| `AI_FIELD_NOTES_SRC` | `~/.cache/ai-field-notes-src` | Spark's local `ai-field-notes` working copy (or leave default to clone the remote) |
| `AI_FIELD_NOTES_REMOTE` | `https://github.com/manavsehgal/ai-field-notes.git` | unchanged |
| `AI_FIELD_NOTES_BRANCH` | `main` | unchanged |

The skill syncs **committed + pushed** state only — Spark should commit/push its authoring in `ai-field-notes` before (or as part of) a sync run. Full workflow: `.claude/skills/sync-field-notes/SKILL.md`.

### Build & deploy
- Deploy is automatic: `.github/workflows/deploy.yml` runs on every push to `main` (also `workflow_dispatch`). It installs Chrome in CI, runs `npm run build`, and publishes `dist/` to GitHub Pages. **No local build is required to ship** — pushing to `main` is the deploy.
- Local build chain (`package.json`):
  ```
  npm run build
    = astro build
   && node scripts/generate-slashless-duplicates.mjs   # trailingSlash:'always' + slashless aliases
   && npm run build:og                                  # tsx scripts/generate-og-images.ts (Puppeteer)
   && node scripts/verify_artifact_rendering.mjs        # contract gate (exit code = #failures)
   && node scripts/verify_field_notes_rendering.mjs     # contract gate (exit code = #failures)
  ```
- **OG image generation needs Chrome** via `CHROME_PATH` / `PUPPETEER_EXECUTABLE_PATH` (uses `puppeteer-core`). CI installs it; for a local Spark build either install Chrome or rely on CI to generate OG images on push.

### Build-time contracts (destination-owned)
Two post-build verifiers fail the build on violation — these encode the website's rendering contract, **not** authoring rules, so a failure is a template/CSS regression to fix on the destination side:
- `scripts/verify_artifact_rendering.mjs` — drift entries carry measurable bounds, no forward-looking roadmap language, signature SVG present, NotebookBadges before first `<h2>`.
- `scripts/verify_field_notes_rendering.mjs` — explainer float classes (`explain--before-explainer`, `explain--before-figure`).

### Editorial contracts that travel
- **In this repo:** `.claude/skills/sync-field-notes/references/site-rendering-rubric.md` (manifest field → Astro slot mapping, visual/accessibility rules).
- **In the `ai-field-notes` source repo (Spark already has these):** `NARRATIVE-CONTRACT.md`, `mirrors/destination-overrides.md` (the "paths the website owns, source must not stomp" list), and `SYNC-WORKFLOW.md`. ⚠️ `SYNC-WORKFLOW.md` describes the older NFS/two-machine model and is largely **moot** once Spark operates this repo directly — treat it as historical; update or retire it on the source side at your convenience.

### Settings & hooks
`.claude/settings.json` (tracked) carries a `SessionStart` hook that warns if the last GitHub Pages deploy failed (needs `gh` + `jq` on PATH). Spark inherits it on clone.

---

## 3. What stays Mac-side for now (product-derived work)

The **product repo `/Users/manavsehgal/Developer/ainative/` lives on the Mac and stays there.** The skills below read from it, so they are present in the clone but **will not run on Spark until the product source is reachable** — do not run them on Spark yet. A later phase will simplify this (Spark picking up product changes from the product's **public** repo); until then this is the boundary.

| Skill | Mac-local dependency | Why it can't run on Spark yet |
|---|---|---|
| `apply-screengrabs` | `/Users/.../ainative/screengrabs/` + `manifest.json` | reads product screenshots |
| `apply-product-docs` | `/Users/.../ainative/docs/features/*.md` | reads product feature docs |
| `apply-api-docs` | `/Users/.../ainative/src/app/api/` + validators/schema | reads product API source |
| `apply-book-update` | `/Users/.../ainative/book/chapters/` + images | reads product book content |
| `ainative-stats` | `/Users/.../ainative/` (+ `tokei`) | counts product LOC/tests/commits |
| `apply-product-release` | orchestrates the five above | inherits all product deps |
| `deck` | product roadmap/CHANGELOG + `ainative-stats.md` + Chrome + `/deck/` | builds the prospect PPTX |
| `seo-monitor` | Chrome + signed-in Google (GSC/GA4) session | scrapes Search Console / GA4 |

**Future simplification (deferred):** wire `apply-*` / `ainative-stats` to read the product's **public** repo (env-var `PRODUCT_ROOT` or a clone), so Spark can run product→website sync without the private Mac path. Not in scope for this cutover.

---

## 4. Mac-local dependencies a Spark clone will NOT have

- **Product repo** at `/Users/manavsehgal/Developer/ainative/` — Mac-only (see §3).
- **Chrome binary** — needed for OG image generation and `deck`. CI handles OG on push; install Chrome on Spark only if you build OG locally.
- **`tokei`** — fast LOC counter for `ainative-stats` (falls back to `find + wc -l`).
- **Browser + Google OAuth session** — `seo-monitor` only; interactive, Mac-side.
- **`/deck/`** — gitignored; **currently empty** on the Mac, so nothing to transfer. The `deck` skill is tracked but its working dir/PPTX are not.
- **`.claude/settings.local.json`** — gitignored permission allowlist (no secrets). Spark builds its own as it approves commands. Key approved commands for reference: `git *`, `git push origin main`, `gh run *`, `python3 .claude/skills/sync-field-notes/scripts/*.py`, and the sync-script import-checks.
- **Supabase edge functions** (`supabase/functions/waitlist-signup`, `confirm-email`) — in the repo but **not driven by any skill**; they deploy separately via the Supabase CLI/project and are not part of the website build.

---

## 5. In git vs deliberately not

| Tracked (Spark inherits on clone) | Not tracked (and why) |
|---|---|
| All 11 skills under `.claude/skills/` | `.claude/settings.local.json` — machine-local allowlist |
| `scripts/` (verifiers, OG, slashless, generators) | `/deck/` — local/empty |
| `sync-field-notes` Python scripts + `references/` | `.claude/skills/skill-creator/` — stock plugin; Spark has its own |
| `.claude/settings.json` (deploy-status hook) | `__pycache__/`, `output/`, `.agents/`, `.playwright-mcp/`, `dist/`, `.astro/` — regenerated |
| Content, contracts, `.github/workflows/deploy.yml`, `public/CNAME` | `*/references/manifest-cache.md` — per-run cache |

**No `.gitignore` changes are needed for this transition.** The original worry about gitignored custom skills doesn't apply — they're all tracked.

---

## 6. Cutover runbook

**On the Mac (now — the final push):**
1. `git add HANDOFF.md MAC-TO-SPARK-TRANSITION.md`
2. `git commit` (conventional message recording the cutover).
3. `git push origin main` — this is the handoff; the doc is now readable from the remote.

**On Spark (taking over):**
1. `git clone git@github.com-manavsehgal:manavsehgal/ainative-business.github.io.git`
2. `npm ci`
3. `export AI_FIELD_NOTES_SRC=<path to Spark's local ai-field-notes>` (ensure its last tranche is committed+pushed).
4. Run `/sync-field-notes` to pull the pending content into the website.
5. `npm run build` — both verifiers must pass.
6. `git commit` + `git push origin main` — GitHub Pages auto-deploys.

From step 6 onward Spark owns the repo. The Mac folder can be archived. Product-derived skills (§3) remain Mac-side until the later simplification.

---

## 7. Where the operating knowledge lives

- **`HANDOFF.md`** (repo root) — the live backlog and per-session decision log. **This is the carry-forward state** (see §8). There is no `CLAUDE.md`/`README.md` at root; `HANDOFF.md` + this doc are the onboarding.
- **`.claude/skills/<name>/SKILL.md`** — the authoritative procedure for each skill (esp. `sync-field-notes/SKILL.md`).
- **`ainative-stats.md`, `seo-progress.md`** (repo root) — latest stats / SEO snapshots (Mac-generated; product-side, see §3).
- **Source repo (`ai-field-notes`):** `NARRATIVE-CONTRACT.md`, `mirrors/destination-overrides.md`, `SYNC-WORKFLOW.md` (last is historical).

---

## 8. Open items inherited at cutover

`HANDOFF.md` carries the active backlog. At cutover it splits by owner:

**Spark owns (destination / field-notes):**
- LoRA detail-page "How to use" snippet fix (`src/pages/artifacts/loras/[slug]/index.astro` ~167–179) — honor `how_to_load`, fall back to direct `AutoModelForCausalLM` load, not PEFT.
- Browser-verify new LoRA/Adapter/Dataset/Quant detail pages (live preview, contrast).
- Bakeoff article catalog-footer drift (one article ↔ four manifests; last-write-wins) — multi-binding footer support.
- Step-4 config-file diffs still drifting (`package.json`, `astro.config.mjs`, `tsconfig.json`, `src/styles/global.css`, `src/data/seo.ts`, some `src/components/sections/fieldkit/*.astro`) — targeted per-file review on next sync.

**Stays Mac-side (product-derived, until §3 simplification):**
- Patent-strategist `siblings[]` cross-links and `lane_summary` copy (source authoring).
- Older quant manifests' positioning narrative backfill.
- `seo-monitor` rerun (needs Chrome + Google session).
