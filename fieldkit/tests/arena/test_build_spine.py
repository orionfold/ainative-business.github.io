"""Tests for the vertical-build spine endpoint (AE-5 / AF-1 — ``GET /api/build``).

The spine is a pure projection over signals the cockpit already has (the reward
report, the bench registry, the rl_run rows, the lane arbiter) plus an optional
``build-manifest.json``. These tests pin the assembly contract: eight stages in
pipeline order, the live-feed signals win, the manifest fills the no-feed stages
+ the gate annotations, and a fresh box degrades to ``pending`` rather than a 500
— never reading or writing arena.db schema.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

fastapi = pytest.importorskip("fastapi")

from fastapi.testclient import TestClient  # noqa: E402

from fieldkit.arena.server import create_app  # noqa: E402

_STAGE_KEYS = ["scout", "bench", "corpus", "sft", "smoke", "lane", "rlvr", "publish"]

_REWARD = {
    "model": "Qwen/Qwen3-8B",
    "status": "done",
    "boxed_rate": 1.0,
    "reward_rate_step0": 0.864,
    "gate_pass": True,
}


def _no_hermes(monkeypatch: pytest.MonkeyPatch) -> None:
    """Steer the resident-lane reader at nothing so the lane stage is
    deterministic regardless of the developer's local Spark state."""
    monkeypatch.setattr(
        "fieldkit.arena.server._read_hermes_lane",
        lambda hermes_path=None: None,
    )


def _no_scout(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Point the scout-presence probe at an empty dir (no /tmp/hf-scout leak)."""
    monkeypatch.setenv("FK_ARENA_SCOUT_DIR", str(tmp_path / "no-scout"))


def _no_sft(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Point the SFT-feed reader at an empty dir so the developer's real
    ``/home/nvidia/data`` run-root doesn't leak into a hermetic assertion."""
    monkeypatch.setenv("FK_ARENA_SFT_DIR", str(tmp_path / "no-sft"))


def _app(tmp_path: Path):
    return create_app(
        repo_root=tmp_path,
        db=str(tmp_path / "no-such.db"),
        telemetry_interval=2.0,
    )


def test_build_fresh_box_is_all_pending(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # No manifest, no feeds → 200 with eight stages in pipeline order, not a
    # 404/500. The stages with no signal on a clean box (corpus/smoke/lane/rlvr/
    # publish + the neutralized scout/sft) read pending; bench reflects the
    # machine-global registry, so it isn't asserted here.
    _no_hermes(monkeypatch)
    _no_scout(monkeypatch, tmp_path)
    _no_sft(monkeypatch, tmp_path)
    with TestClient(_app(tmp_path)) as client:
        r = client.get("/api/build")
        assert r.status_code == 200
        body = r.json()
        assert body["available"] is True
        assert body["manifest_present"] is False
        assert body["stages_total"] == 8
        assert [s["key"] for s in body["stages"]] == _STAGE_KEYS
        stages = {s["key"]: s for s in body["stages"]}
        for key in ("scout", "corpus", "smoke", "rlvr", "publish"):
            assert stages[key]["state"] == "pending", key
        # no resident config + no db → lane is pending (not falsely "active")
        assert stages["lane"]["state"] == "pending"


def test_build_live_reward_lights_smoke_stage(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The smoke stage reads the newest reward report live (no manifest needed):
    # a passing av10-preflight → done + the held-out headline + gate pass.
    _no_hermes(monkeypatch)
    _no_scout(monkeypatch, tmp_path)
    p = tmp_path / "evidence" / "astrodynamics" / "av10-preflight.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(_REWARD))
    with TestClient(_app(tmp_path)) as client:
        stages = {s["key"]: s for s in client.get("/api/build").json()["stages"]}
        smoke = stages["smoke"]
        assert smoke["state"] == "done"
        assert smoke["source"] == "reward-signal"
        assert "86%" in smoke["headline"]
        assert smoke["gate_state"] == "pass"
        assert "boxed 100%" in smoke["detail"]


def test_build_running_reward_marks_smoke_active(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _no_hermes(monkeypatch)
    _no_scout(monkeypatch, tmp_path)
    p = tmp_path / "evidence" / "astrodynamics" / "av10-preflight.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(dict(_REWARD, status="running", scored=3, total=8)))
    with TestClient(_app(tmp_path)) as client:
        stages = {s["key"]: s for s in client.get("/api/build").json()["stages"]}
        assert stages["smoke"]["state"] == "active"
        assert "3/8" in stages["smoke"]["headline"]


def test_build_manifest_fills_no_feed_stages_and_label(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The manifest owns the no-live-feed stages (scout/corpus/publish) + the
    # vertical label + the human-gate text; it must NOT clobber a live signal.
    _no_hermes(monkeypatch)
    _no_scout(monkeypatch, tmp_path)
    p = tmp_path / "evidence" / "astrodynamics" / "av10-preflight.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(_REWARD))
    manifest = {
        "vertical": "astrodynamics",
        "label": "Kepler",
        "updated": "2026-06-05",
        "stages": {
            "scout": {"state": "done", "headline": "Qwen3-8B locked", "gate_state": "pass"},
            "publish": {
                "state": "done",
                "headline": "Orionfold/Kepler-GGUF",
                "href": "https://huggingface.co/Orionfold/Kepler-GGUF",
                "gate_state": "pass",
            },
            # smoke is a LIVE stage — the manifest's bogus headline must be ignored
            # in favor of the reward report, but its gate annotation still applies.
            "smoke": {"headline": "SHOULD-NOT-WIN", "gate": "AV-10 preflight"},
        },
    }
    (tmp_path / "evidence" / "astrodynamics" / "build-manifest.json").write_text(
        json.dumps(manifest)
    )
    with TestClient(_app(tmp_path)) as client:
        body = client.get("/api/build").json()
        assert body["label"] == "Kepler"
        assert body["manifest_present"] is True
        stages = {s["key"]: s for s in body["stages"]}
        assert stages["scout"]["state"] == "done"
        assert stages["scout"]["headline"] == "Qwen3-8B locked"
        assert stages["publish"]["href"].endswith("Kepler-GGUF")
        # live smoke headline wins; manifest gate annotation still applied
        assert "86%" in stages["smoke"]["headline"]
        assert stages["smoke"]["headline"] != "SHOULD-NOT-WIN"
        assert stages["smoke"]["gate"] == "AV-10 preflight"


def test_build_manifest_bench_id_files_absent_stays_blank(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # astro-bench is registered (AE-11/S6), but when its JSONL is absent on this
    # box the bench stage must NOT fall back to an unrelated vertical's bench — it
    # stays blank so the manifest's headline fills it, rather than mislabeling the
    # card. (Point the astro root at an empty dir so the registry row is
    # unavailable regardless of the machine-global eval-benches tree.)
    _no_hermes(monkeypatch)
    _no_scout(monkeypatch, tmp_path)
    monkeypatch.setenv("FK_ARENA_BENCH_DIR", str(tmp_path / "no-bench-files"))
    manifest = {
        "vertical": "astrodynamics",
        "label": "Kepler",
        "bench_id": "astro-bench",
        "stages": {
            "bench": {"state": "done", "headline": "astro-bench v0.1 · 120+44"},
        },
    }
    (tmp_path / "evidence" / "astrodynamics").mkdir(parents=True, exist_ok=True)
    (tmp_path / "evidence" / "astrodynamics" / "build-manifest.json").write_text(
        json.dumps(manifest)
    )
    with TestClient(_app(tmp_path)) as client:
        stages = {s["key"]: s for s in client.get("/api/build").json()["stages"]}
        # the manifest's headline fills the blanked live stage
        assert stages["bench"]["headline"] == "astro-bench v0.1 · 120+44"
        assert "Patent" not in stages["bench"]["headline"]


def test_build_dir_env_override(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # FK_ARENA_BUILD_DIR relocates the manifest away from the evidence default.
    _no_hermes(monkeypatch)
    _no_scout(monkeypatch, tmp_path)
    alt = tmp_path / "alt-build"
    alt.mkdir()
    (alt / "build-manifest.json").write_text(
        json.dumps({"label": "Relocated", "stages": {}})
    )
    monkeypatch.setenv("FK_ARENA_BUILD_DIR", str(alt))
    with TestClient(_app(tmp_path)) as client:
        body = client.get("/api/build").json()
        assert body["label"] == "Relocated"
        assert body["manifest_present"] is True


def test_build_gate_cards_carry_consequence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # AE-7 — every gated stage ships a default ``gate_consequence`` (the cost of
    # holding), so the gate ledger has copy without a manifest.
    _no_hermes(monkeypatch)
    _no_scout(monkeypatch, tmp_path)
    _no_sft(monkeypatch, tmp_path)
    monkeypatch.setenv("FK_ARENA_CORPUS_DIR", str(tmp_path / "no-corpus"))
    with TestClient(_app(tmp_path)) as client:
        stages = {s["key"]: s for s in client.get("/api/build").json()["stages"]}
        for key in ("scout", "corpus", "sft", "smoke", "rlvr", "publish"):
            assert stages[key].get("gate"), key
            assert stages[key].get("gate_consequence"), key
        # bench + lane have no human gate → no consequence forced.
        assert stages["bench"].get("gate") is None


def test_build_manifest_overrides_gate_consequence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The operator can override the gate copy via the manifest (AE-7 + AE-5
    # ownership: gate annotations are always manifest-owned).
    _no_hermes(monkeypatch)
    _no_scout(monkeypatch, tmp_path)
    _no_sft(monkeypatch, tmp_path)
    monkeypatch.setenv("FK_ARENA_CORPUS_DIR", str(tmp_path / "no-corpus"))
    p = tmp_path / "evidence" / "astrodynamics" / "build-manifest.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(
        json.dumps(
            {
                "stages": {
                    "publish": {
                        "gate_state": "hold",
                        "gate_consequence": "Custom hold reason.",
                    }
                }
            }
        )
    )
    with TestClient(_app(tmp_path)) as client:
        stages = {s["key"]: s for s in client.get("/api/build").json()["stages"]}
        assert stages["publish"]["gate_state"] == "hold"
        assert stages["publish"]["gate_consequence"] == "Custom hold reason."


# ---------------------------------------------------------------------------
# AE-8 — bench provenance card (a pure projection over the on-disk bench JSONL)
# ---------------------------------------------------------------------------


def _bench_row(prompt: str, *, tier: int, topic: str, gold: float | None = 1.0) -> str:
    row = {
        "task_id": f"t-{abs(hash(prompt)) % 99999}",
        "topic": topic,
        "subtopic": "x",
        "tier": tier,
        "prompt": prompt,
        "answer": "1.0 s",
        "gold_unit": "s",
        "rel_tol": 0.02,
    }
    if gold is not None:
        row["gold_value_si"] = gold
    return json.dumps(row)


def _seed_bench(
    bench_dir: Path,
    *,
    pool: list[str],
    heldout: list[str],
    queue: list[str] | None = None,
    name: str = "astro-bench-v0.1",
) -> None:
    """Write a pool + held-out split (and optional SFT-init queue) into the bench
    dir in the on-disk JSONL shape the projection reads."""
    bench_dir.mkdir(parents=True, exist_ok=True)
    (bench_dir / f"{name}.jsonl").write_text(
        "\n".join(_bench_row(p, tier=2, topic="orbital_mechanics") for p in pool) + "\n"
    )
    (bench_dir / f"{name}.heldout.jsonl").write_text(
        "\n".join(_bench_row(p, tier=1, topic="astrophysics") for p in heldout) + "\n"
    )
    if queue is not None:
        (bench_dir / "astro-sft-queue.jsonl").write_text(
            "\n".join(_bench_row(p, tier=2, topic="orbital_mechanics") for p in queue) + "\n"
        )


def test_bench_provenance_projection(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The standalone /api/bench-provenance derives the pedigree from the JSONL:
    # version + counts + disjointness + self-verifying golds + corpus exclusion.
    bench_dir = tmp_path / "bench"
    monkeypatch.setenv("FK_ARENA_BENCH_DIR", str(bench_dir))
    _seed_bench(
        bench_dir,
        pool=[f"pool prompt {i}" for i in range(5)],
        heldout=[f"held prompt {i}" for i in range(3)],
        queue=[f"corpus prompt {i}" for i in range(10)],
    )
    with TestClient(_app(tmp_path)) as client:
        prov = client.get("/api/bench-provenance").json()
        assert prov["available"] is True
        assert prov["version"] == "v0.1"
        assert prov["pool"] == 5 and prov["heldout"] == 3
        assert prov["disjoint"] is True and prov["overlap"] == 0
        # every seeded row carries a numeric gold → all self-verify
        assert prov["golds_with_si"] == prov["rows_total"] == 8
        assert prov["tier_mix"] == {"1": 3, "2": 5}
        assert prov["topic_mix"]["orbital_mechanics"] == 5
        assert prov["tolerance"] == "±2%"
        assert prov["corpus"]["rows"] == 10 and prov["corpus"]["excluded"] is True


def test_bench_provenance_detects_overlap(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # RV-10 is a real check, not a label: a prompt shared across pool + held-out
    # flips disjoint to False and counts the overlap (so the card warns honestly).
    bench_dir = tmp_path / "bench"
    monkeypatch.setenv("FK_ARENA_BENCH_DIR", str(bench_dir))
    _seed_bench(
        bench_dir,
        pool=["shared prompt", "pool only"],
        heldout=["shared prompt", "held only"],
        queue=["shared prompt", "corpus only"],  # corpus leak too
    )
    with TestClient(_app(tmp_path)) as client:
        prov = client.get("/api/bench-provenance").json()
        assert prov["disjoint"] is False and prov["overlap"] == 1
        assert prov["corpus"]["excluded"] is False and prov["corpus"]["overlap"] == 1


def test_bench_provenance_absent_is_clean_empty(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # No bench pair on disk → {available: false}, never a 500.
    monkeypatch.setenv("FK_ARENA_BENCH_DIR", str(tmp_path / "empty"))
    with TestClient(_app(tmp_path)) as client:
        r = client.get("/api/bench-provenance")
        assert r.status_code == 200
        assert r.json() == {"available": False, "kind": "bench"}


def test_build_bench_stage_lit_by_provenance(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # AE-8 rides the build spine: an unregistered bench (astro-bench, pending
    # AE-11) still lights the bench stage live off its JSONL — done state, a
    # provenance-derived headline, and the full `provenance` object attached.
    _no_hermes(monkeypatch)
    _no_scout(monkeypatch, tmp_path)
    _no_sft(monkeypatch, tmp_path)
    monkeypatch.setenv("FK_ARENA_CORPUS_DIR", str(tmp_path / "no-corpus"))
    bench_dir = tmp_path / "bench"
    monkeypatch.setenv("FK_ARENA_BENCH_DIR", str(bench_dir))
    monkeypatch.setenv("FK_ARENA_BUILD_DIR", str(bench_dir))
    _seed_bench(
        bench_dir,
        pool=[f"p{i}" for i in range(4)],
        heldout=[f"h{i}" for i in range(2)],
    )
    (bench_dir / "build-manifest.json").write_text(json.dumps({"bench_id": "astro-bench"}))
    with TestClient(_app(tmp_path)) as client:
        stages = {s["key"]: s for s in client.get("/api/build").json()["stages"]}
        bench = stages["bench"]
        assert bench["state"] == "done"
        assert "4 pool + 2 held-out" in bench["headline"]
        assert bench["provenance"]["disjoint"] is True
        assert bench["provenance"]["bench_id"] == "astro-bench"


# ---------------------------------------------------------------------------
# AE-26 (v2 cut 3) — inventory truth: manifest claims VERIFIED on disk at read
# ---------------------------------------------------------------------------


def _manifest_with_artifacts(tmp_path: Path, stage: str, artifacts: list) -> None:
    d = tmp_path / "evidence" / "astrodynamics"
    d.mkdir(parents=True, exist_ok=True)
    (d / "build-manifest.json").write_text(
        json.dumps({
            "vertical": "astrodynamics",
            "label": "Kepler",
            "stages": {stage: {"state": "done", "headline": "x", "artifacts": artifacts}},
        })
    )


def _stage(client, key):
    body = client.get("/api/build").json()
    return {s["key"]: s for s in body["stages"]}[key]


def test_inventory_verifies_matching_line_count(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _no_hermes(monkeypatch)
    _no_scout(monkeypatch, tmp_path)
    _no_sft(monkeypatch, tmp_path)
    d = tmp_path / "evidence" / "astrodynamics"
    d.mkdir(parents=True, exist_ok=True)
    (d / "corpus.jsonl").write_text("\n".join('{"prompt": "p%d"}' % i for i in range(600)) + "\n")
    _manifest_with_artifacts(tmp_path, "corpus", [{"path": "corpus.jsonl", "rows": 600}])
    with TestClient(_app(tmp_path)) as client:
        st = _stage(client, "corpus")
        inv = st["inventory"]
        assert inv["ok"] is True
        item = inv["items"][0]
        assert item["exists"] is True
        assert item["lines"] == 600 and item["claimed_rows"] == 600
        assert item["match"] is True
        assert item["mtime"] is not None
        # The raw declaration never ships — only the computed observation.
        assert "artifacts" not in st


def test_inventory_flags_count_drift_and_missing_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _no_hermes(monkeypatch)
    _no_scout(monkeypatch, tmp_path)
    _no_sft(monkeypatch, tmp_path)
    d = tmp_path / "evidence" / "astrodynamics"
    d.mkdir(parents=True, exist_ok=True)
    (d / "short.jsonl").write_text('{"a":1}\n{"a":2}\n')  # 2 rows, claims 600
    _manifest_with_artifacts(
        tmp_path, "corpus",
        [{"path": "short.jsonl", "rows": 600}, {"path": "gone.jsonl", "rows": 44}],
    )
    with TestClient(_app(tmp_path)) as client:
        inv = _stage(client, "corpus")["inventory"]
        assert inv["ok"] is False  # assertion ≠ disk truth — the OBS-2 fix
        drift = next(i for i in inv["items"] if i["name"] == "short.jsonl")
        assert drift["lines"] == 2 and drift["match"] is False
        gone = next(i for i in inv["items"] if i["name"] == "gone.jsonl")
        assert gone["exists"] is False


def test_inventory_directory_file_claim_and_binary_size_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _no_hermes(monkeypatch)
    _no_scout(monkeypatch, tmp_path)
    _no_sft(monkeypatch, tmp_path)
    d = tmp_path / "evidence" / "astrodynamics"
    quants = tmp_path / "quants"
    quants.mkdir(parents=True, exist_ok=True)
    for n in ("a.gguf", "b.gguf"):
        (quants / n).write_bytes(b"\x00" * 64)
    _manifest_with_artifacts(
        tmp_path, "publish",
        [
            {"path": str(quants), "files": 2},
            {"path": str(quants / "a.gguf")},  # binary: exists/bytes only
        ],
    )
    d.mkdir(parents=True, exist_ok=True)
    with TestClient(_app(tmp_path)) as client:
        inv = _stage(client, "publish")["inventory"]
        assert inv["ok"] is True
        dirit = next(i for i in inv["items"] if i["files"] is not None)
        assert dirit["files"] == 2 and dirit["match"] is True
        binit = next(i for i in inv["items"] if i["name"] == "a.gguf")
        assert binit["bytes"] == 64
        assert binit["lines"] is None  # never read as text


def test_inventory_absent_when_nothing_declared(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _no_hermes(monkeypatch)
    _no_scout(monkeypatch, tmp_path)
    _no_sft(monkeypatch, tmp_path)
    _manifest_with_artifacts(tmp_path, "corpus", [])
    with TestClient(_app(tmp_path)) as client:
        st = _stage(client, "corpus")
        assert "inventory" not in st
