#!/usr/bin/env python3
# Copyright 2026 Manav Sehgal
# SPDX-License-Identifier: Apache-2.0
"""Freeze the AC-7 license **canonicalization + signing conformance vector**.

The license contract has two owners (per `_SPECS/arena-field-edition-license-
workflow-v1.md` §4): Spark owns the offline verifier (`fieldkit.field_edition.
license`), Mac/Website owns the issuer (`fulfillLicense`, a TS/JS port of the same
canonicalization). The fragile seam is **canonicalization byte-drift** (§6): the
Python `canonical_bytes()` and the JS `canonicalize()` must produce byte-identical
signing input — sort keys at *every* level, no inter-token whitespace, UTF-8, and
no floats. One byte of divergence → every license silently fails to verify.

This script freezes a shared **conformance vector** that makes that contract
executable on both sides:

    fieldkit/src/fieldkit/field_edition/data/license-conformance-v1.json

Each case carries a `payload`, the exact `canonical_utf8` string Spark's
`canonical_bytes()` produces, its `canonical_sha256_12`, and the dev-key
`signature_b64`. The fieldkit test suite asserts the vendored vector still matches
the live `canonical_bytes()` / `sign_payload()` (drift guard for *our* side); the
Mac side adds a mirror assertion to `fulfillLicense`'s CI — re-canonicalize each
`payload`, assert the bytes/sha match, re-sign with the dev seed, assert the
signature matches. If both CIs are green, the two implementations are byte-aligned.

The cases deliberately stress the four dimensions canonicalization gets wrong
across languages: recursive key sort, compact separators, UTF-8 non-ASCII, and
integer/bool/null formatting (NO floats — float text diverges cross-language).

Signed with the **throwaway dev key** only (seed = `bytes(range(32))`, public half
already in `TRUSTED_KEYS["of-license-dev-2026-06"]`) so the vector self-validates
with no secret. A production keypair NEVER signs a conformance vector.

Usage:

    python3 scripts/field_edition/build_license_conformance_vector.py          # write
    python3 scripts/field_edition/build_license_conformance_vector.py --check   # verify, no write
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
LICENSE_SRC = REPO_ROOT / "fieldkit" / "src"
OUT_PATH = (
    REPO_ROOT
    / "fieldkit"
    / "src"
    / "fieldkit"
    / "field_edition"
    / "data"
    / "license-conformance-v1.json"
)

NAME = "license-conformance"
VERSION = "v1"
DEV_KEY_ID = "of-license-dev-2026-06"
#: The openly-throwaway dev seed (00 01 … 1f) — published on purpose; dev-only.
DEV_SEED_B64 = base64.b64encode(bytes(range(32))).decode("ascii")

#: A self-documenting copy of the JS port the issuer (`fulfillLicense`) must use.
JS_REFERENCE = (
    "function canonicalize(v){"
    "if(Array.isArray(v))return '['+v.map(canonicalize).join(',')+']';"
    "if(v&&typeof v==='object')return '{'+Object.keys(v).sort()."
    "map(k=>JSON.stringify(k)+':'+canonicalize(v[k])).join(',')+'}';"
    "return JSON.stringify(v);} "
    "const bytes=new TextEncoder().encode(canonicalize(payload));"
)

#: The conformance cases — each stresses a cross-language canonicalization trap.
CASES: list[dict[str, Any]] = [
    {
        "name": "nested-key-sort",
        "stresses": "recursive key sort at every object level + compact separators (no whitespace)",
        "payload": {"b": 1, "a": {"y": 2, "x": 1}},
    },
    {
        "name": "unicode-utf8",
        "stresses": "ensure_ascii=False / UTF-8 multibyte — accents, em dash, emoji, CJK must encode raw",
        "payload": {"org": "Acmé Robotics 🤖", "note": "café — naïve", "city": "東京"},
    },
    {
        "name": "scalars-no-floats",
        "stresses": "integer/bool/null formatting (1 not 1.0, true/false, null) — NO floats anywhere",
        "payload": {"seats": 1, "count": 1000000, "zero": 0, "flag": True, "off": False, "empty": None},
    },
    {
        "name": "full-license-founding25",
        "stresses": "a realistic v1 license payload (keys unsorted in source) incl. a unicode org + provenance",
        "payload": {
            "schema": "orionfold.license/v1",
            "product": "arena-field-edition",
            "license_id": "OF-FE-2026-0099",
            "tier": "field-edition",
            "edition": "founding-25",
            "seats": 1,
            "issued_to": {"org": "Société Générale Robotique", "name": "José Núñez", "email": "jose@example.com"},
            "issued_at": "2026-06-14T00:00:00Z",
            "not_before": "2026-06-14T00:00:00Z",
            "expires_at": "2027-06-14T00:00:00Z",
            "entitlements": ["proven-matrix-images", "signed-update-channel"],
            "registry": {
                "type": "ghcr",
                "host": "ghcr.io",
                "namespace": "orionfold",
                "username": "of-license-OF-FE-2026-0099",
                "pull_token": "ghp_EXAMPLE_read_packages_token_rotate_to_revoke",
            },
            "provenance": {"stripe_purchase_id": "pi_EXAMPLE0099", "stripe_price_id": "price_founding25"},
        },
    },
]


def _load_license_module():
    """Import the SHIPPED verifier so the vector is computed by the same code that
    validates it (the vector IS the validator's truth, not a parallel reimpl)."""
    if str(LICENSE_SRC) not in sys.path:
        sys.path.insert(0, str(LICENSE_SRC))
    from fieldkit.field_edition import license as lic  # noqa: WPS433

    return lic


def build() -> dict[str, Any]:
    lic = _load_license_module()
    pub_b64 = lic.TRUSTED_KEYS[DEV_KEY_ID]
    if pub_b64 == lic.PROD_KEY_PENDING:
        raise SystemExit(f"dev key {DEV_KEY_ID} unexpectedly pending — cannot build vector")

    cases: list[dict[str, Any]] = []
    for case in CASES:
        payload = case["payload"]
        canon = lic.canonical_bytes(payload)
        sig = lic.sign_payload(payload, DEV_SEED_B64)
        # Self-check at build time: the signature must verify with the dev key.
        lic.verify_signature(payload, {"alg": "ed25519", "key_id": DEV_KEY_ID, "value": sig})
        cases.append(
            {
                "name": case["name"],
                "stresses": case["stresses"],
                "payload": payload,
                "canonical_utf8": canon.decode("utf-8"),
                "canonical_sha256_12": hashlib.sha256(canon).hexdigest()[:12],
                "signature_b64": sig,
            }
        )

    return {
        "name": NAME,
        "version": VERSION,
        "purpose": (
            "Shared canonicalization + Ed25519 signing conformance vector for the "
            "orionfold.license/v1 contract. The Python verifier (fieldkit.field_edition."
            "license) and the JS issuer (fulfillLicense) MUST both reproduce every "
            "canonical_utf8 / canonical_sha256_12 / signature_b64 below. See "
            "_SPECS/arena-field-edition-license-workflow-v1.md §6."
        ),
        "schema": lic.LICENSE_SCHEMA,
        "algorithm": "ed25519",
        "canonicalization_py": (
            'json.dumps(payload, sort_keys=True, separators=(",", ":"), '
            'ensure_ascii=False).encode("utf-8")'
        ),
        "canonicalization_js": JS_REFERENCE,
        "rules": [
            "sort object keys at EVERY level (recursive)",
            "no inter-token whitespace (compact)",
            "UTF-8, emit non-ASCII raw (ensure_ascii=False)",
            "no floats anywhere (ints/bool/null/string/list/object only)",
            "signature_b64 = standard base64 (padded) of the 64-byte Ed25519 signature",
        ],
        "dev_key": {
            "key_id": DEV_KEY_ID,
            "note": "throwaway dev key (seed = bytes(range(32))); NEVER signs a real license",
            "private_seed_b64": DEV_SEED_B64,
            "public_key_b64": pub_b64,
        },
        "case_count": len(cases),
        "cases": cases,
    }


def _file_bytes(doc: dict[str, Any]) -> bytes:
    return (json.dumps(doc, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode("utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="verify the vendored vector matches; no write")
    parser.add_argument("--out", type=Path, default=OUT_PATH)
    args = parser.parse_args()

    doc = build()
    payload = _file_bytes(doc)
    sha = hashlib.sha256(payload).hexdigest()[:12]

    if args.check:
        if not args.out.exists():
            raise SystemExit(f"missing conformance vector: {args.out}")
        current = args.out.read_bytes()
        cur_sha = hashlib.sha256(current).hexdigest()[:12]
        if current != payload:
            raise SystemExit(
                f"DRIFT: {args.out} sha {cur_sha} != rebuilt {sha} "
                "(canonical_bytes/sign_payload changed? re-run without --check)"
            )
        print(f"ok: {args.out.name} matches the live verifier (sha {sha}, {doc['case_count']} cases)")
        return

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_bytes(payload)
    print(f"wrote {args.out} ({doc['case_count']} cases)")
    print(f"vector sha12: {sha}")
    for c in doc["cases"]:
        print(f"  {c['name']:24} canon-sha {c['canonical_sha256_12']}  sig {c['signature_b64'][:16]}…")


if __name__ == "__main__":
    main()
