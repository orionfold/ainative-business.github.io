// Canonical public home of every deep-dive article. The arena bake PRUNES the
// in-app articles/ tree (live `:7866/arena/articles/*` 404s, and the demo
// deploy drops `dist-arena-demo/articles/` too), so in-bundle relative article
// links 404 everywhere outside dev. Every article's canonical page is the root
// site's `src/pages/field-notes/[slug]/` route (slug = the article collection
// id). Always absolute — it survives the demo deploy's `/arena/` → `/arena/demo/`
// rebase (no `/arena/` substring) and works from the live bake, the demo, and dev.

export const FIELD_NOTES_BASE = 'https://ainative.business/field-notes/';

export function articleUrl(slug) {
  const s = String(slug || '')
    .replace(/^\/+|\/+$/g, '')
    .replace(/^articles\//, '');
  return `${FIELD_NOTES_BASE}${s}/`;
}
