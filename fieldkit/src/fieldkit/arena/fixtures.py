"""Demo-fixture recorder — turns real, operator-captured Arena runs into a
self-contained replay bundle so the cockpit is interactive WITHOUT a sidecar.

The public web preview has no FastAPI sidecar, so the live surfaces (chat,
compare, telemetry) normally degrade to an offline banner. This module records
a curated slice of the *real* runs in ``~/.fieldkit/arena.db`` into a single
static JSON the client replays — same SSE wire format, real answers, real
measured TTFT/throughput, with the per-token cadence synthesized from the
measured ``tok_per_s``. The browser plays it back token-by-token so it *feels*
live while being 100% static and distributable.

Leak discipline (mirrors ``mirror.py``): this exporter does NOT bulk-dump the
DB. It selects a small curated set of showcase runs and writes only the fields
the replay needs. It is meant for *deliberately chosen* golden interactions —
not "recent chat" — so review the output before publishing. Telemetry is
synthesized deterministically (no telemetry_samples table exists) from
GB10-plausible envelopes, so the committed fixture is stable across runs.
"""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from fieldkit.arena.mirror import _atomic_write_json, _utc_now_iso
from fieldkit.arena.store import ArenaStore

FIXTURE_SCHEMA_VERSION = 1

#: Read-only GET endpoints whose live responses we bake as canned stubs so the
#: cockpit's lane pickers / activity feed / benches render fully on the public
#: preview. Captured from a running sidecar, then sanitized (below).
_STUB_ENDPOINTS = (
    "healthz",
    "api/lanes",
    "api/compare/options",
    "api/rubrics",
    "api/eval/benches",
    "api/activity",
    "api/chat/sessions",
    "api/lab/notes",
    # Feature panes that rendered "Cockpit offline" on the demo until these
    # were recorded (build spine, training flow, jobs board, standup, models,
    # settings, live leaderboard).
    "api/build",
    "api/corpus-progress",
    "api/runtimes",
    "api/sft-progress",
    "api/reward-signal",
    "api/standup",
    "api/jobs",
    "api/leaderboard/live",
    "api/active-lane",
    "api/lane-recipes",
    "api/guardrail-config",
    "api/prices",
)

#: Host-specific keys stripped from every captured stub — same discipline as
#: ``mirror.py``'s lane redaction (no local paths, ports, or base URLs leak).
_FORBIDDEN_STUB_KEYS = frozenset(
    {
        "base_url",
        "config_path",
        "config_mtime",
        "port",
        "start_script",
        "stop_script",
        "repo_root",
        "db",
        "db_path",
    }
)

#: Absolute host paths anywhere in a captured value — including INSIDE embedded
#: JSON strings (jobs/standup ``result_json``) and markdown blobs
#: (``lineage_card``) — are reduced to their basename. A model path like
#: ``/home/nvidia/data/astro-train-lora/p65-nemo/merged-hf-bf16-fixed`` becomes
#: ``merged-hf-bf16-fixed``: still meaningful, no host layout leaked.
_HOST_PATH_RE = re.compile(r"/(?:home|Users|root|tmp|var|opt|mnt|data)/[^\s\"'\)\],}]*")


def _scrub_str(s: str) -> str:
    """Collapse absolute host paths inside a string value to their basename."""

    def _basename(m: re.Match[str]) -> str:
        tail = m.group(0).rstrip("/").rsplit("/", 1)[-1]
        return tail or "redacted"

    return _HOST_PATH_RE.sub(_basename, s)

#: Prompts that are scaffolding/smoke noise, never showcase material.
_JUNK_PROMPTS = {
    "test hero seed flow",
    "reply with exactly: ok",
    "ping",
    "test",
}

#: Minimum assistant tokens for a chat turn to be worth replaying.
_MIN_CHAT_TOKENS = 30

#: Watchable per-chunk cadence bounds (ms). Real tok/s can be 100+, which is
#: too fast to read; clamp so the replay reads like a brisk live stream.
_MIN_CHUNK_MS = 9.0
_MAX_CHUNK_MS = 90.0

#: Synthetic telemetry envelope for the GB10 (128 GB unified). Idle vs inflight
#: profiles; the client overlays the live tok/s during a replay.
_UNIFIED_TOTAL_GB = 128.0


def _sanitize(obj: Any) -> Any:
    """Recursively drop host-specific keys from a captured stub response and
    scrub absolute host paths out of every surviving string value (they hide
    inside ``result_json`` strings and ``lineage_card`` markdown too)."""
    if isinstance(obj, dict):
        return {
            k: _sanitize(v)
            for k, v in obj.items()
            if k not in _FORBIDDEN_STUB_KEYS
        }
    if isinstance(obj, list):
        return [_sanitize(v) for v in obj]
    if isinstance(obj, str):
        return _scrub_str(obj)
    return obj


def _capture_stubs(sidecar_url: str) -> dict[str, Any]:
    """GET each read-only endpoint from a running sidecar and sanitize it.

    Returns ``{ "/healthz": {...}, "/api/lanes": {...}, ... }`` (path keyed,
    leading slash) for endpoints that answered 200. Missing/unreachable
    endpoints are simply omitted — the client shim falls back to a minimal stub.
    """
    base = sidecar_url.rstrip("/")
    stubs: dict[str, Any] = {}
    for ep in _STUB_ENDPOINTS:
        url = f"{base}/{ep}"
        try:
            with urllib.request.urlopen(url, timeout=5) as resp:  # noqa: S310
                if resp.status != 200:
                    continue
                data = json.loads(resp.read().decode("utf-8"))
        except (urllib.error.URLError, ValueError, TimeoutError, OSError):
            continue
        stubs[f"/{ep}"] = _sanitize(data)
    return stubs


@dataclass
class FixtureReport:
    out_path: str
    chat: int = 0
    compare: int = 0
    telemetry_samples: int = 0
    stubs: int = 0
    lanes_seen: set[str] = field(default_factory=set)
    skipped: int = 0

    def summary_line(self) -> str:
        return (
            f"{self.chat} chat · {self.compare} compare · "
            f"{self.telemetry_samples} telemetry samples · {self.stubs} stubs "
            f"({len(self.lanes_seen)} lanes; {self.skipped} skipped)"
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "out_path": self.out_path,
            "chat": self.chat,
            "compare": self.compare,
            "telemetry_samples": self.telemetry_samples,
            "stubs": self.stubs,
            "lanes": sorted(self.lanes_seen),
            "skipped": self.skipped,
        }


# --------------------------------------------------------------------------- #
# Token-cadence synthesis
# --------------------------------------------------------------------------- #

def _chunk_text(text: str) -> list[str]:
    """Split text into stream-like pieces: whitespace runs and word fragments.

    Long words are broken into ~4-char pieces so the replay drips like real
    subword token streaming rather than landing whole words at once.
    """
    pieces: list[str] = []
    for unit in re.findall(r"\s+|\S+", text):
        if unit.isspace() or len(unit) <= 5:
            pieces.append(unit)
            continue
        for i in range(0, len(unit), 4):
            pieces.append(unit[i : i + 4])
    return [p for p in pieces if p != ""]


def _stream_events(
    *,
    content: str,
    reasoning: str | None,
    ttft_ms: float | None,
    tok_per_s: float | None,
    tokens_out: int | None,
    channel_prefix: str,
    start_event: str,
    start_data: dict[str, Any],
    done_event: str,
    done_data: dict[str, Any],
) -> list[dict[str, Any]]:
    """Build a timestamped SSE-event list for one streamed turn.

    ``t`` is a millisecond offset from the turn's start. Token cadence is
    derived from the real ``tok_per_s`` (clamped to a readable range).
    """
    events: list[dict[str, Any]] = [{"t": 0, "event": start_event, "data": start_data}]
    t = float(ttft_ms or 200.0)

    def emit(blocks: str, channel: str) -> None:
        nonlocal t
        chunks = _chunk_text(blocks)
        if not chunks:
            return
        rate = tok_per_s if (tok_per_s and tok_per_s > 1) else 45.0
        # total stream seconds for this block ≈ chunk count / rate, spread evenly
        per = max(_MIN_CHUNK_MS, min(_MAX_CHUNK_MS, 1000.0 / rate))
        for ch in chunks:
            events.append(
                {
                    "t": round(t, 1),
                    "event": f"token{channel_prefix}",
                    "data": {"channel": channel, "text": ch},
                }
            )
            t += per

    if reasoning:
        emit(reasoning, "reasoning")
    emit(content, "content")

    done = dict(done_data)
    done.setdefault("ttft_ms", ttft_ms)
    done.setdefault("tok_per_s", tok_per_s)
    done.setdefault("tokens_out", tokens_out)
    events.append({"t": round(t + 30, 1), "event": done_event, "data": done})
    return events


# --------------------------------------------------------------------------- #
# Telemetry synthesis (deterministic — no telemetry_samples table exists)
# --------------------------------------------------------------------------- #

def _synth_telemetry(resident_lane: str, resident_used_gb: float) -> dict[str, Any]:
    """A deterministic ~30 s idle loop. The client raises gpu_util / temp and
    overlays live tok/s while a chat or compare replay is inflight.
    """
    import math

    samples: list[dict[str, Any]] = []
    step_ms = 500
    n = 60  # 30 s loop
    for i in range(n):
        # gentle deterministic idle jitter via sine — stable across exports
        phase = i / n * 2 * math.pi
        gpu = round(3.0 + 3.5 * (1 + math.sin(phase * 2)) / 2, 1)  # ~3–6.5%
        temp = round(46.0 + 4.0 * (1 + math.sin(phase)) / 2, 1)  # ~46–50 °C
        mem = round(resident_used_gb + 0.3 * math.sin(phase * 3), 2)
        samples.append(
            {
                "t": i * step_ms,
                "data": {
                    "gpu_util": gpu,
                    "gpu_temp_c": temp,
                    "unified_used_gb": mem,
                    "unified_total_gb": _UNIFIED_TOTAL_GB,
                    "inflight": False,
                    "tok_per_s": None,
                    "ttft_ms": None,
                    "lane_id": None,
                    "resident_lane": resident_lane,
                    "openrouter_cost_usd": 0.0,
                    "openrouter_calls": 0,
                },
            }
        )
    return {
        "loop_ms": n * step_ms,
        "step_ms": step_ms,
        # the client multiplies idle values by these during a replay
        "inflight_profile": {
            "gpu_util": [88.0, 99.0],
            "gpu_temp_c": [68.0, 79.0],
            "mem_bump_gb": 2.4,
        },
        "samples": samples,
    }


# --------------------------------------------------------------------------- #
# Selection helpers
# --------------------------------------------------------------------------- #

def _is_junk(prompt: str) -> bool:
    return prompt.strip().lower() in _JUNK_PROMPTS


def _model_for_lane(lane_map: dict[str, str], lane_id: str | None) -> str:
    if not lane_id:
        return "local model"
    if lane_id in lane_map:
        return lane_map[lane_id]
    # lane ids can carry a ::variant suffix; try the base
    base = lane_id.split("::", 1)[0]
    return lane_map.get(base, lane_id)


# --------------------------------------------------------------------------- #
# Public entry point
# --------------------------------------------------------------------------- #

def _apply_overlay(payload: dict[str, Any], overlay: dict[str, Any]) -> None:
    """Merge a hand-authored showcase overlay over the recorded payload.

    The overlay is the *simulated-data* layer (operator decision 2026-06-07):
    hand-authored stubs grounded in past real runs, kept in a checked-in JSON
    so future re-records don't lose the showcase. Semantics: ``stubs`` merges
    per-endpoint (overlay endpoint replaces recorded endpoint wholesale); any
    other top-level key (``knowledge``, ``note``, …) replaces the recorded
    value. Overlay content is reviewed by hand — it is NOT re-sanitized; the
    deploy verifier's leak scan is the backstop.
    """
    for key, value in overlay.items():
        if key == "stubs" and isinstance(value, dict):
            payload.setdefault("stubs", {}).update(value)
        else:
            payload[key] = value


def record_demo_fixtures(
    *,
    db_path: str,
    out_path: str,
    repo_root: str | None = None,
    max_chat: int = 5,
    max_compare: int = 3,
    sidecar_url: str = "http://127.0.0.1:7866",
    stubs_overlay: str | None = None,
) -> FixtureReport:
    """Record a curated demo-replay bundle to ``out_path`` (a JSON file)."""
    root = Path(repo_root).expanduser() if repo_root else Path.cwd()
    final = Path(out_path)
    if not final.is_absolute():
        final = root / final
    staging = final.parent / "_staging" / final.name

    store = ArenaStore(db_path)
    store.initialize()
    report = FixtureReport(out_path=str(final))

    with store:
        lane_map = {r["id"]: r["model"] for r in store.lanes()}
        resident_lane = next(
            (lid for lid in lane_map if "resident" in lid), "resident-brain"
        )

        chat_fixtures = _collect_chat(store, lane_map, max_chat, report)
        compare_fixtures = _collect_compare(store, lane_map, max_compare, report)
        report.chat = len(chat_fixtures)
        report.compare = len(compare_fixtures)

        # resident model footprint for the idle telemetry baseline (Qwen3-30B
        # Q4 ≈ 18 GB resident); fall back to a sane default.
        telemetry = _synth_telemetry(resident_lane, resident_used_gb=18.6)
        report.telemetry_samples = len(telemetry["samples"])

    # Bake sanitized stub responses for the read-only endpoints (lane pickers,
    # activity feed, benches) from the live sidecar if reachable.
    stubs = _capture_stubs(sidecar_url)
    report.stubs = len(stubs)

    payload = {
        "schema_version": FIXTURE_SCHEMA_VERSION,
        "generated_at": _utc_now_iso(),
        "source": "fieldkit arena record",
        "note": (
            "Curated replay of real DGX Spark runs. Answers + measured TTFT and "
            "throughput are real; per-token cadence is synthesized from the "
            "measured tok/s. No sidecar required."
        ),
        "resident_lane": resident_lane,
        "chat": chat_fixtures,
        "compare": compare_fixtures,
        "telemetry": telemetry,
        "stubs": stubs,
    }

    if stubs_overlay:
        overlay_path = Path(stubs_overlay).expanduser()
        if not overlay_path.is_absolute():
            overlay_path = root / overlay_path
        overlay = json.loads(overlay_path.read_text(encoding="utf-8"))
        _apply_overlay(payload, overlay)
        report.stubs = len(payload.get("stubs", {}))

    _atomic_write_json(staging, final, payload)
    return report


def _collect_chat(
    store: ArenaStore,
    lane_map: dict[str, str],
    limit: int,
    report: FixtureReport,
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    seen_prompts: set[str] = set()
    for sess in store.recent_chat_sessions(limit=64):
        turns = sorted(store.chat_turns(sess["id"]), key=lambda t: t["ord"])
        # pair the LAST exchange: the final assistant turn and the user turn
        # immediately preceding it (multi-turn sessions otherwise mismatch the
        # opening prompt with a much later answer).
        asst = next((t for t in reversed(turns) if t["role"] == "assistant"), None)
        user = None
        if asst is not None:
            user = next(
                (
                    t
                    for t in reversed(turns)
                    if t["role"] == "user" and t["ord"] < asst["ord"]
                ),
                None,
            )
        if not user or not asst:
            report.skipped += 1
            continue
        prompt = (user["content"] or "").strip()
        content = (asst["content"] or "").strip()
        key = prompt.lower()
        if (
            not prompt
            or not content
            or _is_junk(prompt)
            or key in seen_prompts
            or (asst["tokens_out"] or 0) < _MIN_CHAT_TOKENS
            or content.lower().startswith("i don't have access")
        ):
            report.skipped += 1
            continue
        seen_prompts.add(key)
        lane_id = sess["lane_id"]
        model = _model_for_lane(lane_map, lane_id)
        report.lanes_seen.add(lane_id)
        events = _stream_events(
            content=content,
            reasoning=asst["reasoning"] if "reasoning" in asst.keys() else None,
            ttft_ms=asst["ttft_ms"],
            tok_per_s=asst["tok_per_s"],
            tokens_out=asst["tokens_out"],
            channel_prefix="",
            start_event="start",
            start_data={
                "session_id": "demo",
                "model": model,
                "base_url": "local",
                "lane_id": lane_id,
                "context_length": 64000,
            },
            done_event="done",
            done_data={"turn_id": -1, "finish_reason": asst["finish_reason"] or "stop"},
        )
        out.append(
            {
                "prompt": prompt,
                "lane_id": lane_id,
                "model": model,
                "events": events,
            }
        )
        if len(out) >= limit:
            break
    return out


def _collect_compare(
    store: ArenaStore,
    lane_map: dict[str, str],
    limit: int,
    report: FixtureReport,
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for recent in store.recent_compare_runs(limit=32):
        run_id = recent["id"]
        # recent_compare_runs() redacts the prompt; fetch the full header for
        # this curated, deliberately-published showcase run.
        run = store.compare_run(run_id)
        if not run:
            report.skipped += 1
            continue
        responses = {r["side"]: r for r in store.compare_responses(run_id)}
        a, b = responses.get("A"), responses.get("B")
        prompt = (run["prompt"] or "").strip()
        key = prompt.lower()
        if not a or not b or not prompt or _is_junk(prompt) or key in seen:
            report.skipped += 1
            continue
        if not (a["content"] or "").strip() or not (b["content"] or "").strip():
            report.skipped += 1
            continue
        seen.add(key)
        scores = store.rubric_scores_for_run(run_id)
        score_by_side = {s["side"]: s for s in scores}
        report.lanes_seen.add(a["lane_id"])
        report.lanes_seen.add(b["lane_id"])

        events: list[dict[str, Any]] = []
        ev_a = _stream_events(
            content=a["content"],
            reasoning=a["reasoning"] if "reasoning" in a.keys() else None,
            ttft_ms=a["ttft_ms"],
            tok_per_s=a["tok_per_s"],
            tokens_out=a["tokens_out"],
            channel_prefix="_a",
            start_event="start_a",
            start_data={
                "run_id": "demo",
                "rubric_id": run["rubric_id"],
                "lane_id": a["lane_id"],
                "model": _model_for_lane(lane_map, a["lane_id"]),
                "base_url": "local",
                "side": "A",
            },
            done_event="done_a",
            done_data={"finish_reason": "stop"},
        )
        # B starts after A finishes
        offset = ev_a[-1]["t"] + 120
        ev_b = _stream_events(
            content=b["content"],
            reasoning=b["reasoning"] if "reasoning" in b.keys() else None,
            ttft_ms=b["ttft_ms"],
            tok_per_s=b["tok_per_s"],
            tokens_out=b["tokens_out"],
            channel_prefix="_b",
            start_event="start_b",
            start_data={
                "lane_id": b["lane_id"],
                "model": _model_for_lane(lane_map, b["lane_id"]),
                "base_url": "local",
                "no_key": False,
            },
            done_event="done_b",
            done_data={"finish_reason": "stop"},
        )
        for e in ev_b:
            e["t"] = round(e["t"] + offset, 1)
        events = ev_a + ev_b

        def _score_payload(side: str) -> dict[str, Any]:
            s = score_by_side.get(side)
            if not s:
                return {"total": 0, "checks": []}
            try:
                checks = json.loads(s["checks_json"]) if s["checks_json"] else []
            except (ValueError, TypeError):
                checks = []
            return {"total": s["total"], "checks": checks}

        score_t = events[-1]["t"] + 150
        events.append(
            {
                "t": round(score_t, 1),
                "event": "score",
                "data": {
                    "rubric_id": run["rubric_id"],
                    "a": _score_payload("A"),
                    "b": _score_payload("B"),
                },
            }
        )
        out.append(
            {
                "prompt": prompt,
                "lane_a": a["lane_id"],
                "lane_b": b["lane_id"],
                "events": events,
            }
        )
        if len(out) >= limit:
            break
    return out
