# Copyright 2026 Manav Sehgal
# SPDX-License-Identifier: Apache-2.0
"""Lineage primitive — append-only trial log + deterministic prompt rendering.

The portable part of cxcscmu's *Auto-Research-Recipes* harness: a 17-column
TSV per trial, a status enum that doubles as failure semantics, and a
deterministic Markdown rendering of "what's been tried" that the next
specialist reads at session entry.

The released `pg_ablation_lineage_on` / `pg_ablation_lineage_off` runs are
the load-bearing evidence: same agent, same prompt template, same trial
budget — only the rendered lineage block differs, and the run with lineage
produces 5.3x more keeps and 3.2x less wall-time waste. The agent without
lineage rediscovers dead ends. The agent with lineage doesn't.

See the [auto-research-loop-on-spark article] for the schema walkthrough
and the cxcscmu ablation evidence; see `articles/auto-research-loop-on-spark/
evidence/repo-snapshot/release_artifacts/example_lineage_pg_lineage_on_arch.txt`
for the canonical rendered-prompt format this module emits.

[auto-research-loop-on-spark article]: https://ainative.business/field-notes/auto-research-loop-on-spark/

Module shape (~200 LOC public surface):

- `FailureLabel` — 10-class string enum with an `is_informational` predicate.
- `Trial` — frozen dataclass for one TSV row. 17 fields in canonical order.
- `RecipeEdit` — keep-trial workdir snapshot + parent reference + lazy diff.
- `LineageSnapshot` — record of what the agent saw at session entry, including
  the full rendered Markdown prompt block.
- `LineageStore` — TSV append (fcntl-locked) + read-side accessors
  (`latest`, `best`, `chain_to`, `render_prompt`).

No torch / numpy / external runtime dependencies — pure stdlib.
"""

from __future__ import annotations

import csv
import difflib
import fcntl
from dataclasses import asdict, dataclass, fields
from enum import Enum
from pathlib import Path
from typing import Iterable, Optional

__all__ = [
    "FailureLabel",
    "LineageSnapshot",
    "LineageStore",
    "RecipeEdit",
    "Trial",
]


class FailureLabel(str, Enum):
    """Status of a trial. String-valued so TSV round-trip is identity.

    The five core classes (`keep`, `discard`, `crash`, `eval_budget_overrun`,
    `size_blocked`) cover any task where trials can run to completion, fail
    mid-run, exceed an eval budget, or be killed by structural constraints.
    The tail classes are task-specific extensions:
    `train_budget_overrun` for separately-budgeted train phases,
    `preflight_crash` / `harness_abort` for infrastructure-level failures
    that don't reflect on the hypothesis, and `disqualified` for vision
    tasks (CIFAR) where a trial completes but fails a structural gate.
    `baseline` is the seed row every run starts from.
    """

    KEEP = "keep"
    DISCARD = "discard"
    CRASH = "crash"
    EVAL_BUDGET_OVERRUN = "eval_budget_overrun"
    TRAIN_BUDGET_OVERRUN = "train_budget_overrun"
    SIZE_BLOCKED = "size_blocked"
    PREFLIGHT_CRASH = "preflight_crash"
    HARNESS_ABORT = "harness_abort"
    DISQUALIFIED = "disqualified"
    BASELINE = "baseline"

    @property
    def is_informational(self) -> bool:
        """True if this status carries usable signal for the next agent.

        `harness_abort` is bookkeeping — a wall-clock or process-level kill
        that says nothing about the hypothesis. Everything else (including
        crashes and budget overruns) tells the next specialist something
        about what doesn't work, and is therefore informational.
        """
        return self is not FailureLabel.HARNESS_ABORT


@dataclass(frozen=True, slots=True)
class Trial:
    """One row of results.tsv. Field order matches the canonical TSV header.

    `core_metric` is the task-agnostic primary metric — for language-model
    runs this mirrors `val_bpb`; for CIFAR it would be top-1 error; for any
    other task whatever the leaderboard sorts on. Lower is better by default
    (configurable on `LineageStore`).
    """

    exp_id: str
    timestamp: str
    specialist: str
    parent_exp: str
    baseline_exp: str
    domain: str
    hypothesis: str
    expected_delta: str
    status: FailureLabel
    core_metric: Optional[float]
    val_bpb: Optional[float]
    delta_vs_best: Optional[float]
    train_s: Optional[float]
    total_s: Optional[float]
    job_name: str
    snapshot_path: str
    notes: str

    @classmethod
    def header(cls) -> tuple[str, ...]:
        """Canonical TSV header — field names in declaration order."""
        return tuple(f.name for f in fields(cls))

    def to_row(self) -> list[str]:
        """Serialize to a list of TSV cells. Empty string for `None`."""
        out: list[str] = []
        for fld in fields(Trial):
            val = getattr(self, fld.name)
            if val is None:
                out.append("")
            elif isinstance(val, FailureLabel):
                out.append(val.value)
            else:
                out.append(str(val))
        return out

    @classmethod
    def from_row(cls, row: dict[str, str]) -> "Trial":
        """Parse a row dict (csv.DictReader style) into a Trial."""

        def _f(name: str) -> Optional[float]:
            raw = row.get(name, "")
            if raw == "" or raw is None:
                return None
            return float(raw)

        return cls(
            exp_id=row.get("exp_id", ""),
            timestamp=row.get("timestamp", ""),
            specialist=row.get("specialist", ""),
            parent_exp=row.get("parent_exp", ""),
            baseline_exp=row.get("baseline_exp", ""),
            domain=row.get("domain", ""),
            hypothesis=row.get("hypothesis", ""),
            expected_delta=row.get("expected_delta", ""),
            status=FailureLabel(row.get("status", "discard")),
            core_metric=_f("core_metric"),
            val_bpb=_f("val_bpb"),
            delta_vs_best=_f("delta_vs_best"),
            train_s=_f("train_s"),
            total_s=_f("total_s"),
            job_name=row.get("job_name", ""),
            snapshot_path=row.get("snapshot_path", ""),
            notes=row.get("notes", ""),
        )


@dataclass(frozen=True, slots=True)
class RecipeEdit:
    """A keep trial's frozen workdir + the diff against its parent.

    `snapshot_path` is materialized (a directory of the keep's working files);
    `parent_snapshot_path` is the path to the trial's parent's snapshot, or
    `None` for the baseline. The diff is computed lazily on first call —
    one walk per file pair, unified-diff format.
    """

    trial: Trial
    snapshot_path: Path
    parent_snapshot_path: Optional[Path]

    def diff(self) -> str:
        """Unified diff of every text file in `snapshot_path` vs parent.

        Returns an empty string if `parent_snapshot_path` is None (baseline).
        Binary files (files that raise `UnicodeDecodeError` on read) are
        elided with a `Binary files ... differ` marker, mirroring `git diff`.
        """
        if self.parent_snapshot_path is None:
            return ""
        parts: list[str] = []
        parent_root = self.parent_snapshot_path
        this_root = self.snapshot_path
        for path in sorted(_walk_files(this_root)):
            rel = path.relative_to(this_root)
            parent_file = parent_root / rel
            try:
                this_text = path.read_text().splitlines(keepends=True)
            except (UnicodeDecodeError, OSError):
                parts.append(f"Binary files a/{rel} and b/{rel} differ\n")
                continue
            parent_text: list[str] = []
            if parent_file.exists():
                try:
                    parent_text = parent_file.read_text().splitlines(keepends=True)
                except UnicodeDecodeError:
                    parts.append(f"Binary files a/{rel} and b/{rel} differ\n")
                    continue
            diff = list(
                difflib.unified_diff(
                    parent_text,
                    this_text,
                    fromfile=f"a/{rel}",
                    tofile=f"b/{rel}",
                )
            )
            if diff:
                parts.extend(diff)
        return "".join(parts)


def _walk_files(root: Path) -> Iterable[Path]:
    """Recursively yield regular files under `root`. Stable order via sort upstream."""
    if not root.exists():
        return
    for path in root.rglob("*"):
        if path.is_file():
            yield path


@dataclass(frozen=True, slots=True)
class LineageSnapshot:
    """Record of what the agent saw at session start.

    `rendered_prompt` is the full Markdown block injected into the session;
    the other fields are the underlying structured data that fed the
    rendering, exposed so callers can index into it without re-parsing the
    string.
    """

    rendered_prompt: str
    current_best: Trial
    chain_to_best: tuple[Trial, ...]
    top_k_leaderboard: tuple[Trial, ...]
    recent_n_activity: tuple[Trial, ...]
    last_m_with_full_hypothesis: tuple[Trial, ...]


class LineageStore:
    """Append-only TSV writer + read-side accessors.

    Layout under `root`:
        results.tsv     — one row per trial, 17 columns, header on first line.
        snapshots/      — optional directory of per-keep workdir snapshots.

    All writes go through `append()` which takes an exclusive `fcntl.flock`
    on the TSV file, so multiple specialists can write concurrently without
    interleaving. Reads scan the whole file; a 1,704-trial release scans in
    a few milliseconds on warm I/O.
    """

    RESULTS_FILENAME = "results.tsv"

    def __init__(self, root: Path, *, lower_is_better: bool = True) -> None:
        self.root = Path(root)
        self.lower_is_better = lower_is_better
        self.results_path = self.root / self.RESULTS_FILENAME

    def append(self, trial: Trial) -> None:
        """Append `trial` to results.tsv. Creates the file with a header if absent.

        Holds an exclusive `fcntl.flock` on the file across the header-write
        + row-write sequence; safe for concurrent writers.
        """
        self.root.mkdir(parents=True, exist_ok=True)
        write_header = not self.results_path.exists() or self.results_path.stat().st_size == 0
        with self.results_path.open("a", newline="") as fh:
            fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
            try:
                writer = csv.writer(fh, delimiter="\t", lineterminator="\n")
                if write_header:
                    writer.writerow(Trial.header())
                writer.writerow(trial.to_row())
                fh.flush()
            finally:
                fcntl.flock(fh.fileno(), fcntl.LOCK_UN)

    def all_trials(self) -> list[Trial]:
        """Read every row of results.tsv as a list of Trials (insertion order)."""
        if not self.results_path.exists():
            return []
        with self.results_path.open("r", newline="") as fh:
            reader = csv.DictReader(fh, delimiter="\t")
            return [Trial.from_row(row) for row in reader]

    def latest(self, n: int = 30) -> tuple[Trial, ...]:
        """Return the most recent `n` trials (by insertion order)."""
        trials = self.all_trials()
        return tuple(trials[-n:]) if n > 0 else ()

    def best(self) -> Optional[Trial]:
        """Best trial by `core_metric` among informational rows with a metric.

        Honors `lower_is_better`. Falls back to the baseline if no keeps yet
        have a metric. Returns `None` if the store is empty.
        """
        scored: list[Trial] = [
            t
            for t in self.all_trials()
            if t.core_metric is not None and t.status.is_informational
        ]
        if not scored:
            trials = self.all_trials()
            return trials[0] if trials else None
        key = (lambda t: t.core_metric) if self.lower_is_better else (lambda t: -t.core_metric)  # type: ignore[arg-type,return-value]
        return min(scored, key=key)  # type: ignore[arg-type]

    def chain_to(self, exp_id: str) -> tuple[Trial, ...]:
        """Walk parent pointers from `exp_id` back to the baseline.

        Returned tuple is root-first (baseline at index 0, target at -1).
        Raises `KeyError` if `exp_id` isn't in the store.
        """
        by_id = {t.exp_id: t for t in self.all_trials()}
        if exp_id not in by_id:
            raise KeyError(f"exp_id={exp_id!r} not in {self.results_path}")
        chain: list[Trial] = []
        cur: Optional[str] = exp_id
        seen: set[str] = set()
        while cur and cur not in seen:
            seen.add(cur)
            t = by_id.get(cur)
            if t is None:
                break
            chain.append(t)
            cur = t.parent_exp or None
        chain.reverse()
        return tuple(chain)

    def render_prompt(
        self,
        for_specialist: str,
        *,
        top_k: int = 20,
        recent_n: int = 30,
        last_m_full: int = 10,
        session_timestamp: str = "",
    ) -> LineageSnapshot:
        """Render the Markdown lineage block for a specialist's session start.

        Deterministic function of (TSV state, parameters). The output mirrors
        the cxcscmu `release_artifacts/example_lineage_*.txt` format: header
        line + LEADERBOARD.md section (current best + top-K kept table) +
        KNOWLEDGE.md section (current-best lineage as nested tree + recent
        activity table + last-M detailed entries).
        """
        trials = self.all_trials()
        if not trials:
            return LineageSnapshot(
                rendered_prompt="# Session start — empty lineage\n",
                current_best=_empty_trial(),
                chain_to_best=(),
                top_k_leaderboard=(),
                recent_n_activity=(),
                last_m_with_full_hypothesis=(),
            )

        best = self.best()
        assert best is not None  # trials non-empty => best non-None
        chain = self.chain_to(best.exp_id)

        keeps = [t for t in trials if t.status is FailureLabel.KEEP]
        keeps.sort(
            key=(lambda t: t.core_metric if t.core_metric is not None else float("inf")),
            reverse=not self.lower_is_better,
        )
        top_k_list = tuple(keeps[:top_k])

        recent_n_list = tuple(trials[-recent_n:])
        last_m_list = tuple(trials[-last_m_full:])

        rendered = _render_markdown(
            for_specialist=for_specialist,
            session_timestamp=session_timestamp,
            best=best,
            chain=chain,
            top_k=top_k_list,
            recent_n=recent_n_list,
            last_m=last_m_list,
        )
        return LineageSnapshot(
            rendered_prompt=rendered,
            current_best=best,
            chain_to_best=chain,
            top_k_leaderboard=top_k_list,
            recent_n_activity=recent_n_list,
            last_m_with_full_hypothesis=last_m_list,
        )


def _empty_trial() -> Trial:
    return Trial(
        exp_id="",
        timestamp="",
        specialist="",
        parent_exp="",
        baseline_exp="",
        domain="",
        hypothesis="",
        expected_delta="",
        status=FailureLabel.BASELINE,
        core_metric=None,
        val_bpb=None,
        delta_vs_best=None,
        train_s=None,
        total_s=None,
        job_name="",
        snapshot_path="",
        notes="",
    )


def _fmt_metric(v: Optional[float]) -> str:
    return f"{v:.6f}" if v is not None else "—"


def _fmt_delta(v: Optional[float]) -> str:
    return f"{v:+.6f}" if v is not None else "—"


def _truncate(s: str, n: int) -> str:
    if len(s) <= n:
        return s
    return s[: max(0, n - 1)] + "…"


def _render_markdown(
    *,
    for_specialist: str,
    session_timestamp: str,
    best: Trial,
    chain: tuple[Trial, ...],
    top_k: tuple[Trial, ...],
    recent_n: tuple[Trial, ...],
    last_m: tuple[Trial, ...],
) -> str:
    lines: list[str] = []
    ts = session_timestamp or "—"
    lines.append(f"# Session start — {ts}")
    lines.append(
        f"You are specialist **{for_specialist}**. "
        f"Current best: **exp_{best.exp_id}** "
        f"(core_metric={_fmt_metric(best.core_metric)})."
    )
    lines.append("")

    lines.append("## LEADERBOARD.md")
    lines.append("")
    lines.append("## Current Best")
    lines.append(f"- **exp_id**: {best.exp_id}")
    lines.append(f"- **core_metric**: {_fmt_metric(best.core_metric)}")
    lines.append(f"- **specialist**: {best.specialist}")
    lines.append(f"- **hypothesis**: {_truncate(best.hypothesis, 110)}")
    if best.snapshot_path:
        lines.append(f"- **snapshot**: `{best.snapshot_path}`")
    lines.append("")

    lines.append(f"## Top {len(top_k)} Kept Trials")
    lines.append("")
    if top_k:
        lines.append("| exp | core_metric | Δ | specialist | hypothesis |")
        lines.append("|-----|-------------|---|------------|------------|")
        for t in top_k:
            lines.append(
                f"| {t.exp_id} | {_fmt_metric(t.core_metric)} "
                f"| {_fmt_delta(t.delta_vs_best)} | {t.specialist} "
                f"| {_truncate(t.hypothesis, 100)} |"
            )
    else:
        lines.append("*(no keeps yet)*")
    lines.append("")

    lines.append("## KNOWLEDGE.md")
    lines.append("")
    lines.append("**Current-best lineage** (root → best):")
    lines.append("```")
    for i, t in enumerate(chain):
        prefix = "" if i == 0 else " └─ "
        lines.append(
            f"{prefix}exp_{t.exp_id} "
            f"[{t.specialist or 'baseline'}, {t.status.value}, "
            f"metric={_fmt_metric(t.core_metric)}, Δ={_fmt_delta(t.delta_vs_best)}] "
            f"{_truncate(t.hypothesis, 100)}"
        )
    if chain:
        lines[-1] = lines[-1] + " ← BEST"
    lines.append("```")
    lines.append("")

    lines.append(f"## Recent Activity (last {len(recent_n)})")
    lines.append("")
    if recent_n:
        lines.append("| exp | specialist | status | core_metric | hypothesis |")
        lines.append("|-----|------------|--------|-------------|------------|")
        for t in reversed(recent_n):
            lines.append(
                f"| {t.exp_id} | {t.specialist} | {t.status.value} "
                f"| {_fmt_metric(t.core_metric)} | {_truncate(t.hypothesis, 80)} |"
            )
    lines.append("")

    if last_m:
        lines.append(f"## Recent Activity (most recent {len(last_m)} — full hypothesis)")
        for t in reversed(last_m):
            lines.append(
                f"- exp_{t.exp_id} [{t.specialist}, {t.status.value}, "
                f"metric={_fmt_metric(t.core_metric)}, Δ={_fmt_delta(t.delta_vs_best)}] "
                f"{t.hypothesis}"
            )
            if t.notes:
                lines.append(f"  └─ {_truncate(t.notes, 200)}")
        lines.append("")

    return "\n".join(lines) + "\n"


def _asdict_compat(t: Trial) -> dict[str, object]:
    """Helper for downstream consumers: dict view of a Trial."""
    d = asdict(t)
    d["status"] = t.status.value
    return d
