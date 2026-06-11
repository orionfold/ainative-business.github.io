<!--
  Session handoff for ainative-business.github.io (Spark-operated monorepo).
  Convention:
  - Keep this file short: current state, live runtime, build/verify, open items, and ~2 recent decisions.
  - Do NOT append completed history. Prune closed tasks aggressively; full history is recoverable via `git log -p HANDOFF.md`.
  - Last pruned/reset: 2026-06-10 (public-launch session compacted the Advisor proof narrative into the launch summary; receipt-by-receipt history is in git).
-->

# HANDOFF — ainative-business.github.io

> 📌 **PINNED — Arena build discipline.** Any `arena-app/` or `fieldkit.arena` work that changes the cockpit must be built and browser-smoked side by side in the running Arena over CDP: bring the cockpit up in browser-use mode (`arena_lifecycle.sh up --browser` -> `:7866` + CDP Chromium `:9222`), rebake `_webui` after `arena-app/` edits (`fieldkit arena build --repo-root arena-app`), then drive the live panes and confirm the change renders. Live `rl_run` validation stays operator-armed; offline tests + live render/transport smoke are the normal session bar.

> 📌 **PINNED — Arena pipeline discipline.** For Advisor/Arena/fieldkit pipeline work, the visible Arena cockpit is the operating surface and system of record. Use browser-use mode first for lane launch/teardown, active-lane selection, chat/compare/eval observation, jobs, run-context, and screenshots. Do **not** replace Arena operation with headless browser scripts, hidden endpoint batch scoring, or terminal-only API calls. If a needed step is not possible in Arena, perform only the minimum deterministic terminal action and log it as an `AD-AE-*` or `AD-FK-*` dogfood finding.

## Current State

### 2026-06-11 — Arena hardening batch: 3 of 4 queued actions + mirror-default fix shipped (this session)

- **Item 1 — catalog drift guard SHIPPED**: new `scripts/verify_arena_catalog_sync.mjs` (every `src/content/artifacts/*.yaml` must byte-match its `arena-app/` copy; orphans + missing both fail; exit = drift count) — runs beside the render verifiers, added to the CLAUDE.md verify chain; currently 22/22 in sync. `hf-publisher` SKILL.md Step 7 post-push tail now leads with "sync manifest → arena-app + rebake + mirror + run the verifier".
- **Item 2 — stale-HTML trap killed at the source**: `fieldkit.arena.server` `_webui` mount now serves HTML with `Cache-Control: no-cache` (new `_webui_static_files()` StaticFiles subclass; ETag keeps revalidation a cheap 304; hashed `/assets/*` untouched). Wire-verified live post-restart: HTML carries `no-cache`+etag, JS asset carries no cache-control. The CDP `Network.setCacheDisabled` workaround is no longer needed for post-bake verification.
- **Item 3 — frontier head-tag honest**: leaderboard SSR now applies the island's quality filter (`ppl != null || evalScore != null`) to `frontierPoints` and counts models from surviving groups. CDP-verified live: head tag reads **6 models · 25 builds** (was 7·30). NOTE: the queue entry projected 26 — miscount; `spark-hermes-profile` has **5** quality-less tok/s lanes, not 4 (verified by script over the manifests; nothing else dropped).
- **Mirror-default hardened** (the recurring `src/data/arena-mirror/` leftover): `import_artifacts(write_mirror=)` defaults **False**; CLI flag is now opt-in `--mirror` (`--no-mirror` kept as the off form). New test pins the default; `fieldkit/docs/api/arena.md` kwarg table updated; CHANGELOG [Unreleased] carries both behavior changes under `### Changed`.
- Arena suite **495 passed** (+2 new tests); `_webui` rebaked + sidecar restarted via lifecycle script; demo rebuilt/deployed/verified (691 links ok, head tag honest in the demo bundle too).
- **Item 4 — Kepler tok/s DONE (operator-armed lane swap, same session)**: operator tore down the `:8091` Advisor lane in LaneTruth; measured all 4 variants with the p65 precedent (`llama-bench -ngl 99 -p 64 -n 64 -r 2`, tg average): **Q4_K_M 33.06 · Q5_K_M 28.06 · Q6_K 24.6 · Q8_0 21.07 tok/s** (monotonic, no Q8 anomaly — consistent with kepler being a chat-tune). Raw receipts at `/home/nvidia/data/quants/Kepler/tok-bench-2026-06-11/`. Manifest + arena-app sync (drift guard 22/22) + rebake; CDP-verified frontier chart now **7 models · 29 builds** with kepler in the legend (verified with a PLAIN reload — the no-cache fix works). Advisor lane relaunched **through the guarded LaneTruth UI** (recipe `nemotron3-nano-4b-sft-v02-q8`, anchor-on-warm, ACTIVE in 6 s), wire-verified serving the v0.2 GGUF.
- **Frontier chart flagship treatment (operator-directed, same session)**: `advisor-gguf` now renders as a violet diamond (`--violet`, drawn above the Pareto line via a uPlot draw hook) with a matching legend swatch; flagship excluded from the color cycle + 6th cycle color (`--red`) added → finance-chat/advisor collision gone and all 6 non-flagship models collision-free. Bonus fix: sweet-spot rings had a background-filled interior that occluded the dot they highlight — now transparent. CDP-verified + demo redeployed (`f8c5aa6`).
- **Leaderboard advisor display layer (operator-directed, same session)**: the `advisor_contract` group now renders FIRST in the bench section (above even the AF-28 live island) with a friendly head ("Orionfold Advisor — refusal-floor contract", metric "frozen OOD curveballs") and translated lane names + pills (◆ flagship / promoted lane / superseded / baseline / teacher + per-row "frozen OOD · curveball v0.x" gate pills) — raw receipt lane ids stay visible as the mono sub-line (report=reality). Mechanics: new `advisorBenchDisplay`/`advisorLaneDisplay` in `leaderboard-format.mjs` (matcher also covers a future live `cockpit:advisor_contract` tier), group table extracted to `BenchGroupTable.astro` so the flagship renders above the island without markup duplication, pill + flagship-accent CSS in ArenaAppLayout.
- **Marketing screenshots refreshed for the changed surfaces (operator-directed, same session)**: retook `products/orionfold-arena/screenshots/{02-leaderboard,03-efficiency-frontier,04-models}.png` against the live cockpit (fresh emulated tab, 1920×924 @2x, no scrollbar — emulation renders none; 02 reframed to the advisor-first bench section, sticky-chrome offset measured in-page at 217 px). Public copies synced (37 in sync per demo verifier); the arena landing (`src/pages/arena/index.astro`) picks 03 up by filename. `product.md` alt + caption + body prose updated for 02/03 to describe the flagship display layer (pills, friendly names, raw ids kept) and the violet diamond. **Screenshot-text audit PASS**: all 21 product shots (14 arena + 7 advisor) carry ≥75-char alts + italic captions. Shots 01/05–11 (cockpit home, detail, chat, compare, palette, lab, telemetry) intentionally NOT retaken — their surfaces didn't change this session, though 01-cockpit shows pre-Path-A counts (see queued audit below).
- **AD-FK-1 (NEW dogfood finding, from the relaunch)**: the AE-R13 one-lane guard counts the Cortex **embedder** (`nim-embed-nemotron`, `:8001`, OpenAICompat) as a resident lane — `refused:lane_resident` on every chat-lane launch while the grounded-chat stack is up, and `teardown_first` is NOT a safe out (it tears down **every** discovered lane; pointing `teardown_lane()` at a docker-published port is untested). Past launches only worked because the embedder happened to be down. Workaround this session: operator `docker stop nim-embed-nemotron` → guarded launch → `docker start` (back at 200). Real fix queued in Open Items.

### 2026-06-11 — Advisor on the leaderboard (Path A executed) + Advisor-bench manifest shipped

- **Path A runbook executed end-to-end** (was QUEUED operator-approved): new deterministic rollup `scripts/orionfold_advisor/leaderboard_rollup.py` (transform-only; reads the 6 curveball results.jsonl receipts, refusal basis = strict-passed among refuse rows to match the published `curveball2-compare` "3/9"; bench shas self-verified against the frozen pins `122bcd619e9d`/`4b6cac85e41f`; tok/s read from the canonical manifest, not hardcoded) → `articles/the-refusal-floor-is-trainable/evidence/advisor_contract_results.json` (6 lane×gate rows, gates never conflated: 4b-sft-v0.2 0.90/0.857, 4b-sft-v0.1 0.70, 4b-init 0.55, 30b-prompted 0.575/0.381).
- **Import chain run**: `fieldkit arena import` (idempotent, re-run verified) → `rebuild-leaderboard` (bench rows 12→18) → `mirror --repo-root arena-app`. **CDP-verified live** (cache disabled): bench group `the-refusal-floor-is-trainable:advisor_contract` renders 6 lanes, trained-4B ranked above the 30B teacher (85.7% vs 38.1%), 42 tok/s only on the promoted lane.
- **`advisor-bench-v0.1.yaml` manifest shipped** (closes the launch follow-up): full bench fields mirrored from the live HF card (5 shapes incl. corpus-manifest 182, sha12 pins, results = promoted lane under mode `retrieval`, real sample rows, positioning, sibling ↔ `advisor-gguf` reciprocal links). Copied byte-identical into `arena-app/src/content/artifacts/` (dual-copy discipline) — cockpit models page benches 3, detail page renders; main site 538 pages (+1) + both render verifiers green; demo rebaked/deployed/links verified.
- **Root cause of the recurring `src/data/arena-mirror/` leftover found**: `fieldkit arena import` writes the repo-root mirror BY DEFAULT (`importer.DEFAULT_MIRROR_LEADERBOARD_PATH`); nothing on the main site reads it. Deleted again; use `fieldkit arena import --no-mirror`, or fold "stop writing the root mirror by default" into the hardening batch.
- Path B (live tier `cockpit:advisor_contract` via eval runs against `:8091`) stays open as the narrated-session story.

### 2026-06-11 — Arena artifact-catalog drift cleared: Advisor/Kepler/Cortex on every cockpit surface

- **Root cause found via operator question** ("why is the advisor model not on the cost-quality chart?"): `arena-app/src/content/artifacts/` is a SEPARATE copy of the canonical `src/content/artifacts/` and had been frozen at the 2026-05-29 consolidation commit — the leaderboard frontier chart, models catalog, model detail pages, and command palette all build from it. Same two-copies trap as the M9 module-enum bake break.
- **Fix shipped**: all 17 canonical manifests synced into arena-app (adds `advisor-gguf`, `kepler-gguf`, `orionfold-cortex`; refreshes the 8 drifted with positioning/known_drift/lane_summary/siblings); arena-app `content.config.ts` artifacts schema ported up to canonical (bench fields `shapes/modes/results/samples/sources/how_to_load/citation` + `lane_summary` + `siblings`); `model-prompts.mjs` gained advisor + kepler example prompts and `advisor`/`astro` vertical badges. `evals.mjs` BENCH_MODELS verified — already an exact mirror of `fieldkit.arena.benches` (no drift).
- **Canonical `advisor-gguf.yaml` enriched** (was bare): `published_at` + positioning drawn from the published launch copy (30B-prompted 8/21 vs 4B-trained 18/21, refusals 9/9, 42 tok/s) **+ `article: the-refusal-floor-is-trainable` — NOTE this overrides the launch session's deliberate "no `article:`, product page is the methods surface" call** so catalog cards get a real link; revert is a one-line delete if the operator wants the omission back.
- **Leaderboard mirror refreshed** (`fieldkit arena mirror --repo-root arena-app`): was 2026-05-28 (pre-Advisor/Kepler); now 2026-06-11 — live rows 2→21, `kepler::Q8_0` ranks. Advisor serving-lane evidence stays in its offline preflight receipts (no cockpit leaderboard rows) — data-honest.
- **Verified live over CDP** (per pinned discipline): frontier chart legend now lists `advisor-gguf` (7 models · 30 builds; advisor at 42 tok/s × 0.86 eval, sweet-spot ring), models page shows advisor/kepler/cortex cards, detail page renders the new positioning. Main build 537 pages + both render verifiers green; demo rebaked + deployed + links verified. ⚠ Gotcha logged: the sidecar serves `_webui` with NO `Cache-Control`, so the parked Chromium heuristically served the STALE pre-bake leaderboard HTML after restart — verify post-bake pages with `Network.setCacheDisabled` (or a hard reload), not a plain `goto`.
- ~~Open follow-up: missing `kind: bench` manifest for `Orionfold/Advisor-bench`~~ — CLOSED 2026-06-11 (Path A session shipped `advisor-bench-v0.1.yaml`).

### 2026-06-10 — Cortex-grounded Advisor chat wired into Arena

- **Free-prompt chat can now retrieve live from the Advisor corpus pack** — closes the launch-era gap where the full retrieval loop existed only through eval-row replays. New `fieldkit.arena.cortex_chat` (packet builder: pgvector `advisor_corpus_v01` + NIM embedder via `MemoryIndex`, chunk→top-3-unique-source dedup, 900-char query-centered excerpts, verbatim `/no_think` system contract + `enable_thinking:false` rider — byte-compatible with `preflight.py` production packets). `ChatRequest.retrieval: bool`; eval mode wins; Cortex down = hard SSE `error`, never a silent ungrounded turn. `start` event carries a `retrieval` receipt (table + manifest sha `6b1e832d099c` + source cards w/ cosine dist). `/api/compare/options` flags `advisor: true` lanes + carries `retrieval_source` (active pack: table/sha/source-count); ChatLane defaults a "🧠 Cortex retrieval" toggle ON for advisor lanes, labels it with the active pack (`⛁ advisor_corpus_v01 · 182 src · 6b1e832d099c`), and renders grounded source chips per turn. 13 new tests (10 packet-builder + 3 chat-stream), arena suite 490 green; `_webui` rebaked (also clears the pending FieldkitModules copy rebake) + demo rebaked/deployed/verified.
- **Step-0 stack verification receipts**: `advisor_corpus_v01` intact (646 chunks / 183 slugs); `nim-embed-nemotron` restarted (was exited 25 h); live recall rescored `--skip-ingest`: source_recall@5 **0.977, gate pass** — identical to the 2026-06-09 receipt. Fixed `score_recall_live.py` signature drift (`_load_rows` gained pool/heldout args after the live script was written).
- **Live smoke (API + CDP browser)**: Hermes-brain question → grounded answer, exact `Citations: [article_the_hermes_harness_on_spark]`, 45 tok/s; urgency-pretext `.env.local` probe → clean refusal `Citations: []`. UI smoke: toggle ON by default on the advisor resident lane, chips render. Noted: fieldkit-v0.5 question hit the known safe-direction over-refusal drift (cited changelog sources but refused) — model behavior, not wiring.

### 2026-06-10 — /fieldkit/ landing un-froze (v0.13.0 → v0.31.0) + module-copy rebalance

- **Live `/fieldkit/` page was 18 releases stale**: `index.astro` read the retired two-repo-era mirror `fieldkit/_version.py` (frozen at 0.13.0 since the cutover) while releases bumped only the canonical `fieldkit/src/fieldkit/_version.py`. Page now reads the canonical file directly; mirror deleted; `sync-field-notes` mirror logic retired in scripts + SKILL.md (do not resurrect).
- **Module-card copy rebalanced** (operator-directed): all 18 `fieldkit/docs/api/*.md` `summary:` lines rewritten reader-facing at 96–222 chars (`training` was ~780; `arena`/`harness` read like internal ship logs with M*/H*/Bet codenames — detail stays in doc bodies). Taglines trimmed (`arena` 71→38 chars) and the arena-app `FieldkitModules.astro` copy synced 13→18 modules. NOTE: arena-app `_webui` rebake pending next cockpit session (copy-only change).
- **`audit_landing.py` upgraded 4→6 checks**: new `landing_version_source` (canonical version path + no mirror) and `doc_summary_balance` (60–260 chars, no internal codenames); `module_taglines` now audits BOTH component copies + a ≤56-char cap. 6/6 PASS; build 537 pages green + both render verifiers green.

### 2026-06-10 — SVG legacy debt cleared + orionfold.com brand realignment

- **`verify_svg.sh` legacy debt CLEARED** (was Open Items → Cleanup): 105 violations → 0 across the 12 old signature components. role/aria on every legacy `<svg>`, stroke-widths snapped to the {0.5,1,1.5,2} scale, referenced atmospheric gradients added where missing; orphaned `FeatureVelocity.astro` + `FieldkitConstellation.astro` deleted (unreferenced since the pre-cutover redesign). Commit `ad6a092`.
- **Marketing site realigned to the orionfold.com parent brand** (operator-directed): new spec `_SPECS/orionfold-brand-alignment-v1.md`. Tokens extracted from live orionfold.com → `src/styles/global.css` `@theme`: cool 260-hue neutrals, indigo primary `oklch(55% .18 260)`, orbit-gold `oklch(70% .14 82)`, navy→blue→gold hero ramp, SVG accents re-tuned (blue=brand indigo, orange=gold). Ported `.of-surface`/`.of-pressable` card idiom and applied to the home-page cards; hero gained the gold orb; field-notes hardcoded Airtable dark1 hexes → semantic vars. **`design-system-v1.md` (Airtable) re-scoped to operator panes (`arena-app/`) only** — index updated. Build 537 pages green; artifact/field-notes/SVG verifiers green; browser-smoked home/field-notes/article/artifacts at 1440px.

### 2026-06-10 — Orionfold Advisor PUBLIC LAUNCH

- **HF artifacts live**: [`Orionfold/Advisor-GGUF`](https://huggingface.co/Orionfold/Advisor-GGUF) (4B-SFT-v0.2 Q8_0 4.0 GB as `model-Q8_0.gguf`; `license: other` + nvidia-nemotron-open-model-license link; OOD-first card — headline eval is curveball-v0.2 85.7%, Spark-tested 42 tok/s measured live, 4 bounded known-drift entries, Methods → product page + evidence dir; pushed via `hf_push_resilient.py`, ~16 min) and [`Orionfold/Advisor-bench`](https://huggingface.co/datasets/Orionfold/Advisor-bench) (pool 75 / frozen heldout 28 / curveball-v0.1 40 / curveball-v0.2 21 / corpus-manifest 182, all sha12-pinned in the card; results table for 3 lanes). verify_stage 7/8 — the sole FAIL is check 4 (Methods must be a field-notes URL; the Advisor's methods doc is deliberately the product page), operator-accepted at the push gate. Artifact manifest `src/content/artifacts/advisor-gguf.yaml` written (no `article:` — product page is the methods surface).
- **Website launch shipped**: `products/orionfold-advisor/` (positioning per spec §2/§3; mined build block — 2 days/29.9 h, 10 sessions, 871 turns, 118.9M tokens 97.4% cache, 4,307 LOC `scripts/orionfold_advisor/`, 54 advisor tests, all Claude Fable 5; 7-feature tour: 5 fresh 2x clips + 2 authentic dogfood captures) + `AdvisorTeaser` on the home page (after CortexTeaser; reads the products collection) + fieldkit arena module blurb refresh. `verify_product_article.sh` PASS, build 537 pages green, both render verifiers green.
- **Article series started**: `articles/the-refusal-floor-is-trainable/` PUBLISHED (flagship: frozen-curveball discipline; 30B prompt-contract 8/21 + 3 private-state fabrications vs 4B trained 18/21 + refusals 9/9 on identical packets; v0.1 refusal regression 14/15→9/15 caught by frozen OOD bench, v0.2 corpus-design fix; new `RefusalFloor` signature SVG + dual-path inline fn-diagram + 8 explainers; transcript.md carries receipt provenance). Two `status: upcoming` placeholders queued: `gates-before-the-advisor` (recall gates, raw-base preflights, spec-contamination catch) and `governed-routing-with-receipts` (observables-only router, bakeoff economics, §14 receipt). NOTE: `verify_svg.sh` has ~105 pre-existing violations in OLD signature components (MarketGrowth, SystemArchitecture, etc.) — the new article's two SVGs pass; the legacy components are untouched tech debt.
- **Arena surfaces refreshed for the Advisor era**: `products/orionfold-arena/` gained 3 toured features (guarded lane lifecycle / measured benches in the eval drawer / vertical-proof Cortex cards; shots 12–14, feature list now matches the 14 count); **arena demo re-recorded** against the live cockpit — `fieldkit.arena.fixtures._STUB_ENDPOINTS` extended with the 4 `api/advisor/*` reads and `_FORBIDDEN_STUB_KEYS` gained `endpoint` (probed lane URLs were leaking 127.0.0.1:8091 into stubs; now 0 local-URL occurrences), 29 fixture tests green, fieldkit CHANGELOG [Unreleased] entry added; `ARENA_DEMO=1` rebuild + `deploy_arena_demo.mjs` → `public/arena/demo/` (37 product screenshots in sync, links verified) + headless smoke: **all 4 advisor cards render in the sidecar-less demo cortex page**.
- Advisor proof state (compact; receipt-level history in git log of this section): 4B-SFT-v0.2 PROMOTED serving lane (publish receipt 9/9 gates, `advisor-publish-receipt-v0.1.json`); 30B = teacher/comparison on disk; benches frozen (heldout 28 `3220b8e799cd`-combined, curveball-v0.1 `122bcd619e9d`, curveball-v0.2 `4b6cac85e41f`, corpus manifest 182 `6b1e832d099c`); AD-AE-11..17 all closed/fixed except the open §10 controls + §12 live ledger (Open Items).

### 2026-06-09 — Codex coexistence baseline adopted

- Codex reads `HANDOFF.md` at session start and updates it at session end when live state, public artifacts, release posture, or the status beacon changes. Coexistence layer at `ddb6626`, scoped to `AGENTS.md`, `CODEX-CC.md`, `.codex/`, `.agents/skills/`. Do not edit `.claude/` for Codex behavior unless explicitly requested.

### Published Baseline To Preserve

- **Advisor (NEW)**: <https://huggingface.co/Orionfold/Advisor-GGUF> (Q8_0 only; recommended) + <https://huggingface.co/datasets/Orionfold/Advisor-bench>; launch page `products/orionfold-advisor/`; flagship article `articles/the-refusal-floor-is-trainable/`. Headline held-out numbers: frozen curveball-v0.2 18/21 scored==strict, refusals 9/9, 0 private-state risk (vs 30B prompt-only 8/21, 3/9, 3 fabrications); heldout 28/28 hinted+hint-free; 42 tok/s / ~12 GB / warm 2 s on the Spark. Known drift: Route:-prefix soft class (2/5), one OOD over-refusal (safe), in-distribution heldout caveat, packet-contract-shaped behavior.
- Kepler: <https://huggingface.co/Orionfold/Kepler-GGUF> + <https://huggingface.co/datasets/Orionfold/Kepler-bench>; article `articles/the-gate-before-the-gpu/`; Q8_0 recommended; held-out: Q8 88.6% / curveball 84.1% local/$0. Drift: `hohmann_transfer`, `altitude_from_period`.

## Live Runtime

Last recorded runtime baseline: hardening-batch session, 2026-06-11.

- Cockpit `:7866` UP in browser-use mode (pid 3479262, `_webui` bake incl. kepler on the frontier chart, HTML `Cache-Control: no-cache`), visible CDP Chromium `:9222` UP (pid 3479279), parked on `/arena/models/`. Serving lane: llama-server `nemotron3-nano-4b-sft-v02-q8` on `:8091` (the PROMOTED Advisor lane, ~12 GB) — **relaunched through the guarded LaneTruth UI** after the kepler bench window, run-context anchored on warm. **`pgvector` (:5432) + `nim-embed-nemotron` (:8001) containers UP** (embedder was docker-stop/start-bounced around the guarded launch per AD-FK-1 — verify 200 before grounded-chat work). 30B down-but-on-disk; `fk-nim-8000` + `nemo-train` stopped (restartable). Recipes 8 in `~/.fieldkit/arena/lane-recipes.json`.
- This session's lane-adjacent terminal actions (logged per pipeline discipline): operator-armed `:8091` teardown (operator-clicked in LaneTruth), 4× `llama-bench` on the kepler GGUFs while the box was free, operator `docker stop/start nim-embed-nemotron` around the guarded relaunch (AD-FK-1 workaround).
- ~~`src/data/arena-mirror/` written by default~~ — FIXED 2026-06-11: `fieldkit arena import` no longer writes the root mirror unless `--mirror` is passed. The tracked mirror lives at `arena-app/src/data/arena-mirror/leaderboard.json`.
- `.env.local` still carries `FK_ARENA_BUILD_DIR`/`FK_ARENA_CORPUS_DIR`/`FK_ARENA_SFT_DIR`/`FK_ARENA_REWARD_DIR` pointed at the Advisor proof.
- `/tmp/fk` and `/tmp/fk-test` venvs are GONE (reboot); `/tmp/arena-venv` (fieldkit editable + huggingface_hub 1.18 + `hf` CLI) is the working HF/publish venv this session used. HF pushes need `HF_HOME=/home/nvidia/data/.hf-cache HF_HUB_DISABLE_XET=1`.
- Tear down when done: `:8091` lane from visible LaneTruth first, then `arena_lifecycle.sh down --browser`.

## Build / Verify

```bash
node node_modules/astro/astro.js build          # 538 pages
node scripts/verify_artifact_rendering.mjs
node scripts/verify_field_notes_rendering.mjs
node scripts/verify_arena_catalog_sync.mjs   # artifact yamls byte-match arena-app copies
# arena demo rebake (when arena-app or fixtures change):
ARENA_DEMO=1 node arena-app/node_modules/astro/astro.js build --root arena-app
node scripts/deploy_arena_demo.mjs && node scripts/verify_arena_demo_links.mjs
```

- `npm run build` remains broken on this checkout; use direct Astro.
- `build:og` is CI-only. Privacy gate before commits: `.codex/hooks/secret_scan.sh --cached`.
- arena-app has its OWN articles schema copy — summaries >300 chars pass the main build but fail the `ARENA_DEMO=1` build (bit this session; both placeholder summaries trimmed).

## Open Items

### Editorial / Series

- **NEXT TASK (queued 2026-06-11, operator-directed): orphan-screenshot audit + reuse.** Sweep the project folders (`products/*/screenshots/`, `products/*/assets/`, `articles/*/`, `public/products/`, `public/screenshots/`, `arena-app/public/`, evidence dirs) for screenshots no page references. For each orphan: if usable on a product page, marketing surface, or article, place it WITH a proper descriptive alt + italic caption (per the 21-shot audit bar: ≥75-char alt + caption); otherwise list it for deletion. Also fold in: `01-cockpit.png` shows pre-Path-A counts (artifacts 18, runs 16, kepler active lane) — retake or accept; `kepler-gguf` catalog card shows a bare slug (manifest has no `positioning:` field — content gap found during the 04-models retake).

- Write the two queued Advisor series pieces in place (promote `status: upcoming` → `published`): `gates-before-the-advisor`, `governed-routing-with-receipts`.
- Phase 2 launch (`product-writer` for the autonomous-harness cockpit) and Living-model launch posture unchanged.

### Advisor / Arena

- **Path A DONE 2026-06-11** (rollup + import + bench manifest + CDP verify — see Current State). Path B (live tier, `cockpit:advisor_contract` via eval runs against the serving lane on `:8091`) stays open as the ongoing narrated-session story; AF-28 projects done `eval_rerun` jobs without a rebuild.
- **Arena hardening batch: ALL 4 items + mirror-default DONE 2026-06-11** (see Current State; frontier chart now 7 models · 29 builds, every quality-bearing model renders).
- **AD-FK-1 — one-lane guard vs the Cortex embedder** (found during the kepler lane swap): exempt non-serving OpenAICompat container lanes (the `:8001` embedder) from the AE-R13 one-lane envelope in `fieldkit.arena.launcher`, OR give the guard an explicit allowlist — today a guarded chat-lane launch is impossible while the grounded-chat stack is up, and `teardown_first` would reap the docker port. Safety-guard behavior change → needs its own test; do NOT hot-patch.
- Optional §10 corpus *controls* (import/swap + cockpit-driven pgvector re-ingest; read pane shipped). Optional §12 live per-query route-ledger persistence (bakeoff read surface shipped). Optional v0.3 lever: `Route:`-prefix boundary + one over-refusal class — **freeze curveball-v0.3 before any v0.3 training**.
- AD-AE-13 display gap stands: terminal-run wide receipts show "0 results" on the Cortex card until a card run.
- WB-11: LaneTruth can discover/pin NIM lanes but not launch them through the guarded UI.

### Operator-Owned Live Infra

- Second Brain evidence-server deploy + first `/api/knowledge/reindex` backfill still pending. PSI key still missing (blocks PageSpeed in `/seo-monitor`).
- `sudo chown` root-owned container-written dirs when needed (`merged-hf-bf16`, `init-lora-r16`, HF-cache stubs; the advisor-4b-sft GGUFs are root-owned but readable).

### SEO

- Re-run `/seo-monitor` in the settlement window; GSC token `fePoYwMX...` HOLD. New public URLs to watch for indexing: `/products/orionfold-advisor/`, `/articles/the-refusal-floor-is-trainable/`, the two HF repos.

### Cleanup

- Human-eye/Lighthouse pass on LoRA/adapter/dataset detail pages; bakeoff gated-catalog footer last-write-wins; deprecate retired `sync-field-notes` skill body; optional Claude memory-namespace symlink relocation.

## Recent Decisions

### 2026-06-10 - Marketing site follows orionfold.com; Airtable system scoped to operator panes

The Airtable-derived design system (design-system-v1) had been applied site-wide; the operator directed that it stay appropriate for the Arena app UI only, while the rest of ainative.business reads as a natural extension of the redesigned orionfold.com parent brand. Tokens were extracted from the live parent site (indigo primary, orbit gold, cool 260-hue neutrals, of-surface card idiom) and applied at the token layer — the two sites already shared structure (nav idiom, blur orbs, Geist fonts), so the realignment is recorded in `_SPECS/orionfold-brand-alignment-v1.md` and reversible via git. | Manav (with Claude)

### 2026-06-10 - Advisor public launch executed (full scope, operator-approved)

Operator approved the full public launch in one session: HF model repo `Orionfold/Advisor-GGUF` (name mirrors Kepler-GGUF precedent), HF bench dataset, product page, home teaser, flagship article + 2 series placeholders, Arena product/demo refresh. Push gate accepted the known verify_stage check-4 deviation (Methods links the product page, not a field-note — the launch's methods doc IS the product page). The HF card leads with the frozen OOD number (85.7%), not the in-distribution 28/28 — measurement-first positioning carried to the eval choice. | Manav (with Claude)

### 2026-06-10 - 4B-SFT-v0.2 promoted to the Advisor serving lane

After the SFT-v0.2 receipt battery, the operator promoted the trained 4B over the 30B on evidence: the frozen pre-registered curveball-v0.2 gate (18/21 scored==strict, refusals 9/9, 0 private-state risk vs the 30B's 8/21, 3/9, 3 risk rows — the 30B's prompt-only contract fabricated private-looking state under novel pretexts), both 28/28 wides (hinted + hint-free), and the curveball-v0.1 refusal-regression fix (15/15). The trained lane, not the prompt, carries the refusal floor. ~12 GB / warm 2 s vs ~40 GB / 14 s. The 30B stays on disk as teacher/comparison. | Manav (with Claude)
