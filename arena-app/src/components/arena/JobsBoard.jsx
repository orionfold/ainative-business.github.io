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
import { useRunContext } from './ProvenanceChip.jsx';
import { anchorMs } from '../../lib/arena/run-context.mjs';

const COLUMNS = [
  { key: 'queued', label: 'Queued', match: (s) => s === 'queued' || s === 'dispatched' },
  { key: 'running', label: 'Running', match: (s) => s === 'running' },
  { key: 'done', label: 'Done', match: (s) => s === 'done' },
  { key: 'failed', label: 'Failed', match: (s) => s === 'failed' || s === 'skipped' },
];

function laneBench(job) {
  const p = job.payload || {};
  if (job.kind === 'sft_run' && p.recipe_path) {
    // AE-29 — the card face names the declarative contract: recipe × mode.
    const tail = String(p.recipe_path).split('/').pop();
    return [tail, p.mode || 'smoke'].join(' × ');
  }
  return [p.lane_id, p.bench_id || p.manifest_slug].filter(Boolean).join(' × ') || job.kind;
}

function fmtEta(s) {
  if (s == null) return '—';
  if (s < 90) return `${Math.round(s)}s`;
  if (s < 5400) return `${Math.round(s / 60)}m`;
  return `${(s / 3600).toFixed(1)}h`;
}

// AE-16 — on-card job identity. Distinct done jobs (C5 smoke vs the full run; two
// byte-identical rag_evals) read as repeats because the card face shows only kind
// + laneBench. A relative enqueue time + a short id + (for rl_run) a run label
// give every card a unique discriminator. Pure render — enqueued_at + id are
// already in the board snapshot.
function fmtAgo(iso) {
  if (!iso) return null;
  const t = Date.parse(iso);
  if (Number.isNaN(t)) return null;
  const s = Math.max(0, (Date.now() - t) / 1000);
  if (s < 90) return `${Math.round(s)}s ago`;
  if (s < 5400) return `${Math.round(s / 60)}m ago`;
  if (s < 172800) return `${(s / 3600).toFixed(1)}h ago`;
  return `${Math.round(s / 86400)}d ago`;
}

function shortId(id) {
  return id ? String(id).slice(0, 8) : null;
}

// A run discriminator for the card face: an explicit payload.run_label wins, else
// for an rl_run derive the step count (result.n_steps live/done, else the
// configured max_steps) so the smoke and the full run never read alike.
function runLabel(job) {
  const p = job.payload || {};
  if (p.run_label) return p.run_label;
  if (job.kind === 'rl_run') {
    const r = job.result || {};
    const n = r.n_steps ?? r.max_steps ?? (p.max_steps != null ? p.max_steps : null);
    return n != null ? `${n}-step` : null;
  }
  return null;
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

// AE-17 (S7) — cloud-run guardrail accounting on a metered eval card. Armed only
// for cloud lanes (a non-loopback base_url), so `result.guardrail` is absent on a
// local run and this renders nothing. Composes with AE-16 card identity + AE-2
// abort visibility + the AE-13 cost chip: an abort badge naming the trip
// condition + a per-run cost/token chip (the per-run sibling of the day cap).
const GUARDRAIL_REASON = {
  teardown: 'teardown',
  stall_timeout: 'stalled',
  cost_cap: 'cost cap',
};
function EvalGuardrailBadge({ result }) {
  const g = result && result.guardrail;
  if (!g) return null;
  const cost = g.run_cost_usd != null ? Number(g.run_cost_usd) : null;
  const toks = (g.tokens_in || 0) + (g.tokens_out || 0);
  // A cost chip whenever the lane was priced (or any spend accrued) — $0.0000 on a
  // zero-token run still tells the operator the guardrail was watching.
  const costChip =
    g.priced || cost ? (
      <span class="jobs__guard-cost" title={`${toks} tokens (in ${g.tokens_in ?? 0} / out ${g.tokens_out ?? 0})`}>
        ${cost != null ? cost.toFixed(4) : '0.0000'}
        {toks ? ` · ${toks} tok` : ''}
      </span>
    ) : null;
  // BUG-3 / AF-29 — loud degradation: a cloud run whose model had no price row
  // ran with the $ cap UNARMED (tokens-only). Silence here is exactly how the
  // cost cap was inert for every current lane until the e2e smoke caught it.
  const unarmedChip =
    g.priced === false ? (
      <span
        class="jobs__guard-unarmed"
        title="no price resolved for this model — the $ cap could not arm (tokens-only run); refresh prices on the Settings pane"
      >
        ⚠ G3 unarmed · tokens-only{toks ? ` · ${toks} tok` : ''}
      </span>
    ) : null;
  // GS-6 — surface the *active thresholds* that governed this run (read from the
  // already-persisted result_json.guardrail), so the config is visible at the run,
  // not just on the Settings pane. 0 ⇒ that guard was off (omit the part).
  const capParts = [];
  if (g.cost_cap_usd) capParts.push(`$${Number(g.cost_cap_usd)}`);
  const stallCap = fmtStallCap(g.stall_timeout_s);
  if (stallCap) capParts.push(stallCap);
  const capChip = capParts.length ? (
    <span class="jobs__guard-capcfg" title="the guardrail config that governed this run (edit on the Settings pane)">
      cap {capParts.join(' / ')}
    </span>
  ) : null;
  if (g.aborted_by) {
    return (
      <div class="jobs__card-guard" data-aborted="true">
        <span class="jobs__guard-flag">⚠ aborted</span>
        <span class="jobs__guard-reason">{GUARDRAIL_REASON[g.aborted_by] || g.aborted_by}</span>
        {g.partial && <span class="jobs__guard-partial">partial · {g.n_scored ?? '—'} scored</span>}
        {unarmedChip}
        {costChip}
        {capChip}
      </div>
    );
  }
  if (!costChip && !capChip && !unarmedChip) return null;
  return (
    <div class="jobs__card-guard">
      {unarmedChip || (
        <span class="jobs__guard-ok" title="cloud-run guardrail: within stall + cost caps">guarded ✓</span>
      )}
      {costChip}
      {capChip}
    </div>
  );
}

// Format a stall window for the badge cap chip (GS-6): whole minutes as `Nm`,
// else seconds as `Ns`; 0/absent ⇒ G2 off (no chip part).
function fmtStallCap(s) {
  const n = Number(s);
  if (!n || Number.isNaN(n)) return null;
  const m = n / 60;
  return Number.isInteger(m) ? `${m}m` : `${n}s`;
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

  // AE-2 — degenerate / no-op step. `n_used==0` (or `trained===false`) is a GRPO
  // step with uniform-reward groups → zero advantage → no gradient: correct with
  // a strong SFT init, but otherwise indistinguishable from a stall. Surface
  // keep-rate / n_used / advantage-spread and badge the no-op explicitly.
  const keepRate = result.keep_rate;
  const nUsed = result.n_used;
  const advSpread = result.adv_spread;
  const hasGrpo = keepRate != null || nUsed != null || advSpread != null;
  const degenerate = hasGrpo && (result.trained === false || nUsed === 0);

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

      {/* AE-2 — GRPO step internals: keep-rate, rollouts used, advantage spread,
          and the explicit no-op badge so a zero-advantage step ≠ a stall. */}
      {hasGrpo && (
        <div class="jobs__rl-grpo" data-degenerate={degenerate}>
          {keepRate != null && <span>keep {(Number(keepRate) * 100).toFixed(0)}%</span>}
          {nUsed != null && <span>n_used {nUsed}</span>}
          {advSpread != null && <span>adv-spread {Number(advSpread).toFixed(3)}</span>}
          {degenerate && <span class="jobs__rl-noop">no update — zero advantage</span>}
        </div>
      )}

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
  const [sftRecipe, setSftRecipe] = useState('');
  const [sftMode, setSftMode] = useState('smoke');
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState('');
  const baseRef = useRef(null);
  const esRef = useRef(null);
  // Per-rl_run rolling (pool, held-out) history for the LA-14 interpreter. Keyed
  // by job id; one sample per distinct step (the result_json is throttled), last
  // ~8 kept. The interpreter reads the trend, not just the latest point.
  const histRef = useRef({});
  // AE-24 run-context — cards enqueued before the run anchor (the instant the
  // operator armed a lane) are labelled "○ prior run" + stale-dimmed (OBS-5).
  // Unanchored ⇒ no anchor ⇒ no claim (cards render exactly as before).
  const runCtx = useRunContext();
  const anchor = anchorMs(runCtx);
  const isPrior = (j) =>
    anchor != null && j.enqueued_at && Date.parse(j.enqueued_at) < anchor;

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

  // Enqueue an SFT run (AE-29 / AF-21 dispatch half). Async-only AND
  // operator-armed: the server never drains it in the request, and the drain
  // brake releases it unless the draining process exports FK_SFT_RUN_ARMED=1
  // — so this click can never start GPU training by itself.
  async function enqueueSft(e) {
    e.preventDefault();
    const rp = sftRecipe.trim();
    if (!rp || busy) return;
    setBusy(true);
    setNote('');
    try {
      const r = await fetch(`${baseRef.current}/api/jobs`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          kind: 'sft_run',
          payload: { recipe_path: rp, mode: sftMode },
          trigger: 'manual',
          dispatch: false,
        }),
      });
      const j = await r.json();
      if (j.coalesced) setNote('an sft_run is already queued');
      else {
        setSftRecipe('');
        setNote(j.note || 'sft_run queued — operator-armed (FK_SFT_RUN_ARMED=1)');
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

      <form class="jobs__dispatch jobs__dispatch--sft" onSubmit={enqueueSft}>
        <span
          class="jobs__dispatch-label"
          title="Enqueue a declarative SFT (LoRA) run — async-only AND operator-armed: it drains only under a process exporting FK_SFT_RUN_ARMED=1 (AE-29); the canonical sft-progress heartbeat feeds the SFT pane live"
        >
          Arm&nbsp;SFT&nbsp;run
        </span>
        <input
          class="jobs__input"
          type="text"
          value={sftRecipe}
          placeholder="recipe YAML path (TrainRecipe contract)"
          maxLength={300}
          disabled={!online}
          onInput={(e) => setSftRecipe(e.currentTarget.value)}
        />
        <select
          class="jobs__input jobs__input--mode"
          value={sftMode}
          disabled={!online}
          onChange={(e) => setSftMode(e.currentTarget.value)}
        >
          <option value="smoke">smoke (recipe smoke_steps)</option>
          <option value="full">full (recipe max_steps)</option>
        </select>
        <button
          type="submit"
          class="jobs__go"
          disabled={!online || busy || !sftRecipe.trim()}
          title="Queued only — never runs in this request; the operator arms the drain with FK_SFT_RUN_ARMED=1"
        >
          {busy ? '…' : 'queue (armed drain)'}
        </button>
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
                  <article class="jobs__card" key={j.id} data-status={j.status} data-prior={isPrior(j)}>
                    <div class="jobs__card-top">
                      <span class="jobs__card-kind">{j.kind}</span>
                      <span class="jobs__card-trigger">{j.trigger}</span>
                    </div>
                    <div class="jobs__card-target">{laneBench(j)}</div>
                    {/* AE-16 — on-card identity: run label · relative time · short id
                        AE-24 — "○ prior run" when enqueued before the run anchor */}
                    <div class="jobs__card-id">
                      {runLabel(j) && <span class="jobs__card-runlabel">{runLabel(j)}</span>}
                      {fmtAgo(j.enqueued_at) && <span class="jobs__card-ago">{fmtAgo(j.enqueued_at)}</span>}
                      {shortId(j.id) && <code class="jobs__card-shortid">{shortId(j.id)}</code>}
                      {isPrior(j) && (
                        <span class="jobs__card-prior" title={`enqueued before the run anchor (lane armed ${runCtx?.run_started || '—'}) — from a prior run`}>
                          ○ prior run
                        </span>
                      )}
                    </div>
                    {j.status === 'running' && j.kind === 'rl_run' && (
                      <RlProgress result={j.result} curriculum={curriculum} hist={histRef.current[j.id]} />
                    )}
                    {/* AE-29 — a running sft_run's live truth is the canonical
                        heartbeat (AE-25); deep-link instead of duplicating it. */}
                    {j.status === 'running' && j.kind === 'sft_run' && (
                      <div class="jobs__card-result">
                        training… <a href="../sft/">follow live in the SFT pane ↗</a>
                      </div>
                    )}
                    {j.status === 'queued' && j.kind === 'sft_run' && (
                      <div class="jobs__card-armed" title="The drain brake holds this until a process exporting FK_SFT_RUN_ARMED=1 drains the queue — a stray background drain can never start training (AE-29)">
                        ⏸ awaiting armed drain · <code>FK_SFT_RUN_ARMED=1</code>
                      </div>
                    )}
                    {j.status === 'done' && j.result && j.result.mean_normalized != null && (
                      <div class="jobs__card-result">
                        acc {Number(j.result.mean_normalized).toFixed(2)} · n {j.result.n_scored ?? '—'}
                      </div>
                    )}
                    {/* AE-17 — cloud-run guardrail accounting (cost chip + abort
                        badge) on a metered eval card; absent on a local run.
                        Failed cards render it too — a BUG-2 reconciled orphan
                        lands `failed` carrying a teardown-shaped guardrail. */}
                    {(j.status === 'done' || j.status === 'failed') && j.kind === 'eval_rerun' && j.result && (
                      <EvalGuardrailBadge result={j.result} />
                    )}
                    {j.status === 'done' && j.kind === 'rl_run' && j.result && (
                      <div class="jobs__card-result" data-aborted={j.result.aborted === true}>
                        {j.result.aborted
                          ? 'OOM-aborted'
                          : `held-out step ${j.result.selected_step ?? '—'}${
                              /* AE-4 — the selected-step → lineage trial back-pointer */
                              j.result.selected_exp_id ? ` (${j.result.selected_exp_id})` : ''
                            } · ${
                              j.result.selected_heldout_score != null
                                ? Number(j.result.selected_heldout_score).toFixed(3)
                                : '—'
                            }`}
                        {j.result.mem_trace && j.result.mem_trace.peak_used_gb != null
                          ? ` · peak ${Math.round(j.result.mem_trace.peak_used_gb)} GB`
                          : ''}
                      </div>
                    )}
                    {/* AE-9 — inter-run upstream lineage: the corpus (C1) + SFT-init
                        (C2) + bench version this run grew from, so a regression
                        traces to its corpus, not just its step (AE-4). */}
                    {j.status === 'done' && j.kind === 'rl_run' && j.result && j.result.upstream &&
                      (j.result.upstream.corpus || j.result.upstream.sft_init || j.result.upstream.bench) && (
                      <div class="jobs__card-lineage" title="upstream lineage — corpus · SFT-init · bench (AE-9)">
                        <span class="jobs__lineage-arrow" aria-hidden="true">↑</span>
                        {j.result.upstream.corpus && (
                          <span class="jobs__lineage-item">corpus <code>{j.result.upstream.corpus}</code></span>
                        )}
                        {j.result.upstream.sft_init && (
                          <span class="jobs__lineage-item">sft-init <code>{j.result.upstream.sft_init}</code></span>
                        )}
                        {j.result.upstream.bench && (
                          <span class="jobs__lineage-item">bench <code>{j.result.upstream.bench}</code></span>
                        )}
                      </div>
                    )}
                    {j.status === 'done' && j.kind === 'rl_run' && j.result && (
                      <RlDebrief result={j.result} curriculum={curriculum} />
                    )}
                    {/* AE-29 — the sft_run completion digest (the live progress
                        already rode the heartbeat; this is the settled record). */}
                    {j.status === 'done' && j.kind === 'sft_run' && j.result && (
                      <div class="jobs__card-result">
                        {j.result.backend || '—'} · iter {j.result.final_iter ?? '—'}
                        {j.result.max_steps != null ? `/${j.result.max_steps}` : ''}
                        {j.result.wall_seconds != null ? ` · ${fmtEta(j.result.wall_seconds)} wall` : ''}
                        {j.result.base_model ? ` · ${String(j.result.base_model).split('/').pop()}` : ''}
                      </div>
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
