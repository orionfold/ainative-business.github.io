/** @jsxImportSource preact */
// SftProgressPane — `<SftProgressPane>` Preact island for /arena/sft/.
//
// Dogfood AF (astrodynamics-vertical-v1 §1 goal 2; _IDEAS/arena-dogfood-
// feature-extraction.md). Closes the AF-2 blind spot for the SFT-init stage:
// the NeMo p65 LoRA SFT run (C2(b)) is in-session skill work the control plane
// never saw — this pane makes the training itself visible, the training-stage
// analogue of the rl_run progress strip. The operator can watch a
// TrainRecipe(backend="nemo") run side-by-side instead of tailing a log.
//
// GET /api/sft-progress parses a NeMo driver log + run-dir:
//   • iter / max + a progress bar + ETA + iter/s — is it advancing?
//   • the loss curve (sparkline) — is it actually learning the format?
//   • peak GPU memory — the unified-memory OOM-landmine watch;
//   • checkpoints written — what merge_and_export can pick up.
//
// History + auto-follow mirror RewardSignalPane (AF-9): a run dropdown defaults
// to the live run and can pin a prior one. Read-only: an HTTP GET parses a log,
// it never launches a lane. On the public mirror there's no sidecar → note.

import { useEffect, useRef, useState } from 'preact/hooks';
import { resolveSidecarUrl, isPublicMirrorHost } from '../../lib/arena/sidecar.mjs';

const fmtEta = (s) => {
  if (s == null) return '—';
  const t = Math.round(s);
  if (t < 60) return `${t}s`;
  const m = Math.floor(t / 60);
  return `${m}m ${t % 60}s`;
};

// History dropdown label per run: iter-progress · loss · state.
const runOptLabel = (run, i) => {
  const prog =
    run.max_iters ? `${run.latest_iter ?? 0}/${run.max_iters}` : `${run.latest_iter ?? 0}`;
  const loss = run.last_loss != null ? `loss ${run.last_loss}` : '';
  const state = run.status === 'running' ? 'running' : (run.status || 'done');
  return `${prog} · ${state}${loss ? ' · ' + loss : ''}${i === 0 ? ' · latest' : ''} — ${run.source}`;
};

// Inline SVG sparkline of the loss curve. Normalizes loss across its own
// min/max so the descent is always legible regardless of absolute scale.
function LossSpark({ series }) {
  if (!series || series.length < 2) return null;
  const W = 520, H = 96, P = 6;
  const losses = series.map((p) => p.loss);
  const lo = Math.min(...losses), hi = Math.max(...losses);
  const span = hi - lo || 1;
  const n = series.length;
  const x = (i) => P + (i / (n - 1)) * (W - 2 * P);
  const y = (v) => P + (1 - (v - lo) / span) * (H - 2 * P);
  const pts = series.map((p, i) => `${x(i).toFixed(1)},${y(p.loss).toFixed(1)}`).join(' ');
  const area = `${P},${H - P} ${pts} ${(W - P).toFixed(1)},${H - P}`;
  return (
    <svg class="sft__spark" viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none"
         role="img" aria-label="LoRA SFT loss curve">
      <polygon class="sft__spark-area" points={area} />
      <polyline class="sft__spark-line" points={pts} />
      <circle class="sft__spark-dot" cx={x(n - 1)} cy={y(losses[n - 1])} r="3.2" />
    </svg>
  );
}

export default function SftProgressPane() {
  const [online, setOnline] = useState(false);
  const [data, setData] = useState(null);
  const [selected, setSelected] = useState('');
  const baseRef = useRef(null);
  const pollRef = useRef(null);
  const selectedRef = useRef('');

  async function refresh() {
    const base = baseRef.current;
    if (!base) return;
    const sel = selectedRef.current;
    const url = sel
      ? `${base}/api/sft-progress?source=${encodeURIComponent(sel)}`
      : `${base}/api/sft-progress`;
    try {
      const r = await fetch(url);
      if (r.ok) {
        setData(await r.json());
        setOnline(true);
      }
    } catch (_e) {
      setOnline(false);
    }
  }

  function onPick(e) {
    const v = e.target.value;
    selectedRef.current = v;
    setSelected(v);
    refresh();
  }

  useEffect(() => {
    if (isPublicMirrorHost()) return;
    const base = resolveSidecarUrl();
    if (!base) return;
    baseRef.current = base;
    setOnline(true);
    refresh();
    pollRef.current = setInterval(refresh, 3000);
    return () => pollRef.current && clearInterval(pollRef.current);
  }, []);

  if (!online && !data) {
    return (
      <div class="sft">
        <div class="sft__offline">
          <span class="sft__offline-dot" aria-hidden="true" />
          <div>
            <strong>Cockpit offline.</strong> The SFT feed renders the live NeMo
            LoRA training run — it surfaces only against a running sidecar
            (<code>fieldkit arena up</code> on the Spark). It reads a driver log;
            it never launches a lane.
          </div>
        </div>
      </div>
    );
  }

  if (data && data.available === false) {
    return (
      <div class="sft">
        <div class="sft__empty">
          <strong>No SFT run yet.</strong> Drive a NeMo SFT-init
          (<code>scripts/astro_bench/run_sft_nemo.py full</code>) and the live
          training feed lands here — iter progress, the loss curve, ETA, and the
          peak-memory watch.
        </div>
      </div>
    );
  }

  const rep = (data && data.report) || {};
  const runs = (data && data.runs) || [];
  const source = data && data.source;
  const status = rep.status || 'init';
  const isRunning = status === 'running' || status === 'starting';
  const max = rep.max_iters || 0;
  const cur = rep.latest_iter || 0;
  const progressPct = max ? Math.min(100, Math.round((cur / max) * 100)) : 0;
  const ckpts = rep.checkpoints || [];

  return (
    <div class="sft">
      {/* Run-history selector — default latest, look up prior runs. */}
      {runs.length > 0 && (
        <div class="sft__history">
          <label class="sft__history-label" for="sft-run-select">run</label>
          <select id="sft-run-select" class="sft__history-select"
                  value={selected} onChange={onPick}>
            <option value="">Latest (auto-follow)</option>
            {runs.map((run, i) => (
              <option value={run.source} key={run.source}>{runOptLabel(run, i)}</option>
            ))}
          </select>
          {source && (
            <span class="sft__history-now">showing <code>{source}</code></span>
          )}
        </div>
      )}

      {/* Live strip — phase, iter progress bar, ETA. */}
      <div class="sft__live" data-running={isRunning} role="status">
        <span class="sft__live-dot" data-running={isRunning} aria-hidden="true" />
        <span class="sft__live-label">{status === 'done' ? 'DONE' : status.toUpperCase()}</span>
        <span class="sft__live-count">{status === 'starting' || status === 'init'
          ? 'model + optimizer setup…'
          : `iter ${cur}/${max}`}</span>
        <div class="sft__live-bar" aria-hidden="true">
          <div class="sft__live-fill" style={`width:${progressPct}%`} data-done={status === 'done'} />
        </div>
        <span class="sft__live-eta">
          {isRunning && status === 'running'
            ? `ETA ${fmtEta(rep.eta_s)} · ${rep.iter_per_s ?? '—'} it/s · refreshes 3s`
            : (status === 'done' ? 'training complete' : 'starting · refreshes 3s')}
        </span>
      </div>

      {/* Headline numbers. */}
      <div class="sft__gauges">
        <div class="sft__gauge">
          <span class="sft__gauge-val">{rep.last_loss ?? '—'}</span>
          <span class="sft__gauge-label">lm loss</span>
          <span class="sft__gauge-sub">{rep.first_loss != null ? `from ${rep.first_loss}` : 'latest iteration'}</span>
        </div>
        <div class="sft__gauge sft__gauge--accent">
          <span class="sft__gauge-val">{progressPct}%</span>
          <span class="sft__gauge-label">progress</span>
          <span class="sft__gauge-sub">{cur}/{max} iters</span>
        </div>
        <div class="sft__gauge" data-alarm={(rep.peak_mem_gb || 0) >= 60}>
          <span class="sft__gauge-val">{rep.peak_mem_gb != null ? `${rep.peak_mem_gb}` : '—'}<span class="sft__gauge-unit">GB</span></span>
          <span class="sft__gauge-label">peak GPU mem</span>
          <span class="sft__gauge-sub">unified-memory watch</span>
        </div>
      </div>

      {/* Loss curve. */}
      <div class="sft__curve">
        <div class="sft__curve-head">
          <span class="sft__curve-title">LoRA SFT loss</span>
          <span class="sft__curve-meta"><code>{rep.run_label || '—'}</code></span>
        </div>
        <LossSpark series={rep.loss_series} />
      </div>

      {/* Checkpoints — what merge_and_export can pick up. */}
      <div class="sft__ckpts">
        <span class="sft__ckpts-label">checkpoints</span>
        {ckpts.length > 0
          ? ckpts.map((it) => <span class="sft__ckpt" key={it}>iter_{String(it).padStart(7, '0')}</span>)
          : <span class="sft__ckpts-none">none yet — first save lands at the save interval</span>}
      </div>

      <p class="sft__foot">
        <b>SFT-init</b> — the format-conditioning warm-start the RLVR loop begins
        from (<code>FK_RL_ADAPTER_INIT</code>). The loss descent is the
        <code> &lt;think&gt;…\boxed&#123;&#125;</code> format being learned; the held-out
        reward gate (see <a href="../reward/">Reward</a>) is what proves it beat base.
      </p>
    </div>
  );
}
