# SVG architecture visualizations

ai-field-notes articles are architecture-heavy. A well-chosen diagram reinforces the article's thesis in a single glance — a poorly chosen one is decoration that slows the reader. This reference describes *when* to add a diagram, *which archetype* to reach for, and *how* to author it so the site's visual language (OKLCH hue 250 indigo + Geist typography, dark-first with light toggle) stays coherent across articles.

The CSS system lives at `/home/nvidia/ainative-business.github.io/src/styles/diagrams.css` and is imported globally. Every class, token, and keyframe referenced here is defined there — read that file once before designing a new diagram.

## When a diagram earns its keep

The architectural-context section (Section 3 in `article-structure.md`) almost always benefits from one. Beyond that, add a diagram only when it passes all five:

1. **Thesis reinforcement, not step illustration.** If the diagram could be captioned "we did step 4", it doesn't belong. The caption should be a claim — the same claim the article is making in prose.
2. **The delete test.** Would removing the diagram weaken the article's argument? If not, delete it.
3. **Fits the column.** The prose column is 48rem (~768px) in text but diagrams break out to the 80rem article frame (~1232px at desktop after padding). Design the viewBox around that wider canvas; if the diagram still feels cramped, redesign it — don't fight the chrome.
4. **Motion serves understanding.** Stroke-draw reveals a sequence. A travelling particle reveals a flow. A staggered reveal reveals a layering. If the motion is just "things appearing", drop the animation and keep it static.
5. **The caption interprets.** Not "Diagram of the access stack" — something like *"The tools are interchangeable; the breadth of the surface is what compounds."*

One strong diagram beats three weak ones. Most articles land with zero or one. Two is the ceiling unless the piece is explicitly topology-heavy.

## The six archetypes

Every architecture visualization collapses into one of these shapes. Pick the shape first, then design within its motion pattern.

### 1. Flow pipeline

Linear stages; a request travels through a chain (tokenizer → model → KV cache → streamed tokens).

- **SVG primitives:** rectangles or rounded rects as stages, `<path>` connectors between them, one `<circle class="fn-diagram__flow">` with `<animateMotion>` travelling the path.
- **Motion:** edges draw left-to-right; once all drawn, the particle starts travelling and loops.
- **Use when:** the article is about a transformation that passes through distinct stages.

### 2. Layered stack

Hardware/software layers; "where this sits" diagrams (model → inference engine → GPU → app).

- **SVG primitives:** stacked rectangles of equal width, labels centred on each.
- **Motion:** layers fade-rise bottom-up, staggered by `--fn-stagger`. No edges; the stack *is* the relationship.
- **Use when:** the article places a product on the existing LLM/inference/agentic map.

### 3. Dual-path comparison

Two parallel routes to the same destination (host OpenClaw vs sandbox → Ollama).

- **SVG primitives:** two rows of rects connected by edges, converging at a shared endpoint on the right.
- **Motion:** both paths draw simultaneously; the shared endpoint fade-rises last to land the convergence.
- **Use when:** the article argues for one path over another, or claims the paths converge at some shared cost.

### 4. Topology / hub-and-spoke

Central component with radiating dependencies — "the five roles of the access stack", "one inference endpoint feeding N agents".

- **SVG primitives:** one central circle/rect, N spokes as `<path>`, N terminal chips around the perimeter.
- **Motion:** hub fades in first, spokes draw outward, chips fade in last — staggered.
- **Use when:** the thesis is about *breadth* or *fan-out* from a single point.

### 5. Timeline / sequence

Wall-clock comparison; cold-start curves; turn-by-turn benchmarks.

- **SVG primitives:** x- and y-axis `<line>`s with tick `<text>`; data traces as `<polyline>` or `<path>`; optional shaded regions via `<rect>` with low alpha.
- **Motion:** axes draw first (short), then each data trace draws left-to-right at `--fn-dur-long`, staggered.
- **Use when:** a number changes over time or across discrete events, and the *shape* of the change is the point.

### 6. Waterfall / stacked bar

Cost decomposition — "where the 2× latency tax lives", "memory budget across a model load".

- **SVG primitives:** horizontal rects laid side-by-side, each `class="fn-diagram__bar"`; numeric annotations above.
- **Motion:** segments scale-in from left, widest first, via the `fn-bar-grow` keyframe.
- **Use when:** a total decomposes into parts and the relative sizes are the insight.

## Authoring template

Every diagram follows this skeleton. Copy it, change the `viewBox` to suit the archetype, fill in the groups. Do **not** add inline `style` attributes for colour or font — let the classes cascade.

```html
<figure class="fn-diagram" aria-label="One sentence describing the whole diagram — will be announced by screen readers, never shown as a tooltip.">
  <svg viewBox="0 0 900 440" role="img" preserveAspectRatio="xMidYMid meet">
    <g class="fn-diagram__edges">
      <!-- Every <path> MUST include pathLength="100" so stroke-draw timing is predictable -->
      <path class="fn-diagram__edge" pathLength="100" d="M 100 220 L 400 220" />
    </g>
    <g class="fn-diagram__nodes">
      <rect class="fn-diagram__node" x="40" y="180" width="160" height="80" rx="8" />
    </g>
    <g class="fn-diagram__labels">
      <text class="fn-diagram__label" x="120" y="225" text-anchor="middle">Label</text>
      <text class="fn-diagram__label fn-diagram__label--mono" x="120" y="245" text-anchor="middle">127.0.0.1:11434</text>
    </g>
    <g class="fn-diagram__symbols">
      <!-- Icon positioned by inline transform — DO NOT animate these with a
           CSS transform keyframe (collapses every icon to the origin). -->
      <g class="fn-diagram__icon" transform="translate(108 198)"><path d="M6.75 7.5l3 2.25-3 2.25m4.5 0h3m-9 8.25h13.5A2.25 2.25 0 0021 18V6a2.25 2.25 0 00-2.25-2.25H5.25A2.25 2.25 0 003 6v12a2.25 2.25 0 002.25 2.25z"/></g>
    </g>
    <g class="fn-diagram__annotations">
      <text class="fn-diagram__annotation" x="250" y="210" text-anchor="middle">~20 ms</text>
    </g>
  </svg>
  <figcaption>One interpretive sentence — the <em>claim</em> the diagram makes, not a description of its contents.</figcaption>
</figure>
```

Heroicons v2 (outline variant) are the default icon set — their 24×24 viewBox paths drop in cleanly. Centre an icon at `(cx, cy)` in diagram coordinates with `transform="translate(cx-12 cy-12)"`; scale with an additional `scale(s)` if the chip wants a larger glyph (e.g., the hub's persona icon at 1.33× in the access-layer diagram).

### Iconography and shape variety

Pick one icon per labelled node — not every chip needs one, but the thesis-critical ones usually benefit. Prefer Heroicons outline paths verbatim; keep `class="fn-diagram__icon"` (which sets `fill: none; stroke: var(--color-text)` and handles the fade-in). Apply `--accent` if the node is the diagram's accent (matches the indigo-primary node chrome), `--muted` if it's legend-only.

Common Heroicons choices for NVIDIA-DGX-Spark contexts:

| Concept | Heroicon |
|---|---|
| User / persona | `user` |
| Remote reach / streaming | `signal` |
| AI collaboration | `sparkles` |
| Browsing / exploration | `globe-alt` / `globe-americas` |
| Sandbox / isolation | `shield-check` / `cube-transparent` |
| Publishing / outbound | `paper-airplane` / `cloud-arrow-up` |
| Transcript / document | `document-text` |
| Editing / drafting | `pencil-square` |
| Privacy check | `shield-check` |
| Git / commits | `code-bracket` |
| Reader / public | `globe-alt` / `eye` |
| Terminal / CLI | `command-line` |
| Container / k3s / microservices | `cube-transparent` |
| Auth / token | `key` |
| Inference backend / DB | `server-stack` / `circle-stack` |
| Warning / divergence | `exclamation-triangle` |
| Convergence / success | `check-circle` / `arrow-trending-up` |
| Latency / wall-clock | `clock` / `stopwatch` |

Shape variety earns its place by *reading* differently, not by being different for its own sake. Keep rectangles for "processes" and "services"; reach for other shapes when the semantics warrant it:

- **Hexagon** — platform, orchestrator, or mesh ("the hub", "k3s gateway"). Flat-top hexagon is more readable at small sizes.
- **Cylinder** — data store, model weights, inference backend. One `<ellipse>` on top + one open path for the body with a half-ellipse bottom.
- **Circle** — individual data points in a timeline/scatter (`fn-diagram__dot`).
- **Dashed rectangle (`fn-diagram__node--ghost`)** — container boundary, isolation zone, conceptual grouping.
- **Dark rectangle (`fn-diagram__node--ink`)** — terminal/code surface when a chip specifically represents a shell or container interior.

Never mix more than three shape families per diagram. A diagram with rectangles, one hexagon, and a cylinder reads as a coherent system; one with rectangles, hexagons, circles, diamonds, triangles, and cylinders reads as a kitchen sink.

### Required constraints

- **`viewBox` only** — no fixed `width`/`height` on the `<svg>`. The figure scales to the viewport container.
- **`role="img"` + `aria-label`** directly on the `<svg>`. Do NOT use `<title>` as a child of the SVG — browsers render it as a hover tooltip on the whole diagram, which fights the CSS hover states. One descriptive `aria-label` sentence is sufficient. An `aria-describedby` → `<desc>` pair is optional for longer narration.
- **`pathLength="100"` on every `<path class="fn-diagram__edge">`** — the stroke-draw keyframe assumes a 100-unit path.
- **Text is real `<text>`**, never SVG paths. Screen readers must be able to read labels.
- **Palette via classes, not hex.** If you find yourself typing a hex colour (e.g. `#7c8df0`) into a `fill=`, stop — use `class="fn-diagram__edge--accent"` instead. All colour flows through OKLCH tokens so dark / light themes stay coherent; hardcoded hex bypasses that.
- **Label font sizes:** body 14px, mono 12px, annotations 11px, display 16px. Don't invent new sizes.
- **No blank lines inside the `<figure>` block.** Astro's markdown renderer (via remark) treats `<figure>` as a type-6 raw-HTML block, which ends at the first blank line. A blank line inside your figure will make everything after it render as an escaped `<pre>` code block on the page. Keep the whole figure contiguous — use indentation for readability, never blank lines. If you want visual grouping in the source, add an HTML comment like `<!-- labels -->` on its own line instead of a blank line.
- **Icon positioning uses `<g transform="translate(x y)">`**, not CSS transform. The `.fn-diagram__icon` class runs an opacity-only animation precisely so its inline transform survives; if you animate the icon with a transform-based keyframe you will wipe out the translate and every icon in the figure will collapse to (0, 0). The CSS is already configured correctly — just don't add your own transform animation to icons.

### Hard invariants (validator-enforced)

Every invariant below is checked by `scripts/verify_svg.sh`, which runs as a blocking gate inside `verify_article.sh`. Violations fail the publish. Each rule names the bug it prevents so you can eyeball a diagram and predict what the validator will say.

1. **Child order.** Inside the `<svg>`: `<defs>` → atmosphere (gradient-filled background rects) → `<g class="fn-diagram__edges">` → `<circle class="fn-diagram__flow">` → `<g class="fn-diagram__nodes">` → `<g class="fn-diagram__labels">` → `<g class="fn-diagram__symbols">`. The z-order is bottom-to-top, so putting nodes before edges hides the edges; putting labels before nodes puts text behind fills. *Prevents:* "lines are over text" and "node fill covers its own label".

2. **No edge endpoint lands inside a ghost node.** Every `<path class="fn-diagram__edge">` start and end coordinate must be either outside all nodes or on a node boundary (±2 units). Ghost nodes have `fill: none`, so an endpoint inside one leaves the stroke drawn *through* the ghost's interior text. Accent edges may terminate at their accent node's centre (that's their job); all other edge/node intersections mean "route the endpoint to the boundary." *Prevents:* the dashed arrow that cuts through "2048-D SPACE / cosine(q,p)" text.

3. **Flow circles MUST NOT set `cx` or `cy`** (or must set them to `0`). `<animateMotion>` applies as an *additional* `translate()` on top of the element's intrinsic position — so any non-zero `cx`/`cy` compounds with the motion path and displaces the dot off the edge. Pre-begin invisibility is handled by CSS: `.fn-diagram__flow { opacity: 0 }` gated through the `.fn-diagram--visible` parent class (scroll-triggered), so the dot never appears at the pre-animation (0,0) default position. *Prevents:* "the animating dot is displaced off the path."

4. **`animateMotion begin ≥ 1.4s`.** The path-draw animation finishes at `--fn-dur-long` (1400 ms). Starting the particle earlier means it begins travelling a path that hasn't finished drawing yet.

5. **Node text capacity: max lines = `floor(height / 22) − 1`.** A 100-unit-tall node holds 3 text lines with safe padding; 4 lines requires height ≥ 120. Every `<text>` baseline inside a node must satisfy `node.y + 14 ≤ baseline ≤ node.y + height − 8`, or be explicitly positioned as a kicker 4 units above the node top. *Prevents:* "last line is broken from rest" (accent-node glow cropping the bottom label).

6. **Icon clearance: ≥ 10 units between icon bbox (24×24) and every `<text>` bbox in the same visual column.** An icon at `translate(x y)` occupies `[x, y, x+24, y+24]`; a text baseline at `ty` occupies roughly `[_, ty−14, _, ty+4]`. Distance between those two rects along y must be ≥ 10. *Prevents:* "icons are touching titles."

7. **Every SVG declares at least one `<linearGradient>` or `<radialGradient>` in `<defs>`.** See §Gradient palette below for the three canonical patterns. *Prevents:* flat, gradient-less diagrams that look weaker than peer editorial work.

8. **Stroke-width ∈ {0.5, 1, 1.5, 2}.** Four weights, strictly: 0.5 = grid/guide, 1 = baseline flow, 1.5 = secondary emphasis, 2 = primary flow. No 0.75, no 1.1, no 1.25. Hierarchy via weight *and* dash pattern, not random decimals.

9. **Zero hex literals in `fill=` or `stroke=`.** All colour flows through `--svg-*`/`--color-*` CSS variables or the `fn-diagram__*` class system, so dark/light themes stay coherent. `stop-color` in gradient defs follows the same rule.

10. **`<svg>` has both `role="img"` and `aria-label`.** The `aria-label` on the wrapping `<figure>` is not sufficient — screen readers look at the SVG's own attributes. Copy the same sentence onto the SVG.

11. **No `<title>` child of `<svg>`.** Browsers render it as a hover tooltip over the whole diagram, which fights the CSS hover states. Use `aria-label` instead. `<desc>` + `aria-describedby` is fine for longer narration.

12. **Halo rects must be bounded.** Every `<rect fill="url(#…-halo…)">` or field-radial `<rect fill="url(#…-space…)">` must satisfy *one* of: (a) its coordinates match an `fn-diagram__node--accent` rect in the same SVG exactly (so the accent's own stroke bounds the halo), (b) a `fn-diagram__node--ghost` rect sits at identical coordinates, or (c) for signature SVGs, a dashed outline rect (`stroke-dasharray="3 3"`) sits at identical coordinates. See §Containing the halo for the sizing rule. *Prevents:* unbounded atmospheric bleed past the node edge — halos that drift 20+ units wider/taller than their target and read as free-form washes. Atmospheric lane washes (linearGradient patterns 1 & 2) are exempt — they're backdrop, not focal glow.

### Gradient palette (the "atmosphere" layer)

The validator requires a gradient in every SVG because gradient *absence* is the single loudest tell that a diagram is half-finished. Four canonical patterns cover every archetype. Keep gradients on *surfaces* (backgrounds, lane washes, field radials, halos) and on the *thesis-critical accent node* (the one with `fn-diagram__node--accent`) — never on *data marks* (bars, dots, edges) where comparison must read true.

**1. Atmospheric lane wash (linear, vertical).** Colour-code semantic lanes or zones by tinting their background with a 0.12 → 0.02 opacity ramp in the lane's accent hue. Three-stop variants (0.02 → 0.12 → 0.02) for symmetric vertical bands also OK.

```svg
<defs>
  <linearGradient id="d-query-lane-grad" x1="0" y1="0" x2="0" y2="1">
    <stop offset="0%"   stop-color="var(--svg-accent-blue)" stop-opacity="0.12"/>
    <stop offset="100%" stop-color="var(--svg-accent-blue)" stop-opacity="0.03"/>
  </linearGradient>
</defs>
<rect x="20" y="40" width="200" height="140" rx="10"
      fill="url(#d-query-lane-grad)" stroke="none"/>
```

**2. Field radial (for "space" / "surface" regions).** Use inside any ghost boundary that represents a latent space, solution space, or decision surface. Centre the gradient at the node centre; fade to zero at 70 % radius. Keep the opacity low — 0.08 max at centre — so the glow reads as atmosphere, not a paint-fill.

```svg
<radialGradient id="d-space-grad" cx="0.5" cy="0.5" r="0.7">
  <stop offset="0%"   stop-color="var(--svg-accent-blue)" stop-opacity="0.08"/>
  <stop offset="100%" stop-color="var(--svg-accent-blue)" stop-opacity="0"/>
</radialGradient>
<rect x="700" y="120" width="160" height="120" rx="8"
      fill="url(#d-space-grad)" stroke="none"/>
```

**3. Halo + core dot (depth without blur filters).** Every data-marker dot is a pair of concentric circles — a faint halo and a solid core — sharing the same hue.

```svg
<g fill="var(--svg-accent-teal)">
  <circle cx="231" cy="88" r="8" opacity="0.12"/>   <!-- halo  -->
  <circle cx="231" cy="88" r="3"/>                   <!-- core  -->
</g>
```

The flow particle (`.fn-diagram__flow`) is the one dot type that stays single-radius — it's a connector animation, not a data marker.

**4. Accent-node fill gradient (the "lit from above" effect on the thesis node).** The `.fn-diagram__node--accent` CSS class sets a flat `color-mix` fill. Override via inline `style="fill: url(#…)"` to get a vertical ramp — inline style beats the class-level fill. Use a linear, vertical ramp of `--color-primary` from **0.30 opacity at top to 0.08 at bottom** — a *light* wash, not a saturated block. Signature thumbnails use a slightly stronger ramp (0.45 → 0.15) since they render smaller. Only the *one* accent node per diagram should carry this; plain nodes stay flat.

```svg
<defs>
  <linearGradient id="d-accent-grad" x1="0" y1="0" x2="0" y2="1">
    <stop offset="0%"   stop-color="var(--color-primary)" stop-opacity="0.30"/>
    <stop offset="100%" stop-color="var(--color-primary)" stop-opacity="0.08"/>
  </linearGradient>
</defs>
<rect class="fn-diagram__node fn-diagram__node--accent fn-diagram__pulse"
      x="420" y="120" width="160" height="120" rx="10"
      style="fill: url(#d-accent-grad)" />
```

The accent node's visual identity comes from **three** stacked layers: (a) the halo radial behind it at 0.12 top opacity, (b) this inline linear gradient fill, (c) a hard 1.25-width stroke in `--color-text-muted` matching every other node's border. No blur filters, no drop-shadows — the stroke must read as a crisp line exactly like plain nodes' borders, anchoring the glow as a bounded design element. (The `.fn-diagram__pulse` class is kept for future use but currently runs a no-op fade-rise — the earlier infinite scale-pulse was jarring against the hard-bordered boxes and was removed.)

### Containing the halo (bounded glow)

A halo-pattern gradient rect (radial `…-halo…`, or a field radial like `…-space…` behind a key element) must read as a **bounded design element** — a member of the same family as every other box in the diagram — not a free-form atmospheric wash bleeding past the node edge. Two halves to the rule:

**1. Halo sizing follows what it wraps.**

- **Single-node halo** — one node in a graph, stack, or pipeline. Halo coords ≡ target node coords (same `x y width height rx`). No overflow, no asymmetry. Example: in `articles/pgvector-on-spark/article.md`, `url(#d03-pgv-halo-grad)` is at `(120,208,660,76) rx=10` — exactly the accent node. Example: in `articles/bigger-generator-grounding-on-spark/article.md`, `url(#d06-49b-halo)` is at `(340,90,220,100) rx=10` — exactly the 49B accent node, not a larger free-form glow.
- **Distribution halo** — a group: bar chart, sibling chips, a region of interest. Halo coords ≡ the tightest bounding box over the group (use the same rx convention the rest of the diagram uses). Example: in `src/components/svg/PgvectorStore.astro`, `url(#pgv-graph-grad)` wraps the entire HNSW graph region at `(180,38,112,136)`.
- **Non-rect shapes** (hexagon hub, cylinder, polygon): halo rect ≡ the shape's bounding box, same rx (often `rx=0` for cylinders, `rx=10`+ for hex). Example: `articles/dgx-spark-day-one-access-first/article.md` fig 1 — hub-hex's halo tightened to the hex bbox `(390,248,120,104)`. Example: `articles/nemoclaw-vs-openclaw-dgx-spark/article.md` — Ollama cylinder halo tightened to the cylinder bbox `(690,152,140,156)`.

**2. Bounding box — pair the halo with an outline at identical coordinates.**

- **For fn-diagrams:** if the accent node's own stroke already traces the halo (halo coords ≡ accent node coords), no extra rect is needed — the accent node *is* the bounding box. Otherwise add a ghost rect at the halo's coords:
  ```svg
  <rect class="fn-diagram__node fn-diagram__node--ghost"
        x="…" y="…" width="…" height="…" rx="…"/>
  ```
  Reference: `articles/nemo-retriever-embeddings-local/article.md` — halo `(700,120,160,120)` paired with `fn-diagram__node--ghost` at identical coords to bound the 2048-D vector-space region.
- **For signature SVGs:** if the target node already has a visible stroke at the halo's coords, tightening the halo alone is sufficient. Otherwise pair the halo with a dashed outline at identical coordinates:
  ```svg
  <rect x="…" y="…" width="…" height="…" rx="…"
        fill="none" stroke="var(--svg-bg-inner-stroke)"
        stroke-width="1" stroke-dasharray="3 3"/>
  ```
  Reference: `src/components/svg/PgvectorStore.astro` — the HNSW graph halo + dashed outline at identical coords. Also `src/components/svg/EmbeddingPipeline.astro` for the 2048-D space halo.

**The rule applies to halos only.** Atmospheric lane/band washes (linearGradient patterns 1 & 2 above) that span the whole diagram width as semantic colour-coding stay unbounded — they're contextual backdrop, not focal glow.

**Anti-pattern.** A halo rect that's 20–60 units wider or taller than its target node, with no ghost/dashed outline. Reads as a free-form atmospheric bleed past the node edge, and breaks the "same family as every other box" language.

### Breakout & sizing

All figures break out of the 48rem prose column via the CSS — the selector is `.prose .fn-diagram` (spec'd higher than the generic `.prose figure { margin: 2rem 0 }` so the figure's own `margin-left: 50%` actually wins). The formula is `width: min(calc(100vw - 3rem), calc(80rem - 3rem)); margin-left: 50%; transform: translateX(-50%)`, combined with `body { overflow-x: hidden }` to prevent a transient horizontal scrollbar from pulling the layout viewport off-centre. You don't need to do anything to opt in — every `<figure class="fn-diagram">` escapes the column and centres on the page, capped at the 80rem `.article` frame width (~1232px content width at desktop), with an equal 24px bleed on both sides matching the article's inner padding.

Design your viewBox around the *content*, not the display size. A 900×500 viewBox is a good starting point for hub-and-spoke and dual-path layouts; 900×240 suits horizontal pipelines; 900×440 suits timelines. The figure scales to fit the container at render time.

### Optional variants

- `class="fn-diagram__node--accent"` — indigo-primary fill (semi-transparent, via `color-mix`), use sparingly for the *one* thesis-critical node
- `class="fn-diagram__node--ink"` — dark-terminal fill, for code-surface nodes (CLI, container interior). Note: currently theme-reactive (dark in dark mode, near-white in light mode); if you want a forced-dark terminal chip in both themes, wrap your SVG in a `data-theme-invariant="dark"` marker and open an issue.
- `class="fn-diagram__node--ghost"` — dashed outline, for speculative / future / not-yet-wired components
- `class="fn-diagram__edge--accent"` — indigo-primary stroke, for the thesis-critical flow
- `class="fn-diagram__edge--dashed"` — dashed, for optional / conditional connections
- `class="fn-diagram__pulse"` — legacy class, kept for compatibility; the infinite scale-pulse was removed (jarring against hard-bordered boxes). Currently just runs fade-rise, same as any other node. Safe to include but cosmetically a no-op.

## Traveling particles (flow archetype only)

When you want a particle to travel a path — used almost exclusively in the flow pipeline archetype — use SMIL `<animateMotion>` with the diagram's ease curve:

```html
<g class="fn-diagram__edges">
  <path id="d01-flow-path" class="fn-diagram__edge fn-diagram__edge--accent"
        pathLength="100"
        d="M 60 180 L 740 180" />
</g>

<circle class="fn-diagram__flow" r="5">
  <animateMotion dur="3.2s" repeatCount="indefinite"
                 calcMode="spline" keyTimes="0;1" keySplines="0.4 0 0.2 1"
                 begin="1.4s">
    <mpath href="#d01-flow-path" />
  </animateMotion>
</circle>
```

`begin="1.4s"` matches `--fn-dur-long` — the particle starts once the path finishes drawing. The ease keySplines match `--fn-ease`.

## Motion policy (non-negotiable)

- **Ease:** `cubic-bezier(0.4, 0, 0.2, 1)` (token `--fn-ease`) everywhere, in every animation, including SMIL `keySplines`. No linear. No `ease-out-back`. No cubic curves with overshoot.
- **Durations:** `--fn-dur-short` (600ms) for fades; `--fn-dur-med` (900ms) for nodes; `--fn-dur-long` (1400ms) for strokes and timelines. Don't invent new durations.
- **Stagger:** child index via the CSS in `diagrams.css`. First element delays 0ms, second 120ms, third 240ms, etc. For bespoke ordering, reorder the siblings — don't override with inline style.
- **Loop count:** 1 for entry animations (draw, fade-rise, bar-grow). Infinite is reserved for `--flow` particles only — at most one per diagram. The old `fn-soft-pulse` is retired; don't re-introduce scale-pulsing on accent nodes (it fights the hard-bordered aesthetic).
- **Scroll-triggered entry.** Entry animations are gated behind `.fn-diagram--visible` — the page's IntersectionObserver flips it when the figure enters the viewport, so animations never waste themselves above the fold. You do nothing to opt in; the gating is in `diagrams.css` and the observer is in `src/layouts/BaseLayout.astro`. Accent nodes do **not** carry a `filter: drop-shadow` — the crisp stroke matching every other node's border is what anchors them; the halo + gradient fill supplies the "glow" without softening the edge.
- **No hover effects.** Diagrams are read, not interacted with — no colour shifts, scale changes, shadow lifts, or tooltips on pointer hover. The entry animation does the work of drawing attention; anything more is decoration that fights the site's "calm page" aesthetic.
- **Reduced motion:** already handled in CSS. You don't need to opt in — but you must not override it with inline `animation: ...` styles.

## Signature figures (home-page thumbnails)

Every published article declares a `signature:` field in its frontmatter pointing to a component under `src/components/svg/` — a compact 300×200 thumbnail that renders to the right of the card on the home and stage pages. Think of it as a one-glance summary of the article's headline metric or topology.

- **Authoring path:** `src/components/svg/<ComponentName>.astro`. Three ship today — `AccessLayer`, `NemoClawTurns`, `NimPipeline`. New articles ship a new component alongside the draft unless reusing one is explicitly approved.
- **Design language:** semantic tokens from the expanded SVG palette — `--svg-card-fill`, `--svg-bg-inner`, `--svg-text-bright/muted/faint`, `--svg-connector`, plus nine accent hues (`--svg-accent-blue/teal/green/green-alt/cyan/purple/orange/red/pink`). Never hex-code a colour.
- **Motion:** opt in via `data-svg-animate` on the root `<svg>`, then tag children with `svg-reveal svg-reveal-d1..d8` (fade-rise), `line-draw` (stroke-dashoffset draw-in, path length auto-detected), `bar-grow` / `bar-grow-x` (scaleY/scaleX from bottom/left), `ring-expand` (scale from centre), or `dot-pop` (spring). The BaseLayout observer flips `.visible` when the SVG enters the viewport.
- **Depth via fill-opacity.** Instead of `<linearGradient>`, vary opacity across stacked shapes (`fill-opacity={0.4 + i * 0.1}`). One small `<linearGradient>` for the thesis-critical node is fine but not required.
- **Two diagram systems, do not mix per figure.** In-article diagrams use the `fn-diagram__*` class system (opacity-only keyframes, animation-play-state gated). Signature thumbnails use the `svg-reveal` / `line-draw` / `bar-grow` system (IntersectionObserver-driven). The two coexist but within a single SVG pick one or the other.

## Taste test (run before committing a diagram)

1. Does this diagram reinforce the article's thesis, or just illustrate a step?
2. Could I delete it without losing meaning?
3. Does the caption interpret rather than describe?
4. Is exactly one component marked as accent — the thesis-critical one — with a halo + gradient fill + the same hard-line border every other node has?
5. Did I keep the motion restrained? (Stroke-draw + fade-rise. At most one travelling particle. No infinite pulses.)

If any answer is "no" or "not sure", revise before embedding.

## Where to see it in practice

Two diagrams ship with the initial system — study them as reference implementations:

- `articles/dgx-spark-day-one-access-first/article.md` — hub-and-spoke (access layer stack) + flow pipeline (publishing loop)
- `articles/nemoclaw-vs-openclaw-dgx-spark/article.md` — dual-path comparison (twin paths to Ollama) + timeline (onboarding vs steady-state)

When authoring a new diagram, copy the closest existing one and modify — do not start from a blank SVG.
