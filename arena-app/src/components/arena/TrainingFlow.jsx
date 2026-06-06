/** @jsxImportSource preact */
// TrainingFlow — AE-13 (data-flow routing) cockpit landing card.
//
// The dogfood "Baseline finding": an operator parked on the cockpit during a
// live vertical build watches "a static board of yesterday's jobs" — the
// SFT → Reward → RL chain that IS the machine building has no single legible
// thread. This card stitches the three existing feeds into one left→right flow:
//
//   SFT-init  →  Reward (step-0 gauge)  →  RL run
//
// It owns NO new transport: it polls the same endpoints the dedicated panes use
// (/api/sft-progress, /api/reward-signal, /api/jobs) and degrades to "idle" per
// stage when a feed is absent — so on a quiet box it reads "nothing building"
// rather than erroring. Each node links to its full pane. Offline-safe (public
// mirror short-circuits, like CurrentLane).

import { useEffect, useState } from 'preact/hooks';
import { resolveSidecarUrl, isPublicMirrorHost } from '../../lib/arena/sidecar.mjs';

const POLL_MS = 6000;

// base-aware sibling links (relative — robust across dev / baked / mirror).
const LINKS = { sft: '../sft/', reward: '../reward/', rl: '../jobs/' };

function deriveSft(d) {
  if (!d || d.available === false) return { state: 'idle', value: 'no run yet' };
  const rep = d.report || {};
  const status = rep.status || 'init';
  const cur = rep.latest_iter || 0;
  const max = rep.max_iters || 0;
  if (status === 'running' || status === 'starting') {
    return { state: 'running', value: max ? `${cur}/${max} iters` : `${cur} iters` };
  }
  return { state: max ? 'done' : 'idle', value: max ? `done · ${cur} iters` : 'idle' };
}

function deriveReward(d) {
  if (!d || d.available === false) return { state: 'idle', value: 'no run yet' };
  const rep = d.report || {};
  const scored = rep.scored ?? (rep.rows || []).length;
  const total = rep.total ?? rep.n ?? scored;
  if (rep.status === 'running') return { state: 'running', value: `scoring ${scored}/${total}` };
  if (rep.gate_pass === true) return { state: 'done', value: 'gate PASS' };
  if (rep.gate_pass === false) return { state: 'warn', value: 'gate HOLD' };
  return { state: total ? 'done' : 'idle', value: total ? `${scored}/${total} scored` : 'idle' };
}

function deriveRl(jobs) {
  const rl = (jobs || []).filter((j) => j.kind === 'rl_run');
  if (!rl.length) return { state: 'idle', value: 'no run yet' };
  const running = rl.find((j) => j.status === 'running' || j.status === 'dispatched');
  if (running) {
    const r = running.result || {};
    const n = r.n_steps ?? r.max_steps;
    return { state: 'running', value: n != null ? `step ${n}` : 'running' };
  }
  // newest done/failed (list is newest-first).
  const last = rl[0];
  const r = last.result || {};
  if (r.aborted) return { state: 'warn', value: 'OOM-aborted' };
  const held = r.selected_heldout_score;
  return { state: 'done', value: held != null ? `held-out ${(held * 100).toFixed(0)}%` : 'done' };
}

function Node({ stage, label, hint, data }) {
  // Relative href so it works on dev / baked bundle / public mirror alike.
  return (
    <a class="trainflow__node" href={LINKS[stage]} data-state={data.state}>
      <span class="trainflow__node-dot" data-state={data.state} aria-hidden="true" />
      <span class="trainflow__node-label">{label}</span>
      <span class="trainflow__node-value">{data.value}</span>
      <span class="trainflow__node-hint">{hint}</span>
    </a>
  );
}

export default function TrainingFlow() {
  const [sft, setSft] = useState({ state: 'idle', value: '—' });
  const [reward, setReward] = useState({ state: 'idle', value: '—' });
  const [rl, setRl] = useState({ state: 'idle', value: '—' });
  const [online, setOnline] = useState(false);

  useEffect(() => {
    if (isPublicMirrorHost()) return undefined;
    const base = resolveSidecarUrl();
    if (!base) return undefined;
    let cancelled = false;

    const refresh = async () => {
      try {
        const [s, w, j] = await Promise.all([
          fetch(`${base}/api/sft-progress`).then((r) => (r.ok ? r.json() : null)).catch(() => null),
          fetch(`${base}/api/reward-signal`).then((r) => (r.ok ? r.json() : null)).catch(() => null),
          fetch(`${base}/api/jobs?limit=50`).then((r) => (r.ok ? r.json() : null)).catch(() => null),
        ]);
        if (cancelled) return;
        setSft(deriveSft(s));
        setReward(deriveReward(w));
        setRl(deriveRl(j && j.jobs));
        setOnline(true);
      } catch (_e) {
        if (!cancelled) setOnline(false);
      }
    };

    refresh();
    const id = setInterval(() => {
      if (document.visibilityState === 'visible') refresh();
    }, POLL_MS);
    return () => { cancelled = true; clearInterval(id); };
  }, []);

  const building = [sft, reward, rl].some((s) => s.state === 'running');

  return (
    <article class="bezel trainflow">
      <header class="bezel__head">
        <span class="bezel__head-title">Training flow</span>
        <span class={`bezel__head-tag ${building ? 'bezel__head-tag--live' : 'bezel__head-tag--cold'}`}>
          {building ? 'building' : online ? 'idle' : 'offline'}
        </span>
      </header>
      <div class="bezel__body trainflow__chain">
        <Node stage="sft" label="SFT-init" hint="warm-start" data={sft} />
        <span class="trainflow__arrow" aria-hidden="true">→</span>
        <Node stage="reward" label="Reward" hint="step-0 gauge" data={reward} />
        <span class="trainflow__arrow" aria-hidden="true">→</span>
        <Node stage="rl" label="RL run" hint="rl_run job" data={rl} />
      </div>
    </article>
  );
}
