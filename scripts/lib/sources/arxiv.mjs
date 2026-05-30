// arxiv.org Atom API — public, no auth.
// Docs: https://info.arxiv.org/help/api/user-manual.html

import { setDefaultResultOrder } from 'node:dns';

// arxiv.org's AAAA records are unstable on the Spark's network path; force
// IPv4 to avoid `EAI_AGAIN` on the DNS lookup. Module-scoped so callers don't
// need to set NODE_OPTIONS=--dns-result-order=ipv4first.
try { setDefaultResultOrder('ipv4first'); } catch { /* node < 18 fallback */ }

const ATOM_NS = 'http://www.w3.org/2005/Atom';
const ARXIV_NS = 'http://arxiv.org/schemas/atom';

const CATEGORIES = ['cs.LG', 'cs.CL', 'cs.AI', 'cs.CV', 'cs.IR', 'cs.DC', 'stat.ML'];

function pickTag(xml, tag, after = 0) {
  const open = xml.indexOf(`<${tag}`, after);
  if (open === -1) return null;
  const close = xml.indexOf(`</${tag}>`, open);
  if (close === -1) return null;
  const inner = xml.slice(xml.indexOf('>', open) + 1, close);
  return { inner, end: close + tag.length + 3 };
}

function pickAttr(tagText, attr) {
  const re = new RegExp(`${attr}="([^"]*)"`);
  const m = tagText.match(re);
  return m ? m[1] : null;
}

function decodeEntities(s) {
  return s
    .replace(/&amp;/g, '&')
    .replace(/&lt;/g, '<')
    .replace(/&gt;/g, '>')
    .replace(/&quot;/g, '"')
    .replace(/&#39;/g, "'");
}

function parseEntries(xml) {
  const entries = [];
  let cursor = 0;
  while (true) {
    const e = pickTag(xml, 'entry', cursor);
    if (!e) break;
    cursor = e.end;
    const block = e.inner;

    const idTag = pickTag(block, 'id');
    if (!idTag) continue;
    const idUrl = idTag.inner.trim(); // http://arxiv.org/abs/2511.12345v1
    const arxivIdRaw = idUrl.split('/abs/')[1] || '';
    const arxiv_id = arxivIdRaw.replace(/v\d+$/, '');

    const title = (pickTag(block, 'title')?.inner || '').replace(/\s+/g, ' ').trim();
    const summary = (pickTag(block, 'summary')?.inner || '').replace(/\s+/g, ' ').trim();
    const published = (pickTag(block, 'published')?.inner || '').trim();
    const updated = (pickTag(block, 'updated')?.inner || '').trim();

    // Authors — repeat <author><name>X</name></author>
    const authors = [];
    let aCursor = 0;
    while (true) {
      const a = pickTag(block, 'author', aCursor);
      if (!a) break;
      aCursor = a.end;
      const nm = pickTag(a.inner, 'name');
      if (nm) authors.push(nm.inner.trim());
    }

    // Primary category — <arxiv:primary_category term="cs.LG"/>
    const primaryMatch = block.match(/<arxiv:primary_category[^/]*\/>/);
    const primary_category = primaryMatch ? pickAttr(primaryMatch[0], 'term') : null;

    // Links — abs + pdf
    const links = [...block.matchAll(/<link[^/]*\/>/g)].map((m) => m[0]);
    const abs_url = links.map((l) => pickAttr(l, 'href')).find((h) => h && h.includes('/abs/')) || `https://arxiv.org/abs/${arxiv_id}`;
    const pdf_url = links.map((l) => pickAttr(l, 'href')).find((h) => h && h.includes('/pdf/')) || `https://arxiv.org/pdf/${arxiv_id}`;

    entries.push({
      arxiv_id,
      title: decodeEntities(title),
      authors,
      abstract: decodeEntities(summary),
      published,
      updated,
      primary_category,
      abs_url,
      pdf_url,
    });
  }
  return entries;
}

/**
 * Fetch the most recent N papers across the project's relevant arxiv categories.
 * Sorted by submission date desc.
 */
export async function fetchRecentArxiv({ maxResults = 100, categories = CATEGORIES, retries = 4 } = {}) {
  const search_query = categories.map((c) => `cat:${c}`).join('+OR+');
  const url = `https://export.arxiv.org/api/query?search_query=${search_query}&sortBy=submittedDate&sortOrder=descending&max_results=${maxResults}`;
  let lastErr = null;
  for (let i = 0; i < retries; i++) {
    try {
      const res = await fetch(url, { headers: { 'User-Agent': 'frontier-scout/0.1 (ai-field-notes)' } });
      if (res.status === 429 || res.status >= 500) {
        const wait = 3000 * (i + 1);
        await new Promise((r) => setTimeout(r, wait));
        continue;
      }
      if (!res.ok) throw new Error(`arxiv: HTTP ${res.status}`);
      const xml = await res.text();
      return parseEntries(xml);
    } catch (e) {
      lastErr = e;
      // DNS / network errors get a longer backoff than HTTP errors do
      const isDns = e?.cause?.code === 'EAI_AGAIN' || e?.cause?.code === 'ENOTFOUND';
      await new Promise((r) => setTimeout(r, isDns ? 4000 * (i + 1) : 2000));
    }
  }
  throw lastErr || new Error('arxiv: exhausted retries');
}
