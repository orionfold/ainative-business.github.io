<!--
  Session handoff for ainative-business.github.io (Spark-operated monorepo).
  Convention:
  - Replace "Open items" each session; do NOT append.
  - "Recent decisions" is a short running log — keep ~2 latest, prune older.
  - Full history of any pruned entry is recoverable via `git log -p HANDOFF.md`.
  - Last pruned/reset: 2026-06-05 (full prune — stale Phase-C in-flight detail removed after Kepler shipped).
-->

# HANDOFF — ainative-business.github.io

> 📌 **PINNED — arena-enhancements build discipline.** Every arena-enhancements session (S1…S7)
> **builds AND browser-smokes side by side in the *running* Arena over CDP** — bring the cockpit up
> in browser-use mode (`arena_lifecycle.sh up --browser` → `:7866` + CDP Chromium `:9222`), rebake the
> `_webui` after any `arena-app/` edit (`fieldkit arena build --repo-root arena-app`), then drive the
> live panes (Jobs / Reward / Standup) and confirm the change renders before calling a decision done.
> Discrepancies are same-session fixes (`[[feedback_side_by_side_review_after_major_features]]`).
> The live `rl_run` GPU gate (AE-R1) stays operator-armed — offline tests + a live browser-smoke of the
> render/transport are the session bar; the real RL validation lands on the next armed run.

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

- **Arena cockpit UP** (`:7866`, OpenRouter key loaded) + **visible CDP Chromium UP** (`:9222`, browser-use mode) — **restarted 2026-06-05 onto the S1+S2-rebaked `_webui`** (serves AE-1/2/3/4/16 + AE-12/13/14/15); **left up**. `arena.db` has **0 running/queued jobs**, **7 done jobs** (the 2 synthetic S1-smoke rows were deleted after the smoke). Kepler eval results preserved on the board: `kepler-q8-gguf` **0.86/44**, `deepseek-r1` **0.84/37**. ⚠️ The visible Chromium caches hashed JS — if the board looks pre-S1, hard-reload / CDP `Network.clearBrowserCache` (the served HTML already points at the fresh `JobsBoard.BHICGzWJ.js`).
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

### 🔧 Arena dogfood — `arena-enhancements-v1` — BUILD STARTED 2026-06-05 (spec §6 breakdown; S1 IN PROGRESS)
The payoff from running Kepler's pipeline live through the cockpit. Spec `_SPECS/arena-enhancements-v1.md` (§6 = the canonical session map); gitignored ledger `_IDEAS/arena-dogfood-feature-extraction.md`. **No arena.db churn** (everything lands in `result_json`/file-reports/panes/nav; `user_version` stays 6). Release gate ~`v0.24.0+`. Astro C6/Kepler has shipped → the build gate is **lifted**; executing the §6 breakdown session by session, RL-observability first. Each session closes to the pinned discipline (tests + `_webui` rebake + live browser side-by-side). **Operator gave the go-ahead to take up S1 (2026-06-05).**

- **✅ S1 — RL-run observability (BUILT + SMOKED 2026-06-05; CHANGELOG `[Unreleased]`, not yet released):** AE-1 reward gauge wired to the live `rl_run` (new `lane.reward_signal_writer`+`_reward_signal_dir`, composed onto `progress_cb` in `_run_rl_arbitered`; writes an `av10-preflight`-shaped report → gauge key `reward_rate_step0`, env dir `FK_ARENA_REWARD_DIR`→`ARENA_REPO_ROOT/evidence/astrodynamics`) · AE-2 degenerate-step visibility (`_emit` carries `keep_rate`/`n_used`/`adv_spread`/`trained`; `<RlProgress>` GRPO row + "no update — zero advantage" badge) · AE-3 `RLLoop.summary().step_history[]` threaded through `_persist_rl_run` · AE-4 `selected_exp_id` (`rl-<step>`) back-pointer rendered on the done card · AE-16 Jobs-card identity (relative time + short id + rl_run run-label). **NO arena.db schema change** (`user_version` 6), no new route, backward-compatible. **Offline: 1277 pass / 5 skip** (6 new tests in `test_rl.py` + `tests/arena/test_lane.py`). `_webui` rebaked + cockpit restarted; **live side-by-side browser-smoke ✓** (seeded synthetic running+done rl_run, confirmed the badge / `step 12 (rl-012)` / `34-step·24.4h ago·08e6cca7` vs `4-step·25.4h ago·ac8739be` renders, then deleted the seed rows). ▶ REMAINING GATE: the **live reward-gauge lighting end-to-end** is the *next* armed `rl_run` (astro re-run / vertical #2, operator-armed AE-R1). ▶ S2 now built on top (see below).
- **✅ S2 — Information architecture & flow (BUILT + SMOKED 2026-06-05; CHANGELOG `[Unreleased]`, not yet released):** AE-12 two-tier flow-based nav (Build/Train → Serve/Infer → Review/Meta lifecycle groups; URLs unchanged, every tab reachable) · AE-13 data-flow corrections (new `TrainingFlow` cockpit-landing card stitching SFT→Reward→RL into one chain off existing endpoints; Jobs↔Standup cross-link boundary notes; `$0·local` Compare cost chip) · AE-14 purpose redefinition (Reward = cross-stage scorable-output gauge spanning SFT-init + live rl_run; Standup = overnight RL-digest + promote gate; cockpit body card "Active lane"→"Resident lane · configured") · AE-15 telemetry lane-truth (`resident_live` TCP liveness probe + `_read_active_gpu_lane` arbiter reader in `server.py`; rail relabels the idle config as **"Configured Lane · idle"** instead of falsely claiming Qwen3-30B active). **NO arena.db schema change** (`user_version` 6), **no route change** (AE-R5). **Offline 1282 pass / 5 skip** (+5 AE-15 tests in `test_server.py`); `_webui` rebaked + cockpit restarted; **live side-by-side browser-smoke ✓** (two-tier nav all-tabs-reachable; rail CONFIGURED LANE on the idle box; training-flow card reads SFT `done·100 iters`→Reward `gate PASS`→RL `held-out 96%` off residual data; boundary cross-links resolve jobs↔standup). ▶ DEFERRED: **AE-13a** leaderboard-row→job link (aggregate rows strip per-run provenance + no job-detail route → folds into **S5** provenance) · **AE-14c** Lab→build threading (needs the S3 `/arena/build/` pane). ▶ AE-15's positive RL-lane label is live-validated on the next armed `rl_run` (AE-R1). ▶ NEXT: cut `fieldkit v0.24.0` (curator) when ready, or proceed to **S3** (AE-5 `/arena/build/` pane).
- **S3 — Build-spine backbone:** AE-5 `/arena/build/` pane (into the new Build/Train nav group).
- **S4 — Live feeds + gates:** AE-6 corpus-synth live feed · AE-7 build-gate cards.
- **S5 — Provenance / lineage:** AE-8 bench provenance card · AE-9 rl_run lineage threading (corpus/SFT/bench upstream).
- **S6 — Wiring quick-wins:** AE-10 scout top-3 → Compare (+ lock-time behavioral gate) · AE-11 bench preview (register `astro-bench v0.1` in Eval).
- **S7 — Cloud-run guardrails (safety; MAY pull forward ahead of S1 if cloud evals resume):** AE-17 `EvalGuardrail` on metered cloud lanes — **G1** teardown-abort (`_lifespan`/`arena down` aborts an in-flight cloud eval cleanly) · **G2** stall-timeout (`FK_EVAL_STALL_TIMEOUT_S` default 600 s no-progress) · **G3** per-run cost cap (`FK_EVAL_RUN_COST_CAP_USD` default $5, live `usage`→`PriceSnapshot`). Env-config + tracked in `result_json`. Motivated by the qwen3-8b OpenRouter eval that hung ~2.5 h (Body 4). GATE: a deliberately-slow/capped cloud eval that trips each condition + a teardown mid-run.

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

### 2026-06-05 (arena-enhancements **S2 BUILT + browser-smoked** — information architecture & flow; AE-12/13/14/15)
Operator: "read handoff and continue" → took up **S2** (the IA refresh, queued after S1). Built all four S2 decisions to the pinned discipline (build AND browser-smoke side-by-side in the running cockpit over CDP). **AE-12** two-tier nav (the flat 11-tab row overflowed + read as a list → regrouped into Build/Train → Serve/Infer → Review/Meta lifecycle clusters on a 2-row bar driven by a `--arena-bar-h` var so the sticky rail offset follows; first single-tier attempt clipped LAB/CORTEX → two-tier fixed it; URLs unchanged, AE-R5). **AE-15** telemetry lane-truth (`server.py`: `_resident_live` cached TCP probe + `_read_active_gpu_lane` injected store-decoupled reader → payload `resident_live`/`active_lane_*`; rail reconciles in-flight→RL/external→live-resident→warm→**"Configured Lane · idle"** for the idle config, killing the "Qwen3-30B always active" lie; cockpit body card relabelled too; **5 new tests**). **AE-13** training-flow `TrainingFlow` island (SFT→Reward→RL chain off `/api/sft-progress`+`/api/reward-signal`+`/api/jobs`, graceful idle) + Jobs↔Standup cross-link boundary notes + `$0·local` Compare cost chip. **AE-14** Reward/Standup purpose reframing (leverage not rebuild). **Deferred:** AE-13a (leaderboard→job link — aggregate strips provenance + no job route → S5) + AE-14c (Lab→build → needs S3 build pane). **NO arena.db schema change** (`user_version` 6), no route change. **Offline 1282 pass / 5 skip**; `_webui` rebaked, cockpit restarted (browser-use), **live smoke ✓** (all tabs reachable; rail honest on the idle box; training-flow reads `done·100 iters`→`gate PASS`→`held-out 96%`; cross-links resolve). CHANGELOG `[Unreleased]` now carries **S1+S2** (not yet released — next: cut `v0.24.0` or proceed to S3). Cockpit left **up**. | Manav (with Claude)

### 2026-06-05 (arena-enhancements **S1 BUILT + browser-smoked** — RL-run observability; build STARTED, session-by-session)
Operator: "read handoff + the arena-enhancements spec → work-breakdown session by session, update HANDOFF, take up S1" (+ "pin a note in HANDOFF & memory: build AND browser-smoke arena enhancements in the running arena side by side"). Transcribed spec §6 into the HANDOFF as the live S1…S7 plan + pinned the build discipline (top of HANDOFF + new `[[project_arena_enhancements_build]]`). The astro-C6/Kepler ship **lifted the build gate**, so took up **S1 (AE-1/2/3/4/16)** — all within `result_json`/file reports, **no arena.db schema change** (`user_version` 6), no new route, backward-compatible. `fieldkit.rl`: `_emit` widened with `keep_rate`/`n_used`/`adv_spread`/`trained` (AE-2), `RLLoop.step_history[]` captured live + `summary()` adds `step_history` + `selected_exp_id` (AE-3/AE-4); `fieldkit.arena.lane`: new `reward_signal_writer`+`_reward_signal_dir` (AE-1, av10-shaped report → gauge key `reward_rate_step0`), composed onto `progress_cb` in `_run_rl_arbitered`; `jobs._persist_rl_run` threads the new fields; `JobsBoard.jsx` renders the GRPO row + "no update — zero advantage" badge (AE-2), the `(rl-<step>)` pointer (AE-4), and the card-identity row (AE-16) + matching CSS in `ArenaAppLayout.astro`. **Offline 1277 pass / 5 skip** (6 new tests). `_webui` rebaked, cockpit restarted (browser-use), **live side-by-side smoke ✓** over CDP (seeded a synthetic running+done rl_run → confirmed the badge, `held-out step 12 (rl-012)`, and the two real Body-3 runs now distinguishable `34-step·24.4h` vs `4-step·25.4h`; deleted the seed rows, board restored to 7). CHANGELOG `[Unreleased]` carries S1 (**not yet released** — next: cut `v0.24.0` or proceed to S2). The live reward-gauge-lighting end-to-end stays the operator-armed AE-R1 gate. Cockpit left **up** (browser-use). | Manav (with Claude)

<!--
  Older entries pruned 2026-06-05 (keep ~2 latest). Recover any via `git log -p HANDOFF.md`. Pruned set, newest→oldest:
  - post-release (arena venv→0.23.0 · in-cockpit eval-dispatch VERIFIED via browser-use · OpenRouter runs shut down · AE-17 guardrail spec): refreshed /tmp/arena-venv to 0.23.0; verified AF-15 scorer_path dispatch live (kepler-q8-gguf 0.86/44, deepseek-r1 0.84/37; same boxed completion 0.0 built-in vs 1.0 bench scorer); qwen3-8b OpenRouter eval hung ~2.5h → killed + 0 OpenRouter jobs; motivated AE-17+Cluster F (G1 teardown/G2 stall FK_EVAL_STALL_TIMEOUT_S=600/G3 cost FK_EVAL_RUN_COST_CAP_USD=$5; spec only, operator hold). Commits 81b37b9 + handoff.
  - `fieldkit v0.23.0` CUT + on PyPI (Kepler ship-tail): T1 HF links to the-gate-before-the-gpu (871a654); T4 test fix ARENA_AUTONOMY_STATE isolation (a8acc1c); T3 curator minor bump 0.22.0→0.23.0 (3bda6df, tag fieldkit/v0.23.0, https://pypi.org/project/fieldkit/0.23.0/), offline 1271 pass; stats 9885dc2. Summarized in the Current state block.
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
