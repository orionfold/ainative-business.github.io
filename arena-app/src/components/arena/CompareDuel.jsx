/** @jsxImportSource preact */
// CompareDuel — `<CompareDuel>` Preact island for /arena/compare/.
//
// Side-by-side compare against the resident brain (lane A — always) and a
// configurable B-lane (default = OpenRouter via the H6 cost router). One
// `POST /api/compare/stream` SSE proxy emits the full
// `start_a → token_a* → done_a → [swap] → start_b → token_b* → done_b →
// score` event sequence per spec §4.3. Each side renders into its own
// column card; the score event paints the per-check ok/why strings under
// each side; the operator's thumbs-up / thumbs-down / tie verdict POSTs
// to `/api/prefs` — a separate signal that NEVER mutates the displayed
// rubric score (spec §4.3 contract).
//
// Render contract — five states across a run:
//   - idle           → composer + rubric picker enabled, no pending stream
//   - streaming_a    → A column pulses, tokens flow in; B column is empty
//   - streaming_b    → A is pinned with done_a chips; B pulses, tokens flow
//   - scored         → both sides pinned, score panel painted with per-check rows
//   - errored        → both sides freeze; error banner above composer
//
// Persistence: each compare lands as one `compare_runs` row + two
// `compare_responses` + two `rubric_scores` rows; thumbs add a
// `human_prefs` row that surfaces in the leaderboard only at ≥5 prefs.

import { useEffect, useRef, useState, useMemo } from 'preact/hooks';
import {
  resolveSidecarUrl,
  isPublicMirrorHost,
} from '../../lib/arena/sidecar.mjs';
import { renderMarkdown } from '../../lib/arena/markdown.mjs';
import { drawBars, SLOTS } from '../../lib/arena/peakbars.mjs';
import {
  fetchBenches,
  benchForLane,
  isDeterministic,
  formatEvalScore,
} from '../../lib/arena/evals.mjs';
import EvalPromptDrawer from './EvalPromptDrawer.jsx';
import EvalScore, { ReferencePanel } from './EvalScore.jsx';
import JudgeSelect from './JudgeSelect.jsx';

const MIN_PROMPT = 1;
const MAX_PROMPT = 32_000;

// Manual SSE parser — mirrors ChatLane's. sse-starlette emits CRLF; we
// normalise to LF up-front so `\n\n` is the canonical boundary.
async function* readSse(resp) {
  const decoder = new TextDecoder();
  const reader = resp.body.getReader();
  let buf = '';
  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buf += decoder.decode(value, { stream: true }).replace(/\r\n/g, '\n');
    let idx;
    while ((idx = buf.indexOf('\n\n')) !== -1) {
      const block = buf.slice(0, idx);
      buf = buf.slice(idx + 2);
      let event = 'message';
      let dataLines = [];
      for (const line of block.split('\n')) {
        if (line.startsWith('event:')) event = line.slice(6).trim();
        else if (line.startsWith('data:')) dataLines.push(line.slice(5).trim());
      }
      if (dataLines.length > 0 || event !== 'message') {
        yield { event, data: dataLines.join('\n') };
      }
    }
  }
}

function fmtMs(v) {
  if (v == null || typeof v !== 'number' || Number.isNaN(v)) return '—';
  return `${v.toFixed(0)} ms`;
}
function fmtTok(v) {
  if (v == null || typeof v !== 'number' || Number.isNaN(v)) return '—';
  return `${v.toFixed(1)} tok/s`;
}
function fmtScore(v) {
  if (v == null || typeof v !== 'number' || Number.isNaN(v)) return '—';
  return `${(v * 100).toFixed(0)}%`;
}

function makeEmptySide() {
  return {
    content: '',
    reasoning: '',
    ttft_ms: null,
    tok_per_s: null,
    tokens_out: null,
    finish_reason: null,
    lane_id: null,
    model: null,
    base_url: null,
    no_key: false,
    cost_usd: null,
    tokens_estimated: 1, // M9 (Bet 6, R20): 1 = heuristic token count → "~" cost marker
    loadStatus: null, // { phase, model, detail } while an on-demand lane loads
    score: null, // { total, checks } — deterministic rubric (free-prompt mode)
    evalScore: null, // { scored, score, max, normalized, scorer_kind, why } — eval mode
    state: 'idle', // idle | streaming | done | error
  };
}

export default function CompareDuel() {
  const [prompt, setPrompt] = useState('');
  const [rubrics, setRubrics] = useState([]);
  const [rubricId, setRubricId] = useState(''); // '' → server picks default
  // v0.2 any-vs-any lane selection. laneOptions = {local, groups, all, has_key}.
  const [laneOptions, setLaneOptions] = useState({
    local: [],
    groups: { frontier: [], open: [], project_base: [] },
    all: [],
    has_key: false,
  });
  const [laneA, setLaneA] = useState('local:resident');
  const [laneB, setLaneB] = useState('openrouter');
  const [showAllModels, setShowAllModels] = useState(false);
  // Which lanes are warm (loaded). Resident is always warm; on-demand is a
  // single slot, so at most one on-demand id sits here alongside the resident.
  const [warmLanes, setWarmLanes] = useState(['local:resident']);
  const [runId, setRunId] = useState(null);
  const [resolvedRubricId, setResolvedRubricId] = useState(null);
  const [a, setA] = useState(makeEmptySide());
  const [b, setB] = useState(makeEmptySide());
  // Per-metric session history — one record per completed compare, fed to the
  // metric-card sparklines (peak-bar style, reusing the telemetry renderer).
  // Each record: { a: {quality,tok_per_s,ttft_ms,tokens_out,cost_usd}, b: {…} }.
  const [history, setHistory] = useState([]);
  const [streaming, setStreaming] = useState(false);
  const [error, setError] = useState(null);
  const [offline, setOffline] = useState(false);
  const [thanks, setThanks] = useState(null); // 'A' | 'B' | 'tie' | null
  const [nPrefs, setNPrefs] = useState(0);
  // v0.3 — eval mode (mirrors ChatLane). When active, both sides are scored
  // against the bench gold and the eval score replaces the rubric verdict.
  const [benches, setBenches] = useState([]);
  const [judgeInfo, setJudgeInfo] = useState({ local_available: false, openrouter_available: false });
  const [judgeBackend, setJudgeBackend] = useState('local');
  const [evalMode, setEvalMode] = useState(null);
  const [evalRef, setEvalRef] = useState(null); // shared gold reference for the run
  const [evalDrawerOpen, setEvalDrawerOpen] = useState(false);
  const composerRef = useRef(null);

  // Deep-link pre-fill: /arena/compare/?prompt=… pre-loads the composer but
  // does NOT auto-send — compare fires a paid frontier (OpenRouter) lane, so
  // auto-firing on navigation would be a cost surprise. The operator presses
  // Compare. We scrub the query from the URL so a refresh doesn't re-fill.
  useEffect(() => {
    if (typeof window === 'undefined') return;
    try {
      const url = new URL(window.location.href);
      const pre = url.searchParams.get('prompt');
      if (pre) {
        setPrompt(pre);
        url.searchParams.delete('prompt');
        window.history.replaceState({}, '', url.pathname + url.search + url.hash);
        composerRef.current?.focus();
      }
    } catch (_e) {}
  }, []);

  useEffect(() => {
    if (isPublicMirrorHost()) {
      setOffline(true);
      return;
    }
    const base = resolveSidecarUrl();
    if (!base) {
      setOffline(true);
      return;
    }
    // Fetch the rubric registry + selectable lanes once at mount.
    (async () => {
      try {
        const r = await fetch(`${base}/api/rubrics`);
        if (r.ok) {
          const data = await r.json();
          setRubrics(data.rubrics || []);
        }
      } catch (_e) {
        // Don't toggle offline here — the gauge owns the offline banner;
        // an empty rubrics list just falls through to the server picker.
      }
      try {
        const r = await fetch(`${base}/api/compare/options`);
        if (r.ok) {
          const data = await r.json();
          const local = data.local || [];
          const groups = data.openrouter_groups || {
            frontier: [],
            open: [],
            project_base: [],
          };
          const all = data.openrouter || [];
          setLaneOptions({ local, groups, all, has_key: !!data.has_key });
          // Seed warm set from the server's view (resident + any loaded slot).
          const warm = local.filter((o) => o.warm).map((o) => o.id);
          if (!warm.includes('local:resident')) warm.push('local:resident');
          setWarmLanes(warm);
          // Defaults: A = warm resident (first local), B = newest frontier.
          if (local[0]) setLaneA(local[0].id);
          else if (all[0]) setLaneA(all[0].id);
          const defB =
            groups.frontier[0] ||
            groups.open[0] ||
            groups.project_base[0] ||
            all[0] ||
            local[0];
          if (defB) setLaneB(defB.id);
        }
      } catch (_e) {
        // Fall back to the static defaults (local:resident / openrouter).
      }
      try {
        const ev = await fetchBenches();
        if (ev) {
          setBenches(ev.benches || []);
          if (ev.judge) {
            setJudgeInfo(ev.judge);
            if (ev.judge.default_backend) setJudgeBackend(ev.judge.default_backend);
          }
        }
      } catch (_e) { /* eval surface is optional */ }
    })();
  }, []);

  const pickEvalPrompt = (p, benchId) => {
    setPrompt(p.question);
    setEvalMode({
      bench_id: benchId,
      qid: p.qid,
      reference: p.reference,
      scorer_kind: p.scorer_kind,
      scoring_mode: p.scoring_mode,
      has_context: p.has_context,
      context_tokens: p.context_token_hint,
      question: p.question,
      family: p.family,
      judge_required: p.judge_required,
    });
    composerRef.current?.focus();
  };
  const clearEvalMode = () => setEvalMode(null);

  const reset = () => {
    setA(makeEmptySide());
    setB(makeEmptySide());
    setRunId(null);
    setResolvedRubricId(null);
    setThanks(null);
    setNPrefs(0);
    setError(null);
    setEvalRef(null);
  };

  const send = async () => {
    const trimmed = prompt.trim();
    if (trimmed.length < MIN_PROMPT || trimmed.length > MAX_PROMPT) return;
    const base = resolveSidecarUrl();
    if (!base) {
      setOffline(true);
      return;
    }
    reset();
    setStreaming(true);

    let resp;
    try {
      resp = await fetch(`${base}/api/compare/stream`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Accept: 'text/event-stream',
        },
        body: JSON.stringify({
          prompt: trimmed,
          lane_a: laneA,
          lane_b: laneB,
          rubric_id: rubricId || null,
          ...(evalMode
            ? {
                bench_id: evalMode.bench_id,
                eval_qid: evalMode.qid,
                judge: { backend: judgeBackend },
              }
            : {}),
        }),
      });
    } catch (err) {
      setError(`Could not reach the sidecar: ${String(err.message || err)}`);
      setStreaming(false);
      return;
    }
    if (!resp.ok || !resp.body) {
      let detail = `HTTP ${resp.status}`;
      try {
        const body = await resp.json();
        if (body && body.detail) detail = body.detail;
      } catch (_e) {}
      setError(detail);
      setStreaming(false);
      return;
    }

    let aAcc = { content: '', reasoning: '' };
    let bAcc = { content: '', reasoning: '' };
    // Accumulate this run's final per-side metrics; pushed to `history` (the
    // sparkline store) once in `finally` so each completed compare = one bar.
    const runMetrics = { a: {}, b: {} };
    try {
      for await (const ev of readSse(resp)) {
        const payload = (() => {
          try { return JSON.parse(ev.data); } catch (_e) { return null; }
        })();
        if (!payload && ev.event !== 'message') continue;
        if (ev.event === 'lane_status') {
          // On-demand local load progress (teardown/loading/warming/ready).
          const setter = payload.side === 'B' ? setB : setA;
          setter((prev) => ({
            ...prev,
            loadStatus: {
              phase: payload.phase,
              model: payload.model,
              detail: payload.detail,
            },
          }));
          if (payload.phase === 'ready' && payload.model) {
            markWarm(`local:${payload.model}`);
          }
        } else if (ev.event === 'start_a') {
          setRunId(payload.run_id);
          setResolvedRubricId(payload.rubric_id);
          setA((prev) => ({
            ...prev,
            state: 'streaming',
            lane_id: payload.lane_id,
            model: payload.model,
            base_url: payload.base_url,
            loadStatus: null,
          }));
        } else if (ev.event === 'token_a') {
          if (payload.channel === 'reasoning') aAcc.reasoning += payload.text;
          else aAcc.content += payload.text;
          setA((prev) => ({
            ...prev,
            content: aAcc.content,
            reasoning: aAcc.reasoning,
          }));
        } else if (ev.event === 'done_a') {
          runMetrics.a = {
            tok_per_s: payload.tok_per_s ?? null,
            ttft_ms: payload.ttft_ms ?? null,
            tokens_out: payload.tokens_out ?? null,
            cost_usd: payload.cost_usd ?? null,
            tokens_estimated: payload.tokens_estimated ?? 1,
          };
          setA((prev) => ({
            ...prev,
            state: 'done',
            ttft_ms: payload.ttft_ms ?? null,
            tok_per_s: payload.tok_per_s ?? null,
            tokens_out: payload.tokens_out ?? null,
            finish_reason: payload.finish_reason ?? null,
            cost_usd: payload.cost_usd ?? null,
            tokens_estimated: payload.tokens_estimated ?? 1,
          }));
        } else if (ev.event === 'start_b') {
          setB((prev) => ({
            ...prev,
            state: 'streaming',
            lane_id: payload.lane_id,
            model: payload.model,
            base_url: payload.base_url,
            no_key: !!payload.no_key,
            loadStatus: null,
          }));
        } else if (ev.event === 'token_b') {
          if (payload.channel === 'reasoning') bAcc.reasoning += payload.text;
          else bAcc.content += payload.text;
          setB((prev) => ({
            ...prev,
            content: bAcc.content,
            reasoning: bAcc.reasoning,
          }));
        } else if (ev.event === 'done_b') {
          runMetrics.b = {
            tok_per_s: payload.tok_per_s ?? null,
            ttft_ms: payload.ttft_ms ?? null,
            tokens_out: payload.tokens_out ?? null,
            cost_usd: payload.cost_usd ?? null,
            tokens_estimated: payload.tokens_estimated ?? 1,
          };
          setB((prev) => ({
            ...prev,
            state: 'done',
            ttft_ms: payload.ttft_ms ?? null,
            tok_per_s: payload.tok_per_s ?? null,
            tokens_out: payload.tokens_out ?? null,
            finish_reason: payload.finish_reason ?? null,
            cost_usd: payload.cost_usd ?? null,
            tokens_estimated: payload.tokens_estimated ?? 1,
          }));
        } else if (ev.event === 'score') {
          setResolvedRubricId(payload.rubric_id);
          setA((prev) => ({ ...prev, score: payload.a }));
          setB((prev) => ({ ...prev, score: payload.b }));
          // Quality for the sparkline: gold-match normalized in eval mode, else
          // the deterministic rubric total.
          runMetrics.a.quality = (payload.eval ? payload.eval.a?.normalized : payload.a?.total) ?? null;
          runMetrics.b.quality = (payload.eval ? payload.eval.b?.normalized : payload.b?.total) ?? null;
          // v0.3 — reference-based eval block (present only in eval mode).
          if (payload.eval) {
            setEvalRef(payload.eval.reference || null);
            setA((prev) => ({ ...prev, evalScore: payload.eval.a }));
            setB((prev) => ({ ...prev, evalScore: payload.eval.b }));
          }
        } else if (ev.event === 'error') {
          const code = payload?.code;
          const detail = payload?.detail || 'Stream errored';
          setError(detail);
          if (code === 'two_local_lanes_v0_2_only') {
            setA((prev) => ({ ...prev, state: 'error' }));
            setB((prev) => ({ ...prev, state: 'error' }));
          }
        } else if (ev.event === 'swap') {
          // v0.2 only — visible swap chip between A's done and B's start.
          // Renders as a fleeting status line in the divider.
        }
      }
    } catch (err) {
      setError(`Stream broke: ${String(err.message || err)}`);
    } finally {
      setStreaming(false);
      // Land this run as one history record (one sparkline bar) if either side
      // produced a measurement. Keep at most SLOTS so the chart FIFOs like the
      // telemetry rail.
      const produced =
        runMetrics.a.tok_per_s != null || runMetrics.b.tok_per_s != null ||
        runMetrics.a.quality != null || runMetrics.b.quality != null;
      if (produced) {
        setHistory((h) => [...h, runMetrics].slice(-SLOTS));
      }
      composerRef.current?.focus();
    }
  };

  const sendPref = async (winner) => {
    if (!runId || thanks) return;
    const base = resolveSidecarUrl();
    if (!base) return;
    try {
      const r = await fetch(`${base}/api/prefs`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ compare_run_id: runId, winner }),
      });
      if (r.ok) {
        const data = await r.json();
        setThanks(winner);
        setNPrefs(data.n_prefs ?? 0);
      }
    } catch (_e) {
      // Silently swallow — the next click can retry.
    }
  };

  const onKey = (ev) => {
    if (
      (ev.metaKey || ev.ctrlKey) &&
      ev.key === 'Enter' &&
      !streaming
    ) {
      ev.preventDefault();
      send();
    }
  };

  // Human label for a selected lane id (falls back to the raw id).
  const labelFor = (id) => {
    const g = laneOptions.groups || {};
    const pool = [
      ...(laneOptions.local || []),
      ...(laneOptions.all || []),
      ...(g.frontier || []),
      ...(g.open || []),
      ...(g.project_base || []),
    ];
    const found = pool.find((o) => o.id === id);
    return found ? found.label : id;
  };

  const isOnDemand = (id) =>
    typeof id === 'string' && id.startsWith('local:') && id !== 'local:resident';
  const needsLoad = (id) => isOnDemand(id) && !warmLanes.includes(id);

  // Single on-demand slot: loading one evicts any prior on-demand model, so the
  // warm set becomes {resident, id}. Resident stays warm always.
  const markWarm = (id) => {
    setWarmLanes((prev) => {
      if (id === 'local:resident')
        return prev.includes(id) ? prev : [...prev, id];
      const keepResident = prev.filter((x) => x === 'local:resident');
      if (!keepResident.length) keepResident.push('local:resident');
      return [...keepResident, id];
    });
  };

  // Pre-warm an on-demand local lane on the operator's click, with the same
  // teardown→loading→warming→ready progress the compare uses.
  const loadLane = async (side, laneSpec) => {
    const base = resolveSidecarUrl();
    if (!base) {
      setOffline(true);
      return;
    }
    const setter = side === 'A' ? setA : setB;
    const shortModel = laneSpec.replace(/^local:/, '');
    setter((prev) => ({
      ...prev,
      loadStatus: { phase: 'loading', model: shortModel, detail: 'starting' },
    }));
    let resp;
    try {
      resp = await fetch(`${base}/api/local/load`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Accept: 'text/event-stream' },
        body: JSON.stringify({ lane: laneSpec }),
      });
    } catch (err) {
      setter((prev) => ({ ...prev, loadStatus: null }));
      setError(`Could not reach the sidecar: ${String(err.message || err)}`);
      return;
    }
    if (!resp.ok || !resp.body) {
      setter((prev) => ({ ...prev, loadStatus: null }));
      setError(`Load failed: HTTP ${resp.status}`);
      return;
    }
    try {
      for await (const ev of readSse(resp)) {
        const payload = (() => {
          try {
            return JSON.parse(ev.data);
          } catch (_e) {
            return null;
          }
        })();
        if (ev.event === 'status') {
          setter((prev) => ({
            ...prev,
            loadStatus: {
              phase: payload.phase,
              model: payload.model,
              detail: payload.detail,
            },
          }));
        } else if (ev.event === 'done') {
          setter((prev) => ({ ...prev, loadStatus: null }));
          markWarm(laneSpec);
        } else if (ev.event === 'error') {
          setter((prev) => ({ ...prev, loadStatus: null }));
          setError(payload?.detail || 'Model load failed');
        }
      }
    } catch (err) {
      setter((prev) => ({ ...prev, loadStatus: null }));
      setError(`Load stream broke: ${String(err.message || err)}`);
    }
  };

  if (offline) {
    return (
      <div class="compare-duel compare-duel--offline">
        <p class="compare-duel__status">
          Sidecar offline — start with <code>fieldkit arena serve</code> on
          the Spark, then refresh this page.
        </p>
      </div>
    );
  }

  return (
    <div class="compare-duel">
      <div class="compare-duel__controls">
        <label class="compare-duel__field">
          <span class="compare-duel__field-label" style="color:#76b900">Lane A</span>
          <LaneSelect
            value={laneA}
            disabled={streaming}
            options={laneOptions}
            showAll={showAllModels}
            onChange={setLaneA}
          />
        </label>
        <label class="compare-duel__field">
          <span class="compare-duel__field-label" style="color:#5b9cff">Lane B</span>
          <LaneSelect
            value={laneB}
            disabled={streaming}
            options={laneOptions}
            showAll={showAllModels}
            onChange={setLaneB}
          />
        </label>
        {evalMode ? (
          <span class="compare-duel__field compare-duel__field--evalnote">
            <span class="compare-duel__field-label">Scoring</span>
            <span class="compare-duel__evalnote">
              reference-based ({evalMode.scorer_kind}) — rubric paused in eval mode
            </span>
          </span>
        ) : (
          <label class="compare-duel__field">
            <span class="compare-duel__field-label">Rubric</span>
            <select
              class="compare-duel__select"
              value={rubricId}
              disabled={streaming}
              onChange={(ev) => setRubricId(ev.currentTarget.value)}
            >
              <option value="">Default — picked from prompt</option>
              {rubrics.map((r) => (
                <option key={r.id} value={r.id}>
                  {r.title} — {r.id}
                </option>
              ))}
            </select>
          </label>
        )}
        <div class="compare-duel__field-spacer" />
        {benches.some((bn) => bn.available) && (
          <button
            type="button"
            class="arena-btn--ghost eval-trigger"
            disabled={streaming}
            onClick={() => setEvalDrawerOpen(true)}
            title="Browse eval-bench prompts + score both sides against the reference"
          >
            🧪 Eval prompts
          </button>
        )}
        {laneOptions.all.length > 0 && (
          <label class="compare-duel__allmodels" title="Toggle the full OpenRouter catalog">
            <input
              type="checkbox"
              checked={showAllModels}
              disabled={streaming}
              onChange={(ev) => setShowAllModels(ev.currentTarget.checked)}
            />
            all {laneOptions.all.length} models
          </label>
        )}
        {(laneA.startsWith('openrouter') || laneB.startsWith('openrouter')) &&
          !laneOptions.has_key && (
            <span class="compare-duel__lane-b">
              <code>OPENROUTER_API_KEY</code> unset — OpenRouter side returns a stub
            </span>
          )}
      </div>

      <div class="compare-duel__columns">
        <SideCard
          side="A"
          accent="#76b900"
          state={a}
          streaming={streaming}
          title={labelFor(laneA)}
          needsLoad={needsLoad(laneA)}
          onLoad={() => loadLane('A', laneA)}
        />
        <SideCard
          side="B"
          accent="#5b9cff"
          state={b}
          streaming={streaming}
          title={labelFor(laneB)}
          needsLoad={needsLoad(laneB)}
          onLoad={() => loadLane('B', laneB)}
        />
      </div>

      {evalRef && (
        <div class="compare-reference bezel">
          <details open>
            <summary>◆ Reference answer{evalMode ? ` · ${evalMode.bench_id}` : ''}</summary>
            <pre class="compare-reference__body">{evalRef}</pre>
          </details>
        </div>
      )}

      {/* Eval mode: the reference-based eval score is the yardstick, replacing
          the deterministic rubric verdict. Free-prompt mode keeps the rubric. */}
      {evalMode ? (
        a.evalScore && b.evalScore && <WinnerBanner a={a} b={b} evalMode />
      ) : (
        a.score && b.score && <WinnerBanner a={a} b={b} />
      )}

      {(history.length > 0 || a.state === 'done' || b.state === 'done') && (
        <MetricCards a={a} b={b} evalMode={!!evalMode} history={history} />
      )}

      {evalMode && (a.evalScore || b.evalScore) ? (
        <div class="compare-duel__verdict">
          <h3 class="compare-duel__verdict-title">
            Eval score{' '}
            <code class="compare-duel__verdict-rubric">{evalMode.bench_id} · {evalMode.scorer_kind}</code>
          </h3>
          <div class="compare-duel__verdict-grid">
            <div class="eval-score-col" style="--side-accent:#76b900">
              <span class="compare-score-col__tag">A</span>
              <EvalScore result={a.evalScore} />
            </div>
            <div class="eval-score-col" style="--side-accent:#5b9cff">
              <span class="compare-score-col__tag">B</span>
              <EvalScore result={b.evalScore} />
            </div>
          </div>
        </div>
      ) : !evalMode && resolvedRubricId ? (
        <div class="compare-duel__verdict">
          <h3 class="compare-duel__verdict-title">
            Score{' '}
            <code class="compare-duel__verdict-rubric">
              {resolvedRubricId}
            </code>
          </h3>
          <div class="compare-duel__verdict-grid">
            <ScoreColumn side="A" score={a.score} accent="#76b900" />
            <ScoreColumn side="B" score={b.score} accent="#5b9cff" />
          </div>
        </div>
      ) : null}

      {runId && a.score && b.score && (
        <div class="compare-duel__prefs">
          <span class="compare-duel__prefs-label">
            Operator pick (separate signal — does not change the score above)
          </span>
          <div class="compare-duel__prefs-buttons">
            {['A', 'B', 'tie'].map((w) => (
              <button
                key={w}
                type="button"
                class={`compare-duel__pref ${
                  thanks === w ? 'compare-duel__pref--active' : ''
                }`}
                disabled={!!thanks}
                onClick={() => sendPref(w)}
              >
                {w === 'A' ? '👍 A' : w === 'B' ? '👍 B' : '↔︎ Tie'}
              </button>
            ))}
          </div>
          {thanks && (
            <p class="compare-duel__prefs-thanks">
              Recorded as <strong>{thanks}</strong>. Total prefs on this run:{' '}
              {nPrefs}.
            </p>
          )}
        </div>
      )}

      {error && (
        <p class="compare-duel__error">
          <strong>Error.</strong> {error}
        </p>
      )}

      <div class="compare-duel__composer">
        {evalMode && (
          <div class="eval-chip">
            <span class="eval-chip__main">
              <span class="eval-chip__bench">🧪 {evalMode.bench_id}</span>
              <span class={`eval-badge ${evalMode.judge_required ? 'eval-badge--judge' : 'eval-badge--det'}`}>
                {evalMode.scorer_kind}
              </span>
              {evalMode.reference && <span class="eval-badge eval-badge--ref">◆ reference loaded</span>}
              {evalMode.has_context && (
                <span class="eval-badge eval-badge--ctx">📎 context attached ({evalMode.context_tokens || 0} tok)</span>
              )}
              {prompt.trim() !== (evalMode.question || '').trim() && (
                <span class="eval-chip__edited">✎ edited — still scored vs original gold</span>
              )}
            </span>
            <span class="eval-chip__right">
              <JudgeSelect
                value={judgeBackend}
                onChange={setJudgeBackend}
                availability={judgeInfo}
                deterministic={isDeterministic(evalMode.scorer_kind)}
              />
              <button type="button" class="eval-chip__clear" onClick={clearEvalMode} title="Back to free prompt">
                ✕ free prompt
              </button>
            </span>
          </div>
        )}
        <textarea
          ref={composerRef}
          class="compare-duel__textarea"
          rows={4}
          placeholder="Drop a prompt here — both lanes will answer + the rubric scores them deterministically."
          value={prompt}
          disabled={streaming}
          onInput={(ev) => setPrompt(ev.currentTarget.value)}
          onKeyDown={onKey}
        />
        <div class="compare-duel__composer-actions">
          <span class="compare-duel__hint">
            <kbd>⌘</kbd> + <kbd>Enter</kbd> to send · A streams first, then B,
            then the rubric scores
          </span>
          <button
            type="button"
            class="compare-duel__send"
            disabled={streaming || prompt.trim().length === 0}
            onClick={send}
          >
            {streaming ? 'Streaming…' : 'Compare'}
          </button>
        </div>
      </div>

      <EvalPromptDrawer
        open={evalDrawerOpen}
        onClose={() => setEvalDrawerOpen(false)}
        benches={benches}
        scopeLanes={[laneA, laneB]}
        onPick={pickEvalPrompt}
      />
    </div>
  );
}

// On-demand local load progress shown in the side body until tokens arrive.
function LoadStatus({ status }) {
  const labels = {
    teardown: 'Unloading prior model',
    loading: 'Loading model',
    warming: 'Warming on GPU',
    ready: 'Ready — starting',
  };
  const label = labels[status.phase] || status.phase;
  return (
    <span class="compare-side__loading">
      <span class="compare-side__spinner" aria-hidden="true" />
      <span>
        {label}
        {status.detail ? <span class="dim"> · {status.detail}</span> : null}
      </span>
    </span>
  );
}

// Shown when a selected on-demand local model isn't loaded yet — a notice +
// confirm button. Clicking spawns the load (progress indicator takes over).
function NeedsLoad({ title, onLoad }) {
  return (
    <div class="compare-side__needsload">
      <span class="compare-side__needsload-msg">
        <strong>{title}</strong> isn’t loaded onto the GPU. Loading it serves the
        model on the Spark (any prior on-demand model is unloaded first).
      </span>
      <button type="button" class="compare-side__loadbtn" onClick={onLoad}>
        ⤓ Load model
      </button>
    </div>
  );
}

// Lane picker — Local (resident + on-demand article models) then either the
// curated 3 groups (frontier / open SOTA / project bases) or, with the toggle,
// the full OpenRouter catalog. On-demand local entries are marked ⤓ (they boot
// a llama-server when the compare runs).
function LaneSelect({ value, disabled, options, showAll, onChange }) {
  const g = options.groups || { frontier: [], open: [], project_base: [] };
  return (
    <select
      class="compare-duel__select"
      value={value}
      disabled={disabled}
      onChange={(ev) => onChange(ev.currentTarget.value)}
    >
      {options.local.length > 0 && (
        <optgroup label="Local · Spark">
          {options.local.map((o) => (
            <option key={o.id} value={o.id}>
              {o.on_demand ? '⤓ ' : ''}
              {o.label}
            </option>
          ))}
        </optgroup>
      )}
      {showAll ? (
        <optgroup label={`OpenRouter · all (${options.all.length})`}>
          {options.all.map((o) => (
            <option key={o.id} value={o.id}>{o.label}</option>
          ))}
        </optgroup>
      ) : (
        <>
          {g.frontier.length > 0 && (
            <optgroup label="Frontier · latest">
              {g.frontier.map((o) => (
                <option key={o.id} value={o.id}>{o.label}</option>
              ))}
            </optgroup>
          )}
          {g.open.length > 0 && (
            <optgroup label="Open SOTA · latest">
              {g.open.map((o) => (
                <option key={o.id} value={o.id}>{o.label}</option>
              ))}
            </optgroup>
          )}
          {g.project_base.length > 0 && (
            <optgroup label="Our project bases">
              {g.project_base.map((o) => (
                <option key={o.id} value={o.id}>{o.label}</option>
              ))}
            </optgroup>
          )}
        </>
      )}
    </select>
  );
}

// Winner banner — derived purely from the deterministic rubric totals. This
// NEVER touches human prefs (those stay a separate signal below). Tie when the
// totals are within a hair of each other.
function WinnerBanner({ a, b, evalMode }) {
  const at = evalMode ? (a.evalScore?.normalized ?? 0) : (a.score?.total ?? 0);
  const bt = evalMode ? (b.evalScore?.normalized ?? 0) : (b.score?.total ?? 0);
  const margin = Math.abs(at - bt);
  const tie = margin < 0.005;
  const winner = tie ? 'tie' : at > bt ? 'A' : 'B';
  const accent = winner === 'A' ? '#76b900' : winner === 'B' ? '#5b9cff' : 'var(--arena-text-mute)';
  return (
    <div class={`compare-winner compare-winner--${winner}`} style={`--win-accent: ${accent};`}>
      <span class="compare-winner__tag">{evalMode ? 'Closest to gold' : 'Rubric verdict'}</span>
      {tie ? (
        <span class="compare-winner__text">Dead heat — both score {(at * 100).toFixed(0)}%</span>
      ) : (
        <span class="compare-winner__text">
          <b>Lane {winner}</b> wins by <b>{(margin * 100).toFixed(0)} pts</b>
          <span class="dim"> · {(Math.max(at, bt) * 100).toFixed(0)}% vs {(Math.min(at, bt) * 100).toFixed(0)}%</span>
        </span>
      )}
    </div>
  );
}

// Head-to-head — paired magnitude bars from a common left baseline. Each lane
// gets its own bar sized to the REAL value (longer = larger number), scaled to
// the row's max so the two are directly comparable; the winner (honouring
// lower-is-better for TTFT) is marked with a ✓ and full opacity, the loser
// dimmed. This reads literally ("B's tok/s bar is ~4× A's") — unlike the old
// centre-diverging bars whose length was a normalised margin, not the value.
const DELTA_A = '#76b900';
const DELTA_B = '#5b9cff';

// One small canvas of peak bars across the session's runs, reusing the exact
// telemetry-rail renderer. `series` is this metric's value per run (oldest
// first); `max` is shared across the A and B canvas so the two read on one scale.
function CanvasSpark({ series, color, max }) {
  const ref = useRef(null);
  useEffect(() => {
    if (ref.current) drawBars(ref.current, series, null, { color, max });
  }, [series, color, max]);
  return <canvas ref={ref} width="120" height="9" class="compare-metric__canvas" />;
}

// MetricCards — the head-to-head metrics as telemetry-style horizontal cards.
// Each card: metric label · current-run A-vs-B values (winner emphasised) · a
// two-row peak-bar sparkline (A over B) of that metric across this session's
// compare runs. Replaces the old paired-bar DeltaStrip.
function MetricCards({ a, b, evalMode, history }) {
  const qualityA = evalMode ? a.evalScore?.normalized : a.score?.total;
  const qualityB = evalMode ? b.evalScore?.normalized : b.score?.total;
  const num = (v) => typeof v === 'number' && !Number.isNaN(v);
  const specs = [
    { key: 'quality', label: evalMode ? 'Gold match' : 'Quality', lowerBetter: false, av: qualityA, bv: qualityB, fmt: (v) => `${(v * 100).toFixed(0)}%` },
    { key: 'tok_per_s', label: 'tok/s', lowerBetter: false, av: a.tok_per_s, bv: b.tok_per_s, fmt: (v) => v.toFixed(1) },
    { key: 'ttft_ms', label: 'TTFT', lowerBetter: true, av: a.ttft_ms, bv: b.ttft_ms, fmt: (v) => `${v.toFixed(0)} ms` },
    { key: 'tokens_out', label: 'Tokens', lowerBetter: false, av: a.tokens_out, bv: b.tokens_out, fmt: (v) => v.toLocaleString() },
    // M9 (Bet 6, R20): a "~" prefix marks a cost computed from estimated
    // (heuristic) token counts — never silently trusted as exact.
    { key: 'cost_usd', label: 'Cost', lowerBetter: true, av: a.cost_usd, bv: b.cost_usd, fmt: (v) => `${(a.tokens_estimated || b.tokens_estimated) ? '~' : ''}$${v.toFixed(4)}` },
  ].filter((s) => num(s.av) || num(s.bv) || history.some((h) => num(h.a?.[s.key]) || num(h.b?.[s.key])));

  return (
    <div class="compare-metrics" aria-label="Head-to-head metrics">
      <div class="compare-metrics__legend">
        <span class="compare-metrics__head">Head to head</span>
        <span class="compare-metrics__key">
          <span style={`color:${DELTA_A};font-weight:700`}>A</span>
          <span style={`color:${DELTA_B};font-weight:700`}>B</span>
          <span class="compare-metrics__keytext">· bars = this session's runs · ✓ winner</span>
        </span>
      </div>
      <div class="compare-metrics__grid">
        {specs.map((s) => {
          const both = num(s.av) && num(s.bv);
          const tie = both && s.av === s.bv;
          const aWins = both && !tie && (s.lowerBetter ? s.av < s.bv : s.av > s.bv);
          const bWins = both && !tie && !aWins;
          const aSeries = history.map((h) => (num(h.a?.[s.key]) ? h.a[s.key] : null));
          const bSeries = history.map((h) => (num(h.b?.[s.key]) ? h.b[s.key] : null));
          let max = 1e-9;
          for (const v of [...aSeries, ...bSeries]) if (v != null) max = Math.max(max, v);
          return (
            <div class="compare-metric" key={s.key}>
              <span class="compare-metric__label" title={s.lowerBetter ? 'lower is better' : 'higher is better'}>{s.label}</span>
              <span class="compare-metric__vals">
                <span class="compare-metric__a" style={`color:${DELTA_A};font-weight:${aWins ? 700 : 500}`}>
                  {num(s.av) ? s.fmt(s.av) : '—'}{aWins ? ' ✓' : ''}
                </span>
                <span class="compare-metric__vs">vs</span>
                <span class="compare-metric__b" style={`color:${DELTA_B};font-weight:${bWins ? 700 : 500}`}>
                  {num(s.bv) ? s.fmt(s.bv) : '—'}{bWins ? ' ✓' : ''}
                </span>
              </span>
              <div class="compare-metric__spark">
                <CanvasSpark series={aSeries} color={DELTA_A} max={max} />
                <CanvasSpark series={bSeries} color={DELTA_B} max={max} />
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function SideCard({ side, accent, state, streaming, title, needsLoad, onLoad }) {
  const isCurrent =
    streaming && state.state === 'streaming';
  // Markdown + syntax-highlight parity with chat (shared renderer). Memoized
  // on content so it only recomputes as tokens arrive.
  const html = useMemo(() => renderMarkdown(state.content || ''), [state.content]);
  return (
    <div
      class={`compare-side compare-side--${side.toLowerCase()} ${
        isCurrent ? 'compare-side--streaming' : ''
      } ${state.state === 'error' ? 'compare-side--error' : ''}`}
      style={`--side-accent: ${accent};`}
    >
      <header class="compare-side__head" style="display:flex; align-items:center; gap:0.5rem;">
        <span class="compare-side__tag">{side}</span>
        <span class="compare-side__title">{title}</span>
        {(state.lane_id || state.base_url) && (() => {
          const isOR = String(state.lane_id || '').startsWith('openrouter')
            || /openrouter\.ai/.test(state.base_url || '');
          const c = isOR ? '#5b9cff' : '#76b900';
          return (
            <span
              title={isOR ? 'Runs in the cloud via OpenRouter' : 'Runs locally on the DGX Spark'}
              style={`margin-left:auto; flex:none; font-size:0.58rem; font-weight:700; letter-spacing:0.06em; text-transform:uppercase; padding:2px 8px; border-radius:999px; color:${c}; background:${c}1f; border:1px solid ${c}66;`}
            >
              {isOR ? 'OpenRouter' : 'Spark GPU'}
            </span>
          );
        })()}
      </header>
      {state.no_key && (
        <div class="compare-side__meta">
          <span class="compare-side__warn">no OPENROUTER_API_KEY</span>
        </div>
      )}
      {state.reasoning && state.reasoning.length > 0 && (
        <details class="compare-side__think">
          <summary>
            💭 Reasoning ({state.reasoning.length.toLocaleString()} chars)
          </summary>
          <pre class="compare-side__think-body">{state.reasoning}</pre>
        </details>
      )}
      <div class="compare-side__body chat-markdown">
        {state.content ? (
          <span dangerouslySetInnerHTML={{ __html: html }} />
        ) : state.loadStatus ? (
          <LoadStatus status={state.loadStatus} />
        ) : needsLoad && !streaming ? (
          <NeedsLoad title={title} onLoad={onLoad} />
        ) : isCurrent ? (
          <span class="compare-side__cursor">▍</span>
        ) : (
          <em>(no answer yet)</em>
        )}
        {state.content && isCurrent && <span class="compare-side__cursor">▍</span>}
      </div>
      {(state.ttft_ms != null || state.tok_per_s != null) && (
        <div class="compare-side__perf">
          <span class="compare-side__chip">TTFT {fmtMs(state.ttft_ms)}</span>
          <span class="compare-side__chip">{fmtTok(state.tok_per_s)}</span>
          {state.tokens_out != null && (
            <span class="compare-side__chip">
              ≈{state.tokens_out.toLocaleString()} tok
            </span>
          )}
          {/* AE-13: cost legible on every duel — metered cloud spend, or an
              explicit "$0 · local" so a free Spark lane reads as free, not blank. */}
          {state.cost_usd != null && state.cost_usd > 0 ? (
            <span class="compare-side__chip compare-side__chip--cost">
              ${state.cost_usd < 0.01 ? state.cost_usd.toFixed(4) : state.cost_usd.toFixed(3)}
            </span>
          ) : state.tokens_out != null ? (
            <span class="compare-side__chip compare-side__chip--muted">$0 · local</span>
          ) : null}
          {state.finish_reason && (
            <span class="compare-side__chip compare-side__chip--muted">
              {state.finish_reason}
            </span>
          )}
        </div>
      )}
      {state.evalScore && (
        <div class="compare-side__eval">
          <EvalScore result={state.evalScore} />
        </div>
      )}
    </div>
  );
}

function ScoreColumn({ side, score, accent }) {
  if (!score) {
    return (
      <div
        class="compare-score-col"
        style={`--side-accent: ${accent};`}
      >
        <div class="compare-score-col__head">
          <span class="compare-score-col__tag">{side}</span>
          <span class="compare-score-col__total">—</span>
        </div>
      </div>
    );
  }
  const total = score.total;
  const passing = score.checks?.filter((c) => c.ok).length ?? 0;
  const totalChecks = score.checks?.length ?? 0;
  return (
    <div
      class="compare-score-col"
      style={`--side-accent: ${accent};`}
    >
      <div class="compare-score-col__head">
        <span class="compare-score-col__tag">{side}</span>
        <span class="compare-score-col__total">
          {fmtScore(total)}{' '}
          <span class="compare-score-col__count">
            ({passing}/{totalChecks})
          </span>
        </span>
      </div>
      <ul class="compare-score-col__checks">
        {(score.checks || []).map((c) => (
          <li
            key={c.name}
            class={`compare-score-col__check ${
              c.ok
                ? 'compare-score-col__check--pass'
                : 'compare-score-col__check--fail'
            }`}
          >
            <span class="compare-score-col__check-icon">
              {c.ok ? '✓' : '✗'}
            </span>
            <code class="compare-score-col__check-name">
              {c.name} · {c.kind}
            </code>
            <span class="compare-score-col__check-why">{c.why}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
