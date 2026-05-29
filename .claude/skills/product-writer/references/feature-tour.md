# The feature tour

The feature tour is the operator-facing half of a product article: one
screenshot per surface, each with a benefit-led caption. A scanning reader who
never reads a full paragraph should still come away understanding what the
product does and wanting to run it. This is where a product article earns its
length.

## Capture mechanics

Product UIs are web apps, so captures use Playwright-MCP against the running
product — the same toolchain and the same aarch64/DGX-Spark setup the
tech-writer skill documents. Rather than duplicate it, read
`../../tech-writer/references/screenshot-workflows.md` for the decision tree,
the resize-to-1440×900-at-2×-DPR rule, and the bundled-chromium executable-path
fix for the Spark. The privacy rules there
(`../../tech-writer/references/privacy-and-security.md`) apply unchanged: scoped
shots, fresh browser profile, visual scan before embedding.

The one product-specific wrinkle: **the product has to be running.** For a
fieldkit-backed product like the Arena that means starting its sidecar first
(e.g. `fieldkit arena up`) and capturing against the local loopback URL. If the
product surfaces live telemetry or model output, let it warm up so the captures
show real data, not empty states — a screenshot of a populated cockpit sells;
a screenshot of a loading spinner doesn't.

Save captures to `products/<slug>/screenshots/NN-feature.png`, numbered in tour
order (the order the reader will walk them, usually the order an operator
encounters the surfaces).

## Choosing what to show

- **One capture per distinct surface**, not per minor state. Fourteen features
  is a rich tour; forty screenshots is a slog. If two views belong to the same
  feature, pick the one that best shows the benefit.
- **Lead with the surface the operator lands on** (the cockpit/home), then walk
  outward to the surfaces reached from it.
- **Prefer populated, real-data captures.** Live telemetry reading real GPU
  numbers, a leaderboard with real rows, a compare with a real verdict — these
  are the shots that make the product feel alive and trustworthy.
- **Scope tightly.** Capture the feature, not the whole browser window. Browser
  chrome leaks information and dilutes the subject.

## Caption style — benefit, not label

Each feature block is a benefit-led heading + one screenshot + 1–3 sentences.
The heading and first sentence should state the *benefit*, then you can name the
mechanism. Contrast:

- Label (weak): "Command Palette — the Arena has a ⌘K palette."
- Benefit (strong): "Jump anywhere without the mouse — ⌘K opens a fuzzy palette
  over every model, article, and lane; type a question and it offers to send it
  to the warm model or set up a compare."

Write captions that work in isolation, because many readers only read captions.
Keep the centered-mono caption convention the site uses (a paragraph whose only
content is `*italic text*` renders as a caption) for the image's own caption;
the surrounding benefit prose is normal body text above or below the image.

## Tying the tour back to the argument

The tour is operator-facing, but don't let it become a flat catalog. Where a
feature is *also* a research-workflow point, say so in one clause — "the
efficiency frontier is where a researcher decides which quant to ship" — so the
two readers (see `voice-and-positioning.md`) stay served by the same block. The
features that map to the product's core thesis deserve a sentence more than the
incidental ones; not every surface gets equal weight.
