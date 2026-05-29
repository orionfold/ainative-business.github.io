---
title: "__SLUG__: TODO launch headline — product + what it is"
date: 2026-01-01
author: Manav Sehgal
product_name: "TODO Product Name"
tagline: "TODO one line of positioning — what it is, for whom (<=120 chars)"
summary: "TODO <=300 chars, stands alone as the card blurb. Lead with what the product is and who it's for."
hardware: NVIDIA DGX Spark
status: published
# series: Cockpit          # optional, reuses the article SERIES enum
tags: [todo-tag, todo-tag, todo-tag]
# signature: TODOComponent  # optional card-thumbnail SVG under src/components/svg/
# product_url: "TODO"
# repo_url: "TODO"
# fieldkit_modules: [harness, eval, notebook, nim]   # optional — modules the product surfaces
# --- build-metrics block: the infographic's data source (fill from mine_build_metrics.py) ---
build:
  window: "TODO e.g. one day (~15 hours)"
  wall_clock_hours: 0
  sessions: 0
  assistant_turns: 0
  tokens_processed: 0
  tokens_generated: 0
  cache_read_tokens: 0
  lines_of_code: 0
  test_cases: 0
  feature_count: 0
  models: ["TODO Claude Opus X.Y"]
  daily_driver: "TODO Claude Opus X.Y"
  harness: "Claude Code"
# --- feature tour: drives the operator-facing gallery (one entry per surface) ---
features:
  - name: "TODO Feature"
    benefit: "TODO one-line benefit — what it does FOR the operator."
    screenshot: "screenshots/01-todo.png"
---

<!-- Read references/voice-and-positioning.md and references/product-narrative-structure.md before writing. -->
<!-- Lead with the PRODUCT, not the build story. No competitors named or implied. -->

## TODO: The lead — positioning

<!-- 1–2 ¶. Name it, say what it is and who it's for, in plain language. The reader
should know in 15 seconds whether this is for them. No metrics yet, no build story yet. -->

## TODO: What it unlocks

<!-- 2–3 ¶. The researcher's section. Why does this change how work gets done on a Spark?
Live experimentation, faster decisions, tighter prototype loop, private iteration.
Name concrete things the reader could do this week. -->

## TODO: How it got built — vision → MVP → production

<!-- 3–5 ¶ + the build-metrics infographic. The honest arc: the itch, the unglamorous
first slice, the leap. Interpret the metrics (don't just dump them) — see
references/metrics-infographic.md. Credit the models + Claude Code harness + caching here. -->

<!-- The destination renders the `build:` frontmatter as the infographic. If you want an
inline prose summary of the headline numbers, write it here and let the chart carry the rest. -->

## TODO: The feature tour

<!-- The bulk. One block per surface: benefit-led heading + screenshot + 1–3 sentences.
Start at the surface the operator lands on, walk outward. See references/feature-tour.md. -->

### TODO Feature one — benefit-led heading

![TODO alt text describing the feature](screenshots/01-todo.png)

*TODO centered caption — benefit in isolation.*

<!-- 1–3 sentences: what it does and why it matters in practice. -->

## TODO: Built on the substrate

<!-- 2–3 ¶. The leverage story. Buildable in a day BECAUSE of what existed: the fieldkit
package it's a thin surface over (name the modules + what each powers), and the AI Field
Notes articles + artifacts that gave it real data. Assembly of compounding work, not scratch. -->

## TODO: The workflow, generalized

<!-- 2–3 ¶. Zoom out to the repeatable method: solo operator + Spark + Opus via Claude Code +
maturing toolkit → production surface in a day. Grounded in the real metrics. -->

## TODO: Get it / run it / what's next

<!-- 1–2 ¶. Where to find it, the one-line run command if any, an honest line on what's next.
Close on the product. -->
