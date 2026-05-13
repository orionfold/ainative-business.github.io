#!/usr/bin/env python3
"""
Contract-aware sweep helpers for the sync-field-notes skill.

Five capabilities deferred from the 2026-05-11 a2tgpo handoff §B, batched here
as one module so the SKILL.md workflow Step 5a can drive them mechanically:

  1. parse_handoff_frontmatter — read SYNC-HANDOFF.md's YAML frontmatter (if
     present); fall back to None so prose-only releases still work.
  2. replay_renames           — read SYNC-RENAMES.log, find entries with
     status == destination-needs-replay, apply mechanical renames across
     articles/** and surface high-judgement (prose) mentions for brainstorm.
  3. is_destination_owned     — read mirrors/destination-overrides.md and
     check whether a given path lives under a Mac-authoritative glob. Gates
     every other capability so source can't stomp /book/, /pricing/, etc.
  4. check_artifacts_phase2   — no-op stub until src/content/artifacts/ shows
     up in source (lands with fieldkit v0.4 + fieldkit.publish module).
  5. flip_handoff_to_shipped  — produce the edit + PR-body text that flips
     STATUS: NEW → STATUS: SHIPPED in source's SYNC-HANDOFF.md.

The actual cross-repo PR opens (capabilities 2 and 5) are NOT done by this
module — those need user approval per `feedback_work_on_main` and the skill's
overall "scripts do mechanical work, Claude opens PRs at runtime" split.
The module returns structured plan objects; the CLI in `contract_sweep.py`
prints them; Claude opens the PRs via `gh` with user approval.
"""

from __future__ import annotations

import fnmatch
import re
import subprocess
from dataclasses import MISSING, dataclass, field
from pathlib import Path
from typing import Iterable

import yaml

SOURCE_REPO = Path("/Users/manavsehgal/Developer/ai-field-notes")
TARGET_REPO = Path("/Users/manavsehgal/Developer/ainative-business.github.io")

SOURCE_HANDOFF = SOURCE_REPO / "SYNC-HANDOFF.md"
SOURCE_RENAMES_LOG = SOURCE_REPO / "SYNC-RENAMES.log"
SOURCE_OVERRIDES = SOURCE_REPO / "mirrors" / "destination-overrides.md"
SOURCE_ARTIFACTS_DIR = SOURCE_REPO / "src" / "content" / "artifacts"

TARGET_ARTICLES = TARGET_REPO / "articles"

FRONTMATTER_FENCE = "---"


# ─────────────────────────────── Capability #1 ───────────────────────────────
# YAML frontmatter parser for SYNC-HANDOFF.md.

@dataclass
class HandoffFrontmatter:
    """Structured slice of SYNC-HANDOFF.md, when the file carries YAML
    frontmatter. Every field defaults to its empty form so consumers can read
    `fm.articles_added` without guarding on key presence. `release_slug` and
    `status` are the only fields the schema makes load-bearing; everything
    else is advisory delta."""

    release_slug: str = ""
    status: str = ""
    source_range: str = ""
    articles_added: list[str] = field(default_factory=list)
    articles_updated: list[str] = field(default_factory=list)
    artifacts_added: list[str] = field(default_factory=list)
    artifacts_updated: list[str] = field(default_factory=list)
    fieldkit_modules_changed: list[str] = field(default_factory=list)
    renames_to_replay: list[str] = field(default_factory=list)
    removes: list[str] = field(default_factory=list)
    new_top_level_pages: list[str] = field(default_factory=list)
    breaking_changes: list[str] = field(default_factory=list)
    destination_overrides_to_preserve: list[str] = field(default_factory=list)
    hf_repos_added: list[str] = field(default_factory=list)
    civitai_artifacts_added: list[str] = field(default_factory=list)
    raw: dict = field(default_factory=dict)


def parse_handoff_frontmatter(path: Path = SOURCE_HANDOFF) -> HandoffFrontmatter | None:
    """Return parsed frontmatter if the file leads with a `---\\n...\\n---`
    YAML block, else None. None means the caller should fall back to the
    skill's existing semantic prose walk (Step 2 in SKILL.md)."""
    if not path.exists():
        return None
    text = path.read_text(encoding="utf8")
    fm_dict = _extract_yaml_frontmatter(text)
    if fm_dict is None:
        return None
    known = {f.name for f in HandoffFrontmatter.__dataclass_fields__.values()} - {"raw"}
    init_kwargs = {k: fm_dict.get(k, _default_for(k)) for k in known}
    init_kwargs["raw"] = fm_dict
    return HandoffFrontmatter(**init_kwargs)


def _extract_yaml_frontmatter(text: str) -> dict | None:
    """Pop the leading `---\\n...\\n---` block (skipping any HTML comment
    preamble — the current handoff format opens with a `<!-- ... -->` block
    documenting the file rotation policy). Returns the parsed dict or None
    if no frontmatter is present."""
    cursor = 0
    if text.lstrip().startswith("<!--"):
        end = text.find("-->", cursor)
        if end == -1:
            return None
        cursor = end + 3
    rest = text[cursor:].lstrip("\n")
    if not rest.startswith(FRONTMATTER_FENCE + "\n") and not rest.startswith(FRONTMATTER_FENCE + "\r\n"):
        return None
    body_start = rest.find("\n") + 1
    body_end = rest.find("\n" + FRONTMATTER_FENCE, body_start)
    if body_end == -1:
        return None
    yaml_body = rest[body_start:body_end]
    try:
        data = yaml.safe_load(yaml_body)
    except yaml.YAMLError:
        return None
    return data if isinstance(data, dict) else None


def _default_for(field_name: str):
    """Mirror HandoffFrontmatter's defaults for any field name. Dataclasses
    use a MISSING sentinel rather than None to signal "no default of this
    kind set," so check identity rather than truthiness."""
    f = HandoffFrontmatter.__dataclass_fields__[field_name]
    if f.default_factory is not MISSING:
        return f.default_factory()
    return f.default


# ─────────────────────────────── Capability #3 ───────────────────────────────
# Destination-overrides check — gates every other capability.

# The mirror file's "Top-level pages" and "Forthcoming top-level pages"
# sections each list one bullet per Mac-owned route glob. We extract the
# glob token between the leading "- `" and the next backtick. Anything outside
# those two sections (e.g. the prose explainer paragraphs) is ignored.
_OVERRIDE_BULLET_RE = re.compile(r"^\s*-\s+`([^`]+)`", re.MULTILINE)
_OVERRIDE_SECTION_RE = re.compile(
    r"## (?:Top-level pages|Forthcoming top-level pages)[^\n]*\n(.*?)(?=\n## |\Z)",
    re.DOTALL,
)


def read_destination_overrides(path: Path = SOURCE_OVERRIDES) -> list[str]:
    """Return the list of Mac-authoritative path globs declared in the
    source repo's `mirrors/destination-overrides.md`. Globs use shell-style
    wildcards (`*`, `**`) and lead with `/`. Returns [] if the file is
    missing — fail-open is safe because the no-clobber check below only
    *adds* skip behavior; an empty glob list means nothing is gated, which
    is the pre-contract baseline."""
    if not path.exists():
        return []
    text = path.read_text(encoding="utf8")
    globs: list[str] = []
    for section in _OVERRIDE_SECTION_RE.finditer(text):
        for m in _OVERRIDE_BULLET_RE.finditer(section.group(1)):
            globs.append(m.group(1))
    return globs


def is_destination_owned(rel_path: str, globs: Iterable[str]) -> bool:
    """Match a target-repo-relative path against the override globs. Both
    sides are normalized to leading-slash form so `/book/ch10.md` matches
    `/book/**`. `**` is translated to `*` for fnmatch's globstar-free
    semantics; for the patterns Mac actually publishes (`/book/**`,
    `/pricing/**`, `/artifacts/<kind>/`, `/skills/**`, `/`) this is
    sufficient — every override is "everything under this prefix" or the
    bare root."""
    candidate = rel_path if rel_path.startswith("/") else "/" + rel_path
    for raw_glob in globs:
        g = raw_glob.rstrip("/")
        if g == "":
            if candidate in ("/", "/index.html"):
                return True
            continue
        if g.endswith("/**"):
            prefix = g[:-3]
            if candidate == prefix or candidate.startswith(prefix + "/"):
                return True
            continue
        normalized = g.replace("**", "*")
        if fnmatch.fnmatch(candidate, normalized):
            return True
        if candidate.startswith(g + "/"):
            return True
    return False


# ─────────────────────────────── Capability #2 ───────────────────────────────
# SYNC-RENAMES.log replay.

@dataclass
class RenameEntry:
    """One row from SYNC-RENAMES.log, plus the sweep receipt populated when
    the destination side applies (or no-ops) the rename."""

    date: str
    kind: str
    old: str
    new: str
    affected: list[str]
    status: str
    raw: dict = field(default_factory=dict)


@dataclass
class RenameReplayResult:
    """What the script actually did for one entry. `mechanical_edits` lists
    every file the script rewrote (frontmatter or URL surfaces);
    `judgement_findings` lists files where the old identifier appears in
    prose, surfaced to Claude for the brainstorm — NOT auto-rewritten."""

    entry: RenameEntry
    mechanical_edits: list[Path] = field(default_factory=list)
    judgement_findings: list[Path] = field(default_factory=list)
    skipped_destination_owned: list[Path] = field(default_factory=list)
    error: str | None = None


def read_renames_log(path: Path = SOURCE_RENAMES_LOG) -> list[RenameEntry]:
    """Load every entry from SYNC-RENAMES.log. Comment-only headers are
    skipped automatically by `yaml.safe_load`. Returns [] if the file is
    missing (pre-contract releases)."""
    if not path.exists():
        return []
    text = path.read_text(encoding="utf8")
    data = yaml.safe_load(text)
    if not isinstance(data, list):
        return []
    out: list[RenameEntry] = []
    for row in data:
        if not isinstance(row, dict):
            continue
        out.append(
            RenameEntry(
                date=str(row.get("date", "")),
                kind=str(row.get("kind", "")),
                old=str(row.get("old", "")),
                new=str(row.get("new", "")),
                affected=list(row.get("affected") or []),
                status=str(row.get("status", "")),
                raw=row,
            )
        )
    return out


def pending_renames(entries: list[RenameEntry]) -> list[RenameEntry]:
    """Filter to only entries the destination still owes the source — i.e.
    `status: destination-needs-replay`. Everything else is already swept or
    is source-side bookkeeping."""
    return [e for e in entries if e.status == "destination-needs-replay"]


# Frontmatter scalar — handles bare, single-quoted, and double-quoted values
# on either the top-level `key: value` form or the array entry form.
# Lookups always happen against an exact key prefix to avoid false matches.
_FRONTMATTER_BLOCK_RE = re.compile(r"^---\n(.*?)\n---", re.DOTALL)


def _rewrite_frontmatter_scalar(text: str, key: str, old: str, new: str) -> tuple[str, bool]:
    """Rewrite `key: old` → `key: new` in the article's YAML frontmatter
    block, preserving any quoting style. Returns (new_text, changed)."""
    m = _FRONTMATTER_BLOCK_RE.match(text)
    if not m:
        return text, False
    fm = m.group(1)
    line_re = re.compile(
        rf"^(?P<indent>[ \t]*){re.escape(key)}:\s*(?P<q>['\"]?){re.escape(old)}(?P=q)\s*$",
        re.MULTILINE,
    )
    new_fm, n = line_re.subn(lambda mm: f"{mm.group('indent')}{key}: {new}", fm)
    if n == 0:
        return text, False
    return text[: m.start(1)] + new_fm + text[m.end(1) :], True


def _scan_prose_for_mention(text: str, old: str) -> bool:
    """Return True if `old` appears anywhere outside the frontmatter block."""
    fm_match = _FRONTMATTER_BLOCK_RE.match(text)
    body_start = fm_match.end() if fm_match else 0
    return old in text[body_start:]


def replay_renames(
    entries: list[RenameEntry],
    overrides: list[str],
    articles_root: Path = TARGET_ARTICLES,
    dry_run: bool = False,
) -> list[RenameReplayResult]:
    """Apply every pending rename mechanically to articles/**. The
    `overrides` list gates writes — any target path that matches a
    Mac-authoritative glob is skipped (the `articles/` tree is Spark-owned
    by SYNC-CONTRACT.md, so the override check is mostly defensive; it
    fires only if Mac later declares `articles/` paths off-limits).
    Returns one RenameReplayResult per entry."""
    results: list[RenameReplayResult] = []
    if not articles_root.is_dir():
        return results

    for entry in entries:
        result = RenameReplayResult(entry=entry)
        affected = {a.strip().lower() for a in entry.affected}
        targets_mechanical = _resolve_mechanical_surfaces(entry, affected)
        wants_prose_scan = "prose_mentions" in affected

        for article in sorted(articles_root.glob("*/article.md")) + sorted(
            articles_root.glob("*/article.mdx")
        ):
            rel = "/" + str(article.relative_to(TARGET_REPO))
            if is_destination_owned(rel, overrides):
                result.skipped_destination_owned.append(article)
                continue

            text = article.read_text(encoding="utf8")
            new_text = text
            changed = False

            for surface in targets_mechanical:
                if surface.startswith("frontmatter."):
                    key = surface.split(".", 1)[1]
                    new_text, did = _rewrite_frontmatter_scalar(new_text, key, entry.old, entry.new)
                    changed = changed or did

            if changed and not dry_run:
                article.write_text(new_text, encoding="utf8")
            if changed:
                result.mechanical_edits.append(article)

            if wants_prose_scan and _scan_prose_for_mention(new_text, entry.old):
                result.judgement_findings.append(article)

        results.append(result)
    return results


def _resolve_mechanical_surfaces(entry: RenameEntry, affected: set[str]) -> list[str]:
    """Translate `affected:` labels from the log into concrete mechanical
    surfaces the script knows how to rewrite deterministically. Surfaces
    not in this map (URLs, slugs, paths, etc.) stay in the judgement layer
    and are reported, not rewritten."""
    surfaces: list[str] = []
    if entry.kind == "series":
        if "frontmatter.series" in affected:
            surfaces.append("frontmatter.series")
    elif entry.kind == "tag":
        if "frontmatter.tags" in affected:
            surfaces.append("frontmatter.tags")
    elif entry.kind == "module":
        if "frontmatter.module" in affected:
            surfaces.append("frontmatter.module")
    return surfaces


# ─────────────────────────────── Capability #4 ───────────────────────────────
# /artifacts/<kind>/ catalog stub (Phase 2).

ARTIFACT_KINDS = (
    "quants",
    "loras",
    "adapters",
    "embedders",
    "datasets",
    "spaces",
    "benchmarks",
)


def check_artifacts_phase2(source_artifacts_dir: Path = SOURCE_ARTIFACTS_DIR) -> dict:
    """Return a status dict describing whether Phase 2 has begun. The skill
    no-ops until `src/content/artifacts/` exists in source. When it does, the
    return value carries the manifest count + the kinds present so Claude can
    scaffold catalog and detail pages at runtime (the scaffolding itself is
    judgement-heavy — page chrome, copy, design tokens — and lives outside
    this script)."""
    if not source_artifacts_dir.is_dir():
        return {"active": False, "manifests": 0, "kinds_present": []}
    manifests = list(source_artifacts_dir.rglob("*.yaml")) + list(
        source_artifacts_dir.rglob("*.yml")
    )
    kinds_present: set[str] = set()
    for m in manifests:
        try:
            data = yaml.safe_load(m.read_text(encoding="utf8"))
        except yaml.YAMLError:
            continue
        if isinstance(data, dict) and data.get("kind") in ARTIFACT_KINDS:
            kinds_present.add(data["kind"])
    return {
        "active": True,
        "manifests": len(manifests),
        "kinds_present": sorted(kinds_present),
    }


# ─────────────────────────────── Capability #5 ───────────────────────────────
# SYNC-HANDOFF.md status flip (STATUS: NEW → STATUS: SHIPPED).

_HANDOFF_STATUS_RE = re.compile(r"⚠️\s*STATUS:\s*NEW")


@dataclass
class HandoffFlipPlan:
    """Edit + PR body the caller (Claude, with user approval) executes
    against the source repo. The script never writes to the source repo
    directly — `feedback_work_on_main` keeps Mac side as primary working
    tree, and cross-repo writes are user-controlled."""

    needs_flip: bool
    new_text: str
    pr_title: str
    pr_body: str
    error: str | None = None


def flip_handoff_to_shipped(
    destination_commit_hash: str,
    handoff_path: Path = SOURCE_HANDOFF,
    release_slug: str | None = None,
) -> HandoffFlipPlan:
    """Produce the SYNC-HANDOFF.md edit + PR scaffold that flips the status
    marker from NEW → SHIPPED. The caller writes the edit upstream via a
    PR; this function never mutates the source repo on its own. If the
    marker is already SHIPPED or absent, `needs_flip` is False and the
    caller skips the PR."""
    if not handoff_path.exists():
        return HandoffFlipPlan(False, "", "", "", error="SYNC-HANDOFF.md missing")
    text = handoff_path.read_text(encoding="utf8")
    if not _HANDOFF_STATUS_RE.search(text):
        return HandoffFlipPlan(False, text, "", "", error="STATUS: NEW marker not found")
    new_text = _HANDOFF_STATUS_RE.sub("⚠️ STATUS: SHIPPED", text, count=1)
    slug_part = f" — {release_slug}" if release_slug else ""
    pr_title = f"mirror: SYNC-HANDOFF.md SHIPPED{slug_part} ({destination_commit_hash[:7]})"
    pr_body = (
        f"Mac CC swept this release at destination commit `{destination_commit_hash}`. "
        "Flipping STATUS marker so the next release rotation has a clean signal.\n\n"
        "Companion PR: SYNC-RENAMES.log status flips, if any pending renames were "
        "replayed in this sweep.\n"
    )
    return HandoffFlipPlan(True, new_text, pr_title, pr_body)


# ───────────────────────────── Shared utilities ──────────────────────────────


def destination_commit_hash() -> str:
    """Current HEAD of the destination repo. Used to stamp PR bodies + the
    `swept_by` field in SYNC-RENAMES.log status flips (per the 2026-05-12
    receipt PR convention)."""
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=TARGET_REPO,
            check=True,
            capture_output=True,
            text=True,
        )
        return out.stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return "unknown"
