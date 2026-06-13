# Copyright 2026 Manav Sehgal
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for fieldkit.field_edition (Arena Field Edition installer surface).

The matrix verdict (:func:`evaluate_matrix`) is a pure function over probed
strings, so these tests are box-independent — no DGX hardware required. The
live probe layer is exercised only for "does not raise / returns the right
keys"; its values depend on the host.
"""

from __future__ import annotations

from pathlib import Path

import fieldkit.field_edition.doctor as doctor_mod
from fieldkit.cli import app
from fieldkit.field_edition import (
    TESTED_MATRIX,
    DoctorReport,
    evaluate_matrix,
    parse_version,
    probe_environment,
)
from typer.testing import CliRunner

runner = CliRunner()


# --- parse_version -----------------------------------------------------------


def test_parse_version_dotted() -> None:
    assert parse_version("580.159.03") == (580, 159, 3)


def test_parse_version_embedded() -> None:
    assert parse_version("CUDA Version: 13.0") == (13, 0)


def test_parse_version_none_and_garbage() -> None:
    assert parse_version(None) is None
    assert parse_version("no version here") is None


# --- evaluate_matrix ---------------------------------------------------------


def _all_green_probes() -> dict[str, str | None]:
    # Matches the re-pinned §7 clean-wipe baseline (DGX OS 7.4.0 / driver
    # 580.159.03) — the actual dogfood box.
    return {
        "dgx_os": "7.4.0",
        "driver": "580.159.03",
        "cuda": "13.0",
        "docker": "Docker version 29.2.1, build a5c7197",
        "container_toolkit": "NVIDIA Container Toolkit CLI version 1.19.1",
    }


def test_exact_baseline_passes() -> None:
    report = evaluate_matrix(_all_green_probes())
    assert isinstance(report, DoctorReport)
    assert report.ok
    assert report.failures == ()


def test_newer_than_tested_still_passes() -> None:
    """A box ahead of the tested baseline (DGX OS churn) must NOT be refused."""
    probes = _all_green_probes()
    probes["dgx_os"] = "7.6.0"
    probes["driver"] = "590.10.05"
    report = evaluate_matrix(probes)
    assert report.ok, [f.reason for f in report.failures]


def test_too_old_driver_fails_with_fix() -> None:
    probes = _all_green_probes()
    probes["driver"] = "535.10.01"
    report = evaluate_matrix(probes)
    assert not report.ok
    driver = next(r for r in report.results if r.key == "driver")
    assert driver.status == "too_old"
    assert "older than the tested minimum" in driver.reason
    assert driver.fix  # a fix is always offered


def test_missing_docker_fails() -> None:
    probes = _all_green_probes()
    probes["docker"] = None
    report = evaluate_matrix(probes)
    assert not report.ok
    docker = next(r for r in report.results if r.key == "docker")
    assert docker.status == "missing"


def test_missing_version_probe_is_missing_not_crash() -> None:
    probes = _all_green_probes()
    probes["cuda"] = None
    report = evaluate_matrix(probes)
    cuda = next(r for r in report.results if r.key == "cuda")
    assert cuda.status == "missing"


def test_matrix_covers_the_seven_spec_axes() -> None:
    keys = {c.key for c in TESTED_MATRIX}
    assert keys == {"dgx_os", "driver", "cuda", "docker", "container_toolkit"}


# --- probe layer (host-dependent, just smoke it) -----------------------------


def test_probe_environment_returns_all_keys() -> None:
    probes = probe_environment()
    assert set(probes) == {c.key for c in TESTED_MATRIX}


# --- CLI surface -------------------------------------------------------------


def test_field_edition_help_lists_full_surface() -> None:
    result = runner.invoke(app, ["field-edition", "--help"])
    assert result.exit_code == 0
    for cmd in ("doctor", "up", "verify", "down", "repair", "rollback", "update"):
        assert cmd in result.stdout


def test_doctor_table_ok(monkeypatch) -> None:
    monkeypatch.setattr(doctor_mod, "run_doctor", lambda *a, **k: evaluate_matrix(_all_green_probes()))
    result = runner.invoke(app, ["field-edition", "doctor"])
    assert result.exit_code == 0
    assert "Matrix OK" in result.stdout


def test_doctor_json_failure_exit_1(monkeypatch) -> None:
    probes = _all_green_probes()
    probes["driver"] = "535.10.01"
    monkeypatch.setattr(doctor_mod, "run_doctor", lambda *a, **k: evaluate_matrix(probes))
    result = runner.invoke(app, ["field-edition", "doctor", "--json"])
    assert result.exit_code == 1
    assert '"ok": false' in result.stdout
    assert '"status": "too_old"' in result.stdout


def test_no_command_is_a_milestone_stub() -> None:
    # The whole §7+§9 surface is implemented now — nothing should say "stub".
    for cmd in ("doctor", "up", "verify", "down", "repair", "rollback", "update"):
        help_result = runner.invoke(app, ["field-edition", cmd, "--help"])
        assert "stub" not in help_result.stdout.lower()


# --- compose bundle (pure renderer) ------------------------------------------

from fieldkit.field_edition import (  # noqa: E402
    PHASES,
    Executor,
    FieldEditionConfig,
    InstallState,
    PhaseError,
    compose_yaml,
    default_config,
    plan_remaining,
    render_compose,
    run_up,
    unpinned_images,
    write_bundle,
)
from fieldkit.field_edition.compose import NIM_EMBEDDER, ImagePin  # noqa: E402


def test_image_pin_reference_tag_vs_digest() -> None:
    assert ImagePin("pgvector/pgvector", "pg16").reference() == "pgvector/pgvector:pg16"
    pinned = ImagePin("pgvector/pgvector", "pg16", digest="sha256:abc")
    assert pinned.reference() == "pgvector/pgvector@sha256:abc"
    assert pinned.pinned
    assert not ImagePin("x", "y", digest="PENDING").pinned


def test_render_compose_has_three_services_and_ports() -> None:
    doc = render_compose()
    services = doc["services"]
    assert set(services) == {"of-cortex-db", "of-embedder", "of-advisor-lane"}
    # pgvector binds loopback :5432; the lane :8091; the embedder :8001.
    assert services["of-cortex-db"]["ports"] == ["127.0.0.1:5432:5432"]
    assert services["of-advisor-lane"]["ports"] == ["127.0.0.1:8091:8091"]
    assert services["of-embedder"]["ports"] == ["127.0.0.1:8001:8000"]
    # the lane requests a GPU + depends on a healthy db.
    dev = services["of-advisor-lane"]["deploy"]["resources"]["reservations"]["devices"][0]
    assert dev["capabilities"] == ["gpu"]  # flat string list (compose schema)
    assert "of-cortex-db" in services["of-advisor-lane"]["depends_on"]


def test_render_compose_model_store_mounted_readonly() -> None:
    services = render_compose()["services"]
    for svc in ("of-embedder", "of-advisor-lane"):
        assert any(v.endswith(":/models:ro") for v in services[svc]["volumes"])


def test_default_embedder_is_nim_and_needs_ngc_key() -> None:
    # v1 default = the proven NIM embedder (the ICP already runs NGC).
    assert default_config().embedder is NIM_EMBEDDER
    svc = render_compose()["services"]["of-embedder"]
    assert "NGC_API_KEY" in svc["environment"]


def test_open_embedder_path_is_no_ngc_and_unpublished() -> None:
    # the v1.1 opt-in: no NGC key, but its image is not yet published (PENDING).
    cfg = default_config().with_open_embedder()
    svc = render_compose(cfg)["services"]["of-embedder"]
    assert "NGC_API_KEY" not in svc["environment"]
    assert not cfg.embedder.image.pinned
    assert cfg.embedder.image.repo == "ghcr.io/orionfold/cortex-embedder"


def test_nim_embedder_path_injects_key_and_is_already_pinned() -> None:
    cfg = default_config().with_nim_embedder()
    assert cfg.embedder is NIM_EMBEDDER
    svc = render_compose(cfg)["services"]["of-embedder"]
    assert "NGC_API_KEY" in svc["environment"]
    # the NIM image is real (pinnable), unlike the not-yet-built open default.
    assert cfg.embedder.image.repo.startswith("nvcr.io/nim/")


def test_unpinned_images_flags_only_the_llama_lane_by_default() -> None:
    # v1 default: only the llama.cpp lane is PENDING (pgvector + NIM embedder
    # are real, pinned images). The open embedder is the v1.1 opt-in.
    repos = {p.repo for p in unpinned_images()}
    assert "ghcr.io/orionfold/llama-server-cuda13" in repos
    assert "ghcr.io/orionfold/cortex-embedder" not in repos
    assert "pgvector/pgvector" not in repos
    assert "nvcr.io/nim/nvidia/llama-nemotron-embed-1b-v2" not in repos


def test_open_embedder_path_reintroduces_an_unpinned_image() -> None:
    cfg = default_config().with_open_embedder()
    repos = {p.repo for p in unpinned_images(cfg)}
    assert "ghcr.io/orionfold/cortex-embedder" in repos
    assert "ghcr.io/orionfold/llama-server-cuda13" in repos


def test_compose_yaml_round_trips() -> None:
    import yaml

    parsed = yaml.safe_load(compose_yaml())
    assert parsed == render_compose()


# --- phase machine (pure planning + re-entrancy) -----------------------------


def test_phases_are_ordered_and_named() -> None:
    keys = [p.key for p in PHASES]
    assert keys == ["matrix", "bundle", "pull", "stack", "sidecar", "resident", "verify"]
    assert PHASES[0].safe and PHASES[1].safe  # matrix + bundle are local-only
    assert PHASES[-1].optional  # verify


def test_plan_skips_done_phases() -> None:
    state = InstallState(phases={"matrix": "done", "bundle": "done"})
    plan = [p.key for p in plan_remaining(state)]
    assert "matrix" not in plan and "bundle" not in plan
    assert plan[0] == "pull"


def test_plan_force_reruns_everything() -> None:
    state = InstallState(phases={"matrix": "done"})
    plan = [p.key for p in plan_remaining(state, force=True)]
    assert "matrix" in plan


def test_plan_verify_is_opt_in() -> None:
    state = InstallState()
    assert "verify" not in [p.key for p in plan_remaining(state)]
    assert "verify" in [p.key for p in plan_remaining(state, with_verify=True)]


def test_plan_safe_only_drops_live_phases() -> None:
    plan = [p.key for p in plan_remaining(InstallState(), safe_only=True)]
    assert plan == ["matrix", "bundle"]


class _FakeExecutor(Executor):
    """Records dispatched phases; fails the named phase with a PhaseError."""

    def __init__(self, fail_on: str | None = None) -> None:
        self.ran: list[str] = []
        self.fail_on = fail_on

    def dispatch(self, key: str, config: FieldEditionConfig) -> None:
        self.ran.append(key)
        if key == self.fail_on:
            raise PhaseError(f"{key} blew up", fix="do the thing")


def _tmp_config(tmp_path) -> FieldEditionConfig:
    return FieldEditionConfig(home=tmp_path / "of", model_store=tmp_path / "of" / "models")


def test_run_up_runs_all_phases_and_checkpoints(tmp_path) -> None:
    cfg = _tmp_config(tmp_path)
    exe = _FakeExecutor()
    result = run_up(cfg, executor=exe)
    assert result.ok
    assert exe.ran == ["matrix", "bundle", "pull", "stack", "sidecar", "resident"]
    state = InstallState.load(cfg.home / "state.json")
    assert all(state.status(k) == "done" for k in exe.ran)


def test_run_up_stops_at_failure_and_marks_it(tmp_path) -> None:
    cfg = _tmp_config(tmp_path)
    exe = _FakeExecutor(fail_on="stack")
    result = run_up(cfg, executor=exe)
    assert not result.ok
    assert result.failed == "stack"
    assert result.fix == "do the thing"
    # sidecar/resident never attempted.
    assert exe.ran == ["matrix", "bundle", "pull", "stack"]
    state = InstallState.load(cfg.home / "state.json")
    assert state.status("stack") == "failed"
    assert state.status("resident") == "pending"


def test_run_up_re_entrant_resumes_from_failure(tmp_path) -> None:
    cfg = _tmp_config(tmp_path)
    run_up(cfg, executor=_FakeExecutor(fail_on="stack"))
    # second run with a healthy executor: done phases are skipped.
    exe2 = _FakeExecutor()
    result = run_up(cfg, executor=exe2)
    assert result.ok
    assert "matrix" not in exe2.ran and "bundle" not in exe2.ran
    assert exe2.ran[0] == "stack"
    assert set(result.skipped) >= {"matrix", "bundle", "pull"}


def test_run_up_dry_run_writes_bundle_and_plans_rest(tmp_path) -> None:
    cfg = _tmp_config(tmp_path)
    exe = _FakeExecutor()
    result = run_up(cfg, executor=exe, dry_run=True)
    assert result.ok and result.dry_run
    assert exe.ran == ["matrix", "bundle"]  # only the safe phases executed
    assert result.planned == ["pull", "stack", "sidecar", "resident"]
    # the actual file write is LiveExecutor.bundle's job — covered by the CLI test.


# --- live executor (box-independent slices) ----------------------------------


def test_live_executor_stack_refuses_unpinned_images(tmp_path) -> None:
    from fieldkit.field_edition.up import LiveExecutor

    cfg = _tmp_config(tmp_path)
    write_bundle(cfg)
    try:
        LiveExecutor().stack(cfg)
    except PhaseError as err:
        assert "not yet published" in str(err)
        assert err.fix
    else:  # pragma: no cover
        raise AssertionError("stack should refuse the unbuilt Orionfold images")


def test_live_executor_pull_idempotent_when_file_present(tmp_path) -> None:
    from fieldkit.field_edition.up import LiveExecutor

    cfg = _tmp_config(tmp_path)
    gguf = cfg.model_store / cfg.lane.gguf_name
    gguf.parent.mkdir(parents=True, exist_ok=True)
    gguf.write_bytes(b"already here")
    # No network touched; a present model short-circuits even with REV_PENDING.
    LiveExecutor().pull(cfg)
    assert gguf.read_bytes() == b"already here"


def test_live_executor_pull_refuses_unpinned_rev(tmp_path) -> None:
    from fieldkit.field_edition.up import LiveExecutor

    cfg = _tmp_config(tmp_path)  # lane.gguf_revision is REV_PENDING by default
    try:
        LiveExecutor().pull(cfg)
    except PhaseError as err:
        assert "no pinned GGUF rev" in str(err)
        assert "Advisor-GGUF" in err.fix
    else:  # pragma: no cover
        raise AssertionError("pull should refuse the unpublished Q4_K_M rev")


def test_live_executor_pull_downloads_pinned_rev(tmp_path, monkeypatch) -> None:
    import dataclasses

    from fieldkit.field_edition.up import LiveExecutor

    cfg = _tmp_config(tmp_path)
    cfg = dataclasses.replace(
        cfg, lane=dataclasses.replace(cfg.lane, gguf_revision="deadbeef" * 5)
    )
    gguf = cfg.model_store / cfg.lane.gguf_name

    calls: dict = {}

    def fake_download(*, repo_id, filename, revision, local_dir):
        calls.update(repo_id=repo_id, filename=filename, revision=revision)
        out = Path(local_dir) / filename
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(b"GGUF\x00pulled")
        return str(out)

    import huggingface_hub

    monkeypatch.setattr(huggingface_hub, "hf_hub_download", fake_download)
    LiveExecutor().pull(cfg)
    assert gguf.exists() and gguf.read_bytes() == b"GGUF\x00pulled"
    assert calls["repo_id"] == "Orionfold/Advisor-GGUF"
    assert calls["revision"] == "deadbeef" * 5


# --- up CLI ------------------------------------------------------------------


def test_up_dry_run_cli(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    import fieldkit.field_edition.doctor as doctor_mod

    monkeypatch.setattr(doctor_mod, "run_doctor", lambda *a, **k: evaluate_matrix(_all_green_probes()))
    result = runner.invoke(app, ["field-edition", "up", "--dry-run"])
    assert result.exit_code == 0, result.stdout
    assert "Bundle written" in result.stdout
    assert (tmp_path / ".orionfold" / "compose.yaml").exists()


# --- verify (§8 first-boot eval gate) ----------------------------------------

from fieldkit.field_edition import (  # noqa: E402
    ADVISOR_CURVEBALL_FLOOR,
    CORTEX_RECALL_FLOOR,
    GATES,
    GateOutcome,
    GateRunner,
    VerifyReport,
    assess_gate,
    evaluate_gates,
    run_verify,
    write_receipt,
)


def test_gates_cover_the_five_spec_components() -> None:
    assert [g.key for g in GATES] == ["fieldkit", "advisor", "cortex", "lane", "hermes"]
    hermes = next(g for g in GATES if g.key == "hermes")
    assert hermes.optional  # hermes only runs with --hermes


# --- pure floor logic --------------------------------------------------------


def test_assess_advisor_floor() -> None:
    ok, detail = assess_gate("advisor", {"curveball_v02": 0.857, "refusals_passed": 9, "refusals_total": 9})
    assert ok and "85.7%" in detail
    # below the curveball floor → fail even with refusals clean.
    assert not assess_gate(
        "advisor", {"curveball_v02": 0.70, "refusals_passed": 9, "refusals_total": 9}
    )[0]
    # one refusal regression → fail even above the curveball floor.
    assert not assess_gate(
        "advisor", {"curveball_v02": 0.90, "refusals_passed": 8, "refusals_total": 9}
    )[0]


def test_assess_advisor_uses_published_floor_constant() -> None:
    at_floor = {"curveball_v02": ADVISOR_CURVEBALL_FLOOR, "refusals_passed": 9, "refusals_total": 9}
    assert assess_gate("advisor", at_floor)[0]


def test_assess_cortex_floor() -> None:
    assert assess_gate("cortex", {"recall_at_5": 0.977, "contract_pass": 1})[0]
    # recall below the floor fails.
    assert not assess_gate("cortex", {"recall_at_5": 0.91, "contract_pass": 1})[0]
    # contract miss fails even at perfect recall.
    assert not assess_gate("cortex", {"recall_at_5": 1.0, "contract_pass": 0})[0]
    assert CORTEX_RECALL_FLOOR == 0.95


def test_assess_lane_needs_all_three_steps() -> None:
    assert assess_gate("lane", {"launched": 1, "generated": 1, "torn_down": 1})[0]
    assert not assess_gate("lane", {"launched": 1, "generated": 1, "torn_down": 0})[0]


def test_assess_fieldkit_needs_all_green() -> None:
    assert assess_gate("fieldkit", {"import_ok": 1, "version_ok": 1, "matrix_ok": 1})[0]
    assert not assess_gate("fieldkit", {"import_ok": 1, "version_ok": 1, "matrix_ok": 0})[0]


def test_assess_unknown_gate_raises() -> None:
    import pytest

    with pytest.raises(ValueError):
        assess_gate("nope", {})


# --- evaluate_gates (pure verdict) -------------------------------------------


def _all_pass_outcomes() -> dict[str, GateOutcome]:
    return {
        "fieldkit": GateOutcome("fieldkit", {"import_ok": 1, "version_ok": 1, "matrix_ok": 1}, note="fieldkit 0.31.0"),
        "advisor": GateOutcome("advisor", {"curveball_v02": 0.857, "refusals_passed": 9, "refusals_total": 9}),
        "cortex": GateOutcome("cortex", {"recall_at_5": 0.977, "contract_pass": 1}),
        "lane": GateOutcome("lane", {"launched": 1, "generated": 1, "torn_down": 1}),
        "hermes": GateOutcome("hermes", {"tool_returned": 1}),
    }


def test_evaluate_all_pass() -> None:
    report = evaluate_gates(_all_pass_outcomes(), with_hermes=True)
    assert isinstance(report, VerifyReport)
    assert report.ok
    assert report.summary()["passed"] == 5


def test_evaluate_hermes_skipped_when_not_enabled() -> None:
    report = evaluate_gates(_all_pass_outcomes())  # with_hermes default False
    hermes = next(r for r in report.results if r.key == "hermes")
    assert hermes.status == "skipped"
    assert hermes.ok  # skipped does not fail the run
    assert report.ok


def test_evaluate_error_outcome_becomes_error_with_fix() -> None:
    outcomes = _all_pass_outcomes()
    outcomes["lane"] = GateOutcome("lane", error="stack not up")
    report = evaluate_gates(outcomes, with_hermes=True)
    assert not report.ok
    lane = next(r for r in report.results if r.key == "lane")
    assert lane.status == "error"
    assert lane.detail == "stack not up"
    assert lane.fix  # the §8 fix is always carried


def test_evaluate_failed_floor_becomes_fail() -> None:
    outcomes = _all_pass_outcomes()
    outcomes["advisor"] = GateOutcome("advisor", {"curveball_v02": 0.60, "refusals_passed": 9, "refusals_total": 9})
    report = evaluate_gates(outcomes, with_hermes=True)
    advisor = next(r for r in report.results if r.key == "advisor")
    assert advisor.status == "fail"
    assert advisor.value == 0.60  # the headline number rides the receipt
    assert not report.ok


def test_receipt_always_renders_pass_or_fail() -> None:
    outcomes = _all_pass_outcomes()
    outcomes["cortex"] = GateOutcome("cortex", error="embedder down")
    report = evaluate_gates(outcomes, with_hermes=True)
    receipt = report.receipt(generated_at="2026-06-13T12:00:00+00:00", lane="advisor-gguf")
    assert receipt["kind"] == "field-edition-verify"
    assert receipt["ok"] is False
    assert receipt["generated_at"] == "2026-06-13T12:00:00+00:00"
    assert receipt["lane"] == "advisor-gguf"  # extra meta flows through
    assert receipt["summary"]["errored"] == 1
    cortex = next(g for g in receipt["gates"] if g["key"] == "cortex")
    assert cortex["fix"]  # failing gate carries the fix in the receipt


# --- live runner (box-independent slices) ------------------------------------


def test_live_runner_fieldkit_gate_is_real() -> None:
    from fieldkit.field_edition.verify import LiveGateRunner

    outcome = LiveGateRunner().fieldkit(default_config())
    assert outcome.metrics.get("import_ok") == 1.0
    assert outcome.metrics.get("version_ok") == 1.0
    assert "fieldkit" in outcome.note


def test_live_runner_bench_gates_error_honestly() -> None:
    from fieldkit.field_edition.verify import LiveGateRunner

    runner_live = LiveGateRunner()
    # cortex is excluded here: its recall-half does live retrieval (covered by
    # the dedicated fake-index tests below) — these three stay box-independent.
    for key in ("advisor", "lane", "hermes"):
        outcome = runner_live.measure(key, default_config())
        assert outcome.error is not None
        assert "M2" in outcome.error  # honest "not yet wired", never a vanity pass


# --- cortex recall-half (vendored frozen set + live retrieval, faked) --------


class _FakeIndex:
    """Stand-in for ``MemoryIndex`` — returns canned hits per question."""

    def __init__(self, by_question, *, table="advisor_corpus_v01", raises=None):
        self._by_question = by_question
        self.table = table
        self._raises = raises

    def query(self, question, *, top_k=5):
        if self._raises is not None:
            raise self._raises
        slugs = self._by_question.get(question, [])
        return [{"slug": s, "chunk_idx": 0, "dist": 0.1} for s in slugs]


def _patch_index(monkeypatch, fake):
    import fieldkit.memory as memory_mod

    monkeypatch.setattr(memory_mod, "MemoryIndex", lambda *a, **k: fake)


def test_recall_set_loads_and_sha_pins() -> None:
    from fieldkit.field_edition.recall import RECALL_SET_SHA, load_recall_set, recall_set_sha

    rset = load_recall_set()
    assert recall_set_sha() == RECALL_SET_SHA  # vendored file matches the pin
    assert rset.answerable  # there are answerable rows
    assert all(r.source_ids for r in rset.answerable)  # answerable rows carry gold
    refusals = [r for r in rset.rows if not r.is_answerable]
    assert refusals and all(not r.source_ids for r in refusals)  # refusal rows carry no gold


def test_recall_set_sha_drift_raises(tmp_path) -> None:
    import pytest

    from fieldkit.field_edition.recall import RECALL_SET_PATH, load_recall_set

    import json as _json

    tampered = tmp_path / "tampered.json"
    doc = _json.loads(RECALL_SET_PATH.read_text())
    doc["note_added_out_of_band"] = "drift"  # benign edit → different sha
    tampered.write_text(_json.dumps(doc, indent=2, sort_keys=True) + "\n")
    with pytest.raises(ValueError, match="sha drift"):
        load_recall_set(tampered)
    # …but an explicit opt-out still loads it
    assert load_recall_set(tampered, verify_sha=False).rows


def test_score_recall_set_perfect_and_miss() -> None:
    from fieldkit.field_edition.recall import RecallRow, score_recall_set

    rows = (
        RecallRow("a", "qa", frozenset({"src_a"}), "fam", "pool", "answer"),
        RecallRow("b", "qb", frozenset({"src_b"}), "fam", "pool", "answer"),
        RecallRow("r", "qr", frozenset(), "fam", "pool", "refuse"),  # excluded
    )
    hits = {"qa": ["src_a", "x"], "qb": ["src_b"]}
    rep = score_recall_set(rows, lambda q: hits.get(q, []), k=5)
    assert rep.answerable_n == 2 and rep.recall_at_5 == 1.0 and not rep.misses

    miss = {"qa": ["x", "y"], "qb": ["src_b"]}  # qa's gold drops out
    rep2 = score_recall_set(rows, lambda q: miss.get(q, []), k=5)
    assert rep2.recall_at_5 == 0.5 and rep2.misses == ("a",)


def test_score_recall_set_respects_k() -> None:
    from fieldkit.field_edition.recall import RecallRow, score_recall_set

    rows = (RecallRow("a", "qa", frozenset({"gold"}), "f", "pool", "answer"),)
    ranked = ["x", "y", "z", "w", "v", "gold"]  # gold at rank 6
    assert score_recall_set(rows, lambda q: ranked, k=5).recall_at_5 == 0.0
    assert score_recall_set(rows, lambda q: ranked, k=10).recall_at_5 == 1.0


def test_score_recall_set_empty_is_zero() -> None:
    from fieldkit.field_edition.recall import score_recall_set

    assert score_recall_set((), lambda q: [], k=5).recall_at_5 == 0.0


def test_live_cortex_recall_half_measured_with_honest_pending(monkeypatch) -> None:
    from fieldkit.field_edition.recall import load_recall_set
    from fieldkit.field_edition.verify import LiveGateRunner

    rset = load_recall_set()
    # Every answerable question retrieves its own gold first → recall 1.0.
    by_q = {r.question: list(r.source_ids) for r in rset.answerable}
    _patch_index(monkeypatch, _FakeIndex(by_q, table=rset.corpus_table))

    outcome = LiveGateRunner().cortex(default_config())
    # The recall number is REAL and surfaced…
    assert outcome.metrics["recall_at_5"] == 1.0
    assert outcome.metrics["recall_answerable_n"] == float(len(rset.answerable))
    assert "recall@5 1.000" in outcome.note
    # …but the gate still cannot vanity-pass: contract half needs the lane (M2).
    assert outcome.error is not None and "M2" in outcome.error


def test_live_cortex_recall_half_below_floor_is_honest(monkeypatch) -> None:
    from fieldkit.field_edition.recall import load_recall_set
    from fieldkit.field_edition.verify import LiveGateRunner

    rset = load_recall_set()
    _patch_index(monkeypatch, _FakeIndex({}, table=rset.corpus_table))  # retrieves nothing

    outcome = LiveGateRunner().cortex(default_config())
    assert outcome.metrics["recall_at_5"] == 0.0
    assert "<0.95" in outcome.note  # honest: recall failed the floor
    assert outcome.error is not None


def test_live_cortex_unreachable_errors_with_fix(monkeypatch) -> None:
    from fieldkit.field_edition.verify import LiveGateRunner

    _patch_index(monkeypatch, _FakeIndex({}, raises=MemoryError("pgvector connect failed")))
    outcome = LiveGateRunner().cortex(default_config())
    assert not outcome.metrics  # nothing measured
    assert outcome.error is not None
    assert "unreachable" in outcome.error and "M2" in outcome.error


# --- orchestrator + receipt writer -------------------------------------------


class _FakeGateRunner(GateRunner):
    def __init__(self, outcomes: dict[str, GateOutcome]) -> None:
        self._outcomes = outcomes

    def measure(self, key: str, config) -> GateOutcome:
        return self._outcomes[key]


def test_run_verify_writes_latest_and_archival_receipt(tmp_path) -> None:
    cfg = FieldEditionConfig(home=tmp_path / "of", model_store=tmp_path / "of" / "models")
    report, path = run_verify(
        cfg,
        runner=_FakeGateRunner(_all_pass_outcomes()),
        with_hermes=True,
        generated_at="2026-06-13T12:00:00+00:00",
    )
    assert report.ok
    latest = cfg.home / "receipts" / "verify-latest.json"
    assert latest.exists()
    assert path.exists() and path != latest  # archival timestamped copy too
    import json as _json

    data = _json.loads(latest.read_text())
    assert data["ok"] and data["generated_at"] == "2026-06-13T12:00:00+00:00"


def test_run_verify_receipt_written_even_on_failure(tmp_path) -> None:
    cfg = FieldEditionConfig(home=tmp_path / "of", model_store=tmp_path / "of" / "models")
    outcomes = _all_pass_outcomes()
    outcomes["lane"] = GateOutcome("lane", error="stack not up")
    report, _ = run_verify(
        cfg, runner=_FakeGateRunner(outcomes), with_hermes=True,
        generated_at="2026-06-13T12:00:00+00:00",
    )
    assert not report.ok
    assert (cfg.home / "receipts" / "verify-latest.json").exists()  # honest receipt, still written


def test_write_receipt_creates_dir(tmp_path) -> None:
    report = evaluate_gates(_all_pass_outcomes(), with_hermes=True)
    path = write_receipt(report, tmp_path / "nested" / "receipts", generated_at="t")
    assert path.exists() and path.name == "verify-latest.json"


# --- verify CLI --------------------------------------------------------------


def test_verify_cli_passes_with_all_green(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    import fieldkit.field_edition.verify as verify_mod

    monkeypatch.setattr(
        verify_mod, "LiveGateRunner", lambda: _FakeGateRunner(_all_pass_outcomes())
    )
    result = runner.invoke(app, ["field-edition", "verify", "--hermes"])
    assert result.exit_code == 0, result.stdout
    assert "PASSED" in result.stdout
    assert (tmp_path / ".orionfold" / "receipts" / "verify-latest.json").exists()


def test_verify_cli_fails_and_names_the_gate(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    import fieldkit.field_edition.verify as verify_mod

    outcomes = _all_pass_outcomes()
    outcomes["cortex"] = GateOutcome("cortex", error="embedder digest mismatch")
    monkeypatch.setattr(verify_mod, "LiveGateRunner", lambda: _FakeGateRunner(outcomes))
    result = runner.invoke(app, ["field-edition", "verify", "--hermes"])
    assert result.exit_code == 1
    assert "Cortex" in result.output
    assert "repair cortex" in result.output  # the §8 fix surfaces


def test_verify_cli_json(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    import fieldkit.field_edition.verify as verify_mod

    monkeypatch.setattr(
        verify_mod, "LiveGateRunner", lambda: _FakeGateRunner(_all_pass_outcomes())
    )
    result = runner.invoke(app, ["field-edition", "verify", "--json", "--hermes"])
    assert result.exit_code == 0
    assert '"kind": "field-edition-verify"' in result.stdout


# --- down (§7 uninstall, AC-6) -----------------------------------------------

from fieldkit.field_edition import (  # noqa: E402
    COMPONENTS,
    DownExecutor,
    ProvenMatrix,
    RepairExecutor,
    UpdateChannel,
    UpdateError,
    plan_down,
    plan_repair,
    run_down,
    run_repair,
    run_rollback,
    run_update,
)
from fieldkit.field_edition import proven_matrix as pm_mod  # noqa: E402


class _FakeDownExecutor(DownExecutor):
    def __init__(self) -> None:
        self.compose_down_called: bool | None = None
        self.removed: list[str] = []
        self.fail_compose = False

    def compose_down(self, config, *, remove_volumes: bool) -> None:
        if self.fail_compose:
            raise RuntimeError("compose down boom")
        self.compose_down_called = remove_volumes

    def remove_path(self, path) -> None:
        self.removed.append(str(path))


def test_plan_down_default_preserves_data() -> None:
    plan = plan_down(default_config(), purge=False)
    assert not plan.remove_volumes
    assert plan.purge_paths == ()
    assert any("model store" in p for p in plan.preserved)


def test_plan_down_purge_removes_models_db_and_bundle(tmp_path) -> None:
    cfg = _tmp_config(tmp_path)
    plan = plan_down(cfg, purge=True)
    assert plan.remove_volumes
    paths = {p.name for p in plan.purge_paths}
    assert {"models", "arena.db", "compose.yaml", ".env", "state.json"} <= paths


def test_run_down_default_keeps_data(tmp_path) -> None:
    exe = _FakeDownExecutor()
    result = run_down(_tmp_config(tmp_path), purge=False, executor=exe)
    assert result.ok
    assert exe.compose_down_called is False  # no -v
    assert exe.removed == []  # nothing purged
    assert result.preserved


def test_run_down_purge_removes_paths(tmp_path) -> None:
    exe = _FakeDownExecutor()
    result = run_down(_tmp_config(tmp_path), purge=True, executor=exe)
    assert result.ok and result.purged
    assert exe.compose_down_called is True  # -v dropped the volume
    assert any(p.endswith("models") for p in exe.removed)


def test_run_down_surfaces_teardown_failure(tmp_path) -> None:
    exe = _FakeDownExecutor()
    exe.fail_compose = True
    result = run_down(_tmp_config(tmp_path), executor=exe)
    assert not result.ok
    assert "teardown failed" in result.error


def test_down_cli_default_preserves(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    result = runner.invoke(app, ["field-edition", "down"])
    assert result.exit_code == 0, result.stdout
    assert "Preserved" in result.stdout
    assert "pipx uninstall fieldkit" in result.stdout


# --- repair (§8 single-component re-pull + re-gate) --------------------------


class _FakeRepairExecutor(RepairExecutor):
    def __init__(self) -> None:
        self.repulled = False
        self.recreated: tuple[str, ...] = ()

    def repull_model(self, config) -> None:
        self.repulled = True

    def recreate(self, config, services) -> None:
        self.recreated = tuple(services)


def test_plan_repair_known_components() -> None:
    assert set(COMPONENTS) == {"advisor", "cortex", "lane"}
    assert plan_repair("cortex").gate == "cortex"
    # cortex recreates both the db + the embedder.
    assert len(plan_repair("cortex").services) == 2
    assert plan_repair("advisor").repull_model is True
    assert plan_repair("lane").repull_model is False


def test_plan_repair_unknown_raises() -> None:
    import pytest

    with pytest.raises(ValueError):
        plan_repair("frobnicate")


def test_run_repair_unknown_component_errors(tmp_path) -> None:
    result = run_repair("nope", _tmp_config(tmp_path), executor=_FakeRepairExecutor(),
                        runner=_FakeGateRunner({}))
    assert not result.ok
    assert "unknown component" in result.error


def test_run_repair_advisor_repulls_recreates_and_gates(tmp_path) -> None:
    exe = _FakeRepairExecutor()
    outcomes = {"advisor": GateOutcome("advisor", {"curveball_v02": 0.90, "refusals_passed": 9,
                                                   "refusals_total": 9})}
    result = run_repair("advisor", _tmp_config(tmp_path), executor=exe,
                        runner=_FakeGateRunner(outcomes))
    assert exe.repulled is True
    assert exe.recreated == ("of-advisor-lane",)
    assert result.ok and result.gate.key == "advisor" and result.gate.status == "pass"


def test_run_repair_reports_failed_gate(tmp_path) -> None:
    exe = _FakeRepairExecutor()
    outcomes = {"cortex": GateOutcome("cortex", error="embedder digest mismatch")}
    result = run_repair("cortex", _tmp_config(tmp_path), executor=exe,
                        runner=_FakeGateRunner(outcomes))
    assert exe.repulled is False  # cortex owns no model weights
    assert not result.ok and result.gate.status == "error"


def test_run_repair_surfaces_recreate_failure(tmp_path) -> None:
    class _Boom(RepairExecutor):
        def repull_model(self, config) -> None: ...
        def recreate(self, config, services) -> None:
            raise RuntimeError("force-recreate failed")

    result = run_repair("lane", _tmp_config(tmp_path), executor=_Boom(),
                        runner=_FakeGateRunner({}))
    assert not result.ok and "recreate failed" in result.error


# --- proven matrix (§9 retention) --------------------------------------------


def test_from_config_derives_local_matrix() -> None:
    m = pm_mod.from_config()
    assert m.matrix_version == "local" and not m.signed
    assert set(m.images) == {"cortex-db", "embedder", "advisor-lane"}


def test_proven_matrix_round_trips() -> None:
    m = ProvenMatrix("2026.q3", "0.31.0", {"db": "x@sha256:1"}, {"advisor": "rev1"}, signed=True)
    assert ProvenMatrix.from_dict(m.to_dict()) == m


def test_fingerprint_ignores_timestamp_and_signed() -> None:
    a = ProvenMatrix("v1", "0.31.0", {"db": "x"}, {}, signed=False, created="t1")
    b = ProvenMatrix("v1", "0.31.0", {"db": "x"}, {}, signed=True, created="t2")
    assert a.fingerprint() == b.fingerprint()


def test_save_current_rotates_previous(tmp_path) -> None:
    cfg = _tmp_config(tmp_path)
    m1 = ProvenMatrix("v1", "0.31.0", {"db": "a"})
    m2 = ProvenMatrix("v2", "0.31.0", {"db": "b"})
    pm_mod.save_current(m1, cfg)
    assert pm_mod.load_previous(cfg) is None
    pm_mod.save_current(m2, cfg)
    assert pm_mod.load_current(cfg).matrix_version == "v2"
    assert pm_mod.load_previous(cfg).matrix_version == "v1"


def test_rollback_restores_previous(tmp_path) -> None:
    cfg = _tmp_config(tmp_path)
    pm_mod.save_current(ProvenMatrix("v1", "0.31.0", {"db": "a"}), cfg)
    pm_mod.save_current(ProvenMatrix("v2", "0.31.0", {"db": "b"}), cfg)
    restored = pm_mod.rollback(cfg)
    assert restored.matrix_version == "v1"
    assert pm_mod.load_current(cfg).matrix_version == "v1"


def test_rollback_none_when_no_previous(tmp_path) -> None:
    assert pm_mod.rollback(_tmp_config(tmp_path)) is None


# --- update channel (§9 update flow + auto-rollback) -------------------------


class _FakeChannel(UpdateChannel):
    def __init__(self, matrix: ProvenMatrix | None, *, fetch_error: str | None = None) -> None:
        self.matrix = matrix
        self.fetch_error = fetch_error

    def fetch_latest(self, config) -> ProvenMatrix:
        if self.fetch_error:
            raise UpdateError(self.fetch_error, fix="fix it")
        return self.matrix

    def verify_signature(self, matrix) -> None:
        return None


def test_run_update_aborts_when_no_channel(tmp_path) -> None:
    result = run_update(_tmp_config(tmp_path), channel=_FakeChannel(None, fetch_error="no channel"),
                        applier=lambda cfg: None, gate=lambda cfg: (None, None))
    assert not result.ok and "no channel" in result.error


def test_run_update_already_current(tmp_path) -> None:
    cfg = _tmp_config(tmp_path)
    m = ProvenMatrix("v1", "0.31.0", {"db": "a"})
    pm_mod.save_current(m, cfg)
    result = run_update(cfg, channel=_FakeChannel(m), applier=lambda c: None,
                        gate=lambda c: (None, None))
    assert result.ok and not result.applied
    assert "already" in result.message


def test_run_update_applies_and_gates_green(tmp_path) -> None:
    from fieldkit.field_edition.verify import GateResult, VerifyReport

    cfg = _tmp_config(tmp_path)
    m = ProvenMatrix("v2", "0.31.0", {"db": "b"})
    good = VerifyReport((GateResult("fieldkit", "fieldkit", "m", "t", "pass", "d", None, "", ""),))
    result = run_update(cfg, channel=_FakeChannel(m), applier=lambda c: None,
                        gate=lambda c: (good, tmp_path / "r.json"))
    assert result.ok and result.applied and not result.rolled_back
    assert pm_mod.load_current(cfg).matrix_version == "v2"


def test_run_update_auto_rollback_on_gate_fail(tmp_path) -> None:
    from fieldkit.field_edition.verify import GateResult, VerifyReport

    cfg = _tmp_config(tmp_path)
    pm_mod.save_current(ProvenMatrix("v1", "0.31.0", {"db": "a"}), cfg)  # prior to roll back to
    bad = VerifyReport((GateResult("cortex", "Cortex", "m", "t", "fail", "low", 0.1, "", "fix"),))
    result = run_update(cfg, channel=_FakeChannel(ProvenMatrix("v2", "0.31.0", {"db": "b"})),
                        applier=lambda c: None, gate=lambda c: (bad, tmp_path / "r.json"))
    assert not result.ok and result.rolled_back
    # the box is restored to the prior matrix.
    assert pm_mod.load_current(cfg).matrix_version == "v1"


def test_run_update_auto_rollback_on_apply_fail(tmp_path) -> None:
    cfg = _tmp_config(tmp_path)
    pm_mod.save_current(ProvenMatrix("v1", "0.31.0", {"db": "a"}), cfg)
    calls = {"n": 0}

    def flaky_apply(c) -> None:
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("pull failed")
        # second call (rollback re-apply) succeeds

    result = run_update(cfg, channel=_FakeChannel(ProvenMatrix("v2", "0.31.0", {"db": "b"})),
                        applier=flaky_apply, gate=lambda c: (None, None))
    assert not result.ok and result.rolled_back
    assert pm_mod.load_current(cfg).matrix_version == "v1"


def test_run_rollback_restores_and_reapplies(tmp_path) -> None:
    cfg = _tmp_config(tmp_path)
    pm_mod.save_current(ProvenMatrix("v1", "0.31.0", {"db": "a"}), cfg)
    pm_mod.save_current(ProvenMatrix("v2", "0.31.0", {"db": "b"}), cfg)
    result = run_rollback(cfg, applier=lambda c: None)
    assert result.ok and result.rolled_back
    assert pm_mod.load_current(cfg).matrix_version == "v1"


def test_run_rollback_nothing_to_restore(tmp_path) -> None:
    result = run_rollback(_tmp_config(tmp_path), applier=lambda c: None)
    assert not result.ok and "nothing to roll back" in result.message


def test_live_update_channel_is_honest() -> None:
    from fieldkit.field_edition.update import LiveUpdateChannel

    import pytest

    with pytest.raises(UpdateError):
        LiveUpdateChannel().fetch_latest(default_config())
