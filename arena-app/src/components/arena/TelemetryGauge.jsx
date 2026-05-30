/** @jsxImportSource preact */
// TelemetryGauge — `<TelemetryGauge>` Preact island for /arena/.
//
// Subscribes to `GET /api/telemetry/stream` (SSE) on the FastAPI sidecar
// at 127.0.0.1:7866. Renders 6 metric chips (GPU%, GPU °C, unified-mem
// used/total + the spec's 120 GB guard band, tok/s, TTFT, lane chip) +
// a 60s rolling sparkline of unified-mem via uPlot.
//
// Spec §4.6 — 500 ms cadence; idle ticks omit tok/s/TTFT; the connection
// is the only thing keeping the sampler alive (hub stops when the last
// subscriber leaves).
//
// Render contract: handles three states cleanly:
//   - connecting (initial, no event yet)        → all chips show "—"
//   - subscribed + alive (received event)       → live values
//   - sidecar offline (EventSource error)       → "Sidecar offline"
//                                                  banner; rest stays dash

import { useEffect, useRef, useState } from 'preact/hooks';
import uPlot from 'uplot';
import 'uplot/dist/uPlot.min.css';
import { resolveSidecarUrl, isPublicMirrorHost } from '../../lib/arena/sidecar.mjs';

const SPARK_WIDTH = 480;
const SPARK_HEIGHT = 56;
const ROLLING_WINDOW = 60; // seconds of unified-mem to keep on the sparkline

function clsForGpu(util) {
  if (util == null) return '';
  if (util >= 95) return 'gauge-chip--red';
  if (util >= 80) return 'gauge-chip--yellow';
  return 'gauge-chip--green';
}

function clsForTemp(temp) {
  if (temp == null) return '';
  if (temp >= 90) return 'gauge-chip--red';
  if (temp >= 80) return 'gauge-chip--yellow';
  return 'gauge-chip--green';
}

function fmt(v, unit, digits = 0) {
  if (v == null) return '—';
  if (typeof v !== 'number' || Number.isNaN(v)) return '—';
  return `${v.toFixed(digits)}${unit}`;
}

export default function TelemetryGauge() {
  const [state, setState] = useState('connecting'); // 'connecting' | 'live' | 'offline'
  const [tick, setTick] = useState(null);
  const sparkRef = useRef(null);
  const plotRef = useRef(null);
  const seriesRef = useRef({ t: [], used: [] });

  useEffect(() => {
    // Public-mirror short-circuit — the ArenaLayout offline banner already
    // explains. Don't try to connect, don't drop a "couldn't reach" toast.
    if (isPublicMirrorHost()) {
      setState('offline');
      return undefined;
    }
    const base = resolveSidecarUrl();
    if (!base) {
      setState('offline');
      return undefined;
    }
    const url = `${base}/api/telemetry/stream`;
    let es;
    try {
      es = new EventSource(url);
    } catch (err) {
      setState('offline');
      return undefined;
    }
    es.addEventListener('telemetry', (ev) => {
      try {
        const payload = JSON.parse(ev.data);
        setTick(payload);
        setState('live');
      } catch (err) {
        /* swallow — malformed payload, gauge stays sticky */
      }
    });
    es.addEventListener('heartbeat', () => {
      // Connection still healthy — but no new payload. Leave state alone.
    });
    es.onerror = () => {
      // EventSource auto-reconnects; surface the disconnected state until
      // it does. Don't close — let the browser retry.
      setState('offline');
    };
    return () => {
      try { es.close(); } catch {}
    };
  }, []);

  // Append to the unified-mem rolling sparkline + redraw on every tick.
  useEffect(() => {
    if (!tick) return;
    const used = tick.unified_used_gb;
    if (used == null) return;
    const now = Date.now() / 1000;
    const s = seriesRef.current;
    s.t.push(now);
    s.used.push(used);
    // Trim to the rolling window.
    while (s.t.length && s.t[0] < now - ROLLING_WINDOW) {
      s.t.shift();
      s.used.shift();
    }
    if (!sparkRef.current) return;
    const data = [s.t.slice(), s.used.slice()];
    if (!plotRef.current) {
      // Build the uPlot lazily on the first tick so we have at least one
      // data point and a known unified_total for the y-axis band.
      const total = tick.unified_total_gb || 128;
      plotRef.current = new uPlot(
        {
          width: SPARK_WIDTH,
          height: SPARK_HEIGHT,
          legend: { show: false },
          cursor: { show: false },
          axes: [
            { show: false },
            {
              size: 28,
              gap: 4,
              stroke: 'currentColor',
              grid: { stroke: 'rgba(127,127,127,0.15)' },
              ticks: { show: false },
              values: (_u, vals) => vals.map((v) => `${v.toFixed(0)} GB`),
            },
          ],
          scales: { y: { range: [0, Math.max(total, 128)] } },
          series: [
            {},
            {
              stroke: 'oklch(74% 0.16 165)',
              width: 1.5,
              fill: 'rgba(74, 222, 128, 0.12)',
              points: { show: false },
            },
          ],
        },
        data,
        sparkRef.current,
      );
    } else {
      plotRef.current.setData(data);
    }
  }, [tick]);

  // Final plot cleanup on unmount — Preact effect-cleanup pattern.
  useEffect(() => () => {
    if (plotRef.current) {
      try { plotRef.current.destroy(); } catch {}
      plotRef.current = null;
    }
  }, []);

  const offline = state === 'offline';
  const gpuUtil = tick?.gpu_util;
  const gpuTemp = tick?.gpu_temp_c;
  const used = tick?.unified_used_gb;
  const total = tick?.unified_total_gb;
  const tokPerS = tick?.tok_per_s;
  const ttft = tick?.ttft_ms;
  const laneId = tick?.lane_id;
  const inflight = tick?.inflight;

  return (
    <div class="telemetry-gauge">
      <div class="gauge-row">
        <Chip label="GPU" value={fmt(gpuUtil, '%')} cls={clsForGpu(gpuUtil)} />
        <Chip label="Temp" value={fmt(gpuTemp, '°C')} cls={clsForTemp(gpuTemp)} />
        <Chip
          label="Unified"
          value={
            used != null
              ? `${used.toFixed(1)} / ${total ? total.toFixed(0) : '?'} GB`
              : '—'
          }
          cls={used != null && used > (total ?? 128) - 8 ? 'gauge-chip--yellow' : ''}
        />
        <Chip
          label="Tok/s"
          value={inflight ? fmt(tokPerS, ' tok/s', 1) : '—'}
        />
        <Chip
          label="TTFT"
          value={fmt(ttft, ' ms')}
        />
        <Chip
          label="Lane"
          value={laneId || 'idle'}
          cls="gauge-chip--mono"
        />
      </div>
      <div class="gauge-sparkline">
        <div ref={sparkRef} class="gauge-sparkline__plot" />
        <div class="gauge-sparkline__caption">
          unified-mem · last {ROLLING_WINDOW}s · 8 GB guard band at top
        </div>
      </div>
      {offline ? (
        <p class="gauge-status gauge-status--offline">
          Sidecar offline — start with{' '}
          <code>fieldkit arena serve</code> on the Spark.
        </p>
      ) : state === 'connecting' ? (
        <p class="gauge-status">Connecting to sidecar…</p>
      ) : null}
    </div>
  );
}

function Chip({ label, value, cls = '' }) {
  return (
    <div class={`gauge-chip ${cls}`}>
      <div class="gauge-chip__label">{label}</div>
      <div class="gauge-chip__value">{value}</div>
    </div>
  );
}
