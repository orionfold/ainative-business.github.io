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
import json
import re
import shutil
import subprocess
import sys
import textwrap
from pathlib import Path

# `chrome_footers` is a sibling module; add this script's dir to sys.path
# the same way contract_sweep.py does it.
sys.path.insert(0, str(Path(__file__).resolve().parent))
import chrome_footers  # noqa: E402

SOURCE_REPO = Path("/Users/manavsehgal/Developer/ai-field-notes")
SOURCE_ROOT = SOURCE_REPO / "articles"
TARGET_ROOT = Path("/Users/manavsehgal/Developer/ainative-business.github.io/articles")

# Sequence manifest — captures the source repo's authoritative article order
# (git first-add time of each articles/*/article.md). Read by the website's
# publishOrdinals() so the №01..№N labels match source order regardless of
# when articles got committed on this side. Idempotent: only rewritten when
# the slug ordering actually changes.
SEQUENCE_MANIFEST = Path(
    "/Users/manavsehgal/Developer/ainative-business.github.io/src/data/field-notes/sequence.json"
)

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

# Signature SVG components — referenced by `signature: <Name>` in article
# frontmatter. ArticleCard.astro auto-discovers them via import.meta.glob, so
# dropping a new file in the target dir is enough to wire it up. Source and
# target paths differ (the website nests under field-notes/) but basenames
# match. One-way flow: source→target. Never delete target-only signatures —
# the website may have signatures the source doesn't (reframed papers).
SIGNATURE_SVG_SOURCE = Path("/Users/manavsehgal/Developer/ai-field-notes/src/components/svg")
SIGNATURE_SVG_TARGET = Path("/Users/manavsehgal/Developer/ainative-business.github.io/src/components/field-notes/svg")

# Project-stats JSON. Drives the "At a glance" KPI block on /field-notes/ and
# the homepage FieldNotesSummary KPIs. Source path is shallower (no nested
# field-notes/ dir) than target. The website applies one hand-curated override
# (see _apply_recall_at_5_override below); we re-apply it on every sync so it
# survives source regenerations.
PROJECT_STATS_SOURCE = Path("/Users/manavsehgal/Developer/ai-field-notes/src/data/project-stats.json")
PROJECT_STATS_TARGET = Path("/Users/manavsehgal/Developer/ainative-business.github.io/src/data/field-notes/project-stats.json")

TARGET_ONLY_SLUGS = {"ai-transformation", "solo-builder-case-study"}
SOURCE_IGNORED_TOPLEVEL = {"_drafts"}
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".svg", ".gif", ".webp"}


def file_hash(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


# Source articles cross-link via `/articles/<slug>/` and the bare index
# `/articles/` (the source repo's URL convention). On this site, articles
# live at `/field-notes/<slug>/` and the index is `/field-notes/`.
# `astro.config.mjs` registers per-slug redirects, but on GitHub Pages those
# resolve to a meta-refresh HTML shim — Search Console reports each one as
# "Page with redirect." Rewriting at sync time keeps the shims off the crawl
# path so internal links surface only canonical URLs.
_ARTICLE_LINK_RE = re.compile(r'\]\(/articles/(?:([a-z0-9-]+)/?)?(#[^)]*|\?[^)]*)?\)')


def rewrite_article_links(text: str) -> str:
    """Rewrite `](/articles/...)` → `](/field-notes/...)` in markdown link hrefs.

    Handles both the bare index `](/articles/)` → `](/field-notes/)` and the
    per-article form `](/articles/<slug>...)` → `](/field-notes/<slug>/...)`.
    Only matches markdown-link form so it can't rewrite the same path embedded
    in an external URL like `github.com/.../articles/<slug>/evidence/file.py`.
    Preserves anchors (`#fragment`) and query strings (`?key=value`).
    """
    def _sub(m: re.Match) -> str:
        slug = m.group(1)
        suffix = m.group(2) or ""
        if slug is None:
            return f"](/field-notes/{suffix})"
        return f"](/field-notes/{slug}/{suffix})"
    return _ARTICLE_LINK_RE.sub(_sub, text)


def copy_if_different(src: Path, dst: Path) -> bool:
    """Copy src→dst if dst is missing or content differs. Return True if copied."""
    if dst.exists() and file_hash(src) == file_hash(dst):
        return False
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    return True


def copy_article_if_different(src: Path, dst: Path) -> bool:
    """Copy article markdown with `/articles/<slug>/` → `/field-notes/<slug>/`
    rewrite applied. The mirror transform lives in `diff_articles.py` so the
    diff compares apples to apples.

    For articles whose target carries a Mac-owned trailing catalog footer,
    compare source against target-with-footer-stripped — if they match, the
    article is already in step and the gated footer is preserved by skipping
    the write. (Without this, every sync would clobber the footer and the
    restore step would re-add it, producing a phantom write every run.)"""
    new_text = rewrite_article_links(src.read_text(encoding="utf8"))
    if dst.exists():
        existing = dst.read_text(encoding="utf8")
        comparison = existing
        slug = dst.parent.name
        if slug in chrome_footers.collect_gated_articles():
            comparison = chrome_footers.strip_footer(existing).rstrip() + "\n"
            new_for_compare = new_text.rstrip() + "\n"
        else:
            new_for_compare = new_text
        if comparison == new_for_compare:
            return False
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(new_text, encoding="utf8")
    s = src.stat()
    import os as _os
    _os.utime(dst, (s.st_atime, s.st_mtime))
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
        if copy_article_if_different(src_md, tgt_dir / "article.md"):
            counts["article"] += 1
    elif src_mdx.exists():
        if copy_article_if_different(src_mdx, tgt_dir / "article.mdx"):
            counts["article"] += 1
    elif seed_md.exists():
        # No real article yet; promote seed.md → article.md so the upcoming
        # placeholder shows up in the collection.
        if copy_article_if_different(seed_md, tgt_dir / "article.md"):
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


def restore_gated_footers() -> dict:
    """Re-append destination-owned trailing catalog footers after sync.

    See `chrome_footers.py` for the full ownership rationale. Briefly:
    Mac CC appends a trailing `**Catalog page:** [...](...)` block to any
    article that has a matching `src/content/artifacts/<slug>.yaml`
    manifest; source repo never writes this block, so a naive copy of
    source over target drops it every release.

    Strategy: scan destination manifests for the binding, strip any
    existing trailing footer from each matching article, append the
    canonical one. Idempotent — no-op when target already matches.
    """
    counts = {"footer_restored": 0}
    gated = chrome_footers.collect_gated_articles()
    if not gated:
        return counts
    for article_slug, footer in gated.items():
        article_path = TARGET_ROOT / article_slug / "article.md"
        if not article_path.exists():
            continue
        current = article_path.read_text(encoding="utf8")
        new = chrome_footers.strip_footer(current).rstrip() + footer
        if current != new:
            article_path.write_text(new, encoding="utf8")
            counts["footer_restored"] += 1
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


def sync_signature_svgs() -> dict:
    """Copy new and changed signature SVG components source→target.

    One-way flow only: never deletes target-only signatures (the website may
    have signatures the source doesn't, e.g., for reframed research papers).
    """
    counts = {"signature_svg": 0}
    if not SIGNATURE_SVG_SOURCE.is_dir():
        return counts
    SIGNATURE_SVG_TARGET.mkdir(parents=True, exist_ok=True)
    for src in SIGNATURE_SVG_SOURCE.glob("*.astro"):
        if copy_if_different(src, SIGNATURE_SVG_TARGET / src.name):
            counts["signature_svg"] += 1
    return counts


def _apply_recall_at_5_override(stats: dict) -> dict:
    """Re-apply the website's override on metrics.accuracy[].

    The auto-generator orders accuracy metrics by article-recency, but the
    homepage KPI tile and the /field-notes/ "At a glance" block both read
    index 0. The recall@5 = 1.0 result from bigger-generator-grounding-on-spark
    is a more flattering, equally-citable headline than raw accuracy
    percentages out of context, so the website pins it to position 0 with a
    cleaned label. Match by (article_slug, value) so re-ordering in source
    doesn't silently break the override.
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


def sync_project_stats() -> dict:
    """Copy source project-stats.json → target with the override re-applied.

    Idempotent: writes only when the post-override JSON differs from target.
    The source is auto-regenerated on every release of ai-field-notes, so this
    is the bridge that keeps the website's "At a glance" KPIs current.
    """
    counts = {"project_stats": 0}
    if not PROJECT_STATS_SOURCE.exists():
        return counts
    try:
        src = json.loads(PROJECT_STATS_SOURCE.read_text(encoding="utf8"))
    except json.JSONDecodeError:
        return counts
    src = _apply_recall_at_5_override(src)
    new_text = json.dumps(src, indent=2) + "\n"
    if PROJECT_STATS_TARGET.exists():
        if PROJECT_STATS_TARGET.read_text(encoding="utf8") == new_text:
            return counts
    PROJECT_STATS_TARGET.parent.mkdir(parents=True, exist_ok=True)
    PROJECT_STATS_TARGET.write_text(new_text, encoding="utf8")
    counts["project_stats"] = 1
    return counts


def _compute_source_sequence() -> list[str] | None:
    """Read the source repo's git history and return article slugs in
    first-add order. Slugs whose article.md no longer exists in source
    (renamed or deleted) are dropped. Returns None if source isn't a git
    checkout or git is unavailable — caller treats this as "skip the
    manifest write" and the website falls back to local-git derivation.
    """
    try:
        proc = subprocess.run(
            [
                "git",
                "log",
                "--diff-filter=A",
                "--name-only",
                "--pretty=format:%at",
                "--reverse",
                "--",
                "articles/*/article.md",
            ],
            cwd=SOURCE_REPO,
            capture_output=True,
            text=True,
            check=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None

    sequence: list[str] = []
    seen: set[str] = set()
    for line in proc.stdout.split("\n"):
        trimmed = line.strip()
        if not trimmed or trimmed.isdigit():
            continue
        if not (trimmed.startswith("articles/") and trimmed.endswith("/article.md")):
            continue
        slug = trimmed[len("articles/") : -len("/article.md")]
        if slug in seen or slug in SOURCE_IGNORED_TOPLEVEL:
            continue
        if not (SOURCE_ROOT / slug / "article.md").exists():
            continue
        seen.add(slug)
        sequence.append(slug)
    return sequence


def write_sequence_manifest() -> dict:
    """Write src/data/field-notes/sequence.json from source git order.

    Idempotent: rewrites the file only when the ordered slug list changes,
    so a no-op sync produces no diff on this file. Provenance (when did the
    sequence last change?) is recoverable from `git log` on the manifest
    itself — no synced_at field is stored, since that would make every
    sync produce a noisy timestamp-only diff.
    """
    counts = {"sequence_manifest": 0}
    sequence = _compute_source_sequence()
    if sequence is None:
        return counts

    manifest = {
        "version": 1,
        "source": "ai-field-notes",
        "sequence": sequence,
    }
    new_text = json.dumps(manifest, indent=2) + "\n"

    if SEQUENCE_MANIFEST.exists():
        try:
            existing = json.loads(SEQUENCE_MANIFEST.read_text(encoding="utf8"))
        except json.JSONDecodeError:
            existing = None
        if (
            isinstance(existing, dict)
            and existing.get("version") == manifest["version"]
            and existing.get("sequence") == manifest["sequence"]
        ):
            return counts

    SEQUENCE_MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    SEQUENCE_MANIFEST.write_text(new_text, encoding="utf8")
    counts["sequence_manifest"] = 1
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
    sig_counts = sync_signature_svgs()
    seq_counts = write_sequence_manifest()
    stats_counts = sync_project_stats()
    footer_counts = restore_gated_footers()

    print(f"# Field Notes sync — applied")
    print(f"  articles source: {SOURCE_ROOT}")
    print(f"  articles target: {TARGET_ROOT}")
    print()
    nothing_articles = not touched_slugs
    nothing_fieldkit = not any(fk_counts.values())
    nothing_landing = not any(landing_counts.values())
    nothing_sig = not any(sig_counts.values())
    nothing_seq = not any(seq_counts.values())
    nothing_stats = not any(stats_counts.values())
    nothing_footer = not any(footer_counts.values())
    if (
        nothing_articles
        and nothing_fieldkit
        and nothing_landing
        and nothing_sig
        and nothing_seq
        and nothing_stats
        and nothing_footer
    ):
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
    if sig_counts["signature_svg"]:
        print(
            f"  • src/components/field-notes/svg/: "
            f"{sig_counts['signature_svg']} signature component(s) updated"
        )
    if seq_counts["sequence_manifest"]:
        print("  • src/data/field-notes/sequence.json: source order changed")
    if stats_counts["project_stats"]:
        print("  • src/data/field-notes/project-stats.json: refreshed (override re-applied)")
    if footer_counts["footer_restored"]:
        print(
            f"  • articles/<n>/article.md: {footer_counts['footer_restored']} "
            f"gated catalog footer(s) restored (Mac-owned chrome)"
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
    for k, v in sig_counts.items():
        if v:
            print(f"  {k}: {v}")
    for k, v in seq_counts.items():
        if v:
            print(f"  {k}: {v}")
    for k, v in stats_counts.items():
        if v:
            print(f"  {k}: {v}")
    for k, v in footer_counts.items():
        if v:
            print(f"  {k}: {v}")

    print()
    print("Next: run `npm run build` to verify, then preview /field-notes/ and /fieldkit/.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
