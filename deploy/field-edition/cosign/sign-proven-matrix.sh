#!/bin/sh
# Copyright 2026 Manav Sehgal
# SPDX-License-Identifier: Apache-2.0
#
# Cosign keyless signing of the Orionfold proven-matrix images (§9/M3 of
# _SPECS/arena-field-edition-v1.md; distribution-spec §9). This is the
# OPERATOR-ARMED step: signing uses Sigstore keyless via an interactive GitHub
# OIDC browser flow, which only the operator can complete — this script is
# authored Spark-side but RUN by the operator on a box logged in to the
# `orionfold` GitHub account.
#
# What it signs: only Orionfold-built, GHCR-hosted, digest-pinned images
# (derived live from fieldkit so it stays in sync). Today that is exactly the
# llama.cpp CUDA-13 lane; the cortex-embedder is auto-included once it is built
# + pinned at v1.1. Upstream images (pgvector) and NVIDIA NGC images (the NIM
# embedder) are NOT ours to sign — they are skipped.
#
# Default mode is DRY-RUN (lists + checks, signs nothing). Add --sign to arm.
#
#   ./sign-proven-matrix.sh                 # dry-run: show what would be signed
#   ./sign-proven-matrix.sh --install-cosign --sign   # the operator arm
#
# After a successful --sign, the resulting certificate identity + OIDC issuer
# are recorded to ./signed-identity.env — those are the values the installer's
# §9 verify (and ./verify-proven-matrix.sh) must pin. cosign writes the
# signature to the same GHCR repo (a .sig tag) and logs it to the public Rekor
# transparency log.

set -eu

HERE="$(cd "$(dirname "$0")" && pwd)"
IDENTITY_FILE="${HERE}/signed-identity.env"
COSIGN_VERSION="${COSIGN_VERSION:-v2.4.1}"

DO_SIGN=0
DO_INSTALL=0
for arg in "$@"; do
  case "$arg" in
    --sign) DO_SIGN=1 ;;
    --install-cosign) DO_INSTALL=1 ;;
    -h|--help) sed -n '2,40p' "$0"; exit 0 ;;
    *) echo "unknown arg: $arg (try --help)" >&2; exit 2 ;;
  esac
done

if [ -t 1 ]; then B='\033[1m'; R='\033[0m'; Y='\033[33m'; G='\033[32m'; X='\033[31m'; else B=''; R=''; Y=''; G=''; X=''; fi
say()  { printf '%b\n' "${B}cosign${R} $*"; }
warn() { printf '%b\n' "${Y}cosign warning${R} $*" >&2; }
die()  { printf '%b\n' "${X}cosign error${R} $*" >&2; exit 1; }

# --- the signable set: Orionfold GHCR images that are digest-pinned ----------
# Derived from the installed fieldkit so this never drifts from compose.py.
# Falls back to the known v1 lane digest if fieldkit is not importable.
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

# --- cosign availability -----------------------------------------------------
ensure_cosign() {
  if command -v cosign >/dev/null 2>&1; then
    say "cosign present: $(cosign version 2>/dev/null | sed -n 's/^GitVersion:[[:space:]]*//p' | head -1 || echo present)"
    return 0
  fi
  if [ "$DO_INSTALL" = "1" ]; then
    arch="$(uname -m)"; case "$arch" in aarch64|arm64) ca=arm64 ;; x86_64|amd64) ca=amd64 ;; *) die "unsupported arch $arch for auto-install — install cosign manually" ;; esac
    url="https://github.com/sigstore/cosign/releases/download/${COSIGN_VERSION}/cosign-linux-${ca}"
    dest="${HOME}/.local/bin/cosign"
    say "installing cosign ${COSIGN_VERSION} (${ca}) -> ${dest} ..."
    mkdir -p "${HOME}/.local/bin"
    curl -fsSL "$url" -o "$dest" || die "cosign download failed ($url)"
    chmod +x "$dest"
    command -v cosign >/dev/null 2>&1 || { warn "added ${HOME}/.local/bin/cosign — ensure ~/.local/bin is on PATH"; export PATH="${HOME}/.local/bin:$PATH"; }
    say "installed: $(cosign version 2>/dev/null | sed -n 's/^GitVersion:[[:space:]]*//p' | head -1 || echo present)"
  else
    die "cosign not found. Re-run with --install-cosign, or install it:
   https://docs.sigstore.dev/cosign/system_config/installation/
   (single Go binary; arm64: cosign-linux-arm64 from the sigstore/cosign releases)."
  fi
}

# --- GHCR write auth (the signature is pushed to the same repo) --------------
check_registry_auth() {
  # cosign reuses the docker credential store. The .sig is WRITTEN to GHCR, so
  # we need orionfold's own write:packages auth (per the publish-auth-surfaces
  # memory: `gh auth login` as orionfold -> docker login ghcr.io). We can only
  # check that *some* ghcr.io credential exists; the write is confirmed by sign.
  cfg="${HOME}/.docker/config.json"
  if [ -f "$cfg" ] && grep -q 'ghcr.io' "$cfg" 2>/dev/null; then
    say "found a ghcr.io credential in ~/.docker/config.json (must be the orionfold write token)."
  else
    warn "no ghcr.io credential detected in ~/.docker/config.json.
   Before --sign, authenticate as the orionfold account (it owns the package):
     gh auth switch -u orionfold   # or: gh auth login  (write:packages)
     echo \"\$(gh auth token)\" | docker login ghcr.io -u orionfold --password-stdin
   then switch git back: gh auth switch -u manavsehgal"
  fi
}

# --- dry-run vs arm ----------------------------------------------------------
if [ "$DO_SIGN" != "1" ]; then
  echo
  say "${Y}DRY-RUN${R} — nothing signed. The operator arms it with:"
  say "  $0 --install-cosign --sign"
  echo
  say "armed, it will (per image above) run the keyless GitHub-OIDC flow:"
  printf '%s\n' "$REFS" | sed 's#^#  cosign sign --yes #'
  exit 0
fi

ensure_cosign
check_registry_auth

echo
say "ARMED. cosign will open a browser for GitHub OIDC — authenticate as the"
say "orionfold GitHub account (its email becomes the signing identity)."
say "Signatures are pushed to GHCR + logged to the public Rekor log."
echo

signed_any=0
for ref in $REFS; do
  say "signing ${ref} ..."
  cosign sign --yes "$ref" || die "cosign sign failed for ${ref}"
  signed_any=1
done
[ "$signed_any" = "1" ] || die "nothing was signed."

# --- discover + record the identity the verify side must pin -----------------
# Read it back from the cert cosign just minted (don't guess the email/issuer).
first_ref="$(printf '%s\n' "$REFS" | head -1)"
say "reading back the signing identity from ${first_ref} ..."
bundle="$(cosign verify --output json "$first_ref" 2>/dev/null || true)"
ident=""; issuer=""
if [ -n "$bundle" ]; then
  ident="$(printf '%s' "$bundle" | python3 -c 'import sys,json;d=json.load(sys.stdin);o=d[0]["optional"];print(o.get("Subject") or o.get("Issuer","") and o.get("Subject",""))' 2>/dev/null || true)"
  issuer="$(printf '%s' "$bundle" | python3 -c 'import sys,json;d=json.load(sys.stdin);print(d[0]["optional"].get("Issuer",""))' 2>/dev/null || true)"
fi
{
  echo "# Recorded by sign-proven-matrix.sh — the cosign keyless identity to PIN on verify."
  echo "# The installer's §9 LiveUpdateChannel.verify_signature + verify-proven-matrix.sh use these."
  echo "OF_COSIGN_IDENTITY=\"${ident}\""
  echo "OF_COSIGN_ISSUER=\"${issuer}\""
} > "$IDENTITY_FILE"
say "recorded -> ${IDENTITY_FILE}"
printf '  identity: %s\n  issuer:   %s\n' "${ident:-<unread — inspect manually>}" "${issuer:-<unread>}"
if [ -z "$ident" ] || [ -z "$issuer" ]; then
  warn "could not auto-read the identity/issuer — confirm with:
   cosign verify --output json ${first_ref} | python3 -m json.tool
   and edit ${IDENTITY_FILE} (Subject -> OF_COSIGN_IDENTITY, Issuer -> OF_COSIGN_ISSUER)."
fi

echo
say "${G}done.${R} Commit signed-identity.env so the installer's §9 verify can pin it."
say "Confirm anytime with:  ./verify-proven-matrix.sh"
