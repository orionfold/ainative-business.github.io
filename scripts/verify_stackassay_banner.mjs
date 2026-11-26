/**
 * Post-build verifier for the Stack Assay flagship surfaces (2026-11-25).
 * Walks every dist/**\/index.html and asserts:
 *   1. Every page that renders the nav (#nav-wrapper) carries the sticky banner
 *      (#sa-bar) with a labelled close button, and no longer carries #flow-bar.
 *   2. Every stackassay.com link carries all four UTM parameters of the shared
 *      Orionfold scheme: utm_source=ainative.business,
 *      utm_campaign=stackassay-launch, utm_medium=banner (sticky bar only) or
 *      referral (everything else), utm_content from the known spot list. The
 *      banner link is exactly the contract URL. Links open in the same tab.
 *   3. No arrow glyphs inside the banner, the end note, or any Stack Assay
 *      link text.
 *
 * Exit code = number of failed checks. Non-zero blocks the build.
 */
import { readdir, readFile } from 'node:fs/promises';
import { join } from 'node:path';

const DIST = 'dist';
const BANNER_URL =
  'https://stackassay.com/?utm_source=ainative.business&utm_medium=banner&utm_campaign=stackassay-launch&utm_content=topbar';
const CONTENTS = new Set(['topbar', 'nav', 'home-band', 'closing-band']);
const contentOk = (c) => CONTENTS.has(c) || /^(fieldnote|book)-[a-z0-9-]+$/.test(c);
const ARROWS = /[←-⇿➔-➿⬀-⯿›»]|&rarr;|&nearr;|&raquo;|&rsaquo;/;

async function* walk(dir) {
  for (const e of await readdir(dir, { withFileTypes: true })) {
    const p = join(dir, e.name);
    if (e.isDirectory()) yield* walk(p);
    else if (e.name === 'index.html') yield p;
  }
}

const unescape = (s) => s.replace(/&amp;/g, '&');
const fails = [];
let navPages = 0, saLinks = 0, endNotes = 0;

for await (const file of walk(DIST)) {
  const html = await readFile(file, 'utf8');
  const rel = file.slice(DIST.length + 1);

  if (html.includes('id="nav-wrapper"')) {
    navPages++;
    if (!html.includes('id="sa-bar"')) fails.push(`${rel}: nav present but #sa-bar missing`);
    if (!/id="sa-bar-close"[^>]*aria-label="[^"]+"/.test(html) && !/aria-label="[^"]+"[^>]*id="sa-bar-close"/.test(html))
      fails.push(`${rel}: #sa-bar-close missing aria-label`);
    if (html.includes('id="flow-bar"')) fails.push(`${rel}: #flow-bar still rendered`);
    const bar = html.match(/<aside[^>]*id="sa-bar"[\s\S]*?<\/aside>/);
    if (bar) {
      const hrefs = [...bar[0].matchAll(/href="([^"]+)"/g)].map((m) => unescape(m[1]));
      if (hrefs.length !== 1 || hrefs[0] !== BANNER_URL)
        fails.push(`${rel}: banner link is ${JSON.stringify(hrefs)}, expected exactly the contract URL`);
      if (ARROWS.test(bar[0].replace(/<style[\s\S]*?<\/style>/g, '')))
        fails.push(`${rel}: arrow glyph inside banner`);
    }
  }

  for (const note of html.matchAll(/<aside[^>]*class="sa-note[\s\S]*?<\/aside>/g)) {
    endNotes++;
    if (ARROWS.test(note[0])) fails.push(`${rel}: arrow glyph inside end note`);
  }

  for (const m of html.matchAll(/<a\b[^>]*href="(https:\/\/stackassay\.com[^"]*)"[^>]*>([\s\S]*?)<\/a>/g)) {
    saLinks++;
    const url = new URL(unescape(m[1]));
    const q = url.searchParams;
    if (q.get('utm_source') !== 'ainative.business') fails.push(`${rel}: bad utm_source on ${url}`);
    if (q.get('utm_campaign') !== 'stackassay-launch') fails.push(`${rel}: bad utm_campaign on ${url}`);
    const content = q.get('utm_content') ?? '';
    const medium = q.get('utm_medium');
    if (!contentOk(content)) fails.push(`${rel}: bad utm_content on ${url}`);
    if (medium !== (content === 'topbar' ? 'banner' : 'referral')) fails.push(`${rel}: bad utm_medium on ${url}`);
    if (/target="_blank"/.test(m[0].slice(0, m[0].indexOf('>') + 1))) fails.push(`${rel}: Stack Assay link opens a new tab`);
    const text = m[2].replace(/<[^>]+>/g, '');
    if (ARROWS.test(text)) fails.push(`${rel}: arrow glyph in Stack Assay link text`);
  }
}

console.log(`stackassay: ${navPages} nav pages, ${saLinks} stackassay.com links, ${endNotes} end notes`);
if (navPages === 0) fails.push('no nav pages found (did the build run?)');
for (const f of fails.slice(0, 40)) console.error('FAIL ' + f);
if (fails.length > 40) console.error(`... and ${fails.length - 40} more`);
console.log(fails.length ? `${fails.length} failure(s)` : 'stackassay: all checks passed');
process.exit(fails.length);
