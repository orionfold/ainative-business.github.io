# Architecture Glance Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a simplified 4-pillar architecture bar to the homepage Proof section, linking to the full diagram in the research paper.

**Architecture:** New `ArchitectureGlance.astro` inline SVG component rendered inside the existing `Proof.astro` section, placed between the metrics grid and the Living Book callout. Uses the same `--svg-accent-*` design tokens as the full `SystemArchitecture.astro` diagram.

**Tech Stack:** Astro, inline SVG, CSS custom properties (OKLCH palette), scroll-reveal via `data-svg-animate`

---

### Task 1: Create ArchitectureGlance SVG Component

**Files:**
- Create: `src/components/svg/ArchitectureGlance.astro`
- Reference: `src/components/svg/SystemArchitecture.astro` (icon paths, token usage)

- [ ] **Step 1: Create the component file with SVG skeleton**

Create `src/components/svg/ArchitectureGlance.astro`:

```astro
---
/**
 * Simplified architecture-at-a-glance: 4 pillars in a single row.
 * Lightweight version of SystemArchitecture for the homepage Proof section.
 */
---
<svg viewBox="0 0 720 160" xmlns="http://www.w3.org/2000/svg" class="w-full mx-auto" data-svg-animate>
  <defs>
    <linearGradient id="ag-orch-grad" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="var(--svg-accent-blue)" stop-opacity="0.12" />
      <stop offset="100%" stop-color="var(--svg-accent-blue)" stop-opacity="0.03" />
    </linearGradient>
    <linearGradient id="ag-auto-grad" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="var(--svg-accent-teal)" stop-opacity="0.12" />
      <stop offset="100%" stop-color="var(--svg-accent-teal)" stop-opacity="0.03" />
    </linearGradient>
    <linearGradient id="ag-gov-grad" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="var(--svg-accent-purple)" stop-opacity="0.12" />
      <stop offset="100%" stop-color="var(--svg-accent-purple)" stop-opacity="0.03" />
    </linearGradient>
    <linearGradient id="ag-conv-grad" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="var(--svg-accent-orange)" stop-opacity="0.12" />
      <stop offset="100%" stop-color="var(--svg-accent-orange)" stop-opacity="0.03" />
    </linearGradient>
  </defs>

  <!-- ═══ PILLAR 1: ORCHESTRATE ═══ -->
  <g class="svg-reveal">
    <rect x="0" y="0" width="170" height="152" rx="8" fill="url(#ag-orch-grad)" stroke="var(--svg-stroke)" stroke-width="0.5" />
    <rect x="10" y="12" width="150" height="30" rx="6" fill="var(--svg-accent-blue)" fill-opacity="0.2" stroke="var(--svg-accent-blue)" stroke-width="0.75" stroke-opacity="0.4" />
    <g transform="translate(16, 17) scale(0.65)" fill="none" stroke="var(--svg-accent-blue)" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
      <circle cx="12" cy="12" r="10" /><path d="M16 12H8M12 16V8" />
    </g>
    <text x="42" y="32" fill="var(--svg-accent-blue)" font-family="var(--font-mono)" font-size="10" font-weight="700" letter-spacing="1">ORCHESTRATE</text>

    <rect x="10" y="54" width="150" height="24" rx="4" fill="var(--svg-bg-inner)" stroke="var(--svg-bg-inner-stroke)" stroke-width="0.5" />
    <rect x="10" y="54" width="3" height="24" rx="1.5" fill="var(--svg-accent-blue)" />
    <text x="85" y="70" fill="var(--svg-text-dim)" font-family="var(--font-body)" font-size="9.5" text-anchor="middle">21+ Agent Profiles</text>

    <rect x="10" y="86" width="150" height="24" rx="4" fill="var(--svg-bg-inner)" stroke="var(--svg-bg-inner-stroke)" stroke-width="0.5" />
    <rect x="10" y="86" width="3" height="24" rx="1.5" fill="var(--svg-accent-blue)" />
    <text x="85" y="102" fill="var(--svg-text-dim)" font-family="var(--font-body)" font-size="9.5" text-anchor="middle">Smart Routing</text>

    <rect x="10" y="118" width="150" height="24" rx="4" fill="var(--svg-bg-inner)" stroke="var(--svg-bg-inner-stroke)" stroke-width="0.5" />
    <rect x="10" y="118" width="3" height="24" rx="1.5" fill="var(--svg-accent-blue)" />
    <text x="85" y="134" fill="var(--svg-text-dim)" font-family="var(--font-body)" font-size="9.5" text-anchor="middle">Episodic Memory</text>
  </g>

  <!-- ═══ PILLAR 2: AUTOMATE ═══ -->
  <g class="svg-reveal svg-reveal-d1">
    <rect x="184" y="0" width="170" height="152" rx="8" fill="url(#ag-auto-grad)" stroke="var(--svg-stroke)" stroke-width="0.5" />
    <rect x="194" y="12" width="150" height="30" rx="6" fill="var(--svg-accent-teal)" fill-opacity="0.2" stroke="var(--svg-accent-teal)" stroke-width="0.75" stroke-opacity="0.4" />
    <g transform="translate(200, 17) scale(0.65)" fill="none" stroke="var(--svg-accent-teal)" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
      <polyline points="23 4 23 10 17 10" /><polyline points="1 20 1 14 7 14" /><path d="M3.51 9a9 9 0 0114.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0020.49 15" />
    </g>
    <text x="228" y="32" fill="var(--svg-accent-teal)" font-family="var(--font-mono)" font-size="10" font-weight="700" letter-spacing="1">AUTOMATE</text>

    <rect x="194" y="54" width="150" height="24" rx="4" fill="var(--svg-bg-inner)" stroke="var(--svg-bg-inner-stroke)" stroke-width="0.5" />
    <rect x="194" y="54" width="3" height="24" rx="1.5" fill="var(--svg-accent-teal)" />
    <text x="269" y="70" fill="var(--svg-text-dim)" font-family="var(--font-body)" font-size="9.5" text-anchor="middle">6 Workflow Patterns</text>

    <rect x="194" y="86" width="150" height="24" rx="4" fill="var(--svg-bg-inner)" stroke="var(--svg-bg-inner-stroke)" stroke-width="0.5" />
    <rect x="194" y="86" width="3" height="24" rx="1.5" fill="var(--svg-accent-teal)" />
    <text x="269" y="102" fill="var(--svg-text-dim)" font-family="var(--font-body)" font-size="9.5" text-anchor="middle">Heartbeat Scheduler</text>

    <rect x="194" y="118" width="150" height="24" rx="4" fill="var(--svg-bg-inner)" stroke="var(--svg-bg-inner-stroke)" stroke-width="0.5" />
    <rect x="194" y="118" width="3" height="24" rx="1.5" fill="var(--svg-accent-teal)" />
    <text x="269" y="134" fill="var(--svg-text-dim)" font-family="var(--font-body)" font-size="9.5" text-anchor="middle">NLP Schedule Parser</text>
  </g>

  <!-- ═══ PILLAR 3: GOVERN ═══ -->
  <g class="svg-reveal svg-reveal-d2">
    <rect x="368" y="0" width="170" height="152" rx="8" fill="url(#ag-gov-grad)" stroke="var(--svg-stroke)" stroke-width="0.5" />
    <rect x="378" y="12" width="150" height="30" rx="6" fill="var(--svg-accent-purple)" fill-opacity="0.2" stroke="var(--svg-accent-purple)" stroke-width="0.75" stroke-opacity="0.4" />
    <g transform="translate(384, 17) scale(0.65)" fill="none" stroke="var(--svg-accent-purple)" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
      <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
    </g>
    <text x="414" y="32" fill="var(--svg-accent-purple)" font-family="var(--font-mono)" font-size="10" font-weight="700" letter-spacing="1">GOVERN</text>

    <rect x="378" y="54" width="150" height="24" rx="4" fill="var(--svg-bg-inner)" stroke="var(--svg-bg-inner-stroke)" stroke-width="0.5" />
    <rect x="378" y="54" width="3" height="24" rx="1.5" fill="var(--svg-accent-purple)" />
    <text x="453" y="70" fill="var(--svg-text-dim)" font-family="var(--font-body)" font-size="9.5" text-anchor="middle">Human-in-the-Loop</text>

    <rect x="378" y="86" width="150" height="24" rx="4" fill="var(--svg-bg-inner)" stroke="var(--svg-bg-inner-stroke)" stroke-width="0.5" />
    <rect x="378" y="86" width="3" height="24" rx="1.5" fill="var(--svg-accent-purple)" />
    <text x="453" y="102" fill="var(--svg-text-dim)" font-family="var(--font-body)" font-size="9.5" text-anchor="middle">Cost Metering</text>

    <rect x="378" y="118" width="150" height="24" rx="4" fill="var(--svg-bg-inner)" stroke="var(--svg-bg-inner-stroke)" stroke-width="0.5" />
    <rect x="378" y="118" width="3" height="24" rx="1.5" fill="var(--svg-accent-purple)" />
    <text x="453" y="134" fill="var(--svg-text-dim)" font-family="var(--font-body)" font-size="9.5" text-anchor="middle">Audit Trail</text>
  </g>

  <!-- ═══ PILLAR 4: CONVERSE ═══ -->
  <g class="svg-reveal svg-reveal-d3">
    <rect x="552" y="0" width="170" height="152" rx="8" fill="url(#ag-conv-grad)" stroke="var(--svg-stroke)" stroke-width="0.5" />
    <rect x="562" y="12" width="150" height="30" rx="6" fill="var(--svg-accent-orange)" fill-opacity="0.2" stroke="var(--svg-accent-orange)" stroke-width="0.75" stroke-opacity="0.4" />
    <g transform="translate(568, 17) scale(0.65)" fill="none" stroke="var(--svg-accent-orange)" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
      <path d="M21 15a2 2 0 01-2 2H7l-4 4V5a2 2 0 012-2h14a2 2 0 012 2z" />
    </g>
    <text x="596" y="32" fill="var(--svg-accent-orange)" font-family="var(--font-mono)" font-size="10" font-weight="700" letter-spacing="1">CONVERSE</text>

    <rect x="562" y="54" width="150" height="24" rx="4" fill="var(--svg-bg-inner)" stroke="var(--svg-bg-inner-stroke)" stroke-width="0.5" />
    <rect x="562" y="54" width="3" height="24" rx="1.5" fill="var(--svg-accent-orange)" />
    <text x="637" y="70" fill="var(--svg-text-dim)" font-family="var(--font-body)" font-size="9.5" text-anchor="middle">Multi-Model Chat</text>

    <rect x="562" y="86" width="150" height="24" rx="4" fill="var(--svg-bg-inner)" stroke="var(--svg-bg-inner-stroke)" stroke-width="0.5" />
    <rect x="562" y="86" width="3" height="24" rx="1.5" fill="var(--svg-accent-orange)" />
    <text x="637" y="102" fill="var(--svg-text-dim)" font-family="var(--font-body)" font-size="9.5" text-anchor="middle">Slack · Telegram</text>

    <rect x="562" y="118" width="150" height="24" rx="4" fill="var(--svg-bg-inner)" stroke="var(--svg-bg-inner-stroke)" stroke-width="0.5" />
    <rect x="562" y="118" width="3" height="24" rx="1.5" fill="var(--svg-accent-orange)" />
    <text x="637" y="134" fill="var(--svg-text-dim)" font-family="var(--font-body)" font-size="9.5" text-anchor="middle">Browser Automation</text>
  </g>
</svg>
```

- [ ] **Step 2: Verify the file was created**

Run: `ls -la src/components/svg/ArchitectureGlance.astro`
Expected: File exists

- [ ] **Step 3: Commit**

```bash
git add src/components/svg/ArchitectureGlance.astro
git commit -m "feat: add simplified ArchitectureGlance SVG component"
```

---

### Task 2: Integrate into Proof Section

**Files:**
- Modify: `src/components/sections/Proof.astro`
- Reference: `src/components/svg/ArchitectureGlance.astro`

- [ ] **Step 1: Add the import**

Add at the top of the frontmatter in `src/components/sections/Proof.astro`, after the existing `SectionLabel` import (line 2):

```astro
import ArchitectureGlance from '../svg/ArchitectureGlance.astro';
```

- [ ] **Step 2: Insert the architecture block after the metrics grid**

In `src/components/sections/Proof.astro`, insert the following block between the metrics grid closing `</div>` (the one with `mb-14` at ~line 43) and the Living Book `<div>` (at ~line 46):

```astro
    <!-- Architecture at a glance -->
    <div data-animate class="rounded-xl border border-border/60 bg-surface-raised/50 p-6 md:p-8 mb-14">
      <ArchitectureGlance />
      <div class="mt-4 text-center">
        <a href="/research#architecture" class="inline-flex items-center gap-1.5 text-primary font-mono text-xs tracking-wider hover:underline">
          See full architecture
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M5 12h14M12 5l7 7-7 7"/>
          </svg>
        </a>
      </div>
    </div>
```

- [ ] **Step 3: Verify the build compiles**

Run: `npm run build 2>&1 | tail -5`
Expected: Build completes without errors

- [ ] **Step 4: Commit**

```bash
git add src/components/sections/Proof.astro
git commit -m "feat: add architecture glance to homepage Proof section"
```

---

### Task 3: Visual Verification

**Files:** None (read-only verification)

- [ ] **Step 1: Start dev server and verify in browser**

Run: `npm run dev`

Navigate to `http://localhost:4321` (or whichever port Astro uses) and scroll to the Proof section. Verify:
- The 4-pillar bar appears between the metrics grid and the Living Book callout
- Each pillar shows its colored header (blue, teal, purple, orange), icon, name, and 3 capability labels
- The "See full architecture →" link appears below the diagram
- Clicking it navigates to `/research#architecture`
- Scroll-reveal animation fires when the diagram enters the viewport

- [ ] **Step 2: Verify mobile rendering**

Resize browser to 375px width. Verify:
- No horizontal scrollbar
- The SVG scales down proportionally
- Text remains legible (small but readable)
- The container card maintains proper padding

- [ ] **Step 3: Verify light mode appearance**

Confirm in light mode (the primary design target) that:
- Pillar gradient backgrounds are visible but subtle
- Inner capability boxes have sufficient contrast
- The link color matches other primary-colored links on the page
