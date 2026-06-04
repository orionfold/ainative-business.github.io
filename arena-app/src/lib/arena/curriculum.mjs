// curriculum.mjs — load the Arena operator curriculum (rl-lane-autonomy LA-12)
// for baking into the cockpit islands as a prop.
//
// The `explainers` content collection (src/content/explainers.yaml — single
// canonical source, shared with the main site) is build-time data; the Jobs +
// Standup Preact islands are client:only and can't call getCollection. So the
// .astro page reads it here and passes the flat, JSON-serializable map below as
// a prop. Keys are teach_keys (phase-*/interp-*/concept-*/gate-*).
//
// `source` is the absolute deep-dive backlink — absolute (not root-relative)
// because the cockpit is served by the sidecar (localhost), not ainative.business.
// The anchor replicates remark-explainers.mjs slugify() byte-for-byte so the
// `#explain-<kind>-<slug>` fragment lands on the rendered `:::` block.

import { getCollection } from 'astro:content';

const SITE = 'https://ainative.business';

const slugify = (s) =>
  String(s ?? '')
    .toLowerCase()
    .normalize('NFKD')
    .replace(/[̀-ͯ]/g, '')
    .replace(/[^\w\s-]/g, '')
    .trim()
    .replace(/\s+/g, '-')
    .replace(/-+/g, '-');

export async function loadCurriculum() {
  const entries = await getCollection('explainers');
  const map = {};
  for (const e of entries) {
    const d = e.data;
    let source = null;
    if (d.source_article && d.source_term && d.source_kind) {
      const anchor = `explain-${d.source_kind}-${slugify(d.source_term)}`;
      source = { url: `${SITE}/field-notes/${d.source_article}/#${anchor}` };
    }
    map[d.id] = {
      term: d.term,
      kind: d.kind,
      what: d.what,
      why: d.why ?? null,
      watch: d.watch ?? null,
      source,
    };
  }
  return map;
}
