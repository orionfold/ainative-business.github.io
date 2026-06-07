/** @jsxImportSource preact */
// Source pill — Spark-green for local, OpenRouter-blue for cloud. Same colours
// as the compare side-card badges (CompareDuel) so the cockpit reads as one app.
// Shared by LiveLeaderboard (live cockpit runs) and EvalBenchLive (bench-anchored
// live projection) so every leaderboard tier badges lanes identically.

export default function SourceBadge({ source }) {
  const isOR = source === 'openrouter';
  const c = isOR ? '#2750AE' : '#338A17';
  return (
    <span
      title={isOR ? 'Runs in the cloud via OpenRouter' : 'Runs locally on the DGX Spark'}
      style={`flex:none; font-family: var(--arena-mono); font-size:0.55rem; font-weight:700; letter-spacing:0.06em; text-transform:uppercase; padding:1px 7px; border-radius:999px; color:${c}; background:${c}1f; border:1px solid ${c}66;`}
    >
      {isOR ? 'OpenRouter' : 'Spark GPU'}
    </span>
  );
}
