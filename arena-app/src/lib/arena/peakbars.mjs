// peakbars.mjs — fixed-window peak-bar canvas renderer.
//
// Lifted verbatim from the telemetry rail's `drawBars` (TelemetryRail.astro),
// extracted so bundled islands (e.g. CompareDuel) can reuse the exact same
// chart vocabulary. NB: the rail itself keeps its own inline copy — its
// `<script is:inline>` is a classic IIFE (not a module) by design, so it can't
// `import` this; the two must stay byte-identical if either changes.
//
// The chart fills left→right; once SLOTS bars are present the caller FIFOs the
// oldest off. Each value is a finalized peak; `current` (optional) is an
// in-progress bucket drawn dimmed as the rightmost forming bar.

export const SLOTS = 30; // bars across the chart when full

/**
 * @param {HTMLCanvasElement} canvas
 * @param {Array<number|null>} finalized  finalized peak values, oldest first
 * @param {number|null} current           in-progress bucket peak (dimmed), or null
 * @param {{color:string, max?:number|null, band?:number|null}} opts
 */
export function drawBars(canvas, finalized, current, opts) {
  if (!canvas) return;
  const ctx = canvas.getContext('2d');
  if (!ctx) return;
  const W = canvas.width, H = canvas.height;
  ctx.clearRect(0, 0, W, H);
  let max = opts.max;
  if (max != null && opts.band != null) {
    const gy = (opts.band / max) * H;
    ctx.fillStyle = 'oklch(0.83 0.16 78 / 0.10)';
    ctx.fillRect(0, 0, W, gy);
  }
  let vals = finalized.slice();
  if (current != null) vals.push(current);
  if (vals.length > SLOTS) vals = vals.slice(vals.length - SLOTS);
  if (!vals.length) return;
  if (max == null) { max = 1e-9; for (const v of vals) if (v != null) max = Math.max(max, v); }
  const slotW = W / SLOTS;
  const gap = slotW > 3 ? 1 : 0;
  const barW = Math.max(slotW - gap, 1);
  ctx.fillStyle = opts.color;
  for (let i = 0; i < vals.length; i++) {
    const v = vals[i];
    if (v == null) continue;
    const h = Math.max((Math.min(v, max) / max) * (H - 1.5), 1);
    const isForming = current != null && i === vals.length - 1;
    ctx.globalAlpha = isForming ? 0.5 : 1;
    ctx.fillRect(i * slotW, H - h, barW, h);
  }
  ctx.globalAlpha = 1;
}
