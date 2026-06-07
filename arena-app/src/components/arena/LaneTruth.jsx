/** @jsxImportSource preact */
// LaneTruth — the AE-21/AE-22 serving-lane system-of-record surface
// (arena-enhancements-v2 Cluster G frontend; OBS-4 / AF-24 / AF-25).
//
// Renders what discovery actually OBSERVED on the box (`GET /api/active-lane`):
// every resident lane with its self-reported model id, which one is active,
// any drift between the operator's selection and reality, and the demoted
// Hermes hint clearly labelled as an assertion. The operator SELECTS a
// discovered lane as active here (`POST /api/active-lane {port}` — AE-22's
// select half; selecting also ANCHORS run-context, AE-23).
//
// v2 cut 4 (AE-31 — AE-22's LAUNCH half): the operator can now LAUNCH a
// recipe-defined GGUF lane (`POST /api/jobs {kind: lane_launch}`) and TEAR a
// discovered lane down (`lane_teardown`) from here. Both are guard-braked
// server-side (launch lock · envelope · ONE-LANE · binary/GGUF — AE-R13);
// a refusal renders as the job's typed `refused:<reason>` error.

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

const JOB_POLL_MS = 2_000;
const JOB_POLL_MAX_MS = 160_000; // past the launcher's 120 s warm ceiling

export default function LaneTruth() {
  const [state, setState] = useState('connecting'); // connecting | live | offline
  const [data, setData] = useState(null);
  const [busyPort, setBusyPort] = useState(null);
  const [err, setErr] = useState(null);
  // AE-31 launch surface
  const [recipes, setRecipes] = useState(null); // null until fetched
  const [recipesPath, setRecipesPath] = useState('');
  const [recipeSel, setRecipeSel] = useState('');
  const [teardownFirst, setTeardownFirst] = useState(false);
  const [anchorOnWarm, setAnchorOnWarm] = useState(true);
  const [op, setOp] = useState(null); // {kind, label, status: 'running'|'done'|'failed', detail}
  const [confirmPort, setConfirmPort] = useState(null); // two-click teardown confirm
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

  async function loadRecipes() {
    const base = baseRef.current;
    if (!base) return;
    try {
      const r = await fetch(`${base}/api/lane-recipes`, {
        headers: { Accept: 'application/json' },
      });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const body = await r.json();
      setRecipes(body.recipes || []);
      setRecipesPath(body.path || '');
      const firstValid = (body.recipes || []).find((x) => x.valid && x.gguf_present);
      if (firstValid) setRecipeSel((cur) => cur || firstValid.name);
    } catch {
      setRecipes([]);
    }
  }

  // Dispatch a lane_launch / lane_teardown job and follow it to done/failed —
  // the form gives live feedback while the Jobs board carries the durable row.
  async function dispatchLaneJob(kind, payload, label) {
    const base = baseRef.current;
    if (!base) return;
    setOp({ kind, label, status: 'running', detail: 'dispatching…' });
    try {
      const r = await fetch(`${base}/api/jobs`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ kind, payload }),
      });
      const created = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(created.detail || `HTTP ${r.status}`);
      if (!created.job_id) throw new Error('coalesced — an identical job is already in flight');
      const t0 = Date.now();
      // poll the job row until it lands
      for (;;) {
        await new Promise((res) => setTimeout(res, JOB_POLL_MS));
        const jr = await fetch(`${base}/api/jobs/${created.job_id}`, {
          headers: { Accept: 'application/json' },
        });
        if (jr.ok) {
          const job = await jr.json();
          if (job.status === 'done') {
            const d = job.result || {};
            const detail =
              kind === 'lane_launch'
                ? `${d.model || d.model_file || ''} live on :${d.port} · warm ${d.warm_seconds}s${d.selected ? ' · run anchored' : ''}`
                : d.already_dead
                  ? `:${d.port} was already dead · state reverted`
                  : `:${d.port} torn down · ${d.freed_gb != null ? `${d.freed_gb} GB freed` : 'memory delta n/a'}`;
            setOp({ kind, label, status: 'done', detail });
            break;
          }
          if (job.status === 'failed') {
            setOp({ kind, label, status: 'failed', detail: job.error || 'failed' });
            break;
          }
          setOp({ kind, label, status: 'running', detail: `${job.status}…` });
        }
        if (Date.now() - t0 > JOB_POLL_MAX_MS) {
          setOp({ kind, label, status: 'failed', detail: 'stopped following — see the Jobs board' });
          break;
        }
      }
    } catch (e) {
      setOp({ kind, label, status: 'failed', detail: String(e.message || e) });
    } finally {
      invalidateRunContext();
      refresh();
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
    loadRecipes();
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
          <strong>No lane resident — arm one below.</strong> Discovery probed the
          lane ports and found nothing serving. Launch a recipe lane from the
          form (guarded: envelope · one-lane · binary checks run pre-flight), or
          start one yourself (e.g. <code>llama-server … --port 8091</code>) and
          it appears here within ~8&nbsp;s, no config edit needed.
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
                {confirmPort === l.port ? (
                  <span class="lanetruth__confirm">
                    <button
                      class="lanetruth__teardown lanetruth__teardown--confirm"
                      disabled={op?.status === 'running'}
                      onClick={() => {
                        setConfirmPort(null);
                        dispatchLaneJob(
                          'lane_teardown',
                          { port: l.port, confirm: true },
                          `tear down :${l.port}`,
                        );
                      }}
                    >
                      confirm teardown
                    </button>
                    <button class="lanetruth__teardown" onClick={() => setConfirmPort(null)}>
                      keep
                    </button>
                  </span>
                ) : (
                  <button
                    class="lanetruth__teardown"
                    disabled={op?.status === 'running'}
                    onClick={() => setConfirmPort(l.port)}
                    title="tear this lane down (verified: process group reaped + port dead; clears the selection if it pointed here)"
                  >
                    tear down
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

      {/* AE-31 — the guarded launch form (the AE-22 launch half) */}
      <div class="lanetruth__launch">
        <div class="lanetruth__launch-head">
          <span class="lanetruth__launch-title">Launch lane</span>
          <span class="lanetruth__sub">
            guarded pre-flight: envelope · one-lane · binary/GGUF (AE-R13)
          </span>
        </div>
        {recipes === null ? (
          <p class="lanetruth__probing">Loading recipes…</p>
        ) : recipes.length === 0 ? (
          <p class="lanetruth__note">
            No launch recipes — author <code>{recipesPath || 'lane-recipes.json'}</code>{' '}
            (name · gguf_path · port · n_ctx · ngl) and they appear here.
          </p>
        ) : (
          <div class="lanetruth__launch-form">
            <select
              class="lanetruth__launch-recipe"
              value={recipeSel}
              disabled={op?.status === 'running'}
              onChange={(e) => setRecipeSel(e.currentTarget.value)}
              aria-label="launch recipe"
            >
              {recipes.map((rc) => (
                <option key={rc.name} value={rc.name} disabled={!rc.valid || !rc.gguf_present}>
                  {rc.name}
                  {rc.valid
                    ? ` — ${rc.model_file} · :${rc.port}${rc.gguf_present ? '' : ' · GGUF missing'}`
                    : ' — invalid recipe'}
                </option>
              ))}
            </select>
            {discovered.length > 0 && (
              <label class="lanetruth__launch-opt" title="tear the resident lane(s) down first — the envelope re-checks against the recovered memory">
                <input
                  type="checkbox"
                  checked={teardownFirst}
                  disabled={op?.status === 'running'}
                  onChange={(e) => setTeardownFirst(e.currentTarget.checked)}
                />
                tear down resident lane first
              </label>
            )}
            <label class="lanetruth__launch-opt" title="select the lane + anchor run-context (AE-23) the moment it warms">
              <input
                type="checkbox"
                checked={anchorOnWarm}
                disabled={op?.status === 'running'}
                onChange={(e) => setAnchorOnWarm(e.currentTarget.checked)}
              />
              anchor run on warm
            </label>
            <button
              class="lanetruth__launch-go"
              disabled={op?.status === 'running' || !recipeSel}
              onClick={() =>
                dispatchLaneJob(
                  'lane_launch',
                  {
                    recipe: recipeSel,
                    teardown_first: teardownFirst,
                    select_on_warm: anchorOnWarm,
                  },
                  `launch ${recipeSel}`,
                )
              }
            >
              {op?.status === 'running' && op.kind === 'lane_launch' ? 'launching…' : 'launch'}
            </button>
          </div>
        )}
        {op && (
          <p class="lanetruth__op" data-state={op.status} role={op.status === 'failed' ? 'alert' : undefined}>
            {op.status === 'running' ? '◌' : op.status === 'done' ? '✓' : '⚠'} {op.label} —{' '}
            {op.detail}
          </p>
        )}
      </div>
    </section>
  );
}
