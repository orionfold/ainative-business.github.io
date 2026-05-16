# PageSpeed Insights — REST API Playbook

PSI has a public v5 REST API. `seo-monitor` uses the API rather than scraping the UI — it's faster, more reliable, and returns the full Lighthouse JSON.

## Endpoint

```
https://www.googleapis.com/pagespeedonline/v5/runPagespeed
```

| Param | Required | Default | Notes |
|-------|----------|---------|-------|
| `url` | yes | — | The URL to audit, URL-encoded |
| `strategy` | no | `desktop` | `mobile` or `desktop`. We always pass both. |
| `category` | repeatable | `performance` | Use four: `performance`, `seo`, `accessibility`, `best-practices` |
| `locale` | no | `en` | Default fine |
| `key` | no | — | API key — not needed for unauthenticated use (slower / rate-limited) |

Authenticated calls require a Google API key and a Google Cloud project. The skill operates unauthenticated to avoid setup; this caps us at ~1qps and ~25,000 calls/day, well within our needs (10 calls per run, weekly runs).

## Priority URLs to audit

Always audit these 5, both mobile and desktop (10 calls/run total):

1. `https://ainative.business/` — homepage
2. `https://ainative.business/field-notes/` — editorial hub (highest organic traffic)
3. `https://ainative.business/book/` — book hub
4. `https://ainative.business/docs/` — product docs hub
5. `https://ainative.business/projects/` — about / portfolio

Skip per-article audits in v1 — they would 10× the call count and most articles share the same Astro layout, so their CWV scores cluster around the section averages.

## Calling pattern

From any tab open in `claude-in-chrome` (PSI tab is fine, but any will do — the API is CORS-permissive):

```js
javascript_tool(tab_id, `(async () => {
  const urls = [
    'https://ainative.business/',
    'https://ainative.business/field-notes/',
    'https://ainative.business/book/',
    'https://ainative.business/docs/',
    'https://ainative.business/projects/',
  ];
  const strategies = ['mobile', 'desktop'];
  const cats = ['performance', 'seo', 'accessibility', 'best-practices']
    .map(c => 'category=' + c).join('&');
  const results = [];
  for (const u of urls) {
    for (const s of strategies) {
      const api = 'https://www.googleapis.com/pagespeedonline/v5/runPagespeed' +
        '?url=' + encodeURIComponent(u) +
        '&strategy=' + s + '&' + cats;
      let attempt = 0, ok = false, json;
      while (attempt < 3 && !ok) {
        try {
          const r = await fetch(api);
          if (r.status === 429 || r.status >= 500) throw new Error('retryable ' + r.status);
          json = await r.json();
          ok = true;
        } catch (e) {
          attempt++;
          await new Promise(res => setTimeout(res, 5000 * attempt));
        }
      }
      results.push({ url: u, strategy: s, ok, json: ok ? json : null });
      await new Promise(res => setTimeout(res, 1100)); // ~1qps unauth limit
    }
  }
  return results;
})()`)
```

This takes ~25–45 seconds end-to-end (10 audits × ~2–3s analysis + 1.1s rate-limit pause).

## Parsing the response

The Lighthouse result is at `result.lighthouseResult`. Extract:

```js
const lh = response.lighthouseResult;

const scores = {
  performance: lh.categories.performance.score * 100,
  seo: lh.categories.seo.score * 100,
  accessibility: lh.categories.accessibility.score * 100,
  bestPractices: lh.categories['best-practices'].score * 100,
};

const cwv = {
  lcp: lh.audits['largest-contentful-paint'].numericValue / 1000, // seconds
  inp: lh.audits['interaction-to-next-paint']?.numericValue || null, // ms, may be null in lab
  cls: lh.audits['cumulative-layout-shift'].numericValue, // unitless
  fcp: lh.audits['first-contentful-paint'].numericValue / 1000,
  tbt: lh.audits['total-blocking-time'].numericValue, // ms
};

// Top 5 failed audits (score < 0.9)
const failed = Object.values(lh.audits)
  .filter(a => typeof a.score === 'number' && a.score < 0.9 && a.score !== null)
  .sort((a, b) => a.score - b.score)
  .slice(0, 5)
  .map(a => ({ id: a.id, title: a.title, score: a.score, displayValue: a.displayValue }));
```

The unitless CLS, ms INP, and seconds-cast LCP are the three Core Web Vitals we track over time. Google's "good" thresholds:

| Metric | Good | Needs Improvement | Poor |
|--------|------|-------------------|------|
| LCP | ≤ 2.5s | ≤ 4.0s | > 4.0s |
| INP | ≤ 200ms | ≤ 500ms | > 500ms |
| CLS | ≤ 0.1 | ≤ 0.25 | > 0.25 |

## Field data vs lab data

The PSI response has two analyses:

1. **`loadingExperience`** (and `originLoadingExperience`) — real-user field data from Chrome UX Report (CrUX), 28-day aggregate. Only present if the URL has enough traffic.
2. **`lighthouseResult`** — synthetic lab data from one Lighthouse run.

For a low-traffic site like ainative.business (months of buildup ahead), CrUX field data will be `null` for most URLs. Always extract lab data. If CrUX is present, capture it as a secondary signal — it's the ground truth for what Google scores on for SEO.

```js
const crux = response.loadingExperience?.metrics; // may be undefined
// crux.LARGEST_CONTENTFUL_PAINT_MS.percentile === median LCP across real users
```

## Fix-taxonomy mapping

These Lighthouse audit IDs map to specific fixes in `fix-taxonomy.md`:

| Audit ID | Mapped fix |
|----------|-----------|
| `unused-css-rules` | review and prune in `global.css` / component styles |
| `unused-javascript` | check for unused imports in dev tooling |
| `render-blocking-resources` | audit `Layout.astro` for synchronous external scripts |
| `largest-contentful-paint-element` | the element will be named — add `loading="eager"` / explicit dimensions |
| `uses-rel-preconnect` | candidate for new `<link rel="preconnect">` in Layout.astro |
| `uses-text-compression` | dist/ artifacts — GitHub Pages handles this, low priority |
| `image-size-responsive` | use Astro's `<Image>` with `widths` |
| `next-gen-images` | ensure WebP/AVIF generation in Astro image pipeline |
| `meta-description` | console fix (manual authoring) |
| `document-title` | check page title front-matter |
| `crawlable-anchors` | trailing-slash audit territory |
| `tap-targets` | mobile accessibility |
| `color-contrast` | accessibility, WCAG AA |

## Rate-limit handling

Unauthenticated: 25,000 queries/day, ~1qps. The skill makes 10 calls per run; even 100 runs/day stays under the daily limit.

On 429 response: retry with exponential backoff (5s, 10s, 20s). After 3 failures on the same URL, mark that URL `skipped` in the snapshot, omit from PSI deltas, continue.

If all 10 calls fail (e.g., outage), fall back to scraping the UI at `https://pagespeed.web.dev/analysis?url=…` in the PSI tab. Wait for the score circles to render (look for `aria-label` containing "Performance"), then `get_page_text` to extract score numbers. Note in the snapshot that PSI ran in fallback mode and only the home URL was audited.

## Anti-patterns / things not to do

- **Don't pass a Google API key** — adds setup complexity, no meaningful benefit at this scale.
- **Don't audit deep article URLs in v1** — they cluster around section averages; section-level signal is what matters.
- **Don't read the `i18n.rendererFormattedStrings` field** — locale-dependent strings will inflate diff noise across runs if locale ever varies.
- **Don't trust a single PSI run as ground truth** — Lighthouse scores have ±5 variance run-to-run. Trend over multiple snapshots is what matters; don't propose a fix based on one run unless the score is in the "Poor" band.
