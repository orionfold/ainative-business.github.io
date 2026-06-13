# Copyright 2026 Manav Sehgal
# SPDX-License-Identifier: Apache-2.0
"""The §9 "proven matrix" — the pinned, eval-gated, rollback-safe release unit.

Implements the distribution + retention half of §9 of
``_SPECS/arena-field-edition-v1.md``. A **proven matrix** is one release: a
digest-pinned Compose image set + the pinned PyPI ``fieldkit`` version + the
pinned GGUF HF revisions, cosign-signed. The update channel (:mod:`.update`)
fetches a new matrix, verifies it, applies it, re-runs the §8 gate, and **rolls
back to the prior matrix on failure** — which is why the prior matrix must be
*retained on disk*. This module owns that retained state + the pure manifest.

Layout under ``~/.orionfold/matrix/``::

    current.json    the matrix the box is running now
    previous.json   the matrix to roll back to (rotated in when current is replaced)

Design (the deterministic-scripts invariant): the manifest is a pure dataclass
with JSON (de)serialization and a content :meth:`ProvenMatrix.fingerprint` (so
"already current" / "unchanged" is decided without comparing volatile timestamps);
the retention helpers (:func:`save_current` / :func:`rollback`) are the only I/O
and are exercised with a ``tmp_path`` home in tests — no network, no registry.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from fieldkit.field_edition.compose import FieldEditionConfig, default_config

__all__ = [
    "ProvenMatrix",
    "matrix_dir",
    "from_config",
    "load_current",
    "load_previous",
    "save_current",
    "rollback",
]


@dataclass(frozen=True)
class ProvenMatrix:
    """One §9 release: the pinned, signed version matrix.

    ``images`` maps a service key to its full pinned reference
    (``repo@sha256:…``); ``gguf_revs`` maps a model slug to its pinned HF
    revision. ``signed`` records whether the matrix carried a verified cosign
    signature when it was written (false for a locally-derived matrix — there is
    no published, signed channel yet; that lands with GHCR + cosign at M3)."""

    matrix_version: str
    fieldkit_version: str
    images: dict[str, str] = field(default_factory=dict)
    gguf_revs: dict[str, str] = field(default_factory=dict)
    signed: bool = False
    created: str = ""

    def fingerprint(self) -> tuple:
        """Content identity (excludes volatile ``created``/``signed``).

        Two matrices with the same pins are the same release even if fetched at
        different times — this is what "already current" compares."""
        return (
            self.matrix_version,
            self.fieldkit_version,
            tuple(sorted(self.images.items())),
            tuple(sorted(self.gguf_revs.items())),
        )

    def to_dict(self) -> dict:
        return {
            "version": 1,
            "kind": "field-edition-proven-matrix",
            "matrix_version": self.matrix_version,
            "fieldkit_version": self.fieldkit_version,
            "images": dict(self.images),
            "gguf_revs": dict(self.gguf_revs),
            "signed": self.signed,
            "created": self.created,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ProvenMatrix":
        return cls(
            matrix_version=str(data.get("matrix_version", "")),
            fieldkit_version=str(data.get("fieldkit_version", "")),
            images=dict(data.get("images", {})),
            gguf_revs=dict(data.get("gguf_revs", {})),
            signed=bool(data.get("signed", False)),
            created=str(data.get("created", "")),
        )


def from_config(config: FieldEditionConfig | None = None, *, created: str = "") -> ProvenMatrix:
    """Derive the matrix the box is *configured* to run from the live config.

    This is the locally-known matrix (the pins :mod:`.compose` carries today) —
    ``signed=False`` because it was not fetched from a signed channel. It is what
    ``current.json`` is seeded with on first ``up``, and the baseline a fetched
    update is compared against."""
    cfg = config or default_config()
    from fieldkit import __version__ as fk_version

    images = {
        "cortex-db": cfg.postgres.image.reference(),
        "embedder": cfg.embedder.image.reference(),
        "advisor-lane": cfg.lane.image.reference(),
    }
    gguf_revs = {"advisor-gguf": cfg.lane.gguf_name}
    return ProvenMatrix(
        matrix_version="local",
        fieldkit_version=fk_version,
        images=images,
        gguf_revs=gguf_revs,
        signed=False,
        created=created,
    )


# --- Retention (the only I/O) ------------------------------------------------


def matrix_dir(config: FieldEditionConfig | None = None) -> Path:
    cfg = config or default_config()
    return cfg.home / "matrix"


def _read(path: Path) -> ProvenMatrix | None:
    try:
        return ProvenMatrix.from_dict(json.loads(path.read_text(encoding="utf-8")))
    except (OSError, ValueError):
        return None


def load_current(config: FieldEditionConfig | None = None) -> ProvenMatrix | None:
    return _read(matrix_dir(config) / "current.json")


def load_previous(config: FieldEditionConfig | None = None) -> ProvenMatrix | None:
    return _read(matrix_dir(config) / "previous.json")


def _write(path: Path, matrix: ProvenMatrix) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(matrix.to_dict(), indent=2) + "\n", encoding="utf-8")


def save_current(matrix: ProvenMatrix, config: FieldEditionConfig | None = None) -> Path:
    """Make ``matrix`` the current one, rotating the old current → previous.

    The rotation is what makes auto-rollback possible (§9): after an update the
    box can always restore the matrix it was running before. Returns the
    ``current.json`` path."""
    d = matrix_dir(config)
    current_path = d / "current.json"
    existing = _read(current_path)
    if existing is not None and existing.fingerprint() != matrix.fingerprint():
        _write(d / "previous.json", existing)
    _write(current_path, matrix)
    return current_path


def rollback(config: FieldEditionConfig | None = None) -> ProvenMatrix | None:
    """Restore ``previous.json`` as the current matrix; return it (``None`` if
    there is nothing to roll back to). The §9 manual escape hatch + the target of
    the update channel's auto-rollback."""
    prev = load_previous(config)
    if prev is None:
        return None
    _write(matrix_dir(config) / "current.json", prev)
    return prev
