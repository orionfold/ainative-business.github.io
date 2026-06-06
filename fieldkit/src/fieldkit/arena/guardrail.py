"""``fieldkit.arena.guardrail`` — AE-17 cloud-run eval guardrails (arena-enhancements S7).

Bounded, configurable, **tracked** guardrails on *metered cloud* eval lanes — the
fix for the baseline OpenRouter eval that hung ~2.5 h holding the lane and accruing
uncapped spend (2026-06-05). Three trip conditions, all writing a shared
**eval-abort sentinel** the :func:`fieldkit.eval.VerticalBench.run` row-loop polls
between rows (mirroring the RL ``abort_poller`` / sentinel pattern in
:mod:`fieldkit.arena.lane`):

* **G1 — teardown.** The cockpit ``_lifespan`` shutdown (and an explicit
  ``arena down``) touch the sentinel, so an in-flight cloud eval aborts cleanly
  instead of only dying with the process. Always-on for a cloud run.
* **G2 — stall.** A **no-progress** watchdog: trips when no row has completed
  within ``FK_EVAL_STALL_TIMEOUT_S`` (default **600 s / 10 min**), reset on every
  completed row (never a wall-clock total — AE-R6 false-trip guard), backstopped
  by the existing 120 s per-request httpx timeout.
* **G3 — cost.** Captures per-row ``usage`` tokens → accumulates via
  :meth:`fieldkit.cost.PriceSnapshot.cost_usd` → trips when the **per-run** total
  exceeds ``FK_EVAL_RUN_COST_CAP_USD`` (default **$5**) — the per-run sibling of
  the governor's per-day cap. Inert when no price snapshot resolves for the model
  (tokens still tracked; G1 + G2 stay live).

Scoped to metered cloud lanes (a non-loopback ``base_url``); a local
``127.0.0.1`` / ``172.17.0.1`` llama-server lane runs byte-for-byte unchanged —
the arena dispatcher simply never arms a guardrail for it. **No arena.db schema
change** — a sentinel file + ``result_json`` fields + env config (AH-9 / RV-8).

Stdlib-cheap by construction (no torch / no vLLM / no LLM call), like
:mod:`fieldkit.arena.lane`.
"""

from __future__ import annotations

import ipaddress
import json
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, Optional
from urllib.parse import urlparse

__all__ = [
    "DEFAULT_STALL_TIMEOUT_S",
    "DEFAULT_RUN_COST_CAP_USD",
    "EVAL_SENTINEL_DIR",
    "EvalGuardrail",
    "eval_sentinel_dir",
    "eval_sentinel_for",
    "is_cloud_endpoint",
]

#: No-progress stall window (G2). Reset on every completed row, NOT a wall-clock
#: total — a legitimately-slow-but-progressing run never trips (AE-R6).
DEFAULT_STALL_TIMEOUT_S = 600.0

#: Per-run USD cost cap (G3) — the per-run sibling of the governor's per-day cap.
DEFAULT_RUN_COST_CAP_USD = 5.0

#: Dir for the per-job eval-abort sentinels (mirrors the RL ``sentinel_dir``).
EVAL_SENTINEL_DIR = "~/.fieldkit/arena/eval"


def _utc_now_iso() -> str:
    """ISO-8601 UTC stamp, matching the dispatcher + lane convention."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def eval_sentinel_dir() -> Path:
    """The dir holding per-job eval-abort sentinels (env-overridable)."""
    return Path(os.path.expanduser(os.environ.get("FK_EVAL_SENTINEL_DIR", EVAL_SENTINEL_DIR)))


def eval_sentinel_for(job_id: str) -> Path:
    """The deterministic abort-sentinel path for an eval ``job_id``.

    Deterministic from ``job_id`` so the cockpit ``_lifespan`` can compute it for
    a running job to trip G1 without sharing memory with the dispatch task — the
    same trick the RL lane uses (``RLLaneContext.sentinel_for``).
    """
    return eval_sentinel_dir() / f"abort-{job_id}.json"


def is_cloud_endpoint(base_url: Optional[str]) -> bool:
    """True iff ``base_url`` is a **metered cloud** lane (non-loopback host).

    A local Spark lane — ``127.0.0.1`` / ``localhost`` / the docker bridge
    ``172.17.0.1`` / any RFC-1918 or link-local host — is free and fast, so it
    runs unguarded. A public DNS name or public IP (OpenRouter today) is metered
    → guardable. A blank/unparseable URL is treated as local (fail-safe: never
    arm a guardrail we can't reason about).
    """
    if not base_url:
        return False
    host = (urlparse(base_url).hostname or "").strip().lower()
    if not host:
        return False
    if host in {"localhost", "localhost.localdomain"}:
        return False
    if host.endswith(".local") or host.endswith(".localhost"):
        return False
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        # A DNS hostname (e.g. openrouter.ai) — metered cloud.
        return True
    return not (ip.is_loopback or ip.is_private or ip.is_link_local)


@dataclass
class EvalGuardrail:
    """A stall + cost + teardown watchdog around one metered cloud eval run.

    Duck-typed against the row-loop hooks ``VerticalBench.run`` accepts —
    :meth:`should_abort` (polled between rows), :meth:`record_progress` (G2 reset,
    per completed row) — plus :meth:`record_usage` (G3, per response, wired into
    the OpenAI-compat client's ``on_usage`` callback). The harness
    (``run_vertical_eval``) holds no reference to this class; it just calls the
    bound methods and reads :meth:`result_fields` back, so no harness→arena import.

    ``price`` is the resolved :class:`fieldkit.cost.PriceSnapshot` for the lane's
    model (``None`` → cost tracking is best-effort: tokens accumulate, no $ cap).
    ``clock`` is injectable for deterministic stall tests.
    """

    sentinel: Path
    stall_timeout_s: float = DEFAULT_STALL_TIMEOUT_S
    cost_cap_usd: float = DEFAULT_RUN_COST_CAP_USD
    price: Optional[Any] = None
    clock: Callable[[], float] = time.monotonic

    tokens_in: int = field(default=0, init=False)
    tokens_out: int = field(default=0, init=False)
    run_cost_usd: float = field(default=0.0, init=False)
    n_scored: int = field(default=0, init=False)
    aborted_by: Optional[str] = field(default=None, init=False)
    _last_progress: float = field(default=0.0, init=False)

    def __post_init__(self) -> None:
        self.sentinel = Path(self.sentinel)
        self._last_progress = self.clock()

    @classmethod
    def from_env(
        cls,
        sentinel: Any,
        *,
        price: Optional[Any] = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> "EvalGuardrail":
        """Build a guardrail with thresholds read from the env (AF-9/AF-10 convention).

        ``FK_EVAL_STALL_TIMEOUT_S`` (default 600 s) and ``FK_EVAL_RUN_COST_CAP_USD``
        (default $5). A non-numeric override falls back to the default rather than
        crashing a run.
        """
        return cls(
            sentinel=Path(sentinel),
            stall_timeout_s=_env_float("FK_EVAL_STALL_TIMEOUT_S", DEFAULT_STALL_TIMEOUT_S),
            cost_cap_usd=_env_float("FK_EVAL_RUN_COST_CAP_USD", DEFAULT_RUN_COST_CAP_USD),
            price=price,
            clock=clock,
        )

    # -- G3 cost ------------------------------------------------------------
    def record_usage(self, usage: Optional[Mapping[str, Any]]) -> None:
        """Accumulate one response's ``usage`` and trip G3 if over the cap.

        ``usage`` is the OpenAI-compat ``{prompt_tokens, completion_tokens, …}``
        block (or ``None``/empty when the server omits it). The $ total only
        moves when a ``price`` snapshot is present; the cap trips on *accrued*
        cost from real usage (never a pre-estimate — AE-R6).
        """
        if not usage:
            return
        self.tokens_in += _as_int(usage.get("prompt_tokens"))
        self.tokens_out += _as_int(usage.get("completion_tokens"))
        if self.price is not None:
            self.run_cost_usd = round(
                self.price.cost_usd(tokens_in=self.tokens_in, tokens_out=self.tokens_out), 6
            )
            if self.cost_cap_usd and self.run_cost_usd > self.cost_cap_usd:
                self._trip("cost_cap")

    # -- G2 stall reset -----------------------------------------------------
    def record_progress(self) -> None:
        """Mark one completed row — counts it + resets the no-progress timer."""
        self.n_scored += 1
        self._last_progress = self.clock()

    # -- the row-loop poll (G1 teardown + G2 stall) -------------------------
    def should_abort(self) -> bool:
        """Polled between rows by ``VerticalBench.run`` — True ⇒ stop cleanly.

        Precedence: a prior in-process trip (cost/stall) wins; otherwise an
        externally-touched sentinel is G1 teardown; otherwise the stall window.
        """
        if self.aborted_by is not None:
            return True
        if self.sentinel.exists():
            self.aborted_by = "teardown"
            return True
        if self.stall_timeout_s and (self.clock() - self._last_progress) > self.stall_timeout_s:
            self._trip("stall_timeout")
            return True
        return False

    def _trip(self, reason: str) -> None:
        self.aborted_by = reason
        try:
            self.sentinel.parent.mkdir(parents=True, exist_ok=True)
            self.sentinel.write_text(
                json.dumps(
                    {
                        "aborted_by": reason,
                        "run_cost_usd": self.run_cost_usd,
                        "n_scored": self.n_scored,
                        "tripped_at": _utc_now_iso(),
                    },
                    sort_keys=True,
                )
            )
        except OSError:
            pass

    def result_fields(self) -> dict[str, Any]:
        """The ``result_json`` block — what the run cost + whether/why it aborted.

        Threaded into ``jobs.result_json`` by ``_persist_eval_rerun`` and rendered
        on the Jobs card (composes with AE-16 identity + AE-2 abort visibility +
        the AE-13 cost chip).
        """
        return {
            "aborted_by": self.aborted_by,
            "partial": self.aborted_by is not None,
            "run_cost_usd": self.run_cost_usd,
            "tokens_in": self.tokens_in,
            "tokens_out": self.tokens_out,
            "n_scored": self.n_scored,
            "stall_timeout_s": self.stall_timeout_s,
            "cost_cap_usd": self.cost_cap_usd,
            "priced": self.price is not None,
        }


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        return float(raw)
    except (TypeError, ValueError):
        return default


def _as_int(v: Any) -> int:
    try:
        return int(v or 0)
    except (TypeError, ValueError):
        return 0
