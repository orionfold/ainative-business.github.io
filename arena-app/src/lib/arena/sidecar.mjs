// Sidecar URL resolver for the Spark Arena Preact islands.
//
// The FastAPI sidecar binds 127.0.0.1:7866 (loopback). The Astro dev
// server binds :4321 on `host: true` so the operator can hit it from a
// LAN tab. Both cases need to reach the sidecar at the SAME machine the
// browser is talking to:
//
//   browser → 127.0.0.1:4321 (Astro dev)        → sidecar at 127.0.0.1:7866
//   browser → 10.0.0.209:4321 (LAN tab)         → sidecar at 10.0.0.209:7866 (rebind needed)
//   browser → ainative.business/arena/ (mirror) → sidecar OFFLINE (banner)
//
// The default is "same hostname, port 7866". Operators on the public mirror
// see the offline banner ArenaLayout already paints. Override via
// `window.__ARENA_SIDECAR_URL__` for custom setups.
//
// Returns null when the page is being served from a non-loopback host
// AND `window.__ARENA_SIDECAR_URL__` isn't set — that's the "public mirror,
// don't even try to connect" signal.

export const SIDECAR_PORT = 7866;

// Build-time flag injected by astro.config.mjs (`define`). In demo mode the
// cockpit talks to itself: resolveSidecarUrl() returns the page origin so the
// islands issue normal /api/* requests, which demo-mode.mjs's fetch shim
// intercepts and replays from the static fixture bundle. See demo-mode.mjs.
const DEMO = typeof __ARENA_DEMO__ !== 'undefined' && __ARENA_DEMO__;

export function resolveSidecarUrl() {
  if (typeof window === 'undefined') return null;
  if (DEMO) return window.location.origin;
  const override = window.__ARENA_SIDECAR_URL__;
  if (override) return String(override).replace(/\/$/, '');

  const { protocol, hostname } = window.location;
  if (!hostname) return null;
  // Loopback or LAN-IP-on-same-Spark: rebuild the URL with port 7866.
  // The sidecar binds 127.0.0.1 by default — for LAN tabs the operator
  // needs to `fieldkit arena serve --host 0.0.0.0`. That detail lives
  // in HANDOFF; here we just construct the URL the operator expects.
  return `${protocol}//${hostname}:${SIDECAR_PORT}`;
}

export function isPublicMirrorHost() {
  if (typeof window === 'undefined') return false;
  // In demo mode the live surfaces are NOT offline — the shim serves them.
  if (DEMO) return false;
  const h = window.location.hostname;
  if (!h) return false;
  if (h === '127.0.0.1' || h === 'localhost') return false;
  // Spark LAN address per `reference_nvidia_learn_runtime` — kept here
  // so the LAN tab from the laptop also resolves the sidecar URL.
  if (/^10\.0\.0\.\d+$/.test(h)) return false;
  return true;
}
