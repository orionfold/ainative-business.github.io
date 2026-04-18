import rss from '@astrojs/rss';
import type { APIContext } from 'astro';
import { CHAPTERS, CHAPTER_SLUG_MAP } from '../lib/book/content';
import { SITE } from '../data/seo';

type ResearchFrontmatter = {
  title: string;
  description: string;
  datePublished: string;
  dateModified?: string;
  author?: string;
  canonical?: string;
};

const researchModules = import.meta.glob<{ frontmatter: ResearchFrontmatter; url?: string }>(
  '../pages/research/*.mdx',
  { eager: true },
);

export async function GET(context: APIContext) {
  const researchItems = Object.values(researchModules).map((mod) => ({
    title: mod.frontmatter.title,
    description: mod.frontmatter.description,
    pubDate: new Date(mod.frontmatter.datePublished),
    link: mod.frontmatter.canonical ?? mod.url ?? '/research/',
    categories: ['Research'],
  }));

  const chapterItems = CHAPTERS.map((ch) => {
    const slug = CHAPTER_SLUG_MAP[ch.id];
    return {
      title: `Chapter ${ch.number}: ${ch.title}`,
      description: ch.subtitle ?? '',
      pubDate: new Date('2026-04-01'),
      link: `/book/${slug}/`,
      categories: ['Book', `Part ${ch.part.number}: ${ch.part.title}`],
    };
  });

  const items = [...researchItems, ...chapterItems].sort(
    (a, b) => b.pubDate.getTime() - a.pubDate.getTime(),
  );

  return rss({
    title: 'AI Native research',
    description:
      'Research papers and book chapters from ainative — a personal research project by Manav Sehgal on building AI-native businesses with governed agent orchestration.',
    site: context.site ?? SITE.url,
    items,
    customData: '<language>en-us</language>',
    stylesheet: false,
  });
}
