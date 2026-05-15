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

**Last session:** 2026-05-15 (cyber-vertical sweep — third Orionfold quant card)
**Last destination commit (pre-sweep):** `ae23184` — chore(handoff): forward open items for next session
**Push status:** prior session's commits (`d41b096` feat + `cc02e3f` + `ae23184` handoff) live on `origin/main`. This sweep's changes are uncommitted in working tree — see `git status`.

## Open items (replace each session)

### 1. Article wire-back propagation to source (carry-forward)

**Status (unchanged from previous session):** Three destination-side articles now carry the `Catalog page: …` footer (`becoming-a-gguf-publisher-on-spark`, `becoming-a-legal-curator-on-spark`, `becoming-a-cyber-curator-on-spark` — added this session). Each sync that pulls these articles from source surfaces a phantom diff (destination has the line, source doesn't); `git checkout HEAD -- <article>` after sync is the established workaround. Confirmed working this session.

**Resolution rule when the conflict appears:** keep destination's. The catalog link is destination-only chrome (this site has the catalog; source's HuggingFace cards don't). Article body remains source-of-record. Cleanest fix is a source-side PR replicating the three wire-back lines — author it the next time you're in the source repo.

### 1a. `recommended_variant` override in `securityllm-gguf.yaml` (destination-side)

**Status:** This session added a `recommended_variant: Q4_K_M` field to `src/content/artifacts/securityllm-gguf.yaml` to override the picker's rank-avg pick (Q5_K_M → Q4_K_M, matching the source article's narrative). Source's manifest doesn't have this field. Next sync that overwrites this manifest will lose the override. Add `git checkout HEAD -- src/content/artifacts/securityllm-gguf.yaml` to the post-sync restore step alongside the three article wire-backs, OR upstream the `recommended_variant` field to source on the next source-side PR.

**Schema is forward-compatible:** the field is `z.string().optional()` so source-shipped manifests without it continue to work; the picker falls through to rank-avg when unset. Finance + Saul don't currently have the field set — they keep their existing picks (Q6_K, Q5_K_M).

### 2. SHIPPED-flip PR back to source

**Status:** Contract sweep generated the PR plan. Title: `mirror: SYNC-HANDOFF.md SHIPPED — 2026-05-15-cyber-vertical (<destination-commit>)`. Body cites the destination commit hash. Open after this session's commit lands so the hash in the body matches reality. No rename status flips this cycle (`renames_to_replay: []`).

## Recent decisions (running log — append, don't replace)

### 2026-05-15 (cyber-vertical sweep — third Orionfold quant card)
- **Source release `2026-05-15-cyber-vertical` swept.** Single source commit `dd81a29` (Add cyber-vertical card: Orionfold/SecurityLLM-GGUF + CyberMetric mini-eval). Auto-flow: 1 new article (`becoming-a-cyber-curator-on-spark`), project-stats refresh (36→37 articles, 121,613→124,081 words), sequence manifest rewrite (cyber slots into ordinal sequence). Zero fieldkit source changes — the v0.4.1 publishing surface generalized to vertical #3 as designed.
- **Third Phase-2 artifact manifest landed.** Byte-copied `src/content/artifacts/securityllm-gguf.yaml` from source (license.tier=free, license.model=apache-2.0, vertical_eval_name="CyberMetric (n=50, mcq_letter)"). Catalog now renders three cards side-by-side: `securityllm-gguf` (15 May) → `saul-7b-instruct-v1-gguf` (14 May) → `finance-chat-gguf` (13 May), chronological-desc as source handoff recommended. No catalog scaffolding work — `getCollection` + `getStaticPaths` enumerate manifests dynamically; new card + new detail route auto-generated.
- **Two phantom diffs handled.** `becoming-a-gguf-publisher-on-spark` + `becoming-a-legal-curator-on-spark` surfaced as updated in the sync diff because destination has the catalog wire-back footer added during the 2026-05-15 catalog ship; source doesn't. Resolution per Open item #1 (previous session): `git checkout HEAD -- <both>` immediately after sync. Article bodies unchanged upstream — confirmed by line-diff (only the trailing `Catalog page:` block differs).
- **Third wire-back added.** Pattern continued for cyber article — `Catalog page: /artifacts/quants/securityllm-gguf/` appended after the closing line "Three verticals down, one machine." Three articles now carry destination-only wire-back chrome; will need the same `git checkout` treatment on each future sync until source-side PR lands.
- **Sweet-spot divergence flagged then resolved via option (a).** Catalog page first surfaced `Q5_K_M` (balanced rank-avg winner) while the article body recommends `Q4_K_M` (top of bench + throughput, worst perplexity). User picked the manifest-override resolution: added optional `recommended_variant: z.string()` to artifacts schema in `src/content.config.ts`, made `pickSweetSpot()` in `src/lib/artifacts.ts:93` return the override directly when set + present in candidates, threaded the field through three call sites (`QuantCard.astro`, `QuantSignature.astro`, `[slug]/index.astro`), and set `recommended_variant: Q4_K_M` on `securityllm-gguf.yaml`. All three surfaces (index card, detail page sweet-spot chip, SVG signature point) now show Q4_K_M. Finance + Saul unaffected — no override field set, rank-avg keeps their existing picks.
- **Build clean.** 383 pages (was 376 at the catalog ship) — net +7: cyber article + cyber artifact detail + OG card + tag pages for new tags (`cyber`, `security`, `orionfold`, `cybermetric`, `zephyr`).
- **Contract sweep clean.** `mirrors/destination-overrides.md` confirmed present at source (May 13, 7.6KB; previous HANDOFF Open item #2 was outdated). No pending rename replays. Phase 2 ACTIVE with 3 manifests on disk. SHIPPED-flip PR plan generated — open after this session's commit lands.
- **Source handoff prose vs project-stats discrepancy.** Handoff prose says "41 articles total"; project-stats.json says 37. Mechanical numbers track stats (37 is what's synced). Likely prose was forward-looking author note; not a destination issue.

### 2026-05-15 (production verification — catalog deploy closed)
- **Open item #1 (previous session) closed.** User manually verified the `/artifacts/quants/` catalog on the deployed `ainative.business` — all four routes live, trailing slashes preserved, heatmap and sweet-spot chips render correctly in both themes, nav + footer placements as planned. Item dropped from the active list; remaining items renumbered (article wire-back → #1, `mirrors/destination-overrides.md` → #2).

### 2026-05-15 (`/artifacts/quants/` catalog scaffold ships)
- **Open item #1 resolved.** Catalog feature lives at `/artifacts/` (hub), `/artifacts/quants/` (index, 2 cards), `/artifacts/quants/finance-chat-gguf/`, and `/artifacts/quants/saul-7b-instruct-v1-gguf/`. Build clean at 376 pages (was 372). Verified in browser across dark + light themes; trailing slashes enforced; console clean.
- **Schema enum mirrors source verbatim.** HANDOFF prose previously said `embedder`/`benchmark`; source `ai-field-notes/src/content.config.ts` uses `embed`/`bench`. Destination adopts source's enum (`quant`, `lora`, `adapter`, `embed`, `reranker`, `dataset`, `space`, `bench`) — eight kinds, not seven. URL plural map lives in `src/lib/artifacts.ts:kindToSegment`: `quant→quants`, `embed→embeds`, `bench→benches`, etc.
- **Aesthetic commit: "research spec-sheet, treated as poster."** Each artifact has a per-card SVG **tradeoff-curve signature** (perplexity vs spark_tokens_per_sec, sweet-spot point glows) — same role as field-notes' signature SVG aside, but data-derived. Detail page elevates a variant × axis table where each cell carries a `linear-gradient` heatmap bar scaled to column rank, making sweet-spot variants visually emergent without explicit hierarchy.
- **`pickSweetSpot` excludes unquantized reference variants.** First smoke pass picked `F16` as the sweet spot on `finance-chat-gguf` because perplexity ties + vertical_eval ties outweighed F16's mediocre throughput in the rank-average score. F16 by GGUF convention is the source weights being quantized FROM — not a recommended user download. Picker now filters `F16`/`BF16`/`FP16`/`F32` out of the candidate set (but keeps them in the heatmap ranking so the table scale stays honest). Re-pick: `Q6_K` for finance-chat, `Q5_K_M` for Saul — both match the source articles' written recommendations.
- **Article wire-back lines added.** Two articles (`becoming-a-gguf-publisher-on-spark`, `becoming-a-legal-curator-on-spark`) gained a closing `Catalog page: …` link. Source-side propagation is an open question — these were destination-edited; next sync may surface a conflict if source-side authors edit the same closing region.
- **Primary nav addition (reversed from plan).** User overrode the "footer-only" call mid-session — `/artifacts/` now appears in: (a) desktop nav between Field Notes and Fieldkit, (b) mobile menu in the same slot, (c) footer "Reading" column between Field Notes and RSS (moved from Platform column). The "research output" pairing with Field Notes is consistent across all three surfaces.
- **Memory note for next session.** When source ships its second quant catalog kind (likely `embed` or `bench`), the destination already has the `/artifacts/` hub set up to render it as an active tile — only a new `src/pages/artifacts/{segment}/index.astro` and matching detail route are needed. Schema is already permissive.

### 2026-05-14 (fieldkit v0.4.1 sweep — Saul vertical card)
- **Bundled release swept clean.** Source range `7f1159e..HEAD` (6 commits). Content auto-flow: 1 new article (`becoming-a-legal-curator-on-spark`), 1 fieldkit doc updated (`eval.md` — `open_book` + `subset` kwarg catch-up), `_version.py` 0.4.0→0.4.1, sequence manifest rewrites (new slug slots into ordinal sequence), project-stats refresh (35→36 articles, 120,093→121,613 words, 24,026→24,185 LOC) with recall@5 override preserved.
- **Second Phase-2 artifact manifest landed.** Byte-copied `src/content/artifacts/saul-7b-instruct-v1-gguf.yaml` (`license.tier=free`, `license.model=mit`, `vertical_eval_name="LegalBench (n=50, contains)"`). Now two manifests on disk, both dormant — strengthens the case for the `/artifacts/quants/` catalog scaffold (Open item #1).
- **Build clean.** 372 pages (was 367 last v0.4.0 sweep — net +5 from `dist/og/field-notes/` OG card for the new article + the new article page + a few derived routes). New article route confirmed at `dist/field-notes/becoming-a-legal-curator-on-spark/index.html` (59 KB rendered HTML, full h1/h2 hierarchy intact). Fieldkit landing reads `v0.4.1` via the `_version.py` thread-through that landed in the v0.4.0 sweep.
- **Customer-link audit not triggered.** The Saul article is linked from the HF README card, which means [[feedback_customer_link_audit]] applies — but the source-side article body already passed the audit in the source repo before commit (`status: published` in source). No destination-side audit needed.
- **No UX brainstorm needed.** Handoff was content-only (`new_top_level_pages: []`, `breaking_changes: []`, `destination_overrides_to_preserve: []`). The artifact manifest copy was the only mechanical-new-files item; everything else auto-flowed through the scripts.
- **Source SHIPPED flip to send.** Contract sweep produced the PR plan with destination commit citation; companion PR opens after this session's commit so the hash in the PR body matches the sweep that actually shipped. No rename status flips this cycle (`renames_to_replay: []`).

### 2026-05-14 (no-op sweep + script-fix touch)
- **Third `/sync-field-notes` invocation of the day, no-op on content.** Diff clean; contract sweep clean (`status: SHIPPED` in YAML + `✅ STATUS: SHIPPED` in HTML comment; renames all `complete`/`source-applied`; 1 dormant artifacts manifest). Source handoff `swept_by` already cites `f7ea7aa`. Item 2 from the previous Open-items list (source PR back) is resolved — the upstream flip landed in a prior cycle, which is why this sweep had nothing to do.
- **`contract.flip_handoff_to_shipped` regex extended to YAML frontmatter form.** Split `_HANDOFF_STATUS_RE` into `_HANDOFF_STATUS_HTML_RE` (`⚠️ STATUS: NEW`) and `_HANDOFF_STATUS_YAML_RE` (`^status: NEW$`, multiline). Function now flips either or both — important for transitional releases that carry both markers, which was the v0.4.0 case. Four-shape sanity test (yaml-only / html-only / both / already-shipped) passes; live sweep against current source still reports "No flip needed" as expected. Addresses the follow-up note flagged in the previous session's Open items.

### 2026-05-14 (fieldkit v0.4.0 sweep)
- **fieldkit v0.4.0 swept.** Two new top-level modules (`publish`, `quant`) plus `eval`/`capabilities`/`nim`/`rag`/`cli` drift fixes shipped to PyPI 2026-05-14 (`pypi.org/project/fieldkit/0.4.0/`). Mirror sweep auto-flowed: 1 article frontmatter (`hf_url:` field), 7 fieldkit docs (2 new, 5 modified), `fieldkit/_version.py` 0.3.0→0.4.0, project-stats LOC 23,728→24,026.
- **`hf_url` schema extension.** `src/content.config.ts` articles schema gains optional `hf_url: z.string().url().optional()` — first article using it is `becoming-a-gguf-publisher-on-spark`. Backwards-compatible; existing articles render identically.
- **Landing page dynamic-derive applied.** Three fieldkit landing components got the v0.4.0 anti-drift treatment: `FieldkitProblem.astro` now reads module count + list from `FIELDKIT_MODULES` (was hardcoded `'7'` + 7-name string); `FieldkitModules.astro` adds `quant`/`publish` taglines + NUMBER_WORDS map driving the "in {N} imports" headline (rendered "in nine imports"); `FieldkitCli.astro` accepts `version` prop, threaded from `src/pages/fieldkit/index.astro`. Customize note: kept `/field-notes/` URL on the article-count KPI (source uses `base` which would render as `/`).
- **Build clean.** 367 pages built, no schema errors. Rendered CLI demo shows `0.4.0`; module list shows 9 modules with comma+space wrapping.

### 2026-05-14 (earlier — no-op sweep + handoff convention)
- **Destination-side HANDOFF.md convention adopted.** This file is the canonical destination-side session handoff, updated every session. Parallels source's `ai-field-notes/SYNC-HANDOFF.md`. Auto-memory still tracks durable cross-session context (preferences, project state); HANDOFF.md tracks active in-flight work.
- **Catalog URL convention: plural.** `/artifacts/quants/`, not `/artifacts/quant/`. Settled per `mirrors/destination-overrides.md` over the source-handoff prose. Applies to all seven catalog kinds.
- **Phase 2 artifact manifests went live.** First `kind: quant` manifest landed at `src/content/artifacts/finance-chat-gguf.yaml`. `FIELDKIT_MODULES` enum extended with `quant` + `publish` to admit the article frontmatter.
- **Customer-link audit pattern introduced** as `feedback_customer_link_audit` memory. Triggered when an article is linked from a public product card (HF README, Civitai); four failure modes documented.
- **Source PR #3 merged** (`mirror: SYNC-HANDOFF SHIPPED + SYNC-RENAMES.log status flip — 2026-05-14 orionfold-finance-chat-gguf`, merged 05:45 UTC). Resolves the recurring `series: 'Autoresearch'` seed-regression that previously needed a one-line correction every sync.
- **No-op `/sync-field-notes` sweep (second of the day).** Source has one post-handoff commit `ab6e385` (`fix(fieldkit.publish): model_license plumbing + auto-rendered ## How to run defaults`). Out-of-scope for this skill: lib code (`fieldkit/src/.../publish/__init__.py`), tests, runner scripts (`g3_*.sh|py`), `src/content.config.ts` (DO NOT touch list), and `src/content/artifacts/finance-chat-gguf.yaml` (destination-authored per `mirrors/destination-overrides.md`). `fieldkit/_version.py` byte-identical between source and target. Articles diff empty; contract sweep clean (no pending renames). Nothing copied.
