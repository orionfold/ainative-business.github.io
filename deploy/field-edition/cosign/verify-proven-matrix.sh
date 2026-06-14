#!/bin/sh
# Copyright 2026 Manav Sehgal
# SPDX-License-Identifier: Apache-2.0
#
# Verify the cosign keyless signatures on the Orionfold proven-matrix images
# against the PINNED identity recorded by sign-proven-matrix.sh. This is the
# operator's post-sign confirmation AND the exact check the installer's §9
# LiveUpdateChannel.verify_signature must perform before apply -> gate ->
# receipt (M3). No browser / no OIDC — verification is offline-ish (it queries
# the registry + Rekor, but needs no login and no private key).
#
#   ./verify-proven-matrix.sh
#
# Reads ./signed-identity.env for OF_COSIGN_IDENTITY + OF_COSIGN_ISSUER. A
# keyless verify that does NOT pin both is meaningless (any GitHub user could
# sign), so this refuses to run until both are set.

set -eu

HERE="$(cd "$(dirname "$0")" && pwd)"
IDENTITY_FILE="${HERE}/signed-identity.env"

if [ -t 1 ]; then B='\033[1m'; R='\033[0m'; G='\033[32m'; X='\033[31m'; else B=''; R=''; G=''; X=''; fi
say() { printf '%b\n' "${B}cosign-verify${R} $*"; }
die() { printf '%b\n' "${X}cosign-verify error${R} $*" >&2; exit 1; }

command -v cosign >/dev/null 2>&1 || die "cosign not found (see sign-proven-matrix.sh --install-cosign)."

[ -f "$IDENTITY_FILE" ] || die "no ${IDENTITY_FILE} — run ./sign-proven-matrix.sh --sign first (it records the identity to pin)."
# shellcheck disable=SC1090
. "$IDENTITY_FILE"
[ -n "${OF_COSIGN_IDENTITY:-}" ] || die "OF_COSIGN_IDENTITY is empty in ${IDENTITY_FILE} — pin the signer identity (a keyless verify without it is meaningless)."
[ -n "${OF_COSIGN_ISSUER:-}" ] || die "OF_COSIGN_ISSUER is empty in ${IDENTITY_FILE} — pin the OIDC issuer."

say "pinning identity '${OF_COSIGN_IDENTITY}' / issuer '${OF_COSIGN_ISSUER}'"

signable_refs() {
  python3 - <<'PY' 2>/dev/null || true
try:
    from fieldkit.field_edition import compose
    cfg = compose.default_config()
    for p in (cfg.postgres.image, cfg.embedder.image, cfg.lane.image):
        if p.pinned and p.repo.startswith("ghcr.io/orionfold/"):
            print(f"{p.repo}@{p.digest}")
except Exception:
    pass
PY
}
REFS="$(signable_refs)"
[ -n "$REFS" ] || REFS="ghcr.io/orionfold/llama-server-cuda13@sha256:93993cc2609cc684cb0086e9512b1640bd2ac316084bd30955ccf4c6927f1ec2"

fail=0
for ref in $REFS; do
  say "verifying ${ref} ..."
  if cosign verify \
        --certificate-identity "$OF_COSIGN_IDENTITY" \
        --certificate-oidc-issuer "$OF_COSIGN_ISSUER" \
        "$ref" >/dev/null 2>&1; then
    say "  ${G}OK${R} signed by the pinned identity."
  else
    printf '%b\n' "${X}  FAIL${R} ${ref} — no valid signature from the pinned identity/issuer." >&2
    fail=1
  fi
done

[ "$fail" = "0" ] || die "one or more proven-matrix images did not verify."
say "${G}all proven-matrix images verify.${R}"
