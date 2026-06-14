#!/bin/sh
# Copyright 2026 Manav Sehgal
# SPDX-License-Identifier: Apache-2.0
#
# Cosign KEY-BASED signing of the Orionfold proven-matrix images (§9/M3 of
# _SPECS/arena-field-edition-v1.md; distribution-spec §9). This is the
# OPERATOR-ARMED step.
#
# Why key-based, not keyless: Sigstore keyless needs Fulcio (the CA) at
# fulcio.sigstore.dev, which is network-blocked on the Spark box (it answers
# 443 in plaintext — "wrong version number" / "first record does not look like
# a TLS handshake"). Rekor + the TUF root ARE reachable, so we sign with a
# long-lived key (cosign's default, ECDSA P-256) and still upload to the public
# Rekor transparency log.
# The public key is committed + pinned (./proven-matrix.pub) — exactly mirroring
# how this repo already pins the (Ed25519) license key in `license.TRUSTED_KEYS`
# — same pin-a-committed-public-key pattern, different algorithm.
#
# What it signs: only Orionfold-built, GHCR-hosted, digest-pinned images
# (derived live from fieldkit so it stays in sync). Today that is exactly the
# llama.cpp CUDA-13 lane; cortex-embedder is auto-included once it is built +
# pinned at v1.1. Upstream images (pgvector) and NVIDIA NGC images (the NIM
# embedder) are NOT ours to sign — they are skipped.
#
# Default mode is DRY-RUN (lists + checks, signs nothing). Add --sign to arm.
#
#   ./sign-proven-matrix.sh                          # dry-run
#   COSIGN_PASSWORD=… ./sign-proven-matrix.sh --sign # the operator arm
#
# Key custody:
#   private key -> $OF_COSIGN_KEY (default ~/.orionfold/cosign/cosign.key),
#                  encrypted with COSIGN_PASSWORD — keep BOTH in the orionfold
#                  secret store (same custody as the prod license seed). NEVER
#                  commit the private key.
#   public  key -> ./proven-matrix.pub (committed + pinned; the verify side and
#                  the installer's §9 LiveUpdateChannel.verify_signature use it).
#
# Set OF_NO_TLOG=1 to skip the Rekor upload entirely (fully self-contained — use
# only if the transparency log is unreachable; verify then needs the same flag).

set -eu

HERE="$(cd "$(dirname "$0")" && pwd)"
PUB_PIN="${HERE}/proven-matrix.pub"
OF_COSIGN_KEY="${OF_COSIGN_KEY:-${HOME}/.orionfold/cosign/cosign.key}"
COSIGN_VERSION="${COSIGN_VERSION:-v2.4.1}"

DO_SIGN=0
DO_INSTALL=0
for arg in "$@"; do
  case "$arg" in
    --sign) DO_SIGN=1 ;;
    --install-cosign) DO_INSTALL=1 ;;
    -h|--help) sed -n '2,44p' "$0"; exit 0 ;;
    *) echo "unknown arg: $arg (try --help)" >&2; exit 2 ;;
  esac
done

if [ -t 1 ]; then B='\033[1m'; R='\033[0m'; Y='\033[33m'; G='\033[32m'; X='\033[31m'; else B=''; R=''; Y=''; G=''; X=''; fi
say()  { printf '%b\n' "${B}cosign${R} $*"; }
warn() { printf '%b\n' "${Y}cosign warning${R} $*" >&2; }
die()  { printf '%b\n' "${X}cosign error${R} $*" >&2; exit 1; }

TLOG_FLAG=""
[ "${OF_NO_TLOG:-0}" = "1" ] && TLOG_FLAG="--tlog-upload=false"

# --- the signable set: Orionfold GHCR images that are digest-pinned ----------
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
if [ -z "$REFS" ]; then
  warn "could not derive images from fieldkit — falling back to the embedded v1 lane digest."
  REFS="ghcr.io/orionfold/llama-server-cuda13@sha256:93993cc2609cc684cb0086e9512b1640bd2ac316084bd30955ccf4c6927f1ec2"
fi

say "proven-matrix images to sign (Orionfold GHCR, digest-pinned):"
printf '%s\n' "$REFS" | sed 's/^/  - /'
[ -n "$TLOG_FLAG" ] && say "${Y}Rekor tlog upload DISABLED${R} (OF_NO_TLOG=1) — verify needs --insecure-ignore-tlog."

# --- cosign availability -----------------------------------------------------
ensure_cosign() {
  if command -v cosign >/dev/null 2>&1; then
    say "cosign present: $(cosign version 2>/dev/null | sed -n 's/^GitVersion:[[:space:]]*//p' | head -1 || echo present)"
    return 0
  fi
  if [ "$DO_INSTALL" = "1" ]; then
    arch="$(uname -m)"; case "$arch" in aarch64|arm64) ca=arm64 ;; x86_64|amd64) ca=amd64 ;; *) die "unsupported arch $arch — install cosign manually" ;; esac
    url="https://github.com/sigstore/cosign/releases/download/${COSIGN_VERSION}/cosign-linux-${ca}"
    dest="${HOME}/.local/bin/cosign"
    say "installing cosign ${COSIGN_VERSION} (${ca}) -> ${dest} ..."
    mkdir -p "${HOME}/.local/bin"
    curl -fsSL "$url" -o "$dest" || die "cosign download failed ($url)"
    chmod +x "$dest"; export PATH="${HOME}/.local/bin:$PATH"
    say "installed: $(cosign version 2>/dev/null | sed -n 's/^GitVersion:[[:space:]]*//p' | head -1 || echo present)"
  else
    die "cosign not found. Re-run with --install-cosign, or install it manually
   (https://docs.sigstore.dev/cosign/system_config/installation/)."
  fi
}

# --- ensure the signing key pair (generate once) -----------------------------
ensure_key() {
  keydir="$(dirname "$OF_COSIGN_KEY")"
  prefix="${OF_COSIGN_KEY%.key}"
  if [ -f "$OF_COSIGN_KEY" ]; then
    say "using existing signing key: ${OF_COSIGN_KEY}"
  else
    [ -n "${COSIGN_PASSWORD+x}" ] || warn "COSIGN_PASSWORD not set — cosign will prompt to protect the new key."
    say "generating a new signing key pair at ${prefix}.{key,pub} ..."
    mkdir -p "$keydir"; chmod 700 "$keydir"
    ( cd "$keydir" && cosign generate-key-pair --output-key-prefix "$(basename "$prefix")" ) \
      || die "cosign generate-key-pair failed"
    chmod 600 "$OF_COSIGN_KEY"
    say "${Y}store ${OF_COSIGN_KEY} + its COSIGN_PASSWORD in the orionfold secret store (never commit the private key).${R}"
  fi
  # (Re)publish the public half to the committed pin so verify + the installer
  # always pin the current key.
  cosign public-key --key "$OF_COSIGN_KEY" > "$PUB_PIN" 2>/dev/null \
    || die "could not export the public key (wrong COSIGN_PASSWORD?)."
  say "pinned public key -> ${PUB_PIN}"
}

# --- dry-run vs arm ----------------------------------------------------------
if [ "$DO_SIGN" != "1" ]; then
  echo
  say "${Y}DRY-RUN${R} — nothing signed. The operator arms it with:"
  say "  COSIGN_PASSWORD=… $0 --install-cosign --sign"
  echo
  say "armed, it will (per image above) run key-based signing:"
  printf '%s\n' "$REFS" | sed "s#^#  cosign sign --key ${OF_COSIGN_KEY} ${TLOG_FLAG} --yes #"
  exit 0
fi

ensure_cosign
ensure_key

echo
say "ARMED (key-based). Signing with ${OF_COSIGN_KEY}."
[ -n "$TLOG_FLAG" ] || say "Signatures are pushed to GHCR + logged to the public Rekor log."
echo

signed_any=0
for ref in $REFS; do
  say "signing ${ref} ..."
  # shellcheck disable=SC2086
  cosign sign --key "$OF_COSIGN_KEY" $TLOG_FLAG --yes "$ref" || die "cosign sign failed for ${ref}"
  signed_any=1
done
[ "$signed_any" = "1" ] || die "nothing was signed."

echo
say "${G}done.${R} Commit ${PUB_PIN##*/} (the pinned public key) so the §9 verify can use it."
say "Confirm anytime with:  ./verify-proven-matrix.sh"
