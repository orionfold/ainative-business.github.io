#!/usr/bin/env python3
"""
Source-repo resolution for the sync-field-notes skill.

The field-notes source lives at https://github.com/manavsehgal/ai-field-notes.
This skill syncs from a *local cache clone* of that remote — not from the old
SMB mount at /Volumes/home/ai-field-notes. The remote is the single source of
truth, kept current by Spark pushing to origin/main; the Mac never reads
Spark's working tree over the network, which removes the smbfs stale-handle /
torn-write / peer-writer-lock machinery entirely.

This module is the one place that defines:
  - where the cache clone lives (env-overridable),
  - the remote URL + branch (env-overridable),
  - every source-side path the diff/sync scripts read,
  - ensure_fresh(): clone-or-fetch the cache to origin/<branch>.

diff_articles.py and sync_articles.py import the path names from here, so
there is exactly one place to change if the layout ever moves again.

Env knobs (defaults in parentheses):
  AI_FIELD_NOTES_SRC     (~/.cache/ai-field-notes-src)                 cache clone location
  AI_FIELD_NOTES_REMOTE  (https://github.com/manavsehgal/ai-field-notes.git)  git remote URL
  AI_FIELD_NOTES_BRANCH  (main)                                        branch to track

Run directly as the Step 1 bootstrap:
    python3 .claude/skills/sync-field-notes/scripts/source_repo.py
"""

import os
import subprocess
import sys
from pathlib import Path

REMOTE_URL = os.environ.get(
    "AI_FIELD_NOTES_REMOTE",
    "https://github.com/manavsehgal/ai-field-notes.git",
)
BRANCH = os.environ.get("AI_FIELD_NOTES_BRANCH", "main")
SOURCE_REPO = Path(
    os.environ.get(
        "AI_FIELD_NOTES_SRC",
        str(Path.home() / ".cache" / "ai-field-notes-src"),
    )
).expanduser()

# Derived source paths — every surface the skill mirrors. Kept in sync with the
# "Source and target paths" table in SKILL.md.
SOURCE_ROOT = SOURCE_REPO / "articles"
FIELDKIT_DOCS_SOURCE = SOURCE_REPO / "fieldkit" / "docs" / "api"
FIELDKIT_VERSION_SOURCE = SOURCE_REPO / "fieldkit" / "src" / "fieldkit" / "_version.py"
LANDING_SOURCE = SOURCE_REPO / "src" / "pages" / "fieldkit" / "index.astro"
SIGNATURE_SVG_SOURCE = SOURCE_REPO / "src" / "components" / "svg"
PROJECT_STATS_SOURCE = SOURCE_REPO / "src" / "data" / "project-stats.json"


def _run(args: list[str], cwd: Path | None = None, capture: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(
        args,
        cwd=str(cwd) if cwd else None,
        check=True,
        capture_output=capture,
        text=True,
    )


def is_clone() -> bool:
    return (SOURCE_REPO / ".git").is_dir()


def head_info() -> tuple[str, str]:
    """(short_sha, subject) of the cache clone's current HEAD."""
    sha = _run(["git", "rev-parse", "--short", "HEAD"], cwd=SOURCE_REPO).stdout.strip()
    subj = _run(["git", "log", "-1", "--pretty=%s"], cwd=SOURCE_REPO).stdout.strip()
    return sha, subj


def ensure_fresh(verbose: bool = True) -> tuple[str, str]:
    """Clone the cache clone if absent, else fetch + hard-reset to origin/<branch>.

    Returns (short_sha, subject) of the resulting HEAD. Raises
    subprocess.CalledProcessError on any git failure (e.g. remote unreachable).
    A hard reset is deliberate: the cache is a disposable mirror of the remote,
    never edited in place except by Step 6 (which commits + pushes before the
    next sync resets).
    """
    if not is_clone():
        if SOURCE_REPO.exists() and any(SOURCE_REPO.iterdir()):
            raise RuntimeError(
                f"{SOURCE_REPO} exists but is not a git clone — remove it or set "
                f"AI_FIELD_NOTES_SRC to a clean path."
            )
        SOURCE_REPO.parent.mkdir(parents=True, exist_ok=True)
        if verbose:
            print(f"[source] cloning {REMOTE_URL} -> {SOURCE_REPO}")
        _run(["git", "clone", REMOTE_URL, str(SOURCE_REPO)], capture=not verbose)
    else:
        if verbose:
            print(f"[source] fetching origin/{BRANCH} into {SOURCE_REPO}")
    _run(["git", "fetch", "--prune", "origin", BRANCH], cwd=SOURCE_REPO, capture=not verbose)
    _run(["git", "reset", "--hard", f"origin/{BRANCH}"], cwd=SOURCE_REPO, capture=not verbose)
    sha, subj = head_info()
    if verbose:
        print(f"[source] HEAD {sha} {subj}")
    return sha, subj


def main() -> int:
    try:
        ensure_fresh()
    except subprocess.CalledProcessError as e:
        print(f"ERROR: git failed ({e.returncode}). Is the remote reachable?", file=sys.stderr)
        if e.stderr:
            print(e.stderr.strip(), file=sys.stderr)
        return 2
    except RuntimeError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
