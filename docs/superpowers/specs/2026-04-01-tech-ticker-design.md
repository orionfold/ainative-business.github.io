# Technology Ticker — Design Spec

## Context

The ainative landing page hero section needs a continuous scrolling ticker at its bottom edge to visually communicate the breadth of technologies ainative integrates with. The ticker groups logos by architecture layer (AI Runtimes, Channels, Browser Use, Platform, Data) using category pill labels that match the existing value proposition pills aesthetic. This reinforces the "operating system for AI-native business" messaging by showing the technology ecosystem at a glance.

## Component

**File:** `src/components/sections/TechTicker.astro`

Single Astro component using inline SVG paths from Simple Icons. No new npm dependencies.

## Technology Groups

| Category Label | Technologies |
|---------------|-------------|
| AI RUNTIMES | Anthropic, OpenAI, Ollama |
| CHANNELS | Slack, Telegram |
| BROWSER USE | Google Chrome, Playwright |
| PLATFORM | Next.js, React, TypeScript, Tailwind CSS |
| DATA | SQLite, Drizzle |

5 categories, 13 icons total.

## Visual Design

### Layout
- Full-width, positioned `absolute bottom-8 left-0 right-0` inside the hero `<section>`
- Sits above the atmospheric glow (`z-10`) but visually part of the hero's bottom edge
- Content overflows hidden; CSS mask fades edges to transparent

### Category Pills
- Style matches existing value prop pills but smaller
- `font-mono text-[9px] tracking-wider text-primary border border-primary/20 bg-primary/5 rounded-full px-2 py-0.5`

### Logo Items
- 18px Simple Icons SVG (monochrome, filled with `text-text-dim`)
- 11px label text in `text-text-dim`
- `gap-3` between icon and label within an item
- `gap-8` between items within a group

### Group Separators
- Vertical divider: `w-px h-4 bg-border` between groups

### Edge Fade
- CSS `mask-image: linear-gradient(to right, transparent, black 8%, black 92%, transparent)`
- Creates smooth fade at both horizontal edges

### Animation
- `@keyframes ticker-scroll { from { transform: translateX(0); } to { transform: translateX(-50%); } }`
- Duration: `40s linear infinite`
- Content is duplicated (rendered twice) for seamless loop
- `@media (prefers-reduced-motion: reduce)` pauses the animation

### Theming
- All colors use CSS custom properties (`--color-primary`, `--color-text-dim`, `--color-border`)
- Light/dark theme works automatically via existing OKLCH token overrides
- Light-first design: designed primarily for light theme appearance

## Logo Sourcing

Inline SVG `<path>` data from Simple Icons (https://simpleicons.org/). Each icon stored as an object in an Astro frontmatter array:

```typescript
const groups = [
  {
    label: 'AI RUNTIMES',
    items: [
      { name: 'Anthropic', path: '...' },
      { name: 'OpenAI', path: '...' },
      { name: 'Ollama', path: '...' },
    ]
  },
  // ... etc
];
```

## Integration into Hero.astro

- Import `TechTicker` component
- Place just before the closing `</section>` tag
- After the existing bottom gradient fade div
- No `data-animate` attribute — the ticker is above the fold and should be visible immediately

## Files to Create/Modify

| File | Action |
|------|--------|
| `src/components/sections/TechTicker.astro` | Create — new ticker component |
| `src/components/sections/Hero.astro` | Modify — import and place TechTicker |

## Verification

1. Run `npm run dev` and verify ticker appears at hero bottom
2. Check both light and dark themes
3. Verify seamless infinite scroll (no visible seam/jump)
4. Verify edge fade masks work on both sides
5. Test `prefers-reduced-motion` (animation should pause)
6. Confirm responsive behavior on mobile (ticker should still scroll, just narrower)
7. Verify the ticker visually connects hero to the Problem section below
