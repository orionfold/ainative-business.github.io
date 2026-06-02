# Copyright 2026 Manav Sehgal
# SPDX-License-Identifier: Apache-2.0
"""Agent-harness serving, configuration, hardening, routing, and profiling.

The deterministic Python spine of the **Harnesses** content line — optimized
agent harnesses released for the DGX Spark, Hermes Agent (Nous Research, MIT)
first. See `_SPECS/hermes-harness-v1.md` for the full design.

**H1 surface (this release):** install + doctor + configure + the NIM /
llama-server serving lanes + the `serve_lane` contextmanager with a
unified-memory guard. The remaining surfaces land across the arc:

- **Serve** (H1 done; H2 adds `VLLMLane` / `OllamaLane`): `NIMLane` /
  `LlamaServerLane` concrete lanes + `serve_lane(spec, guard=True)`.
  `LlamaServerLane` delegates to `notebook.local_server`; `NIMLane` reuses
  `nim.wait_for_warm`; the `serve_lane` guard reuses `capabilities.weight_bytes`
  to refuse a lane that would clearly tip the 128 GB unified-memory envelope.
- **Install / doctor** (H1): `install_hermes`, `hermes_doctor`, `DoctorReport`.
- **Configure** (H1): `HermesConfig` / `EnvFile` / `configure_hermes`.
- **Harden** (H3): `HardeningPolicy` + `harden_config`.
- **Route** (H5–H6): `VerticalRoute` / `RouterConfig` / `build_vertical_router`
  for vertical dispatch (H5); `RouteTier` / `CostRouterConfig` /
  `build_cost_router` for cost-tier escalation (H6). The vertical router
  swaps *which expert* answers a prompt; the cost router swaps *which tier*
  (local $0 / OpenRouter cheap / OpenRouter frontier). Both use
  deterministic keyword + token-budget predicates — no runtime LLM
  classifier.
- **Eval** (H2): `tool_call_reliability` + `HarnessEvalResult` (composes
  `fieldkit.eval`).
- **Profile / publish** (H2): `HarnessProfile` → `ArtifactManifest(kind="harness")`.

Per `feedback_llm_skill_pattern`, this module is deterministic Python only — all
LLM generation (skill bodies, agent task runs, prose) stays in session-driven
skills, never here. Heavy/optional integrations (docker, httpx, the other
fieldkit modules) stay lazy so `import fieldkit.harness` stays cheap.
"""

from __future__ import annotations

import json
import os
import subprocess
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator, Sequence

__all__ = [
    # errors
    "HarnessError",
    "ServingLaneError",
    "UnifiedMemoryExceeded",
    "HermesNotInstalled",
    "DoctorFailed",
    "HardeningError",
    "RoutingError",
    # serve
    "LaneSpec",
    "ServingLane",
    "NIMLane",
    "LlamaServerLane",
    "VLLMLane",
    "OllamaLane",
    "resolve_lane",
    "serve_lane",
    "SERVING_LANES",
    # install / doctor
    "HERMES_INSTALL_URL",
    "install_hermes",
    "hermes_doctor",
    "DoctorCheck",
    "DoctorReport",
    # configure
    "HermesConfig",
    "EnvFile",
    "configure_hermes",
    # harden (H3)
    "HardeningPolicy",
    "DEFAULT_HARDENING",
    "harden_config",
    "LOCAL_PROVIDERS",
    # route (H5 vertical dispatch)
    "VerticalRoute",
    "RouterConfig",
    "build_vertical_router",
    "lane_spec_for_vertical",
    # route (H6 cost-tier escalation)
    "RouteTier",
    "CostRouterConfig",
    "build_cost_router",
    "estimate_tokens",
    # eval (H2)
    "export_hermes_sessions",
    "agent_runs_from_hermes_sessions",
    "tool_call_reliability",
    "HarnessEvalResult",
    # profile / publish (H2; H6 adds `LaneMetricColumns` for $/M column overrides)
    "HarnessProfile",
    "LaneMetricColumns",
    "publish_harness",
    # fieldkit-as-MCP (H4)
    "MCP_SERVER_NAME",
    "McpNotAvailable",
    "MCPToolSpec",
    "MCP_TOOL_SPECS",
    "build_mcp_server",
    "run_mcp_server",
    # brain evaluator (Step 3 — Hermes brain-quality bakeoff promotion)
    "BrainAttempt",
    "BrainCandidate",
    "BrainPromptScore",
    "BrainScorecard",
    "Telemetry",
    "bucket_hermes_sessions",
    "evaluate_brain",
    "evaluate_brains",
    "measure_throughput",
    "point_hermes_at_endpoint",
]


# --- Errors ----------------------------------------------------------------


class HarnessError(Exception):
    """Base for every error raised by `fieldkit.harness`."""


class ServingLaneError(HarnessError):
    """A serving lane failed to start, warm, or tear down cleanly."""


class UnifiedMemoryExceeded(ServingLaneError):
    """The `serve_lane` guard refused a lane that would tip the 128 GB envelope.

    Raised before launch by the `serve_lane` guard when a lane's estimated
    footprint plus the configured headroom would exceed available unified
    memory — the OOM-stacking landmine from `project_spark_unified_memory_oom`.
    The guard errs toward refusing.
    """


class HermesNotInstalled(HarnessError):
    """The `hermes` CLI was not found on PATH (or at the given binary path)."""


class DoctorFailed(HarnessError):
    """`hermes doctor` reported a failing required check."""


class HardeningError(HarnessError):
    """`harden_config` refused to produce a hardened config from this input.

    Raised when the input can't be safely hardened (a cloud provider under
    `local_first`, an `approvals.mode` of `off`/`--yolo`, or a secret sitting
    in the config body instead of `~/.hermes/.env`). The function errs toward
    refusing rather than emitting a falsely-hardened config.
    """


class RoutingError(HarnessError):
    """`build_vertical_router` / `build_cost_router` refused to construct a router.

    Raised on duplicate route or tier names, an empty `routes` / `tiers` set,
    a route with no keywords (a vertical that can never be picked), a
    `default` route that also appears in `routes` (the default is the
    fallback brain — it competes with no one), or a non-monotonic cost-tier
    price progression (the second tier is supposed to cost more than the
    first — a router with `complex < standard < simple` is almost certainly
    a config bug, not an editorial choice). Both functions err toward
    refusing rather than emitting a quietly-broken router.
    """


# --- Serve: lane spec + abstract lane --------------------------------------


@dataclass(frozen=True)
class LaneSpec:
    """A provider-agnostic description of one single-model serving lane.

    The minimal, hashable contract every `ServingLane` is constructed from.
    `provider` selects the concrete lane (`"nim"` / `"llama-server"`; `"vllm"` /
    `"ollama"` land in H2); `model` is the lane-native model id (a NIM image
    short-name or served-model id, an Ollama tag, or an HF GGUF repo). `extra`
    is a free-form escape hatch for lane-specific knobs (e.g. NIM's
    `max_batch_size`, llama-server's `variant`) so new options don't force a
    dataclass change — mirrors `HermesConfig.extra` / `ModelCard.extra_yaml`.
    """

    provider: str
    model: str
    host: str = "127.0.0.1"
    port: int = 8000
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def base_url(self) -> str:
        """OpenAI-compatible base URL the harness points its provider at."""
        return f"http://{self.host}:{self.port}/v1"


class ServingLane:
    """Abstract base for a single-model serving lane on the Spark.

    Defines the lifecycle contract the `serve_lane` contextmanager drives:
    `start()` brings the lane up, `wait_for_warm()` blocks until it answers
    health, `teardown()` stops it (and, for the forthcoming `VLLMLane`, sweeps
    orphaned EngineCore PIDs per `feedback_vllm_engine_core_orphan`), and
    `weight_bytes()` reports the model-weight estimate the unified-memory guard
    checks.
    """

    provider: str = ""

    def __init__(self, spec: LaneSpec) -> None:
        self.spec = spec

    @property
    def base_url(self) -> str:
        return self.spec.base_url

    def start(self) -> None:  # pragma: no cover - abstract
        raise NotImplementedError

    def wait_for_warm(self, timeout: float = 180.0) -> bool:  # pragma: no cover - abstract
        raise NotImplementedError

    def teardown(self) -> None:  # pragma: no cover - abstract
        raise NotImplementedError

    def weight_bytes(self) -> int:  # pragma: no cover - abstract
        raise NotImplementedError


# --- Serve: NIM lane (the H1 hero) -----------------------------------------

# Full image for the project's cached, G2-validated Spark NIM. A bare short-name
# in `LaneSpec.model` (e.g. "nemotron-nano-9b-v2-dgx-spark") is expanded against
# this prefix; a value already containing "/" is used verbatim.
NIM_IMAGE_PREFIX = "nvcr.io/nim/nvidia/nvidia-"
NIM_IMAGE_SUFFIX = ":latest"


class NIMLane(ServingLane):
    """A NVIDIA NIM serving lane — the H1 hero, started via `docker run -d`.

    Codifies the verified-on-Spark recipe (`reference_nim_local_serving`,
    `reference_nim_spark_env_vars`): `--network host`, the cache mount, the
    NGC-key env-file, and `NIM_MAX_BATCH_SIZE=32` (the measured 325 tok/s knob
    for the hybrid-Mamba Nemotron-Nano-9B-v2 — `wait_for_warm` reuses
    `fieldkit.nim`). The served model id (for the OpenAI client / Hermes
    `model:`) is `spec.model` when it contains "/", else queried lazily.

    `weight_bytes()` is the *model-weight* estimate the guard checks; pass
    `footprint_gb` for the realistic resident size (NIM reserves far more than
    weights for CUDA graphs + KV + runtime — ~95 GB observed for the 9B), which
    makes the `serve_lane` guard meaningful against stacking.
    """

    provider = "nim"

    def __init__(
        self,
        spec: LaneSpec,
        *,
        image: str | None = None,
        max_batch_size: int = 32,
        cache_dir: str = "~/.nim/cache",
        secrets_env: str = "~/.nim/secrets.env",
        shm_size: str = "16g",
        container_name: str | None = None,
        params_b: float = 9.0,
        dtype: str = "bf16",
        footprint_gb: float | None = None,
        extra_env: dict[str, str] | None = None,
    ) -> None:
        super().__init__(spec)
        self.image = image or self._resolve_image(spec.model)
        self.max_batch_size = max_batch_size
        self.cache_dir = cache_dir
        self.secrets_env = secrets_env
        self.shm_size = shm_size
        self.container_name = container_name or f"fk-nim-{spec.port}"
        self.params_b = params_b
        self.dtype = dtype
        self.footprint_gb = footprint_gb
        self.extra_env = dict(extra_env or {})

    @staticmethod
    def _resolve_image(model: str) -> str:
        if "/" in model:
            return model
        return f"{NIM_IMAGE_PREFIX}{model}{NIM_IMAGE_SUFFIX}"

    def docker_run_cmd(self) -> list[str]:
        """The exact `docker run` argv this lane launches (no side effects)."""
        cmd = [
            "docker", "run", "-d", "--name", self.container_name,
            "--gpus", "all", "--network", "host", "--shm-size", self.shm_size,
            "--env-file", os.path.expanduser(self.secrets_env),
            "-e", f"NIM_MAX_BATCH_SIZE={self.max_batch_size}",
        ]
        for k, v in self.extra_env.items():
            cmd += ["-e", f"{k}={v}"]
        cmd += [
            "-v", f"{os.path.expanduser(self.cache_dir)}:/opt/nim/.cache",
            self.image,
        ]
        return cmd

    def start(self) -> None:
        # remove a stale same-named container first (Exited/Created) so re-runs
        # don't trip "name already in use".
        subprocess.run(
            ["docker", "rm", "-f", self.container_name],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False,
        )
        proc = subprocess.run(
            self.docker_run_cmd(), capture_output=True, text=True, check=False,
        )
        if proc.returncode != 0:
            raise ServingLaneError(
                f"NIM container failed to start: {proc.stderr.strip() or proc.stdout.strip()}"
            )

    def wait_for_warm(self, timeout: float = 180.0) -> bool:
        from fieldkit.nim import wait_for_warm

        return wait_for_warm(self.base_url, timeout=timeout)

    def teardown(self) -> None:
        subprocess.run(
            ["docker", "stop", self.container_name],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False,
        )

    def weight_bytes(self) -> int:
        if self.footprint_gb is not None:
            return int(self.footprint_gb * 1e9)
        from fieldkit.capabilities import weight_bytes

        return weight_bytes(params_b=self.params_b, dtype=self.dtype)


# --- Serve: llama-server lane (the easy GGUF alternative) ------------------


class LlamaServerLane(ServingLane):
    """A local `llama-server` GGUF lane that **delegates** to
    `notebook.local_server` (cleanest reuse — the project's primary GGUF path).

    `spec.model` is the HF GGUF repo (e.g.
    `Orionfold/patent-strategist-v3-nemo-GGUF`); `spec.extra` may carry
    `variant` / `gguf_file` / `n_ctx` / `reasoning_format`. The lifecycle bridges
    `local_server`'s contextmanager: `start()` enters it, `teardown()` exits it.
    `local_server` already waits for `/health`, so `wait_for_warm()` just
    confirms the endpoint came up.
    """

    provider = "llama-server"

    def __init__(self, spec: LaneSpec, *, params_b: float = 8.0, dtype: str = "int4") -> None:
        super().__init__(spec)
        self.params_b = params_b
        self.dtype = dtype
        self._cm: Any = None
        self._endpoint: str | None = None

    def start(self) -> None:
        from fieldkit.notebook import local_server

        e = self.spec.extra
        self._cm = local_server(
            self.spec.model,
            host=self.spec.host,
            port=self.spec.port,
            **{k: e[k] for k in ("variant", "gguf_file", "n_ctx", "n_gpu_layers",
                                 "chat_template", "reasoning_format", "hf_token")
               if k in e},
        )
        self._endpoint = self._cm.__enter__()

    def wait_for_warm(self, timeout: float = 180.0) -> bool:
        # local_server already blocked on /health inside start(); a non-None
        # endpoint means it warmed.
        return self._endpoint is not None

    def teardown(self) -> None:
        if self._cm is not None:
            self._cm.__exit__(None, None, None)
            self._cm = None
            self._endpoint = None

    def weight_bytes(self) -> int:
        from fieldkit.capabilities import weight_bytes

        return weight_bytes(params_b=self.params_b, dtype=self.dtype)


# --- Serve: shared HTTP health poll + EngineCore orphan sweep --------------


def _wait_http_200(url: str, *, timeout: float, interval: float = 3.0) -> bool:
    """Poll `url` (GET) until it returns HTTP 200 or `timeout` elapses.

    Stdlib-only (urllib) so the lanes don't pull `httpx` just to health-check.
    Used by `VLLMLane`/`OllamaLane` against the OpenAI-compatible `/v1/models`
    endpoint (200 once the engine has the model resident)."""
    import urllib.error
    import urllib.request

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=10) as resp:  # noqa: S310 - local
                if resp.status == 200:
                    return True
        except (urllib.error.URLError, OSError, ValueError):
            pass
        time.sleep(interval)
    return False


def _sweep_engine_core_orphans() -> int:
    """SIGKILL any *host* process whose cmdline names vLLM's `EngineCore`.

    The R8 landmine (`feedback_vllm_engine_core_orphan`): a torn-down vLLM can
    leave an `EngineCore` worker reparented to PID 1 holding ~100 GB of unified
    memory. `VLLMLane` runs vLLM inside docker (so `docker stop` normally reaps
    the workers), but the teardown contract sweeps the host PID table too —
    belt-and-suspenders, and the one place `serve_lane` can't lean on
    `notebook.local_server`. Returns the count of processes signalled.

    Pattern-matched narrowly to `EngineCore` (vLLM's own worker name) so it
    never touches unrelated `python` processes. Verify with `free -h` after."""
    try:
        out = subprocess.run(
            ["pgrep", "-f", "EngineCore"],
            capture_output=True, text=True, check=False,
        )
    except FileNotFoundError:
        return 0
    pids = [p for p in out.stdout.split() if p.strip().isdigit()]
    killed = 0
    for pid in pids:
        try:
            os.kill(int(pid), 9)
            killed += 1
        except (ProcessLookupError, PermissionError):
            pass
    return killed


# --- Serve: vLLM lane (high-throughput MoE; the EngineCore-orphan landmine) -

# The community DGX-Spark vLLM image (eugr/spark-vllm-docker) builds to this tag
# by default; it ships prebuilt, Spark-tested vLLM + FlashInfer wheels for the
# GB10 (compute capability 12.1a) so no aarch64 source build is needed.
VLLM_SPARK_IMAGE = "vllm-node"


class VLLMLane(ServingLane):
    """A vLLM serving lane — the high-throughput MoE path (Qwen3-30B-A3B-FP8).

    Runs `vllm serve <model>` inside the DGX-Spark vLLM image
    (`VLLM_SPARK_IMAGE`) via `docker run -d`, mounting the shared HF cache so
    the served model resolves by repo id. `spec.model` is the HF repo
    (e.g. `Qwen/Qwen3-30B-A3B-FP8`); `spec.extra` carries vLLM knobs
    (`gpu_memory_utilization`, `load_format`, `max_model_len`, `served_name`).

    `teardown()` stops + removes the container, then runs
    `_sweep_engine_core_orphans()` — the R8 landmine
    (`feedback_vllm_engine_core_orphan`) is the one teardown `serve_lane`
    cannot delegate to `notebook.local_server`. Verify `free -h` afterward.
    """

    provider = "vllm"

    def __init__(
        self,
        spec: LaneSpec,
        *,
        image: str = VLLM_SPARK_IMAGE,
        hf_cache_dir: str = "~/data/.hf-cache",
        gpu_memory_utilization: float = 0.7,
        load_format: str = "auto",
        max_model_len: int | None = None,
        container_name: str | None = None,
        params_b: float = 30.0,
        active_params_b: float | None = None,
        dtype: str = "fp8",
        footprint_gb: float | None = None,
        enable_auto_tool_choice: bool = True,
        tool_call_parser: str = "hermes",
        extra_args: Sequence[str] = (),
        hf_token_env: str = "HF_TOKEN",
    ) -> None:
        super().__init__(spec)
        self.image = image
        self.hf_cache_dir = hf_cache_dir
        self.gpu_memory_utilization = spec.extra.get(
            "gpu_memory_utilization", gpu_memory_utilization
        )
        self.load_format = spec.extra.get("load_format", load_format)
        self.max_model_len = spec.extra.get("max_model_len", max_model_len)
        # An agent lane is useless without tool calls; vLLM only emits structured
        # `tool_calls` when served with --enable-auto-tool-choice + a model-matched
        # --tool-call-parser (Qwen3 / Hermes-style models use "hermes"). On by
        # default; override via spec.extra or the constructor.
        self.enable_auto_tool_choice = spec.extra.get(
            "enable_auto_tool_choice", enable_auto_tool_choice
        )
        self.tool_call_parser = spec.extra.get("tool_call_parser", tool_call_parser)
        self.container_name = container_name or f"fk-vllm-{spec.port}"
        self.params_b = params_b
        # MoE lanes activate only a fraction of the weights per token; the guard
        # still checks resident weight bytes (all experts are resident), so
        # active_params_b is informational for the profile, not the guard.
        self.active_params_b = active_params_b
        self.dtype = dtype
        self.footprint_gb = footprint_gb
        self.served_name = spec.extra.get("served_name", spec.model)
        self.extra_args = list(extra_args) + list(spec.extra.get("extra_args", ()))
        self.hf_token_env = hf_token_env

    def docker_run_cmd(self) -> list[str]:
        """The exact `docker run` argv this lane launches (no side effects)."""
        cmd = [
            "docker", "run", "-d", "--name", self.container_name,
            "--gpus", "all", "--network", "host", "--ipc", "host",
            "-v", f"{os.path.expanduser(self.hf_cache_dir)}:/root/.cache/huggingface",
        ]
        token = os.environ.get(self.hf_token_env)
        if token:
            cmd += ["-e", f"HF_TOKEN={token}"]
        cmd += [self.image, "vllm", "serve", self.spec.model,
                "--host", "0.0.0.0", "--port", str(self.spec.port),
                "--gpu-memory-utilization", str(self.gpu_memory_utilization),
                "--load-format", str(self.load_format)]
        if self.max_model_len:
            cmd += ["--max-model-len", str(self.max_model_len)]
        if self.enable_auto_tool_choice:
            cmd += ["--enable-auto-tool-choice"]
            if self.tool_call_parser:
                cmd += ["--tool-call-parser", str(self.tool_call_parser)]
        cmd += self.extra_args
        return cmd

    def start(self) -> None:
        subprocess.run(
            ["docker", "rm", "-f", self.container_name],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False,
        )
        proc = subprocess.run(
            self.docker_run_cmd(), capture_output=True, text=True, check=False,
        )
        if proc.returncode != 0:
            raise ServingLaneError(
                f"vLLM container failed to start: {proc.stderr.strip() or proc.stdout.strip()}"
            )

    def wait_for_warm(self, timeout: float = 600.0) -> bool:
        # vLLM cold-loads large weights; allow a long default. /v1/models 200
        # once the engine is serving.
        return _wait_http_200(f"{self.base_url}/models", timeout=timeout)

    def teardown(self) -> None:
        subprocess.run(
            ["docker", "rm", "-f", self.container_name],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False,
        )
        _sweep_engine_core_orphans()

    def weight_bytes(self) -> int:
        if self.footprint_gb is not None:
            return int(self.footprint_gb * 1e9)
        from fieldkit.capabilities import weight_bytes

        return weight_bytes(params_b=self.params_b, dtype=self.dtype)


# --- Serve: Ollama lane (the easiest local alternative) --------------------


class OllamaLane(ServingLane):
    """An Ollama serving lane — the lowest-friction local alternative.

    Matches the NVIDIA official Spark guide's first-turn path. `spec.model` is
    an Ollama tag (e.g. `qwen3:30b-a3b`). `start()` ensures `ollama serve` is up
    (daemon) and `ollama pull`s the tag; the model loads lazily on first
    request. The OpenAI-compatible endpoint is `:11434/v1` (the lane's default
    port). `teardown()` unloads the model (`ollama stop`) to free unified
    memory but leaves the daemon running — per `feedback_stop_unneeded_services`
    a model resident is the memory cost, not the idle daemon.
    """

    provider = "ollama"

    def __init__(
        self,
        spec: LaneSpec | None = None,
        *,
        model: str = "",
        params_b: float = 8.0,
        dtype: str = "int4",
        ollama_bin: str = "ollama",
        pull: bool = True,
    ) -> None:
        if spec is None:
            spec = LaneSpec(provider="ollama", model=model, port=11434)
        super().__init__(spec)
        self.params_b = params_b
        self.dtype = dtype
        self.ollama_bin = ollama_bin
        self.pull = pull
        self._serve_proc: Any = None

    def _daemon_up(self) -> bool:
        return _wait_http_200(f"http://{self.spec.host}:{self.spec.port}/api/tags", timeout=2.0, interval=1.0)

    def start(self) -> None:
        if not self._daemon_up():
            # Start `ollama serve` detached; it backgrounds itself as a daemon.
            self._serve_proc = subprocess.Popen(  # noqa: S603
                [self.ollama_bin, "serve"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                stdin=subprocess.DEVNULL,
            )
            if not _wait_http_200(
                f"http://{self.spec.host}:{self.spec.port}/api/tags",
                timeout=30.0, interval=1.0,
            ):
                raise ServingLaneError("ollama serve did not come up on :11434")
        if self.pull and self.spec.model:
            proc = subprocess.run(
                [self.ollama_bin, "pull", self.spec.model],
                capture_output=True, text=True, check=False,
            )
            if proc.returncode != 0:
                raise ServingLaneError(
                    f"ollama pull {self.spec.model} failed: {proc.stderr.strip()[-300:]}"
                )

    def wait_for_warm(self, timeout: float = 180.0) -> bool:
        # Warm a generation so the model is resident before the bench starts.
        return _wait_http_200(f"{self.base_url}/models", timeout=timeout)

    def teardown(self) -> None:
        if self.spec.model:
            subprocess.run(
                [self.ollama_bin, "stop", self.spec.model],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False,
            )

    def weight_bytes(self) -> int:
        from fieldkit.capabilities import weight_bytes

        return weight_bytes(params_b=self.params_b, dtype=self.dtype)


# Registry of concrete lanes by `provider` string (populated as each lands).
# `resolve_lane(spec)` looks the constructor up here so callers can build a lane
# from a bare `LaneSpec` without importing the concrete classes.
SERVING_LANES: dict[str, type[ServingLane]] = {
    "nim": NIMLane,
    "llama-server": LlamaServerLane,
    "vllm": VLLMLane,
    "ollama": OllamaLane,
}


def resolve_lane(spec: LaneSpec, **kwargs: Any) -> ServingLane:
    """Construct the concrete `ServingLane` for `spec.provider` from the
    registry. Extra kwargs pass through to the lane constructor."""
    try:
        cls = SERVING_LANES[spec.provider]
    except KeyError as exc:
        known = ", ".join(sorted(SERVING_LANES)) or "(none registered)"
        raise ServingLaneError(
            f"no serving lane for provider {spec.provider!r}; known: {known}"
        ) from exc
    return cls(spec, **kwargs)


def _available_memory_gb() -> float | None:
    """Currently-available unified memory in GB from `/proc/meminfo`
    (`MemAvailable`), or None off-Linux. This is what the live OOM-stacking
    guard checks — total envelope is a separate, coarser sanity bound."""
    try:
        for line in Path("/proc/meminfo").read_text().splitlines():
            if line.startswith("MemAvailable:"):
                return int(line.split()[1]) / (1024 * 1024)  # kB -> GB
    except (OSError, ValueError, IndexError):
        return None
    return None


@contextmanager
def serve_lane(
    lane: ServingLane | LaneSpec,
    *,
    guard: bool = True,
    headroom_gb: float = 8.0,
    warm_timeout: float = 180.0,
    **lane_kwargs: Any,
) -> Iterator[ServingLane]:
    """Bring `lane` up for the `with` block, then tear it down — the OOM-safe
    "one model at a time" pattern (the contextmanager's teardown is the
    structural guarantee against stacking, per `project_spark_unified_memory_oom`).

    Accepts a concrete `ServingLane` or a bare `LaneSpec` (resolved via
    `resolve_lane`). With `guard=True` (default), refuses to start a lane whose
    estimated footprint + `headroom_gb` exceeds currently-available unified
    memory, raising `UnifiedMemoryExceeded` *before* launch — erring toward
    refusing. Raises `ServingLaneError` if the lane never warms.

        with serve_lane(LaneSpec("nim", "nemotron-nano-9b-v2-dgx-spark")) as l:
            ...  # NIM live on l.base_url
    """
    if isinstance(lane, LaneSpec):
        lane = resolve_lane(lane, **lane_kwargs)

    if guard:
        est_gb = lane.weight_bytes() / 1e9
        free_gb = _available_memory_gb()
        if free_gb is not None and est_gb + headroom_gb > free_gb:
            raise UnifiedMemoryExceeded(
                f"lane {lane.provider!r} estimated at {est_gb:.1f} GB + "
                f"{headroom_gb:.1f} GB headroom exceeds {free_gb:.1f} GB available "
                "unified memory. Stop other lanes/models first "
                "(one model at a time)."
            )

    lane.start()
    try:
        if not lane.wait_for_warm(timeout=warm_timeout):
            raise ServingLaneError(
                f"lane {lane.provider!r} did not warm within {warm_timeout:.0f}s "
                f"at {lane.base_url}"
            )
        yield lane
    finally:
        lane.teardown()


# --- Install / doctor ------------------------------------------------------

HERMES_INSTALL_URL = "https://raw.githubusercontent.com/NousResearch/hermes-agent/main/scripts/install.sh"
"""The official Hermes Agent (Nous Research, MIT) install script."""


def install_hermes(
    *,
    method: str = "script",
    dry_run: bool = True,
    allow_pipe_to_bash: bool = False,
    install_url: str = HERMES_INSTALL_URL,
) -> str:
    """Install Hermes Agent, or (default) return the exact command without running it.

    Two-key safety on piping a remote script to a shell: `dry_run=True` (default)
    only *returns* the `curl -fsSL <url> | bash` command string for review. To
    actually execute it you must pass **both** `dry_run=False` **and**
    `allow_pipe_to_bash=True` — a single flag is intentionally not enough.

    Returns the command string in every case. The non-root install lands in
    `~/.hermes/`, symlinks `~/.local/bin/hermes`, and pulls nothing into Docker
    (reviewed for v0.14.0).
    """
    if method != "script":
        raise HarnessError(f"unknown install method {method!r}; only 'script' is supported")
    cmd = f"curl -fsSL {install_url} | bash"
    if dry_run:
        return cmd
    if not allow_pipe_to_bash:
        raise HarnessError(
            "refusing to pipe a remote script to bash without allow_pipe_to_bash=True "
            "(two-key safety). Review the command first:\n  " + cmd
        )
    proc = subprocess.run(
        cmd, shell=True, executable="/bin/bash", stdin=subprocess.DEVNULL,
        capture_output=True, text=True, check=False,
    )
    if proc.returncode != 0:
        raise HarnessError(
            f"hermes install failed (exit {proc.returncode}): {proc.stderr.strip()[-500:]}"
        )
    return cmd


@dataclass(frozen=True)
class DoctorCheck:
    """One `hermes doctor` line: a check name, pass/fail, detail, and section.

    `required` distinguishes a real failure (a core-section check that failed)
    from an expected ✗/⚠ on an optional, un-configured surface — Hermes lists
    *dozens* of optional integrations (discord, spotify, web-search API keys,
    ripgrep) as ✗ when you haven't configured them, none of which matter to a
    local-NIM agent. Classification is by `section` (robust to upstream churn,
    R11) rather than per-line phrase matching. Mirrors `eval.GradeResult`'s
    per-item shape.
    """

    name: str
    ok: bool
    detail: str = ""
    required: bool = True
    section: str = ""


@dataclass(frozen=True)
class DoctorReport:
    """Parsed `hermes doctor` output: a list of `DoctorCheck`s plus a binary
    `.ok` (True iff every *required* check passed) and a `.report()` markdown
    summary. Mirrors `eval.GradeResult` — the harness analog of a grade."""

    checks: list[DoctorCheck]
    raw: str = ""

    @property
    def ok(self) -> bool:
        return all(c.ok for c in self.checks if c.required)

    @property
    def n_failed(self) -> int:
        return sum(1 for c in self.checks if c.required and not c.ok)

    def report(self) -> str:
        lines = [f"# hermes doctor — {'OK' if self.ok else f'{self.n_failed} required failure(s)'}", ""]
        for c in self.checks:
            mark = "✓" if c.ok else ("⚠" if not c.required else "✗")
            detail = f" — {c.detail}" if c.detail else ""
            lines.append(f"- {mark} {c.name}{detail}")
        return "\n".join(lines)


# `hermes doctor` groups checks under `◆ Section` headers. Only these core
# sections gate a working local-NIM agent; everything else (cloud auth, opt-in
# integrations, external-tool niceties, live API connectivity that depends on a
# lane being up) is informational. Section-based is robust to upstream churn
# (R11) — new integration sections don't silently become "required".
_DOCTOR_CORE_SECTIONS = frozenset({
    "Security Advisories",
    "Python Environment",
    "Required Packages",
    "Configuration Files",
    "Directory Structure",
    "Command Installation",
})
# Within a core section, these substrings still mark a line optional (e.g.
# "Croniter (optional)", "python-telegram-bot (optional, not installed)").
_DOCTOR_OPTIONAL_HINTS = ("optional", "not logged in")


def hermes_doctor(*, hermes_bin: str = "hermes", timeout: float = 120.0) -> DoctorReport:
    """Run `hermes doctor` and parse its sectioned ✓/⚠/✗ output into a `DoctorReport`.

    A check is `required` iff it falls under a core section
    (`_DOCTOR_CORE_SECTIONS`) and isn't an explicitly-optional line — so the
    dozens of un-configured integration ✗'s Hermes emits don't make `.ok` False.

    Raises `HermesNotInstalled` if the binary isn't found. Does NOT raise on a
    failing check — inspect `report.ok` / `report.report()` (raise `DoctorFailed`
    yourself for hard-fail semantics)."""
    import shutil

    if shutil.which(hermes_bin) is None and not Path(os.path.expanduser(hermes_bin)).exists():
        raise HermesNotInstalled(
            f"{hermes_bin!r} not found. Install with install_hermes(dry_run=False, "
            "allow_pipe_to_bash=True), then ensure ~/.local/bin is on PATH."
        )
    proc = subprocess.run(
        [hermes_bin, "doctor"], stdin=subprocess.DEVNULL,
        capture_output=True, text=True, check=False, timeout=timeout,
    )
    raw = (proc.stdout or "") + (proc.stderr or "")
    checks: list[DoctorCheck] = []
    section = ""
    for line in raw.splitlines():
        s = line.strip()
        if s.startswith("◆"):
            section = s[1:].strip()
            continue
        if not s or s[0] not in "✓⚠✗":
            continue
        mark, text = s[0], s[1:].strip()
        ok = mark == "✓"
        is_optional_line = any(h in text.lower() for h in _DOCTOR_OPTIONAL_HINTS)
        required = section in _DOCTOR_CORE_SECTIONS and not is_optional_line
        checks.append(DoctorCheck(name=text, ok=ok, required=required, section=section))
    return DoctorReport(checks=checks, raw=raw)


# --- Configure -------------------------------------------------------------

# Local serving is slow vs cloud; raise the socket read timeout so long
# local cold generations don't trip the default. The installer auto-raises to
# this for local providers; we mirror it explicitly.
HERMES_STREAM_READ_TIMEOUT_SLOW = 1800


@dataclass(frozen=True)
class HermesConfig:
    """The `model:` section of `~/.hermes/config.yaml` for one provider.

    For a local NIM / llama-server the verified shape is `provider="custom"`
    (Hermes aliases `ollama`/`vllm`/`llamacpp` → `custom`) with an explicit
    `base_url`. `extra` is a free-form escape hatch for new Hermes YAML keys so
    upstream churn doesn't force a fieldkit release (decision §3.1 #10).
    `render()` emits the YAML block; `config_set_commands()` emits the
    equivalent `hermes config set` lines (Hermes owns the heavily-commented,
    versioned config.yaml, so setting keys is cleaner than overwriting it).
    """

    provider: str = "custom"
    base_url: str = "http://127.0.0.1:8000/v1"
    model: str = ""
    extra: dict[str, Any] = field(default_factory=dict)
    sections: dict[str, Any] = field(default_factory=dict)
    """Top-level config.yaml sections beyond `model:` (e.g. `terminal`,
    `tool_loop_guardrails`, `approvals`). Empty for a plain configure;
    populated by `harden_config` (H3). `render()` emits them after `model:`."""

    def _model_block(self) -> dict[str, Any]:
        block: dict[str, Any] = {"provider": self.provider, "base_url": self.base_url}
        if self.model:
            block["default"] = self.model
        block.update(self.extra)
        return block

    def render(self) -> str:
        """The config.yaml block(s) (reuses publish's stdlib emitter — no dep).

        Always emits `model:`; appends any hardened top-level `sections` after
        it (insertion order preserved, so `model:` stays first)."""
        from fieldkit.publish import _render_yaml_block

        blocks: dict[str, Any] = {"model": self._model_block()}
        blocks.update(self.sections)
        return "\n".join(_render_yaml_block(blocks))

    def config_set_commands(self) -> list[str]:
        """`hermes config set ...` lines that produce this config.

        Covers `model.*` plus every *scalar* leaf in `sections`. List/dict
        leaves (e.g. `terminal.docker_extra_args`) are skipped — `hermes config
        set` coerces bools/ints but stores everything else as a raw string, so
        those keys must be applied via the rendered config.yaml instead."""
        cmds = [
            f"hermes config set model.provider {self.provider}",
            f"hermes config set model.base_url {self.base_url}",
        ]
        if self.model:
            cmds.append(f"hermes config set model.default {self.model}")
        for path, value in _flatten_scalars(self.sections):
            cmds.append(f"hermes config set {path} {_config_set_literal(value)}")
        return cmds


@dataclass(frozen=True)
class EnvFile:
    """A `~/.hermes/.env` rendering. Values in `.env` take precedence over
    config.yaml. `render()` emits `KEY=VALUE` lines (sorted, stable)."""

    values: dict[str, str] = field(default_factory=dict)

    def render(self) -> str:
        return "\n".join(f"{k}={self.values[k]}" for k in sorted(self.values))


def configure_hermes(
    *,
    lane: ServingLane | None = None,
    provider: str = "custom",
    base_url: str | None = None,
    model: str | None = None,
    api_key: str = "local",
    slow_serving: bool = True,
) -> tuple[HermesConfig, EnvFile]:
    """Build the (`HermesConfig`, `EnvFile`) pair to point Hermes at a local
    lane — no side effects; the caller `.render()`s and writes them (or runs
    `config.config_set_commands()`).

    Endpoint resolution mirrors `notebook.open_model`: an explicit `base_url`
    wins; else `lane.base_url`; else autodiscover a running local server
    (`notebook.discover_local_server` probes :8080 llama-server, :8000 NIM).
    `slow_serving=True` sets `HERMES_STREAM_READ_TIMEOUT` to 1800 s for long
    local cold generations.
    """
    if base_url is None and lane is not None:
        base_url = lane.base_url
    if base_url is None:
        from fieldkit.notebook import discover_local_server

        found = discover_local_server()
        if found is None:
            raise HarnessError(
                "no base_url given, no lane, and no local server discovered on "
                ":8080/:8000. Start a lane (serve_lane) or pass base_url."
            )
        base_url = found.rstrip("/") + "/v1" if not found.rstrip("/").endswith("/v1") else found

    config = HermesConfig(provider=provider, base_url=base_url, model=model or "")
    env_values = {"OPENAI_BASE_URL": base_url, "OPENAI_API_KEY": api_key}
    if slow_serving:
        env_values["HERMES_STREAM_READ_TIMEOUT"] = str(HERMES_STREAM_READ_TIMEOUT_SLOW)
    return config, EnvFile(values=env_values)


# --- Harden (H3) -----------------------------------------------------------
#
# Hermes ships permissive defaults for fast local iteration: terminal backend
# `local` (commands run straight on the host), tool-loop guardrails warn-only
# (`hard_stop_enabled: false`), and the agent can be run `--yolo` (approvals
# off). A harness you'd leave running on your desk needs the opposite posture.
# `harden_config` is a pure function — (HermesConfig, HardeningPolicy) -> a new
# frozen HermesConfig carrying the hardened top-level sections, mapped to the
# real Hermes config keys verified against the installed v0.14.0 schema
# (terminal.* / tool_loop_guardrails.* / approvals.* / agent.* / session_reset.*).
# It errs toward refusing: an un-hardenable input raises HardeningError rather
# than emitting a falsely-hardened config.
#
# Conceptual basis is the project's Guardrails-on-the-retrieval-path pattern —
# a frozen policy object + a pure apply function, no hidden side effects.

# Providers Hermes serves locally (no cloud egress). `custom` aliases
# ollama/vllm/llamacpp with an explicit local base_url (the verified NIM /
# llama-server shape). The native `nvidia` provider is *cloud* Nemotron — so it
# is deliberately excluded from the local-first allowlist.
LOCAL_PROVIDERS = ("custom", "ollama", "vllm", "llamacpp", "local")

# Substrings that mark a key as carrying a secret. If one shows up in the
# config *body* (`extra`/`sections`) under `secrets_from_env_only`, harden_config
# refuses — secrets belong in `~/.hermes/.env` (Hermes' own `config set` routes
# `*_API_KEY`/`*_TOKEN` there automatically).
_SECRET_KEY_HINTS = ("api_key", "token", "secret", "password")


def _flatten_scalars(d: dict[str, Any], prefix: str = "") -> list[tuple[str, Any]]:
    """`(dotted.path, value)` for scalar leaves only (recurses into dicts,
    skips list/dict leaves). Used to emit `hermes config set` lines."""
    out: list[tuple[str, Any]] = []
    for k, v in d.items():
        path = f"{prefix}.{k}" if prefix else str(k)
        if isinstance(v, dict):
            out.extend(_flatten_scalars(v, path))
        elif isinstance(v, (str, int, float, bool)):
            out.append((path, v))
        # lists / None are skipped — see config_set_commands docstring.
    return out


def _config_set_literal(value: Any) -> str:
    """Render a scalar the way `hermes config set` coerces it back: bools as
    lowercase `true`/`false`, everything else `str()`'d."""
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def _find_secret_keys(d: dict[str, Any], prefix: str = "") -> list[str]:
    """Dotted paths of secret-looking keys anywhere in a nested mapping."""
    found: list[str] = []
    for k, v in d.items():
        kl = str(k).lower()
        path = f"{prefix}.{k}" if prefix else str(k)
        if any(hint in kl for hint in _SECRET_KEY_HINTS):
            found.append(path)
        if isinstance(v, dict):
            found.extend(_find_secret_keys(v, path))
    return found


@dataclass(frozen=True)
class HardeningPolicy:
    """The desk-grade posture `harden_config` applies to a `HermesConfig`.

    Defaults are the spec §4.3 baseline: a docker-sandboxed terminal with
    network egress denied, secrets confined to `~/.hermes/.env`, a local-only
    provider, manual approvals, hard-stopping tool-loop guardrails, a turn cap,
    and an ephemeral (non-persistent) sandbox that resets on a schedule. Every
    field maps to a real Hermes config key (verified against the installed
    v0.14.0 schema). Frozen + plain data — no I/O on construction.
    """

    terminal_backend: str = "docker"          # terminal.backend — sandbox, not host `local`
    network_egress: str = "deny"              # "deny" -> terminal.docker_extra_args += --network=none
    secrets_from_env_only: bool = True        # refuse secrets in the config body
    local_first: bool = True                  # provider must be in LOCAL_PROVIDERS
    approval_mode: str = "manual"             # approvals.mode (manual|smart); "off" is refused
    hard_stop_loops: bool = True              # tool_loop_guardrails.hard_stop_enabled
    max_turns: int = 30                       # agent.max_turns cap (Hermes default 60)
    ephemeral_terminal: bool = True           # terminal.container_persistent=false + mount off
    terminal_lifetime_seconds: int = 300      # terminal.lifetime_seconds
    deny_toolsets: tuple[str, ...] = ()       # agent.disabled_toolsets
    auto_restart: bool = True                 # session_reset wiring (idle + daily)
    idle_reset_minutes: int = 1440            # session_reset.idle_minutes
    reset_at_hour: int = 4                    # session_reset.at_hour


DEFAULT_HARDENING = HardeningPolicy()
"""The spec §4.3 baseline policy (docker / egress-deny / env-secrets / local-first)."""


def harden_config(
    config: HermesConfig,
    policy: HardeningPolicy = DEFAULT_HARDENING,
) -> HermesConfig:
    """Apply `policy` to `config`, returning a NEW hardened frozen `HermesConfig`.

    Pure function — `config` is left unchanged. Raises `HardeningError` when the
    input can't be safely hardened:

    - `local_first` and the provider is not in `LOCAL_PROVIDERS` (a cloud
      provider would defeat the local-only posture).
    - `approval_mode == "off"` (that is `--yolo`; refusing to bless it).
    - `secrets_from_env_only` and a secret-looking key sits in `extra`/`sections`
      (secrets belong in `~/.hermes/.env`, never the config body).

    The returned config carries the hardened top-level sections (`terminal`,
    `tool_loop_guardrails`, `approvals`, `agent`, optional `session_reset`),
    emitted by `.render()` and partly applyable via `.config_set_commands()`
    (scalar keys only — see that method's note on the list-valued
    `terminal.docker_extra_args`).
    """
    if policy.local_first and config.provider not in LOCAL_PROVIDERS:
        raise HardeningError(
            f"local_first policy: provider {config.provider!r} is not local "
            f"(allowed: {', '.join(LOCAL_PROVIDERS)}). A cloud provider defeats "
            "the local-only posture — harden against a local lane instead."
        )
    if policy.approval_mode == "off":
        raise HardeningError(
            "approval_mode 'off' is --yolo; harden_config refuses to emit it. "
            "Use 'manual' (always prompt) or 'smart' (auxiliary-LLM triage)."
        )
    if policy.secrets_from_env_only:
        leaked = _find_secret_keys(config.extra) + _find_secret_keys(config.sections)
        if leaked:
            raise HardeningError(
                f"secrets_from_env_only policy: secret-looking key(s) {leaked} in "
                "the config body. Secrets belong in ~/.hermes/.env (Hermes' own "
                "`config set` routes *_API_KEY/*_TOKEN there). Move them out."
            )

    terminal: dict[str, Any] = {
        "backend": policy.terminal_backend,
        "container_persistent": not policy.ephemeral_terminal,
        "docker_mount_cwd_to_workspace": False,
        "lifetime_seconds": policy.terminal_lifetime_seconds,
    }
    if policy.network_egress == "deny":
        terminal["docker_extra_args"] = ["--network=none"]

    agent: dict[str, Any] = {
        "max_turns": policy.max_turns,
        "subagent_auto_approve": False,
    }
    if policy.deny_toolsets:
        agent["disabled_toolsets"] = list(policy.deny_toolsets)

    sections: dict[str, Any] = {
        **config.sections,
        "terminal": terminal,
        "tool_loop_guardrails": {
            "warnings_enabled": True,
            "hard_stop_enabled": policy.hard_stop_loops,
        },
        "approvals": {"mode": policy.approval_mode, "cron_mode": "deny"},
        "agent": agent,
    }
    if policy.auto_restart:
        sections["session_reset"] = {
            "mode": "both",
            "idle_minutes": policy.idle_reset_minutes,
            "at_hour": policy.reset_at_hour,
        }

    return HermesConfig(
        provider=config.provider,
        base_url=config.base_url,
        model=config.model,
        extra=dict(config.extra),
        sections=sections,
    )


# --- Route: vertical router (H5) -------------------------------------------
#
# The H5 surface: route an inbound prompt to one of N already-published
# verticals (the 5 Orionfold GGUFs — patent / legal / finance / cyber / medical)
# served one-at-a-time under the 128 GB unified-memory envelope; fall through
# to a strong general default brain when no vertical's keywords fire. This is
# pure config + a deterministic predicate; the serving itself is done by
# `serve_lane` (the OOM-safe contextmanager already in this module).
#
# Per spec §4.6 discipline, the classifier is **deterministic** — keyword
# sets — NOT a runtime LLM classifier. Two reasons: (a) zero memory cost (a
# 1.5B Tier-0 classifier would compete with the brain for the envelope) and
# (b) a misroute on a vertical-named prompt is auditable (you can read the
# keyword list and see why); a black-box classifier's misroutes are not.
#
# H6 adds `RouteTier` + `build_cost_router` (3-tier local→OpenRouter cost
# router) — same `RouterConfig` shape, different builder, lands separately.


@dataclass(frozen=True)
class VerticalRoute:
    """One vertical lane in a `RouterConfig`.

    A vertical is a domain (patent / legal / finance / cyber / medical) backed
    by a specific GGUF on HF + a chosen variant. The router picks at most one
    vertical per inbound prompt; the caller then serves it via `serve_lane`
    one-at-a-time per the unified-memory envelope.

    `keywords` is the deterministic classifier signal — lowercased
    substring matches against the prompt (no regex, no LLM). Tune per vertical
    from a small bench. `weight` defaults to `1.0`; bump it to bias toward a
    more specific vertical when two routes' keyword sets overlap (e.g.,
    medical over cyber when both fire on `"security"`).

    `params_b` / `dtype` flow into `LlamaServerLane.weight_bytes()` for the
    `serve_lane` unified-memory guard — see `lane_spec_for_vertical` for the
    default `LaneSpec` builder this route renders to.
    """

    name: str
    hf_repo: str
    variant: str = "Q5_K_M"
    keywords: tuple[str, ...] = ()
    description: str = ""
    base_model: str = ""
    params_b: float = 8.0
    dtype: str = "int4"
    weight: float = 1.0
    article: str | None = None


@dataclass(frozen=True)
class RouterConfig:
    """A frozen router config — a tuple of `VerticalRoute`s + a `default` route.

    `default` is the fallback served when no vertical's keyword score is
    positive — typically a strong general brain (the Step-2 pinned
    Qwen3-30B-A3B MoE) so generic prompts don't get mis-routed to a vertical
    specialist. `escalation` is an optional cloud lane (e.g. OpenRouter) for
    prompts that overflow local capacity — reserved for the H6 cost router.

    `.classify(prompt)` is a pure predicate over the keyword sets — the
    auditable core of the router. `.render_yaml()` emits the router config
    for inclusion in a `HarnessProfile.router_yaml`. `.serve_for(prompt)` is
    the OOM-safe convenience: classify, then `serve_lane` the picked
    vertical (one-at-a-time).
    """

    routes: tuple[VerticalRoute, ...]
    default: VerticalRoute
    escalation: VerticalRoute | None = None

    def classify(self, prompt: str) -> VerticalRoute:
        """Pick the vertical for `prompt` via deterministic keyword scoring.

        Each keyword that occurs in `prompt.lower()` contributes `route.weight`
        to that route's score; the highest-scoring route wins. Ties: the
        route appearing **earlier** in `routes` wins (stable, listed-first
        bias). Zero matches: `default`. Pure function — no I/O, no model.
        """
        text = prompt.lower()
        best: tuple[float, int, VerticalRoute] | None = None
        for i, route in enumerate(self.routes):
            hits = sum(1 for kw in route.keywords if kw.lower() in text)
            if hits == 0:
                continue
            score = hits * route.weight
            # ties: earlier index wins (negate i for stable tiebreak via min)
            cand = (-score, i, route)
            if best is None or cand < best:
                best = cand
        return best[2] if best is not None else self.default

    def route_for(self, prompt: str) -> VerticalRoute:
        """Alias for `classify` that reads better at call sites
        (`route = config.route_for(prompt)`)."""
        return self.classify(prompt)

    def render_yaml(self) -> str:
        """Render the router as a `router.yaml` block — deterministic, diff-stable.

        Embedded in `HarnessProfile.router_yaml` so the published `harness`
        artifact carries the actual routing table, not just prose.
        """
        from fieldkit.publish import _render_yaml_block

        def _route_dict(r: VerticalRoute, *, fallback: bool = False) -> dict[str, Any]:
            d: dict[str, Any] = {"name": r.name, "hf_repo": r.hf_repo, "variant": r.variant}
            if not fallback and r.keywords:
                d["keywords"] = list(r.keywords)
            if r.description:
                d["description"] = r.description
            if r.weight != 1.0 and not fallback:
                d["weight"] = r.weight
            return d

        data: dict[str, Any] = {
            "router": {
                "kind": "vertical",
                "default": _route_dict(self.default, fallback=True),
                "routes": [_route_dict(r) for r in self.routes],
            }
        }
        if self.escalation is not None:
            data["router"]["escalation"] = _route_dict(self.escalation, fallback=True)
        return "\n".join(_render_yaml_block(data)) + "\n"

    @contextmanager
    def serve_for(
        self,
        prompt: str,
        *,
        guard: bool = True,
        headroom_gb: float = 8.0,
        warm_timeout: float = 180.0,
        host: str = "127.0.0.1",
        port: int = 8080,
        lane_factory: Any = None,
    ) -> Iterator[tuple[VerticalRoute, ServingLane]]:
        """Classify `prompt`, then `serve_lane` the picked vertical one-at-a-time.

        Yields `(picked_route, serving_lane)`. The `serve_lane` contextmanager
        is the structural guarantee against stacking — only one vertical is
        warm at a time (cf. `project_spark_unified_memory_oom`).

        `lane_factory(route) -> LaneSpec | ServingLane` overrides the default
        (`lane_spec_for_vertical`, which builds an `LlamaServerLane`-bound
        `LaneSpec`). Override to point at an in-process NIM, a remote
        endpoint, etc.

        The `default` route is **not** auto-served here — most defaults are a
        long-running general brain (e.g. the pinned MoE) that callers warm
        once and leave up. If you want it served too, call `.classify(prompt)`
        + `serve_lane()` directly.
        """
        picked = self.classify(prompt)
        if lane_factory is None:
            spec = lane_spec_for_vertical(picked, host=host, port=port)
        else:
            spec = lane_factory(picked)
        with serve_lane(
            spec, guard=guard, headroom_gb=headroom_gb, warm_timeout=warm_timeout,
            params_b=picked.params_b, dtype=picked.dtype,
        ) as lane:
            yield picked, lane


def lane_spec_for_vertical(
    route: VerticalRoute,
    *,
    host: str = "127.0.0.1",
    port: int = 8080,
    n_ctx: int | None = None,
    reasoning_format: str | None = None,
) -> LaneSpec:
    """Build the default `LlamaServerLane`-bound `LaneSpec` for `route`.

    The router defaults to `llama-server` because it's the simplest cold-start
    lane on Spark (a llama.cpp process per vertical; teardown reaps cleanly
    via the `notebook.local_server` delegate's contextmanager — no
    EngineCore-orphan tax). `n_ctx` / `reasoning_format` flow into
    `local_server` via `spec.extra`. Pure function (no I/O)."""
    extra: dict[str, Any] = {"variant": route.variant}
    if n_ctx is not None:
        extra["n_ctx"] = n_ctx
    if reasoning_format is not None:
        extra["reasoning_format"] = reasoning_format
    return LaneSpec(
        provider="llama-server", model=route.hf_repo, host=host, port=port, extra=extra,
    )


def build_vertical_router(
    routes: Sequence[VerticalRoute],
    *,
    default: VerticalRoute,
    escalation: VerticalRoute | None = None,
) -> RouterConfig:
    """Construct a `RouterConfig` from per-vertical routes + a default brain.

    Lightweight validation (raises `RoutingError`):
    - `routes` non-empty
    - all route names unique
    - every route has at least one keyword (a route with no keywords can
      never be picked — that's a bug, not a config choice)
    - `default.name` not among `routes` names (the default is the fallback,
      not a competitor; including it in both lists confuses the classifier
      semantics)

    The classifier itself is deterministic keyword scoring per spec §4.6;
    no LLM, no embedder. See `RouterConfig.classify`.
    """
    if not routes:
        raise RoutingError("build_vertical_router: `routes` must be non-empty.")
    seen: set[str] = set()
    for r in routes:
        if not r.name:
            raise RoutingError("build_vertical_router: route name must be non-empty.")
        if r.name in seen:
            raise RoutingError(f"build_vertical_router: duplicate route name {r.name!r}.")
        seen.add(r.name)
        if not r.keywords:
            raise RoutingError(
                f"build_vertical_router: route {r.name!r} has no keywords — it could "
                "never be picked. Add at least one vertical-distinctive keyword."
            )
    if default.name in seen:
        raise RoutingError(
            f"build_vertical_router: `default` route {default.name!r} also appears in "
            "`routes`. The default is the fallback brain — it competes with no one."
        )
    return RouterConfig(routes=tuple(routes), default=default, escalation=escalation)


# --- Route (H6): cost-tier escalation router -------------------------------
#
# Sibling of the H5 vertical router (above). The vertical router decides
# **which expert** answers a prompt (one of five Orionfold GGUFs) — same
# tier, different domains. The cost router decides **which tier** answers it
# (local Spark $0 → OpenRouter cheap → OpenRouter frontier) — same domain,
# different price/capacity envelopes. Both use deterministic keyword +
# token-budget predicates; neither runs an LLM at classification time.
#
# Reframed editorially per HANDOFF: the cost-savings pitch barely applies
# on a $0 local lane — the genuinely-interesting question is *when does the
# local MoE actually fail and we need to call OpenRouter*. The classifier
# is the leak-rate measurement instrument, not the savings instrument.


def estimate_tokens(text: str) -> int:
    """Rough token estimate from raw text (4 chars/token heuristic).

    Used by `CostRouterConfig.classify` when the caller doesn't pass an
    explicit `est_input_tokens`. ~4-chars-per-token is the GPT-family rule
    of thumb; close enough for routing decisions (we're picking *which
    tier* — a 10% over/undercount doesn't flip the decision). Avoids
    taking a tokenizer dependency for a single int. Pure function."""
    return max(1, len(text) // 4)


@dataclass(frozen=True)
class RouteTier:
    """One tier in a cost-tier router (e.g. simple / standard / complex).

    The first tier in a `CostRouterConfig.tiers` tuple is the **floor**: it
    catches everything no higher tier claims, and its keyword set + min-token
    threshold are ignored (a tier can't escalate to itself). Subsequent tiers
    are escalation steps: a prompt routes to the **highest** tier whose
    `complexity_keywords` fire on the prompt OR whose `min_input_tokens`
    threshold is met.

    `endpoint` is OpenAI-compatible (e.g. `http://127.0.0.1:8080/v1` for the
    local Spark lane, `https://openrouter.ai/api/v1` for OpenRouter); `model`
    is the lane-native model id ('Qwen3-30B-A3B-Q4_K_M.gguf' /
    'openai/gpt-4o-mini' / 'anthropic/claude-opus-4.1'). `api_key_env` names
    the env var holding the bearer token (None for local).

    `price_per_m_input_usd` / `price_per_m_output_usd` are informational —
    they feed `CostRouterConfig.estimated_cost_usd` for the per-prompt $
    accounting the H6 article reports. Defaults of 0.0 are correct for the
    local lane; OpenRouter tiers should set them from a snapshot per R7
    (see `articles/hermes-cost-routing-local-and-openrouter/evidence/
    openrouter_prices.json` for the precedent).
    """

    name: str
    endpoint: str
    model: str
    complexity_keywords: tuple[str, ...] = ()
    min_input_tokens: int | None = None
    price_per_m_input_usd: float = 0.0
    price_per_m_output_usd: float = 0.0
    api_key_env: str | None = None
    notes: str = ""


@dataclass(frozen=True)
class CostRouterConfig:
    """A frozen N-tier cost router (typically 3-tier: simple/standard/complex).

    `tiers` is ordered low-cost → high-cost. The first tier is the **floor**
    (the local Spark lane in the standard 3-tier shape); subsequent tiers are
    escalation steps with deterministic predicates.

    `.classify(prompt)` walks the tiers from highest to lowest and returns
    the first tier whose `complexity_keywords` fire OR whose
    `min_input_tokens` threshold the prompt's estimated input length meets.
    Falls through to the floor tier (`tiers[0]`) if nothing escalates.
    `.estimated_cost_usd(prompt_toks, completion_toks, tier)` is the per-call
    $ accounting used by the H6 measurement. `.render_yaml()` emits a
    `router.yaml` block for the published `harness` artifact.

    Deterministic, no I/O, no runtime LLM classifier — the auditable core of
    the H6 router (spec §4.6)."""

    tiers: tuple[RouteTier, ...]

    def classify(
        self,
        prompt: str,
        *,
        est_input_tokens: int | None = None,
    ) -> RouteTier:
        """Pick the cheapest tier whose predicate the prompt clears.

        Walks `tiers` from highest-index (most expensive) to lowest; returns
        the first tier whose `complexity_keywords` substring-match the
        lowercased prompt OR whose `min_input_tokens` threshold is met by
        `est_input_tokens` (falls back to `estimate_tokens(prompt)` when
        not given). The floor tier (`tiers[0]`) is the fallback — its
        predicates are *not* evaluated as escalation triggers (a tier can't
        escalate to itself; the floor is the no-trigger answer).

        Pure function — no I/O, no API call. Same shape as
        `RouterConfig.classify`; reads like a different question."""
        if not self.tiers:
            raise RoutingError("CostRouterConfig has no tiers.")
        text = prompt.lower()
        n_tokens = est_input_tokens if est_input_tokens is not None else estimate_tokens(prompt)
        floor = self.tiers[0]
        # Walk highest-cost → lowest-cost (skip floor); first fire wins.
        for tier in reversed(self.tiers):
            if tier is floor:
                continue
            kw_hit = any(kw.lower() in text for kw in tier.complexity_keywords)
            token_hit = (
                tier.min_input_tokens is not None
                and n_tokens >= tier.min_input_tokens
            )
            if kw_hit or token_hit:
                return tier
        return floor

    def route_for(self, prompt: str, **kw: Any) -> RouteTier:
        """Alias for `classify` that reads better at call sites
        (`tier = config.route_for(prompt)`)."""
        return self.classify(prompt, **kw)

    def tier_by_name(self, name: str) -> RouteTier:
        """Look up a tier by `name` (e.g. for snapshot-price reconciliation)."""
        for t in self.tiers:
            if t.name == name:
                return t
        names = ", ".join(t.name for t in self.tiers)
        raise RoutingError(f"unknown tier {name!r}; have: {names}")

    @staticmethod
    def estimated_cost_usd(
        prompt_tokens: int,
        completion_tokens: int,
        tier: RouteTier,
    ) -> float:
        """Per-call USD cost from token counts × the tier's snapshot prices.

        The headline number the H6 article reports per strategy. Local tier
        returns 0.0 (prices are 0.0). Static method — pure arithmetic, no
        rounding (rounding happens at report time)."""
        return (
            prompt_tokens * tier.price_per_m_input_usd / 1_000_000.0
            + completion_tokens * tier.price_per_m_output_usd / 1_000_000.0
        )

    def render_yaml(self) -> str:
        """Render the cost router as a `router.yaml` block — diff-stable.

        Embedded in `HarnessProfile.router_yaml` so the published `harness`
        artifact carries the routing table + snapshot prices in one place
        (R7 — make the dollar curve reproducible by snapshot, not by live
        re-query)."""
        from fieldkit.publish import _render_yaml_block

        def _tier_dict(t: RouteTier) -> dict[str, Any]:
            d: dict[str, Any] = {
                "name": t.name,
                "endpoint": t.endpoint,
                "model": t.model,
            }
            if t.complexity_keywords:
                d["complexity_keywords"] = list(t.complexity_keywords)
            if t.min_input_tokens is not None:
                d["min_input_tokens"] = t.min_input_tokens
            if t.price_per_m_input_usd or t.price_per_m_output_usd:
                d["price_per_m_input_usd"] = t.price_per_m_input_usd
                d["price_per_m_output_usd"] = t.price_per_m_output_usd
            if t.api_key_env:
                d["api_key_env"] = t.api_key_env
            if t.notes:
                d["notes"] = t.notes
            return d

        data: dict[str, Any] = {
            "router": {
                "kind": "cost",
                "tiers": [_tier_dict(t) for t in self.tiers],
            }
        }
        return "\n".join(_render_yaml_block(data)) + "\n"


def build_cost_router(tiers: Sequence[RouteTier]) -> CostRouterConfig:
    """Construct a `CostRouterConfig` from an ordered tier sequence (cheap → frontier).

    Lightweight validation (raises `RoutingError`):
    - `tiers` non-empty
    - all tier names unique
    - prices monotonically non-decreasing across the sequence (a tier later in
      the sequence shouldn't cost less than an earlier one — that's almost
      certainly a config bug, not an editorial choice). Equal prices are fine
      (the local floor at 0.0 + a second-floor at 0.0 is conceivable).
    - escalation tiers (`tiers[1:]`) must have at least one trigger —
      either `complexity_keywords` non-empty OR `min_input_tokens is not None`.
      An escalation tier with neither could never fire (same reasoning as
      `build_vertical_router`'s "no-keyword" check).

    Returns a frozen `CostRouterConfig`. Pure function — no I/O."""
    if not tiers:
        raise RoutingError("build_cost_router: `tiers` must be non-empty.")
    seen: set[str] = set()
    prev_total = -1.0
    for i, t in enumerate(tiers):
        if not t.name:
            raise RoutingError("build_cost_router: tier name must be non-empty.")
        if t.name in seen:
            raise RoutingError(f"build_cost_router: duplicate tier name {t.name!r}.")
        seen.add(t.name)
        total = t.price_per_m_input_usd + t.price_per_m_output_usd
        if total < prev_total:
            raise RoutingError(
                f"build_cost_router: tier {t.name!r} (combined "
                f"${total:.3f}/M) is cheaper than the previous tier (combined "
                f"${prev_total:.3f}/M). Order `tiers` cheapest → most expensive."
            )
        prev_total = total
        # The floor tier (index 0) is allowed to have no triggers — it's the
        # fallback. Escalation tiers need at least one.
        if i > 0 and not t.complexity_keywords and t.min_input_tokens is None:
            raise RoutingError(
                f"build_cost_router: escalation tier {t.name!r} has no triggers — "
                "set `complexity_keywords` or `min_input_tokens` (a tier with "
                "neither could never fire)."
            )
    return CostRouterConfig(tiers=tuple(tiers))


# --- Eval: Hermes session trace -> AgentRun -> tool-call reliability -------
#
# Hermes persists every agent run in its SQLite session store
# (`~/.hermes/state.db`); `hermes sessions export <out.jsonl>` is the structured
# trace surface (one JSON record per session, each with a `messages` array of
# per-turn role / finish_reason / tool_calls / tool_name). This is the H2
# eval input — ~90% of the work is reuse of `fieldkit.eval.AgentRun`.

# finish_reason values that mean the assistant stopped cleanly (vs. mid-loop
# or truncated). Hermes/OpenAI emit "stop"; other providers vary.
_FINISHED_REASONS = ("stop", "end_turn", "completed", "eos")


def export_hermes_sessions(
    out_path: str | Path,
    *,
    source: str | None = None,
    session_id: str | None = None,
    hermes_bin: str = "hermes",
    timeout: float = 120.0,
) -> Path:
    """Shell `hermes sessions export` to a JSONL file; return its path.

    `source` filters by session source (e.g. `"cli"`); `session_id` exports one
    session. Raises `HarnessError` on a non-zero exit. The resulting JSONL is
    the input to `agent_runs_from_hermes_sessions`."""
    cmd = [hermes_bin, "sessions", "export", str(out_path)]
    if source:
        cmd += ["--source", source]
    if session_id:
        cmd += ["--session-id", session_id]
    proc = subprocess.run(
        cmd, stdin=subprocess.DEVNULL, capture_output=True, text=True,
        check=False, timeout=timeout,
    )
    if proc.returncode != 0:
        raise HarnessError(
            f"`hermes sessions export` failed (exit {proc.returncode}): "
            f"{(proc.stderr or proc.stdout).strip()[-300:]}"
        )
    return Path(out_path)


def _load_session_records(source: str | Path | Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    """Accept a JSONL path/str or an iterable of session-record dicts."""
    if isinstance(source, (str, Path)):
        recs: list[dict[str, Any]] = []
        with open(source) as f:
            for line in f:
                s = line.strip()
                if not s:
                    continue
                try:
                    r = json.loads(s)
                except json.JSONDecodeError:
                    continue
                if isinstance(r, dict):
                    recs.append(r)
        return recs
    return [r for r in source if isinstance(r, dict)]


def _parse_tool_calls(raw: Any) -> list[Any]:
    """Coerce a message's `tool_calls` field (JSON string, list, or None) to a
    list. Returns `[]` for null / empty / unparseable — the empty case on a
    `finish_reason == "tool_calls"` message is the format-error signal."""
    if not raw:
        return []
    if isinstance(raw, list):
        return raw
    if isinstance(raw, str):
        try:
            v = json.loads(raw)
        except json.JSONDecodeError:
            return []
        return v if isinstance(v, list) else []
    return []


def agent_runs_from_hermes_sessions(
    source: str | Path | Sequence[dict[str, Any]],
    *,
    finished_reasons: Sequence[str] = _FINISHED_REASONS,
) -> list[Any]:
    """Parse a `hermes sessions export` JSONL (or session-record dicts) into a
    list of `fieldkit.eval.AgentRun`.

    Each Hermes session becomes one `AgentRun`. Per assistant message:

    - a well-formed `tool_calls` entry → one `action="tool"` turn (so
      `AgentRun.tool_calls()` totals the individual calls, matching the
      session's `tool_call_count`);
    - `finish_reason == "tool_calls"` with no parseable call → one
      `action="error"` turn — the **malformed-call** failure
      `tool_call_reliability` measures (`AgentRun.tool_format_errors()`);
    - otherwise → one `action="synthesis"` turn (the final answer).

    `status` is `"finished"` iff the last assistant message stopped in
    `finished_reasons`, else the session `end_reason` / `"unfinished"`.
    `wall_seconds` is derived from message timestamps — Hermes's `ended_at` is
    unreliable for one-shot runs (it can read as a different clock)."""
    from fieldkit.eval import AgentRun, TurnDetail

    runs: list[Any] = []
    for rec in _load_session_records(source):
        msgs = rec.get("messages") or []
        turns: list[Any] = []
        tn = 0
        last_assistant_fr: str | None = None
        timestamps = [
            float(m["timestamp"]) for m in msgs
            if isinstance(m, dict) and isinstance(m.get("timestamp"), (int, float))
        ]
        for m in msgs:
            if not isinstance(m, dict) or m.get("role") != "assistant":
                continue
            fr = m.get("finish_reason")
            last_assistant_fr = fr
            tok = m.get("token_count")
            out_tok = int(tok) if isinstance(tok, (int, float)) else None
            calls = _parse_tool_calls(m.get("tool_calls"))
            if calls:
                for c in calls:
                    tn += 1
                    name = ""
                    if isinstance(c, dict):
                        name = (c.get("function") or {}).get("name") or c.get("name") or ""
                    turns.append(TurnDetail(
                        turn=tn, action="tool", duration_s=0.0,
                        extras={"tool_name": name},
                    ))
            elif fr == "tool_calls":
                tn += 1
                turns.append(TurnDetail(
                    turn=tn, action="error", duration_s=0.0,
                    extras={"reason": "empty_or_unparseable_tool_calls"},
                ))
            else:
                tn += 1
                turns.append(TurnDetail(
                    turn=tn, action="synthesis", duration_s=0.0,
                    output_tokens=out_tok,
                ))
        finished = last_assistant_fr in tuple(finished_reasons)
        status = "finished" if finished else (str(rec.get("end_reason") or "") or "unfinished")
        wall = (max(timestamps) - min(timestamps)) if len(timestamps) >= 2 else 0.0
        runs.append(AgentRun(
            question_id=str(rec.get("id") or rec.get("title") or ""),
            status=status,
            wall_seconds=round(float(wall), 2),
            n_turns=len(turns),
            n_candidates=1 if finished else 0,
            turns=turns,
            raw=rec,
        ))
    return runs


def tool_call_reliability(runs: Sequence[Any]) -> dict[str, Any]:
    """Reduce `AgentRun`s to the agent-critical tool-call reliability metrics.

    The headline feasibility number of a harness (spec F3): a lane that can't
    do reliable tool calls is useless regardless of speed. Returns:

    - `tool_calls` — total well-formed tool calls across runs;
    - `tool_format_errors` — total malformed tool-call attempts;
    - `format_error_rate` — errors / (calls + errors), the fraction of tool-call
      *attempts* that were malformed;
    - `clean_run_rate` — fraction of runs with zero format errors;
    - plus `n_runs`, `finished_rate`, `tool_calls_per_run`.
    """
    n = len(runs)
    calls = sum(r.tool_calls() for r in runs)
    errs = sum(r.tool_format_errors() for r in runs)
    attempts = calls + errs
    clean = sum(1 for r in runs if r.tool_format_errors() == 0)
    finished = sum(1 for r in runs if r.status == "finished")
    return {
        "n_runs": n,
        "tool_calls": calls,
        "tool_format_errors": errs,
        "format_error_rate": round(errs / attempts, 4) if attempts else 0.0,
        "clean_run_rate": round(clean / n, 4) if n else 0.0,
        "finished_rate": round(finished / n, 4) if n else 0.0,
        "tool_calls_per_run": round(calls / n, 2) if n else 0.0,
    }


@dataclass(frozen=True)
class HarnessEvalResult:
    """Per-lane agent-eval rollup: tool-call reliability + agent-run summary.

    Composes `fieldkit.eval.summarize_agent_runs` (status / wall / turns / token
    rollups) with `tool_call_reliability` (the 4 agent-critical metrics).
    `.report()` renders a markdown block for the harness card + H2 article;
    mirrors `eval.GradeResult` as the harness analog of a graded result."""

    label: str
    reliability: dict[str, Any]
    summary: dict[str, Any]

    @classmethod
    def from_runs(cls, runs: Sequence[Any], *, label: str = "") -> HarnessEvalResult:
        from fieldkit.eval import summarize_agent_runs

        return cls(
            label=label,
            reliability=tool_call_reliability(runs),
            summary=summarize_agent_runs(runs, label=label),
        )

    @classmethod
    def from_hermes_sessions(
        cls,
        source: str | Path | Sequence[dict[str, Any]],
        *,
        label: str = "",
        finished_reasons: Sequence[str] = _FINISHED_REASONS,
    ) -> HarnessEvalResult:
        runs = agent_runs_from_hermes_sessions(source, finished_reasons=finished_reasons)
        return cls.from_runs(runs, label=label)

    @property
    def format_error_rate(self) -> float:
        return float(self.reliability.get("format_error_rate", 0.0))

    @property
    def clean_run_rate(self) -> float:
        return float(self.reliability.get("clean_run_rate", 0.0))

    def report(self) -> str:
        r = self.reliability
        lines = [f"# harness eval — {self.label or 'lane'}", ""]
        lines.append(f"- runs: {r.get('n_runs', 0)}")
        lines.append(
            f"- tool calls: {r.get('tool_calls', 0)} ({r.get('tool_calls_per_run', 0)}/run)"
        )
        lines.append(f"- tool format errors: {r.get('tool_format_errors', 0)}")
        lines.append(f"- format-error rate: {100 * self.format_error_rate:.1f}%")
        lines.append(f"- clean-run rate: {100 * self.clean_run_rate:.1f}%")
        lines.append(f"- finished rate: {100 * float(r.get('finished_rate', 0.0)):.1f}%")
        wall = self.summary.get("wall_seconds")
        if isinstance(wall, dict) and wall.get("mean") is not None:
            lines.append(f"- wall/run: mean {wall['mean']}s (n={wall.get('n', 0)})")
        return "\n".join(lines)


# --- Profile / publish: the `harness` artifact -----------------------------


@dataclass(frozen=True)
class LaneMetricColumns:
    """Custom last-two-columns + caption for `HarnessProfile.render()` lanes table.

    The default (None on `HarnessProfile.lane_metrics`) keeps the H2/H4 tool-call
    reliability shape: `format_error_rate` + `clean_run_rate`, both rendered as
    percentages, with the agent-critical caption. The H5 vertical router and
    H6 cost router swap in their own column pairs — pass-rate + warm-time, or
    $/M input + $/M output — without forking the renderer.

    `format_a` / `format_b` are one of `"percent"` (multiply by 100, suffix `%`,
    1 decimal), `"money"` (prefix `$`, 2 decimals, `/M` suffix), or `"raw"`
    (call `str()`). `key_a` / `key_b` are the lane-dict keys the renderer
    reads. `caption` replaces the default "tool-call format-error rate is
    agent-critical" line — leave empty to suppress the caption entirely.

    Added at H6 to retire the v0.12.1 polish item flagged in the H5 publish
    (template assumed tool-call metrics on every `kind: harness` artifact)."""

    label_a: str
    label_b: str
    key_a: str
    key_b: str
    format_a: str = "percent"
    format_b: str = "percent"
    caption: str = ""


# Sentinel for the default tool-call reliability columns — keeps the H2/H4
# shape working when `HarnessProfile.lane_metrics` is None.
_DEFAULT_LANE_METRICS = LaneMetricColumns(
    label_a="Format-error",
    label_b="Clean-run",
    key_a="format_error_rate",
    key_b="clean_run_rate",
    format_a="percent",
    format_b="percent",
    caption=(
        "Tool-call **format-error rate** is the agent-critical number: a lane "
        "that can't emit well-formed tool calls is disqualified regardless of "
        "speed."
    ),
)


def _format_lane_metric(value: Any, fmt: str) -> str:
    """Format one lane-table cell value per `LaneMetricColumns.format_*`.

    `"percent"` — `value × 100`, 1 decimal, `%` suffix (`format_error_rate`,
    `clean_run_rate`, vertical `pass_rate`).
    `"money"` — `$value`, 2 decimals, `/M` suffix (cost-router $/M columns).
    `"raw"` — `str(value)` (warm-seconds, finish-rate, anything else)."""
    if value is None:
        return "—"
    if not isinstance(value, (int, float)):
        return str(value)
    if fmt == "percent":
        return f"{100 * float(value):.1f}%"
    if fmt == "money":
        return f"${float(value):.2f}/M"
    return f"{value:g}" if isinstance(value, float) else str(value)


@dataclass(frozen=True)
class HarnessProfile:
    """A reproducible Spark-Hermes profile bundle — the `harness` artifact.

    The analog of `publish.ModelCard` for a harness: positioning + serving-lane
    recipe + measured tok/s + tool-call reliability + embedded config files.
    `.render()` emits the README; `.files()` returns the `(rel_path, text)`
    pairs the HF push stages (README + `hermes.yaml` + `.env.example` +
    optional `router.yaml`); `.to_manifest()` builds the
    `ArtifactManifest(kind="harness")` the Astro catalog renders. Deterministic
    and diff-stable — mirrors `ModelCard.render()`.

    `lanes` is a tuple of per-lane rows, each a dict with at least `name` and
    `provider`; optional `model`, `tokens_per_sec`, `sustained_load_minutes`,
    `format_error_rate`, `clean_run_rate`, `footprint_gb`, `recommended`,
    `note`. `perplexity`/`vertical_eval` are N/A to a harness (omitted)."""

    title: str
    one_liner: str
    harness: str = "Hermes Agent"
    harness_version: str = ""
    license: str = "mit"
    positioning: dict[str, Any] | None = None
    lanes: tuple[dict[str, Any], ...] = ()
    lane_metrics: LaneMetricColumns | None = None
    hermes_config: HermesConfig | None = None
    env_example: EnvFile | None = None
    router_yaml: str | None = None
    doctor_checklist: tuple[str, ...] = ()
    known_drift: tuple[dict[str, str], ...] = ()
    tags: tuple[str, ...] = ()
    article_slug: str | None = None
    article_title: str | None = None
    hf_repo: str | None = None
    model_creator: str = "Orionfold LLC"

    # -- rendering --
    def _frontmatter(self) -> dict[str, Any]:
        # Dedupe while preserving order — caller-supplied `tags` may overlap with
        # the four built-ins, which used to ship as duplicates (v0.12.1 polish
        # item flagged in the H5 publish).
        tags = list(dict.fromkeys(
            ("agent-harness", "hermes", "dgx-spark", "orionfold", *self.tags)
        ))
        fm: dict[str, Any] = {
            "license": self.license,
            "library_name": "hermes-agent",
            "tags": tags,
        }
        return fm

    def _lane_value(self, lane: dict[str, Any], key: str, default: str = "—") -> str:
        v = lane.get(key)
        if v is None:
            return default
        if isinstance(v, float):
            return f"{v:g}"
        return str(v)

    def render(self) -> str:
        from fieldkit.publish import _render_yaml_block

        yaml_lines = ["---", *_render_yaml_block(self._frontmatter()), "---", ""]
        L: list[str] = []
        L.append(f"# {self.title}")
        L.append("")
        L.append(self.one_liner)
        L.append("")

        if self.positioning:
            p = self.positioning
            L.append("## What this harness is")
            L.append("")
            if p.get("headline"):
                L.append(f"**{p['headline']}**")
                L.append("")
            if p.get("problem"):
                L.append(str(p["problem"]))
                L.append("")
            if p.get("use_cases"):
                L.append("Good for:")
                L.append("")
                for uc in p["use_cases"]:
                    L.append(f"- {uc}")
                L.append("")
            if p.get("audience"):
                L.append(f"_For: {p['audience']}_")
                L.append("")

        # Serving lanes table — the measured core. The last two columns + the
        # caption swap via `lane_metrics` so a vertical-router or cost-router
        # card doesn't ship a tool-call caption it has no business making.
        if self.lanes:
            metrics = self.lane_metrics or _DEFAULT_LANE_METRICS
            L.append("## Serving lanes")
            L.append("")
            L.append(
                f"| Lane | Provider | Model | tok/s | Sustained (min) "
                f"| {metrics.label_a} | {metrics.label_b} |"
            )
            L.append("|---|---|---|---|---|---|---|")
            for lane in self.lanes:
                star = " ⭐" if lane.get("recommended") else ""
                cell_a = _format_lane_metric(lane.get(metrics.key_a), metrics.format_a)
                cell_b = _format_lane_metric(lane.get(metrics.key_b), metrics.format_b)
                L.append(
                    f"| {self._lane_value(lane, 'name')}{star} "
                    f"| {self._lane_value(lane, 'provider')} "
                    f"| {self._lane_value(lane, 'model')} "
                    f"| {self._lane_value(lane, 'tokens_per_sec')} "
                    f"| {self._lane_value(lane, 'sustained_load_minutes')} "
                    f"| {cell_a} | {cell_b} |"
                )
            L.append("")
            if metrics.caption:
                L.append(metrics.caption)
                L.append("")

        # Embedded config.
        if self.hermes_config is not None:
            L.append("## Configuration")
            L.append("")
            L.append("`~/.hermes/config.yaml` (model block):")
            L.append("")
            L.append("```yaml")
            L.append(self.hermes_config.render())
            L.append("```")
            L.append("")
        if self.env_example is not None:
            L.append("`~/.hermes/.env`:")
            L.append("")
            L.append("```ini")
            L.append(self.env_example.render())
            L.append("```")
            L.append("")
        if self.router_yaml:
            L.append("`router.yaml`:")
            L.append("")
            L.append("```yaml")
            L.append(self.router_yaml.rstrip())
            L.append("```")
            L.append("")

        if self.doctor_checklist:
            L.append("## Doctor checklist")
            L.append("")
            for item in self.doctor_checklist:
                L.append(f"- [ ] {item}")
            L.append("")

        if self.article_slug:
            L.append("## Methods")
            L.append("")
            title = self.article_title or self.article_slug
            L.append(
                f"Measured and documented in [{title}]"
                f"(https://ainative.business/field-notes/{self.article_slug}/)."
            )
            L.append("")

        if self.known_drift:
            L.append("## Known drift")
            L.append("")
            for entry in self.known_drift:
                item = str(entry.get("item", "")).strip()
                bound = str(entry.get("bound", "")).strip()
                if not item:
                    continue
                L.append(f"- **{item}**" + (f" — {bound}" if bound else ""))
            L.append("")

        L.append("---")
        L.append("")
        L.append(
            f"Published by **{self.model_creator}** · [orionfold.com](https://orionfold.com)"
            " · Methods documented at [ainative.business/field-notes]"
            "(https://ainative.business/field-notes/)."
        )
        L.append("")
        return "\n".join(yaml_lines) + "\n".join(L) + "\n"

    def files(self) -> list[tuple[str, str]]:
        """`(rel_path, text)` pairs to stage for the HF push."""
        out: list[tuple[str, str]] = [("README.md", self.render())]
        if self.hermes_config is not None:
            out.append(("hermes.yaml", self.hermes_config.render() + "\n"))
        if self.env_example is not None:
            out.append((".env.example", self.env_example.render() + "\n"))
        if self.router_yaml:
            out.append(("router.yaml", self.router_yaml.rstrip() + "\n"))
        return out

    def to_manifest(self, *, slug: str, hf_repo: str) -> Any:
        """Build the `ArtifactManifest(kind="harness")` for the Astro catalog."""
        from fieldkit.publish import ArtifactManifest

        base = self.harness + (f" {self.harness_version}" if self.harness_version else "")
        tps = {
            lane["name"]: float(lane["tokens_per_sec"])
            for lane in self.lanes
            if lane.get("name") and isinstance(lane.get("tokens_per_sec"), (int, float))
        }
        sustained_vals = [
            float(lane["sustained_load_minutes"])
            for lane in self.lanes
            if isinstance(lane.get("sustained_load_minutes"), (int, float))
        ]
        recommended = next(
            (lane["name"] for lane in self.lanes if lane.get("recommended") and lane.get("name")),
            None,
        )
        # Astro/destination's strict regex on `article:` requires the
        # path-shape `articles/<slug>/` (Mac fix 14360e5). Render it
        # path-shape directly here; this retires the post-write fixup the
        # H5 publisher script carried (v0.12.1 polish item #1).
        article_path = (
            f"articles/{self.article_slug}/" if self.article_slug else None
        )
        return ArtifactManifest(
            slug=slug,
            kind="harness",
            artifact_class="agent-harness",
            base_model=base,
            hf_repo=hf_repo,
            variants=tuple(lane["name"] for lane in self.lanes if lane.get("name")),
            spark_tokens_per_sec=tps,
            sustained_load_minutes=max(sustained_vals) if sustained_vals else None,
            recommended_variant=recommended,
            model_license=self.license,
            known_drift=self.known_drift,
            positioning=self.positioning,
            article=article_path,
        )


def publish_harness(
    *,
    profile: HarnessProfile,
    repo_name: str,
    staging_dir: str | Path,
    slug: str | None = None,
    artifacts_dir: str | Path | None = None,
    dry_run: bool = True,
    token: str | None = None,
    org: str | None = None,
    commit_message: str = "Orionfold Spark-Hermes harness profile",
) -> Any:
    """Orchestrate the `harness` artifact push — render → stage → manifest → push.

    Thinner than `publish.publish_quant` (no quant variants / lineage): stages
    `profile.files()` into `staging_dir`, optionally writes the
    `ArtifactManifest(kind="harness")` to `artifacts_dir` (the Astro content
    dir), and pushes the folder via the existing `HFHubAdapter` (dry-run by
    default). Returns the `publish.PublishResult`.
    """
    from fieldkit.publish import (
        HFHubAdapter,
        ORIONFOLD_HF_HANDLE,
        write_artifact_manifest,
    )

    if org is None:
        org = ORIONFOLD_HF_HANDLE
    adapter = HFHubAdapter(staging_dir=staging_dir, dry_run=dry_run, token=token, org=org)
    hf_repo = adapter.repo_id(repo_name)
    if slug is None:
        slug = repo_name.split("/")[-1].lower()

    for rel, text in profile.files():
        adapter.stage_text(text, rel)

    manifest_path = None
    if artifacts_dir is not None:
        manifest = profile.to_manifest(slug=slug, hf_repo=hf_repo)
        manifest_path = write_artifact_manifest(manifest, artifacts_dir=artifacts_dir)

    result = adapter.push_folder(
        repo_name=repo_name, commit_message=commit_message, repo_type="model",
    )
    result.manifest_path = manifest_path
    return result


# --- Hermes brain-quality evaluator (Step 3) -------------------------------
# Eager re-export from `.brains` — the submodule is stdlib-only at top level,
# and the brain primitives are the canonical surface; lazy import would only
# matter for an optional extra (cf. `.mcp` below).
from fieldkit.harness.brains import (  # noqa: E402
    BrainAttempt,
    BrainCandidate,
    BrainPromptScore,
    BrainScorecard,
    Telemetry,
    bucket_hermes_sessions,
    evaluate_brain,
    evaluate_brains,
    measure_throughput,
    point_hermes_at_endpoint,
)


# --- fieldkit-as-MCP (H4) --------------------------------------------------
# Lazily re-exported from the `.mcp` submodule via PEP 562 `__getattr__`. Keeping
# this lazy (rather than a top-level `from .mcp import ...`) means `import
# fieldkit.harness` never touches the submodule, and `python -m
# fieldkit.harness.mcp` doesn't double-import it (no runpy RuntimeWarning). The
# submodule top level is stdlib-only anyway — only `build_mcp_server` imports the
# optional `mcp` SDK, and only when called.
_MCP_EXPORTS = frozenset(
    {
        "MCP_SERVER_NAME",
        "MCP_TOOL_SPECS",
        "MCPToolSpec",
        "McpNotAvailable",
        "build_mcp_server",
        "run_mcp_server",
    }
)


def __getattr__(name: str) -> Any:  # PEP 562 module-level lazy attribute
    if name in _MCP_EXPORTS:
        from . import mcp as _mcp

        return getattr(_mcp, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
