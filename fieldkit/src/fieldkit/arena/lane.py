# Copyright 2026 Manav Sehgal
# SPDX-License-Identifier: Apache-2.0
"""`fieldkit.arena.lane` — the RL-lane autonomy arbiter (rl-lane-autonomy-v1).

The **self-driving** layer for the Phase-3 engine: the connective tissue that
turns a dispatchable `rl_run` (RV-6) into a run that is *self-driving*,
*observable*, and *self-defending* — without re-implementing any GPU physics.
It wires together primitives that already shipped:

- :class:`fieldkit.budget.MemoryEnvelope` — the one-lane OOM guard (LA-1/6/10).
- :class:`fieldkit._rl_gpu_serve.VLLMLane` — the EngineCore-aware serve lane the
  arbiter tears down on exit (its ``stop`` is a process-pattern ``pkill``, so it
  also reaps the seam-started vLLM — `[[feedback_vllm_engine_core_orphan]]`).
- ``jobs.result_json`` + ``update_job`` — the live progress channel the loop
  writes throttled step state into (LA-8); **no schema change** (LA-7).
- ``/proc/meminfo`` — the same unified-mem source ``TelemetryHub`` samples, so
  the :class:`MemoryWatchdog` enforces a headroom floor *before* the kernel
  OOM-kills the box (the 2026-04-22 landmine, `[[project_spark_unified_memory_oom]]`).

Four public surfaces (`_SPECS/rl-lane-autonomy-v1.md` §3.1/§3.3):

- :class:`LaneArbiter` — the envelope-gated single-lane context manager
  (LA-1/2/6): a 3-way pre-flight (governor *allow* ∧ envelope *fits* ∧ lane
  binary present) → tears down the resident chat brain → runs under the
  watchdog → restores the prior lane on exit.
- :class:`MemoryWatchdog` — the telemetry-correlated OOM defense (LA-10):
  persistent-breach → touch an abort sentinel the loop polls between steps.
- :func:`mem_trace` — the per-run memory recorder (LA-11): peak / headroom /
  per-phase deltas → the lineage card + the standup.
- :class:`RLLaneContext` — the one optional object dispatch consults for an
  `rl_run` job; absent (the M8 default) `rl_run` runs bare, byte-for-byte.

Per `feedback_llm_skill_pattern`: deterministic Python only — no ``anthropic`` /
``claude_agent_sdk`` import, no LLM call. torch / vLLM are **never** imported at
module load (only inside :meth:`LaneArbiter.__enter__`'s lane factory), so
``import fieldkit.arena.lane`` stays stdlib-cheap.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, Optional

from fieldkit.arena import ArenaError

# rl_hooks/current_rl_hooks live in fieldkit.rl (where RLLoop reads them), so the
# arena layer pushes hooks downward without harness ever importing arena.
from fieldkit.rl import rl_hooks  # noqa: F401 — re-exported for dispatch

__all__ = [
    "LaneArbiter",
    "MemoryWatchdog",
    "MemTrace",
    "mem_trace",
    "RLLaneContext",
    "LaneError",
    "LaneDeferred",
    "lane_binary_present",
    "rl_progress_writer",
    "reward_signal_writer",
    "abort_poller",
    "unified_used_gb",
    "unified_total_gb",
    "headroom_gb",
    "rl_hooks",
]


class LaneError(ArenaError):
    """Base for the RL-lane arbiter's faults (a lane that won't start, …)."""


class LaneDeferred(LaneError):
    """The 3-way pre-flight declined a lane spawn (LA-6).

    Carries the :class:`fieldkit.budget.BudgetDecision` (action ``defer`` /
    ``escalate``) so the dispatcher releases the claim back to ``queued`` and
    writes the matching ``budget_<action>`` audit row — exactly the AH-4 path
    the M11 drain governor already uses.
    """

    def __init__(self, decision: Any) -> None:
        self.decision = decision
        reason = getattr(decision, "reason", "deferred")
        super().__init__(f"rl lane deferred: {reason}")


def _utc_now_iso() -> str:
    """ISO-8601 UTC stamp, matching the dispatcher + scheduler convention."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------------------------------------------------------------------------
# Unified-memory sampling — the same /proc/meminfo source TelemetryHub reads
# ---------------------------------------------------------------------------


def _meminfo_gb() -> tuple[Optional[float], Optional[float]]:
    """``(total_gb, available_gb)`` from ``/proc/meminfo`` (None on any failure)."""
    total = avail = None
    try:
        for ln in Path("/proc/meminfo").read_text().splitlines():
            key, _, rest = ln.partition(":")
            if key == "MemTotal":
                tok = rest.split()
                total = float(tok[0]) if tok else None
            elif key == "MemAvailable":
                tok = rest.split()
                avail = float(tok[0]) if tok else None
            if total is not None and avail is not None:
                break
    except OSError:
        return None, None
    total_gb = round(total / 1024 / 1024, 2) if total is not None else None
    avail_gb = round(avail / 1024 / 1024, 2) if avail is not None else None
    return total_gb, avail_gb


def unified_total_gb() -> Optional[float]:
    """Total unified memory (GB) — the 128 GB envelope's denominator."""
    return _meminfo_gb()[0]


def unified_used_gb() -> Optional[float]:
    """Used unified memory (GB) = total − available — the watchdog's numerator."""
    total, avail = _meminfo_gb()
    if total is None or avail is None:
        return None
    return round(total - avail, 2)


def headroom_gb(total: Optional[float] = None) -> Optional[float]:
    """Free unified memory (GB) above current use — what the floor floor guards."""
    total_gb, avail = _meminfo_gb()
    if avail is None:
        return None
    return avail  # MemAvailable IS the headroom; total arg kept for symmetry


# ---------------------------------------------------------------------------
# MemTrace — the per-run memory report (LA-11)
# ---------------------------------------------------------------------------


@dataclass
class MemTrace:
    """The memory trace one `rl_run` attaches to its lineage snapshot (LA-11).

    Thread-safe: the progress writer (loop thread) feeds per-phase *used* samples
    while the watchdog (its own thread) feeds *headroom* samples; both go through
    :meth:`observe` under a lock. ``as_dict`` is what rides ``jobs.result_json``
    + the standup; ``display`` is the one-line "peak 119 GB · 3 GB at abort".
    """

    total_gb: Optional[float] = None
    headroom_at_spawn_gb: Optional[float] = None
    peak_used_gb: Optional[float] = None
    min_headroom_gb: Optional[float] = None
    abort_headroom_gb: Optional[float] = None
    oom_deferred: bool = False
    phase_used_gb: dict[str, float] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def observe(
        self,
        *,
        used_gb: Optional[float] = None,
        headroom_gb: Optional[float] = None,
        phase: Optional[str] = None,
    ) -> None:
        """Fold one sample in (used and/or headroom), optionally tagged by phase."""
        with self._lock:
            if headroom_gb is not None:
                if self.min_headroom_gb is None or headroom_gb < self.min_headroom_gb:
                    self.min_headroom_gb = headroom_gb
                if used_gb is None and self.total_gb is not None:
                    used_gb = round(self.total_gb - headroom_gb, 2)
            if used_gb is not None:
                if self.peak_used_gb is None or used_gb > self.peak_used_gb:
                    self.peak_used_gb = used_gb
                if phase:
                    self.phase_used_gb[phase] = used_gb

    def mark_abort(self, headroom_gb: Optional[float]) -> None:
        """Record the headroom at an OOM abort (the watchdog's trip sample)."""
        with self._lock:
            self.abort_headroom_gb = headroom_gb
            self.oom_deferred = True

    def as_dict(self) -> dict[str, Any]:
        with self._lock:
            return {
                "total_gb": self.total_gb,
                "headroom_at_spawn_gb": self.headroom_at_spawn_gb,
                "peak_used_gb": self.peak_used_gb,
                "min_headroom_gb": self.min_headroom_gb,
                "abort_headroom_gb": self.abort_headroom_gb,
                "oom_deferred": self.oom_deferred,
                "phase_used_gb": dict(self.phase_used_gb),
                "display": self._display_locked(),
            }

    def display(self) -> str:
        with self._lock:
            return self._display_locked()

    def _display_locked(self) -> str:
        if self.peak_used_gb is None and self.min_headroom_gb is None:
            return "—"
        parts: list[str] = []
        if self.peak_used_gb is not None:
            parts.append(f"peak {self.peak_used_gb:.0f} GB")
        if self.oom_deferred and self.abort_headroom_gb is not None:
            parts.append(f"OOM-deferred at {self.abort_headroom_gb:.0f} GB headroom")
        elif self.min_headroom_gb is not None:
            parts.append(f"min headroom {self.min_headroom_gb:.0f} GB")
        return " · ".join(parts)


def mem_trace(*, total_gb: Optional[float] = None) -> MemTrace:
    """Seed a :class:`MemTrace` with the current envelope (LA-11).

    Reads the unified-memory total + headroom-at-spawn once so per-phase deltas
    and the peak are measured against a real baseline. ``total_gb`` overrides the
    ``/proc/meminfo`` read (a test passes a fixed envelope).
    """
    tot = total_gb if total_gb is not None else unified_total_gb()
    return MemTrace(total_gb=tot, headroom_at_spawn_gb=headroom_gb(tot))


# ---------------------------------------------------------------------------
# MemoryWatchdog — telemetry-correlated OOM defense (LA-10)
# ---------------------------------------------------------------------------


@dataclass
class MemoryWatchdog:
    """Enforce a unified-memory headroom floor during a GPU job (LA-10, arena-wide).

    Subscribed to the same ``/proc/meminfo`` headroom ``TelemetryHub`` samples,
    it warns below ``warn_gb`` and, on a breach that **persists ``persist_n``
    samples** (~2 s at the 0.5 s interval — the R6 anti-transient guard), trips:
    it touches the ``sentinel`` file the loop polls between steps and records the
    abort sample on the ``trace``. It **never** trips on a missing sample (R7) —
    a stale ``/proc/meminfo`` read returns ``"stale"`` and leaves a running job
    alone. Reusable by every GPU kind (`rl_run` is the proving ground).
    """

    sentinel: Path
    floor_gb: float = 4.0
    warn_gb: float = 8.0
    persist_n: int = 4
    interval: float = 0.5
    mem_sampler: Callable[[], Optional[float]] = headroom_gb
    trace: Optional[MemTrace] = None
    on_warn: Optional[Callable[[float], None]] = None
    _breaches: int = field(default=0, init=False)
    tripped: bool = field(default=False, init=False)
    _stop: threading.Event = field(default_factory=threading.Event, init=False, repr=False)
    _thread: Optional[threading.Thread] = field(default=None, init=False, repr=False)

    def poll(self) -> str:
        """Take one sample → ``ok`` | ``warn`` | ``breach`` | ``tripped`` | ``stale``.

        Pure enough to drive directly from a test (inject a scripted
        ``mem_sampler`` and call :meth:`poll` N times); the thread loop in
        :meth:`watch` just calls this on a cadence.
        """
        hr = self.mem_sampler()
        if hr is None:
            return "stale"  # R7 — never abort a running job on missing data
        if self.trace is not None:
            self.trace.observe(headroom_gb=hr)
        if hr < self.floor_gb:
            self._breaches += 1
            if self._breaches >= self.persist_n and not self.tripped:
                self.tripped = True
                if self.trace is not None:
                    self.trace.mark_abort(hr)
                self._touch_sentinel(hr)
                return "tripped"
            return "breach"
        self._breaches = 0
        if hr < self.warn_gb:
            if self.on_warn is not None:
                self.on_warn(hr)
            return "warn"
        return "ok"

    def _touch_sentinel(self, headroom: float) -> None:
        try:
            self.sentinel.parent.mkdir(parents=True, exist_ok=True)
            self.sentinel.write_text(
                json.dumps(
                    {
                        "reason": "oom_envelope",
                        "headroom_gb": headroom,
                        "floor_gb": self.floor_gb,
                        "tripped_at": _utc_now_iso(),
                    },
                    sort_keys=True,
                )
            )
        except OSError:
            pass

    def watch(self) -> None:
        """Start the background sampling thread (idempotent)."""
        if self._thread is not None:
            return
        self._stop.clear()

        def _loop() -> None:
            while not self._stop.is_set():
                try:
                    if self.poll() == "tripped":
                        break
                except Exception:  # noqa: BLE001 — a watchdog must never crash the run
                    pass
                self._stop.wait(self.interval)

        self._thread = threading.Thread(
            target=_loop, name="arena-rl-watchdog", daemon=True
        )
        self._thread.start()

    def stop(self) -> None:
        """Stop the sampling thread (joins with a short timeout)."""
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2)
            self._thread = None


# ---------------------------------------------------------------------------
# Live progress (LA-8) + abort sentinel poll
# ---------------------------------------------------------------------------


def rl_progress_writer(
    store: Any,
    job_id: str,
    *,
    mem: Optional[MemTrace] = None,
    min_interval: float = 30.0,
    used_sampler: Callable[[], Optional[float]] = unified_used_gb,
    clock: Callable[[], float] = time.monotonic,
) -> Callable[[Mapping[str, Any]], None]:
    """Build the throttled ``result_json`` progress callback (LA-8, single writer).

    The loop is the **only** writer of ``result_json`` while ``status='running'``
    (no race). A write fires on a **phase change** or a **held-out gate**
    (``progress['gate']``), else at most once per ``min_interval`` seconds — so
    8.5 h of steps is a trickle of single-row ``update_job`` patches, not churn
    (R5). Each write also folds a per-phase *used*-memory sample into ``mem``
    (LA-11) so the trace's per-phase deltas accrue from the same event stream.
    """
    state: dict[str, Any] = {"last_write": float("-inf"), "last_phase": None}

    def write(progress: Mapping[str, Any]) -> None:
        phase = progress.get("phase")
        if mem is not None:
            mem.observe(used_gb=used_sampler(), phase=phase if isinstance(phase, str) else None)
        now = clock()
        phase_changed = phase != state["last_phase"]
        gate = bool(progress.get("gate"))
        if not phase_changed and not gate and (now - state["last_write"]) < min_interval:
            return
        state["last_write"] = now
        state["last_phase"] = phase
        blob: dict[str, Any] = {"status": "running", **dict(progress)}
        if mem is not None:
            blob["mem"] = mem.as_dict()
        try:
            store.update_job(job_id, result_json=json.dumps(blob, sort_keys=True))
        except Exception:  # noqa: BLE001 — progress is best-effort, never fail the run
            pass

    return write


def abort_poller(sentinel: Any) -> Callable[[], bool]:
    """Build the ``should_abort`` callback the loop polls between steps (LA-10).

    Returns True once the watchdog (or an operator) has touched ``sentinel`` —
    a filesystem signal so the watchdog thread and the loop need share no memory
    (and an operator can trip it by hand to stop a run cleanly).
    """
    path = Path(sentinel)

    def should_abort() -> bool:
        return path.exists()

    return should_abort


def _reward_signal_dir(override: Optional[Any] = None) -> Path:
    """Resolve the dir the reward gauge auto-follows (AE-1).

    Mirrors the server's ``_reward_reports_dir`` (``repo_root/evidence/
    astrodynamics``) so a report written here is the one ``/api/reward-signal``
    picks up. Precedence: explicit ``override`` → ``FK_ARENA_REWARD_DIR`` →
    ``ARENA_REPO_ROOT``/evidence/astrodynamics → cwd/evidence/astrodynamics.
    """
    if override:
        return Path(os.path.expanduser(str(override)))
    env = os.environ.get("FK_ARENA_REWARD_DIR")
    if env:
        return Path(os.path.expanduser(env))
    root = os.environ.get("ARENA_REPO_ROOT") or os.getcwd()
    return Path(root) / "evidence" / "astrodynamics"


def reward_signal_writer(
    job_id: str,
    *,
    reward_dir: Optional[Any] = None,
    model: Optional[str] = None,
    vertical: Optional[str] = None,
    n_heldout: Optional[int] = None,
) -> Callable[[Mapping[str, Any]], None]:
    """Light the ``/arena/reward/`` gauge from a live ``rl_run`` (AE-1 / AF-11).

    The reward pane auto-follows the **newest** ``av10-preflight*.json`` by mtime
    (server ``_reward_reports_dir`` = ``repo_root/evidence/astrodynamics``). An
    ``rl_run`` writes its live progress to ``jobs.result_json`` (the Jobs-board
    strip), never that dir — so the dedicated gauge stayed **dark during the run
    it exists for** (the AF-11 root cause: AF-9's "same transport, no UI change"
    assumption failed at first contact).

    Composed onto the loop's ``progress_cb``, this drops an **av10-preflight-
    shaped** report into the followed dir at every held-out **gate** (and a final
    ``status:done`` write on teardown): the held-out reward → ``reward_rate_step0``
    (the gauge's key — **not** ``reward``, the ledger foot-gun), the step, and the
    running/done status. Unsurfaced fields (boxed-rate, truncation, buckets, rows)
    are left empty/calm — the held-out seam returns a scalar today (a richer
    report is a future pane change, deliberately out of v1's zero-pane-change
    scope). Best-effort: a write failure never fails the run.
    """
    base = _reward_signal_dir(reward_dir)
    short = str(job_id)[:8]
    slug = (vertical or "rl").replace("/", "-")
    target = base / f"av10-preflight-rl-{slug}-{short}.json"
    state: dict[str, Any] = {"held": None, "step": None, "written": False}

    def write(progress: Mapping[str, Any]) -> None:
        phase = progress.get("phase")
        gate = bool(progress.get("gate"))
        if gate:
            state["held"] = progress.get("last_heldout")
            state["step"] = progress.get("step")
        elif phase == "teardown":
            if not state["written"]:
                return  # no gate ever ran — nothing to finalize
        else:
            return
        report = {
            "model": model or progress.get("base"),
            "vertical": vertical or progress.get("domain"),
            "kind": "rl_run",  # discriminator (server tolerates extra keys)
            "step": state["step"],
            "n": n_heldout,
            "total": n_heldout,
            "scored": n_heldout,
            "status": "done" if phase == "teardown" else "running",
            "boxed_rate": None,
            "reward_rate_step0": state["held"],  # gauge key — the held-out reward
            "truncation_rate": 0.0,  # unknown via the scalar seam → calm AV-R1
            "gate_pass": None,
            "buckets": {},
            "rows": [],
        }
        try:
            base.mkdir(parents=True, exist_ok=True)
            target.write_text(json.dumps(report, sort_keys=True))
            state["written"] = True
        except OSError:  # noqa: BLE001 — the gauge is observational, never load-bearing
            pass

    return write


# ---------------------------------------------------------------------------
# Lane discovery + the arbiter (LA-1/2/3/6)
# ---------------------------------------------------------------------------


def lane_binary_present(cfg: Any) -> bool:
    """True when a vLLM serving binary is discoverable for the lane (LA-3/6).

    The arbiter's third pre-flight check. vLLM is an out-of-tree *managed
    process*, not a dep (no aarch64+CUDA-13 wheel, `[[project_verl_atgpo_vllm_gap]]`),
    so presence is the operator's signal: ``FK_RL_VLLM_BIN`` pointing at an
    existing file, an ``FK_RL_SERVE_CMD`` whose launcher resolves, or a ``vllm``
    on ``PATH``. Absent all three → the arbiter ``defer``s with ``LANE_BIN_ABSENT``
    (a clean hold, never a crash).
    """
    binp = os.environ.get("FK_RL_VLLM_BIN")
    if binp:
        return Path(os.path.expanduser(binp)).exists()
    override = getattr(cfg, "serve_cmd_override", "") or ""
    if override:
        first = override.split()[0] if override.split() else ""
        return bool(first) and (
            shutil.which(first) is not None or Path(os.path.expanduser(first)).exists()
        )
    return shutil.which("vllm") is not None


def _default_lane(cfg: Any) -> Any:
    """Build the real :class:`fieldkit._rl_gpu_serve.VLLMLane` for teardown.

    Imported lazily so ``import fieldkit.arena.lane`` stays stdlib-cheap; the
    lane's ``stop`` is a process-pattern ``pkill`` (it reaps the seam-started
    vLLM too — they need not be the same handle).
    """
    from fieldkit._rl_gpu_serve import VLLMLane

    return VLLMLane(cfg)


def _job_lane_id(job: Mapping[str, Any]) -> Optional[str]:
    """The ``lane_id`` off a ``jobs`` row (``payload_json``) or a synthetic job."""
    if not job:
        return None
    raw = job.get("payload")
    if isinstance(raw, Mapping):
        return raw.get("lane_id")
    pj = job.get("payload_json")
    if isinstance(pj, str) and pj:
        try:
            loaded = json.loads(pj)
            return loaded.get("lane_id") if isinstance(loaded, dict) else None
        except json.JSONDecodeError:
            return None
    return None


def _defer(reason: str, detail: dict[str, Any]) -> Any:
    from fieldkit.budget import DEFER, BudgetDecision

    return BudgetDecision(DEFER, reason, detail)


@dataclass
class LaneArbiter:
    """The envelope-gated single serving slot around one GPU job (LA-1/2/6).

    A context manager the GPU-kind runner enters. ``__enter__`` runs the 3-way
    pre-flight (governor *allow* ∧ envelope *fits* ∧ lane binary present) — any
    failure raises :class:`LaneDeferred` *before* anything is torn down — then
    frees the resident chat brain (``stop_resident``) and starts the
    :class:`MemoryWatchdog`. ``__exit__`` stops the watchdog, tears down the vLLM
    lane (EngineCore-aware), and **always** restores the prior lane in a finally
    (R1: never leave the box with no serving lane). One arbiter, one slot
    (invariant #2); it composes *inside* the M11 ``DrainLock``, never replaces it
    (LA-2). It drives the shipped lane lifecycle — it does not re-implement serving.
    """

    envelope: Any
    cfg: Any
    job: Mapping[str, Any] = field(default_factory=dict)
    governor: Optional[Any] = None
    mem: Optional[MemTrace] = None
    sentinel: Optional[Any] = None
    stop_resident: Optional[Callable[[], None]] = None
    restore_resident: Optional[Callable[[], None]] = None
    lane_factory: Optional[Callable[[Any], Any]] = None
    bin_check: Optional[Callable[[Any], bool]] = None
    watchdog: Optional[MemoryWatchdog] = None
    floor_gb: float = 4.0
    warn_gb: float = 8.0
    _lane: Any = field(default=None, init=False, repr=False)
    _resident_stopped: bool = field(default=False, init=False, repr=False)

    def preflight(self) -> Optional[Any]:
        """The 3-way gate (LA-6) → a deferring :class:`~fieldkit.budget.
        BudgetDecision`, or None when the lane may spawn."""
        if self.governor is not None:
            decision = self.governor.check_budget(dict(self.job))
            if not getattr(decision, "allowed", False):
                return decision
        lane_id = _job_lane_id(self.job)
        if not self.envelope.fits(lane_id):
            from fieldkit.budget import EscalationReason

            return _defer(
                EscalationReason.OOM_ENVELOPE,
                {
                    "lane_id": lane_id,
                    "lane_gb": self.envelope.lane_footprint(lane_id),
                    "reserved_gb": getattr(self.envelope, "reserved_gb", None),
                    "total_gb": getattr(self.envelope, "total_gb", None),
                },
            )
        check = self.bin_check or lane_binary_present
        if not check(self.cfg):
            from fieldkit.budget import EscalationReason

            return _defer(
                EscalationReason.LANE_BIN_ABSENT,
                {
                    "lane_id": lane_id,
                    "hint": "set FK_RL_VLLM_BIN / FK_RL_SERVE_CMD or install vLLM",
                },
            )
        return None

    def __enter__(self) -> "LaneArbiter":
        decision = self.preflight()
        if decision is not None:
            raise LaneDeferred(decision)
        if self.mem is not None and self.mem.headroom_at_spawn_gb is None:
            self.mem.headroom_at_spawn_gb = headroom_gb(self.mem.total_gb)
        if self.stop_resident is not None:
            self.stop_resident()
            self._resident_stopped = True
        factory = self.lane_factory or _default_lane
        self._lane = factory(self.cfg)
        if self.watchdog is None and self.sentinel is not None:
            self.watchdog = MemoryWatchdog(
                sentinel=Path(self.sentinel),
                floor_gb=self.floor_gb,
                warn_gb=self.warn_gb,
                trace=self.mem,
            )
        if self.watchdog is not None:
            self.watchdog.watch()
        return self

    def __exit__(self, *exc: Any) -> None:
        # Returns None (never True) → the run's own exception always propagates;
        # the arbiter cleans up but never *suppresses*.
        if self.watchdog is not None:
            try:
                self.watchdog.stop()
            except Exception:  # noqa: BLE001
                pass
        try:
            if self._lane is not None:
                self._lane.stop()
        except Exception:  # noqa: BLE001
            pass
        if self._resident_stopped and self.restore_resident is not None:
            try:
                self.restore_resident()
            except Exception:  # noqa: BLE001
                pass


# ---------------------------------------------------------------------------
# RLLaneContext — the one optional object dispatch consults for an rl_run (LA-1..11)
# ---------------------------------------------------------------------------


def _shell_runner(cmd: str) -> Callable[[], None]:
    def _run() -> None:
        subprocess.run(cmd, shell=True, check=False)  # operator-controlled

    return _run


@dataclass
class RLLaneContext:
    """The per-drain RL-lane wiring the dispatcher consults for `rl_run` (LA-1..11).

    One optional object on :func:`fieldkit.arena.jobs.dispatch_job` /
    :func:`~fieldkit.arena.jobs.drain_jobs`: when present it arbiters the
    `rl_run` (pre-flight → resident-brain teardown → watchdog → live progress →
    mem-trace); when **absent** (the M8 default) `rl_run` runs bare, byte-for-byte
    M8/RV-6 behavior. Resident-brain teardown/restore default to the
    ``FK_RL_RESIDENT_STOP_CMD`` / ``FK_RL_RESIDENT_START_CMD`` shell commands the
    operator sets; the watchdog thresholds default to ``FK_RL_OOM_FLOOR_GB`` /
    ``FK_RL_OOM_WARN_GB``. Nothing here touches the GPU until a real run drains.
    """

    envelope: Any = None
    cfg: Any = None
    governor: Optional[Any] = None
    stop_resident: Optional[Callable[[], None]] = None
    restore_resident: Optional[Callable[[], None]] = None
    sentinel_dir: str = "~/.fieldkit/arena/rl"
    throttle_s: float = 30.0
    floor_gb: float = 4.0
    warn_gb: float = 8.0
    lane_factory: Optional[Callable[[Any], Any]] = None
    bin_check: Optional[Callable[[Any], bool]] = None

    def __post_init__(self) -> None:
        if self.envelope is None:
            from fieldkit.budget import MemoryEnvelope

            self.envelope = MemoryEnvelope()
        self.floor_gb = float(os.environ.get("FK_RL_OOM_FLOOR_GB", self.floor_gb))
        self.warn_gb = float(os.environ.get("FK_RL_OOM_WARN_GB", self.warn_gb))
        if self.stop_resident is None and os.environ.get("FK_RL_RESIDENT_STOP_CMD"):
            self.stop_resident = _shell_runner(os.environ["FK_RL_RESIDENT_STOP_CMD"])
        if self.restore_resident is None and os.environ.get("FK_RL_RESIDENT_START_CMD"):
            self.restore_resident = _shell_runner(os.environ["FK_RL_RESIDENT_START_CMD"])

    def config(self) -> Any:
        """The :class:`fieldkit._rl_gpu_serve.RLBackendConfig` for teardown/bin-check.

        Resolved once from the ``FK_RL_*`` env (the operator tunes the box). The
        arbiter only needs its ``stop_cmd`` + ``serve_cmd_override`` — the seams
        own the actual serving — so a default base is fine.
        """
        if self.cfg is not None:
            return self.cfg
        from fieldkit._rl_gpu_serve import RLBackendConfig
        from fieldkit.rl import GRPOConfig

        self.cfg = RLBackendConfig.from_env(GRPOConfig(base="rl-lane"))
        return self.cfg

    def sentinel_for(self, job_id: str) -> Path:
        return Path(os.path.expanduser(self.sentinel_dir)) / f"abort-{job_id}.json"

    def preflight(self, job: Mapping[str, Any]) -> Optional[Any]:
        """The 3-way gate for ``job`` (LA-6) → a deferring decision, or None.

        Used by :func:`fieldkit.arena.jobs.drain_jobs` as a **brake**: a deferred
        ``rl_run`` is released back to ``queued`` + audited and the pass stops
        (the governor-brake pattern), so a missing vLLM binary can't spin the
        drain re-claiming the same job. Builds a throwaway arbiter purely to
        reuse :meth:`LaneArbiter.preflight` — no lane is spawned.
        """
        return LaneArbiter(
            envelope=self.envelope,
            cfg=self.config(),
            job=job,
            governor=self.governor,
            bin_check=self.bin_check,
        ).preflight()

    def arbiter_for(
        self, job: Mapping[str, Any], mem: MemTrace, sentinel: Path
    ) -> LaneArbiter:
        return LaneArbiter(
            envelope=self.envelope,
            cfg=self.config(),
            job=job,
            governor=self.governor,
            mem=mem,
            sentinel=sentinel,
            stop_resident=self.stop_resident,
            restore_resident=self.restore_resident,
            lane_factory=self.lane_factory,
            bin_check=self.bin_check,
            floor_gb=self.floor_gb,
            warn_gb=self.warn_gb,
        )
