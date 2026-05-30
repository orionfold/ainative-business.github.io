// Build-time helper: parses an article's raw markdown, runs the same
// remark-directive + remark-explainers pipeline that the page render uses,
// and pulls out every :::define[term] block as a structured glossary entry.
//
// Used by:
//   - TermsInThisPiece.astro  → per-article "terms in this piece" collapsible
//   - /glossary/index.astro   → site-wide alphabetized index
//
// Returning plain-text definitions on purpose: explainer bodies are short
// (one or two sentences); plain text avoids dragging marked or another
// renderer into the build for cosmetic markup that won't matter in a
// glossary index. If we ever want rich definitions, swap mdastToString for
// a remark-stringify or remark-rehype pass here only.

import { unified } from 'unified';
import remarkParse from 'remark-parse';
import remarkDirective from 'remark-directive';
import remarkExplainers from './remark-explainers.mjs';

const processor = unified()
  .use(remarkParse)
  .use(remarkDirective)
  .use(remarkExplainers);

// Extract glossary entries from a single article body. Returns
// [{term, anchor, definitionText}, ...] in document order.
export function extractGlossaryEntries(body) {
  if (!body || typeof body !== 'string') return [];
  const file = { value: body, data: {} };
  const tree = processor.parse(file);
  processor.runSync(tree, file);
  return Array.isArray(file.data?.glossaryEntries) ? file.data.glossaryEntries : [];
}

// Collect entries across many articles. Each input has shape
// `{slug, title, body}`. Returns a flat array enriched with slug/title.
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

// Group + dedupe for the site-wide /glossary/ page. If a term appears in
// multiple articles, the first occurrence (by article order in input) wins
// for the canonical anchor; remaining sightings show up as "also in" links.
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
  // Sort alphabetically by term, case-insensitive.
  const sorted = Array.from(byTerm.values()).sort((a, b) =>
    a.term.toLowerCase().localeCompare(b.term.toLowerCase()),
  );
  return sorted;
}
