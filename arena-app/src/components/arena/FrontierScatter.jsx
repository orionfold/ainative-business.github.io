/** @jsxImportSource preact */
// FrontierScatter — the cost/quality efficiency frontier.
//
// A quality(y) × throughput tok/s(x) scatter with the Pareto-optimal frontier
// drawn in gold — the frontier public cloud arenas can't draw because they
// don't know what hardware their votes ran on. Pure client-side uPlot fed a build-time
// `points` prop, so it survives on the public web preview (no sidecar).
//
// Quality is normalized to a 0..1 index PER VISIBLE SET so heterogeneous
// sources share one axis honestly:
//   - leaderboard rows carry `score` (already 0..1) → used directly;
//   - artifact variants carry `ppl` (perplexity, lower=better) → inverted via
//     min-max within the rendered set; raw ppl is always shown in the tooltip
//     and the axis is labelled "quality index" so the inversion is never hidden;
//   - `evalScore` (0..1) is preferred over ppl when present.
//
// Modes: 'single' (one model's variants — the natural per-quant Pareto),
// 'multi' (all artifacts), 'leaderboard' (lane rows). Mode only changes labels
// + grouping; the frontier math is identical.

import { useEffect, useRef, useMemo } from 'preact/hooks';
import uPlot from 'uplot';
import 'uplot/dist/uPlot.min.css';

// Per-group point colors (OKLCH) — cycles for multi/leaderboard modes.
const GROUP_COLORS = [
  '#1283DA', // blue mid
  '#11AF22', // green mid
  '#E08D00', // yellow mid
  '#E929BA', // pink mid
  '#01A9DB', // cyan mid
];
const FRONTIER_COLOR = '#E08D00'; // --arena-gold
const REC_COLOR = '#E08D00';

function qualityOf(p) {
  if (typeof p.score === 'number') return { norm: p.score, raw: p.score, kind: 'score' };
  if (typeof p.evalScore === 'number') return { norm: p.evalScore, raw: p.evalScore, kind: 'eval' };
  return { norm: null, raw: typeof p.ppl === 'number' ? p.ppl : null, kind: 'ppl' };
}

// Deterministic skyline: a point is Pareto-optimal iff no other point has both
// higher-or-equal x (tok/s) AND higher-or-equal y (quality). Sort by x desc,
// then y desc; sweep keeping the best y seen — a point survives iff it strictly
// beats every higher-throughput point on quality.
function paretoFrontier(pts) {
  const idx = pts.map((_, i) => i).sort((a, b) => (pts[b].x - pts[a].x) || (pts[b].y - pts[a].y));
  const onFrontier = new Set();
  let maxY = -Infinity;
  for (const i of idx) {
    if (pts[i].y > maxY) { onFrontier.add(i); maxY = pts[i].y; }
  }
  return onFrontier;
}

export default function FrontierScatter({ points = [], mode = 'multi', title = '', normalize = 'global' }) {
  const wrapRef = useRef(null);
  const plotEl = useRef(null);
  const plotRef = useRef(null);
  const tipRef = useRef(null);

  // Resolve normalized points + frontier once per `points` change.
  const model = useMemo(() => {
    const enriched = points
      .map((p) => ({ ...p, q: qualityOf(p) }))
      .filter((p) => typeof p.x === 'number' && (p.q.norm != null || typeof p.q.raw === 'number'));
    // Perplexity is corpus-dependent, so it's only comparable WITHIN one base
    // model. 'per-group' min-maxes each model's variants separately (honest
    // multi-model view); 'global' min-maxes the whole set (fine for one model).
    const pplRange = (pts) => {
      const vals = pts.filter((p) => p.q.kind === 'ppl' && typeof p.q.raw === 'number').map((p) => p.q.raw);
      return vals.length ? { min: Math.min(...vals), max: Math.max(...vals) } : { min: 0, max: 0 };
    };
    const ranges = {};
    if (normalize === 'per-group') {
      const byGroup = {};
      for (const p of enriched) (byGroup[p.group || title || 'set'] ||= []).push(p);
      for (const g of Object.keys(byGroup)) ranges[g] = pplRange(byGroup[g]);
    } else {
      ranges.__global__ = pplRange(enriched);
    }
    const resolved = enriched.map((p) => {
      let y = p.q.norm;
      if (y == null && p.q.kind === 'ppl' && typeof p.q.raw === 'number') {
        const r = normalize === 'per-group' ? ranges[p.group || title || 'set'] : ranges.__global__;
        const span = r.max - r.min;
        y = span > 0 ? (r.max - p.q.raw) / span : 1; // higher = better; flat → 1
      }
      return { ...p, y: y == null ? 0 : y };
    }).filter((p) => typeof p.y === 'number');
    // uPlot needs x ascending.
    resolved.sort((a, b) => a.x - b.x);
    const frontier = paretoFrontier(resolved);
    const groups = Array.from(new Set(resolved.map((p) => p.group || title || 'set')));
    return { resolved, frontier, groups };
  }, [points, mode, title, normalize]);

  useEffect(() => {
    if (!plotEl.current || model.resolved.length === 0) return;
    const { resolved, frontier, groups } = model;
    const xs = resolved.map((p) => p.x);

    // One series per group (native per-group colors + legend), each y array
    // non-null only at that group's indices.
    const groupSeries = groups.map((g, gi) => ({
      label: g,
      stroke: GROUP_COLORS[gi % GROUP_COLORS.length],
      fill: GROUP_COLORS[gi % GROUP_COLORS.length],
      paths: () => null,
      points: { show: true, size: 9, width: 0 },
    }));
    const groupData = groups.map((g) => resolved.map((p) => ((p.group || title || 'set') === g ? p.y : null)));

    // Frontier polyline (gold) — y at frontier indices, null elsewhere.
    const frontierY = resolved.map((p, i) => (frontier.has(i) ? p.y : null));
    // Recommended highlight (single mode): the sweet-spot variant, gold ring.
    const recY = resolved.map((p) => (p.recommended ? p.y : null));

    const data = [xs, ...groupData, frontierY, recY];

    const series = [
      {},
      ...groupSeries,
      {
        label: 'Pareto frontier',
        stroke: FRONTIER_COLOR,
        width: 2,
        spanGaps: true,
        points: { show: false },
      },
      {
        label: 'sweet spot',
        stroke: REC_COLOR,
        fill: REC_COLOR,
        paths: () => null,
        points: { show: true, size: 15, width: 2 },
      },
    ];

    const opts = {
      width: wrapRef.current?.clientWidth || 640,
      height: 320,
      legend: { show: false },
      cursor: { points: { show: false }, y: false },
      scales: { x: { time: false }, y: { range: [0, 1.04] } },
      axes: [
        {
          stroke: 'currentColor',
          grid: { stroke: 'rgba(127,127,127,0.12)' },
          ticks: { show: false },
          values: (_u, vals) => vals.map((v) => `${v.toFixed(0)}`),
          label: 'throughput · tok/s',
          labelGap: 6,
          labelSize: 22,
        },
        {
          stroke: 'currentColor',
          grid: { stroke: 'rgba(127,127,127,0.12)' },
          ticks: { show: false },
          size: 44,
          values: (_u, vals) => vals.map((v) => `${(v * 100).toFixed(0)}`),
          label: 'quality index',
          labelGap: 6,
          labelSize: 22,
        },
      ],
      series,
      hooks: {
        setCursor: [
          (u) => {
            const { idx } = u.cursor;
            const tip = tipRef.current;
            if (!tip) return;
            if (idx == null || idx < 0 || idx >= resolved.length) { tip.style.display = 'none'; return; }
            const p = resolved[idx];
            const left = u.valToPos(p.x, 'x');
            const top = u.valToPos(p.y, 'y');
            const qLine = p.q.kind === 'ppl'
              ? `ppl ${typeof p.ppl === 'number' ? p.ppl.toFixed(3) : '—'}`
              : `${(p.q.raw * 100).toFixed(0)}% ${p.q.kind === 'eval' ? 'eval' : 'score'}`;
            tip.innerHTML =
              `<b>${p.label ?? ''}</b>` +
              (mode !== 'single' && p.group ? `<span class="frontier-tip__grp">${p.group}</span>` : '') +
              `<span class="frontier-tip__row">${p.x.toFixed(1)} tok/s · ${qLine}</span>` +
              (frontier.has(idx) ? `<span class="frontier-tip__pareto">◆ on the frontier</span>` : '') +
              (p.recommended ? `<span class="frontier-tip__rec">★ sweet spot</span>` : '');
            tip.style.display = 'block';
            tip.style.left = `${left}px`;
            tip.style.top = `${top}px`;
          },
        ],
      },
    };

    plotRef.current = new uPlot(opts, data, plotEl.current);

    const ro = new ResizeObserver(() => {
      if (plotRef.current && wrapRef.current) {
        plotRef.current.setSize({ width: wrapRef.current.clientWidth, height: 320 });
      }
    });
    if (wrapRef.current) ro.observe(wrapRef.current);

    return () => {
      ro.disconnect();
      if (plotRef.current) { try { plotRef.current.destroy(); } catch {} plotRef.current = null; }
    };
  }, [model, mode, title]);

  if (model.resolved.length === 0) {
    return (
      <div class="frontier-scatter frontier-scatter--empty">
        <p class="dim mono">No quality×throughput data to plot yet.</p>
      </div>
    );
  }

  const legendGroups = model.groups;
  return (
    <div class="frontier-scatter" ref={wrapRef}>
      <div class="frontier-plot" ref={plotEl} />
      <div class="frontier-tip" ref={tipRef} style="display:none" />
      <div class="frontier-legend">
        {legendGroups.map((g, i) => (
          <span class="frontier-legend__item">
            <span class="frontier-legend__swatch" style={`background:${GROUP_COLORS[i % GROUP_COLORS.length]}`} />
            {mode === 'single' ? 'variants' : g}
          </span>
        ))}
        <span class="frontier-legend__item">
          <span class="frontier-legend__swatch frontier-legend__swatch--line" style={`background:${FRONTIER_COLOR}`} />
          Pareto frontier
        </span>
        <span class="frontier-legend__note">higher + righter = better · hover a point</span>
      </div>
    </div>
  );
}
