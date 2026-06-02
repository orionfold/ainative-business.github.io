<!--
  Session handoff for ainative-business.github.io (Spark-operated monorepo).
  Convention:
  - Replace "Open items" each session; do NOT append.
  - "Recent decisions" is a short running log — keep ~2 latest, prune older.
  - Full history of any pruned entry is recoverable via `git log -p HANDOFF.md`.
  - Last pruned/reset: 2026-06-01.
-->

# HANDOFF — ainative-business.github.io

## Current state

- **This repo is the single Spark-owned monorepo** at `/home/nvidia/ainative-business.github.io` — build workspace *and* website. The old two-repo `ai-field-notes`→Mac sync model is **retired**; author directly here (do NOT use `sync-field-notes`).
- **Live** at `ainative.business` (GitHub Pages). `origin/main` tip = `bca63e7`; **tree clean, 0 ahead / 0 behind — all pushed.** `WORKFLOWS.md` + `HANDOFF.md` are both **now tracked** (WORKFLOWS un-ignored in `adb1c04`; the older "operator-local gitignored" framing is superseded — they're canonical tracked docs). Two pre-existing untracked items remain (`.claude/scheduled_tasks.lock`, `src/data/arena-mirror/` — leave alone).
- **Build/verify loop:** `node node_modules/astro/astro.js build` (485 pages; `npm run build` is broken on this checkout per `reference_astro_build_smb_symlink_break`) → `node scripts/verify_artifact_rendering.mjs` (18 pages/7 kinds) + `node scripts/verify_field_notes_rendering.mjs` (404/62). `build:og` is **CI-only** (needs Chrome); CI regenerates OG on push.
- **arena-app/ + fieldkit/ build separately** from the marketing site — pushing arena/fieldkit changes does NOT change the public `dist/`. After any `arena-app/` edit, rebuild the served bundle: `fieldkit arena build --repo-root arena-app` (bakes `_webui`, gitignored).
- **Secrets:** `.env.local` (gitignored, chmod 600) holds `PYPI_TOKEN`, `HF_TOKEN`, `OPENROUTER_API_KEY` — `fieldkit-curator` + `hf-publisher` auth here.

**Recently shipped (all live):** **MTBM-arc opener `the-meta-program-on-spark` (`bca63e7`, pushed)** — thesis-spine deep-dive (pane→hands→engine + Ch-14 meta-program; `book_chapters:[10,11,14]`; new signature `MetaProgramRecursion`; inline fn-diagram; 8 explainers); closes the editorial-overlay "Now (not gated)" item below; patent-strategist `lane_summary`+`siblings` (`9df9438`); positioning+`known_drift` backfill on the 4 older vertical quants (`ddfa492`); per-product OG card for `/products/` (`0cb175d`); Arena marketing refresh — demo bundle + launch article + landing (`0bf2ec7`); Orionfold LLC brand pass + go-live (deploy `26664480875`). Arena cockpit/leaderboard/telemetry work is committed on `origin/main` (arena-app only).

## ⚙️ Live runtime

- **Arena cockpit is DOWN** (was left up per a prior session; torn down since — no process, `:7866` dead as of 2026-06-02). To bring it back: `.claude/skills/arena-lifecycle/scripts/arena_lifecycle.sh restart [--browser]` (venv `/tmp/arena-venv`, serves http://127.0.0.1:7866/arena/, log `/tmp/arena-cockpit.log`, db `~/.fieldkit/arena.db`, OpenRouter key from `.env.local`). Find: `pgrep -af 'fieldkit arena up'`.
- Nothing running. (The 2026-05-31 throwaway dist server `:8099` + visible Chromium CDP `:9222` used to show the quant pages have been torn down.) To bring a visible browser back for browser-use, see memory `reference_visible_browser_cdp_attach` or `arena_lifecycle.sh restart --browser`.

## Open items

### Operator actions (you own these)
- ✅ **`ai-field-notes` archived read-only** (2026-06-02). Git history + the 92M research-evidence layer preserved; local copy kept at `/home/nvidia/archive-ai-field-notes`. Mac PR #11 is now moot (repo is read-only).
- **PSI authenticated key** still missing (blocks PageSpeed in `/seo-monitor`).

### Destination work
- **#7 remainder — human-eye browser pass on the LoRA/adapter/dataset detail pages.** The 4 quant pages were browser-verified 2026-05-31 (0 console errors); the LoRA (`/artifacts/loras/patent-strategist-v3-nemo/`), adapter, and dataset detail + empty-state listing pages have only HTML-level verifier coverage, no human-eye/Lighthouse pass yet.
- **#11 — bakeoff article's gated catalog footer last-write-wins.** `chrome_footers.collect_gated_articles()` keys by article-slug, so when multiple manifests bind one article the alphabetically-last wins (currently points at the surviving NeMo lane). Low priority; fix when the next multi-binding case lands.
- **#18 — patent-strategist W3 fine-tune** (source-side, ETA ~2 weeks). Likely ships more `kind: lora` manifests; the render path + notebooks-as-artifacts scaffold are ready (new manifests can carry `notebooks:{colab,kaggle}` with no code change). NB future quant *republishes* get `positioning`+`known_drift` only — NOT `stack_origin`/`lane_summary`/`siblings` (those are for Orionfold fine-tunes; see 2026-05-31 decision).

### Editorial overlay — WORKFLOWS journey → article series (sequenced at roadmap extraction points)
The book is **published** (Amazon / Leanpub / Orionfold) — do **NOT** edit `src/data/book/chapters/**`. Overlay the "machine that builds machines" journey as **articles** instead, threading the published chapters via the `book_chapters: [10, 11, 14]` frontmatter cross-link (editorial reference, **not** a series retag, **not** a book edit — H4 precedent). It's a **hybrid of two genres** stitched by existing machinery: deep-dives via `tech-writer` (the **MTBM arc** A1–A9 + the **Harnesses series** H1–H6 already exist), launches via `product-writer` (`products/**`, `series: Cockpit`, build-metrics + feature tour). Extraction points, mapped to `WORKFLOWS.md` §3 phases:
- ✅ **DONE 2026-06-02 — thesis-spine deep-dive SHIPPED** as `the-meta-program-on-spark` (`bca63e7`, pushed, published in full): the `pane → hands → engine` arc + the Ch-14 *meta-program-as-operator-instance* framing, `book_chapters:[10,11,14]`, signature `MetaProgramRecursion`, inline fn-diagram, 8 explainers. This was the book-overlay opener; the gated Phase-1/2/3 items below remain.
- **Phase 1 ship — Arena control plane** → `product-writer` launch (`products/`, `series: Cockpit`): M8 build-metrics + feature tour (jobs view · dispatch · regression→re-eval). Cross-links the H4 deep-dive. **Gated on M8 shipping** (needs runnable surface + mined metrics).
- **Phase 2 ship — autonomous harness** → the Harnesses deep-dives **already exist and are published** (H3 `hardening-the-hermes-harness-on-spark`, H4 `hermes-drives-the-spark-via-fieldkit-mcp` — the MCP write-surface concept); so the new piece is a `product-writer` launch for the **built** cockpit surface (morning-standup · cron queue · budget-governor) that **cross-links the existing H4**. Gated on Phase 2 shipping.
- **Phase 3 ship — closed-loop RLVR** → `tech-writer` MTBM installment (new A-slug; the arc already scopes "RL on agent trajectories — GRPO…") + Looking-Beyond-Spark extrapolation, **plus** the first §5 "living-model" `product-writer` launch (the `fieldkit.lineage` delta chart as hero). Gated on Phase 3.
- **Mechanism to stake now:** both skills support `status: upcoming` placeholders — drop one per extraction point to claim the slug + commitment, promote to `published` as each phase lands. Each product launch's build-metrics block is the per-phase proof of Ch-14's configuration-over-code economics; collected across the series they're a running ledger of the machine compounding.

### Roadmap & specs — harvest the existing corpus (grounding, not discovery)
Before further refining `WORKFLOWS.md` §3 or writing the named spec stubs (`rlvr-loop-v1`, `autonomous-harness-v1`, Arena M8), harvest the article corpus — but it's a **scoped, output-producing harvest, not a brute-force read** (62 articles; ~30 are RAG-foundation / quant-card / one-offs that don't bear on this roadmap).
- **The grounding is already written (verified published 2026-06-02):** `autonomous-harness-v1` ← `hardening-the-hermes-harness-on-spark` (H3) + `hermes-drives-the-spark-via-fieldkit-mcp` (H4, MCP write surface); `rlvr-loop-v1` ← `clawgym-on-spark-grpo`, `t2po-uncertainty-guided-rl-on-spark`, `test-time-distilling-for-exploration`, `distill-architect-lora-from-trajectories`, `trajectory-eval-is-the-agent-flailing`, `autoresearch-agent-loop`. The specs can cite real Spark-measured work instead of re-deriving.
- **Scope:** the ~32 roadmap-relevant articles (MTBM `A*` + Harnesses `H*` + GRPO/RL/agent/eval). Only **6 carry `evidence/` trees** — read those in full (the real code material); mine the rest's prose via the **Second Brain MCP** (`mcp__second-brain__{ask_blog,search_blog}` — **verify index freshness first**, it may lag recent commits; dogfoods the Second Brain arc) rather than reading every piece.
- **Two outputs:** (1) a **§3 reconciliation note** — where measured reality (e.g. `clawgym-grpo`/`t2po` real GRPO numbers; whether `hermes-drives` validates the Phase-1 "dispatch through the MCP harness" call) confirms / sharpens / complicates §3's abstract claims; (2) a **per-spec evidence index** (article + `evidence/` file → spec section), done **JIT when writing each spec** so it's targeted to that spec's open questions, not harvested cold.
- **Execution:** the canonical **Phase-0 `Workflow` fan-out** (one agent per relevant article → extract roadmap claims + spec-feedable evidence → synthesize) — i.e. refine the roadmap *using* its own first bet. Opt-in (needs the "workflow" keyword) before running at that scale.

### SEO watch
- **Re-run `/seo-monitor`** (~1–2 weeks out). Confirm live `sitemap-0.xml` settled at ~182 URLs (no `/field-notes/tags/` or `/stages/`); GSC *Discovered–not-indexed* (355, **stale — those URLs are already indexed** per the 2026-05-30 inspection) should bleed down as the Validate-Fix completes. GSC "unused verification token" `fePoYwMX…` is **HOLD / do-not-remove** (Workspace-owned TXT; removing risks email). Journal: `seo-progress.md`.

### Skill-path drift (publish-workflow bug — fix before relying on the stats/README refresh)
- **`nvidia-learn-stats/scripts/compute_stats.py` and `tech-writer/scripts/refresh_readme.py` write pre-cutover paths the monorepo doesn't use.** Discovered 2026-06-02 publishing `the-meta-program-on-spark`: `compute_stats.py` writes `src/data/project-stats.json` but the site reads **`src/data/field-notes/project-stats.json`** (tracked); `refresh_readme.py` writes a root `README.md` that the monorepo doesn't track. Both ran as **no-ops/strays** (the stray outputs were `rm`'d, not committed). Impact: the home "At a glance" non-derived KPIs (words/LOC/models) silently don't refresh on publish — article *count* is fine (derived from the collection at build, per the `ProjectStats.astro:34` comment). **Fix:** repoint both scripts' output to the `src/data/field-notes/` + (decide whether the monorepo wants a tracked root README at all). Memory `feedback_refresh_stats_on_publish` is now path-stale too.

### Cleanup (non-blocking, tied to the retired two-repo model)
- **Dead-sync docs deleted 2026-06-02** (`MAC-TO-SPARK-TRANSITION.md`, `SYNC-WORKFLOW.md`, `mirrors/`, `handoff/`) as part of the `_GUIDES/`+`_SPECS/` consolidation — see the 2026-06-02 decision below.
- All dead `mirrors/destination-overrides.md` references cleared 2026-06-02 (in `_SPECS/spark-arena-v1.md`, `src/content/artifacts/README.md`, `chrome_footers.py`, `site-rendering-rubric.md` — reframed to monorepo reality). Still open: deprecate/remove the now-obsolete `sync-field-notes` skill itself (a separate decision — the skill body is retired but not deleted).
- Optional: relocate the CC memory namespace symlink (`-home-nvidia-ai-field-notes`, 93 files) into this namespace for a fully clean cutover (safe as-is — points into `~/.claude/projects`, not the repo).

## Recent decisions (short running log — prune older)

### 2026-06-02 (Doc consolidation — `_GUIDES/` + `_SPECS/`, dead folders removed)
- **Active guidance → `_GUIDES/`** (with `INDEX.md`): `NARRATIVE-CONTRACT.md`, `PRODUCT-ARTICLES.md` (names kept — code/test identifiers), plus renames `arena-distribution.md` ← `APP-SYNC.md`, `arena-storefront-marketing.md` ← `APP-MARKETING.md`, `local-ai-stack-commands.md` ← `COMMANDS.md`. Each carries a `Last updated` header. `WORKFLOWS.md` + `HANDOFF.md` stay root-tier living docs; `ainative-stats.md` + `seo-progress.md` stay root (skill-generated).
- **All specs/plans/designs → `_SPECS/`** (with `INDEX.md`): the 4 active specs at root (`specs/` → `_SPECS/`, basenames unchanged), superseded/historical under `_SPECS/archive/` (model-playground design, patent-strategist-v4-nemo, the 12 `docs/superpowers/` pivot-era docs). **Every live `specs/` reference rewired** — skills (incl. the `claude-corpus-synth` hard path-check), `src/content.config.ts`, `arena-app` config, `fieldkit/src/**` + `fieldkit/docs/api/`. Per the approved decision, **CHANGELOG, `evidence/*.json`, and the archived-repo article permalink were left untouched** (immutable history).
- **Deleted:** `handoff/` (April stagent→ainative migration + unreferenced logos), `mirrors/`, `MAC-TO-SPARK-TRANSITION.md`, `SYNC-WORKFLOW.md`. Git preserves history. `WORKFLOWS.md` cross-refs + §2G contracts table + §7 drift note updated; build verified green.

### 2026-06-02 (WORKFLOWS roadmap resequenced + Ch-14 fold-in + article-overlay strategy)
- **§3 roadmap resequenced** from a flat four-bet list into a `pane → hands → engine` phasing: **Phase 0** Bet 4 (Workflow fan-out, free/now) → **Phase 1** Bet 3 (Arena control plane M8, *the* lever) → **Phase 2** Bet 2 (autonomy: hooks + cron + morning-standup + budget-governor + freshness-monitor) → **Phase 3** Bet 1 (closed-loop RLVR). Rationale: each phase makes the next more valuable, and autonomy is useless without a control plane to approve/dispatch from on a no-auto-push, single-lane box.
- **Build-state ground-truth (Explore agent) corrected 3 stale claims** now fixed in §3/§4/§7: the **MCP harness is already built** (`fieldkit/harness/mcp.py` `build_mcp_server()` ships 7 tools — *not* stubbed), the **Arena store has a job socket** (`eval_runs.arq_job_id`), and **all 7 `fieldkit.eval` verifiers exist**. Genuinely absent: dispatcher glue, cron, hook *expansion* (one `SessionStart` hook), the RLVR stack (`fieldkit.reward`/`rl`/`g6_*`). **Decision:** Phase 1 dispatcher executes **through the MCP harness** (single surface shared w/ Hermes), growing harness coverage (`measure_variants`/`run_vertical_eval`) by demand.
- **§1 mission frame folds in Ch-14** (`ch-14-the-meta-program.md`) as the sharpest recursion (*the tool you build with is itself an instance of the thing you build*; "the specification IS the application; configuration over code"), framed as same-pattern/another-instance (Ch-14 is about the sibling `ainative` platform, this is the Spark monorepo). §5 reframed to sequence speculative items vs the phases (eval-as-a-service → Arena M9; living-model → Phase-3 product). All edits in operator-local gitignored `WORKFLOWS.md` (no commit/build).
- **Article-overlay strategy set** (book published → don't edit chapters; overlay via articles — see the *Editorial overlay* open-item above for the per-phase genre/extraction-point sequencing).
- **Stale-memory fix still queued:** memory `project_uber_corpus_decision_doc` points at `ideas/uber-local-corpus-gen-decision.md` which **does not exist** (only `ideas/ai-field-notes-consolidation.md` present) — correct next pass.

<!-- 2026-06-01 WORKFLOWS.md-authoring entry pruned per "keep ~2 latest" (its roadmap + key-insight content is superseded by the 2026-06-02 resequence above; Ch-14 noted there is now folded in); recover via `git log -p HANDOFF.md`. -->

<!-- 2026-05-31 catalog-narrative entry (patent-strategist lanes + 4 older-quant positioning) pruned per "keep ~2 latest"; recover via `git log -p HANDOFF.md`. -->
<!-- 2026-05-29 Orionfold LLC go-live entry pruned per "keep ~2 latest"; recover via `git log -p HANDOFF.md`. -->
