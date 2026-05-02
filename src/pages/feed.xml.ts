import rss from '@astrojs/rss';
import type { APIContext } from 'astro';
import { getCollection, type CollectionEntry } from 'astro:content';
import { CHAPTERS, CHAPTER_SLUG_MAP } from '../lib/book/content';
import { SITE } from '../data/seo';

type FieldNoteEntry = CollectionEntry<'field-notes'>;

// Site-wide feed at /feed.xml — replaces the legacy /rss.xml endpoint as the
// canonical RSS source. Includes Field Notes articles, Book chapters, and
// the AI Native Platform series papers (which now live inside Field Notes).
//
// Sort order: most recent publication date first. The Field Notes collection
// drives recency for the editorial side; book chapters get a fixed pubDate.
export async function GET(context: APIContext) {
  const fieldNotes: FieldNoteEntry[] = await getCollection('field-notes');
  const fieldNoteItems = fieldNotes
    .filter((a: FieldNoteEntry) => a.data.status !== 'upcoming')
    .map((a: FieldNoteEntry) => ({
      title: a.data.title,
      description: a.data.summary,
      pubDate: a.data.date,
      link: `/field-notes/${a.id}/`,
      categories: [
        'Field Notes',
        a.data.stage,
        ...(a.data.series ? [a.data.series] : []),
      ],
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

  const items = [...fieldNoteItems, ...chapterItems].sort(
    (a, b) => b.pubDate.getTime() - a.pubDate.getTime(),
  );

  return rss({
    title: 'AI Native Field Notes',
    description:
      'Field notes, deep-dive papers, and book chapters from ainative — a personal research project by Manav Sehgal on building AI-native businesses with governed agent orchestration.',
    site: context.site ?? SITE.url,
    items,
    customData: '<language>en-us</language>',
    stylesheet: false,
  });
}
