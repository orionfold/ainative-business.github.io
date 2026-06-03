#!/usr/bin/env node
// Deploy the sidecar-less Arena demo bundle to the public site.
//
// The ARENA_DEMO=1 build (arena-app, base '/arena') emits the whole site to
// arena-app/dist-arena-demo/, with the cockpit under `arena/` and a fetch-shim
// in `arena-demo/` (boot.js + fixtures.json). The public web preview serves the
// cockpit at `/arena/demo/`, so this script:
//   1. flattens the `arena/` subtree to the demo root (arena/chat → demo/chat),
//   2. brings along `assets/` (built JS/CSS) + `arena-demo/` (shim) + favicon,
//   3. rewrites every absolute `/arena/` path → `/arena/demo/` in html/js/css
//      (NOT in *.json — fixtures.json is data and must stay verbatim).
//
// This is the previously-manual step, now scripted + reproducible. Run after
// `ARENA_DEMO=1 node arena-app/node_modules/astro/astro.js build --root arena-app`.
// Usage: node scripts/deploy_arena_demo.mjs

import { promises as fs } from 'node:fs';
import path from 'node:path';

const REPO = path.resolve(path.dirname(new URL(import.meta.url).pathname), '..');
const SRC = path.join(REPO, 'arena-app', 'dist-arena-demo');
const DEST = path.join(REPO, 'public', 'arena', 'demo');

async function exists(p) { try { await fs.access(p); return true; } catch { return false; } }

async function copyDir(from, to) {
  await fs.mkdir(to, { recursive: true });
  for (const ent of await fs.readdir(from, { withFileTypes: true })) {
    const s = path.join(from, ent.name), d = path.join(to, ent.name);
    if (ent.isDirectory()) await copyDir(s, d);
    else await fs.copyFile(s, d);
  }
}

async function* walk(dir) {
  for (const ent of await fs.readdir(dir, { withFileTypes: true })) {
    const p = path.join(dir, ent.name);
    if (ent.isDirectory()) yield* walk(p);
    else yield p;
  }
}

async function main() {
  if (!(await exists(path.join(SRC, 'arena', 'index.html')))) {
    console.error(`[deploy-arena-demo] missing ${SRC}/arena/index.html — run the ARENA_DEMO=1 build first.`);
    process.exit(1);
  }

  // 1. clean the deploy target
  await fs.rm(DEST, { recursive: true, force: true });
  await fs.mkdir(DEST, { recursive: true });

  // 2. flatten the cockpit subtree + bring along assets, the shim, favicon
  await copyDir(path.join(SRC, 'arena'), DEST);                       // arena/* → demo/*
  await copyDir(path.join(SRC, 'assets'), path.join(DEST, 'assets')); // built JS/CSS
  await copyDir(path.join(SRC, 'arena-demo'), path.join(DEST, 'arena-demo')); // boot.js + fixtures
  for (const f of ['favicon.svg', 'favicon.ico']) {
    if (await exists(path.join(SRC, f))) await fs.copyFile(path.join(SRC, f), path.join(DEST, f));
  }
  // GitHub Pages: keep Jekyll from touching the bundle (defensive — the demo
  // serves from assets/, but the tracked .nojekyll must survive the clean).
  await fs.writeFile(path.join(DEST, '.nojekyll'), '');

  // 3. rebase absolute paths /arena/ → /arena/demo/ in markup + code (skip data json)
  let rewritten = 0;
  for await (const file of walk(DEST)) {
    if (!/\.(html|js|css)$/.test(file)) continue; // fixtures.json + any json stay verbatim
    const before = await fs.readFile(file, 'utf8');
    const after = before.replaceAll('/arena/', '/arena/demo/');
    if (after !== before) { await fs.writeFile(file, after); rewritten++; }
  }

  const pages = (await fs.readdir(DEST, { withFileTypes: true })).filter((e) => e.isDirectory() || e.name.endsWith('.html')).length;
  // The Cortex recall pane is the demo's headline surface — fail loudly if the
  // bundle was built without it (the route is /arena/cortex/, data API stays
  // /api/knowledge).
  const hasCortex = await exists(path.join(DEST, 'cortex', 'index.html'));
  console.log(`[deploy-arena-demo] deployed → ${path.relative(REPO, DEST)}`);
  console.log(`[deploy-arena-demo] top-level entries: ${pages} · rebased files: ${rewritten} · cortex route: ${hasCortex ? 'YES' : 'MISSING'}`);
  if (!hasCortex) { console.error('[deploy-arena-demo] cortex route missing — aborting signal'); process.exit(2); }
}

main().catch((e) => { console.error(e); process.exit(1); });
