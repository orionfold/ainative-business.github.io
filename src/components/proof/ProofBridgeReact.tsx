import { PROOF_COPY, proofHref, fireProofBridgeClick, type ProofVariant } from './copy';

/**
 * React twin of ProofBridge.astro for the book reader's client SPA. Shares the
 * voice-locked copy + link contract via ./copy; styled with the reader's own
 * Tailwind card idiom so the accent inherits the active book theme. Re-renders
 * per active chapter (surface = chapter-<slug>).
 */
export function ProofBridgeReact({
  variant = 'economics',
  surface,
}: {
  variant?: ProofVariant;
  surface: string;
}) {
  const { eyebrow, body, cta } = PROOF_COPY[variant];
  const href = proofHref(surface);
  return (
    <aside data-proof-bridge data-surface={surface} data-variant={variant} className="mt-10">
      <a
        href={href}
        rel="noopener"
        onClick={() => fireProofBridgeClick({ surface, variant, link_url: href })}
        className="group block no-underline rounded-xl border border-primary/30 border-l-[3px] bg-surface-raised px-7 py-6 transition-colors hover:border-primary/60 hover:bg-primary/5"
      >
        <span className="mb-3 block font-mono text-[0.65rem] uppercase tracking-[0.2em] text-primary">
          {eyebrow}
        </span>
        <p className="mb-4 text-[0.95rem] leading-relaxed text-text">{body}</p>
        <span className="inline-flex items-center gap-1.5 font-mono text-xs font-semibold uppercase tracking-[0.18em] text-primary">
          {cta}
          <svg
            width="14"
            height="14"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
            aria-hidden="true"
            className="transition-transform group-hover:translate-x-0.5 group-hover:-translate-y-0.5"
          >
            <path d="M7 17 17 7" />
            <path d="M7 7h10v10" />
          </svg>
        </span>
      </a>
    </aside>
  );
}
