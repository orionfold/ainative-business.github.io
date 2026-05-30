// Paper → repo discovery.
//
// Historical: this module hit the Papers-with-Code public API
// (https://paperswithcode.com/api/v1/papers/?arxiv_id=<id>). That API was
// retired in 2026 — the host now 302-redirects to huggingface.co/papers/trending
// and never returns JSON. We keep the same export signature so callers don't
// change, but the implementation now has two stages:
//
//   1. Try PWC. If it's actually reachable again someday, prefer it.
//   2. Fall back to scraping github.com/<owner>/<repo> URLs out of the arXiv
//      abstract HTML — most AI papers link their repo from the abstract page.
//
// Returns the same shape as before:
//   { paper_url: string|null, repos: [{ url, stars, framework, is_official }] }
// or null on hard miss.

import { setDefaultResultOrder } from 'node:dns';

// Same DNS-stability fix used by arxiv.mjs — both export.arxiv.org and arxiv.org
// have flaky AAAA records from the Spark's network path.
try { setDefaultResultOrder('ipv4first'); } catch { /* node < 18 fallback */ }

const UA = 'frontier-scout/0.2 (ai-field-notes)';

async function tryPwcApi(arxivId) {
  const lookupUrl = `https://paperswithcode.com/api/v1/papers/?arxiv_id=${encodeURIComponent(arxivId)}`;
  let res;
  try {
    // `redirect: manual` so we can detect the dead-API 302 → HF without
    // accidentally following it and parsing HF's HTML as JSON.
    res = await fetch(lookupUrl, {
      redirect: 'manual',
      headers: { Accept: 'application/json', 'User-Agent': UA },
    });
  } catch {
    return null;
  }
  if (res.status >= 300 && res.status < 400) return null; // API retired
  if (!res.ok) return null;
  const ct = res.headers.get('content-type') || '';
  if (!ct.includes('application/json')) return null;
  const data = await res.json().catch(() => null);
  const paper = data?.results?.[0];
  if (!paper?.id) return null;

  const reposUrl = `https://paperswithcode.com/api/v1/papers/${paper.id}/repositories/`;
  const r2 = await fetch(reposUrl, {
    redirect: 'manual',
    headers: { Accept: 'application/json', 'User-Agent': UA },
  }).catch(() => null);
  if (!r2 || !r2.ok) return { paper_url: paper.url_abs || null, repos: [] };
  const ct2 = r2.headers.get('content-type') || '';
  if (!ct2.includes('application/json')) return { paper_url: paper.url_abs || null, repos: [] };
  const reposData = await r2.json().catch(() => null);
  const repos = (reposData?.results || [])
    .map((r) => ({
      url: r.url || null,
      stars: typeof r.stars === 'number' ? r.stars : 0,
      framework: r.framework || null,
      is_official: !!r.is_official,
    }))
    .filter((r) => r.url);

  return { paper_url: paper.url_abs || null, repos };
}

function extractGithubLinks(text) {
  if (!text) return [];
  const found = new Set();
  const re = /https?:\/\/github\.com\/([\w.-]+)\/([\w.-]+)/gi;
  // Owner segments that are clearly GitHub product pages, not real repos
  const reservedOwners = new Set(['blog', 'about', 'features', 'pricing', 'login', 'sponsors']);
  let m;
  while ((m = re.exec(text)) !== null) {
    const owner = m[1];
    let repo = m[2].replace(/\.git$/, '').replace(/[).,;:"'<>]+$/, '');
    if (!owner || !repo || repo.length < 2) continue;
    if (reservedOwners.has(owner.toLowerCase())) continue;
    found.add(`https://github.com/${owner}/${repo}`);
  }
  return [...found];
}

async function fetchAbstractHtml(arxivId) {
  try {
    const res = await fetch(`https://arxiv.org/abs/${arxivId}`, {
      headers: { 'User-Agent': UA },
    });
    if (!res.ok) return '';
    return await res.text();
  } catch {
    return '';
  }
}

async function fallbackFromArxiv(arxivId) {
  const html = await fetchAbstractHtml(arxivId);
  if (!html) return null;
  const urls = extractGithubLinks(html).slice(0, 3);
  if (!urls.length) return { paper_url: `https://arxiv.org/abs/${arxivId}`, repos: [] };
  return {
    paper_url: `https://arxiv.org/abs/${arxivId}`,
    repos: urls.map((url) => ({ url, stars: 0, framework: null, is_official: true })),
  };
}

/**
 * Look up the official + community repos linked to an arxiv paper.
 * Returns { paper_url, repos: [{ url, stars, framework, is_official }] } or null on miss.
 *
 * The returned repos lack live metadata (stars/forks/last_commit). Callers should
 * pipe each url through `fetchGitHubRepoMeta(url)` from `./github.mjs` to enrich.
 */
export async function fetchPapersWithCodeRepos(arxivId) {
  const fromApi = await tryPwcApi(arxivId);
  if (fromApi) return fromApi;
  return await fallbackFromArxiv(arxivId);
}
