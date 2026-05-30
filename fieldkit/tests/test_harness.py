# Copyright 2026 Manav Sehgal
# SPDX-License-Identifier: Apache-2.0
"""Unit + Spark-live tests for fieldkit.harness (H1 + H2 surface).

Unit tests mock `subprocess.run` and the lazily-imported sibling-module
functions, so they stay green on any laptop. The `@pytest.mark.spark` tests
need the live `hermes` CLI and (for the NIM lane) the cached Spark NIM image;
they're skipped without `pytest --spark`.

H1 surface: install_hermes (two-key safety), hermes_doctor + DoctorReport
(section-aware classification), HermesConfig / EnvFile / configure_hermes, the
NIM + llama-server lanes, resolve_lane, and serve_lane's unified-memory guard.

H2 surface: VLLMLane (docker recipe + the R8 EngineCore orphan-sweep teardown)
+ OllamaLane; the Hermes session-export → AgentRun parser + tool_call_reliability
+ HarnessEvalResult (the agent-critical metrics); HarnessProfile.render/.files/
.to_manifest + publish_harness dry-run; the `harness`/`skill` artifact kinds.
"""

from __future__ import annotations

import subprocess

import pytest

import fieldkit.harness as h
from fieldkit.harness import (
    DEFAULT_HARDENING,
    LOCAL_PROVIDERS,
    CostRouterConfig,
    DoctorCheck,
    DoctorReport,
    EnvFile,
    HardeningError,
    HardeningPolicy,
    HarnessError,
    HarnessEvalResult,
    HarnessProfile,
    HermesConfig,
    HermesNotInstalled,
    LaneMetricColumns,
    LaneSpec,
    LlamaServerLane,
    NIMLane,
    OllamaLane,
    RouteTier,
    RouterConfig,
    RoutingError,
    ServingLane,
    ServingLaneError,
    UnifiedMemoryExceeded,
    VLLMLane,
    VerticalRoute,
    agent_runs_from_hermes_sessions,
    build_cost_router,
    build_vertical_router,
    configure_hermes,
    estimate_tokens,
    harden_config,
    hermes_doctor,
    install_hermes,
    lane_spec_for_vertical,
    publish_harness,
    resolve_lane,
    serve_lane,
    tool_call_reliability,
)


# --- LaneSpec --------------------------------------------------------------


def test_lanespec_base_url() -> None:
    assert LaneSpec("nim", "m", host="127.0.0.1", port=8000).base_url == "http://127.0.0.1:8000/v1"
    assert LaneSpec("x", "m", host="h", port=9).base_url == "http://h:9/v1"


# --- NIMLane ---------------------------------------------------------------


def test_nimlane_image_resolution() -> None:
    short = NIMLane(LaneSpec("nim", "nemotron-nano-9b-v2-dgx-spark"))
    assert short.image == "nvcr.io/nim/nvidia/nvidia-nemotron-nano-9b-v2-dgx-spark:latest"
    full = NIMLane(LaneSpec("nim", "nvcr.io/nim/custom/foo:1.0"))
    assert full.image == "nvcr.io/nim/custom/foo:1.0"
    override = NIMLane(LaneSpec("nim", "x"), image="my/img:tag")
    assert override.image == "my/img:tag"


def test_nimlane_docker_cmd_carries_recipe() -> None:
    lane = NIMLane(LaneSpec("nim", "m", port=8000), max_batch_size=32,
                   extra_env={"NIM_LOG_LEVEL": "INFO"})
    argv = lane.docker_run_cmd()
    s = " ".join(argv)
    assert "--network host" in s and "--gpus all" in s
    assert "NIM_MAX_BATCH_SIZE=32" in argv
    assert "NIM_LOG_LEVEL=INFO" in argv
    assert any(a.endswith(":/opt/nim/.cache") for a in argv)
    assert "fk-nim-8000" in argv  # derived container name
    assert argv[-1] == lane.image


def test_nimlane_weight_bytes_footprint_override() -> None:
    lane = NIMLane(LaneSpec("nim", "m"), footprint_gb=95.0)
    assert lane.weight_bytes() == int(95e9)
    # without override falls back to capabilities.weight_bytes (9B bf16 = 18 GB)
    lane2 = NIMLane(LaneSpec("nim", "m"), params_b=9.0, dtype="bf16")
    assert lane2.weight_bytes() == int(9 * 1e9 * 2)


def test_nimlane_start_failure_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = []

    def fake_run(cmd, **kw):  # noqa: ANN001
        calls.append(cmd)
        if cmd[:3] == ["docker", "rm", "-f"]:
            return subprocess.CompletedProcess(cmd, 0, "", "")
        return subprocess.CompletedProcess(cmd, 1, "", "boom: no gpu")

    monkeypatch.setattr(subprocess, "run", fake_run)
    with pytest.raises(ServingLaneError, match="boom: no gpu"):
        NIMLane(LaneSpec("nim", "m")).start()
    # it removed the stale container before run
    assert calls[0][:3] == ["docker", "rm", "-f"]


def test_nimlane_wait_for_warm_delegates(monkeypatch: pytest.MonkeyPatch) -> None:
    seen = {}

    def fake_warm(base_url, **kw):  # noqa: ANN001
        seen["url"] = base_url
        return True

    monkeypatch.setattr("fieldkit.nim.wait_for_warm", fake_warm)
    lane = NIMLane(LaneSpec("nim", "m", port=8000))
    assert lane.wait_for_warm(timeout=5) is True
    assert seen["url"] == "http://127.0.0.1:8000/v1"


# --- LlamaServerLane (delegates to notebook.local_server) ------------------


def test_llamaserver_lane_delegates(monkeypatch: pytest.MonkeyPatch) -> None:
    import contextlib

    entered = {}

    @contextlib.contextmanager
    def fake_local_server(repo, **kw):  # noqa: ANN001
        entered["repo"] = repo
        entered["kw"] = kw
        yield f"http://{kw['host']}:{kw['port']}"

    monkeypatch.setattr("fieldkit.notebook.local_server", fake_local_server)
    spec = LaneSpec("llama-server", "Org/Repo-GGUF", port=8080,
                    extra={"variant": "Q5_K_M", "ignored_key": 1})
    lane = LlamaServerLane(spec)
    lane.start()
    assert entered["repo"] == "Org/Repo-GGUF"
    assert entered["kw"]["variant"] == "Q5_K_M"
    assert entered["kw"]["port"] == 8080
    assert "ignored_key" not in entered["kw"]  # only known kwargs forwarded
    assert lane.wait_for_warm() is True
    lane.teardown()
    assert lane._endpoint is None


# --- resolve_lane ----------------------------------------------------------


def test_resolve_lane_registry() -> None:
    assert isinstance(resolve_lane(LaneSpec("nim", "m")), NIMLane)
    assert isinstance(resolve_lane(LaneSpec("llama-server", "r")), LlamaServerLane)


def test_resolve_lane_unknown_provider() -> None:
    with pytest.raises(ServingLaneError, match="no serving lane for provider 'nope'"):
        resolve_lane(LaneSpec("nope", "m"))


# --- serve_lane guard + lifecycle ------------------------------------------


class _RecordingLane(ServingLane):
    provider = "rec"

    def __init__(self, spec: LaneSpec, *, gb: float, events: list[str]) -> None:
        super().__init__(spec)
        self._gb = gb
        self.events = events

    def weight_bytes(self) -> int:
        return int(self._gb * 1e9)

    def start(self) -> None:
        self.events.append("start")

    def wait_for_warm(self, timeout: float = 180.0) -> bool:
        self.events.append("warm")
        return True

    def teardown(self) -> None:
        self.events.append("teardown")


def test_serve_lane_guard_refuses_oversized(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(h, "_available_memory_gb", lambda: 30.0)
    ev: list[str] = []
    with pytest.raises(UnifiedMemoryExceeded, match="exceeds 30.0 GB"):
        with serve_lane(_RecordingLane(LaneSpec("rec", "m"), gb=200, events=ev)):
            pass
    assert ev == []  # never started


def test_serve_lane_lifecycle_and_teardown_on_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(h, "_available_memory_gb", lambda: 116.0)
    ev: list[str] = []
    with serve_lane(_RecordingLane(LaneSpec("rec", "m"), gb=18, events=ev)):
        ev.append("body")
    assert ev == ["start", "warm", "body", "teardown"]

    # teardown still runs if the body raises
    ev2: list[str] = []
    with pytest.raises(ValueError):
        with serve_lane(_RecordingLane(LaneSpec("rec", "m"), gb=18, events=ev2)):
            raise ValueError("boom")
    assert ev2[-1] == "teardown"


def test_serve_lane_guard_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(h, "_available_memory_gb", lambda: 1.0)
    ev: list[str] = []
    with serve_lane(_RecordingLane(LaneSpec("rec", "m"), gb=200, events=ev), guard=False):
        pass
    assert "start" in ev  # guard bypassed


def test_serve_lane_warm_timeout_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(h, "_available_memory_gb", lambda: 116.0)

    class NeverWarm(_RecordingLane):
        def wait_for_warm(self, timeout: float = 180.0) -> bool:
            return False

    with pytest.raises(ServingLaneError, match="did not warm"):
        with serve_lane(NeverWarm(LaneSpec("rec", "m"), gb=1, events=[])):
            pass


def test_serve_lane_accepts_bare_spec(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(h, "_available_memory_gb", lambda: 116.0)
    # resolve to NIMLane but mock its lifecycle so nothing real runs
    monkeypatch.setattr(NIMLane, "start", lambda self: None)
    monkeypatch.setattr(NIMLane, "wait_for_warm", lambda self, timeout=180.0: True)
    monkeypatch.setattr(NIMLane, "teardown", lambda self: None)
    monkeypatch.setattr(NIMLane, "weight_bytes", lambda self: int(18e9))
    with serve_lane(LaneSpec("nim", "m")) as lane:
        assert isinstance(lane, NIMLane)


# --- install_hermes (two-key safety) ---------------------------------------


def test_install_hermes_dry_run_returns_command() -> None:
    cmd = install_hermes()
    assert cmd == f"curl -fsSL {h.HERMES_INSTALL_URL} | bash"


def test_install_hermes_requires_both_keys() -> None:
    with pytest.raises(HarnessError, match="two-key safety"):
        install_hermes(dry_run=False)  # allow_pipe_to_bash defaults False


def test_install_hermes_unknown_method() -> None:
    with pytest.raises(HarnessError, match="unknown install method"):
        install_hermes(method="pip")


def test_install_hermes_executes_with_both_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    ran = {}

    def fake_run(cmd, **kw):  # noqa: ANN001
        ran["cmd"] = cmd
        ran["shell"] = kw.get("shell")
        return subprocess.CompletedProcess(cmd, 0, "ok", "")

    monkeypatch.setattr(subprocess, "run", fake_run)
    cmd = install_hermes(dry_run=False, allow_pipe_to_bash=True)
    assert ran["shell"] is True
    assert "curl -fsSL" in ran["cmd"] and cmd.endswith("| bash")


# --- hermes_doctor + DoctorReport ------------------------------------------

_DOCTOR_SAMPLE = """
┌─ Hermes Doctor ─┐
◆ Security Advisories
  ✓ No active security advisories
◆ Python Environment
  ✓ Python 3.11.15
  ✓ Virtual environment active
◆ Required Packages
  ✓ OpenAI SDK
  ✓ PyYAML
  ⚠ python-telegram-bot (optional, not installed)
◆ Configuration Files
  ✓ ~/.hermes/.env file exists
  ✓ ~/.hermes/config.yaml exists
◆ Auth Providers
  ⚠ Nous Portal auth (not logged in)
◆ External Tools
  ✗ ripgrep (rg) not found (file search uses grep fallback)
◆ Tool Availability
  ✗ discord (missing DISCORD_BOT_TOKEN)
  ✗ spotify (system dependency not met)
◆ Directory Structure
  ✓ ~/.hermes directory exists
"""


def _patch_doctor(monkeypatch: pytest.MonkeyPatch, raw: str, *, present: bool = True) -> None:
    monkeypatch.setattr("shutil.which", lambda b: "/usr/bin/hermes" if present else None)
    monkeypatch.setattr(
        subprocess, "run",
        lambda *a, **k: subprocess.CompletedProcess(a, 0, raw, ""),
    )


def test_hermes_doctor_section_aware_clean(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_doctor(monkeypatch, _DOCTOR_SAMPLE)
    rep = hermes_doctor()
    # the two ✗ (external tools, tool availability) + the ⚠ optionals are NOT required
    assert rep.ok is True
    assert rep.n_failed == 0
    # but they were still parsed (with sections + required flags)
    discord = next(c for c in rep.checks if c.name.startswith("discord"))
    assert discord.ok is False and discord.required is False and discord.section == "Tool Availability"
    telegram = next(c for c in rep.checks if "telegram" in c.name)
    assert telegram.required is False  # optional-line hint inside a core section


def test_hermes_doctor_core_failure_flags(monkeypatch: pytest.MonkeyPatch) -> None:
    bad = _DOCTOR_SAMPLE.replace("✓ Virtual environment active", "✗ Virtual environment NOT active")
    _patch_doctor(monkeypatch, bad)
    rep = hermes_doctor()
    assert rep.ok is False
    assert rep.n_failed == 1
    assert "Virtual environment NOT active" in rep.report()


def test_hermes_doctor_not_installed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("shutil.which", lambda b: None)
    monkeypatch.setattr("pathlib.Path.exists", lambda self: False)
    with pytest.raises(HermesNotInstalled, match="not found"):
        hermes_doctor()


def test_doctor_report_render_and_ok() -> None:
    r = DoctorReport(checks=[
        DoctorCheck("Python 3.11", True, section="Python Environment"),
        DoctorCheck("Nous (not logged in)", False, required=False, section="Auth Providers"),
        DoctorCheck("Config missing", False, section="Configuration Files"),
    ])
    assert r.ok is False and r.n_failed == 1
    out = r.report()
    assert "✓ Python 3.11" in out and "⚠ Nous" in out and "✗ Config missing" in out
    assert "1 required failure" in out


# --- HermesConfig / EnvFile / configure_hermes -----------------------------


def test_hermes_config_render_yaml() -> None:
    cfg = HermesConfig(provider="custom", base_url="http://127.0.0.1:8000/v1",
                       model="nvidia/nemotron-nano-9b-v2")
    out = cfg.render()
    assert out.startswith("model:")
    assert "provider: custom" in out
    assert "base_url:" in out and "127.0.0.1:8000/v1" in out
    assert "default: nvidia/nemotron-nano-9b-v2" in out


def test_hermes_config_set_commands_and_extra() -> None:
    cfg = HermesConfig(model="m", extra={"temperature": 0})
    cmds = cfg.config_set_commands()
    assert cmds[0] == "hermes config set model.provider custom"
    assert any("model.default m" in c for c in cmds)
    assert "temperature: 0" in cfg.render()


def test_envfile_render_sorted() -> None:
    env = EnvFile(values={"B": "2", "A": "1"})
    assert env.render() == "A=1\nB=2"


def test_configure_hermes_from_lane() -> None:
    lane = NIMLane(LaneSpec("nim", "m", port=8000))
    cfg, env = configure_hermes(lane=lane, model="nvidia/nemotron-nano-9b-v2")
    assert cfg.base_url == "http://127.0.0.1:8000/v1"
    assert env.values["OPENAI_BASE_URL"] == "http://127.0.0.1:8000/v1"
    assert env.values["OPENAI_API_KEY"] == "local"
    assert env.values["HERMES_STREAM_READ_TIMEOUT"] == "1800"


def test_configure_hermes_explicit_base_url_no_slow() -> None:
    cfg, env = configure_hermes(base_url="http://h:9/v1", slow_serving=False)
    assert cfg.base_url == "http://h:9/v1"
    assert "HERMES_STREAM_READ_TIMEOUT" not in env.values


def test_configure_hermes_autodiscover(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("fieldkit.notebook.discover_local_server", lambda: "http://127.0.0.1:8080")
    cfg, _ = configure_hermes()
    assert cfg.base_url == "http://127.0.0.1:8080/v1"  # /v1 appended


def test_configure_hermes_nothing_found(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("fieldkit.notebook.discover_local_server", lambda: None)
    with pytest.raises(HarnessError, match="no local server discovered"):
        configure_hermes()


# --- harden_config / HardeningPolicy (H3) ----------------------------------


def test_default_hardening_is_the_spec_baseline() -> None:
    p = DEFAULT_HARDENING
    assert p.terminal_backend == "docker"      # sandbox, not host `local`
    assert p.network_egress == "deny"
    assert p.secrets_from_env_only is True
    assert p.local_first is True
    assert p.approval_mode == "manual"
    assert p.hard_stop_loops is True


def test_harden_config_maps_to_real_hermes_keys() -> None:
    cfg = HermesConfig(provider="custom", base_url="http://127.0.0.1:8000/v1", model="m")
    h = harden_config(cfg)
    s = h.sections
    # model block is untouched
    assert h.provider == "custom" and h.model == "m"
    # the real Hermes hardening keys (verified against the v0.14.0 schema)
    assert s["terminal"]["backend"] == "docker"
    assert s["terminal"]["container_persistent"] is False
    assert s["terminal"]["docker_extra_args"] == ["--network=none"]
    assert s["tool_loop_guardrails"]["hard_stop_enabled"] is True
    assert s["approvals"]["mode"] == "manual" and s["approvals"]["cron_mode"] == "deny"
    assert s["agent"]["max_turns"] == 30 and s["agent"]["subagent_auto_approve"] is False
    assert s["session_reset"]["mode"] == "both"


def test_harden_config_is_pure() -> None:
    cfg = HermesConfig()
    h = harden_config(cfg)
    assert cfg.sections == {}      # input untouched
    assert h is not cfg and h.sections  # new object, populated


def test_harden_config_render_emits_sections_after_model() -> None:
    h = harden_config(HermesConfig(model="m"))
    out = h.render()
    assert out.startswith("model:")
    assert "\nterminal:" in out and "backend: docker" in out
    assert "hard_stop_enabled: true" in out           # bool lowercased
    assert '- "--network=none"' in out                 # list rendered structurally


def test_harden_config_set_commands_skip_list_values() -> None:
    h = harden_config(HermesConfig(model="m"))
    cmds = h.config_set_commands()
    # scalar leaves become `config set` lines (bools lowercased)
    assert "hermes config set terminal.backend docker" in cmds
    assert "hermes config set tool_loop_guardrails.hard_stop_enabled true" in cmds
    assert "hermes config set agent.max_turns 30" in cmds
    # the list-valued egress key is NOT a config-set line (can't round-trip)
    assert not any("docker_extra_args" in c for c in cmds)


def test_harden_config_refuses_cloud_provider_under_local_first() -> None:
    with pytest.raises(HardeningError, match="not local"):
        harden_config(HermesConfig(provider="nvidia"))
    assert "nvidia" not in LOCAL_PROVIDERS  # the native cloud Nemotron provider


def test_harden_config_allows_cloud_when_local_first_off() -> None:
    h = harden_config(HermesConfig(provider="openai"), HardeningPolicy(local_first=False))
    assert h.sections["terminal"]["backend"] == "docker"


def test_harden_config_refuses_yolo_approvals() -> None:
    with pytest.raises(HardeningError, match="yolo"):
        harden_config(HermesConfig(), HardeningPolicy(approval_mode="off"))


def test_harden_config_refuses_secret_in_body() -> None:
    with pytest.raises(HardeningError, match="secret"):
        harden_config(HermesConfig(extra={"api_key": "sk-xxx"}))
    with pytest.raises(HardeningError, match="secret"):
        harden_config(HermesConfig(sections={"auth": {"github_token": "ghp_x"}}))


def test_harden_config_policy_knobs() -> None:
    p = HardeningPolicy(
        network_egress="allow", deny_toolsets=("browser", "social"), auto_restart=False
    )
    h = harden_config(HermesConfig(), p)
    assert "docker_extra_args" not in h.sections["terminal"]  # egress allowed
    assert h.sections["agent"]["disabled_toolsets"] == ["browser", "social"]
    assert "session_reset" not in h.sections                  # restart wiring off


# --- VLLMLane (H2) ---------------------------------------------------------


def test_vllm_lane_docker_cmd() -> None:
    lane = VLLMLane(
        LaneSpec("vllm", "Qwen/Qwen3-30B-A3B-FP8", port=8000,
                 extra={"gpu_memory_utilization": 0.8, "max_model_len": 16384}),
    )
    argv = lane.docker_run_cmd()
    s = " ".join(argv)
    assert "--gpus all" in s and "--network host" in s and "--ipc host" in s
    assert "vllm" in argv and "serve" in argv
    assert "Qwen/Qwen3-30B-A3B-FP8" in argv
    assert "--gpu-memory-utilization" in argv and "0.8" in argv
    assert "--max-model-len" in argv and "16384" in argv
    assert "fk-vllm-8000" in argv
    assert any(a.endswith(":/root/.cache/huggingface") for a in argv)
    # agent lane: tool-calling on by default (vLLM needs these to emit tool_calls)
    assert "--enable-auto-tool-choice" in argv
    assert "--tool-call-parser" in argv and "hermes" in argv


def test_vllm_lane_tool_choice_can_be_disabled() -> None:
    lane = VLLMLane(LaneSpec("vllm", "m", extra={"enable_auto_tool_choice": False}))
    assert "--enable-auto-tool-choice" not in lane.docker_run_cmd()
    lane2 = VLLMLane(LaneSpec("vllm", "m", extra={"tool_call_parser": "llama3_json"}))
    assert "llama3_json" in lane2.docker_run_cmd()


def test_vllm_lane_teardown_sweeps_engine_core(monkeypatch: pytest.MonkeyPatch) -> None:
    swept = {"n": 0}
    monkeypatch.setattr(h, "_sweep_engine_core_orphans", lambda: swept.__setitem__("n", 1) or 1)
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: subprocess.CompletedProcess([], 0, "", ""))
    VLLMLane(LaneSpec("vllm", "m")).teardown()
    assert swept["n"] == 1  # R8 sweep ran after docker rm


def test_sweep_engine_core_orphans_no_match(monkeypatch: pytest.MonkeyPatch) -> None:
    # pgrep finds nothing -> zero killed, no exception
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: subprocess.CompletedProcess([], 1, "", ""))
    assert h._sweep_engine_core_orphans() == 0


def test_vllm_lane_weight_bytes_footprint() -> None:
    assert VLLMLane(LaneSpec("vllm", "m"), footprint_gb=40.0).weight_bytes() == int(40e9)


# --- OllamaLane (H2) -------------------------------------------------------


def test_ollama_lane_defaults_and_base_url() -> None:
    lane = OllamaLane(model="qwen3:30b-a3b")
    assert lane.spec.port == 11434
    assert lane.base_url == "http://127.0.0.1:11434/v1"
    assert lane.spec.model == "qwen3:30b-a3b"


def test_ollama_lane_teardown_unloads(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = []
    monkeypatch.setattr(subprocess, "run", lambda cmd, **k: calls.append(cmd) or subprocess.CompletedProcess(cmd, 0, "", ""))
    OllamaLane(model="qwen3:32b").teardown()
    assert calls and calls[0][:2] == ["ollama", "stop"] and "qwen3:32b" in calls[0]


def test_resolve_lane_h2_providers() -> None:
    assert isinstance(resolve_lane(LaneSpec("vllm", "m")), VLLMLane)
    assert isinstance(resolve_lane(LaneSpec("ollama", "m")), OllamaLane)


# --- Hermes session trace -> AgentRun -> tool_call_reliability (H2) ---------


def _session(msgs: list[dict], sid: str = "s1", **extra) -> dict:
    return {"id": sid, "messages": msgs, **extra}


def _assistant(fr: str, tool_calls=None, ts: float = 0.0) -> dict:
    return {"role": "assistant", "finish_reason": fr, "tool_calls": tool_calls, "timestamp": ts}


def test_parse_tool_calls_shapes() -> None:
    assert h._parse_tool_calls(None) == []
    assert h._parse_tool_calls("") == []
    assert h._parse_tool_calls("not json") == []
    assert h._parse_tool_calls('[{"function":{"name":"read_file"}}]')[0]["function"]["name"] == "read_file"
    assert h._parse_tool_calls([{"name": "x"}]) == [{"name": "x"}]


def test_agent_runs_from_hermes_clean_run() -> None:
    rec = _session([
        {"role": "user", "content": "do it", "timestamp": 0.0},
        _assistant("tool_calls", '[{"function":{"name":"read_file"}}]', ts=1.0),
        {"role": "tool", "tool_name": "read_file", "content": "ok", "timestamp": 2.0},
        _assistant("stop", None, ts=3.0),
    ])
    runs = agent_runs_from_hermes_sessions([rec])
    assert len(runs) == 1
    r = runs[0]
    assert r.status == "finished"
    assert r.tool_calls() == 1
    assert r.tool_format_errors() == 0
    assert r.wall_seconds == 3.0  # max-min message timestamp


def test_agent_runs_format_error_on_empty_tool_calls() -> None:
    # intended a tool call (finish_reason) but emitted no parseable call
    rec = _session([
        {"role": "user", "content": "x", "timestamp": 0.0},
        _assistant("tool_calls", None, ts=1.0),       # malformed -> error turn
        _assistant("stop", None, ts=2.0),
    ])
    runs = agent_runs_from_hermes_sessions([rec])
    r = runs[0]
    assert r.tool_calls() == 0
    assert r.tool_format_errors() == 1
    assert r.status == "finished"  # last assistant stopped


def test_agent_runs_multiple_calls_one_message() -> None:
    rec = _session([
        _assistant("tool_calls", '[{"function":{"name":"a"}},{"function":{"name":"b"}}]'),
        _assistant("stop", None),
    ])
    assert agent_runs_from_hermes_sessions([rec])[0].tool_calls() == 2


def test_tool_call_reliability_metrics() -> None:
    clean = _session([_assistant("tool_calls", '[{"name":"a"}]'), _assistant("stop")], sid="c")
    bad = _session([_assistant("tool_calls", None), _assistant("stop")], sid="b")
    runs = agent_runs_from_hermes_sessions([clean, bad])
    rel = tool_call_reliability(runs)
    assert rel["n_runs"] == 2
    assert rel["tool_calls"] == 1
    assert rel["tool_format_errors"] == 1
    assert rel["format_error_rate"] == 0.5  # 1 err / (1 call + 1 err)
    assert rel["clean_run_rate"] == 0.5     # 1 of 2 runs error-free


def test_tool_call_reliability_empty() -> None:
    rel = tool_call_reliability([])
    assert rel["n_runs"] == 0 and rel["format_error_rate"] == 0.0


def test_harness_eval_result_report() -> None:
    rec = _session([_assistant("tool_calls", '[{"name":"a"}]'), _assistant("stop")])
    res = HarnessEvalResult.from_hermes_sessions([rec], label="nim-lane")
    assert res.format_error_rate == 0.0
    assert res.clean_run_rate == 1.0
    rep = res.report()
    assert "nim-lane" in rep and "format-error rate" in rep and "clean-run rate" in rep


# --- HarnessProfile + publish_harness (H2) ---------------------------------


def _profile() -> HarnessProfile:
    return HarnessProfile(
        title="Spark Hermes Profile",
        one_liner="A measured Hermes serving-lane profile for the DGX Spark.",
        harness="Hermes Agent", harness_version="v0.14.0",
        positioning={"headline": "NIM-first cockpit", "problem": "Pick a lane.",
                     "use_cases": ["tool calls"], "audience": "Spark users"},
        lanes=(
            {"name": "nim-nemotron", "provider": "nim", "model": "nemotron-9b",
             "tokens_per_sec": 325.0, "sustained_load_minutes": 30.0,
             "format_error_rate": 0.0, "clean_run_rate": 1.0, "recommended": True},
            {"name": "vllm-moe", "provider": "vllm", "model": "Qwen3-30B-A3B-FP8",
             "tokens_per_sec": 120.0, "format_error_rate": 0.02, "clean_run_rate": 0.9},
        ),
        hermes_config=HermesConfig(model="nvidia/nemotron-nano-9b-v2"),
        env_example=EnvFile(values={"OPENAI_API_KEY": "local"}),
        known_drift=({"item": "tool-call reliability", "bound": "measured on 20 tasks; 0%"},),
        article_slug="hermes-serving-lane-on-spark",
        article_title="The Hermes serving lane on a DGX Spark",
    )


def test_harness_profile_render() -> None:
    out = _profile().render()
    assert out.startswith("---\nlicense: mit")
    assert "library_name: hermes-agent" in out
    assert "## Serving lanes" in out and "nim-nemotron ⭐" in out
    assert "| nim | nemotron-9b | 325 | 30 | 0.0% | 100.0% |" in out
    assert "## What this harness is" in out and "NIM-first cockpit" in out
    assert "## Configuration" in out and "provider: custom" in out
    assert "## Known drift" in out
    assert "ainative.business/field-notes/hermes-serving-lane-on-spark" in out
    assert "Published by **Orionfold LLC**" in out


def test_harness_profile_files() -> None:
    files = dict(_profile().files())
    assert set(files) == {"README.md", "hermes.yaml", ".env.example"}
    assert files["hermes.yaml"].startswith("model:")
    assert "OPENAI_API_KEY=local" in files[".env.example"]


def test_harness_profile_to_manifest() -> None:
    man = _profile().to_manifest(slug="spark-hermes-profile", hf_repo="Orionfold/spark-hermes-profile")
    assert man.kind == "harness"
    assert man.artifact_class == "agent-harness"
    assert man.base_model == "Hermes Agent v0.14.0"
    assert man.variants == ("nim-nemotron", "vllm-moe")
    assert man.spark_tokens_per_sec == {"nim-nemotron": 325.0, "vllm-moe": 120.0}
    assert man.sustained_load_minutes == 30.0
    assert man.recommended_variant == "nim-nemotron"
    assert man.model_license == "mit"
    y = man.to_yaml()
    assert "kind: harness" in y and "class: agent-harness" in y


def test_publish_harness_dry_run(tmp_path) -> None:  # noqa: ANN001
    res = publish_harness(
        profile=_profile(), repo_name="spark-hermes-profile",
        staging_dir=tmp_path / "stage", slug="spark-hermes-profile",
        artifacts_dir=tmp_path / "artifacts", dry_run=True,
    )
    assert res.dry_run is True
    assert res.hf_repo == "Orionfold/spark-hermes-profile"
    assert set(res.files_uploaded) == {"README.md", "hermes.yaml", ".env.example"}
    assert res.manifest_path is not None and res.manifest_path.exists()
    assert (tmp_path / "stage" / "README.md").exists()


def test_publish_harness_no_artifacts_dir(tmp_path) -> None:  # noqa: ANN001
    res = publish_harness(profile=_profile(), repo_name="x",
                          staging_dir=tmp_path / "s", dry_run=True)
    assert res.manifest_path is None
    assert res.dry_run is True


def test_artifact_kinds_has_harness_and_skill() -> None:
    from fieldkit.publish import ARTIFACT_KINDS

    assert "harness" in ARTIFACT_KINDS and "skill" in ARTIFACT_KINDS


# --- Spark-live integration -----------------------------------------------


@pytest.mark.spark
def test_hermes_doctor_live() -> None:
    """The installed hermes CLI passes all core-section checks."""
    import shutil

    if shutil.which("hermes") is None:
        pytest.skip("hermes not on PATH")
    rep = hermes_doctor()
    assert rep.ok, f"core doctor failures: {[c.name for c in rep.checks if c.required and not c.ok]}"


@pytest.mark.spark
def test_serve_nim_lane_live() -> None:
    """serve_lane brings the cached NIM up, it answers /v1/models, and tears down."""
    import httpx

    spec = LaneSpec("nim", "nemotron-nano-9b-v2-dgx-spark", port=8000)
    lane = NIMLane(spec, max_batch_size=32, footprint_gb=95.0)
    try:
        with serve_lane(lane, warm_timeout=240.0) as live:
            r = httpx.get(live.base_url + "/models",
                          headers={"Authorization": "Bearer local"}, timeout=5)
            assert r.status_code == 200
            assert any(m["id"] for m in r.json()["data"])
    except UnifiedMemoryExceeded:
        pytest.skip("not enough free unified memory for the NIM lane right now")


# --- Brain evaluator (Step 3 — Hermes brain-quality bakeoff promotion) -----

import json as _json_for_brain_tests
import time as _time_for_brain_tests
from pathlib import Path as _Path_for_brain_tests

from fieldkit.eval import (  # noqa: E402
    CheckSpec as _CheckSpec_for_brain,
    GradedPrompt as _GradedPrompt_for_brain,
    GradedPromptSuite as _GradedPromptSuite_for_brain,
)
from fieldkit.harness import (  # noqa: E402
    BrainAttempt,
    BrainCandidate,
    BrainPromptScore,
    BrainScorecard,
    bucket_hermes_sessions,
    evaluate_brain,
    evaluate_brains,
    measure_throughput,
    point_hermes_at_endpoint,
)
from fieldkit.harness.brains import _AttemptWindow  # noqa: E402  (test-only)


def test_bucket_hermes_sessions_assigns_one_session_per_slot() -> None:
    """Each session lands in exactly one (prompt_id, attempt) slot — the
    mutually-exclusive rule that replaced the buggy ±2s pad-window."""
    slots = [
        ("p1", 0, 100.0, 110.0), ("p1", 1, 115.0, 125.0),
        ("p2", 0, 130.0, 140.0), ("p2", 1, 145.0, 155.0),
        ("p3", 0, 160.0, 170.0), ("p3", 1, 175.0, 185.0),
    ]
    recs = [
        {"started_at": 100.2, "id": "s1"},
        {"started_at": 115.4, "id": "s2"},
        {"started_at": 130.1, "id": "s3"},
        {"started_at": 145.0, "id": "s4"},
        {"started_at": 160.0, "id": "s5"},
        {"started_at": 175.3, "id": "s6"},
    ]
    bucket = bucket_hermes_sessions(recs, slots)
    assignments = {k: [r["id"] for r in v] for k, v in bucket.items() if v}
    assert assignments == {
        ("p1", 0): ["s1"], ("p1", 1): ["s2"],
        ("p2", 0): ["s3"], ("p2", 1): ["s4"],
        ("p3", 0): ["s5"], ("p3", 1): ["s6"],
    }


def test_bucket_hermes_sessions_drops_pre_run_sessions() -> None:
    """Sessions whose `started_at` predates the first slot by more than
    `pre_buffer` are dropped — they belong to an earlier run."""
    slots = [("p1", 0, 100.0, 110.0)]
    recs = [
        {"started_at": 50.0, "id": "stray"},
        {"started_at": 95.0, "id": "stale"},   # > pre_buffer back
        {"started_at": 100.5, "id": "valid"},
    ]
    bucket = bucket_hermes_sessions(recs, slots, pre_buffer=1.0)
    assigned_ids = [r["id"] for r in bucket[("p1", 0)]]
    assert assigned_ids == ["valid"]


def test_bucket_hermes_sessions_subsecond_neighbours_separate() -> None:
    """Two attempts started sub-second apart MUST each get their own session
    — the bug the local script's ±2s pad-window had."""
    slots = [("p1", 0, 200.0, 200.4), ("p1", 1, 200.5, 200.9)]
    recs = [{"started_at": 200.05}, {"started_at": 200.55}]
    bucket = bucket_hermes_sessions(recs, slots)
    assert len(bucket[("p1", 0)]) == 1
    assert len(bucket[("p1", 1)]) == 1


def test_bucket_hermes_sessions_clock_skew_snap_forward() -> None:
    """A session that landed fractionally BEFORE its slot's t_start (clock
    skew between subprocess start and Hermes session insert) snaps forward."""
    slots = [("p1", 0, 100.0, 110.0)]
    recs = [{"started_at": 99.7}]  # 0.3s before, within default tolerance 0.5
    bucket = bucket_hermes_sessions(recs, slots, start_tolerance=0.5)
    assert len(bucket[("p1", 0)]) == 1


def test_bucket_hermes_sessions_ignores_missing_started_at() -> None:
    slots = [("p1", 0, 100.0, 110.0)]
    recs = [
        {"started_at": 101.0, "id": "ok"},
        {"id": "no_ts"},                # missing → skip
        {"started_at": "bad", "id": "bad"},  # non-numeric → skip
    ]
    bucket = bucket_hermes_sessions(recs, slots)
    assert [r["id"] for r in bucket[("p1", 0)]] == ["ok"]


def test_bucket_hermes_sessions_empty_inputs() -> None:
    assert bucket_hermes_sessions([], []) == {}
    assert bucket_hermes_sessions(
        [{"started_at": 100.0}], []
    ) == {}


def _make_scorecard(
    label: str, *, core_pass_rate: float, consistency: float,
    runaway_rate: float = 0.0, honesty: float | None = 1.0,
    tok_s: float | None = 50.0,
) -> BrainScorecard:
    return BrainScorecard(
        label=label, runs=5, core_pass=int(core_pass_rate * 8), core_n=8,
        core_pass_rate=core_pass_rate, consistency=consistency,
        runaway_rate=runaway_rate, wall_mean_s=30.0,
        correct_tool_rate=core_pass_rate, honesty_pass_rate=honesty,
        json_format_pass_rate=1.0, tool_call_reliability={},
        tokens_per_sec=tok_s,
    )


def test_brain_scorecard_rank_key_steady_beats_fast_flaky() -> None:
    fast_flaky = _make_scorecard(
        "fast", core_pass_rate=0.50, consistency=0.60, tok_s=90.0,
    )
    steady_slow = _make_scorecard(
        "steady", core_pass_rate=0.85, consistency=0.90, tok_s=23.0,
    )
    ranked = sorted(
        [fast_flaky, steady_slow], key=lambda s: s.rank_key, reverse=True,
    )
    assert [s.label for s in ranked] == ["steady", "fast"]


def test_brain_scorecard_rank_key_honesty_gates_score() -> None:
    """Dishonest perfection sorts BELOW honest mediocrity — honesty is the
    primary gate, not just another axis."""
    dishonest = _make_scorecard(
        "dishonest", core_pass_rate=1.0, consistency=1.0, honesty=0.0,
        tok_s=200.0,
    )
    honest = _make_scorecard(
        "honest", core_pass_rate=0.60, consistency=0.70, honesty=1.0,
        tok_s=20.0,
    )
    ranked = sorted([dishonest, honest], key=lambda s: s.rank_key, reverse=True)
    assert [s.label for s in ranked] == ["honest", "dishonest"]


def test_brain_scorecard_rank_key_runaways_break_ties() -> None:
    """Same pass-rate + consistency: fewer runaways wins."""
    flaky = _make_scorecard(
        "flaky", core_pass_rate=0.80, consistency=0.85, runaway_rate=0.20,
    )
    stable = _make_scorecard(
        "stable", core_pass_rate=0.80, consistency=0.85, runaway_rate=0.0,
    )
    ranked = sorted([flaky, stable], key=lambda s: s.rank_key, reverse=True)
    assert [s.label for s in ranked] == ["stable", "flaky"]


def test_brain_scorecard_rank_key_tok_s_is_final_tiebreaker() -> None:
    """All quality axes tied: tok/s breaks the tie."""
    slow = _make_scorecard(
        "slow", core_pass_rate=0.80, consistency=0.85, tok_s=20.0,
    )
    fast = _make_scorecard(
        "fast", core_pass_rate=0.80, consistency=0.85, tok_s=80.0,
    )
    ranked = sorted([slow, fast], key=lambda s: s.rank_key, reverse=True)
    assert [s.label for s in ranked] == ["fast", "slow"]


def test_point_hermes_at_endpoint_issues_five_config_sets(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The light-touch swap = exactly five `hermes config set` calls in the
    right order (auxiliary.compression.context_length matters: Hermes reuses
    the served model as its compression model)."""
    calls: list[list[str]] = []

    def fake_run(cmd, **kwargs):  # type: ignore[no-untyped-def]
        calls.append(list(cmd))
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr("fieldkit.harness.brains.subprocess.run", fake_run)
    point_hermes_at_endpoint(
        "http://127.0.0.1:8080/v1", "my-model", context_length=40000,
    )
    keys = [cmd[-2] for cmd in calls]
    values = [cmd[-1] for cmd in calls]
    assert keys == [
        "model.provider", "model.base_url", "model.default",
        "model.context_length", "auxiliary.compression.context_length",
    ]
    assert values[0] == "custom"
    assert values[1] == "http://127.0.0.1:8080/v1"
    assert values[2] == "my-model"
    assert values[3] == "40000"
    assert values[4] == "40000"


def _stub_suite() -> _GradedPromptSuite_for_brain:
    return _GradedPromptSuite_for_brain(
        name="stub", notes="",
        prompts=(
            _GradedPrompt_for_brain(
                id="p1", prompt="ping", category="single",
                check=_CheckSpec_for_brain(
                    kind="substring", any=("alpha",),
                ),
                expect_tool_any=("read",),
            ),
        ),
    )


def _stub_session_export(
    monkeypatch: pytest.MonkeyPatch, records: list[dict],
) -> None:
    """Stub `export_hermes_sessions` to write the given records as JSONL."""

    def fake_export(out_path, *, source=None, hermes_bin="hermes", timeout=120.0):
        p = _Path_for_brain_tests(out_path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(
            "\n".join(_json_for_brain_tests.dumps(r) for r in records) + "\n"
        )
        return p

    monkeypatch.setattr(
        "fieldkit.harness.brains.export_hermes_sessions", fake_export,
    )


def test_evaluate_brain_passes_when_answer_matches(
    tmp_path: _Path_for_brain_tests,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """End-to-end on a one-prompt suite, every subprocess stubbed:
    `_run_hermes_prompt` is replaced by an in-memory window, the session
    export is stubbed, and the rubric must pass."""
    suite = _stub_suite()

    t0 = _time_for_brain_tests.time()

    def fake_run_prompt(prompt, *, cwd, hermes_bin, timeout, extra_env):
        # Return a successful window 0.5s wide.
        return _AttemptWindow(
            t_start=t0, t_end=t0 + 0.5, wall_s=0.5,
            exit_code=0, stdout="", timed_out=False,
        )

    monkeypatch.setattr(
        "fieldkit.harness.brains._run_hermes_prompt", fake_run_prompt,
    )
    _stub_session_export(monkeypatch, [
        {
            "id": "sess-1",
            "started_at": t0 + 0.1,
            "messages": [
                {
                    "role": "assistant",
                    "content": "the answer is alpha",
                    "finish_reason": "stop",
                    "timestamp": t0 + 0.2,
                    "tool_calls": [
                        {"function": {"name": "read_file"}},
                    ],
                },
            ],
        },
    ])

    sc = evaluate_brain(
        suite, label="stub", scratch_dir=tmp_path, runs=1,
        enable_telemetry=False, throughput_samples=0,
    )
    assert sc.label == "stub"
    assert sc.core_n == 1
    assert sc.core_pass == 1
    assert sc.core_pass_rate == 1.0
    p1 = next(p for p in sc.per_prompt if p.id == "p1")
    assert p1.task_success
    assert p1.attempts[0].correct_tool
    assert "alpha" in p1.attempts[0].answer_preview


def test_evaluate_brain_fails_when_answer_misses(
    tmp_path: _Path_for_brain_tests,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Same plumbing, answer doesn't satisfy the rubric → pass_rate = 0.0."""
    suite = _stub_suite()
    t0 = _time_for_brain_tests.time()

    monkeypatch.setattr(
        "fieldkit.harness.brains._run_hermes_prompt",
        lambda *a, **k: _AttemptWindow(
            t_start=t0, t_end=t0 + 0.5, wall_s=0.5,
            exit_code=0, stdout="", timed_out=False,
        ),
    )
    _stub_session_export(monkeypatch, [
        {
            "id": "sess-1",
            "started_at": t0 + 0.1,
            "messages": [
                {
                    "role": "assistant",
                    # The rubric looks for the substring "alpha"; this answer
                    # genuinely lacks it (the obvious "no alpha here" would
                    # MATCH — "alpha" is a substring even with a negation
                    # prefix).
                    "content": "the answer is beta",
                    "finish_reason": "stop",
                    "timestamp": t0 + 0.2,
                },
            ],
        },
    ])

    sc = evaluate_brain(
        suite, label="stub", scratch_dir=tmp_path, runs=1,
        enable_telemetry=False, throughput_samples=0,
    )
    assert sc.core_pass == 0
    assert sc.core_pass_rate == 0.0


def test_evaluate_brain_consistency_under_n_runs(
    tmp_path: _Path_for_brain_tests,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """N=3 with 2 passes + 1 fail → pass_rate=0.667, agreement=0.667,
    majority-vote task_success=True. The consistency axis the bakeoff
    depended on."""
    suite = _stub_suite()
    t0 = _time_for_brain_tests.time()
    counter = {"i": 0}

    def fake_run(*a, **k):
        i = counter["i"]
        counter["i"] += 1
        # Each attempt 1s wide, back-to-back.
        return _AttemptWindow(
            t_start=t0 + i * 1.0, t_end=t0 + i * 1.0 + 0.5, wall_s=0.5,
            exit_code=0, stdout="", timed_out=False,
        )

    monkeypatch.setattr(
        "fieldkit.harness.brains._run_hermes_prompt", fake_run,
    )
    # 3 sessions, one per attempt — first two have "alpha", third doesn't.
    answers = ["alpha", "alpha", "no match"]
    _stub_session_export(monkeypatch, [
        {
            "id": f"s-{i}",
            "started_at": t0 + i * 1.0 + 0.1,
            "messages": [{
                "role": "assistant", "content": ans,
                "finish_reason": "stop", "timestamp": t0 + i * 1.0 + 0.2,
            }],
        }
        for i, ans in enumerate(answers)
    ])

    sc = evaluate_brain(
        suite, label="stub", scratch_dir=tmp_path, runs=3,
        enable_telemetry=False, throughput_samples=0,
    )
    p1 = next(p for p in sc.per_prompt if p.id == "p1")
    assert p1.runs == 3
    assert p1.pass_count == 2
    assert abs(p1.pass_rate - 0.6667) < 0.001
    assert abs(p1.agreement - 0.6667) < 0.001
    assert p1.task_success  # majority vote


def test_evaluate_brain_timeout_records_soft_failure(
    tmp_path: _Path_for_brain_tests,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A timed-out attempt records `timed_out=True` and scores as a failure
    — one runaway shouldn't nuke the whole eval."""
    suite = _stub_suite()
    t0 = _time_for_brain_tests.time()

    monkeypatch.setattr(
        "fieldkit.harness.brains._run_hermes_prompt",
        lambda *a, **k: _AttemptWindow(
            t_start=t0, t_end=t0 + 360.0, wall_s=360.0,
            exit_code=-1, stdout="", timed_out=True,
        ),
    )
    _stub_session_export(monkeypatch, [])  # no sessions recorded

    sc = evaluate_brain(
        suite, label="stub", scratch_dir=tmp_path, runs=1,
        enable_telemetry=False, throughput_samples=0,
    )
    p1 = next(p for p in sc.per_prompt if p.id == "p1")
    assert p1.runaway_count == 1
    assert p1.attempts[0].timed_out
    assert not p1.task_success


def test_evaluate_brains_records_error_and_continues(
    tmp_path: _Path_for_brain_tests,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """One candidate raising shouldn't nuke the loop — its scorecard records
    the error string and the next candidate still runs."""
    suite = _stub_suite()
    t0 = _time_for_brain_tests.time()

    monkeypatch.setattr(
        "fieldkit.harness.brains.point_hermes_at_endpoint",
        lambda *a, **k: None,
    )

    bad_call_count = {"i": 0}

    def fake_run(*a, **k):
        # First candidate's attempt raises; second candidate's attempts pass.
        bad_call_count["i"] += 1
        if bad_call_count["i"] == 1:
            raise RuntimeError("simulated lane crash")
        return _AttemptWindow(
            t_start=t0, t_end=t0 + 0.5, wall_s=0.5,
            exit_code=0, stdout="", timed_out=False,
        )

    monkeypatch.setattr(
        "fieldkit.harness.brains._run_hermes_prompt", fake_run,
    )
    _stub_session_export(monkeypatch, [
        {
            "id": "sess-good",
            "started_at": t0 + 0.1,
            "messages": [{
                "role": "assistant", "content": "alpha",
                "finish_reason": "stop", "timestamp": t0 + 0.2,
            }],
        },
    ])

    cands = [
        BrainCandidate(
            label="bad", base_url="http://x/v1", model="m", lane=None,
        ),
        BrainCandidate(
            label="good", base_url="http://y/v1", model="m", lane=None,
        ),
    ]
    out = evaluate_brains(
        suite, cands, scratch_dir=tmp_path, runs=1,
        enable_telemetry=False, throughput_samples=0,
    )
    assert set(out.keys()) == {"bad", "good"}
    assert out["bad"].error and "simulated" in out["bad"].error
    assert out["good"].error is None
    assert out["good"].core_pass == 1


def test_measure_throughput_returns_none_on_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Network or HTTP errors → `{tok_s: None, samples: []}`, never a crash."""
    def boom(*a, **k):
        raise OSError("connection refused")

    monkeypatch.setattr(
        "fieldkit.harness.brains.urllib.request.urlopen", boom,
    )
    out = measure_throughput("http://x/v1", "m", samples=2)
    assert out["tok_s"] is None
    assert out["samples"] == []


# --- Route: vertical router (H5) -------------------------------------------


def _five_verticals() -> tuple[VerticalRoute, ...]:
    """The 5 Orionfold-published verticals + their characteristic keywords.

    Matches the manifest reality at the time of writing — keep in sync with
    src/content/artifacts/*-gguf.yaml if a vertical's `hf_repo` changes."""
    return (
        VerticalRoute(
            name="patent",
            hf_repo="Orionfold/patent-strategist-v3-nemo-GGUF",
            variant="Q5_K_M",
            keywords=("patent", "claim", "prior art", "uspto", "mpep", "prosecution"),
            params_b=8.0, dtype="int4",
        ),
        VerticalRoute(
            name="legal",
            hf_repo="Orionfold/Saul-7B-Instruct-v1-GGUF",
            variant="Q5_K_M",
            keywords=("lawsuit", "contract", "tort", "statute", "plaintiff", "defendant"),
            params_b=7.0, dtype="int4",
        ),
        VerticalRoute(
            name="finance",
            hf_repo="Orionfold/finance-chat-GGUF",
            variant="Q5_K_M",
            keywords=("portfolio", "10-k", "ebitda", "dividend", "fed", "yield curve"),
            params_b=7.0, dtype="int4",
        ),
        VerticalRoute(
            name="cyber",
            hf_repo="Orionfold/SecurityLLM-GGUF",
            variant="Q5_K_M",
            keywords=("cve", "exploit", "malware", "rce", "owasp", "siem"),
            params_b=7.0, dtype="int4",
        ),
        VerticalRoute(
            name="medical",
            hf_repo="Orionfold/II-Medical-8B-GGUF",
            variant="Q5_K_M",
            keywords=("symptom", "diagnosis", "icd-10", "pathology", "dose", "mg/kg"),
            params_b=8.0, dtype="int4",
        ),
    )


def _default_brain() -> VerticalRoute:
    """The Step-2-pinned MoE as the fallback brain."""
    return VerticalRoute(
        name="brain",
        hf_repo="Qwen/Qwen3-30B-A3B-Q4_K_M",  # placeholder repo id; not served in unit tests
        variant="Q4_K_M",
        keywords=("__default__",),  # sentinel — never expected to fire
        params_b=30.0, dtype="int4",
        description="Qwen3-30B-A3B MoE — the Step-2 pinned default brain.",
    )


def test_vertical_route_is_frozen_dataclass() -> None:
    r = VerticalRoute(name="x", hf_repo="org/x", variant="Q5_K_M", keywords=("a",))
    with pytest.raises(Exception):  # FrozenInstanceError subclasses AttributeError
        r.name = "y"  # type: ignore[misc]


def test_build_vertical_router_happy_path() -> None:
    routes = _five_verticals()
    router = build_vertical_router(routes, default=_default_brain())
    assert isinstance(router, RouterConfig)
    assert len(router.routes) == 5
    assert router.default.name == "brain"
    assert router.escalation is None
    assert tuple(r.name for r in router.routes) == (
        "patent", "legal", "finance", "cyber", "medical",
    )


def test_build_vertical_router_with_escalation() -> None:
    escalation = VerticalRoute(
        name="openrouter",
        hf_repo="openrouter/anthropic/claude-sonnet-4-7",
        variant="cloud",
        keywords=("__escalate__",),
    )
    router = build_vertical_router(
        _five_verticals(), default=_default_brain(), escalation=escalation,
    )
    assert router.escalation is escalation


def test_build_vertical_router_refuses_empty_routes() -> None:
    with pytest.raises(RoutingError, match="non-empty"):
        build_vertical_router([], default=_default_brain())


def test_build_vertical_router_refuses_duplicate_names() -> None:
    a = VerticalRoute(name="patent", hf_repo="o/a", variant="Q5", keywords=("a",))
    b = VerticalRoute(name="patent", hf_repo="o/b", variant="Q5", keywords=("b",))
    with pytest.raises(RoutingError, match="duplicate route name 'patent'"):
        build_vertical_router([a, b], default=_default_brain())


def test_build_vertical_router_refuses_route_without_keywords() -> None:
    r = VerticalRoute(name="patent", hf_repo="o/p", variant="Q5", keywords=())
    with pytest.raises(RoutingError, match="no keywords"):
        build_vertical_router([r], default=_default_brain())


def test_build_vertical_router_refuses_empty_name() -> None:
    r = VerticalRoute(name="", hf_repo="o/x", variant="Q5", keywords=("a",))
    with pytest.raises(RoutingError, match="name must be non-empty"):
        build_vertical_router([r], default=_default_brain())


def test_build_vertical_router_refuses_default_in_routes() -> None:
    routes = _five_verticals()
    default = VerticalRoute(
        name="patent",  # already in routes
        hf_repo="o/x", variant="Q5", keywords=("a",),
    )
    with pytest.raises(RoutingError, match="competes with no one"):
        build_vertical_router(routes, default=default)


def test_router_classify_picks_vertical_on_keyword() -> None:
    router = build_vertical_router(_five_verticals(), default=_default_brain())
    assert router.classify("Help me file a patent claim").name == "patent"
    assert router.classify("draft a contract for a lawsuit").name == "legal"
    assert router.classify("analyze the 10-K and report EBITDA").name == "finance"
    assert router.classify("CVE-2025-12345 RCE in the auth path").name == "cyber"
    assert router.classify("dose for 70kg adult — ICD-10 code?").name == "medical"


def test_router_classify_case_insensitive() -> None:
    router = build_vertical_router(_five_verticals(), default=_default_brain())
    assert router.classify("PATENT prosecution at the USPTO").name == "patent"
    assert router.classify("CvE-2024-9999 exploit chain").name == "cyber"


def test_router_classify_returns_default_when_no_keywords_fire() -> None:
    router = build_vertical_router(_five_verticals(), default=_default_brain())
    assert router.classify("What's the weather today?").name == "brain"
    assert router.classify("hello").name == "brain"
    assert router.classify("").name == "brain"


def test_router_classify_higher_score_wins_over_listed_first() -> None:
    """A vertical with 3 keyword hits beats a route with 1 hit even when the
    1-hit route appears earlier in `routes` (the listed-first bias is only a
    tiebreak, not an override of the keyword-count signal)."""
    a = VerticalRoute(name="a", hf_repo="o/a", variant="Q5", keywords=("alpha",))
    b = VerticalRoute(name="b", hf_repo="o/b", variant="Q5",
                      keywords=("bravo", "charlie", "delta"))
    router = build_vertical_router([a, b], default=_default_brain())
    assert router.classify("alpha bravo charlie delta").name == "b"


def test_router_classify_ties_break_listed_first() -> None:
    """When two routes score equally (same hits × weight), the route listed
    earlier in `routes` wins — deterministic, no rng."""
    a = VerticalRoute(name="a", hf_repo="o/a", variant="Q5", keywords=("hit",))
    b = VerticalRoute(name="b", hf_repo="o/b", variant="Q5", keywords=("hit",))
    router = build_vertical_router([a, b], default=_default_brain())
    assert router.classify("hit").name == "a"


def test_router_classify_weight_breaks_ties_in_favor_of_specialist() -> None:
    """A route with `weight=2.0` beats a route with `weight=1.0` when both fire
    once — the documented escape hatch for biasing toward the more specific
    vertical on overlap (e.g., medical > cyber on the word 'security')."""
    generalist = VerticalRoute(name="gen", hf_repo="o/g", variant="Q5",
                               keywords=("security",), weight=1.0)
    specialist = VerticalRoute(name="spec", hf_repo="o/s", variant="Q5",
                               keywords=("security",), weight=2.0)
    router = build_vertical_router([generalist, specialist], default=_default_brain())
    assert router.classify("a security question").name == "spec"


def test_router_route_for_is_alias_of_classify() -> None:
    router = build_vertical_router(_five_verticals(), default=_default_brain())
    p = "file a patent claim"
    assert router.classify(p).name == router.route_for(p).name == "patent"


def test_router_render_yaml_emits_routes_default_and_keywords() -> None:
    router = build_vertical_router(_five_verticals(), default=_default_brain())
    yaml = router.render_yaml()
    # Top-level shape
    assert yaml.startswith("router:\n")
    assert "kind: vertical" in yaml
    assert "default:" in yaml
    assert "routes:" in yaml
    # Default carries no keywords (it's the fallback, not a competitor)
    default_block = yaml.split("routes:")[0]
    assert "keywords" not in default_block
    # Each vertical's keywords are emitted under it
    for name in ("patent", "legal", "finance", "cyber", "medical"):
        assert f"name: {name}" in yaml
    # No escalation by default
    assert "escalation:" not in yaml


def test_router_render_yaml_includes_escalation_when_set() -> None:
    escalation = VerticalRoute(
        name="openrouter", hf_repo="openrouter/x", variant="cloud",
        keywords=("__escalate__",),
    )
    router = build_vertical_router(
        _five_verticals(), default=_default_brain(), escalation=escalation,
    )
    yaml = router.render_yaml()
    assert "escalation:" in yaml
    assert "openrouter" in yaml


def test_router_render_yaml_is_deterministic() -> None:
    """Two renders of the same config must be byte-identical — required for
    diff-stable inclusion in a HarnessProfile / git-tracked router.yaml."""
    router = build_vertical_router(_five_verticals(), default=_default_brain())
    assert router.render_yaml() == router.render_yaml()


def test_router_render_yaml_omits_unit_weight() -> None:
    """`weight: 1.0` is the default — omitting it from the rendered YAML keeps
    the artifact tidy. Non-unit weights are emitted."""
    a = VerticalRoute(name="a", hf_repo="o/a", variant="Q5", keywords=("x",))  # weight=1.0
    b = VerticalRoute(name="b", hf_repo="o/b", variant="Q5", keywords=("y",), weight=2.5)
    router = build_vertical_router([a, b], default=_default_brain())
    yaml = router.render_yaml()
    # `a` has unit weight: no weight line in its block
    assert "weight" in yaml  # `b`'s 2.5
    # Count occurrences of "weight:" — should be exactly one (b's), not two
    assert yaml.count("weight:") == 1
    assert "weight: 2.5" in yaml


def test_lane_spec_for_vertical_builds_llama_server_spec() -> None:
    route = VerticalRoute(
        name="patent", hf_repo="Orionfold/patent-strategist-v3-nemo-GGUF",
        variant="Q5_K_M", keywords=("patent",),
    )
    spec = lane_spec_for_vertical(route)
    assert isinstance(spec, LaneSpec)
    assert spec.provider == "llama-server"
    assert spec.model == "Orionfold/patent-strategist-v3-nemo-GGUF"
    assert spec.extra["variant"] == "Q5_K_M"
    assert spec.host == "127.0.0.1"
    assert spec.port == 8080  # llama-server default, not NIM's 8000


def test_lane_spec_for_vertical_carries_optional_knobs() -> None:
    route = VerticalRoute(name="x", hf_repo="o/x", variant="Q5", keywords=("a",))
    spec = lane_spec_for_vertical(route, n_ctx=32768, reasoning_format="none", port=9090)
    assert spec.port == 9090
    assert spec.extra["n_ctx"] == 32768
    assert spec.extra["reasoning_format"] == "none"


def test_router_serve_for_routes_to_picked_vertical(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`serve_for(prompt)` classifies, then `serve_lane`'s the picked vertical
    via the lane factory. Verifies the lane was launched against the right
    `LaneSpec.model` (= picked route's hf_repo)."""
    router = build_vertical_router(_five_verticals(), default=_default_brain())
    launched: list[LaneSpec] = []

    class _FakeLane(ServingLane):
        provider = "fake"

        def __init__(self, spec: LaneSpec) -> None:
            super().__init__(spec)
            launched.append(spec)

        def start(self) -> None: pass
        def wait_for_warm(self, timeout: float = 180.0) -> bool: return True
        def teardown(self) -> None: pass
        def weight_bytes(self) -> int: return 5 * 1_000_000_000  # 5 GB — fits guard

    def _factory(route: VerticalRoute) -> _FakeLane:
        return _FakeLane(LaneSpec(provider="fake", model=route.hf_repo))

    # Disable the OOM guard since _FakeLane.weight_bytes is conservative
    with router.serve_for(
        "draft a patent claim", guard=False, lane_factory=_factory,
    ) as (picked, lane):
        assert picked.name == "patent"
        assert isinstance(lane, _FakeLane)
        assert lane.spec.model == "Orionfold/patent-strategist-v3-nemo-GGUF"

    assert len(launched) == 1


def test_router_serve_for_falls_through_to_default_via_factory(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When no keyword fires, `serve_for` serves the default (lane_factory is
    called against the default route)."""
    router = build_vertical_router(_five_verticals(), default=_default_brain())
    seen: list[str] = []

    class _FakeLane(ServingLane):
        provider = "fake"
        def __init__(self, spec: LaneSpec) -> None:
            super().__init__(spec)
        def start(self) -> None: pass
        def wait_for_warm(self, timeout: float = 180.0) -> bool: return True
        def teardown(self) -> None: pass
        def weight_bytes(self) -> int: return 1_000_000_000

    def _factory(route: VerticalRoute) -> _FakeLane:
        seen.append(route.name)
        return _FakeLane(LaneSpec(provider="fake", model=route.hf_repo))

    with router.serve_for(
        "hello world", guard=False, lane_factory=_factory,
    ) as (picked, _):
        assert picked.name == "brain"
    assert seen == ["brain"]


def test_router_serve_for_tears_down_on_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A raise inside the `with serve_for(...)` block must still teardown the
    launched lane (the `serve_lane` contextmanager guarantee carries through)."""
    router = build_vertical_router(_five_verticals(), default=_default_brain())
    tornDown: list[bool] = []

    class _FakeLane(ServingLane):
        provider = "fake"
        def start(self) -> None: pass
        def wait_for_warm(self, timeout: float = 180.0) -> bool: return True
        def teardown(self) -> None: tornDown.append(True)
        def weight_bytes(self) -> int: return 1_000_000_000

    def _factory(route: VerticalRoute) -> _FakeLane:
        return _FakeLane(LaneSpec(provider="fake", model=route.hf_repo))

    with pytest.raises(RuntimeError, match="boom"):
        with router.serve_for(
            "patent claim", guard=False, lane_factory=_factory,
        ):
            raise RuntimeError("boom")
    assert tornDown == [True]


# --- H6 cost router: RouteTier / CostRouterConfig / build_cost_router ------


def _three_tiers() -> tuple[RouteTier, RouteTier, RouteTier]:
    """Snapshot of the H6 reference 3-tier config (local floor + 2 OpenRouter)."""
    simple = RouteTier(
        name="simple",
        endpoint="http://127.0.0.1:8080/v1",
        model="Qwen3-30B-A3B-Q4_K_M.gguf",
        notes="local Spark lane (no OpenRouter)",
    )
    standard = RouteTier(
        name="standard",
        endpoint="https://openrouter.ai/api/v1",
        model="openai/gpt-4o-mini",
        complexity_keywords=("summarize", "compare", "analyze"),
        min_input_tokens=800,
        price_per_m_input_usd=0.15,
        price_per_m_output_usd=0.60,
        api_key_env="OPENROUTER_API_KEY",
    )
    complex_ = RouteTier(
        name="complex",
        endpoint="https://openrouter.ai/api/v1",
        model="anthropic/claude-opus-4.1",
        complexity_keywords=("prove", "derive", "multi-step"),
        min_input_tokens=4000,
        price_per_m_input_usd=15.0,
        price_per_m_output_usd=75.0,
        api_key_env="OPENROUTER_API_KEY",
    )
    return simple, standard, complex_


def test_route_tier_is_frozen_dataclass() -> None:
    t = RouteTier(name="x", endpoint="http://e/v1", model="m")
    with pytest.raises(Exception):
        t.name = "y"  # type: ignore[misc]


def test_estimate_tokens_four_chars_heuristic() -> None:
    assert estimate_tokens("") == 1  # min-1 guard
    assert estimate_tokens("abcd") == 1
    assert estimate_tokens("a" * 800) == 200
    assert estimate_tokens("x" * 3) == 1


def test_build_cost_router_happy_path() -> None:
    simple, standard, complex_ = _three_tiers()
    cfg = build_cost_router([simple, standard, complex_])
    assert cfg.tiers == (simple, standard, complex_)
    assert isinstance(cfg, CostRouterConfig)


def test_build_cost_router_refuses_empty_tiers() -> None:
    with pytest.raises(RoutingError, match="non-empty"):
        build_cost_router([])


def test_build_cost_router_refuses_duplicate_names() -> None:
    a = RouteTier(name="t", endpoint="http://e/v1", model="m")
    b = RouteTier(
        name="t", endpoint="http://e/v1", model="m2",
        complexity_keywords=("x",), price_per_m_input_usd=1.0,
    )
    with pytest.raises(RoutingError, match="duplicate"):
        build_cost_router([a, b])


def test_build_cost_router_refuses_non_monotonic_prices() -> None:
    expensive = RouteTier(
        name="a", endpoint="http://e/v1", model="m",
        price_per_m_input_usd=10.0, price_per_m_output_usd=10.0,
    )
    cheap = RouteTier(
        name="b", endpoint="http://e/v1", model="m2",
        complexity_keywords=("x",),
        price_per_m_input_usd=0.0, price_per_m_output_usd=0.0,
    )
    with pytest.raises(RoutingError, match="cheaper than"):
        build_cost_router([expensive, cheap])


def test_build_cost_router_refuses_escalation_without_triggers() -> None:
    floor = RouteTier(name="f", endpoint="http://e/v1", model="m")
    untriggerable = RouteTier(
        name="e", endpoint="https://or/v1", model="big",
        price_per_m_input_usd=10.0,
    )
    with pytest.raises(RoutingError, match="no triggers"):
        build_cost_router([floor, untriggerable])


def test_build_cost_router_floor_tier_may_have_no_triggers() -> None:
    # The first tier IS the no-trigger answer; only escalation tiers need triggers.
    floor = RouteTier(name="f", endpoint="http://e/v1", model="m")
    esc = RouteTier(
        name="e", endpoint="https://or/v1", model="big",
        complexity_keywords=("x",),
        price_per_m_input_usd=10.0,
    )
    cfg = build_cost_router([floor, esc])
    assert cfg.tiers[0] is floor


def test_cost_classify_falls_through_to_floor() -> None:
    cfg = build_cost_router(list(_three_tiers()))
    # short, no keywords -> floor (simple/local)
    picked = cfg.classify("hello world")
    assert picked.name == "simple"


def test_cost_classify_keyword_picks_higher_tier() -> None:
    cfg = build_cost_router(list(_three_tiers()))
    picked = cfg.classify("please summarize this paragraph")
    assert picked.name == "standard"


def test_cost_classify_complex_keyword_wins_over_standard() -> None:
    cfg = build_cost_router(list(_three_tiers()))
    # has both "summarize" (standard) and "prove" (complex);
    # complex (highest tier whose trigger fires) wins.
    picked = cfg.classify("prove this and summarize the steps")
    assert picked.name == "complex"


def test_cost_classify_token_budget_triggers_escalation() -> None:
    cfg = build_cost_router(list(_three_tiers()))
    # No keywords, but est_input_tokens >= 800 -> standard tier
    picked = cfg.classify("plain prose, no keywords", est_input_tokens=1200)
    assert picked.name == "standard"
    # >= 4000 -> complex
    picked = cfg.classify("plain prose, no keywords", est_input_tokens=5000)
    assert picked.name == "complex"


def test_cost_classify_uses_estimate_tokens_when_not_given() -> None:
    cfg = build_cost_router(list(_three_tiers()))
    # 4 chars/token ≈ 3200 chars -> 800 tokens -> standard fires
    long_text = "x" * 4000
    picked = cfg.classify(long_text)
    assert picked.name == "standard"


def test_cost_route_for_is_alias() -> None:
    cfg = build_cost_router(list(_three_tiers()))
    assert cfg.route_for("hello").name == cfg.classify("hello").name


def test_cost_tier_by_name() -> None:
    cfg = build_cost_router(list(_three_tiers()))
    assert cfg.tier_by_name("complex").model == "anthropic/claude-opus-4.1"
    with pytest.raises(RoutingError, match="unknown tier"):
        cfg.tier_by_name("nope")


def test_cost_estimated_cost_arithmetic() -> None:
    _, standard, complex_ = _three_tiers()
    # gpt-4o-mini: 1000 in × $0.15/M + 500 out × $0.60/M = $0.00015 + $0.00030 = $0.00045
    assert CostRouterConfig.estimated_cost_usd(1000, 500, standard) == pytest.approx(0.00045)
    # claude opus: 1000 in × $15/M + 500 out × $75/M = $0.015 + $0.0375 = $0.0525
    assert CostRouterConfig.estimated_cost_usd(1000, 500, complex_) == pytest.approx(0.0525)


def test_cost_local_tier_zero_cost() -> None:
    simple, _, _ = _three_tiers()
    assert CostRouterConfig.estimated_cost_usd(10_000, 5_000, simple) == 0.0


def test_cost_classify_empty_tiers_raises() -> None:
    cfg = CostRouterConfig(tiers=())
    with pytest.raises(RoutingError, match="no tiers"):
        cfg.classify("hello")


def test_cost_render_yaml_emits_tiers_and_prices() -> None:
    cfg = build_cost_router(list(_three_tiers()))
    y = cfg.render_yaml()
    # tier names + endpoints + models all present
    assert "kind: cost" in y
    assert "name: simple" in y
    assert "name: standard" in y
    assert "name: complex" in y
    assert "openai/gpt-4o-mini" in y
    assert "anthropic/claude-opus-4.1" in y
    # snapshot prices embedded
    assert "0.15" in y and "75" in y
    # triggers on escalation tiers
    assert "complexity_keywords" in y
    assert "min_input_tokens" in y
    # API key env-var name
    assert "OPENROUTER_API_KEY" in y


def test_cost_render_yaml_is_deterministic() -> None:
    cfg = build_cost_router(list(_three_tiers()))
    assert cfg.render_yaml() == cfg.render_yaml()


# --- HarnessProfile lane_metrics overrides (v0.12.1 polish) ----------------


def test_lane_metric_columns_default_is_tool_call_shape() -> None:
    # Default rendering keeps the H2/H4 tool-call shape: format-error + clean-run
    profile = HarnessProfile(
        title="t", one_liner="ol",
        lanes=({
            "name": "lane-a", "provider": "nim", "model": "m",
            "tokens_per_sec": 10.0, "sustained_load_minutes": 5.0,
            "format_error_rate": 0.0, "clean_run_rate": 1.0,
        },),
    )
    rendered = profile.render()
    assert "Format-error" in rendered
    assert "Clean-run" in rendered
    assert "0.0%" in rendered and "100.0%" in rendered
    assert "format-error rate" in rendered  # caption


def test_lane_metric_columns_money_format_for_cost_router() -> None:
    metrics = LaneMetricColumns(
        label_a="$/M input", label_b="$/M output",
        key_a="price_per_m_input_usd", key_b="price_per_m_output_usd",
        format_a="money", format_b="money",
        caption="The **dollar curve** is the cost-router yardstick.",
    )
    profile = HarnessProfile(
        title="t", one_liner="ol",
        lane_metrics=metrics,
        lanes=({
            "name": "local", "provider": "llama-server", "model": "qwen3-moe",
            "price_per_m_input_usd": 0.0, "price_per_m_output_usd": 0.0,
        }, {
            "name": "standard", "provider": "openrouter", "model": "gpt-4o-mini",
            "price_per_m_input_usd": 0.15, "price_per_m_output_usd": 0.60,
        }),
    )
    rendered = profile.render()
    assert "$/M input" in rendered
    assert "$/M output" in rendered
    # money formatter: $V/M with 2 decimals
    assert "$0.00/M" in rendered
    assert "$0.15/M" in rendered
    assert "$0.60/M" in rendered
    # tool-call caption is NOT in this card
    assert "format-error rate" not in rendered.lower()
    # H6 caption IS
    assert "dollar curve" in rendered


def test_lane_metric_columns_empty_caption_suppresses() -> None:
    metrics = LaneMetricColumns(
        label_a="A", label_b="B", key_a="a", key_b="b", caption="",
    )
    profile = HarnessProfile(
        title="t", one_liner="ol",
        lane_metrics=metrics,
        lanes=({"name": "x", "provider": "y", "model": "z", "a": 0.5, "b": 0.7},),
    )
    rendered = profile.render()
    assert "A" in rendered and "B" in rendered
    # The default caption is NOT in this card (overridden with empty)
    assert "agent-critical" not in rendered


# --- HarnessProfile v0.12.1 polish: tag dedup + article path-shape ----------


def test_harness_profile_tags_dedup_built_ins() -> None:
    # Caller-supplied tags overlap with built-in `agent-harness` / `hermes` —
    # the rendered frontmatter should NOT list them twice.
    profile = HarnessProfile(
        title="t", one_liner="ol",
        tags=("hermes", "agent-harness", "router"),
    )
    rendered = profile.render()
    fm = rendered.split("---")[1]  # the frontmatter block
    tag_lines = [
        l.strip().lstrip("- ").strip()
        for l in fm.splitlines()
        if l.strip().startswith("- ")
    ]
    # Each built-in appears once (was twice pre-fix); user `router` also present.
    assert tag_lines.count("hermes") == 1
    assert tag_lines.count("agent-harness") == 1
    assert tag_lines.count("router") == 1
    # No extras (4 built-ins + 1 user = 5 unique tags)
    assert len(tag_lines) == 5


def test_harness_profile_to_manifest_renders_article_path_shape() -> None:
    # H5 publisher carried a post-write fixup to convert article: <slug> →
    # article: articles/<slug>/. With the v0.12.1 polish item retired, the
    # manifest should ship path-shape directly.
    profile = HarnessProfile(
        title="t", one_liner="ol",
        article_slug="hermes-cost-routing-local-and-openrouter",
    )
    manifest = profile.to_manifest(slug="spark-x", hf_repo="Orionfold/spark-x")
    assert manifest.article == "articles/hermes-cost-routing-local-and-openrouter/"


def test_harness_profile_to_manifest_article_none_when_no_slug() -> None:
    profile = HarnessProfile(title="t", one_liner="ol", article_slug=None)
    manifest = profile.to_manifest(slug="spark-x", hf_repo="Orionfold/spark-x")
    assert manifest.article is None
