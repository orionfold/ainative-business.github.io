/** @jsxImportSource preact */
// OpenRouterKeySettings — `<OpenRouterKeySettings>` Preact island for /arena/settings/.
//
// The cloud-lane key surface (v0.34 cloud-lane hide rule). The Arena hides the
// OpenRouter catalog + the spend tile until a key is wired — this is where a
// founding-25 customer wires their OWN key to light the cloud lanes up. It
// AUTO-DETECTS a key already present in the environment / .env.local (the
// founding boxes that exported one) and otherwise lets the customer paste +
// save one locally. The key is written to the gitignored .env.local the sidecar
// loads and set live in os.environ — the cloud lanes appear with NO restart.
//
// Privacy by construction: the key never leaves the box. The status route never
// returns the raw value (only a masked form), and Orionfold never sees it.
//
// Deterministic CRUD over GET/POST /api/openrouter-key — no LLM
// (feedback_llm_skill_pattern). Mirrors the <GuardrailSettings> island: offline
// note on the public mirror (the sidecar is loopback-only), toast feedback.

import { useEffect, useRef, useState } from 'preact/hooks';
import { resolveSidecarUrl, isPublicMirrorHost } from '../../lib/arena/sidecar.mjs';

const SOURCE_NOTE = {
  file: 'saved on this machine',
  env: 'auto-detected from your environment',
};

export default function OpenRouterKeySettings() {
  const [status, setStatus] = useState('loading'); // loading | ready | offline
  const [info, setInfo] = useState(null); // {configured, source, masked, env_path}
  const [entry, setEntry] = useState(''); // the in-progress key input
  const [editing, setEditing] = useState(false); // replace-key mode when configured
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

  async function load() {
    try {
      const r = await fetch(`${baseRef.current}/api/openrouter-key`);
      if (!r.ok) {
        setStatus('offline');
        return;
      }
      setInfo(await r.json());
      setStatus('ready');
    } catch (_e) {
      setStatus('offline');
    }
  }

  async function save(e) {
    if (e) e.preventDefault();
    if (busy) return;
    const key = entry.trim();
    if (!key) {
      setToast({ kind: 'err', msg: 'paste a key first' });
      return;
    }
    setBusy(true);
    try {
      const r = await fetch(`${baseRef.current}/api/openrouter-key`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ key }),
      });
      if (r.status === 422) {
        setToast({ kind: 'err', msg: 'that key looks empty' });
        return;
      }
      if (!r.ok) {
        setToast({ kind: 'err', msg: `save failed (${r.status})` });
        return;
      }
      const j = await r.json();
      setInfo({ ...info, configured: true, source: j.source, masked: j.masked });
      setEntry('');
      setEditing(false);
      setToast({
        kind: 'ok',
        msg: 'saved on this box — cloud lanes are now live in Chat & Compare',
      });
    } catch (_e) {
      setToast({ kind: 'err', msg: 'sidecar unreachable' });
    } finally {
      setBusy(false);
    }
  }

  if (status === 'offline') {
    return (
      <div class="gsettings gsettings--offline">
        <p class="gsettings__offline">
          The OpenRouter key is configured only when the Arena sidecar is live on this machine
          (loopback). It is invisible on the public mirror — your key never leaves your box.
        </p>
      </div>
    );
  }
  if (status === 'loading' || !info) {
    return <div class="gsettings gsettings--loading">checking for a key…</div>;
  }

  const privacyLine = (
    <p class="gsettings__hint orkey__privacy">
      🔒 Your key stays on this machine — it is written to a private file the cockpit reads locally.
      <b> Orionfold never sees it</b>, and it is never sent anywhere but OpenRouter when you run a
      cloud lane.
    </p>
  );

  // Configured: a key is already wired (auto-detected or saved here).
  if (info.configured && !editing) {
    return (
      <div class="gsettings orkey">
        <div class="gsettings__banner orkey__banner--ok" role="status">
          <span class="gsettings__banner-flag">✓ Cloud lanes enabled</span>
          <span class="gsettings__banner-note">
            Key <code>{info.masked}</code> — {SOURCE_NOTE[info.source] || 'configured'}. The
            OpenRouter catalog + the spend tile are live in Chat &amp; Compare.
          </span>
        </div>
        {privacyLine}
        <div class="gsettings__actions">
          <button
            type="button"
            class="gsettings__reset"
            onClick={() => {
              setEditing(true);
              setToast(null);
            }}
          >
            Replace key
          </button>
        </div>
      </div>
    );
  }

  // Not configured (or replacing): paste + save.
  return (
    <div class="gsettings orkey">
      {!info.configured && (
        <p class="gsettings__hint">
          The Field Edition runs your Advisor <b>locally</b> — no cloud key required. Add an
          OpenRouter key only if you also want to chat with or compare against frontier cloud models.
          Until then the cloud catalog stays hidden.
        </p>
      )}
      <form class="gsettings__form" onSubmit={save}>
        <div class="gsettings__row">
          <label class="gsettings__label" for="orkey-input">
            OpenRouter API key
          </label>
          <div class="gsettings__field">
            <input
              id="orkey-input"
              type="password"
              autocomplete="off"
              spellcheck={false}
              placeholder="sk-or-v1-…"
              value={entry}
              disabled={busy}
              onInput={(e) => setEntry(e.currentTarget.value)}
            />
          </div>
          <p class="gsettings__hint">
            Get one free at{' '}
            <a href="https://openrouter.ai/keys" target="_blank" rel="noopener noreferrer">
              openrouter.ai/keys
            </a>
            . Paste it here and save — it takes effect immediately, no restart.
          </p>
        </div>
        {privacyLine}
        <div class="gsettings__actions">
          <button type="submit" class="gsettings__save" disabled={busy}>
            {busy ? 'saving…' : 'Save key'}
          </button>
          {info.configured && (
            <button
              type="button"
              class="gsettings__reset"
              disabled={busy}
              onClick={() => {
                setEditing(false);
                setEntry('');
                setToast(null);
              }}
            >
              Cancel
            </button>
          )}
          {toast && (
            <span class="gsettings__toast" data-kind={toast.kind}>
              {toast.msg}
            </span>
          )}
        </div>
      </form>
    </div>
  );
}
