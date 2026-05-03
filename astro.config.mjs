import { defineConfig } from 'astro/config';
import mdx from '@astrojs/mdx';
import sitemap from '@astrojs/sitemap';
import tailwindcss from '@tailwindcss/vite';
import { readdirSync, existsSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

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
    ...articleSlugRedirects,
  },
  markdown: {
    shikiConfig: {
      themes: {
        light: 'github-light',
        dark: 'github-dark',
      },
    },
  },
  integrations: [mdx(), sitemap({
    filter: (page) =>
      !page.includes('/confirmed') && !page.includes('/og'),
  }), react()],
  vite: {
    plugins: [tailwindcss()],
  },
});