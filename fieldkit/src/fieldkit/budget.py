# Copyright 2026 Manav Sehgal
# SPDX-License-Identifier: Apache-2.0
"""`fieldkit.budget` — the Arena **M11 budget governor** (Phase 2 of the MTBM roadmap).

Phase 2 of the "machine that builds machines" roadmap
(`_FLOWS/the-machine-that-builds-machines.md` §3, Bet 2) — the **brake** the
autonomous harness consults *before* it launches a job. Where M9's
`fieldkit.cost` is the **meter** (per-run ledger + the public `$/quality-point`),
this module is the **governor** (decision M9-9 / AH-4): one pre-launch check that
generalizes the two guards that already exist informally — the corpus-synth
weekly-`/usage` ceiling and the OOM-envelope check — into a single
:class:`BudgetGovernor.check_budget` call returning *allow / escalate / defer*.

Three escalation paths (`_SPECS/spark-arena-v1.md` §15.3):

- **escalate** — the **`LOCAL_CEILING = 33%`** *failure-mode-driven* contract
  (AH-4): escalate to a frontier lane when the local model *gives up* — a
  multi-step-planning / KV-cache-derivation failure class that hits the
  30B-A3B-class boundary — **not** on a token ceiling alone. Grounded in
  H6 (`hermes-cost-routing-local-and-openrouter`: local-only 8/12, frontier 12/12
  ⇒ a third of the workload genuinely needs frontier).
- **defer** — over the daily $ cap (M9 present), over the weekly `/usage` cap
  (M9 absent), or no memory envelope for the lane (the 2026-04-22 OOM landmine,
  `[[project_spark_unified_memory_oom]]`).
- **allow** — within budget and the lane fits the resident envelope.

**M9 is a *soft* prerequisite (AH-5).** When :class:`~fieldkit.cost.CostLedger`
is wired the governor reads the persisted ledger for `$/task` + the 33% ceiling;
when absent it degrades to a **token + OOM-envelope guard** (the two checks that
already exist). M11 ships independent of M9's build slot; M9 *upgrades* the
governor when it lands.

Per `feedback_llm_skill_pattern`: deterministic Python only — no ``anthropic``
import, no ``claude_agent_sdk`` import, no LLM call. Store-agnostic by
duck-typing (a :class:`~fieldkit.cost.CostLedger`, an ``ArenaStore``, or a raw
``sqlite3.Connection``), so this module never imports ``fieldkit.arena`` — the
scheduler injects it into the drain loop, never the other way round.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from typing import Any, Mapping, Optional, Sequence

__all__ = [
    "BudgetGovernor",
    "BudgetDecision",
    "SpendDigest",
    "EscalationReason",
    "MemoryEnvelope",
    "check_budget",
    "BudgetError",
]


class BudgetError(Exception):
    """Raised when a governor configuration or spend read cannot complete."""


# ---------------------------------------------------------------------------
# Decision vocabulary
# ---------------------------------------------------------------------------

#: The three drain-loop actions a :class:`BudgetDecision` carries (the scheduler
#: branches on these — see `_SPECS/spark-arena-v1.md` §15.3 scheduler flow).
ALLOW = "allow"
ESCALATE = "escalate"
DEFER = "defer"


class EscalationReason:
    """Why the governor returned its verdict — the standup's audit string.

    ``LOCAL_CEILING`` is the only *escalate* reason; the rest are *defer*
    reasons (over a cap or no envelope). ``WITHIN_BUDGET`` rides an *allow*.
    """

    WITHIN_BUDGET = "within_budget"
    LOCAL_CEILING = "local_ceiling"  # escalate — local gave up (AH-4, 33%)
    OVER_DAILY_CAP = "over_daily_cap"  # defer — M9 present, $ cap hit
    OVER_USAGE_CAP = "over_usage_cap"  # defer — M9 absent, weekly /usage cap
    OOM_ENVELOPE = "oom_envelope"  # defer — lane won't fit the resident envelope


#: ``failure_class`` values that mean *the local model gave up* → escalate to a
#: frontier lane (AH-4). These are the 30B-A3B-class boundary failure modes from
#: the H6 grounding — multi-step planning the MoE can't hold, a KV-cache
#: derivation it botches, a context overflow, or an explicit low-confidence
#: signal. A job that fails any *other* way (a transient crash, a bench gap) is
#: NOT escalated — it is a local problem to fix, not a frontier spend.
LOCAL_CEILING_TRIGGERS: frozenset[str] = frozenset(
    {
        "multi_step_planning",
        "kv_cache_derivation",
        "context_overflow",
        "local_low_confidence",
    }
)

#: The failure-mode escalation ceiling (AH-4). 0.33 — H6 measured ~a third of the
#: workload (`hermes-cost-routing-local-and-openrouter`) genuinely needs frontier.
#: Carried on the decision detail so the standup can render "escalated (33% ceiling)".
LOCAL_CEILING = 0.33


@dataclass(frozen=True)
class BudgetDecision:
    """The governor's verdict on one job — *allow / escalate / defer* + why.

    ``action`` is one of :data:`ALLOW` / :data:`ESCALATE` / :data:`DEFER`;
    ``reason`` an :class:`EscalationReason` value; ``detail`` carries the numbers
    the standup renders (the projected spend, the cap, the ceiling, the lane
    footprint). The scheduler reads :attr:`allowed` to gate dispatch.
    """

    action: str
    reason: str
    detail: dict[str, Any] = field(default_factory=dict)

    @property
    def allowed(self) -> bool:
        """True only for an outright *allow* — escalate/defer both hold dispatch."""
        return self.action == ALLOW


# ---------------------------------------------------------------------------
# Memory envelope — the OOM guard (one lane at a time, 128 GB unified)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class MemoryEnvelope:
    """The GB10 unified-memory envelope the single-lane drain runs inside.

    Defaults to the Spark-measured numbers (`hermes-vertical-router-on-spark`):
    128 GB shared CPU+GPU, the **resident brain** (Qwen3-30B-A3B Q4_K_M) holding
    ~31.8 GB, one cold vertical ~5.5 GB ⇒ ~50 GB peak with ~78 GB headroom — so
    AH-1's "one lane at a time" has comfortable margin. :meth:`fits` is the OOM
    guard the governor calls (the 2026-04-22 box-hang landmine,
    `[[project_spark_unified_memory_oom]]`): a job whose lane would push past the
    total is deferred, never stacked on top of the resident brain.
    """

    total_gb: float = 128.0
    reserved_gb: float = 31.8  # the resident brain lane (AH-1)
    default_lane_gb: float = 5.5  # one cold vertical (the H-router measurement)
    lane_gb: Mapping[str, float] = field(default_factory=dict)

    def headroom_gb(self) -> float:
        """GB available above the resident brain for one cold lane."""
        return self.total_gb - self.reserved_gb

    def lane_footprint(self, lane_id: Optional[str]) -> float:
        """The lane's resident footprint — a per-lane override, else the default."""
        if lane_id is None:
            return 0.0
        return float(self.lane_gb.get(lane_id, self.default_lane_gb))

    def fits(self, lane_id: Optional[str]) -> bool:
        """True if loading ``lane_id`` alongside the reserved brain stays in budget.

        A ``None`` lane (a job that touches no model — a pure index diff) always
        fits. Otherwise the lane's footprint plus the reserved brain must clear
        the total. Single-lane (M8-5): only one cold lane is ever co-resident.
        """
        if lane_id is None:
            return True
        return self.reserved_gb + self.lane_footprint(lane_id) <= self.total_gb


# ---------------------------------------------------------------------------
# Spend digest — today's $ by lane vs cap (the standup's Spend row, AH-3)
# ---------------------------------------------------------------------------


def _has_cost_plane(conn: sqlite3.Connection) -> bool:
    """True when M9's ``cost_usd`` column exists on ``compare_responses``.

    The soft-prerequisite probe (AH-5): a pre-M9 db has no cost column, so the
    digest renders "—" and the governor degrades to the token+envelope guard.
    """
    try:
        conn.execute("SELECT cost_usd FROM compare_responses LIMIT 1").fetchone()
        return True
    except sqlite3.OperationalError:
        return False


@dataclass(frozen=True)
class SpendDigest:
    """Today's spend rolled up for the morning standup (AH-3 Spend row).

    ``total_usd`` is the restart-surviving session spend (M9-8 semantics);
    ``by_lane`` the per-lane breakdown off the private ``compare_responses``
    rows; ``cap_usd`` the configured daily ceiling (``None`` = uncapped).
    ``has_cost_plane`` is False on a pre-M9 db — then everything renders "—"
    (AH-5 degradation). The aggregate is operator-private: it is assembled from
    the FORBIDDEN ``compare_responses``/``chat_turns`` tables and rendered only
    on the live `/api/standup`, never the public mirror.
    """

    total_usd: Optional[float]
    by_lane: tuple[tuple[str, float], ...]
    cap_usd: Optional[float]
    n_paid_runs: int
    has_cost_plane: bool

    @property
    def over_cap(self) -> bool:
        """True when the session spend has crossed the configured daily cap."""
        return (
            self.cap_usd is not None
            and self.total_usd is not None
            and self.total_usd > self.cap_usd
        )

    @property
    def display(self) -> str:
        """The Spend-row string: "—" pre-M9, "$X.XXXX / $cap" (or uncapped)."""
        if not self.has_cost_plane or self.total_usd is None:
            return "—"
        if self.cap_usd is None:
            return f"${self.total_usd:.4f}"
        return f"${self.total_usd:.4f} / ${self.cap_usd:.2f}"

    def as_dict(self) -> dict[str, Any]:
        """JSON-able snapshot for the `/api/standup` payload + the standup render."""
        return {
            "total_usd": self.total_usd,
            "by_lane": [{"lane_id": lane, "cost_usd": cost} for lane, cost in self.by_lane],
            "cap_usd": self.cap_usd,
            "n_paid_runs": self.n_paid_runs,
            "has_cost_plane": self.has_cost_plane,
            "over_cap": self.over_cap,
            "display": self.display,
        }

    @classmethod
    def from_store(
        cls, store_or_conn: Any, *, cap_usd: Optional[float] = None
    ) -> "SpendDigest":
        """Roll up spend from the private cost rows (M9 present) or "—" (absent)."""
        conn = _as_conn(store_or_conn)
        if not _has_cost_plane(conn):
            return cls(
                total_usd=None,
                by_lane=(),
                cap_usd=cap_usd,
                n_paid_runs=0,
                has_cost_plane=False,
            )
        # Total + paid-run count via the M9 ledger (restart-surviving, M9-8).
        from fieldkit.cost import CostLedger  # lazy — M9 is a soft prereq (AH-5)

        total, n_paid = CostLedger(conn).session_spend()
        by_lane: list[tuple[str, float]] = []
        for row in conn.execute(
            "SELECT lane_id, COALESCE(SUM(cost_usd), 0.0) AS c "
            "FROM compare_responses GROUP BY lane_id "
            "HAVING c > 0 ORDER BY c DESC"
        ):
            by_lane.append((str(row[0]), round(float(row[1]), 6)))
        return cls(
            total_usd=total,
            by_lane=tuple(by_lane),
            cap_usd=cap_usd,
            n_paid_runs=n_paid,
            has_cost_plane=True,
        )


# ---------------------------------------------------------------------------
# The governor
# ---------------------------------------------------------------------------


def _as_conn(store_or_conn: Any) -> sqlite3.Connection:
    """Resolve an ``ArenaStore`` (``.connect()``) or a raw connection.

    Mirrors :func:`fieldkit.cost._as_conn` so this module stays free of any
    ``fieldkit.arena`` import (the scheduler injects the governor downward).
    """
    if hasattr(store_or_conn, "connect"):
        return store_or_conn.connect()
    if isinstance(store_or_conn, sqlite3.Connection):
        return store_or_conn
    raise BudgetError(
        "expected an ArenaStore (with .connect()), a sqlite3.Connection, or a "
        f"CostLedger; got {type(store_or_conn).__name__}"
    )


def _job_payload(job: Mapping[str, Any]) -> dict[str, Any]:
    """Extract a job's payload dict from a ``jobs`` row or a plain mapping.

    A claimed ``jobs`` row carries ``payload_json`` (a string); a synthetic
    test job may carry a ``payload`` mapping directly. Returns ``{}`` for a job
    with neither (a bare kind).
    """
    raw = job.get("payload")
    if isinstance(raw, Mapping):
        return dict(raw)
    pj = job.get("payload_json")
    if isinstance(pj, str) and pj:
        try:
            loaded = json.loads(pj)
            return dict(loaded) if isinstance(loaded, dict) else {}
        except json.JSONDecodeError:
            return {}
    return {}


@dataclass
class BudgetGovernor:
    """The pre-launch check the autonomous drain consults before each job (AH-4).

    Construct with a :class:`~fieldkit.cost.CostLedger` (or an ``ArenaStore`` /
    connection it can build one from) to enable the M9 `$/task` + 33%-ceiling
    branch; leave ``ledger=None`` to run the M9-absent token+envelope guard
    (AH-5). The :class:`MemoryEnvelope` OOM guard always applies.

    The governor is **stateless per call**: it reads spend at decision time
    (or takes an injected ``spend_today`` for a deterministic test), returns a
    :class:`BudgetDecision`, and never mutates the store. The scheduler owns the
    side effects (re-queue, audit row, dispatch).
    """

    ledger: Optional[Any] = None  # CostLedger | ArenaStore | Connection | None
    envelope: MemoryEnvelope = field(default_factory=MemoryEnvelope)
    daily_cap_usd: float = 5.0
    weekly_usage_cap_pct: float = 80.0
    local_ceiling: float = LOCAL_CEILING

    def _session_spend(self) -> Optional[float]:
        """Read total session spend from the ledger, or ``None`` when M9 absent."""
        if self.ledger is None:
            return None
        from fieldkit.cost import CostLedger

        ledger = self.ledger
        if not isinstance(ledger, CostLedger):
            ledger = CostLedger(ledger)
        try:
            total, _ = ledger.session_spend()
        except BudgetError:
            return None
        return total

    def check_budget(
        self,
        job: Mapping[str, Any],
        *,
        spend_today: Optional[float] = None,
        weekly_usage_pct: Optional[float] = None,
    ) -> BudgetDecision:
        """Decide *allow / escalate / defer* for one job (the §15.3 contract).

        Order matches the spec pseudo-code: the M9 branch (daily $ cap → defer;
        local-ceiling failure class → escalate) when a ledger is wired, else the
        M9-absent weekly-`/usage` cap → defer; then the OOM envelope guard → defer
        for either branch; else *allow*. ``spend_today`` / ``weekly_usage_pct``
        override the read inputs for a deterministic test.
        """
        payload = _job_payload(job)
        lane = payload.get("lane_id")
        est_cost = float(payload.get("est_cost_usd", 0.0) or 0.0)
        failure_class = job.get("failure_class") or payload.get("failure_class")

        if self.ledger is not None:
            spent = spend_today if spend_today is not None else self._session_spend()
            spent = float(spent or 0.0)
            projected = round(spent + est_cost, 6)
            if projected > self.daily_cap_usd:
                return BudgetDecision(
                    DEFER,
                    EscalationReason.OVER_DAILY_CAP,
                    {
                        "spend_usd": spent,
                        "est_cost_usd": est_cost,
                        "projected_usd": projected,
                        "cap_usd": self.daily_cap_usd,
                    },
                )
            if failure_class in LOCAL_CEILING_TRIGGERS:
                return BudgetDecision(
                    ESCALATE,
                    EscalationReason.LOCAL_CEILING,
                    {
                        "failure_class": failure_class,
                        "ceiling": self.local_ceiling,
                        "lane_id": lane,
                    },
                )
        else:
            usage = float(weekly_usage_pct or 0.0)
            if usage > self.weekly_usage_cap_pct:
                return BudgetDecision(
                    DEFER,
                    EscalationReason.OVER_USAGE_CAP,
                    {
                        "weekly_usage_pct": usage,
                        "cap_pct": self.weekly_usage_cap_pct,
                    },
                )

        if not self.envelope.fits(lane):
            return BudgetDecision(
                DEFER,
                EscalationReason.OOM_ENVELOPE,
                {
                    "lane_id": lane,
                    "lane_gb": self.envelope.lane_footprint(lane),
                    "reserved_gb": self.envelope.reserved_gb,
                    "total_gb": self.envelope.total_gb,
                },
            )

        return BudgetDecision(ALLOW, EscalationReason.WITHIN_BUDGET, {"lane_id": lane})

    def spend_digest(self, *, cap_usd: Optional[float] = None) -> SpendDigest:
        """The standup Spend row off this governor's ledger (AH-3).

        Uses the configured ``daily_cap_usd`` as the cap when ``cap_usd`` is not
        given. Returns the "—" digest when the governor has no ledger (M9 absent).
        """
        if self.ledger is None:
            return SpendDigest(None, (), cap_usd or self.daily_cap_usd, 0, False)
        return SpendDigest.from_store(
            self.ledger, cap_usd=cap_usd if cap_usd is not None else self.daily_cap_usd
        )


def check_budget(
    job: Mapping[str, Any],
    *,
    ledger: Optional[Any] = None,
    envelope: Optional[MemoryEnvelope] = None,
    daily_cap_usd: float = 5.0,
    weekly_usage_cap_pct: float = 80.0,
    spend_today: Optional[float] = None,
    weekly_usage_pct: Optional[float] = None,
) -> BudgetDecision:
    """One-shot governor read — build a :class:`BudgetGovernor` and decide.

    The convenience entry point for a cron tick or a CLI check that doesn't hold
    a long-lived governor. All keyword args mirror :class:`BudgetGovernor`'s
    fields + :meth:`BudgetGovernor.check_budget`'s overrides.
    """
    governor = BudgetGovernor(
        ledger=ledger,
        envelope=envelope or MemoryEnvelope(),
        daily_cap_usd=daily_cap_usd,
        weekly_usage_cap_pct=weekly_usage_cap_pct,
    )
    return governor.check_budget(
        job, spend_today=spend_today, weekly_usage_pct=weekly_usage_pct
    )
