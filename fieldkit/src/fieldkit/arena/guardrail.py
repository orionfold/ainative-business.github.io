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

**Operator config (arena-guardrail-settings, GS-1).** The thresholds are no longer
env-only: :func:`load_config` resolves an effective :class:`GuardrailConfig`
(``stall_timeout_s`` / ``cost_cap_usd`` / ``enabled``) with **file > env > default**
precedence and per-field source provenance, reading a JSON config file
(``~/.fieldkit/arena/guardrail-config.json``, overridable via ``FK_EVAL_CONFIG_DIR`` /
``FK_EVAL_CONFIG_PATH``). :func:`save_config` validates against :data:`BOUNDS` and writes
it atomically. :meth:`EvalGuardrail.from_env` is now a thin wrapper over the resolver, and
the arm site reads :func:`load_config` **per dispatch**, so an operator edit lands on the
next cloud eval with no restart — and the ``enabled`` master toggle off runs a cloud lane
unguarded. A corrupt/partial config file falls back to env/default (never crashes a
dispatch). The config file is operator-private — a file, not a table, never mirrored.
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
    "DEFAULTS",
    "BOUNDS",
    "EVAL_SENTINEL_DIR",
    "EVAL_CONFIG_PATH",
    "EvalGuardrail",
    "GuardrailConfig",
    "GuardrailConfigError",
    "eval_sentinel_dir",
    "eval_sentinel_for",
    "guardrail_config_path",
    "is_cloud_endpoint",
    "load_config",
    "save_config",
]

#: No-progress stall window (G2). Reset on every completed row, NOT a wall-clock
#: total — a legitimately-slow-but-progressing run never trips (AE-R6).
DEFAULT_STALL_TIMEOUT_S = 600.0

#: Per-run USD cost cap (G3) — the per-run sibling of the governor's per-day cap.
DEFAULT_RUN_COST_CAP_USD = 5.0

#: Dir for the per-job eval-abort sentinels (mirrors the RL ``sentinel_dir``).
EVAL_SENTINEL_DIR = "~/.fieldkit/arena/eval"

#: The operator-config file (GS-1) — the live override layered over env/defaults.
#: Overridable via ``FK_EVAL_CONFIG_PATH`` (exact path) or ``FK_EVAL_CONFIG_DIR``
#: (dir holding ``guardrail-config.json``). Operator-private; never a table, never
#: mirrored (the AF-9/AF-10 file convention — no arena.db schema change).
EVAL_CONFIG_PATH = "~/.fieldkit/arena/guardrail-config.json"

#: Canonical guardrail defaults — the built-in floor under env + the config file.
DEFAULTS: dict[str, Any] = {
    "stall_timeout_s": DEFAULT_STALL_TIMEOUT_S,
    "cost_cap_usd": DEFAULT_RUN_COST_CAP_USD,
    "enabled": True,
}

#: Validation bounds (GS-5, the fat-finger guard). ``stall_timeout_s`` accepts its
#: range **or** ``0`` (G2 off); ``cost_cap_usd`` accepts its range where ``0`` = G3
#: off. ``enabled`` is a plain bool (no numeric bound).
BOUNDS: dict[str, tuple[float, float]] = {
    "stall_timeout_s": (30.0, 86400.0),
    "cost_cap_usd": (0.0, 1000.0),
}


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


class GuardrailConfigError(ValueError):
    """A guardrail config value outside :data:`BOUNDS` (GS-5 fat-finger guard).

    Raised by :func:`save_config`; the API layer (GS-2) maps it to an HTTP 422.
    """


@dataclass
class GuardrailConfig:
    """The operator-editable guardrail thresholds (GS-1).

    The same three knobs :class:`EvalGuardrail` carries, but as a *config* value
    independent of any one run: ``stall_timeout_s`` (G2), ``cost_cap_usd`` (G3),
    and the ``enabled`` master toggle (GS-4 — off ⇒ cloud evals run unguarded,
    byte-for-byte the local-lane path). Persisted to / resolved from a JSON file
    via :func:`save_config` / :func:`load_config`.
    """

    stall_timeout_s: float = DEFAULT_STALL_TIMEOUT_S
    cost_cap_usd: float = DEFAULT_RUN_COST_CAP_USD
    enabled: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "stall_timeout_s": self.stall_timeout_s,
            "cost_cap_usd": self.cost_cap_usd,
            "enabled": self.enabled,
        }


def guardrail_config_path() -> Path:
    """The guardrail config file path (env-overridable).

    ``FK_EVAL_CONFIG_PATH`` (an exact file) wins; else ``FK_EVAL_CONFIG_DIR``
    (a dir, joined with ``guardrail-config.json``); else the
    :data:`EVAL_CONFIG_PATH` default. ``~`` is expanded.
    """
    explicit = os.environ.get("FK_EVAL_CONFIG_PATH")
    if explicit:
        return Path(os.path.expanduser(explicit))
    dir_ = os.environ.get("FK_EVAL_CONFIG_DIR")
    if dir_:
        return Path(os.path.expanduser(dir_)) / "guardrail-config.json"
    return Path(os.path.expanduser(EVAL_CONFIG_PATH))


def load_config() -> tuple[GuardrailConfig, dict[str, str]]:
    """Resolve the effective config with **per-field provenance**: file > env > default.

    Each field is resolved independently — a present, parseable file key wins,
    else the matching env var, else the built-in default — returning
    ``(GuardrailConfig, sources)`` where each ``sources[field]`` ∈
    ``{"file", "env", "default"}``. A corrupt / partial / non-dict config file
    (GS-R5) is treated as absent (every field falls through to env/default); this
    never raises, so a dispatch can always arm. Env vars mirror AE-17's
    (``FK_EVAL_STALL_TIMEOUT_S`` / ``FK_EVAL_RUN_COST_CAP_USD``) plus
    ``FK_EVAL_GUARDRAIL_ENABLED`` for the toggle.
    """
    file_data: dict[str, Any] = {}
    path = guardrail_config_path()
    try:
        if path.exists():
            raw = json.loads(path.read_text())
            if isinstance(raw, dict):
                file_data = raw
    except (OSError, ValueError):
        file_data = {}  # corrupt/partial → fall back to env/default (GS-R5)

    sources: dict[str, str] = {}

    def _resolve_float(key: str, env_name: str, default: float) -> float:
        if key in file_data:
            v = _coerce_float(file_data.get(key))
            if v is not None:
                sources[key] = "file"
                return v
        env_raw = os.environ.get(env_name)
        if env_raw is not None:
            v = _coerce_float(env_raw)
            if v is not None:
                sources[key] = "env"
                return v
        sources[key] = "default"
        return default

    stall = _resolve_float(
        "stall_timeout_s", "FK_EVAL_STALL_TIMEOUT_S", DEFAULT_STALL_TIMEOUT_S
    )
    cost = _resolve_float(
        "cost_cap_usd", "FK_EVAL_RUN_COST_CAP_USD", DEFAULT_RUN_COST_CAP_USD
    )

    if "enabled" in file_data:
        enabled = bool(file_data.get("enabled"))
        sources["enabled"] = "file"
    elif os.environ.get("FK_EVAL_GUARDRAIL_ENABLED") is not None:
        enabled = _coerce_bool(os.environ["FK_EVAL_GUARDRAIL_ENABLED"])
        sources["enabled"] = "env"
    else:
        enabled = bool(DEFAULTS["enabled"])
        sources["enabled"] = "default"

    return (
        GuardrailConfig(stall_timeout_s=stall, cost_cap_usd=cost, enabled=enabled),
        sources,
    )


def _validate_config(cfg: GuardrailConfig) -> None:
    """Raise :class:`GuardrailConfigError` for any out-of-:data:`BOUNDS` field (GS-5).

    ``stall_timeout_s`` accepts its range **or** ``0`` (G2 off); ``cost_cap_usd``
    accepts its range (``0`` = G3 off). A tiny-but-positive cap (e.g. $0.001) is
    *allowed but loud* (GS-R1) — real operator intent, surfaced on the badge.
    """
    lo, hi = BOUNDS["stall_timeout_s"]
    if cfg.stall_timeout_s != 0 and not (lo <= cfg.stall_timeout_s <= hi):
        raise GuardrailConfigError(
            f"stall_timeout_s {cfg.stall_timeout_s} out of range "
            f"[{lo}, {hi}] (or 0 to disable G2)"
        )
    lo, hi = BOUNDS["cost_cap_usd"]
    if not (lo <= cfg.cost_cap_usd <= hi):
        raise GuardrailConfigError(
            f"cost_cap_usd {cfg.cost_cap_usd} out of range [{lo}, {hi}] (0 disables G3)"
        )


def save_config(cfg: GuardrailConfig) -> GuardrailConfig:
    """Validate against :data:`BOUNDS` then **atomically** write the config file.

    Atomic (``tmp + os.replace``) so a crash mid-write never leaves a half-written
    file the arm path would choke on (GS-R5). Returns the persisted config.
    """
    _validate_config(cfg)
    path = guardrail_config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(cfg.to_dict(), sort_keys=True))
    os.replace(tmp, path)
    return cfg


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
        """Build a guardrail with thresholds from the live config resolver (GS-1).

        Thin wrapper over :func:`load_config` (file > env > default), so an
        operator edit to the config file lands on the next dispatch with no
        restart. Back-compat with the original env-only behavior is preserved:
        with no config file present the resolver reads ``FK_EVAL_STALL_TIMEOUT_S``
        / ``FK_EVAL_RUN_COST_CAP_USD`` exactly as before. The ``enabled`` toggle is
        honored upstream at the arm site (``_run_eval_guarded``), not here — a
        constructed guardrail is always live.
        """
        cfg, _ = load_config()
        return cls(
            sentinel=Path(sentinel),
            stall_timeout_s=cfg.stall_timeout_s,
            cost_cap_usd=cfg.cost_cap_usd,
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


def _coerce_float(v: Any) -> Optional[float]:
    """Best-effort float; ``None`` for non-numeric (so the resolver falls through)."""
    if isinstance(v, bool):  # a stray JSON bool is not a valid numeric threshold
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _coerce_bool(v: Any) -> bool:
    """Parse a config/env truthy value: ``"0"``/``"false"``/``"no"``/``""`` ⇒ False."""
    if isinstance(v, bool):
        return v
    return str(v).strip().lower() not in {"", "0", "false", "no", "off"}


def _as_int(v: Any) -> int:
    try:
        return int(v or 0)
    except (TypeError, ValueError):
        return 0
