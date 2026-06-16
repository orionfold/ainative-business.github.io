// Remark plugin: rewrites `::asciinema{...}` leaf directives into an
// asciinema-player mount point with a poster/SVG fallback.
//
// Authoring syntax (in a product .md body):
//   ::asciinema{src="/products/orionfold-arena/casts/onboard.cast"
//     poster="screenshots/17-onboard-1-preflight.svg"
//     alt="The guided onboarding flow, replayed in the terminal"
//     cols=100 rows=18 idle=2 speed=1.4}
//
// Output (mdast `html` node → passed through by remark-rehype):
//   <figure class="asciinema-figure">
//     <div class="asciinema-cast" data-cast=… data-cols=… data-rows=… …>
//       <div class="asciinema-cast__player"></div>
//       <img class="asciinema-cast__poster" src=poster … />   ← shown until play
//     </div>
//   </figure>
//
// The companion island `src/components/products/AsciinemaCasts.astro` mounts a
// real player into every `.asciinema-cast` on scroll-into-view; the poster is
// the no-JS / pre-play fallback (so orionfold.com's clone degrades gracefully
// and the static SVG still carries the meaning). This runs BEFORE
// remark-explainers in the plugin chain so its directive-neutralizer never sees
// the `asciinema` leaf directive.

import { visit, SKIP } from 'unist-util-visit';

const esc = (s) =>
  String(s ?? '')
    .replace(/&/g, '&amp;')
    .replace(/"/g, '&quot;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');

export default function remarkAsciinema() {
  return (tree) => {
    visit(tree, (node, index, parent) => {
      if (!parent || index == null) return;
      if (node.type !== 'leafDirective' && node.type !== 'textDirective') return;
      if (node.name !== 'asciinema') return;

      const a = node.attributes || {};
      const src = a.src || '';
      if (!src) return; // no cast → leave it for the neutralizer to make plain
      const poster = a.poster || '';
      const alt = a.alt || 'Terminal session replay';
      const cols = a.cols || '100';
      const rows = a.rows || '18';
      const idle = a.idle || '2';
      const speed = a.speed || '1';
      const title = a.title || '';

      const posterImg = poster
        ? `<img class="asciinema-cast__poster" src="${esc(poster)}" alt="${esc(alt)}" loading="lazy" decoding="async" />`
        : '';
      const caption = title ? `<figcaption>${esc(title)}</figcaption>` : '';

      const html =
        `<figure class="asciinema-figure">` +
        `<div class="asciinema-cast" role="img" aria-label="${esc(alt)}"` +
        ` data-cast="${esc(src)}" data-cols="${esc(cols)}" data-rows="${esc(rows)}"` +
        ` data-idle="${esc(idle)}" data-speed="${esc(speed)}">` +
        `<div class="asciinema-cast__player"></div>` +
        posterImg +
        `</div>` +
        caption +
        `</figure>`;

      parent.children[index] = { type: 'html', value: html };
      return [SKIP, index];
    });
  };
}
