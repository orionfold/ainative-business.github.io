// verify_explainers.mjs — build check for the Arena operator curriculum
// (rl-lane-autonomy LA-12 / LA-R8 drift guard).
//
// Two assertions:
//   1. Every teach_key the cockpit hardcodes resolves to an explainer entry —
//      so a renamed/removed entry surfaces as a loud failure, not a blank card.
//   2. Every entry that backlinks the deep-dive (source_article + source_kind +
//      source_term) names a `:::<kind>[<term>]` block that STILL EXISTS in that
//      article — so the cockpit tooltip can't silently drift from the prose.
//
// Read-only. Exit code = number of failures (0 = clean). Mirrors the shape of
// verify_artifact_rendering.mjs (plain node, no Astro runtime).

import { readFile } from 'node:fs/promises';
import { existsSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import yaml from 'js-yaml';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..');
const YAML_PATH = join(ROOT, 'src/content/explainers.yaml');

// The teach_keys the cockpit logic depends on (JobsBoard phase cards +
// interpreter, StandupPane/JobsBoard gates). Keep in sync with the cockpit.
const REQUIRED_KEYS = [
  'phase-lane-bringup', 'phase-sampling', 'phase-training', 'phase-heldout-gate', 'phase-teardown',
  'interp-generalizing', 'interp-inversion', 'interp-plateau',
  'gate-autonomy', 'gate-enqueue',
];

let failures = 0;
const fail = (msg) => { failures += 1; console.error(`  \x1b[31mFAIL\x1b[0m ${msg}`); };
const ok = (msg) => console.log(`  \x1b[32mok\x1b[0m   ${msg}`);

const raw = await readFile(YAML_PATH, 'utf8');
const entries = yaml.load(raw);
if (!Array.isArray(entries)) {
  console.error('explainers.yaml did not parse to an array');
  process.exit(1);
}

const byId = new Map();
for (const e of entries) {
  if (!e || !e.id) { fail(`entry missing id: ${JSON.stringify(e).slice(0, 60)}`); continue; }
  if (byId.has(e.id)) fail(`duplicate id: ${e.id}`);
  byId.set(e.id, e);
}

// 1. Required cockpit teach_keys resolve.
for (const k of REQUIRED_KEYS) {
  if (byId.has(k)) ok(`teach_key ${k}`);
  else fail(`cockpit teach_key has no explainer: ${k}`);
}

// 2. Deep-dive backlinks resolve to a live `:::` block.
const articleCache = new Map();
async function articleBody(slug) {
  if (articleCache.has(slug)) return articleCache.get(slug);
  const p = join(ROOT, 'articles', slug, 'article.md');
  const body = existsSync(p) ? await readFile(p, 'utf8') : null;
  articleCache.set(slug, body);
  return body;
}

for (const e of entries) {
  if (!e.source_article && !e.source_term && !e.source_kind) continue;
  if (!(e.source_article && e.source_term && e.source_kind)) {
    fail(`${e.id}: partial source backlink — need all of source_article/source_kind/source_term`);
    continue;
  }
  const body = await articleBody(e.source_article);
  if (body == null) { fail(`${e.id}: source_article not found: ${e.source_article}`); continue; }
  const needle = `:::${e.source_kind}[${e.source_term}]`;
  if (body.includes(needle)) ok(`${e.id} → ${e.source_article} ${needle.slice(0, 40)}…`);
  else fail(`${e.id}: block not found in ${e.source_article}/article.md → ${needle}`);
}

console.log(
  failures === 0
    ? `\n\x1b[32m${entries.length} explainers, ${REQUIRED_KEYS.length} required keys — all resolve\x1b[0m`
    : `\n\x1b[31m${failures} failure(s) — fix before building\x1b[0m`,
);
process.exit(failures);
