/** @jsxImportSource preact */
// AE-28 — compact feed self-description for panes backed by heartbeat/report
// files. Keep it local and collapsed: operators get source health when a pane
// looks stale, without turning the cockpit into a runbook page.

function fmtAgeMs(ms) {
  if (ms == null) return 'unknown';
  const s = Math.max(0, (Date.now() - ms) / 1000);
  if (s < 90) return `${Math.round(s)}s ago`;
  if (s < 5400) return `${Math.round(s / 60)}m ago`;
  if (s < 129600) return `${Math.round(s / 3600)}h ago`;
  return `${Math.round(s / 86400)}d ago`;
}

const TONE_LABEL = {
  live: 'live',
  ok: 'ok',
  stale: 'stale',
  idle: 'idle',
  warn: 'check',
};

export default function FeedHealth({
  title = 'Feed health',
  tone = 'idle',
  source = null,
  sourceKind = null,
  lastStampMs = null,
  producer = null,
  reads = null,
  cadence = null,
  status = null,
  rows = [],
}) {
  const label = TONE_LABEL[tone] || tone || 'status';
  const shownSource = source || 'none';
  const detailRows = [
    ['source', shownSource],
    sourceKind ? ['kind', sourceKind] : null,
    lastStampMs != null ? ['last stamp', fmtAgeMs(lastStampMs)] : null,
    producer ? ['producer', producer] : null,
    reads ? ['reads', reads] : null,
    cadence ? ['poll', cadence] : null,
    status ? ['state', status] : null,
    ...(rows || []),
  ].filter(Boolean);

  return (
    <details class="feed-health" data-tone={tone}>
      <summary class="feed-health__summary">
        <span class="feed-health__dot" data-tone={tone} aria-hidden="true" />
        <span class="feed-health__title">{title}</span>
        <span class="feed-health__state">{label}</span>
        <code class="feed-health__source">{shownSource}</code>
      </summary>
      <dl class="feed-health__grid">
        {detailRows.map(([k, v]) => (
          <div class="feed-health__row" key={k}>
            <dt>{k}</dt>
            <dd>{v}</dd>
          </div>
        ))}
      </dl>
    </details>
  );
}
