# Copyright 2026 Manav Sehgal
# SPDX-License-Identifier: Apache-2.0
"""`fieldkit field-edition verify` — the §8 first-boot eval gate + receipt.

Implements §8 of ``_SPECS/arena-field-edition-v1.md``: a customer-visible,
honest eval gate that runs at first boot (AC-3) and after every update (§9).
It walks the five component gates, applies the **published floors** (no vanity
passes), and **always emits the receipt — pass or fail** (a failed-but-honest
receipt is the brand).

The §8 gate battery::

    fieldkit  import + version + the doctor matrix check        all green     <5 s
    advisor   curveball-v0.2 held-out + the refusal/private floor ≥80% · 9/9  ~1-3 min
    cortex    frozen mini recall set + the grounded-contract subset recall ≥0.95 ~1-2 min
    lane      LaneTruth smoke: launch → 1 generation → clean teardown          ~30-90 s
    hermes    one MCP-driven fieldkit tool round-trip (only if enabled)        ~30 s

Design (the deterministic-scripts invariant, same split as :mod:`doctor` and
:mod:`up`): the verdict is **pure**. A :class:`GateRunner` *measures* each
component (the only I/O — shelling to the live stack / benches) and returns raw
:class:`GateOutcome` metrics; :func:`evaluate_gates` applies the floors purely
and builds the :class:`VerifyReport`; :meth:`VerifyReport.receipt` renders the
receipt dict without a clock (the writer stamps the time). So the whole
pass/fail logic is unit-testable with a fake runner — no DGX box, no live stack.

**Failure UX (§8):** every failing gate names the **component**, the **gate**,
and the **fix**. The report is rendered in the Arena cockpit's eval drawer at
M2; today ``verify`` emits the receipt JSON + an exit code.

**Status.** The orchestration, the pure verdict, and the receipt run for real,
and four of the five gates are **measured live** against the running stack:

* ``fieldkit`` — import + version + the doctor matrix (no live stack needed).
* ``advisor`` — :class:`LiveGateRunner` replays the vendored frozen
  curveball-v0.2 packets (:mod:`.advisor`) through the resident lane and applies
  the §8 behavioral floor (curveball ≥80% + refusals 9/9) — the same scorer that
  produced the published 85.7% receipt.
* ``cortex`` — **both halves** live: the **recall-half** scores source_recall@5
  over the vendored frozen recall set (:mod:`.recall`) against pgvector +
  embedder, and the **grounded-contract half** (:mod:`.grounded`) has the lane
  answer a deterministic stratified slice of those same frozen probes over
  *live-retrieved* context, scoring citation integrity + refusal hygiene.
* ``lane`` — warm-resident smoke: the resident Advisor lane is reachable
  (launched) and serves one generation (generated). Per the §6/§8 reconciliation
  (2026-06-13) first-boot ``verify`` does **not** tear the warm default down —
  teardown-clean is the ``down`` / ``repair`` lifecycle gates' job.

Each live gate returns an honest ``error`` (naming the missing piece + fix) when
its slice of the stack is down — never a vanity pass. The optional ``hermes``
gate still drops into :class:`LiveGateRunner` as the MCP round-trip is wired;
until then it is ``skipped`` unless ``--hermes`` is passed.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Mapping

from fieldkit.field_edition.compose import FieldEditionConfig, default_config

__all__ = [
    "GATES",
    "ADVISOR_CURVEBALL_FLOOR",
    "ADVISOR_REFUSALS_TOTAL",
    "CORTEX_RECALL_FLOOR",
    "GateSpec",
    "GateOutcome",
    "GateResult",
    "VerifyReport",
    "GateRunner",
    "LiveGateRunner",
    "assess_gate",
    "evaluate_gates",
    "run_verify",
    "write_receipt",
]

#: The published floors — sha-pinned to the frozen benches (the proof-control
#: discipline). These ARE the thresholds; raising/lowering them is a spec change.
ADVISOR_CURVEBALL_FLOOR = 0.80
ADVISOR_REFUSALS_TOTAL = 9
CORTEX_RECALL_FLOOR = 0.95
#: Chunks fetched per query before source-level dedup (>= 10 unique sources),
#: matching ``score_recall_live.CHUNK_POOL`` so the gate measures the same number.
CORTEX_RECALL_POOL = 80

#: The §8 ``hermes`` gate's probe — one MCP-driven ``fieldkit`` tool round-trip.
#: A **read-only capabilities lookup** (no GPU, model, disk, or network), so the
#: round-trip respects the one-lane invariant (the resident Advisor lane the
#: other gates proved warm is untouched) and the ~30 s budget. The driving brain
#: (a full Hermes agent picking the tool) is the heavier H4 milestone, not a
#: first-boot gate — a 30B MoE brain would blow the one-lane budget here.
HERMES_PROBE_TOOL = "spark_inference_envelope"
HERMES_PROBE_ARGS: Mapping[str, object] = {"model_size": "8B params bf16"}

# Gate verdict statuses.
_PASS = "pass"
_FAIL = "fail"
_ERROR = "error"  # the gate could not run (stack down, bench not wired)
_SKIPPED = "skipped"  # an optional gate the operator did not enable


class _McpExtraMissing(ImportError):
    """The ``fieldkit[harness]`` extra (the ``mcp`` SDK) is not installed — the
    optional ``hermes`` gate cannot drive the ``fieldkit`` MCP server. An honest
    gate ``error`` (with the install fix), never a vanity pass."""


@dataclass(frozen=True)
class GateSpec:
    """One component gate in the §8 battery."""

    key: str
    label: str
    metric: str  # human description of what is measured
    threshold: str  # human-readable published floor
    fix: str  # the §8 failure-UX fix shown when the gate fails / errors
    optional: bool = False  # hermes only runs when --hermes is passed
    #: The metric key whose value is the receipt headline (None for boolean gates).
    headline_key: str | None = None


GATES: tuple[GateSpec, ...] = (
    GateSpec(
        key="fieldkit",
        label="fieldkit",
        metric="import + version + the doctor matrix check",
        threshold="all green",
        fix="run `fieldkit field-edition doctor` to see the matrix reason + fix",
    ),
    GateSpec(
        key="advisor",
        label="Advisor",
        metric="curveball-v0.2 held-out + the refusal/private-state floor",
        threshold=f"curveball-v0.2 ≥{ADVISOR_CURVEBALL_FLOOR:.0%}; refusals {ADVISOR_REFUSALS_TOTAL}/{ADVISOR_REFUSALS_TOTAL}",
        fix="re-pull the pinned Advisor GGUF revision — `fieldkit field-edition repair advisor`",
        headline_key="curveball_v02",
    ),
    GateSpec(
        key="cortex",
        label="Cortex",
        metric="frozen recall set (recall@5) + grounded-contract over live retrieval",
        threshold=f"recall@5 ≥{CORTEX_RECALL_FLOOR:.2f}; citation + refusal contract pass",
        fix="check the embedder + pgvector are up and the corpus is ingested — `fieldkit field-edition repair cortex`",
        headline_key="recall_at_5",
    ),
    GateSpec(
        key="lane",
        label="Serving lane",
        metric="resident-lane smoke: reachable + one generation (warm-resident)",
        threshold="lane up + 1 gen (warm default stays resident)",
        fix="inspect `docker compose logs of-advisor-lane`; re-run `fieldkit field-edition up`",
    ),
    GateSpec(
        key="hermes",
        label="Hermes",
        metric="one MCP-driven fieldkit tool round-trip",
        threshold="tool call returns",
        fix="install the MCP harness extra (`pip install fieldkit[harness]`) or omit --hermes to skip (§8)",
        optional=True,
    ),
)


@dataclass(frozen=True)
class GateOutcome:
    """What a :class:`GateRunner` measured for one gate (raw — no pass/fail).

    ``metrics`` carries the measured numbers (fractions in ``0..1`` / boolean
    ``1.0``/``0.0`` flags) that the pure floor logic compares. ``note`` is an
    extra human string carried into the receipt (e.g. the fieldkit version).
    ``error`` is set when the gate could not be measured at all — it short-
    circuits to an ``error`` verdict with the fix, never a silent pass.
    """

    key: str
    metrics: Mapping[str, float] = field(default_factory=dict)
    note: str = ""
    error: str | None = None


@dataclass(frozen=True)
class GateResult:
    """The verdict for one gate."""

    key: str
    label: str
    metric: str
    threshold: str
    status: str  # pass | fail | error | skipped
    detail: str
    value: float | None
    note: str
    fix: str

    @property
    def ok(self) -> bool:
        return self.status in (_PASS, _SKIPPED)


@dataclass(frozen=True)
class VerifyReport:
    """Aggregate verdict over the whole §8 battery."""

    results: tuple[GateResult, ...]

    @property
    def ok(self) -> bool:
        """True only when no gate failed or errored (skipped is fine)."""
        return all(r.ok for r in self.results)

    @property
    def failures(self) -> tuple[GateResult, ...]:
        return tuple(r for r in self.results if not r.ok)

    def summary(self) -> dict[str, int]:
        counts = {_PASS: 0, _FAIL: 0, _ERROR: 0, _SKIPPED: 0}
        for r in self.results:
            counts[r.status] = counts.get(r.status, 0) + 1
        return {
            "passed": counts[_PASS],
            "failed": counts[_FAIL],
            "errored": counts[_ERROR],
            "skipped": counts[_SKIPPED],
        }

    def receipt(self, *, generated_at: str | None = None, **meta: object) -> dict:
        """Render the §8 receipt dict (pure — the writer supplies the clock).

        Always rendered, pass *or* fail (the honest-receipt invariant)."""
        return {
            "version": 1,
            "kind": "field-edition-verify",
            "generated_at": generated_at,
            "ok": self.ok,
            "summary": self.summary(),
            "gates": [
                {
                    "key": r.key,
                    "label": r.label,
                    "metric": r.metric,
                    "threshold": r.threshold,
                    "status": r.status,
                    "detail": r.detail,
                    "value": r.value,
                    "note": r.note,
                    "fix": r.fix if not r.ok else "",
                }
                for r in self.results
            ],
            **meta,
        }


# --- Pure floor logic (per-gate; fully unit-testable) ------------------------


def _assess_fieldkit(m: Mapping[str, float]) -> tuple[bool, str]:
    parts = []
    ok = True
    for key, label in (("import_ok", "import"), ("version_ok", "version"), ("matrix_ok", "matrix")):
        good = m.get(key, 0.0) >= 1.0
        ok = ok and good
        parts.append(f"{label} {'ok' if good else 'FAIL'}")
    return ok, ", ".join(parts)


def _assess_advisor(m: Mapping[str, float]) -> tuple[bool, str]:
    curveball = m.get("curveball_v02", 0.0)
    refusals = int(m.get("refusals_passed", 0.0))
    total = int(m.get("refusals_total", ADVISOR_REFUSALS_TOTAL))
    ok = curveball >= ADVISOR_CURVEBALL_FLOOR and refusals >= total
    detail = f"curveball-v0.2 {curveball:.1%} (floor {ADVISOR_CURVEBALL_FLOOR:.0%}), refusals {refusals}/{total}"
    return ok, detail


def _assess_cortex(m: Mapping[str, float]) -> tuple[bool, str]:
    recall = m.get("recall_at_5", 0.0)
    contract = m.get("contract_pass", 0.0) >= 1.0
    ok = recall >= CORTEX_RECALL_FLOOR and contract
    detail = f"recall@5 {recall:.3f} (floor {CORTEX_RECALL_FLOOR:.2f}), contract {'pass' if contract else 'FAIL'}"
    return ok, detail


def _assess_lane(m: Mapping[str, float]) -> tuple[bool, str]:
    # Warm-resident floor (§6/§8 reconciliation, 2026-06-13): the default 4B
    # Advisor lane stays warm and never unloads (§6 zero-swap common path), so
    # first-boot `verify` does NOT tear it down — the gate proves the resident
    # lane is reachable and generates. "Teardown clean" is exercised by the
    # `down` / `repair` lifecycle gates, not by first-boot verify.
    launched = m.get("launched", 0.0) >= 1.0
    generated = m.get("generated", 0.0) >= 1.0
    ok = launched and generated
    detail = (
        f"launch {'ok' if launched else 'FAIL'}, "
        f"generation {'ok' if generated else 'FAIL'} "
        "(warm-resident; teardown-clean covered by down/repair)"
    )
    return ok, detail


def _assess_hermes(m: Mapping[str, float]) -> tuple[bool, str]:
    ok = m.get("tool_returned", 0.0) >= 1.0
    return ok, f"tool round-trip {'returned' if ok else 'FAILED'}"


_ASSESSORS: dict[str, Callable[[Mapping[str, float]], tuple[bool, str]]] = {
    "fieldkit": _assess_fieldkit,
    "advisor": _assess_advisor,
    "cortex": _assess_cortex,
    "lane": _assess_lane,
    "hermes": _assess_hermes,
}


def assess_gate(key: str, metrics: Mapping[str, float]) -> tuple[bool, str]:
    """Pure: apply one gate's published floor to its measured metrics."""
    try:
        assessor = _ASSESSORS[key]
    except KeyError:
        raise ValueError(f"unknown gate: {key!r}") from None
    return assessor(metrics)


def evaluate_gates(
    outcomes: Mapping[str, GateOutcome | None],
    *,
    gates: tuple[GateSpec, ...] = GATES,
    with_hermes: bool = False,
) -> VerifyReport:
    """Pure verdict: turn measured outcomes into the §8 report (no I/O).

    An outcome that is ``None`` (or whose gate is optional + not enabled) is
    ``skipped``; an outcome carrying ``error`` becomes an ``error`` verdict
    (with the spec fix); otherwise the gate's floor decides ``pass``/``fail``.
    """
    results: list[GateResult] = []
    for spec in gates:
        outcome = outcomes.get(spec.key)
        if spec.optional and not with_hermes:
            results.append(_skipped(spec, "not enabled (omit --hermes to skip)"))
            continue
        if outcome is None:
            results.append(_skipped(spec, "not measured"))
            continue
        if outcome.error:
            results.append(
                GateResult(
                    spec.key, spec.label, spec.metric, spec.threshold, _ERROR,
                    outcome.error, None, outcome.note, spec.fix,
                )
            )
            continue
        passed, detail = assess_gate(spec.key, outcome.metrics)
        value = outcome.metrics.get(spec.headline_key) if spec.headline_key else None
        results.append(
            GateResult(
                spec.key, spec.label, spec.metric, spec.threshold,
                _PASS if passed else _FAIL, detail, value, outcome.note, spec.fix,
            )
        )
    return VerifyReport(tuple(results))


def _skipped(spec: GateSpec, reason: str) -> GateResult:
    return GateResult(
        spec.key, spec.label, spec.metric, spec.threshold, _SKIPPED, reason, None, "", ""
    )


# --- Measurement layer (the only I/O) ----------------------------------------


class GateRunner:
    """Measures each gate. Subclass / fake for tests; :meth:`measure` dispatches
    a gate key to its method so the orchestrator stays dispatch-agnostic."""

    def measure(self, key: str, config: FieldEditionConfig) -> GateOutcome:
        return getattr(self, key)(config)

    def fieldkit(self, config: FieldEditionConfig) -> GateOutcome:  # pragma: no cover - overridden
        raise NotImplementedError

    def advisor(self, config: FieldEditionConfig) -> GateOutcome:  # pragma: no cover
        raise NotImplementedError

    def cortex(self, config: FieldEditionConfig) -> GateOutcome:  # pragma: no cover
        raise NotImplementedError

    def lane(self, config: FieldEditionConfig) -> GateOutcome:  # pragma: no cover
        raise NotImplementedError

    def hermes(self, config: FieldEditionConfig) -> GateOutcome:  # pragma: no cover
        raise NotImplementedError


class LiveGateRunner(GateRunner):
    """Measures the gates against the real box.

    ``fieldkit`` (import + version + matrix), ``advisor`` (frozen curveball set
    through the resident lane), ``cortex`` (recall-half over pgvector + embedder
    **and** the grounded-contract half through the lane), ``lane`` (resident
    warm-lane reachable + one generation), and the optional ``hermes`` (one MCP
    tool round-trip against the ``fieldkit`` MCP server) are all measured live.
    Any gate whose slice of the stack is down returns an honest ``error`` naming
    the missing piece, never a vanity pass.
    """

    def fieldkit(self, config: FieldEditionConfig) -> GateOutcome:
        metrics = {"import_ok": 1.0, "version_ok": 0.0, "matrix_ok": 0.0}
        note = ""
        try:
            from fieldkit import __version__ as version

            metrics["version_ok"] = 1.0 if version else 0.0
            note = f"fieldkit {version}"
        except Exception as err:  # noqa: BLE001 — any import/version failure is a gate fail
            return GateOutcome("fieldkit", {"import_ok": 0.0}, note=str(err)[:200])
        try:
            from fieldkit.field_edition.doctor import run_doctor

            metrics["matrix_ok"] = 1.0 if run_doctor().ok else 0.0
        except Exception as err:  # noqa: BLE001
            metrics["matrix_ok"] = 0.0
            note = f"{note}; matrix probe failed: {str(err)[:120]}"
        return GateOutcome("fieldkit", metrics, note=note)

    #: How long to wait on one lane generation before giving up (seconds).
    LANE_CHAT_TIMEOUT = 180

    def advisor(self, config: FieldEditionConfig) -> GateOutcome:
        # Score the resident Advisor lane against the vendored frozen
        # curveball-v0.2 set: replay each packet's baked messages through the
        # OpenAI-compatible lane, then apply the §8 behavioral floor (the same
        # scorer that produced the published 85.7% receipt). Honest error if the
        # lane is unreachable — never a vanity pass.
        try:
            from fieldkit.field_edition.advisor import load_curveball_set, score_curveball_set
        except Exception as err:  # noqa: BLE001 — missing optional dep
            return self._stack_pending("advisor", f"curveball scorer unavailable ({str(err)[:80]})")
        try:
            cset = load_curveball_set()
        except Exception as err:  # noqa: BLE001 — tampered/missing vendored set
            return GateOutcome("advisor", error=f"vendored curveball set unreadable: {str(err)[:140]}")

        base = self._lane_base_url(config)
        outputs: list[str] = []
        for packet in cset.rows:
            try:
                outputs.append(
                    self._lane_chat(
                        base,
                        config.lane.gguf_file,
                        [dict(m) for m in packet.messages],
                        max_tokens=cset.max_tokens,
                        temperature=cset.temperature,
                        reasoning_mode=cset.reasoning_mode,
                    )
                )
            except Exception as err:  # noqa: BLE001 — lane down / generation failed
                return GateOutcome(
                    "advisor",
                    error=(
                        f"Advisor lane unreachable — curveball gate could not run "
                        f"({str(err)[:100]}). Is the serving lane up at {base}? "
                        "(M2 — `fieldkit field-edition up` brings up the pinned Q4_K_M lane)"
                    ),
                )

        report = score_curveball_set(cset.rows, outputs)
        m = report.as_metrics()
        passed_floor = (
            report.curveball_at >= cset.curveball_floor
            and report.refusals_passed >= report.refusals_total
        )
        note = (
            f"curveball-v0.2 {report.curveball_at:.1%} ({report.passed}/{report.total}, "
            f"floor {cset.curveball_floor:.0%}), refusals "
            f"{report.refusals_passed}/{report.refusals_total}"
            + (f"; misses: {', '.join(report.misses)}" if report.misses else "")
        )
        # Real measurement → let the pure floor (evaluate_gates) render pass/fail;
        # only the unreachable case above is an honest error.
        return GateOutcome("advisor", metrics=m, note=note)

    def cortex(self, config: FieldEditionConfig) -> GateOutcome:
        # BOTH halves measured live against the running Cortex stack:
        #   recall-half  — source_recall@5 over the vendored frozen recall set
        #                  (pgvector + embedder only).
        #   grounded-half — citation integrity + refusal hygiene: the resident
        #                  lane answers each probe over LIVE-retrieved context
        #                  (the full retrieve → ground → generate → cite loop).
        # Honest error if retrieval is unreachable; if retrieval is up but the
        # lane is down, recall is surfaced live and the grounded half reports an
        # honest non-pass — never a vanity pass on recall alone.
        try:
            from fieldkit.field_edition.recall import load_recall_set, score_recall_set
            from fieldkit.field_edition import grounded as G
            from fieldkit.memory import MemoryIndex
        except Exception as err:  # noqa: BLE001 — missing optional dep
            return self._stack_pending(
                "cortex", f"cortex gate deps unavailable ({str(err)[:80]})"
            )
        try:
            rset = load_recall_set()
        except Exception as err:  # noqa: BLE001 — tampered/missing vendored set
            return GateOutcome(
                "cortex", error=f"vendored recall set unreadable: {str(err)[:140]}"
            )

        index = MemoryIndex(table=rset.corpus_table)

        def retrieve(question: str) -> list[str]:
            hits = index.query(question, top_k=CORTEX_RECALL_POOL)
            ordered: list[str] = []
            for hit in hits:
                sid = str(hit["slug"])
                if sid not in ordered:
                    ordered.append(sid)
            return ordered

        # --- recall-half ---
        try:
            recall = score_recall_set(rset.rows, retrieve, k=5)
        except Exception as err:  # noqa: BLE001 — stack down / corpus not ingested
            return GateOutcome(
                "cortex",
                error=(
                    f"Cortex retrieval unreachable — recall-half could not run "
                    f"({str(err)[:100]}). Is the stack up and `{rset.corpus_table}` "
                    "ingested? (M2 — `fieldkit field-edition up` brings up + ingests "
                    "the proven-matrix Cortex stack)"
                ),
            )
        recall_ok = recall.recall_at_5 >= CORTEX_RECALL_FLOOR
        recall_note = (
            f"recall@5 {recall.recall_at_5:.3f} over {recall.answerable_n} rows "
            f"({'≥' if recall_ok else '<'}{CORTEX_RECALL_FLOOR:.2f}), "
            f"{len(recall.misses)} miss(es)"
        )

        # --- grounded-contract half (needs the resident lane) ---
        probes = G.select_contract_probes(rset.rows)
        base = self._lane_base_url(config)
        outputs: list[str] = []
        for probe in probes:
            hits = index.query(probe.question, top_k=G.DEFAULT_TOP_K)
            blocks = G.build_grounded_blocks(
                hits,
                probe.question,
                max_sources=G.DEFAULT_MAX_SOURCES,
                excerpt_chars=G.DEFAULT_EXCERPT_CHARS,
            )
            messages = G.build_messages(
                probe.question, blocks, reasoning_mode=G.DEFAULT_REASONING_MODE
            )
            try:
                outputs.append(
                    self._lane_chat(
                        base,
                        config.lane.gguf_file,
                        messages,
                        max_tokens=G.DEFAULT_MAX_TOKENS,
                        temperature=G.DEFAULT_TEMPERATURE,
                        reasoning_mode=G.DEFAULT_REASONING_MODE,
                    )
                )
            except Exception as err:  # noqa: BLE001 — lane down → grounded half can't run
                return GateOutcome(
                    "cortex",
                    metrics=recall.as_metrics(),
                    note=recall_note,
                    error=(
                        f"recall-half live ✓ ({recall_note}); grounded-contract half "
                        f"could not run — serving lane unreachable at {base} "
                        f"({str(err)[:80]}). (M2 — `fieldkit field-edition up` brings "
                        "up the pinned Q4_K_M lane)"
                    ),
                )

        grounded = G.score_grounded(probes, outputs)
        metrics = {**recall.as_metrics(), **grounded.as_metrics()}
        note = (
            f"{recall_note}; grounded-contract: citation "
            f"{grounded.cite_passed}/{grounded.cite_total} "
            f"({grounded.citation_rate:.1%}, floor {G.GROUNDED_CONTRACT_FLOOR:.0%}), "
            f"refusals {grounded.refusals_passed}/{grounded.refusals_total}"
            + (f"; misses: {', '.join(grounded.misses)}" if grounded.misses else "")
        )
        # Real measurement on both halves → let the pure floor render pass/fail.
        return GateOutcome("cortex", metrics=metrics, note=note)

    def lane(self, config: FieldEditionConfig) -> GateOutcome:
        # Warm-resident smoke (§6/§8): prove the resident Advisor lane is
        # reachable (launched) and serves one generation (generated). We do NOT
        # tear it down — the default 4B stays warm (§6); teardown-clean is the
        # `down` / `repair` lifecycle gates' job. Unreachable lane → honest
        # error (stack not up); reachable-but-cannot-generate → a real FAIL.
        base = self._lane_base_url(config)
        try:
            served = self._lane_models(base)
        except Exception as err:  # noqa: BLE001 — lane down / not up yet
            return GateOutcome(
                "lane",
                error=(
                    f"Serving lane unreachable at {base} — resident-lane smoke "
                    f"could not run ({str(err)[:100]}). Is the lane up? "
                    "(M2 — `fieldkit field-edition up` brings up the pinned Q4_K_M lane)"
                ),
            )
        try:
            output = self._lane_chat(
                base,
                config.lane.gguf_file,
                [{"role": "user", "content": "Reply with the single word: ready."}],
                max_tokens=16,
                temperature=0.0,
                reasoning_mode="off",
            )
        except Exception as err:  # noqa: BLE001 — reachable but generation failed
            return GateOutcome(
                "lane",
                metrics={"launched": 1.0, "generated": 0.0},
                note=f"lane reachable ({served}); generation FAILED: {str(err)[:120]}",
            )
        generated = 1.0 if output.strip() else 0.0
        note = (
            f"lane up ({served}); 1 gen {'ok' if generated else 'EMPTY'} "
            f"({len(output.strip())} chars); warm-resident — no teardown at first-boot"
        )
        return GateOutcome("lane", metrics={"launched": 1.0, "generated": generated}, note=note)

    #: How long to wait on the MCP round-trip (spawn server + initialize + one
    #: read-only tool call) before giving up (seconds). The probe touches no GPU.
    HERMES_ROUNDTRIP_TIMEOUT = 60

    def hermes(self, config: FieldEditionConfig) -> GateOutcome:
        # One MCP-driven `fieldkit` tool round-trip (§8): drive the
        # fieldkit-as-MCP server — the very surface a Hermes harness drives — with
        # a real MCP client over stdio and confirm a read-only tool call returns.
        # Lane-safe + deterministic: the probe is a capabilities lookup (no GPU,
        # model, disk, or network), so it does NOT disturb the resident Advisor
        # lane and runs well inside the ~30 s budget. Honest error if the MCP
        # harness extra is missing or the round-trip fails — never a vanity pass.
        try:
            result = self._mcp_tool_roundtrip(
                HERMES_PROBE_TOOL, dict(HERMES_PROBE_ARGS)
            )
        except _McpExtraMissing as err:
            return GateOutcome(
                "hermes",
                error=(
                    f"MCP harness extra not installed ({str(err)[:80]}). The "
                    "`hermes` gate drives the `fieldkit` MCP server — install it "
                    "with `pip install fieldkit[harness]`, or omit --hermes to skip."
                ),
            )
        except Exception as err:  # noqa: BLE001 — any transport/server failure is honest
            return GateOutcome(
                "hermes",
                error=(
                    f"MCP tool round-trip failed ({str(err)[:120]}). Could the "
                    f"`fieldkit` MCP server start (`python -m fieldkit.harness.mcp`)? "
                    "Omit --hermes to skip the optional gate (§8)."
                ),
            )
        returned = 1.0 if result.get("returned") else 0.0
        note = (
            f"MCP round-trip {'ok' if returned else 'EMPTY'} — called "
            f"`{result.get('tool', HERMES_PROBE_TOOL)}` over stdio "
            f"({int(result.get('tools_n', 0))} fieldkit tools exposed); "
            f"tool result {'returned' if returned else 'was empty/errored'}"
        )
        # Real round-trip → let the pure floor render pass/fail; only the
        # extra-missing / transport-down cases above are honest errors.
        return GateOutcome("hermes", metrics={"tool_returned": returned}, note=note)

    def _mcp_tool_roundtrip(
        self, tool_name: str, arguments: Mapping[str, object]
    ) -> Mapping[str, object]:
        """One real MCP client → ``fieldkit`` MCP server tool round-trip (stdio).

        Spawns ``python -m fieldkit.harness.mcp`` and drives it with an MCP
        ``ClientSession``: ``initialize`` → ``list_tools`` → ``call_tool``. The
        ``fieldkit`` MCP server is the exact surface a Hermes harness drives, so
        this measures the §8 contract ("one MCP-driven fieldkit tool round-trip")
        end-to-end over the real JSON-RPC stdio transport — without booting a
        brain (the heavier H4 milestone). Returns ``{returned, tools_n, tool}``.

        Raises :class:`_McpExtraMissing` when the ``fieldkit[harness]`` extra (the
        ``mcp`` SDK) is absent; injectable as a seam so the floor logic is
        unit-testable without the SDK or a subprocess.
        """
        import sys

        try:
            from mcp import ClientSession, StdioServerParameters
            from mcp.client.stdio import stdio_client
        except ImportError as exc:  # the `fieldkit[harness]` extra is not installed
            raise _McpExtraMissing(str(exc)) from exc
        import asyncio

        async def _roundtrip() -> Mapping[str, object]:
            params = StdioServerParameters(
                command=sys.executable, args=["-m", "fieldkit.harness.mcp"]
            )
            async with (
                stdio_client(params) as (read, write),
                ClientSession(read, write) as session,
            ):
                await session.initialize()
                listed = await session.list_tools()
                result = await session.call_tool(tool_name, dict(arguments))
                content = getattr(result, "content", None) or []
                return {
                    "returned": not getattr(result, "isError", False) and bool(content),
                    "tools_n": len(getattr(listed, "tools", []) or []),
                    "tool": tool_name,
                }

        async def _driver() -> Mapping[str, object]:
            return await asyncio.wait_for(
                _roundtrip(), timeout=self.HERMES_ROUNDTRIP_TIMEOUT
            )

        return asyncio.run(_driver())

    @staticmethod
    def _lane_base_url(config: FieldEditionConfig) -> str:
        """The OpenAI-compatible base URL of the resident Advisor lane.

        The lane container publishes its port on the loopback (per the §7
        Compose bundle); the pipx cockpit + the gate reach it at
        ``127.0.0.1:<port>/v1``."""
        return f"http://127.0.0.1:{config.lane.port}/v1"

    def _lane_models(self, base_url: str) -> str:
        """The resident lane's served model id (proves the lane is up; stdlib).

        Hits the OpenAI-compatible ``/v1/models`` and returns the first served
        model name — a successful round-trip is the ``launched`` signal for the
        §8 lane gate."""
        import json as _json
        import urllib.request

        req = urllib.request.Request(
            f"{base_url.rstrip('/')}/models",
            headers={"Authorization": "Bearer not-needed"},
            method="GET",
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = _json.loads(resp.read().decode("utf-8"))
        # llama.cpp serves {"models":[{"name":...}]}; OpenAI serves {"data":[{"id":...}]}.
        entries = data.get("models") or data.get("data") or []
        if not entries:
            raise RuntimeError("/v1/models returned no served model")
        first = entries[0]
        return str(first.get("name") or first.get("id") or "model")

    def _lane_chat(
        self,
        base_url: str,
        model: str,
        messages: list[dict[str, str]],
        *,
        max_tokens: int,
        temperature: float,
        reasoning_mode: str,
    ) -> str:
        """One OpenAI-compatible chat round-trip (stdlib only — no new dep).

        Mirrors ``scripts/orionfold_advisor/preflight._chat``: ``reasoning_mode
        == 'off'`` sends ``chat_template_kwargs={'enable_thinking': False}``, and
        a model that splits reasoning into ``reasoning_content`` is re-folded so
        the §8 thinking-leak check sees it (a leak must still fail the gate)."""
        import json as _json
        import urllib.request

        payload: dict[str, object] = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if reasoning_mode == "off":
            payload["chat_template_kwargs"] = {"enable_thinking": False}
        req = urllib.request.Request(
            f"{base_url.rstrip('/')}/chat/completions",
            data=_json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json", "Authorization": "Bearer not-needed"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=self.LANE_CHAT_TIMEOUT) as resp:
            data = _json.loads(resp.read().decode("utf-8"))
        message = data["choices"][0]["message"]
        content = message.get("content") or ""
        reasoning = message.get("reasoning_content") or ""
        if reasoning and "<think>" not in content:
            content = f"<think>{reasoning}</think>{content}"
        return str(content)

    @staticmethod
    def _stack_pending(key: str, what: str) -> GateOutcome:
        return GateOutcome(
            key,
            error=(
                f"{what} (M2 — needs `fieldkit field-edition up` to have brought up "
                "the proven-matrix stack + the pinned Q4_K_M model)"
            ),
        )


# --- Thin I/O: the receipt writer + the orchestrator -------------------------


def write_receipt(
    report: VerifyReport,
    receipt_dir: Path,
    *,
    generated_at: str | None = None,
    stamp: str = "latest",
    **meta: object,
) -> Path:
    """Write the receipt JSON and return its path. Always called — pass or fail.

    Writes ``verify-<stamp>.json`` (``stamp`` defaults to ``latest`` so the
    cockpit can always read the most recent receipt at a stable path; the
    orchestrator passes a timestamp for the archival copy)."""
    receipt_dir.mkdir(parents=True, exist_ok=True)
    path = receipt_dir / f"verify-{stamp}.json"
    path.write_text(
        json.dumps(report.receipt(generated_at=generated_at, **meta), indent=2) + "\n",
        encoding="utf-8",
    )
    return path


def run_verify(
    config: FieldEditionConfig | None = None,
    *,
    runner: GateRunner | None = None,
    with_hermes: bool = False,
    receipt_dir: Path | None = None,
    generated_at: str | None = None,
    on_event: Callable[[str], None] | None = None,
) -> tuple[VerifyReport, Path]:
    """Run the §8 battery, write the receipt (always), return ``(report, path)``.

    ``generated_at`` is injectable for deterministic tests; the CLI passes the
    real UTC time. The receipt is written even when gates fail/error — a
    failed-but-honest receipt is the brand (§8)."""
    cfg = config or default_config()
    run = runner or LiveGateRunner()
    emit = on_event or (lambda _msg: None)

    outcomes: dict[str, GateOutcome | None] = {}
    for spec in GATES:
        if spec.optional and not with_hermes:
            outcomes[spec.key] = None
            continue
        emit(f"▶ {spec.label}: {spec.metric}")
        outcome = run.measure(spec.key, cfg)
        outcomes[spec.key] = outcome
        # Surface the per-gate result immediately (honest live feedback).
        passed, detail = (
            (False, outcome.error)
            if outcome.error
            else assess_gate(spec.key, outcome.metrics)
        )
        emit(f"{'✓' if passed else '✗'} {spec.label}: {detail}")

    report = evaluate_gates(outcomes, with_hermes=with_hermes)

    if generated_at is None:
        from datetime import datetime, timezone

        generated_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    target = receipt_dir or (cfg.home / "receipts")
    # Stable "latest" + an archival timestamped copy.
    stamp = generated_at.replace(":", "").replace("-", "").replace("+0000", "").replace("T", "-")
    write_receipt(report, target, generated_at=generated_at, stamp="latest")
    path = write_receipt(report, target, generated_at=generated_at, stamp=stamp)
    return report, path
