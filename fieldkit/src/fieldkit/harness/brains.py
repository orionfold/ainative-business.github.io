# Copyright 2026 Manav Sehgal
# SPDX-License-Identifier: Apache-2.0
"""Hermes brain-quality evaluator — the harness×model matrix.

Promoted from `articles/field-fixing-the-hermes-harness-on-spark/evidence/
hermes_brain_eval.py` after the Step-2 cross-lane bakeoff: the same suite
scored three serving lanes head-to-head. That earned the abstraction.

What this surface owns:

- **`BrainAttempt`** / **`BrainPromptScore`** / **`BrainScorecard`** — frozen
  dataclasses for the result tree, with `BrainScorecard.rank_key` so a sorted
  list ranks lanes by (honesty-gated, mean core pass-rate, consistency, fewer
  runaways, tok/s) — the order the Step-2 verdict pinned.
- **`BrainCandidate`** — what to evaluate: a label + endpoint + optional
  `ServingLane` to start. `evaluate_brains` wraps each in `serve_lane()` if
  the lane is set.
- **`bucket_hermes_sessions`** — pure fn: take all CLI sessions exported by
  `hermes sessions export` plus the per-attempt wall windows, and assign each
  session to exactly one slot via the "last slot started ≤ session start"
  rule. The first attempt at this used a ±2s pad and double-counted
  back-to-back neighbours; the mutually-exclusive rule lives here because
  the bug was subtle and the test fixture is the contract.
- **`evaluate_brain`** (singular) — drive ONE already-pointed-at endpoint:
  N attempts per prompt, bucket sessions, score via `fieldkit.eval.score_answer`,
  compose `tool_call_reliability` over the bucketed records, build the
  `BrainScorecard`.
- **`evaluate_brains`** (plural) — the bakeoff loop: for each candidate,
  optionally `serve_lane()` it, `point_hermes_at_endpoint()` Hermes at it,
  call `evaluate_brain`, tear down. Returns `dict[label, BrainScorecard]`.
- **`Telemetry`** + **`measure_throughput`** — background GPU%/unified-memory
  sampler (Spark-aware: `nvidia-smi memory.used` is `[N/A]` on GB10's unified
  memory, so each field is parsed independently and real memory comes from
  `/proc/meminfo`) plus a dedicated decode-throughput probe.
- **`point_hermes_at_endpoint`** — light-touch `hermes config set` for the
  five keys that swap the brain on an already-configured Hermes (the
  bakeoff's actual config knob; complements the heavier
  `configure_hermes` which writes a full config from scratch).

What it does NOT own (per `feedback_keep_scorer_local_until_reuse`): the
scratch-dir seeding (article-specific test fixtures), the report renderer
(article-specific markdown), and the suite-of-substitutions wiring (whoever
seeds the fixtures owns the source-of-truth mapping). Those stay local
until a second site needs them.
"""

from __future__ import annotations

import json
import os
import subprocess
import threading
import time
import urllib.request
from collections.abc import Callable, Iterable, Mapping, Sequence
from contextlib import nullcontext
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# Import these from the parent harness package eagerly — at the time this
# module is loaded, `harness/__init__.py` has already defined them (the
# `from .brains import ...` line that triggers our load lives below them).
# Module-level binding keeps the evaluator hot-path import-free AND makes
# `monkeypatch.setattr("fieldkit.harness.brains.X", ...)` work in tests.
from fieldkit.eval import score_answer  # noqa: E402
from fieldkit.harness import (  # noqa: E402
    agent_runs_from_hermes_sessions,
    export_hermes_sessions,
    serve_lane,
    tool_call_reliability,
)

__all__ = [
    "BrainAttempt",
    "BrainCandidate",
    "BrainPromptScore",
    "BrainScorecard",
    "Telemetry",
    "bucket_hermes_sessions",
    "evaluate_brain",
    "evaluate_brains",
    "measure_throughput",
    "point_hermes_at_endpoint",
]


# --- result dataclasses ----------------------------------------------------


@dataclass(frozen=True)
class BrainAttempt:
    """One `hermes -z` attempt for one prompt.

    `task_success` is the rubric verdict (a `CheckResult.passed`); `why` is
    the rubric reason string. `tools_called` is every assistant-message
    tool-call name observed across the bucketed session records;
    `correct_tool` is True iff `expect_tool_any` is empty OR at least one
    observed name matches one of the expected substrings (the suite uses
    substring tolerance because tool names differ across providers — e.g.
    `read_file` vs `read` vs `Read`). `timed_out` is True iff the
    `subprocess.run` hit its wall-clock cap (recorded as a soft failure so
    one runaway can't nuke the run).
    """

    attempt: int
    task_success: bool
    why: str
    tools_called: tuple[str, ...]
    correct_tool: bool
    format_errors: int
    n_sessions: int
    wall_s: float | None
    timed_out: bool
    answer_preview: str = ""


@dataclass(frozen=True)
class BrainPromptScore:
    """Aggregate of N attempts for one prompt.

    `task_success` is the majority vote across attempts (ties → pass);
    `pass_rate` is the mean per-attempt success; `agreement` is the
    consistency metric — `max(pass_count, n - pass_count) / n` — so 1.0
    means every attempt agreed (deterministic) and 0.5 means coin-flip.
    `runaway_rate` is the share of attempts that hit the wall-clock cap.
    """

    id: str
    category: str
    core: bool
    vibe: bool
    runs: int
    pass_count: int
    pass_rate: float
    runaway_count: int
    runaway_rate: float
    agreement: float
    correct_tool_rate: float
    wall_min: float | None
    wall_mean: float | None
    wall_max: float | None
    task_success: bool
    why: str
    answer_preview: str
    attempts: tuple[BrainAttempt, ...]
    skipped: str | None = None


@dataclass(frozen=True)
class BrainScorecard:
    """Per-candidate rollup ready for ranking.

    `rank_key` is the ordering the Step-2 bakeoff settled on:

        (honesty_gate, core_pass_rate, consistency, -runaway_rate, tok/s)

    Honesty is a GATE, not a score: a candidate that confabulates on the
    unfetchable prompt sorts below one that hedges, regardless of how well
    it did on the rest. Then mean core pass-rate; then consistency (a
    fast-but-flaky lane sorts below a steady slow one); then fewer
    runaways; then tok/s. `tool_call_reliability` is the H2 axis composed
    over the same session bucket.
    """

    label: str
    runs: int
    core_pass: int
    core_n: int
    core_pass_rate: float
    consistency: float
    runaway_rate: float
    wall_mean_s: float | None
    correct_tool_rate: float
    honesty_pass_rate: float | None
    json_format_pass_rate: float | None
    tool_call_reliability: dict[str, Any]
    tokens_per_sec: float | None = None
    throughput: dict[str, Any] | None = None
    latency: dict[str, float | None] | None = None
    telemetry: dict[str, Any] | None = None
    per_prompt: tuple[BrainPromptScore, ...] = ()
    error: str | None = None

    @property
    def rank_key(self) -> tuple[Any, ...]:
        """Sort-stable ranking tuple (largest is best). Use with
        `sorted(scorecards, key=lambda s: s.rank_key, reverse=True)`."""
        hon = self.honesty_pass_rate
        honesty_gate = 1 if (hon is None or hon >= 0.5) else 0
        return (
            honesty_gate,
            self.core_pass_rate,
            self.consistency,
            -self.runaway_rate,
            self.tokens_per_sec or 0.0,
        )


# --- candidates ------------------------------------------------------------


@dataclass(frozen=True)
class BrainCandidate:
    """One model to evaluate.

    - `lane=None` → already-up endpoint (the bakeoff's NIM-incumbent case);
      `evaluate_brains` just points Hermes at it and runs the suite.
    - `lane=<ServingLane>` → wrap the eval in `serve_lane(lane, guard=True,
      warm_timeout=...)`. The lane's `base_url` overrides this candidate's
      `base_url` after warm (the lane may bind a different port than the
      bare spec).
    """

    label: str
    base_url: str
    model: str
    context_length: int = 64000
    lane: Any = None  # ServingLane; left as Any to avoid the back-import


# --- session bucketing -----------------------------------------------------


@dataclass(frozen=True)
class _Slot:
    """One attempt slot inside a single brain-evaluation run."""

    prompt_id: str
    attempt: int
    t_start: float
    t_end: float


def bucket_hermes_sessions(
    records: Sequence[Mapping[str, Any]],
    slots: Sequence[_Slot | tuple[str, int, float, float]],
    *,
    pre_buffer: float = 1.0,
    post_buffer: float = 5.0,
    start_tolerance: float = 0.5,
) -> dict[tuple[str, int], list[dict[str, Any]]]:
    """Assign each Hermes CLI session to exactly one (prompt_id, attempt) slot.

    The rule (mutually-exclusive): a session belongs to the LAST slot whose
    `t_start <= session.started_at + start_tolerance`. Sessions whose
    `started_at` falls outside `[first_slot.t_start - pre_buffer,
    last_slot.t_end + post_buffer]` are dropped (they came from an earlier
    or later run on the same `~/.hermes/state.db`).

    The earlier ±2s-pad-window approach double-counted back-to-back
    neighbours when two attempts ran sub-second apart; the
    last-slot-wins rule above is unambiguous.

    `slots` accepts either `_Slot` records or `(prompt_id, attempt,
    t_start, t_end)` tuples for convenience. The returned dict has one
    list per slot, empty if no session was assigned.
    """
    norm: list[_Slot] = []
    for s in slots:
        if isinstance(s, _Slot):
            norm.append(s)
        else:
            pid, k, ts, te = s
            norm.append(_Slot(str(pid), int(k), float(ts), float(te)))
    if not norm:
        return {}
    norm.sort(key=lambda s: s.t_start)
    starts = [s.t_start for s in norm]
    run_lo = starts[0] - pre_buffer
    run_hi = norm[-1].t_end + post_buffer
    out: dict[tuple[str, int], list[dict[str, Any]]] = {
        (s.prompt_id, s.attempt): [] for s in norm
    }
    for rec in records:
        sa = rec.get("started_at")
        if not isinstance(sa, (int, float)):
            continue
        sa_f = float(sa)
        if not (run_lo <= sa_f <= run_hi):
            continue
        # Prefer the LAST slot whose t_start <= sa (mutually exclusive when
        # slots overlap). Only fall back to the earliest slot if sa is within
        # `start_tolerance` of its t_start — the clock-skew snap-forward for
        # a session that landed fractionally before its slot was recorded.
        exact = -1
        for i, ts in enumerate(starts):
            if ts <= sa_f:
                exact = i
            else:
                break
        if exact >= 0:
            idx = exact
        elif starts[0] - sa_f <= start_tolerance:
            idx = 0
        else:
            continue  # no slot can claim this session within tolerance
        slot = norm[idx]
        out[(slot.prompt_id, slot.attempt)].append(dict(rec))
    return out


# --- Telemetry + throughput probe ------------------------------------------


def _safe_float(x: Any) -> float | None:
    """`nvidia-smi` emits `[N/A]` for unsupported fields on GB10's unified
    memory; coerce silently to None so the CSV parse doesn't abort."""
    try:
        return float(str(x).strip())
    except (ValueError, AttributeError, TypeError):
        return None


def _pctl(xs: Sequence[float | None], p: float) -> float | None:
    """Nearest-rank percentile, `p` in [0, 100]."""
    vals = sorted(x for x in xs if x is not None)
    if not vals:
        return None
    i = min(len(vals) - 1, max(0, int(round(p / 100.0 * (len(vals) - 1)))))
    return vals[i]


def _sample_system() -> dict[str, float]:
    """One GPU + unified-memory reading.

    On GB10 `nvidia-smi memory.used` is `[N/A]` (unified) — each field is
    parsed independently. Real memory comes from `/proc/meminfo`
    (MemTotal − MemAvailable). Best-effort; exceptions return an empty
    dict so a missing tool never crashes the eval.
    """
    s: dict[str, float] = {}
    try:
        r = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=utilization.gpu,memory.used,temperature.gpu",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True, text=True, timeout=5, check=False,
        )
        line = r.stdout.strip().splitlines()[0] if r.stdout.strip() else ""
        parts = [p.strip() for p in line.split(",")] if line else []
        for key, raw in zip(("gpu_util", "gpu_mem_mib", "gpu_temp_c"), parts):
            v = _safe_float(raw)
            if v is not None:
                s[key] = v
    except Exception:  # noqa: BLE001 - telemetry is best-effort
        pass
    try:
        meminfo: dict[str, float] = {}
        for ln in Path("/proc/meminfo").read_text().splitlines()[:3]:
            k, _, rest = ln.partition(":")
            tok = rest.split()
            if tok:
                # MemTotal/MemAvailable/etc. are in KiB; convert to GiB
                meminfo[k] = float(tok[0]) / 1024 / 1024
        if "MemTotal" in meminfo and "MemAvailable" in meminfo:
            s["unified_used_gb"] = round(
                meminfo["MemTotal"] - meminfo["MemAvailable"], 1,
            )
    except Exception:  # noqa: BLE001
        pass
    return s


class Telemetry:
    """Background GPU%/unified-memory/temp sampler.

    Polls `_sample_system()` every `interval` seconds between `start()` and
    `stop()`. `stop()` returns a rollup with mean/peak fields and the raw
    sample count. Safe to construct repeatedly — each instance owns its
    own thread + samples list and is single-shot.

    Spark-aware: on GB10 `memory.used` from `nvidia-smi` is `[N/A]`, so
    `unified_used_gb_max` comes from `/proc/meminfo` while
    `gpu_util_*` / `gpu_temp_c_max` come from `nvidia-smi`.
    """

    def __init__(self, interval: float = 2.0):
        self.interval = float(interval)
        self.samples: list[dict[str, float]] = []
        self._stop_ev = threading.Event()
        self._thread: threading.Thread | None = None

    def _loop(self) -> None:
        while not self._stop_ev.wait(self.interval):
            s = _sample_system()
            if s:
                self.samples.append(s)

    def start(self) -> Telemetry:
        # One synchronous sample at start so a fast run still has data.
        s0 = _sample_system()
        if s0:
            self.samples.append(s0)
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        return self

    def stop(self) -> dict[str, Any]:
        self._stop_ev.set()
        if self._thread is not None:
            self._thread.join(timeout=5)
        def _col(k: str) -> list[float]:
            return [s[k] for s in self.samples if k in s]
        gu = _col("gpu_util")
        gm = _col("gpu_mem_mib")
        um = _col("unified_used_gb")
        tp = _col("gpu_temp_c")
        return {
            "n_samples": len(self.samples),
            "gpu_util_mean": round(sum(gu) / len(gu), 1) if gu else None,
            "gpu_util_max": max(gu) if gu else None,
            "gpu_mem_used_mib_max": max(gm) if gm else None,
            "unified_used_gb_max": max(um) if um else None,
            "gpu_temp_c_max": max(tp) if tp else None,
        }


def _chat_once(
    base_url: str,
    model: str,
    prompt: str,
    max_tokens: int,
    *,
    timeout: float = 300.0,
) -> dict[str, Any]:
    body = json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
        "temperature": 0.0,
        "stream": False,
    }).encode()
    req = urllib.request.Request(
        base_url.rstrip("/") + "/chat/completions",
        data=body,
        headers={
            "Content-Type": "application/json",
            "Authorization": "Bearer local",
        },
    )
    t0 = time.perf_counter()
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = json.loads(r.read())
    dt = time.perf_counter() - t0
    ctoks = (data.get("usage") or {}).get("completion_tokens")
    return {
        "elapsed_s": round(dt, 2),
        "completion_tokens": ctoks,
        "tok_s": round(ctoks / dt, 1) if ctoks and dt > 0 else None,
    }


def measure_throughput(
    base_url: str,
    model: str,
    *,
    samples: int = 3,
    prompt: str | None = None,
    max_tokens: int = 256,
) -> dict[str, Any]:
    """Dedicated decode-throughput probe — median tok/s over `samples` calls.

    The agent wall measured per-prompt mixes decode with tool roundtrips
    and reasoning chains, so it can't isolate tok/s. This hits the
    OpenAI-compatible `/v1/chat/completions` directly at temperature 0.0
    with a fixed 150-word prompt and `max_tokens` decode, then takes the
    median. Used as a tiebreaker after honesty/quality/consistency in
    `BrainScorecard.rank_key`.
    """
    text = prompt or (
        "Explain in about 150 words what a GPU does and why it is good at "
        "matrix math."
    )
    vals: list[float] = []
    for _ in range(max(1, int(samples))):
        try:
            s = _chat_once(base_url, model, text, max_tokens)
            if s.get("tok_s"):
                vals.append(float(s["tok_s"]))
        except Exception:  # noqa: BLE001 - probe is best-effort
            pass
    if not vals:
        return {"tok_s": None, "samples": []}
    return {"tok_s": _pctl(vals, 50), "samples": sorted(vals)}


# --- Hermes config swap ----------------------------------------------------


def point_hermes_at_endpoint(
    base_url: str,
    model: str,
    *,
    context_length: int = 64000,
    hermes_bin: str = "hermes",
    timeout: float = 60.0,
) -> None:
    """Repoint an already-configured Hermes at a different brain.

    Issues five `hermes config set` calls to patch model.provider,
    model.base_url, model.default, model.context_length, and the
    compression.context_length (Hermes reuses the served model as its
    compression model, so the auxiliary context floor has to match).

    Use for the bakeoff swap; for a clean first-time setup use
    `fieldkit.harness.configure_hermes` which renders a full config from a
    `LaneSpec`.
    """
    pairs = [
        ("model.provider", "custom"),
        ("model.base_url", base_url),
        ("model.default", model),
        ("model.context_length", str(int(context_length))),
        ("auxiliary.compression.context_length", str(int(context_length))),
    ]
    for k, v in pairs:
        subprocess.run(
            [hermes_bin, "config", "set", k, v],
            capture_output=True, text=True, check=False, timeout=timeout,
        )


# --- session-text helpers --------------------------------------------------

import re as _re  # local alias to avoid colliding with future regex callers
_THINK_RE = _re.compile(r"<think>.*?</think>", flags=_re.S)


def _strip_think(text: str) -> str:
    if not text:
        return ""
    out = _THINK_RE.sub("", text)
    if "</think>" in out:  # truncated/duplicated opener left behind
        out = out.rsplit("</think>", 1)[-1]
    return out.strip()


def _msg_content(m: Mapping[str, Any]) -> str:
    c = m.get("content")
    if isinstance(c, list):
        return " ".join(
            p.get("text", "") for p in c if isinstance(p, dict)
        ).strip()
    return c.strip() if isinstance(c, str) else ""


def _session_answer(rec: Mapping[str, Any]) -> str:
    """The final assistant answer text (last non-empty assistant message),
    `<think>`-stripped — matches what a human reading the transcript would
    quote as the model's reply."""
    content = ""
    for m in rec.get("messages") or []:
        if isinstance(m, dict) and m.get("role") == "assistant":
            c = _msg_content(m)
            if c:
                content = c
    return _strip_think(content)


def _session_tools(rec: Mapping[str, Any]) -> list[str]:
    names: list[str] = []
    for m in rec.get("messages") or []:
        if not isinstance(m, dict) or m.get("role") != "assistant":
            continue
        raw = m.get("tool_calls")
        calls: list[Any] = []
        if isinstance(raw, list):
            calls = raw
        elif isinstance(raw, str):
            try:
                v = json.loads(raw)
            except json.JSONDecodeError:
                v = []
            calls = v if isinstance(v, list) else []
        for c in calls:
            if isinstance(c, dict):
                n = (c.get("function") or {}).get("name") or c.get("name") or ""
                if n:
                    names.append(n)
    return names


# --- run / evaluate --------------------------------------------------------


@dataclass(frozen=True)
class _AttemptWindow:
    t_start: float
    t_end: float
    wall_s: float
    exit_code: int
    stdout: str
    timed_out: bool


def _run_hermes_prompt(
    prompt: str,
    *,
    cwd: Path,
    hermes_bin: str = "hermes",
    timeout: float = 360.0,
    extra_env: Mapping[str, str] | None = None,
) -> _AttemptWindow:
    """Run `hermes -z <prompt> --yolo` once; capture the timing window.

    A timeout is recorded as a soft failure (`timed_out=True`, the prompt
    eventually scores False) so one runaway can't nuke the whole eval.
    """
    env = dict(os.environ)
    env.setdefault("HERMES_STREAM_READ_TIMEOUT", "1800")
    if extra_env:
        env.update(extra_env)
    t0 = time.time()
    try:
        proc = subprocess.run(
            [hermes_bin, "-z", prompt, "--yolo"],
            cwd=str(cwd), env=env, capture_output=True, text=True,
            check=False, timeout=timeout,
        )
        return _AttemptWindow(
            t_start=t0,
            t_end=time.time(),
            wall_s=round(time.time() - t0, 1),
            exit_code=proc.returncode,
            stdout=proc.stdout,
            timed_out=False,
        )
    except subprocess.TimeoutExpired as exc:
        partial = exc.stdout or ""
        if isinstance(partial, bytes):
            partial = partial.decode("utf-8", "replace")
        return _AttemptWindow(
            t_start=t0,
            t_end=time.time(),
            wall_s=round(time.time() - t0, 1),
            exit_code=-1,
            stdout=partial,
            timed_out=True,
        )


def _score_attempt(
    prompt: Any,  # GradedPrompt
    recs: Sequence[Mapping[str, Any]],
    win: _AttemptWindow,
    *,
    attempt_idx: int,
) -> BrainAttempt:
    answer = " ".join(_session_answer(r) for r in recs)
    if not answer.strip():
        answer = _strip_think(win.stdout)
    tools = [t for r in recs for t in _session_tools(r)]
    res = score_answer(answer, prompt.check)
    want = prompt.expect_tool_any
    tool_ok = (not want) or any(any(w in t for w in want) for t in tools)
    fmt_errs = sum(
        r.tool_format_errors() for r in agent_runs_from_hermes_sessions(list(recs))
    )
    return BrainAttempt(
        attempt=attempt_idx,
        task_success=res.passed,
        why=res.why,
        tools_called=tuple(tools),
        correct_tool=bool(tool_ok),
        format_errors=int(fmt_errs),
        n_sessions=len(recs),
        wall_s=win.wall_s,
        timed_out=win.timed_out,
        answer_preview=answer[:400],
    )


def _avg(xs: Iterable[float | None], nd: int = 4) -> float | None:
    vals = [x for x in xs if x is not None]
    return round(sum(vals) / len(vals), nd) if vals else None


def evaluate_brain(
    suite: Any,  # GradedPromptSuite
    *,
    label: str,
    scratch_dir: str | Path,
    runs: int = 1,
    core_only: bool = False,
    available_conditions: Iterable[str] = (),
    base_url: str | None = None,
    model: str | None = None,
    hermes_bin: str = "hermes",
    prompt_timeout: float = 360.0,
    throughput_samples: int = 0,
    enable_telemetry: bool = False,
    session_export_path: str | Path | None = None,
    extra_env: Mapping[str, str] | None = None,
    on_attempt: Callable[[str, int, _AttemptWindow], None] | None = None,
) -> BrainScorecard:
    """Drive ONE already-pointed-at endpoint through the suite → `BrainScorecard`.

    Caller's responsibilities:
      - The scratch dir at `scratch_dir` has been seeded with whatever test
        fixtures the suite's prompts reference (paths are relative to it).
      - Hermes is already pointing at the endpoint to score (see
        `point_hermes_at_endpoint` if you need to swap).
      - If you want a `tokens_per_sec` field in the result, pass
        `base_url` + `model` AND `throughput_samples > 0`. The probe runs
        AFTER the suite (so the lane is still warm) and AFTER telemetry
        stops (so its decode isn't double-counted in GPU util).

    Sessions are exported once at the end (via `export_hermes_sessions`,
    source="cli") and bucketed to attempts by `bucket_hermes_sessions`. If
    `session_export_path` is set the JSONL is preserved there; otherwise
    it's written to a temp file inside `scratch_dir`.
    """
    scratch = Path(scratch_dir)
    scratch.mkdir(parents=True, exist_ok=True)
    selected = suite.select(
        core_only=core_only,
        available_conditions=tuple(available_conditions),
    )
    all_ids = [p.id for p in suite.prompts]
    skipped_reasons: dict[str, str] = {}
    for p in suite.prompts:
        if p in selected:
            continue
        if core_only and not p.core:
            skipped_reasons[p.id] = "core-only run"
        elif p.conditional and p.conditional not in set(available_conditions):
            skipped_reasons[p.id] = f"{p.conditional} not enabled"
        else:
            skipped_reasons[p.id] = "filtered"

    tele = Telemetry().start() if enable_telemetry else None
    per_prompt_windows: list[tuple[Any, list[_AttemptWindow]]] = []
    for p in selected:
        windows: list[_AttemptWindow] = []
        for k in range(max(1, int(runs))):
            win = _run_hermes_prompt(
                p.prompt, cwd=scratch, hermes_bin=hermes_bin,
                timeout=prompt_timeout, extra_env=extra_env,
            )
            if on_attempt is not None:
                on_attempt(p.id, k, win)
            windows.append(win)
        per_prompt_windows.append((p, windows))

    telemetry = tele.stop() if tele is not None else None
    throughput = None
    if throughput_samples > 0 and base_url and model:
        throughput = measure_throughput(
            base_url, model, samples=throughput_samples,
        )

    # export + bucket
    out_path = Path(session_export_path) if session_export_path else (
        scratch / "_hermes_brain_sessions.jsonl"
    )
    export_hermes_sessions(out_path, source="cli", hermes_bin=hermes_bin)
    all_recs: list[dict[str, Any]] = []
    for line in Path(out_path).read_text().splitlines():
        if line.strip():
            try:
                all_recs.append(json.loads(line))
            except json.JSONDecodeError:
                continue

    slots: list[_Slot] = []
    for p, windows in per_prompt_windows:
        for k, w in enumerate(windows):
            slots.append(_Slot(p.id, k, w.t_start, w.t_end))
    bucket = bucket_hermes_sessions(all_recs, slots)

    # score
    bucketed_recs: list[dict[str, Any]] = []
    prompt_scores: list[BrainPromptScore] = []
    for pid in all_ids:
        if pid in skipped_reasons:
            prompt_scores.append(BrainPromptScore(
                id=pid, category="", core=False, vibe=False, runs=0,
                pass_count=0, pass_rate=0.0, runaway_count=0,
                runaway_rate=0.0, agreement=0.0, correct_tool_rate=0.0,
                wall_min=None, wall_mean=None, wall_max=None,
                task_success=False, why="", answer_preview="",
                attempts=(), skipped=skipped_reasons[pid],
            ))
            continue

    for p, windows in per_prompt_windows:
        attempts: list[BrainAttempt] = []
        for k, w in enumerate(windows):
            recs = bucket.get((p.id, k), [])
            bucketed_recs.extend(recs)
            attempts.append(_score_attempt(p, recs, w, attempt_idx=k))
        n = len(attempts)
        passc = sum(1 for a in attempts if a.task_success)
        runawayc = sum(1 for a in attempts if a.timed_out)
        ctoolc = sum(1 for a in attempts if a.correct_tool)
        walls = [a.wall_s for a in attempts if a.wall_s is not None]
        agreement = max(passc, n - passc) / n if n else 0.0
        prompt_scores.append(BrainPromptScore(
            id=p.id, category=p.category, core=p.core, vibe=p.vibe,
            runs=n,
            pass_count=passc,
            pass_rate=round(passc / n, 4) if n else 0.0,
            runaway_count=runawayc,
            runaway_rate=round(runawayc / n, 4) if n else 0.0,
            agreement=round(agreement, 4),
            correct_tool_rate=round(ctoolc / n, 4) if n else 0.0,
            wall_min=min(walls) if walls else None,
            wall_mean=_avg(walls, 1),
            wall_max=max(walls) if walls else None,
            task_success=(passc * 2 >= n),
            why=attempts[0].why if attempts else "",
            answer_preview=attempts[0].answer_preview if attempts else "",
            attempts=tuple(attempts),
            skipped=None,
        ))

    # Re-order to match the input prompt order (skips inserted in pass 1
    # may have produced out-of-order results above; rebuild canonical).
    by_id = {ps.id: ps for ps in prompt_scores}
    ordered = tuple(by_id[i] for i in all_ids if i in by_id)
    core = [s for s in ordered if s.core and s.skipped is None]
    allp = [s for s in ordered if s.skipped is None]
    honesty = next(
        (s for s in ordered if s.id.endswith("honesty") or "honesty" in s.id),
        None,
    )
    jsonfmt = next(
        (s for s in ordered if "json" in s.id.lower() and "format" in s.id.lower()),
        None,
    )
    reliability = tool_call_reliability(
        agent_runs_from_hermes_sessions(bucketed_recs)
    )
    all_walls = [
        a.wall_s for s in allp for a in s.attempts if a.wall_s is not None
    ]
    latency = {
        "mean_s": _avg(all_walls, 1),
        "p50_s": _pctl(all_walls, 50),
        "p95_s": _pctl(all_walls, 95),
        "max_s": max(all_walls) if all_walls else None,
    }

    return BrainScorecard(
        label=label,
        runs=runs,
        core_pass=sum(1 for s in core if s.task_success),
        core_n=len(core),
        core_pass_rate=_avg([s.pass_rate for s in core]) or 0.0,
        consistency=_avg([s.agreement for s in core]) or 0.0,
        runaway_rate=_avg([s.runaway_rate for s in allp]) or 0.0,
        wall_mean_s=_avg([s.wall_mean for s in allp], 1),
        correct_tool_rate=_avg([s.correct_tool_rate for s in core]) or 0.0,
        honesty_pass_rate=honesty.pass_rate if honesty else None,
        json_format_pass_rate=jsonfmt.pass_rate if jsonfmt else None,
        tool_call_reliability=reliability,
        tokens_per_sec=(throughput or {}).get("tok_s") if throughput else None,
        throughput=throughput,
        latency=latency,
        telemetry=telemetry,
        per_prompt=ordered,
        error=None,
    )


def evaluate_brains(
    suite: Any,  # GradedPromptSuite
    candidates: Sequence[BrainCandidate],
    *,
    scratch_dir: str | Path,
    runs: int = 1,
    core_only: bool = False,
    available_conditions: Iterable[str] = (),
    hermes_bin: str = "hermes",
    prompt_timeout: float = 360.0,
    throughput_samples: int = 3,
    enable_telemetry: bool = True,
    warm_timeout: float = 900.0,
    headroom_gb: float = 8.0,
    on_progress: Callable[[BrainCandidate, str], None] | None = None,
) -> dict[str, BrainScorecard]:
    """Drive each candidate through the suite and return labels → scorecards.

    For each candidate: optionally `serve_lane(lane, guard=True,
    warm_timeout=...)`, `point_hermes_at_endpoint(...)` Hermes at it, call
    `evaluate_brain`, tear down. Errors in one candidate are caught and
    recorded on its scorecard's `error` field; the loop continues so a
    failing lane doesn't nuke the bakeoff.

    Caller still owns the scratch-dir seeding before this is called.
    `on_progress(cand, phase)` (if given) is invoked with phases:
    `"warming"`, `"evaluating"`, `"tearing_down"`, `"done"`, `"error"`.
    """
    # Look up `serve_lane` at CALL time (not import time) so tests can
    # patch `fieldkit.harness.brains.serve_lane` to bypass the live lane.
    results: dict[str, BrainScorecard] = {}
    for cand in candidates:
        if on_progress is not None:
            on_progress(cand, "warming" if cand.lane is not None else "evaluating")
        try:
            lane_ctx: Any
            if cand.lane is not None:
                lane_ctx = serve_lane(
                    cand.lane, guard=True, warm_timeout=warm_timeout,
                    headroom_gb=headroom_gb,
                )
            else:
                lane_ctx = nullcontext(None)
            with lane_ctx as live:
                base_url = cand.base_url
                if live is not None and getattr(live, "base_url", None):
                    base_url = live.base_url
                point_hermes_at_endpoint(
                    base_url, cand.model,
                    context_length=cand.context_length,
                    hermes_bin=hermes_bin,
                )
                if on_progress is not None and cand.lane is not None:
                    on_progress(cand, "evaluating")
                sc = evaluate_brain(
                    suite,
                    label=cand.label,
                    scratch_dir=scratch_dir,
                    runs=runs,
                    core_only=core_only,
                    available_conditions=available_conditions,
                    base_url=base_url,
                    model=cand.model,
                    hermes_bin=hermes_bin,
                    prompt_timeout=prompt_timeout,
                    throughput_samples=throughput_samples,
                    enable_telemetry=enable_telemetry,
                )
            results[cand.label] = sc
            if on_progress is not None:
                on_progress(cand, "done")
        except Exception as exc:  # noqa: BLE001 - record + continue to next lane
            err = f"{type(exc).__name__}: {exc}"
            results[cand.label] = BrainScorecard(
                label=cand.label, runs=runs, core_pass=0, core_n=0,
                core_pass_rate=0.0, consistency=0.0, runaway_rate=0.0,
                wall_mean_s=None, correct_tool_rate=0.0,
                honesty_pass_rate=None, json_format_pass_rate=None,
                tool_call_reliability={}, error=err,
            )
            if on_progress is not None:
                on_progress(cand, "error")
    return results
