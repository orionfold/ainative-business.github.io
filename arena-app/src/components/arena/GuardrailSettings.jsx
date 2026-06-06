/** @jsxImportSource preact */
// GuardrailSettings — `<GuardrailSettings>` Preact island for /arena/settings/.
//
// arena-guardrail-settings (GS-3): the operator-config surface over the AE-17
// cloud-run eval guardrails. View the effective thresholds with per-field
// provenance (file / env / default), edit them, reset to defaults, and flip the
// master `enabled` switch — the next cloud eval picks up the change with NO
// restart (GS-1: the arm path reads load_config() per dispatch). Deterministic
// CRUD over GET/POST /api/guardrail-config — no LLM (feedback_llm_skill_pattern).
//
// Operator-private: the config is a JSON file under ~/.fieldkit/arena/, never a
// table, never mirrored. On the public mirror the sidecar is offline → this
// renders a short offline note (the page chrome explains the rest).

import { useEffect, useRef, useState } from 'preact/hooks';
import { resolveSidecarUrl, isPublicMirrorHost } from '../../lib/arena/sidecar.mjs';

const SOURCE_LABEL = { file: 'edited', env: 'env', default: 'default' };

function SourceChip({ source }) {
  const s = source || 'default';
  return (
    <span class="gsettings__source" data-source={s} title={`resolved from: ${s} (file > env > default)`}>
      {SOURCE_LABEL[s] || s}
    </span>
  );
}

function detailText(j) {
  if (!j) return '';
  if (typeof j.detail === 'string') return j.detail;
  if (Array.isArray(j.detail) && j.detail[0]) return j.detail[0].msg || '';
  return '';
}

// BUG-3 / AF-29 — the G3-arming disclosure. The cost cap only protects a run
// when a price row exists for the exact model_id; this makes that dependency
// visible per roster model (priced? source? captured-at?) and maintainable
// (one deterministic OpenRouter catalog capture). Without it, G3 can sit
// silently inert — exactly what the e2e smoke caught.
function PriceCoverage({ base }) {
  const [data, setData] = useState(null); // {models, unpriced, enabled, cost_cap_usd}
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState(null); // {kind:'ok'|'err', msg}

  async function load() {
    try {
      const r = await fetch(`${base}/api/prices`);
      if (r.ok) setData(await r.json());
    } catch (_e) {
      /* the parent already renders the offline story */
    }
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function refresh() {
    if (busy) return;
    setBusy(true);
    setNote(null);
    try {
      const r = await fetch(`${base}/api/prices/refresh`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({}),
      });
      const j = await r.json().catch(() => ({}));
      if (!r.ok) {
        setNote({ kind: 'err', msg: detailText(j) || `refresh failed (${r.status})` });
        return;
      }
      const n = (j.refreshed || []).length;
      const miss = (j.still_unpriced || []).length;
      setNote({
        kind: miss ? 'err' : 'ok',
        msg: j.note || `captured ${n} price${n === 1 ? '' : 's'}${miss ? ` · ${miss} still unpriced (not in the catalog)` : ''}`,
      });
      await load();
    } catch (_e) {
      setNote({ kind: 'err', msg: 'sidecar unreachable' });
    } finally {
      setBusy(false);
    }
  }

  if (!data) return null;
  const models = data.models || [];
  return (
    <section class="gsettings__prices">
      <h2 class="gsettings__prices-title">G3 price coverage</h2>
      <p class="gsettings__hint">
        The $ cap arms only when the evaled model has a price row. Roster = cloud models from recent
        eval jobs; unpriced ⇒ that model's next run is <b>tokens-only</b> (no $ cap can trip).
      </p>
      {data.unpriced > 0 && (
        <div class="gsettings__banner" role="alert">
          <span class="gsettings__banner-flag">⚠ G3 unarmed for {data.unpriced} model{data.unpriced === 1 ? '' : 's'}</span>
          <span class="gsettings__banner-note">Refresh prices below, or the cost cap cannot trip for them.</span>
        </div>
      )}
      {models.length === 0 ? (
        <p class="gsettings__prices-empty">No cloud-eval models on the roster yet — dispatch a cloud eval and its model appears here.</p>
      ) : (
        <table class="gsettings__prices-table">
          <thead>
            <tr><th>model</th><th>armed</th><th>$/M in · out</th><th>source</th><th>captured</th></tr>
          </thead>
          <tbody>
            {models.map((m) => (
              <tr key={m.model_id} data-priced={m.priced ? 'true' : 'false'}>
                <td><code>{m.model_id}</code></td>
                <td>{m.priced ? '✓' : '✗ tokens-only'}</td>
                <td>{m.priced ? `$${m.price_per_m_input_usd} · $${m.price_per_m_output_usd}` : '—'}</td>
                <td>{m.priced ? m.source : '—'}</td>
                <td>{m.priced ? String(m.captured_at).slice(0, 10) : '—'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      <div class="gsettings__actions">
        <button type="button" class="gsettings__save" onClick={refresh} disabled={busy}>
          {busy ? 'refreshing…' : 'Refresh prices'}
        </button>
        {note && (
          <span class="gsettings__toast" data-kind={note.kind}>
            {note.msg}
          </span>
        )}
      </div>
    </section>
  );
}

export default function GuardrailSettings() {
  const [status, setStatus] = useState('loading'); // loading | ready | offline
  const [cfg, setCfg] = useState(null); // {effective, sources, defaults, bounds}
  const [stall, setStall] = useState('');
  const [cost, setCost] = useState('');
  const [enabled, setEnabled] = useState(true);
  const [busy, setBusy] = useState(false);
  const [toast, setToast] = useState(null); // {kind:'ok'|'err', msg}
  const baseRef = useRef(null);

  useEffect(() => {
    if (isPublicMirrorHost()) {
      setStatus('offline');
      return;
    }
    const base = resolveSidecarUrl();
    if (!base) {
      setStatus('offline');
      return;
    }
    baseRef.current = base;
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function hydrate(j) {
    setCfg(j);
    setStall(String(j.effective.stall_timeout_s));
    setCost(String(j.effective.cost_cap_usd));
    setEnabled(Boolean(j.effective.enabled));
  }

  async function load() {
    try {
      const r = await fetch(`${baseRef.current}/api/guardrail-config`);
      if (!r.ok) {
        setStatus('offline');
        return;
      }
      hydrate(await r.json());
      setStatus('ready');
    } catch (_e) {
      setStatus('offline');
    }
  }

  async function post(payload, okMsg) {
    if (busy) return;
    setBusy(true);
    try {
      const r = await fetch(`${baseRef.current}/api/guardrail-config`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      if (r.status === 422) {
        const j = await r.json().catch(() => ({}));
        setToast({ kind: 'err', msg: detailText(j) || 'value out of range' });
        return;
      }
      if (!r.ok) {
        setToast({ kind: 'err', msg: `save failed (${r.status})` });
        return;
      }
      const j = await r.json();
      hydrate({ ...cfg, effective: j.effective, sources: j.sources });
      setToast({ kind: 'ok', msg: okMsg });
    } catch (_e) {
      setToast({ kind: 'err', msg: 'sidecar unreachable' });
    } finally {
      setBusy(false);
    }
  }

  function save(e) {
    if (e) e.preventDefault();
    post(
      { stall_timeout_s: Number(stall), cost_cap_usd: Number(cost), enabled },
      'saved — the next cloud eval picks it up'
    );
  }

  function resetDefaults() {
    if (!cfg) return;
    const d = cfg.defaults;
    post(
      {
        stall_timeout_s: Number(d.stall_timeout_s),
        cost_cap_usd: Number(d.cost_cap_usd),
        enabled: Boolean(d.enabled),
      },
      'reset to defaults'
    );
  }

  if (status === 'offline') {
    return (
      <div class="gsettings gsettings--offline">
        <p class="gsettings__offline">
          The guardrail config is operator-private and only editable when the Arena sidecar
          is live on this machine (loopback). It is invisible on the public mirror.
        </p>
      </div>
    );
  }
  if (status === 'loading' || !cfg) {
    return <div class="gsettings gsettings--loading">loading config…</div>;
  }

  const off = cfg.effective.enabled === false;
  const [stallLo, stallHi] = cfg.bounds.stall_timeout_s || [30, 86400];
  const [costLo, costHi] = cfg.bounds.cost_cap_usd || [0, 1000];

  return (
    <div class="gsettings">
      {off && (
        <div class="gsettings__banner" role="alert">
          <span class="gsettings__banner-flag">⚠ Cloud-eval guardrails OFF</span>
          <span class="gsettings__banner-note">
            Metered cloud evals run <b>unguarded</b> — no stall watchdog, no cost cap. Re-enable below
            before a long cloud run.
          </span>
        </div>
      )}

      <form class="gsettings__form" onSubmit={save}>
        {/* master toggle */}
        <div class="gsettings__row gsettings__row--toggle">
          <label class="gsettings__label" for="gs-enabled">
            Guardrails <SourceChip source={cfg.sources.enabled} />
          </label>
          <label class="gsettings__switch">
            <input
              id="gs-enabled"
              type="checkbox"
              checked={enabled}
              onChange={(e) => setEnabled(e.currentTarget.checked)}
            />
            <span class="gsettings__switch-track" aria-hidden="true" />
            <span class="gsettings__switch-text">{enabled ? 'on' : 'off'}</span>
          </label>
          <p class="gsettings__hint">
            When off, cloud evals run unguarded (the operator opt-out for a trusted long run).
          </p>
        </div>

        {/* cost cap (G3) */}
        <div class="gsettings__row">
          <label class="gsettings__label" for="gs-cost">
            Per-run cost cap (G3) <SourceChip source={cfg.sources.cost_cap_usd} />
          </label>
          <div class="gsettings__field">
            <span class="gsettings__prefix">$</span>
            <input
              id="gs-cost"
              type="number"
              step="0.01"
              min={costLo}
              max={costHi}
              value={cost}
              disabled={!enabled}
              onInput={(e) => setCost(e.currentTarget.value)}
            />
          </div>
          <p class="gsettings__hint">
            Aborts a cloud eval once accrued spend exceeds this. Range ${costLo}–${costHi}; 0 disables G3.
            Default ${cfg.defaults.cost_cap_usd}.
          </p>
        </div>

        {/* stall window (G2) */}
        <div class="gsettings__row">
          <label class="gsettings__label" for="gs-stall">
            Stall timeout (G2) <SourceChip source={cfg.sources.stall_timeout_s} />
          </label>
          <div class="gsettings__field">
            <input
              id="gs-stall"
              type="number"
              step="1"
              min="0"
              value={stall}
              disabled={!enabled}
              onInput={(e) => setStall(e.currentTarget.value)}
            />
            <span class="gsettings__suffix">seconds</span>
          </div>
          <p class="gsettings__hint">
            Aborts when no eval row completes within this window (reset per row). Range {stallLo}–{stallHi}s,
            or 0 to disable G2. Default {cfg.defaults.stall_timeout_s}s.
          </p>
        </div>

        <div class="gsettings__actions">
          <button type="submit" class="gsettings__save" disabled={busy}>
            {busy ? 'saving…' : 'Save'}
          </button>
          <button type="button" class="gsettings__reset" onClick={resetDefaults} disabled={busy}>
            Reset to defaults
          </button>
          {toast && (
            <span class="gsettings__toast" data-kind={toast.kind}>
              {toast.msg}
            </span>
          )}
        </div>
      </form>

      <p class="gsettings__foot">
        Applies to <b>new</b> runs — a running eval armed its guardrail at dispatch (an immutable
        snapshot). Edits take effect with no restart. <code>file</code> beats <code>env</code> beats
        the built-in default, per field.
      </p>

      <PriceCoverage base={baseRef.current} />
    </div>
  );
}
