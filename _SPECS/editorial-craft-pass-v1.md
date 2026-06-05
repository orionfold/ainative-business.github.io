---
project: editorial-craft-pass
version: v1.0
status: DRAFT (decisions PROPOSED 2026-06-05 — 4 scoping forks confirmed by operator; confirm full spec before build)
created: 2026-06-05
authoritative: Spark
---

# Editorial Craft Pass v1.0 — Project Specification

> A **site-wide craft pass** over every published article: make the prose read **human-written**
> (cut the high-signal LLM tells, vary punctuation off the em-dash default), raise **readability for
> first-time AI learners without diluting technical depth for researchers** (layered — body stays
> dense, accessibility rides in the explainer sidebar), and **diversify the visualizations** (add a
> build-time static-chart path beside the hand-authored `fn-diagram` system; more chart types, more
> color, more variety). The same guidelines are folded back into the **`tech-writer`** and
> **`product-writer`** skills so every *future* article inherits the craft. **Hard constraint: no
> change to slugs / URLs / titles** — SEO + Google Search Console indexing must not regress.
>
> Sibling spec to the content skills, not an extension of any one of them. It owns the **craft layer**:
> prose style, readability, and visualization diversity across the whole corpus + the two authoring
> skills. The *build* is **pilot-gated** — prove the playbook on 2–3 representative articles, get
> operator sign-off, then sweep the rest in themed waves.
>
> **Operator-confirmed scope (2026-06-05, four forks):** (1) prose = **reduce & balance**, NOT a hard
> em-dash ban; (2) viz = **build-time static charts + keep hand-authored SVG**, no client-side JS;
> (3) rollout = **pilot 2–3 → gate → batch in waves**; (4) readability = **layered** (technical body +
> accessible explainers + sentence-level clarity).

## 1. Context

### Why this project

The blog now has **42 published articles** (+ 11 `upcoming` placeholders) authored over months through
the `tech-writer` / `product-writer` skills. Three craft gaps have accumulated:

1. **LLM tells.** The house voice leans hard on the em-dash and a handful of generative-model
   cadences (rule-of-three lists, "it's not just X, it's Y", `delve`/`leverage`/`underscore`/`boasts`,
   uniform paragraph rhythm, reflexive bolding). Individually fine; in aggregate they read as
   machine-written and undercut the "named POV from one power-user" differentiator.
2. **Readability ceiling.** The prose assumes a technically-literate reader throughout. That serves
   AI researchers but loses the **first-time AI learner** the explainer layer was *meant* to onboard —
   and the explainer layer is under-used on the older articles.
3. **Visual monotony.** Every figure is a hand-authored inline SVG in the `fn-diagram` system (six
   architecture archetypes, one indigo accent hue) plus a signature thumbnail. There is **no real
   data-chart path** — timelines, distributions, and benchmark comparisons are drawn by hand or
   skipped. Color and style diversity is low across the corpus.

The fix is one coordinated pass + a permanent upgrade to the two skills so the gap doesn't reopen.

### What exists today (the substrate this builds on)

- **Prose voice:** `tech-writer/references/voice-and-style.md` (drift signals, uber-theme ties,
  honesty patterns, the customer-linked failure-mode audit).
- **Explainer layer:** `tech-writer/references/explainers.md` — six directive types (`:::define`,
  `:::why`, `:::pitfall`, `:::math`, `:::deeper`, `:::hardware`), 6–10/article, the `/glossary/`
  auto-collect, rendered via `src/lib/remark-explainers.mjs`.
- **Visualizations:** `tech-writer/references/visualizations.md` + `src/styles/diagrams.css` — the
  `fn-diagram` archetypes, the validator `scripts/verify_svg.sh` (hard invariants), signature
  components under `src/components/svg/`. Existing palette = OKLCH hue-250 indigo primary + nine
  `--svg-accent-*` hues (blue/teal/green/green-alt/cyan/purple/orange/red/pink) **already defined**
  but barely used.
- **Site ordinal is git-first-add time** (`src/lib/article-order.mjs`), **not** `frontmatter.date` —
  so *re-committing* an existing article's body does **not** reorder it. Only delete+recreate (new
  first-add) or a slug change would. This is the key SEO-safety lever (ECP-10).
- **Existing static-figure tooling:** `fieldkit.viz` (matplotlib + `great_tables`, polars) already
  emits themed static figures/tables for the notebook pipeline — a candidate chart backend.
- **Verify loop:** `verify_article.sh` (frontmatter + image refs + slug↔folder + secret scan + SVG
  invariants) and the two render verifiers; `build:og` (CI) regenerates OG cards from title+summary.

## 2. Decisions

### A — Prose craft / de-LLM-tell (operator: *reduce & balance*)

- **ECP-1 — No hard em-dash ban; rebalance punctuation.** Em-dashes stay legal (they are established
  voice), but they stop being the *default* connector. Target: cut em-dash **density** materially
  (rough aim ≤ ~3 per 1,000 words, down from the current ~8–12) by rewriting to commas, colons,
  parentheses, or sentence breaks where those read more naturally. The test is "varied, human
  punctuation," not a count quota.
- **ECP-2 — The tell taxonomy (flag-and-rewrite list).** The craft pass and the lint tool target,
  in priority order: (a) **rule-of-three** noun/clause triads used reflexively; (b) **"it's not just
  X, it's Y" / "not only … but also"** antithesis scaffolds; (c) **filler openers** — "It's worth
  noting", "In essence", "Importantly", "Ultimately", "At its core"; (d) **generative-register
  vocabulary** — `delve`, `leverage` (as verb), `underscore`, `boasts`, `realm`, `tapestry`,
  `seamless`, `robust`, `crucial`, `pivotal`, `testament`; (e) **reflexive bolding** of non-term
  phrases; (f) **uniform paragraph cadence** (every paragraph the same length / same 3-sentence
  shape); (g) **summary-restating closers** ("In conclusion", "In summary"). The list lives in the
  new `prose-craft.md` (ECP-11) and is the lint tool's ruleset (ECP-12).
- **ECP-3 — Voice guardrail: human, not flattened.** The pass must *increase* sentence-length
  variance and concreteness, not sand the prose into uniform short declaratives (that is its own
  tell). First-person POV, honest-friction passages, and the named perspective are *preserved and
  strengthened*. ECP-R1 is the risk this guards.

### B — Readability for the widest audience (operator: *layered*)

- **ECP-4 — Body stays at full technical depth.** Researchers must never feel talked-down-to. The
  main prose keeps its rigor, equations, and exact numbers. The readability lift comes from
  **sentence-level clarity** (shorter sentences, fewer nested clauses, concrete subject-verb openings,
  unpacking the densest noun stacks) — not from removing technical content.
- **ECP-5 — Accessibility on-ramps ride in the explainer sidebar.** First-time-learner support is
  *added beside* the body, not mixed into it: every article reaches the 6–10 explainer target, with
  enough `:::define` to anchor the domain terms a newcomer hits, ≥1 `:::why` reframing the stakes in
  plain language, and the bracket labels readable as a standalone spine. Older articles below 6
  explainers are brought up to target.
- **ECP-6 — Soft readability metric (advisory, body-only).** The lint tool reports a Flesch–Kincaid
  / reading-ease score on the body prose (excluding code, math, tables). It is a **report, not a
  gate** — a per-article before/after number to confirm the pass moved the needle, never a hard
  threshold that would force dilution. Aim: a measurable reading-ease improvement while staying in
  the "technical-but-clear" band.

### C — Visualization diversity (operator: *build-time static charts + keep SVG*)

- **ECP-7 — Three figure lanes, by job.** (1) **Architecture → hand-authored `fn-diagram`** (the six
  archetypes, unchanged system, expanded color use). (2) **Data → build-time static charts** (new):
  timelines, bar/waterfall, distributions, scatter, small-multiples, head-to-head comparisons. (3)
  **Tables/statistical → `fieldkit.viz`** (`great_tables` / matplotlib) where a styled table or a
  stat plot beats both. The chart-vs-diagram-vs-table decision rule goes in `charts.md` (ECP-11).
- **ECP-8 — Charts are static SVG emitted at build; no client-side JS.** Preserves the "calm page",
  zero-JS, accessible aesthetic. Charts render to SVG either committed as article assets or generated
  by an Astro/Node build step. **No interactive/hover charting library on the client.**
- **ECP-9 — Chart library: research set + pilot spike.** Candidates to evaluate in S0 (ECP-15),
  scored on SVG-native output, dark/light theming, aarch64+CI build, and authoring ergonomics:
  - **Observable Plot** (Node → SVG via jsdom) — concise grammar, broad chart types. *Recommended
    primary* for in-page charts.
  - **Vega-Lite** (→ Vega → `View.toSVG()` in Node) — declarative JSON specs, heavier dep.
  - **D3** (server-side via jsdom) — maximal control, most code.
  - **ECharts SSR** (Node → SVG string) — rich type catalog, SSR-to-SVG supported.
  - **`fieldkit.viz` / matplotlib + great_tables** (Python build step) — *already on the box*, themed,
    proven in the notebook pipeline; the recommended lane for statistical plots + styled tables.
  - S0 picks **one** in-page primary (lean Observable Plot) + keeps `fieldkit.viz` for stat/table.
- **ECP-10 — Charts must be theme-reactive via the existing tokens.** Generated SVG consumes the
  `--svg-*` / `--color-*` OKLCH variables (post-process the library's palette output to tokenized
  classes/`currentColor`) so charts flip dark/light exactly like `fn-diagram`s. Hardcoded hex is
  forbidden (same rule as the SVG validator). `verify_svg.sh` is extended to lint generated charts
  for the no-hex + role/aria + token-palette invariants.
- **ECP-11 — Color & style diversity, bounded.** Put the nine `--svg-accent-*` hues to work: a
  per-series or per-article accent assignment (so the corpus reads varied, not monochrome) + the
  expanded chart-type catalog. The per-article figure ceiling rises from 2 to **3** *only when the
  third is a data chart that earns it* (the taste test in `visualizations.md` still gates each one).

### D — Skill upgrades (so future articles inherit the craft)

- **ECP-12 — New + updated references in BOTH skills.** Author `tech-writer/references/prose-craft.md`
  (the tell taxonomy + punctuation-variety rules + the human-not-flattened guardrail + the readability
  rubric) and `tech-writer/references/charts.md` (the chart-vs-diagram-vs-table decision rule, the
  chosen library + the theming recipe, the chart-type catalog). Update `voice-and-style.md` (cross-ref
  prose-craft, fold in the punctuation-variety note) and `visualizations.md` (add the charts lane +
  cross-ref). **Mirror the same prose-craft + charts guidance into `product-writer`** (it has its own
  voice surface — `_GUIDES/product-articles.md` + the product-writer SKILL.md). Add the explainer
  on-ramp + readability expectation to both skills' `draft` playbooks.
- **ECP-13 — Lint + readability tooling.** Build `scripts/lint_prose.mjs` — flags the ECP-2 tells,
  reports em-dash density, and prints the ECP-6 reading-ease score per article (and a corpus summary).
  Wire it **advisory** into `verify_article.sh` (warns, never blocks — same posture as today's
  `verify_svg` warn). Add a `--report` mode that writes a corpus-wide before/after table.

### E — SEO / Search-Console safety (hard constraint)

- **ECP-14 — Freeze the URL- and index-bearing fields.** **Never** change: the **slug** (the URL),
  the **folder name**, the **`title`** (drives `<title>` + OG + GSC), the **`date`**, or the article's
  **git first-add identity** (no delete+recreate — edit in place so the ordinal + canonical URL are
  preserved). **`summary`** may be improved *only* if it stays ≤300 chars and keeps its existing
  keywords (low-risk, opt-in per article; default is leave it). Body + figures + explainers are the
  editable surface. A git-diff guard (ECP-16) enforces the freeze mechanically.
- Re-crawl note: editing body content updates `sitemap` `lastmod` on rebuild and prompts a normal
  Google re-crawl — this is benign (content freshness), the regression risk is *structural* (URL/title)
  changes only, which the freeze forbids.

### F — Rollout (operator: *pilot → gate → waves*)

- **ECP-15 — S0 foundations gate.** Before any article is touched: write the two references (ECP-12),
  build the lint tool (ECP-13), and **spike the chart library** (ECP-9) — prove one themed static SVG
  chart renders correctly in **both** dark and light, builds on aarch64 + CI, and passes the extended
  validator. Update both skills. Gate: playbook + tooling exist and the chart spike is green.
- **ECP-16 — Per-article workflow + frozen-field guard.** Each article pass: (1) prose craft (ECP-1/2/3),
  (2) readability + explainer top-up (ECP-4/5), (3) viz upgrade where a chart/diagram earns it
  (ECP-7…11), (4) run `lint_prose.mjs` + `verify_article.sh` + build + both render verifiers,
  (5) **frozen-field guard**: `git diff` must show **zero** change to `title`/`date`/slug/folder
  (a scripted check on the frontmatter diff), (6) log before/after lint+readability numbers in the
  article's `transcript.md`.
- **ECP-17 — Pilot then waves.** **S1 pilot = 3 representative articles** (one Foundations install
  piece, one series-anchor essay, one arithmetic-heavy piece) → **operator side-by-side review gate**
  (the "after" must read human + accessible + visually richer without losing rigor) → calibrate the
  skills from what the pilot teaches. **S2…S6 = themed waves** over the remaining ~39 published,
  grouped by series/stage (~8/wave), each wave self-contained (pass + verify + build + commit).
  **S7 = corpus sweep**: site-wide lint/readability report, OG-regen + frozen-field audit, full build,
  stats refresh, final review.
- **ECP-18 — Upcoming placeholders deferred.** The 11 `status: upcoming` articles are *not* in scope
  now; they inherit the upgraded skills automatically when promoted to `published`.

## 3. Risks

- **ECP-R1 — Voice flattening.** Over-stripping tells yields generic, choppy prose (its own tell).
  *Mitigation:* reduce-&-balance (ECP-1), the human-not-flattened guardrail (ECP-3), the pilot review
  gate, and sentence-variance as an explicit goal.
- **ECP-R2 — SEO regression.** Any slug/title drift breaks URLs + GSC. *Mitigation:* the ECP-14 freeze
  + the ECP-16 scripted frozen-field guard (commits blocked if title/date/slug changed).
- **ECP-R3 — Chart theming breakage.** A static chart with baked colors is unreadable in one theme.
  *Mitigation:* tokenized palette (ECP-10), extended `verify_svg.sh`, dual-theme screenshot check in
  the per-article workflow.
- **ECP-R4 — Scope blowout.** 42 articles × deep edits is large. *Mitigation:* pilot calibration +
  bounded waves (~8/article budget) + the skills carrying the load for future pieces.
- **ECP-R5 — Technical dilution.** The readability pass softens rigor and researchers bounce.
  *Mitigation:* the layered decision (body untouched in depth, ECP-4), accessibility quarantined to
  explainers (ECP-5), diff review on the pilot.
- **ECP-R6 — Build-tooling weight / aarch64.** The chart backend must build on the Spark + CI without
  ballooning the build. *Mitigation:* S0 spike validates both; prefer **pre-rendered SVG committed as
  assets** so the runtime Astro build stays light (generation is an authoring-time step, not a
  per-build cost).
- **ECP-R7 — Stale screenshots surface mid-pass.** Some older articles have UI screenshots that have
  drifted from current product state. *Mitigation:* out of scope for this pass (note them; refresh is
  a separate `apply-screengrabs` / `tech-writer polish` task) unless trivially fixable in-pass.

## 4. Session-by-session execution

The detailed, checkable session breakdown lives in **`HANDOFF.md`** (this spec's authoritative task
list, per project convention). High-level shape:

| Session | Scope | Gate |
|---|---|---|
| **S0** | Foundations: `prose-craft.md` + `charts.md`, `lint_prose.mjs`, chart-lib spike (themed SVG, dark+light, CI), update `tech-writer` + `product-writer`. | Playbook + tooling exist; spike green. |
| **S1** | Pilot: 3 representative articles, full playbook, **operator side-by-side gate**, calibrate skills. | Operator sign-off on the "after". |
| **S2–S6** | Themed waves over the remaining ~39 published (by series/stage, ~8/wave): prose + readability + viz + verify + commit. | Per-wave: lint + build + verifiers green; frozen-field guard clean. |
| **S7** | Corpus sweep: site-wide lint/readability report, OG-regen + frozen-field + GSC-safety audit, full build, stats refresh, final review. | Corpus report; zero frozen-field diffs. |

## 5. Out of scope

- Slug / URL / title / date changes (ECP-14 forbids).
- The 11 `upcoming` placeholders (ECP-18 — inherit via the skills at promotion).
- Client-side interactive charts (ECP-8 — static SVG only).
- Screenshot refresh for drifted product UI (ECP-R7 — separate task).
- New articles / new content (this is a craft pass over existing prose + figures).
- Design-system / global CSS changes beyond adding the chart theming tokens (that stays
  `frontend-design` territory).

---

> **Status:** DRAFT — the four scoping forks are operator-confirmed (2026-06-05); the full decision
> set ECP-1…18 + risks await a confirm-before-build green-light. Queued in `HANDOFF.md` after the
> astrodynamics ship-tasks. Sibling to `tech-writer` / `product-writer`; cross-links
> `references/voice-and-style.md`, `references/visualizations.md`, `references/explainers.md`,
> `_GUIDES/product-articles.md`.
