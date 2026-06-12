#!/usr/bin/env python3
# Copyright 2026 Manav Sehgal
# SPDX-License-Identifier: Apache-2.0
"""Deterministic gates for a grounded eval pack (grounded-eval-v1 §6c).

Every check is mechanical — no LLM. Exit code = number of failing rows (plus 1
for pack-level failures), so the authoring loop can gate on it.

Usage:
    python3 scripts/grounded_eval/verify_pack.py evidence/grounded-eval/cortex-grounded-ext.jsonl \
        [--manifest evidence/orionfold-advisor/public-corpus-manifest.jsonl] [--root .] \
        [--sft-corpus /home/nvidia/data/aifn-train-lora/advisor-4b-sft/corpus/advisor-sft-corpus-v0.2.jsonl] \
        [--apply-sft-tags] [--freeze --receipt evidence/grounded-eval/<pack>.receipt.json]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter
from datetime import date
from pathlib import Path

JOURNEYS = ("lookup", "howto", "synthesis", "troubleshoot", "refusal")
BEHAVIORS = ("answer", "refuse")
FACT_KINDS = ("contains", "regex", "numeric")
TASK_ID_RE = re.compile(r"^cg-(lookup|howto|synthesis|troubleshoot|refusal)-\d{4}$")
# Evaluator-hint phrases banned from production-shaped questions.
FORBIDDEN_PHRASES = ("according to", "source id", "source_id", "cite ", "citation", "the article titled")
_DEFAULT_SFT_CORPUS = "/home/nvidia/data/aifn-train-lora/advisor-4b-sft/corpus/advisor-sft-corpus-v0.2.jsonl"
_CITATIONS_RE = re.compile(r"Citations:\s*\[(.*?)\]")
_STOP = {"the", "a", "an", "on", "and", "of", "to", "in", "for", "with", "from", "spark", "dgx"}


def _norm_tokens(text: str) -> list[str]:
    return [t for t in re.findall(r"[a-z0-9]+", (text or "").lower()) if t not in _STOP and len(t) > 2]


def _norm_body(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").lower())


def _title_echo(question: str, title: str, n: int = 4) -> bool:
    """True when ``question`` contains a contiguous ``n``-gram of ``title``."""
    tt, qt = _norm_tokens(title), _norm_tokens(question)
    if len(tt) < n:
        return False
    qs = " ".join(qt)
    return any(" ".join(tt[i:i + n]) in qs for i in range(len(tt) - n + 1))


def _load_manifest(path: Path, root: Path) -> dict[str, dict]:
    rows = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            r = json.loads(line)
            rows[str(r["source_id"])] = r
    return rows


def _gold_bodies(ids: list[str], manifest: dict, root: Path, cache: dict) -> list[str]:
    bodies = []
    for sid in ids:
        if sid in cache:
            bodies.append(cache[sid])
            continue
        src = manifest.get(sid)
        if not src:
            continue
        p = root / str(src["path_or_url"])
        body = _norm_body(p.read_text(encoding="utf-8", errors="replace")) if p.is_file() else ""
        cache[sid] = body
        bodies.append(body)
    return bodies


def _fact_in_bodies(fact: dict, bodies: list[str]) -> bool:
    kind = fact.get("kind")
    values = [str(fact.get("value", ""))] + [str(a) for a in (fact.get("alt") or [])]
    if kind == "regex":
        return True  # compile-checked separately; regexes target the ANSWER, not the body
    needles = [_norm_body(v) for v in values if v]
    return any(n and n in b for n in needles for b in bodies)


def _sft_cited_ids(path: Path) -> set[str] | None:
    if not path.is_file():
        return None
    ids: set[str] = set()
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except ValueError:
            continue
        for m in _CITATIONS_RE.finditer(str(row.get("target") or row.get("answer") or "")):
            ids.update(re.findall(r"[a-z][a-z0-9_]+", m.group(1)))
    return ids


def check_row(row: dict, manifest: dict, root: Path, body_cache: dict) -> list[str]:
    errs: list[str] = []
    tid = str(row.get("task_id") or "")
    if not TASK_ID_RE.match(tid):
        errs.append(f"task_id {tid!r} not cg-<journey>-NNNN")
    journey = row.get("journey")
    if journey not in JOURNEYS:
        errs.append(f"journey {journey!r} invalid")
    elif TASK_ID_RE.match(tid) and f"-{journey}-" not in tid:
        errs.append("task_id journey segment mismatches journey field")
    behavior = row.get("expected_behavior")
    if behavior not in BEHAVIORS:
        errs.append(f"expected_behavior {behavior!r} invalid")

    q = str(row.get("question") or "")
    if not 40 <= len(q) <= 400:
        errs.append(f"question length {len(q)} outside 40..400")
    low = q.lower()
    for phrase in FORBIDDEN_PHRASES:
        if phrase in low:
            errs.append(f"question carries evaluator hint {phrase!r}")

    gold = [str(s) for s in (row.get("gold_source_ids") or [])]
    accepted = [str(s) for s in (row.get("accepted_citation_ids") or [])]
    facts = row.get("key_facts") or []

    for sid in gold + accepted:
        if sid not in manifest:
            errs.append(f"source id {sid!r} not in corpus manifest")

    if behavior == "refuse":
        if gold:
            errs.append("refusal row has gold_source_ids")
        if facts:
            errs.append("refusal row has key_facts")
    elif behavior == "answer":
        if not gold:
            errs.append("answer row has no gold_source_ids")
        if not accepted:
            errs.append("answer row has no accepted_citation_ids")
        if not facts:
            errs.append("answer row has no key_facts")
        if not str(row.get("expected_answer") or "").strip():
            errs.append("answer row has no expected_answer")
        for sid in gold:
            title = str(manifest.get(sid, {}).get("title") or "")
            if title and _title_echo(q, title):
                errs.append(f"question echoes gold title 4-gram ({sid})")
        bodies = _gold_bodies(gold, manifest, root, body_cache)
        for i, fact in enumerate(facts):
            if not isinstance(fact, dict) or fact.get("kind") not in FACT_KINDS:
                errs.append(f"key_facts[{i}] kind invalid")
                continue
            if fact.get("kind") == "regex":
                try:
                    re.compile(str(fact.get("value") or ""))
                except re.error as exc:
                    errs.append(f"key_facts[{i}] regex does not compile: {exc}")
            elif not _fact_in_bodies(fact, bodies):
                errs.append(f"key_facts[{i}] {fact.get('value')!r} not verbatim in any gold source body")
    return errs


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("pack")
    ap.add_argument("--manifest", default="evidence/orionfold-advisor/public-corpus-manifest.jsonl")
    ap.add_argument("--root", default=".")
    ap.add_argument("--sft-corpus", default=_DEFAULT_SFT_CORPUS)
    ap.add_argument("--apply-sft-tags", action="store_true",
                    help="rewrite in_sft_corpus per row from the SFT corpus citations")
    ap.add_argument("--freeze", action="store_true", help="stamp sha12 + write the receipt")
    ap.add_argument("--receipt", default=None)
    args = ap.parse_args()

    root = Path(args.root).resolve()
    pack_path = Path(args.pack)
    manifest = _load_manifest(root / args.manifest, root)
    raw = pack_path.read_bytes()
    rows = [json.loads(l) for l in raw.decode("utf-8").splitlines() if l.strip()]

    failures = 0
    body_cache: dict[str, str] = {}
    seen_ids: set[str] = set()
    norm_questions: list[tuple[str, set[str]]] = []
    for row in rows:
        errs = check_row(row, manifest, root, body_cache)
        tid = str(row.get("task_id") or "?")
        if tid in seen_ids:
            errs.append("duplicate task_id")
        seen_ids.add(tid)
        toks = set(_norm_tokens(str(row.get("question") or "")))
        for other_tid, other in norm_questions:
            union = toks | other
            if union and len(toks & other) / len(union) > 0.6:
                errs.append(f"near-duplicate of {other_tid} (Jaccard > 0.6)")
        norm_questions.append((tid, toks))
        if errs:
            failures += 1
            print(f"FAIL {tid}")
            for e in errs:
                print(f"  - {e}")

    sft_ids = _sft_cited_ids(Path(args.sft_corpus))
    sft_note = "sft corpus unavailable; in_sft_corpus left as-is" if sft_ids is None else None
    if sft_ids is not None:
        changed = False
        for row in rows:
            val = bool(set(row.get("gold_source_ids") or []) & sft_ids) if row.get("expected_behavior") == "answer" else False
            if args.apply_sft_tags and row.get("in_sft_corpus") != val:
                row["in_sft_corpus"] = val
                changed = True
        if args.apply_sft_tags and changed:
            pack_path.write_text(
                "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
            raw = pack_path.read_bytes()
            print("in_sft_corpus tags applied (pack rewritten)")

    counts = Counter(r.get("journey") for r in rows)
    in_sft = sum(1 for r in rows if r.get("in_sft_corpus"))
    print(f"\n{pack_path.name}: {len(rows)} rows · " +
          " · ".join(f"{j} {counts.get(j, 0)}" for j in JOURNEYS) +
          f" · in-SFT-overlap {in_sft}" + (f" · NOTE {sft_note}" if sft_note else ""))
    print(f"failures: {failures}")

    if args.freeze:
        if failures:
            print("freeze refused: pack has failures")
            return failures + 1
        sha12 = hashlib.sha256(raw).hexdigest()[:12]
        receipt = {
            "pack": pack_path.name,
            "sha256_12": sha12,
            "rows": len(rows),
            "journeys": {j: counts.get(j, 0) for j in JOURNEYS},
            "in_sft_overlap": in_sft,
            "sft_corpus_available": sft_ids is not None,
            "manifest": str(args.manifest),
            "frozen": date.today().isoformat(),
        }
        receipt_path = Path(args.receipt or pack_path.with_suffix("").as_posix() + ".receipt.json")
        receipt_path.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
        print(f"FROZEN sha256_12={sha12} → {receipt_path}")
    return failures


if __name__ == "__main__":
    raise SystemExit(main())
