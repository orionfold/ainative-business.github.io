import type { APIContext } from 'astro';
import { getCollection, type CollectionEntry } from 'astro:content';
import { CHAPTERS, CHAPTER_SLUG_MAP } from '../lib/book/content';
import { SITE } from '../data/seo';
import { publishOrdinals } from '../lib/field-notes/article-order.mjs';

// JSON Feed (https://www.jsonfeed.org/) — a modern, easier-to-parse alternative
// to RSS. Reader apps and answer-engine ingestion pipelines increasingly prefer
// JSON Feed because it doesn't require XML parsing. Includes the same items as
// /feed.xml/ — Field Notes articles plus Book chapters — sorted newest-first.

type FieldNoteEntry = CollectionEntry<'field-notes'>;

export async function GET(context: APIContext) {
  const fieldNotes: FieldNoteEntry[] = await getCollection('field-notes');
  const ordinalById = publishOrdinals(fieldNotes, process.cwd());
  const siteUrl = (context.site ?? new URL(SITE.url)).toString().replace(/\/$/, '');

  const fieldNoteItems = fieldNotes
    .filter((a) => a.data.status !== 'upcoming')
    .map((a) => ({
      id: `${siteUrl}/field-notes/${a.id}/`,
      url: `${siteUrl}/field-notes/${a.id}/`,
      title: a.data.title,
      content_text: a.data.summary,
      summary: a.data.summary,
      date_published: a.data.date.toISOString(),
      authors: [{ name: a.data.author, url: `${siteUrl}/about/` }],
      tags: [
        'Field Notes',
        a.data.stage,
        ...(a.data.series ? [a.data.series] : []),
        ...(a.data.tags ?? []),
      ],
      _ainative: {
        ordinal: ordinalById.get(a.id) ?? 0,
        stage: a.data.stage,
        series: a.data.series ?? null,
      },
    }));

  const chapterItems = CHAPTERS.map((ch) => {
    const slug = CHAPTER_SLUG_MAP[ch.id];
    return {
      id: `${siteUrl}/book/${slug}/`,
      url: `${siteUrl}/book/${slug}/`,
      title: `Chapter ${ch.number}: ${ch.title}`,
      content_text: ch.subtitle ?? '',
      summary: ch.subtitle ?? '',
      date_published: '2026-04-01T00:00:00Z',
      authors: [{ name: 'Manav Sehgal', url: `${siteUrl}/about/` }],
      tags: ['Book', `Part ${ch.part.number}: ${ch.part.title}`],
    };
  });

  const items = [...fieldNoteItems, ...chapterItems].sort(
    (a, b) => new Date(b.date_published).getTime() - new Date(a.date_published).getTime(),
  );

  const feed = {
    version: 'https://jsonfeed.org/version/1.1',
    title: 'AI Native Field Notes',
    home_page_url: `${siteUrl}/`,
    feed_url: `${siteUrl}/feed.json/`,
    description:
      'Field notes, deep-dive papers, and book chapters from ainative — an Orionfold project on building AI-native businesses with open software, custom models, and governed agent orchestration that runs on your own machine.',
    icon: SITE.logo,
    favicon: `${siteUrl}/favicon.ico`,
    language: 'en-us',
    authors: [
      {
        name: 'Manav Sehgal',
        url: `${siteUrl}/about/`,
        avatar: SITE.logo,
      },
    ],
    items,
  };

  return new Response(JSON.stringify(feed, null, 2), {
    headers: {
      'Content-Type': 'application/feed+json; charset=utf-8',
    },
  });
}
