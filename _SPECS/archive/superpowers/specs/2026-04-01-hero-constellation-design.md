# Hero Section: AI-Native Business Constellation

**Date:** 2026-04-01
**Status:** Draft
**Scope:** Replace hero architecture view with animated business visualization; update tagline

## Context

The current hero section displays `SystemArchitecture.astro` — a technical swimlane diagram showing 4 pillars × 3 layers with service names, API counts, and infrastructure details. While accurate, it speaks to developers, not business buyers. The goal is to replace this with a visualization that communicates **business outcomes** powered by ainative's AI platform — revenue growth, cost efficiency, compliance — while retaining the technical architecture view in the research paper (`research.mdx`).

## Design Decisions

| Decision | Choice |
|----------|--------|
| Visualization style | Network Constellation |
| Organizing principle | Hybrid: ainative product entities (inner) → business outcomes (outer) |
| Node density | Lean: 10 nodes (4 inner + 6 outer) |
| Animation | Orchestrated Reveal → Ambient steady-state |
| Node rendering | Organic Glow: circular nodes, bezier curves, particle flow |
| Tagline direction | Outcome/value-first |

## Component

**New file:** `src/components/svg/BusinessConstellation.astro`

Replaces `SystemArchitecture` import in `Hero.astro`. `SystemArchitecture.astro` is **not modified** — it remains used in `research.mdx` (Figure 8).

**SVG viewBox:** `0 0 560 400` (matches aspect ratio of current architecture view)

## Node Architecture

### Inner Ring — ainative Product Entities (4 nodes)

| Node | Color Variable | SVG Icon | Radius | Position |
|------|---------------|----------|--------|----------|
| Agents | `--svg-accent-blue` | Bot head (rect + circles + antenna) | 32 | Top center |
| Workflows | `--svg-accent-teal` | Branching arrows (fork paths + dots) | 26 | Center-left |
| Documents | `--svg-accent-purple` | Page with text lines | 26 | Center-right |
| Knowledge | `--svg-accent-orange` | Lightbulb | 26 | Bottom center |

**Visual treatment:**
- Radial gradient fill: accent color at 20% center → 5% edge
- Solid stroke at 40% opacity
- Breathing halo: outer ring pulses radius ±3px over 4–5.5s, stroke-opacity fades 0.15→0.06
- Label below node in accent color, font-size 7.5–8px, font-weight 600

### Outer Ring — Business Outcomes (6 nodes)

| Node | Color Variable | SVG Icon | Radius | Position |
|------|---------------|----------|--------|----------|
| Revenue Growth | `--svg-accent-blue` | Trending-up arrow polyline | 22 | Top-left |
| Customer Success | `--svg-accent-teal` | Checkmark polyline | 22 | Top-right |
| Operations Excellence | `--svg-accent-teal` | Gear (circle + inner dot) | 22 | Left |
| Cost Efficiency | `--svg-accent-orange` | Down-trend arrow polyline | 22 | Bottom-left |
| Business Intelligence | `--svg-accent-purple` | Bar chart (3 rects) | 22 | Bottom-right |
| Compliance & Governance | `--svg-accent-purple` | Shield with checkmark | 22 | Right |

**Visual treatment:**
- Dark fill (`var(--color-surface)` mapped) with faint accent stroke at 25% opacity
- Stroke-only icons in accent color
- Two-line label below: primary text in `--color-text-dim`, secondary smaller line at 70% opacity

### Connection Map

Each inner node connects to 2–3 outer nodes showing product-to-outcome relationships:

| Inner Node | Connected Outcomes |
|------------|-------------------|
| Agents | Revenue Growth, Customer Success, Compliance |
| Workflows | Operations Excellence, Cost Efficiency, Revenue Growth |
| Documents | Business Intelligence, Customer Success |
| Knowledge | Compliance & Governance, Business Intelligence, Cost Efficiency |

**Inner-to-inner:** 4 connections forming a diamond (Agents↔Workflows, Agents↔Documents, Workflows↔Knowledge, Documents↔Knowledge)

## Connections & Particles

### Inner → Outer (Bezier Curves)
- SVG `<path>` with quadratic bezier (`Q` control point)
- Stroke: accent color at 10% opacity, width 1px
- Cross-connections at 6–8% opacity, 0.7–0.8px

### Inner → Inner (Dashed Lines)
- Straight `<line>` elements
- `stroke-dasharray: 3 4`
- Animated `stroke-dashoffset` cycling −14 over 3–3.5s

### Flowing Particles
- Small `<circle>` elements (r=2–2.5)
- `<animateMotion>` following the bezier `<path>` geometry
- Duration: 4–5.5s per trip, `repeatCount="indefinite"`
- Color matches destination node accent
- Opacity: 0.5–0.7

## Animation System

### Phase 1: Orchestrated Reveal (scroll-triggered)

Uses existing `data-svg-animate` + `svg-reveal` classes from `global.css`.

| Timing | Element | Class |
|--------|---------|-------|
| 0.0s | Central atmospheric glow | `svg-reveal` |
| 0.1s | Agents node | `svg-reveal svg-reveal-d1` |
| 0.2s | Workflows node | `svg-reveal svg-reveal-d2` |
| 0.3s | Documents node | `svg-reveal svg-reveal-d3` |
| 0.4s | Knowledge node + inner connections | `svg-reveal svg-reveal-d4` |
| 0.5s | Revenue Growth, Customer Success | `svg-reveal svg-reveal-d5` |
| 0.6s | Operations, Cost Efficiency | `svg-reveal svg-reveal-d6` |
| 0.7s | BI, Compliance + outer connections | `svg-reveal svg-reveal-d7` |
| 0.8s | Particles begin | `svg-reveal svg-reveal-d8` |

### Phase 2: Ambient (continuous after reveal)

| Animation | Target | Duration | Type |
|-----------|--------|----------|------|
| Breathing halo | Inner node outer rings | 4–5.5s each | radius + opacity pulse |
| Particle flow | `<circle>` on bezier paths | 4–5.5s each | `animateMotion` |
| Dash cycle | Inner connection lines | 3–3.5s | `stroke-dashoffset` |

### Reduced Motion

All animations disabled via:
```css
@media (prefers-reduced-motion: reduce) {
  /* Particles hidden, halos static, dash animation paused */
}
```

## Atmosphere

- Central `<radialGradient>`: primary color at 12% → 4% → 0% over 190px radius
- `<filter id="softGlow">` with `feGaussianBlur stdDeviation="6"` on Agents hero node
- Existing `.hero-arch-wrapper::after` radial glow retained as backdrop
- Subtle `AINATIVE` watermark text at center: primary color, 5.5px, letter-spacing 3px, 40% opacity

## Light/Dark Mode

All colors use CSS custom properties. No duplication needed.

| Element | Dark Mode | Light Mode |
|---------|-----------|------------|
| Node fill (inner) | Radial gradient accent 20%→5% | Radial gradient accent 10%→3% |
| Node fill (outer) | `#0d1529` | `white` or surface color |
| Node stroke | Accent at 40% | Accent at 50% |
| Connection stroke | 10% opacity | 15% opacity (higher for contrast) |
| Particle opacity | 0.5–0.7 | 0.4–0.6 |
| Glow/atmosphere | 12% center | 6% center |
| Labels | Accent colors | Darker accent variants |
| Watermark | 40% opacity | 25% opacity |

Implemented via light-mode overrides in `<style>` block within the component, targeting `:global(.light)` or `@media (prefers-color-scheme: light)` consistent with site pattern.

## Hero Content Updates

### Tagline

**Current:**
> Stop cobbling together 15 disconnected tools. ainative orchestrates AI agents across your entire business — with the governance, visibility, and cost controls that keep you in charge.

**New:**
> Every function automated. Every decision informed. Every risk governed.

### Value Proposition Pills

| Current | New |
|---------|-----|
| Open Source | Open Source (keep) |
| Local-First | Local-First (keep) |
| 5 Runtimes | Multi-Model AI |
| Human-in-the-Loop | Human-in-the-Loop (keep) |

### Link Behavior

Current architecture view links to `/research`. The constellation should retain this — wrap in `<a href="/research">` with the same `aria-label` and hover behavior.

## Files Modified

| File | Change |
|------|--------|
| `src/components/svg/BusinessConstellation.astro` | **New** — constellation SVG component |
| `src/components/sections/Hero.astro` | Replace `SystemArchitecture` import with `BusinessConstellation`, update tagline, update pill text |

**Not modified:** `SystemArchitecture.astro`, `research.mdx`, `TechTicker.astro`, `global.css`

## Tech Ticker Complementarity

The constellation shows **what** ainative delivers (business outcomes). The ticker shows **how** (technologies: Anthropic, OpenAI, React, SQLite, etc.). No element overlap between them.

## Verification

1. `npm run dev` — visual inspection of hero on desktop and mobile
2. Light mode toggle — verify all nodes, connections, and labels are visible and contrast-appropriate
3. Dark mode — verify glow effects and atmosphere render correctly
4. Scroll past hero and back — verify orchestrated reveal triggers correctly
5. `prefers-reduced-motion` — verify all animations disabled (browser DevTools → Rendering)
6. Check `/research` page — verify `SystemArchitecture` still renders correctly and unchanged
7. Responsive: check at 375px, 768px, 1280px, 1440px widths
8. Click constellation → navigates to `/research`
