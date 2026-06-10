# Orionfold brand alignment — marketing-site design language (v1)

_Status: applied 2026-06-10 (operator-directed). Scope: the **ainative.business marketing
site** (everything rendered from `src/`). The **Arena cockpit (`arena-app/`) is explicitly
out of scope** — it keeps the Airtable-derived operator-pane standard
(`_SPECS/design-system-v1.md`), which remains the shared standard for operator surfaces
across peer projects._

## 1. Why

ainative.business had diverged after the Airtable-themed design language was applied
site-wide. The Airtable system is right for dense operator UI (Arena), but the public
site should read as a natural extension of the **orionfold.com parent brand**, which
went through its own IA + design-language redesign. This spec records the realignment
so future surfaces follow it.

Reference: live orionfold.com (fetched 2026-06-10; tokens extracted from its built
Tailwind v4 theme). The two sites already shared structure (nav idiom, blur-orb
atmosphere, Geist fonts) — the divergence was almost entirely the token layer plus
the card treatment.

## 2. Token system (source of truth: `src/styles/global.css` `@theme`)

| token | value | orionfold provenance |
|---|---|---|
| `--color-surface` | `oklch(98% 0.005 260)` | canvas (cool near-white) |
| `--color-surface-raised` | `#FFFFFF` | cards, header |
| `--color-surface-overlay` | `oklch(96.5% 0.008 260)` | wells, chips |
| `--color-text` | `oklch(15% 0.02 260)` | ink |
| `--color-text-muted` | `oklch(45% 0.03 260)` | secondary |
| `--color-text-dim` | `oklch(56% 0.025 260)` | tertiary (kept as a 3rd tier; orionfold has 2) |
| `--color-primary` | `oklch(55% 0.18 260)` | indigo primary |
| `--color-primary-dim` | `oklch(55% 0.18 260 / 0.10)` | pill/chip fills |
| `--color-primary-glow` | `oklch(55% 0.18 260 / 0.20)` | glows, selection |
| `--color-orbit-gold` | `oklch(70% 0.14 82)` | gold accent (NEW) |
| `--color-orbit-ink` | `oklch(27% 0.06 260)` | deep navy (NEW) |
| `--color-success` | `oklch(45% 0.15 170)` | success |
| `--color-border` | `oklch(80% 0.02 260 / 0.25)` | hairlines (translucent) |

Fonts unchanged (already shared with orionfold): Geist Sans body/display, Geist Mono.

**Hero gradient text**: `linear-gradient(135deg, #003356, #1952af, oklch(59% 0.13 82))`
— orionfold's navy → royal blue → gold ramp (verbatim).

**SVG semantic tokens**: neutrals moved to the cool 260 hue; categorical diagram
accents re-tuned — `--svg-accent-blue` is now the brand indigo `oklch(50% 0.16 260)`,
`--svg-accent-orange` is the orbit gold `oklch(62% 0.13 82)` (text-safe darkening of
70%), the rest cooled to match (see `@theme` block). All signature components and
fn-diagrams re-skin through these vars; no per-diagram edits needed.

## 3. Card idiom — `.of-surface` / `.of-pressable`

Ported from orionfold.com into `global.css`:

- `.of-surface` — primary-tinted hairline border (`color-mix` border 76% / primary 24%),
  soft vertical sheen over white, long low shadow + inset top highlight, corner glow
  washes (indigo top-left, gold top-right), faint dot-grid texture.
- `.of-pressable` — hover: border toward primary, `translateY(-2px)`, primary-tinted bg,
  primary shadow. Reduced-motion safe.

Applied to the home-page marketing cards (teaser preview frames, field-notes rail,
progress/research/problem stat cards, proof container). Primary-tinted callout cards
(`border-primary/15 bg-primary/[0.04]`) and the book figure with its `border-l` accent
keep their bespoke treatment. BEM-styled hubs (artifacts catalog, field-notes index,
products) re-skin via tokens alone — adopt `.of-surface` opportunistically when touching
those surfaces.

Atmosphere: hero gained orionfold's right-side gold orb
(`bg-[oklch(0.70_0.14_82/0.10)] blur-[120px]`) beside the indigo orbs.

## 4. Hardcoded-color policy

No raw Airtable-palette hexes outside `arena-app/`. The field-notes series badges'
"dark1" hexes were replaced with `var(--svg-accent-*)` (darkened via `color-mix`
where the accent is too light for small text). `verify_svg.sh` invariant 12 keeps
hexes out of signature/fn-diagram SVGs.

## 5. What stays Airtable (out of scope)

- `arena-app/` (cockpit UI) and the baked `public/arena/demo/` bundle.
- `_SPECS/design-system-v1.md` itself — still the operator-pane standard; do not edit
  its body (it is a verbatim shared copy; system of record is self-health's).

## 6. IA posture

Unchanged this pass: ainative.business = knowledge/book/field-notes surface;
orionfold.com = gateway/marketplace ([[project_orionfold_consolidation]]). The nav
already mirrors orionfold's idiom (mono uppercase links, two-tone wordmark,
"Made by Orionfold ↗"). Future IA moves should keep nav taxonomy parallel to
orionfold's (Advisor / Workflows / Experts / Cockpit / Learn / Adoption) where the
two sites cross-link.
