<!--
  Session handoff for ainative-business.github.io (Spark-operated monorepo).
  Convention:
  - Replace "Open items" each session; do NOT append.
  - "Recent decisions" is a short running log — keep ~2 latest, prune older.
  - Full history of any pruned entry is recoverable via `git log -p HANDOFF.md`.
  - Last pruned/reset: 2026-05-31.
-->

# HANDOFF — ainative-business.github.io

## Current state

- **This repo is the single Spark-owned monorepo** at `/home/nvidia/ainative-business.github.io` — build workspace *and* website. The old two-repo `ai-field-notes`→Mac sync model is **retired**; author directly here (do NOT use `sync-field-notes`).
- **Live** at `ainative.business` (GitHub Pages). Tip of `origin/main` = `58363b0`; **everything is pushed**, tree clean except two pre-existing untracked items (`.claude/scheduled_tasks.lock`, `src/data/arena-mirror/` — leave alone).
- **Build/verify loop:** `node node_modules/astro/astro.js build` (485 pages; `npm run build` is broken on this checkout per `reference_astro_build_smb_symlink_break`) → `node scripts/verify_artifact_rendering.mjs` (18 pages/7 kinds) + `node scripts/verify_field_notes_rendering.mjs` (404/62). `build:og` is **CI-only** (needs Chrome); CI regenerates OG on push.
- **arena-app/ + fieldkit/ build separately** from the marketing site — pushing arena/fieldkit changes does NOT change the public `dist/`. After any `arena-app/` edit, rebuild the served bundle: `fieldkit arena build --repo-root arena-app` (bakes `_webui`, gitignored).
- **Secrets:** `.env.local` (gitignored, chmod 600) holds `PYPI_TOKEN`, `HF_TOKEN`, `OPENROUTER_API_KEY` — `fieldkit-curator` + `hf-publisher` auth here.

**Recently shipped (all live):** patent-strategist `lane_summary`+`siblings` (`9df9438`); positioning+`known_drift` backfill on the 4 older vertical quants (`ddfa492`); per-product OG card for `/products/` (`0cb175d`); Arena marketing refresh — demo bundle + launch article + landing (`0bf2ec7`); Orionfold LLC brand pass + go-live (deploy `26664480875`). Arena cockpit/leaderboard/telemetry work is committed on `origin/main` (arena-app only).

## ⚙️ Live runtime (throwaway — kill when done)

- **Arena cockpit** `fieldkit arena up` from venv `/tmp/arena-venv` → http://127.0.0.1:7866/arena/ (loopback; bind `0.0.0.0` for LAN). Log `/tmp/arena-cockpit.log`, db `~/.fieldkit/arena.db`, OpenRouter key sourced from `.env.local` (re-source if restarted). Recycle with `.claude/skills/arena-lifecycle/scripts/arena_lifecycle.sh restart [--browser]`. Left up per operator request — do NOT relaunch unless dead. Find: `pgrep -af 'fieldkit arena up'`.
- **Static dist server + visible Chromium** (stood up 2026-05-31 to show the operator the quant pages): `python3 -m http.server 8099 --bind 127.0.0.1` (cwd `dist/`) + Chromium on `DISPLAY=:1` CDP **:9222**, profile `/tmp/arena-chrome-profile`, parked on `http://127.0.0.1:8099/artifacts/quants/`. Drive via `node` + **`puppeteer-core`** (NOT playwright-core — not installed), `puppeteer.connect({browserURL:'http://127.0.0.1:9222', defaultViewport:null})`, **run the .mjs from repo root** (ESM won't resolve under `/tmp`); screenshots → `/tmp/aifn-smoke/`. Kill: `pkill -f 'http.server 8099'` / `pkill -f remote-debugging-port=9222`. Recipe: memory `reference_visible_browser_cdp_attach`. If the Spark rebooted, both are gone.

## Open items

### Operator actions (you own these)
- **Archive `ai-field-notes` read-only** — `gh repo archive manavsehgal/ai-field-notes`. Monorepo consolidation is committed (`2299d22`); local copy already renamed to `/home/nvidia/archive-ai-field-notes` (kept, not deleted). Archiving preserves git history + the 92M research-evidence layer deliberately not migrated.
- **Merge Mac PR #11** — [ai-field-notes#11](https://github.com/manavsehgal/ai-field-notes/pull/11) still open (will be moot once the repo is archived).
- **PSI authenticated key** still missing (blocks PageSpeed in `/seo-monitor`).

### Destination work
- **#7 remainder — human-eye browser pass on the LoRA/adapter/dataset detail pages.** The 4 quant pages were browser-verified 2026-05-31 (0 console errors); the LoRA (`/artifacts/loras/patent-strategist-v3-nemo/`), adapter, and dataset detail + empty-state listing pages have only HTML-level verifier coverage, no human-eye/Lighthouse pass yet.
- **#11 — bakeoff article's gated catalog footer last-write-wins.** `chrome_footers.collect_gated_articles()` keys by article-slug, so when multiple manifests bind one article the alphabetically-last wins (currently points at the surviving NeMo lane). Low priority; fix when the next multi-binding case lands.
- **#18 — patent-strategist W3 fine-tune** (source-side, ETA ~2 weeks). Likely ships more `kind: lora` manifests; the render path + notebooks-as-artifacts scaffold are ready (new manifests can carry `notebooks:{colab,kaggle}` with no code change). NB future quant *republishes* get `positioning`+`known_drift` only — NOT `stack_origin`/`lane_summary`/`siblings` (those are for Orionfold fine-tunes; see 2026-05-31 decision).

### SEO watch
- **Re-run `/seo-monitor`** (~1–2 weeks out). Confirm live `sitemap-0.xml` settled at ~182 URLs (no `/field-notes/tags/` or `/stages/`); GSC *Discovered–not-indexed* (355, **stale — those URLs are already indexed** per the 2026-05-30 inspection) should bleed down as the Validate-Fix completes. GSC "unused verification token" `fePoYwMX…` is **HOLD / do-not-remove** (Workspace-owned TXT; removing risks email). Journal: `seo-progress.md`.

### Cleanup (non-blocking, tied to the retired two-repo model)
- Deprecate/remove the now-obsolete `sync-field-notes` skill; archive the dead-sync docs `MAC-TO-SPARK-TRANSITION.md` / `SYNC-WORKFLOW.md` / `mirrors/`. The old carry-forward items about source-side `/sync-field-notes` diffs (package.json/astro.config/etc.), SYNC-HANDOFF cleanup, and wire-back PRs are **moot** under the monorepo model — drop on sight.
- Optional: relocate the CC memory namespace symlink (`-home-nvidia-ai-field-notes`, 93 files) into this namespace for a fully clean cutover (safe as-is — points into `~/.claude/projects`, not the repo).

## Recent decisions (short running log — prune older)

### 2026-05-31 (Catalog narrative pass: patent-strategist lanes + 4 older-quant positioning + browser-verify)
- Closed catalog carry-forwards #8/#9 (`9df9438`), #10 (`ddfa492`), #7-for-the-quant-pages (`2b8d531`); HANDOFF/runtime note (`58363b0`). Deploy `26739446188` succeeded + verified live.
- **Scope correction for future quant publishes:** v0.5.x `stack_origin`/`lane_summary`/`siblings` are for **Orionfold fine-tunes**, NOT third-party quant republishes. The 4 vertical quants (finance/medical/legal/cyber) got `positioning`+`known_drift` only — adding lane/family fields would render an empty/misleading "Choosing this lane."
- **Honest-positioning on weak scores** (finance FinanceBench 14–18%, cyber CyberMetric 34–40% vs 25% random): credit the upstream trainer, frame Orionfold as the distribution+measurement layer, state ceilings plainly. The `verify_artifact_rendering` `drift-bounded` rule needs a numeric/comparison anchor per bound (used "inherited from" / "%" / "n=50" / counts).
- Patent-strategist family is **2 lanes, not 4** (Unsloth siblings deleted 2026-05-24). Lane copy uses the bakeoff's measured axes — 26% = *training wall-time*, 44% longer chains, ~0.9 lower perplexity — NOT a head-to-head bench score (the article declines that for lack of a rubric).
- Quant detail pages do NOT surface `positioning.headline` (by design — it shows on the listing card); detail leads with "What this model does" (problem/use_cases/audience) + "Known drift".

### 2026-05-29 (🚀 Go-live: Orionfold LLC launch deployed to ainative.business)
- Merged `spark-cutover-2026-05-29` `--ff-only` to `main` + pushed → Pages deploy `26664480875` (live URLs 200). Site launches as **Orionfold LLC**: employer disclaimer scrubbed from all 6 surfaces → Orionfold blurb; `/about/` redone as an Orionfold studio page; footer "© 2026 Orionfold LLC"; GitHub+theme moved to footer; JSON-LD org→Orionfold. Rollback tag `pre-spark-cutover` on the remote.
- **Upstream-parity carry-forward (now moot — ai-field-notes being archived):** the demo bundle's sponsor link + the `/arena/arena/chat/` double-base fix were applied to the *built* bundle in-repo; would have needed mirroring into the ai-field-notes arena source. Monorepo consolidation makes this self-contained here now.
