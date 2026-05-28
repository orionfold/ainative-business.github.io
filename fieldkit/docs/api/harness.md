---
module: harness
title: fieldkit.harness
summary: Deterministic Python spine for the Harnesses content line — install / configure / serve / harden / route / eval / profile an agent harness (Hermes Agent first) on the DGX Spark. H1 ships install + doctor + configure + the NIM / llama-server lanes + the serve_lane guard; H2 adds the vLLM / Ollama lanes, the Hermes-trace tool-call-reliability eval, and the HarnessProfile artifact. Harden / route land across H3–H6. See specs/hermes-harness-v1.md.
order: 12
---

## What it is

The artifact arc taught the project to publish a *thing you download and run*. A harness is the **cockpit** — what a Spark power-user actually drives the box from. `fieldkit.harness` is the deterministic Python spine of the **Harnesses** content line: take a frontier open-source agent harness (Hermes Agent — Nous Research, MIT — is entry #1), install it, point it at a Spark-right-sized serving lane, harden it, and wire it to the box itself via fieldkit-as-MCP.

Per `feedback_llm_skill_pattern` the module is **deterministic Python only**: it renders configs, sizes serving lanes against the unified-memory envelope, and reduces eval JSONL — all the LLM generation (skill bodies, agent task runs, prose) stays in session-driven skills. The full design is in `specs/hermes-harness-v1.md`.

> **Status: H1 + H2 shipped.** H1: install + doctor + configure + the NIM / llama-server lanes + the `serve_lane` guard, verified on the Spark (Hermes v0.14.0 driving the cached `nemotron-nano-9b-v2-dgx-spark` NIM with reliable tool calls, no API key). H2: the `VLLMLane` (high-throughput MoE lane, with the EngineCore orphan-sweep teardown) + `OllamaLane`; the Hermes session-trace tool-call-reliability eval; and `HarnessProfile` / `publish_harness` (the first `harness` artifact). Harden / route land across H3–H6.

## Public API (today)

```python
from fieldkit.harness import (
    # errors
    HarnessError, ServingLaneError, UnifiedMemoryExceeded,
    HermesNotInstalled, DoctorFailed, HardeningError,
    # serve
    LaneSpec, ServingLane, NIMLane, LlamaServerLane, VLLMLane, OllamaLane,
    resolve_lane, serve_lane, SERVING_LANES,
    # install / doctor
    HERMES_INSTALL_URL, install_hermes, hermes_doctor, DoctorCheck, DoctorReport,
    # configure
    HermesConfig, EnvFile, configure_hermes,
    # harden (H3)
    HardeningPolicy, DEFAULT_HARDENING, harden_config, LOCAL_PROVIDERS,
    # eval (H2)
    export_hermes_sessions, agent_runs_from_hermes_sessions,
    tool_call_reliability, HarnessEvalResult,
    # profile / publish (H2)
    HarnessProfile, publish_harness,
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
| `HardeningError` | `harden_config` refused to produce a hardened config from this input — a cloud provider under `local_first`, an `approvals.mode` of `off`/`--yolo`, or a secret in the config body. Subclass of `HarnessError`; the function errs toward refusing. |

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

#### `VLLMLane`

The high-throughput MoE lane (H2 — e.g. `Qwen/Qwen3-30B-A3B-FP8`). Runs `vllm serve <spec.model>` inside the community DGX-Spark vLLM image (`VLLM_SPARK_IMAGE`, built from `eugr/spark-vllm-docker` — prebuilt, Spark-tested wheels for GB10, no source compile) via `docker run -d`, mounting the shared HF cache so the model resolves by repo id. Constructor knobs: `image`, `hf_cache_dir`, `gpu_memory_utilization` (default 0.7), `load_format`, `max_model_len`, `container_name`, `params_b` / `active_params_b` / `dtype`, `footprint_gb`, `extra_args`, `hf_token_env`, plus `enable_auto_tool_choice` (default **True**) and `tool_call_parser` (default `"hermes"`) — an agent lane is useless without tool calls, and vLLM only emits structured `tool_calls` when served with `--enable-auto-tool-choice` + a model-matched `--tool-call-parser` (Qwen3 / Hermes-style models use `hermes`). `spec.extra` overrides `gpu_memory_utilization` / `load_format` / `max_model_len` / `served_name` / `extra_args` / `enable_auto_tool_choice` / `tool_call_parser`. `docker_run_cmd()` returns the exact argv. **`teardown()` stops + removes the container, then runs `_sweep_engine_core_orphans()`** — the R8 landmine (`feedback_vllm_engine_core_orphan`): a torn-down vLLM can leave an `EngineCore` worker reparented to PID 1 holding ~100 GB of unified memory. Verify `free -h` afterward.

#### `OllamaLane`

The lowest-friction local alternative (H2), matching the NVIDIA official Spark guide's first-turn path. Pass `model` (an Ollama tag like `qwen3:30b-a3b`) and it builds a `:11434` `LaneSpec` for you; or pass a `spec`. `start()` ensures `ollama serve` is up and (with `pull=True`) `ollama pull`s the tag; `teardown()` runs `ollama stop <model>` to unload the weights but leaves the daemon. Other knobs: `params_b` / `dtype` (for the guard estimate), `ollama_bin`.

#### `resolve_lane` / `SERVING_LANES`

`SERVING_LANES` maps each `provider` string to its concrete `ServingLane` subclass (`"nim"` → `NIMLane`, `"llama-server"` → `LlamaServerLane`, `"vllm"` → `VLLMLane`, `"ollama"` → `OllamaLane`). `resolve_lane(spec, **kwargs)` looks the constructor up so a caller can build a lane from a bare `LaneSpec` without importing the concrete classes.

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

- **`HermesConfig`** — the `model:` section of `~/.hermes/config.yaml` for one provider, plus any hardened top-level `sections` (added by `harden_config`). For a local NIM / llama-server the verified shape is `provider="custom"` (Hermes aliases `ollama`/`vllm`/`llamacpp` → `custom`) with an explicit `base_url`. `render()` emits `model:` then each section (insertion order preserved, reusing `publish`'s stdlib emitter); `config_set_commands()` emits the equivalent `hermes config set` lines for `model.*` and every *scalar* leaf in `sections` (list/dict leaves like `terminal.docker_extra_args` are skipped — `hermes config set` can't parse them, so the rendered YAML carries those). `extra` absorbs new Hermes `model:` keys, `sections` carries new top-level sections, neither forcing a fieldkit release.
- **`EnvFile`** — a `~/.hermes/.env` rendering (`KEY=VALUE`, sorted, stable). Values here take precedence over config.yaml.
- **`configure_hermes(lane=None, base_url=None, model=None, api_key="local", slow_serving=True)`** — builds the `(HermesConfig, EnvFile)` pair to point Hermes at a local lane, no side effects. Endpoint resolution mirrors `notebook.open_model`: explicit `base_url` wins, else `lane.base_url`, else autodiscover via `notebook.discover_local_server`. `slow_serving=True` sets `HERMES_STREAM_READ_TIMEOUT=1800` for long local cold generations.

### Harden (H3)

A pure function turns a permissive local `HermesConfig` into a desk-grade one. Hermes ships permissive defaults (terminal backend `local` runs commands straight on the host; tool-loop guardrails warn-only; the agent can run `--yolo`); `harden_config` flips the posture, mapping each policy field to a **real Hermes config key** verified against the installed v0.14.0 schema (`terminal.*`, `tool_loop_guardrails.*`, `approvals.*`, `agent.*`, `session_reset.*`). Conceptual basis: the project's Guardrails-on-the-retrieval-path pattern — a frozen policy + a pure apply function, no hidden side effects.

- **`HardeningPolicy`** — the frozen posture. Fields (defaults are the spec §4.3 baseline): `terminal_backend="docker"` (sandbox, not host `local`), `network_egress="deny"` (adds `--network=none` to `terminal.docker_extra_args`), `secrets_from_env_only=True`, `local_first=True`, `approval_mode="manual"` (`"smart"` allowed; `"off"` refused), `hard_stop_loops=True` (`tool_loop_guardrails.hard_stop_enabled`), `max_turns=30`, `ephemeral_terminal=True` (`container_persistent=false` + mount off), `terminal_lifetime_seconds=300`, `deny_toolsets=()` (`agent.disabled_toolsets`), `auto_restart=True` + `idle_reset_minutes` / `reset_at_hour` (the `session_reset` wiring).
- **`DEFAULT_HARDENING`** — `HardeningPolicy()`, the §4.3 baseline (docker / egress-deny / env-secrets / local-first).
- **`harden_config(config, policy=DEFAULT_HARDENING)`** — returns a **new** frozen `HermesConfig` with the hardened sections folded into `.sections` (the input is unchanged). Raises `HardeningError` rather than emit a falsely-hardened config when: `local_first` and the provider isn't in `LOCAL_PROVIDERS`; `approval_mode == "off"` (that's `--yolo`); or a secret-looking key sits in `extra`/`sections` under `secrets_from_env_only` (secrets belong in `~/.hermes/.env` — Hermes' own `config set` routes `*_API_KEY`/`*_TOKEN` there).
- **`LOCAL_PROVIDERS`** — `("custom", "ollama", "vllm", "llamacpp", "local")`, the providers Hermes serves locally. The native `nvidia` provider is *cloud* Nemotron and is deliberately excluded.

### Eval — tool-call reliability (H2)

The agent-critical feasibility number (spec F3): a lane that can't emit well-formed tool calls is useless regardless of speed. Hermes persists every agent run in its SQLite session store (`~/.hermes/state.db`); the eval reads that trace and reduces it — ~90% reuse of `fieldkit.eval`.

- **`export_hermes_sessions(out_path, source=None, session_id=None, hermes_bin="hermes", timeout=120.0)`** — shells `hermes sessions export` to a JSONL file (one record per session, each with a `messages` array). `source` filters by session source (e.g. `"cli"`); `session_id` exports one session. Returns the path; raises `HarnessError` on non-zero exit.
- **`agent_runs_from_hermes_sessions(source, finished_reasons=...)`** — parses that JSONL (or an iterable of record dicts) into `fieldkit.eval.AgentRun`s. Per assistant message: a well-formed `tool_calls` entry → one `action="tool"` turn; a `finish_reason == "tool_calls"` with no parseable call → one `action="error"` turn (the malformed-call failure); otherwise a `synthesis` turn. `wall_seconds` is derived from message timestamps (Hermes's `ended_at` is unreliable for one-shot runs, so the bakeoff times each call externally).
- **`tool_call_reliability(runs)`** — reduces `AgentRun`s to `{n_runs, tool_calls, tool_format_errors, format_error_rate, clean_run_rate, finished_rate, tool_calls_per_run}`. `format_error_rate` = errors / (calls + errors); `clean_run_rate` = fraction of runs with zero format errors.
- **`HarnessEvalResult`** — a frozen `(label, reliability, summary)` rollup composing `tool_call_reliability` with `eval.summarize_agent_runs`. Build via `HarnessEvalResult.from_runs(runs, label=...)` or `HarnessEvalResult.from_hermes_sessions(source, label=..., finished_reasons=...)`; `.format_error_rate` / `.clean_run_rate` properties; `.report()` renders a markdown block. Mirrors `eval.GradeResult`.

### Profile / publish — the `harness` artifact (H2)

- **`HarnessProfile`** — a frozen dataclass, the harness analog of `publish.ModelCard`: `title`, `one_liner`, `harness` / `harness_version`, `license`, `positioning`, `lanes` (per-lane rows: `name`, `provider`, `model`, `tokens_per_sec`, `sustained_load_minutes`, `format_error_rate`, `clean_run_rate`, `footprint_gb`, `recommended`), `hermes_config`, `env_example`, `router_yaml`, `doctor_checklist`, `known_drift`, `tags`, `article_slug` / `article_title`, `hf_repo`. `.render()` emits the README (positioning → serving-lanes table → embedded config → doctor checklist → Methods backlink → Known drift → footer); `.files()` returns the `(rel_path, text)` pairs to stage (`README.md` + `hermes.yaml` + `.env.example` + optional `router.yaml`); `.to_manifest(slug, hf_repo)` builds the `ArtifactManifest(kind="harness")` the Astro catalog renders. Deterministic and diff-stable.
- **`publish_harness(profile, repo_name, staging_dir, slug=None, artifacts_dir=None, dry_run=True, token=None, org=None, commit_message=...)`** — the orchestrator (thinner than `publish_quant`): stages `profile.files()`, optionally writes the manifest to `artifacts_dir`, and pushes the folder via the existing `publish.HFHubAdapter` (dry-run by default). Returns a `publish.PublishResult`.

### fieldkit-as-MCP — the keystone (H4)

The submodule `fieldkit.harness.mcp` exposes a **curated** subset of fieldkit surfaces as Model-Context-Protocol tools, so an agent harness (Hermes first, but any MCP client) can drive the Spark itself. Launch over stdio with `python -m fieldkit.harness.mcp` and wire into Hermes via `hermes mcp add fieldkit --command <py> --args -m fieldkit.harness.mcp --env LLAMA_CPP_BIN=...`. The `mcp` SDK is the optional **`fieldkit[harness]`** extra — `import fieldkit.harness` stays stdlib-only and the tool *functions* are callable without the SDK; only `build_mcp_server` needs it.

The curation **is** the containment posture (the H3 philosophy at the tool layer): read-only tools carry `readOnlyHint`; the one expensive write (`quantize_gguf`) defaults to `dry_run=True` and is envelope-guarded; `publish_quant_dry_run` is dry-run-*forced* — the real-push code path is unreachable through the server. The server runs on the host, so safety is the shape of the tool list, not a sandbox; pair it with a hardened Hermes (`harden_config`).

- **`MCP_SERVER_NAME`** — `"fieldkit"`, the default server name.
- **`MCPToolSpec`** — frozen `(name, surface, summary, read_only)`; pure data describing one tool, importable without the `mcp` SDK so the catalog/article table can enumerate the surface without booting a server.
- **`MCP_TOOL_SPECS`** — the seven curated tools: `spark_inference_envelope` + `spark_weight_footprint` (capabilities, read-only), `measure_gguf_throughput` + `measure_gguf_perplexity` (quant, real GPU work via llama-bench/llama-perplexity), `quantize_gguf` (quant, `dry_run`-default + guarded), `publish_quant_dry_run` (publish, dry-run-forced card stage + preview), `ask_second_brain` (rag, read-only — NIM embed → pgvector → NIM LLM, the `mcp-second-brain-in-claude-code` bridge).
- **`build_mcp_server(name="fieldkit")`** — lazy-imports `mcp.server.fastmcp.FastMCP`, registers the seven tools with descriptions + `readOnlyHint` annotations, and returns the (un-run) server. Raises `McpNotAvailable` if the extra is missing.
- **`run_mcp_server(name="fieldkit")`** — `build_mcp_server(name).run()` over stdio; the `python -m fieldkit.harness.mcp` entrypoint.
- **`McpNotAvailable`** — an `ImportError` subclass raised when the `fieldkit[harness]` extra (the `mcp` SDK) is not installed; carries the `pip install fieldkit[harness]` hint.

### Brain evaluator (Step 3)

Promoted from `articles/field-fixing-the-hermes-harness-on-spark/evidence/hermes_brain_eval.py` after the cross-lane bakeoff earned the abstraction. Composes the `fieldkit.eval` graded-rubric primitives ([`docs/api/eval.md`](./eval.md#graded-rubric-primitives-v011)) with the existing `tool_call_reliability` to score Hermes head-to-head across serving lanes.

The H2 lane bakeoff measured throughput + tool-call FORMAT reliability and found every lane tied at 0% format error — picking the fastest, not the better brain. This is the missing axis: does the model that drives Hermes actually do the agent tasks *right*, *consistently*?

- **`BrainCandidate(label, base_url, model, context_length=64000, lane=None)`** — what to evaluate. `lane=None` → an already-up endpoint (the NIM-incumbent shape); `lane=<ServingLane>` → wrap the eval in `serve_lane(lane, guard=True, warm_timeout=...)`. After warm the lane's `base_url` overrides the candidate's (the lane may bind a different port than the bare spec).
- **`bucket_hermes_sessions(records, slots, *, pre_buffer=1.0, post_buffer=5.0, start_tolerance=0.5)`** — pure fn: assign each exported Hermes CLI session to exactly one `(prompt_id, attempt)` slot. The rule is mutually-exclusive: a session belongs to the LAST slot whose `t_start <= session.started_at` (with `start_tolerance` letting a clock-skewed-just-before-launch session snap forward to the earliest slot). The earlier ±2s pad-window double-counted back-to-back neighbours; this rule does not. `slots` accepts `_Slot` records or `(prompt_id, attempt, t_start, t_end)` tuples.
- **`evaluate_brain(suite, *, label, scratch_dir, runs=1, core_only=False, available_conditions=(), base_url=None, model=None, hermes_bin="hermes", prompt_timeout=360.0, throughput_samples=0, enable_telemetry=False, session_export_path=None, extra_env=None, on_attempt=None) -> BrainScorecard`** — drives ONE already-pointed-at endpoint through a suite. N attempts per selected prompt, buckets exported sessions to attempts, scores each via `score_answer`, composes `tool_call_reliability` over the bucketed records, and builds the scorecard. Caller's responsibilities: the `scratch_dir` is seeded with the fixtures the prompts reference (paths are relative), and Hermes is already pointing at the endpoint (`point_hermes_at_endpoint` is the swap helper). `throughput_samples > 0` AND `base_url` + `model` run a dedicated decode probe AFTER the suite (so the lane is still warm but the probe's decode isn't double-counted in telemetry).
- **`evaluate_brains(suite, candidates, *, scratch_dir, runs=1, core_only=False, available_conditions=(), hermes_bin="hermes", prompt_timeout=360.0, throughput_samples=3, enable_telemetry=True, warm_timeout=900.0, headroom_gb=8.0, on_progress=None) -> dict[label, BrainScorecard]`** — the bakeoff loop. For each candidate: optionally `serve_lane()` its lane, `point_hermes_at_endpoint(...)` Hermes at it, call `evaluate_brain`, tear down. Exceptions in one candidate are caught and recorded on its scorecard's `error` field; the loop continues. `on_progress(cand, phase)` (if given) fires with `"warming"` / `"evaluating"` / `"done"` / `"error"`.
- **`BrainScorecard`** — frozen, per-candidate rollup. `rank_key` returns the Step-2 ranking tuple: `(honesty_gate, core_pass_rate, consistency, -runaway_rate, tokens_per_sec or 0.0)`. Honesty is a GATE, not just an axis — a candidate that confabulates on the unfetchable prompt sorts below one that hedges, regardless of how well it scored elsewhere. Sort with `sorted(cards, key=lambda s: s.rank_key, reverse=True)`. Carries the suite results (`per_prompt: tuple[BrainPromptScore, ...]`), the composed `tool_call_reliability`, optional `tokens_per_sec` + `latency` + `telemetry` blocks, and `error: str | None` (set when the candidate raised mid-run).
- **`BrainPromptScore`** — per-prompt aggregate: `pass_count`, `pass_rate`, `runaway_count`, `runaway_rate`, `agreement` (`max(pass_count, n - pass_count) / n` — 1.0 deterministic, 0.5 coin-flip), `correct_tool_rate`, wall min/mean/max, `task_success: bool` (majority vote across attempts), and `attempts: tuple[BrainAttempt, ...]`.
- **`BrainAttempt`** — one `hermes -z` turn: `task_success` (rubric verdict), `why`, `tools_called`, `correct_tool`, `format_errors`, `n_sessions`, `wall_s`, `timed_out`, `answer_preview` (first 400 chars, `<think>`-stripped — what a human reading the transcript would quote).
- **`point_hermes_at_endpoint(base_url, model, *, context_length=64000, hermes_bin="hermes", timeout=60.0)`** — the light-touch swap. Issues five `hermes config set` calls (`model.provider=custom`, `model.base_url`, `model.default`, `model.context_length`, `auxiliary.compression.context_length` — Hermes reuses the served model as its compression model, so the auxiliary context floor has to match). For a clean first-time setup use `configure_hermes`.
- **`Telemetry(interval=2.0)`** — background GPU%/unified-memory/temp sampler. `start()` / `stop()`; `stop()` returns a rollup with `gpu_util_mean/max`, `gpu_mem_used_mib_max`, `unified_used_gb_max`, `gpu_temp_c_max`. GB10-aware: `nvidia-smi memory.used` is `[N/A]` on unified memory, so each field is parsed independently and real memory comes from `/proc/meminfo` (`MemTotal − MemAvailable`).
- **`measure_throughput(base_url, model, *, samples=3, prompt=None, max_tokens=256)`** — dedicated decode-throughput probe. Hits `/v1/chat/completions` at temperature 0 with a fixed 150-word prompt and returns `{"tok_s": <median>, "samples": [...]}`. Returns `{"tok_s": None, "samples": []}` on any failure — best-effort, never raises.

## Coming across the arc

| Surface | Article | Reuse |
|---|---|---|
| `VerticalRoute` / `build_vertical_router`, `RouterConfig` / `build_cost_router` | H5–H6 | the 5 Orionfold GGUFs; OpenRouter overflow. |

## Notes

- **Cheap import.** Heavy/optional integrations (docker, httpx, the sibling fieldkit modules) are lazy — `import fieldkit.harness` imports only the stdlib.
- **Two new artifact kinds.** The arc adds `harness` (a reproducible Spark-Hermes profile bundle) and `skill` (an agentskills.io `SKILL.md` package, cross-compatible with Claude Code skills) to `publish.ARTIFACT_KINDS` — see the spec §4.8.
