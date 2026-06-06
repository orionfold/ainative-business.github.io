/** @jsxImportSource preact */
// ScoutPanel — `<ScoutPanel>` for /arena/compare/ (AE-10, S6).
//
// Surfaces the hf-model-scout top-3 ranked base-model picks (the
// `/tmp/hf-scout/<date>/<vertical>/report.md` the cockpit never saw) so the
// scout decision is visible AND frames the lock-time behavioral gate: A/B a
// candidate base on a held-out prompt before committing a bench — eyeball
// boxing + verbosity (we caught Qwen3-8B's over-think one stage too late).
//
// Read-only. Bases live on HuggingFace un-downloaded, so the panel does NOT
// auto-serve a candidate (one-lane envelope, AE-R4) — it points the operator at
// the held-out gate prompt (the Eval drawer's astro-bench split) and leaves the
// download + lane swap a deliberate operator step. A collapsed `<details>` so it
// never crowds the duel.

import { useEffect, useState } from 'preact/hooks';
import { resolveSidecarUrl } from '../../lib/arena/sidecar.mjs';

async function fetchScout() {
  const base = resolveSidecarUrl();
  if (!base) return null;
  try {
    const r = await fetch(`${base}/api/scout`, { headers: { Accept: 'application/json' } });
    if (!r.ok) return null;
    return r.json();
  } catch (_e) {
    return null;
  }
}

function Axis({ label, value, tone }) {
  if (value == null || value === '') return null;
  return (
    <span class={`scout-axis ${tone ? `scout-axis--${tone}` : ''}`}>
      <span class="scout-axis__k">{label}</span>
      <span class="scout-axis__v">{value}</span>
    </span>
  );
}

function PickCard({ pick }) {
  const commercial = pick.commercial_ok === 'true' || pick.commercial_ok === true;
  const archOk = pick.llama_cpp_compat === 'true' || pick.llama_cpp_compat === true;
  return (
    <div class="scout-pick">
      <div class="scout-pick__head">
        <span class="scout-pick__rank">#{pick.rank}</span>
        <code class="scout-pick__repo">{pick.repo}</code>
        <span class="scout-pick__score" title="hf-model-scout score">{pick.score}/100</span>
      </div>
      {pick.tagline && <p class="scout-pick__tag">{pick.tagline}</p>}
      <div class="scout-pick__axes">
        <Axis label="license" value={pick.license} tone={commercial ? 'ok' : 'warn'} />
        <Axis label="chat" value={pick.chat_format} />
        <Axis label="train" value={pick.training_type} />
        <Axis label="arch" value={pick.arch} tone={archOk ? 'ok' : 'warn'} />
        {pick.q4km_gb != null && <Axis label="Q4_K_M" value={`${pick.q4km_gb} GB`} tone={pick.fits ? 'ok' : 'warn'} />}
        {pick.tg_tok_s != null && <Axis label="tg" value={`${pick.tg_tok_s} tok/s`} />}
      </div>
      {(pick.warnings || []).length > 0 && (
        <p class="scout-pick__warn">⚠ {pick.warnings.join(' · ')}</p>
      )}
    </div>
  );
}

export default function ScoutPanel({ onLoadGate }) {
  const [scout, setScout] = useState(null);
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      const s = await fetchScout();
      if (!cancelled) {
        setScout(s);
        setLoaded(true);
      }
    })();
    return () => { cancelled = true; };
  }, []);

  // Nothing to show until a scout report exists — render nothing (no empty box).
  if (!loaded || !scout || !scout.available || !(scout.picks || []).length) return null;

  return (
    <details class="scout-panel bezel">
      <summary class="scout-panel__summary">
        <span class="scout-panel__icon" aria-hidden="true">🔭</span>
        <span class="scout-panel__title">Scout candidates</span>
        <span class="scout-panel__run">{scout.run}</span>
        <span class="scout-panel__count">top {scout.picks.length} of {scout.n_candidates}</span>
      </summary>
      <div class="scout-panel__body">
        <p class="scout-panel__gate">
          The <code>hf-model-scout</code> top picks the cockpit never saw. Before
          committing a bench, A/B a candidate base on a held-out prompt — eyeball
          boxing + verbosity. <b>This is the lock-time behavioral gate</b> (we
          caught Qwen3-8B's over-think one stage too late).
        </p>
        <div class="scout-panel__picks">
          {scout.picks.map((p) => <PickCard key={p.repo} pick={p} />)}
        </div>
        {(scout.ruled_out || []).length > 0 && (
          <details class="scout-panel__ruled">
            <summary>Ruled out ({scout.ruled_out.length})</summary>
            <ul class="scout-panel__ruled-list">
              {scout.ruled_out.map((r) => (
                <li key={r.repo}>
                  <code>{r.repo}</code> — <span class="dim">{r.reason}</span>
                </li>
              ))}
            </ul>
          </details>
        )}
        <p class="scout-panel__note">
          Serving a base needs a download + a one-lane swap (operator step,
          AE-R4).{' '}
          {onLoadGate ? (
            <button type="button" class="scout-panel__gatebtn" onClick={onLoadGate}>
              🧪 Load a held-out gate prompt
            </button>
          ) : (
            <span>Open <b>🧪 Eval prompts → astro-bench → held-out</b> for the gate prompt.</span>
          )}
        </p>
      </div>
    </details>
  );
}
