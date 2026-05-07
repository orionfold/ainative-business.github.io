// Remark plugin: rewrites :::define / :::why / :::deeper / :::pitfall / :::math / :::hardware
// container directives into <aside class="explain explain--<kind>"> nodes.
//
// Authoring syntax:
//   :::define[KV cache]
//   Per-token attention state cached during decode so the model skips
//   recomputing attention over the full context every step.
//   :::
//
// Output (mdast → hast hints — converted to HTML by remark-rehype):
//   <aside class="explain explain--define" id="explain-define-kv-cache"
//          data-explain="define" data-term="KV cache">
//     <p class="explain__title">KV cache</p>
//     <p>Per-token attention state cached during decode...</p>
//   </aside>
//
// Eyebrow label ("DEFINE", "WHY THIS MATTERS", etc.) is injected by CSS
// `::before` content tied to the explain--<kind> class — keeps the AST clean.
//
// As a side effect, every :::define directive is also captured to
// `file.data.glossaryEntries` for callers that re-run this plugin against a
// raw article body (see article-glossary.mjs for that read path).

import { visit, SKIP } from 'unist-util-visit';

const KNOWN = new Set(['define', 'why', 'deeper', 'pitfall', 'math', 'hardware']);

// Reconstruct the original markdown source of a text/leaf directive node so we
// can replace false positives (e.g. `:59 UTC`, `:8001`, `3:2`) with plain text.
// remark-directive parses any `:name` or `::name` regardless of whether name
// starts with a letter or digit — that breaks unrelated prose containing
// timestamps, port numbers, or ratios. This neutralizer runs over text/leaf
// directive nodes whose name is NOT one of our known explainer kinds and
// rebuilds their textual form.
function originalSource(node) {
  const prefix = node.type === 'leafDirective' ? '::' : ':';
  let out = prefix + (node.name ?? '');
  const labelChild = (node.children || []).find((c) => c.data && c.data.directiveLabel);
  if (labelChild) {
    const labelText = (labelChild.children || []).map(mdastToString).join('');
    out += '[' + labelText + ']';
  }
  const attrs = node.attributes || {};
  const keys = Object.keys(attrs);
  if (keys.length) {
    const parts = keys.map((k) => {
      const v = attrs[k];
      if (k === 'id') return '#' + v;
      if (k === 'class') return v.split(/\s+/).map((c) => '.' + c).join('');
      return v == null || v === '' ? k : `${k}="${v}"`;
    });
    out += '{' + parts.join(' ') + '}';
  }
  return out;
}

const slugify = (s) =>
  String(s ?? '')
    .toLowerCase()
    .normalize('NFKD')
    .replace(/[̀-ͯ]/g, '')
    .replace(/[^\w\s-]/g, '')
    .trim()
    .replace(/\s+/g, '-')
    .replace(/-+/g, '-');

function mdastToString(node) {
  if (!node) return '';
  if (typeof node.value === 'string') return node.value;
  if (Array.isArray(node.children)) return node.children.map(mdastToString).join('');
  return '';
}

export default function remarkExplainers() {
  return (tree, file) => {
    const entries = [];
    let counter = 0;

    // Pass 1: neutralize stray text/leaf directives (e.g. `:59` from a
    // timestamp, `:8001` from a port). Replace with plain text so they
    // render as the original prose. Container directives are spared so
    // our `:::name` blocks survive.
    visit(tree, (node, index, parent) => {
      if (!parent || index == null) return;
      if (node.type !== 'textDirective' && node.type !== 'leafDirective') return;
      if (KNOWN.has(node.name)) return;
      parent.children[index] = { type: 'text', value: originalSource(node) };
      return [SKIP, index];
    });

    // Detect mdast siblings within `lookahead` that are wide figure-like
    // blocks: raw-HTML figure/img, or a paragraph that's just an image.
    const FIGURE_HTML_RE = /^\s*<figure[\s>]/i;
    const IMG_HTML_RE = /^\s*<img[\s>]/i;
    function precedesFigure(parent, index, lookahead = 3) {
      const limit = Math.min(parent.children.length - 1, index + lookahead);
      for (let i = index + 1; i <= limit; i++) {
        const s = parent.children[i];
        if (!s) continue;
        if (s.type === 'html' && (FIGURE_HTML_RE.test(s.value) || IMG_HTML_RE.test(s.value))) return true;
        if (s.type === 'paragraph' && Array.isArray(s.children)) {
          const meaningful = s.children.filter((c) => c.type !== 'text' || (c.value && c.value.trim()));
          if (meaningful.length === 1 && meaningful[0].type === 'image') return true;
        }
      }
      return false;
    }

    visit(tree, (node, index, parent) => {
      if (node.type !== 'containerDirective') return;
      if (!KNOWN.has(node.name)) return;

      const data = node.data || (node.data = {});
      const children = node.children || [];

      // First child marked with data.directiveLabel === true holds the
      // bracketed label (e.g. [KV cache]). Style it as the title element.
      const labelNode = children.find((c) => c.data && c.data.directiveLabel);
      const labelText = labelNode ? mdastToString(labelNode).trim() : '';

      counter += 1;
      const anchor = labelText
        ? `explain-${node.name}-${slugify(labelText)}`
        : `explain-${node.name}-${counter}`;

      if (labelNode) {
        labelNode.data = labelNode.data || {};
        labelNode.data.hName = 'p';
        labelNode.data.hProperties = { className: ['explain__title'] };
      }

      data.hName = 'aside';
      const className = ['explain', `explain--${node.name}`];
      if (parent && index != null && precedesFigure(parent, index)) {
        className.push('explain--before-figure');
      }
      const props = {
        id: anchor,
        className,
        'data-explain': node.name,
      };
      if (labelText) props['data-term'] = labelText;
      data.hProperties = props;

      if (node.name === 'define' && labelText) {
        const bodyChildren = children.filter((c) => !(c.data && c.data.directiveLabel));
        const definitionText = bodyChildren.map(mdastToString).join(' ').replace(/\s+/g, ' ').trim();
        entries.push({ term: labelText, anchor, definitionText });
      }
    });

    file.data = file.data || {};
    file.data.glossaryEntries = entries;
  };
}
