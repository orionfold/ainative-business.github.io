#!/bin/sh
# Copyright 2026 Manav Sehgal
# SPDX-License-Identifier: Apache-2.0
#
# Verify the cosign KEY-BASED signatures on the Orionfold proven-matrix images
# against the PINNED public key (./proven-matrix.pub). This is the operator's
# post-sign confirmation AND the exact check the installer's §9
# LiveUpdateChannel.verify_signature must perform before apply -> gate ->
# receipt (M3). No browser, no OIDC, no private key.
#
#   ./verify-proven-matrix.sh
#
# Set OF_NO_TLOG=1 if the images were signed with the Rekor upload disabled
# (then verify adds --insecure-ignore-tlog=true to match).

set -eu

HERE="$(cd "$(dirname "$0")" && pwd)"
PUB_PIN="${HERE}/proven-matrix.pub"

if [ -t 1 ]; then B='\033[1m'; R='\033[0m'; G='\033[32m'; X='\033[31m'; else B=''; R=''; G=''; X=''; fi
say() { printf '%b\n' "${B}cosign-verify${R} $*"; }
die() { printf '%b\n' "${X}cosign-verify error${R} $*" >&2; exit 1; }

command -v cosign >/dev/null 2>&1 || die "cosign not found (see sign-proven-matrix.sh --install-cosign)."
[ -f "$PUB_PIN" ] || die "no pinned public key at ${PUB_PIN} — run ./sign-proven-matrix.sh --sign first (it writes the pin)."

TLOG_FLAG=""
[ "${OF_NO_TLOG:-0}" = "1" ] && TLOG_FLAG="--insecure-ignore-tlog=true"

say "pinning public key ${PUB_PIN}"

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
  # shellcheck disable=SC2086
  if cosign verify --key "$PUB_PIN" $TLOG_FLAG "$ref" >/dev/null 2>&1; then
    say "  ${G}OK${R} signed by the pinned key."
  else
    printf '%b\n' "${X}  FAIL${R} ${ref} — no valid signature from the pinned key." >&2
    fail=1
  fi
done

[ "$fail" = "0" ] || die "one or more proven-matrix images did not verify."
say "${G}all proven-matrix images verify.${R}"
