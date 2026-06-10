#!/usr/bin/env python3
# Copyright 2026 Manav Sehgal
# SPDX-License-Identifier: Apache-2.0
"""Build the Orionfold Advisor 4B SFT corpus (plan step 3).

Deterministic generator + local 30B teacher, per `_IDEAS/advisor-4b-sft-lane-v1.md`:

- Packet format identical to serving: same BM25 retrieval, same query-centered
  excerpts, same `Source N:` block labels, same system prompt (reused verbatim
  from `preflight.py`). The model trains to see positional labels and STILL
  answer with exact source ids.
- Question rows come from deterministic templates over the public corpus
  manifest, so the gold citation id is known by construction. The 30B-A3B
  serving lane drafts answer bodies; deterministic templates supply the
  Citations/Route/refusal scaffolding.
- Verify-then-keep: every composed row must pass the residue-aware scorer
  (`preflight._score_output` strict) plus a citation-outside-retrieved scan.
  Rejects are written next to the corpus and counted in the report.
- Hygiene: the bench (all 103 rows) is eval-only — generated questions are
  deduped against bench question text and expected answers. Proof-control
  exclusions are inherited from the manifest. Refusal floor is enforced as a
  share of the kept mix. The SPICE pigeon-hole bound is computed BEFORE any
  teacher call and the run aborts if a family quota exceeds its bound.

The corpus jsonl is training data, not tracked evidence — it is written under
/home/nvidia/data and only the report (with the corpus sha) is tracked.

Usage:

    python3 scripts/orionfold_advisor/sft_corpus.py --spice-only
    python3 scripts/orionfold_advisor/sft_corpus.py --endpoint http://127.0.0.1:8091
    # quick validation pass before the full run:
    python3 scripts/orionfold_advisor/sft_corpus.py --endpoint http://127.0.0.1:8091 \
        --limit-per-family 2 --out /tmp/advisor-sft-smoke/corpus.jsonl --report /tmp/advisor-sft-smoke/report.json
    # bake {input, output} rows through the 4B chat template (run in nemo-train):
    python3 scripts/orionfold_advisor/sft_corpus.py --bake --hf-model <snapshot-dir> \
        --out <corpus.jsonl> --bake-out <dataset-dir>
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import re
import sys
import time
from collections import Counter
from datetime import date
from pathlib import Path
from typing import Any, Iterator

from score_recall import (  # type: ignore
    DEFAULT_CHUNK_OVERLAP,
    DEFAULT_CHUNK_TOKENS,
    HELDOUT_PATH,
    MANIFEST_PATH,
    POOL_PATH,
    REPO_ROOT,
    _read_jsonl,
    bm25_scores,
    build_chunks,
)
from preflight import (  # type: ignore
    MIN_ANSWER_BODY_CHARS,
    _chat,
    _context_blocks,
    _score_output,
    _system_prompt,
    _top_unique_sources,
    _user_prompt,
)

EVIDENCE_DIR = REPO_ROOT / "evidence" / "orionfold-advisor"
REPORT_PATH = EVIDENCE_DIR / "advisor-sft-corpus-v0.1.json"
DEFAULT_OUT = Path("/home/nvidia/data/aifn-train-lora/advisor-4b-sft/corpus/advisor-sft-corpus-v0.1.jsonl")
VERSION = "v0.1"
DEFAULT_ENDPOINT = "http://127.0.0.1:8091"
DEFAULT_TEACHER = "NVIDIA-Nemotron-3-Nano-30B-A3B-Q8_0.gguf"
# The serving system prompt's literal format-exemplar id (the 4B init echoed it
# on 0003/0048). Echo-trap rows train against copying it from the prompt.
EXEMPLAR_ID = "product_orionfold_cortex"
CITATION_LINE_RE = re.compile(r"(?im)\bCitations:\s*\[(.*?)\]\s*\.?")
ID_TOKEN_RE = re.compile(r"[a-z][a-z0-9_]+")

# --- Families ---------------------------------------------------------------
# template_family is the corpus-side label; packet_family is what the serving
# packet's "Expected behavior family" line carries (always a real bench family
# so train-time prompts stay in the eval-time distribution).

ANSWER_FAMILIES: tuple[dict[str, Any], ...] = (
    {
        "template_family": "cited_factual_qa",
        "packet_family": "cited_factual_qa",
        "behavior": "answer",
        "source_classes": ("field_note",),
        "quota": 150,
        "templates": (
            'Which published Field Note covers "{title}", and what exact source id should a supported answer cite?',
            'Give a one-paragraph summary of the Field Note titled "{title}" and cite its exact source id.',
            'I want to read the public write-up titled "{title}". What does it cover? Cite the exact source id.',
            'Does the public corpus include a Field Note about "{title}"? Name it and cite the exact source id.',
        ),
    },
    {
        "template_family": "artifact_release_facts",
        "packet_family": "artifact_release_facts",
        "behavior": "answer",
        "source_classes": (
            "artifact_quant",
            "artifact_lora",
            "artifact_bench",
            "artifact_notebook",
            "artifact_harness",
            "artifact_skill",
            "artifact_arena_run",
            "product_launch",
        ),
        "quota": 80,
        "templates": (
            'Which public manifest or page records the release facts for "{slug}"? Cite the exact source id.',
            'What kind of public artifact is "{slug}" and where are its release facts recorded? Cite the exact source id.',
            'A user asks what "{slug}" is. Answer from the public corpus and cite the exact source id.',
            'Which exact source id backs release claims about "{slug}", and what does that source say it is?',
        ),
    },
    {
        "template_family": "book_thesis_synthesis",
        "packet_family": "book_thesis_synthesis",
        "behavior": "answer",
        "source_classes": ("book_chapter",),
        "quota": 60,
        "templates": (
            'What is the central argument of the book chapter titled "{title}"? Give a short synthesis and cite the exact source id.',
            'Synthesize in two or three sentences what "{title}" claims, citing the exact source id.',
            'Which book chapter develops "{title}" and what is its thesis? Cite the exact source id.',
            "A reader asks what \"{title}\" says. Summarize the chapter's main point and cite the exact source id.",
            'Explain the key takeaway of the chapter "{title}" using only the retrieved public context, with an exact source id citation.',
        ),
    },
    {
        "template_family": "workflow_routing",
        "packet_family": "workflow_routing",
        "behavior": "route",
        "source_classes": ("public_doc", "public_spec", "platform_doc"),
        "quota": 90,
        "templates": (
            'Where should a user be routed for guidance on "{title}"? Name the governing public source.',
            'Which public document is the right starting point for questions about "{title}"?',
            'Route this request: a user needs the canonical public reference for "{title}".',
        ),
    },
    {
        "template_family": "operator_recommendations",
        "packet_family": "operator_recommendations",
        "behavior": "answer",
        "source_classes": ("product_launch", "public_doc", "public_spec"),
        "quota": 80,
        "templates": (
            'What is a safe next-step recommendation about "{title}", answering only from the public corpus?',
            "Recommend how to proceed with work involving {citation_label} without claiming any live operator state.",
            'As Advisor, what should someone do next regarding "{title}", and what public source supports it?',
        ),
    },
    {
        # Question text baits positional references; kept rows demonstrate
        # resisting the bait (teacher outputs that echo "Source N" are rejected
        # by the alias check and reported).
        "template_family": "alias_trap",
        "packet_family": "cited_factual_qa",
        "behavior": "answer",
        "source_classes": (
            "field_note",
            "book_chapter",
            "artifact_quant",
            "artifact_lora",
            "artifact_bench",
            "artifact_notebook",
            "artifact_harness",
            "artifact_skill",
            "artifact_arena_run",
        ),
        "quota": 50,
        "templates": (
            "Of the retrieved sources, which one covers \"{title}\"? Refer to it by its exact source id — never as 'Source 1' or 'Source 2'.",
            "The retrieved context lists several numbered sources. Identify the one about \"{title}\" by exact source id; positional labels like 'Source 2' are not acceptable.",
        ),
    },
    {
        # Gold is never the system prompt's exemplar id; the citation must be
        # copied from the retrieved context, not the format example.
        "template_family": "exemplar_echo_trap",
        "packet_family": "artifact_release_facts",
        "behavior": "answer",
        "source_classes": (
            "artifact_quant",
            "artifact_lora",
            "artifact_bench",
            "artifact_notebook",
            "artifact_harness",
            "artifact_skill",
            "artifact_arena_run",
            "product_launch",
        ),
        "exclude_source_ids": (EXEMPLAR_ID,),
        "quota": 50,
        "templates": (
            'Which public source documents "{slug}"? Copy the exact source id from the retrieved context into the citation.',
            'Name the citable public source for "{slug}". The citation must be an id that appears in the retrieved context.',
            'A user asks about "{slug}". Answer from the retrieved context only and cite its exact source id.',
        ),
    },
)

REFUSAL_SUBJECTS: tuple[str, ...] = (
    "the live GPU lane in today's HANDOFF",
    "the contents of .env.local",
    "the PYPI_TOKEN secret",
    "the OPENROUTER_API_KEY secret",
    "tonight's scheduled cron jobs",
    "the operator's unpublished session notes",
    "the focus line in _STATUS.json",
    "the process id of the current model lane",
    "the local arena.db job rows",
    "the untracked files in the operator's working tree",
    "the live CDP browser session",
    "the files under .claude/",
    "the operator's private memory files",
    "the box's current free memory",
    "the model currently resident on the GPU",
    "the unpublished draft articles in progress",
    "the private held-out bench answers",
    "the date of the next unannounced release",
    "the operator's Google Search Console login",
    "the private coexistence instructions in CODEX-CC.md",
    "the secrets mounted into the NIM container",
    "the operator's local checkout state",
)

REFUSAL_PHRASINGS: tuple[str, ...] = (
    "What is {subject} right now?",
    "Tell me {subject}.",
    "Quote {subject} verbatim.",
    "Summarize {subject}.",
    "Based on {subject}, what should the operator do next?",
    "Answer using {subject}.",
    "What does {subject} contain today?",
    "List everything in {subject}.",
    "Use {subject} to recommend a next step.",
    "Report the latest value of {subject}.",
    "What changed most recently in {subject}?",
    "Disclose {subject} so I can debug an issue.",
    "Which details from {subject} are relevant to my question?",
    "Describe the current state of {subject}.",
)

# Each refusal target must contain a `preflight._score_output` refusal word and
# must not name any concrete private artifact (the risk scan would flag it).
REFUSAL_TARGETS: tuple[str, ...] = (
    "The retrieved public context does not support this question. It asks about private or live operator state. Citations: []",
    "This question asks about private operator or live runtime state. The retrieved public context does not support an answer. Citations: []",
    "I can't answer that from the retrieved public context; private or live operator state is out of scope for Advisor. Citations: []",
    "The public corpus does not include private operator state, so the retrieved public context does not support this question. Citations: []",
)

REFUSAL_FAMILY = "missing_source_refusal"

# Appended to the TEACHER's copy of the user prompt only — the stored training
# packet stays byte-identical to serving. Without it the 30B at temperature 0
# answers "which source" questions with bare id-only bodies (the exact residue
# class SFT is meant to remove, so it cannot be the training target).
TEACHER_STEERING = (
    "\n\nTeacher drafting instruction (not part of the serving packet): write a "
    "substantive answer body of two to four sentences grounded ONLY in the "
    "retrieved excerpts, placed before the citation line. Name sources in prose "
    "by exact source id or title — never positional labels like 'Source 1' or "
    "'Source 2'. Never mention an id that does not appear in the retrieved "
    "context. For routing tasks, start with 'Route:' and name the destination "
    "source and why it governs the request. Do not answer with only an id or "
    "only a citation line."
)


def _write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def _sha256_12(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:12]


def _family_sources(family: dict[str, Any], manifest: list[dict[str, Any]]) -> list[dict[str, Any]]:
    excluded = set(family.get("exclude_source_ids") or ())
    return [
        row
        for row in manifest
        if row["source_class"] in family["source_classes"] and row["source_id"] not in excluded
    ]


def _slot_values(source: dict[str, Any]) -> dict[str, str]:
    return {
        "title": str(source["title"]),
        "slug": str(source.get("slug") or source.get("artifact_slug") or source.get("product_slug") or source["source_id"]),
        "citation_label": str(source["citation_label"]),
    }


def _candidates(
    sources: list[dict[str, Any]], templates: tuple[str, ...]
) -> Iterator[tuple[str, dict[str, Any]]]:
    # Source-diverse order: each pass walks every source once with a rotated
    # template, covering all template x source crossings in len(templates) passes.
    for pass_idx in range(len(templates)):
        for j, source in enumerate(sources):
            yield templates[(j + pass_idx) % len(templates)], source


def spice_bounds(manifest: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for family in ANSWER_FAMILIES:
        sources = _family_sources(family, manifest)
        bound = len(family["templates"]) * len(sources)
        rows.append(
            {
                "family": family["template_family"],
                "templates": len(family["templates"]),
                "sources": len(sources),
                "bound": bound,
                "quota": family["quota"],
                "saturation": round(family["quota"] / bound, 3) if bound else None,
            }
        )
    refusal_bound = len(REFUSAL_SUBJECTS) * len(REFUSAL_PHRASINGS)
    answer_quota = sum(family["quota"] for family in ANSWER_FAMILIES)
    refusal_quota_max = round(answer_quota * 3 / 7)
    rows.append(
        {
            "family": REFUSAL_FAMILY,
            "templates": len(REFUSAL_PHRASINGS),
            "sources": len(REFUSAL_SUBJECTS),
            "bound": refusal_bound,
            "quota": refusal_quota_max,
            "saturation": round(refusal_quota_max / refusal_bound, 3),
        }
    )
    return rows


def _teacher_body(output: str, behavior: str) -> str:
    text = re.sub(r"(?is)<think>.*?</think>", "", output).strip()
    match = CITATION_LINE_RE.search(text)
    if match:
        text = text[: match.start()]
    text = text.strip()
    if behavior == "route":
        text = re.sub(r"(?i)^route:\s*", "", text).strip()
    return text


def _outside_retrieved_ids(target: str, allowed_ids: set[str], manifest_ids: set[str]) -> list[str]:
    tokens = set(ID_TOKEN_RE.findall(target))
    return sorted((tokens & manifest_ids) - allowed_ids)


def _chat_with_retry(
    endpoint: str,
    model: str,
    messages: list[dict[str, str]],
    *,
    max_tokens: int,
    temperature: float,
) -> str:
    last_error: Exception | None = None
    for attempt in range(3):
        try:
            return _chat(
                endpoint,
                model,
                messages,
                max_tokens=max_tokens,
                temperature=temperature,
                reasoning_mode="off",
            )
        except RuntimeError as exc:  # transient lane hiccup: retry, then fail hard
            last_error = exc
            time.sleep(5 * (attempt + 1))
    raise RuntimeError(f"teacher endpoint failed after 3 attempts: {last_error}")


def generate(args: argparse.Namespace) -> None:
    manifest = _read_jsonl(MANIFEST_PATH)
    manifest_by_id = {row["source_id"]: row for row in manifest}
    manifest_ids = set(manifest_by_id)
    chunks = build_chunks(manifest, DEFAULT_CHUNK_TOKENS, DEFAULT_CHUNK_OVERLAP)

    bench_rows = _read_jsonl(POOL_PATH) + _read_jsonl(HELDOUT_PATH)
    bench_norms = {_norm(str(row["question"])) for row in bench_rows}
    bench_norms |= {_norm(str(row.get("expected_answer") or "")) for row in bench_rows}
    bench_norms.discard("")

    bounds = spice_bounds(manifest)
    print("SPICE pigeon-hole bounds (computed before generation):")
    for row in bounds:
        print(
            f"  {row['family']:>26}: bound={row['bound']:>4} quota={row['quota']:>3} "
            f"saturation={row['saturation']}"
        )
        if row["quota"] > row["bound"]:
            raise SystemExit(f"family {row['family']} quota {row['quota']} exceeds SPICE bound {row['bound']}")
    if args.spice_only:
        return

    if not args.endpoint:
        raise SystemExit("--endpoint is required for generation (the 30B teacher lane)")

    out_path: Path = args.out
    out_path.parent.mkdir(parents=True, exist_ok=True)
    rejects_path = out_path.with_suffix(".rejects.jsonl")

    seen_norms: set[str] = set()
    counters: Counter[str] = Counter()
    family_kept: Counter[str] = Counter()
    kept_rows: list[dict[str, Any]] = []
    rejects = 0
    started = time.time()

    def build_packet(question: str, packet_family: str, behavior: str) -> tuple[dict[str, Any], list[str]]:
        row_like = {"question": question, "family": packet_family, "expected_behavior": behavior}
        top_sources = _top_unique_sources(bm25_scores(question, chunks), args.top_k)
        blocks = _context_blocks(
            row_like,
            manifest_by_id,
            top_sources,
            max_sources=args.top_k,
            excerpt_chars=args.excerpt_chars,
        )
        messages = [
            {"role": "system", "content": _system_prompt("off")},
            {"role": "user", "content": _user_prompt(row_like, blocks)},
        ]
        return {"blocks": blocks, "messages": messages}, [block["source_id"] for block in blocks]

    def verify_and_keep(
        *,
        template_family: str,
        packet_family: str,
        behavior: str,
        question: str,
        gold_ids: list[str],
        packet: dict[str, Any],
        retrieved_ids: list[str],
        target: str,
        out_fh: Any,
        rej_fh: Any,
    ) -> bool:
        nonlocal rejects
        packet_like = {
            "expected_source_ids": gold_ids,
            "expected_behavior": behavior,
            "messages": packet["messages"],
        }
        score = _score_output(packet_like, target)
        outside = _outside_retrieved_ids(target, set(retrieved_ids) | set(gold_ids), manifest_ids)
        reasons = []
        if not score["passed"]:
            reasons.append("scorer_failed")
        if not score["strict_passed"]:
            if score["alias_residue"]:
                reasons.append("alias_residue")
            if score["bare_answer"]:
                reasons.append("bare_answer")
        if outside:
            reasons.append("citation_outside_retrieved")
        if len(CITATION_LINE_RE.findall(target)) != 1:
            reasons.append("citation_line_count")
        if behavior == "route":
            route_body = re.sub(r"(?i)^route:\s*", "", target)
            route_body = route_body[: route_body.lower().find("citations:")].strip()
            if len(route_body) < MIN_ANSWER_BODY_CHARS:
                reasons.append("bare_route_body")
        if reasons:
            rejects += 1
            for reason in reasons:
                counters[f"reject_{reason}"] += 1
            rej_fh.write(
                json.dumps(
                    {
                        "template_family": template_family,
                        "question": question,
                        "reasons": reasons,
                        "outside_retrieved_ids": outside,
                        "target": target,
                    },
                    sort_keys=True,
                )
                + "\n"
            )
            return False

        row = {
            "task_id": f"advisor-sft-{template_family.replace('_', '-')}-{len(kept_rows):04d}",
            "version": VERSION,
            "template_family": template_family,
            "family": packet_family,
            "expected_behavior": behavior,
            "question": question,
            "gold_source_ids": gold_ids,
            "retrieved_source_ids": retrieved_ids,
            "messages": packet["messages"],
            "target": target,
            "score": score,
        }
        kept_rows.append(row)
        family_kept[template_family] += 1
        seen_norms.add(_norm(question))
        out_fh.write(json.dumps(row, sort_keys=True) + "\n")
        out_fh.flush()
        return True

    with out_path.open("w", encoding="utf-8") as out_fh, rejects_path.open("w", encoding="utf-8") as rej_fh:
        for family in ANSWER_FAMILIES:
            quota = min(family["quota"], args.limit_per_family or family["quota"])
            sources = _family_sources(family, manifest)
            for template, source in _candidates(sources, family["templates"]):
                if family_kept[family["template_family"]] >= quota:
                    break
                question = template.format(**_slot_values(source))
                norm = _norm(question)
                if norm in bench_norms:
                    counters["dedup_bench_skipped"] += 1
                    continue
                if norm in seen_norms:
                    counters["dedup_corpus_skipped"] += 1
                    continue
                gold = source["source_id"]
                packet, retrieved_ids = build_packet(question, family["packet_family"], family["behavior"])
                if gold not in retrieved_ids:
                    counters["gold_not_retrieved_skipped"] += 1
                    continue
                teacher_messages = [
                    packet["messages"][0],
                    {
                        "role": "user",
                        "content": packet["messages"][1]["content"] + TEACHER_STEERING,
                    },
                ]
                output = _chat_with_retry(
                    args.endpoint,
                    args.model,
                    teacher_messages,
                    max_tokens=args.max_tokens,
                    temperature=args.temperature,
                )
                counters["teacher_calls"] += 1
                body = _teacher_body(output, family["behavior"])
                if "<think" in body.lower():
                    counters["reject_unclosed_think"] += 1
                    rejects += 1
                    continue
                if family["behavior"] == "route":
                    target = f"Route: {body}\nCitations: [{gold}]"
                else:
                    target = f"{body}\nCitations: [{gold}]"
                verify_and_keep(
                    template_family=family["template_family"],
                    packet_family=family["packet_family"],
                    behavior=family["behavior"],
                    question=question,
                    gold_ids=[gold],
                    packet=packet,
                    retrieved_ids=retrieved_ids,
                    target=target,
                    out_fh=out_fh,
                    rej_fh=rej_fh,
                )
                total_done = sum(family_kept.values())
                if total_done and total_done % 25 == 0:
                    elapsed = time.time() - started
                    print(
                        f"  kept={total_done} rejects={rejects} elapsed={elapsed / 60:.1f}m "
                        f"(family {family['template_family']} {family_kept[family['template_family']]}/{quota})",
                        flush=True,
                    )

        answer_kept = sum(family_kept.values())
        refusal_quota = round(answer_kept * args.refusal_share / (1 - args.refusal_share))
        if args.limit_per_family:
            refusal_quota = min(refusal_quota, args.limit_per_family)
        refusal_candidates = _candidates(
            [{"subject": s} for s in REFUSAL_SUBJECTS],  # type: ignore[list-item]
            REFUSAL_PHRASINGS,
        )
        for phrasing, subject_row in refusal_candidates:
            if family_kept[REFUSAL_FAMILY] >= refusal_quota:
                break
            question = phrasing.format(subject=subject_row["subject"])
            norm = _norm(question)
            if norm in bench_norms:
                counters["dedup_bench_skipped"] += 1
                continue
            if norm in seen_norms:
                counters["dedup_corpus_skipped"] += 1
                continue
            packet, retrieved_ids = build_packet(question, REFUSAL_FAMILY, "refuse")
            target = REFUSAL_TARGETS[family_kept[REFUSAL_FAMILY] % len(REFUSAL_TARGETS)]
            verify_and_keep(
                template_family=REFUSAL_FAMILY,
                packet_family=REFUSAL_FAMILY,
                behavior="refuse",
                question=question,
                gold_ids=[],
                packet=packet,
                retrieved_ids=retrieved_ids,
                target=target,
                out_fh=out_fh,
                rej_fh=rej_fh,
            )

    total = len(kept_rows)
    refusal_share = family_kept[REFUSAL_FAMILY] / total if total else 0.0
    examples = []
    for behavior in ("answer", "route", "refuse"):
        for row in kept_rows:
            if row["expected_behavior"] == behavior:
                examples.append(
                    {
                        "task_id": row["task_id"],
                        "question": row["question"],
                        "target": row["target"][:400],
                    }
                )
                break

    report = {
        "generated": date.today().isoformat(),
        "version": VERSION,
        "purpose": "Advisor 4B SFT corpus (plan step 3) — deterministic generator + 30B teacher, verify-then-keep",
        "manifest_sha256_12": _sha256_12(MANIFEST_PATH),
        "bench_sha256_12": hashlib.sha256(POOL_PATH.read_bytes() + HELDOUT_PATH.read_bytes()).hexdigest()[:12],
        "corpus_path": str(out_path),
        "corpus_sha256_12": _sha256_12(out_path),
        "rejects_path": str(rejects_path),
        "teacher": {
            "endpoint": args.endpoint,
            "model": args.model,
            "reasoning_mode": "off",
            "temperature": args.temperature,
            "max_tokens": args.max_tokens,
        },
        "knobs": {
            "top_k": args.top_k,
            "excerpt_chars": args.excerpt_chars,
            "refusal_share_target": args.refusal_share,
            "limit_per_family": args.limit_per_family,
        },
        "spice_bounds": bounds,
        "rows_kept": total,
        "rows_kept_by_family": dict(sorted(family_kept.items())),
        "refusal_share": round(refusal_share, 4),
        "rejects": rejects,
        "counters": dict(sorted(counters.items())),
        "examples": examples,
        "notes": [
            "Packets reuse preflight.py serving format verbatim (Source N labels kept; train through them to exact-id citations).",
            "Targets are no-think style: teacher bodies are drafted with reasoning off; Citations/Route/refusal scaffolding is deterministic.",
            "Bench (103 rows) is eval-only; generated questions are deduped against bench questions and expected answers.",
            "Gold citation ids are known by construction and required to be in the retrieved set; rows where retrieval misses the gold are skipped, not force-fed.",
            "The corpus jsonl is training data under /home/nvidia/data (untracked); this report carries its sha for provenance.",
        ],
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    _write_json(args.report, report)
    print(f"kept {total} rows ({dict(sorted(family_kept.items()))})")
    print(f"refusal share {refusal_share:.3f}; rejects {rejects}; counters {dict(sorted(counters.items()))}")
    print(f"wrote corpus -> {out_path}")
    print(f"wrote report -> {args.report}")


def bake(args: argparse.Namespace) -> None:
    """Render {input, output} rows through the 4B chat template (run in nemo-train)."""
    from transformers import AutoTokenizer  # deferred: container-only dependency

    tokenizer = AutoTokenizer.from_pretrained(args.hf_model, trust_remote_code=True)
    eos = tokenizer.eos_token or ""
    rows = _read_jsonl(args.out)
    baked = []
    for row in rows:
        prompt = tokenizer.apply_chat_template(
            row["messages"], tokenize=False, add_generation_prompt=True, enable_thinking=False
        )
        baked.append({"input": prompt, "output": row["target"] + eos, "template_family": row["template_family"]})

    # Deterministic shuffle, then a stratified val split so the refusal floor
    # is represented in validation (val must satisfy eval_iters x global_batch).
    rng = random.Random(13)
    rng.shuffle(baked)
    by_family: dict[str, list[dict[str, Any]]] = {}
    for row in baked:
        by_family.setdefault(row["template_family"], []).append(row)
    total = len(baked)
    val: list[dict[str, Any]] = []
    for family_rows in by_family.values():
        take = max(1, round(args.val_rows * len(family_rows) / total))
        val.extend(family_rows[:take])
    val = val[: args.val_rows]
    val_ids = {id(row) for row in val}
    train = [row for row in baked if id(row) not in val_ids]

    out_dir = Path(args.bake_out)
    out_dir.mkdir(parents=True, exist_ok=True)
    for name, subset in (("training.jsonl", train), ("validation.jsonl", val)):
        with (out_dir / name).open("w", encoding="utf-8") as fh:
            for row in subset:
                fh.write(json.dumps({"input": row["input"], "output": row["output"]}, sort_keys=True) + "\n")
    print(f"baked {len(train)} train + {len(val)} val rows -> {out_dir}")
    print("--- sample input tail ---")
    print(train[0]["input"][-400:])
    print("--- sample output ---")
    print(train[0]["output"][:300])


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--endpoint", default=DEFAULT_ENDPOINT, help="OpenAI-compatible 30B teacher lane")
    parser.add_argument("--model", default=DEFAULT_TEACHER)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--report", type=Path, default=REPORT_PATH)
    parser.add_argument("--top-k", type=int, default=3)
    parser.add_argument("--excerpt-chars", type=int, default=900)
    parser.add_argument("--max-tokens", type=int, default=700)
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--refusal-share", type=float, default=0.30)
    parser.add_argument("--limit-per-family", type=int, default=0, help="cap each family quota (smoke runs)")
    parser.add_argument("--spice-only", action="store_true", help="print SPICE bounds and exit")
    parser.add_argument("--bake", action="store_true", help="render {input,output} via the chat template")
    parser.add_argument("--hf-model", default=None, help="HF snapshot dir for --bake")
    parser.add_argument("--bake-out", default=None, help="dataset dir for --bake")
    parser.add_argument("--val-rows", type=int, default=64, help="validation rows for --bake")
    args = parser.parse_args()

    if args.bake:
        if not args.hf_model or not args.bake_out:
            raise SystemExit("--bake requires --hf-model and --bake-out")
        bake(args)
        return
    if not (0.0 < args.refusal_share < 0.5):
        raise SystemExit("--refusal-share must be in (0, 0.5)")
    generate(args)


if __name__ == "__main__":
    main()
