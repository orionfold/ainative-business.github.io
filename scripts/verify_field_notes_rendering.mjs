/**
 * Post-build verifier: enforces the article-body explainer float contract on
 * every field-notes page. Walks dist/field-notes/<slug>/index.html.
 *
 * Why this exists. On wide viewports explainer asides float into the gutter
 * (src/styles/explainers.css). A float needs following content to wrap it;
 * an explainer whose next significant sibling can't wrap a float orphans in
 * the gutter with empty prose beside it. rehype-explainer-figure.mjs tags
 * those cases so the CSS can un-float them:
 *   - next significant sibling is another explainer → `explain--before-explainer`
 *   - next significant sibling is a wide figure       → `explain--before-figure`
 *
 * This check asserts the tag is present whenever the structural condition
 * holds, so a regression in the plugin or CSS fails the build instead of
 * silently shipping an orphaned float (the bug that hit
 * `the-hermes-harness-on-spark`'s `:::why[NIM-first]` explainer). It is
 * viewport-independent: it verifies the markup invariant, not the layout.
 *
 * Adjacency = whitespace/comment-only gap between one explainer's `</aside>`
 * and the next element — the same "next significant sibling" definition the
 * plugin uses. The figure half asserts only on an immediately-following
 * `<figure>` (the unambiguous subset); the plugin's wider image-only-<p>
 * lookahead is intentionally not re-derived here to keep the check free of
 * false positives.
 *
 * Exit code = number of failed checks. Non-zero blocks the build.
 */
import { readdir, readFile } from 'node:fs/promises';
import { existsSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const distDir = join(dirname(fileURLToPath(import.meta.url)), '..', 'dist');
const fieldNotesDir = join(distDir, 'field-notes');

const failures = [];
const stats = { pagesChecked: 0, asidesChecked: 0 };

function recordFailure(file, rule, detail) {
  failures.push({ file: file.replace(distDir + '/', ''), rule, detail });
}

function classListOf(openTag) {
  const m = openTag.match(/\bclass="([^"]*)"/i);
  return m ? m[1].split(/\s+/).filter(Boolean) : [];
}

function idOf(openTag) {
  const m = openTag.match(/\bid="([^"]*)"/i);
  return m ? m[1] : '(no id)';
}

function isExplainerOpenTag(openTag) {
  return /^<aside\b/i.test(openTag) && classListOf(openTag).includes('explain');
}

// Strip leading whitespace and HTML comments, then classify the element that
// begins the remaining markup: { kind, openTag } where kind is
// 'explainer' | 'figure' | 'other' | 'end'.
function nextSignificantElement(html, fromIdx) {
  let rest = html.slice(fromIdx);
  for (;;) {
    rest = rest.replace(/^\s+/, '');
    if (rest.startsWith('<!--')) {
      const end = rest.indexOf('-->');
      if (end === -1) return { kind: 'end' };
      rest = rest.slice(end + 3);
      continue;
    }
    break;
  }
  if (!rest.startsWith('<')) return rest ? { kind: 'other' } : { kind: 'end' };
  const tagMatch = rest.match(/^<[^>]*>/);
  if (!tagMatch) return { kind: 'other' };
  const openTag = tagMatch[0];
  if (isExplainerOpenTag(openTag)) return { kind: 'explainer', openTag };
  if (/^<figure\b/i.test(openTag)) return { kind: 'figure', openTag };
  return { kind: 'other', openTag };
}

function checkPage(file, html) {
  stats.pagesChecked += 1;
  for (const m of html.matchAll(/<aside\b[^>]*>/gi)) {
    const openTag = m[0];
    if (!isExplainerOpenTag(openTag)) continue;
    stats.asidesChecked += 1;

    // Explainer asides never nest, so the matching close is the next </aside>.
    const openEnd = m.index + openTag.length;
    const closeIdx = html.indexOf('</aside>', openEnd);
    if (closeIdx === -1) continue;
    const afterClose = closeIdx + '</aside>'.length;

    const cls = classListOf(openTag);
    const id = idOf(openTag);
    const next = nextSignificantElement(html, afterClose);

    if (next.kind === 'explainer' && !cls.includes('explain--before-explainer')) {
      recordFailure(
        file,
        'orphaned-float-before-explainer',
        `Explainer #${id} is immediately followed by another explainer but is missing ` +
          `\`explain--before-explainer\`; on wide viewports it floats into the gutter with ` +
          `no prose to wrap it. Tagging is rehype-explainer-figure.mjs's job — check the plugin.`,
      );
    }
    if (next.kind === 'figure' && !cls.includes('explain--before-figure')) {
      recordFailure(
        file,
        'orphaned-float-before-figure',
        `Explainer #${id} is immediately followed by a <figure> but is missing ` +
          `\`explain--before-figure\`; on wide viewports it floats into the gutter beside the figure. ` +
          `Tagging is rehype-explainer-figure.mjs's job — check the plugin.`,
      );
    }
  }
}

async function main() {
  if (!existsSync(fieldNotesDir)) {
    console.log('[verify_field_notes_rendering] no dist/field-notes/ — nothing to check.');
    process.exit(0);
  }

  const entries = await readdir(fieldNotesDir, { withFileTypes: true });
  for (const e of entries) {
    if (!e.isDirectory()) continue;
    const idx = join(fieldNotesDir, e.name, 'index.html');
    if (!existsSync(idx)) continue;
    const html = await readFile(idx, 'utf8');
    checkPage(idx, html);
  }

  console.log(
    `\n[verify_field_notes_rendering] Checked ${stats.asidesChecked} explainer(s) across ${stats.pagesChecked} field-notes page(s).`,
  );

  if (failures.length === 0) {
    console.log('[verify_field_notes_rendering] ✓ No orphaned floated explainers.');
    process.exit(0);
  }

  console.error(`\n[verify_field_notes_rendering] ✗ ${failures.length} explainer float violation(s):\n`);
  const byRule = {};
  for (const f of failures) (byRule[f.rule] ??= []).push(f);
  for (const [rule, items] of Object.entries(byRule)) {
    console.error(`  ${rule} (${items.length}):`);
    for (const i of items) console.error(`    - ${i.file}\n        ${i.detail}`);
  }
  process.exit(failures.length);
}

main().catch((err) => {
  console.error('[verify_field_notes_rendering] crashed:', err);
  process.exit(99);
});
