#!/usr/bin/env python3
"""
Diff source articles/ (from the ai-field-notes cache clone, see source_repo.py)
against this website's articles/ tree.

Reports new articles, updated articles, new/changed images, and orphan
folders that exist only on the website side. Read-only — never copies.

Run from the website project root:
    python3 .claude/skills/sync-field-notes/scripts/sync_articles.py --plan
or directly:
    python3 .claude/skills/sync-field-notes/scripts/diff_articles.py
"""

import hashlib
import json
import re
import sys
import textwrap
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import chrome_footers  # noqa: E402

# Source-side paths come from the shared `source_repo` module, which resolves
# them under a local cache clone of github.com/manavsehgal/ai-field-notes
# (refreshed in SKILL.md Step 1). Target-side paths are this website repo.
from source_repo import (  # noqa: E402
    SOURCE_REPO,
    SOURCE_ROOT,
    FIELDKIT_DOCS_SOURCE,
    FIELDKIT_VERSION_SOURCE,
    LANDING_SOURCE,
    SIGNATURE_SVG_SOURCE,
    PROJECT_STATS_SOURCE,
)

TARGET_ROOT = Path("/Users/manavsehgal/Developer/ainative-business.github.io/articles")

# Fieldkit module reference docs and the version file the homepage reads at
# build time. Mirrored separately from articles because they live under a
# different top-level path in both repos.
FIELDKIT_DOCS_TARGET = Path("/Users/manavsehgal/Developer/ainative-business.github.io/fieldkit/docs/api")
FIELDKIT_VERSION_TARGET = Path("/Users/manavsehgal/Developer/ainative-business.github.io/fieldkit/_version.py")

# Fieldkit landing page — both repos render /fieldkit/ from a Nav-wrapped Astro
# page with an identical section-block structure. The wrappers differ (source
# uses BaseLayout; this site uses FieldNotesLayout + Nav + Footer), so a 1:1
# file copy would break the build. Instead, we sync only the inner bodies of
# specific <section class="fk-section"> blocks keyed by their <h2> title.
# Section list is intentionally narrow: these are pure copy/code blocks that
# don't reference site-local URL helpers (articleHref) or content collections.
LANDING_TARGET = Path("/Users/manavsehgal/Developer/ainative-business.github.io/src/pages/fieldkit/index.astro")
LANDING_SECTIONS_TO_SYNC = ("Install", "Quickstart", "CLI")

# Signature SVG components — referenced by `signature: <Name>` in article
# frontmatter. Source and target paths differ (the website nests them under
# field-notes/), but the file basenames match. ArticleCard.astro auto-discovers
# new files via import.meta.glob, so no registration is needed when adding one.
# The website may legitimately have signatures the source doesn't (e.g., for
# the two reframed research papers), so we only flow source→target — never
# report orphans, never delete.
SIGNATURE_SVG_TARGET = Path("/Users/manavsehgal/Developer/ainative-business.github.io/src/components/field-notes/svg")

# Project-stats JSON — drives the "At a glance" KPI block on /field-notes/ and
# the homepage FieldNotesSummary KPIs. Source path is shallower than target.
# The website applies one hand-curated override (recall@5 = 1.0 pinned to
# index 0 of metrics.accuracy[] with a cleaned label); we re-apply that
# override before comparing so a no-op sync reports no drift.
PROJECT_STATS_TARGET = Path("/Users/manavsehgal/Developer/ainative-business.github.io/src/data/field-notes/project-stats.json")

# Articles authored only on the website (the two reframed research papers).
# Never report or sync these — they have no source counterpart.
TARGET_ONLY_SLUGS = {"ai-transformation", "solo-builder-case-study"}

# Folder at the source root that contains in-progress drafts. Never sync.
SOURCE_IGNORED_TOPLEVEL = {"_drafts"}

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".svg", ".gif", ".webp"}


def file_hash(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


# Mirror of sync_articles.py's link rewrite. Required so the diff doesn't
# report phantom "content differs" on every sync — the script must compare
# source-after-transform vs target.
_ARTICLE_LINK_RE = re.compile(r'\]\(/articles/(?:([a-z0-9-]+)/?)?(#[^)]*|\?[^)]*)?\)')


def rewrite_article_links(text: str) -> str:
    def _sub(m: re.Match) -> str:
        slug = m.group(1)
        suffix = m.group(2) or ""
        if slug is None:
            return f"](/field-notes/{suffix})"
        return f"](/field-notes/{slug}/{suffix})"
    return _ARTICLE_LINK_RE.sub(_sub, text)


_GATED_ARTICLES: set[str] | None = None


def _gated_slugs() -> set[str]:
    """Memoized set of article slugs whose target carries a Mac-owned trailing
    catalog footer. Stripped from target before comparing against source so
    the diff stops flagging chrome-footer drift on every release."""
    global _GATED_ARTICLES
    if _GATED_ARTICLES is None:
        _GATED_ARTICLES = set(chrome_footers.collect_gated_articles().keys())
    return _GATED_ARTICLES


def article_content_differs(src: Path, tgt: Path) -> bool:
    """Compare source vs target after applying the link rewrite to source.
    For articles whose target carries a gated catalog footer, strip it from
    target before comparing — that block is Mac-authoritative chrome, not
    editorial content. Used in place of `file_hash(src) != file_hash(tgt)`
    for article files."""
    src_text = rewrite_article_links(src.read_text(encoding="utf8"))
    tgt_text = tgt.read_text(encoding="utf8")
    slug = tgt.parent.name
    if slug in _gated_slugs():
        tgt_text = chrome_footers.strip_footer(tgt_text).rstrip() + "\n"
        src_text = src_text.rstrip() + "\n"
    return src_text != tgt_text


def article_payload(slug_dir: Path) -> Path | None:
    """Return the article.md or article.mdx path if present, else None."""
    for name in ("article.md", "article.mdx"):
        p = slug_dir / name
        if p.exists():
            return p
    return None


def upcoming_seed(slug_dir: Path) -> Path | None:
    """Return seed.md if present and there is no published article.md/mdx."""
    seed = slug_dir / "seed.md"
    if seed.exists() and article_payload(slug_dir) is None:
        return seed
    return None


def syncable_image_files(slug_dir: Path) -> list[Path]:
    """All image files inside screenshots/ or evidence/ — recursive."""
    result: list[Path] = []
    for sub in ("screenshots", "evidence"):
        d = slug_dir / sub
        if not d.is_dir():
            continue
        for f in d.rglob("*"):
            if f.is_file() and f.suffix.lower() in IMAGE_EXTS:
                result.append(f)
    return result


def list_source_slugs() -> list[str]:
    if not SOURCE_ROOT.is_dir():
        return []
    return sorted(
        d.name
        for d in SOURCE_ROOT.iterdir()
        if d.is_dir() and d.name not in SOURCE_IGNORED_TOPLEVEL
    )


def list_target_slugs() -> list[str]:
    if not TARGET_ROOT.is_dir():
        return []
    return sorted(d.name for d in TARGET_ROOT.iterdir() if d.is_dir())


def fieldkit_doc_changes() -> list[tuple[str, str]]:
    """Return list of (filename, reason) for fieldkit/docs/api/*.md changes."""
    changes: list[tuple[str, str]] = []
    if not FIELDKIT_DOCS_SOURCE.is_dir():
        return changes
    for src in sorted(FIELDKIT_DOCS_SOURCE.glob("*.md")):
        tgt = FIELDKIT_DOCS_TARGET / src.name
        if not tgt.exists():
            changes.append((src.name, "new module reference doc"))
        elif file_hash(src) != file_hash(tgt):
            changes.append((src.name, "content differs"))
    return changes


def _apply_recall_at_5_override(stats: dict) -> dict:
    """Mirror sync_articles.py's override so the diff compares apples to apples.

    Match by (article_slug, value) so the rule survives source re-orderings.
    """
    metrics = stats.get("metrics")
    if not isinstance(metrics, dict):
        return stats
    accuracy = metrics.get("accuracy")
    if not isinstance(accuracy, list):
        return stats
    target_idx: int | None = None
    for i, entry in enumerate(accuracy):
        if (
            isinstance(entry, dict)
            and entry.get("article_slug") == "bigger-generator-grounding-on-spark"
            and entry.get("value") == "recall@5 = 1.0"
        ):
            target_idx = i
            break
    if target_idx is None:
        return stats
    entry = accuracy.pop(target_idx)
    entry["label"] = "perfect retrieval on the eval set"
    accuracy.insert(0, entry)
    return stats


def project_stats_changes() -> list[tuple[str, str, str]]:
    """Return [(label, target_value, source_value), ...] for headline drift.

    Compares source-after-override to current target. Empty list = no drift.
    Surfaces the three numbers a human would actually want to see (article
    count, words, generated_at) plus a generic catch-all if other fields drift.
    """
    if not PROJECT_STATS_SOURCE.exists() or not PROJECT_STATS_TARGET.exists():
        return []
    try:
        src = json.loads(PROJECT_STATS_SOURCE.read_text(encoding="utf8"))
        tgt = json.loads(PROJECT_STATS_TARGET.read_text(encoding="utf8"))
    except json.JSONDecodeError:
        return []
    src = _apply_recall_at_5_override(src)
    if json.dumps(src, sort_keys=True) == json.dumps(tgt, sort_keys=True):
        return []
    changes: list[tuple[str, str, str]] = []
    src_articles = src.get("articles", {}).get("total", 0)
    tgt_articles = tgt.get("articles", {}).get("total", 0)
    if src_articles != tgt_articles:
        changes.append(("articles.total", str(tgt_articles), str(src_articles)))
    src_words = src.get("words", {}).get("total", 0)
    tgt_words = tgt.get("words", {}).get("total", 0)
    if src_words != tgt_words:
        changes.append(("words.total", f"{tgt_words:,}", f"{src_words:,}"))
    src_loc = src.get("code", {}).get("total_loc", 0)
    tgt_loc = tgt.get("code", {}).get("total_loc", 0)
    if src_loc != tgt_loc:
        changes.append(("code.total_loc", f"{tgt_loc:,}", f"{src_loc:,}"))
    src_when = src.get("generated_at", "")[:10]
    tgt_when = tgt.get("generated_at", "")[:10]
    if src_when != tgt_when:
        changes.append(("generated_at", tgt_when, src_when))
    if not changes:
        changes.append(("project-stats.json", "stale", "in step with source"))
    return changes


def signature_svg_changes() -> list[tuple[str, str]]:
    """Return list of (filename, reason) for signature SVG component changes.

    Only flows source→target. Target-only signatures are not reported as
    orphans because the website may legitimately have signatures the source
    doesn't (e.g., for reframed research papers).
    """
    changes: list[tuple[str, str]] = []
    if not SIGNATURE_SVG_SOURCE.is_dir():
        return changes
    for src in sorted(SIGNATURE_SVG_SOURCE.glob("*.astro")):
        tgt = SIGNATURE_SVG_TARGET / src.name
        if not tgt.exists():
            changes.append((src.name, "new signature component"))
        elif file_hash(src) != file_hash(tgt):
            changes.append((src.name, "content differs"))
    return changes


# Match a top-level <section class="fk-section"> ... </section> with no extra
# classes (avoids matching <section class="fk-section fk-glance"> etc.) and
# capture both its leading indent and inner body. Sections in these files are
# never nested, so the lazy match is safe.
_LANDING_SECTION_RE = re.compile(
    r'(?P<indent>[ \t]*)<section\s+class="fk-section">(?P<body>.*?)</section>',
    re.DOTALL,
)
_LANDING_H2_RE = re.compile(r'<h2[^>]*>(?P<title>.*?)</h2>', re.DOTALL)


def _extract_landing_sections(text: str) -> dict[str, dict]:
    """Return {h2_title: {indent, body, span}} for every plain fk-section in text."""
    out: dict[str, dict] = {}
    for m in _LANDING_SECTION_RE.finditer(text):
        body = m.group("body")
        h2 = _LANDING_H2_RE.search(body)
        if not h2:
            continue
        title = re.sub(r"<[^>]+>", "", h2.group("title")).strip()
        out[title] = {
            "indent": m.group("indent"),
            "body": body,
            "span": m.span(),
        }
    return out


def _normalize_section_body(body: str) -> str:
    """Dedent and trim so two equivalent bodies at different indents compare equal."""
    return textwrap.dedent(body).strip()


def landing_section_changes() -> list[tuple[str, str]]:
    """Return [(title, reason), ...] for each LANDING_SECTIONS_TO_SYNC that drifted."""
    changes: list[tuple[str, str]] = []
    if not LANDING_SOURCE.exists() or not LANDING_TARGET.exists():
        return changes
    src = LANDING_SOURCE.read_text(encoding="utf8")
    tgt = LANDING_TARGET.read_text(encoding="utf8")
    src_sections = _extract_landing_sections(src)
    tgt_sections = _extract_landing_sections(tgt)
    for title in LANDING_SECTIONS_TO_SYNC:
        if title not in src_sections:
            # Source dropped a section we sync — flag for the user, don't auto-remove.
            if title in tgt_sections:
                changes.append((title, "missing in source (target retains)"))
            continue
        if title not in tgt_sections:
            changes.append((title, "missing in target — needs hand-add of <section>"))
            continue
        if _normalize_section_body(src_sections[title]["body"]) != _normalize_section_body(
            tgt_sections[title]["body"]
        ):
            changes.append((title, "content differs"))
    return changes


def fieldkit_version_change() -> tuple[bool, str | None, str | None]:
    """(changed, source_version_str, target_version_str) — version drift check.

    RETIRED (2026-06-10): always reports no change. The `fieldkit/_version.py`
    mirror is gone — `src/pages/fieldkit/index.astro` reads the package's
    canonical `fieldkit/src/fieldkit/_version.py` directly, so there is no
    mirror to drift. Do NOT resurrect the mirror comparison.
    """
    return False, None, None


def compute_diff() -> dict:
    src_slugs = list_source_slugs()
    tgt_slugs = list_target_slugs()
    src_set = set(src_slugs)
    tgt_set = set(tgt_slugs)

    new_articles: list[str] = []
    updated_articles: list[tuple[str, str]] = []  # (slug, reason)
    image_changes: list[tuple[str, Path]] = []  # (slug, source-image-path)
    orphans = sorted((tgt_set - src_set) - TARGET_ONLY_SLUGS)

    for slug in src_slugs:
        src_dir = SOURCE_ROOT / slug
        tgt_dir = TARGET_ROOT / slug
        src_md = article_payload(src_dir) or upcoming_seed(src_dir)
        if src_md is None:
            # Source folder has neither article nor seed — nothing to mirror.
            continue
        tgt_md = article_payload(tgt_dir) if tgt_dir.exists() else None

        if not tgt_dir.exists():
            new_articles.append(slug)
        elif tgt_md is None:
            updated_articles.append((slug, "target has no article.md/mdx — promote seed"))
        elif article_content_differs(src_md, tgt_md):
            updated_articles.append((slug, f"{src_md.name} content differs"))

        for img in syncable_image_files(src_dir):
            rel = img.relative_to(src_dir)
            tgt_img = tgt_dir / rel
            if not tgt_img.exists() or file_hash(img) != file_hash(tgt_img):
                image_changes.append((slug, img))

    fk_doc_changes = fieldkit_doc_changes()
    fk_version_changed, fk_src_ver, fk_tgt_ver = fieldkit_version_change()
    landing_changes = landing_section_changes()
    sig_changes = signature_svg_changes()
    stats_changes = project_stats_changes()

    return {
        "new_articles": new_articles,
        "updated_articles": updated_articles,
        "image_changes": image_changes,
        "orphans": orphans,
        "fieldkit_doc_changes": fk_doc_changes,
        "fieldkit_version_changed": fk_version_changed,
        "fieldkit_source_version": fk_src_ver,
        "fieldkit_target_version": fk_tgt_ver,
        "landing_changes": landing_changes,
        "signature_svg_changes": sig_changes,
        "project_stats_changes": stats_changes,
    }


def print_diff(diff: dict) -> int:
    new = diff["new_articles"]
    upd = diff["updated_articles"]
    imgs = diff["image_changes"]
    orphans = diff["orphans"]
    fk_doc = diff["fieldkit_doc_changes"]
    fk_ver_changed = diff["fieldkit_version_changed"]
    fk_src_ver = diff["fieldkit_source_version"]
    fk_tgt_ver = diff["fieldkit_target_version"]
    landing = diff["landing_changes"]
    sig = diff["signature_svg_changes"]
    stats = diff["project_stats_changes"]

    total = (
        len(new) + len(upd) + len(imgs) + len(fk_doc) + len(landing) + len(sig)
        + (1 if fk_ver_changed else 0)
        + (1 if stats else 0)
    )

    print(f"# Field Notes sync diff")
    print(f"  articles source: {SOURCE_ROOT}")
    print(f"  articles target: {TARGET_ROOT}")
    print(f"  fieldkit-docs source: {FIELDKIT_DOCS_SOURCE}")
    print(f"  fieldkit-docs target: {FIELDKIT_DOCS_TARGET}")
    print()

    if total == 0 and not orphans:
        print("Nothing to sync. Source and target are in step.")
        return 0

    if new:
        print(f"## New articles ({len(new)})")
        for slug in new:
            print(f"  + {slug}")
        print()

    if upd:
        print(f"## Updated articles ({len(upd)})")
        for slug, reason in upd:
            print(f"  ~ {slug}  [{reason}]")
        print()

    if imgs:
        # Group images by slug for readability.
        by_slug: dict[str, list[Path]] = {}
        for slug, img in imgs:
            by_slug.setdefault(slug, []).append(img)
        print(f"## Image changes ({len(imgs)})")
        for slug, paths in sorted(by_slug.items()):
            print(f"  {slug}:")
            for p in paths:
                rel = p.relative_to(SOURCE_ROOT / slug)
                print(f"    + {rel}")
        print()

    if orphans:
        print(f"## Orphans in target ({len(orphans)})")
        print("  (folder exists on website but not in source — likely renamed in source)")
        for slug in orphans:
            print(f"  ? {slug}")
        print()
        print("  Review by hand. Do not auto-delete.")
        print()

    if fk_doc:
        print(f"## Fieldkit module reference docs ({len(fk_doc)})")
        for name, reason in fk_doc:
            print(f"  ~ fieldkit/docs/api/{name}  [{reason}]")
        print()

    if fk_ver_changed:
        print(f"## Fieldkit version")
        if fk_src_ver and fk_tgt_ver:
            print(f"  source v{fk_src_ver}  →  target v{fk_tgt_ver}")
        elif fk_src_ver:
            print(f"  source v{fk_src_ver}  →  target (missing)")
        else:
            print("  drift in fieldkit/_version.py — inspect by hand")
        print()

    if landing:
        print(f"## Fieldkit landing page sections ({len(landing)})")
        print(f"  src/pages/fieldkit/index.astro — replacing target's <section> body by <h2> title")
        for title, reason in landing:
            print(f"  ~ {title}  [{reason}]")
        print()

    if sig:
        print(f"## Signature SVG components ({len(sig)})")
        print(f"  src/components/field-notes/svg/ — referenced by `signature:` frontmatter")
        for name, reason in sig:
            print(f"  ~ {name}  [{reason}]")
        print()

    if stats:
        print(f"## Project stats — At a glance KPIs ({len(stats)} field(s) drifted)")
        print(f"  src/data/field-notes/project-stats.json — auto-regenerated in source")
        for label, tgt_val, src_val in stats:
            print(f"  ~ {label}: {tgt_val} → {src_val}")
        print()

    return 0


def main() -> int:
    if not SOURCE_ROOT.is_dir():
        print(f"ERROR: source path not found: {SOURCE_ROOT}", file=sys.stderr)
        print(f"  Run the Step 1 bootstrap first to clone/refresh the cache:", file=sys.stderr)
        print(f"    python3 {Path(__file__).with_name('source_repo.py')}", file=sys.stderr)
        return 2
    if not TARGET_ROOT.is_dir():
        print(f"ERROR: target path not found: {TARGET_ROOT}", file=sys.stderr)
        return 2
    diff = compute_diff()
    return print_diff(diff)


if __name__ == "__main__":
    sys.exit(main())
