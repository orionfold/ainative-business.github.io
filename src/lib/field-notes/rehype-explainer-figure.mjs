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

function isExplainerAside(node) {
  if (!node || node.type !== 'element' || node.tagName !== 'aside') return false;
  const cls = node.properties?.className;
  return Array.isArray(cls) && cls.includes('explain');
}

// True when the next significant sibling (skipping whitespace-only text) is
// itself an explainer aside — i.e. there is no prose between this explainer
// and the next. A float here has nothing to wrap, so it orphans in the gutter
// with empty prose beside it (the abutting aside clears the float and drops
// below). Mirrors precedesWideFigure: same "next sibling can't wrap a float"
// condition, with another explainer in place of a figure.
function abutsFollowingExplainer(parent, index) {
  for (let i = index + 1; i < parent.children.length; i++) {
    const sib = parent.children[i];
    if (sib.type === 'text' && (!sib.value || !sib.value.trim())) continue;
    return isExplainerAside(sib);
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

      if (precedesWideFigure(parent, index) && !cls.includes('explain--before-figure')) {
        cls.push('explain--before-figure');
      }
      if (abutsFollowingExplainer(parent, index) && !cls.includes('explain--before-explainer')) {
        cls.push('explain--before-explainer');
      }
    });
  };
}
