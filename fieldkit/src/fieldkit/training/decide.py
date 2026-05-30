# Copyright 2026 Manav Sehgal
# SPDX-License-Identifier: Apache-2.0
"""YAML-lookup decision API for backend / recipe / hyperparam picks.

Phase E (last) of the v0.5 `fieldkit.training` build-out. The
"carry both Unsloth & NeMo in fieldkit v0.5" finding from
`[[project_nemo_pilot_verdict]]` lands as the first seed entry; future
bakeoff articles add their entries via the same contract.

Two layers:

1. **YAML entries** describe a *question* (e.g. ``train_backend``), the
   *context* in which it was answered (e.g. ``base_model_family:
   qwen3-r1-distill``), and one or more *findings* (e.g.
   ``optimize_for: patent_chain_length → pick: nemo``). Each entry has
   a ``lifecycle`` (``active`` | ``superseded`` | ``deprecated``) and a
   ``created`` date so the corpus can be filtered + refreshed.
2. **Query API** — `train_backend(base_model_family=..., optimize_for=...)`
   walks the configured entry directories, filters to active entries
   matching the question + context, finds the matching finding, and
   returns a `DecidePick`. The default search path is the bundled
   `SEED_ENTRIES_DIR` (ships with the wheel) plus the user's
   `USER_ENTRIES_DIR` (`~/.fieldkit/decide-entries/`, read-after-write,
   gitignored) — so users can extend the decision corpus without
   forking.

The **refresh flywheel** is `refresh(freshness_days=180)` which walks
every entry and flags any older than the cutoff. The decision corpus
must not go stale silently; flagged entries should either be re-verified
+ re-stamped or promoted to ``superseded``.

YAML schema::

    slug: 2026-05-22-paired-bakeoff       # required, unique within dir
    lifecycle: active                     # active | superseded | deprecated
    created: 2026-05-22                   # ISO date (YYYY-MM-DD)
    question: train_backend               # the decide.<name>() entry point
    context:                              # required mapping
      base_model_family: qwen3-r1-distill
    findings:                             # required, non-empty
      - optimize_for: patent_chain_length
        pick: nemo
        evidence: "+44% mean chain ..."
    sources: []                           # optional, default []
    supersedes: []                        # optional, default []
    notes: "free-form annotation"         # optional

Bakeoff article H ships the seed entry alongside its prose; every
``articles/*-bakeoff-*`` should follow the contract so the next-session's
``decide(...)`` returns the article's findings programmatically.
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any, Iterable, Mapping, Optional, Sequence


__all__ = [
    "DEFAULT_FRESHNESS_DAYS",
    "DecideEntry",
    "DecideError",
    "DecideFinding",
    "DecidePick",
    "SEED_ENTRIES_DIR",
    "StalenessReport",
    "USER_ENTRIES_DIR",
    "VALID_LIFECYCLES",
    "load_entries",
    "refresh",
    "train_backend",
]


DEFAULT_FRESHNESS_DAYS: int = 180
"""Default age cutoff for `refresh()` — entries older than this are
flagged as stale. Six months matches the typical cadence at which
hardware perf, framework versions, and base-model checkpoints drift
enough to invalidate a paired-bakeoff finding."""


VALID_LIFECYCLES: frozenset[str] = frozenset({"active", "superseded", "deprecated"})
"""Lifecycle values accepted in a `DecideEntry.lifecycle` field.

- ``active`` — currently authoritative; `train_backend()` returns these.
- ``superseded`` — replaced by a newer entry; preserved for audit.
- ``deprecated`` — explicitly retired (e.g. the question itself was
  reframed); preserved for audit but never returned from lookups."""


SEED_ENTRIES_DIR: Path = (Path(__file__).parent / "data" / "decide-entries").resolve()
"""Bundled-in-wheel seed entries. Read-only at install time. The
patent-strategist v3 paired-bakeoff entry is the first seed."""


USER_ENTRIES_DIR: Path = (Path.home() / ".fieldkit" / "decide-entries").resolve()
"""User-extension entry directory. Read-after-write, gitignored — so
project teams can drop their own A/B findings here without forking
fieldkit. Created on first write by the caller; not auto-created at
module import."""


class DecideError(RuntimeError):
    """Raised by `load_entries` / `train_backend` / `refresh` on bad
    inputs or unresolved lookups. Distinct from `ValueError` so callers
    can selectively catch decide-layer failures."""


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DecideFinding:
    """One finding within a `DecideEntry` — the answer for a single
    `(question, context, optimize_for)` cell.

    ``pick`` is the recommended choice (e.g. ``"nemo"`` or ``"unsloth"``
    for ``train_backend``). ``evidence`` is a short prose justification
    so the consumer doesn't have to read the source article to trust
    the answer. Extra keys are accepted on load (forward-compat) and
    surface as ``extra``."""

    optimize_for: str
    pick: str
    evidence: str = ""
    extra: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class DecideEntry:
    """One YAML decision entry. Slug is the on-disk filename (without
    extension) and the unique identity for ``supersedes`` graphs.

    `path` is the resolved on-disk location (None for in-memory entries
    constructed via `from_dict`).
    """

    slug: str
    lifecycle: str
    created: date
    question: str
    context: Mapping[str, Any]
    findings: tuple[DecideFinding, ...]
    sources: tuple[str, ...] = ()
    supersedes: tuple[str, ...] = ()
    notes: str = ""
    path: Optional[Path] = None

    def __post_init__(self) -> None:  # type: ignore[override]
        if self.lifecycle not in VALID_LIFECYCLES:
            raise DecideError(
                f"DecideEntry {self.slug!r} lifecycle={self.lifecycle!r} "
                f"not in {sorted(VALID_LIFECYCLES)}"
            )
        if not self.findings:
            raise DecideError(
                f"DecideEntry {self.slug!r} has no findings — at least one is required"
            )

    def age_days(self, *, today: Optional[date] = None) -> int:
        """Days between ``created`` and ``today`` (defaults to ``date.today()``).
        Negative values clamp to 0 — useful when a YAML entry is dated
        in the near future (e.g. a draft committed ahead of publish)."""
        today_d = today or date.today()
        delta = (today_d - self.created).days
        return max(0, delta)

    def matches_context(self, **constraints: Any) -> bool:
        """True iff every key in ``constraints`` exists in ``self.context``
        and matches by ``==``. Unknown keys in context are ignored;
        unknown keys in constraints (i.e. context doesn't carry them)
        fail-closed."""
        for k, v in constraints.items():
            if self.context.get(k) != v:
                return False
        return True

    @classmethod
    def from_dict(cls, data: Mapping[str, Any], *, path: Optional[Path] = None) -> DecideEntry:
        """Hydrate from a plain dict (e.g. `yaml.safe_load` output).

        Raises `DecideError` on missing required keys or bad shape.
        Unknown top-level keys are tolerated for forward compatibility;
        unknown keys inside a finding survive under ``finding.extra``.
        """
        try:
            slug = str(data["slug"])
            lifecycle = str(data["lifecycle"])
            created_raw = data["created"]
            question = str(data["question"])
            context = data.get("context") or {}
            findings_raw = data["findings"]
        except KeyError as exc:
            raise DecideError(
                f"DecideEntry dict missing required key {exc!s}"
                + (f" (path={path})" if path else "")
            ) from exc
        if not isinstance(context, Mapping):
            raise DecideError(
                f"DecideEntry {slug!r} context must be a mapping (got {type(context).__name__})"
            )
        if not isinstance(findings_raw, Sequence) or isinstance(findings_raw, (str, bytes)):
            raise DecideError(
                f"DecideEntry {slug!r} findings must be a sequence "
                f"(got {type(findings_raw).__name__})"
            )
        created = _parse_iso_date(created_raw, slug=slug)
        findings: list[DecideFinding] = []
        for i, fd in enumerate(findings_raw):
            if not isinstance(fd, Mapping):
                raise DecideError(
                    f"DecideEntry {slug!r} finding[{i}] must be a mapping "
                    f"(got {type(fd).__name__})"
                )
            try:
                opt = str(fd["optimize_for"])
                pick = str(fd["pick"])
            except KeyError as exc:
                raise DecideError(
                    f"DecideEntry {slug!r} finding[{i}] missing required key {exc!s}"
                ) from exc
            evidence = str(fd.get("evidence", ""))
            extra = {k: v for k, v in fd.items() if k not in {"optimize_for", "pick", "evidence"}}
            findings.append(
                DecideFinding(
                    optimize_for=opt, pick=pick, evidence=evidence, extra=extra
                )
            )

        sources = tuple(str(s) for s in (data.get("sources") or ()))
        supersedes = tuple(str(s) for s in (data.get("supersedes") or ()))
        notes = str(data.get("notes", ""))
        return cls(
            slug=slug,
            lifecycle=lifecycle,
            created=created,
            question=question,
            context=dict(context),
            findings=tuple(findings),
            sources=sources,
            supersedes=supersedes,
            notes=notes,
            path=path,
        )

    @classmethod
    def from_yaml(cls, path: str | Path) -> DecideEntry:
        """Read a YAML (or JSON) entry from disk. Uses optional ``pyyaml``
        if available; falls back to ``json.loads`` so test fixtures and
        callers without pyyaml still work for flat-shaped entries."""
        p = Path(path)
        if not p.is_file():
            raise DecideError(f"DecideEntry file not found at {p}")
        text = p.read_text(encoding="utf-8")
        try:
            import yaml  # type: ignore[import-untyped]

            data = yaml.safe_load(text)
        except ImportError:
            try:
                data = json.loads(text)
            except json.JSONDecodeError as exc:
                raise DecideError(
                    f"DecideEntry file {p} requires pyyaml to parse "
                    f"(or write the entry in flat JSON)"
                ) from exc
        if not isinstance(data, Mapping):
            raise DecideError(
                f"DecideEntry file {p} did not parse to a mapping (got {type(data).__name__})"
            )
        return cls.from_dict(data, path=p.resolve())

    def find(self, *, optimize_for: str) -> Optional[DecideFinding]:
        """First finding with the given ``optimize_for`` value, or None."""
        for fd in self.findings:
            if fd.optimize_for == optimize_for:
                return fd
        return None


@dataclass(frozen=True)
class DecidePick:
    """Result of a `train_backend()` (or similar) call.

    ``pick`` is the recommended value (e.g. ``"nemo"``); ``evidence``
    is the matched finding's evidence string; ``entry`` is the
    `DecideEntry` that supplied the answer (so callers can audit
    ``entry.slug`` / ``entry.created`` / ``entry.path``)."""

    pick: str
    evidence: str
    entry: DecideEntry
    optimize_for: str
    context: Mapping[str, Any]

    @property
    def backend(self) -> str:
        """Alias for ``pick``. Kept because the canonical
        `train_backend()` consumer reaches for ``result.backend`` per
        the v0.5 spec example. Other future ``decide.<question>()``
        entry points won't carry this alias."""
        return self.pick

    @property
    def entry_path(self) -> Optional[Path]:
        """Convenience accessor for ``entry.path``."""
        return self.entry.path


@dataclass(frozen=True)
class StalenessReport:
    """One row of `refresh()` output: a `DecideEntry` paired with its
    age in days and a ``stale`` flag. Stale entries should be
    re-verified + re-stamped or promoted to ``superseded``."""

    entry: DecideEntry
    age_days: int
    stale: bool


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------


_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _parse_iso_date(value: Any, *, slug: str) -> date:
    """Coerce a YAML ``created`` value into a ``date``. Accepts native
    ``date`` (already parsed by pyyaml), native ``datetime``, and ISO
    ``YYYY-MM-DD`` strings."""
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str) and _DATE_RE.match(value):
        try:
            return date.fromisoformat(value)
        except ValueError as exc:
            raise DecideError(
                f"DecideEntry {slug!r} created={value!r} is not a valid ISO date"
            ) from exc
    raise DecideError(
        f"DecideEntry {slug!r} created={value!r} must be an ISO date string "
        f"(YYYY-MM-DD) or a date object (got {type(value).__name__})"
    )


def _resolve_dirs(dirs: Optional[Iterable[str | Path]]) -> tuple[Path, ...]:
    """Default search path = seed dir + user dir (if it exists). Caller
    can override with an explicit ``dirs=`` to scope a query."""
    if dirs is None:
        out: list[Path] = []
        if SEED_ENTRIES_DIR.is_dir():
            out.append(SEED_ENTRIES_DIR)
        if USER_ENTRIES_DIR.is_dir():
            out.append(USER_ENTRIES_DIR)
        return tuple(out)
    return tuple(Path(d) for d in dirs)


def load_entries(
    *,
    dirs: Optional[Iterable[str | Path]] = None,
    lifecycle: Optional[str | Iterable[str]] = "active",
    question: Optional[str] = None,
) -> list[DecideEntry]:
    """Read every YAML / JSON entry under each directory and return the
    parsed list.

    Parameters:
        dirs: Directories to scan. Defaults to ``[SEED_ENTRIES_DIR,
            USER_ENTRIES_DIR]`` (only those that exist). Pass an
            explicit list to scope (e.g. tests pass a tmp_path).
        lifecycle: Filter — ``"active"`` (default), ``"superseded"``,
            ``"deprecated"``, a sequence of these, or ``None`` to
            return entries of any lifecycle. Unknown values raise
            ``DecideError``.
        question: Optional filter on ``entry.question``. None returns
            entries with any question name.

    Returns the matched entries sorted by ``created`` descending
    (most-recent first) so callers iterating linearly hit the freshest
    finding first.
    """
    if lifecycle is None:
        wanted_lc: Optional[frozenset[str]] = None
    elif isinstance(lifecycle, str):
        if lifecycle not in VALID_LIFECYCLES:
            raise DecideError(
                f"lifecycle={lifecycle!r} not in {sorted(VALID_LIFECYCLES)}"
            )
        wanted_lc = frozenset({lifecycle})
    else:
        wanted_lc = frozenset(lifecycle)
        bad = wanted_lc - VALID_LIFECYCLES
        if bad:
            raise DecideError(
                f"lifecycle values {sorted(bad)} not in {sorted(VALID_LIFECYCLES)}"
            )

    out: list[DecideEntry] = []
    for d in _resolve_dirs(dirs):
        if not d.is_dir():
            continue
        for p in sorted(d.iterdir()):
            if not p.is_file():
                continue
            if p.suffix.lower() not in {".yaml", ".yml", ".json"}:
                continue
            entry = DecideEntry.from_yaml(p)
            if wanted_lc is not None and entry.lifecycle not in wanted_lc:
                continue
            if question is not None and entry.question != question:
                continue
            out.append(entry)
    out.sort(key=lambda e: e.created, reverse=True)
    return out


def train_backend(
    *,
    base_model_family: str,
    optimize_for: str,
    dirs: Optional[Iterable[str | Path]] = None,
) -> DecidePick:
    """Look up the recommended training backend for the given
    ``(base_model_family, optimize_for)`` cell.

    The active corpus is scanned for entries with
    ``question="train_backend"`` whose ``context.base_model_family``
    equals the argument. Entries are sorted by ``created`` descending,
    and the first one with a matching ``optimize_for`` finding wins.

    Raises `DecideError` with a clear message if no active entry covers
    the cell — the message lists every active entry's ``slug`` +
    ``created`` so the caller can either widen their query, add a new
    user-dir entry, or `refresh()` a stale one back to active.
    """
    candidates = load_entries(dirs=dirs, lifecycle="active", question="train_backend")
    matched: list[DecideEntry] = [
        e for e in candidates if e.matches_context(base_model_family=base_model_family)
    ]
    if not matched:
        seen = ", ".join(
            f"{e.slug}@{e.created.isoformat()}"
            for e in candidates
        ) or "<none>"
        raise DecideError(
            f"no active train_backend entry for "
            f"base_model_family={base_model_family!r} "
            f"(seen: {seen})"
        )
    for entry in matched:
        fd = entry.find(optimize_for=optimize_for)
        if fd is None:
            continue
        return DecidePick(
            pick=fd.pick,
            evidence=fd.evidence,
            entry=entry,
            optimize_for=optimize_for,
            context=dict(entry.context),
        )

    avail = sorted({
        fd.optimize_for
        for e in matched
        for fd in e.findings
    })
    raise DecideError(
        f"no train_backend entry for "
        f"base_model_family={base_model_family!r} + "
        f"optimize_for={optimize_for!r} "
        f"(available optimize_for in matched entries: {avail})"
    )


def refresh(
    *,
    dirs: Optional[Iterable[str | Path]] = None,
    freshness_days: int = DEFAULT_FRESHNESS_DAYS,
    today: Optional[date] = None,
    include_lifecycle: Optional[str | Iterable[str]] = None,
) -> list[StalenessReport]:
    """Walk every entry and flag any older than ``freshness_days``.

    Returns a list of `StalenessReport`, sorted by ``age_days``
    descending (oldest first) so callers can act on the stalest entries
    first. By default scans entries of *every* lifecycle (i.e.
    ``include_lifecycle=None``) — the refresh flywheel cares about the
    full corpus, not just active entries. Pass an explicit
    ``include_lifecycle="active"`` to scope.

    ``today`` defaults to ``date.today()``; tests override.
    """
    if freshness_days < 0:
        raise DecideError(f"freshness_days must be >= 0 (got {freshness_days})")
    entries = load_entries(dirs=dirs, lifecycle=include_lifecycle)
    today_d = today or date.today()
    reports: list[StalenessReport] = []
    for e in entries:
        age = e.age_days(today=today_d)
        reports.append(
            StalenessReport(entry=e, age_days=age, stale=age > freshness_days)
        )
    reports.sort(key=lambda r: r.age_days, reverse=True)
    return reports
