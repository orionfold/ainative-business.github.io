#!/usr/bin/env python3
"""Mine real build metrics for a product-launch article.

A "built it in a day" claim is only as good as the numbers behind it. This
script reconstructs those numbers from primary sources rather than estimates:

  * Token spend — summed from the Claude Code session transcripts (JSONL) that
    fall inside the build window, deduplicated by assistant-message id and
    split by model (so an "Opus 4.7 + 4.8" story can show the real mix).
  * Lines of code — counted directly off the shipped source paths, by
    extension, non-blank lines only.
  * Tests — counted as `def test_` / `it(` / `test(` occurrences under the
    test globs.
  * Wall-clock — the span between the first and last git commit matching a
    subject pattern (e.g. "arena:").

Everything is parameterised so the next product launch reuses the same script.
Nothing here calls an LLM or an external service — it is pure local accounting.

Usage (Orionfold Arena example):

  python3 mine_build_metrics.py \
    --since 2026-05-28T09:00:00 --until 2026-05-29T01:00:00 \
    --log-dir /home/nvidia/.claude/projects/-home-nvidia-ainative-business-github-io \
    --repo /home/nvidia/ainative-business.github.io \
    --commit-grep '^arena:' \
    --loc fieldkit/src/fieldkit/arena \
    --loc src/components/arena --loc src/lib/arena --loc src/pages/arena \
    --tests 'fieldkit/src/fieldkit/arena/tests/test_*.py' \
    --out /tmp/arena-build-metrics.json

The session transcripts are operator-private. This script only reads token
counts and timestamps out of them — never message content — and writes only
aggregates. Sanity-check the JSON before quoting any figure publicly.
"""
import argparse
import glob
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone


def parse_iso(s: str) -> datetime:
    """Accept '2026-05-28T09:00:00', with or without trailing Z / offset."""
    s = s.strip()
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def mine_tokens(log_dir: str, since: datetime, until: datetime) -> dict:
    """Walk every *.jsonl transcript, sum usage for assistant messages whose
    timestamp lands in [since, until]. Dedup by the API message id so resumed
    or recompacted sessions (which re-log the same response) count once."""
    seen_ids: set[str] = set()
    by_model: dict[str, dict] = {}
    sessions: set[str] = set()
    turns = 0

    fields = (
        "input_tokens",
        "output_tokens",
        "cache_creation_input_tokens",
        "cache_read_input_tokens",
    )

    for path in sorted(glob.glob(os.path.join(log_dir, "*.jsonl"))):
        with open(path, encoding="utf-8", errors="replace") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    o = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if o.get("type") != "assistant":
                    continue
                msg = o.get("message")
                if not isinstance(msg, dict):
                    continue
                usage = msg.get("usage")
                if not isinstance(usage, dict):
                    continue
                ts_raw = o.get("timestamp")
                if not ts_raw:
                    continue
                try:
                    ts = parse_iso(ts_raw)
                except ValueError:
                    continue
                if not (since <= ts <= until):
                    continue
                mid = msg.get("id") or o.get("uuid")
                if mid in seen_ids:
                    continue
                seen_ids.add(mid)

                model = msg.get("model", "unknown")
                bucket = by_model.setdefault(
                    model, {f: 0 for f in fields} | {"turns": 0}
                )
                for f in fields:
                    bucket[f] += int(usage.get(f, 0) or 0)
                bucket["turns"] += 1
                turns += 1
                sessions.add(os.path.basename(path))

    totals = {f: 0 for f in fields}
    for bucket in by_model.values():
        for f in fields:
            totals[f] += bucket[f]

    # Two useful headline numbers:
    #   total      — every token the API processed (input incl. cache reads + output)
    #   throughput — input + output excluding cache reads (the "fresh" work)
    totals["total_all"] = sum(totals[f] for f in fields)
    totals["fresh_in_out"] = totals["input_tokens"] + totals["output_tokens"]

    return {
        "by_model": by_model,
        "totals": totals,
        "assistant_turns": turns,
        "sessions_touched": len(sessions),
    }


def count_loc(paths: list[str], excludes: list[str]) -> dict:
    """Non-blank line counts per extension across the given source roots.

    Counts *authored* source only: built bundles, vendored deps, and macOS
    AppleDouble `._*` turds (which appear on SMB/NFS mounts and would both
    crash the decoder and inflate the file count) are skipped. Pass
    `--loc-exclude <substring>` to drop generated output dirs such as
    `_webui/` — quoting a compiled bundle as "lines of code we wrote" is the
    fastest way to lose a reader's trust."""
    by_ext: dict[str, dict] = {}
    code_exts = {
        ".py", ".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs",
        ".astro", ".css", ".html", ".sh", ".sql", ".vue", ".svelte",
    }
    for root in paths:
        if os.path.isfile(root):
            files = [root]
        else:
            files = []
            for dirpath, _dirs, names in os.walk(root):
                if "node_modules" in dirpath or "/." in dirpath:
                    continue
                for n in names:
                    files.append(os.path.join(dirpath, n))
        for fp in files:
            base = os.path.basename(fp)
            if base.startswith("._"):  # AppleDouble turd, not source
                continue
            if any(ex in fp for ex in excludes):
                continue
            ext = os.path.splitext(fp)[1].lower()
            if ext not in code_exts:
                continue
            try:
                with open(fp, encoding="utf-8", errors="replace") as fh:
                    nonblank = sum(1 for ln in fh if ln.strip())
            except OSError:
                continue
            b = by_ext.setdefault(ext, {"files": 0, "lines": 0})
            b["files"] += 1
            b["lines"] += nonblank
    total = sum(b["lines"] for b in by_ext.values())
    total_files = sum(b["files"] for b in by_ext.values())
    return {"by_ext": by_ext, "total_lines": total, "total_files": total_files}


TEST_PATTERNS = [
    re.compile(r"^\s*def\s+test_\w+"),      # pytest / unittest
    re.compile(r"\bit\s*\(\s*['\"]"),         # jest / vitest / mocha
    re.compile(r"\btest\s*\(\s*['\"]"),       # jest / node:test
]


def count_tests(globs: list[str]) -> dict:
    files = 0
    cases = 0
    for g in globs:
        for fp in glob.glob(g, recursive=True):
            if not os.path.isfile(fp):
                continue
            files += 1
            try:
                with open(fp, encoding="utf-8", errors="replace") as fh:
                    for ln in fh:
                        if any(p.search(ln) for p in TEST_PATTERNS):
                            cases += 1
            except OSError:
                continue
    return {"test_files": files, "test_cases": cases}


def git_wall_clock(repo: str, grep: str) -> dict:
    """First → last commit whose subject matches `grep`, with elapsed hours."""
    try:
        out = subprocess.check_output(
            ["git", "-C", repo, "log", "--reverse",
             "--grep", grep, "--extended-regexp",
             "--format=%H\t%cI\t%s"],
            text=True,
        ).strip()
    except subprocess.CalledProcessError:
        return {}
    rows = [r.split("\t", 2) for r in out.splitlines() if r]
    if not rows:
        return {}
    first, last = rows[0], rows[-1]
    t0, t1 = parse_iso(first[1]), parse_iso(last[1])
    hours = round((t1 - t0).total_seconds() / 3600, 2)
    return {
        "first_commit": {"hash": first[0][:9], "time": first[1], "subject": first[2]},
        "last_commit": {"hash": last[0][:9], "time": last[1], "subject": last[2]},
        "commit_count": len(rows),
        "elapsed_hours": hours,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--since", required=True, help="build window start (ISO)")
    ap.add_argument("--until", required=True, help="build window end (ISO)")
    ap.add_argument("--log-dir", required=True,
                    help="Claude Code project transcript dir (holds *.jsonl)")
    ap.add_argument("--repo", help="git repo root (for wall-clock)")
    ap.add_argument("--commit-grep", help="regex matched against commit subjects")
    ap.add_argument("--loc", action="append", default=[],
                    help="source path to LOC-count (repeatable)")
    ap.add_argument("--loc-exclude", action="append", default=[],
                    help="skip files whose path contains this substring, e.g. "
                         "_webui (built bundle). Repeatable.")
    ap.add_argument("--tests", action="append", default=[],
                    help="glob of test files (repeatable)")
    ap.add_argument("--out", required=True, help="output JSON path")
    args = ap.parse_args()

    since, until = parse_iso(args.since), parse_iso(args.until)

    metrics = {
        "build_window": {"since": since.isoformat(), "until": until.isoformat()},
        "tokens": mine_tokens(args.log_dir, since, until),
    }
    if args.loc:
        metrics["loc"] = count_loc(args.loc, args.loc_exclude)
    if args.tests:
        metrics["tests"] = count_tests(args.tests)
    if args.repo and args.commit_grep:
        metrics["wall_clock"] = git_wall_clock(args.repo, args.commit_grep)

    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(metrics, fh, indent=2)

    # Human-readable summary to stderr so a pipe to the JSON file stays clean.
    t = metrics["tokens"]["totals"]
    print(f"\nWrote {args.out}", file=sys.stderr)
    print(f"  build window : {args.since} -> {args.until}", file=sys.stderr)
    print(f"  sessions     : {metrics['tokens']['sessions_touched']}", file=sys.stderr)
    print(f"  asst turns   : {metrics['tokens']['assistant_turns']}", file=sys.stderr)
    print(f"  tokens total : {t['total_all']:,} (incl. cache reads)", file=sys.stderr)
    print(f"    output     : {t['output_tokens']:,}", file=sys.stderr)
    print(f"    input      : {t['input_tokens']:,}", file=sys.stderr)
    print(f"    cache write: {t['cache_creation_input_tokens']:,}", file=sys.stderr)
    print(f"    cache read : {t['cache_read_input_tokens']:,}", file=sys.stderr)
    print("  by model:", file=sys.stderr)
    for model, b in sorted(metrics["tokens"]["by_model"].items()):
        tot = sum(b[k] for k in
                  ("input_tokens", "output_tokens",
                   "cache_creation_input_tokens", "cache_read_input_tokens"))
        print(f"    {model:24s} {b['turns']:5d} turns  {tot:>14,} tok", file=sys.stderr)
    if "loc" in metrics:
        print(f"  LOC          : {metrics['loc']['total_lines']:,} "
              f"across {metrics['loc']['total_files']} files", file=sys.stderr)
        for ext, b in sorted(metrics["loc"]["by_ext"].items(),
                             key=lambda kv: -kv[1]["lines"]):
            print(f"    {ext:8s} {b['lines']:>8,} lines  ({b['files']} files)",
                  file=sys.stderr)
    if "tests" in metrics:
        print(f"  tests        : {metrics['tests']['test_cases']} cases "
              f"in {metrics['tests']['test_files']} files", file=sys.stderr)
    if metrics.get("wall_clock"):
        w = metrics["wall_clock"]
        print(f"  wall clock   : {w['elapsed_hours']} h across "
              f"{w['commit_count']} commits", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
