#!/usr/bin/env node
// Link-integrity + leak + screenshot-drift verifier for the Arena demo deploy.
//
// Born from the 2026-06-07 sweep: the deployed demo at public/arena/demo/ had
// FOUR classes of 404 (TrainingFlow's `../sft/` escaping the base, the pruned
// articles/ tree, the lab page's /arena/demo/arena/* double prefix, and the
// missing public/products/ screenshot copies that shipped dark/404 images to
// the live product articles). Each class has an explicit regression guard here.
//
// Usage:
//   node scripts/verify_arena_demo_links.mjs              # checks public/arena/demo
//   node scripts/verify_arena_demo_links.mjs <other-root> # e.g. fieldkit/src/fieldkit/arena/_webui
//
// Exit code = number of failures (0 = clean).

import { promises as fs } from 'node:fs';
import { createHash } from 'node:crypto';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const REPO = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const rootArg = process.argv[2] || 'public/arena/demo';
const ROOT = path.isAbsolute(rootArg) ? rootArg : path.join(REPO, rootArg);
// The URL prefix the deployed tree is served under (demo: /arena/demo, webui: /arena).
const isDemoRoot = rootArg.replace(/\/+$/, '').endsWith('arena/demo');
const URL_PREFIX = isDemoRoot ? '/arena/demo' : '/arena';

let failures = 0;
const fail = (msg) => { failures++; console.error(`  FAIL ${msg}`); };
const ok = (msg) => console.log(`  ok   ${msg}`);

async function* walk(dir) {
  for (const ent of await fs.readdir(dir, { withFileTypes: true })) {
    const p = path.join(dir, ent.name);
    if (ent.isDirectory()) yield* walk(p);
    else yield p;
  }
}

async function exists(p) { try { await fs.access(p); return true; } catch { return false; } }

// Resolve a site-absolute or page-relative URL to an on-disk path under ROOT.
function diskPathFor(target, htmlFile) {
  const clean = target.split('#')[0].split('?')[0];
  if (!clean) return null;
  let abs;
  if (clean.startsWith('/')) {
    if (!clean.startsWith(`${URL_PREFIX}/`) && clean !== URL_PREFIX) return { outside: clean };
    abs = path.join(ROOT, clean.slice(URL_PREFIX.length));
  } else {
    abs = path.resolve(path.dirname(htmlFile), clean);
    if (!abs.startsWith(ROOT)) return { outside: clean };
  }
  return { abs };
}

async function checkHtmlLinks() {
  console.log(`== link integrity under ${path.relative(REPO, ROOT)} (served at ${URL_PREFIX}/)`);
  let checked = 0;
  const missing = new Map(); // target -> first referencing file
  for await (const file of walk(ROOT)) {
    if (!file.endsWith('.html')) continue;
    const html = await fs.readFile(file, 'utf8');
    const rel = path.relative(ROOT, file);

    // regression guards for the exact 404 classes fixed 2026-06-07
    if (html.includes(`${URL_PREFIX}/arena/`)) fail(`${rel}: doubled prefix ${URL_PREFIX}/arena/ (lab href bug)`);
    if (html.includes(`${URL_PREFIX}/articles/`)) fail(`${rel}: in-bundle article link ${URL_PREFIX}/articles/ — the bake prunes articles/ (use articleUrl())`);

    for (const m of html.matchAll(/(?:href|src)=["']([^"']+)["']/g)) {
      const target = m[1];
      if (/^(https?:|mailto:|javascript:|data:|#)/.test(target)) continue;
      const r = diskPathFor(target, file);
      if (!r) continue;
      if (r.outside) {
        // a RELATIVE link that escapes the bundle root 404s on the live site
        // (the TrainingFlow `../sft/` class); absolute non-prefix paths are
        // other site sections, validated by their own verifiers.
        if (!target.startsWith('/')) fail(`${rel}: relative link escapes the bundle → ${target}`);
        continue;
      }
      checked++;
      let p = r.abs;
      if ((await exists(p)) === false || (await fs.stat(p).then((s) => s.isDirectory()).catch(() => false))) {
        const idx = path.join(p, 'index.html');
        if (await exists(idx)) continue;
        if (await exists(p)) continue; // existing non-dir file
        if (!missing.has(target)) missing.set(target, rel);
      }
    }
  }
  for (const [target, rel] of missing) fail(`${rel}: broken link → ${target}`);
  if (!missing.size) ok(`${checked} internal links resolve`);
}

async function checkJsAssets() {
  // TrainingFlow's pane links are CLIENT-rendered (invisible to the HTML scan)
  // and the card mounts on the LANDING page, where a parent-relative '../sft/'
  // escapes the bundle (the 2026-06-07 404). Level-1 panes (BuildSpine, Jobs,
  // SFT) legitimately use '../' sibling links, so the guard keys on the
  // trainflow chunk specifically.
  console.log('== built JS asset guards');
  const assets = path.join(ROOT, 'assets');
  if (!(await exists(assets))) { ok('no assets/ under this root — skipped'); return; }
  let hits = 0;
  for await (const file of walk(assets)) {
    if (!file.endsWith('.js')) continue;
    const js = await fs.readFile(file, 'utf8');
    if (js.includes('trainflow') && /["']\.\.\/(sft|reward|jobs)\/["']/.test(js)) {
      fail(`${path.relative(ROOT, file)}: TrainingFlow uses parent-relative pane links — they escape the landing page base (use './sft/' etc.)`);
      hits++;
    }
  }
  if (!hits) ok('no base-escaping TrainingFlow links in built JS');
}

async function checkFixtureLeaks() {
  console.log('== fixture leak scan');
  const fixture = path.join(ROOT, 'arena-demo', 'fixtures.json');
  if (!(await exists(fixture))) { ok('no fixtures.json under this root — skipped'); return; }
  const text = await fs.readFile(fixture, 'utf8');
  const leakRe = /\/home\/|\/Users\/|\.hermes\/|:7866|:8080|config_mtime|config_path/g;
  const hits = text.match(leakRe);
  if (hits) fail(`fixtures.json leaks host details: ${[...new Set(hits)].join(', ')}`);
  else ok('fixtures.json clean (no host paths / sidecar ports / config metadata)');
}

async function checkScreenshotDrift() {
  // products/<slug>/screenshots/ is the AUTHORED source; the site serves
  // public/products/<slug>/screenshots/. Drift here is exactly how the
  // 2026-06-06 light re-capture shipped dark/404 images to the live site.
  console.log('== product screenshot drift (products/ vs public/products/)');
  const src = path.join(REPO, 'products');
  let drift = 0, checkedN = 0;
  for (const slug of await fs.readdir(src)) {
    const shotDir = path.join(src, slug, 'screenshots');
    if (!(await exists(shotDir))) continue;
    for (const f of await fs.readdir(shotDir)) {
      if (!/\.(png|jpg|webp)$/i.test(f)) continue;
      checkedN++;
      const pub = path.join(REPO, 'public', 'products', slug, 'screenshots', f);
      if (!(await exists(pub))) { fail(`public copy MISSING: products/${slug}/screenshots/${f}`); drift++; continue; }
      const [a, b] = await Promise.all([fs.readFile(shotDir + '/' + f), fs.readFile(pub)]);
      const h = (x) => createHash('md5').update(x).digest('hex');
      if (h(a) !== h(b)) { fail(`public copy STALE: products/${slug}/screenshots/${f}`); drift++; }
    }
  }
  if (!drift) ok(`${checkedN} product screenshots in sync`);
}

await checkHtmlLinks();
await checkJsAssets();
await checkFixtureLeaks();
if (isDemoRoot) await checkScreenshotDrift();
console.log(failures ? `\n${failures} failure(s)` : '\nall checks passed');
process.exit(failures);
