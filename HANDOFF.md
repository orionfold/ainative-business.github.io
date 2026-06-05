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

### ✅ 2026-06-05 — Kepler SHIPPED + `fieldkit v0.23.0` RELEASED; repo clean + in sync; box idle

> **The greenfield astrodynamics vertical (`Kepler`) is published end-to-end, `fieldkit v0.23.0` is on PyPI, and the tree is clean.**
> `origin/main` tip = **`9885dc2`** (stats refresh post-v0.23.0), **branch up to date with `origin/main` (0 ahead)**, working tree clean
> except two pre-existing untracked items to **leave alone** (`.claude/scheduled_tasks.lock` = runtime lock; `src/data/arena-mirror/leaderboard.json` = generated).
> GitHub Pages auto-deploys on push to `main` → site is live at `ainative.business`.
> **`fieldkit v0.23.0`** — tag `fieldkit/v0.23.0` + <https://pypi.org/project/fieldkit/0.23.0/> (both install-verifies green): ships the
> LA-12..16 cockpit education layer in the baked `_webui` + the AF-15 `scorer_path`/`api_key_env` hooks on the eval/compare path +
> AF-3/AF-9 reward-signal + SFT-progress endpoints. No schema/module change (`user_version` stays 6). The `[Unreleased]` CHANGELOG is now empty.

**What's live:**
- **Model** — <https://huggingface.co/Orionfold/Kepler-GGUF>: 4 GGUF variants (Q4_K_M / Q5_K_M / Q6_K / **Q8_0**=recommended),
  apache-2.0, chat_format chatml, positioning-led card (Spark-tested ladder → T2 head-to-head → variants → how-to → known-drift → bench cross-link).
  **F16 deliberately NOT published** (operator call). Source GGUFs still at `/home/nvidia/data/quants/Kepler/`.
- **Dataset** — <https://huggingface.co/datasets/Orionfold/Kepler-bench>: `pool.jsonl` (120) + `heldout.jsonl` (44) + `verifier.py` + `units.py` + card (`kind: bench`, AV-11).
- **Article** — `articles/the-gate-before-the-gpu/` (`cf132a4`; `series: Machine that Builds Machines`, `book_chapters:[10,11,14]`,
  `customer_linked: true`). The SFT-vs-RL-vs-RLVR method-selection deep-dive. Now links `Orionfold/Kepler-GGUF` + `-bench` in the deliverable section (`871a654`, pushed).

**Headline numbers (on disk under `evidence/astrodynamics/`):**
- **T2 head-to-head** (44-row external curveball, 4096-token budget, `astro_numeric_match` ±2%): **Kepler-Q8_0 84.1% local/$0/166 mean-tok** · Claude Haiku 4.5 97.7% · Gemini 3.1 Flash-Lite 95.5% (both cloud, ~3× more verbose). Local 8B specialist ~11–14 pp below frontier *small* cloud, $0/offline, format reliability matches (100% boxed / 0% trunc).
- **Per-variant fidelity** (44-row held-out, 2048-budget): Q4 75% · Q5 75% · Q6 84.1% · **Q8 88.6%** · F16(ref) 86.4%.
- **Honest `known_drift`** (on the card): weak on `hohmann_transfer` + `altitude_from_period` (SFT-coverage gap, not AV-R1 truncation).

**The Kepler pipeline lessons are encoded as memories** (apply to the next vertical): `feedback_sft_vs_rlvr_decision` (the prior question — cheap-correct-trajectory + enumerable-output → SFT-only wins), `feedback_rlvr_headroom_gate` (the Goldilocks band + the bimodal-per-family refinement: 0% = SFT-coverage gap, not RL headroom), `feedback_preflight_bench_before_quant`, `feedback_smoke_projection_slack`.

## ⚙️ Live runtime (cockpit UP in browser-use mode; GPU lane FREE, no OpenRouter activity)

- **Arena cockpit UP** (`:7866`, OpenRouter key loaded) + **visible CDP Chromium UP** (`:9222`, browser-use mode) — brought up 2026-06-05 to verify eval dispatch; **left up**. `arena.db` has **0 running/queued jobs** (the hung qwen OpenRouter eval was killed + its job row deleted — no cloud spend). Kepler eval results preserved on the board: `kepler-q8-gguf` **0.86/44**, `deepseek-r1` **0.84/37**.
- **`pgvector` container UP** (`:5432`, db `vectors`, table `blog_chunks`) — backs the Second Brain index.
- **DOWN:** Kepler Q8 `llama-server` (`:8091`), NIM embedder (`:8001`). No llama.cpp/vLLM process; **GPU lane FREE** (~115 GiB available, one-lane envelope wide open).
- **`/tmp/arena-venv` fieldkit refreshed to 0.23.0** (editable `-e ./fieldkit`) — in-cockpit `POST /api/jobs` eval now dispatches through the AF-15 `scorer_path` (verified: built-in `numeric_match` scores a boxed Kepler completion 0.0, the bench `scorer_path` verifier scores it 1.0).
- **Tear down when done:** `.claude/skills/arena-lifecycle/scripts/arena_lifecycle.sh down --browser` (verbs `up|down|restart|status`; `--browser` is CC-Bash-safe). After any `arena-app/` edit, rebake: `fieldkit arena build --repo-root arena-app`.
- **To serve a Kepler lane** (e.g. for Arena Compare): `spark-serve` the GGUF at `/home/nvidia/data/quants/Kepler/`, or the merged SFT `merged-hf-bf16` via the proven `vllm-node:latest` image.

## Build / verify

`node node_modules/astro/astro.js build` (~517 pages; `npm run build` is broken on this SMB checkout per `reference_astro_build_smb_symlink_break`) → `node scripts/verify_artifact_rendering.mjs` + `node scripts/verify_field_notes_rendering.mjs`. `build:og` is CI-only (needs Chrome). **arena-app/ + fieldkit/ build separately** from the marketing site — pushing arena/fieldkit changes does NOT change public `dist/`. **Secrets:** `.env.local` (gitignored, chmod 600) holds `PYPI_TOKEN`, `HF_TOKEN`, `OPENROUTER_API_KEY`.

## Open items (by swimlane)

### ✅ Kepler ship-tail + Release + eval-dispatch verify — ALL DONE 2026-06-05
- ✅ Kepler HF links added to `articles/the-gate-before-the-gpu/` (`871a654`, pushed). ✅ Stray `model-f16.gguf` dup deleted (operator). ✅ `test_drain_arbiters…mem_trace` fixed via `ARENA_AUTONOMY_STATE` isolation (`a8acc1c`). ✅ `fieldkit v0.23.0` cut + on PyPI (see Current state).
- ✅ **`/tmp/arena-venv` fieldkit refreshed to 0.23.0** (was editable-linked at stale 0.13.0 metadata → `pip install -e ./fieldkit`) — the AF-15 caveat is **resolved**; in-cockpit eval now uses the `scorer_path` hook.
- ✅ **In-cockpit eval dispatch VERIFIED** via browser-use mode (cockpit + CDP Chromium up): `resolve_bench` surfaces the bench `scorer_path`, `run_vertical_eval`/`_load_scorer_callable` load it (resolving the sibling `from units import` that breaks a naive load), and the Jobs board renders `kepler-q8-gguf` 0.86/44 + `deepseek-r1` 0.84/37. Decisive proof: same boxed completion → built-in `numeric_match` **0.0** vs bench `scorer_path` **1.0**.
- ✅ **OpenRouter runs shut down** — the qwen3-8b eval that hung ~2.5 h was killed (cockpit bounce) + its job row deleted; no OpenRouter jobs running/queued. **This motivated AE-17** (cloud-run guardrails — see Arena dogfood S7 below).

### 🔧 Arena dogfood — `arena-enhancements-v1` (spec DRAFT, 17 decisions AE-1…17; confirm before build)
The payoff from running Kepler's pipeline live through the cockpit. Spec `_SPECS/arena-enhancements-v1.md`; gitignored ledger `_IDEAS/arena-dogfood-feature-extraction.md`. **No arena.db churn** (everything lands in `result_json`/file-reports/panes/nav; `user_version` stays 6). Release gate ~`v0.24.0+`.
- **S1** (gaps the live `rl_run` exposed): AE-1 wire reward gauge to the live run (AF-11) · AE-2 surface degenerate/zero-advantage steps · AE-3 persist per-step `step_history[]` · AE-4 lineage step-index. Validate on the *next* live `rl_run`, not a file test.
- **S2** (IA/flow refresh): AE-12 regroup the flat 11-tab nav by lifecycle · AE-13 data-flow routing audit · AE-14 redefine Standup/Lab/Reward leverage · AE-15 telemetry "active lane" reads the live GPU process not the static config · AE-16 on-card job identity (time/id/run-label).
- **S3–S6:** build-spine pane (AF-1) · corpus feed + gate cards (AF-2/AF-5) · provenance/lineage (AF-4/AF-6) · wiring quick-wins (AF-7 scout→Compare + lock-time behavioral gate, AF-8 bench preview).
- **S7 (Cluster F, NEW 2026-06-05 — may pull forward):** AE-17 cloud-run safety guardrails — an `EvalGuardrail` on metered cloud lanes: **G1** teardown-abort (cockpit `_lifespan`/`arena down` kills an in-flight cloud eval cleanly) · **G2** stall-timeout (`FK_EVAL_STALL_TIMEOUT_S` default 600 s no-progress) · **G3** per-run cost cap (`FK_EVAL_RUN_COST_CAP_USD` default $5, live `usage`→`PriceSnapshot`). Env-configurable + tracked in `result_json`. Motivated by the qwen3-8b OpenRouter eval that hung ~2.5 h on 2026-06-05 (§1 Body 4). Spec-only; **not built** (operator hold).

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

### 2026-06-05 (post-release: arena venv → 0.23.0 · in-cockpit eval-dispatch VERIFIED via browser-use · OpenRouter runs shut down · AE-17 guardrail spec)
After the v0.23.0 cut, refreshed `/tmp/arena-venv` fieldkit (`pip install -e ./fieldkit` — was editable-linked at stale 0.13.0 metadata; runtime already current). Brought the cockpit up in **browser-use mode** (`arena_lifecycle.sh up --browser`; `:7866` + CDP Chromium `:9222`) and **verified in-cockpit eval dispatch through AF-15**: `resolve_bench` surfaces the bench `scorer_path` → `run_vertical_eval`/`_load_scorer_callable` load it (resolving the sibling `from units import` a naive load breaks on) → the Jobs board renders `kepler-q8-gguf` **0.86/44** + `deepseek-r1` **0.84/37**; decisive proof = same boxed completion scores **0.0** under built-in `numeric_match` vs **1.0** under the bench `scorer_path`. Bringing the cockpit up had drained two **queued** baseline OpenRouter evals — deepseek-r1 finished (0.84), but **qwen3-8b hung ~2.5 h** holding the lane with uncapped spend → **operator: "shutdown any openrouter runs"** → killed it (cockpit bounce) + deleted its job row; **0 OpenRouter jobs running/queued**. That incident → **operator: spec a guardrail** → added **AE-17 + new Cluster F** to `arena-enhancements-v1` (G1 teardown-abort · G2 stall-timeout `FK_EVAL_STALL_TIMEOUT_S`=600 s · G3 per-run cost cap `FK_EVAL_RUN_COST_CAP_USD`=$5; env-config + `result_json` tracking; mirrors the RL `abort_poller`/sentinel) + risk AE-R6; **spec only, not built** (operator hold). Commits `81b37b9` (AE-17) + this HANDOFF. Cockpit left **up** (browser-use). | Manav (with Claude)

### 2026-06-05 (`fieldkit v0.23.0` CUT + on PyPI; Kepler ship-tail closed — HF links, dup delete, test fix)
Closed the operator's "do 1, prioritize 3+4" queue. **Task 1:** added reader-facing `Orionfold/Kepler-GGUF` + `Orionfold/Kepler-bench` links to `articles/the-gate-before-the-gpu/` deliverable section (`871a654`; build green 518 pages, verifiers pass). **Task 4 (test fix):** `test_drain_arbiters_rl_run_with_progress_and_mem_trace` failed because `build_standup` reads the box's `~/.fieldkit/arena/autonomy.json` (armed `enabled:true`) → isolated it via `monkeypatch.setenv("ARENA_AUTONOMY_STATE", tmp)` (`a8acc1c`; test-only, 19/19 lane tests green). **Task 3 (release):** `fieldkit-curator` interactive — minor bump 0.22.0→**0.23.0** (new public kwargs + endpoint, backward-compatible, no schema/module change), offline test mode (GPU-free connective tissue; v0.21/v0.22 precedent). Gates: audit-docs 17/18 (1 pre-existing ArenaStore kwarg WARN, not this release) + audit-landing 4/4. Offline suite **1271 pass / 5 skip**. CHANGELOG `[Unreleased]`→`[0.23.0]` (+Fixed/Test-suite/Articles), commit **`3bda6df`**, tag `fieldkit/v0.23.0`, pushed. Both install-verifies green (git-source + PyPI). **PyPI upload user-authorized** → <https://pypi.org/project/fieldkit/0.23.0/>. Stats refreshed (`fieldkit` LOC 43,690→**44,392**; 53 articles) → `9885dc2`. The `[Unreleased]` block is now empty. (Task 2 — the F16 dup delete — done by operator.) | Manav (with Claude)

<!--
  Older entries pruned 2026-06-05 (keep ~2 latest). Recover any via `git log -p HANDOFF.md`. Pruned set, newest→oldest:
  - Kepler PUBLISHED (the three STEP-2 ship-tasks): T1 article the-gate-before-the-gpu (cf132a4, GateReadings.astro); T2 head-to-head (Kepler-Q8_0 84.1% local/$0 vs Haiku 97.7% / Gemini Flash-Lite 95.5%); T3 requant→4 GGUF (9dce32a)→hf-publisher Orionfold/Kepler-GGUF + Kepler-bench; AF-15 scorer_path threaded through eval/compare. be1ed2d tip. Summarized in the Current state block + the v0.23.0 entry above.
  - C6 STEP-1.5: AV-12 RL-headroom gate RAN (scripts/astro_bench/{transfer,gen_transfer,headroom_gate}.py); SFT agg 20.83% but BIMODAL per-family (0% = SFT-coverage gap, not RL headroom) → operator BRANCH 1 = ship the 86% SFT + methodology story (feedback_rlvr_headroom_gate); a49dff6. Fed the publish work above.
  - C5 full RLVR run = clean null (selected_step=0, in-loop held-out flat 0.9583) + C6 STEP-1(a) generalization 86.36%; encoded the RL-headroom gate (AV-12/RV-11, feedback_rlvr_headroom_gate); 2 cockpit bugs → AE-15/AE-16.
  - C4 wiring-complete + C5 4-step smoke PASSED (scorer_path hook; enqueue_rl.py; reward REAL pool 0.75–0.875 / held-out 0.958).
  - C2(b) SFT-init GATE PASS (held-out 86.36% vs base 12.5%, NeMo p65, ~11 min not multi-hour) + AF-10 live SFT cockpit feed.
  - Phase-C spec authored (_SPECS/astrodynamics-vertical-v1.md, AV-1…11 + AV-R1…R5); bench generator built (scripts/astro_bench/, 20 tests).
  - rl-lane-autonomy LA-1..16 BUILT + RELEASED (fieldkit v0.21.0 GPU backend, v0.22.0 LA-1..11 autonomy, LA-12..16 education layer 27efc11).
  - rlvr-loop-v1 / autonomous-harness-v1 / second-brain-pipeline-v1 / cost-plane-v1 ALL BUILT + RELEASED (fieldkit v0.18.0→v0.20.0); the whole pane→hands→engine roadmap is built + shipped.
  - Phase-3 editorial: the-machine-improves-itself deep-dive SHIPPED; living-model launch STAKED upcoming.
  - Phase-1 Arena launch article SHIPPED (products/arena-control-plane/, 606333d).
-->
