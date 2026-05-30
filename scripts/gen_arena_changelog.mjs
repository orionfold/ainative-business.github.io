#!/usr/bin/env node
// gen_arena_changelog.mjs — build the "built together" timeline for /arena/lab/.
//
// Deterministic build step (Phase 6): walks `git log --grep '^arena:'` and
// writes a compact `src/data/arena-changelog.json` the Lab board reads at build
// time. Committed to the repo so the public-mirror build (which may not have
// full git history / the same grep) reads identical data — same contract as
// `src/data/arena-mirror/leaderboard.json`.
//
// Run from the repo root:  node scripts/gen_arena_changelog.mjs
// Re-run whenever a new `arena:` commit lands (and at each fieldkit release cut).

import { execFileSync } from 'node:child_process';
import { writeFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const repoRoot = join(dirname(fileURLToPath(import.meta.url)), '..');
const OUT = join(repoRoot, 'src', 'data', 'arena-changelog.json');

// Unit separator between fields, record separator between commits — robust
// against subjects containing any normal punctuation.
const FMT = '%H%x1f%aI%x1f%s';

let raw = '';
try {
  raw = execFileSync(
    'git',
    ['log', '--grep=^arena:', '--date-order', `--pretty=format:${FMT}`],
    { cwd: repoRoot, encoding: 'utf8', maxBuffer: 8 * 1024 * 1024 },
  );
} catch (err) {
  console.error('git log failed:', err.message);
  process.exit(1);
}

const entries = raw
  .split('\n')
  .filter(Boolean)
  .map((line) => {
    const [hash, dateISO, subject] = line.split('\x1f');
    // Strip the leading "arena: " prefix for the display title.
    const title = subject.replace(/^arena:\s*/, '');
    return {
      hash: hash.slice(0, 8),
      date: dateISO.slice(0, 10),
      title,
    };
  });

const payload = {
  generated_from: 'git log --grep ^arena:',
  count: entries.length,
  entries, // newest first (git default order)
};

writeFileSync(OUT, JSON.stringify(payload, null, 2) + '\n', 'utf8');
console.log(`wrote ${entries.length} arena commits → ${OUT}`);
