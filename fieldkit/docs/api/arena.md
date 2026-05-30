---
module: arena
title: fieldkit.arena
summary: Operator cockpit for the DGX Spark — FastAPI sidecar on 127.0.0.1:7866 with SSE telemetry/chat/compare streams, a SQLite-backed `~/.fieldkit/arena.db`, and a static-mirror exporter that publishes a leak-proof leaderboard slice to `ainative.business/arena/`. Sibling to `fieldkit.harness` (Hermes = agent harness; Arena = operator harness). M2 ships the SQLite store + retroactive importer; M3 ships the FastAPI app + telemetry SSE; M4 ships the chat island; M5 ships side-by-side compare; **M6 (this release) ships the leak-proof mirror exporter** (`fieldkit.arena.mirror.export_publishable_slice` with hardcoded allowlist; regression test pins zero chat-content leaks); M7 lands the launch article + Mac sync per `specs/spark-arena-v1.md`.
order: 13
---

## What it is

The Harnesses arc taught the project to publish *agent harnesses* — Hermes drives Spark, fieldkit-as-MCP keystone, vertical + cost routers. `fieldkit.arena` is the **operator** counterpart: the cockpit a solo Spark builder uses to drive every artifact the rest of the package has shipped. Six months of work has accreted 49 articles, 17 manifests under `src/content/artifacts/`, 13 HF repos under the `Orionfold/` namespace, and a 950-test `fieldkit` substrate — none of it had a single surface to drive it from until now. The cockpit lives at `http://127.0.0.1:7866/arena/` (loopback only) with a static slice mirrored to `ainative.business/arena/`. Per `feedback_llm_skill_pattern` the module is **deterministic Python only** — all LLM generation (rubric prompts, prose) stays in session-driven skills.

The full design is in `specs/spark-arena-v1.md`. M2 ships the SQLite store + the retroactive importer; M3–M7 fill the substantive sidecar surface (see `[Unreleased]` in `CHANGELOG.md`).

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
| `FORBIDDEN_COLUMNS` | `tuple[tuple[str, str], ...]` | The (table, column) pairs that MUST NOT leak. `(compare_runs, prompt)`, `(compare_responses, content)`, `(compare_responses, reasoning)`, the `chat_turns` columns, plus `(lab_notes, body)`. |
| `MIRROR_SCHEMA_VERSION` | `int` | Bumped to `2` for M6 (was `1` at M2). Adds `bench_rows` / `live_rows` arrays alongside the legacy `rows` alias. |

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

The deterministic-Python spine of `fieldkit arena import`. Walks the repo's `src/content/artifacts/`, `articles/*/`, `notebooks/*/exports/**`, `~/.hermes/config.yaml`, and (optionally) the HuggingFace API into `~/.fieldkit/arena.db`, then writes `src/data/arena-mirror/leaderboard.json` so the cockpit landing (M3) ships non-empty.

| Kwarg | Default | What it does |
|---|---|---|
| `repo_root` | the checkout this fieldkit ships in | Walk a different repo (mainly for tests). |
| `db_path` | `~/.fieldkit/arena.db` | SQLite to populate. Ignored when `dry_run=True` (`:memory:` is used). |
| `dry_run` | `False` | Plan-only mode: in-memory SQLite, no on-disk writes, the report's row counts reflect what *would* have landed. |
| `refresh_hf` | `False` | Hit the HF API once per `Orionfold/` repo + write a 24h cache to `~/.fieldkit/arena_cache/hf/`. Default `False` keeps the importer offline-safe. |
| `write_mirror` | `True` | Write `src/data/arena-mirror/leaderboard.json` from the seeded leaderboard rows. Set `False` in test runs. |
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

- `specs/spark-arena-v1.md` — the locked v1.0 spec; section numbers referenced throughout this page.
- `HANDOFF.md` 🏟️ ARENA TRACK section — the session-by-session milestone breakdown.
- `ideas/spark-arena.md` — the living-doc tracking of gate decisions + execution updates (per `feedback_ideas_docs_living`).
- `fieldkit.harness` API page — the sibling content line's module reference.
