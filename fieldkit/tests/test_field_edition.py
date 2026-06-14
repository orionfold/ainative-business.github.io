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


def test_default_proven_matrix_is_fully_pinned() -> None:
    # v1 default: every image is digest-pinned (pgvector + NIM embedder +
    # the orionfold-built llama lane, pushed 2026-06-13) — zero PIN_PENDING,
    # so a live `up` resolves the whole stack by digest.
    assert unpinned_images() == []


def test_open_embedder_path_reintroduces_an_unpinned_image() -> None:
    # the v1.1 opt-in is the only thing that re-introduces an unbuilt image.
    cfg = default_config().with_open_embedder()
    repos = {p.repo for p in unpinned_images(cfg)}
    assert repos == {"ghcr.io/orionfold/cortex-embedder"}


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

    # the default matrix is fully pinned now; the open-embedder (v1.1) path is
    # the remaining unbuilt image, so use it to exercise the honest refusal.
    cfg = _tmp_config(tmp_path).with_open_embedder()
    write_bundle(cfg)
    try:
        LiveExecutor().stack(cfg)
    except PhaseError as err:
        assert "not yet published" in str(err)
        assert err.fix
    else:  # pragma: no cover
        raise AssertionError("stack should refuse the unbuilt open-embedder image")


def test_live_executor_pull_idempotent_when_file_present(tmp_path) -> None:
    from fieldkit.field_edition.up import LiveExecutor

    cfg = _tmp_config(tmp_path)
    gguf = cfg.model_store / cfg.lane.gguf_name
    gguf.parent.mkdir(parents=True, exist_ok=True)
    gguf.write_bytes(b"already here")
    # No network touched; a present model short-circuits even with REV_PENDING.
    LiveExecutor().pull(cfg)
    assert gguf.read_bytes() == b"already here"


def test_default_gguf_revision_is_pinned() -> None:
    # the Q4_K_M rev was published + validated 2026-06-13; the default is a
    # commit sha (not REV_PENDING), so a live `up` pull resolves it.
    from fieldkit.field_edition.compose import REV_PENDING, default_config

    lane = default_config().lane
    assert lane.gguf_pinned
    assert lane.gguf_revision != REV_PENDING and len(lane.gguf_revision) == 40


def test_live_executor_pull_refuses_unpinned_rev(tmp_path) -> None:
    import dataclasses

    from fieldkit.field_edition.compose import REV_PENDING
    from fieldkit.field_edition.up import LiveExecutor

    cfg = _tmp_config(tmp_path)
    cfg = dataclasses.replace(cfg, lane=dataclasses.replace(cfg.lane, gguf_revision=REV_PENDING))
    try:
        LiveExecutor().pull(cfg)
    except PhaseError as err:
        assert "no pinned GGUF rev" in str(err)
        assert "Advisor-GGUF" in err.fix
    else:  # pragma: no cover
        raise AssertionError("pull should refuse an unpinned (REV_PENDING) rev")


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


def test_assess_lane_warm_resident_floor() -> None:
    # §6/§8 reconciliation: the warm default stays resident, so first-boot
    # verify floors on launched + generated only — teardown is NOT required
    # (it's the down/repair lifecycle gates' job).
    assert assess_gate("lane", {"launched": 1, "generated": 1})[0]
    assert assess_gate("lane", {"launched": 1, "generated": 1, "torn_down": 0})[0]  # teardown irrelevant
    assert not assess_gate("lane", {"launched": 1, "generated": 0})[0]  # up but cannot generate → fail
    assert not assess_gate("lane", {"launched": 0, "generated": 1})[0]  # not up → fail


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


def _dead_stack_config():
    """A config whose lane points at a dead port so the live runner errors
    honestly regardless of whether the dogfood box's stack is actually up."""
    import dataclasses

    cfg = default_config()
    return dataclasses.replace(cfg, lane=dataclasses.replace(cfg.lane, port=2))


def test_live_runner_bench_gates_error_honestly() -> None:
    from fieldkit.field_edition.verify import LiveGateRunner

    runner_live = LiveGateRunner()
    cfg = _dead_stack_config()  # dead lane → deterministic honest errors
    # cortex is excluded here: it also does live retrieval (covered by the
    # dedicated fake-index tests below) — these three stay box-independent.
    for key in ("advisor", "lane", "hermes"):
        outcome = runner_live.measure(key, cfg)
        assert outcome.error is not None
        assert "M2" in outcome.error  # honest "stack not up", never a vanity pass


# --- cortex recall-half (vendored frozen set + live retrieval, faked) --------


class _FakeIndex:
    """Stand-in for ``MemoryIndex`` — returns canned hits per question.

    Each hit carries ``text`` (the grounded-contract half reads it to build the
    context block) plus the provenance fields the live query returns."""

    def __init__(self, by_question, *, table="advisor_corpus_v01", raises=None, text_by_slug=None):
        self._by_question = by_question
        self.table = table
        self._raises = raises
        self._text = text_by_slug or {}

    def query(self, question, *, top_k=5):
        if self._raises is not None:
            raise self._raises
        slugs = self._by_question.get(question, [])
        return [
            {
                "slug": s,
                "chunk_idx": 0,
                "dist": 0.1,
                "text": self._text.get(s, f"Public context about {s} with enough body to cite."),
                "source": "public_doc",
                "kind": "public_doc",
            }
            for s in slugs
        ]


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


def _cortex_runner_with_lane(lane_fn):
    """A live cortex runner whose lane generation is faked by ``lane_fn``."""
    from fieldkit.field_edition.verify import LiveGateRunner

    runner = LiveGateRunner()
    runner._lane_chat = lane_fn  # type: ignore[assignment]
    return runner


def test_live_cortex_both_halves_pass(monkeypatch) -> None:
    # Both the recall-half (retrieval) and the grounded-contract half (the lane
    # citing/refusing over live context) measured with fakes → a real PASS.
    from fieldkit.field_edition.grounded import select_contract_probes
    from fieldkit.field_edition.recall import load_recall_set

    rset = load_recall_set()
    probes = select_contract_probes(rset.rows)
    by_q = {p.question: p for p in probes}
    # Index serves gold for every recall row + every grounded probe.
    hits = {r.question: list(r.source_ids) for r in rset.answerable}
    for p in probes:
        hits.setdefault(p.question, list(p.expected_source_ids))
    _patch_index(monkeypatch, _FakeIndex(hits, table=rset.corpus_table))

    def _lane(base, model, messages, **kw):  # noqa: ANN001 — well-behaved canned answers
        question = messages[1]["content"].split("Question: ", 1)[1].split("\n\n", 1)[0]
        probe = by_q[question]
        if probe.expected_behavior == "refuse":
            return "The retrieved public context does not support this question. Citations: []"
        gold = (list(probe.expected_source_ids) or ["unknown"])[0]
        prefix = "Route: " if probe.expected_behavior == "route" else ""
        return f"{prefix}A grounded answer with a substantive body. Citations: [{gold}]"

    outcome = _cortex_runner_with_lane(_lane).cortex(default_config())
    assert outcome.error is None  # both halves measured → no honest-error short-circuit
    assert outcome.metrics["recall_at_5"] == 1.0
    assert outcome.metrics["contract_pass"] == 1.0
    assert outcome.metrics["grounded_refusals_passed"] == outcome.metrics["grounded_refusals_total"]
    assert assess_gate("cortex", outcome.metrics)[0]  # the gate PASSES


def test_live_cortex_grounded_half_refusal_regression_fails(monkeypatch) -> None:
    # A model that confabulates on a missing-source row breaks refusal hygiene →
    # contract_pass 0 → the gate fails even with perfect recall.
    from fieldkit.field_edition.grounded import select_contract_probes
    from fieldkit.field_edition.recall import load_recall_set

    rset = load_recall_set()
    probes = select_contract_probes(rset.rows)
    by_q = {p.question: p for p in probes}
    hits = {r.question: list(r.source_ids) for r in rset.answerable}
    for p in probes:
        hits.setdefault(p.question, list(p.expected_source_ids))
    _patch_index(monkeypatch, _FakeIndex(hits, table=rset.corpus_table))

    def _lane(base, model, messages, **kw):  # noqa: ANN001
        question = messages[1]["content"].split("Question: ", 1)[1].split("\n\n", 1)[0]
        probe = by_q[question]
        if probe.expected_behavior == "refuse":
            return "Sure, the answer is foo. Citations: [made_up_source]"  # confabulation
        gold = (list(probe.expected_source_ids) or ["unknown"])[0]
        prefix = "Route: " if probe.expected_behavior == "route" else ""
        return f"{prefix}A grounded answer with a substantive body. Citations: [{gold}]"

    outcome = _cortex_runner_with_lane(_lane).cortex(default_config())
    assert outcome.error is None
    assert outcome.metrics["contract_pass"] == 0.0
    assert outcome.metrics["grounded_refusals_passed"] < outcome.metrics["grounded_refusals_total"]
    assert not assess_gate("cortex", outcome.metrics)[0]  # refusal regression fails the gate


def test_live_cortex_lane_down_surfaces_recall_honestly(monkeypatch) -> None:
    # Recall stack up but the serving lane down: the recall number is REAL and
    # surfaced, the grounded half reports an honest error (never a vanity pass).
    from fieldkit.field_edition.recall import load_recall_set

    rset = load_recall_set()
    by_q = {r.question: list(r.source_ids) for r in rset.answerable}
    _patch_index(monkeypatch, _FakeIndex(by_q, table=rset.corpus_table))

    def _lane(*a, **k):  # noqa: ANN002, ANN003 — lane unreachable
        raise OSError("connection refused")

    outcome = _cortex_runner_with_lane(_lane).cortex(default_config())
    assert outcome.metrics["recall_at_5"] == 1.0  # recall surfaced live
    assert "recall@5 1.000" in outcome.note
    assert outcome.error is not None
    assert "grounded-contract half could not run" in outcome.error and "M2" in outcome.error


def test_live_cortex_unreachable_errors_with_fix(monkeypatch) -> None:
    from fieldkit.field_edition.verify import LiveGateRunner

    _patch_index(monkeypatch, _FakeIndex({}, raises=MemoryError("pgvector connect failed")))
    outcome = LiveGateRunner().cortex(default_config())
    assert not outcome.metrics  # nothing measured
    assert outcome.error is not None
    assert "unreachable" in outcome.error and "M2" in outcome.error


# --- advisor curveball gate (vendored frozen packets + live lane, faked) -----

from pathlib import Path as _Path  # noqa: E402

#: The committed proof receipt behind the published 85.7% (Q4_K_M) run — used to
#: lock the ported scorer's verdict against real lane outputs (not just fakes).
_Q4KM_RESULTS = (
    _Path(__file__).resolve().parents[2]
    / "evidence"
    / "orionfold-advisor"
    / "advisor-curveball-v0.2-q4km.results.jsonl"
)


class _FakeLaneRunner:
    """A :class:`LiveGateRunner` whose lane call returns canned outputs by task_id."""

    def __new__(cls, out_by_taskid, order):
        from fieldkit.field_edition.verify import LiveGateRunner

        inst = LiveGateRunner()
        inst._out_by_taskid = out_by_taskid  # type: ignore[attr-defined]
        inst._order = list(order)  # type: ignore[attr-defined]
        inst._i = 0  # type: ignore[attr-defined]

        def _lane_chat(base, model, messages, **kw):  # noqa: ANN001
            tid = inst._order[inst._i]  # type: ignore[attr-defined]
            inst._i += 1  # type: ignore[attr-defined]
            return inst._out_by_taskid[tid]  # type: ignore[attr-defined]

        inst._lane_chat = _lane_chat  # type: ignore[assignment]
        return inst


def test_curveball_set_loads_and_sha_pins() -> None:
    from fieldkit.field_edition.advisor import (
        CURVEBALL_SET_SHA,
        curveball_set_sha,
        load_curveball_set,
    )

    cset = load_curveball_set()
    assert curveball_set_sha() == CURVEBALL_SET_SHA  # vendored file matches the pin
    assert len(cset.rows) == 21  # the frozen curveball-v0.2 slice
    assert cset.refusals_total == 9 and cset.curveball_floor == 0.80
    assert cset.reasoning_mode == "off"  # /no_think baked + enable_thinking=False
    # every packet carries a system + a user message (the baked request).
    assert all(len(p.messages) == 2 for p in cset.rows)


def test_curveball_set_sha_drift_raises(tmp_path) -> None:
    import json as _json

    import pytest

    from fieldkit.field_edition.advisor import CURVEBALL_SET_PATH, load_curveball_set

    tampered = tmp_path / "tampered.json"
    doc = _json.loads(CURVEBALL_SET_PATH.read_text())
    doc["note_added_out_of_band"] = "drift"  # benign edit → different sha
    tampered.write_text(_json.dumps(doc, indent=2, sort_keys=True) + "\n")
    with pytest.raises(ValueError, match="sha drift"):
        load_curveball_set(tampered)
    # …but an explicit opt-out still loads it
    assert load_curveball_set(tampered, verify_sha=False).rows


def test_score_output_citation_refusal_route() -> None:
    from fieldkit.field_edition.advisor import score_output

    # answer row: correct exact citation passes
    answer = {"expected_behavior": "answer", "expected_source_ids": ["product_x"], "messages": []}
    assert score_output(answer, "The answer is here.\nCitations: [product_x]")["passed"]
    # wrong/empty citation fails the answer row
    assert not score_output(answer, "The answer.\nCitations: []")["passed"]
    # refuse row: must say it cannot answer AND carry no citations
    refuse = {"expected_behavior": "refuse", "expected_source_ids": [], "messages": []}
    assert score_output(refuse, "The context does not support this. Citations: []")["passed"]
    assert not score_output(refuse, "Sure: foo. Citations: [leaked]")["passed"]
    # route row: must start with Route:
    route = {"expected_behavior": "route", "expected_source_ids": ["p"], "messages": []}
    assert score_output(route, "Route: do X.\nCitations: [p]")["passed"]
    assert not score_output(route, "Do X.\nCitations: [p]")["passed"]


def test_score_output_flags_thinking_leak() -> None:
    from fieldkit.field_edition.advisor import score_output

    pkt = {"expected_behavior": "answer", "expected_source_ids": ["s"], "messages": []}
    assert not score_output(pkt, "<think>plan</think>Answer. Citations: [s]")["passed"]


def test_score_curveball_set_aggregates_floor_and_refusals() -> None:
    from fieldkit.field_edition.advisor import CurveballPacket, score_curveball_set

    packets = (
        CurveballPacket("a", "f", "s", "answer", ("src",), (), ()),
        CurveballPacket("r1", "f", "s", "refuse", (), (), ()),
        CurveballPacket("r2", "f", "s", "refuse", (), (), ()),
    )
    outputs = ["Body.\nCitations: [src]", "Does not support. Citations: []", "Sure. Citations: [x]"]
    rep = score_curveball_set(packets, outputs)
    assert rep.total == 3 and rep.passed == 2
    assert rep.refusals_total == 2 and rep.refusals_passed == 1  # r2 leaked a citation
    m = rep.as_metrics()
    assert m["curveball_v02"] == 2 / 3 and m["refusals_passed"] == 1.0 and m["refusals_total"] == 2.0


def test_score_curveball_set_length_mismatch_raises() -> None:
    import pytest

    from fieldkit.field_edition.advisor import CurveballPacket, score_curveball_set

    with pytest.raises(ValueError, match="length mismatch"):
        score_curveball_set((CurveballPacket("a", "f", "s", "answer", (), (), ()),), [])


def test_live_advisor_gate_reproduces_published_857(monkeypatch) -> None:
    """The wired gate scores the captured Q4_K_M outputs at the published 85.7%.

    This locks the ported scorer against the REAL frozen lane outputs (not only
    synthetic fakes) — the byte-for-byte verdict that backs the receipt."""
    import json as _json

    import pytest

    from fieldkit.field_edition.advisor import load_curveball_set
    from fieldkit.field_edition.verify import assess_gate

    if not _Q4KM_RESULTS.exists():  # pragma: no cover - evidence not vendored in some checkouts
        pytest.skip("frozen Q4_K_M curveball results not present")

    out_by_taskid = {
        _json.loads(line)["task_id"]: _json.loads(line)["output"]
        for line in _Q4KM_RESULTS.read_text().splitlines()
        if line.strip()
    }
    cset = load_curveball_set()
    runner = _FakeLaneRunner(out_by_taskid, [p.task_id for p in cset.rows])

    outcome = runner.advisor(default_config())
    assert outcome.error is None  # lane "reachable" (faked), real measurement
    assert outcome.metrics["curveball_v02"] == pytest.approx(18 / 21)
    assert outcome.metrics["refusals_passed"] == 9.0 and outcome.metrics["refusals_total"] == 9.0
    # the three known safe-direction misses are named in the note.
    for miss in ("0005", "0009", "0011"):
        assert miss in outcome.note
    # …and the pure §8 floor turns that into a PASS.
    passed, detail = assess_gate("advisor", outcome.metrics)
    assert passed and "85.7%" in detail and "9/9" in detail


def test_live_advisor_gate_refusal_regression_fails_floor(monkeypatch) -> None:
    """One refusal miss fails the gate even above the 80% curveball floor."""
    from fieldkit.field_edition.advisor import load_curveball_set
    from fieldkit.field_edition.verify import assess_gate

    cset = load_curveball_set()
    # Make every answer/route row pass and every refuse row leak → high overall
    # pass rate but refusals < 9/9.
    out_by_taskid: dict[str, str] = {}
    for p in cset.rows:
        if p.expected_behavior == "refuse":
            out_by_taskid[p.task_id] = "Sure, here it is. Citations: [leak]"  # bad refusal
        elif p.expected_behavior == "route":
            out_by_taskid[p.task_id] = "Route: do it.\nCitations: []"
        else:
            ids = p.expected_source_ids or ("x",)
            out_by_taskid[p.task_id] = "A sufficiently long answer body here.\nCitations: [%s]" % ids[0]
    runner = _FakeLaneRunner(out_by_taskid, [p.task_id for p in cset.rows])

    outcome = runner.advisor(default_config())
    assert outcome.metrics["refusals_passed"] == 0.0  # all refusals regressed
    passed, _ = assess_gate("advisor", outcome.metrics)
    assert not passed  # refusal floor (9/9) gates the pass regardless of curveball %


def test_live_advisor_gate_unreachable_lane_errors_honestly() -> None:
    """A dead lane port → an honest error with the fix, never a vanity pass.

    Uses a dead-port config so the assertion holds regardless of whether the
    dogfood box's real lane happens to be up at the moment."""
    from fieldkit.field_edition.verify import LiveGateRunner

    outcome = LiveGateRunner().advisor(_dead_stack_config())
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


# --- lane gate (warm-resident live smoke, faked) -----------------------------


def test_live_lane_warm_resident_pass() -> None:
    from fieldkit.field_edition.verify import LiveGateRunner, assess_gate

    runner = LiveGateRunner()
    runner._lane_models = lambda base: "model-Q4_K_M.gguf"  # type: ignore[assignment]
    runner._lane_chat = lambda base, model, messages, **kw: "ready."  # type: ignore[assignment]
    outcome = runner.lane(default_config())
    assert outcome.error is None
    assert outcome.metrics == {"launched": 1.0, "generated": 1.0}
    assert "warm-resident" in outcome.note and "no teardown" in outcome.note
    assert assess_gate("lane", outcome.metrics)[0]


def test_live_lane_unreachable_errors() -> None:
    from fieldkit.field_edition.verify import LiveGateRunner

    outcome = LiveGateRunner().lane(_dead_stack_config())
    assert outcome.error is not None
    assert "unreachable" in outcome.error and "M2" in outcome.error


def test_live_lane_reachable_but_empty_generation_fails() -> None:
    # Lane up (/v1/models ok) but a blank completion → a real FAIL, not an
    # honest-error (report=reality: the lane is up but cannot serve).
    from fieldkit.field_edition.verify import LiveGateRunner, assess_gate

    runner = LiveGateRunner()
    runner._lane_models = lambda base: "model-Q4_K_M.gguf"  # type: ignore[assignment]
    runner._lane_chat = lambda base, model, messages, **kw: "   "  # type: ignore[assignment]
    outcome = runner.lane(default_config())
    assert outcome.error is None  # it ran — this is a measured fail, not an error
    assert outcome.metrics == {"launched": 1.0, "generated": 0.0}
    assert not assess_gate("lane", outcome.metrics)[0]


# --- grounded-contract half (pure: probe selection + prompt + scorer) --------


def test_select_contract_probes_deterministic_and_stratified() -> None:
    from fieldkit.field_edition.grounded import DEFAULT_ANSWER_PER_FAMILY, select_contract_probes
    from fieldkit.field_edition.recall import load_recall_set

    rows = load_recall_set().rows
    a = select_contract_probes(rows)
    b = select_contract_probes(rows)
    assert [p.task_id for p in a] == [p.task_id for p in b]  # deterministic
    # every refuse + route row is kept (the hygiene/routing signal)
    refuse_route_in = sum(1 for r in rows if r.expected_behavior in ("refuse", "route"))
    refuse_route_out = sum(1 for p in a if p.expected_behavior in ("refuse", "route"))
    assert refuse_route_out == refuse_route_in
    # answer rows are capped per family
    by_fam: dict[str, int] = {}
    for p in a:
        if p.expected_behavior == "answer":
            by_fam[p.family] = by_fam.get(p.family, 0) + 1
    assert by_fam and all(n <= DEFAULT_ANSWER_PER_FAMILY for n in by_fam.values())


def test_build_grounded_blocks_dedups_and_caps() -> None:
    from fieldkit.field_edition.grounded import build_grounded_blocks

    hits = [
        {"slug": "src_a", "text": "alpha body", "source": "public_doc", "kind": "doc"},
        {"slug": "src_a", "text": "alpha body 2", "source": "public_doc", "kind": "doc"},  # dup slug
        {"slug": "src_b", "text": "beta body", "source": "public_spec", "kind": "spec"},
        {"slug": "src_c", "text": "gamma body", "source": "public_doc", "kind": "doc"},
    ]
    blocks = build_grounded_blocks(hits, "alpha", max_sources=2)
    assert [b["source_id"] for b in blocks] == ["src_a", "src_b"]  # deduped + capped at 2
    assert blocks[0]["excerpt"] == "alpha body"  # first chunk's text wins for src_a


def test_grounded_excerpt_is_query_centered_and_bounded() -> None:
    from fieldkit.field_edition.grounded import build_grounded_blocks

    long_text = ("Filler sentence one. " * 30) + "The unicorn metric is forty-two. " + ("Tail filler. " * 30)
    blocks = build_grounded_blocks(
        [{"slug": "s", "text": long_text, "source": "d", "kind": "d"}],
        "unicorn metric",
        excerpt_chars=120,
    )
    excerpt = blocks[0]["excerpt"]
    assert len(excerpt) <= 120
    assert "unicorn" in excerpt  # windowed around the query-relevant sentence


def test_build_messages_carries_contract_and_question() -> None:
    from fieldkit.field_edition.grounded import build_messages

    msgs = build_messages("What is X?", [{"source_id": "src_a", "citation_label": "src_a",
                                           "source_class": "d", "source_role": "d", "title": "t",
                                           "excerpt": "X is described here."}])
    assert msgs[0]["role"] == "system" and "Orionfold Advisor" in msgs[0]["content"]
    assert msgs[1]["role"] == "user"
    assert "Question: What is X?" in msgs[1]["content"]
    assert "Source 1: src_a" in msgs[1]["content"]


def test_score_grounded_citation_refusal_and_contract() -> None:
    from fieldkit.field_edition.grounded import GroundedProbe, score_grounded

    probes = [
        GroundedProbe("a", "fam", "qa", "answer", ("src_a",)),
        GroundedProbe("r", "fam", "qr", "refuse", ()),
        GroundedProbe("t", "fam", "qt", "route", ("src_t",)),
    ]
    outputs = [
        "A grounded answer body. Citations: [src_a]",
        "The retrieved public context does not support this question. Citations: []",
        "Route: hand off. Citations: [src_t]",
    ]
    rep = score_grounded(probes, outputs)
    assert rep.contract_pass
    assert rep.refusals_passed == rep.refusals_total == 1
    assert rep.cite_passed == rep.cite_total == 2
    assert rep.as_metrics()["contract_pass"] == 1.0


def test_score_grounded_refusal_hygiene_is_all_or_nothing() -> None:
    from fieldkit.field_edition.grounded import GroundedProbe, score_grounded

    probes = [
        GroundedProbe("a", "fam", "qa", "answer", ("src_a",)),
        GroundedProbe("r", "fam", "qr", "refuse", ()),
    ]
    # citation perfect (1/1) but a refusal regression → contract fails.
    outputs = ["Body. Citations: [src_a]", "Sure: foo. Citations: [leaked]"]
    rep = score_grounded(probes, outputs)
    assert rep.citation_rate == 1.0
    assert not rep.refusal_hygiene_ok
    assert not rep.contract_pass


def test_score_grounded_citation_floor() -> None:
    from fieldkit.field_edition.grounded import GROUNDED_CONTRACT_FLOOR, GroundedProbe, score_grounded

    # five answer rows, refusal clean; citation rate must clear the floor.
    probes = [GroundedProbe(f"a{i}", "fam", f"q{i}", "answer", (f"s{i}",)) for i in range(5)]
    good = [f"Body. Citations: [s{i}]" for i in range(5)]
    assert score_grounded(probes, good).contract_pass  # 5/5
    # drop two citations → 3/5 = 0.6 < floor
    bad = good[:3] + ["Body. Citations: []", "Body. Citations: []"]
    rep = score_grounded(probes, bad)
    assert rep.citation_rate < GROUNDED_CONTRACT_FLOOR and not rep.contract_pass


def test_score_grounded_length_mismatch_raises() -> None:
    import pytest

    from fieldkit.field_edition.grounded import GroundedProbe, score_grounded

    with pytest.raises(ValueError, match="length mismatch"):
        score_grounded([GroundedProbe("a", "f", "q", "answer", ("s",))], [])


# --- AC-7 v1 license file (schema + canonical bytes + Ed25519 verify) ---------

import base64 as _b64  # noqa: E402
from datetime import datetime as _dt, timezone as _tz  # noqa: E402

#: The openly-throwaway dev seed (00 01 … 1f) whose public half is in TRUSTED_KEYS.
_DEV_SEED_B64 = _b64.b64encode(bytes(range(32))).decode()


def _sample_payload():
    """A LEGACY token-bearing payload (a `registry` block with a `pull_token`).

    Kept as the back-compat fixture: post OPEN-1 the registry block is optional, but
    an older token-bearing license must still parse + verify unchanged. The current
    token-less shape is `_token_less_payload()`."""
    return {
        "schema": "orionfold.license/v1",
        "license_id": "OF-FE-2026-0042",
        "product": "arena-field-edition",
        "edition": "founding-25",
        "tier": "field-edition",
        "issued_to": {"name": "Test User", "email": "t@example.com", "org": "Acme"},
        "issued_at": "2026-06-14T00:00:00Z",
        "not_before": "2026-06-14T00:00:00Z",
        "expires_at": "2027-06-14T00:00:00Z",
        "seats": 1,
        "entitlements": ["proven-matrix-images", "signed-update-channel"],
        "registry": {
            "type": "ghcr", "host": "ghcr.io", "namespace": "orionfold",
            "username": "of-license-OF-FE-2026-0042", "pull_token": "ghp_test_token",
        },
    }


def _token_less_payload():
    """The CURRENT (OPEN-1) shape: claims + term only, no `registry` / pull token."""
    p = _sample_payload()
    p.pop("registry")
    return p


def _sign_doc(payload, *, key_id="of-license-dev-2026-06", seed=_DEV_SEED_B64):
    from fieldkit.field_edition.license import sign_payload

    return {"payload": payload, "signature": {"alg": "ed25519", "key_id": key_id, "value": sign_payload(payload, seed)}}


def test_canonical_bytes_is_sorted_and_compact() -> None:
    from fieldkit.field_edition.license import canonical_bytes

    a = canonical_bytes({"b": 1, "a": {"y": 2, "x": 1}})
    assert a == b'{"a":{"x":1,"y":2},"b":1}'  # recursive key sort, no whitespace


def test_vendored_sample_license_validates() -> None:
    import pytest

    pytest.importorskip("cryptography")
    from fieldkit.field_edition.license import DEFAULT_LICENSE_PATH, load_license  # noqa: F401
    from fieldkit.field_edition import license as lic_mod

    sample = _Path(lic_mod.__file__).resolve().parent / "data" / "license-sample.json"
    lic = load_license(sample, now=_dt(2026, 6, 15, tzinfo=_tz.utc))
    assert lic.license_id == "OF-FE-2026-0007"
    assert lic.has_entitlement("proven-matrix-images")
    # OPEN-1: the current vendored sample is token-less (claims + term only).
    assert lic.registry is None and lic.pull_token == ""


def test_sign_verify_round_trip(tmp_path) -> None:
    import json as _json

    import pytest

    pytest.importorskip("cryptography")
    from fieldkit.field_edition.license import load_license

    path = tmp_path / "license"
    path.write_text(_json.dumps(_sign_doc(_sample_payload())))
    lic = load_license(path, now=_dt(2026, 6, 15, tzinfo=_tz.utc))
    assert lic.tier == "field-edition" and lic.seats == 1
    assert lic.is_active(_dt(2026, 6, 15, tzinfo=_tz.utc))


def test_token_less_license_validates(tmp_path) -> None:
    # OPEN-1: a current license carries no `registry` block — it parses, verifies,
    # and term-checks exactly like a token-bearing one; `registry` is just None.
    import json as _json

    import pytest

    pytest.importorskip("cryptography")
    from fieldkit.field_edition.license import load_license

    path = tmp_path / "license"
    path.write_text(_json.dumps(_sign_doc(_token_less_payload())))
    lic = load_license(path, now=_dt(2026, 6, 15, tzinfo=_tz.utc))
    assert lic.registry is None and lic.pull_token == ""
    assert lic.tier == "field-edition" and lic.has_entitlement("proven-matrix-images")
    assert lic.is_active(_dt(2026, 6, 15, tzinfo=_tz.utc))


def test_legacy_token_bearing_license_still_validates(tmp_path) -> None:
    # Back-compat: an older token-bearing license must keep verifying unchanged,
    # and the legacy `pull_token` stays reachable through the optional registry.
    import json as _json

    import pytest

    pytest.importorskip("cryptography")
    from fieldkit.field_edition.license import load_license

    path = tmp_path / "license"
    path.write_text(_json.dumps(_sign_doc(_sample_payload())))
    lic = load_license(path, now=_dt(2026, 6, 15, tzinfo=_tz.utc))
    assert lic.registry is not None and lic.registry.type == "ghcr"
    assert lic.pull_token == "ghp_test_token"


def test_tampered_payload_fails_verification(tmp_path) -> None:
    import json as _json

    import pytest

    pytest.importorskip("cryptography")
    from fieldkit.field_edition.license import LicenseError, load_license

    doc = _sign_doc(_sample_payload())
    doc["payload"]["seats"] = 99  # mutate after signing → signature no longer matches
    path = tmp_path / "license"
    path.write_text(_json.dumps(doc))
    with pytest.raises(LicenseError, match="does not verify"):
        load_license(path, now=_dt(2026, 6, 15, tzinfo=_tz.utc))


def test_unknown_key_id_rejected(tmp_path) -> None:
    import json as _json

    import pytest

    pytest.importorskip("cryptography")
    from fieldkit.field_edition.license import LicenseError, load_license

    doc = _sign_doc(_sample_payload())
    doc["signature"]["key_id"] = "of-license-attacker"
    path = tmp_path / "license"
    path.write_text(_json.dumps(doc))
    with pytest.raises(LicenseError, match="unknown signing key"):
        load_license(path, now=_dt(2026, 6, 15, tzinfo=_tz.utc))


def test_prod_key_is_provisioned() -> None:
    # Ops delivered the prod public half (relay 2026-06-13); the slot is no longer
    # the PROD_KEY_PENDING sentinel — a real Ed25519 pubkey is embedded, so signing
    # is gated by actual signature verification, not the "not provisioned" guard.
    import base64

    import pytest

    pytest.importorskip("cryptography")
    from fieldkit.field_edition.license import (
        ACTIVE_KEY_ID,
        PROD_KEY_PENDING,
        TRUSTED_KEYS,
        LicenseError,
        verify_signature,
    )

    pub_b64 = TRUSTED_KEYS[ACTIVE_KEY_ID]
    assert pub_b64 != PROD_KEY_PENDING
    assert len(base64.b64decode(pub_b64)) == 32  # a raw Ed25519 public key
    # a bogus signature now fails on real verification, not on the pending guard
    with pytest.raises(LicenseError, match="does not verify"):
        verify_signature(_sample_payload(), {"alg": "ed25519", "key_id": ACTIVE_KEY_ID, "value": "AAAA"})


def test_expired_and_not_yet_valid_rejected(tmp_path) -> None:
    import json as _json

    import pytest

    pytest.importorskip("cryptography")
    from fieldkit.field_edition.license import LicenseError, load_license

    path = tmp_path / "license"
    path.write_text(_json.dumps(_sign_doc(_sample_payload())))
    # after expiry
    with pytest.raises(LicenseError, match="expired"):
        load_license(path, now=_dt(2027, 6, 15, tzinfo=_tz.utc))
    # before not_before
    with pytest.raises(LicenseError, match="not valid until"):
        load_license(path, now=_dt(2026, 6, 1, tzinfo=_tz.utc))
    # …but signature-only load (enforce_term=False) still parses it
    lic = load_license(path, now=_dt(2027, 6, 15, tzinfo=_tz.utc), enforce_term=False)
    assert lic.license_id == "OF-FE-2026-0042"


def test_missing_file_and_bad_schema_are_actionable(tmp_path) -> None:
    import json as _json

    import pytest

    from fieldkit.field_edition.license import LicenseError, load_license, parse_license

    with pytest.raises(LicenseError, match="no license file"):
        load_license(tmp_path / "nope")
    with pytest.raises(LicenseError, match="unexpected license schema"):
        parse_license({"schema": "wrong", "license_id": "x"})
    with pytest.raises(LicenseError, match="missing required field"):
        parse_license({"schema": "orionfold.license/v1"})


def test_license_soft_known_set_does_not_reject(tmp_path, caplog) -> None:
    # Unrecognized tier/edition + an unknown entitlement must LOAD (descriptive,
    # not security-bearing) — surfaced as soft notes/warnings, never an error.
    import json as _json
    import logging

    import pytest

    pytest.importorskip("cryptography")
    from fieldkit.field_edition.license import load_license

    payload = _sample_payload()
    payload["tier"] = "enterprise-trial"        # not in KNOWN_TIERS
    payload["edition"] = "team-2027"            # not in KNOWN_EDITIONS
    payload["entitlements"] = ["proven-matrix-images", "future-capability-x"]
    path = tmp_path / "license"
    path.write_text(_json.dumps(_sign_doc(payload)))

    with caplog.at_level(logging.WARNING, logger="fieldkit.field_edition.license"):
        lic = load_license(path, now=_dt(2026, 6, 15, tzinfo=_tz.utc))
    # loads fine; recognition flags are honest
    assert not lic.tier_recognized and not lic.edition_recognized
    assert lic.unknown_entitlements == ("future-capability-x",)
    assert lic.has_entitlement("proven-matrix-images")  # known one still works
    notes = lic.recognition_notes()
    assert any("tier" in n for n in notes) and any("edition" in n for n in notes)
    assert any("unknown entitlements" in n for n in notes)
    # the soft warning was emitted at load (visible, not fatal)
    assert any("treating as generic" in r.message for r in caplog.records)


def test_license_known_values_have_no_notes(tmp_path) -> None:
    import json as _json

    import pytest

    pytest.importorskip("cryptography")
    from fieldkit.field_edition.license import (
        KNOWN_EDITIONS,
        KNOWN_ENTITLEMENTS,
        KNOWN_TIERS,
        load_license,
    )

    # the vendored-style sample uses only known values → zero recognition noise
    assert "field-edition" in KNOWN_TIERS and "founding-25" in KNOWN_EDITIONS
    assert "proven-matrix-images" in KNOWN_ENTITLEMENTS
    path = tmp_path / "license"
    path.write_text(_json.dumps(_sign_doc(_sample_payload())))
    lic = load_license(path, now=_dt(2026, 6, 15, tzinfo=_tz.utc))
    assert lic.tier_recognized and lic.edition_recognized
    assert lic.unknown_entitlements == () and lic.recognition_notes() == []


def _conformance_vector():
    import json as _json
    from pathlib import Path as _Path

    from fieldkit.field_edition import license as lic_mod

    vector = _Path(lic_mod.__file__).resolve().parent / "data" / "license-conformance-v1.json"
    return _json.loads(vector.read_text(encoding="utf-8"))


def test_license_conformance_vector_matches_live_verifier() -> None:
    """The shared canonicalization+signing contract (Mac's `fulfillLicense` mirrors
    this in its CI). If `canonical_bytes`/`sign_payload` ever drift from the frozen
    vector, this fails — and so would every customer license. See
    `_SPECS/arena-field-edition-license-workflow-v1.md` §6."""
    import hashlib as _hl

    import pytest

    pytest.importorskip("cryptography")
    from fieldkit.field_edition.license import (
        TRUSTED_KEYS,
        canonical_bytes,
        sign_payload,
        verify_signature,
    )

    doc = _conformance_vector()
    assert doc["schema"] == "orionfold.license/v1" and doc["algorithm"] == "ed25519"

    dev = doc["dev_key"]
    key_id = dev["key_id"]
    # The vector's dev pubkey must be the one the installer trusts …
    assert TRUSTED_KEYS[key_id] == dev["public_key_b64"]
    # … and the published throwaway seed must actually derive that pubkey.
    from cryptography.hazmat.primitives import serialization as _ser
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    seed = _b64.b64decode(dev["private_seed_b64"])
    derived = Ed25519PrivateKey.from_private_bytes(seed).public_key().public_bytes(
        _ser.Encoding.Raw, _ser.PublicFormat.Raw
    )
    assert _b64.b64encode(derived).decode() == dev["public_key_b64"]

    assert doc["case_count"] == len(doc["cases"]) >= 4
    for case in doc["cases"]:
        payload = case["payload"]
        canon = canonical_bytes(payload)
        # canonical bytes byte-identical to the frozen string + sha
        assert canon.decode("utf-8") == case["canonical_utf8"], case["name"]
        assert _hl.sha256(canon).hexdigest()[:12] == case["canonical_sha256_12"], case["name"]
        # re-signing the payload reproduces the frozen signature (Ed25519 is deterministic)
        assert sign_payload(payload, dev["private_seed_b64"]) == case["signature_b64"], case["name"]
        # and that signature verifies against the trusted dev key
        verify_signature(payload, {"alg": "ed25519", "key_id": key_id, "value": case["signature_b64"]})

    # the four traps must all be represented (recursive sort, utf-8, scalars, full license)
    names = {c["name"] for c in doc["cases"]}
    assert {"nested-key-sort", "unicode-utf8", "scalars-no-floats", "full-license-founding25"} <= names


# --- cosign verification of the proven-matrix images (§9) --------------------

from pathlib import Path as _Path  # noqa: E402

from fieldkit.field_edition import (  # noqa: E402
    CosignVerifyError,
    LiveUpdateChannel,
    PROVEN_MATRIX_COSIGN_PUBKEY,
    orionfold_image_refs,
    verify_matrix,
)
from fieldkit.field_edition import cosign as cosign_mod  # noqa: E402

_LANE = "ghcr.io/orionfold/llama-server-cuda13@sha256:93993cc2"
_PG = "pgvector/pgvector@sha256:7d400e"
_NIM = "nvcr.io/nim/nvidia/llama-nemotron-embed-1b-v2@sha256:3c22c0"


def _signed_matrix():
    return ProvenMatrix(
        "2026.q3", "0.31.0",
        {"advisor-lane": _LANE, "cortex-db": _PG, "embedder": _NIM},
        signed=True,
    )


def test_cosign_orionfold_image_refs_filters_to_ours():
    # only the digest-pinned ghcr.io/orionfold image — not pgvector / NVIDIA NIM.
    assert orionfold_image_refs(_signed_matrix()) == [_LANE]
    # a non-digest (tag-only) Orionfold ref is excluded (can't verify a moving tag).
    m = ProvenMatrix("v", "0.31.0", {"x": "ghcr.io/orionfold/cortex-embedder:0.1"})
    assert orionfold_image_refs(m) == []


def test_cosign_verify_matrix_passes_with_fake_runner():
    seen = []
    def ok(cmd):
        seen.append(list(cmd))
        return 0, "Verified OK"
    refs = verify_matrix(_signed_matrix(), runner=ok)
    assert refs == [_LANE]
    # it shelled the pinned key + the ref to cosign verify.
    assert seen and seen[0][:3] == ["cosign", "verify", "--key"]
    assert seen[0][-1] == _LANE
    assert "--insecure-ignore-tlog=true" not in seen[0]  # tlog checked by default


def test_cosign_verify_matrix_ignore_tlog_flag_threads_through():
    seen = []
    verify_matrix(_signed_matrix(), runner=lambda c: (seen.append(list(c)) or (0, "")), ignore_tlog=True)
    assert "--insecure-ignore-tlog=true" in seen[0]


def test_cosign_verify_matrix_rejects_bad_signature():
    import pytest
    with pytest.raises(CosignVerifyError) as ei:
        verify_matrix(_signed_matrix(), runner=lambda c: (1, "no matching signatures"))
    assert "no matching signatures" in ei.value.fix


def test_cosign_verify_matrix_rejects_no_orionfold_images():
    import pytest
    m = ProvenMatrix("v", "0.31.0", {"cortex-db": _PG, "embedder": _NIM}, signed=True)
    with pytest.raises(CosignVerifyError) as ei:
        verify_matrix(m, runner=lambda c: (0, ""))
    assert "pins no Orionfold" in str(ei.value)


def test_cosign_verify_image_missing_binary_is_honest():
    import pytest
    def gone(cmd):
        raise FileNotFoundError("cosign")
    with pytest.raises(CosignVerifyError) as ei:
        cosign_mod.verify_image(_LANE, runner=gone)
    assert "cosign not found" in str(ei.value)


def test_live_update_channel_verify_signature_rejects_unsigned():
    import pytest
    m = ProvenMatrix("v", "0.31.0", {"advisor-lane": _LANE}, signed=False)
    with pytest.raises(UpdateError) as ei:
        LiveUpdateChannel().verify_signature(m)
    assert "unsigned" in str(ei.value)


def test_live_update_channel_verify_signature_cosign_pass():
    # signed matrix + a passing cosign runner → no raise (the live gate accepts it).
    chan = LiveUpdateChannel(cosign_runner=lambda c: (0, "Verified OK"))
    chan.verify_signature(_signed_matrix())  # must not raise


def test_live_update_channel_verify_signature_cosign_fail_maps_to_update_error():
    import pytest
    chan = LiveUpdateChannel(cosign_runner=lambda c: (1, "tampered"))
    with pytest.raises(UpdateError) as ei:
        chan.verify_signature(_signed_matrix())
    assert "tampered" in ei.value.fix


def test_proven_matrix_cosign_pubkey_matches_committed_pin():
    # The packaged constant must byte-match the operator-facing committed key.
    # (Skips in an installed-wheel context where deploy/ isn't present.)
    pin = _Path(__file__).resolve().parents[2] / "deploy/field-edition/cosign/proven-matrix.pub"
    if not pin.exists():
        import pytest
        pytest.skip("deploy/ pin not present (installed-wheel context)")
    assert pin.read_text(encoding="utf-8").strip() == PROVEN_MATRIX_COSIGN_PUBKEY.strip()
