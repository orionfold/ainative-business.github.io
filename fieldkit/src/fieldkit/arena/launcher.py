"""Guarded lane launch + teardown — serving becomes an Arena operator action (AE-31).

The AE-22 *launch half* (arena-enhancements v2 cut 4, risk class AE-R13). Cuts 2–3
shipped the safe halves — *select/pin* a discovered lane (AE-22) and *observe* the
runtime roster (AE-30) — while launching a serve lane stayed a memorized terminal
block (the S1 smoke's ``exit-127`` PATH stumble is the evidence). This module is the
deterministic, correct-by-construction runner behind the Arena "launch lane" action:

- **Recipes** (:func:`load_lane_recipes`) — operator-authored
  ``~/.fieldkit/arena/lane-recipes.json``: the once-memorized command line stored as
  data (``gguf_path`` · ``port`` · ``n_ctx`` · ``ngl`` · ``extra_args``).
- **Pre-flight brake** (:func:`launch_lane`) — every side-effect-free check runs
  BEFORE the one destructive step: launch lock → recipe → binary → GGUF → unified-
  memory envelope → fused ONE-LANE/port check (``project_spark_unified_memory_oom``).
  A resident lane refuses the launch unless the operator explicitly passed
  ``teardown_first`` — and a doomed launch never tears a working lane down.
  **Infra ports** (:func:`infra_ports`, AD-FK-1) are exempt from ONE-LANE: the
  Cortex embedder container answers ``/v1/models`` so discovery honestly reports
  it, but it is not a chat lane — without the exemption a guarded launch was
  impossible whenever the grounded-chat stack was up. The ``oom_envelope`` gate
  still runs against real MemAvailable, so memory safety is unchanged.
- **Detached spawn** — ``start_new_session=True`` (the ``_rl_gpu_serve.VLLMLane``
  pattern) + an atomic owner file, so a launched lane *survives sidecar restarts*;
  the cockpit never child-manages it.
- **Verified teardown** (:func:`teardown_lane`) — owner-pid kill with a PID-reuse
  cmdline guard, targeted fallback (never a broad pkill for llama.cpp; the
  EngineCore-aware stop only for vLLM-kind lanes), and a "released" gate that is
  *observed* (process group empty + port refused), never asserted. The
  ``MemAvailable`` delta is reported informationally — page cache makes it noisy.

Refusals raise :class:`LaunchRefused` with a machine-readable ``reason`` — the jobs
layer persists them as honestly-failed rows (``refused:<reason> — …``). No
``arena.db`` schema change; all state is files beside the AE-19 registry.
"""

from __future__ import annotations

import fcntl
import json
import os
import shutil
import signal
import socket
import subprocess
import time
import urllib.request
from pathlib import Path
from typing import Any, Callable, Optional

from fieldkit.arena import lanes
from fieldkit.arena.lane import _meminfo_gb

__all__ = [
    "LaunchRefused",
    "infra_ports",
    "lane_recipes_path",
    "load_lane_recipes",
    "recipe_summaries",
    "estimate_lane_gb",
    "launch_lane",
    "teardown_lane",
    "lane_owner_path",
    "read_lane_owner",
]

#: Operator-authored launchable-lane recipes (sibling of the AE-19 registry file).
LANE_RECIPES_PATH = "~/.fieldkit/arena/lane-recipes.json"

#: One launch at a time — discovery is an observation, not a lock (TOCTOU).
LAUNCH_LOCK_NAME = "lane-launch.lock"

#: Infrastructure ports the ONE-LANE guard ignores and teardown refuses to touch
#: (AD-FK-1): the Cortex embedder (``nim-embed-nemotron``, :8001 — the port the
#: runtime telemetry already names "NIM embedder") is a co-resident docker
#: container, not a chat serving lane, and pointing the kill chain at a
#: docker-published port is untested. Override via ``FK_ARENA_INFRA_PORTS``
#: (comma-separated; set EMPTY to exempt nothing).
DEFAULT_INFRA_PORTS = (8001,)

#: Hard ceiling on a recipe's warm timeout — a launch holds one request-drain
#: worker while it polls; a genuinely slower model is left loading on timeout
#: (non-destructive), watchable via discovery.
WARM_TIMEOUT_CEILING_S = 120.0
WARM_TIMEOUT_DEFAULT_S = 90.0

_TERM_GRACE_S = 10.0
_KILL_GRACE_S = 5.0
_PORT_DEAD_GRACE_S = 15.0
_MEM_SETTLE_S = 3.0

#: Envelope estimate terms — deliberately conservative (the guard errs toward
#: refusing, mirroring ``harness.serve_lane``): weights ×1.2 for mmap/compute
#: buffers + ~0.2 GB KV per 1k ctx tokens (an ~8B-class lane) + a 4 GB floor.
_GGUF_FACTOR = 1.2
_KV_GB_PER_1K_CTX = 0.2
_FLOOR_GB = 4.0

_RECIPE_KINDS = ("llama-server", "vllm")


class LaunchRefused(RuntimeError):
    """A typed launch/teardown refusal — the deterministic brake (AE-R13).

    ``reason`` is machine-readable (``lane_resident`` · ``oom_envelope`` ·
    ``launch_in_progress`` · ``recipe_not_found`` · ``recipe_malformed`` ·
    ``binary_absent`` · ``gguf_absent`` · ``port_busy`` · ``launch_crashed`` ·
    ``warm_timeout`` · ``aborted`` · ``teardown_failed`` · ``infra_port``); the
    message renders on the failed Jobs card.
    """

    def __init__(self, reason: str, message: str) -> None:
        self.reason = reason
        super().__init__(f"refused:{reason} — {message}")


# --------------------------------------------------------------------------- #
# state paths — beside the AE-19 registry (FK_ARENA_LANE_DIR isolates tests)
# --------------------------------------------------------------------------- #
def _arena_dir() -> Path:
    d = os.environ.get("FK_ARENA_LANE_DIR")
    if d:
        return Path(os.path.expanduser(d))
    return Path(os.path.expanduser("~/.fieldkit/arena"))


def lane_recipes_path() -> Path:
    """The operator-authored recipes file (env ``FK_ARENA_LANE_RECIPES``)."""
    explicit = os.environ.get("FK_ARENA_LANE_RECIPES")
    if explicit:
        return Path(os.path.expanduser(explicit))
    return _arena_dir() / "lane-recipes.json"


def lane_owner_path(port: int) -> Path:
    """The owner file recording the process this runner spawned on ``port``."""
    return _arena_dir() / f"lane-owner-{int(port)}.json"


def read_lane_owner(port: int) -> Optional[dict[str, Any]]:
    """The owner record for ``port``, or None. Corrupt/missing → None."""
    p = lane_owner_path(port)
    try:
        v = json.loads(p.read_text())
        return v if isinstance(v, dict) else None
    except (OSError, ValueError):
        return None


def _write_owner(port: int, owner: dict[str, Any]) -> None:
    """Atomic owner-file write (tmp + os.replace — the GS-1 pattern)."""
    p = lane_owner_path(port)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + ".tmp")
    tmp.write_text(json.dumps(owner, indent=2, sort_keys=True))
    os.replace(tmp, p)


def _remove_owner(port: int) -> bool:
    try:
        lane_owner_path(port).unlink()
        return True
    except FileNotFoundError:
        return False


def infra_ports() -> set[int]:
    """Ports exempt from ONE-LANE and protected from teardown (AD-FK-1).

    Resolution: ``FK_ARENA_INFRA_PORTS`` (comma-separated) when SET — including
    set-but-empty, which means "no exemptions" (an operator must be able to turn
    the exemption off, unlike :func:`lanes.lane_ports` where empty falls back) —
    else :data:`DEFAULT_INFRA_PORTS`.
    """
    raw = os.environ.get("FK_ARENA_INFRA_PORTS")
    if raw is not None:
        return {int(t) for t in (s.strip() for s in raw.split(",")) if t.isdigit()}
    return set(DEFAULT_INFRA_PORTS)


# --------------------------------------------------------------------------- #
# recipes
# --------------------------------------------------------------------------- #
def load_lane_recipes() -> dict[str, dict[str, Any]]:
    """All recipes keyed by name. Missing file → ``{}``; bad JSON raises typed."""
    p = lane_recipes_path()
    if not p.is_file():
        return {}
    try:
        raw = json.loads(p.read_text())
    except (OSError, ValueError) as exc:
        raise LaunchRefused("recipe_malformed", f"{p} is not valid JSON: {exc}")
    if isinstance(raw, dict) and isinstance(raw.get("recipes"), list):
        raw = raw["recipes"]
    if not isinstance(raw, list):
        raise LaunchRefused(
            "recipe_malformed", f"{p} must be a JSON list of recipe objects"
        )
    out: dict[str, dict[str, Any]] = {}
    for item in raw:
        if isinstance(item, dict) and item.get("name"):
            out[str(item["name"])] = item
    return out


def _validate_recipe(rec: dict[str, Any]) -> dict[str, Any]:
    """Normalize one recipe; raise ``recipe_malformed`` on any bad field."""
    name = str(rec.get("name") or "")
    kind = str(rec.get("kind") or "llama-server")
    if kind not in _RECIPE_KINDS:
        raise LaunchRefused(
            "recipe_malformed", f"recipe {name!r}: kind must be one of {_RECIPE_KINDS}"
        )
    gguf = rec.get("gguf_path")
    if not isinstance(gguf, str) or not gguf or not os.path.isabs(gguf):
        raise LaunchRefused(
            "recipe_malformed",
            f"recipe {name!r}: gguf_path must be an absolute path (got {gguf!r})",
        )
    port = rec.get("port")
    if not isinstance(port, int) or not (0 < port < 65536):
        raise LaunchRefused("recipe_malformed", f"recipe {name!r}: port must be 1-65535")

    def _pos_int(key: str, default: int) -> int:
        v = rec.get(key, default)
        if not isinstance(v, int) or v <= 0:
            raise LaunchRefused(
                "recipe_malformed", f"recipe {name!r}: {key} must be a positive int"
            )
        return v

    warm = rec.get("warm_timeout", WARM_TIMEOUT_DEFAULT_S)
    if not isinstance(warm, (int, float)) or warm <= 0:
        raise LaunchRefused(
            "recipe_malformed", f"recipe {name!r}: warm_timeout must be positive"
        )
    extra = rec.get("extra_args", [])
    if not isinstance(extra, list) or not all(isinstance(a, str) for a in extra):
        raise LaunchRefused(
            "recipe_malformed", f"recipe {name!r}: extra_args must be a list of strings"
        )
    return {
        "name": name,
        "kind": kind,
        "gguf_path": gguf,
        "port": port,
        "n_ctx": _pos_int("n_ctx", 8192),
        "ngl": _pos_int("ngl", 99),
        "chat_template": rec.get("chat_template"),
        "reasoning_format": rec.get("reasoning_format"),
        "extra_args": list(extra),
        "warm_timeout": min(float(warm), WARM_TIMEOUT_CEILING_S),
    }


def recipe_summaries() -> list[dict[str, Any]]:
    """Card-safe recipe digests (no absolute-path leakage): name · model file ·
    port · n_ctx · whether the GGUF currently exists on disk."""
    out = []
    for name, rec in sorted(load_lane_recipes().items()):
        try:
            v = _validate_recipe(rec)
        except LaunchRefused as exc:
            out.append({"name": name, "valid": False, "error": str(exc)})
            continue
        out.append(
            {
                "name": name,
                "valid": True,
                "kind": v["kind"],
                "model_file": Path(v["gguf_path"]).name,
                "port": v["port"],
                "n_ctx": v["n_ctx"],
                "gguf_present": Path(v["gguf_path"]).is_file(),
            }
        )
    return out


# --------------------------------------------------------------------------- #
# pre-flight helpers
# --------------------------------------------------------------------------- #
#: Known-good CUDA llama-server build on the Spark (mirrors
#: ``notebook._KNOWN_LLAMA_SERVER``); module-level so tests can pin it away.
_KNOWN_LLAMA_SERVER = "/home/nvidia/llama.cpp/build/bin/llama-server"


def _find_server_binary() -> str:
    """The llama-server resolver (mirrors ``notebook._find_llama_server``):
    ``FIELDKIT_LLAMA_SERVER`` env → PATH → the known Spark build path."""
    for cand in (
        os.environ.get("FIELDKIT_LLAMA_SERVER"),
        shutil.which("llama-server"),
        _KNOWN_LLAMA_SERVER,
    ):
        if cand and Path(cand).exists():
            return cand
    raise LaunchRefused(
        "binary_absent",
        "llama-server not found (FIELDKIT_LLAMA_SERVER, PATH, known Spark path) — "
        "the exit-127 class of failure, caught pre-flight",
    )


def estimate_lane_gb(gguf_bytes: int, n_ctx: int) -> float:
    """Conservative resident-footprint estimate for a GGUF lane (GB)."""
    return round(
        gguf_bytes / 1e9 * _GGUF_FACTOR + (n_ctx / 1000.0) * _KV_GB_PER_1K_CTX + _FLOOR_GB,
        2,
    )


def _check_envelope(gguf_path: str, n_ctx: int, *, soft: bool = False) -> dict[str, Any]:
    """Envelope gate. ``soft=True`` (a ``teardown_first`` launch's *pre*-teardown
    pass) records the numbers without refusing — the authoritative check is the
    re-run against the *recovered* memory after the resident lane is freed."""
    gguf_bytes = Path(gguf_path).stat().st_size
    est = estimate_lane_gb(gguf_bytes, n_ctx)
    total, avail = _meminfo_gb()
    if not soft and avail is not None and est > avail:
        raise LaunchRefused(
            "oom_envelope",
            f"estimated {est:.1f} GB (weights ×{_GGUF_FACTOR} + KV@{n_ctx} + "
            f"{_FLOOR_GB:.0f} GB floor) exceeds {avail:.1f} GB MemAvailable — "
            "one lane at a time; tear the resident lane down first",
        )
    return {"estimated_gb": est, "available_gb": avail, "total_gb": total}


def _tcp_connectable(port: int, host: str = "127.0.0.1", timeout: float = 0.3) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _http_ok(url: str, timeout: float = 1.0) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:  # noqa: S310
            return 200 <= resp.status < 300
    except Exception:  # noqa: BLE001 — a cold/dead port is the common case
        return False


# --------------------------------------------------------------------------- #
# process observation — /proc, never trusted PIDs
# --------------------------------------------------------------------------- #
def _proc_cmdline(pid: int) -> Optional[list[str]]:
    """NUL-split argv for ``pid``, or None if gone/unreadable."""
    try:
        raw = Path(f"/proc/{pid}/cmdline").read_bytes()
    except OSError:
        return None
    return [t.decode("utf-8", "replace") for t in raw.split(b"\0") if t]


def _proc_stat(pid: int) -> Optional[tuple[str, int]]:
    """``(state, pgrp)`` from ``/proc/<pid>/stat``, or None if gone."""
    try:
        stat = Path(f"/proc/{pid}/stat").read_text()
    except OSError:
        return None
    # comm may contain spaces/parens — parse from the LAST ')'.
    rest = stat.rsplit(")", 1)[-1].split()
    try:
        return rest[0], int(rest[2])  # state, ppid, pgrp
    except (IndexError, ValueError):
        return None


def _proc_pgid(pid: int) -> Optional[int]:
    """The process group of ``pid``, or None if gone."""
    st = _proc_stat(pid)
    return st[1] if st else None


def _pgid_members(pgid: int) -> list[int]:
    """Every LIVE pid whose pgrp is ``pgid`` (the orphan-group sweep).

    Zombies are skipped: a dead-but-unreaped child keeps its /proc entry until
    the parent waits, yet holds no memory and no port — counting it would
    dishonestly fail the released gate forever."""
    out = []
    try:
        entries = list(Path("/proc").iterdir())
    except OSError:
        return out
    for p in entries:
        if not p.name.isdigit():
            continue
        st = _proc_stat(int(p.name))
        if st and st[1] == pgid and st[0] != "Z":
            out.append(int(p.name))
    return out


def _owner_cmdline_matches(owner: dict[str, Any], argv: list[str]) -> bool:
    """PID-reuse guard: the live argv must still look like the lane we spawned —
    the right binary family AND the recipe's model path among the args.

    The family check spans the first two argv entries: a shebang'd wrapper
    script execs as ``interpreter script-path …``, so the binary name lands in
    ``argv[1]`` (the real ELF llama-server keeps it in ``argv[0]``)."""
    if not argv:
        return False
    kind = str(owner.get("kind") or "llama-server")
    needle = "vllm" if kind == "vllm" else "llama-server"
    family_ok = any(needle in Path(a).name for a in argv[:2])
    gguf = str(owner.get("gguf_path") or "")
    return family_ok and (not gguf or gguf in argv)


def _killpg_graceful(pgid: int) -> bool:
    """SIGTERM → grace → SIGKILL the group; True iff no live member remains.

    Gone-ness is decided by the zombie-skipping /proc scan, NOT ``killpg(pgid,
    0)`` — signalling a zombie-only group still succeeds, which would spin the
    grace loop against a process that is already dead."""
    for sig, grace in ((signal.SIGTERM, _TERM_GRACE_S), (signal.SIGKILL, _KILL_GRACE_S)):
        try:
            os.killpg(pgid, sig)
        except ProcessLookupError:
            return True
        except PermissionError:
            return False
        deadline = time.monotonic() + grace
        while time.monotonic() < deadline:
            if not _pgid_members(pgid):
                return True
            time.sleep(0.5)
    return not _pgid_members(pgid)


def _scan_lane_procs(port: int, gguf_path: Optional[str]) -> list[tuple[int, int]]:
    """Targeted fallback scan: (pid, pgid) for processes that look like OUR lane —
    the serve binary family AND ``--port <port>`` (AND the gguf when known).
    Deliberately conjunctive: never a broad ``pkill -f llama`` (P1-3)."""
    hits: list[tuple[int, int]] = []
    try:
        entries = list(Path("/proc").iterdir())
    except OSError:
        return hits
    for p in entries:
        if not p.name.isdigit():
            continue
        pid = int(p.name)
        argv = _proc_cmdline(pid)
        if not argv:
            continue
        # the family name may ride argv[1] for a shebang'd wrapper (see
        # _owner_cmdline_matches)
        if not any("llama-server" in Path(a).name or "vllm" in Path(a).name for a in argv[:2]):
            continue
        joined = argv[1:]
        port_ok = False
        for i, a in enumerate(joined):
            if a in ("--port", "-p") and i + 1 < len(joined) and joined[i + 1] == str(port):
                port_ok = True
            if a == f"--port={port}":
                port_ok = True
        if not port_ok:
            continue
        if gguf_path and gguf_path not in joined:
            continue
        pgid = _proc_pgid(pid)
        if pgid is not None:
            hits.append((pid, pgid))
    return hits


# --------------------------------------------------------------------------- #
# teardown (AE-31) — observed release, honest revert
# --------------------------------------------------------------------------- #
def teardown_lane(port: int) -> dict[str, Any]:
    """Tear down the lane on ``port``; verify release; honest-revert the registry.

    "Released" is **observed**: the spawned process group is empty AND the port
    refuses connections. The ``MemAvailable`` delta is informational only (page
    cache noise). Raises ``LaunchRefused("teardown_failed")`` when the port still
    answers after the kill chain — never a false "freed".

    Infra ports (AD-FK-1) refuse up front: the embedder is a docker container
    whose port is published by docker-proxy — the lane kill chain was never
    designed for it. Manage it with its own lifecycle (``docker stop/start``).
    """
    port = int(port)
    if port in infra_ports():
        raise LaunchRefused(
            "infra_port",
            f":{port} is an infrastructure lane (Cortex-embedder class; "
            "FK_ARENA_INFRA_PORTS) — manage it via its own lifecycle "
            "(docker stop/start), never the lane kill chain",
        )
    _, pre_avail = _meminfo_gb()
    owner = read_lane_owner(port)
    method = "none"
    notes: list[str] = []
    kind = str((owner or {}).get("kind") or "llama-server")

    pgids: list[int] = []
    if owner and isinstance(owner.get("pid"), int):
        pid = owner["pid"]
        argv = _proc_cmdline(pid)
        if argv is None:
            notes.append("owner pid already gone")
        elif _owner_cmdline_matches(owner, argv):
            pgid = owner.get("pgid") if isinstance(owner.get("pgid"), int) else _proc_pgid(pid)
            if pgid is not None:
                pgids.append(pgid)
                method = "owner-killpg"
        else:
            # PID reuse — the pid is alive but it is NOT our lane. Never kill it.
            notes.append(f"owner pid {pid} reused by another process — not killed")
    if not pgids:
        scan = _scan_lane_procs(port, (owner or {}).get("gguf_path"))
        if scan:
            pgids = sorted({pg for _, pg in scan})
            method = "targeted-scan"

    already_dead = not pgids and not _tcp_connectable(port)

    for pgid in pgids:
        if not _killpg_graceful(pgid):
            notes.append(f"process group {pgid} survived SIGKILL")
    if kind == "vllm" and pgids:
        # The EngineCore orphan holds ~108 GB past a plain group kill
        # (feedback_vllm_engine_core_orphan) — run the proven sweep.
        from fieldkit._rl_gpu_serve import DEFAULT_STOP_CMD

        subprocess.run(DEFAULT_STOP_CMD, shell=True, check=False)
        method += "+enginecore-sweep"

    # --- the released gate: port must go dead (observed, polled) -------------
    deadline = time.monotonic() + _PORT_DEAD_GRACE_S
    port_dead = False
    while time.monotonic() < deadline:
        if not _tcp_connectable(port) and lanes.probe_port(port) is None:
            port_dead = True
            break
        time.sleep(0.5)
    pgid_empty = all(not _pgid_members(pg) for pg in pgids) if pgids else True

    freed_gb: Optional[float] = None
    if port_dead and not already_dead:
        time.sleep(_MEM_SETTLE_S)
        _, post_avail = _meminfo_gb()
        if pre_avail is not None and post_avail is not None:
            freed_gb = round(post_avail - pre_avail, 2)

    owner_removed = _remove_owner(port)
    registry_cleared = False
    reg = lanes.load_active_lane()
    if reg and reg.get("port") == port:
        lanes.clear_active_lane()
        registry_cleared = True

    if not port_dead:
        raise LaunchRefused(
            "teardown_failed",
            f":{port} still answers after the kill chain (method {method}; "
            f"{'; '.join(notes) or 'no notes'}) — inspect the box",
        )
    return {
        "port": port,
        "method": method,
        "already_dead": already_dead,
        "port_dead": port_dead,
        "pgid_empty": pgid_empty,
        "freed_gb": freed_gb,
        "owner_removed": owner_removed,
        "registry_cleared": registry_cleared,
        "model": (owner or {}).get("model")
        or (Path(str((owner or {}).get("gguf_path"))).name if owner else None),
        "notes": notes or None,
    }


# --------------------------------------------------------------------------- #
# launch (AE-31)
# --------------------------------------------------------------------------- #
def _build_argv(binary: str, rec: dict[str, Any]) -> list[str]:
    """The llama-server argv (mirrors ``notebook._build_llama_server_cmd``)."""
    cmd = [
        binary,
        "-m",
        rec["gguf_path"],
        "--host",
        "127.0.0.1",
        "--port",
        str(rec["port"]),
        "-ngl",
        str(rec["ngl"]),
        "-c",
        str(rec["n_ctx"]),
    ]
    ct = rec.get("chat_template")
    if ct in (None, "jinja", "auto"):
        cmd.append("--jinja")
    else:
        cmd += ["--chat-template", str(ct)]
    if rec.get("reasoning_format"):
        cmd += ["--reasoning-format", str(rec["reasoning_format"])]
    cmd += rec["extra_args"]
    return cmd


def _log_tail(path: Path, n: int = 12) -> str:
    try:
        return "\n".join(path.read_text(errors="replace").splitlines()[-n:])
    except OSError:
        return "(no log)"


def launch_lane(
    recipe: str,
    *,
    teardown_first: bool = False,
    select_on_warm: bool = True,
    should_abort: Optional[Callable[[], bool]] = None,
) -> dict[str, Any]:
    """Launch the named recipe's lane, guarded; return the launch digest.

    Pre-flight order (every fallible-but-side-effect-free check before the one
    destructive step): launch lock → recipe → binary → GGUF → envelope → fused
    ONE-LANE/port. ``teardown_first`` is the only path that touches a resident
    lane, and the envelope re-checks against the *recovered* memory after it.
    The spawned process is detached (survives sidecar restarts); ``should_abort``
    (the BUG-2 sentinel poller) only aborts the *warm-poll*, never the lane.
    """
    lock_path = _arena_dir() / LAUNCH_LOCK_NAME
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_f = open(lock_path, "a+")
    try:
        try:
            fcntl.flock(lock_f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            raise LaunchRefused(
                "launch_in_progress", "another lane launch holds the launch lock"
            )

        # 2. recipe
        recipes = load_lane_recipes()
        if recipe not in recipes:
            raise LaunchRefused(
                "recipe_not_found",
                f"no recipe {recipe!r} in {lane_recipes_path()} "
                f"(known: {sorted(recipes) or 'none — author the file'})",
            )
        rec = _validate_recipe(recipes[recipe])
        if rec["kind"] != "llama-server":
            raise LaunchRefused(
                "recipe_malformed",
                f"recipe {recipe!r}: only llama-server launch is implemented "
                "(vLLM lanes stay the RL arbiter's job)",
            )
        port = rec["port"]

        # 3. binary — the cheapest hard gate, BEFORE any teardown.
        binary = _find_server_binary()

        # 4. gguf on disk
        if not Path(rec["gguf_path"]).is_file():
            raise LaunchRefused("gguf_absent", f"{rec['gguf_path']} does not exist")

        # 5. envelope — soft when a teardown_first will free memory; the
        # post-teardown re-check below is then the authoritative gate.
        envelope = _check_envelope(rec["gguf_path"], rec["n_ctx"], soft=teardown_first)

        # 6. ONE-LANE + port, fused — sweep includes the target port (P0-3).
        # Infra ports (AD-FK-1) are filtered out of the resident set: the Cortex
        # embedder must neither trip ONE-LANE nor be reaped by teardown_first.
        # If the TARGET port is itself infra-exempt and busy, the port_busy gate
        # below still refuses — the exemption never makes a launch less safe.
        exempt = infra_ports()
        sweep = sorted(set(lanes.lane_ports()) | {port})
        discovered = [l for l in lanes.discover(sweep) if l.get("port") not in exempt]
        teardowns: list[dict[str, Any]] = []
        if discovered:
            roster = ", ".join(f"{l.get('model')}:{l.get('port')}" for l in discovered)
            if not teardown_first:
                raise LaunchRefused(
                    "lane_resident",
                    f"lane(s) resident — {roster}. One lane at a time; pass "
                    "teardown_first to replace",
                )
            for live in discovered:
                teardowns.append(teardown_lane(int(live["port"])))
            if [l for l in lanes.discover(sweep) if l.get("port") not in exempt]:
                raise LaunchRefused(
                    "lane_resident", "a lane is still resident after teardown_first"
                )
        if teardown_first:
            # the whole point of teardown_first is to make room — the hard gate
            # runs against the *recovered* memory (also covers the nothing-to-
            # tear-down case, where the soft pass above never enforced).
            envelope = _check_envelope(rec["gguf_path"], rec["n_ctx"])
        if _tcp_connectable(port):
            raise LaunchRefused(
                "port_busy", f":{port} is held by a non-lane process — free it first"
            )

        # 7. spawn detached + atomic owner file immediately after (P1-4).
        log_dir = _arena_dir() / "lane-logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        log_path = log_dir / f"{rec['name']}-{port}.log"
        argv = _build_argv(binary, rec)
        log_f = open(log_path, "ab")
        try:
            proc = subprocess.Popen(  # noqa: S603 — operator-authored recipe argv
                argv, stdout=log_f, stderr=subprocess.STDOUT, start_new_session=True
            )
        finally:
            log_f.close()  # the child keeps its inherited fd (P2-2)
        started_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        owner = {
            "pid": proc.pid,
            "pgid": proc.pid,  # start_new_session ⇒ group leader
            "recipe": rec["name"],
            "kind": rec["kind"],
            "gguf_path": rec["gguf_path"],
            "port": port,
            "log_path": str(log_path),
            "started_at": started_at,
        }
        _write_owner(port, owner)

        # 8. warm-poll — poll() fast-fail + sentinel abort (BUG-2 lesson).
        t0 = time.monotonic()
        deadline = t0 + rec["warm_timeout"]
        lane_seen: Optional[dict[str, Any]] = None
        while time.monotonic() < deadline:
            rc = proc.poll()
            if rc is not None:
                _remove_owner(port)
                raise LaunchRefused(
                    "launch_crashed",
                    f"llama-server exited {rc} during warm-up. Log tail:\n"
                    f"{_log_tail(log_path)}",
                )
            if should_abort is not None and should_abort():
                raise LaunchRefused(
                    "aborted",
                    f"warm-poll aborted (teardown sentinel); the detached lane on "
                    f":{port} may still come up — watch discovery or tear it down",
                )
            if _http_ok(f"http://127.0.0.1:{port}/health"):
                lane_seen = lanes.probe_port(port, timeout=1.0)
                if lane_seen:
                    break
            time.sleep(1.0)
        if lane_seen is None:
            raise LaunchRefused(
                "warm_timeout",
                f"not warm after {rec['warm_timeout']:.0f}s — lane left loading "
                f"(owner file kept); watch discovery or dispatch lane_teardown :{port}",
            )
        warm_seconds = round(time.monotonic() - t0, 1)
        owner["warm_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        owner["model"] = lane_seen.get("model")
        _write_owner(port, owner)

        # 9. select/anchor — the AE-19 shape POST /api/active-lane writes.
        selected = False
        if select_on_warm:
            lanes.save_active_lane(
                {
                    "model": lane_seen.get("model"),
                    "base_url": lane_seen.get("base_url"),
                    "port": port,
                    "source": "operator-selected",
                    "set_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                }
            )
            selected = True

        return {
            "recipe": rec["name"],
            "model": lane_seen.get("model"),
            "model_file": Path(rec["gguf_path"]).name,
            "port": port,
            "base_url": lane_seen.get("base_url"),
            "pid": proc.pid,
            "warm_seconds": warm_seconds,
            "estimated_gb": envelope.get("estimated_gb"),
            "available_gb_before": envelope.get("available_gb"),
            "selected": selected,
            "teardown_first": teardowns or None,
            "log_path": str(log_path),
        }
    finally:
        try:
            fcntl.flock(lock_f.fileno(), fcntl.LOCK_UN)
        except OSError:
            pass
        lock_f.close()
