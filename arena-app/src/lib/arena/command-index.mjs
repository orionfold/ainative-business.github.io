// Build-time command index for the ⌘K palette.
//
// Called from ArenaAppLayout frontmatter with the already-fetched collections
// (the layout owns the `getCollection` + leaderboard import; this helper stays
// pure so it's trivially testable and has no `astro:content` dependency). The
// result is serialized into the CommandPalette island as a prop, so fuzzy
// search works with zero network — it survives on the public mirror.
//
// Entry shape: { id, type, label, sub, href, keywords }
//   type ∈ 'page' | 'model' | 'article' | 'lane'
//   href is already base-resolved (the caller passes its `href()` helper).
//   keywords is a pre-lowercased haystack for the matcher.

const PAGES = [
  { id: 'page:cockpit', label: 'Cockpit', sub: 'live telemetry + top runs', path: 'arena/' },
  { id: 'page:models', label: 'Models', sub: 'capability browser', path: 'arena/models/' },
  { id: 'page:leaderboard', label: 'Leaderboard', sub: 'efficiency frontier + ranks', path: 'arena/leaderboard/' },
  { id: 'page:chat', label: 'Chat', sub: 'against the resident brain', path: 'arena/chat/' },
  { id: 'page:compare', label: 'Compare', sub: 'side-by-side rubric scoring', path: 'arena/compare/' },
  { id: 'page:lab', label: 'Lab', sub: 'what we are building next', path: 'arena/lab/' },
  { id: 'page:settings', label: 'Settings', sub: 'cloud-eval guardrail config', path: 'arena/settings/' },
];

// Strip the `::variant`/`::suffix` tail the importer appends to lane ids.
function laneLabel(laneId) {
  return String(laneId || '').replace(/::[a-z0-9-]+$/i, '');
}

/**
 * @param {object} opts
 * @param {Array} opts.articles   getCollection('articles') entries
 * @param {Array} opts.artifacts  getCollection('artifacts') entries
 * @param {object} opts.leaderboard  the arena-mirror leaderboard.json
 * @param {(path: string) => string} opts.href  base-resolver from the layout
 * @returns {Array} flat command index
 */
export function buildCommandIndex({ articles = [], artifacts = [], leaderboard = {}, href = (p) => `/${p}` }) {
  const out = [];

  for (const p of PAGES) {
    out.push({
      id: p.id,
      type: 'page',
      label: p.label,
      sub: p.sub,
      href: href(p.path),
      keywords: `${p.label} ${p.sub}`.toLowerCase(),
    });
  }

  for (const a of artifacts) {
    const d = a.data || {};
    const label = d.positioning?.headline || d.slug || a.id;
    const sub = [d.kind, d.base_model].filter(Boolean).join(' · ');
    out.push({
      id: `model:${a.id}`,
      type: 'model',
      label,
      sub,
      href: href(`arena/models/${a.id}/`),
      keywords: `${label} ${d.slug || ''} ${d.base_model || ''} ${d.kind || ''} ${d.vertical_eval_name || ''} ${(d.positioning?.use_cases || []).join(' ')}`.toLowerCase(),
    });
  }

  for (const a of articles) {
    const d = a.data || {};
    if (d.status === 'upcoming') continue;
    out.push({
      id: `article:${a.id}`,
      type: 'article',
      label: d.title || a.id,
      sub: [d.stage, d.series].filter(Boolean).join(' · '),
      href: href(`articles/${a.id}/`),
      keywords: `${d.title || ''} ${a.id} ${d.stage || ''} ${d.series || ''} ${(d.tags || []).join(' ')}`.toLowerCase(),
    });
  }

  // Lanes that carry a real score — dedupe by display label, keep the best.
  const benchRows = leaderboard.bench_rows || leaderboard.rows || [];
  const liveRows = leaderboard.live_rows || [];
  const seen = new Set();
  for (const r of [...liveRows, ...benchRows]) {
    const label = laneLabel(r.lane_id);
    if (!label || seen.has(label)) continue;
    seen.add(label);
    out.push({
      id: `lane:${r.lane_id}`,
      type: 'lane',
      label,
      sub: `leaderboard · ${(r.mean_score * 100).toFixed(0)}% quality`,
      href: href('arena/leaderboard/'),
      keywords: `${label} ${r.bench_id || ''} leaderboard lane`.toLowerCase(),
    });
  }

  return out;
}
