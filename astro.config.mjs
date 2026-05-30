import { defineConfig } from 'astro/config';
import mdx from '@astrojs/mdx';
import sitemap from '@astrojs/sitemap';
import tailwindcss from '@tailwindcss/vite';
import { readdirSync, existsSync, readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';
import remarkDirective from 'remark-directive';
import remarkExplainers from './src/lib/field-notes/remark-explainers.mjs';
import rehypeExplainerFigure from './src/lib/field-notes/rehype-explainer-figure.mjs';

import react from '@astrojs/react';

// Internal cross-links inside synced field-notes articles use the source
// ai-field-notes repo's `/articles/<slug>/` URL convention. This site serves
// those at `/field-notes/<slug>/`, so generate an explicit redirect for every
// article folder that has an article.{md,mdx}.
const articlesDir = join(dirname(fileURLToPath(import.meta.url)), 'articles');
const articleSlugRedirects = Object.fromEntries(
  readdirSync(articlesDir, { withFileTypes: true })
    .filter((d) => d.isDirectory())
    .filter((d) =>
      existsSync(join(articlesDir, d.name, 'article.md')) ||
      existsSync(join(articlesDir, d.name, 'article.mdx'))
    )
    .map((d) => [`/articles/${d.name}/`, `/field-notes/${d.name}/`]),
);

// Per-article <lastmod> for the sitemap, parsed from each article's frontmatter
// `date:`. A real, varied freshness signal (NOT a uniform build-date, which
// Google distrusts and ignores) helps the crawler prioritize the field-notes
// URLs that the 2026-05-29 consolidation left stuck in "Discovered – currently
// not indexed". Keyed by the canonical /field-notes/<slug>/ URL.
const articleLastmod = Object.fromEntries(
  readdirSync(articlesDir, { withFileTypes: true })
    .filter((d) => d.isDirectory())
    .map((d) => {
      const file = ['article.md', 'article.mdx']
        .map((f) => join(articlesDir, d.name, f))
        .find((p) => existsSync(p));
      if (!file) return null;
      const fm = readFileSync(file, 'utf8').match(/^---\r?\n([\s\S]*?)\r?\n---/);
      const m = fm && fm[1].match(/^date:\s*['"]?(\d{4}-\d{2}-\d{2})/m);
      if (!m) return null;
      const iso = new Date(`${m[1]}T00:00:00Z`).toISOString();
      return [`https://ainative.business/field-notes/${d.name}/`, iso];
    })
    .filter(Boolean),
);

export default defineConfig({
  site: 'https://ainative.business',
  trailingSlash: 'always',
  // /research/* now lives inside /field-notes/ as the AI Native Platform
  // series. Redirects preserve any existing inbound links since the old
  // research index was the only deep-linked surface the consolidation moved.
  redirects: {
    '/research/': '/field-notes/series/ai-native-platform/',
    '/research/ai-transformation/': '/field-notes/ai-transformation/',
    '/research/solo-builder-case-study/': '/field-notes/solo-builder-case-study/',
    '/rss.xml/': '/feed.xml/',
    // Autoresearch arc renamed and broadened to "Machine that Builds Machines"
    // on 2026-05-08 to ground the /book/ Part-4 thesis (Ch10–11).
    '/field-notes/series/autoresearch/': '/field-notes/series/machine-that-builds-machines/',
    ...articleSlugRedirects,
  },
  markdown: {
    remarkPlugins: [remarkDirective, remarkExplainers],
    rehypePlugins: [rehypeExplainerFigure],
    shikiConfig: {
      themes: {
        light: 'github-light',
        dark: 'github-dark',
      },
    },
  },
  integrations: [mdx(), sitemap({
    filter: (page) =>
      !page.includes('/confirmed') && !page.includes('/og') &&
      // Thin taxonomy pages are noindex; keep them out of the sitemap too so
      // Google doesn't surface them as "Discovered – currently not indexed".
      !page.includes('/field-notes/tags/') && !page.includes('/field-notes/stages/'),
    // Priority + changefreq hints. Search engines treat these as signals,
    // not directives — but they influence crawl scheduling, especially for
    // sites with frequently updated editorial sections like /field-notes/.
    serialize(item) {
      const url = item.url;
      // Attach a real per-article lastmod where we have one (field-notes).
      // Other sections omit lastmod rather than emit a faked uniform date.
      if (articleLastmod[url]) {
        item = { ...item, lastmod: articleLastmod[url] };
      }
      if (url === 'https://ainative.business/') {
        return { ...item, changefreq: 'weekly', priority: 1.0 };
      }
      if (url.includes('/field-notes/') || url.includes('/book/')) {
        return { ...item, changefreq: 'weekly', priority: 0.8 };
      }
      if (url.includes('/docs/')) {
        return { ...item, changefreq: 'weekly', priority: 0.7 };
      }
      if (url.includes('/about/') || url.includes('/projects/') || url.includes('/fieldkit/')) {
        return { ...item, changefreq: 'monthly', priority: 0.6 };
      }
      if (url.includes('/privacy/') || url.includes('/terms/')) {
        return { ...item, changefreq: 'yearly', priority: 0.3 };
      }
      return { ...item, changefreq: 'monthly', priority: 0.5 };
    },
  }), react()],
  vite: {
    plugins: [tailwindcss()],
  },
});