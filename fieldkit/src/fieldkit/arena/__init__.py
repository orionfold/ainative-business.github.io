# Copyright 2026 Manav Sehgal
# SPDX-License-Identifier: Apache-2.0
"""Operator cockpit for the DGX Spark — FastAPI sidecar + SQLite store.

The deterministic Python spine of the **Cockpit** content line — the surface a
solo Spark builder drives every shipped artifact from. Sibling to
`fieldkit.harness`: where Hermes is the *agent harness* (Spark answers "how
does my agent drive the box"), Arena is the *operator harness* (Spark answers
"how do *I* drive the box"). See `_SPECS/spark-arena-v1.md` for the full design.

**M1 surface (this scaffold — Sessions 1):** the import-cheap submodule with
errors + placeholder dataclasses + a typed `__all__`. No FastAPI on package
load (the `arena` extra is required to *run* the sidecar, not to *import* the
submodule); no SQLite work; no SSE. The rest lands across the arc:

- **M2 — retroactive load:** `scripts/import_existing.py` walks the 17
  manifests + 49 articles + 2 published benches + 13 HF repos into
  `~/.fieldkit/arena.db` (lanes, bench_results, article_index, hf_meta tables).
- **M3 — telemetry SSE + cockpit landing:** `server.py` FastAPI app on
  `127.0.0.1:7866`; `GET /api/telemetry/stream` SSE backed by
  `fieldkit.harness.Telemetry`.
- **M4 — chat island:** `<ChatLane>` + `POST /api/chat/stream` SSE proxy to
  `llama-server :8080` reusing `fieldkit.notebook.OpenAICompatClient` +
  `split_think`.
- **M5 — side-by-side compare:** `<CompareDuel>` + `POST /api/compare/stream`
  + deterministic rubric scoring via `fieldkit.eval.score_answer` over
  `Rubric` / `CheckSpec`.
- **M6 — leaderboard + mirror exporter:** `mirror.py` with the hardcoded
  allowlist guard (`chat_*` tables NEVER enumerated) writing to
  `src/data/arena-mirror/*.json`.
- **M7 — fieldkit v0.14.0 cut + launch article + Mac sync.**

Per `feedback_llm_skill_pattern`, this module is **deterministic Python only**;
all LLM generation (rubric prompts, prose) stays in session-driven skills, never
here. Per `[[feedback_keep_scorer_local_until_reuse]]`, ad-hoc rubrics live at
`~/.fieldkit/arena/rubrics/` until a 2nd reuse triggers promotion to
`fieldkit.eval.rubrics`. The FastAPI / aiosqlite / sse-starlette / arq / redis
deps stay lazy so `import fieldkit.arena` stays stdlib-only — `create_app()`
(M3) is the first symbol that imports FastAPI.
"""

from __future__ import annotations

__all__ = [
    # version pin (mirrors fieldkit.__version__ for tooling that wants to
    # gate on the arena surface specifically)
    "ARENA_SURFACE_VERSION",
    # errors (the M1 hierarchy — M3–M6 add `LaneSwapBusy`, `RubricNotFound`,
    # `MirrorAllowlistViolation` as they land)
    "ArenaError",
    "LaneNotRegistered",
    "PublishableSliceEmpty",
    # default port + sqlite path (frozen constants — operator-visible)
    "DEFAULT_ARENA_PORT",
    "DEFAULT_ARENA_DB",
    # M2 — synchronous store + the retroactive-load surface
    "ArenaStore",
    "ImportReport",
    "import_artifacts",
    # M2 — row records (subset of spec §3 `__all__`; M5 adds compare/pref)
    "LaneRecord",
    "BenchResultRow",
    "ArticleIndexRow",
    "HfMetaRow",
    "NotebookExportRow",
    "LeaderboardRow",
    # M3 — FastAPI sidecar surface. Lazy: `import fieldkit.arena` stays
    # stdlib-cheap; calling `create_app()` is what pulls FastAPI.
    "create_app",
    "serve",
    "TelemetryHub",
    # M4 — chat session/turn records (operator-private; never mirrored).
    # The route + island land in `server.py` + the Astro `<ChatLane>` island;
    # these records are the on-disk row shape `ArenaStore` traffics in.
    "ChatSessionRecord",
    "ChatTurnRecord",
    # M5 — compare / rubric-score / human-pref records + the default rubric
    # registry the side-by-side compare scores against. ``RubricSpec`` is the
    # registry entry shape (id + title + executable :class:`Rubric`);
    # ``DEFAULT_RUBRIC_REGISTRY`` is the frozen built-in 3-rubric dict;
    # ``default_rubric_for_prompt`` is the spec §4.3 substring-sweep picker.
    "CompareRunRecord",
    "CompareResponseRecord",
    "RubricScoreRecord",
    "HumanPrefRecord",
    "RubricSpec",
    "DEFAULT_RUBRIC_REGISTRY",
    "default_rubric_for_prompt",
    # M6 — leak-proof public mirror exporter. Hardcoded allowlist +
    # forbidden list; ``chat_*`` tables never enumerated. See
    # ``fieldkit/tests/arena/test_mirror_does_not_leak.py`` for the
    # M7-blocker regression test.
    "export_publishable_slice",
    "rebuild_leaderboard",
    "ExportReport",
    "RebuildReport",
    "MIRROR_SCHEMA_VERSION",
    "PUBLISHABLE_TABLES",
    "FORBIDDEN_TABLES",
    "FORBIDDEN_COLUMNS",
    # M8 — control-plane queue (operator-private; never mirrored). The job
    # records, the dispatcher (executes through the `fieldkit.harness` MCP
    # surface), and the leaderboard-regression trigger producer. See
    # `_SPECS/spark-arena-v1.md` §12.
    "JobRecord",
    "JobTriggerRecord",
    "JobKind",
    "JobStatus",
    "enqueue_job",
    "dispatch_job",
    "drain_jobs",
    "detect_leaderboard_regression",
    "enqueue_regressions",
    "JobDispatchError",
    "UnknownJobKind",
]

# v0.1.0-alpha; bumps independently of fieldkit's package version so a
# downstream tool can gate on the surface ("arena ≥ 0.1.0") without pinning
# the whole fieldkit package version. Promoted to 0.1.0 at M7 release.
ARENA_SURFACE_VERSION = "0.1.0a0"

# Spec §3.4 — locked port (mnemonic: Spark+Arena reads; free across the
# existing port map of llama-server :8080, NIM :8000, pgvector :5432,
# Astro dev :4321, Redis :6379).
DEFAULT_ARENA_PORT = 7866

# Spec §3.4 — operator-private SQLite store. Created lazily on first sidecar
# boot via `ArenaStore.initialize()` (M2); NOT in the repo (gitignored).
DEFAULT_ARENA_DB = "~/.fieldkit/arena.db"


class ArenaError(Exception):
    """Base for every error raised by `fieldkit.arena`."""


class LaneNotRegistered(ArenaError):
    """A lane lookup (`store.lane_by_id` / `serve_lane_by_id`) hit an id not
    in the `lanes` table.

    M2+ surface: the M1 stub raises this never; defined here so the error
    hierarchy is stable from day one and tests/callers can `except` it
    without waiting on M2's `store.py` to land.
    """


class PublishableSliceEmpty(ArenaError):
    """`export_publishable_slice` produced an empty leaderboard JSON.

    M6+ surface: refusing to write a zero-row mirror JSON over a non-empty
    prior file — a guard against accidentally blanking the public mirror
    when an upstream query goes wrong. Operator opt-out via `--allow-empty`.
    """


# M2 — re-export the store + importer + row records. Lazy via PEP 562 to
# keep `import fieldkit.arena` cheap; the first attribute access pulls
# stdlib `sqlite3` (already imported by Python itself) + the dataclass
# definitions. Operators usually want one of these symbols, so the lazy
# path runs at most once per process.

_LAZY_RE_EXPORTS: dict[str, tuple[str, str]] = {
    "ArenaStore": ("fieldkit.arena.store", "ArenaStore"),
    "ImportReport": ("fieldkit.arena.importer", "ImportReport"),
    "import_artifacts": ("fieldkit.arena.importer", "import_artifacts"),
    "LaneRecord": ("fieldkit.arena.schemas", "LaneRecord"),
    "BenchResultRow": ("fieldkit.arena.schemas", "BenchResultRow"),
    "ArticleIndexRow": ("fieldkit.arena.schemas", "ArticleIndexRow"),
    "HfMetaRow": ("fieldkit.arena.schemas", "HfMetaRow"),
    "NotebookExportRow": ("fieldkit.arena.schemas", "NotebookExportRow"),
    "LeaderboardRow": ("fieldkit.arena.schemas", "LeaderboardRow"),
    "create_app": ("fieldkit.arena.server", "create_app"),
    "serve": ("fieldkit.arena.server", "serve"),
    "TelemetryHub": ("fieldkit.arena.server", "TelemetryHub"),
    "ChatSessionRecord": ("fieldkit.arena.schemas", "ChatSessionRecord"),
    "ChatTurnRecord": ("fieldkit.arena.schemas", "ChatTurnRecord"),
    "CompareRunRecord": ("fieldkit.arena.schemas", "CompareRunRecord"),
    "CompareResponseRecord": ("fieldkit.arena.schemas", "CompareResponseRecord"),
    "RubricScoreRecord": ("fieldkit.arena.schemas", "RubricScoreRecord"),
    "HumanPrefRecord": ("fieldkit.arena.schemas", "HumanPrefRecord"),
    "RubricSpec": ("fieldkit.arena.rubrics", "RubricSpec"),
    "DEFAULT_RUBRIC_REGISTRY": (
        "fieldkit.arena.rubrics",
        "DEFAULT_RUBRIC_REGISTRY",
    ),
    "default_rubric_for_prompt": (
        "fieldkit.arena.rubrics",
        "default_rubric_for_prompt",
    ),
    "export_publishable_slice": (
        "fieldkit.arena.mirror",
        "export_publishable_slice",
    ),
    "rebuild_leaderboard": ("fieldkit.arena.mirror", "rebuild_leaderboard"),
    "ExportReport": ("fieldkit.arena.mirror", "ExportReport"),
    "RebuildReport": ("fieldkit.arena.mirror", "RebuildReport"),
    "MIRROR_SCHEMA_VERSION": (
        "fieldkit.arena.mirror",
        "MIRROR_SCHEMA_VERSION",
    ),
    "PUBLISHABLE_TABLES": ("fieldkit.arena.mirror", "PUBLISHABLE_TABLES"),
    "FORBIDDEN_TABLES": ("fieldkit.arena.mirror", "FORBIDDEN_TABLES"),
    "FORBIDDEN_COLUMNS": ("fieldkit.arena.mirror", "FORBIDDEN_COLUMNS"),
    # M8 — jobs control plane
    "JobRecord": ("fieldkit.arena.schemas", "JobRecord"),
    "JobTriggerRecord": ("fieldkit.arena.schemas", "JobTriggerRecord"),
    "JobKind": ("fieldkit.arena.jobs", "JobKind"),
    "JobStatus": ("fieldkit.arena.jobs", "JobStatus"),
    "enqueue_job": ("fieldkit.arena.jobs", "enqueue_job"),
    "dispatch_job": ("fieldkit.arena.jobs", "dispatch_job"),
    "drain_jobs": ("fieldkit.arena.jobs", "drain_jobs"),
    "detect_leaderboard_regression": (
        "fieldkit.arena.jobs",
        "detect_leaderboard_regression",
    ),
    "enqueue_regressions": ("fieldkit.arena.jobs", "enqueue_regressions"),
    "JobDispatchError": ("fieldkit.arena.jobs", "JobDispatchError"),
    "UnknownJobKind": ("fieldkit.arena.jobs", "UnknownJobKind"),
}


def __getattr__(name: str):  # PEP 562
    if name in _LAZY_RE_EXPORTS:
        module_name, attr = _LAZY_RE_EXPORTS[name]
        import importlib

        module = importlib.import_module(module_name)
        value = getattr(module, attr)
        globals()[name] = value
        return value
    raise AttributeError(f"module 'fieldkit.arena' has no attribute {name!r}")


def __dir__() -> list[str]:
    return sorted(set(__all__) | set(globals()))
