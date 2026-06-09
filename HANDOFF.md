<!--
  Session handoff for ainative-business.github.io (Spark-operated monorepo).
  Convention:
  - Keep this file short: current state, live runtime, build/verify, open items, and ~2 recent decisions.
  - Do NOT append completed history. Prune closed tasks aggressively; full history is recoverable via `git log -p HANDOFF.md`.
  - Last pruned/reset: 2026-06-09 (Codex compacted completed Arena/fieldkit release history and stale completed task blocks).
-->

# HANDOFF — ainative-business.github.io

> 📌 **PINNED — Arena build discipline.** Any `arena-app/` or `fieldkit.arena` work that changes the cockpit must be built and browser-smoked side by side in the running Arena over CDP: bring the cockpit up in browser-use mode (`arena_lifecycle.sh up --browser` -> `:7866` + CDP Chromium `:9222`), rebake `_webui` after `arena-app/` edits (`fieldkit arena build --repo-root arena-app`), then drive the live panes and confirm the change renders. Live `rl_run` validation stays operator-armed; offline tests + live render/transport smoke are the normal session bar.

## Current State

### 2026-06-09 - Codex Linux sandbox repaired

- Operator installed/loaded the Ubuntu AppArmor `bwrap-userns-restrict` profile for bubblewrap after Codex tools intermittently failed with `bwrap: loopback: Failed RTM_NEWADDR: Operation not permitted`.
- Verified fixed in this repo: `codex sandbox /bin/true` exits cleanly and `codex sandbox pwd` prints `/home/nvidia/ainative-business.github.io`.
- Syntax note for current local CLI (`codex-cli 0.138.0`): use `codex sandbox <command>`. Older issue/docs examples using `codex sandbox linux <command>` are stale here and try to execute a command named `linux`.
- If sandbox failures recur after a Codex restart, next fallback is the known Codex GitHub workaround `[features] use_legacy_landlock = true`; do not enable it unless the AppArmor profile stops working.

### 2026-06-09 - Advisor proof-start evidence generated

- Began the Orionfold Advisor Unsloth/Arena proof with deterministic, tracked pre-GPU evidence under `evidence/orionfold-advisor/`.
- `scripts/orionfold_advisor/generate.py` now writes and validates: `domain-gate.json`, `source-audit.json`, `public-corpus-manifest.jsonl`, `advisor-bench-v0.1.jsonl`, and `advisor-bench-v0.1.heldout.jsonl`.
- Domain gate winner: **Orionfold Advisor**. Corpus manifest currently contains 137 public-safe sources; upcoming articles/products, proof-control specs, handoff/status/operator state, and private config paths are excluded. Source audit records that this checkout exposes one public 14-chapter book surface, not three books.
- Advisor bench seed: 103 total rows, 28 frozen held-out rows, with >=15 refusal/private-state cases and source-id validation. This is an eval/source-boundary seed, not SFT training data.
- Corpus correction before RAG: v0.1 captured local repo docs/guides/specs but **missed `src/pages/docs/**` / `https://ainative.business/docs/`**, which is the Book 3 source for **AI Native Platform**. Treat Field Notes as Book 2 (**AI Research on NVIDIA DGX Spark**) source and `src/data/book/chapters/**` as Book 1 (**AI Native Business**) source. `https://orionfold.com/books/` is reference/CTA, not primary training evidence.
- Next proof step: regenerate the corpus manifest with the Platform docs route included and book-surface/source-role metadata, then build the RAG/recall lane and run the Advisor base-model scout/preflight before any Unsloth Core training.

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

Last recorded runtime baseline: post-AE-31 rep, 2026-06-07.

- Cockpit `:7866` was left up in browser-use mode via `arena-lifecycle restart --browser`; visible CDP Chromium `:9222` was parked on `/arena/models/`.
- GPU lane is free. The `kepler-q8` lane launched during AE-31 was torn down from the UI; run-context is honestly unanchored.
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
- Codex sandbox health: Ubuntu AppArmor `bwrap-userns-restrict` is loaded and `codex sandbox /bin/true` / `codex sandbox pwd` pass as of 2026-06-09.

### Strategy / Growth

- **Orionfold Advisor Unsloth/Arena proof**: execute `_SPECS/orionfold-advisor-unsloth-arena-v1.md` as the next publish-grade small run. Default domain = Advisor over the public Orionfold corpus; use Unsloth Core for SFT/export; use Arena/fieldkit for import, launch, eval, RL headroom decision, provenance, and publish/reject receipt. Respect the one-lane DGX Spark memory envelope.
- Immediate Advisor proof next step: first correct/regenerate the manifest to include `src/pages/docs/**` as Book 3 / AI Native Platform source, then build/score the RAG recall path against `advisor-bench-v0.1*.jsonl` and use `hf-model-scout` for the base-model preflight before Unsloth setup.
- During the run, update `_SPECS/orionfold-advisor-dogfood-v1.md` with `AD-FK-*` fieldkit and `AD-AE-*` Arena findings. Treat terminal-only workarounds as dogfood findings unless they are expected external setup.
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

### 2026-06-09 - Codex sandbox AppArmor fix applied

Loaded Ubuntu's `bwrap-userns-restrict` AppArmor profile for bubblewrap and verified Codex sandbox commands pass with current syntax (`codex sandbox <command>`). No Codex config change or `use_legacy_landlock` fallback needed yet. | Manav (with Codex)

### 2026-06-09 - Advisor proof-start evidence generated

Started the Advisor proof with deterministic pre-GPU evidence: domain gate, public source manifest/audit, and a frozen 103-row Advisor bench seed with 28 held-out rows. Follow-up correction recorded: v0.1 missed `src/pages/docs/**` / `/docs/`, the Book 3 AI Native Platform source; include it before RAG. No model download, training, Arena launch, or public page edit yet. | Manav (with Codex)

### 2026-06-09 — Arena validation reminders consolidated

Pruned stale one-off Arena validation reminders into the planned end-to-end new-model Arena run. The next readiness proof should exercise the real training-to-inference path; RL/cloud-eval/cap-edit/candidate-base checks are only in scope if that run needs them. | Manav (with Codex)

### 2026-06-09 — Advisor proof specs authored

Captured the combined Unsloth partner-path + Arena readiness proof in `_SPECS/orionfold-advisor-unsloth-arena-v1.md`, with `_SPECS/orionfold-advisor-dogfood-v1.md` as the parallel fieldkit/Arena dogfood ledger. Defaults locked from planning: Advisor domain, public corpus, RAG-first, Unsloth Core primary, publish-grade small run, Arena browser-use first, RL only after headroom gate. | Manav (with Codex)

### 2026-06-09 — Unsloth compete/partner memo corrected with bakeoff guardrail

Completed U1-U5 of the Unsloth strategy workstream in `_IDEAS/unsloth-compete-partner-analysis.md`, then folded in the patent-strategist Unsloth-vs-NeMo bakeoff decision: do not use the unpublished patent-strategist Unsloth lane as the next proof artifact. Recommendation remains partner-compatible: Unsloth trains/exports; Arena/fieldkit score, govern, publish, or reject. No public pages changed. U6 live Spark proof remains optional/operator-gated. | Manav (with Codex)
