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

**M1 status.** The orchestration, the pure verdict, and the receipt run for real
now, and the ``fieldkit`` gate is measured live (import + version + matrix). The
``cortex`` gate's **recall-half** is also measured live today — over the vendored
frozen recall set (:mod:`.recall`) against the running pgvector + embedder — and
reported honestly: the gate still cannot fully PASS because its grounded-contract
generation half (citation integrity + refusal hygiene) needs the serving lane
(M2). The ``advisor``/``lane``/``hermes`` gates likewise need the live stack +
the pinned Q4_K_M model (M2): :class:`LiveGateRunner` reports them as an honest
``error`` ("stack not up / bench not yet wired") rather than a vanity pass,
exactly as ``up``'s live phases fail honestly until the proven-matrix images
land. The receipt + verdict + CLI are complete and tested today; the remaining
bench measurements drop into :class:`LiveGateRunner` at M2.
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

# Gate verdict statuses.
_PASS = "pass"
_FAIL = "fail"
_ERROR = "error"  # the gate could not run (stack down, bench not wired)
_SKIPPED = "skipped"  # an optional gate the operator did not enable


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
        metric="frozen mini recall set + the grounded-contract subset",
        threshold=f"recall@5 ≥{CORTEX_RECALL_FLOOR:.2f}; contract pass",
        fix="embedder image digest mismatch — `fieldkit field-edition repair cortex`",
        headline_key="recall_at_5",
    ),
    GateSpec(
        key="lane",
        label="Serving lane",
        metric="LaneTruth smoke: launch → 1 generation → clean teardown",
        threshold="lane up + 1 gen + clean teardown",
        fix="inspect `docker compose logs of-advisor-lane`; re-run `fieldkit field-edition up`",
    ),
    GateSpec(
        key="hermes",
        label="Hermes",
        metric="one MCP-driven fieldkit tool round-trip",
        threshold="tool call returns",
        fix="enable Hermes (~/.hermes/) or omit --hermes to skip (§8)",
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
    launched = m.get("launched", 0.0) >= 1.0
    generated = m.get("generated", 0.0) >= 1.0
    torn_down = m.get("torn_down", 0.0) >= 1.0
    ok = launched and generated and torn_down
    detail = (
        f"launch {'ok' if launched else 'FAIL'}, "
        f"generation {'ok' if generated else 'FAIL'}, "
        f"teardown {'ok' if torn_down else 'FAIL'}"
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

    The ``fieldkit`` gate is fully measured today (import + version + matrix).
    The bench gates (``advisor``/``cortex``/``lane``/``hermes``) need the live
    Field Edition stack + the pinned Q4_K_M model — until that lands (M2) they
    return an honest ``error`` naming the missing piece, never a vanity pass.
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

    def advisor(self, config: FieldEditionConfig) -> GateOutcome:
        return self._stack_pending(
            "advisor",
            "advisor-bench held-out + refusal-floor scoring not yet wired to the live lane",
        )

    def cortex(self, config: FieldEditionConfig) -> GateOutcome:
        # The recall-half is live-measurable TODAY against the running Cortex
        # stack (pgvector + embedder) over the vendored frozen recall set; the
        # grounded-contract generation half (citation integrity + refusal
        # hygiene) still needs the serving lane (M2). Measure recall for real,
        # then report honestly that the gate cannot fully PASS yet — never a
        # vanity pass on recall alone.
        try:
            from fieldkit.field_edition.recall import load_recall_set, score_recall_set
            from fieldkit.memory import MemoryIndex
        except Exception as err:  # noqa: BLE001 — missing optional dep
            return self._stack_pending(
                "cortex", f"recall deps unavailable ({str(err)[:80]})"
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

        try:
            report = score_recall_set(rset.rows, retrieve, k=5)
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

        recall_ok = report.recall_at_5 >= CORTEX_RECALL_FLOOR
        note = (
            f"recall@5 {report.recall_at_5:.3f} over {report.answerable_n} rows "
            f"({'≥' if recall_ok else '<'}{CORTEX_RECALL_FLOOR:.2f}), "
            f"{len(report.misses)} miss(es)"
        )
        return GateOutcome(
            "cortex",
            metrics=report.as_metrics(),
            note=note,
            error=(
                f"recall-half live ✓ ({note}); grounded-contract half "
                "(citation integrity + refusal hygiene) needs the serving lane "
                "(M2 — `fieldkit field-edition up` + the pinned Q4_K_M model)"
            ),
        )

    def lane(self, config: FieldEditionConfig) -> GateOutcome:
        return self._stack_pending(
            "lane",
            "the LaneTruth launch→generate→teardown smoke needs the live serving lane",
        )

    def hermes(self, config: FieldEditionConfig) -> GateOutcome:
        return self._stack_pending(
            "hermes", "the MCP fieldkit tool round-trip needs the live Hermes harness"
        )

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
