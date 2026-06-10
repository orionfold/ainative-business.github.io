<!--
  Session handoff for ainative-business.github.io (Spark-operated monorepo).
  Convention:
  - Keep this file short: current state, live runtime, build/verify, open items, and ~2 recent decisions.
  - Do NOT append completed history. Prune closed tasks aggressively; full history is recoverable via `git log -p HANDOFF.md`.
  - Last pruned/reset: 2026-06-09 (Codex compacted completed Arena/fieldkit release history and stale completed task blocks).
-->

# HANDOFF — ainative-business.github.io

> 📌 **PINNED — Arena build discipline.** Any `arena-app/` or `fieldkit.arena` work that changes the cockpit must be built and browser-smoked side by side in the running Arena over CDP: bring the cockpit up in browser-use mode (`arena_lifecycle.sh up --browser` -> `:7866` + CDP Chromium `:9222`), rebake `_webui` after `arena-app/` edits (`fieldkit arena build --repo-root arena-app`), then drive the live panes and confirm the change renders. Live `rl_run` validation stays operator-armed; offline tests + live render/transport smoke are the normal session bar.

> 📌 **PINNED — Arena pipeline discipline.** For Advisor/Arena/fieldkit pipeline work, the visible Arena cockpit is the operating surface and system of record. Use browser-use mode first for lane launch/teardown, active-lane selection, chat/compare/eval observation, jobs, run-context, and screenshots. Do **not** replace Arena operation with headless browser scripts, hidden endpoint batch scoring, or terminal-only API calls. If a needed step is not possible in Arena, perform only the minimum deterministic terminal action and log it as an `AD-AE-*` or `AD-FK-*` dogfood finding.

## Current State

### 2026-06-09 - Codex Linux sandbox repaired

- Operator installed/loaded the Ubuntu AppArmor `bwrap-userns-restrict` profile for bubblewrap after Codex tools intermittently failed with `bwrap: loopback: Failed RTM_NEWADDR: Operation not permitted`.
- Verified fixed in this repo: `codex sandbox /bin/true` exits cleanly, `codex sandbox pwd` prints `/home/nvidia/ainative-business.github.io`, and `codex sandbox bash -lc 'printf ok'` prints `ok`.
- Syntax note for current local CLI (`codex-cli 0.138.0`): use `codex sandbox <command>`. Older issue/docs examples using `codex sandbox linux <command>` are stale here and try to execute a command named `linux`.
- If sandbox failures recur after a Codex restart, next fallback is the known Codex GitHub workaround `[features] use_legacy_landlock = true`; do not enable it unless the AppArmor profile stops working.

### 2026-06-09 - Advisor proof-start evidence generated

- Began the Orionfold Advisor proof with deterministic, tracked pre-GPU evidence under `evidence/orionfold-advisor/`. This workstream is now pivoted away from Unsloth and toward the NVIDIA-native flagship Advisor plan in `_SPECS/orionfold-advisor-nvidia-native-v1.md`.
- `scripts/orionfold_advisor/generate.py` now writes and validates: `domain-gate.json`, `source-audit.json`, `public-corpus-manifest.jsonl`, `advisor-bench-v0.1.jsonl`, and `advisor-bench-v0.1.heldout.jsonl`.
- Domain gate winner: **Orionfold Advisor**. Corpus manifest currently contains 181 public-safe sources; upcoming articles/products, proof-control specs, handoff/status/operator state, and private config paths are excluded.
- Corpus manifest corrected after v0.1: `src/pages/docs/**` / `https://ainative.business/docs/` is now included as Book 3 / **AI Native Platform** source. Manifest rows now include `source_role` for every source and `book_surface` metadata for Book 1 / **AI Native Business** (`src/data/book/chapters/**`), Book 2 / **AI Research on NVIDIA DGX Spark** (published Field Notes), and Book 3 / **AI Native Platform** (`src/pages/docs/**`). `https://orionfold.com/books/` remains reference/CTA, not primary training evidence.
- Advisor bench seed: 103 total rows, 28 frozen held-out rows, with >=15 refusal/private-state cases and source-id validation. This is an eval/source-boundary seed, not SFT training data.
- RAG/recall gate added: `scripts/orionfold_advisor/score_recall.py` writes `rag-recall-v0.1.json` and `rag-recall-v0.1.predictions.jsonl`. Local BM25/provenance-chunk baseline over the 181-source manifest passed: all rows source_recall@5 = 0.9885, held-out answerable source_recall@5 = 1.0, 16 refusal rows excluded from recall denominators. Only top-5 miss is one pool workflow-routing row for `doc_fieldkit_docs_api_memory_md`; it is recovered by top-10.
- Earlier HF-only Advisor scout artifacts remain under `/tmp/hf-scout/2026-06-09/advisor-8B/`, but that scout is now superseded by the NVIDIA-native weighting in `_SPECS/orionfold-advisor-nvidia-native-v1.md`. Keep Qwen-family results as comparison baselines and use the failed Qwen2.5 preflight receipt as evidence that the old route is not the product path. Browser-use gap logged as `AD-AE-12`: Arena stayed parked on Cortex because the cockpit has no visible base-model scout/preflight artifact surface yet.
- Arena browser-use is now up for the Advisor proof. Cortex pane smoke confirmed the local Advisor manifest/bench/recall receipt is **not** visible in Arena yet; logged concrete dogfood finding `AD-AE-11` in `_SPECS/orionfold-advisor-dogfood-v1.md`. Retaken Cortex screenshot at the operator-resized real browser window is staged at `/tmp/orionfold-advisor-dogfood/cortex-no-advisor-recall.png`.
- Advisor retrieved-context generator preflight harness added: `scripts/orionfold_advisor/preflight.py` writes balanced held-out prompt packets and can score a local OpenAI-compatible endpoint for deterministic artifact generation, but live validation must be driven through the visible Arena cockpit. Current tracked packet receipt: `evidence/orionfold-advisor/advisor-preflight-v0.1.json` plus `advisor-preflight-v0.1.prompts.jsonl` (8 rows across cited QA, artifact, book, workflow routing, operator recommendation, Unsloth/Arena separation, and 2 refusal cases). Logged Arena visibility/lane-readiness gap `AD-AE-13`.
- 2026-06-09 browser-use continuation: Qwen3-8B was converted locally to GGUF and launched through Arena/fieldkit LaneTruth on `:8091`, then replaced via guarded `teardown_first` with official `Qwen/Qwen2.5-7B-Instruct-GGUF` Q5_K_M shards on `:8091` after Qwen3 visibly failed behavior checks. Current visible Arena lane is `qwen2.5-7b-instruct-q5_k_m-00001-of-00002.gguf`; run context is anchored in Arena, but still labeled Kepler/astrodynamics because Advisor has no first-class run-context surface yet.
- Browser-use evidence staged under `/tmp/orionfold-advisor-dogfood/`: `arena-current-visible-qwen25.json/png` and `arena-visible-qwen25-safe-refusal-turn.json` plus before/after screenshots. Visible Chat refused a safe private-config-token disclosure prompt with `Citations: []`. Do not claim the full 8-row Advisor batch preflight passed; continue in Arena and treat missing Advisor eval/preflight UI as the blocking dogfood gap.
- 2026-06-09 continuation built the first visible Advisor preflight receipt surface in Arena: `GET /api/advisor/preflight` reads `evidence/orionfold-advisor/advisor-preflight-v0.1.json` plus packet metadata, and `/arena/cortex/` now shows the Advisor preflight card (8 packets, Qwen3 target, `not_run`, 0 scored results). Baked with `/tmp/arena-venv/bin/fieldkit arena build --repo-root arena-app`, restarted Arena in browser-use mode, and smoked the live Cortex card. Evidence: `/tmp/orionfold-advisor-dogfood/arena-cortex-advisor-preflight-card.json/png`.
- Visible Chat smoke on Qwen2.5 fallback ran one cited-factual Advisor packet (`advisor-cited-factual-qa-0003`) and returned `Citations: [article_autoresearchbench_on_spark]` with no thinking leakage. This is single-turn manual evidence only, not an 8-row preflight pass. Logged `AD-AE-14` because the result is still a chat turn and the cockpit run context remains labeled Kepler.
- 2026-06-09 continuation added the visible Advisor preflight execution path in Arena: `GET /api/advisor/preflight` now reports active-lane readiness, `/arena/cortex/` shows the active Qwen2.5 lane and a `run preflight` control, and `POST /api/advisor/preflight/run` runs the tracked preflight script against Arena's active lane and returns the redacted scored receipt. Baked with `/tmp/arena-venv/bin/fieldkit arena build --repo-root arena-app`, restarted Arena in browser-use mode, and smoked live Cortex. Evidence: `/tmp/orionfold-advisor-dogfood/arena-cortex-advisor-run-control.png`.
- The visible Advisor preflight was executed through Cortex against Qwen2.5 fallback on `:8091`. It wrote `evidence/orionfold-advisor/advisor-preflight-v0.1.results.jsonl`; the initial gate was **failed**, not publishable: 8 rows scored, 4 passed, 4 failed. Failing rows: `advisor-cited-factual-qa-0003`, `advisor-artifact-release-facts-0034`, `advisor-workflow-routing-0065`, and `advisor-missing-source-refusal-0088`. Evidence: `/tmp/orionfold-advisor-dogfood/arena-cortex-advisor-scored-failing-run.png`.
- 2026-06-09 continuation diagnosed the failures and reran the gate twice through the visible Cortex `run preflight` control. `scripts/orionfold_advisor/preflight.py` now clarifies private/local-state refusal boundaries, tells packets to cite exact `source_id` values, tolerates harmless trailing punctuation on citation lines, and avoids treating citation source ids as private-token risk. Current tracked receipt remains **failed**, not publishable: 8 rows scored, 5 passed, 3 failed. Remaining failures are `advisor-operator-recommendations-0074` (`Source 2` alias instead of `product_orionfold_cortex`) and both missing-source refusal rows (`Citations: []` only, no refusal sentence). Live Cortex renders `scored` / `8 rows` / `3 failing`. Evidence: `/tmp/orionfold-advisor-dogfood/arena-cortex-advisor-rerun-after-boundary-instructions.png`.
- Revised NVIDIA-native metadata scout is staged at `/tmp/hf-scout/2026-06-09/advisor-nvidia-native/`. It ranks `nvidia/NVIDIA-Nemotron-Nano-9B-v2` as first probe, `nvidia/NVIDIA-Nemotron-3-Nano-4B-BF16` as fast Spark-native probe, and `nvidia/nemotron-3-nano-30b-a3b` as larger serve-only/T2 probe. Qwen3 and `openai/gpt-oss-20b` remain comparison baselines. This is not a live behavioral pass; next proof step is to tear down the Qwen2.5 lane through Arena/LaneTruth, serve the first Nemotron candidate, and run the 8-row Advisor preflight through visible Cortex.
- 2026-06-09 continuation tore Qwen2.5 down through visible LaneTruth (`lane_teardown` job `58d9df18`, `:8091` dead, 8.68 GB freed), started cached `nvidia/nemotron-nano-9b-v2-dgx-spark` NIM on `:8000` with fieldkit `NIMLane`, pinned it in visible Models/LaneTruth, and ran the 8-row Advisor preflight through visible Cortex. Current tracked receipt is **failed**, not publishable: 8 rows scored, 0 passed, 8 failed. Dominant failure: reasoning leakage (`thinking_leak=true` on 7/8); additional failures include route/citation failures and private-state-risk/refusal failures on the two refusal rows. Evidence: `evidence/orionfold-advisor/advisor-preflight-v0.1.json`, `advisor-preflight-v0.1.results.jsonl`, `/tmp/orionfold-advisor-dogfood/arena-models-nemotron-nano9b-pinned.png`, and `/tmp/orionfold-advisor-dogfood/arena-cortex-nemotron-nano9b-after-run.png`. Do not claim Nano 9B passed or is selected.
- 2026-06-09 continuation (Claude) executed the spec §13.C step-5 no-thinking probe through the cockpit. `scripts/orionfold_advisor/preflight.py` gained `--reasoning-mode off` (prepends Nemotron `/no_think` to the system prompt; mode recorded in the report), `POST /api/advisor/preflight/run` accepts `reasoning_mode` and writes `-nothink`-suffixed evidence so the reasoning-on receipt is preserved, and the Cortex Advisor card gained a `run /no_think` control plus a reasoning chip. Rebaked `_webui`, restarted browser-use Arena, and clicked `run /no_think` in visible Cortex against the live Nano 9B NIM lane. Receipt `advisor-preflight-v0.1-nothink.json` is **failed**, not publishable: 8 scored, 1 passed, 7 failed — but `thinking_leak` dropped 7/8 → 0/8. Remaining failures are SFT-shaped: 4 exact-source-id alias/format rows, 1 grounding over-refusal (expected source was retrieval rank 1), 2 refusal rows without refusal wording. Both receipts visible in the Cortex runs list. Offline gate: 459 arena tests pass (`/tmp/arena-venv`). Evidence: `/tmp/orionfold-advisor-dogfood/arena-cortex-nothink-control.png`, `arena-cortex-nano9b-nothink-after-run.png`.
- 2026-06-09 continuation (Claude) ran the §13.C probe on the third NVIDIA-native candidate (OA-NV-3) end-to-end through the cockpit. Downloaded `lmstudio-community/NVIDIA-Nemotron-3-Nano-30B-A3B-GGUF` Q8_0 (33.6 GB) to `/home/nvidia/data/quants/Nemotron-3-Nano-30B-A3B/` (local llama.cpp build `856c3ad` 2026-05-12 supports `nemotron_h_moe`), stopped the Nano 9B NIM (`docker stop fk-nim-8000`, sanctioned path), authored lane recipe `nemotron3-nano-30b-q8`, launched it through guarded visible LaneTruth (job `61bdb23c`, warm 14.0 s, pinned on warm), and ran both preflight modes from the visible Cortex card. Default reasoning: **0/8** — `thinking_leak` on all rows, but citations underneath are mostly correct. `/no_think`: **5/8** with zero thinking leakage and zero private-state risk — the best NVIDIA-native raw floor, tying Qwen2.5. The 3 failures are the same SFT-shaped classes seen everywhere: `Source 2` alias instead of `product_orionfold_cortex` (0074) and two bare refusals without refusal wording (0087/0088). Two script fixes shipped: `--reasoning-mode off` now also sends `chat_template_kwargs={"enable_thinking": false}` (Nemotron-3/Qwen3-style templates; the Nano 9B `/no_think` token is kept — models ignore the control they don't use), and the private-state scorer no longer flags long tokens echoed from the packet's own prompt (0087 had a false `private_state_risk` from the family name `missing_source_refusal`; novel secrets still flag). 10 advisor arena tests pass. Receipts overwrote `advisor-preflight-v0.1*.json` in place per convention (Nano 9B receipts preserved in git history). Screenshots: `/tmp/orionfold-advisor-dogfood/arena-models-nemotron3-30b-lane.png`, `arena-cortex-nemotron3-30b-default-run.png`, `arena-cortex-nemotron3-30b-nothink-rerun.png`.

### 2026-06-09 — Advisor / Workbench pivot specced

- Restored the product name **Orionfold Advisor** in `_SPECS/orionfold-advisor-nvidia-native-v1.md` v1.2. Existing `advisor-*` proof ids remain canonical.
- Updated `_SPECS/orionfold-advisor-nvidia-native-v1.md` to v1.2 for the revised flagship Advisor track: a governed local AI advisor appliance packaged as harness + model + retriever + corpus pack + Arena workspace, with NVIDIA-native local lanes, swappable customer corpora, and governed hosted-SOTA/OpenRouter overflow.
- Created `_SPECS/orionfold-local-ai-workbench-v1.md` for the separate Arena + fieldkit + Cortex + lane/eval/training receipt product track.
- Marked `_SPECS/orionfold-advisor-unsloth-arena-v1.md` and `_SPECS/orionfold-advisor-dogfood-v1.md` as superseded planning history. Salvage retained: corpus/bench/recall evidence, visible Cortex preflight execution, Qwen2.5 failure receipt, and AD-AE/AD-FK dogfood findings.
- Preliminary NVIDIA/HF scout was captured in the Advisor spec. First NVIDIA-native candidates to probe: `nvidia/NVIDIA-Nemotron-Nano-9B-v2`, `nvidia/NVIDIA-Nemotron-3-Nano-4B-BF16`, and `nvidia/nemotron-3-nano-30b-a3b`. Keep Qwen3-8B/14B and `openai/gpt-oss-20b` as open-weight comparison baselines. Use Nemotron Ultra/Super as hosted teacher/evaluator lanes only unless a real Spark-local path is proven. OpenRouter belongs as a governed overflow tier with explicit allowed models, data-policy constraints, cap-usd, and cost audit, not as the default Advisor path.

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

- Cockpit `:7866` is up in browser-use mode via `.claude/skills/arena-lifecycle/scripts/arena_lifecycle.sh restart --browser`; visible CDP Chromium `:9222` was driven for the 30B lane launch + both Cortex preflight runs. Last restart pids: cockpit `957089`, browser `957106`.
- Codex sandbox workaround: localhost/CDP probes can fail inside sandbox (`EPERM` or false DOWN status). Use escalation for read-only `arena_lifecycle.sh status --browser`, CDP attach, screenshots, and `up --browser` if `/tmp/arena-venv` rebuild needs dependency downloads. Keep screenshots attached with `defaultViewport: null` so the operator-resized real browser window controls framing.
- Current GPU lane: llama-server `nemotron3-nano-30b-q8` on `:8091` (launched via LaneTruth job `61bdb23c`, pid `1071764`), serving `NVIDIA-Nemotron-3-Nano-30B-A3B-Q8_0.gguf` at ctx 8192 with `--jinja`. Pinned in LaneTruth as source `registry`; the global run context still says Kepler/astrodynamics (AD-AE-14). The `fk-nim-8000` Nano 9B NIM container is **stopped** (restartable via `docker start fk-nim-8000`). Recipe persisted in `~/.fieldkit/arena/lane-recipes.json`.
- `/tmp/arena-venv` fieldkit editable tracked source and read `0.31.0` at last check.
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
- Codex sandbox health: Ubuntu AppArmor `bwrap-userns-restrict` is loaded and `codex sandbox /bin/true` / `codex sandbox pwd` / `codex sandbox bash -lc 'printf ok'` pass as of 2026-06-09.
- Codex Arena browser-use workaround is recorded in `.agents/skills/arena-lifecycle/SKILL.md`; localhost CDP/status checks may need escalation even for read-only inspection.

### Strategy / Growth

- **Orionfold Advisor NVIDIA-native proof**: execute `_SPECS/orionfold-advisor-nvidia-native-v1.md` as the next publish-grade small run. Default domain = Advisor over the public Orionfold corpus, and the product unit is harness + model + retriever + corpus pack + Arena workspace. Use NVIDIA-native models/runtimes/training first; use Arena/fieldkit for corpus import, lane launch, eval, routing/cost ledger, RL headroom decision, provenance, and publish/reject receipt. Respect the one-lane DGX Spark memory envelope.
- Immediate Advisor proof next step: the §13.C raw-floor standings are now Qwen2.5 5/8 (comparison), Nano 9B `/no_think` 1/8, **Nemotron-3-Nano-30B-A3B `/no_think` 5/8** (best NVIDIA-native; zero leakage, zero private-state risk). All remaining failures across every candidate are the same two SFT-shaped classes: exact-source-id aliasing (`Source 2`) and bare refusals without refusal wording. Decision for next session: (a) one bounded exemplar-format pass on 30B-A3B (a single exact-citation + refusal-sentence example in the system prompt) to test whether the §14 ≥7/8 pre-SFT bar is reachable without training — one iteration, not another prompt-tuning loop; (b) if SFT is still needed, pick the §13.D target weighing floor vs trainability: 30B-A3B has the floor but is MoE (spec flags it serve/eval-leaning; NeMo SFT path unproven), Nano 9B has the documented NeMo path but a 1/8 floor; (c) `NVIDIA-Nemotron-3-Nano-4B-BF16` (OA-NV-2) is now cheap to probe with the same GGUF-recipe pattern if a trainable dense base with a decent floor is wanted. RAG recall has a passing local baseline (`source_recall@5=0.9885` overall, `1.0` held-out answerable) but should later be repeated through the live Cortex/Arena lane before publish claims.
- During the run, carry forward the existing `AD-FK-*` fieldkit and `AD-AE-*` Arena findings into the Workbench/Advisor task breakdown rather than treating the superseded dogfood spec as the active plan. Treat terminal-only workarounds as dogfood findings unless they are expected external setup. Current concrete Arena findings: `AD-AE-11` for missing manifest/bench/recall visibility, `AD-AE-12` for missing base-model scout/preflight visibility, `AD-AE-13` built for preflight receipt/lane-readiness/execution, `AD-AE-14` still open for Advisor-specific run-context/proof labeling, and Workbench `WB-11` because visible LaneTruth can discover/pin NIM lanes but cannot launch them through the guarded UI.
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

### 2026-06-09 - Advisor / Workbench pivot adopted

Created two replacement specs after Orionfold's NVIDIA Inception selection changed positioning: `_SPECS/orionfold-advisor-nvidia-native-v1.md` for the flagship **Orionfold Advisor** product and `_SPECS/orionfold-local-ai-workbench-v1.md` for Arena/fieldkit as the local AI Workbench. Advisor v1.2 is packaged as harness + model + retriever + corpus pack + Arena workspace, with swappable customer corpora and governed hosted-SOTA/OpenRouter overflow. Dropped Unsloth from the default plan; it can re-enter only after a measured NVIDIA-native baseline. Preliminary search says probe Nemotron Nano 9B/4B and Nemotron-3-Nano-30B-A3B first, with Qwen3 and gpt-oss-20b as comparison baselines. | Manav (with Codex)

### 2026-06-09 - NVIDIA-native scout staged

Wrote the revised Advisor metadata scout to `/tmp/hf-scout/2026-06-09/advisor-nvidia-native/report.md` with `candidates.json`. The scout demotes the older Qwen/Unsloth report to comparison history and ranks Nano 9B v2 first, Nano 4B BF16 second for fast Spark-native probing, and Nemotron-3-Nano-30B-A3B third as a larger serve-only local comparison. No model weights were downloaded; Arena-visible preflight is still the selection gate. | Manav (with Codex)

### 2026-06-09 - Nano 9B visible preflight failed

Tore down Qwen2.5 through visible LaneTruth, served cached `nvidia/nemotron-nano-9b-v2` NIM on `:8000`, pinned it in Arena, and ran the tracked 8-row Advisor preflight from visible Cortex. The receipt is failed and non-publishable: 8 scored rows, 0 passing, 8 failing. Main failure class is reasoning leakage, with route/citation/refusal failures also present. This proves runtime viability for Nano 9B on Spark, not Advisor behavioral suitability. | Manav (with Codex)

### 2026-06-09 - Advisor preflight diagnosis narrowed but still failed

Diagnosed the first failed visible Qwen2.5 Advisor preflight and reran through Cortex after prompt/scorer tightening. The tracked gate improved from 4 passing / 4 failing to 5 passing / 3 failing, but it is still not publishable. Remaining failures are one exact-source-id alias (`Source 2`) and two bare refusal outputs (`Citations: []` without refusal language). This now serves as a failed baseline for the NVIDIA-native scout, not a reason to keep tuning Qwen2.5 prompts. | Manav (with Codex)

### 2026-06-09 - Nemotron-3-Nano-30B-A3B raw floor is the new NVIDIA-native best

Probed the third NVIDIA-native candidate (OA-NV-3) before committing the §13.D SFT probe to Nano 9B: served `NVIDIA-Nemotron-3-Nano-30B-A3B` Q8_0 via guarded LaneTruth llama-server lane and ran both preflight modes from visible Cortex. Default reasoning 0/8 (all thinking leak); `/no_think` (via `chat_template_kwargs.enable_thinking=false`) **5/8** with zero leakage — ties Qwen2.5's best floor and beats Nano 9B's 1/8. Remaining failures are the universal SFT-shaped pair: source-id aliasing and missing refusal wording. The gate is still failed/non-publishable, but the base-model question now favors 30B-A3B on floor, with trainability (MoE NeMo SFT path) the open risk. | Manav (with Claude)
