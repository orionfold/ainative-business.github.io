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
import re
import shutil
import sys
import textwrap
from pathlib import Path

SOURCE_ROOT = Path("/Users/manavsehgal/Developer/ai-field-notes/articles")
TARGET_ROOT = Path("/Users/manavsehgal/Developer/ainative-business.github.io/articles")

FIELDKIT_DOCS_SOURCE = Path("/Users/manavsehgal/Developer/ai-field-notes/fieldkit/docs/api")
FIELDKIT_DOCS_TARGET = Path("/Users/manavsehgal/Developer/ainative-business.github.io/fieldkit/docs/api")
FIELDKIT_VERSION_SOURCE = Path("/Users/manavsehgal/Developer/ai-field-notes/fieldkit/src/fieldkit/_version.py")
FIELDKIT_VERSION_TARGET = Path("/Users/manavsehgal/Developer/ainative-business.github.io/fieldkit/_version.py")

# Fieldkit landing page — see diff_articles.py for the full rationale. Both
# repos render /fieldkit/ from a Nav-wrapped Astro page with the same
# section-block structure but different layout wrappers, so we sync only the
# inner bodies of <section class="fk-section"> blocks keyed by <h2> title.
LANDING_SOURCE = Path("/Users/manavsehgal/Developer/ai-field-notes/src/pages/fieldkit/index.astro")
LANDING_TARGET = Path("/Users/manavsehgal/Developer/ainative-business.github.io/src/pages/fieldkit/index.astro")
LANDING_SECTIONS_TO_SYNC = ("Install", "Quickstart", "CLI")

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


# Landing-page section sync. Match a top-level <section class="fk-section">
# (no extra classes) and capture indent + body. Sections are never nested in
# this file, so a lazy match is safe.
_LANDING_SECTION_RE = re.compile(
    r'(?P<indent>[ \t]*)<section\s+class="fk-section">(?P<body>.*?)</section>',
    re.DOTALL,
)
_LANDING_H2_RE = re.compile(r'<h2[^>]*>(?P<title>.*?)</h2>', re.DOTALL)


def _extract_landing_sections(text: str) -> dict[str, dict]:
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
            "match": m,
        }
    return out


def _normalize_section_body(body: str) -> str:
    return textwrap.dedent(body).strip()


def _transplant_section_body(source_body: str, target_indent: str) -> str:
    """
    Take source section body (between <section ...> and </section>) and produce
    a body suitable for splicing into target's <section> at target_indent.
    Dedents source content to col 0, then re-indents at target_indent + 2 spaces.
    """
    inner = source_body.lstrip("\n")
    lines = inner.split("\n")
    non_blank = [ln for ln in lines if ln.strip()]
    if not non_blank:
        return source_body
    min_indent = min(len(ln) - len(ln.lstrip(" ")) for ln in non_blank)
    dedented = [(ln[min_indent:] if ln.strip() else "") for ln in lines]
    while dedented and not dedented[-1].strip():
        dedented.pop()
    content_indent = target_indent + "  "
    reindented = [(content_indent + ln if ln.strip() else "") for ln in dedented]
    return "\n" + "\n".join(reindented) + "\n" + target_indent


def sync_landing_page() -> dict:
    """
    Replace target's section bodies (matched by <h2>) with source's, for the
    sections in LANDING_SECTIONS_TO_SYNC. Idempotent: writes only if the file
    actually changes after reindentation. Returns counts.
    """
    counts = {"landing_section": 0}
    if not LANDING_SOURCE.exists() or not LANDING_TARGET.exists():
        return counts

    src_text = LANDING_SOURCE.read_text(encoding="utf8")
    tgt_text = LANDING_TARGET.read_text(encoding="utf8")
    src_sections = _extract_landing_sections(src_text)
    tgt_sections = _extract_landing_sections(tgt_text)

    # Replace from the bottom up so earlier section spans stay valid.
    targets_to_replace: list[tuple[str, dict, str]] = []
    for title in LANDING_SECTIONS_TO_SYNC:
        if title not in src_sections or title not in tgt_sections:
            continue
        if _normalize_section_body(src_sections[title]["body"]) == _normalize_section_body(
            tgt_sections[title]["body"]
        ):
            continue
        new_body = _transplant_section_body(
            src_sections[title]["body"], tgt_sections[title]["indent"]
        )
        targets_to_replace.append((title, tgt_sections[title], new_body))

    if not targets_to_replace:
        return counts

    targets_to_replace.sort(key=lambda x: x[1]["span"][0], reverse=True)

    new_text = tgt_text
    for title, sec, new_body in targets_to_replace:
        full_match = sec["match"]
        # Reconstruct: same indent + section open tag + new_body + close tag
        replacement = (
            sec["indent"]
            + '<section class="fk-section">'
            + new_body
            + "</section>"
        )
        start, end = full_match.span()
        new_text = new_text[:start] + replacement + new_text[end:]
        counts["landing_section"] += 1

    if new_text != tgt_text:
        LANDING_TARGET.write_text(new_text, encoding="utf8")

    return counts


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
    landing_counts = sync_landing_page()

    print(f"# Field Notes sync — applied")
    print(f"  articles source: {SOURCE_ROOT}")
    print(f"  articles target: {TARGET_ROOT}")
    print()
    nothing_articles = not touched_slugs
    nothing_fieldkit = not any(fk_counts.values())
    nothing_landing = not any(landing_counts.values())
    if nothing_articles and nothing_fieldkit and nothing_landing:
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
    if landing_counts["landing_section"]:
        print(
            f"  • src/pages/fieldkit/index.astro: "
            f"{landing_counts['landing_section']} section(s) updated"
        )

    print()
    print("Totals:")
    for k, v in totals.items():
        if v:
            print(f"  {k}: {v}")
    for k, v in fk_counts.items():
        if v:
            print(f"  {k}: {v}")
    for k, v in landing_counts.items():
        if v:
            print(f"  {k}: {v}")

    print()
    print("Next: run `npm run build` to verify, then preview /field-notes/ and /fieldkit/.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
