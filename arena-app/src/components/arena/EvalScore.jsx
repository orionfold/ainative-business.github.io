/** @jsxImportSource preact */
// EvalScore — renders one reference-based eval grade.
//
// Shared by ChatLane (per-turn) and CompareDuel (per-side). Takes a score
// result from `/api/chat/score` or the compare `score` event's `eval` block:
//   { scored, score, max, normalized, scorer_kind, why, judge_backend }
// or the unscored shape { scored:false, reason }.
//
// Deterministic scorers (MCQ/numeric/exact/IRAC) show a green "instant" badge;
// judge-backed scorers show a blue badge + a collapsible rationale. The meter
// is banded on the normalized [0,1] score so 0–1 and 0–5 scorers read alike.

import { isDeterministic, formatEvalScore, scorerLabel } from '../../lib/arena/evals.mjs';

export default function EvalScore({ result, pending }) {
  if (pending) {
    return (
      <div class="eval-score eval-score--pending">
        <span class="eval-score__spinner" aria-hidden="true" />
        <span class="eval-score__label">scoring…</span>
      </div>
    );
  }
  if (!result) return null;

  if (!result.scored) {
    return (
      <div class="eval-score eval-score--skip" title={result.reason || ''}>
        <span class="eval-score__badge eval-score__badge--skip">not scored</span>
        <span class="eval-score__why">{result.reason || 'scoring unavailable'}</span>
      </div>
    );
  }

  const det = isDeterministic(result.scorer_kind);
  const norm = result.normalized ?? (result.max ? result.score / result.max : 0);
  const band = norm >= 0.75 ? 'ok' : norm >= 0.4 ? 'mid' : 'low';

  return (
    <div class="eval-score">
      <div class="eval-score__row">
        <span class={`eval-score__badge eval-score__badge--${det ? 'det' : 'judge'}`}>
          {det ? '⚡ ' : '⚖ '}
          {scorerLabel(result.scorer_kind)}
          {!det && result.judge_backend ? ` · ${result.judge_backend}` : ''}
        </span>
        <span class="eval-score__value">{formatEvalScore(result)}</span>
        <span class="eval-score__meter" aria-hidden="true">
          <span class={`eval-score__meter-fill eval-score__meter-fill--${band}`} style={`width:${Math.round(norm * 100)}%`} />
        </span>
      </div>
      {result.why && (
        det ? (
          <span class="eval-score__why">{result.why}</span>
        ) : (
          <details class="eval-score__rationale">
            <summary>judge rationale</summary>
            <p>{result.why}</p>
          </details>
        )
      )}
    </div>
  );
}

// The shared reference (gold) answer panel — collapsible, markdown-free (gold
// answers are short labels / numbers / claim text, shown verbatim).
export function ReferencePanel({ reference, open = false }) {
  if (!reference) return null;
  return (
    <details class="eval-reference" open={open}>
      <summary>◆ Reference answer</summary>
      <pre class="eval-reference__body">{reference}</pre>
    </details>
  );
}
