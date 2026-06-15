"""Lane truth — *discover* what's actually serving + *own* the active lane (AE-18/19/20).

Arena's system of record for the serving lane. The v1 path trusted
``~/.hermes/config.yaml`` (a *foreign tool's assertion* of what *should* be warm),
so the rail claimed an idle box was running Qwen3-30B while a real Kepler lane
served on another port (OBS-4). This module replaces that with:

- :func:`discover` — probe a small port set; each lane that answers ``/v1/models``
  (+ llama.cpp ``/props``) self-reports its identity. The **observation** (P1).
- :func:`load_active_lane` / :func:`save_active_lane` — an Arena-**owned** registry
  file (``~/.fieldkit/arena/active-lane.json``, GS-1 atomic pattern). The operator's
  selection (P2).
- :func:`resolve_active_lane` — reconcile the registry against discovery, demoting
  the Hermes config to one optional, labelled *hint* (AE-20). Drift is surfaced
  explicitly, never silently trusted (AE-R9).

See ``_SPECS/arena-enhancements-v2.md`` Cluster G. No ``arena.db`` schema change —
the registry is a JSON file. No skill imports. Best-effort throughout: a probe
failure degrades to "lane unknown," never an error.
"""

from __future__ import annotations

import json
import os
import time
import urllib.request
from pathlib import Path
from typing import Any, Optional

#: Ports discovery sweeps by default (llama.cpp lanes, NIM/vLLM OpenAI-compat).
#: Overridable via ``FK_ARENA_LANE_PORTS`` (comma-separated).
DEFAULT_LANE_PORTS = (8080, 8091, 8000, 8001)

#: Operator-owned active-lane registry. Override exact path via ``FK_ARENA_LANE_PATH``
#: or the dir via ``FK_ARENA_LANE_DIR`` (mirrors the GS-1 guardrail-config resolver).
LANE_REGISTRY_PATH = "~/.fieldkit/arena/active-lane.json"

_DISCOVER_TTL_S = 8.0
_discover_cache: dict[str, Any] = {"t": 0.0, "key": None, "v": None}


# --------------------------------------------------------------------------- #
# discovery (AE-18) — observe what is actually resident
# --------------------------------------------------------------------------- #
def lane_ports() -> list[int]:
    """The port set discovery sweeps for *chat* lanes (env-overridable).

    Excludes the infra ports (:func:`launcher.infra_ports` — the Cortex embedder
    on :8001) so an embedding endpoint that answers ``/v1/models`` is never
    enumerated as a selectable chat lane (AD-AE: it made the first-boot cockpit
    see "2 lanes", resolve the active lane "ambiguous", and land idle → the
    customer had to hand-pick the Advisor). With the embedder filtered out, the
    lone chat lane auto-resolves (``resolve_active_lane`` → ``source="discovered"``)
    and the cockpit lands warm. The lazy import keeps the launcher→lanes load
    order acyclic."""
    from fieldkit.arena.launcher import infra_ports

    raw = os.environ.get("FK_ARENA_LANE_PORTS")
    candidates = list(DEFAULT_LANE_PORTS)
    if raw:
        out = [int(t) for t in (s.strip() for s in raw.split(",")) if t.isdigit()]
        if out:
            candidates = out
    infra = infra_ports()
    return [p for p in candidates if p not in infra]


def _http_json(url: str, timeout: float) -> Optional[Any]:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:  # noqa: S310
            return json.loads(resp.read().decode("utf-8"))
    except Exception:  # noqa: BLE001 — a dead/refused port is the common case
        return None


def probe_port(port: int, host: str = "127.0.0.1", timeout: float = 0.4) -> Optional[dict[str, Any]]:
    """Probe one port; return a lane dict (``_read_hermes_lane`` shape + ``source``) or None.

    A lane is "resident" iff it answers OpenAI-compat ``/v1/models``. llama.cpp
    additionally serves ``/props`` (``model_path`` + ``n_ctx``) — used to enrich
    the identity and classify the lane kind.
    """
    base = f"http://{host}:{port}"
    models = _http_json(f"{base}/v1/models", timeout)
    if not isinstance(models, dict):
        return None
    data = models.get("data")
    model_id = ""
    if isinstance(data, list) and data and isinstance(data[0], dict):
        model_id = str(data[0].get("id") or "")

    props = _http_json(f"{base}/props", timeout)
    n_ctx: Optional[int] = None
    model_path = ""
    if isinstance(props, dict):
        gen = props.get("default_generation_settings")
        if isinstance(gen, dict):
            n_ctx = gen.get("n_ctx")
        n_ctx = n_ctx or props.get("n_ctx")
        model_path = str(props.get("model_path") or "")

    if model_path or isinstance(props, dict):
        kind = "LlamaServerLane"
    elif port in (8000,):
        kind = "NIMLane"
    else:
        kind = "OpenAICompatLane"

    model = model_id or (Path(model_path).name if model_path else "")
    if not model:
        return None
    return {
        "id": f"discovered:{port}",
        "kind": kind,
        "model": model,
        "base_url": f"{base}/v1",
        "port": port,
        "provider": "custom",
        "context_length": int(n_ctx) if n_ctx else None,
        "max_tokens": None,
        "model_path": model_path or None,
        "source": "discovered",
    }


def discover(
    ports: Optional[list[int]] = None,
    host: str = "127.0.0.1",
    timeout: float = 0.4,
) -> list[dict[str, Any]]:
    """Probe every port; return the resident lanes (uncached — pure)."""
    ports = ports if ports is not None else lane_ports()
    out: list[dict[str, Any]] = []
    for p in ports:
        lane = probe_port(p, host=host, timeout=timeout)
        if lane:
            out.append(lane)
    return out


def discover_cached(
    ports: Optional[list[int]] = None,
    ttl: float = _DISCOVER_TTL_S,
    **kw: Any,
) -> list[dict[str, Any]]:
    """Cached :func:`discover` (~8 s) so the telemetry tick never port-storms (AE-R7)."""
    key = tuple(ports) if ports is not None else tuple(lane_ports())
    now = time.monotonic()
    c = _discover_cache
    if c["v"] is not None and c["key"] == key and (now - c["t"]) < ttl:
        return c["v"]
    v = discover(list(key), **kw)
    c.update(t=now, key=key, v=v)
    return v


# --------------------------------------------------------------------------- #
# registry (AE-19) — Arena owns the operator's active-lane selection
# --------------------------------------------------------------------------- #
def lane_registry_path() -> Path:
    explicit = os.environ.get("FK_ARENA_LANE_PATH")
    if explicit:
        return Path(os.path.expanduser(explicit))
    dir_ = os.environ.get("FK_ARENA_LANE_DIR")
    if dir_:
        return Path(os.path.expanduser(dir_)) / "active-lane.json"
    return Path(os.path.expanduser(LANE_REGISTRY_PATH))


def load_active_lane() -> Optional[dict[str, Any]]:
    """The operator-selected active lane, or None. Corrupt file → None (never raises)."""
    p = lane_registry_path()
    if not p.is_file():
        return None
    try:
        v = json.loads(p.read_text())
        return v if isinstance(v, dict) else None
    except (OSError, ValueError):
        return None


def save_active_lane(lane: dict[str, Any]) -> dict[str, Any]:
    """Persist the active-lane selection atomically (tmp + os.replace, GS-1 pattern)."""
    p = lane_registry_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + ".tmp")
    tmp.write_text(json.dumps(lane, indent=2))
    os.replace(tmp, p)
    return lane


def clear_active_lane() -> None:
    """Forget the active-lane selection (revert to pure discovery)."""
    try:
        lane_registry_path().unlink()
    except FileNotFoundError:
        pass


# --------------------------------------------------------------------------- #
# reconciliation (AE-19/20, AE-R9/R11) — registry ∩ discovery, Hermes demoted
# --------------------------------------------------------------------------- #
def _models_agree(a: str, b: str) -> bool:
    a, b = (a or "").lower(), (b or "").lower()
    if not a or not b:
        return True  # can't disagree if one is unknown
    return a in b or b in a


def resolve_active_lane(
    discovered: Optional[list[dict[str, Any]]] = None,
    registry: Optional[dict[str, Any]] = None,
    hermes_hint: Optional[dict[str, Any]] = None,
    *,
    ports: Optional[list[int]] = None,
) -> dict[str, Any]:
    """Reconcile the active lane against observed reality. Always returns a dict.

    Resolution order (AE-R9 — drift is explicit, never silently trusted):

    1. **registry**, iff discovery confirms its port is live (drift flag if the
       model id disagrees);
    2. else the **single** live discovered lane (auto);
    3. else the **Hermes hint**, iff its port is live (demoted — AE-20);
    4. else **none** (``source="none"`` / ``"ambiguous"`` when >1 lane and no pick).

    The returned dict is the ``_read_hermes_lane`` shape (``base_url``/``model``/
    ``port``/… so chat/compare/rail are drop-in) plus orientation fields:
    ``source`` · ``drift`` · ``discovered`` · ``hermes_hint``. ``base_url`` is ``""``
    when nothing resolved (callers raise "no lane resident — arm one", AE-R11).
    """
    if discovered is None:
        discovered = discover_cached(ports=ports)
    by_port = {l["port"]: l for l in discovered if l.get("port")}

    chosen: Optional[dict[str, Any]] = None
    drift: Optional[str] = None
    source = "none"

    if registry and registry.get("port") in by_port:
        live = by_port[registry["port"]]
        if not _models_agree(str(registry.get("model") or ""), str(live.get("model") or "")):
            drift = (
                f"registry expects {registry.get('model')!r} on :{registry['port']}, "
                f"but it serves {live.get('model')!r}"
            )
        chosen = dict(live)
        # carry an operator max_tokens/context override from the registry, if set
        for k in ("max_tokens", "context_length"):
            if registry.get(k):
                chosen[k] = registry[k]
        source = "registry"
    elif registry and registry.get("port") not in by_port:
        drift = (
            f"selected lane {registry.get('model')!r} on :{registry.get('port')} "
            f"is not live"
        )

    if chosen is None:
        if len(discovered) == 1:
            chosen = dict(discovered[0])
            source = "discovered"
        elif len(discovered) > 1:
            source = "ambiguous"  # operator must pick (AE-22)

    if chosen is None and source != "ambiguous" and hermes_hint and hermes_hint.get("base_url"):
        # The Hermes config is a *demoted hint* (AE-20): surface it when discovery
        # found nothing, so the rail shows "configured · idle" instead of blank.
        # Liveness (rail label / build-stage state) is decided by ``source`` +
        # the TCP probe — a hint here is NOT a claim that it's serving.
        chosen = dict(hermes_hint)
        source = "hermes-hint"

    result: dict[str, Any] = dict(chosen) if chosen else {"base_url": "", "model": ""}
    result.update(
        {
            "source": source,
            "drift": drift,
            "discovered": discovered,
            "hermes_hint": hermes_hint,
        }
    )
    return result
