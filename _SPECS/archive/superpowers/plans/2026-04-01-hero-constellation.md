# Hero Business Constellation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the hero section's technical architecture diagram with an animated "AI-Native Business" constellation visualization, and update the tagline to outcome-focused messaging.

**Architecture:** New `BusinessConstellation.astro` SVG component with 10 nodes (4 inner ainative product entities + 6 outer business outcomes), bezier curve connections with flowing particles, orchestrated scroll-reveal entrance, and ambient steady-state animations. Swapped into `Hero.astro` in place of `SystemArchitecture`. The existing `SystemArchitecture.astro` is untouched (still used in `research.mdx`).

**Tech Stack:** Astro components, inline SVG with SMIL animations, CSS custom properties (OKLCH), existing `svg-reveal` animation system from `global.css`.

**Spec:** `docs/superpowers/specs/2026-04-01-hero-constellation-design.md`

---

### Task 1: Create BusinessConstellation.astro — SVG Skeleton, Defs, and Atmosphere

**Files:**
- Create: `src/components/svg/BusinessConstellation.astro`

This task creates the component file with the SVG container, all `<defs>` (gradients, filters), atmospheric background glow, and the embedded `<style>` block covering animations, light mode, and reduced motion.

- [ ] **Step 1: Create the component file with SVG skeleton, defs, atmosphere, and styles**

Create `src/components/svg/BusinessConstellation.astro` with:

```astro
---
/**
 * BusinessConstellation — Hero visualization
 * Network constellation: 4 inner ainative product nodes → 6 outer business outcome nodes
 * Organic glow style with bezier curves, flowing particles, orchestrated reveal
 */
---
<svg viewBox="0 0 560 400" xmlns="http://www.w3.org/2000/svg" class="bc w-full mx-auto" data-svg-animate>
  <defs>
    <!-- Soft glow filter for Agents hero node -->
    <filter id="bc-glow">
      <feGaussianBlur stdDeviation="6" result="blur"/>
      <feMerge><feMergeNode in="blur"/><feMergeNode in="SourceGraphic"/></feMerge>
    </filter>

    <!-- Inner node radial gradient fills -->
    <radialGradient id="bc-grad-blue" cx="50%" cy="30%" r="70%">
      <stop offset="0%" stop-color="var(--svg-accent-blue)" stop-opacity="0.2"/>
      <stop offset="100%" stop-color="var(--svg-accent-blue)" stop-opacity="0.05"/>
    </radialGradient>
    <radialGradient id="bc-grad-teal" cx="50%" cy="30%" r="70%">
      <stop offset="0%" stop-color="var(--svg-accent-teal)" stop-opacity="0.2"/>
      <stop offset="100%" stop-color="var(--svg-accent-teal)" stop-opacity="0.05"/>
    </radialGradient>
    <radialGradient id="bc-grad-purple" cx="50%" cy="30%" r="70%">
      <stop offset="0%" stop-color="var(--svg-accent-purple)" stop-opacity="0.2"/>
      <stop offset="100%" stop-color="var(--svg-accent-purple)" stop-opacity="0.05"/>
    </radialGradient>
    <radialGradient id="bc-grad-orange" cx="50%" cy="30%" r="70%">
      <stop offset="0%" stop-color="var(--svg-accent-orange)" stop-opacity="0.2"/>
      <stop offset="100%" stop-color="var(--svg-accent-orange)" stop-opacity="0.05"/>
    </radialGradient>

    <!-- Central atmospheric glow -->
    <radialGradient id="bc-atmo" cx="50%" cy="50%" r="50%">
      <stop offset="0%" stop-color="var(--svg-accent-blue)" stop-opacity="0.12"/>
      <stop offset="40%" stop-color="var(--svg-accent-blue)" stop-opacity="0.04"/>
      <stop offset="100%" stop-color="var(--svg-accent-blue)" stop-opacity="0"/>
    </radialGradient>
  </defs>

  <style>
    /* Ambient animations */
    @keyframes bc-dash { to { stroke-dashoffset: -14; } }
    .bc-inner-conn { stroke-dasharray: 3 4; animation: bc-dash 3s linear infinite; }

    /* Light mode overrides */
    :global(html[data-theme="light"]) .bc .bc-atmo-circle { opacity: 0.5; }
    :global(html[data-theme="light"]) .bc .bc-outer-fill { fill: var(--svg-bg-inner); }
    :global(html[data-theme="light"]) .bc .bc-particle { opacity: 0.4; }
    :global(html[data-theme="light"]) .bc .bc-watermark { opacity: 0.2; }
    :global(html[data-theme="light"]) .bc .bc-label-secondary { opacity: 0.6; }

    /* Reduced motion */
    @media (prefers-reduced-motion: reduce) {
      .bc-inner-conn { animation: none; }
      .bc .bc-particle { display: none; }
      .bc .bc-halo { animation: none !important; }
    }
  </style>

  <!-- ═══ ATMOSPHERE ═══ -->
  <g class="svg-reveal">
    <circle class="bc-atmo-circle" cx="280" cy="200" r="190" fill="url(#bc-atmo)"/>
  </g>

  <!-- Content groups will be added in subsequent tasks -->

</svg>
```

- [ ] **Step 2: Verify file created and dev server renders**

Run: `ls -la src/components/svg/BusinessConstellation.astro`
Expected: File exists.

No visual check yet — the component isn't imported anywhere. This just confirms the file is valid.

- [ ] **Step 3: Commit**

```bash
git add src/components/svg/BusinessConstellation.astro
git commit -m "feat: add BusinessConstellation SVG skeleton with defs, atmosphere, and styles"
```

---

### Task 2: Add Inner-to-Inner Connections and Inner-to-Outer Bezier Paths

**Files:**
- Modify: `src/components/svg/BusinessConstellation.astro`

Add all connection paths between nodes. These are rendered before nodes so nodes draw on top. Includes inner diamond dashed lines, outer bezier curves, and flowing particle circles.

- [ ] **Step 1: Add connection paths and particles inside the SVG, after the atmosphere group**

Replace the `<!-- Content groups will be added in subsequent tasks -->` comment with:

```svg
  <!-- ═══ CONNECTIONS: Inner ↔ Outer (bezier curves) ═══ -->
  <g class="svg-reveal svg-reveal-d7">
    <!-- Agents → Revenue Growth -->
    <path id="bc-p-ag-rev" d="M280,155 Q200,95 115,65" fill="none" stroke="var(--svg-accent-blue)" stroke-opacity="0.1" stroke-width="1"/>
    <!-- Agents → Customer Success -->
    <path id="bc-p-ag-cus" d="M280,155 Q360,95 445,70" fill="none" stroke="var(--svg-accent-blue)" stroke-opacity="0.1" stroke-width="1"/>
    <!-- Agents → Compliance (cross) -->
    <path d="M280,155 Q400,165 490,195" fill="none" stroke="var(--svg-accent-blue)" stroke-opacity="0.06" stroke-width="0.7"/>

    <!-- Workflows → Operations Excellence -->
    <path id="bc-p-wf-ops" d="M210,215 Q140,210 70,190" fill="none" stroke="var(--svg-accent-teal)" stroke-opacity="0.1" stroke-width="1"/>
    <!-- Workflows → Cost Efficiency -->
    <path id="bc-p-wf-cost" d="M210,215 Q160,285 100,330" fill="none" stroke="var(--svg-accent-teal)" stroke-opacity="0.1" stroke-width="1"/>
    <!-- Workflows → Revenue (cross) -->
    <path d="M210,215 Q155,135 115,65" fill="none" stroke="var(--svg-accent-teal)" stroke-opacity="0.06" stroke-width="0.7"/>

    <!-- Documents → Business Intelligence -->
    <path id="bc-p-doc-bi" d="M350,215 Q405,285 460,335" fill="none" stroke="var(--svg-accent-purple)" stroke-opacity="0.1" stroke-width="1"/>
    <!-- Documents → Customer Success (cross) -->
    <path d="M350,215 Q410,150 445,70" fill="none" stroke="var(--svg-accent-purple)" stroke-opacity="0.06" stroke-width="0.7"/>

    <!-- Knowledge → Compliance & Governance -->
    <path id="bc-p-kb-comp" d="M280,275 Q395,270 490,195" fill="none" stroke="var(--svg-accent-orange)" stroke-opacity="0.1" stroke-width="1"/>
    <!-- Knowledge → Business Intelligence (cross) -->
    <path d="M280,275 Q370,315 460,335" fill="none" stroke="var(--svg-accent-orange)" stroke-opacity="0.06" stroke-width="0.7"/>
    <!-- Knowledge → Cost Efficiency -->
    <path id="bc-p-kb-cost" d="M280,275 Q185,315 100,330" fill="none" stroke="var(--svg-accent-orange)" stroke-opacity="0.1" stroke-width="1"/>
  </g>

  <!-- ═══ CONNECTIONS: Inner ↔ Inner (dashed diamond) ═══ -->
  <g class="svg-reveal svg-reveal-d4">
    <line x1="280" y1="168" x2="222" y2="207" class="bc-inner-conn" stroke="var(--svg-accent-blue)" stroke-opacity="0.08" stroke-width="0.8"/>
    <line x1="280" y1="168" x2="338" y2="207" class="bc-inner-conn" stroke="var(--svg-accent-blue)" stroke-opacity="0.08" stroke-width="0.8"/>
    <line x1="222" y1="223" x2="280" y2="262" class="bc-inner-conn" stroke="var(--svg-accent-teal)" stroke-opacity="0.06" stroke-width="0.8"/>
    <line x1="338" y1="223" x2="280" y2="262" class="bc-inner-conn" stroke="var(--svg-accent-purple)" stroke-opacity="0.06" stroke-width="0.8"/>
  </g>

  <!-- ═══ PARTICLES (flowing along bezier paths) ═══ -->
  <g class="svg-reveal svg-reveal-d8">
    <circle class="bc-particle" r="2.5" fill="var(--svg-accent-blue)" opacity="0.7">
      <animateMotion dur="4s" repeatCount="indefinite"><mpath href="#bc-p-ag-rev"/></animateMotion>
    </circle>
    <circle class="bc-particle" r="2" fill="var(--svg-accent-blue)" opacity="0.5">
      <animateMotion dur="5s" repeatCount="indefinite"><mpath href="#bc-p-ag-cus"/></animateMotion>
    </circle>
    <circle class="bc-particle" r="2.5" fill="var(--svg-accent-teal)" opacity="0.6">
      <animateMotion dur="4.5s" repeatCount="indefinite"><mpath href="#bc-p-wf-ops"/></animateMotion>
    </circle>
    <circle class="bc-particle" r="2" fill="var(--svg-accent-teal)" opacity="0.5">
      <animateMotion dur="5.5s" repeatCount="indefinite"><mpath href="#bc-p-wf-cost"/></animateMotion>
    </circle>
    <circle class="bc-particle" r="2.5" fill="var(--svg-accent-purple)" opacity="0.6">
      <animateMotion dur="4.2s" repeatCount="indefinite"><mpath href="#bc-p-doc-bi"/></animateMotion>
    </circle>
    <circle class="bc-particle" r="2" fill="var(--svg-accent-orange)" opacity="0.6">
      <animateMotion dur="5s" repeatCount="indefinite"><mpath href="#bc-p-kb-comp"/></animateMotion>
    </circle>
    <circle class="bc-particle" r="2.5" fill="var(--svg-accent-orange)" opacity="0.5">
      <animateMotion dur="4.8s" repeatCount="indefinite"><mpath href="#bc-p-kb-cost"/></animateMotion>
    </circle>
  </g>
```

- [ ] **Step 2: Commit**

```bash
git add src/components/svg/BusinessConstellation.astro
git commit -m "feat: add constellation connection paths and flowing particles"
```

---

### Task 3: Add Inner Nodes (ainative Product Entities)

**Files:**
- Modify: `src/components/svg/BusinessConstellation.astro`

Add the 4 inner nodes with icons, labels, and breathing halo animations. Insert after the particles group.

- [ ] **Step 1: Add inner nodes group after the particles group**

Insert before the closing `</svg>`:

```svg
  <!-- ═══ INNER NODES: ainative Product Entities ═══ -->

  <!-- Agents (top center — hero node) -->
  <g class="svg-reveal svg-reveal-d1">
    <circle class="bc-halo" cx="280" cy="155" r="32" fill="none" stroke="var(--svg-accent-blue)" stroke-opacity="0.15" stroke-width="0.5">
      <animate attributeName="r" values="32;35;32" dur="4s" repeatCount="indefinite"/>
      <animate attributeName="stroke-opacity" values="0.15;0.06;0.15" dur="4s" repeatCount="indefinite"/>
    </circle>
    <circle cx="280" cy="155" r="32" fill="url(#bc-grad-blue)" stroke="var(--svg-accent-blue)" stroke-opacity="0.4" stroke-width="1.2" filter="url(#bc-glow)"/>
    <!-- Bot icon -->
    <rect x="268" y="140" width="24" height="16" rx="4" fill="none" stroke="var(--svg-accent-blue)" stroke-width="1.2"/>
    <circle cx="275" cy="148" r="2" fill="var(--svg-accent-blue)"/>
    <circle cx="285" cy="148" r="2" fill="var(--svg-accent-blue)"/>
    <line x1="280" y1="140" x2="280" y2="135" stroke="var(--svg-accent-blue)" stroke-width="1"/>
    <circle cx="280" cy="133" r="1.5" fill="var(--svg-accent-blue)"/>
    <text x="280" y="174" text-anchor="middle" fill="var(--svg-accent-blue)" font-size="8" font-family="var(--font-body)" font-weight="600">Agents</text>
  </g>

  <!-- Workflows (center-left) -->
  <g class="svg-reveal svg-reveal-d2">
    <circle class="bc-halo" cx="210" cy="215" r="26" fill="none" stroke="var(--svg-accent-teal)" stroke-opacity="0.12" stroke-width="0.5">
      <animate attributeName="r" values="26;29;26" dur="5s" repeatCount="indefinite"/>
      <animate attributeName="stroke-opacity" values="0.12;0.05;0.12" dur="5s" repeatCount="indefinite"/>
    </circle>
    <circle cx="210" cy="215" r="26" fill="url(#bc-grad-teal)" stroke="var(--svg-accent-teal)" stroke-opacity="0.4" stroke-width="1"/>
    <!-- Fork/branch icon -->
    <path d="M203,208 L210,208 L217,203" fill="none" stroke="var(--svg-accent-teal)" stroke-width="1.2" stroke-linecap="round"/>
    <path d="M203,208 L210,208 L217,213" fill="none" stroke="var(--svg-accent-teal)" stroke-width="1.2" stroke-linecap="round"/>
    <circle cx="217" cy="203" r="1.5" fill="var(--svg-accent-teal)"/>
    <circle cx="217" cy="213" r="1.5" fill="var(--svg-accent-teal)"/>
    <circle cx="203" cy="208" r="1.5" fill="var(--svg-accent-teal)"/>
    <text x="210" y="234" text-anchor="middle" fill="var(--svg-accent-teal)" font-size="7.5" font-family="var(--font-body)" font-weight="600">Workflows</text>
  </g>

  <!-- Documents (center-right) -->
  <g class="svg-reveal svg-reveal-d3">
    <circle class="bc-halo" cx="350" cy="215" r="26" fill="none" stroke="var(--svg-accent-purple)" stroke-opacity="0.12" stroke-width="0.5">
      <animate attributeName="r" values="26;29;26" dur="4.5s" repeatCount="indefinite"/>
      <animate attributeName="stroke-opacity" values="0.12;0.05;0.12" dur="4.5s" repeatCount="indefinite"/>
    </circle>
    <circle cx="350" cy="215" r="26" fill="url(#bc-grad-purple)" stroke="var(--svg-accent-purple)" stroke-opacity="0.4" stroke-width="1"/>
    <!-- Document icon -->
    <rect x="343" y="205" width="14" height="16" rx="2" fill="none" stroke="var(--svg-accent-purple)" stroke-width="1.1"/>
    <line x1="346" y1="210" x2="354" y2="210" stroke="var(--svg-accent-purple)" stroke-width="0.8" stroke-opacity="0.6"/>
    <line x1="346" y1="213" x2="352" y2="213" stroke="var(--svg-accent-purple)" stroke-width="0.8" stroke-opacity="0.6"/>
    <line x1="346" y1="216" x2="350" y2="216" stroke="var(--svg-accent-purple)" stroke-width="0.8" stroke-opacity="0.6"/>
    <text x="350" y="234" text-anchor="middle" fill="var(--svg-accent-purple)" font-size="7.5" font-family="var(--font-body)" font-weight="600">Documents</text>
  </g>

  <!-- Knowledge (bottom center) -->
  <g class="svg-reveal svg-reveal-d4">
    <circle class="bc-halo" cx="280" cy="275" r="26" fill="none" stroke="var(--svg-accent-orange)" stroke-opacity="0.12" stroke-width="0.5">
      <animate attributeName="r" values="26;29;26" dur="5.5s" repeatCount="indefinite"/>
      <animate attributeName="stroke-opacity" values="0.12;0.05;0.12" dur="5.5s" repeatCount="indefinite"/>
    </circle>
    <circle cx="280" cy="275" r="26" fill="url(#bc-grad-orange)" stroke="var(--svg-accent-orange)" stroke-opacity="0.4" stroke-width="1"/>
    <!-- Lightbulb icon -->
    <circle cx="280" cy="268" r="6" fill="none" stroke="var(--svg-accent-orange)" stroke-width="1.1"/>
    <line x1="277" y1="275" x2="283" y2="275" stroke="var(--svg-accent-orange)" stroke-width="1" stroke-linecap="round"/>
    <line x1="278" y1="277" x2="282" y2="277" stroke="var(--svg-accent-orange)" stroke-width="0.8" stroke-linecap="round"/>
    <text x="280" y="294" text-anchor="middle" fill="var(--svg-accent-orange)" font-size="7.5" font-family="var(--font-body)" font-weight="600">Knowledge</text>
  </g>
```

- [ ] **Step 2: Commit**

```bash
git add src/components/svg/BusinessConstellation.astro
git commit -m "feat: add inner ainative product nodes with icons and breathing halos"
```

---

### Task 4: Add Outer Nodes (Business Outcomes) and Watermark

**Files:**
- Modify: `src/components/svg/BusinessConstellation.astro`

Add the 6 outer business outcome nodes and the center watermark. Insert after the Knowledge node group, before `</svg>`.

- [ ] **Step 1: Add outer nodes and watermark**

Insert before the closing `</svg>`:

```svg
  <!-- ═══ OUTER NODES: Business Outcomes ═══ -->

  <!-- Revenue Growth (top-left) -->
  <g class="svg-reveal svg-reveal-d5">
    <circle cx="115" cy="65" r="22" class="bc-outer-fill" fill="var(--svg-bg)" stroke="var(--svg-accent-blue)" stroke-opacity="0.25" stroke-width="0.8"/>
    <!-- Trending up icon -->
    <path d="M105,71 L112,63 L118,68 L125,60" fill="none" stroke="var(--svg-accent-blue)" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round"/>
    <path d="M121,60 L125,60 L125,64" fill="none" stroke="var(--svg-accent-blue)" stroke-width="1" stroke-linecap="round"/>
    <text x="115" y="80" text-anchor="middle" fill="var(--svg-text-dim)" font-size="6.5" font-family="var(--font-body)">Revenue</text>
    <text x="115" y="88" text-anchor="middle" class="bc-label-secondary" fill="var(--svg-text-dim)" font-size="5" font-family="var(--font-body)" opacity="0.7">Growth</text>
  </g>

  <!-- Customer Success (top-right) -->
  <g class="svg-reveal svg-reveal-d5">
    <circle cx="445" cy="70" r="22" class="bc-outer-fill" fill="var(--svg-bg)" stroke="var(--svg-accent-teal)" stroke-opacity="0.25" stroke-width="0.8"/>
    <!-- Checkmark icon -->
    <path d="M437,70 L442,75 L453,64" fill="none" stroke="var(--svg-accent-teal)" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round"/>
    <text x="445" y="85" text-anchor="middle" fill="var(--svg-text-dim)" font-size="6.5" font-family="var(--font-body)">Customer</text>
    <text x="445" y="93" text-anchor="middle" class="bc-label-secondary" fill="var(--svg-text-dim)" font-size="5" font-family="var(--font-body)" opacity="0.7">Success</text>
  </g>

  <!-- Operations Excellence (left) -->
  <g class="svg-reveal svg-reveal-d6">
    <circle cx="70" cy="190" r="22" class="bc-outer-fill" fill="var(--svg-bg)" stroke="var(--svg-accent-teal)" stroke-opacity="0.25" stroke-width="0.8"/>
    <!-- Gear icon -->
    <circle cx="70" cy="187" r="5.5" fill="none" stroke="var(--svg-accent-teal)" stroke-width="1"/>
    <circle cx="70" cy="187" r="2" fill="var(--svg-accent-teal)" opacity="0.5"/>
    <text x="70" y="205" text-anchor="middle" fill="var(--svg-text-dim)" font-size="6.5" font-family="var(--font-body)">Operations</text>
    <text x="70" y="213" text-anchor="middle" class="bc-label-secondary" fill="var(--svg-text-dim)" font-size="5" font-family="var(--font-body)" opacity="0.7">Excellence</text>
  </g>

  <!-- Cost Efficiency (bottom-left) -->
  <g class="svg-reveal svg-reveal-d6">
    <circle cx="100" cy="330" r="22" class="bc-outer-fill" fill="var(--svg-bg)" stroke="var(--svg-accent-orange)" stroke-opacity="0.25" stroke-width="0.8"/>
    <!-- Down-trend icon -->
    <path d="M90,324 L97,330 L103,326 L110,334" fill="none" stroke="var(--svg-accent-orange)" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round"/>
    <path d="M106,334 L110,334 L110,330" fill="none" stroke="var(--svg-accent-orange)" stroke-width="1" stroke-linecap="round"/>
    <text x="100" y="345" text-anchor="middle" fill="var(--svg-text-dim)" font-size="6.5" font-family="var(--font-body)">Cost</text>
    <text x="100" y="353" text-anchor="middle" class="bc-label-secondary" fill="var(--svg-text-dim)" font-size="5" font-family="var(--font-body)" opacity="0.7">Efficiency</text>
  </g>

  <!-- Business Intelligence (bottom-right) -->
  <g class="svg-reveal svg-reveal-d7">
    <circle cx="460" cy="335" r="22" class="bc-outer-fill" fill="var(--svg-bg)" stroke="var(--svg-accent-purple)" stroke-opacity="0.25" stroke-width="0.8"/>
    <!-- Bar chart icon -->
    <rect x="451" y="332" width="4" height="8" rx="0.5" fill="var(--svg-accent-purple)" opacity="0.6"/>
    <rect x="457" y="328" width="4" height="12" rx="0.5" fill="var(--svg-accent-purple)" opacity="0.6"/>
    <rect x="463" y="324" width="4" height="16" rx="0.5" fill="var(--svg-accent-purple)" opacity="0.6"/>
    <text x="460" y="350" text-anchor="middle" fill="var(--svg-text-dim)" font-size="6.5" font-family="var(--font-body)">Business</text>
    <text x="460" y="358" text-anchor="middle" class="bc-label-secondary" fill="var(--svg-text-dim)" font-size="5" font-family="var(--font-body)" opacity="0.7">Intelligence</text>
  </g>

  <!-- Compliance & Governance (right) -->
  <g class="svg-reveal svg-reveal-d7">
    <circle cx="490" cy="195" r="22" class="bc-outer-fill" fill="var(--svg-bg)" stroke="var(--svg-accent-purple)" stroke-opacity="0.25" stroke-width="0.8"/>
    <!-- Shield with check icon -->
    <path d="M490,185 L498,189 L498,196 C498,201 490,205 490,205 C490,205 482,201 482,196 L482,189 Z" fill="none" stroke="var(--svg-accent-purple)" stroke-width="1"/>
    <path d="M486,196 L489,199 L494,193" fill="none" stroke="var(--svg-accent-purple)" stroke-width="0.9" stroke-linecap="round"/>
    <text x="490" y="211" text-anchor="middle" fill="var(--svg-text-dim)" font-size="6.5" font-family="var(--font-body)">Compliance</text>
    <text x="490" y="219" text-anchor="middle" class="bc-label-secondary" fill="var(--svg-text-dim)" font-size="5" font-family="var(--font-body)" opacity="0.7">& Governance</text>
  </g>

  <!-- ═══ CENTER WATERMARK ═══ -->
  <text class="bc-watermark svg-reveal svg-reveal-d4" x="280" y="218" text-anchor="middle" fill="var(--svg-accent-blue)" font-size="5.5" font-family="var(--font-mono)" letter-spacing="3" opacity="0.35">AINATIVE</text>
```

- [ ] **Step 2: Commit**

```bash
git add src/components/svg/BusinessConstellation.astro
git commit -m "feat: add outer business outcome nodes, icons, and watermark"
```

---

### Task 5: Integrate into Hero.astro — Swap Component and Update Copy

**Files:**
- Modify: `src/components/sections/Hero.astro:1-112`

Replace the `SystemArchitecture` import with `BusinessConstellation`, update the tagline paragraph, and change the "5 Runtimes" pill to "Multi-Model AI".

- [ ] **Step 1: Update the import**

In `src/components/sections/Hero.astro`, change line 3:

Old:
```
import SystemArchitecture from '../svg/SystemArchitecture.astro';
```

New:
```
import BusinessConstellation from '../svg/BusinessConstellation.astro';
```

- [ ] **Step 2: Update the tagline paragraph**

In `src/components/sections/Hero.astro`, replace the `<p>` tag content (lines 29-34):

Old:
```
        Stop cobbling together 15 disconnected tools. ainative orchestrates AI agents across your entire business — with the governance, visibility, and cost controls that keep you in charge.
```

New:
```
        Every function automated. Every decision informed. Every risk governed.
```

- [ ] **Step 3: Update the value proposition pill**

In `src/components/sections/Hero.astro`, change the "5 Runtimes" pill (line 68):

Old:
```
        <span class="font-mono text-[10px] tracking-wider text-primary border border-primary/20 bg-primary/5 rounded-full px-2.5 py-1">5 Runtimes</span>
```

New:
```
        <span class="font-mono text-[10px] tracking-wider text-primary border border-primary/20 bg-primary/5 rounded-full px-2.5 py-1">Multi-Model AI</span>
```

- [ ] **Step 4: Swap the component in the right column**

In `src/components/sections/Hero.astro`, replace line 76:

Old:
```
      <SystemArchitecture />
```

New:
```
      <BusinessConstellation />
```

- [ ] **Step 5: Commit**

```bash
git add src/components/sections/Hero.astro
git commit -m "feat: swap hero to BusinessConstellation, update tagline and pills"
```

---

### Task 6: Visual Verification

**Files:** None (read-only verification)

Run the dev server and verify the implementation matches the spec across all dimensions.

- [ ] **Step 1: Start dev server**

Run: `npm run dev`
Expected: Server starts on localhost, no build errors.

- [ ] **Step 2: Desktop dark mode verification**

Open `http://localhost:4321` in browser at 1440px width.

Verify:
- Constellation renders in right column of hero
- 4 inner nodes visible with colored gradient fills and breathing halos
- 6 outer nodes visible with stroke-only icons
- Bezier connections visible between inner and outer nodes
- Particles flowing along paths
- Dashed inner connections animating
- "AINATIVE" watermark visible at center
- Tagline reads "Every function automated. Every decision informed. Every risk governed."
- Pill reads "Multi-Model AI" (not "5 Runtimes")
- Clicking constellation navigates to `/research`
- TechTicker still visible below hero

- [ ] **Step 3: Light mode verification**

Toggle to light mode via theme switcher.

Verify:
- All nodes visible with adequate contrast
- Glow/atmosphere reduced (less prominent than dark mode)
- Outer node fills switch to light background
- Labels readable against light background
- Particles less prominent but visible

- [ ] **Step 4: Responsive verification**

Check at 375px (mobile) and 768px (tablet).

Verify:
- Constellation stacks below content on mobile
- SVG scales properly (viewBox handles responsive)
- Labels still readable at small sizes
- No horizontal overflow

- [ ] **Step 5: Reduced motion verification**

In browser DevTools → Rendering → check "Emulate CSS prefers-reduced-motion: reduce".

Verify:
- Particles hidden
- Breathing halos static
- Dashed line animation stopped
- Nodes and connections still visible (static state)

- [ ] **Step 6: Research paper regression check**

Navigate to `/research`.

Verify:
- SystemArchitecture diagram still renders correctly as Figure 8
- No visual changes to the research paper page

- [ ] **Step 7: Commit (if any fixes were needed)**

Only if fixes were applied during verification:
```bash
git add -A
git commit -m "fix: visual adjustments from constellation verification"
```
