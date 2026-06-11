<!-- CLAUDE.md — onboarding / doc-navigation map. Last updated: 2026-06-02 -->

# CLAUDE.md — where things live

This repo (`ainative-business.github.io`) is the single **Spark-owned monorepo** — build
workspace *and* website — since the 2026-05-29 cutover. There is no separate Mac sync repo;
author directly here. Live at `ainative.business` (GitHub Pages, auto-deploy on push to `main`).

## Doc map

- **`_FLOWS/`** → **`_FLOWS/the-machine-that-builds-machines.md`** — the canonical
  **origin-instruction → artifact** map + the forward-looking roadmap. Start here to understand
  how a request ("write this up", "publish the GGUF", "release fieldkit") flows to a shipped
  artifact. `_FLOWS/` is the home of the "Flows" stream — process flow, data flow, and operator
  flow-state. *(renamed from root `WORKFLOWS.md` 2026-06-02 — "Flows", not the CC-overloaded
  "Workflow"; tracked since `adb1c04`)*
- **`HANDOFF.md`** (root) — the living **session-transfer** doc: current state, live runtime,
  open items, recent decisions. Read at the start of a session; update after significant work.
- **`_GUIDES/`** → see [`_GUIDES/index.md`](_GUIDES/index.md) — **active guidance & practices**:
  publishing contracts (`narrative-contract.md`, `product-articles.md`), Arena distribution
  (`arena-distribution.md`, `arena-storefront-marketing.md`), operator reference
  (`local-ai-stack-commands.md`).
- **`_SPECS/`** → see [`_SPECS/index.md`](_SPECS/index.md) — **specs, plans & design docs**:
  the 4 active specs (`patent-strategist-v1`, `notebooks-as-artifacts-v1`, `spark-arena-v1`,
  `hermes-harness-v1`) at root; superseded/historical under `_SPECS/archive/`.
- **Skill procedures** — `.claude/skills/<name>/SKILL.md` (authoritative per-skill workflow).
- **Generated reports** (root, skill-written) — `ainative-stats.md`, `seo-progress.md`.

## Load-bearing invariants (full detail in `_FLOWS/the-machine-that-builds-machines.md` §1)

1. **Solo-blog, direct-to-main** — commit subjects are the changelog; human review is the gate.
2. **One serving lane in 128 GB** — GB10 shares CPU+GPU memory; one model resident at a time.
3. **Privacy-gated publish** — secret-scan + scoped captures before commit; no auto-push.
4. **Deterministic scripts, not LLM coordination** — skills' `scripts/` do only mechanical
   transforms; the session model does the writing. Never call `anthropic`/`claude-agent-sdk`.

## Build / verify

`node node_modules/astro/astro.js build` (485 pages; `npm run build` is broken on this checkout
per the SMB-symlink memory) → `node scripts/verify_artifact_rendering.mjs` +
`node scripts/verify_field_notes_rendering.mjs` +
`node scripts/verify_arena_catalog_sync.mjs` (artifact manifests must byte-match their
`arena-app/` copies). `build:og` is CI-only (needs Chrome).

## Status beacon (Agency cockpit, 2026-06-06)

End every session by writing `_STATUS.json` at the repo root and **committing
it with the session's push** (it churns once per session, like `HANDOFF.md`).
The operator's Agency cockpit (on another desktop) mirrors this repo
read-only and renders the beacon in preference to parsing `HANDOFF.md`. Keep
`focus`/`blockers`/`next`/`recent` short (≤5 items) and factual:

```json
{
  "version": 1,
  "project": "spark",
  "updated": "2026-06-06",
  "health": "green",
  "focus": "one line — what this session moved",
  "blockers": [],
  "next": [],
  "recent": [],
  "session": "S42 (short tag)",
  "metrics": {
    "articles": 66,
    "models": 4,
    "software_released": 12,
    "arena_features": 16,
    "fieldkit_modules": 9,
    "gsc_indexed": 12,
    "gsc_submitted": 305,
    "ga4_users_7d": 123,
    "checked": "2026-06-06"
  }
}
```

`metrics` carries the canonical counts only this project knows — the cockpit
cannot compute them remotely (example values above; replace with real ones).
Sessions that don't re-verify a number carry the previous value forward
verbatim. `checked` is the ISO date the GSC/GA4/HF numbers were actually
read — never bump it without a real check (the cockpit renders staleness
from it, >14d shows a warning).
