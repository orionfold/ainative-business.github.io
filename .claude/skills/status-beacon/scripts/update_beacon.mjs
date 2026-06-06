#!/usr/bin/env node
// update_beacon.mjs — assemble _STATUS.json (the Agency cockpit beacon).
//
// Deterministic + cheap by default. Three metric tiers, each with its own cost:
//   • CHEAP   (articles, fieldkit_modules)  — local file reads, recomputed EVERY
//     run (~free). These are the counts that drift silently.
//   • MANUAL  (models, software_released, arena_features) — "counts only this
//     project knows" (beacon contract); carried forward verbatim. The session
//     model bumps them when a model/tool/feature actually ships.
//   • EXPENSIVE (gsc_*, ga4_*) — a ~40-90s CDP browser scrape. TTL-GATED: only
//     re-scraped when `checked` is older than the TTL (default 7d). Otherwise
//     carried forward (the contract's own rule). This keeps the several-commits-
//     per-hour cadence free — the scrape runs at most ~1×/week.
//
// NEVER fabricates a number; NEVER blocks a commit (browser down/logged-out when
// a scrape is due → carry forward, leave `checked` stale, cockpit shows the >14d
// warning). Narrative fields (focus/recent/next/health/session/blockers) are
// owned by the session model — this script PRESERVES them (edit _STATUS.json).
//
// Usage:
//   node update_beacon.mjs              # TTL-gated (scrape only if SEO ≥7d stale)
//   node update_beacon.mjs --force      # force the SEO scrape now (post-deploy)
//   node update_beacon.mjs --no-scrape  # cheap+manual only, never touch browser
//   node update_beacon.mjs --ttl 14     # override the TTL in days
//   node update_beacon.mjs --cdp-port N # CDP port for the scraper (default 9222)

import { readFileSync, writeFileSync, existsSync } from "node:fs";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";

const HERE = dirname(fileURLToPath(import.meta.url));
const REPO = resolve(HERE, "../../../.."); // status-beacon/scripts → repo root
const BEACON = resolve(REPO, "_STATUS.json");
const SCRAPER = resolve(REPO, ".claude/skills/seo-monitor/scripts/scrape_cdp_fallback.mjs");
const PROJECT_STATS = resolve(REPO, "src/data/field-notes/project-stats.json");
const CONTENT_CONFIG = resolve(REPO, "src/content.config.ts");

const args = process.argv.slice(2);
const force = args.includes("--force");
const noScrape = args.includes("--no-scrape");
const ttlIdx = args.indexOf("--ttl");
const TTL_DAYS = ttlIdx >= 0 ? Number(args[ttlIdx + 1]) : 7;
const portIdx = args.indexOf("--cdp-port");
const CDP_PORT = portIdx >= 0 ? String(args[portIdx + 1]) : "9222";
const today = new Date().toISOString().slice(0, 10);

const daysBetween = (a, b) =>
  Math.round((new Date(b + "T00:00:00Z") - new Date(a + "T00:00:00Z")) / 86400000);
const warn = (field, e) => console.error(`  warn: ${field} recompute failed — ${e.message}`);

if (!existsSync(BEACON)) {
  console.error(`update_beacon: ${BEACON} missing — author the first _STATUS.json by hand (see the status-beacon skill), then this maintains it.`);
  process.exit(1);
}
const beacon = JSON.parse(readFileSync(BEACON, "utf8"));
const m = beacon.metrics || {};

// --- CHEAP: recompute every run -------------------------------------------
try {
  const ps = JSON.parse(readFileSync(PROJECT_STATS, "utf8"));
  if (ps?.articles?.total != null) m.articles = ps.articles.total;
} catch (e) { warn("articles", e); }
try {
  const cfg = readFileSync(CONTENT_CONFIG, "utf8");
  const mm = cfg.match(/const fieldkitModules\s*=\s*\[(.*?)\]/s);
  if (mm) m.fieldkit_modules = (mm[1].match(/'[^']+'/g) || []).length;
} catch (e) { warn("fieldkit_modules", e); }

// --- EXPENSIVE: TTL-gated SEO/GA scrape -----------------------------------
const checked = m.checked || "1970-01-01";
const age = daysBetween(checked, today);
let seoNote;
if (noScrape) {
  seoNote = `skip (--no-scrape) — carried forward (checked ${checked}, ${age}d old)`;
} else if (!force && age < TTL_DAYS) {
  seoNote = `fresh — carried forward (checked ${checked}, ${age}d < ${TTL_DAYS}d TTL)`;
} else {
  const reason = force ? "forced" : `stale ${age}d ≥ ${TTL_DAYS}d TTL`;
  const r = spawnSync("node", [SCRAPER, CDP_PORT], { encoding: "utf8", timeout: 120000 });
  const line = (r.stdout || "").trim().split("\n").filter(Boolean).pop() || "";
  let data; try { data = JSON.parse(line); } catch { data = null; }
  if (data && data.ok) {
    if (data.gsc_indexed != null) m.gsc_indexed = data.gsc_indexed;
    if (data.gsc_submitted != null) m.gsc_submitted = data.gsc_submitted;
    if (data.ga4_users_7d != null) m.ga4_users_7d = data.ga4_users_7d;
    m.checked = data.checked || today;
    seoNote = `scraped (${reason}) — GSC ${m.gsc_indexed}/${m.gsc_submitted} · GA4-7d ${m.ga4_users_7d} · checked ${m.checked}`;
  } else {
    seoNote = `DUE (${reason}) but unavailable (${data?.reason || "no logged-in CDP browser"}) — carried forward, checked stays ${checked}`;
  }
}

beacon.metrics = m;
beacon.updated = today;
writeFileSync(BEACON, JSON.stringify(beacon, null, 2) + "\n");

console.log(`update_beacon → ${BEACON}`);
console.log(`  cheap:  articles ${m.articles} · fieldkit_modules ${m.fieldkit_modules} (recomputed)`);
console.log(`  manual: models ${m.models} · software_released ${m.software_released} · arena_features ${m.arena_features} (carried — bump at ship time)`);
console.log(`  seo:    ${seoNote}`);
