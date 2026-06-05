<!--
  Session handoff for ainative-business.github.io (Spark-operated monorepo).
  Convention:
  - Replace "Open items" each session; do NOT append.
  - "Recent decisions" is a short running log — keep ~2 latest, prune older.
  - Full history of any pruned entry is recoverable via `git log -p HANDOFF.md`.
  - Last pruned/reset: 2026-06-05 (full prune — stale Phase-C in-flight detail removed after Kepler shipped).
-->

# HANDOFF — ainative-business.github.io

## Current state

### ✅ 2026-06-05 — Kepler SHIPPED; repo clean + in sync; box idle

> **The greenfield astrodynamics vertical (`Kepler`) is published end-to-end and the tree is clean.**
> `origin/main` tip = **`be1ed2d`**, **branch up to date with `origin/main` (0 ahead)**, working tree clean except two
> pre-existing untracked items to **leave alone** (`.claude/scheduled_tasks.lock` = runtime lock; `src/data/arena-mirror/leaderboard.json` = generated).
> GitHub Pages auto-deploys on push to `main` → site is live at `ainative.business`.

**What's live:**
- **Model** — <https://huggingface.co/Orionfold/Kepler-GGUF>: 4 GGUF variants (Q4_K_M / Q5_K_M / Q6_K / **Q8_0**=recommended),
  apache-2.0, chat_format chatml, positioning-led card (Spark-tested ladder → T2 head-to-head → variants → how-to → known-drift → bench cross-link).
  **F16 deliberately NOT published** (operator call). Source GGUFs still at `/home/nvidia/data/quants/Kepler/`.
- **Dataset** — <https://huggingface.co/datasets/Orionfold/Kepler-bench>: `pool.jsonl` (120) + `heldout.jsonl` (44) + `verifier.py` + `units.py` + card (`kind: bench`, AV-11).
- **Article** — `articles/the-gate-before-the-gpu/` (`cf132a4`, pushed; `series: Machine that Builds Machines`, `book_chapters:[10,11,14]`,
  `customer_linked: true`). The SFT-vs-RL-vs-RLVR method-selection deep-dive. **Has NO outbound HF links yet** (optional enhancement now both repos are live).

**Headline numbers (on disk under `evidence/astrodynamics/`):**
- **T2 head-to-head** (44-row external curveball, 4096-token budget, `astro_numeric_match` ±2%): **Kepler-Q8_0 84.1% local/$0/166 mean-tok** · Claude Haiku 4.5 97.7% · Gemini 3.1 Flash-Lite 95.5% (both cloud, ~3× more verbose). Local 8B specialist ~11–14 pp below frontier *small* cloud, $0/offline, format reliability matches (100% boxed / 0% trunc).
- **Per-variant fidelity** (44-row held-out, 2048-budget): Q4 75% · Q5 75% · Q6 84.1% · **Q8 88.6%** · F16(ref) 86.4%.
- **Honest `known_drift`** (on the card): weak on `hohmann_transfer` + `altitude_from_period` (SFT-coverage gap, not AV-R1 truncation).

**The Kepler pipeline lessons are encoded as memories** (apply to the next vertical): `feedback_sft_vs_rlvr_decision` (the prior question — cheap-correct-trajectory + enumerable-output → SFT-only wins), `feedback_rlvr_headroom_gate` (the Goldilocks band + the bimodal-per-family refinement: 0% = SFT-coverage gap, not RL headroom), `feedback_preflight_bench_before_quant`, `feedback_smoke_projection_slack`.

## ⚙️ Live runtime (mostly torn down — box is idle, GPU lane FREE)

- **`pgvector` container UP** (`:5432`, db `vectors`, table `blog_chunks`) — backs the Second Brain index. The only thing running.
- **DOWN:** Arena cockpit (`:7866`), Kepler Q8 `llama-server` (`:8091`), NIM embedder (`:8001`), visible CDP Chromium (`:9222`). No llama.cpp/vLLM process. **~115 GiB available** (one-lane envelope wide open).
- **To bring the cockpit back:** `bash .claude/skills/arena-lifecycle/scripts/arena_lifecycle.sh up --browser` (verbs `up|down|restart|status`; `--browser` is CC-Bash-safe; venv `/tmp/arena-venv`). After any `arena-app/` edit, rebake: `fieldkit arena build --repo-root arena-app`.
- **To serve a Kepler lane** (e.g. for Arena Compare): `spark-serve` the GGUF at `/home/nvidia/data/quants/Kepler/`, or the merged SFT `merged-hf-bf16` via the proven `vllm-node:latest` image.

## Build / verify

`node node_modules/astro/astro.js build` (~517 pages; `npm run build` is broken on this SMB checkout per `reference_astro_build_smb_symlink_break`) → `node scripts/verify_artifact_rendering.mjs` + `node scripts/verify_field_notes_rendering.mjs`. `build:og` is CI-only (needs Chrome). **arena-app/ + fieldkit/ build separately** from the marketing site — pushing arena/fieldkit changes does NOT change public `dist/`. **Secrets:** `.env.local` (gitignored, chmod 600) holds `PYPI_TOKEN`, `HF_TOKEN`, `OPENROUTER_API_KEY`.

## Open items (by swimlane)

### 🪐 Kepler / astrodynamics — ship tail (small, optional)
- **Add Kepler HF links to the article** — `articles/the-gate-before-the-gpu/` has no outbound `Orionfold/Kepler-GGUF` / `-bench` links yet; optional now both repos are live. Operator-gated push.
- **Manual cleanup** — delete the stray byte-identical lowercase dup `model-f16.gguf` at `/home/nvidia/data/quants/Kepler/` (auto-classifier blocked the `rm`; safe by hand; the canonical `model-F16.gguf` reference variant stays).

### 🚀 Release
- **Optional `fieldkit v0.23.0` cut** — ships (a) the cockpit education layer **LA-12..16** in the wheel's baked `_webui` (site/cockpit-only, already committed at `27efc11`), and (b) the **AF-15 `scorer_path` hook** on the eval/compare path. The `[Unreleased]` CHANGELOG block carries these. `fieldkit-curator` release mode. ⚠️ The running cockpit's `/tmp/arena-venv` + the PyPI wheel still carry OLD source — in-cockpit `POST /api/jobs` eval needs a `pip install -e ./fieldkit` there (or this cut).
- **1-line test fix** — pre-existing `test_drain_arbiters…mem_trace` failure: asserts `autonomy.enabled is False` but reads the box's armed `~/.fieldkit/arena/autonomy.json` without `path=` isolation. Unrelated to recent diffs.

### 🔧 Arena dogfood — `arena-enhancements-v1` (spec DRAFT, 16 decisions AE-1…16; confirm before build)
The payoff from running Kepler's pipeline live through the cockpit. Spec `_SPECS/arena-enhancements-v1.md`; gitignored ledger `_IDEAS/arena-dogfood-feature-extraction.md`. **No arena.db churn** (everything lands in `result_json`/file-reports/panes/nav; `user_version` stays 6). Release gate ~`v0.23.0+`.
- **S1** (gaps the live `rl_run` exposed): AE-1 wire reward gauge to the live run (AF-11) · AE-2 surface degenerate/zero-advantage steps · AE-3 persist per-step `step_history[]` · AE-4 lineage step-index. Validate on the *next* live `rl_run`, not a file test.
- **S2** (IA/flow refresh): AE-12 regroup the flat 11-tab nav by lifecycle · AE-13 data-flow routing audit · AE-14 redefine Standup/Lab/Reward leverage · AE-15 telemetry "active lane" reads the live GPU process not the static config · AE-16 on-card job identity (time/id/run-label).
- **S3–S6:** build-spine pane (AF-1) · corpus feed + gate cards (AF-2/AF-5) · provenance/lineage (AF-4/AF-6) · wiring quick-wins (AF-7 scout→Compare + lock-time behavioral gate, AF-8 bench preview).

### ✍️ Editorial — MTBM series (book-overlay, `book_chapters` cross-link only — do NOT edit `src/data/book/chapters/**`)
- **Phase 2 launch** — `product-writer` launch for the built **autonomous-harness** cockpit surface (morning-standup · cron queue · budget-governor), cross-linking the existing H4 deep-dive. Phase 2 has shipped (fieldkit v0.19.0); the launch article is the open beat.
- **Living-model launch** (`products/living-model/`, `status: upcoming`) — stays staked; its hero is the `fieldkit.lineage` delta chart, which is ~flat under SFT-only. Promote when a future RL-sensitive run produces real delta data, OR reframe honestly around the headroom-gate methodology.

### ⚙️ Operator-owned (live infra; deliberate human-armed steps)
- **A future live `rl_run`** — install pinned `fieldkit[rl]` + a standalone pinned aarch64+CUDA-13 vLLM lane (`vllm-node:latest` exists on the box), set `FK_RL_*` (env wrapper `scripts/astro_bench/fk-rl-env.sh`), `fieldkit arena autonomy on` → overnight drain. NB Kepler's own C5 run already completed (clean null); this is for a *future* RL-sensitive vertical/bench, and it draws the real `fieldkit.lineage` chart that promotes the living-model launch. Runbook: `fieldkit/docs/api/rl.md` → "Operator run". One-lane envelope only (`project_spark_unified_memory_oom`); teardown EngineCore-aware (`pkill -9 -f 'vllm|EngineCore'`).
- **`sudo chown`** the root-owned container-written dirs (`merged-hf-bf16`, `init-lora-r16`, the HF-cache `models--Qwen--Qwen3-8B` stub).
- **Second Brain** — deploy `articles/rag-eval-ragas-and-nemo-evaluator/evidence/second-brain-server.py` over the live `/home/nvidia/second-brain-mcp/server.py` + `pip install -e fieldkit` in its venv; first `/api/knowledge/reindex` runs `ensure_schema()` (backfills provenance cols). `ask_blog` also needs the cached local Llama-3.1-8B generator on `:8000`.
- **PSI authenticated key** still missing (blocks PageSpeed in `/seo-monitor`).

### 📈 SEO
- **Re-run `/seo-monitor`** (~1–2 weeks out) — confirm live `sitemap-0.xml` settled ~182 URLs; GSC *Discovered–not-indexed* (355, stale) should bleed down as the Validate-Fix completes. GSC "unused verification token" `fePoYwMX…` is **HOLD / do-not-remove** (Workspace-owned TXT). Journal: `seo-progress.md`.

### 🧹 Destination & cleanup (non-blocking)
- **#7** — human-eye/Lighthouse pass on the LoRA/adapter/dataset detail + empty-state listing pages (only HTML-verifier coverage so far; the 4 quant pages were browser-verified 2026-05-31).
- **#11** — bakeoff article's gated catalog footer last-write-wins (`chrome_footers.collect_gated_articles()` keys by slug). Low priority.
- **#18** — patent-strategist W3 fine-tune (source-side, ETA ~2 weeks). Likely more `kind: lora` manifests; render path + notebooks scaffold are ready.
- **Deprecate the retired `sync-field-notes` skill** (body retired post-monorepo-cutover but not deleted; still references the old source `project-stats.json` path).
- Optional: relocate the CC memory namespace symlink (`-home-nvidia-ai-field-notes`, 93 files) into this namespace for a fully clean cutover (safe as-is).

## Recent decisions (short running log — prune older)

### 2026-06-05 (Kepler PUBLISHED — T1 article + T2 head-to-head + T3 GGUF/bench, both HF repos LIVE)
Executed the operator's three STEP-2 ship-tasks for the astrodynamics vertical (named **Kepler**). **T1:** wrote + pushed the method-selection deep-dive `articles/the-gate-before-the-gpu/` (`cf132a4`; new signature `GateReadings.astro`; the SFT-vs-RL-vs-RLVR decision discipline as the spine — the 86% SFT was the right call, RLVR added 0, ran only as a control-plane stress-test). **T2:** scored Kepler-Q8_0 vs cloud frontier-small via `scripts/astro_bench/score_gguf_lane.py` (GGUF lane + OpenRouter, shared `astro_numeric_match`, new `--max-tokens`) → the model-card "how it stacks up" table (Kepler 84.1% local/$0 vs Haiku 97.7% / Gemini Flash-Lite 95.5%; dropped qwen3-8b + deepseek-r1 — slow OpenRouter providers stalled under the 4096 budget). **T3:** requant `merged-hf-bf16` → 4 GGUF variants (`9dce32a`), then `hf-publisher` → `Orionfold/Kepler-GGUF` (Q8=recommended, F16 dropped) + `Orionfold/Kepler-bench` (`kind: bench`). **AF-15 dogfood:** threaded the generic `scorer_path` hook through the eval/compare path (was rl_run-only) so a `\boxed{}` vertical scores correctly through the cockpit, not 0.0 via boxed-blind `numeric_match` — committed `9dce32a`, +2 tests, suite 250 pass (1 pre-existing mem_trace failure, see Open items). **All committed + pushed** (`be1ed2d` tip; tree clean). The `[Unreleased]` CHANGELOG carries the AF-15 hook for the next cut. | Manav (with Claude)

### 2026-06-05 (C6 STEP-1.5 — the AV-12 RL-headroom gate RAN; bimodal result → ship SFT, branch 1)
Built + ran the RL-headroom gate (AV-12/RV-11): `scripts/astro_bench/{transfer,gen_transfer,headroom_gate}.py` — 11 error-mined Tier-1 transfer templates (un-named formulas · new bodies μ_Mars/μ_Moon/μ_Jupiter · two-hop chains · e>1 hyperbolic), 48 candidates disjoint from pool+heldout+SFT corpus, all self-verify, 47 tests green. Scored the frozen SFT (`merged-hf-bf16`) in the NeMo container (~24 min): **agg reward 20.83% · boxed 100% · trunc 0%** — but the per-family read is **BIMODAL**: fully-generalizes some (`altitude→speed` 100%), **0%** on the target weak spots (new-body hohmann/circular, un-named altitude_from_period); only 4 families/15 rows in the productive (0,1) band. **Refines the C5 lesson:** 0% = the mirror of saturation (zero group-advantage) → an **SFT-coverage gap, not RL headroom**. **FORK RESOLVED (operator) = BRANCH 1: SHIP the 86%-generalizing SFT + tell the honest methodology story** (re-RL buys a thin lift of narrow value; expand-SFT is a later option). Memory `feedback_rlvr_headroom_gate` updated. Committed `a49dff6`. **→ became the 2026-06-05 publish work above.** | Manav (with Claude)

<!--
  Older entries pruned 2026-06-05 (keep ~2 latest). Recover any via `git log -p HANDOFF.md`. Pruned set, newest→oldest:
  - C5 full RLVR run = clean null (selected_step=0, in-loop held-out flat 0.9583) + C6 STEP-1(a) generalization 86.36%; encoded the RL-headroom gate (AV-12/RV-11, feedback_rlvr_headroom_gate); 2 cockpit bugs → AE-15/AE-16.
  - C4 wiring-complete + C5 4-step smoke PASSED (scorer_path hook; enqueue_rl.py; reward REAL pool 0.75–0.875 / held-out 0.958).
  - C2(b) SFT-init GATE PASS (held-out 86.36% vs base 12.5%, NeMo p65, ~11 min not multi-hour) + AF-10 live SFT cockpit feed.
  - Phase-C spec authored (_SPECS/astrodynamics-vertical-v1.md, AV-1…11 + AV-R1…R5); bench generator built (scripts/astro_bench/, 20 tests).
  - rl-lane-autonomy LA-1..16 BUILT + RELEASED (fieldkit v0.21.0 GPU backend, v0.22.0 LA-1..11 autonomy, LA-12..16 education layer 27efc11).
  - rlvr-loop-v1 / autonomous-harness-v1 / second-brain-pipeline-v1 / cost-plane-v1 ALL BUILT + RELEASED (fieldkit v0.18.0→v0.20.0); the whole pane→hands→engine roadmap is built + shipped.
  - Phase-3 editorial: the-machine-improves-itself deep-dive SHIPPED; living-model launch STAKED upcoming.
  - Phase-1 Arena launch article SHIPPED (products/arena-control-plane/, 606333d).
-->
