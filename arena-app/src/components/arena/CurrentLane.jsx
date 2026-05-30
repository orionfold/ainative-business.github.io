/** @jsxImportSource preact */
// CurrentLane — `<CurrentLane>` Preact island for /arena/.
//
// Fetches `GET /api/lanes` once on mount + re-polls every 10s while the
// tab is visible. Renders the resident-brain card (model / port /
// context / kind) the spec §4.1 calls out as the cockpit's first-fold
// "this is what your Hermes config is pointed at right now."

import { useEffect, useState } from 'preact/hooks';
import { resolveSidecarUrl, isPublicMirrorHost } from '../../lib/arena/sidecar.mjs';

const POLL_INTERVAL_MS = 10_000;

// `compact` (default false) renders a horizontal two-row variant for the
// v0.1.1 cockpit 3-col dense grid: model + endpoint share row 1, ctx +
// max-out + kind share row 2. Skip the roster line entirely so the card
// fits in a ~140px-tall slot beside top-runs + activity feed.
export default function CurrentLane({ compact = false } = {}) {
  const [state, setState] = useState('connecting'); // 'connecting' | 'live' | 'offline'
  const [resident, setResident] = useState(null);
  const [rosterCount, setRosterCount] = useState(null);

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
    let cancelled = false;

    const fetchLanes = async () => {
      try {
        const resp = await fetch(`${base}/api/lanes`, {
          headers: { Accept: 'application/json' },
        });
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
        const body = await resp.json();
        if (cancelled) return;
        setResident(body.resident ?? null);
        setRosterCount(Array.isArray(body.roster) ? body.roster.length : 0);
        setState('live');
      } catch (err) {
        if (cancelled) return;
        setState('offline');
      }
    };

    fetchLanes();
    const id = setInterval(() => {
      if (document.visibilityState === 'visible') fetchLanes();
    }, POLL_INTERVAL_MS);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, []);

  const offline = state === 'offline';

  if (offline) {
    return (
      <div class={`current-lane current-lane--offline${compact ? ' current-lane--compact' : ''}`}>
        <p class="current-lane__status">
          {compact ? (
            <>Resident brain offline — <code>fieldkit arena serve</code>.</>
          ) : (
            <>Sidecar offline — start with <code>fieldkit arena serve</code> on the Spark to see the resident brain.</>
          )}
        </p>
      </div>
    );
  }
  if (state === 'connecting') {
    return (
      <div class={`current-lane current-lane--connecting${compact ? ' current-lane--compact' : ''}`}>
        <p class="current-lane__status">Reading <code>~/.hermes/config.yaml</code>…</p>
      </div>
    );
  }
  if (!resident) {
    return (
      <div class={`current-lane current-lane--empty${compact ? ' current-lane--compact' : ''}`}>
        <p class="current-lane__status">
          {compact ? (
            <>No resident brain. Start a lane and refresh.</>
          ) : (
            <>No resident brain in <code>~/.hermes/config.yaml</code>. Start a lane (<code>start-llama-moe.sh</code> in the brain-bakeoff evidence dir) and refresh.</>
          )}
        </p>
        {!compact && rosterCount != null && (
          <p class="current-lane__roster">
            Roster registered: <strong>{rosterCount}</strong> lanes (from the
            M2 import).
          </p>
        )}
      </div>
    );
  }

  if (compact) {
    // Two-row dense layout for the v0.1.1 cockpit grid. Model + endpoint
    // share row 1; ctx + max-out + kind share row 2. No roster line.
    return (
      <div class="current-lane current-lane--live current-lane--compact">
        <div class="current-lane__row">
          <span class="current-lane__label">Model</span>
          <code class="current-lane__value">{resident.model || '—'}</code>
        </div>
        <div class="current-lane__row">
          <span class="current-lane__label">Endpoint</span>
          <code class="current-lane__value">{resident.base_url || '—'}</code>
        </div>
        <div class="current-lane__row">
          <span class="current-lane__label">Ctx</span>
          <span class="current-lane__value">
            {resident.context_length
              ? `${(resident.context_length / 1024).toFixed(0)}K`
              : '—'}
          </span>
          <span class="current-lane__sep">·</span>
          <span class="current-lane__label">Max</span>
          <span class="current-lane__value">
            {resident.max_tokens
              ? `${(resident.max_tokens / 1024).toFixed(1)}K`
              : '—'}
          </span>
          <span class="current-lane__chip">{resident.kind || 'lane'}</span>
        </div>
      </div>
    );
  }

  return (
    <div class="current-lane current-lane--live">
      <div class="current-lane__row">
        <span class="current-lane__label">Model</span>
        <code class="current-lane__value">{resident.model || '—'}</code>
      </div>
      <div class="current-lane__row">
        <span class="current-lane__label">Endpoint</span>
        <code class="current-lane__value">{resident.base_url || '—'}</code>
        <span class="current-lane__chip">{resident.kind || 'lane'}</span>
      </div>
      <div class="current-lane__row">
        <span class="current-lane__label">Context</span>
        <span class="current-lane__value">
          {resident.context_length
            ? `${resident.context_length.toLocaleString()} tokens`
            : '—'}
        </span>
        <span class="current-lane__sep">·</span>
        <span class="current-lane__label">Max out</span>
        <span class="current-lane__value">
          {resident.max_tokens
            ? `${resident.max_tokens.toLocaleString()} tokens`
            : '—'}
        </span>
      </div>
      {rosterCount != null && (
        <p class="current-lane__roster">
          Roster registered: <strong>{rosterCount}</strong> lanes (from the
          M2 import — swap surface lands at M4).
        </p>
      )}
    </div>
  );
}
