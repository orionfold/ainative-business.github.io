---
project: hermes-harness
version: v1.0
status: locked
created: 2026-05-26
authoritative: Spark
---

# Hermes Harness v1.0 — Project Specification

> First entry in the new **"Harnesses"** content line — optimized agent harnesses released for the
> DGX Spark. This spec covers Hermes Agent (Nous Research, MIT) end-to-end: install → configure →
> optimize serving lane → harden → run → drive value, with `fieldkit` API extensions and reusable
> artifacts at every step. Entry #2 (a different harness) will get its own `specs/<harness>-v1.md`.

## 1. Context

### Why this project

Through the Orionfold publishing arc, this project mastered the *artifact* surface: quantize a base
model, measure it on the Spark, publish a GGUF + card + notebook. The verticals (patent / legal /
finance / cyber / medical) are all "here is a thing you download and run." What's missing is the
**cockpit** — the harness a Spark power-user actually *drives the box from*, the thing that turns five
published models and a `fieldkit` API into a daily-use personal AI.

This project opens that surface. **Hermes Agent** (Nous Research, MIT-licensed) is the rare frontier
harness whose design intersects almost everything this project already owns:

- It treats **NVIDIA NIM (Nemotron) as a first-class provider** — not just Ollama. Nobody else's
  Spark write-up documents the NIM lane; this project has deep NIM expertise (`fieldkit.nim`, the
  cached `nemotron-nano-9b-v2-dgx-spark` NIM, the tuned `NIM_MAX_BATCH_SIZE=32` → 325 tok/s knob).
- It speaks **MCP**, so `fieldkit` can be exposed as tools and Hermes can *drive the Spark itself* —
  quantize, measure, publish, retrieve. That is the "machine that builds machines" thesis, productized.
- Its skills follow the **agentskills.io standard = the same `SKILL.md` + YAML format as Claude Code
  skills**. A skill written for Hermes works in Claude Code, Cursor, or Codex CLI unchanged. The
  project's existing `.claude/skills/` library is *already* a set of distributable artifacts.
- It is **provider-agnostic with a built-in OpenRouter path**, which makes a measured local-vs-cloud
  cost story tractable: local NIM/GGUF for free, OpenRouter open models for hard reasoning.

### The "cockpit" thesis

The three application arcs (Second Brain / LLM Wiki / Machine that Builds Machines) answer *what you
run* on the Spark. Harnesses answers a different question: **what you drive it from, and how you make
that fast, cheap, and hardened.** A harness sits *above* the arcs — the same `fieldkit`-as-MCP surface
that gives Hermes the Second Brain (via `fieldkit.rag`) also lets it operate the MTBM pipeline (via
`fieldkit.quant`/`.publish`). "Second Brain, Wiki, and MTBM are *what* you run; the harness is *how you
drive it*."

### Editorial uber-theme alignment

"DGX Spark as personal AI power user / edge AI builder" gets a new, strong expression: the Spark is
always on at home, so a hardened Hermes gateway becomes a private always-on agent you text from your
phone — 100% local, no cloud, no API key, optionally escalating to cheap open models only when a task
truly needs it. The unique, defensible angle is **NIM-first** (everyone else documents Ollama).

## 2. Use-case taxonomy — the three pillars

The requirement frame for this project is the three-pillar test the user set. Every article and every
fieldkit surface maps to at least one pillar; the publish gate checks all three are demonstrated.

**Desirability — easy, fast setup, powerful capabilities**
- D1. One-command install + first local agent turn with no API key (time-to-first-turn budget).
- D2. Setup step count low enough to fit one article without a checklist appendix.
- D3. Powerful out of the box: MCP tools, persistent memory, self-improving skills, multi-platform
  gateway (the always-on Telegram/Signal agent).

**Viability — zero / low cost via local routing + OpenRouter**
- V1. Local NIM / GGUF lane = $0 marginal cost (electricity only); the default for private/simple work.
- V2. 3-tier cost router (local → OpenRouter cheap → frontier) with a **measured** dollar curve, not a
  claimed one.
- V3. Reuse of already-published Orionfold verticals as the local experts — zero new training cost.

**Feasibility — optimized stack for DGX Spark**
- F1. Serving lane right-sized for the 128 GB unified-memory envelope (Qwen3 35B-A3B MoE ~20 GB vs
  27B dense), with the OOM-stacking landmine guarded in code.
- F2. NIM-first lane tuned to the project's measured throughput; vLLM/Ollama/llama-server documented as
  alternatives with their Spark gotchas (EngineCore orphan, unified-memory pressure).
- F3. **Tool-call reliability** measured as the agent-critical capability — a fast lane that can't do
  reliable tool calls is useless to a harness.

### Deliverables

| Artifact | Surface | Article / Session |
|---|---|---|
| New SERIES `Harnesses` + two artifact kinds (`harness`, `skill`) | `content.config.ts` + `[series].astro` | Session 1 |
| `fieldkit.harness` module (serve / configure / install / harden / route / eval / profile) + `docs/api/harness.md` | `fieldkit` PyPI | S1 stub → fleshed across H1–H6 |
| `articles/the-hermes-harness-on-spark/` (H1 — install + NIM) | published article | Session 2 |
| `articles/hermes-serving-lane-on-spark/` (H2 — lane bakeoff) | published article | Session 3 |
| `Orionfold/spark-hermes-profile` (`kind: harness`) | HF + artifact manifest | Session 3 |
| `articles/hardening-the-hermes-harness-on-spark/` (H3 — harden) | published article | Session 4 |
| `articles/hermes-drives-the-spark-via-fieldkit-mcp/` (H4 — keystone) | published article | Session 5 |
| Curated `.claude/skills/` subset + new Hermes-Spark skills → agentskills.io (`kind: skill`) | agentskills.io + artifact manifests | Session 5 |
| `articles/hermes-vertical-router-on-spark/` (H5 — router) + router `harness` artifact | published article + HF | Session 6 |
| `articles/hermes-cost-routing-local-and-openrouter/` (H6 — cost) | published article | Session 7 |
| `fieldkit` release(s) cutting the `harness` module + the two new artifact kinds | PyPI | as modules land |

## 3. Decisions

### 3.1 Locked decisions

| # | Decision | Value |
|---|---|---|
| 1 | Category shape | New **SERIES `Harnesses`**, NOT a new STAGE (precedent: Frontier Scout) |
| 2 | New artifact kinds | **`harness`** (Spark-Hermes profile bundle) + **`skill`** (agentskills.io SKILL.md package) |
| 3 | Arc scope | Full 6-article arc H1–H6; spine = H1–H4 (H4 keystone); H5/H6 are leverage multipliers |
| 4 | Hero serving lane (H1) | **NIM Nemotron first**; Ollama + llama-server shown as the easy alternatives |
| 5 | Keystone | **fieldkit-as-MCP ("Hermes drives the Spark") is in v1** (H4) |
| 6 | Skill artifacts | Publish **both** a curated `.claude/skills/` subset AND new Hermes-Spark skills |
| 7 | Documented serving models | Qwen3 35B-A3B MoE (~20 GB) + 27B dense as the two lanes; Nemotron via NIM |
| 8 | Arc threading | MTBM (H4) + Second Brain (`fieldkit.rag` over MCP) stay **editorial cross-links + `book_chapters`**, not `series:`-tagged |
| 9 | Generation boundary | `fieldkit.harness` is deterministic Python only; all LLM generation (skill bodies, agent task runs, prose) stays in session-driven skills per `[[feedback_llm_skill_pattern]]` |
| 10 | Upstream pin discipline | Hermes is fast-moving; `HermesConfig.extra` free-form escape hatch absorbs new YAML keys without a fieldkit release (mirrors `ModelCard.extra_yaml`) |

### 3.2 SERIES not STAGE — justification

STAGES are pipeline phases of working with a model (`foundations → … → agentic → observability →
dev-tools`). The Hermes journey threads through `agentic` / `deployment` / `inference` / `observability`
but introduces no new *phase of ML work*. Adding a `harnesses` stage would (a) orphan these articles
from the stage pages where readers already look for serving and agent content, and (b) be the only
stage named after a product line rather than a workflow phase — breaking the taxonomy's internal logic.
**Frontier Scout** is the precedent: a series whose articles spread across stages ad-hoc with no
dedicated stage. Harnesses is the same shape.

### 3.3 Provider matrix (why NIM-first)

| Provider | Role | Why |
|---|---|---|
| **NIM (Nemotron)** | Primary local lane, H1 hero | First-class Hermes provider; project's unique, tuned, measured angle; correct tokenizer + chat-template + engine config per `[[feedback_prefer_nim_over_vllm_for_nemotron]]` |
| **llama-server (GGUF)** | Local vertical lane | The project's primary GGUF lane; serves the 5 Orionfold verticals directly; `discover_local_server` already probes :8080 |
| **Ollama** | Easiest local alternative | Matches the NVIDIA official Spark guide; lowest-friction first turn; shown as the "if you just want it running" path |
| **vLLM** | High-throughput MoE lane | Qwen3 35B-A3B-FP8 via `eugr/spark-vllm-docker`; documented with the EngineCore-orphan teardown landmine |
| **OpenRouter** | Cloud overflow | The cost-routing escalation tier (H6); 200+ open models; cheap-per-token vs frontier |

### 3.4 Naming

- Series display name: **`Harnesses`**; slug `harnesses` (`/series/harnesses/`).
- Article slugs: the `*-on-spark` family — `the-hermes-harness-on-spark`, `hermes-serving-lane-on-spark`,
  `hardening-the-hermes-harness-on-spark`, `hermes-drives-the-spark-via-fieldkit-mcp`,
  `hermes-vertical-router-on-spark`, `hermes-cost-routing-local-and-openrouter`.
- Harness artifact slug: `spark-hermes-profile` (lane variants `nim-nemotron` / `local-gguf` /
  `openrouter-overflow`); router artifact `spark-hermes-vertical-router`.

## 4. Architecture

### 4.0 Article sequence (the spine)

| # | Slug | Thesis | Stage (also_stages) | fieldkit_modules | Pillar |
|---|---|---|---|---|---|
| **H1** (must) | `the-hermes-harness-on-spark` | Install Hermes; first local agent turn against NIM Nemotron, no API key. The harness is the cockpit; NIM-first is the unique angle. | agentic (inference, deployment) | nim, capabilities, harness | Desirability + Feasibility |
| **H2** (must) | `hermes-serving-lane-on-spark` | Right-size the lane: Qwen3 35B-A3B MoE vs 27B dense on the 128 GB envelope; tok/s, sustained-load, **tool-call reliability**. | deployment (inference) | capabilities, harness, nim | Feasibility + Desirability |
| **H3** (must) | `hardening-the-hermes-harness-on-spark` | Guardrails on the loop, tool scoping, secret hygiene, restart behavior — a harness you'd leave running on your desk. | agentic (observability) | harness, eval | Desirability |
| **H4** (must, keystone) | `hermes-drives-the-spark-via-fieldkit-mcp` | Expose `fieldkit` as MCP tools → Hermes quantizes/measures/publishes/retrieves. The machine that builds machines, productized. | agentic (dev-tools, deployment) | harness, cli, quant, publish | Desirability + Viability |
| **H5** (nice) | `hermes-vertical-router-on-spark` | One harness, five experts — route per-domain to the 5 Orionfold GGUFs, all local, zero new model work. | inference (agentic, deployment) | harness, nim, eval | Viability + Feasibility |
| **H6** (nice) | `hermes-cost-routing-local-and-openrouter` | The viability close: 3-tier routing (local NIM $0 → OpenRouter cheap → frontier) with a **measured** dollar curve. | deployment (observability, agentic) | harness, eval | Viability |

H1–H4 ship in order; that arc alone is a complete story (cockpit installed → fast → safe → driving the
box). H5/H6 follow H4 in either order.

### 4.1 H1 — install + NIM provider wiring

- `install_hermes(dry_run=True)` logs the exact `curl -fsSL <install.sh> | bash`; flip
  `dry_run=False, allow_pipe_to_bash=True` to execute (two-key safety on piping a remote script to a
  shell). Then `hermes_doctor()` → `DoctorReport`.
- Bring up the NIM lane: `NIMLane(LaneSpec("nim", "nemotron-nano-9b-v2-dgx-spark", port=8000),
  max_batch_size=32)` inside `serve_lane(...)`; health via `nim.wait_for_warm` (~90 s cold start).
- `configure_hermes(lane=..., provider="nim", slow_serving=True)` renders the Hermes YAML + `.env`
  (`HERMES_STREAM_READ_TIMEOUT=1800` for slow local serving). Endpoint resolution reuses
  `discover_local_server` (probes :8080 llama-server, :8000 NIM).
- Gate: first agent turn runs locally, no API key. Capture the `<think>`-prefix behavior per
  `[[feedback_nim_think_prefix_convention]]`.

### 4.2 H2 — serving-lane bakeoff + envelope sizing

- Size each lane with `fieldkit.capabilities` (`weight_bytes` + `kv_cache_bytes` vs
  `Capabilities.load().hardware.unified_memory_gb`) before launch. `serve_lane(..., guard=True)` refuses
  to start a lane that would tip the 128 GB envelope (the OOM-stacking landmine per
  `[[project_spark_unified_memory_oom]]`).
- Benchmark Qwen3 35B-A3B MoE (~20 GB) vs 27B dense across lanes; record tok/s, sustained-load minutes,
  thermal envelope, and **tool-call reliability** (`tool_call_reliability` over `eval.AgentRun`).
- First `harness` artifact: `HarnessProfile.render()` → `Orionfold/spark-hermes-profile` with lane
  variants. `perplexity`/`vertical_eval` left empty (N/A to a harness).

### 4.3 H3 — hardening

- `HardeningPolicy(terminal_backend="docker", network_egress="deny", secrets_from_env_only=True,
  local_first=True)` + `harden_config(config, policy)` → a hardened `HermesConfig`. Sandbox backend by
  default (not `local`), tool allow/deny lists, env-only secrets.
- Reuse the project's Guardrails policy patterns (the `guardrails-on-the-retrieval-path` work) as the
  conceptual basis for the agent-loop guardrails.
- Gate: harness survives a scripted hostile-tool-call test; restart behavior verified.

### 4.4 H4 — fieldkit-as-MCP (keystone)

- Expose a curated set of `fieldkit` surfaces as MCP tools so Hermes can operate the Orionfold pipeline:
  `fieldkit feasibility/envelope` (capabilities), `quantize_gguf` + `measure_*` (quant), `publish_quant`
  dry-run (publish), `Pipeline.ask` (rag, Second-Brain bridge).
- The agentskills.io ≡ Claude Code skill equivalence is the editorial hook: "the skills you already
  wrote for Claude Code load into Hermes unchanged." Publish the curated `.claude/skills/` subset +
  new Hermes-Spark skills (§4.8).
- Threading: open by acknowledging `autoresearch-agent-loop` / the MTBM agent-loop pieces; frame
  Hermes + fieldkit-MCP as the *general-purpose, productized* version of that bespoke loop. Cross-link
  `mcp-second-brain-in-claude-code` — the same MCP tool surface serves both harnesses. Set
  `book_chapters: [10, 11]`; keep `series: Harnesses`.
- Gate: Hermes runs a real `fieldkit` quant or measure via MCP, end-to-end on the box.

### 4.5 H5 — vertical router (one harness, five experts)

- `build_vertical_router([VerticalRoute("patent", "Orionfold/patent-strategist-v3-nemo-GGUF", …),
  VerticalRoute("legal", "Orionfold/Saul-7B-Instruct-v1-GGUF", …), …])` over the 5 published verticals
  (patent / legal / finance / cyber / medical). Each route is served one-at-a-time via
  `serve_lane(LlamaServerLane(...))` so the router stays OOM-safe.
- Optional escalation tier to OpenRouter for hard reasoning. Reuses every shipped GGUF at zero new
  training cost — the strongest expression of the "leverage not forced" test.

### 4.6 H6 — cost routing (the viability close)

- `build_cost_router(local_endpoint=…, local_model=…, openrouter_standard=…, openrouter_complex=…)`
  → 3-tier `RouterConfig` (TIER_SIMPLE → local Spark $0, TIER_STANDARD/COMPLEX → OpenRouter). Routing
  predicates are deterministic (keyword sets / token-budget thresholds), NOT a runtime LLM classifier.
- **Measure** the dollar curve: run a representative task suite across the tiers, record cost + quality
  per tier, embed the actual curve. The claimed "60–80% savings" is metadata in `notes`, never asserted
  as fact by the code — the article shows our number.

### 4.7 `fieldkit.harness` module — public API surface

New single-file module `fieldkit/src/fieldkit/harness/__init__.py`, idiomatic to the package
(`from __future__ import annotations`, frozen/plain dataclasses, context managers, lazy imports,
`HarnessError` base, deterministic `.render()`, hand-rolled YAML via `publish`'s stdlib emitter — no new
dep). `__all__` groups:

- **Serve:** `LaneSpec`, `ServingLane` + `NIMLane`/`VLLMLane`/`OllamaLane`/`LlamaServerLane`,
  `resolve_lane`, `serve_lane(spec, guard=True, headroom_gb=8.0, …)` contextmanager,
  `UnifiedMemoryExceeded`, `ServingLaneError`, `SERVING_LANES`.
  - `LlamaServerLane` **delegates** to `notebook.local_server` (cleanest reuse).
  - `NIMLane` health **reuses** `nim.wait_for_warm`; starts the cached NIM with `NIM_MAX_BATCH_SIZE=32`.
  - `VLLMLane.teardown` stops the container then **sweeps orphaned EngineCore PIDs** per
    `[[feedback_vllm_engine_core_orphan]]` (the one place `serve_lane` can't copy `local_server`).
  - `serve_lane` guard **reuses** `capabilities.weight_bytes`/`kv_cache_bytes`; errs toward refusing.
- **Install / doctor:** `install_hermes(method="script", dry_run=True, allow_pipe_to_bash=False)`,
  `hermes_doctor`, `DoctorReport` (per-check `(name, ok, detail)` + binary `.ok` + `.report()` markdown,
  mirroring `eval.GradeResult`), `HermesNotInstalled`, `DoctorFailed`.
- **Configure:** `HermesConfig`/`EnvFile`/`configure_hermes` (endpoint resolution mirrors
  `notebook.open_model`; reuses `discover_local_server`; `HERMES_STREAM_READ_TIMEOUT_SLOW=1800`).
  No side effects on import; caller `.render()` + writes.
- **Harden:** `HardeningPolicy` + `harden_config` (pure function → new frozen `HermesConfig`).
- **Route:** `RouteTier`/`RouterConfig`/`build_cost_router` (3-tier) + `VerticalRoute`/
  `build_vertical_router` (over the 5 Orionfold GGUFs). Config generators; deterministic predicates.
- **Eval:** `tool_call_reliability(runs)` (4-metric reducer over `eval.AgentRun.tool_calls()`/
  `tool_format_errors()`) + `HarnessEvalResult` (composes `eval.summarize_agent_runs`/`Bench`/
  `AssertionGrader`; `.report()`). ~90% reuse of `fieldkit.eval`.
- **Profile / publish:** `HarnessProfile` (frozen dataclass; `.render()` README-style bundle +
  `.files()` `(rel_path, text)` pairs + `.to_manifest(slug, hf_repo)` → `ArtifactManifest(kind="harness")`).

Add `'harness'` to `FIELDKIT_MODULES` (`content.config.ts`) and ship `fieldkit/docs/api/harness.md`
(the curator `audit-docs` diffs `__all__` against the api page, so the page is required at release).

### 4.8 New artifact kinds + manifest writers

`fieldkit.publish.ARTIFACT_KINDS` is currently
`("quant", "lora", "adapter", "dataset", "bench", "notebook")`. Append two:

- **`harness`** — reproducible Spark-Hermes profile bundle: provider config + serving-lane recipe +
  guardrail policy + skills/MCP wiring + measured tok/s + tool-call reliability. Rendered by
  `HarnessProfile` (analog of `ModelCard`); pushed via the **existing** `HFHubAdapter` (dry-run-first,
  `.files()` → `stage_text` → `push_folder`). `perplexity`/`vertical_eval` optional → schema unaffected.
  Add `publish_harness(profile, repo_name, …)` orchestrator (thinner than `publish_quant`).
- **`skill`** — agentskills.io `SKILL.md` package. Seed corpus = a curated subset of existing
  `.claude/skills/` (the cross-compatible ones, e.g. a `fieldkit-ops` extraction, `hf-publisher`
  patterns) **plus** new Hermes-Spark skills (`spark-serve`, `vertical-route`). Published to
  agentskills.io via `hermes skills publish … --to github`; cataloged via an `ArtifactManifest(kind=
  "skill")`. The harvest→curate→republish flywheel (Hermes auto-writes skills; we curate the good ones)
  is the MTBM expression — documented in H4 prose, automated later if it earns it.

**Authoring SKILL.md *bodies* is LLM generation → a session-driven skill** (`hermes-skill-author`,
writing via Edit like `notebook-author`), never `fieldkit.harness`. The module may offer a deterministic
frontmatter *scaffolder* (defer to v2 unless H5 needs it).

### 4.9 Schema edits (Session 1) — the two-site trap

- `src/content.config.ts`: append `'Harnesses'` to `SERIES` + `SERIES_SLUGS` (`'Harnesses':
  'harnesses'`); append `'harness'` and `'skill'` to `ARTIFACT_KINDS`; append `'harness'` to
  `FIELDKIT_MODULES`.
- `src/pages/series/[series].astro`: add a `'Harnesses'` entry to the hardcoded `SERIES_COPY` map
  (line 10). **This is the trap** — the page does `const copy = SERIES_COPY[name]; … copy.blurb`, so a
  missing key throws on `undefined.blurb` and the series page 500s. Both edits MUST land together.
  Proposed blurb: *"Optimized agent harnesses for the DGX Spark. Take a frontier open-source harness,
  tune its serving lane, harden it, and wire it to the box itself via fieldkit-as-MCP — the cockpit you
  drive Spark from. Hermes (Nous Research, MIT) is entry #1."*
- `.claude/skills/tech-writer/references/use-case-arc.md`: add a "Harnesses series" section so the
  tech-writer next-article detection knows the H1–H6 walk.

## 5. Pillar-realization strategy

Analog to the patent-strategist reasoning-preservation strategy — the measurable commitments that decide
whether each pillar is actually demonstrated, not just asserted.

| Pillar | Metric | Target / gate |
|---|---|---|
| Desirability | time-to-first-agent-turn (install → first local reply) | single article, no appendix; record the wall-clock number |
| Desirability | setup step count | fits H1 prose without a checklist appendix |
| Viability | local lane marginal cost | $0 (electricity only) — stated and shown for NIM/GGUF |
| Viability | cost-routing dollar curve | **measured** local-vs-OpenRouter on a representative task suite (H6); embed the curve |
| Feasibility | unified-memory headroom | every documented lane stays inside 128 GB with the `serve_lane` guard proving it |
| Feasibility | throughput | tok/s + sustained-load minutes per lane (H2), NIM lane tied to the project's measured 325 tok/s |
| Feasibility | **tool-call reliability** | `format_error_rate` per lane (the agent-critical number); a lane that fails here is disqualified regardless of speed |

## 6. Harness artifact + bench design

### 6.1 What the `harness` bundle contains

`HarnessProfile.files()` stages: `README.md` (positioning → lane → reliability eval → embedded
`hermes.yaml` + `.env.example` + `router.yaml` → doctor checklist → Methods backlink → Orionfold
footer), plus the embedded config files. Deterministic, diff-stable — mirrors `ModelCard.render()`.

### 6.2 Serving-lane benchmark methodology (H2)

- **Throughput:** tok/s per lane × model, via the lane's own bench path; NIM lane uses the tuned
  `NIM_MAX_BATCH_SIZE` setting.
- **Sustained-load:** minutes of continuous generation before thermal throttle (reuse the quant
  module's `ThermalProbe` pattern).
- **Tool-call reliability:** drive Hermes through a fixed agentic task set; parse the run JSONL via
  `eval.AgentRun`; `tool_call_reliability` returns `{tool_calls, tool_format_errors, format_error_rate,
  clean_run_rate}`. This is the headline metric of the harness card.
- **Bench-equivalence:** identical task prompts byte-for-byte across lanes (hash-asserted), same
  temperature, same tool schema.

### 6.3 Cost-routing measurement methodology (H6)

Run the same representative task suite through (a) local-only, (b) 3-tier routed. Record per-tier token
counts × published OpenRouter prices → dollar cost; record quality via the same agentic-task pass rate.
Embed both the cost delta and the quality delta. The article's claim is *our measured number*, with the
upstream "60–80%" cited as the source claim.

## 7. Reuse inventory (genuine-leverage audit)

### 7.1 Reused as-is (zero or near-zero new work)

| Asset | Where reused | Note |
|---|---|---|
| `fieldkit.nim.NIMClient` (OpenAI-compatible) | H1 provider wiring; `NIMLane` health | already correct tokenizer/template per `[[feedback_prefer_nim_over_vllm_for_nemotron]]` |
| Cached `nemotron-nano-9b-v2-dgx-spark` NIM + `NIM_MAX_BATCH_SIZE=32` knob | H1/H2 hero lane | `[[reference_nim_local_serving]]`, `[[reference_nim_spark_env_vars]]` |
| `notebook.local_server` / `discover_local_server` | `LlamaServerLane`, `configure_hermes` | cleanest reuse — `LlamaServerLane` fully delegates |
| `capabilities.weight_bytes` / `kv_cache_bytes` / `Capabilities.load()` | `serve_lane` unified-memory guard | no new memory math |
| `eval.AgentRun` / `summarize_agent_runs` / `Trajectory` / `Bench` / `AssertionGrader` | H2/H3/H6 eval | ~90% of EVAL is reuse |
| 5 Orionfold vertical GGUFs (`patent-strategist-v3-nemo-gguf`, `saul-7b-instruct-v1-gguf`, `finance-chat-gguf`, `securityllm-gguf`, `ii-medical-8b-gguf`) | H5 vertical router | every shipped model reused, zero new training |
| Existing `.claude/skills/` (agentskills.io format already) | H4 `skill` artifacts | cross-compatible; curate + republish |
| `publish.ArtifactManifest` / `write_artifact_manifest` / `HFHubAdapter` / stdlib YAML emitter | `harness`/`skill` publishing | no new publishing machinery |
| `fieldkit.rag.Pipeline` | H4 Second-Brain-over-MCP bridge | exposed as an MCP tool |
| Guardrails policy patterns (`guardrails-on-the-retrieval-path`) | H3 hardening | conceptual basis |

### 7.2 Newly generated

`fieldkit.harness` module · `publish_harness()` / `publish_skill()` writers · the `harness` + `skill`
artifact kinds · the Spark-Hermes profile bundle + router config · the agentskills.io-published skills ·
6 articles · the content.config + `[series].astro` edits · `docs/api/harness.md`.

### 7.3 Flagged forced — deliberately NOT doing

- A new STAGE for Harnesses (use the series; map to existing stages).
- Schema-tagging H4 as `series: Machine that Builds Machines` (keep MTBM editorial, per Frontier-Scout
  precedent).
- Per-vertical Hermes *notebooks* (a harness is config, not a notebook — don't manufacture notebook
  artifacts just to reuse `notebook-author`).
- A frontmatter scaffolder in `fieldkit.harness` before a second consumer needs it (per
  `[[feedback_keep_scorer_local_until_reuse]]` discipline).

## 8. Risks and contingencies

### 8.1 Risk register

| ID | Risk | Likelihood | Impact | Mitigation | Fallback |
|---|---|---|---|---|---|
| R1 | Hermes installer fails on aarch64 / DGX OS | Med | High | `hermes_doctor` parse + early Session-2 smoke before writing H1 | Ollama-first path (still on-theme); document the gap |
| R2 | NIM Nemotron incompatible with Hermes's provider/tool-call interface | **Med** | **High** | Verify tool-calling against the NIM lane in Session 2 before committing H1 framing | Fall back to llama-server GGUF lane as H1 hero; keep NIM as H2 optimization |
| R3 | Local model can't do reliable tool calls (agent-critical) | Med | High | `tool_call_reliability` measured per lane in H2; disqualify a lane that fails | Document which models/lanes are agent-grade; recommend the reliable one |
| R4 | 35B-A3B MoE doesn't fit / throttles on Spark | Low-Med | Med | `serve_lane` guard + envelope math before launch | Document 27B dense or a smaller MoE as the recommended lane |
| R5 | MCP tool-exposure widens attack surface (Hermes drives the box) | Med | High | H3 hardening lands BEFORE H4; sandbox backend + tool allowlist for the fieldkit MCP server | Read-only MCP tool subset (feasibility/measure only, no publish/write) |
| R6 | agentskills.io publish format drifts vs `.claude/skills/` | Low | Med | Validate one skill round-trips both runtimes before bulk publish | Publish the subset that round-trips; note divergences |
| R7 | OpenRouter pricing/API instability undermines the cost curve | Low | Med | Snapshot prices at measurement time into the article evidence | Present the curve as a point-in-time measurement |
| R8 | vLLM EngineCore orphan hangs the box during H2 bakeoff | Med | High | `VLLMLane.teardown` orphan-sweep per `[[feedback_vllm_engine_core_orphan]]`; verify `free -h` after each lane | `pkill -f 'vllm\|EngineCore'`; reboot if mem not reclaimed |
| R9 | Unified-memory OOM from stacking lanes during the bakeoff | Med | High | One-model-at-a-time `serve_lane` guard; never stack | per `[[project_spark_unified_memory_oom]]` — stop services between lanes |
| R10 | Scope creep across 6 articles | High | Med | Hard cut lines (§8.3); H1–H4 is a shippable arc on its own | Ship the spine, defer H5/H6 to a follow-on |
| R11 | Hermes upstream moves fast, config schema shifts mid-arc | Med | Med | `HermesConfig.extra` free-form escape hatch | Pin a Hermes version in the profile bundle metadata |
| R12 | The two-site `[series].astro` edit gets missed → series page 500s | Med | Low | Called out in §4.9 + Session-1 gate (build + render `/series/harnesses/`) | n/a — caught at build |

### 8.2 Top 3 must-do early actions

1. **Session-2 NIM-tool-call smoke (R2 + R3)** — before writing H1, confirm Hermes drives the NIM
   Nemotron lane with reliable tool calls. This decides whether NIM stays the H1 hero or moves to H2.
2. **Session-1 build gate (R12)** — land both schema sites + confirm `/series/harnesses/` renders and the
   artifact schema validates the two new kinds before any article work.
3. **H3 hardening before H4 (R5)** — never expose the fieldkit MCP write surface to an un-hardened
   Hermes; sequence harden→drive.

### 8.3 Hard cut lines

- **End of Session 1:** series + kinds + `fieldkit.harness` stub land; site builds. Cut if schema won't
  validate the new kinds.
- **End of H2:** lane bakeoff measured. **Cut if:** no lane clears the tool-call-reliability bar → H1–H2
  become a "honest limits" piece and the arc pauses for a better serving story.
- **End of H4:** the keystone ships → the arc is a complete story. **H5/H6 are explicitly optional.**
- **Never** ship H4 without H3 (security sequencing, R5).

## 9. Article-by-article task plan

(Each ≈ one session of work; see HANDOFF.md for the live session breakdown.)

- **S1 — scaffold (no GPU):** spec; the two schema sites; `fieldkit.harness` stub + `FIELDKIT_MODULES`
  + `docs/api/harness.md`; use-case-arc section. Gate: build + `/series/harnesses/` render + schema valid.
- **S2 — H1 (install + NIM):** install Hermes; NIM smoke (R2/R3); first local turn; draft H1.
- **S3 — H2 (serving lane):** lane bakeoff + envelope math + tool-call reliability; first `harness`
  artifact; draft H2.
- **S4 — H3 (hardening):** policy + tool scoping + restart; hostile-tool-call test; draft H3.
- **S5 — H4 (fieldkit-as-MCP, keystone):** fieldkit MCP server; agentskills.io reuse; publish curated +
  new `skill` artifacts; draft H4 with MTBM/Second-Brain cross-links.
- **S6 — H5 (vertical router):** router over 5 verticals; router `harness` artifact; draft H5.
- **S7 — H6 (cost routing):** 3-tier router + measured dollar curve; draft H6; stats refresh; arc done.

## 10. Publish checklist

### 10.1 `harness` artifact card (`Orionfold/spark-hermes-profile`)
- Positioning block (problem / use_cases / audience / headline) — required post-v0.5.
- Lane variants table; measured tok/s + sustained-load + tool-call reliability.
- `known_drift` with bounds (e.g. "tool-call reliability measured on N tasks; format_error_rate X%").
- Embedded `hermes.yaml` + `.env.example` + (router) `router.yaml`. License `mit` (Hermes upstream).
- Article backlink (`ainative.business/field-notes/<slug>/`) + Orionfold footer.

### 10.2 `skill` artifacts (agentskills.io)
- One round-trip-validated skill first (R6); then the curated bulk + new Hermes-Spark skills.
- Each: `SKILL.md` (agentskills.io frontmatter) + an `ArtifactManifest(kind="skill")` catalog card.

### 10.3 Repo / site
- The two schema sites (`content.config.ts` + `[series].astro`) — together, always.
- `nvidia-learn-stats` refresh before committing any article (home infographic drifts silently).
- HANDOFF tail update after every commit per `[[feedback_handoff_md_update_protocol]]`.
- fieldkit release(s) via `fieldkit-curator` when the `harness` module / new kinds land; ship
  `docs/api/harness.md` (audit-docs gate) and a CHANGELOG `[Unreleased]` entry.

## 11. Change log

| Date | Change | Author |
|---|---|---|
| 2026-05-26 | Initial spec landed (v1.0 locked). Decisions §3.1 #1–#10 confirmed in the planning session (full 6-article arc · NIM-first hero · MCP keystone in v1 · both existing+new skills). | Manav (with Claude planning session) |

## 12. References

### Internal
- Plan workspace: `/home/nvidia/.claude/plans/we-will-create-another-delightful-willow.md`
- Vertical-curator article template: `articles/becoming-a-legal-curator-on-spark/article.md`
- Spec format precedent: `specs/patent-strategist-v1.md`, `specs/notebooks-as-artifacts-v1.md`
- Editorial arcs: `.claude/skills/tech-writer/references/use-case-arc.md`
- MTBM agent-loop pieces: `articles/autoresearch-agent-loop/`, `mcp-second-brain-in-claude-code`
- fieldkit modules reused: `fieldkit/src/fieldkit/{nim,notebook,capabilities,eval,publish,rag}/`
- Series page (the trap): `src/pages/series/[series].astro` `SERIES_COPY`
- Artifact schema: `src/content.config.ts` (`SERIES`, `ARTIFACT_KINDS`, `FIELDKIT_MODULES`)

### External
- Hermes Agent (Nous Research, MIT): https://github.com/NousResearch/hermes-agent
- Hermes docs: https://hermes-agent.nousresearch.com/docs/
- agentskills.io spec: https://agentskills.io/specification
- NVIDIA — Run Hermes Agent with Local Models | DGX Spark: https://build.nvidia.com/spark/hermes-agent/instructions
- NVIDIA blog — Hermes on RTX & DGX Spark: https://blogs.nvidia.com/blog/rtx-ai-garage-hermes-agent-dgx-spark/
- vLLM-on-Spark docker: https://github.com/eugr/spark-vllm-docker
- OpenRouter: https://openrouter.ai/

### Memory cross-references (`[[name]]`)
- `[[feedback_llm_skill_pattern]]` — generation = skill, never API/SDK; the §3.1 #9 boundary
- `[[reference_nim_local_serving]]` / `[[reference_nim_spark_env_vars]]` — NIM serving + the batch=32 knob
- `[[feedback_prefer_nim_over_vllm_for_nemotron]]` — why NIM (config, not engine) for Nemotron
- `[[feedback_nim_think_prefix_convention]]` — `<think>`-prefix handling on the NIM lane
- `[[project_spark_unified_memory_oom]]` — the OOM-stacking landmine the `serve_lane` guard enforces
- `[[feedback_vllm_engine_core_orphan]]` — `VLLMLane.teardown` orphan sweep
- `[[reference_fieldkit_notebook_module]]` — `local_server`/`discover_local_server` reuse
- `[[project_orionfold_parent_brand]]` — Orionfold handle for the harness/skill artifacts
- `[[project_publishing_to_ainative]]` — articles publish to ainative.business/field-notes/
- `[[feedback_handoff_md_update_protocol]]` — HANDOFF tail discipline
- `[[feedback_refresh_stats_on_publish]]` — stats refresh before article commits
- `[[feedback_hf_readme_positioning]]` — positioning-first card discipline for the harness card
