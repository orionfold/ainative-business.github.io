/**
 * Catalog drift guard: the Arena cockpit builds its artifact catalog from
 * arena-app/src/content/artifacts/, which is a COPY of the canonical
 * src/content/artifacts/. The copy froze silently for 13 days in 2026-06
 * (dropped Advisor/Kepler/Cortex from every cockpit surface), so this
 * verifier makes the drift deterministic and loud:
 *
 *   1. Every canonical *.yaml must exist in arena-app and be byte-identical.
 *   2. arena-app must carry no *.yaml absent from canonical (reverse drift).
 *
 * Non-yaml files (README.md, .gitkeep) are exempt — they're per-copy chrome.
 * Run beside verify_artifact_rendering.mjs / verify_field_notes_rendering.mjs.
 * Exit code = number of drifted manifests. Fix: cp the canonical yaml into
 * arena-app, rebake _webui (`fieldkit arena build --repo-root arena-app`),
 * refresh the mirror (`fieldkit arena mirror --repo-root arena-app`).
 */
import { readdir, readFile } from 'node:fs/promises';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const repoRoot = join(dirname(fileURLToPath(import.meta.url)), '..');
const canonicalDir = join(repoRoot, 'src', 'content', 'artifacts');
const arenaDir = join(repoRoot, 'arena-app', 'src', 'content', 'artifacts');

const yamlsIn = async (dir) =>
  (await readdir(dir)).filter((f) => f.endsWith('.yaml') || f.endsWith('.yml')).sort();

const canonical = await yamlsIn(canonicalDir);
const arena = await yamlsIn(arenaDir);

const failures = [];

for (const name of canonical) {
  if (!arena.includes(name)) {
    failures.push(`MISSING in arena-app: ${name}`);
    continue;
  }
  const [a, b] = await Promise.all([
    readFile(join(canonicalDir, name)),
    readFile(join(arenaDir, name)),
  ]);
  if (!a.equals(b)) failures.push(`DRIFTED (bytes differ): ${name}`);
}

for (const name of arena) {
  if (!canonical.includes(name)) failures.push(`ORPHAN in arena-app (no canonical source): ${name}`);
}

if (failures.length) {
  console.error(`verify_arena_catalog_sync: ${failures.length} manifest(s) out of sync\n`);
  for (const f of failures) console.error(`  ✗ ${f}`);
  console.error(
    '\nFix: cp src/content/artifacts/<name>.yaml arena-app/src/content/artifacts/,' +
      ' then rebake _webui + refresh the mirror.'
  );
} else {
  console.log(
    `verify_arena_catalog_sync: OK — ${canonical.length} manifests byte-identical across both copies`
  );
}
process.exit(failures.length);
