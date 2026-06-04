/** @jsxImportSource preact */
// RewardSignalPane — `<RewardSignalPane>` Preact island for /arena/reward/.
//
// Dogfood AF-3 (astrodynamics-vertical-v1 §1 goal 2; _IDEAS/arena-dogfood-
// feature-extraction.md). The eval-IS-the-reward gauge: it makes the verifier's
// signal visible so the operator can SEE whether the model is producing scorable
// output — the single highest-value safety surface in the RLVR arc.
//
// Today it renders the AV-10 preflight baseline (GET /api/reward-signal →
// evidence/astrodynamics/av10-preflight.json): the step-0 zero of the lineage
// delta. Three numbers carry the meaning:
//   • boxed-rate    — does the base emit a parseable \boxed{} at all? (if ~0, no
//                     amount of RLVR helps — the reward is 0 on every rollout);
//   • reward-rate   — zero-shot held-out correctness (the baseline to beat);
//   • truncation    — AV-R1 firing: <think> opened, hit the token cap, never
//                     closed → the \boxed{} never reaches the verifier. THIS is
//                     the silent no-learning the gauge exists to catch in minutes.
//
// The same report shape is what the C5 per-step RLVR gauge will emit, so this
// pane is reusable. Read-only: an HTTP GET never launches a lane. On the public
// mirror there is no sidecar → static note (isPublicMirrorHost). Reuses the
// resolveSidecarUrl pattern from the standup / jobs / knowledge islands.

import { useEffect, useRef, useState } from 'preact/hooks';
import { resolveSidecarUrl, isPublicMirrorHost } from '../../lib/arena/sidecar.mjs';

const pct = (x) => (x == null ? '—' : `${(Number(x) * 100).toFixed(0)}%`);

const BUCKETS = [
  ['correct', 'correct', 'boxed ✓ & within ±tol'],
  ['boxed_wrong', 'boxed · wrong', 'boxed ✓ but off (SFT closes this)'],
  ['no_answer', 'no answer', 'closed think, never boxed'],
  ['truncated_think', 'truncated', 'AV-R1 — raise max_new_tokens'],
];

export default function RewardSignalPane() {
  const [online, setOnline] = useState(false);
  const [data, setData] = useState(null);
  const baseRef = useRef(null);
  const pollRef = useRef(null);

  async function refresh() {
    const base = baseRef.current;
    if (!base) return;
    try {
      const r = await fetch(`${base}/api/reward-signal`);
      if (r.ok) {
        setData(await r.json());
        setOnline(true);
      }
    } catch (_e) {
      setOnline(false);
    }
  }

  useEffect(() => {
    if (isPublicMirrorHost()) return;
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
      <div class="reward">
        <div class="reward__offline">
          <span class="reward__offline-dot" aria-hidden="true" />
          <div>
            <strong>Cockpit offline.</strong> The reward gauge renders the
            eval-is-reward signal from the latest verifier run — it surfaces only
            against a running sidecar (<code>fieldkit arena up</code> on the
            Spark). It reads a report; it never launches a lane.
          </div>
        </div>
      </div>
    );
  }

  if (data && data.available === false) {
    return (
      <div class="reward">
        <div class="reward__empty">
          <strong>No reward run yet.</strong> Run the AV-10 preflight
          (<code>scripts/astro_bench/preflight_av10.py</code>) or a C5
          <code> rl_run</code> and the step-0 baseline lands here — boxed-rate,
          held-out reward, and the AV-R1 truncation check.
        </div>
      </div>
    );
  }

  const rep = (data && data.report) || {};
  const rows = rep.rows || [];
  const buckets = rep.buckets || {};
  const trunc = Number(rep.truncation_rate || 0);
  const gatePass = rep.gate_pass === true;

  return (
    <div class="reward">
      {/* Three headline gauges — the eval-is-reward signal at a glance. */}
      <div class="reward__gauges">
        <div class="reward__gauge">
          <span class="reward__gauge-val">{pct(rep.boxed_rate)}</span>
          <span class="reward__gauge-label">boxed-rate</span>
          <span class="reward__gauge-sub">emits \boxed{'{}'} at all?</span>
        </div>
        <div class="reward__gauge reward__gauge--reward">
          <span class="reward__gauge-val">{pct(rep.reward_rate_step0)}</span>
          <span class="reward__gauge-label">reward @ step-0</span>
          <span class="reward__gauge-sub">zero-shot held-out (baseline)</span>
        </div>
        <div class="reward__gauge" data-alarm={trunc >= 0.5}>
          <span class="reward__gauge-val">{pct(rep.truncation_rate)}</span>
          <span class="reward__gauge-label">truncation</span>
          <span class="reward__gauge-sub">AV-R1 — silent no-learning</span>
        </div>
      </div>

      {/* Gate verdict + the run's knobs. */}
      <div class="reward__verdict" data-pass={gatePass}>
        <span class="reward__verdict-badge">{gatePass ? 'GATE · PASS' : 'GATE · HOLD'}</span>
        <span class="reward__verdict-rule">boxed&gt;0 ∧ truncation&lt;50%</span>
        <span class="reward__verdict-meta">
          <code>{rep.model || '—'}</code> · n={rep.n ?? '—'} · max_new_tokens={rep.max_new_tokens ?? '—'} · ±{((rep.rel_tol ?? 0.02) * 100).toFixed(0)}%
        </span>
      </div>

      {/* Bucket breakdown — where the completions land. */}
      <div class="reward__buckets">
        {BUCKETS.map(([key, label, hint]) => (
          <div class="reward__bucket" key={key} data-bucket={key} data-warn={key === 'truncated_think' && (buckets[key] || 0) > 0}>
            <span class="reward__bucket-n">{buckets[key] || 0}</span>
            <span class="reward__bucket-label">{label}</span>
            <span class="reward__bucket-hint">{hint}</span>
          </div>
        ))}
      </div>

      {/* Per-row detail — what each held-out prompt produced. */}
      {rows.length > 0 && (
        <table class="reward__rows">
          <thead>
            <tr><th>subtopic</th><th>tier</th><th>gold</th><th>boxed</th><th>bucket</th><th>score</th></tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.task_id} data-bucket={r.bucket}>
                <td><code>{r.subtopic}</code></td>
                <td>{r.tier}</td>
                <td>{r.answer}</td>
                <td class="reward__rows-boxed">{r.boxed || '—'}</td>
                <td>{r.bucket}</td>
                <td class="reward__rows-score" data-hit={r.score >= 1}>{Number(r.score).toFixed(0)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      <p class="reward__foot">
        <b>eval-is-reward</b> — the bench verifier IS the reward (no learned RM).
        This is the step-0 zero of the <code>fieldkit.lineage</code> delta the C5
        RLVR run lifts; the per-step gauge reuses this shape.
      </p>
    </div>
  );
}
