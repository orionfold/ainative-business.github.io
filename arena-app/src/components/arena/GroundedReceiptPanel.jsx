/** @jsxImportSource preact */
// GroundedReceiptPanel — the Grounded (live Cortex) leaderboard tier card.
//
// grounded-eval-v1 §7/§8: renders the NEWEST offline `run_pack.py` receipt
// (`evidence/grounded-eval/results/<run>/summary.json` via
// GET /api/grounded/receipts) — pass rate per operator journey, the
// per-component decomposition, and the ±Cortex grounding lift, headed by the
// corpus-pack pill (table · sources sha) + the pack sha. Receipt files are
// the canonical evidence (advisor precedent); interactive cockpit grades feed
// the live island above, never this card. Renders nothing on the public
// mirror or a box with no runs.

import { useEffect, useState } from 'preact/hooks';
import { resolveSidecarUrl, isPublicMirrorHost } from '../../lib/arena/sidecar.mjs';
import { scoreColor } from '../../lib/arena/leaderboard-format.mjs';

const JOURNEY_ORDER = ['lookup', 'howto', 'synthesis', 'troubleshoot', 'refusal'];
const COMPONENT_LABELS = {
  retrieval_hit: 'retrieval hit',
  citation: 'citation integrity',
  key_facts: 'key facts',
  refusal_wording: 'refusal wording',
  empty_citations: 'empty citations',
  no_private_state_risk: 'no private-state risk',
  no_thinking_leak: 'no thinking leak',
};

const pctStr = (r) => (r == null ? '—' : `${(r * 100).toFixed(0)}%`);

export default function GroundedReceiptPanel() {
  const [data, setData] = useState(null);

  useEffect(() => {
    if (isPublicMirrorHost()) return;
    const base = resolveSidecarUrl();
    if (!base) return;
    (async () => {
      try {
        const r = await fetch(`${base}/api/grounded/receipts?limit=1`);
        if (!r.ok) return;
        const body = await r.json();
        if (body.available) setData(body.runs[0]);
      } catch {
        /* sidecar offline — card stays absent */
      }
    })();
  }, []);

  if (!data) return null;

  const grounded = data.modes?.retrieval;
  const ungrounded = data.modes?.no_retrieval;
  const lift = data.grounding_lift;
  const journeys = grounded
    ? JOURNEY_ORDER.filter((j) => grounded.per_journey?.[j])
    : [];
  const comps = grounded?.per_component || {};

  return (
    <div class="bench-group grounded-receipt">
      <div class="bench-group__head">
        <span class="bench-group__id" title={`offline run_pack.py receipt · ${data.run}`}>
          Grounded (live Cortex) — pack receipt
          <span class="bench-group__raw">{data.pack} · {data.pack_sha256_12}</span>
        </span>
        <span
          class="evalbench__live-tag"
          title="canonical receipt — scripts/grounded_eval/run_pack.py builds every packet through the live Cortex stack and scores with the deterministic grounded_contract gate; files under evidence/grounded-eval/results/ are the evidence"
        >
          ⛁ receipt tier
        </span>
        {data.corpus && (
          <span
            class="bench-group__count"
            title="corpus pack the packets were retrieved from (the OA-NV-8 swap unit)"
          >
            ⛁ {data.corpus.table} · {data.corpus.manifest_sha256_12}
          </span>
        )}
        <span class="bench-group__metric">lane · {data.model}</span>
      </div>
      <div class="grounded-receipt__body">
        <div class="grounded-receipt__arms">
          {grounded && (
            <span class="grounded-receipt__arm">
              <b>grounded</b> {grounded.overall.passed}/{grounded.overall.n} ({pctStr(grounded.overall.pass_rate)})
            </span>
          )}
          {ungrounded && (
            <span class="grounded-receipt__arm grounded-receipt__arm--off">
              <b>ungrounded</b> {ungrounded.overall.passed}/{ungrounded.overall.n} ({pctStr(ungrounded.overall.pass_rate)})
            </span>
          )}
          {lift && (
            <span
              class="grounded-receipt__arm grounded-receipt__arm--lift"
              title={lift.note}
            >
              <b>grounding lift</b> {lift.overall > 0 ? '+' : ''}{pctStr(lift.overall)} overall · {lift.answer_rows > 0 ? '+' : ''}{pctStr(lift.answer_rows)} answer rows
            </span>
          )}
          <span class="grounded-receipt__stamp dim">{data.started_utc}</span>
        </div>
        {journeys.length > 0 && (
          <table class="ranktable grounded-receipt__journeys">
            <thead>
              <tr>
                <th class="rankcol-lane">Journey</th>
                <th class="rankcol-score">Pass rate (grounded)</th>
                <th class="rankcol-num">Rows</th>
              </tr>
            </thead>
            <tbody>
              {journeys.map((j) => {
                const jr = grounded.per_journey[j];
                const v = jr.pass_rate ?? 0;
                return (
                  <tr key={j}>
                    <td class="rankcol-lane mono">{j}</td>
                    <td class="rankcol-score">
                      <div class="scorebar" style={`--scorebar-color: ${scoreColor(v)};`}>
                        <span class="scorebar__track">
                          <span class="scorebar__fill" style={`width: ${(v * 100).toFixed(1)}%`}></span>
                        </span>
                        <span class="scorebar__value">{(v * 100).toFixed(0)}%</span>
                      </div>
                    </td>
                    <td class="rankcol-num mono" style="color: var(--arena-text-mute);">{jr.passed}/{jr.n}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
        {Object.keys(comps).length > 0 && (
          <p class="grounded-receipt__components dim">
            {Object.entries(COMPONENT_LABELS)
              .filter(([k]) => comps[k])
              .map(([k, label]) => {
                const c = comps[k];
                const unknown = c.unknown ? ` · ${c.unknown}?` : '';
                return `${label} ${c.pass}/${c.pass + c.fail}${unknown}`;
              })
              .join('  ·  ')}
          </p>
        )}
      </div>
    </div>
  );
}
