# Product-launch article structure

This is the section blueprint for a product article. It is deliberately
different from the tech-writer 8-section deep-dive: the deep-dive is an
argument with steps as evidence; this is a launch with a build story and a
tour. Treat the order as the default reading flow, not a rigid form — but every
published product article should hit all of these beats.

## The frontmatter schema (products collection)

Product articles live in their own content collection at
`products/<slug>/product.md` and validate against a `products` Zod schema in
`src/content.config.ts`. The full proposed schema and the destination-repo
rendering contract are in `_GUIDES/product-articles.md` — read it
before authoring so the frontmatter you emit matches what the site expects.
The fields the skill fills:

```yaml
title: string                 # the launch headline — product + what it is
date: YYYY-MM-DD
author: Manav Sehgal
product_name: string          # "Orionfold Arena"
tagline: string               # one line of positioning (<=120 chars)
summary: string               # <=300 chars, stands alone as the card blurb
hardware: NVIDIA DGX Spark
status: published | upcoming
series: Cockpit               # optional, reuses the article SERIES enum
tags: [array, of, kebab, tags]
signature: ComponentName      # optional card-thumbnail SVG
product_url: string           # optional — where to run/get it
repo_url: string              # optional
fieldkit_modules: [harness, eval, notebook, nim]   # optional
# --- build-metrics block: the infographic's data source ---
build:
  window: "one day (~15 hours)"
  wall_clock_hours: 14.9
  sessions: 12
  assistant_turns: 1130
  tokens_processed: 233169238
  tokens_generated: 972393
  cache_read_tokens: 228083141
  lines_of_code: 12713
  test_cases: 125
  feature_count: 14
  models: ["Claude Opus 4.7"]   # build models, honest mix
  daily_driver: "Claude Opus 4.8"
  harness: "Claude Code"
# --- feature tour: drives the operator-facing gallery ---
features:
  - name: "Cockpit"
    benefit: "One screen to see every artifact, bench, and the warm model's live telemetry."
    screenshot: "screenshots/01-cockpit.png"
  # ...one entry per surface
```

`build` and `features` are what make this a product article rather than a
deep-dive — the destination renders them as the infographic and the tour. Both
are required for a published piece.

## Section blueprint

### 1. The lead — positioning (1–2 ¶)
Name the product and say what it is and who it's for, in plain language, before
anything else. No build story yet, no metrics yet. The reader should know in
fifteen seconds whether this is for them. See `voice-and-positioning.md`
("Positioning first").

### 2. What it unlocks (2–3 ¶)
The researcher's section. Why does this surface change how work gets done on a
Spark? Live experimentation, faster decisions, a tighter prototype loop,
private-by-construction iteration. Make the argument that would stand even with
every screenshot removed. Name concrete things the reader could do *this week*.

### 3. The build story — vision → MVP → production (3–5 ¶ + the infographic)
The honest arc (see `voice-and-positioning.md`, "The vision arc"). The
operator's itch, the unglamorous first slice, the leap to the production tool.
**The build-metrics infographic lands here** — it is the evidence for the "in a
day" claim. Don't just drop the numbers; interpret them (see
`metrics-infographic.md`). This is also where the agentic-coding workflow gets
its due: the models, the Claude Code harness, the caching that made the token
budget what it was.

### 4. The feature tour (the bulk — one block per surface)
The operator's section. Walk each feature in a sensible order (start where the
operator starts — the landing/cockpit — then the surfaces they reach from it).
For each: a benefit-led heading, one screenshot, and 1–3 sentences on what it
does and why it matters in practice. See `feature-tour.md` for the capture
workflow and caption style. This is the longest section; it's allowed to be.

### 5. Built on the substrate (2–3 ¶)
The leverage story, and the one that flatters the whole body of work. The
product was buildable in a day *because* of what already existed: the
`fieldkit` package it's a thin surface over (name the modules and what each one
powers in the product), and the AI Field Notes articles + published artifacts
that gave it real data to display. Make explicit how much the product is
"assembly of compounding work" rather than "from scratch." If `fieldkit`
abstractions unlocked specific features cheaply, say which and how.

### 6. The workflow, generalized (2–3 ¶)
Zoom out from this one product to the repeatable method: how a solo operator on
a Spark, driving Opus models through Claude Code over a maturing toolkit, turns
an idea into a production surface in a day. This is the part a reader takes with
them even if they never run the specific product. Keep it grounded in what
actually happened — reference the real metrics, not aspirations.

### 7. Get it / run it / what's next (1–2 ¶)
Where to find it, how to run it (the one-line command if there is one), and an
honest line on what's next. Close on the product, not on the author.

## Length and shape
- Sweet spot: **1,800–3,500 words**. The feature tour makes product articles run
  long; that's fine, because much of the length is scannable captions.
- The infographic and the screenshot tour mean a product article carries more
  visual weight than a deep-dive — lean into it.
- One optional architecture diagram (e.g. how the product sits over fieldkit
  and the Spark) can live in section 3 or 5 if it reinforces the leverage story.
  Reuse the tech-writer `fn-diagram` archetypes and invariants
  (`../../tech-writer/references/visualizations.md`) so it reads in the same
  hand as the rest of the site. A diagram is optional here, unlike a deep-dive.

## What a product article is NOT
- Not a changelog or release notes (no exhaustive version-by-version list).
- Not API docs (link to those; don't reproduce them).
- Not a tutorial (it shows what the product does, not how to rebuild it
  step-by-step — that's a tech-writer deep-dive's job).
- Not a comparison piece. No competitors, named or implied.
