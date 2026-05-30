# Copyright 2026 Manav Sehgal
# SPDX-License-Identifier: Apache-2.0
"""Retroactive load — walks the repo into ``~/.fieldkit/arena.db``.

**M2 surface.** This is the deterministic-Python spine of M2. Spec §7 gives
the source inventory; this module walks each source, normalizes it into the
:class:`fieldkit.arena.schemas` records, and upserts via :class:`ArenaStore`.
The CLI entry point in :mod:`fieldkit.arena.cli` and the script shim in
``scripts/import_existing.py`` both call :func:`import_artifacts` — no logic
lives there, so tests cover the same code path operators run.

**Inventory (per spec §7):**

- ``src/content/artifacts/*.yaml`` (17 manifests) → ``lanes`` (per variant
  for quant/lora; one nav row per harness/skill/bench/notebook).
- ``articles/*/article.md`` (49 published + 6 upcoming frontmatter) →
  ``article_index``.
- ``articles/<slug>/evidence/*_results.json`` → ``bench_results`` (per
  ``(bench_slug, variant_label)``).
- ``articles/picking-the-hermes-brain-on-spark/evidence/hermes_brain_results.json``
  → ``leaderboard_rows`` (the day-one cut + the 3 brain-bakeoff lanes the
  3 ``models[label]`` entries seed).
- ``notebooks/<vertical>/exports/**/*.png`` → ``notebook_export``.
- HF API (13 ``Orionfold/`` repos) → ``hf_meta`` (optional — skipped without
  network or without ``huggingface_hub``; the importer still succeeds).
- ``~/.hermes/config.yaml`` (optional — skipped if absent) →
  one ``lanes`` row for the resident-brain endpoint Hermes is pointed at.

**Idempotency gate (M2 validation):** every upsert uses
``INSERT OR REPLACE``, so re-running ``fieldkit arena import`` produces
identical row counts. The test
``test_importer_is_idempotent_on_second_run`` asserts that.

Per `feedback_llm_skill_pattern`: deterministic Python only.
"""

from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from fieldkit.arena.schemas import (
    ArticleIndexRow,
    BenchResultRow,
    HfMetaRow,
    LaneRecord,
    LeaderboardRow,
    NotebookExportRow,
)
from fieldkit.arena.store import ArenaStore

__all__ = [
    "ImportReport",
    "import_artifacts",
    "ORIONFOLD_HF_REPOS",
    "DEFAULT_REPO_ROOT",
    "DEFAULT_MIRROR_LEADERBOARD_PATH",
]

log = logging.getLogger("fieldkit.arena.importer")

# Resolve once: this file lives at fieldkit/src/fieldkit/arena/importer.py;
# the repo root is four levels up. The CLI accepts an override so the
# importer is testable against a temp tree.
DEFAULT_REPO_ROOT: Path = Path(__file__).resolve().parents[4]

# Day-one leaderboard cut path (committed to the repo so the M3 cockpit
# landing has data to render before M5 lands the live compare).
DEFAULT_MIRROR_LEADERBOARD_PATH = "src/data/arena-mirror/leaderboard.json"

# Hardcoded list of HF repos we publish under (per spec §7 — 13 repos).
# Kept as a frozen tuple so the HF refresh has a deterministic ordering;
# any new Orionfold release appends one entry here (the curator skill's
# `import-new` mode auto-appends; for M2 we list them by hand).
ORIONFOLD_HF_REPOS: tuple[str, ...] = (
    # quants (GGUFs)
    "Orionfold/patent-strategist-v3-nemo-GGUF",
    "Orionfold/saul-7b-instruct-v1-GGUF",
    "Orionfold/finance-chat-GGUF",
    "Orionfold/securityllm-GGUF",
    "Orionfold/ii-medical-8b-GGUF",
    # LoRA (merged adapter — the Unsloth lane is unpublished per
    # `project_patent_strategist_unsloth_unpublished`)
    "Orionfold/patent-strategist-v3-nemo",
    # benches (datasets)
    "Orionfold/patent-strategist-bench-v0.1",
    "Orionfold/hermes-brain-bench-v0.1",
    # harnesses (Hermes profiles + routers)
    "Orionfold/spark-hermes-profile",
    "Orionfold/spark-hermes-vertical-router",
    "Orionfold/spark-hermes-cost-router",
    # notebooks (artifact pairs publish into their model repos, not
    # separate notebook repos — these two are the pilot vertical pair)
    "Orionfold/patent-strategist-v3-nemo-Notebooks",
    # skills (lives on GitHub not HF, but tracked here for symmetry —
    # the importer marks it `error='hosted-on-github'` rather than
    # silently dropping it)
    "manavsehgal/spark-skills",
)


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------


@dataclass
class ImportReport:
    """Row-count summary returned by :func:`import_artifacts`.

    Counts are *post-upsert* totals from the database, NOT the number of
    rows written this run — that means a re-run with identical inputs
    returns the same numbers (idempotency gate per spec M2 validation).
    """

    db_path: str
    repo_root: str
    lanes: int = 0
    bench_results: int = 0
    article_index: int = 0
    hf_meta: int = 0
    notebook_export: int = 0
    leaderboard_rows: int = 0
    skipped: dict[str, int] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        d = asdict(self)
        return d

    def summary_line(self) -> str:
        return (
            f"lanes={self.lanes} bench_results={self.bench_results} "
            f"article_index={self.article_index} hf_meta={self.hf_meta} "
            f"notebook_export={self.notebook_export} "
            f"leaderboard_rows={self.leaderboard_rows}"
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


_FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n", re.DOTALL)


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _load_yaml(path: Path) -> dict[str, Any]:
    import yaml  # local import — pyyaml ships via the `arena` extra

    with path.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    if not isinstance(data, dict):
        raise ValueError(f"Expected mapping in {path}, got {type(data).__name__}")
    return data


def _parse_frontmatter(article_path: Path) -> dict[str, Any] | None:
    """Return the YAML frontmatter at the top of ``article.md``, or None."""
    try:
        with article_path.open("r", encoding="utf-8") as fh:
            head = fh.read(8192)
    except OSError:
        return None
    m = _FRONTMATTER_RE.match(head)
    if not m:
        return None
    import yaml

    try:
        data = yaml.safe_load(m.group(1)) or {}
    except yaml.YAMLError:
        return None
    return data if isinstance(data, dict) else None


def _bench_slug_from_results_json(path: Path) -> str:
    """Derive a stable bench slug from the article + filename.

    Examples:
      articles/picking-the-hermes-brain-on-spark/evidence/hermes_brain_results.json
        -> 'picking-the-hermes-brain-on-spark:hermes_brain'
      articles/hermes-serving-lane-on-spark/evidence/bakeoff_results.json
        -> 'hermes-serving-lane-on-spark:bakeoff'
    """
    parts = path.parts
    try:
        article_idx = parts.index("articles") + 1
        article_slug = parts[article_idx]
    except (ValueError, IndexError):
        article_slug = "unknown"
    stem = path.stem
    if stem.endswith("_results"):
        stem = stem[: -len("_results")]
    return f"{article_slug}:{stem}"


# ---------------------------------------------------------------------------
# Walks
# ---------------------------------------------------------------------------


def _walk_manifests(repo_root: Path, store: ArenaStore) -> tuple[int, list[str]]:
    """Each manifest yields one or more ``lanes`` rows; return inserted count
    + a list of warnings for malformed manifests."""
    manifests_dir = repo_root / "src" / "content" / "artifacts"
    if not manifests_dir.is_dir():
        return 0, [f"no manifest dir at {manifests_dir}"]

    inserted = 0
    warnings: list[str] = []
    now = _utcnow_iso()

    for path in sorted(manifests_dir.glob("*.yaml")):
        try:
            data = _load_yaml(path)
        except Exception as exc:
            warnings.append(f"failed to parse {path.name}: {exc}")
            continue

        slug = data.get("slug") or path.stem
        kind = data.get("kind") or "unknown"
        base_model = data.get("base_model") or ""
        recommended_variant = data.get("recommended_variant")
        variants = data.get("variants") or []

        # quant/lora → one lane per variant; harness/skill/bench/notebook →
        # one navigational row (the operator still wants to see them in the
        # browser even though they aren't directly servable).
        if kind in ("quant", "lora") and variants:
            for variant in variants:
                lane_id = f"{slug}::{variant}"
                store.upsert_lane(
                    asdict(
                        LaneRecord(
                            id=lane_id,
                            kind=_lane_kind_for_manifest(kind, data),
                            model=f"{base_model}@{variant}" if base_model else str(variant),
                            port=0,  # M2 doesn't know the live port; M3 fills
                            base_url="",
                            manifest_slug=slug,
                            recommended=1 if variant == recommended_variant else 0,
                            notes=f"From {path.name}",
                        )
                    )
                )
                inserted += 1
        else:
            # nav-only row — single entry keyed by slug
            lane_id = f"{slug}::nav"
            store.upsert_lane(
                asdict(
                    LaneRecord(
                        id=lane_id,
                        kind=_lane_kind_for_manifest(kind, data),
                        model=base_model or slug,
                        port=0,
                        base_url="",
                        manifest_slug=slug,
                        recommended=1,
                        notes=f"Nav row for {kind} manifest {path.name}",
                    )
                )
            )
            inserted += 1

    return inserted, warnings


def _lane_kind_for_manifest(manifest_kind: str, data: Mapping[str, Any]) -> str:
    """Map (manifest.kind, manifest.class) to a `lanes.kind` bucket.

    GGUF quants → ``LlamaServerLane`` (the lane that serves them on Spark).
    NVFP4 quants → ``VLLMLane``. LoRA merged adapter → ``LoRAMerged``.
    Harness/skill/bench/notebook → a navigational bucket (no live serving).
    """
    cls = (data.get("class") or "").lower()
    if manifest_kind == "quant":
        if cls == "gguf":
            return "LlamaServerLane"
        if cls in ("nvfp4", "fp8"):
            return "VLLMLane"
        return "LlamaServerLane"  # best default for an unknown quant class
    if manifest_kind == "lora":
        return "LoRAMerged"
    if manifest_kind == "harness":
        return "HarnessConfig"
    if manifest_kind == "skill":
        return "SkillBundle"
    if manifest_kind == "bench":
        return "BenchSpec"
    if manifest_kind == "notebook":
        return "NotebookPair"
    return manifest_kind  # pass-through for forward compat


def _walk_articles(repo_root: Path, store: ArenaStore) -> tuple[int, list[str]]:
    articles_dir = repo_root / "articles"
    if not articles_dir.is_dir():
        return 0, [f"no articles dir at {articles_dir}"]

    inserted = 0
    warnings: list[str] = []
    now = _utcnow_iso()

    for article_path in sorted(articles_dir.glob("*/article.md")):
        fm = _parse_frontmatter(article_path)
        if fm is None:
            warnings.append(f"no frontmatter in {article_path.relative_to(repo_root)}")
            continue

        slug = article_path.parent.name
        title = fm.get("title") or slug
        series = fm.get("series")
        stage = fm.get("stage")
        status = fm.get("status") or "published"
        customer_linked = 1 if fm.get("customer_linked") else 0
        published_at = fm.get("date")
        if published_at is not None:
            published_at = str(published_at)
        signature = fm.get("signature")
        summary = fm.get("summary")
        fk_modules = fm.get("fieldkit_modules") or []

        store.upsert_article(
            asdict(
                ArticleIndexRow(
                    slug=slug,
                    title=str(title),
                    source_path=str(article_path.relative_to(repo_root)),
                    fetched_at=now,
                    series=str(series) if series else None,
                    stage=str(stage) if stage else None,
                    status=str(status),
                    customer_linked=customer_linked,
                    published_at=published_at,
                    signature=str(signature) if signature else None,
                    summary=str(summary) if summary else None,
                    fieldkit_modules_json=(
                        json.dumps(fk_modules) if fk_modules else None
                    ),
                    referenced_artifact_slugs_json=None,
                )
            )
        )
        inserted += 1

    return inserted, warnings


def _walk_bench_results(
    repo_root: Path, store: ArenaStore
) -> tuple[int, list[str]]:
    articles_dir = repo_root / "articles"
    if not articles_dir.is_dir():
        return 0, []

    inserted = 0
    warnings: list[str] = []
    now = _utcnow_iso()

    for path in sorted(articles_dir.glob("*/evidence/*_results.json")):
        try:
            with path.open("r", encoding="utf-8") as fh:
                data = json.load(fh)
        except (OSError, json.JSONDecodeError) as exc:
            warnings.append(f"failed to parse {path.relative_to(repo_root)}: {exc}")
            continue

        bench_slug = _bench_slug_from_results_json(path)
        rows = _extract_bench_rows(data)
        if not rows:
            warnings.append(
                f"no per-variant rows extracted from "
                f"{path.relative_to(repo_root)} — skipped"
            )
            continue

        for row in rows:
            store.upsert_bench_result(
                asdict(
                    BenchResultRow(
                        bench_slug=bench_slug,
                        variant_label=row["variant_label"],
                        core_pass_rate=row.get("core_pass_rate"),
                        consistency=row.get("consistency"),
                        runaway_rate=row.get("runaway_rate"),
                        wall_mean_s=row.get("wall_mean_s"),
                        tok_per_sec=row.get("tok_per_sec"),
                        p50_s=row.get("p50_s"),
                        p95_s=row.get("p95_s"),
                        gpu_util_mean=row.get("gpu_util_mean"),
                        unified_used_gb_max=row.get("unified_used_gb_max"),
                        source_path=str(path.relative_to(repo_root)),
                        fetched_at=now,
                    )
                )
            )
            inserted += 1

    return inserted, warnings


def _extract_bench_rows(data: Any) -> list[dict[str, Any]]:
    """Best-effort extraction of per-variant rollup rows from a bench JSON.

    The canonical shape (brain-bakeoff) is ``{"models": {label: {...}}}``
    where each value carries ``core_pass_rate``, ``consistency``,
    ``runaway_rate``, ``wall_mean_s``, ``tokens_per_sec`` (with an ``_s``
    suffix in some lanes), ``latency.p50_s`` / ``latency.p95_s``,
    ``telemetry.gpu_util_mean`` / ``telemetry.unified_used_gb_max``.

    Other shapes (router bakeoffs, etc.) carry per-vertical or per-strategy
    breakdowns under different top-level keys; we extract what we can and
    fill ``None`` for the rest. The cockpit treats ``None`` as "not
    measured" rather than an error.
    """
    rows: list[dict[str, Any]] = []
    if not isinstance(data, dict):
        return rows

    # 1) Canonical brain-bakeoff shape (`models`) — also the H2 serving-lane
    # bakeoff shape (`lanes` at top level, distinct from the SQLite table).
    for top_key in ("models", "lanes"):
        block = data.get(top_key)
        if isinstance(block, dict):
            for label, payload in block.items():
                if not isinstance(payload, dict):
                    continue
                rows.append(_row_from_model_payload(label, payload))
            if rows:
                return rows

    # 2) Cost-router shape: `strategies` is a DICT of label → {summary, ...}
    # with `majority_pass_rates` on the top-level `summary` and total cost
    # at `summary.total_cost_usd_per_strategy`.
    strategies = data.get("strategies")
    summary = data.get("summary") if isinstance(data.get("summary"), dict) else {}
    pass_rates = summary.get("majority_pass_rates") if isinstance(summary, dict) else None
    cost_by_strategy = (
        summary.get("total_cost_usd_per_strategy") if isinstance(summary, dict) else None
    )
    if isinstance(strategies, dict):
        for label, payload in strategies.items():
            row = {
                "variant_label": str(label),
                "core_pass_rate": (
                    pass_rates.get(label) if isinstance(pass_rates, dict) else None
                ),
            }
            if isinstance(payload, dict):
                row["consistency"] = payload.get("consistency")
                row["tok_per_sec"] = payload.get("tok_per_sec")
                row["wall_mean_s"] = payload.get("wall_mean_s")
            # Cost-routed strategies record `$ spent` as wall-equivalent
            # context — keep in notes via source_path; no schema bump.
            rows.append(row)
        if rows:
            return rows
    if isinstance(strategies, list):
        for entry in strategies:
            if not isinstance(entry, dict):
                continue
            label = entry.get("label") or entry.get("name") or "default"
            rows.append(
                {
                    "variant_label": str(label),
                    "core_pass_rate": entry.get("accuracy")
                    or entry.get("pass_rate"),
                    "consistency": entry.get("consistency"),
                    "tok_per_sec": entry.get("tok_per_sec"),
                }
            )
        if rows:
            return rows

    # 3) Vertical-router shape: `per_vertical_quality` + `summary.vertical_pass_rates`
    per_vert = data.get("per_vertical_quality")
    vert_pass = summary.get("vertical_pass_rates") if isinstance(summary, dict) else None
    vert_warm = summary.get("vertical_warm_seconds") if isinstance(summary, dict) else None
    if isinstance(per_vert, dict) or isinstance(vert_pass, dict):
        labels = set()
        if isinstance(per_vert, dict):
            labels.update(per_vert.keys())
        if isinstance(vert_pass, dict):
            labels.update(vert_pass.keys())
        for label in sorted(labels):
            payload = per_vert.get(label) if isinstance(per_vert, dict) else None
            row = {
                "variant_label": str(label),
                "core_pass_rate": (
                    vert_pass.get(label) if isinstance(vert_pass, dict) else None
                ),
                "wall_mean_s": (
                    vert_warm.get(label) if isinstance(vert_warm, dict) else None
                ),
            }
            if isinstance(payload, dict):
                row.setdefault(
                    "core_pass_rate",
                    payload.get("pass_rate") or payload.get("accuracy"),
                )
            rows.append(row)
        if rows:
            return rows

    # 4) Original list-of-{label} verticals fallback
    verticals = data.get("verticals")
    if isinstance(verticals, dict):
        for label, payload in verticals.items():
            if not isinstance(payload, dict):
                continue
            rows.append(
                {
                    "variant_label": str(label),
                    "core_pass_rate": payload.get("pass_rate"),
                    "wall_mean_s": payload.get("warm_time_s"),
                }
            )
        if rows:
            return rows

    return rows


def _row_from_model_payload(label: str, payload: dict[str, Any]) -> dict[str, Any]:
    latency = payload.get("latency") if isinstance(payload.get("latency"), dict) else {}
    telemetry = (
        payload.get("telemetry") if isinstance(payload.get("telemetry"), dict) else {}
    )
    return {
        "variant_label": str(label),
        "core_pass_rate": payload.get("core_pass_rate"),
        "consistency": payload.get("consistency"),
        "runaway_rate": payload.get("runaway_rate"),
        "wall_mean_s": payload.get("wall_mean_s"),
        "tok_per_sec": payload.get("tokens_per_sec") or payload.get("tok_per_sec"),
        "p50_s": latency.get("p50_s"),
        "p95_s": latency.get("p95_s"),
        "gpu_util_mean": telemetry.get("gpu_util_mean"),
        "unified_used_gb_max": telemetry.get("unified_used_gb_max"),
    }


def _walk_notebook_exports(
    repo_root: Path, store: ArenaStore
) -> tuple[int, list[str]]:
    notebooks_dir = repo_root / "notebooks"
    if not notebooks_dir.is_dir():
        return 0, []

    inserted = 0
    warnings: list[str] = []
    now = _utcnow_iso()

    for path in sorted(notebooks_dir.glob("*/exports/*/*.png")):
        try:
            rel = path.relative_to(repo_root)
        except ValueError:
            rel = path
        # path = notebooks/<vertical>/exports/<role>/<file>.png
        parts = rel.parts
        if len(parts) < 5:
            continue
        vertical = parts[1]
        role = parts[3]  # 'builder' | 'user'
        # Match the notebook manifest slug convention:
        # notebooks/patent-strategist/exports/... → patent-strategist-notebooks
        artifact_slug = f"{vertical}-notebooks"
        try:
            stat = path.stat()
            size = stat.st_size
            mtime = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).strftime(
                "%Y-%m-%dT%H:%M:%SZ"
            )
        except OSError:
            size = None
            mtime = None

        store.upsert_notebook_export(
            asdict(
                NotebookExportRow(
                    file_path=str(rel),
                    fetched_at=now,
                    artifact_slug=artifact_slug,
                    role=role,
                    kind="png",
                    bytes=size,
                    mtime=mtime,
                )
            )
        )
        inserted += 1

    return inserted, warnings


def _walk_hermes_config(
    repo_root: Path, store: ArenaStore
) -> tuple[int, list[str]]:
    """If ``~/.hermes/config.yaml`` is present, register the lane Hermes is
    currently pointed at. Quietly skips otherwise — Hermes isn't required
    for the importer to succeed."""
    hermes_path = Path("~/.hermes/config.yaml").expanduser()
    if not hermes_path.is_file():
        return 0, []
    try:
        data = _load_yaml(hermes_path)
    except Exception as exc:
        return 0, [f"failed to parse {hermes_path}: {exc}"]

    model_block = data.get("model") or {}
    if not isinstance(model_block, dict):
        return 0, []
    base_url = model_block.get("base_url") or ""
    model = model_block.get("name") or model_block.get("model") or ""
    if not (base_url or model):
        return 0, []

    # Infer port from base_url ("http://127.0.0.1:8080/v1" → 8080).
    port = 0
    m = re.search(r":(\d+)", str(base_url))
    if m:
        port = int(m.group(1))

    store.upsert_lane(
        asdict(
            LaneRecord(
                id="resident-brain",
                kind="LlamaServerLane",
                model=str(model),
                port=port,
                base_url=str(base_url),
                manifest_slug=None,
                recommended=1,
                notes=f"Resident brain inferred from {hermes_path}",
            )
        )
    )
    return 1, []


def _walk_hf_meta(
    repo_root: Path, store: ArenaStore, *, refresh: bool, cache_dir: Path | None
) -> tuple[int, list[str]]:
    """Cached HF metadata pull.

    Without ``--refresh-hf`` we read the on-disk cache (or skip the repo if
    none). With ``--refresh-hf`` we hit ``huggingface_hub.HfApi.repo_info``
    once per repo and write the result to
    ``~/.fieldkit/arena_cache/hf/<safe_repo>.json``. ``huggingface_hub`` is
    in the ``arena`` extra; absence is non-fatal — the row records the error
    + the cockpit shows "metadata not available" rather than blocking.
    """
    inserted = 0
    warnings: list[str] = []
    cache_root = cache_dir or Path("~/.fieldkit/arena_cache/hf").expanduser()
    cache_root.mkdir(parents=True, exist_ok=True)
    now = _utcnow_iso()

    HfApi: Any = None
    if refresh:
        try:
            from huggingface_hub import HfApi as _HfApi  # type: ignore[import-not-found]

            HfApi = _HfApi()
        except Exception as exc:  # noqa: BLE001
            warnings.append(
                f"huggingface_hub unavailable ({exc}); falling back to cache-only"
            )
            HfApi = None

    for repo_id in ORIONFOLD_HF_REPOS:
        safe = repo_id.replace("/", "__")
        cache_path = cache_root / f"{safe}.json"
        meta: dict[str, Any] = {}
        err: str | None = None

        if refresh and HfApi is not None:
            try:
                # Skip non-Orionfold repos (e.g. GitHub-hosted skill bundle)
                if not repo_id.startswith("Orionfold/"):
                    err = "hosted-on-github" if "spark-skills" in repo_id else "non-orionfold"
                else:
                    info = HfApi.repo_info(
                        repo_id=repo_id,
                        # try the right repo_type per published shape
                        repo_type="dataset"
                        if any(b in repo_id for b in ("-bench-",))
                        else "model",
                        timeout=15.0,
                    )
                    meta = {
                        "downloads": getattr(info, "downloads", None),
                        "likes": getattr(info, "likes", None),
                        "last_modified": (
                            info.last_modified.isoformat()
                            if getattr(info, "last_modified", None)
                            else None
                        ),
                        "has_card": 1 if getattr(info, "card_data", None) else 0,
                    }
                    cache_path.write_text(
                        json.dumps({**meta, "fetched_at": now}, indent=2),
                        encoding="utf-8",
                    )
            except Exception as exc:  # noqa: BLE001
                err = str(exc)[:200]

        if not meta and cache_path.is_file():
            try:
                cached = json.loads(cache_path.read_text(encoding="utf-8"))
                meta = {
                    k: cached.get(k)
                    for k in ("downloads", "likes", "last_modified", "has_card")
                }
            except (OSError, json.JSONDecodeError):
                pass

        store.upsert_hf_meta(
            asdict(
                HfMetaRow(
                    repo_id=repo_id,
                    fetched_at=now,
                    downloads=meta.get("downloads"),
                    likes=meta.get("likes"),
                    last_modified=meta.get("last_modified"),
                    has_card=int(meta.get("has_card") or 0),
                    error=err,
                )
            )
        )
        inserted += 1

    return inserted, warnings


def _seed_leaderboard(
    repo_root: Path, store: ArenaStore
) -> tuple[int, list[str]]:
    """Seed ``leaderboard_rows`` + the 3 brain-bakeoff lanes from the
    canonical evidence JSON. Idempotent: the lanes use
    ``id={label}::brain-bakeoff`` so re-running doesn't duplicate."""
    src = (
        repo_root
        / "articles"
        / "picking-the-hermes-brain-on-spark"
        / "evidence"
        / "hermes_brain_results.json"
    )
    if not src.is_file():
        return 0, [f"brain-bakeoff seed not found at {src}"]

    try:
        with src.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, json.JSONDecodeError) as exc:
        return 0, [f"failed to read {src}: {exc}"]

    models = data.get("models") or {}
    if not isinstance(models, dict):
        return 0, [f"unexpected shape in {src}"]

    inserted = 0
    now = _utcnow_iso()
    bench_id = "picking-the-hermes-brain-on-spark:hermes_brain"

    for label, payload in models.items():
        if not isinstance(payload, dict):
            continue
        lane_id = f"{label}::brain-bakeoff"
        store.upsert_lane(
            asdict(
                LaneRecord(
                    id=lane_id,
                    kind=_lane_kind_for_label(label),
                    model=str(label),
                    port=0,
                    base_url="",
                    manifest_slug=None,
                    recommended=1
                    if label == "qwen3-30b-moe-llamacpp-q4km"
                    else 0,
                    notes="Brain-bakeoff lane (Step-2 seed; see HANDOFF)",
                )
            )
        )
        store.upsert_leaderboard_row(
            asdict(
                LeaderboardRow(
                    bench_id=bench_id,
                    lane_id=lane_id,
                    n_runs=int(payload.get("runs") or 0),
                    mean_score=float(payload.get("core_pass_rate") or 0.0),
                    last_run_at=now,
                    manifest_slug=None,
                    median_tok_per_s=payload.get("tokens_per_sec"),
                    mean_ttft_ms=None,
                    human_pref_winrate=None,
                )
            )
        )
        inserted += 1

    return inserted, []


def _lane_kind_for_label(label: str) -> str:
    low = label.lower()
    if "nim" in low:
        return "NIMLane"
    if "vllm" in low:
        return "VLLMLane"
    if "llamacpp" in low or "llama-cpp" in low or "llama.cpp" in low:
        return "LlamaServerLane"
    return "LlamaServerLane"


# ---------------------------------------------------------------------------
# Mirror leaderboard writer (day-one cut for M3 cockpit landing)
# ---------------------------------------------------------------------------


def write_mirror_leaderboard(
    repo_root: Path, store: ArenaStore, out_path: str | os.PathLike[str] | None = None
) -> Path:
    """Write ``src/data/arena-mirror/leaderboard.json`` from the seeded rows.

    This is the file the Astro build reads at M3; committing it lets the
    leaderboard render non-empty on day one (the M6 mirror exporter takes
    over once it lands; M5 will keep both fresh).
    """
    target = Path(out_path) if out_path else (repo_root / DEFAULT_MIRROR_LEADERBOARD_PATH)
    target.parent.mkdir(parents=True, exist_ok=True)
    rows = []
    for row in store.leaderboard_rows():
        rows.append(
            {
                "bench_id": row["bench_id"],
                "lane_id": row["lane_id"],
                "manifest_slug": row["manifest_slug"],
                "n_runs": row["n_runs"],
                "mean_score": row["mean_score"],
                "median_tok_per_s": row["median_tok_per_s"],
                "mean_ttft_ms": row["mean_ttft_ms"],
                "human_pref_winrate": row["human_pref_winrate"],
                "last_run_at": row["last_run_at"],
            }
        )
    payload = {
        "generated_at": _utcnow_iso(),
        "source": "fieldkit arena import (M2 seed)",
        "schema_version": 1,
        "rows": rows,
    }
    target.write_text(json.dumps(payload, indent=2, sort_keys=False) + "\n", encoding="utf-8")
    return target


# ---------------------------------------------------------------------------
# Top-level entry
# ---------------------------------------------------------------------------


def import_artifacts(
    *,
    repo_root: str | os.PathLike[str] | None = None,
    db_path: str | os.PathLike[str] | None = None,
    dry_run: bool = False,
    refresh_hf: bool = False,
    write_mirror: bool = True,
    hf_cache_dir: str | os.PathLike[str] | None = None,
) -> ImportReport:
    """Walk the repo and populate ``~/.fieldkit/arena.db``.

    Parameters
    ----------
    repo_root
        Repo to walk. Defaults to the ai-field-notes checkout this file
        ships in.
    db_path
        SQLite path. Defaults to ``~/.fieldkit/arena.db``.
    dry_run
        Plan-only mode — opens an in-memory SQLite database, runs every
        walk, returns the report. Nothing on disk is touched. Used by the
        CLI's ``--dry-run`` default to let an operator preview row counts
        before committing.
    refresh_hf
        If True, hit the HF API for each ``Orionfold/`` repo; else read the
        cache (or fill an empty row). Default False so M2 doesn't require
        network.
    write_mirror
        If True (default), write ``src/data/arena-mirror/leaderboard.json``
        from the seeded leaderboard rows. Set False in test runs.
    hf_cache_dir
        Override the default ``~/.fieldkit/arena_cache/hf`` cache root.
        Mainly for tests; the live path is what operators want.
    """
    root = Path(repo_root) if repo_root else DEFAULT_REPO_ROOT
    store_path = ":memory:" if dry_run else (
        os.path.expanduser(str(db_path)) if db_path else os.path.expanduser(str(ArenaStore().db_path))
    )
    store = ArenaStore(store_path)

    try:
        store.initialize()

        all_warnings: list[str] = []
        skipped: dict[str, int] = {}

        n_manifests, warn = _walk_manifests(root, store)
        all_warnings.extend(warn)
        n_articles, warn = _walk_articles(root, store)
        all_warnings.extend(warn)
        n_bench, warn = _walk_bench_results(root, store)
        all_warnings.extend(warn)
        n_notebook, warn = _walk_notebook_exports(root, store)
        all_warnings.extend(warn)
        n_hermes, warn = _walk_hermes_config(root, store)
        all_warnings.extend(warn)
        n_hf, warn = _walk_hf_meta(
            root,
            store,
            refresh=refresh_hf,
            cache_dir=Path(hf_cache_dir) if hf_cache_dir else None,
        )
        all_warnings.extend(warn)
        n_seed, warn = _seed_leaderboard(root, store)
        all_warnings.extend(warn)

        if write_mirror and not dry_run:
            target = write_mirror_leaderboard(root, store)
            log.info("wrote mirror leaderboard %s", target)

        # Read post-upsert counts for the report (NOT n_* inserted because
        # the idempotency gate wants stable numbers across re-runs).
        report = ImportReport(
            db_path=str(store.db_path),
            repo_root=str(root),
            lanes=store.count("lanes"),
            bench_results=store.count("bench_results"),
            article_index=store.count("article_index"),
            hf_meta=store.count("hf_meta"),
            notebook_export=store.count("notebook_export"),
            leaderboard_rows=store.count("leaderboard_rows"),
            warnings=all_warnings,
            skipped=skipped,
        )
        return report
    finally:
        store.close()
