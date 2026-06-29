import { defineConfig } from 'astro/config';
import mdx from '@astrojs/mdx';
import sitemap from '@astrojs/sitemap';
import tailwindcss from '@tailwindcss/vite';
import { readdirSync, existsSync, readFileSync } from 'node:fs';
import { execFileSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';
import remarkDirective from 'remark-directive';
import remarkAsciinema from './src/lib/products/remark-asciinema.mjs';
import remarkExplainers from './src/lib/field-notes/remark-explainers.mjs';
import rehypeExplainerFigure from './src/lib/field-notes/rehype-explainer-figure.mjs';

import react from '@astrojs/react';

// Internal cross-links inside synced field-notes articles use the source
// ai-field-notes repo's `/articles/<slug>/` URL convention. This site serves
// those at `/field-notes/<slug>/`, so generate an explicit redirect for every
// article folder that has an article.{md,mdx}.
const root = dirname(fileURLToPath(import.meta.url));
const articlesDir = join(root, 'articles');
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

// Helper: parse a `key: value` from a frontmatter block (first match only).
const fmDate = (text, key) => {
  const fm = text.match(/^---\r?\n([\s\S]*?)\r?\n---/);
  return fm && fm[1].match(new RegExp(`^${key}:\\s*['"]?(\\d{4}-\\d{2}-\\d{2})`, 'm'));
};

// Product launch pages — real <lastmod> from each product.md's frontmatter
// `date:`. Keyed by the canonical /products/<slug>/ URL.
const productsDir = join(root, 'products');
const productLastmod = Object.fromEntries(
  (existsSync(productsDir) ? readdirSync(productsDir, { withFileTypes: true }) : [])
    .filter((d) => d.isDirectory())
    .map((d) => {
      const file = join(productsDir, d.name, 'product.md');
      if (!existsSync(file)) return null;
      const m = fmDate(readFileSync(file, 'utf8'), 'date');
      if (!m) return null;
      return [`https://ainative.business/products/${d.name}/`,
        new Date(`${m[1]}T00:00:00Z`).toISOString()];
    })
    .filter(Boolean),
);

// Artifact detail pages — real <lastmod> from each manifest's `published_at:`.
// The route segment differs from the `kind:` value for a few kinds, so map it.
const ARTIFACT_KIND_SEGMENT = {
  quant: 'quants', lora: 'loras', adapter: 'adapters', dataset: 'datasets',
  notebook: 'notebooks', bench: 'benches', skill: 'skills', harness: 'harnesses',
  arena_run: 'apps',
};
const artifactsDir = join(root, 'src/content/artifacts');
const artifactLastmod = Object.fromEntries(
  (existsSync(artifactsDir) ? readdirSync(artifactsDir) : [])
    .filter((f) => f.endsWith('.yaml'))
    .map((f) => {
      const txt = readFileSync(join(artifactsDir, f), 'utf8');
      const slug = txt.match(/^slug:\s*['"]?([\w.-]+)/m);
      const kind = txt.match(/^kind:\s*['"]?(\w+)/m);
      const pub = txt.match(/^published_at:\s*['"]?([0-9T:.\-]+Z?)/m);
      const seg = kind && ARTIFACT_KIND_SEGMENT[kind[1]];
      if (!slug || !seg || !pub) return null;
      return [`https://ainative.business/artifacts/${seg}/${slug[1]}/`,
        new Date(pub[1]).toISOString()];
    })
    .filter(Boolean),
);

// Docs pages (.mdx) carry no frontmatter date, so derive a real, varied
// <lastmod> from each file's last-commit date. Needs full git history — the
// deploy workflow checks out with fetch-depth: 0 for exactly this. Falls back
// to omitting lastmod (never a faked uniform date) if git is unavailable.
const gitLastmod = (absPath) => {
  try {
    const iso = execFileSync('git', ['log', '-1', '--format=%cI', '--', absPath],
      { cwd: root, encoding: 'utf8', stdio: ['ignore', 'pipe', 'ignore'] }).trim();
    return iso ? new Date(iso).toISOString() : null;
  } catch {
    return null;
  }
};
const walkMdx = (dir, base = '') =>
  readdirSync(dir, { withFileTypes: true }).flatMap((e) =>
    e.isDirectory()
      ? walkMdx(join(dir, e.name), `${base}${e.name}/`)
      : e.name.endsWith('.mdx')
        ? [{ abs: join(dir, e.name), rel: `${base}${e.name.replace(/\.mdx$/, '')}` }]
        : []);
const docsDir = join(root, 'src/pages/docs');
const docsLastmod = Object.fromEntries(
  (existsSync(docsDir) ? walkMdx(docsDir) : [])
    .map(({ abs, rel }) => {
      const iso = gitLastmod(abs);
      if (!iso) return null;
      const path = rel.endsWith('/index') ? rel.slice(0, -'/index'.length) : rel;
      return [`https://ainative.business/docs/${path}/`, iso];
    })
    .filter(Boolean),
);

// Single URL→lastmod lookup the sitemap serialize hook reads from.
const lastmodByUrl = {
  ...articleLastmod, ...productLastmod, ...artifactLastmod, ...docsLastmod,
};

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
    remarkPlugins: [remarkDirective, remarkAsciinema, remarkExplainers],
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
      // Attach a real per-page lastmod where we have one (field-notes,
      // products, artifacts, docs). Sections without a real date source omit
      // lastmod rather than emit a faked uniform date Google would distrust.
      if (lastmodByUrl[url]) {
        item = { ...item, lastmod: lastmodByUrl[url] };
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