<!--
  Session handoff for ainative-business.github.io.
  Updated at the end of every Claude Code session with anything the next
  session needs to pick up. Parallels source's ai-field-notes/SYNC-HANDOFF.md
  but for destination-side work (catalog chrome, marketing surfaces, deferred
  items the user owns end-to-end).

  Convention:
  - Replace the "Open items" section each session; do NOT append.
  - "Recent decisions" is the running log — append, don't replace.
  - Last reset: 2026-05-14.
-->

# HANDOFF — ainative-business.github.io

**Last session:** 2026-05-14
**Last destination commit:** `85f9307` — feat(field-notes): publish becoming-a-gguf-publisher-on-spark + land first kind:quant manifest

## Open items (replace each session)

### 1. `/artifacts/quants/` catalog scaffold

**Status:** deferred from the 2026-05-14 `/sync-field-notes` sweep. First Phase-2 manifest (`src/content/artifacts/finance-chat-gguf.yaml`) is on disk but dormant until the catalog renders it.

**Work to do:**
1. **Add `artifacts` collection to `src/content.config.ts`.** Mirror the schema from `ai-field-notes/src/content.config.ts` (around the `artifacts` block — fields: `slug`, `kind`, `class`, `base_model`, `hf_repo`, `variants[]`, `perplexity{}`, `spark_tokens_per_sec{}`, `sustained_load_minutes`, `vertical_eval{}`, `vertical_eval_name`, `license.tier`, `article`, `published_at`). Constrain `kind` to a closed enum: `quant`, `lora`, `adapter`, `embedder`, `dataset`, `space`, `benchmark`.
2. **`src/pages/artifacts/quants/index.astro`** — catalog index page. Lists every `kind: quant` artifact with slug + base_model + variant count + license tier + linked-article excerpt. **Use plural `/quants/`** per `mirrors/destination-overrides.md` — that's the catalog-family convention (`/loras/`, `/adapters/`, etc.). Ignore the singular `/artifacts/quant/` in source's SYNC-HANDOFF prose — that was source-side shorthand.
3. **`src/pages/artifacts/quants/[slug]/index.astro`** — detail page rendering the four-axis card (perplexity, spark_tokens_per_sec, vertical_eval, sustained_load_minutes) mirroring the HF model card.
4. **Optional wire-back:** add a one-line "Catalog page" link from `articles/becoming-a-gguf-publisher-on-spark/article.md` to the new `/artifacts/quants/finance-chat-gguf/` once it's live. The article currently links directly to the HF repo URL, so this is polish, not gating.

**Non-blockers:** the article ships today with all its inbound links intact (HF, direct download, etc.). The catalog is additive marketing surface.

### 2. Source PR #3 awaiting merge

**URL:** https://github.com/manavsehgal/ai-field-notes/pull/3

**Why it matters:** until this merges, every `/sync-field-notes` run will re-introduce the build-breaking `series: 'Autoresearch'` regression in two seeds (`claw-eval-live-on-spark`, `scientific-foundation-models-as-tools`). Each sync currently requires the same one-line correction post-copy.

**Next session action:** if the PR has merged, no follow-up needed. If still open, hold or merge before the next content sync.

## Recent decisions (running log — append, don't replace)

### 2026-05-14
- **Destination-side HANDOFF.md convention adopted.** This file is the canonical destination-side session handoff, updated every session. Parallels source's `ai-field-notes/SYNC-HANDOFF.md`. Auto-memory still tracks durable cross-session context (preferences, project state); HANDOFF.md tracks active in-flight work.
- **Catalog URL convention: plural.** `/artifacts/quants/`, not `/artifacts/quant/`. Settled per `mirrors/destination-overrides.md` over the source-handoff prose. Applies to all seven catalog kinds.
- **Phase 2 artifact manifests went live.** First `kind: quant` manifest landed at `src/content/artifacts/finance-chat-gguf.yaml`. `FIELDKIT_MODULES` enum extended with `quant` + `publish` to admit the article frontmatter.
- **Customer-link audit pattern introduced** as `feedback_customer_link_audit` memory. Triggered when an article is linked from a public product card (HF README, Civitai); four failure modes documented.
