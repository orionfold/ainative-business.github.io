// Shared markdown renderer for the Arena islands (ChatLane, CompareDuel, Lab).
//
// Extracted verbatim from ChatLane's original module-level block so every
// streaming surface renders assistant output identically: GitHub-flavored
// markdown via `marked`, code blocks syntax-highlit by a focused highlight.js
// subset (keeps the island bundle ~12 kB gz vs ~150 kB for the full set), and
// the result sanitized through DOMPurify. The emitted `.hljs-*` spans are
// painted by the OKLCH token theme in ArenaAppLayout (`.chat-markdown .hljs-*`).
//
// `marked.setOptions` is global — both consumers want {gfm, breaks}, so a
// single shared setup is correct. If a future consumer needs different options,
// switch to a per-call `marked.parse(content, opts)` instead of the global.

import { marked } from 'marked';
import DOMPurify from 'dompurify';
import hljs from 'highlight.js/lib/core';

// Lazy-register a focused subset of languages — keeps the island bundle small.
import python from 'highlight.js/lib/languages/python';
import bash from 'highlight.js/lib/languages/bash';
import javascript from 'highlight.js/lib/languages/javascript';
import typescript from 'highlight.js/lib/languages/typescript';
import json from 'highlight.js/lib/languages/json';
import yaml from 'highlight.js/lib/languages/yaml';
import sql from 'highlight.js/lib/languages/sql';
import rust from 'highlight.js/lib/languages/rust';

hljs.registerLanguage('python', python);
hljs.registerLanguage('bash', bash);
hljs.registerLanguage('sh', bash);
hljs.registerLanguage('shell', bash);
hljs.registerLanguage('javascript', javascript);
hljs.registerLanguage('js', javascript);
hljs.registerLanguage('typescript', typescript);
hljs.registerLanguage('ts', typescript);
hljs.registerLanguage('json', json);
hljs.registerLanguage('yaml', yaml);
hljs.registerLanguage('yml', yaml);
hljs.registerLanguage('sql', sql);
hljs.registerLanguage('rust', rust);
hljs.registerLanguage('rs', rust);

// Custom code renderer — uses hljs.highlight() when the lang is registered,
// falls back to plaintext otherwise. Outputs spans with .hljs-* class names
// which our ArenaAppLayout OKLCH theme paints.
const renderer = new marked.Renderer();
renderer.code = function ({ text, lang } = {}) {
  const codeText = String(text ?? '');
  let highlighted;
  let langClass = lang ? ` language-${lang}` : '';
  try {
    if (lang && hljs.getLanguage(lang)) {
      highlighted = hljs.highlight(codeText, { language: lang, ignoreIllegals: true }).value;
    } else {
      highlighted = escapeHtml(codeText);
    }
  } catch (_e) {
    highlighted = escapeHtml(codeText);
  }
  return `<pre><code class="hljs${langClass}">${highlighted}</code></pre>`;
};

marked.setOptions({
  gfm: true,
  breaks: true,
  renderer,
});

export function escapeHtml(s) {
  return String(s)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

export function renderMarkdown(content) {
  try {
    const raw = marked.parse(String(content || ''));
    return DOMPurify.sanitize(raw);
  } catch (_e) {
    return escapeHtml(content || '');
  }
}
