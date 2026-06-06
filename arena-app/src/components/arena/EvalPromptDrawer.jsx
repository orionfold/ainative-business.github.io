/** @jsxImportSource preact */
// EvalPromptDrawer — right-anchored slide-over for browsing eval-bench prompts.
//
// Shared by ChatLane + CompareDuel. Lists the available benches (scoped to the
// model(s) in play — the lane's own-vertical bench is suggested first, others
// are reachable as "cross-vertical" so a frontier model can still be thrown at
// any bench). Searchable + family-filterable + paginated (FinanceBench is 150
// rows). Picking a row autofills the composer via `onPick(prompt, benchId)` and
// pins eval mode in the parent.

import { useEffect, useState } from 'preact/hooks';
import { fetchPrompts, benchForLane, scorerLabel } from '../../lib/arena/evals.mjs';

export default function EvalPromptDrawer({ open, onClose, benches, scopeLanes, onPick }) {
  const available = (benches || []).filter((b) => b.available);
  // Suggested benches = the own-vertical bench for any lane in play.
  const suggested = new Set(
    (scopeLanes || []).map((l) => benchForLane(l)).filter(Boolean),
  );

  const [benchId, setBenchId] = useState(null);
  const [q, setQ] = useState('');
  const [family, setFamily] = useState('');
  const [data, setData] = useState(null); // { total, offset, limit, prompts }
  const [prompts, setPrompts] = useState([]);
  const [loading, setLoading] = useState(false);

  // Default the bench to the first suggested (own-vertical) one, else the first
  // available bench, whenever the drawer opens or the scope changes.
  useEffect(() => {
    if (!open) return;
    if (benchId && available.some((b) => b.bench_id === benchId)) return;
    const firstSuggested = available.find((b) => suggested.has(b.bench_id));
    setBenchId((firstSuggested || available[0])?.bench_id || null);
    setFamily('');
    setQ('');
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, (scopeLanes || []).join('|')]);

  // Debounced fetch on bench / search / family change (offset resets to 0).
  useEffect(() => {
    if (!open || !benchId) return;
    let cancelled = false;
    setLoading(true);
    const id = setTimeout(async () => {
      const res = await fetchPrompts(benchId, { q, family, offset: 0, limit: 40 });
      if (cancelled) return;
      setData(res);
      setPrompts(res?.prompts || []);
      setLoading(false);
    }, 220);
    return () => { cancelled = true; clearTimeout(id); };
  }, [open, benchId, q, family]);

  const loadMore = async () => {
    if (!data) return;
    const res = await fetchPrompts(benchId, {
      q, family, offset: prompts.length, limit: 40,
    });
    if (res) {
      setData(res);
      setPrompts((prev) => [...prev, ...(res.prompts || [])]);
    }
  };

  if (!open) return null;

  const benchMeta = available.find((b) => b.bench_id === benchId);
  const families = benchMeta?.families || [];

  return (
    <>
      <div class="eval-drawer__scrim" onClick={onClose} />
      <aside class="eval-drawer bezel" role="dialog" aria-label="Eval prompts">
        <header class="eval-drawer__head">
          <span class="eval-drawer__title">🧪 Eval prompts</span>
          <button type="button" class="eval-drawer__close" onClick={onClose} title="Close (Esc)">✕</button>
        </header>

        <div class="eval-drawer__benchbar">
          {available.length === 0 ? (
            <span class="eval-drawer__empty">No eval benches found on this Spark.</span>
          ) : (
            available.map((b) => (
              <button
                key={b.bench_id}
                type="button"
                class={`eval-drawer__benchpill ${b.bench_id === benchId ? 'is-active' : ''}`}
                onClick={() => setBenchId(b.bench_id)}
                title={`${b.count} prompts · ${b.vertical}`}
              >
                {b.label}
                {suggested.has(b.bench_id) ? (
                  <span class="eval-drawer__benchpill-tag">own</span>
                ) : (
                  <span class="eval-drawer__benchpill-tag eval-drawer__benchpill-tag--x">cross</span>
                )}
              </button>
            ))
          )}
        </div>

        {benchId && (
          <div class="eval-drawer__filterbar">
            <input
              type="search"
              class="eval-drawer__search"
              placeholder="Filter prompts…"
              value={q}
              onInput={(ev) => setQ(ev.currentTarget.value)}
            />
            {families.length > 1 && (
              <select
                class="compare-duel__select eval-drawer__familysel"
                value={family}
                onChange={(ev) => setFamily(ev.currentTarget.value)}
              >
                <option value="">all families</option>
                {families.map((f) => (
                  <option key={f} value={f}>{f}</option>
                ))}
              </select>
            )}
          </div>
        )}

        <div class="eval-drawer__list">
          {loading && prompts.length === 0 ? (
            <div class="eval-drawer__loading">loading…</div>
          ) : prompts.length === 0 ? (
            <div class="eval-drawer__empty">No prompts match.</div>
          ) : (
            prompts.map((p) => (
              <button
                key={p.qid}
                type="button"
                class="eval-row"
                onClick={() => { onPick(p, benchId); onClose(); }}
              >
                <span class="eval-row__q">{p.question}</span>
                <span class="eval-row__meta">
                  {p.family && <span class="eval-badge eval-badge--fam">{p.family}</span>}
                  {/* AE-11 — astro facets: tier + subtopic ride alongside the split. */}
                  {p.tier != null && <span class="eval-badge eval-badge--tier">T{p.tier}</span>}
                  {p.subtopic && <span class="eval-badge eval-badge--sub">{p.subtopic}</span>}
                  <span class={`eval-badge ${p.judge_required ? 'eval-badge--judge' : 'eval-badge--det'}`}>
                    {scorerLabel(p.scorer_kind)}
                  </span>
                  {/* AE-11 — for the numeric astro bench the gold is a short value;
                      preview it inline (these are the operator's own bench). Other
                      benches keep the leak-safe "◆ ref" badge (gold hidden). */}
                  {p.split && p.reference ? (
                    <span class="eval-badge eval-badge--gold" title="gold answer">◆ {p.reference}</span>
                  ) : p.has_reference !== false && p.reference ? (
                    <span class="eval-badge eval-badge--ref">◆ ref</span>
                  ) : null}
                  {p.has_context && (
                    <span class="eval-badge eval-badge--ctx">📎 {p.context_token_hint || 0} tok</span>
                  )}
                </span>
              </button>
            ))
          )}
          {data && prompts.length < data.total && (
            <button type="button" class="eval-drawer__more" onClick={loadMore}>
              Load more ({prompts.length} / {data.total})
            </button>
          )}
        </div>
      </aside>
    </>
  );
}
