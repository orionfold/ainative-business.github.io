/** @jsxImportSource preact */
// ProvenanceChip — the AE-24 per-pane run-provenance cue (arena-enhancements-v2
// Cluster H; OBS-5 / AF-26, operator-raised).
//
// During the e2e smoke every pane rendered *prior-run* data that LOOKED current
// (Jun-4 SFT runs as peers of the live one; a prior Kepler eval on the
// leaderboard; the reward gauge reading an old preflight). This chip is the
// cross-cutting cue: `run-id · relative-age · live ◉ / prior ○` — reusing the
// AE-16 relative-time + short-id pattern from the Jobs cards.
//
// Honesty contract: "this run" vs "prior run" is only claimed when a run
// anchor exists — the instant the operator selected/armed a lane (AE-22 →
// registry `set_at`, served by GET /api/run-context). Unanchored, the chip
// shows plain age and says so on hover, instead of inventing a run boundary.

import { useEffect, useState } from 'preact/hooks';
import { fetchRunContext, anchorMs } from '../../lib/arena/run-context.mjs';

const POLL_MS = 20_000;

/** Shared hook: the current run-context (cached module-wide, light poll). */
export function useRunContext() {
  const [ctx, setCtx] = useState(null);
  useEffect(() => {
    let cancelled = false;
    const tick = async () => {
      const v = await fetchRunContext();
      if (!cancelled && v) setCtx(v);
    };
    tick();
    const id = setInterval(() => {
      if (document.visibilityState === 'visible') tick();
    }, POLL_MS);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, []);
  return ctx;
}

export function fmtAge(ms) {
  if (ms == null) return '';
  const s = Math.max(0, (Date.now() - ms) / 1000);
  if (s < 90) return 'just now';
  if (s < 5400) return `${Math.round(s / 60)}m ago`;
  if (s < 172800) return `${(s / 3600).toFixed(1)}h ago`;
  return `${Math.round(s / 86400)}d ago`;
}

/**
 * Classify a datum against the run anchor.
 *   live      — the producer is writing right now (pane-specific signal);
 *   current   — stamped at/after the anchor → this run;
 *   prior     — stamped before the anchor → a prior run (stale-dim it);
 *   unanchored — no run anchor exists; show age, claim nothing.
 */
export function provState({ tsMs, live, anchor }) {
  if (live) return 'live';
  if (anchor != null && tsMs != null) return tsMs >= anchor ? 'current' : 'prior';
  return 'unanchored';
}

export default function ProvenanceChip({ tsMs = null, live = false, runId = null }) {
  const ctx = useRunContext();
  const anchor = anchorMs(ctx);
  const state = provState({ tsMs, live, anchor });
  const age = fmtAge(tsMs);
  const mark = state === 'live' || state === 'current' ? '◉' : '○';
  const label =
    state === 'live'
      ? 'live · this run'
      : state === 'current'
        ? `this run${age ? ' · ' + age : ''}`
        : state === 'prior'
          ? `prior run${age ? ' · ' + age : ''}`
          : tsMs == null
            ? anchor != null
              ? `run armed ${fmtAge(anchor)}`
              : 'unanchored'
            : age || 'age unknown';
  const title =
    state === 'prior'
      ? `from a prior run — stamped before the run anchor (lane armed ${ctx?.run_started || '—'})`
      : anchor != null
        ? `run anchored when the lane was selected (${ctx?.run_started || '—'})`
        : 'unanchored — select a lane (Models → serving lanes) to anchor run-context; until then only the data age is claimed';
  return (
    <span class={`prov-chip prov-chip--${state}`} title={title} role="note">
      <span class="prov-chip__mark" aria-hidden="true">{mark}</span>
      {runId && <code class="prov-chip__run">{runId}</code>}
      <span class="prov-chip__label">{label}</span>
    </span>
  );
}
