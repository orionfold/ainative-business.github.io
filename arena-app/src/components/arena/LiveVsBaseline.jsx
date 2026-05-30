/** @jsxImportSource preact */
// LiveVsBaseline — `<LiveVsBaseline>` Preact island for the cockpit (/arena/).
//
// Phase 5 (telemetry ↔ article-evidence bridge). The static <EvidenceBand>
// shows what the Spark was MEASURED doing in the published articles; this
// island closes the loop — when a stream is in flight it contrasts the LIVE
// resident-brain throughput against the published baseline number, so the
// operator sees how this run stacks up against the article that set the bar.
//
// Progressive enhancement only:
//   - public mirror / sidecar offline → renders the static baseline alone
//   - sidecar live, idle               → static baseline + "waiting for a run"
//   - sidecar live, inflight           → "live N vs baseline M tok/s · ±X%"
//
// Same SSE substrate as <TelemetryGauge> / <TelemetryRail>. The baseline is
// passed as a prop from project-stats.json so it stays honest + offline-safe.

import { useEffect, useState } from 'preact/hooks';
import { resolveSidecarUrl, isPublicMirrorHost } from '../../lib/arena/sidecar.mjs';

export default function LiveVsBaseline({
  baselineTokPerS = 100,
  baselineLabel = 'resident brain',
  baselineArticle = '',
  baselineHref = '',
}) {
  const [state, setState] = useState('connecting'); // connecting | live | offline
  const [liveTok, setLiveTok] = useState(null);
  const [inflight, setInflight] = useState(false);

  useEffect(() => {
    if (isPublicMirrorHost()) {
      setState('offline');
      return undefined;
    }
    const base = resolveSidecarUrl();
    if (!base) {
      setState('offline');
      return undefined;
    }
    let es;
    try {
      es = new EventSource(`${base}/api/telemetry/stream`);
    } catch (_err) {
      setState('offline');
      return undefined;
    }
    es.addEventListener('telemetry', (ev) => {
      try {
        const t = JSON.parse(ev.data);
        setState('live');
        setInflight(Boolean(t.inflight));
        if (t.inflight && typeof t.tok_per_s === 'number') setLiveTok(t.tok_per_s);
      } catch (_e) {
        /* sticky on malformed payload */
      }
    });
    es.onerror = () => setState('offline');
    return () => {
      try { es.close(); } catch {}
    };
  }, []);

  const delta =
    liveTok != null && baselineTokPerS
      ? ((liveTok - baselineTokPerS) / baselineTokPerS) * 100
      : null;
  const deltaCls =
    delta == null ? '' : delta >= -2 ? 'lvb__delta--up' : delta >= -15 ? 'lvb__delta--mid' : 'lvb__delta--down';

  return (
    <div class="lvb">
      <div class="lvb__head">
        <span class="lvb__title">Live vs baseline</span>
        {baselineHref ? (
          <a class="lvb__src" href={baselineHref}>{baselineLabel} →</a>
        ) : (
          <span class="lvb__src lvb__src--plain">{baselineLabel}</span>
        )}
      </div>

      <div class="lvb__bars">
        <div class="lvb__row">
          <span class="lvb__row-label">baseline</span>
          <span class="lvb__row-val">{baselineTokPerS.toFixed(0)} tok/s</span>
        </div>
        <div class="lvb__row lvb__row--live">
          <span class="lvb__row-label">
            <span class={`lvb__dot ${state === 'live' && inflight ? 'lvb__dot--on' : ''}`} />
            live
          </span>
          <span class="lvb__row-val">
            {state === 'live' && inflight && liveTok != null ? `${liveTok.toFixed(1)} tok/s` : '—'}
          </span>
        </div>
      </div>

      <p class="lvb__verdict">
        {state === 'offline' ? (
          <span class="lvb__muted">
            Sidecar offline — showing the published baseline. Start with{' '}
            <code>fieldkit arena up</code>.
          </span>
        ) : state === 'connecting' ? (
          <span class="lvb__muted">Connecting to the resident brain…</span>
        ) : !inflight || delta == null ? (
          <span class="lvb__muted">Idle — send a prompt to compare this run against the bar.</span>
        ) : (
          <span class={`lvb__delta ${deltaCls}`}>
            {delta >= 0 ? '+' : ''}{delta.toFixed(1)}% {delta >= 0 ? 'above' : 'below'} the published {baselineTokPerS.toFixed(0)} tok/s
          </span>
        )}
      </p>
    </div>
  );
}
