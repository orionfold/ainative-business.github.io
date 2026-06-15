#!/usr/bin/env python3
# Copyright 2026 Manav Sehgal
# SPDX-License-Identifier: Apache-2.0
"""Freeze the Advisor demo corpus into a vendored, self-contained pack.

AD-FK-β: a fresh Field Edition box boots an EMPTY pgvector, so the §8 Cortex
gate can't pass until the Advisor demo corpus is ingested. `up` has no repo
checkout to read the 182 public sources from, so we vendor a **self-contained
pack** in the wheel: for each source, the already-`_strip_markup`'d body + the
provenance metadata prefix line, exactly as `score_recall_live.ingest_corpus`
computes them. `fieldkit.field_edition.ingest` then chunks→embeds→upserts the
pack offline into `advisor_corpus_v01` — reproducing the chunks the recall@5
0.977 proof was measured against (no network, ~1 MB gzipped in the wheel).

Decision (operator, 2026-06-15): **wheel-vendored** over HF/GitHub — the
bootstrap already pulls the fieldkit wheel, so the pack rides along with zero
extra fetches, zero auth, fully offline (AC-2), matching the existing frozen
`data/*.json` sets. The 2.6 GB GGUF is pulled from HF precisely because it is
too big to vendor; the ~1 MB corpus is the opposite case.

The pack is a **deliberate frozen snapshot**, NOT a live mirror of the repo:
several corpus sources (the fieldkit CHANGELOG, the docs/api pages) churn every
release, and one — `doc_fieldkit_changelog_md` — is even a gold source for a
recall probe, so it cannot be excluded. A re-freeze is therefore a deliberate
act gated on re-running EVERY bench (proof-control discipline), not something the
repo's day-to-day churn forces. Accordingly:

    python3 scripts/field_edition/build_advisor_corpus_pack.py          # RE-FREEZE
    python3 scripts/field_edition/build_advisor_corpus_pack.py --check  # validate artifact

``--check`` validates the **shipped artifact** (decompresses, parses, and asserts
its content sha matches the runtime pin `fieldkit.field_edition.ingest.CORPUS_PACK_SHA`)
— it does NOT re-derive from the churning repo (that would "drift" on every
unrelated doc edit). Re-freeze only when you intend to refresh the demo corpus;
the printed sha then goes into `CORPUS_PACK_SHA` and every bench is re-run.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
MANIFEST_PATH = REPO_ROOT / "evidence" / "orionfold-advisor" / "public-corpus-manifest.jsonl"
PACK_PATH = (
    REPO_ROOT
    / "fieldkit"
    / "src"
    / "fieldkit"
    / "field_edition"
    / "data"
    / "advisor-corpus-pack-v01.jsonl.gz"
)
NAME = "advisor-corpus-pack"
VERSION = "v01"
CORPUS_TABLE = "advisor_corpus_v01"

# The provenance-prefix keys — verbatim from score_recall_live._metadata_line so
# the vendored chunks match the proof's chunks byte-for-byte.
_META_KEYS = (
    "source_id",
    "path_or_url",
    "source_class",
    "source_role",
    "book_surface",
    "citation_label",
    "title",
    "slug",
    "artifact_slug",
    "product_slug",
    "chapter_id",
)


def _metadata_line(source: dict[str, Any]) -> str:
    return " ".join(str(source.get(k) or "") for k in _META_KEYS).strip()


def _strip_markup(text: str) -> str:
    # Verbatim from scripts/orionfold_advisor/score_recall.py — the exact body
    # text the recall proof ingested.
    text = re.sub(r"^---\n.*?\n---\n", " ", text, flags=re.DOTALL)
    text = re.sub(r"```.*?```", " ", text, flags=re.DOTALL)
    text = re.sub(r"`([^`]+)`", r"\1", text)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\{[^{}]*\}", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _read_manifest() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in MANIFEST_PATH.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def build_pack() -> dict[str, Any]:
    manifest = _read_manifest()
    sources: list[dict[str, Any]] = []
    for src in manifest:
        path = REPO_ROOT / src["path_or_url"]
        if not path.exists():
            raise FileNotFoundError(f"manifest path missing: {src['path_or_url']}")
        body = _strip_markup(path.read_text(encoding="utf-8", errors="replace"))
        sources.append(
            {
                "source_id": str(src["source_id"]),
                "meta": _metadata_line(src),
                "body": body,
                "source_class": str(src["source_class"]),
                "date_or_version": str(src.get("date_or_version") or ""),
                "path_or_url": str(src["path_or_url"]),
            }
        )
    return {
        "name": NAME,
        "version": VERSION,
        "corpus_table": CORPUS_TABLE,
        "source_manifest_sha256_12": hashlib.sha256(MANIFEST_PATH.read_bytes()).hexdigest()[:12],
        "n_sources": len(sources),
        "sources": sources,
    }


def canonical_payload(pack: dict[str, Any]) -> bytes:
    """The deterministic decompressed payload the sha pins (gzip headers vary,
    so we pin the *content*, not the compressed bytes)."""
    return json.dumps(pack, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )


def payload_sha(pack: dict[str, Any]) -> str:
    return hashlib.sha256(canonical_payload(pack)).hexdigest()[:12]


def _runtime_pin() -> str | None:
    """The sha the wheel runtime pins (so ``--check`` validates against the same
    constant the loader enforces). ``None`` if fieldkit isn't importable."""
    try:
        from fieldkit.field_edition.ingest import CORPUS_PACK_SHA
    except Exception:  # noqa: BLE001 — builder may run without fieldkit installed
        return None
    return CORPUS_PACK_SHA


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--check",
        action="store_true",
        help="validate the shipped artifact (decompress + parse + sha == runtime pin)",
    )
    args = ap.parse_args()

    if args.check:
        if not PACK_PATH.exists():
            print(f"FAIL: {PACK_PATH} does not exist — re-freeze first", file=sys.stderr)
            sys.exit(1)
        raw = gzip.decompress(PACK_PATH.read_bytes())
        disk_sha = hashlib.sha256(raw).hexdigest()[:12]
        doc = json.loads(raw)  # parses → well-formed
        n = len(doc.get("sources", []))
        pin = _runtime_pin()
        print(f"artifact content sha: {disk_sha}  ({n} sources)")
        if pin is None:
            print("(fieldkit not importable — sha printed, pin not checked)")
            sys.exit(0)
        ok = disk_sha == pin
        print(f"runtime CORPUS_PACK_SHA: {pin}")
        print("OK artifact matches the runtime pin" if ok else "FAIL: artifact ≠ pin — re-pin")
        sys.exit(0 if ok else 1)

    # Re-freeze: rebuild from the live repo + write. mtime=0 → reproducible gzip.
    pack = build_pack()
    payload = canonical_payload(pack)
    sha = payload_sha(pack)
    PACK_PATH.parent.mkdir(parents=True, exist_ok=True)
    PACK_PATH.write_bytes(gzip.compress(payload, compresslevel=9, mtime=0))
    print(f"wrote {PACK_PATH.relative_to(REPO_ROOT)}")
    print(f"  sources: {pack['n_sources']}")
    print(f"  on-disk: {PACK_PATH.stat().st_size / 1024:.0f} KB gz")
    print(f"  CORPUS_PACK_SHA = {sha!r}  (re-pin in fieldkit.field_edition.ingest + re-run all benches)")


if __name__ == "__main__":
    main()
