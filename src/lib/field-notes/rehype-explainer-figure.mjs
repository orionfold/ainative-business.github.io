import { visit } from 'unist-util-visit';

const FIGURE_TAGS = new Set(['figure']);

function isWideFigureLike(node) {
  if (!node || node.type !== 'element') return false;
  if (FIGURE_TAGS.has(node.tagName)) return true;
  if (
    node.tagName === 'p' &&
    Array.isArray(node.children) &&
    node.children.filter((c) => c.type !== 'text' || (c.value && c.value.trim())).length === 1 &&
    node.children.find((c) => c.type === 'element' && c.tagName === 'img')
  ) {
    return true;
  }
  return false;
}

function precedesWideFigure(parent, index, lookahead = 3) {
  const limit = Math.min(parent.children.length - 1, index + lookahead);
  for (let i = index + 1; i <= limit; i++) {
    if (isWideFigureLike(parent.children[i])) return true;
  }
  return false;
}

export default function rehypeExplainerFigure() {
  return (tree) => {
    visit(tree, 'element', (node, index, parent) => {
      if (node.tagName !== 'aside') return;
      const cls = node.properties?.className;
      if (!Array.isArray(cls) || !cls.includes('explain')) return;
      if (!parent || index == null) return;
      if (!precedesWideFigure(parent, index)) return;
      if (cls.includes('explain--before-figure')) return;
      cls.push('explain--before-figure');
    });
  };
}
