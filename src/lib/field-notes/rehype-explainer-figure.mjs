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

function extractText(node) {
  if (!node) return '';
  if (node.type === 'text') return node.value || '';
  if (!Array.isArray(node.children)) return '';
  let s = '';
  for (const c of node.children) s += extractText(c);
  return s;
}

// True when the next explainer aside is close enough that a float here would
// orphan. Two cases:
//   (a) Strict adjacency: the next significant sibling is itself an explainer
//       (no prose between). A float has nothing to wrap, so it sits in the
//       gutter with empty prose beside it.
//   (b) Short-wrap: an explainer is reachable within MAX_INTERVENING prose
//       elements AND MAX_PROSE_CHARS characters. The intervening prose is
//       too short to absorb the float's height; the next explainer (often
//       already inline via the trailing-pair rule or `--before-explainer`)
//       has to clear the still-floating aside and drops below, leaving a
//       visible whitespace gap on the prose side of the article.
// Threshold rationale: a single ~1200-char prose paragraph wraps at roughly
// 8–10 lines around a 13–17rem floated aside; explainer asides commonly
// reach 12–18 lines at their narrowest, so 1 paragraph is rarely enough.
// MAX_INTERVENING=1 stays conservative: only catches single-paragraph
// gaps, never multi-paragraph runs where wrapping works fine.
function abutsFollowingExplainer(parent, index) {
  const MAX_INTERVENING = 1;
  const MAX_PROSE_CHARS = 1200;
  let proseElements = 0;
  let proseChars = 0;
  for (let i = index + 1; i < parent.children.length; i++) {
    const sib = parent.children[i];
    if (sib.type === 'text') {
      if (sib.value && sib.value.trim()) proseChars += sib.value.length;
      continue;
    }
    if (sib.type !== 'element') continue;
    if (isExplainerAside(sib)) return true;
    proseElements += 1;
    proseChars += extractText(sib).length;
    if (proseElements > MAX_INTERVENING) return false;
    if (proseChars > MAX_PROSE_CHARS) return false;
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
