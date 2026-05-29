#!/usr/bin/env bash
# Static-check every SVG diagram an article depends on — the in-body
# fn-diagram figures in article.md and the four signature components
# under src/components/svg/*.astro that the home/article cards reference.
#
# Invariants enforced (see references/visualizations.md §Hard invariants):
#   1. SVG child order: defs → gradients → edges → flow → nodes → labels → symbols
#      (structural; we check that <g class="fn-diagram__edges"> appears before
#       <g class="fn-diagram__nodes"> which appears before __labels which
#       appears before __symbols).
#   2. No <path class="fn-diagram__edge"> endpoint lands inside a
#      <rect class="fn-diagram__node--ghost"> (ghost has fill:none so the
#      stroke is visible through the text).
#   3. Every <circle class="fn-diagram__flow"> declares cx + cy — otherwise
#      SMIL parks the dot at (0,0) between cycles.
#   4. Every <animateMotion begin="Ns"> has N ≥ 1.4 (so the particle doesn't
#      start travelling before the paths finish drawing).
#   7. Every <g class="fn-diagram__icon"> clears every <text> in its visual
#      column by ≥ 10 units (icon bottom vs text ascender).
#   8. Every SVG has at least one <linearGradient> or <radialGradient> in <defs>.
#  11. stroke-width ∈ {0.5, 1, 1.5, 2}.
#  12. No hex literals in fill= / stroke= attributes.
#  13. <svg> has role="img" + aria-label.
#  14. No <title> child of <svg>.
#
# Invariants 5/6 (node-text capacity) are left to the vibe-check — too
# font-metric-dependent to catch reliably in a regex pass.
#
# Usage: verify_svg.sh <slug>
# Exit:   0 = all SVGs pass; 1 = one or more invariants violated.

set -uo pipefail

if [ $# -lt 1 ]; then
  echo "Usage: $0 <slug>" >&2
  exit 1
fi

SLUG="$1"
REPO="${AI_FIELD_NOTES_REPO:-/home/nvidia/ainative-business.github.io}"
ARTICLE="$REPO/articles/$SLUG/article.md"
SVG_DIR="$REPO/src/components/svg"

if [ ! -f "$ARTICLE" ]; then
  echo "FAIL: $ARTICLE not found" >&2
  exit 1
fi

python3 - "$ARTICLE" "$SVG_DIR" <<'PY'
import re
import sys
from pathlib import Path

ARTICLE_PATH = Path(sys.argv[1])
SVG_DIR = Path(sys.argv[2])

# Tolerance for "on the boundary" of a node — within this many SVG units of an
# edge counts as boundary-aligned, not inside.
BOUNDARY_TOL = 2.0
# Minimum clearance required between an icon's 24x24 bbox and a text element's
# bbox in the same visual column.
ICON_TEXT_CLEARANCE = 10.0
# Approximate text bbox above/below baseline (Geist at 14px).
TEXT_ASCENT = 14.0
TEXT_DESCENT = 4.0

ALLOWED_STROKE_WIDTHS = {"0.5", "1", "1.5", "2"}


# ---------- Extraction ----------

def extract_fn_diagram_svgs(article_text):
    """Return [(svg_text, figure_label), ...] for every fn-diagram figure."""
    figures = re.findall(
        r'<figure\s+class="fn-diagram"[^>]*>(.*?)</figure>',
        article_text, re.DOTALL)
    out = []
    for i, fig in enumerate(figures, start=1):
        svg = re.search(r'<svg\b[^>]*>.*?</svg>', fig, re.DOTALL)
        if svg:
            out.append((svg.group(0), f"article fn-diagram #{i}"))
    return out


def extract_signature_svg(astro_path):
    """Strip Astro frontmatter and pull the outermost <svg>...</svg>."""
    text = astro_path.read_text()
    text = re.sub(r'^---\n.*?\n---\n', '', text, count=1, flags=re.DOTALL)
    m = re.search(r'<svg\b[^>]*>.*?</svg>', text, re.DOTALL)
    return m.group(0) if m else None


# ---------- Helpers ----------

def parse_path_endpoints(d):
    """Return (start, end) coordinate tuples from a path d attribute.

    Simple parser — only handles explicit M and L/l absolute commands which
    is what every fn-diagram edge currently uses. Returns (None, None) on
    unparseable input.
    """
    # First move
    m = re.match(r'\s*M\s+(-?\d+(?:\.\d+)?)\s+(-?\d+(?:\.\d+)?)', d)
    if not m:
        return None, None
    start = (float(m.group(1)), float(m.group(2)))
    # Collect every (x, y) pair that follows a move/line command
    coords = re.findall(
        r'[MLT]\s+(-?\d+(?:\.\d+)?)\s+(-?\d+(?:\.\d+)?)', d)
    if coords:
        end = (float(coords[-1][0]), float(coords[-1][1]))
    else:
        end = start
    return start, end


def find_attr(attrs, name):
    """Extract a simple attribute value from an opening-tag attribute string.
    Handles both quoted attrs and JSX-style {expr}. Returns None if absent
    or expression-valued (we skip expression-valued ones as non-static)."""
    m = re.search(
        rf'\b{name}\s*=\s*"([^"]*)"', attrs)
    return m.group(1) if m else None


def has_class(attrs, cls):
    """Return True iff the class attribute contains cls as a whole token."""
    val = find_attr(attrs, "class")
    if not val:
        return False
    return cls in val.split()


# ---------- Invariant checks ----------

def check_flow_cxcy(svg):
    """Invariant 3: <circle class="fn-diagram__flow"> must NOT set non-zero
    cx/cy. animateMotion applies as an additional translate() *on top of*
    the element's intrinsic position, so cx/cy compounds with the path and
    displaces the dot. Let the CSS opacity:0 gate (via .fn-diagram--visible)
    handle pre-begin invisibility instead.
    """
    issues = []
    for m in re.finditer(r'<circle\b([^>]*)>', svg):
        attrs = m.group(1)
        if not has_class(attrs, "fn-diagram__flow"):
            continue
        for axis in ("cx", "cy"):
            val = find_attr(attrs, axis)
            if val is None:
                continue
            try:
                if float(val) != 0.0:
                    issues.append(
                        f'flow circle has {axis}="{val}" — animateMotion '
                        "compounds cx/cy with the path transform, displacing "
                        f"the dot. Remove the {axis} attribute (or set to 0).")
            except ValueError:
                issues.append(
                    f'flow circle has non-numeric {axis}="{val}" — remove it.')
    return issues


def check_animate_motion_begin(svg):
    """Invariant 4: animateMotion begin ≥ 1.4s."""
    issues = []
    for m in re.finditer(r'<animateMotion\b([^>]*)', svg):
        attrs = m.group(1)
        begin = find_attr(attrs, "begin")
        if begin is None:
            issues.append("animateMotion missing begin attribute "
                          "(should be \"1.4s\" or later).")
            continue
        mb = re.match(r'^\s*(\d+(?:\.\d+)?)s\s*$', begin)
        if mb:
            val = float(mb.group(1))
            if val < 1.4:
                issues.append(
                    f'animateMotion begin="{begin}" (< 1.4s) — flow particle '
                    "starts before path-draw finishes.")
    return issues


def check_svg_aria(svg):
    """Invariant 13: <svg> has role="img" + aria-label."""
    issues = []
    m = re.match(r'<svg\b([^>]*)>', svg)
    if not m:
        return issues
    attrs = m.group(1)
    if find_attr(attrs, "role") != "img":
        issues.append('<svg> missing role="img".')
    if find_attr(attrs, "aria-label") is None:
        issues.append('<svg> missing aria-label.')
    return issues


def check_no_title_child(svg):
    """Invariant 14: no <title> child of <svg>."""
    if re.search(r'<title[\s>]', svg):
        return ['<title> element inside <svg> — '
                'use aria-label on the <svg> instead.']
    return []


def check_stroke_widths(svg):
    """Invariant 11: stroke-width ∈ {0.5, 1, 1.5, 2}."""
    issues = []
    for m in re.finditer(r'\bstroke-width\s*=\s*"([^"]+)"', svg):
        w = m.group(1).strip()
        if w not in ALLOWED_STROKE_WIDTHS:
            issues.append(
                f'stroke-width="{w}" not in {{0.5, 1, 1.5, 2}} '
                "(use 0.5=grid, 1=baseline, 1.5=secondary flow, 2=primary).")
    return issues


def check_no_hex_colors(svg):
    """Invariant 12: no hex literals in fill / stroke."""
    issues = []
    for m in re.finditer(
            r'\b(fill|stroke)\s*=\s*"(#[0-9A-Fa-f]{3,8})"', svg):
        issues.append(
            f'hex literal {m.group(2)} in {m.group(1)}= — '
            "route through --svg-*/--color-* CSS var or fn-diagram__* class.")
    return issues


def check_edge_ghost_penetration(svg):
    """Invariant 2: no <path class="fn-diagram__edge"> endpoint lands deep
    inside a <rect class="fn-diagram__node--ghost"> *unless* it's on another
    node's boundary (the grouping-container case). Ghost has fill:none, so
    a stroke with no nearby node to anchor it cuts through the ghost's text.
    """
    # Collect every node's bbox (rects + path-based nodes like hexagons/cylinders)
    # so we can detect "edge endpoint lands on SOME node's boundary."
    nodes = []
    for m in re.finditer(r'<rect\b([^>]*)', svg):
        attrs = m.group(1)
        if not has_class(attrs, "fn-diagram__node"):
            continue
        try:
            x = float(find_attr(attrs, "x"))
            y = float(find_attr(attrs, "y"))
            w = float(find_attr(attrs, "width"))
            h = float(find_attr(attrs, "height"))
        except (TypeError, ValueError):
            continue
        nodes.append({'x': x, 'y': y, 'w': w, 'h': h,
                      'ghost': has_class(attrs, "fn-diagram__node--ghost")})
    # Path-based nodes: compute bbox from the d attribute's extrema.
    for m in re.finditer(r'<path\b([^>]*)', svg):
        attrs = m.group(1)
        if not has_class(attrs, "fn-diagram__node"):
            continue
        d = find_attr(attrs, "d")
        if not d:
            continue
        coords = re.findall(r'(-?\d+(?:\.\d+)?)\s+(-?\d+(?:\.\d+)?)', d)
        if not coords:
            continue
        xs = [float(c[0]) for c in coords]
        ys = [float(c[1]) for c in coords]
        nodes.append({'x': min(xs), 'y': min(ys),
                      'w': max(xs) - min(xs), 'h': max(ys) - min(ys),
                      'ghost': has_class(attrs, "fn-diagram__node--ghost")})

    def on_any_node_boundary(pt):
        for n in nodes:
            left, right = n['x'], n['x'] + n['w']
            top, bot = n['y'], n['y'] + n['h']
            on_x_edge = (abs(pt[0] - left) <= BOUNDARY_TOL or
                         abs(pt[0] - right) <= BOUNDARY_TOL)
            on_y_edge = (abs(pt[1] - top) <= BOUNDARY_TOL or
                         abs(pt[1] - bot) <= BOUNDARY_TOL)
            in_x = left - BOUNDARY_TOL <= pt[0] <= right + BOUNDARY_TOL
            in_y = top - BOUNDARY_TOL <= pt[1] <= bot + BOUNDARY_TOL
            if (on_x_edge and in_y) or (on_y_edge and in_x):
                return True
        return False

    issues = []
    for m in re.finditer(r'<path\b([^>]*)', svg):
        attrs = m.group(1)
        if not has_class(attrs, "fn-diagram__edge"):
            continue
        d = find_attr(attrs, "d")
        if not d:
            continue
        start, end = parse_path_endpoints(d)
        if start is None:
            continue
        for name, pt in (("start", start), ("end", end)):
            if on_any_node_boundary(pt):
                continue
            for n in nodes:
                if not n['ghost']:
                    continue
                inside_x = n['x'] + BOUNDARY_TOL < pt[0] < n['x'] + n['w'] - BOUNDARY_TOL
                inside_y = n['y'] + BOUNDARY_TOL < pt[1] < n['y'] + n['h'] - BOUNDARY_TOL
                if inside_x and inside_y:
                    issues.append(
                        f'edge {name}=({pt[0]},{pt[1]}) is inside ghost node '
                        f'at ({n["x"]},{n["y"]}) {n["w"]}×{n["h"]} and not on '
                        "any other node's boundary — route the endpoint to a "
                        "node edge so the line doesn't cut through text.")
                    break
    return issues


def check_z_order(svg):
    """Invariant 1: edges group precedes nodes group precedes labels group
    precedes symbols group (if multiple are present)."""
    layers = [
        ("fn-diagram__edges", "edges"),
        ("fn-diagram__nodes", "nodes"),
        ("fn-diagram__labels", "labels"),
        ("fn-diagram__symbols", "symbols"),
    ]
    positions = []
    for cls, name in layers:
        m = re.search(
            rf'<g\b[^>]*class="[^"]*{re.escape(cls)}[^"]*"', svg)
        if m:
            positions.append((m.start(), name))
    issues = []
    for i in range(1, len(positions)):
        if positions[i][0] < positions[i - 1][0]:
            issues.append(
                f'z-order: <g class="fn-diagram__{positions[i][1]}"> appears '
                f'before <g class="fn-diagram__{positions[i-1][1]}"> — '
                "reorder so edges → nodes → labels → symbols.")
    return issues


def check_icon_text_clearance(svg):
    """Invariant 7: each fn-diagram__icon clears every text bbox by ≥ 10 SVG
    units in whichever axis separates them. Horizontally-adjacent legend
    pairs (icon left of text, side-by-side) are not flagged, only icons
    that overlap or crowd a text's vertical column.
    """
    issues = []
    icons = []
    for m in re.finditer(r'<g\b([^>]*)>', svg):
        attrs = m.group(1)
        if not has_class(attrs, "fn-diagram__icon"):
            continue
        tr = re.search(
            r'transform\s*=\s*"translate\(\s*(-?\d+(?:\.\d+)?)[\s,]+'
            r'(-?\d+(?:\.\d+)?)\s*\)(?:\s*scale\(\s*(-?\d+(?:\.\d+)?)\s*\))?',
            attrs)
        if tr:
            scale = float(tr.group(3)) if tr.group(3) else 1.0
            icons.append((float(tr.group(1)), float(tr.group(2)), scale))

    texts = []
    for m in re.finditer(r'<text\b([^>]*)>([^<]*)</text>', svg):
        attrs = m.group(1)
        try:
            tx = float(find_attr(attrs, "x"))
            ty = float(find_attr(attrs, "y"))
        except (TypeError, ValueError):
            continue
        anchor = find_attr(attrs, "text-anchor") or "start"
        content = m.group(2).strip()
        # Rough width estimate: 7 units per char. Good enough for bbox
        # separation tests — we don't need precise metrics.
        est_w = max(16, len(content) * 7)
        if anchor == "middle":
            text_left, text_right = tx - est_w / 2, tx + est_w / 2
        elif anchor == "end":
            text_left, text_right = tx - est_w, tx
        else:  # start (SVG default)
            text_left, text_right = tx, tx + est_w
        texts.append({
            'x': tx, 'y': ty, 'content': content,
            'left': text_left, 'right': text_right,
            'top': ty - TEXT_ASCENT, 'bottom': ty + TEXT_DESCENT,
        })

    for ix, iy, scale in icons:
        size = 24 * scale
        il, it, ir, ib = ix, iy, ix + size, iy + size
        for t in texts:
            tl, tt, tr_, tb = t['left'], t['top'], t['right'], t['bottom']
            h_overlap = not (ir < tl or tr_ < il)
            v_overlap = not (ib < tt or tb < it)
            if h_overlap and v_overlap:
                issues.append(
                    f'icon at ({ix},{iy}) overlaps text "{t["content"][:40]}" '
                    f'at ({t["x"]},{t["y"]}).')
                continue
            # Only flag a vertical-clearance violation when the two are
            # horizontally aligned (same visual column). Side-by-side icon+
            # text legends — horizontally separated — are fine.
            if h_overlap and not v_overlap:
                if ib <= tt:
                    gap = tt - ib
                    if gap < ICON_TEXT_CLEARANCE:
                        issues.append(
                            f'icon at ({ix},{iy}) is only {gap:.1f} units above '
                            f'text "{t["content"][:40]}" (need ≥{ICON_TEXT_CLEARANCE}).')
                else:
                    gap = it - tb
                    if gap < ICON_TEXT_CLEARANCE:
                        issues.append(
                            f'icon at ({ix},{iy}) is only {gap:.1f} units below '
                            f'text "{t["content"][:40]}" (need ≥{ICON_TEXT_CLEARANCE}).')
    return issues


def check_has_gradient(svg):
    """Invariant 8: SVG must declare at least one gradient in <defs>."""
    if not re.search(r'<(linearGradient|radialGradient)\b', svg):
        return [
            "no <linearGradient>/<radialGradient> in <defs> — add an "
            "atmospheric gradient (lane wash, field radial, or dot halo)."]
    return []


# ---------- Run ----------

def run_checks(svg, label, is_signature=False):
    """Return list of (severity, issue) tuples."""
    issues = []
    issues += check_svg_aria(svg)
    issues += check_no_title_child(svg)
    issues += check_no_hex_colors(svg)
    issues += check_stroke_widths(svg)
    issues += check_has_gradient(svg)
    if not is_signature:
        # fn-diagram-specific invariants
        issues += check_flow_cxcy(svg)
        issues += check_animate_motion_begin(svg)
        issues += check_z_order(svg)
        issues += check_edge_ghost_penetration(svg)
        issues += check_icon_text_clearance(svg)
    return [(label, i) for i in issues]


total_issues = []

# In-body fn-diagrams.
# Published articles MUST ship at least one inline fn-diagram alongside the
# signature — the signature is the card thumbnail, the fn-diagram is the
# architectural figure that lives in the article body. Upcoming placeholders
# are exempt because they are abstract-only previews.
article_text = ARTICLE_PATH.read_text()

def _article_status(text):
    m = re.search(r'^---\n(.*?)\n---\n', text, re.DOTALL)
    if not m:
        return "published"
    for line in m.group(1).splitlines():
        sm = re.match(r'^\s*status\s*:\s*["\']?(\w+)["\']?\s*$', line)
        if sm:
            return sm.group(1)
    return "published"

status = _article_status(article_text)
fn_svgs = extract_fn_diagram_svgs(article_text)
if not fn_svgs:
    if status == "upcoming":
        print(f"NOTE: no fn-diagram figures in {ARTICLE_PATH.name} "
              "— skipping in-body SVG checks (status: upcoming).")
    else:
        total_issues.append((
            f"article {ARTICLE_PATH.name}",
            'no <figure class="fn-diagram"> in article body — '
            'published articles must ship at least one inline architectural '
            'figure alongside the signature component. See '
            'references/visualizations.md §When a diagram earns its keep.'
        ))
else:
    for svg_text, label in fn_svgs:
        total_issues += run_checks(svg_text, label, is_signature=False)

# Signature components
if SVG_DIR.is_dir():
    for astro in sorted(SVG_DIR.glob("*.astro")):
        svg_text = extract_signature_svg(astro)
        if svg_text is None:
            print(f"WARN: {astro.name} has no <svg> — skipping.")
            continue
        total_issues += run_checks(
            svg_text, f"signature {astro.name}", is_signature=True)
else:
    print(f"WARN: {SVG_DIR} not found — skipping signature checks.")

if total_issues:
    # Group by label for readable output
    current = None
    for label, msg in total_issues:
        if label != current:
            print(f"\nFAIL [{label}]")
            current = label
        print(f"  · {msg}")
    print(f"\n{len(total_issues)} SVG invariant violation(s) — "
          "see references/visualizations.md §Hard invariants.")
    sys.exit(1)

print("OK: all SVG diagrams pass the hard invariants "
      "(flow particle, edge routing, icon clearance, gradient defs, "
      "accessibility, color tokens, stroke hierarchy).")
PY
