import type { ImageMetadata } from 'astro';

// Product screenshots are stored in the content `screenshot:` field as dynamic
// strings (e.g. "screenshots/01-cockpit.png") rather than static imports, so they
// can't be handed to <Image> directly. Eagerly glob every screenshot at build time
// — files live at repo-root products/<slug>/screenshots/ (NOT in public/, so Vite
// can optimize them; the public/ mirror is left untouched for the arena-demo
// drift-guard + the orionfold.com sync). Lets components resolve a string → the
// optimizable ImageMetadata and emit responsive WebP.
const screenshots = import.meta.glob<{ default: ImageMetadata }>(
  '/products/*/screenshots/*.{png,jpg,jpeg,webp,avif}',
  { eager: true },
);

/**
 * Resolve a product screenshot string to optimizable ImageMetadata.
 * Accepts the bare relative form ("screenshots/x.png"), a slash-prefixed form,
 * or a full "products/<slug>/screenshots/x.png" path. Returns undefined if the
 * file isn't present so callers can fall back to the raw /public URL.
 */
export function productScreenshot(slug: string, screenshot: string): ImageMetadata | undefined {
  const rel = screenshot.replace(/^\/+/, '').replace(new RegExp(`^products/${slug}/`), '');
  return screenshots[`/products/${slug}/${rel}`]?.default;
}
