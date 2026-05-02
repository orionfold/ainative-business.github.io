#!/usr/bin/env python3
"""
Sync new and changed field-notes articles + images from the local
ai-field-notes drafting repo into this website's articles/ tree.

Idempotent — files are overwritten only when their content actually changed.
Never deletes anything, never touches the two reframed papers
(ai-transformation, solo-builder-case-study), never copies non-image
evidence files, never copies transcript.md or seed.md when a real
article.md is alongside.

Run from the website project root:
    python3 .claude/skills/sync-field-notes/scripts/sync_articles.py
"""

import hashlib
import shutil
import sys
from pathlib import Path

SOURCE_ROOT = Path("/Users/manavsehgal/Developer/ai-field-notes/articles")
TARGET_ROOT = Path("/Users/manavsehgal/Developer/ainative-business.github.io/articles")

FIELDKIT_DOCS_SOURCE = Path("/Users/manavsehgal/Developer/ai-field-notes/fieldkit/docs/api")
FIELDKIT_DOCS_TARGET = Path("/Users/manavsehgal/Developer/ainative-business.github.io/fieldkit/docs/api")
FIELDKIT_VERSION_SOURCE = Path("/Users/manavsehgal/Developer/ai-field-notes/fieldkit/src/fieldkit/_version.py")
FIELDKIT_VERSION_TARGET = Path("/Users/manavsehgal/Developer/ainative-business.github.io/fieldkit/_version.py")

TARGET_ONLY_SLUGS = {"ai-transformation", "solo-builder-case-study"}
SOURCE_IGNORED_TOPLEVEL = {"_drafts"}
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".svg", ".gif", ".webp"}


def file_hash(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def copy_if_different(src: Path, dst: Path) -> bool:
    """Copy src→dst if dst is missing or content differs. Return True if copied."""
    if dst.exists() and file_hash(src) == file_hash(dst):
        return False
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    return True


def sync_slug(slug: str) -> dict:
    """Sync one article folder. Returns counts of changes."""
    src_dir = SOURCE_ROOT / slug
    tgt_dir = TARGET_ROOT / slug

    counts = {"article": 0, "screenshot": 0, "evidence_image": 0, "seed_promoted": 0}

    # Article markdown — prefer .md, then .mdx, else seed.md → article.md.
    src_md = src_dir / "article.md"
    src_mdx = src_dir / "article.mdx"
    seed_md = src_dir / "seed.md"

    if src_md.exists():
        if copy_if_different(src_md, tgt_dir / "article.md"):
            counts["article"] += 1
    elif src_mdx.exists():
        if copy_if_different(src_mdx, tgt_dir / "article.mdx"):
            counts["article"] += 1
    elif seed_md.exists():
        # No real article yet; promote seed.md → article.md so the upcoming
        # placeholder shows up in the collection.
        if copy_if_different(seed_md, tgt_dir / "article.md"):
            counts["seed_promoted"] += 1

    # Screenshots — copy every file (not just images) since they're authored
    # specifically for publication and don't carry heavyweight extras.
    src_shots = src_dir / "screenshots"
    if src_shots.is_dir():
        for f in src_shots.rglob("*"):
            if not f.is_file():
                continue
            rel = f.relative_to(src_shots)
            if copy_if_different(f, tgt_dir / "screenshots" / rel):
                counts["screenshot"] += 1

    # Evidence — image files only, recursively. Source code stays in the
    # source repo; the article body links out to GitHub if it needs the code.
    src_evidence = src_dir / "evidence"
    if src_evidence.is_dir():
        for f in src_evidence.rglob("*"):
            if not f.is_file() or f.suffix.lower() not in IMAGE_EXTS:
                continue
            rel = f.relative_to(src_evidence)
            if copy_if_different(f, tgt_dir / "evidence" / rel):
                counts["evidence_image"] += 1

    return counts


def list_source_slugs() -> list[str]:
    if not SOURCE_ROOT.is_dir():
        return []
    return sorted(
        d.name
        for d in SOURCE_ROOT.iterdir()
        if d.is_dir() and d.name not in SOURCE_IGNORED_TOPLEVEL
    )


def sync_fieldkit() -> dict:
    """Sync the 5 module reference markdown files + the version file."""
    counts = {"fieldkit_doc": 0, "fieldkit_version": 0}
    if FIELDKIT_DOCS_SOURCE.is_dir():
        FIELDKIT_DOCS_TARGET.mkdir(parents=True, exist_ok=True)
        for src in FIELDKIT_DOCS_SOURCE.glob("*.md"):
            if copy_if_different(src, FIELDKIT_DOCS_TARGET / src.name):
                counts["fieldkit_doc"] += 1
    if FIELDKIT_VERSION_SOURCE.exists():
        if copy_if_different(FIELDKIT_VERSION_SOURCE, FIELDKIT_VERSION_TARGET):
            counts["fieldkit_version"] += 1
    return counts


def main() -> int:
    if not SOURCE_ROOT.is_dir():
        print(f"ERROR: source path not found: {SOURCE_ROOT}", file=sys.stderr)
        return 2
    TARGET_ROOT.mkdir(parents=True, exist_ok=True)

    totals = {"article": 0, "screenshot": 0, "evidence_image": 0, "seed_promoted": 0}
    touched_slugs: list[tuple[str, dict]] = []

    for slug in list_source_slugs():
        counts = sync_slug(slug)
        if any(counts.values()):
            touched_slugs.append((slug, counts))
            for k, v in counts.items():
                totals[k] += v

    fk_counts = sync_fieldkit()

    print(f"# Field Notes sync — applied")
    print(f"  articles source: {SOURCE_ROOT}")
    print(f"  articles target: {TARGET_ROOT}")
    print()
    nothing_articles = not touched_slugs
    nothing_fieldkit = not any(fk_counts.values())
    if nothing_articles and nothing_fieldkit:
        print("No changes copied. Source and target were already in step.")
        return 0

    for slug, counts in touched_slugs:
        bits = []
        if counts["article"]:
            bits.append("article body")
        if counts["seed_promoted"]:
            bits.append("upcoming seed promoted")
        if counts["screenshot"]:
            bits.append(f"{counts['screenshot']} screenshot file(s)")
        if counts["evidence_image"]:
            bits.append(f"{counts['evidence_image']} evidence image(s)")
        print(f"  • {slug}: {', '.join(bits)}")

    if fk_counts["fieldkit_doc"]:
        print(f"  • fieldkit/docs/api/: {fk_counts['fieldkit_doc']} module reference doc(s)")
    if fk_counts["fieldkit_version"]:
        print(f"  • fieldkit/_version.py: bumped")

    print()
    print("Totals:")
    for k, v in totals.items():
        if v:
            print(f"  {k}: {v}")
    for k, v in fk_counts.items():
        if v:
            print(f"  {k}: {v}")

    print()
    print("Next: run `npm run build` to verify, then preview /field-notes/ and /fieldkit/.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
