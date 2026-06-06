# Copyright 2026 Manav Sehgal
# SPDX-License-Identifier: Apache-2.0
"""FastAPI sidecar — ``127.0.0.1:7866`` cockpit backend.

**M4 surface.** ``create_app()`` builds a FastAPI app with:

- ``GET /healthz`` — process liveness + the arena surface version.
- ``GET /api/lanes`` — reads ``~/.hermes/config.yaml`` for the current warm
  brain plus the ``lanes`` table for the registered roster.
- ``GET /api/leaderboard?limit=N`` — proxies the static mirror JSON at
  ``src/data/arena-mirror/leaderboard.json``.
- ``GET /api/telemetry/stream`` — Server-Sent-Events at 500 ms cadence
  backed by :class:`fieldkit.harness.Telemetry`. The sampler runs only
  while at least one subscriber is open (zero background load otherwise)
  via the :class:`TelemetryHub` reference-counter.
- ``POST /api/chat/stream`` — single-lane chat against the resident brain
  (the lane returned by ``GET /api/lanes``'s ``resident`` field). Streams
  ``start`` / ``token`` / ``done`` SSE events from ``llama-server :8080``
  by way of :class:`fieldkit.notebook.OpenAICompatClient`; user + assistant
  turns persist to ``chat_sessions`` + ``chat_turns`` (operator-private —
  spec §4.8 + the M6 mirror allowlist hardcodes ``chat_*`` tables out of
  the enumeration). Wires :meth:`TelemetryHub.report_inflight` on stream
  start + done so the M3 telemetry gauge's tok/s / TTFT / lane chip light
  up while a stream is in flight.

**M5 surface (added this milestone):** ``GET /api/rubrics`` returns the
default 3-rubric registry (see :mod:`fieldkit.arena.rubrics`);
``POST /api/compare/stream`` proxies the side-by-side compare's
``start_a / token_a / done_a / [swap] / start_b / token_b / done_b /
score`` SSE event sequence (spec §4.3); ``POST /api/prefs`` writes one
``human_prefs`` row — separate signal, never mutates the scored total.
M6 adds ``GET /api/arena-mirror`` for the public-mirror handshake.

FastAPI / uvicorn / sse-starlette are pulled in via the ``arena`` extra
and imported lazily inside :func:`create_app` and :func:`serve` — so
``import fieldkit.arena.server`` stays stdlib-only and the package-level
``import fieldkit.arena`` doesn't pay the FastAPI startup cost.
"""

# NOTE: this module deliberately does NOT use `from __future__ import
# annotations`. FastAPI's dependency-injection introspects the endpoint
# function signatures via inspect; with PEP 563 deferred annotations the
# locally-imported `Request` symbol in `create_app` would be invisible to
# FastAPI's `get_type_hints` call (it looks at module globals), and the
# `/api/telemetry/stream` route would mis-bind `request` as a query param.
# Every annotation in this file is therefore a real runtime object.

import asyncio
import json
import logging
import os
import re
import threading
import time
from pathlib import Path
from typing import Any, AsyncIterator, Callable, Optional, Tuple

from fieldkit.arena import (
    ARENA_SURFACE_VERSION,
    DEFAULT_ARENA_DB,
    DEFAULT_ARENA_PORT,
)

__all__ = [
    "create_app",
    "serve",
    "TelemetryHub",
    "telemetry_event_stream",
    "chat_event_stream",
    "compare_event_stream",
]

_log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Hermes config reader — a thin wrapper over the YAML at ``~/.hermes/config.yaml``.
# ---------------------------------------------------------------------------


def _read_hermes_lane(hermes_path: Path | None = None) -> dict[str, Any] | None:
    """Return the resident-brain shape pulled from ``~/.hermes/config.yaml``.

    Returns ``None`` when the file is missing or doesn't carry a usable
    ``model`` block. The reader re-runs on every endpoint call and lets
    the OS cache do the work — per Risk R8 in the spec, operator edits to
    the config should reflect on the next ``GET /api/lanes`` round-trip.

    Spec §4.6 / §4.9 — the shape mirrors a ``LaneRecord`` row that the
    M2 importer also writes; the live endpoint is the source-of-truth
    while the sidecar is up.
    """
    if hermes_path is None:
        hermes_path = Path("~/.hermes/config.yaml").expanduser()
    if not hermes_path.is_file():
        return None
    try:
        import yaml  # type: ignore[import-not-found]
    except ImportError:
        return None
    try:
        data = yaml.safe_load(hermes_path.read_text()) or {}
    except Exception as exc:  # noqa: BLE001 — telemetry/config is best-effort
        _log.warning("failed to parse %s: %s", hermes_path, exc)
        return None

    model_block = data.get("model") or {}
    if not isinstance(model_block, dict):
        return None
    # ``default`` is the live hermes config shape; ``name``/``model`` are
    # tolerated as legacy/alternate keys.
    model = (
        model_block.get("default")
        or model_block.get("name")
        or model_block.get("model")
        or ""
    )
    base_url = str(model_block.get("base_url") or "")
    if not (model or base_url):
        return None

    port = 0
    m = re.search(r":(\d+)", base_url)
    if m:
        port = int(m.group(1))

    provider = str(model_block.get("provider") or "")
    # ``provider: custom`` + base_url 127.0.0.1 → it's our local llama-server lane.
    if "127.0.0.1" in base_url or "localhost" in base_url:
        kind = "LlamaServerLane"
    elif provider in {"nim", "nvidia"} or ":8000" in base_url:
        kind = "NIMLane"
    else:
        kind = "RemoteLane"

    try:
        mtime = hermes_path.stat().st_mtime
    except OSError:
        mtime = None

    return {
        "id": "resident-brain",
        "kind": kind,
        "model": str(model),
        "base_url": base_url,
        "port": port,
        "provider": provider,
        "context_length": int(model_block.get("context_length") or 0) or None,
        "max_tokens": int(model_block.get("max_tokens") or 0) or None,
        "config_path": str(hermes_path),
        "config_mtime": mtime,
    }


def _read_active_gpu_lane(db_path: str) -> dict[str, Any] | None:
    """The lane currently holding the GPU per a running job (AE-15 layer 2).

    The lane arbiter (``fieldkit.arena.lane``) tears the resident chat brain down
    and seats a vLLM RL lane for the duration of an ``rl_run`` — a lane Hermes
    does not manage, so the static config can't see it. A running ``rl_run`` job
    row IS that truth: its ``base`` is the model on the RL lane. Returns
    ``{model, where}`` for the newest running GPU job, else ``None``. Best-effort
    (a missing/cold db just yields ``None``); the telemetry hub caches the call.
    """
    try:
        from fieldkit.arena.store import ArenaStore

        db_file = Path(db_path).expanduser()
        if not db_file.is_file():
            return None
        store = ArenaStore(db_file)
        with store:
            running = store.list_jobs(status="running", limit=20)
        for row in running:
            kind = row["kind"] if "kind" in row.keys() else None
            if kind != "rl_run":
                continue
            payload: dict[str, Any] = {}
            pj = row["payload_json"] if "payload_json" in row.keys() else None
            if isinstance(pj, str) and pj:
                try:
                    payload = json.loads(pj) or {}
                except json.JSONDecodeError:
                    payload = {}
            model = payload.get("base") or payload.get("lane_id") or "RL lane"
            return {"model": str(model), "where": "rl"}
    except Exception as exc:  # noqa: BLE001 — telemetry nicety, never fatal
        _log.debug("active-gpu-lane read failed: %s", exc)
    return None


def _trip_running_eval_sentinels(db_path: str) -> int:
    """Touch the eval-abort sentinel for every running ``eval_rerun`` job (AE-17 / G1).

    Called from ``_lifespan`` shutdown so an in-flight cloud eval aborts cleanly.
    The guardrail's sentinel path is deterministic from ``job_id`` (no shared
    memory with the dispatch task). Returns the count tripped. Best-effort — a
    missing/cold db, or a job without a guardrail (local lane), simply trips
    nothing harmful (the local-lane runner never polls the sentinel). Idempotent.
    """
    from fieldkit.arena.guardrail import eval_sentinel_for

    tripped = 0
    db_file = Path(db_path).expanduser()
    if not db_file.is_file():
        return 0
    from fieldkit.arena.store import ArenaStore

    store = ArenaStore(db_file)
    with store:
        running = store.list_jobs(status="running", limit=50)
    for row in running:
        kind = row["kind"] if "kind" in row.keys() else None
        if kind != "eval_rerun":
            continue
        sentinel = eval_sentinel_for(str(row["id"]))
        try:
            sentinel.parent.mkdir(parents=True, exist_ok=True)
            sentinel.write_text(
                json.dumps({"aborted_by": "teardown", "tripped_at": _utc_now_iso()}, sort_keys=True)
            )
            tripped += 1
        except OSError:
            pass
    return tripped


# ---------------------------------------------------------------------------
# Telemetry pump — one Telemetry instance shared across SSE subscribers.
# ---------------------------------------------------------------------------

# Sentinel for ``report_inflight``: distinguishes "caller didn't mention the
# speeds, keep the last ones sticky" from "caller explicitly cleared them to
# None". Using ``None`` as the default would make the stream-start ping and the
# idle/disconnect guard wipe the most recent generation's tok/s + TTFT, which
# is exactly the bug that left those rail cells blank the moment a stream ended.
_KEEP_SPEEDS: Any = object()


class TelemetryHub:
    """Reference-counted wrapper around :class:`fieldkit.harness.Telemetry`.

    Each subscriber calls :meth:`subscribe` to get an asyncio queue + a
    cleanup callable. The hub starts the underlying ``Telemetry`` sampler
    when the first subscriber attaches and stops it when the last one
    detaches — so the cockpit pays zero background CPU when no tab is open.

    The sampler runs on a background thread inside ``Telemetry``; this hub
    layers a second thread that polls ``Telemetry.samples`` at ``interval``
    seconds and fans the latest sample out to every queue via
    ``call_soon_threadsafe``. The decoupling keeps ``Telemetry`` 1:1 with
    the existing harness code (no changes needed there).
    """

    # Used to seed the rolling ``unified_total_gb`` field on every emitted
    # sample. Cheap (one stat) and stable for the life of the process.
    _UNIFIED_TOTAL_GB_CACHE: float | None = None

    def __init__(self, interval: float = 0.5) -> None:
        # Local import; harness is stdlib-cheap.
        from fieldkit.harness import Telemetry

        self.interval = float(interval)
        self._Telemetry = Telemetry
        self._telemetry: Any | None = None
        self._pump_thread: threading.Thread | None = None
        self._pump_stop = threading.Event()
        self._subscribers: list[
            tuple[asyncio.Queue[dict[str, Any]], asyncio.AbstractEventLoop]
        ] = []
        self._lock = threading.Lock()
        # Tok/s + TTFT come from in-flight stream callers (M4); the hub
        # keeps the last reported value so idle ticks can sticky them.
        self._last_inflight: dict[str, Any] = {
            "inflight": False,
            "tok_per_s": None,
            "ttft_ms": None,
            "lane_id": None,
        }
        # Running OpenRouter spend since this sidecar started (in-memory; resets
        # on restart per the v0.2 cost-meter contract). Compare-stream callers
        # add per-run cost via :meth:`add_openrouter_cost`; the rail renders it.
        self._openrouter_cost_usd: float = 0.0
        self._openrouter_calls: int = 0
        # Monotonic "the live leaderboard changed" revision. Bumped on compare /
        # chat completion + chat scoring; surfaced on every telemetry tick as
        # ``leaderboard_rev`` so the LiveLeaderboard island refetches
        # ``/api/leaderboard/live`` only when it actually moved (not every tick).
        self._leaderboard_rev: int = 0
        # Optional callable returning the configured resident lane dict, so the
        # "Active Lane" cell can show the warm brain at idle (not "no warm
        # brain"). Set by create_app; cached ~5s to avoid re-reading per tick.
        self._resident_reader: Callable[[], Any] | None = None
        self._resident_cache_t: float = 0.0
        self._resident_cache_v: str | None = None
        # AE-15 (telemetry lane-truth) — the rail's "active lane" must reflect a
        # LIVE process, not the static ~/.hermes/config.yaml value (which
        # persists at idle and while an rl_run has torn the resident brain down).
        #   layer 1: liveness-gate — a TCP probe of the configured resident
        #            base_url, cached so it never runs on the 0.5s pump tick.
        self._lane_live_cache_t: float = 0.0
        self._lane_live_cache_v: bool = False
        #   layer 2: arbiter truth — an injected, store-decoupled reader that
        #            returns the lane currently holding the GPU per a running
        #            rl_run/external job (validated live on the next armed run,
        #            AE-R1). Set by create_app; cached ~5s.
        self._active_lane_reader: Callable[[], Any] | None = None
        self._active_lane_cache_t: float = 0.0
        self._active_lane_cache_v: dict[str, Any] | None = None

    # -- subscription contract --------------------------------------------

    def subscribe(
        self, loop: asyncio.AbstractEventLoop
    ) -> tuple[asyncio.Queue[dict[str, Any]], Callable[[], None]]:
        """Attach a subscriber; return ``(queue, unsubscribe)``.

        The first subscriber starts the underlying sampler. The
        ``unsubscribe`` callable is idempotent.
        """
        q: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=64)
        with self._lock:
            self._subscribers.append((q, loop))
            should_start = len(self._subscribers) == 1
        if should_start:
            self._start()

        def _unsubscribe() -> None:
            with self._lock:
                for i, (qq, _) in enumerate(list(self._subscribers)):
                    if qq is q:
                        self._subscribers.pop(i)
                        break
                should_stop = len(self._subscribers) == 0
            if should_stop:
                self._stop()

        return q, _unsubscribe

    @property
    def subscriber_count(self) -> int:
        with self._lock:
            return len(self._subscribers)

    @property
    def is_running(self) -> bool:
        return self._telemetry is not None

    def report_inflight(
        self,
        *,
        inflight: bool,
        tok_per_s: float | None = _KEEP_SPEEDS,
        ttft_ms: float | None = _KEEP_SPEEDS,
        lane_id: Any = _KEEP_SPEEDS,
    ) -> None:
        """M4+ stream callers ping this to tag the active lane + speeds.

        The last reported tok/s + TTFT are *sticky*: the rail keeps showing the
        most recent generation's speeds after the stream ends, until the next
        ``done`` refreshes them. So callers that only flip ``inflight`` — the
        stream-start ping and the idle/disconnect ``finally`` guard — must NOT
        clobber the speeds. Omit ``tok_per_s``/``ttft_ms`` (they default to the
        keep-sentinel and are preserved); pass ``None`` explicitly only when you
        genuinely want to clear them.

        ``lane_id`` is sticky the same way — the rail keeps labelling the last
        model + where it ran (Spark vs OpenRouter) at idle, so the throughput /
        TTFT figures always carry their source. Omit it to preserve the label;
        pass ``None`` explicitly only to genuinely clear the active-lane tag.
        """
        prev = self._last_inflight
        self._last_inflight = {
            "inflight": bool(inflight),
            "tok_per_s": prev["tok_per_s"] if tok_per_s is _KEEP_SPEEDS else tok_per_s,
            "ttft_ms": prev["ttft_ms"] if ttft_ms is _KEEP_SPEEDS else ttft_ms,
            "lane_id": prev["lane_id"] if lane_id is _KEEP_SPEEDS else lane_id,
        }

    def add_openrouter_cost(self, usd: float) -> None:
        """Accumulate paid OpenRouter spend (USD) since sidecar start.

        Called by :func:`compare_event_stream` after a metered OpenRouter side
        completes; the figure surfaces in the telemetry payload's
        ``openrouter_cost_usd`` so the rail can render a live spend cell. Float
        ``+=`` is fine under the GIL — the only writer is the event-loop thread.
        """
        try:
            inc = float(usd)
        except (TypeError, ValueError):
            return
        if inc > 0:
            self._openrouter_cost_usd += inc
            self._openrouter_calls += 1

    def seed_session_spend(self, usd: float, calls: int) -> None:
        """Initialize the spend rail from the persisted cost ledger (M9-8).

        Called once at ``create_app`` from :meth:`fieldkit.cost.CostLedger.
        session_spend` so the live rail surfaces the running total instead of
        resetting to ``0.0`` on every sidecar restart — the recon-#1 fix.
        Replaces (not accumulates) the in-memory figures: it is the rehydrated
        baseline, and subsequent :meth:`add_openrouter_cost` calls add to it.
        """
        try:
            self._openrouter_cost_usd = max(0.0, float(usd))
            self._openrouter_calls = max(0, int(calls))
        except (TypeError, ValueError):
            pass

    @property
    def leaderboard_rev(self) -> int:
        with self._lock:
            return self._leaderboard_rev

    def bump_leaderboard(self) -> None:
        """Signal that a run completed and the live leaderboard moved.

        Surfaces as ``leaderboard_rev`` on the next telemetry tick (≤ the pump
        interval) so the LiveLeaderboard island refetches. Called from the
        event-loop thread after the relevant DB commit, so a refetch triggered
        by the bump always sees committed data. Guarded by ``self._lock`` (also
        held by the pump thread's payload read) for a consistent value."""
        with self._lock:
            self._leaderboard_rev += 1

    # -- internal: sampler + pump -----------------------------------------

    def _start(self) -> None:
        # Telemetry's interval drives the underlying nvidia-smi cadence; we
        # sample slightly more often than the SSE tick so the queue always
        # has a fresh value to dispatch.
        self._telemetry = self._Telemetry(interval=self.interval).start()
        self._pump_stop.clear()
        self._pump_thread = threading.Thread(
            target=self._pump_loop, name="arena-telemetry-pump", daemon=True
        )
        self._pump_thread.start()

    def _stop(self) -> None:
        self._pump_stop.set()
        # Telemetry's own stop joins its thread (5s timeout).
        if self._telemetry is not None:
            try:
                self._telemetry.stop()
            except Exception as exc:  # noqa: BLE001
                _log.warning("Telemetry.stop() raised: %s", exc)
            self._telemetry = None
        if self._pump_thread is not None:
            self._pump_thread.join(timeout=2)
            self._pump_thread = None

    def _unified_total_gb(self) -> float | None:
        if TelemetryHub._UNIFIED_TOTAL_GB_CACHE is not None:
            return TelemetryHub._UNIFIED_TOTAL_GB_CACHE
        try:
            for ln in Path("/proc/meminfo").read_text().splitlines()[:3]:
                k, _, rest = ln.partition(":")
                if k == "MemTotal":
                    tok = rest.split()
                    if tok:
                        TelemetryHub._UNIFIED_TOTAL_GB_CACHE = round(
                            float(tok[0]) / 1024 / 1024, 1
                        )
                        return TelemetryHub._UNIFIED_TOTAL_GB_CACHE
        except OSError:
            pass
        return None

    def _resident_model(self) -> str | None:
        """The configured resident lane's model name (cached ~5s), or None."""
        reader = self._resident_reader
        if reader is None:
            return None
        now = time.monotonic()
        if now - self._resident_cache_t < 5.0:
            return self._resident_cache_v
        try:
            lane = reader()
            val = (lane or {}).get("model") if lane else None
        except Exception:  # noqa: BLE001
            val = None
        self._resident_cache_t = now
        self._resident_cache_v = val
        return val

    def _resident_live(self) -> bool:
        """True iff the configured resident lane's ``base_url`` answers (AE-15 l1).

        The config (``~/.hermes/config.yaml``) names a pinned brain (Qwen3-30B)
        whether or not anything is actually serving — so the rail used to claim
        an idle box was running it, and an ``rl_run`` that tore the resident brain
        down stayed invisible. A cheap TCP connect to the configured host:port is
        the honest liveness signal. Cached ~8s — never run on the 0.5s pump tick.
        """
        now = time.monotonic()
        if now - self._lane_live_cache_t < 8.0:
            return self._lane_live_cache_v
        live = False
        reader = self._resident_reader
        try:
            lane = reader() if reader is not None else None
            if lane:
                base = str(lane.get("base_url") or "")
                port = int(lane.get("port") or 0)
                m = re.search(r"//([^:/]+)", base)
                host = m.group(1) if m else "127.0.0.1"
                if port:
                    import socket

                    with socket.create_connection((host, port), timeout=0.4):
                        live = True
        except Exception:  # noqa: BLE001 — liveness is best-effort
            live = False
        self._lane_live_cache_t = now
        self._lane_live_cache_v = live
        return live

    def _active_lane(self) -> dict[str, Any] | None:
        """The lane currently holding the GPU per the arbiter's truth (AE-15 l2).

        When an ``rl_run``/external GPU job is running, the resident chat brain has
        been torn down and a vLLM RL lane (which Hermes does not manage) holds the
        slot. The injected ``_active_lane_reader`` surfaces ``{model, where}`` for
        that job so the rail names the real lane instead of the stale config.
        Store-decoupled (mirrors ``_resident_reader``); cached ~5s. Returns None
        when nothing GPU-bound is running. Validated live on the next run (AE-R1).
        """
        reader = self._active_lane_reader
        if reader is None:
            return None
        now = time.monotonic()
        if now - self._active_lane_cache_t < 5.0:
            return self._active_lane_cache_v
        try:
            val = reader()
        except Exception:  # noqa: BLE001
            val = None
        self._active_lane_cache_t = now
        self._active_lane_cache_v = val if isinstance(val, dict) else None
        return self._active_lane_cache_v

    def _speed_label(self, lane_id: str | None) -> tuple[str | None, str | None]:
        """``lane_id`` → (friendly model name, where it runs).

        ``where`` is ``"spark"`` for any local lane (the on-demand quant slot or
        the warm resident brain) and ``"openrouter"`` for a cloud lane, so the
        rail can print the throughput/TTFT source as ``<model>`` + ``Spark GPU``
        / ``OpenRouter`` two-liner. Returns ``(None, None)`` before the first
        generation (no lane to label)."""
        if not lane_id:
            return None, None
        lid = str(lane_id)
        # Cloud lane — "openrouter::<provider/model>" (built in the lane factory)
        # or the "openrouter:<id>" picker form. Strip either, drop the provider
        # prefix for brevity (nvidia/nemotron-nano-9b-v2 → nemotron-nano-9b-v2).
        if lid.startswith("openrouter:"):
            mid = lid[len("openrouter:") :].lstrip(":")
            model = mid.split("/", 1)[1] if "/" in mid else mid
            return model, "openrouter"
        # The always-warm resident brain (row id varies — "resident-brain",
        # "local:resident", …); label it with the configured resident model.
        if "resident" in lid:
            return (self._resident_model() or "resident brain"), "spark"
        # On-demand local quant — bare "<slug>::<variant>" (the compare lane_id)
        # or a "local:" picker-prefixed form. Strip "-gguf", pretty the variant.
        spec = lid[len("local:") :] if lid.startswith("local:") else lid
        if "::" in spec:
            slug, _, variant = spec.partition("::")
            if slug.endswith("-gguf"):
                slug = slug[: -len("-gguf")]
            model = f"{slug} · {variant}" if variant else slug
            return model, "spark"
        # Any other bare local row id → still a Spark lane.
        return (self._resident_model() or spec), "spark"

    def _build_payload(self) -> dict[str, Any]:
        sample: dict[str, float] = {}
        if self._telemetry is not None and self._telemetry.samples:
            # Last sample on the deque; copying keeps it append-safe.
            sample = dict(self._telemetry.samples[-1])
        active_lane = self._active_lane()  # AE-15 layer 2 (None when idle)
        payload: dict[str, Any] = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "gpu_util": sample.get("gpu_util"),
            "gpu_temp_c": sample.get("gpu_temp_c"),
            "unified_used_gb": sample.get("unified_used_gb"),
            "unified_total_gb": self._unified_total_gb(),
            "inflight": self._last_inflight["inflight"],
            # tok/s and TTFT both sticky to the last generation — the rail
            # shows them at idle (dimmed) rather than blanking the instant a
            # stream ends. The ``inflight`` flag distinguishes live vs. last.
            "tok_per_s": self._last_inflight["tok_per_s"],
            "ttft_ms": self._last_inflight["ttft_ms"],
            "lane_id": self._last_inflight["lane_id"],
            # Source of the sticky tok/s + TTFT above: the model that produced
            # them + where it ran (Spark vs OpenRouter). After a compare this
            # is reconciled to the local/Spark side; in chat it's the lane you
            # ran. Lets the rail print a "<model> / <where>" two-liner so the
            # throughput/TTFT figures are never ambiguous about their origin.
            **dict(
                zip(
                    ("speed_model", "speed_where"),
                    self._speed_label(self._last_inflight["lane_id"]),
                )
            ),
            "resident_lane": self._resident_model(),
            # AE-15 telemetry lane-truth: the rail reconciles the configured
            # resident against what's actually serving. ``resident_live`` gates
            # the "active vs configured" label (layer 1/3); ``active_lane_*`` name
            # the real GPU lane during an rl_run/external job (layer 2).
            "resident_live": self._resident_live(),
            "active_lane_model": active_lane.get("model") if active_lane else None,
            "active_lane_where": active_lane.get("where") if active_lane else None,
            "openrouter_cost_usd": round(self._openrouter_cost_usd, 6),
            "openrouter_calls": self._openrouter_calls,
            # Change signal for the live leaderboard (see bump_leaderboard).
            "leaderboard_rev": self.leaderboard_rev,
        }
        return payload

    def _pump_loop(self) -> None:
        # Sleep first so the underlying Telemetry has at least one sample
        # before the first dispatch. Subscribers therefore see a populated
        # first tick rather than a row of null fields.
        while not self._pump_stop.wait(self.interval):
            payload = self._build_payload()
            with self._lock:
                subscribers = list(self._subscribers)
            for q, loop in subscribers:
                loop.call_soon_threadsafe(self._try_put, q, payload)

    @staticmethod
    def _try_put(
        q: asyncio.Queue[dict[str, Any]], payload: dict[str, Any]
    ) -> None:
        try:
            q.put_nowait(payload)
        except asyncio.QueueFull:
            # The subscriber is slow; drop the oldest to keep the gauge live.
            try:
                q.get_nowait()
                q.put_nowait(payload)
            except Exception:  # noqa: BLE001
                pass


# ---------------------------------------------------------------------------
# App factory.
# ---------------------------------------------------------------------------


def create_app(
    *,
    db: str | os.PathLike[str] | None = None,
    repo_root: str | os.PathLike[str] | None = None,
    telemetry_interval: float = 0.5,
    cors_origins: list[str] | None = None,
):
    """Build the FastAPI cockpit sidecar.

    Parameters
    ----------
    db
        Path to the operator-private SQLite store. Defaults to
        :data:`fieldkit.arena.DEFAULT_ARENA_DB`. Created lazily on first
        endpoint that needs it.
    repo_root
        Source-of-truth for the static mirror JSON
        (``src/data/arena-mirror/leaderboard.json``). Defaults to the
        current working directory; pass an explicit path when running
        the sidecar from a different cwd.
    telemetry_interval
        Seconds between SSE ticks. Spec §4.6 locks 0.5 s while a
        subscriber is open.
    cors_origins
        Astro dev runs on :4321 (host: true); the cockpit binds :7866 on
        loopback. The dev page's ``fetch`` / ``EventSource`` thus needs a
        CORS allow for ``http://127.0.0.1:4321`` and the LAN address the
        operator's browser actually sees. Defaults to a permissive dev
        set; production static mirror has no live fetches so there is no
        CORS exposure on the public surface.
    """
    # FastAPI is a fairly heavy import; keep it inside the factory so
    # ``import fieldkit.arena.server`` stays cheap (the CLI surfaces only).
    try:
        from contextlib import asynccontextmanager

        from fastapi import BackgroundTasks, FastAPI, HTTPException, Query, Request
        from fastapi.middleware.cors import CORSMiddleware
        from pydantic import BaseModel, Field
        from sse_starlette.sse import EventSourceResponse
    except ImportError as exc:  # pragma: no cover — explicit dep error message
        raise RuntimeError(
            "fieldkit.arena.server.create_app() requires the 'arena' extra. "
            "Install with `pip install 'fieldkit[arena]'`."
        ) from exc

    # ---- Pydantic request shapes (M4) ----

    class JudgeSpec(BaseModel):
        """Judge-backend selection for eval scoring (v0.3).

        ``backend`` is ``"local"`` (the warm resident brain — zero extra model
        load) or ``"openrouter"`` (a cloud frontier grader; needs
        ``OPENROUTER_API_KEY``). ``model`` optionally overrides the grader
        model. Only consulted for judge-backed scorers (patent A / D-oa /
        open-ended C / E) and free-prompt quality grading — deterministic
        scorers (MCQ / numeric / exact / IRAC) never build a judge."""

        backend: str = Field(default="local", pattern="^(local|openrouter)$")
        model: Optional[str] = None

    class ChatRequest(BaseModel):
        """``POST /api/chat/stream`` body. ``session_id`` is optional: omit
        on the first turn and the server allocates one + echoes it back in
        the ``start`` SSE event. ``rubric_id`` is reserved for M5
        score-on-completion; the M4 surface ignores it.
        """

        prompt: str = Field(min_length=1, max_length=32_000)
        session_id: Optional[str] = None
        rubric_id: Optional[str] = None
        # v0.2 — chat against any lane (default = resident brain). Same spec as
        # compare: "local:resident" / "local:<slug>::<variant>" / "openrouter" /
        # "openrouter:<model_id>". On-demand local lanes load on first turn.
        lane: str = Field(default="local:resident")
        # Token budget per turn; spec §4.6 calls 8 GB the headroom guard.
        # We default to a generous 4096 — Qwen3-30B-A3B with
        # ``--reasoning-format none`` (per the resident brain config) emits
        # a ``<think>`` chain that can be long; truncating loses the answer.
        max_tokens: int = Field(default=4096, ge=16, le=32_000)
        temperature: float = Field(default=0.0, ge=0.0, le=2.0)
        # v0.3 eval mode — when set, the server runs the bench's canonical
        # context-prepended prompt for ``eval_qid`` (replicating measurement
        # conditions) and surfaces an ``eval_context`` block in the ``start``
        # event. Scoring is a separate ``POST /api/chat/score`` call.
        bench_id: Optional[str] = Field(default=None, max_length=80)
        eval_qid: Optional[str] = Field(default=None, max_length=120)

    class CompareRequest(BaseModel):
        """``POST /api/compare/stream`` body — spec §4.3.

        ``lane_b`` is either ``"openrouter"`` (default — proxies through the
        H6 cost router's frontier tier) or ``"local:<lane_id>"`` (explicit
        two-local-lanes mode; the sidecar swaps the resident lane out for
        ``<lane_id>``'s warm path, emits a visible ``swap`` SSE event, then
        streams B's response). ``rubric_id`` is optional — the server falls
        back to :func:`default_rubric_for_prompt` when absent (spec §4.3
        substring-sweep picker). ``run_id`` is server-allocated; surfaces in
        the ``start_a`` SSE event so the thumbs-up handler can echo it back.
        """

        prompt: str = Field(min_length=1, max_length=32_000)
        # v0.2 any-vs-any: each side is one of
        #   "local:resident"            → the warm Spark lane (default for A)
        #   "openrouter"                → the curated H6 frontier tier (default B)
        #   "openrouter:<model_id>"     → any catalogued OpenRouter model
        # Back-compat: omitting lane_a keeps A on the resident brain, and the
        # bare "openrouter" lane_b still routes through the priced frontier tier.
        lane_a: str = Field(default="local:resident")
        lane_b: str = Field(default="openrouter")
        rubric_id: Optional[str] = None
        max_tokens: int = Field(default=4096, ge=16, le=32_000)
        temperature: float = Field(default=0.0, ge=0.0, le=2.0)
        # v0.3 eval mode — score BOTH sides against the bench gold for
        # ``eval_qid`` and augment the ``score`` event with an ``eval`` block.
        bench_id: Optional[str] = Field(default=None, max_length=80)
        eval_qid: Optional[str] = Field(default=None, max_length=120)
        judge: Optional[JudgeSpec] = None

    class ChatScoreRequest(BaseModel):
        """``POST /api/chat/score`` body — grade a completed chat turn.

        ``turn_id`` is the assistant turn returned in the chat ``done`` event.
        With ``bench_id`` + ``eval_qid`` the answer is scored against the bench
        gold; without them (free prompt) a ``judge`` grades quality vs the
        ``question``. ``lane_id`` + ``cross_vertical`` are echoed into the
        persisted ``eval_scores`` row for the accuracy leaderboard."""

        turn_id: int = Field(ge=1)
        bench_id: Optional[str] = Field(default=None, max_length=80)
        eval_qid: Optional[str] = Field(default=None, max_length=120)
        question: Optional[str] = Field(default=None, max_length=32_000)
        lane_id: Optional[str] = Field(default=None, max_length=200)
        cross_vertical: bool = False
        judge: Optional[JudgeSpec] = None

    class PrefRequest(BaseModel):
        """``POST /api/prefs`` body — operator thumbs verdict on a compare run.

        Per spec §4.3 the insert is a **separate signal**; the M5 sidecar
        records the row in ``human_prefs`` but never mutates the
        corresponding ``rubric_scores.total``. The leaderboard surfaces the
        winrate only at ≥5 prefs per lane.
        """

        compare_run_id: str = Field(min_length=1)
        winner: str = Field(pattern="^(A|B|tie)$")
        note: Optional[str] = Field(default=None, max_length=2000)

    class LabNoteRequest(BaseModel):
        """``POST /api/lab/notes`` body — operator annotation pinned to a Lab
        board card (v0.2).

        Operator-private: the ``body`` is freeform and is NEVER mirrored — the
        ``lab_notes`` table is on ``mirror.FORBIDDEN_TABLES`` + pinned by
        ``test_mirror_does_not_leak.py``. Deterministic CRUD only; no LLM
        generation here (``feedback_llm_skill_pattern``).
        """

        card_id: str = Field(min_length=1, max_length=200)
        body: str = Field(min_length=1, max_length=4000)
        lane: Optional[str] = Field(default=None, max_length=40)

    class LocalLoadRequest(BaseModel):
        """``POST /api/local/load`` body — pre-warm an on-demand local lane.

        ``lane`` is a compare lane spec (``"local:<slug>::<variant>"`` or the
        bare ``"<slug>::<variant>"``). Loading is single-slot (the prior
        on-demand model is torn down first); the resident on :8080 is untouched."""

        lane: str = Field(min_length=1, max_length=200)

    class JobCreateRequest(BaseModel):
        """``POST /api/jobs`` body — enqueue a control-plane job (M8).

        Operator-private: ``payload`` carries the lane/bench/manifest the job
        operates on and lands in ``jobs.payload_json`` — a FORBIDDEN_COLUMN,
        never mirrored (R13). M8 dispatches only ``eval_rerun`` /
        ``measure_variants``; ``dispatch=True`` (default) drains the queue in
        a BackgroundTask right after enqueue (the M8 primary single-lane path,
        R14 — no arq/Redis required). The drain executes **through the
        `fieldkit.harness` MCP surface** (M8-1), so it needs the resident lane
        served + the `harness` extra; on a box without them the job is marked
        ``failed`` with the import/connection error, never silently dropped."""

        kind: str = Field(
            pattern="^(eval_rerun|measure_variants|reindex|rag_eval|scout_ingest|rl_run)$"
        )
        payload: dict = Field(default_factory=dict)
        trigger: str = Field(default="manual", max_length=40)
        priority: int = Field(default=0, ge=0, le=100)
        dispatch: bool = True

    class KnowledgeReindexRequest(BaseModel):
        """``POST /api/knowledge/reindex`` — enqueue an M10 ``reindex`` job.

        ``source_set`` ∈ ``{articles, scout, lineage, all}``; the drain runs
        ``fieldkit.memory`` through the harness surface and writes a
        ``reindex_runs`` row. ``rag_eval`` (default True) chains a scoring job
        after the rebuild so the RAG-eval trend + promotion gate stay current."""

        source_set: str = Field(
            default="articles", pattern="^(articles|scout|lineage|all)$"
        )
        papers_json: Optional[str] = Field(default=None, max_length=500)
        rag_eval: bool = True
        dispatch: bool = True

    class KnowledgeQueryRequest(BaseModel):
        """``POST /api/knowledge/query`` — the operator's provenance-filtered
        query console (M10-4/9). Returns chunk text — OPERATOR-PRIVATE, served
        live only, never mirrored. ``provenance`` filters by trust tier."""

        query: str = Field(min_length=1, max_length=2000)
        top_k: int = Field(default=5, ge=1, le=20)
        provenance: Optional[list[str]] = Field(default=None)

    db_path = str(db or DEFAULT_ARENA_DB)
    root = Path(repo_root or Path.cwd()).resolve()
    hub = TelemetryHub(interval=telemetry_interval)
    # Let the telemetry "Active Lane" cell show the warm resident at idle.
    hub._resident_reader = _read_hermes_lane  # noqa: SLF001
    # AE-15 layer 2 — name the real GPU lane when an rl_run/external job is
    # running (the resident brain is torn down then). Store-decoupled callable.
    hub._active_lane_reader = lambda: _read_active_gpu_lane(db_path)  # noqa: SLF001
    # M9 (Bet 6): rehydrate the live spend rail from the persisted cost ledger
    # so the running OpenRouter total survives a sidecar restart (M9-8) instead
    # of resetting to $0. Best-effort — a cold/missing db just leaves $0.
    try:
        from fieldkit.arena.store import ArenaStore
        from fieldkit.cost import CostLedger

        _db_file = Path(db_path).expanduser()
        if _db_file.is_file():
            _store = ArenaStore(_db_file)
            with _store:
                _spend, _calls = CostLedger(_store).session_spend()
            hub.seed_session_spend(_spend, _calls)
    except Exception as exc:  # noqa: BLE001 — telemetry nicety, never fatal
        _log.warning("session-spend rehydrate failed: %s", exc)

    if cors_origins is None:
        cors_origins = [
            "http://127.0.0.1:4321",
            "http://localhost:4321",
            # LAN address per ``reference_nvidia_learn_runtime``; harmless
            # if Spark's IP changes — the dev server only binds loopback
            # in production-mirror mode.
            "http://10.0.0.209:4321",
        ]

    @asynccontextmanager
    async def _lifespan(_app: "FastAPI"):
        # Yield-only: the hub starts itself on first SSE subscribe, so
        # there is nothing to do on app boot. On shutdown, last-line guard:
        # if subscribers were torn off uncleanly, stop the sampler thread
        # so the process exits cleanly.
        try:
            yield
        finally:
            # AE-17 / G1 — trip the eval-abort sentinel for any in-flight cloud
            # eval so its row-loop stops cleanly instead of only dying with the
            # process (the qwen3-8b OpenRouter hang motivation). Deterministic
            # sentinel paths from job_id (the RL `sentinel_for` trick) mean we
            # need share no memory with the dispatch BackgroundTask.
            try:
                _trip_running_eval_sentinels(db_path)
            except Exception as exc:  # noqa: BLE001 — never block a clean shutdown
                _log.warning("eval guardrail teardown on shutdown raised: %s", exc)
            # Tear down any on-demand local model so the process exits clean.
            try:
                _LOCAL_SERVER_MANAGER.teardown()
            except Exception as exc:  # noqa: BLE001
                _log.warning("on-demand teardown on shutdown raised: %s", exc)
            if hub.is_running:
                hub._stop()  # noqa: SLF001

    app = FastAPI(
        title="Spark Arena sidecar",
        version=ARENA_SURFACE_VERSION,
        docs_url="/api/_docs",  # off the main /arena/ path
        redoc_url=None,
        lifespan=_lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_methods=["GET", "POST", "DELETE"],
        allow_headers=["*"],
    )

    # Stash hub on app.state so tests can introspect.
    app.state.hub = hub
    app.state.db_path = db_path
    app.state.repo_root = root

    # ------------------------------------------------------------------
    # Endpoints
    # ------------------------------------------------------------------

    @app.get("/healthz")
    async def healthz() -> dict[str, Any]:
        return {
            "ok": True,
            "arena_surface_version": ARENA_SURFACE_VERSION,
            "telemetry_running": hub.is_running,
            "subscribers": hub.subscriber_count,
            "db": db_path,
            "repo_root": str(root),
        }

    @app.get("/api/lanes")
    async def api_lanes() -> dict[str, Any]:
        """Live read of the current resident lane + the registered roster.

        Resident: re-reads ``~/.hermes/config.yaml`` on every request
        (cheap; the OS caches the file). Roster: pulled from
        ``ArenaStore.lanes()`` if the M2 store exists; otherwise empty.
        """
        resident = _read_hermes_lane()
        roster: list[dict[str, Any]] = []
        try:
            from fieldkit.arena.store import ArenaStore

            db_file = Path(db_path).expanduser()
            if db_file.is_file():
                store = ArenaStore(db_file)
                with store:
                    for row in store.lanes():
                        roster.append({k: row[k] for k in row.keys()})
        except Exception as exc:  # noqa: BLE001
            _log.warning("ArenaStore.lanes() failed: %s", exc)
        return {"resident": resident, "roster": roster}

    @app.get("/api/leaderboard")
    async def api_leaderboard(
        limit: int = Query(default=5, ge=1, le=200),
    ) -> dict[str, Any]:
        """Proxy the static mirror JSON. M5 will rebuild this from
        ``compare_runs`` / ``rubric_scores``; M3 reads what M2 seeded."""
        mirror_file = (
            root / "src" / "data" / "arena-mirror" / "leaderboard.json"
        )
        if not mirror_file.is_file():
            return {
                "rows": [],
                "source": str(mirror_file),
                "found": False,
            }
        try:
            data = json.loads(mirror_file.read_text())
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(
                status_code=500,
                detail=f"failed to parse mirror JSON: {exc}",
            ) from exc
        rows = list(data.get("rows") or [])[:limit]
        return {
            "rows": rows,
            "source": (
                str(mirror_file.relative_to(root))
                if mirror_file.is_relative_to(root)
                else str(mirror_file)
            ),
            "found": True,
        }

    @app.get("/api/telemetry/stream")
    async def api_telemetry_stream(request: Request) -> Any:
        """500 ms SSE stream — GPU% / temp / unified-mem / tok/s / TTFT.

        Subscribes via :class:`TelemetryHub`; unsubscribes (and stops the
        sampler if zero subscribers remain) when the client disconnects.
        """
        return EventSourceResponse(
            telemetry_event_stream(hub, request),
            # Keep the connection self-pinging so a sleepy proxy doesn't
            # tear the channel; payload-bearing telemetry events arrive
            # at the configured interval regardless.
            ping=15,
        )

    @app.post("/api/chat/stream")
    async def api_chat_stream(body: ChatRequest, request: Request) -> Any:
        """Single-lane chat against the resident brain — SSE.

        Resolves the lane from ``~/.hermes/config.yaml`` (spec §4.2 +
        Risk R8 — re-read every request so operator config edits take
        effect on the next turn). Persists user + assistant turns to
        ``chat_sessions`` + ``chat_turns`` (operator-private; spec §4.8
        — never mirrored). Wires :meth:`TelemetryHub.report_inflight` on
        stream start + done so the M3 gauge's tok/s + TTFT + lane chip
        light up.

        Emits these SSE events in order:

        - ``start`` ``{session_id, lane_id, model, base_url}``
        - ``token`` ``{channel: "reasoning"|"content", text: "..."}``
        - ``done``  ``{ttft_ms, tok_per_s, tokens_out, finish_reason,
          session_id, turn_id}``
        """
        resident = _read_hermes_lane()
        # v0.2 — a resident is only required when chatting the local resident
        # lane; on-demand local + OpenRouter lanes don't need it.
        lane_spec = getattr(body, "lane", "local:resident")
        needs_resident = lane_spec in ("", "local", "local:resident")
        if needs_resident and (not resident or not resident.get("base_url")):
            raise HTTPException(
                status_code=503,
                detail=(
                    "No resident brain in ~/.hermes/config.yaml — start a "
                    "lane and ensure model.base_url is set, or pick another model."
                ),
            )
        return EventSourceResponse(
            chat_event_stream(
                hub=hub,
                request=request,
                body=body,
                resident=resident,
                db_path=db_path,
            ),
            ping=15,
        )

    # ---- M5 — rubric registry + compare SSE + prefs ----

    @app.get("/api/rubrics")
    async def api_rubrics() -> dict[str, Any]:
        """Return the default rubric registry (3 entries today).

        Each entry carries an id, title, description, and a flat list of
        check kinds so the picker dropdown can render the right column
        shape under each side. Operator-supplied rubrics (M6+) layer on
        top via a separate directory walk; the default list is always
        the head.
        """
        from fieldkit.arena.rubrics import list_rubrics

        return {"rubrics": list_rubrics()}

    # ---- v0.3 — eval-prompt benches + reference-based scoring ----

    @app.get("/api/eval/benches")
    async def api_eval_benches() -> dict[str, Any]:
        """List the eval benches the cockpit can browse + score against.

        Each row carries its vertical, prompt count, families/scorers, the
        artifact slugs it maps to, and an ``available`` flag (false when the
        JSONL is absent on this machine). ``judge`` reports which judge
        backends are usable right now so the UI can disable OpenRouter when
        there's no key (and grey the local judge when there's no resident)."""
        from fieldkit.arena import benches as _benches

        return {
            "benches": _benches.list_benches(),
            "judge": _benches.judge_availability(_read_hermes_lane()),
        }

    @app.get("/api/eval/benches/{bench_id}/prompts")
    async def api_eval_prompts(
        bench_id: str,
        q: Optional[str] = None,
        family: Optional[str] = None,
        offset: int = 0,
        limit: int = 50,
    ) -> dict[str, Any]:
        """Paginated, filterable prompt list for one bench.

        ``q`` substring-filters the question; ``family`` filters patent rows.
        ``reference`` is included for display — the scoring path re-derives
        gold server-side from ``(bench_id, qid)`` and never trusts the client."""
        from fieldkit.arena import benches as _benches

        result = _benches.list_prompts(
            bench_id, q=q, family=family, offset=offset, limit=limit
        )
        if result is None:
            raise HTTPException(
                status_code=404,
                detail=(
                    f"bench {bench_id!r} not found or its files are absent under "
                    f"{_benches.ARENA_EVAL_BENCHES_ROOT} "
                    "(set ARENA_EVAL_BENCHES_ROOT)."
                ),
            )
        return result

    @app.get("/api/scout")
    async def api_scout() -> dict[str, Any]:
        """AE-10 — the newest hf-model-scout report as a Compare-pane projection.

        Surfaces the top-3 ranked base-model picks (with each one's license /
        chat-format / arch / Spark-envelope traps joined from ``candidates.json``)
        and the ruled-out table, so the scout decision is visible in the cockpit
        and frames the lock-time behavioral gate. ``{available: false}`` when no
        report is on disk (fresh box / no scout run yet). Pure read — no skill
        import (AE-R3), no GPU, no db."""
        proj = _scout_projection()
        return proj or {"available": False, "dir": str(_scout_dir())}

    @app.get("/api/eval/leaderboard")
    async def api_eval_leaderboard(include_cross_vertical: bool = False) -> dict[str, Any]:
        """Accuracy-per-(bench, model) rollup over persisted eval scores.

        ``mean_normalized`` averages the ``[0,1]``-scaled grades so
        deterministic (0/1) and judge (0-5) scorers share one axis. Own-bench
        rollups exclude cross-vertical runs by default."""
        from fieldkit.arena.store import ArenaStore

        db_file = Path(db_path).expanduser()
        rows: list[dict[str, Any]] = []
        if db_file.is_file():
            store = ArenaStore(db_file)
            with store:
                # Idempotent — adds the v0.3 eval_scores table to a pre-v0.3 DB
                # so the board reads cleanly before the first eval write.
                store.initialize()
                for r in store.eval_leaderboard(
                    include_cross_vertical=include_cross_vertical
                ):
                    rows.append(
                        {
                            "bench_id": r["bench_id"],
                            "lane_id": r["lane_id"],
                            "n_runs": r["n_runs"],
                            "mean_normalized": round(float(r["mean_normalized"]), 4),
                            "last_run_at": r["last_run_at"],
                        }
                    )
        return {"rows": rows, "include_cross_vertical": include_cross_vertical}

    @app.get("/api/leaderboard/live")
    async def api_leaderboard_live(include_chat: bool = True) -> dict[str, Any]:
        """Live cockpit leaderboard — aggregated on-the-fly from the compare +
        chat tables, no rebuild, no mirror. **Spark-local only**: the public
        mirror serves the curated static ``leaderboard.json`` via
        ``/api/leaderboard``; this endpoint surfaces the operator's live runs.

        Column-allowlisted by construction — the response dict copies only
        numeric metrics + ids + timestamps, so no prompt/content/reasoning ever
        leaves the box (same defense as ``/api/activity``). ``rev`` echoes the
        current telemetry ``leaderboard_rev`` so the client can dedupe."""
        from fieldkit.arena.store import ArenaStore

        db_file = Path(db_path).expanduser()
        rows: list[dict[str, Any]] = []
        if db_file.is_file():
            store = ArenaStore(db_file)
            with store:
                store.initialize()  # cold-DB safe — reads cleanly pre-first-run
                for r in store.leaderboard_live(include_chat=include_chat):
                    rows.append(
                        {
                            "bench_id": r["bench_id"],
                            "lane_id": r["lane_id"],
                            "manifest_slug": r.get("manifest_slug"),
                            "n_runs": r["n_runs"],
                            "mean_score": (
                                round(float(r["mean_score"]), 4)
                                if r["mean_score"] is not None
                                else None
                            ),
                            "median_tok_per_s": r.get("median_tok_per_s"),
                            "mean_ttft_ms": r.get("mean_ttft_ms"),
                            "human_pref_winrate": r.get("human_pref_winrate"),
                            "last_run_at": r["last_run_at"],
                        }
                    )
        return {"rows": rows, "rev": hub.leaderboard_rev, "now": _utc_now_iso()}

    @app.post("/api/chat/score")
    async def api_chat_score(body: ChatScoreRequest) -> dict[str, Any]:
        """Score a completed chat turn against a bench gold (or judge a free
        prompt for quality). Loads the persisted answer by ``turn_id``, scores,
        persists an ``eval_scores`` row when graded, and returns the score."""
        from fieldkit.arena import benches as _benches
        from fieldkit.arena.store import ArenaStore

        db_file = Path(db_path).expanduser()
        if not db_file.is_file():
            raise HTTPException(status_code=404, detail="no arena store yet")
        store = ArenaStore(db_file)
        store.initialize()
        try:
            turn = store.chat_turn(body.turn_id)
            if turn is None:
                raise HTTPException(status_code=404, detail=f"turn {body.turn_id} not found")
            predicted = turn["content"] or ""
            resident = _read_hermes_lane()
            judge_backend = body.judge.backend if body.judge else None
            judge_model = body.judge.model if body.judge else None

            if body.bench_id and body.eval_qid:
                result = _benches.score_eval_prediction(
                    body.bench_id,
                    body.eval_qid,
                    predicted,
                    judge_backend=judge_backend,
                    judge_model=judge_model,
                    resident=resident,
                )
                bench_id = body.bench_id
            elif body.judge is not None:
                result = _benches.score_free_prompt(
                    body.question or "",
                    predicted,
                    judge_backend=judge_backend,
                    judge_model=judge_model,
                    resident=resident,
                )
                bench_id = ""
            else:
                return {
                    "turn_id": body.turn_id,
                    "scored": False,
                    "reason": "no eval prompt and no judge backend requested",
                }

            if result.get("scored"):
                store.append_eval_score(
                    {
                        "bench_id": bench_id,
                        "qid": body.eval_qid or "",
                        "lane_id": body.lane_id or "",
                        "scorer_kind": result.get("scorer_kind") or "",
                        "score": result.get("score"),
                        "max_score": result.get("max") or 1.0,
                        "normalized": result.get("normalized"),
                        "reference": result.get("reference") or "",
                        "rationale": result.get("why") or "",
                        "judge_backend": result.get("judge_backend"),
                        "cross_vertical": 1 if body.cross_vertical else 0,
                        "source": "chat",
                        "source_id": str(body.turn_id),
                        "scored_at": _utc_now_iso(),
                    }
                )
                # A quality grade landed for a chat turn → nudge the live
                # boards to refetch on the next telemetry tick.
                hub.bump_leaderboard()
            result["turn_id"] = body.turn_id
            return result
        finally:
            store.close()

    @app.post("/api/compare/stream")
    async def api_compare_stream(
        body: CompareRequest, request: Request
    ) -> Any:
        """Side-by-side compare against the resident brain (A) and a
        configurable B-lane — SSE event sequence per spec §4.3.

        Default B is the OpenRouter frontier tier reached via the H6
        :class:`fieldkit.harness.CostRouterConfig`. Explicit two-local-lanes
        mode (``lane_b="local:<id>"``) is a v0.2 promotion — the M5
        surface emits a 400 when the second-local target isn't the
        resident (the single-brain envelope can't host two warm local
        lanes safely; per spec §4.9). Emits these SSE events in order:

        - ``start_a`` ``{run_id, lane_id, model, base_url, side: "A"}``
        - ``token_a`` ``{channel: "reasoning"|"content", text}``
        - ``done_a``  ``{ttft_ms, tok_per_s, tokens_out, finish_reason}``
        - ``swap`` ``{from, to}`` — only on explicit two-local-lanes mode
        - ``start_b`` ``{lane_id, model, base_url, side: "B"}``
        - ``token_b`` ``{channel, text}``
        - ``done_b``  ``{ttft_ms, tok_per_s, tokens_out, finish_reason}``
        - ``score`` ``{rubric_id, a: {total, checks: […]}, b: {…},
          deltas: {score, speed_tok_per_s}}``
        """
        resident = _read_hermes_lane()
        # v0.2 any-vs-any: a resident brain is only required when a side is
        # actually local. OpenRouter-vs-OpenRouter runs with no warm Spark lane.
        needs_local = any(
            not str(spec or "").startswith("openrouter")
            for spec in (
                getattr(body, "lane_a", "local:resident"),
                body.lane_b,
            )
        )
        if needs_local and (not resident or not resident.get("base_url")):
            raise HTTPException(
                status_code=503,
                detail=(
                    "No resident brain in ~/.hermes/config.yaml — start "
                    "a lane and ensure model.base_url is set, or pick "
                    "OpenRouter on both sides."
                ),
            )
        return EventSourceResponse(
            compare_event_stream(
                hub=hub,
                request=request,
                body=body,
                resident=resident,
                db_path=db_path,
            ),
            ping=15,
        )

    @app.get("/api/compare/options")
    async def api_compare_options() -> dict[str, Any]:
        """Selectable lanes for the compare duel — local + OpenRouter catalog.

        ``local`` lists the warm resident brain (the only live Spark lane).
        ``openrouter`` is the TTL-cached OpenRouter model catalog (or the
        curated priced fallback when there's no key / the fetch fails); each
        entry carries per-million prices so the client can preview cost and the
        meter can price the chosen model. ``has_key`` tells the UI whether
        OpenRouter lanes will actually stream or fall to the no-key stub."""
        resident = _read_hermes_lane()
        local: list[dict[str, Any]] = []
        if resident and resident.get("base_url"):
            local.append(
                {
                    "id": "local:resident",
                    "label": resident.get("model") or "resident brain",
                    "model": resident.get("model"),
                    "base_url": resident.get("base_url"),
                    "on_demand": False,
                    "warm": True,
                }
            )
        # On-demand article-series models — roster LlamaServerLane lanes whose
        # GGUF resolves on disk. Selecting one boots a llama-server for it
        # (single-slot OOM teardown) when the compare runs.
        try:
            from fieldkit.arena.store import ArenaStore

            db_file = Path(db_path).expanduser()
            if db_file.is_file():
                store = ArenaStore(db_file)
                with store:
                    seen: set[str] = set()
                    for row in store.lanes():
                        rid = row["id"]
                        if row["kind"] != "LlamaServerLane" or "::" not in rid:
                            continue
                        if rid in seen:
                            continue
                        slug, _, variant = rid.partition("::")
                        if _resolve_local_gguf(slug, variant) is None:
                            continue
                        seen.add(rid)
                        local.append(
                            {
                                "id": f"local:{rid}",
                                "label": f"{slug} · {variant}",
                                "model": rid,
                                "on_demand": True,
                                "warm": _LOCAL_SERVER_MANAGER.loaded_id == rid,
                            }
                        )
        except Exception as exc:  # noqa: BLE001
            _log.warning("compare-options roster scan failed: %s", exc)

        catalog = _openrouter_models_for_ui()
        curated = _curate_openrouter_models(catalog)

        def _mk(m: dict[str, Any], group: str) -> dict[str, Any]:
            return {
                "id": f"openrouter:{m['id']}",
                "model": m["id"],
                "label": m.get("name") or m["id"],
                "family": m.get("group_label"),
                "price_per_m_input_usd": m.get("price_per_m_input_usd"),
                "price_per_m_output_usd": m.get("price_per_m_output_usd"),
                "context_length": m.get("context_length"),
                "group": group,
            }

        openrouter_groups = {
            g: [_mk(m, g) for m in curated[g]]
            for g in ("frontier", "open", "project_base")
        }
        # Full catalog (escape hatch for the "show all" toggle).
        openrouter_all = [
            {
                "id": f"openrouter:{m['id']}",
                "model": m["id"],
                "label": m.get("name") or m["id"],
                "price_per_m_input_usd": m.get("price_per_m_input_usd"),
                "price_per_m_output_usd": m.get("price_per_m_output_usd"),
            }
            for m in catalog
        ]
        from fieldkit.arena import benches as _benches

        return {
            "local": local,
            "openrouter_groups": openrouter_groups,
            "openrouter": openrouter_all,
            "has_key": bool(os.environ.get("OPENROUTER_API_KEY")),
            "catalog_size": len(catalog),
            "live_catalog": bool(_openrouter_catalog()),
            "judge": _benches.judge_availability(resident),
        }

    @app.post("/api/local/load")
    async def api_local_load(body: LocalLoadRequest, request: Request) -> Any:
        """Pre-warm an on-demand local lane (SSE progress). Lets the compare
        picker load a model on the operator's click, before running a duel."""
        return EventSourceResponse(_local_load_stream(body.lane), ping=15)

    # ---- v0.1.1 — cockpit-density + chat-overhaul read endpoints ----

    @app.get("/api/activity")
    async def api_activity(
        limit: int = Query(default=8, ge=1, le=50),
    ) -> dict[str, Any]:
        """Redacted recent-events feed for the cockpit landing.

        Merges the last N rows from ``chat_sessions``, ``compare_runs``,
        and ``human_prefs`` into one ``ts``-DESC stream. Each event row is
        column-allowlisted at the store layer — **never** carries
        ``chat_turns.content`` / ``.reasoning``, ``compare_runs.prompt``,
        ``compare_responses.content`` / ``.reasoning``, or
        ``human_prefs.note``. Spec §4.2 / §4.8 + Risk R1 — operator
        privacy holds even on a sniffed loopback request.

        Returns ``{"events": [...], "now": "<ISO8601 UTC>"}``. Defensive
        on cold DB: returns ``{"events": []}`` instead of a 500 so the
        client never has to special-case startup.
        """
        from fieldkit.arena.store import ArenaStore

        db_file = Path(os.path.expanduser(db_path))
        if not db_file.is_file():
            return {"events": [], "now": _utc_now_iso()}

        events: list[dict[str, Any]] = []
        try:
            store = ArenaStore(db_file)
            with store:
                for row in store.recent_chat_sessions(limit=limit):
                    events.append(
                        {
                            "kind": "chat_session",
                            "ts": row["created_at"],
                            "session_id": row["id"],
                            "lane_id": row["lane_id"],
                            "turn_count": int(row["turn_count"] or 0),
                        }
                    )
                for row in store.recent_compare_runs(limit=limit):
                    events.append(
                        {
                            "kind": "compare_run",
                            "ts": row["created_at"],
                            "run_id": row["id"],
                            "lane_a_id": row["lane_a_id"],
                            "lane_b_id": row["lane_b_id"],
                            "rubric_id": row["rubric_id"],
                            "a_score": (
                                float(row["a_score"])
                                if row["a_score"] is not None
                                else None
                            ),
                            "b_score": (
                                float(row["b_score"])
                                if row["b_score"] is not None
                                else None
                            ),
                        }
                    )
                for row in store.recent_human_prefs(limit=limit):
                    events.append(
                        {
                            "kind": "human_pref",
                            "ts": row["created_at"],
                            "pref_id": row["id"],
                            "run_id": row["compare_run_id"],
                            "winner": row["winner"],
                        }
                    )
        except Exception as exc:  # noqa: BLE001 — feed is best-effort
            _log.warning("activity feed read failed: %s", exc)
            return {"events": [], "now": _utc_now_iso(), "error": str(exc)}

        # Sort merged events by ts DESC, then slice to ``limit``. Strings
        # are ISO8601 UTC so lex compare matches chronological order.
        events.sort(key=lambda e: e.get("ts") or "", reverse=True)
        return {"events": events[:limit], "now": _utc_now_iso()}

    @app.get("/api/chat/sessions")
    async def api_chat_sessions(
        limit: int = Query(default=8, ge=1, le=50),
    ) -> dict[str, Any]:
        """Redacted list of recent chat sessions for the switcher pill.

        Returns ``{"sessions": [{id, lane_id, created_at, turn_count,
        publishable}]}``. **Never** carries content/reasoning — the pill
        only needs metadata + a turn count to render the popover row.
        """
        from fieldkit.arena.store import ArenaStore

        db_file = Path(os.path.expanduser(db_path))
        if not db_file.is_file():
            return {"sessions": []}
        try:
            store = ArenaStore(db_file)
            with store:
                rows = store.recent_chat_sessions(limit=limit)
                return {
                    "sessions": [
                        {
                            "id": r["id"],
                            "lane_id": r["lane_id"],
                            "created_at": r["created_at"],
                            "turn_count": int(r["turn_count"] or 0),
                            "publishable": int(r["publishable"] or 0),
                        }
                        for r in rows
                    ]
                }
        except Exception as exc:  # noqa: BLE001
            _log.warning("chat sessions list failed: %s", exc)
            return {"sessions": [], "error": str(exc)}

    @app.get("/api/chat/sessions/{session_id}")
    async def api_chat_session_detail(session_id: str) -> dict[str, Any]:
        """Replay one session for the switcher pill's "load prior" click.

        Unlike :func:`api_chat_sessions` + :func:`api_activity`, this
        endpoint **does** include ``content`` + ``reasoning`` — the
        redaction contract is about *mirror export*, not about hiding
        the operator's own history from themselves. Loopback only;
        public-mirror clients short-circuit at
        :func:`isPublicMirrorHost` and never call this.
        """
        from fieldkit.arena.store import ArenaStore

        db_file = Path(os.path.expanduser(db_path))
        if not db_file.is_file():
            raise HTTPException(
                status_code=404,
                detail=f"session {session_id!r} not found",
            )
        store = ArenaStore(db_file)
        with store:
            session = store.chat_session(session_id)
            if session is None:
                raise HTTPException(
                    status_code=404,
                    detail=f"session {session_id!r} not found",
                )
            rows = store.chat_turns(session_id)
            turns = [
                {
                    "ord": int(r["ord"]),
                    "role": r["role"],
                    "content": r["content"],
                    "reasoning": r["reasoning"],
                    "tokens_out": (
                        int(r["tokens_out"])
                        if r["tokens_out"] is not None
                        else None
                    ),
                    "ttft_ms": (
                        float(r["ttft_ms"])
                        if r["ttft_ms"] is not None
                        else None
                    ),
                    "tok_per_s": (
                        float(r["tok_per_s"])
                        if r["tok_per_s"] is not None
                        else None
                    ),
                    "finish_reason": r["finish_reason"],
                }
                for r in rows
            ]
            return {
                "session_id": session["id"],
                "lane_id": session["lane_id"],
                "created_at": session["created_at"],
                "rubric_id": session["rubric_id"],
                "publishable": int(session["publishable"] or 0),
                "turns": turns,
            }

    @app.post("/api/prefs")
    async def api_prefs(body: PrefRequest) -> dict[str, Any]:
        """Record one operator thumbs verdict against a compare run.

        Spec §4.3 — **separate signal**: this writes a ``human_prefs`` row
        but does NOT mutate the corresponding ``rubric_scores.total``. The
        leaderboard surfaces the winrate only at ≥5 prefs per lane.
        Returns the row id + a count of prefs for the run (the picker UI
        uses the count to lock further clicks once the operator has
        voted).
        """
        from fieldkit.arena.schemas import HumanPrefRecord
        from fieldkit.arena.store import ArenaStore

        db_file = Path(os.path.expanduser(db_path))
        store = ArenaStore(db_file)
        store.initialize()
        try:
            run = store.compare_run(body.compare_run_id)
            if run is None:
                raise HTTPException(
                    status_code=404,
                    detail=f"compare_run_id {body.compare_run_id!r} not found",
                )
            import uuid

            pref_id = "hp-" + uuid.uuid4().hex[:12]
            store.append_human_pref(
                HumanPrefRecord(
                    id=pref_id,
                    compare_run_id=body.compare_run_id,
                    winner=body.winner,
                    note=body.note,
                    created_at=_utc_now_iso(),
                )
            )
            prefs = store.human_prefs_for_run(body.compare_run_id)
            return {
                "ok": True,
                "pref_id": pref_id,
                "compare_run_id": body.compare_run_id,
                "n_prefs": len(prefs),
            }
        finally:
            store.close()

    # ------------------------------------------------------------------
    # Lab notes (v0.2; operator-private, loopback-only, deterministic CRUD)
    # ------------------------------------------------------------------

    @app.get("/api/lab/notes")
    async def api_lab_notes(
        card_id: Optional[str] = Query(default=None),
        limit: int = Query(default=200, ge=1, le=500),
    ) -> dict[str, Any]:
        """List the operator's Lab annotations, newest first.

        Optionally scoped to one board card via ``?card_id=``. Returns
        ``{"notes": [{id, card_id, lane, body, created_at, updated_at}]}``.
        These rows DO carry ``body`` — like the chat-replay endpoint, the
        redaction contract is about *mirror export*, not hiding the
        operator's own notes from themselves; the ``LabNotes.jsx`` island
        short-circuits on a public-mirror host and never calls this.
        Defensive on cold DB (returns ``{"notes": []}`` not a 500).
        """
        from fieldkit.arena.store import ArenaStore

        db_file = Path(os.path.expanduser(db_path))
        if not db_file.is_file():
            return {"notes": []}
        try:
            store = ArenaStore(db_file)
            with store:
                rows = store.lab_notes(card_id=card_id, limit=limit)
                return {
                    "notes": [
                        {
                            "id": int(r["id"]),
                            "card_id": r["card_id"],
                            "lane": r["lane"],
                            "body": r["body"],
                            "created_at": r["created_at"],
                            "updated_at": r["updated_at"],
                        }
                        for r in rows
                    ]
                }
        except Exception as exc:  # noqa: BLE001 — best-effort read
            _log.warning("lab notes read failed: %s", exc)
            return {"notes": [], "error": str(exc)}

    @app.post("/api/lab/notes")
    async def api_lab_notes_create(body: LabNoteRequest) -> dict[str, Any]:
        """Pin one operator annotation to a Lab board card.

        Append-only deterministic insert. Returns the new note id +
        the refreshed count for the card so the island can lock/re-render.
        """
        from fieldkit.arena.store import ArenaStore

        db_file = Path(os.path.expanduser(db_path))
        store = ArenaStore(db_file)
        store.initialize()
        try:
            note_id = store.append_lab_note(
                {
                    "card_id": body.card_id,
                    "lane": body.lane,
                    "body": body.body,
                    "created_at": _utc_now_iso(),
                    "updated_at": None,
                }
            )
            n = len(store.lab_notes(card_id=body.card_id))
            return {"ok": True, "note_id": note_id, "card_id": body.card_id, "n_notes": n}
        finally:
            store.close()

    @app.delete("/api/lab/notes/{note_id}")
    async def api_lab_notes_delete(note_id: int) -> dict[str, Any]:
        """Delete one Lab note by id. 404 if it didn't exist."""
        from fieldkit.arena.store import ArenaStore

        db_file = Path(os.path.expanduser(db_path))
        if not db_file.is_file():
            raise HTTPException(status_code=404, detail="no notes")
        store = ArenaStore(db_file)
        store.initialize()
        try:
            removed = store.delete_lab_note(note_id)
            if not removed:
                raise HTTPException(status_code=404, detail=f"note {note_id} not found")
            return {"ok": True, "note_id": note_id}
        finally:
            store.close()

    # ------------------------------------------------------------------
    # M8 — control-plane jobs. Enqueue/inspect/cancel + an SSE board feed.
    # ``/api/jobs/stream`` is declared BEFORE ``/api/jobs/{job_id}`` so the
    # literal path isn't captured as a job id. ``jobs`` is OUT of the mirror
    # allowlist (R13) — these routes are the ONLY way the queue surfaces, and
    # they bind loopback (CORS) only.
    @app.get("/api/jobs")
    async def api_jobs_list(
        status: Optional[str] = Query(default=None, max_length=20),
        limit: int = Query(default=200, ge=1, le=1000),
    ) -> dict[str, Any]:
        """The jobs board read — newest first, optional status filter.

        Empty (not 404) when the store doesn't exist yet, so the cockpit
        paints an empty board instead of erroring on a fresh box."""
        from fieldkit.arena.store import ArenaStore

        db_file = Path(os.path.expanduser(db_path))
        if not db_file.is_file():
            return {"jobs": []}
        store = ArenaStore(db_file)
        store.initialize()
        try:
            rows = store.list_jobs(status=status, limit=limit)
            return {"jobs": [_job_to_public(r) for r in rows]}
        finally:
            store.close()

    @app.post("/api/jobs")
    async def api_jobs_create(
        body: JobCreateRequest, background_tasks: BackgroundTasks
    ) -> dict[str, Any]:
        """Enqueue a job; optionally drain the queue in the background (M8).

        Returns the new job id, or ``coalesced=True`` when an in-flight job
        already covers the same ``(kind, lane, bench)`` (R15 dedup gate)."""
        from fieldkit.arena import jobs as _jobs
        from fieldkit.arena.store import ArenaStore

        db_file = Path(os.path.expanduser(db_path))
        store = ArenaStore(db_file)
        store.initialize()
        try:
            job_id = _jobs.enqueue_job(
                store,
                body.kind,
                body.payload,
                trigger=body.trigger,
                priority=body.priority,
            )
        finally:
            store.close()
        if job_id is None:
            return {"ok": True, "coalesced": True, "job_id": None}
        # rl_run is async-only (LA-4 / RV-6): never drain the 8.5 h GRPO loop in
        # a request BackgroundTask — it drains under the M11 cron + RL arbiter.
        async_only = body.kind == "rl_run"
        if body.dispatch and not async_only:
            background_tasks.add_task(_drain_jobs_background, str(db_file))
        note = (
            "queued — drains under the autonomy cron (one lane at a time); "
            "arm it with `fieldkit arena autonomy on`"
            if async_only
            else None
        )
        return {
            "ok": True,
            "coalesced": False,
            "job_id": job_id,
            "async_only": async_only,
            "note": note,
        }

    @app.get("/api/jobs/stream")
    async def api_jobs_stream(request: Request) -> Any:
        """SSE board feed — emits a full jobs snapshot on connect + on change.

        Offline-safe by construction: on the public mirror there is no
        sidecar (and ``jobs`` is never exported), so the island falls back to
        an empty 'Cockpit offline' board."""
        return EventSourceResponse(
            jobs_event_stream(str(Path(os.path.expanduser(db_path))), request),
            ping=15,
        )

    @app.post("/api/jobs/check-regressions")
    async def api_jobs_check_regressions(
        background_tasks: BackgroundTasks,
        tau: Optional[float] = Query(default=None, ge=0.0, le=1.0),
        dispatch: bool = Query(default=True),
    ) -> dict[str, Any]:
        """Scan the live leaderboard for regressions and enqueue confirmations.

        The wired producer (M8-2): diffs ``eval_leaderboard()`` against the
        stored baseline, enqueues one ``leaderboard_regression`` ``eval_rerun``
        per over-tau accuracy drop (R15 dedup applies), then re-baselines. The
        first scan only sets the baseline. Operator-triggered today (a Jobs-page
        button); the Phase-2 cron calls the same path on a schedule. Declared
        before ``/api/jobs/{job_id}`` so the literal path isn't read as an id."""
        from fieldkit.arena import jobs as _jobs
        from fieldkit.arena.store import ArenaStore

        db_file = Path(os.path.expanduser(db_path))
        store = ArenaStore(db_file)
        store.initialize()
        try:
            kwargs = {} if tau is None else {"tau": tau}
            result = _jobs.check_and_enqueue_regressions(store, **kwargs)
        finally:
            store.close()
        if dispatch and result["enqueued"]:
            background_tasks.add_task(_drain_jobs_background, str(db_file))
        return {"ok": True, **result}

    @app.get("/api/jobs/{job_id}")
    async def api_jobs_get(job_id: str) -> dict[str, Any]:
        """One job by id (+ its trigger audit trail). 404 if unknown."""
        from fieldkit.arena.store import ArenaStore

        db_file = Path(os.path.expanduser(db_path))
        if not db_file.is_file():
            raise HTTPException(status_code=404, detail="no jobs")
        store = ArenaStore(db_file)
        store.initialize()
        try:
            row = store.get_job(job_id)
            if row is None:
                raise HTTPException(status_code=404, detail=f"job {job_id} not found")
            triggers = list(
                store.connect().execute(
                    "SELECT source, detail_json, created_at FROM job_triggers "
                    "WHERE job_id=? ORDER BY id",
                    [job_id],
                )
            )
            job = _job_to_public(row)
            job["triggers"] = [dict(t) for t in triggers]
            return job
        finally:
            store.close()

    @app.delete("/api/jobs/{job_id}")
    async def api_jobs_cancel(job_id: str) -> dict[str, Any]:
        """Cancel a not-yet-running job (queued/dispatched → skipped).

        A ``running`` job owns the GPU lane to completion (M8-5); 409 if it's
        past the point of safe cancellation, 404 if it never existed."""
        from fieldkit.arena.store import ArenaStore

        db_file = Path(os.path.expanduser(db_path))
        if not db_file.is_file():
            raise HTTPException(status_code=404, detail="no jobs")
        store = ArenaStore(db_file)
        store.initialize()
        try:
            if store.get_job(job_id) is None:
                raise HTTPException(status_code=404, detail=f"job {job_id} not found")
            if not store.cancel_job(job_id):
                raise HTTPException(
                    status_code=409,
                    detail=f"job {job_id} is past cancellation (running/done)",
                )
            return {"ok": True, "job_id": job_id, "status": "skipped"}
        finally:
            store.close()

    # ------------------------------------------------------------------
    # M10 (Bet 5 recall layer) — the knowledge / RAG pane API.
    # ------------------------------------------------------------------

    @app.get("/api/knowledge")
    async def api_knowledge(
        limit: int = Query(default=50, ge=1, le=200),
    ) -> dict[str, Any]:
        """The knowledge-pane snapshot: coverage · RAG-eval trend · recent
        re-index runs · source classes (M10-8/6).

        Degraded-safe: the coverage join needs pgvector (the live index) — if
        it's unreachable the ``coverage`` field is ``null`` with an ``index_note``,
        and the arena.db-backed trend + run history still render. The public
        mirror has no sidecar, so the island falls back to the static
        ``rag_eval_runs`` trend only (M10-10)."""
        from fieldkit.arena.store import ArenaStore
        from fieldkit.memory import SOURCE_CLASSES

        db_file = Path(os.path.expanduser(db_path))
        if not db_file.is_file():
            return {
                "coverage": None,
                "index_note": "arena.db not initialized",
                "rag_eval_runs": [],
                "reindex_runs": [],
                "source_classes": list(SOURCE_CLASSES),
            }
        store = ArenaStore(db_file)
        store.initialize()
        try:
            rag_rows = [dict(r) for r in store.rag_eval_runs(limit=limit)]
            reindex_rows = [dict(r) for r in store.reindex_runs(limit=limit)]
            coverage: Optional[dict[str, Any]] = None
            index_note: Optional[str] = None
            backfilled: Optional[dict[str, int]] = None
            try:
                from fieldkit.memory import MemoryIndex, coverage_report

                index = MemoryIndex()
                coverage = coverage_report(store, index)
                done, total = index.provenance_backfilled()
                backfilled = {"with_provenance": done, "total": total}
            except Exception as exc:  # noqa: BLE001 — degrade, never 500
                index_note = f"live index unavailable: {exc}"
            return {
                "coverage": coverage,
                "provenance_backfilled": backfilled,
                "index_note": index_note,
                "rag_eval_runs": rag_rows,
                "reindex_runs": reindex_rows,
                "source_classes": list(SOURCE_CLASSES),
            }
        finally:
            store.close()

    @app.post("/api/knowledge/reindex")
    async def api_knowledge_reindex(
        body: KnowledgeReindexRequest, background_tasks: BackgroundTasks
    ) -> dict[str, Any]:
        """Enqueue a ``reindex`` job (+ an optional chained ``rag_eval``), then
        drain in the background (M10-1). Returns the enqueued ids."""
        from fieldkit.arena import jobs as _jobs
        from fieldkit.arena.store import ArenaStore

        db_file = Path(os.path.expanduser(db_path))
        store = ArenaStore(db_file)
        store.initialize()
        try:
            payload: dict[str, Any] = {"source_set": body.source_set}
            if body.papers_json:
                payload["papers_json"] = body.papers_json
            reindex_id = _jobs.enqueue_job(
                store, _jobs.JobKind.REINDEX, payload, trigger="operator"
            )
            rag_id = None
            if body.rag_eval:
                rag_id = _jobs.enqueue_job(
                    store, _jobs.JobKind.RAG_EVAL, {}, trigger="operator",
                    dedup_key="", priority=0,
                )
        finally:
            store.close()
        if body.dispatch:
            background_tasks.add_task(_drain_jobs_background, str(db_file))
        return {"ok": True, "reindex_job_id": reindex_id, "rag_eval_job_id": rag_id}

    @app.post("/api/knowledge/rag-eval")
    async def api_knowledge_rag_eval(
        background_tasks: BackgroundTasks, dispatch: bool = Query(default=True)
    ) -> dict[str, Any]:
        """Enqueue a standalone ``rag_eval`` scoring job over the live index
        (M10-6). The promotion gate compares it like-for-like against the prior
        cosine-only score."""
        from fieldkit.arena import jobs as _jobs
        from fieldkit.arena.store import ArenaStore

        db_file = Path(os.path.expanduser(db_path))
        store = ArenaStore(db_file)
        store.initialize()
        try:
            job_id = _jobs.enqueue_job(
                store, _jobs.JobKind.RAG_EVAL, {}, trigger="operator", dedup_key=""
            )
        finally:
            store.close()
        if dispatch:
            background_tasks.add_task(_drain_jobs_background, str(db_file))
        return {"ok": True, "rag_eval_job_id": job_id}

    @app.post("/api/knowledge/query")
    async def api_knowledge_query(body: KnowledgeQueryRequest) -> dict[str, Any]:
        """The operator's provenance-filtered query console (M10-4/9).

        Returns chunk text + provenance — OPERATOR-PRIVATE (served live only,
        never mirrored). Needs the live index (pgvector + embedder); 503 if the
        index is unreachable so the pane can show a clear 'index offline' state."""
        from fieldkit.memory import MemoryError as _MemErr
        from fieldkit.memory import MemoryIndex

        try:
            index = MemoryIndex()
            hits = index.query(
                body.query, top_k=body.top_k, sources=body.provenance
            )
        except _MemErr as exc:
            raise HTTPException(status_code=503, detail=f"index unavailable: {exc}")
        return {"query": body.query, "provenance": body.provenance, "hits": hits}

    # ------------------------------------------------------------------
    # M11 (autonomous harness) — the morning-standup render (AH-3).
    # ------------------------------------------------------------------

    @app.get("/api/standup")
    async def api_standup(
        cap_usd: Optional[float] = Query(default=None, ge=0.0),
    ) -> dict[str, Any]:
        """The morning-standup snapshot: **Ran / Regressed / Queued / Spend** (AH-3).

        A read-only render over the existing ``jobs`` / ``leaderboard_baseline`` /
        M9 cost rows — it does NOT drain (the overnight cron owns dispatch; an
        HTTP GET never launches a GPU lane). Stage-only by construction: no push
        path, no per-run prompt, no per-run cost (R26). The Spend row degrades to
        "—" when the M9 cost plane is absent (AH-5). Empty (not 404) on a fresh
        box so the pane paints a clean standup. Declared before the static mount
        so ``/arena/standup`` (the page) and ``/api/standup`` (this) stay distinct.
        """
        from fieldkit.arena.scheduler import build_standup
        from fieldkit.arena.store import ArenaStore
        from fieldkit.budget import BudgetGovernor

        db_file = Path(os.path.expanduser(db_path))
        if not db_file.is_file():
            return {
                "generated_at": None,
                "ran": [],
                "failed": [],
                "regressed": [],
                "queued": [],
                "spend": {"display": "—", "has_cost_plane": False},
                "counts": {"ran": 0, "failed": 0, "regressed": 0, "queued": 0},
                "staged_only": True,
                "note": "arena.db not initialized",
            }
        store = ArenaStore(db_file)
        store.initialize()
        try:
            # The cost ledger reads the same db (M9 soft prereq, AH-5); the
            # governor supplies the Spend row's $/cap. No drain, no dispatch.
            governor = BudgetGovernor(ledger=store)
            return build_standup(store, governor=governor, cap_usd=cap_usd)
        finally:
            store.close()

    @app.get("/api/reward-signal")
    async def api_reward_signal(
        source: str | None = Query(default=None),
    ) -> dict[str, Any]:
        """The eval-is-reward gauge (dogfood AF-3/AF-9): extract-rate / reward-rate
        / AV-R1 truncation over a verifier run, with a run-history selector.

        A read-only render of a reward-signal report JSON — today the **AV-10
        preflight** (`scripts/astro_bench/preflight_av10.py` →
        ``evidence/astrodynamics/av10-preflight*.json``), the step-0 zero of the
        RLVR lineage delta. The same shape (boxed/extract/reward/truncation +
        per-row buckets) is what the C5 per-step RLVR gauge will emit, so the pane
        is reusable.

        **History + auto-follow (AF-9):** every response carries ``runs`` — a
        newest-first summary of all ``av10-preflight*.json`` reports (source,
        mtime, model, budget, status, gate) — so the pane renders a dropdown. The
        displayed report is chosen by precedence: an explicit ``?source=<file>``
        (a prior run picked from the dropdown, traversal-sanitized to the evidence
        dir) → the ``FK_ARENA_REWARD_SIGNAL`` env pin → else the **newest by
        mtime** (so with no selection the gauge tracks a live run, which rewrites
        its file every row, and any later run automatically). The chosen file's
        name is returned as ``source``. No arena.db read, no schema bump
        (AH-9/RV-8); ``{available: false}`` (still with ``runs``) when no report
        exists yet so the pane paints a clean empty state. Declared before the
        static mount so ``/arena/reward`` (page) and ``/api/reward-signal`` stay
        distinct."""
        runs = _list_reward_reports(root)
        if source:
            report_path = _resolve_reward_report(root, source)  # None if invalid
        elif os.environ.get("FK_ARENA_REWARD_SIGNAL"):
            report_path = Path(os.path.expanduser(os.environ["FK_ARENA_REWARD_SIGNAL"]))
        else:
            report_path = _newest_reward_report(root)
        if report_path is None or not report_path.is_file():
            return {"available": False, "kind": "preflight", "runs": runs}
        try:
            report = json.loads(report_path.read_text())
        except (OSError, ValueError):
            return {"available": False, "kind": "preflight", "runs": runs}
        return {
            "available": True, "kind": "preflight",
            "report": report, "source": report_path.name, "runs": runs,
        }

    @app.get("/api/sft-progress")
    async def api_sft_progress(
        source: str | None = Query(default=None),
    ) -> dict[str, Any]:
        """Live SFT-training feed (dogfood AF — closes the AF-2 blind spot for the
        SFT stage). Parses a NeMo ``p65`` driver log + run-dir and renders
        iter/max, the loss curve, iter/s, ETA, and peak GPU memory — the
        training-stage analogue of the ``rl_run`` progress strip, so the operator
        can watch a ``TrainRecipe(backend="nemo")`` run (astrodynamics C2(b))
        side-by-side instead of tailing a log.

        Read-only: an HTTP GET parses a log; it never launches a lane. The SFT
        run-root is OUTSIDE the repo (the trainer writes to ``/home/nvidia/data``)
        so it is anchored by ``FK_ARENA_SFT_DIR`` (default the astrodynamics
        run-root). History + auto-follow mirror ``/api/reward-signal``: every
        response carries ``runs`` (the driver logs found, newest-first); the shown
        log is ``?source=`` (traversal-sanitized) → else newest by mtime, so with
        no selection the feed tracks the live run. ``{available: false}`` (still
        with ``runs``) paints a clean empty state. Declared before the static
        mount so ``/arena/sft`` (page) and ``/api/sft-progress`` stay distinct.
        No arena.db read, no schema bump."""
        sft_dir = _sft_run_dir()
        runs = _list_sft_runs(sft_dir)
        log_path = (
            _resolve_sft_log(sft_dir, source) if source else _newest_sft_log(sft_dir)
        )
        if log_path is None or not log_path.is_file():
            return {"available": False, "kind": "sft", "runs": runs}
        report = _parse_sft_log(log_path, sft_dir)
        if report is None:
            return {"available": False, "kind": "sft", "runs": runs}
        return {
            "available": True, "kind": "sft",
            "report": report, "source": log_path.name, "runs": runs,
        }

    @app.get("/api/corpus-progress")
    async def api_corpus_progress(
        source: str | None = Query(default=None),
    ) -> dict[str, Any]:
        """Live corpus-synth feed (AE-6 / AF-2 — closes the C1 corpus blind spot).

        The corpus-synth skill writes SFT-init rows in-CC-session (Edit-append to
        ``out.jsonl`` against a deterministic ``queue.jsonl``); the control plane
        never saw it — the "#1 immediate win" in the dogfood ledger. The producer
        stamps a ``corpus-progress-<slug>.json`` heartbeat
        (``fieldkit.arena.lane.write_corpus_progress``) into the dir this endpoint
        auto-follows; the response carries ``written/target``, the batch verify
        tally, the accumulating tier/topic ``family_mix``, and the ETA-in-batches
        — the corpus-stage analogue of the ``rl_run`` / SFT progress strip.

        Read-only: an HTTP GET reads a JSON file; it never launches a lane and
        never imports skill code (AE-R3). History + auto-follow mirror
        ``/api/sft-progress``: ``runs`` lists every heartbeat newest-first; the
        shown one is ``?source=`` (traversal-sanitized) → else newest by mtime.
        ``{available: false}`` paints a clean empty state. No arena.db read."""
        runs = _list_corpus_runs(root)
        report_path = (
            _resolve_corpus_report(root, source)
            if source
            else _newest_corpus_report(root)
        )
        if report_path is None or not report_path.is_file():
            return {"available": False, "kind": "corpus", "runs": runs}
        report = _parse_corpus_report(report_path)
        if report is None:
            return {"available": False, "kind": "corpus", "runs": runs}
        return {
            "available": True, "kind": "corpus",
            "report": report, "source": report_path.name, "runs": runs,
        }

    @app.get("/api/build")
    async def api_build() -> dict[str, Any]:
        """The vertical-build spine (AE-5 / AF-1): C1..C6 stage cards.

        Assembles eight stage cards (scout · bench · corpus · SFT · smoke · lane
        · RLVR · publish) — each with a state, a headline metric, and the
        operator gate — from the signals the cockpit ALREADY has (the SFT log
        feed, the reward report, the bench registry, the ``rl_run`` rows, the
        lane arbiter) plus an optional operator-authored ``build-manifest.json``
        (``FK_ARENA_BUILD_DIR``) for the no-live-feed stages + the gate text.

        Read-only by construction: an HTTP GET reads files + lists rows; it never
        launches a lane. **No arena.db schema change** (no write, no new table)
        and **no skill imports** (AE-R3) — the spine is a pure projection over
        existing feeds. On the public mirror there is no sidecar, so the island
        renders a static note. Declared before the static mount so ``/arena/build``
        (page) and ``/api/build`` stay distinct."""
        return _assemble_build(root, db_path)

    @app.get("/api/bench-provenance")
    async def api_bench_provenance() -> dict[str, Any]:
        """Bench provenance card (AE-8 / AF-4): version · pool/held-out counts ·
        RV-10 disjointness · tier/topic mix · self-verifying golds · corpus
        held-out-exclusion proof.

        A pure projection over the bench JSONL the vertical ships
        (``FK_ARENA_BENCH_DIR``, default the build-manifest/evidence dir) — no
        bench registry, no skill import (AE-R3), no arena.db read. The same
        provenance also rides the ``/api/build`` bench stage (lights the card);
        this standalone route folds into AE-11's Eval preview. ``{available:
        false}`` paints a clean empty state when no bench pair is on disk."""
        manifest = _load_build_manifest(root)
        prov = _bench_provenance(root, manifest)
        return prov or {"available": False, "kind": "bench"}

    # ------------------------------------------------------------------
    # Packaged web UI (P7 distribution) — serve the baked Orionfold Arena
    # bundle at /arena/ when it shipped in the wheel. Same-origin with the
    # API (page + sidecar both on :7866), so the islands' resolveSidecarUrl()
    # resolves to their own origin and no CORS is needed post-install. Guarded:
    # a fieldkit installed without `fieldkit arena build` having baked _webui/
    # degrades silently to API-only mode (today's behavior). The mount goes
    # last so it never shadows /api/* or /healthz.
    _mount_packaged_webui(app)

    return app


def _reward_reports_dir(root: Path) -> Path:
    """Directory holding the reward-signal report JSONs (AF-3/AF-9)."""
    return root / "evidence" / "astrodynamics"


def _newest_reward_report(root: Path) -> Path:
    """The most-recent ``av10-preflight*.json`` by mtime (AF-9 auto-follow).

    A live run rewrites its file after every row, so it stays freshest while
    running and after it finishes; a later run to a new filename becomes newest
    automatically — no manual repointing. Falls back to the canonical
    ``av10-preflight.json`` when nothing matches (fresh box)."""
    base = _reward_reports_dir(root)
    canonical = base / "av10-preflight.json"
    try:
        candidates = sorted(
            base.glob("av10-preflight*.json"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
    except OSError:
        return canonical
    return candidates[0] if candidates else canonical


def _resolve_reward_report(root: Path, source: str) -> Path | None:
    """Resolve a dropdown-selected report filename to a path, traversal-safe.

    ``Path(source).name`` strips any directory components, and the name must be
    an ``av10-preflight*.json`` that actually exists in the evidence dir — so a
    crafted ``../../`` source can never escape it. Returns None if invalid."""
    name = Path(source).name
    if not name.startswith("av10-preflight") or not name.endswith(".json"):
        return None
    p = _reward_reports_dir(root) / name
    return p if p.is_file() else None


def _list_reward_reports(root: Path) -> list:
    """Newest-first summaries of every reward report (AF-9 history dropdown).

    One small dict per ``av10-preflight*.json`` — enough to label the dropdown
    (budget · status · gate) without the caller fetching each full report."""
    base = _reward_reports_dir(root)
    out: list = []
    try:
        paths = sorted(
            base.glob("av10-preflight*.json"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
    except OSError:
        return out
    for p in paths:
        try:
            mtime = p.stat().st_mtime
        except OSError:
            continue
        item: dict[str, Any] = {"source": p.name, "mtime": mtime}
        try:
            r = json.loads(p.read_text())
            item.update({
                "model": r.get("model"),
                "max_new_tokens": r.get("max_new_tokens"),
                "status": r.get("status", "done"),
                "scored": r.get("scored"),
                "total": r.get("total", r.get("n")),
                "gate_pass": r.get("gate_pass"),
                "boxed_rate": r.get("boxed_rate"),
            })
        except (OSError, ValueError):
            item["status"] = "unreadable"
        out.append(item)
    return out


# ---------------------------------------------------------------------------
# SFT-progress feed (dogfood AF — live NeMo p65 training feed; AF-2 blind spot)
# ---------------------------------------------------------------------------

# One Megatron iter line, e.g.:
#   iteration  7/  100 | consumed samples: 112 | elapsed time per iteration
#   (ms): 4190.1 | learning rate: ... | global batch size: 16 | lm loss:
#   9.79E-01 | ...
# `.` doesn't cross newlines, so each match stays within a single iter line.
_SFT_ITER_RE = re.compile(
    r"iteration\s+(\d+)/\s*(\d+).*?elapsed time per iteration \(ms\):\s*"
    r"([\d.]+).*?lm loss:\s*([\d.eE+-]+)"
)
_SFT_MEM_RE = re.compile(r"mem-max-reserved-gigabytes:\s*([\d.]+)")

# Driver logs that are NOT training runs (no iter lines) — the merge/export
# stage shares the run-root's logs/ dir but isn't an SFT-feed run, so it's kept
# out of the auto-follow + history dropdown.
_SFT_SKIP_LOGS = frozenset({"merge-driver.log"})


def _sft_training_logs(base: Path) -> list[Path]:
    """All training driver logs in ``base``, newest-first (merge logs excluded)."""
    try:
        cands = [p for p in base.glob("*-driver.log") if p.name not in _SFT_SKIP_LOGS]
    except OSError:
        return []
    return sorted(cands, key=lambda p: p.stat().st_mtime, reverse=True)


def _sft_run_dir() -> Path:
    """Run-root holding the NeMo SFT driver logs + ``runs-*`` checkpoints.

    External to the repo (the trainer writes to ``/home/nvidia/data``), so it is
    env-anchored via ``FK_ARENA_SFT_DIR`` with the astrodynamics default."""
    return Path(
        os.path.expanduser(
            os.environ.get(
                "FK_ARENA_SFT_DIR",
                "/home/nvidia/data/astro-train-lora/p65-nemo",
            )
        )
    )


def _sft_logs_dir(sft_dir: Path) -> Path:
    return sft_dir / "logs"


def _newest_sft_log(sft_dir: Path) -> Path | None:
    """Most-recent training driver log by mtime (auto-follow the live run)."""
    cands = _sft_training_logs(_sft_logs_dir(sft_dir))
    return cands[0] if cands else None


def _resolve_sft_log(sft_dir: Path, source: str) -> Path | None:
    """Resolve a dropdown-selected driver log, traversal-safe."""
    name = Path(source).name
    if not name.endswith("-driver.log") or name in _SFT_SKIP_LOGS:
        return None
    p = _sft_logs_dir(sft_dir) / name
    return p if p.is_file() else None


def _sft_run_subdir(log_name: str) -> str:
    """``full-driver.log`` → ``runs-full``; ``smoke-driver.log`` → ``runs-smoke``."""
    stem = log_name[: -len("-driver.log")]
    return f"runs-{stem}"


def _sft_checkpoints(log_path: Path, sft_dir: Path) -> list[int]:
    run_dir = sft_dir / _sft_run_subdir(log_path.name)
    out: list[int] = []
    try:
        for d in run_dir.glob("iter_*"):
            parts = d.name.split("_")
            if d.is_dir() and len(parts) == 2 and parts[1].isdigit():
                out.append(int(parts[1]))
    except OSError:
        pass
    return sorted(out)


def _parse_sft_log(log_path: Path, sft_dir: Path) -> dict[str, Any] | None:
    """Parse one NeMo driver log into the SFT-progress report shape.

    Returns iter/max, the loss curve (downsampled), recent iter/s, ETA, and peak
    GPU memory. Before the first iter line it returns an ``init``/``starting``
    status so the pane can paint the setup phase (model load + optimizer setup
    take ~40 s on the GB10). ``None`` only on unreadable file."""
    try:
        text = log_path.read_text(errors="replace")
    except OSError:
        return None
    label = f"NeMo p65 LoRA SFT — {log_path.name[: -len('-driver.log')]}"
    iters: list[tuple[int, int, float, float]] = []
    for m in _SFT_ITER_RE.finditer(text):
        iters.append(
            (int(m.group(1)), int(m.group(2)), float(m.group(3)), float(m.group(4)))
        )
    peak_mem = 0.0
    for mm in _SFT_MEM_RE.finditer(text):
        peak_mem = max(peak_mem, float(mm.group(1)))
    checkpoints = _sft_checkpoints(log_path, sft_dir)

    if not iters:
        started = "Starting training loop" in text
        return {
            "status": "starting" if started else "init",
            "latest_iter": 0,
            "max_iters": 0,
            "first_loss": None,
            "last_loss": None,
            "loss_series": [],
            "iter_per_s": None,
            "eta_s": None,
            "peak_mem_gb": round(peak_mem, 1),
            "checkpoints": checkpoints,
            "run_label": label,
        }

    max_iters = iters[-1][1]
    latest_iter = iters[-1][0]
    first_loss = iters[0][3]
    last_loss = iters[-1][3]
    # iter/s + ETA from the last ~10 iters (the first carries warmup cost).
    recent = iters[-10:] if len(iters) > 1 else iters
    recent_ms = [e for (_i, _m, e, _l) in recent if e > 0]
    mean_ms = sum(recent_ms) / len(recent_ms) if recent_ms else None
    iter_per_s = (1000.0 / mean_ms) if mean_ms else None
    remaining = max(0, max_iters - latest_iter)
    eta_s = (remaining * mean_ms / 1000.0) if mean_ms else None
    done = "[after training is done]" in text
    status = "done" if (done or latest_iter >= max_iters) else "running"
    series = [{"iter": i, "loss": round(loss, 4)} for (i, _m, _e, loss) in iters]
    if len(series) > 60:
        step = len(series) // 60 + 1
        series = series[::step] + [series[-1]]
    return {
        "status": status,
        "latest_iter": latest_iter,
        "max_iters": max_iters,
        "first_loss": round(first_loss, 4),
        "last_loss": round(last_loss, 4),
        "loss_series": series,
        "iter_per_s": round(iter_per_s, 3) if iter_per_s else None,
        "eta_s": round(eta_s, 1) if eta_s is not None else None,
        "peak_mem_gb": round(peak_mem, 1),
        "checkpoints": checkpoints,
        "run_label": label,
    }


def _list_sft_runs(sft_dir: Path) -> list:
    """Newest-first summaries of every SFT training driver log (dropdown)."""
    out: list = []
    paths = _sft_training_logs(_sft_logs_dir(sft_dir))
    for p in paths:
        rep = _parse_sft_log(p, sft_dir) or {}
        out.append(
            {
                "source": p.name,
                "status": rep.get("status"),
                "latest_iter": rep.get("latest_iter"),
                "max_iters": rep.get("max_iters"),
                "last_loss": rep.get("last_loss"),
            }
        )
    return out


# ---------------------------------------------------------------------------
# Corpus-synth live feed (AE-6 / AF-2) — the consumer side of the heartbeat
# ---------------------------------------------------------------------------
#
# The producer is the claude-corpus-synth skill, which stamps a
# ``corpus-progress-<slug>.json`` heartbeat via
# ``fieldkit.arena.lane.write_corpus_progress`` after each batch. The cockpit
# only polls that file (AE-R3: never imports skill code) — exactly the AF-9
# reward / AF-10 SFT auto-newest transport, one dir over.


def _corpus_reports_dir(root: Path) -> Path:
    """Dir holding the corpus heartbeat JSONs (env ``FK_ARENA_CORPUS_DIR``).

    Defaults to the same ``evidence/astrodynamics`` dir the reward + SFT feeds
    use, so one vertical's build signals sit together (mirrors the producer's
    ``lane._corpus_signal_dir``)."""
    env = os.environ.get("FK_ARENA_CORPUS_DIR")
    if env:
        return Path(os.path.expanduser(env))
    return root / "evidence" / "astrodynamics"


def _newest_corpus_report(root: Path) -> Path | None:
    """The most-recent ``corpus-progress*.json`` by mtime (auto-follow the live
    synth); ``None`` when no run has stamped a heartbeat yet."""
    base = _corpus_reports_dir(root)
    try:
        cands = sorted(
            base.glob("corpus-progress*.json"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
    except OSError:
        return None
    return cands[0] if cands else None


def _resolve_corpus_report(root: Path, source: str) -> Path | None:
    """Resolve a dropdown-selected heartbeat filename to a path, traversal-safe."""
    name = Path(source).name
    if not name.startswith("corpus-progress") or not name.endswith(".json"):
        return None
    p = _corpus_reports_dir(root) / name
    return p if p.is_file() else None


def _parse_corpus_report(path: Path) -> dict[str, Any] | None:
    """Read one corpus heartbeat into the feed shape (mostly passthrough + a
    derived ``pct``). ``None`` only on an unreadable / non-dict file."""
    try:
        r = json.loads(path.read_text())
    except (OSError, ValueError):
        return None
    if not isinstance(r, dict):
        return None
    written = r.get("written") or 0
    target = r.get("target")
    pct = (
        min(100, round(written / target * 100))
        if isinstance(target, (int, float)) and target
        else None
    )
    return {
        "status": r.get("status") or "running",
        "written": written,
        "target": target,
        "pct": pct,
        "verified": r.get("verified"),
        "verify_fail": r.get("verify_fail"),
        "batch_size": r.get("batch_size"),
        "batches_done": r.get("batches_done"),
        "eta_batches": r.get("eta_batches"),
        "family_mix": r.get("family_mix") or {},
        "last_batch": r.get("last_batch"),
        "run_label": r.get("run_label"),
        "vertical": r.get("vertical"),
    }


def _list_corpus_runs(root: Path) -> list:
    """Newest-first summaries of every corpus heartbeat (history dropdown)."""
    base = _corpus_reports_dir(root)
    out: list = []
    try:
        paths = sorted(
            base.glob("corpus-progress*.json"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
    except OSError:
        return out
    for p in paths:
        rep = _parse_corpus_report(p) or {}
        out.append(
            {
                "source": p.name,
                "status": rep.get("status"),
                "written": rep.get("written"),
                "target": rep.get("target"),
                "run_label": rep.get("run_label"),
            }
        )
    return out


# ---------------------------------------------------------------------------
# Build spine (AE-5 / AF-1) — the vertical-build pipeline as C1..C6 stage cards
# ---------------------------------------------------------------------------
#
# The /arena/build/ pane's data source — the spine that frames the dogfood
# enhancements. Assembles eight stage cards (scout · bench · corpus · SFT ·
# smoke · lane · RLVR · publish) from the signals the cockpit ALREADY has — the
# SFT log feed, the reward report, the bench registry, the rl_run job rows, the
# lane arbiter — plus an optional, operator-authored ``build-manifest.json`` for
# the stages with no live feed (scout / corpus / publish) and the human-gate
# annotations. No arena.db schema change, no skill imports (AE-R3): every signal
# is a file the sidecar already reads or a row it already lists. Read-only — an
# HTTP GET assembles state; it never launches a lane.


def _build_manifest_dir(root: Path) -> Path:
    """Dir holding the optional ``build-manifest.json`` (AE-5).

    Env-anchored (``FK_ARENA_BUILD_DIR``) with the astrodynamics evidence dir as
    default — the same place the reward reports live, so one vertical's build
    state sits together."""
    env = os.environ.get("FK_ARENA_BUILD_DIR")
    if env:
        return Path(os.path.expanduser(env))
    return _reward_reports_dir(root)


def _load_build_manifest(root: Path) -> dict[str, Any]:
    """Read ``build-manifest.json`` if present, else ``{}`` (best-effort).

    The manifest is the operator's hand for the stages with no live feed
    (scout / corpus / publish) and for the human-gate text on every stage. It is
    never required — with no manifest the pane still renders the live stages off
    their existing feeds."""
    path = _build_manifest_dir(root) / "build-manifest.json"
    try:
        if path.is_file():
            data = json.loads(path.read_text())
            if isinstance(data, dict):
                return data
    except (OSError, ValueError) as exc:
        _log.debug("build-manifest read failed: %s", exc)
    return {}


# ---------------------------------------------------------------------------
# Bench provenance (AE-8 / AF-4) — the eval substrate's pedigree as a card
# ---------------------------------------------------------------------------
#
# The Cortex-pane card pattern applied to the bench: version · pool/held-out
# counts · RV-10 disjointness · tier/topic mix · self-verifying-gold count ·
# corpus held-out-exclusion. A PURE read of the JSONL the bench already ships
# (pool + held-out splits + the SFT-init queue) — no registry, no skill import
# (AE-R3), no arena.db read. It threads into the build-spine bench stage (lights
# the card live) and stands alone at /api/bench-provenance for AE-11's preview.


def _bench_dir(root: Path) -> Path:
    """Dir holding the bench pool + held-out JSONL (env ``FK_ARENA_BENCH_DIR``).

    Defaults to the build-manifest dir (the evidence dir) so the bench splits sit
    with the rest of the vertical's build signals (reward / SFT / corpus feeds)."""
    env = os.environ.get("FK_ARENA_BENCH_DIR")
    if env:
        return Path(os.path.expanduser(env))
    return _build_manifest_dir(root)


_BENCH_VERSION_RE = re.compile(r"v\d+(?:\.\d+)*")


def _bench_split_files(d: Path) -> tuple[Path, Path] | None:
    """The (pool, held-out) JSONL pair: the newest ``*.heldout.jsonl`` + its
    sibling pool (same name, ``.heldout`` dropped). ``None`` when absent."""
    try:
        heldouts = sorted(
            d.glob("*.heldout.jsonl"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
    except OSError:
        return None
    if not heldouts:
        return None
    heldout = heldouts[0]
    pool = heldout.with_name(heldout.name.replace(".heldout.jsonl", ".jsonl"))
    if not pool.is_file():
        return None
    return pool, heldout


def _read_jsonl_prompts(path: Path) -> tuple[list[dict[str, Any]], set[str]]:
    """Parse a bench/queue JSONL → (rows, prompt-set). Best-effort per line."""
    rows: list[dict[str, Any]] = []
    prompts: set[str] = set()
    try:
        text = path.read_text()
    except OSError:
        return rows, prompts
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except ValueError:
            continue
        if isinstance(obj, dict):
            rows.append(obj)
            p = obj.get("prompt")
            if isinstance(p, str):
                prompts.add(p)
    return rows, prompts


def _bench_provenance(
    root: Path, manifest: dict[str, Any] | None = None
) -> dict[str, Any] | None:
    """Provenance projection over the on-disk bench (AE-8).

    Reads the pool + held-out splits (and the SFT-init queue, if present) and
    derives: version, pool/held-out counts, RV-10 disjointness (pool ∩ held-out),
    tier/topic mix, the count of golds carrying a precomputed SI value (the
    on-disk evidence of the generator's self-verify invariant), and the corpus
    held-out-exclusion proof (queue ∩ held-out). ``None`` when no bench pair is on
    disk. No registry, no skill import (AE-R3)."""
    d = _bench_dir(root)
    pair = _bench_split_files(d)
    if pair is None:
        return None
    pool_path, heldout_path = pair
    pool_rows, pool_prompts = _read_jsonl_prompts(pool_path)
    held_rows, held_prompts = _read_jsonl_prompts(heldout_path)
    if not pool_rows and not held_rows:
        return None
    overlap = len(pool_prompts & held_prompts)
    all_rows = pool_rows + held_rows
    tier_mix: dict[str, int] = {}
    topic_mix: dict[str, int] = {}
    golds_with_si = 0
    rel: float | None = None
    for r in all_rows:
        t = r.get("tier")
        if t is not None:
            tier_mix[str(t)] = tier_mix.get(str(t), 0) + 1
        topic = r.get("topic")
        if isinstance(topic, str):
            topic_mix[topic] = topic_mix.get(topic, 0) + 1
        gv = r.get("gold_value_si")
        if isinstance(gv, (int, float)) and not isinstance(gv, bool) and gv == gv:
            golds_with_si += 1
        rt = r.get("rel_tol")
        if rel is None and isinstance(rt, (int, float)) and not isinstance(rt, bool):
            rel = float(rt)
    # Corpus held-out-exclusion proof: the SFT-init queue's prompts must be
    # disjoint from the held-out split (RV-10) — a wrong answer can't trace to a
    # leaked train row. Best-effort; absent queue → no proof block (not a fail).
    corpus: dict[str, Any] | None = None
    try:
        queues = sorted(
            d.glob("*-sft-queue.jsonl"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
    except OSError:
        queues = []
    if queues:
        _qr, q_prompts = _read_jsonl_prompts(queues[0])
        if q_prompts:
            c_overlap = len(q_prompts & held_prompts)
            corpus = {
                "rows": len(q_prompts),
                "overlap": c_overlap,
                "excluded": c_overlap == 0,
                "source": queues[0].name,
            }
    m = _BENCH_VERSION_RE.search(pool_path.stem)
    bench_id = (manifest or {}).get("bench_id")
    if not bench_id:
        # Derive from the filename: strip the trailing ``-vN.N`` if present.
        stem = pool_path.stem
        bench_id = re.sub(r"-v\d+(?:\.\d+)*$", "", stem) or stem
    return {
        "available": True,
        "kind": "bench",
        "bench_id": bench_id,
        "version": m.group(0) if m else None,
        "pool": len(pool_rows),
        "heldout": len(held_rows),
        "rows_total": len(all_rows),
        "overlap": overlap,
        "disjoint": overlap == 0,
        "golds_with_si": golds_with_si,
        "tier_mix": tier_mix,
        "topic_mix": topic_mix,
        "tolerance": (f"±{rel * 100:g}%" if rel is not None else None),
        "corpus": corpus,
        "source": pool_path.name,
        "heldout_source": heldout_path.name,
    }


def _newest_rl_run(db_path: str) -> dict[str, Any] | None:
    """The most-recent ``rl_run`` job row as a public dict, else ``None``.

    ``list_jobs`` returns newest-first, so the first ``rl_run`` is the latest.
    Best-effort: a missing/cold db yields ``None``."""
    try:
        from fieldkit.arena.store import ArenaStore

        db_file = Path(os.path.expanduser(db_path))
        if not db_file.is_file():
            return None
        store = ArenaStore(db_file)
        store.initialize()
        try:
            rows = store.list_jobs(limit=200)
        finally:
            store.close()
        for row in rows:
            kind = row["kind"] if "kind" in row.keys() else None
            if kind == "rl_run":
                return _job_to_public(row)
    except Exception as exc:  # noqa: BLE001 — build-spine nicety, never fatal
        _log.debug("newest rl_run read failed: %s", exc)
    return None


def _pct(v: Any) -> str | None:
    """``0.864`` → ``"86%"``; non-numeric → ``None``."""
    if isinstance(v, (int, float)):
        return f"{round(v * 100)}%"
    return None


# ---------------------------------------------------------------------------
# AE-10 (S6) — scout → Compare. The hf-model-scout writes a top-3 ranked
# base-model report (``/tmp/hf-scout/<date>/<vertical>/{report.md,candidates.json}``)
# the cockpit never saw — so the operator A/Bs candidate bases one stage too late
# (we caught Qwen3-8B's over-think after committing). This projects the newest
# report into the cockpit (a Compare-pane candidate panel) so the scout decision
# is visible AND frames the lock-time behavioral gate (eyeball boxing + verbosity
# on a held-out prompt before committing a bench). A PURE read of the report dir —
# no skill import (AE-R3), no arena.db, no GPU.


def _scout_dir() -> Path:
    """Root the hf-model-scout writes its run dirs under (``FK_ARENA_SCOUT_DIR``,
    default ``/tmp/hf-scout``)."""
    return Path(os.path.expanduser(os.environ.get("FK_ARENA_SCOUT_DIR", "/tmp/hf-scout")))


def _newest_scout_report(scout_root: Path) -> Path | None:
    """The newest ``report.md`` under the scout root (any depth), or ``None``."""
    try:
        reports = sorted(
            scout_root.rglob("report.md"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
    except OSError:
        return None
    return reports[0] if reports else None


_SCOUT_PICK_RE = re.compile(
    r"^###\s+(\d+)\.\s+(.+?)\s+[—-]\s+score\s+(\d+)/100(?:\s*[·-]\s*(.+))?$"
)
_SCOUT_RULED_RE = re.compile(r"^\|\s*`([^`]+)`\s*\|\s*(.+?)\s*\|\s*$")


def _parse_scout_report(text: str) -> dict[str, Any]:
    """Parse an hf-model-scout ``report.md`` into ranked picks + ruled-out rows.

    Picks come from the ``### N. <repo> — score NN/100 · <tagline>`` headings
    (the canonical skill format); ruled-out from the ``Picks ruled out`` table's
    `` `repo` | reason `` rows. Best-effort — a report missing either section just
    yields an empty list for it."""
    picks: list[dict[str, Any]] = []
    ruled: list[dict[str, str]] = []
    generated: str | None = None
    in_ruled = False
    for raw in text.splitlines():
        line = raw.strip()
        if generated is None and line.startswith("> Run:"):
            generated = line[len("> Run:"):].strip()
        m = _SCOUT_PICK_RE.match(line)
        if m:
            picks.append({
                "rank": int(m.group(1)),
                "repo": m.group(2).strip(),
                "score": int(m.group(3)),
                "tagline": (m.group(4) or "").strip() or None,
            })
            continue
        if line.lower().startswith("## picks ruled out"):
            in_ruled = True
            continue
        if in_ruled:
            if line.startswith("## "):
                in_ruled = False
                continue
            rm = _SCOUT_RULED_RE.match(line)
            if rm:
                repo, reason = rm.group(1).strip(), rm.group(2).strip()
                # Skip the markdown table header/separator rows.
                if repo.lower() in ("repo", "") or set(repo) <= {"-", " ", ":"}:
                    continue
                ruled.append({"repo": repo, "reason": reason})
    picks.sort(key=lambda p: p["rank"])
    return {"picks": picks, "ruled_out": ruled, "generated": generated}


def _scout_projection() -> dict[str, Any] | None:
    """AE-10 — the newest scout report as a cockpit-ready projection, or ``None``.

    Joins the report's ranked picks with the structured ``candidates.json``
    (license / chat-format / arch / Spark envelope) by repo, so each pick carries
    both the prose ranking and the machine-checked traps. Read-only + best-effort."""
    root = _scout_dir()
    report = _newest_scout_report(root)
    if report is None:
        return None
    try:
        parsed = _parse_scout_report(report.read_text())
    except OSError:
        return None
    run_dir = report.parent
    # candidates.json sits beside the report — index by repo for the join.
    by_repo: dict[str, dict[str, Any]] = {}
    cand_path = run_dir / "candidates.json"
    if cand_path.is_file():
        try:
            for c in json.loads(cand_path.read_text()):
                if isinstance(c, dict) and c.get("repo"):
                    by_repo[str(c["repo"])] = c
        except (OSError, ValueError):
            by_repo = {}

    def _axes(repo: str) -> dict[str, Any]:
        c = by_repo.get(repo) or {}
        env = c.get("spark_envelope") or {}
        warnings = [w for w in (c.get("warnings") or []) if w]
        return {
            "license": c.get("license"),
            "commercial_ok": c.get("commercial_ok"),
            "chat_format": c.get("chat_format"),
            "training_type": c.get("training_type"),
            "arch": c.get("arch_name"),
            "llama_cpp_compat": c.get("llama_cpp_compat"),
            "f16_gb": env.get("f16_gb"),
            "q4km_gb": env.get("q4km_gb"),
            "tg_tok_s": env.get("estimated_tg_tok_s"),
            "fits": bool(env.get("fits_q4km")),
            "warnings": warnings,
        }

    picks = [{**p, **_axes(p["repo"])} for p in parsed["picks"]]
    try:
        rel = str(run_dir.relative_to(root))
    except ValueError:
        rel = run_dir.name
    return {
        "available": True,
        "run": rel,
        "generated": parsed["generated"],
        "report": report.name,
        "n_candidates": len(by_repo),
        "picks": picks,
        "ruled_out": parsed["ruled_out"],
    }


def _build_scout_stage() -> dict[str, Any]:
    """C-A scout — a base-model pick has no structured feed, so the only live
    signal is the *presence* of an ``hf-model-scout`` report (``FK_ARENA_SCOUT_DIR``,
    default ``/tmp/hf-scout``). That is a coarse default the manifest overrides
    with the actual locked base (``live: False`` → manifest owns state/headline)."""
    scout_root = _scout_dir()
    try:
        found = _newest_scout_report(scout_root) is not None
    except OSError:
        found = False
    return {
        "key": "scout", "code": "A", "label": "Scout",
        "state": "done" if found else "pending",
        "headline": "base-model report present" if found else "—",
        "detail": "hf-model-scout top-3 → base lock (license · arch · size traps)",
        "gate": "base lock", "gate_state": "pass" if found else "pending",
        "gate_consequence": (
            "Locks the base model; a wrong base (NC-license / unsupported "
            "llama.cpp-arch / oversize weights) sinks the whole pipeline."
        ),
        "href": None, "source": "scout-dir", "live": False,
    }


def _build_bench_stage(
    bench_id: str | None,
    vertical: str,
    provenance: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """C-B bench — the eval substrate. Read live from the bench registry
    (``benches.list_benches``), then overlaid with the AE-8 provenance projection
    when the bench JSONL is on disk. Picks the manifest's ``bench_id`` → else the
    first available bench for the vertical → else the first available."""
    base = {
        "key": "bench", "code": "B", "label": "Bench",
        "state": "pending", "headline": "—",
        "detail": "pool + held-out · self-verifying golds",
        "gate": None, "gate_state": "none",
        "href": None, "source": "benches", "live": True,
    }
    try:
        from fieldkit.arena import benches as _benches

        rows = _benches.list_benches()
    except Exception as exc:  # noqa: BLE001
        _log.debug("bench list for build spine failed: %s", exc)
        rows = []
    row = None
    if bench_id:
        # An explicit pin selects exactly that bench. astro-bench is registered
        # (AE-11/S6); when its JSONL is present the registry + AE-8 overlay light
        # it live, and when absent the card stays blank so the manifest fills it
        # (rather than mislabeling with an unrelated vertical's bench).
        row = next((r for r in rows if r.get("bench_id") == bench_id), None)
        if row is None:
            base["state"] = "blank"
    else:
        row = next(
            (r for r in rows if r.get("vertical") == vertical and r.get("available")),
            None,
        ) or next((r for r in rows if r.get("available")), None)
    if row is not None and row.get("available"):
        fams = ", ".join(row.get("families", [])[:6])
        base["state"] = "done"
        base["headline"] = (
            f"{row.get('label') or row.get('bench_id')} · {row.get('count')} prompts"
        )
        if fams:
            base["detail"] = f"families: {fams}"
    elif row is not None:
        # Registered but its files aren't on this box — keep the headline blank
        # (state ``blank``) so the operator manifest's headline can fill it;
        # surface the files-absent reason in detail (manifest-overridable).
        base["state"] = "blank"
        base["detail"] = f"{row.get('bench_id')} — files absent on this box"
    # AE-8 — overlay the on-disk provenance. When the bench JSONL exists this
    # wins over the registry (the bench may not be registered yet, AE-11/S6): it
    # lights the card live AND attaches the full provenance the island renders as
    # a card (version · disjointness ✓ · self-verify · tier/topic mix · corpus
    # exclusion). The card's headline/detail become a live read, not a manifest
    # string.
    if provenance and provenance.get("available"):
        base["provenance"] = provenance
        ver = provenance.get("version")
        bid = provenance.get("bench_id") or "bench"
        base["state"] = "done"
        base["headline"] = (
            f"{bid} {ver} · {provenance['pool']} pool + {provenance['heldout']} held-out"
            if ver
            else f"{bid} · {provenance['pool']} pool + {provenance['heldout']} held-out"
        )
        dj = (
            "disjoint ✓ (RV-10)"
            if provenance.get("disjoint")
            else f"{provenance.get('overlap')} OVERLAP ✗ (RV-10)"
        )
        sv = f"{provenance.get('golds_with_si')}/{provenance.get('rows_total')} self-verify"
        tol = provenance.get("tolerance")
        base["detail"] = f"{dj} · {sv}" + (f" · {tol}" if tol else "")
    return base


def _build_corpus_stage(root: Path) -> dict[str, Any]:
    """C1 corpus — the SFT-init corpus-synth run, read live from the corpus
    heartbeat feed (AE-6): ``written/target`` + the batch-verify tally on a
    running synth, the final count on done. The manifest fills it when no run has
    stamped a heartbeat yet (the producer is the in-CC-session skill)."""
    base = {
        "key": "corpus", "code": "C1", "label": "Corpus",
        "state": "pending", "headline": "—",
        "detail": "SFT-init corpus · closed-form numeric · held-out-excluded",
        "gate": "/usage token preflight", "gate_state": "pending",
        "gate_consequence": (
            "Confirms the synth fits the weekly cap before a multi-session run; "
            "holding stops the spend."
        ),
        "href": None, "source": "corpus-progress", "live": True,
    }
    rp = _newest_corpus_report(root)
    if rp is None:
        return base
    rep = _parse_corpus_report(rp)
    if not rep:
        return base
    status = rep.get("status") or "running"
    written, target = rep.get("written") or 0, rep.get("target")
    vf = rep.get("verify_fail")
    if vf == 0:
        verify = " · verify ✓"
    elif vf:
        verify = f" · {vf} verify ✗"
    else:
        verify = ""
    count = f"{written}/{target} rows" if target else f"{written} rows"
    if status == "done":
        base["state"] = "done"
        base["headline"] = count + verify
    else:
        base["state"] = "active"
        base["headline"] = count + verify
    return base


def _build_sft_stage() -> dict[str, Any]:
    """C2 SFT-init — read live from the SFT-progress feed (the newest NeMo p65
    driver log), the format-conditioning warm-start the RLVR loop begins from."""
    base = {
        "key": "sft", "code": "C2", "label": "SFT-init",
        "state": "pending", "headline": "—",
        "detail": "NeMo p65 LoRA format-conditioning warm-start",
        "gate": "held-out > base", "gate_state": "pending",
        "gate_consequence": (
            "SFT-init must beat base on held-out or the warm-start adds nothing; "
            "holding blocks the RLVR loop."
        ),
        "href": "../sft/", "source": "sft-progress", "live": True,
    }
    sft_dir = _sft_run_dir()
    log = _newest_sft_log(sft_dir)
    if log is None:
        return base
    rep = _parse_sft_log(log, sft_dir)
    if not rep:
        return base
    status = rep.get("status") or "init"
    cur, mx = rep.get("latest_iter") or 0, rep.get("max_iters") or 0
    loss = rep.get("last_loss")
    if status == "done":
        base["state"] = "done"
        base["headline"] = f"done · {mx} iters" + (f" · loss {loss}" if loss is not None else "")
    elif status == "running":
        base["state"] = "active"
        base["headline"] = f"running {cur}/{mx}" + (f" · loss {loss}" if loss is not None else "")
    else:
        base["state"] = "active"
        base["headline"] = "model + optimizer setup…"
    return base


def _build_smoke_stage(root: Path) -> dict[str, Any]:
    """C2/C5 smoke — read live from the newest reward report (the AV-10 held-out
    preflight, the same report the Reward gauge follows). The behavioral gate
    between a warm-start / checkpoint and trusting it."""
    base = {
        "key": "smoke", "code": "C2/C5", "label": "Smoke",
        "state": "pending", "headline": "—",
        "detail": "held-out preflight · boxed-rate · AV-R1 truncation",
        "gate": "AV-10 preflight", "gate_state": "pending",
        "gate_consequence": (
            "The behavioral smoke gates trusting the checkpoint; holding sends "
            "it back to corpus coverage."
        ),
        "href": "../reward/", "source": "reward-signal", "live": True,
    }
    rp = _newest_reward_report(root)
    if rp is None or not rp.is_file():
        return base
    try:
        r = json.loads(rp.read_text())
    except (OSError, ValueError):
        return base
    status = r.get("status", "done")
    scored, total = r.get("scored"), r.get("total", r.get("n"))
    boxed = _pct(r.get("boxed_rate"))
    if status == "running":
        base["state"] = "active"
        base["headline"] = f"running {scored}/{total}"
    else:
        base["state"] = "done"
        reward = _pct(r.get("reward_rate_step0"))
        base["headline"] = f"{reward} held-out" if reward else "complete"
        gate = r.get("gate_pass")
        base["gate_state"] = (
            "pass" if gate else ("hold" if gate is False else "pending")
        )
    if boxed:
        base["detail"] = f"boxed {boxed} · held-out preflight · AV-R1 watch"
    return base


def _build_lane_stage(db_path: str) -> dict[str, Any]:
    """C4 lane — the serving lane (one-lane envelope). The live RL/external lane
    (the arbiter's truth, AE-15 layer 2) wins; else the configured resident brain
    is shown as *configured · idle* rather than falsely claimed active (AE-15)."""
    base = {
        "key": "lane", "code": "C4", "label": "Lane",
        "state": "pending", "headline": "—",
        "detail": "serving lane · one-lane envelope",
        "gate": None, "gate_state": "none",
        "href": None, "source": "lane", "live": True,
    }
    active = _read_active_gpu_lane(db_path)
    if active:
        base["state"] = "active"
        base["headline"] = f"{active['model']} · RL lane live"
        return base
    resident = _read_hermes_lane() or {}
    name = resident.get("model") or resident.get("lane_id")
    if name:
        base["state"] = "idle"
        base["headline"] = f"{name} · configured · idle"
    return base


def _build_rlvr_stage(db_path: str) -> dict[str, Any]:
    """C5 RLVR — read live from the newest ``rl_run`` job row's ``result_json``
    (the held-out-gated GRPO loop). Held-out-selected step + score on done; the
    live step on running; queued/failed surfaced honestly."""
    base = {
        "key": "rlvr", "code": "C5", "label": "RLVR",
        "state": "pending", "headline": "—",
        "detail": "GRPO held-out-gated · operator-armed",
        "gate": "held-out-win promote", "gate_state": "pending",
        "gate_consequence": (
            "Only a held-out-winning step promotes; holding keeps the prior "
            "checkpoint resident."
        ),
        "href": "../jobs/", "source": "jobs", "live": True,
    }
    job = _newest_rl_run(db_path)
    if job is None:
        return base
    status = job.get("status")
    res = job.get("result") or {}
    if status == "running":
        base["state"] = "active"
        step = res.get("step")
        base["headline"] = f"running step {step}" if step is not None else "running"
    elif status == "done":
        base["state"] = "done"
        held = _pct(res.get("selected_heldout_score"))
        sel = res.get("selected_exp_id") or (
            f"rl-{res.get('selected_step')}"
            if res.get("selected_step") is not None
            else None
        )
        base["headline"] = (held + " held-out" if held else "complete") + (
            f" · {sel}" if sel else ""
        )
        base["gate_state"] = "pass" if res.get("selected_heldout_score") else "pending"
    elif status in ("queued", "pending"):
        base["state"] = "pending"
        base["headline"] = "queued — armed by autonomy cron"
    elif status == "failed":
        base["state"] = "hold"
        base["headline"] = "failed"
    return base


def _build_publish_stage() -> dict[str, Any]:
    """C6 publish — the HF push + bench card. No sidecar-visible signal (the
    artifacts live in the marketing repo), so the manifest owns this stage."""
    return {
        "key": "publish", "code": "C6", "label": "Publish",
        "state": "pending", "headline": "—",
        "detail": "HF GGUF + bench card (hf-publisher)",
        "gate": "held-out-win publish", "gate_state": "pending",
        "gate_consequence": (
            "Publish only on a held-out win; holding keeps the artifact "
            "unpublished."
        ),
        "href": None, "source": "manifest", "live": False,
    }


def _merge_build_stage(
    auto: dict[str, Any], manifest_stage: Any
) -> dict[str, Any]:
    """Overlay the operator's manifest onto an auto-derived stage.

    Ownership split: for a stage with a rich live feed (``live: True``) the live
    ``state`` / ``headline`` / ``detail`` win — the manifest only fills them when
    the live signal is blank. ``gate`` / ``gate_state`` / ``href`` (operator
    annotations) and every field of a non-live stage are always manifest-owned."""
    out = dict(auto)
    live = out.pop("live", False)
    if isinstance(manifest_stage, dict):
        blank = {None, "", "—", "unknown", "pending", "blank"}
        for k, v in manifest_stage.items():
            if v is None:
                continue
            if live and k in ("state", "headline", "detail"):
                if out.get(k) in blank:
                    out[k] = v
            else:
                out[k] = v
    return out


def _assemble_build(root: Path, db_path: str) -> dict[str, Any]:
    """Assemble the eight-stage build spine (AE-5).

    Auto-derives every stage from existing signals, then overlays the optional
    ``build-manifest.json``. Always ``available: True`` when the sidecar answers;
    individual stages carry ``pending`` / ``blank`` until their signal exists."""
    manifest = _load_build_manifest(root)
    m_stages = manifest.get("stages")
    if not isinstance(m_stages, dict):
        m_stages = {}
    vertical = manifest.get("vertical") or "astrodynamics"
    label = manifest.get("label") or "the current vertical"
    bench_id = manifest.get("bench_id")
    provenance = _bench_provenance(root, manifest)
    auto = [
        _build_scout_stage(),
        _build_bench_stage(bench_id, vertical, provenance),
        _build_corpus_stage(root),
        _build_sft_stage(),
        _build_smoke_stage(root),
        _build_lane_stage(db_path),
        _build_rlvr_stage(db_path),
        _build_publish_stage(),
    ]
    stages = [_merge_build_stage(s, m_stages.get(s["key"])) for s in auto]
    done = sum(1 for s in stages if s.get("state") == "done")
    return {
        "available": True,
        "vertical": vertical,
        "label": label,
        "manifest_present": bool(manifest),
        "updated": manifest.get("updated"),
        "stages_done": done,
        "stages_total": len(stages),
        "stages": stages,
    }


def _mount_packaged_webui(app: Any) -> bool:
    """Mount the packaged ``_webui/`` static bundle at ``/arena`` if present.

    Returns True if the bundle was found + mounted, False otherwise (the
    common dev case where the UI is served by the Astro dev server instead).
    Resolves the bundle via :mod:`importlib.resources` so it works from any
    pip-installed location.
    """
    try:
        from importlib.resources import files as _ir_files

        webui = _ir_files("fieldkit.arena").joinpath("_webui")
        index = webui.joinpath("index.html")
        if not index.is_file():
            return False
        from fastapi.staticfiles import StaticFiles

        app.mount(
            "/arena",
            StaticFiles(directory=str(webui), html=True),
            name="arena-webui",
        )
        return True
    except Exception as exc:  # noqa: BLE001 — missing/zip bundle → API-only
        _log.debug("packaged _webui not mounted: %s", exc)
        return False


async def telemetry_event_stream(
    hub: "TelemetryHub", request: Any
) -> "AsyncIterator[dict[str, str]]":
    """Async generator powering ``/api/telemetry/stream``.

    Pulled out of the route closure so it can be unit-tested directly
    against an in-memory queue (no FastAPI / sse-starlette round-trip).
    Subscribes on entry, unsubscribes on exit (and stops the sampler if
    last subscriber leaves). Yields the "hello" payload immediately so the
    gauge paints without waiting for the first sampler interval.
    """
    loop = asyncio.get_event_loop()
    queue, unsubscribe = hub.subscribe(loop)
    try:
        hello = hub._build_payload()  # noqa: SLF001
        yield {"event": "telemetry", "data": json.dumps(hello)}
        while True:
            if await request.is_disconnected():
                break
            try:
                payload = await asyncio.wait_for(
                    queue.get(), timeout=hub.interval * 4
                )
            except asyncio.TimeoutError:
                yield {"event": "heartbeat", "data": "{}"}
                continue
            yield {"event": "telemetry", "data": json.dumps(payload)}
    finally:
        unsubscribe()


# ---------------------------------------------------------------------------
# M4 — chat SSE proxy to the resident brain.
# ---------------------------------------------------------------------------


def _chat_client_factory(
    resident: dict[str, Any],
):
    """Factory the chat event stream calls to build an OpenAI-compat client.

    Defined as a module-level hook so the M4 tests can monkeypatch it
    with a stub that yields canned token chunks (no live ``llama-server``
    required). The default builds
    :class:`fieldkit.notebook.OpenAICompatClient` against the resident's
    ``base_url``.
    """
    from fieldkit.notebook import OpenAICompatClient

    base_url = str(resident.get("base_url") or "")
    model = str(resident.get("model") or "local")
    return OpenAICompatClient(base_url, model)


def _new_session_id() -> str:
    """Generate a new ``chat_sessions.id`` — a short UTC-timestamped slug."""
    import uuid

    return "cs-" + uuid.uuid4().hex[:12]


def _utc_now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


# ---------------------------------------------------------------------------
# M8 — control-plane job helpers (shared by the /api/jobs routes + SSE feed)
# ---------------------------------------------------------------------------


def _job_to_public(row: Any) -> dict[str, Any]:
    """Render a ``jobs`` row for the cockpit board.

    Parses ``payload_json`` / ``result_json`` into objects so the island
    doesn't double-decode. Operator-only surface (loopback CORS, never
    mirrored), so the payload — the lane/bench the job operates on — is
    returned as-is for the operator's own board."""
    d = {k: row[k] for k in row.keys()}
    raw_payload = d.pop("payload_json", None)
    try:
        d["payload"] = json.loads(raw_payload) if raw_payload else {}
    except (json.JSONDecodeError, TypeError):
        d["payload"] = {}
    if d.get("result_json"):
        try:
            d["result"] = json.loads(d["result_json"])
        except (json.JSONDecodeError, TypeError):
            d["result"] = None
    return d


def _jobs_signature(jobs: list[dict[str, Any]]) -> tuple:
    """Cheap change-detector for the SSE feed — id × status × finished_at × progress.

    The progress nonce (rl-lane-autonomy LA-8) makes the board re-emit while a
    long ``rl_run`` is ``running`` — a step/phase advance in ``result_json``
    changes the signature even though status + finished_at don't, so the live
    progress pane updates without waiting for the job to finish.
    """

    def _nonce(j: dict[str, Any]) -> Any:
        if j.get("status") != "running":
            return None
        res = j.get("result")
        if not isinstance(res, dict):
            raw = j.get("result_json")
            if isinstance(raw, str) and raw:
                try:
                    res = json.loads(raw)
                except (json.JSONDecodeError, TypeError):
                    res = None
        if isinstance(res, dict):
            return (res.get("step"), res.get("phase"))
        return None

    return tuple((j["id"], j["status"], j.get("finished_at"), _nonce(j)) for j in jobs)


def _drain_jobs_background(db_path_str: str) -> None:
    """Drain the queue one job at a time through the harness (BackgroundTask).

    The M8 primary single-lane path (R14) — no arq/Redis. Runs in FastAPI's
    threadpool after the POST response, executing each job through the
    `fieldkit.harness` MCP tools (M8-1). Never raises out of the background
    task: a failed job is already marked ``failed`` in its row; an
    environment failure (no harness extra / lane not served) is swallowed
    after the row is stamped, so a misconfigured box degrades to a visible
    ``failed`` card rather than a 500."""
    from fieldkit.arena import jobs as _jobs
    from fieldkit.arena.store import ArenaStore

    store = ArenaStore(Path(db_path_str))
    store.initialize()
    try:
        _jobs.drain_jobs(store, on_error="record")
    except Exception as exc:  # noqa: BLE001 — background task must not crash the loop
        _log.warning("job drain aborted: %s", exc)
    finally:
        store.close()


async def jobs_event_stream(
    db_path_str: str, request: Any
) -> "AsyncIterator[dict[str, str]]":
    """Async generator powering ``/api/jobs/stream``.

    Emits a full board snapshot on connect, then re-emits only when the
    board changes (a job flips status or finishes) — polling the sync store
    off the event loop via :func:`asyncio.to_thread`. A heartbeat keeps the
    channel warm between changes. Pulled out of the route closure so it can
    be unit-tested against a temp DB without a FastAPI round-trip."""
    from fieldkit.arena.store import ArenaStore

    def _snapshot() -> list[dict[str, Any]]:
        path = Path(db_path_str)
        if not path.is_file():
            return []
        store = ArenaStore(path)
        store.initialize()
        try:
            return [_job_to_public(r) for r in store.list_jobs(limit=200)]
        finally:
            store.close()

    last_sig: tuple | None = None
    idle = 0
    while True:
        if await request.is_disconnected():
            break
        jobs = await asyncio.to_thread(_snapshot)
        sig = _jobs_signature(jobs)
        if sig != last_sig:
            last_sig = sig
            idle = 0
            yield {"event": "jobs", "data": json.dumps({"jobs": jobs})}
        else:
            idle += 1
            if idle >= 8:  # ~12 s of quiet → heartbeat so proxies don't reap
                idle = 0
                yield {"event": "heartbeat", "data": "{}"}
        await asyncio.sleep(1.5)


def _ensure_resident_lane_row(store: Any, resident: dict[str, Any]) -> str:
    """Upsert a minimal ``lanes`` row for the resident brain.

    The ``chat_sessions.lane_id`` column FKs to ``lanes.id``; the resident
    brain comes from a live ``~/.hermes/config.yaml`` read, not the M2
    importer, so the row may not yet exist. Upserting on every chat
    keeps the FK happy without requiring the operator to have run
    ``fieldkit arena import`` first. The row is idempotent on ``id``;
    a subsequent M2 import will overwrite with the richer manifest shape.
    """
    from fieldkit.arena.schemas import LaneRecord

    lane_id = str(resident.get("id") or "resident-brain")
    store.upsert_lane(
        LaneRecord(
            id=lane_id,
            kind=str(resident.get("kind") or "LlamaServerLane"),
            model=str(resident.get("model") or ""),
            port=int(resident.get("port") or 0),
            base_url=str(resident.get("base_url") or ""),
            last_warm_at=_utc_now_iso(),
        )
    )
    return lane_id


def _ensure_session(
    store: Any,
    session_id: str | None,
    *,
    lane_id: str,
    rubric_id: str | None,
) -> str:
    """Return the (existing or freshly created) ``chat_sessions.id``.

    The M4 sidecar persists every chat into a session even when the
    operator never lifts an ``id`` to the client — keeps replay simple
    + bumps the ``ord`` column monotonically. The caller is responsible
    for ensuring a ``lanes`` row exists for ``lane_id`` first (see
    :func:`_ensure_resident_lane_row`).
    """
    from fieldkit.arena.schemas import ChatSessionRecord

    if session_id:
        existing = store.chat_session(session_id)
        if existing is not None:
            return session_id
    new_id = session_id or _new_session_id()
    store.upsert_chat_session(
        ChatSessionRecord(
            id=new_id,
            lane_id=lane_id,
            created_at=_utc_now_iso(),
            rubric_id=rubric_id,
            publishable=0,
        )
    )
    return new_id


def _next_ord(store: Any, session_id: str) -> int:
    """Next ``chat_turns.ord`` for ``session_id`` (0-based, monotonic)."""
    rows = store.chat_turns(session_id)
    return len(rows)


def _resolve_eval_prompt(body: Any) -> tuple[str | None, dict[str, Any] | None]:
    """If ``body`` carries ``bench_id`` + ``eval_qid``, return the canonical
    model prompt (context-prepended, edit-aware) + an ``eval_context`` block to
    surface in the ``start`` event. Returns ``(None, None)`` otherwise / on a
    missing bench so the caller falls back to ``body.prompt``."""
    bench_id = getattr(body, "bench_id", None)
    qid = getattr(body, "eval_qid", None)
    if not bench_id or not qid:
        return None, None
    from fieldkit.arena import benches as _benches

    loaded = _benches.load_bench(bench_id)
    if loaded is None:
        return None, None
    prompt = loaded.by_qid.get(qid)
    if prompt is None:
        return None, None
    model_prompt = _benches.build_model_prompt(prompt, getattr(body, "prompt", "") or "")
    eval_context = {
        "bench_id": bench_id,
        "qid": qid,
        "scorer_kind": prompt.scorer_kind,
        "attached": prompt.has_context,
        "kind": prompt.context_kind,
        "token_hint": prompt.context_token_hint,
    }
    return model_prompt, eval_context


def _guard_prompt_ctx(
    model_prompt: str, *, max_tokens: int, ceiling: int
) -> tuple[str, bool]:
    """Middle-truncate ``model_prompt`` if it would overflow ``ceiling`` tokens
    (leaving headroom for ``max_tokens``). Returns ``(prompt, truncated)``.

    Crude char≈token/4 budgeting — enough to dodge an opaque context-window
    400 on big oracle/evidence blocks while keeping both the leading context
    and the trailing question/options intact."""
    budget_tokens = max(256, ceiling - max_tokens - 256)
    if len(model_prompt) // 4 <= budget_tokens:
        return model_prompt, False
    budget_chars = budget_tokens * 4
    head = budget_chars // 2
    tail = budget_chars - head
    marker = "\n\n…[context truncated to fit the context window]…\n\n"
    return model_prompt[:head] + marker + model_prompt[-tail:], True


async def chat_event_stream(
    *,
    hub: "TelemetryHub",
    request: Any,
    body: Any,
    resident: dict[str, Any],
    db_path: str,
) -> "AsyncIterator[dict[str, str]]":
    """Async generator powering ``/api/chat/stream``.

    Pulled out of the route closure so unit tests can drive it directly
    (no FastAPI / sse-starlette round-trip needed). The shape:

    1. Resolve the lane (already passed in by the route from
       :func:`_read_hermes_lane`).
    2. Open / reuse a chat session row; persist the user turn.
    3. Build the M4 stub-or-real client via :func:`_chat_client_factory`
       (tests monkeypatch).
    4. Run ``client.chat_stream`` on a worker thread (it's a blocking
       generator over ``httpx.stream``). Drain its chunks into an
       ``asyncio.Queue`` on the main loop.
    5. For each chunk, classify reasoning vs content via
       :func:`fieldkit.notebook.split_think` over the rolling buffer.
       Emit ``token`` SSE events with ``channel`` = ``"reasoning"`` or
       ``"content"``.
    6. On done: persist the assistant turn; emit ``done`` with
       ``ttft_ms`` + ``tok_per_s``; clear telemetry inflight.

    The ``report_inflight`` pings drive the M3 telemetry gauge so the
    operator sees the same lane chip + tok/s in the gauge as the
    streaming reply. Spec §4.2 calls this round-trip out as the visible
    proof the M3+M4 surfaces share substrate.
    """
    # Local imports — keep the module surface stdlib-cheap.
    from fieldkit.arena.schemas import ChatTurnRecord
    from fieldkit.arena.store import ArenaStore
    from fieldkit.notebook import split_think

    db_file = Path(os.path.expanduser(db_path))
    store = ArenaStore(db_file)
    store.initialize()  # idempotent — ensures chat_* tables exist before write

    try:
        # v0.2 — resolve the requested lane (resident / on-demand local /
        # OpenRouter). _resolve_compare_lane upserts the backing lane row so the
        # chat_sessions FK holds even pre-`fieldkit arena import`.
        try:
            lane = _resolve_compare_lane(
                getattr(body, "lane", "local:resident"), resident, store
            )
        except ValueError as exc:
            yield {"event": "error", "data": json.dumps({"detail": str(exc)})}
            return
        lane_id = lane["lane_id"]

        # OpenRouter chat needs a key — there's no stub fallback here (unlike
        # compare); fail clearly so the operator can set it.
        if lane["kind"] == "openrouter" and lane["no_key"]:
            yield {
                "event": "error",
                "data": json.dumps(
                    {"detail": "OPENROUTER_API_KEY is not set — can't chat with an OpenRouter model."}
                ),
            }
            return

        session_id = _ensure_session(
            store,
            getattr(body, "session_id", None),
            lane_id=lane_id,
            rubric_id=getattr(body, "rubric_id", None),
        )
        # Persist the user turn FIRST — guarantees the row is on disk
        # even if the model errors / the stream tears mid-flight.
        user_ord = _next_ord(store, session_id)
        store.append_chat_turn(
            ChatTurnRecord(
                session_id=session_id,
                ord=user_ord,
                role="user",
                content=body.prompt,
                created_at=_utc_now_iso(),
            )
        )

        # On-demand local: load the GGUF (single-slot OOM teardown) with visible
        # progress before streaming. Resident / OpenRouter skip this.
        if lane["kind"] == "local_ondemand":
            mgr = _LOCAL_SERVER_MANAGER
            lid = lane["lane_id"]

            def _lstatus(phase: str, detail: str) -> dict[str, str]:
                return {
                    "event": "lane_status",
                    "data": json.dumps(
                        {"phase": phase, "model": lane["model"], "detail": detail}
                    ),
                }

            if mgr.is_warm(lid):
                yield _lstatus("ready", "already loaded")
            else:
                torn = await asyncio.to_thread(mgr.teardown_prior, lid)
                if torn:
                    yield _lstatus("teardown", f"unloading {torn}")
                yield _lstatus("loading", lane["gguf"].name)
                try:
                    await asyncio.to_thread(
                        mgr.spawn, lid, lane["gguf"], lane["alias"]
                    )
                except Exception as exc:  # noqa: BLE001
                    yield {
                        "event": "error",
                        "data": json.dumps({"detail": f"could not launch {lid}: {exc}"}),
                    }
                    return
                yield _lstatus("warming", "loading weights onto GPU")
                if not await asyncio.to_thread(mgr.wait_warm):
                    yield {
                        "event": "error",
                        "data": json.dumps({"detail": f"{lid} did not warm in time"}),
                    }
                    return
                yield _lstatus("ready", "warm")
            from fieldkit.notebook import OpenAICompatClient

            lane["client"] = OpenAICompatClient(
                lane["base_url"], lane["alias"], api_key="not-needed"
            )

        # v0.3 eval mode — run the bench's canonical context-prepended prompt
        # so the score matches measurement conditions. The persisted user turn
        # above keeps the displayed prompt; only the model sees the prepend.
        eval_model_prompt, eval_context = _resolve_eval_prompt(body)
        effective_prompt = eval_model_prompt if eval_model_prompt is not None else body.prompt
        if eval_model_prompt is not None:
            ceiling = (
                _ONDEMAND_CTX
                if lane["kind"] == "local_ondemand"
                else int(lane.get("context_length") or resident.get("context_length") or 8192)
            )
            effective_prompt, truncated = _guard_prompt_ctx(
                effective_prompt,
                max_tokens=int(getattr(body, "max_tokens", 4096)),
                ceiling=ceiling,
            )
            if eval_context is not None:
                eval_context["truncated"] = truncated

        # Emit the start event with the metadata the client needs to
        # render the lane chip / paint the session header.
        start_payload: dict[str, Any] = {
            "session_id": session_id,
            "lane_id": lane_id,
            "model": lane.get("model"),
            "base_url": lane.get("base_url"),
        }
        if eval_context is not None:
            start_payload["eval_context"] = eval_context
        yield {
            "event": "start",
            "data": json.dumps(start_payload),
        }
        # Clear the previous run's sticky speeds at stream start so the prefill
        # window shows a clean dash, not the last generation's rate flashed as
        # if it were live; the throttled ping below fills in real values.
        hub.report_inflight(inflight=True, tok_per_s=None, ttft_ms=None, lane_id=lane_id)

        client = lane["client"]
        messages = [{"role": "user", "content": effective_prompt}]
        kwargs = {
            "max_tokens": int(getattr(body, "max_tokens", 4096)),
            "temperature": float(getattr(body, "temperature", 0.0)),
        }

        # Stream the chat off a worker thread so the asyncio loop stays
        # free for the SSE writer. The httpx-backed ``chat_stream`` is
        # a blocking generator (sync httpx), so each ``next(it)`` call
        # blocks the worker thread but never the event loop.
        loop = asyncio.get_event_loop()
        queue: asyncio.Queue[tuple[str, Any]] = asyncio.Queue(maxsize=256)
        # Channel-aware split: the OpenAICompatClient already reconstructs
        # the `<think>…</think>` shape across both reasoning-format modes;
        # we classify each emitted chunk against a stateful in-think flag.
        rolling: list[str] = []
        in_think = False
        first_token_at: float | None = None
        start_at = time.monotonic()

        def _producer() -> None:
            try:
                for piece in client.chat_stream(messages, **kwargs):
                    if piece:
                        loop.call_soon_threadsafe(
                            queue.put_nowait, ("chunk", piece)
                        )
                loop.call_soon_threadsafe(queue.put_nowait, ("done", None))
            except Exception as exc:  # noqa: BLE001 — surface error to client
                loop.call_soon_threadsafe(
                    queue.put_nowait, ("error", str(exc))
                )

        producer = asyncio.create_task(asyncio.to_thread(_producer))
        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    kind, payload = await asyncio.wait_for(
                        queue.get(), timeout=60.0
                    )
                except asyncio.TimeoutError:
                    yield {"event": "heartbeat", "data": "{}"}
                    continue
                if kind == "done":
                    break
                if kind == "error":
                    yield {
                        "event": "error",
                        "data": json.dumps({"detail": payload}),
                    }
                    # Persist whatever we did stream so the operator can
                    # forensic the partial.
                    partial = "".join(rolling)
                    if partial:
                        reasoning, answer = split_think(partial)
                        asst_ord = _next_ord(store, session_id)
                        store.append_chat_turn(
                            ChatTurnRecord(
                                session_id=session_id,
                                ord=asst_ord,
                                role="assistant",
                                content=answer or partial,
                                reasoning=reasoning or None,
                                created_at=_utc_now_iso(),
                                finish_reason="error",
                            )
                        )
                    return
                # ``kind == "chunk"``: classify + emit.
                piece = str(payload)
                if first_token_at is None:
                    first_token_at = time.monotonic()
                rolling.append(piece)
                # Tag boundaries: the client emits ``<think>`` / ``</think>``
                # as standalone chunks (not interleaved with payload), so a
                # cheap equality check is enough.
                if piece == "<think>":
                    in_think = True
                    continue
                if piece == "</think>":
                    in_think = False
                    continue
                channel = "reasoning" if in_think else "content"
                yield {
                    "event": "token",
                    "data": json.dumps({"channel": channel, "text": piece}),
                }
                # Throttle inflight pings so the gauge sees a smoothed
                # tok/s rather than a 100-events-per-second cascade.
                if first_token_at and len(rolling) % 16 == 0:
                    elapsed = time.monotonic() - first_token_at
                    if elapsed > 0:
                        toks = max(len(rolling) - 1, 1)
                        hub.report_inflight(
                            inflight=True,
                            tok_per_s=toks / elapsed,
                            ttft_ms=(first_token_at - start_at) * 1_000,
                            lane_id=lane_id,
                        )
        finally:
            if not producer.done():
                producer.cancel()
                try:
                    await producer
                except (asyncio.CancelledError, Exception):  # noqa: BLE001
                    pass

        # Stream complete — finalize, persist, emit ``done``.
        full = "".join(rolling)
        reasoning, answer = split_think(full)
        end_at = time.monotonic()
        wall = end_at - start_at
        ttft_ms: float | None = (
            (first_token_at - start_at) * 1_000.0
            if first_token_at is not None
            else None
        )
        # Approx tok/s — character-count / 4 ≈ tokens; the M4 surface
        # publishes this approximation explicitly (the M5 compare pulls
        # the actual usage block out of the upstream response).
        approx_tokens = max(int(len(full) / 4), 0)
        post_first = (end_at - first_token_at) if first_token_at else 0.0
        tok_per_s = (
            approx_tokens / post_first if post_first > 0.001 else None
        )

        # M9 (Bet 6): meter OpenRouter spend BEFORE persisting so the cost
        # lands ON the chat turn row (local lanes cost nothing → 0.0). Token
        # counts are the 4-char heuristic (no usage block on the stream), so
        # ``tokens_estimated=1`` marks the figure as approximate (R20).
        cost_usd = 0.0
        tokens_in_est: int | None = None
        tokens_estimated = 1
        if lane["kind"] == "openrouter":
            tokens_in_est = _estimate_input_tokens(body.prompt)
            cost_usd = _compare_cost_usd(
                prompt=body.prompt,
                tokens_out=approx_tokens,
                price_in=lane["price_in"],
                price_out=lane["price_out"],
            )
        asst_ord = _next_ord(store, session_id)
        turn_id = store.append_chat_turn(
            ChatTurnRecord(
                session_id=session_id,
                ord=asst_ord,
                role="assistant",
                content=answer,
                reasoning=reasoning or None,
                tokens_in=tokens_in_est,
                tokens_out=approx_tokens or None,
                ttft_ms=ttft_ms,
                tok_per_s=tok_per_s,
                finish_reason="stop",
                created_at=_utc_now_iso(),
                cost_usd=cost_usd,
                tokens_estimated=tokens_estimated,
            )
        )
        hub.report_inflight(
            inflight=False,
            tok_per_s=tok_per_s,
            ttft_ms=ttft_ms,
            lane_id=lane_id,
        )
        # Chat turn persisted (with tok/s + TTFT) → the live leaderboard moved;
        # signal the LiveLeaderboard island to refetch (throughput-only row
        # even before any quality score lands).
        hub.bump_leaderboard()
        if cost_usd > 0:
            hub.add_openrouter_cost(cost_usd)
        yield {
            "event": "done",
            "data": json.dumps(
                {
                    "session_id": session_id,
                    "turn_id": turn_id,
                    "ttft_ms": ttft_ms,
                    "tok_per_s": tok_per_s,
                    "tokens_out": approx_tokens,
                    "wall_s": wall,
                    "finish_reason": "stop",
                    "cost_usd": round(cost_usd, 6),
                    "tokens_estimated": tokens_estimated,
                }
            ),
        }
    finally:
        store.close()
        # Last-line guard: idle ticks read the in-flight defaults, so
        # always reset to "no in-flight stream" when this generator
        # exits (success, disconnect, or error). Keep the lane label +
        # final speeds sticky (omit lane_id) so the rail shows the model
        # you just ran + where it ran, with its completion-final tok/s.
        hub.report_inflight(inflight=False)


# ---------------------------------------------------------------------------
# M5 — compare SSE proxy (side-by-side A/B + deterministic rubric scoring).
# ---------------------------------------------------------------------------


def _openrouter_b_lane_factory():
    """Build the default B-lane (OpenRouter frontier tier).

    Reads the snapshot prices from the H6 article's evidence JSON via
    :func:`fieldkit.harness.build_cost_router` — if ``OPENROUTER_API_KEY``
    is unset we still build the tier (the key resolution happens at the
    HTTP layer, not the config layer), but :func:`compare_event_stream`
    falls back to a stub "no-key" response in that case.

    Defined as a module-level hook so the M5 tests can monkeypatch with a
    stub OpenAI-compat client. The default uses
    :class:`fieldkit.notebook.OpenAICompatClient` against the OpenRouter
    OpenAI-compatible endpoint.
    """
    from fieldkit.harness import RouteTier
    from fieldkit.notebook import OpenAICompatClient

    # Spec §4.3 calls the default frontier as the H6 frontier tier — we
    # rebuild the lane shape locally rather than hard-coding the model id
    # so the price snapshot stays auditable. Keep the model + endpoint
    # canonical against the H6 article's evidence/openrouter_prices.json.
    frontier = RouteTier(
        name="frontier",
        endpoint="https://openrouter.ai/api/v1",
        model="anthropic/claude-opus-4.1",
        api_key_env="OPENROUTER_API_KEY",
        price_per_m_input_usd=15.0,
        price_per_m_output_usd=75.0,
        notes="H6 default frontier tier; reads OPENROUTER_API_KEY.",
    )
    api_key = os.environ.get(frontier.api_key_env or "OPENROUTER_API_KEY")
    client = OpenAICompatClient(
        frontier.endpoint, frontier.model, api_key=api_key
    )
    return client, frontier


def _stub_no_key_chunks(prompt: str) -> "list[str]":
    """Canned reply chunks when the operator has no OPENROUTER_API_KEY.

    Lets the compare path still terminate cleanly with a visible
    explanation instead of crashing the stream. The stub explicitly
    flags the cost-router status so the M5 UI can render an actionable
    "set OPENROUTER_API_KEY to enable the frontier tier" message instead
    of a generic "no answer" placeholder.
    """
    return [
        "[OpenRouter B-lane disabled — OPENROUTER_API_KEY is not set. ",
        f"The prompt {prompt[:80]!r} would have routed to the frontier ",
        "tier; export the key + restart `fieldkit arena serve` to enable ",
        "the live comparison.]",
    ]


# --- v0.2 OpenRouter catalog + any-vs-any lane resolution ------------------

# Cached OpenRouter /models catalog. Each entry already carries inline pricing,
# so one cached fetch serves both the lane dropdown AND the cost meter (price is
# looked up from this cache when a model is selected). TTL-bounded so a long-
# lived sidecar refreshes prices without hammering the API on every request.
_OR_CATALOG_CACHE: dict[str, Any] = {"fetched_monotonic": None, "models": None}
_OR_CATALOG_TTL_S = 3600.0  # 1 h — prices move slowly; the operator can restart.

# Curated fallback when the catalog can't be fetched (no key / offline). These
# two are the H6 priced tiers — keep canonical with the article evidence JSON.
_OR_FALLBACK_MODELS = [
    {
        "id": "anthropic/claude-opus-4.1",
        "name": "Anthropic: Claude Opus 4.1",
        "context_length": 200_000,
        "price_per_m_input_usd": 15.0,
        "price_per_m_output_usd": 75.0,
    },
    {
        "id": "openai/gpt-4o-mini",
        "name": "OpenAI: GPT-4o-mini",
        "context_length": 128_000,
        "price_per_m_input_usd": 0.15,
        "price_per_m_output_usd": 0.6,
    },
]


def _per_m(token_price: Any) -> float | None:
    """OpenRouter quotes USD-per-token as a string; convert to USD-per-million."""
    try:
        return round(float(token_price) * 1_000_000, 4)
    except (TypeError, ValueError):
        return None


def _openrouter_catalog(*, force: bool = False) -> list[dict[str, Any]]:
    """Return the OpenRouter model catalog (id, name, ctx, per-M prices).

    Cached with :data:`_OR_CATALOG_TTL_S`. Returns ``[]`` when there's no key
    or the fetch fails — callers fall back to :data:`_OR_FALLBACK_MODELS`.
    """
    now = time.monotonic()
    fetched = _OR_CATALOG_CACHE["fetched_monotonic"]
    cached = _OR_CATALOG_CACHE["models"]
    if (
        not force
        and fetched is not None
        and cached is not None
        and (now - fetched) < _OR_CATALOG_TTL_S
    ):
        return cached

    key = os.environ.get("OPENROUTER_API_KEY")
    models: list[dict[str, Any]] = []
    try:
        import httpx

        headers = {"Authorization": f"Bearer {key}"} if key else {}
        resp = httpx.get(
            "https://openrouter.ai/api/v1/models", headers=headers, timeout=10.0
        )
        if resp.status_code == 200:
            for m in resp.json().get("data", []):
                pricing = m.get("pricing") or {}
                mid = m.get("id")
                if not mid:
                    continue
                models.append(
                    {
                        "id": mid,
                        "name": m.get("name") or mid,
                        "context_length": m.get("context_length"),
                        "created": m.get("created"),
                        "price_per_m_input_usd": _per_m(pricing.get("prompt")),
                        "price_per_m_output_usd": _per_m(pricing.get("completion")),
                    }
                )
        else:
            _log.warning(
                "OpenRouter catalog HTTP %s — falling back to curated tiers.",
                resp.status_code,
            )
    except Exception as exc:  # noqa: BLE001 — network/JSON best-effort
        _log.warning("OpenRouter catalog fetch failed: %s", exc)

    if models:
        _OR_CATALOG_CACHE["fetched_monotonic"] = now
        _OR_CATALOG_CACHE["models"] = models
    return models


def _openrouter_models_for_ui() -> list[dict[str, Any]]:
    """Catalog if reachable, else the curated priced fallback."""
    return _openrouter_catalog() or list(_OR_FALLBACK_MODELS)


# Curation taxonomy — reduce the ~350-model catalog to a useful shortlist.
# Each entry is (group, label, id-regex); for each we keep the NEWEST matching
# model (by OpenRouter ``created``). Order here = display order.
_FRONTIER_FAMILIES = [
    ("OpenAI · GPT", r"^openai/gpt-\d"),
    ("OpenAI · o-series", r"^openai/o\d"),
    ("Anthropic · Claude Opus", r"^anthropic/claude-opus"),
    ("Anthropic · Claude Sonnet", r"^anthropic/claude-sonnet"),
    ("Anthropic · Claude Haiku", r"^anthropic/claude-haiku"),
    ("Google · Gemini Pro", r"^google/gemini[\w.\-]*pro"),
    ("Google · Gemini Flash", r"^google/gemini[\w.\-]*flash"),
    ("xAI · Grok", r"^x-ai/grok-?\d"),
]
_OPEN_FAMILIES = [
    ("Qwen3", r"^qwen/qwen3"),
    ("DeepSeek", r"^deepseek/deepseek"),
    ("Meta · Llama", r"^meta-llama/llama"),
    ("Mistral", r"^mistralai/(mistral|ministral|devstral|codestral)"),
    ("Google · Gemma", r"^google/gemma"),
    ("Z.ai · GLM", r"^z-ai/glm"),
    ("Moonshot · Kimi", r"^moonshotai/kimi"),
    ("NVIDIA · Nemotron", r"^nvidia/.*nemotron"),
    ("Microsoft · Phi", r"^microsoft/phi"),
    ("OpenAI · gpt-oss", r"^openai/gpt-oss"),
    ("MiniMax", r"^minimax/"),
]
# Base models our fine-tunes / corpora started from (or their nearest OpenRouter
# kin). Matched as id-prefixes; newest match wins. See artifact base_model fields.
_PROJECT_BASE_FAMILIES = [
    ("Patent · R1-Qwen3 lineage", r"^deepseek/deepseek-r1"),
    ("Patent/Medical · Qwen3-8B", r"^qwen/qwen3-8b"),
    ("Finance/Medical · Llama-3.1-8B", r"^meta-llama/llama-3\.1-8b"),
    ("Saul · Mistral-7B", r"^mistralai/mistral-7b"),
    ("Corpus teacher · Nemotron Nano", r"^nvidia/nemotron-nano"),
]

# Skip non-chat modalities + routers so the shortlist stays a chat A/B set.
_OR_SKIP_RE = re.compile(
    r"(image|audio|tts|whisper|embed|moderation|guard|sonar|search|router|nano-banana|lyria)",
    re.IGNORECASE,
)


def _curate_openrouter_models(
    models: list[dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    """Bucket the catalog into frontier / open / project-base shortlists.

    For each family matcher, keep the single newest (by ``created``) chat model
    whose id matches and isn't a non-chat modality. A model can appear in more
    than one bucket (e.g. a project base that's also a SOTA-open family)."""

    def _newest_for(families: list[tuple[str, str]]) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        seen_ids: set[str] = set()
        for label, pat in families:
            rx = re.compile(pat, re.IGNORECASE)
            cands = [
                m
                for m in models
                if m.get("id")
                and rx.search(m["id"])
                and not m["id"].endswith(":free")
                and not _OR_SKIP_RE.search(m["id"])
            ]
            if not cands:
                continue
            # Newest by created (fallback: keep catalog order = newest-first).
            cands.sort(key=lambda m: m.get("created") or 0, reverse=True)
            pick = cands[0]
            if pick["id"] in seen_ids:
                continue
            seen_ids.add(pick["id"])
            out.append({**pick, "group_label": label})
        return out

    return {
        "frontier": _newest_for(_FRONTIER_FAMILIES),
        "open": _newest_for(_OPEN_FAMILIES),
        "project_base": _newest_for(_PROJECT_BASE_FAMILIES),
    }


def _openrouter_price_for(model_id: str) -> tuple[float, float]:
    """(per-M input, per-M output) USD for ``model_id`` from the cached catalog.

    Falls back to the curated tiers, then to ``(0.0, 0.0)`` for unknown models
    (cost simply reads as $0 rather than crashing the meter)."""
    for src in (_openrouter_catalog(), _OR_FALLBACK_MODELS):
        for m in src:
            if m["id"] == model_id:
                return (
                    m.get("price_per_m_input_usd") or 0.0,
                    m.get("price_per_m_output_usd") or 0.0,
                )
    return (0.0, 0.0)


def _estimate_input_tokens(prompt: str) -> int:
    """Cheap ~4-chars-per-token estimate (the OAI-compat stream doesn't echo
    prompt-token usage). Honest order-of-magnitude for the cost meter."""
    return max(1, len(prompt) // 4)


def _compare_cost_usd(
    *, prompt: str, tokens_out: int | None, price_in: float, price_out: float
) -> float:
    """Per-run OpenRouter cost: input estimate × in-price + output × out-price."""
    tin = _estimate_input_tokens(prompt)
    tout = int(tokens_out or 0)
    return (tin / 1_000_000.0) * price_in + (tout / 1_000_000.0) * price_out


# M9 (Bet 6): the price snapshot every persisted OpenRouter cost row stamps. The
# lane prices flow from the baked H6 evidence (``_OR_FALLBACK_MODELS`` /
# ``_openrouter_b_lane_factory``), the same source ``fieldkit.cost`` seeds
# ``openrouter_price_snapshot`` from — so a row priced at ``H6_SNAPSHOT_ID``
# stays reproducible. (When the live catalog overrides a price the row still
# stamps the baseline snapshot; R19's reseed path issues a fresh id.)
from fieldkit.cost import H6_SNAPSHOT_ID as _ACTIVE_PRICE_SNAPSHOT_ID  # noqa: E402


# --- v0.2 on-demand local model serving (OOM-managed single slot) ----------

_QUANTS_ROOT = Path(os.environ.get("ARENA_QUANTS_ROOT", "/home/nvidia/data/quants"))
_ONDEMAND_PORT = int(os.environ.get("ARENA_ONDEMAND_PORT", "8091"))
_ONDEMAND_CTX = int(os.environ.get("ARENA_ONDEMAND_CTX", "8192"))


def _llama_server_bin() -> str | None:
    """Locate the llama-server binary (env override → known paths → PATH)."""
    import shutil

    cand = os.environ.get("LLAMA_SERVER_BIN")
    if cand and Path(cand).is_file():
        return cand
    for p in (
        "/home/nvidia/llama.cpp/build/bin/llama-server",
        os.path.expanduser("~/.hermes/bin/llama-server"),
        os.path.expanduser("~/llama.cpp/build/bin/llama-server"),
    ):
        if Path(p).is_file():
            return p
    return shutil.which("llama-server")


def _norm_name(s: str) -> str:
    return "".join(ch for ch in (s or "").lower() if ch.isalnum())


def _resolve_local_gguf(slug: str, variant: str) -> Path | None:
    """Map an artifact slug + quant ``variant`` → an on-disk GGUF.

    Matches the quants dir whose normalized name is a prefix of (or equals) the
    normalized slug — handles ``finance-chat-gguf``→``finance-chat``,
    ``ii-medical-8b-gguf``→``II-Medical-8B``, ``securityllm-gguf``→``SecurityLLM``,
    ``saul-7b-instruct-v1-gguf``→``Saul-7B-Instruct-v1``,
    ``patent-strategist-v3-nemo-gguf``→``patent-strategist-v3-nemo``. Then the
    ``model-<variant>.gguf`` file (with an F16/f16 case fallback)."""
    if not _QUANTS_ROOT.is_dir():
        return None
    nslug = _norm_name(slug)
    if nslug.endswith("gguf"):
        nslug = nslug[: -len("gguf")]
    best: Path | None = None
    best_len = -1
    for d in _QUANTS_ROOT.iterdir():
        if not d.is_dir():
            continue
        nd = _norm_name(d.name)
        if nd and (nslug.startswith(nd) or nd.startswith(nslug)):
            if len(nd) > best_len:
                best, best_len = d, len(nd)
    if best is None:
        return None
    for fn in (f"model-{variant}.gguf", f"model-{variant.lower()}.gguf"):
        p = best / fn
        if p.is_file():
            return p
    nv = _norm_name(variant)
    for p in best.glob("model-*.gguf"):
        if _norm_name(p.stem).endswith(nv):
            return p
    return None


class LocalServerManager:
    """Owns ONE on-demand llama-server slot (default :8091).

    OOM-smart: ``swap_to`` tears down the prior on-demand model before booting
    the requested one, so at most one managed local model is resident at a time
    (the always-warm resident brain on :8080 is NOT managed here). Methods are
    blocking — callers run them via ``asyncio.to_thread`` and emit progress
    events between phases."""

    def __init__(self, port: int = _ONDEMAND_PORT, ctx: int = _ONDEMAND_CTX) -> None:
        self.port = port
        self.ctx = ctx
        self.base_url = f"http://127.0.0.1:{port}/v1"
        self._proc: Any | None = None
        self._loaded_id: str | None = None
        self._lock = threading.Lock()

    @property
    def loaded_id(self) -> str | None:
        return self._loaded_id

    def _alive(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    def _kill_locked(self) -> None:
        if self._proc is not None:
            try:
                self._proc.terminate()
                try:
                    self._proc.wait(timeout=10)
                except Exception:  # noqa: BLE001
                    self._proc.kill()
            except Exception as exc:  # noqa: BLE001
                _log.warning("on-demand llama-server teardown raised: %s", exc)
        self._proc = None
        self._loaded_id = None

    def teardown(self) -> None:
        with self._lock:
            self._kill_locked()

    def is_warm(self, lane_id: str) -> bool:
        with self._lock:
            return self._loaded_id == lane_id and self._alive()

    def teardown_prior(self, keep_id: str) -> str | None:
        """Kill the loaded model unless it's ``keep_id`` (and still alive).
        Returns the id that was torn down, for the progress event."""
        with self._lock:
            if self._loaded_id == keep_id and self._alive():
                return None
            prev = self._loaded_id
            self._kill_locked()
            return prev

    def spawn(self, lane_id: str, gguf: Path, alias: str) -> None:
        """Boot llama-server for ``gguf`` (no-op if already the loaded lane)."""
        import subprocess

        binp = _llama_server_bin()
        if not binp:
            raise RuntimeError(
                "llama-server binary not found — set LLAMA_SERVER_BIN to enable "
                "on-demand local lanes."
            )
        with self._lock:
            if self._loaded_id == lane_id and self._alive():
                return
            self._kill_locked()
            self._proc = subprocess.Popen(
                [
                    binp,
                    "-m",
                    str(gguf),
                    "--host",
                    "127.0.0.1",
                    "--port",
                    str(self.port),
                    "-c",
                    str(self.ctx),
                    "-ngl",
                    "999",
                    "--alias",
                    alias,
                    "--jinja",
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            self._loaded_id = lane_id

    def wait_warm(self, timeout: float = 240.0) -> bool:
        """Poll ``/v1/models`` until the freshly-spawned server answers."""
        import httpx

        url = f"http://127.0.0.1:{self.port}/v1/models"
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if not self._alive():
                return False
            try:
                if httpx.get(url, timeout=2.0).status_code == 200:
                    return True
            except Exception:  # noqa: BLE001
                pass
            time.sleep(1.0)
        return False


# One manager per sidecar process (the cockpit is single-operator).
_LOCAL_SERVER_MANAGER = LocalServerManager()


async def _local_load_stream(lane_spec: str) -> "AsyncIterator[dict[str, str]]":
    """SSE generator that pre-warms an on-demand local lane with progress.

    Emits ``status`` events (phase teardown/loading/warming/ready) then a
    terminal ``done`` (or ``error``). Single-slot: tears the prior on-demand
    model down first. Used by ``POST /api/local/load`` so the operator can load
    a model from the compare picker before running a duel."""
    spec = (lane_spec or "").strip()
    if spec.startswith("local:"):
        spec = spec[len("local:") :]
    if spec in ("", "resident", "local"):
        yield {
            "event": "done",
            "data": json.dumps(
                {"ok": True, "lane_id": "local:resident", "detail": "resident is always warm"}
            ),
        }
        return

    slug, _, variant = spec.partition("::")
    variant = variant or "Q4_K_M"
    gguf = _resolve_local_gguf(slug, variant)
    if gguf is None:
        yield {
            "event": "error",
            "data": json.dumps({"detail": f"no on-disk GGUF for {spec!r}"}),
        }
        return

    mgr = _LOCAL_SERVER_MANAGER

    def _status(phase: str, detail: str) -> dict[str, str]:
        return {
            "event": "status",
            "data": json.dumps({"phase": phase, "model": spec, "detail": detail}),
        }

    if mgr.is_warm(spec):
        yield _status("ready", "already loaded")
        yield {"event": "done", "data": json.dumps({"ok": True, "lane_id": f"local:{spec}"})}
        return

    torn = await asyncio.to_thread(mgr.teardown_prior, spec)
    if torn:
        yield _status("teardown", f"unloading {torn}")
    yield _status("loading", gguf.name)
    try:
        await asyncio.to_thread(mgr.spawn, spec, gguf, spec.replace("::", ":"))
    except Exception as exc:  # noqa: BLE001
        yield {"event": "error", "data": json.dumps({"detail": f"could not launch {spec}: {exc}"})}
        return
    yield _status("warming", "loading weights onto GPU")
    if not await asyncio.to_thread(mgr.wait_warm):
        yield {"event": "error", "data": json.dumps({"detail": f"{spec} did not warm in time"})}
        return
    yield _status("ready", "warm")
    yield {"event": "done", "data": json.dumps({"ok": True, "lane_id": f"local:{spec}"})}


class _CompareSideError(Exception):
    """Raised inside ``_emit_side`` after a side's error SSE event is yielded,
    so the outer ``compare_event_stream`` aborts the run cleanly (no further
    persistence/score) — mirrors the M5 ``yield error; return`` contract."""


def _resolve_compare_lane(
    spec: str, resident: dict[str, Any] | None, store: Any
) -> dict[str, Any]:
    """Resolve one compare side's spec → a ready-to-stream lane descriptor.

    ``spec`` is ``"local:resident"`` / ``"local"`` / ``""`` (the warm Spark
    lane), ``"openrouter"`` (curated frontier via the test-monkeypatchable
    :data:`_compare_b_factory`), or ``"openrouter:<model_id>"`` (any catalogued
    model). Upserts the backing lane row so the ``compare_runs`` FK holds.

    Returns ``{kind, lane_id, client, model, base_url, price_in, price_out,
    no_key}``. Raises ``ValueError`` on an unknown/unsatisfiable spec (e.g. a
    local lane requested with no resident brain).
    """
    from fieldkit.arena.schemas import LaneRecord

    spec = (spec or "local:resident").strip()

    # --- OpenRouter sides ------------------------------------------------
    if spec == "openrouter" or spec.startswith("openrouter:"):
        if spec == "openrouter":
            # Preserve the M5 test hook + curated frontier defaults.
            client, frontier = _compare_b_factory()
            model = getattr(frontier, "model", "anthropic/claude-opus-4.1")
            price_in = float(getattr(frontier, "price_per_m_input_usd", 0.0) or 0.0)
            price_out = float(getattr(frontier, "price_per_m_output_usd", 0.0) or 0.0)
        else:
            from fieldkit.notebook import OpenAICompatClient

            model = spec[len("openrouter:") :]
            api_key = os.environ.get("OPENROUTER_API_KEY")
            client = OpenAICompatClient(
                "https://openrouter.ai/api/v1", model, api_key=api_key
            )
            price_in, price_out = _openrouter_price_for(model)

        lane_id = f"openrouter::{model}"
        store.upsert_lane(
            LaneRecord(
                id=lane_id,
                kind="RemoteLane",
                model=model,
                port=443,
                base_url="https://openrouter.ai/api/v1",
                last_warm_at=_utc_now_iso(),
                notes="OpenRouter lane (v0.2 any-vs-any)",
            )
        )
        no_key = (
            os.environ.get("OPENROUTER_API_KEY") is None
            or getattr(client, "api_key", "x") is None
        )
        return {
            "kind": "openrouter",
            "lane_id": lane_id,
            "client": client,
            "model": model,
            "base_url": "https://openrouter.ai/api/v1",
            "price_in": price_in,
            "price_out": price_out,
            "no_key": no_key,
        }

    # --- Local sides -----------------------------------------------------
    target = spec[len("local:") :] if spec.startswith("local:") else spec
    if target in ("", "resident", "local"):
        # The always-warm Spark lane (resident brain on :8080).
        if not resident or not resident.get("base_url"):
            raise ValueError(
                "local lane requested but no resident brain is configured in "
                "~/.hermes/config.yaml"
            )
        lane_id = _ensure_resident_lane_row(store, resident)
        return {
            "kind": "local",
            "lane_id": lane_id,
            "client": _chat_client_factory(resident),
            "model": resident.get("model"),
            "base_url": resident.get("base_url"),
            "price_in": 0.0,
            "price_out": 0.0,
            "no_key": False,
        }

    # On-demand local artifact, e.g. "finance-chat-gguf::Q4_K_M". The client is
    # built AFTER the model is loaded (see _emit_side's activation step); here we
    # just resolve the GGUF + register the lane row.
    slug, _, variant = target.partition("::")
    variant = variant or "Q4_K_M"
    gguf = _resolve_local_gguf(slug, variant)
    if gguf is None:
        raise ValueError(
            f"no on-disk GGUF for {target!r} under {_QUANTS_ROOT} — "
            "download/quantize it first."
        )
    from fieldkit.arena.schemas import LaneRecord

    store.upsert_lane(
        LaneRecord(
            id=target,
            kind="LlamaServerLane",
            model=target,
            port=_LOCAL_SERVER_MANAGER.port,
            base_url=_LOCAL_SERVER_MANAGER.base_url,
            last_warm_at=_utc_now_iso(),
            notes=f"on-demand GGUF {gguf.name}",
        )
    )
    return {
        "kind": "local_ondemand",
        "lane_id": target,
        "client": None,  # built post-load
        "model": target,
        "base_url": _LOCAL_SERVER_MANAGER.base_url,
        "gguf": gguf,
        "alias": target.replace("::", ":"),
        "price_in": 0.0,
        "price_out": 0.0,
        "no_key": False,
    }


def _new_compare_run_id() -> str:
    """Generate a fresh ``compare_runs.id`` — short UUID-derived slug."""
    import uuid

    return "cr-" + uuid.uuid4().hex[:12]


def _checks_to_payload(
    checks: "list[Any]",
) -> "list[dict[str, Any]]":
    """JSON-safe per-check rows for the ``score`` SSE event.

    Mirrors the :class:`fieldkit.eval.CheckResult` shape — ``ok`` is a
    bool, ``why`` is the short human-readable reason. Includes a ``name``
    field even though :class:`Rubric` is single-check today; the UI keys
    on it for the multi-check shape (Rubric of length >1) so the wire
    format stays forward-compatible.
    """
    payload: list[dict[str, Any]] = []
    for idx, (kind, result) in enumerate(checks):
        payload.append(
            {
                "name": f"check_{idx + 1}",
                "kind": kind,
                "ok": bool(result.passed),
                "why": str(result.why),
            }
        )
    return payload


async def _stream_one_side(
    *,
    client: Any,
    prompt: str,
    side: str,
    lane_id: str,
    request: Any,
    hub: "TelemetryHub",
    max_tokens: int,
    temperature: float,
) -> "AsyncIterator[Tuple[str, dict[str, Any] | str]]":
    """Pull tokens off ``client.chat_stream`` and yield ``(kind, payload)``.

    Two yield shapes:
    - ``("token", {"channel": "reasoning"|"content", "text": ...})``
    - ``("done", {"ttft_ms", "tok_per_s", "tokens_out", "wall_s",
      "finish_reason", "content", "reasoning"})``

    The wrapper keeps :func:`compare_event_stream` lean — it just decides
    which SSE event tag to attach (``token_a`` / ``token_b`` / ``done_a`` /
    ``done_b``) per yielded ``(kind, payload)``.
    """
    from fieldkit.notebook import split_think

    loop = asyncio.get_event_loop()
    queue: asyncio.Queue[tuple[str, Any]] = asyncio.Queue(maxsize=256)
    rolling: list[str] = []
    in_think = False
    first_token_at: float | None = None
    start_at = time.monotonic()

    def _producer() -> None:
        try:
            for piece in client.chat_stream(
                [{"role": "user", "content": prompt}],
                max_tokens=max_tokens,
                temperature=temperature,
            ):
                if piece:
                    loop.call_soon_threadsafe(
                        queue.put_nowait, ("chunk", piece)
                    )
            loop.call_soon_threadsafe(queue.put_nowait, ("done", None))
        except Exception as exc:  # noqa: BLE001 — surface error to client
            loop.call_soon_threadsafe(
                queue.put_nowait, ("error", str(exc))
            )

    producer = asyncio.create_task(asyncio.to_thread(_producer))
    finish_reason = "stop"
    try:
        while True:
            if await request.is_disconnected():
                finish_reason = "disconnect"
                break
            try:
                kind, payload = await asyncio.wait_for(
                    queue.get(), timeout=60.0
                )
            except asyncio.TimeoutError:
                # No heartbeat on the per-side stream; the outer SSE
                # ping loop covers proxy idle-tear protection.
                continue
            if kind == "done":
                break
            if kind == "error":
                finish_reason = "error"
                yield ("error", str(payload))
                break
            piece = str(payload)
            if first_token_at is None:
                first_token_at = time.monotonic()
            rolling.append(piece)
            if piece == "<think>":
                in_think = True
                continue
            if piece == "</think>":
                in_think = False
                continue
            channel = "reasoning" if in_think else "content"
            yield ("token", {"channel": channel, "text": piece})
            if first_token_at and len(rolling) % 16 == 0:
                elapsed = time.monotonic() - first_token_at
                if elapsed > 0:
                    toks = max(len(rolling) - 1, 1)
                    hub.report_inflight(
                        inflight=True,
                        tok_per_s=toks / elapsed,
                        ttft_ms=(first_token_at - start_at) * 1_000,
                        lane_id=lane_id,
                    )
    finally:
        if not producer.done():
            producer.cancel()
            try:
                await producer
            except (asyncio.CancelledError, Exception):  # noqa: BLE001
                pass

    full = "".join(rolling)
    reasoning, answer = split_think(full)
    end_at = time.monotonic()
    wall = end_at - start_at
    ttft_ms: float | None = (
        (first_token_at - start_at) * 1_000.0
        if first_token_at is not None
        else None
    )
    approx_tokens = max(int(len(full) / 4), 0)
    post_first = (end_at - first_token_at) if first_token_at else 0.0
    tok_per_s = (
        approx_tokens / post_first if post_first > 0.001 else None
    )
    yield (
        "done",
        {
            "side": side,
            "lane_id": lane_id,
            "ttft_ms": ttft_ms,
            "tok_per_s": tok_per_s,
            "tokens_out": approx_tokens,
            "wall_s": wall,
            "finish_reason": finish_reason,
            "content": answer,
            "reasoning": reasoning or None,
        },
    )


# Module-level hooks the M5 tests monkeypatch — declared near the
# generator so the binding is obvious; the chat factory pattern is the
# precedent.
_compare_b_factory = _openrouter_b_lane_factory


async def compare_event_stream(
    *,
    hub: "TelemetryHub",
    request: Any,
    body: Any,
    resident: dict[str, Any],
    db_path: str,
) -> "AsyncIterator[dict[str, str]]":
    """Async generator powering ``POST /api/compare/stream`` — spec §4.3.

    Drives the side-by-side compare top to bottom: warms A (the resident
    brain), streams A's response, persists A's row, warms B (default =
    OpenRouter frontier; explicit two-local-lanes mode rejected in v0.1
    per spec §4.9), streams B's response, persists B's row, runs the
    deterministic rubric score, emits the ``score`` SSE event with
    per-check ``ok`` / ``why`` strings.

    The B-lane factory is a module-level hook the M5 tests monkeypatch
    with a stub; the default builds an
    :class:`fieldkit.notebook.OpenAICompatClient` against the H6 frontier
    tier (price snapshot in the H6 article evidence). When
    ``OPENROUTER_API_KEY`` is unset the stub canned-reply path keeps the
    stream terminating cleanly with a visible explanation.

    Pulled out of the route closure so unit tests can drive it directly
    against a stub client (no live `llama-server` or OpenRouter needed).
    """
    from fieldkit.arena.rubrics import (
        DEFAULT_RUBRIC_REGISTRY,
        default_rubric_for_prompt,
        get_rubric,
    )
    from fieldkit.arena.schemas import (
        CompareResponseRecord,
        CompareRunRecord,
        RubricScoreRecord,
    )
    from fieldkit.arena.store import ArenaStore
    from fieldkit.eval import score_answer

    db_file = Path(os.path.expanduser(db_path))
    store = ArenaStore(db_file)
    store.initialize()

    try:
        # 1. Resolve rubric (explicit → registry; missing → spec §4.3 picker).
        rubric_id = (
            getattr(body, "rubric_id", None)
            or default_rubric_for_prompt(body.prompt)
        )
        spec = get_rubric(rubric_id)
        if spec is None:
            # Stale id — fall back to the floor rather than 400, so the
            # picker UX never strands an in-flight stream.
            rubric_id = "generic-correctness"
            spec = DEFAULT_RUBRIC_REGISTRY[rubric_id]

        # 2-3. Resolve both sides (v0.2 any-vs-any). Local sides need a warm
        #      resident; OpenRouter sides resolve a client + per-M prices. The
        #      default "openrouter" still flows through the monkeypatchable
        #      _compare_b_factory so the M5 stub-client tests keep working.
        try:
            lane_a = _resolve_compare_lane(
                getattr(body, "lane_a", "local:resident"), resident, store
            )
            lane_b = _resolve_compare_lane(body.lane_b, resident, store)
        except ValueError as exc:
            yield {"event": "error", "data": json.dumps({"detail": str(exc)})}
            return
        lane_a_id = lane_a["lane_id"]
        lane_b_id = lane_b["lane_id"]

        # 4. Allocate compare_run id + persist header row up-front so a
        #    mid-stream tear leaves a forensic trail.
        run_id = _new_compare_run_id()
        store.upsert_compare_run(
            CompareRunRecord(
                id=run_id,
                prompt=body.prompt,
                rubric_id=rubric_id,
                lane_a_id=lane_a_id,
                lane_b_id=lane_b_id,
                created_at=_utc_now_iso(),
                publishable=1,
            )
        )

        max_tokens = int(getattr(body, "max_tokens", 4096))
        temperature = float(getattr(body, "temperature", 0.0))
        side_done: dict[str, dict[str, Any]] = {}

        # v0.3 eval mode — both sides receive the bench's canonical
        # context-prepended prompt so the per-side scores match measurement
        # conditions. ``eval_context`` rides the start events for transparency.
        eval_model_prompt, eval_context = _resolve_eval_prompt(body)
        effective_prompt = (
            eval_model_prompt if eval_model_prompt is not None else body.prompt
        )
        if eval_model_prompt is not None:
            ceilings = [
                _ONDEMAND_CTX
                if ln["kind"] == "local_ondemand"
                else int(ln.get("context_length") or 8192)
                for ln in (lane_a, lane_b)
            ]
            effective_prompt, _ev_trunc = _guard_prompt_ctx(
                effective_prompt, max_tokens=max_tokens, ceiling=min(ceilings)
            )
            if eval_context is not None:
                eval_context["truncated"] = _ev_trunc

        async def _emit_side(side: str, lane: dict[str, Any]):
            """Yield one side's start/token/done SSE events; record its done
            payload (+ OpenRouter cost) into ``side_done[side]``.

            Events are named ``*_a`` / ``*_b`` by side. The ``start_a`` event
            additionally carries ``run_id`` + ``rubric_id`` (the client reads
            them off A). OpenRouter sides with no key fall to the canned stub so
            the stream still terminates and the rubric still scores."""
            suffix = side.lower()
            head_extra = (
                {"run_id": run_id, "rubric_id": rubric_id} if side == "A" else {}
            )

            def _status(phase: str, detail: str):
                return {
                    "event": "lane_status",
                    "data": json.dumps(
                        {
                            "side": side,
                            "phase": phase,
                            "model": lane["model"],
                            "detail": detail,
                        }
                    ),
                }

            # On-demand local artifact: load the GGUF before streaming, with
            # visible progress. Single-slot — tears down any prior on-demand
            # model first (OOM-smart). The warm resident on :8080 is untouched.
            if lane["kind"] == "local_ondemand":
                mgr = _LOCAL_SERVER_MANAGER
                lid = lane["lane_id"]
                if mgr.is_warm(lid):
                    yield _status("ready", "already loaded")
                else:
                    torn = await asyncio.to_thread(mgr.teardown_prior, lid)
                    if torn:
                        yield _status("teardown", f"unloading {torn}")
                    yield _status("loading", lane["gguf"].name)
                    try:
                        await asyncio.to_thread(
                            mgr.spawn, lid, lane["gguf"], lane["alias"]
                        )
                    except Exception as exc:  # noqa: BLE001
                        yield {
                            "event": "error",
                            "data": json.dumps(
                                {"detail": f"could not launch {lid}: {exc}", "side": side}
                            ),
                        }
                        raise _CompareSideError(str(exc))
                    yield _status("warming", "loading weights onto GPU")
                    if not await asyncio.to_thread(mgr.wait_warm):
                        yield {
                            "event": "error",
                            "data": json.dumps(
                                {"detail": f"{lid} did not warm in time", "side": side}
                            ),
                        }
                        raise _CompareSideError("warm timeout")
                    yield _status("ready", "warm")
                from fieldkit.notebook import OpenAICompatClient

                lane["client"] = OpenAICompatClient(
                    lane["base_url"], lane["alias"], api_key="not-needed"
                )

            if lane["kind"] == "openrouter" and lane["no_key"]:
                yield {
                    "event": f"start_{suffix}",
                    "data": json.dumps(
                        {
                            **head_extra,
                            "side": side,
                            "lane_id": lane["lane_id"],
                            "model": "OPENROUTER_API_KEY_unset",
                            "base_url": lane["base_url"],
                            "no_key": True,
                            **({"eval_context": eval_context} if eval_context else {}),
                        }
                    ),
                }
                chunks = _stub_no_key_chunks(effective_prompt)
                for chunk in chunks:
                    yield {
                        "event": f"token_{suffix}",
                        "data": json.dumps({"channel": "content", "text": chunk}),
                    }
                full = "".join(chunks)
                done = {
                    "content": full,
                    "reasoning": None,
                    "tokens_out": max(int(len(full) / 4), 0),
                    "ttft_ms": 0.0,
                    "tok_per_s": None,
                    "wall_s": 0.0,
                    "finish_reason": "stub_no_key",
                    "cost_usd": 0.0,
                }
                yield {
                    "event": f"done_{suffix}",
                    "data": json.dumps(
                        {
                            k: done[k]
                            for k in (
                                "ttft_ms",
                                "tok_per_s",
                                "tokens_out",
                                "wall_s",
                                "finish_reason",
                                "cost_usd",
                            )
                        }
                    ),
                }
                side_done[side] = done
                return

            yield {
                "event": f"start_{suffix}",
                "data": json.dumps(
                    {
                        **head_extra,
                        "side": side,
                        "lane_id": lane["lane_id"],
                        "model": lane["model"],
                        "base_url": lane["base_url"],
                        **({"eval_context": eval_context} if eval_context else {}),
                    }
                ),
            }
            # Clear sticky speeds at side-start (see chat-stream note) so each
            # compare side's prefill shows a dash, not the prior side's rate.
            hub.report_inflight(
                inflight=True, tok_per_s=None, ttft_ms=None, lane_id=lane["lane_id"]
            )
            done = None
            async for kind, payload in _stream_one_side(
                client=lane["client"],
                prompt=effective_prompt,
                side=side,
                lane_id=lane["lane_id"],
                request=request,
                hub=hub,
                max_tokens=max_tokens,
                temperature=temperature,
            ):
                if kind == "token":
                    yield {"event": f"token_{suffix}", "data": json.dumps(payload)}
                elif kind == "error":
                    yield {
                        "event": "error",
                        "data": json.dumps({"detail": payload, "side": side}),
                    }
                    raise _CompareSideError(payload)
                elif kind == "done":
                    done = payload
                    # M9 (Bet 6): price the side + carry the cost fields onto
                    # the ``done`` payload so the compare_responses INSERT below
                    # persists them (per-side input tokens — each lane bills the
                    # shared prompt at its own input price, M9-2).
                    cost = 0.0
                    tokens_in: int | None = None
                    tokens_estimated = 1
                    price_snapshot_id: str | None = None
                    if lane["kind"] == "openrouter":
                        tokens_in = _estimate_input_tokens(body.prompt)
                        cost = _compare_cost_usd(
                            prompt=body.prompt,
                            tokens_out=payload.get("tokens_out"),
                            price_in=lane["price_in"],
                            price_out=lane["price_out"],
                        )
                        price_snapshot_id = _ACTIVE_PRICE_SNAPSHOT_ID
                        hub.add_openrouter_cost(cost)
                    done["cost_usd"] = round(cost, 6)
                    done["tokens_in"] = tokens_in
                    done["tokens_estimated"] = tokens_estimated
                    done["price_snapshot_id"] = price_snapshot_id
                    yield {
                        "event": f"done_{suffix}",
                        "data": json.dumps(
                            {
                                k: done[k]
                                for k in (
                                    "ttft_ms",
                                    "tok_per_s",
                                    "tokens_out",
                                    "wall_s",
                                    "finish_reason",
                                    "cost_usd",
                                    "tokens_estimated",
                                )
                            }
                        ),
                    }
            assert done is not None
            side_done[side] = done

        # 5-6. Stream A, persist it, then stream B. A side error aborts the run
        #      before its (and any later) persistence — same contract as M5.
        try:
            async for ev in _emit_side("A", lane_a):
                yield ev
            a_done = side_done["A"]
            store.upsert_compare_response(
                CompareResponseRecord(
                    compare_run_id=run_id,
                    side="A",
                    lane_id=lane_a_id,
                    content=a_done["content"],
                    reasoning=a_done["reasoning"],
                    tokens_out=a_done["tokens_out"],
                    ttft_ms=a_done["ttft_ms"],
                    tok_per_s=a_done["tok_per_s"],
                    tokens_in=a_done.get("tokens_in"),
                    cost_usd=a_done.get("cost_usd"),
                    tokens_estimated=a_done.get("tokens_estimated", 1),
                    price_snapshot_id=a_done.get("price_snapshot_id"),
                )
            )
            async for ev in _emit_side("B", lane_b):
                yield ev
        except _CompareSideError:
            return
        b_done = side_done["B"]

        store.upsert_compare_response(
            CompareResponseRecord(
                compare_run_id=run_id,
                side="B",
                lane_id=lane_b_id,
                content=b_done["content"],
                reasoning=b_done["reasoning"],
                tokens_out=b_done["tokens_out"],
                ttft_ms=b_done["ttft_ms"],
                tok_per_s=b_done["tok_per_s"],
                tokens_in=b_done.get("tokens_in"),
                cost_usd=b_done.get("cost_usd"),
                tokens_estimated=b_done.get("tokens_estimated", 1),
                price_snapshot_id=b_done.get("price_snapshot_id"),
            )
        )

        # 7. Deterministic score — single rubric over both sides.
        rubric = spec.rubric
        a_checks = [
            (c.kind, score_answer(a_done["content"], c)) for c in rubric.checks
        ]
        b_checks = [
            (c.kind, score_answer(b_done["content"], c)) for c in rubric.checks
        ]
        a_total = sum(1.0 for _, r in a_checks if r.passed) / len(a_checks)
        b_total = sum(1.0 for _, r in b_checks if r.passed) / len(b_checks)
        scored_at = _utc_now_iso()
        a_payload = _checks_to_payload(a_checks)
        b_payload = _checks_to_payload(b_checks)
        store.append_rubric_score(
            RubricScoreRecord(
                rubric_id=rubric_id,
                total=a_total,
                checks_json=json.dumps(a_payload),
                scored_at=scored_at,
                compare_run_id=run_id,
                side="A",
            )
        )
        store.append_rubric_score(
            RubricScoreRecord(
                rubric_id=rubric_id,
                total=b_total,
                checks_json=json.dumps(b_payload),
                scored_at=scored_at,
                compare_run_id=run_id,
                side="B",
            )
        )

        speed_delta = None
        a_speed = a_done.get("tok_per_s")
        b_speed = b_done.get("tok_per_s")
        if isinstance(a_speed, (int, float)) and isinstance(
            b_speed, (int, float)
        ):
            speed_delta = float(a_speed) - float(b_speed)

        # 7b. v0.3 — reference-based eval scoring (augments, never replaces,
        #     the deterministic rubric block above). Both sides are graded
        #     against the bench gold with the correct per-prompt scorer; the
        #     normalized [0,1] scores feed the eval accuracy leaderboard.
        eval_payload: dict[str, Any] | None = None
        if eval_context is not None:
            from fieldkit.arena import benches as _benches

            judge = getattr(body, "judge", None)
            j_backend = getattr(judge, "backend", None) if judge else None
            j_model = getattr(judge, "model", None) if judge else None
            bench_id = eval_context["bench_id"]
            qid = eval_context["qid"]
            a_eval = _benches.score_eval_prediction(
                bench_id, qid, a_done["content"],
                judge_backend=j_backend, judge_model=j_model, resident=resident,
            )
            b_eval = _benches.score_eval_prediction(
                bench_id, qid, b_done["content"],
                judge_backend=j_backend, judge_model=j_model, resident=resident,
            )
            for side, ev, lane_sid in (("A", a_eval, lane_a_id), ("B", b_eval, lane_b_id)):
                if ev.get("scored"):
                    store.append_eval_score(
                        {
                            "bench_id": bench_id,
                            "qid": qid,
                            "lane_id": lane_sid,
                            "scorer_kind": ev.get("scorer_kind") or "",
                            "score": ev.get("score"),
                            "max_score": ev.get("max") or 1.0,
                            "normalized": ev.get("normalized"),
                            "reference": ev.get("reference") or "",
                            "rationale": ev.get("why") or "",
                            "judge_backend": ev.get("judge_backend"),
                            "cross_vertical": 0 if _benches.bench_for_lane(lane_sid) == bench_id else 1,
                            "source": "compare",
                            "source_id": f"{run_id}:{side}",
                            "scored_at": scored_at,
                        }
                    )
            eval_payload = {
                "bench_id": bench_id,
                "qid": qid,
                "scorer_kind": a_eval.get("scorer_kind") or b_eval.get("scorer_kind"),
                "reference": a_eval.get("reference") or b_eval.get("reference") or "",
                "max": a_eval.get("max") or b_eval.get("max") or 1.0,
                "a": a_eval,
                "b": b_eval,
            }

        score_event: dict[str, Any] = {
            "run_id": run_id,
            "rubric_id": rubric_id,
            "a": {"total": a_total, "checks": a_payload},
            "b": {"total": b_total, "checks": b_payload},
            "deltas": {
                "score": a_total - b_total,
                "speed_tok_per_s": speed_delta,
            },
        }
        if eval_payload is not None:
            score_event["eval"] = eval_payload

        # Reconcile the top instrument rail to this duel's *resting* state.
        # The rail's tok/s + TTFT are sticky to the last ping, which during a
        # local-vs-cloud duel is the cloud side (B streams last) — and that
        # last ping was a mid-stream 16-token estimate, not the final figure
        # the per-side card shows. Two fixes in one push: (1) prefer the LOCAL
        # (Spark) side so the cockpit headlines the Spark lane, falling back to
        # B when neither side is local; (2) report that side's FINAL tok/s +
        # TTFT (the exact numbers in its card) so the rail and the compare view
        # agree no matter where the operator looks.
        if lane_a["kind"] != "openrouter":
            rest_id, rest = lane_a_id, a_done
        elif lane_b["kind"] != "openrouter":
            rest_id, rest = lane_b_id, b_done
        else:
            rest_id, rest = lane_b_id, b_done
        hub.report_inflight(
            inflight=False,
            tok_per_s=rest.get("tok_per_s"),
            ttft_ms=rest.get("ttft_ms"),
            lane_id=rest_id,
        )
        # Both sides scored + persisted → the live leaderboard moved.
        hub.bump_leaderboard()

        yield {"event": "score", "data": json.dumps(score_event)}
    finally:
        store.close()
        # Flip to idle but KEEP the reconciled speeds + lane label so the rail
        # keeps showing "<model> / <where>" at rest (omit lane_id → sticky).
        hub.report_inflight(inflight=False)


# ---------------------------------------------------------------------------
# Launcher.
# ---------------------------------------------------------------------------


def _load_env_local(repo_root: str | None = None) -> list[str]:
    """Load ``KEY=VALUE`` pairs from ``.env.local`` into ``os.environ``.

    Lets ``fieldkit arena serve`` pick up ``OPENROUTER_API_KEY`` (and friends)
    from the repo's gitignored ``.env.local`` without the operator exporting
    them by hand. Dependency-free (no python-dotenv). Existing environment
    values WIN — an explicit export overrides the file. Checks ``repo_root``
    then the cwd. Returns the names that were set (for the boot log)."""
    candidates: list[Path] = []
    if repo_root:
        candidates.append(Path(repo_root))
    candidates.append(Path.cwd())
    loaded: list[str] = []
    seen: set[Path] = set()
    for base in candidates:
        try:
            env_path = (base / ".env.local").resolve()
        except OSError:
            continue
        if env_path in seen or not env_path.is_file():
            continue
        seen.add(env_path)
        try:
            for raw in env_path.read_text().splitlines():
                line = raw.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, val = line.partition("=")
                key = key.strip()
                # Strip an optional leading `export ` and matched quotes.
                if key.startswith("export "):
                    key = key[len("export ") :].strip()
                val = val.strip().strip('"').strip("'")
                if key and key not in os.environ:
                    os.environ[key] = val
                    loaded.append(key)
        except OSError:
            continue
    return loaded


def serve(
    host: str = "127.0.0.1",
    port: int = DEFAULT_ARENA_PORT,
    *,
    db: str = DEFAULT_ARENA_DB,
    repo_root: str | None = None,
    reload: bool = False,
    log_level: str = "info",
) -> None:
    """Run the sidecar via uvicorn.

    Loopback-only by default — the operator cockpit is local. Bind to
    ``0.0.0.0`` only when intentionally exposing on the LAN (no auth in
    v0.1 per spec §3.1 #4).
    """
    loaded_env = _load_env_local(repo_root)
    if loaded_env:
        _log.info(
            "Loaded %d var(s) from .env.local: %s",
            len(loaded_env),
            ", ".join(loaded_env),
        )

    try:
        import uvicorn
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError(
            "fieldkit.arena.server.serve() requires the 'arena' extra. "
            "Install with `pip install 'fieldkit[arena]'`."
        ) from exc

    # Export ARENA_DB / ARENA_REPO_ROOT into the process env so modules that
    # resolve roots from the environment rather than the create_app arg (e.g.
    # ``fieldkit.arena.benches`` — the astro-bench root override, AE-11) see the
    # operator's ``--repo-root``. Set in BOTH the reload and direct paths (only
    # the reload worker read it before). Kept out of ``create_app`` itself so the
    # test suite's repeated ``create_app(repo_root=tmp_path)`` stays isolated.
    os.environ.setdefault("ARENA_DB", db)
    if repo_root:
        os.environ.setdefault("ARENA_REPO_ROOT", repo_root)

    # When ``reload`` is requested we pass an import-string to uvicorn so
    # the worker process can reload module sources. Otherwise pass the app
    # instance directly — cheaper, no double-import.
    if reload:
        uvicorn.run(
            "fieldkit.arena.server:_reload_target",
            host=host,
            port=port,
            reload=True,
            log_level=log_level,
        )
    else:
        app = create_app(db=db, repo_root=repo_root)
        uvicorn.run(app, host=host, port=port, log_level=log_level)


def _reload_target():
    """Factory pulled by uvicorn's --reload codepath."""
    return create_app(
        db=os.environ.get("ARENA_DB", DEFAULT_ARENA_DB),
        repo_root=os.environ.get("ARENA_REPO_ROOT") or None,
    )
