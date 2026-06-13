import type { APIContext } from 'astro';
import { getCollection, type CollectionEntry } from 'astro:content';
import { CHAPTERS, CHAPTER_SLUG_MAP } from '../lib/book/content';
import { SITE } from '../data/seo';
import { publishOrdinals } from '../lib/field-notes/article-order.mjs';

// llms.txt — a curated, human-readable site map for LLM agents and answer
// engines (Perplexity, ChatGPT, Claude, Google AI Overviews). Spec from
// https://llmstxt.org/. Generated at build time so it stays in sync with
// the content collection — no manual maintenance.
//
// Sibling /llms-full.txt is the longer, citation-friendly version and is
// served from llms-full.txt.ts.

type FieldNoteEntry = CollectionEntry<'field-notes'>;

export async function GET(_context: APIContext) {
  const fieldNotes: FieldNoteEntry[] = await getCollection('field-notes');
  const ordinalById = publishOrdinals(fieldNotes, process.cwd());
  const published = fieldNotes
    .filter((a) => a.data.status !== 'upcoming')
    .sort((a, b) => (ordinalById.get(b.id) ?? 0) - (ordinalById.get(a.id) ?? 0));

  const lines: string[] = [];
  lines.push('# ainative');
  lines.push('');
  lines.push(`> ${SITE.description}`);
  lines.push('');
  lines.push('## About');
  lines.push('');
  lines.push('ainative is the companion software for the AI Native Business book by Manav Sehgal — a 14-chapter playbook for building autonomous business systems. The runtime is local-first (Tauri), open source (Apache 2.0), and free.');
  lines.push('');
  lines.push('### Five Differentiation Pillars');
  lines.push('');
  lines.push('1. **Long-Horizon Task Persistence** — Tasks that survive beyond sessions with checkpoint/resume, progress tracking, failure recovery, and per-task resource budgets.');
  lines.push('2. **Multi-Model Orchestration** — Routes subtasks to the best available model (Claude, GPT, Gemini, Grok, Ollama) based on measured performance.');
  lines.push('3. **Memory-Native Architecture** — Four-tier hierarchical memory (working, episodic, semantic, procedural) with hybrid retrieval (BM25 + vector + MMR).');
  lines.push('4. **Graduated Autonomy** — Trust earned through demonstrated competence. Supervised → semi-autonomous → autonomous, scoped per-agent-type and per-risk-level.');
  lines.push('5. **Hybrid Execution** — Desktop-native with cloud reach. Same task graph runs locally or in the cloud with state portability.');
  lines.push('');
  lines.push('### Status');
  lines.push('');
  lines.push('- License: Apache 2.0');
  lines.push('- Stage: Pre-alpha (active development)');
  lines.push('- Author: Manav Sehgal');
  lines.push('');
  lines.push('## Documentation');
  lines.push('');
  lines.push(`- [Homepage](${SITE.url}/): Book + companion software overview, architecture, research`);
  lines.push(`- [The Book](${SITE.url}/book/): AI Native Business — the 14-chapter playbook`);
  lines.push(`- [Field Notes](${SITE.url}/field-notes/): Running editorial log — ${published.length} published articles`);
  lines.push(`- [About](${SITE.url}/about/): Manav Sehgal — author bio, credentials, and contact`);
  lines.push(`- [Projects](${SITE.url}/projects/): 25-year project portfolio across five technology waves`);
  lines.push(`- [Docs](${SITE.url}/docs/): Reference for the companion software — agents, tasks, workflows, memory, governance`);
  lines.push(`- [API Reference](${SITE.url}/docs/api/): REST and local API surface for ainative-business`);
  lines.push(`- [Fieldkit](${SITE.url}/fieldkit/): Open-source CLI for AI-native infrastructure on workstations`);
  lines.push('');
  lines.push('## Book Chapters');
  lines.push('');
  let lastPart = -1;
  for (const ch of CHAPTERS) {
    if (ch.part.number !== lastPart) {
      lines.push(`### Part ${ch.part.number} — ${ch.part.title}`);
      lastPart = ch.part.number;
    }
    const slug = CHAPTER_SLUG_MAP[ch.id];
    const sub = ch.subtitle ? `: ${ch.subtitle}` : '';
    lines.push(`- [Ch ${ch.number}: ${ch.title}](${SITE.url}/book/${slug}/)${sub ? ` —${sub}` : ''}`);
  }
  lines.push('');
  lines.push(`## Field Notes (${published.length} articles)`);
  lines.push('');
  lines.push('Editorial log of building AI-native infrastructure on a workstation. Each article is a session transcript turned into a paper — covering training, fine-tuning, inference, RAG, agentic loops, observability, and dev tools.');
  lines.push('');
  for (const article of published) {
    const ordinal = ordinalById.get(article.id) ?? 0;
    const ordStr = `№${String(ordinal).padStart(2, '0')}`;
    lines.push(`- [${ordStr} · ${article.data.title}](${SITE.url}/field-notes/${article.id}/): ${article.data.summary}`);
  }
  lines.push('');
  lines.push('## Source Code');
  lines.push('');
  lines.push('- [GitHub Repository](https://github.com/orionfold/ainative)');
  lines.push('');
  lines.push('## Optional');
  lines.push('');
  lines.push(`- [Sitemap](${SITE.url}/sitemap-index.xml)`);
  lines.push(`- [RSS feed](${SITE.url}/feed.xml/): All field notes + book chapters`);
  lines.push(`- [JSON Feed](${SITE.url}/feed.json/): Modern alternative to RSS`);
  lines.push(`- [llms-full.txt](${SITE.url}/llms-full.txt): Long-form, citation-friendly site overview for AI agents`);
  lines.push('');

  return new Response(lines.join('\n'), {
    headers: {
      'Content-Type': 'text/plain; charset=utf-8',
    },
  });
}
