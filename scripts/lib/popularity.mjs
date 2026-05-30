// Composite popularity score in 0..100 from heterogeneous signals.
// We weight HF upvotes most (best leading indicator), then repo stars, then
// citations, with a recency decay so 6-month-old hits don't dominate the page.

const NOW = Date.now();
const DAY = 86400_000;

export function popularityScore({ hf_upvotes = 0, repos = [], citations = 0, published }) {
  const stars = repos.reduce((m, r) => Math.max(m, r.stars || 0), 0);
  // log-scale each signal so a single 10k-star repo doesn't pin the ceiling
  const upvoteN = hf_upvotes ? Math.log10(hf_upvotes + 1) / Math.log10(500) : 0;       // 500 upvotes = 1.0
  const starsN = stars ? Math.log10(stars + 1) / Math.log10(20000) : 0;                // 20k stars = 1.0
  const citeN = citations ? Math.log10(citations + 1) / Math.log10(2000) : 0;          // 2k citations = 1.0

  let recencyMul = 1;
  if (published) {
    const ageDays = (NOW - new Date(published).getTime()) / DAY;
    if (ageDays > 0) recencyMul = Math.exp(-ageDays / 90); // half-life ~63 days
  }

  const raw = (0.5 * upvoteN + 0.3 * starsN + 0.2 * citeN) * recencyMul;
  return Math.round(Math.max(0, Math.min(1, raw)) * 100);
}
