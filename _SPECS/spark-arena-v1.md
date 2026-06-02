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

## 12. Change log

| Date | Change | Author |
|---|---|---|
| 2026-05-28 | Initial spec landed (v1.0 locked). Decisions §3.1 #1–#10 confirmed in the planning session (hybrid Astro + FastAPI · rubric-deterministic compare · anchor MVP scope · public-mirror distribution · new Cockpit series · `arena_run` artifact kind · Qwen3-30B-A3B brain as the resident lane · OpenRouter via H6 CostRouterConfig as default compare B-lane · deterministic generation boundary · scorer-reuse discipline). Plan workspace: `/home/nvidia/.claude/plans/let-s-plan-for-2-curious-thacker.md`. | Manav (with Claude planning session) |

## 13. References

### Internal
- Plan workspace: `/home/nvidia/.claude/plans/let-s-plan-for-2-curious-thacker.md`
- Spec format precedents: `_SPECS/hermes-harness-v1.md` (closest sibling), `_SPECS/notebooks-as-artifacts-v1.md`, `_SPECS/patent-strategist-v1.md`
- Editorial arcs: `.claude/skills/tech-writer/references/use-case-arc.md`
- Hermes brain pin (the resident lane): `articles/picking-the-hermes-brain-on-spark/`
- H5 vertical router (compare-routing v0.2 surface): `articles/hermes-vertical-router-on-spark/`
- H6 cost router (Compare B-lane substrate): `articles/hermes-cost-routing-local-and-openrouter/`
- H4 fieldkit-MCP (the trajectory replay shape): `articles/hermes-drives-the-spark-via-fieldkit-mcp/`
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
