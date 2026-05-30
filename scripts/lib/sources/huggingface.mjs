// HuggingFace daily-papers API — community-curated trending papers with upvote count.
// Endpoint: https://huggingface.co/api/daily_papers (returns ~30 most-recent days)

/**
 * Fetch HF daily papers; flatten across the last `days` cohorts.
 * Each entry includes `paper.upvotes`, `paper.title`, `paper.summary`,
 * `paper.id` (arxiv id), and submission metadata.
 */
export async function fetchHuggingFaceDailyPapers({ days = 30 } = {}) {
  const url = `https://huggingface.co/api/daily_papers`;
  const res = await fetch(url, { headers: { 'User-Agent': 'frontier-scout/0.1 (ai-field-notes)' } });
  if (!res.ok) throw new Error(`hf daily papers: HTTP ${res.status}`);
  const data = await res.json();

  const cutoff = new Date(Date.now() - days * 86400_000);
  const out = [];
  for (const entry of data) {
    const submittedAt = entry.publishedAt ? new Date(entry.publishedAt) : null;
    if (submittedAt && submittedAt < cutoff) continue;
    const p = entry.paper || {};
    if (!p.id) continue;
    out.push({
      arxiv_id: p.id,
      title: p.title || '',
      abstract: p.summary || '',
      hf_upvotes: typeof p.upvotes === 'number' ? p.upvotes : 0,
      hf_paper_url: `https://huggingface.co/papers/${p.id}`,
      published: submittedAt ? submittedAt.toISOString() : null,
    });
  }
  return out;
}
