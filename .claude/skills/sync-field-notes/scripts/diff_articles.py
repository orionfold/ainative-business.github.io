#!/usr/bin/env python3
"""
Diff source ai-field-notes/articles/ against this website's articles/ tree.

Reports new articles, updated articles, new/changed images, and orphan
folders that exist only on the website side. Read-only — never copies.

Run from the website project root:
    python3 .claude/skills/sync-field-notes/scripts/sync_articles.py --plan
or directly:
    python3 .claude/skills/sync-field-notes/scripts/diff_articles.py
"""

import hashlib
import sys
from pathlib import Path

SOURCE_ROOT = Path("/Users/manavsehgal/Developer/ai-field-notes/articles")
TARGET_ROOT = Path("/Users/manavsehgal/Developer/ainative-business.github.io/articles")

# Fieldkit module reference docs and the version file the homepage reads at
# build time. Mirrored separately from articles because they live under a
# different top-level path in both repos.
FIELDKIT_DOCS_SOURCE = Path("/Users/manavsehgal/Developer/ai-field-notes/fieldkit/docs/api")
FIELDKIT_DOCS_TARGET = Path("/Users/manavsehgal/Developer/ainative-business.github.io/fieldkit/docs/api")
FIELDKIT_VERSION_SOURCE = Path("/Users/manavsehgal/Developer/ai-field-notes/fieldkit/src/fieldkit/_version.py")
FIELDKIT_VERSION_TARGET = Path("/Users/manavsehgal/Developer/ainative-business.github.io/fieldkit/_version.py")

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


def fieldkit_version_change() -> tuple[bool, str | None, str | None]:
    """(changed, source_version_str, target_version_str) — version drift check."""
    if not FIELDKIT_VERSION_SOURCE.exists():
        return False, None, None
    src_text = FIELDKIT_VERSION_SOURCE.read_text(encoding="utf8")
    tgt_text = FIELDKIT_VERSION_TARGET.read_text(encoding="utf8") if FIELDKIT_VERSION_TARGET.exists() else ""

    def extract(text: str) -> str | None:
        import re
        m = re.search(r'__version__\s*=\s*"([^"]+)"', text)
        return m.group(1) if m else None

    return (file_hash(FIELDKIT_VERSION_SOURCE) != file_hash(FIELDKIT_VERSION_TARGET)
            if FIELDKIT_VERSION_TARGET.exists() else True), extract(src_text), extract(tgt_text)


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
        elif file_hash(src_md) != file_hash(tgt_md):
            updated_articles.append((slug, f"{src_md.name} content differs"))

        for img in syncable_image_files(src_dir):
            rel = img.relative_to(src_dir)
            tgt_img = tgt_dir / rel
            if not tgt_img.exists() or file_hash(img) != file_hash(tgt_img):
                image_changes.append((slug, img))

    fk_doc_changes = fieldkit_doc_changes()
    fk_version_changed, fk_src_ver, fk_tgt_ver = fieldkit_version_change()

    return {
        "new_articles": new_articles,
        "updated_articles": updated_articles,
        "image_changes": image_changes,
        "orphans": orphans,
        "fieldkit_doc_changes": fk_doc_changes,
        "fieldkit_version_changed": fk_version_changed,
        "fieldkit_source_version": fk_src_ver,
        "fieldkit_target_version": fk_tgt_ver,
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

    total = len(new) + len(upd) + len(imgs) + len(fk_doc) + (1 if fk_ver_changed else 0)

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

    return 0


def main() -> int:
    if not SOURCE_ROOT.is_dir():
        print(f"ERROR: source path not found: {SOURCE_ROOT}", file=sys.stderr)
        print("  Make sure the local clone of ai-field-notes exists at this path.", file=sys.stderr)
        return 2
    if not TARGET_ROOT.is_dir():
        print(f"ERROR: target path not found: {TARGET_ROOT}", file=sys.stderr)
        return 2
    diff = compute_diff()
    return print_diff(diff)


if __name__ == "__main__":
    sys.exit(main())
