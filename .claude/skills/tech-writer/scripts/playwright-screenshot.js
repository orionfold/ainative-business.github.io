#!/usr/bin/env node
/*
 * Direct Node + Playwright screenshot — fallback for when Playwright-MCP's
 * default `chrome` channel isn't available (e.g. aarch64 DGX Spark, where
 * /opt/google/chrome/chrome doesn't exist) or when mid-session MCP arg
 * reconfiguration doesn't reload. Uses Playwright's bundled chromium
 * from ~/.cache/ms-playwright/.
 *
 * Usage:
 *   node playwright-screenshot.js <URL> <OUT_PATH> [--viewport-only] [--selector '.prose img']
 *
 * Examples:
 *   # full-page shot
 *   node playwright-screenshot.js 'https://build.nvidia.com' /tmp/shot.png
 *
 *   # viewport scrolled to a specific element
 *   node playwright-screenshot.js 'http://127.0.0.1:4321/articles/foo/' /tmp/shot.png --viewport-only --selector '.prose img'
 */

const fs = require('fs');
const path = require('path');

function resolvePlaywright() {
  try { return require('playwright'); } catch {}
  const npxDir = path.join(process.env.HOME, '.npm/_npx');
  if (fs.existsSync(npxDir)) {
    for (const h of fs.readdirSync(npxDir)) {
      const p = path.join(npxDir, h, 'node_modules/playwright');
      if (fs.existsSync(p)) return require(p);
    }
  }
  console.error('playwright not found. Install: npx playwright install chromium');
  process.exit(1);
}

function resolveChromiumExecutable() {
  const browsersDir = process.env.PLAYWRIGHT_BROWSERS_PATH
    || path.join(process.env.HOME, '.cache/ms-playwright');
  if (!fs.existsSync(browsersDir)) return null;
  const dirs = fs.readdirSync(browsersDir)
    .filter((n) => /^chromium-\d+$/.test(n))
    .sort();
  if (dirs.length === 0) return null;
  const exe = path.join(browsersDir, dirs[dirs.length - 1], 'chrome-linux', 'chrome');
  return fs.existsSync(exe) ? exe : null;
}

const args = process.argv.slice(2);
const URL = args[0];
const OUT = args[1];
if (!URL || !OUT) {
  console.error('usage: playwright-screenshot.js <URL> <OUT> [--viewport-only] [--selector SEL]');
  process.exit(2);
}
const viewportOnly = args.includes('--viewport-only');
const selIdx = args.indexOf('--selector');
const SELECTOR = selIdx >= 0 ? args[selIdx + 1] : null;

const { chromium } = resolvePlaywright();
const executablePath = resolveChromiumExecutable();

(async () => {
  const browser = await chromium.launch({
    ...(executablePath ? { executablePath } : {}),
    headless: true,
    args: ['--no-sandbox', '--disable-gpu', '--disable-dev-shm-usage'],
  });
  const context = await browser.newContext({
    viewport: { width: 1440, height: 900 },
    deviceScaleFactor: 2,
  });
  const page = await context.newPage();
  page.on('console', (m) => {
    if (m.type() === 'error' || m.type() === 'warning') console.error('[console]', m.type(), m.text());
  });
  try {
    await page.goto(URL, { waitUntil: 'domcontentloaded', timeout: 30000 });
    await page.waitForLoadState('networkidle', { timeout: 15000 }).catch(() => {});
    if (SELECTOR) {
      await page.locator(SELECTOR).first().scrollIntoViewIfNeeded();
      await page.evaluate(() => window.scrollBy(0, -120));
    }
    await page.waitForTimeout(1500);
    await page.screenshot({ path: OUT, fullPage: !viewportOnly });
    console.error('ok', OUT);
  } finally {
    await browser.close();
  }
})().catch((e) => { console.error('fail', e.message); process.exit(1); });
