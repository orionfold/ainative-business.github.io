<!-- CLAUDE.md — onboarding / doc-navigation map. Last updated: 2026-06-30 -->

# CLAUDE.md — where things live

This repo (`orionfold/ainative-business.github.io` — transferred from `manavsehgal` to the
Orionfold account 2026-06-12) is the single **Orionfold monorepo** — build workspace *and*
website — since the 2026-05-29 cutover. Author directly here.
Live at `ainative.business` (GitHub Pages, auto-deploy on push to `main`).

**Two clones, one repo, never concurrent.** This repo is cloned on the **Mac** (operator cockpit —
website design, marketing, analytics, SEO, migrations) and the **Spark** (DGX — field notes,
`fieldkit`, Arena feature dev; anything Spark-envelope-dependent). Same operator, **never authoring
on both at once** — they hand off. The mechanism that makes that real: **`git pull --rebase origin
main` at session start, `git fetch` + confirm `0 behind` before every push.** A non-clean rebase at
start is the early warning that the two clones diverged — reconcile before working, not after. Full
protocol (routine loop · relay reachability · migration loop · the portable-path rule) in
[`_SPECS/mac-spark-repo-flow-v1.md`](_SPECS/mac-spark-repo-flow-v1.md).

## Doc map

- **`HANDOFF.md`** (root) — the living **session-transfer** doc: current state, live runtime,
  open items, recent decisions. Read at the start of a session; update after significant work.
- **`_GUIDES/`** → see [`_GUIDES/index.md`](_GUIDES/index.md) — **active guidance & practices**:
  the canonical **machine map** (`the-machine-that-builds-machines.md` — the origin-instruction →
  artifact flow + forward-looking roadmap + the 4 invariants; **start here** to see how a request
  flows to a shipped artifact; moved here when the `_FLOWS/` stream was retired 2026-06-12),
  publishing contracts (`narrative-contract.md`, `product-articles.md`), Arena distribution
  (`arena-distribution.md`, `arena-storefront-marketing.md`), operator reference
  (`local-ai-stack-commands.md`).
- **`_SPECS/`** → see [`_SPECS/index.md`](_SPECS/index.md) — **specs, plans & design docs**:
  the active specs (`patent-strategist-v1`, `notebooks-as-artifacts-v1`, `spark-arena-v1`,
  `hermes-harness-v1`, `arena-field-edition-v1`) at root; superseded/historical under
  `_SPECS/archive/`.
- **`_GUIDES/`, `_SPECS/`, `_IDEAS/` (and `_RELAY.md`) are private** (root, **symlinks**, since
  2026-06-12 — `_IDEAS` first, `_SPECS`/`_GUIDES` followed) — each resolves into the **local clone of
  the private `orionfold/strategy` repo** at that machine's path (Spark:
  `/home/nvidia/orionfold-strategy/...`; Mac: `~/orionfold/strategy/ainative-business-website/`).
  Gitignored on both clones (`_RELAY.md` via local `.git/info/exclude` where the tracked
  `.gitignore` doesn't cover it) so the private mailbox can never stage into the public repo.
  `_RELAY.md` is the **cross-clone mailbox** (append-only, dated newest-first, `direction` +
  `status`). Internal strategy, design intent, and guidance stay private; **only released code is
  public** (privacy is structural, not a per-push scrub). Contract: `git pull` the strategy repo at
  session start; commit+push it at session end if changed. Their content NEVER enters this public
  repo (HANDOFF may reference paths only).
- **Skill procedures** — `.claude/skills/<name>/SKILL.md` (authoritative per-skill workflow).
- **Generated reports** (root, skill-written) — `ainative-stats.md`, `seo-progress.md`.

## Load-bearing invariants (full detail in `_GUIDES/the-machine-that-builds-machines.md` §1)

1. **Solo-blog, direct-to-main** — commit subjects are the changelog; human review is the gate.
   *Exception:* a **multi-repo migration/pivot** (e.g. moving platform content to `orionfold/ainative`
   → `orionfold/relay`, republished on orionfold.com) gets a spec + a `_RELAY.md` announce + a branch
   + **destination-first ordering with 301 redirects** — never direct-to-main (no atomic commit
   spans repos; the risk is a half-done state that 404s indexed URLs). See `mac-spark-repo-flow-v1` §4.
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
