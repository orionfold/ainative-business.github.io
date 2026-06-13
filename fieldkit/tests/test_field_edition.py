# Copyright 2026 Manav Sehgal
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for fieldkit.field_edition (Arena Field Edition installer surface).

The matrix verdict (:func:`evaluate_matrix`) is a pure function over probed
strings, so these tests are box-independent — no DGX hardware required. The
live probe layer is exercised only for "does not raise / returns the right
keys"; its values depend on the host.
"""

from __future__ import annotations

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
    return {
        "dgx_os": "7.2.3",
        "driver": "580.95.05",
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
    probes["dgx_os"] = "7.5.0"
    probes["driver"] = "580.159.03"
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


def test_stub_commands_exit_with_milestone_marker() -> None:
    for cmd in ("down", "rollback", "update"):
        result = runner.invoke(app, ["field-edition", cmd])
        assert result.exit_code != 0
        assert "stub" in result.stdout or "stub" in str(result.exception)


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


def test_default_open_embedder_needs_no_ngc_key() -> None:
    svc = render_compose()["services"]["of-embedder"]
    assert "NGC_API_KEY" not in svc["environment"]


def test_nim_embedder_path_injects_key_and_is_already_pinned() -> None:
    cfg = default_config().with_nim_embedder()
    assert cfg.embedder is NIM_EMBEDDER
    svc = render_compose(cfg)["services"]["of-embedder"]
    assert "NGC_API_KEY" in svc["environment"]
    # the NIM image is real (pinnable), unlike the not-yet-built open default.
    assert cfg.embedder.image.repo.startswith("nvcr.io/nim/")


def test_unpinned_images_flags_the_unbuilt_orionfold_images() -> None:
    # default ships the open embedder + llama lane as PENDING; pgvector is real.
    repos = {p.repo for p in unpinned_images()}
    assert "ghcr.io/orionfold/cortex-embedder" in repos
    assert "ghcr.io/orionfold/llama-server-cuda13" in repos
    assert "pgvector/pgvector" not in repos


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
    for key in ("advisor", "cortex", "lane", "hermes"):
        outcome = runner_live.measure(key, default_config())
        assert outcome.error is not None
        assert "M2" in outcome.error  # honest "not yet wired", never a vanity pass


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
