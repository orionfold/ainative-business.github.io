# Google Search Console — Scrape Playbook

The reference for everything `seo-monitor` does on Google Search Console. Read the section that matches the Plan Phase step you're on.

## Identity

| Key | Value |
|-----|-------|
| Property type | Domain property |
| Property id | `sc-domain:ainative.business` |
| Resource id (URL param) | `sc-domain%3Aainative.business` |

The resource id is URL-encoded everywhere in the GSC URL space.

## Report URLs

| Report | URL template |
|--------|--------------|
| Overview | `https://search.google.com/search-console?resource_id=sc-domain%3Aainative.business` |
| Performance — Search results | `https://search.google.com/search-console/performance/search-analytics?resource_id=sc-domain%3Aainative.business&num_of_days=28` |
| Indexing — Pages (Coverage) | `https://search.google.com/search-console/index/coverage?resource_id=sc-domain%3Aainative.business` |
| Sitemaps | `https://search.google.com/search-console/sitemaps?resource_id=sc-domain%3Aainative.business` |
| URL Inspection | `https://search.google.com/search-console/inspect?resource_id=sc-domain%3Aainative.business&id=<encoded-URL>` |
| Enhancement — Articles | `https://search.google.com/search-console/enhancement/structured-data-articles?resource_id=sc-domain%3Aainative.business` |
| Enhancement — Breadcrumbs | `https://search.google.com/search-console/enhancement/structured-data-breadcrumbs?resource_id=sc-domain%3Aainative.business` |

`num_of_days=28` is the default window the skill uses. GSC supports 1, 7, 28, 90, and 16 months — we standardize on 28 to balance signal and noise.

## Login probe

After `navigate` + `read_page`, the page is "logged out" if:

- The current URL contains `accounts.google.com/signin` or `accounts.google.com/ServiceLogin`
- The page text contains `Sign in to continue`, `Choose an account`, or `Use your Google Account`
- The page text contains `Verify it's you` (2FA challenge — also halt and ask the user to complete it manually)

If any of these are true, halt with the canonical sign-in instruction and emit `Status: login-required`.

## Performance — preferred (network) path

After the Performance report loads (5–8s on first nav, cached on re-renders), the page emits XHR requests to:

```
https://search.google.com/search-console/api/searchanalytics/query
```

The request body is a JSON object specifying dimensions and a date range. The response shape:

```json
{
  "rows": [
    {
      "keys": ["<dimension value>"],
      "clicks": 123,
      "impressions": 4567,
      "ctr": 0.027,
      "position": 12.34
    },
    ...
  ],
  "responseAggregationType": "byProperty"
}
```

The same endpoint is hit multiple times — once per active dimension chip (Queries, Pages, Countries, Devices, Search Appearance, Dates). Capture all of them via `read_network_requests(tab_id)` and filter URLs containing `/searchanalytics/query`.

**To switch the active table to "Pages"** before scraping, programmatically click the "Pages" chip:

```js
javascript_tool(tab_id, `(() => {
  const chip = [...document.querySelectorAll('[role="tab"], [role="button"]')]
    .find(el => el.textContent.trim() === 'Pages');
  if (chip) chip.click();
  return chip ? 'clicked' : 'not-found';
})()`)
```

Then wait 1.5s for the XHR to fire, then re-read network requests.

## Performance — fallback (DOM scrape) path

If `read_network_requests` returns no rows (the MCP can miss in-flight requests if it attaches after the request fires), use `get_page_text(tab_id)` and parse the rendered table.

The table is a virtualized list — rows are rendered as `<tr>` elements but only the visible ~25 are in the DOM at any time. Scroll the table container to load more if needed:

```js
javascript_tool(tab_id, `(() => {
  const grid = document.querySelector('[role="grid"], table');
  if (grid) grid.scrollBy(0, 5000);
  return grid ? 'scrolled' : 'no-grid';
})()`)
```

Each row's columns (in order): Query / Page / Clicks / Impressions / CTR / Position. Skip the column headers in the first row.

## Indexing — Coverage

The Coverage page shows aggregate counts at the top and a "Why pages aren't indexed" table below. The table cells map to the reason categories — capture by text match:

| Display name | Internal key (use this in JSON) |
|--------------|----------------------------------|
| Crawled - currently not indexed | `crawled_not_indexed` |
| Discovered - currently not indexed | `discovered_not_indexed` |
| Page with redirect | `redirect` |
| Duplicate without user-selected canonical | `duplicate_no_canonical` |
| Duplicate, Google chose different canonical than user | `duplicate_google_canonical` |
| Soft 404 | `soft_404` |
| Excluded by 'noindex' tag | `noindex` |
| Blocked by robots.txt | `robots_blocked` |
| Not found (404) | `not_found` |
| Server error (5xx) | `server_error` |
| URL marked 'noindex' | `noindex` (combine) |

To drill into a reason and capture example URLs: click the reason name, wait for the example-URLs table to render, capture up to 10 URLs by reading text-content of the rows.

## Sitemaps

The Sitemaps page lists each submitted sitemap. For each row capture:

| Column | What to grab |
|--------|--------------|
| Sitemap | URL string (the cell is a link) |
| Type | "Sitemap index", "Sitemap" |
| Submitted | Date (parse to ISO) |
| Last read | Date or "—" if never |
| Status | "Success", "Has errors", "Couldn't fetch", "Pending" |
| Discovered URLs | Integer |

A "Last read" > 14 days ago combined with new pages in the site (which the local audit can detect by counting `dist/**/*.html`) is a high-confidence "resubmit sitemap" `console` fix.

## URL Inspection (optional, on-demand per URL)

The skill does **not** drive URL inspections in bulk — Google rate-limits them and shows a "Daily quota" warning. But for one or two high-priority URLs flagged in cross-reference (Step 8), the skill can navigate:

```
https://search.google.com/search-console/inspect?resource_id=sc-domain%3Aainative.business&id=https%3A%2F%2Fainative.business%2Ffield-notes%2Fkv-cache%2F
```

…then `read_page` to extract: "URL is on Google" / "URL is not on Google", last crawl date, indexing status. Don't click "Request indexing" — that's a `console` fix the user performs.

## Enhancements (structured data)

The enhancement reports list URLs with JSON-LD warnings/errors. For each enhancement type:

1. Navigate to the enhancement URL.
2. Read top-line warning/error counts.
3. For each non-zero category, capture up to 5 example URLs and the human-readable issue (e.g., "Missing field 'image'").

These map cleanly to `references/fix-taxonomy.md` JSON-LD checks for the local audit (Step 7).

## Anti-patterns / things not to do

- **Don't click "Request indexing"** — always surfaced as a console fix, never automated. Bot-detection risk and arguably a ToS gray area.
- **Don't click "Validate fix"** in enhancement reports — let Google re-discover naturally; the skill measures delta over time.
- **Don't change date range to anything other than 28 days** — comparability across runs depends on the window being constant.
- **Don't accept cookie consent banners** — they shouldn't appear inside an authenticated Google product, but if one does, screenshot and ask the user to dismiss manually.
