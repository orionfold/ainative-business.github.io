import { visit } from 'unist-util-visit';

// rehype-caption
// Tags paragraphs whose visible content is a single <em> with a `caption`
// class. Runs after Remark → Rehype so the tree is hast (HTML AST).
//
// Why: markdown convention `*caption*` on its own paragraph produces a hast
// `<p><em>…</em></p>`. CSS `p > em:only-child` would fire for inline emphasis
// too (CSS `:only-child` ignores text-node siblings), so we move the
// detection up into the AST where we can see text nodes and whitespace.
//
// Rule: the paragraph qualifies when, ignoring whitespace-only text nodes,
// its children collapse to exactly one <em> element. That em's contents are
// then lifted into the paragraph and the paragraph gets class "caption" —
// keeping the DOM flat (no redundant <em> inside a styled <p>).
export default function rehypeCaption() {
  return (tree) => {
    visit(tree, 'element', (node) => {
      if (node.tagName !== 'p') return;

      const meaningful = node.children.filter((child) => {
        if (child.type === 'text') return child.value.trim().length > 0;
        return true;
      });
      if (meaningful.length !== 1) return;

      const only = meaningful[0];
      if (only.type !== 'element' || only.tagName !== 'em') return;

      const existing = (node.properties && node.properties.className) || [];
      const classes = Array.isArray(existing) ? existing : [existing];
      node.properties = {
        ...(node.properties || {}),
        className: [...classes, 'caption'],
      };
      node.children = only.children;
    });
  };
}
