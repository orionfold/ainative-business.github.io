// Single source of truth for the A17 magnet-bridge copy + link contract.
// Sibling to the A13 Proof bridge (../proof/copy.ts): that bridge cross-sells
// the Proof receipts wall; THIS bridge cross-sells the live lead magnet (the
// free AI-Native-Business book/playbook, email-gated) so ainative.business
// builder traffic is captured as owned email contacts, not just a pageview.
//
// Destination + UTM are the approved contract from the demand-gen relay
// (strategy ainative-business-website/_RELAY.md, 2026-06-28 Mac→Spark, A17).
// utm_content is per-placement so GA4 attributes which surface converts —
// matching the orionfold.com sibling campaign's per-placement pattern
// (orionfold-website/_RELAY.md latest+21). Do NOT reword the copy without a
// new relay: framing is outcome/ICP-led (the "structure" line) for prose
// surfaces and value-first price-anchored ("the $20 book free, PDF+EPUB") for
// chrome/contextual surfaces. No em-dashes in CTA copy.

// Live magnet destination (relay 2026-06-28). The trailing slash matters.
const MAGNET_BASE = 'https://orionfold.com/become-ai-native-business/';
const UTM =
  'utm_source=ainative-onsite&utm_medium=organic&utm_campaign=2026-q3-magnet-traffic';

/** Magnet URL with per-placement utm_content (e.g. footer / sticky-bar / book-cta). */
export function magnetHref(placement: string): string {
  return `${MAGNET_BASE}?${UTM}&utm_content=${encodeURIComponent(placement)}`;
}

// Outcome/ICP framing — for the prose surfaces (footer band, end-of-content card).
export const MAGNET_COPY = {
  eyebrow: 'Free playbook',
  body: 'How an AI-native company is actually structured. Get the playbook free.',
  cta: 'Get the book',
} as const;

// Value-first, price-anchored framing — for chrome + contextual surfaces (the
// sticky bar, and the "read book" adjacent links). The price tag makes "free"
// read as valuable (message-matched to the magnet page's own $20 anchor).
export const MAGNET_OFFER = {
  eyebrow: 'Free book',
  body: 'Get the $20 AI Native Business book free, PDF and EPUB.',
  cta: 'Get it free',
  short: 'Get the $20 AI Native Business book free (PDF + EPUB)',
} as const;

/** Fire the GA4 cross-property click event (no-op if gtag absent). */
export function fireMagnetBridgeClick(detail: { surface: string; link_url: string }): void {
  const gtag = (globalThis as unknown as { gtag?: (...a: unknown[]) => void }).gtag;
  if (typeof gtag === 'function') {
    gtag('event', 'magnet_bridge_click', { ...detail, transport_type: 'beacon' });
  }
}
