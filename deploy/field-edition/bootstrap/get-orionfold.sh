#!/bin/sh
# Copyright 2026 Manav Sehgal
# SPDX-License-Identifier: Apache-2.0
#
# Orionfold Arena Field Edition — first-boot bootstrap.
#
#   curl -fsSL https://getarena.orionfold.com | OF_LICENSE_URL='https://...' sh
#
# This is the customer-facing install entry point (license-workflow-v1 §5.2).
# It is RELEASED CODE authored Spark-side; getarena.orionfold.com DNS + hosting +
# the per-customer signed URLs that feed it are the Website/commerce peer's
# lane (Supabase bucket + CDN). The script itself is dumb and offline-honest:
# it drops the signed license file at the canonical path, installs fieldkit
# into a self-contained venv, and hands off to `fieldkit field-edition up`
# (which gates the box, pulls the proven matrix, and runs the §8 first-boot
# verify). The license is verified OFFLINE by fieldkit (Ed25519 vs the embedded
# trusted key) — this script does no entitlement check of its own; Supabase
# already did that when it minted the signed URL.
#
# ---------------------------------------------------------------------------
# Environment contract (the Website peer sets these in the order-status snippet)
# ---------------------------------------------------------------------------
#   OF_LICENSE_URL    (required) short-TTL signed URL to the customer's license
#                     file. Fetched into OF_LICENSE_PATH, chmod 600.
#   OF_WEIGHTS_URL    (optional) signed URL to the Q4_K_M GGUF. Only needed if
#                     weights are served from Supabase; for v1 they stay on HF
#                     and `up` pulls them, so this is normally unset.
#   OF_MODEL_STORE    (optional) where OF_WEIGHTS_URL lands if set
#                     (default: ~/.orionfold/models).
#   OF_LICENSE_PATH   (optional) license drop path
#                     (default: ~/.orionfold/license; mirrors fieldkit's
#                     ORIONFOLD_LICENSE override).
#   OF_FIELDKIT_SPEC  (optional) pip install target
#                     (default: "fieldkit[arena]"). Pin a version or point at a
#                     signed wheel URL for air-gapped/locked installs.
#   OF_VENV           (optional) venv location for the managed install
#                     (default: ~/.orionfold/venv).
#   OF_SKIP_DOCTOR=1  skip the §7 support-matrix gate (NOT recommended).
#   OF_SKIP_UP=1      install + stage the license only; do not run `up`
#                     (for operators who want to drive bring-up by hand).
# ---------------------------------------------------------------------------

set -eu

OF_LICENSE_PATH="${OF_LICENSE_PATH:-${HOME}/.orionfold/license}"
OF_MODEL_STORE="${OF_MODEL_STORE:-${HOME}/.orionfold/models}"
OF_FIELDKIT_SPEC="${OF_FIELDKIT_SPEC:-fieldkit[arena]}"
OF_VENV="${OF_VENV:-${HOME}/.orionfold/venv}"

# ---- output helpers (no color when not a tty) ------------------------------
if [ -t 1 ]; then B='\033[1m'; R='\033[0m'; Y='\033[33m'; G='\033[32m'; X='\033[31m'; else B=''; R=''; Y=''; G=''; X=''; fi
say()  { printf '%b\n' "${B}orionfold${R} $*"; }
warn() { printf '%b\n' "${Y}orionfold warning${R} $*" >&2; }
die()  { printf '%b\n' "${X}orionfold error${R} $*" >&2; exit 1; }

# Mask a signed URL down to origin+path so query-string tokens never echo.
mask_url() { echo "$1" | sed 's/?.*$/?<signed>/'; }

# ---- 0. preconditions ------------------------------------------------------
say "Arena Field Edition — first-boot bootstrap"

command -v curl >/dev/null 2>&1 || die "curl is required (install curl, then re-run)."

[ -n "${OF_LICENSE_URL:-}" ] || die \
"OF_LICENSE_URL is not set. Run the exact command from your Orionfold order page —
   the signed license URL expires within minutes and must be passed in, e.g.
     curl -fsSL https://getarena.orionfold.com | OF_LICENSE_URL='https://...' sh"

PY=""
for c in python3 python; do command -v "$c" >/dev/null 2>&1 && { PY="$c"; break; }; done
[ -n "$PY" ] || die "Python 3.10+ is required (DGX OS ships it; install python3 and re-run)."

# ---- 1. drop the signed license FIRST (cheapest, most time-sensitive) ------
# Signed URLs expire in minutes — fetch them before the slow fieldkit install
# so an expired URL fails fast with a clear message, not after a long wait.
say "fetching license -> ${OF_LICENSE_PATH} ($(mask_url "$OF_LICENSE_URL"))"
mkdir -p "$(dirname "$OF_LICENSE_PATH")"
tmp_lic="$(mktemp)"
trap 'rm -f "$tmp_lic"' EXIT INT TERM
curl -fsSL "$OF_LICENSE_URL" -o "$tmp_lic" \
  || die "license download failed — the signed URL may have expired. Re-copy it from your order page."
# Cheap shape check before we commit it (full Ed25519 verify happens in `up`).
head -c 1 "$tmp_lic" | grep -q '{' \
  || die "downloaded license is not a JSON license file (got a redirect or error page?). Re-copy the signed URL."
install -m 600 "$tmp_lic" "$OF_LICENSE_PATH"
rm -f "$tmp_lic"; trap - EXIT INT TERM
say "license written (chmod 600)."

# ---- 2. optional: stage Supabase-served weights ----------------------------
if [ -n "${OF_WEIGHTS_URL:-}" ]; then
  mkdir -p "$OF_MODEL_STORE"
  dest="${OF_MODEL_STORE}/model-Q4_K_M.gguf"
  say "fetching weights -> ${dest} ($(mask_url "$OF_WEIGHTS_URL")) ..."
  curl -fL --retry 3 --retry-delay 5 -C - "$OF_WEIGHTS_URL" -o "$dest" \
    || die "weights download failed — re-copy the signed URL from your order page (the download resumes on re-run)."
  say "weights staged."
else
  say "no OF_WEIGHTS_URL set — weights will be pulled by 'up' (v1 default: HuggingFace)."
fi

# ---- 3. resolve a fieldkit command (`FK`) ----------------------------------
# Order: an existing `fieldkit` on PATH -> pipx -> a self-contained venv.
# The venv path is the robust default on DGX OS: Debian marks the system Python
# "externally managed" (PEP 668), so a bare `pip install --user` is refused.
# A dedicated venv sidesteps that with no sudo, no apt, no --break-system.
FK=""
if command -v fieldkit >/dev/null 2>&1; then
  FK="fieldkit"
  say "using existing fieldkit: $($FK --version 2>/dev/null || echo present)"
elif command -v pipx >/dev/null 2>&1; then
  say "installing fieldkit via pipx ($OF_FIELDKIT_SPEC) ..."
  pipx install "$OF_FIELDKIT_SPEC" || die "pipx install failed for $OF_FIELDKIT_SPEC"
  if command -v fieldkit >/dev/null 2>&1; then FK="fieldkit"
  else FK="${HOME}/.local/bin/fieldkit"; fi
  [ -x "$FK" ] || command -v fieldkit >/dev/null 2>&1 || die \
"pipx installed fieldkit but it is not on PATH — run 'pipx ensurepath', open a new shell, and re-run."
else
  say "installing fieldkit into a managed venv at ${OF_VENV} ($OF_FIELDKIT_SPEC) ..."
  if [ ! -x "${OF_VENV}/bin/fieldkit" ]; then
    "$PY" -m venv "$OF_VENV" 2>/dev/null || die \
"could not create a venv at ${OF_VENV} — the python venv module is missing.
   Install it (DGX OS: 'sudo apt install python3-venv python3-full') and re-run,
   or install pipx ('sudo apt install pipx') for the pipx path."
    "${OF_VENV}/bin/python" -m pip install --quiet --upgrade pip >/dev/null 2>&1 || true
    "${OF_VENV}/bin/python" -m pip install --upgrade "$OF_FIELDKIT_SPEC" \
      || die "pip install failed for $OF_FIELDKIT_SPEC inside ${OF_VENV}"
  fi
  FK="${OF_VENV}/bin/fieldkit"
  [ -x "$FK" ] || die "fieldkit did not install into ${OF_VENV} (no ${FK})."
  say "installed: $($FK --version 2>/dev/null || echo present)"
  say "tip: add it to PATH with  export PATH=\"${OF_VENV}/bin:\$PATH\"  (so 'fieldkit' works directly)."
fi

# ---- 4. gate the box -------------------------------------------------------
if [ "${OF_SKIP_DOCTOR:-0}" = "1" ]; then
  warn "skipping the §7 support-matrix gate (OF_SKIP_DOCTOR=1)."
else
  say "checking the DGX OS / driver / CUDA / Container-Toolkit matrix ..."
  "$FK" field-edition doctor || die \
"this box does not satisfy the tested support matrix (see the report above).
   Update the flagged component, or set OF_SKIP_DOCTOR=1 to bypass at your own risk."
fi

# ---- 4b. source the NGC key for the NIM embedder ---------------------------
# The v1 default Cortex embedder is the NGC NIM image; its compose service needs
# NGC_API_KEY. The Field Edition box already runs NGC, so the key lives in
# ~/.nim/secrets.env. Export it here so `up` (and `down`/`repair`) can resolve
# it — `fieldkit` also reads this file directly, so this is belt-and-suspenders.
NIM_SECRETS="${HOME}/.nim/secrets.env"
if [ -z "${NGC_API_KEY:-}" ] && [ -f "$NIM_SECRETS" ]; then
  # shellcheck disable=SC1090
  . "$NIM_SECRETS" 2>/dev/null || true
  [ -n "${NGC_API_KEY:-}" ] && export NGC_API_KEY
fi
if [ -z "${NGC_API_KEY:-}" ]; then
  warn "no NGC_API_KEY found (env or ${NIM_SECRETS}). The v1 NIM embedder needs it;
   the guided onboarding will prompt you for one (paste a free key from
   https://org.ngc.nvidia.com/setup/api-keys) and save it to ${NIM_SECRETS}."
fi

# ---- 5. guided onboarding (the customer front door) ------------------------
# `onboard` is the Rich-rendered guided flow over `up`: it re-checks the matrix,
# captures a missing NGC key, narrates the model pull with a manifest + 'while
# you wait' cards, and opens the cockpit warm. `up` stays the headless engine and
# the documented fallback. Re-entrant: a re-run resumes from the stopped phase.
if [ "${OF_SKIP_UP:-0}" = "1" ]; then
  say "license staged + box gated. OF_SKIP_UP=1 set — run the bring-up yourself:"
  say "  $FK field-edition onboard   (guided)   ·   $FK field-edition up   (headless)"
  exit 0
fi

say "starting the guided onboarding (preflight · NGC key · model pull · first chat) ..."
# Read the NGC prompt from the controlling terminal even under `curl … | sh`
# (the script's own stdin is the pipe). No TTY (headless/CI) → skip the auto-open
# and rely on a pre-seeded key (a blank prompt aborts honestly with the fix).
if [ -e /dev/tty ]; then
  "$FK" field-edition onboard < /dev/tty || die \
"onboarding did not complete. It is re-entrant — fix the reported cause and re-run
   '$FK field-edition onboard'; completed phases are skipped."
else
  "$FK" field-edition onboard --no-open || die \
"onboarding did not complete. It is re-entrant — fix the reported cause and re-run
   '$FK field-edition onboard'; completed phases are skipped."
fi

say "${G}done.${R} The Arena cockpit + Advisor + Cortex are up. Open the cockpit and run a query."
