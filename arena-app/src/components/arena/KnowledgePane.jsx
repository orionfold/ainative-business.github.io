/** @jsxImportSource preact */
// KnowledgePane — `<KnowledgePane>` Preact island for /arena/cortex/ (data API stays /api/knowledge).
//
// M10 recall layer (Bet 5, spec §14). Four blocks fed by GET /api/knowledge:
//   (a) coverage/freshness — the article_index ⋈ live-index diff (M10-8): the
//       silent 12/63 staleness becomes a standing, actionable number;
//   (b) a Re-index control (full or per-source-class) → POST /api/knowledge/
//       reindex (M10-1), with a chained RAG-eval scoring job;
//   (c) a RAG-eval trend over rag_eval_runs (recall@k by index version,
//       "cosine-only" labelled, M10-7) — the only block the public mirror keeps;
//   (d) a provenance-filtered query console (M10-4/9) — operator-private chunk
//       text, served live only, never mirrored.
//
// Privacy + offline: reindex_runs + chunk text are on mirror.FORBIDDEN_TABLES;
// only rag_eval_runs aggregates publish. On the public mirror there is no
// sidecar, so this island short-circuits (isPublicMirrorHost) to a static note.
// Reuses the resolveSidecarUrl pattern from the jobs / telemetry islands.

import { useEffect, useRef, useState } from 'preact/hooks';
import { resolveSidecarUrl, isPublicMirrorHost } from '../../lib/arena/sidecar.mjs';

const SOURCE_SETS = [
  { key: 'articles', label: 'Articles' },
  { key: 'scout', label: 'Scout' },
  { key: 'lineage', label: 'Lineage' },
  { key: 'all', label: 'All' },
];

function pct(n) {
  return n == null ? '—' : `${Number(n).toFixed(1)}%`;
}

// A tiny inline sparkline over the recall@k trend (oldest → newest).
function Spark({ values }) {
  if (!values.length) return null;
  const w = 120;
  const h = 22;
  const max = Math.max(...values, 1);
  const min = Math.min(...values, 0);
  const span = max - min || 1;
  const step = values.length > 1 ? w / (values.length - 1) : 0;
  const pts = values
    .map((v, i) => `${(i * step).toFixed(1)},${(h - ((v - min) / span) * h).toFixed(1)}`)
    .join(' ');
  return (
    <svg class="kp__spark" viewBox={`0 0 ${w} ${h}`} width={w} height={h} aria-hidden="true">
      <polyline points={pts} fill="none" stroke="currentColor" stroke-width="1.5" />
    </svg>
  );
}

export default function KnowledgePane() {
  const [online, setOnline] = useState(false);
  const [data, setData] = useState(null);
  const [advisor, setAdvisor] = useState(null);
  const [advisorBusy, setAdvisorBusy] = useState(false);
  const [advisorNote, setAdvisorNote] = useState('');
  // Advisor corpus pane (spec §10, AD-AE-11) + routing surface (spec §12, AD-AE-16)
  const [corpus, setCorpus] = useState(null);
  const [routing, setRouting] = useState(null);
  // §14 publish/reject receipt card (spec §12 Receipt)
  const [receipt, setReceipt] = useState(null);
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState('');
  const [sourceSet, setSourceSet] = useState('articles');
  // Query console
  const [q, setQ] = useState('');
  const [prov, setProv] = useState([]); // provenance filter (source classes)
  const [hits, setHits] = useState(null);
  const [qErr, setQErr] = useState('');
  const baseRef = useRef(null);
  const pollRef = useRef(null);

  async function refresh() {
    const base = baseRef.current;
    if (!base) return;
    try {
      const r = await fetch(`${base}/api/knowledge`);
      if (r.ok) {
        setData(await r.json());
        setOnline(true);
      }
      const ar = await fetch(`${base}/api/advisor/preflight`);
      if (ar.ok) {
        setAdvisor(await ar.json());
      }
      const cr = await fetch(`${base}/api/advisor/corpus`);
      if (cr.ok) {
        setCorpus(await cr.json());
      }
      const rr = await fetch(`${base}/api/advisor/routing`);
      if (rr.ok) {
        setRouting(await rr.json());
      }
      const pr = await fetch(`${base}/api/advisor/receipt`);
      if (pr.ok) {
        setReceipt(await pr.json());
      }
    } catch (_e) {
      setOnline(false);
    }
  }

  useEffect(() => {
    if (isPublicMirrorHost()) return; // public mirror — static offline note
    const base = resolveSidecarUrl();
    if (!base) return;
    baseRef.current = base;
    setOnline(true);
    refresh();
    pollRef.current = setInterval(refresh, 5000);
    return () => pollRef.current && clearInterval(pollRef.current);
  }, []);

  async function reindex() {
    if (busy || !online) return;
    setBusy(true);
    setNote('');
    try {
      const r = await fetch(`${baseRef.current}/api/knowledge/reindex`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ source_set: sourceSet, rag_eval: true }),
      });
      const j = await r.json();
      setNote(j.ok ? `re-index queued (${sourceSet}) → RAG-eval chained` : 'enqueue failed');
      setTimeout(refresh, 600);
    } catch (_e) {
      setNote('sidecar unreachable');
    } finally {
      setBusy(false);
    }
  }

  async function runEval() {
    if (busy || !online) return;
    setBusy(true);
    setNote('');
    try {
      await fetch(`${baseRef.current}/api/knowledge/rag-eval`, { method: 'POST' });
      setNote('RAG-eval queued (cosine-only)');
      setTimeout(refresh, 600);
    } catch (_e) {
      setNote('sidecar unreachable');
    } finally {
      setBusy(false);
    }
  }

  async function runAdvisorPreflight(reasoningMode = 'default') {
    if (advisorBusy || !online) return;
    setAdvisorBusy(true);
    setAdvisorNote('');
    try {
      const r = await fetch(`${baseRef.current}/api/advisor/preflight/run`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ reasoning_mode: reasoningMode }),
      });
      const j = await r.json();
      if (r.ok) {
        setAdvisor(j);
        const status = j && j.report && j.report.gate ? j.report.gate.status : 'scored';
        const rows = j && j.results ? j.results.row_count : 0;
        const modeTag = reasoningMode === 'off' ? ' · /no_think' : '';
        setAdvisorNote(`preflight ${status} · ${rows} rows${modeTag}`);
      } else {
        setAdvisorNote(j && j.detail ? j.detail : 'preflight failed');
      }
    } catch (_e) {
      setAdvisorNote('sidecar unreachable');
    } finally {
      setAdvisorBusy(false);
    }
  }

  function toggleProv(s) {
    setProv((cur) => (cur.includes(s) ? cur.filter((x) => x !== s) : [...cur, s]));
  }

  async function runQuery(e) {
    e.preventDefault();
    const query = q.trim();
    if (!query || busy || !online) return;
    setBusy(true);
    setQErr('');
    setHits(null);
    try {
      const r = await fetch(`${baseRef.current}/api/knowledge/query`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query, top_k: 5, provenance: prov.length ? prov : null }),
      });
      if (r.status === 503) {
        setQErr('index offline — re-index to bring the live index up');
      } else if (r.ok) {
        const j = await r.json();
        setHits(j.hits || []);
      } else {
        setQErr('query failed');
      }
    } catch (_e) {
      setQErr('sidecar unreachable');
    } finally {
      setBusy(false);
    }
  }

  if (!online && !data) {
    return (
      <div class="kp">
        <div class="kp__offline">
          <span class="kp__offline-dot" aria-hidden="true" />
          <div>
            <strong>Cockpit offline.</strong> The knowledge index, its re-index
            controls, and the query console are operator-private — they surface
            only against a live sidecar (<code>fieldkit arena up</code> on the
            Spark). Only the aggregate RAG-eval trend is ever mirrored.
          </div>
        </div>
      </div>
    );
  }

  const cov = data && data.coverage;
  const bf = data && data.provenance_backfilled;
  const rag = (data && data.rag_eval_runs) || [];
  const reindexRuns = (data && data.reindex_runs) || [];
  const sources = (data && data.source_classes) || [];
  // trend = oldest→newest recall, like-for-like cosine-only (rerank=0)
  const cosineRuns = rag.filter((r) => Number(r.rerank) === 0 && r.recall_at_k != null);
  const trendVals = cosineRuns.map((r) => Number(r.recall_at_k)).reverse();
  const latest = cosineRuns[0];
  const advisorReport = advisor && advisor.available ? advisor.report || {} : null;
  const advisorGate = (advisorReport && advisorReport.gate) || {};
  const advisorFamilies = Object.entries((advisorReport && advisorReport.families) || {});
  const advisorPackets = (advisor && advisor.packets) || [];
  const advisorResults = advisor && advisor.results;
  const advisorLane = (advisor && advisor.lane) || {};

  return (
    <div class="kp">
      {/* (a) coverage / freshness — the article_index ⋈ index diff (M10-8) */}
      <section class="kp__cov">
        <div class="kp__cov-stat">
          <span class="kp__cov-num">{cov ? pct(cov.coverage_pct) : '—'}</span>
          <span class="kp__cov-lab">coverage</span>
        </div>
        <div class="kp__cov-grid">
          <div><b>{cov ? cov.indexed : '—'}</b><span>indexed</span></div>
          <div><b>{cov ? cov.should_index : '—'}</b><span>should</span></div>
          <div data-warn={cov && cov.missing_n > 0}><b>{cov ? cov.missing_n : '—'}</b><span>stale</span></div>
          <div><b>{cov ? cov.orphan_n : '—'}</b><span>non-prose</span></div>
          <div data-warn={bf && bf.total > 0 && bf.with_provenance < bf.total}>
            <b>{bf ? `${bf.with_provenance}/${bf.total}` : '—'}</b><span>provenance</span>
          </div>
        </div>
        {data && data.index_note && (
          <p class="kp__index-note">{data.index_note}</p>
        )}
        {cov && cov.missing && cov.missing.length > 0 && (
          <details class="kp__missing">
            <summary>{cov.missing.length} stale / un-indexed</summary>
            <div class="kp__missing-list">
              {cov.missing.map((s) => <code key={s}>{s}</code>)}
            </div>
          </details>
        )}
      </section>

      {/* Advisor proof receipt — read-only packet gate, no scoring or dispatch. */}
      <section class="kp__advisor" data-status={advisorGate.status || 'missing'}>
        <header class="kp__advisor-head">
          <div>
            <span class="kp__advisor-title">Advisor preflight</span>
            <span class="kp__advisor-sub">retrieved-context generator gate</span>
          </div>
          <span class="kp__advisor-badge" data-pass={advisorGate.passed === true}>
            {advisorGate.status || 'missing'}
          </span>
        </header>
        {!advisor || advisor.available === false ? (
          <p class="kp__empty">No Advisor preflight receipt found under evidence/orionfold-advisor.</p>
        ) : (
          <>
            <div class="kp__advisor-grid">
              <div><b>{advisorReport.row_count ?? advisorPackets.length}</b><span>packets</span></div>
              <div><b>{advisorReport.model_target || '—'}</b><span>target</span></div>
              <div><b>{advisorResults && advisorResults.available ? advisorResults.row_count : 0}</b><span>results</span></div>
              <div><b>{advisorReport.mode || '—'}</b><span>mode</span></div>
              <div><b>{advisorReport.reasoning_mode || 'default'}</b><span>reasoning</span></div>
            </div>
            <div class="kp__advisor-lane" data-ready={advisorLane.ready === true}>
              <div>
                <span class="kp__advisor-lane-label">active lane</span>
                <code>{advisorLane.model || 'not ready'}</code>
                <span>{advisorLane.base_url || advisorLane.reason || 'no lane'}</span>
              </div>
              <button
                type="button"
                class="kp__advisor-run"
                disabled={!online || advisorBusy || advisorLane.ready !== true}
                onClick={() => runAdvisorPreflight('default')}
                title={advisorLane.ready === true ? 'Run the tracked Advisor packets against the active lane' : advisorLane.reason || 'No active lane'}
              >
                {advisorBusy ? 'running…' : 'run preflight'}
              </button>
              <button
                type="button"
                class="kp__advisor-run"
                disabled={!online || advisorBusy || advisorLane.ready !== true}
                onClick={() => runAdvisorPreflight('off')}
                title={advisorLane.ready === true ? 'Run with the Nemotron /no_think reasoning-suppression control (writes a -nothink receipt)' : advisorLane.reason || 'No active lane'}
              >
                {advisorBusy ? 'running…' : 'run /no_think'}
              </button>
            </div>
            {(advisorNote || (advisorLane && advisorLane.reason)) && (
              <p class="kp__advisor-note">{advisorNote || advisorLane.reason}</p>
            )}
            {advisorFamilies.length > 0 && (
              <div class="kp__advisor-families">
                {advisorFamilies.map(([family, n]) => (
                  <span class="kp__advisor-family" key={family}>{family}: {n}</span>
                ))}
              </div>
            )}
            <p class="kp__advisor-rule">{advisorGate.threshold || 'No threshold recorded.'}</p>
            {advisorPackets.length > 0 && (
              <details class="kp__advisor-packets">
                <summary>{advisorPackets.length} packet summaries</summary>
                <ol>
                  {advisorPackets.map((pkt) => (
                    <li key={pkt.task_id}>
                      <code>{pkt.task_id}</code>
                      <span>{pkt.family}</span>
                      <span>{pkt.expected_behavior}</span>
                      <span>{pkt.source_count ?? '—'} sources</span>
                    </li>
                  ))}
                </ol>
              </details>
            )}
            {advisorResults && advisorResults.available && advisorResults.rows && advisorResults.rows.length > 0 && (
              <details class="kp__advisor-results" open>
                <summary>
                  {advisorResults.row_count} scored rows
                  {advisorResults.failures ? ` · ${advisorResults.failures} failing` : ' · all passing'}
                </summary>
                <ol>
                  {advisorResults.rows.map((row) => (
                    <li key={row.task_id} data-pass={row.passed === true}>
                      <code>{row.task_id}</code>
                      <span>{row.family}</span>
                      <span>{row.expected_behavior}</span>
                      <span>{row.passed === true ? 'pass' : row.passed === false ? 'fail' : 'unknown'}</span>
                      <span>{(row.cited_source_ids || []).length} cited</span>
                    </li>
                  ))}
                </ol>
              </details>
            )}
            <p class="kp__advisor-source">
              receipt <code>{advisor.source}</code>
              {advisorResults && advisorResults.available
                ? ` · results ${advisorResults.row_count} rows`
                : ' · no scored result artifact yet'}
            </p>
          </>
        )}
      </section>

      {/* Advisor publish/reject receipt — spec §12 Receipt card. Read-only
          projection of the §14 verdict assembled by publish_receipt.py. */}
      {receipt && receipt.available && (
        <section class="kp__advisor" data-status="ok">
          <header class="kp__advisor-head">
            <div>
              <span class="kp__advisor-title">Advisor publish receipt</span>
              <span class="kp__advisor-sub">§14 verdict — every gate re-verified against evidence at assembly</span>
            </div>
            <span class="kp__advisor-badge" data-pass={receipt.decision && receipt.decision.verdict === 'PROMOTED'}>
              {receipt.decision ? receipt.decision.verdict : '—'}
            </span>
          </header>
          <div class="kp__advisor-lane" data-ready={true}>
            <div>
              <span class="kp__advisor-lane-label">promoted lane</span>
              <code>{receipt.decision && receipt.decision.model}</code>
              <span>{receipt.decision && receipt.decision.role}</span>
            </div>
          </div>
          <div class="kp__advisor-families">
            {Object.entries(receipt.gates || {}).map(([g, v]) => (
              <span class="kp__advisor-family" key={g} data-pass={v.passed === true}>
                {v.passed === true ? '✓' : '✗'} {g.replace(/_/g, ' ')}
              </span>
            ))}
          </div>
          {receipt.decision && (receipt.decision.why || []).length > 0 && (
            <details class="kp__advisor-packets">
              <summary>why promoted · {(receipt.lanes_considered || []).length} lanes considered</summary>
              <ol>
                {receipt.decision.why.map((w, i) => <li key={i}><span>{w}</span></li>)}
              </ol>
            </details>
          )}
          <p class="kp__advisor-source">
            receipt <code>advisor-publish-receipt-{receipt.version}.json</code>
            {' · '}manifest <code>{receipt.provenance && receipt.provenance.manifest_sha256_12}</code>
            {' · '}bench <code>{receipt.provenance && receipt.provenance.bench_sha256_12}</code>
          </p>
        </section>
      )}

      {/* Advisor corpus pack — spec §10 corpus pane (AD-AE-11). Read-only:
          manifest digest, both recall-gate receipts, the OA-NV-8 swap fixture,
          and the SFT-corpus handoff reports. */}
      <section class="kp__advisor" data-status={corpus && corpus.available ? 'ok' : 'missing'}>
        <header class="kp__advisor-head">
          <div>
            <span class="kp__advisor-title">Advisor corpus pack</span>
            <span class="kp__advisor-sub">manifest · recall gates · swap fixture · SFT handoff</span>
          </div>
          <span
            class="kp__advisor-badge"
            data-pass={!!(corpus && corpus.recall_live && corpus.recall_live.gate_passed)}
          >
            {corpus && corpus.recall_live && corpus.recall_live.available
              ? (corpus.recall_live.gate_passed ? 'recall green' : 'recall FAILING')
              : 'no recall receipt'}
          </span>
        </header>
        {!corpus || corpus.available === false ? (
          <p class="kp__empty">No corpus-pack manifest found under evidence/orionfold-advisor.</p>
        ) : (
          <>
            <div class="kp__advisor-grid">
              <div><b>{corpus.manifest.source_count}</b><span>sources</span></div>
              <div><b>{corpus.manifest.sha256_12}</b><span>manifest</span></div>
              <div><b>{corpus.recall_bm25.available ? corpus.recall_bm25.source_recall['@5'] : '—'}</b><span>bm25 @5</span></div>
              <div><b>{corpus.recall_live.available ? corpus.recall_live.source_recall['@5'] : '—'}</b><span>live @5</span></div>
              <div><b>{corpus.recall_live.available ? corpus.recall_live.heldout_source_recall['@5'] : '—'}</b><span>held-out @5</span></div>
            </div>
            {corpus.swap_fixture && corpus.swap_fixture.available && (
              <p class="kp__advisor-rule">
                OA-NV-8 corpus swap: synthetic fixture pack ({corpus.swap_fixture.source_count} sources,
                {' '}{corpus.swap_fixture.row_count} gold rows) through the same scorer —{' '}
                {corpus.swap_fixture.gate_passed ? 'gate PASS' : 'gate FAIL'} @5 ={' '}
                {corpus.swap_fixture.source_recall['@5']} (manifest {corpus.swap_fixture.manifest_sha256_12})
              </p>
            )}
            {(corpus.sft_corpora || []).length > 0 && (
              <div class="kp__advisor-families">
                {corpus.sft_corpora.map((s) => (
                  <span class="kp__advisor-family" key={s.version}>
                    SFT {s.version}: {s.rows_kept} rows · {s.rejects} rejects · sha {s.corpus_sha256_12}
                  </span>
                ))}
              </div>
            )}
            {corpus.manifest.by_class && (
              <details class="kp__advisor-packets">
                <summary>source composition</summary>
                <div class="kp__advisor-families">
                  {Object.entries(corpus.manifest.by_class).map(([k, n]) => (
                    <span class="kp__advisor-family" key={k}>{k}: {n}</span>
                  ))}
                </div>
              </details>
            )}
          </>
        )}
      </section>

      {/* Advisor routing & cost — spec §12 route-tier/ledger surface (AD-AE-16).
          Read-only projection of the §13.F bakeoff receipt + hosted-escalation
          ledger; the bakeoff itself stays a deterministic tracked script. */}
      <section class="kp__advisor" data-status={routing && routing.available ? 'ok' : 'missing'}>
        <header class="kp__advisor-head">
          <div>
            <span class="kp__advisor-title">Advisor routing &amp; cost</span>
            <span class="kp__advisor-sub">governed escalation — tiers, providers, spend, data policy</span>
          </div>
          <span
            class="kp__advisor-badge"
            data-pass={!!(routing && routing.available && routing.configs && Object.values(routing.configs).every((c) => c.pass_rate === 1))}
          >
            {routing && routing.available
              ? `router rev ${routing.router ? routing.router.revision : '—'}`
              : 'no bakeoff receipt'}
          </span>
        </header>
        {!routing || routing.available === false ? (
          <p class="kp__empty">No route-bakeoff receipt found under evidence/orionfold-advisor.</p>
        ) : (
          <>
            <div class="kp__advisor-grid">
              {Object.entries(routing.configs || {}).map(([cfg, c]) => (
                <div key={cfg}>
                  <b>{c.pass}/{routing.slice ? routing.slice.rows : '—'}</b>
                  <span>{cfg} · ${Number(c.hosted_cost_usd || 0).toFixed(4)}</span>
                </div>
              ))}
              <div>
                <b>{routing.private_state_blocked}</b>
                <span>private-state blocked</span>
              </div>
            </div>
            {routing.governance && (
              <p class="kp__advisor-rule">
                T4 governance: allowed {routing.governance.allowed_models.join(', ')} · cap ${routing.governance.cap_usd} ·{' '}
                {routing.governance.data_policy}
              </p>
            )}
            {(routing.escalations || []).length > 0 && (
              <details class="kp__advisor-results" open>
                <summary>{routing.escalations.length} hosted escalation{routing.escalations.length === 1 ? '' : 's'}</summary>
                <ol>
                  {routing.escalations.map((e) => (
                    <li key={e.task_id}>
                      <code>{e.task_id}</code>
                      <span>{e.trigger}</span>
                      {(e.tiers || []).map((t) => (
                        <span key={t.config} data-pass={t.passed === true}>
                          {t.config}: {t.model} · {t.status || (t.passed === true ? 'pass' : t.passed === false ? 'fail' : '—')}
                          {t.cost_usd != null ? ` · $${Number(t.cost_usd).toFixed(4)}` : ''}
                        </span>
                      ))}
                    </li>
                  ))}
                </ol>
              </details>
            )}
            {routing.router && (
              <p class="kp__advisor-source">
                policy: {routing.router.policy}
              </p>
            )}
          </>
        )}
      </section>

      {/* (b) re-index controls (M10-1) */}
      <div class="kp__controls">
        <span class="kp__controls-label">Re-index</span>
        <select
          class="kp__select"
          value={sourceSet}
          disabled={!online || busy}
          onChange={(e) => setSourceSet(e.currentTarget.value)}
        >
          {SOURCE_SETS.map((s) => <option key={s.key} value={s.key}>{s.label}</option>)}
        </select>
        <button type="button" class="kp__go" disabled={!online || busy} onClick={reindex}>
          {busy ? '…' : 'rebuild'}
        </button>
        <button type="button" class="kp__scan" disabled={!online || busy} onClick={runEval}
          title="Score the live index against the in-repo qa-eval gold set (cosine-only)">
          run RAG-eval
        </button>
        {note && <span class="kp__note">{note}</span>}
      </div>

      {/* (c) RAG-eval trend (M10-7) — cosine-only labelled */}
      <section class="kp__trend">
        <header class="kp__trend-head">
          <span class="kp__trend-title">RAG-eval trend</span>
          <span class="kp__cosine">cosine-only · GB10</span>
        </header>
        {cosineRuns.length === 0 ? (
          <p class="kp__empty">No eval runs yet — rebuild + score to populate the trend.</p>
        ) : (
          <div class="kp__trend-body">
            <div class="kp__trend-spark"><Spark values={trendVals} /></div>
            <div class="kp__trend-now">
              <span class="kp__trend-recall">recall@k {Number(latest.recall_at_k).toFixed(3)}</span>
              <span class="kp__trend-sub">slug {Number(latest.slug_recall_at_k).toFixed(3)} · {latest.qa_set}</span>
            </div>
          </div>
        )}
      </section>

      {/* (d) provenance-filtered query console (M10-4/9) */}
      <section class="kp__query">
        <form class="kp__query-form" onSubmit={runQuery}>
          <input
            class="kp__input"
            type="text"
            value={q}
            placeholder="ask the Second Brain…"
            maxLength={2000}
            disabled={!online}
            onInput={(e) => setQ(e.currentTarget.value)}
          />
          <button type="submit" class="kp__go" disabled={!online || busy || !q.trim()}>
            {busy ? '…' : 'query'}
          </button>
        </form>
        {sources.length > 0 && (
          <div class="kp__prov">
            <span class="kp__prov-label">trust tier</span>
            {sources.map((s) => (
              <button
                key={s}
                type="button"
                class={`kp__prov-chip${prov.includes(s) ? ' is-on' : ''}`}
                onClick={() => toggleProv(s)}
              >{s}</button>
            ))}
          </div>
        )}
        {qErr && <p class="kp__qerr">{qErr}</p>}
        {hits && hits.length === 0 && <p class="kp__empty">No hits.</p>}
        {hits && hits.length > 0 && (
          <ol class="kp__hits">
            {hits.map((h, i) => (
              <li class="kp__hit" key={i}>
                <div class="kp__hit-top">
                  <code class="kp__hit-src">{h.slug} #{h.chunk_idx}</code>
                  <span class="kp__hit-prov" data-src={h.source || 'unknown'}>{h.source || '—'}{h.verdict ? ` · ${h.verdict}` : ''}</span>
                  <span class="kp__hit-dist">{Number(h.dist).toFixed(3)}</span>
                </div>
                <p class="kp__hit-text">{(h.text || '').slice(0, 280)}{(h.text || '').length > 280 ? ' …' : ''}</p>
              </li>
            ))}
          </ol>
        )}
      </section>

      {reindexRuns.length > 0 && (
        <details class="kp__runs">
          <summary>recent re-index runs ({reindexRuns.length})</summary>
          <ul class="kp__runs-list">
            {reindexRuns.slice(0, 8).map((r) => (
              <li key={r.id}>
                <code>{r.source_set}</code>
                <span>{r.chunks_after ?? '—'} chunks</span>
                <span class="kp__runs-ver">{r.index_version}</span>
                <span class="kp__runs-status" data-status={r.status}>{r.status}</span>
              </li>
            ))}
          </ul>
        </details>
      )}
    </div>
  );
}
