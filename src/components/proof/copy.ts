// Single source of truth for the A13 Proof-bridge copy + link contract.
// Shared by ProofBridge.astro (static surfaces) and ProofBridgeReact.tsx (the
// book reader's React SPA) so the voice-locked copy lives in exactly one place.
//
// Copy is the approved, paste-ready per-surface CTA from the demand-gen relay
// (strategy ainative-business-website/_RELAY.md, 2026-06-27 Mac→Spark). Do NOT
// reword without a new relay — value-led, "rerun it" never "trust us", no
// em-dashes, grounded in leads/proof-icp.md P0–P3.
//
// Destination is exactly https://orionfold.com/proof/ — the short slug 404s.
// UTM contract: utm_source=ainative · utm_medium=cross-sell ·
// utm_campaign=proof-bridge · utm_content=<surface>.

export type ProofVariant = 'builder' | 'governance' | 'economics';

export const PROOF_COPY: Record<ProofVariant, { eyebrow: string; body: string; cta: string }> = {
  builder: {
    eyebrow: 'Orionfold Proof',
    body:
      'Think a small local model can beat the frontier ones on your task? We proved it on one desk, and you can rerun the exact run yourself.',
    cta: 'See the receipt',
  },
  governance: {
    eyebrow: 'Orionfold Proof',
    body:
      'This is not an opinion, it is a signed, rerunnable receipt: a 4B model that refused all 9 trick questions while a model 8x its size made up 3 answers. Prove which AI you can trust, on your own machine.',
    cta: 'Open Proof',
  },
  economics: {
    eyebrow: 'Orionfold Proof',
    body:
      'Same inputs, same receipt, every time. Before you bet a budget on a model, prove which one is actually worth it on your own task.',
    cta: 'Run the proof',
  },
};

export function proofHref(surface: string): string {
  return (
    'https://orionfold.com/proof/' +
    `?utm_source=ainative&utm_medium=cross-sell&utm_campaign=proof-bridge&utm_content=${encodeURIComponent(surface)}`
  );
}

/** Fire the GA4 cross-property click event (no-op if gtag absent). */
export function fireProofBridgeClick(detail: { surface: string; variant: string; link_url: string }): void {
  const gtag = (globalThis as unknown as { gtag?: (...a: unknown[]) => void }).gtag;
  if (typeof gtag === 'function') {
    gtag('event', 'proof_bridge_click', { ...detail, transport_type: 'beacon' });
  }
}
