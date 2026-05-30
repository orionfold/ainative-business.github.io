import { visit } from 'unist-util-visit';

// remark-fix-links — repair two link patterns that markdown alone cannot
// resolve correctly:
//
//   1. Site-rooted links like `/articles/foo/`. In production the site is
//      served under `/ai-field-notes/`, so these need the base prefix.
//      Astro auto-prefixes hrefs in .astro files but not in markdown.
//
//   2. Per-article relative links to `./evidence/<file>`. Files inside
//      `articles/<slug>/evidence/` are not part of any Astro route, so the
//      generated href 404s. Rewrite them to GitHub blob URLs so readers
//      land on the source-of-truth file with syntax highlighting.
//
// Pass `base` (e.g. `/ai-field-notes` or `/`) and `repoBase` (e.g.
// `https://github.com/manavsehgal/ai-field-notes/blob/main`) from
// astro.config.mjs.

export default function remarkFixLinks({ base = '/', repoBase } = {}) {
  const basePrefix = base.replace(/\/+$/, '');

  return (tree, file) => {
    const articlePath = file?.path || (file?.history?.[file.history.length - 1]) || '';
    const slugMatch = articlePath.match(/articles\/([^/]+)\/article\.md$/);
    const slug = slugMatch?.[1];

    visit(tree, 'link', (node) => {
      const url = node.url;
      if (!url) return;

      if (basePrefix && url.startsWith('/articles/') && !url.startsWith(`${basePrefix}/`)) {
        node.url = basePrefix + url;
        return;
      }

      if (slug && repoBase && url.startsWith('./evidence/')) {
        node.url = `${repoBase}/articles/${slug}/${url.slice(2)}`;
      }
    });
  };
}
