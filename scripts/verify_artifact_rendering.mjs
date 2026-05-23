/**
 * Post-build verifier: enforces the narrative + visual contract on every
 * artifact detail page. Walks dist/artifacts/{loras,adapters,datasets,quants,benches,notebooks}/
 * and checks each rendered HTML against the rules codified in source's
 * NARRATIVE-CONTRACT.md.
 *
 * Rules (apply only when the corresponding manifest field is populated):
 *   1. First <h2> on a detail page must NOT be a drift heading.
 *   2. Every drift list entry must carry a bound annotation (count, fraction,
 *      or comparison). Unbounded narrative drift is rejected.
 *   3. No forward-looking roadmap language anywhere in detail page body.
 *      Catalog hub "Coming soon" pills are exempt (they're chrome on the index).
 *   4. Every artifact detail page must include at least one signature SVG
 *      (LoRASignature / AdapterSignature / DatasetSignature / QuantSignature /
 *      BenchSignature / NotebookSignature) — the visual contract.
 *   5. When the page carries the NotebookBadges block (data-component="notebook-badges"),
 *      it must render BEFORE the first <h2> on the page — the runnable on-ramp
 *      is a navigation aid that lives above-the-fold per the Spark spec §8.3 +
 *      NARRATIVE-CONTRACT updates.
 *
 * Exit code = number of failed checks. Non-zero blocks the build.
 */
import { readdir, readFile } from 'node:fs/promises';
import { existsSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const distDir = join(dirname(fileURLToPath(import.meta.url)), '..', 'dist');
const ARTIFACT_KINDS = ['loras', 'adapters', 'datasets', 'quants', 'benches', 'notebooks'];

const FORWARD_LOOKING_PATTERNS = [
  /\bcoming soon\b/i,
  /\bwill\s+(?:be\s+)?(?:fix|address|ship|land|arrive|support|include)/i,
  /\b(?:on|in)\s+the\s+roadmap\b/i,
  /\bfix\s*eta\b/i,
  /\bnext\s+version\s+(?:will|to)/i,
];

const BOUND_PATTERN = /\b(\d+(?:[.,]\d+)?(?:\s*%|\/\d|x|\s+of\s+\d+|\s+entries?|\s+rows?|\s+cases?|\s+answers?)|<\s*\d|~\s*\d|less\s+than\s+\d|fewer\s+than\s+\d|approximately\s+\d|balance|all\s+other|every\s+other|rest\s+of|same\s+(?:scope|as|bound)|inherited\s+from|two\s+known|three\s+known|four\s+known|subsections?\s*\([a-z]|\([a-z]\)[-–]\([a-z]\))/i;

const failures = [];
const stats = { pagesChecked: 0, kindsCovered: new Set() };

function recordFailure(file, rule, detail) {
  failures.push({ file: file.replace(distDir + '/', ''), rule, detail });
}

function extractBody(html) {
  return html
    .replace(/<head\b[\s\S]*?<\/head>/i, '')
    .replace(/<script\b[\s\S]*?<\/script>/gi, '')
    .replace(/<noscript\b[\s\S]*?<\/noscript>/gi, '')
    .replace(/<nav\b[\s\S]*?<\/nav>/gi, '')
    .replace(/<footer\b[\s\S]*?<\/footer>/gi, '');
}

function firstH2(bodyHtml) {
  const m = bodyHtml.match(/<h2\b[^>]*>([\s\S]*?)<\/h2>/i);
  if (!m) return null;
  return m[1].replace(/<[^>]+>/g, '').trim();
}

function findDriftSection(bodyHtml) {
  const start = bodyHtml.search(/<h2\b[^>]*>\s*Known drift\s*<\/h2>/i);
  if (start === -1) return null;
  const tail = bodyHtml.slice(start);
  const stopMatch = tail.slice(40).search(/<h2\b|<\/section>/i);
  return stopMatch === -1 ? tail : tail.slice(0, 40 + stopMatch);
}

function findDriftEntries(driftHtml) {
  const rows = [];
  for (const m of driftHtml.matchAll(/<dt\b[^>]*>([\s\S]*?)<\/dt>\s*<dd\b[^>]*>([\s\S]*?)<\/dd>/gi)) {
    rows.push({
      item: m[1].replace(/<[^>]+>/g, '').trim(),
      bound: m[2].replace(/<[^>]+>/g, '').trim(),
    });
  }
  return rows;
}

async function checkPage(file, kindSegment) {
  const raw = await readFile(file, 'utf8');
  const body = extractBody(raw);
  stats.pagesChecked++;
  stats.kindsCovered.add(kindSegment);

  const h2 = firstH2(body);
  if (h2 && /^known drift$/i.test(h2)) {
    recordFailure(file, 'positioning-first', `First H2 is "Known drift"; positioning should lead.`);
  }

  const drift = findDriftSection(body);
  if (drift) {
    const rows = findDriftEntries(drift);
    for (const row of rows) {
      if (!BOUND_PATTERN.test(row.bound)) {
        recordFailure(file, 'drift-bounded', `Drift entry "${row.item}" lacks a bound annotation.`);
      }
    }
  }

  for (const pat of FORWARD_LOOKING_PATTERNS) {
    const m = body.match(pat);
    if (m) {
      recordFailure(file, 'no-forward-looking', `Found phrase "${m[0]}" — narrative contract forbids forward-looking language in detail bodies.`);
      break;
    }
  }

  const hasSignature =
    /class="[^"]*\b(?:quant-sig|bs|lora-sig|adapter-sig|ds-sig|nb-sig)\b/.test(body) ||
    /class="[^"]*Signature/.test(body);
  if (!hasSignature) {
    recordFailure(file, 'visual-required', `No signature SVG found on page. Every detail page must carry a data-driven visual.`);
  }

  // Rule 5 — when NotebookBadges renders, it must appear before the first <h2>.
  // Detection key: data-component="notebook-badges" attribute set by the
  // component. Pages without the field render nothing, so this rule simply
  // no-ops on the (today, all) graceful-fallback cases.
  const badgesIdx = body.search(/data-component="notebook-badges"/);
  if (badgesIdx !== -1) {
    const firstH2Idx = body.search(/<h2\b/i);
    if (firstH2Idx !== -1 && badgesIdx > firstH2Idx) {
      recordFailure(
        file,
        'badges-above-fold',
        `NotebookBadges block renders below the first <h2>; the runnable on-ramp must appear above-the-fold per the narrative contract.`,
      );
    }
  }
}

async function main() {
  const detailPages = [];
  for (const seg of ARTIFACT_KINDS) {
    const kindDir = join(distDir, 'artifacts', seg);
    if (!existsSync(kindDir)) continue;
    const entries = await readdir(kindDir, { withFileTypes: true });
    for (const e of entries) {
      if (e.isDirectory()) {
        const idx = join(kindDir, e.name, 'index.html');
        if (existsSync(idx)) detailPages.push({ file: idx, seg });
      }
    }
  }

  for (const { file, seg } of detailPages) {
    await checkPage(file, seg);
  }

  console.log(`\n[verify_artifact_rendering] Checked ${stats.pagesChecked} detail page(s) across ${stats.kindsCovered.size} kind(s): ${[...stats.kindsCovered].join(', ')}`);

  if (failures.length === 0) {
    console.log('[verify_artifact_rendering] ✓ All artifact pages pass the narrative + visual contract.');
    process.exit(0);
  }

  console.error(`\n[verify_artifact_rendering] ✗ ${failures.length} contract violation(s):\n`);
  const byRule = {};
  for (const f of failures) (byRule[f.rule] ??= []).push(f);
  for (const [rule, items] of Object.entries(byRule)) {
    console.error(`  ${rule} (${items.length}):`);
    for (const i of items) console.error(`    - ${i.file}\n        ${i.detail}`);
  }
  process.exit(failures.length);
}

main().catch((err) => {
  console.error('[verify_artifact_rendering] crashed:', err);
  process.exit(99);
});
