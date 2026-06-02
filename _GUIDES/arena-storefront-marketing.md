<!-- Arena storefront marketing (orionfold.com) — Last updated: 2026-05-28 -->

# Arena storefront marketing — Orionfold Arena → orionfold.com (the MARKETER)

> Builder-authored handoff for the **storefront** surface. Sibling to
> `arena-distribution.md`. The operator points the Orionfold marketing repo at
> this file. The operator controls orionfold.com messaging, so this is
> **guidance to implement**, not a contract.
>
> Distribution pipeline: **this monorepo (BUILDER + PUBLISHER, on Spark) →
> orionfold.com (MARKETER).** orionfold.com is a separate, thin, **light-themed**
> static storefront that routes outward to the real hosts (GitHub / HF
> `Orionfold` / PyPI) with docs/preview on ainative.business; every product
> carries local/private/open badges + a "Sponsor this work" CTA.

## Positioning (on-thesis — lead with the local runnable app)

> **An operator cockpit you run on your own DGX Spark — your prompts,
> telemetry, and eval data never leave the box.**

Orionfold's spine is "runs on your own machine, your data never leaves it." So
the **primary** positioning everywhere is the **local runnable app**, never a
hosted SaaS.

- **Primary CTA** (mirrors fieldkit's):
  ```
  pip install fieldkit[arena]
  fieldkit arena up
  ```
  \+ a GitHub link (`manavsehgal/ai-field-notes`).
- **Secondary CTA**: "see a live preview" → `ainative.business/arena/`,
  explicitly framed as a *preview*, not the product.

## Card placement

A **Software-catalog card** (new "Apps" sub-category, or under "The Platform"
alongside fieldkit): poster image + name **Orionfold Arena** + one-liner +
**local / private / open / free** badges.

## Detail page — `orionfold.com/software/orionfold-arena/`

Mirror the existing `/software/fieldkit/` template:

- Hero one-liner + the local/private value prop.
- What-it-is: the six surfaces (cockpit · models browser · efficiency frontier ·
  compare · leaderboard · Lab), built on fieldkit and shipped by fieldkit — the
  flagship dogfood of the package.
- Install + run commands (the primary CTA above).
- **Screenshots of the dark cockpit** — models browser, efficiency frontier,
  side-by-side compare. (The dark cockpit appears **only in imagery**.)
- External links: PyPI (`fieldkit`), GitHub (`ai-field-notes`), docs/preview on
  ainative.business.
- The standard **Sponsor this work** tier block
  (Bronze / Silver / Gold / Platinum — $10 / $25 / $50 / $100).

## Visual

Light **poster style** for the page (match the Orionfold storefront); the dark
cockpit appears only inside screenshots/embeds. **Do NOT** re-skin the storefront
dark. **Do NOT** host the app or proxy a sidecar from orionfold.com.

## Launch ritual

A `/story/<arena-launch>/` building-in-public post (honest-numbers voice) is the
established announce pattern — pair it with the launch.

## Naming

Use **"Orionfold Arena"** consistently across the card, detail page, and story.
It scopes the product under the parent brand and resolves the **spark-arena.com**
collision (an active same-space DGX Spark LLM *leaderboard* — GitHub org
`spark-arena`, the `sparkrun` tool, an NVIDIA forums thread). Internal code
surfaces stay `arena` (module / CLI / DB / routes / CSS namespace) — not
user-facing.
