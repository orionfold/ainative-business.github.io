// Single source of truth for the Flow bridge copy + link contract. Sibling to
// the A17 magnet bridge (../magnet/copy.ts) and the A13 proof bridge
// (../proof/copy.ts): same shape, different destination + campaign.
//
// Flow is available for Mac. This site sends visitors to the live product
// page, where Orionfold owns downloads and conversion tracking.
//
// Copy is persona-matched on purpose. Flow's own page carries a local-first
// story (a bundled local AI runtime, four execution domains, Ollama/LM Studio
// detection) and the parent states the family logic itself: "Arena scores local
// models with reruns you can verify. Flow brings the same discipline to the
// document itself." That is the angle this audience responds to, so these
// surfaces lead with local runtime + receipts, never with document
// productivity. No em-dashes in CTA copy (house style).

// Keep the canonical landing page as the destination so new visitors see the
// product and current download options before choosing a download.
const FLOW_BASE = 'https://orionfold.com/flow/';
const UTM =
  'utm_source=ainative-onsite&utm_medium=organic&utm_campaign=2026-q3-flow-launch';

/**
 * Flow landing page URL with per-placement utm_content (e.g. sticky-bar /
 * home-band / nav / cta-footer). Doubles as the GA4 event surface so we can
 * read which placement drives the click.
 *
 * Land at the top of the product page; the parent owns the current installer
 * URL and download CTA. Do not pin an installer version in this bridge.
 */
export function flowHref(placement: string): string {
  return `${FLOW_BASE}?${UTM}&utm_content=${encodeURIComponent(placement)}`;
}

// Shared launch CTA for the bar, navigation, homepage band and closing CTA.
const FLOW_CTA = 'Download Flow';

export const FLOW_BAR = {
  eyebrow: 'Live',
  lead: 'Orionfold Flow is live for Mac',
  qualifier: 'Free Base · 10 Pro days included · No credit card',
  cta: FLOW_CTA,
} as const;

// Prose framing — the homepage band and the closing CTA. Leads with the
// mechanism (approve the diff, keep the receipt) because that is the part an
// engineer evaluates.
export const FLOW_COPY = {
  eyebrow: 'Orionfold Flow · Available now for Mac',
  title: 'The AI document app that shows its work',
  body:
    'Flow is the Mac app where AI does real work in the document, shows you the exact diff, and leaves a receipt naming what ran, where it ran, and what it cost. It carries its own local inference runtime, and if you already run Ollama or LM Studio it serves the models you have pulled in place.',
  kicker: 'Arena scores local models with reruns you can verify. Flow brings the same discipline to the document.',
  // One CTA per surface, deliberately. Every Flow link goes to the same page,
  // so a second button is a second way to do the identical thing dressed up as
  // a choice — it splits attention and measures nothing useful.
  cta: FLOW_CTA,
  fine: 'Free Base · 10 Pro days included · No credit card',
} as const;

/**
 * Fire the GA4 cross-property click event (no-op if gtag absent).
 *
 * NOTE ON MEASUREMENT: this click is the LAST thing this property can observe.
 * Downloads and subsequent conversions happen on orionfold.com. Attribution
 * past the click depends on the parent preserving the incoming campaign and
 * utm_content; this event alone does not prove a download or installation.
 */
export function fireFlowBridgeClick(detail: { surface: string; link_url: string }): void {
  const gtag = (globalThis as unknown as { gtag?: (...a: unknown[]) => void }).gtag;
  if (typeof gtag === 'function') {
    gtag('event', 'flow_bridge_click', { ...detail, transport_type: 'beacon' });
  }
}
