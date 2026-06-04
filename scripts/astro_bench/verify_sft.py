#!/usr/bin/env python3
# Copyright 2026 Manav Sehgal
# SPDX-License-Identifier: Apache-2.0
"""verify_sft.py — the C1 corpus gate (deterministic; `feedback_llm_skill_pattern`).

Every row the session model writes into the SFT-init corpus must clear all gates:

  1. ``task_id`` resolves to a queue row, and the row's ``prompt`` matches the
     queue's prompt verbatim (no drift / no held-out prompt smuggled in).
  2. the completion carries a real ``<think>…</think>`` chain — non-empty, shows
     work, NOT a bare/placeholder think (`feedback_split_think_strip_check_trap`:
     a stripped-empty or answer-only chain is rejected).
  3. the completion ends in a ``\\boxed{value unit}`` sentinel.
  4. the boxed answer **self-verifies** through ``astro_numeric_match`` against the
     queue gold at ±2% (the reward the RLVR loop will use — RV-2/AV-2). A row whose
     own answer scores 0 is corpus poison: it would teach the model to box a wrong
     number, then RLVR would reward that wrong number.

Exit nonzero on ANY failure (CI-style; the live loop runs this each batch).

    python verify_sft.py                                  # default corpus + queue
    python verify_sft.py --corpus <jsonl> --queue <jsonl>
"""

from __future__ import annotations

import argparse
import json
import os

from verifier import astro_numeric_match, extract_boxed

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
_DIR = os.path.join(_REPO_ROOT, "evidence", "astrodynamics")
_REL_TOL = 0.02
_MIN_CHAIN_CHARS = 40   # a genuine worked chain is well above this

_OPEN, _CLOSE = "<think>", "</think>"


def _load(path: str) -> list[dict]:
    rows: list[dict] = []
    with open(path, encoding="utf-8") as fh:
        for ln, line in enumerate(fh, 1):
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as e:
                raise SystemExit(f"{path}:{ln}: bad JSON: {e}") from e
    return rows


def _chain_of(completion: str) -> str | None:
    """The text strictly between the first <think> and the next </think>, or None."""
    i = completion.find(_OPEN)
    if i == -1:
        return None
    j = completion.find(_CLOSE, i + len(_OPEN))
    if j == -1:
        return None
    return completion[i + len(_OPEN) : j]


def check_row(row: dict, queue: dict[str, dict]) -> list[str]:
    errs: list[str] = []
    tid = row.get("task_id", "<none>")
    q = queue.get(tid)
    if q is None:
        return [f"{tid}: task_id not in queue"]

    if row.get("prompt") != q["prompt"]:
        errs.append(f"{tid}: prompt drift from queue")

    completion = row.get("completion", "") or ""
    chain = _chain_of(completion)
    if chain is None:
        errs.append(f"{tid}: no <think>…</think> block")
    else:
        stripped = chain.strip()
        if not stripped:
            errs.append(f"{tid}: empty <think> chain")
        elif stripped.startswith(_OPEN):
            errs.append(f"{tid}: nested/placeholder <think>")
        elif len(stripped) < _MIN_CHAIN_CHARS:
            errs.append(f"{tid}: <think> chain too short ({len(stripped)} chars) — show the work")

    boxed = extract_boxed(completion)
    if boxed is None or not boxed.strip():
        errs.append(f"{tid}: no \\boxed{{}} sentinel")

    score = astro_numeric_match(completion, q["answer"], rel_tolerance=_REL_TOL)
    if score != 1.0:
        errs.append(
            f"{tid}: self-verify FAIL — boxed={boxed!r} vs gold={q['answer']!r} (score {score})"
        )
    return errs


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--corpus", default=os.path.join(_DIR, "astro-sft-corpus.jsonl"))
    ap.add_argument("--queue", default=os.path.join(_DIR, "astro-sft-queue.jsonl"))
    args = ap.parse_args()

    if not os.path.exists(args.corpus):
        raise SystemExit(f"corpus not found: {args.corpus}")
    queue_rows = _load(args.queue)
    queue = {r["task_id"]: r for r in queue_rows}
    corpus = _load(args.corpus)

    all_errs: list[str] = []
    seen: set[str] = set()
    for row in corpus:
        tid = row.get("task_id", "<none>")
        if tid in seen:
            all_errs.append(f"{tid}: duplicate task_id in corpus")
            continue
        seen.add(tid)
        all_errs.extend(check_row(row, queue))

    ok = len(corpus) - len({e.split(':')[0] for e in all_errs})
    print(f"[verify-sft] corpus={len(corpus)} rows  queue={len(queue)}  passing≈{ok}")
    if all_errs:
        print(f"[verify-sft] {len(all_errs)} FAILURES:")
        for e in all_errs[:50]:
            print("  ✗", e)
        if len(all_errs) > 50:
            print(f"  … and {len(all_errs) - 50} more")
        return 1
    print(f"[verify-sft] ALL {len(corpus)} rows clear: real <think> chain + \\boxed{{}} self-verifies ✓")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
