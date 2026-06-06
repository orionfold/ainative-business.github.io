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
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, Optional, Sequence

from fieldkit.arena import ArenaError
from fieldkit.arena.schemas import JobRecord, JobTriggerRecord

__all__ = [
    "JobKind",
    "JobStatus",
    "JobDispatchError",
    "UnknownJobKind",
    "BenchNotRegistered",
    "enqueue_job",
    "dispatch_job",
    "drain_jobs",
    "resolve_bench",
    "DEFAULT_BENCH_DIR",
    "detect_leaderboard_regression",
    "enqueue_regressions",
    "check_and_enqueue_regressions",
    "default_runner",
    "DEFAULT_REGRESSION_TAU",
]


class JobKind:
    """The job kinds the queue understands.

    M8 dispatched :data:`EVAL_RERUN` + :data:`MEASURE_VARIANTS`; **M10 (Bet 5
    recall layer) promoted** :data:`REINDEX` / :data:`RAG_EVAL` /
    :data:`SCOUT_INGEST`; **Phase 3 (`rlvr-loop-v1`, RV-6) promotes the last two
    stubs** — :data:`RL_RUN` (the closed-loop RLVR run) + :data:`REQUANT` (the
    re-quantize of a held-out-winning checkpoint) — into :data:`DISPATCHABLE`.
    With that, every enqueueable kind is now dispatchable (``DISPATCHABLE ==
    ALL``). The RLVR run is **async/overnight only** (the 8.5 h GRPO loop can't
    be a synchronous cockpit click — RV-6): the `server.py` ``POST /api/jobs``
    allowlist stays narrow, so `rl_run` reaches the dispatcher via
    :func:`enqueue_job` (a compare-loss trigger, a manual CLI enqueue) and runs
    under the M11 single-lane cron drain, not a button.
    """

    EVAL_RERUN = "eval_rerun"
    MEASURE_VARIANTS = "measure_variants"
    # M10 (Bet 5) — the recall-pipeline kinds:
    REINDEX = "reindex"
    RAG_EVAL = "rag_eval"
    SCOUT_INGEST = "scout_ingest"
    # Phase 3 (rlvr-loop-v1, RV-6) — the closed-loop RLVR engine, overnight-only:
    REQUANT = "requant"
    RL_RUN = "rl_run"

    DISPATCHABLE: frozenset[str] = frozenset(
        {EVAL_RERUN, MEASURE_VARIANTS, REINDEX, RAG_EVAL, SCOUT_INGEST, REQUANT, RL_RUN}
    )
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


class BenchNotRegistered(ArenaError):
    """An ``eval_rerun`` named a ``bench_id`` with no resolvable gold JSONL.

    The dispatcher resolves ``bench_path`` from the bench registry
    (:func:`resolve_bench` — the ``$ARENA_BENCH_DIR/<bench_id>.jsonl``
    convention) when the job payload doesn't carry one. This is raised, with
    the exact path it looked for, when neither a payload ``bench_path`` nor a
    registered gold set exists — so a re-eval can't silently grade nothing.
    """


#: Default accuracy drop (in normalized [0,1] points) that counts as a
#: regression. 0.05 ≈ a 5-point accuracy slip — above eval/synth noise per the
#: R15 false-positive guard. Tunable per call.
DEFAULT_REGRESSION_TAU = 0.05


def _utc_now_iso() -> str:
    """ISO-8601 UTC stamp, matching the sidecar + mirror convention."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


#: Where the bench registry lives — one ``<bench_id>.jsonl`` gold set per bench,
#: with an optional ``<bench_id>.meta.json`` sidecar carrying ``scorer`` /
#: ``max_tokens`` / ``limit``. Override with ``$ARENA_BENCH_DIR``. This is the
#: convention `run_vertical_eval`'s "needs bench_path" error advertises.
DEFAULT_BENCH_DIR = "~/.fieldkit/arena/benches"


def resolve_bench(
    bench_id: str, *, bench_dir: Optional[str] = None
) -> Optional[dict[str, Any]]:
    """Resolve a ``bench_id`` → ``{bench_path, scorer, max_tokens, limit}``.

    The registry is a directory (``$ARENA_BENCH_DIR`` or
    :data:`DEFAULT_BENCH_DIR`): a bench is registered when
    ``<bench_id>.jsonl`` exists there. An optional ``<bench_id>.meta.json``
    sidecar overrides the scorer (default ``exact_match``) and the eval knobs.
    Returns ``None`` when no gold set is registered — the dispatcher turns that
    into a :class:`BenchNotRegistered` with the path it searched. Pure
    filesystem lookup (no store, no GPU), so it's cheap and unit-testable.
    """
    base = Path(
        os.path.expanduser(
            bench_dir or os.environ.get("ARENA_BENCH_DIR", DEFAULT_BENCH_DIR)
        )
    )
    jsonl = base / f"{bench_id}.jsonl"
    if not jsonl.is_file():
        return None
    meta: dict[str, Any] = {}
    meta_path = base / f"{bench_id}.meta.json"
    if meta_path.is_file():
        try:
            meta = json.loads(meta_path.read_text())
        except (OSError, json.JSONDecodeError):
            meta = {}
    return {
        "bench_path": str(jsonl),
        "scorer": meta.get("scorer", "exact_match"),
        "scorer_path": meta.get("scorer_path"),
        "max_tokens": int(meta.get("max_tokens", 512)),
        "limit": meta.get("limit"),
    }


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
        bench_id = payload["bench_id"]
        # Resolve the gold JSONL from the bench registry when the payload
        # (regression triggers, the UI dispatch form) carries only bench_id.
        # An explicit payload bench_path/scorer/limit still wins.
        bench_path = payload.get("bench_path")
        scorer = payload.get("scorer", "exact_match")
        # A registered bench may carry a custom verifier (`scorer_path`) — the
        # AF-15 hook that lets a `\boxed{}`-style vertical score correctly through
        # the eval/compare path, not just the built-in scorers. Payload overrides.
        scorer_path = payload.get("scorer_path")
        max_tokens = int(payload.get("max_tokens", 512))
        limit = payload.get("limit")
        if not bench_path:
            reg = resolve_bench(bench_id)
            if reg is None:
                base = os.path.expanduser(
                    os.environ.get("ARENA_BENCH_DIR", DEFAULT_BENCH_DIR)
                )
                raise BenchNotRegistered(
                    f"bench {bench_id!r} is not registered — no gold JSONL at "
                    f"{base}/{bench_id}.jsonl. Register one (or pass an explicit "
                    f"`bench_path` in the job payload)."
                )
            bench_path = reg["bench_path"]
            scorer = payload.get("scorer", reg["scorer"])
            scorer_path = payload.get("scorer_path", reg.get("scorer_path"))
            max_tokens = int(payload.get("max_tokens", reg["max_tokens"]))
            limit = payload.get("limit", reg["limit"])
        return mcp.run_vertical_eval(
            lane=payload["lane_id"],
            bench=bench_id,
            bench_path=bench_path,
            base_url=payload.get("base_url"),
            model=payload.get("model"),
            scorer=scorer,
            scorer_path=scorer_path,
            api_key_env=payload.get("api_key_env"),
            limit=limit,
            max_tokens=max_tokens,
        )
    if kind == JobKind.MEASURE_VARIANTS:
        return mcp.measure_variants(
            manifest_slug=payload["manifest_slug"],
            gguf_paths=payload.get("gguf_paths"),
        )
    # M10 (Bet 5 recall layer) — the recall-pipeline kinds, through the same surface.
    if kind == JobKind.REINDEX:
        return mcp.reindex_memory(
            source_set=payload.get("source_set", "articles"),
            articles_dir=payload.get("articles_dir"),
            papers_json=payload.get("papers_json"),
            lineage_cards=payload.get("lineage_cards"),
        )
    if kind == JobKind.RAG_EVAL:
        return mcp.rag_eval_index(
            qa_set=payload.get("qa_set"),
            top_k=int(payload.get("top_k", 5)),
            rerank=bool(payload.get("rerank", False)),
        )
    if kind == JobKind.SCOUT_INGEST:
        return mcp.scout_ingest(
            papers_json=payload["papers_json"],
            articles_dir=payload.get("articles_dir"),
        )
    # Phase 3 (rlvr-loop-v1) — the closed-loop RLVR engine, through the same surface.
    if kind == JobKind.RL_RUN:
        return mcp.run_rl_loop(
            base=payload["base"],
            vertical=payload.get("vertical", "patent-strategist"),
            bench_path=payload["bench_path"],
            scorer=payload.get("scorer", "mcq_letter"),
            scorer_path=payload.get("scorer_path"),
            lane=payload.get("lane_id"),
            bench_id=payload.get("bench_id"),
            config=payload.get("config"),
        )
    if kind == JobKind.REQUANT:
        return mcp.requant_checkpoint(
            manifest_slug=payload["manifest_slug"],
            checkpoint=payload["checkpoint"],
            variants=payload.get("variants"),
        )
    raise UnknownJobKind(
        f"job kind {kind!r} is a named stub, not dispatchable "
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


def _persist_reindex(
    store: Any, payload: Mapping[str, Any], result: Mapping[str, Any], now: str
) -> dict[str, Any]:
    """Write a ``reindex_runs`` row from a ``reindex`` / ``scout_ingest`` result
    (M10-5). Records the source set, chunk delta, and ``index_version`` so the
    coverage pane can show what each rebuild did. Operator-private (the row
    never mirrors). Returns a compact summary for ``jobs.result_json``."""
    run_id = uuid.uuid4().hex
    store.insert_reindex_run(
        {
            "id": run_id,
            "source_set": str(result.get("source_set", payload.get("source_set", "articles"))),
            "index_version": str(result.get("index_version", "")),
            "chunks_before": result.get("chunks_before"),
            "chunks_after": result.get("chunks_after"),
            "articles_n": result.get("articles_n"),
            "status": "done",
            "started_at": now,
            "finished_at": now,
            "error": None,
        }
    )
    return {
        "reindex_run_id": run_id,
        "source_set": result.get("source_set"),
        "index_version": result.get("index_version"),
        "chunks_before": result.get("chunks_before"),
        "chunks_after": result.get("chunks_after"),
        "articles_n": result.get("articles_n"),
        "by_source": result.get("by_source"),
    }


def _persist_rag_eval(
    store: Any, payload: Mapping[str, Any], result: Mapping[str, Any], now: str
) -> dict[str, Any]:
    """Write a ``rag_eval_runs`` row and apply the **promotion gate** (M10-6).

    Compares the new ``recall_at_k`` against the prior *done* score for the same
    ``qa_set`` **at the same rerank mode** (like-for-like, R22). A rebuild that
    drops recall below the prior index is flagged ``promote=False`` — the index
    is already physically rebuilt (single store), so the verdict + delta are
    recorded for the operator / Phase-2 monitor to act on (roll back / override).
    The score row itself is the public RAG-eval trend (aggregates only, M10-10).
    """
    run_id = uuid.uuid4().hex
    qa_set = str(result.get("qa_set", payload.get("qa_set", "qa-eval.jsonl")))
    rerank = int(result.get("rerank", 0))
    recall = result.get("recall_at_k")
    prior = store.last_rag_eval(qa_set, rerank=rerank)
    prior_recall = float(prior["recall_at_k"]) if prior is not None else None
    promote = True
    if prior_recall is not None and recall is not None:
        promote = float(recall) >= prior_recall
    store.insert_rag_eval_run(
        {
            "id": run_id,
            "reindex_run_id": payload.get("reindex_run_id"),
            "qa_set": qa_set,
            "recall_at_k": recall,
            "slug_recall_at_k": result.get("slug_recall_at_k"),
            "faithfulness": result.get("faithfulness"),
            "mean_correctness": result.get("mean_correctness"),
            "refusal_rate": result.get("refusal_rate"),
            "rerank": rerank,
            "status": "done",
            "created_at": now,
        }
    )
    return {
        "rag_eval_run_id": run_id,
        "qa_set": qa_set,
        "recall_at_k": recall,
        "slug_recall_at_k": result.get("slug_recall_at_k"),
        "rerank": rerank,
        "prior_recall_at_k": prior_recall,
        "promote": promote,
        "delta": (round(float(recall) - prior_recall, 4)
                  if prior_recall is not None and recall is not None else None),
    }


def _persist_rl_run(
    store: Any, payload: Mapping[str, Any], result: Mapping[str, Any], now: str
) -> dict[str, Any]:
    """Summarize an ``rl_run`` result for ``jobs.result_json`` (RV-7/RV-8).

    **No new arena.db table** (RV-8): the per-step trajectory already rode
    `fieldkit.lineage` (the ``rl_run`` card is the run's ``LineageSnapshot``) and
    the held-out checkpoint scores rode the ``eval_runs`` / leaderboard path via
    the loop's dispatched ``eval_rerun`` gate. This persists only the aggregate
    digest the standup + the Phase-3 "living-model" delta chart read: the
    held-out-selected step, the held-out vs pool trajectories, and the base. The
    selection metric is **held-out, never pool** (RV-4) — echoed as
    ``selected_on`` so a downstream consumer can't misread it.
    """
    return {
        "kind": JobKind.RL_RUN,
        "base": result.get("base", payload.get("base")),
        "vertical": result.get("domain", payload.get("vertical")),
        "n_steps": result.get("n_steps"),
        "selected_step": result.get("selected_step"),
        "selected_heldout_score": result.get("selected_heldout_score"),
        "heldout_scores": result.get("heldout_scores"),
        "pool_scores": result.get("pool_scores"),
        "selected_on": result.get("selected_on", "heldout"),
        # AE-3/AE-4 (arena-enhancements S1) — the bounded per-step trajectory +
        # the selected-step → lineage-trial back-pointer. Pure passthrough from
        # RLLoop.summary(); both land in the existing result_json column (RV-8,
        # no schema change). None on a bare M8/RV-6 run that didn't populate them.
        "step_history": result.get("step_history"),
        "selected_exp_id": result.get("selected_exp_id"),
        "lineage_card": result.get("lineage_card"),
        # rl-lane-autonomy (LA-10/11) — the memory trace + whether the watchdog
        # tore the run down early. Present only when the run drained under an
        # RLLaneContext; absent (bare M8/RV-6 run) leaves these None/False.
        "mem_trace": result.get("mem_trace"),
        "aborted": bool(result.get("aborted", False)),
    }


def _run_rl_arbitered(
    store: Any,
    job_id: str,
    job: Mapping[str, Any],
    payload: Mapping[str, Any],
    runner: Callable[[str, Mapping[str, Any]], dict[str, Any]],
    now_fn: Callable[[], str],
    rl_lane: Any,
) -> dict[str, Any]:
    """Run one ``rl_run`` under the RL-lane arbiter (rl-lane-autonomy LA-1..11).

    Sets up the live-progress writer (LA-8) + an OOM abort sentinel (LA-10) +
    the per-run memory trace (LA-11), enters the :class:`fieldkit.arena.lane.
    LaneArbiter` (the 3-way pre-flight → resident-brain teardown → watchdog),
    binds the loop's observability hooks, and runs the same ``runner`` the bare
    path uses — so `run_rl_loop` is untouched. A pre-flight failure raises
    :class:`~fieldkit.arena.lane.LaneDeferred` (caught by :func:`dispatch_job`,
    which releases the claim + audits, never *fails* the job). The returned dict
    is the runner result augmented with ``mem_trace`` + ``aborted``.
    """
    from fieldkit.arena import lane as _lane
    from fieldkit.rl import rl_hooks

    mem = _lane.mem_trace()
    sentinel = rl_lane.sentinel_for(job_id)
    sentinel.unlink(missing_ok=True)  # fresh — no stale abort from a prior run
    _board_writer = _lane.rl_progress_writer(
        store, job_id, mem=mem, min_interval=rl_lane.throttle_s, used_sampler=_lane.unified_used_gb
    )
    # AE-1 (arena-enhancements S1) — also light the /arena/reward/ gauge: at each
    # held-out gate, write an av10-preflight-shaped report to the dir the gauge
    # auto-follows. Composed onto the SAME progress_cb so the loop stays the lone
    # writer of result_json (LA-8) while the gauge gets its own file feed.
    _reward_writer = _lane.reward_signal_writer(
        job_id, model=payload.get("base"), vertical=payload.get("vertical")
    )

    def progress_cb(blob: Mapping[str, Any]) -> None:
        _board_writer(blob)
        try:
            _reward_writer(blob)
        except Exception:  # noqa: BLE001 — the gauge feed never fails the run
            pass

    should_abort = _lane.abort_poller(sentinel)
    arbiter = rl_lane.arbiter_for(job, mem, sentinel)
    try:
        with arbiter:  # __enter__ raises LaneDeferred on a failed pre-flight (LA-6)
            with rl_hooks(progress_cb, should_abort):
                result = dict(runner(JobKind.RL_RUN, payload))
    finally:
        aborted = sentinel.exists()
        sentinel.unlink(missing_ok=True)
    result["mem_trace"] = mem.as_dict()
    result["aborted"] = aborted
    return result


def dispatch_job(
    store: Any,
    job: Mapping[str, Any],
    *,
    runner: Callable[[str, Mapping[str, Any]], dict[str, Any]] = default_runner,
    now_fn: Callable[[], str] = _utc_now_iso,
    rl_lane: Optional[Any] = None,
) -> dict[str, Any]:
    """Run one claimed job end-to-end; return the updated job row as a dict.

    ``job`` is a ``dispatched`` row (from :meth:`ArenaStore.claim_next_job`).
    Flips it ``running`` → executes via ``runner`` (the harness surface) →
    ``done`` (persisting through the existing scorer path for ``eval_rerun``)
    or ``failed`` (stamping ``jobs.error`` + re-raising :class:`JobDispatchError`).

    ``rl_lane`` (rl-lane-autonomy, LA-1..11) is an optional
    :class:`fieldkit.arena.lane.RLLaneContext`. When wired **and** ``kind`` is
    ``rl_run`` the run is arbitered (envelope pre-flight → resident-brain
    teardown → OOM watchdog → live progress → mem-trace); a pre-flight defer
    releases the claim back to ``queued`` + audits (never *fails*). When ``None``
    (the M8 default) every kind — `rl_run` included — runs bare, byte-for-byte
    RV-6 behavior, so existing callers/tests are unaffected.
    """
    job_id = str(job["id"])
    kind = str(job["kind"])
    if kind not in JobKind.DISPATCHABLE:
        store.update_job(
            job_id,
            status=JobStatus.FAILED,
            error=f"kind {kind!r} not dispatchable",
            finished_at=now_fn(),
        )
        raise UnknownJobKind(f"job kind {kind!r} is not dispatchable")

    payload = json.loads(job["payload_json"])
    store.update_job(job_id, status=JobStatus.RUNNING)
    try:
        if kind == JobKind.RL_RUN and rl_lane is not None:
            from fieldkit.arena.lane import LaneDeferred

            try:
                result = _run_rl_arbitered(
                    store, job_id, job, payload, runner, now_fn, rl_lane
                )
            except LaneDeferred as deferred:
                # A failed 3-way pre-flight (LA-6): release the claim back to
                # queued + audit (the AH-4 path), leave the job for the next
                # tick — it is deferred, NOT failed.
                _release_and_audit(store, job, deferred.decision, now_fn())
                row = store.get_job(job_id)
                return {k: row[k] for k in row.keys()}
        else:
            result = runner(kind, payload)
        now = now_fn()
        if kind == JobKind.EVAL_RERUN:
            summary = _persist_eval_rerun(store, payload, result, now)
        elif kind in (JobKind.REINDEX, JobKind.SCOUT_INGEST):
            summary = _persist_reindex(store, payload, result, now)
        elif kind == JobKind.RAG_EVAL:
            summary = _persist_rag_eval(store, payload, result, now)
        elif kind == JobKind.RL_RUN:
            summary = _persist_rl_run(store, payload, result, now)
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


def _release_and_audit(
    store: Any, job: Mapping[str, Any], decision: Any, now: str
) -> None:
    """Return a governor-held job to ``queued`` + record why (M11, AH-4).

    The drain claimed (``dispatched``) the job before consulting the governor;
    a non-``allow`` verdict releases that claim back to ``queued`` (so the *next*
    cron tick reconsiders it once spend resets / a frontier lane is approved)
    and writes a ``job_triggers`` audit row (``budget_<action>``) carrying the
    decision detail. No schedule state is persisted (AH-9) — the trigger row +
    the still-queued job ARE the state.
    """
    store.update_job(str(job["id"]), status=JobStatus.QUEUED, dispatched_at=None)
    store.record_job_trigger(
        JobTriggerRecord(
            job_id=str(job["id"]),
            source=f"budget_{getattr(decision, 'action', 'defer')}",
            detail_json=json.dumps(
                {
                    "reason": getattr(decision, "reason", "unknown"),
                    **getattr(decision, "detail", {}),
                },
                sort_keys=True,
            ),
            created_at=now,
        )
    )


def drain_jobs(
    store: Any,
    *,
    runner: Callable[[str, Mapping[str, Any]], dict[str, Any]] = default_runner,
    max_jobs: Optional[int] = None,
    now_fn: Callable[[], str] = _utc_now_iso,
    on_error: str = "record",
    governor: Optional[Any] = None,
    rl_lane: Optional[Any] = None,
) -> list[dict[str, Any]]:
    """Drain the queue one job at a time until empty (M8-5, sequential).

    Claims the oldest ``queued`` job, dispatches it, repeats. ``max_jobs``
    caps a single drain pass (the **M11 cron calls this on a schedule** via
    :func:`fieldkit.arena.scheduler.run_drain_cycle`). ``on_error='record'``
    (default) keeps draining past a failed job (it's already marked ``failed``);
    ``on_error='raise'`` stops at the first failure.

    ``governor`` (M11, AH-4) is an optional duck-typed budget governor — anything
    with ``.check_budget(job) -> BudgetDecision`` (the :class:`fieldkit.budget.
    BudgetGovernor`). When wired, each claimed job is checked **before** dispatch:
    an *allow* dispatches as usual; an *escalate* / *defer* releases the claim
    back to ``queued``, records a ``budget_<action>`` audit row, and **stops the
    pass** (the budget brake — a daily-cap defer holds all remaining work; an
    escalate leaves the job for the operator to promote to a frontier lane from
    the standup). The drain never escalates or pushes itself (AH-3 / AH-8): it
    *stages* the decision for the human-review gate. Returns the updated row dict
    for every job it actually dispatched.

    ``rl_lane`` (rl-lane-autonomy) is an optional
    :class:`fieldkit.arena.lane.RLLaneContext` passed straight to
    :func:`dispatch_job`; it only affects ``rl_run`` jobs (arbiter + watchdog +
    live progress) and is inert for every other kind. ``None`` = bare M8 behavior.
    """
    done: list[dict[str, Any]] = []
    while max_jobs is None or len(done) < max_jobs:
        claimed = store.claim_next_job(dispatched_at=now_fn())
        if claimed is None:
            break
        job = {k: claimed[k] for k in claimed.keys()}
        if governor is not None:
            decision = governor.check_budget(job)
            if not getattr(decision, "allowed", False):
                _release_and_audit(store, job, decision, now_fn())
                break  # budget brake — leave the rest queued for the next tick
        if rl_lane is not None and str(job.get("kind")) == JobKind.RL_RUN:
            # rl-lane brake (LA-6): a failed 3-way pre-flight (no vLLM binary, or
            # the lane won't fit) releases the claim + audits + stops the pass —
            # so an undispatchable rl_run can't spin the drain re-claiming itself.
            lane_decision = rl_lane.preflight(job)
            if lane_decision is not None:
                _release_and_audit(store, job, lane_decision, now_fn())
                break
        try:
            done.append(
                dispatch_job(store, job, runner=runner, now_fn=now_fn, rl_lane=rl_lane)
            )
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


def check_and_enqueue_regressions(
    store: Any,
    *,
    tau: float = DEFAULT_REGRESSION_TAU,
    now_fn: Callable[[], str] = _utc_now_iso,
) -> dict[str, Any]:
    """The wired producer (M8-2): diff the live leaderboard against the stored
    baseline, enqueue a confirming ``eval_rerun`` per regression, then re-set
    the baseline to the current snapshot.

    This is the missing link between the pure :func:`detect_leaderboard_regression`
    core and the running cockpit — an operator-triggered scan (``POST
    /api/jobs/check-regressions``; the Phase-2 cron will call the same code on a
    schedule). The baseline is per ``(bench, lane)`` accuracy, persisted in
    ``leaderboard_baseline``; the first scan only *sets* the baseline (nothing
    to diff against → no regressions), so a fresh box never storms.

    Returns ``{checked, baselined, enqueued: [job_id, …], regressions: [delta,
    …]}``. Dedup (R15) still applies — a confirming re-eval already in flight
    for the same bench×lane yields no new id.
    """
    curr = store.eval_leaderboard()
    prev = store.leaderboard_baseline()
    regressions = detect_leaderboard_regression(prev, curr, tau=tau)
    enqueued = enqueue_regressions(store, prev, curr, tau=tau, now_fn=now_fn)
    store.snapshot_leaderboard_baseline(curr, now=now_fn())
    return {
        "checked": len(curr),
        "baselined": len(curr),
        "had_baseline": len(prev) > 0,
        "enqueued": enqueued,
        "regressions": regressions,
    }
