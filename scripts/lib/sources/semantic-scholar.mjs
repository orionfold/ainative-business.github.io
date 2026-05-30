// Semantic Scholar Graph API — citation count for an arxiv paper.
// Public, unauthenticated; rate-limited so callers should batch and sleep.

export async function fetchSemanticScholarCitations(arxivId) {
  const url = `https://api.semanticscholar.org/graph/v1/paper/arXiv:${encodeURIComponent(arxivId)}?fields=citationCount,influentialCitationCount`;
  try {
    const res = await fetch(url, { headers: { 'User-Agent': 'frontier-scout/0.1' } });
    if (!res.ok) return null;
    const data = await res.json();
    return {
      citations: data.citationCount ?? null,
      influential_citations: data.influentialCitationCount ?? null,
    };
  } catch {
    return null;
  }
}
