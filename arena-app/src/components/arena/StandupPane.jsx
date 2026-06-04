/** @jsxImportSource preact */
// StandupPane — `<StandupPane>` Preact island for /arena/standup/.
//
// M11 autonomous harness (Phase 2, spec §15). The morning-review gate (AH-3),
// fed by GET /api/standup. Four read-only buckets over the existing tables:
//   (a) Spend rail — the M9 SpendDigest (today's $ by lane vs cap), "—" when the
//       cost plane is absent (AH-5);
//   (b) Ran — jobs the overnight cron completed;
//   (c) Regressed — the leaderboard_baseline deltas from the last freshness sweep;
//   (d) Queued — pending jobs, including any the budget governor DEFERRED back to
//       the queue (their budget_<action> audit row records why).
//
// Stage-only by construction (R26): this island renders; it never dispatches or
// pushes. The cron (fieldkit.arena.scheduler.run_drain_cycle) owns the drain; an
// HTTP read never launches a GPU lane. On the public mirror there is no sidecar,
// so it short-circuits (isPublicMirrorHost) to a static note. Reuses the
// resolveSidecarUrl pattern from the jobs / knowledge islands.

import { useEffect, useRef, useState } from 'preact/hooks';
import { resolveSidecarUrl, isPublicMirrorHost } from '../../lib/arena/sidecar.mjs';

// Compact "HH:MM" from an ISO stamp (UTC), or "—".
function clock(iso) {
  if (!iso) return '—';
  const m = String(iso).match(/T(\d{2}:\d{2})/);
  return m ? m[1] : '—';
}

function JobRow({ job }) {
  return (
    <li class="standup__row">
      <code>{job.kind}</code>
      <span>{clock(job.finished_at || job.enqueued_at)}</span>
      <span class="standup__row-status" data-status={job.status}>{job.status}</span>
    </li>
  );
}

export default function StandupPane() {
  const [online, setOnline] = useState(false);
  const [data, setData] = useState(null);
  const baseRef = useRef(null);
  const pollRef = useRef(null);

  async function refresh() {
    const base = baseRef.current;
    if (!base) return;
    try {
      const r = await fetch(`${base}/api/standup`);
      if (r.ok) {
        setData(await r.json());
        setOnline(true);
      }
    } catch (_e) {
      setOnline(false);
    }
  }

  useEffect(() => {
    if (isPublicMirrorHost()) return; // public mirror — static offline note
    const base = resolveSidecarUrl();
    if (!base) return;
    baseRef.current = base;
    setOnline(true);
    refresh();
    pollRef.current = setInterval(refresh, 5000);
    return () => pollRef.current && clearInterval(pollRef.current);
  }, []);

  if (!online && !data) {
    return (
      <div class="standup">
        <div class="standup__offline">
          <span class="standup__offline-dot" aria-hidden="true" />
          <div>
            <strong>Cockpit offline.</strong> The morning standup is an
            operator-private render over the live job queue and cost ledger — it
            surfaces only against a running sidecar (<code>fieldkit arena up</code>
            on the Spark). The overnight cron stages it; the loop never pushes.
          </div>
        </div>
      </div>
    );
  }

  const ran = (data && data.ran) || [];
  const failed = (data && data.failed) || [];
  const regressed = (data && data.regressed) || [];
  const queued = (data && data.queued) || [];
  const spend = (data && data.spend) || { display: '—', has_cost_plane: false };
  const lanes = (spend && spend.by_lane) || [];
  const autonomy = (data && data.autonomy) || { enabled: false };
  const rl = (data && data.rl) || { n_rl_run: 0, display: '—' };

  return (
    <div class="standup">
      {/* Autonomy policy + RL memory digest (rl-lane-autonomy LA-5/11) */}
      <div class="standup__autonomy" data-armed={autonomy.enabled === true}>
        <span class="standup__autonomy-dot" aria-hidden="true" />
        <span class="standup__autonomy-label">
          {autonomy.enabled
            ? `autonomy ON — every ${autonomy.interval_min ?? '?'} min · cap $${autonomy.cap_usd ?? '?'}`
            : 'autonomy OFF — overnight drain not armed'}
        </span>
        {autonomy.enabled ? (
          <span class="standup__autonomy-hint">single-lane · lock-guarded · `autonomy off` to disarm</span>
        ) : (
          <span class="standup__autonomy-hint">arm with <code>fieldkit arena autonomy on</code></span>
        )}
        {rl.n_rl_run > 0 && (
          <span class="standup__autonomy-rl" data-oom={rl.oom_deferred > 0}>RL {rl.display}</span>
        )}
      </div>

      {/* (a) Spend rail — M9 SpendDigest (AH-3), "—" when cost plane absent (AH-5) */}
      <div class="standup__spend" data-over={spend.over_cap === true}>
        <span class="standup__spend-total">{spend.display}</span>
        <span class="standup__spend-label">
          {spend.has_cost_plane ? `spend${spend.over_cap ? ' · over cap' : ''}` : 'cost plane absent'}
        </span>
        {lanes.length > 0 && (
          <span class="standup__spend-lanes">
            {lanes.slice(0, 6).map((l) => (
              <span class="standup__spend-lane" key={l.lane_id}>
                {l.lane_id} <b>${Number(l.cost_usd).toFixed(4)}</b>
              </span>
            ))}
          </span>
        )}
      </div>

      {/* (b–d) Ran / Regressed / Queued + (failed) */}
      <div class="standup__cols">
        <section class="standup__col">
          <header class="standup__col-head">
            <span class="standup__col-title">Ran</span>
            <span class="standup__col-count">{ran.length}</span>
          </header>
          {ran.length === 0 ? (
            <p class="standup__empty">Nothing drained since the last cycle.</p>
          ) : (
            <ul class="standup__list">{ran.slice(0, 12).map((j) => <JobRow job={j} key={j.id} />)}</ul>
          )}
        </section>

        <section class="standup__col" data-warn={regressed.length > 0}>
          <header class="standup__col-head">
            <span class="standup__col-title">Regressed</span>
            <span class="standup__col-count">{regressed.length}</span>
          </header>
          {regressed.length === 0 ? (
            <p class="standup__empty">No leaderboard regressions this pass.</p>
          ) : (
            <ul class="standup__list">
              {regressed.slice(0, 12).map((r, i) => (
                <li class="standup__row standup__row-reg" key={i}>
                  <code>{r.lane_id}</code>
                  <span>{r.bench_id}</span>
                  <span class="standup__row-status">{Number(r.delta).toFixed(3)}</span>
                </li>
              ))}
            </ul>
          )}
        </section>

        <section class="standup__col" data-warn={failed.length > 0}>
          <header class="standup__col-head">
            <span class="standup__col-title">Failed</span>
            <span class="standup__col-count">{failed.length}</span>
          </header>
          {failed.length === 0 ? (
            <p class="standup__empty">No failures.</p>
          ) : (
            <ul class="standup__list">{failed.slice(0, 12).map((j) => <JobRow job={j} key={j.id} />)}</ul>
          )}
        </section>

        <section class="standup__col">
          <header class="standup__col-head">
            <span class="standup__col-title">Queued</span>
            <span class="standup__col-count">{queued.length}</span>
          </header>
          {queued.length === 0 ? (
            <p class="standup__empty">Queue drained.</p>
          ) : (
            <ul class="standup__list">{queued.slice(0, 12).map((j) => <JobRow job={j} key={j.id} />)}</ul>
          )}
        </section>
      </div>

      <p class="standup__staged">
        <b>stage-only</b> — the overnight cron drains + sweeps, then stops at this
        gate. Review, then promote manually. The loop has no push path.
      </p>
    </div>
  );
}
