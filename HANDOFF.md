<!--
  Session handoff for ainative-business.github.io (Spark-operated monorepo).
  Convention:
  - Keep this file short: current state, live runtime, build/verify, open items, and ~2 recent decisions.
  - Do NOT append completed history. Prune closed tasks aggressively; full history is recoverable via `git log -p HANDOFF.md`.
  - Last pruned/reset: 2026-06-09 (Claude compacted the Advisor probe narrative into a receipt-history bullet and trimmed Recent Decisions).
-->

# HANDOFF — ainative-business.github.io

> 📌 **PINNED — Arena build discipline.** Any `arena-app/` or `fieldkit.arena` work that changes the cockpit must be built and browser-smoked side by side in the running Arena over CDP: bring the cockpit up in browser-use mode (`arena_lifecycle.sh up --browser` -> `:7866` + CDP Chromium `:9222`), rebake `_webui` after `arena-app/` edits (`fieldkit arena build --repo-root arena-app`), then drive the live panes and confirm the change renders. Live `rl_run` validation stays operator-armed; offline tests + live render/transport smoke are the normal session bar.

> 📌 **PINNED — Arena pipeline discipline.** For Advisor/Arena/fieldkit pipeline work, the visible Arena cockpit is the operating surface and system of record. Use browser-use mode first for lane launch/teardown, active-lane selection, chat/compare/eval observation, jobs, run-context, and screenshots. Do **not** replace Arena operation with headless browser scripts, hidden endpoint batch scoring, or terminal-only API calls. If a needed step is not possible in Arena, perform only the minimum deterministic terminal action and log it as an `AD-AE-*` or `AD-FK-*` dogfood finding.

## Current State

### 2026-06-09 - Orionfold Advisor NVIDIA-native proof (active)

- Workstream: `_SPECS/orionfold-advisor-nvidia-native-v1.md` (v1.2, flagship Advisor — harness + model + retriever + corpus pack + Arena workspace, NVIDIA-native first, governed OpenRouter overflow); `_SPECS/orionfold-local-ai-workbench-v1.md` is the separate Arena/fieldkit Workbench track. Unsloth-era specs (`orionfold-advisor-unsloth-arena-v1.md`, `orionfold-advisor-dogfood-v1.md`) are superseded planning history; existing `advisor-*` proof ids and AD-AE/AD-FK findings remain canonical.
- Tracked pre-GPU evidence under `evidence/orionfold-advisor/`: `scripts/orionfold_advisor/generate.py` writes domain-gate/source-audit, `public-corpus-manifest.jsonl` (181 public-safe sources with `source_role` + `book_surface` metadata for Books 1–3; private/operator state excluded), and the bench seed (103 rows, 28 frozen held-out, ≥15 refusal/private-state cases — an eval seed, not SFT data).
- RAG/recall gate green on BOTH lanes: local BM25 `score_recall.py` → `rag-recall-v0.1.json` (source_recall@5 = 0.9885 all rows, 1.0 held-out answerable) AND the live Cortex stack `score_recall_live.py` → `rag-recall-v0.1-cortex.json` (pgvector `advisor_corpus_v01` + `llama-nemotron-embed-1b-v2` NIM, cosine dense: **0.977@5 overall, 1.0 held-out answerable, 1.0@10 everywhere; @1 0.8506 vs BM25 0.7471**). The §14 "retriever recall remains green on public corpus" pre-publish condition is met on the live lane; 2 pool misses@5 (0004, 0076) recover @10. `blog_chunks` untouched (own table per OA-NV-8).
- Advisor preflight harness: `preflight.py` builds 8 balanced held-out packets and scores a local OpenAI-compatible lane; the Cortex card (`GET /api/advisor/preflight`, `POST /api/advisor/preflight/run`) exposes lane readiness plus `run preflight` / `run /no_think` controls; `-nothink`-suffixed evidence preserves the reasoning-on receipt. `--reasoning-mode off` applies BOTH the Nano 9B `/no_think` system token AND `chat_template_kwargs={"enable_thinking": false}` (Nemotron-3/Qwen3-style templates) — models ignore the control they don't use. The private-state scorer ignores long tokens echoed from the packet's own prompt (0087 false positive fixed); novel secrets still flag.
- §13.C raw-floor receipt history, all run through visible Cortex (receipts overwrite `advisor-preflight-v0.1*.json` in place; priors in git history): Qwen2.5-7B Q5_K_M 4/8 → 5/8 after boundary tightening (comparison baseline); Nano 9B v2 NIM 0/8 default (7/8 thinking leak) → 1/8 `/no_think` (0 leak); Nemotron-3-Nano-30B-A3B Q8_0 0/8 default (8/8 leak) → 5/8 `/no_think` → **7/8 after the bounded exemplar-format pass (one exact-citation + one refusal-sentence example in the tracked system prompt) — meets the §14 ≥7/8 pre-SFT bar, 0 leak, 0 private-state risk**. Both SFT-shaped classes (source-id aliasing, bare refusals) resolved by prompt contract; all five answer rows cite distinct exact ids (format generalized beyond the exemplar token; weak confound noted — the exemplar id coincides with 0074's expected id, but 0074 also cites a non-exemplar id). Sole remaining failure: 0082 over-refuses an answerable question with its expected source at retrieval rank 1 (same grounding over-refusal class Nano 9B showed). One iteration only — no further prompt tuning. The receipt gate itself (8/8) is still failed/non-publishable; no base is *selected*, but 30B-A3B now leads on floor.
- 30B-A3B probe mechanics (current lane): lmstudio-community Q8_0 GGUF (33.6 GB) at `/home/nvidia/data/quants/Nemotron-3-Nano-30B-A3B/`; local llama.cpp `856c3ad` supports `nemotron_h_moe`; recipe `nemotron3-nano-30b-q8` launched via guarded LaneTruth (job `61bdb23c`, warm 14 s, pinned on warm). NVIDIA-native metadata scout: `/tmp/hf-scout/2026-06-09/advisor-nvidia-native/`.
- **§13.F routing probe DONE** (`scripts/orionfold_advisor/route_bakeoff.py` → `evidence/orionfold-advisor/advisor-route-bakeoff-v0.1.{json,ledger.jsonl}`): T1-only **26/28 (92.9%)** on the FULL frozen held-out — refusals 16/16, 0 leak, 0 private-state risk, so the 0082 over-refusal class is **not systematic** (the wider-slice condition for SFT re-entry was checked and not met). Deterministic observables-only router escalated exactly 1 row (0082); route accuracy 27/28 (sole miss = 0040 wrong-citation, the undetectable class). T3 Ultra-550B ($0/NGC) and T4 Claude Haiku 4.5 ($0.0022 under the $1 cap, allowed-list) **both also refused 0082 on the same context** → the sole §13.C failure is reclassified as excerpt-window/bench drift, not model over-refusal; quality delta 0 points at both hosted tiers. Next quality lever is excerpt/retrieval granularity, not the generator. T2 skipped honestly (no larger local lane on disk).
- Browser-use evidence staged under `/tmp/orionfold-advisor-dogfood/` (latest: `arena-build-advisor-spine-2x.png` — marketing-grade 2x full-page Build pane retaken AFTER the AD-AE-15 fix, intended for future articles/product pages; prior Cortex 7/8 + lane shots also there). Open dogfood findings are tracked in Open Items (AD-AE-11/12, AD-AE-16, WB-11; AD-AE-13 built; AD-AE-14/15 FIXED).

### 2026-06-09 — Codex coexistence baseline adopted

- Codex reads `HANDOFF.md` at session start and updates it at session end when live state, public artifacts, release posture, or the status beacon changes.
- Codex coexistence layer is committed at `ddb6626 chore(codex): add coexisting CLI contract` and scoped to `AGENTS.md`, `CODEX-CC.md`, `.codex/`, `.agents/skills/`, and the `.gitignore` exception for tracked Codex skills.
- Do not edit `.claude/` for Codex behavior unless explicitly requested. Existing untracked `.claude/scheduled_tasks.lock` and `src/data/arena-mirror/` are operator/Claude/generated state; leave them alone unless the task targets them.

### 2026-06-07 — Arena/fieldkit latest shipped baseline

- Latest fieldkit release: `fieldkit v0.31.0`, tag `fieldkit/v0.31.0`, PyPI live. It includes AE-31 guarded lane launch/teardown and demo recorder extensions. No arena.db schema change (`user_version` 6).
- AE-31 live rep fired successfully: first operator lane recipe `kepler-q8` was authored, launch from LaneTruth passed pre-flight, lane served correctly, and UI teardown honestly released the lane. Recipe file is a kept operator asset at `~/.fieldkit/arena/lane-recipes.json`.
- Arena v2 spec-completion work is closed. The planned end-to-end new-model Arena run is the next readiness proof and should cover the relevant shipped-surface validations as one flow: corpus handoff -> training drain -> manifest/publish -> lane launch/inference -> Arena score/provenance. Metered cloud-eval, GS-1 cap edits, AE-10 candidate-base checks, and RL drain are only in scope if that run explicitly needs them.
- Public Arena demo and product screenshots were repaired after the light-theme pass; link sweep and render verifiers were green at the last recorded Arena release session.

### Published Baseline To Preserve

- Kepler model: <https://huggingface.co/Orionfold/Kepler-GGUF> with 4 GGUF variants; Q8_0 is recommended; F16 deliberately not published.
- Kepler bench: <https://huggingface.co/datasets/Orionfold/Kepler-bench>.
- Article: `articles/the-gate-before-the-gpu/`.
- Headline held-out numbers: Kepler-Q8_0 84.1% local/$0/166 mean tokens on the 44-row external curveball; Claude Haiku 4.5 97.7%; Gemini 3.1 Flash-Lite 95.5%. Per-variant held-out: Q4 75%, Q5 75%, Q6 84.1%, Q8 88.6%, F16 ref 86.4%.
- Known drift: `hohmann_transfer` and `altitude_from_period` remain honest SFT-coverage gaps.

## Live Runtime

Last recorded runtime baseline: Advisor Nemotron-3-Nano-30B-A3B visible preflight, 2026-06-09.

- Cockpit `:7866` is up in browser-use mode; visible CDP Chromium `:9222` was driven for the 30B lane launch, all Cortex preflight runs, the Advisor build-spine smoke, and the post-AD-AE-15 Build-pane screengrab. Last restart pids: cockpit `1161843` (restarted again 2026-06-09 evening to pick up the AD-AE-15 RLVR vertical-scope fix; plain `restart` leaves the browser alone), browser `957106`. `.env.local` now carries `FK_ARENA_BUILD_DIR`/`FK_ARENA_CORPUS_DIR`/`FK_ARENA_SFT_DIR`/`FK_ARENA_REWARD_DIR` pointed at the Advisor proof — remove or repoint when the active vertical changes (Kepler's reward/build panes read astro dirs again once unset).
- Codex sandbox workaround: localhost/CDP probes can fail inside sandbox (`EPERM` or false DOWN status). Use escalation for read-only `arena_lifecycle.sh status --browser`, CDP attach, screenshots, and `up --browser` if `/tmp/arena-venv` rebuild needs dependency downloads. Keep screenshots attached with `defaultViewport: null` so the operator-resized real browser window controls framing.
- Current GPU lane: llama-server `nemotron3-nano-30b-q8` on `:8091` (launched via LaneTruth job `61bdb23c`, pid `1071764`), serving `NVIDIA-Nemotron-3-Nano-30B-A3B-Q8_0.gguf` at ctx 8192 with `--jinja`. Pinned in LaneTruth as source `registry`; the global run context still says Kepler/astrodynamics (AD-AE-14). The `fk-nim-8000` Nano 9B NIM container is **stopped** (restartable via `docker start fk-nim-8000`). Recipe persisted in `~/.fieldkit/arena/lane-recipes.json`.
- `/tmp/arena-venv` fieldkit editable tracked source and read `0.31.0` at last check.
- Live recall gate side-state: pgvector container (up, operator-owned) now also holds the Advisor corpus pack in table `advisor_corpus_v01` (637 chunks; rebuildable any time via `score_recall_live.py`). The `nim-embed-nemotron` embedder container was started for the run and **stopped** afterward (restartable via `docker start nim-embed-nemotron`, serves `:8001`).
- Kept arena.db deltas: two honest job rows from the AE-31 rep (`5419a336` lane_launch done, `caa0ada1` lane_teardown done) plus Advisor Qwen2.5 teardown job `58d9df18` (`:8091` torn down, 8.68 GB freed). Prior capture rows remain as history.
- `openrouter_price_snapshot` still carries `or-refresh-2026-06-06`; G3 was armed at last check. No open corpus request and no `sft_run` rows.
- Tear down when done: tear down the `:8091` lane from visible LaneTruth (or `kill 1071764`) before starting another model lane, then `.claude/skills/arena-lifecycle/scripts/arena_lifecycle.sh down --browser` if the cockpit/browser should close too.

## Build / Verify

Website verification preference:

```bash
node node_modules/astro/astro.js build
node scripts/verify_artifact_rendering.mjs
node scripts/verify_field_notes_rendering.mjs
```

Notes:

- `npm run build` is documented as broken on this checkout; use direct Astro unless you verify the state has changed.
- `build:og` is CI-only because it needs Chrome.
- `arena-app/` and `fieldkit/` build separately from the marketing site. Pushing arena/fieldkit source changes does not update public `dist/` by itself.
- Privacy gate before commits: `.codex/hooks/secret_scan.sh --cached`. Secrets live in `.env.local`.

## Open Items

### Codex / Claude Coexistence

- Keep Codex project settings under `.codex/` and repo skills under `.agents/skills/`.
- Log any new Codex/Claude interoperability changes in `CODEX-CC.md`.
- Keep `HANDOFF.md` compact; prune completed history instead of appending.
- Codex sandbox health: Ubuntu AppArmor `bwrap-userns-restrict` is loaded and `codex sandbox /bin/true` / `codex sandbox pwd` / `codex sandbox bash -lc 'printf ok'` pass as of 2026-06-09. Syntax is `codex sandbox <command>` (older `codex sandbox linux <command>` examples are stale). If `bwrap: loopback: Failed RTM_NEWADDR` failures recur, the fallback is `[features] use_legacy_landlock = true` — do not enable it unless the AppArmor profile stops working.
- Codex Arena browser-use workaround is recorded in `.agents/skills/arena-lifecycle/SKILL.md`; localhost CDP/status checks may need escalation even for read-only inspection.

### Strategy / Growth

- **Orionfold Advisor NVIDIA-native proof**: execute `_SPECS/orionfold-advisor-nvidia-native-v1.md` as the next publish-grade small run. Default domain = Advisor over the public Orionfold corpus, and the product unit is harness + model + retriever + corpus pack + Arena workspace. Use NVIDIA-native models/runtimes/training first; use Arena/fieldkit for corpus import, lane launch, eval, routing/cost ledger, RL headroom decision, provenance, and publish/reject receipt. Respect the one-lane DGX Spark memory envelope.
- Immediate Advisor proof next step: §13.F routing probe DONE; live-lane recall gate DONE (receipt above — `rag-recall-v0.1-cortex.json` PASSED, the pre-publish recall condition is met). Remaining order: (1) excerpt/retrieval granularity pass — the routing probe showed the next quality lever is the 900-char query-centered excerpt window (0082's rank-1 source never showed the relevant passage), so consider larger/multi excerpts per source before touching the generator; (2) optional cheap probe of `NVIDIA-Nemotron-3-Nano-4B-BF16` (OA-NV-2) with the same GGUF-recipe + exemplar prompt as a trainable dense fallback. 0040's wrong-citation class suggests a deterministic harness check (cited id ∉ retrieved set / rank sanity) as future routing input. AD-AE-14 is FIXED: operator-authored `evidence/orionfold-advisor/build-manifest.json` + `FK_ARENA_BUILD_DIR`/`FK_ARENA_CORPUS_DIR`/`FK_ARENA_SFT_DIR`/`FK_ARENA_REWARD_DIR` anchors in `.env.local` (sourced by `arena_lifecycle.sh`) — run context, build spine, and bench provenance now say Advisor/advisor-bench through the visible cockpit.
- During the run, carry forward the existing `AD-FK-*` fieldkit and `AD-AE-*` Arena findings into the Workbench/Advisor task breakdown rather than treating the superseded dogfood spec as the active plan. Treat terminal-only workarounds as dogfood findings unless they are expected external setup. Current concrete Arena findings: `AD-AE-11` for missing manifest/bench/recall visibility (extended 2026-06-09: corpus-pack pgvector ingest + the live recall gate also have no Arena surface — spec §10 corpus pane plans it; `score_recall_live.py` ran as the minimum deterministic terminal action), `AD-AE-12` for missing base-model scout/preflight visibility, `AD-AE-13` built for preflight receipt/lane-readiness/execution, `AD-AE-14` FIXED (Advisor run-context via build-manifest + FK_ARENA_* env anchors), `AD-AE-15` FIXED in fieldkit `[Unreleased]` (build-spine RLVR stage now vertical-scoped by result-carried identity — payload `bench_id` prefix or result `vertical`/`domain`; 3 new tests in `tests/arena/test_build_spine.py`, 462 arena tests green; live Advisor spine shows RLVR pending instead of Kepler's 96%), **`AD-AE-16` NEW: no Arena routing surface — the §13.F probe's route decisions/tier/cost ledger ran as a deterministic script (`route_bakeoff.py`) per the minimum-action rule; spec §12 already plans the route-tier/ledger panes**, and Workbench `WB-11` because visible LaneTruth can discover/pin NIM lanes but cannot launch them through the guarded UI.
- Do not create public Advisor positioning until the NVIDIA-native model scout, corpus-pack shape, and Arena workspace gates have produced a publishable receipt.

### Editorial

- Phase 2 launch: use `product-writer` for the built autonomous-harness cockpit surface (morning standup, cron queue, budget governor), cross-linking the H4 deep dive.
- Living-model launch (`products/living-model/`, `status: upcoming`): promote only when a future RL-sensitive run produces real lineage delta data, or reframe honestly around headroom-gate methodology. Do not edit `src/data/book/chapters/**` for MTBM book-overlay work; use `book_chapters` cross-links only.

### Operator-Owned Live Infra

- Planned end-to-end new-model Arena run: use current `fieldkit v0.31.0` / Arena, respect the one-lane DGX Spark memory envelope, and validate the actual training-to-inference path before adding a new release or public proof. Only arm `rl_run` with pinned `fieldkit[rl]`, aarch64/CUDA-13 vLLM, and `FK_RL_*` env if the run is RL-sensitive.
- `sudo chown` root-owned container-written dirs when needed: `merged-hf-bf16`, `init-lora-r16`, HF-cache `models--Qwen--Qwen3-8B` stub.
- Second Brain: deploy evidence server over `/home/nvidia/second-brain-mcp/server.py`, `pip install -e fieldkit` in its venv, and run first `/api/knowledge/reindex` to backfill schema/provenance.
- PSI authenticated key still missing; blocks PageSpeed in `/seo-monitor`.

### SEO

- Re-run `/seo-monitor` in the next 1-2 week settlement window to confirm sitemap/indexing. Keep GSC unused verification token `fePoYwMX...` as HOLD/do-not-remove. Journal in `seo-progress.md`.

### Cleanup

- Human-eye/Lighthouse pass on LoRA/adapter/dataset detail pages and empty-state listing pages.
- Low-priority bakeoff gated-catalog footer last-write-wins issue.
- Deprecate or replace the retired `sync-field-notes` skill body now that the monorepo cutover changed source paths.
- Optional: relocate the old Claude memory namespace symlink into this repo namespace for a cleaner cutover.

## Recent Decisions

### 2026-06-09 - §13.F routing probe: local floor is frontier-equivalent on this slice; quality lever moves to retrieval

Ran the route bakeoff over the full 28-row held-out from the live 30B-A3B lane. T1-only 26/28 with refusals 16/16 and zero leak/private-state risk; the deterministic observables-only router (private-state egress gate + escalate on error/format/non-private-refusal) escalated exactly the one detectable failure. Both governed hosted tiers — NVIDIA Ultra-550B teacher ($0) and OpenRouter Claude Haiku 4.5 ($0.0022, capped, allowed-list) — refused the same row on the same retrieved context, reclassifying the sole §13.C failure as excerpt-window/bench drift rather than model over-refusal: quality delta 0 points. Consequences: SFT stays deferred (over-refusal not systematic on the wider slice), and the next quality investment is retrieval/excerpt granularity, not the generator. | Manav (with Claude)

### 2026-06-09 - Advisor / Workbench pivot adopted

Created two replacement specs after Orionfold's NVIDIA Inception selection changed positioning: `_SPECS/orionfold-advisor-nvidia-native-v1.md` for the flagship **Orionfold Advisor** product and `_SPECS/orionfold-local-ai-workbench-v1.md` for Arena/fieldkit as the local AI Workbench. Advisor v1.2 is packaged as harness + model + retriever + corpus pack + Arena workspace, with swappable customer corpora and governed hosted-SOTA/OpenRouter overflow. Dropped Unsloth from the default plan; it can re-enter only after a measured NVIDIA-native baseline. Preliminary search says probe Nemotron Nano 9B/4B and Nemotron-3-Nano-30B-A3B first, with Qwen3 and gpt-oss-20b as comparison baselines. | Manav (with Codex)

