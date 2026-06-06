# Copyright 2026 Manav Sehgal
# SPDX-License-Identifier: Apache-2.0
"""`fieldkit.cost` — the Arena **M9 cost plane**: per-run ledger + price snapshot.

Bet 6 of the MTBM roadmap (`_FLOWS/the-machine-that-builds-machines.md` §3) —
"token economics as a first-class decision axis". M9 is **connective tissue**:
the Arena sidecar already *computes* an OpenRouter cost per run
(`fieldkit.arena.server._compare_cost_usd`) but discards it. This module is the
**ledger + read API** that persists + reads it back, plus the **price snapshot**
that pins prices reproducibly. It does NOT enforce a budget — the
`fieldkit.budget` governor (Phase 2 / Arena M11, `_SPECS/spark-arena-v1.md` §15)
*consumes* this ledger; M9 ships the meter, not the brake (decision M9-9).

Three surfaces:

- :class:`PriceSnapshot` + :func:`seed_price_snapshot` — the
  ``openrouter_price_snapshot`` table, seeded at store-init from the **baked H6
  evidence** (`articles/hermes-cost-routing-local-and-openrouter/evidence/
  openrouter_prices.json`). Each persisted cost row stamps the
  :data:`H6_SNAPSHOT_ID` it was priced against, so a comparison stays
  reproducible as live OpenRouter prices drift (decision M9-5, risk R19). The
  seed is **baked as a Python constant** (`H6_PRICE_SEED`) so a PyPI wheel can
  re-seed without shipping the article tree — the JSON is the canonical
  *source*, this constant its distributable mirror.
- :class:`CostLedger` — read over the persisted per-run rows
  (``compare_responses`` / ``chat_turns``). :meth:`CostLedger.session_spend`
  rehydrates the live spend rail across a sidecar restart (decision M9-8).
- :func:`cost_per_quality` — the public **$/quality-point** read off
  ``leaderboard_rows`` (``mean_cost_usd / mean_score``), with the local-lane
  ``$0 (local)`` rendering that avoids a divide-by-zero "—" (decision M9-4).

Per `feedback_llm_skill_pattern`: deterministic Python only. No ``anthropic``
import, no ``claude_agent_sdk`` import, no LLM call. The store dependency is
duck-typed (anything with ``.connect()`` → a ``sqlite3.Connection``) so this
module never imports ``fieldkit.arena`` (avoids the circular: the store seeds
*this* module at ``initialize()``).
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

__all__ = [
    "CostLedger",
    "PriceSnapshot",
    "seed_price_snapshot",
    "fetch_openrouter_prices",
    "refresh_prices",
    "cost_per_quality",
    "CostError",
]

#: The canonical H6 price-snapshot id. The seed rows carry it and every
#: persisted OpenRouter cost row stamps it (``price_snapshot_id``) so a
#: comparison stays reproducible as live prices drift (M9-5 / R19).
H6_SNAPSHOT_ID = "h6-baseline"

#: ``snapshot_at_utc`` from the H6 evidence ``openrouter_prices.json`` — the
#: instant the baked tier prices were captured (R19 surfaces this in the UI as
#: a "prices as of <date>" stamp).
H6_CAPTURED_AT = "2026-05-28T14:32:06.836115+00:00"

#: The baked H6 OpenRouter price seed — the two **priced** tiers from
#: ``articles/hermes-cost-routing-local-and-openrouter/evidence/
#: openrouter_prices.json`` (the ``simple`` tier is a local Spark lane at $0 and
#: needs no snapshot row — local runs persist ``cost_usd = 0`` with no
#: ``price_snapshot_id``). Per-million USD, matching the JSON verbatim.
H6_PRICE_SEED: tuple[dict[str, Any], ...] = (
    {
        "model_id": "openai/gpt-4o-mini",
        "price_per_m_input_usd": 0.15,
        "price_per_m_output_usd": 0.6,
    },
    {
        "model_id": "anthropic/claude-opus-4.1",
        "price_per_m_input_usd": 15.0,
        "price_per_m_output_usd": 75.0,
    },
)


class CostError(Exception):
    """Raised when a cost seed/lookup cannot complete (bad seed shape, etc.)."""


# ---------------------------------------------------------------------------
# Connection plumbing — duck-typed store or raw connection
# ---------------------------------------------------------------------------


def _as_conn(store_or_conn: Any) -> sqlite3.Connection:
    """Resolve an ``ArenaStore`` (has ``.connect()``) or a raw connection.

    Keeps this module import-free of ``fieldkit.arena`` (the store seeds this
    module at ``initialize()`` — importing it back would be circular).
    """
    if hasattr(store_or_conn, "connect"):
        return store_or_conn.connect()
    if isinstance(store_or_conn, sqlite3.Connection):
        return store_or_conn
    raise CostError(
        "expected an ArenaStore (with .connect()) or a sqlite3.Connection, "
        f"got {type(store_or_conn).__name__}"
    )


# ---------------------------------------------------------------------------
# Price snapshot
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PriceSnapshot:
    """One ``openrouter_price_snapshot`` row — a model's pinned per-million price.

    ``source`` is ``'h6_evidence'`` for the baked baseline (or ``'fallback'`` /
    an operator label for a re-seed). ``captured_at`` is the instant the prices
    were captured upstream (NOT the seed time) — it is what the cockpit renders
    as "prices as of <date>".
    """

    snapshot_id: str
    model_id: str
    price_per_m_input_usd: float
    price_per_m_output_usd: float
    source: str
    captured_at: str

    def cost_usd(
        self, *, tokens_in: int | None, tokens_out: int | None
    ) -> float:
        """USD for ``tokens_in`` × input price + ``tokens_out`` × output price."""
        tin = int(tokens_in or 0)
        tout = int(tokens_out or 0)
        return (tin / 1_000_000.0) * self.price_per_m_input_usd + (
            tout / 1_000_000.0
        ) * self.price_per_m_output_usd


def seed_price_snapshot(
    store_or_conn: Any,
    *,
    prices: Sequence[Mapping[str, Any]] | None = None,
    snapshot_id: str = H6_SNAPSHOT_ID,
    source: str = "h6_evidence",
    captured_at: str = H6_CAPTURED_AT,
) -> int:
    """Seed (idempotent) the ``openrouter_price_snapshot`` table and return the
    row count written.

    Defaults to the baked :data:`H6_PRICE_SEED`; pass ``prices`` (a sequence of
    ``{model_id, price_per_m_input_usd, price_per_m_output_usd}`` mappings) to
    re-seed from a fresh capture under a new ``snapshot_id`` (the R19 fallback —
    old rows keep their ``price_snapshot_id``, so prior comparisons stay
    reproducible). ``INSERT OR REPLACE`` on the ``(snapshot_id, model_id)``
    primary key makes a re-run a no-op for the same snapshot.
    """
    rows = list(prices) if prices is not None else list(H6_PRICE_SEED)
    conn = _as_conn(store_or_conn)
    written = 0
    for r in rows:
        try:
            model_id = str(r["model_id"])
            p_in = float(r["price_per_m_input_usd"])
            p_out = float(r["price_per_m_output_usd"])
        except (KeyError, TypeError, ValueError) as exc:
            raise CostError(f"bad price seed row {r!r}: {exc}") from exc
        conn.execute(
            "INSERT OR REPLACE INTO openrouter_price_snapshot "
            "(snapshot_id, model_id, price_per_m_input_usd, "
            " price_per_m_output_usd, source, captured_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (snapshot_id, model_id, p_in, p_out, source, captured_at),
        )
        written += 1
    conn.commit()
    return written


# ---------------------------------------------------------------------------
# Live price refresh (BUG-3 / AF-29 — the snapshot table gains a refresh path)
# ---------------------------------------------------------------------------


def fetch_openrouter_prices(
    model_ids: Sequence[str] | None = None,
    *,
    timeout: float = 10.0,
) -> list[dict[str, Any]]:
    """Read current per-million prices from the OpenRouter ``/models`` catalog.

    Returns ``{model_id, price_per_m_input_usd, price_per_m_output_usd}`` rows —
    the :func:`seed_price_snapshot` ``prices`` shape — for ``model_ids`` (or the
    whole catalog when ``None``). The endpoint is public (the ``OPENROUTER_API_KEY``
    header is attached when present, not required). Raises :class:`CostError` on
    a network / HTTP / shape failure so callers can decide how loud to be; a
    model absent from the catalog is simply omitted (the caller's unpriced
    handling stays honest).
    """
    import os

    try:
        import httpx
    except ImportError as exc:  # pragma: no cover — arena extra ships httpx
        raise CostError("fetch_openrouter_prices requires httpx (fieldkit[arena])") from exc

    key = os.environ.get("OPENROUTER_API_KEY")
    headers = {"Authorization": f"Bearer {key}"} if key else {}
    want = {str(m) for m in model_ids} if model_ids is not None else None
    try:
        resp = httpx.get(
            "https://openrouter.ai/api/v1/models", headers=headers, timeout=timeout
        )
        resp.raise_for_status()
        data = resp.json().get("data", [])
    except Exception as exc:  # noqa: BLE001 — surface as the module error
        raise CostError(f"OpenRouter price fetch failed: {exc}") from exc

    rows: list[dict[str, Any]] = []
    for m in data if isinstance(data, list) else []:
        mid = m.get("id")
        if not mid or (want is not None and mid not in want):
            continue
        pricing = m.get("pricing") or {}
        p_in = _per_m_usd(pricing.get("prompt"))
        p_out = _per_m_usd(pricing.get("completion"))
        if p_in is None or p_out is None:
            continue  # un-priceable entry (image/embedding/router) — omit
        rows.append(
            {
                "model_id": mid,
                "price_per_m_input_usd": p_in,
                "price_per_m_output_usd": p_out,
            }
        )
    return rows


def refresh_prices(
    store_or_conn: Any,
    model_ids: Sequence[str] | None = None,
    *,
    fetcher: Any = None,
    now_iso: str | None = None,
) -> list[dict[str, Any]]:
    """Capture current OpenRouter prices into the snapshot table (BUG-3 fix).

    The M9 snapshot previously had **no refresh path** — nothing ever populated
    prices for the lanes actually being evaled, so ``price_for()`` returned
    ``None`` for every current model and the G3 cost cap was silently inert
    (e2e smoke C1). This fetches live prices (via ``fetcher``, default
    :func:`fetch_openrouter_prices`) and seeds them under a dated snapshot id
    (``or-refresh-<UTC date>``) with ``source='openrouter-api'`` — prior
    snapshots keep their rows, and :meth:`CostLedger.price_for`'s newest-row
    default makes the refresh effective on the very next dispatch. Returns the
    rows written (the seed shape + ``snapshot_id``/``captured_at``).
    """
    from datetime import datetime, timezone

    fetch = fetcher or fetch_openrouter_prices
    rows = fetch(model_ids)
    if not rows:
        return []
    captured = now_iso or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    snapshot_id = f"or-refresh-{captured[:10]}"
    seed_price_snapshot(
        store_or_conn,
        prices=rows,
        snapshot_id=snapshot_id,
        source="openrouter-api",
        captured_at=captured,
    )
    return [{**r, "snapshot_id": snapshot_id, "captured_at": captured} for r in rows]


def _per_m_usd(token_price: Any) -> float | None:
    """OpenRouter quotes USD-per-token as a string; convert to USD-per-million."""
    try:
        return round(float(token_price) * 1_000_000, 4)
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# Per-run ledger
# ---------------------------------------------------------------------------


class CostLedger:
    """Read API over the persisted per-run cost rows in ``arena.db``.

    Per-run cost lives on ``compare_responses`` (per side) and ``chat_turns``
    (per turn) — both **operator-private** tables (absent from
    ``mirror.PUBLISHABLE_TABLES``), so the ledger is private by construction
    (M9-2). Construct with an ``ArenaStore`` or a raw ``sqlite3.Connection``.
    """

    def __init__(self, store_or_conn: Any) -> None:
        self._conn = _as_conn(store_or_conn)

    def session_spend(self) -> tuple[float, int]:
        """``(total_usd, n_paid_runs)`` summed across the persisted cost rows.

        Survives a sidecar restart — the M9-8 fix for the in-memory accumulator
        that reset to ``0.0`` on every boot. Tables missing their cost column
        (a pre-M9 db) contribute zero rather than raising.

        **AF-30 (e2e smoke C4):** also folds in **eval-job spend** — a metered
        cloud eval persists its accrued cost in
        ``jobs.result_json.guardrail.run_cost_usd`` (AE-17), which this read was
        blind to: the smoke's Standup SPEND showed $0.0023 while the session's
        real metered spend was ~$0.18, all in eval runs. The $5 autonomy cap
        governed the wrong number.
        """
        total = 0.0
        calls = 0
        for table in ("compare_responses", "chat_turns"):
            try:
                row = self._conn.execute(
                    f"SELECT COALESCE(SUM(cost_usd), 0.0), "
                    f"       COUNT(CASE WHEN cost_usd > 0 THEN 1 END) "
                    f"FROM {table}"
                ).fetchone()
            except sqlite3.OperationalError:
                continue  # pre-M9 schema — column absent
            if row is not None:
                total += float(row[0] or 0.0)
                calls += int(row[1] or 0)
        for cost, _lane in self._eval_job_spend():
            total += cost
            calls += 1
        return round(total, 6), calls

    def _eval_job_spend(self) -> list[tuple[float, str]]:
        """``(run_cost_usd, lane_id)`` per landed eval job that accrued spend (AF-30)."""
        out: list[tuple[float, str]] = []
        try:
            rows = self._conn.execute(
                "SELECT payload_json, result_json FROM jobs "
                "WHERE kind='eval_rerun' AND result_json IS NOT NULL"
            ).fetchall()
        except sqlite3.OperationalError:
            return out  # no jobs table (a non-arena db)
        for payload_json, result_json in rows:
            try:
                result = json.loads(result_json) if result_json else {}
            except (ValueError, TypeError):
                continue
            guardrail = (result or {}).get("guardrail") or {}
            try:
                cost = float(guardrail.get("run_cost_usd") or 0.0)
            except (TypeError, ValueError):
                cost = 0.0
            if cost <= 0:
                continue
            lane = "eval"
            try:
                payload = json.loads(payload_json) if payload_json else {}
                lane = str(payload.get("lane_id") or payload.get("model") or "eval")
            except (ValueError, TypeError):
                pass
            out.append((cost, lane))
        return out

    def price_for(
        self, model_id: str, *, snapshot_id: str | None = None
    ) -> PriceSnapshot | None:
        """The :class:`PriceSnapshot` for ``model_id``, or ``None`` if unpriced.

        With no ``snapshot_id`` (the default) the **freshest** row for the model
        wins (newest ``captured_at`` across snapshots) — so a price captured at
        dispatch / refreshed from the OpenRouter catalog takes effect on the
        next run. The pre-BUG-3 default pinned every read to the baked H6
        baseline, which is exactly how the G3 cost cap ran silently inert for
        every current lane (e2e smoke C1, 2026-06-06). Pass ``snapshot_id`` to
        pin a read to one snapshot — prior comparisons stay reproducible.
        """
        try:
            if snapshot_id is not None:
                row = self._conn.execute(
                    "SELECT snapshot_id, model_id, price_per_m_input_usd, "
                    "       price_per_m_output_usd, source, captured_at "
                    "FROM openrouter_price_snapshot "
                    "WHERE snapshot_id=? AND model_id=?",
                    (snapshot_id, model_id),
                ).fetchone()
            else:
                row = self._conn.execute(
                    "SELECT snapshot_id, model_id, price_per_m_input_usd, "
                    "       price_per_m_output_usd, source, captured_at "
                    "FROM openrouter_price_snapshot "
                    "WHERE model_id=? "
                    "ORDER BY captured_at DESC, snapshot_id DESC LIMIT 1",
                    (model_id,),
                ).fetchone()
        except sqlite3.OperationalError:
            return None
        if row is None:
            return None
        return PriceSnapshot(
            snapshot_id=row[0],
            model_id=row[1],
            price_per_m_input_usd=float(row[2]),
            price_per_m_output_usd=float(row[3]),
            source=row[4],
            captured_at=row[5],
        )


# ---------------------------------------------------------------------------
# Public $/quality-point read (M9-3 / M9-4)
# ---------------------------------------------------------------------------


def _format_cost_per_quality(
    mean_cost_usd: float | None, cost_per_quality_point: float | None
) -> str:
    """The M9-4 display contract — never a divide-by-zero "—".

    A local lane (``$0`` aggregate cost) renders ``"$0 (local)"`` rather than a
    blank; a priced lane renders ``"$<cpq>/pt"``; an as-yet-unscored lane
    (``cost_per_quality_point is None`` but cost present) renders ``"—"``.
    """
    if mean_cost_usd is not None and float(mean_cost_usd) == 0.0:
        return "$0 (local)"
    if cost_per_quality_point is None:
        return "—"
    return f"${float(cost_per_quality_point):.4f}/pt"


def cost_per_quality(
    store_or_conn: Any, bench_id: str, lane_id: str
) -> dict[str, Any] | None:
    """The public **$/quality-point** read off ``leaderboard_rows``.

    Returns a dict (``bench_id``, ``lane_id``, ``mean_cost_usd``,
    ``mean_score``, ``cost_per_quality_point``, ``is_local``, ``display``) or
    ``None`` if the (bench, lane) pair has no leaderboard row. ``display`` is
    the M9-4 render string ("$0 (local)" for local lanes, "$X.XXXX/pt"
    otherwise). The aggregate cost surface is the **only** one that goes public
    (per-run cost stays on the private host tables, M9-2/M9-7).
    """
    conn = _as_conn(store_or_conn)
    try:
        row = conn.execute(
            "SELECT mean_cost_usd, mean_score, cost_per_quality_point "
            "FROM leaderboard_rows WHERE bench_id=? AND lane_id=?",
            (bench_id, lane_id),
        ).fetchone()
    except sqlite3.OperationalError:
        return None
    if row is None:
        return None
    mean_cost_usd = None if row[0] is None else float(row[0])
    mean_score = None if row[1] is None else float(row[1])
    cpq = None if row[2] is None else float(row[2])
    is_local = mean_cost_usd is not None and mean_cost_usd == 0.0
    return {
        "bench_id": bench_id,
        "lane_id": lane_id,
        "mean_cost_usd": mean_cost_usd,
        "mean_score": mean_score,
        "cost_per_quality_point": cpq,
        "is_local": is_local,
        "display": _format_cost_per_quality(mean_cost_usd, cpq),
    }
