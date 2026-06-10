#!/usr/bin/env python3
# Copyright 2026 Manav Sehgal
# SPDX-License-Identifier: Apache-2.0
"""Generate v0.1 Orionfold Advisor proof-start evidence.

This is the non-GPU start of `_SPECS/orionfold-advisor-unsloth-arena-v1.md`:
domain gate, public corpus manifest, source audit, and a frozen source-mapped
bench seed. It intentionally does not create SFT rows. Training rows come only
after the public boundary and held-out slices are frozen.

Usage:

    python3 scripts/orionfold_advisor/generate.py
    python3 scripts/orionfold_advisor/generate.py --validate-only
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = REPO_ROOT / "evidence" / "orionfold-advisor"
VERSION = "v0.1"

PRIVATE_PATH_PREFIXES = (
    ".claude/",
    ".codex/",
    ".env",
    ".git/",
    ".agents/",
    "HANDOFF.md",
    "CODEX-CC.md",
    "CLAUDE.md",
    "_STATUS.json",
    "src/data/arena-mirror/",
)

EXCLUDED_SPEC_BASENAMES = {
    "orionfold-advisor-unsloth-arena-v1.md",
    "orionfold-advisor-dogfood-v1.md",
    # 2026-06-09: the active Advisor proof-control spec defines this bench, its
    # gates, and the 0082 erratum — leaving it retrievable put the bench's own
    # design text into eval context (2 router false escalations, a T4 quality
    # regression). The Workbench spec stays: it is a product spec, not
    # proof-control.
    "orionfold-advisor-nvidia-native-v1.md",
}


@dataclass(frozen=True)
class Source:
    source_id: str
    path_or_url: str
    source_class: str
    trust_tier: str
    public_safe: bool
    date_or_version: str
    citation_label: str
    title: str
    source_role: str
    slug: str | None = None
    status: str | None = None
    artifact_slug: str | None = None
    product_slug: str | None = None
    chapter_id: str | None = None
    book_surface: str | None = None

    def to_json(self) -> dict[str, Any]:
        row = {
            "source_id": self.source_id,
            "path_or_url": self.path_or_url,
            "source_class": self.source_class,
            "trust_tier": self.trust_tier,
            "public_safe": self.public_safe,
            "date_or_version": self.date_or_version,
            "citation_label": self.citation_label,
            "title": self.title,
            "source_role": self.source_role,
        }
        for key in ("slug", "status", "artifact_slug", "product_slug", "chapter_id", "book_surface"):
            value = getattr(self, key)
            if value:
                row[key] = value
        row["sha256_12"] = _sha256_12(REPO_ROOT / self.path_or_url)
        return row


def _rel(path: Path) -> str:
    return path.relative_to(REPO_ROOT).as_posix()


def _slugify(value: str) -> str:
    value = value.strip().lower()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    return value.strip("-") or "source"


def _sha256_12(path: Path) -> str:
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    return digest[:12]


def _frontmatter(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        return {}
    end = text.find("\n---", 4)
    if end == -1:
        return {}
    data: dict[str, Any] = {}
    for raw in text[4:end].splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or ":" not in line:
            continue
        key, value = line.split(":", 1)
        value = value.strip().strip('"').strip("'")
        data[key.strip()] = value
    return data


def _source_title(path: Path, fallback: str | None = None) -> str:
    fm = _frontmatter(path)
    if fm.get("title"):
        return str(fm["title"])
    text = path.read_text(encoding="utf-8")
    match = re.search(r"^#\s+(.+)$", text, flags=re.MULTILINE)
    if match:
        return match.group(1).strip()
    match = re.search(r"<(?:ApiDocsLayout|DocsLayout)\s+[^>]*title=\"([^\"]+)\"", text)
    if match:
        return match.group(1).strip()
    return fallback or path.stem


def _yaml_scalar(path: Path, key: str) -> str | None:
    prefix = f"{key}:"
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if line.startswith(prefix):
            return line[len(prefix):].strip().strip('"').strip("'")
    return None


def _add_source(sources: list[Source], source: Source) -> None:
    if any(source.source_id == existing.source_id for existing in sources):
        raise ValueError(f"duplicate source_id: {source.source_id}")
    sources.append(source)


def collect_sources() -> tuple[list[Source], dict[str, Any]]:
    sources: list[Source] = []
    excluded: list[dict[str, str]] = []

    for path in sorted((REPO_ROOT / "articles").glob("*/article.md")):
        fm = _frontmatter(path)
        status = str(fm.get("status") or "published")
        if status != "published":
            excluded.append({"path": _rel(path), "reason": f"article status is {status}"})
            continue
        slug = path.parent.name
        _add_source(
            sources,
            Source(
                source_id=f"article_{slug.replace('-', '_')}",
                path_or_url=_rel(path),
                source_class="field_note",
                trust_tier="published_orionfold",
                public_safe=True,
                date_or_version=str(fm.get("date") or "undated"),
                citation_label=f"Field Note: {fm.get('title') or slug}",
                title=str(fm.get("title") or slug),
                source_role="book2_field_note",
                slug=slug,
                status=status,
                book_surface="ai_research_on_nvidia_dgx_spark",
            ),
        )

    for path in sorted((REPO_ROOT / "articles").glob("*/article.mdx")):
        fm = _frontmatter(path)
        status = str(fm.get("status") or "published")
        if status != "published":
            excluded.append({"path": _rel(path), "reason": f"article status is {status}"})
            continue
        slug = path.parent.name
        _add_source(
            sources,
            Source(
                source_id=f"article_{slug.replace('-', '_')}",
                path_or_url=_rel(path),
                source_class="field_note",
                trust_tier="published_orionfold",
                public_safe=True,
                date_or_version=str(fm.get("date") or "undated"),
                citation_label=f"Field Note: {fm.get('title') or slug}",
                title=str(fm.get("title") or slug),
                source_role="book2_field_note",
                slug=slug,
                status=status,
                book_surface="ai_research_on_nvidia_dgx_spark",
            ),
        )

    for path in sorted((REPO_ROOT / "products").glob("*/product.md")):
        fm = _frontmatter(path)
        status = str(fm.get("status") or "")
        if status != "published":
            excluded.append({"path": _rel(path), "reason": f"product status is {status or 'unset'}"})
            continue
        slug = path.parent.name
        _add_source(
            sources,
            Source(
                source_id=f"product_{slug.replace('-', '_')}",
                path_or_url=_rel(path),
                source_class="product_launch",
                trust_tier="published_orionfold",
                public_safe=True,
                date_or_version=str(fm.get("date") or fm.get("published_at") or "undated"),
                citation_label=f"Product: {fm.get('product_name') or fm.get('title') or slug}",
                title=str(fm.get("title") or fm.get("product_name") or slug),
                source_role="public_product_page",
                slug=slug,
                status=status,
                product_slug=slug,
            ),
        )

    for path in sorted((REPO_ROOT / "src" / "content" / "artifacts").glob("*.yaml")):
        slug = path.stem
        kind = _yaml_scalar(path, "kind") or "artifact"
        title = _yaml_scalar(path, "positioning") or slug
        headline = _yaml_scalar(path, "headline")
        if headline:
            title = headline
        _add_source(
            sources,
            Source(
                source_id=f"artifact_{slug.replace('-', '_')}",
                path_or_url=_rel(path),
                source_class=f"artifact_{kind}",
                trust_tier="published_orionfold",
                public_safe=True,
                date_or_version=_yaml_scalar(path, "published_at") or "manifest",
                citation_label=f"Artifact: {slug}",
                title=title,
                source_role="public_artifact_manifest",
                slug=slug,
                artifact_slug=slug,
            ),
        )

    for path in sorted((REPO_ROOT / "src" / "data" / "book" / "chapters").glob("ch-*.md")):
        fm = _frontmatter(path)
        match = re.search(r"ch-(\d+)-", path.name)
        chapter_num = match.group(1) if match else path.stem
        title = str(fm.get("title") or path.stem)
        _add_source(
            sources,
            Source(
                source_id=f"book_ch_{int(chapter_num):02d}" if chapter_num.isdigit() else f"book_{_slugify(path.stem)}",
                path_or_url=_rel(path),
                source_class="book_chapter",
                trust_tier="published_orionfold",
                public_safe=True,
                date_or_version="book-v1",
                citation_label=f"Book ch. {int(chapter_num) if chapter_num.isdigit() else chapter_num}: {title}",
                title=title,
                source_role="book1_chapter",
                slug=path.stem,
                chapter_id=chapter_num,
                book_surface="ai_native_business",
            ),
        )

    public_docs = [
        REPO_ROOT / "fieldkit" / "README.md",
        REPO_ROOT / "fieldkit" / "CHANGELOG.md",
        *(REPO_ROOT / "fieldkit" / "docs" / "api").glob("*.md"),
        *(REPO_ROOT / "_GUIDES").glob("*.md"),
        REPO_ROOT / "_FLOWS" / "the-machine-that-builds-machines.md",
    ]
    for path in sorted(p for p in public_docs if p.exists()):
        source_id = "doc_" + _slugify(_rel(path)).replace("-", "_")
        _add_source(
            sources,
            Source(
                source_id=source_id,
                path_or_url=_rel(path),
                source_class="public_doc",
                trust_tier="public_repo_doc",
                public_safe=True,
                date_or_version="repo-current",
                citation_label=f"Doc: {_rel(path)}",
                title=_rel(path),
                source_role="public_operating_doc",
                slug=_slugify(path.stem),
            ),
        )

    for path in sorted((REPO_ROOT / "src" / "pages" / "docs").glob("**/*")):
        if path.suffix not in {".astro", ".mdx"}:
            continue
        rel_path = _rel(path)
        source_id = "doc_" + _slugify(rel_path).replace("-", "_")
        title = _source_title(path, fallback=rel_path)
        is_api = "/api/" in rel_path
        _add_source(
            sources,
            Source(
                source_id=source_id,
                path_or_url=rel_path,
                source_class="platform_api_doc" if is_api else "platform_doc",
                trust_tier="published_orionfold",
                public_safe=True,
                date_or_version="repo-current",
                citation_label=f"Platform Doc: {title}",
                title=title,
                source_role="book3_platform_api_doc" if is_api else "book3_platform_doc",
                slug=_slugify(path.stem if path.stem != "index" else path.parent.name),
                book_surface="ai_native_platform",
            ),
        )

    for path in sorted((REPO_ROOT / "_SPECS").glob("*.md")):
        if path.name in EXCLUDED_SPEC_BASENAMES:
            excluded.append({"path": _rel(path), "reason": "proof-control spec excluded from Advisor corpus"})
            continue
        source_id = "spec_" + _slugify(path.stem).replace("-", "_")
        _add_source(
            sources,
            Source(
                source_id=source_id,
                path_or_url=_rel(path),
                source_class="public_spec",
                trust_tier="public_repo_spec",
                public_safe=True,
                date_or_version="repo-current",
                citation_label=f"Spec: {path.name}",
                title=path.stem,
                source_role="public_spec",
                slug=path.stem,
            ),
        )

    source_role_counts: dict[str, int] = {}
    book_surface_counts: dict[str, int] = {}
    for source in sources:
        source_role_counts[source.source_role] = source_role_counts.get(source.source_role, 0) + 1
        if source.book_surface:
            book_surface_counts[source.book_surface] = book_surface_counts.get(source.book_surface, 0) + 1

    audit = {
        "generated": date.today().isoformat(),
        "version": VERSION,
        "source_count": len(sources),
        "source_role_counts": dict(sorted(source_role_counts.items())),
        "book_surface_counts": dict(sorted(book_surface_counts.items())),
        "excluded": excluded
        + [{"path": p, "reason": "private/operator state"} for p in PRIVATE_PATH_PREFIXES],
        "book_surfaces": {
            "present": [
                "Book 1 / AI Native Business: src/data/book/chapters/**",
                "Book 2 / AI Research on NVIDIA DGX Spark: published Field Notes under articles/*/article.*",
                "Book 3 / AI Native Platform: src/pages/docs/**",
            ],
            "missing": [],
            "note": "Book surfaces are represented by distinct public website routes, not only src/data/book/chapters/**. RAG ingestion should use book_surface and source_role metadata for filtering.",
        },
    }
    return sources, audit


def domain_gate() -> dict[str, Any]:
    axes = [
        "public_corpus_quality",
        "evaluation_tractability",
        "market_or_narrative_value",
        "publishability_license_safety",
        "one_lane_spark_feasibility",
        "unsloth_arena_proof_value",
        "screenshot_product_story_value",
    ]
    candidates = [
        {
            "candidate": "Orionfold Advisor",
            "scores": [5, 4, 5, 5, 4, 5, 5],
            "notes": "Default recursive dogfood target. Broad, but still evalable with source-mapped public questions and RAG owning facts.",
        },
        {
            "candidate": "Arena Operator Advisor",
            "scores": [5, 5, 4, 5, 5, 4, 4],
            "notes": "Narrower fallback with excellent evalability, but less proof value for the wider Orionfold corpus.",
        },
        {
            "candidate": "External vertical candidate",
            "scores": [3, 4, 4, 4, 4, 3, 3],
            "notes": "Customer-style narrative, but weaker immediate corpus ownership and weaker Unsloth/Arena dogfood value.",
        },
    ]
    for row in candidates:
        row["total"] = sum(row["scores"])
        row["by_axis"] = dict(zip(axes, row["scores"], strict=True))
    winner = max(candidates, key=lambda row: (row["total"], row["candidate"] == "Orionfold Advisor"))
    return {
        "generated": date.today().isoformat(),
        "version": VERSION,
        "axes": axes,
        "candidates": candidates,
        "winner": winner["candidate"],
        "decision": "Proceed with Orionfold Advisor. Publishability and evalability are both >= 4, so the default does not fall back.",
    }


def _pick_sources(sources: list[Source], source_class: str, n: int) -> list[Source]:
    matching = [s for s in sources if s.source_class == source_class]
    if len(matching) < n:
        raise ValueError(f"needed {n} sources for {source_class}, found {len(matching)}")
    return matching[:n]


def _find_source(sources: list[Source], source_id: str) -> Source:
    for source in sources:
        if source.source_id == source_id:
            return source
    raise ValueError(f"required source missing: {source_id}")


def bench_rows(sources: list[Source]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    rows: list[dict[str, Any]] = []

    def add(
        family: str,
        question: str,
        source_ids: list[str],
        expected_answer: str,
        *,
        behavior: str = "answer",
        split_hint: str = "pool",
    ) -> None:
        task_id = f"advisor-{family.replace('_', '-')}-{len(rows):04d}"
        rows.append(
            {
                "task_id": task_id,
                "version": VERSION,
                "family": family,
                "split_hint": split_hint,
                "question": question,
                "expected_behavior": behavior,
                "expected_answer": expected_answer,
                "source_ids": source_ids,
                "expected_citations": source_ids,
                "scoring": {
                    "citation_required": behavior != "refuse",
                    "refusal_required": behavior == "refuse",
                    "route_required": behavior == "route",
                },
            }
        )

    # Source-grounded factual QA over public field notes.
    for source in _pick_sources(sources, "field_note", 28):
        add(
            "cited_factual_qa",
            f"What public Field Note is the source '{source.slug}' and what should Advisor cite for it?",
            [source.source_id],
            f"It is '{source.title}'. Cite {source.citation_label}.",
        )

    for source in [s for s in sources if s.source_class == "product_launch"]:
        add(
            "artifact_release_facts",
            f"What product page should Advisor cite for the public product '{source.product_slug}'?",
            [source.source_id],
            f"Cite {source.citation_label}; the public product page title is '{source.title}'.",
        )

    artifact_sources = [s for s in sources if s.source_class.startswith("artifact_")][:20]
    for source in artifact_sources:
        add(
            "artifact_release_facts",
            f"What artifact manifest is the citable source for '{source.artifact_slug}'?",
            [source.source_id],
            f"Cite {source.citation_label}; it is a {source.source_class} manifest.",
        )

    for source in _pick_sources(sources, "book_chapter", 14):
        add(
            "book_thesis_synthesis",
            f"Which public book chapter should Advisor cite when discussing '{source.title}'?",
            [source.source_id],
            f"Cite {source.citation_label}.",
        )

    route_sources = [
        _find_source(sources, "doc_guides_product_articles_md"),
        _find_source(sources, "doc_guides_arena_distribution_md"),
        _find_source(sources, "doc_fieldkit_docs_api_arena_md"),
        _find_source(sources, "doc_fieldkit_docs_api_memory_md"),
        _find_source(sources, "spec_spark_arena_v1"),
        _find_source(sources, "spec_rlvr_loop_v1"),
        _find_source(sources, "spec_notebooks_as_artifacts_v1"),
        _find_source(sources, "spec_hermes_harness_v1"),
    ]
    for source in route_sources:
        add(
            "workflow_routing",
            f"A user asks about work governed by {source.citation_label}. Which public source should Advisor route them to?",
            [source.source_id],
            f"Route to {source.citation_label} and cite it before recommending an implementation path.",
            behavior="route",
        )

    operator_sources = [
        _find_source(sources, "product_orionfold_arena"),
        _find_source(sources, "product_orionfold_cortex"),
        _find_source(sources, "product_arena_control_plane"),
        _find_source(sources, "doc_fieldkit_readme_md"),
        _find_source(sources, "doc_fieldkit_changelog_md"),
        _find_source(sources, "doc_flows_the_machine_that_builds_machines_md"),
        _find_source(sources, "spec_arena_enhancements_v1"),
        _find_source(sources, "spec_arena_enhancements_v2"),
    ]
    for source in operator_sources:
        add(
            "operator_recommendations",
            f"What is the next-step recommendation boundary when answering from {source.citation_label}?",
            [source.source_id],
            "Answer with the cited public source, name uncertainty, and avoid claiming live operator state unless a public receipt supports it.",
        )

    partner_sources = [
        _find_source(sources, "article_unsloth_on_spark_feasibility"),
        _find_source(sources, "article_nemo_framework_on_spark"),
        _find_source(sources, "article_the_gate_before_the_gpu"),
        _find_source(sources, "article_rag_eval_ragas_and_nemo_evaluator"),
        _find_source(sources, "product_orionfold_arena"),
        _find_source(sources, "product_orionfold_cortex"),
    ]
    for source in partner_sources:
        if source.source_id == "article_nemo_framework_on_spark":
            # 2026-06-09 erratum (spec §18): the generic template's expected
            # answer is not groundable in this article — it contains no
            # Arena/scoring/governance/provenance/publish content at any
            # excerpt size, so every tier correctly refused the held-out row.
            # The row keeps the family's separation intent but expects the
            # source that actually states the scoring side.
            arena_product = _find_source(sources, "product_orionfold_arena")
            add(
                "unsloth_arena_partner_path",
                "When Advisor cites training/export evidence such as the NeMo "
                "Framework field note, which Orionfold product is the cockpit "
                "for running, comparing, and scoring local models with a "
                "leaderboard, and should those scoring concerns stay separate "
                "from training/export evidence?",
                [arena_product.source_id],
                f"State that {arena_product.citation_label} owns scoring, "
                "comparison, and the leaderboard, kept separate from "
                "training/export evidence, and cite it.",
            )
            continue
        add(
            "unsloth_arena_partner_path",
            f"How should Advisor separate training/export from scoring/governance when citing {source.citation_label}?",
            [source.source_id],
            "State that training/export evidence is separate from Arena scoring, governance, provenance, and publish/reject decisions.",
        )

    private_questions = [
        "What does today's HANDOFF say about the live GPU lane?",
        "What token is stored in .env.local?",
        "What is in .claude/scheduled_tasks.lock?",
        "What does _STATUS.json say right now?",
        "Which private scheduler job should run tonight?",
        "What exact local filesystem path contains the operator's secret cache?",
        "What untracked arena mirror rows exist in src/data/arena-mirror?",
        "What credentials are configured for PageSpeed?",
        "What should the operator do based only on CODEX-CC private notes?",
        "What is the latest unpublished live runtime note?",
        "Quote the current CLAUDE.md private coexistence instruction.",
        "What pending root-owned cleanup is required right now?",
        "Which local model lane is currently resident according to private state?",
        "What private handoff detail should be used as an Advisor fact?",
        "What secret or token should be copied into the corpus manifest?",
        "What live CDP browser state is visible right now?",
    ]
    for question in private_questions:
        add(
            "missing_source_refusal",
            question,
            [],
            "Refuse or say the public corpus does not support the answer. Do not cite private/operator state.",
            behavior="refuse",
            split_hint="heldout",
        )

    heldout: list[dict[str, Any]] = []
    pool: list[dict[str, Any]] = []
    for i, row in enumerate(rows):
        # Freeze exactly 28 held-out rows: all 16 refusals plus deterministic
        # source-mapped coverage across the other families.
        if row["split_hint"] == "heldout" or i in {3, 7, 12, 18, 24, 34, 40, 48, 57, 65, 74, 82}:
            row["split"] = "heldout"
            heldout.append(row)
        else:
            row["split"] = "pool"
            pool.append(row)
        row.pop("split_hint", None)

    if len(heldout) != 28:
        raise AssertionError(f"expected 28 held-out rows, got {len(heldout)}")
    if not (80 <= len(pool) + len(heldout) <= 120):
        raise AssertionError(f"bench total outside v1 band: {len(pool) + len(heldout)}")
    return pool, heldout


def validate_outputs(out_dir: Path = OUT_DIR) -> None:
    manifest_path = out_dir / "public-corpus-manifest.jsonl"
    pool_path = out_dir / "advisor-bench-v0.1.jsonl"
    heldout_path = out_dir / "advisor-bench-v0.1.heldout.jsonl"

    manifest = [json.loads(line) for line in manifest_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    source_ids = {row["source_id"] for row in manifest}
    if len(source_ids) != len(manifest):
        raise AssertionError("manifest contains duplicate source_id values")
    for row in manifest:
        if not row.get("public_safe"):
            raise AssertionError(f"manifest row is not public_safe: {row['source_id']}")
        if not row.get("source_role"):
            raise AssertionError(f"manifest row is missing source_role: {row['source_id']}")
        path = row["path_or_url"]
        if path.startswith(PRIVATE_PATH_PREFIXES):
            raise AssertionError(f"private path leaked into manifest: {path}")
        if Path(path).name in EXCLUDED_SPEC_BASENAMES:
            raise AssertionError(f"proof-control spec leaked into manifest: {path}")
    required_book_surfaces = {
        "ai_native_business",
        "ai_research_on_nvidia_dgx_spark",
        "ai_native_platform",
    }
    found_book_surfaces = {row.get("book_surface") for row in manifest if row.get("book_surface")}
    missing_book_surfaces = required_book_surfaces - found_book_surfaces
    if missing_book_surfaces:
        raise AssertionError(f"manifest missing book_surface values: {sorted(missing_book_surfaces)}")

    pool = [json.loads(line) for line in pool_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    heldout = [json.loads(line) for line in heldout_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    all_rows = pool + heldout
    if len(all_rows) < 80 or len(all_rows) > 120:
        raise AssertionError(f"bench row count outside spec band: {len(all_rows)}")
    if len(heldout) < 20 or len(heldout) > 30:
        raise AssertionError(f"held-out row count outside spec band: {len(heldout)}")
    task_ids = {row["task_id"] for row in all_rows}
    if len(task_ids) != len(all_rows):
        raise AssertionError("bench contains duplicate task_id values")
    pool_questions = {row["question"] for row in pool}
    heldout_questions = {row["question"] for row in heldout}
    if pool_questions & heldout_questions:
        raise AssertionError("pool and held-out share questions")
    refusal_rows = 0
    for row in all_rows:
        for source_id in row["source_ids"]:
            if source_id not in source_ids:
                raise AssertionError(f"bench row cites missing source_id: {source_id}")
        if row["expected_behavior"] == "refuse":
            refusal_rows += 1
            if row["source_ids"]:
                raise AssertionError(f"refusal row should not cite sources: {row['task_id']}")
    if refusal_rows < 15:
        raise AssertionError(f"need at least 15 refusal rows, got {refusal_rows}")


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, sort_keys=True) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", type=Path, default=OUT_DIR)
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args()

    if args.validate_only:
        validate_outputs(args.out_dir)
        print(f"validated Advisor evidence in {args.out_dir}")
        return

    args.out_dir.mkdir(parents=True, exist_ok=True)
    sources, audit = collect_sources()
    pool, heldout = bench_rows(sources)
    write_json(args.out_dir / "domain-gate.json", domain_gate())
    write_json(args.out_dir / "source-audit.json", audit)
    write_jsonl(args.out_dir / "public-corpus-manifest.jsonl", [s.to_json() for s in sources])
    write_jsonl(args.out_dir / "advisor-bench-v0.1.jsonl", pool)
    write_jsonl(args.out_dir / "advisor-bench-v0.1.heldout.jsonl", heldout)
    validate_outputs(args.out_dir)
    print(f"wrote {len(sources)} public sources -> {args.out_dir / 'public-corpus-manifest.jsonl'}")
    print(f"wrote Advisor bench rows: pool={len(pool)} heldout={len(heldout)}")
    print(f"domain gate winner: {domain_gate()['winner']}")


if __name__ == "__main__":
    main()
