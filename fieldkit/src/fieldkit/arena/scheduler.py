# Copyright 2026 Manav Sehgal
# SPDX-License-Identifier: Apache-2.0
"""`fieldkit.arena.scheduler` — the M11 cron glue over the built drain (AH-1).

The **hands** in the `pane → hands → engine` sequence: the missing *trigger*
that turns M8's button-driven dispatcher into a self-operating overnight loop
with a human-review gate. M11 reimplements **no dispatch** — it calls the
already-built :func:`fieldkit.arena.jobs.drain_jobs` +
:func:`~fieldkit.arena.jobs.check_and_enqueue_regressions` on a schedule, gated
by the :class:`fieldkit.budget.BudgetGovernor`, behind a one-drain-at-a-time
lock, and stages a morning standup it **never pushes** (AH-3 / invariants #1/#3).

Three pieces (`_SPECS/spark-arena-v1.md` §15.3):

1. :class:`DrainLock` — the one-drain-at-a-time file lock (the
   ``scheduled_tasks.lock`` pattern, AH-1) with stale-pid stealing, so two cron
   ticks can never stack a second model lane on the resident brain (R24).
2. :func:`run_drain_cycle` — one cron tick: acquire the lock, drain (governor in
   the loop), run the freshness sweep (AH-6), build the standup, release. Returns
   the standup dict; **no push path exists by construction** (R26).
3. :func:`build_standup` — the AH-3 render over the *existing* tables
   (``jobs`` / ``leaderboard_baseline`` / the M9 cost rows): **Ran / Regressed /
   Queued / Spend**. Aggregate, operator-private, stage-only.

No schema, no ``user_version`` bump (AH-9): schedules live in version-controlled
config + a ``/schedule`` routine; the standup is an ephemeral render. Per
`feedback_llm_skill_pattern`: deterministic Python only — no ``anthropic`` /
``claude_agent_sdk`` import, no LLM call. The scheduler is the loop; the work it
drains is the same harness-contained dispatch M8 built (AH-8).
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, Optional

from fieldkit.arena.jobs import (
    DEFAULT_REGRESSION_TAU,
    check_and_enqueue_regressions,
    default_runner,
    drain_jobs,
)

__all__ = [
    "DrainLock",
    "DrainLockHeld",
    "run_drain_cycle",
    "build_standup",
    "DEFAULT_LOCK_PATH",
    "DEFAULT_AUTONOMY_PATH",
    "read_autonomy_state",
    "write_autonomy_state",
    "clear_autonomy_state",
    "autonomy_cron_line",
]

#: The drain lock lives beside arena.db (NOT ``.claude/scheduled_tasks.lock`` —
#: that path is the CC harness's own lock; M11 reuses the *pattern*, not the
#: file). Override with ``$ARENA_DRAIN_LOCK``.
DEFAULT_LOCK_PATH = "~/.fieldkit/arena/drain.lock"

#: The autonomy *policy* record (LA-5): ``{enabled, interval_min, cap_usd,
#: armed_at, db}`` written by ``fieldkit arena autonomy on``. NOT schedule
#: *state* (AH-9) — it records that the operator armed the overnight cron + the
#: knobs the standup echoes back; the cron line itself lives in the user's
#: crontab. Override with ``$ARENA_AUTONOMY_STATE``.
DEFAULT_AUTONOMY_PATH = "~/.fieldkit/arena/autonomy.json"

#: How many done/queued rows the standup surfaces per bucket (newest first).
STANDUP_LIMIT = 50


# ---------------------------------------------------------------------------
# Autonomy policy record (LA-5) — the one reversible "arm the cron" step
# ---------------------------------------------------------------------------


def _autonomy_path(path: Optional[str] = None) -> Path:
    return Path(
        os.path.expanduser(path or os.environ.get("ARENA_AUTONOMY_STATE", DEFAULT_AUTONOMY_PATH))
    )


def read_autonomy_state(path: Optional[str] = None) -> dict[str, Any]:
    """The current autonomy policy (LA-5), or ``{"enabled": False}`` when unarmed."""
    p = _autonomy_path(path)
    try:
        data = json.loads(p.read_text())
        if isinstance(data, dict):
            data.setdefault("enabled", False)
            return data
    except (OSError, json.JSONDecodeError):
        pass
    return {"enabled": False}


def write_autonomy_state(state: Mapping[str, Any], path: Optional[str] = None) -> Path:
    """Persist the autonomy policy record (LA-5). Returns the path written."""
    p = _autonomy_path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(dict(state), sort_keys=True, indent=2))
    return p


def clear_autonomy_state(path: Optional[str] = None) -> bool:
    """Remove the autonomy policy record (``autonomy off``). True if one existed."""
    p = _autonomy_path(path)
    existed = p.exists()
    p.unlink(missing_ok=True)
    return existed


def autonomy_cron_line(db: str, interval_min: int) -> str:
    """The crontab line that arms the overnight drain (LA-5).

    Calls ``fieldkit arena drain`` every ``interval_min`` minutes against the
    operator-private ``db``; the drain is single-lane + lock-guarded, so two
    ticks can never stack a second GPU lane (R24). Emitted for the operator to
    install (or installed by ``autonomy on --install-cron``)."""
    every = max(1, int(interval_min))
    return f"*/{every} * * * * fieldkit arena drain --db {db}  # fieldkit-arena-autonomy"


def _utc_now_iso() -> str:
    """ISO-8601 UTC stamp, matching the dispatcher + mirror convention."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _pid_alive(pid: int) -> bool:
    """True if a process with ``pid`` is alive (signal-0 probe; PID 0 = never)."""
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True  # exists, owned by another user
    return True


class DrainLockHeld(Exception):
    """Raised by :meth:`DrainLock.acquire` (strict mode) when a live drain holds it."""


class DrainLock:
    """A one-drain-at-a-time file lock (AH-1, the R24 OOM bound).

    A best-effort advisory lock: ``acquire`` writes ``{pid, acquired_at}`` to the
    lock path iff no live holder exists. A **stale** lock — one whose recorded
    pid is no longer alive (the ``scheduled_tasks.lock`` from a dead session was
    exactly this case, recon #5) — is silently stolen. Use as a context manager;
    :attr:`acquired` reports whether this process owns it, so the caller can skip
    a tick rather than stack a second GPU lane.
    """

    def __init__(self, path: Optional[str] = None) -> None:
        self.path = Path(
            os.path.expanduser(
                path or os.environ.get("ARENA_DRAIN_LOCK", DEFAULT_LOCK_PATH)
            )
        )
        self.acquired = False

    def _holder_alive(self) -> bool:
        """True if the lock file names a still-running process."""
        try:
            data = json.loads(self.path.read_text())
        except (OSError, json.JSONDecodeError):
            return False  # missing or corrupt → not a live holder
        return _pid_alive(int(data.get("pid", 0)))

    def acquire(self, *, strict: bool = False) -> bool:
        """Take the lock; return whether this process now owns it.

        Steals a stale lock (dead-pid holder). With ``strict=True`` a live holder
        raises :class:`DrainLockHeld` instead of returning ``False``.
        """
        if self._holder_alive():
            if strict:
                raise DrainLockHeld(f"a live drain holds {self.path}")
            self.acquired = False
            return False
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(
                {"pid": os.getpid(), "acquired_at": _utc_now_iso()}, sort_keys=True
            )
        )
        self.acquired = True
        return True

    def release(self) -> None:
        """Drop the lock iff this process owns it (never another holder's)."""
        if not self.acquired:
            return
        try:
            data = json.loads(self.path.read_text())
            if int(data.get("pid", 0)) == os.getpid():
                self.path.unlink(missing_ok=True)
        except (OSError, json.JSONDecodeError):
            pass
        self.acquired = False

    def __enter__(self) -> "DrainLock":
        self.acquire()
        return self

    def __exit__(self, *exc: Any) -> None:
        self.release()


def _job_brief(row: Any) -> dict[str, Any]:
    """Aggregate-safe projection of a ``jobs`` row for the standup.

    Carries id / kind / status / trigger / timestamps + the compact
    ``result_json`` summary — **never** ``payload_json`` (operator prompts /
    lanes / benches, on the mirror denylist, R13). The standup is the only
    promote path and it shows *what ran*, not *what was asked*.
    """
    keys = ("id", "kind", "status", "trigger", "enqueued_at", "finished_at", "result_json")
    out: dict[str, Any] = {}
    for k in keys:
        try:
            out[k] = row[k]
        except (KeyError, IndexError):
            out[k] = None
    return out


def _rl_mem_digest(ran: list[dict[str, Any]]) -> dict[str, Any]:
    """Roll up the rl-lane memory traces (LA-11) from this cycle's done jobs.

    Scans the ``ran`` briefs for ``rl_run`` results carrying a ``mem_trace`` and
    summarizes peak unified-mem + OOM-defer count into the standup's ``rl`` row —
    so an OOM becomes "RAN 1 · peak 119 GB · 1 OOM-deferred at bring-up", never a
    silent hang. Aggregate-only (no payloads), stage-safe.
    """
    n_rl = 0
    peak = None
    oom = 0
    aborted = 0
    for brief in ran:
        rj = brief.get("result_json")
        if not isinstance(rj, str) or not rj:
            continue
        try:
            res = json.loads(rj)
        except json.JSONDecodeError:
            continue
        if not isinstance(res, dict) or res.get("kind") != "rl_run":
            continue
        n_rl += 1
        if res.get("aborted"):
            aborted += 1
        trace = res.get("mem_trace")
        if isinstance(trace, dict):
            p = trace.get("peak_used_gb")
            if isinstance(p, (int, float)) and (peak is None or p > peak):
                peak = p
            if trace.get("oom_deferred"):
                oom += 1
    parts: list[str] = [f"RAN {n_rl}"]
    if peak is not None:
        parts.append(f"peak {peak:.0f} GB")
    if oom:
        parts.append(f"{oom} OOM-deferred")
    if aborted:
        parts.append(f"{aborted} aborted")
    return {
        "n_rl_run": n_rl,
        "peak_used_gb": peak,
        "oom_deferred": oom,
        "aborted": aborted,
        "display": " · ".join(parts) if n_rl else "—",
    }


def build_standup(
    store: Any,
    *,
    governor: Optional[Any] = None,
    sweep: Optional[dict[str, Any]] = None,
    cap_usd: Optional[float] = None,
    now_fn: Callable[[], str] = _utc_now_iso,
) -> dict[str, Any]:
    """Assemble the morning-standup render (AH-3) over the existing tables.

    Four buckets, all read-only:

    - **ran** — recent ``done`` jobs (what the overnight drain completed).
    - **regressed** — the deltas from this cycle's freshness ``sweep`` (the
      ``leaderboard_baseline`` diff), else an empty list on a render-only call.
    - **queued** — pending jobs (including any the budget governor *deferred*
      back to the queue this pass — their ``budget_<action>`` audit row records
      why; see :func:`fieldkit.arena.jobs.drain_jobs`).
    - **spend** — the M9 :class:`fieldkit.budget.SpendDigest` (today's $ by lane
      vs cap), or "—" when the cost plane is absent (AH-5).

    The result is operator-private + **stage-only**: it has no push capability,
    no per-run prompt, no per-run cost — invariants #1/#3, R26. ``governor``
    supplies the cost ledger + cap for the Spend row; without it the spend digest
    degrades to "—".
    """
    from fieldkit.budget import SpendDigest  # lazy — budget is a sibling top-level module

    ran = [_job_brief(r) for r in store.list_jobs(status="done", limit=STANDUP_LIMIT)]
    failed = [_job_brief(r) for r in store.list_jobs(status="failed", limit=STANDUP_LIMIT)]
    queued = [_job_brief(r) for r in store.list_jobs(status="queued", limit=STANDUP_LIMIT)]
    regressed = list(sweep.get("regressions", [])) if sweep else []

    if governor is not None:
        digest = governor.spend_digest(cap_usd=cap_usd)
    else:
        digest = SpendDigest.from_store(store, cap_usd=cap_usd)

    return {
        "generated_at": now_fn(),
        "ran": ran,
        "failed": failed,
        "regressed": regressed,
        "queued": queued,
        "spend": digest.as_dict(),
        # rl-lane-autonomy LA-5/11 — the armed-policy state + the memory digest
        # over any rl_run that drained ("RAN 1 · peak 119 GB · 1 OOM-deferred").
        "autonomy": read_autonomy_state(),
        "rl": _rl_mem_digest(ran),
        "counts": {
            "ran": len(ran),
            "failed": len(failed),
            "regressed": len(regressed),
            "queued": len(queued),
        },
        "staged_only": True,  # AH-3 — no push capability (R26)
    }


def run_drain_cycle(
    store: Any,
    *,
    governor: Optional[Any] = None,
    runner: Callable[[str, Any], dict[str, Any]] = default_runner,
    max_jobs: Optional[int] = None,
    freshness: bool = True,
    tau: float = DEFAULT_REGRESSION_TAU,
    cap_usd: Optional[float] = None,
    lock: Optional[DrainLock] = None,
    rl_lane: Optional[Any] = None,
    now_fn: Callable[[], str] = _utc_now_iso,
) -> dict[str, Any]:
    """One cron tick (the §15.3 scheduler flow) — drain, sweep, stage the standup.

    Steps, all behind the one-drain-at-a-time lock (R24):

    1. acquire :class:`DrainLock` — if a live drain holds it, return early with
       ``{"skipped": True}`` (never stack a second GPU lane).
    2. :func:`drain_jobs` with the ``governor`` in the loop (single-lane,
       ``max_jobs``-capped, the budget brake stops the pass on a defer/escalate).
    3. :func:`check_and_enqueue_regressions` — the freshness sweep (AH-6) emits
       new ``eval_rerun`` triggers into the same queue for the *next* tick.
    4. :func:`build_standup` — the stage-only review render (AH-3).
    5. release the lock.

    Returns ``{"skipped", "drained": [job ids], "sweep", "standup"}``. **No push**
    (R26): the cron stages the standup; the operator reviews + promotes manually.
    """
    lk = lock or DrainLock()
    if not lk.acquire():
        return {
            "skipped": True,
            "reason": "a drain is already in progress",
            "drained": [],
            "sweep": None,
            "standup": None,
        }
    try:
        # rl-lane-autonomy: arbiter an rl_run when it drains (envelope pre-flight
        # → resident-brain teardown → OOM watchdog → live progress). Default-built
        # from the governor so the autonomous cron runs the engine safely; inert
        # for every non-rl_run kind (LA-1..11). Pass rl_lane=False to opt out.
        if rl_lane is None:
            from fieldkit.arena.lane import RLLaneContext

            rl_lane = RLLaneContext(governor=governor)
        drained = drain_jobs(
            store,
            runner=runner,
            max_jobs=max_jobs,
            governor=governor,
            rl_lane=rl_lane or None,
            now_fn=now_fn,
        )
        sweep = (
            check_and_enqueue_regressions(store, tau=tau, now_fn=now_fn)
            if freshness
            else None
        )
        standup = build_standup(
            store, governor=governor, sweep=sweep, cap_usd=cap_usd, now_fn=now_fn
        )
        return {
            "skipped": False,
            "drained": [j.get("id") for j in drained],
            "n_drained": len(drained),
            "sweep": sweep,
            "standup": standup,
        }
    finally:
        lk.release()
