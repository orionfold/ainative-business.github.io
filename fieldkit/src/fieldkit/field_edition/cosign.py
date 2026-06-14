# Copyright 2026 Manav Sehgal
# SPDX-License-Identifier: Apache-2.0
"""Cosign verification of the §9 proven-matrix images.

The §9 update channel (:mod:`.update`) must confirm a fetched proven matrix is
authentic before it applies it: every Orionfold-built image in the matrix has to
carry a valid cosign signature by the **pinned proven-matrix key** (otherwise an
attacker who can publish to the registry could ship a malicious update). This
module owns that check.

**Key-based, not keyless.** Sigstore keyless needs Fulcio, which is
network-blocked on the Spark box, so the proven-matrix images are signed with a
long-lived key (the operator runbook + signing scripts live in
``deploy/field-edition/cosign/``). This module **pins the matching public key**
(:data:`PROVEN_MATRIX_COSIGN_PUBKEY`) — the same pin-a-committed-public-key
pattern as the Ed25519 :data:`fieldkit.field_edition.license.TRUSTED_KEYS`
(different algorithm — cosign's default is ECDSA P-256 — same idea). The
committed copy at ``deploy/field-edition/cosign/proven-matrix.pub`` is the
operator-facing twin; a test asserts the two never drift.

Design (the deterministic-scripts invariant): the ``cosign`` subprocess is the
only external boundary and is **injected** (the ``runner`` seam), so the
filter + verification control flow is unit-testable without the cosign binary,
a registry, or the network.
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from typing import Callable, Sequence

from fieldkit.field_edition.proven_matrix import ProvenMatrix

__all__ = [
    "PROVEN_MATRIX_COSIGN_PUBKEY",
    "ORIONFOLD_GHCR_PREFIX",
    "CosignVerifyError",
    "orionfold_image_refs",
    "verify_image",
    "verify_matrix",
]

#: GHCR namespace of the Orionfold-built images (the only ones we sign + verify;
#: upstream pgvector and the NVIDIA NIM embedder are not ours to sign).
ORIONFOLD_GHCR_PREFIX = "ghcr.io/orionfold/"

#: The pinned **public** key for the proven-matrix signatures. Must byte-match
#: ``deploy/field-edition/cosign/proven-matrix.pub`` (a test enforces it). The
#: private half + its ``COSIGN_PASSWORD`` live only in the orionfold secret
#: store and never enter the repo. Rotating the signing key = swap this constant
#: (+ the committed twin) and re-sign — same discipline as ``TRUSTED_KEYS``.
PROVEN_MATRIX_COSIGN_PUBKEY = """\
-----BEGIN PUBLIC KEY-----
MFkwEwYHKoZIzj0CAQYIKoZIzj0DAQcDQgAEq8h+DnHUMeDUC1ijlCtMPWCf9ixP
wZKXPUWOzRkTstz7b0t9JdCNpmpcINd01hhVuMKJQnsTrD9HoKuTdOk5JA==
-----END PUBLIC KEY-----
"""

#: A runner maps a cosign argv to ``(returncode, combined_output)``. The default
#: shells out; tests inject a fake.
Runner = Callable[[Sequence[str]], "tuple[int, str]"]


class CosignVerifyError(RuntimeError):
    """Verification failed (bad/absent signature, or cosign unavailable).

    Carries an operator-facing ``fix`` the §9 channel surfaces in its receipt."""

    def __init__(self, message: str, *, fix: str = "") -> None:
        super().__init__(message)
        self.fix = fix


def _default_runner(cmd: Sequence[str]) -> "tuple[int, str]":
    proc = subprocess.run(list(cmd), capture_output=True, text=True, timeout=120)
    return proc.returncode, (proc.stdout + proc.stderr)


def orionfold_image_refs(matrix: ProvenMatrix) -> list[str]:
    """The digest-pinned Orionfold image references in ``matrix`` — the set we
    verify. Skips upstream/NVIDIA images and any non-``@sha256`` reference."""
    return [
        ref
        for ref in matrix.images.values()
        if isinstance(ref, str)
        and ref.startswith(ORIONFOLD_GHCR_PREFIX)
        and "@sha256:" in ref
    ]


def verify_image(
    ref: str,
    *,
    pubkey_pem: str = PROVEN_MATRIX_COSIGN_PUBKEY,
    ignore_tlog: bool = False,
    runner: Runner | None = None,
) -> None:
    """Verify one image ``ref`` against the pinned key. Raises
    :class:`CosignVerifyError` on a bad/absent signature or a missing cosign.

    ``ignore_tlog`` mirrors the signing side's ``OF_NO_TLOG`` (for a
    self-contained verify when the Rekor transparency log is unreachable); the
    default checks the tlog, matching how the images were signed."""
    run = runner or _default_runner
    if runner is None and shutil.which("cosign") is None:
        raise CosignVerifyError(
            "cosign not found on PATH",
            fix=(
                "install cosign to verify proven-matrix updates "
                "(https://docs.sigstore.dev/cosign/system_config/installation/)"
            ),
        )
    with tempfile.NamedTemporaryFile("w", suffix=".pub") as keyfile:
        keyfile.write(pubkey_pem)
        keyfile.flush()
        cmd = ["cosign", "verify", "--key", keyfile.name]
        if ignore_tlog:
            cmd.append("--insecure-ignore-tlog=true")
        cmd.append(ref)
        try:
            code, out = run(cmd)
        except FileNotFoundError as err:  # cosign vanished between the which() and exec
            raise CosignVerifyError(
                "cosign not found on PATH",
                fix="install cosign to verify proven-matrix updates",
            ) from err
    if code != 0:
        raise CosignVerifyError(
            f"cosign verify failed for {ref}",
            fix=(
                out.strip()[:300]
                or "image is not signed by the pinned proven-matrix key — reject the update (§9)"
            ),
        )


def verify_matrix(
    matrix: ProvenMatrix,
    *,
    pubkey_pem: str = PROVEN_MATRIX_COSIGN_PUBKEY,
    ignore_tlog: bool = False,
    runner: Runner | None = None,
) -> list[str]:
    """Verify every Orionfold image in ``matrix`` against the pinned key.

    Returns the list of verified references. Raises :class:`CosignVerifyError` if
    the matrix pins no Orionfold image (nothing to anchor trust on) or if any one
    fails verification."""
    refs = orionfold_image_refs(matrix)
    if not refs:
        raise CosignVerifyError(
            "proven matrix pins no Orionfold @sha256 image to verify",
            fix="a signed proven matrix must pin at least one ghcr.io/orionfold image by digest (§9)",
        )
    for ref in refs:
        verify_image(ref, pubkey_pem=pubkey_pem, ignore_tlog=ignore_tlog, runner=runner)
    return refs
