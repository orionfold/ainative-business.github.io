# Copyright 2026 Manav Sehgal
# SPDX-License-Identifier: Apache-2.0
"""verifier.py — the numeric reward for the astrodynamics RLVR vertical.

This IS the reward (RV-2: the eval harness *is* the reward model, no learned RM).
It conforms to the `fieldkit.eval` verifier signature
``(predicted, expected, *, rel_tolerance) -> float`` so it drops straight into
``fieldkit.reward.RewardAdapter`` — the adapter's kwarg introspection forwards
``rel_tolerance`` and nothing else::

    from fieldkit.reward import RewardAdapter
    adapter = RewardAdapter(astro_numeric_match, scorer_kwargs={"rel_tolerance": 0.02})
    reward  = adapter.score(Rollout(prediction=rollout_text, expected=row["answer"]))

Kept LOCAL (not promoted to ``fieldkit.eval``) until a second vertical reuses a
unit-aware numeric scorer — per `feedback_keep_scorer_local_until_reuse`.

Grading policy (decided 2026-06-04, see `_IDEAS/astrodynamics-rlvr-vertical.md`):
  * **binary** — 1.0 / 0.0, no partial credit (partial credit invites Goodhart).
  * **relative tolerance** default ±2% (answers span orders of magnitude;
    absolute tolerance breaks across scales).
  * **unit-normalized** — convert both sides to SI; a dimension mismatch fails.
  * a **bare number** (no unit) is graded against gold *in gold's unit* (the
    common convention — the model answered in the expected unit).
  * answer is read from a ``\\boxed{...}`` sentinel, then a "final answer:" line,
    then the last quantity in the text (most lenient fallback).
"""

from __future__ import annotations

import re

from units import parse_last_quantity, parse_quantity, same_dimension, to_si

_BOXED_OPEN = "\\boxed{"


def extract_boxed(text: str) -> str | None:
    """Return the inner text of the LAST ``\\boxed{...}`` (brace-matched), or None."""
    idx = text.rfind(_BOXED_OPEN)
    if idx == -1:
        return None
    start = idx + len(_BOXED_OPEN)
    depth = 1
    i = start
    while i < len(text) and depth > 0:
        ch = text[i]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
        i += 1
    if depth != 0:
        return text[start:]  # unterminated — take the tail
    return text[start : i - 1]


_FINAL_RE = re.compile(r"final\s+answer\s*[:=]?\s*(.+)", re.IGNORECASE)


def extract_answer(predicted: str) -> str | None:
    """Pull the answer substring from a model generation.

    Priority: ``\\boxed{}`` → a "final answer:" line → the whole text (the caller
    then parses the *last* quantity from it).
    """
    boxed = extract_boxed(predicted)
    if boxed is not None and boxed.strip():
        return boxed
    m = None
    for m in _FINAL_RE.finditer(predicted):  # take the last "final answer" hit
        pass
    if m is not None:
        return m.group(1)
    return None  # signal: fall back to last-quantity scan over the whole text


def astro_numeric_match(
    predicted: str,
    expected: str,
    *,
    rel_tolerance: float = 0.02,
) -> float:
    """1.0 if `predicted`'s answer matches `expected` within `rel_tolerance`, else 0.0.

    `expected` is the bench row's canonical ``"<value> <unit>"`` gold string.
    """
    gold = parse_quantity(expected)
    if gold is None:
        return 0.0
    gold_val, gold_unit = gold
    try:
        gold_si, gold_dim = to_si(gold_val, gold_unit)
    except KeyError:
        return 0.0

    answer_text = extract_answer(predicted)
    if answer_text is not None:
        pred = parse_quantity(answer_text)
    else:
        pred = parse_last_quantity(predicted)
    if pred is None:
        return 0.0
    pred_val, pred_unit = pred

    if pred_unit == "":
        # bare number — assume the model answered in gold's unit.
        pred_si = pred_val * (gold_si / gold_val if gold_val != 0 else 1.0)
    else:
        if not same_dimension(pred_unit, gold_unit):
            return 0.0
        pred_si, _ = to_si(pred_val, pred_unit)

    if gold_si == 0.0:
        return 1.0 if abs(pred_si) <= rel_tolerance else 0.0
    return 1.0 if abs(pred_si - gold_si) <= rel_tolerance * abs(gold_si) else 0.0


# Convenience for non-reward callers (debugging / dataset self-check).
def explain(predicted: str, expected: str, *, rel_tolerance: float = 0.02) -> dict:
    gold = parse_quantity(expected)
    ans = extract_answer(predicted)
    pred = parse_quantity(ans) if ans is not None else parse_last_quantity(predicted)
    return {
        "gold": gold,
        "extracted": ans,
        "pred": pred,
        "score": astro_numeric_match(predicted, expected, rel_tolerance=rel_tolerance),
    }
