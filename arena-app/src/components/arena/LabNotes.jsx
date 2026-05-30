/** @jsxImportSource preact */
// LabNotes — `<LabNotes card={id}>` Preact island for /arena/lab/.
//
// Phase 6 annotation layer (operator-private, progressive enhancement). Lets
// the operator pin freeform notes to a Lab board card when the sidecar is live.
// Backed by the deterministic CRUD endpoints GET/POST/DELETE /api/lab/notes —
// no LLM generation (feedback_llm_skill_pattern).
//
// Privacy: the `lab_notes` table is on mirror.FORBIDDEN_TABLES + pinned by
// test_mirror_does_not_leak.py, so notes are NEVER exported. On the public
// mirror this island renders nothing (isPublicMirrorHost short-circuits) — the
// board itself is the public surface; the notes are the operator's private
// margin.

import { useEffect, useRef, useState } from 'preact/hooks';
import { resolveSidecarUrl, isPublicMirrorHost } from '../../lib/arena/sidecar.mjs';

export default function LabNotes({ card, lane = '' }) {
  const [enabled, setEnabled] = useState(true);
  const [notes, setNotes] = useState([]);
  const [open, setOpen] = useState(false);
  const [draft, setDraft] = useState('');
  const [busy, setBusy] = useState(false);
  const baseRef = useRef(null);

  // Resolve sidecar once; public mirror → render nothing.
  useEffect(() => {
    if (isPublicMirrorHost()) {
      setEnabled(false);
      return;
    }
    const base = resolveSidecarUrl();
    if (!base) {
      setEnabled(false);
      return;
    }
    baseRef.current = base;
    refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function refresh() {
    const base = baseRef.current;
    if (!base) return;
    try {
      const r = await fetch(`${base}/api/lab/notes?card_id=${encodeURIComponent(card)}`);
      if (!r.ok) return;
      const j = await r.json();
      setNotes(Array.isArray(j.notes) ? j.notes : []);
    } catch (_e) {
      // sidecar down — keep the toggle but show nothing
    }
  }

  async function addNote(e) {
    e.preventDefault();
    const body = draft.trim();
    if (!body || busy) return;
    setBusy(true);
    try {
      const r = await fetch(`${baseRef.current}/api/lab/notes`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ card_id: card, body, lane }),
      });
      if (r.ok) {
        setDraft('');
        await refresh();
      }
    } catch (_e) {
      /* swallow — best effort */
    } finally {
      setBusy(false);
    }
  }

  async function removeNote(id) {
    if (busy) return;
    setBusy(true);
    try {
      const r = await fetch(`${baseRef.current}/api/lab/notes/${id}`, { method: 'DELETE' });
      if (r.ok) await refresh();
    } catch (_e) {
      /* swallow */
    } finally {
      setBusy(false);
    }
  }

  if (!enabled) return null; // public mirror — invisible

  return (
    <div class="labnotes">
      <button
        type="button"
        class="labnotes__toggle"
        aria-expanded={open}
        onClick={() => setOpen((o) => !o)}
      >
        <span class="labnotes__pin">⊕</span>
        {notes.length > 0 ? `${notes.length} note${notes.length === 1 ? '' : 's'}` : 'pin a note'}
      </button>

      {open && (
        <div class="labnotes__panel">
          {notes.length > 0 && (
            <ul class="labnotes__list">
              {notes.map((n) => (
                <li key={n.id} class="labnotes__item">
                  <span class="labnotes__body">{n.body}</span>
                  <button
                    type="button"
                    class="labnotes__del"
                    aria-label="Delete note"
                    title="Delete note"
                    onClick={() => removeNote(n.id)}
                  >×</button>
                </li>
              ))}
            </ul>
          )}
          <form class="labnotes__form" onSubmit={addNote}>
            <input
              class="labnotes__input"
              type="text"
              value={draft}
              placeholder="operator note (private — never mirrored)…"
              maxLength={4000}
              onInput={(e) => setDraft(e.currentTarget.value)}
            />
            <button type="submit" class="labnotes__add" disabled={busy || !draft.trim()}>
              {busy ? '…' : 'pin'}
            </button>
          </form>
        </div>
      )}
    </div>
  );
}
