#!/usr/bin/env python3
# Copyright 2026 Manav Sehgal
# SPDX-License-Identifier: Apache-2.0
"""Deterministic candidate miner for the grounded eval pack (grounded-eval-v1 §6a).

Pure transforms over the corpus manifest + source bodies — NO LLM calls (per
``feedback_llm_skill_pattern``). Emits journey-tagged *candidates* the session
model turns into eval rows via the ``grounded-eval-synth`` skill. Candidates
are derivable scratch: written to /tmp by default, never tracked.

Usage:
    python3 scripts/grounded_eval/mine_candidates.py \
        [--manifest evidence/orionfold-advisor/public-corpus-manifest.jsonl] \
        [--root .] [--out /tmp/grounded-eval/candidates.jsonl] \
        [--journeys lookup,howto,troubleshoot,synthesis,refusal]
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path

JOURNEYS = ("lookup", "howto", "troubleshoot", "synthesis", "refusal")

_FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n", re.DOTALL)
_CODE_BLOCK_RE = re.compile(r"```([a-zA-Z]*)\n(.*?)```", re.DOTALL)
_TAGS_RE = re.compile(r"^tags:\s*\[(.*?)\]", re.MULTILINE)

# Measurement-shaped claims → lookup seeds.
_MEASURE_RE = re.compile(
    r"(\b\d[\d,.]*\s*(?:tok/s|tokens?/s|GB|MB|ms\b|%|×|x\b|hours?\b|minutes?\b|min\b|seconds?\b)"
    r"|\b\d+/\d+\b"
    r"|\b\d+(?:\.\d+)?[x×]\s*(?:faster|slower|speedup)?)",
    re.IGNORECASE,
)

# Gotcha-shaped sentences → troubleshoot seeds.
_GOTCHA_WORDS = (
    "trap", "gotcha", "symptom", "fails", "failed", "breaks", "broken",
    "crash", "wedge", "landmine", "orphan", "hang", "hung", "stale",
    "silently", "workaround", "the fix", "turns out", "oom",
    "out of memory", "won't", "doesn't work", "misleading", "false",
)

# Comparison vocabulary → single-source synthesis seeds.
_COMPARE_RE = re.compile(r"\b(vs\.?|versus|bakeoff|compared (?:to|with)|head-to-head)\b", re.IGNORECASE)

# Superseded markers → refusal (stale-content) seeds.
_SUPERSEDED_RE = re.compile(r"\b(superseded|retired|deprecated|historical|no longer)\b", re.IGNORECASE)

# Out-of-corpus probe topics (refusal seeds when ABSENT from the corpus
# vocabulary) — plausible operator asks the pack does not cover.
_PROBE_TOPICS = (
    "sagemaker", "kubernetes", "rocm", "mlx", "groq", "snowflake",
    "databricks", "bedrock", "raspberry", "sglang", "modal", "lambda labs",
    "runpod", "tpu", "cerebras", "windows",
)


def _strip_frontmatter(text: str) -> tuple[str, list[str]]:
    tags: list[str] = []
    m = _FRONTMATTER_RE.match(text)
    if m:
        tm = _TAGS_RE.search(m.group(1))
        if tm:
            tags = [t.strip().strip("'\"") for t in tm.group(1).split(",") if t.strip()]
        text = text[m.end():]
    return text, tags


def _prose(text: str) -> str:
    text = _CODE_BLOCK_RE.sub(" ", text)
    text = re.sub(r"`([^`]+)`", r"\1", text)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"[#*_>]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _sentences(prose: str) -> list[str]:
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", prose) if len(s.strip()) > 40]


def _load_sources(manifest_path: Path, root: Path) -> list[dict]:
    sources = []
    for line in manifest_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if not row.get("public_safe", False):
            continue
        path = root / str(row["path_or_url"])
        if not path.is_file():
            continue
        body = path.read_text(encoding="utf-8", errors="replace")
        stripped, tags = _strip_frontmatter(body)
        row["_body"] = stripped
        row["_tags"] = tags
        row["_prose"] = _prose(stripped)
        sources.append(row)
    return sources


def _mine_lookup(src: dict, cap: int) -> list[dict]:
    scored = []
    sents = _sentences(src["_prose"])
    for i, s in enumerate(sents):
        hits = _MEASURE_RE.findall(s)
        if not hits:
            continue
        ctx = " ".join(sents[max(0, i - 1): i + 2])
        scored.append((len(hits), {"sentence": s, "context": ctx[:1200]}))
    scored.sort(key=lambda t: -t[0])
    return [d for _, d in scored[:cap]]


def _mine_howto(src: dict, cap: int) -> list[dict]:
    out = []
    body = src["_body"]
    for m in _CODE_BLOCK_RE.finditer(body):
        lang, code = m.group(1).lower(), m.group(2).strip()
        if lang not in ("", "bash", "sh", "shell", "console") or len(code) < 20:
            continue
        lead = _prose(body[max(0, m.start() - 600): m.start()])[-400:]
        out.append({"command": code[:800], "lead": lead})
        if len(out) >= cap:
            break
    return out


def _mine_troubleshoot(src: dict, cap: int) -> list[dict]:
    scored = []
    sents = _sentences(src["_prose"])
    for i, s in enumerate(sents):
        low = s.lower()
        n = sum(1 for w in _GOTCHA_WORDS if w in low)
        if n == 0:
            continue
        ctx = " ".join(sents[max(0, i - 1): i + 3])
        scored.append((n, {"sentence": s, "context": ctx[:1500]}))
    scored.sort(key=lambda t: -t[0])
    return [d for _, d in scored[:cap]]


def _mine_synthesis_pairs(sources: list[dict], cap: int) -> list[dict]:
    notes = [s for s in sources if s.get("source_class") == "field_note" and s["_tags"]]
    freq = Counter(t for s in notes for t in set(s["_tags"]))
    common = {t for t, n in freq.items() if n > len(notes) * 0.3}
    pairs = []
    for i, a in enumerate(notes):
        for b in notes[i + 1:]:
            shared = (set(a["_tags"]) & set(b["_tags"])) - common
            if len(shared) >= 2:
                pairs.append((len(shared), sorted(shared), a, b))
    pairs.sort(key=lambda t: (-t[0], t[2]["source_id"], t[3]["source_id"]))
    out = []
    for _, shared, a, b in pairs[:cap]:
        out.append({
            "source_ids": [a["source_id"], b["source_id"]],
            "titles": [a["title"], b["title"]],
            "shared_tags": shared,
        })
    return out


def _mine_synthesis_single(src: dict, cap: int) -> list[dict]:
    out = []
    for s in _sentences(src["_prose"]):
        if _COMPARE_RE.search(s):
            out.append({"sentence": s[:600]})
            if len(out) >= cap:
                break
    return out


def _mine_refusal(sources: list[dict]) -> list[dict]:
    out = []
    for src in sources:
        marked = [s for s in _sentences(src["_prose"]) if _SUPERSEDED_RE.search(s)][:2]
        for s in marked:
            out.append({"kind": "superseded", "source_id": src["source_id"],
                        "title": src["title"], "sentence": s[:600]})
    vocab = set()
    for src in sources:
        vocab.update(re.findall(r"[a-z][a-z0-9-]{2,}", src["_prose"].lower()))
    for topic in _PROBE_TOPICS:
        if all(tok not in vocab for tok in topic.split()):
            out.append({"kind": "out_of_corpus", "topic": topic})
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--manifest", default="evidence/orionfold-advisor/public-corpus-manifest.jsonl")
    ap.add_argument("--root", default=".")
    ap.add_argument("--out", default="/tmp/grounded-eval/candidates.jsonl")
    ap.add_argument("--journeys", default=",".join(JOURNEYS))
    ap.add_argument("--max-per-source", type=int, default=3)
    args = ap.parse_args()

    root = Path(args.root).resolve()
    journeys = [j.strip() for j in args.journeys.split(",") if j.strip()]
    unknown = set(journeys) - set(JOURNEYS)
    if unknown:
        ap.error(f"unknown journeys: {sorted(unknown)}")

    sources = _load_sources(root / args.manifest, root)
    cap = args.max_per_source
    rows: list[dict] = []

    per_source = {
        "lookup": _mine_lookup,
        "howto": _mine_howto,
        "troubleshoot": _mine_troubleshoot,
    }
    for journey, fn in per_source.items():
        if journey not in journeys:
            continue
        for src in sources:
            for d in fn(src, cap):
                d.update(journey=journey, source_id=src["source_id"], title=src["title"])
                rows.append(d)

    if "synthesis" in journeys:
        for d in _mine_synthesis_pairs(sources, cap=40):
            d["journey"] = "synthesis"
            rows.append(d)
        for src in sources:
            for d in _mine_synthesis_single(src, cap=1):
                d.update(journey="synthesis", source_id=src["source_id"], title=src["title"])
                rows.append(d)

    if "refusal" in journeys:
        for d in _mine_refusal(sources):
            d["journey"] = "refusal"
            rows.append(d)

    for i, d in enumerate(rows):
        d["cid"] = f"cand-{d['journey']}-{i:04d}"

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as f:
        for d in rows:
            f.write(json.dumps(d, ensure_ascii=False) + "\n")

    counts = Counter(d["journey"] for d in rows)
    print(f"sources read: {len(sources)}")
    for j in JOURNEYS:
        if j in journeys:
            print(f"  {j}: {counts.get(j, 0)} candidates")
    print(f"wrote {len(rows)} → {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
