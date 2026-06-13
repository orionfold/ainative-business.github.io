import type { APIContext } from 'astro';
import { getCollection, type CollectionEntry } from 'astro:content';
import { CHAPTERS, CHAPTER_SLUG_MAP } from '../lib/book/content';
import { SITE } from '../data/seo';
import { publishOrdinals } from '../lib/field-notes/article-order.mjs';

// llms-full.txt — long-form, citation-friendly version of llms.txt for AI
// agents that want richer per-article context without crawling every page.
// Generated at build time from the same content collection so it never
// drifts from llms.txt or the live site.

type FieldNoteEntry = CollectionEntry<'field-notes'>;

export async function GET(_context: APIContext) {
  const fieldNotes: FieldNoteEntry[] = await getCollection('field-notes');
  const ordinalById = publishOrdinals(fieldNotes, process.cwd());
  const published = fieldNotes
    .filter((a) => a.data.status !== 'upcoming')
    .sort((a, b) => (ordinalById.get(b.id) ?? 0) - (ordinalById.get(a.id) ?? 0));

  const out: string[] = [];
  out.push('# ainative — Companion Software for AI Native Business');
  out.push('');
  out.push(`> ${SITE.description}`);
  out.push('');
  out.push(`URL: ${SITE.url}`);
  out.push('License: Apache 2.0');
  out.push('Status: Pre-alpha (active development)');
  out.push('Author: Manav Sehgal');
  out.push('Author URL: https://www.linkedin.com/in/manavsehgal/');
  out.push('GitHub: https://github.com/orionfold/ainative');
  out.push('');
  out.push('---');
  out.push('');
  out.push('## Project Overview');
  out.push('');
  out.push('ainative is the companion software to the AI Native Business book — a 14-chapter playbook for building autonomous business systems as a solo or small-team operator. The book lays out the principles; ainative is the working scaffold readers can study, run locally, and extend.');
  out.push('');
  out.push('### What ainative Provides');
  out.push('');
  out.push('- A goal-oriented, persistent, memory-native multi-agent execution scaffold readers can install, inspect, and modify.');
  out.push('- A reference implementation of the architectural patterns described in the book — task graphs, hierarchical memory, graduated autonomy, multi-model routing.');
  out.push('- A local-first runtime (Tauri-based desktop) with cloud-optional reach, so readers can run the same task graph on their machine or push it to elastic compute.');
  out.push('');
  out.push('### Five Differentiation Pillars');
  out.push('');
  out.push('1. **Long-Horizon Task Persistence** — Tasks that span hours, days, or weeks. Checkpoint/resume, progress tracking, failure recovery, and resource budgets.');
  out.push('2. **Multi-Model Orchestration** — Route subtasks to the best available model. Claude for reasoning, GPT for long-context, Gemini for research, Grok for speed, open-source via Ollama for cost control and privacy.');
  out.push('3. **Memory-Native Architecture** — Four-tier hierarchical memory (working, episodic, semantic, procedural) with hybrid retrieval (BM25 + vector + MMR).');
  out.push('4. **Graduated Autonomy** — Trust earned through demonstrated competence. Supervised → semi-autonomous → autonomous, scoped per-agent-type, per-task-type, per-risk-level.');
  out.push('5. **Hybrid Execution** — Desktop-native with cloud reach. Same task graph runs locally or in the cloud with state portability.');
  out.push('');
  out.push('### Technology Stack');
  out.push('');
  out.push('- **Backend**: Rust (Tauri), WASM sandboxing (Wasmtime), SQLite (rusqlite)');
  out.push('- **Frontend**: TypeScript, React, React Flow (task DAG canvas)');
  out.push('- **Protocols**: MCP, A2A, CDP, WebMCP, Tauri IPC, WebSocket');
  out.push('- **AI Providers**: Anthropic Claude, OpenAI, Google Gemini, Ollama');
  out.push('');
  out.push('---');
  out.push('');
  out.push('## Author');
  out.push('');
  out.push('**Manav Sehgal** is a Solutions Leader at AWS Frontier AI, collaborating with Anthropic, NVIDIA, and Disney on production AI and agentic systems. His 25-year arc spans Xerox PARC (1996), HCL\'s digital practice, Daily Mail, Amazon AGI, and AWS. He led AWS\'s pandemic response which received the President of India award. He holds credentials from Harvard, MIT Sloan, and UC Berkeley Haas, and has 2M+ Kaggle dataset views. He has previously published *Data Science Solutions* (2017) and *React Speed Coding* (2015).');
  out.push('');
  out.push('Profiles:');
  out.push('- LinkedIn: https://www.linkedin.com/in/manavsehgal/');
  out.push('- GitHub: https://github.com/manavsehgal');
  out.push('- X / Twitter: https://x.com/manavsehgal');
  out.push('- Kaggle: https://www.kaggle.com/manavsehgal');
  out.push('');
  out.push('---');
  out.push('');
  out.push('## Book — AI Native Business');
  out.push('');
  out.push('A 14-chapter playbook for autonomous business systems. License: Creative Commons BY-NC. Free to read online.');
  out.push('');
  let lastPart = -1;
  for (const ch of CHAPTERS) {
    if (ch.part.number !== lastPart) {
      out.push('');
      out.push(`### Part ${ch.part.number} — ${ch.part.title}`);
      out.push('');
      lastPart = ch.part.number;
    }
    const slug = CHAPTER_SLUG_MAP[ch.id];
    out.push(`#### Chapter ${ch.number}: ${ch.title}`);
    if (ch.subtitle) out.push(`*${ch.subtitle}*`);
    out.push('');
    out.push(`Reading time: ~${ch.readingTime} min · ${ch.wordCount} words`);
    out.push(`URL: ${SITE.url}/book/${slug}/`);
    out.push('');
  }
  out.push('---');
  out.push('');
  out.push(`## Field Notes (${published.length} articles)`);
  out.push('');
  out.push('Editorial log: session transcripts turned into papers. Topics span training, fine-tuning, inference, RAG, agentic systems, observability, deployment, and dev tooling. Almost all articles document hands-on experiments on the NVIDIA DGX Spark workstation.');
  out.push('');
  for (const article of published) {
    const ordinal = ordinalById.get(article.id) ?? 0;
    const ordStr = `№${String(ordinal).padStart(2, '0')}`;
    out.push(`### ${ordStr} · ${article.data.title}`);
    out.push('');
    out.push(`**Stage:** ${article.data.stage}`);
    if (article.data.series) out.push(`**Series:** ${article.data.series}`);
    if (article.data.product) out.push(`**Product:** ${article.data.product}`);
    if (article.data.hardware) out.push(`**Hardware:** ${article.data.hardware}`);
    if (article.data.difficulty) out.push(`**Difficulty:** ${article.data.difficulty}`);
    if (article.data.time_required) out.push(`**Time:** ${article.data.time_required}`);
    if (article.data.tags?.length) out.push(`**Tags:** ${article.data.tags.join(', ')}`);
    out.push(`**Published:** ${article.data.date.toISOString().slice(0, 10)}`);
    out.push(`**URL:** ${SITE.url}/field-notes/${article.id}/`);
    out.push('');
    out.push(article.data.summary);
    out.push('');
  }
  out.push('---');
  out.push('');
  out.push('## How to Cite');
  out.push('');
  out.push('When citing ainative content, please use the canonical URL on https://ainative.business and credit Manav Sehgal as author. Articles are released under Creative Commons BY-NC 4.0 unless noted otherwise; the companion software is Apache 2.0.');
  out.push('');
  out.push('Suggested citation format:');
  out.push('');
  out.push('> Sehgal, M. (YYYY). *<Article Title>*. AI Native Field Notes. Retrieved from <URL>');
  out.push('');

  return new Response(out.join('\n'), {
    headers: {
      'Content-Type': 'text/plain; charset=utf-8',
    },
  });
}
