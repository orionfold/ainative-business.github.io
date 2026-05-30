#!/usr/bin/env python3
# Copyright 2026 Manav Sehgal
# SPDX-License-Identifier: Apache-2.0
"""Human-review CLI for patent-strategist seed rows.

Walks unreviewed rows in one or more per-shape JSONL files written by
`scripts/seed_patent_bench.py` and lets the reviewer:

    a   accept              — mark reviewed=True (keep gold_label as-is)
    e   edit                — re-enter gold_label / rubric_notes, then accept
    r   reject              — reviewed=True + tags.rejected=True (T10 should skip)
    s   skip                — leave unreviewed; the row resurfaces on next run
    p   previous            — re-open the row you just decided on (session-local undo)
    o   open oracle         — print the full oracle_context (default truncates at 1.5k)
    n   add rubric note     — append to tags.rubric_notes without changing gold_label
    q   quit                — save + exit

Output schema additions (vs. the seeder):

    row["reviewed"]              = True/False                  # top-level, was already in schema
    row["tags"]["rejected"]      = True                        # only on reject
    row["tags"]["reviewed_by"]   = "<reviewer>"                # if --reviewer passed
    row["tags"]["reviewed_at"]   = "<ISO-8601 UTC>"
    row["rubric"]                = "<reviewer-supplied>"       # optional; was None in seed

Atomic save: per decision, the file is rewritten to a sibling `.tmp` and
os.replace'd into place. Crash-safe; loses at most the row in flight.

Prioritization: by default, rows tagged `source_status=synthesized` surface
first within each file (per the seeder handoff — these need more eyeballs
than `anchored` rows). Use `--no-prioritize-synthesized` to keep file order.

Examples
--------

    # Walk D-mcq, default order (synthesized first, then anchored):
    python scripts/review_patent_bench.py --shape D-mcq --reviewer manav

    # Review every file, only the synthesized rows, in order:
    python scripts/review_patent_bench.py --all --source-status synthesized

    # Re-review already-accepted rows (e.g. policy change):
    python scripts/review_patent_bench.py --shape A --include-reviewed
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
import textwrap
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

DEFAULT_BENCH_DIR = Path("/home/nvidia/data/eval-benches/patent-strategist")
SHAPE_FILES = ["A", "B", "C", "D-mcq", "D-oa", "D-irac", "E"]


# --- terminal styling (stdlib only, ANSI escapes) ------------------------

def _supports_color() -> bool:
    return sys.stdout.isatty() and os.environ.get("TERM", "") != "dumb"


_USE_COLOR = _supports_color()


def _ansi(s: str, code: str) -> str:
    if not _USE_COLOR:
        return s
    return f"\033[{code}m{s}\033[0m"


def bold(s: str) -> str: return _ansi(s, "1")
def dim(s: str) -> str: return _ansi(s, "2")
def red(s: str) -> str: return _ansi(s, "31")
def green(s: str) -> str: return _ansi(s, "32")
def yellow(s: str) -> str: return _ansi(s, "33")
def blue(s: str) -> str: return _ansi(s, "34")
def magenta(s: str) -> str: return _ansi(s, "35")
def cyan(s: str) -> str: return _ansi(s, "36")


# --- I/O ----------------------------------------------------------------


def _iter_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open() as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    return rows


def atomic_write_jsonl(rows: list[dict[str, Any]], path: Path) -> None:
    """Rewrite the whole JSONL atomically. Crash-safe per decision."""
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    os.replace(tmp, path)


# --- view ---------------------------------------------------------------


def truncate(s: str, n: int) -> str:
    if len(s) <= n:
        return s
    return s[: n - 1].rstrip() + "…"


def render_row(row: dict[str, Any], oracle_full: bool = False) -> str:
    """Format a single row for the operator. Returns a multi-line string."""
    tags = row.get("tags") or {}
    shape = tags.get("shape", "?")
    use_case = row.get("use_case", "?")
    source_status = tags.get("source_status", "?")
    source = tags.get("source", "?")

    status_badge = (
        red("[SYNTHESIZED]") if source_status == "synthesized" else green("[ANCHORED]")
    )
    family = row.get("family", "?")
    qid = row.get("qid", "?")
    header = (
        bold(f"qid={qid}")
        + "  " + magenta(f"family={family}")
        + "  " + cyan(f"shape={shape}")
        + f"  use_case={use_case}"
        + "  " + status_badge
        + "  " + dim(f"src={source}")
    )

    parts: list[str] = [header, ""]

    # Question
    parts.append(bold("QUESTION:"))
    q = row.get("question", "")
    parts.append(textwrap.fill(q, width=100, replace_whitespace=False))
    parts.append("")

    # Options (D-mcq only)
    options = row.get("options") or []
    if options:
        parts.append(bold("OPTIONS:"))
        for letter, opt in zip("ABCD", options):
            parts.append(f"  {bold(letter + '.')} {opt}")
        parts.append("")

    # Oracle context
    oracle = row.get("oracle_context") or ""
    parts.append(bold("ORACLE CONTEXT:"))
    if oracle_full:
        parts.append(oracle)
    else:
        parts.append(truncate(oracle, 1500))
        if len(oracle) > 1500:
            parts.append(dim(f"  ...({len(oracle) - 1500} more chars; press 'o' to expand)"))
    parts.append("")

    # Gold label
    parts.append(bold("GOLD LABEL:"))
    gold = row.get("gold_label", "")
    parts.append(textwrap.fill(gold, width=100, replace_whitespace=False) or dim("<empty>"))
    parts.append("")

    # Rubric notes (Claude's hint to the reviewer)
    notes = tags.get("rubric_notes")
    if notes:
        parts.append(bold("RUBRIC NOTES (from seeder):"))
        parts.append(textwrap.fill(notes, width=100))
        parts.append("")

    # Reviewer's existing rubric (only on re-review)
    rubric = row.get("rubric")
    if rubric:
        parts.append(bold("REVIEWER RUBRIC:"))
        parts.append(textwrap.fill(rubric, width=100))
        parts.append("")

    return "\n".join(parts)


# --- review loop --------------------------------------------------------


@dataclass
class ReviewStats:
    accepted: int = 0
    edited: int = 0
    rejected: int = 0
    skipped: int = 0
    notes_added: int = 0


@dataclass
class FileSession:
    path: Path
    rows: list[dict[str, Any]] = field(default_factory=list)
    queue_indices: list[int] = field(default_factory=list)
    cursor: int = 0
    stats: ReviewStats = field(default_factory=ReviewStats)


def build_queue(
    rows: list[dict[str, Any]],
    include_reviewed: bool,
    source_status_filter: str | None,
    prioritize_synthesized: bool,
) -> list[int]:
    """Return the in-file indices the reviewer should walk, in order."""
    candidates: list[int] = []
    for i, row in enumerate(rows):
        if not include_reviewed and row.get("reviewed"):
            continue
        tags = row.get("tags") or {}
        status = tags.get("source_status")
        if source_status_filter and status != source_status_filter:
            continue
        candidates.append(i)

    if prioritize_synthesized and not source_status_filter:
        candidates.sort(key=lambda i: 0 if (rows[i].get("tags") or {}).get("source_status") == "synthesized" else 1)
    return candidates


def prompt_line(prompt: str) -> str:
    try:
        return input(prompt)
    except EOFError:
        print()
        return "q"


def edit_gold_label(row: dict[str, Any]) -> None:
    """Inline edit of gold_label. For MCQ, validate letter; otherwise free text."""
    shape = (row.get("tags") or {}).get("shape", "")
    current = row.get("gold_label", "")
    print(dim(f"  current gold_label: {current!r}"))
    if shape == "D-mcq":
        while True:
            new = prompt_line("  new letter (A/B/C/D, or blank to keep): ").strip().upper()
            if not new:
                return
            if new in {"A", "B", "C", "D"}:
                row["gold_label"] = new
                return
            print(red("  must be one of A/B/C/D"))
    else:
        print(dim("  multi-line input — end with a single '.' on its own line, or blank to keep:"))
        buf: list[str] = []
        while True:
            line = prompt_line("    > ")
            if line.strip() == "." and not buf:
                return  # zero lines + '.' → keep
            if line.strip() == ".":
                row["gold_label"] = "\n".join(buf).strip()
                return
            if not line and not buf:
                return  # blank first line → keep
            buf.append(line)


def edit_rubric_notes(row: dict[str, Any]) -> None:
    tags = row.setdefault("tags", {})
    current = tags.get("rubric_notes") or ""
    print(dim(f"  current rubric_notes: {current!r}"))
    print(dim("  enter replacement (blank line to keep, single '-' to clear):"))
    new = prompt_line("    > ").strip()
    if not new:
        return
    if new == "-":
        tags["rubric_notes"] = None
    else:
        tags["rubric_notes"] = new


def edit_reviewer_rubric(row: dict[str, Any]) -> None:
    current = row.get("rubric") or ""
    print(dim(f"  current rubric (reviewer-set): {current!r}"))
    print(dim("  multi-line input — end with '.' alone, blank to keep, '-' alone to clear:"))
    buf: list[str] = []
    while True:
        line = prompt_line("    > ")
        if not line and not buf:
            return
        if line.strip() == "-" and not buf:
            row["rubric"] = None
            return
        if line.strip() == ".":
            row["rubric"] = "\n".join(buf).strip()
            return
        buf.append(line)


def stamp_reviewed(row: dict[str, Any], reviewer: str | None) -> None:
    row["reviewed"] = True
    tags = row.setdefault("tags", {})
    tags["reviewed_at"] = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    if reviewer:
        tags["reviewed_by"] = reviewer


def review_file(
    session: FileSession,
    reviewer: str | None,
) -> str:
    """Walk one file's queue. Returns 'next' to advance, 'quit' to stop."""
    if not session.queue_indices:
        print(dim(f"  (no rows match the filter for {session.path.name})"))
        return "next"

    while session.cursor < len(session.queue_indices):
        q_idx = session.queue_indices[session.cursor]
        row = session.rows[q_idx]
        remaining = len(session.queue_indices) - session.cursor

        print()
        print(blue("─" * 100))
        print(
            blue(f"{session.path.name}")
            + dim(f"  cursor {session.cursor + 1}/{len(session.queue_indices)} ")
            + dim(f"(row {q_idx + 1}/{len(session.rows)}, {remaining} left in this file)")
        )
        print(blue("─" * 100))
        print(render_row(row))
        print(blue("─" * 100))

        action = prompt_line(
            bold("  [a]ccept  [e]dit  [r]eject  [s]kip  [p]rev  [o]racle  [n]ote  'rubric'  [q]uit ▶ ")
        ).strip().lower()

        if action in {"a", "accept", ""}:
            stamp_reviewed(row, reviewer)
            atomic_write_jsonl(session.rows, session.path)
            session.stats.accepted += 1
            print(green(f"  ✓ accepted {row.get('qid')}"))
            session.cursor += 1

        elif action in {"e", "edit"}:
            print(cyan("  → edit gold_label:"))
            edit_gold_label(row)
            print(cyan("  → edit rubric_notes:"))
            edit_rubric_notes(row)
            stamp_reviewed(row, reviewer)
            atomic_write_jsonl(session.rows, session.path)
            session.stats.edited += 1
            print(green(f"  ✎ edited + accepted {row.get('qid')}"))
            session.cursor += 1

        elif action in {"r", "reject"}:
            stamp_reviewed(row, reviewer)
            tags = row.setdefault("tags", {})
            tags["rejected"] = True
            reason = prompt_line("  rejection reason (one line, optional): ").strip()
            if reason:
                tags["rejection_reason"] = reason
            atomic_write_jsonl(session.rows, session.path)
            session.stats.rejected += 1
            print(red(f"  ✗ rejected {row.get('qid')}"))
            session.cursor += 1

        elif action in {"s", "skip"}:
            session.stats.skipped += 1
            session.cursor += 1
            print(yellow(f"  → skipped {row.get('qid')}"))

        elif action in {"p", "prev"}:
            if session.cursor > 0:
                session.cursor -= 1
            else:
                print(yellow("  already at start of this file"))

        elif action in {"o", "oracle"}:
            print()
            print(render_row(row, oracle_full=True))
            # don't advance — re-prompt on the same row

        elif action in {"n", "note"}:
            edit_rubric_notes(row)
            atomic_write_jsonl(session.rows, session.path)
            session.stats.notes_added += 1
            print(green("  + note saved (row not marked reviewed; choose a/e/r/s next)"))

        elif action == "rubric":
            edit_reviewer_rubric(row)
            atomic_write_jsonl(session.rows, session.path)
            print(green("  + reviewer rubric saved (row not marked reviewed)"))

        elif action in {"q", "quit"}:
            return "quit"

        else:
            print(red(f"  unknown action {action!r}; try a/e/r/s/p/o/n/q (or type 'rubric')"))

    return "next"


def print_session_summary(sessions: list[FileSession]) -> None:
    print()
    print(bold("=== review_patent_bench summary ==="))
    grand = ReviewStats()
    for s in sessions:
        st = s.stats
        if not (st.accepted or st.edited or st.rejected or st.skipped or st.notes_added):
            continue
        print(
            f"  {s.path.name:24} "
            f"accepted={st.accepted}  edited={st.edited}  "
            f"rejected={st.rejected}  skipped={st.skipped}  notes={st.notes_added}"
        )
        grand.accepted += st.accepted
        grand.edited += st.edited
        grand.rejected += st.rejected
        grand.skipped += st.skipped
        grand.notes_added += st.notes_added
    print(
        bold(
            f"  TOTAL                   accepted={grand.accepted}  edited={grand.edited}  "
            f"rejected={grand.rejected}  skipped={grand.skipped}  notes={grand.notes_added}"
        )
    )


# --- CLI ----------------------------------------------------------------


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--bench-dir", default=str(DEFAULT_BENCH_DIR), type=Path,
                    help="Directory holding seed-<shape>.jsonl files. Default %(default)s.")
    ap.add_argument("--shape", action="append", choices=SHAPE_FILES,
                    help="Review one or more shapes. Repeatable. Default: all.")
    ap.add_argument("--all", action="store_true",
                    help="Review every shape file in --bench-dir.")
    ap.add_argument("--reviewer", default=os.environ.get("USER"),
                    help="Stamp tags.reviewed_by with this name. Default $USER.")
    ap.add_argument("--include-reviewed", action="store_true",
                    help="Re-walk rows already marked reviewed=True (default: skip).")
    ap.add_argument("--source-status", choices=["anchored", "synthesized"],
                    help="Only review rows with this source_status tag.")
    ap.add_argument("--no-prioritize-synthesized", action="store_true",
                    help="Walk in file order; default puts synthesized rows first.")
    ap.add_argument("--start-index", type=int, default=0,
                    help="Skip the first N rows of the queue for the FIRST file. Useful for resuming a mid-shape walk.")
    ap.add_argument("--summary-only", action="store_true",
                    help="Print per-file review status without prompting (read-only).")
    args = ap.parse_args()

    shapes = SHAPE_FILES if args.all or not args.shape else args.shape

    sessions: list[FileSession] = []
    for shape in shapes:
        path = args.bench_dir / f"seed-{shape}.jsonl"
        if not path.exists():
            print(dim(f"  (no file at {path}; skipping {shape})"))
            continue
        rows = _iter_jsonl(path)
        queue = build_queue(
            rows,
            include_reviewed=args.include_reviewed,
            source_status_filter=args.source_status,
            prioritize_synthesized=not args.no_prioritize_synthesized,
        )
        sessions.append(FileSession(path=path, rows=rows, queue_indices=queue))

    if not sessions:
        print(red("no shape files found"))
        return 1

    # Read-only summary mode
    if args.summary_only:
        print(bold("=== bench review status ==="))
        for s in sessions:
            total = len(s.rows)
            reviewed = sum(1 for r in s.rows if r.get("reviewed"))
            rejected = sum(
                1 for r in s.rows
                if r.get("reviewed") and (r.get("tags") or {}).get("rejected")
            )
            synth = sum(
                1 for r in s.rows
                if (r.get("tags") or {}).get("source_status") == "synthesized"
            )
            synth_reviewed = sum(
                1 for r in s.rows
                if r.get("reviewed") and (r.get("tags") or {}).get("source_status") == "synthesized"
            )
            pct = (reviewed / total * 100) if total else 0.0
            print(
                f"  {s.path.name:24} "
                f"{reviewed}/{total} reviewed ({pct:5.1f}%)  "
                f"rejected={rejected}  "
                f"synthesized={synth_reviewed}/{synth}"
            )
        return 0

    # Apply --start-index to the first non-empty session
    for s in sessions:
        if s.queue_indices:
            s.cursor = min(args.start_index, len(s.queue_indices))
            break

    print(bold(f"  reviewer: {args.reviewer or '<unset>'}"))
    print(bold(f"  files queued: {len(sessions)}"))
    total_pending = sum(len(s.queue_indices) for s in sessions)
    print(bold(f"  rows to walk: {total_pending}"))
    if args.source_status:
        print(dim(f"  filter: source_status == {args.source_status}"))
    if args.include_reviewed:
        print(dim("  filter: including already-reviewed rows"))

    try:
        for s in sessions:
            result = review_file(s, args.reviewer)
            if result == "quit":
                break
    except KeyboardInterrupt:
        print()
        print(yellow("  ^C — saving progress and exiting"))

    print_session_summary(sessions)
    return 0


if __name__ == "__main__":
    sys.exit(main())
