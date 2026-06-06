// scrape_cdp_fallback.mjs — Spark fallback for seo-monitor's GSC + GA4 capture.
//
// The skill's primary path drives the `claude-in-chrome` MCP. That MCP isn't
// connected on the Spark box, but a Google-logged-in Chromium often IS up on a
// CDP port (e.g. the Arena browser-use Chromium on :9222). This script attaches
// to it with puppeteer-core (the same connectOverCDP attach the Arena smokes
// use) and reads the three numbers the _STATUS.json beacon needs:
//   • GSC indexed pages          (Pages/Indexing report)
//   • GSC submitted/discovered    (Sitemaps report — discovered URL count)
//   • GA4 active users, 7-day     (Home card, flipped to "Last 7 days")
//
// READ-ONLY: navigates + reads, never clicks a GSC/GA mutation button
// ("Request indexing", "Resubmit sitemap"). Those stay `console` fixes.
//
// Usage:  node .../scrape_cdp_fallback.mjs [cdpPort]   (default 9222)
// Output: one JSON object on stdout, e.g.
//   {"gsc_indexed":24,"gsc_not_indexed":393,"gsc_submitted":183,
//    "ga4_users_7d":69,"ga4_sessions_7d":108,"checked":"<ISO date>","ok":true}
// Prereq: the CDP Chromium must already be signed into the Google account that
// owns sc-domain:ainative.business. If signed out it returns {ok:false,reason}.

import puppeteer from "puppeteer-core";

const PORT = process.argv[2] || "9222";
const RID = "sc-domain%3Aainative.business";
const GSC_INDEX = `https://search.google.com/search-console/index?resource_id=${RID}`;
const GSC_SITEMAPS = `https://search.google.com/search-console/sitemaps?resource_id=${RID}`;
const GA_HOME = "https://analytics.google.com/analytics/web/#/a391868719p533699836/reports/intelligenthome";
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const out = { ok: false };

let browser;
try {
  browser = await puppeteer.connect({ browserURL: `http://127.0.0.1:${PORT}`, defaultViewport: null });
} catch (e) {
  console.log(JSON.stringify({ ok: false, reason: `no CDP browser on :${PORT} — ${e.message}` }));
  process.exit(0);
}
const page = await browser.newPage();

async function loggedOut() {
  const url = page.url();
  const txt = (await page.evaluate(() => document.body.innerText || "")).slice(0, 400);
  return /accounts\.google\.com\/(signin|ServiceLogin)/.test(url) ||
    /Sign in to continue|Choose an account|Use your Google Account|Verify it's you/.test(txt);
}

try {
  // --- GSC: Pages (indexed / not-indexed summary cards) ---
  await page.goto(GSC_INDEX, { waitUntil: "domcontentloaded" });
  await sleep(8000);
  if (await loggedOut()) {
    console.log(JSON.stringify({ ok: false, reason: "CDP Chromium not signed into Google (GSC)" }));
    await browser.disconnect();
    process.exit(0);
  }
  const gsc = await page.evaluate(() => {
    const t = document.body.innerText || "";
    const pick = (label) => { const m = t.match(new RegExp(label + "\\s*\\n\\s*([0-9][0-9,]*)")); return m ? Number(m[1].replace(/,/g, "")) : null; };
    return { indexed: pick("Indexed"), not_indexed: pick("Not indexed") };
  });
  out.gsc_indexed = gsc.indexed;
  out.gsc_not_indexed = gsc.not_indexed;

  // --- GSC: Sitemaps (max discovered-pages across submitted sitemaps) ---
  await page.goto(GSC_SITEMAPS, { waitUntil: "domcontentloaded" });
  await sleep(6000);
  out.gsc_submitted = await page.evaluate(() => {
    let max = null;
    for (const r of document.querySelectorAll("tr")) {
      const cells = [...r.querySelectorAll("td")].map((c) => (c.innerText || "").trim());
      for (const c of cells) { const n = Number(c.replace(/,/g, "")); if (Number.isInteger(n) && n > 0) max = Math.max(max || 0, n); }
    }
    return max;
  });

  // --- GA4: home card → Last 7 days → Active users ---
  await page.goto(GA_HOME, { waitUntil: "domcontentloaded" });
  await sleep(9000);
  await page.evaluate(async () => {
    const visible = (e) => e && e.offsetParent !== null;
    const find = (pred) => [...document.querySelectorAll("button,[role='button'],span,div,a,[role='option'],[role='menuitem'],li")].find((e) => visible(e) && pred((e.textContent || "").trim()));
    const opener = find((t) => /^Last \d+ days$/.test(t));
    if (opener) { opener.click(); await new Promise((r) => setTimeout(r, 1800)); }
    const seven = find((t) => /^Last 7 days$/.test(t));
    if (seven) { seven.click(); await new Promise((r) => setTimeout(r, 800)); }
    const apply = find((t) => /^Apply$/.test(t));
    if (apply) apply.click();
  });
  await sleep(6000);
  const ga = await page.evaluate(() => {
    const t = document.body.innerText || "";
    const pick = (label) => { const m = t.match(new RegExp(label + "\\s*\\n\\s*([0-9][0-9,.]*)")); return m ? Number(m[1].replace(/,/g, "")) : null; };
    return { users: pick("Active users"), sessions: pick("Sessions") };
  });
  out.ga4_users_7d = ga.users;
  out.ga4_sessions_7d = ga.sessions;

  out.checked = new Date().toISOString().slice(0, 10);
  out.ok = out.gsc_indexed != null || out.ga4_users_7d != null;
  console.log(JSON.stringify(out));
} catch (e) {
  console.log(JSON.stringify({ ok: false, reason: e.message, partial: out }));
} finally {
  await page.close().catch(() => {});
  await browser.disconnect().catch(() => {});
}
