#!/usr/bin/env python3
# Copyright 2026 Manav Sehgal
# SPDX-License-Identifier: Apache-2.0
"""Seed the patent-strategist-v0.1 eval bench by prompting Claude Sonnet 4.6.

Per `_SPECS/patent-strategist-v1.md` §3.2 / §5.1 / §5.3, this script writes
JSONL rows that conform to the `format='patent-strategist'` branch of
`fieldkit.eval.vertical` — qid / question / family / use_case / scoring_mode /
gold_label / options / context / oracle_context / rubric / reviewed=False /
tags. Output lands one file per shape under the bench dir:

    /home/nvidia/data/eval-benches/patent-strategist/
        seed-A.jsonl        Family A — generative/inventive (50 target)
        seed-B.jsonl        Family B — prior-art ranking (40 target)
        seed-C.jsonl        Family C — strategic/portfolio (20 target)
        seed-D-mcq.jsonl    Family D — procedural MCQ on MPEP (40 target)
        seed-D-oa.jsonl     Family D — office-action response (10 target)
        seed-D-irac.jsonl   Family D — IRAC scenarios (10 target)
        seed-E.jsonl        Family E — communication/education (30 target)

Total: 200 questions matching spec §5.1.

Auth path: subprocess to the local `claude` CLI in `-p` mode with
`--model claude-sonnet-4-6`. This uses the OAuth credential at
`~/.claude/.credentials.json` (per `[[reference_claude_agent_sdk_oauth]]`) —
no `ANTHROPIC_API_KEY` needed. The CLI is bundled with Claude Code so
nothing extra to install.

Anchors:
- D-mcq / D-oa / D-irac     → MPEP sections (~2k sections on disk)
- B                          → PatentMatch claim ↔ prior-art pairs (25k rows)
- A / C / E                  → BIGPATENT abstracts (10k rows)

Anchors that the spec calls for but that aren't yet pulled on this Spark
(USPTO OARD for D-oa, Google Patents BigQuery for C) get a Claude-synthesis
fallback anchored on the closest available source — flagged in
`tags.source_status = "synthesized"` so the T9 review CLI can prioritize
human eyeballs on those rows.

Idempotent + resumable: per-shape JSONL is opened in append mode, the qid is
the SHA8 of the canonical question text, and existing qids in the file are
loaded into a dedupe set before each batch round. Rerun the script to top up
a shape that's short of target; nothing regenerates from scratch unless you
delete the file.

Examples
--------

    # Smoke (1 row per shape, no Claude call — emits stub rows for plumbing checks):
    python scripts/seed_patent_bench.py --dry-run --per-shape 1

    # Real seeding, capped at 5 rows per shape (~35 Claude calls, ~$2-3):
    python scripts/seed_patent_bench.py --per-shape 5

    # Full bench (200 rows, ~$10-20 across all shapes):
    python scripts/seed_patent_bench.py --all

    # Resume a single shape (top up to 40):
    python scripts/seed_patent_bench.py --shape D-mcq --target 40
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import re
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

CORPUS_DIR = Path("/home/nvidia/data/corpus/patent")
DEFAULT_OUTPUT_DIR = Path("/home/nvidia/data/eval-benches/patent-strategist")
CLAUDE_BIN = os.environ.get("CLAUDE_BIN", "claude")
CLAUDE_MODEL = os.environ.get("CLAUDE_MODEL", "claude-sonnet-4-6")
CLAUDE_TIMEOUT_S = int(os.environ.get("CLAUDE_TIMEOUT_S", "180"))
ANCHOR_CHAR_CAP = 1800  # MPEP sections run 20k+ chars; cap to keep prompts tight


# --- shape registry ------------------------------------------------------


@dataclass(frozen=True)
class ShapeSpec:
    """One bench shape (A / B / C / D-mcq / D-oa / D-irac / E)."""

    shape: str           # filename token + family-disambiguator
    family: str          # "A" / "B" / "C" / "D" / "E"
    use_cases: list[str]  # rotate across these per-row
    target: int          # spec §5.1 row count
    source: str          # "mpep" | "patentmatch" | "bigpatent"
    scorer_key: str      # matches PATENT_STRATEGIST_SCORERS in vertical.py
    instructions: str    # shape-specific prompt body (Claude side)


SHAPES: dict[str, ShapeSpec] = {
    "A": ShapeSpec(
        shape="A",
        family="A",
        use_cases=["A1", "A2", "A3", "A4"],
        target=50,
        source="bigpatent",
        scorer_key="A",
        instructions=(
            "Generate Family A questions on PATENT CLAIM DRAFTING & STRATEGY. Each "
            "question gives the model a real patent abstract (provided in `oracle_context`) "
            "and asks for ONE of: (A1) a novel patent-angle/white-space proposal, "
            "(A2) Socratic invention-disclosure Q&A, (A3) a broadened OR narrowed claim "
            "rewrite, or (A4) a continuation/divisional strategy. `gold_label` is a "
            "structured rubric-grader REFERENCE answer (1-3 sentences for A1/A4, a draft "
            "claim for A2/A3) the LLM-judge `patent_claim_validity` will score against. "
            "Set `scoring_mode` to 'oracle' (the abstract is the oracle context)."
        ),
    ),
    "B": ShapeSpec(
        shape="B",
        family="B",
        use_cases=["B1", "B3"],
        target=40,
        source="patentmatch",
        scorer_key="B",
        instructions=(
            "Generate Family B questions on PRIOR-ART RELEVANCE & RANKING. Each anchor "
            "is a PatentMatch claim/cited-prior-art pair labeled X (novelty-destroying) "
            "or A (background). For (B1) prior-art search prompts: ask the model to "
            "produce 5 retrieval queries for the claim. For (B3) invalidity ranking: "
            "give the model the claim plus 4-5 candidate prior-art snippets (mix the "
            "labeled X with 3-4 plausible distractors you invent from the same tech area) "
            "and ask for a relevance-ranked list. `gold_label` for B3 is a JSON-array "
            "ranking string like '[\"P3\",\"P1\",\"P2\",\"P4\"]'; for B1 it is a JSON "
            "list of the 5 ideal queries. Set `scoring_mode` to 'oracle' (the cited_text "
            "is the oracle context)."
        ),
    ),
    "C": ShapeSpec(
        shape="C",
        family="C",
        use_cases=["C1", "C2", "C3"],
        target=20,
        source="bigpatent",
        scorer_key="C",
        instructions=(
            "Generate Family C questions on PORTFOLIO / LANDSCAPE STRATEGY. Anchored "
            "on a real patent abstract (provided in `oracle_context`) plus its IPC class. "
            "Question shapes: (C1) landscape clusters/leaders/gaps in the abstract's "
            "tech area, (C2) cross-license overlap identification, (C3) EPO/JPO/CNIPA "
            "filing-strategy particularities for the disclosed invention. Open-ended; "
            "`gold_label` is a 3-5 sentence reference answer for an LLM judge to score "
            "on correctness + faithfulness. Set `scoring_mode` to 'oracle'. "
            "Note: GPat BigQuery is not yet pulled on this Spark — flag "
            "tags.source_status='synthesized' so T9 review can prioritize these."
        ),
    ),
    "D-mcq": ShapeSpec(
        shape="D-mcq",
        family="D",
        use_cases=["D1", "D3"],
        target=40,
        source="mpep",
        scorer_key="D-mcq",
        instructions=(
            "Generate Family D-mcq questions: 4-option MCQs on USPTO patent prosecution. "
            "Anchor: one MPEP section provided in `oracle_context` (title + first ~1500 "
            "chars). Cover 35 USC 101 / 102 / 103 / 112 rejections, MPEP procedural rules, "
            "and prior-art classification. Required output per row: `question` is the "
            "stem (no options inline — they go in `options`); `options` is a list of 4 "
            "strings; `gold_label` is the single correct letter 'A', 'B', 'C', or 'D'. "
            "Distractors must be plausible (cite related-but-incorrect MPEP rules, "
            "swap statute numbers, invert the holding). Set `scoring_mode` to 'oracle' "
            "(the MPEP section is the oracle context)."
        ),
    ),
    "D-oa": ShapeSpec(
        shape="D-oa",
        family="D",
        use_cases=["D1"],
        target=10,
        source="mpep",
        scorer_key="D-oa",
        instructions=(
            "Generate Family D-oa questions: OFFICE-ACTION RESPONSE drafting. Anchor: an "
            "MPEP section covering a rejection type (101, 102, 103, 112). Synthesize a "
            "realistic Non-Final Rejection scenario (claim text + examiner's argument + "
            "cited prior art) IN the `question` field and ask the model for a response "
            "argument. `gold_label` is a reference 3-5 sentence attorney response that the "
            "`office_action_argument` 4-dim scorer will grade against (rejection-type ID, "
            "statutory-citation accuracy, CFR/MPEP citation correctness, persuasiveness). "
            "Set `scoring_mode` to 'oracle'. Flag tags.source_status='synthesized' since "
            "USPTO OARD is not yet pulled."
        ),
    ),
    "D-irac": ShapeSpec(
        shape="D-irac",
        family="D",
        use_cases=["D2"],
        target=10,
        source="mpep",
        scorer_key="D-irac",
        instructions=(
            "Generate Family D-irac questions: PATENT-BAR-STYLE IRAC scenarios. Anchor: "
            "an MPEP section. Synthesize a fact pattern (a practice scenario — claim + "
            "facts + procedural posture) IN the `question` field and ask the model to "
            "respond in IRAC structure (explicit Issue / Rule / Application / Conclusion "
            "headers or labels). `gold_label` is a reference IRAC response with all 4 "
            "components present — the deterministic `irac_structure` scorer checks "
            "keyword presence in the model output. Set `scoring_mode` to 'oracle'."
        ),
    ),
    "E": ShapeSpec(
        shape="E",
        family="E",
        use_cases=["E1", "E2"],
        target=30,
        source="bigpatent",
        scorer_key="E",
        instructions=(
            "Generate Family E questions on COMMUNICATION / EDUCATION. Anchor: a real "
            "patent abstract (provided in `oracle_context`). (E1) patent-to-engineer "
            "explainer — translate a claim or abstract into engineer-readable language. "
            "(E2) inventor-interview — open with the first probing question of a "
            "multi-turn extraction dialogue (model is the IP attorney, hypothetical "
            "inventor is the user). `gold_label` is a 2-4 sentence reference answer the "
            "Judge will score on correctness + faithfulness. Set `scoring_mode` to "
            "'oracle'. Flag tags.source_status='synthesized' for E2 (no real interview "
            "corpus pulled)."
        ),
    ),
}


# --- corpus loaders ------------------------------------------------------


def _iter_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open() as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return rows


def load_anchors(source: str, seed: int) -> list[dict[str, Any]]:
    """Return a shuffled pool of anchor rows for one corpus source."""
    rng = random.Random(seed)
    if source == "mpep":
        # Pull a handful per chapter for coverage rather than dumping all 2,047
        # — the seeder only needs ~70 (40 + 10 + 10 with headroom).
        pool: list[dict[str, Any]] = []
        for chap_file in sorted((CORPUS_DIR / "mpep").glob("mpep-*.jsonl")):
            chap_rows = _iter_jsonl(chap_file)
            # Drop subsection-less chapter headers + ultra-short stubs.
            chap_rows = [r for r in chap_rows if len(r.get("text", "")) > 800]
            rng.shuffle(chap_rows)
            pool.extend(chap_rows[:5])  # ~5 per chapter × 29 chapters ≈ 145
        rng.shuffle(pool)
        return pool
    if source == "patentmatch":
        path = CORPUS_DIR / "patentmatch" / "patentmatch-ultrabalanced.jsonl"
        rows = _iter_jsonl(path)
        # Strong preference for X-labeled (novelty-destroying) pairs — they're
        # the load-bearing ones for B3 ranking. ~50/50 in source corpus.
        x_rows = [r for r in rows if r.get("label_letter") == "X"]
        rng.shuffle(x_rows)
        return x_rows[:200]  # plenty of headroom for B target=40
    if source == "bigpatent":
        rows: list[dict[str, Any]] = []
        for shard in sorted((CORPUS_DIR / "bigpatent").glob("bigpatent-*-train.jsonl")):
            shard_rows = _iter_jsonl(shard)
            # Drop tiny abstracts (< 400 chars) — too thin to anchor a strategic Q.
            shard_rows = [r for r in shard_rows if len(r.get("abstract", "")) > 400]
            rows.extend(shard_rows)
        rng.shuffle(rows)
        return rows[:300]  # ample headroom for A (50) + C (20) + E (30)
    raise ValueError(f"unknown source: {source}")


def render_anchor(source: str, row: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    """Return (context_text, source_meta) for one anchor row.

    `source_meta` lands in the row's `tags` so the bench is provenance-tracked.
    """
    if source == "mpep":
        title = row.get("title") or "MPEP section"
        text = (row.get("text") or "")[:ANCHOR_CHAR_CAP]
        ctx = f"MPEP {title}\nSource: {row.get('url', 'uspto.gov')}\n\n{text}"
        meta = {
            "source": "mpep",
            "section_id": row.get("section_id"),
            "chapter": row.get("chapter"),
            "url": row.get("url"),
        }
        return ctx, meta
    if source == "patentmatch":
        claim = row.get("claim_text", "")
        cited = (row.get("cited_text", ""))[:ANCHOR_CHAR_CAP]
        label = row.get("label_letter", "?")
        ctx = (
            f"EPO claim {row.get('claim_id')} (application {row.get('patent_application_id')}):\n"
            f"\nCLAIM: {claim}\n"
            f"\nCITED PRIOR ART {label} ({row.get('cited_document_id')}):\n{cited}"
        )
        meta = {
            "source": "patentmatch",
            "claim_id": row.get("claim_id"),
            "patent_application_id": row.get("patent_application_id"),
            "cited_document_id": row.get("cited_document_id"),
            "label_letter": label,
        }
        return ctx, meta
    if source == "bigpatent":
        ipc = (row.get("ipc_class") or "?").upper()
        abstract = (row.get("abstract") or "")[:ANCHOR_CHAR_CAP]
        ctx = f"BIGPATENT abstract (IPC class {ipc}):\n\n{abstract}"
        meta = {
            "source": "bigpatent",
            "ipc_class": row.get("ipc_class"),
            "patent_number": row.get("patent_number"),
        }
        return ctx, meta
    raise ValueError(f"unknown source: {source}")


# --- Claude call --------------------------------------------------------


SYSTEM_PROMPT = (
    "You are a senior US patent attorney drafting evaluation questions for an "
    "AI patent-strategist benchmark. You output JSON only — no prose, no "
    "markdown fences. Your output is a single JSON array of question objects "
    "in the exact schema specified by the user. You never include the array in "
    "a code fence or surround it with explanation text."
)

BATCH_PROMPT_TEMPLATE = """\
Generate exactly {batch_size} eval question(s) for SHAPE {shape} (family {family}).

{instructions}

Each question MUST be a JSON object with these fields:
{{
  "question": "<the question text the model will see>",
  "use_case": "<one of {use_cases}>",
  "gold_label": "<the reference answer or correct MCQ letter as a string>",
  "options": <list[str] of 4 options for MCQ shapes, otherwise []>,
  "rubric_notes": "<one-sentence hint for the human reviewer in T9>"
}}

ANCHOR CONTEXT (use this as the substantive ground for the question(s)):
---
{anchor}
---

Constraints:
- Vary `use_case` across the batch.
- Do NOT inline the option letters into the `question` string for MCQ rows — keep options in the `options` field only.
- For non-MCQ shapes, `options` MUST be an empty list [].
- `gold_label` is a string. For MCQ: one letter "A"|"B"|"C"|"D". Otherwise: 1-5 sentences.
- Output: a JSON array of {batch_size} objects. Nothing else.
"""


def call_claude(prompt: str, max_budget_usd: float | None = None) -> str:
    """Call `claude -p` and return the result string (model text output).

    Raises `subprocess.CalledProcessError` on non-zero exit. Times out after
    `CLAUDE_TIMEOUT_S` seconds.
    """
    cmd = [
        CLAUDE_BIN,
        "-p",
        "--model", CLAUDE_MODEL,
        "--system-prompt", SYSTEM_PROMPT,
        "--output-format", "json",
        "--no-session-persistence",
    ]
    if max_budget_usd is not None:
        cmd.extend(["--max-budget-usd", str(max_budget_usd)])
    cmd.append(prompt)
    proc = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=CLAUDE_TIMEOUT_S,
        check=False,
    )
    if proc.returncode != 0:
        sys.stderr.write(f"[claude] exit={proc.returncode}\n[stderr]\n{proc.stderr}\n")
        raise subprocess.CalledProcessError(proc.returncode, cmd, proc.stdout, proc.stderr)
    # `--output-format json` returns one JSON object with a "result" field
    # containing the model's text output.
    envelope = json.loads(proc.stdout)
    return envelope.get("result", "")


_FENCE_RE = re.compile(r"^```(?:json)?\s*\n(.+?)\n```\s*$", re.DOTALL)


def parse_question_batch(raw: str) -> list[dict[str, Any]]:
    """Coerce Claude's response into a list of question dicts.

    Tolerates: markdown fences, leading/trailing prose, single-object responses
    (wraps in list), JSON with a wrapping {"questions": [...]} key.
    """
    s = raw.strip()
    m = _FENCE_RE.match(s)
    if m:
        s = m.group(1).strip()
    # Find first '[' or '{' so leading prose doesn't break json.loads.
    first_arr = s.find("[")
    first_obj = s.find("{")
    starts = [p for p in (first_arr, first_obj) if p != -1]
    if not starts:
        return []
    s = s[min(starts):]
    # Walk back from the end for the matching closer (handles trailing prose).
    for end_char in ("]", "}"):
        last = s.rfind(end_char)
        if last != -1:
            try:
                obj = json.loads(s[: last + 1])
                break
            except json.JSONDecodeError:
                continue
    else:
        return []
    if isinstance(obj, dict):
        # {"questions": [...]} | {"data": [...]} | a single question dict
        for k in ("questions", "data", "items"):
            v = obj.get(k)
            if isinstance(v, list):
                obj = v
                break
        else:
            obj = [obj]
    if not isinstance(obj, list):
        return []
    return [q for q in obj if isinstance(q, dict)]


# --- row construction ---------------------------------------------------


@dataclass
class GenStats:
    """Per-run counters surfaced at end-of-run."""

    requested: int = 0
    generated: int = 0
    dropped: int = 0
    api_calls: int = 0
    api_seconds: float = 0.0
    dedupe_skipped: int = 0
    errors: list[str] = field(default_factory=list)


def _qid(family: str, use_case: str, question: str) -> str:
    digest = hashlib.sha256(question.encode("utf-8")).hexdigest()[:10]
    return f"ps-{family}-{use_case}-{digest}"


def normalize_row(
    raw: dict[str, Any],
    spec: ShapeSpec,
    anchor_ctx: str,
    anchor_meta: dict[str, Any],
    dry_run: bool,
) -> dict[str, Any] | None:
    """Map Claude's batch entry into a patent-strategist JSONL row.

    Returns None if the row is malformed (missing question/gold_label, or MCQ
    without 4 options).
    """
    question = (raw.get("question") or "").strip()
    gold_label = raw.get("gold_label")
    use_case = (raw.get("use_case") or "").strip() or spec.use_cases[0]
    options = raw.get("options") or []
    rubric_notes = (raw.get("rubric_notes") or "").strip() or None

    if not question or not gold_label:
        return None
    if spec.shape == "D-mcq":
        if not isinstance(options, list) or len(options) != 4:
            return None
        if str(gold_label).strip().upper() not in {"A", "B", "C", "D"}:
            return None
        gold_label = str(gold_label).strip().upper()
    else:
        options = []  # non-MCQ shapes carry no options
        gold_label = str(gold_label).strip()

    # Per-shape source_status flag — feeds T9 reviewer prioritization.
    synthesized_shapes = {"C", "D-oa", "E"}
    source_status = "synthesized" if spec.shape in synthesized_shapes else "anchored"

    tags: dict[str, Any] = {
        "shape": spec.shape,
        "source_status": source_status,
        "rubric_notes": rubric_notes,
        **{k: v for k, v in anchor_meta.items() if v is not None},
    }
    if dry_run:
        tags["dry_run"] = True

    return {
        "qid": _qid(spec.family, use_case, question),
        "question": question,
        "family": spec.family,
        "use_case": use_case,
        "scoring_mode": "oracle",
        "gold_label": gold_label,
        "options": options,
        "context": None,
        "oracle_context": anchor_ctx,
        "rubric": None,
        "reviewed": False,
        "tags": tags,
    }


def load_existing_qids(path: Path) -> set[str]:
    if not path.exists():
        return set()
    qids: set[str] = set()
    for row in _iter_jsonl(path):
        qid = row.get("qid")
        if isinstance(qid, str):
            qids.add(qid)
    return qids


# --- per-shape driver ---------------------------------------------------


def make_dry_row(spec: ShapeSpec, anchor_ctx: str, anchor_meta: dict[str, Any], idx: int) -> dict[str, Any]:
    """Build a stub row without calling Claude — for plumbing tests + T9 dev."""
    use_case = spec.use_cases[idx % len(spec.use_cases)]
    if spec.shape == "D-mcq":
        question = f"[DRY] Per the cited MPEP section, which statute governs the rejection described? (stub {idx})"
        options = [
            "35 USC § 101 — patent-eligible subject matter",
            "35 USC § 102 — novelty",
            "35 USC § 103 — non-obviousness",
            "35 USC § 112 — written description / enablement",
        ]
        gold_label = "C"
    else:
        question = f"[DRY] {spec.shape} stub question {idx} anchored on {anchor_meta.get('source')}"
        options = []
        gold_label = f"[DRY reference answer for {spec.shape} {use_case}]"
    raw = {
        "question": question,
        "use_case": use_case,
        "gold_label": gold_label,
        "options": options,
        "rubric_notes": f"DRY stub — no Claude call. Anchor #{idx}.",
    }
    return normalize_row(raw, spec, anchor_ctx, anchor_meta, dry_run=True)  # type: ignore[return-value]


def seed_shape(
    spec: ShapeSpec,
    output_dir: Path,
    *,
    target: int,
    batch_size: int,
    anchors: list[dict[str, Any]],
    dry_run: bool,
    max_budget_usd: float | None,
    stats: GenStats,
) -> None:
    out_path = output_dir / f"seed-{spec.shape}.jsonl"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    existing = load_existing_qids(out_path)
    deficit = max(0, target - len(existing))
    stats.requested += deficit
    if deficit == 0:
        print(f"[{spec.shape}] already at target ({len(existing)}/{target}) — skipping.")
        return
    print(f"[{spec.shape}] {len(existing)}/{target} on disk; generating {deficit} new rows.")

    anchor_iter = iter(anchors)
    rows_written = 0
    f = out_path.open("a")
    try:
        while rows_written < deficit:
            try:
                anchor_row = next(anchor_iter)
            except StopIteration:
                stats.errors.append(f"{spec.shape}: anchor pool exhausted at {rows_written}/{deficit}")
                break
            anchor_ctx, anchor_meta = render_anchor(spec.source, anchor_row)
            batch_n = min(batch_size, deficit - rows_written)

            if dry_run:
                for i in range(batch_n):
                    row = make_dry_row(spec, anchor_ctx, anchor_meta, rows_written + i)
                    if row["qid"] in existing:
                        stats.dedupe_skipped += 1
                        continue
                    existing.add(row["qid"])
                    f.write(json.dumps(row) + "\n")
                    rows_written += 1
                    stats.generated += 1
                continue

            prompt = BATCH_PROMPT_TEMPLATE.format(
                batch_size=batch_n,
                shape=spec.shape,
                family=spec.family,
                use_cases=spec.use_cases,
                instructions=spec.instructions,
                anchor=anchor_ctx,
            )
            t0 = time.perf_counter()
            try:
                raw = call_claude(prompt, max_budget_usd=max_budget_usd)
            except subprocess.TimeoutExpired:
                stats.errors.append(f"{spec.shape}: timeout after {CLAUDE_TIMEOUT_S}s — skipping anchor")
                continue
            except subprocess.CalledProcessError as e:
                stats.errors.append(f"{spec.shape}: claude exit {e.returncode} — skipping anchor")
                continue
            stats.api_calls += 1
            stats.api_seconds += time.perf_counter() - t0

            entries = parse_question_batch(raw)
            if not entries:
                stats.dropped += batch_n
                stats.errors.append(f"{spec.shape}: parse failure on batch (len(raw)={len(raw)})")
                continue
            for raw_entry in entries:
                row = normalize_row(raw_entry, spec, anchor_ctx, anchor_meta, dry_run=False)
                if row is None:
                    stats.dropped += 1
                    continue
                if row["qid"] in existing:
                    stats.dedupe_skipped += 1
                    continue
                existing.add(row["qid"])
                f.write(json.dumps(row) + "\n")
                f.flush()  # crash-safety: each row durable before next API call
                rows_written += 1
                stats.generated += 1
                if rows_written >= deficit:
                    break
    finally:
        f.close()
    final_n = len(load_existing_qids(out_path))
    print(f"[{spec.shape}] wrote {rows_written} new rows → {final_n}/{target} total.")


# --- CLI ----------------------------------------------------------------


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR), type=Path,
                    help="Where seed-<shape>.jsonl files land. Defaults to %(default)s.")
    ap.add_argument("--shape", action="append", choices=sorted(SHAPES.keys()),
                    help="One or more shapes to seed. Repeatable. Default: all if --all is set, else none (use --shape or --all).")
    ap.add_argument("--all", action="store_true",
                    help="Seed every shape to its spec target (200 rows total).")
    ap.add_argument("--target", type=int, default=None,
                    help="Override the per-shape target (default: shape's spec target).")
    ap.add_argument("--per-shape", type=int, default=None,
                    help="Alias for --target — set the same cap on every requested shape.")
    ap.add_argument("--batch-size", type=int, default=5,
                    help="Questions per Claude call. Default 5 — keeps per-call cost ~$0.10-0.20.")
    ap.add_argument("--seed", type=int, default=42, help="RNG seed for anchor shuffling.")
    ap.add_argument("--dry-run", action="store_true",
                    help="Skip Claude entirely; write stub rows tagged dry_run=True (plumbing test).")
    ap.add_argument("--max-budget-usd", type=float, default=None,
                    help="Hard $-cap per Claude call (passed through as `claude -p --max-budget-usd`).")
    args = ap.parse_args()

    if not args.all and not args.shape:
        ap.error("must pass --all or one or more --shape SHAPE flags")
    shapes_to_run = list(SHAPES.keys()) if args.all else args.shape

    # Pre-load anchor pools once per source — avoids re-reading 60 MB jsonls per shape.
    sources_needed = {SHAPES[s].source for s in shapes_to_run}
    anchor_pool = {src: load_anchors(src, args.seed) for src in sources_needed}
    for src, pool in anchor_pool.items():
        print(f"[anchors] {src}: {len(pool)} rows loaded.")

    stats = GenStats()
    t0 = time.perf_counter()
    for shape_key in shapes_to_run:
        spec = SHAPES[shape_key]
        target = args.per_shape or args.target or spec.target
        seed_shape(
            spec,
            args.output_dir,
            target=target,
            batch_size=args.batch_size,
            anchors=list(anchor_pool[spec.source]),
            dry_run=args.dry_run,
            max_budget_usd=args.max_budget_usd,
            stats=stats,
        )
    wall = time.perf_counter() - t0

    print()
    print("=== seed_patent_bench summary ===")
    print(f"  wall:           {wall:.1f}s")
    print(f"  requested:      {stats.requested}")
    print(f"  generated:      {stats.generated}")
    print(f"  dropped:        {stats.dropped}")
    print(f"  dedupe skips:   {stats.dedupe_skipped}")
    print(f"  claude calls:   {stats.api_calls} ({stats.api_seconds:.1f}s total)")
    if stats.errors:
        print(f"  errors ({len(stats.errors)}):")
        for e in stats.errors[:20]:
            print(f"    - {e}")
        if len(stats.errors) > 20:
            print(f"    … and {len(stats.errors) - 20} more")
    # Exit non-zero only if the bench is short of the requested target. Transient
    # per-anchor errors that the script recovered from (timeout → skip anchor →
    # retry with a fresh one) still produce stats.errors entries but should not
    # poison the exit code when generated == requested.
    return 0 if stats.generated >= stats.requested else 1


if __name__ == "__main__":
    sys.exit(main())
