#!/usr/bin/env python3
"""
Contract-aware sweep CLI for the sync-field-notes skill.

Runs the mechanical layer of the 2026-05-11 a2tgpo §B capabilities in order:

  1. Read destination-overrides (gate for everything else).
  2. Parse SYNC-HANDOFF.md YAML frontmatter (if present; None → prose path).
  3. Replay SYNC-RENAMES.log entries with status == destination-needs-replay.
  4. Check whether Phase 2 artifacts collection has appeared in source yet.
  5. Plan the SYNC-HANDOFF.md SHIPPED status flip (for Claude to PR upstream).

The CLI prints a structured report (text). It NEVER opens cross-repo PRs —
those happen at runtime via `gh`, after user approval per `feedback_work_on_main`.

Run from the website project root:
    python3 .claude/skills/sync-field-notes/scripts/contract_sweep.py
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# When invoked as `python3 .claude/skills/.../contract_sweep.py`, the script
# directory isn't on sys.path. Add it so `import contract` resolves to the
# sibling module without forcing a package layout.
sys.path.insert(0, str(Path(__file__).resolve().parent))

import contract  # noqa: E402


def _format_overrides(globs: list[str]) -> str:
    if not globs:
        return "  (no overrides declared — fail-open, nothing gated)"
    return "\n".join(f"  - {g}" for g in globs)


def _format_handoff(fm: contract.HandoffFrontmatter | None) -> str:
    if fm is None:
        return (
            "  (no YAML frontmatter — falling back to Step 2's prose walk; "
            "this is expected for releases on or before 2026-05-11)"
        )
    lines = [
        f"  release_slug: {fm.release_slug or '(unset)'}",
        f"  status:       {fm.status or '(unset)'}",
        f"  source_range: {fm.source_range or '(unset)'}",
    ]
    for key in (
        "articles_added",
        "articles_updated",
        "artifacts_added",
        "artifacts_updated",
        "fieldkit_modules_changed",
        "renames_to_replay",
        "removes",
        "new_top_level_pages",
        "breaking_changes",
        "destination_overrides_to_preserve",
        "hf_repos_added",
        "civitai_artifacts_added",
    ):
        val = getattr(fm, key)
        if val:
            lines.append(f"  {key}: {val}")
    return "\n".join(lines)


def _format_rename_result(r: contract.RenameReplayResult) -> str:
    e = r.entry
    head = f"  [{e.date}] {e.kind}: {e.old!r} → {e.new!r}"
    parts = [head]
    if r.error:
        parts.append(f"    ERROR: {r.error}")
        return "\n".join(parts)
    if r.mechanical_edits:
        parts.append(f"    mechanical edits ({len(r.mechanical_edits)}):")
        for p in r.mechanical_edits:
            parts.append(f"      • {p.relative_to(contract.TARGET_REPO)}")
    else:
        parts.append("    mechanical edits: (none — frontmatter already swept or N/A)")
    if r.judgement_findings:
        parts.append(
            f"    prose mentions surfaced for brainstorm ({len(r.judgement_findings)}):"
        )
        for p in r.judgement_findings:
            parts.append(f"      • {p.relative_to(contract.TARGET_REPO)}")
    if r.skipped_destination_owned:
        parts.append(
            f"    skipped (destination-owned) ({len(r.skipped_destination_owned)}):"
        )
        for p in r.skipped_destination_owned:
            parts.append(f"      • {p.relative_to(contract.TARGET_REPO)}")
    return "\n".join(parts)


def _format_artifacts(status: dict) -> str:
    if not status["active"]:
        return (
            "  Phase 2 inactive — src/content/artifacts/ has not appeared in source yet. "
            "No scaffolding to do this run."
        )
    return (
        f"  Phase 2 ACTIVE — {status['manifests']} manifest(s) found across "
        f"kinds: {status['kinds_present']}\n"
        "  Hand off to Claude to scaffold /artifacts/<kind>/ catalog + detail pages "
        "(judgement layer)."
    )


def _format_flip(plan: contract.HandoffFlipPlan) -> str:
    if plan.error and not plan.needs_flip:
        return f"  No flip needed: {plan.error}"
    if not plan.needs_flip:
        return "  No flip needed (handoff already SHIPPED or marker missing)."
    return (
        "  Flip ready — Claude should open a PR against source with:\n"
        f"    title: {plan.pr_title}\n"
        "    body:\n"
        + "\n".join(f"      {ln}" for ln in plan.pr_body.splitlines())
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Scan and report only; do not write rename edits to disk.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit a machine-readable summary line (one JSON object) after the "
        "human-readable report. Useful for skill orchestration.",
    )
    args = parser.parse_args()

    overrides = contract.read_destination_overrides()
    fm = contract.parse_handoff_frontmatter()
    entries = contract.read_renames_log()
    pending = contract.pending_renames(entries)
    artifacts = contract.check_artifacts_phase2()
    commit = contract.destination_commit_hash()
    release_slug = fm.release_slug if fm else None
    flip = contract.flip_handoff_to_shipped(
        destination_commit_hash=commit, release_slug=release_slug
    )
    results = contract.replay_renames(
        pending, overrides=overrides, dry_run=args.dry_run
    )

    print("contract sweep — destination overrides")
    print(_format_overrides(overrides))
    print()
    print("contract sweep — handoff frontmatter")
    print(_format_handoff(fm))
    print()
    print(f"contract sweep — pending renames ({len(pending)} of {len(entries)} total)")
    if not pending:
        print("  (none — every rename in SYNC-RENAMES.log is already `complete` "
              "or `source-applied`)")
    else:
        for r in results:
            print(_format_rename_result(r))
    print()
    print("contract sweep — artifacts Phase 2 stub")
    print(_format_artifacts(artifacts))
    print()
    print("contract sweep — handoff SHIPPED flip plan")
    print(_format_flip(flip))

    if args.json:
        import json

        summary = {
            "destination_commit": commit,
            "overrides_count": len(overrides),
            "frontmatter_present": fm is not None,
            "release_slug": release_slug,
            "renames_total": len(entries),
            "renames_pending": len(pending),
            "renames_with_edits": sum(1 for r in results if r.mechanical_edits),
            "renames_with_prose_findings": sum(
                1 for r in results if r.judgement_findings
            ),
            "artifacts_phase2_active": artifacts["active"],
            "artifacts_manifest_count": artifacts["manifests"],
            "handoff_flip_needed": flip.needs_flip,
            "dry_run": args.dry_run,
        }
        print()
        print(json.dumps(summary))
    return 0


if __name__ == "__main__":
    sys.exit(main())
