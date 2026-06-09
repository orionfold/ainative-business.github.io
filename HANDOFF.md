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

- Began the Orionfold Advisor Unsloth/Arena proof with deterministic, tracked pre-GPU evidence under `evidence/orionfold-advisor/`.
- `scripts/orionfold_advisor/generate.py` now writes and validates: `domain-gate.json`, `source-audit.json`, `public-corpus-manifest.jsonl`, `advisor-bench-v0.1.jsonl`, and `advisor-bench-v0.1.heldout.jsonl`.
- Domain gate winner: **Orionfold Advisor**. Corpus manifest currently contains 181 public-safe sources; upcoming articles/products, proof-control specs, handoff/status/operator state, and private config paths are excluded.
- Corpus manifest corrected after v0.1: `src/pages/docs/**` / `https://ainative.business/docs/` is now included as Book 3 / **AI Native Platform** source. Manifest rows now include `source_role` for every source and `book_surface` metadata for Book 1 / **AI Native Business** (`src/data/book/chapters/**`), Book 2 / **AI Research on NVIDIA DGX Spark** (published Field Notes), and Book 3 / **AI Native Platform** (`src/pages/docs/**`). `https://orionfold.com/books/` remains reference/CTA, not primary training evidence.
- Advisor bench seed: 103 total rows, 28 frozen held-out rows, with >=15 refusal/private-state cases and source-id validation. This is an eval/source-boundary seed, not SFT training data.
- RAG/recall gate added: `scripts/orionfold_advisor/score_recall.py` writes `rag-recall-v0.1.json` and `rag-recall-v0.1.predictions.jsonl`. Local BM25/provenance-chunk baseline over the 181-source manifest passed: all rows source_recall@5 = 0.9885, held-out answerable source_recall@5 = 1.0, 16 refusal rows excluded from recall denominators. Only top-5 miss is one pool workflow-routing row for `doc_fieldkit_docs_api_memory_md`; it is recovered by top-10.
- Advisor base-model scout completed with `hf-model-scout` metadata probes only; no weights downloaded. Scratch report: `/tmp/hf-scout/2026-06-09/advisor-8B/report.md`; sidecar: `/tmp/hf-scout/2026-06-09/advisor-8B/candidates.json`. Recommendation: start with `Qwen/Qwen3-8B`; fallback `Qwen/Qwen2.5-7B-Instruct`; keep `mistralai/Mistral-7B-Instruct-v0.3` as control. `ibm-granite/granite-3.3-8b-instruct` is manual-review until the local probe whitelist/llama.cpp converter path is verified for `granite`; Gemma/Llama candidates hit approval-gated metadata and were ruled out for the clean publishable flow. Browser-use gap logged as `AD-AE-12`: Arena stayed parked on Cortex because the cockpit has no visible base-model scout/preflight artifact surface yet.
- Arena browser-use is now up for the Advisor proof. Cortex pane smoke confirmed the local Advisor manifest/bench/recall receipt is **not** visible in Arena yet; logged concrete dogfood finding `AD-AE-11` in `_SPECS/orionfold-advisor-dogfood-v1.md`. Retaken Cortex screenshot at the operator-resized real browser window is staged at `/tmp/orionfold-advisor-dogfood/cortex-no-advisor-recall.png`.
- Advisor retrieved-context generator preflight harness added: `scripts/orionfold_advisor/preflight.py` writes balanced held-out prompt packets and can score a local OpenAI-compatible endpoint for deterministic artifact generation, but live validation must be driven through the visible Arena cockpit. Current tracked packet receipt: `evidence/orionfold-advisor/advisor-preflight-v0.1.json` plus `advisor-preflight-v0.1.prompts.jsonl` (8 rows across cited QA, artifact, book, workflow routing, operator recommendation, Unsloth/Arena separation, and 2 refusal cases). Logged Arena visibility/lane-readiness gap `AD-AE-13`.
- 2026-06-09 browser-use continuation: Qwen3-8B was converted locally to GGUF and launched through Arena/fieldkit LaneTruth on `:8091`, then replaced via guarded `teardown_first` with official `Qwen/Qwen2.5-7B-Instruct-GGUF` Q5_K_M shards on `:8091` after Qwen3 visibly failed behavior checks. Current visible Arena lane is `qwen2.5-7b-instruct-q5_k_m-00001-of-00002.gguf`; run context is anchored in Arena, but still labeled Kepler/astrodynamics because Advisor has no first-class run-context surface yet.
- Browser-use evidence staged under `/tmp/orionfold-advisor-dogfood/`: `arena-current-visible-qwen25.json/png` and `arena-visible-qwen25-safe-refusal-turn.json` plus before/after screenshots. Visible Chat refused a safe private-config-token disclosure prompt with `Citations: []`. Do not claim the full 8-row Advisor batch preflight passed; continue in Arena and treat missing Advisor eval/preflight UI as the blocking dogfood gap.
- 2026-06-09 continuation built the first visible Advisor preflight receipt surface in Arena: `GET /api/advisor/preflight` reads `evidence/orionfold-advisor/advisor-preflight-v0.1.json` plus packet metadata, and `/arena/cortex/` now shows the Advisor preflight card (8 packets, Qwen3 target, `not_run`, 0 scored results). Baked with `/tmp/arena-venv/bin/fieldkit arena build --repo-root arena-app`, restarted Arena in browser-use mode, and smoked the live Cortex card. Evidence: `/tmp/orionfold-advisor-dogfood/arena-cortex-advisor-preflight-card.json/png`.
- Visible Chat smoke on Qwen2.5 fallback ran one cited-factual Advisor packet (`advisor-cited-factual-qa-0003`) and returned `Citations: [article_autoresearchbench_on_spark]` with no thinking leakage. This is single-turn manual evidence only, not an 8-row preflight pass. Logged `AD-AE-14` because the result is still a chat turn and the cockpit run context remains labeled Kepler.
- 2026-06-09 continuation added the visible Advisor preflight execution path in Arena: `GET /api/advisor/preflight` now reports active-lane readiness, `/arena/cortex/` shows the active Qwen2.5 lane and a `run preflight` control, and `POST /api/advisor/preflight/run` runs the tracked preflight script against Arena's active lane and returns the redacted scored receipt. Baked with `/tmp/arena-venv/bin/fieldkit arena build --repo-root arena-app`, restarted Arena in browser-use mode, and smoked live Cortex. Evidence: `/tmp/orionfold-advisor-dogfood/arena-cortex-advisor-run-control.png`.
- The visible Advisor preflight was executed through Cortex against Qwen2.5 fallback on `:8091`. It wrote `evidence/orionfold-advisor/advisor-preflight-v0.1.results.jsonl`; the gate is **failed**, not publishable: 8 rows scored, 4 passed, 4 failed. Failing rows: `advisor-cited-factual-qa-0003`, `advisor-artifact-release-facts-0034`, `advisor-workflow-routing-0065`, and `advisor-missing-source-refusal-0088`. Live Cortex renders `scored` / `8 rows` / `4 failing`. Evidence: `/tmp/orionfold-advisor-dogfood/arena-cortex-advisor-scored-failing-run.png`.
- Next proof step: diagnose the four failed Advisor preflight rows and decide whether this is a prompt/scorer/base-model issue before any Unsloth Core setup. Keep doing this through visible Arena surfaces; the remaining Arena gap is Advisor-specific run-context/proof labeling, because the cockpit is still oriented by older Kepler/astrodynamics context.

### 2026-06-09 — Orionfold Advisor Unsloth/Arena proof specced

- Added tracked specs for the next combined proof run: `_SPECS/orionfold-advisor-unsloth-arena-v1.md` and `_SPECS/orionfold-advisor-dogfood-v1.md`.
- Plan: use **Orionfold Advisor** as the default domain over the public Orionfold corpus, keep RAG as the fact/citation layer, use Unsloth Core for SFT/export, then let fieldkit/Arena import, launch, evaluate, score, and publish or reject the candidate.
- Execution posture: publish-grade small, Arena browser-use first (`:7866` + CDP `:9222`), with every terminal-only workaround classified in the dogfood spec as expected external setup or a fieldkit/Arena finding.
- Dogfood ledgers are `AD-FK-*` for fieldkit enhancements and `AD-AE-*` for Arena enhancements. Use them during the run before deciding which fixes deserve a fieldkit release or future Arena enhancement spec.

### 2026-06-09 — Unsloth compete/partner strategy memo drafted

- Created the scaffold `_IDEAS/unsloth-compete-partner-uber-strategy.md` and the internal final memo `_IDEAS/unsloth-compete-partner-analysis.md`.
- Recommendation: do **not** compete with Unsloth on training kernels or generic no-code fine-tuning UI. Position Orionfold as the post-training control plane: **Unsloth trains/exports; Orionfold scores, governs, publishes, and operationalizes.**
- The memo includes persona lenses, official factbase, adoption/friction signal ledger, Orionfold asset audit, scored surface matrix, partner workflow, content/SEO plan, partnership path, risks, kill criteria, and 30-day plan.
- Follow-up bakeoff check: `articles/patent-strategist-bakeoff-unsloth-vs-nemo-framework/` intentionally dropped the patent-strategist Unsloth track as the public/default artifact because NeMo won on wall time, patent-strategic chain length, and perplexity. Future Unsloth proof should **not** resurrect that lane; use it as historical baseline or run a fresh small Studio/Core export.
- No public pages changed. Remaining optional proof is a contained live Spark integration receipt: Unsloth Core/Studio export -> fieldkit manifest -> Arena score -> Field Note.

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

Last recorded runtime baseline: Advisor proof browser-use restart, 2026-06-09.

- Cockpit `:7866` is up in browser-use mode via `.claude/skills/arena-lifecycle/scripts/arena_lifecycle.sh restart --browser`; visible CDP Chromium `:9222` was smoked on `/arena/cortex/` after the Advisor preflight execution change. Last restart pids: cockpit `439107`, browser `439124`.
- Codex sandbox workaround: localhost/CDP probes can fail inside sandbox (`EPERM` or false DOWN status). Use escalation for read-only `arena_lifecycle.sh status --browser`, CDP attach, screenshots, and `up --browser` if `/tmp/arena-venv` rebuild needs dependency downloads. Keep screenshots attached with `defaultViewport: null` so the operator-resized real browser window controls framing.
- Current GPU lane: Qwen2.5 fallback on `:8091`, launched through fieldkit's guarded lane launcher from recipe `qwen25-7b-q5km`; Qwen3 was torn down first. Arena active lane is `qwen2.5-7b-instruct-q5_k_m-00001-of-00002.gguf`, source `registry`, run-context anchored at `2026-06-09T13:52:55Z`. Tear it down from Arena LaneTruth or `launcher.teardown_lane(8091)` when done; preserve one-lane discipline.
- `/tmp/arena-venv` fieldkit editable tracked source and read `0.31.0` at last check.
- Kept arena.db deltas: two honest job rows from the AE-31 rep (`5419a336` lane_launch done, `caa0ada1` lane_teardown done). Prior capture rows remain as history.
- `openrouter_price_snapshot` still carries `or-refresh-2026-06-06`; G3 was armed at last check. No open corpus request and no `sft_run` rows.
- Tear down when done: `.claude/skills/arena-lifecycle/scripts/arena_lifecycle.sh down --browser`.

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

- **Orionfold Advisor Unsloth/Arena proof**: execute `_SPECS/orionfold-advisor-unsloth-arena-v1.md` as the next publish-grade small run. Default domain = Advisor over the public Orionfold corpus; use Unsloth Core for SFT/export; use Arena/fieldkit for import, launch, eval, RL headroom decision, provenance, and publish/reject receipt. Respect the one-lane DGX Spark memory envelope.
- Immediate Advisor proof next step: continue from the visible Arena browser with the Qwen2.5 fallback lane already resident on `:8091`. Cortex now has active-lane readiness and a visible preflight execution control; the tracked receipt is `scored` with 8 rows and 4 failures, so do not claim an Advisor preflight pass. Diagnose the failures first, especially citation omission on answer/route rows and private-state/refusal failure on `advisor-missing-source-refusal-0088`. RAG recall has a passing local baseline (`source_recall@5=0.9885` overall, `1.0` held-out answerable) but should later be repeated through the live Cortex/Arena lane before publish claims.
- During the run, update `_SPECS/orionfold-advisor-dogfood-v1.md` with `AD-FK-*` fieldkit and `AD-AE-*` Arena findings. Treat terminal-only workarounds as dogfood findings unless they are expected external setup. Current concrete Arena findings: `AD-AE-11` for missing manifest/bench/recall visibility, `AD-AE-12` for missing base-model scout/preflight visibility, `AD-AE-13` built for preflight receipt/lane-readiness/execution, and `AD-AE-14` still open for Advisor-specific run-context/proof labeling.
- Do not edit public pages for Unsloth positioning until the strategy recommendations are accepted or a live proof exists.

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

### 2026-06-09 - Advisor preflight execution surfaced and failed honestly

Added a visible Cortex execution path for the Advisor generator preflight: active-lane readiness in `GET /api/advisor/preflight`, a `run preflight` control, and `POST /api/advisor/preflight/run` that runs the tracked script against Arena's active lane and returns the redacted receipt. Browser-use smoke on Qwen2.5 fallback `:8091` produced a real scored artifact with 8 rows / 4 failures, now rendered in Cortex. This is a failed preflight gate, not a publishable pass; next step is failure diagnosis and Advisor run-context labeling. | Manav (with Codex)

### 2026-06-09 - Arena pipeline browser-use rule memorialized

Promoted the repeated Advisor/Arena operating lesson into durable repo instructions: `AGENTS.md`, `HANDOFF.md`, `CODEX-CC.md`, and `_SPECS/orionfold-advisor-dogfood-v1.md` now state that Arena/fieldkit/model-pipeline work must be driven through the visible Arena cockpit in browser-use mode first. Headless browser scripts, hidden endpoint batch scoring, and terminal-only API calls are not substitutes for Arena validation; missing cockpit surfaces become `AD-AE-*` / `AD-FK-*` findings. Current live lane is Qwen2.5 fallback on `:8091`, visible in Arena; tracked Advisor preflight is now scored and failing. | Manav (with Codex)

### 2026-06-09 - Advisor preflight result summaries wired

Extended `/api/advisor/preflight` and the Cortex Advisor card to summarize scored result rows from a real results JSONL artifact without exposing prompt bodies or model outputs. Later continuation added visible execution and produced a scored failing Qwen2.5 receipt. Focused helper smoke passes; `pytest` is unavailable in the local system/arena venv. | Manav (with Codex)

### 2026-06-09 - Advisor generator preflight packets staged

Added `scripts/orionfold_advisor/preflight.py` and staged the first tracked `advisor-preflight-v0.1` prompt packets under `evidence/orionfold-advisor/`. The gate is intentionally `not_run`: no `Qwen/Qwen3-8B` OpenAI-compatible endpoint was live on `:8080`, `:8000`, or `:8091`. Logged `AD-AE-13` for missing Arena preflight receipt/lane-readiness visibility. No model output, training, or public page edit yet. | Manav (with Codex)

### 2026-06-09 - Advisor base-model scout completed

Completed the Advisor base-model scout under `/tmp/hf-scout/2026-06-09/advisor-8B/` with metadata probes only. Recommended `Qwen/Qwen3-8B` for the first retrieved-context generator preflight; fallback is `Qwen/Qwen2.5-7B-Instruct`, with Mistral v0.3 as control. Granite remains manual-review pending local `granite` GGUF/probe whitelist verification; Gemma/Llama were ruled out by approval-gated metadata for this clean publishable flow. No weights downloaded and no public pages changed. | Manav (with Codex)

### 2026-06-09 - Codex sandbox AppArmor fix applied

Loaded Ubuntu's `bwrap-userns-restrict` AppArmor profile for bubblewrap and verified Codex sandbox commands pass with current syntax (`codex sandbox <command>`), including `pwd` and `bash -lc 'printf ok'` smoke checks. No Codex config change or `use_legacy_landlock` fallback needed yet. | Manav (with Codex)

### 2026-06-09 - Advisor proof-start evidence generated

Started the Advisor proof with deterministic pre-GPU evidence: domain gate, public source manifest/audit, a frozen 103-row Advisor bench seed with 28 held-out rows, and a local retrieval-only recall gate. Corrected manifest count is 181 public-safe sources; local BM25/provenance chunks pass source_recall@5 overall (0.9885) and held-out answerable (1.0). No model download, training, Arena launch, or public page edit yet. | Manav (with Codex)

### 2026-06-09 — Advisor proof specs authored

Captured the combined Unsloth partner-path + Arena readiness proof in `_SPECS/orionfold-advisor-unsloth-arena-v1.md`, with `_SPECS/orionfold-advisor-dogfood-v1.md` as the parallel fieldkit/Arena dogfood ledger. Defaults locked from planning: Advisor domain, public corpus, RAG-first, Unsloth Core primary, publish-grade small run, Arena browser-use first, RL only after headroom gate. | Manav (with Codex)

### 2026-06-09 — Unsloth compete/partner memo corrected with bakeoff guardrail

Completed U1-U5 of the Unsloth strategy workstream in `_IDEAS/unsloth-compete-partner-analysis.md`, then folded in the patent-strategist Unsloth-vs-NeMo bakeoff decision: do not use the unpublished patent-strategist Unsloth lane as the next proof artifact. Recommendation remains partner-compatible: Unsloth trains/exports; Arena/fieldkit score, govern, publish, or reject. No public pages changed. U6 live Spark proof remains optional/operator-gated. | Manav (with Codex)
