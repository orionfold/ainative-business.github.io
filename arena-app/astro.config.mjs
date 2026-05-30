import { defineConfig } from 'astro/config';
import mdx from '@astrojs/mdx';
import preact from '@astrojs/preact';
import tailwindcss from '@tailwindcss/vite';
import remarkDirective from 'remark-directive';
import rehypeCaption from './src/lib/rehype-caption.mjs';
import remarkFixLinks from './src/lib/remark-fix-links.mjs';
import remarkExplainers from './src/lib/remark-explainers.mjs';
import rehypeExplainerFigure from './src/lib/rehype-explainer-figure.mjs';

// ai-field-notes — Astro config
// Content sourced from ../articles/<slug>/article.md via content collection
// defined in src/content.config.ts.

// Production source is consumed by a separate Claude Code instance that publishes
// the site at https://ainative.business/field-notes/, so prod needs `base: '/field-notes'`.
// In dev that prefix just makes the root URL 404, which is friction — so drop it
// unless NODE_ENV === 'production'.
const isProd = process.env.NODE_ENV === 'production';

// Arena bundle build (P7 distribution). `ARENA_BUILD=1` switches the build to
// a self-contained Orionfold Arena bundle rooted at `base: '/arena'`, emitted
// to `./dist-arena/`. `fieldkit arena build` runs this, then prunes the
// `arena/**` + shared `assets/**` output into the packaged
// `fieldkit/src/fieldkit/arena/_webui/` so `pip install fieldkit[arena]` ships
// the runnable cockpit (served by the sidecar's StaticFiles mount at /arena).
// The same `/arena` base also serves the public web preview verbatim.
const isArenaBuild = process.env.ARENA_BUILD === '1';

// Demo bundle build. `ARENA_DEMO=1` builds the SAME `/arena` cockpit but the
// islands boot a fetch/EventSource shim (src/lib/arena/demo-mode.mjs) that
// replays a static fixture bundle instead of the FastAPI sidecar — the public,
// sidecar-less web preview. Emitted to `./dist-arena-demo/` so it never clobbers
// the wheel bundle. The `__ARENA_DEMO__` define gates the shim in sidecar.mjs.
const isArenaDemo = process.env.ARENA_DEMO === '1';
const isArena = isArenaBuild || isArenaDemo;
const base = isArena ? '/arena' : isProd ? '/field-notes' : '/';
const arenaOutDir = isArenaDemo ? './dist-arena-demo' : './dist-arena';

const REPO_BASE = 'https://github.com/manavsehgal/ai-field-notes/blob/main';

export default defineConfig({
  site: 'https://ainative.business',
  base,
  trailingSlash: 'always',
  ...(isArena ? { outDir: arenaOutDir } : {}),

  // Preact powers the Spark Arena cockpit islands (TelemetryGauge,
  // CurrentLane, M4+ ChatLane/CompareDuel). `client:only="preact"` on
  // every Arena island — they never SSR (the FastAPI sidecar isn't
  // available at build time). MDX stays the prose pipeline.
  integrations: [mdx(), preact()],

  // Dev server binds to all interfaces so Firefox on the laptop/phone can
  // reach the Spark over the LAN or tailnet, not just loopback.
  server: {
    host: true,
    port: 4321,
  },

  markdown: {
    remarkPlugins: [
      [remarkFixLinks, { base, repoBase: REPO_BASE }],
      remarkDirective,
      remarkExplainers,
    ],
    rehypePlugins: [rehypeCaption, rehypeExplainerFigure],
    shikiConfig: {
      theme: 'github-dark-dimmed',
      wrap: true,
    },
  },

  build: {
    assets: 'assets',
  },

  vite: {
    plugins: [tailwindcss()],
    // Build-time flag the Arena islands read (sidecar.mjs / demo-mode.mjs).
    // Always defined so a bare `__ARENA_DEMO__` reference never ReferenceErrors.
    define: {
      __ARENA_DEMO__: JSON.stringify(isArenaDemo),
    },
  },
});
