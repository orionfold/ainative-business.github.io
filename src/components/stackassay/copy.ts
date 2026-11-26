// Single source of truth for the Stack Assay bridge copy + link contract.
// Sibling to ../flow/copy.ts, ../proof/copy.ts and ../magnet/copy.ts.
//
// Founder decision 2026-11-25: Stack Assay (https://stackassay.com) is
// Orionfold's flagship and replaces Flow on every flagship surface of this site:
// sticky bar, top-level nav item + button, homepage band, closing band. The
// Flow components stay in src/components/flow/ unmounted, for easy restore.
//
// COPY STATUS: APPROVED by the Stack Assay messaging check (2026-11-25), with
// the claim fix applied. Founder approves the push.
//
// CLAIM FIX: never say "Stack Assay tests Claude Code and Codex". The harness
// lab has not run Codex yet. Use "If you build with Claude Code or Codex...".
//
// Copy rules (from the Stack Assay session, 2026-11-25):
//   - Name Claude Code and Codex together, never one alone.
//   - No hype words.
//   - Keep the stackassay.com message: "Don't trust the leaderboard. Assay your stack."
//   - No arrow glyphs or icons in copy or on buttons. No em-dashes (house style).

const SA_BASE = 'https://stackassay.com/';
const SA_SOURCE = 'ainative.business';
const SA_CAMPAIGN = 'stackassay-launch';

// One scheme across every Orionfold property: "banner" for the sticky bar only,
// "referral" for every other placement (nav, bands, end notes).
export type SaMedium = 'banner' | 'referral';

/**
 * Stack Assay URL tagged per placement. `content` doubles as the GA4 event
 * surface. The sticky banner is exactly:
 * https://stackassay.com/?utm_source=ainative.business&utm_medium=banner&utm_campaign=stackassay-launch&utm_content=topbar
 */
export function saHref(medium: SaMedium, content: string): string {
  const q = new URLSearchParams({
    utm_source: SA_SOURCE,
    utm_medium: medium,
    utm_campaign: SA_CAMPAIGN,
    utm_content: content,
  });
  return `${SA_BASE}?${q.toString()}`;
}

/** Bump the suffix whenever the banner copy changes, so it re-shows once. */
export const SA_BANNER_KEY = 'stackassay-banner-v1';

export const SA_BANNER = {
  // Desktop line. The detail sheds below ~900px; the lead stays.
  lead: "Don't trust the leaderboard. Assay your stack.",
  detail: 'Building with Claude Code or Codex? See what holds up on real tasks.',
  cta: 'Stack Assay',
} as const;

export const SA_NAV = {
  item: 'Stack Assay',
  button: 'Assay your stack',
} as const;

export const SA_HOME_BAND = {
  eyebrow: 'New from the author',
  title: "Don't trust the leaderboard. Assay your stack.",
  body:
    'Leaderboards rank models. But if you build with Claude Code or Codex, you ship a stack. That means the model, the harness and the tools around it. Stack Assay runs whole stacks on real tasks. It publishes what held up, with code you can build on.',
  cta: 'See the findings',
} as const;

export const SA_CLOSING_BAND = {
  eyebrow: 'Stack Assay',
  title: 'Leaderboards rank models. You ship a stack.',
  cta: 'Assay your stack',
} as const;

export const SA_END_NOTE = {
  eyebrow: 'Stack Assay',
  title: "Don't trust the leaderboard. Assay your stack.",
  body:
    'If you build with Claude Code or Codex, you ship a stack, not just a model. Stack Assay, the lab from the author of this site, runs whole stacks on real tasks and publishes what held up.',
  cta: 'Visit Stack Assay',
} as const;

/** Field-note tags that earn the end note in place of the Proof card. */
export const SA_END_NOTE_TAGS = new Set([
  'claude-code',
  'claude-agent-sdk',
  'claude-opus',
  'agentic',
  'multi-agent',
  'agent-loop',
  'llm-agents',
  'tool-calling',
  'tool-use',
  'terminal-tools',
  'dev-tools',
  'agentskills',
  'benchmark',
  'benchmarks',
  'eval',
  'evals',
  'evaluation',
  'humaneval',
]);
