#!/usr/bin/env node
// audit_site.mjs — walks dist/ and runs the 14 SEO checks from fix-taxonomy.md.
//
// Usage:
//   node .claude/skills/seo-monitor/scripts/audit_site.mjs [--dist <path>] [--src <path>] [--config <path>]
//
// Defaults: --dist ./dist, --src ./src, --config ./astro.config.mjs
// Output: JSON to stdout: { checks: [{ id, page, file, severity, class, fix, evidence }, ...], summary: {...} }
//
// Pure data transform. No external deps. Regex-based head parsing — Astro's
// emitted HTML is predictable, so we don't need a full DOM parser here.

import { readdirSync, readFileSync, existsSync } from 'node:fs';
import { join, relative, resolve, sep } from 'node:path';
import { argv, exit, stdout } from 'node:process';

// --- args ---
const args = Object.fromEntries(
  argv.slice(2).reduce((acc, v, i, a) => {
    if (v.startsWith('--')) acc.push([v.slice(2), a[i + 1]]);
    return acc;
  }, [])
);
const DIST = resolve(args.dist || 'dist');
const SRC = resolve(args.src || 'src');
const CONFIG = resolve(args.config || 'astro.config.mjs');
const SITEMAP = join(DIST, 'sitemap-0.xml');

// --- helpers ---
function walk(dir, ext) {
  const out = [];
  if (!existsSync(dir)) return out;
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    const p = join(dir, entry.name);
    if (entry.isDirectory()) out.push(...walk(p, ext));
    else if (!ext || entry.name.endsWith(ext)) out.push(p);
  }
  return out;
}

function distPathToRoute(distPath) {
  const rel = relative(DIST, distPath).split(sep).join('/');
  if (rel === 'index.html') return '/';
  if (rel.endsWith('/index.html')) return '/' + rel.slice(0, -'index.html'.length);
  return '/' + rel.replace(/\.html$/, '/');
}

// Attempt to map a dist path back to a likely source file. Best-effort —
// returns null if no obvious match. The skill's Execute Phase resolves
// ambiguity by reading the file.
function routeToSourceFile(route) {
  const base = route.replace(/^\//, '').replace(/\/$/, '');
  const candidates = [];
  if (base === '') {
    candidates.push('pages/index.astro', 'pages/index.mdx', 'pages/index.md');
  } else {
    candidates.push(
      `pages/${base}.astro`,
      `pages/${base}.mdx`,
      `pages/${base}.md`,
      `pages/${base}/index.astro`,
      `pages/${base}/index.mdx`,
      `pages/${base}/index.md`,
    );
    // Field-notes articles may live in a content collection or articles/
    if (base.startsWith('field-notes/')) {
      const slug = base.slice('field-notes/'.length);
      candidates.push(
        `content/field-notes/${slug}.md`,
        `content/field-notes/${slug}.mdx`,
      );
    }
  }
  for (const c of candidates) {
    const p = join(SRC, c);
    if (existsSync(p)) return relative(resolve('.'), p);
  }
  // articles/<slug>/article.{md,mdx} — outside src/
  if (base.startsWith('field-notes/')) {
    const slug = base.slice('field-notes/'.length);
    for (const ext of ['md', 'mdx']) {
      const p = resolve('.', 'articles', slug, `article.${ext}`);
      if (existsSync(p)) return relative(resolve('.'), p);
    }
  }
  return null;
}

// --- head extraction ---
function extractHead(html) {
  const headMatch = html.match(/<head[^>]*>([\s\S]*?)<\/head>/i);
  const head = headMatch ? headMatch[1] : '';
  const titles = [...head.matchAll(/<title[^>]*>([\s\S]*?)<\/title>/gi)].map((m) => m[1].trim());
  const meta = [...head.matchAll(/<meta\s+([^>]*?)\/?>/gi)].map((m) => {
    const attrs = {};
    for (const a of m[1].matchAll(/(\w[\w:-]*)\s*=\s*"([^"]*)"/g)) attrs[a[1].toLowerCase()] = a[2];
    return attrs;
  });
  const link = [...head.matchAll(/<link\s+([^>]*?)\/?>/gi)].map((m) => {
    const attrs = {};
    for (const a of m[1].matchAll(/(\w[\w:-]*)\s*=\s*"([^"]*)"/g)) attrs[a[1].toLowerCase()] = a[2];
    return attrs;
  });
  const jsonLd = [...head.matchAll(/<script\s+type="application\/ld\+json"[^>]*>([\s\S]*?)<\/script>/gi)].map((m) => m[1].trim());
  return { titles, meta, link, jsonLd };
}

function metaContent(meta, name) {
  const m = meta.find((x) => (x.name && x.name.toLowerCase() === name) || (x.property && x.property.toLowerCase() === name));
  return m?.content;
}

// --- sitemap parsing ---
function parseSitemap() {
  if (!existsSync(SITEMAP)) return null;
  const xml = readFileSync(SITEMAP, 'utf8');
  const entries = [];
  for (const m of xml.matchAll(/<url>([\s\S]*?)<\/url>/g)) {
    const loc = m[1].match(/<loc>([^<]+)<\/loc>/)?.[1];
    const priority = parseFloat(m[1].match(/<priority>([^<]+)<\/priority>/)?.[1] || 'NaN');
    const changefreq = m[1].match(/<changefreq>([^<]+)<\/changefreq>/)?.[1];
    if (loc) entries.push({ loc, priority, changefreq });
  }
  return entries;
}

// Mirror of the serialize() rules in astro.config.mjs:55-80.
// If those rules change, this function should be updated in lockstep —
// a divergence between this and the emitted sitemap is the actual signal
// we want to surface.
function expectedPriorityRule(url) {
  if (url === 'https://ainative.business/') return { priority: 1.0, changefreq: 'weekly' };
  if (url.includes('/field-notes/') || url.includes('/book/')) return { priority: 0.8, changefreq: 'weekly' };
  if (url.includes('/docs/')) return { priority: 0.7, changefreq: 'weekly' };
  if (url.includes('/about/') || url.includes('/projects/') || url.includes('/fieldkit/')) return { priority: 0.6, changefreq: 'monthly' };
  if (url.includes('/privacy/') || url.includes('/terms/')) return { priority: 0.3, changefreq: 'yearly' };
  return { priority: 0.5, changefreq: 'monthly' };
}

// --- redirect chain detection ---
function parseRedirectsFromConfig() {
  if (!existsSync(CONFIG)) return {};
  const src = readFileSync(CONFIG, 'utf8');
  // Match the `redirects: { ... }` object literal — keys and values only.
  // We deliberately don't try to evaluate the JS; we just grab key:value pairs
  // matching '/path/': '/other-path/'.
  const block = src.match(/redirects:\s*\{([\s\S]*?)\}\s*,/);
  if (!block) return {};
  const entries = {};
  for (const m of block[1].matchAll(/'([^']+)'\s*:\s*'([^']+)'/g)) {
    entries[m[1]] = m[2];
  }
  return entries;
}

// --- trailing slash audit (src files only) ---
function auditTrailingSlashes() {
  const issues = [];
  const exts = ['.astro', '.tsx', '.ts', '.mdx'];
  const candidates = walk(SRC).filter((f) => exts.some((e) => f.endsWith(e)));
  for (const f of candidates) {
    const text = readFileSync(f, 'utf8');
    const lines = text.split('\n');
    lines.forEach((line, i) => {
      // Match href="/path" without trailing slash, skipping anchors, externals,
      // and obvious non-route paths (assets, JS templating).
      // (?<!\.) excludes JS property assignments like `link.href = '/api/foo'`
      // inside MDX code blocks — those aren't HTML attributes.
      for (const m of line.matchAll(/(?<!\.)href\s*=\s*["'`](\/(?!\/)[^"'`#?]*?)["'`]/g)) {
        const href = m[1];
        if (href === '/') continue;
        if (href.endsWith('/')) continue;
        // Skip asset paths
        if (/\.(png|jpg|jpeg|gif|svg|webp|avif|ico|css|js|mjs|xml|txt|pdf|json|webmanifest|woff2|woff|ttf|otf|eot)$/i.test(href)) continue;
        // Skip dynamic template syntax (Astro/JS interpolation visible in the captured value)
        if (href.includes('${') || href.includes('{{')) continue;
        issues.push({
          id: 'internal-href-missing-trailing-slash',
          page: null,
          file: `${relative(resolve('.'), f)}:${i + 1}`,
          severity: 'warn',
          class: 'auto',
          fix: `Append '/' to href "${href}" so it becomes "${href}/" (per trailingSlash:'always' contract)`,
          evidence: line.trim().slice(0, 200),
        });
      }
    });
  }
  return issues;
}

// --- per-page audit ---
function auditPage(distPath) {
  const html = readFileSync(distPath, 'utf8');
  const route = distPathToRoute(distPath);
  const src = routeToSourceFile(route);
  const { titles, meta, link, jsonLd } = extractHead(html);
  const issues = [];
  const push = (id, severity, klass, fix, evidence) => {
    issues.push({ id, page: route, file: src, severity, class: klass, fix, evidence });
  };

  // 1. missing meta description
  const desc = metaContent(meta, 'description');
  if (!desc) {
    push('missing-meta-description', 'warn', 'console',
      'Author a 70–160 char meta description in front-matter. Skill never auto-derives.',
      'no <meta name="description"> in <head>');
  } else {
    // 2. description-length-out-of-range
    const len = desc.length;
    if (len < 70 || len > 160) {
      push('description-length-out-of-range', 'info', 'console',
        `Description length ${len} outside 70–160 char window. Rewrite.`,
        `length=${len}`);
    }
  }

  // 3. missing title
  const title = titles[0];
  if (!title) {
    push('missing-title', 'error', 'console',
      'Add a <title> via front-matter title field.',
      'no <title> in <head>');
  } else {
    // 4. title length
    const len = title.length;
    if (len < 25 || len > 65) {
      push('title-length-out-of-range', 'info', 'console',
        `Title length ${len} outside 25–65 char window. Rewrite.`,
        `length=${len} title=${JSON.stringify(title)}`);
    }
  }

  // 5. missing canonical
  const canonical = link.find((l) => l.rel === 'canonical');
  if (!canonical) {
    push('missing-canonical', 'warn', 'console',
      'Page bypasses Layout.astro canonical emission. Inspect.',
      'no <link rel="canonical">');
  } else {
    // 6. canonical mismatch (canonical href != expected URL)
    const expected = `https://ainative.business${route}`;
    if (canonical.href !== expected) {
      push('canonical-mismatch', 'warn', 'console',
        `Canonical "${canonical.href}" disagrees with expected "${expected}".`,
        `href=${canonical.href}`);
    }
  }

  // 7. noindex on indexable page
  const robots = metaContent(meta, 'robots');
  if (robots && /noindex/i.test(robots)) {
    push('noindex-on-indexable-page', 'warn', 'console',
      'Page has noindex but may be in sitemap. Verify intent.',
      `robots=${robots}`);
  }

  // 8. missing og:image
  const ogImg = metaContent(meta, 'og:image');
  if (!ogImg) {
    // Try to auto-suggest from public/og/<slug>.png
    const slug = route.replace(/^\//, '').replace(/\/$/, '').split('/').pop();
    const candidate = `public/og/${slug}.png`;
    const canAuto = slug && existsSync(resolve('.', candidate));
    push('missing-og-image', 'info', canAuto ? 'auto' : 'console',
      canAuto
        ? `Set ogImage: /og/${slug}.png (asset exists in public/og/)`
        : 'No matching /og/<slug>.png asset; surface for manual selection.',
      'no <meta property="og:image">');
  }

  // 9. json-ld parse error + 10. article jsonld missing
  let hasArticleSchema = false;
  for (let i = 0; i < jsonLd.length; i++) {
    try {
      const parsed = JSON.parse(jsonLd[i]);
      const types = [];
      const walk = (n) => {
        if (!n) return;
        if (Array.isArray(n)) return n.forEach(walk);
        if (typeof n === 'object') {
          if (n['@type']) types.push(...(Array.isArray(n['@type']) ? n['@type'] : [n['@type']]));
          for (const v of Object.values(n)) walk(v);
        }
      };
      walk(parsed);
      if (types.some((t) => /Article/i.test(t))) hasArticleSchema = true;
    } catch (e) {
      push('json-ld-parse-error', 'error', 'console',
        'JSON-LD block fails JSON.parse. Likely a templating bug.',
        `block ${i + 1}: ${e.message}`);
    }
  }
  if (/^\/field-notes\/[^/]+\/$/.test(route) && !hasArticleSchema) {
    push('article-jsonld-missing', 'warn', 'auto',
      'Field-notes article page missing Article/TechArticle JSON-LD. Patch type guard in field-notes layout.',
      'no Article schema in JSON-LD blocks');
  }

  // 14. person-jsonld stale — light check: if Person schema is emitted but
  // doesn't include the seo.ts canonical fields, surface for review. We don't
  // statically evaluate seo.ts here; we only flag pages that hardcode Person
  // fields outside the Layout.
  // (Heavy version deferred; check #14 is conservatively skipped until needed.)

  return issues;
}

// Resolve which dist HTML files correspond to indexable, sitemap-listed
// routes. Astro emits both `foo.html` and `foo/index.html` for
// trailingSlash:'always', and additionally emits HTML for noindex routes
// (`/og/*`, `/confirmed/*`). We audit only the trailing-slash form for
// pages actually present in the sitemap — that's the canonical surface.
function selectAuditablePages(sitemap) {
  const out = [];
  if (sitemap) {
    for (const entry of sitemap) {
      const route = entry.loc.replace('https://ainative.business', '');
      // Sitemap routes end in '/' per trailingSlash:'always'. Map to dist file.
      const candidate = route === '/'
        ? join(DIST, 'index.html')
        : join(DIST, route.replace(/^\//, '').replace(/\/$/, ''), 'index.html');
      if (existsSync(candidate)) out.push(candidate);
    }
    return out;
  }
  // Fallback: no sitemap — pick *only* the trailing-slash form, skip excluded paths.
  const all = walk(DIST, '.html');
  for (const p of all) {
    const route = distPathToRoute(p);
    if (route === '/') { out.push(p); continue; }
    // Skip the non-trailing-slash form (dist/foo.html). Keep dist/foo/index.html.
    if (!p.endsWith(`${sep}index.html`)) continue;
    // Skip noindex-by-design routes (mirror astro.config.mjs:57 filter).
    if (route.includes('/og/') || route.includes('/confirmed/')) continue;
    out.push(p);
  }
  return out;
}

// --- main ---
function main() {
  const checks = [];
  // Sitemap is the authoritative list of indexable routes. Parse first.
  const sitemap = parseSitemap();
  const pages = selectAuditablePages(sitemap);
  for (const p of pages) {
    try {
      checks.push(...auditPage(p));
    } catch (e) {
      checks.push({
        id: 'audit-error',
        page: distPathToRoute(p),
        file: null,
        severity: 'error',
        class: 'console',
        fix: `audit_site.mjs crashed on this page: ${e.message}`,
        evidence: e.stack?.slice(0, 200),
      });
    }
  }

  // 11. redirect chain depth > 1
  const redirects = parseRedirectsFromConfig();
  for (const [from, to] of Object.entries(redirects)) {
    if (redirects[to]) {
      checks.push({
        id: 'redirect-chain-depth-gt-1',
        page: from,
        file: 'astro.config.mjs',
        severity: 'warn',
        class: 'auto',
        fix: `Flatten chain: ${from} → ${to} → ${redirects[to]}. Point ${from} directly to ${redirects[to]}.`,
        evidence: `${from} -> ${to} -> ${redirects[to]}`,
      });
    }
  }

  // 12. sitemap priority drift (uses sitemap already parsed above)
  if (sitemap) {
    for (const entry of sitemap) {
      const expected = expectedPriorityRule(entry.loc);
      if (Number.isFinite(entry.priority) && Math.abs(entry.priority - expected.priority) > 0.01) {
        checks.push({
          id: 'sitemap-priority-drift',
          page: entry.loc.replace('https://ainative.business', ''),
          file: 'astro.config.mjs:55-80',
          severity: 'info',
          class: 'auto',
          fix: `Sitemap emits priority ${entry.priority} for ${entry.loc}; rule expects ${expected.priority}. Reconcile serialize() rule.`,
          evidence: `emitted=${entry.priority} expected=${expected.priority}`,
        });
      }
    }
  }

  // 13. trailing slashes (src scan)
  checks.push(...auditTrailingSlashes());

  // --- summary ---
  const byId = {};
  for (const c of checks) byId[c.id] = (byId[c.id] || 0) + 1;
  const summary = {
    totalIssues: checks.length,
    byCheck: byId,
    pagesAudited: pages.length,
    sitemapEntries: sitemap?.length ?? null,
    redirectsAudited: Object.keys(redirects).length,
    distRoot: DIST,
    srcRoot: SRC,
  };

  stdout.write(JSON.stringify({ checks, summary }, null, 2));
}

try {
  main();
} catch (e) {
  console.error('audit_site.mjs failed:', e.message);
  console.error(e.stack);
  exit(1);
}
