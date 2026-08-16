// Single source of truth for the Flow bridge copy + link contract. Sibling to
// the A17 magnet bridge (../magnet/copy.ts) and the A13 proof bridge
// (../proof/copy.ts): same shape, different destination + campaign.
//
// Orionfold launched Flow as its flagship 2026-08-15 and took over
// orionfold.com (Flow-only nav, sticky waitlist bar, hero capture form). This
// bridge is the sibling move on ainative.business: point the top of the funnel
// at the Flow waitlist while this site keeps its own AI-Research-Engineer
// persona. See _SPECS/flow-traffic-redirect-v1.md.
//
// WHY THIS SITE ONLY LINKS, NEVER CAPTURES: the waitlist POSTs to a Supabase
// edge function whose CORS allowlist is https://orionfold.com only. A form
// hosted here would fail on submit. So every surface below is an outbound link
// to /flow/#waitlist; the parent owns the form, the double opt-in, and the
// generate_lead conversion event.
//
// Copy is persona-matched on purpose. Flow's own page carries a local-first
// story (a bundled local AI runtime, four execution domains, Ollama/LM Studio
// detection) and the parent states the family logic itself: "Arena scores local
// models with reruns you can verify. Flow brings the same discipline to the
// document itself." That is the angle this audience responds to, so these
// surfaces lead with local runtime + receipts, never with document
// productivity. No em-dashes in CTA copy (house style).

// Live Flow destination. The trailing slash matters; the anchor lands on the
// waitlist band at the foot of the page.
const FLOW_BASE = 'https://orionfold.com/flow/';
const UTM =
  'utm_source=ainative-onsite&utm_medium=organic&utm_campaign=2026-q3-flow-waitlist';

/**
 * Flow waitlist URL with per-placement utm_content (e.g. sticky-bar / home-band
 * / nav / cta-footer). Doubles as the GA4 event surface so we can read which
 * placement drives the click.
 */
export function flowHref(placement: string): string {
  return `${FLOW_BASE}?${UTM}&utm_content=${encodeURIComponent(placement)}#waitlist`;
}

/** Flow landing page, no anchor. For "learn more" links that shouldn't jump to the form. */
export function flowPageHref(placement: string): string {
  return `${FLOW_BASE}?${UTM}&utm_content=${encodeURIComponent(placement)}`;
}

// Chrome framing — the slim sticky bar. Opens with the parent's own line so the
// two properties say the same thing, then swaps the qualifier for the
// local-runtime angle this site's readers care about.
export const FLOW_BAR = {
  eyebrow: 'New',
  lead: 'Orionfold Flow is coming to Mac',
  qualifier: 'AI agency for documents, with a local runtime and a receipt for every run',
  cta: 'Join the waitlist',
} as const;

// Prose framing — the homepage band and the closing CTA. Leads with the
// mechanism (approve the diff, keep the receipt) because that is the part an
// engineer evaluates.
export const FLOW_COPY = {
  eyebrow: 'Orionfold Flow · In development',
  title: 'The AI document app that shows its work',
  body:
    'Flow is the Mac app where AI does real work in the document, shows you the exact diff, and leaves a receipt naming what ran, where it ran, and what it cost. It carries its own local inference runtime, and if you already run Ollama or LM Studio it serves the models you have pulled in place.',
  kicker: 'Arena scores local models with reruns you can verify. Flow brings the same discipline to the document.',
  cta: 'Join the waitlist',
  secondary: 'See the product tour',
  fine: 'In development · Freemium subscription planned · Free to join, one email a week',
} as const;

/**
 * Fire the GA4 cross-property click event (no-op if gtag absent).
 *
 * NOTE ON MEASUREMENT: this click is the LAST thing this property can observe.
 * The waitlist conversion (`generate_lead`) fires on form submit, which happens
 * on orionfold.com, and the confirm link redirects to orionfold.com/?confirmed=1
 * so the visitor never returns here. Attribution past the click depends on the
 * utm_content above surviving into the row the parent records. See
 * _SPECS/flow-traffic-redirect-v1.md §5.
 */
export function fireFlowBridgeClick(detail: { surface: string; link_url: string }): void {
  const gtag = (globalThis as unknown as { gtag?: (...a: unknown[]) => void }).gtag;
  if (typeof gtag === 'function') {
    gtag('event', 'flow_bridge_click', { ...detail, transport_type: 'beacon' });
  }
}
