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
//
// S4 threads two features INTO this spine:
//   • AE-6 corpus-synth live feed — when GET /api/corpus-progress has a live
//     heartbeat (the in-CC-session synth stamping written/target + batch-verify
//     + tier mix), the corpus stage expands into a live strip mirroring the
//     rl_run / SFT progress strip;
//   • AE-7 build-gate cards — the per-stage human gates (base-lock · /usage
//     preflight · held-out>base · AV-10 · promote · publish) render as a gate
//     ledger with an allow/hold/pending state + the consequence of holding,
//     reusing the Standup autonomy-banner pattern (advisory; read-only).
//
// S5 threads one more INTO this spine:
//   • AE-8 bench provenance card — the bench stage's `provenance` projection
//     (version · pool/held-out counts · RV-10 disjointness · self-verifying
//     golds · tier/topic mix · corpus held-out-exclusion) renders as a card, so
//     an eval result traces to its pedigree, not just a prompt count.

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

// AE-7 — the allow/hold control for a build gate. Reuses the Standup
// autonomy-banner pattern: a state indicator (not a mutating button — the spine
// is read-only) that reads `allow` on a passed gate, `hold` on a held one,
// `armed?` while pending.
const GATE_CONTROL = {
  pass: { label: 'allow', tone: 'pass' },
  hold: { label: 'hold', tone: 'hold' },
  pending: { label: 'armed?', tone: 'pending' },
};

// AE-6 — the corpus-synth live feed strip. Mirrors the rl_run / SFT progress
// strip: written/target with a progress bar, the batch-verify tally, the
// ETA-in-batches, and the accumulating tier/topic mix. Surfaces only when
// /api/corpus-progress has a heartbeat (a synth ran); otherwise the corpus
// stage card alone carries the manifest-filled state.
function CorpusStrip({ feed }) {
  if (!feed || feed.available === false || !feed.report) return null;
  const r = feed.report;
  const status = r.status || 'running';
  const isRunning = status !== 'done';
  const pct = r.pct != null ? r.pct : 0;
  const fam = r.family_mix || {};
  const famEntries = Object.entries(fam).sort((a, b) => b[1] - a[1]).slice(0, 8);
  const vf = r.verify_fail;
  const verify =
    vf === 0 ? { label: 'verify ✓', tone: 'pass' }
      : (vf ? { label: `${vf} verify ✗`, tone: 'hold' } : null);
  return (
    <div class="build__corpus" data-running={isRunning} role="status">
      <div class="build__corpus-head">
        <span class="build__corpus-dot" data-running={isRunning} aria-hidden="true" />
        <span class="build__corpus-label">
          CORPUS {status === 'done' ? 'COMPLETE' : 'SYNTH LIVE'}
        </span>
        <span class="build__corpus-run">
          {r.run_label ? <code>{r.run_label}</code> : 'in-CC-session synth'}
        </span>
        {verify && <span class="build__corpus-verify" data-tone={verify.tone}>{verify.label}</span>}
      </div>
      <div class="build__corpus-bar-row">
        <span class="build__corpus-count">
          {r.written}<span class="build__corpus-slash">/{r.target ?? '—'}</span>
          <span class="build__corpus-rows"> rows</span>
        </span>
        <div class="build__corpus-bar" aria-hidden="true">
          <div class="build__corpus-fill" style={`width:${pct}%`} data-done={status === 'done'} />
        </div>
        <span class="build__corpus-eta">
          {status === 'done'
            ? 'synth complete'
            : (r.eta_batches != null
                ? `~${r.eta_batches} batches left · ${r.batch_size}/batch`
                : `${r.batches_done ?? '—'} batches done`)}
        </span>
      </div>
      {famEntries.length > 0 && (
        <div class="build__corpus-mix">
          <span class="build__corpus-mix-label">tier·topic mix</span>
          {famEntries.map(([k, v]) => (
            <span class="build__corpus-chip" key={k}>{k}<b>{v}</b></span>
          ))}
        </div>
      )}
    </div>
  );
}

// AE-8 — the bench provenance card. The Cortex-pane card pattern applied to the
// eval substrate: version · pool/held-out counts · RV-10 disjointness ✓ ·
// self-verifying golds · tier/topic mix · corpus held-out-exclusion proof. A
// pure projection over the bench JSONL (it rides the /api/build bench stage as
// `provenance`), so a wrong answer can be traced to its pedigree: which split,
// disjoint from what, golds that self-verify, a corpus that excluded the held-out.
function BenchProvenance({ prov }) {
  if (!prov || prov.available === false) return null;
  const disjoint = prov.disjoint;
  const corpus = prov.corpus;
  const tierEntries = Object.entries(prov.tier_mix || {}).sort((a, b) => a[0].localeCompare(b[0]));
  const topicEntries = Object.entries(prov.topic_mix || {}).sort((a, b) => b[1] - a[1]);
  return (
    <div class="build__bench" role="status">
      <div class="build__bench-head">
        <span class="build__bench-label">BENCH PROVENANCE</span>
        <span class="build__bench-id">
          <code>{prov.bench_id}</code>{prov.version ? <> <b>{prov.version}</b></> : null}
        </span>
        {prov.tolerance && <span class="build__bench-tol">{prov.tolerance}</span>}
      </div>
      <div class="build__bench-counts">
        <span class="build__bench-count">{prov.pool}<span class="build__bench-cap"> pool</span></span>
        <span class="build__bench-plus">+</span>
        <span class="build__bench-count">{prov.heldout}<span class="build__bench-cap"> held-out</span></span>
        <span class="build__bench-fact" data-tone={disjoint ? 'pass' : 'hold'}>
          {disjoint ? 'disjoint ✓ (RV-10)' : `${prov.overlap} overlap ✗ (RV-10)`}
        </span>
        <span class="build__bench-fact" data-tone={prov.golds_with_si === prov.rows_total ? 'pass' : 'hold'}>
          {prov.golds_with_si}/{prov.rows_total} self-verify ✓
        </span>
      </div>
      {(tierEntries.length > 0 || topicEntries.length > 0) && (
        <div class="build__bench-mix">
          {tierEntries.length > 0 && (
            <>
              <span class="build__bench-mix-label">tier</span>
              {tierEntries.map(([k, v]) => (
                <span class="build__bench-chip" key={`t${k}`}>T{k}<b>{v}</b></span>
              ))}
            </>
          )}
          {topicEntries.length > 0 && (
            <>
              <span class="build__bench-mix-label">topic</span>
              {topicEntries.map(([k, v]) => (
                <span class="build__bench-chip" key={k}>{k}<b>{v}</b></span>
              ))}
            </>
          )}
        </div>
      )}
      {corpus && (
        <div class="build__bench-corpus" data-tone={corpus.excluded ? 'pass' : 'hold'}>
          <span class="build__bench-corpus-dot" data-tone={corpus.excluded ? 'pass' : 'hold'} aria-hidden="true" />
          corpus held-out-{corpus.excluded ? 'excluded ✓' : `LEAK ✗ (${corpus.overlap})`}
          <span class="build__bench-corpus-meta"> · {corpus.rows} SFT-init rows · {corpus.overlap} overlap</span>
        </div>
      )}
    </div>
  );
}

// AE-7 — the build-gate ledger. Every stage that carries a human gate renders a
// row: the gate name, an allow/hold/pending control, and the consequence of
// holding. Advisory + read-only (the spine never mutates arena.db) — the
// Standup autonomy-banner pattern applied to the pipeline's decision points.
function GateLedger({ stages }) {
  const gated = (stages || []).filter((s) => s.gate);
  if (gated.length === 0) return null;
  return (
    <div class="build__gates">
      <div class="build__gates-head">
        <span class="build__gates-title">Build gates</span>
        <span class="build__gates-sub">the human decision points — allow / hold · advisory</span>
      </div>
      <div class="build__gates-list">
        {gated.map((s) => {
          const ctrl = GATE_CONTROL[s.gate_state] || GATE_CONTROL.pending;
          return (
            <div class="build__gate" key={s.key} data-tone={ctrl.tone}>
              <span class="build__gate-stage">
                <span class="build__gate-code">{s.code}</span>
                {s.label}
              </span>
              <span class="build__gate-name">{s.gate}</span>
              <span class="build__gate-ctrl" data-tone={ctrl.tone}>
                <span class="build__gate-ctrl-dot" data-tone={ctrl.tone} aria-hidden="true" />
                {ctrl.label}
              </span>
              {s.gate_consequence && (
                <span class="build__gate-conseq">{s.gate_consequence}</span>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

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
  const [corpus, setCorpus] = useState(null);
  const baseRef = useRef(null);
  const pollRef = useRef(null);

  async function refresh() {
    const base = baseRef.current;
    if (!base) return;
    try {
      // The spine + the corpus feed (AE-6) are independent file-polled reads;
      // fetch both each tick so a running synth's strip tracks alongside the
      // stage grid. The corpus read is best-effort — its failure never blanks
      // the spine.
      const [r, rc] = await Promise.all([
        fetch(`${base}/api/build`),
        fetch(`${base}/api/corpus-progress`).catch(() => null),
      ]);
      if (r.ok) {
        setData(await r.json());
        setOnline(true);
      }
      if (rc && rc.ok) setCorpus(await rc.json());
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

      {/* AE-6 — the corpus-synth live strip; surfaces only with a heartbeat. */}
      <CorpusStrip feed={corpus} />

      {/* AE-8 — the bench provenance card; rides the bench stage's projection. */}
      <BenchProvenance prov={(stages.find((s) => s.key === 'bench') || {}).provenance} />

      <div class="build__grid">
        {stages.map((s) => <StageCard stage={s} key={s.key} />)}
      </div>

      {/* AE-7 — the build-gate ledger (allow/hold · consequence per gate). */}
      <GateLedger stages={stages} />

      <p class="build__foot">
        <b>The spine.</b> Each card is a projection over a feed the cockpit
        already has — the <a href="../sft/">SFT</a> log, the
        <a href="../reward/"> reward</a> report, the bench registry, the
        <a href="../jobs/"> rl_run</a> rows, the lane arbiter — plus a manifest
        for the stages with no live feed. Read-only; <strong>no arena.db
        change</strong>. The <b>corpus live feed</b> (AE-6) lights the strip
        above when an in-session synth is running; the <b>bench provenance</b>
        (AE-8) shows the eval substrate's pedigree (disjoint splits · self-
        verifying golds · held-out-excluded corpus); the <b>gate ledger</b>
        (AE-7) surfaces each human decision point with the consequence of holding.
      </p>
    </div>
  );
}
