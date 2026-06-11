// Shared leaderboard cell formatters — used by the static SSR table in
// leaderboard.astro and the live <LiveLeaderboard> island so the two render
// identically. Pure functions, no DOM / browser deps.

export const pct = (s) => (s * 100).toFixed(1);
export const fmtTok = (n) => (n == null ? '—' : Number(n).toFixed(1));
export const fmtTtft = (n) => (n == null ? '—' : `${Number(n).toFixed(0)} ms`);
export const fmtPref = (n) => (n == null ? '—' : `${(n * 100).toFixed(0)}%`);

// M9 (Bet 6 — cost plane): the $/task + $/quality-point cells. A local lane
// (mean_cost_usd === 0) renders "$0 (local)" rather than a divide-by-zero "—",
// matching fieldkit.cost._format_cost_per_quality (M9-4). An unpriced/unscored
// lane (null) renders "—".
export const fmtCost = (n) => {
  if (n == null) return '—';
  const v = Number(n);
  if (v === 0) return '$0';
  return v < 0.01 ? `$${v.toFixed(4)}` : `$${v.toFixed(3)}`;
};
export const fmtCostPerQuality = (meanCost, cpq) => {
  if (meanCost != null && Number(meanCost) === 0) return '$0 (local)';
  if (cpq == null) return '—';
  return `$${Number(cpq).toFixed(4)}/pt`;
};
// Live spend rail (the running session total survives a sidecar restart, M9-8).
export const fmtSpend = (n) => {
  const v = Number(n || 0);
  return v < 0.01 ? `$${v.toFixed(4)}` : `$${v.toFixed(2)}`;
};

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
// Some early eval rows carry un-prefixed cloud ids (`claude-haiku-45`) — catch
// the obvious frontier-model names so a cloud run never badges as "Spark GPU".
export const laneSource = (id) =>
  /^(openrouter|claude|gpt-|gemini|anthropic\/|openai\/)/.test(String(id || '')) ? 'openrouter' : 'spark';
// Model name for the source-badged live table — drops the cloud prefix since
// the badge carries that signal: `openrouter::owner/model` → `owner/model`,
// `openrouter-frontier` → `frontier`. The bench table keeps prefix-aware laneLabel.
export const laneModel = (id) => laneLabel(id).replace(/^openrouter(::|-)/, '');
export const benchLabel = (id) => String(id || '').replace(/^cockpit:/, '');

// ---- Advisor display layer -------------------------------------------------
// The advisor_contract bench rows carry receipt-shaped ids
// (`4b-sft-v0.2::curveball-v0.2::the-refusal-floor-is-trainable`) that are
// exact but cryptic. These helpers translate them for the operator WITHOUT
// touching the data: the raw lane id is always returned alongside and the
// caller keeps it visible as the secondary line (report = reality).
// Matches both the bench-anchored id and a future live tier
// (`cockpit:advisor_contract`).
export const isAdvisorBench = (benchId) => /(^|:)advisor_contract$/.test(String(benchId || ''));

export const advisorBenchDisplay = (benchId) =>
  isAdvisorBench(benchId)
    ? {
        title: 'Orionfold Advisor — refusal-floor contract',
        sub: String(benchId),
        metric: 'frozen OOD curveballs',
      }
    : null;

// Lane stub → operator-facing name + pills. Kinds map to .lane-pill--<kind>.
const ADVISOR_LANES = {
  '4b-sft-v0.2': {
    name: 'Advisor 4B — trained (SFT v0.2)',
    pills: [
      { label: '◆ flagship', kind: 'flagship' },
      { label: 'promoted lane', kind: 'ok' },
    ],
  },
  '4b-sft-v0.1': {
    name: 'Advisor 4B — trained (SFT v0.1)',
    pills: [{ label: 'superseded', kind: 'dim' }],
  },
  '4b-init': {
    name: 'Nemotron 4B — untrained base',
    pills: [{ label: 'baseline', kind: 'dim' }],
  },
  '30b-prompted': {
    name: 'Nemotron 30B — teacher · prompt-only',
    pills: [{ label: 'teacher', kind: 'warn' }],
  },
};
const ADVISOR_GATES = {
  'curveball-v0.1': 'curveball v0.1',
  'curveball-v0.2': 'curveball v0.2',
};

export function advisorLaneDisplay(benchId, laneId) {
  if (!isAdvisorBench(benchId)) return null;
  const [stub, gate] = String(laneId || '').split('::');
  const lane = ADVISOR_LANES[stub];
  if (!lane) return null;
  const gateLabel = ADVISOR_GATES[gate] || gate || null;
  return {
    name: lane.name,
    pills: gateLabel
      ? [...lane.pills, { label: `frozen OOD · ${gateLabel}`, kind: 'gate' }]
      : lane.pills,
    raw: String(laneId),
  };
}

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
