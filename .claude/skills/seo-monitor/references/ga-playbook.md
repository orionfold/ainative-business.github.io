# Google Analytics 4 — Scrape Playbook

GA4 is a brittle React SPA. This playbook documents the survival tricks `seo-monitor` uses to extract data reliably.

## Identity

| Key | Value |
|-----|-------|
| Account id | `391868719` |
| Property id | `533699836` |
| URL fragment prefix | `#/a391868719p533699836/` |

The fragment shape is `#/a<accountId>p<propertyId>/<report-path>`. Always include the account+property prefix when constructing report URLs.

## Report URLs

| Report | URL |
|--------|-----|
| Home (Intelligent home) | `https://analytics.google.com/analytics/web/#/a391868719p533699836/reports/intelligenthome` |
| Acquisition — Traffic acquisition | `https://analytics.google.com/analytics/web/#/a391868719p533699836/reports/explorer?params=_u..nav%3Dmaui&r=lifecycle-traffic-acquisition-v2` |
| Engagement — Landing page | `https://analytics.google.com/analytics/web/#/a391868719p533699836/reports/explorer?params=_u..nav%3Dmaui&r=lifecycle-engagement-landing-page` |
| Tech — Pages and screens | `https://analytics.google.com/analytics/web/#/a391868719p533699836/reports/explorer?params=_u..nav%3Dmaui&r=lifecycle-pages-and-screens` |

These URLs are reverse-engineered from interactive navigation; they may rot if GA4's nav structure changes. If a URL 404s or redirects to the home report, fall back to clicking through the left-nav.

## Login probe

Same as GSC. Look for `accounts.google.com/signin` in the URL or `Sign in` / `Choose an account` in the page text.

GA4 also occasionally shows a "Set up Google Analytics" wizard for new properties — if the page contains "Set up your first property" or similar, the property hasn't been configured. Halt and ask the user.

## The "wait for a data cell" trick

GA4's grid is `[role="grid"]` with `[role="row"]` and `[role="cell"]` children. The grid renders skeleton cells (empty, no text) for ~3–8s before data arrives.

**Don't `wait_for("domcontentloaded")`** — DOM is loaded immediately but data is empty.

**Don't `wait_for(selector="[role='grid']")`** — the grid exists during skeleton state.

**Do** wait until at least one cell contains numeric-looking text:

```js
javascript_tool(tab_id, `(async () => {
  const start = Date.now();
  while (Date.now() - start < 15000) {
    const cells = document.querySelectorAll('[role="cell"], td');
    for (const c of cells) {
      const t = c.textContent.trim();
      // Numeric or percent or duration-looking content
      if (/^[\\$0-9][0-9,.]*[%sm]?$/.test(t) || /^\\d+m\\s\\d+s$/.test(t)) {
        return 'ready';
      }
    }
    await new Promise(r => setTimeout(r, 500));
  }
  return 'timeout';
})()`)
```

If this returns `timeout` on the first attempt, retry once after an additional 10s wait. If still `timeout`, mark this report `partial` and continue with whatever data is captured.

## Preferred (network) path

When GA4 grids render, the page fires XHR to:

```
https://analytics.google.com/analytics/web/api/dataservice/data/v1beta/properties/<propertyId>:runReport
```

or `:batchRunReports` for multi-report views. The request body is JSON specifying dateRanges, dimensions, metrics. The response shape:

```json
{
  "dimensionHeaders": [{ "name": "sessionDefaultChannelGrouping" }],
  "metricHeaders": [{ "name": "sessions", "type": "TYPE_INTEGER" }, { "name": "engagementRate", "type": "TYPE_FLOAT" }],
  "rows": [
    {
      "dimensionValues": [{ "value": "Organic Search" }],
      "metricValues": [{ "value": "905" }, { "value": "0.52" }]
    },
    ...
  ],
  "rowCount": 8
}
```

Capture all responses via `read_network_requests(tab_id)`, filter URLs containing `runReport` or `batchRunReports`, and parse.

Important: GA4 also calls the backend during the skeleton phase to fetch metadata (dimension lists, etc.). Filter responses to those whose body actually contains `rows` and `metricValues` — empty `rows` arrays mean either no data in the window or you captured a metadata call.

## Fallback (DOM scrape) path

If the network capture is empty, use `get_page_text(tab_id)` after the wait-for-data-cell loop returned `ready`. The grid renders as a series of rows:

```
| Session source / medium | Sessions | Engaged sessions | Engagement rate | Avg engagement time per session | ... |
| google / organic        | 905      | 632              | 52.4%           | 1m 23s                          |     |
```

The text-content is whitespace-collapsed by `get_page_text` — split on multiple spaces and align by column count.

## Filters

The default Traffic Acquisition report has no source filter — it groups by Session source/medium. To extract organic-only metrics, filter rows where the dimension value is `google / organic`, `bing / organic`, `duckduckgo / organic` (sum them) — Google is typically >95% of organic so summing or just taking `google / organic` is fine.

The Landing Page report supports a "Session source / medium" secondary dimension or a filter chip. Easiest path: scrape the full landing-page table, then in post-processing keep only rows whose source contains `organic`.

## Date range

GA4 reports default to "Last 28 days" — verify in the date picker chip at the top right of the report. If it doesn't say "Last 28 days" (e.g., the user previously set it to "Last 7 days"), the comparability with prior snapshots breaks. Click the chip and select "Last 28 days":

```js
// Reference selector — may shift; verify before relying
javascript_tool(tab_id, `(() => {
  const chip = document.querySelector('[aria-label*="Date range"], [data-test-id*="date-range"]');
  if (chip) chip.click();
  return chip ? 'opened' : 'not-found';
})()`)
```

Then a popover opens with preset chips. Click the "Last 28 days" preset. Wait 2s for the grid to re-render. Re-run the wait-for-data-cell loop.

## Anti-patterns / things not to do

- **Don't poll GA inside a tight loop** — each navigation re-fires `runReport` and racks up quota.
- **Don't accept the "Compare" toggle** — it doubles the dimension count and complicates parsing. Plain mode only.
- **Don't change the property/account id** — the URL is locked to `391868719/533699836` in the skill.
- **Don't try to export CSV via the UI** — GA4's "Share this report" dropdown can trigger downloads which sit in the user's Downloads folder unreliably.
- **Don't trust `engagementRate` from a partial render** — if the cell shows `--` or a single dash, treat as missing data and mark `partial`.
