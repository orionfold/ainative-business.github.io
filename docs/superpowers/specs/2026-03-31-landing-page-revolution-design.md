# Landing Page Revolution + Research Paper Rewrite

**Date:** 2026-03-31
**Status:** Approved
**Approach:** Revolution — Persona-Led Narrative (clean break from existing layout)

---

## Context

ainative's product has evolved significantly — 74 features across 15 surfaces, including multi-channel chat (Slack/Telegram), heartbeat scheduling, episodic agent memory, 6 business-function profiles, 5 AI runtimes (including Ollama), and smart runtime routing. The vision has been refined through two strategic documents that reposition ainative from "Governed AI Agent Workspace" to "The Operating System for AI-Native Business."

The current landing page positions ainative as a developer governance tool with technical feature-card layout (RuntimeBridge, 15 feature cards, architecture diagrams). This doesn't serve the new target personas (solo founders, agency owners, PE operating partners) or the new monetization strategy (product tiers + consulting advisory).

**Goals:**
1. Reposition the landing page around the bold "AI Business OS" vision with honest current/roadmap framing
2. Introduce pricing (Free/Pro/Team + Advisory consulting)
3. Convert the newsletter form into a demand-generation lead capture CTA (email only)
4. Rewrite the research paper as a market-facing "AI Transformation Playbook"

---

## Landing Page: 7-Section Narrative Flow

### Section 1: Hero

**Headline:** "The Operating System for AI-Native Business"
**Subheadline:** "Stop cobbling together 15 disconnected tools. ainative orchestrates AI agents across your entire business — with the governance, visibility, and cost controls that keep you in charge."

**Layout:**
- Headline → Subheadline → Email capture (primary CTA) → GitHub link (secondary)
- Value prop pills: Open Source · Local-First · Multi-Runtime · Human-in-the-Loop
- Product carousel (keep existing 9-screenshot rotating carousel)

**Primary CTA:** Single email input + "Get Early Access" button (replaces `npx ainative` terminal prompt)
**Secondary CTA:** "View on GitHub" link

**Key files to modify:**
- `src/pages/index.astro` — section composition
- `src/components/Hero.astro` — headline, CTA, layout
- New: email capture component (reuse/adapt existing newsletter form)

---

### Section 2: Problem — "The Missing Layer in Your AI Stack"

**New section — does not exist today.**

**Headline:** "The Missing Layer in Your AI Stack"
**Subtitle:** "AI models are powerful. Agent frameworks are maturing. But between 'run this agent' and 'run my business' — there's a gap no one has filled."

**Tone:** Educational, opportunity-framed (not fear-based)

**Content:**
- 3 opportunity stat cards (indigo/blue, not red):
  - $52.6B — AI agent market by 2030, 46% CAGR
  - 36.3% — of new startups are solo-founded (Carta)
  - 1,445% — surge in agentic AI inquiries (Gartner)
- Bridge paragraph: "The demand is real. But most founders still stitch together 8–15 disconnected tools..."
- 4 capability gap cards (compact, icon-led):
  - Orchestration — agents that work together, not in silos
  - Visibility — see what's running, what it costs, what needs attention
  - Governance — human oversight without slowing agents down
  - Lifecycle — plan → build → operate → grow in one place
- Transition: "That's what ainative builds. ↓"

**Key files:**
- New: `src/components/Problem.astro`

---

### Section 3: Solution — Persona Swim Lanes

**Replaces:** RuntimeBridge + ProductOverview sections

**Headline:** "One Platform. Three Ways to Win."

**Layout:** Three columns, each addressing a persona:

**Solo Founder lane — "Run your business with AI agents"**
- Marketing, sales, support agents working proactively
- Chat with your business from Slack or Telegram
- See everything on one dashboard
- Heartbeat scheduling keeps agents running overnight

**Agency Owner lane — "Deploy AI operations for every client"**
- Reusable profiles and workflow blueprints
- Multi-project portfolio management
- Cost tracking per client engagement
- Import and customize skills from repos

**PE Operating Partner lane — "Transform portfolio companies at scale"**
- Standardized AI playbooks across companies
- Governed execution with audit trails
- EBITDA-trackable agent ROI
- *Some items marked as roadmap*

**Shared platform layer (below lanes):**
5 runtimes · 21+ profiles · 6 workflow patterns · Human-in-the-loop · Cost metering · Open source

**Key files:**
- New: `src/components/PersonaLanes.astro`
- Remove: `src/components/RuntimeBridge.astro` (from landing page only)
- Remove: `src/components/ProductOverview.astro` (from landing page only)

---

### Section 4: Proof — "Not Slideware. Shipped Software."

**Replaces:** No direct predecessor (new section, absorbs Book showcase)

**Headline:** "Not Slideware. Shipped Software."
**Subtitle:** "Every feature below is live, open-source, and inspectable on GitHub."

**Content:**
- Metric bar (5 stats): 74 features · 15 surfaces · 5 runtimes · 21+ profiles · 6 workflow patterns
- Living Book showcase: callout card with book icon, description of the self-writing book, "Read the Living Book →" CTA
- Market validation quotes (2):
  - Sam Altman on one-person billion-dollar companies
  - Dario Amodei on 70-80% odds in 2026
- Open-source trust line: "Open source under Apache 2.0 · Every line inspectable on GitHub · Local-first — your data never leaves your machine"

**Key files:**
- New: `src/components/Proof.astro`

---

### Section 5: Pricing — Product Tiers + Advisory

**New section — does not exist today.**

**Headline:** "Start Free. Scale When You're Ready."
**Subtitle:** "Open-source foundation. Premium capabilities as you grow."

**Product tiers (3 cards):**

| | Starter | Pro | Team |
|---|---|---|---|
| Price | Free forever | $149/mo | $499/mo |
| Badge | — | Coming Soon | Coming Soon |
| Target | Everyone | Solo founders & agencies | Teams & portfolios |
| Key features | Full local workspace, 21+ profiles, 6 workflow patterns, HITL, 5 runtimes, community support | Everything in Starter + cloud sync, advanced workflows, multi-channel delivery, priority support, skills marketplace | Everything in Pro + multi-user workspaces, shared governance, portfolio dashboards, RBAC, dedicated support |
| CTA | `npx ainative` | Join Waitlist | Join Waitlist |

Pro tier visually highlighted (indigo border, recommended).

**Advisory block (below tiers):**
- Dark indigo background — visually distinct, premium feel
- Headline: "AI Transformation Advisory"
- Description: "We help agencies and PE-backed companies design, deploy, and govern AI agent operations."
- 6 service offerings in 2-column grid:
  - AI operations strategy
  - Agent workflow design
  - Portfolio-wide deployment
  - Governance framework setup
  - Team training & enablement
  - ROI measurement & reporting
- Email capture + "Book a Conversation" CTA (separate from waitlist)

**Key files:**
- New: `src/components/Pricing.astro`

---

### Section 6: Playbook Teaser

**Headline:** "The AI Transformation Playbook"
**Subtitle:** "How solo founders, agencies, and PE firms are building AI-native businesses"

**Content:**
- 3-4 topic preview cards (compact, single row):
  - The $52B market landscape
  - The governance gap nobody's filling
  - The PE AI transformation wave
  - Building your first AI-native business
- CTA: "Read the Playbook →" linking to `/research`

**Key files:**
- New: `src/components/PlaybookTeaser.astro`

---

### Section 7: CTA Footer

**Replaces:** Existing CTAFooter

**Headline:** "Ready to build an AI-native business?"
**Email input + "Get Early Access" button** (same form component as hero)
**Secondary links:** GitHub · Documentation · Playbook
**Tagline:** "The operating system for the agentic economy"

**Key files:**
- Modify: `src/components/CTAFooter.astro`

---

## Research Paper → "The AI Transformation Playbook"

**Full rewrite** of `src/pages/research.mdx`. Drop investor framing, lead with market-facing thought leadership.

**Proposed structure:**

1. **The Agentic Economy is Here** — Market size ($7.6B → $52.6B), adoption velocity, the one-person unicorn thesis
2. **The Governance Gap** — Why 80-90% of agent projects fail in production, the missing layer between autonomy and control
3. **The PE Transformation Wave** — Vista's Agentic AI Factory, Hg Catalyst, Apollo's 40% cost reductions, $200B in accounting PE deals
4. **Building AI-Native Businesses** — The orchestration gap, strategy-to-execution gap, business lifecycle gap, solo founder opportunity
5. **The ainative Approach** — Platform architecture, four pillars (orchestrate, automate, govern, converse), what's shipped vs. roadmap
6. **Use Cases by Industry** — Professional services, BPO, insurance, marketing agencies, e-commerce
7. **The 10x Vision** — Agent marketplace flywheel, business-as-a-service platform, physical AI governance
8. **Getting Started** — Free tier, advisory services, community

**Tone:** Authoritative thought leadership, publishable sections on LinkedIn. Cite sources (Gartner, RAND, Carta, BCG, McKinsey).

**Key files:**
- Rewrite: `src/pages/research.mdx`

---

## Navigation Updates

- "Research" → "Playbook" in nav
- Add "Pricing" anchor link (scrolls to Section 5)
- Keep: Docs, Book, GitHub links

---

## Sections Removed from Landing Page (Clean Break)

| Removed Component | Fate |
|---|---|
| `RuntimeBridge.astro` | Not relocated — content exists in docs |
| `ProductOverview.astro` | Not relocated — absorbed into persona lanes |
| `Features.astro` (15 cards) | Not relocated — content exists in docs |
| `Architecture.astro` | Not relocated — content exists in docs |
| `MarketPosition.astro` | Not relocated — stats absorbed into Problem section, matrix moves to Playbook |

These components are removed from `index.astro` imports. Component files can remain in the codebase but are not rendered on the landing page.

---

## Email Capture Implementation

**Existing component:** `src/components/ui/WaitlistForm.astro` — already supports `variant` prop (`hero`, `cta`, `footer`), Supabase edge function endpoint, honeypot spam protection, and success/error states.

**Changes needed:**
- Add a `source` prop (e.g., `"hero"`, `"pricing-waitlist"`, `"pricing-advisory"`, `"footer"`) passed in the POST body for lead segmentation
- Add a `buttonText` prop to customize: "Get Early Access" / "Join Waitlist" / "Book a Conversation" (currently hardcoded as "Subscribe")
- Update success copy from "Check your inbox to confirm your subscription" to context-appropriate messaging
- Supabase edge function may need a minor update to store the `source` field

---

## Screenshot Refresh

Dependent on user completing fresh screengrabs in `/Users/manavsehgal/Developer/ainative/screengrabs/`. The carousel in Section 1 will use updated screenshots once available. Docs and user guide updates are also pending.

---

## Verification Plan

1. **Visual check:** Run `npm run dev` and verify all 7 sections render correctly on desktop and mobile
2. **Email capture:** Test all 3 email forms submit successfully with source parameter
3. **Links:** Verify Playbook, Book, GitHub, Docs, and anchor links work
4. **Responsive:** Check persona swim lanes collapse gracefully on mobile (stack vertically)
5. **Lighthouse:** Run audit — target 90+ performance score (current site is well-optimized)
6. **Content review:** Verify no broken stat references, quote attributions are accurate
7. **Playbook page:** Full read-through of rewritten research paper for tone and accuracy
