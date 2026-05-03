import { execFileSync } from 'node:child_process';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';

// Map article id → ordinal. Published articles are numbered 1..N to match the
// source repo's authoring order (oldest = №01). Upcoming placeholders get
// ordinal 0 — they render as "Upcoming" in the UI, not as a number, so they
// must not consume ordinal slots or the published sequence grows gaps.
//
// Frontmatter `ordinal` overrides the derivation. The two reframed research
// papers (ai-transformation, solo-builder-case-study) use this to claim №01
// and №02 in the AI Native Platform series; they live only on the website
// and aren't in the source's authoring sequence.
//
// Ordering source of truth, in priority order:
//   1. src/data/field-notes/sequence.json — written by the sync skill from
//      the source repo's git first-add timestamps. This is the canonical
//      sequence: the website's №03..№N tracks ai-field-notes' №01..№N.
//   2. This repo's own git log — fallback when the manifest is missing
//      (fresh clone before a sync, manual content edits, etc.). Less
//      reliable: bulk syncs collapse many articles into a single commit
//      window and ties resolve alphabetically.
//   3. Frontmatter `date` — last-resort fallback when neither git source
//      is available. Day-granularity, so ties are common.
export function publishOrdinals(articles, projectRoot) {
  const explicit = new Map();
  for (const a of articles) {
    if (a.data.status !== 'upcoming' && a.data.ordinal !== undefined) {
      explicit.set(a.id, a.data.ordinal);
    }
  }

  const sequence = readSequenceManifest(projectRoot);
  if (sequence) {
    return assignFromSequence(articles, explicit, sequence);
  }
  return deriveFromLocalGit(articles, explicit, projectRoot);
}

function readSequenceManifest(projectRoot) {
  try {
    const raw = readFileSync(
      join(projectRoot, 'src/data/field-notes/sequence.json'),
      'utf8',
    );
    const parsed = JSON.parse(raw);
    if (Array.isArray(parsed.sequence) && parsed.sequence.every((s) => typeof s === 'string')) {
      return parsed.sequence;
    }
  } catch {
    // Manifest missing or malformed — caller falls back to local git.
  }
  return null;
}

function assignFromSequence(articles, explicit, sequence) {
  // An article can be present in the source's git history (so it lands in
  // the manifest) yet still carry `status: upcoming` in frontmatter — these
  // are planned outlines that source committed as article.md to reserve
  // their place but haven't been written yet. They must NOT consume a
  // published ordinal, or the №NN sequence on the website grows gaps where
  // the upcoming articles render as "Upcoming" instead of a number.
  const upcomingIds = new Set(
    articles.filter((a) => a.data.status === 'upcoming').map((a) => a.id),
  );

  const result = new Map();
  const taken = new Set(explicit.values());
  for (const [id, ord] of explicit) result.set(id, ord);

  let next = 1;
  for (const slug of sequence) {
    if (explicit.has(slug)) continue;
    if (upcomingIds.has(slug)) continue;
    while (taken.has(next)) next++;
    result.set(slug, next);
    taken.add(next);
    next++;
  }

  // Articles on disk that aren't in the manifest and have no explicit
  // override: append in alphabetical order with a build-time warning.
  // This catches drift (a new article exists locally but the manifest
  // hasn't been refreshed via sync yet) without breaking the build.
  const orphans = articles
    .filter((a) => a.data.status !== 'upcoming' && !result.has(a.id))
    .map((a) => a.id)
    .sort();
  if (orphans.length > 0) {
    console.warn(
      `[field-notes] ${orphans.length} published article(s) not in sequence manifest — ` +
        `appended alphabetically: ${orphans.join(', ')}. ` +
        `Re-run the sync-field-notes skill to refresh src/data/field-notes/sequence.json.`,
    );
    for (const slug of orphans) {
      while (taken.has(next)) next++;
      result.set(slug, next);
      taken.add(next);
      next++;
    }
  }

  for (const a of articles) {
    if (a.data.status === 'upcoming') result.set(a.id, 0);
  }
  return result;
}

// Fallback path — kept identical to the pre-manifest behavior so the
// website still renders correctly in environments where the manifest
// hasn't been generated yet (e.g., a fresh checkout).
//
// execFileSync (not exec) is used so no shell is spawned — git args pass as
// an array, the command string isn't interpolated.
function deriveFromLocalGit(articles, explicit, projectRoot) {
  const firstAddTs = new Map();
  try {
    const out = execFileSync(
      'git',
      [
        'log',
        '--diff-filter=A',
        '--name-only',
        '--pretty=format:%at',
        '--reverse',
        '--',
        'articles/*/article.md',
        'articles/*/article.mdx',
      ],
      { cwd: projectRoot, encoding: 'utf8' },
    );
    let currentTs = null;
    for (const line of out.split('\n')) {
      const trimmed = line.trim();
      if (!trimmed) { currentTs = null; continue; }
      if (/^\d+$/.test(trimmed)) { currentTs = Number(trimmed); continue; }
      if (currentTs !== null && !firstAddTs.has(trimmed)) {
        firstAddTs.set(trimmed, currentTs);
      }
    }
  } catch {
    // Not a git checkout, or no matching paths yet. Fall back to date-only order.
  }

  const published = articles
    .filter((a) => a.data.status !== 'upcoming')
    .map((a) => ({
      article: a,
      ts: firstAddTs.get(`articles/${a.id}/article.md`)
        ?? firstAddTs.get(`articles/${a.id}/article.mdx`)
        ?? a.data.date.getTime() / 1000,
    }));

  published.sort((x, y) => x.ts - y.ts || x.article.id.localeCompare(y.article.id));

  const result = new Map();
  const taken = new Set(explicit.values());
  for (const [id, ord] of explicit) result.set(id, ord);
  let next = 1;
  for (const { article } of published) {
    if (explicit.has(article.id)) continue;
    while (taken.has(next)) next++;
    result.set(article.id, next);
    taken.add(next);
    next++;
  }

  for (const a of articles) {
    if (a.data.status === 'upcoming') result.set(a.id, 0);
  }
  return result;
}
