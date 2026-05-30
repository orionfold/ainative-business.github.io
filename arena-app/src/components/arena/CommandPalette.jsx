/** @jsxImportSource preact */
// CommandPalette — the ⌘K global navigator.
//
// Mounted once in ArenaAppLayout (outside <slot/>) so it's available on every
// cockpit page. Fed a build-time `index` prop (models / articles / lanes /
// pages, assembled by lib/arena/command-index.mjs) so fuzzy search works with
// zero network — it survives on the public web preview. When the query doesn't
// match an entry it synthesizes two quick actions: "Ask the brain: …" (routes
// to chat with ?prompt=, which auto-sends) and "Compare: …" (routes to compare
// with ?prompt=, which pre-fills).

import { useEffect, useMemo, useRef, useState } from 'preact/hooks';

const TYPE_LABEL = { page: 'Page', model: 'Model', article: 'Article', lane: 'Lane', action: 'Action' };
const TYPE_GLYPH = { page: '▸', model: '◆', article: '¶', lane: '☷', action: '⚡' };

// Tiny subsequence-fuzzy score: all query chars must appear in order. Lower is
// better; contiguous + early matches win. Returns null on no match.
function fuzzyScore(hay, q) {
  if (!q) return 0;
  let qi = 0, score = 0, last = -1;
  for (let i = 0; i < hay.length && qi < q.length; i++) {
    if (hay[i] === q[qi]) {
      score += (i - last); // gaps cost
      last = i;
      qi++;
    }
  }
  return qi === q.length ? score : null;
}

export default function CommandPalette({ index = [] }) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState('');
  const [sel, setSel] = useState(0);
  const inputRef = useRef(null);

  const chatHref = useMemo(() => (index.find((e) => e.id === 'page:chat')?.href) || '/arena/chat/', [index]);
  const compareHref = useMemo(() => (index.find((e) => e.id === 'page:compare')?.href) || '/arena/compare/', [index]);

  const results = useMemo(() => {
    const q = query.trim().toLowerCase();
    let items;
    if (!q) {
      items = index.filter((e) => e.type === 'page' || e.type === 'model').slice(0, 12);
    } else {
      items = index
        .map((e) => ({ e, s: fuzzyScore(e.keywords, q) }))
        .filter((x) => x.s != null)
        .sort((a, b) => a.s - b.s)
        .slice(0, 16)
        .map((x) => x.e);
    }
    // Synthesize quick actions when there's a free-text query.
    if (q.length >= 2) {
      const enc = encodeURIComponent(query.trim());
      items = items.concat([
        { id: 'act:ask', type: 'action', label: `Ask the brain: “${query.trim()}”`, sub: 'chat · auto-sends', href: `${chatHref}?prompt=${enc}` },
        { id: 'act:compare', type: 'action', label: `Compare: “${query.trim()}”`, sub: 'side-by-side · pre-fills', href: `${compareHref}?prompt=${enc}` },
      ]);
    }
    return items;
  }, [query, index, chatHref, compareHref]);

  // Global ⌘K / Ctrl-K to open; "/" opens too when not typing in a field.
  useEffect(() => {
    const onKey = (e) => {
      const k = e.key?.toLowerCase();
      const inField = /^(input|textarea|select)$/i.test(document.activeElement?.tagName || '') ||
        document.activeElement?.isContentEditable;
      if ((e.metaKey || e.ctrlKey) && k === 'k') {
        e.preventDefault();
        setOpen((o) => !o);
      } else if (k === '/' && !inField && !open) {
        e.preventDefault();
        setOpen(true);
      } else if (k === 'escape' && open) {
        setOpen(false);
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open]);

  // Focus the input + reset selection whenever the palette opens.
  useEffect(() => {
    if (open) {
      setSel(0);
      requestAnimationFrame(() => inputRef.current?.focus());
    } else {
      setQuery('');
    }
  }, [open]);

  useEffect(() => { setSel(0); }, [query]);

  const go = (item) => {
    if (!item) return;
    setOpen(false);
    window.location.href = item.href;
  };

  const onInputKey = (e) => {
    if (e.key === 'ArrowDown') { e.preventDefault(); setSel((s) => Math.min(s + 1, results.length - 1)); }
    else if (e.key === 'ArrowUp') { e.preventDefault(); setSel((s) => Math.max(s - 1, 0)); }
    else if (e.key === 'Enter') { e.preventDefault(); go(results[sel]); }
  };

  if (!open) return null;

  return (
    <div class="cmdk" role="dialog" aria-modal="true" aria-label="Command palette" onClick={() => setOpen(false)}>
      <div class="cmdk__panel" onClick={(e) => e.stopPropagation()}>
        <div class="cmdk__inputrow">
          <span class="cmdk__prompt">⌘K</span>
          <input
            ref={inputRef}
            class="cmdk__input"
            type="text"
            placeholder="Jump to a model, article, lane — or ask the brain…"
            value={query}
            onInput={(e) => setQuery(e.currentTarget.value)}
            onKeyDown={onInputKey}
          />
          <kbd class="cmdk__esc">esc</kbd>
        </div>
        <div class="cmdk__results">
          {results.length === 0 ? (
            <div class="cmdk__empty">No matches — type to ask the brain instead.</div>
          ) : (
            results.map((item, i) => (
              <button
                key={item.id}
                type="button"
                class={`cmdk__row ${i === sel ? 'cmdk__row--active' : ''}`}
                onMouseEnter={() => setSel(i)}
                onClick={() => go(item)}
              >
                <span class={`cmdk__glyph cmdk__glyph--${item.type}`}>{TYPE_GLYPH[item.type] || '·'}</span>
                <span class="cmdk__label">{item.label}</span>
                {item.sub && <span class="cmdk__sub">{item.sub}</span>}
                <span class="cmdk__type">{TYPE_LABEL[item.type] || ''}</span>
              </button>
            ))
          )}
        </div>
        <div class="cmdk__foot">
          <span><kbd>↑</kbd><kbd>↓</kbd> navigate</span>
          <span><kbd>↵</kbd> open</span>
          <span><kbd>esc</kbd> close</span>
          <span class="cmdk__foot-spacer" />
          <span>{index.length} indexed</span>
        </div>
      </div>
    </div>
  );
}
