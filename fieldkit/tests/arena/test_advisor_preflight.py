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
