import http from 'node:http';
import path from 'node:path';
import fs from 'node:fs';
import { fileURLToPath } from 'node:url';
import type { AddressInfo } from 'node:net';
import puppeteer from 'puppeteer-core';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(__dirname, '..');
const DIST = path.join(ROOT, 'dist');
const OUT_DIR = path.join(ROOT, 'announce');

type Target = {
  name: string;
  route: string;
  selector: string;
  padding: number;
  theme?: 'light' | 'dark';
};

const TARGETS: Target[] = [
  {
    name: 'hero.png',
    route: '/',
    selector: '.hero-arch-wrapper',
    padding: 80,
    theme: 'dark',
  },
  {
    name: 'architecture.png',
    route: '/research/ai-transformation/',
    selector: 'figure.figure--architecture svg',
    padding: 40,
    theme: 'light',
  },
];

const VIEWPORT = { width: 1600, height: 1200 };
const DPR = 3;

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
    throw new Error(`Build output missing at ${DIST}. Run 'npm run build' first.`);
  }

  const chromeExecutable = findChromeExecutable();
  console.log(`[announce] Chrome: ${chromeExecutable}`);

  const { server, port } = await serveDist();
  console.log(`[announce] Serving dist on http://127.0.0.1:${port}`);

  const browser = await puppeteer.launch({
    executablePath: chromeExecutable,
    headless: true,
    args: ['--no-sandbox', '--disable-setuid-sandbox'],
  });

  try {
    const page = await browser.newPage();
    await page.setViewport({ ...VIEWPORT, deviceScaleFactor: DPR });
    await page.emulateMediaFeatures([{ name: 'prefers-reduced-motion', value: 'reduce' }]);

    fs.mkdirSync(OUT_DIR, { recursive: true });

    for (const target of TARGETS) {
      console.log(`[announce] ${target.route} -> ${target.name}`);
      await page.goto(`http://127.0.0.1:${port}${target.route}`, {
        waitUntil: 'networkidle0',
        timeout: 60_000,
      });

      // Force any data-animate elements into their visible end state
      // (the site animates with opacity/translate — reduced-motion should neutralize
      // these, but we add a safety net in case styles guard behind it are incomplete).
      await page.addStyleTag({
        content: `
          [data-animate], [data-animate-stagger] > *, [data-svg-animate] * {
            opacity: 1 !important;
            transform: none !important;
            animation-play-state: paused !important;
          }
        `,
      });

      // Allow fonts + any lingering paint to settle
      await new Promise((r) => setTimeout(r, 400));

      const handle = await page.waitForSelector(target.selector, { timeout: 10_000 });
      if (!handle) throw new Error(`selector not found: ${target.selector}`);

      // Inline-pad the element so elementHandle.screenshot() captures with
      // breathing room (ambient glow + visual margin). scrollIntoViewIfNeeded
      // runs automatically inside element.screenshot() on Puppeteer.
      await page.evaluate(
        (sel, pad) => {
          const el = document.querySelector(sel) as HTMLElement | null;
          if (!el) return;
          el.style.padding = `${pad}px`;
          el.style.boxSizing = 'content-box';
        },
        target.selector,
        target.padding,
      );

      const outFile = path.join(OUT_DIR, target.name);
      await handle.screenshot({ path: outFile, type: 'png', omitBackground: false });

      const box = await handle.boundingBox();
      const sizeKB = (fs.statSync(outFile).size / 1024).toFixed(1);
      const dims = box ? `${Math.round(box.width * DPR)}×${Math.round(box.height * DPR)}px` : '';
      console.log(`[announce]   ${target.name} — ${dims} @ ${sizeKB} KB`);
    }
  } finally {
    await browser.close();
    server.close();
  }
}

main().catch((err) => {
  console.error('[announce] Generation failed:', err);
  process.exit(1);
});
