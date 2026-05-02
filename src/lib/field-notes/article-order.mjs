import { execFileSync } from 'node:child_process';

// Map article id → ordinal. Published articles are numbered 1..N by first-add
// commit time (oldest = №01). Upcoming placeholders get ordinal 0 — they
// render as "Upcoming" in the UI, not as a number.
//
// Frontmatter `ordinal` overrides the derivation. The two reframed research
// papers (ai-transformation, solo-builder-case-study) use this to claim
// №01 and №02 in the AI Native Platform series; their git first-add time
// would otherwise place them late in the global ordering.
//
// execFileSync (not exec) is used so no shell is spawned — git args are
// passed as an array, the command string isn't interpolated.
export function publishOrdinals(articles, projectRoot) {
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

  // Two-pass ordinal assignment so frontmatter overrides take their fixed slot
  // and everyone else fills the gaps. The two reframed research papers claim
  // №01 and №02 explicitly; the original 33 field-note articles fill the rest.
  const result = new Map();
  const explicit = new Map();
  for (const a of articles.filter((a) => a.data.status !== 'upcoming')) {
    if (a.data.ordinal !== undefined) {
      explicit.set(a.id, a.data.ordinal);
    }
  }
  const taken = new Set(explicit.values());
  let next = 1;
  for (const { article } of published) {
    if (explicit.has(article.id)) {
      result.set(article.id, explicit.get(article.id));
      continue;
    }
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
