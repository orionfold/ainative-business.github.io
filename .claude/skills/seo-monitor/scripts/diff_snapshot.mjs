#!/usr/bin/env node
// diff_snapshot.mjs — compute KPI deltas between prior and current snapshots.
//
// Usage:
//   node .claude/skills/seo-monitor/scripts/diff_snapshot.mjs \
//     --prior <path-or-empty> \
//     --current <path>
//
// Inputs are JSON files matching the shape produced by the skill in Plan Phase:
//   {
//     gsc: { totals: { clicks, impressions, ctr, position }, indexed, notIndexed: { byReason }, queries: [...], pages: [...], sitemaps: [...] },
//     ga:  { organic: { sessions, users, engagementRate, avgEngagementTime }, landingPages: [...], partial?: true },
//     psi: { byUrl: { [url]: { mobile: { lcp, inp, cls, scores }, desktop: {...} } } },
//     audit: { checks: [...], summary: {...} },
//     capturedAt: ISO timestamp
//   }
//
// Output: JSON to stdout: { deltas: [...], topMovers: [...], isFirstRun: bool }

import { readFileSync, existsSync } from 'node:fs';
import { argv, stdout, exit } from 'node:process';

const args = Object.fromEntries(
  argv.slice(2).reduce((acc, v, i, a) => {
    if (v.startsWith('--')) acc.push([v.slice(2), a[i + 1]]);
    return acc;
  }, [])
);

if (!args.current) {
  console.error('usage: diff_snapshot.mjs --prior <path> --current <path>');
  exit(2);
}

const current = JSON.parse(readFileSync(args.current, 'utf8'));
const prior = args.prior && existsSync(args.prior) ? JSON.parse(readFileSync(args.prior, 'utf8')) : null;
const isFirstRun = !prior;

// Direction-of-good rules. "up" means a higher value is better.
const goodDir = {
  'GSC.clicks': 'up',
  'GSC.impressions': 'up',
  'GSC.ctr': 'up',
  'GSC.position': 'down', // lower (closer to #1) is better
  'GSC.indexed': 'up',
  'GSC.crawled_not_indexed': 'down',
  'GSC.discovered_not_indexed': 'down',
  'GSC.duplicate_no_canonical': 'down',
  'GSC.soft_404': 'down',
  'GSC.redirect': 'flat', // expected migration noise; trend doesn't have a moral direction
  'GA.sessions': 'up',
  'GA.users': 'up',
  'GA.engagementRate': 'up',
  'GA.avgEngagementTime': 'up',
  'PSI.lcp': 'down',
  'PSI.inp': 'down',
  'PSI.cls': 'down',
  'PSI.performance': 'up',
  'PSI.seo': 'up',
  'PSI.accessibility': 'up',
  'PSI.bestPractices': 'up',
  'AUDIT.totalIssues': 'down',
};

function dir(delta) {
  if (delta === 0) return 'flat';
  return delta > 0 ? 'up' : 'down';
}
function better(key, deltaDir) {
  const want = goodDir[key];
  if (!want || want === 'flat') return 'neutral';
  if (deltaDir === 'flat') return 'neutral';
  return want === deltaDir ? 'better' : 'worse';
}

function delta(source, metric, key, currentVal, priorVal, opts = {}) {
  if (currentVal == null) return null;
  if (priorVal == null && !isFirstRun) priorVal = null;
  const d = (currentVal != null && priorVal != null) ? (currentVal - priorVal) : null;
  const direction = d != null ? dir(d) : 'na';
  return {
    source,
    metric,
    key,
    prior: priorVal,
    current: currentVal,
    delta: d,
    direction,
    better: d != null ? better(key, direction) : 'na',
    unit: opts.unit ?? null,
    format: opts.format ?? null, // 'int' | 'float' | 'percent' | 'seconds' | 'ms'
  };
}

const out = { deltas: [], topMovers: [], isFirstRun };

// --- GSC totals ---
const cT = current.gsc?.totals ?? {};
const pT = prior?.gsc?.totals ?? {};
out.deltas.push(delta('GSC', 'Total clicks (28d)', 'GSC.clicks', cT.clicks, pT.clicks, { format: 'int' }));
out.deltas.push(delta('GSC', 'Total impressions (28d)', 'GSC.impressions', cT.impressions, pT.impressions, { format: 'int' }));
out.deltas.push(delta('GSC', 'Avg CTR (28d)', 'GSC.ctr', cT.ctr, pT.ctr, { format: 'percent' }));
out.deltas.push(delta('GSC', 'Avg position', 'GSC.position', cT.position, pT.position, { format: 'float' }));

// --- GSC indexing ---
const cI = current.gsc?.indexed ?? null;
const pI = prior?.gsc?.indexed ?? null;
out.deltas.push(delta('GSC', 'Indexed pages', 'GSC.indexed', cI, pI, { format: 'int' }));
const reasons = ['crawled_not_indexed', 'discovered_not_indexed', 'redirect', 'duplicate_no_canonical', 'soft_404'];
for (const r of reasons) {
  const cv = current.gsc?.notIndexed?.byReason?.[r];
  const pv = prior?.gsc?.notIndexed?.byReason?.[r];
  if (cv != null || pv != null) {
    const label = r.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
    out.deltas.push(delta('GSC', label, `GSC.${r}`, cv, pv, { format: 'int' }));
  }
}

// --- GA organic ---
const cG = current.ga?.organic ?? {};
const pG = prior?.ga?.organic ?? {};
if (!current.ga?.partial) {
  out.deltas.push(delta('GA', 'Organic sessions', 'GA.sessions', cG.sessions, pG.sessions, { format: 'int' }));
  out.deltas.push(delta('GA', 'Organic users', 'GA.users', cG.users, pG.users, { format: 'int' }));
  out.deltas.push(delta('GA', 'Engagement rate', 'GA.engagementRate', cG.engagementRate, pG.engagementRate, { format: 'percent' }));
  out.deltas.push(delta('GA', 'Avg engagement time', 'GA.avgEngagementTime', cG.avgEngagementTime, pG.avgEngagementTime, { format: 'seconds' }));
}

// --- PSI home mobile (representative single-page metric for the summary) ---
const psiHome = 'https://ainative.business/';
const cP = current.psi?.byUrl?.[psiHome]?.mobile ?? {};
const pP = prior?.psi?.byUrl?.[psiHome]?.mobile ?? {};
out.deltas.push(delta('PSI', 'Home mobile LCP (s)', 'PSI.lcp', cP.lcp, pP.lcp, { format: 'seconds' }));
out.deltas.push(delta('PSI', 'Home mobile INP (ms)', 'PSI.inp', cP.inp, pP.inp, { format: 'ms' }));
out.deltas.push(delta('PSI', 'Home mobile CLS', 'PSI.cls', cP.cls, pP.cls, { format: 'float' }));
out.deltas.push(delta('PSI', 'Home mobile Performance', 'PSI.performance', cP.scores?.performance, pP.scores?.performance, { format: 'int' }));
out.deltas.push(delta('PSI', 'Home mobile SEO', 'PSI.seo', cP.scores?.seo, pP.scores?.seo, { format: 'int' }));
out.deltas.push(delta('PSI', 'Home mobile Accessibility', 'PSI.accessibility', cP.scores?.accessibility, pP.scores?.accessibility, { format: 'int' }));

// --- audit totals ---
const cA = current.audit?.summary?.totalIssues ?? null;
const pA = prior?.audit?.summary?.totalIssues ?? null;
out.deltas.push(delta('AUDIT', 'Local audit issues', 'AUDIT.totalIssues', cA, pA, { format: 'int' }));

// drop nulls
out.deltas = out.deltas.filter(Boolean);

// --- top movers (queries + pages whose clicks moved most) ---
function indexBy(arr, keyFn) {
  const m = new Map();
  for (const it of arr ?? []) m.set(keyFn(it), it);
  return m;
}

function movers(currentArr, priorArr, keyFn, metric = 'clicks', limit = 5) {
  const cMap = indexBy(currentArr, keyFn);
  const pMap = indexBy(priorArr ?? [], keyFn);
  const keys = new Set([...cMap.keys(), ...pMap.keys()]);
  const out = [];
  for (const k of keys) {
    const c = cMap.get(k)?.[metric] ?? 0;
    const p = pMap.get(k)?.[metric] ?? 0;
    if (c === p) continue;
    out.push({
      key: k,
      metric,
      prior: p,
      current: c,
      delta: c - p,
      positionPrior: pMap.get(k)?.position ?? null,
      positionCurrent: cMap.get(k)?.position ?? null,
    });
  }
  return out.sort((a, b) => Math.abs(b.delta) - Math.abs(a.delta)).slice(0, limit);
}

out.topMovers = [
  ...movers(current.gsc?.queries, prior?.gsc?.queries, (q) => q.query ?? q.keys?.[0], 'clicks', 5).map((m) => ({ kind: 'gsc-query', ...m })),
  ...movers(current.gsc?.pages, prior?.gsc?.pages, (p) => p.page ?? p.keys?.[0], 'clicks', 5).map((m) => ({ kind: 'gsc-page', ...m })),
  ...movers(current.ga?.landingPages, prior?.ga?.landingPages, (p) => p.page ?? p.landingPage, 'sessions', 5).map((m) => ({ kind: 'ga-landing', ...m })),
];

stdout.write(JSON.stringify(out, null, 2));
