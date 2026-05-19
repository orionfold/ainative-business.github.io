"""
Gated trailing-catalog-footer chrome helpers.

The website (Mac-authoritative) appends a single trailing
`**Catalog page:** [...](...) — ...` block at the tail of articles whose
catalog manifests live at `src/content/artifacts/<slug>.yaml`. Source repo
never carries this block (it's destination chrome pointing at destination
URLs), so a naive `cp source → target` clobbers it every release.

This module owns:

1. The footer-text template (one constant, easy to evolve per kind).
2. A `kind:` → URL-family map (`quant` → `quants/`, etc.).
3. `collect_gated_articles()` — reads destination manifests and returns
   `{article_slug: expected_footer_text}` for every article with a manifest.
4. `_FOOTER_REMOVE_RE` — strips any existing trailing footer before
   re-appending so the operation is idempotent on repeat runs.

Both `sync_articles.py` (post-sync re-append) and `diff_articles.py`
(pre-compare strip) import from here so they agree on the boundary.

Per `mirrors/destination-overrides.md` "Article-body overrides (narrow,
gated)" section in the source repo: Spark CC never writes this block;
Mac CC owns it end-to-end.
"""

from __future__ import annotations

import re
from pathlib import Path

try:
    import yaml  # type: ignore[import-not-found]
except ImportError:  # pragma: no cover — yaml is a hard dep of contract.py too
    yaml = None  # type: ignore[assignment]

REPO_ROOT = Path("/Users/manavsehgal/Developer/ainative-business.github.io")
ARTIFACTS_DIR = REPO_ROOT / "src/content/artifacts"

# Maps the `kind:` field of an artifact manifest to the URL family Mac owns
# under `/artifacts/`. Must mirror `kindToSegment` in `src/lib/artifacts.ts`
# (the destination's source of truth for URL paths). Add new entries here
# when a new ARTIFACT_KIND ships its first manifest + catalog page.
_KIND_TO_URL_FAMILY: dict[str, str] = {
    "quant": "quants",
    "lora": "loras",
    "adapter": "adapters",
    "embed": "embeds",
    "reranker": "rerankers",
    "dataset": "datasets",
    "space": "spaces",
    "bench": "benches",
}

# Per-kind footer template. Defaults to the quant text (four-axis card +
# sweet-spot heatmap row); each non-quant kind that ships a detail page
# overrides the inner blurb here so the footer points at what the destination
# actually renders.
_DEFAULT_BLURB = (
    "the same four-axis card rendered on this site, "
    "with the sweet-spot variant highlighted on a heatmap row."
)
_BLURB_BY_KIND: dict[str, str] = {
    "bench": (
        "three-mode bracket results, shape composition, sample rows per "
        "shape, and source provenance — the full bench card."
    ),
}

_FOOTER_PREFIX = "\n\n---\n\n**Catalog page:** [`{url}`]({url}) — "

# Matches the trailing catalog footer for idempotent strip-before-replace.
# Anchored to end-of-string; tolerant of variant whitespace between blocks.
_FOOTER_REMOVE_RE = re.compile(
    r"\n+---\s*\n+\*\*Catalog page:\*\* \[[^\]]+\]\([^)]+\)[^\n]*\n*\Z",
    re.MULTILINE,
)

# Match `articles/<slug>/` or `articles/<slug>` in the manifest's `article:` field.
_ARTICLE_FIELD_RE = re.compile(r"^articles/([^/]+)/?$")


def build_catalog_footer(kind: str, artifact_slug: str) -> str | None:
    """Return the trailing footer block for an artifact, or None if `kind` is
    unmapped (defensive — better to skip than emit a broken URL)."""
    family = _KIND_TO_URL_FAMILY.get(kind)
    if family is None:
        return None
    url = f"/artifacts/{family}/{artifact_slug}/"
    blurb = _BLURB_BY_KIND.get(kind, _DEFAULT_BLURB)
    return _FOOTER_PREFIX.format(url=url) + blurb + "\n"


_GATED_CACHE: dict[str, str] | None = None


def collect_gated_articles() -> dict[str, str]:
    """Scan destination artifact manifests; return {article_slug: footer_text}.

    Memoized at module level — sync's article loop calls this per-slug, so
    the YAML re-parse cost would otherwise scale with the article count.

    Skips manifests whose `kind:` is unmapped, whose `article:` doesn't point
    at an `articles/<slug>/` path, or whose YAML fails to parse. Empty dict
    when the artifacts collection doesn't exist yet (pre-Phase-2 baseline).
    """
    global _GATED_CACHE
    if _GATED_CACHE is not None:
        return _GATED_CACHE
    if yaml is None or not ARTIFACTS_DIR.is_dir():
        _GATED_CACHE = {}
        return _GATED_CACHE
    out: dict[str, str] = {}
    for yaml_path in sorted(ARTIFACTS_DIR.glob("*.yaml")):
        try:
            data = yaml.safe_load(yaml_path.read_text(encoding="utf8"))
        except yaml.YAMLError:
            continue
        if not isinstance(data, dict):
            continue
        kind = data.get("kind")
        article_field = data.get("article", "")
        artifact_slug = data.get("slug") or yaml_path.stem
        if not isinstance(kind, str) or not isinstance(article_field, str):
            continue
        m = _ARTICLE_FIELD_RE.match(article_field.strip())
        if not m:
            continue
        footer = build_catalog_footer(kind, str(artifact_slug))
        if footer is None:
            continue
        out[m.group(1)] = footer
    _GATED_CACHE = out
    return _GATED_CACHE


def strip_footer(text: str) -> str:
    """Remove a trailing catalog footer (if any) from article text.

    Returns text without the footer, preserving everything up to (but not
    including) the footer's leading whitespace. Used by `diff_articles.py`
    to compare apples-to-apples (target carries footer, source doesn't).
    """
    return _FOOTER_REMOVE_RE.sub("", text)
