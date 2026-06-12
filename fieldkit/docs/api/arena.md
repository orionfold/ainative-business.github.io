---
module: arena
title: fieldkit.arena
summary: Operator cockpit for the Spark — a local FastAPI sidecar streaming telemetry, chat, and side-by-side compares over a SQLite store, with a leak-proof mirror that publishes the leaderboard to this site.
order: 13
---

## What it is

The Harnesses arc taught the project to publish *agent harnesses* — Hermes drives Spark, fieldkit-as-MCP keystone, vertical + cost routers. `fieldkit.arena` is the **operator** counterpart: the cockpit a solo Spark builder uses to drive every artifact the rest of the package has shipped. Six months of work has accreted 49 articles, 17 manifests under `src/content/artifacts/`, 13 HF repos under the `Orionfold/` namespace, and a 950-test `fieldkit` substrate — none of it had a single surface to drive it from until now. The cockpit lives at `http://127.0.0.1:7866/arena/` (loopback only) with a static slice mirrored to `ainative.business/arena/`. Per `feedback_llm_skill_pattern` the module is **deterministic Python only** — all LLM generation (rubric prompts, prose) stays in session-driven skills.

The full design is in `_SPECS/spark-arena-v1.md`. M2 ships the SQLite store + the retroactive importer; M3–M7 fill the substantive sidecar surface (see `[Unreleased]` in `CHANGELOG.md`).

> **Status: v0.2 product leap — Orionfold Arena.** Builds on the M1–M6 sidecar with six showcase surfaces: a Models/capabilities browser, the cost/quality efficiency frontier, Compare markdown+winner+delta parity, a ⌘K command palette, the telemetry↔article-evidence bridge, and the **Lab** co-iteration board (`/arena/lab/`) with an operator-private `lab_notes` annotation layer (`GET/POST/DELETE /api/lab/notes`; on `FORBIDDEN_TABLES`). Distribution: the runnable cockpit now ships **inside the fieldkit wheel** — `pip install fieldkit[arena]` → `fieldkit arena up` → `http://127.0.0.1:7866/arena/` — baked by `fieldkit arena build` and served via a `StaticFiles` mount. The leak gate `fieldkit/tests/arena/test_mirror_does_not_leak.py` still pins zero operator-private leaks (chat + `lab_notes`). The full breakdown lives in HANDOFF.md's 🏟️ ARENA TRACK section.

## Public API (today — M6)

```python
from fieldkit.arena import (
    # version pin
    ARENA_SURFACE_VERSION,
    # constants — operator-visible, frozen at spec §3.4
    DEFAULT_ARENA_PORT,   # 7866
    DEFAULT_ARENA_DB,     # "~/.fieldkit/arena.db"
    # errors (hierarchy stable from day one)
    ArenaError,
    LaneNotRegistered,
    PublishableSliceEmpty,
    # M2 — synchronous SQLite store + the retroactive-load surface
    ArenaStore,
    ImportReport,
    import_artifacts,
    # M2 — row records (the importer constructs these; the store persists them)
    LaneRecord,
    BenchResultRow,
    ArticleIndexRow,
    HfMetaRow,
    NotebookExportRow,
    LeaderboardRow,
    # M3 — FastAPI sidecar (lazy: import is stdlib-cheap; calling
    # `create_app()` pulls FastAPI + sse-starlette behind the `arena` extra)
    create_app,
    serve,
    TelemetryHub,
    # M4 — chat session + turn records (operator-private; never mirrored)
    ChatSessionRecord,
    ChatTurnRecord,
    # M5 — compare / rubric-score / human-pref records + the default
    # rubric registry the side-by-side compare scores against
    CompareRunRecord,
    CompareResponseRecord,
    RubricScoreRecord,
    HumanPrefRecord,
    RubricSpec,
    DEFAULT_RUBRIC_REGISTRY,
    default_rubric_for_prompt,
    # M6 — leak-proof public mirror exporter. Hardcoded allowlist guard;
    # chat_* tables NEVER enumerated. The regression test
    # fieldkit/tests/arena/test_mirror_does_not_leak.py pins zero leaks
    # against random-UUID sentinels (the M7-blocker gate).
    export_publishable_slice,
    rebuild_leaderboard,
    ExportReport,
    RebuildReport,
    MIRROR_SCHEMA_VERSION,
    PUBLISHABLE_TABLES,
    FORBIDDEN_TABLES,
    FORBIDDEN_COLUMNS,
    # M8 — control-plane queue (operator-private; never mirrored). The job
    # records, the dispatcher (executes through the fieldkit.harness MCP
    # surface), and the leaderboard-regression trigger producer. See §12.
    JobRecord,
    JobTriggerRecord,
    JobKind,
    JobStatus,
    enqueue_job,
    dispatch_job,
    drain_jobs,
    detect_leaderboard_regression,
    enqueue_regressions,
    JobDispatchError,
    UnknownJobKind,
)
```

### M3 — `create_app()` + the sidecar endpoints

The FastAPI app factory. Lazy on FastAPI / sse-starlette / uvicorn imports, so `import fieldkit.arena.server` is stdlib-cheap and the failure mode without the `arena` extra installed is a clear `RuntimeError` pointing the operator at `pip install 'fieldkit[arena]'`.

```python
from fieldkit.arena import create_app
app = create_app(repo_root="/home/nvidia/ainative-business.github.io", telemetry_interval=0.5)
# Mount under uvicorn, or use fieldkit.arena.serve(...)
```

| Kwarg | Default | What it does |
|---|---|---|
| `db` | `~/.fieldkit/arena.db` | Operator-private SQLite path. Created lazily by `ArenaStore.initialize()` on first read. |
| `repo_root` | `Path.cwd()` | Source-of-truth for the static mirror JSON (`src/data/arena-mirror/leaderboard.json`). Pass explicitly when running the sidecar from a different cwd. |
| `telemetry_interval` | `0.5` (spec §4.6) | Seconds between SSE telemetry ticks while a subscriber is open. Set lower for unit smokes; the spec's hardware-shape claim is 500 ms. |
| `cors_origins` | dev set (`:4321` + `localhost` + Spark LAN IP) | Astro dev page at `:4321` needs CORS to reach the sidecar at `:7866`. Production mirror has no live fetches. |

#### Endpoints

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/healthz` | Liveness + `ARENA_SURFACE_VERSION` + `subscribers` count + `telemetry_running` flag. |
| `GET` | `/api/lanes` | Live read: `resident` brain from `~/.hermes/config.yaml` (re-read every request per Risk R8) + `roster` from the M2 `lanes` table (empty if the store doesn't exist yet). |
| `GET` | `/api/leaderboard?limit=N` | Proxies the static mirror JSON. M5 will rebuild this from `compare_runs` / `rubric_scores`; M3 reads what M2 seeded. |
| `GET` | `/api/telemetry/stream` | SSE — one `telemetry` event per `telemetry_interval` while subscribed; payload shape per spec §4.6 (`ts`, `gpu_util`, `gpu_temp_c`, `unified_used_gb`, `unified_total_gb`, `inflight`, `tok_per_s`, `ttft_ms`, `lane_id`). Yields a `hello` payload immediately on subscribe so the gauge paints without waiting for the first sampler interval. |

### M3 — `serve(host, port, ...)`

Thin uvicorn launcher. Loopback-only by default (no auth in v0.1 per spec §3.1 #4); pass `--reload` to use uvicorn's source-watcher (works because the launcher swaps to import-string mode and reads `ARENA_DB` / `ARENA_REPO_ROOT` env vars to reconstruct `create_app(...)` inside the worker process).

```bash
fieldkit arena serve --port 7866 --repo-root /home/nvidia/ainative-business.github.io
```

| Kwarg | Default | What it does |
|---|---|---|
| `host` | `"127.0.0.1"` | Loopback by default; pass `0.0.0.0` to expose on the LAN (no auth in v0.1 per spec §3.1 #4). |
| `port` | `DEFAULT_ARENA_PORT` (7866) | Spec §3.4 — locked. |
| `db` | `~/.fieldkit/arena.db` | Operator-private SQLite path. |
| `repo_root` | cwd | Where to find `src/data/arena-mirror/leaderboard.json`. |
| `reload` | `False` | uvicorn `--reload`; swaps the launcher to an import-string and threads `ARENA_DB` / `ARENA_REPO_ROOT` env vars into the worker process. |
| `log_level` | `"info"` | uvicorn log level (`"debug"` is useful during M3 SSE bring-up). |

### M3 — `TelemetryHub`

Reference-counted wrapper around `fieldkit.harness.Telemetry`. The first SSE subscriber attaches the underlying sampler; the last one to disconnect stops it (spec §4.6 zero-idle commitment). Layered on top of `Telemetry` rather than modifying it — keeps the harness module stable.

| Attribute / Method | What it does |
|---|---|
| `TelemetryHub(interval=0.5)` | Construct; sampler starts on first `subscribe()`. |
| `.subscribe(loop)` | Returns `(asyncio.Queue, unsubscribe_callable)`. First subscriber starts the sampler; `unsubscribe()` is idempotent. |
| `.subscriber_count` | Current attached subscriber count (thread-safe). |
| `.is_running` | True between the first `subscribe` and the last `unsubscribe`. |
| `.report_inflight(inflight, tok_per_s, ttft_ms, lane_id)` | M4+ stream callers tag the active lane + speeds; idle ticks read these as sticky defaults until refreshed. |

### M3 — `telemetry_event_stream(hub, request)`

Async generator powering `/api/telemetry/stream`. Extracted out of the route closure so unit tests can drive it directly against an in-memory queue (no FastAPI / sse-starlette round-trip needed) — see `fieldkit/tests/arena/test_server.py`.

### M4 — `POST /api/chat/stream`

Single-lane chat against the resident brain. Resolves the lane from `~/.hermes/config.yaml` on every request (Risk R8 — operator config edits take effect on the next turn). Streams via SSE; persists user + assistant turns to `chat_sessions` + `chat_turns` (operator-private; the M6 mirror exporter's hardcoded allowlist hardcodes `chat_*` tables OUT of its enumeration).

Request body (Pydantic):

| Field | Default | Notes |
|---|---|---|
| `prompt` | required | 1–32 000 chars. The user's turn for this round. |
| `session_id` | `None` | Omit on the first turn; the server allocates one + echoes it in the `start` event. Thread it back on subsequent turns to keep the multi-turn history in the same session. |
| `rubric_id` | `None` | Reserved for M5 score-on-completion (`rubric_scores`); ignored at M4. |
| `max_tokens` | `4096` | Per-turn budget. Qwen3-30B-A3B with `--reasoning-format none` emits a long `<think>` chain — truncating loses the answer. |
| `temperature` | `0.0` | Deterministic by default — the cockpit is for measured comparisons. |

Emitted SSE events:

- `start` — `{session_id, lane_id, model, base_url}`. Painted by the client as the conversation header / lane chip.
- `token` — `{channel: "reasoning"|"content", text: "..."}`. One per upstream chunk; the channel classifier flips at the `<think>` / `</think>` boundary, so the UI collapses the reasoning into a `<details>` block by default.
- `done` — `{session_id, turn_id, ttft_ms, tok_per_s, tokens_out, wall_s, finish_reason}`. The client pins the perf metadata to the assistant card footer.
- `error` — `{detail}` (on upstream stream errors). The partial reply is still persisted with `finish_reason="error"` so the operator can forensic it.
- `heartbeat` — `{}` (sse-starlette's keepalive on a >60s idle).

Returns 503 if `~/.hermes/config.yaml` doesn't carry a usable `model.base_url`. The route wires `TelemetryHub.report_inflight(inflight=True, tok_per_s=..., ttft_ms=..., lane_id=...)` on stream start + ~every 16 tokens, then `inflight=False` on done — that's the visible M3↔M4 round-trip the spec §4.2 review validates.

### M4 — `chat_event_stream(*, hub, request, body, resident, db_path)`

Async generator powering `POST /api/chat/stream`. Extracted out of the route closure so unit tests can drive it directly against a stub of `OpenAICompatClient` (no live `llama-server` needed) — see `test_chat_event_stream_emits_start_token_done` + the two persistence + telemetry-wiring tests in `fieldkit/tests/arena/test_server.py`.

### M4 — `ChatSessionRecord` / `ChatTurnRecord`

Stdlib dataclasses mirroring the spec §4.8 `chat_sessions` + `chat_turns` columns. Both default `publishable=0` (operator-private). The M6 mirror exporter's table allowlist hardcodes the `chat_*` tables out, so even rows the operator opts to promote (a future v0.2 workflow) never leak through the bulk mirror path.

| Record | Table | Key columns |
|---|---|---|
| `ChatSessionRecord` | `chat_sessions` | `id` (FK target for `chat_turns.session_id`) |
| `ChatTurnRecord` | `chat_turns` | `(session_id, ord)` UNIQUE — append-only |

`ArenaStore` exposes four helpers for these:

| Method | Returns | Notes |
|---|---|---|
| `.upsert_chat_session(row)` | `None` | `INSERT OR REPLACE INTO chat_sessions …`; row may be a mapping or `ChatSessionRecord`. |
| `.append_chat_turn(row)` | `int` | Strict `INSERT INTO chat_turns …` (the `(session_id, ord)` UNIQUE is meaningful — duplicate ord is a programming error). Returns the rowid. |
| `.chat_session(session_id)` | `sqlite3.Row \| None` | Lookup by id. |
| `.chat_turns(session_id)` | `list[sqlite3.Row]` | All turns for a session, ordered by `ord`. |

### M5 — `POST /api/compare/stream`

Side-by-side rubric-scored compare against the resident brain (lane A — always; the single-brain envelope per `[[project_spark_unified_memory_oom]]` and spec §4.9 doesn't allow two warm local lanes in v0.1) and a configurable B-lane. Default B is the OpenRouter frontier tier reached via the H6 `CostRouterConfig` (snapshot prices in the H6 article evidence; no concurrent local warm — safe by construction). Explicit two-local-lanes mode (`lane_b="local:<id>"`) emits a structured error in v0.1 (`code: "two_local_lanes_v0_2_only"`) so the UI can show the v0.2 affordance.

Body (Pydantic):

| Field | Default | Notes |
|---|---|---|
| `prompt` | required | 1–32 000 chars. |
| `lane_b` | `"openrouter"` | `"openrouter"` (default, H6 frontier tier) or `"local:<lane_id>"` (v0.2). |
| `rubric_id` | `None` | Server picks from `default_rubric_for_prompt` when absent — patent prompts → `patent_claim_validity`, MCQ → `mcq_letter`, free-form → `generic-correctness`. |
| `max_tokens` | `4096` | Per-side token budget. |
| `temperature` | `0.0` | Deterministic by default. |

Emitted SSE events (spec §4.3 event sequence):

- `start_a` — `{run_id, side: "A", lane_id, model, base_url, rubric_id}`. Painted as the A-column header; `run_id` threads back into the eventual `POST /api/prefs` call.
- `token_a` — `{channel: "reasoning"|"content", text}`. Channel classifier flips at the `<think>` / `</think>` boundary.
- `done_a` — `{ttft_ms, tok_per_s, tokens_out, wall_s, finish_reason}`. Pinned to the A-column footer.
- `start_b` — `{side: "B", lane_id, model, base_url, no_key?}`. `no_key: true` flags the OpenRouter-key-missing stub path so the UI can show an actionable "set OPENROUTER_API_KEY" message.
- `token_b` / `done_b` — same shape as A.
- `score` — `{run_id, rubric_id, a: {total, checks: [{name, kind, ok, why}]}, b: {…}, deltas: {score, speed_tok_per_s}}`. Per-check `ok` + `why` strings paint under each side.
- `error` — `{detail, code?, side?}`. The `two_local_lanes_v0_2_only` code is the v0.1 advisory.

Returns 503 if `~/.hermes/config.yaml` doesn't carry a usable `model.base_url`. The route wires `TelemetryHub.report_inflight(inflight=True, ...)` on each side's stream start + ~every 16 tokens, then `inflight=False` on score. Persistence: one `compare_runs` header row (`publishable=1`), two `compare_responses` rows (one per side), two `rubric_scores` rows (per side), all under the same `run_id`.

### M5 — `compare_event_stream(*, hub, request, body, resident, db_path)`

Async generator powering `POST /api/compare/stream`. Extracted out of the route closure so unit tests drive it directly against stub clients (no live `llama-server` or OpenRouter needed) — see `test_compare_event_stream_emits_full_sse_sequence` + the persistence + thumbs-no-mutation + stub-no-key + two-local-lanes-v0.2 tests in `fieldkit/tests/arena/test_server.py`.

### M5 — `GET /api/rubrics`

Returns the default rubric registry — three deterministic rubrics ship with v0.1. Each entry carries an `id`, `title`, `description`, and a flat list of check `kinds` so the picker dropdown can render the right column shape under each side.

| Id | Title | Check kind | What it asserts |
|---|---|---|---|
| `generic-correctness` | Generic correctness | `regex` | Answer is non-empty (alphanumeric token present). The floor rubric for free-form prompts. |
| `patent_claim_validity` | Patent claim validity | `substring` | Any of: `anticipation`, `obviousness`, `written description`, `enablement`, `§ 102` / `§ 103` / `§ 112`, `35 U.S.C.`. The patent-strategist canonical rubric. |
| `mcq_letter` | MCQ letter (A/B/C/D) | `regex` | Bare A/B/C/D, word-boundary, case-insensitive. The cyber-bench canonical rubric. |

Operator-supplied rubrics layer on top via `~/.fieldkit/arena/rubrics/` at M6+ (a directory walk loaded at sidecar boot); the default list is always the head.

### M5 — `POST /api/prefs`

Records one operator thumbs verdict on a compare run. **Separate signal** per spec §4.3 — writes a `human_prefs` row but does NOT mutate the corresponding `rubric_scores.total`. The leaderboard (M6) surfaces this as `human_pref_winrate` only at ≥5 prefs per lane.

| Field | Notes |
|---|---|
| `compare_run_id` | The id from the `start_a` event. 404 on unknown. |
| `winner` | `"A"`, `"B"`, or `"tie"` (Pydantic-validated). |
| `note` | Optional free text (≤2000 chars). |

Returns `{ok, pref_id, compare_run_id, n_prefs}` — the count lets the picker UX lock further clicks once the operator has voted.

### M5 — `RubricSpec` / `DEFAULT_RUBRIC_REGISTRY` / `default_rubric_for_prompt`

Frozen Python data — no YAML round-trip at runtime. `RubricSpec` is the registry entry (id + title + description + executable `fieldkit.eval.Rubric`); `DEFAULT_RUBRIC_REGISTRY` is the 3-entry built-in dict; `default_rubric_for_prompt(prompt)` is a substring-sweep picker (patent triggers → `patent_claim_validity`; `(a)` / `(b)` / `(c)` / `(d)` / `multiple choice` → `mcq_letter`; otherwise `generic-correctness`).

| Helper | Returns | Notes |
|---|---|---|
| `list_rubrics(registry=None)` | `list[dict]` | JSON-safe shape for `GET /api/rubrics`. |
| `get_rubric(id, *, registry=None)` | `RubricSpec \| None` | Lookup, or `None` (the compare path falls through to `generic-correctness` rather than raising). |
| `default_rubric_for_prompt(prompt)` | `str` | The spec §4.3 picker. Pure function, no I/O. |

### M5 — `CompareRunRecord` / `CompareResponseRecord` / `RubricScoreRecord` / `HumanPrefRecord`

Stdlib dataclasses mirroring the spec §4.8 `compare_runs` / `compare_responses` / `rubric_scores` / `human_prefs` columns. `CompareRunRecord` defaults `publishable=1` — compare runs are the public-facing slice of the cockpit. `CompareResponseRecord` keys on `(compare_run_id, side)`. `RubricScoreRecord` carries the JSON-serialized `checks_json` (one entry per `CheckResult`); the SQL CHECK constraint enforces at-least-one of `compare_run_id` / `chat_turn_id` is set.

| Record | Table | Key columns |
|---|---|---|
| `CompareRunRecord` | `compare_runs` | `id` |
| `CompareResponseRecord` | `compare_responses` | `(compare_run_id, side)` UNIQUE |
| `RubricScoreRecord` | `rubric_scores` | autoincrement `id`; FK back to compare_run_id or chat_turn_id |
| `HumanPrefRecord` | `human_prefs` | `id` |

`ArenaStore` exposes seven helpers for these — `upsert_compare_run` / `upsert_compare_response` / `append_rubric_score` (returns rowid) / `append_human_pref` / `compare_run(id)` / `compare_responses(id)` / `rubric_scores_for_run(id)` / `human_prefs_for_run(id)`.

### M6 — `export_publishable_slice(store, out_dir, *, allow_empty, rebuild, repo_root)`

The leak-proof boundary between the operator-private cockpit DB and the public mirror at `ainative.business/arena/`. Reads ONLY columns listed in `PUBLISHABLE_TABLES`; the `chat_*` tables and `compare_runs.prompt` / `compare_responses.content` / `compare_responses.reasoning` are never enumerated by any code path. Writes to `<out_dir>/_staging/leaderboard.json` first, fully `fsync`'d, then atomic-renames onto `<out_dir>/leaderboard.json` per `[[reference_sync_workflow_nfs_mount]]`.

```python
from fieldkit.arena import export_publishable_slice, ArenaStore

store = ArenaStore()
store.initialize()
with store:
    report = export_publishable_slice(store, out_dir="src/data/arena-mirror")
print(report.summary_line())
# → bench=12 live=2 compare_runs=4 rubric_scores=4 human_prefs=2 lanes=50
```

| Kwarg | Default | What it does |
|---|---|---|
| `store` | — | An open `ArenaStore`; caller is responsible for `.initialize()`. |
| `out_dir` | `"src/data/arena-mirror"` | Target dir for the JSON files; resolved against `repo_root` if relative. |
| `allow_empty` | `False` | If False, refuse to write a zero-row leaderboard export (guard against blanking the public mirror). |
| `rebuild` | `True` | If True, run `rebuild_leaderboard` as a pre-step. Set False if the caller has already rebuilt. |
| `repo_root` | `None` | Override for resolving a relative `out_dir` (mainly for tests). |

Returns `ExportReport` (file paths + per-table counts + optional `RebuildReport` subreport). Raises `PublishableSliceEmpty` if `allow_empty=False` and both bench + live row counts would be zero.

### M6 — `rebuild_leaderboard(store)`

Recomputes `leaderboard_rows` from `bench_results` (one row per `(bench_slug, variant_label)` with non-null pass-rate) + the live `compare_runs × rubric_scores × human_prefs` join (one row per `(rubric_id, lane_id)` aggregated across publishable runs). Live-cockpit rows use `bench_id="cockpit:{rubric_id}"` so they sort separately from bench-anchored rows. Human-pref winrate is gated at ≥5 prefs per spec §4.4 — under threshold the column is `None`.

Idempotent — re-running over the same DB produces identical rows. Returns `RebuildReport(bench_rows_written, cockpit_rows_written, total_rows)`. Implicitly run inside `export_publishable_slice` unless `rebuild=False`.

### M6 — Allowlist constants

`fieldkit.arena.mirror` surfaces three load-bearing constants the regression test pins against:

| Constant | Shape | What |
|---|---|---|
| `PUBLISHABLE_TABLES` | `dict[str, tuple[str, ...]]` | The hardcoded allowlist. The exporter NEVER reads a column from a table that isn't a key here, and NEVER reads a column from a publishable table that isn't in its tuple. `compare_runs` exposes `redacted_prompt` but NOT `prompt`. `compare_responses` exposes `tokens_out` / `tok_per_s` / `unified_peak_gb` but NOT `content` / `reasoning`. |
| `FORBIDDEN_TABLES` | `tuple[str, ...]` | `("chat_sessions", "chat_turns", "lab_notes")`. Belt over the allowlist's suspenders — the exporter does not reference these by name; the regression test asserts the table NAMES don't appear in the emitted JSON either. `lab_notes` added at v0.2 (operator-private Lab annotations). |
| `FORBIDDEN_COLUMNS` | `tuple[tuple[str, str], ...]` | The (table, column) pairs that MUST NOT leak. `(compare_runs, prompt)`, `(compare_responses, content)`, `(compare_responses, reasoning)`, the `chat_turns` columns, `(lab_notes, body)`, plus `(jobs, payload_json)` (M8). |
| `MIRROR_SCHEMA_VERSION` | `int` | Bumped to `2` for M6 (was `1` at M2). Adds `bench_rows` / `live_rows` arrays alongside the legacy `rows` alias. |

## M8 — Arena as the control plane

The M8 milestone (`_SPECS/spark-arena-v1.md` §12) promotes Arena from a **recorder** into a **dispatcher** — the place the operator triggers work from. `~/.fieldkit/arena.db` gains three operator-private tables (additive + idempotent over the v0.2 schema): `jobs` (the queue spine) and `job_triggers` (the audit trail) at `PRAGMA user_version = 3`, plus `leaderboard_baseline` (the regression detector's prev-snapshot store) at `user_version = 4`. All three are on `FORBIDDEN_TABLES`; `(jobs, payload_json)` is on `FORBIDDEN_COLUMNS` — job payloads carry prompts/lanes/benches and are **never** mirrored (R13). The dispatcher executes **through the `fieldkit.harness` MCP surface** (M8-1) — one execution surface shared with Hermes, so the containment rails are defined once.

### M8 — records (`fieldkit.arena.schemas`)

| Record | Table | Notes |
|---|---|---|
| `JobRecord` | `jobs` | The queue row. `kind` is `eval_rerun` / `measure_variants` (M8) or a later-phase stub; `status` ∈ `queued`/`dispatched`/`running`/`done`/`failed`/`skipped`; `payload_json` is operator-only; `dedup_key` = `(kind, lane_id, bench_id)` coalesces in-flight duplicates (R15), `None` = always-run; `arq_job_id` is the `eval_runs` socket (`None` on the M8 BackgroundTasks path). |
| `JobTriggerRecord` | `job_triggers` | What fired a job: a regression delta, a staleness age, or an operator note. `id` is AUTOINCREMENT (omit on insert). |

### M8 — `JobKind` / `JobStatus`

| Symbol | Members |
|---|---|
| `JobKind` | `EVAL_RERUN`, `MEASURE_VARIANTS` (the `DISPATCHABLE` set), plus the named-but-not-built stubs `REQUANT`, `RL_RUN`, `REINDEX`, `RAG_EVAL`, `SCOUT_INGEST`, and `SFT_RUN` (AE-29, v2 cut 3 — the **operator-armed** SFT dispatch: async-only like `RL_RUN`, and the drain releases it back to `queued` unless the draining process exports `FK_SFT_RUN_ARMED=1`; the held job never starves the queue behind it), and `LANE_LAUNCH` / `LANE_TEARDOWN` (AE-31, v2 cut 4 — guarded serve-lane launch/teardown through `launcher.py`'s pre-flight brake; refusals persist as honestly-failed rows `refused:<reason>`). `DISPATCHABLE` / `ALL` are frozensets. |
| `JobStatus` | `QUEUED`, `DISPATCHED`, `RUNNING`, `DONE`, `FAILED`, `SKIPPED`; `IN_FLIGHT` is the dedup-holding subset. |

### M8 — `enqueue_job(store, kind, payload, *, trigger, priority, dedup_key, trigger_detail, now_fn)`

Writes one `queued` row and returns its id, or `None` when an in-flight job already holds the `dedup_key` (the R15 coalesce). Records a `job_triggers` audit row when `trigger_detail` is given.

| Kwarg | Default | What it does |
|---|---|---|
| `trigger` | `"manual"` | Provenance: `manual` / `leaderboard_regression` / `stale_bench` / … |
| `priority` | `0` | Higher drains first (regression confirmations enqueue at `1`). |
| `dedup_key` | `(kind, lane_id, bench_id)` from payload | Pass `""` to force an always-run job, or a custom key. `None`-resolving keys never coalesce. |
| `trigger_detail` | `None` | When set, also writes the `job_triggers` audit row (the regression delta / staleness age / operator note). |
| `now_fn` | UTC ISO stamp | Injectable clock (deterministic tests). |

### M8 — `dispatch_job(store, job, *, runner, now_fn)` / `drain_jobs(store, *, runner, max_jobs, now_fn, on_error)`

`dispatch_job` runs one claimed job end-to-end: `running` → execute via `runner` (default `default_runner`, which calls the harness MCP tools — `run_vertical_eval` / `measure_variants`) → `done` (persisting an `eval_rerun` through the existing `eval_scores` scorer path + activating the `eval_runs` status row) or `failed` (stamping `jobs.error` + raising `JobDispatchError`). `runner` is injectable so tests dispatch without a GPU. `drain_jobs` claims the oldest `queued` job and dispatches it in a loop until empty (M8-5, sequential single-lane); `max_jobs` caps a pass, `on_error` (`"record"` default / `"raise"`) controls whether a failed job halts the drain.

### M8 — `detect_leaderboard_regression(prev, curr, *, tau)` / `enqueue_regressions(store, prev, curr, *, tau, now_fn)`

`detect_leaderboard_regression` is the pure, testable core: diff two `ArenaStore.eval_leaderboard()` accuracy-rollup snapshots and return one `{bench_id, lane_id, prev_score, new_score, delta}` per `(bench, lane)` whose `mean_normalized` dropped by more than `tau` (default `0.05`), worst-drop first. Newly-seen lanes can't regress. `enqueue_regressions` runs the detector and enqueues a confirming `eval_rerun` (priority 1, `leaderboard_regression` trigger) per regression — coalescing duplicates while one is in flight.

### M8 — `check_and_enqueue_regressions(store, *, tau, now_fn)`

The **wired** regression producer (M8-2) — the link between the pure detector and the running cockpit. Diffs the live `eval_leaderboard()` against the stored `leaderboard_baseline`, enqueues a confirming `eval_rerun` per over-`tau` drop (R15 dedup applies), then overwrites the baseline with the current snapshot. The first scan only *sets* the baseline (nothing to diff against → no enqueues), so a fresh box never storms. Returns `{checked, baselined, had_baseline, enqueued: [job_id, …], regressions: [delta, …]}`. Operator-triggered via `POST /api/jobs/check-regressions` (a Jobs-page button); the Phase-2 cron calls the same path on a schedule.

### M8 — `resolve_bench(bench_id, *, bench_dir)` / `DEFAULT_BENCH_DIR`

Resolves a `bench_id` → `{bench_path, scorer, max_tokens, limit}` from the **bench registry** — a directory (`$ARENA_BENCH_DIR` or `DEFAULT_BENCH_DIR` = `~/.fieldkit/arena/benches`) holding one `<bench_id>.jsonl` gold set per bench, with an optional `<bench_id>.meta.json` sidecar overriding the scorer (default `exact_match`) and the eval knobs. Returns `None` when no gold set is registered. `default_runner` calls this to fill an `eval_rerun`'s `bench_path` when the job payload (a regression trigger, the UI dispatch form) carries only a `bench_id`; an unresolvable bench raises `BenchNotRegistered` naming the exact path searched, rather than failing opaquely deep in the eval tool. An explicit payload `bench_path` still wins.

### M8 — errors

| Error | Raised when |
|---|---|
| `JobDispatchError` | A job failed mid-execution; the row is already marked `failed` with the message in `jobs.error`. |
| `UnknownJobKind` | An `enqueue` named a kind outside `JobKind.ALL`, or a `dispatch` named a stub outside `JobKind.DISPATCHABLE`. |
| `BenchNotRegistered` | An `eval_rerun` named a `bench_id` with no resolvable gold JSONL (no payload `bench_path`, no registered `<bench_id>.jsonl`). The message names the path searched. |

### M8 — sidecar endpoints (`/api/jobs`)

| Method | Path | Notes |
|---|---|---|
| `GET` | `/api/jobs?status=&limit=` | The board read — newest first, optional status filter. Empty (not 404) on a fresh box. |
| `POST` | `/api/jobs` | Enqueue `{kind, payload, trigger, priority, dispatch}`. `dispatch=True` (default) drains the queue in a BackgroundTask (the M8 primary single-lane path, R14 — no arq/Redis). Returns `coalesced=True` when the dedup gate fires. |
| `POST` | `/api/jobs/check-regressions?tau=&dispatch=` | Scan the live leaderboard vs the baseline, enqueue a `leaderboard_regression` `eval_rerun` per over-`tau` drop, re-baseline. First scan only sets the baseline. Returns `{checked, had_baseline, enqueued, regressions}`. Declared before `{job_id}`. |
| `GET` | `/api/jobs/stream` | SSE — emits a full board snapshot on connect + on change (declared before `{job_id}` so it isn't captured as an id). |
| `GET` | `/api/jobs/{job_id}` | One job + its trigger trail; 404 if unknown. |
| `DELETE` | `/api/jobs/{job_id}` | Cancel a not-yet-running job (→ `skipped`); 409 if running/done, 404 if unknown. |

### M8 — store methods (`ArenaStore`)

| Method | Returns | What |
|---|---|---|
| `.enqueue_job(row)` | `str \| None` | Strict INSERT; `None` when the dedup unique-index coalesces. |
| `.record_job_trigger(row)` | `int` | Append a `job_triggers` audit row. |
| `.claim_next_job(*, dispatched_at, skip_ids=())` | `sqlite3.Row \| None` | Atomically flip the oldest `queued` job to `dispatched`. `skip_ids` (AE-29) excludes rows the current drain pass already released (an operator-armed brake), so the pass works past a held job instead of re-claiming it forever. |
| `.update_job(job_id, **fields)` / `.get_job(id)` / `.list_jobs(*, status, limit)` / `.cancel_job(id)` | — | Patch / read / board-list / cancel. |
| `.upsert_eval_run(row)` / `.update_eval_run(id, **fields)` / `.get_eval_run(id)` | — | The per-run status row M8 activates (the `arq_job_id` socket). |
| `.leaderboard_baseline()` / `.snapshot_leaderboard_baseline(rows, *, now)` | `list[Row]` / `int` | Read / full-overwrite the regression baseline (one `(bench, lane)` accuracy row each) that `check_and_enqueue_regressions` diffs against. |

## M9 — cost plane (Bet 6)

The **third ranking axis** — token economics promoted to a first-class signal
(`_SPECS/spark-arena-v1.md` §13). The cost the compare/chat path already
*computes* (`_compare_cost_usd`) is now **persisted** and **surfaced**: per-run
rows feed an aggregate `$/quality-point` on the public leaderboard, and the live
spend rail survives a sidecar restart. The full API lives in its own module —
**[`fieldkit.cost`](cost.md)** (`CostLedger`, `PriceSnapshot`,
`seed_price_snapshot`, `cost_per_quality`) — because it spans the new
`openrouter_price_snapshot` table, not just `fieldkit.arena`. It is a **ledger,
not a governor**: enforcement (`fieldkit.budget`) is Phase 2 (Arena M11, §15).

What changed inside `fieldkit.arena`:

- **Schema `user_version` 4 → 5** — the first ALTER-based migration
  (`ArenaStore._migrate` / `_add_column_if_missing`, R18). Adds the per-run cost
  columns to `chat_turns` / `compare_responses`, the aggregate
  `mean_cost_usd` / `cost_per_quality_point` to `leaderboard_rows`, and the new
  `openrouter_price_snapshot` table (seeded at `initialize()` from the baked H6
  evidence via `fieldkit.cost.seed_price_snapshot`).
- **`server.py`** — the compare `_emit_side` + chat completion paths INSERT
  `cost_usd` / `tokens_in` / `tokens_estimated` / `price_snapshot_id` onto the
  response row at the point they call `add_openrouter_cost`; `TelemetryHub.
  seed_session_spend` rehydrates the live rail from `CostLedger.session_spend()`
  at `create_app` (M9-8). Local lanes write `0.0`.
- **`mirror.py`** — `rebuild_leaderboard` computes `mean_cost_usd` (AVG over the
  bench×lane runs) + `cost_per_quality_point` (`mean_cost_usd / mean_score`,
  guard `>0`). `openrouter_price_snapshot` joins `PUBLISHABLE_TABLES` (public —
  no prompts), the two aggregate cost columns join the `leaderboard_rows`
  allowlist, and the per-run cost columns inherit their host tables' exclusion
  (M9-7, anchored by `test_mirror_does_not_leak.py`).

## M10 — recall layer (Bet 5)

The Second Brain promoted from a manual, prose-only, externally-scripted index
into a **managed, multi-source, evaluated, provenance-tagged** one the operator
drives from the cockpit (`_SPECS/spark-arena-v1.md` §14). The full ingest /
query / coverage API lives in its own module — **[`fieldkit.memory`](memory.md)**
(`MemoryIndex`, `KnowledgeCard`, `Provenance`, `ingest_sources`,
`coverage_report`, `resolve_qa_set`) — because it spans pgvector `blog_chunks`,
not just `fieldkit.arena`. It ships the **operator-driven pane + managed index**;
the autonomous re-index-on-publish hook + scheduled freshness monitor are Phase 2
(Arena M11, §15), which *consumes* this pane's re-index button + eval gate.

What changed inside `fieldkit.arena`:

- **Schema `user_version` 5 → 6** — additive `CREATE TABLE IF NOT EXISTS` for
  `reindex_runs` (per-rebuild provenance — operator-private) and `rag_eval_runs`
  (eval scores per index version — public-safe aggregates). The pgvector
  provenance ALTER lives in `fieldkit.memory.MemoryIndex.ensure_schema` (R21),
  not the arena store. Store readers/writers: `insert_reindex_run` /
  `update_reindex_run` / `reindex_runs` and `insert_rag_eval_run` /
  `rag_eval_runs` / `last_rag_eval` (the promotion-gate baseline).
- **`jobs.py`** — `reindex` / `rag_eval` / `scout_ingest` promoted from `JobKind`
  named stubs into `JobKind.DISPATCHABLE` (M10-1, the move M8 made for
  `eval_rerun`). `default_runner` dispatches each through the `fieldkit.harness`
  MCP surface (`reindex_memory` / `rag_eval_index` / `scout_ingest`);
  `_persist_reindex` writes a `reindex_runs` row, `_persist_rag_eval` writes a
  `rag_eval_runs` row and applies the **promotion gate** (M10-6 — a recall-
  dropping rebuild is flagged `promote=False`, like-for-like per R22).
- **`server.py`** — the `/api/knowledge` pane API: a degraded-safe coverage +
  trend + run-history snapshot (`GET`), `POST /api/knowledge/reindex` (+ chained
  `rag_eval`), `POST /api/knowledge/rag-eval`, and the operator-private
  `POST /api/knowledge/query` (provenance-filtered chunk text — 503 when the
  live index is unreachable). The jobs-board `kind` pattern widens to accept the
  three new dispatchable kinds.
- **`mirror.py`** — `rag_eval_runs` aggregates join `PUBLISHABLE_TABLES` for the
  public RAG-eval trend (no prompts, no chunk text); `reindex_runs` joins
  `FORBIDDEN_TABLES` (its `source_set` can name internal slugs). A knowledge-path
  sentinel anchors `test_mirror_does_not_leak.py` (M10-10).
- **Cockpit** — a new `/arena/knowledge/` pane: coverage/freshness (the
  `article_index` ⋈ index diff, M10-8), a per-source-class Re-index button, the
  RAG-eval trend (cosine-only labelled, M10-7), and the trust-tier query console.

## M11 — autonomous harness + cron (Phase 2)

The **hands** in the `pane → hands → engine` sequence
(`_SPECS/spark-arena-v1.md` §15): the missing *trigger* that turns M8's
button-driven dispatcher into a self-operating overnight loop with a human-review
gate. M11 reimplements **no dispatch** — it schedules the already-built
`drain_jobs()` + `check_and_enqueue_regressions()`, gated by the new
**[`fieldkit.budget`](budget.md)** governor (`BudgetGovernor`, `BudgetDecision`,
`SpendDigest`, `EscalationReason`, `MemoryEnvelope`, `check_budget`) — a
sibling top-level module, because the governor spans more than `fieldkit.arena`.
**No schema, no `user_version` bump (AH-9)** — the schema stays at M10's `6`;
schedules live in version-controlled config, the standup is an ephemeral render.

What changed inside `fieldkit.arena`:

- **`scheduler.py` (new)** — the cron glue (AH-1). `run_drain_cycle(store, *,
  governor=None, …)` is one tick: acquire the one-drain-at-a-time `DrainLock`
  (the `scheduled_tasks.lock` pattern with stale-pid stealing — never stacks a
  second GPU lane, R24), `drain_jobs` with the governor in the loop, the
  `check_and_enqueue_regressions` freshness sweep (AH-6 — emits the next tick's
  triggers), then `build_standup`. Returns `{skipped, drained, sweep, standup}`;
  **no push path exists by construction** (R26). `build_standup(store, *,
  governor, sweep, cap_usd)` is the AH-3 render — **Ran / Regressed / Queued /
  Spend** over the existing `jobs` / `leaderboard_baseline` / M9 cost rows,
  aggregate + operator-private (it projects `id/kind/status`, never
  `payload_json`).
- **`jobs.py`** — `drain_jobs` gains an optional `governor` (duck-typed —
  anything with `.check_budget(job) -> BudgetDecision`). Each claimed job is
  checked **before** dispatch: an *allow* dispatches; an *escalate* / *defer*
  releases the claim back to `queued`, records a `budget_<action>` audit row in
  `job_triggers`, and stops the pass (the budget brake). The drain never
  escalates or pushes itself — it *stages* the decision (AH-3/AH-8).
- **`server.py`** — `GET /api/standup` renders the standup snapshot (the cost
  ledger is read via a `BudgetGovernor(ledger=store)`; the Spend row degrades to
  "—" pre-M9, AH-5). Read-only — it never drains (an HTTP GET never launches a
  GPU lane; the cron owns dispatch). Empty (not 404) on a fresh box.
- **Cockpit** — a new `/arena/standup/` pane (the morning-review gate): the Spend
  rail + the Ran / Regressed / Failed / Queued buckets, stage-only ("the loop has
  no push path").
- **Hook battery (`.claude/`)** — the lone `SessionStart` hook expands into a
  battery (AH-2, deterministic shell only, invariant #4): `pre_commit_guard.sh`
  (PreToolUse — secret-scan **hard-blocks** a planted secret, the render verifiers
  run **advisory** per R25), `post_publish.sh` (PostToolUse — stats nudge +
  freshness-trigger enqueue on an articles/products commit), and `stop_feedback.sh`
  (the §6.5 Stop loop, finally wired — nudges on uncommitted artifact work).

## RL-lane autonomy (`lane.py`, rl-lane-autonomy v1 — LA-1..11)

The self-driving layer for the Phase-3 engine — the connective tissue that turns
a dispatchable `rl_run` (RV-6) into a run that is **self-driving, observable, and
self-defending**, without re-implementing any GPU physics. `import
fieldkit.arena.lane` stays stdlib-cheap (torch/vLLM only enter inside the lane
factory). **No schema change** (LA-7 — `user_version` stays `6`); **no new
top-level module** (it documents here, under `arena`).

- **`LaneArbiter`** (LA-1/2/6) — the envelope-gated single serving slot, a
  context manager the GPU-kind runner enters. `__enter__` runs the **3-way
  pre-flight** (governor *allow* ∧ `MemoryEnvelope.fits` ∧ a vLLM binary present
  — any failure raises `LaneDeferred` *before* anything is torn down), frees the
  resident chat brain (`stop_resident`), and starts the `MemoryWatchdog`.
  `__exit__` stops the watchdog, tears down the vLLM lane (`VLLMLane.stop`,
  EngineCore-aware — its process-pattern `pkill` reaps the seam-started server
  too), and **always** restores the prior lane (R1: never leave the box with no
  serving lane). It composes *inside* the M11 `DrainLock`, never replaces it (LA-2).
- **`MemoryWatchdog`** (LA-10, arena-wide) — enforces a unified-memory headroom
  floor off the same `/proc/meminfo` source `TelemetryHub` samples. Warns below
  `FK_RL_OOM_WARN_GB` (8); on a breach that **persists `persist_n` samples**
  (~2 s — the R6 anti-transient guard) it touches an abort sentinel the loop
  polls between steps and records the trip on the trace. It **never** trips on a
  missing sample (R7). Reusable by every GPU kind.
- **`mem_trace` / `MemTrace`** (LA-11) — the per-run memory recorder (peak,
  headroom-at-spawn, per-phase deltas, abort sample). Thread-safe; rides
  `jobs.result_json` + the standup ("RAN 1 · peak 119 GB · 1 OOM-deferred").
- **`RLLaneContext`** — the one optional object dispatch consults for an `rl_run`.
  `dispatch_job(store, job, *, rl_lane=…)` and `drain_jobs(store, *, rl_lane=…)`
  take it; when wired **and** the kind is `rl_run` the run is arbitered (pre-flight
  → resident-brain teardown → watchdog → live progress → mem-trace) and a failed
  pre-flight releases the claim back to `queued` + audits (`budget_<action>`,
  never *fails*); when `None` (the M8 default) every kind runs bare, byte-for-byte
  RV-6 behavior. Defaults read `FK_RL_OOM_*` + `FK_RL_RESIDENT_{STOP,START}_CMD`.
- **Live progress (LA-8)** — `rl_progress_writer(store, job_id, …)` builds the
  throttled single-writer callback the loop pushes `{step, phase, pool_score,
  last_heldout, eta_s, mem}` through (a write per phase-change/held-out-gate, else
  ≤ once per `throttle_s`). `_jobs_signature` gains a progress nonce so the
  `/api/jobs/stream` board re-emits while a run is `running`.
- **Async-enqueue (LA-4)** — `POST /api/jobs` now accepts `rl_run` but forces
  `dispatch=False` (RV-6): the 8.5 h loop never runs in a request's
  BackgroundTask. The response carries `async_only: true` + an autonomy note.
- **Autonomy CLI (LA-5)** — `fieldkit arena autonomy on|off|status` writes the
  reversible policy record (`fieldkit.arena.scheduler.read_autonomy_state`) and
  prints/installs the crontab line; `fieldkit arena drain` is the cron target
  (one `run_drain_cycle` tick). The standup surfaces the armed state + the RL
  memory digest. The external blocker is unchanged (a pinned aarch64+CUDA-13
  vLLM); absent it the arbiter `defer`s cleanly (`LANE_BIN_ABSENT`), so the whole
  surface ships + is GPU-free-testable now. See `docs/api/rl.md` →
  "Operator: full autonomy" + `_SPECS/rl-lane-autonomy-v1.md`.

## AE-31 — guarded lane launch + teardown (`launcher.py`, v2 cut 4)

Serving becomes an Arena operator action (risk class AE-R13 — the launch half AE-22
and the arm/teardown half AF-20 deferred from cuts 2–3). `fieldkit.arena.launcher` is
the deterministic runner behind `POST /api/jobs {kind: lane_launch | lane_teardown}`
and the LaneTruth launch form; it is a submodule (not re-exported through
`fieldkit.arena.__all__`) because its consumers are the jobs layer + the sidecar, not
library callers.

- **Recipes** — operator-authored `~/.fieldkit/arena/lane-recipes.json` (sibling of
  the AE-19 registry): the once-memorized launch command stored as data
  (`gguf_path` · `port` · `n_ctx` · `ngl` · `extra_args`). `GET /api/lane-recipes`
  lists summaries for the LaneTruth form.
- **Pre-flight brake** (`launch_lane`) — every side-effect-free check runs BEFORE
  the one destructive step: launch lock → recipe → binary → GGUF → unified-memory
  envelope (`estimate_lane_gb`) → fused ONE-LANE/port check. A resident lane refuses
  the launch unless `teardown_first` was explicitly passed — a doomed launch never
  tears a working lane down. Refusals raise `LaunchRefused` with a machine-readable
  `reason`; the jobs layer persists them as honestly-failed rows (`refused:<reason>`).
- **Infra ports** (`infra_ports`, AD-FK-1) — co-resident non-serving OpenAI-compat
  containers (default: the Cortex embedder `:8001`) are exempt from ONE-LANE and
  from the `teardown_first` sweep, and `teardown_lane` refuses them up front
  (`refused:infra_port` — never point the lane kill chain at a docker-published
  port; manage the container with its own lifecycle). The `oom_envelope` gate still
  runs against real MemAvailable, so memory safety is unchanged. Override via
  `FK_ARENA_INFRA_PORTS` (comma-separated; set EMPTY to turn the exemption off).
- **Detached spawn** — `start_new_session=True` + an atomic owner file
  (`lane_owner_path` / `read_lane_owner`), so a launched lane survives sidecar
  restarts; the cockpit never child-manages it. The warm-poll honors the per-job
  cancel sentinel (the same one `eval_rerun` polls).
- **Verified teardown** (`teardown_lane`) — owner-pid kill with a PID-reuse cmdline
  guard, targeted fallback (never a broad pkill for llama.cpp; EngineCore-aware stop
  only for vLLM-kind lanes), and a "released" gate that is **observed** (process
  group empty + port refused), never asserted.

No `arena.db` schema change; all state is files beside the AE-19 registry.

## v0.2 surfaces (Lab + distribution)

### v0.2 — Lab notes (`lab_notes` table + `/api/lab/notes`)

Operator-private annotations pinned to a Lab board card, powering `/arena/lab/`'s `<LabNotes>` island. Deterministic CRUD only — no LLM generation (`feedback_llm_skill_pattern`). The `lab_notes` table is on `FORBIDDEN_TABLES` + pinned by `test_mirror_does_not_leak.py`, so the freeform `body` is **never** mirrored.

`ArenaStore` methods: `append_lab_note(row) -> int` (append-only insert; caller stamps `created_at`), `lab_notes(card_id=None, limit=200) -> list[Row]` (newest first, optionally scoped to one card; rows carry `body` — loopback-only reads, same stance as the chat-replay endpoint), `delete_lab_note(note_id) -> bool`.

| Method | Endpoint | Body / params | Returns |
|---|---|---|---|
| `GET` | `/api/lab/notes?card_id=&limit=` | optional `card_id` scope | `{notes: [{id, card_id, lane, body, created_at, updated_at}]}` (empty list on cold DB, never 500) |
| `POST` | `/api/lab/notes` | `LabNoteRequest{card_id, body, lane?}` | `{ok, note_id, card_id, n_notes}` |
| `DELETE` | `/api/lab/notes/{note_id}` | — | `{ok, note_id}`; 404 if absent |

### v0.2 — packaged web UI (`fieldkit arena build` / `up`)

Arena's primary distribution surface is the `fieldkit` PyPI wheel. `fieldkit.arena.webui.build_webui(repo_root, *, dest, skip_astro, demo)` runs the Astro build (`base: '/arena'`) and prunes the routed pages + shared assets (raster images dropped) into a self-contained bundle. **Two modes:**

- **wheel** (default) — `ARENA_BUILD=1` → packaged `fieldkit/src/fieldkit/arena/_webui/` (declared in `pyproject.toml`'s hatch `include`); served by the sidecar's `StaticFiles` mount.
- **demo** (`demo=True`) — `ARENA_DEMO=1` → `<repo_root>/dist-arena-demo-pruned/` for the **sidecar-less public web preview** (GitHub Pages). The prune *promotes* `arena/*` to the bundle root (so `/arena/` is the cockpit and the absolute single-`/arena/` nav hrefs resolve), additionally copies the demo-only `arena-demo/` dir (the fetch/EventSource shim + recorded `fixtures.json`), and writes a `.nojekyll` marker (GitHub Pages' Jekyll would otherwise strip `assets/_slug_*.css`). Deploy = copy the bundle's contents into the publisher's `public/arena/`.

`webui_dir()` / `bundle_present()` locate the wheel bake. `create_app()` mounts it via a `StaticFiles` mount at `/arena` (`_mount_packaged_webui`, guarded — a missing bundle degrades to API-only mode). Served from the sidecar → page origin == sidecar origin == same-origin, so the islands' `resolveSidecarUrl()` resolves to their own origin and CORS is dev-only.

| CLI | What |
|---|---|
| `fieldkit arena build [--repo-root …] [--skip-astro] [--demo]` | **Builder-side only** — bake the bundle (shells out to `node node_modules/astro/astro.js build`). Default bakes the wheel bundle (run at release time); `--demo` bakes the GitHub Pages preview into `dist-arena-demo-pruned/`. |
| `fieldkit arena up [--host --port --db --open/--no-open]` | The one-command UX — serve the cockpit **and** open a browser tab. `pip install fieldkit[arena]` → `fieldkit arena up` → `http://127.0.0.1:7866/arena/`. |

### M2 — `ArenaStore`

Synchronous SQLite store at `~/.fieldkit/arena.db`. Used by the M2 importer + the future M6 mirror exporter; the M3 FastAPI sidecar opens a parallel async connection via `aiosqlite` against the same database file (SQLite handles concurrency via WAL).

| Method | Returns | Notes |
|---|---|---|
| `ArenaStore(db_path=None)` | — | Path defaults to `~/.fieldkit/arena.db` (operator-private, gitignored). |
| `.initialize()` | `None` | Creates the 13-table schema + indexes (idempotent — every DDL is `CREATE TABLE IF NOT EXISTS`); pins `PRAGMA user_version=1` for forward migration. |
| `.connect()` | `sqlite3.Connection` | Opens lazily; enables WAL + foreign keys; returns the conn for raw SQL access. |
| `.close()` | `None` | Commits + closes. Also called by the `with` block on exit. |
| `.transaction()` | `Iterator[sqlite3.Connection]` | Batch helper: commits on success, rolls back on exception. |
| `.initialize` ↔ `.user_version` | `int` | Read-only — current `PRAGMA user_version`. |
| `.table_names()` | `list[str]` | Sorted; introspection for tests + curator audit. |
| `.count(table)` | `int` | Validates table name against `sqlite_master`; returns 0 for unknown tables. |
| `.upsert_lane(row)` | `None` | `INSERT OR REPLACE INTO lanes …`; row may be a mapping or a `LaneRecord`. |
| `.upsert_bench_result(row)` | `None` | Same shape, keyed on `(bench_slug, variant_label)`. |
| `.upsert_article(row)` | `None` | Keyed on `slug`. |
| `.upsert_hf_meta(row)` | `None` | Keyed on `repo_id`. |
| `.upsert_notebook_export(row)` | `None` | Keyed on `file_path`. |
| `.upsert_leaderboard_row(row)` | `None` | Keyed on `(bench_id, lane_id)`. |
| `.lanes()` / `.articles()` / `.bench_results(slug=None)` / `.leaderboard_rows()` | `list[sqlite3.Row]` | Read helpers the importer + future mirror exporter both call. |

The store also exposes `DEFAULT_DB_PATH` (`os.path.expanduser`'d at module load) and `USER_VERSION` (the schema version pin).

### M2 — Row records

Stdlib `dataclasses` records. Each maps 1:1 to a table column; the importer constructs them via `asdict()` and feeds them to `ArenaStore.upsert_*`.

| Record | Table | Key columns |
|---|---|---|
| `LaneRecord` | `lanes` | `id` (composite of `{manifest_slug}::{variant}` for quant/lora, `{slug}::nav` for harness/skill/bench/notebook, `{label}::brain-bakeoff` for the seeded brain lanes) |
| `BenchResultRow` | `bench_results` | `(bench_slug, variant_label)` |
| `ArticleIndexRow` | `article_index` | `slug` |
| `HfMetaRow` | `hf_meta` | `repo_id` |
| `NotebookExportRow` | `notebook_export` | `file_path` |
| `LeaderboardRow` | `leaderboard_rows` | `(bench_id, lane_id)` |

The records `ChatTurnRecord` / `CompareRunRecord` / `RubricScoreRecord` / `HumanPrefRecord` are declared at M2 (for the M3+ import path) but not yet exported via `__all__` until their milestone lands.

### M2 — `import_artifacts(repo_root, db_path, dry_run, refresh_hf, write_mirror, hf_cache_dir)`

The deterministic-Python spine of `fieldkit arena import`. Walks the repo's `src/content/artifacts/`, `articles/*/`, `notebooks/*/exports/**`, `~/.hermes/config.yaml`, and (optionally) the HuggingFace API into `~/.fieldkit/arena.db`. Opt in with `write_mirror=True` (CLI `--mirror`) to also drop a `src/data/arena-mirror/leaderboard.json` snapshot under the repo root — the tracked, published mirror is produced by `fieldkit arena mirror` instead.

| Kwarg | Default | What it does |
|---|---|---|
| `repo_root` | the checkout this fieldkit ships in | Walk a different repo (mainly for tests). |
| `db_path` | `~/.fieldkit/arena.db` | SQLite to populate. Ignored when `dry_run=True` (`:memory:` is used). |
| `dry_run` | `False` | Plan-only mode: in-memory SQLite, no on-disk writes, the report's row counts reflect what *would* have landed. |
| `refresh_hf` | `False` | Hit the HF API once per `Orionfold/` repo + write a 24h cache to `~/.fieldkit/arena_cache/hf/`. Default `False` keeps the importer offline-safe. |
| `write_mirror` | `False` | Opt-in: write `src/data/arena-mirror/leaderboard.json` under `repo_root` from the seeded leaderboard rows. Off by default since 2026-06-11 — nothing on the main site reads the root copy (use `fieldkit arena mirror` for the tracked arena-app mirror). |
| `hf_cache_dir` | `~/.fieldkit/arena_cache/hf` | Override the HF cache root (mainly for tests). |

Returns an `ImportReport` with the post-upsert row counts + a `warnings` list (every malformed-manifest or unknown-bench-shape goes here rather than raising). The report's counts are *post-upsert totals*, NOT rows written this run — so a re-run with identical inputs returns the same numbers (the M2 idempotency gate).

```python
from fieldkit.arena import import_artifacts

report = import_artifacts(dry_run=True)
print(report.summary_line())
# → lanes=40 bench_results=17 article_index=55 hf_meta=13 notebook_export=54 leaderboard_rows=3
```

### M2 — runnable script form

The Typer CLI (`fieldkit arena import …`) and a `python -m` shim share one code path:

```bash
# Plan-only — prints row counts without writing
python -m fieldkit.arena.scripts.import_existing --dry-run

# Real run + refresh HF metadata over the wire (writes to ~/.fieldkit/arena_cache/hf/)
python -m fieldkit.arena.scripts.import_existing --refresh-hf

# Identical via the Typer CLI
fieldkit arena import --dry-run
fieldkit arena import --refresh-hf
```

### Errors

| Exception | Raised when |
|---|---|
| `ArenaError` | Base for every error the module raises — catch this to catch them all. |
| `LaneNotRegistered` | A lane lookup hits an id not in the `lanes` table (M2+ surface). Defined at M1 so callers can `except` it without waiting on `store.py`. Subclass of `ArenaError`. |
| `PublishableSliceEmpty` | `export_publishable_slice` produced a zero-row leaderboard JSON (M6+ surface) — a guard against accidentally blanking the public mirror. Operator opt-out via `--allow-empty`. Subclass of `ArenaError`. |

### Constants

| Name | Value | Why |
|---|---|---|
| `ARENA_SURFACE_VERSION` | `"0.1.0a0"` (M1) → `"0.1.0"` at M7 | Independent of `fieldkit.__version__` so a downstream tool can gate on the surface (`arena ≥ 0.1.0`) without pinning the whole package. |
| `DEFAULT_ARENA_PORT` | `7866` | Spec §3.4 — mnemonic Spark+Arena reads; free across the existing port map (llama-server :8080, NIM :8000, pgvector :5432, Astro dev :4321, Redis :6379). |
| `DEFAULT_ARENA_DB` | `"~/.fieldkit/arena.db"` | Operator-private SQLite, NOT in repo (gitignored). Created lazily on first sidecar boot at M2. |

## The `arena` extra

The sidecar deps ship via an optional install:

```bash
pip install 'fieldkit[arena]'
```

| Dep | Why |
|---|---|
| `fastapi>=0.115` | sidecar HTTP framework — async-native, pydantic schemas, lifespan, SSE-friendly |
| `uvicorn[standard]>=0.30` | ASGI server (M3 launcher) |
| `sse-starlette>=2.1` | SSE helpers (telemetry pump, chat stream adapter, compare event sequence) |
| `aiosqlite>=0.20` | async access to `~/.fieldkit/arena.db` |
| `arq>=0.26` | v0.2 job queue (eval-runner pane); installed at M1 for forward compat, runtime-optional in v0.1 |
| `redis>=5.0` | arq broker (Redis already on the box for pgvector); runtime-optional in v0.1 |
| `huggingface_hub>=0.24` | M2 retroactive import reads HF repo metadata for the 13 `Orionfold/` repos |
| `pyyaml>=6.0` | reads `src/content/artifacts/*.yaml` manifests + `~/.hermes/config.yaml` |

**`import fieldkit.arena` is stdlib-only** — none of these are loaded on package import. FastAPI ships behind `create_app()` (M3); aiosqlite behind `ArenaStore.initialize()` (M2); huggingface_hub behind the M2 import script.

## CLI surface (locked at M1, bodies fill across the arc)

```text
$ fieldkit arena --help
Usage: fieldkit arena [OPTIONS] COMMAND [ARGS]...

  Operator cockpit for the DGX Spark (M1 stub; M3 fills the sidecar).

Commands:
  serve                Launch the FastAPI cockpit sidecar (M3).
  import               Retroactive load: manifests + articles + benches + HF (M2).
  mirror               Export leak-proof publishable slice (M6, this release).
  rebuild-leaderboard  Recompute denormalized `leaderboard_rows` (M6).
  memcheck             Print unified-memory envelope + warm-lane footprint (stub).
  promote-run          Mark a `compare_run` as publishable + supply redaction (stub).
```

`serve` / `import` / `mirror` / `rebuild-leaderboard` are live as of M6; `memcheck` and `promote-run` ship at M7. The CLI shape was frozen at M1 so the bodies can fill across the arc without drifting the operator-visible contract.

## Milestone roadmap (forward-looking; not API)

| Milestone | Surface |
|---|---|
| M1 | scaffold — `__init__.py` + `schemas.py` + `server.py` skeleton + `cli.py` stubs + the `arena` extra |
| M2 | `scripts/import_existing.py` retroactive load + SQLite schema (spec §4.8); `ArenaStore` materializes |
| M3 (this release) | `create_app()` + lifespan + `GET /api/telemetry/stream` SSE backed by `fieldkit.harness.Telemetry` + `GET /api/lanes` + `GET /api/leaderboard` + `<TelemetryGauge>` Preact island on `/arena/` |
| M4 | `<ChatLane>` + `POST /api/chat/stream` SSE proxy to `llama-server :8080` |
| M5 | `<CompareDuel>` + `POST /api/compare/stream` + deterministic rubric scoring via `fieldkit.eval.score_answer` |
| M6 (this release) | `mirror.py` with hardcoded allowlist guard (chat_* tables NEVER enumerated); `/arena/leaderboard/` Astro page; regression test asserts zero leaks against random-UUID sentinels |
| M7 | fieldkit v0.14.0 cut + `articles/introducing-spark-arena-on-spark/` + Mac `/sync-field-notes` push |

Each milestone is independently shippable on `origin/main`; the M2/M5/M6 risky milestones each have an explicit "fresh-session hint: YES" marker in HANDOFF.md's ARENA TRACK section.

## Cross-module reuse (M3 onward)

Arena calls into — never duplicates — these symbols:

| Symbol | Source | Used for |
|---|---|---|
| `serve_lane`, `LaneSpec`, `NIMLane`, `LlamaServerLane`, `VLLMLane`, `OllamaLane` | `fieldkit.harness` | every lane swap routes through `serve_lane(guard=True, headroom_gb=8.0)` — the only enforcer of the single-brain envelope |
| `Telemetry`, `measure_throughput` | `fieldkit.harness` | the GPU% / unified-mem / temp / tok/s / ttft sampler |
| `CostRouterConfig`, `RouteTier`, `build_cost_router` | `fieldkit.harness` | powers the default Compare B-lane (OpenRouter via tier predicates) |
| `RouterConfig`, `build_vertical_router` | `fieldkit.harness` | H5 vertical router — surfaced as the v0.2 "route this compare per-vertical" mode |
| `score_answer`, `Rubric`, `CheckSpec`, `GradedPromptSuite`, `load_rubric`, `HEDGE_PHRASES` | `fieldkit.eval` | every rubric score event; the deterministic scoring axis |
| `OpenAICompatClient`, `split_think`, `stream_reply`, `discover_local_server` | `fieldkit.notebook` | chat client forwarding; `<think>` prefix split per `feedback_nim_think_prefix_convention` |
| `ArtifactManifest`, `ArtifactKind`, `ORIONFOLD_HF_HANDLE` | `fieldkit.publish` | read-only; drives artifact browser; v0.2 HF dataset push reuses `HFHubAdapter` |
| `Capabilities.load()`, `weight_bytes`, `kv_cache_bytes` | `fieldkit.capabilities` | the `serve_lane` guard's memory math |

Per `feedback_keep_scorer_local_until_reuse`, ad-hoc rubrics live at `~/.fieldkit/arena/rubrics/` until a 2nd reuse triggers promotion to `fieldkit/src/fieldkit/eval/rubrics/`.

## See also

- `_SPECS/spark-arena-v1.md` — the locked v1.0 spec; section numbers referenced throughout this page.
- `HANDOFF.md` 🏟️ ARENA TRACK section — the session-by-session milestone breakdown.
- `ideas/spark-arena.md` — the living-doc tracking of gate decisions + execution updates (per `feedback_ideas_docs_living`).
- `fieldkit.harness` API page — the sibling content line's module reference.
