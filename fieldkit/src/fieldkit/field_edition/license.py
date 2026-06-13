# Copyright 2026 Manav Sehgal
# SPDX-License-Identifier: Apache-2.0
"""The §AC-7 v1 license file — schema, canonical signing bytes, Ed25519 verify.

The Arena Field Edition license is an **offline-verifiable** entitlement file the
bootstrap drops at ``~/.orionfold/license`` (AC-7: no continuous connectivity, no
license-server round-trip on every boot — the privacy stance is the brand). It is
a JSON document: a ``payload`` of claims + a detached **Ed25519** ``signature``
over the payload's canonical bytes. The installer verifies the signature locally
against a **public key embedded in this module** (:data:`TRUSTED_KEYS`); the
matching **private key is held only by the issuer** (the Mac/ops commerce server),
never shipped. No phone-home — the math is the gate.

What the license carries (and why):

* **identity + term** — ``license_id``, ``issued_to``, ``issued_at`` /
  ``not_before`` / ``expires_at`` (the 12-month kept-proven window), ``seats``.
* **the paid boundary** — ``registry.pull_token``: a GHCR read-scoped token that
  pulls the private proven-matrix images (§9). The signature binds the token to
  this license, so a token can't be transplanted into a forged license. **This is
  the entire DRM** — no token → no proven-matrix images, but the open repos stay
  usable (AC-7 "low-friction over DRM"). Revocation is rotating the GHCR token.
* **entitlements** — coarse capability flags (e.g. ``proven-matrix-images``,
  ``signed-update-channel``) the installer can branch on.

**The signing contract (Mac's ``fulfillLicense`` must match byte-for-byte):** the
signed bytes are :func:`canonical_bytes` of the ``payload`` object —
``json.dumps(payload, sort_keys=True, separators=(",", ":"),
ensure_ascii=False).encode("utf-8")`` — a compact, **recursively key-sorted**,
UTF-8 encoding (RFC-8785-style canonicalization, pinned to this exact recipe).
The signature value is **standard base64** (with padding) of the 64-byte Ed25519
signature; the public key in :data:`TRUSTED_KEYS` is standard base64 of the
32-byte raw Ed25519 public key. Keep every payload value a string / int / bool /
list / nested object — **no floats** (cross-language float formatting diverges and
would break the signature).

This module is dependency-light at import time; the Ed25519 primitives
(``cryptography``) are imported lazily inside :func:`verify_signature` /
:func:`sign_payload` so ``import fieldkit.field_edition.license`` stays cheap and
a box without ``cryptography`` fails with a clear, actionable error only when it
actually needs to verify.
"""

from __future__ import annotations

import base64
import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

__all__ = [
    "LICENSE_SCHEMA",
    "DEFAULT_LICENSE_PATH",
    "TRUSTED_KEYS",
    "ACTIVE_KEY_ID",
    "PROD_KEY_PENDING",
    "LicenseError",
    "IssuedTo",
    "Registry",
    "License",
    "canonical_bytes",
    "sign_payload",
    "verify_signature",
    "parse_license",
    "load_license",
]

#: The schema discriminator every v1 payload carries.
LICENSE_SCHEMA = "orionfold.license/v1"

#: Where the bootstrap drops the license (chmod 600 — it carries a pull token).
DEFAULT_LICENSE_PATH = Path(
    os.environ.get("ORIONFOLD_LICENSE", str(Path.home() / ".orionfold" / "license"))
)

#: Sentinel for a key slot whose real public key the ops keypair hasn't produced
#: yet (same "drift is visible, not silent" stance as the image digest pins).
PROD_KEY_PENDING = "PROD_KEY_PENDING"

#: key_id → base64(32-byte raw Ed25519 public key). The installer trusts any key
#: listed here, so rotation is additive: publish a new key_id, sign new licenses
#: with it, retire the old one once outstanding licenses lapse.
#:
#: ``of-license-prod-2026`` is the PRODUCTION slot — ops generates the keypair
#: (see the keygen recipe in the §AC-7 relay / module tests), keeps the private
#: key in the commerce-server secret store, and sends ONLY the public key to drop
#: in here. Until then it is ``PROD_KEY_PENDING`` and signing real licenses with a
#: production key is blocked.
#:
#: ``of-license-dev-2026-06`` is a NON-PRODUCTION developer key whose public half
#: is committed so the vendored sample license + the unit tests self-validate. It
#: must NEVER sign a customer license. Its private seed is the openly-throwaway
#: ``bytes(range(32))`` (00 01 02 … 1f) — published on purpose so tests can
#: reproduce it without storing a secret; that is precisely why it is dev-only.
TRUSTED_KEYS: dict[str, str] = {
    "of-license-prod-2026": PROD_KEY_PENDING,
    "of-license-dev-2026-06": "A6EHv/POEL4dcN0Y50vAmWfk1jCbpQ1fHdyGZBJVMbg=",
}

#: The key_id the issuer should sign with in production once it is provisioned.
ACTIVE_KEY_ID = "of-license-prod-2026"


class LicenseError(Exception):
    """A license is missing, malformed, expired, or fails signature verification."""


@dataclass(frozen=True)
class IssuedTo:
    """Who the license was issued to (provenance — not security-bearing)."""

    name: str
    email: str
    org: str = ""

    @classmethod
    def from_obj(cls, obj: Mapping[str, Any]) -> "IssuedTo":
        return cls(name=str(obj.get("name", "")), email=str(obj.get("email", "")), org=str(obj.get("org", "")))


@dataclass(frozen=True)
class Registry:
    """How the private proven-matrix images are pulled (the paid boundary)."""

    type: str  # "ghcr"
    host: str  # "ghcr.io"
    namespace: str  # "orionfold"
    username: str  # the robot/login user the token authenticates as
    pull_token: str  # GHCR read:packages token — bound to this license by the signature

    @classmethod
    def from_obj(cls, obj: Mapping[str, Any]) -> "Registry":
        return cls(
            type=str(obj["type"]),
            host=str(obj["host"]),
            namespace=str(obj["namespace"]),
            username=str(obj.get("username", "")),
            pull_token=str(obj["pull_token"]),
        )


@dataclass(frozen=True)
class License:
    """A parsed, structurally-validated v1 license payload.

    Signature verification + term enforcement happen in :func:`load_license`;
    this dataclass is just the typed view of a verified payload."""

    license_id: str
    product: str
    edition: str
    tier: str
    issued_to: IssuedTo
    issued_at: str
    not_before: str
    expires_at: str
    seats: int
    entitlements: tuple[str, ...]
    registry: Registry
    raw: Mapping[str, Any]  # the exact payload object (for round-trip / debugging)

    @property
    def pull_token(self) -> str:
        return self.registry.pull_token

    def has_entitlement(self, name: str) -> bool:
        return name in self.entitlements

    def expires_dt(self) -> datetime:
        return _parse_ts(self.expires_at)

    def not_before_dt(self) -> datetime:
        return _parse_ts(self.not_before)

    def is_active(self, now: datetime | None = None) -> bool:
        now = now or datetime.now(timezone.utc)
        return self.not_before_dt() <= now < self.expires_dt()


# --- the signing contract ----------------------------------------------------


def canonical_bytes(payload: Mapping[str, Any]) -> bytes:
    """The exact bytes the Ed25519 signature covers (issuer + verifier MUST match).

    Compact, recursively key-sorted, UTF-8 JSON. The JS issuer must produce the
    identical bytes — sort keys at every object level, no inter-token whitespace,
    UTF-8, and no floats anywhere in the payload."""
    return json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def sign_payload(payload: Mapping[str, Any], private_key_b64: str) -> str:
    """Sign a payload with a base64 32-byte Ed25519 private seed → base64 sig.

    The issuer-side reference (Mac's ``fulfillLicense`` ports this to TS). Kept
    here so the sample license + the tests sign with the exact verifier recipe."""
    try:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    except Exception as err:  # noqa: BLE001 — cryptography missing
        raise LicenseError(
            "the `cryptography` package is required to sign a license "
            f"(pip install cryptography): {err}"
        ) from err
    seed = base64.b64decode(private_key_b64)
    if len(seed) != 32:
        raise LicenseError(f"Ed25519 private seed must be 32 bytes, got {len(seed)}")
    key = Ed25519PrivateKey.from_private_bytes(seed)
    sig = key.sign(canonical_bytes(payload))
    return base64.b64encode(sig).decode("ascii")


def verify_signature(payload: Mapping[str, Any], signature: Mapping[str, Any]) -> None:
    """Verify a detached Ed25519 signature against an embedded trusted key.

    Raises :class:`LicenseError` on an unknown/pending key id, a bad algorithm, a
    malformed signature, or a verification failure — never returns a soft verdict.
    """
    alg = str(signature.get("alg", ""))
    if alg != "ed25519":
        raise LicenseError(f"unsupported signature alg {alg!r} (expected 'ed25519')")
    key_id = str(signature.get("key_id", ""))
    pub_b64 = TRUSTED_KEYS.get(key_id)
    if pub_b64 is None:
        raise LicenseError(f"unknown signing key id {key_id!r} (not in TRUSTED_KEYS)")
    if pub_b64 == PROD_KEY_PENDING:
        raise LicenseError(
            f"signing key {key_id!r} is not provisioned yet (PROD_KEY_PENDING) — "
            "ops must generate the production keypair and embed its public key"
        )
    try:
        from cryptography.exceptions import InvalidSignature
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
    except Exception as err:  # noqa: BLE001 — cryptography missing
        raise LicenseError(
            "the `cryptography` package is required to verify a license "
            f"(pip install cryptography): {err}"
        ) from err
    try:
        pub = Ed25519PublicKey.from_public_bytes(base64.b64decode(pub_b64))
        sig = base64.b64decode(str(signature["value"]))
    except Exception as err:  # noqa: BLE001 — malformed base64 / key
        raise LicenseError(f"malformed signature or key material: {err}") from err
    try:
        pub.verify(sig, canonical_bytes(payload))
    except InvalidSignature as err:
        raise LicenseError(
            "license signature does not verify against the trusted public key "
            f"({key_id}) — the file was tampered with or signed by the wrong key"
        ) from err


# --- parsing + loading -------------------------------------------------------


def parse_license(payload: Mapping[str, Any]) -> License:
    """Structurally validate a payload into a :class:`License` (no crypto)."""
    schema = str(payload.get("schema", ""))
    if schema != LICENSE_SCHEMA:
        raise LicenseError(f"unexpected license schema {schema!r} (expected {LICENSE_SCHEMA!r})")
    try:
        return License(
            license_id=str(payload["license_id"]),
            product=str(payload["product"]),
            edition=str(payload.get("edition", "")),
            tier=str(payload.get("tier", "")),
            issued_to=IssuedTo.from_obj(payload.get("issued_to") or {}),
            issued_at=str(payload["issued_at"]),
            not_before=str(payload.get("not_before") or payload["issued_at"]),
            expires_at=str(payload["expires_at"]),
            seats=int(payload.get("seats", 1)),
            entitlements=tuple(str(e) for e in (payload.get("entitlements") or [])),
            registry=Registry.from_obj(payload["registry"]),
            raw=payload,
        )
    except KeyError as err:
        raise LicenseError(f"license payload missing required field: {err}") from err


def load_license(
    path: Path | None = None,
    *,
    now: datetime | None = None,
    enforce_term: bool = True,
) -> License:
    """Read, **verify**, and term-check the license file → a :class:`License`.

    The full AC-7 gate: parse the JSON, verify the Ed25519 signature against the
    embedded trusted key, then (``enforce_term``) reject a not-yet-valid or
    expired license. Any failure raises :class:`LicenseError` with an actionable
    message — the installer surfaces it as a named, fixable error (never a silent
    pass to an unentitled pull)."""
    path = path or DEFAULT_LICENSE_PATH
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as err:
        raise LicenseError(
            f"no license file at {path} — place your Field Edition license there "
            "(the bootstrap drops it; for a manual install copy the file ops issued)"
        ) from err
    except json.JSONDecodeError as err:
        raise LicenseError(f"license file at {path} is not valid JSON: {err}") from err

    payload = doc.get("payload")
    signature = doc.get("signature")
    if not isinstance(payload, Mapping) or not isinstance(signature, Mapping):
        raise LicenseError("license file must have an object `payload` and `signature`")

    verify_signature(payload, signature)
    lic = parse_license(payload)

    if enforce_term:
        now = now or datetime.now(timezone.utc)
        if now < lic.not_before_dt():
            raise LicenseError(
                f"license {lic.license_id} is not valid until {lic.not_before} (now {now.isoformat()})"
            )
        if now >= lic.expires_dt():
            raise LicenseError(
                f"license {lic.license_id} expired {lic.expires_at} — renew to keep the "
                "proven-matrix pull + signed update channel (the open repos stay usable)"
            )
    return lic


def _parse_ts(ts: str) -> datetime:
    """Parse an ISO-8601 UTC timestamp (accepting a trailing ``Z``)."""
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except ValueError as err:
        raise LicenseError(f"malformed timestamp {ts!r}: {err}") from err
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
