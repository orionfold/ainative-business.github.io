# Voice and positioning for product-launch articles

A product article is a different genre from a tech-writer deep-dive, and the
difference is the whole point of having a separate skill. The deep-dive teaches
a concept and uses the work as evidence. The product article **introduces a
thing the reader can have**, shows what it took to build it, and makes the case
for the workflow that produced it. It is closer to a launch essay than a
tutorial — but it is still written in the operator's first-person builder voice,
not a press release.

Read this before writing any prose. Voice drift here goes two ways: toward dry
documentation (loses the launch energy) or toward hype (loses credibility).

## The two readers, and how to serve both

Every product article in this repo has to land for two people at once:

- **The AI researcher** wants to know what the product *unlocks* — live
  experimentation, faster decisions, a tighter prototype loop on the Spark.
  They read top to bottom and care about the argument: why this surface changes
  how research gets done on one machine.
- **The Spark operator / power user** wants to know what each feature *does for
  them* and what it looks like. They scan. They stop at screenshots. The
  feature tour is written for them — one capture, one concrete benefit.

Don't pick one and abandon the other. Structure the piece so the narrative
spine carries the researcher and the feature tour carries the operator, with
the build-metrics infographic as the hinge that interests both. A good test:
if you deleted every screenshot, the researcher's argument should still stand;
if you read only the screenshots and their captions, the operator should still
understand the product.

## Positioning first, always

This repo already runs a positioning-first discipline on HuggingFace model
cards (lead with what it is and who it's for, not with caveats or roadmap). The
same rule governs product articles. The first two paragraphs answer:

1. **What is this?** Name it and say what it is in one plain sentence.
2. **Who is it for, and what does it let them do they couldn't before?**

Only after positioning do you earn the right to talk about how it was built,
the metrics, and the workflow. A launch piece that opens with "over the last
day I…" buries the product behind the process. Open with the product.

## Never punch at, name, or imply a competitor

This is a hard line, and it has bitten before — there is even a comment in the
Arena source that punches at a named competitor. **That energy never reaches
the prose.** Specifically:

- Never name a competing product or company.
- Never frame the product as a clone, a copy, an alternative-to, or "what X
  can't do." Even an oblique "unlike the hosted tools" invites the comparison
  you're trying to avoid and reads as defensive.
- State the product's strengths on their own terms. "It draws the efficiency
  frontier because it knows exactly which hardware every number came from" is a
  strength. "…which the cloud tools can't do" is a punch — cut the clause.
- The strongest positioning is *what's uniquely true here* (local-first, on
  your own Spark, over your own artifacts, private by construction), not what's
  wrong elsewhere.

If the product genuinely began as a riff on something that exists, that origin
story stays private. The published piece describes what the product *is now*,
which — by the time it ships — looks like nothing but itself.

## The vision arc: where it came from, where it is

Readers love a build story, and this is the part the product article does that
a deep-dive doesn't. Tell the honest evolution:

- **The operator's vision** — the itch. What does a solo builder on a Spark
  actually need that nothing on the machine gave them yet? (For a cockpit: "I
  have forty artifacts and no single place to drive them.")
- **The MVP** — the first thin slice that proved the idea. Be specific about
  what it could and couldn't do. The MVP is allowed to be unglamorous; that
  contrast is what makes the production version land.
- **The production tool** — what it became, and the leap between them. This is
  where the metrics and the feature count do their work: "the MVP was one page;
  a day later it was fourteen surfaces over a real sidecar."

Keep the arc truthful. If a feature is still rough, say so plainly once — it
buys trust for everything else. Don't front-load the failure narrative, though
(another HF-card lesson): the arc moves toward what works.

## Selling the workflow without selling

The article markets a refined agentic-coding workflow and the tools behind it —
Claude Opus models, the Claude Code harness, the Spark, and the body of work
that made it possible. The way to do that credibly is to *show the receipts*,
not to adjective them:

- Let the **mined metrics** make the speed argument. "14 hours, 12,000 lines,
  125 tests, one machine" is more persuasive than "incredibly fast."
- Name the **models honestly**. If the build ran on Opus 4.7 and the daily
  driver is now 4.8, say exactly that — don't imply a split that didn't happen.
  The interesting story is the handoff: what 4.7 built, what 4.8 now drives.
- Credit the **substrate explicitly**. The product was buildable in a day
  *because* of what already existed: the `fieldkit` package (the product is
  largely a thin surface over its `harness`, `eval`, `notebook`, `nim`
  modules), and the AI Field Notes articles + artifacts that gave it real data
  to show. This is the leverage story — "I didn't build it from nothing, I
  built it on a year of compounding work" — and it's both true and more
  impressive than a from-scratch claim.
- Describe the **Claude Code harness** as a working surface, not a miracle:
  the caching that made 233M processed tokens cost what they cost, the
  subagent fan-out, the skills that encode repeatable work. Concrete beats
  breathless.

## Drift signals — stop and re-anchor if you write these

- "Introducing the revolutionary…" / "game-changing" / "supercharge" — hype
  without evidence. Replace with the specific thing it does.
- "In this article we'll explore how I built…" — that's a tutorial opening on a
  launch piece. Lead with the product.
- "Unlike other tools…" / "what the cloud can't do" — competitor punch. Cut.
- A wall of metrics with no interpretation — the numbers need one sentence each
  saying what they *mean* for the reader.
- A feature list with no benefits — "X has a command palette" is a fact;
  "hit ⌘K and you're chatting with the warm model without touching the mouse"
  is a benefit.

## Tone calibration

Confident, specific, first-person, generous with credit. The reader should
finish wanting to (a) try the product and (b) try the workflow that built it —
and should trust every number on the way there because each one was measured,
not asserted.
