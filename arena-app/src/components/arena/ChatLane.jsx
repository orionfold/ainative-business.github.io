/** @jsxImportSource preact */
// ChatLane — `<ChatLane>` Preact island for /arena/chat/.
//
// v0.1.1 overhaul — turns the M4 functional minimum into an arena-grade
// chat surface. Single-lane chat against the resident brain — `POST
// /api/chat/stream` on the FastAPI sidecar at 127.0.0.1:7866. Uses
// `fetch` + a manual SSE parser (EventSource is GET-only; the chat
// endpoint is POST so we can carry JSON + a turn budget).
//
// What's new in v0.1.1 (per /home/nvidia/.claude/plans/review-and-improve-the-harmonic-ladybug.md):
//
// - LanePill + SessionSwitcher pill in a topbar row, with "+ New chat".
// - 4 example-prompt chips on the empty state (familiar chat-UI pattern).
// - AbortController-backed Stop button + Esc keybind for in-flight cancel.
// - Copy + Regenerate actions on assistant turns (hover-revealed).
// - Markdown rendering (marked + DOMPurify + highlight.js core w/ OKLCH
//   token theme in ArenaAppLayout). Debounced ~60ms during streaming so
//   the per-token re-render stays cheap.
// - Slash menu (`/clear`, `/copy`, `/compare`) with Tab/Enter selection.
// - Live token-count preview (chars/4 heuristic; the `~` is intentional).
// - Visible kbd hints row.
// - `?prompt=` query-string handler — the cockpit hero form lands here
//   pre-filled and auto-sends.
//
// Persistence + privacy contract (unchanged): every turn POSTs to
// `/api/chat/stream`, persists to chat_sessions + chat_turns. Spec §4.2 —
// operator-private; the M6 mirror exporter hardcodes `chat_*` tables OUT
// of its allowlist, so even publishable=1 rows never leak.

import { useEffect, useRef, useState } from 'preact/hooks';

import {
  resolveSidecarUrl,
  isPublicMirrorHost,
} from '../../lib/arena/sidecar.mjs';
import { renderMarkdown } from '../../lib/arena/markdown.mjs';
import {
  fetchBenches,
  scoreChatTurn,
  benchForLane,
  isDeterministic,
} from '../../lib/arena/evals.mjs';
import EvalPromptDrawer from './EvalPromptDrawer.jsx';
import EvalScore, { ReferencePanel } from './EvalScore.jsx';
import JudgeSelect from './JudgeSelect.jsx';

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const MIN_PROMPT = 1;
const MAX_PROMPT = 32_000;
const STREAM_RENDER_INTERVAL_MS = 60;
const SESSIONS_LIMIT = 8;

const PROMPT_CHIPS = [
  {
    kind: 'Ask',
    body: 'In one short paragraph, what makes a DGX Spark well suited to running local language models?',
  },
  {
    kind: 'Explain',
    body: 'Explain how the Spark Arena cockpit telemetry rail works in three lines.',
  },
  {
    kind: 'Table',
    body: 'create a table of tallest buildings',
  },
  {
    kind: 'Draft',
    body: 'Draft a 3-bullet release note for the Spark Arena v0.1.1 cockpit overhaul.',
  },
];

const SLASH_COMMANDS = [
  { name: '/clear', desc: 'Drop current session, start fresh' },
  { name: '/copy', desc: 'Copy last assistant turn to clipboard' },
  { name: '/compare', desc: 'Open compare with this prompt pre-filled' },
  { name: '/eval', desc: 'Browse eval-bench prompts for this model' },
];

// ---------------------------------------------------------------------------
// SSE reader (manual, abortable)
// ---------------------------------------------------------------------------

// Manual SSE parser — reads chunks off a fetch ReadableStream, accumulates
// until each event-boundary blank line, and yields `{ event, data }` records.
// sse-starlette terminates lines with CRLF, so the event separator is
// `\r\n\r\n` (and individual lines end in `\r\n`). We normalise to LF up
// front so a single boundary + split logic covers both wire styles.
// One event per yield; `data` is the raw payload string (caller JSON.parses).
//
// v0.1.1: accepts an optional `signal` so the abort path can drop the
// reader cleanly (the fetch itself aborts on signal, but the reader holds
// the body; this loop checks aborted between reads).
async function* readSse(resp, signal) {
  const decoder = new TextDecoder();
  const reader = resp.body.getReader();
  let buf = '';
  try {
    while (true) {
      if (signal?.aborted) {
        try { await reader.cancel(); } catch (_e) {}
        break;
      }
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
  } finally {
    try { reader.releaseLock(); } catch (_e) {}
  }
}

// ---------------------------------------------------------------------------
// Formatters
// ---------------------------------------------------------------------------

function fmtMs(v) {
  if (v == null || typeof v !== 'number' || Number.isNaN(v)) return '—';
  return `${v.toFixed(0)} ms`;
}
function fmtTok(v) {
  if (v == null || typeof v !== 'number' || Number.isNaN(v)) return '—';
  return `${v.toFixed(1)} tok/s`;
}
function shortId(id, prefixLen = 3) {
  if (!id) return '';
  const s = String(id);
  return s.slice(prefixLen, prefixLen + 8) || s.slice(0, 8);
}
function shortModel(model) {
  if (!model) return '—';
  const s = String(model);
  // Take last slash segment, trim common quant suffixes.
  return s.split('/').slice(-1)[0].replace(/-(Q\d_K_[A-Z]|GGUF|gguf)$/, '');
}
function shortEndpoint(url) {
  if (!url) return '—';
  return String(url).replace(/^https?:\/\//, '').replace(/\/$/, '');
}
function fmtCtx(ctx) {
  if (!ctx) return '?';
  return `${Math.round(ctx / 1024)}K`;
}
function relTime(ts) {
  if (!ts) return '—';
  try {
    const dt = Math.max(0, (Date.now() - new Date(ts).getTime()) / 1000);
    if (dt < 60) return `${Math.floor(dt)}s`;
    if (dt < 3600) return `${Math.floor(dt / 60)}m`;
    if (dt < 86400) return `${Math.floor(dt / 3600)}h`;
    return `${Math.floor(dt / 86400)}d`;
  } catch (_e) { return '—'; }
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export default function ChatLane() {
  const [prompt, setPrompt] = useState('');
  const [turns, setTurns] = useState([]); // [{role, content, html?, reasoning?, ttft_ms?, tok_per_s?, error?}]
  const [streaming, setStreaming] = useState(false);
  const [sessionId, setSessionId] = useState(null);
  const [laneMeta, setLaneMeta] = useState(null); // { model, base_url, lane_id, context_length }
  const [error, setError] = useState(null);
  const [offline, setOffline] = useState(false);
  const [sessions, setSessions] = useState([]);
  const [sessionsOpen, setSessionsOpen] = useState(false);
  const [slashIdx, setSlashIdx] = useState(0);
  const [toast, setToast] = useState(null);
  // v0.2 — pick any model to chat with (resident / on-demand local / OpenRouter).
  const [laneOptions, setLaneOptions] = useState({
    local: [],
    groups: { frontier: [], open: [], project_base: [] },
    all: [],
    has_key: false,
  });
  const [selectedLane, setSelectedLane] = useState('local:resident');
  const [warmLanes, setWarmLanes] = useState(['local:resident']);
  const [showAllModels, setShowAllModels] = useState(false);
  const [loadStatus, setLoadStatus] = useState(null); // {phase, model, detail}
  // v0.3 — eval-prompt mode. `evalMode` pins {bench_id, qid, reference,
  // scorer_kind, scoring_mode, has_context, context_tokens, question, family,
  // judge_required}; cleared back to free-prompt via the chip's ✕.
  const [benches, setBenches] = useState([]);
  const [judgeInfo, setJudgeInfo] = useState({ local_available: false, openrouter_available: false });
  const [judgeBackend, setJudgeBackend] = useState('local');
  const [evalMode, setEvalMode] = useState(null);
  const [evalDrawerOpen, setEvalDrawerOpen] = useState(false);

  const tailRef = useRef(null);
  const composerRef = useRef(null);
  const abortRef = useRef(null);
  const lastRenderRef = useRef(0);
  const promptHandledRef = useRef(false);

  // Eager lane meta fetch — so the pill renders before any turn is sent.
  useEffect(() => {
    if (isPublicMirrorHost()) {
      setOffline(true);
      return;
    }
    const base = resolveSidecarUrl();
    if (!base) { setOffline(true); return; }
    let cancelled = false;
    (async () => {
      try {
        const resp = await fetch(`${base}/api/lanes`, { headers: { Accept: 'application/json' } });
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
        const body = await resp.json();
        if (cancelled) return;
        if (body.resident) {
          setLaneMeta({
            model: body.resident.model,
            base_url: body.resident.base_url,
            lane_id: body.resident.id || null,
            context_length: body.resident.context_length || null,
          });
        }
      } catch (_e) {
        // Soft-fail: the lane pill will fill in on the first stream's start event.
      }
      // Selectable models (local + curated OpenRouter) + warm state.
      try {
        const r = await fetch(`${base}/api/compare/options`);
        if (r.ok && !cancelled) {
          const data = await r.json();
          const local = data.local || [];
          const groups = data.openrouter_groups || {
            frontier: [], open: [], project_base: [],
          };
          const all = data.openrouter || [];
          setLaneOptions({ local, groups, all, has_key: !!data.has_key });
          const warm = local.filter((o) => o.warm).map((o) => o.id);
          if (!warm.includes('local:resident')) warm.push('local:resident');
          setWarmLanes(warm);
        }
      } catch (_e) { /* keep the resident default */ }
      // Eval benches + judge availability (v0.3).
      try {
        const ev = await fetchBenches();
        if (ev && !cancelled) {
          setBenches(ev.benches || []);
          if (ev.judge) {
            setJudgeInfo(ev.judge);
            if (ev.judge.default_backend) setJudgeBackend(ev.judge.default_backend);
          }
        }
      } catch (_e) { /* eval surface is optional */ }
    })();
    return () => { cancelled = true; };
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

  // Auto-scroll to the latest turn while a stream is in flight.
  useEffect(() => {
    if (tailRef.current) {
      tailRef.current.scrollIntoView({ behavior: 'smooth', block: 'end' });
    }
  }, [turns, streaming]);

  // Toast auto-dismiss
  useEffect(() => {
    if (!toast) return;
    const id = setTimeout(() => setToast(null), 1500);
    return () => clearTimeout(id);
  }, [toast]);

  // ?prompt= query-string handler — funnels the cockpit hero form's
  // submission here. Fires once, scrubs the URL, then auto-sends.
  useEffect(() => {
    if (promptHandledRef.current) return;
    if (offline) return;
    if (typeof window === 'undefined') return;
    try {
      const url = new URL(window.location.href);
      const seeded = url.searchParams.get('prompt');
      if (!seeded) return;
      promptHandledRef.current = true;
      setPrompt(seeded);
      // Scrub so a refresh doesn't re-send.
      url.searchParams.delete('prompt');
      window.history.replaceState({}, '', url.toString());
      // Defer send to after state flush.
      queueMicrotask(() => {
        // Use the latest prompt closure via setPrompt? send() reads
        // `prompt` state, which queueMicrotask will see post-update.
        sendSeed(seeded);
      });
    } catch (_e) {
      // Best-effort — the operator can still type by hand.
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [offline, laneMeta]);

  // ---- send (with optional explicit text — used by the hero seed path)

  const sendSeed = (text) => {
    setPrompt(text);
    queueMicrotask(() => sendImpl(text));
  };
  const send = () => sendImpl(prompt);

  const sendImpl = async (textRaw) => {
    const trimmed = String(textRaw || '').trim();
    if (trimmed.length < MIN_PROMPT || trimmed.length > MAX_PROMPT) return;
    const base = resolveSidecarUrl();
    if (!base) {
      setOffline(true);
      return;
    }
    setError(null);
    setPrompt('');
    setStreaming(true);

    // Snapshot eval state at send time — the operator may clear/repick the
    // chip while the stream is in flight; the score must reflect what was run.
    const evalSnapshot = evalMode;
    const judgeSnapshot = judgeBackend;
    const laneSnapshot = selectedLane;

    // AbortController integration — Stop/Esc abort.
    const ctrl = new AbortController();
    abortRef.current = ctrl;

    // Mount the user turn + an empty assistant card we'll fill.
    setTurns((prev) => [
      ...prev,
      { role: 'user', content: trimmed },
      { role: 'assistant', content: '', reasoning: '', html: '' },
    ]);

    let resp;
    try {
      resp = await fetch(`${base}/api/chat/stream`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Accept: 'text/event-stream',
        },
        body: JSON.stringify({
          prompt: trimmed,
          session_id: sessionId || null,
          lane: selectedLane,
          ...(evalSnapshot
            ? { bench_id: evalSnapshot.bench_id, eval_qid: evalSnapshot.qid }
            : {}),
        }),
        signal: ctrl.signal,
      });
    } catch (err) {
      if (err.name === 'AbortError') {
        markLastAssistantFinish('aborted', null);
        setStreaming(false);
        abortRef.current = null;
        return;
      }
      setError(`Could not reach the sidecar: ${String(err.message || err)}`);
      setStreaming(false);
      abortRef.current = null;
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
      abortRef.current = null;
      setTurns((prev) => {
        const next = prev.slice();
        const last = next[next.length - 1];
        if (last && last.role === 'assistant') {
          next[next.length - 1] = { ...last, content: '', error: detail };
        }
        return next;
      });
      return;
    }

    let acc = { content: '', reasoning: '' };
    let doneMeta = null;
    let aborted = false;
    lastRenderRef.current = 0;

    try {
      for await (const ev of readSse(resp, ctrl.signal)) {
        if (ev.event === 'lane_status') {
          // On-demand local load progress before the first token.
          try {
            const p = JSON.parse(ev.data);
            setLoadStatus({ phase: p.phase, model: p.model, detail: p.detail });
            if (p.phase === 'ready' && p.model) markWarm(`local:${p.model}`);
          } catch (_e) {}
        } else if (ev.event === 'start') {
          setLoadStatus(null);
          try {
            const meta = JSON.parse(ev.data);
            setSessionId(meta.session_id);
            // Refresh lane meta from the actual stream — covers the case
            // where the eager /api/lanes fetch failed.
            setLaneMeta((prev) => ({
              ...(prev || {}),
              model: meta.model || prev?.model,
              base_url: meta.base_url || prev?.base_url,
              lane_id: meta.lane_id || prev?.lane_id,
              context_length: prev?.context_length || null,
            }));
          } catch (_e) {}
        } else if (ev.event === 'token') {
          try {
            const payload = JSON.parse(ev.data);
            if (payload.channel === 'reasoning') {
              acc.reasoning += payload.text;
            } else {
              acc.content += payload.text;
            }
            const now = Date.now();
            const shouldRender = now - lastRenderRef.current > STREAM_RENDER_INTERVAL_MS;
            if (shouldRender) lastRenderRef.current = now;
            setTurns((prev) => {
              const next = prev.slice();
              const last = next[next.length - 1];
              if (last && last.role === 'assistant') {
                next[next.length - 1] = {
                  ...last,
                  content: acc.content,
                  reasoning: acc.reasoning,
                  html: shouldRender ? renderMarkdown(acc.content) : last.html,
                };
              }
              return next;
            });
          } catch (_e) {}
        } else if (ev.event === 'done') {
          try {
            doneMeta = JSON.parse(ev.data);
          } catch (_e) {}
        } else if (ev.event === 'error') {
          setLoadStatus(null);
          try {
            const payload = JSON.parse(ev.data);
            setError(payload.detail || 'Stream errored');
          } catch (_e) {
            setError('Stream errored');
          }
        }
      }
    } catch (err) {
      if (err && (err.name === 'AbortError' || ctrl.signal.aborted)) {
        aborted = true;
      } else {
        setError(`Stream broke: ${String(err.message || err)}`);
      }
    } finally {
      // Pin perf metadata + final markdown render.
      const wantScore = !aborted && evalSnapshot && doneMeta?.turn_id;
      setTurns((prev) => {
        const next = prev.slice();
        const last = next[next.length - 1];
        if (last && last.role === 'assistant') {
          const finalContent = acc.content || last.content;
          next[next.length - 1] = {
            ...last,
            content: finalContent,
            reasoning: acc.reasoning || last.reasoning,
            html: renderMarkdown(finalContent),
            ttft_ms: doneMeta?.ttft_ms ?? null,
            tok_per_s: doneMeta?.tok_per_s ?? null,
            tokens_out: doneMeta?.tokens_out ?? null,
            finish_reason: aborted ? 'aborted' : (doneMeta?.finish_reason ?? null),
            turn_id: doneMeta?.turn_id ?? null,
            // Show the reference + a scoring spinner immediately on eval turns.
            reference: evalSnapshot ? evalSnapshot.reference : null,
            scorePending: !!wantScore,
          };
        }
        return next;
      });
      setStreaming(false);
      abortRef.current = null;
      composerRef.current?.focus();
      void refreshSessions();
      // v0.3 — score the completed eval turn (deterministic = instant; judge =
      // a beat later). Patches the matching turn by turn_id.
      if (wantScore) {
        void scoreEvalTurn(doneMeta.turn_id, evalSnapshot, judgeSnapshot, laneSnapshot);
      }
    }
  };

  // Score a completed eval turn out-of-band and patch it by turn_id.
  const scoreEvalTurn = async (turnId, snap, judge, lane) => {
    const crossVertical = benchForLane(lane) !== snap.bench_id;
    const res = await scoreChatTurn({
      turn_id: turnId,
      bench_id: snap.bench_id,
      eval_qid: snap.qid,
      lane_id: lane,
      cross_vertical: crossVertical,
      judge: { backend: judge },
    });
    setTurns((prev) =>
      prev.map((t) =>
        t.turn_id === turnId
          ? {
              ...t,
              scorePending: false,
              score: res,
              reference: (res && res.reference) || snap.reference || t.reference,
              crossVertical,
            }
          : t,
      ),
    );
  };

  // Helper used by abort/error paths — just sets finish_reason on the
  // last assistant turn without touching content.
  const markLastAssistantFinish = (reason, doneMeta) => {
    setTurns((prev) => {
      const next = prev.slice();
      const last = next[next.length - 1];
      if (last && last.role === 'assistant') {
        next[next.length - 1] = {
          ...last,
          finish_reason: reason,
          ttft_ms: doneMeta?.ttft_ms ?? last.ttft_ms ?? null,
          tok_per_s: doneMeta?.tok_per_s ?? last.tok_per_s ?? null,
        };
      }
      return next;
    });
  };

  // ---- abort/stop

  const abort = () => {
    if (abortRef.current) {
      try { abortRef.current.abort(); } catch (_e) {}
    }
  };

  // ---- new chat / clear

  const newChat = () => {
    abort();
    setTurns([]);
    setSessionId(null);
    setError(null);
    setPrompt('');
    setEvalMode(null);
    promptHandledRef.current = true; // avoid re-firing the seed handler
    composerRef.current?.focus();
  };

  // ---- copy + regenerate

  const copyAssistant = async (turn) => {
    try {
      await navigator.clipboard.writeText(turn.content || '');
      setToast('Copied to clipboard');
    } catch (_e) {
      setToast('Clipboard unavailable');
    }
  };

  const regenerateLast = () => {
    // Pop last assistant + last user, restore prompt, send.
    if (streaming) return;
    let userPrompt = null;
    setTurns((prev) => {
      const next = prev.slice();
      // Find last assistant + the user turn immediately before it.
      let assistantIdx = -1;
      for (let i = next.length - 1; i >= 0; i--) {
        if (next[i].role === 'assistant') { assistantIdx = i; break; }
      }
      if (assistantIdx < 1) return prev;
      if (next[assistantIdx - 1].role !== 'user') return prev;
      userPrompt = next[assistantIdx - 1].content;
      next.splice(assistantIdx - 1, 2);
      return next;
    });
    if (userPrompt) {
      // Defer so the splice flushes before we re-mount the turn pair.
      queueMicrotask(() => sendImpl(userPrompt));
    }
  };

  // ---- session switcher data

  const refreshSessions = async () => {
    const base = resolveSidecarUrl();
    if (!base) return;
    try {
      const resp = await fetch(`${base}/api/chat/sessions?limit=${SESSIONS_LIMIT}`);
      if (!resp.ok) return;
      const body = await resp.json();
      setSessions(Array.isArray(body.sessions) ? body.sessions : []);
    } catch (_e) {}
  };

  const openSwitcher = () => {
    setSessionsOpen((v) => !v);
    void refreshSessions();
  };

  const loadSession = async (id) => {
    if (!id || id === sessionId) { setSessionsOpen(false); return; }
    const base = resolveSidecarUrl();
    if (!base) return;
    abort();
    try {
      const resp = await fetch(`${base}/api/chat/sessions/${encodeURIComponent(id)}`);
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const body = await resp.json();
      const replay = (body.turns || []).map((t) => ({
        role: t.role,
        content: t.content || '',
        reasoning: t.reasoning || '',
        html: t.role === 'assistant' ? renderMarkdown(t.content || '') : undefined,
        ttft_ms: t.ttft_ms ?? null,
        tok_per_s: t.tok_per_s ?? null,
        tokens_out: t.tokens_out ?? null,
        finish_reason: t.finish_reason ?? null,
      }));
      setTurns(replay);
      setSessionId(body.session_id);
      setSessionsOpen(false);
      setError(null);
    } catch (err) {
      setError(`Couldn't load session: ${String(err.message || err)}`);
    }
  };

  // ---- slash menu

  const slashMatch = (() => {
    const lead = prompt.trimStart();
    if (!lead.startsWith('/')) return null;
    const q = lead.slice(1).split(/\s/)[0].toLowerCase();
    const items = SLASH_COMMANDS.filter((c) =>
      c.name.slice(1).toLowerCase().startsWith(q),
    );
    return { q, items };
  })();
  const slashOpen = !!slashMatch && slashMatch.items.length > 0 && !streaming;

  const runSlash = (cmd) => {
    const fullText = prompt.trim();
    // Strip the slash command + leading whitespace; the remainder is the arg.
    const rest = fullText.replace(/^\/\S+\s*/, '');
    if (cmd.name === '/clear') {
      newChat();
      return;
    }
    if (cmd.name === '/copy') {
      const lastAssistant = [...turns].reverse().find((t) => t.role === 'assistant');
      if (lastAssistant) {
        void copyAssistant(lastAssistant);
      } else {
        setToast('Nothing to copy');
      }
      setPrompt('');
      return;
    }
    if (cmd.name === '/compare') {
      const target = rest || '';
      if (typeof window !== 'undefined') {
        window.location.assign(
          `/arena/compare/?prompt=${encodeURIComponent(target)}`,
        );
      }
      return;
    }
    if (cmd.name === '/eval') {
      setPrompt('');
      setEvalDrawerOpen(true);
      return;
    }
  };

  // ---- keyboard handler (composer)

  const onKey = (ev) => {
    if (ev.key === 'Escape') {
      if (sessionsOpen) {
        setSessionsOpen(false);
        ev.preventDefault();
        return;
      }
      if (streaming) {
        ev.preventDefault();
        abort();
        return;
      }
    }
    if (slashOpen) {
      if (ev.key === 'ArrowDown') {
        ev.preventDefault();
        setSlashIdx((i) => Math.min(slashMatch.items.length - 1, i + 1));
        return;
      }
      if (ev.key === 'ArrowUp') {
        ev.preventDefault();
        setSlashIdx((i) => Math.max(0, i - 1));
        return;
      }
      if (ev.key === 'Tab' || (ev.key === 'Enter' && !ev.metaKey && !ev.ctrlKey)) {
        ev.preventDefault();
        const sel = slashMatch.items[Math.min(slashIdx, slashMatch.items.length - 1)];
        if (sel) runSlash(sel);
        return;
      }
    }
    // Cmd/Ctrl-Enter submits.
    if ((ev.metaKey || ev.ctrlKey) && ev.key === 'Enter' && !streaming) {
      ev.preventDefault();
      send();
    }
  };

  // Keep slash highlight in range as user types.
  useEffect(() => {
    if (slashOpen && slashMatch && slashIdx >= slashMatch.items.length) {
      setSlashIdx(0);
    }
  }, [prompt, slashOpen, slashIdx, slashMatch]);

  // ---- live token-count heuristic
  const tokenCount = Math.max(0, Math.ceil(prompt.length / 4));
  const tokenWarn = laneMeta?.context_length && tokenCount > laneMeta.context_length * 0.6;

  // ---- model selection + on-demand load
  const isOnDemand = (id) =>
    typeof id === 'string' && id.startsWith('local:') && id !== 'local:resident';
  const needsLoad = (id) => isOnDemand(id) && !warmLanes.includes(id);
  const markWarm = (id) => {
    setWarmLanes((prev) => {
      if (id === 'local:resident') return prev.includes(id) ? prev : [...prev, id];
      const keep = prev.filter((x) => x === 'local:resident');
      if (!keep.length) keep.push('local:resident');
      return [...keep, id];
    });
  };
  const laneLabel = (id) => {
    const g = laneOptions.groups || {};
    const pool = [
      ...(laneOptions.local || []),
      ...(laneOptions.all || []),
      ...(g.frontier || []),
      ...(g.open || []),
      ...(g.project_base || []),
    ];
    const f = pool.find((o) => o.id === id);
    return f ? f.label : id;
  };

  // Pre-warm an on-demand local lane on click (same progress as a chat turn).
  const loadLane = async (laneSpec) => {
    const base = resolveSidecarUrl();
    if (!base) { setOffline(true); return; }
    setLoadStatus({ phase: 'loading', model: laneSpec.replace(/^local:/, ''), detail: 'starting' });
    let resp;
    try {
      resp = await fetch(`${base}/api/local/load`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Accept: 'text/event-stream' },
        body: JSON.stringify({ lane: laneSpec }),
      });
    } catch (err) {
      setLoadStatus(null);
      setError(`Could not reach the sidecar: ${String(err.message || err)}`);
      return;
    }
    if (!resp.ok || !resp.body) { setLoadStatus(null); setError(`Load failed: HTTP ${resp.status}`); return; }
    try {
      for await (const ev of readSse(resp)) {
        const p = (() => { try { return JSON.parse(ev.data); } catch (_e) { return null; } })();
        if (ev.event === 'status') {
          setLoadStatus({ phase: p.phase, model: p.model, detail: p.detail });
        } else if (ev.event === 'done') {
          setLoadStatus(null);
          markWarm(laneSpec);
        } else if (ev.event === 'error') {
          setLoadStatus(null);
          setError(p?.detail || 'Model load failed');
        }
      }
    } catch (err) {
      setLoadStatus(null);
      setError(`Load stream broke: ${String(err.message || err)}`);
    }
  };

  // ---- offline render

  if (offline) {
    return (
      <div class="chat-lane chat-lane--offline">
        <p class="chat-lane__status">
          Sidecar offline — start with <code>fieldkit arena serve</code> on
          the Spark, then refresh this page.
        </p>
      </div>
    );
  }

  // ---- main render

  return (
    <div class="chat-lane">
      <div class="chat-lane__topbar">
        <LanePill meta={laneMeta} />
        <SessionSwitcher
          sessions={sessions}
          currentId={sessionId}
          open={sessionsOpen}
          onToggle={openSwitcher}
          onPick={loadSession}
        />
        <span class="chat-lane__topbar-spacer" />
        <button
          type="button"
          class="arena-btn--ghost"
          onClick={newChat}
          title="Start a fresh chat session"
        >
          ＋ New chat
        </button>
      </div>

      <div class="chat-modelbar">
        <span class="chat-modelbar__label">Chatting with</span>
        <LaneSelect
          value={selectedLane}
          disabled={streaming || !!loadStatus}
          options={laneOptions}
          showAll={showAllModels}
          onChange={setSelectedLane}
        />
        {loadStatus ? (
          <span class="chat-modelbar__status">
            <span class="chat-modelbar__spinner" aria-hidden="true" />
            {({
              teardown: 'Unloading prior model',
              loading: 'Loading model',
              warming: 'Warming on GPU',
              ready: 'Ready',
            })[loadStatus.phase] || loadStatus.phase}
            {loadStatus.detail ? <span class="dim"> · {loadStatus.detail}</span> : null}
          </span>
        ) : needsLoad(selectedLane) ? (
          <span class="chat-modelbar__needsload">
            <span class="chat-modelbar__warn">⚠ not loaded</span>
            <button
              type="button"
              class="chat-modelbar__loadbtn"
              disabled={streaming}
              onClick={() => loadLane(selectedLane)}
            >
              ⤓ Load model
            </button>
          </span>
        ) : isOnDemand(selectedLane) ? (
          <span class="chat-modelbar__warm">● loaded</span>
        ) : null}
        <span class="chat-lane__topbar-spacer" />
        {benches.some((b) => b.available) && (
          <button
            type="button"
            class="arena-btn--ghost eval-trigger"
            disabled={streaming}
            onClick={() => setEvalDrawerOpen(true)}
            title="Browse eval-bench prompts + score against the reference"
          >
            🧪 Eval prompts
          </button>
        )}
        {laneOptions.all.length > 0 && (
          <label class="chat-modelbar__allmodels" title="Toggle the full OpenRouter catalog">
            <input
              type="checkbox"
              checked={showAllModels}
              disabled={streaming}
              onChange={(ev) => setShowAllModels(ev.currentTarget.checked)}
            />
            all {laneOptions.all.length}
          </label>
        )}
      </div>

      <div class="chat-lane__transcript">
        {turns.length === 0 ? (
          <EmptyState
            onPick={(body) => { setPrompt(body); composerRef.current?.focus(); }}
            onEval={benches.some((b) => b.available) ? () => setEvalDrawerOpen(true) : null}
          />
        ) : (
          <>
            {turns.map((t, i) => (
              <TurnCard
                key={i}
                turn={t}
                streaming={streaming && i === turns.length - 1}
                isLast={i === turns.length - 1}
                canRegenerate={!streaming && i === turns.length - 1 && t.role === 'assistant'}
                onCopy={() => copyAssistant(t)}
                onRegenerate={regenerateLast}
              />
            ))}
          </>
        )}
        <div ref={tailRef} />
      </div>

      {error && (
        <p class="chat-lane__error">
          <strong>Error.</strong> {error}
        </p>
      )}

      <div class="chat-lane__composer">
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
          class="chat-lane__textarea"
          rows={4}
          placeholder="Ask the resident brain anything…  (type / for commands)"
          value={prompt}
          disabled={streaming}
          onInput={(ev) => setPrompt(ev.currentTarget.value)}
          onKeyDown={onKey}
        />
        <span class={`chat-tokencount${tokenWarn ? ' chat-tokencount--warn' : ''}`}>
          ~{tokenCount.toLocaleString()} tok
        </span>
        {slashOpen && (
          <SlashMenu items={slashMatch.items} activeIdx={slashIdx} onSelect={runSlash} />
        )}
        <div class="chat-lane__composer-actions">
          <div class="chat-kbd-row">
            <span class="chat-kbd-hint"><kbd>⌘</kbd>+<kbd>Enter</kbd> send</span>
            <span class="chat-kbd-hint"><kbd>Esc</kbd> stop</span>
            <span class="chat-kbd-hint"><kbd>/</kbd> commands</span>
            {laneMeta?.lane_id && (
              <span class="chat-kbd-hint" style="margin-left: auto;">
                lane: {shortModel(laneMeta.model)}
              </span>
            )}
          </div>
          {streaming ? (
            <button
              type="button"
              class="chat-lane__send chat-lane__send--stop"
              onClick={abort}
              title="Stop streaming (Esc)"
            >
              ◼ Stop
            </button>
          ) : (
            <button
              type="button"
              class="chat-lane__send"
              disabled={prompt.trim().length === 0}
              onClick={send}
            >
              Send
            </button>
          )}
        </div>
      </div>

      {toast && <div class="chat-toast" role="status">{toast}</div>}

      <EvalPromptDrawer
        open={evalDrawerOpen}
        onClose={() => setEvalDrawerOpen(false)}
        benches={benches}
        scopeLanes={[selectedLane]}
        onPick={pickEvalPrompt}
      />
    </div>
  );
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

// Model picker — Local (resident + on-demand article models, marked ⤓) then
// the curated frontier / open / project-base groups, or the full catalog.
function LaneSelect({ value, disabled, options, showAll, onChange }) {
  const g = options.groups || { frontier: [], open: [], project_base: [] };
  return (
    <select
      class="compare-duel__select chat-modelbar__select"
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

function LanePill({ meta }) {
  if (!meta) {
    return (
      <span class="chat-lane-pill" title="Resident lane probing">
        <span class="chat-lane-pill__model">resident brain</span>
        <span class="chat-lane-pill__sep">·</span>
        <span class="chat-lane-pill__endpoint">probing…</span>
      </span>
    );
  }
  return (
    <span class="chat-lane-pill" title="Lane swap is v0.2">
      <span class="chat-lane-pill__model">{shortModel(meta.model)}</span>
      <span class="chat-lane-pill__sep">·</span>
      <span class="chat-lane-pill__endpoint">{shortEndpoint(meta.base_url)}</span>
      <span class="chat-lane-pill__sep">·</span>
      <span class="chat-lane-pill__ctx">{fmtCtx(meta.context_length)}</span>
    </span>
  );
}

function SessionSwitcher({ sessions, currentId, open, onToggle, onPick }) {
  const currentShort = currentId ? shortId(currentId) : 'new';
  return (
    <div class="chat-session-switcher">
      <button
        type="button"
        class="chat-session-switcher__pill"
        onClick={onToggle}
        aria-expanded={open ? 'true' : 'false'}
      >
        Session <span style="color: var(--arena-accent-glow);">#{currentShort}</span>
        <span class="chat-session-switcher__chevron">{open ? '▴' : '▾'}</span>
      </button>
      {open && (
        <div class="chat-session-switcher__popover" role="listbox">
          {sessions.length === 0 ? (
            <div class="chat-session-switcher__empty">No prior sessions yet.</div>
          ) : (
            sessions.map((s) => (
              <div
                key={s.id}
                class={`chat-session-switcher__row${s.id === currentId ? ' chat-session-switcher__row--current' : ''}`}
                role="option"
                aria-selected={s.id === currentId ? 'true' : 'false'}
                onClick={() => onPick(s.id)}
              >
                <span class="chat-session-switcher__row-id">#{shortId(s.id)}</span>
                <span>{s.turn_count} turn{s.turn_count === 1 ? '' : 's'} · {(s.lane_id || '').replace(/::[a-z0-9-]+$/, '')}</span>
                <span class="chat-session-switcher__row-meta">{relTime(s.created_at)}</span>
              </div>
            ))
          )}
        </div>
      )}
    </div>
  );
}

function EmptyState({ onPick, onEval }) {
  return (
    <div class="chat-empty">
      <p class="chat-empty__title">Start a turn against the resident brain.</p>
      <p class="chat-empty__sub">streams via SSE · operator-private · never mirrored</p>
      <div class="chat-prompt-chips">
        {onEval && (
          <button type="button" class="chat-prompt-chip chat-prompt-chip--eval" onClick={onEval}>
            <span class="chat-prompt-chip__kind">🧪 Eval</span>
            <span class="chat-prompt-chip__body">Try an eval-bench prompt — see the reference + an auto-score.</span>
          </button>
        )}
        {PROMPT_CHIPS.map((c) => (
          <button
            key={c.kind}
            type="button"
            class="chat-prompt-chip"
            onClick={() => onPick(c.body)}
          >
            <span class="chat-prompt-chip__kind">{c.kind}</span>
            <span class="chat-prompt-chip__body">{c.body}</span>
          </button>
        ))}
      </div>
    </div>
  );
}

function SlashMenu({ items, activeIdx, onSelect }) {
  return (
    <div class="chat-slashmenu" role="menu">
      <div class="chat-slashmenu__head">Slash commands · ⏎ select · ↑↓ move · Esc close</div>
      {items.map((c, i) => (
        <div
          key={c.name}
          class={`chat-slashmenu__row${i === activeIdx ? ' chat-slashmenu__row--active' : ''}`}
          role="menuitem"
          onClick={() => onSelect(c)}
        >
          <span class="chat-slashmenu__name">{c.name}</span>
          <span class="chat-slashmenu__desc">{c.desc}</span>
        </div>
      ))}
    </div>
  );
}

function TurnCard({ turn, streaming, isLast, canRegenerate, onCopy, onRegenerate }) {
  const [showThink, setShowThink] = useState(false);

  if (turn.role === 'user') {
    return (
      <div class="chat-turn chat-turn--user">
        <div class="chat-turn__role">You</div>
        <div class="chat-turn__body">{turn.content}</div>
        <div class="chat-turn__actions">
          <button
            type="button"
            class="chat-turn__action"
            onClick={onCopy}
            title="Copy this prompt"
          >⎘ Copy</button>
        </div>
      </div>
    );
  }

  return (
    <div
      class={`chat-turn chat-turn--assistant ${
        streaming ? 'chat-turn--streaming' : ''
      } ${turn.error ? 'chat-turn--error' : ''}`}
    >
      <div class="chat-turn__role">Brain</div>
      {turn.reasoning && turn.reasoning.length > 0 && (
        <details
          class="chat-turn__think"
          open={showThink}
          onToggle={(ev) => setShowThink(ev.currentTarget.open)}
        >
          <summary>
            💭 Reasoning ({turn.reasoning.length.toLocaleString()} chars)
          </summary>
          <pre class="chat-turn__think-body">{turn.reasoning}</pre>
        </details>
      )}
      <div class="chat-turn__body">
        {turn.error ? (
          <em class="chat-turn__error-body">{turn.error}</em>
        ) : turn.html ? (
          <div class="chat-markdown" dangerouslySetInnerHTML={{ __html: turn.html }} />
        ) : turn.content ? (
          <div class="chat-markdown">{turn.content}</div>
        ) : streaming ? (
          <span class="chat-turn__cursor">▍</span>
        ) : (
          <em>(no answer text)</em>
        )}
        {streaming && turn.html && (
          <span class="chat-turn__cursor" style="margin-left: 0.2rem;">▍</span>
        )}
      </div>
      {(turn.ttft_ms != null || turn.tok_per_s != null || turn.finish_reason) && (
        <div class="chat-turn__perf">
          {turn.ttft_ms != null && (
            <span class="chat-turn__chip">TTFT {fmtMs(turn.ttft_ms)}</span>
          )}
          {turn.tok_per_s != null && (
            <span class="chat-turn__chip">{fmtTok(turn.tok_per_s)}</span>
          )}
          {turn.tokens_out != null && (
            <span class="chat-turn__chip">
              ≈{turn.tokens_out.toLocaleString()} tok
            </span>
          )}
          {turn.finish_reason && (
            <span class="chat-turn__chip chat-turn__chip--muted">
              {turn.finish_reason}
            </span>
          )}
          {turn.crossVertical && (
            <span class="chat-turn__chip chat-turn__chip--muted" title="Scored against a bench that isn't this model's own vertical">
              cross-vertical · judged
            </span>
          )}
        </div>
      )}
      {(turn.scorePending || turn.score || turn.reference) && (
        <div class="chat-turn__eval">
          <EvalScore result={turn.score} pending={turn.scorePending} />
          <ReferencePanel reference={turn.reference} />
        </div>
      )}
      <div class="chat-turn__actions">
        <button
          type="button"
          class="chat-turn__action"
          onClick={onCopy}
          title="Copy this answer"
        >⎘ Copy</button>
        {canRegenerate && (
          <button
            type="button"
            class="chat-turn__action chat-turn__action--ok"
            onClick={onRegenerate}
            title="Re-run the prior prompt"
          >↻ Regenerate</button>
        )}
      </div>
    </div>
  );
}
