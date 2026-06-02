<!-- CLAUDE.md — onboarding / doc-navigation map. Last updated: 2026-06-02 -->

# CLAUDE.md — where things live

This repo (`ainative-business.github.io`) is the single **Spark-owned monorepo** — build
workspace *and* website — since the 2026-05-29 cutover. There is no separate Mac sync repo;
author directly here. Live at `ainative.business` (GitHub Pages, auto-deploy on push to `main`).

## Doc map

- **`WORKFLOWS.md`** (root) — the canonical **origin-instruction → artifact** map + the
  forward-looking roadmap. Start here to understand how a request ("write this up", "publish
  the GGUF", "release fieldkit") flows to a shipped artifact. *(tracked since `adb1c04`)*
- **`HANDOFF.md`** (root) — the living **session-transfer** doc: current state, live runtime,
  open items, recent decisions. Read at the start of a session; update after significant work.
- **`_GUIDES/`** → see [`_GUIDES/INDEX.md`](_GUIDES/INDEX.md) — **active guidance & practices**:
  publishing contracts (`NARRATIVE-CONTRACT.md`, `PRODUCT-ARTICLES.md`), Arena distribution
  (`arena-distribution.md`, `arena-storefront-marketing.md`), operator reference
  (`local-ai-stack-commands.md`).
- **`_SPECS/`** → see [`_SPECS/INDEX.md`](_SPECS/INDEX.md) — **specs, plans & design docs**:
  the 4 active specs (`patent-strategist-v1`, `notebooks-as-artifacts-v1`, `spark-arena-v1`,
  `hermes-harness-v1`) at root; superseded/historical under `_SPECS/archive/`.
- **Skill procedures** — `.claude/skills/<name>/SKILL.md` (authoritative per-skill workflow).
- **Generated reports** (root, skill-written) — `ainative-stats.md`, `seo-progress.md`.

## Load-bearing invariants (full detail in `WORKFLOWS.md` §1)

1. **Solo-blog, direct-to-main** — commit subjects are the changelog; human review is the gate.
2. **One serving lane in 128 GB** — GB10 shares CPU+GPU memory; one model resident at a time.
3. **Privacy-gated publish** — secret-scan + scoped captures before commit; no auto-push.
4. **Deterministic scripts, not LLM coordination** — skills' `scripts/` do only mechanical
   transforms; the session model does the writing. Never call `anthropic`/`claude-agent-sdk`.

## Build / verify

`node node_modules/astro/astro.js build` (485 pages; `npm run build` is broken on this checkout
per the SMB-symlink memory) → `node scripts/verify_artifact_rendering.mjs` +
`node scripts/verify_field_notes_rendering.mjs`. `build:og` is CI-only (needs Chrome).
