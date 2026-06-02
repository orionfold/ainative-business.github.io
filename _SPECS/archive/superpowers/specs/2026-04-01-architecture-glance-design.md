# Architecture Glance — Simplified Diagram for Homepage Proof Section

**Date:** 2026-04-01

## Context

The full System Architecture diagram (4 pillars x 3 layers, 36 service boxes) lives in the research paper at `/research`. The homepage Proof section ("Not Slideware. Shipped Software.") needs a lightweight visual that signals architectural depth without overwhelming a marketing audience. This simplified "architecture at a glance" sits after the metrics grid and links to the full diagram in the research paper.

## Design

### New Component: `src/components/svg/ArchitectureGlance.astro`

An inline SVG showing 4 horizontal pillar blocks in a single row. Each block contains:

1. **Pillar icon** — reused from `SystemArchitecture.astro` (crosshair, refresh arrows, shield, chat bubble)
2. **Pillar name** — mono caps label (ORCHESTRATE, AUTOMATE, GOVERN, CONVERSE)
3. **3 capability labels** — the most marketable capabilities from each pillar

#### Capability labels per pillar

| Pillar | Label 1 | Label 2 | Label 3 |
|--------|---------|---------|---------|
| Orchestrate (blue) | 21+ Agent Profiles | Smart Routing | Episodic Memory |
| Automate (teal) | 6 Workflow Patterns | Heartbeat Scheduler | NLP Schedule Parser |
| Govern (purple) | Human-in-the-Loop | Cost Metering | Audit Trail |
| Converse (orange) | Multi-Model Chat | Slack · Telegram | Browser Automation |

#### Visual tokens

- Column fills: `--svg-accent-blue`, `--svg-accent-teal`, `--svg-accent-purple`, `--svg-accent-orange` (same as full diagram)
- Inner boxes: `--svg-bg-inner`, `--svg-bg-inner-stroke`
- Text: `--svg-text-muted`, `--svg-text-dim`
- Fonts: `--font-mono` for pillar names, `--font-body` for capability labels
- Attribute: `data-svg-animate` for scroll-reveal
- No animated connectors — static diagram for quick scanning

#### SVG structure

```
viewBox="0 0 720 160" (compact, wide aspect ratio)

4 equal-width column blocks (~170px each, ~10px gaps)
Each block:
  - Rounded rect background with pillar gradient fill (low opacity)
  - Icon (14px, positioned top-center of block)
  - Pillar name text (mono, 10px, caps)
  - Capability label 1 (body, 9px)
  - Capability label 2 (body, 9px)
```

### Integration: `src/components/sections/Proof.astro`

Insert new block between the metrics grid (`mb-14`) and the Living Book callout:

```astro
<!-- Architecture at a glance -->
<div data-animate class="rounded-xl border border-border/60 bg-surface-raised/50 p-6 md:p-8 mb-14">
  <ArchitectureGlance />
  <div class="mt-4 text-center">
    <a href="/research#architecture" class="inline-flex items-center gap-1.5 text-primary font-mono text-xs tracking-wider hover:underline">
      See full architecture
      <svg ...arrow icon... />
    </a>
  </div>
</div>
```

### Responsive behavior

- Desktop (>640px): 4 columns side by side, SVG scales via `viewBox` + `w-full`
- Mobile (<640px): SVG scales down naturally. Text remains readable due to generous sizing within the viewBox. No layout change needed — the SVG's horizontal layout compresses gracefully.

### Files to create/modify

| File | Action |
|------|--------|
| `src/components/svg/ArchitectureGlance.astro` | Create — new simplified SVG component |
| `src/components/sections/Proof.astro` | Modify — import component, add block after metrics grid |

### Verification

1. Run `npm run dev` and navigate to homepage
2. Confirm the 4-pillar bar appears between metrics and Living Book
3. Confirm colors match the 4 accent tokens (blue, teal, purple, orange)
4. Confirm "See full architecture →" links to `/research#architecture`
5. Confirm scroll-reveal animation fires on scroll
6. Confirm mobile rendering at 375px width — no overflow, text readable
7. Confirm light mode appearance (primary design target per project feedback)
