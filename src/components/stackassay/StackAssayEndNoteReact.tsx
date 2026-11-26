import { saHref, fireSaBridgeClick, SA_END_NOTE } from './copy';

/**
 * React twin of StackAssayEndNote.astro for the book reader's client SPA.
 * Same copy and link contract via ./copy. Re-renders per active chapter
 * (surface = book-<chapter-slug>).
 *
 * Deliberately NOT marked data-sa-bridge: the delegated listener in
 * StackAssayBar binds at page load, and this node survives hydration, so it
 * would double-count. The onClick below is the only GA4 hook here.
 */
export function StackAssayEndNoteReact({ surface }: { surface: string }) {
  const href = saHref('referral', surface);
  return (
    <aside className="sa-note-react mt-10" data-surface={surface} aria-label="Stack Assay">
      <a
        href={href}
        onClick={() => fireSaBridgeClick({ surface, link_url: href })}
        className="block no-underline rounded-xl border border-primary/30 border-l-[3px] bg-surface-raised px-7 py-6 text-text transition-colors hover:border-primary/60 hover:bg-primary/5 focus-visible:outline-2 focus-visible:outline-offset-[3px] focus-visible:outline-text"
      >
        <span className="mb-2.5 block font-mono text-[0.65rem] font-semibold uppercase tracking-[0.2em] text-text-muted">
          {SA_END_NOTE.eyebrow}
        </span>
        <span className="mb-2 block text-[1.1rem] font-semibold leading-snug text-text">
          {SA_END_NOTE.title}
        </span>
        <span className="mb-4 block text-[0.95rem] leading-relaxed text-text">{SA_END_NOTE.body}</span>
        <span className="inline-block font-mono text-xs font-semibold uppercase tracking-[0.12em] text-text underline decoration-primary decoration-2 underline-offset-4">
          {SA_END_NOTE.cta}
        </span>
      </a>
    </aside>
  );
}
