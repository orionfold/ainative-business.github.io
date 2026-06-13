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
    for cmd in ("verify", "down", "rollback", "update"):
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
