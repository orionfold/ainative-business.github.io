# Design system — Airtable-derived light theme (shared standard)

_Status: adopted 2026-06-06 (self-health dashboard; agency cockpit same day). Written to be **shared across peer projects** (agency, self-wealth, spark, …): copy this file into your `_SPECS/` or reference it; keep §3 semantic token names stable so components port between dashboards._

_Relayed into this repo 2026-06-06 via PR from the operator's agency cockpit (which mirrors this repo read-only — see `CLAUDE.md` "Status beacon"). System of record: self-health's copy; this copy is verbatim apart from this provenance note. Apply **incrementally to new operator-facing panes** — do not restyle the shipped Arena cockpit wholesale without an operator green-light (this repo's specs are green-lit before build)._

Operator directive (2026-06-06): research Airtable's design system, clone what's good, improvise for our use case, capture as a standard.

## 1. Provenance — what's cloned vs improvised

**Cloned from Airtable** (sources: Brandkit case study by V. Van Keuren; Blocks SDK style-system docs; `Airtable/blocks` GitHub source for exact palette hexes; Airtable visual-refresh + color-update announcements):

- **Token taxonomy**: Grid, Spacing, Elevation, Typography, Color — primitives first, then a **semantic theming layer**; naming synced across design ↔ code (their Brandkit discipline).
- **Spacing scale**: powers-of-two on a 4px base (`0, 4, 8, 16, 32…`), from the Blocks SDK style system.
- **Color palette**: the Blocks SDK named palette — 10 hues × 5 flavors (`light2, light1, mid, bright, dark1`), hex-verified from source (§2.1).
- **Accessibility stance** (their 2023+ visual refresh): status colors must keep readable text-on-color; distinct status pairs for color-vision deficiency; vibrant fills reserved for large areas, dark flavors for text.
- **Surface language**: white surfaces on a near-white canvas, hairline borders, low elevation, minimalist chrome ("reduce prominence of color in the data layer — color earns meaning").

**Improvised for our use case**:

- **Neutrals ramp** (§2.2) — the SDK gray scale (#eee/#ccc/#666/#444) is too sparse for a dense dashboard; we define a 7-step ramp.
- **Zero-egress substitutions** — no webfonts (Airtable's AT Aero → system stack §2.3), no icon font/CDN (heroicons inlined as SVG paths), all CSS/JS served same-origin. Binding for health data; recommended everywhere.
- **Attention semantics** (§4) — green/amber/red mapped to *monitoring* meaning (red/amber = act: logging pending or unhealthy reading), not just task status.
- **Bento grid** (§5.6) — measured-height row spanning; Airtable has no equivalent public pattern.

## 2. Primitives

### 2.1 Color palette (Airtable Blocks SDK, hex-verified)

Flavors per hue: `light2` (tint fills), `light1` (borders on tints), `mid` (chart fills, large graphics), `bright` (emphasis fills), `dark1` (text/icons on white or on the matching tint).

| hue | light2 | light1 | mid | bright | dark1 |
|---|---|---|---|---|---|
| blue | `#CFDFFF` | `#9CC7FF` | `#1283DA` | `#2D7FF9` | `#2750AE` |
| cyan | `#D0F0FD` | `#77D1F3` | `#01A9DB` | `#18BFFF` | `#0B76B7` |
| teal | `#C2F5E9` | `#72DDC3` | `#02AAA4` | `#20D9D2` | `#06A09B` |
| green | `#D1F7C4` | `#93E088` | `#11AF22` | `#20C933` | `#338A17` |
| yellow | `#FFEAB6` | `#FFD66E` | `#E08D00` | `#FCB400` | `#B87503` |
| orange | `#FEE2D5` | `#FFA981` | `#F7653B` | `#FF6F2C` | `#D74D26` |
| red | `#FFDCE5` | `#FF9EB7` | `#EF3061` | `#F82B60` | `#BA1E45` |
| pink | `#FFDAF6` | `#F99DE2` | `#E929BA` | `#FF08C2` | `#B2158B` |
| purple | `#EDE2FE` | `#CDB0FF` | `#7C39ED` | `#8B46FF` | `#6B1CB0` |
| gray | `#EEEEEE` | `#CCCCCC` | `#666666` | `#666666` | `#444444` |

Usage rule (Airtable's accessibility refresh, kept binding): **`mid`/`bright` never carry small text**; text and icons use `dark1` (or ink); tint chips pair `light2` background + `dark1` text (+ optional `light1` border).

### 2.2 Neutrals (improvised ramp)

| token | value | use |
|---|---|---|
| `canvas` | `#F7F8FA` | page background |
| `surface` | `#FFFFFF` | cards, header |
| `surface-2` | `#F2F4F7` | inset chips, input wells, bar tracks |
| `border` | `#E4E7EC` | card + table borders |
| `border-soft` | `#EEF0F4` | row separators, gridlines |
| `ink` | `#1D1F25` | primary text (Airtable's modern ink) |
| `ink-muted` | `#5C6470` | secondary text, labels |
| `ink-faint` | `#8A919C` | tertiary text, axis labels, placeholders |

### 2.3 Typography

- **Family**: `-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif` (zero-egress substitute for Airtable's AT Aero). `font-variant-numeric: tabular-nums` everywhere data renders.
- **Scale** (px): 10 (chip labels, axis), 11 (badges, legends), 12.5–13 (table body), 14 (base), 19 (stat values), 28 (headline stat). Weights: 400 body · 600 labels · 650 values · 700 emphasis.
- **Case**: section titles and chip labels are uppercase 10–12px with `.08–.14em` tracking.

### 2.4 Spacing, radius, elevation

- **Spacing**: 4px scale — `4, 8, 16, 32` (+ 12/14 grid gutters as the only sanctioned in-betweens for dense dashboards).
- **Radius**: 12px cards · 9px chips · 7px buttons · 5px pills/badges · 2px heat cells.
- **Elevation**: level 0 = border only; level 1 (cards) = `0 1px 2px rgba(29,31,37,.06)`; level 2 (sticky header, popovers) = `0 4px 16px rgba(29,31,37,.08)`. Never heavier — light themes read elevation from borders first, shadow second.

## 3. Semantic tokens (the portable contract)

CSS custom properties every peer dashboard should expose. Primitives (§2) may evolve; **these names should not**.

```css
:root {
  /* neutrals */
  --canvas / --surface / --surface-2 / --border / --border-soft
  --ink / --mute / --faint
  /* status (attention semantics, §4) — fill vs ink vs soft */
  --green: #11AF22;  --green-ink: #338A17;  --green-soft: #D1F7C4;
  --amber: #E08D00;  --amber-ink: #B87503;  --amber-soft: #FFEAB6;
  --red:   #EF3061;  --red-ink:   #BA1E45;  --red-soft:  #FFDCE5;
  /* data series (charts; not status-bearing) */
  --blue: #1283DA;   --blue-ink: #2750AE;   --blue-soft: #CFDFFF;
  --violet: #7C39ED; --violet-ink: #6B1CB0; --violet-soft: #EDE2FE;
  /* per-project accent (§6) */
  --accent / --accent-ink / --accent-soft
}
```

Rule of thumb: `--x` for SVG/chart fills and swatches · `--x-ink` for any text/icon · `--x-soft` for pill/badge/chip backgrounds (always paired with `--x-ink` text).

## 4. Status semantics

Traffic-light **attention** model (from the self-health header status bar, generalize as-is):

- **green** — healthy / complete / on-track. No action.
- **amber** — attention: partially logged, nearing a cap, fair-band reading, mildly stale sync.
- **red** — act now: logging missing, unhealthy reading (CO₂ poor-band, sleep short), dead poller, over cap.
- **off** — dashed border + faint text: future/disconnected surface (placeholder, not an alarm).

Color alone never carries the state: every status element also has a label or value, and a `title` tooltip with the reason + threshold.

## 5. Components

1. **Status bar** (sticky header) — two **labeled chip rows** with distinct jobs (decision 2026-06-06, operator):
   - **`goals` row** — _"how are we progressing?"_ — outcome telemetry: rollup (n/rated on-track) + one chip per top goal with its trend value (avg/day, days since, min/d × d/wk…).
   - **`monitors` row** — _"tracking? any alerts?"_ — pipeline health: one chip per data surface (wearable sync, air sensor, daily log, spend feed, weigh-in recency, future surfaces as `off`).
   - Row label: 10px uppercase muted + 9.5px faint caption stating the row's question. Keep the two reds apart — a monitors-red means "data missing/unhealthy reading", never "losing the goal".
   - **Chip anatomy** (consistent RAG, decision 2026-06-06): white surface, 9px radius, 17px heroicon (inline SVG, `stroke="currentColor"`). Three text tiers — **label** 10px uppercase, always neutral gray (titles never carry state, including the page wordmark); **value** 13px bold, always in the state's `-ink` color (green included — value is where status lives); optional **sub** 9.5px faint = actual/trend context ("+/− vs base · cap n", "n/7d ≥20 min", "since 06/02"). Border `light1` of the state hue; `off` = dashed + faint. `title` tooltip carries reason + threshold.
   - **Headline stat** (brand block) follows the same anatomy writ large: neutral wordmark, 28px value colored by its goal's RAG status, trend subtext below (Δ over 7d, green/red by direction).
2. **Card**: surface + border + level-1 shadow, 12px radius, 14–16px padding; title = 12px uppercase muted with optional right-aligned `sub`.
3. **Pill / badge**: `--x-soft` background + `--x-ink` text, 5px radius, 10–11px bold.
4. **Table**: 11px uppercase muted headers, `border-soft` row separators, hover = `--surface-2`, right-aligned numerics.
5. **Charts (inline SVG)**: gridlines `border-soft`; axis text 10px `--faint`; series fills from §3 (`--x` flavors, .85 opacity bars); reference lines dashed (`cap` red / `floor` amber / `goal` green / `pace` amber); empty days render gaps or `·` markers — **never zero**.
   - **Interactive tooltips** (decision 2026-06-06, operator — replaces native `<title>`): every datum element carries a `data-tip` attribute; one **shared fixed-position tooltip singleton** per page follows the cursor via delegated `mousemove` (`closest("[data-tip]")` — works on SVG nodes), flips at viewport edges, `pointer-events: none`.
   - **Tooltip surface**: `--surface` + `--border`, 7px radius, **level-2 elevation** (popover tier, §2.4), 11.5px ink text, max-width 260px; first line = 10px uppercase muted head (usually the date), following lines = tabular-num metric rows (value · threshold · provenance, e.g. "source: BMR estimate (ring dark)").
   - **Hover affordance**: hovered datum goes full opacity + 0.9px ink stroke (paths thicken instead).
   - **No HTML round-trips** (security review 2026-06-06): tooltip content travels as plain values in `data-tip-head` / `data-tip-lines` (JSON array) attributes and is rendered **only via `textContent` + `replaceChildren`** — never `innerHTML`. Escaping an HTML string into an attribute is NOT protection: `getAttribute` decodes it right back.
6. **Bento grid — content-aware bin packing** (decision 2026-06-06, operator: "no structural whitespace"): 12-col, 10px auto-rows + dense flow; single-column under 1100px. The packer runs after every render/resize:
   - **Measure** each card's natural content height (span set to `auto`, read `scrollHeight`).
   - **Pair** half-width cards by height similarity with a small lookahead (≈4) over the remaining pool — similar-height neighbors minimize internal stretch while roughly preserving panel priority order; the DOM is reordered to the chosen pairing.
   - **Equalize** each pair's row span to the taller card — both cards stretch to the same track height (e.g. bloodwork grows to match medications), so every grid row is fully spanned edge to edge.
   - **Promote** an odd card out to a full-width row (re-measured at 12-col width) instead of leaving a half-row hole.
   - Full-width anchor cards (hero tables, timelines) are never paired; they size from their own content.
7. **Empty/degraded states**: italic faint `no data — <reason>`; degraded sections enumerated in the footer.

## 6. Theming for peer projects

Keep neutrals + status tokens identical; differentiate by **accent** (used for brand/wordmark, active toggles, focus rings — never for status):

| project | accent | accent-ink | accent-soft |
|---|---|---|---|
| self-health | teal `#02AAA4` | `#06A09B` | `#C2F5E9` |
| self-wealth (suggested) | blue `#1283DA` | `#2750AE` | `#CFDFFF` |
| agency (suggested) | purple `#7C39ED` | `#6B1CB0` | `#EDE2FE` |

## 7. Adoption checklist

- [ ] `:root` exposes §3 token names; no raw hexes outside the token block (charts may read tokens via `var()`).
- [ ] No webfont / icon-font / CDN fetch — system stack + inline SVG only (egress-free).
- [ ] Small text never sits on `mid`/`bright` fills; pills use `soft` + `ink` pairs.
- [ ] Status colors always accompanied by text + tooltip reason.
- [ ] Empty data renders as absence (`n/a`, gap), never as fabricated zero.
- [ ] `color-scheme: light` set; tabular numerals on all data surfaces.

## Appendix — research notes (2026-06-06)

- Airtable's internal system "Brandkit": atomic-design organization (24 atoms / molecules / 92 organisms / 5 templates), federated contribution, tokens as the foundation layer. Public case study; no public token values.
- Blocks SDK style system: powers-of-two 4px spacing; named palette with `ColorUtils.getHexForColor`; hexes extracted from `Airtable/blocks` `packages/sdk/src/colors.ts` (MIT-licensed source) — §2.1 table.
- 2023+ visual refresh: contrast-driven color update ("many colors were inaccessible with text on top"), status-indicator distinction, cleaner minimalist base UI.
- AT Aero (their 2023 custom typeface) is not redistributable → system stack substitution recorded in §2.3.
