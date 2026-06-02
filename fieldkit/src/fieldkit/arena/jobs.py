# Copyright 2026 Manav Sehgal
# SPDX-License-Identifier: Apache-2.0
"""`fieldkit.arena.jobs` — the M8 control-plane dispatcher.

**M8 surface (`_SPECS/spark-arena-v1.md` §12).** Promotes Arena from a
*recorder* into a *dispatcher* — the place the operator triggers work from.
Three pieces:

1. **`enqueue_job`** — write a ``queued`` row (the partial unique index
   coalesces duplicate triggers while a job is in flight — the R15 dedup gate).
2. **`dispatch_job` / `drain_jobs`** — claim the oldest queued job and run it
   **through the `fieldkit.harness` MCP surface** (M8-1: one execution surface
   shared with Hermes, so the containment rails are defined once). Single lane,
   one job at a time (M8-5, the 128 GB envelope).
3. **`detect_leaderboard_regression`** — diff two accuracy-rollup snapshots
   (`ArenaStore.eval_leaderboard()`); an over-threshold drop enqueues an
   ``eval_rerun`` to *confirm* the regression (M8-2 — the first and only real
   M8 job type; everything else is a named stub).

Per `feedback_llm_skill_pattern`: deterministic Python only — no `anthropic`
import, no `claude_agent_sdk` import, no LLM call. The harness tools the
dispatcher calls are themselves plain, GPU-touching functions; this module is
the queue + control flow around them.

Importing this module stays cheap: the harness/eval deps are lazy-imported
inside :func:`default_runner`, so `import fieldkit.arena.jobs` pulls only
stdlib + the sibling store.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any, Callable, Mapping, Optional, Sequence

from fieldkit.arena import ArenaError
from fieldkit.arena.schemas import JobRecord, JobTriggerRecord

__all__ = [
    "JobKind",
    "JobStatus",
    "JobDispatchError",
    "UnknownJobKind",
    "enqueue_job",
    "dispatch_job",
    "drain_jobs",
    "detect_leaderboard_regression",
    "enqueue_regressions",
    "default_runner",
    "DEFAULT_REGRESSION_TAU",
]


class JobKind:
    """The job kinds the queue understands.

    M8 dispatches only :data:`EVAL_RERUN` and :data:`MEASURE_VARIANTS`
    (:data:`DISPATCHABLE`); the rest are **named stubs** — enqueueable as a
    forward marker but rejected by the dispatcher until their phase lands
    (`rl_run`/`requant` → Phase 3 `rlvr-loop-v1`; `reindex`/`rag_eval`/
    `scout_ingest` → Bet-5 `second-brain-pipeline-v1`).
    """

    EVAL_RERUN = "eval_rerun"
    MEASURE_VARIANTS = "measure_variants"
    # Named stubs (not dispatchable in M8):
    REQUANT = "requant"
    RL_RUN = "rl_run"
    REINDEX = "reindex"
    RAG_EVAL = "rag_eval"
    SCOUT_INGEST = "scout_ingest"

    DISPATCHABLE: frozenset[str] = frozenset({EVAL_RERUN, MEASURE_VARIANTS})
    ALL: frozenset[str] = frozenset(
        {EVAL_RERUN, MEASURE_VARIANTS, REQUANT, RL_RUN, REINDEX, RAG_EVAL, SCOUT_INGEST}
    )


class JobStatus:
    """The lifecycle states of a ``jobs`` row."""

    QUEUED = "queued"
    DISPATCHED = "dispatched"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    SKIPPED = "skipped"

    #: States that hold a slot in the dedup unique-index (an in-flight job).
    IN_FLIGHT: frozenset[str] = frozenset({QUEUED, DISPATCHED, RUNNING})


class JobDispatchError(ArenaError):
    """A job failed while executing through the harness.

    The dispatcher catches the underlying error, flips the row to ``failed``
    with the message in ``jobs.error``, and re-raises this so a synchronous
    caller (a test, the CLI) can react; the async sidecar drain swallows it
    after the row is marked failed.
    """


class UnknownJobKind(ArenaError):
    """An ``enqueue_job`` / ``dispatch_job`` named a kind the queue can't run.

    Raised for a kind outside :data:`JobKind.ALL` on enqueue, or outside
    :data:`JobKind.DISPATCHABLE` on dispatch (the named-but-not-yet-built
    stubs — `rl_run`, `reindex`, …).
    """


#: Default accuracy drop (in normalized [0,1] points) that counts as a
#: regression. 0.05 ≈ a 5-point accuracy slip — above eval/synth noise per the
#: R15 false-positive guard. Tunable per call.
DEFAULT_REGRESSION_TAU = 0.05


def _utc_now_iso() -> str:
    """ISO-8601 UTC stamp, matching the sidecar + mirror convention."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _dedup_key(kind: str, payload: Mapping[str, Any]) -> Optional[str]:
    """``(kind, lane_id, bench_id)`` — coalesces duplicate triggers in flight.

    Returns ``None`` (always-run, never coalesced) when the payload carries
    neither a lane nor a bench — a manual one-off has nothing to dedup on.
    """
    lane = payload.get("lane_id")
    bench = payload.get("bench_id")
    if lane is None and bench is None:
        return None
    return f"{kind}:{lane or ''}:{bench or ''}"


# ---------------------------------------------------------------------------
# Enqueue
# ---------------------------------------------------------------------------


def enqueue_job(
    store: Any,
    kind: str,
    payload: Mapping[str, Any],
    *,
    trigger: str = "manual",
    priority: int = 0,
    dedup_key: Optional[str] = None,
    trigger_detail: Optional[Mapping[str, Any]] = None,
    now_fn: Callable[[], str] = _utc_now_iso,
) -> Optional[str]:
    """Write one ``queued`` job; return its id, or ``None`` if coalesced.

    ``dedup_key`` defaults to ``(kind, lane_id, bench_id)`` derived from the
    payload; pass an explicit ``""`` (empty string) to force an always-run
    job, or a custom key. When an in-flight job already holds the key the
    insert is a no-op and this returns ``None`` (R15 — no re-eval storm).

    Records a ``job_triggers`` audit row when ``trigger_detail`` is given (the
    regression delta, the staleness age, the operator note).
    """
    if kind not in JobKind.ALL:
        raise UnknownJobKind(
            f"unknown job kind {kind!r}; known: {sorted(JobKind.ALL)}"
        )
    key = dedup_key if dedup_key is not None else _dedup_key(kind, payload)
    job_id = uuid.uuid4().hex
    record = JobRecord(
        id=job_id,
        kind=kind,
        status=JobStatus.QUEUED,
        trigger=trigger,
        payload_json=json.dumps(dict(payload), sort_keys=True),
        enqueued_at=now_fn(),
        priority=priority,
        dedup_key=key or None,
    )
    written = store.enqueue_job(record)
    if written is None:
        return None  # coalesced — an in-flight job already owns this dedup_key
    if trigger_detail is not None:
        store.record_job_trigger(
            JobTriggerRecord(
                job_id=job_id,
                source=trigger,
                detail_json=json.dumps(dict(trigger_detail), sort_keys=True),
                created_at=now_fn(),
            )
        )
    return job_id


# ---------------------------------------------------------------------------
# Dispatch — execute one job through the harness
# ---------------------------------------------------------------------------


def default_runner(kind: str, payload: Mapping[str, Any]) -> dict[str, Any]:
    """Execute one job by calling the matching `fieldkit.harness` MCP tool.

    This is M8-1 made concrete: the dispatcher's *only* execution surface is
    the same curated tool set the Hermes harness drives (`build_mcp_server`),
    so the containment posture (`publish` unreachable, `quantize` dry-run-
    default, `--network=none` sandbox) is inherited, never re-implemented. The
    two tools are lazy-imported so `import fieldkit.arena.jobs` stays stdlib-
    cheap and the GPU/eval deps load only when a job actually runs.

    Injectable: :func:`dispatch_job` takes a ``runner`` parameter, so tests
    pass a fake that returns canned results without touching the GPU.
    """
    from fieldkit.harness import mcp

    if kind == JobKind.EVAL_RERUN:
        return mcp.run_vertical_eval(
            lane=payload["lane_id"],
            bench=payload["bench_id"],
            bench_path=payload.get("bench_path"),
            limit=payload.get("limit"),
        )
    if kind == JobKind.MEASURE_VARIANTS:
        return mcp.measure_variants(
            manifest_slug=payload["manifest_slug"],
            gguf_paths=payload.get("gguf_paths"),
        )
    raise UnknownJobKind(
        f"job kind {kind!r} is a named stub, not dispatchable in M8 "
        f"(dispatchable: {sorted(JobKind.DISPATCHABLE)})"
    )


def _persist_eval_rerun(
    store: Any, payload: Mapping[str, Any], result: Mapping[str, Any], now: str
) -> dict[str, Any]:
    """Write an ``eval_rerun`` result through the EXISTING scorer path.

    Activates the dormant ``eval_runs`` status row (the ``arq_job_id`` socket
    M8 finally wires) and appends one ``eval_scores`` row per graded question —
    the same table the live `/api/chat/score` scorer writes, so the accuracy
    leaderboard (`eval_leaderboard()`) picks the re-eval up with no new plumbing.
    Returns a compact summary for ``jobs.result_json``.
    """
    run_id = uuid.uuid4().hex
    bench_id = str(payload["bench_id"])
    lane_id = str(payload["lane_id"])
    store.upsert_eval_run(
        {
            "id": run_id,
            "bench_id": bench_id,
            "lane_id": lane_id,
            "status": "started",
            "enqueued_at": now,
            "started_at": now,
            "finished_at": None,
            "result_json": None,
            "arq_job_id": None,
        }
    )
    calls: Sequence[Mapping[str, Any]] = result.get("calls", []) or []
    n_scored = 0
    for call in calls:
        normalized = call.get("normalized")
        if normalized is None:
            continue
        store.append_eval_score(
            {
                "bench_id": bench_id,
                "qid": str(call.get("qid", f"q-{n_scored}")),
                "lane_id": lane_id,
                "scorer_kind": str(result.get("scorer_kind", "exact_match")),
                "score": call.get("score"),
                "max_score": call.get("max_score", 1.0),
                "normalized": normalized,
                "reference": call.get("reference"),
                "rationale": call.get("rationale"),
                "judge_backend": None,
                "cross_vertical": int(bool(payload.get("cross_vertical", False))),
                "source": "eval_rerun",
                "source_id": run_id,
                "scored_at": now,
            }
        )
        n_scored += 1
    summary = {
        "eval_run_id": run_id,
        "bench_id": bench_id,
        "lane_id": lane_id,
        "n_scored": n_scored,
        "mean_normalized": result.get("mean_normalized"),
    }
    store.update_eval_run(
        run_id,
        status="finished",
        finished_at=now,
        result_json=json.dumps(summary, sort_keys=True),
    )
    return summary


def dispatch_job(
    store: Any,
    job: Mapping[str, Any],
    *,
    runner: Callable[[str, Mapping[str, Any]], dict[str, Any]] = default_runner,
    now_fn: Callable[[], str] = _utc_now_iso,
) -> dict[str, Any]:
    """Run one claimed job end-to-end; return the updated job row as a dict.

    ``job`` is a ``dispatched`` row (from :meth:`ArenaStore.claim_next_job`).
    Flips it ``running`` → executes via ``runner`` (the harness surface) →
    ``done`` (persisting through the existing scorer path for ``eval_rerun``)
    or ``failed`` (stamping ``jobs.error`` + re-raising :class:`JobDispatchError`).
    """
    job_id = str(job["id"])
    kind = str(job["kind"])
    if kind not in JobKind.DISPATCHABLE:
        store.update_job(
            job_id,
            status=JobStatus.FAILED,
            error=f"kind {kind!r} not dispatchable in M8",
            finished_at=now_fn(),
        )
        raise UnknownJobKind(f"job kind {kind!r} is not dispatchable in M8")

    payload = json.loads(job["payload_json"])
    store.update_job(job_id, status=JobStatus.RUNNING)
    try:
        result = runner(kind, payload)
        now = now_fn()
        if kind == JobKind.EVAL_RERUN:
            summary = _persist_eval_rerun(store, payload, result, now)
        else:
            summary = dict(result)
        store.update_job(
            job_id,
            status=JobStatus.DONE,
            result_json=json.dumps(summary, sort_keys=True),
            finished_at=now,
        )
    except Exception as exc:  # noqa: BLE001 — surface to the row + caller
        store.update_job(
            job_id,
            status=JobStatus.FAILED,
            error=str(exc),
            finished_at=now_fn(),
        )
        raise JobDispatchError(f"job {job_id} ({kind}) failed: {exc}") from exc
    row = store.get_job(job_id)
    return {k: row[k] for k in row.keys()}


def drain_jobs(
    store: Any,
    *,
    runner: Callable[[str, Mapping[str, Any]], dict[str, Any]] = default_runner,
    max_jobs: Optional[int] = None,
    now_fn: Callable[[], str] = _utc_now_iso,
    on_error: str = "record",
) -> list[dict[str, Any]]:
    """Drain the queue one job at a time until empty (M8-5, sequential).

    Claims the oldest ``queued`` job, dispatches it, repeats. ``max_jobs``
    caps a single drain pass (the Phase-2 cron will call this on a schedule).
    ``on_error='record'`` (default) keeps draining past a failed job (it's
    already marked ``failed``); ``on_error='raise'`` stops at the first failure.
    Returns the updated row dict for every job it touched.
    """
    done: list[dict[str, Any]] = []
    while max_jobs is None or len(done) < max_jobs:
        claimed = store.claim_next_job(dispatched_at=now_fn())
        if claimed is None:
            break
        job = {k: claimed[k] for k in claimed.keys()}
        try:
            done.append(dispatch_job(store, job, runner=runner, now_fn=now_fn))
        except JobDispatchError:
            if on_error == "raise":
                raise
            done.append({k: store.get_job(job["id"])[k] for k in claimed.keys()})
    return done


# ---------------------------------------------------------------------------
# Regression trigger producer
# ---------------------------------------------------------------------------


def _rollup_index(rows: Sequence[Any]) -> dict[tuple[str, str], float]:
    """Index an ``eval_leaderboard()`` snapshot by ``(bench_id, lane_id)`` →
    ``mean_normalized``. Accepts ``sqlite3.Row`` or plain mappings."""
    out: dict[tuple[str, str], float] = {}
    for r in rows:
        score = r["mean_normalized"]
        if score is None:
            continue
        out[(r["bench_id"], r["lane_id"])] = float(score)
    return out


def detect_leaderboard_regression(
    prev: Sequence[Any],
    curr: Sequence[Any],
    *,
    tau: float = DEFAULT_REGRESSION_TAU,
) -> list[dict[str, Any]]:
    """Pure diff of two accuracy-rollup snapshots → regression deltas.

    Each input is an :meth:`ArenaStore.eval_leaderboard` result (rows carrying
    ``bench_id`` / ``lane_id`` / ``mean_normalized``). A ``(bench, lane)`` whose
    accuracy dropped by **more than ``tau``** is a regression. Returns one dict
    per regression — ``{bench_id, lane_id, prev_score, new_score, delta}`` —
    sorted worst-drop first. Lanes/benches absent from ``prev`` (newly seen)
    can't regress and are skipped. This is the M8 release-gate's testable core.
    """
    prev_idx = _rollup_index(prev)
    curr_idx = _rollup_index(curr)
    regressions: list[dict[str, Any]] = []
    for key, new_score in curr_idx.items():
        prev_score = prev_idx.get(key)
        if prev_score is None:
            continue
        delta = new_score - prev_score
        if delta < -tau:
            bench_id, lane_id = key
            regressions.append(
                {
                    "bench_id": bench_id,
                    "lane_id": lane_id,
                    "prev_score": round(prev_score, 6),
                    "new_score": round(new_score, 6),
                    "delta": round(delta, 6),
                }
            )
    regressions.sort(key=lambda r: r["delta"])  # most-negative first
    return regressions


def enqueue_regressions(
    store: Any,
    prev: Sequence[Any],
    curr: Sequence[Any],
    *,
    tau: float = DEFAULT_REGRESSION_TAU,
    now_fn: Callable[[], str] = _utc_now_iso,
) -> list[str]:
    """Detect regressions between two rollup snapshots and enqueue a confirming
    ``eval_rerun`` for each (M8-2). Returns the ids actually enqueued (a
    coalesced duplicate — an in-flight re-eval for the same bench×lane —
    yields no id, R15). Each enqueue records a ``leaderboard_regression``
    audit row carrying the delta."""
    enqueued: list[str] = []
    for reg in detect_leaderboard_regression(prev, curr, tau=tau):
        job_id = enqueue_job(
            store,
            JobKind.EVAL_RERUN,
            {"lane_id": reg["lane_id"], "bench_id": reg["bench_id"]},
            trigger="leaderboard_regression",
            priority=1,  # confirm regressions ahead of manual re-evals
            trigger_detail=reg,
            now_fn=now_fn,
        )
        if job_id is not None:
            enqueued.append(job_id)
    return enqueued
