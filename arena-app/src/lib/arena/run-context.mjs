// Run-context client — AE-23 (arena-enhancements-v2 Cluster H).
//
// One module-level cache over GET /api/run-context so every island (the rail
// banner, each AE-24 provenance chip) shares a single fetch per TTL window
// instead of stampeding the sidecar. The payload carries the current run's
// identity (build-manifest vertical/label + the reconciled active lane) and
// the run anchor: `run_started` is the instant the operator selected/armed a
// lane (the AE-19 registry `set_at`). Honest when unanchored — with no
// operator selection there is no run boundary, so `anchored:false` and chips
// show age without claiming "this run" / "prior run".

import { resolveSidecarUrl, isPublicMirrorHost } from './sidecar.mjs';

const TTL_MS = 15_000;
let _cache = { t: 0, v: null, p: null };

/** Fetch (or serve cached) run-context; null on the public mirror / offline. */
export async function fetchRunContext() {
  if (isPublicMirrorHost()) return null;
  const base = resolveSidecarUrl();
  if (!base) return null;
  const now = Date.now();
  if (_cache.v && now - _cache.t < TTL_MS) return _cache.v;
  if (_cache.p) return _cache.p;
  _cache.p = (async () => {
    try {
      const r = await fetch(`${base}/api/run-context`, {
        headers: { Accept: 'application/json' },
      });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const v = await r.json();
      _cache = { t: Date.now(), v, p: null };
      return v;
    } catch {
      _cache.p = null;
      return _cache.v; // stale-ok: keep the last good context over an error
    }
  })();
  return _cache.p;
}

/** The run anchor as epoch-ms, or null when unanchored (no claim possible). */
export function anchorMs(ctx) {
  if (!ctx || !ctx.anchored || !ctx.run_started) return null;
  const t = Date.parse(ctx.run_started);
  return Number.isNaN(t) ? null : t;
}

/** Force the next fetch live (e.g. right after a select/clear POST). */
export function invalidateRunContext() {
  _cache = { t: 0, v: _cache.v, p: null };
}
