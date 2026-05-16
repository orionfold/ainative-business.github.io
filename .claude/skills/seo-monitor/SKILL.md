---
name: seo-monitor
description: Audit and monitor SEO health for ainative.business by scraping Google Search Console, Google Analytics 4, and PageSpeed Insights via the claude-in-chrome browser, diffing against the prior snapshot, proposing code-level fixes against the Astro site, and writing a timestamped entry to ./seo-progress.md plus a per-snapshot archive at ./seo/YYYY-MM-DD-HHMM.md. Use whenever the user says "/seo-monitor", "check seo", "seo audit", "seo check", "search console", "indexing issues", "google analytics seo", "page speed", "core web vitals", "seo progress", "monthly seo", "site indexing", "crawl errors", "sitemap status", "lighthouse audit", or any request to inspect organic-search health, indexing coverage, query performance, organic landing-page traffic, or Web Vitals for the ainative.business marketing site.
---

This skill watches the ainative.business marketing site's organic-search health over time. It scrapes three sources — **Google Search Console** (indexing, queries, sitemap status), **Google Analytics 4** (organic landing-page traction), and **PageSpeed Insights** (Core Web Vitals + Lighthouse scores) — joins those signals with a local audit of the built Astro site, and writes a timestamped snapshot to `./seo-progress.md` at repo root plus an archive at `./seo/YYYY-MM-DD-HHMM.md`.

The leverage of the skill is not the scraping itself; it is the **join**. A URL that GSC flags as "Crawled — not indexed" *and* is missing a meta description is a high-confidence fix. A landing page from GA with low engagement *and* a too-long title is a fix candidate. Two consecutive runs that surface the same issue mark it `stale` so you can decide between repairing it or removing it.

The skill is **on-demand only** — invoke via `/seo-monitor` or any of the trigger phrases above. It is not part of `apply-product-release` and does not run on a schedule.

## Source URLs and prerequisites

| Source | URL | Auth |
|--------|-----|------|
| Google Search Console | `https://search.google.com/search-console?resource_id=sc-domain%3Aainative.business` | Requires signed-in Google account that owns `sc-domain:ainative.business` |
| Google Analytics 4 | `https://analytics.google.com/analytics/web/#/a391868719p533699836/reports/intelligenthome` | Same Google account |
| PageSpeed Insights v5 REST | `https://www.googleapis.com/pagespeedonline/v5/runPagespeed?url=…&strategy=…` | None — public API, ~1qps unauthenticated |

**Chrome must already be signed into Google before invocation.** This skill does not attempt re-authentication; if the session is expired it halts with a copy-pasteable sign-in instruction.

The three reference playbooks document the exact URLs, network endpoints, and SPA quirks per source. Read them before/during the matching Plan Phase step:

- `references/gsc-playbook.md` — GSC report URLs, `/searchanalytics/query` network shape, fallback selectors
- `references/ga-playbook.md` — GA4 SPA gotchas, `analyticsdata.googleapis.com/.../runReport` shape, the "wait for a data cell" trick
- `references/pagespeed-playbook.md` — PSI v5 REST parameters, rate-limit handling, Lighthouse JSON interpretation

The fix taxonomy lives in `references/fix-taxonomy.md`: every audit check, the file glob it touches, the repair recipe, and whether it's `auto` (code edit) or `console` (user clicks in Google's UI).

## Workflow

One phase → one gate → in place. There is no orchestrator coupling. Plan Phase scrapes, audits, diffs, and emits a proposed-fixes block. After one OK from the user, Execute Phase applies the `auto` fixes, runs `npm run build`, writes the snapshot to `seo-progress.md`, archives the run, and surfaces the `console` fixes as a checklist for the user to perform manually in GSC/GA.

## Plan Phase

### 1. Verify browser session

Load the claude-in-chrome tool schemas before first use:

```
ToolSearch query: select:mcp__claude-in-chrome__tabs_context_mcp,mcp__claude-in-chrome__tabs_create_mcp,mcp__claude-in-chrome__navigate,mcp__claude-in-chrome__read_page,mcp__claude-in-chrome__read_network_requests,mcp__claude-in-chrome__get_page_text,mcp__claude-in-chrome__take_screenshot,mcp__claude-in-chrome__javascript_tool
```

Call `mcp__claude-in-chrome__tabs_context_mcp` to confirm Chrome is reachable. If the tool errors or returns no tabs, inform the user: *"claude-in-chrome is not connected. SEO monitor requires a running Chrome session signed into Google. Connect chrome (or restart it) and re-run /seo-monitor."* and halt.

If connected, create three tabs in parallel via `tabs_create_mcp`:
1. GSC: the URL in the prerequisites table
2. GA4: the URL in the prerequisites table
3. PSI: `https://pagespeed.web.dev/` (kept open for fallback UI scrape; the REST API is primary)

Then for the GSC and GA4 tabs:
- `read_page(tab_id)` — read the accessibility tree
- **Login probe:** if the URL contains `accounts.google.com/signin` or the page text matches `Sign in` / `Sign in to continue` / `Choose an account`, halt with:

  *"You need to sign into Google before /seo-monitor can run. Open Chrome, sign in with the account that owns sc-domain:ainative.business, then re-run."*

  Emit a minimal `Status: login-required` plan block and stop. Do **not** attempt to drive the login.

### 2. GSC Performance scrape (28-day window)

Navigate the GSC tab to:
```
https://search.google.com/search-console/performance/search-analytics?resource_id=sc-domain%3Aainative.business&num_of_days=28
```

Wait for the report to render. Then **prefer the network capture path**: `read_network_requests(tab_id)` and filter for requests whose URL contains `/searchanalytics/query`. The response is clean JSON with rows of dimensions (query / page / country / device) and metrics (clicks, impressions, ctr, position).

If the network capture is unavailable, fall back to `get_page_text(tab_id)` and parse the rendered table. The GSC fallback selector reference is in `references/gsc-playbook.md`.

Extract:
- 28-day totals: clicks, impressions, average CTR, average position
- Top 25 queries with per-query clicks/impressions/CTR/position
- Top 25 pages (the destinations from search) with per-page clicks/impressions/CTR/position

### 3. GSC Indexing & Coverage

Navigate the GSC tab to:
```
https://search.google.com/search-console/index/coverage?resource_id=sc-domain%3Aainative.business
```

Extract:
- Count of "Indexed" pages
- Count of "Not indexed" pages, broken down by reason — the typical categories are: `Crawled — currently not indexed`, `Discovered — currently not indexed`, `Page with redirect`, `Duplicate without user-selected canonical`, `Soft 404`, `Page is not indexed because it's blocked by noindex`, `Excluded by 'noindex' tag`, `Not found (404)`
- For each non-zero reason, capture up to 10 example URLs by drilling in

The user's memory notes: "Page with redirect" is expected for the stagent.io → ainative.business migration; we surface its count but do not treat it as a problem unless it grows.

### 4. GSC Sitemaps & Enhancements

Navigate to:
```
https://search.google.com/search-console/sitemaps?resource_id=sc-domain%3Aainative.business
```

Extract per sitemap: submitted-on date, last-read date, type, status (Success / Has errors / Couldn't fetch), discovered URLs count.

Then check `…/enhancement/structured-data-articles` (and any other enhancement reports that exist). Extract warning and error counts. These usually map to JSON-LD issues the local audit (Step 7) can pinpoint.

### 5. GA4 Acquisition & Landing pages

Navigate the GA tab to the acquisition report. GA4 is a fragile SPA — use this sequence:

1. `navigate(tab_id, "<base GA URL>/_/AcquisitionTrafficAcquisition")`
2. Wait for a data cell to render. The reliable wait predicate is text content (a dollar sign, percent, or session count) inside a `[role="cell"]` element — see `references/ga-playbook.md` for selectors. If `wait_for` with that predicate times out at 15s, retry once with a 10s additional wait.
3. **Prefer the network capture path:** `read_network_requests(tab_id)` and filter for requests whose URL contains `analyticsdata.googleapis.com/v1beta/properties/` and `:runReport` or `:batchRunReports`. The response is clean JSON.
4. If the network capture is unavailable, fall back to `get_page_text(tab_id)` and parse the data grid.

Repeat for the landing-page report. Filter (or post-filter) to "Organic Search" source.

Extract:
- 28-day organic: sessions, users, engagement rate, avg engagement time per session
- Top 25 landing pages from organic search: sessions, engagement rate, conversions

If GA4 returns an empty grid after both attempts, mark the GA section `partial`, omit GA from the cross-reference join in Step 8, and continue.

### 6. PageSpeed audit (no auth)

Use the PSI v5 REST API rather than scraping the UI. From any tab, run:

```js
javascript_tool(tab_id, `(async () => {
  const u = 'https://www.googleapis.com/pagespeedonline/v5/runPagespeed' +
    '?url=' + encodeURIComponent('https://ainative.business/') +
    '&strategy=mobile' +
    '&category=performance&category=seo&category=accessibility&category=best-practices';
  const r = await fetch(u);
  return await r.json();
})()`)
```

Run for both `strategy=mobile` and `strategy=desktop` on these 5 priority URLs:
1. `https://ainative.business/`
2. `https://ainative.business/field-notes/`
3. `https://ainative.business/book/`
4. `https://ainative.business/docs/`
5. `https://ainative.business/projects/`

That's 10 calls total. PSI rate-limits unauth at ~1qps — pace calls with `await new Promise(r => setTimeout(r, 1100))` between them, or run sequentially. If a call times out or returns 429, retry up to 2× with 5s backoff. If still failing, fall back to scraping `https://pagespeed.web.dev/analysis?url=…` UI in the PSI tab for the home URL only; mark per-page audits `skipped`.

Extract per audit:
- Core Web Vitals: LCP (s), INP (ms), CLS (unitless)
- Lighthouse scores: Performance, SEO, Accessibility, Best Practices (each out of 100)
- Top 5 failed audit IDs (e.g., `unused-javascript`, `largest-contentful-paint-element`) with their per-audit score

### 7. Local site audit

Run the bundled audit script against the built site:

```bash
# Build dist/ only if it's older than 24h or missing
test -d dist && find dist -maxdepth 0 -mtime -1 | grep -q . || npm run build

# Then audit
node .claude/skills/seo-monitor/scripts/audit_site.mjs > /tmp/seo-audit.json
```

The script walks `dist/**/*.html` and checks the 14 audit rules listed in `references/fix-taxonomy.md`. Output is JSON: `{ "checks": [{ "id": "missing-meta-description", "page": "/docs/foo/", "file": "src/pages/docs/foo.mdx", "severity": "warn", "class": "auto|console", "fix": "<recipe>" }, ...] }`.

### 8. Cross-reference

Build a ranked list of fixes by **joining** the four sources:

| Join | Confidence | Example |
|------|-----------|---------|
| GSC "Crawled — not indexed" page ∩ local audit "missing meta description" | high | propose adding description |
| GSC "Discovered — not indexed" ∩ local audit "missing OG image" | medium | propose OG image |
| GA low engagement (<20%) ∩ local audit "title length out of range" | medium | propose title rewrite (surfaced, not auto-applied) |
| PSI poor LCP ∩ local audit "unoptimized hero image" | high | propose `loading="eager"` + dimensions |
| Local-audit issue only (no GSC/GA signal) | low | still surface, but rank below joined fixes |

Cross-reference logic lives in `references/fix-taxonomy.md` (the "join recipe" column). Fixes get split into the `auto` list (this skill will edit code on user approval) and the `console` list (user must click in GSC/GA UI).

### 9. Diff against snapshot cache

Read `references/snapshot-cache.json` (the prior run's raw extract). If missing, this is a first-run — all deltas show as `—` and no stale flag fires.

Run the diff script:

```bash
node .claude/skills/seo-monitor/scripts/diff_snapshot.mjs \
  --prior .claude/skills/seo-monitor/references/snapshot-cache.json \
  --current /tmp/seo-current.json \
  > /tmp/seo-diff.json
```

The diff script emits per-metric deltas with direction arrows ("good direction" awareness — LCP ↓ is better, clicks ↑ is better).

Dedup proposed fixes against `references/issue-history.md`. Issues with the same `<file>:<issue-id>` key in 2+ consecutive runs get flagged `stale`. After 3 runs, flag `manual-review-needed`.

Emit the Plan Output Format below and **halt for one OK**.

## Plan Output Format

Emit this block at the end of Plan Phase. Do not write any files yet.

```markdown
### seo-monitor
- **Status**: changed | no-changes | error | login-required
- **Snapshot window**: 2026-04-18 → 2026-05-16 (28 days)
- **Summary**: Clicks 1,240 (↑ +180) · Impressions 48k (↑ +6k) · Indexed 312/383 (↑ +4) · Mobile LCP 2.4s (↓ 0.3s)

#### KPI deltas vs prior snapshot
| Source | Metric | Prior | Current | Δ |
|--------|--------|-------|---------|---|
| GSC | Total clicks (28d) | 1,060 | 1,240 | ↑ +180 |
| GSC | Avg position | 18.2 | 16.9 | ↓ 1.3 (better) |
| GSC | Indexed pages | 308 | 312 | ↑ +4 |
| GSC | Discovered — not indexed | 41 | 38 | ↓ −3 |
| GA  | Organic sessions | 740 | 905 | ↑ +165 |
| GA  | Organic engagement rate | 48% | 52% | ↑ +4pp |
| PSI | Home mobile LCP (s) | 2.7 | 2.4 | ↓ −0.3 (better) |
| PSI | Home mobile SEO score | 92 | 100 | ↑ +8 |

#### Top movers
- Query "ai native business" — position 12 → 6 (↑ +22 clicks)
- Page /field-notes/kv-cache/ — sessions 18 → 84
- Page /book/chapter-3/ — clicks 0 → 12 (newly indexed)

#### Proposed code fixes (auto, this skill will apply on approval)
| # | File | Issue | Fix |
|---|------|-------|-----|
| 1 | src/pages/field-notes/kv-cache.mdx | OG image missing | set `ogImage: /og/kv-cache.png` |
| 2 | astro.config.mjs:55-80 | sitemap priority drift for /fieldkit/ | bump priority in serialize() |
| 3 | src/data/timeline.ts:142 | internal href missing trailing slash | add `/` |

#### Proposed console fixes (user, manual in GSC/GA UI)
| # | Action | Where | Reason |
|---|--------|-------|--------|
| 1 | Resubmit sitemap | GSC › Sitemaps | last-read 14 days ago, 12 new URLs |
| 2 | Request indexing /field-notes/agentic-coding/ | GSC › URL Inspection | crawled-not-indexed 21 days |
| 3 | Add meta description to docs/delivery-channels.mdx | manual MDX edit | safer to author than auto-derive |

#### Stale issues (persist 2+ runs)
- src/pages/docs/provider-runtimes.mdx — missing meta description (3rd run, flagged manual-review-needed)

#### Risks
- audit_site.mjs depends on a recent `dist/`; rebuild adds ~25s if stale
- GA SPA returned partial data on this run — engagement rate metric trusted, conversions skipped
```

**Gate question:** *"OK to apply the N auto fixes? The K console fixes will be re-listed in the final report for you to perform manually."*

If the user says no, end gracefully — do not write any files, do not update the snapshot cache.

## Execute Phase

### 10. Apply auto fixes in order

Iterate the auto-fixes table. For each:

1. `Read` the target file.
2. `Edit` with the specific repair from `references/fix-taxonomy.md`.
3. If the file's structure doesn't match what the recipe expects (e.g., a `description:` slot doesn't exist because the file uses a different layout), abort *that fix only*, log to `skipped` with a one-line reason, and continue with the next.

One edit per file per fix — no batched edits — so a single failure doesn't roll back unrelated changes.

**Never auto-derive meta descriptions from page content.** The user's memory and the design decision behind this skill is that descriptions are author-quality content; auto-derivation produces awkward output that costs more to revert than to write fresh. A "missing meta description" issue is always emitted as a `console` (manual) fix, never an `auto` fix.

### 11. Build verification

```bash
cd /Users/manavsehgal/Developer/ainative-business.github.io && npm run build 2>&1 | tail -30
```

Capture the last 30 lines of output. The build must complete without errors and produce a similar page count (±5) to the prior run.

**If the build fails, halt before any further state changes.** Do not write `seo-progress.md`, do not update the snapshot cache. Report the error and which fix (the last `Edit` before the build) is the likely culprit. Leave the partial edits in place so the user can inspect and decide whether to revert.

### 12. Update snapshot cache

Write `references/snapshot-cache.json` with the full raw extract from Steps 2–7 (GSC, GA, PSI, local audit results). Overwrite — the cache holds only the latest snapshot.

### 13. Append to `./seo-progress.md`

Run the render script:

```bash
node .claude/skills/seo-monitor/scripts/render_progress.mjs \
  --current /tmp/seo-current.json \
  --diff /tmp/seo-diff.json \
  --applied /tmp/seo-applied.json \
  --progress ./seo-progress.md
```

The script's idempotence rule: if the most-recent entry in `seo-progress.md` has the same `YYYY-MM-DD` date as today, it **replaces** that entry rather than appending a second one. Same-day re-runs reflect the latest state, not a noisy chain. (The per-snapshot archive in Step 14 always gets a new file since its timestamp differs.)

If `seo-progress.md` doesn't exist, the script copies `assets/progress-template.md` as the skeleton and inserts the first entry.

### 14. Write per-snapshot archive

Write `./seo/YYYY-MM-DD-HHMM.md` containing:
1. The full Plan Output block (from Step 9)
2. The applied/skipped fix log (from Step 10)
3. The build result (from Step 11) — last 30 lines on success, full error on failure

Create `./seo/` if it doesn't exist. The archive is always a new file.

### 15. Update issue history

Append an entry to `references/issue-history.md` for every `<file>:<issue-id>` key seen in this run's proposed-fixes list (before user approval — even skipped/declined fixes count toward the stale flag). Format:

```markdown
| YYYY-MM-DD | <file>:<issue-id> | <auto|console> | <new|stale|manual-review-needed> |
```

### 16. Emit completion report

Print to the user:

```
seo-monitor — snapshot YYYY-MM-DD HH:MM

  Applied:  N auto fixes
  Skipped:  K  (see archive for reasons)
  Build:    ✓ XX.Xs   |   ✗ <error>
  Snapshot: ./seo-progress.md  (most recent at top)
  Archive:  ./seo/YYYY-MM-DD-HHMM.md

  Console actions for you to perform:
    [ ] Resubmit sitemap (GSC › Sitemaps)
    [ ] Request indexing /field-notes/agentic-coding/ (GSC › URL Inspection)
    [ ] Add meta description to src/pages/docs/delivery-channels.mdx (manual)

  Suggested commit:
    seo: monitor snapshot YYYY-MM-DD — N auto fixes (clicks +X, indexed +Y)
```

Do not auto-commit. The user controls commit timing.

## Failure Modes

| Condition | Behavior |
|-----------|----------|
| `claude-in-chrome` MCP not connected | Halt at Step 1 with message and `Status: error`. No files written. |
| User not signed into Google in Chrome | Halt at Step 1. `Status: login-required`. Copy-paste instruction emitted. No files written. |
| GA4 returns empty grid after 2 attempts | Mark GA section `partial`. Omit GA from cross-reference join (Step 8). Continue. Note in the snapshot. |
| PSI 429 / timeout | Retry each URL up to 2× with 5s backoff. If still failing, fall back to UI scrape for home only; mark per-page audits `skipped`. |
| Auto-fix can't apply (file structure unexpected) | Log under `skipped` with one-line reason, continue. Same issue stale after 2 runs → flagged `manual-review-needed`. |
| Two runs same day | Step 13 *replaces* today's entry in `seo-progress.md`. Archive always appends (timestamp differs). Snapshot cache overwritten. |
| Build fails after auto fixes | Halt before Steps 12–14. Leave edits in place. Surface error and last-edit pointer. User decides whether to revert. |

## Key Rules

- **Never auto-commit.** Suggest a commit message at the end; the user owns commit timing.
- **Never attempt to re-authenticate.** If signed out, halt with sign-in instruction.
- **Never click in modal dialogs / consent banners.** The system prompt warns these block MCP control. If a dialog appears, take a screenshot, ask the user to dismiss manually, and re-run.
- **Trailing slashes mandatory.** Any auto-fix that emits or rewrites an internal `<a href>` must include the trailing slash to avoid GitHub Pages 301 redirects (per the project's `trailingSlash: 'always'` Astro config and the user's memory).
- **Meta descriptions are authored, never derived.** Always a `console` (manual) fix.
- **Idempotence.** Two runs on the same day produce one entry in `seo-progress.md` (replaced) and two entries in `./seo/` (timestamps differ). The snapshot cache always reflects the latest run.
- **Build must pass before journal write.** If `npm run build` fails after auto fixes, halt before writing `seo-progress.md` or updating the snapshot cache.
- **`auto` vs `console` is a fixed contract from `fix-taxonomy.md`.** Don't reclassify on the fly. If a check feels miscategorized, update the taxonomy first, then re-run.
- **Snapshot cache is the only persistent state besides the journal.** Everything else (the diff, the applied log, the per-snapshot archive) is derived per-run.
- **Read-only on Google's UI.** This skill scrapes GSC/GA but never clicks "Request indexing", "Resubmit sitemap", or any other mutation button. Those are always surfaced as `console` fixes for the user to perform.
- **Respect rate limits.** PSI ~1qps unauthenticated. Pace calls. Don't poll GA/GSC in a tight loop.
