/** @jsxImportSource preact */
// LiveLeaderboard — the "Live cockpit runs" table, live on the Spark.
//
// SSRs the static seed rows (from leaderboard.json, passed as `seedRows`) for
// first paint + the public-mirror fallback, then — only when the sidecar is
// reachable (not isPublicMirrorHost) — fetches GET /api/leaderboard/live and
// re-renders, refetching whenever `leaderboard_rev` changes on the existing
// /api/telemetry/stream SSE. So a compare or chat run shows up here within ~1s
// with NO rebuild. On the public mirror it stays the static curated snapshot.
//
// Reuses the EventSource pattern from TelemetryGauge/TelemetryRail and the
// sidecar.mjs host helpers; renders the same markup/classes as the SSR table.

import { useEffect, useRef, useState } from 'preact/hooks';
import { resolveSidecarUrl, isPublicMirrorHost } from '../../lib/arena/sidecar.mjs';
import {
  pct,
  fmtTok,
  fmtTtft,
  fmtPref,
  fmtCost,
  fmtCostPerQuality,
  laneModel,
  laneSuffix,
  laneSource,
  benchLabel,
  scoreColor,
  sortLiveRows,
} from '../../lib/arena/leaderboard-format.mjs';

// Source pill — Spark-green for local, OpenRouter-blue for cloud. Same colours
// as the compare side-card badges (CompareDuel) so the cockpit reads as one app.
function SourceBadge({ source }) {
  const isOR = source === 'openrouter';
  const c = isOR ? '#2750AE' : '#338A17';
  return (
    <span
      title={isOR ? 'Runs in the cloud via OpenRouter' : 'Runs locally on the DGX Spark'}
      style={`flex:none; font-family: var(--arena-mono); font-size:0.55rem; font-weight:700; letter-spacing:0.06em; text-transform:uppercase; padding:1px 7px; border-radius:999px; color:${c}; background:${c}1f; border:1px solid ${c}66;`}
    >
      {isOR ? 'OpenRouter' : 'Spark GPU'}
    </span>
  );
}

const H2_STYLE =
  'font-family: var(--arena-mono); font-size: 0.7rem; letter-spacing: 0.22em; ' +
  'text-transform: uppercase; color: var(--arena-text-mute); margin: 0 0 0.85rem; ' +
  'display: flex; align-items: center; gap: 0.6rem;';

// AF-27 — the default cockpit rubrics are FORMAT checks (regex/substring
// anchors), not correctness verdicts; their leaderboard scores carry a `fmt`
// qualifier so a wrong-but-well-formatted answer can't read as 100% quality
// (the smoke's `kepler 100.0%` off a format regex).
const FORMAT_RUBRICS = new Set(['generic-correctness', 'patent_claim_validity', 'mcq_letter']);
const isFormatScore = (benchId) =>
  typeof benchId === 'string' &&
  benchId.startsWith('cockpit:') &&
  FORMAT_RUBRICS.has(benchId.slice('cockpit:'.length));

export default function LiveLeaderboard({ seedRows = [] }) {
  const [rows, setRows] = useState(() => sortLiveRows(seedRows));
  const [mode, setMode] = useState('static'); // 'static' | 'live' | 'offline'
  const revRef = useRef(-1);
  const debounceRef = useRef(null);

  useEffect(() => {
    // Public mirror — keep the static seed, never reach for the sidecar.
    if (isPublicMirrorHost()) {
      setMode('static');
      return undefined;
    }
    const base = resolveSidecarUrl();
    if (!base) {
      setMode('static');
      return undefined;
    }

    let cancelled = false;
    const fetchRows = async () => {
      if (typeof document !== 'undefined' && document.visibilityState === 'hidden') return;
      try {
        const r = await fetch(`${base}/api/leaderboard/live`, {
          headers: { Accept: 'application/json' },
        });
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        const body = await r.json();
        if (cancelled) return;
        setRows(sortLiveRows(Array.isArray(body.rows) ? body.rows : []));
        if (typeof body.rev === 'number') revRef.current = body.rev;
        setMode('live');
      } catch {
        if (!cancelled) setMode((m) => (m === 'live' ? 'offline' : 'static'));
      }
    };

    fetchRows(); // initial live pull replaces the SSR seed

    // Ride the shared telemetry bus (one page-wide EventSource) rather than
    // opening a second stream to the same endpoint — the duplicate streams were
    // a big part of the rapid-tab-switch connection-pool starvation. The bus
    // handles after-load deferral and ref-counted close.
    const bus = typeof window !== 'undefined' && window.__arenaTelemetry;
    const unsubscribe = bus
      ? bus.subscribe({
          onTelemetry: (t) => {
            const rev = t && t.leaderboard_rev;
            if (typeof rev !== 'number' || rev === revRef.current) return;
            revRef.current = rev;
            // Debounce the compare double-bump + a near-simultaneous chat-score
            // bump into a single refetch.
            if (debounceRef.current) clearTimeout(debounceRef.current);
            debounceRef.current = setTimeout(fetchRows, 200);
          },
          onError: (rs) => {
            if (rs === 2) setMode((m) => (m === 'live' ? 'offline' : m));
          },
        })
      : null;

    return () => {
      cancelled = true;
      if (unsubscribe) unsubscribe();
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
  }, []);

  const totalRuns = rows.reduce((s, r) => s + (r.n_runs || 0), 0);
  const dot =
    mode === 'live'
      ? { c: 'var(--arena-ok)', t: 'live · DB' }
      : mode === 'offline'
        ? { c: 'var(--arena-warn)', t: 'sidecar offline · last snapshot' }
        : { c: 'var(--arena-text-dim)', t: 'static snapshot' };

  return (
    <div>
      <h2 style={H2_STYLE}>
        ◉ Live cockpit runs — operator compares & chats
        <span
          title={dot.t}
          style={`display:inline-flex; align-items:center; gap:0.35rem; font-size:0.6rem; letter-spacing:0.12em; color:${dot.c};`}
        >
          <span style={`width:6px; height:6px; border-radius:50%; background:${dot.c}; box-shadow:0 0 6px ${dot.c};`} />
          {dot.t}
        </span>
      </h2>
      {rows.length === 0 ? (
        <div class="empty">
          <p>
            No live cockpit rows yet — run a compare in{' '}
            <a href="/arena/compare/">/arena/compare/</a> or a chat in{' '}
            <a href="/arena/chat/">/arena/chat/</a>.
          </p>
        </div>
      ) : (
        <div class="bench-group">
          <div class="bench-group__head">
            <span class="bench-group__id">cockpit · all rubrics</span>
            <span class="bench-group__count">
              {rows.length} rows · {totalRuns} runs
            </span>
            <span class="bench-group__metric">
              {mode === 'live' ? 'live · compare + chat' : 'metric · rubric mean'}
            </span>
          </div>
          <table class="ranktable">
            <thead>
              <tr>
                <th class="rankcol-rank">Rank</th>
                <th class="rankcol-lane">Model · rubric</th>
                <th class="rankcol-score">Quality</th>
                <th class="rankcol-tok">Throughput</th>
                <th class="rankcol-tok">TTFT</th>
                <th class="rankcol-tok" title="Mean cost per task — $0 (local) for Spark lanes">$/task</th>
                <th class="rankcol-tok" title="Cost per quality point — mean cost ÷ mean score (M9)">$/quality</th>
                <th class="rankcol-num">Runs</th>
                <th class="rankcol-pct">Human ↑</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r, i) => {
                const rank = i + 1;
                const badgeClass = rank < 4 ? `rank-badge--${rank}` : '';
                const hasScore = r.mean_score != null;
                const pctVal = hasScore ? pct(r.mean_score) : null;
                const color = scoreColor(r.mean_score);
                return (
                  <tr key={`${r.bench_id}::${r.lane_id}`}>
                    <td class="rankcol-rank">
                      <span class={`rank-badge ${badgeClass}`}>{rank}</span>
                    </td>
                    <td class="rankcol-lane">
                      <div class="lane-cell">
                        {/* Model leads + source badge; the rubric (or "chat"
                            for the unscored fold) rides as the secondary line. */}
                        <span style="display:inline-flex; align-items:center; gap:7px; min-width:0;">
                          <span class="lane-cell__id">
                            {laneModel(r.lane_id)}
                            {laneSuffix(r.lane_id) && ` (${laneSuffix(r.lane_id)})`}
                          </span>
                          <SourceBadge source={laneSource(r.lane_id)} />
                        </span>
                        <span class="lane-cell__slug">
                          {r.bench_id === 'cockpit:chat' ? 'chat' : benchLabel(r.bench_id)}
                        </span>
                      </div>
                    </td>
                    <td class="rankcol-score">
                      {hasScore ? (
                        <div class="scorebar" style={`--scorebar-color: ${color};`}>
                          <span class="scorebar__track">
                            <span class="scorebar__fill" style={`width: ${pctVal}%`} />
                          </span>
                          <span class="scorebar__value">
                            {pctVal}%
                            {isFormatScore(r.bench_id) && (
                              <span
                                class="dim"
                                title="format-rubric score (regex/substring anchors) — checks answer SHAPE, not whether the value is correct; gold verdicts live in the bench-anchored live group"
                              >
                                {' '}·fmt
                              </span>
                            )}
                          </span>
                        </div>
                      ) : (
                        <span class="dim" title="throughput-only — no quality score yet">—</span>
                      )}
                    </td>
                    <td class="rankcol-tok mono" style="color: var(--arena-text-mute);">
                      {r.median_tok_per_s != null ? (
                        `${fmtTok(r.median_tok_per_s)} tok/s`
                      ) : (
                        <span class="dim">—</span>
                      )}
                    </td>
                    <td class="rankcol-tok mono" style="color: var(--arena-text-mute);">
                      {fmtTtft(r.mean_ttft_ms)}
                    </td>
                    {/* M9 (Bet 6): the cost axis. Local lanes read "$0 (local)";
                        a priced lane reads its $/task + $/quality-point. */}
                    <td class="rankcol-tok mono" style="color: var(--arena-text-mute);">
                      {fmtCost(r.mean_cost_usd)}
                    </td>
                    <td class="rankcol-tok mono" style="color: var(--arena-text-mute);">
                      {fmtCostPerQuality(r.mean_cost_usd, r.cost_per_quality_point)}
                    </td>
                    <td class="rankcol-num mono" style="color: var(--arena-text-mute);">
                      {r.n_runs}
                    </td>
                    <td class="rankcol-pct mono" style="color: var(--arena-text-mute);">
                      {fmtPref(r.human_pref_winrate)}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
