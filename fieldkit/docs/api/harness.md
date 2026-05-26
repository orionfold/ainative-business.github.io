---
module: harness
title: fieldkit.harness
summary: Deterministic Python spine for the Harnesses content line — install / configure / serve / harden / route / eval / profile an agent harness (Hermes Agent first) on the DGX Spark. H1 ships install + doctor + configure + the NIM / llama-server serving lanes + the serve_lane unified-memory guard; harden / route / eval / profile land across H2–H6. See specs/hermes-harness-v1.md.
order: 12
---

## What it is

The artifact arc taught the project to publish a *thing you download and run*. A harness is the **cockpit** — what a Spark power-user actually drives the box from. `fieldkit.harness` is the deterministic Python spine of the **Harnesses** content line: take a frontier open-source agent harness (Hermes Agent — Nous Research, MIT — is entry #1), install it, point it at a Spark-right-sized serving lane, harden it, and wire it to the box itself via fieldkit-as-MCP.

Per `feedback_llm_skill_pattern` the module is **deterministic Python only**: it renders configs, sizes serving lanes against the unified-memory envelope, and reduces eval JSONL — all the LLM generation (skill bodies, agent task runs, prose) stays in session-driven skills. The full design is in `specs/hermes-harness-v1.md`.

> **Status: H1 shipped.** Install + doctor + configure + the NIM / llama-server serving lanes + the `serve_lane` guard are live and verified on the Spark (Hermes v0.14.0 driving the cached `nemotron-nano-9b-v2-dgx-spark` NIM with reliable tool calls, no API key). The harden / route / eval / profile surfaces land across H2–H6.

## Public API (today)

```python
from fieldkit.harness import (
    # errors
    HarnessError, ServingLaneError, UnifiedMemoryExceeded,
    HermesNotInstalled, DoctorFailed,
    # serve
    LaneSpec, ServingLane, NIMLane, LlamaServerLane,
    resolve_lane, serve_lane, SERVING_LANES,
    # install / doctor
    HERMES_INSTALL_URL, install_hermes, hermes_doctor, DoctorCheck, DoctorReport,
    # configure
    HermesConfig, EnvFile, configure_hermes,
)
```

### Errors

| Exception | Raised when |
|---|---|
| `HarnessError` | Base for every error the module raises — catch this to catch them all. |
| `ServingLaneError` | A serving lane fails to start, warm, or tear down cleanly. Subclass of `HarnessError`. |
| `UnifiedMemoryExceeded` | The `serve_lane` guard refuses a lane whose estimated footprint plus headroom would exceed available unified memory — the OOM-stacking landmine from `project_spark_unified_memory_oom`. Subclass of `ServingLaneError`; the guard errs toward refusing. |
| `HermesNotInstalled` | `hermes_doctor` can't find the `hermes` CLI on PATH (or at the given binary path). |
| `DoctorFailed` | Raise this yourself when you want hard-fail semantics on a failing required `hermes doctor` check (`hermes_doctor` itself never raises it — inspect `report.ok`). |

### Serving lanes

A serving lane wraps one single-model endpoint's lifecycle so the harness can bring it up, point at it, and tear it down — one model at a time.

#### `LaneSpec`

A frozen, hashable description of one lane — the minimal contract every `ServingLane` is built from.

```python
spec = LaneSpec(provider="nim", model="nemotron-nano-9b-v2-dgx-spark", port=8000)
spec.base_url   # "http://127.0.0.1:8000/v1"  — the OpenAI-compatible endpoint
```

`provider` selects the concrete lane (`"nim"` / `"llama-server"`; `"vllm"` / `"ollama"` arrive in H2); `model` is the lane-native id (a NIM image short-name or served id, an Ollama tag, or an HF GGUF repo). `extra` is a free-form escape hatch for lane-specific knobs so new options never force a dataclass change — it mirrors the `HermesConfig.extra` / `ModelCard.extra_yaml` pattern.

#### `ServingLane`

Abstract base fixing the lifecycle contract `serve_lane` drives: `start()` brings the lane up, `wait_for_warm(timeout=180.0)` blocks until it answers health, `teardown()` stops it, and `weight_bytes()` reports the estimate the unified-memory guard checks. `base_url` proxies through to the spec.

#### `NIMLane`

The H1 hero — a NVIDIA NIM lane started via `docker run -d`, codifying the verified-on-Spark recipe (`reference_nim_local_serving`, `reference_nim_spark_env_vars`): `--network host`, the cache mount, the NGC-key env-file, and `NIM_MAX_BATCH_SIZE=32` (the measured 325 tok/s knob for the hybrid-Mamba Nemotron-Nano-9B-v2). `wait_for_warm` reuses `nim.wait_for_warm`. A bare short-name in `model` is expanded to the full `nvcr.io/nim/nvidia/...` image; pass `footprint_gb` to give the guard the realistic resident size (NIM reserves far more than weights — ~95 GB for the 9B). `docker_run_cmd()` returns the exact argv with no side effects.

#### `LlamaServerLane`

The easy GGUF alternative — **delegates** to `notebook.local_server` (the project's primary GGUF path). `model` is the HF GGUF repo; `extra` may carry `variant` / `gguf_file` / `n_ctx` / `reasoning_format`. The lifecycle bridges `local_server`'s contextmanager.

#### `resolve_lane` / `SERVING_LANES`

`SERVING_LANES` maps each `provider` string to its concrete `ServingLane` subclass (`"nim"` → `NIMLane`, `"llama-server"` → `LlamaServerLane`). `resolve_lane(spec, **kwargs)` looks the constructor up so a caller can build a lane from a bare `LaneSpec` without importing the concrete classes.

#### `serve_lane`

The OOM-safe "one model at a time" contextmanager. Accepts a `ServingLane` or a bare `LaneSpec` (resolved for you). With `guard=True` (default) it refuses to start a lane whose estimated footprint + `headroom_gb` exceeds currently-available unified memory, raising `UnifiedMemoryExceeded` *before* launch. The contextmanager's teardown is the structural guarantee against stacking.

```python
with serve_lane(LaneSpec("nim", "nemotron-nano-9b-v2-dgx-spark"), warm_timeout=240) as lane:
    ...  # NIM live on lane.base_url; torn down on exit
```

### Install / doctor

- **`HERMES_INSTALL_URL`** — the official Hermes install script (`scripts/install.sh`, MIT).
- **`install_hermes(method="script", dry_run=True, allow_pipe_to_bash=False, install_url=HERMES_INSTALL_URL)`** — returns the exact `curl -fsSL <install_url> | bash` command for review by default. Executing it requires **both** `dry_run=False` **and** `allow_pipe_to_bash=True` (two-key safety on piping a remote script to a shell). `install_url` overrides the script source (e.g. to pin a fork/tag).
- **`hermes_doctor(hermes_bin="hermes")`** — runs `hermes doctor` and parses its sectioned output into a `DoctorReport`. Classification is **by section**, not per-line phrase matching (robust to upstream churn): only core sections (Python Environment, Required Packages, Configuration Files, Directory Structure, Command Installation, Security Advisories) gate `report.ok`. Raises `HermesNotInstalled` if the binary is absent; never raises on a failing check.
- **`DoctorCheck`** — one parsed line: `name`, `ok`, `detail`, `required`, `section`.
- **`DoctorReport`** — `checks` + `.ok` (True iff every *required* check passed) + `.n_failed` + `.report()` markdown. Mirrors `eval.GradeResult` — the harness analog of a grade.

### Configure

- **`HermesConfig`** — the `model:` section of `~/.hermes/config.yaml` for one provider. For a local NIM / llama-server the verified shape is `provider="custom"` (Hermes aliases `ollama`/`vllm`/`llamacpp` → `custom`) with an explicit `base_url`. `render()` emits the YAML block (reusing `publish`'s stdlib emitter); `config_set_commands()` emits the equivalent `hermes config set` lines (Hermes owns the heavily-commented, versioned config.yaml, so setting keys beats overwriting it). `extra` absorbs new Hermes YAML keys without a fieldkit release.
- **`EnvFile`** — a `~/.hermes/.env` rendering (`KEY=VALUE`, sorted, stable). Values here take precedence over config.yaml.
- **`configure_hermes(lane=None, base_url=None, model=None, api_key="local", slow_serving=True)`** — builds the `(HermesConfig, EnvFile)` pair to point Hermes at a local lane, no side effects. Endpoint resolution mirrors `notebook.open_model`: explicit `base_url` wins, else `lane.base_url`, else autodiscover via `notebook.discover_local_server`. `slow_serving=True` sets `HERMES_STREAM_READ_TIMEOUT=1800` for long local cold generations.

## Coming across the arc

| Surface | Article | Reuse |
|---|---|---|
| `VLLMLane` / `OllamaLane` lanes | H2 | `VLLMLane.teardown` sweeps orphaned EngineCore PIDs (`feedback_vllm_engine_core_orphan`). |
| `HardeningPolicy` / `harden_config` | H3 | Guardrails policy patterns. |
| `tool_call_reliability` / `HarnessEvalResult` | H2 | composes `eval.AgentRun` / `summarize_agent_runs` / `Bench`. |
| `HarnessProfile` → `ArtifactManifest(kind="harness")` | H2 | `publish.HFHubAdapter`, stdlib YAML emitter. |
| `VerticalRoute` / `build_vertical_router`, `RouterConfig` / `build_cost_router` | H5–H6 | the 5 Orionfold GGUFs; OpenRouter overflow. |

## Notes

- **Cheap import.** Heavy/optional integrations (docker, httpx, the sibling fieldkit modules) are lazy — `import fieldkit.harness` imports only the stdlib.
- **Two new artifact kinds.** The arc adds `harness` (a reproducible Spark-Hermes profile bundle) and `skill` (an agentskills.io `SKILL.md` package, cross-compatible with Claude Code skills) to `publish.ARTIFACT_KINDS` — see the spec §4.8.
