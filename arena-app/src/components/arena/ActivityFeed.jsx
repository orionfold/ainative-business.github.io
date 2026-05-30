/** @jsxImportSource preact */
// ActivityFeed — `<ActivityFeed>` Preact island for /arena/.
//
// Fetches `GET /api/activity?limit=N` once on mount + re-polls every 15s
// while the tab is visible. Renders the v0.1.1 cockpit's third
// above-the-fold column: redacted recent events from chat_sessions +
// compare_runs + human_prefs (no prompts, no content, no reasoning, no
// notes — see store.recent_chat_sessions / recent_compare_runs /
// recent_human_prefs for the column allowlist).
//
// Public-mirror short-circuit: when running off ainative.business/arena/
// the sidecar is unreachable, so render the operator-private notice and
// don't even try to fetch. Same shape as ChatLane / CurrentLane.

import { useEffect, useState } from 'preact/hooks';
import {
  resolveSidecarUrl,
  isPublicMirrorHost,
} from '../../lib/arena/sidecar.mjs';

const POLL_INTERVAL_MS = 15_000;

function shortId(id, prefixLen = 3) {
  if (!id) return '—';
  const s = String(id);
  // `cs-abc12345` → `abc12345`; if no prefix, take first 8.
  return s.slice(prefixLen, prefixLen + 8) || s.slice(0, 8);
}

function laneShort(lane_id) {
  if (!lane_id) return '—';
  return String(lane_id).replace(/::[a-z0-9-]+$/, '');
}

function relTime(ts, now) {
  if (!ts) return '—';
  try {
    const t = new Date(ts).getTime();
    const n = now ? new Date(now).getTime() : Date.now();
    const dt = Math.max(0, (n - t) / 1000); // seconds
    if (dt < 60) return `${Math.floor(dt)}s`;
    if (dt < 3600) return `${Math.floor(dt / 60)}m`;
    if (dt < 86400) return `${Math.floor(dt / 3600)}h`;
    return `${Math.floor(dt / 86400)}d`;
  } catch (_e) {
    return '—';
  }
}

function fmtPct(v) {
  if (v == null) return '—';
  return `${(v * 100).toFixed(0)}%`;
}

export default function ActivityFeed({ limit = 8 } = {}) {
  const [state, setState] = useState('connecting'); // 'connecting' | 'live' | 'offline' | 'mirror'
  const [events, setEvents] = useState([]);
  const [now, setNow] = useState(null);

  useEffect(() => {
    if (isPublicMirrorHost()) {
      setState('mirror');
      return undefined;
    }
    const base = resolveSidecarUrl();
    if (!base) {
      setState('offline');
      return undefined;
    }
    let cancelled = false;

    const fetchFeed = async () => {
      try {
        const resp = await fetch(`${base}/api/activity?limit=${limit}`, {
          headers: { Accept: 'application/json' },
        });
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
        const body = await resp.json();
        if (cancelled) return;
        setEvents(Array.isArray(body.events) ? body.events : []);
        setNow(body.now || null);
        setState('live');
      } catch (_err) {
        if (cancelled) return;
        setState('offline');
      }
    };

    fetchFeed();
    const id = setInterval(() => {
      if (document.visibilityState === 'visible') fetchFeed();
    }, POLL_INTERVAL_MS);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, [limit]);

  // ---- header is fixed across all states so the column doesn't reflow.
  const header = (
    <header class="bezel__head">
      <span class="bezel__head-title">Recent activity</span>
      <span class="bezel__head-tag bezel__head-tag--live">
        {state === 'live' ? `${events.length} ev` : state}
      </span>
    </header>
  );

  if (state === 'mirror') {
    return (
      <article class="bezel activity-feed">
        {header}
        <div class="bezel__body">
          <p class="activity-feed__status">
            Activity is operator-private — only visible on the Spark itself.
          </p>
        </div>
      </article>
    );
  }
  if (state === 'offline') {
    return (
      <article class="bezel activity-feed">
        {header}
        <div class="bezel__body">
          <p class="activity-feed__status">
            Sidecar offline — start with <code>fieldkit arena serve</code>.
          </p>
        </div>
      </article>
    );
  }
  if (state === 'connecting') {
    return (
      <article class="bezel activity-feed">
        {header}
        <div class="bezel__body">
          <p class="activity-feed__status">Reading feed…</p>
        </div>
      </article>
    );
  }
  if (events.length === 0) {
    return (
      <article class="bezel activity-feed">
        {header}
        <div class="bezel__body">
          <p class="activity-feed__status">
            No turns, compares, or prefs yet. Send a prompt above to seed
            the feed.
          </p>
        </div>
      </article>
    );
  }

  return (
    <article class="bezel activity-feed">
      {header}
      <div class="bezel__body bezel__body--flush">
        {events.map((ev, i) => (
          <ActivityRow key={`${ev.kind}-${ev.ts}-${i}`} ev={ev} now={now} />
        ))}
      </div>
    </article>
  );
}

function ActivityRow({ ev, now }) {
  if (ev.kind === 'chat_session') {
    return (
      <div class="activity-feed__row activity-feed__row--chat">
        <span class="activity-feed__ts" title={ev.ts}>{relTime(ev.ts, now)}</span>
        <span class="activity-feed__glyph activity-feed__glyph--chat">▶</span>
        <span class="activity-feed__body">
          <span class="activity-feed__verb">chat</span>
          {' · '}
          <span class="activity-feed__metric">
            {ev.turn_count} turn{ev.turn_count === 1 ? '' : 's'}
          </span>
          {' · '}
          <code class="activity-feed__id">{shortId(ev.session_id)}</code>
          {ev.lane_id && (
            <span class="activity-feed__chip">{laneShort(ev.lane_id)}</span>
          )}
        </span>
      </div>
    );
  }
  if (ev.kind === 'compare_run') {
    return (
      <div class="activity-feed__row activity-feed__row--compare">
        <span class="activity-feed__ts" title={ev.ts}>{relTime(ev.ts, now)}</span>
        <span class="activity-feed__glyph activity-feed__glyph--compare">▓</span>
        <span class="activity-feed__body">
          <span class="activity-feed__verb">compare</span>
          {' · '}
          <span class="activity-feed__metric">
            {fmtPct(ev.a_score)} vs {fmtPct(ev.b_score)}
          </span>
          {' · '}
          <code class="activity-feed__id">{shortId(ev.run_id)}</code>
          {ev.rubric_id && (
            <span class="activity-feed__chip">{ev.rubric_id}</span>
          )}
        </span>
      </div>
    );
  }
  if (ev.kind === 'human_pref') {
    return (
      <div class="activity-feed__row activity-feed__row--pref">
        <span class="activity-feed__ts" title={ev.ts}>{relTime(ev.ts, now)}</span>
        <span class="activity-feed__glyph activity-feed__glyph--pref">⚑</span>
        <span class="activity-feed__body">
          <span class="activity-feed__verb">pref</span>
          {' · '}
          <span class="activity-feed__metric">
            {ev.winner === 'tie' ? 'tie' : `${ev.winner} win`}
          </span>
          {' · '}
          <code class="activity-feed__id">{shortId(ev.run_id)}</code>
        </span>
      </div>
    );
  }
  return null;
}
