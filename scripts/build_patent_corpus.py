#!/usr/bin/env python3
# Copyright 2026 Manav Sehgal
# SPDX-License-Identifier: Apache-2.0
"""Build the patent-strategist raw corpus on disk.

Per `_SPECS/patent-strategist-v1.md` §3.2 + §6: pulls commercial-safe patent
sources to `/home/nvidia/data/corpus/patent/<source>/*.jsonl` and writes a
provenance snapshot at `evidence/patent-strategist/corpus-snapshot.json`
that the R10 (license-drift) mitigation hangs on.

Sources (spec §6.1):

    | source       | license      | role                        | tier |
    | ------------ | ------------ | --------------------------- | ---- |
    | bigpatent    | CC-BY-4.0    | Family A drafting / style   | 1    |
    | patentmatch  | (see notes)  | Family B analytical primary | 1    |
    | mpep         | public dom.  | Family D anchor + RAG       | 2    |
    | oa           | public dom.  | Family D procedural primary | 3    |
    | gpat         | CC-BY-4.0    | Family C landscape          | 3    |

Tier 1 sources pull cleanly from HuggingFace (anonymous). Tier 2 (MPEP)
needs an HTTP scraper. Tier 3 (USPTO OARD + Google Patents BigQuery) needs
external auth (USPTO data portal + gcloud). Tier 1 runs by default; tier 2
runs when `--sources` includes ``mpep``; tier 3 sources are scaffolded but
write a stub snapshot entry with ``status: blocked`` so downstream tasks
can plan around the gap.

Spec drift note: the spec lists ``pakuvis/PatentMatch`` for the PatentMatch
pull, but that HF repo returns 404. ``BNNT/PatentMatch`` (Apache-2.0,
English+Chinese JSON) is the closest available substitute; we pull the
English half and flag the substitution in the snapshot. The canonical
HPI-Naumann PatentMatch lives at https://hpi.de/naumann/s/patentmatch but
distributes via direct download, not HF — wire that in once the dataset
shape is confirmed.

Usage::

    python scripts/build_patent_corpus.py                       # all default-enabled
    python scripts/build_patent_corpus.py --sources bigpatent   # one source
    python scripts/build_patent_corpus.py --max-per-source 2000 # cap rows
    python scripts/build_patent_corpus.py --force               # overwrite existing JSONLs

The script is idempotent: existing per-source output dirs are skipped
unless ``--force`` is passed. Snapshot is rewritten on every run.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUT = Path("/home/nvidia/data/corpus/patent")
SNAPSHOT_PATH = REPO_ROOT / "evidence" / "patent-strategist" / "corpus-snapshot.json"

# `~/.cache/huggingface/hub/` is root-owned on this Spark (artifact of an
# earlier container-run download). Redirect cache to user-writable space.
# Skip if caller has already set HF_HOME explicitly.
os.environ.setdefault("HF_HOME", "/home/nvidia/data/.hf-cache")
os.environ.setdefault("HF_HUB_CACHE", "/home/nvidia/data/.hf-cache/hub")

ALL_SOURCES = ("bigpatent", "patentmatch", "mpep", "oa", "gpat")
DEFAULT_SOURCES = ("bigpatent", "patentmatch", "mpep")
TIER3_SOURCES = ("oa", "gpat")


@dataclass
class SourceResult:
    name: str
    status: str  # "pulled" | "pending" | "blocked" | "skipped"
    hf_repo: str | None = None
    commit_sha: str | None = None
    license: str | None = None
    rows: int = 0
    files: list[str] = field(default_factory=list)
    notes: str = ""


# --- BIGPATENT (Tier 1) -----------------------------------------------------


def pull_bigpatent(out_dir: Path, max_rows: int | None) -> SourceResult:
    """Pull BIGPATENT abstracts from HF `big_patent`.

    Pulls IPC configs `g` (physics) + `h` (electricity) — the two most
    relevant for the tech-leaning patent-strategist scope. Caps at
    `max_rows` per config to keep the working corpus manageable; spec mix
    only needs ~2,500 examples downstream so the cap can be aggressive.
    """
    from datasets import load_dataset  # type: ignore[import-not-found]
    from huggingface_hub import HfApi  # type: ignore[import-not-found]

    repo_id = "big_patent"
    sha = HfApi().dataset_info(repo_id).sha
    out_dir.mkdir(parents=True, exist_ok=True)

    total = 0
    files: list[str] = []
    for cfg in ("g", "h"):
        path = out_dir / f"bigpatent-{cfg}-train.jsonl"
        ds = load_dataset(repo_id, cfg, split="train", streaming=True)
        with path.open("w") as f:
            for i, row in enumerate(ds):
                if max_rows is not None and i >= max_rows:
                    break
                f.write(
                    json.dumps(
                        {
                            "patent_number": row.get("patent_number"),
                            "ipc_class": cfg,
                            "description": row.get("description", "")[:8000],
                            "abstract": row.get("abstract", ""),
                        }
                    )
                    + "\n"
                )
                total += 1
        files.append(path.name)
        print(f"  bigpatent[{cfg}] → {path.name}: {total} rows so far", flush=True)
    return SourceResult(
        name="bigpatent",
        status="pulled",
        hf_repo=repo_id,
        commit_sha=sha,
        license="CC-BY-4.0",
        rows=total,
        files=files,
        notes="configs g+h (physics+electricity); abstracts capped to 8k chars",
    )


# --- PatentMatch (canonical HPI-Naumann via HiDrive share) -----------------


PMATCH_HIDRIVE_SHARE = "rwfam92omy"
PMATCH_HIDRIVE_API = "https://my.hidrive.com/api"
# Spec §6.1's canonical PatentMatch from HPI-Naumann (Risch et al. 2021)
# is hosted at https://hpi.de/naumann/s/patentmatch, which redirects to
# the HiDrive share above. The share contains 8 zips spanning full +
# balanced + ultra-balanced × {train, test} × {flat, DPR-format}. The
# ultra-balanced flat zips are the highest-signal subset (one X and one
# A per claim, 25,340 rows total) — large enough to dominate Family B
# corpus weight, small enough to embed in seconds. The full 1.4 GB
# `patentmatch_train.zip` (6.26M rows) would 99%-overlap retrieval cells
# for our 200-question bench and lengthen embed time without lifting
# retrieval quality, so we skip it for v1.0.
PMATCH_FILES = ("patentmatch_train_ultrabalanced.zip", "patentmatch_test_ultrabalanced.zip")


def _hidrive_token(share_id: str) -> str:
    """POST a share-id to HiDrive's public share-token endpoint, get a
    4-hour Bearer token. No login required; token scopes to the share."""
    import requests  # type: ignore[import-not-found]

    r = requests.post(
        f"{PMATCH_HIDRIVE_API}/share/token",
        data={"id": share_id},
        timeout=30,
    )
    r.raise_for_status()
    return r.json()["access_token"]


def pull_patentmatch(out_dir: Path, max_rows: int | None) -> SourceResult:
    """Pull canonical HPI-Naumann PatentMatch ultra-balanced split.

    Replaces session-19's `BNNT/PatentMatch` 500-row substitute. The
    canonical pairs are labeled by EPO patent examiners — `label=1`
    rows are "X" documents (particularly relevant to claim's novelty
    /inventive step); `label=0` rows are "A" documents (general
    background, non-prejudicial). Ultra-balanced means exactly one X
    and one A per claim — 25,340 rows total (20,272 train + 5,068 test).

    Schema per row (matches the source TSV):

        {
          "claim_id": str,           # e.g. "44939_1"
          "patent_application_id": str,  # EPO application, e.g. "EP2551115A1"
          "cited_document_id": str,  # cited prior art, e.g. "EP2105306"
          "claim_text": str,         # claim from the application
          "cited_text": str,         # paragraph from the cited document
          "label": int,              # 1 = X (relevant), 0 = A (background)
          "label_letter": "X"|"A",   # convenience for prompt rendering
          "date": str,               # decision date YYYYMMDD
          "split": "train"|"test",   # source split (test is held-out)
        }

    Source paper: Risch et al. 2021, "PatentMatch: A Dataset for Matching
    Patent Claims & Prior Art" (PatentSemTech@SIGIR 2021). License: MIT
    per the project GitHub repo (github.com/julian-risch/PatentMatch).
    """
    import csv
    import io
    import zipfile

    import requests  # type: ignore[import-not-found]

    out_dir.mkdir(parents=True, exist_ok=True)
    raw_dir = out_dir / "_raw"
    raw_dir.mkdir(exist_ok=True)

    token = _hidrive_token(PMATCH_HIDRIVE_SHARE)

    rows: list[dict] = []
    splits_pulled: dict[str, int] = {}
    for filename in PMATCH_FILES:
        split = "train" if "train" in filename else "test"
        zip_path = raw_dir / filename
        if not zip_path.exists():
            url = (
                f"{PMATCH_HIDRIVE_API}/file?attachment=true"
                f"&path=/{filename}&access_token={token}"
            )
            print(f"  patentmatch GET {filename} ...", flush=True)
            r = requests.get(url, timeout=300, stream=True)
            r.raise_for_status()
            with zip_path.open("wb") as f:
                for chunk in r.iter_content(chunk_size=1 << 16):
                    f.write(chunk)

        with zipfile.ZipFile(zip_path) as z:
            tsv_name = z.namelist()[0]
            with z.open(tsv_name) as f:
                text = io.TextIOWrapper(f, encoding="utf-8", errors="replace")
                reader = csv.DictReader(text, delimiter="\t")
                for r_in in reader:
                    label_int = int(r_in["label"])
                    rows.append({
                        "claim_id": r_in["claim_id"],
                        "patent_application_id": r_in["patent_application_id"],
                        "cited_document_id": r_in["cited_document_id"],
                        "claim_text": r_in["text"],
                        "cited_text": r_in["text_b"],
                        "label": label_int,
                        "label_letter": "X" if label_int == 1 else "A",
                        "date": r_in["date"],
                        "split": split,
                    })
                    if max_rows is not None and len(rows) >= max_rows:
                        break
            splits_pulled[split] = sum(1 for x in rows if x["split"] == split)
        if max_rows is not None and len(rows) >= max_rows:
            break

    # Drop the BNNT substitute JSONL if present (session-19 artifact).
    legacy = out_dir / "patentmatch-en.jsonl"
    if legacy.exists():
        legacy.unlink()

    out_path = out_dir / "patentmatch-ultrabalanced.jsonl"
    with out_path.open("w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")

    return SourceResult(
        name="patentmatch",
        status="pulled",
        hf_repo=None,
        commit_sha=None,  # HiDrive share lacks a versioning anchor; mtime in raw cache
        license="MIT (github.com/julian-risch/PatentMatch)",
        rows=len(rows),
        files=[out_path.name],
        notes=(
            f"CANONICAL HPI-Naumann PatentMatch ultra-balanced "
            f"(Risch et al. 2021). Pulled via HiDrive share {PMATCH_HIDRIVE_SHARE}; "
            f"splits: {splits_pulled}. One X and one A per claim — Family B "
            f"primary corpus. Full 6.26M-row variant skipped for v1.0 (overkill "
            f"vs 200-Q bench). Replaces session-19's BNNT/PatentMatch 500-row "
            f"substitute (deleted from this dir on re-pull)."
        ),
    )


# --- MPEP (Tier 2) ----------------------------------------------------------


MPEP_BASE = "https://www.uspto.gov/web/offices/pac/mpep"
# Session-19's stub flagged "JS-rendered" — that was the eMPEP RDMS
# chrome at https://mpep.uspto.gov/RDMS/MPEP/current, which hash-routes
# section content via XHR. The static HTML mirror at uspto.gov/web/.../mpep
# serves chapter TOCs (mpep-0XXX.html) and per-section pages (s<NNN>.html)
# directly — no JS required. Switch confirmed 2026-05-17 in session 20.
#
# MPEP standard ninth-edition chapters are 100..2900 in 100-step increments.
# Chapter 1700 is reserved (USPTO skipped that band); the puller probes the
# TOC URL and skips on 404. The "current" alias resolves to E9_R-01.2024
# (November 2024 publication of January 2024 revision).
MPEP_CHAPTERS = [f"{n:04d}" for n in range(100, 3000, 100)]

_MPEP_FETCH_DELAY_S = 0.5  # polite throttle for federal site


def _http_get(url: str, timeout: int = 30) -> str | None:
    """Fetch a URL and return text body, or None on 404/timeout.

    Lazy-import requests to keep the rest of the puller drier — non-MPEP
    sources don't need it.
    """
    import requests  # type: ignore[import-not-found]

    try:
        r = requests.get(url, timeout=timeout, headers={"User-Agent": "ai-field-notes patent-strategist corpus puller (sehgal.manav@gmail.com)"})
    except requests.RequestException as exc:
        print(f"  WARN: GET {url} failed: {exc}", file=sys.stderr)
        return None
    if r.status_code == 404:
        return None
    if not r.ok:
        print(f"  WARN: GET {url} → HTTP {r.status_code}", file=sys.stderr)
        return None
    return r.text


def _mpep_extract_subsections(section_html: str, section_id: str, chapter: str) -> Iterator[dict]:
    """Walk a section page's `h1.page-title` headings in document order.

    Each heading anchors a subsection (e.g. "704.01 Search"). Content
    between consecutive headings comes from `<p>` and `<li>` descendants;
    info-class `<div>` tags carry MPEP examiner notes and are kept too.
    The first h1 on the page is the section banner itself (`704 Search
    and Requirements for Information`) and has no body content; we still
    emit it so downstream tools can attach metadata to it if needed.
    """
    from bs4 import BeautifulSoup  # type: ignore[import-not-found]

    soup = BeautifulSoup(section_html, "lxml")
    heads = soup.select("h1.page-title")
    for i, h in enumerate(heads):
        title = h.get_text(" ", strip=True)
        anchor = h.get("id")  # None for the section banner h1
        nxt = heads[i + 1] if i + 1 < len(heads) else None
        text_parts: list[str] = []
        el = h
        while True:
            el = el.find_next()
            if el is None or el is nxt:
                break
            if el.name in ("p", "li"):
                t = el.get_text(" ", strip=True)
                if t:
                    text_parts.append(t)
            elif el.name == "div" and "info" in (el.get("class") or []):
                t = el.get_text(" ", strip=True)
                if t:
                    text_parts.append(t)
        text = " ".join(text_parts).strip()
        # Strip the trailing `&nbsp;` placeholder h1s at the bottom of
        # each section (they wrap the chapter-TOC nav widget; not real
        # examiner content). Real subsection titles start with a digit
        # (e.g. `701`, `704.10`, `2106(a)(1)`).
        title_clean = title.replace("\xa0", " ").strip()
        if not title_clean or not title_clean[0].isdigit():
            continue
        if not text:
            # Section banner h1 with no body (the subsection h1s carry
            # the actual content). Emit anyway so callers can attach
            # section-level metadata; chunker will skip zero-text rows.
            pass
        yield {
            "chapter": chapter,
            "section_id": section_id,
            "anchor": anchor,
            "title": title,
            "text": text,
            "url": f"{MPEP_BASE}/{section_id}.html" + (f"#{anchor}" if anchor else ""),
        }


def pull_mpep(out_dir: Path, max_rows: int | None) -> SourceResult:
    """Pull MPEP per-subsection text from the USPTO static HTML mirror.

    Discovery: iterate `mpep-0XXX.html` chapter TOCs for X in 100..2900,
    parse out `s<NNN>.html` section filenames. For each section, parse
    `h1.page-title` boundaries to emit one JSONL row per subsection.

    Caches raw chapter + section HTML at `<out_dir>/_raw/` so re-extraction
    after a chunking-rule tweak is free. Polite 0.5s throttle between
    requests — public USPTO infra, not rate-limited but we behave anyway.

    The `max_rows` cap applies to the per-chapter row count, not the
    section count — useful for smoke runs.
    """
    raw_dir = out_dir / "_raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    out_dir.mkdir(parents=True, exist_ok=True)

    total_rows = 0
    written_files: list[str] = []
    chapters_skipped: list[str] = []

    for chapter in MPEP_CHAPTERS:
        toc_url = f"{MPEP_BASE}/mpep-{chapter}.html"
        toc_cache = raw_dir / f"mpep-{chapter}.html"
        if toc_cache.exists():
            toc_html = toc_cache.read_text()
        else:
            toc_html = _http_get(toc_url)
            time.sleep(_MPEP_FETCH_DELAY_S)
            if toc_html is None:
                chapters_skipped.append(chapter)
                continue
            toc_cache.write_text(toc_html)

        import re

        section_ids = sorted({m for m in re.findall(r"s\d+\.html", toc_html)})
        # Strip ".html"
        section_ids = [s[:-5] for s in section_ids]
        if not section_ids:
            chapters_skipped.append(chapter)
            continue

        chapter_rows: list[dict] = []
        per_chapter_raw = raw_dir / chapter
        per_chapter_raw.mkdir(exist_ok=True)
        for sid in section_ids:
            sec_url = f"{MPEP_BASE}/{sid}.html"
            sec_cache = per_chapter_raw / f"{sid}.html"
            if sec_cache.exists():
                sec_html = sec_cache.read_text()
            else:
                sec_html = _http_get(sec_url)
                time.sleep(_MPEP_FETCH_DELAY_S)
                if sec_html is None:
                    continue
                sec_cache.write_text(sec_html)
            for row in _mpep_extract_subsections(sec_html, sid, chapter):
                chapter_rows.append(row)
                if max_rows is not None and len(chapter_rows) >= max_rows:
                    break
            if max_rows is not None and len(chapter_rows) >= max_rows:
                break

        if not chapter_rows:
            chapters_skipped.append(chapter)
            continue

        path = out_dir / f"mpep-{chapter}.jsonl"
        with path.open("w") as f:
            for row in chapter_rows:
                f.write(json.dumps(row) + "\n")
        written_files.append(path.name)
        total_rows += len(chapter_rows)
        print(
            f"  mpep[{chapter}] → {path.name}: {len(chapter_rows)} subsections "
            f"({len(section_ids)} sections); cumulative {total_rows}",
            flush=True,
        )

    notes = (
        f"USPTO static-HTML mirror at {MPEP_BASE}; chapters scraped per "
        f"mpep-0XXX.html TOC + per-section h1.page-title boundaries. "
        f"Skipped (404 or empty): {','.join(chapters_skipped) or 'none'}. "
        f"Raw HTML cached under _raw/ for re-extraction without re-fetch."
    )
    return SourceResult(
        name="mpep",
        status="pulled" if total_rows else "pending",
        hf_repo=None,
        commit_sha=None,
        license="public-domain (17 USC §105)",
        rows=total_rows,
        files=written_files,
        notes=notes,
    )


# --- USPTO OARD (Tier 3) ----------------------------------------------------


def pull_oa(out_dir: Path, max_rows: int | None) -> SourceResult:
    return SourceResult(
        name="oa",
        status="blocked",
        license="public-domain (17 USC §105)",
        notes=(
            "USPTO Office Action Research Dataset (4.4M actions 2008-2017). "
            "Download via USPTO data portal (https://www.uspto.gov/ip-policy/"
            "economic-research/research-datasets/) — needs portal account + "
            "bulk file fetch (CSV/Stata, multi-GB). Wire in W1-late."
        ),
    )


# --- Google Patents BigQuery (Tier 3) --------------------------------------


def pull_gpat(out_dir: Path, max_rows: int | None) -> SourceResult:
    return SourceResult(
        name="gpat",
        status="blocked",
        license="CC-BY-4.0",
        notes=(
            "Google Patents Public Data BigQuery dataset (patents-public-data). "
            "Needs gcloud auth + google-cloud-bigquery + a US-only IPC-class "
            "filtered query (Family C landscape work). Wire in W2 alongside "
            "the RAG index build."
        ),
    )


# --- Dispatch ---------------------------------------------------------------


PULLERS: dict[str, Callable[[Path, int | None], SourceResult]] = {
    "bigpatent": pull_bigpatent,
    "patentmatch": pull_patentmatch,
    "mpep": pull_mpep,
    "oa": pull_oa,
    "gpat": pull_gpat,
}


def _iter_existing(path: Path) -> Iterator[Path]:
    if path.exists():
        yield from path.glob("*.jsonl")


def _build_snapshot(results: list[SourceResult]) -> dict[str, Any]:
    """Merge new pull results into the existing snapshot.

    Sources NOT touched this run keep their prior commit_sha / row counts —
    selective re-pulls (e.g. `--sources mpep`) don't wipe bigpatent
    provenance. Sources covered in this run overwrite their entries.
    """
    existing: dict[str, Any] = {}
    if SNAPSHOT_PATH.exists():
        try:
            existing = json.loads(SNAPSHOT_PATH.read_text())
        except json.JSONDecodeError:
            existing = {}
    sources = dict(existing.get("sources", {}))
    for r in results:
        sources[r.name] = {
            "status": r.status,
            "hf_repo": r.hf_repo,
            "commit_sha": r.commit_sha,
            "license": r.license,
            "rows": r.rows,
            "files": r.files,
            "notes": r.notes,
        }
    return {
        "pulled_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "spec_ref": "_SPECS/patent-strategist-v1.md §6",
        "sources": sources,
    }


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument(
        "--sources",
        default=",".join(DEFAULT_SOURCES),
        help=f"Comma-separated source names. Available: {','.join(ALL_SOURCES)}. "
        f"Default: {','.join(DEFAULT_SOURCES)}.",
    )
    p.add_argument(
        "--out-dir",
        type=Path,
        default=DEFAULT_OUT,
        help=f"Output root. Default: {DEFAULT_OUT}",
    )
    p.add_argument(
        "--max-per-source",
        type=int,
        default=5000,
        help="Row cap per source/config. Default: 5000.",
    )
    p.add_argument(
        "--force",
        action="store_true",
        help="Overwrite per-source dirs that already have JSONLs.",
    )
    args = p.parse_args()

    requested = [s.strip() for s in args.sources.split(",") if s.strip()]
    unknown = [s for s in requested if s not in PULLERS]
    if unknown:
        print(f"FATAL: unknown sources: {unknown}", file=sys.stderr)
        return 2

    results: list[SourceResult] = []
    for src in requested:
        src_dir = args.out_dir / src
        existing = list(_iter_existing(src_dir))
        if existing and not args.force:
            print(f"[{src}] SKIP — {len(existing)} JSONLs already present (use --force to overwrite)")
            results.append(
                SourceResult(
                    name=src,
                    status="skipped",
                    rows=sum(1 for f in existing for _ in f.open()),
                    files=[f.name for f in existing],
                    notes="existing artifacts kept; pass --force to rebuild",
                )
            )
            continue
        print(f"[{src}] PULL → {src_dir}/", flush=True)
        try:
            results.append(PULLERS[src](src_dir, args.max_per_source))
        except Exception as exc:  # noqa: BLE001
            print(f"[{src}] FAIL: {type(exc).__name__}: {exc}", file=sys.stderr)
            results.append(
                SourceResult(
                    name=src,
                    status="blocked",
                    notes=f"pull failed: {type(exc).__name__}: {exc}",
                )
            )

    SNAPSHOT_PATH.parent.mkdir(parents=True, exist_ok=True)
    snap = _build_snapshot(results)
    SNAPSHOT_PATH.write_text(json.dumps(snap, indent=2) + "\n")
    print(f"\nSNAPSHOT → {SNAPSHOT_PATH}")
    for r in results:
        print(f"  {r.name:12s} {r.status:8s} rows={r.rows:>7d} {r.notes[:80]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
