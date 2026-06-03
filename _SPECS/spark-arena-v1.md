---
project: spark-arena
version: v1.0
status: locked
created: 2026-05-28
authoritative: Spark
---

# Spark Arena v1.0 — Project Specification

> First entry in the new **"Cockpit"** content line — the operator-driven surface a solo Spark
> builder uses to drive every artifact this repo has produced. Sibling to the Hermes
> Harnesses arc: where Hermes is the *agent harness* (Spark answers "how does my agent drive
> the box"), Arena is the *operator harness* (Spark answers "how do *I* drive the box").
> This spec covers v0.1 end-to-end: spec lock → retroactive artifact import → telemetry
> sidecar → chat → side-by-side rubric-scored compare → leaderboard → public mirror, with
> `fieldkit.arena` extensions and a `spark-arena-curator` CC skill keeping the index in sync.

> **Changelog — v0.2 product leap (2026-05-28), branch `arena-v0.2-product-leap`.** Rebrand to
> **Orionfold Arena** (display-only; internal `arena` code surfaces unchanged — resolves the
> spark-arena.com collision). Six surfaces added on top of M1–M6: (1) Models/capabilities
> browser (promoted from the M7 stub; §4.0); (2) cost/quality efficiency frontier on the
> leaderboard (the Pareto frontier §1.3 promised); (3) Compare markdown+highlight parity +
> rubric-derived winner banner + head-to-head delta strip; (4) ⌘K command palette; (5)
> telemetry↔article-evidence bridge on the cockpit; (6) the **Lab** co-iteration board
> (`/arena/lab/`) with an operator-private `lab_notes` annotation layer (new table on
> `FORBIDDEN_TABLES` + the leak-gate). **Distribution decision (amends §3.1 #4):** the runnable
> cockpit's primary distribution surface is now the **`fieldkit[arena]` PyPI wheel** — the web
> UI is baked into the wheel (`fieldkit arena build`) and served by the sidecar's `StaticFiles`
> mount (`fieldkit arena up`); `ainative.business/arena/` serves the same bundle as a public
> web preview. v0.1's "cockpit on 127.0.0.1:7866 only" still holds for the *sidecar*; what
> changed is that the static UI is no longer sync-only — it ships in the package. App
> registered as the first `arena_run` artifact manifest (`src/content/artifacts/orionfold-arena.yaml`).
> Handoffs: `_GUIDES/arena-distribution.md` (publisher) + `_GUIDES/arena-storefront-marketing.md` (marketer).

> **Changelog — M8 control-plane extension (2026-06-02).** Added **§12 — Arena as the control
> plane**, the `_FLOWS/the-machine-that-builds-machines.md` §3 **Phase 1 / Bet 3** milestone:
> promote Arena from recorder → **dispatcher** via a `jobs`/`job_triggers` table + a single-lane
> dispatcher that executes **through the live MCP harness** (`build_mcp_server()`), with
> `eval_rerun` (leaderboard-regression → re-eval) as the first and only real M8 job type and
> `/arena/jobs/` as the cockpit surface. Grounded against `roadmap-reconciliation.md` §"Phase 1"
> (CONFIRMED, operational — connective tissue, not greenfield: the `eval_runs.arq_job_id` socket
> and the 7-tool harness already exist). **Spec only — unbuilt;** Phases 2/3 + cross-cutting
> Bets 5/6 are sequenced to extend this same `jobs` table. Release gate: `fieldkit v0.16.0` (§11).

## 1. Context

### Why this project

Six months of Spark work has accreted real surface: **17 artifact manifests** in
`src/content/artifacts/` (5 quants + 1 LoRA + 2 benches + 3 harnesses + 1 skill + 5 notebook
pairs), **49 published articles** (40 with runnable `evidence/`), **13 HF repositories**
under the `Orionfold/` namespace, and **`fieldkit` v0.13.0** (950 tests, 13 modules, with
`harness` / `eval` / `viz` / `notebook` / `publish` carrying the routing, scoring,
telemetry, and manifest substrate). **None of it has a cockpit** — the place a solo
Spark builder actually drives all of it from. Chat-with-this-quant, side-by-side compare,
"which lane is best for *this* task?", a leaderboard that ranks on quality **and**
efficiency, live telemetry while a session runs, a browseable artifact graveyard, a place
to publish a versioned solo-builder leaderboard — none of these surfaces exist today; the
operator opens five terminals and a manifest file.

**Spark Arena** is that cockpit.

### The "operator cockpit" thesis — sibling to Hermes

The Hermes Harnesses arc (H1–H6 + brain bakeoff, just closed) answered *"how does my agent
drive the box."* Arena answers *"how do *I* drive the box."* They share substrate
(`fieldkit.arena` rides on `fieldkit.harness`'s `serve_lane` + `RouterConfig` +
`CostRouterConfig` and on `fieldkit.eval`'s `Rubric` / `score_answer` / `CheckSpec`), they
share a runtime brain (the Step-2-pinned Qwen3-30B-A3B-Q4_K_M MoE @ 83.5 tok/s on
`llama-server :8080`), and they share the unified-memory envelope guard
(`serve_lane(guard=True, headroom_gb=8.0)` per `[[project_spark_unified_memory_oom]]`).
Arena does not replace Hermes; Arena is the human-driven sibling.

### The "operator harness" thesis vs arena.ai

arena.ai's "Chatbot Arena" pattern (blind battle → Bradley-Terry Elo → public leaderboard)
is intrinsically multi-tenant cloud — it optimizes for crowdsourced vote volume and
external API access to every model. Its 8 differentiator gaps for a solo Spark builder
become Arena's product thesis:

1. **Private eval leaderboards.** Data never leaves the box.
2. **Efficiency-as-metric.** Quality *and* tok/s, unified-mem peak, ttft_ms, $/M — the
   cost-per-quality Pareto frontier arena.ai can't draw because it doesn't know what
   hardware its votes ran on. Spark Arena does, because *the operator is the hardware*.
3. **Closed-loop eval → fine-tune → re-rank.** patent-strategist v1 → v2 → v3 already
   demonstrates this; Arena surfaces version history.
4. **Tool-call + agent replay.** The H4 fieldkit-MCP gate already captures full
   `gate-session.jsonl` traces; arena.ai can't introspect agent loops.
5. **Custom scorers + rubrics.** `fieldkit.eval` ships graded-rubric primitives; Arena
   exposes them as a leaderboard axis.
6. **Telemetry-native cost-aware ranking.** `fieldkit.harness.Telemetry` + H6
   `CostRouterConfig` bind together as first-class leaderboard dimensions.
7. **Reproducibility + versioning.** Every bench is a published HF dataset; every quant is
   a manifest at a fixed commit; Arena gives every leaderboard row a content-addressed ID.
8. **Solo-builder publishing.** Arena is the "publish your model, prove it works, get
   cited" surface for indie Spark builders — the 5 vertical curator quants are the seeded
   evidence base.

### Editorial uber-theme alignment

"DGX Spark as personal AI power user / edge AI builder" gets its strongest expression
yet: the cockpit you can install with `pip install fieldkit[arena] && fieldkit arena serve`
and drive at `http://127.0.0.1:7866/arena/`, fully local, zero cloud, no API key required —
and the leaderboard you publish at `ainative.business/arena/` when you're ready to show your
work. Personal AI, hardware-real, citable.

## 2. Use-case taxonomy — the three pillars

Same D/V/F frame as the Hermes spec. Every Arena surface and every `fieldkit.arena` symbol
maps to at least one pillar; the M7 publish gate checks all three are demonstrated.

**Desirability — one-process cockpit, real-time, beautiful**
- D1. `fieldkit arena serve` + open `http://127.0.0.1:7866/arena/` → telemetry, chat,
  compare, leaderboard, artifact browser all live in one Astro shell.
- D2. Side-by-side rubric-scored compare in under 90 seconds (warm A → stream → swap → warm
  B → stream) with visible per-check `why` strings, not just an opaque vote.
- D3. Live telemetry pane (GPU% / unified-mem / tok/s / ttft / temp) ticking at 500ms
  cadence while a session runs.
- D4. Artifact browser surfaces all 17 manifests + 49 articles on day one — no manual
  registration step.

**Viability — local-first, zero marginal cost, optional bridge**
- V1. Local-only loop = $0 marginal cost; the resident brain is always on; chat history
  never leaves the box.
- V2. Optional OpenRouter bridge for local-vs-frontier compare via the H6
  `CostRouterConfig` — per-call cost recorded, $/quality-point Pareto frontier rendered.
- V3. Reuse of every shipped Orionfold artifact as a lane — zero new training cost, zero
  new manifests required.

**Feasibility — Spark envelope, deterministic compare, leak-proof mirror**
- F1. Single-brain envelope guard (`serve_lane(guard=True, headroom_gb=8.0)`) — exactly
  zero or one local lane shows the `WARM` chip at any moment.
- F2. Rubric-deterministic scoring via `fieldkit.eval.score_answer` — reproducible,
  versioned, no LLM-judge dependency, no blind votes.
- F3. Hardcoded allowlist mirror exporter — `chat_*` tables never enumerated; regression
  test asserts no chat-content string appears in `src/data/arena-mirror/*.json`.

### Deliverables

| Artifact | Surface | Article / Session |
|---|---|---|
| New SERIES `Cockpit` + artifact kind `arena_run` + fieldkit module `arena` | `content.config.ts` + `[series].astro` | M1 |
| `fieldkit.arena` module (server + store + streams + mirror + cli + schemas + jobs) + `docs/api/arena.md` | `fieldkit` PyPI | M1 skeleton → fleshed across M3–M6 |
| `src/pages/arena/` Astro routes + `<TelemetryGauge>` / `<ChatLane>` / `<CompareDuel>` Preact islands + `ArenaLayout.astro` | source Astro site | M1 stubs → M3–M5 fills |
| `~/.fieldkit/arena.db` SQLite schema (lanes, chat, compare, rubric, leaderboard, prefs) | operator-private state | M2 |
| `import_existing.py` retroactive load (17 manifests → SQLite + per-artifact pages) | M2 commit | M2 |
| `src/data/arena-mirror/*.json` static slice + Mac `/sync-field-notes` push to `ainative.business/arena/` | public mirror | M6 |
| `fieldkit` v0.14.0 release cutting the `arena` module + the `arena` extra | PyPI | M7 |
| `articles/introducing-spark-arena-on-spark/` (A1 — the launch piece) | published article | M7 |
| `~/.claude/skills/spark-arena-curator/` CC skill (sibling to `fieldkit-curator`, `hf-publisher`) | CC skill registry | M7 |
| HANDOFF Arena Track + Stop-hook feedback loop into `~/.claude/settings.json` | operator workflow | M7 |

## 3. Decisions

### 3.1 Locked decisions (user-confirmed 2026-05-28)

| # | Decision | Value |
|---|---|---|
| 1 | Stack shape | **Hybrid Astro shell + FastAPI sidecar.** Astro routes under `src/pages/arena/`; Preact islands (`client:only="preact"`) on hot surfaces; FastAPI at `fieldkit/src/fieldkit/arena/server.py` binding `127.0.0.1:7866` (loopback only); SSE streaming throughout; SQLite at `~/.fieldkit/arena.db`; `arq`+Redis for jobs (Redis already on the box for pgvector). |
| 2 | Battle / compare mode | **Rubric-deterministic side-by-side compare, NO blind votes.** `fieldkit.eval.score_answer` over `Rubric` / `CheckSpec` IS the scoring axis. Operator may cast a thumbs-up override recorded as a separate `human_prefs` row that does NOT contaminate `rubric_scores.total`. |
| 3 | v0.1 scope (anchor MVP) | **Chat + side-by-side compare + artifact browser + leaderboard read + telemetry gauge.** Eval-runner, HF publish gate, and cost-routed chat are explicitly v0.2+. |
| 4 | Distribution | **Operator cockpit on Spark `127.0.0.1:7866` only.** Static slice (leaderboard + artifact browser) mirrors to `ainative.business/arena/` via the Mac-side `/sync-field-notes` flow. Distributed for other Spark builders as `pip install fieldkit[arena]` + `fieldkit arena serve` CLI. |
| 5 | Category shape | New **SERIES `Cockpit`**, NOT a new STAGE (Frontier Scout / Harnesses precedent). Sibling to Harnesses, not a sub-arc of it. |
| 6 | New artifact kind | **`arena_run`** (9th kind alongside `quant, lora, adapter, dataset, bench, notebook, harness, skill`). Backwards-compatible additive change to `ARTIFACT_KINDS`. |
| 7 | Resident brain | The Step-2 pinned **Qwen3-30B-A3B-Q4_K_M MoE** at `llama-server :8080` (83.5 tok/s, 31.8 GB unified). Arena reads `~/.hermes/config.yaml` as the truth-of-current-lane. |
| 8 | Default compare B-lane | **OpenRouter via H6 `CostRouterConfig`** (no concurrent local warm). Explicit "two local lanes" mode triggers the visible warm-A → stream → swap → warm-B → stream sequence. |
| 9 | Generation boundary | `fieldkit.arena` is **deterministic Python only**; all LLM generation (rubric prompts at v0.2, prose) stays in session-driven skills per `[[feedback_llm_skill_pattern]]`. |
| 10 | Scorer reuse discipline | Ad-hoc rubrics live at `~/.fieldkit/arena/rubrics/` until a **2nd reuse** triggers promotion to `fieldkit/src/fieldkit/eval/rubrics/` per `[[feedback_keep_scorer_local_until_reuse]]`. |

### 3.2 SERIES not STAGE — justification

Same logic as Harnesses (precedent). STAGES are pipeline phases of working with a model
(`foundations → training → fine-tuning → inference → deployment → agentic → observability
→ dev-tools`). Arena threads through `dev-tools` and `agentic` but introduces no new
*phase of ML work*. Adding a `cockpit` stage would orphan Arena articles from the stage
pages where readers look for serving and tooling content, and would be the only stage
named after a product line rather than a workflow phase — breaking the taxonomy's logic.
**Cockpit** is a SERIES (sibling to **Harnesses**), mapped to existing stages.

### 3.3 Stack matrix — why each piece

| Layer | Choice | Why |
|---|---|---|
| Astro shell | extend existing site at `src/pages/arena/` | reuses dark-OKLCH + Geist brand, `BaseLayout.astro`, content collections; produces a static slice publishable via existing Mac sync; islands handle the interactive surface without forking the site |
| Islands | **Preact** `client:only` | smallest hydration footprint; matches existing brand JS budget; never SSRs (sidecar isn't available at build time) |
| Sidecar | **FastAPI** at `127.0.0.1:7866` | Python-native (fieldkit is Python); SSE + lifespan + pydantic schemas first-class; OpenAI-compat patterns are copy-paste; aarch64-friendly |
| Streaming | **SSE** (sse-starlette) | one-way (server→client), CORS-friendly, survives proxies, browser-native `EventSource`; chat tokens + telemetry + compare events all use the same shape |
| Lane I/O | **OpenAI-compat HTTP** to existing `llama-server :8080` / NIM :8000 / OpenRouter | reuses what's already running; no new lane infrastructure; H6 `CostRouterConfig` already wraps the routing logic |
| Persistence | **SQLite** (`aiosqlite`) at `~/.fieldkit/arena.db`, WAL mode | one file, portable, gitignore-friendly, queryable; replay via schema dumps; survives restarts |
| Jobs (v0.2 wires) | **`arq` + Redis** (Redis already on box for pgvector) | async-native, FastAPI-friendly, durable, ~50 LOC worker; v0.1 makes Redis runtime-optional |
| Charts | **uPlot** (35 KB, canvas-only, no React dep) for live telemetry; `fieldkit.viz` great_tables for static leaderboard | ARM-friendly, 60fps on 10k points; mixed-by-use-case |
| Mirror | static export to `src/data/arena-mirror/*.json` consumed at build time | zero new sync wiring — Mac `/sync-field-notes` picks up files already in the source tree |

### 3.4 Naming

- Series display name: **`Cockpit`**; slug `cockpit` (`/series/cockpit/`).
- Routes: under `/arena/` only (NOT `/cockpit/` — the cockpit is what Arena *is*).
- Python module: **`fieldkit.arena`**.
- pyproject extra: **`arena`**.
- CLI: **`fieldkit arena {serve, import, mirror, memcheck, rebuild-leaderboard, promote-run}`**.
- Default port: **7866** (mnemonic: Spark+Arena reads; free across the existing port map of
  llama-server :8080, NIM :8000, pgvector :5432, Astro dev :4321, Redis :6379).
- SQLite path: **`~/.fieldkit/arena.db`** (operator-private, NOT in repo).
- HF dataset (publishable slice, v0.2 push): **`Orionfold/spark-arena-leaderboard-v0.1`**.
- CC skill: **`spark-arena-curator`** (sibling to `fieldkit-curator`, `hf-publisher`).
- Spec path: **`_SPECS/spark-arena-v1.md`** (this file).
- Ideas doc: **`ideas/spark-arena.md`**.
- First article slug: **`articles/introducing-spark-arena-on-spark/`**.

## 4. Architecture

### 4.0 Astro route map (`src/pages/arena/`)

All routes statically exportable; every hot island declared `client:only="preact"` so it
never SSRs (the sidecar isn't available at build time).

| URL | Page file | Static vs Island | Source data | Sidecar endpoint(s) | MVP / v0.2 |
|---|---|---|---|---|---|
| `/arena/` | `index.astro` | static shell + `<TelemetryGauge>` + `<RecentCompares>` | active lane (`~/.hermes/config.yaml`); recent 5 compare rows from mirror JSON | `GET /api/telemetry/stream`, `GET /api/leaderboard?limit=5` | MVP |
| `/arena/chat/` | `chat.astro` | static shell + `<ChatLane>` | active lane | `POST /api/chat/stream`, `POST /api/lanes/swap`, `GET /api/lanes` | MVP |
| `/arena/compare/` | `compare.astro` | static shell + `<CompareDuel>` | lane picker from `getCollection('artifacts')`; rubric picker from `GET /api/rubrics` | `POST /api/compare/stream`, `POST /api/lanes/swap` | MVP |
| `/arena/leaderboard/` | `leaderboard/index.astro` | static | `src/data/arena-mirror/leaderboard.json` (build-time read) | — | MVP |
| `/arena/leaderboard/[bench]/` | `leaderboard/[bench].astro` | static | per-bench slice | — | MVP |
| `/arena/models/` | `models/index.astro` | static | `getCollection('artifacts')` where `kind in ('quant','lora','adapter')` | — | MVP |
| `/arena/models/[slug]/` | `models/[slug].astro` | static + optional `<LaneSwapButton>` island | one manifest + leaderboard rollup; links OUT to Mac-owned `/artifacts/<kind>/<slug>/` for canonical catalog | `POST /api/lanes/swap?slug=…` (island-only) | MVP |
| `/arena/benches/` (+ `[slug]`) | `benches/*.astro` | static | `getCollection('artifacts')` where `kind=='bench'` + cached results JSON | — | MVP |
| `/arena/harnesses/` (+ `[slug]`) | `harnesses/*.astro` | static + (v0.2) `<HarnessApplyButton>` | the 3 spark-hermes-* manifests | `POST /api/harnesses/{slug}/apply` (v0.2) | MVP shell |
| `/arena/skills/` | `skills/index.astro` | static | `kind=='skill'` | — | MVP |
| `/arena/notebooks/` (+ `[vertical]`) | `notebooks/*.astro` | static | `kind=='notebook'` + cached PNG exports | — | MVP |
| `/arena/articles/` | `articles/index.astro` | static filtered cross-link | `getCollection('articles')` sliced to harness/eval/viz/manifested | — | MVP |
| `/arena/evals/` (+ `[run]`) | `evals/*.astro` | static shell + `<EvalReplay>` island | `eval_runs` table | `GET /api/runs`, `GET /api/runs/{id}/stream` | v0.2 |
| `/arena/publish/` | `publish.astro` | static shell + `<PublishGate>` | publishable slice preview | `POST /api/publish/hf-dataset` | v0.2 |

**Layout:** new `src/layouts/ArenaLayout.astro` (source-side; thin shell over
`BaseLayout.astro` adding the cockpit nav). Mac mirrors via the standard
`mirror: destination-overrides update` PR loop.

**Folding `/articles/` decision.** Keep root `/articles/<slug>/` URL intact (Mac-mirrored,
many inbound links). Add `/arena/articles/` as a *filtered cross-link surface* over the
same `getCollection('articles')` source. No URL collision.

**`/arena/models/[slug]/` boundary.** The `/artifacts/<kind>/<slug>/` URL space is the
**canonical catalog surface**. Arena's per-model pages are the **cockpit surface**
(chat-with-this-model, run-rubric, telemetry-while-warm) and **link OUT** to the catalog
for canonical detail. No chrome collision.

### 4.1 Cockpit landing — `/arena/`

The first page the operator sees. Two-row layout: top row = telemetry strip
(`<TelemetryGauge>` island, 6 metrics, ticking at 500ms); middle row = current lane card
(reads `~/.hermes/config.yaml` for the warm brain; shows its manifest slug + uptime);
bottom row = the 5 most recent compare rows (from
`src/data/arena-mirror/leaderboard.json`). One-click jumps to `/arena/chat/` or
`/arena/compare/`. Renders gracefully on the public mirror ("Cockpit offline — visit your
Spark at `127.0.0.1:7866`") when not on loopback.

### 4.2 Chat — `/arena/chat/`

Single-lane chat against the active brain. `<ChatLane>` Preact island POSTs to
`/api/chat/stream`. Token-streaming via SSE. Optional `rubric_id` query → a `score` SSE
event fires after the response completes, with per-check pass/fail + `why` strings.
History persists to `chat_sessions` + `chat_turns` tables (**operator-private; NEVER
mirrored**; default `publishable=0`).

Reuses `fieldkit.notebook.OpenAICompatClient`, `split_think` (per
`[[feedback_nim_think_prefix_convention]]`), and `stream_reply`. The `<think>` prefix is
captured in the `chat_turns.reasoning` column so the UI can collapse it.

### 4.3 Compare — `/arena/compare/`

The cockpit's centerpiece. Side-by-side rubric-scored compare. `<CompareDuel>` Preact
island POSTs to `/api/compare/stream`. Default B-lane = OpenRouter via the H6
`CostRouterConfig` (no concurrent local warm — safe by construction). Explicit "two local
lanes" mode triggers the warm-A → stream → swap → warm-B → stream sequence with a visible
`swap` SSE event between A's `done` and B's `start`.

**Sequence (single SSE for the whole flow):**
1. `start_a` `{lane, lane_id}`. The Qwen3 lane is stopped (was warm). Lane A is warmed via
   `serve_lane(spec_a, guard=True, headroom_gb=8.0)`.
2. Stream A's response (`token_a` events; `<think>` in `reasoning` channel).
3. `done_a` `{tokens_out, ttft_ms, tok_per_s, unified_peak_gb}`.
4. `swap` `{from, to, headroom_gb}` — only on explicit two-local-lanes mode.
5. `start_b`, stream B, `done_b`.
6. `score` event: `{rubric_id, a: {score, checks: [{name, ok, why}]}, b: {…}, deltas:
   {score, speed_tok_per_s, headroom_gb}}`.

**Rubric pick.** `<CompareDuel>` fetches `GET /api/rubrics` on mount. Defaults: `generic-
correctness` (substring + non-hedge + length); patent prompts default to
`patent_claim_validity`; cyber → `mcq_letter`. Operator can override per-compare.

**Persistence.** Server inserts `compare_runs` (publishable=1 by default), 2×
`compare_responses`, 2× `rubric_scores`, and updates the denormalized `leaderboard_rows`
read-model. Operator thumbs-up fires `POST /api/prefs` which writes `human_prefs` — a
**separate signal**, never mutating `rubric_scores.total`.

### 4.4 Leaderboard — `/arena/leaderboard/` + `/arena/leaderboard/[bench]/`

Static pages built from `src/data/arena-mirror/leaderboard.json`. Two tabs: **Bench-anchored**
(rows pulled from cached bench evidence — patent-strategist-bench, hermes-brain-bench, +
future) and **Live cockpit runs** (rows pulled from `compare_runs` + `rubric_scores`).
Sort by quality / tok/s / unified-mem / $/M; filter by manifest_slug / kind / bench.

Mac-side build picks up the mirror JSON during the Astro build; the public mirror at
`ainative.business/arena/leaderboard/` ships the same view, no live data needed.

### 4.5 Browser surfaces — models / benches / harnesses / skills / notebooks / articles

Each is a static index over `getCollection('artifacts')` filtered to a kind. Per-slug
detail pages render from the manifest YAML directly (positioning block + variants +
license + known_drift + recommended_variant + notebooks badge row). Detail pages **link
OUT** to the Mac-owned `/artifacts/<kind>/<slug>/` for the canonical catalog rendering.

`/arena/articles/` is a filtered cross-link surface — not a duplicate of `/articles/`. The
filter: articles whose `fieldkit_modules` touches `harness`, `eval`, `viz`, `arena`, or
which produced a Phase-1 artifact.

### 4.6 Telemetry pane

`<TelemetryGauge>` Preact island, embedded in `/arena/`, `/arena/chat/`, and
`/arena/compare/`. Subscribes to `GET /api/telemetry/stream` SSE; receives one event per
~500ms tick:

```
event: telemetry
data: {"ts":"2026-05-28T15:32:11.504Z","gpu_util":68,"gpu_temp_c":73,
       "unified_used_gb":31.7,"unified_total_gb":119.5,"tok_per_s":83.4,
       "ttft_ms":462,"inflight":true,"lane_id":"llama-qwen3-30b-a3b"}
```

Idle ticks omit `tok_per_s`/`ttft_ms`, set `inflight: false`, emit only ambient values.
**Cadence rationale:** 500ms is the floor below which `nvidia-smi --query-gpu` reads add
measurable cost on GB10 (each call ~80ms). `fieldkit.harness.Telemetry` defaults to 2s;
Arena passes `interval=0.5` and accepts the slightly higher CPU cost while a subscriber is
open. **Zero background load when the cockpit is closed** (lifespan tracks subscribers; no
subscribers → `Telemetry.stop()`).

**Rendered columns:** GPU% (green ≤80 / yellow 80–95 / red ≥95), GPU °C (yellow ≥80 / red
≥90), Unified (`used / total` with a band at `total - 8 = ~120 GB` showing the guard
headroom), Tok/s (only when `inflight=true`; otherwise dash), TTFT (sticky from previous
`done` event), Lane chip (clicking → `/arena/models/<slug>` if the lane has a manifest
slug).

**Chart library: uPlot** (locked). 35 KB minified, no React/Preact dep, plain canvas;
renders on ARM with no SIMD-shim surprises; draws 10k points at 60fps. Wrapped in a thin
Preact island.

### 4.7 `fieldkit.arena` — public API surface

New submodule `fieldkit/src/fieldkit/arena/`. Idiomatic to the package: `from __future__
import annotations`, frozen/plain dataclasses, context managers, lazy imports (`import
fieldkit.arena` stays cheap; `fastapi` only loaded when `create_app()` is called),
`ArenaError` base, deterministic mirror output, hand-rolled YAML for any config rendering
via `publish`'s stdlib emitter (no new YAML dep).

```
fieldkit/src/fieldkit/arena/
  __init__.py        # __all__, version pin, lazy re-exports
  schemas.py         # pydantic request/response (Lane, ChatRequest, CompareRequest, …)
  models.py          # plain dataclasses (LaneRecord, LeaderboardRow, RubricScoreRecord, …)
  store.py           # aiosqlite layer (initialize / read-models / rebuild_leaderboard /
                     #   insert_human_pref / export_publishable_slice)
  streams.py         # sse-starlette helpers (sse_event, heartbeat, token-stream adapter,
                     #   telemetry pump)
  server.py          # FastAPI app factory + routers + lifespan (warms lane registry
                     #   from ~/.hermes/config.yaml + toggle-script scan)
  jobs.py            # arq worker stubs (v0.2: run_bench, refresh_leaderboard, mirror_export)
  mirror.py          # SQLite → src/data/arena-mirror/*.json with allowlist guard
  cli.py             # `fieldkit arena {serve,import,mirror,memcheck,
                     #   rebuild-leaderboard,promote-run}` (Typer)
  data/
    rubrics-default.yaml    # default rubric registry (id → rubric md path)
  scripts/
    import_existing.py      # M2 retroactive load
```

Proposed `__all__` (v0.1):

```python
__all__ = [
    # sidecar lifecycle
    "create_app", "serve",
    # store
    "ArenaStore",
    "LaneRecord", "ChatTurnRecord", "CompareRunRecord", "RubricScoreRecord",
    "LeaderboardRow", "HumanPrefRecord",
    # mirror
    "export_publishable_slice", "rebuild_leaderboard",
    # errors
    "ArenaError", "LaneNotRegistered", "PublishableSliceEmpty",
]
```

**Reuse — fieldkit symbols Arena calls into, never duplicates:**

| Symbol | Source file | What Arena uses it for |
|---|---|---|
| `serve_lane(spec, guard=True, headroom_gb=8.0)` | `fieldkit/src/fieldkit/harness/brains.py` | every lane swap goes through this; the only enforcer of the single-brain envelope; raises `UnifiedMemoryExceeded` cleanly |
| `NIMLane`, `LlamaServerLane`, `VLLMLane`, `OllamaLane`, `LaneSpec`, `resolve_lane` | `fieldkit.harness` | lane lifecycle (start/health/teardown including the vLLM EngineCore orphan sweep per `[[feedback_vllm_engine_core_orphan]]`) |
| `Telemetry`, `measure_throughput` | `fieldkit.harness` | the GPU% / unified-mem / temp / tok/s / ttft sampler |
| `CostRouterConfig`, `RouteTier`, `estimate_tokens`, `build_cost_router` | `fieldkit.harness` | powers the default Compare B-lane (OpenRouter via tier predicates) |
| `RouterConfig`, `build_vertical_router`, `VerticalRoute` | `fieldkit.harness` | the H5 vertical router — Arena surfaces it as the v0.2 "route this compare per-vertical" mode |
| `score_answer`, `Rubric`, `CheckSpec`, `GradedPromptSuite`, `load_rubric`, `HEDGE_PHRASES`, `extract_last_json` | `fieldkit.eval` | every rubric score event; the deterministic scoring axis |
| `Bench`, `Judge`, `PassAtK`, `VerticalBench` | `fieldkit.eval` | v0.2 eval-runner pane |
| `OpenAICompatClient`, `split_think`, `stream_reply`, `discover_local_server` | `fieldkit.notebook` | chat client forwarding; `<think>` prefix split |
| `ArtifactManifest`, `ArtifactKind`, `ORIONFOLD_HF_HANDLE`, `write_artifact_manifest` | `fieldkit.publish` | read-only; drives artifact browser; v0.2 HF dataset push reuses `HFHubAdapter` |
| `fieldkit.viz` chart helpers | `fieldkit.viz` | v0.2 server-side leaderboard PNG render for HF dataset card |
| `Capabilities.load()`, `weight_bytes`, `kv_cache_bytes` | `fieldkit.capabilities` | the `serve_lane` guard's memory math |

**No new scorer surface in v0.1.** Per `[[feedback_keep_scorer_local_until_reuse]]` ad-hoc
rubrics stay at `~/.fieldkit/arena/rubrics/` until a 2nd reuse triggers promotion to
`fieldkit/src/fieldkit/eval/rubrics/`.

**`pyproject.toml` extra** (additive to existing `dev`, `notebook`, `harness`):

```toml
arena = [
  "fastapi>=0.115",
  "uvicorn[standard]>=0.30",
  "sse-starlette>=2.1",
  "aiosqlite>=0.20",
  "arq>=0.26",         # v0.2 wires jobs; install in v0.1 for forward compat
  "redis>=5.0",        # ditto; runtime-optional in v0.1 (sidecar logs warning + disables /api/runs)
  "huggingface_hub>=0.24",
  "pyyaml>=6.0",
]
```

Add `'arena'` to `FIELDKIT_MODULES` and ship `fieldkit/docs/api/arena.md` (the curator
`audit-docs` diffs `__all__` against the api page, so the page is required at release).

### 4.8 SQLite schema (`~/.fieldkit/arena.db`)

Single file, WAL mode (`PRAGMA journal_mode=WAL`), foreign keys on. `PRAGMA user_version=1`
for forward migration. Created lazily on first sidecar boot via `ArenaStore.initialize()`
(idempotent `CREATE TABLE IF NOT EXISTS`).

```sql
CREATE TABLE lanes (
  id              TEXT PRIMARY KEY,
  kind            TEXT NOT NULL,               -- 'NIMLane'|'LlamaServerLane'|'VLLMLane'|'OllamaLane'
  model           TEXT NOT NULL,
  port            INTEGER NOT NULL,
  base_url        TEXT NOT NULL,
  start_script    TEXT,
  stop_script     TEXT,
  manifest_slug   TEXT,
  recommended     INTEGER NOT NULL DEFAULT 0,
  last_warm_at    TEXT,
  last_swap_at    TEXT,
  notes           TEXT
);

CREATE TABLE chat_sessions (
  id              TEXT PRIMARY KEY,
  lane_id         TEXT NOT NULL REFERENCES lanes(id),
  created_at      TEXT NOT NULL,
  rubric_id       TEXT,
  publishable     INTEGER NOT NULL DEFAULT 0   -- operator-private by default
);

CREATE TABLE chat_turns (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  session_id      TEXT NOT NULL REFERENCES chat_sessions(id) ON DELETE CASCADE,
  ord             INTEGER NOT NULL,
  role            TEXT NOT NULL,
  content         TEXT NOT NULL,
  reasoning       TEXT,                        -- <think> prefix split per fieldkit.notebook.split_think
  tokens_in       INTEGER,
  tokens_out      INTEGER,
  ttft_ms         REAL,
  tok_per_s       REAL,
  finish_reason   TEXT,
  created_at      TEXT NOT NULL,
  UNIQUE (session_id, ord)
);

CREATE TABLE compare_runs (
  id              TEXT PRIMARY KEY,
  prompt          TEXT NOT NULL,
  rubric_id       TEXT NOT NULL,
  lane_a_id       TEXT NOT NULL REFERENCES lanes(id),
  lane_b_id       TEXT NOT NULL REFERENCES lanes(id),
  created_at      TEXT NOT NULL,
  publishable     INTEGER NOT NULL DEFAULT 1,
  redacted_prompt TEXT                         -- operator opt-in; only this leaks to mirror
);

CREATE TABLE compare_responses (
  compare_run_id  TEXT NOT NULL REFERENCES compare_runs(id) ON DELETE CASCADE,
  side            TEXT NOT NULL CHECK (side IN ('A','B')),
  lane_id         TEXT NOT NULL REFERENCES lanes(id),
  content         TEXT NOT NULL,
  reasoning       TEXT,
  tokens_out      INTEGER,
  ttft_ms         REAL,
  tok_per_s       REAL,
  unified_peak_gb REAL,
  PRIMARY KEY (compare_run_id, side)
);

CREATE TABLE rubric_scores (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  compare_run_id  TEXT REFERENCES compare_runs(id) ON DELETE CASCADE,
  chat_turn_id    INTEGER REFERENCES chat_turns(id) ON DELETE CASCADE,
  side            TEXT,
  rubric_id       TEXT NOT NULL,
  total           REAL NOT NULL,
  checks_json     TEXT NOT NULL,               -- shape mirrors eval.CheckResult: [{name, kind, ok, why}, …]
  scored_at       TEXT NOT NULL,
  CHECK ((compare_run_id IS NOT NULL) OR (chat_turn_id IS NOT NULL))
);

CREATE TABLE leaderboard_rows (
  bench_id        TEXT NOT NULL,
  lane_id         TEXT NOT NULL REFERENCES lanes(id),
  manifest_slug   TEXT,
  n_runs          INTEGER NOT NULL,
  mean_score      REAL NOT NULL,
  median_tok_per_s REAL,
  mean_ttft_ms   REAL,
  human_pref_winrate REAL,                     -- nullable; meaningful at ≥5 prefs
  last_run_at     TEXT NOT NULL,
  PRIMARY KEY (bench_id, lane_id)
);

CREATE TABLE human_prefs (
  id              TEXT PRIMARY KEY,
  compare_run_id  TEXT NOT NULL REFERENCES compare_runs(id) ON DELETE CASCADE,
  winner          TEXT NOT NULL CHECK (winner IN ('A','B','tie')),
  note            TEXT,
  created_at      TEXT NOT NULL
);

-- v0.2:
CREATE TABLE eval_runs (
  id              TEXT PRIMARY KEY,
  bench_id        TEXT NOT NULL,
  lane_id         TEXT NOT NULL REFERENCES lanes(id),
  status          TEXT NOT NULL,
  enqueued_at     TEXT NOT NULL,
  started_at      TEXT,
  finished_at     TEXT,
  result_json     TEXT,
  arq_job_id      TEXT
);
```

**Publishable vs operator-only split** (load-bearing for §4.10 mirror safety):

- **Publishable to HF dataset + static mirror:** `compare_runs` (with `publishable=1` and
  only the `redacted_prompt` column, never `prompt`); `compare_responses`; `rubric_scores`;
  `leaderboard_rows`; `human_prefs`; `lanes` table publishes only
  `(id, kind, model, manifest_slug, recommended)`.
- **Operator-only, NEVER mirrored:** `chat_sessions`, `chat_turns`. The mirror exporter
  in `mirror.py` enforces a hardcoded table+column allowlist; `chat_*` tables are NEVER
  enumerated. Regression test
  `fieldkit/tests/arena/test_mirror_does_not_leak.py` asserts no row in the JSON output
  contains text from any `chat_turns.content`.

### 4.9 Single-brain envelope guard UX

Hard rule (128 GB unified mem per `[[project_spark_unified_memory_oom]]`): exactly **zero
or one** lane shows the `WARM` chip. Every swap routes through
`serve_lane(spec, guard=True, headroom_gb=8.0)`. Cockpit UI rules:

- The "warm" button on a `COLD` row, when clicked, runs **swap, not co-warm** — the
  FastAPI handler stops the prior warm lane before warming the new one. Same pattern as
  the existing `articles/picking-the-hermes-brain-on-spark/evidence/start-nim.sh` which
  calls `stop-llama-moe.sh` first.
- The lane-swap button has inline confirm-on-second-click (4s window). Prevents
  fat-finger swaps during open SSE streams.
- During an open chat stream, lane-swap blocks until the active stream's `done` event has
  flushed (or 2s timeout). UI shows: "A chat stream is active — swap will start in ~1s."
- `UnifiedMemoryExceeded` during the second warm of a compare → SSE emits `error
  {reason: 'envelope_exceeded', headroom_gb: -3.1}`; cockpit shows a yellow banner.

**Two compare flows:**

1. **Default** (local vs frontier): only one local lane warm; B is OpenRouter
   over-the-wire (no additional unified-memory cost). Safe by construction.
2. **Explicit "two local lanes"** (v0.1 gated behind an advanced toggle): single SSE for
   the whole sequence — `start_a` → stream → `done_a` → `swap` event with countdown →
   `start_b` → stream → `done_b` → `score`. Operator sees a visible 30–90s swap gap with
   "Swapping brain… (47s, 12 GB freed → 28 GB warming)" driven by `Telemetry`.

### 4.10 Static mirror to `ainative.business/arena/`

**What gets exported to `dist/arena/` at Astro build time** (zero new sync wiring; the Mac
`/sync-field-notes` skill picks up files already in the source tree):

| Path | Source | Generation |
|---|---|---|
| `index.html`, `chat/`, `compare/` | Astro static build | island JS bundled but emits "Cockpit offline" on the public mirror (detect via `window.location.hostname !== '127.0.0.1'`) |
| `leaderboard/*.html` | reads `src/data/arena-mirror/leaderboard.json` | fully static |
| `models/*`, `benches/*`, `harnesses/*`, `skills/*`, `notebooks/*`, `articles/*` | `getCollection('artifacts')` + cached JSON | fully static |

**Build inputs.** The `/arena/**` static surface is built in this monorepo directly from
`src/pages/arena/**` + `src/data/arena-mirror/**` + `ArenaLayout.astro`. (Pre-cutover this
was a Mac `/sync-field-notes` handshake; under the monorepo it's just part of the site build.)

**SQLite → JSON serialization.** `fieldkit arena mirror` CLI runs
`store.export_publishable_slice()` into `src/data/`. Triggers:

- Manually from the operator: `fieldkit arena mirror`.
- Automatically from `spark-arena-curator cut-mirror` mode.
- As an Astro build prehook (`prebuild`: `fieldkit arena mirror || true` — `|| true` so a
  missing sidecar doesn't break the Mac build).

**PII safety.** `mirror.py` writes to `src/data/arena-mirror/_staging/` first, runs the
schema-allowlist validator, then **atomically renames** to the final path. The Mac's
`/sync-field-notes` is contracted to only read settled files (already its convention per
`[[reference_sync_workflow_nfs_mount]]`).

## 5. Pillar-realization commitments

The measurable commitments that decide whether each pillar is actually demonstrated.

| Pillar | Metric | Target / gate |
|---|---|---|
| Desirability | time-to-first-cockpit-page | `fieldkit arena serve` → `http://127.0.0.1:7866/arena/` returns 200 in < 5s on warm sidecar |
| Desirability | TTFT (chat) | < 5s on warm Qwen3-30B-A3B brain (matches H5 measurement) |
| Desirability | side-by-side compare wall | < 90s including warm-A → swap → warm-B for two-local-lanes mode; < 15s for local-vs-OpenRouter mode |
| Desirability | telemetry cadence | 500ms tick while subscriber open; zero-emit when idle |
| Viability | local marginal cost | $0 (chat + telemetry + local compare lane) — stated and shown on the cockpit landing |
| Viability | cost-routed B-lane | per-call cost recorded from OpenRouter `usage` block; rendered on every compare row |
| Feasibility | unified-memory headroom | every documented lane stays inside 128 GB with `serve_lane(guard=True)` enforcing |
| Feasibility | mirror leak gate | `pytest fieldkit/tests/arena/test_mirror_does_not_leak.py` passes; zero `chat_turns.content` strings in any mirror JSON |
| Feasibility | rubric reproducibility | running the same compare twice (same lane, same rubric, same seed where applicable) produces deterministic `rubric_scores.checks_json` |
| Feasibility | fresh-venv install | `pip install fieldkit[arena]==0.14.0` on a fresh aarch64 venv succeeds; `fieldkit arena serve` boots without manual dep fixes |

## 6. Curator + skill ecosystem

### 6.1 `spark-arena-curator` CC skill

Sibling to `fieldkit-curator` and `hf-publisher`. **Location:**
`~/.claude/skills/spark-arena-curator/SKILL.md` (CC-side only; **NOT** in source-side
`skills/` per Phase-3 correction — source `skills/` is exclusively for published
agentskills.io artifacts like `spark-serve` and `vertical-route`).

**Honors `[[feedback_llm_skill_pattern]]`:** scripts are deterministic only; the session
model drives via Edit/Bash — no `anthropic` / `claude-agent-sdk` import anywhere in
`scripts/`.

**Modes** (mirror `fieldkit-curator` pattern):

- `import-new` — scan for artifacts not yet in `arena.db`; register lanes; append a HANDOFF
  amendment under the Arena Track section.
- `refresh-leaderboard` — re-pull bench JSONs; recompute leaderboard; write mirror JSON.
- `index-article` — write Arena cross-link block for a new article.
- `cut-mirror` — full `fieldkit arena export-mirror` → validate → ready for
  `/sync-field-notes`.
- `audit` — three-way drift report (manifests ↔ `arena.db` ↔ rendered pages); emits
  HANDOFF "feature-signal queue" entries for v0.2 backlog ideas surfaced during the scan.

**Scripts:**

```
~/.claude/skills/spark-arena-curator/scripts/
  scan_artifacts.py        # walks src/content/artifacts/*.yaml; diffs vs arena.db.lanes
  scan_evidence.py         # walks articles/*/evidence/start-*.sh; parses lane shape
  register_lane.py         # INSERT OR REPLACE into lanes table
  rebuild_mirror.py        # invokes `fieldkit arena mirror`
  write_handoff_entry.py   # appends to HANDOFF.md under the anchor "## 🏟️ ARENA TRACK"
  verify_drift.py          # asserts arena.db.lanes == src/content/artifacts/ + ~/.hermes/config.yaml
```

### 6.2 Handshake with `fieldkit-curator`

When `fieldkit-curator release` cuts a minor bump that touches `fieldkit.arena.__all__`,
the curator audit-docs step requires `fieldkit/docs/api/arena.md`. The
`spark-arena-curator` skill is invoked once after a release lands to verify
`audit-docs arena/N` is clean.

### 6.3 Handshake with `hf-publisher`

When v0.2 ships the publishable slice as `Orionfold/spark-arena-leaderboard-v0.1`,
`hf-publisher` is the publishing surface (same as the benches and harness profiles).
`spark-arena-curator cut-mirror` produces the staged data; `hf-publisher` pushes.

### 6.4 Handshake with `tech-writer`

When a new article ships that produced (or references) an Arena-visible artifact, the
`spark-arena-curator index-article` mode writes the cross-link block. No prose generation
— template render only.

### 6.5 Feedback loop — `Stop` hook in `~/.claude/settings.json`

Per `[[feedback_terminal_bang_unavailable]]` no terminal `!` hooks. The harness-executed
`Stop` hook in `~/.claude/settings.json` runs:

```json
{
  "hooks": {
    "Stop": [{
      "matcher": ".*",
      "hooks": [{
        "type": "command",
        "command": "cd /home/nvidia/ainative-business.github.io && /home/nvidia/.local/bin/fieldkit arena audit --quiet --since-last-stop --emit-handoff-block || true"
      }]
    }]
  }
}
```

Near-zero cost on sessions that didn't touch `src/content/artifacts/` or `articles/` (the
script's first action is a git-log check; if no relevant paths changed, exit 0). Appends a
one-line bullet to the HANDOFF Arena Track "This-session Arena amendments" subsection when
artifacts move. The `|| true` ensures Arena audit failures NEVER block a Stop.

Operator opt-in at M7 cutover.

## 7. Phase-1 inventory — the retroactive load

The M2 `scripts/import_existing.py` walks these sources to populate `~/.fieldkit/arena.db`
on first run:

| Source | Reader | What it yields |
|---|---|---|
| `src/content/artifacts/*.yaml` (17 manifests) | `pyyaml` | one `lanes` row per quant/lora/harness; metadata; manifest_slug joins |
| `articles/<slug>/evidence/*_results.json` (40 evidence dirs) | filename convention | `bench_results` rows — `core_pass_rate`, `consistency`, `runaway_rate`, `wall_mean_s`, `tok_per_sec`, `p50_s`, `p95_s`, `gpu_util_mean`, `unified_used_gb_max` per `(bench_slug, variant_label)` |
| `articles/*/article.md` frontmatter (49 articles) | the existing remark-frontmatter pipeline | `article_index` rows — `slug, title, series, stage, customer_linked, published_at, referenced_artifact_slugs[]` |
| HF API (13 repos under `Orionfold/`) | `huggingface_hub.HfApi.repo_info` (cached 24h to `~/.fieldkit/arena_cache/hf/<repo>.json`) | `hf_meta` rows — `downloads, likes, last_modified, has_card` |
| `notebooks/<vertical>/exports/*.png` (5 verticals × N files) | filesystem glob | `notebook_export` rows — joins to artifact via the notebook manifest |
| `~/.hermes/config.yaml` + toggle scripts | one-off scan | `lanes` table population for the resident brain + the 3 toggle-script-derived lanes |
| `articles/picking-the-hermes-brain-on-spark/evidence/hermes_brain_results.json` | direct read | the seeded first-leaderboard cut (3 lanes × 8 prompts × N=5) |

**Outputs:**
- ~17 `lanes` rows (one per quant/lora/harness manifest, plus the resident brain).
- ~10+ `bench_results` rows (the per-variant rollup from the 2 published benches).
- 49 `article_index` rows.
- ~25 `notebook_export` rows.
- A first leaderboard cut written to `src/data/arena-mirror/leaderboard.json` so the
  leaderboard ships non-empty on day one.

**Backwards-compat — no manifest schema bump required.** The current bench manifests carry
the minimum (`hermes-brain-bench-v0.1.yaml` is 8 lines); their results live in the article's
`evidence/` JSON, not the manifest. M2's import script uses a deterministic convention:
`articles/<article-slug-from-yaml-`article:`>/evidence/*_results.json`. The 2 benches in
the wild work under this convention without needing manifest edits. An optional `bench_meta`
block can be added later if a bench wants to declare result file paths explicitly.

## 8. Schema edits + `content.config.ts` deltas

All three edits land in a single M1 commit:

```ts
// 1. Add `arena_run` to ARTIFACT_KINDS (9th kind)
export const ARTIFACT_KINDS = [
  'quant', 'lora', 'adapter', 'dataset', 'bench',
  'notebook', 'harness', 'skill',
  'arena_run',
] as const;

// 2. Add `arena` to FIELDKIT_MODULES (13th module)
export const FIELDKIT_MODULES = [
  'capabilities', 'nim', 'rag', 'eval', 'training', 'lineage',
  'quant', 'publish', 'cli', 'viz', 'notebook', 'harness',
  'arena',
] as const;

// 3. Add `Cockpit` series (8th)
export const SERIES = [
  'Foundations', 'Second Brain', 'LLM Wiki',
  'Machine that Builds Machines', 'Looking Beyond Spark',
  'Frontier Scout', 'Harnesses',
  'Cockpit',
] as const;
export const SERIES_SLUGS: Record<(typeof SERIES)[number], string> = {
  ..., 'Cockpit': 'cockpit',
};
```

**The `[series].astro` two-site trap (per Hermes spec §4.9).** The series page does
`const copy = SERIES_COPY[name]; … copy.blurb`, so a missing key throws on
`undefined.blurb` and `/series/cockpit/` 500s. Both edits MUST land together.

Proposed Cockpit blurb:

> *"The operator cockpit for the DGX Spark — drive every quant, LoRA, bench, harness, and
> skill your Spark has produced from one local-first surface. Spark Arena (entry #1) is a
> hybrid Astro + FastAPI app at `http://127.0.0.1:7866/arena/` that surfaces live
> telemetry, rubric-scored side-by-side compare, and a private leaderboard you can publish
> when you're ready. The cockpit complements the Harnesses arc: where Hermes is the
> agent harness, Arena is the operator harness."*

**IA note.** `/arena/**` is a top-level route family alongside `/book/`, `/pricing/`,
`/artifacts/`, etc., owned in this monorepo. (Pre-cutover this was a Spark-authoritative
entry in the two-repo chrome-boundary contract; that boundary is retired.)

**`.claude/skills/tech-writer/references/use-case-arc.md`.** Add a "Cockpit series"
section so the tech-writer next-article detection knows the Arena arc.

## 9. Article arc

| # | Slug | Thesis | Stage (also_stages) | fieldkit_modules | Pillar | Session |
|---|---|---|---|---|---|---|
| **A1** (must, launch) | `introducing-spark-arena-on-spark` | The cockpit thesis: Hermes is the agent harness, Arena is the operator harness. The §4.3 compare walkthrough as the canonical example. The schema-split mirror. The day-one retroactive load. | dev-tools (agentic) | arena, harness, eval | Desirability + Feasibility | M7 |
| **A2** (v0.2) | `side-by-side-rubric-scored-compare-on-spark` | The §4.3 compare walkthrough as a standalone deep-dive: how `fieldkit.eval.score_answer` becomes a leaderboard axis; why no blind votes; the human-prefs separate-signal design. | agentic (dev-tools) | arena, eval | Feasibility | v0.2 |
| **A3** (v0.2) | `publishing-a-spark-arena-leaderboard` | Publishing the leaderboard as `Orionfold/spark-arena-leaderboard-v0.1`; the schema-split, the redaction gate, the citable solo-builder evidence base. | dev-tools (observability) | arena, publish | Viability | v0.2 |

A1 frontmatter (locked):

```yaml
title: "Introducing Spark Arena: a local-first cockpit for the solo Spark builder"
date: 2026-XX-XX
product: "NVIDIA DGX Spark"
stage: dev-tools
also_stages: [agentic]
difficulty: intermediate
time_required: "20 min read"
hardware: "NVIDIA DGX Spark"
tags: ["spark-arena", "fieldkit", "cockpit", "telemetry", "compare", "leaderboard"]
summary: "Six months of Spark work produced 49 articles, 13 HF artifacts, and the fieldkit
  substrate. Now it has a cockpit: a hybrid Astro + FastAPI app at 127.0.0.1:7866 with
  live telemetry, rubric-scored side-by-side compare, and a private leaderboard."
signature: SparkArenaCockpit
status: published
series: Cockpit
fieldkit_modules: [arena, harness, eval]
hf_url: https://huggingface.co/Orionfold/spark-arena-leaderboard-v0.1  # post-v0.2
```

A1 includes the cockpit screenshot grid (`SparkArenaCockpit.astro` signature component
showing all 5 panes), 8 explainers (2 define / 1 why / 2 pitfall / 1 hardware-shape on the
128 GB envelope under concurrent streams / 1 math on the cost-per-quality Pareto / 1
deeper on the rubric-deterministic decision), and the §4.3 compare walkthrough as the
narrative spine. `customer_linked: true` (the cockpit landing cross-links to it).

## 10. Risk register

| ID | Risk | Likelihood | Impact | Mitigation | Fallback |
|---|---|---|---|---|---|
| R1 | **Public mirror leaks operator chat history** | low | **Catastrophic** | `mirror.py` allowlist; `chat_*` tables never enumerated; regression test in M6; `chat_sessions.publishable` default 0 | Mac `git revert` the sync commit; restage |
| R2 | Single-brain envelope OOM during compare | med | high | Default compare = local vs OpenRouter (no concurrent local warm); explicit two-local mode uses visible swap; `serve_lane(guard=True)` refuses | UI red banner; SSE `error` event with headroom report |
| R3 | Astro hybrid mode fails to statically export island-using pages | low-med | build breakage | Every island declared `client:only="preact"` (never SSRs); static pages contain no sidecar fetches at build time; `prebuild` mirror tolerated failing | `output: 'server'` for `/arena/**` only, behind an arena integration flag |
| R4 | `arq` / Redis aarch64 surprise | low-med | v0.2 surface unavailable | v0.1 makes Redis runtime-optional; `--no-jobs` CLI flag; M1 install-verify is the canary | Fall back to `fastapi.BackgroundTasks` (only background work in v0.1 is telemetry) |
| R5 | Spec rot / Phase-N-of-M cliff | low | medium | Every milestone independently shippable; M7 is the public commit gravity; HANDOFF Arena Track makes incompleteness visible | Cut at any M; the prior milestones are valuable on their own |
| R6 | Mac↔Spark SMB-mount tear during sync | low | data tear | `cut-mirror` writes to `_staging/` then atomic-rename per `[[reference_sync_workflow_nfs_mount]]`; `/sync-field-notes` reads only settled files | DESTINATION SYNC WATCH banner notes last `_staging/` write timestamp |
| R7 | Toggle-script discovery brittle | med | new lanes invisible | `scan_evidence.py` looks for `HOST=`, `PORT=`, model id; if not findable, lane registered as `notes: 'manual-only'` and shown with "Run manually" badge | Operator writes `~/.fieldkit/arena/lanes.yaml` to register explicitly |
| R8 | Hermes config drift (operator manually edits `~/.hermes/config.yaml`) | high | cockpit shows wrong "active" chip | On every `GET /api/lanes`, re-read `~/.hermes/config.yaml` mtime; update cached row | "Refresh lanes" button calls `POST /api/lanes/refresh` |
| R9 | Rubric reuse policy collision (ad-hoc rubric sprawl) | med | rubric debt | Honor `[[feedback_keep_scorer_local_until_reuse]]`: ad-hoc rubrics at `~/.fieldkit/arena/rubrics/`; promote to fieldkit on 2nd reuse | Curator skill flags >2 reuses with "promote candidate" entry in HANDOFF |
| R10 | SQLite WAL contention (curator + sidecar both write) | low | brief write block | WAL mode + short busy_timeout; curator refuses to run mid-compare (touches `~/.fieldkit/arena/.lock`) | Operator pauses sidecar; runs curator; resumes |
| R11 | `/arena/` URL collision with future Mac chrome | very low (destination-overrides clearly Mac-owns `/book`, `/pricing` etc.; `/arena/**` is Spark-authoritative addition) | route clash | This spec includes the Mac PR adding `/arena/**` to Spark-authoritative side | Rename to `/cockpit/` (slug already reserved) if Mac ever wants `/arena/` for marketing |
| R12 | `fieldkit.arena` bloats `import fieldkit` time | low | CLI slow | Follow `fieldkit.harness` pattern: lazy `__getattr__`, no FastAPI import on package load | Benchmark in `test_arena.py::test_import_time_under_50ms` |

> **M8 adds R13–R17** (job-payload mirror leak, arq/Redis aarch64 first-consumer, regression false-positives, dangerous-tool reach, per-job restart cost) — see §12.5.

**Top 3 must-do early actions:**

1. **M1 build + schema gate** — land both `content.config.ts` + `[series].astro` edits +
   confirm `/series/cockpit/` renders and the artifact schema validates `arena_run` before
   any code work.
2. **M2 import-script idempotency test** — first time the script runs against the live
   repo state must be reproducible (re-runs produce identical SQLite rows).
3. **M6 mirror leak regression test BEFORE M7 article publish** — the leak gate is a hard
   gate; ship M7 only if the test is green and a manual grep confirms zero chat content
   in `src/data/arena-mirror/*.json`.

**Hard cut lines:**

- **End of M1:** spec + skeleton land; site builds. Cut if schema won't validate the new
  `arena_run` kind.
- **End of M2:** retroactive import populates SQLite + per-artifact pages render. Cut if
  the import script can't reproduce a clean leaderboard cut from the 2 published benches.
- **End of M6:** mirror exporter green + regression test passing. **Cut if the leak gate
  fails.** No public mirror until this is solved.
- **Never** ship the A1 article without M6's leak gate passing (security sequencing).

## 11. Release gates

| Release | Scope | Gate |
|---|---|---|
| `fieldkit v0.14.0` | First arena cut; MVP surface (M1–M6 fills) | All 5 cockpit panes paint; mirror leak regression test green; `audit-docs arena/N` clean; fresh-venv install verifies on aarch64; A1 article published; `nvidia-learn-stats` refreshed; Mac `/sync-field-notes` pushes static slice to `ainative.business/arena/`. |
| `fieldkit v0.14.1` | Telemetry + compare polish | Lane-swap UX edge cases (concurrent streams); rubric reuse promotion of any 2nd-reuse rubrics; mirror exporter performance on full-leaderboard exports. |
| `fieldkit v0.15.0` | v0.2 surface (eval runner + HF publish gate + cost-routed chat) | `arq` worker green; `Orionfold/spark-arena-leaderboard-v0.1` HF dataset live; A2 + A3 articles published. |
| `fieldkit v0.16.0` | **M8 control plane** (§12 — Phase 1 / Bet 3) | `jobs`/`job_triggers` schema migrates (`user_version` 2→3); an `eval_rerun` job dispatches **end-to-end through the MCP harness** and writes back an `eval_runs` row + rebuilds the leaderboard; leaderboard-regression trigger fires on a seeded regression; `/arena/jobs/` paints; `jobs` is OUT of the mirror allowlist and the leak regression test (R13) is green; `audit-docs arena/N` clean; the Phase-1 `product-writer` launch published. **No cron / no auto-push** (that is Phase 2). |
| ~`fieldkit v0.17.0` | **M9 cost plane** (§13 — Bet 6) — *spec written, unbuilt* | Schema `user_version` 4→5 (first ALTER migration, R18) round-trips a seeded v4 db; compare/chat completions INSERT `cost_usd`; `leaderboard_rows` carries `mean_cost_usd` + `cost_per_quality_point`; `openrouter_price_snapshot` seeded from the version-controlled H6 evidence + added to `PUBLISHABLE_TABLES`; cockpit shows `$/task` + `$/quality-point`; session spend survives restart; `audit-docs cost` clean. **Ledger only — `fieldkit.budget` enforcement is Phase 2.** |
| ~`fieldkit v0.18.0` | **M10 recall layer** (§14 — Bet 5) — *spec written, unbuilt* | Schema `user_version` 5→6 (`reindex_runs` + `rag_eval_runs`) + pgvector `blog_chunks` provenance columns; `reindex`/`rag_eval`/`scout_ingest` promoted to `DISPATCHABLE`; multi-source ingest under one provenance card via `fieldkit.memory` over `fieldkit.rag`; a `rag_eval` job tracks recall@k + gates promotion; `/arena/knowledge/` pane paints coverage (`article_index`⋈index) + the RAG-eval trend; single query backend behind both MCP surfaces; `rag_eval_runs` aggregates mirror, chunk text never; external assets version-controlled (M10-12); `audit-docs memory` clean. **Pane only — the publish-hook + scheduled sweep are Phase 2.** |

## 12. M8 — Arena as the control plane (Phase 1 of the MTBM roadmap)

> **Status: BUILT (2026-06-02).** All 8 M8 decisions (M8-1…8) were green-lit as written and the
> milestone is implemented end-to-end — see §12.7 for the as-built map. The release *tag/publish*
> (`fieldkit v0.16.0`) is a separate `fieldkit-curator` action, not yet cut. This section extends
> the locked v0.1+v0.2 spec
> with the **M8 control-plane milestone** — `_FLOWS/the-machine-that-builds-machines.md` §3
> **Phase 1 / Bet 3 ("Arena as the control plane — the pane")**. It is grounded against
> Spark-measured evidence in [`roadmap-reconciliation.md`](roadmap-reconciliation.md) §"Phase 1"
> (marked **CONFIRMED, operational** — the only bet with zero wrong abstractions). M8 promotes
> Arena from a **recorder** (M1–M7: records lanes/chats/compares, exports a leaderboard mirror)
> into a **dispatcher** — the place the operator *triggers* work from. It is **connective
> tissue, not greenfield**: both its inputs (the `eval_runs.arq_job_id` socket drilled in §4.8)
> and its execution surface (the live 7-tool MCP harness, `build_mcp_server()`) already exist.
>
> **Code reconciliation (2026-06-02, verified against the built `fieldkit/src/fieldkit/`).** The
> "already exists" claims hold: `harness/mcp.py::build_mcp_server()` registers exactly **7
> `server.tool()`** (envelope · weight · throughput · perplexity · `quantize_gguf` [dry-default] ·
> `publish_quant_dry_run` · `ask_second_brain`); `arena/store.py` has the real `eval_runs` table
> with `arq_job_id`; `arena/mirror.py` has the `PUBLISHABLE_TABLES` allowlist **plus** a
> `FORBIDDEN_TABLES`/`FORBIDDEN_COLUMNS` deny-list. Three drift corrections folded into this
> section: (1) **no `jobs.py` exists** — the §4.7 file tree named it a v0.2 stub but it was never
> built, so M8 *creates* the module; (2) the built store is **already at `user_version = 2`** (v0.2
> added `lab_notes` + `eval_scores`), so M8 migrates **2→3**, not 1→2; (3) M8 extends *both* mirror
> lists (allowlist + forbidden), matching the built `lab_notes` precedent.
>
> **Fuller `fieldkit.arena` audit (2026-06-02) — M8 is *more* connective tissue than first stated.**
> The eval-scoring substrate `eval_rerun` needs **already exists and runs synchronously**: an
> **`eval_scores`** table (per-question grades), `ArenaStore.append_eval_score()`,
> `ArenaStore.eval_leaderboard()` (accuracy rollup), and the `POST /api/chat/score` + `GET
> /api/eval/*` endpoints. **So M8's `eval_rerun` job wraps the existing inline scorer in the queue
> — it does not build eval from scratch.** Two clarifications this forces: **(a)** the three eval
> tables play distinct roles — **`jobs`** (M8) = queue spine; **`eval_runs`** (built, but its
> `arq_job_id` socket is currently *unused*) = M8 activates it as the per-run *status* row;
> **`eval_scores`** (built, populated by `/api/chat/score`) = the per-question *results*. **(b)** two
> leaderboards exist — `leaderboard_rows` (rebuilt by `rebuild_leaderboard()`, `mean_score` from
> `rubric_scores.total`/`core_pass_rate`) and `eval_leaderboard()` (accuracy over `eval_scores`) —
> so the §12.3 regression detector diffs the **accuracy** rollup (`eval_leaderboard`), not the
> compare-rubric one. **Pre-existing §4.7 drift (not M8's):** the file tree lists `models.py` /
> `streams.py` / `jobs.py`, but records live in `schemas.py` and SSE helpers are embedded in
> `server.py` — only `jobs.py` is M8's to create.

### 12.1 M8 locked decisions (proposed — confirm before build)

| # | Decision | Value | Grounding |
|---|---|---|---|
| M8-1 | **Execution surface** | The dispatcher executes **through the MCP harness** (`fieldkit.harness.build_mcp_server()`), **not** ad-hoc `g3_*` shelling. Single surface shared with Hermes ⇒ the safety rails are defined once and never diverge. | `hermes-drives-the-spark-via-fieldkit-mcp`: agent → `measure_gguf_throughput` → GPU → real number (41.75 tok/s), **0% tool-call format error**, stdio, no network. |
| M8-2 | **First job type** | **`eval_rerun` / re-measure only.** Deterministic, already exists, meaningful day one ("leaderboard regression → re-eval"). `requant`, `rl_run`, `reindex`/`rag_eval`/`scout_ingest` ship as **named stubs** (Phases 3 / Bet-5). | reconciliation: the measure tools are "exactly the ones already exercised through the harness with zero format errors." |
| M8-3 | **Containment** | **Two-layer, inherited from the harness:** (a) tool curation — the 7-tool list size *is* the policy (`publish` structurally unreachable, `quantize` dry-run-default); (b) execution sandbox — docker `--network=none`, hard-stop guardrails. The dispatcher adds nothing new; it inherits both. | `hardening-the-hermes-harness-on-spark`: 3/3 hostile DNS/exfil/fetch calls contained. |
| M8-4 | **Anti-amnesia gate** | Any *agentic* job (Phase-3 `rl_run`, Bet-5 `scout_ingest`) bakes in the Phase-0 dedup/history gate: `block_repeat(last_k≈50)` + `render_history(k≈30)`. `eval_rerun` is deterministic and exempt. | `trajectory-eval-is-the-agent-flailing`: 72% repeat rate, 14 unique/50 → gate lifts unique trials ≈**4×**. |
| M8-5 | **Sequential loads only** | The dispatcher drains **one job at a time**, one lane resident (128 GB envelope, `serve_lane(guard=True)`). Parallel drain is a DGX-Cloud config (`_FLOWS` §6), **out of scope** for the Spark M8. | `[[project_spark_unified_memory_oom]]`; `hermes-vertical-router-on-spark`: 78 GB headroom at brain + 1 vertical, still single-lane. |
| M8-6 | **No autonomy yet** | M8 is **operator-triggered + button-dispatched.** The cron drain, hook battery, and morning-standup review gate are **Phase 2** (now written: §15 / Arena M11). M8 honors the no-auto-push invariant by *staging only* — no job pushes. | `_FLOWS` §3 sequencing: pane (M8) before hands (cron). |
| M8-7 | **Harness grows by demand** | Add `measure_variants` / `run_vertical_eval` MCP tools to `fieldkit.harness` **as the dispatcher calls them** — not speculatively. This is where Phase 1 and Phase 2's harness work partially merge. | `_FLOWS` §4 enhancement table (harness row is **S**, not M — 7 tools already shipped). |
| M8-8 | **Mirror safety** | The new `jobs` + `job_triggers` tables stay **OUT** of `export_publishable_slice()`'s `PUBLISHABLE_TABLES` allowlist *and* are added to the belt-and-suspenders `FORBIDDEN_TABLES` (with `("jobs","payload_json")` in `FORBIDDEN_COLUMNS`) — the exact two-list pattern the built `mirror.py` already uses for `lab_notes`/`("lab_notes","body")`. Job payloads carry prompts and must never leak. Same discipline as `chat_*` (§4.8, R1). | Extends the M6 leak-gate regression test. |

### 12.2 Deliverables

| Artifact | Surface | Gate |
|---|---|---|
| `jobs` + `job_triggers` tables (`PRAGMA user_version` **2 → 3** — the built store is already at 2 after v0.2's `lab_notes`/`eval_scores`; idempotent migration) | `~/.fieldkit/arena.db` | M8 schema gate |
| **New module `fieldkit.arena.jobs`** — `JobStore` + `dispatch_job` + `enqueue_job` (dispatches via the MCP harness). NB the §4.7 file tree named `jobs.py` as a v0.2 stub but it was **never built** — M8 creates it fresh, not "promotes" it. | `fieldkit` PyPI | `audit-docs arena/N` clean |
| `POST/GET /api/jobs`, `GET /api/jobs/{id}`, `GET /api/jobs/stream` (SSE), `DELETE /api/jobs/{id}` | sidecar `server.py` | endpoint smoke |
| `/arena/jobs/` Astro route + `<JobsBoard>` Preact island (queued · running · done · failed; dispatch + cancel) | source site | paints offline-safe on mirror |
| **Leaderboard-regression trigger producer** — diff new `leaderboard_rows.mean_score` vs prior; over-threshold drop enqueues an `eval_rerun` | `fieldkit.arena.jobs` | unit test on a seeded regression |
| `measure_variants` + `run_vertical_eval` MCP tools (added by M8-7 demand) — **`mcp.py`'s first `fieldkit.eval` wiring** (the 7 built tools import only `capabilities`/`quant`/`publish`/`nim`/`rag`); also add their `MCPToolSpec` entries to `MCP_TOOL_SPECS` | `fieldkit.harness.mcp` | dispatch smoke through the harness + `docs/api/` updated (audit-docs gate) |
| Mirror allowlist+denylist extension + leak-test sentinel: plant a `LEAK_SENTINEL_*` string in `jobs.payload_json`, assert it is absent from `src/data/arena-mirror/*.json` (the existing test only covers tables that exist) | `mirror.py` + `tests/arena/test_mirror_does_not_leak.py` | **hard gate** (R1 family) |
| The Phase-1 **`product-writer` launch** (`products/`, `series: Cockpit`) — build-metrics + jobs/dispatch/regression feature tour, cross-linking the H4 deep-dive | `products/<slug>/product.md` | gated on M8 shipping (HANDOFF editorial overlay) |

### 12.3 Architecture

**The `jobs` table** (the queue spine; distinct from the two built eval tables — `eval_runs` is the per-run *status* row whose `arq_job_id` socket M8 finally activates, and `eval_scores` holds the per-question *results* the existing `/api/chat/score` scorer already writes):

```sql
-- M8 (user_version 2→3):
CREATE TABLE jobs (
  id              TEXT PRIMARY KEY,
  kind            TEXT NOT NULL,               -- 'eval_rerun'|'measure_variants'  (M8)
                                               --   |'requant'|'rl_run'            (Phase 3 stub)
                                               --   |'reindex'|'rag_eval'|'scout_ingest' (Bet-5 stub)
  status          TEXT NOT NULL,               -- 'queued'|'dispatched'|'running'|'done'|'failed'|'skipped'
  trigger         TEXT NOT NULL,               -- 'manual'|'leaderboard_regression'|'stale_bench'|'compare_loss'(P3)
  priority        INTEGER NOT NULL DEFAULT 0,
  payload_json    TEXT NOT NULL,               -- {lane_id, bench_id, manifest_slug, …} — OPERATOR-ONLY, never mirrored
  dedup_key       TEXT,                        -- (kind, lane_id, bench_id) — coalesces duplicate triggers while queued
  result_json     TEXT,                        -- harness tool return; for eval_rerun → an eval_runs.id ref
  error           TEXT,
  attempt         INTEGER NOT NULL DEFAULT 0,
  enqueued_at     TEXT NOT NULL,
  dispatched_at   TEXT,
  finished_at     TEXT,
  arq_job_id      TEXT                         -- the existing socket; null when running via BackgroundTasks fallback
);
CREATE UNIQUE INDEX ix_jobs_dedup ON jobs(dedup_key) WHERE status IN ('queued','dispatched','running');

CREATE TABLE job_triggers (                    -- audit trail of what fired each job (regression deltas, etc.)
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  job_id          TEXT NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
  source          TEXT NOT NULL,               -- 'leaderboard_regression'|'stale_bench'|'operator'
  detail_json     TEXT NOT NULL,               -- {bench_id, prev_score, new_score, delta} | {age_days} | {operator_note}
  created_at      TEXT NOT NULL
);
```

**The dispatcher** (`fieldkit.arena.jobs.dispatch_job`) — single-lane, MCP-routed:

```
enqueue_job(kind, payload, trigger)            # writes a 'queued' row; dedup_key coalesces
  → drain loop (arq worker | BackgroundTasks fallback per R4), one job at a time:
      claim oldest 'queued' (priority desc, enqueued asc) → 'dispatched'
      → build_mcp_server() tool call:
            eval_rerun       → run_vertical_eval(lane, bench)   [M8-7 tool]
            measure_variants → measure_variants(manifest_slug)  [M8-7 tool]
      → 'running' → harness executes on GPU (one lane resident, serve_lane guard)
      → eval_rerun writes via the EXISTING scorer path (append_eval_score → eval_scores rows)
            + flips the eval_runs status row (enqueued→started→finished); result_json = eval_runs.id
      → 'done' | 'failed'
      → on 'done': rebuild_leaderboard() + refresh eval_leaderboard() → re-run the regression
            detector against the accuracy rollup (may enqueue follow-ups)
      → SSE 'job' event on /api/jobs/stream throughout
```

**Trigger producers** (M8 wires the first two; the third is a Phase-3 stub):

| Trigger | Source | Fires | Status |
|---|---|---|---|
| `leaderboard_regression` | diff the **accuracy** rollup (`eval_leaderboard()`): `new.mean_score < prev.mean_score − τ` (the per-question `eval_scores` source, not the compare-rubric `leaderboard_rows`) | `eval_rerun` (confirm the regression is real, not noise) | **M8** |
| `stale_bench` | `leaderboard_rows.last_run_at` older than `freshness_days` | `eval_rerun` | **M8** (manual-poll in M8; *scheduled* in Phase 2) |
| `compare_loss` | a `human_prefs`/`rubric_scores` loss on the resident model | `rl_run` | **Phase 3 stub** (`rlvr-loop-v1.md`) |

**`fieldkit.arena` `__all__` additions (M8):**

```python
# + jobs
"JobRecord", "JobStore", "enqueue_job", "dispatch_job", "JobKind", "JobStatus",
"detect_leaderboard_regression",
# + errors
"JobDispatchError", "UnknownJobKind",
```

**Cockpit UX (`/arena/jobs/`).** A `<JobsBoard>` island: four columns (queued / running / done /
failed) over `GET /api/jobs/stream`; a **"Dispatch"** affordance (re-eval a lane×bench manually);
a **regression banner** when the detector has auto-enqueued ("Leaderboard regression on `patent-bench`:
0.81 → 0.74; `eval_rerun` queued"). Offline-safe on the public mirror (same `hostname !== '127.0.0.1'`
guard as the other islands) — and since `jobs` is never mirrored, the public `/arena/jobs/` renders an
empty "Cockpit offline" state by construction.

### 12.4 Grounding (from `roadmap-reconciliation.md`)

- **Dispatch-through-MCP is validated end-to-end, not theoretical** — `hermes-drives-the-spark-via-fieldkit-mcp`: real measured dispatch, **0% format error**. ⇒ M8-1 is connective tissue.
- **Containment is two-layer** — tool curation (the list size *is* the policy) + docker `--network=none` sandbox (3/3 hostile contained, `hardening-the-hermes-harness-on-spark`). ⇒ M8-3 inherits both.
- **First job type is the right call** — the measure tools are exactly the ones exercised through the harness with zero format errors. ⇒ M8-2.
- **The dedup gate is where the leverage is** — 72% repeat rate without it (`trajectory-eval-is-the-agent-flailing`); ≈4× unique trials with `block_repeat(last_k=50)` + `render_history(k=30)`. ⇒ M8-4.

### 12.5 M8 risk additions (extend §10)

| ID | Risk | Likelihood | Impact | Mitigation | Fallback |
|---|---|---|---|---|---|
| R13 | **`jobs.payload_json` leaks to the public mirror** | low | **Catastrophic** (job prompts) | `jobs`/`job_triggers` OUT of `PUBLISHABLE_TABLES`; regression test asserts no `payload_json` text in the mirror JSON (R1 family) | revert the mirror commit; restage from `_staging/` |
| R14 | **arq/Redis aarch64 surface finally exercised** (R4 was deferred to v0.2; M8 is the first real consumer) | low-med | dispatcher dead | M8 ships a `fastapi.BackgroundTasks` drain as the *primary* single-lane path; arq is opt-in (`--jobs-backend arq`) for when Phase 2 needs durable cross-process scheduling | BackgroundTasks-only; jobs drain in-process while the sidecar is up |
| R15 | **Regression detector false-positives** (synth/eval noise trips a re-eval storm) | med | wasted GPU | threshold `τ` + a `dedup_key` unique-index that coalesces duplicate triggers while queued; `eval_rerun` is cheap (measure, no train) and *confirms* before any downstream action | raise `τ`; require manual confirm for any non-`eval_rerun` follow-up |
| R16 | **Dispatcher reaches a dangerous tool** | low | publish/quant side-effect | inherited M8-3 curation: `publish` structurally absent from `build_mcp_server()`, `quantize` dry-run-default; M8 job kinds only call read/measure tools | the harness tool-list is the single chokepoint — audit it, not each job |
| R17 | **Per-job lane restart dominates wall** (`~3.5 min` vLLM restart per the RL grounding) | med | slow drain | `eval_rerun` measures the *resident* lane where possible (no restart); batch same-lane jobs before swapping; this is the same restart-elimination win flagged for Phase 3 | accept the restart cost for cross-lane batches; surface it in the jobs board ETA |

### 12.6 Sequencing — what M8 unblocks

M8 is the **pane** the rest of the roadmap lands into. Each later phase extends *this* `jobs`
table rather than inventing its own queue:

- **Phase 2 (M11, §15)** — a cron layer *drains the M8 queue overnight* (sequential loads, M8-5); a hook battery enqueues jobs (post-publish → `eval_rerun`); the morning-standup artifact renders the jobs board as the human-review gate. M8-6's "stage only, no push" is the contract the standup enforces.
- **Phase 3 (`rlvr-loop-v1.md`)** — a `compare_loss` trigger enqueues an `rl_run`; the result flows back to the leaderboard, closing the loop *visibly* — the entire reason the pane was built first. The held-out-every-10-steps gate and the `(success, failure_class, auxiliary)` reward tuple live in that spec, not here.
- **Bet 5 (`second-brain-pipeline-v1.md`)** — adds `reindex` / `rag_eval` / `scout_ingest` job kinds + an Arena knowledge pane; the re-index-on-publish hook is a Phase-2 trigger producer.
- **Bet 6 (`cost-plane-v1.md`)** — persists `cost_usd` on the compare/chat tables + an `openrouter_price_snapshot`; the jobs board and leaderboard gain a `$/task` + `$/quality-point` axis; `fieldkit.budget` (Phase 2) reads the ledger before the dispatcher launches a job.

### 12.7 As-built map (2026-06-02 — all 8 decisions green-lit, implemented)

Every §12 decision landed as specified. Where the spec described "already exists" infrastructure, the build wired into it rather than recreating it.

| Deliverable | As built | Tests |
|---|---|---|
| `jobs` + `job_triggers` tables, `user_version` 2→3 | `arena/store.py` `_SCHEMA_SQL` (idempotent `CREATE TABLE IF NOT EXISTS` + partial unique `ix_jobs_dedup` + `USER_VERSION = 3`); `JobStore` methods on `ArenaStore` (`enqueue_job`/`claim_next_job`/`update_job`/`get_job`/`list_jobs`/`cancel_job` + `upsert_eval_run`/`update_eval_run`/`get_eval_run`) | store smoke; `test_jobs.py` |
| `JobRecord` / `JobTriggerRecord` | `arena/schemas.py` | — |
| **`fieldkit.arena.jobs`** — `enqueue_job` · `dispatch_job` · `drain_jobs` · `detect_leaderboard_regression` · `enqueue_regressions` · `JobKind`/`JobStatus` · `JobDispatchError`/`UnknownJobKind` · `default_runner` | new module; dispatch routes through `fieldkit.harness.mcp` (M8-1); `eval_rerun` persists via the existing `append_eval_score` → `eval_scores` path + activates the `eval_runs` status row; sequential single-lane drain (M8-5); dedup coalesce (R15) | `test_jobs.py` (17) |
| `measure_variants` + `run_vertical_eval` MCP tools | `harness/mcp.py` — `run_vertical_eval` is the first `fieldkit.eval` wiring (wraps `VerticalBench`); both registered on `build_mcp_server()` (9 tools) + `MCP_TOOL_SPECS` | `test_harness_mcp.py` (live FastMCP registration) |
| `POST/GET /api/jobs`, `GET /api/jobs/{id}`, `GET /api/jobs/stream` (SSE), `DELETE /api/jobs/{id}` | `arena/server.py` — `BackgroundTasks` drain as the primary path (R14, no arq/Redis); `jobs_event_stream` snapshot-on-change SSE; graceful `failed`-not-500 degradation when no lane is served | `test_jobs_api.py` (9) |
| `/arena/jobs/` route + `<JobsBoard>` island | `arena-app/src/pages/arena/jobs.astro` + `components/arena/JobsBoard.jsx` (4 columns, dispatch form, cancel, regression banner, `isPublicMirrorHost` offline-safe) + "Jobs" nav tab + global CSS; builds into both the public preview (`dist/`) and the wheel bundle (`dist-arena/`) | Astro build (119 pages) |
| Mirror allowlist+denylist extension + leak sentinel | `mirror.py` — `jobs`/`job_triggers` → `FORBIDDEN_TABLES`, `("jobs","payload_json")` → `FORBIDDEN_COLUMNS`; `test_mirror_does_not_leak.py` plants a `payload_json` sentinel + adds the `test_jobs_tables_are_forbidden` anchor | `test_mirror_does_not_leak.py` (8) |
| Docs | `docs/api/arena.md` §"M8" + `docs/api/harness.md` — `audit-docs arena/harness` both clean | audit-docs gate |

**Gates green:** full `fieldkit` suite **1118 passed / 16 skipped** (skips = optional heavy deps + `--spark`-only); `audit-docs` 12/13 PASS (the lone SKIP is `cli`, no `__all__`; the 2 residual kwarg-WARNs are pre-existing v0.2/v0.3 methods, not M8). **Not done (deliberately):** the `fieldkit v0.16.0` tag + PyPI publish (a `fieldkit-curator` action), the Phase-1 `product-writer` launch article (gated on M8 shipping — now unblocked), and a live human-eye/Lighthouse pass of `/arena/jobs/` with the sidecar up (the cockpit is currently DOWN).

## 13. M9 — Cost plane (Bet 6 of the MTBM roadmap)

> **Status: BUILT (2026-06-02) — see §13.7 as-built map; staged for `~v0.17.0`.** This section
> realizes `_FLOWS/the-machine-that-builds-machines.md` §3 **Bet 6 ("the cost plane —
> token economics as a first-class decision axis")** as the **Arena M9** milestone, the
> first of the two cross-cutting bets to extend the M8 control plane (the priority is
> recorded in `_SPECS/index.md` Planned queue + `HANDOFF.md` ▶ NEXT UP). It is grounded
> against Spark-measured evidence in [`roadmap-reconciliation.md`](roadmap-reconciliation.md)
> §"Bet 6" / `hermes-cost-routing-local-and-openrouter`. **Like M8, M9 is connective
> tissue, not greenfield** — the cost is already *computed*, just discarded; M9 *persists +
> surfaces* it. The `fieldkit.budget` **enforcement** arm is explicitly out of scope (Phase 2,
> now written: §15 / Arena M11); M9 ships the **ledger + read API** that governor consumes.
>
> **Code reconciliation (2026-06-02, verified against the built `fieldkit/src/fieldkit/`).**
> Five facts shape the decisions: **(1)** `_compare_cost_usd()` is **real but DB-ephemeral** —
> `arena/server.py` computes `cost_usd` for OpenRouter lanes only, feeds it to the in-memory
> `hub.add_openrouter_cost()` accumulator (`_openrouter_cost_usd`) + the SSE `done` payload,
> and **never INSERTs it**; the accumulator resets on every sidecar restart. **(2)** The store
> is already at `USER_VERSION = 4` (M8's 2→3 jobs + the side-by-side 3→4 `leaderboard_baseline`),
> so M9 migrates **4→5**. **(3)** `compare_responses` has `tokens_out` but **no `tokens_in`**;
> `compare_runs` carries the prompt but zero token columns; only `chat_turns` has both — so
> per-side input cost needs a new column. **(4)** Token counts are the **4-char heuristic**
> (`approx_tokens = int(len(full)/4)`) — today's `$` is doubly approximate. **(5)** The H6
> evidence (`evidence/openrouter_prices.json`, `cost_router_results.json`) the code declares
> canonical (`RouteTier` docstring + `_OR_FALLBACK_MODELS` both say "keep canonical with the
> article evidence JSON") is **not version-controlled** — `git ls-files` of that dir is empty
> (the `_FLOWS` §7 drift bullet). **M9 is the first milestone that ALTERs existing tables** —
> M8 only added new tables (idempotent `CREATE TABLE IF NOT EXISTS` sufficed); M9 needs a real
> `ALTER TABLE ADD COLUMN` migration guarded on `PRAGMA user_version` (R18).

### 13.1 M9 locked decisions (signed off 2026-06-02)

| # | Decision | Value | Grounding |
|---|---|---|---|
| M9-1 | **Persist what's already computed** | The compare/chat completion path **INSERTs** the `cost_usd` it currently throws away, at the exact point it calls `add_openrouter_cost()`. Local lanes write `0.0`. Lowest-marginal-effort core: no new arithmetic, just persistence. | recon #1 — `_compare_cost_usd()` exists + is ephemeral. |
| M9-2 | **Where cost lands (per-run, private)** | `user_version 4→5`. Add `cost_usd` to **`chat_turns`** (per turn) + **`compare_responses`** (**per side**) and add the missing **`tokens_in`** to `compare_responses` — per-side because each lane bills the shared prompt at *its own* input price. These tables are **never mirrored** (absent from `PUBLISHABLE_TABLES`), so per-run cost is private by construction. | recon #2, #3; mirror allowlist. |
| M9-3 | **Aggregate cost (public)** | Add `mean_cost_usd` + derived **`cost_per_quality_point`** to **`leaderboard_rows`** (already in `PUBLISHABLE_TABLES`), computed in `rebuild_leaderboard()`/`_split_leaderboard_rows` where `mean_score` already lands. The only cost surface that goes public. | `leaderboard_rows` is the mirrored aggregate. |
| M9-4 | **`$/quality-point` definition** | `cost_per_quality_point = mean_cost_usd / mean_score` (guard `mean_score > 0`). Local-lane $0 renders **"$0 (local)"**, not a divide-by-zero "—". | roadmap UX (three-axis ranking). |
| M9-5 | **Price snapshot, pinned at import** | New **`openrouter_price_snapshot`** table seeded at store-init from the **baked H6 evidence JSON** (the source the code already declares canonical), **NOT** the live `_openrouter_catalog()`. Each cost row stamps the `snapshot_id` it was priced against ⇒ a comparison stays reproducible as live prices drift. The live catalog still drives the model dropdown only. | R7 reproducible-by-snapshot (`CostRouterConfig.render_yaml`); recon #5; signed-off call #2. |
| M9-6 | **Real token counts, heuristic fallback** | Use the OpenAI-compat response `usage.{prompt_tokens, completion_tokens}` when present; fall back to the 4-char heuristic when the endpoint omits `usage`. Persist a `tokens_estimated` flag so an approximate `$/task` is visibly marked, never silently trusted. | recon #4. |
| M9-7 | **Mirror safety (two-list discipline)** | `openrouter_price_snapshot` is **public-safe** (no prompts) ⇒ added to `PUBLISHABLE_TABLES` so the public leaderboard's `$/task` is reconstructable. Per-run cost columns inherit their host tables' exclusion. Extend `test_mirror_does_not_leak.py` with a sentinel asserting no prompt text rides a cost path. | mirror two-list pattern + R13 precedent (§12.5/M8-8). |
| M9-8 | **Persisted session spend (fix the reset)** | The live spend rail's session total is **read back from the persisted rows**, surviving a sidecar restart instead of resetting from `_openrouter_cost_usd = 0.0`. | recon #1 — accumulator resets. |
| M9-9 | **Scope boundary — ship the ledger, not the governor** | M9 ships `fieldkit.cost` (per-run ledger + price snapshot + `$/quality` read API) + the cockpit cost axis. It does **NOT** ship enforcement: `fieldkit.budget`, the `LOCAL_CEILING = 33%` escalation contract, and the standup spend digest live in **Phase 2 (§15 / Arena M11)**, which *consumes* this ledger. | §12.6 sequencing; cross-bet-feeds-Phase-2 dependency. |
| M9-10 | **Version-control the H6 evidence** | Commit `evidence/openrouter_prices.json` + `cost_router_results.json` to the `hermes-cost-routing-local-and-openrouter` article (currently untracked) as the canonical seed for M9-5 — closing the `_FLOWS` §7 drift in the same milestone. | recon #5; signed-off call #3. |

### 13.2 Deliverables

| Artifact | Surface | Gate |
|---|---|---|
| Schema `user_version` **4 → 5** — `ALTER TABLE` adds `cost_usd`/`tokens_estimated` to `chat_turns`; `tokens_in`/`cost_usd`/`tokens_estimated`/`price_snapshot_id` to `compare_responses`; `mean_cost_usd`/`cost_per_quality_point` to `leaderboard_rows`; new `openrouter_price_snapshot` table (first ALTER-based migration, R18) | `~/.fieldkit/arena.db` | M9 migration gate (round-trips a `user_version=4` db) |
| **New module `fieldkit.cost`** — `CostLedger` (per-run rows) + `PriceSnapshot` (seed/lookup) + `cost_per_quality(bench, lane)` read API | `fieldkit` PyPI | `audit-docs cost` clean |
| `_compare_cost_usd()` INSERT wiring + `usage`-token parse + heuristic fallback | sidecar `server.py` | cost-persisted smoke (compare → row carries `cost_usd` > 0 + `tokens_estimated=0`) |
| Leaderboard `mean_cost_usd` + `cost_per_quality_point` compute | `arena/store.py` `rebuild_leaderboard()` | unit test on seeded cost rows |
| Cockpit cost cells — compare view + leaderboard `$/task` & `$/quality-point`; persisted session spend rail | source site | paints offline-safe (aggregate $ only on mirror) |
| Mirror: `openrouter_price_snapshot` → `PUBLISHABLE_TABLES`; leak-test sentinel on the cost path | `mirror.py` + `tests/arena/test_mirror_does_not_leak.py` | **hard gate** (R13 family) |
| H6 evidence committed (M9-10) | `articles/hermes-cost-routing-local-and-openrouter/evidence/` | `git ls-files` non-empty |
| Docs `docs/api/arena.md` §"M9" + `docs/api/cost.md` | `fieldkit` docs | `audit-docs` gate |
| Release `~fieldkit v0.17.0` | PyPI + tag | `fieldkit-curator` action (separate) |

### 13.3 Architecture

**Schema (`user_version 4→5`)** — the new price-snapshot table + the per-run/aggregate column adds:

```sql
-- M9 ALTERs (guarded on PRAGMA user_version=4 → 5; R18):
ALTER TABLE chat_turns        ADD COLUMN cost_usd REAL;
ALTER TABLE chat_turns        ADD COLUMN tokens_estimated INTEGER NOT NULL DEFAULT 1;
ALTER TABLE compare_responses ADD COLUMN tokens_in INTEGER;
ALTER TABLE compare_responses ADD COLUMN cost_usd REAL;
ALTER TABLE compare_responses ADD COLUMN tokens_estimated INTEGER NOT NULL DEFAULT 1;
ALTER TABLE compare_responses ADD COLUMN price_snapshot_id TEXT;  -- which snapshot priced this row
ALTER TABLE leaderboard_rows  ADD COLUMN mean_cost_usd REAL;            -- aggregate, public
ALTER TABLE leaderboard_rows  ADD COLUMN cost_per_quality_point REAL;   -- mean_cost_usd / mean_score

CREATE TABLE openrouter_price_snapshot (       -- public-safe (no prompts); seeded from H6 evidence JSON
  snapshot_id            TEXT NOT NULL,          -- batch id (content-hash of seed JSON | 'h6-baseline')
  model_id               TEXT NOT NULL,          -- 'anthropic/claude-opus-4.1'
  price_per_m_input_usd  REAL NOT NULL,
  price_per_m_output_usd REAL NOT NULL,
  source                 TEXT NOT NULL,          -- 'h6_evidence'|'fallback'
  captured_at            TEXT NOT NULL,
  PRIMARY KEY (snapshot_id, model_id)
);
```

**Cost flow** — persist at completion, aggregate at leaderboard rebuild:

```
compare/chat completion (server.py, OpenRouter lane):
  tokens_in, tokens_out ← response.usage  (fallback: len/4 heuristic, tokens_estimated=1)
  snapshot ← active openrouter_price_snapshot row for the model      [M9-5]
  cost_usd ← _compare_cost_usd(tokens_in, tokens_out, snapshot)      [M9-1]
  → INSERT cost_usd + tokens_in + tokens_estimated + price_snapshot_id onto the row  [M9-2]
  → hub.add_openrouter_cost(cost_usd)  (live rail; now also rehydrated from rows on restart, M9-8)

rebuild_leaderboard():
  mean_cost_usd ← AVG(cost_usd) over the bench×lane runs                 [M9-3]
  cost_per_quality_point ← mean_cost_usd / mean_score  (guard >0)        [M9-4]
  → leaderboard_rows (mirrored, public)

mirror export:
  openrouter_price_snapshot → PUBLISHABLE_TABLES (public, no prompts)    [M9-7]
  per-run cost_usd stays on chat_turns/compare_responses (never mirrored)
```

**`fieldkit.cost` `__all__` (M9):** `CostLedger`, `PriceSnapshot`, `seed_price_snapshot`, `cost_per_quality`, `CostError`.

**Cockpit UX.** The compare view's per-lane result cell and the leaderboard each gain a **`$/task`** + **`$/quality-point`** column beside `median_tok_per_s` + quality — "hosted SOTA or local?" answered on three axes. The live spend rail shows a session total that survives restart (M9-8). Offline-safe: the public mirror renders the aggregate `$/task` (from `leaderboard_rows` + `openrouter_price_snapshot`) but never a per-run figure.

### 13.4 Grounding (from `roadmap-reconciliation.md` §"Bet 6")

- **The economics are published, not theoretical** — `hermes-cost-routing-local-and-openrouter`: local-only 8/12 at **$0.00**, cost-routed 11/12 at **$2.19/100 tasks**, frontier-only 12/12 at **$2.94/100** behind a `--cap-usd` hard stop ⇒ a **25% spend cut at an 8.3% quality cost**, with a **33% leak** (a third genuinely needs frontier). ⇒ M9-3/M9-4 make this the standing third axis; the 33% leak is the constant M9-9 hands to the Phase-2 governor.
- **The cost-to-failure inversion** — `autoresearch-agent-loop`: **~$0.0004/failed trial** on the Spark ⇒ wide local exploration is effectively free; the $/quality axis is what makes the hosted-vs-local call legible.
- **Reproducible-by-snapshot is the established discipline** — the harness already bakes `spark-hermes-cost-router.yaml` rather than live-querying (R7). ⇒ M9-5 pins the snapshot table the same way.

### 13.5 M9 risk additions (extend §10)

| ID | Risk | Likelihood | Impact | Mitigation | Fallback |
|---|---|---|---|---|---|
| R18 | **First ALTER-based migration corrupts a live `user_version=4` db** | low-med | data loss | guarded `ALTER TABLE ADD COLUMN` (additive, non-destructive) inside a `user_version` check; a migration round-trip test on a seeded v4 db; columns nullable / defaulted | restore from the `_staging/` db copy; ADD COLUMN is reversible by ignoring the columns |
| R19 | **Snapshot staleness vs live drift** (a baked price diverges far from live, mis-ranking $/quality) | med | misleading rank | `captured_at` + a cockpit "prices as of <date>" stamp; an operator-triggered `reseed_price_snapshot` (not auto — reproducibility is the point) | re-seed from a fresh H6 evidence capture; old rows keep their `price_snapshot_id` |
| R20 | **Estimated tokens inflate/deflate $** when `usage` is absent | med | soft $/task error | `tokens_estimated=1` flag surfaced in the UI as a "~" prefix; prefer endpoints that return `usage` | accept the ~ marker; never publish an estimated figure as exact |

### 13.6 Sequencing — what M9 feeds

M9 is a **cross-cutting price signal**, not a sequential phase — it threads the pane/hands/engine the same way M8's `jobs` table does:

- **Phase 2 (M11, §15)** — `fieldkit.budget` reads M9's persisted ledger before the dispatcher launches a job; it encodes the **`LOCAL_CEILING = 33%`** failure-mode escalation (escalate when local *gives up*, not on a token ceiling alone) and emits a **spend digest** (today's $ by lane / by bench vs cap) into the morning standup. M9-9 is the seam.
- **Phase 3 (`rlvr-loop-v1.md`)** — **$/quality-point ROI**: a `compare_loss` trigger consults measured $/quality *before* the governor approves an `rl_run`, declining RL when frontier escalation is cheaper at equal quality — generalizing the $0.0004/failed-trial inversion to "cheaper to RLVR a local model to threshold, or pay frontier per call?" (mirrors Bet 5's pre-flight gate).
- **Bet 5 (Arena M10, §14)** — **now written**; shares the M8 `jobs` table + this $/quality discipline (a `rag_eval` job can carry its own cost row from this ledger).

### 13.7 As-built map (2026-06-02)

All 10 decisions landed as designed; the build matched the spec with no
deviations. Verified: full fieldkit suite **1142 passed / 16 skipped** (+13 over
the v0.16.0 baseline — 10 new `tests/test_cost.py`, 4 new mirror anchors, 1
existing allowlist test extended), `audit-docs` **cost 5/5 + arena clean**, main
`astro build` **493 pages** (the new `/fieldkit/api/cost/` route), both rendering
verifiers green, the arena cockpit bundle **bakes** (cost cells compile).

| Decision | As-built |
|---|---|
| M9-1 / M9-2 | New module **`fieldkit/src/fieldkit/cost.py`** (`__all__` = 5). Server `_emit_side` + chat path INSERT `cost_usd`/`tokens_in`/`tokens_estimated`/`price_snapshot_id` at the `add_openrouter_cost` point; local lanes write `0.0`. Dataclass fields added to `ChatTurnRecord` / `CompareResponseRecord`. |
| M9-3 / M9-4 | `mirror._aggregate_cockpit_rows` accumulates per-run cost → `mean_cost_usd` + `cost_per_quality_point` (guard `mean_score>0`); `cost.cost_per_quality()` + `_format_cost_per_quality()` own the `$0 (local)` render. |
| M9-5 / R19 | `openrouter_price_snapshot` seeded at `ArenaStore.initialize()` → `_seed_prices()` → `cost.seed_price_snapshot()` from the baked `H6_PRICE_SEED` (snapshot id `h6-baseline`); re-seed-under-new-id path tested. |
| M9-6 / R20 | Heuristic tokens carry `tokens_estimated=1`; cockpit marks the figure with a `~` prefix (compare metric + SSE `done` payload). |
| M9-7 | `openrouter_price_snapshot` → `PUBLISHABLE_TABLES`; the two aggregate columns → `leaderboard_rows` allowlist; per-run cost columns stay off (inherit host-table exclusion). 4 new anchors in `test_mirror_does_not_leak.py` + a `price_snapshot_id` sentinel. |
| M9-8 | `TelemetryHub.seed_session_spend()` ← `CostLedger.session_spend()` at `create_app` — the rail's running total now survives a restart. |
| M9-9 | Scope held — ledger + read API + cockpit axis only; no `fieldkit.budget` (Phase 2). |
| M9-10 | `articles/hermes-cost-routing-local-and-openrouter/evidence/{openrouter_prices,cost_router_results}.json` committed (was untracked). |
| R18 | `ArenaStore._migrate` / `_add_column_if_missing` — guarded `ALTER TABLE ADD COLUMN` on `PRAGMA table_info`. **Round-trip test on a seeded `user_version=4` db** (`test_migration_v4_to_v5_round_trip`): existing rows preserved, columns added, version → 5, snapshot seeded. |

**Staged, not released:** the version bump + tag + PyPI push are a separate
`fieldkit-curator` action (CHANGELOG `[Unreleased]` entry written). The running
cockpit's `_webui` was rebaked; the public `dist/` is unchanged until a
marketing-site deploy.

## 14. M10 — Recall layer (Bet 5 of the MTBM roadmap)

> **Status: LOCKED (decisions signed off 2026-06-02) — UNBUILT.** This section
> realizes `_FLOWS/the-machine-that-builds-machines.md` §3 **Bet 5 ("the recall layer —
> the Second Brain as a control-plane-managed knowledge pipeline")** as the **Arena M10**
> milestone, the second cross-cutting bet to extend the M8 control plane (priority recorded
> in `_SPECS/index.md` Planned queue + `HANDOFF.md` ▶ NEXT UP — it rides the *now-shipped*
> M8 pane, its grounding is *freshest* after the 2026-06-02 re-index, and it is the cleanest
> dogfood: the machine managing its own memory). It is grounded against Spark-measured
> evidence in [`roadmap-reconciliation.md`](roadmap-reconciliation.md) (the 12/63 staleness
> finding) + `_FLOWS` §3 "Bet 5" (the shipped retrieval-stack article corpus). **Like M8/M9,
> M10 is connective tissue, not greenfield** — the RAG stack, the eval harness, the query
> tool, and the *job-kind sockets themselves* already exist; M10 *promotes + consolidates +
> makes multi-source* what is today a manual, prose-only, externally-scripted index. The
> autonomous freshness arm (re-index-on-publish hook + scheduled scout sweep) is explicitly
> out of scope (Phase 2, now written: §15 / Arena M11); M10 ships the **operator-driven pane +
> the managed index** that arm later automates.
>
> **Code reconciliation (2026-06-02, verified against the built `fieldkit/src/fieldkit/` + the
> on-disk RAG stack).** Seven facts shape the decisions: **(1)** the **job-kind sockets are
> already drilled** — `arena/jobs.py` declares `JobKind.REINDEX`/`RAG_EVAL`/`SCOUT_INGEST` as
> **named stubs** (in `ALL`, excluded from `DISPATCHABLE`), commented `→ Bet-5
> second-brain-pipeline-v1`; M10 promotes them, the exact move M8 made for `eval_rerun`.
> **(2)** **`fieldkit.rag` exists** (`Pipeline.ingest()/retrieve()`, `Document`/`Chunk`,
> pgvector cosine), so `fieldkit.memory` is a **provenance/multi-source layer over it**, not a
> new RAG stack. **(3)** But there is an **ingest fork** — the *live* `blog_chunks` index was
> built by the **external** `/home/nvidia/rag-eval-work/ingest_blog.py` (word-based 900w/150-
> overlap, `(slug, chunk_idx)` PK, DROP+rebuild), **not** by `fieldkit.rag.Pipeline` (token-
> based chunking, different `cid` scheme); M10-2 adopts the `Pipeline` as canonical and
> converges the scheme on one re-index. **(4)** `blog_chunks` is `(id, slug, chunk_idx, text,
> embedding)` — **no provenance columns**; trust-filtered multi-source recall needs the
> `source·kind·date·claims·verdict·link` card added to the vector table (M10-3/4). **(5)** the
> **RAG-eval harness is real but stale-pointed** — `rag-eval-work/{retrieve,grade,analyze}.py`
> + `nemo_evaluator_config.yaml` produce real metrics (`summary.json`: rerank lane
> `p_chunk_at_k`=**0.955**, `p_slug_at_k`=0.977, faithfulness 0.477, vs cosine-only 0.659) but
> `retrieve.py` reads its `qa-eval.jsonl` gold set from the **retired `/home/nvidia/nvidia-
> learn/` path**. **(6)** arena.db **already has an `article_index`** table (metadata-only,
> store.py) distinct from the pgvector index, so coverage/freshness = `article_index` ⋈
> indexed-slug set — the silent 12/63 staleness becomes a computed number. **(7)** **two
> stores + a version dependency** — the index lives in pgvector, the jobs/scores in arena.db
> (at `USER_VERSION = 4`; M9 takes it to 5), so M10 migrates **5→6**, contingent on M9 shipping
> first. **The drift M10 closes (the M9-10 analog):** `ingest_blog.py`, the `qa-eval` gold set,
> the eval config, and the `second-brain-mcp` query server **all live outside the repo, none
> version-controlled** — precisely why the index sat stale at 12/63 (its external script still
> pointed at the retired `nvidia-learn` path until the 2026-06-02 re-index repointed it).

### 14.1 M10 locked decisions (signed off 2026-06-02)

| # | Decision | Value | Grounding |
|---|---|---|---|
| M10-1 | **Promote the pre-drilled job kinds** | `reindex` / `rag_eval` / `scout_ingest` move from `JobKind` named stubs into `JobKind.DISPATCHABLE`; the dispatcher gains a handler per kind, executing **through the same MCP harness surface** M8 established (single execution surface, inherited safety rails). Lowest-marginal-effort core: the sockets, dedup index, and lifecycle already exist. | recon #1 — `arena/jobs.py:76–78` stubs tagged for this spec; mirrors M8-2. |
| M10-2 | **`fieldkit.memory` over `fieldkit.rag`** (ingest fork resolved) | New module `fieldkit.memory` wraps the existing `rag.Pipeline` with multi-source ingest + provenance + a managed-index registry. **The `Pipeline` is adopted as the canonical ingest** — `ingest_blog.py`'s multi-source logic ports onto it and one re-index converges the divergent chunk scheme; the external word-based script is retired. One version-controlled ingest path. | recon #2, #3; **signed-off open call A.** |
| M10-3 | **Multi-source, one provenance card** | Ingest extends from `articles/*` to **three source classes**: (i) **published prose** (articles + Book sections), (ii) **internal experiment memory** (`fieldkit.lineage` trials, `eval_runs`, future `rl_run` cards, `evidence/` summaries), (iii) **external research** (`frontier-scout` `papers.json` + Spark-feasibility verdicts, `deep-research` cited reports). Every chunk carries `source · kind · date · claims · verdict · link`. | `_FLOWS` §3 Bet 5 (three source classes); recon #4; **signed-off open call C.** |
| M10-4 | **Provenance is a retrieval filter** (in pgvector) | The card lives as **columns on `blog_chunks`** so retrieval filters by **trust tier** in the vector SQL itself — a Spark-*measured* number and an external-*claimed* one are not interchangeable. `ask_second_brain` gains a `provenance` filter arg; the harvest's confirms / sharpens / **complicates** discipline is baked into the index. | recon #4; **signed-off open call C** (columns-on-`blog_chunks`). |
| M10-5 | **Two stores, explicit** | Vector + provenance rows stay in **pgvector `blog_chunks`** (extended with the provenance columns). The **bookkeeping** lands in **arena.db (`user_version 5→6`)**: a **`reindex_runs`** table (run provenance — when, source-set, chunk delta, index version) + a **`rag_eval_runs`** table (the harness metrics per index version). Honest note: `5→6` assumes M9's `4→5` shipped first (else these are the `4→5` adds). | recon #6, #7; M9 §13.1/M9-2 schema precedent. |
| M10-6 | **Wrap the existing eval harness as the `rag_eval` job** | `rag-eval-work/{retrieve,grade,analyze}.py` + `nemo_evaluator_config.yaml` become a recurring dispatcher job emitting a tracked score into `rag_eval_runs`. **Index promotion gates on it** — a rebuild that drops `recall@k` below the prior index does not get promoted (don't ship a regression). | recon #5 — real metrics in `summary.json`; `_FLOWS` §3 Bet 5 ("index promotion can gate on it"). |
| M10-7 | **Rerank-off is the measured baseline; rerank is bounded drift** | The eval + query run **cosine-only on GB10** (no reranker profile — NGC 410-dead, local NIM has no `-dgx-spark` build). Every `rag_eval_runs` row stamps `rerank=0`; the pane labels it "cosine-only"; the `RERANK_URL` env-override (already baked into both query servers) self-enables a `-dgx-spark`/frontier reranker. A bounded known-drift bullet carries the measured gap (`p_chunk_at_k` 0.659 → 0.955 under rerank). | recon #5 + `[[reference_second_brain_reindex]]` (GB10 reranker gap); mirrors M9 R19 snapshot-drift discipline. |
| M10-8 | **Coverage = `article_index` ⋈ index** | The pane's coverage/freshness number is the join of arena.db `article_index` (what *should* be indexed) against the set of indexed slugs in pgvector (what *is*) — chunk counts, stale-since, missing. The silent 12/63 staleness that bit the harvest becomes a visible, actionable number. | recon #6 — `article_index` exists; `_FLOWS` §7 (the 12/63 lag was invisible). |
| M10-9 | **Single canonical query backend** | `fieldkit.memory` is the **one backend** behind *both* the standalone `second-brain-mcp` server and the harness `ask_second_brain` tool — provenance filter + rerank policy defined once, never diverging. | recon #2; **signed-off open call B.** |
| M10-10 | **Mirror safety (two-list discipline)** | `rag_eval_runs` *scores* (recall@k, faithfulness — aggregates, no prompts) are **public-safe** ⇒ added to `PUBLISHABLE_TABLES` for a public "RAG-eval trend". `reindex_runs` and **any chunk-text path** (the query/inspect console returns chunk text, which is prompt-like) stay **out**, in `FORBIDDEN_TABLES`. Extend `test_mirror_does_not_leak.py` with a sentinel on the knowledge path. | M8-8 / M9-7 two-list precedent (R13 family). |
| M10-11 | **Scope boundary — ship the pane, not the autonomous hands** | M10 ships the operator-driven **knowledge pane** + the three dispatcher job types + `fieldkit.memory` + the **eval-gated manual re-index**. It does **NOT** ship the **re-index-on-publish hook** or the **scheduled freshness monitor + scout sweep** — those live in **Phase 2 (§15 / Arena M11)**, which *consumes* this pane's re-index button + eval gate. | §12.6 / M9-9 ledger-not-governor pattern; `_FLOWS` §3 Bet 5 cross-phase wiring. |
| M10-12 | **Version-control the external assets** | Commit `ingest_blog.py` (as the seed for `fieldkit.memory`'s ingest), the `qa-eval.jsonl` gold set, `nemo_evaluator_config.yaml`, and the `second-brain-mcp` server into the monorepo (under `fieldkit/` + the relevant article's `evidence/`) as the canonical seed — closing the `_FLOWS` §7 "external / manually re-indexed" drift in the same milestone. | recon (the drift); **signed-off open call D**; the M9-10 analog. |

### 14.2 Deliverables

| Artifact | Surface | Gate |
|---|---|---|
| Schema `user_version` **5 → 6** — `ALTER`/`CREATE` adds `reindex_runs` + `rag_eval_runs` to arena.db; pgvector `blog_chunks` += `source`/`kind`/`doc_date`/`verdict`/`link` provenance columns (re-ingest backfills, R21) | `~/.fieldkit/arena.db` + pgvector `vectors` | M10 migration gate (round-trips a `user_version=5` db); provenance-backfill smoke |
| **New module `fieldkit.memory`** — `MemoryIndex` (managed multi-source ingest over `rag.Pipeline`) + `KnowledgeCard`/`Provenance` + `coverage_report()` + provenance-aware `query()` | `fieldkit` PyPI | `audit-docs memory` clean |
| Dispatcher handlers for `reindex` / `rag_eval` / `scout_ingest` (promoted into `JobKind.DISPATCHABLE`) | `arena/jobs.py` | a `reindex` job rebuilds the index + writes a `reindex_runs` row; a `rag_eval` job scores it; `scout_ingest` folds a `frontier-scout` verdict in |
| Multi-source ingest — prose + lineage/eval + scout/deep-research, one provenance card | `fieldkit.memory` | ingest smoke across all three source classes; provenance column populated |
| RAG-eval harness wired as the `rag_eval` job (qa-eval gold repointed to the monorepo) | `fieldkit.memory` + `rag_eval_runs` | recall@k tracked; promotion-gate test (a recall-dropping rebuild is blocked) |
| **Arena knowledge/RAG pane** — coverage·freshness (the `article_index`⋈index diff) · re-index button · RAG-eval trend chart · provenance-filtered query console | source site `/arena/knowledge/` | paints offline-safe (only `rag_eval_runs` aggregates on the mirror; no chunk text) |
| Single query backend — `fieldkit.memory` behind both the standalone server + harness tool | `second-brain-mcp/server.py` + `harness/mcp.py` | both call one backend; provenance filter works through both |
| Mirror: `rag_eval_runs` → `PUBLISHABLE_TABLES`; `reindex_runs` + chunk-text path → `FORBIDDEN_TABLES`; leak sentinel | `mirror.py` + `tests/arena/test_mirror_does_not_leak.py` | **hard gate** (R13 family) |
| External assets committed (M10-12) | `fieldkit/` + `articles/<rag-eval-article>/evidence/` | `git ls-files` non-empty for the seed set |
| Docs `docs/api/arena.md` §"M10" + `docs/api/memory.md` | `fieldkit` docs | `audit-docs` gate |
| Release `~fieldkit v0.18.0` | PyPI + tag | `fieldkit-curator` action (separate); follows M9's v0.17.0 |

### 14.3 Architecture

**Schema (arena.db `user_version 5→6`)** — the run-bookkeeping tables; the index itself stays in pgvector:

```sql
-- M10 (arena.db, user_version 5→6; assumes M9's 4→5 shipped — else 4→5):
CREATE TABLE IF NOT EXISTS reindex_runs (   -- provenance of each index rebuild (private)
  id            TEXT PRIMARY KEY,
  source_set    TEXT NOT NULL,              -- 'articles' | 'lineage' | 'scout' | 'all'
  index_version TEXT NOT NULL,              -- content-hash / monotonic tag of the resulting index
  chunks_before INTEGER,
  chunks_after  INTEGER,
  articles_n    INTEGER,                    -- distinct source docs ingested
  status        TEXT NOT NULL,              -- queued|running|done|failed
  started_at    TEXT NOT NULL,
  finished_at   TEXT,
  error         TEXT
);
CREATE TABLE IF NOT EXISTS rag_eval_runs (  -- scores per index version (aggregates → public)
  id               TEXT PRIMARY KEY,
  reindex_run_id   TEXT REFERENCES reindex_runs(id),
  qa_set           TEXT NOT NULL,           -- which gold set (versioned in-repo)
  recall_at_k      REAL,                    -- p_chunk_at_k
  slug_recall_at_k REAL,                    -- p_slug_at_k
  faithfulness     REAL,
  mean_correctness REAL,
  refusal_rate     REAL,
  rerank           INTEGER NOT NULL DEFAULT 0,  -- 0 = cosine-only (GB10 default, R22)
  status           TEXT NOT NULL,
  created_at       TEXT NOT NULL
);

-- M10 (pgvector `blog_chunks`, provenance card — trust-filterable at query time):
ALTER TABLE blog_chunks ADD COLUMN source   text;  -- 'article'|'lineage'|'eval'|'scout'|'deep_research'
ALTER TABLE blog_chunks ADD COLUMN kind     text;  -- doc kind within the source class
ALTER TABLE blog_chunks ADD COLUMN doc_date text;
ALTER TABLE blog_chunks ADD COLUMN verdict  text;  -- e.g. scout feasibility ('feasible'|'infeasible:X')
ALTER TABLE blog_chunks ADD COLUMN link     text;
```

**Recall flow** — ingest multi-source → eval-gate → promote → query-with-provenance:

```
reindex job (dispatcher, through fieldkit.memory):
  for source_class in {articles, lineage, scout}:           [M10-3]
    docs ← collect(source_class) with provenance card        [M10-3/4]
    rag.Pipeline.ingest(docs)  → blog_chunks (+ provenance)   [M10-2/4]
  → reindex_runs row (chunks_before/after, index_version)     [M10-5]

rag_eval job (dispatcher):
  retrieve.py + grade.py over the in-repo qa-eval gold set    [M10-6]
  → rag_eval_runs row (recall@k, faithfulness, rerank=0)      [M10-5/7]
  PROMOTE iff recall_at_k ≥ prior index's recall_at_k         [M10-6]

query (ask_second_brain, single backend):
  qvec ← embed(query)                                         [M10-9]
  hits ← blog_chunks ORDER BY embedding <=> qvec
         [WHERE source IN (trust filter)]                     [M10-4]
  → provenance-tagged, cited answer

mirror export:
  rag_eval_runs (aggregates) → PUBLISHABLE_TABLES (public)    [M10-10]
  reindex_runs + chunk text → FORBIDDEN_TABLES (never)
```

**`fieldkit.memory` `__all__` (M10):** `MemoryIndex`, `KnowledgeCard`, `Provenance`, `ingest_sources`, `coverage_report`, `MemoryError`.

**Cockpit UX.** A new `/arena/knowledge/` pane: **(a)** a coverage/freshness panel (the `article_index`⋈index diff — indexed/stale/missing with chunk counts, M10-8); **(b)** a **Re-index** button (full or per-source-class) that enqueues a `reindex` job; **(c)** a **RAG-eval trend** chart over `rag_eval_runs` (recall@k by index version, "cosine-only" labelled, R22); **(d)** a provenance-filtered **query console** (the operator's own cited `ask_second_brain`, with a trust-tier toggle). Offline-safe: the public mirror renders only the `rag_eval_runs` aggregate trend — never chunk text or a `reindex_runs` row.

### 14.4 Grounding (from `_FLOWS` §3 "Bet 5" + the on-disk RAG stack)

- **The retrieval stack is shipped + measured, not theoretical** — `naive-rag-on-spark`, `pgvector-on-spark`, `nemo-retriever-embeddings-local`, `rerank-fusion-retrieval-on-spark`, `guardrails-on-the-retrieval-path`, `bigger-generator-grounding-on-spark` build the stack; `rag-eval-ragas-and-nemo-evaluator` (+ the on-disk `rag-eval-work/` harness) is the eval half; `mcp-second-brain-in-claude-code` is the query surface. M10 **consolidates these producers into one managed, evaluated, operator-driven index**, not invents them.
- **The measured eval ceiling is on disk** — `rag-eval-work/summary.json`: the `rerank_8b` lane scores `p_chunk_at_k`=**0.955** / `p_slug_at_k`=0.977 / faithfulness 0.477 / refusal 0.0, vs cosine-only `naive_8b` at 0.659 / 0.864 / 0.432 / 0.182. ⇒ M10-7's bounded-drift gap is a real number, and the GB10 cosine-only baseline (M10-6's gate) is the honest floor until a `-dgx-spark` reranker lands.
- **Staleness was invisible and bit the last harvest** — the Second Brain held **12/63 articles** at the 2026-06-02 harvest (its external `ingest_blog.py` still pointed at the retired `nvidia-learn` path), so the roadmap-reconciliation harvest fell back to a disk-read fan-out. ⇒ M10-8 makes coverage a standing number; M10-12 version-controls the script so it can't silently rot again.
- **Re-scouting amnesia has both an internal and external cure** — `autoresearch-agent-loop`'s 72%-repeat finding (the internal cure baked into M8-4) has an external twin: a scouted-but-rejected paper persists in the index as *"evaluated, infeasible because X"* (M10-3's external source class), so the system stops re-scouting what it already judged.

### 14.5 M10 risk additions (extend §10)

| ID | Risk | Likelihood | Impact | Mitigation | Fallback |
|---|---|---|---|---|---|
| R21 | **Provenance backfill** — adding columns to a populated `blog_chunks` leaves existing rows with NULL provenance, so trust-filtering silently drops legacy chunks | med | recall gap | the ingest is already a DROP+rebuild (idempotent), so M10's first re-index backfills every row; a `provenance_backfilled` coverage check in the pane gates the trust filter until 100% | run the trust filter only over backfilled slugs; NULL-provenance = treat as lowest tier, never drop |
| R22 | **Cosine-only ceiling mistaken for the index's true recall** — a `rag_eval_runs` score looks worse than a historical rerank-capable run, mis-reading the index as regressed | med | misleading trend | every row stamps `rerank=0`; the pane labels "cosine-only"; the promotion gate (M10-6) compares **like-for-like** (`rerank=0` vs `rerank=0` only), never across rerank modes | re-enable rerank via `RERANK_URL` when a `-dgx-spark` reranker arrives; old rows keep their `rerank` flag |
| R23 | **Eval-gate blocks a legitimately-different rebuild** — adding lineage/scout chunks changes the corpus, so article-only `recall@k` can move for a good reason; a naive gate blocks it | med | stalled re-index | gate **per-source-class** (the article qa-eval set gates only the article slice; lineage/scout get their own gold sets as they mature) + an explicit operator override logged on the `reindex_runs` row | operator-confirm promotion; widen the qa-eval set to cover the new source classes before gating them |

### 14.6 Sequencing — what M10 feeds

M10 is a **cross-cutting recall surface**, not a sequential phase — it threads pane/hands/engine the same way M8's `jobs` table and M9's cost ledger do:

- **Phase 2 (M11, §15)** — the **re-index-on-publish hook** + a **scheduled freshness monitor** automate M10's manual re-index button, and a scheduled `frontier-scout` sweep lands back through M10's `scout_ingest` job — finally realizing Ch-11's named-but-unbuilt "Freshness Monitoring" box. M10-11 is the seam (it ships the pane the hooks later drive).
- **Phase 3 (`rlvr-loop-v1.md`)** — the index ingests `rl_run`/`lineage` cards (M10-3's internal class), and a `compare_loss` trigger **queries the Second Brain before the governor approves an `rl_run`** — returning the internal `t2po` finding (47.7% per-assertion ceiling, +33% wall for nothing) *and* any external paper verdict, so a doomed RL run is declined or redirected. Mirrors M9's pre-flight cost gate.
- **Phase 2 (M11, §15) — now written** — with both cross-cutting bets specced (M9 cost ✅, M10 recall ✅), the autonomous harness references both defined contracts (the budget governor reads M9's ledger; the freshness monitor drives M10's re-index) instead of dangling them. Authored as **§15 (Arena M11)** 2026-06-02 (placement chosen consistent with M8/M9/M10). Then `rlvr-loop-v1.md` (Phase 3) last.

## 15. M11 — Autonomous harness + cron (Phase 2 of the MTBM roadmap)

> **Status: LOCKED (decisions signed off 2026-06-02) — UNBUILT.** This section
> realizes `_FLOWS/the-machine-that-builds-machines.md` §3 **Phase 2 / Bet 2 ("the
> autonomous harness — hooks + a scheduled loop that the control plane governs")** as the
> **Arena M11** milestone — the **hands** in the `pane → hands → engine` sequence. Placement
> chosen 2026-06-02 to land as an Arena section (consistent with M8/M9/M10) rather than the
> standalone `_SPECS/autonomous-harness-v1.md` the roadmap text originally named: Phase 2's
> concrete build is the autonomy layer *over* the M8 pane — it drains the M8 `jobs` queue,
> renders the standup from the M8 board + M9 ledger, and emits triggers into the M8 dispatcher.
> It is grounded against Spark-measured evidence in
> [`roadmap-reconciliation.md`](roadmap-reconciliation.md) §"Phase 2" (*foundation solid,
> autonomy scaffold genuinely unbuilt*). **Unlike M8/M9/M10, M11 is NOT pure connective tissue
> on the data plane** — the *trigger producers and the drain already exist*, but the
> **scheduler, the hook battery, and `fieldkit.budget` are greenfield**; M11 is the layer that
> turns a button-driven dispatcher into a self-operating loop with a human review gate. The
> closed-loop **engine** (`rl_run` dispatch, the RLVR trainer) is explicitly out of scope
> (Phase 3, `rlvr-loop-v1.md`); M11 ships the **scheduler + hooks + budget governor + standup**
> that *drain and govern* whatever the dispatcher already supports.
>
> **Code reconciliation (2026-06-02, verified against the built `fieldkit/src/fieldkit/` + the
> live `.claude/`).** Six facts shape the decisions: **(1)** the **drain + trigger producer are
> already built** — `arena/jobs.py` ships `drain_jobs()` (single-pass, `max_jobs`-capped) and
> `check_and_enqueue_regressions()`, *both carrying the in-code comment "the Phase-2 cron will
> call this on a schedule"*; M11 adds the **scheduler that calls them**, not the dispatch. **(2)**
> **`fieldkit.budget` does NOT exist** (`ls fieldkit/src/fieldkit/` — no `budget`); it is the new
> top-level module M11 introduces, sibling to M9's `fieldkit.cost`. **(3)** **`fieldkit.cost`
> (M9) is also unbuilt**, so the governor's `$/task` input has *no source yet* — M11 must degrade
> gracefully rather than hard-block on M9's build slot (AH-5). **(4)** there is **exactly one hook
> today** — repo `.claude/settings.json` `SessionStart` (the gh-deploy-failure check); `~/.claude`
> hooks are `{}`, and the §6.5 Stop-hook feedback loop is **named but never installed** — so §3's
> "one hook, no cron" is literally accurate. **(5)** `.claude/scheduled_tasks.lock` is a **stale
> lock from a dead 2026-05-30 session** (pid 357866) — a lock file, *not* a scheduler — confirming
> the substrate is half-wired. **(6)** arena.db is at `USER_VERSION = 4` (M9 → 5, M10 → 6); M11
> adds **no schema** (AH-9) — schedules live in version-controlled config + `/schedule` routines,
> the standup is an ephemeral render over the existing `jobs` / `leaderboard_baseline` / M9 cost
> rows — keeping M11 a *connective* milestone on the storage plane even as it is greenfield on the
> automation plane.

### 15.1 M11 locked decisions (signed off 2026-06-02)

| # | Decision | Value | Grounding |
|---|---|---|---|
| AH-1 | **Scheduler over the built drain, not a new dispatcher** | A `/schedule`-driven cron (or `~/.claude` cron routine) calls the *already-built* `drain_jobs()` + `check_and_enqueue_regressions()` on a schedule — **single-lane sequential**, `max_jobs`/per-pass timeout, one model lane resident at a time (OOM envelope). The cron reimplements nothing; it is the missing *trigger*, not new dispatch logic. | recon #1 — drain + regression producer exist, comments name the Phase-2 cron. |
| AH-2 | **Hook battery, 1 → N** | Expand the lone `SessionStart` hook into a battery: **post-publish → `nvidia-learn-stats` refresh + enqueue `eval_rerun`**; **pre-commit → `verify_*`** (the two rendering verifiers); **post-article → secret-scan**; and finally *install* the §6.5 Stop-hook feedback loop (named-but-absent today). Hooks are **deterministic shell only — never an LLM call** (invariant #4). | recon #4 — one hook today; §6.5 Stop hook uninstalled. |
| AH-3 | **Morning-standup artifact = an Arena render, NO push** | The no-auto-push invariant (#3/#1) means the cron **stages + opens a review, never pushes.** The standup renders **what ran / what regressed / what's queued / today's $ by lane** over the M8 `jobs` board + the M8 `leaderboard_baseline` regression set + the M9 spend digest — the *mandatory human-review gate*. M8-6's "stage only, no push" is the contract it enforces. | §12.6 (M8-6); invariants #1/#3. |
| AH-4 | **`fieldkit.budget` — new governor module** | New top-level module the cron consults **before** launching a job. Encodes the **`LOCAL_CEILING = 33%`** *failure-mode-driven* escalation (escalate when local *gives up* — multi-step planning / KV-cache derivation hit the 30B-A3B class boundary — not on a token ceiling alone). Generalizes the corpus-synth weekly-`/usage` gate + the OOM-envelope check into one guard. | recon #2; recon §"Phase 2" 33%-leak; `[[project_spark_unified_memory_oom]]`. |
| AH-5 | **M9 cost plane = a *soft* prerequisite** | When `fieldkit.cost` (M9) is present the governor reads the persisted ledger for `$/task` + the 33% ceiling; when absent it **degrades to a token + OOM-envelope guard** (the two checks that already exist). M11 ships **independent of M9's build slot**; M9 *upgrades* the governor when it lands. No hard ordering between M9 and M11 builds. | recon #3 — `fieldkit.cost` unbuilt; avoid build deadlock. |
| AH-6 | **Freshness-monitor = a scheduled job that *emits* M8 triggers** | A scheduled bench / stale-index check that enqueues `eval_rerun` (post-M10: `reindex` / `rag_eval`) into the dispatcher via the built `check_and_enqueue_regressions()` path — realizing Ch-11's named-but-unbuilt **"Freshness Monitoring"** box. This is the *trigger source* that makes the plane autonomous rather than button-driven. | recon #1; §12.6; `_FLOWS` §3 Phase 2(e); M10-11 seam. |
| AH-7 | **Scope = the autonomy *layer*, not new job kinds** | M11 builds scheduler + hooks + budget + standup over what the dispatcher *already* supports (`eval_rerun`, `measure_variants`). It does **NOT** promote `rl_run` (Phase 3) or `reindex`/`rag_eval`/`scout_ingest` (M10) to `DISPATCHABLE` — those land in their own milestones. M11 *drains and schedules*; it does not extend `JobKind.DISPATCHABLE`. | `JobKind.DISPATCHABLE` (recon); §12.6 phase boundaries. |
| AH-8 | **Containment carries forward — unsupervised ≠ unconstrained** | The overnight loop dispatches through the **same two-layer MCP harness + docker `--network=none` sandbox** M8 inherited (tool-list-is-policy; `publish` dry-run-forced; 3/3 hostile calls contained). Autonomy adds the budget ceiling (AH-4) + the standup review gate (AH-3) *on top of* that containment; it never relaxes it. | M8 §12.4 grounding; `hardening-the-hermes-harness-on-spark`. |
| AH-9 | **No new arena.db table, no `user_version` bump** | Schedules live in **version-controlled config** (`fieldkit.budget` policy + `/schedule` routines), not a new table; the standup is an **ephemeral render** over the existing `jobs` / `leaderboard_baseline` / M9 cost rows. M11 leaves the schema at M10's `6`. Keeps M11 connective-tissue on the storage plane. | recon #6 — minimize schema churn. |

### 15.2 Deliverables

| Artifact | Surface | Gate |
|---|---|---|
| **New module `fieldkit.budget`** — `BudgetGovernor` (pre-launch check) + `BudgetDecision` (allow / escalate / defer + reason) + `SpendDigest` (today's $ by lane/bench vs cap) + `check_budget()` read API | `fieldkit` PyPI | `audit-docs budget` clean |
| **Scheduler glue** — a cron/`/schedule` routine calling `drain_jobs(max_jobs=…)` + `check_and_enqueue_regressions()` single-lane on a schedule, behind a one-drain-at-a-time lock | `fieldkit.arena` / cron config | drain-on-schedule smoke (a seeded queue drains one pass, lane teardown verified) |
| **Hook battery** — post-publish / pre-commit / post-article / Stop hooks in `.claude/settings.json` | repo `.claude/` | each hook fires deterministically; pre-commit `verify_*` round-trip; secret-scan blocks a planted secret |
| **Budget governor wiring** — the drain consults `BudgetGovernor.check_budget()` before each job; escalation honors `LOCAL_CEILING=33%` (M9 present) or token+envelope (M9 absent, AH-5) | `arena/jobs.py` drain path | governor unit tests (both M9-present and M9-absent branches) |
| **Morning-standup render** — an Arena surface (`/arena/standup/` or the jobs board's digest header) over `jobs` + `leaderboard_baseline` + M9 spend; stage-only, no push | source site | paints offline-safe (mirror shows aggregate only); no push path exists by construction |
| **Freshness-monitor job** — a scheduled `eval_rerun`/regression sweep emitting triggers into the M8 dispatcher | cron + `arena/jobs.py` | a stale-bench sweep enqueues the expected `job_triggers` row |
| Docs `docs/api/arena.md` §"M11" + `docs/api/budget.md` | `fieldkit` docs | `audit-docs` gate |
| Release `~fieldkit v0.19.0` | PyPI + tag | `fieldkit-curator` action (separate) |

### 15.3 Architecture

**No schema (AH-9).** M11 adds neither a table nor a `user_version` bump; it is automation glue over the M8/M9 storage already in place. The three new surfaces are the **scheduler**, the **governor**, and the **standup render**.

**Scheduler flow** — the cron is a thin loop over the built drain, gated by the governor:

```
cron tick (overnight, single-lane):
  acquire drain lock (.claude/scheduled_tasks.lock pattern — one drain at a time)  [AH-1]
  for each pending job (claim_next_job, sequential):                              [AH-1]
    decision ← BudgetGovernor.check_budget(job, today_spend, envelope)            [AH-4]
      ├─ allow    → dispatch_job(job)  via the MCP harness + sandbox              [AH-8]
      ├─ escalate → mark job for frontier lane (local gave up; 33% ceiling)       [AH-4/AH-5]
      └─ defer    → leave queued, log to standup (over cap / no envelope)         [AH-3]
  check_and_enqueue_regressions()   (freshness sweep emits new triggers)          [AH-6]
  release lock; stage the standup; DO NOT push                                    [AH-3]
```

**Hook battery** (`.claude/settings.json` — deterministic shell, AH-2):

| Event | Hook | Action |
|---|---|---|
| post-publish (commit touching `articles/**`/`products/**`) | stats + enqueue | run `nvidia-learn-stats`; `enqueue_job(eval_rerun)` for affected benches |
| pre-commit | verify | `verify_artifact_rendering.mjs` + `verify_field_notes_rendering.mjs` (advisory `\|\| true` where non-blocking) |
| post-article | secret-scan | scan the staged diff for secrets before it can be committed |
| Stop | feedback loop | the §6.5 named-but-uninstalled loop, finally wired |

**Budget governor decision** — `fieldkit.budget` generalizes the two existing guards into one pre-launch check:

```
BudgetGovernor.check_budget(job, spend_today, envelope):
  if cost ledger present (M9):                                                    [AH-5]
      if spend_today + est_cost(job) > daily_cap:        return defer
      if job.failure_class in LOCAL_CEILING_TRIGGERS:    return escalate (33%)    [AH-4]
  else (M9 absent — token + envelope only):                                       [AH-5]
      if weekly_usage_pct > cap:                         return defer  (/usage gate)
  if not envelope.fits(job.lane):                        return defer  (OOM guard) [AH-4]
  return allow
```

**`fieldkit.budget` `__all__` (M11):** `BudgetGovernor`, `BudgetDecision`, `SpendDigest`, `EscalationReason`, `check_budget`, `BudgetError`.

**Standup render (AH-3).** An Arena surface assembling, from the existing tables, a stage-only review: **Ran** (completed `jobs` since the last standup), **Regressed** (`leaderboard_baseline` deltas this pass), **Queued** (pending `jobs`), **Spend** (M9 `SpendDigest`: today's $ by lane/bench vs cap; "—" when M9 absent). It has **no push capability** — the operator reads it and promotes manually, honoring #1/#3. Offline-safe: the public mirror renders only the aggregate standup (never a per-run prompt or per-run $).

### 15.4 Grounding (from `roadmap-reconciliation.md` §"Phase 2" + `_FLOWS` §3 Phase 2)

- **Every prerequisite is measured and in place.** The brain is pinned by evidence — `picking-the-hermes-brain-on-spark` + `hermes-serving-lane-on-spark`: **Qwen3-30B-A3B Q4_K_M at 83.5 tok/s / 31.8 GB / 8/8**, where the 9B incumbent hits a hard **2/5 multi-step-planning wall** ⇒ the MoE is **non-negotiable** for overnight reasoning (AH-1's single-lane drain assumes the brain is the resident lane). The sequential-load envelope is validated — `hermes-vertical-router-on-spark`: brain 31.8 GB + one cold vertical ~5.5 GB ≈ **50 GB, 78 GB headroom** ⇒ AH-1's "one lane at a time" has comfortable margin.
- **The 33% local ceiling sets the governor's escalation contract.** `hermes-cost-routing-local-and-openrouter`: local-only **8/12**, cost-routed **11/12** at $2.19/100, frontier-only **12/12** at $2.94/100 ⇒ a third of the workload *genuinely needs* frontier escalation. So AH-4's `LOCAL_CEILING = 33%` is **failure-mode-driven**, not a token ceiling — the governor decides *when local gives up*.
- **The gap is real (greenfield), and that's the whole milestone.** No published article demonstrates a cron scheduler, a hook battery, or a morning-standup flow — the agent is *shown able to run unsupervised* (`hermes-drives-the-spark-via-fieldkit-mcp`, 0% format error) but **not shown running overnight with a review gate**. M11 is exactly that missing scaffold, built on a proven synchronous-dispatch substrate.
- **Containment is the precondition for autonomy.** `hardening-the-hermes-harness-on-spark` (docker `--network=none`, **3/3 hostile DNS/exfil/fetch calls contained**) + the tool-list-is-policy MCP layer are what make unsupervised overnight runs *safe* — AH-8 inherits both rather than re-deriving them.

### 15.5 M11 risk additions (extend §10)

| ID | Risk | Likelihood | Impact | Mitigation | Fallback |
|---|---|---|---|---|---|
| R24 | **Overnight cron OOMs the box** — a job loads a second model while the brain is resident, or the drain stacks lanes | med | box hang (the 2026-04-22 landmine) | single-lane sequential drain (AH-1) + the governor's envelope guard (AH-4) + the one-drain-at-a-time lock; each job tears its lane down before the next claims | the lock bounds blast radius to one pass; OOM kills the pass, not the box; `pkill -f 'vllm\|EngineCore'` sweep in lane teardown (`[[feedback_vllm_engine_core_orphan]]`) |
| R25 | **A hook slows or blocks the solo-blog commit flow** — a flaky/slow pre-commit hook stalls a legitimate direct-to-main commit | med | friction / blocked commit | hooks are fast deterministic checks (`verify_*` run in seconds); advisory checks use `\|\| true` and log rather than abort; only the secret-scan is hard-blocking | `--no-verify` escape hatch; demote a misbehaving hook to advisory; the SessionStart deploy check already catches a bad push downstream |
| R26 | **An errant autonomous path pushes or leaks** despite the no-push invariant — a cron route bypasses the standup gate | low | published leak / unreviewed push | the cron has **no push capability by construction** (stages only, AH-3); job payloads are already on the mirror denylist (M8-8, R13); the standup is the *only* promote path and it is human-driven | the `SessionStart` deploy-failure hook surfaces any errant push; revert + re-stage; mirror leak sentinel (`test_mirror_does_not_leak.py`) blocks payload columns |

### 15.6 Sequencing — what M11 feeds

M11 is the **hands** that operate the pane (M8) using the cost (M9) and recall (M10) signals — and it is the *home* the engine (Phase 3) lands into:

- **Phase 3 (`rlvr-loop-v1.md`)** — the cron **drains `rl_run` jobs overnight** (Phase 3's compute is too long for a synchronous click; the M11 scheduler is its execution home, single-lane); the budget governor's **$/quality gate decides RL-vs-frontier** *before* approving an `rl_run` (cheaper to RLVR a local model to threshold, or pay frontier per call?); and **held-out eval becomes a scheduled job** (the held-out-every-10-steps hard gate from `t2po` runs as an M11-scheduled `eval_rerun`, not a manual step). RLVR without M11 is a loop with no overnight home and no budget brake.
- **Closes the autonomous loop over M8/M9/M10** — M8's queue gets **drained autonomously**, M9's ledger gets **enforced** (not just displayed), M10's index gets **refreshed on schedule** (AH-6 ⇒ M10-11's freshness arm). After M11, the operator's posture is *review the standup + promote*, not *run the scripts* — the thesis the whole roadmap is about.
- **The §5 series gets its Phase-2 launch** — the `product-writer` "autonomous harness" launch (morning-standup · cron queue · budget governor) cross-linking the existing H4 deep-dive, per the HANDOFF editorial overlay, becomes promotable once M11 ships.

## 16. Change log

| Date | Change | Author |
|---|---|---|
| 2026-05-28 | Initial spec landed (v1.0 locked). Decisions §3.1 #1–#10 confirmed in the planning session (hybrid Astro + FastAPI · rubric-deterministic compare · anchor MVP scope · public-mirror distribution · new Cockpit series · `arena_run` artifact kind · Qwen3-30B-A3B brain as the resident lane · OpenRouter via H6 CostRouterConfig as default compare B-lane · deterministic generation boundary · scorer-reuse discipline). Plan workspace: `/home/nvidia/.claude/plans/let-s-plan-for-2-curious-thacker.md`. | Manav (with Claude planning session) |
| 2026-06-02 | **M8 control-plane milestone authored (§12).** Extends the locked v0.1+v0.2 spec with `_FLOWS` §3 **Phase 1 / Bet 3** — promote Arena recorder → dispatcher: new `jobs`/`job_triggers` tables, a single-lane dispatcher executing **through the MCP harness**, `eval_rerun` as the first (and only real) M8 job type, a leaderboard-regression trigger producer, `/arena/jobs/` cockpit surface, and the mirror-allowlist extension (R13). 8 locked decisions (M8-1…8, confirm before build), 5 new risks (R13–R17), grounded against `roadmap-reconciliation.md` §"Phase 1" (CONFIRMED, operational). Phases 2/3 + Bets 5/6 sequenced to extend this `jobs` table. **Spec only — unbuilt.** | Manav (with Claude) |
| 2026-06-02 | **M8 BUILT** (all 8 decisions green-lit as written). `fieldkit.arena.jobs` dispatcher + `jobs`/`job_triggers` schema (`user_version` 2→3) + `JobStore` methods; two harness MCP tools (`run_vertical_eval` — first `fieldkit.eval` wiring — + `measure_variants`); `/api/jobs` CRUD + SSE drain (BackgroundTasks primary, R14); `jobs`/`job_triggers` on the mirror denylist + leak sentinel (R13); `/arena/jobs/` route + `<JobsBoard>` island (builds into preview + wheel bundle). Tests: `test_jobs.py` (17) + `test_jobs_api.py` (9) + extended `test_mirror_does_not_leak.py`; full suite **1118 passed**, `audit-docs` clean. As-built map in §12.7. **Not yet: the `fieldkit v0.16.0` tag/publish + the Phase-1 launch article + a live-sidecar human-eye pass.** | Manav (with Claude) |
| 2026-06-02 | **M9 cost-plane milestone authored (§13).** Realizes `_FLOWS` §3 **Bet 6** as the first cross-cutting Arena milestone after M8 (priority locked in `_SPECS/index.md` Planned queue). 10 locked decisions (M9-1…10, **signed off** — persist the already-computed `_compare_cost_usd()`; per-side cost on `compare_responses` + `tokens_in`; aggregate `$/quality-point` on the public `leaderboard_rows`; `openrouter_price_snapshot` pinned from the H6 evidence JSON; real `usage` tokens w/ heuristic fallback; ledger-not-governor scope boundary; version-control the untracked H6 evidence). Schema `user_version` **4→5** — the first ALTER-based migration (R18). 3 new risks (R18–R20). New abstraction `fieldkit.cost`. Grounded against `roadmap-reconciliation.md` §"Bet 6" (`hermes-cost-routing`: 25% spend cut at 8.3% quality cost, 33% leak). **Spec only — unbuilt;** release gate ~`fieldkit v0.17.0`. | Manav (with Claude) |
| 2026-06-02 | **M10 recall-layer milestone authored (§14).** Realizes `_FLOWS` §3 **Bet 5** as the second cross-cutting Arena milestone (priority locked in `_SPECS/index.md` Planned queue; rides the shipped M8 pane, freshest grounding post-re-index). 12 locked decisions (M10-1…12, **signed off** — promote the pre-drilled `reindex`/`rag_eval`/`scout_ingest` job stubs to dispatchable; `fieldkit.memory` over the existing `fieldkit.rag.Pipeline` w/ the Pipeline adopted as canonical ingest; multi-source [prose · lineage/eval · scout/deep-research] under one provenance card on `blog_chunks`; trust-filtered retrieval; arena.db `5→6` + pgvector provenance cols; wrap the on-disk `rag-eval-work/` harness as the eval-gated `rag_eval` job; cosine-only GB10 baseline w/ rerank as bounded drift; coverage = `article_index`⋈index; single query backend behind both MCP surfaces; two-list mirror; version-control the external `ingest_blog.py`/`qa-eval`/eval-config/SB-server). 4 open calls signed off "recommended" (ingest fork → Pipeline canonical; query backend → `fieldkit.memory`; provenance → `blog_chunks` columns; VC the external assets). Schema `user_version` **5→6** (contingent on M9's 4→5). 3 new risks (R21–R23). New abstraction `fieldkit.memory`. Code-reconciled against the built `arena/jobs.py` (sockets pre-drilled), `fieldkit.rag`, the on-disk `rag-eval-work/` + `second-brain-mcp/`. **Spec only — unbuilt;** release gate ~`fieldkit v0.18.0`. **Next stub: `autonomous-harness-v1.md` (Phase 2).** | Manav (with Claude) |
| 2026-06-02 | **M11 autonomous-harness milestone authored (§15).** Realizes `_FLOWS` §3 **Phase 2 / Bet 2** as the **hands** — placement chosen to land as an Arena section (§15/M11), consistent with M8/M9/M10, rather than the standalone `_SPECS/autonomous-harness-v1.md` the roadmap originally named. 9 locked decisions (AH-1…9, **signed off** — a `/schedule` cron over the *already-built* `drain_jobs()`/`check_and_enqueue_regressions()`, single-lane sequential; hook battery 1→N [post-publish/pre-commit/post-article/Stop]; morning-standup as a stage-only Arena render; new `fieldkit.budget` governor w/ `LOCAL_CEILING=33%` failure-mode escalation; M9 cost-plane a **soft** prerequisite [token+envelope fallback when `fieldkit.cost` absent]; freshness-monitor emits M8 triggers [Ch-11's box]; scope = the autonomy layer NOT new job kinds; two-layer containment carried forward; **no new arena.db table / no `user_version` bump**). 3 new risks (R24–R26: overnight OOM · hook-blocks-commit · errant push/leak). New abstraction `fieldkit.budget`. Code-reconciled against the built `arena/jobs.py` (drain + regression producer pre-built, comments name the Phase-2 cron), the absent `fieldkit.budget`/`fieldkit.cost`, the one live `.claude/` hook, and the stale `scheduled_tasks.lock`. **Spec only — unbuilt;** release gate ~`fieldkit v0.19.0`. **Last stub: `rlvr-loop-v1.md` (Phase 3 — the engine).** | Manav (with Claude) |

## 17. References

### Internal
- Plan workspace: `/home/nvidia/.claude/plans/let-s-plan-for-2-curious-thacker.md`
- Spec format precedents: `_SPECS/hermes-harness-v1.md` (closest sibling), `_SPECS/notebooks-as-artifacts-v1.md`, `_SPECS/patent-strategist-v1.md`
- Editorial arcs: `.claude/skills/tech-writer/references/use-case-arc.md`
- Hermes brain pin (the resident lane): `articles/picking-the-hermes-brain-on-spark/`
- H5 vertical router (compare-routing v0.2 surface): `articles/hermes-vertical-router-on-spark/`
- H6 cost router (Compare B-lane substrate): `articles/hermes-cost-routing-local-and-openrouter/`
- H4 fieldkit-MCP (the trajectory replay shape; M8 dispatch surface): `articles/hermes-drives-the-spark-via-fieldkit-mcp/`
- H3 harness hardening (M8 sandbox containment layer): `articles/hardening-the-hermes-harness-on-spark/`
- **MTBM roadmap (M8 = Phase 1 / Bet 3):** `_FLOWS/the-machine-that-builds-machines.md` §3
- **M8 grounding (CONFIRMED, operational):** `_SPECS/roadmap-reconciliation.md` §"Phase 1" + the "Arena M8" spec-feedable facts
- Series page (the trap): `src/pages/series/[series].astro` `SERIES_COPY`
- Artifact schema: `src/content.config.ts` (`SERIES`, `ARTIFACT_KINDS`, `FIELDKIT_MODULES`)
- fieldkit modules reused: `fieldkit/src/fieldkit/{harness,eval,viz,notebook,publish,capabilities}/`

### External
- arena.ai (the comparison surface this diverges from): https://arena.ai/
- LMSYS FastChat (battle-mode UI patterns): https://github.com/lm-sys/FastChat
- Astro Islands docs: https://docs.astro.build/en/concepts/islands/
- FastAPI + sse-starlette streaming: https://github.com/sysid/sse-starlette
- uPlot (telemetry chart library): https://github.com/leeoniya/uPlot
- aiosqlite (async SQLite for FastAPI): https://github.com/omnilib/aiosqlite
- arq (async task queue): https://arq-docs.helpmanual.io/
- OpenRouter API (Compare B-lane): https://openrouter.ai/docs

### Memory cross-references (`[[name]]`)
- `[[project_hermes_brain_pinned_moe]]` — the resident brain Arena treats as truth
- `[[reference_hermes_harness_on_spark]]` — `~/.hermes/config.yaml` shape Arena reads
- `[[project_spark_unified_memory_oom]]` — the 128 GB envelope `serve_lane(guard=True)` enforces
- `[[feedback_vllm_engine_core_orphan]]` — vLLM teardown sweep `serve_lane` already handles
- `[[feedback_nim_think_prefix_convention]]` — `<think>` prefix split in chat lane
- `[[feedback_keep_scorer_local_until_reuse]]` — rubric promotion discipline (§3.1 #10)
- `[[feedback_llm_skill_pattern]]` — generation boundary (§3.1 #9); applies to curator skill
- `[[feedback_terminal_bang_unavailable]]` — Stop-hook via `~/.claude/settings.json`, NOT terminal `!`
- `[[feedback_handoff_md_update_protocol]]` — HANDOFF tail discipline; Arena Track section
- `[[feedback_ideas_docs_living]]` — `ideas/spark-arena.md` refresh discipline
- `[[reference_sync_workflow_nfs_mount]]` — Mac SMB-mount contract; `_staging/` + atomic rename
- `[[reference_destination_overrides_mirror]]` — Mac-vs-Spark URL ownership boundary
- `[[reference_fieldkit_notebook_module]]` — `OpenAICompatClient` / `split_think` chat client
- `[[project_orionfold_parent_brand]]` — Orionfold HF namespace for the leaderboard dataset
- `[[project_publishing_to_ainative]]` — `ainative.business/arena/` destination
- `[[feedback_refresh_stats_on_publish]]` — stats refresh at M7 cut
- `[[feedback_customer_link_audit]]` — A1 article customer-link audit
