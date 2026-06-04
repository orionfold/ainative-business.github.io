/** @jsxImportSource preact */
// JobsBoard — `<JobsBoard>` Preact island for /arena/jobs/.
//
// M8 control-plane surface (spec §12). Four columns (queued / running / done /
// failed) fed by GET /api/jobs/stream (SSE, named `jobs` events carrying a full
// board snapshot). A "Dispatch" form re-evals a lane×bench manually; a
// regression banner surfaces when the leaderboard-regression detector has
// auto-enqueued an eval_rerun. Cancel sits on not-yet-running cards.
//
// Privacy + offline: the `jobs` table is on mirror.FORBIDDEN_TABLES — it is
// NEVER exported. On the public mirror there is no sidecar, so this island
// short-circuits (isPublicMirrorHost) to a static "Cockpit offline" board.
// Reuses the EventSource + resolveSidecarUrl pattern from the telemetry / live-
// leaderboard islands.

import { useEffect, useRef, useState } from 'preact/hooks';
import { resolveSidecarUrl, isPublicMirrorHost } from '../../lib/arena/sidecar.mjs';

const COLUMNS = [
  { key: 'queued', label: 'Queued', match: (s) => s === 'queued' || s === 'dispatched' },
  { key: 'running', label: 'Running', match: (s) => s === 'running' },
  { key: 'done', label: 'Done', match: (s) => s === 'done' },
  { key: 'failed', label: 'Failed', match: (s) => s === 'failed' || s === 'skipped' },
];

function laneBench(job) {
  const p = job.payload || {};
  return [p.lane_id, p.bench_id || p.manifest_slug].filter(Boolean).join(' × ') || job.kind;
}

function fmtEta(s) {
  if (s == null) return '—';
  if (s < 90) return `${Math.round(s)}s`;
  if (s < 5400) return `${Math.round(s / 60)}m`;
  return `${(s / 3600).toFixed(1)}h`;
}

// Classify the pool-vs-held-out shape over a short rolling history (LA-14). The
// teach_keys map to the interp-* explainers in the shared curriculum, so the
// one-line read is the SAME source as the deep-dive's :::pitfall. Inversion is
// checked first — it's the dangerous one (RV-4): a pool climbing while held-out
// is flat is the loop about to publish an earlier step.
function classifyInterp(hist) {
  if (!hist || hist.length < 2) return null;
  const last = hist[hist.length - 1];
  const first = hist[0];
  const pool = last.pool;
  const held = last.held;
  if (pool == null || held == null) return null;
  const dPool = pool - (first.pool ?? pool);
  const dHeld = held - (first.held ?? held);
  const eps = 0.01;
  if ((dPool > eps && dHeld <= eps) || pool - held > 0.15) return 'interp-inversion';
  if (dPool > eps && dHeld > eps) return 'interp-generalizing';
  if (Math.abs(dPool) <= eps && Math.abs(dHeld) <= eps && held < 0.6) return 'interp-plateau';
  return null;
}

// A "what / why / watch" guide card (LA-13) drawn from a curriculum entry. Plain
// language first; the optional deep-dive backlink opens the canonical :::block.
function GuideCard({ entry, label }) {
  if (!entry) return null;
  return (
    <details class="jobs__rl-guide" data-kind={entry.kind}>
      <summary>
        <span class="jobs__rl-guide-eyebrow">{label || 'what’s happening'}</span>
        <span class="jobs__rl-guide-term">{entry.term}</span>
      </summary>
      <p class="jobs__rl-guide-what">{entry.what}</p>
      {entry.why && <p class="jobs__rl-guide-why"><b>why</b> {entry.why}</p>}
      {entry.watch && <p class="jobs__rl-guide-watch"><b>watch</b> {entry.watch}</p>}
      {entry.source && (
        <a class="jobs__rl-guide-link" href={entry.source.url} target="_blank" rel="noopener">
          read the deep-dive →
        </a>
      )}
    </details>
  );
}

// A compounding post-run debrief (LA-16) on a completed rl_run — what it did,
// which pitfall it dodged (held-out selection over the pool), or why it aborted,
// and a flag when the held-out lift is notable enough to draw the living-model
// delta chart (the §5 editorial flywheel). Backlinks the shared curriculum.
function RlDebrief({ result, curriculum }) {
  if (!result) return null;
  const held = Array.isArray(result.heldout_scores) ? result.heldout_scores.filter((v) => v != null) : [];
  const lift =
    held.length >= 2 && result.selected_heldout_score != null
      ? result.selected_heldout_score - held[0]
      : null;
  const promotable = !result.aborted && lift != null && lift >= 0.1;
  const heldoutEntry = curriculum['concept-heldout'];
  const oomEntry = curriculum['phase-teardown'];
  return (
    <details class="jobs__rl-debrief" data-promotable={promotable}>
      <summary>
        <span class="jobs__rl-guide-eyebrow">debrief</span>
        <span class="jobs__rl-guide-term">{result.aborted ? 'OOM-aborted run' : 'what this run taught'}</span>
      </summary>
      <p class="jobs__rl-guide-what">
        RLVR on <code>{result.base || '—'}</code>
        {result.vertical ? <> → <code>{result.vertical}</code></> : null}
        {result.n_steps != null ? `, ${result.n_steps} steps.` : '.'}
      </p>
      {result.aborted ? (
        <p class="jobs__rl-guide-why">
          The memory watchdog tore the run down before the kernel could OOM the box. Check the standup's RL
          digest for the peak and the headroom at trip
          {oomEntry && oomEntry.source && (
            <>
              {' '}— <a href={oomEntry.source.url} target="_blank" rel="noopener">the lane envelope</a>
            </>
          )}
          .
        </p>
      ) : (
        <>
          <p class="jobs__rl-guide-watch">
            Shipped <b>held-out step {result.selected_step ?? '—'}</b>
            {result.selected_heldout_score != null ? ` @ ${Number(result.selected_heldout_score).toFixed(3)}` : ''}
            {lift != null ? ` · held-out lift ${lift >= 0 ? '+' : ''}${lift.toFixed(3)} over the first gate` : ''}. Selected
            on <b>{result.selected_on || 'heldout'}</b>, never the pool
            {heldoutEntry && heldoutEntry.source && (
              <>
                {' '}— <a href={heldoutEntry.source.url} target="_blank" rel="noopener">why</a>
              </>
            )}
            .
          </p>
          {promotable && (
            <p class="jobs__rl-promote">
              📈 editorial-promotable — a held-out-winning run can draw the{' '}
              <a href="https://ainative.business/products/living-model/" target="_blank" rel="noopener">living-model</a>{' '}
              delta chart.
            </p>
          )}
        </>
      )}
    </details>
  );
}

// Live rl_run progress (rl-lane-autonomy LA-9) — the throttled result_json the
// loop writes (LA-8), now with the education layer: a per-phase guide card
// (LA-13) and a live pool-vs-held-out interpreter (LA-14), both sourced from the
// shared `explainers` curriculum passed in as a prop.
function RlProgress({ result, curriculum, hist }) {
  if (!result || !result.phase) return null;
  const step = result.step ?? 0;
  const max = result.max_steps ?? 0;
  const pct = max > 0 ? Math.min(100, Math.round((step / max) * 100)) : 0;
  const pool = result.pool_score;
  const held = result.last_heldout;
  const mem = result.mem || {};
  const inversion = pool != null && held != null && pool - held > 0.15;

  const phaseEntry = curriculum[`phase-${result.phase}`];
  const interpKey = classifyInterp(hist);
  const interp = interpKey ? curriculum[interpKey] : null;

  return (
    <div class="jobs__rl" data-phase={result.phase}>
      <div class="jobs__rl-head">
        <span class="jobs__rl-phase">{result.phase}</span>
        <span class="jobs__rl-step">
          step {step}/{max} · ETA {fmtEta(result.eta_s)}
        </span>
      </div>
      <div class="jobs__rl-bar" role="progressbar" aria-valuenow={pct} aria-valuemin={0} aria-valuemax={100}>
        <span class="jobs__rl-fill" style={`width:${pct}%`} />
      </div>
      <div class="jobs__rl-metrics" data-inversion={inversion}>
        <span>pool {pool != null ? Number(pool).toFixed(3) : '—'}</span>
        <span class="jobs__rl-held">held-out {held != null ? Number(held).toFixed(3) : '—'}</span>
        {mem.peak_used_gb != null && <span class="jobs__rl-mem">peak {Math.round(mem.peak_used_gb)} GB</span>}
      </div>

      {/* LA-14 — the live interpreter: a one-line read of the two curves that
          updates as they move. Falls back to the static inversion warn if the
          curriculum prop didn't bake (offline / older shell). */}
      {interp ? (
        <div class="jobs__rl-interp" data-kind={interp.kind}>
          <span class="jobs__rl-interp-term">{interp.term}</span>
          <span class="jobs__rl-interp-watch">{interp.watch || interp.what}</span>
        </div>
      ) : (
        inversion && (
          <div class="jobs__rl-interp" data-kind="pitfall">
            <span class="jobs__rl-interp-term">Pool up, held-out flat</span>
            <span class="jobs__rl-interp-watch">
              the published checkpoint is chosen on the held-out line, never the pool.
            </span>
          </div>
        )
      )}

      {/* LA-13 — the per-phase guide card. */}
      <GuideCard entry={phaseEntry} />
    </div>
  );
}

// Banner verb phrase per confirm-job status — reads as prose, not "is failed".
function confirmPhrase(status) {
  if (status === 'failed') return 'failed to confirm — needs a look';
  if (status === 'running') return 'is running to confirm';
  return 'is queued to confirm'; // queued / dispatched
}

export default function JobsBoard({ curriculum = {} }) {
  const [online, setOnline] = useState(false);
  const [jobs, setJobs] = useState([]);
  const [lane, setLane] = useState('');
  const [bench, setBench] = useState('');
  const [rlBase, setRlBase] = useState('');
  const [rlBench, setRlBench] = useState('');
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState('');
  const baseRef = useRef(null);
  const esRef = useRef(null);
  // Per-rl_run rolling (pool, held-out) history for the LA-14 interpreter. Keyed
  // by job id; one sample per distinct step (the result_json is throttled), last
  // ~8 kept. The interpreter reads the trend, not just the latest point.
  const histRef = useRef({});

  useEffect(() => {
    if (isPublicMirrorHost()) return; // public mirror — static offline board
    const base = resolveSidecarUrl();
    if (!base) return;
    baseRef.current = base;
    setOnline(true);

    let es;
    try {
      es = new EventSource(`${base}/api/jobs/stream`);
    } catch (_e) {
      setOnline(false);
      return;
    }
    esRef.current = es;
    es.addEventListener('jobs', (ev) => {
      try {
        const data = JSON.parse(ev.data);
        const next = Array.isArray(data.jobs) ? data.jobs : [];
        // Append a (pool, held) sample per running rl_run when its step advances,
        // so the LA-14 interpreter has a trend to read (cap the window at 8).
        const hist = histRef.current;
        for (const j of next) {
          if (j.kind !== 'rl_run' || j.status !== 'running' || !j.result) continue;
          const r = j.result;
          const series = hist[j.id] || (hist[j.id] = []);
          const last = series[series.length - 1];
          if (!last || last.step !== r.step) {
            series.push({ step: r.step ?? 0, pool: r.pool_score ?? null, held: r.last_heldout ?? null });
            if (series.length > 8) series.shift();
          }
        }
        setJobs(next);
      } catch (_e) {
        /* ignore malformed frame */
      }
    });
    es.onerror = () => {
      // Sidecar went away mid-session — keep the last snapshot, drop the dot.
      setOnline(false);
    };
    // Prime once over plain fetch so the board paints before the first SSE tick.
    fetch(`${base}/api/jobs`)
      .then((r) => (r.ok ? r.json() : { jobs: [] }))
      .then((j) => setJobs(Array.isArray(j.jobs) ? j.jobs : []))
      .catch(() => {});

    return () => es && es.close();
  }, []);

  async function dispatch(e) {
    e.preventDefault();
    const l = lane.trim();
    const b = bench.trim();
    if (!l || !b || busy) return;
    setBusy(true);
    setNote('');
    try {
      const r = await fetch(`${baseRef.current}/api/jobs`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          kind: 'eval_rerun',
          payload: { lane_id: l, bench_id: b },
          trigger: 'manual',
        }),
      });
      const j = await r.json();
      if (j.coalesced) setNote(`already queued for ${l} × ${b}`);
      else { setLane(''); setBench(''); }
    } catch (_e) {
      setNote('sidecar unreachable');
    } finally {
      setBusy(false);
    }
  }

  // Enqueue an RLVR run (rl-lane-autonomy LA-4). Async-only by contract (RV-6):
  // the server forces dispatch=False, so this NEVER runs the 8.5 h loop in the
  // request — the job waits for the autonomy cron + the RL-lane arbiter.
  async function enqueueRl(e) {
    e.preventDefault();
    const base = rlBase.trim();
    const bp = rlBench.trim();
    if (!base || !bp || busy) return;
    setBusy(true);
    setNote('');
    try {
      const r = await fetch(`${baseRef.current}/api/jobs`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          kind: 'rl_run',
          payload: { base, bench_path: bp, vertical: 'patent-strategist' },
          trigger: 'manual',
          dispatch: false,
        }),
      });
      const j = await r.json();
      if (j.coalesced) setNote('an rl_run is already queued');
      else {
        setRlBase('');
        setRlBench('');
        setNote(j.note || 'rl_run queued — drains under the autonomy cron');
      }
    } catch (_e) {
      setNote('sidecar unreachable');
    } finally {
      setBusy(false);
    }
  }

  async function cancel(id) {
    if (busy) return;
    setBusy(true);
    try {
      await fetch(`${baseRef.current}/api/jobs/${id}`, { method: 'DELETE' });
    } catch (_e) {
      /* swallow */
    } finally {
      setBusy(false);
    }
  }

  // Diff the live leaderboard against the baseline → enqueue a confirming
  // eval_rerun per regression (M8-2). The first scan only sets the baseline.
  async function scanRegressions() {
    if (busy || !online) return;
    setBusy(true);
    setNote('');
    try {
      const r = await fetch(`${baseRef.current}/api/jobs/check-regressions`, { method: 'POST' });
      const j = await r.json();
      const n = (j.enqueued || []).length;
      if (!j.had_baseline) setNote(`baseline set (${j.checked} lanes) — scan again after the next eval`);
      else if (n === 0) setNote(`no regressions across ${j.checked} lanes`);
      else setNote(`${n} regression${n > 1 ? 's' : ''} → eval_rerun queued`);
    } catch (_e) {
      setNote('sidecar unreachable');
    } finally {
      setBusy(false);
    }
  }

  // Most-recent auto-enqueued regression still in flight → banner.
  const regression = jobs.find(
    (j) => j.trigger === 'leaderboard_regression' && j.status !== 'done' && j.status !== 'skipped',
  );

  if (!online && jobs.length === 0) {
    return (
      <div class="jobs">
        <div class="jobs__offline">
          <span class="jobs__offline-dot" aria-hidden="true" />
          <div>
            <strong>Cockpit offline.</strong> The jobs queue is operator-private and
            never mirrored — it surfaces only against a live sidecar
            (<code>fieldkit arena up</code> on the Spark).
          </div>
        </div>
      </div>
    );
  }

  return (
    <div class="jobs">
      {regression && (
        <div class="jobs__regression" role="status">
          <span class="jobs__regression-tag">regression</span>
          <span>
            Leaderboard drop on <code>{laneBench(regression)}</code> — an
            <code> eval_rerun</code> {confirmPhrase(regression.status)}.
          </span>
        </div>
      )}

      <form class="jobs__dispatch" onSubmit={dispatch}>
        <span class="jobs__dispatch-label">Dispatch&nbsp;re-eval</span>
        <input
          class="jobs__input"
          type="text"
          value={lane}
          placeholder="lane id (e.g. patent-q4km)"
          maxLength={200}
          disabled={!online}
          onInput={(e) => setLane(e.currentTarget.value)}
        />
        <input
          class="jobs__input"
          type="text"
          value={bench}
          placeholder="bench id (e.g. patent-bench)"
          maxLength={80}
          disabled={!online}
          onInput={(e) => setBench(e.currentTarget.value)}
        />
        <button type="submit" class="jobs__go" disabled={!online || busy || !lane.trim() || !bench.trim()}>
          {busy ? '…' : 'queue'}
        </button>
        <button
          type="button"
          class="jobs__scan"
          onClick={scanRegressions}
          disabled={!online || busy}
          title="Diff the live leaderboard against the baseline and enqueue a confirming re-eval per regression"
        >
          scan regressions
        </button>
        {note && <span class="jobs__note">{note}</span>}
      </form>

      <form class="jobs__dispatch jobs__dispatch--rl" onSubmit={enqueueRl}>
        <span class="jobs__dispatch-label" title="Enqueue a closed-loop RLVR run — async-only, drains under the autonomy cron (never a synchronous 8.5 h click)">
          Enqueue&nbsp;RLVR&nbsp;run
        </span>
        <input
          class="jobs__input"
          type="text"
          value={rlBase}
          placeholder="base model (e.g. Qwen/Qwen2.5-7B-Instruct)"
          maxLength={200}
          disabled={!online}
          onInput={(e) => setRlBase(e.currentTarget.value)}
        />
        <input
          class="jobs__input"
          type="text"
          value={rlBench}
          placeholder="bench path (gold JSONL, ≥100 rows)"
          maxLength={300}
          disabled={!online}
          onInput={(e) => setRlBench(e.currentTarget.value)}
        />
        <button
          type="submit"
          class="jobs__go"
          disabled={!online || busy || !rlBase.trim() || !rlBench.trim()}
          title="Async-only — queued for the overnight single-lane drain, never run in this request (RV-6)"
        >
          {busy ? '…' : 'queue (async)'}
        </button>
        {/* LA-15 — guided gate: consequence + reversal before the click. */}
        <GuideCard entry={curriculum['gate-enqueue']} label="before you queue" />
      </form>

      <div class="jobs__board">
        {COLUMNS.map((col) => {
          const cards = jobs.filter((j) => col.match(j.status));
          return (
            <section class="jobs__col" key={col.key} data-col={col.key}>
              <header class="jobs__col-head">
                <span class="jobs__col-title">{col.label}</span>
                <span class="jobs__col-count">{cards.length}</span>
              </header>
              <div class="jobs__col-body">
                {cards.length === 0 && <p class="jobs__empty">—</p>}
                {cards.map((j) => (
                  <article class="jobs__card" key={j.id} data-status={j.status}>
                    <div class="jobs__card-top">
                      <span class="jobs__card-kind">{j.kind}</span>
                      <span class="jobs__card-trigger">{j.trigger}</span>
                    </div>
                    <div class="jobs__card-target">{laneBench(j)}</div>
                    {j.status === 'running' && j.kind === 'rl_run' && (
                      <RlProgress result={j.result} curriculum={curriculum} hist={histRef.current[j.id]} />
                    )}
                    {j.status === 'done' && j.result && j.result.mean_normalized != null && (
                      <div class="jobs__card-result">
                        acc {Number(j.result.mean_normalized).toFixed(2)} · n {j.result.n_scored ?? '—'}
                      </div>
                    )}
                    {j.status === 'done' && j.kind === 'rl_run' && j.result && (
                      <div class="jobs__card-result" data-aborted={j.result.aborted === true}>
                        {j.result.aborted
                          ? 'OOM-aborted'
                          : `held-out step ${j.result.selected_step ?? '—'} · ${
                              j.result.selected_heldout_score != null
                                ? Number(j.result.selected_heldout_score).toFixed(3)
                                : '—'
                            }`}
                        {j.result.mem_trace && j.result.mem_trace.peak_used_gb != null
                          ? ` · peak ${Math.round(j.result.mem_trace.peak_used_gb)} GB`
                          : ''}
                      </div>
                    )}
                    {j.status === 'done' && j.kind === 'rl_run' && j.result && (
                      <RlDebrief result={j.result} curriculum={curriculum} />
                    )}
                    {j.status === 'failed' && j.error && (
                      <div class="jobs__card-error" title={j.error}>{j.error}</div>
                    )}
                    {col.key === 'queued' && (
                      <button type="button" class="jobs__cancel" onClick={() => cancel(j.id)} disabled={busy}>
                        cancel
                      </button>
                    )}
                  </article>
                ))}
              </div>
            </section>
          );
        })}
      </div>
    </div>
  );
}
