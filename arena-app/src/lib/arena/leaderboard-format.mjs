// Shared leaderboard cell formatters — used by the static SSR table in
// leaderboard.astro and the live <LiveLeaderboard> island so the two render
// identically. Pure functions, no DOM / browser deps.

export const pct = (s) => (s * 100).toFixed(1);
export const fmtTok = (n) => (n == null ? '—' : Number(n).toFixed(1));
export const fmtTtft = (n) => (n == null ? '—' : `${Number(n).toFixed(0)} ms`);
export const fmtPref = (n) => (n == null ? '—' : `${(n * 100).toFixed(0)}%`);

// Lanes can carry a `local:` serving-prefix on some chat rows but not others —
// strip it so the model name reads identically everywhere.
const stripLanePrefix = (id) => String(id || '').replace(/^local:/, '');
// Trailing `::token`. Two shapes share this slot: the live table's uppercase
// quant tag (Q4_K_M, Q8_0, F16) and the bench table's kebab manifest slug
// (…::hermes-vertical-router-on-spark). One class — uppercase, digits, `_`,
// `-` — covers both. Cloud lanes (`openrouter::owner/model`) have `/` after the
// `::` so they never match this end-anchored class and are left intact.
const TAIL_SUFFIX = /::([A-Za-z0-9_-]+)$/;
export const laneLabel = (id) => stripLanePrefix(id).replace(TAIL_SUFFIX, '');
export const laneSuffix = (id) => {
  const m = stripLanePrefix(id).match(TAIL_SUFFIX);
  return m ? m[1] : '';
};
// Where the lane ran — cloud (OpenRouter) vs local (DGX Spark). Rendered as a
// badge instead of an `openrouter::` prefix / no marker at all. Reads the RAW id.
export const laneSource = (id) => (/^openrouter/.test(String(id || '')) ? 'openrouter' : 'spark');
// Model name for the source-badged live table — drops the cloud prefix since
// the badge carries that signal: `openrouter::owner/model` → `owner/model`,
// `openrouter-frontier` → `frontier`. The bench table keeps prefix-aware laneLabel.
export const laneModel = (id) => laneLabel(id).replace(/^openrouter(::|-)/, '');
export const benchLabel = (id) => String(id || '').replace(/^cockpit:/, '');

export const scoreColor = (s) => {
  // OKLCH so the inline style scales cleanly against the design system.
  if (s == null) return 'oklch(0.55 0 0)'; // neutral grey — throughput-only row
  if (s >= 0.9) return 'oklch(0.78 0.18 155)'; // green
  if (s >= 0.75) return 'oklch(0.72 0.18 250)'; // blue
  if (s >= 0.5) return 'oklch(0.83 0.16 78)'; // amber
  return 'oklch(0.68 0.22 25)'; // red
};

// Quality desc (null — throughput-only — sinks to the bottom), tok/s tiebreak.
export function sortLiveRows(rows) {
  return [...rows].sort((a, b) => {
    const as = a.mean_score == null ? -1 : a.mean_score;
    const bs = b.mean_score == null ? -1 : b.mean_score;
    if (bs !== as) return bs - as;
    return (b.median_tok_per_s ?? 0) - (a.median_tok_per_s ?? 0);
  });
}
