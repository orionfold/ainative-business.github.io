/** @jsxImportSource preact */
// GroundedSources — per-turn / per-side live retrieval receipt chips.
//
// grounded-eval-v1 §8: renders the Cortex retrieval receipt (sources, table,
// manifest sha) and — on grounded bench rows, where the receipt carries the
// row's gold_source_ids + the stream-time retrieval_hit — the gold-vs-actual
// read, so a retrieval miss is visible BEFORE any scoring runs. Shared by
// ChatLane (per assistant turn) and CompareDuel (per side card) so the
// grounded read looks identical across both panes.

export default function GroundedSources({ retrieval }) {
  const gold = retrieval.gold_source_ids || [];
  const goldSet = new Set(gold);
  const got = new Set((retrieval.sources || []).map((s) => s.source_id));
  const missing = gold.filter((g) => !got.has(g));
  return (
    <div
      class="chat-turn__sources"
      title={`Live Cortex retrieval · ${retrieval.table} · manifest ${retrieval.manifest_sha256_12} · top-${retrieval.top_k}`}
    >
      <span class="chat-turn__sources-label">🧠 grounded</span>
      {gold.length > 0 && (
        <span
          class={`chat-turn__goldhit ${retrieval.retrieval_hit ? 'chat-turn__goldhit--ok' : 'chat-turn__goldhit--miss'}`}
          title="Gold-vs-actual: did the live top-k surface a gold source for this bench row?"
        >
          {retrieval.retrieval_hit ? '✓ gold retrieved' : '✗ gold missed'}
        </span>
      )}
      {(retrieval.sources || []).map((s) => (
        <span
          key={s.source_id}
          class={`chat-turn__source${goldSet.has(s.source_id) ? ' chat-turn__source--gold' : ''}`}
          title={`${s.citation_label || s.title} · cos dist ${s.dist}${goldSet.has(s.source_id) ? ' · gold source for this eval row' : ''}`}
        >
          <code>{s.source_id}</code>{goldSet.has(s.source_id) ? ' ◆' : ''}
        </span>
      ))}
      {missing.map((g) => (
        <span
          key={`gold-miss-${g}`}
          class="chat-turn__source chat-turn__source--goldmiss"
          title="Gold source for this eval row — NOT in the live top-k (retrieval miss)"
        >
          ◇ <code>{g}</code>
        </span>
      ))}
      {(retrieval.sources || []).length === 0 && (
        <span class="chat-turn__source chat-turn__source--none">no sources retrieved</span>
      )}
    </div>
  );
}
