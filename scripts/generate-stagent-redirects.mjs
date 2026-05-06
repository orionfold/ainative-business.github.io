#!/usr/bin/env node
/**
 * Generate per-path redirect HTML files for the stagent-io-redirect repo so
 * each old stagent.io URL returns HTTP 200 with a path-specific canonical
 * pointing to its ainative.business equivalent.
 *
 * Why this exists:
 *
 * Google Search Console's site-move tool samples representative URLs on the
 * old domain and verifies that each one redirects to the corresponding URL
 * on the new domain. GitHub Pages can't emit HTTP 301s — every path either
 * resolves to a real file (HTTP 200) or falls through to 404.html (HTTP 404
 * with the same redirect HTML). When the redirect repo only has a single
 * apex `index.html`, every sub-path returns 404 and Search Console reports:
 *   - "Couldn't fetch the page" for the sample sub-paths
 *   - "Duplicate redirect targets" for the apex (since the only canonical
 *     it can read is the apex's, pointing to the new-site root)
 *
 * Generating per-path index.html files for every URL that existed on
 * stagent.io produces HTTP 200 responses with path-specific canonicals.
 * That fixes the two warnings while still meta-refresh+JS-replacing to the
 * destination URL for human visitors.
 *
 * Long-term, the proper fix is HTTP 301 via a host that can return real
 * redirect headers (Cloudflare Bulk Redirects, Vercel, Netlify). Until then,
 * this is the cleanest signal we can give static-hosting visitors and
 * Googlebot's site-move check.
 *
 * Source for paths:
 *   - dist/sitemap-0.xml on this site, filtered to paths that existed on
 *     stagent.io before the 2026-05-02 /field-notes/ + /fieldkit/ additions
 *   - The 3 historical /research/ → /field-notes/ destination mappings that
 *     match the redirects in astro.config.mjs
 *
 * Run:
 *   node scripts/generate-stagent-redirects.mjs <path-to-stagent-io-redirect>
 */
import { readFileSync, writeFileSync, mkdirSync, existsSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = dirname(__dirname);
const SITEMAP = join(REPO_ROOT, 'dist', 'sitemap-0.xml');
const TARGET_REPO = process.argv[2];

if (!TARGET_REPO) {
  console.error('Usage: node scripts/generate-stagent-redirects.mjs <path-to-stagent-io-redirect>');
  process.exit(1);
}
if (!existsSync(TARGET_REPO)) {
  console.error(`Target repo not found: ${TARGET_REPO}`);
  process.exit(1);
}

// Paths added AFTER stagent.io was retired (2026-04-18). Skip these — generating
// redirect shims for URLs Googlebot never indexed on stagent.io would just create
// new "Page with redirect" surface for nothing.
const POST_REBRAND_PREFIXES = ['/field-notes/', '/fieldkit/'];

// Historical /research/ → /field-notes/ mappings. Matches the redirects in
// astro.config.mjs so the destination on stagent.io matches the destination
// on ainative.business.
const RESEARCH_MAPPINGS = {
  '/research/': '/field-notes/series/ai-native-platform/',
  '/research/ai-transformation/': '/field-notes/ai-transformation/',
  '/research/solo-builder-case-study/': '/field-notes/solo-builder-case-study/',
};

const xml = readFileSync(SITEMAP, 'utf8');
const urlMatches = [...xml.matchAll(/<loc>([^<]+)<\/loc>/g)];
const allPaths = urlMatches.map((m) => new URL(m[1]).pathname);

// stagent.io existed at every path that's still on ainative.business EXCEPT
// the post-rebrand additions.
const stagentEraPaths = allPaths.filter(
  (p) => !POST_REBRAND_PREFIXES.some((prefix) => p.startsWith(prefix)),
);

// Compose the final mapping: stagent.io <path> → ainative.business <destination>
const redirects = new Map();
for (const p of stagentEraPaths) {
  redirects.set(p, p); // path-preserving for everything that survived
}
for (const [src, dst] of Object.entries(RESEARCH_MAPPINGS)) {
  redirects.set(src, dst);
}

function renderRedirectHtml(srcPath, destPath) {
  const destUrl = `https://ainative.business${destPath}`;
  const escapedTitle = srcPath.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  return `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Redirecting ${escapedTitle} to ainative.business</title>
<meta name="robots" content="noindex">
<meta http-equiv="refresh" content="0; url=${destUrl}">
<link rel="canonical" href="${destUrl}">
<script>location.replace(${JSON.stringify(destUrl)});</script>
</head>
<body>
<p>This page has moved to <a href="${destUrl}">${destUrl}</a>.</p>
</body>
</html>
`;
}

let written = 0;
let unchanged = 0;
for (const [srcPath, destPath] of redirects) {
  // GitHub Pages serves /foo/ from /foo/index.html. Map "/" → "index.html".
  const fileRel = srcPath === '/' ? 'index.html' : srcPath.replace(/^\//, '').replace(/\/$/, '/index.html');
  const filePath = join(TARGET_REPO, fileRel);
  const html = renderRedirectHtml(srcPath, destPath);
  mkdirSync(dirname(filePath), { recursive: true });
  if (existsSync(filePath) && readFileSync(filePath, 'utf8') === html) {
    unchanged++;
    continue;
  }
  writeFileSync(filePath, html, 'utf8');
  written++;
}

// Update the catch-all 404.html to use the same JS path-preservation but with
// a clearer comment explaining the HTTP 404 limitation. Even with all sample
// paths handled by per-path files, 404.html still fires for any URL we didn't
// pre-generate (e.g. an unindexed stagent.io tag page someone bookmarked).
const fallback404 = `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Redirecting to ainative.business</title>
<meta name="robots" content="noindex">
<meta http-equiv="refresh" content="0; url=https://ainative.business/">
<link rel="canonical" href="https://ainative.business/">
<script>
  location.replace('https://ainative.business' + location.pathname + location.search + location.hash);
</script>
</head>
<body>
<p>This site has moved to <a href="https://ainative.business/">ainative.business</a>.
For the destination of a specific path, visit
<a id="dest" href="https://ainative.business/">ainative.business</a>.
</p>
<script>
  document.getElementById('dest').href = 'https://ainative.business' + location.pathname;
  document.getElementById('dest').textContent = 'ainative.business' + location.pathname;
</script>
</body>
</html>
`;
const fb404Path = join(TARGET_REPO, '404.html');
if (!existsSync(fb404Path) || readFileSync(fb404Path, 'utf8') !== fallback404) {
  writeFileSync(fb404Path, fallback404, 'utf8');
  console.log('  updated 404.html');
}

console.log(`\nGenerated ${written} redirect file(s), ${unchanged} unchanged.`);
console.log(`Target: ${TARGET_REPO}`);
