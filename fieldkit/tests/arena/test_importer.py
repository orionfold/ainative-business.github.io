# Copyright 2026 Manav Sehgal
# SPDX-License-Identifier: Apache-2.0
"""Tests for `fieldkit.arena.importer` — fixture-based walks + idempotency."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from fieldkit.arena.importer import (
    _bench_slug_from_results_json,
    _extract_bench_rows,
    _lane_kind_for_label,
    _lane_kind_for_manifest,
    _parse_frontmatter,
    import_artifacts,
    write_mirror_leaderboard,
)
from fieldkit.arena.store import ArenaStore


# ---------------------------------------------------------------------------
# unit tests — extractors
# ---------------------------------------------------------------------------


def test_bench_slug_from_results_path():
    p = Path("articles/picking-the-hermes-brain-on-spark/evidence/hermes_brain_results.json")
    assert (
        _bench_slug_from_results_json(p)
        == "picking-the-hermes-brain-on-spark:hermes_brain"
    )


def test_bench_slug_handles_stem_without_results_suffix():
    p = Path("articles/foo/evidence/raw.json")
    assert _bench_slug_from_results_json(p) == "foo:raw"


def test_extract_bench_rows_models_shape():
    rows = _extract_bench_rows(
        {
            "models": {
                "a": {
                    "core_pass_rate": 0.9,
                    "consistency": 0.85,
                    "tokens_per_sec": 80.0,
                    "latency": {"p50_s": 12.0, "p95_s": 30.0},
                    "telemetry": {"gpu_util_mean": 0.91, "unified_used_gb_max": 32.0},
                },
                "b": {"core_pass_rate": 0.78, "tokens_per_sec": 24.0},
            }
        }
    )
    assert len(rows) == 2
    a = next(r for r in rows if r["variant_label"] == "a")
    assert a["core_pass_rate"] == 0.9
    assert a["tok_per_sec"] == 80.0
    assert a["p50_s"] == 12.0
    assert a["gpu_util_mean"] == 0.91


def test_extract_bench_rows_cost_router_shape():
    rows = _extract_bench_rows(
        {
            "strategies": {
                "local-only": {},
                "cost-routed": {},
                "frontier-only": {},
            },
            "summary": {
                "majority_pass_rates": {
                    "local-only": 0.667,
                    "cost-routed": 0.917,
                    "frontier-only": 1.0,
                }
            },
        }
    )
    by_label = {r["variant_label"]: r for r in rows}
    assert set(by_label) == {"local-only", "cost-routed", "frontier-only"}
    assert by_label["frontier-only"]["core_pass_rate"] == 1.0


def test_extract_bench_rows_vertical_router_shape():
    rows = _extract_bench_rows(
        {
            "per_vertical_quality": {
                "patent": {"pass_rate": 0.8},
                "legal": {"pass_rate": 0.8},
            },
            "summary": {
                "vertical_pass_rates": {"patent": 0.8, "legal": 0.8, "medical": 1.0}
            },
        }
    )
    labels = {r["variant_label"] for r in rows}
    assert labels == {"patent", "legal", "medical"}


def test_extract_bench_rows_lanes_shape():
    # H2 serving-lane bakeoff uses `lanes` as top key
    rows = _extract_bench_rows(
        {
            "lanes": {
                "nim-nemotron": {"tokens_per_sec": 27.7},
                "llama-qwen3-moe": {"tokens_per_sec": 88.0},
            }
        }
    )
    assert len(rows) == 2
    assert {r["variant_label"] for r in rows} == {"nim-nemotron", "llama-qwen3-moe"}


def test_extract_bench_rows_unknown_shape_returns_empty():
    assert _extract_bench_rows({"unknown": 1}) == []
    assert _extract_bench_rows([1, 2, 3]) == []
    assert _extract_bench_rows("nope") == []


def test_lane_kind_for_manifest_mappings():
    assert _lane_kind_for_manifest("quant", {"class": "gguf"}) == "LlamaServerLane"
    assert _lane_kind_for_manifest("quant", {"class": "nvfp4"}) == "VLLMLane"
    assert _lane_kind_for_manifest("lora", {}) == "LoRAMerged"
    assert _lane_kind_for_manifest("harness", {}) == "HarnessConfig"
    assert _lane_kind_for_manifest("skill", {}) == "SkillBundle"
    assert _lane_kind_for_manifest("notebook", {}) == "NotebookPair"
    assert _lane_kind_for_manifest("bench", {}) == "BenchSpec"


def test_lane_kind_for_label_mappings():
    assert _lane_kind_for_label("nim-incumbent") == "NIMLane"
    assert _lane_kind_for_label("qwen3-30b-moe-vllm-fp8") == "VLLMLane"
    assert _lane_kind_for_label("qwen3-30b-moe-llamacpp-q4km") == "LlamaServerLane"
    assert _lane_kind_for_label("something-else") == "LlamaServerLane"  # default


# ---------------------------------------------------------------------------
# end-to-end tests — fixture repo
# ---------------------------------------------------------------------------


def _write(p: Path, text: str) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


@pytest.fixture
def fixture_repo(tmp_path):
    """A miniature repo that exercises every walk."""
    root = tmp_path / "repo"
    # Manifest fixtures
    _write(
        root / "src/content/artifacts/foo-gguf.yaml",
        "slug: foo-gguf\n"
        "kind: quant\n"
        "class: gguf\n"
        "base_model: orgs/foo-base\n"
        "hf_repo: Orionfold/foo-GGUF\n"
        "variants: [Q4_K_M, Q5_K_M]\n"
        "recommended_variant: Q5_K_M\n",
    )
    _write(
        root / "src/content/artifacts/foo-harness.yaml",
        "slug: foo-harness\nkind: harness\nclass: agent-harness\nbase_model: x\n"
        "hf_repo: Orionfold/foo-harness\nvariants: []\n",
    )
    # Article fixtures
    _write(
        root / "articles/foo-piece/article.md",
        "---\n"
        "title: Foo Piece\n"
        "date: 2026-05-28\n"
        "series: Cockpit\n"
        "stage: agentic\n"
        "summary: Sample piece.\n"
        "customer_linked: true\n"
        "fieldkit_modules: [arena]\n"
        "---\n\n"
        "Body.\n",
    )
    _write(
        root / "articles/upcoming-piece/article.md",
        "---\n"
        "title: Upcoming\n"
        "status: upcoming\n"
        "series: Cockpit\n"
        "---\n\nDraft.\n",
    )
    # Bench-results fixtures
    _write(
        root / "articles/foo-piece/evidence/foo_results.json",
        json.dumps(
            {
                "models": {
                    "lane-a": {"core_pass_rate": 0.8, "tokens_per_sec": 50.0},
                    "lane-b": {"core_pass_rate": 0.6, "tokens_per_sec": 12.0},
                }
            }
        ),
    )
    # Notebook export fixtures
    _write(
        root / "notebooks/foo/exports/builder/chart.png",
        "fake-png-bytes",
    )
    _write(
        root / "notebooks/foo/exports/user/chart.png",
        "fake-png-bytes",
    )
    # Brain-bakeoff seed
    _write(
        root / "articles/picking-the-hermes-brain-on-spark/article.md",
        "---\n"
        "title: Picking the Hermes Brain\n"
        "date: 2026-05-28\n"
        "series: Harnesses\n"
        "stage: agentic\n"
        "---\n\nbody\n",
    )
    _write(
        root / "articles/picking-the-hermes-brain-on-spark/evidence/hermes_brain_results.json",
        json.dumps(
            {
                "models": {
                    "qwen3-30b-moe-llamacpp-q4km": {
                        "core_pass_rate": 0.9,
                        "consistency": 0.9,
                        "tokens_per_sec": 83.5,
                        "runs": 5,
                    },
                    "nim-incumbent": {
                        "core_pass_rate": 0.78,
                        "tokens_per_sec": 23.9,
                        "runs": 5,
                    },
                }
            }
        ),
    )
    return root


@pytest.fixture
def no_hermes(monkeypatch):
    """Suppress the host-side `~/.hermes/config.yaml` walk so fixture tests
    are deterministic regardless of the developer's Spark state."""
    import fieldkit.arena.importer as imp

    monkeypatch.setattr(imp, "_walk_hermes_config", lambda *a, **kw: (0, []))


def test_import_artifacts_dry_run(fixture_repo, tmp_path, no_hermes):
    report = import_artifacts(
        repo_root=fixture_repo,
        db_path=tmp_path / "should-not-be-used.db",
        dry_run=True,
        refresh_hf=False,
        write_mirror=False,
    )
    # 2 quant variants + 1 nav harness + 2 brain-bakeoff lanes = 5
    assert report.lanes == 5
    # foo_results (2) + brain (2) = 4
    assert report.bench_results == 4
    assert report.article_index == 3  # foo-piece + upcoming-piece + brain article
    assert report.notebook_export == 2
    assert report.leaderboard_rows == 2
    assert report.hf_meta > 0  # HF cache rows always land (cache-only mode)


def test_import_artifacts_writes_db(fixture_repo, tmp_path, no_hermes):
    db = tmp_path / "arena.db"
    report = import_artifacts(
        repo_root=fixture_repo,
        db_path=db,
        dry_run=False,
        refresh_hf=False,
        write_mirror=False,
    )
    assert db.is_file()
    conn = sqlite3.connect(str(db))
    conn.row_factory = sqlite3.Row
    assert conn.execute("SELECT COUNT(*) FROM lanes").fetchone()[0] == report.lanes
    assert (
        conn.execute("SELECT COUNT(*) FROM article_index").fetchone()[0]
        == report.article_index
    )
    # Upcoming article is preserved with status='upcoming'
    row = conn.execute(
        "SELECT status FROM article_index WHERE slug='upcoming-piece'"
    ).fetchone()
    assert row["status"] == "upcoming"
    conn.close()


def test_importer_is_idempotent_on_second_run(fixture_repo, tmp_path, no_hermes):
    db = tmp_path / "arena.db"
    first = import_artifacts(
        repo_root=fixture_repo,
        db_path=db,
        dry_run=False,
        refresh_hf=False,
        write_mirror=False,
    )
    second = import_artifacts(
        repo_root=fixture_repo,
        db_path=db,
        dry_run=False,
        refresh_hf=False,
        write_mirror=False,
    )
    # The gate per spec M2 validation: identical counts.
    assert first.lanes == second.lanes
    assert first.bench_results == second.bench_results
    assert first.article_index == second.article_index
    assert first.hf_meta == second.hf_meta
    assert first.notebook_export == second.notebook_export
    assert first.leaderboard_rows == second.leaderboard_rows


def test_mirror_leaderboard_writes_non_empty(fixture_repo, tmp_path, no_hermes):
    db = tmp_path / "arena.db"
    import_artifacts(
        repo_root=fixture_repo,
        db_path=db,
        dry_run=False,
        refresh_hf=False,
        write_mirror=True,
    )
    out = fixture_repo / "src/data/arena-mirror/leaderboard.json"
    assert out.is_file()
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["schema_version"] == 1
    assert "rows" in payload
    assert len(payload["rows"]) == 2  # the two brain-bakeoff lanes


def test_parse_frontmatter_handles_no_frontmatter(tmp_path):
    p = tmp_path / "x.md"
    p.write_text("no frontmatter here", encoding="utf-8")
    assert _parse_frontmatter(p) is None


def test_parse_frontmatter_handles_malformed_yaml(tmp_path):
    p = tmp_path / "x.md"
    p.write_text("---\n: : not yaml\n---\n", encoding="utf-8")
    # Should not raise — returns None or empty dict on malformed YAML
    result = _parse_frontmatter(p)
    assert result is None or result == {}


def test_no_chat_content_ends_up_in_mirror_leaderboard(fixture_repo, tmp_path, no_hermes):
    """Sanity gate ahead of M6: even at M2 the leaderboard JSON must not
    leak chat content. (M2 doesn't write any chat content yet — but the
    mirror writer's shape should make that impossible by construction.)"""
    db = tmp_path / "arena.db"
    import_artifacts(
        repo_root=fixture_repo,
        db_path=db,
        dry_run=False,
        refresh_hf=False,
        write_mirror=True,
    )
    out = fixture_repo / "src/data/arena-mirror/leaderboard.json"
    payload = json.loads(out.read_text(encoding="utf-8"))
    # No row should expose anything chat-shaped — only the 9 leaderboard cols
    expected_keys = {
        "bench_id",
        "lane_id",
        "manifest_slug",
        "n_runs",
        "mean_score",
        "median_tok_per_s",
        "mean_ttft_ms",
        "human_pref_winrate",
        "last_run_at",
    }
    for row in payload["rows"]:
        assert set(row.keys()) == expected_keys
