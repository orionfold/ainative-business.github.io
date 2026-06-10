"""Tests for the Advisor preflight receipt helpers.

The endpoint is a thin FastAPI wrapper around these helpers. Keep these tests
lifespan-free: they pin the read-only evidence parsing contract without starting
the full Arena sidecar.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from fieldkit.arena.server import (  # noqa: E402
    _advisor_lane_readiness,
    _advisor_preflight_command,
    _list_advisor_preflight_reports,
    _newest_advisor_preflight_report,
    _resolve_advisor_preflight_report,
    _summarize_advisor_packets,
    _summarize_advisor_results,
)


def _write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(row) for row in rows) + "\n")


def _write_receipt(
    repo_root: Path,
    *,
    report_name: str = "advisor-preflight-v0.1.json",
    results: bool = False,
) -> Path:
    base = repo_root / "evidence" / "orionfold-advisor"
    prompts = base / "advisor-preflight-v0.1.prompts.jsonl"
    results_path = base / "advisor-preflight-v0.1.results.jsonl"
    _write_jsonl(
        prompts,
        [
            {
                "task_id": "advisor-cited-factual-qa-0003",
                "family": "cited_factual_qa",
                "split": "heldout",
                "question": "Which source?",
                "expected_behavior": "answer",
                "expected_source_ids": ["article_autoresearchbench_on_spark"],
                "retrieved_sources": [
                    {"source_id": "article_autoresearchbench_on_spark"},
                    {"source_id": "spec_index"},
                ],
                "messages": [{"role": "user", "content": "private prompt body"}],
            },
            {
                "task_id": "advisor-missing-source-refusal-0100",
                "family": "missing_source_refusal",
                "split": "heldout",
                "question": "What is private?",
                "expected_behavior": "refuse",
                "expected_source_ids": [],
                "retrieved_sources": [],
                "messages": [{"role": "user", "content": "private prompt body"}],
            },
        ],
    )
    if results:
        _write_jsonl(
            results_path,
            [
                {
                    "task_id": "advisor-cited-factual-qa-0003",
                    "family": "cited_factual_qa",
                    "expected_behavior": "answer",
                    "expected_source_ids": ["article_autoresearchbench_on_spark"],
                    "output": "model output stays private",
                    "score": {
                        "citation_ok": True,
                        "refusal_ok": True,
                        "route_ok": True,
                        "thinking_leak": False,
                        "private_state_risk": False,
                        "cited_source_ids": ["article_autoresearchbench_on_spark"],
                        "passed": True,
                    },
                },
                {
                    "task_id": "advisor-missing-source-refusal-0100",
                    "family": "missing_source_refusal",
                    "expected_behavior": "refuse",
                    "expected_source_ids": [],
                    "output": "model output stays private",
                    "score": {
                        "citation_ok": False,
                        "refusal_ok": False,
                        "route_ok": True,
                        "thinking_leak": False,
                        "private_state_risk": False,
                        "cited_source_ids": ["spec_index"],
                        "passed": False,
                    },
                },
            ],
        )
    report = {
        "generated": "2026-06-09",
        "version": "v0.1",
        "model_target": "Qwen/Qwen2.5-7B-Instruct-GGUF",
        "mode": "endpoint" if results else "prompt_packets",
        "prompt_path": prompts.relative_to(repo_root).as_posix(),
        "results_path": results_path.relative_to(repo_root).as_posix() if results else None,
        "row_count": 2,
        "families": {"cited_factual_qa": 1, "missing_source_refusal": 1},
        "gate": {
            "name": "advisor-generator-preflight",
            "status": "scored" if results else "not_run",
            "passed": False,
            "threshold": "all selected rows pass",
        },
    }
    path = base / report_name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report))
    return path


def test_advisor_preflight_absent_helpers_are_empty(tmp_path: Path) -> None:
    assert _list_advisor_preflight_reports(tmp_path) == []
    newest = _newest_advisor_preflight_report(tmp_path)
    assert newest == tmp_path / "evidence" / "orionfold-advisor" / "advisor-preflight-v0.1.json"
    assert not newest.exists()


def test_advisor_preflight_summarizes_packets_without_prompt_bodies(tmp_path: Path) -> None:
    report_path = _write_receipt(tmp_path)
    report = json.loads(report_path.read_text())
    packets = _summarize_advisor_packets(tmp_path, report["prompt_path"])
    results = _summarize_advisor_results(tmp_path, report["results_path"])

    assert len(packets) == 2
    assert packets[0]["task_id"] == "advisor-cited-factual-qa-0003"
    assert packets[0]["source_count"] == 2
    assert "messages" not in packets[0]
    assert results == {"available": False, "row_count": 0, "path": None}


def test_advisor_preflight_summarizes_scored_rows(tmp_path: Path) -> None:
    report_path = _write_receipt(tmp_path, results=True)
    report = json.loads(report_path.read_text())
    results = _summarize_advisor_results(tmp_path, report["results_path"])

    assert results["available"] is True
    assert results["row_count"] == 2
    assert results["failures"] == 1
    assert results["passed"] is False
    assert results["rows"][0]["passed"] is True
    assert results["rows"][0]["cited_source_ids"] == ["article_autoresearchbench_on_spark"]
    assert results["rows"][1]["passed"] is False
    assert "output" not in results["rows"][0]


def test_advisor_preflight_history_and_source_select(tmp_path: Path) -> None:
    old = _write_receipt(tmp_path, report_name="advisor-preflight-v0.1.json")
    new = _write_receipt(tmp_path, report_name="advisor-preflight-qwen25.json", results=True)

    os.utime(old, (1000.0, 1000.0))
    os.utime(new, (2000.0, 2000.0))

    assert _newest_advisor_preflight_report(tmp_path).name == "advisor-preflight-qwen25.json"
    assert [r["source"] for r in _list_advisor_preflight_reports(tmp_path)] == [
        "advisor-preflight-qwen25.json",
        "advisor-preflight-v0.1.json",
    ]
    picked = _resolve_advisor_preflight_report(tmp_path, "advisor-preflight-v0.1.json")
    assert picked is not None
    assert picked.name == "advisor-preflight-v0.1.json"
    assert json.loads(picked.read_text())["mode"] == "prompt_packets"


def test_advisor_preflight_source_traversal_rejected(tmp_path: Path) -> None:
    _write_receipt(tmp_path)
    (tmp_path / "secret.json").write_text(json.dumps({"leak": True}))
    assert _resolve_advisor_preflight_report(tmp_path, "../../secret.json") is None


def test_advisor_preflight_malformed_degrades(tmp_path: Path) -> None:
    path = tmp_path / "evidence" / "orionfold-advisor" / "advisor-preflight-v0.1.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{not valid json")
    runs = _list_advisor_preflight_reports(tmp_path)
    assert runs == [{"source": "advisor-preflight-v0.1.json", "mtime": path.stat().st_mtime, "status": "unreadable"}]


def test_advisor_lane_readiness_requires_resolved_live_lane() -> None:
    assert _advisor_lane_readiness({"source": "none", "base_url": "", "model": ""}) == {
        "ready": False,
        "reason": "no active serving lane discovered",
        "model": None,
        "base_url": None,
        "port": None,
        "source": "none",
        "drift": None,
    }
    ambiguous = _advisor_lane_readiness({"source": "ambiguous", "base_url": "", "model": ""})
    assert ambiguous["ready"] is False
    assert "select one" in ambiguous["reason"]
    hint = _advisor_lane_readiness(
        {"source": "hermes-hint", "base_url": "http://127.0.0.1:8091/v1", "model": "configured"}
    )
    assert hint["ready"] is False
    assert "Hermes config hint" in hint["reason"]


def test_advisor_lane_readiness_accepts_discovered_or_registry_lane() -> None:
    discovered = _advisor_lane_readiness(
        {
            "source": "discovered",
            "base_url": "http://127.0.0.1:8091/v1",
            "model": "qwen.gguf",
            "port": 8091,
        }
    )
    assert discovered["ready"] is True
    assert discovered["model"] == "qwen.gguf"
    assert discovered["port"] == 8091


def test_advisor_preflight_command_threads_active_lane(tmp_path: Path) -> None:
    script = tmp_path / "scripts" / "orionfold_advisor" / "preflight.py"
    script.parent.mkdir(parents=True)
    script.write_text("#!/usr/bin/env python3\n")

    cmd = _advisor_preflight_command(
        tmp_path,
        {
            "source": "registry",
            "base_url": "http://127.0.0.1:8091/v1",
            "model": "qwen25.gguf",
            "port": 8091,
        },
    )

    assert cmd[-4:] == [
        "--endpoint",
        "http://127.0.0.1:8091/v1",
        "--model",
        "qwen25.gguf",
    ]


def test_advisor_preflight_command_nothink_uses_suffixed_evidence(tmp_path: Path) -> None:
    script = tmp_path / "scripts" / "orionfold_advisor" / "preflight.py"
    script.parent.mkdir(parents=True)
    script.write_text("#!/usr/bin/env python3\n")

    lane = {
        "source": "registry",
        "base_url": "http://127.0.0.1:8000/v1",
        "model": "nvidia/nemotron-nano-9b-v2",
        "port": 8000,
    }
    cmd = _advisor_preflight_command(tmp_path, lane, "off")

    assert "--reasoning-mode" in cmd
    assert cmd[cmd.index("--reasoning-mode") + 1] == "off"
    base = tmp_path / "evidence" / "orionfold-advisor" / "advisor-preflight-v0.1-nothink"
    assert cmd[cmd.index("--prompts") + 1] == f"{base}.prompts.jsonl"
    assert cmd[cmd.index("--results") + 1] == f"{base}.results.jsonl"
    assert cmd[cmd.index("--report") + 1] == f"{base}.json"
    # The default run must stay untouched — no suffixed paths, no mode flag.
    assert "--reasoning-mode" not in _advisor_preflight_command(tmp_path, lane)


# --- corpus pane (spec §10, AD-AE-11) + routing surface (spec §12, AD-AE-16) --


def _write_corpus_evidence(repo_root: Path) -> Path:
    base = repo_root / "evidence" / "orionfold-advisor"
    base.mkdir(parents=True, exist_ok=True)
    _write_jsonl(
        base / "public-corpus-manifest.jsonl",
        [
            {"source_id": "a", "source_class": "field_note", "source_role": "article"},
            {"source_id": "b", "source_class": "field_note", "source_role": "article"},
            {"source_id": "c", "source_class": "product_doc", "source_role": "product"},
        ],
    )
    recall = {
        "generated": "2026-06-10",
        "method": "local-bm25-provenance-chunks",
        "source_count": 3,
        "chunk_count": 9,
        "row_count": 7,
        "manifest_sha256_12": "abc123def456",
        "bench_sha256_12": "fed654cba321",
        "metrics": {"source_recall": {"@1": 0.9, "@5": 1.0}, "source_misses_at_5": []},
        "by_split": {"heldout": {"source_recall": {"@5": 1.0}}},
        "gate": {"passed": True, "threshold": ">= 0.90"},
    }
    (base / "rag-recall-v0.1.json").write_text(json.dumps(recall))
    (base / "rag-recall-v0.1-cortex.json").write_text(json.dumps(recall))
    (base / "advisor-corpus-swap-fixture-v0.1.json").write_text(json.dumps(recall))
    (base / "advisor-sft-corpus-v0.2.json").write_text(
        json.dumps(
            {
                "version": "v0.2",
                "generated": "2026-06-10",
                "rows_kept": 827,
                "rejects": 48,
                "refusal_share": 0.3,
                "corpus_sha256_12": "e096aa6b12cc",
                "manifest_sha256_12": "abc123def456",
                "bench_sha256_12": "fed654cba321",
                "teacher": {"model": "30B-teacher"},
            }
        )
    )
    return base


def test_advisor_corpus_projection_reads_pack_state(tmp_path: Path) -> None:
    from fieldkit.arena.server import _advisor_corpus_projection

    _write_corpus_evidence(tmp_path)
    proj = _advisor_corpus_projection(tmp_path)
    assert proj["available"] is True
    assert proj["manifest"]["source_count"] == 3
    assert proj["manifest"]["by_class"] == {"field_note": 2, "product_doc": 1}
    assert proj["recall_bm25"]["gate_passed"] is True
    assert proj["recall_live"]["source_recall"]["@5"] == 1.0
    assert proj["recall_live"]["heldout_source_recall"]["@5"] == 1.0
    assert proj["swap_fixture"]["available"] is True
    assert proj["sft_corpora"][0]["rows_kept"] == 827
    assert proj["sft_corpora"][0]["teacher_model"] == "30B-teacher"


def test_advisor_corpus_projection_degrades_on_fresh_box(tmp_path: Path) -> None:
    from fieldkit.arena.server import _advisor_corpus_projection

    proj = _advisor_corpus_projection(tmp_path)
    assert proj["available"] is False
    assert proj["recall_bm25"]["available"] is False
    assert proj["sft_corpora"] == []


def test_advisor_routing_projection_reads_bakeoff_and_ledger(tmp_path: Path) -> None:
    from fieldkit.arena.server import _advisor_routing_projection

    base = tmp_path / "evidence" / "orionfold-advisor"
    base.mkdir(parents=True, exist_ok=True)
    (base / "advisor-route-bakeoff-v0.1.json").write_text(
        json.dumps(
            {
                "generated": "2026-06-10",
                "version": "v0.1",
                "slice": {"rows": 28},
                "t1": {"pass": 28},
                "t2_status": "skipped",
                "configs": {"t1-only": {"pass": 28, "pass_rate": 1.0, "hosted_cost_usd": 0.0}},
                "router": {"revision": 2, "policy": "deterministic observables-only"},
                "t4_governance": {
                    "allowed_models": ["anthropic/claude-haiku-4.5"],
                    "cap_usd": 1.0,
                    "data_policy": "public-corpus packets only",
                },
            }
        )
    )
    _write_jsonl(
        base / "advisor-route-bakeoff-v0.1.ledger.jsonl",
        [
            {
                "task_id": "advisor-0082",
                "route": {"escalate": True, "trigger": "citation_rank_sanity"},
                "escalations": {
                    "t1+t4": {
                        "model": "anthropic/claude-haiku-4.5",
                        "cost_usd": 0.0033,
                        "score": {"passed": True},
                    }
                },
            },
            {
                "task_id": "advisor-0090",
                "route": {"escalate": False, "hosted_egress_blocked": True},
            },
        ],
    )
    proj = _advisor_routing_projection(tmp_path)
    assert proj["available"] is True
    assert proj["configs"]["t1-only"]["pass"] == 28
    assert proj["governance"]["cap_usd"] == 1.0
    assert proj["private_state_blocked"] == 1
    assert len(proj["escalations"]) == 1
    esc = proj["escalations"][0]
    assert esc["task_id"] == "advisor-0082" and esc["trigger"] == "citation_rank_sanity"
    assert esc["tiers"][0]["model"] == "anthropic/claude-haiku-4.5"
    assert esc["tiers"][0]["passed"] is True


def test_advisor_routing_projection_degrades_without_receipt(tmp_path: Path) -> None:
    from fieldkit.arena.server import _advisor_routing_projection

    proj = _advisor_routing_projection(tmp_path)
    assert proj == {"available": False, "kind": "advisor_routing"}


def test_advisor_receipt_endpoint_reads_publish_receipt(tmp_path: Path) -> None:
    from fieldkit.arena.server import _advisor_read_json, _advisor_preflight_dir

    base = tmp_path / "evidence" / "orionfold-advisor"
    base.mkdir(parents=True, exist_ok=True)
    assert _advisor_read_json(_advisor_preflight_dir(tmp_path), "advisor-publish-receipt-v0.1.json") is None
    (base / "advisor-publish-receipt-v0.1.json").write_text(
        json.dumps({"kind": "advisor_publish_receipt", "decision": {"verdict": "PROMOTED"}})
    )
    receipt = _advisor_read_json(_advisor_preflight_dir(tmp_path), "advisor-publish-receipt-v0.1.json")
    assert receipt["decision"]["verdict"] == "PROMOTED"
