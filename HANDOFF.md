<!--
  Session handoff for ainative-business.github.io (Spark-operated monorepo).
  Convention:
  - Replace "Open items" each session; do NOT append.
  - "Recent decisions" is a short running log — keep ~2 latest, prune older.
  - Full history of any pruned entry is recoverable via `git log -p HANDOFF.md`.
  - Last pruned/reset: 2026-06-09 (Codex session start — stale completed open-item blocks and superseded runtime baselines pruned).
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

### 🔄 2026-06-09 — **Codex session opened; HANDOFF contract adopted**

> Codex read `HANDOFF.md` as the per-session continuity contract. Start every future Codex session by reading this file, use it as the live state handoff, update it at session end when work changes repo/runtime/public posture, and periodically prune completed or stale context while keeping recovery through `git log -p HANDOFF.md`. The Codex coexistence layer is committed as `ddb6626` and deliberately scoped: `AGENTS.md`, `CODEX-CC.md`, `.codex/`, `.agents/skills/`, and a narrow `.gitignore` exception for tracked Codex skills. Existing untracked `.claude/scheduled_tasks.lock` and `src/data/arena-mirror/` remain untouched. No Arena runtime was revalidated during the handoff-only update; the last recorded runtime state remains the 2026-06-07 post-AE-31 note below.

### ✅ 2026-06-07 — **AE-31 LIVE REP FIRED** (the v0.31.0 remaining gate): real guarded lane-launch from the LaneTruth form + UI teardown — **zero Arena-vs-actual discrepancies**

> The launch-runner cut is now validated end-to-end on a real run, narrated step-by-step (`feedback_arena_narrated_operator_smoke`):
> - **Recipe authored** — first operator lane recipe: `kepler-q8` (Q8_0 GGUF · `:8091` · ctx 8K · ngl 99) → `~/.fieldkit/arena/lane-recipes.json` (**kept** — future launches are one-click); `GET /api/lane-recipes` validated it live (`valid ✓ · gguf_present ✓`), no restart needed (per-request load).
> - **Launch from the form** (anchor-on-warm ticked): job `5419a336` — **pre-flight brake passed honestly** (114.69 GB available vs 16.09 GB estimated) → detached spawn pid 381072 (exact recipe argv) → **warm 6.0 s** → owner file atomic → discovery lit the rail (`ACTIVE LANE · resident · live`) + LaneTruth roster (`:8091 · ACTIVE · operator-selected`) → **run anchored** (`RUN · Kepler · armed just now`) — this also fires the queued **run-anchor-on-real-serve** gate.
> - **Lane really serves**: circular-velocity question → **7.67 km/s boxed, correct** (the pre-verified capture-class question).
> - **Teardown from the UI** — two-click confirm (a deliberate guard, found live) → job `caa0ada1`: `owner-killpg · freed 9.51 GB · pgid_empty · port_dead` (released **observed**, never asserted) · `owner_removed` · `registry_cleared` → **honest revert**: roster "No lane resident — arm one below", run-context `anchored:false · run_started:null`, no process (exact-name pgrep).
> - The 2 job rows kept as honest history. One false signal caught on my side, not Arena's: `pgrep -f llama-server` matching my own shell wrapper text (the `feedback_cdp_smoke_innertext_traps` class) — re-verified with `pgrep -x`.
> - Follow-on live exercises such as real armed `sft_run` drain, corpus-request fulfilment, metered cloud-eval teardown, GS-1 no-restart cap edit, and AE-10 candidate-base behavior are validation/test work for already-shipped surfaces, not Arena v2 spec-completion tasks.

### ✅ 2026-06-07 — **`fieldkit v0.31.0` RELEASED** — arena-enhancements **v2 cut 4**: **AE-31 guarded lane launch + teardown** (launch-runner cut, AE-R13) + demo recorder extensions

> Tag `fieldkit/v0.31.0` + <https://pypi.org/project/fieldkit/0.31.0/> (both install-verifies green; PyPI needed one CDN-lag wait, as usual). Commit `fd0b2e3` (version + CHANGELOG + docs catch-up). **Offline 1496 pass / 19 skip** (+51). **NO arena.db schema change** (`user_version` 6). The release packages the two already-committed-but-unreleased cuts:
> - **AE-31** (`ec8cd8e`) — `fieldkit.arena.launcher` (751 lines): `JobKind.LANE_LAUNCH`/`LANE_TEARDOWN` + `GET /api/lane-recipes`; operator-authored lane recipes → **pre-flight brake** (launch lock → recipe → binary → GGUF → memory envelope → fused one-lane/port check; a doomed launch never tears a working lane down) → detached spawn (survives sidecar restarts, atomic owner file) → **verified teardown** (owner-pid kill w/ PID-reuse guard, "released" observed never asserted). Refusals persist as honestly-failed rows (`refused:<reason>`). LaneTruth launch form + teardown buttons, BuildSpine lane wiring, JobsBoard launch cards. 1268 test lines incl. real-process `test_launch_process.py`.
> - **Recorder extensions** (`4abe639` fieldkit side) — 12 new sanitized stub endpoints, recursive `_scrub_str` host-path scrubber, `--stubs-overlay` showcase merge (23 tests, `test_fixtures.py`).
> - **Docs catch-up in the release commit**: `arena.md` JobKind row + a new AE-31 launcher section (the audit only checks `__all__`; launcher is a non-re-exported submodule — eyeballed per `feedback_audit_docs_kwarg_blind_spot`).
> - The operator-armed real guarded lane-launch gate fired in the 2026-06-07 live rep above.

### ✅ 2026-06-07 — **DEMO "FULL GLORY" + LINK SWEEP + SCREENGRAB SYNC** (operator-reported blanks/404s/dark-shots all fixed) · AE-31 launch cut committed

> Operator drove the public demo and found: blank feature panes (build/sft/reward/jobs/standup), "training flow" + "Measured on the Spark" 404s, and dark screengrabs on the LIVE product articles. All three classes fixed + regression-guarded.
> - **Demo simulated data (operator decision: simulated-from-past-runs, w/ disclaimer)** — `fieldkit arena record` records 12 NEW endpoint stubs (build/sft-progress/reward-signal/standup/jobs/leaderboard-live/active-lane/lane-recipes/guardrail-config/prices/corpus-progress/runtimes), sanitized by a new recursive host-path scrubber (`_scrub_str` — catches paths INSIDE `result_json`/`lineage_card` strings); a checked-in overlay `arena-app/arena-demo-sim/stubs.json` (+ its `assemble_overlay.py`) merges via the new `--stubs-overlay` flag (enriched jobs board w/ queued+running, standup queue, 3 lane recipes, Kepler `discovered:8091` active lane, Cortex before→after + 3 canned queries). `boot.js`: jobs SSE shim (named `jobs` events), **interactive dispatch simulation** (queued→running→done over ~6 s, cancel + check-regressions wired), per-endpoint fallbacks, ribbon now discloses "simulated data drawn from past real runs". NEW `fieldkit/tests/arena/test_fixtures.py` (23 tests; suite 449 pass).
> - **Link sweep** — root causes: the arena bake PRUNES `articles/` (live AND demo 404 every in-bundle article link) · TrainingFlow's `../sft/` escaped the base from the landing page · lab's local `href` lacked the strip-prefix → `/arena/arena/*`. Fixes: NEW `arena-app/src/lib/arena/article-url.mjs` (absolute `ainative.business/field-notes/<slug>/`, survives the deploy rebase) wired into EvidenceBand · lab · models/[slug] · cockpit baseline link · ⌘K command-index; TrainingFlow → `./sft/`; lab href fixed. NEW **`scripts/verify_arena_demo_links.mjs`** (walks deployed HTML, resolves every internal link on disk, guards the exact 404 classes + fixture leak scan + product-screenshot drift; runs against `public/arena/demo` AND `_webui`) — green on both.
> - **Operator UI fixes** — EvalBenchLive rendered RAW `lane_id` (the `local:` regression; now `laneModel`+`laneSuffix`+shared `SourceBadge.jsx`); `laneSource` also catches un-prefixed cloud ids (`claude-haiku-45` no longer badges "Spark GPU"); telemetry rail wrapped the OpenRouter cell to a 2nd row when the AE-23 Run cell appeared (fixed 7-track grid → `grid-auto-flow: column` one-row + nowrap labels); TrainingFlow understands the AV-10 preflight reward shape (`step-0 96%` instead of idle).
> - **Screengrab sync (the dark-shots root cause)** — the 2026-06-06 light re-capture never copied to **`public/products/`** (the SERVING dir per product-writer §134): orionfold-arena served STALE DARK, arena-control-plane was MISSING entirely (live 404s). Both synced. **orionfold-cortex re-captured light for real** (embedder `:8001` up → cockpit rebuild → real reindex+chained rag_eval (3rd run, recall@k 0.409 stable) → real query; 4 shots @2×, captions updated 313→328 provenance, 94→96% GPU, query swapped to the pictured one; 3 unused dark leftovers deleted). Drift now FAILS the verifier.
> - **Verified**: demo smoke (headless playwright) — all 13 panes render data, dispatch sim animates, chat replays, Cortex flips 93.9→100%, **0 console errors / 0 sidecar escapes**; live cockpit re-baked + restarted (rail one-row ✓ pills ✓); site build 518 pages + both verifiers ALL_OK; fixtures leak-grep 0.
> - **AE-31 committed** (`ec8cd8e`) — the prior session's in-flight guarded lane-launch cut (launcher.py + LaneTruth form + 1268 test lines) committed first so the shipped bakes match source.

### ✅ 2026-06-06 — **ARENA MARKETING RE-CAPTURE COMPLETE** (post-light-theme): all 22 product shots re-shot light + demo fixtures re-recorded + prose drift swept

> The "📸 QUEUED FIRST" task is DONE — every published arena capture in BOTH product articles now shows the light cockpit, with the v2 cut 1–3 features visible (inventory chips · LaneTruth roster · run-anchor cell · Arm-SFT form · Settings/guardrails · G3 price coverage).
> - **Capture rig**: headless `playwright-core` + `deviceScaleFactor:2` per `reference_marketing_screenshots_live_sse_2x` (the visible CDP Chromium was already dead — not needed). Kepler Q8 served on `:8091` for the session (discovered lane lit the rail/LaneTruth/chat/compare), torn down after.
> - **`products/arena-control-plane/screenshots/`** (11): 01–03 re-seeded with the launch-demo composition (6 rows w/ realistic hex ids — first pass leaked `seed-…` AE-16 id chips, re-seeded; seeds hard-deleted + API-verified after). 04–11 straight page shots off the real data.
> - **`products/orionfold-arena/screenshots/`** (11): 06-chat + 07-compare are REAL runs — **answers pre-verified against the lane before shooting** (first takes had Kepler flubbing a 550 km period (233.8 vs 95.6 min) and the GEO duel (7.3 vs 24 h) — known-drift adjacent; swapped to verified-correct questions: Kepler-3rd-law 97.0 min ✓, circular velocity 7.67 km/s ✓ vs Haiku 7.7 ✓ w/ the cost cards $0-local vs ~$0.0007). The two wrong-answer capture-drafts were deleted from arena.db (my runs, seed→revert); the operator's real smoke history kept.
> - **Prose swept**: arena-control-plane (rail lane Qwen3-30B→Kepler ×2) · orionfold-arena (chat 116 tok/s/30B→210 ms TTFT/Kepler-8B · compare local-vs-local→local-vs-hosted w/ cost card · rail memory numbers · frontier "gold"→"orange" ×6, light-theme Pareto line).
> - **Demo re-recorded**: `fieldkit arena record --max-chat 5 --max-compare 1` (curated: 2 correct Kepler chats + 2 vintage 30B chats + 1 Haiku + the verified velocity duel; sanitized stubs, no base_url/config leaks) → `ARENA_DEMO=1` build → `scripts/deploy_arena_demo.mjs` → `public/arena/demo/`. Static smoke ✓: shim active, light `#F7F8FA`, replay streams the fixture answer, **0 console errors / 0 sidecar calls**.
> - **Verified**: site build 518 pages + both verifiers ALL_OK. Session cloud spend ≈ **$0.003** (3 short Haiku duels).
> - ⚠️ **Residual dark surfaces** (the step-4 grep): `products/orionfold-cortex/screenshots/` (8 embeds — re-shoot needs the Second Brain stack UP (embedder `:8001` down) + seeded rebuild/drain/RAG states → **queued below**) · `articles/the-machine-manages-its-own-memory/` (5 evidence shots — historical record of that session, deliberately kept dark).

### ✅ 2026-06-06 — **LIGHT-ONLY THEME SHIPPED** (operator green-lit): marketing site + Arena cockpit restyled to `design-system-v1` (Airtable light, spark orange accent)

> The wholesale restyle the relay deferred was **green-lit and executed same-day** (operator: "switch to light theme as guided by the design spec"; scope answer: cockpit + marketing site, light-only). 21 files; both surfaces verified + operator-approved on a side-by-side review before commit.
> - **Mechanism**: `data-theme="light"` **pinned** on both `<html>`s (legacy light-scoped overrides became the permanent styles); toggles + FOUC scripts deleted (`ThemeToggle`×2, `ThemeScript`); three token layers rewritten to the spec palette — site `--color-*`/`--svg-*` (`src/styles/global.css`), arena copies (`arena-app/.../global.css`), and the cockpit's own `--arena-*` block (`ArenaAppLayout.astro`, flips the 5k-line cockpit sheet). `design-tokens.css` (§3 contract) now imported as source of truth. `color-scheme: light`, manifest + theme-color metas → `#F7F8FA`.
> - **~60 dark assumptions patched**: white-wash overlays → ink washes; black shadows → §2.4 elevations; lane colors `#76b900`/`#5b9cff` → `#338A17`/`#2750AE` (CompareDuel/LiveLeaderboard); FrontierScatter/TelemetryGauge → Airtable mids; rank badges → soft+ink pills; cmdk scrim; series-chip text → dark1 inks (§2.1 small-text rule); hero gradient → orange ramp. **Kept deliberately**: always-dark code blocks, reader-theme prefs (sepia/dark reading modes), modal scrims.
> - **Verified**: site build + both verifiers ALL_OK ×2; arena bake OK (caught a real `*/`-inside-comment CSS bug in design-tokens.css); cockpit restarted onto the light bake; CDP smoke 9/9 panes + 6 site routes, computed colors spot-checked on the wire. OG images regenerate light in CI (`build:og`).
> - ⚠️ Every published arena screen capture (22 shots across both product articles + the record→replay demo fixtures) now shows the OLD dark cockpit — **queued as the NEXT task** (see "📸 QUEUED FIRST" in Open items).

### ✅ 2026-06-06 — Relayed standards MERGED + ADOPTED (PR #5 from the Agency cockpit): `/dashboard` skill + design-system token contract

> **PR #5 squash-merged** (`f5d298b` — `_SPECS/design-system-v1.md` + `_SPECS/dashboard-skill-v1.md` + index registration; the second relay through the PR channel after the beacon). **Both specs implemented same-session:**
> - **`/dashboard` skill** — `.claude/skills/dashboard/SKILL.md`: thin operator-triggered *"show me the cockpit"* wrapper (launch-policy verbatim incl. the peers' SessionStart-rollback record; never auto-start). Launch = `:7866/healthz` check → `arena_lifecycle.sh up` (the repo's proven launcher — NOT a raw server line; root `/` 404s so the skeleton's bare-`/` probe was corrected to `/healthz`) → §4-detached `xdg-open` on `DISPLAY :1`. **Live-smoked:** piped launch line returned **0.008 s** (bar <1 s), tab landed in the visible Chromium. Heavy lifecycle (restart/down/CDP) stays with `arena-lifecycle`.
> - **Design-system §3 token contract** — `arena-app/src/styles/design-tokens.css` (neutrals · status · data-series · accent), **spark accent locked orange `#F7653B` / ink `#D74D26` / soft `#FEE2D5`** (distinct from self-health teal / self-wealth blue / agency purple). For **NEW operator-facing panes only** — not imported by `global.css`; the shipped Arena keeps its dark OKLCH theme (wholesale restyle = its own green-lit spec). Collision-scan vs `--color-*`/`--svg-*` namespaces clean.
> - `_SPECS/index.md` rows flipped RELAYED → **ADOPTED** with pointers.

### ✅ 2026-06-06 — `fieldkit v0.30.0` RELEASED — arena-enhancements **v2 cut 3**: **Cluster I core** (AE-26 inventory truth · AE-27 corpus handshake · AE-29 operator-armed sft_run · AE-30 runtime readiness)

> Tag `fieldkit/v0.30.0` + <https://pypi.org/project/fieldkit/0.30.0/> (both install-verifies green; PyPI needed one CDN-lag wait, as usual). Commits `4f71f27` (build, 17 files +1761) + `720dd16` (release) + `d25aba8` (stats). **Offline 1445 pass / 19 skip** (+26: `test_corpus_request.py`, `test_runtimes.py`, sft_run jobs/api, inventory). **NO arena.db schema change** (`user_version` 6). Every guarded-launch risk (AF-20 arming + AE-22 launch) deliberately deferred to the dedicated launch-runner cut (AE-R13). Live CDP smoke on the rebaked cockpit (seed→verify→revert; smoke rows + files fully reverted).
> - **AE-26 ✅ inventory truth (AF-19/OBS-2)** — manifest stages declare `artifacts: [{path, rows?, files?}]`; `GET /api/build` **verifies them on disk at read time** (exists · line-count vs claim · dir files · bytes · mtime) → per-stage `inventory` facet + `<BuildSpine>` chips. The tracked Kepler manifest declares the real corpus/bench/publish artifacts — the live chips read `600/600 ✓ · 120/120 ✓ · 44/44 ✓ · 8.7 GB ✓`. "DONE · 600 rows" can no longer be an unchecked assertion (P1). Binaries stat'd, never read.
> - **AE-27 ✅ corpus handshake (AF-22/OBS-3)** — `POST/GET/DELETE /api/corpus-request`: one atomic intent file beside the heartbeats (GS-1 pattern) the claude-corpus-synth session polls + fulfils (AE-R3 holds); fulfilment = a heartbeat newer than the request, **observed**. Producer liveness = heartbeat-mtime freshness (`live ◉ / ⚠ stale / done / none`, window `FK_ARENA_CORPUS_LIVE_S` 180 s) — "running but not stamping" finally distinguishable. Build-pane **Corpus handshake** block (request form · open state · withdraw). Smoke: UI request → synthetic heartbeat fulfilled (AE-6 strip lit from the same heartbeat) → withdraw → honest revert.
> - **AE-29 ✅ operator-armed `sft_run` (AF-21 dispatch half)** — `JobKind.SFT_RUN` + curated `mcp.run_sft_training(recipe_path, mode)` (`TrainRecipe.from_yaml` → `training.run`; the AE-25 heartbeat feeds the SFT pane free). **Armed twice over:** async-only at `POST /api/jobs` (the rl_run shape) + a **drain brake** — released to `queued` (audited `budget_defer`) unless the draining process exports `FK_SFT_RUN_ARMED=1`; `claim_next_job(skip_ids)` keeps a held job from starving the queue behind it. Jobs **Arm SFT run** form + `⏸ awaiting armed drain` cue + completion digest. Smoke: queued via the form, cue verified, cancel DELETE verified on the wire.
> - **AE-30 ✅ runtime readiness read-only (AF-20 observation half)** — `GET /api/runtimes`: lanes via AE-18 discovery · containers via one short-timeout `docker inspect` (`up/stopped/absent/unknown`; roster `FK_ARENA_RUNTIME_CONTAINERS` default `nemo-train,ps-train`) · pgvector/embedder via TCP; ~8 s cache (AE-R7). `<BuildSpine>` Runtimes roster — the live roster matched the box exactly (pgvector up · ps-train stopped · nemo-train absent · lane free · embedder down).

### ✅ 2026-06-06 — `fieldkit v0.29.0` RELEASED — arena-enhancements **v2 cut 2**: Cluster G **frontend** (AE-21 multi-lane truth · AE-22 select/pin) + Cluster H **run-context** (AE-23 run identity · AE-24 provenance chips + stale-dimming)

> Tag `fieldkit/v0.29.0` + <https://pypi.org/project/fieldkit/0.29.0/> (both install-verifies green; PyPI needed one CDN-lag retry, as usual). Commits `28c2a12` (build, 16 files +845) + `935ae6f` (release) + `b507445` (stats). **Offline 1419 pass / 19 skip** (+6, new `tests/arena/test_run_context.py`). **NO arena.db schema change** (`user_version` 6). Live CDP browser-smoke against the running cockpit with a synthetic llama-server-shaped lane on `:8091` (seed→verify→revert): discover → **pin · anchor run** → prior data dims → kill lane ⇒ drift → clear ⇒ honest revert.
> - **AE-23 ✅ run identity** — new `GET /api/run-context` (build-manifest vertical/label + reconciled lane); the **run anchor** = the instant the operator selects/arms a lane (`POST /api/active-lane` now stamps `set_at`, the spec AE-19 shape). Rail gains a global **Run** cell (`Kepler · armed 2m ago · model-Q8_0.gguf` / `lane live · select to anchor` / `unanchored · no lane armed`). **Honest when unanchored: no selection ⇒ no this-run/prior-run claims anywhere.**
> - **AE-24 ✅ provenance + stale-dimming** — shared `<ProvenanceChip>` (`run-id · age · live ◉ / prior ○`, the AE-16 pattern) on SFT/Reward/Build; Jobs cards + leaderboard live-eval rows label `○ prior run` + dim (hover restores) when stamped pre-anchor. `/api/sft-progress` runs gained `mtime` (parity w/ reward runs).
> - **AE-21 ✅ multi-lane truth** — new `<LaneTruth>` on Models (every discovered lane · active marked w/ winning source · **drift banner** · Hermes hint labelled "an assertion, not an observation" · honest "no lane resident — arm one" empty state); rail lane cell gains `⚠ drift` / `N lanes` badge; CurrentLane card gains source+drift chips, stale hermes copy dropped.
> - **AE-22 ✅ select half** — select a discovered lane (or **pin** the auto-active single lane: `pin · anchor run`) → AE-19 registry + run anchor; clear → pure discovery, un-anchored. **Launch half stays deferred (AE-R13).**
> - **BONUS FIX (real bug):** the registry **never participated in `_resolve_active_lane`** — the resolver was called without loading the registry file, so an operator selection was write-only (routing/rail ignored it; registry drift could never fire). The Cluster G smoke only exercised pure discovery so it slipped; the cut-2 endpoint tests caught it. Mock-blind strikes again (`dogfood_finds_mock_blind_bugs`).

### ✅ 2026-06-06 — `fieldkit v0.28.0` RELEASED — arena-enhancements **v2 cut 1**: Cluster G lane-truth + the e2e-smoke **bug-fix cluster** (BUG-1/2/3/4 + AF-27/28/29/30) — every smoke-harvested HIGH bug FIXED + live-smoked

> **The whole S1 harvest is closed.** Tag `fieldkit/v0.28.0` + <https://pypi.org/project/fieldkit/0.28.0/> (both install-verifies green; PyPI needed one CDN-lag retry). Commit `5e992ad` (32 files, +2739/−105) + stats `5c9941c`. **Offline 1413 pass / 19 skip** (+44). **NO arena.db schema change** (`user_version` 6). Each fix browser-smoked live in the running cockpit (seed→verify→revert, operator-approved):
> - **BUG-2 ✅** — G1 sentinels now trip from a **chained SIGTERM/SIGINT handler** (the lifespan trip deadlocked behind uvicorn's graceful drain — the circular wait) + a **startup reconciler** lands orphaned `running`/`dispatched` rows as `failed` w/ an honest error + teardown-shaped guardrail trail; an **owner-pid stamp** at the `running` flip keeps a live cron-drain's jobs untouched. Proven by a **real-process SIGTERM test** that holds the drain open exactly like a guarded eval (`test_signal_teardown_process.py`) AND live: a seeded orphan landed on a real cockpit restart.
> - **BUG-3/AF-29 ✅** — `price_for` resolves the **freshest** snapshot (pinned reads stay reproducible); `fieldkit.cost.fetch_openrouter_prices`/`refresh_prices` (dated snapshot, `source='openrouter-api'`); **price-at-dispatch capture** for unpriced cloud models (`FK_EVAL_PRICE_AT_DISPATCH=0` opts out); `GET /api/prices` + `POST /api/prices/refresh`; Settings **"G3 price coverage"** card; loud **`⚠ G3 unarmed · tokens-only`** Jobs badge (renders retroactively on the smoke's real unpriced R1 teardown eval). Live refresh captured REAL prices for the whole roster — and corrected the stale operator-manual deepseek-r1 row ($0.4/$2.0 → true $0.7/$2.5).
> - **BUG-4 ✅** — `[rl]` extra **ceiling-pinned to the proven GB10 stack** (`transformers>=4.51.3,<4.52` + `protobuf` + `sentencepiece` + `peft<0.20`); the 4-link drift chain + the shadow-model-dir recipe documented in `docs/api/rl.md` "Operator run".
> - **BUG-1/AE-25 ✅** — `fieldkit.training.run` stamps a **canonical `sft-progress-*.json` heartbeat** (checkpoint-liveness truth; `starting→running→done/failed→final`); `/api/sft-progress` reads it first-class (auto-follow spans heartbeats + driver logs; `canonical feed` chip). The exact OBS-1 failure now renders `DONE · iter 10/10`.
> - **AF-27 ✅** — rubric verdicts labelled by **scope** (`RubricSpec.scope="format"` → banner "Format check — not correctness", metrics row "Format", leaderboard `·fmt` qualifier); free prompts **auto-match registered bench rows** (`benches.find_prompt_by_text`) and score via the bench's **scorer_path verifier** — astro rows now load the registered verifier (`_registry_scorer_callable`) instead of honest-skipping. The smoke's "Dead heat — both 100%" while A was wrong ~2× can't recur.
> - **AF-28 ✅** — leaderboard projects **bench-anchored LIVE rows** from done `eval_rerun` jobs (`<EvalBenchLive>` over the existing `/api/eval/leaderboard`); cached mirror tier carries a `cached tier · <date>` staleness stamp. The smoke's real evidence (kepler-q8 0.85/54 · deepseek-r1 0.85/40 · haiku 0.89/19) now ranks live.
> - **AF-30 ✅** — `session_spend` + Standup `SpendDigest` fold in eval-job spend (`guardrail.run_cost_usd`, per-lane); SPEND reads $0.0538 w/ the cost-cap abort leading (was $0.0023/blind).
> - **Cluster G (AE-18..22 backend, `dd63802`) shipped in this same cut** — it predated v0.28.0 on main but was unreleased on PyPI; CHANGELOG now carries it.
> Test hygiene hardening: `create_app(db=None)` honors `ARENA_DB`; conftest pins `ARENA_DB`/`FK_EVAL_SENTINEL_DIR`/`ARENA_BENCH_DIR`/`FK_ARENA_OWNER_DIR` per-test — **no TestClient lifespan can ever touch the live store** (a pre-existing landmine the reconciler would have armed). Ledger statuses updated in `_IDEAS/arena-smoke-v2-features.md`.

### ✅ 2026-06-06 — Arena e2e operator-smoke **RUN S1 COMPLETE** (resumed post-reboot, post-Cluster-G) — **BOTH long-deferred AE-R1 gates FIRED on real runs**; 3 new HIGH bugs + 4 new findings harvested → **all fixed in v0.28.0 (above)**

> **The whole build→serve→review pipeline has now been walked end-to-end as one operator session.**
> Phase A pre-pause (A0 spine · scout · bench-provenance · corpus feed · REAL NeMo SFT smoke ·
> reward · gates ✓). The box **rebooted mid-pause**; resumed by re-arming (cockpit + CDP via
> `arena-lifecycle`, Kepler-Q8 lane re-served on `:8091`) — **Cluster-G survived the cold boot**:
> discovery found the re-served lane with no config (`source: discovered`, rail `ACTIVE LANE ·
> model-Q8_0.gguf · resident · live`), and after teardown honestly reverted to `configured · idle`.
> **Phase B (unblocked by AE-20 routing):** B2 chat streams from the *discovered* lane
> (`CHATTING WITH model-Q8_0.gguf · :8091/v1`), bench question scored **1.0** vs gold; B3 compare
> duel `local:resident` vs Haiku 4.5 (chips `$0·local` vs `$0.0018`); B4 leaderboard renders.
> **Phase C — the two operator-armed gates:**
> - **Guardrail AE-R1 ✅ G3** tripped on a REAL metered eval: cap $0.05 set via the Settings UI
>   (source=file, no restart) → Haiku × 44 rows aborted at row 19 with **$0.0515 genuinely accrued**
>   → badge `⚠ aborted · cost cap · partial · 19 scored · $0.0515 · cap $0.05/10m`. **✅ G1**
>   mechanism verified on a real metered R1 eval (sentinel → row-boundary abort → `teardown ·
>   partial · 3 scored` persisted → clean exit) — but the *trigger* is broken (BUG-2 below). G2 skipped per runbook.
> - **RL-lane AE-R1 ✅** — a REAL 4-step GRPO `rl_run` (`35ed71b9`, attempt 4) lit everything:
>   reward pane **auto-followed the live run** (`RUNNING · streaming · REWARD @ STEP-0 96%`), done
>   card `held-out step 0 (rl-000) · 0.958 · peak 92 GB` + **AE-9 lineage** `↑ corpus · sft-init ·
>   bench` + AE-2 degenerate-step truth (`adv_spread 0.0 · trained: false` — the expected
>   headroom-gate null, honestly rendered). vLLM lane cycled per step; teardown clean.
>
> **Session harvest (HIGH bugs, all root-caused, in the gitignored ledger
> [`_IDEAS/arena-smoke-v2-features.md`](_IDEAS/arena-smoke-v2-features.md) — READ IT next session):**
> - **BUG-2** — G1's trigger is a **circular wait**: uvicorn graceful shutdown waits for the eval
>   BackgroundTask before running `_lifespan`, but the eval only aborts when `_lifespan` writes the
>   sentinel. `arena down` can never fire G1 exactly when it matters; no restart reconciler either
>   (an orphaned job stays `running` forever). Fix: signal-handler trip + startup reconciler.
> - **BUG-3** — **G3 was silently inert in production**: `openrouter_price_snapshot` held only 2
>   stale h6-baseline rows → `price_for()=None` for every current lane → tokens-only, cap can never
>   trip, no surface says so. Fired only after an `operator-manual` price insert (deepseek-r1 +
>   claude-haiku-4.5 rows now in the table, provenance-marked, **kept**).
> - **BUG-4** — rl_run dep-drift, a 4-link chain: loose `[rl]` floor-pins + reboot-ephemeral /tmp
>   venv resolved transformers **5.10.2** (meta-tensor crash under `device_map="auto"` on GB10) →
>   4.57.6 (protobuf missing) → all qwen3-capable 4.x reject the NeMo-written **list-form
>   `extra_special_tokens`** (root-owned tokenizer_config.json) → **working combo: transformers==
>   4.51.3 + protobuf + sentencepiece + torch 2.12.0+cu130 + peft 0.19.1 + a shadow model dir**
>   (`merged-hf-bf16-fixed/` — symlinks + fixed config; **kept on disk**, `FK_RL_BASE_MODEL` points
>   at it; vLLM serves the original).
> - **AF-27** Compare rubric "Dead heat — both 100%" while lane A's value was wrong ~2× (format-regex
>   presented as QUALITY; propagates into the leaderboard) · **AF-28** eval_rerun scores never feed
>   the leaderboard (bench-anchored mirror stale 2026-05-28) · **AF-29** G3-armed? invisible ·
>   **AF-30** Standup budget governor blind to eval spend ($0.0023 shown vs ~$0.18 real).
> **Cluster-G is committed** (`dd63802` — the pause-block's "UNCOMMITTED" note is stale). Cloud
> spend this session ≈ **$0.18** (ceiling $1). **11 curated 2× screenshots** now in
> `products/arena-control-plane/screenshots/` (04–11 new: build/chat/compare/leaderboard/settings/
> jobs/reward/standup) — article-refresh candidates.

### ✅ 2026-06-06 — `fieldkit v0.27.0` RELEASED (`arena-guardrail-settings-v1` **GS-1…6**) — the operator-config surface over the AE-17 guardrails

> **`arena-guardrail-settings-v1` is BUILT + browser-smoked + RELEASED as `fieldkit v0.27.0`** (the whole GS-1…6 cluster in one cut). The post-v0.26.0 question *"where can I see the guardrails config in Arena?"* is answered: a new **Settings** pane (`/arena/settings/`, REVIEW/META nav group) **views + live-edits** the AE-17 eval-guardrail thresholds (per-run cost cap · stall window · `enabled` master toggle) with **no restart** — the arm path reads the config **per dispatch**.
> **`fieldkit v0.27.0`** — tag `fieldkit/v0.27.0` + <https://pypi.org/project/fieldkit/0.27.0/> (both install-verifies green). **GS-1 config core** — `fieldkit.arena.guardrail` gains `GuardrailConfig` + `load_config()` (file > env > default + per-field source provenance) + atomic `save_config()` + `DEFAULTS`/`BOUNDS`; `EvalGuardrail.from_env` now wraps the resolver (back-compat); `_run_eval_guarded` reads `load_config()` per dispatch + honors `enabled` (off ⇒ cloud lane runs unguarded, byte-for-byte the local-lane path); a corrupt config file falls back to env/default. **GS-2 config API** — `GET`/`POST /api/guardrail-config` (Pydantic body, 422 on bounds violation, operator-private — config is a file, never mirrored). **GS-3 Settings pane** — `settings.astro` + `<GuardrailSettings>` island (source chips · reset-to-default · `enabled` toggle · loud **"Cloud-eval guardrails OFF"** banner) + Settings nav tab; **GS-6** Jobs-card `<EvalGuardrailBadge>` appends `· cap $X / Nm` from the persisted `result_json.guardrail`. **NO arena.db schema change** (`user_version` 6) · **no skill imports** (AE-R3) · no route change elsewhere. Offline **1369 pass / 5 skip** (+16). Config file: `~/.fieldkit/arena/guardrail-config.json` (env-overridable `FK_EVAL_CONFIG_DIR`/`FK_EVAL_CONFIG_PATH`; toggle env `FK_EVAL_GUARDRAIL_ENABLED`). Commits `1b579fe` (build+release) + `a4d2b34` (stats), tag pushed, on PyPI. ▶ **REMAINING GATE (operator-armed):** the AE-R1-style live cloud-eval validation (edit a cap → confirm the next real metered cloud eval picks it up with no restart) lands when cloud evals resume — offline trips + the live CDP render-smoke were the session bar.

### ✅ 2026-06-06 — `fieldkit v0.26.0` RELEASED (arena-enhancements **S7 / AE-17 cloud-run guardrails**); **whole arena-enhancements cluster S1–S7 now built + released**; Kepler shipped

> **arena-enhancements is COMPLETE: S1–S7 are all built, browser-smoked, AND released across `fieldkit v0.24.0` (S1–S4) + `fieldkit v0.25.0` (S5–S6) + `fieldkit v0.26.0` (S7). The greenfield Kepler vertical remains published end-to-end.**
> **`fieldkit v0.26.0`** — tag `fieldkit/v0.26.0` + <https://pypi.org/project/fieldkit/0.26.0/> (both install-verifies green): **S7 / AE-17 cloud-run guardrails**.
> **S7 / AE-17 cloud-run guardrails** — a new `fieldkit.arena.guardrail.EvalGuardrail` wraps any metered cloud eval (non-loopback `base_url`) with **G1 teardown** (`_lifespan`/`arena down` trip the eval-abort sentinel for running `eval_rerun` jobs) · **G2 stall** (`FK_EVAL_STALL_TIMEOUT_S` default 600 s no-progress, reset per row) · **G3 cost** (`OpenAICompatClient.chat` `on_usage` → `PriceSnapshot.cost_usd` → `FK_EVAL_RUN_COST_CAP_USD` default $5 per-run cap). The `VerticalBench.run` row-loop polls a shared sentinel (the eval-side `abort_poller`); every run threads `result_json.guardrail` (`aborted_by`/`run_cost_usd`/`partial`/`n_scored`) → Jobs-card cost chip + abort badge (composes AE-16 + AE-2 + AE-13). **NO arena.db schema change** (`user_version` 6) · **no skill imports** (AE-R3) · a local lane runs byte-for-byte unchanged. Offline **1353 pass / 5 skip** (+38). Committed `85e4cfd`, tagged `fieldkit/v0.26.0`, on PyPI.
> **`fieldkit v0.25.0`** — tag `fieldkit/v0.25.0` + <https://pypi.org/project/fieldkit/0.25.0/> (both install-verifies green): **S5** provenance/lineage (AE-8 bench provenance card `GET /api/bench-provenance` · AE-9 rl_run upstream lineage) · **S6** wiring quick-wins (AE-10 scout→Compare `GET /api/scout` + `<ScoutPanel>` lock-time gate · AE-11 astro-bench registered in the Eval preview surface). **NO arena.db schema change** (`user_version` stays 6); both sessions are pure read-only projections, no skill imports (AE-R3). Offline **1315 pass / 5 skip**. `[Unreleased]` is now empty.
> `origin/main` is current through the v0.25.0 release + stats/HANDOFF refresh (commit `9bdbd11` cut the version; the stats+HANDOFF refresh follows it). Working tree clean
> except two pre-existing untracked items to **leave alone** (`.claude/scheduled_tasks.lock` = runtime lock; `src/data/arena-mirror/` = generated mirror).
> GitHub Pages auto-deploys on push to `main` → site is live at `ainative.business`.
> **`fieldkit v0.24.0`** — tag `fieldkit/v0.24.0` + <https://pypi.org/project/fieldkit/0.24.0/> (both install-verifies green): the arena-enhancements
> dogfood cluster — **S1** RL-run observability (AE-1/2/3/4/16) · **S2** information architecture & flow (AE-12/13/14/15) · **S3** build-spine
> backbone (AE-5) · **S4** live feeds & gates (AE-6 corpus feed · AE-7 gate ledger). **NO arena.db schema change** across the whole cluster
> (`user_version` stays 6); every signal lands in `result_json` / file-polled reports / panes / nav. Offline 1297 pass / 5 skip. `[Unreleased]` is now empty.
> Prior **`fieldkit v0.23.0`** (Kepler ship-tail; LA-12..16 + AF-15 scorer_path) remains on PyPI.

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

## ⚙️ Live runtime (post-AE-31-rep 2026-06-07 — cockpit UP in browser-use mode; GPU lane FREE)

> **Cockpit `:7866` UP** (restarted via `arena-lifecycle restart --browser`, OpenRouter key
> loaded) + **visible CDP Chromium `:9222` UP** (browser-use mode, parked on `/arena/models/`)
> — both left up. The kepler-q8 lane launched for the AE-31 rep was **torn down from the UI**
> — GPU lane FREE (~115 GiB headroom), run-context honestly unanchored. **NEW operator asset:**
> `~/.fieldkit/arena/lane-recipes.json` with the `kepler-q8` recipe (Q8_0 · `:8091` · ctx 8K) —
> kept; future launches are one-click from LaneTruth. `/tmp/arena-venv` fieldkit editable
> tracks source — reads **0.31.0**. **arena.db deltas (deliberate, kept):** +2 honest job rows
> from the rep (`5419a336` lane_launch done · `caa0ada1` lane_teardown done). Prior capture
> session's rows unchanged (chat `cs-d7611` + compare `cr-bdb44` + 14 real job rows).
> `openrouter_price_snapshot` still carries `or-refresh-2026-06-06` — G3 armed. Cloud spend
> this session **$0** (local lane only). No open corpus request; no sft_run rows.
> **Tear down when done:** `.claude/skills/arena-lifecycle/scripts/arena_lifecycle.sh down --browser`.

### Pruned runtime baselines

> Superseded 2026-06-06 post-smoke and pre-smoke runtime baselines were pruned on 2026-06-09. Recover via `git log -p HANDOFF.md` if forensic detail is needed.

## Build / verify

`node node_modules/astro/astro.js build` (~517 pages; `npm run build` is broken on this SMB checkout per `reference_astro_build_smb_symlink_break`) → `node scripts/verify_artifact_rendering.mjs` + `node scripts/verify_field_notes_rendering.mjs`. `build:og` is CI-only (needs Chrome). **arena-app/ + fieldkit/ build separately** from the marketing site — pushing arena/fieldkit changes does NOT change public `dist/`. **Secrets:** `.env.local` (gitignored, chmod 600) holds `PYPI_TOKEN`, `HF_TOKEN`, `OPENROUTER_API_KEY`.

## Open items (by swimlane)

### 🤝 Codex / Claude coexistence
- **Codex layer is committed** — current baseline is `ddb6626 chore(codex): add coexisting CLI contract`. Do not modify `.claude/` for Codex behavior unless explicitly requested.
- **HANDOFF contract for Codex** — read `HANDOFF.md` at session start, update it at session end when continuity changes, and prune stale completed detail periodically. Keep `CODEX-CC.md` for Codex/Claude interoperability changes.

### 🔬 Arena-enhancements v2 remainder
- **Arena v2 spec-completion work is now closed.** Cuts 1-4 are done + released, AE-31 live rep is done, and AE-28 landed as a narrow feed self-description/source-health disclosure on SFT, Reward, and Corpus. The broad operator-brief/checklist pane was reviewed and intentionally skipped as redundant. Operator-armed live gates remain validation/test work for shipped surfaces, not spec-completion tasks.
- Discipline unchanged: build and browser-smoke side by side in the running Arena over CDP; rebake `_webui` after `arena-app/` edits; no arena.db schema change unless a spec explicitly calls for it.

### ✍️ Editorial
- **Phase 2 launch** — `product-writer` launch for the built autonomous-harness cockpit surface (morning-standup, cron queue, budget-governor), cross-linking the H4 deep-dive.
- **Living-model launch** (`products/living-model/`, `status: upcoming`) — promote when a future RL-sensitive run produces real lineage delta data, or reframe honestly around the headroom-gate methodology. Do not edit `src/data/book/chapters/**` for MTBM book-overlay work; use `book_chapters` cross-links only.

### ⚙️ Operator-owned live infra
- Future live `rl_run`: install pinned `fieldkit[rl]` + pinned aarch64/CUDA-13 vLLM lane, set `FK_RL_*` via `scripts/astro_bench/fk-rl-env.sh`, then arm overnight drain when operator is ready. One-lane memory envelope still applies.
- `sudo chown` root-owned container-written dirs (`merged-hf-bf16`, `init-lora-r16`, HF-cache `models--Qwen--Qwen3-8B` stub).
- Second Brain: deploy the evidence server over `/home/nvidia/second-brain-mcp/server.py`, `pip install -e fieldkit` in its venv, and run first `/api/knowledge/reindex` to backfill schema/provenance.
- PSI authenticated key still missing; blocks PageSpeed in `/seo-monitor`.

### 📈 SEO
- Re-run `/seo-monitor` in the next 1-2 week window to confirm sitemap/indexing settlement. Keep GSC unused verification token `fePoYwMX...` as HOLD/do-not-remove. Journal in `seo-progress.md`.

### 🧹 Cleanup
- Human-eye/Lighthouse pass on LoRA/adapter/dataset detail + empty-state listing pages.
- Low-priority bakeoff gated-catalog footer last-write-wins issue.
- Patent-strategist W3 fine-tune follow-up when source-side work lands.
- Deprecate or replace the retired `sync-field-notes` skill body now that the monorepo cutover changed source paths.
- Optional: relocate the old Claude memory namespace symlink into this repo namespace for a cleaner cutover.

## Recent decisions (short running log — prune older)

### 2026-06-09 (Codex session start — HANDOFF contract adopted)
Codex read `HANDOFF.md` as the per-session continuity contract and recorded the rule: read at session start, update at session end when state changes, and prune stale completed detail periodically. Added a current-state note for the uncommitted Codex coexistence layer (`AGENTS.md`, `CODEX-CC.md`, `.codex/`, `.agents/skills/`, `.gitignore` exception), then pruned stale completed open-item blocks and superseded 2026-06-06 runtime baselines. No Arena runtime revalidation was performed in this handoff-only update. | Manav (with Codex)

### 2026-06-09 (AE-28 source-health disclosure built)
Completed the real value-add AE-28 slice: added a shared collapsed `FeedHealth` disclosure and wired it into SFT, Reward, and Corpus surfaces. It names source filename/kind, last stamp, producer, read path, poll cadence, and health state; the broad operator-brief/checklist pane was skipped as low ROI because provenance, runtime readiness, corpus liveness, and run-context are already surfaced in-place. Verified with site build + render verifiers, Arena `_webui` bake, cockpit restart in browser-use mode, and CDP smoke on `/arena/build/`, `/arena/sft/`, `/arena/reward/` (one feed-health disclosure each, expandable, zero console errors). | Manav (with Codex)

### 2026-06-09 (Arena v2 handoff pruning)
Arena v2 open-items were narrowed to real spec-completion work. Operator-armed live exercises (`sft_run` drain, corpus-request fulfilment, metered cloud-eval teardown, GS-1 cap edit, AE-10 candidate-base behavior) are validation/test work for shipped code, not open Arena v2 spec tasks. AE-28 was then completed as the narrow source-health disclosure recorded above. Also corrected the Codex coexistence baseline to committed `ddb6626`. | Manav (with Codex)

### 2026-06-07 (AE-31 live rep FIRED — zero discrepancies; recipe file is a kept operator asset)
The v0.31.0 remaining gate closed same-day: authored the first lane recipe (`kepler-q8` → `~/.fieldkit/arena/lane-recipes.json`, loaded per-request so no restart), launched from the LaneTruth form with anchor-on-warm (pre-flight 114.69 GB vs 16.09 est → warm 6.0 s → discovery lit → run anchored — the run-anchor-on-real-serve gate fired with it), verified real serving (7.67 km/s boxed, correct), tore down from the UI (two-click confirm — a guard discovered live, not a bug; `owner-killpg · freed 9.51 GB · port_dead observed`) → honest revert. Worth keeping: (1) the recipe file persists as an operator asset — future launches are one-click; (2) `pgrep -f` self-matches the CC shell wrapper's command text — verify process death with `pgrep -x` (the cdp-smoke-traps class, shell edition). Job rows kept as honest history. Spend $0. | Manav (with Claude)

<!--
  Older entries pruned 2026-06-07 (keep ~2 latest). Recover any via `git log -p HANDOFF.md`. Pruned set, newest→oldest:
  - arena marketing re-capture COMPLETE (2026-06-06): 22 light shots + demo re-record with headless playwright-core 2× (CDP dead, not needed); 2 quality gates kept — realistic hex seed ids (AE-16 chip renders id[:8]) + pre-verify live-model answers before shooting (Kepler flubbed 2/3 first capture questions; curl the lane first, delete wrong-answer drafts, keep operator history). Prose swept both articles; build 518 + verifiers ALL_OK; spend ≈ $0.003.
  - fieldkit v0.30.0 RELEASED (2026-06-06, v2 cut 3: Cluster I core — AE-26 disk-verified inventory facet, AE-27 corpus handshake + heartbeat liveness, AE-29 sft_run armed twice over (async-only + FK_SFT_RUN_ARMED brake + claim_next_job(skip_ids)), AE-30 runtimes observed): every launch risk deferred to cut 4 (AE-R13). Two CDP false-signals caught (uppercase innerText; vacuous scrollIntoView pass) by API/db verification. Commits 4f71f27+720dd16+d25aba8, tag fieldkit/v0.30.0, offline 1445/19, both install-verifies green.
  - fieldkit v0.29.0 RELEASED (2026-06-06, v2 cut 2: Cluster G frontend + Cluster H run-context): AE-23 /api/run-context + set_at run-anchor + rail Run cell; AE-24 ProvenanceChip + prior-run dimming (honest no-claims unanchored); AE-21 LaneTruth + drift badges; AE-22 select/pin half. Real bug found: _resolve_active_lane never loaded the registry (selection write-only; endpoint tests caught it). Live CDP smoke on synthetic :8091 lane seed→verify→revert. Commits 28c2a12+935ae6f+b507445, tag fieldkit/v0.29.0, offline 1419/19.
  - fieldkit v0.28.0 RELEASED (2026-06-06, v2 cut 1: Cluster G backend + the S1 smoke bug-fix cluster): BUG-2 signal-handler G1 trip + startup orphan-reconciler w/ owner-pid stamps + real-process SIGTERM test; BUG-3/AF-29 newest-row price_for + live OpenRouter refresh + /api/prices* + G3-coverage card + tokens-only badge; BUG-4 [rl] ceiling-pins + shadow-dir recipe; BUG-1/AE-25 canonical sft-progress heartbeat; AF-27 rubric scope labels + bench auto-match via scorer_path; AF-28 EvalBenchLive; AF-30 eval spend in session_spend. Test-hygiene: ARENA_DB conftest pins (tests could touch the real arena.db). Commit 5e992ad, tag fieldkit/v0.28.0, offline 1413/19, stats 5c9941c.
  - e2e operator-smoke S1 COMPLETE (2026-06-06): both AE-R1 gates FIRED on real runs — G3 cost-cap aborted a metered Haiku eval at $0.0515 accrued (19/44, badge+chip); G1 mechanism verified on a metered R1 eval (sentinel→abort→teardown·partial·3-scored→clean exit); real 4-step GRPO rl_run 35ed71b9 lit the reward gauge live (REWARD @ STEP-0 96% auto-follow) + AE-9 lineage + AE-2 degenerate-step truth (clean headroom null). 3 HIGH bugs root-caused live (BUG-2 G1 circular-wait · BUG-3 G3 silently inert/empty price table · BUG-4 RL dep-drift 4-link chain → transformers==4.51.3 + shadow dir) + AF-27..30; all fixed in v0.28.0. Cluster-G dd63802 verified cold post-reboot (discovery found the re-served lane w/ no config). C4/C5/C6 ✓; close-out: lanes torn down, autonomy left OFF, 11 curated 2× shots → products/arena-control-plane/screenshots/. Session cloud spend ≈ $0.18.
  - arena-guardrail-settings-v1 GS-1..6 BUILT + smoked + RELEASED as fieldkit v0.27.0 (2026-06-06): GuardrailConfig/load_config (file>env>default + provenance) + atomic save; GET/POST /api/guardrail-config (422 bounds); /arena/settings/ pane + GuardrailSettings island (source chips · reset · enabled toggle · loud OFF banner) + GS-6 jobs cap chip; per-dispatch config read = no-restart cap edits; offline 1369/5 (+16); live CDP smoke 11/11; commit 1b579fe, tag fieldkit/v0.27.0, PyPI + stats a4d2b34 (47,900 LOC). Per-job cap override answered: out of scope, global config only.
  - arena-enhancements S7/AE-17 cloud-run guardrails BUILT+smoked (EvalGuardrail G1/G2/G3, no schema change, offline 1353 pass, live CDP smoke w/ seeded+reverted rows) then cut as fieldkit v0.26.0 (85e4cfd, tag, PyPI, both install-verifies green); cluster S1-S7 feature-complete. AE-R1 live cloud validation → FIRED 2026-06-06 in the e2e smoke (see the smoke entry).
  - Agency cockpit status beacon adopted + `status-beacon` skill with TTL refresh: merged PR #4 (beacon contract → CLAUDE.md); wrote first _STATUS.json; status-beacon skill (.claude/skills/status-beacon/ + update_beacon.mjs) — 3 metric tiers (cheap recompute every run / manual carried-forward / expensive GSC+GA4 TTL-gated 7d off the `checked` clock); never fabricates, never blocks a commit; scrape = seo-monitor/scripts/scrape_cdp_fallback.mjs (puppeteer CDP attach to logged-in Arena Chromium :9222, read-only). Live reads: GSC indexed 24, sitemap submitted 183, GA4 7d users 69; fieldkit_modules 9→18 (canonical FIELDKIT_MODULES); models/software_released/arena_features (6/7/16) operator-defined. Run update_beacon.mjs at session end (--force post-deploy, --no-scrape mid-day).
  - `fieldkit v0.25.0` CUT + on PyPI (arena-enhancements S5–S6): minor 0.24.0→0.25.0 (new GET /api/bench-provenance + GET /api/scout + BenchSpec root override + astro-bench registration, no breaking); offline-only tests; audit-docs 17/18 + 1 skip, audit-landing 4/4; CHANGELOG→[0.25.0], offline 1315 pass; commit 9bdbd11, tag fieldkit/v0.25.0, https://pypi.org/project/fieldkit/0.25.0/; both install-verifies green; stats 46,966 LOC. user_version 6.
  - arena-enhancements S6 BUILT + browser-smoked + RELEASED in v0.25.0 (wiring quick-wins; AE-10 / AE-11): AE-10 scout→Compare — new `GET /api/scout` projects the newest hf-model-scout report (report.md ranked picks joined by repo with candidates.json traps) → collapsed `<ScoutPanel>` on Compare + lock-time behavioral-gate framing; serving a candidate stays operator (one-lane AE-R4). AE-11 astro-bench preview — registered `astro-bench` in `fieldkit.arena.benches` via a `root_env`/`root_fallback` BenchSpec override + `fmt="astrodynamics"` loader (split→family, tier/subtopic/split facets + inline gold); interactive grading honest-skips (astro_numeric_match scores via the eval-job scorer_path). `serve()` now exports ARENA_REPO_ROOT (non-reload). Offline 1315 pass/5 skip (+12). Commit 47aeb16. Live CDP smoke 13/13.
  - `fieldkit v0.24.0` CUT + on PyPI (arena-enhancements S1–S4): minor 0.23.0→0.24.0 (new write_corpus_progress + /api/corpus-progress + /api/build across S1–S4, no breaking); offline-only tests; audit-docs 17/18, audit-landing 4/4; CHANGELOG→[0.24.0], offline 1297 pass; commit 8bfe9e1, tag fieldkit/v0.24.0, https://pypi.org/project/fieldkit/0.24.0/; both install-verifies green; stats 3aac2e2 (46,124 LOC). user_version 6.
  - arena-enhancements S5 BUILT + browser-smoked (provenance / lineage; AE-8 / AE-9): AE-8 bench provenance card — `_bench_provenance()` + `GET /api/bench-provenance` reads pool + held-out JSONL (+ SFT-init queue) → version · counts · RV-10 disjointness (pool ∩ held-out set check) · tier/topic mix · self-verifying-gold count · corpus held-out-exclusion proof (queue ∩ held-out); rides the `/api/build` bench stage as `provenance`, `<BuildSpine>` renders the card, `FK_ARENA_BENCH_DIR` anchors the dir. AE-9 rl_run upstream lineage — `_persist_rl_run` threads corpus/SFT-init/bench upstream into `result_json.upstream` (loop summary else enqueue payload; `enqueue_rl.py` stamps `corpus_slug`/`sft_init`), Jobs board renders `↑ corpus · sft-init · bench`. No schema/skill-import (AE-R3). Offline 1303 pass/5 skip (+6 tests). Commit 80b0d9a. Released in fieldkit v0.25.0.
  - arena-enhancements S4 BUILT + browser-smoked (live feeds & gates; AE-6 / AE-7): AE-6 corpus-synth live feed — new producer stamper `fieldkit.arena.lane.write_corpus_progress` (AF-9/AF-10 heartbeat) reads `out.jsonl` vs `queue.jsonl` → `corpus-progress-<slug>.json` (written/target · batch-verify · `family_mix` · ETA); new `GET /api/corpus-progress` mirrors `/api/sft-progress`; build-spine corpus stage reads it live + `<BuildSpine>` corpus strip. AE-7 build-gate cards — default `gate_consequence` per gated stage (manifest-overridable) + gate ledger (allow/hold/pending). No schema/route/skill-import (AE-R3). Offline 1297 pass/5 skip (+9 tests). Commit cbdc332. Released in v0.24.0.
  - arena-enhancements S3 BUILT + browser-smoked (build-spine backbone; AE-5 / AF-1): new `GET /api/build` assembles eight C1..C6 stage cards (scout·bench·corpus·SFT·smoke·lane·RLVR·publish) as a pure projection over existing feeds + an optional `build-manifest.json` (env `FK_ARENA_BUILD_DIR`); live-feed state/headline/detail win, gate/href + no-feed stages manifest-owned. Frontend `build.astro` + `<BuildSpine>` (5s poll) + Build tab. Tracked Kepler `build-manifest.json` (7/8 done). No schema/skill-import (AE-R3). Offline 1288 pass/5 skip (6 tests). Commit 0d2246b. Released in v0.24.0.
  - arena-enhancements S2 BUILT + browser-smoked (information architecture & flow; AE-12/13/14/15): AE-12 two-tier flow nav (Build/Train→Serve/Infer→Review/Meta, `--arena-bar-h` var, URLs unchanged AE-R5); AE-15 telemetry lane-truth (`_resident_live` TCP probe + `_read_active_gpu_lane` reader → "Configured Lane · idle", kills the Qwen3-30B-always-active lie, 5 tests); AE-13 `TrainingFlow` island (SFT→Reward→RL) + Jobs↔Standup boundary notes + `$0·local` Compare chip; AE-14 Reward/Standup purpose reframing. Deferred AE-13a (→S5) + AE-14c (needed S3). No schema/route change. Offline 1282 pass/5 skip. Commit 9fb1875.
  - arena-enhancements S1 BUILT + browser-smoked (RL-run observability; AE-1/2/3/4/16): `fieldkit.rl` `_emit` widened keep_rate/n_used/adv_spread/trained (AE-2) + RLLoop.step_history[] + summary() step_history/selected_exp_id (AE-3/4); `fieldkit.arena.lane` reward_signal_writer (AE-1, av10-shaped→reward_rate_step0) on progress_cb; jobs._persist_rl_run threads fields; JobsBoard.jsx GRPO row + "no update — zero advantage" badge + (rl-<step>) pointer + card-identity. No arena.db schema change. Offline 1277 pass/5 skip (6 new tests). Live smoke ✓ (seeded synthetic running+done rl_run, deleted after). Commit 60273cb. Live reward-gauge end-to-end stays operator-armed AE-R1.
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
