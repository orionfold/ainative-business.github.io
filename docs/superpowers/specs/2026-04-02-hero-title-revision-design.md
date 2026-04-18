# Hero Title Revision Design

## Context

The current hero title "The Operating System for AI-Native Business" is a category-defining statement that's 7 words across 2 lines. It requires readers to already understand the problem space and doesn't immediately connect with the three target personas (Solo Founder, Agency Owner, PE Operating Partner). We're revising to an outcome-first, aspirational, single-line title that resonates across all personas.

## Design

### Title

**Before:** "The Operating System for AI-Native Business"
**After:** "Your Business, Run by AI"

- Single line, 5 words
- Outcome-first: leads with the transformation, not the product category
- "Your" makes it personal — each persona sees their own business
- The comma creates a dramatic pause that adds weight to "Run by AI"

### Subtitle

**Before:** "AI agents that grow revenue, cut costs, and govern themselves. Every function automated. Every decision informed. Every risk governed."

**After:** "Orchestrate AI agents across every function — marketing, sales, support, operations — governed, auditable, and under your control."

- Bridges from bold title to how it works
- Names specific functions so each persona sees their world
- Ends with governance differentiator ("under your control") — ainative's key moat
- Single sentence vs. the previous 4 fragmented sentences

### Persona resonance

| Persona | Title reads as | Subtitle hooks |
|---------|---------------|----------------|
| Solo Founder | "MY business can run on AI" | marketing, sales, support |
| Agency Owner | "Client businesses, run by AI" | every function, orchestrate |
| PE Partner | "Portfolio companies, run by AI" | governed, auditable, under your control |

### What stays unchanged

- Value pills: Local-First, Multi-Model AI, Human-in-the-Loop
- Email CTA: "Get Early Access"
- Terminal CTA: `npx ainative`
- Architecture diagram (right column)
- All styling, layout, and animations

### Files to modify

1. `src/components/sections/Hero.astro` — lines 26-27 (title), line 33 (subtitle)
2. `src/layouts/Layout.astro` — line 19, default page title uses old title
3. `src/pages/og.astro` — line 122, OG image generator uses old title
4. `src/pages/research.mdx` — line 157, heading references old title

### SEO consideration

Update the site's default page title in `Layout.astro` to "ainative — Your Business, Run by AI" to align with the new hero. The OG image template should also reflect the new title for social sharing.

## Verification

1. Run `npm run dev` and visually confirm the hero section
2. Check that the title renders on a single line at desktop and wraps gracefully on mobile
3. Verify meta tags in page source reflect updated copy
4. Confirm no other components reference the old title text
