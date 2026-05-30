# Copyright 2026 Manav Sehgal
# SPDX-License-Identifier: Apache-2.0
"""Tests for `fieldkit.arena.server` — M3 surface.

Covers the FastAPI app factory, the three M3 GET endpoints, and the
`TelemetryHub` reference-counter contract (sampler starts on first
subscriber, stops on last). The SSE endpoint is exercised via
`httpx.AsyncClient` + a short-window `stream` cycle; we never sit on
the live stream for more than a fraction of a second.
"""

from __future__ import annotations

import asyncio
import json
import os
import textwrap
import threading
import time
from pathlib import Path

import pytest

# Skip the whole module cleanly if the `arena` extra isn't installed —
# matches how `test_store.py` already guards on `aiosqlite` availability
# patterns. The dev venv always has them; CI installs the extra.
fastapi = pytest.importorskip("fastapi")
httpx = pytest.importorskip("httpx")

from fastapi.testclient import TestClient  # noqa: E402

from fieldkit.arena import (  # noqa: E402
    ARENA_SURFACE_VERSION,
    DEFAULT_ARENA_PORT,
)
from fieldkit.arena.server import (  # noqa: E402
    TelemetryHub,
    _read_hermes_lane,
    create_app,
)


@pytest.fixture
def repo_root(tmp_path: Path) -> Path:
    """A fixture repo with the mirror JSON wired up the way M2 writes it."""
    mirror_dir = tmp_path / "src" / "data" / "arena-mirror"
    mirror_dir.mkdir(parents=True)
    (mirror_dir / "leaderboard.json").write_text(
        json.dumps(
            {
                "version": 1,
                "rows": [
                    {
                        "bench_id": "fixture-bench",
                        "lane_id": "fixture-lane-a",
                        "manifest_slug": None,
                        "n_runs": 5,
                        "mean_score": 0.9,
                        "median_tok_per_s": 83.5,
                        "mean_ttft_ms": 460,
                        "human_pref_winrate": None,
                        "last_run_at": "2026-05-28T15:00:00Z",
                    },
                    {
                        "bench_id": "fixture-bench",
                        "lane_id": "fixture-lane-b",
                        "manifest_slug": None,
                        "n_runs": 5,
                        "mean_score": 0.8,
                        "median_tok_per_s": 55.0,
                        "mean_ttft_ms": 700,
                        "human_pref_winrate": None,
                        "last_run_at": "2026-05-28T15:00:00Z",
                    },
                ],
            }
        )
    )
    return tmp_path


# ---------------------------------------------------------------------------
# Hermes config reader
# ---------------------------------------------------------------------------


def test_read_hermes_lane_with_missing_file(tmp_path: Path) -> None:
    missing = tmp_path / "config.yaml"
    assert _read_hermes_lane(hermes_path=missing) is None


def test_read_hermes_lane_with_live_shape(tmp_path: Path) -> None:
    cfg = tmp_path / "hermes-config.yaml"
    cfg.write_text(
        textwrap.dedent(
            """\
            model:
              default: Qwen3-30B-A3B-Q4_K_M
              provider: custom
              base_url: http://127.0.0.1:8080/v1
              context_length: 64000
              max_tokens: 8192
            """
        )
    )
    lane = _read_hermes_lane(hermes_path=cfg)
    assert lane is not None
    assert lane["id"] == "resident-brain"
    assert lane["model"] == "Qwen3-30B-A3B-Q4_K_M"
    assert lane["base_url"] == "http://127.0.0.1:8080/v1"
    assert lane["port"] == 8080
    # provider==custom + 127.0.0.1 → LlamaServerLane.
    assert lane["kind"] == "LlamaServerLane"
    assert lane["context_length"] == 64000
    assert lane["max_tokens"] == 8192
    assert lane["config_path"] == str(cfg)


def test_read_hermes_lane_with_nim_shape(tmp_path: Path) -> None:
    cfg = tmp_path / "hermes-nim.yaml"
    cfg.write_text(
        textwrap.dedent(
            """\
            model:
              default: nemotron-9b-v2
              provider: nim
              base_url: http://127.0.0.1:8000/v1
            """
        )
    )
    lane = _read_hermes_lane(hermes_path=cfg)
    assert lane is not None
    # 127.0.0.1 wins over the provider hint (it's our local NIM container).
    assert lane["kind"] == "LlamaServerLane"
    # Either way the port + base_url surface for the chip.
    assert lane["port"] == 8000


def test_read_hermes_lane_empty_model_block(tmp_path: Path) -> None:
    cfg = tmp_path / "hermes-empty.yaml"
    cfg.write_text("model: {}\nproviders: {}\n")
    assert _read_hermes_lane(hermes_path=cfg) is None


# ---------------------------------------------------------------------------
# TelemetryHub — subscriber bookkeeping
# ---------------------------------------------------------------------------


def test_telemetry_hub_starts_and_stops_with_subscribers() -> None:
    """First subscribe starts the underlying Telemetry; last unsubscribe
    stops it. The spec §4.6 zero-emit-when-idle commitment depends on this."""
    hub = TelemetryHub(interval=2.0)  # slow tick — we just check the counter
    assert hub.subscriber_count == 0
    assert not hub.is_running

    loop = asyncio.new_event_loop()
    try:
        q1, unsub1 = hub.subscribe(loop)
        assert hub.subscriber_count == 1
        assert hub.is_running

        q2, unsub2 = hub.subscribe(loop)
        assert hub.subscriber_count == 2
        assert hub.is_running  # still up

        unsub1()
        assert hub.subscriber_count == 1
        assert hub.is_running  # second subscriber keeps it up

        unsub2()
        assert hub.subscriber_count == 0
        # The pump thread joins on stop; give it a beat.
        time.sleep(0.05)
        assert not hub.is_running

        # Idempotent.
        unsub2()
        assert hub.subscriber_count == 0
        assert not hub.is_running
    finally:
        loop.close()


def test_telemetry_hub_unsubscribe_is_idempotent() -> None:
    hub = TelemetryHub(interval=2.0)
    loop = asyncio.new_event_loop()
    try:
        _q, unsub = hub.subscribe(loop)
        assert hub.is_running
        unsub()
        unsub()  # no-op the second time
        assert hub.subscriber_count == 0
        assert not hub.is_running
    finally:
        loop.close()


def test_telemetry_hub_report_inflight_threads_through_payload() -> None:
    hub = TelemetryHub(interval=2.0)
    hub.report_inflight(
        inflight=True, tok_per_s=83.5, ttft_ms=462.0, lane_id="llama-qwen3-30b"
    )
    payload = hub._build_payload()  # noqa: SLF001
    assert payload["inflight"] is True
    assert payload["tok_per_s"] == 83.5
    assert payload["ttft_ms"] == 462.0
    assert payload["lane_id"] == "llama-qwen3-30b"

    # The idle/disconnect guard flips inflight off but omits the speeds — they
    # must stay *sticky* so the rail keeps showing the last generation's tok/s
    # + TTFT (dimmed) instead of blanking the instant a stream ends.
    hub.report_inflight(inflight=False, lane_id=None)
    payload = hub._build_payload()  # noqa: SLF001
    assert payload["inflight"] is False
    assert payload["tok_per_s"] == 83.5
    assert payload["ttft_ms"] == 462.0
    assert payload["lane_id"] is None

    # A new stream start explicitly clears the speeds (passing None) so the
    # prefill window shows a clean dash, not the prior run's rate as if live.
    hub.report_inflight(inflight=True, tok_per_s=None, ttft_ms=None, lane_id="lane-b")
    payload = hub._build_payload()  # noqa: SLF001
    assert payload["tok_per_s"] is None
    assert payload["ttft_ms"] is None
    assert payload["lane_id"] == "lane-b"


# ---------------------------------------------------------------------------
# create_app — endpoints
# ---------------------------------------------------------------------------


def test_create_app_healthz_reports_surface_version(repo_root: Path) -> None:
    app = create_app(repo_root=repo_root, telemetry_interval=2.0)
    with TestClient(app) as client:
        r = client.get("/healthz")
        assert r.status_code == 200
        body = r.json()
        assert body["ok"] is True
        assert body["arena_surface_version"] == ARENA_SURFACE_VERSION
        assert body["telemetry_running"] is False
        assert body["subscribers"] == 0


def test_create_app_leaderboard_reads_mirror_json(repo_root: Path) -> None:
    app = create_app(repo_root=repo_root, telemetry_interval=2.0)
    with TestClient(app) as client:
        r = client.get("/api/leaderboard?limit=5")
        assert r.status_code == 200
        body = r.json()
        assert body["found"] is True
        assert len(body["rows"]) == 2
        assert body["rows"][0]["lane_id"] == "fixture-lane-a"
        assert body["rows"][0]["median_tok_per_s"] == 83.5
        # source path is relative to the repo root.
        assert body["source"].endswith("arena-mirror/leaderboard.json")


def test_create_app_leaderboard_limit_truncates(repo_root: Path) -> None:
    app = create_app(repo_root=repo_root, telemetry_interval=2.0)
    with TestClient(app) as client:
        r = client.get("/api/leaderboard?limit=1")
        assert r.status_code == 200
        assert len(r.json()["rows"]) == 1


def test_create_app_leaderboard_missing_mirror_yields_empty(
    tmp_path: Path,
) -> None:
    # Empty repo with no mirror file — should not 500, just return empty.
    app = create_app(repo_root=tmp_path, telemetry_interval=2.0)
    with TestClient(app) as client:
        r = client.get("/api/leaderboard?limit=5")
        assert r.status_code == 200
        body = r.json()
        assert body["found"] is False
        assert body["rows"] == []


def test_create_app_lanes_with_no_hermes_config(
    repo_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Steer the hermes-config reader at a non-existent path so tests don't
    # depend on the developer's local Spark state.
    monkeypatch.setattr(
        "fieldkit.arena.server._read_hermes_lane",
        lambda hermes_path=None: None,
    )
    app = create_app(
        repo_root=repo_root,
        db=str(repo_root / "no-such.db"),
        telemetry_interval=2.0,
    )
    with TestClient(app) as client:
        r = client.get("/api/lanes")
        assert r.status_code == 200
        body = r.json()
        assert body["resident"] is None
        assert body["roster"] == []


def test_create_app_lanes_surfaces_resident_when_present(
    repo_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "fieldkit.arena.server._read_hermes_lane",
        lambda hermes_path=None: {
            "id": "resident-brain",
            "kind": "LlamaServerLane",
            "model": "Qwen3-30B-A3B-Q4_K_M",
            "base_url": "http://127.0.0.1:8080/v1",
            "port": 8080,
            "provider": "custom",
            "context_length": 64000,
            "max_tokens": 8192,
            "config_path": "/tmp/hermes.yaml",
            "config_mtime": 1.0,
        },
    )
    app = create_app(
        repo_root=repo_root,
        db=str(repo_root / "no-such.db"),
        telemetry_interval=2.0,
    )
    with TestClient(app) as client:
        r = client.get("/api/lanes")
        body = r.json()
        assert body["resident"]["model"] == "Qwen3-30B-A3B-Q4_K_M"
        assert body["resident"]["port"] == 8080


# ---------------------------------------------------------------------------
# SSE endpoint — exercised via httpx stream against a live uvicorn loop.
# ---------------------------------------------------------------------------


class _FakeRequest:
    """Minimal stand-in for ``starlette.Request.is_disconnected()``.

    The generator polls it on each loop iteration. Tests flip
    ``_disconnected`` to terminate the stream and exercise the
    ``finally`` cleanup branch.
    """

    def __init__(self) -> None:
        self._disconnected = False

    async def is_disconnected(self) -> bool:
        return self._disconnected

    def disconnect(self) -> None:
        self._disconnected = True


def test_telemetry_event_stream_emits_hello_payload() -> None:
    """Direct unit test of the generator: subscribes on entry, yields the
    "hello" payload immediately, then waits on the queue. We disconnect
    after the first event so the generator's ``finally`` unsubscribes.

    Bypassing the HTTP layer keeps the test deterministic across the
    sse-starlette / httpx-ASGITransport / TestClient triad — the wire
    behaviour is covered by the live curl + Playwright smoke at M3
    side-by-side review time.
    """
    from fieldkit.arena.server import telemetry_event_stream

    hub = TelemetryHub(interval=0.1)
    request = _FakeRequest()

    async def _drive() -> dict[str, object]:
        gen = telemetry_event_stream(hub, request)
        event = await gen.__anext__()
        # Tell the generator to terminate on its next loop iteration,
        # then drive one more step so the `finally` runs.
        request.disconnect()
        try:
            await gen.__anext__()
        except StopAsyncIteration:
            pass
        await gen.aclose()
        return event

    event = asyncio.run(_drive())
    assert event["event"] == "telemetry"
    payload = json.loads(event["data"])
    # Required keys on every M3 tick (values may be None on a host without
    # nvidia-smi or /proc/meminfo, e.g. a CI runner).
    for key in (
        "ts",
        "gpu_util",
        "gpu_temp_c",
        "unified_used_gb",
        "unified_total_gb",
        "inflight",
        "tok_per_s",
        "ttft_ms",
        "lane_id",
    ):
        assert key in payload, f"missing key: {key}"

    # Cleanup: the generator's `finally` should have torn down the hub.
    for _ in range(80):
        if hub.subscriber_count == 0 and not hub.is_running:
            break
        time.sleep(0.05)
    assert hub.subscriber_count == 0
    assert not hub.is_running


def test_telemetry_event_stream_unsubscribes_on_disconnect() -> None:
    """Spec §4.6 zero-idle commitment — disconnect must stop the sampler."""
    from fieldkit.arena.server import telemetry_event_stream

    hub = TelemetryHub(interval=0.1)
    request = _FakeRequest()

    async def _drive() -> None:
        gen = telemetry_event_stream(hub, request)
        await gen.__anext__()  # hello payload
        assert hub.subscriber_count == 1
        assert hub.is_running
        request.disconnect()
        # Drain until StopAsyncIteration — the next yield path checks
        # is_disconnected before pulling from the queue.
        try:
            for _ in range(8):
                await gen.__anext__()
        except StopAsyncIteration:
            pass
        await gen.aclose()

    asyncio.run(_drive())
    for _ in range(80):
        if hub.subscriber_count == 0 and not hub.is_running:
            break
        time.sleep(0.05)
    assert hub.subscriber_count == 0
    assert not hub.is_running


def test_telemetry_event_stream_route_is_registered(repo_root: Path) -> None:
    """The HTTP surface stays minimal: a route at the spec'd path that
    returns an EventSourceResponse. The wire-level behaviour is exercised
    via the live curl smoke at M3 review time; here we just gate that
    the route exists and is shaped right."""
    app = create_app(repo_root=repo_root, telemetry_interval=2.0)
    paths = {r.path for r in app.routes if hasattr(r, "path")}
    assert "/api/telemetry/stream" in paths
    assert "/api/lanes" in paths
    assert "/api/leaderboard" in paths
    assert "/healthz" in paths


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------


def test_default_arena_port_locked_at_7866() -> None:
    """Spec §3.4 — DEFAULT_ARENA_PORT is operator-visible and must stay 7866."""
    assert DEFAULT_ARENA_PORT == 7866


# ---------------------------------------------------------------------------
# M4 — chat SSE proxy
# ---------------------------------------------------------------------------


class _StubChatClient:
    """Stub of `fieldkit.notebook.OpenAICompatClient` for the chat-stream
    unit tests. Yields a canned `<think>…</think>answer` shape so the
    `split_think` / channel-classification path exercises end-to-end.
    Captures the `messages` it was called with so the test can assert
    the prompt threading.
    """

    def __init__(self, chunks: list[str]) -> None:
        self._chunks = list(chunks)
        self.calls: list[list[dict[str, str]]] = []

    def chat_stream(self, messages, **_kwargs):
        self.calls.append(list(messages))
        for piece in self._chunks:
            yield piece


_CANNED_CHAT_CHUNKS = [
    "<think>",
    "Routing to the answer.",
    "</think>",
    "Hello, ",
    "world.",
]


def test_chat_event_stream_emits_start_token_done(
    repo_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Drive `chat_event_stream` directly: it should emit `start` first,
    then one `token` event per chunk (with `channel` set per the
    `<think>` boundary), then `done` with a `session_id` + `turn_id`."""
    from types import SimpleNamespace

    from fieldkit.arena.server import chat_event_stream

    stub = _StubChatClient(_CANNED_CHAT_CHUNKS)
    monkeypatch.setattr(
        "fieldkit.arena.server._chat_client_factory",
        lambda resident: stub,
    )

    hub = TelemetryHub(interval=0.1)
    request = _FakeRequest()
    body = SimpleNamespace(
        prompt="ping",
        session_id=None,
        rubric_id=None,
        max_tokens=128,
        temperature=0.0,
    )
    resident = {
        "id": "test-lane",
        "model": "qwen-fixture",
        "base_url": "http://127.0.0.1:8080/v1",
    }
    db_path = str(repo_root / "arena.db")

    async def _drive():
        events: list[dict[str, str]] = []
        gen = chat_event_stream(
            hub=hub,
            request=request,
            body=body,
            resident=resident,
            db_path=db_path,
        )
        async for ev in gen:
            events.append(ev)
            if ev["event"] == "done":
                break
        await gen.aclose()
        return events

    events = asyncio.run(_drive())
    kinds = [ev["event"] for ev in events]
    assert kinds[0] == "start"
    assert kinds[-1] == "done"
    # Every middle event is a token (or heartbeat); we expect at least
    # one of each channel — reasoning ("Routing…") + content ("Hello…").
    token_events = [ev for ev in events if ev["event"] == "token"]
    channels = {json.loads(ev["data"])["channel"] for ev in token_events}
    assert "reasoning" in channels
    assert "content" in channels

    start_payload = json.loads(events[0]["data"])
    assert start_payload["lane_id"] == "test-lane"
    assert start_payload["model"] == "qwen-fixture"
    assert start_payload["session_id"].startswith("cs-")

    done_payload = json.loads(events[-1]["data"])
    assert done_payload["session_id"] == start_payload["session_id"]
    assert done_payload["turn_id"] > 0
    assert done_payload["finish_reason"] == "stop"
    # Stub used a single round; the messages passed to chat_stream were a
    # single-user-turn shape (the M4 surface doesn't carry history yet —
    # M5 wires that).
    assert len(stub.calls) == 1
    assert stub.calls[0] == [{"role": "user", "content": "ping"}]


def test_chat_event_stream_persists_user_and_assistant_turns(
    repo_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Each chat turn lands as two `chat_turns` rows: user + assistant.
    Re-running the generator under the same session_id appends + bumps
    ord monotonically."""
    from types import SimpleNamespace

    from fieldkit.arena.server import chat_event_stream
    from fieldkit.arena.store import ArenaStore

    stub = _StubChatClient(_CANNED_CHAT_CHUNKS)
    monkeypatch.setattr(
        "fieldkit.arena.server._chat_client_factory",
        lambda resident: stub,
    )

    hub = TelemetryHub(interval=0.1)
    db_path = str(repo_root / "arena.db")
    resident = {
        "id": "test-lane",
        "model": "qwen-fixture",
        "base_url": "http://127.0.0.1:8080/v1",
    }

    async def _drive(session_id):
        request = _FakeRequest()
        body = SimpleNamespace(
            prompt="ping",
            session_id=session_id,
            rubric_id=None,
            max_tokens=128,
            temperature=0.0,
        )
        events: list[dict[str, str]] = []
        gen = chat_event_stream(
            hub=hub,
            request=request,
            body=body,
            resident=resident,
            db_path=db_path,
        )
        async for ev in gen:
            events.append(ev)
            if ev["event"] == "done":
                break
        await gen.aclose()
        return events

    events1 = asyncio.run(_drive(None))
    sid = json.loads(events1[0]["data"])["session_id"]
    # Second turn under the same session.
    events2 = asyncio.run(_drive(sid))
    sid2 = json.loads(events2[0]["data"])["session_id"]
    assert sid2 == sid

    with ArenaStore(repo_root / "arena.db") as store:
        rows = store.chat_turns(sid)
        # 2 turns × (user + assistant) = 4 rows; ord = 0,1,2,3.
        assert [r["ord"] for r in rows] == [0, 1, 2, 3]
        roles = [r["role"] for r in rows]
        assert roles == ["user", "assistant", "user", "assistant"]
        # Assistant rows carry the split reasoning + content.
        asst = [r for r in rows if r["role"] == "assistant"]
        for a in asst:
            assert "Hello," in a["content"]
            assert a["reasoning"] and "Routing" in a["reasoning"]
            assert a["finish_reason"] == "stop"


def test_chat_event_stream_pings_report_inflight(
    repo_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The M4 telemetry round-trip: `report_inflight(inflight=True, lane_id=…)`
    fires at stream start, and `inflight=False` fires on done. Idle ticks
    after the stream should therefore read inflight=False."""
    from types import SimpleNamespace

    from fieldkit.arena.server import chat_event_stream

    stub = _StubChatClient(_CANNED_CHAT_CHUNKS)
    monkeypatch.setattr(
        "fieldkit.arena.server._chat_client_factory",
        lambda resident: stub,
    )

    hub = TelemetryHub(interval=0.1)
    request = _FakeRequest()
    body = SimpleNamespace(
        prompt="ping",
        session_id=None,
        rubric_id=None,
        max_tokens=128,
        temperature=0.0,
    )
    resident = {
        "id": "test-lane",
        "model": "qwen-fixture",
        "base_url": "http://127.0.0.1:8080/v1",
    }
    db_path = str(repo_root / "arena.db")

    seen: list[dict[str, object]] = []
    real_report = hub.report_inflight

    def _spy(**kwargs):
        seen.append(dict(kwargs))
        return real_report(**kwargs)

    monkeypatch.setattr(hub, "report_inflight", _spy)

    async def _drive():
        gen = chat_event_stream(
            hub=hub,
            request=request,
            body=body,
            resident=resident,
            db_path=db_path,
        )
        async for ev in gen:
            if ev["event"] == "done":
                break
        await gen.aclose()

    asyncio.run(_drive())
    # First call: inflight=True with the resident lane id.
    assert seen[0]["inflight"] is True
    assert seen[0]["lane_id"] == "test-lane"
    # Final call: inflight=False (lane_id cleared in the finally guard).
    assert seen[-1]["inflight"] is False
    assert seen[-1]["lane_id"] is None


def test_chat_stream_route_is_registered_with_pydantic_body(
    repo_root: Path,
) -> None:
    """Route surface gate: POST /api/chat/stream is mounted; the empty body
    case returns 422 from the Pydantic validator (proves the request model
    is wired)."""
    app = create_app(
        repo_root=repo_root,
        db=str(repo_root / "arena.db"),
        telemetry_interval=2.0,
    )
    routes = {
        (r.path, tuple(sorted(r.methods))) for r in app.routes if hasattr(r, "methods")
    }
    assert ("/api/chat/stream", ("POST",)) in routes
    with TestClient(app) as client:
        r = client.post("/api/chat/stream", json={})
        # Empty body — Pydantic rejects with 422 (prompt missing).
        assert r.status_code == 422


def test_chat_stream_returns_503_when_no_resident_lane(
    repo_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """If `~/.hermes/config.yaml` is unreadable / empty, the chat endpoint
    surfaces an explicit 503 rather than crashing on a missing base_url."""
    monkeypatch.setattr(
        "fieldkit.arena.server._read_hermes_lane",
        lambda hermes_path=None: None,
    )
    app = create_app(
        repo_root=repo_root,
        db=str(repo_root / "arena.db"),
        telemetry_interval=2.0,
    )
    with TestClient(app) as client:
        r = client.post(
            "/api/chat/stream", json={"prompt": "ping"}
        )
        assert r.status_code == 503
        assert "resident brain" in r.json()["detail"].lower()


# ---------------------------------------------------------------------------
# M5 — rubric registry + compare SSE + prefs
# ---------------------------------------------------------------------------


def test_default_rubric_registry_has_three_entries() -> None:
    from fieldkit.arena.rubrics import DEFAULT_RUBRIC_REGISTRY

    assert set(DEFAULT_RUBRIC_REGISTRY.keys()) == {
        "generic-correctness",
        "patent_claim_validity",
        "mcq_letter",
    }
    # Each spec carries an executable Rubric.
    for spec in DEFAULT_RUBRIC_REGISTRY.values():
        assert len(spec.rubric.checks) >= 1


def test_default_rubric_for_prompt_picks_patent_when_claim_word_present() -> None:
    from fieldkit.arena.rubrics import default_rubric_for_prompt

    assert (
        default_rubric_for_prompt("Is claim 1 anticipated by prior art under §102?")
        == "patent_claim_validity"
    )
    # MCQ — answer letter (A) on Q5
    assert (
        default_rubric_for_prompt("Which of (a), (b), (c), (d) is the floor?")
        == "mcq_letter"
    )
    # Free-form falls through to the floor
    assert default_rubric_for_prompt("Write a haiku about Spark.") == (
        "generic-correctness"
    )


def test_api_rubrics_returns_default_registry(repo_root: Path) -> None:
    app = create_app(
        repo_root=repo_root,
        db=str(repo_root / "arena.db"),
        telemetry_interval=2.0,
    )
    with TestClient(app) as client:
        r = client.get("/api/rubrics")
        assert r.status_code == 200
        data = r.json()
        ids = [row["id"] for row in data["rubrics"]]
        assert ids[0] == "generic-correctness"
        assert "patent_claim_validity" in ids
        assert "mcq_letter" in ids
        # Each entry surfaces the check kinds.
        kinds = {row["id"]: [c["kind"] for c in row["checks"]] for row in data["rubrics"]}
        assert kinds["patent_claim_validity"] == ["substring"]


class _StubBlankAClient:
    """Stub for lane A — yields a fixture <think>… chain plus an answer
    that does NOT match the patent rubric (so the rubric score is 0)."""

    def chat_stream(self, messages, **_kwargs):
        for piece in [
            "<think>",
            "Routing for A.",
            "</think>",
            "Hello from lane A.",
        ]:
            yield piece


class _StubPatentBClient:
    """Stub for lane B — answer contains 'obviousness' (matches the
    patent_claim_validity substring rubric)."""

    def __init__(self) -> None:
        self.api_key = "fake-key-so-no-stub"

    def chat_stream(self, messages, **_kwargs):
        for piece in [
            "Under §103, obviousness is the controlling standard. ",
            "The claim is invalid.",
        ]:
            yield piece


def test_compare_event_stream_emits_full_sse_sequence(
    repo_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The compare generator emits exactly the spec §4.3 SSE event
    sequence: ``start_a → token_a* → done_a → start_b → token_b* →
    done_b → score`` with the score event carrying the per-check
    ``ok`` + ``why`` strings for both sides."""
    from types import SimpleNamespace

    from fieldkit.arena.server import compare_event_stream

    monkeypatch.setattr(
        "fieldkit.arena.server._chat_client_factory",
        lambda resident: _StubBlankAClient(),
    )
    stub_b = _StubPatentBClient()
    monkeypatch.setattr(
        "fieldkit.arena.server._compare_b_factory",
        lambda: (stub_b, None),
    )
    # Make sure the "no-key" fallback doesn't fire.
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-fake")

    hub = TelemetryHub(interval=0.1)
    request = _FakeRequest()
    body = SimpleNamespace(
        prompt="Is the claim anticipated under §102?",
        lane_b="openrouter",
        rubric_id="patent_claim_validity",
        max_tokens=128,
        temperature=0.0,
    )
    resident = {
        "id": "resident-brain",
        "model": "qwen-fixture",
        "base_url": "http://127.0.0.1:8080/v1",
    }
    db_path = str(repo_root / "arena.db")

    async def _drive():
        events: list[dict[str, str]] = []
        gen = compare_event_stream(
            hub=hub,
            request=request,
            body=body,
            resident=resident,
            db_path=db_path,
        )
        async for ev in gen:
            events.append(ev)
            if ev["event"] == "score":
                break
        await gen.aclose()
        return events

    events = asyncio.run(_drive())
    kinds = [ev["event"] for ev in events]
    # Floor ordering: start_a comes before done_a, done_a before start_b,
    # start_b before done_b, done_b before score.
    assert kinds[0] == "start_a"
    assert "done_a" in kinds
    assert kinds.index("done_a") < kinds.index("start_b")
    assert "done_b" in kinds
    assert kinds.index("done_b") < kinds.index("score")
    assert kinds[-1] == "score"

    # Token events carry the channel.
    token_a = [ev for ev in events if ev["event"] == "token_a"]
    channels_a = {json.loads(ev["data"])["channel"] for ev in token_a}
    assert "reasoning" in channels_a
    assert "content" in channels_a

    # Score payload: A fails patent rubric (no anchor term), B passes.
    score = json.loads(events[-1]["data"])
    assert score["rubric_id"] == "patent_claim_validity"
    assert score["a"]["total"] == 0.0  # "Hello from lane A." — no §103 / obviousness
    assert score["b"]["total"] == 1.0  # carries 'obviousness'
    assert score["deltas"]["score"] == -1.0  # B beats A on the rubric
    # Per-check why strings are visible.
    assert all("why" in c for c in score["a"]["checks"])
    assert all("why" in c for c in score["b"]["checks"])


def test_compare_event_stream_persists_rows_and_no_pref_mutation(
    repo_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Drive one compare end-to-end + verify the on-disk artifacts:
    one ``compare_runs`` row, two ``compare_responses``, two
    ``rubric_scores``. Then insert a human pref and assert the
    rubric_scores totals do NOT move — spec §4.3 separate-signal
    contract."""
    from types import SimpleNamespace

    from fieldkit.arena.schemas import HumanPrefRecord
    from fieldkit.arena.server import compare_event_stream
    from fieldkit.arena.store import ArenaStore

    monkeypatch.setattr(
        "fieldkit.arena.server._chat_client_factory",
        lambda resident: _StubBlankAClient(),
    )
    monkeypatch.setattr(
        "fieldkit.arena.server._compare_b_factory",
        lambda: (_StubPatentBClient(), None),
    )
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-fake")

    hub = TelemetryHub(interval=0.1)
    db_path = str(repo_root / "arena.db")
    resident = {
        "id": "resident-brain",
        "model": "qwen-fixture",
        "base_url": "http://127.0.0.1:8080/v1",
    }

    async def _drive():
        body = SimpleNamespace(
            prompt="Is the claim anticipated under §102?",
            lane_b="openrouter",
            rubric_id="patent_claim_validity",
            max_tokens=128,
            temperature=0.0,
        )
        events: list[dict[str, str]] = []
        gen = compare_event_stream(
            hub=hub,
            request=_FakeRequest(),
            body=body,
            resident=resident,
            db_path=db_path,
        )
        async for ev in gen:
            events.append(ev)
            if ev["event"] == "score":
                break
        await gen.aclose()
        return events

    events = asyncio.run(_drive())
    run_id = json.loads(events[0]["data"])["run_id"]

    with ArenaStore(repo_root / "arena.db") as store:
        head = store.compare_run(run_id)
        assert head is not None
        assert head["rubric_id"] == "patent_claim_validity"
        sides = store.compare_responses(run_id)
        assert [r["side"] for r in sides] == ["A", "B"]
        scores = store.rubric_scores_for_run(run_id)
        assert len(scores) == 2
        totals_before = {s["side"]: s["total"] for s in scores}
        assert totals_before["A"] == 0.0
        assert totals_before["B"] == 1.0

        # Operator thumbs B — spec §4.3 separate-signal: rubric_scores.total stays put.
        store.append_human_pref(
            HumanPrefRecord(
                id="hp-test",
                compare_run_id=run_id,
                winner="B",
                created_at="2026-05-28T19:00:00Z",
                note="B clearer",
            )
        )
        scores_after = store.rubric_scores_for_run(run_id)
        totals_after = {s["side"]: s["total"] for s in scores_after}
        assert totals_after == totals_before


def test_compare_stub_no_key_path_emits_clean_termination(
    repo_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When the env var is missing AND the stub client carries no api_key,
    the B-lane falls through to a canned reply. The stream still terminates
    cleanly with a ``score`` event (A wins by default — the stub reply has
    no patent anchor)."""
    from types import SimpleNamespace

    from fieldkit.arena.server import compare_event_stream

    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)

    class _NoKeyB:
        api_key = None  # triggers the stub path

        def chat_stream(self, messages, **kwargs):  # pragma: no cover — never called
            raise AssertionError("stub no-key path should NOT call chat_stream")

    monkeypatch.setattr(
        "fieldkit.arena.server._chat_client_factory",
        lambda resident: _StubBlankAClient(),
    )
    monkeypatch.setattr(
        "fieldkit.arena.server._compare_b_factory",
        lambda: (_NoKeyB(), None),
    )

    hub = TelemetryHub(interval=0.1)
    body = SimpleNamespace(
        prompt="hello",
        lane_b="openrouter",
        rubric_id=None,
        max_tokens=128,
        temperature=0.0,
    )
    resident = {
        "id": "resident-brain",
        "model": "qwen-fixture",
        "base_url": "http://127.0.0.1:8080/v1",
    }

    async def _drive():
        events: list[dict[str, str]] = []
        gen = compare_event_stream(
            hub=hub,
            request=_FakeRequest(),
            body=body,
            resident=resident,
            db_path=str(repo_root / "arena.db"),
        )
        async for ev in gen:
            events.append(ev)
            if ev["event"] == "score":
                break
        await gen.aclose()
        return events

    events = asyncio.run(_drive())
    kinds = [ev["event"] for ev in events]
    assert kinds[-1] == "score"
    start_b = next(ev for ev in events if ev["event"] == "start_b")
    assert json.loads(start_b["data"]).get("no_key") is True


def test_compare_stream_two_local_lanes_runs_full_duel(
    repo_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """v0.2 any-vs-any — two local lanes are now allowed (no v0.2-only error).

    The only warm Spark lane is the resident, so a ``local:*`` B-side resolves
    to it: the duel streams both sides off the resident client and scores
    normally. (The pre-v0.2 ``two_local_lanes_v0_2_only`` guard is gone.)"""
    from types import SimpleNamespace

    from fieldkit.arena.server import compare_event_stream

    monkeypatch.setattr(
        "fieldkit.arena.server._chat_client_factory",
        lambda resident: _StubBlankAClient(),
    )

    hub = TelemetryHub(interval=0.1)
    # Both sides = the resident (the only warm local lane); a full duel runs.
    body = SimpleNamespace(
        prompt="hello",
        lane_a="local:resident",
        lane_b="local:resident",
        rubric_id=None,
        max_tokens=128,
        temperature=0.0,
    )
    resident = {
        "id": "resident-brain",
        "model": "qwen-fixture",
        "base_url": "http://127.0.0.1:8080/v1",
    }

    async def _drive():
        events: list[dict[str, str]] = []
        gen = compare_event_stream(
            hub=hub,
            request=_FakeRequest(),
            body=body,
            resident=resident,
            db_path=str(repo_root / "arena.db"),
        )
        async for ev in gen:
            events.append(ev)
        await gen.aclose()
        return events

    events = asyncio.run(_drive())
    kinds = [ev["event"] for ev in events]
    # No v0.2-only error, and a full A→B→score sequence ran.
    assert not any(ev["event"] == "error" for ev in events)
    assert "start_a" in kinds and "done_a" in kinds
    assert "start_b" in kinds and "done_b" in kinds
    assert kinds[-1] == "score"
    # Both local sides cost nothing.
    done_b = json.loads(next(ev for ev in events if ev["event"] == "done_b")["data"])
    assert done_b.get("cost_usd") == 0.0


def test_api_prefs_inserts_row_and_returns_count(
    repo_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """POST /api/prefs writes one human_prefs row and returns the new
    pref id + the per-run pref count. 404 on unknown compare_run_id."""
    from types import SimpleNamespace

    from fieldkit.arena.server import compare_event_stream
    from fieldkit.arena.store import ArenaStore

    monkeypatch.setattr(
        "fieldkit.arena.server._chat_client_factory",
        lambda resident: _StubBlankAClient(),
    )
    monkeypatch.setattr(
        "fieldkit.arena.server._compare_b_factory",
        lambda: (_StubPatentBClient(), None),
    )
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-fake")

    # First, drive one compare so we have a real run_id.
    hub = TelemetryHub(interval=0.1)
    db_path = str(repo_root / "arena.db")

    async def _drive():
        body = SimpleNamespace(
            prompt="ping",
            lane_b="openrouter",
            rubric_id="generic-correctness",
            max_tokens=128,
            temperature=0.0,
        )
        gen = compare_event_stream(
            hub=hub,
            request=_FakeRequest(),
            body=body,
            resident={
                "id": "resident-brain",
                "model": "qwen-fixture",
                "base_url": "http://127.0.0.1:8080/v1",
            },
            db_path=db_path,
        )
        events = []
        async for ev in gen:
            events.append(ev)
            if ev["event"] == "score":
                break
        await gen.aclose()
        return events

    events = asyncio.run(_drive())
    run_id = json.loads(events[0]["data"])["run_id"]

    # Stub _read_hermes_lane so the app builds without needing live config.
    monkeypatch.setattr(
        "fieldkit.arena.server._read_hermes_lane",
        lambda hermes_path=None: {
            "id": "resident-brain",
            "model": "qwen-fixture",
            "base_url": "http://127.0.0.1:8080/v1",
        },
    )
    app = create_app(
        repo_root=repo_root,
        db=db_path,
        telemetry_interval=2.0,
    )
    with TestClient(app) as client:
        r = client.post(
            "/api/prefs",
            json={"compare_run_id": run_id, "winner": "B"},
        )
        assert r.status_code == 200
        payload = r.json()
        assert payload["ok"] is True
        assert payload["n_prefs"] == 1
        assert payload["pref_id"].startswith("hp-")

        # Second pref bumps the count.
        r2 = client.post(
            "/api/prefs",
            json={"compare_run_id": run_id, "winner": "tie", "note": "wash"},
        )
        assert r2.json()["n_prefs"] == 2

        # 404 on unknown.
        r3 = client.post(
            "/api/prefs",
            json={"compare_run_id": "cr-does-not-exist", "winner": "A"},
        )
        assert r3.status_code == 404

        # Pydantic gate: bad winner shape.
        r4 = client.post(
            "/api/prefs",
            json={"compare_run_id": run_id, "winner": "X"},
        )
        assert r4.status_code == 422

    # Persistence sanity: pref count on disk matches.
    with ArenaStore(repo_root / "arena.db") as store:
        prefs = store.human_prefs_for_run(run_id)
        assert len(prefs) == 2


def test_compare_stream_route_is_registered_with_pydantic_body(
    repo_root: Path,
) -> None:
    """Route surface gate — POST /api/compare/stream is mounted; empty
    body returns 422 (Pydantic prompt-missing)."""
    app = create_app(
        repo_root=repo_root,
        db=str(repo_root / "arena.db"),
        telemetry_interval=2.0,
    )
    routes = {
        (r.path, tuple(sorted(r.methods))) for r in app.routes if hasattr(r, "methods")
    }
    assert ("/api/compare/stream", ("POST",)) in routes
    assert ("/api/rubrics", ("GET",)) in routes
    assert ("/api/prefs", ("POST",)) in routes
    with TestClient(app) as client:
        r = client.post("/api/compare/stream", json={})
        assert r.status_code == 422


# ---------------------------------------------------------------------------
# Lab notes (v0.2; operator-private CRUD)
# ---------------------------------------------------------------------------


def test_api_lab_notes_crud_round_trip(repo_root: Path) -> None:
    """POST → GET → DELETE the operator-private Lab annotations. Notes are
    scoped per card and carry the freeform body on read (loopback-only;
    never mirrored — see test_mirror_does_not_leak)."""
    from fieldkit.arena.store import ArenaStore

    db_path = str(repo_root / "arena.db")
    app = create_app(repo_root=repo_root, db=db_path, telemetry_interval=2.0)
    with TestClient(app) as client:
        # Empty to start.
        assert client.get("/api/lab/notes").json()["notes"] == []

        # Pin two notes to one card + one to another.
        r = client.post(
            "/api/lab/notes",
            json={"card_id": "frontier", "body": "tighten the gold skyline", "lane": "now"},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["ok"] is True and body["n_notes"] == 1
        note_id = body["note_id"]

        client.post("/api/lab/notes", json={"card_id": "frontier", "body": "add hover labels"})
        client.post("/api/lab/notes", json={"card_id": "compare", "body": "two-local-lanes"})

        # Scoped read returns only this card's notes, newest first, with body.
        scoped = client.get("/api/lab/notes", params={"card_id": "frontier"}).json()["notes"]
        assert len(scoped) == 2
        assert scoped[0]["body"] == "add hover labels"
        assert all(n["card_id"] == "frontier" for n in scoped)

        # Unscoped read sees all three.
        assert len(client.get("/api/lab/notes").json()["notes"]) == 3

        # Delete one; 404 on a second delete of the same id.
        assert client.delete(f"/api/lab/notes/{note_id}").status_code == 200
        assert client.delete(f"/api/lab/notes/{note_id}").status_code == 404
        assert len(client.get("/api/lab/notes", params={"card_id": "frontier"}).json()["notes"]) == 1

        # Pydantic gate: empty body rejected.
        assert client.post("/api/lab/notes", json={"card_id": "x", "body": ""}).status_code == 422

    # Persistence sanity on disk.
    with ArenaStore(repo_root / "arena.db") as store:
        assert len(store.lab_notes()) == 2


def test_api_lab_notes_missing_db_returns_empty(tmp_path: Path) -> None:
    """GET on a cold DB returns an empty list, not a 500."""
    app = create_app(repo_root=tmp_path, db=str(tmp_path / "no-such.db"), telemetry_interval=2.0)
    with TestClient(app) as client:
        assert client.get("/api/lab/notes").json() == {"notes": []}


# ---------------------------------------------------------------------------
# v0.2 — OpenRouter curation + on-demand local lane resolution
# ---------------------------------------------------------------------------


def test_curate_openrouter_models_picks_newest_per_family() -> None:
    """Each family matcher keeps the single newest (by `created`) chat model;
    non-chat modalities are skipped."""
    from fieldkit.arena.server import _curate_openrouter_models

    catalog = [
        {"id": "openai/gpt-5.5", "name": "GPT-5.5", "created": 200},
        {"id": "openai/gpt-5.1", "name": "GPT-5.1", "created": 100},
        {"id": "openai/gpt-5-image", "name": "GPT-5 Image", "created": 999},
        {"id": "anthropic/claude-opus-4.8", "name": "Opus 4.8", "created": 300},
        {"id": "qwen/qwen3-8b", "name": "Qwen3 8B", "created": 50},
        {"id": "qwen/qwen3.6-max", "name": "Qwen3.6 Max", "created": 400},
        {"id": "mistralai/mistral-7b-instruct", "name": "Mistral 7B", "created": 10},
    ]
    out = _curate_openrouter_models(catalog)
    front_ids = {m["id"] for m in out["frontier"]}
    # Newest GPT (non-image) + the Opus; the image model is excluded.
    assert "openai/gpt-5.5" in front_ids
    assert "openai/gpt-5-image" not in front_ids
    assert "anthropic/claude-opus-4.8" in front_ids
    open_ids = {m["id"] for m in out["open"]}
    assert "qwen/qwen3.6-max" in open_ids  # newest Qwen3 wins
    assert "qwen/qwen3-8b" not in open_ids
    base_ids = {m["id"] for m in out["project_base"]}
    assert "qwen/qwen3-8b" in base_ids  # project-base family matches the 8B
    assert "mistralai/mistral-7b-instruct" in base_ids


def test_resolve_local_gguf_missing_returns_none(monkeypatch: pytest.MonkeyPatch) -> None:
    """A slug with no on-disk quants dir resolves to None (not a crash)."""
    from pathlib import Path as _P

    import fieldkit.arena.server as srv

    monkeypatch.setattr(srv, "_QUANTS_ROOT", _P("/nonexistent/quants/root"))
    assert srv._resolve_local_gguf("no-such-model-gguf", "Q4_K_M") is None


def test_resolve_local_gguf_prefix_match(tmp_path: Path) -> None:
    """Normalized dir-name prefix match + model-<variant>.gguf resolution."""
    import fieldkit.arena.server as srv

    d = tmp_path / "II-Medical-8B"
    d.mkdir()
    (d / "model-Q4_K_M.gguf").write_bytes(b"gguf")
    orig = srv._QUANTS_ROOT
    srv._QUANTS_ROOT = tmp_path
    try:
        hit = srv._resolve_local_gguf("ii-medical-8b-gguf", "Q4_K_M")
        assert hit is not None and hit.name == "model-Q4_K_M.gguf"
    finally:
        srv._QUANTS_ROOT = orig


def test_compare_options_endpoint_shape(
    repo_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """/api/compare/options returns local + curated openrouter groups + full list."""
    import fieldkit.arena.server as srv

    monkeypatch.setattr(srv, "_read_hermes_lane", lambda *a, **k: None)
    monkeypatch.setattr(
        srv,
        "_openrouter_catalog",
        lambda *a, **k: [
            {"id": "openai/gpt-5.5", "name": "GPT-5.5", "created": 200,
             "price_per_m_input_usd": 5.0, "price_per_m_output_usd": 25.0},
            {"id": "qwen/qwen3.6-max", "name": "Qwen3.6 Max", "created": 100,
             "price_per_m_input_usd": 1.0, "price_per_m_output_usd": 3.0},
        ],
    )
    app = create_app(repo_root=repo_root, telemetry_interval=2.0)
    with TestClient(app) as client:
        r = client.get("/api/compare/options")
        assert r.status_code == 200
        data = r.json()
        assert "local" in data
        assert set(data["openrouter_groups"]) == {"frontier", "open", "project_base"}
        assert data["catalog_size"] == 2
        assert any(o["id"] == "openrouter:openai/gpt-5.5" for o in data["openrouter"])


def test_telemetry_payload_carries_resident_lane() -> None:
    """Idle ticks surface the warm resident so the rail shows it (not 'no warm
    brain'). The hub reads it via the injected resident reader."""
    hub = TelemetryHub(interval=2.0)
    hub._resident_reader = lambda: {"model": "Qwen3-30B-A3B-Q4_K_M"}  # noqa: SLF001
    payload = hub._build_payload()  # noqa: SLF001
    assert payload["resident_lane"] == "Qwen3-30B-A3B-Q4_K_M"
    # No reader → None (e.g. tests that don't inject one).
    assert TelemetryHub(interval=2.0)._build_payload()["resident_lane"] is None  # noqa: SLF001


def test_local_load_stream_missing_gguf_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    """Loading an unknown on-demand lane yields a clean error event (no spawn)."""
    import fieldkit.arena.server as srv

    monkeypatch.setattr(srv, "_resolve_local_gguf", lambda *a, **k: None)

    async def _drive():
        evs = []
        async for ev in srv._local_load_stream("local:no-such-model::Q4_K_M"):
            evs.append(ev)
        return evs

    events = asyncio.run(_drive())
    assert any(e["event"] == "error" for e in events)
    assert not any(e["event"] == "done" for e in events)


def test_local_load_stream_resident_is_noop() -> None:
    """Loading the resident is a no-op done (it's always warm; no spawn)."""
    import fieldkit.arena.server as srv

    async def _drive():
        return [ev async for ev in srv._local_load_stream("local:resident")]

    events = asyncio.run(_drive())
    assert events and events[-1]["event"] == "done"
    assert json.loads(events[-1]["data"])["lane_id"] == "local:resident"


# ---------------------------------------------------------------------------
# v0.3 — eval-prompt benches, scoring, leaderboard
# ---------------------------------------------------------------------------


def _write_eval_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n")


@pytest.fixture
def eval_tree(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Minimal eval-benches tree wired into ``fieldkit.arena.benches``."""
    from fieldkit.arena import benches

    root = tmp_path / "eval-benches"
    _write_eval_jsonl(
        root / "medmcqa" / "medmcqa_merged.jsonl",
        [
            {"id": "mm-1", "text": "Q1?\nA) a\nB) b\nC) c\nD) d", "answer": "B", "task": "medmcqa"},
            {"id": "mm-2", "text": "Q2?\nA) a\nB) b\nC) c\nD) d", "answer": "C", "task": "medmcqa"},
        ],
    )
    _write_eval_jsonl(
        root / "patent-strategist" / "seed-A.jsonl",
        [{
            "qid": "ps-A-1", "question": "Draft a claim.", "family": "A",
            "use_case": "A1", "scoring_mode": "oracle", "gold_label": "A claim.",
            "options": [], "oracle_context": "ctx", "rubric": {"claim_type": "independent"},
        }],
    )
    monkeypatch.setattr(benches, "ARENA_EVAL_BENCHES_ROOT", root)
    benches._CACHE.clear()
    yield root
    benches._CACHE.clear()


def test_api_eval_benches_lists_and_reports_judge(
    repo_root: Path, eval_tree: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("fieldkit.arena.server._read_hermes_lane", lambda hermes_path=None: None)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    app = create_app(repo_root=repo_root, telemetry_interval=2.0)
    with TestClient(app) as client:
        r = client.get("/api/eval/benches")
        assert r.status_code == 200
        body = r.json()
        ids = {b["bench_id"]: b for b in body["benches"]}
        assert ids["medmcqa"]["available"] and ids["medmcqa"]["count"] == 2
        assert ids["patent-strategist"]["available"]
        # No resident + no key → both judge backends unavailable.
        assert body["judge"]["local_available"] is False
        assert body["judge"]["openrouter_available"] is False


def test_api_eval_prompts_pagination_and_404(repo_root: Path, eval_tree: Path) -> None:
    app = create_app(repo_root=repo_root, telemetry_interval=2.0)
    with TestClient(app) as client:
        r = client.get("/api/eval/benches/medmcqa/prompts", params={"limit": 1})
        body = r.json()
        assert body["total"] == 2 and len(body["prompts"]) == 1
        assert body["prompts"][0]["scorer_kind"] == "mcq_letter"
        assert body["prompts"][0]["reference"] in ("B", "C")
        # Unknown bench → 404 with a path hint.
        miss = client.get("/api/eval/benches/nope/prompts")
        assert miss.status_code == 404
        assert "ARENA_EVAL_BENCHES_ROOT" in miss.json()["detail"]


def test_api_chat_score_deterministic_persists_and_leaderboards(
    repo_root: Path, eval_tree: Path, tmp_path: Path
) -> None:
    """A persisted chat turn scored against an MCQ bench lands an eval_scores
    row and shows in the accuracy leaderboard."""
    from fieldkit.arena.schemas import ChatSessionRecord, ChatTurnRecord, LaneRecord
    from fieldkit.arena.store import ArenaStore

    db_path = str(tmp_path / "arena.db")
    store = ArenaStore(db_path)
    store.initialize()
    store.upsert_lane(
        LaneRecord(id="local:ii-medical-8b-gguf::Q8_0", kind="LlamaServerLane",
                   model="ii-medical-8b-gguf::Q8_0", port=8091, base_url="")
    )
    store.upsert_chat_session(
        ChatSessionRecord(id="cs-x", lane_id="local:ii-medical-8b-gguf::Q8_0",
                          created_at="2026-05-28T00:00:00Z", publishable=0)
    )
    turn_id = store.append_chat_turn(
        ChatTurnRecord(session_id="cs-x", ord=1, role="assistant",
                       content="The answer is B.", created_at="2026-05-28T00:00:01Z")
    )
    store.close()

    app = create_app(repo_root=repo_root, db=db_path, telemetry_interval=2.0)
    with TestClient(app) as client:
        r = client.post("/api/chat/score", json={
            "turn_id": turn_id, "bench_id": "medmcqa", "eval_qid": "mm-1",
            "lane_id": "local:ii-medical-8b-gguf::Q8_0",
        })
        body = r.json()
        assert body["scored"] is True and body["score"] == 1.0
        assert body["scorer_kind"] == "mcq_letter" and body["turn_id"] == turn_id
        # Leaderboard rollup picks it up (own-bench, not cross-vertical).
        lb = client.get("/api/eval/leaderboard").json()
        rows = {(r["bench_id"], r["lane_id"]): r for r in lb["rows"]}
        key = ("medmcqa", "local:ii-medical-8b-gguf::Q8_0")
        assert key in rows and rows[key]["mean_normalized"] == 1.0


def test_api_chat_score_missing_turn_404(repo_root: Path, eval_tree: Path, tmp_path: Path) -> None:
    db_path = str(tmp_path / "arena.db")
    ArenaStore_init(db_path)
    app = create_app(repo_root=repo_root, db=db_path, telemetry_interval=2.0)
    with TestClient(app) as client:
        r = client.post("/api/chat/score", json={"turn_id": 999, "bench_id": "medmcqa", "eval_qid": "mm-1"})
        assert r.status_code == 404


def ArenaStore_init(db_path: str) -> None:
    from fieldkit.arena.store import ArenaStore

    s = ArenaStore(db_path)
    s.initialize()
    s.close()


class _StubAnswerClient:
    """Compare-side stub that yields a fixed answer (no <think>)."""

    def __init__(self, answer: str) -> None:
        self._answer = answer

    def chat_stream(self, messages, **_kwargs):
        yield self._answer


def test_compare_eval_block_scores_both_sides(
    repo_root: Path, eval_tree: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A compare run with an eval prompt augments the score event with an
    ``eval`` block grading both sides against the bench gold."""
    from types import SimpleNamespace

    from fieldkit.arena.server import compare_event_stream

    monkeypatch.setattr(
        "fieldkit.arena.server._chat_client_factory",
        lambda resident: _StubAnswerClient("Answer: B"),  # correct vs gold "B"
    )
    monkeypatch.setattr(
        "fieldkit.arena.server._compare_b_factory",
        lambda: (_StubAnswerClient("Answer: D"), None),  # wrong
    )
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-fake")

    hub = TelemetryHub(interval=0.1)
    body = SimpleNamespace(
        prompt="Q1?", lane_a="local:resident", lane_b="openrouter",
        rubric_id=None, max_tokens=64, temperature=0.0,
        bench_id="medmcqa", eval_qid="mm-1", judge=None,
    )
    resident = {"id": "resident", "model": "qwen", "base_url": "http://127.0.0.1:8080/v1"}
    db_path = str(tmp_path / "arena.db")

    async def _drive():
        events = []
        gen = compare_event_stream(hub=hub, request=_FakeRequest(), body=body,
                                   resident=resident, db_path=db_path)
        async for ev in gen:
            events.append(ev)
            if ev["event"] == "score":
                break
        await gen.aclose()
        return events

    events = asyncio.run(_drive())
    # start events carry the eval_context transparency block.
    start_a = json.loads(next(e["data"] for e in events if e["event"] == "start_a"))
    assert start_a["eval_context"]["bench_id"] == "medmcqa"
    score = json.loads(events[-1]["data"])
    assert "eval" in score
    assert score["eval"]["scorer_kind"] == "mcq_letter"
    assert score["eval"]["reference"] == "B"
    assert score["eval"]["a"]["score"] == 1.0
    assert score["eval"]["b"]["score"] == 0.0
