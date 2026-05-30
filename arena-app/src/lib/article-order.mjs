import { execSync } from 'node:child_process';

// Map article id → ordinal. Published articles are numbered 1..N by first-add
// commit time (oldest = №01). Upcoming placeholders get ordinal 0 — they
// render as "Upcoming" in the UI, not as a number, so they must not consume
// ordinals or the published sequence grows gaps (e.g. №10 → №15).
// Date frontmatter alone isn't granular enough — multiple articles often
// share a publish day, making a date-only sort unstable.
export function publishOrdinals(articles, projectRoot) {
  const firstAddTs = new Map();
  try {
    const out = execSync(
      "git log --diff-filter=A --name-only --pretty=format:%at --reverse -- 'articles/*/article.md'",
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
    // Not a git checkout (e.g. tarball build). Fall back to date-only order.
  }

  const result = new Map();
  const published = articles
    .filter((a) => a.data.status !== 'upcoming')
    .map((a) => ({
      article: a,
      ts: firstAddTs.get(`articles/${a.id}/article.md`) ?? a.data.date.getTime() / 1000,
    }));
  published.sort((x, y) => x.ts - y.ts || x.article.id.localeCompare(y.article.id));
  published.forEach((d, i) => result.set(d.article.id, i + 1));

  // Upcoming placeholders: ordinal 0. Display paths branch on `isUpcoming`
  // before reading the number, so this is never rendered.
  for (const a of articles) {
    if (a.data.status === 'upcoming') result.set(a.id, 0);
  }
  return result;
}
