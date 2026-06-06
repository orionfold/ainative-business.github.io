---
name: status-beacon
description: Maintain `_STATUS.json` — the Agency cockpit status beacon at the repo root. The operator's Agency cockpit (another desktop) mirrors this repo read-only and renders the beacon in preference to parsing HANDOFF.md. Use at session end (alongside the HANDOFF update) to refresh the beacon, and whenever the user says "update the beacon", "refresh _STATUS.json", "update the status beacon", "the beacon is stale", or "force a beacon SEO refresh". Cheap project counts (articles, fieldkit_modules) recompute every run for free; manual counts (models, software_released, arena_features) carry forward and are bumped at ship time; the expensive GSC/GA4 numbers are TTL-gated (default 7 days) so the several-commits-per-hour cadence isn't slowed by a browser scrape. Do NOT use for the full SEO audit (that's seo-monitor) or for HANDOFF.md.
---

# status-beacon

Keeps `_STATUS.json` (repo root) current for the **Agency cockpit** — a separate
desktop that mirrors this repo read-only and renders the beacon instead of
parsing `HANDOFF.md`. The contract lives in `CLAUDE.md` ("Status beacon (Agency
cockpit)"); this skill is the *mechanics* of refreshing it without slowing the
build cadence.

## The core idea — three metric tiers, three costs

The beacon's `metrics` block mixes cheap and expensive numbers. Treating them
uniformly (re-reading everything every session) was the productivity trap: a
~40-90s browser scrape on every one of several-commits-per-hour. So the tiers are
gated separately by `scripts/update_beacon.mjs`:

| Tier | Metrics | Cost | Cadence |
|---|---|---|---|
| **Cheap** | `articles`, `fieldkit_modules` | local file reads, ~free | recomputed **every run** (these drift silently) |
| **Manual** | `models`, `software_released`, `arena_features` | none — "counts only this project knows" | **carried forward**; bump by hand when one ships |
| **Expensive** | `gsc_indexed`, `gsc_submitted`, `ga4_users_7d` | ~40-90s CDP browser scrape | **TTL-gated** (default **7d** off `checked`) |

`checked` (ISO date the GSC/GA4 numbers were actually read) is the TTL clock —
and it's the same field the cockpit renders a `>14d` staleness warning from. A
7-day TTL keeps the beacon well inside that warning while scraping at most
~once/week.

## When to run

- **Every session end**, right after the HANDOFF update, before the session's
  push. The beacon "churns once per session, like HANDOFF.md" (per the contract).
- On demand when the user asks to refresh it or force a SEO re-read.

## Procedure

1. **Edit the narrative fields** in `_STATUS.json` for this session — these are
   yours to write, the script preserves them:
   - `focus` — one line: what this session moved.
   - `health` — `green` | `yellow` | `red`.
   - `blockers` / `next` / `recent` — ≤5 short factual items each.
   - `session` — a short tag.
2. **Run the assembler** (recomputes cheap metrics, TTL-gates the SEO scrape,
   bumps `updated`, preserves everything else):
   ```bash
   node .claude/skills/status-beacon/scripts/update_beacon.mjs
   ```
   - Add `--force` to scrape GSC/GA4 now regardless of TTL (e.g. right after a
     deploy, or when the user explicitly wants fresh SEO data).
   - Add `--no-scrape` to refresh only the cheap/manual tiers (never touch the
     browser) — the fast path for a routine mid-day commit.
   - `--ttl <days>` overrides the 7-day default; `--cdp-port <n>` the scraper port.
3. **Bump a manual count** if this session shipped one — e.g. a new published
   model → edit `metrics.models`; a new fieldkit/software release → `software_released`;
   a new shipped arena feature → `arena_features`. (The script carries these
   forward; it does not invent them.)
4. **Commit** `_STATUS.json` with the session's push.

## What the SEO scrape does (and its prerequisite)

The TTL-gated scrape runs `.claude/skills/seo-monitor/scripts/scrape_cdp_fallback.mjs`,
which attaches over CDP (default `:9222`) to a **Google-logged-in Chromium** (e.g.
the Arena browser-use Chromium) and read-only-reads: GSC indexed pages, the
sitemap's submitted/discovered URL count, and GA4 7-day active users. It NEVER
clicks a mutation button ("Request indexing", "Resubmit sitemap").

If no logged-in CDP browser is reachable when a scrape is **due**, the script
carries the old SEO numbers forward, leaves `checked` unchanged, and prints a
`DUE … unavailable` note — it does **not** block the commit or fabricate a value.
To get fresh numbers the operator signs the CDP Chromium into the Google account
that owns `sc-domain:ainative.business`, then re-runs with `--force`. (The full
SEO audit — fixes, diffs, reports — is the separate `seo-monitor` skill, which
prefers the `claude-in-chrome` MCP; this beacon path is the lighter CDP read.)

## Non-negotiables

- **Never fabricate a metric.** Cheap = derived, manual = carried, expensive =
  scraped-or-carried. A number with no real source is carried forward, never invented.
- **Never bump `checked` without a real GSC/GA4 read.** It is the staleness clock.
- **Never block a commit on the scrape.** Browser down/logged-out → carry forward.
- **Narrative fields are author-written.** The script preserves `focus`/`recent`/
  `next`/`health`/`session`/`blockers`; it never auto-writes them.
- **Don't scrape on every commit.** The TTL exists precisely to keep the cadence
  free; only `--force` overrides it.
