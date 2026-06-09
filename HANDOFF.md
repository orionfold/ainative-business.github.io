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

### 2026-06-09 — Unsloth compete/partner strategy memo drafted

- Created the scaffold `_IDEAS/unsloth-compete-partner-uber-strategy.md` and the internal final memo `_IDEAS/unsloth-compete-partner-analysis.md`.
- Recommendation: do **not** compete with Unsloth on training kernels or generic no-code fine-tuning UI. Position Orionfold as the post-training control plane: **Unsloth trains/exports; Orionfold scores, governs, publishes, and operationalizes.**
- The memo includes persona lenses, official factbase, adoption/friction signal ledger, Orionfold asset audit, scored surface matrix, partner workflow, content/SEO plan, partnership path, risks, kill criteria, and 30-day plan.
- No public pages changed. Remaining optional proof is a contained live Spark integration receipt: Unsloth Core/Studio export -> fieldkit manifest -> Arena score -> Field Note.

### 2026-06-09 — Codex coexistence baseline adopted

- Codex reads `HANDOFF.md` at session start and updates it at session end when live state, public artifacts, release posture, or the status beacon changes.
- Codex coexistence layer is committed at `ddb6626 chore(codex): add coexisting CLI contract` and scoped to `AGENTS.md`, `CODEX-CC.md`, `.codex/`, `.agents/skills/`, and the `.gitignore` exception for tracked Codex skills.
- Do not edit `.claude/` for Codex behavior unless explicitly requested. Existing untracked `.claude/scheduled_tasks.lock` and `src/data/arena-mirror/` are operator/Claude/generated state; leave them alone unless the task targets them.

### 2026-06-07 — Arena/fieldkit latest shipped baseline

- Latest fieldkit release: `fieldkit v0.31.0`, tag `fieldkit/v0.31.0`, PyPI live. It includes AE-31 guarded lane launch/teardown and demo recorder extensions. No arena.db schema change (`user_version` 6).
- AE-31 live rep fired successfully: first operator lane recipe `kepler-q8` was authored, launch from LaneTruth passed pre-flight, lane served correctly, and UI teardown honestly released the lane. Recipe file is a kept operator asset at `~/.fieldkit/arena/lane-recipes.json`.
- Arena v2 spec-completion work is closed. Follow-on live exercises (`sft_run` drain, corpus-request fulfilment, metered cloud-eval teardown, GS-1 cap edit, AE-10 candidate-base behavior) are validation/test work for shipped surfaces, not open spec tasks.
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

### Strategy / Growth

- **Unsloth compete-vs-partner U6 optional live Spark proof**: if operator wants it, install/run Unsloth Studio/Core in an isolated lane, train or adapt a tiny model, export/import into fieldkit/Arena, score it, and publish a build receipt. Respect the one-lane DGX Spark memory envelope.
- Do not edit public pages for Unsloth positioning until the strategy recommendations are accepted or a live proof exists.

### Editorial

- Phase 2 launch: use `product-writer` for the built autonomous-harness cockpit surface (morning standup, cron queue, budget governor), cross-linking the H4 deep dive.
- Living-model launch (`products/living-model/`, `status: upcoming`): promote only when a future RL-sensitive run produces real lineage delta data, or reframe honestly around headroom-gate methodology. Do not edit `src/data/book/chapters/**` for MTBM book-overlay work; use `book_chapters` cross-links only.

### Operator-Owned Live Infra

- Future live `rl_run`: install pinned `fieldkit[rl]` plus pinned aarch64/CUDA-13 vLLM lane, set `FK_RL_*` via `scripts/astro_bench/fk-rl-env.sh`, then arm overnight drain when operator is ready. One-lane memory envelope still applies.
- `sudo chown` root-owned container-written dirs when needed: `merged-hf-bf16`, `init-lora-r16`, HF-cache `models--Qwen--Qwen3-8B` stub.
- Second Brain: deploy evidence server over `/home/nvidia/second-brain-mcp/server.py`, `pip install -e fieldkit` in its venv, and run first `/api/knowledge/reindex` to backfill schema/provenance.
- PSI authenticated key still missing; blocks PageSpeed in `/seo-monitor`.

### SEO

- Re-run `/seo-monitor` in the next 1-2 week settlement window to confirm sitemap/indexing. Keep GSC unused verification token `fePoYwMX...` as HOLD/do-not-remove. Journal in `seo-progress.md`.

### Cleanup

- Human-eye/Lighthouse pass on LoRA/adapter/dataset detail pages and empty-state listing pages.
- Low-priority bakeoff gated-catalog footer last-write-wins issue.
- Patent-strategist W3 fine-tune follow-up when source-side work lands.
- Deprecate or replace the retired `sync-field-notes` skill body now that the monorepo cutover changed source paths.
- Optional: relocate the old Claude memory namespace symlink into this repo namespace for a cleaner cutover.

## Recent Decisions

### 2026-06-09 — HANDOFF compacted

Pruned completed Arena/fieldkit release history and stale task blocks from `HANDOFF.md`. Current-state and open-task continuity remain; full removed history is recoverable through `git log -p HANDOFF.md`. | Manav (with Codex)

### 2026-06-09 — Unsloth compete/partner memo drafted

Completed U1-U5 of the Unsloth strategy workstream in `_IDEAS/unsloth-compete-partner-analysis.md`. Recommendation: avoid direct competition on kernels/no-code training UI; use Unsloth as training/export partner and position Orionfold as the post-training control plane for scoring, governance, publication, and workflow routing. No public pages changed. U6 live Spark proof remains optional/operator-gated. | Manav (with Codex)
