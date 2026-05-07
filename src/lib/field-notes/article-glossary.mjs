// Build-time helper: parses an article's raw markdown, runs the same
// remark-directive + remark-explainers pipeline that the page render uses,
// and pulls out every :::define[term] block as a structured glossary entry.
//
// Used by:
//   - TermsInThisPiece.astro  → per-article "terms in this piece" collapsible
//   - /glossary/index.astro   → site-wide alphabetized index

import { unified } from 'unified';
import remarkParse from 'remark-parse';
import remarkDirective from 'remark-directive';
import remarkExplainers from './remark-explainers.mjs';

const processor = unified()
  .use(remarkParse)
  .use(remarkDirective)
  .use(remarkExplainers);

export function extractGlossaryEntries(body) {
  if (!body || typeof body !== 'string') return [];
  const file = { value: body, data: {} };
  const tree = processor.parse(file);
  processor.runSync(tree, file);
  return Array.isArray(file.data?.glossaryEntries) ? file.data.glossaryEntries : [];
}

export function collectGlossaryAcrossArticles(articles) {
  const all = [];
  for (const a of articles) {
    const entries = extractGlossaryEntries(a.body);
    for (const e of entries) {
      all.push({ ...e, slug: a.slug, title: a.title });
    }
  }
  return all;
}

export function buildSiteGlossary(articles) {
  const collected = collectGlossaryAcrossArticles(articles);
  const byTerm = new Map();
  for (const e of collected) {
    const key = e.term.toLowerCase();
    const existing = byTerm.get(key);
    if (!existing) {
      byTerm.set(key, {
        term: e.term,
        canonical: { slug: e.slug, title: e.title, anchor: e.anchor, definitionText: e.definitionText },
        alsoIn: [],
      });
    } else {
      existing.alsoIn.push({ slug: e.slug, title: e.title, anchor: e.anchor });
    }
  }
  const sorted = Array.from(byTerm.values()).sort((a, b) =>
    a.term.toLowerCase().localeCompare(b.term.toLowerCase()),
  );
  return sorted;
}
