# Copyright 2026 Manav Sehgal
# SPDX-License-Identifier: Apache-2.0
"""Tests for the `GET /api/sft-progress` endpoint (dogfood AF — live SFT feed).

The live SFT-training feed — a read-only parse of a NeMo ``p65`` driver log +
run-dir into iter/max, the loss curve, iter/s, ETA, and peak GPU memory. Closes
the AF-2 blind spot for the SFT stage. No arena.db read, no schema bump: the
endpoint parses a log under ``FK_ARENA_SFT_DIR`` and degrades to
``{available: false}`` when no training log exists, so the pane paints a clean
empty state. The merge/export driver log is deliberately excluded (no iters).
"""

from __future__ import annotations

from pathlib import Path

import pytest

fastapi = pytest.importorskip("fastapi")

from fastapi.testclient import TestClient  # noqa: E402

from fieldkit.arena.server import create_app  # noqa: E402

# One iter line + a peak-mem line, byte-shaped like real Megatron stdout.
_ITER = (
    " [2026-06-04 20:57:{ss}] iteration      {it:>3}/{mx:>5} | consumed samples: "
    "{cs} | elapsed time per iteration (ms): {ms} | learning rate: 9.9E-05 | "
    "global batch size:    16 | lm loss: {loss} | grad norm: 1.3 |"
)
_MEM = (
    "[Rank 0] (after 1 iterations) memory (GB) | mem-allocated-gigabytes: 16.6 | "
    "mem-max-reserved-gigabytes: 25.4 | mem-alloc-retires: 0 |"
)


def _log_lines(n: int, max_iters: int = 100, done: bool = False) -> str:
    lines = [
        "Starting training loop at iteration 0",
        _MEM,
    ]
    for i in range(1, n + 1):
        loss = f"{2.0 - i * 0.05:.6f}E+00"
        lines.append(
            _ITER.format(ss=40 + i, it=i, mx=max_iters, cs=i * 16, ms="4500.0", loss=loss)
        )
    if done:
        lines.append("[after training is done] datetime: 2026-06-04 21:00:00 ")
    return "\n".join(lines) + "\n"


def _write_log(sft_dir: Path, name: str, text: str) -> Path:
    logs = sft_dir / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    p = logs / name
    p.write_text(text)
    return p


def test_sft_progress_parses_running(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("FK_ARENA_SFT_DIR", str(tmp_path))
    _write_log(tmp_path, "full-driver.log", _log_lines(40))
    app = create_app(repo_root=tmp_path, telemetry_interval=2.0)
    with TestClient(app) as client:
        body = client.get("/api/sft-progress").json()
    assert body["available"] is True
    assert body["kind"] == "sft"
    assert body["source"] == "full-driver.log"
    rep = body["report"]
    assert rep["status"] == "running"
    assert rep["latest_iter"] == 40
    assert rep["max_iters"] == 100
    assert rep["peak_mem_gb"] == 25.4
    assert rep["iter_per_s"] == pytest.approx(1000.0 / 4500.0, rel=1e-3)
    assert rep["eta_s"] is not None and rep["eta_s"] > 0
    assert len(rep["loss_series"]) == 40
    # loss descends
    assert rep["loss_series"][0]["loss"] > rep["loss_series"][-1]["loss"]


def test_sft_progress_done_marker(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("FK_ARENA_SFT_DIR", str(tmp_path))
    _write_log(tmp_path, "full-driver.log", _log_lines(100, done=True))
    # a checkpoint dir under runs-full
    (tmp_path / "runs-full" / "iter_0000050").mkdir(parents=True)
    (tmp_path / "runs-full" / "iter_0000100").mkdir(parents=True)
    app = create_app(repo_root=tmp_path, telemetry_interval=2.0)
    with TestClient(app) as client:
        rep = client.get("/api/sft-progress").json()["report"]
    assert rep["status"] == "done"
    assert rep["latest_iter"] == 100
    assert rep["checkpoints"] == [50, 100]


def test_sft_progress_absent_is_clean_empty(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("FK_ARENA_SFT_DIR", str(tmp_path))
    app = create_app(repo_root=tmp_path, telemetry_interval=2.0)
    with TestClient(app) as client:
        r = client.get("/api/sft-progress")
    assert r.status_code == 200
    assert r.json() == {"available": False, "kind": "sft", "runs": []}


def test_sft_progress_excludes_merge_log(tmp_path: Path, monkeypatch) -> None:
    # The merge/export driver log shares logs/ but has no iters — it must not
    # become the auto-followed run nor appear in the history dropdown.
    monkeypatch.setenv("FK_ARENA_SFT_DIR", str(tmp_path))
    _write_log(tmp_path, "full-driver.log", _log_lines(100, done=True))
    _write_log(tmp_path, "merge-driver.log", "Merge complete\nExporting...\n")
    import os
    # make merge-driver.log strictly newest by mtime
    os.utime(tmp_path / "logs" / "merge-driver.log", (9_000_000_000, 9_000_000_000))
    app = create_app(repo_root=tmp_path, telemetry_interval=2.0)
    with TestClient(app) as client:
        body = client.get("/api/sft-progress").json()
        assert body["source"] == "full-driver.log"  # NOT merge-driver.log
        assert [r["source"] for r in body["runs"]] == ["full-driver.log"]
        # and it can't be selected explicitly either
        picked = client.get("/api/sft-progress",
                            params={"source": "merge-driver.log"}).json()
        assert picked["available"] is False


def test_sft_progress_history_and_source_select(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("FK_ARENA_SFT_DIR", str(tmp_path))
    _write_log(tmp_path, "smoke-driver.log", _log_lines(10, max_iters=10, done=True))
    full = _write_log(tmp_path, "full-driver.log", _log_lines(100, done=True))
    import os
    os.utime(full, (9_000_000_000, 9_000_000_000))  # full newest
    app = create_app(repo_root=tmp_path, telemetry_interval=2.0)
    with TestClient(app) as client:
        body = client.get("/api/sft-progress").json()
        assert body["source"] == "full-driver.log"
        sources = [r["source"] for r in body["runs"]]
        assert sources == ["full-driver.log", "smoke-driver.log"]
        picked = client.get("/api/sft-progress",
                            params={"source": "smoke-driver.log"}).json()
        assert picked["source"] == "smoke-driver.log"
        assert picked["report"]["latest_iter"] == 10


def test_sft_progress_source_traversal_rejected(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("FK_ARENA_SFT_DIR", str(tmp_path))
    _write_log(tmp_path, "full-driver.log", _log_lines(100, done=True))
    app = create_app(repo_root=tmp_path, telemetry_interval=2.0)
    with TestClient(app) as client:
        # a crafted source falls back to newest (never escapes logs/)
        body = client.get("/api/sft-progress",
                          params={"source": "../../../etc/passwd"}).json()
    assert body.get("available") is False or body.get("source") == "full-driver.log"
