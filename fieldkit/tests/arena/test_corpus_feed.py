"""Tests for the corpus-synth live feed (AE-6 / AF-2).

Two surfaces: the producer-side heartbeat stamper
(``fieldkit.arena.lane.write_corpus_progress``) that the in-CC-session synth
calls after each batch, and the consumer-side ``GET /api/corpus-progress`` +
the build-spine corpus stage that reads it. The contract: written/target +
accumulating tier/topic mix from the live ``out.jsonl`` against the
deterministic ``queue.jsonl``, the file-polled auto-newest transport (AF-9/AF-10
one dir over), and a clean empty state on a fresh box — never importing skill
code, never touching arena.db.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from fieldkit.arena.lane import write_corpus_progress

fastapi = pytest.importorskip("fastapi")

from fastapi.testclient import TestClient  # noqa: E402

from fieldkit.arena.server import create_app  # noqa: E402


def _queue(path: Path, n: int) -> None:
    fams = ["A1", "A2", "B1"]
    path.write_text(
        "\n".join(
            json.dumps({"row_idx": i, "family": fams[i % 3], "prompt": "x"})
            for i in range(n)
        )
    )


def _out(path: Path, n: int) -> None:
    path.write_text(
        "\n".join(
            json.dumps({"row_idx": i, "response": "<think>x</think>42"})
            for i in range(n)
        )
    )


def _app(tmp_path: Path):
    return create_app(
        repo_root=tmp_path, db=str(tmp_path / "no-such.db"), telemetry_interval=2.0
    )


# --- producer: write_corpus_progress ---------------------------------------


def test_writer_counts_written_target_and_family_mix(tmp_path: Path) -> None:
    q, o = tmp_path / "queue.jsonl", tmp_path / "out.jsonl"
    _queue(q, 120)
    _out(o, 37)
    cdir = tmp_path / "evidence" / "astrodynamics"
    p = write_corpus_progress(
        o, q, corpus_dir=cdir, run_label="patent-prod", vertical="patent",
        batch_size=25, status="running", verified=36, verify_fail=1,
    )
    assert p is not None and p.name == "corpus-progress-patent-prod.json"
    rep = json.loads(p.read_text())
    assert rep["written"] == 37
    assert rep["target"] == 120
    # 120 - 37 = 83 remaining → ceil(83/25) = 4 batches.
    assert rep["eta_batches"] == 4
    # family mix tallied from the queue's row_idx → family map.
    assert rep["family_mix"] == {"A1": 13, "A2": 12, "B1": 12}
    assert rep["verify_fail"] == 1
    assert rep["kind"] == "corpus_run"


def test_writer_without_queue_has_no_target(tmp_path: Path) -> None:
    # A heartbeat with no queue still reports written rows (target/eta blank).
    o = tmp_path / "out.jsonl"
    _out(o, 5)
    cdir = tmp_path / "ev"
    p = write_corpus_progress(o, corpus_dir=cdir, run_label="r")
    rep = json.loads(p.read_text())
    assert rep["written"] == 5
    assert rep["target"] is None
    assert rep["eta_batches"] is None


def test_writer_prefers_row_family_over_queue(tmp_path: Path) -> None:
    # When out rows carry `family` (post-merge), it wins over the queue lookup.
    o = tmp_path / "out.jsonl"
    o.write_text(
        "\n".join(json.dumps({"row_idx": i, "family": "Z9"}) for i in range(3))
    )
    p = write_corpus_progress(o, corpus_dir=tmp_path / "ev", run_label="r")
    assert json.loads(p.read_text())["family_mix"] == {"Z9": 3}


# --- consumer: /api/corpus-progress ----------------------------------------


def test_endpoint_empty_state_on_fresh_box(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("FK_ARENA_CORPUS_DIR", str(tmp_path / "no-corpus"))
    with TestClient(_app(tmp_path)) as client:
        r = client.get("/api/corpus-progress")
        assert r.status_code == 200
        body = r.json()
        assert body["available"] is False
        assert body["kind"] == "corpus"
        assert body["runs"] == []


def test_endpoint_serves_newest_heartbeat(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cdir = tmp_path / "evidence" / "astrodynamics"
    q, o = tmp_path / "queue.jsonl", tmp_path / "out.jsonl"
    _queue(q, 100)
    _out(o, 40)
    write_corpus_progress(o, q, corpus_dir=cdir, run_label="run1", batch_size=20)
    monkeypatch.setenv("FK_ARENA_CORPUS_DIR", str(cdir))
    with TestClient(_app(tmp_path)) as client:
        body = client.get("/api/corpus-progress").json()
        assert body["available"] is True
        rep = body["report"]
        assert rep["written"] == 40
        assert rep["target"] == 100
        assert rep["pct"] == 40
        assert rep["status"] == "running"
        assert body["source"] == "corpus-progress-run1.json"
        assert [run["source"] for run in body["runs"]] == ["corpus-progress-run1.json"]


def test_endpoint_source_pin_is_traversal_safe(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cdir = tmp_path / "evidence" / "astrodynamics"
    o = tmp_path / "out.jsonl"
    _out(o, 3)
    write_corpus_progress(o, corpus_dir=cdir, run_label="ok")
    monkeypatch.setenv("FK_ARENA_CORPUS_DIR", str(cdir))
    with TestClient(_app(tmp_path)) as client:
        # a crafted traversal source must not escape the dir → empty state
        bad = client.get("/api/corpus-progress?source=../../../etc/passwd").json()
        assert bad["available"] is False
        # a non-matching prefix is rejected too
        nope = client.get("/api/corpus-progress?source=av10-preflight.json").json()
        assert nope["available"] is False


# --- the build-spine corpus stage reads the feed live (AE-6 into AE-5) ------


def test_build_corpus_stage_lights_from_feed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "fieldkit.arena.server._read_hermes_lane", lambda hermes_path=None: None
    )
    monkeypatch.setenv("FK_ARENA_SCOUT_DIR", str(tmp_path / "no-scout"))
    monkeypatch.setenv("FK_ARENA_SFT_DIR", str(tmp_path / "no-sft"))
    cdir = tmp_path / "evidence" / "astrodynamics"
    q, o = tmp_path / "queue.jsonl", tmp_path / "out.jsonl"
    _queue(q, 100)
    _out(o, 60)
    write_corpus_progress(
        o, q, corpus_dir=cdir, run_label="run1", batch_size=20,
        status="running", verify_fail=0,
    )
    monkeypatch.setenv("FK_ARENA_CORPUS_DIR", str(cdir))
    with TestClient(_app(tmp_path)) as client:
        stages = {s["key"]: s for s in client.get("/api/build").json()["stages"]}
        corpus = stages["corpus"]
        assert corpus["state"] == "active"
        assert corpus["source"] == "corpus-progress"
        assert "60/100 rows" in corpus["headline"]
        assert "verify ✓" in corpus["headline"]
