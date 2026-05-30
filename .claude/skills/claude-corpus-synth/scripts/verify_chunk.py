#!/usr/bin/env python3
"""Deterministic verifier for a producer subagent's chunk_<lo>_<hi>.jsonl output.

Used by the orchestrator (the CC session model) after each parallel-fan-out
subagent returns DONE. Runs zero-token gates: line count, row_idx order,
<think> presence, length bounds, MPEP-section sanity, case-citation regex.

Exits 0 on pass, 1 on fail. Prints a structured report either way.

Example:
    python3 verify_chunk.py /tmp/aifn-corpus-synth/chunk_100_149.jsonl 100 149

If LO/HI are omitted, the script infers them from the filename (chunk_<lo>_<hi>.jsonl).
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

# Real MPEP sections seen in patent practice. Adding to this list is fine;
# the verifier uses it only to AUDIT (warn), not to FAIL. Failing on
# whitelist-miss would be too strict (subagents legitimately extend coverage).
KNOWN_MPEP = {
    "201.08", "608.01(m)", "608.01(n)", "608.01(p)",
    "609", "706", "706.07(f)", "715", "715.07",
    "803", "1207", "1207.02", "1207.03", "1209",
    "2106", "2106.04(a)", "2112", "2131",
    "2141", "2141.01(a)", "2164",
    "2173.02", "2173.02(II)", "2173.02(III)",
    "2173.05", "2173.05(b)", "2173.05(c)", "2173.05(d)",
    "2173.05(g)", "2173.05(h)", "2173.05(o)",
    "2173.06", "2173.06(II)", "2181",
}

# Filenames hint LO/HI: chunk_<lo>_<hi>.jsonl
FILE_PATTERN = re.compile(r"chunk_(\d+)_(\d+)\.jsonl$")
THINK_RE = re.compile(r"<think>(.*?)</think>", re.DOTALL)
MPEP_RE = re.compile(r"MPEP\s+(\d{2,4}(?:\.\d{1,4})?(?:\([A-Za-z0-9]+\))?)")
CASE_RE = re.compile(r"\b[A-Z][\w'.-]+(?:\s+[A-Z][\w'.-]+){0,3}\s+v\.\s+[A-Z][\w'.-]+")
MIN_RESPONSE_CHARS = 400

# Producer-subagent meta-state leakage patterns. The producer's working notes
# (family designator, "duplicate of N", "diversify by …") must not leak into
# the <think> block — these were the 56% contamination axis from the s40
# patent-strategist v2 failure documented in
# articles/fine-tune-data-prep-decisions-on-spark/.
META_FAMILY_PREFIX_RE = re.compile(r"^\s*(A[124]|E[12])(\s|:|\.|duplicate|spice)", re.IGNORECASE)
META_DUPLICATE_OF_RE = re.compile(r"\bduplicate\s+of\s+\d+", re.IGNORECASE)
META_DIVERSIFY_RE = re.compile(r"\bdiversify\s+by\b", re.IGNORECASE)
# R<digits> row references — the surface form that surfaced in chunk_100_124
# (cursor=100, 2026-05-19). "For R120 the paralegal audience can handle …"
# or "R5, R29, R47 have hit MBA-audience framings" are clear producer-state
# leaks but were not caught by the original three regexes.
META_ROW_REF_RE = re.compile(r"\bR\d{2,4}\b")


def infer_range(path: Path) -> tuple[int, int] | None:
    m = FILE_PATTERN.search(path.name)
    if not m:
        return None
    return int(m.group(1)), int(m.group(2))


def verify(path: Path, lo: int | None = None, hi: int | None = None) -> int:
    fails: list[str] = []
    warns: list[str] = []

    if not path.exists():
        print(f"FAIL: file does not exist: {path}")
        return 1

    if lo is None or hi is None:
        inferred = infer_range(path)
        if inferred is None:
            print(f"FAIL: cannot infer LO/HI from filename {path.name}; pass --lo and --hi explicitly")
            return 1
        lo, hi = inferred

    expected_count = hi - lo + 1
    expected_idxs = list(range(lo, hi + 1))

    try:
        with path.open() as f:
            rows = [json.loads(line) for line in f if line.strip()]
    except json.JSONDecodeError as e:
        print(f"FAIL: invalid JSON in {path}: {e}")
        return 1

    # Line count
    if len(rows) != expected_count:
        fails.append(f"row count {len(rows)}, expected {expected_count}")

    # row_idx order
    got_idxs = [r.get("row_idx") for r in rows]
    if got_idxs != expected_idxs:
        # Show the first divergence
        mismatch = next(
            ((i, g, e) for i, (g, e) in enumerate(zip(got_idxs, expected_idxs)) if g != e),
            None,
        )
        fails.append(
            f"row_idx order mismatch (first divergence at position {mismatch})"
            if mismatch
            else "row_idx order mismatch"
        )

    # Per-row checks
    missing_think: list[int] = []
    short_rows: list[tuple[int, int]] = []  # (row_idx, chars)
    mpep_sections_seen: set[str] = set()
    case_cites_total = 0
    chars_dist: list[int] = []
    meta_family_prefix: list[int] = []
    meta_duplicate_of: list[int] = []
    meta_diversify_by: list[int] = []
    meta_row_ref: list[int] = []

    for r in rows:
        idx = r.get("row_idx", "?")
        resp = r.get("response", "")
        think_match = THINK_RE.search(resp)
        if not think_match:
            missing_think.append(idx)
            think_content = ""
        else:
            think_content = think_match.group(1)
        chars = len(resp)
        chars_dist.append(chars)
        if chars < MIN_RESPONSE_CHARS:
            short_rows.append((idx, chars))
        for m in MPEP_RE.finditer(resp):
            mpep_sections_seen.add(m.group(1))
        case_cites_total += len(CASE_RE.findall(resp))

        # Producer-meta-state leakage gates (applied to <think> body only)
        if think_content:
            if META_FAMILY_PREFIX_RE.match(think_content):
                meta_family_prefix.append(idx)
            if META_DUPLICATE_OF_RE.search(think_content):
                meta_duplicate_of.append(idx)
            if META_DIVERSIFY_RE.search(think_content):
                meta_diversify_by.append(idx)
            if META_ROW_REF_RE.search(think_content):
                meta_row_ref.append(idx)

    if missing_think:
        fails.append(f"missing <think>...</think> on rows {missing_think}")
    if short_rows:
        fails.append(f"rows under {MIN_RESPONSE_CHARS} chars: {short_rows}")
    if meta_family_prefix:
        fails.append(
            f"producer meta-state leak — <think> begins with family designator "
            f"(A1/A2/A4/E1/E2 prefix): rows {meta_family_prefix}"
        )
    if meta_duplicate_of:
        fails.append(
            f"producer meta-state leak — 'duplicate of N' annotation in <think>: rows {meta_duplicate_of}"
        )
    if meta_diversify_by:
        fails.append(
            f"producer meta-state leak — 'diversify by …' instruction in <think>: rows {meta_diversify_by}"
        )
    if meta_row_ref:
        fails.append(
            f"producer meta-state leak — 'R<digits>' sibling-row callout in <think>: rows {meta_row_ref}"
        )

    # MPEP audit: sections outside the known list → warn (not fail)
    suspicious_mpep = sorted(m for m in mpep_sections_seen if m not in KNOWN_MPEP)
    if suspicious_mpep:
        warns.append(
            f"MPEP sections outside known whitelist (manual semantic check recommended): {suspicious_mpep}"
        )

    # Report
    mean_chars = sum(chars_dist) // len(chars_dist) if chars_dist else 0
    print(f"== verify_chunk: {path.name} (LO={lo} HI={hi}) ==")
    print(f"  line count:    {len(rows)} (expected {expected_count})")
    print(f"  <think> rate:  {(expected_count - len(missing_think)) / expected_count * 100:.0f}%")
    print(f"  chars: min={min(chars_dist) if chars_dist else 0} max={max(chars_dist) if chars_dist else 0} mean={mean_chars}")
    print(f"  MPEP sections: {len(mpep_sections_seen)} unique")
    print(f"  Case cites:    {case_cites_total} total ({case_cites_total / max(len(rows), 1):.1f}/row)")
    n = max(len(rows), 1)
    print(
        f"  Meta-state:    family-prefix={len(meta_family_prefix)} ({len(meta_family_prefix)/n*100:.0f}%) "
        f"duplicate-of={len(meta_duplicate_of)} ({len(meta_duplicate_of)/n*100:.0f}%) "
        f"diversify-by={len(meta_diversify_by)} ({len(meta_diversify_by)/n*100:.0f}%) "
        f"row-ref={len(meta_row_ref)} ({len(meta_row_ref)/n*100:.0f}%)"
    )

    for w in warns:
        print(f"  WARN: {w}")

    if fails:
        print()
        for f in fails:
            print(f"  FAIL: {f}")
        print("\nverdict: FAIL")
        return 1

    print("\nverdict: PASS")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify a producer chunk file.")
    parser.add_argument("path", type=Path, help="Path to chunk_<lo>_<hi>.jsonl")
    parser.add_argument("--lo", type=int, default=None, help="First row_idx (inclusive); inferred from filename if omitted")
    parser.add_argument("--hi", type=int, default=None, help="Last row_idx (inclusive); inferred from filename if omitted")
    args = parser.parse_args()
    return verify(args.path, args.lo, args.hi)


if __name__ == "__main__":
    sys.exit(main())
