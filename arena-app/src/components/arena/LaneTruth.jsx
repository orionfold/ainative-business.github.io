/** @jsxImportSource preact */
// LaneTruth — the AE-21/AE-22 serving-lane system-of-record surface
// (arena-enhancements-v2 Cluster G frontend; OBS-4 / AF-24 / AF-25).
//
// Renders what discovery actually OBSERVED on the box (`GET /api/active-lane`):
// every resident lane with its self-reported model id, which one is active,
// any drift between the operator's selection and reality, and the demoted
// Hermes hint clearly labelled as an assertion. The operator SELECTS a
// discovered lane as active here (`POST /api/active-lane {port}` — AE-22's
// select half; selecting also ANCHORS run-context, AE-23). Launching a lane
// stays a CLI step for now (AE-R13 — the guarded runner phases later);
// the empty state says so instead of pretending.

import { useEffect, useRef, useState } from 'preact/hooks';
import { resolveSidecarUrl, isPublicMirrorHost } from '../../lib/arena/sidecar.mjs';
import { invalidateRunContext } from '../../lib/arena/run-context.mjs';

const POLL_MS = 8_000;

const SOURCE_LABEL = {
  registry: 'operator-selected',
  discovered: 'auto · single live lane',
  'hermes-hint': 'hermes hint · not observed',
  ambiguous: 'ambiguous · pick one',
  none: 'none resident',
};

export default function LaneTruth() {
  const [state, setState] = useState('connecting'); // connecting | live | offline
  const [data, setData] = useState(null);
  const [busyPort, setBusyPort] = useState(null);
  const [err, setErr] = useState(null);
  const baseRef = useRef(null);

  async function refresh() {
    const base = baseRef.current;
    if (!base) return;
    try {
      const r = await fetch(`${base}/api/active-lane`, {
        headers: { Accept: 'application/json' },
      });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      setData(await r.json());
      setState('live');
    } catch {
      setState('offline');
    }
  }

  async function post(body) {
    const base = baseRef.current;
    if (!base) return;
    setErr(null);
    setBusyPort(body.port ?? 'clear');
    try {
      const r = await fetch(`${base}/api/active-lane`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      if (!r.ok) {
        const detail = await r.json().catch(() => ({}));
        throw new Error(detail.detail || `HTTP ${r.status}`);
      }
      setData(await r.json());
      invalidateRunContext(); // selecting/clearing moves the AE-23 run anchor
    } catch (e) {
      setErr(String(e.message || e));
    } finally {
      setBusyPort(null);
    }
  }

  useEffect(() => {
    if (isPublicMirrorHost()) {
      setState('offline');
      return undefined;
    }
    const base = resolveSidecarUrl();
    if (!base) {
      setState('offline');
      return undefined;
    }
    baseRef.current = base;
    refresh();
    const id = setInterval(() => {
      if (document.visibilityState === 'visible') refresh();
    }, POLL_MS);
    return () => clearInterval(id);
  }, []);

  if (state === 'offline' && !data) return null; // public mirror / sidecar down — static catalog stands alone
  if (state === 'connecting') {
    return (
      <section class="lanetruth bezel" aria-label="Serving lanes">
        <p class="lanetruth__probing">Discovering serving lanes…</p>
      </section>
    );
  }

  const active = data?.active || {};
  const discovered = data?.discovered || [];
  const registry = data?.registry || null;
  const drift = data?.drift || null;
  const source = data?.source || 'none';
  const hint = active?.hermes_hint || null;
  const resident = !!active?.base_url && (source === 'registry' || source === 'discovered');

  return (
    <section class="lanetruth bezel" aria-label="Serving lanes — observed">
      <div class="lanetruth__head">
        <span class="lanetruth__title">Serving lanes</span>
        <span class="lanetruth__sub">observed by discovery probe — not a config assertion</span>
        {registry && (
          <button
            class="lanetruth__clear"
            disabled={busyPort != null}
            onClick={() => post({ clear: true })}
            title="forget the selection — revert to pure discovery (also un-anchors run-context)"
          >
            {busyPort === 'clear' ? 'clearing…' : 'clear selection'}
          </button>
        )}
      </div>

      {drift && (
        <div class="lanetruth__drift" role="alert">
          <span class="lanetruth__drift-mark" aria-hidden="true">⚠ drift</span>
          <span>{drift}</span>
        </div>
      )}
      {err && <div class="lanetruth__err" role="alert">⚠ {err}</div>}

      {discovered.length === 0 ? (
        <div class="lanetruth__empty">
          <strong>No lane resident — arm one.</strong> Discovery probed the lane
          ports and found nothing serving. Serving stays an operator step for now
          (one-lane envelope; the guarded launch action phases later): start a
          GGUF lane (e.g. <code>llama-server … --port 8091</code>) and it appears
          here within ~8&nbsp;s, no config edit needed.
        </div>
      ) : (
        <ul class="lanetruth__list">
          {discovered.map((l) => {
            const isActive = resident && active.port === l.port;
            return (
              <li class="lanetruth__lane" data-active={isActive} key={l.port}>
                <span class="lanetruth__dot" data-state="ok" aria-hidden="true" />
                <code class="lanetruth__model">{l.model}</code>
                <span class="lanetruth__meta">
                  :{l.port}
                  {l.context_length ? ` · ctx ${(l.context_length / 1024).toFixed(0)}K` : ''}
                  {l.kind ? ` · ${l.kind.replace('Lane', '')}` : ''}
                </span>
                {isActive ? (
                  <>
                    <span class="lanetruth__active-tag" title={`active — ${SOURCE_LABEL[source] || source}`}>
                      ACTIVE · {SOURCE_LABEL[source] || source}
                    </span>
                    {source === 'discovered' && (
                      // Auto-active (single live lane) is an observation, not a
                      // selection — pinning persists it to the registry, which
                      // also ANCHORS run-context (AE-23: arming = the operator
                      // act that starts "this run").
                      <button
                        class="lanetruth__select"
                        disabled={busyPort != null}
                        onClick={() => post({ port: l.port })}
                        title="pin this lane as the operator selection — anchors run-context (AE-23): pane data older than this instant labels as a prior run"
                      >
                        {busyPort === l.port ? 'pinning…' : 'pin · anchor run'}
                      </button>
                    )}
                  </>
                ) : (
                  <button
                    class="lanetruth__select"
                    disabled={busyPort != null}
                    onClick={() => post({ port: l.port })}
                    title="set this lane active — chat/compare route to it; selecting anchors run-context (AE-23)"
                  >
                    {busyPort === l.port ? 'selecting…' : 'select'}
                  </button>
                )}
              </li>
            );
          })}
        </ul>
      )}

      {source === 'ambiguous' && (
        <p class="lanetruth__note">
          More than one lane is live and none is selected — chat/compare have no
          routing truth until you pick one.
        </p>
      )}

      {hint && hint.base_url && !resident && (
        <p class="lanetruth__hint" title={hint.config_path || '~/.hermes/config.yaml'}>
          <span class="lanetruth__hint-tag">hint</span>
          <code>{hint.model || '—'}</code> on :{hint.port || '—'} per the Hermes
          config — an assertion, not an observation; nothing answers there.
        </p>
      )}
    </section>
  );
}
