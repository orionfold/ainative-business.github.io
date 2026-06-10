// evals.mjs — client helpers for the v0.3 eval-prompt surface.
//
// Fetch wrappers for the eval-bench endpoints, the model→bench mapping
// (a mirror of `fieldkit.arena.benches.bench_for_lane` so the drawer can
// suggest the right bench for a selected lane without a round-trip), and
// the score-formatting + scorer-classification helpers shared by ChatLane,
// CompareDuel, EvalPromptDrawer, and EvalScore.

import { resolveSidecarUrl } from './sidecar.mjs';

// Deterministic scorers run instantly server-side and never invoke a judge.
const DETERMINISTIC_KINDS = new Set([
  'mcq_letter',
  'numeric_match',
  'exact_match',
  'contains',
  'irac_structure',
  // AE-11 — astro is non-judge (unit-aware numeric); the interactive grader
  // honest-skips it, but it's never a judge backend, so the judge picker hides.
  'astro_numeric_match',
  // Advisor — deterministic citation/refusal/route contract mirror of the
  // offline preflight scorer; never a judge.
  'advisor_contract',
]);

// Model slugs each bench maps to — mirror of the backend registry.
const BENCH_MODELS = {
  'patent-strategist': ['patent-strategist-v3-nemo-gguf', 'patent-strategist-v3-nemo'],
  financebench: ['finance-chat-gguf'],
  legalbench: ['saul-7b-instruct-v1-gguf'],
  cybermetric: ['securityllm-gguf'],
  medmcqa: ['ii-medical-8b-gguf'],
  // AE-11 — the astro bench maps to the Kepler GGUF lanes.
  'astro-bench': ['kepler-q8-gguf', 'kepler-gguf', 'kepler'],
  // Advisor — the released 4B-SFT-v0.2 serving lane + the comparison lanes
  // (lane-recipe slugs; the 30B teacher and the un-trained 4B init).
  'advisor-bench': [
    'nemotron3-nano-4b-sft-v02-q8',
    'nemotron3-nano-4b-sft-q8',
    'nemotron3-nano-30b-q8',
    'nemotron3-nano-4b-q8',
  ],
};

function norm(s) {
  return String(s || '').toLowerCase().replace(/[^a-z0-9]/g, '');
}

// Mirror of bench_for_lane: a compare/options lane id → its own-vertical
// bench, or null (resident / OpenRouter / no match → cross-vertical only).
export function benchForLane(laneId) {
  if (!laneId) return null;
  let lid = laneId.startsWith('local:') ? laneId.slice('local:'.length) : laneId;
  if (lid === 'resident' || lid.startsWith('openrouter')) return null;
  const slug = norm(lid.split('::')[0]);
  if (!slug) return null;
  for (const [bench, models] of Object.entries(BENCH_MODELS)) {
    for (const m of models) {
      const nm = norm(m);
      if (nm && (slug.startsWith(nm) || nm.startsWith(slug))) return bench;
    }
  }
  return null;
}

export function isDeterministic(scorerKind) {
  return DETERMINISTIC_KINDS.has(scorerKind);
}

// One scored result → a compact display string, or null if unscored.
// Deterministic + judge_quality scorers are 0–1 (rendered as %); judge-backed
// rubric scorers are 0–5 (rendered as "N.N / 5").
export function formatEvalScore(res) {
  if (!res || !res.scored) return null;
  const max = res.max || 1;
  if (max <= 1) return `${Math.round(((res.score ?? 0) / max) * 100)}%`;
  return `${(res.score ?? 0).toFixed(1)} / ${max.toFixed(0)}`;
}

// A short, human label for a scorer kind (badge text).
export function scorerLabel(kind) {
  return (
    {
      mcq_letter: 'MCQ letter',
      numeric_match: 'numeric',
      exact_match: 'exact match',
      contains: 'contains',
      irac_structure: 'IRAC',
      astro_numeric_match: 'numeric · unit-aware ±2%',
      advisor_contract: 'citation/refusal contract',
      patent_claim_validity: 'judge · claim validity',
      office_action_argument: 'judge · office action',
      judge_rubric: 'judge · correctness',
      judge_fallback: 'judge · correctness',
      judge_quality: 'judge · quality',
    }[kind] || kind
  );
}

export async function fetchBenches() {
  const base = resolveSidecarUrl();
  if (!base) return null;
  const r = await fetch(`${base}/api/eval/benches`, { headers: { Accept: 'application/json' } });
  if (!r.ok) return null;
  return r.json(); // { benches: [...], judge: {...} }
}

export async function fetchPrompts(benchId, { q = '', family = '', offset = 0, limit = 50 } = {}) {
  const base = resolveSidecarUrl();
  if (!base) return null;
  const params = new URLSearchParams();
  if (q) params.set('q', q);
  if (family) params.set('family', family);
  params.set('offset', String(offset));
  params.set('limit', String(limit));
  const r = await fetch(
    `${base}/api/eval/benches/${encodeURIComponent(benchId)}/prompts?${params}`,
  );
  if (!r.ok) return null;
  return r.json(); // { bench_id, total, offset, limit, prompts: [...] }
}

// Score a completed chat turn. `body` = { turn_id, bench_id?, eval_qid?,
// question?, lane_id?, cross_vertical?, judge? }.
export async function scoreChatTurn(body) {
  const base = resolveSidecarUrl();
  if (!base) return null;
  const r = await fetch(`${base}/api/chat/score`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!r.ok) {
    let detail = `HTTP ${r.status}`;
    try {
      const j = await r.json();
      if (j && j.detail) detail = j.detail;
    } catch (_e) {}
    return { scored: false, reason: detail, turn_id: body.turn_id };
  }
  return r.json();
}
