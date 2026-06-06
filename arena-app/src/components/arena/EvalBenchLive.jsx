/** @jsxImportSource preact */
// EvalBenchLive — bench-anchored LIVE rows from real eval runs (AF-28).
//
// The static "Bench-anchored — cached evidence" section reads only the
// `fieldkit arena mirror` snapshot, so the newest real bench evidence —
// `eval_rerun` jobs scored through the bench's own `scorer_path` verifier —
// was invisible on the leaderboard (e2e smoke B4: kepler-q8 0.86/44 and
// deepseek-r1 0.84/37 existed only on the Jobs board while the bench section
// showed a snapshot stamped 2026-05-28). This island projects
// GET /api/eval/leaderboard (the accuracy rollup over persisted eval scores)
// live on the Spark; on the public mirror it renders nothing (the cached tier
// remains the public story).
//
// Markup reuses the SSR ranktable/scorebar classes so the live group reads as
// one surface with the cached groups.

import { useEffect, useState } from 'preact/hooks';
import { resolveSidecarUrl, isPublicMirrorHost } from '../../lib/arena/sidecar.mjs';
import { pct, benchLabel, scoreColor } from '../../lib/arena/leaderboard-format.mjs';

const POLL_MS = 15000; // eval jobs land on minutes-cadence; a light poll suffices

function fmtAgo(iso) {
  if (!iso) return '';
  const t = Date.parse(iso);
  if (Number.isNaN(t)) return '';
  const s = Math.max(0, (Date.now() - t) / 1000);
  if (s < 90) return 'just now';
  if (s < 5400) return `${Math.round(s / 60)}m ago`;
  if (s < 129600) return `${(s / 3600).toFixed(1)}h ago`;
  return `${Math.round(s / 86400)}d ago`;
}

export default function EvalBenchLive() {
  const [rows, setRows] = useState(null); // null until first live fetch lands

  useEffect(() => {
    if (isPublicMirrorHost()) return undefined;
    const base = resolveSidecarUrl();
    if (!base) return undefined;
    let cancelled = false;
    const load = async () => {
      if (typeof document !== 'undefined' && document.visibilityState === 'hidden') return;
      try {
        const r = await fetch(`${base}/api/eval/leaderboard`, { headers: { Accept: 'application/json' } });
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        const body = await r.json();
        if (!cancelled) setRows(Array.isArray(body.rows) ? body.rows : []);
      } catch {
        /* sidecar offline — section simply stays absent */
      }
    };
    load();
    const t = setInterval(load, POLL_MS);
    return () => {
      cancelled = true;
      clearInterval(t);
    };
  }, []);

  if (!rows || rows.length === 0) return null;

  // Group by bench, quality-desc within each.
  const groups = Object.values(
    rows.reduce((acc, r) => {
      (acc[r.bench_id] ||= { bench_id: r.bench_id, rows: [] }).rows.push(r);
      return acc;
    }, {})
  ).sort((a, b) => a.bench_id.localeCompare(b.bench_id));
  groups.forEach((g) => g.rows.sort((a, b) => b.mean_normalized - a.mean_normalized));

  return (
    <div class="evalbench">
      {groups.map((g) => (
        <div class="bench-group" key={g.bench_id}>
          <div class="bench-group__head">
            <span class="bench-group__id">{benchLabel(g.bench_id)}</span>
            <span
              class="evalbench__live-tag"
              title="projected live from done eval_rerun jobs — scored through the bench's own scorer_path verifier; the groups below are the cached mirror snapshot"
            >
              ● live · eval runs
            </span>
            <span class="bench-group__count">
              {g.rows.length} lanes · {g.rows.reduce((s, r) => s + (r.n_runs || 0), 0)} runs
            </span>
            <span class="bench-group__metric">metric · mean_normalized (scorer_path)</span>
          </div>
          <table class="ranktable">
            <thead>
              <tr>
                <th class="rankcol-rank">Rank</th>
                <th class="rankcol-lane">Lane</th>
                <th class="rankcol-score">Quality</th>
                <th class="rankcol-tok">Last run</th>
                <th class="rankcol-num">Runs</th>
              </tr>
            </thead>
            <tbody>
              {g.rows.map((r, i) => {
                const rank = i + 1;
                const badgeClass = rank < 4 ? `rank-badge--${rank}` : '';
                const pctVal = pct(r.mean_normalized);
                const color = scoreColor(r.mean_normalized);
                return (
                  <tr key={r.lane_id}>
                    <td class="rankcol-rank">
                      <span class={`rank-badge ${badgeClass}`}>{rank}</span>
                    </td>
                    <td class="rankcol-lane">
                      <div class="lane-cell">
                        <span class="lane-cell__id">{r.lane_id}</span>
                      </div>
                    </td>
                    <td class="rankcol-score">
                      <div class="scorebar" style={`--scorebar-color: ${color};`}>
                        <span class="scorebar__track">
                          <span class="scorebar__fill" style={`width: ${pctVal}%`}></span>
                        </span>
                        <span class="scorebar__value">{pctVal}%</span>
                      </div>
                    </td>
                    <td class="rankcol-tok mono" style="color: var(--arena-text-mute);">
                      {fmtAgo(r.last_run_at) || <span class="dim">—</span>}
                    </td>
                    <td class="rankcol-num mono" style="color: var(--arena-text-mute);">{r.n_runs}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      ))}
    </div>
  );
}
