---
module: cost
title: fieldkit.cost
summary: Per-run cost ledger for the cockpit — persists what each cloud call cost and ranks lanes by $/task and $/quality-point alongside speed and quality. Ledger, not governor.
order: 14
---

## What it is

The **cost plane** — Bet 6 of the "machine that builds machines" roadmap
(`_FLOWS/the-machine-that-builds-machines.md` §3), shipped as **Arena M9**
(`_SPECS/spark-arena-v1.md` §13). Token economics promoted to a first-class
decision axis: "hosted SOTA or local?" answered on **three** axes — quality,
throughput, **and cost** — instead of two.

M9 is **connective tissue, not greenfield.** The Arena sidecar already
*computes* an OpenRouter cost per run (`fieldkit.arena.server._compare_cost_usd`)
but throws it away — it lands in an in-memory accumulator that resets on every
restart and never reaches the database. `fieldkit.cost` is the **ledger + read
API** that persists it, plus the **price snapshot** that pins prices
reproducibly.

It is a **ledger, not a governor.** M9 ships the meter (per-run rows + the
public `$/quality-point`); the `fieldkit.budget` *enforcement* arm — the
`LOCAL_CEILING = 33%` escalation contract, the spend digest — lives in Phase 2
(Arena M11, `_SPECS/spark-arena-v1.md` §15), which *consumes* this ledger.

The module is **store-agnostic by duck-typing**: every entry point accepts
either an `ArenaStore` (anything with `.connect()`) or a raw
`sqlite3.Connection`, so `fieldkit.cost` never imports `fieldkit.arena` — the
store seeds *this* module at `initialize()`, and a back-import would be circular.

## The three surfaces

- **Price snapshot** — `PriceSnapshot` + `seed_price_snapshot`. The
  `openrouter_price_snapshot` table is seeded at store-init from the **baked H6
  evidence** (`articles/hermes-cost-routing-local-and-openrouter/evidence/
  openrouter_prices.json`), NOT the live OpenRouter catalog. Each persisted cost
  row stamps the `snapshot_id` (`H6_SNAPSHOT_ID = "h6-baseline"`) it was priced
  against, so a comparison stays reproducible as live prices drift (R19). The
  seed is baked as the `H6_PRICE_SEED` Python constant so a PyPI wheel can
  re-seed without shipping the article tree.
- **Per-run ledger** — `CostLedger`. Reads the persisted per-run cost rows on
  `compare_responses` (per side) and `chat_turns` (per turn) — both
  operator-private tables (off `mirror.PUBLISHABLE_TABLES`), so the ledger is
  private by construction. `CostLedger.session_spend()` rehydrates the live
  spend rail's running total across a sidecar restart (M9-8);
  `CostLedger.price_for(model_id)` returns a `PriceSnapshot`.
- **Public $/quality-point** — `cost_per_quality`. Reads the aggregate
  `mean_cost_usd / mean_score` off `leaderboard_rows` (the only cost surface
  that goes public), with the local-lane **`$0 (local)`** rendering that avoids
  a divide-by-zero "—" (M9-4).

## Public API

```python
from fieldkit.cost import (
    CostLedger,              # read API over the persisted per-run cost rows
    PriceSnapshot,           # one openrouter_price_snapshot row (+ .cost_usd())
    seed_price_snapshot,     # idempotent seed (defaults to the baked H6 evidence)
    fetch_openrouter_prices, # live per-M prices from the OpenRouter /models catalog
    refresh_prices,          # capture live prices into a dated snapshot (BUG-3 fix)
    cost_per_quality,        # the public $/quality-point read off leaderboard_rows
    CostError,               # raised on a bad seed / lookup / fetch failure
)
```

### `PriceSnapshot`

A frozen dataclass — `snapshot_id`, `model_id`, `price_per_m_input_usd`,
`price_per_m_output_usd`, `source` (`'h6_evidence'` / `'fallback'` / an operator
label), `captured_at` (the upstream capture instant, rendered as "prices as of
&lt;date&gt;"). `PriceSnapshot.cost_usd(tokens_in=…, tokens_out=…)` returns the
USD for those token counts at this snapshot's per-million prices.

### `seed_price_snapshot(store_or_conn, *, prices=None, snapshot_id="h6-baseline", source="h6_evidence", captured_at=…)`

Seeds (idempotent, `INSERT OR REPLACE` on the `(snapshot_id, model_id)` PK) the
`openrouter_price_snapshot` table and returns the row count. Defaults to the
baked `H6_PRICE_SEED`; pass `prices` (a sequence of `{model_id,
price_per_m_input_usd, price_per_m_output_usd}` mappings) under a new
`snapshot_id` to re-seed from a fresh capture — the R19 fallback. Old rows keep
their `price_snapshot_id`, so prior comparisons stay reproducible. Called by
`ArenaStore.initialize()` so a fresh or migrated db is always seeded.

### `fetch_openrouter_prices(model_ids=None, *, timeout=10.0)`

Reads current per-million prices from the public OpenRouter `/models` catalog
(the `OPENROUTER_API_KEY` header is attached when present, not required) and
returns rows in the `seed_price_snapshot` `prices` shape — filtered to
`model_ids` when given, the whole catalog otherwise. Un-priceable entries
(image/embedding/router) are omitted. Raises `CostError` on a network / HTTP /
shape failure so callers decide how loud to be; `timeout` bounds the request.

### `refresh_prices(store_or_conn, model_ids=None, *, fetcher=None, now_iso=None)`

The BUG-3 fix — the snapshot table's **refresh path**. Fetches live prices (via
`fetcher`, default `fetch_openrouter_prices`; inject a fake in tests) and seeds
them under a dated snapshot id (`or-refresh-<UTC date>`, `source='openrouter-api'`,
`captured_at` = `now_iso` or now). Prior snapshots keep their rows; the
newest-row default of `price_for` makes the refresh effective on the very next
dispatch. Returns the rows written (+ `snapshot_id`/`captured_at`). The Arena
eval dispatch calls this automatically for an unpriced cloud model
(price-at-dispatch capture, `FK_EVAL_PRICE_AT_DISPATCH=0` opts out), and
`POST /api/prices/refresh` exposes it as the Settings-pane operator action.

### `CostLedger(store_or_conn)`

- `.session_spend() -> (total_usd, n_paid_runs)` — total persisted OpenRouter
  spend summed across `compare_responses` + `chat_turns` (the M9-8 fix for the
  accumulator that reset to `$0` on every boot), **plus metered eval-job spend**
  persisted at `jobs.result_json.guardrail.run_cost_usd` (AF-30 — the budget
  governor and Standup SPEND were blind to it). A pre-M9 db (no cost column)
  contributes zero rather than raising.
- `.price_for(model_id, *, snapshot_id=None) -> PriceSnapshot | None` — the
  **freshest** snapshot row for a model by default (newest `captured_at` across
  snapshots — so a refresh/capture takes effect immediately; the pre-BUG-3
  default pinned every read to the stale H6 baseline, which is exactly how the
  G3 cost cap ran silently inert). Pass `snapshot_id` to pin a read to one
  snapshot — prior comparisons stay reproducible. `None` for a local/unknown
  lane.

### `cost_per_quality(store_or_conn, bench_id, lane_id)`

Returns a dict — `bench_id`, `lane_id`, `mean_cost_usd`, `mean_score`,
`cost_per_quality_point` (`mean_cost_usd / mean_score`, guarded `mean_score >
0`), `is_local`, and `display` (the M9-4 render string: `"$0 (local)"` for a
local lane, `"$X.XXXX/pt"` otherwise) — or `None` if the (bench, lane) pair has
no leaderboard row.

## Schema (`user_version` 4 → 5)

M9 is the **first ALTER-based migration** (`ArenaStore._migrate`, R18 — every
prior bump only added whole tables). It adds, additively + non-destructively:

- `chat_turns.cost_usd` / `tokens_estimated`
- `compare_responses.tokens_in` / `cost_usd` / `tokens_estimated` /
  `price_snapshot_id` (per-side — each lane bills the shared prompt at its own
  input price)
- `leaderboard_rows.mean_cost_usd` / `cost_per_quality_point` (the public
  aggregate)
- the new `openrouter_price_snapshot` table

`tokens_estimated = 1` flags a cost computed from the 4-char heuristic (the
streaming path carries no `usage` block) so an approximate `$/task` is marked
with a `~` in the cockpit, never silently trusted (R20).

## Mirror safety

The per-run cost columns are operator-private (each is keyed to a specific
prompt) and stay **off** `mirror.PUBLISHABLE_TABLES`. Only the aggregate
(`leaderboard_rows.mean_cost_usd` / `cost_per_quality_point`) and the
prompt-free `openrouter_price_snapshot` are publishable — enough to reconstruct
the public `$/task` without leaking a single prompt. Anchored by
`tests/arena/test_mirror_does_not_leak.py` (the R13-family hard gate).

## See also

- `fieldkit.arena` — the cockpit + store this plane meters.
- `_SPECS/spark-arena-v1.md` §13 — the M9 locked decisions (M9-1…10).
- `articles/hermes-cost-routing-local-and-openrouter/` — the H6 evidence the
  price snapshot is seeded from (25% spend cut at an 8.3% quality cost, 33%
  leak).
