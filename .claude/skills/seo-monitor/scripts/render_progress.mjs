#!/usr/bin/env node
// render_progress.mjs — write a snapshot block to ./seo-progress.md.
//
// Usage:
//   node .claude/skills/seo-monitor/scripts/render_progress.mjs \
//     --current <path-to-current.json> \
//     --diff <path-to-diff.json> \
//     --applied <path-to-applied.json> \
//     --progress ./seo-progress.md \
//     --archive ./seo/YYYY-MM-DD-HHMM.md \
//     --buildStatus "ok|fail" \
//     --buildDuration "24.8s" \
//     [--template <path-to-progress-template.md>]
//
// Idempotence: if the most recent entry in <progress> has today's date, the
// new entry replaces it. Otherwise the new entry is inserted at the top
// (immediately after the template's header marker comment).

import { readFileSync, writeFileSync, existsSync, mkdirSync, copyFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { argv, exit } from 'node:process';

const args = Object.fromEntries(
  argv.slice(2).reduce((acc, v, i, a) => {
    if (v.startsWith('--')) acc.push([v.slice(2), a[i + 1]]);
    return acc;
  }, [])
);

const requireArg = (k) => {
  if (!args[k]) {
    console.error(`missing --${k}`);
    exit(2);
  }
};
['current', 'diff', 'applied', 'progress'].forEach(requireArg);

const current = JSON.parse(readFileSync(args.current, 'utf8'));
const diff = JSON.parse(readFileSync(args.diff, 'utf8'));
const applied = JSON.parse(readFileSync(args.applied, 'utf8')); // { applied: [...], skipped: [...] }
const progressPath = resolve(args.progress);
const archivePath = args.archive ? resolve(args.archive) : null;
const buildStatus = args.buildStatus || 'unknown'; // 'ok' | 'fail'
const buildDuration = args.buildDuration || '';
const templatePath = args.template
  ? resolve(args.template)
  : resolve(__dirname_safe(), '..', 'assets', 'progress-template.md');

function __dirname_safe() {
  // ESM-safe equivalent of __dirname
  return dirname(new URL(import.meta.url).pathname);
}

// --- formatting helpers ---
function fmt(val, format) {
  if (val == null) return '—';
  if (format === 'percent') return (val * 100).toFixed(1) + '%';
  if (format === 'seconds') return val.toFixed(2) + 's';
  if (format === 'ms') return Math.round(val) + 'ms';
  if (format === 'float') return Number(val).toFixed(2);
  if (format === 'int') return Math.round(val).toLocaleString('en-US');
  return String(val);
}

function arrow(d, { showQuality = true } = {}) {
  if (!d) return '';
  if (d.direction === 'flat' || d.delta === 0) return '→ no change';
  const sign = d.delta > 0 ? '+' : '';
  const head = d.direction === 'up' ? '↑' : '↓';
  let body = `${head} ${sign}${fmt(d.delta, d.format)}`;
  if (showQuality) {
    if (d.better === 'better') body += ' (better)';
    else if (d.better === 'worse') body += ' (worse)';
  }
  return body;
}

// --- compose the block ---
function buildBlock() {
  const now = new Date(current.capturedAt || Date.now());
  const yyyy = now.getFullYear();
  const mm = String(now.getMonth() + 1).padStart(2, '0');
  const dd = String(now.getDate()).padStart(2, '0');
  const HH = String(now.getHours()).padStart(2, '0');
  const MM = String(now.getMinutes()).padStart(2, '0');
  const date = `${yyyy}-${mm}-${dd}`;
  const ts = `${date} ${HH}:${MM}`;

  // Snapshot window: end = now, start = 28 days back
  const start = new Date(now);
  start.setDate(start.getDate() - 28);
  const wStart = `${start.getFullYear()}-${String(start.getMonth() + 1).padStart(2, '0')}-${String(start.getDate()).padStart(2, '0')}`;

  const appliedN = applied.applied?.length ?? 0;
  const skippedN = applied.skipped?.length ?? 0;
  const consoleN = applied.console?.length ?? 0;

  const status = diff.isFirstRun
    ? 'first-run'
    : (appliedN === 0 && diff.deltas.every((d) => (d.delta ?? 0) === 0))
      ? 'no-changes'
      : 'changed';

  // pick a few headline metrics for the one-liner summary
  const pick = (key) => diff.deltas.find((d) => d.key === key);
  const clicks = pick('GSC.clicks');
  const impressions = pick('GSC.impressions');
  const indexed = pick('GSC.indexed');
  const lcp = pick('PSI.lcp');

  const parts = [];
  const shortArrow = (d) => arrow(d, { showQuality: false });
  if (clicks?.current != null) parts.push(`Clicks ${fmt(clicks.current, 'int')} (${shortArrow(clicks)})`);
  if (impressions?.current != null) parts.push(`Impressions ${fmt(impressions.current, 'int')} (${shortArrow(impressions)})`);
  if (indexed?.current != null) parts.push(`Indexed ${fmt(indexed.current, 'int')} (${shortArrow(indexed)})`);
  if (lcp?.current != null) parts.push(`LCP ${fmt(lcp.current, 'seconds')} (${shortArrow(lcp)})`);
  const summary = parts.join(' · ') || '(no headline metrics this run)';

  const lines = [];
  lines.push(`## [${ts}] Snapshot`);
  lines.push('');
  lines.push(`**Window:** ${wStart} → ${date} (28 days)`);
  lines.push(`**Status:** ${status} · ${appliedN} auto fixes applied · ${skippedN} skipped · ${consoleN} console actions surfaced`);
  lines.push(`**Summary:** ${summary}`);
  lines.push('');

  // KPI table
  lines.push(`| KPI | Value | Δ vs prior |`);
  lines.push('|-----|-------|------------------|');
  for (const d of diff.deltas) {
    lines.push(`| ${d.source} ${d.metric} | ${fmt(d.current, d.format)} | ${arrow(d)} |`);
  }
  lines.push('');

  // top movers
  if (diff.topMovers?.length) {
    lines.push('**Top movers:**');
    for (const m of diff.topMovers.slice(0, 5)) {
      const kindLabel = m.kind === 'gsc-query' ? 'Query' : m.kind === 'gsc-page' ? 'Page' : 'Landing';
      const arr = m.delta > 0 ? '↑' : '↓';
      lines.push(`- ${kindLabel} "${m.key}" — ${m.metric} ${m.prior}→${m.current} (${arr} ${m.delta > 0 ? '+' : ''}${m.delta})`);
    }
    lines.push('');
  }

  // applied fixes
  if (applied.applied?.length) {
    lines.push(`**Applied auto fixes (${appliedN}):** ${applied.applied.map((f) => f.summary || `${f.id} on ${f.file}`).join('; ')}.`);
  } else {
    lines.push(`**Applied auto fixes:** none.`);
  }

  // skipped
  if (skippedN) {
    lines.push(`**Skipped (${skippedN}):** ${applied.skipped.map((f) => `${f.id} on ${f.file} — ${f.reason}`).join('; ')}.`);
  }

  // console actions
  if (consoleN) {
    lines.push(`**Console actions surfaced (${consoleN}):** ${applied.console.map((f) => f.summary || f.id).join('; ')}.`);
  }
  lines.push('');

  // archive + build
  lines.push(`**Archive:** ${archivePath ? toRelativeForJournal(archivePath, progressPath) : '—'} · **Build:** ${buildStatus === 'ok' ? '✓' : '✗'} ${buildDuration}`);
  lines.push('');
  lines.push('---');
  lines.push('');

  return { block: lines.join('\n'), date };
}

function toRelativeForJournal(absPath, journalPath) {
  // The journal sits at repo root; archive is ./seo/...
  const journalDir = dirname(journalPath);
  if (absPath.startsWith(journalDir)) return absPath.slice(journalDir.length + 1);
  return absPath;
}

// --- write to seo-progress.md ---
const { block, date } = buildBlock();

let body;
if (!existsSync(progressPath)) {
  // Initialize from template
  if (existsSync(templatePath)) {
    copyFileSync(templatePath, progressPath);
    body = readFileSync(progressPath, 'utf8');
  } else {
    body = '# SEO Progress\n\n<!-- snapshots appended below this line; newest first -->\n\n';
  }
} else {
  body = readFileSync(progressPath, 'utf8');
}

// Idempotence: if a snapshot with today's date already exists, replace it.
// Match `## [YYYY-MM-DD HH:MM] Snapshot` through the closing `\n---\n` —
// blocks always end with a single newline after the divider; any extra
// blank line before the next block belongs to the insertion logic.
const todayRe = new RegExp(`(^|\\n)## \\[${date} \\d{2}:\\d{2}\\] Snapshot[\\s\\S]*?\\n---\\n`, 'm');
if (todayRe.test(body)) {
  body = body.replace(todayRe, (_, leading) => `${leading}${block}`);
} else {
  // Insert right after the marker comment, or after the first H1+blank if marker missing
  const markerIdx = body.indexOf('<!-- snapshots appended below this line; newest first -->');
  if (markerIdx >= 0) {
    const insertAt = body.indexOf('\n', markerIdx) + 1;
    body = body.slice(0, insertAt) + '\n' + block + body.slice(insertAt);
  } else {
    // Fallback: prepend
    body = body.trimEnd() + '\n\n' + block;
  }
}

writeFileSync(progressPath, body);

// --- write archive (if requested) ---
if (archivePath) {
  mkdirSync(dirname(archivePath), { recursive: true });
  const archive = [
    block,
    '',
    '## Applied / Skipped / Console',
    '',
    '```json',
    JSON.stringify(applied, null, 2),
    '```',
    '',
    '## Build',
    '',
    '```',
    `status: ${buildStatus}`,
    `duration: ${buildDuration}`,
    '```',
    '',
    '## Current Snapshot (raw extract)',
    '',
    '```json',
    JSON.stringify(current, null, 2),
    '```',
    '',
    '## Diff vs prior',
    '',
    '```json',
    JSON.stringify(diff, null, 2),
    '```',
    '',
  ].join('\n');
  writeFileSync(archivePath, archive);
}

console.error(`wrote ${progressPath}` + (archivePath ? ` and ${archivePath}` : ''));
