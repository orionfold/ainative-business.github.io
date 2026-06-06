/** @jsxImportSource preact */
// BuildSpine — `<BuildSpine>` Preact island for /arena/build/.
//
// Dogfood AF-1 / AE-5 (arena-enhancements-v1 §6 S3; _IDEAS/arena-dogfood-
// feature-extraction.md). "The vertical I'm building" as a staged pipeline —
// the spine that frames the rest of the dogfood enhancements. Eight stage
// cards (scout · bench · corpus · SFT · smoke · lane · RLVR · publish), each
// with a state, a headline metric, and the operator gate, so the operator sees
// the whole C1..C6 build at a glance instead of a flat job board.
//
// GET /api/build assembles the spine from the signals the cockpit ALREADY has
// (the SFT log feed, the reward report, the bench registry, the rl_run rows,
// the lane arbiter) + an optional operator-authored build-manifest.json for the
// no-live-feed stages (scout / corpus / publish). Read-only: an HTTP GET reads
// files + lists rows, it never launches a lane. The live stages deep-link to
// their dedicated panes (SFT → /arena/sft/, smoke → /arena/reward/, RLVR →
// /arena/jobs/). On the public mirror there's no sidecar → a static note.

import { useEffect, useRef, useState } from 'preact/hooks';
import { resolveSidecarUrl, isPublicMirrorHost } from '../../lib/arena/sidecar.mjs';

// State → visual treatment. `active` is the live/in-flight tone (accent),
// `done` the settled green, `hold`/`blank` the warn/dim edges.
const STATE_META = {
  done: { label: 'done', tone: 'done' },
  active: { label: 'live', tone: 'active' },
  idle: { label: 'idle', tone: 'idle' },
  pending: { label: 'pending', tone: 'pending' },
  hold: { label: 'hold', tone: 'hold' },
  blank: { label: 'absent', tone: 'pending' },
};

const GATE_META = {
  pass: { label: 'PASS', tone: 'pass' },
  hold: { label: 'HOLD', tone: 'hold' },
  pending: { label: 'gate', tone: 'pending' },
};

function StageCard({ stage }) {
  const sm = STATE_META[stage.state] || STATE_META.pending;
  const gate = stage.gate ? (GATE_META[stage.gate_state] || GATE_META.pending) : null;
  const headline = stage.headline && stage.headline !== '—' ? stage.headline : null;
  const isLink = !!stage.href;
  const inner = (
    <>
      <div class="build__card-top">
        <span class="build__card-code">{stage.code}</span>
        <span class="build__card-state" data-tone={sm.tone}>
          <span class="build__card-dot" data-tone={sm.tone} aria-hidden="true" />
          {sm.label}
        </span>
      </div>
      <span class="build__card-label">{stage.label}</span>
      <span class="build__card-headline" data-empty={!headline}>
        {headline || 'no signal yet'}
      </span>
      {stage.detail && <span class="build__card-detail">{stage.detail}</span>}
      {stage.gate && (
        <span class="build__card-gate">
          <span class="build__card-gate-chip" data-tone={gate.tone}>{gate.label}</span>
          <span class="build__card-gate-text">{stage.gate}</span>
        </span>
      )}
      {isLink && <span class="build__card-link" aria-hidden="true">open ↗</span>}
    </>
  );
  const cls = `build__card${isLink ? ' build__card--link' : ''}`;
  return isLink ? (
    <a class={cls} href={stage.href} data-state={stage.state}>{inner}</a>
  ) : (
    <div class={cls} data-state={stage.state}>{inner}</div>
  );
}

export default function BuildSpine() {
  const [online, setOnline] = useState(false);
  const [data, setData] = useState(null);
  const baseRef = useRef(null);
  const pollRef = useRef(null);

  async function refresh() {
    const base = baseRef.current;
    if (!base) return;
    try {
      const r = await fetch(`${base}/api/build`);
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
    // 5 s poll — the live stages (SFT / smoke / RLVR) advance on their own feeds;
    // the spine re-reads them so a running stage's headline tracks without a reload.
    pollRef.current = setInterval(refresh, 5000);
    return () => pollRef.current && clearInterval(pollRef.current);
  }, []);

  if (!online && !data) {
    return (
      <div class="build">
        <div class="build__offline">
          <span class="build__offline-dot" aria-hidden="true" />
          <div>
            <strong>Cockpit offline.</strong> The build spine assembles the
            vertical's C1..C6 pipeline from the live cockpit feeds — it surfaces
            only against a running sidecar (<code>fieldkit arena up</code> on the
            Spark). It reads files + job rows; it never launches a lane.
          </div>
        </div>
      </div>
    );
  }

  const stages = (data && data.stages) || [];
  const label = (data && data.label) || 'the current vertical';
  const done = data && data.stages_done;
  const total = data && data.stages_total;
  const pct = total ? Math.round((done / total) * 100) : 0;

  return (
    <div class="build">
      <div class="build__head">
        <div class="build__head-title">
          <span class="build__head-vertical">{label}</span>
          <span class="build__head-sub">scout → bench → corpus → SFT → smoke → lane → RLVR → publish</span>
        </div>
        <div class="build__head-progress">
          <span class="build__head-count">{done}<span class="build__head-slash">/{total}</span></span>
          <span class="build__head-bar" aria-hidden="true">
            <span class="build__head-fill" style={`width:${pct}%`} />
          </span>
          <span class="build__head-label">stages complete</span>
        </div>
      </div>

      {data && data.manifest_present === false && (
        <p class="build__note">
          No <code>build-manifest.json</code> — the live stages (SFT, smoke, lane,
          RLVR) render off their feeds; scout / corpus / publish stay
          <strong> pending</strong> until a manifest names them
          (<code>FK_ARENA_BUILD_DIR</code>).
        </p>
      )}

      <div class="build__grid">
        {stages.map((s) => <StageCard stage={s} key={s.key} />)}
      </div>

      <p class="build__foot">
        <b>The spine.</b> Each card is a projection over a feed the cockpit
        already has — the <a href="../sft/">SFT</a> log, the
        <a href="../reward/"> reward</a> report, the bench registry, the
        <a href="../jobs/"> rl_run</a> rows, the lane arbiter — plus a manifest
        for the stages with no live feed. Read-only; <strong>no arena.db
        change</strong>. The corpus live feed (AE-6) and bench preview (AE-11)
        land in later sessions.
      </p>
    </div>
  );
}
