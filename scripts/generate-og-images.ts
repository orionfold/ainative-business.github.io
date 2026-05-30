import http from 'node:http';
import path from 'node:path';
import fs from 'node:fs';
import { fileURLToPath } from 'node:url';
import type { AddressInfo } from 'node:net';
import puppeteer from 'puppeteer-core';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(__dirname, '..');
const DIST = path.join(ROOT, 'dist');
const PUBLIC_DIR = path.join(ROOT, 'public');

// Static targets: site-wide and book OG images.
const STATIC_TARGETS = [
  { route: '/og/', outName: 'og-image.png' },
  { route: '/book/og/', outName: 'book/og-image.png' },
];

// Discover field-note articles by reading the articles/ directory. Each
// article gets a per-slug OG image rendered from /og/field-notes/<slug>/
// and saved to /public/og/field-notes/<slug>.png so social/SMS/answer-engine
// link previews use article-specific imagery instead of the generic site OG.
function discoverFieldNoteSlugs(): string[] {
  const articlesDir = path.join(ROOT, 'articles');
  if (!fs.existsSync(articlesDir)) return [];
  return fs
    .readdirSync(articlesDir, { withFileTypes: true })
    .filter((d) => d.isDirectory())
    .filter((d) => {
      const dir = path.join(articlesDir, d.name);
      return (
        fs.existsSync(path.join(dir, 'article.md')) ||
        fs.existsSync(path.join(dir, 'article.mdx'))
      );
    })
    .map((d) => d.name)
    .sort();
}

// Discover product-launch articles by reading the products/ directory. Each
// product gets a per-slug OG image rendered from /og/products/<slug>/ and saved
// to /public/og/products/<slug>.png so the flagship product pages surface a
// branded, build-metric social card instead of the generic site OG.
function discoverProductSlugs(): string[] {
  const productsDir = path.join(ROOT, 'products');
  if (!fs.existsSync(productsDir)) return [];
  return fs
    .readdirSync(productsDir, { withFileTypes: true })
    .filter((d) => d.isDirectory())
    .filter((d) => fs.existsSync(path.join(productsDir, d.name, 'product.md')))
    .map((d) => d.name)
    .sort();
}

function buildTargets(): { route: string; outName: string }[] {
  const articleTargets = discoverFieldNoteSlugs().map((slug) => ({
    route: `/og/field-notes/${slug}/`,
    outName: `og/field-notes/${slug}.png`,
  }));
  const productTargets = discoverProductSlugs().map((slug) => ({
    route: `/og/products/${slug}/`,
    outName: `og/products/${slug}.png`,
  }));
  return [...STATIC_TARGETS, ...articleTargets, ...productTargets];
}

const MIME: Record<string, string> = {
  '.html': 'text/html; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.js': 'application/javascript; charset=utf-8',
  '.mjs': 'application/javascript; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.svg': 'image/svg+xml',
  '.png': 'image/png',
  '.jpg': 'image/jpeg',
  '.jpeg': 'image/jpeg',
  '.gif': 'image/gif',
  '.webp': 'image/webp',
  '.avif': 'image/avif',
  '.ico': 'image/x-icon',
  '.woff': 'font/woff',
  '.woff2': 'font/woff2',
  '.ttf': 'font/ttf',
};

function mimeType(filePath: string): string {
  return MIME[path.extname(filePath).toLowerCase()] ?? 'application/octet-stream';
}

function findChromeExecutable(): string {
  const envPath = process.env.CHROME_PATH || process.env.PUPPETEER_EXECUTABLE_PATH;
  if (envPath && fs.existsSync(envPath)) return envPath;

  const candidates = [
    '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
    '/Applications/Google Chrome Canary.app/Contents/MacOS/Google Chrome Canary',
    '/Applications/Chromium.app/Contents/MacOS/Chromium',
    '/usr/bin/google-chrome-stable',
    '/usr/bin/google-chrome',
    '/usr/bin/chromium-browser',
    '/usr/bin/chromium',
    '/snap/bin/chromium',
  ];

  for (const candidate of candidates) {
    if (fs.existsSync(candidate)) return candidate;
  }

  throw new Error(
    'Could not locate Chrome/Chromium. Install Google Chrome or set CHROME_PATH to the executable.',
  );
}

function serveDist(): Promise<{ server: http.Server; port: number }> {
  return new Promise((resolve, reject) => {
    const server = http.createServer((req, res) => {
      const urlPath = decodeURIComponent(new URL(req.url ?? '/', 'http://localhost').pathname);
      let filePath = path.join(DIST, urlPath);
      const safe = path.resolve(filePath).startsWith(path.resolve(DIST));
      if (!safe) {
        res.statusCode = 403;
        res.end('forbidden');
        return;
      }
      if (fs.existsSync(filePath) && fs.statSync(filePath).isDirectory()) {
        filePath = path.join(filePath, 'index.html');
      }
      if (!fs.existsSync(filePath)) {
        res.statusCode = 404;
        res.end('not found');
        return;
      }
      res.setHeader('Content-Type', mimeType(filePath));
      fs.createReadStream(filePath).pipe(res);
    });

    server.on('error', reject);
    server.listen(0, '127.0.0.1', () => {
      const addr = server.address() as AddressInfo;
      resolve({ server, port: addr.port });
    });
  });
}

async function main() {
  if (!fs.existsSync(DIST)) {
    throw new Error(`Build output missing at ${DIST}. Run 'astro build' first.`);
  }

  const chromeExecutable = findChromeExecutable();
  console.log(`[og] Chrome: ${chromeExecutable}`);

  const { server, port } = await serveDist();
  console.log(`[og] Serving dist on http://127.0.0.1:${port}`);

  const browser = await puppeteer.launch({
    executablePath: chromeExecutable,
    headless: true,
    args: ['--no-sandbox', '--disable-setuid-sandbox'],
  });

  try {
    const page = await browser.newPage();
    await page.setViewport({ width: 1200, height: 630, deviceScaleFactor: 1 });

    const targets = buildTargets();
    const productCount = discoverProductSlugs().length;
    const fieldNoteCount = targets.length - STATIC_TARGETS.length - productCount;
    console.log(`[og] Rendering ${targets.length} OG images (${STATIC_TARGETS.length} static + ${fieldNoteCount} field-notes + ${productCount} products)`);

    for (const { route, outName } of targets) {
      const url = `http://127.0.0.1:${port}${route}`;
      console.log(`[og] ${route} -> ${outName}`);
      await page.goto(url, { waitUntil: 'networkidle0', timeout: 60_000 });

      const publicOut = path.join(PUBLIC_DIR, outName);
      const distOut = path.join(DIST, outName);
      fs.mkdirSync(path.dirname(publicOut), { recursive: true });
      fs.mkdirSync(path.dirname(distOut), { recursive: true });

      await page.screenshot({
        path: publicOut,
        type: 'png',
        clip: { x: 0, y: 0, width: 1200, height: 630 },
      });
      fs.copyFileSync(publicOut, distOut);

      const sizeKB = (fs.statSync(publicOut).size / 1024).toFixed(1);
      console.log(`[og]   wrote ${publicOut} (${sizeKB} KB)`);
    }
  } finally {
    await browser.close();
    server.close();
  }
}

main().catch((err) => {
  console.error('[og] Generation failed:', err);
  process.exit(1);
});
