import { defineConfig } from 'astro/config';
import mdx from '@astrojs/mdx';
import sitemap from '@astrojs/sitemap';
import tailwindcss from '@tailwindcss/vite';

import react from '@astrojs/react';

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